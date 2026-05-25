# Этап Q: Death & Dying — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подключить спасброски от смерти PHB-2024 (dying/unconscious/stabilize/смерть) в движок, добавить лут трупов через CORPSE-объект, пересмотреть условие конца боя.

**Architecture:** Domain `Creature` получает флаг `uses_death_saves` + поле `death_saves: DeathSaveState | None` и методы согласованных переходов. `Encounter` реагирует на падение в 0 HP (PC → dying+Unconscious, NPC → CORPSE-объект с лутом), на старте хода лежачего PC авто-бросает death save, пересматривает `_check_end_condition` (downed ≠ поражение). Новый `StabilizeAction`. Новые события + рендер в CLI/TUI + TUI overlay.

**Tech Stack:** Python 3.12, pydantic v2 (frozen DTO, `extra="forbid"`), Textual, hexagonal architecture, pytest, mypy strict, ruff.

**Конвенции репо:**
- Коммиты: автор `Maxim Lokotkov`, email `anticrab@users.noreply.github.com`. Команда:
  `git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "..."`.
- Документация и комментарии — на русском.
- После каждого task'а полный sweep: `python3 -m pytest -q` + `mypy src/` + `ruff check`.
- Запреты git: `push`, `reset --hard`, `rebase` — не использовать.

---

## Уже готовый фундамент (НЕ переписывать, переиспользовать)

- `src/dnd/domain/values/death_save_state.py` — `DeathSaveState` (frozen, slots):
  `apply_save_roll(d20_raw)`, `apply_damage_at_zero(*, is_critical=False)`,
  `stabilized()`, `reset()`, свойства `is_dead` (failures>=3), `is_stable`
  (stable or successes>=3). На нат-20 `apply_save_roll` возвращает
  `DeathSaveState()` (сброс); поднятие на 1 HP — забота вызывающего.
- `src/dnd/domain/entities/creature.py`:
  - `take_damage(damage, *, is_critical=False) -> DamageResult`
    (`was_lethal`, `killed_outright`, `overflow`, `final_amount`).
  - `heal(amount) -> HealResult` (`revived: bool` — поднял с 0 HP).
  - `apply_condition(id)`, `remove_condition(id)`, `has_condition(id)`.
  - `is_alive` (HP>0), `is_at_zero_hp` (HP==0).
  - фабрика `Creature.create(*, id_, name, abilities, max_hp, ...)` — kwargs.
- `src/dnd/domain/conditions/builtin.py`: `UNCONSCIOUS: ConditionId`.
- `src/dnd/domain/values/object_kind.py`: `ObjectKind` StrEnum (DOOR/CHEST/BARREL/WINDOW).
- `src/dnd/domain/entities/battlefield.py`: `place_object`, `object_at`,
  `objects_at(square)`, `remove_creature`, `position_of`, `creatures_at`.
- `src/dnd/domain/entities/interactable.py`: `InteractableObject` (id, kind, pos, state).
- `src/dnd/application/inventory/loot_helpers.py`: `dump_loot_entries(stacks)`,
  `parse_loot(raw, repo)`.
- `src/dnd/application/engine/actions/pickup.py`: `PickupAction` — работает с любым
  открытым (`state["open"]`), не запертым InteractableObject.
- `src/dnd/application/abilities/defaults.py`: `register_default_abilities(registry)`.
- `src/dnd/application/engine/encounter.py`: `start_turn`, `end_turn`,
  `_check_end_condition`, `_is_outcome_decided`, `current_actor_id`,
  `_participants`, `_factions`, `_deps` (event_bus/dice_roller/battlefield).

---

## File Structure

**Создаются:**
- `src/dnd/application/engine/actions/stabilize.py` — `StabilizeAction` + `StabilizeParams`.
- `tests/unit/domain/test_creature_dying.py` — domain death-saves.
- `tests/integration/engine/test_encounter_dying.py` — lifecycle dying.
- `tests/integration/engine/test_encounter_end_condition_dying.py` — end-condition.
- `tests/integration/engine/test_stabilize_action.py` — StabilizeAction.
- `tests/integration/engine/test_corpse_loot.py` — спавн CORPSE + лут.
- `tests/integration/tui/test_death_save_overlay.py` — overlay pilot.
- `docs/DYING.md` — модель умирания.

**Модифицируются:**
- `src/dnd/domain/entities/creature.py` — поля + методы dying.
- `src/dnd/domain/values/object_kind.py` — `CORPSE`.
- `src/dnd/application/dto/engine_event.py` — 3 новых события.
- `src/dnd/application/dto/player_intent.py` — `StabilizeIntent`.
- `src/dnd/application/engine/encounter.py` — death-wiring + end-condition + corpse.
- `src/dnd/application/engine/game_runner.py` — диспатч `StabilizeIntent`.
- `src/dnd/application/abilities/defaults.py` — ability `stabilize`.
- `src/dnd/interfaces/cli/event_printer.py` — handlers новых событий.
- `src/dnd/interfaces/tui/widgets/status_widget.py` — пипсы death-saves.
- `src/dnd/interfaces/tui/widgets/map_widget.py` — глиф CORPSE (на клетке без живых).
- `docs/ROADMAP.md`, `docs/TUI.md` — пометки.

---

## Task Q-1: `Creature` — флаг + поле + методы dying

**Files:**
- Modify: `src/dnd/domain/entities/creature.py`
- Test: `tests/unit/domain/test_creature_dying.py`

Контракт методов:
- `begin_dying() -> bool` — если `uses_death_saves` и `death_saves is None` и
  `is_at_zero_hp`: ставит `death_saves = DeathSaveState()` и накладывает
  `UNCONSCIOUS`; возвращает True. Иначе False.
- `roll_death_save(d20_raw: int) -> DeathSaveOutcome` — только если в dying.
  Нат-20 → `heal(1)` + `death_saves=None` + снять `UNCONSCIOUS`
  (result="recovered"). Иначе делегирует в `death_saves.apply_save_roll`;
  result="success"|"failure" по тому, вырос successes или failures.
- `is_dead` property: `uses_death_saves and death_saves is not None and death_saves.is_dead`.
- `take_damage` расширяется: если **до** удара `is_at_zero_hp` и в dying →
  `death_saves = death_saves.apply_damage_at_zero(is_critical=is_critical)`.
  Если новый удар `killed_outright` ИЛИ опустил живого PC в dying с massive →
  `death_saves = DeathSaveState(failures=3)`.
- `heal`: если был в dying и стал HP>0 → `death_saves=None` + снять `UNCONSCIOUS`.

`DeathSaveOutcome` — новый frozen dataclass в creature.py рядом с `DamageResult`:
поля `result: Literal["success","failure","recovered"]`, `successes: int`,
`failures: int`, `d20_raw: int`.

- [ ] **Step 1: Написать падающий тест**

