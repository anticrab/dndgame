# T2 — контроль-заклинания (Sleep / Hold Person) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить контроль-заклинания волшебника (Sleep → Unconscious по HP-пулу, Hold Person → Paralyzed по WIS-спасброску с концентрацией) через новый `SpellEffect.CONTROL` и событийную службу `OngoingEffectTracker`, снимающую состояния по триггерам (урон / повторный спасбросок / срыв концентрации); попутно исправить уровни Fireball/Lightning Bolt.

**Architecture:** Заклинание остаётся данными — единый `CastSpellAction` исполняет его через реестр эффект-хендлеров. Новый `ControlSpellHandler` накладывает состояние через `ConditionService.apply_with_implies` и публикует `ConditionApplied` со всей метой снятия. `OngoingEffectTracker` подписан на шину: ловит `ConditionApplied` (запись), `TurnEnded` (повторный спасбросок), `DamageDealt` (пробуждение), `ConcentrationBroken` (снятие каста). Хендлер не знает про трекер — связь через события (как весь движок).

**Tech Stack:** Python 3.12, pydantic v2 (frozen `BaseModel` для событий), frozen dataclasses (domain VO + эффект), pytest, mypy strict, ruff. Гексагональная архитектура (guard `tests/unit/test_layering.py`). Коммиты: `Maxim Lokotkov` / `anticrab@users.noreply.github.com`.

---

## Карта файлов

| Файл | Ответственность | Изменение |
|------|-----------------|-----------|
| `src/dnd/domain/values/spell.py` | `SpellEffect.CONTROL` + поля `condition`/`hp_pool_dice`/`condition_ends_on_damage`/`condition_repeat_save` + валидация | Modify |
| `src/dnd/application/dto/engine_event.py` | события `ConditionApplied` / `ConditionRemoved` | Modify |
| `src/dnd/application/engine/saving_throw.py` | `roll_saving_throw_raw` (без `ctx`) | Modify |
| `src/dnd/application/engine/effects/ongoing_effect_tracker.py` | служба активных условие-эффектов + триггеры снятия | Create |
| `src/dnd/application/engine/effects/__init__.py` | пакет | Create |
| `src/dnd/application/engine/spells/handlers.py` | `ControlSpellHandler` | Modify |
| `src/dnd/application/engine/spells/defaults.py` | регистрация CONTROL | Modify |
| `src/dnd/infrastructure/content/yaml_spell_repository.py` | парс новых полей | Modify |
| `data/content/spells.yaml` | `sleep`, `hold_person`, фикс уровней | Modify |
| `data/content/monsters.yaml` | `known_spells` мага += sleep/hold_person | Modify |
| `src/dnd/application/engine/game_runner.py` | пропуск хода инкапаситированного | Modify |
| `src/dnd/application/engine/ai/simple_monster.py` | то же для AI | Modify |
| `src/dnd/interfaces/cli/app.py`, `src/dnd/interfaces/tui/app.py` | wiring `OngoingEffectTracker.subscribe()` | Modify |
| `src/dnd/interfaces/cli/event_printer.py` | рендер `ConditionApplied`/`ConditionRemoved` | Modify |
| `src/dnd/interfaces/tui/bridge/event_renderer.py` | рефреш на эти события | Modify |
| `docs/SPELLS.md`, `docs/ROADMAP.md` | документация T2 | Modify |

**Важно про события:** `EngineEvent` — это **pydantic `BaseModel`** (`frozen=True, extra="forbid"`), НЕ dataclass. Новые события объявляем как подклассы `EngineEvent` с `event_type: ClassVar[str]` и типизированными полями. `frozenset[...]` валиден в pydantic v2. `ConditionId`/`SpellId`/`CreatureId` — `NewType(str)`; `Ability` — `StrEnum`.

---

## Task T2-1: `SpellEffect.CONTROL` + поля Spell + валидация + парсер

**Files:**
- Modify: `src/dnd/domain/values/spell.py`
- Modify: `src/dnd/infrastructure/content/yaml_spell_repository.py`
- Test: `tests/unit/domain/test_spell_control.py` (Create), `tests/integration/content/test_spell_repository.py` (Modify — если есть; иначе пропустить второй)

- [ ] **Step 1: Написать падающий тест модели**

Create `tests/unit/domain/test_spell_control.py`:

```python
"""CONTROL-заклинания (T2): валидация полей Spell."""
from __future__ import annotations

import pytest

from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import (
    Spell,
    SpellEffect,
    TargetingSpec,
    TargetKind,
)


def _control(**over: object) -> Spell:
    base: dict[str, object] = dict(
        id=SpellId("x"), name="X", level=1, school="enchantment",
        effect=SpellEffect.CONTROL,
        targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=60, description="",
        condition=PARALYZED, save_ability=Ability.WIS,
    )
    base.update(over)
    return Spell(**base)  # type: ignore[arg-type]


def test_control_with_save_ok() -> None:
    sp = _control()
    assert sp.effect is SpellEffect.CONTROL
    assert sp.condition == PARALYZED


def test_control_with_pool_ok() -> None:
    sp = _control(save_ability=None, hp_pool_dice="5d8", condition=UNCONSCIOUS)
    assert sp.hp_pool_dice == "5d8"


def test_control_requires_condition() -> None:
    with pytest.raises(ValueError, match="condition"):
        _control(condition=None)


def test_control_requires_exactly_one_gate() -> None:
    # ни пула, ни save
    with pytest.raises(ValueError, match="hp_pool_dice|save_ability"):
        _control(save_ability=None, hp_pool_dice=None)
    # и пул, и save одновременно
    with pytest.raises(ValueError, match="hp_pool_dice|save_ability"):
        _control(hp_pool_dice="5d8")


def test_repeat_save_requires_save_ability() -> None:
    with pytest.raises(ValueError, match="condition_repeat_save"):
        _control(save_ability=None, hp_pool_dice="5d8",
                 condition=UNCONSCIOUS, condition_repeat_save=True)
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/domain/test_spell_control.py -q`
Expected: FAIL (`Spell` не знает `condition`/`hp_pool_dice`/...; `TypeError: unexpected keyword`).

- [ ] **Step 3: Реализовать**

В `src/dnd/domain/values/spell.py`:

В импорты добавить:
```python
from dnd.domain.values.ids import ConditionId, SpellId
```
(`SpellId` уже импортирован — добавить только `ConditionId`.)

В `class SpellEffect` добавить член:
```python
    CONTROL = "control"  # наложение состояния (± длительность/снятие) — T2
```

