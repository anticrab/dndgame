# T3 — боевые условия Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заставить состояния влиять на броски по PHB-2024: чинить осиротевший `provides_modifiers` (self-помехи), добавить cross-creature преимущество/помеху, авто-крит по обездвиженному в упор, авто-провал STR/DEX-спасбросков и преимущество на DEX-спасброски в Dodge.

**Architecture:** `ConditionService` становится мостом «данные состояния → бросок»: `collect_modifiers` (self-модификаторы на момент броска), `incoming_attack_adjustment` (cross-creature adv/disadv из декларативных полей состояний цели), `auto_fails_save` (авто-провал). Боевые правила — декларативные поля на самих состояниях (domain), не switch. `attack.py`/`saving_throw.py` спрашивают сервис; конкретных состояний не знают.

**Tech Stack:** Python 3.12, frozen dataclasses (domain VO), pydantic v2, pytest, mypy strict, ruff. Гексагональная архитектура (guard `tests/unit/test_layering.py`). Коммиты: `Maxim Lokotkov` / `anticrab@users.noreply.github.com`.

---

## Карта файлов

| Файл | Ответственность | Изменение |
|------|-----------------|-----------|
| `src/dnd/domain/conditions/base.py` | Protocol `Condition` + боевые поля (документация контракта) | Modify |
| `src/dnd/domain/conditions/builtin.py` | значения боевых полей у Paralyzed/Unconscious/Stunned/Restrained/Prone | Modify |
| `src/dnd/application/engine/condition_service.py` | `collect_modifiers` / `incoming_attack_adjustment` / `auto_fails_save` | Modify |
| `src/dnd/application/engine/actions/attack.py` | self-модификаторы + cross-creature adv/disadv + авто-крит | Modify |
| `src/dnd/application/engine/saving_throw.py` | self-модификаторы + авто-провал + Dodge DEX-advantage | Modify |
| `src/dnd/application/engine/effects/ongoing_effect_tracker.py` | прокинуть `condition_service` (авто-провал в повторных спасбросках) | Modify |
| `src/dnd/interfaces/cli/app.py` | передать `condition_service` в трекер | Modify |
| `docs/CONDITIONS.md` (или раздел в существующем), `docs/MODIFIERS.md`, `docs/ROADMAP.md` | документация T3 | Modify |

**Факт о builtin-состояниях:** это frozen `@dataclass(slots=True)`. Новые поля
добавляем как поля dataclass с дефолтами. У состояний, которым поле не нужно,
дефолт «нет эффекта» (через значение по умолчанию в каждом классе ИЛИ через
доступ `getattr(cond, "имя", дефолт)` в сервисе — см. ниже выбранный путь).

**Выбранный путь типобезопасности:** поля объявляем в `Condition`-протоколе как
атрибуты, и в КАЖДОМ builtin-dataclass прописываем их с дефолтом. Состояния без
эффекта получают `grants_advantage_to_attackers: bool = False` и т.д. Это явно и
проходит mypy (Protocol-атрибуты + конкретные поля). Сервис обращается к полям
напрямую (`cond.grants_advantage_to_attackers`), без `getattr`.

---

## Task T3-1: `collect_modifiers` + проводка self-модификаторов (фикс орфана)

**Files:**
- Modify: `src/dnd/application/engine/condition_service.py`
- Modify: `src/dnd/application/engine/actions/attack.py`
- Modify: `src/dnd/application/engine/saving_throw.py`
- Test: `tests/unit/application/test_condition_modifiers.py` (Create)

- [ ] **Step 1: Падающий тест `collect_modifiers`**

Create `tests/unit/application/test_condition_modifiers.py`:

```python
"""ConditionService.collect_modifiers — self-модификаторы активных состояний (T3)."""
from __future__ import annotations

from dnd.application.engine.condition_service import ConditionService
from dnd.domain.conditions.builtin import POISONED, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.modifiers import DisadvantageEffect, ModifierTargetKind


def _svc() -> ConditionService:
    reg = ConditionRegistry()
    register_default_conditions(reg)
    return ConditionService(reg)


def _creature() -> Creature:
    return Creature.create(
        id_=CreatureId("c"), name="c",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )


def test_poisoned_gives_attack_disadvantage_modifier() -> None:
    svc = _svc()
    c = _creature()
    c.apply_condition(POISONED)
    mods = svc.collect_modifiers(c, ModifierTargetKind.ATTACK_ROLL)
    assert len(mods) == 1
    assert isinstance(mods[0].effect, DisadvantageEffect)


def test_no_conditions_no_modifiers() -> None:
    svc = _svc()
    assert svc.collect_modifiers(_creature(), ModifierTargetKind.ATTACK_ROLL) == []
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_condition_modifiers.py -q`
Expected: FAIL (`AttributeError: 'ConditionService' object has no attribute 'collect_modifiers'`).

- [ ] **Step 3: Реализовать `collect_modifiers`**

В `src/dnd/application/engine/condition_service.py`. Дополнить импорты в TYPE_CHECKING:
```python
if TYPE_CHECKING:
    from dnd.domain.values.modifiers import Modifier, ModifierTargetKind
```
(Проверить, что блок TYPE_CHECKING есть; `Creature` уже импортирован для сигнатур —
если нет, добавить туда же `from dnd.domain.entities.creature import Creature`.)

Добавить метод в класс `ConditionService`:
```python
    def collect_modifiers(
        self, creature: Creature, target_kind: ModifierTargetKind,
    ) -> list[Modifier]:
        """Self-модификаторы от активных состояний носителя для данного класса
        броска (T3 — активирует осиротевший provides_modifiers). Состояние без
        модификаторов этого класса просто ничего не добавляет."""
        out: list[Modifier] = []
        for cid in creature.conditions:
            if not self._registry.has(cid):
                continue
            for m in self._registry.get(cid).provides_modifiers(creature.id):
                if m.target_kind is target_kind:
                    out.append(m)
        return out
```

- [ ] **Step 4: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/application/test_condition_modifiers.py -q`
Expected: PASS (2 теста).

- [ ] **Step 5: Проводка в attack.py (ATTACK_ROLL)**

В `src/dnd/application/engine/actions/attack.py`, в `execute`, заменить сбор
atk_mods:
```python
        atk_mods = ctx.modifier_applier.collect(
            owner_id=actor.id,
            target_kind=ModifierTargetKind.ATTACK_ROLL,
        )
        atk_mods = atk_mods + ctx.condition_service.collect_modifiers(
            actor, ModifierTargetKind.ATTACK_ROLL
        )
        atk_adj = ctx.modifier_applier.to_roll_adjustments(atk_mods)
```
(`to_roll_adjustments` принимает Sequence[Modifier] — конкатенированный список
ок; правило adv+disadv=обычный применится поверх всего.)

- [ ] **Step 6: Проводка в saving_throw.py (SAVING_THROW)**

В `src/dnd/application/engine/saving_throw.py`. Сейчас `roll_saving_throw_raw`
собирает только `modifier_applier.collect(...)`. Добавить опциональный
`condition_service` и подмешать его модификаторы. Сигнатура:
```python
def roll_saving_throw_raw(
    actor: Creature,
    ability: Ability,
    *,
    dc: int,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    condition_service: ConditionService | None = None,
    tags: tuple[str, ...] = ("saving_throw",),
) -> bool:
```
Тело — собрать модификаторы:
```python
    mods = list(modifier_applier.collect(
        owner_id=actor.id, target_kind=ModifierTargetKind.SAVING_THROW
    ))
    if condition_service is not None:
        mods += condition_service.collect_modifiers(
            actor, ModifierTargetKind.SAVING_THROW
        )
    adj = modifier_applier.to_roll_adjustments(mods)
```
(Заменить прежнюю строку, где `adj` собирался напрямую через collect.)
`roll_saving_throw` (ctx-вариант) передаёт `condition_service=ctx.condition_service`:
```python
    return roll_saving_throw_raw(
        actor, ability, dc=dc,
        dice_roller=ctx.dice_roller, modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service, tags=tags,
    )
```
Импорт `ConditionService` в TYPE_CHECKING `saving_throw.py`:
```python
    from dnd.application.engine.condition_service import ConditionService