```python
# tests/unit/domain/test_creature_dying.py
"""Q-1: Creature — спасброски от смерти, dying state."""
from __future__ import annotations

import pytest

from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.damage_type import DamageType


def _pc(max_hp: int = 10, *, uses_death_saves: bool = True) -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=max_hp, armor_class=12, speed_ft=30,
    )
    c.uses_death_saves = uses_death_saves
    return c


def _hit(c: Creature, amount: int, *, crit: bool = False) -> None:
    c.take_damage(DamageInstance(amount=amount, type_=DamageType.SLASHING), is_critical=crit)


def test_pc_dropped_to_zero_begins_dying() -> None:
    c = _pc(10)
    _hit(c, 10)
    assert c.is_at_zero_hp
    # ещё не dying, пока не begin_dying (это делает Encounter)
    assert c.death_saves is None
    assert c.begin_dying() is True
    assert c.death_saves is not None
    assert c.has_condition(UNCONSCIOUS)
    assert not c.is_dead


def test_npc_does_not_begin_dying() -> None:
    c = _pc(10, uses_death_saves=False)
    _hit(c, 10)
    assert c.begin_dying() is False
    assert c.death_saves is None


def test_death_save_success_then_failure() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    out = c.roll_death_save(15)
    assert out.result == "success"
    assert out.successes == 1 and out.failures == 0
    out = c.roll_death_save(5)
    assert out.result == "failure"
    assert out.successes == 1 and out.failures == 1


def test_nat20_recovers_one_hp() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    out = c.roll_death_save(20)
    assert out.result == "recovered"
    assert c.hit_points.current == 1
    assert c.death_saves is None
    assert not c.has_condition(UNCONSCIOUS)


def test_nat1_two_failures() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    out = c.roll_death_save(1)
    assert out.failures == 2


def test_three_failures_is_dead() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    c.roll_death_save(5)
    c.roll_death_save(5)
    out = c.roll_death_save(5)
    assert out.failures == 3
    assert c.is_dead


def test_damage_at_zero_adds_failure_crit_two() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    _hit(c, 3)  # обычный удар по лежачему
    assert c.death_saves.failures == 1
    _hit(c, 3, crit=True)  # крит в упор
    assert c.death_saves.failures == 3
    assert c.is_dead


def test_massive_damage_kills_outright() -> None:
    c = _pc(10)
    _hit(c, 25)  # overflow 15 >= max 10 → killed_outright
    c.begin_dying()  # no-op в смысле: всё равно проставит, но...
    # massive damage обрабатывается в take_damage:
    assert c.death_saves is not None
    assert c.death_saves.is_dead


def test_heal_from_dying_restores_consciousness() -> None:
    c = _pc(10)
    _hit(c, 10)
    c.begin_dying()
    c.heal(4)
    assert c.death_saves is None
    assert not c.has_condition(UNCONSCIOUS)
    assert c.hit_points.current == 4
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `python3 -m pytest tests/unit/domain/test_creature_dying.py -q`
Expected: FAIL (`uses_death_saves`/`death_saves`/`begin_dying`/`roll_death_save` не существуют).

- [ ] **Step 3: Реализовать в `creature.py`**

В импортах добавить:
```python
from typing import Literal
from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.values.death_save_state import DeathSaveState
```

Рядом с `DamageResult` (после него) добавить:
```python
@dataclass(frozen=True, slots=True)
class DeathSaveOutcome:
    """Результат одного спасброска от смерти (для публикации события)."""

    result: Literal["success", "failure", "recovered"]
    successes: int
    failures: int
    d20_raw: int
```

В классе `Creature` добавить поля (после `concentration`, до `ability_ids`):
```python
    uses_death_saves: bool = False
    """True у персонажей игроков и важных NPC: при 0 HP уходят в спасброски
    от смерти, а не умирают мгновенно (PHB-2024 стр. 27). NPC-расходники —
    False (default): при 0 HP их убирает Encounter в CORPSE."""

    death_saves: DeathSaveState | None = None
    """Не None ⟺ существо в dying (0 HP, ещё не мёртв и не поднят). Ставится
    через begin_dying(); сбрасывается в None при лечении/нат-20. Инвариант
    синхронизируется с HitPoints и Condition Unconscious."""
```

Методы (в секции HP, после `heal`):
```python
    def begin_dying(self) -> bool:
        """Войти в состояние умирания. Вызывает Encounter при падении в 0 HP.

        Возвращает True, если переход состоялся (PC при 0 HP, ещё не dying).
        Накладывает Unconscious. Для NPC (uses_death_saves=False) — no-op.
        """
        if not self.uses_death_saves:
            return False
        if not self.is_at_zero_hp:
            return False
        if self.death_saves is not None:
            return False
        self.death_saves = DeathSaveState()
        self.apply_condition(UNCONSCIOUS)
        return True

    def roll_death_save(self, d20_raw: int) -> DeathSaveOutcome:
        """Применить бросок спасброска от смерти. d20_raw — сырое значение."""
        if self.death_saves is None:
            raise ValueError("roll_death_save called on a creature not dying")
        if d20_raw == 20:
            self.hit_points = self.hit_points.heal(1)
            self.death_saves = None
            self.remove_condition(UNCONSCIOUS)
            return DeathSaveOutcome(result="recovered", successes=0, failures=0, d20_raw=20)
        before = self.death_saves
        self.death_saves = before.apply_save_roll(d20_raw)
        result: Literal["success", "failure"] = (
            "success" if self.death_saves.successes > before.successes else "failure"
        )
        return DeathSaveOutcome(
            result=result,
            successes=self.death_saves.successes,
            failures=self.death_saves.failures,
            d20_raw=d20_raw,
        )

    @property
    def is_dead(self) -> bool:
        """Окончательно мёртв (3 провала спасбросков). Только для тех, кто
        uses_death_saves; NPC «мертвы» через is_alive=False + CORPSE."""
        return (
            self.uses_death_saves
            and self.death_saves is not None
            and self.death_saves.is_dead
        )
```

В `take_damage`, ПОСЛЕ строки `self.hit_points = self.hit_points.take_damage(final)`
и вычисления `was_lethal`/`killed_outright`, перед блоком концентрации, вставить:
```python
        # Q-1: спасброски от смерти (PHB-2024 стр. 27).
        if self.uses_death_saves:
            if killed_outright:
                # Огромный урон — мгновенная смерть, минуя спасброски.
                self.death_saves = DeathSaveState(failures=3)
            elif not was_alive and self.death_saves is not None:
                # Удар по уже лежачему: провал (крит → 2).
                self.death_saves = self.death_saves.apply_damage_at_zero(
                    is_critical=is_critical
                )
```
(`was_alive` уже вычислен выше в методе как снимок ДО удара.)

В `heal`, после вычисления `revived`, перед `return HealResult(...)`:
```python
        if revived and self.death_saves is not None:
            self.death_saves = None
            self.remove_condition(UNCONSCIOUS)
```
где `revived = was_at_zero and not self.is_at_zero_hp` (уже есть как поле результата;
вынести в локальную переменную, если её нет).

- [ ] **Step 4: Запустить — зелено**

Run: `python3 -m pytest tests/unit/domain/test_creature_dying.py -q`
Expected: PASS (9 тестов).

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/domain/entities/creature.py tests/unit/domain/test_creature_dying.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(domain): Q-1 Creature dying state + death saves"
```

---