В `class Spell` добавить поля после `buffs`:
```python
    # CONTROL (T2): наложение состояния. condition — что; ровно один гейт —
    # hp_pool_dice (Sleep: пул хитов, без спасброска) ИЛИ save_ability (резист).
    condition: ConditionId | None = None
    hp_pool_dice: str | None = None
    condition_ends_on_damage: bool = False   # Sleep: пробуждение от урона
    condition_repeat_save: bool = False       # Hold Person: спасбросок в конце хода
```

В `__post_init__` добавить ветку (после блока BUFF):
```python
        elif self.effect is SpellEffect.CONTROL:
            if self.condition is None:
                raise ValueError(
                    f"CONTROL spell {self.id} requires condition"
                )
            has_pool = self.hp_pool_dice is not None
            has_save = self.save_ability is not None
            if has_pool == has_save:
                raise ValueError(
                    f"CONTROL spell {self.id}: ровно один гейт — "
                    "hp_pool_dice ИЛИ save_ability"
                )
            if self.condition_repeat_save and not has_save:
                raise ValueError(
                    f"CONTROL spell {self.id}: condition_repeat_save требует "
                    "save_ability (есть что перебрасывать)"
                )
```

- [ ] **Step 4: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/domain/test_spell_control.py -q`
Expected: PASS (5 тестов).

- [ ] **Step 5: Парсер YAML**

В `src/dnd/infrastructure/content/yaml_spell_repository.py`, в `_parse`, в конструктор `Spell(...)` добавить (после `buffs=buffs,`):
```python
            condition=ConditionId(entry["condition"]) if entry.get("condition") else None,
            hp_pool_dice=entry.get("hp_pool_dice"),
            condition_ends_on_damage=bool(entry.get("condition_ends_on_damage", False)),
            condition_repeat_save=bool(entry.get("condition_repeat_save", False)),
```
И импорт вверху файла:
```python
from dnd.domain.values.ids import ConditionId, SpellId
```
(`SpellId` уже импортирован — добавить `ConditionId`.)

- [ ] **Step 6: Регрессия + коммит**

Run: `python3 -m pytest tests/unit/domain/test_spell_control.py -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: всё зелёно.

```bash
git add src/dnd/domain/values/spell.py src/dnd/infrastructure/content/yaml_spell_repository.py tests/unit/domain/test_spell_control.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t2): SpellEffect.CONTROL + поля Spell (condition/пул/триггеры) + парсер"
```

---

## Task T2-2: события `ConditionApplied` / `ConditionRemoved`

**Files:**
- Modify: `src/dnd/application/dto/engine_event.py`
- Test: `tests/unit/application/test_condition_events.py` (Create)

- [ ] **Step 1: Падающий тест**

Create `tests/unit/application/test_condition_events.py`:

```python
"""События наложения/снятия состояний (T2)."""
from __future__ import annotations

from dnd.application.dto.engine_event import ConditionApplied, ConditionRemoved
from dnd.domain.conditions.builtin import PARALYZED
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import CreatureId, SpellId


def test_condition_applied_fields() -> None:
    ev = ConditionApplied(
        caster_id=CreatureId("mage"), target_id=CreatureId("orc"),
        spell_id=SpellId("hold_person"), conditions=frozenset({PARALYZED}),
        ends_on_damage=False, repeat_save_ability=Ability.WIS,
        save_dc=13, concentration=True,
    )
    assert ev.target_id == CreatureId("orc")
    assert PARALYZED in ev.conditions
    assert ev.repeat_save_ability is Ability.WIS


def test_condition_removed_fields() -> None:
    ev = ConditionRemoved(
        target_id=CreatureId("orc"), conditions=frozenset({PARALYZED}),
        reason="save",
    )
    assert ev.reason == "save"
    assert PARALYZED in ev.conditions
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_condition_events.py -q`
Expected: FAIL (`ImportError: cannot import name 'ConditionApplied'`).

- [ ] **Step 3: Реализовать**

В `src/dnd/application/dto/engine_event.py`. Убедиться, что вверху импортированы `Ability`, `ConditionId`, `SpellId` (добавить недостающее — `Ability` из `dnd.domain.values.ability`, `ConditionId` из `dnd.domain.values.ids`). Добавить классы (рядом с прочими событиями, например после `ConcentrationBroken`):

```python
class ConditionApplied(EngineEvent):
    """Состояние наложено на цель (T2). Несёт всю мету снятия, чтобы
    OngoingEffectTracker восстановил активный эффект из события."""

    event_type: ClassVar[str] = "condition.applied"
    caster_id: CreatureId
    target_id: CreatureId
    spell_id: SpellId | None
    conditions: frozenset[ConditionId]
    ends_on_damage: bool = False
    repeat_save_ability: Ability | None = None
    save_dc: int | None = None
    concentration: bool = False


class ConditionRemoved(EngineEvent):
    """Состояние(я) снято с цели (T2)."""

    event_type: ClassVar[str] = "condition.removed"
    target_id: CreatureId
    conditions: frozenset[ConditionId]
    reason: str  # "damage" | "save" | "concentration_ended" | "manual"
```

Если `__all__` в файле есть — добавить туда `"ConditionApplied"`, `"ConditionRemoved"`.

