# X0 — время и сессия Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`).

**Goal:** Единый источник игрового времени (`GameClock` в раундах) + `Duration` на эффектах + истечение эффектов по времени + `GameSession` над `Encounter`, чтобы баффы/состояния истекали по часам и время переживало границу боёв.

**Architecture:** `Duration` (domain VO) и `GameClock` (domain entity) — чистые, канон в раундах (1 мин=10, 1 ч=600). Источник эффекта вычисляет `expires_at_round` через часы и кладёт в событие; `OngoingEffectTracker` (clock-aware) сравнивает на `RoundEnded` и снимает истёкшее. `GameSession` держит партию+часы+общий трекер поверх `Encounter`; часы двигаются на границе раунда. Длительность **дополняет** существующие триггеры (урон/спасбросок/срыв концентрации), не заменяет.

**Tech Stack:** Python 3.12, frozen dataclasses (domain), pydantic v2 (события — frozen BaseModel), pytest, mypy strict, ruff. Guard `tests/unit/test_layering.py` (domain НЕ импортирует application). Коммиты: `Maxim Lokotkov` / `anticrab@users.noreply.github.com`. Доки/комментарии — русский.

**CI-гейты (гонять ВСЕ после каждой задачи):** `python3 -m ruff check src tests` · `python3 -m ruff format --check src tests` · `python3 -m mypy src` (стабы: `pip install --break-system-packages ".[dev]"`) · `python3 -m pytest -q`. После `ruff format` — перепроверять mypy.

---

## Карта файлов

| Файл | Изменение |
|------|-----------|
| `src/dnd/domain/values/duration.py` | **Create** — `DurationUnit` + `Duration` |
| `src/dnd/domain/entities/game_clock.py` | **Create** — `GameClock` |
| `src/dnd/application/dto/engine_event.py` | `ConditionApplied.expires_at_round`; новые `BuffApplied`/`BuffExpired` |
| `src/dnd/application/engine/effects/ongoing_effect_tracker.py` | clock-aware: `expires_at_round`, sweep на `RoundEnded`, buff-expiry |
| `src/dnd/domain/values/spell.py` | `Spell.duration: Duration` + валидация |
| `src/dnd/infrastructure/content/yaml_spell_repository.py` | парсинг `duration` |
| `data/content/spells.yaml` | `duration` у заклинаний |
| `src/dnd/application/engine/turn_context.py` | поле `clock: GameClock` |
| `src/dnd/application/engine/spells/handlers.py` | хендлеры кладут `expires_at_round` |
| `src/dnd/application/engine/encounter.py` | `clock` в deps; `clock.advance(1)` на границе раунда |
| `src/dnd/application/engine/game_session.py` | **Create** — `GameSession` |
| `src/dnd/composition.py` | `clock` в services; сборка `GameSession` |
| `src/dnd/interfaces/cli/app.py`, `tui/app.py` | передать `clock` трекеру |
| `docs/TIME.md` | **Create**; ENCOUNTER/SPELLS/ROADMAP — правки |

Все новые поля — с дефолтами (backward-compat): `Spell.duration=INSTANT`, `ConditionApplied.expires_at_round=None`, `tracker.clock=None`, `TurnContext.clock` через default_factory.

---

# X0-1 — `Duration` (значение игрового времени)

**Files:** Create `src/dnd/domain/values/duration.py`; Test `tests/unit/domain/test_duration.py`.

- [ ] **Step 1: Падающий тест**