## Task Q-2: Encounter — развилка при падении в 0 HP (PC → dying)

**Files:**
- Modify: `src/dnd/application/engine/encounter.py`
- Test: `tests/integration/engine/test_encounter_dying.py`

Подход: Encounter подписывается на `AttackResolved` (там `downed=True` ⟺
`was_lethal`). В handler'е `_on_downed`: для актора-цели определить, кто упал.
Но `AttackResolved` несёт `target_id`. Handler берёт `target = participants[target_id]`,
и если `target.is_at_zero_hp` и `target.uses_death_saves` и не dying → `begin_dying()`
+ публикация (Unconscious уже наложен внутри begin_dying). NPC (не uses_death_saves)
→ Q-8 (CORPSE) — пока в Q-2 только PC-ветка + `CreatureDied` для is_dead.

Подписка оформляется как `_on_provoked`: в `start()` подписаться, в
`_check_end_condition`/`_force_end` — отписаться (добавить `_unsubscribe_downed`).

- [ ] **Step 1: Падающий тест**

```python
# tests/integration/engine/test_encounter_dying.py
"""Q-2/Q-3: lifecycle умирания в Encounter."""
from __future__ import annotations

from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.damage_type import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _pc() -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    c.uses_death_saves = True
    return c


def _goblin() -> Creature:
    return Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
    )


def _enc(pc: Creature, gob: Creature) -> Encounter:
    bf = Battlefield(8, 8)
    bf.place_creature(pc.id, Square(1, 1))
    bf.place_creature(gob.id, Square(6, 6))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 40)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc


def test_pc_dropped_to_zero_enters_dying_not_dead() -> None:
    pc, gob = _pc(), _goblin()
    enc = _enc(pc, gob)
    # Симулируем смертельный урон по PC через прямой take_damage + публикацию,
    # эмулируя то, что делает AttackAction: проще ударить и вручную toggle'нуть
    # через приватный путь движка — но корректнее проверить через handler.
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    from dnd.application.dto.engine_event import AttackResolved
    enc.event_bus.publish(AttackResolved(
        attacker_id=gob.id, target_id=pc.id, attack_roll_id="r",
        hit=True, is_critical=False, downed=True,
    ))
    assert pc.death_saves is not None
    assert pc.has_condition(UNCONSCIOUS)
    assert not pc.is_dead
    assert not enc.is_concluded  # бой продолжается
```

- [ ] **Step 2: Запустить — FAIL** (death_saves остаётся None — нет handler'а).

Run: `python3 -m pytest tests/integration/engine/test_encounter_dying.py::test_pc_dropped_to_zero_enters_dying_not_dead -q`

- [ ] **Step 3: Реализация в encounter.py**

В импорты событий добавить `AttackResolved`, `CreatureDied` (создаётся в Q-6 —
для Q-2 импортировать только `AttackResolved`; `CreatureDied` подключить в Q-6).
В `__init__`/state добавить `self._unsubscribe_downed: Callable[[], None] | None = None`.

В `start()`, рядом с подпиской на `OpportunityAttackProvoked`:
```python
        self._unsubscribe_downed = self._deps.event_bus.subscribe(
            AttackResolved, self._on_downed
        )
```

Метод:
```python
    def _on_downed(self, event: AttackResolved) -> None:
        """Реакция на падение цели в 0 HP (PHB-2024 стр. 27).

        PC (uses_death_saves) → переход в dying (Unconscious + DeathSaveState).
        NPC → судьба решается в end_turn/Q-8 (CORPSE).
        """
        if not event.downed or self._state.concluded:
            return
        target = self._participants.get(event.target_id)
        if target is None:
            return
        if target.uses_death_saves and target.is_at_zero_hp:
            target.begin_dying()
```

В `_check_end_condition` и `_force_end_by_round_limit`, рядом с отпиской
`_unsubscribe_provoked`, добавить симметричную отписку `_unsubscribe_downed`:
```python
        if self._unsubscribe_downed is not None:
            self._unsubscribe_downed()
            self._unsubscribe_downed = None
```

- [ ] **Step 4: Запустить — PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/application/engine/encounter.py tests/integration/engine/test_encounter_dying.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(engine): Q-2 PC уходит в dying при падении в 0 HP"
```

---

## Task Q-3: Encounter — авто death-save на старте хода лежачего PC

**Files:**
- Modify: `src/dnd/application/engine/encounter.py`
- Test: `tests/integration/engine/test_encounter_dying.py` (дополнить)

В `start_turn`, после вычисления `actor`/сброса stances и ДО формирования
`TurnContext`/публикации `TurnStarted`, добавить авто-бросок death save, если
актор в dying и не stable/dead. Бросок — через `self._deps.dice_roller`
выражением `d20` (без модификаторов, PHB-2024 стр. 27). Публикуется
`DeathSaveRolled` (Q-6 — для Q-3 ввести событие сразу, см. ниже минимальную
версию или объединить с Q-6; здесь публикуем).

Чтобы не зависеть от Q-6 по порядку, **в Q-3 добавляем событие `DeathSaveRolled`
сразу** (минимально), а Q-6 добавит `CreatureStabilized`/`CreatureDied` и рендер.

- [ ] **Step 1: Падающий тест (дописать в файл Q-2)**

```python
def test_dying_pc_auto_rolls_death_save_on_turn_start() -> None:
    from dnd.application.dto.engine_event import DeathSaveRolled
    pc, gob = _pc(), _goblin()
    bf = Battlefield(8, 8)
    bf.place_creature(pc.id, Square(1, 1))
    bf.place_creature(gob.id, Square(6, 6))
    # rolls: первый d20 пойдёт на инициативу обоим, дальше death saves.
    # Дадим фиксированные 15 (успех).
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 19] + [15] * 20)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()

    captured: list[DeathSaveRolled] = []
    enc.event_bus.subscribe(DeathSaveRolled, captured.append)

    # Прокрутить ходы до хода PC.
    for _ in range(10):
        if enc.current_actor_id == pc.id:
            break
        enc.start_turn()
        enc.end_turn()
    enc.start_turn()  # ход PC → авто death save
    assert len(captured) == 1
    assert captured[0].actor_id == pc.id
    assert captured[0].result == "success"
    assert pc.death_saves.successes == 1
```

- [ ] **Step 2: FAIL** (`DeathSaveRolled` не существует / нет авто-броска).

- [ ] **Step 3: Реализация**

В `src/dnd/application/dto/engine_event.py` добавить (рядом с прочими событиями):
```python
class DeathSaveRolled(EngineEvent):
    """Спасбросок от смерти PC (PHB-2024 стр. 27)."""

    actor_id: CreatureId
    d20_raw: int
    result: Literal["success", "failure", "recovered"]
    successes: int
    failures: int
```
(добавить `from typing import Literal`, если ещё нет, и в `__all__`.)

В `encounter.py` импортировать `DeathSaveRolled`, `DiceExpr`, `RollContext`,
`RollPurpose` (часть уже импортирована для инициативы — переиспользовать).
В `start_turn`, перед формированием `TurnContext`:
```python
        # Q-3: лежачий PC на старте своего хода бросает спасбросок от смерти.
        if (
            actor.death_saves is not None
            and not actor.death_saves.is_dead
            and not actor.death_saves.is_stable
        ):
            self._roll_death_save_for(actor)