- [ ] **Step 4: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/application/test_condition_events.py -q && python3 -m mypy src`
Expected: PASS.

- [ ] **Step 5: Коммит**

```bash
git add src/dnd/application/dto/engine_event.py tests/unit/application/test_condition_events.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t2): события ConditionApplied / ConditionRemoved"
```

---

## Task T2-3: `roll_saving_throw_raw` + `OngoingEffectTracker`

**Files:**
- Modify: `src/dnd/application/engine/saving_throw.py`
- Create: `src/dnd/application/engine/effects/__init__.py`
- Create: `src/dnd/application/engine/effects/ongoing_effect_tracker.py`
- Test: `tests/unit/application/test_ongoing_effect_tracker.py` (Create)

- [ ] **Step 1: Рефактор-обёртка спасброска (падающий тест)**

Append to `tests/unit/application/test_saving_throw.py`:

```python
def test_roll_saving_throw_raw_uses_services() -> None:
    """raw-вариант не требует TurnContext — берёт службы напрямую."""
    from dnd.application.engine.saving_throw import roll_saving_throw_raw
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability, AbilityScores
    from dnd.domain.values.ids import CreatureId

    deps, _bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=[10]
    )
    actor = Creature.create(
        id_=CreatureId("a"), name="a",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=14, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )
    # d20=10 + WIS(+2) = 12 >= 12 → успех.
    assert roll_saving_throw_raw(
        actor, Ability.WIS, dc=12,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    ) is True
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_saving_throw.py::test_roll_saving_throw_raw_uses_services -q`
Expected: FAIL (`ImportError: roll_saving_throw_raw`).

- [ ] **Step 3: Реализовать обёртку**

В `src/dnd/application/engine/saving_throw.py` заменить тело `roll_saving_throw`, выделив raw:

```python
def roll_saving_throw_raw(
    actor: Creature,
    ability: Ability,
    *,
    dc: int,
    dice_roller: DiceRoller,
    modifier_applier: ModifierApplier,
    tags: tuple[str, ...] = ("saving_throw",),
) -> bool:
    """Бросок спасброска без боевого ``TurnContext`` — нужен службам вне хода
    (OngoingEffectTracker, concentration). ``d20 + saving_throw_bonus +
    adjustments`` ≥ dc; учитывает advantage/disadvantage от состояний."""
    bonus = saving_throw_bonus(actor, ability)
    adj = modifier_applier.to_roll_adjustments(
        modifier_applier.collect(
            owner_id=actor.id, target_kind=ModifierTargetKind.SAVING_THROW
        )
    )
    roll = dice_roller.roll(
        DiceExpr.parse(f"d20{bonus + adj.numeric_bonus:+d}"),
        RollContext(
            purpose=RollPurpose.SAVE, actor_id=actor.id,
            advantage=adj.advantage, disadvantage=adj.disadvantage,
            extra_dice=adj.extra_dice, tags=tags,
        ),
    )
    return roll.total >= dc


def roll_saving_throw(
    actor: Creature,
    ability: Ability,
    *,
    dc: int,
    ctx: TurnContext,
    tags: tuple[str, ...] = ("saving_throw",),
) -> bool:
    """Бросок спасброска в контексте хода — делегирует в raw."""
    return roll_saving_throw_raw(
        actor, ability, dc=dc,
        dice_roller=ctx.dice_roller, modifier_applier=ctx.modifier_applier,
        tags=tags,
    )
```

Добавить в TYPE_CHECKING-импорты типы служб:
```python
    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.application.ports.modifier_applier import ModifierApplier
```
(Проверить точные пути портов: `grep -rn "class DiceRoller\|class ModifierApplier" src/dnd/application/ports`.)
Обновить `__all__`: добавить `"roll_saving_throw_raw"`.

- [ ] **Step 4: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/application/test_saving_throw.py -q`
Expected: PASS (старые + новый).

- [ ] **Step 5: Падающий тест трекера**

Create `tests/unit/application/test_ongoing_effect_tracker.py`:

```python
"""OngoingEffectTracker (T2): запись эффектов + триггеры снятия."""
from __future__ import annotations

from dnd.application.dto.engine_event import (
    ConcentrationBroken,
    ConditionApplied,
    ConditionRemoved,
    DamageDealt,
    TurnEnded,
)
from dnd.application.engine.effects.ongoing_effect_tracker import (
    OngoingEffectTracker,
)
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.damage import DamageType
from dnd.domain.values.ids import CreatureId, RollId, SpellId


def _victim() -> Creature:
    c = Creature.create(
        id_=CreatureId("orc"), name="orc",
        abilities=AbilityScores.of(str_=12, dex=10, con=12, int_=8, wis=8, cha=8),
        max_hp=15, armor_class=13, speed_ft=30,
    )
    return c


def _tracker(rolls: list[int], victim: Creature) -> tuple[OngoingEffectTracker, object]:
    deps, bus, _rng = build_scripted_dependencies(
        battlefield=Battlefield(1, 1), rolls=rolls
    )
    tracker = OngoingEffectTracker(
        participants={victim.id: victim}, event_bus=bus,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    )
    tracker.subscribe()
    return tracker, bus


def test_damage_wakes_sleeper() -> None:
    victim = _victim()
    victim.apply_condition(UNCONSCIOUS)
    _t, bus = _tracker([], victim)
    bus.publish(ConditionApplied(
        caster_id=CreatureId("mage"), target_id=victim.id, spell_id=SpellId("sleep"),
        conditions=frozenset({UNCONSCIOUS}), ends_on_damage=True,
        repeat_save_ability=None, save_dc=None, concentration=False,
    ))
    removed: list[ConditionRemoved] = []
    bus.subscribe(ConditionRemoved, removed.append)
    bus.publish(DamageDealt(
        attacker_id=CreatureId("x"), target_id=victim.id,
        damage_roll_id=RollId("r"), damage_type=DamageType.SLASHING,
        raw_amount=3, final_amount=3, is_critical=False,
        hp_after=12, hp_max=15, was_lethal=False,
    ))
    assert not victim.has_condition(UNCONSCIOUS)
    assert removed and removed[-1].reason == "damage"


def test_turn_end_save_frees_held() -> None:
    victim = _victim()
    victim.apply_condition(PARALYZED)
    # WIS(-1); d20=20 → 19 >= dc 13 → успех.
    _t, bus = _tracker([20], victim)
    bus.publish(ConditionApplied(
        caster_id=CreatureId("mage"), target_id=victim.id,
        spell_id=SpellId("hold_person"), conditions=frozenset({PARALYZED}),
        ends_on_damage=False, repeat_save_ability=Ability.WIS,
        save_dc=13, concentration=True,
    ))
    removed: list[ConditionRemoved] = []
    bus.subscribe(ConditionRemoved, removed.append)
    bus.publish(TurnEnded(actor_id=victim.id, round_number=1))
    assert not victim.has_condition(PARALYZED)
    assert removed[-1].reason == "save"


def test_turn_end_save_fail_keeps_held() -> None:
    victim = _victim()
    victim.apply_condition(PARALYZED)
    # d20=1 → 0 < 13 → провал, держим.
    _t, bus = _tracker([1], victim)
    bus.publish(ConditionApplied(
        caster_id=CreatureId("mage"), target_id=victim.id,
        spell_id=SpellId("hold_person"), conditions=frozenset({PARALYZED}),
        ends_on_damage=False, repeat_save_ability=Ability.WIS,
        save_dc=13, concentration=True,
    ))
    bus.publish(TurnEnded(actor_id=victim.id, round_number=1))
    assert victim.has_condition(PARALYZED)


def test_concentration_break_frees() -> None:
    victim = _victim()
    victim.apply_condition(PARALYZED)
    _t, bus = _tracker([], victim)
    bus.publish(ConditionApplied(
        caster_id=CreatureId("mage"), target_id=victim.id,
        spell_id=SpellId("hold_person"), conditions=frozenset({PARALYZED}),
        ends_on_damage=False, repeat_save_ability=Ability.WIS,
        save_dc=13, concentration=True,
    ))
    bus.publish(ConcentrationBroken(
        actor_id=CreatureId("mage"), spell_id="hold_person", dc=10, roll_total=3,
    ))
    assert not victim.has_condition(PARALYZED)
```