```python
"""Duration — игровое время в раундах (X0)."""
from __future__ import annotations

import pytest

from dnd.domain.values.duration import Duration, DurationUnit


def test_instant_is_zero_rounds() -> None:
    assert Duration.instant().to_rounds() == 0
    assert Duration.instant().unit is DurationUnit.INSTANT


def test_rounds_minutes_hours_conversion() -> None:
    assert Duration.rounds(3).to_rounds() == 3
    assert Duration.minutes(1).to_rounds() == 10
    assert Duration.hours(1).to_rounds() == 600


def test_unbounded_durations_are_none() -> None:
    assert Duration(DurationUnit.PERMANENT).to_rounds() is None
    assert Duration(DurationUnit.UNTIL_ENCOUNTER_END).to_rounds() is None


def test_concentration_cap_in_minutes() -> None:
    assert Duration.concentration(cap_min=1).to_rounds() == 10
    assert Duration.concentration(cap_min=10).to_rounds() == 100
    # Без потолка — длится, пока держится концентрация (счётного предела нет).
    assert Duration.concentration().to_rounds() is None


def test_positive_amount_required() -> None:
    with pytest.raises(ValueError, match="amount"):
        Duration(DurationUnit.ROUNDS, 0)
```

- [ ] **Step 2: Запустить — падает** (`ImportError`).

- [ ] **Step 3: Реализовать**

Create `src/dnd/domain/values/duration.py`:
```python
"""Длительность игрового эффекта (X0). Канон — раунд (PHB-2024: 1 раунд = 6 c;
1 мин = 10 раундов; 1 ч = 600). Минуты/часы конвертируются в раунды в одном
месте — потребители (часы, трекер) работают только с раундами.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class DurationUnit(StrEnum):
    INSTANT = "instant"
    ROUNDS = "rounds"
    MINUTES = "minutes"
    HOURS = "hours"
    CONCENTRATION = "concentration"  # пока держится концентрация (+ потолок мин)
    UNTIL_ENCOUNTER_END = "until_encounter_end"
    PERMANENT = "permanent"


@dataclass(frozen=True, slots=True)
class Duration:
    """Длительность эффекта. ``amount``: число для ROUNDS/MINUTES/HOURS; потолок
    в минутах для CONCENTRATION (0 = без счётного потолка)."""

    unit: DurationUnit
    amount: int = 0

    ROUNDS_PER_MINUTE: ClassVar[int] = 10
    ROUNDS_PER_HOUR: ClassVar[int] = 600

    def __post_init__(self) -> None:
        if self.unit in (DurationUnit.ROUNDS, DurationUnit.MINUTES, DurationUnit.HOURS):
            if self.amount <= 0:
                raise ValueError(f"{self.unit} requires amount > 0, got {self.amount}")
        if self.amount < 0:
            raise ValueError(f"duration amount must be >= 0, got {self.amount}")

    def to_rounds(self) -> int | None:
        """Длительность в раундах. ``None`` — нет счётного предела
        (PERMANENT / UNTIL_ENCOUNTER_END / CONCENTRATION без потолка)."""
        match self.unit:
            case DurationUnit.INSTANT:
                return 0
            case DurationUnit.ROUNDS:
                return self.amount
            case DurationUnit.MINUTES:
                return self.amount * self.ROUNDS_PER_MINUTE
            case DurationUnit.HOURS:
                return self.amount * self.ROUNDS_PER_HOUR
            case DurationUnit.CONCENTRATION:
                return self.amount * self.ROUNDS_PER_MINUTE if self.amount > 0 else None
            case _:
                return None

    # --- конструкторы-удобства ---
    @classmethod
    def instant(cls) -> Duration:
        return cls(DurationUnit.INSTANT)

    @classmethod
    def rounds(cls, n: int) -> Duration:
        return cls(DurationUnit.ROUNDS, n)

    @classmethod
    def minutes(cls, n: int) -> Duration:
        return cls(DurationUnit.MINUTES, n)

    @classmethod
    def hours(cls, n: int) -> Duration:
        return cls(DurationUnit.HOURS, n)

    @classmethod
    def concentration(cls, cap_min: int = 0) -> Duration:
        return cls(DurationUnit.CONCENTRATION, cap_min)


__all__ = ["Duration", "DurationUnit"]
```

- [ ] **Step 4: Зелёно + гейты + коммит**

Run: `python3 -m pytest tests/unit/domain/test_duration.py -q && python3 -m ruff format src/dnd/domain/values/duration.py tests/unit/domain/test_duration.py && python3 -m ruff check src tests && python3 -m mypy src`
```bash
git add src/dnd/domain/values/duration.py tests/unit/domain/test_duration.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(x0): Duration — игровое время в раундах (мин/час → раунды)"
```