```

Метод:
```python
    def _roll_death_save_for(self, actor: Creature) -> None:
        ctx = RollContext(
            purpose=RollPurpose.SAVE,
            actor_id=actor.id,
            tags=("death_save",),
        )
        result = self._deps.dice_roller.roll(DiceExpr.parse("d20"), ctx)
        d20_raw = result.d20_raw if result.d20_raw is not None else result.total
        outcome = actor.roll_death_save(d20_raw)
        if outcome.result == "recovered":
            actor.remove_condition(UNCONSCIOUS)  # на случай, если не снято
        self._deps.event_bus.publish(
            DeathSaveRolled(
                actor_id=actor.id,
                d20_raw=outcome.d20_raw,
                result=outcome.result,
                successes=outcome.successes,
                failures=outcome.failures,
            )
        )
```
(импортировать `UNCONSCIOUS` из `dnd.domain.conditions.builtin`; `RollPurpose.SAVE` —
проверить наличие значения; если нет — использовать существующий подходящий
purpose, напр. `RollPurpose.SAVING_THROW`. Реализатор сверяет enum в
`dnd/domain/values/roll_context.py` или аналоге.)

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/application/engine/encounter.py src/dnd/application/dto/engine_event.py tests/integration/engine/test_encounter_dying.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(engine): Q-3 авто death-save на старте хода + DeathSaveRolled"
```

---

## Task Q-4: Урон по лежачему в упор → авто-крит (2 провала)

**Files:**
- Modify: `src/dnd/application/engine/actions/attack.py`
- Test: `tests/integration/engine/test_encounter_dying.py` (дополнить)

PHB-2024 стр. 27: попадание по существу в 0 HP в пределах 5 фт — критическое.
В `AttackAction.execute`, при определении `is_crit`, добавить: если цель
`is_at_zero_hp` (в dying) и дистанция атакующий↔цель ≤ 5 фт → `is_crit = True`.

- [ ] **Step 1: Падающий тест**

```python
def test_melee_hit_on_dying_pc_is_auto_crit() -> None:
    from dnd.application.engine.actions.attack import AttackAction, AttackParams
    from dnd.application.dto.weapon import to_attack_params  # если есть helper
    pc, gob = _pc(), _goblin()
    bf = Battlefield(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(gob.id, Square(2, 3))  # в упор (1 клетка = 5 фт)
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 19] + [10] * 20)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    # Прокрутить до хода гоблина.
    for _ in range(10):
        if enc.current_actor_id == gob.id:
            break
        enc.start_turn(); enc.end_turn()
    ctx = enc.start_turn()
    before = pc.death_saves.failures
    # Гоблин бьёт лежачего PC в упор.
    params = AttackParams(
        target_id=pc.id, damage_expr="1d6", damage_type=DamageType.SLASHING,
        attack_bonus=4, reach_ft=5, ranged=False,
    )
    AttackAction().execute(gob, params, ctx)
    assert pc.death_saves.failures - before == 2  # авто-крит → 2 провала
```
(Реализатор: точную сигнатуру `AttackParams` и фабрику из equipped_weapon
взять из `attack.py`; тест адаптировать под реальный конструктор.)

- [ ] **Step 2: FAIL** (обычный удар даёт +1, не +2).

- [ ] **Step 3: Реализация в attack.py**

Найти место вычисления `is_crit` (бросок атаки). После него, до применения урона:
```python
        # PHB-2024 стр. 27: попадание по лежачему (0 HP) в упор — авто-крит.
        if hit and target.is_at_zero_hp and not params.ranged:
            attacker_pos = ctx.battlefield.position_of(actor.id)
            target_pos = ctx.battlefield.position_of(target.id)
            if attacker_pos.chebyshev_distance_to(target_pos) <= 1:
                is_crit = True
```
(сверить имя метода дистанции на `Square` — вероятно `chebyshev_distance_to`
или `distance_to`; реализатор уточняет. `params.ranged` — сверить имя поля.)

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/application/engine/actions/attack.py tests/integration/engine/test_encounter_dying.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(engine): Q-4 авто-крит по лежачему в упор → 2 провала"
```

---

## Task Q-5: End-condition — downed PC ≠ поражение

**Files:**
- Modify: `src/dnd/application/engine/encounter.py`
- Test: `tests/integration/engine/test_encounter_end_condition_dying.py`

Переписать `_is_outcome_decided` и `_check_end_condition`: сторона считается
«в бою», если есть существо, которое `is_alive` **ИЛИ** «спасаемо»
(`uses_death_saves and death_saves is not None and not death_saves.is_dead`).

- [ ] **Step 1: Падающий тест**

```python
# tests/integration/engine/test_encounter_end_condition_dying.py
"""Q-5: end-condition с учётом dying."""
from __future__ import annotations

from dnd.application.dto.engine_event import EncounterEnded
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.damage_type import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _mk(id_: str, hp: int, *, dsave: bool) -> Creature:
    c = Creature.create(
        id_=id_, name=id_,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=hp, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    c.uses_death_saves = dsave
    return c


def _enc(pc: Creature, gob: Creature) -> Encounter:
    bf = Battlefield(6, 6)
    bf.place_creature(pc.id, Square(1, 1))
    bf.place_creature(gob.id, Square(4, 4))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 19] + [10] * 30)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc


def test_downed_pc_does_not_end_encounter() -> None:
    pc, gob = _mk("hero", 10, dsave=True), _mk("gob", 7, dsave=False)
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    assert not enc.outcome_decided()  # PC лежит, но спасаем → бой идёт


def test_dead_pc_ends_encounter_as_defeat() -> None:
    pc, gob = _mk("hero", 10, dsave=True), _mk("gob", 7, dsave=False)
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    pc.death_saves = pc.death_saves.apply_save_roll(5)
    pc.death_saves = pc.death_saves.apply_save_roll(5)
    pc.death_saves = pc.death_saves.apply_save_roll(5)  # 3 провала
    assert pc.is_dead
    assert enc.outcome_decided()
    ended: list[EncounterEnded] = []
    enc.event_bus.subscribe(EncounterEnded, ended.append)
    enc.start_turn(); enc.end_turn()
    assert ended and ended[0].winners is Faction.MONSTERS


def test_all_enemies_dead_while_pc_dying_is_party_win() -> None:
    pc, gob = _mk("hero", 10, dsave=True), _mk("gob", 7, dsave=False)
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    gob.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))  # враг мёртв
    assert enc.outcome_decided()
    ended: list[EncounterEnded] = []
    enc.event_bus.subscribe(EncounterEnded, ended.append)
    enc.start_turn(); enc.end_turn()
    assert ended and ended[0].winners is Faction.PARTY