- [ ] **Step 6: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_ongoing_effect_tracker.py -q`
Expected: FAIL (нет модуля `effects.ongoing_effect_tracker`).

- [ ] **Step 7: Реализовать службу**

Create `src/dnd/application/engine/effects/__init__.py`:
```python
"""Активные эффекты во времени (T2): OngoingEffectTracker."""
```

Create `src/dnd/application/engine/effects/ongoing_effect_tracker.py`:

```python
"""OngoingEffectTracker — снятие состояний по событийным триггерам (T2).

Контроль-заклинания накладывают состояние «до момента X». Хендлер публикует
:class:`ConditionApplied` со всей метой снятия; трекер хранит активный эффект и
снимает состояние, когда срабатывает триггер:

* урон по цели (``ends_on_damage``) — пробуждение Sleep;
* конец хода цели (``repeat_save_ability``) — повторный спасбросок Hold Person;
* срыв концентрации кастера (``ConcentrationBroken``) — снятие удержания.

Связь только через шину — трекер не знает про хендлеры, хендлеры не знают про
трекер. Это фундамент длительностей для этапа T3.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import (
    ConcentrationBroken,
    ConditionApplied,
    ConditionRemoved,
    DamageDealt,
    TurnEnded,
)
from dnd.application.engine.saving_throw import roll_saving_throw_raw

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dnd.application.ports.dice_roller import DiceRoller
    from dnd.application.ports.event_bus import EventBus
    from dnd.application.ports.modifier_applier import ModifierApplier
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import Ability
    from dnd.domain.values.ids import ConditionId, CreatureId, SpellId


@dataclass(slots=True)
class OngoingConditionEffect:
    caster_id: CreatureId
    target_id: CreatureId
    spell_id: SpellId | None
    conditions: frozenset[ConditionId]
    ends_on_damage: bool
    repeat_save_ability: Ability | None
    save_dc: int | None
    concentration: bool


class OngoingEffectTracker:
    """Хранит активные условие-эффекты и снимает их по триггерам."""

    def __init__(
        self,
        participants: Mapping[CreatureId, Creature],
        event_bus: EventBus,
        *,
        dice_roller: DiceRoller,
        modifier_applier: ModifierApplier,
    ) -> None:
        self._participants = participants
        self._bus = event_bus
        self._dice = dice_roller
        self._mods = modifier_applier
        self._effects: list[OngoingConditionEffect] = []

    def subscribe(self) -> None:
        self._bus.subscribe(ConditionApplied, self._on_applied)
        self._bus.subscribe(TurnEnded, self._on_turn_ended)
        self._bus.subscribe(DamageDealt, self._on_damage)
        self._bus.subscribe(ConcentrationBroken, self._on_concentration_broken)

    # --- запись ---------------------------------------------------------
    def _on_applied(self, event: ConditionApplied) -> None:
        self._effects.append(OngoingConditionEffect(
            caster_id=event.caster_id, target_id=event.target_id,
            spell_id=event.spell_id, conditions=event.conditions,
            ends_on_damage=event.ends_on_damage,
            repeat_save_ability=event.repeat_save_ability,
            save_dc=event.save_dc, concentration=event.concentration,
        ))

    # --- триггеры снятия ------------------------------------------------
    def _on_turn_ended(self, event: TurnEnded) -> None:
        actor = self._participants.get(event.actor_id)
        if actor is None:
            return
        for effect in list(self._effects):
            if effect.target_id != event.actor_id:
                continue
            if effect.repeat_save_ability is None or effect.save_dc is None:
                continue
            saved = roll_saving_throw_raw(
                actor, effect.repeat_save_ability, dc=effect.save_dc,
                dice_roller=self._dice, modifier_applier=self._mods,
                tags=("repeat_save",),
            )
            if saved:
                self._remove(effect, reason="save")

    def _on_damage(self, event: DamageDealt) -> None:
        if event.final_amount <= 0:
            return
        for effect in list(self._effects):
            if effect.target_id == event.target_id and effect.ends_on_damage:
                self._remove(effect, reason="damage")

    def _on_concentration_broken(self, event: ConcentrationBroken) -> None:
        for effect in list(self._effects):
            if (
                effect.concentration
                and effect.caster_id == event.actor_id
                and effect.spell_id is not None
                and str(effect.spell_id) == event.spell_id
            ):
                self._remove(effect, reason="concentration_ended")

    # --- снятие ---------------------------------------------------------
    def _remove(self, effect: OngoingConditionEffect, *, reason: str) -> None:
        target = self._participants.get(effect.target_id)
        if target is not None:
            for cond in effect.conditions:
                target.remove_condition(cond)
        if effect in self._effects:
            self._effects.remove(effect)
        self._bus.publish(ConditionRemoved(
            target_id=effect.target_id, conditions=effect.conditions, reason=reason,
        ))


__all__ = ["OngoingConditionEffect", "OngoingEffectTracker"]
```

- [ ] **Step 8: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/application/test_ongoing_effect_tracker.py -q && python3 -m mypy src`
Expected: PASS (4 теста).

- [ ] **Step 9: Регрессия + коммит**

Run: `python3 -m pytest tests/unit/application -q && python3 -m ruff check src tests`

```bash
git add src/dnd/application/engine/saving_throw.py src/dnd/application/engine/effects/ tests/unit/application/test_saving_throw.py tests/unit/application/test_ongoing_effect_tracker.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t2): roll_saving_throw_raw + OngoingEffectTracker (триггеры снятия состояний)"
```

---

## Task T2-4: `ControlSpellHandler` + регистрация

**Files:**
- Modify: `src/dnd/application/engine/spells/handlers.py`
- Modify: `src/dnd/application/engine/spells/defaults.py`
- Test: `tests/unit/application/test_control_spell_handler.py` (Create)

- [ ] **Step 1: Падающий тест**

Create `tests/unit/application/test_control_spell_handler.py`:

```python
"""ControlSpellHandler (T2): пул Sleep + спасбросок Hold Person."""
from __future__ import annotations

from dnd.application.dto.engine_event import ConditionApplied
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.spells.handlers import ControlSpellHandler
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.conditions.registry import default_condition_registry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind


def _mage() -> Creature:
    m = Creature.create(
        id_=CreatureId("mage"), name="mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=14, armor_class=12, speed_ft=30,
    )
    m.spellcasting_ability = Ability.INT
    m.spell_slots = {1: 2, 2: 2}
    return m


def _weak(id_: str, hp: int) -> Creature:
    c = Creature.create(
        id_=CreatureId(id_), name=id_,
        abilities=AbilityScores.of(str_=8, dex=10, con=10, int_=8, wis=8, cha=8),
        max_hp=hp, armor_class=12, speed_ft=30,
    )
    return c


def _ctx(rolls: list[int], creatures: list[Creature]):
    bf = Battlefield(8, 8)
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    from dnd.application.engine.turn_context import TurnContext
    ctx = TurnContext(
        actor_id=creatures[0].id,
        participants={c.id: c for c in creatures},
        battlefield=bf, dice_roller=deps.dice_roller, event_bus=bus,
        modifier_applier=deps.modifier_applier,
        condition_service=ConditionService(default_condition_registry()),
    )
    return ctx, bus


def _sleep() -> Spell:
    return Spell(
        id=SpellId("sleep"), name="Sleep", level=1, school="enchantment",
        effect=SpellEffect.CONTROL,
        targeting=TargetingSpec(kind=TargetKind.AREA, shape=None) if False else
        TargetingSpec(kind=TargetKind.SINGLE),  # цели уже отрезолвлены до handler
        range_ft=90, description="", condition=UNCONSCIOUS,
        hp_pool_dice="5d8", condition_ends_on_damage=True,
    )


def test_sleep_pool_orders_by_hp_and_stops() -> None:
    mage = _mage()
    low = _weak("low", 5)
    high = _weak("high", 30)
    ctx, bus = _ctx([2, 2, 2, 2, 2], [mage, low, high])  # 5d8 → пул 10
    applied: list[ConditionApplied] = []
    bus.subscribe(ConditionApplied, applied.append)
    # ВАЖНО: TurnContext.dice_roller отдаёт по скрипту; 5d8=10 (хватает на low=5,
    # не хватает на high=30, т.к. сначала идёт low).
    ControlSpellHandler().apply(mage, (high, low), _sleep(), ctx)
    assert low.has_condition(UNCONSCIOUS)
    assert not high.has_condition(UNCONSCIOUS)
    assert any(a.target_id == low.id for a in applied)


def _hold() -> Spell:
    return Spell(
        id=SpellId("hold_person"), name="Hold Person", level=2,
        school="enchantment", effect=SpellEffect.CONTROL,
        targeting=TargetingSpec(kind=TargetKind.SINGLE), range_ft=60,
        description="", condition=PARALYZED, save_ability=Ability.WIS,
        concentration=True, condition_repeat_save=True,
    )


def test_hold_person_fail_save_paralyzes_and_sets_concentration() -> None:
    mage = _mage()
    orc = _weak("orc", 15)  # WIS -1
    ctx, bus = _ctx([1], [mage, orc])  # d20=1 → провал
    applied: list[ConditionApplied] = []
    bus.subscribe(ConditionApplied, applied.append)
    ControlSpellHandler().apply(mage, (orc,), _hold(), ctx)
    assert orc.has_condition(PARALYZED)
    assert mage.concentration == SpellId("hold_person")
    assert applied[-1].repeat_save_ability is Ability.WIS


def test_hold_person_success_save_no_effect() -> None:
    mage = _mage()
    orc = _weak("orc", 15)
    ctx, bus = _ctx([20], [mage, orc])  # d20=20 → успех
    ControlSpellHandler().apply(mage, (orc,), _hold(), ctx)
    assert not orc.has_condition(PARALYZED)
```

> Примечание: точная сигнатура `TurnContext` и `default_condition_registry` —
> сверить (`grep -n "class TurnContext" -A20 src/dnd/application/engine/turn_context.py`,
> `grep -rn "default_condition_registry\|def.*condition_registry" src/dnd/domain/conditions/registry.py`).
> Если конструктор отличается — подогнать `_ctx`, не меняя смысла теста.

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/unit/application/test_control_spell_handler.py -q`
Expected: FAIL (`ImportError: ControlSpellHandler`).

- [ ] **Step 3: Реализовать хендлер**

В `src/dnd/application/engine/spells/handlers.py` добавить класс (в конец, рядом с прочими хендлерами). Импорты вверху дополнить:
```python
from dnd.application.dto.engine_event import ConditionApplied, DamageDealt, HealingApplied
from dnd.application.engine.saving_throw import roll_saving_throw
```
(`DamageDealt`/`HealingApplied` уже импортированы; добавить `ConditionApplied`. `roll_saving_throw` уже импортирован.)

```python
class ControlSpellHandler:
    """CONTROL: наложение состояния. Две ветки гейта (валидация — в Spell):

    * пул (``hp_pool_dice``, Sleep): кидаем пул, усыпляем цели по возрастанию
      текущего HP, пока хватает; без спасброска;
    * спасбросок (``save_ability``, Hold Person): провал → состояние.

    Накладывает через ConditionService (каскад implies) и публикует
    ``ConditionApplied`` со всей метой снятия — её слушает OngoingEffectTracker.
    """

    def apply(
        self,
        caster: Creature,
        targets: tuple[Creature, ...],
        spell: Spell,
        ctx: TurnContext,
    ) -> None:
        assert spell.condition is not None
        affected: list[Creature] = []
        if spell.hp_pool_dice is not None:
            affected = self._apply_pool(caster, targets, spell, ctx)
        else:
            affected = self._apply_save(caster, targets, spell, ctx)
        if affected and spell.concentration:
            caster.concentration = spell.id

    def _apply_pool(
        self, caster: Creature, targets: tuple[Creature, ...],
        spell: Spell, ctx: TurnContext,
    ) -> list[Creature]:
        assert spell.hp_pool_dice is not None and spell.condition is not None
        pool_roll = ctx.dice_roller.roll(
            DiceExpr.parse(spell.hp_pool_dice),
            RollContext(purpose=RollPurpose.UTILITY, actor_id=caster.id),
        )
        pool = pool_roll.total
        candidates = sorted(
            (t for t in targets if t.is_alive and not t.is_at_zero_hp),
            key=lambda c: c.hit_points.current,
        )
        affected: list[Creature] = []
        for cand in candidates:
            need = cand.hit_points.current
            if need > pool:
                break
            pool -= need
            self._apply_condition(caster, cand, spell, ctx)
            affected.append(cand)
        return affected

    def _apply_save(
        self, caster: Creature, targets: tuple[Creature, ...],
        spell: Spell, ctx: TurnContext,
    ) -> list[Creature]:
        assert spell.save_ability is not None
        dc = caster.spell_save_dc()
        affected: list[Creature] = []
        for target in targets:
            if not target.is_alive or target.is_at_zero_hp:
                continue
            saved = roll_saving_throw(
                target, spell.save_ability, dc=dc, ctx=ctx, tags=("spell_save",),
            )
            if not saved:
                self._apply_condition(caster, target, spell, ctx)
                affected.append(target)
        return affected

    def _apply_condition(
        self, caster: Creature, target: Creature, spell: Spell, ctx: TurnContext,
    ) -> None:
        assert spell.condition is not None
        result = ctx.condition_service.apply_with_implies(target, spell.condition)
        if not result.applied:
            return
        dc = caster.spell_save_dc() if spell.save_ability is not None else None
        ctx.event_bus.publish(ConditionApplied(
            caster_id=caster.id, target_id=target.id, spell_id=spell.id,
            conditions=result.applied,
            ends_on_damage=spell.condition_ends_on_damage,
            repeat_save_ability=spell.save_ability if spell.condition_repeat_save else None,
            save_dc=dc if spell.condition_repeat_save else None,
            concentration=spell.concentration,
        ))
```

Дополнить импорт `RollPurpose` — проверить, что `RollPurpose.UTILITY` существует
(`grep -n "UTILITY\|class RollPurpose" src/dnd/application/dto/rolls.py`); если
нет — использовать ближайший нейтральный (`RollPurpose.DAMAGE` не подходит
семантически; при отсутствии UTILITY добавить член `UTILITY = "utility"` в enum
отдельным мелким шагом).

- [ ] **Step 4: Регистрация в реестре**

В `src/dnd/application/engine/spells/defaults.py`:
- импорт: добавить `ControlSpellHandler` в список из `...spells.handlers`;
- в `default_spell_effect_registry`: `registry.register(SpellEffect.CONTROL, ControlSpellHandler())`.

- [ ] **Step 5: Запустить — зелёно**

Run: `python3 -m pytest tests/unit/application/test_control_spell_handler.py -q && python3 -m mypy src`
Expected: PASS (3 теста).

- [ ] **Step 6: Коммит**

```bash
git add src/dnd/application/engine/spells/handlers.py src/dnd/application/engine/spells/defaults.py tests/unit/application/test_control_spell_handler.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t2): ControlSpellHandler (пул Sleep + спасбросок Hold Person) + регистрация"
```

---

## Task T2-5: пропуск хода инкапаситированного + wiring трекера

**Files:**
- Modify: `src/dnd/application/engine/game_runner.py:~123,~149`
- Modify: `src/dnd/application/engine/ai/simple_monster.py:~57`
- Modify: `src/dnd/interfaces/cli/app.py`, `src/dnd/interfaces/tui/app.py`
- Test: `tests/integration/engine/test_incapacitated_skip.py` (Create)

- [ ] **Step 1: Падающий тест пропуска хода**

Create `tests/integration/engine/test_incapacitated_skip.py`:

```python
"""Инкапаситированный актёр (Paralyzed/Unconscious) не действует (T2)."""
from __future__ import annotations

from dnd.application.engine.ai.simple_monster import (
    is_hostile_from_factions,
    take_monster_turn,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import SCIMITAR


def test_paralyzed_monster_does_nothing() -> None:
    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("hero"), name="hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=15, speed_ft=30,
    )
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=10, dex=12, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30, equipped_weapon=SCIMITAR,
    )
    gob.apply_condition(PARALYZED)
    bf.place_creature(hero.id, Square(1, 2))
    bf.place_creature(gob.id, Square(2, 2))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1])
    enc = Encounter(
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    hp_before = hero.hit_points.current
    if enc.factions[actor.id] is Faction.MONSTERS:
        take_monster_turn(
            actor, ctx, is_hostile=is_hostile_from_factions(actor.id, enc.factions)
        )
    # Парализованный гоблин не атакует — герой целым.
    assert hero.hit_points.current == hp_before
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/integration/engine/test_incapacitated_skip.py -q`
Expected: возможно FAIL (парализованный гоблин атакует) — фиксируем.
Если он уже не действует (например, `is_at_zero_hp`-логика случайно ловит) — тест может пройти; тогда всё равно добавить явный guard ниже для надёжности и оставить тест как регрессию.

- [ ] **Step 3: Guard в AI**

В `src/dnd/application/engine/ai/simple_monster.py`, в `take_monster_turn`, рядом со строкой `if not actor.is_alive or actor.is_at_zero_hp:` (≈ строка 57) расширить условие:
```python
    from dnd.domain.conditions.builtin import INCAPACITATED
    if not actor.is_alive or actor.is_at_zero_hp or actor.has_condition(INCAPACITATED):
        return
```
(Импорт `INCAPACITATED` поднять в шапку модуля, не внутрь функции, если стиль файла это требует — проверить существующие импорты.)

- [ ] **Step 4: Guard в GameRunner**

В `src/dnd/application/engine/game_runner.py` на обоих местах (≈ строки 123 и 149), где `if not actor.is_alive or actor.is_at_zero_hp:` — добавить `or actor.has_condition(INCAPACITATED)`. Импорт `INCAPACITATED` из `dnd.domain.conditions.builtin` в шапку.

- [ ] **Step 5: Запустить — зелёно**

Run: `python3 -m pytest tests/integration/engine/test_incapacitated_skip.py -q`
Expected: PASS.

- [ ] **Step 6: Wiring трекера (CLI)**

В `src/dnd/interfaces/cli/app.py` рядом с блоком `XpAwardService(...).subscribe()` добавить:
```python
    from dnd.application.engine.effects.ongoing_effect_tracker import (
        OngoingEffectTracker,
    )
    OngoingEffectTracker(
        participants=enc.participants, event_bus=enc.event_bus,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    ).subscribe()
```
(Сверить имя переменной зависимостей: `deps` vs `services`/`runtime` — взять то,
что в этом scope; `dice_roller`/`modifier_applier` доступны через него.)

- [ ] **Step 7: Wiring трекера (TUI)**

В `src/dnd/interfaces/tui/app.py` — аналогично, рядом с тем же XP/level-up wiring.
Сверить, что объект зависимостей/энкаунтера в scope. Если TUI создаёт `enc` и
`deps` внутри `run_tui` — добавить туда.

- [ ] **Step 8: Регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: всё зелёно.

```bash
git add src/dnd/application/engine/game_runner.py src/dnd/application/engine/ai/simple_monster.py src/dnd/interfaces/cli/app.py src/dnd/interfaces/tui/app.py tests/integration/engine/test_incapacitated_skip.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t2): пропуск хода инкапаситированных + wiring OngoingEffectTracker (CLI/TUI)"
```

---

## Task T2-6: контент (sleep / hold_person) + фикс уровней + рендер

**Files:**
- Modify: `data/content/spells.yaml`
- Modify: `data/content/monsters.yaml`
- Modify: `src/dnd/interfaces/cli/event_printer.py`
- Modify: `src/dnd/interfaces/tui/bridge/event_renderer.py`
- Test: `tests/integration/content/test_control_spells_content.py` (Create)

- [ ] **Step 1: Падающий контент-тест**

Create `tests/integration/content/test_control_spells_content.py`:

```python
"""Контент T2: sleep/hold_person парсятся; уровни evocation исправлены."""
from __future__ import annotations

from pathlib import Path

from dnd.domain.conditions.builtin import PARALYZED, UNCONSCIOUS
from dnd.domain.values.ability import Ability
from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import SpellEffect
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository

_SPELLS = Path("data/content/spells.yaml")


def _repo() -> YamlSpellRepository:
    return YamlSpellRepository(_SPELLS)


def test_sleep_parsed() -> None:
    sp = _repo().load(SpellId("sleep"))
    assert sp.effect is SpellEffect.CONTROL
    assert sp.condition == UNCONSCIOUS
    assert sp.hp_pool_dice == "5d8"
    assert sp.condition_ends_on_damage is True
    assert sp.level == 1


def test_hold_person_parsed() -> None:
    sp = _repo().load(SpellId("hold_person"))
    assert sp.effect is SpellEffect.CONTROL
    assert sp.condition == PARALYZED
    assert sp.save_ability is Ability.WIS
    assert sp.concentration is True
    assert sp.condition_repeat_save is True
    assert sp.level == 2


def test_evocation_levels_fixed() -> None:
    repo = _repo()
    assert repo.load(SpellId("fireball")).level == 3
    assert repo.load(SpellId("lightning_bolt")).level == 3
    assert repo.load(SpellId("burning_hands")).level == 1
```

- [ ] **Step 2: Запустить — падает**

Run: `python3 -m pytest tests/integration/content/test_control_spells_content.py -q`
Expected: FAIL (нет sleep/hold_person; fireball level 1).

- [ ] **Step 3: Контент в spells.yaml**

В `data/content/spells.yaml` исправить уровни:
- `fireball`: `level: 1` → `level: 3`
- `lightning_bolt`: `level: 1` → `level: 3`
- (`burning_hands` — проверить, что `level: 1`; не трогать, если так.)

Добавить два заклинания:
```yaml
- id: sleep
  name: "Sleep"
  level: 1
  school: enchantment
  effect: control
  targeting: { kind: area, shape: circle, radius_ft: 5, origin: at_point }
  range_ft: 90
  condition: unconscious
  hp_pool_dice: "5d8"
  condition_ends_on_damage: true
  description: "Усыпляет существ в сфере: пул хитов 5d8 тратится от самых раненых; без спасброска; цель просыпается, получив урон."

- id: hold_person
  name: "Hold Person"
  level: 2
  school: enchantment
  effect: control
  targeting: { kind: single }
  range_ft: 60
  condition: paralyzed
  save_ability: WIS
  concentration: true
  condition_repeat_save: true
  description: "Удерживает гуманоида (WIS-спасбросок). Парализован; в конце каждого своего хода повторяет спасбросок. Требует концентрации."
```

- [ ] **Step 4: known_spells мага**

В `data/content/monsters.yaml`, `mage_apprentice.known_spells` — добавить `sleep`, `hold_person`:
```yaml
  known_spells: [fire_bolt, sacred_flame, magic_missile, cure_wounds, shield_of_faith, fireball, burning_hands, lightning_bolt, sleep, hold_person]
```

- [ ] **Step 5: Запустить — зелёно (контент)**

Run: `python3 -m pytest tests/integration/content/test_control_spells_content.py -q`
Expected: PASS.

- [ ] **Step 6: Рендер CLI**

В `src/dnd/interfaces/cli/event_printer.py`:
- импорт: добавить `ConditionApplied, ConditionRemoved` в список из `engine_event`;
- методы:
```python
    def _on_condition_applied(self, event: ConditionApplied) -> None:
        names = ", ".join(sorted(str(c) for c in event.conditions))
        self._print(f"[magenta]✦ {event.target_id} получает состояние: {names}[/magenta]")

    def _on_condition_removed(self, event: ConditionRemoved) -> None:
        names = ", ".join(sorted(str(c) for c in event.conditions))
        reason = {
            "damage": "от урона", "save": "спасброском",
            "concentration_ended": "конец концентрации", "manual": "снято",
        }.get(event.reason, event.reason)
        self._print(f"[green]✧ {event.target_id} освобождается ({names}, {reason})[/green]")
```
- в `_DISPATCH` добавить:
```python
        ConditionApplied: lambda self, e: self._on_condition_applied(e),
        ConditionRemoved: lambda self, e: self._on_condition_removed(e),
```
(Тексты в стиле остального printer'а; при наличии i18n-обёртки в файле —
использовать её, иначе оставить как есть, как сделано для прочих строк.)

- [ ] **Step 7: Рендер TUI**

В `src/dnd/interfaces/tui/bridge/event_renderer.py`:
- импорт: `ConditionApplied, ConditionRemoved`;
- в `_DISPATCH` (≈ строка 247) добавить:
```python
    ConditionApplied: lambda r, e: r._on_hp_changed(e),
    ConditionRemoved: lambda r, e: r._on_hp_changed(e),
```
(`_on_hp_changed` уже принимает `EngineEvent` и рефрешит карту/инициативу —
состояния влияют на бейджи существа.)

- [ ] **Step 8: Регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: всё зелёно (старые тесты слотов мага не затронуты — sleep/hold_person добавлены к known_spells, slots не менялись).

```bash
git add data/content/spells.yaml data/content/monsters.yaml src/dnd/interfaces/cli/event_printer.py src/dnd/interfaces/tui/bridge/event_renderer.py tests/integration/content/test_control_spells_content.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(t2): контент sleep/hold_person + фикс уровней fireball/lightning_bolt + рендер состояний"
```

---

## Task T2-7: e2e-смок + интеграционный сценарий + документация

**Files:**
- Create: `tests/e2e/test_control_spells_play.py`
- Modify: `docs/SPELLS.md`, `docs/ROADMAP.md`

- [ ] **Step 1: Падающий e2e (Sleep)**

Create `tests/e2e/test_control_spells_play.py`:

```python
"""E2E T2: маг усыпляет гоблина (Sleep), затем сцена сходится."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.action import Allowed
from dnd.application.dto.engine_event import ConditionApplied, EngineEvent
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.effects.ongoing_effect_tracker import OngoingEffectTracker
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.square import Square
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository


@pytest.mark.e2e
def test_mage_sleeps_goblin() -> None:
    bf = Battlefield(8, 8)
    mage = Creature.create(
        id_=CreatureId("mage"), name="mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=14, armor_class=12, speed_ft=30,
    )
    mage.spellcasting_ability = Ability.INT
    mage.known_spells = (SpellId("sleep"),)
    mage.spell_slots = {1: 2}
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=8, dex=12, con=10, int_=8, wis=8, cha=8),
        max_hp=6, armor_class=12, speed_ft=30,
    )
    bf.place_creature(mage.id, Square(1, 1))
    bf.place_creature(gob.id, Square(2, 2))
    # init mage=20, gob=1; пул 5d8 = 8 (8 кубов? нет — 5 кубов по 2 = 10).
    deps, bus, _ = build_scripted_dependencies(
        battlefield=bf, rolls=[20, 1, 2, 2, 2, 2, 2]
    )
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    OngoingEffectTracker(
        participants=enc.participants, event_bus=enc.event_bus,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    ).subscribe()
    applied: list[ConditionApplied] = []
    bus.subscribe(ConditionApplied, applied.append)
    enc.start()
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    assert enc.factions[actor.id] is Faction.PARTY  # маг первый

    spell_repo = YamlSpellRepository(Path("data/content/spells.yaml"))
    action = CastSpellAction(spell_repository=spell_repo)
    params = CastSpellParams(spell_id=SpellId("sleep"), target_point=Square(2, 2))
    assert isinstance(action.can_perform_against(actor, params, ctx), Allowed)
    action.execute(actor, params, ctx)

    assert gob.has_condition(UNCONSCIOUS)
    assert applied and applied[-1].target_id == gob.id