---

# X0-2 — `GameClock` (часы в раундах)

**Files:** Create `src/dnd/domain/entities/game_clock.py`; Test `tests/unit/domain/test_game_clock.py`.

- [ ] **Step 1: Падающий тест**

```python
"""GameClock — монотонные игровые часы в раундах (X0)."""
from __future__ import annotations

import pytest

from dnd.domain.entities.game_clock import GameClock
from dnd.domain.values.duration import Duration


def test_starts_at_zero_and_advances() -> None:
    clock = GameClock()
    assert clock.now_round == 0
    clock.advance(1)
    assert clock.now_round == 1
    clock.advance_minutes(1)  # +10
    assert clock.now_round == 11
    clock.advance_hours(1)  # +600
    assert clock.now_round == 611


def test_advance_rejects_negative() -> None:
    with pytest.raises(ValueError, match="rounds"):
        GameClock().advance(-1)


def test_expires_at_counts_from_now() -> None:
    clock = GameClock()
    clock.advance(5)
    assert clock.expires_at(Duration.minutes(1)) == 15  # 5 + 10
    assert clock.expires_at(Duration.instant()) == 5
    # Бесконечная длительность → None (не истекает по часам).
    assert clock.expires_at(Duration.concentration()) is None
```

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Реализовать**

Create `src/dnd/domain/entities/game_clock.py`:
```python
"""GameClock (X0) — единые игровые часы. Канон — раунд. Бой двигает +1 раунд на
границе раунда; исследование (X) будет двигать по стоимости действий. Монотонны
(только вперёд)."""
from __future__ import annotations

from dnd.domain.values.duration import Duration


class GameClock:
    """Счётчик игрового времени в раундах (старт 0, неубывающий)."""

    def __init__(self, now_round: int = 0) -> None:
        if now_round < 0:
            raise ValueError(f"now_round must be >= 0, got {now_round}")
        self.now_round = now_round

    def advance(self, rounds: int) -> None:
        if rounds < 0:
            raise ValueError(f"advance requires rounds >= 0, got {rounds}")
        self.now_round += rounds

    def advance_minutes(self, n: int) -> None:
        self.advance(n * Duration.ROUNDS_PER_MINUTE)

    def advance_hours(self, n: int) -> None:
        self.advance(n * Duration.ROUNDS_PER_HOUR)

    def expires_at(self, duration: Duration) -> int | None:
        """Раунд, на котором эффект истечёт: ``now_round + duration``. ``None`` —
        длительность без счётного предела (эффект не снимается по часам)."""
        rounds = duration.to_rounds()
        return None if rounds is None else self.now_round + rounds


__all__ = ["GameClock"]
```

- [ ] **Step 4: Зелёно + гейты + коммит**

Run: `python3 -m pytest tests/unit/domain/test_game_clock.py -q && python3 -m ruff format ... && python3 -m ruff check src tests && python3 -m mypy src`
```bash
git add src/dnd/domain/entities/game_clock.py tests/unit/domain/test_game_clock.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(x0): GameClock — монотонные игровые часы в раундах"
```

---

# X0-3 — clock-aware истечение состояний

**Files:** Modify `application/dto/engine_event.py` (`ConditionApplied.expires_at_round`); `application/engine/effects/ongoing_effect_tracker.py`; Test `tests/unit/application/test_effect_duration.py`.

- [ ] **Step 1: Падающий тест**