```

- [ ] **Step 2: FAIL** (текущая логика считает по `is_alive`: downed PC = «не жив» →
бой завершится преждевременно как поражение).

- [ ] **Step 3: Реализация**

В `encounter.py` добавить хелпер и переписать обе функции:
```python
    @staticmethod
    def _is_combatant(cr: Creature) -> bool:
        """Существо ещё «в бою»: живо или спасаемо (dying, но не мёртв)."""
        if cr.is_alive:
            return True
        return (
            cr.uses_death_saves
            and cr.death_saves is not None
            and not cr.death_saves.is_dead
        )
```

В `_is_outcome_decided` и `_check_end_condition` заменить условие
`if not cr.is_alive: continue` на `if not self._is_combatant(cr): continue`.
В `survivors` оставить `is_alive` (лежачий PC — не survivor, но и не «убит»;
конец боя при победе PARTY с лежачим PC даст `survivors` без него — это ок,
лог отдельно отметит dying в Q-6/Q-10).

- [ ] **Step 4: PASS** (3 теста).

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/application/engine/encounter.py tests/integration/engine/test_encounter_end_condition_dying.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(engine): Q-5 downed PC не завершает бой; смерть = поражение"
```

---

## Task Q-6: События CreatureStabilized/CreatureDied + EventPrinter

**Files:**
- Modify: `src/dnd/application/dto/engine_event.py`, `src/dnd/interfaces/cli/event_printer.py`
- Modify: `src/dnd/application/engine/encounter.py` (публикация `CreatureDied`)
- Test: `tests/integration/cli/test_event_printer_dying.py`

`DeathSaveRolled` уже добавлен в Q-3. Здесь — `CreatureStabilized`,
`CreatureDied` + handlers в `EventPrinter` (общие для CLI и TUI лога).
Публикация `CreatureDied`: в `_on_downed` (NPC сразу — но NPC-смерть пойдёт в
Q-8 вместе с CORPSE; здесь — публикация при is_dead PC из `_roll_death_save_for`
и при добивании в `take_damage`-пути). Минимально: в `_roll_death_save_for`,
если после броска `actor.is_dead` → опубликовать `CreatureDied(actor_id)`.

- [ ] **Step 1: Падающий тест**

```python
# tests/integration/cli/test_event_printer_dying.py
"""Q-6: EventPrinter рендерит события умирания."""
from __future__ import annotations

from dnd.application.dto.engine_event import (
    CreatureDied, CreatureStabilized, DeathSaveRolled,
)
from dnd.interfaces.cli.event_printer import EventPrinter


def _capture(event) -> str:
    lines: list[str] = []
    printer = EventPrinter(sink=lines.append)
    printer.dispatch_event(event)
    return "\n".join(lines)


def test_death_save_rolled_rendered() -> None:
    out = _capture(DeathSaveRolled(
        actor_id="hero", d20_raw=14, result="success", successes=1, failures=0,
    ))
    assert "hero" in out and "death save" in out.lower() and "14" in out


def test_creature_died_rendered() -> None:
    out = _capture(CreatureDied(actor_id="hero"))
    assert "hero" in out and "died" in out.lower()


def test_creature_stabilized_rendered() -> None:
    out = _capture(CreatureStabilized(actor_id="hero", by="cleric"))
    assert "hero" in out and "cleric" in out
```

- [ ] **Step 2: FAIL** (события/handlers отсутствуют).

- [ ] **Step 3: Реализация**

В `engine_event.py`:
```python
class CreatureStabilized(EngineEvent):
    actor_id: CreatureId
    by: CreatureId


class CreatureDied(EngineEvent):
    actor_id: CreatureId
```
(добавить в `__all__`.)

В `event_printer.py` добавить handlers и записи в `_dispatch`:
```python
    def _on_death_save(self, event: DeathSaveRolled) -> None:
        tag = {"success": "[green]success[/]", "failure": "[red]failure[/]",
               "recovered": "[bold green]RECOVERED (1 HP)[/]"}[event.result]
        self._print(
            f"  🎲 {event.actor_id} death save: {event.d20_raw} → {tag} "
            f"([green]{event.successes}[/]/[red]{event.failures}[/])"
        )

    def _on_died(self, event: CreatureDied) -> None:
        self._print(f"  💀 [bold red]{event.actor_id} died[/]")

    def _on_stabilized(self, event: CreatureStabilized) -> None:
        self._print(f"  ✚ [green]{event.by} stabilizes {event.actor_id}[/]")
```
В `_dispatch`:
```python
        DeathSaveRolled: lambda self, e: self._on_death_save(e),
        CreatureDied: lambda self, e: self._on_died(e),
        CreatureStabilized: lambda self, e: self._on_stabilized(e),
```
(импортировать три события сверху.)

В `encounter.py` `_roll_death_save_for`, в конце:
```python
        if actor.is_dead:
            self._deps.event_bus.publish(CreatureDied(actor_id=actor.id))
```
(импортировать `CreatureDied`.)

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/application/dto/engine_event.py src/dnd/interfaces/cli/event_printer.py src/dnd/application/engine/encounter.py tests/integration/cli/test_event_printer_dying.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(events): Q-6 CreatureDied/Stabilized + рендер death-событий"
```

---

## Task Q-7: StabilizeAction + Ability + StabilizeIntent

**Files:**
- Create: `src/dnd/application/engine/actions/stabilize.py`
- Modify: `src/dnd/application/dto/player_intent.py`, `src/dnd/application/abilities/defaults.py`, `src/dnd/application/engine/game_runner.py`
- Test: `tests/integration/engine/test_stabilize_action.py`

`StabilizeAction` по образцу существующих Action'ов (см. `interact.py`/`attack.py`):
`can_perform_against(actor, params, ctx) -> Allowed | Forbidden`, `execute(...) -> ActionOutcome`.
Цель — союзник в dying (death_saves не None, не dead, не stable), в пределах 5 фт.
Бросок WIS(Медицина) vs DC10 через `ctx.dice_roller`. Успех → `target.death_saves =
target.death_saves.stabilized()` + публикация `CreatureStabilized`. Экономика —
ACTION (использует action актора).

- [ ] **Step 1: Падающий тест**

```python
# tests/integration/engine/test_stabilize_action.py
"""Q-7: StabilizeAction — стабилизация союзника Медициной DC10."""
from __future__ import annotations

from dnd.application.dto.action import Allowed, Forbidden
from dnd.application.dto.engine_event import CreatureStabilized
from dnd.application.engine.actions.stabilize import StabilizeAction, StabilizeParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.damage_type import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _ally(id_: str, wis: int = 14) -> Creature:
    c = Creature.create(
        id_=id_, name=id_,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=wis, cha=10),
        max_hp=12, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    c.uses_death_saves = True
    return c