```

> Бюджет RNG order-sensitive: первые два значения — инициатива (mage/gob),
> дальше 5d8 пула. Подогнать список `rolls`, если `enc.start()` потребляет
> инициативу иначе (см. сложившийся порядок в других e2e). Если Sleep —
> AREA at_point, проверить, что `params.target_point` корректно резолвит зону
> (radius 5 → клетка цели). При расхождении сигнатур — поправить вызов, сохранив
> проверку `gob.has_condition(UNCONSCIOUS)`.

- [ ] **Step 2: Запустить — падает/зелёно**

Run: `python3 -m pytest tests/e2e/test_control_spells_play.py -q`
Expected: PASS после подгонки RNG-бюджета (итеративно: если `can_perform_against`
возвращает Forbidden — проверить дальность/слот; если пул не усыпил — проверить
порядок кубов).

- [ ] **Step 3: Документация SPELLS.md**

В `docs/SPELLS.md` в перечень эффектов добавить `CONTROL` и раздел про
контроль-заклинания: модель `condition`/`hp_pool_dice`/триггеры; `OngoingEffectTracker`
и три триггера снятия; Sleep (пул 5d8, пробуждение) / Hold Person (WIS-спасбросок,
концентрация, повторный спасбросок). Отметить упрощение: ограничение «гуманоид»
для Hold Person отложено (нет типа существа).

- [ ] **Step 4: Документация ROADMAP.md**

В `docs/ROADMAP.md` отметить веху **T2 ✅** (контроль-заклинания + OngoingEffectTracker,
фикс уровней fireball/lightning_bolt), обновить под-пункт T2 из ⏳ в ✅; T3/T4 — ⏳.

- [ ] **Step 5: Финальная регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m pytest tests/unit/test_layering.py -q`
Expected: всё зелёно, guard слоёв проходит.