```python
"""Истечение состояний по часам (X0-3)."""
from __future__ import annotations

from dnd.application.dto.engine_event import (
    ConditionApplied,
    ConditionRemoved,
    EngineEvent,
    RoundEnded,
)
from dnd.application.engine.effects.ongoing_effect_tracker import OngoingEffectTracker
from dnd.composition import build_scripted_runtime_services
from dnd.domain.conditions.builtin import PARALYZED, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.creature import Creature
from dnd.domain.entities.game_clock import GameClock
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import ConditionId, CreatureId, SpellId


def _victim() -> Creature:
    return Creature.create(
        id_=CreatureId("v"), name="v",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=10, speed_ft=30,
    )


def test_condition_expires_when_clock_passes_deadline() -> None:
    services, bus, _ = build_scripted_runtime_services(rolls=[])
    reg = ConditionRegistry(); register_default_conditions(reg)
    victim = _victim()
    victim.apply_condition(PARALYZED)
    clock = GameClock()
    tracker = OngoingEffectTracker(
        {victim.id: victim}, bus,
        dice_roller=services.dice_roller, modifier_applier=services.modifier_applier,
        condition_service=services.condition_service, clock=clock,
    )
    tracker.subscribe()
    removed: list[ConditionRemoved] = []
    bus.subscribe(ConditionRemoved, removed.append)

    # Эффект истекает на раунде 2.
    bus.publish(ConditionApplied(
        caster_id=CreatureId("c"), target_id=victim.id, spell_id=SpellId("hold_person"),
        conditions=frozenset({PARALYZED}), concentration=True, expires_at_round=2,
    ))

    # Раунд 1: ещё держится.
    clock.advance(1)
    bus.publish(RoundEnded(round_number=1))
    assert victim.has_condition(PARALYZED)

    # Раунд 2: дедлайн достигнут → снято с reason="duration".
    clock.advance(1)
    bus.publish(RoundEnded(round_number=2))
    assert not victim.has_condition(PARALYZED)
    assert removed and removed[-1].reason == "duration"
```

- [ ] **Step 2: Запустить — падает** (`ConditionApplied` без `expires_at_round`; `OngoingEffectTracker` без `clock`).

- [ ] **Step 3: Поле в событии**

В `application/dto/engine_event.py`, класс `ConditionApplied`, добавить поле:
```python
    concentration: bool = False
    expires_at_round: int | None = None  # X0: дедлайн снятия по часам (None = не по времени)
```

- [ ] **Step 4: clock-aware трекер**

В `ongoing_effect_tracker.py`:
1. В `OngoingConditionEffect` добавить поле `expires_at_round: int | None`.
2. Импорт `RoundEnded` в блок событий; в `TYPE_CHECKING` — `from dnd.domain.entities.game_clock import GameClock`.
3. `__init__` — добавить `clock: GameClock | None = None`, сохранить `self._clock = clock`.
4. `_on_applied` — прокинуть `expires_at_round=event.expires_at_round`.
5. `subscribe()` — добавить `self._bus.subscribe(RoundEnded, self._on_round_ended)`.
6. Новый метод:
```python
    def _on_round_ended(self, event: RoundEnded) -> None:
        if self._clock is None:
            return
        now = self._clock.now_round
        for effect in list(self._effects):
            if effect.expires_at_round is not None and effect.expires_at_round <= now:
                self._remove(effect, reason="duration")
```

- [ ] **Step 5: Зелёно + регрессия + коммит**

Run: `python3 -m pytest tests/unit/application/test_effect_duration.py tests/unit/application/test_ongoing_effect_tracker.py -q && python3 -m ruff format src tests && python3 -m ruff check src tests && python3 -m mypy src`
Expected: PASS (старые тесты трекера зелёные — `clock` опционален).
```bash
git add src/dnd/application/dto/engine_event.py src/dnd/application/engine/effects/ongoing_effect_tracker.py tests/unit/application/test_effect_duration.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(x0): истечение состояний по часам (ConditionApplied.expires_at_round + sweep на RoundEnded)"
```

---

# X0-4 — истечение баффов-модификаторов по времени

**Files:** Modify `application/dto/engine_event.py` (`BuffApplied`/`BuffExpired`); `ongoing_effect_tracker.py`; Test (дописать `test_effect_duration.py`).

- [ ] **Step 1: Падающий тест** (дописать)