def _setup(rolls: list[int]):
    healer, downed = _ally("healer"), _ally("downed")
    bf = Battlefield(6, 6)
    bf.place_creature(healer.id, Square(2, 2))
    bf.place_creature(downed.id, Square(2, 3))  # рядом
    # фиктивный враг, чтобы бой не закончился
    enemy = Creature.create(
        id_="enemy", name="enemy",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=7, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf.place_creature(enemy.id, Square(5, 5))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={healer.id: healer, downed.id: downed, enemy.id: enemy},
        factions={healer.id: Faction.PARTY, downed.id: Faction.PARTY,
                  enemy.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    downed.take_damage(DamageInstance(amount=12, type_=DamageType.SLASHING))
    downed.begin_dying()
    # дойти до хода healer'а
    for _ in range(12):
        if enc.current_actor_id == healer.id:
            break
        enc.start_turn(); enc.end_turn()
    ctx = enc.start_turn()
    return enc, healer, downed, ctx


def test_stabilize_success_makes_target_stable() -> None:
    # rolls: 2 инициативы + death saves лежачего по ходам + бросок Медицины=20
    enc, healer, downed, ctx = _setup([20, 19, 18] + [15] * 10 + [20] * 5)
    captured: list[CreatureStabilized] = []
    enc.event_bus.subscribe(CreatureStabilized, captured.append)
    action = StabilizeAction()
    params = StabilizeParams(target_id=downed.id)
    assert isinstance(action.can_perform_against(healer, params, ctx), Allowed)
    out = action.execute(healer, params, ctx)
    assert out.success
    assert downed.death_saves.is_stable
    assert captured and captured[0].actor_id == downed.id


def test_stabilize_healthy_target_forbidden() -> None:
    enc, healer, downed, ctx = _setup([20, 19, 18] + [15] * 10 + [20] * 5)
    downed.heal(5)  # больше не dying
    action = StabilizeAction()
    avail = action.can_perform_against(healer, StabilizeParams(target_id=downed.id), ctx)
    assert isinstance(avail, Forbidden)
```

- [ ] **Step 2: FAIL** (модуль `stabilize` не существует).

- [ ] **Step 3: Реализация**

Создать `src/dnd/application/engine/actions/stabilize.py`. Реализатор сверяет
точные типы `Allowed/Forbidden/ForbiddenReason/ActionOutcome/ActionEconomyCost`
из `dnd/application/dto/action.py` и образец `interact.py`. Скелет:
```python
"""StabilizeAction — стабилизировать союзника в 0 HP (Медицина DC10).

PHB-2024 стр. 27 / навык «Медицина». Проверка WIS(Медицина) vs DC 10.
Успех → DeathSaveState.stabilized(). Не выводит в сознание (нужно лечение).
"""
from __future__ import annotations

from dataclasses import dataclass

from dnd.application.dto.action import (
    ActionEconomyCost, ActionOutcome, Allowed, Forbidden, ForbiddenReason,
)
from dnd.application.dto.engine_event import CreatureStabilized
from dnd.application.dto.ids import CreatureId
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.roll_context import RollContext, RollPurpose

_MEDICINE_DC = 10


@dataclass(frozen=True, slots=True)
class StabilizeParams:
    target_id: CreatureId


class StabilizeAction:
    economy_cost_value = ActionEconomyCost.ACTION

    def can_perform_against(
        self, actor: Creature, params: StabilizeParams, ctx: TurnContext
    ) -> Allowed | Forbidden:
        target = ctx.participants.get(params.target_id)
        if target is None:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS,
                             details="no such target")
        if target.death_saves is None or target.death_saves.is_dead \
                or target.death_saves.is_stable:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS,
                             details="target is not dying")
        ap = ctx.battlefield.position_of(actor.id)
        tp = ctx.battlefield.position_of(target.id)
        if ap.chebyshev_distance_to(tp) > 1:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE,
                             details="target out of reach (5 ft)")
        return Allowed()

    def execute(
        self, actor: Creature, params: StabilizeParams, ctx: TurnContext
    ) -> ActionOutcome:
        avail = self.can_perform_against(actor, params, ctx)
        if isinstance(avail, Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)
        target = ctx.participants[params.target_id]
        wis_mod = actor.abilities.modifier(Ability.WIS)
        expr = DiceExpr.parse(f"d20{wis_mod:+d}")
        roll = ctx.dice_roller.roll(
            expr, RollContext(purpose=RollPurpose.CHECK, actor_id=actor.id,
                              tags=("medicine",)),
        )
        if roll.total >= _MEDICINE_DC:
            target.death_saves = target.death_saves.stabilized()
            ctx.event_bus.publish(
                CreatureStabilized(actor_id=target.id, by=actor.id)
            )
            return ActionOutcome(success=True, consumed=self.economy_cost_value)
        return ActionOutcome(success=True, consumed=self.economy_cost_value)
```
(Имена `RollPurpose.CHECK`, `ForbiddenReason.OUT_OF_RANGE`,
`ap.chebyshev_distance_to`, сигнатуру `ActionOutcome` — реализатор сверяет с
реальными модулями и правит. Если проверка Медицины должна идти через
`modifier_applier`/proficiency — добавить по образцу `SearchAction`.)

В `player_intent.py` добавить в discriminated union:
```python
class StabilizeIntent(BaseModel):
    kind: Literal["stabilize"] = "stabilize"
    target_id: CreatureId
```
(точный паттерн union — по образцу `PickupIntent`; добавить в `PlayerIntent`.)

В `game_runner.py` — ветка диспатча `StabilizeIntent` → `StabilizeAction` (по
образцу `_do_pickup`). В `defaults.py` — ability `stabilize`:
```python
def _stabilize(target_id: CreatureId) -> PlayerIntent:
    return StabilizeIntent(target_id=target_id)
...
    registry.register(Ability(
        id=AbilityId("stabilize"), name="Stabilize", icon="S",
        default_hotkey="s", economy_cost=ActionEconomyCost.ACTION,
        requires_target=True, requires_path=False,
        intent_factory=_stabilize,
    ))
```
И добавить `AbilityId("stabilize")` в `Creature.ability_ids` default tuple.

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/application/engine/actions/stabilize.py src/dnd/application/dto/player_intent.py src/dnd/application/abilities/defaults.py src/dnd/application/engine/game_runner.py src/dnd/domain/entities/creature.py tests/integration/engine/test_stabilize_action.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(engine): Q-7 StabilizeAction + ability + intent"
```

---

## Task Q-8: ObjectKind.CORPSE + спавн трупа при смерти NPC

**Files:**
- Modify: `src/dnd/domain/values/object_kind.py`, `src/dnd/application/engine/encounter.py`
- Modify: `src/dnd/interfaces/tui/widgets/map_widget.py` (глиф CORPSE на клетке без живых)
- Test: `tests/integration/engine/test_corpse_loot.py`

Решение (минимизация регрессий): мёртвое существо **остаётся на сетке** (как
этап N — `%` через is_alive-callback). При смерти NPC дополнительно кладётся
`InteractableObject(kind=CORPSE)` на ту же клетку — контейнер лута. Это не
меняет stage-N рендеринг и не ломает его тесты. CORPSE-объект рисуется как `%`
**только если на клетке нет ни одного существа** (на случай, если существо
позже уберут) — иначе невидим (priority у существа).

Спавн: в `_on_downed`, ветка NPC (не uses_death_saves) при `target.is_at_zero_hp`:
если у трупа ещё нет CORPSE-объекта — создать. Также при смерти PC (is_dead) можно
спавнить CORPSE — но PC обычно один; реализуем для NPC, PC-ветку оставляем
опциональной (см. Q-9 тест охватывает NPC).