```

- [ ] **Step 7: Прогон + перепроверка регрессии**

Run: `python3 -m pytest -q`
Expected: возможны падения старых тестов, где Poisoned/Frightened/Prone-актёр
теперь РЕАЛЬНО получил помеху (раньше эффект терялся). Для каждого падения:
прочитать тест, понять — ожидание было основано на «нет помехи». Если так —
обновить ожидание (помеха корректна по PHB) или скорректировать RNG-бюджет
(advantage/disadvantage меняет число потребляемых d20). НЕ ослаблять проверки
по сути — приводить к правильному поведению.

- [ ] **Step 8: mypy + ruff + коммит**

Run: `python3 -m mypy src && python3 -m ruff check src tests && python3 -m pytest -q`
Expected: зелёно.

```bash
git add src/dnd/application/engine/condition_service.py src/dnd/application/engine/actions/attack.py src/dnd/application/engine/saving_throw.py tests/unit/application/test_condition_modifiers.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t3): ConditionService.collect_modifiers + проводка self-помех состояний (фикс provides_modifiers)"
```

---

## Task T3-2: боевые поля состояний + cross-creature advantage/disadvantage

**Files:**
- Modify: `src/dnd/domain/conditions/base.py`
- Modify: `src/dnd/domain/conditions/builtin.py`
- Modify: `src/dnd/application/engine/condition_service.py`
- Modify: `src/dnd/application/engine/actions/attack.py`
- Test: `tests/unit/application/test_incoming_attack_adjustment.py` (Create), `tests/integration/engine/test_attack_conditions.py` (Create)

- [ ] **Step 1: Падающий тест сервиса**

Create `tests/unit/application/test_incoming_attack_adjustment.py`:

```python
"""ConditionService.incoming_attack_adjustment — cross-creature adv/disadv (T3)."""
from __future__ import annotations

from dnd.application.engine.condition_service import ConditionService
from dnd.domain.conditions.builtin import PARALYZED, PRONE, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.attack_kind import AttackKind
from dnd.domain.values.ids import CreatureId


def _svc() -> ConditionService:
    reg = ConditionRegistry()
    register_default_conditions(reg)
    return ConditionService(reg)


def _c() -> Creature:
    return Creature.create(
        id_=CreatureId("t"), name="t",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )


def test_paralyzed_grants_advantage_any_kind() -> None:
    svc = _svc()
    t = _c()
    t.apply_condition(PARALYZED)
    assert svc.incoming_attack_adjustment(
        t, distance_ft=30, attack_kind=AttackKind.RANGED
    ) == (True, False)


def test_prone_melee_point_blank_advantage() -> None:
    svc = _svc()
    t = _c()
    t.apply_condition(PRONE)
    assert svc.incoming_attack_adjustment(
        t, distance_ft=5, attack_kind=AttackKind.MELEE
    ) == (True, False)


def test_prone_ranged_disadvantage() -> None:
    svc = _svc()
    t = _c()
    t.apply_condition(PRONE)
    assert svc.incoming_attack_adjustment(
        t, distance_ft=30, attack_kind=AttackKind.RANGED
    ) == (False, True)


def test_no_condition_no_adjustment() -> None:
    assert _svc().incoming_attack_adjustment(
        _c(), distance_ft=5, attack_kind=AttackKind.MELEE
    ) == (False, False)
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_incoming_attack_adjustment.py -q`
Expected: FAIL (`AttributeError: incoming_attack_adjustment`).

- [ ] **Step 3: Боевые поля в протоколе**

В `src/dnd/domain/conditions/base.py`, в `class Condition(Protocol)` добавить
(после `implies`):
```python
    grants_advantage_to_attackers: bool
    """T3: атаки по носителю — с преимуществом (Paralyzed/Unconscious/Stunned/
    Restrained). PHB-2024 стр. 367."""

    melee_advantage_ranged_disadvantage: bool
    """T3: Prone — атака в упор (melee ≤5 фт) с преимуществом, иначе с помехой."""

    auto_fail_saves: frozenset[Ability]
    """T3: спасброски этих характеристик авто-проваливаются (Paralyzed/
    Unconscious/Stunned → STR, DEX)."""