```python
def test_modifier_buff_expires_by_clock() -> None:
    from dnd.application.dto.engine_event import BuffApplied, BuffExpired
    from dnd.domain.values.modifiers import (
        Modifier, ModifierSourceKind, ModifierTargetKind, NumericBonusEffect,
    )

    services, bus, _ = build_scripted_runtime_services(rolls=[])
    mods = services.modifier_applier
    clock = GameClock()
    tracker = OngoingEffectTracker(
        {}, bus, dice_roller=services.dice_roller, modifier_applier=mods,
        condition_service=services.condition_service, clock=clock,
    )
    tracker.subscribe()
    owner = CreatureId("hero")
    src = f"item:potion:{owner}"
    mods.add(Modifier(
        source_id=src, source_kind=ModifierSourceKind.ITEM,
        target_kind=ModifierTargetKind.SAVING_THROW, effect=NumericBonusEffect(bonus=2),
        owner_id=owner, stack_key=src,
    ))
    expired: list[BuffExpired] = []
    bus.subscribe(BuffExpired, expired.append)

    bus.publish(BuffApplied(owner_id=owner, source_id=src, expires_at_round=1))
    clock.advance(1)
    bus.publish(RoundEnded(round_number=1))

    assert expired and expired[-1].source_id == src
    # Модификатор снят.
    assert mods.collect(owner_id=owner, target_kind=ModifierTargetKind.SAVING_THROW) == ()
```

> Проверить точное имя `NumericBonusEffect` и сигнатуру `collect`/`Modifier` в `domain/values/modifiers.py`; при расхождении подогнать конструктор в тесте.

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: События `BuffApplied`/`BuffExpired`**

В `engine_event.py`:
```python
class BuffApplied(EngineEvent):
    """Наложен бафф-модификатор с дедлайном по часам (X0)."""
    event_type: ClassVar[str] = "buff.applied"
    owner_id: CreatureId
    source_id: str
    expires_at_round: int | None = None


class BuffExpired(EngineEvent):
    """Бафф-модификатор снят по истечении времени (X0)."""
    event_type: ClassVar[str] = "buff.expired"
    owner_id: CreatureId
    source_id: str
```

- [ ] **Step 4: Трекер ведёт сроки баффов**

В `ongoing_effect_tracker.py`:
1. Импорт `BuffApplied`, `BuffExpired`.
2. В `__init__`: `self._buff_expiry: dict[str, tuple[CreatureId, int]] = {}` (source_id → (owner, deadline)).
3. `subscribe()`: `self._bus.subscribe(BuffApplied, self._on_buff_applied)`.
4. Методы:
```python
    def _on_buff_applied(self, event: BuffApplied) -> None:
        if event.expires_at_round is not None:
            self._buff_expiry[event.source_id] = (event.owner_id, event.expires_at_round)
```
5. В `_on_round_ended` (после снятия состояний) добавить sweep баффов:
```python
        for source_id, (owner_id, deadline) in list(self._buff_expiry.items()):
            if deadline <= now:
                self._mods.remove_by_source(source_id)
                del self._buff_expiry[source_id]
                self._bus.publish(BuffExpired(owner_id=owner_id, source_id=source_id))
```

- [ ] **Step 5: Зелёно + гейты + коммит**

Run: `python3 -m pytest tests/unit/application/test_effect_duration.py -q && python3 -m ruff format src tests && python3 -m ruff check src tests && python3 -m mypy src`
```bash
git add src/dnd/application/dto/engine_event.py src/dnd/application/engine/effects/ongoing_effect_tracker.py tests/unit/application/test_effect_duration.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(x0): истечение баффов-модификаторов по часам (BuffApplied/BuffExpired + sweep)"
```

---

# X0-5 — `Spell.duration` + clock в TurnContext + хендлеры + контент

**Files:** Modify `domain/values/spell.py`, `infrastructure/content/yaml_spell_repository.py`, `data/content/spells.yaml`, `application/engine/turn_context.py`, `application/engine/spells/handlers.py`; Test `tests/unit/domain/test_spell_duration.py`, дописать handler-тесты.

- [ ] **Step 1: Падающий тест (Spell.duration)**