- [ ] **Step 1: Падающий тест**

```python
# tests/integration/engine/test_corpse_loot.py
"""Q-8/Q-9: при смерти NPC спавнится CORPSE с лутом; лут через Pickup."""
from __future__ import annotations

from dnd.application.dto.engine_event import AttackResolved
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.inventory import Inventory
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.damage_type import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _gold() -> Item:
    return Item(id=ItemId("gold"), name="Gold", kind=ItemKind.MISC,
                weight_lb=0.02, stackable=True)


def test_npc_death_spawns_corpse_with_loot() -> None:
    pc = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    pc.uses_death_saves = True
    inv = Inventory()
    inv.add(_gold(), 15)
    gob = Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD,
        inventory=inv,
    )
    bf = Battlefield(6, 6)
    bf.place_creature(pc.id, Square(1, 1))
    bf.place_creature(gob.id, Square(3, 3))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 19] + [10] * 20)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    gob.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    enc.event_bus.publish(AttackResolved(
        attacker_id=pc.id, target_id=gob.id, attack_roll_id="r",
        hit=True, is_critical=False, downed=True,
    ))
    corpses = bf.objects_at(Square(3, 3))
    assert any(o.kind == ObjectKind.CORPSE for o in corpses)
    corpse = next(o for o in corpses if o.kind == ObjectKind.CORPSE)
    assert corpse.state.get("contents") == [{"item_id": "gold", "qty": 15}]
    assert corpse.state.get("open") is False  # надо открыть Interact'ом
```

- [ ] **Step 2: FAIL** (`ObjectKind.CORPSE` нет; труп не спавнится).

- [ ] **Step 3: Реализация**

`object_kind.py`: добавить `CORPSE = "corpse"`.

`encounter.py`: импортировать `InteractableObject`, `ObjectKind`, `ObjectId`,
`dump_loot_entries`. В `_on_downed`, ветка NPC:
```python
        elif not target.uses_death_saves and target.is_at_zero_hp:
            self._spawn_corpse(target)
```
Метод:
```python
    def _spawn_corpse(self, dead: Creature) -> None:
        """Положить CORPSE-объект с инвентарём покойного NPC для лута (Q-8)."""
        corpse_id = ObjectId(f"corpse-{dead.id}")
        try:
            self._deps.battlefield.object_at(corpse_id)
            return  # уже есть
        except KeyError:
            pass
        pos = self._deps.battlefield.position_of(dead.id)
        contents = dump_loot_entries(dead.inventory.stacks)
        self._deps.battlefield.place_object(InteractableObject(
            id=corpse_id, kind=ObjectKind.CORPSE, pos=pos,
            state={"open": False, "locked": False, "hp": 1, "ac": 5,
                   "contents": contents},
        ))
```
(сверить: `object_at` кидает KeyError при отсутствии — см. battlefield.py:190;
`dump_loot_entries` принимает `inventory.stacks` — сверить тип.)

`map_widget.py`: в `_cell_glyph`, если на клетке нет occupants (или все мертвы и
нет dead-creature) и есть объект CORPSE — рисовать `%` red dim. Реализатор
встраивает в существующую ветку рендера объектов (CHEST/DOOR), не ломая `%`
от мёртвого существа (приоритет существа сохраняется).

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/domain/values/object_kind.py src/dnd/application/engine/encounter.py src/dnd/interfaces/tui/widgets/map_widget.py tests/integration/engine/test_corpse_loot.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(engine): Q-8 CORPSE-объект с лутом при смерти NPC"
```

---

## Task Q-9: Лут трупа через Interact+Pickup (smoke)

**Files:**
- Test: `tests/integration/engine/test_corpse_loot.py` (дополнить)
- При необходимости — мелкая правка `pickup.py`/`interact.py`, если CORPSE
  не проходит существующие проверки (ожидается, что проходит — это просто
  InteractableObject с `open`/`locked`/`contents`).

`PickupAction` уже работает с любым открытым InteractableObject. `InteractAction`
(OPEN) открывает любой объект с `state["open"]`. Цель Q-9 — доказать, что лут
трупа работает тем же путём, что и сундук (никакого нового кода в идеале).

- [ ] **Step 1: Падающий/проверочный тест**

```python
def test_loot_corpse_via_interact_then_pickup() -> None:
    from dnd.application.dto.action import Allowed
    from dnd.application.engine.actions.interact import (
        InteractAction, InteractKind, InteractParams,
    )
    from dnd.application.engine.actions.pickup import PickupAction, PickupParams
    from dnd.domain.values.item import Item, ItemId, ItemKind

    class _Repo:
        _m = {ItemId("gold"): Item(id=ItemId("gold"), name="Gold",
              kind=ItemKind.MISC, weight_lb=0.02, stackable=True)}
        def list_ids(self): return tuple(self._m)
        def load(self, i): return self._m[i]
        def contains(self, i): return i in self._m

    pc = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    pc.uses_death_saves = True
    inv = Inventory(); inv.add(_gold(), 15)
    gob = Creature.create(
        id_="gob", name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=LONGSWORD, inventory=inv,
    )
    bf = Battlefield(6, 6)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(gob.id, Square(2, 3))  # рядом
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 19] + [10] * 20)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    gob.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    enc.event_bus.publish(AttackResolved(
        attacker_id=pc.id, target_id=gob.id, attack_roll_id="r",
        hit=True, is_critical=False, downed=True))
    # дойти до хода PC
    for _ in range(10):
        if enc.current_actor_id == pc.id:
            break
        enc.start_turn(); enc.end_turn()
    ctx = enc.start_turn()
    from dnd.application.dto.ids import ObjectId
    corpse_id = ObjectId("corpse-gob")
    # 1) открыть
    InteractAction().execute(pc, InteractParams(
        target_object_id=corpse_id, interact_kind=InteractKind.OPEN), ctx)
    # 2) забрать
    out = PickupAction(_Repo()).execute(pc, PickupParams(
        target_object_id=corpse_id, item_id=ItemId("gold")), ctx)
    assert out.success
    assert pc.inventory.find_by_id(ItemId("gold")).qty == 15
```
(Сигнатуры `InteractParams`/`InteractKind`/`PickupParams` — сверить с
реальными модулями; реализатор адаптирует.)

- [ ] **Step 2: Запустить.** Если упадёт — диагностировать (скорее всего из-за
`use_object_interaction` экономики: открыть и лутать в один ход — оба free
interaction; тест может потребовать двух ходов или прямого вызова. Реализатор
решает по факту, без хаков: либо тест ставит `corpse.state["open"]=True` напрямую
для проверки именно Pickup, либо расходует две клетки экономики корректно).

- [ ] **Step 3: Минимальные правки** (только если тест выявил реальный баг в
переиспользовании; в идеале — 0 строк production-кода).

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add tests/integration/engine/test_corpse_loot.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "test(engine): Q-9 лут трупа через Interact+Pickup"
```

---

## Task Q-10: TUI death-save overlay (пипсы в StatusWidget)

**Files:**
- Modify: `src/dnd/interfaces/tui/widgets/status_widget.py`
- Test: `tests/integration/tui/test_death_save_overlay.py`