```bash
git add tests/e2e/test_control_spells_play.py docs/SPELLS.md docs/ROADMAP.md
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "test+docs(t2): e2e контроль-заклинаний + SPELLS.md/ROADMAP"
```

---

## Self-Review (выполнено при написании плана)

**Покрытие спека:**
- §3.1 модель CONTROL — T2-1 ✅
- §3.2 события — T2-2 ✅
- §3.3 ControlSpellHandler — T2-4 ✅
- §3.4 OngoingEffectTracker + roll_saving_throw_raw — T2-3 ✅
- §3.5 wiring + пропуск инкап. — T2-5 ✅
- §3.6 контент + фикс уровней — T2-6 ✅
- §3.7 рендер — T2-6 ✅
- §5 тесты (юнит/интеграция/e2e) — распределены по задачам ✅
- §6 инварименты — закрыты валидацией (T2-1), снятие точного набора (T2-3), пропуск инкап. (T2-5), guard слоёв (T2-7).

**Согласованность типов:** `ConditionApplied(caster_id, target_id, spell_id, conditions, ends_on_damage, repeat_save_ability, save_dc, concentration)` — одинаково в T2-2 (объявление), T2-3 (чтение в трекере), T2-4 (публикация в хендлере). `OngoingEffectTracker(participants, event_bus, *, dice_roller, modifier_applier)` — одинаково в T2-3/T2-5/T2-7. `roll_saving_throw_raw(actor, ability, *, dc, dice_roller, modifier_applier, tags)` — T2-3 объявление, использование в трекере.

**Плейсхолдеры:** места «сверить сигнатуру» (TurnContext в T2-4, deps-переменная в T2-5, RNG-бюджет в T2-7) — это указания свериться с существующим кодом перед написанием, логика и проверки приведены полностью; не заглушки фич.

**Известные риски, требующие сверки на месте (не блокеры):**
1. Точная сигнатура `TurnContext` (поля) — для тестового харнесса T2-4.
2. Имя переменной зависимостей в `cli/app.py` / `tui/app.py` (deps vs services).
3. `RollPurpose.UTILITY` — добавить член enum, если отсутствует.
4. Порядок потребления RNG в `enc.start()` — для e2e-бюджета T2-7.