```python
"""Spell.duration (X0-5)."""
from __future__ import annotations

from dnd.domain.values.duration import Duration, DurationUnit
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository
from pathlib import Path


def test_default_duration_is_instant() -> None:
    from dnd.domain.values.spell import Spell, SpellEffect, TargetingSpec, TargetKind
    from dnd.domain.values.ids import SpellId
    from dnd.domain.values.damage import DamageType
    s = Spell(
        id=SpellId("x"), name="x", level=1, school="evocation",
        effect=SpellEffect.AUTO, targeting=TargetingSpec(kind=TargetKind.SINGLE),
        range_ft=30, description="", dice="1d4", damage_type=DamageType.FORCE,
    )
    assert s.duration == Duration.instant()


def test_bless_duration_parsed_from_yaml() -> None:
    repo = YamlSpellRepository(Path("data/content/spells.yaml"))
    bless = repo.load(__import__("dnd.domain.values.ids", fromlist=["SpellId"]).SpellId("bless"))
    assert bless.duration.unit is DurationUnit.CONCENTRATION
    assert bless.duration.to_rounds() == 10  # 1 мин концентрации
```

> Сверить точный id заклинания Bless и API `YamlSpellRepository.load` (как в существующих тестах репозитория заклинаний); при необходимости упростить второй тест до прямой проверки парсера.

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: Поле `Spell.duration`**

В `spell.py`: импорт `from dnd.domain.values.duration import Duration`; в `Spell` добавить
```python
    duration: Duration = Duration.instant()
```
(после `condition_repeat_save`). Дефолт INSTANT — backward-compat.

- [ ] **Step 4: Парсинг в репозитории**

В `yaml_spell_repository.py` `_parse`: распарсить опциональный `duration`:
```python
        raw_dur = entry.get("duration")
        if raw_dur is None:
            duration = Duration.instant()
        else:
            duration = Duration(DurationUnit(raw_dur["unit"]), int(raw_dur.get("amount", 0)))
```
и передать `duration=duration` в конструктор `Spell(...)` (импорты `Duration`, `DurationUnit`).

- [ ] **Step 5: clock в TurnContext**

В `turn_context.py`: рантайм-импорт `from dnd.domain.entities.game_clock import GameClock`; в dataclass добавить поле (после `turn_number_in_round`):
```python
    clock: GameClock = field(default_factory=GameClock)
```
(default_factory — чтобы ручная сборка ctx в тестах не ломалась; реальный общий clock проставит Encounter в X0-6.)

- [ ] **Step 6: Хендлеры кладут `expires_at_round`**

В `handlers.py`:
- `ControlSpellHandler`: при публикации `ConditionApplied(...)` добавить
  `expires_at_round=ctx.clock.expires_at(spell.duration)`.
- `BuffSpellHandler`: после `ctx.modifier_applier.add(...)` опубликовать
  `BuffApplied(owner_id=target.id, source_id=<source_id баффа>, expires_at_round=ctx.clock.expires_at(spell.duration))` (импорт `BuffApplied`). Для концентрации `source_id` = `concentration_source(caster.id)`.

- [ ] **Step 7: Контент длительностей**

В `data/content/spells.yaml` добавить `duration` (PHB-2024):
```yaml
# bless:
  duration: { unit: concentration, amount: 1 }
# shield_of_faith:
  duration: { unit: concentration, amount: 10 }
# hold_person:
  duration: { unit: concentration, amount: 1 }
# урон/лечение (fireball, cure wounds, magic missile, ...) — duration не указывать (INSTANT по умолчанию)
```

- [ ] **Step 8: Зелёно + регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests`
Expected: PASS (обновить тесты заклинаний/репозитория, если сверяют точный конструктор `Spell`).
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(x0): Spell.duration + clock в TurnContext + хендлеры кладут expires_at_round + контент"
```

---

# X0-6 — `GameSession` над `Encounter` + проводка

**Files:** Modify `application/engine/encounter.py` (clock в deps + advance на границе раунда); Create `application/engine/game_session.py`; Modify `composition.py`, `interfaces/cli/app.py`, `interfaces/tui/app.py`; Test `tests/integration/engine/test_game_session.py`.