Когда у отображаемого существа `death_saves is not None` — добавить строку
`Death saves: ●●○ / ○○○` (зелёные успехи / красные провалы). Пипс ● для
накопленных, ○ для оставшихся (из 3).

- [ ] **Step 1: Падающий тест**

```python
# tests/integration/tui/test_death_save_overlay.py
"""Q-10: StatusWidget показывает пипсы спасбросков."""
from __future__ import annotations

import pytest

pytest.importorskip("textual")

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.death_save_state import DeathSaveState
from dnd.interfaces.tui.widgets.status_widget import render_status  # pure helper


def _pc() -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=12, speed_ft=30,
    )
    c.uses_death_saves = True
    return c


def test_status_shows_death_save_pips_when_dying() -> None:
    c = _pc()
    c.hit_points = c.hit_points.take_damage(10)
    c.death_saves = DeathSaveState(successes=2, failures=1)
    text = render_status(c)
    assert "Death saves" in text
    assert text.count("●") == 3  # 2 success + 1 failure накоплено


def test_status_no_pips_when_healthy() -> None:
    c = _pc()
    text = render_status(c)
    assert "Death saves" not in text
```
(Если в `status_widget.py` нет чистого `render_status(creature) -> str`, реализатор
извлекает рендер в такой helper — по образцу `map_widget._cell_glyph` /
`initiative_widget`. Это улучшает тестируемость, в духе репо.)

- [ ] **Step 2: FAIL.**

- [ ] **Step 3: Реализация** — добавить строку пипсов в рендер статуса:
```python
    if creature.death_saves is not None:
        ds = creature.death_saves
        succ = "[green]" + "●" * ds.successes + "[/]" + "○" * (3 - ds.successes)
        fail = "[red]" + "●" * ds.failures + "[/]" + "○" * (3 - ds.failures)
        lines.append(f"Death saves: {succ} / {fail}")
```

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add src/dnd/interfaces/tui/widgets/status_widget.py tests/integration/tui/test_death_save_overlay.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(tui): Q-10 death-save пипсы в StatusWidget"
```

---

## Task Q-11: Документация — DYING.md + ROADMAP + scenario-флаг

**Files:**
- Create: `docs/DYING.md`
- Modify: `docs/ROADMAP.md`, `docs/TUI.md`
- Modify: `src/dnd/application/engine/scenario_builder.py` (проставлять
  `uses_death_saves=True` для PARTY-существ из сценария) + тест.

PC из сценария должны получать `uses_death_saves=True`, иначе вся механика Q
не активируется в реальной игре. Где строятся существа PARTY — там выставить флаг.

- [ ] **Step 1: Падающий тест**

```python
# tests/integration/engine/test_scenario_death_saves.py
"""Q-11: PARTY-существа сценария получают uses_death_saves=True."""
from __future__ import annotations

from pathlib import Path

from dnd.application.engine.scenario_builder import build_encounter_from_scenario
from dnd.composition import build_default_runtime_services
from dnd.domain.values.faction import Faction
from dnd.infrastructure.content.yaml_repository import YamlContentRepository
# ... map/sprite repos как в cli/app.py ...


def test_party_creatures_use_death_saves() -> None:
    repo = YamlContentRepository(Path("data/content"))
    scenario = repo.scenario_by_id("mvp_skirmish")
    # построить encounter (с map/sprite repos по образцу cli/app.py)
    enc = build_encounter_from_scenario(scenario, content=repo,
                                        services=build_default_runtime_services())
    for cid, cr in enc._participants.items():
        if enc._factions[cid] is Faction.PARTY:
            assert cr.uses_death_saves, f"{cid} должен иметь death saves"
```
(Реализатор адаптирует под точную сигнатуру `build_encounter_from_scenario`,
возможно с map_repository/sprite_registry; если PARTY определяется внутри
билдера — проверить там.)

- [ ] **Step 2: FAIL** (флаг не выставляется).

- [ ] **Step 3: Реализация** — в месте создания PARTY-существ в
`scenario_builder.py` проставить `creature.uses_death_saves = True` (или через
фабрику). NPC/MONSTERS — оставить False.

- [ ] **Step 4: PASS.**

- [ ] **Step 5: Документация**

Создать `docs/DYING.md` (на русском): модель dying/death saves/stabilize/CORPSE,
инварианты (§6 спека), как помечается PC (`uses_death_saves`), правила бросков.
В `docs/ROADMAP.md` — пометить этап Q как ✅ с кратким описанием. В `docs/TUI.md` —
описать death-save overlay (пипсы) и поведение CORPSE-лута (`i`/`l`).

- [ ] **Step 6: Sweep + commit**

```bash
python3 -m pytest -q && mypy src/ && ruff check
git add docs/DYING.md docs/ROADMAP.md docs/TUI.md src/dnd/application/engine/scenario_builder.py tests/integration/engine/test_scenario_death_saves.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "docs+content: Q-11 DYING.md + PARTY uses_death_saves + roadmap"
```

---

## Финальный аудит (после Q-1..Q-11)

Независимый аудит этапа Q (general-purpose subagent), как после O: проверить
инварианты §6 спека, отсутствие регрессий, корректность правил PHB-2024,
полный sweep. Применить CRITICAL/MAJOR до закрытия этапа.

---

## Self-Review (выполнено при написании плана)

**Spec coverage:**
- §3.1 флаг PC/NPC → Q-1. §3.2 CORPSE-лут → Q-8/Q-9. §3.3 end-condition → Q-5.
- §4.1 Creature методы → Q-1. §4.2 engine wiring → Q-2/Q-3/Q-4. §4.3 end-condition
  → Q-5. §4.4 StabilizeAction → Q-7. §4.5 corpse → Q-8/Q-9. §4.6 события → Q-3/Q-6.
  §4.7 UI → Q-6 (лог) + Q-10 (overlay). §7 тесты → в каждом task'е. §8 monster AI
  → **частично**: добивание лежачего работает (Q-4 авто-крит), но «предпочтение
  живых целей» — отдельной правки SimpleMonsterAI в плане нет. **Добавлено
  замечание:** если playtest покажет, что AI бьёт лежачего вместо живого —
  внести в финальный аудит как доработку; для DoD не блокирует (одиночный PC).
- §10 DoD → покрыт Q-1..Q-11 + scenario-флаг (Q-11) + docs (Q-11).

**Placeholder scan:** код-шаги содержат конкретный код; несколько мест помечены
«реализатор сверяет точную сигнатуру X» — это намеренно (точные имена enum'ов
`RollPurpose`/`ForbiddenReason` и метод дистанции `Square` надо взять из кода,
а не угадывать), с указанием конкретного файла-источника. Не плейсхолдеры задач.

**Type consistency:** `DeathSaveOutcome.result` ∈ {success,failure,recovered} —
совпадает с `DeathSaveRolled.result`. `uses_death_saves`/`death_saves` —
единообразны во всех task'ах. `ObjectKind.CORPSE`, `corpse-{id}`,
`state.contents` (canonical `[{"item_id","qty"}]`) — согласованы с loot_helpers.