```
Импорт `Ability` в `base.py`:
```python
from dnd.domain.values.ability import Ability
```

- [ ] **Step 4: Значения полей в builtin.py**

В `src/dnd/domain/conditions/builtin.py` — добавить поля в КАЖДЫЙ builtin-dataclass
условия. Импорт `Ability`:
```python
from dnd.domain.values.ability import Ability
```
Для состояний **с эффектом** (значения):
- `ParalyzedCondition`, `UnconsciousCondition`, `StunnedCondition`:
  ```python
      grants_advantage_to_attackers: bool = True
      melee_advantage_ranged_disadvantage: bool = False
      auto_fail_saves: frozenset[Ability] = field(
          default_factory=lambda: frozenset({Ability.STR, Ability.DEX})
      )
  ```
- `RestrainedCondition` (если есть в builtin; если нет — пропустить):
  `grants_advantage_to_attackers: bool = True`, остальные дефолты.
- `ProneCondition`:
  ```python
      grants_advantage_to_attackers: bool = False
      melee_advantage_ranged_disadvantage: bool = True
      auto_fail_saves: frozenset[Ability] = frozenset()
  ```
Для **остальных** условий (Incapacitated, Poisoned, Frightened, Invisible, …) —
добавить три поля с дефолтами «нет эффекта»:
```python
    grants_advantage_to_attackers: bool = False
    melee_advantage_ranged_disadvantage: bool = False
    auto_fail_saves: frozenset[Ability] = frozenset()
```
> Важно: в frozen dataclass поля с дефолтом-`frozenset()` — неизменяемый литерал,
> можно как прямое значение (не нужен default_factory для immutable). Для
> `{STR,DEX}` тоже допустимо прямое `frozenset({Ability.STR, Ability.DEX})` как
> дефолт (иммутабельный) — это проще, чем default_factory. Используем прямые
> значения.

Перепроверить, что `id`/`implies` остаются с прежними дефолтами и порядок полей
не ломает существующие конструкторы (поля с дефолтами идут после полей без
дефолтов; `id` и `implies` уже с дефолтами — добавляемые тоже с дефолтами, ок).

- [ ] **Step 5: `incoming_attack_adjustment` в сервисе**

В `condition_service.py` добавить метод. Импорт `AttackKind` в TYPE_CHECKING:
```python
    from dnd.domain.values.attack_kind import AttackKind
```
```python
    def incoming_attack_adjustment(
        self, target: Creature, *, distance_ft: int, attack_kind: AttackKind,
    ) -> tuple[bool, bool]:
        """(advantage, disadvantage) для атакующего по target из боевых данных
        состояний цели. Prone: melee≤5 → adv, иначе disadv."""
        from dnd.domain.values.attack_kind import AttackKind as _AK
        advantage = False
        disadvantage = False
        for cid in target.conditions:
            if not self._registry.has(cid):
                continue
            cond = self._registry.get(cid)
            if cond.grants_advantage_to_attackers:
                advantage = True
            if cond.melee_advantage_ranged_disadvantage:
                if attack_kind is _AK.MELEE and distance_ft <= 5:
                    advantage = True
                else:
                    disadvantage = True
        return advantage, disadvantage
```

- [ ] **Step 6: Запустить тест сервиса — зелёно**

Run: `python3 -m pytest tests/unit/application/test_incoming_attack_adjustment.py -q`
Expected: PASS (4 теста).

- [ ] **Step 7: Cross-creature в attack.py + интеграционный тест**

Create `tests/integration/engine/test_attack_conditions.py`:

```python
"""Атака учитывает состояния цели/атакующего (T3)."""
from __future__ import annotations

from dnd.application.dto.action import Allowed
from dnd.application.dto.engine_event import AttackRolled, EngineEvent
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED, POISONED
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.application.engine.encounter import Encounter
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _enc(rolls: list[int]) -> tuple[Encounter, Creature, Creature, list[EngineEvent]]:
    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("hero"), name="hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=30, armor_class=13, speed_ft=30,
    )
    bf.place_creature(hero.id, Square(1, 2))
    bf.place_creature(gob.id, Square(2, 2))
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.start()
    return enc, hero, gob, captured