- [ ] **Step 1: Падающий тест**

```python
"""GameSession: часы двигаются по раундам, эффекты переживают границу боя (X0-6)."""
from __future__ import annotations

from dnd.application.engine.game_session import GameSession
from dnd.domain.entities.game_clock import GameClock


def test_session_holds_clock_and_advances_on_round_end() -> None:
    from dnd.composition import build_default_runtime_services
    services = build_default_runtime_services()
    clock = GameClock()
    session = GameSession(party={}, clock=clock, services=services)
    # Часы стартуют с 0; имитируем границу раунда боя.
    from dnd.application.dto.engine_event import RoundEnded
    services.event_bus.publish(RoundEnded(round_number=1))
    assert clock.now_round == 1
```

> Конкретная форма `GameSession.__init__` и `begin_encounter` — подогнать под существующую сборку (Encounter принимает `EncounterDependencies` = services.with_battlefield(bf) + participants/factions). Тест проверяет ключевой инвариант: сессия двигает общие часы на `RoundEnded`.

- [ ] **Step 2: Запустить — падает.**

- [ ] **Step 3: clock в Encounter deps + advance**

- В `encounter.py` `EncounterDependencies` добавить `clock: GameClock` (с дефолтом `field(default_factory=GameClock)` для backward-compat). В `with_battlefield` (composition) пробросить clock.
- В `start_turn` `TurnContext(...)` добавить `clock=self._deps.clock`.
- В `_advance_turn_pointer` перед публикацией `RoundEnded(...)` (или сразу после) — `self._deps.clock.advance(1)` (одно продвижение на закрытый раунд). Убедиться, что `RoundEnded` публикуется ОДИН раз на раунд (так и есть).

> Чтобы не было двойного advance, продвигает часы ТОЛЬКО `Encounter` (трекер лишь читает). `GameSession` отдаёт свой `clock` в `EncounterDependencies`, поэтому это те же часы.

- [ ] **Step 4: `GameSession`**

Create `application/engine/game_session.py`:
```python
"""GameSession (X0) — рантайм кампании поверх боёв: партия + общие часы + шина +
общий OngoingEffectTracker. Бой (Encounter) создаётся из сессии и делит её часы;
по EncounterEnded управление возвращается в сессию, часы и активные эффекты
сохраняются. Режим исследования — этап X (сейчас сессия оборачивает бой)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.entities.game_clock import GameClock

if TYPE_CHECKING:
    from collections.abc import Mapping
    from dnd.composition import EncounterRuntimeServices
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ids import CreatureId


class GameSession:
    def __init__(
        self,
        *,
        party: Mapping[CreatureId, Creature],
        clock: GameClock,
        services: EncounterRuntimeServices,
    ) -> None:
        self.party = dict(party)
        self.clock = clock
        self._services = services
```

> Полноценный `begin_encounter` (создание Encounter из партии+врагов с общими часами/трекером) добавить здесь же по образцу текущей сборки боя в `interfaces/cli/app.py`/`tui/app.py`. Главное X0: общие часы и трекер живут в сессии, а не пересоздаются на бой.

- [ ] **Step 5: Проводка composition + интерфейсы**

- `composition.py`: `EncounterRuntimeServices`/`build_*` — создать `clock` и положить в `with_battlefield` (`EncounterDependencies(clock=...)`). Добавить `build_default_session()`/фабрику `GameSession` при необходимости.
- `interfaces/cli/app.py` и `tui/app.py`: при создании `OngoingEffectTracker(...)` передать `clock=<общие часы>` (тот же объект, что в `EncounterDependencies`). Так трекер снимает истёкшее по тем же часам, что двигает Encounter.

- [ ] **Step 6: Зелёно + регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests && python3 -m pytest tests/unit/test_layering.py -q`
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(x0): GameSession над Encounter + общие часы (advance на RoundEnded) + проводка"
```

---

# X0-7 — документация + аудит-смок

**Files:** Create `docs/TIME.md`; Modify `docs/ENCOUNTER.md`, `docs/SPELLS.md`, `docs/ROADMAP.md`; Test `tests/integration/engine/test_time_smoke.py`.

- [ ] **Step 1: Смок-тест «концентрация-бафф истекает по потолку»**

```python
"""Аудит-смок X0: бафф концентрации истекает по временно́му потолку (X0-7)."""
from __future__ import annotations

# Сценарий: наложить бафф с duration concentration(1 мин = 10 раундов);
# продвинуть часы на 10 раундов через RoundEnded; убедиться, что BuffExpired
# опубликован и модификатор снят (даже без срыва концентрации).
# Сборка — как в test_effect_duration (services + tracker + clock).
```

Реализовать по образцу `test_effect_duration.py`: `BuffApplied(expires_at_round=10)`, 10× (`clock.advance(1)` + `RoundEnded`), проверить `BuffExpired` и пустой `collect`.

- [ ] **Step 2: Запустить — PASS** (логика уже есть из X0-4; смок фиксирует сценарий).

- [ ] **Step 3: Доки**

`docs/TIME.md`: модель времени (раунд=6 c, 1 мин=10, 1 ч=600), `Duration`/`DurationUnit`, `GameClock` (монотонность, advance), истечение состояний (`expires_at_round` в `ConditionApplied`, sweep на `RoundEnded`) и баффов (`BuffApplied`/`BuffExpired`), `GameSession` (общие часы поверх боёв; исследование — задел X), правило «длительность дополняет триггеры». `ENCOUNTER.md`: clock двигается на границе раунда. `SPELLS.md`: `duration` у заклинаний (Bless/Shield of Faith/Hold Person concentration-потолки). `ROADMAP.md`: отметить **X0 ✅** (часы/длительности; долг T2 закрыт в боевой части); кросс-локационное время — остаток X.

- [ ] **Step 4: Финальная регрессия + коммит**

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests && python3 -m ruff format --check src tests`
```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "docs(x0): TIME.md + ENCOUNTER/SPELLS/ROADMAP + аудит-смок (этап X0 завершён)"
```

---

## Self-Review (выполнено)

**Покрытие спека:** §2 Duration — X0-1; §3 GameClock — X0-2; §4.1 истечение состояний — X0-3; §4.2 истечение баффов — X0-4; §5 Spell.duration+контент+хендлеры — X0-5; §6 GameSession+проводка — X0-6; §7 проводка composition/GameRunner — X0-5/6; §8 инварианты (часы монотонны, длительность=данные, триггеры+время независимы, backward-compat) — X0-1/3/5; §9 декомпозиция — задачи 1:1.

**Согласованность типов/имён:** `Duration.instant/rounds/minutes/hours/concentration`, `to_rounds()->int|None`, `GameClock.now_round/advance/advance_minutes/advance_hours/expires_at`, `ConditionApplied.expires_at_round`, `OngoingConditionEffect.expires_at_round`, `OngoingEffectTracker(..., clock=None)` + `_on_round_ended`, `BuffApplied(owner_id, source_id, expires_at_round)`/`BuffExpired(owner_id, source_id)`, `TurnContext.clock`, `EncounterDependencies.clock`, `GameSession(party, clock, services)` — единообразно между задачами.

**Плейсхолдеры:** места «сверить точное имя/API» (`NumericBonusEffect`/`collect`, `YamlSpellRepository.load`, `begin_encounter`) — указания свериться с существующим кодом при реализации; логика и тесты приведены целиком, не заглушки.

**Риски:** (1) `clock` опционален в трекере → старые call-sites (cli/tui app.py) не ломаются, но без clock не истекают по времени — в X0-6 явно передать. (2) двойной advance часов исключён: двигает только Encounter, трекер читает. (3) тесты репозитория/заклинаний могут сверять конструктор `Spell` — обновить под новое поле. (4) `RoundEnded` публикуется один раз на раунд — проверено в `_advance_turn_pointer`.
```