def test_attack_against_paralyzed_has_advantage() -> None:
    # init hero, init gob, затем атака (advantage → 2 d20), затем урон.
    enc, hero, gob, captured = _enc([18, 1, 5, 19, 7])
    gob.apply_condition(PARALYZED)
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    assert actor.id == hero.id
    params = weapon_attack_params(actor, gob.id)
    AttackAction().execute(actor, params, ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.advantage is True


def test_poisoned_attacker_has_disadvantage() -> None:
    enc, hero, gob, captured = _enc([18, 1, 19, 5, 7])
    hero.apply_condition(POISONED)
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    params = weapon_attack_params(actor, gob.id)
    AttackAction().execute(actor, params, ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.disadvantage is True
```

> RNG-бюджет (init×2, затем d20 атаки; при advantage/disadvantage DiceRoller
> потребляет 2 d20). Подогнать список `rolls`, если порядок инициативы иной —
> важно лишь, чтобы первым ходил hero и атака состоялась; проверка — на флаг
> advantage/disadvantage в AttackRolled, не на исход.

В `attack.py` после вычисления `dodge_penalty`/`help_bonus` добавить:
```python
        tgt_adv, tgt_disadv = ctx.condition_service.incoming_attack_adjustment(
            target, distance_ft=distance_ft, attack_kind=params.kind
        )
```
и в `RollContext`:
```python
            advantage=atk_adj.advantage or help_bonus or tgt_adv,
            disadvantage=(
                atk_adj.disadvantage or long_range_penalty or dodge_penalty
                or tgt_disadv
            ),
```

- [ ] **Step 8: Запустить — зелёно + регрессия**

Run: `python3 -m pytest tests/integration/engine/test_attack_conditions.py tests/unit/application/test_incoming_attack_adjustment.py -q && python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: всё зелёно (перепроверить старые attack-тесты — Prone-цель теперь даёт
adv/disadv по дистанции).

- [ ] **Step 9: Коммит**

```bash
git add src/dnd/domain/conditions/base.py src/dnd/domain/conditions/builtin.py src/dnd/application/engine/condition_service.py src/dnd/application/engine/actions/attack.py tests/unit/application/test_incoming_attack_adjustment.py tests/integration/engine/test_attack_conditions.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t3): декларативные боевые поля состояний + cross-creature advantage/disadvantage"
```

---

## Task T3-3: авто-крит по Paralyzed/Unconscious в упор

**Files:**
- Modify: `src/dnd/application/engine/actions/attack.py`
- Test: `tests/integration/engine/test_attack_conditions.py` (дописать)

- [ ] **Step 1: Падающий тест**

Дописать в `tests/integration/engine/test_attack_conditions.py`:

```python
def test_melee_point_blank_vs_paralyzed_is_auto_crit() -> None:
    # d20 атаки = 10 (не нат-20), но цель Paralyzed в упор → крит.
    # advantage от Paralyzed → 2 d20 (10,10), затем 2× кости урона.
    enc, hero, gob, captured = _enc([18, 1, 10, 10, 4, 4])
    gob.apply_condition(PARALYZED)
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    from dnd.application.dto.engine_event import AttackRolled
    AttackAction().execute(actor, weapon_attack_params(actor, gob.id), ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.hit is True
    assert ar.is_critical_hit is True
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/integration/engine/test_attack_conditions.py::test_melee_point_blank_vs_paralyzed_is_auto_crit -q`
Expected: FAIL (крит не выставлен — текущее условие только `is_at_zero_hp`).

- [ ] **Step 3: Расширить условие авто-крита**

В `attack.py` заменить блок Q-4:
```python
        # Q-4 / T3: попадание в упор (≤5 фт, melee) по беспомощной цели —
        # авто-крит (PHB-2024 стр. 27, 367). Беспомощность: 0 HP (умирает)
        # ИЛИ Paralyzed / Unconscious (даже при полном HP, напр. Hold Person).
        melee_point_blank = params.kind is AttackKind.MELEE and distance_ft <= 5
        helpless = (
            target.is_at_zero_hp
            or target.has_condition(PARALYZED)
            or target.has_condition(UNCONSCIOUS)
        )
        if hit and melee_point_blank and helpless:
            is_crit = True
```
(`PARALYZED`/`UNCONSCIOUS` уже импортированы в attack.py.)

- [ ] **Step 4: Запустить — зелёно**

Run: `python3 -m pytest tests/integration/engine/test_attack_conditions.py -q && python3 -m pytest -q`
Expected: PASS, регрессия зелёная.

- [ ] **Step 5: mypy + ruff + коммит**

Run: `python3 -m mypy src && python3 -m ruff check src tests`

```bash
git add src/dnd/application/engine/actions/attack.py tests/integration/engine/test_attack_conditions.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t3): авто-крит по Paralyzed/Unconscious в упор (не только по 0 HP)"
```

---

## Task T3-4: авто-провал STR/DEX-спасбросков + Dodge DEX-advantage

**Files:**
- Modify: `src/dnd/application/engine/condition_service.py`
- Modify: `src/dnd/application/engine/saving_throw.py`
- Modify: `src/dnd/application/engine/effects/ongoing_effect_tracker.py`
- Modify: `src/dnd/interfaces/cli/app.py`
- Test: `tests/unit/application/test_saving_throw.py` (дописать)

- [ ] **Step 1: Падающий тест `auto_fails_save` + поведение saving_throw**

Дописать в `tests/unit/application/test_saving_throw.py`:

```python
def test_auto_fails_save_paralyzed_dex() -> None:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.domain.conditions.builtin import (
        PARALYZED, register_default_conditions,
    )
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    reg = ConditionRegistry()
    register_default_conditions(reg)
    svc = ConditionService(reg)
    c = Creature.create(
        id_=CreatureId("c"), name="c",
        abilities=AbilityScores.of(str_=10, dex=18, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )
    c.apply_condition(PARALYZED)
    assert svc.auto_fails_save(c, Ability.DEX) is True
    assert svc.auto_fails_save(c, Ability.CON) is False


def test_roll_saving_throw_auto_fails_under_paralyzed() -> None:
    from dnd.application.engine.condition_service import ConditionService
    from dnd.application.engine.saving_throw import roll_saving_throw_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.conditions.builtin import PARALYZED, register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    reg = ConditionRegistry()
    register_default_conditions(reg)
    svc = ConditionService(reg)
    deps, _bus, _ = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=[20]  # даже d20=20 не спасёт
    )
    c = Creature.create(
        id_=CreatureId("c"), name="c",
        abilities=AbilityScores.of(str_=10, dex=18, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )
    c.apply_condition(PARALYZED)
    assert roll_saving_throw_raw(
        c, Ability.DEX, dc=5,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
        condition_service=svc,
    ) is False
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_saving_throw.py -q`
Expected: FAIL (`auto_fails_save` нет; авто-провал не реализован).

- [ ] **Step 3: `auto_fails_save` в сервисе**

В `condition_service.py`. Импорт `Ability` в TYPE_CHECKING:
```python
    from dnd.domain.values.ability import Ability
```
```python
    def auto_fails_save(self, creature: Creature, ability: Ability) -> bool:
        """True, если активное состояние носителя авто-проваливает спасбросок
        этой характеристики (Paralyzed/Unconscious/Stunned → STR, DEX)."""
        for cid in creature.conditions:
            if not self._registry.has(cid):
                continue
            if ability in self._registry.get(cid).auto_fail_saves:
                return True
        return False
```

- [ ] **Step 4: Авто-провал + Dodge-advantage в saving_throw.py**

В `roll_saving_throw_raw` (после сбора `mods`, перед броском) добавить авто-провал
ПЕРВЫМ и Dodge-advantage. Полный фрагмент тела:
```python
    if condition_service is not None and condition_service.auto_fails_save(actor, ability):
        return False  # авто-провал приоритетнее любых преимуществ (PHB-2024 стр. 367)
    mods = list(modifier_applier.collect(
        owner_id=actor.id, target_kind=ModifierTargetKind.SAVING_THROW
    ))
    if condition_service is not None:
        mods += condition_service.collect_modifiers(
            actor, ModifierTargetKind.SAVING_THROW
        )
    adj = modifier_applier.to_roll_adjustments(mods)
    bonus = saving_throw_bonus(actor, ability)
    # Dodge: преимущество на DEX-спасброски (PHB-2024 стр. 22), если стойка
    # активна и существо дееспособно (auto_fails_save для DEX уже отсёк бы
    # Paralyzed/Unconscious выше — сюда попадает только дееспособный dodger).
    dodge_dex_adv = (
        ability is Ability.DEX and "dodging" in actor.combat_stances
    )
    roll = dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.SAVE, actor_id=actor.id,
            advantage=adj.advantage or dodge_dex_adv,
            disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice, tags=tags,
        ),
    )
    return roll.total >= dc
```
Импорт `Ability` для рантайма (не только TYPE_CHECKING — используется
`Ability.DEX`): добавить `from dnd.domain.values.ability import Ability` в
основные импорты `saving_throw.py`.

> Примечание: `saving_throw_bonus` уже импортирована/определена в файле; не
> дублировать. `ModifierTargetKind`, `DiceExpr`, `RollContext`, `RollPurpose`
> уже импортированы (использовались в прежнем теле).

- [ ] **Step 5: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/application/test_saving_throw.py -q`
Expected: PASS.

- [ ] **Step 6: Прокинуть condition_service в OngoingEffectTracker**

В `ongoing_effect_tracker.py`: добавить параметр конструктора и использовать в
повторном спасброске (`_on_turn_ended`):
```python
    def __init__(
        self,
        participants,
        event_bus,
        *,
        dice_roller,
        modifier_applier,
        condition_service=None,
    ) -> None:
        ...
        self._conds = condition_service
```
(Аннотации типов — как у прочих: `ConditionService | None = None` в TYPE_CHECKING.)
В `_on_turn_ended`, в вызов `roll_saving_throw_raw` добавить
`condition_service=self._conds`.

- [ ] **Step 7: Composition — передать condition_service**

В `src/dnd/interfaces/cli/app.py`, в создание `OngoingEffectTracker(...)`
добавить `condition_service=services.condition_service,`.
(Проверить имя: `EncounterRuntimeServices.condition_service` — есть.)

- [ ] **Step 8: Регрессия + mypy + ruff + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: зелёно.

```bash
git add src/dnd/application/engine/condition_service.py src/dnd/application/engine/saving_throw.py src/dnd/application/engine/effects/ongoing_effect_tracker.py src/dnd/interfaces/cli/app.py tests/unit/application/test_saving_throw.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t3): авто-провал STR/DEX-спасбросков под Paralyzed/Unconscious + Dodge DEX-advantage"
```

---

## Task T3-5: e2e + документация

**Files:**
- Create: `tests/e2e/test_combat_conditions_play.py`
- Modify: `docs/CONDITIONS.md` (если нет — создать), `docs/MODIFIERS.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Падающий e2e (Hold Person → advantage + авто-крит союзника)**

Create `tests/e2e/test_combat_conditions_play.py`:

```python
"""E2E T3: парализованная цель — атака союзника с преимуществом и авто-критом."""
from __future__ import annotations

import pytest

from dnd.application.dto.engine_event import AttackRolled, EngineEvent
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


@pytest.mark.e2e
def test_paralyzed_target_attacked_with_advantage_and_autocrit() -> None:
    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("hero"), name="hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    foe = Creature.create(
        id_=CreatureId("foe"), name="foe",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=40, armor_class=14, speed_ft=30,
    )
    foe.apply_condition(PARALYZED)
    bf.place_creature(hero.id, Square(1, 2))
    bf.place_creature(foe.id, Square(2, 2))
    # init hero=18, foe пропустит (парализован); атака advantage → 2 d20 (10,10),
    # урон 2× кости (крит).
    deps, bus, _ = build_scripted_dependencies(
        battlefield=bf, rolls=[18, 1, 10, 10, 5, 5]
    )
    enc = Encounter(
        participants={hero.id: hero, foe.id: foe},
        factions={hero.id: Faction.PARTY, foe.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.start()
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    assert actor.id == hero.id
    AttackAction().execute(actor, weapon_attack_params(actor, foe.id), ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.advantage is True
    assert ar.is_critical_hit is True
```

> RNG-бюджет: init×2, затем d20×2 (advantage), затем кости урона ×2 (крит).
> Подогнать, если инициатива потребляет иначе; проверка — на advantage+crit.

- [ ] **Step 2: Запустить e2e — зелёно**

Run: `python3 -m pytest tests/e2e/test_combat_conditions_play.py -q`
Expected: PASS (подогнать RNG при необходимости).

- [ ] **Step 3: Документация**

`docs/CONDITIONS.md` — создать (или дополнить существующий раздел про состояния):
описать боевые поля (`grants_advantage_to_attackers`,
`melee_advantage_ranged_disadvantage`, `auto_fail_saves`), как `ConditionService`
их применяет (`collect_modifiers` / `incoming_attack_adjustment` /
`auto_fails_save`), правило авто-крита в упор, Dodge DEX-advantage. Отметить
исправление: `provides_modifiers` теперь реально применяются.
`docs/MODIFIERS.md` — добавить, что condition-модификаторы подмешиваются в сбор
ATTACK_ROLL/SAVING_THROW через `ConditionService.collect_modifiers` (раньше были
осиротевшими).
`docs/ROADMAP.md` — веха **T3 ✅** (закрыты cross-creature преимущество,
Dodge-saves, авто-провалы, авто-крит; T4 — ⏳); в блоке «Доработки по аудиту
2026-05-27» отметить, что соответствующие отложенные пункты сделаны в T3.

- [ ] **Step 4: Финальная регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m pytest tests/unit/test_layering.py -q`
Expected: всё зелёно, guard слоёв проходит.

```bash
git add tests/e2e/test_combat_conditions_play.py docs/CONDITIONS.md docs/MODIFIERS.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "test+docs(t3): e2e боевых условий + CONDITIONS/MODIFIERS/ROADMAP"
```

---

## Self-Review (выполнено при написании плана)

**Покрытие спека:**
- §3.1 боевые поля состояний — T3-2 ✅
- §3.2 ConditionService (collect_modifiers/incoming_attack_adjustment/auto_fails_save) — T3-1/T3-2/T3-4 ✅
- §3.3 attack.py (self + cross-creature + авто-крит) — T3-1/T3-2/T3-3 ✅
- §3.4 saving_throw (авто-провал + Dodge DEX-adv + self) — T3-1/T3-4 ✅
- §3.5 wiring (трекер + composition) — T3-4 ✅
- §5 тесты — распределены; §6 инварианты (авто-провал первым — T3-4 step4; adv+disadv в RollContext — не дублируем).

**Согласованность сигнатур:** `collect_modifiers(creature, target_kind)`,
`incoming_attack_adjustment(target, *, distance_ft, attack_kind) -> (bool,bool)`,
`auto_fails_save(creature, ability) -> bool` — одинаково в объявлении (T3-1/2/4)
и вызовах (attack.py/saving_throw). `roll_saving_throw_raw(..., condition_service=
None)` — объявление T3-1 step6, использование T3-4. Боевые поля состояния —
имена идентичны в base.py (T3-2 step3), builtin (step4), сервисе (step5).

**Плейсхолдеры:** «подогнать RNG-бюджет» (T3-2/T3-3/T3-5) и «перепроверить
старые тесты» (T3-1 step7) — это указания по верификации против фактического
порядка потребления RNG и реальной регрессии, не заглушки фич; код и проверки
приведены полностью.

**Риски на месте:** (1) порядок полей в frozen dataclass'ах builtin (все
добавляемые — с дефолтами, идут после `id`/`implies`); (2) есть ли
`RestrainedCondition` в builtin — если нет, пропустить (отмечено); (3) точный
RNG-бюджет интеграционных/e2e тестов с advantage (2 d20).
