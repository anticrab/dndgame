# R1 — Прогрессия и level-up в бою: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать персонажу уровни/опыт с кульминацией — level-up в середине боя (HP/proficiency/spell-slots/фичи), плюс data-driven классы Воин/Плут L1–3 и фичи Improved Critical / Sneak Attack / Second Wind / Action Surge.

**Architecture:** Классы — данные (YAML) + `ClassRepository`; фичи — `FeatureRegistry` (feature_id → хендлер), как `SpellEffectRegistry`. Прогрессия/XP/level-up/rest — сервисы в `application/engine/progression/`. Отдых — полноценная абстракция `RestKind`/`RechargeOn`/`RestService`, в R1 триггерится «между боями» (SHORT на старте encounter). Поля `level`/`xp`/`character_class` — на `Creature` (без Character/Monster split).

**Tech Stack:** Python 3.12, pydantic v2 (события `EngineEvent` frozen), dataclasses (frozen/slots) для domain VO, Textual TUI (модальный `LevelUpScreen`), pytest, mypy strict, ruff.

**Спек:** `docs/superpowers/specs/2026-05-25-r1-progression-design.md`. **Опора:** `docs/PROGRESSION.md`.

**Соглашения:**
- Инструменты: `python3 -m pytest -q`, `python3 -m mypy src`, `python3 -m ruff check src tests` (бинарники в `~/.local/bin`, но `python3 -m` надёжнее).
- Коммиты: `git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "..."`.
- Доки/комментарии — на русском. Запрещено: `git push`, `git reset --hard`, `git rebase`, `--no-verify`.
- После каждой задачи: `pytest -q` + `mypy src` + `ruff check src tests` + просмотр `git diff`. Особое внимание «протуханию»: крит-проверка (`attack.py`) и экономика действий (Action Surge refresh).

---

## Структура файлов

**Создаются:**
- `src/dnd/domain/values/rest.py` — `RestKind`, `RechargeOn`, `recharge_covers()`.
- `src/dnd/domain/values/class_progression.py` — `ClassLevel`, `ClassProgression`.
- `src/dnd/application/ports/class_repository.py` — `ClassRepository` Protocol.
- `src/dnd/infrastructure/content/yaml_class_repository.py` — `YamlClassRepository`.
- `data/content/classes.yaml` — fighter/rogue L1–3.
- `src/dnd/application/engine/progression/__init__.py`
- `src/dnd/application/engine/progression/xp_curve.py` — `XpCurve` + Fast/Standard/Milestone + `make_xp_curve`.
- `src/dnd/application/engine/progression/xp_award.py` — `XpAwardService`.
- `src/dnd/application/engine/progression/level_up.py` — `LevelUpService`, `LevelUpResult`.
- `src/dnd/application/engine/progression/rest.py` — `RestService`.
- `src/dnd/application/engine/features/__init__.py`
- `src/dnd/application/engine/features/registry.py` — `FeatureHandler`, `FeatureRegistry`, `ResourceSpec`, `ResourceRegistry`.
- `src/dnd/application/engine/features/handlers.py` — improved_critical, sneak_attack, second_wind, action_surge хендлеры.
- `src/dnd/application/engine/features/defaults.py` — `default_feature_registry()`, `default_resource_registry()`.
- `src/dnd/application/engine/actions/second_wind.py` — `SecondWindAction`, `SecondWindParams`.
- `src/dnd/application/engine/actions/action_surge.py` — `ActionSurgeAction`, `ActionSurgeParams`.
- `src/dnd/interfaces/tui/screens/level_up_screen.py` — модальный `LevelUpScreen`.
- Тесты: `tests/unit/domain/test_rest.py`, `tests/unit/domain/test_class_progression.py`, `tests/integration/content/test_yaml_class_repository.py`, `tests/unit/application/progression/test_xp_curve.py`, `tests/integration/engine/test_xp_award.py`, `tests/integration/engine/test_level_up.py`, `tests/integration/engine/test_rest_service.py`, `tests/integration/engine/test_features.py`, `tests/integration/engine/test_second_wind.py`, `tests/integration/engine/test_action_surge.py`, `tests/integration/tui/test_level_up_screen.py`.

**Изменяются:**
- `src/dnd/domain/entities/creature.py` — поля level/xp/character_class/challenge_rating/features/crit_range_min/resource_uses.
- `src/dnd/application/dto/engine_event.py` — `LevelUpReady`, `LeveledUp`.
- `src/dnd/application/dto/player_intent.py` — `SecondWindIntent`, `ActionSurgeIntent`.
- `src/dnd/application/engine/actions/attack.py` — крит по `crit_range_min`; хук Sneak Attack.
- `src/dnd/application/engine/encounter.py` — SHORT-rest на старте; подписка `XpAwardService`.
- `src/dnd/application/engine/game_runner.py` — роутинг SecondWind/ActionSurge интентов.
- `src/dnd/application/dto/templates.py` — `cr`, `character_class` в `MonsterTemplate`/spawn.
- `src/dnd/application/engine/builder.py` — проброс cr/класса.
- `data/content/monsters.yaml` — `cr` монстрам.
- `src/dnd/interfaces/cli/event_printer.py` — рендер LeveledUp.
- `docs/PROGRESSION.md`, `docs/ROADMAP.md`, `docs/ABILITIES.md`.

---

## Task R1-1: поля Creature + rest VO

**Files:**
- Create: `src/dnd/domain/values/rest.py`
- Modify: `src/dnd/domain/entities/creature.py`
- Test: `tests/unit/domain/test_rest.py`, `tests/unit/domain/test_creature_progression.py` (создать)

- [ ] **Step 1: Тест rest VO**

Создать `tests/unit/domain/test_rest.py`:

```python
"""R1-1: RestKind / RechargeOn + покрытие отдыхом."""
from __future__ import annotations

from dnd.domain.values.rest import RechargeOn, RestKind, recharge_covers


def test_short_rest_covers_short_and_encounter_and_turn() -> None:
    assert recharge_covers(RestKind.SHORT, RechargeOn.TURN)
    assert recharge_covers(RestKind.SHORT, RechargeOn.ENCOUNTER)
    assert recharge_covers(RestKind.SHORT, RechargeOn.SHORT_REST)
    assert not recharge_covers(RestKind.SHORT, RechargeOn.LONG_REST)


def test_long_rest_covers_everything() -> None:
    for r in RechargeOn:
        assert recharge_covers(RestKind.LONG, r)
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/unit/domain/test_rest.py -q`
Expected: FAIL — модуль `rest` отсутствует.

- [ ] **Step 3: Реализовать rest.py**

Создать `src/dnd/domain/values/rest.py`:

```python
"""Отдых: типы отдыха и политика восстановления ресурсов.

«Словарь» отдыха, на который опираются классовые фичи (поле ``recharge_on``)
и ``RestService``. В R1 отдых триггерится только «между боями» (SHORT на старте
encounter), но абстракция полная — будущие внебоевые short/long rest подключатся
к той же ``RestService`` без переделок.
"""
from __future__ import annotations

from enum import StrEnum


class RestKind(StrEnum):
    SHORT = "short"
    LONG = "long"


class RechargeOn(StrEnum):
    TURN = "turn"
    ENCOUNTER = "encounter"
    SHORT_REST = "short_rest"
    LONG_REST = "long_rest"


# Ранг «силы» отдыха: чем больше, тем больше восстанавливает.
_RANK: dict[RechargeOn, int] = {
    RechargeOn.TURN: 0,
    RechargeOn.ENCOUNTER: 1,
    RechargeOn.SHORT_REST: 2,
    RechargeOn.LONG_REST: 3,
}
_REST_RANK: dict[RestKind, int] = {
    RestKind.SHORT: _RANK[RechargeOn.SHORT_REST],
    RestKind.LONG: _RANK[RechargeOn.LONG_REST],
}


def recharge_covers(kind: RestKind, recharge: RechargeOn) -> bool:
    """Восстанавливает ли отдых ``kind`` ресурс с политикой ``recharge``.

    SHORT восстанавливает всё с recharge ≤ short_rest; LONG — всё."""
    return _RANK[recharge] <= _REST_RANK[kind]


__all__ = ["RechargeOn", "RestKind", "recharge_covers"]
```

- [ ] **Step 4: Прогнать — зелёные**

Run: `python3 -m pytest tests/unit/domain/test_rest.py -q`
Expected: PASS.

- [ ] **Step 5: Тест полей Creature**

Создать `tests/unit/domain/test_creature_progression.py`:

```python
"""R1-1: прогрессионные поля Creature (level/xp/класс/фичи/крит/ресурсы)."""
from __future__ import annotations

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores


def _c() -> Creature:
    return Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=10, armor_class=14, speed_ft=30,
    )


def test_progression_defaults() -> None:
    c = _c()
    assert c.level == 1 and c.xp == 0
    assert c.character_class is None
    assert c.challenge_rating == 0.0
    assert c.features == ()
    assert c.crit_range_min == 20
    assert c.resource_uses == {}


def test_progression_fields_mutable() -> None:
    c = _c()
    c.level = 2
    c.xp = 120
    c.character_class = "fighter"
    c.crit_range_min = 19
    c.resource_uses["second_wind"] = 1
    assert c.level == 2 and c.resource_uses["second_wind"] == 1
```

- [ ] **Step 6: Прогнать — падает**

Run: `python3 -m pytest tests/unit/domain/test_creature_progression.py -q`
Expected: FAIL — у `Creature` нет полей.

- [ ] **Step 7: Добавить поля Creature**

В `src/dnd/domain/entities/creature.py` найти блок с `known_spells: tuple[SpellId, ...] = ()` (около строки 262) и сразу ПОСЛЕ него (перед `ability_ids`) добавить:

```python
    # --- прогрессия (этап R1) ------------------------------------------
    level: int = 1
    """Уровень существа (PHB-2024). PC растут через LevelUpService; монстры — 1."""

    xp: int = 0
    """Накопленный опыт. Растёт через XpAwardService (за убийства/бонусы)."""

    character_class: str | None = None
    """ID класса ("fighter"/"rogue"), резолвится в ClassProgression через
    ClassRepository. None у монстров."""

    challenge_rating: float = 0.0
    """CR для награды XP (XP = CR*100, PROGRESSION.md §2). 0 у PC."""

    features: tuple[FeatureId, ...] = ()
    """Обретённые классовые фичи (feature_id). Применяются FeatureRegistry'ем
    при level-up; хранятся для inspect и повторного применения."""

    crit_range_min: int = 20
    """Минимальный d20 для крита. По умолчанию 20 (нат-20). Improved Critical
    (Чемпион) ставит 19 — AttackAction читает это поле."""

    resource_uses: dict[str, int] = field(default_factory=dict)
    """Счётчики ограниченных ресурсов фич (resource_key → осталось), напр.
    {"second_wind": 1, "action_surge": 1}. Восстанавливаются RestService'ом
    по политике recharge_on ресурса."""
```

Проверить, что `FeatureId` импортирован в creature.py. Если нет — добавить в существующий импорт из `dnd.domain.values.ids`:

```python
from dnd.domain.values.ids import CreatureId, FeatureId, SpellId
```
(добавь `FeatureId` к фактическому списку импорта ids в этом файле; не дублируй строку импорта.)

- [ ] **Step 8: Прогнать — зелёные + mypy + ruff + layering**

Run: `python3 -m pytest tests/unit/domain/test_creature_progression.py tests/unit/domain/test_rest.py tests/unit/test_layering.py -q && python3 -m mypy src/dnd/domain && python3 -m ruff check src/dnd/domain/values/rest.py src/dnd/domain/entities/creature.py tests/unit/domain/test_rest.py tests/unit/domain/test_creature_progression.py`
Expected: PASS, mypy/ruff чисто.

- [ ] **Step 9: Commit**

```bash
git add src/dnd/domain/values/rest.py src/dnd/domain/entities/creature.py tests/unit/domain/test_rest.py tests/unit/domain/test_creature_progression.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-1): прогрессионные поля Creature + rest VO (RestKind/RechargeOn)"
```

---

## Task R1-2: ClassProgression VO + classes.yaml + репозиторий

**Files:**
- Create: `src/dnd/domain/values/class_progression.py`, `src/dnd/application/ports/class_repository.py`, `src/dnd/infrastructure/content/yaml_class_repository.py`, `data/content/classes.yaml`
- Test: `tests/unit/domain/test_class_progression.py`, `tests/integration/content/test_yaml_class_repository.py`

- [ ] **Step 1: Тест VO**

Создать `tests/unit/domain/test_class_progression.py`:

```python
"""R1-2: ClassProgression / ClassLevel."""
from __future__ import annotations

import pytest

from dnd.domain.values.class_progression import ClassLevel, ClassProgression
from dnd.domain.values.ids import FeatureId


def _fighter() -> ClassProgression:
    return ClassProgression(
        id="fighter", name="Воин", hit_die="1d10",
        levels={
            1: ClassLevel(proficiency_bonus=2, features=(FeatureId("second_wind"),)),
            2: ClassLevel(proficiency_bonus=2, features=(FeatureId("action_surge"),)),
            3: ClassLevel(proficiency_bonus=2, features=(FeatureId("improved_critical"),)),
        },
    )


def test_level_lookup() -> None:
    f = _fighter()
    assert f.levels[1].proficiency_bonus == 2
    assert f.levels[2].features == (FeatureId("action_surge"),)


def test_requires_level_1() -> None:
    with pytest.raises(ValueError):
        ClassProgression(id="x", name="X", hit_die="1d8", levels={})


def test_hit_die_average() -> None:
    # ⌈(sides+1)/2⌉: d10 → 6, d8 → 5.
    assert _fighter().hit_die_average() == 6
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/unit/domain/test_class_progression.py -q`
Expected: FAIL — модуль отсутствует.

- [ ] **Step 3: Реализовать VO**

Создать `src/dnd/domain/values/class_progression.py`:

```python
"""ClassProgression — декларативная таблица прогрессии класса (этап R1).

Класс — **данные** (data/content/classes.yaml), а не код: LevelUpService читает
таблицу, FeatureRegistry исполняет фичи по id. Новый класс = строки в YAML +
(при необходимости) хендлеры фич, без правки движка.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil

from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import FeatureId


@dataclass(frozen=True, slots=True)
class ClassLevel:
    """Что даёт один уровень класса."""

    proficiency_bonus: int
    features: tuple[FeatureId, ...] = ()
    spell_slots: dict[int, int] | None = None   # None у не-кастеров (Воин/Плут)


@dataclass(frozen=True, slots=True)
class ClassProgression:
    """Таблица класса: кость хитов + что даётся на каждом уровне."""

    id: str
    name: str
    hit_die: str                                 # сериализованный DiceExpr, "1d10"
    levels: dict[int, ClassLevel] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if 1 not in self.levels:
            raise ValueError(f"class {self.id} must define level 1")
        DiceExpr.parse(self.hit_die)             # валидируем нотацию кости

    def hit_die_average(self) -> int:
        """Фикс. среднее кости хитов (PHB «fixed value»): ⌈(sides+1)/2⌉."""
        sides = DiceExpr.parse(self.hit_die).sides
        return ceil((sides + 1) / 2)


__all__ = ["ClassLevel", "ClassProgression"]
```

> Если у `DiceExpr` атрибут числа граней называется не `sides` — поправь на фактический (`grep -n "sides\|faces\|class DiceExpr" src/dnd/domain/values/dice.py`). Аналогично метод парсинга.

- [ ] **Step 4: Прогнать VO — зелёные**

Run: `python3 -m pytest tests/unit/domain/test_class_progression.py -q && python3 -m mypy src/dnd/domain/values/class_progression.py`
Expected: PASS.

- [ ] **Step 5: classes.yaml**

Создать `data/content/classes.yaml`:

```yaml
# Таблицы прогрессии классов (этап R1). Формат — YamlClassRepository.
# В R1 указаны только R1-фичи; R2 дополнит уровни Плута и остальные фичи.
- id: fighter
  name: "Воин"
  hit_die: "1d10"
  levels:
    1: { proficiency_bonus: 2, features: [second_wind] }
    2: { proficiency_bonus: 2, features: [action_surge] }
    3: { proficiency_bonus: 2, features: [improved_critical] }
- id: rogue
  name: "Плут"
  hit_die: "1d8"
  levels:
    1: { proficiency_bonus: 2, features: [sneak_attack] }
    2: { proficiency_bonus: 2, features: [] }
    3: { proficiency_bonus: 2, features: [] }
```

- [ ] **Step 6: Тест репозитория**

Создать `tests/integration/content/test_yaml_class_repository.py`:

```python
"""R1-2: YamlClassRepository грузит классы из classes.yaml."""
from __future__ import annotations

from pathlib import Path

from dnd.domain.values.ids import FeatureId
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository

_CLASSES = Path(__file__).resolve().parents[3] / "data" / "content" / "classes.yaml"


def _repo() -> YamlClassRepository:
    return YamlClassRepository(_CLASSES)


def test_loads_fighter_and_rogue() -> None:
    repo = _repo()
    assert set(repo.list_ids()) == {"fighter", "rogue"}


def test_fighter_levels() -> None:
    f = _repo().load("fighter")
    assert f.hit_die == "1d10"
    assert f.levels[1].features == (FeatureId("second_wind"),)
    assert f.levels[3].features == (FeatureId("improved_critical"),)


def test_contains_and_unknown() -> None:
    repo = _repo()
    assert repo.contains("rogue") and not repo.contains("wizard")
    import pytest
    with pytest.raises(KeyError):
        repo.load("wizard")
```

- [ ] **Step 7: Прогнать — падает**

Run: `python3 -m pytest tests/integration/content/test_yaml_class_repository.py -q`
Expected: FAIL — нет порта/адаптера.

- [ ] **Step 8: Порт + адаптер**

Создать `src/dnd/application/ports/class_repository.py`:

```python
"""Порт каталога классов (этап R1)."""
from __future__ import annotations

from typing import Protocol

from dnd.domain.values.class_progression import ClassProgression


class ClassRepository(Protocol):
    def load(self, class_id: str) -> ClassProgression: ...
    def contains(self, class_id: str) -> bool: ...
    def list_ids(self) -> tuple[str, ...]: ...


__all__ = ["ClassRepository"]
```

Создать `src/dnd/infrastructure/content/yaml_class_repository.py`:

```python
"""YamlClassRepository — таблицы классов из одного YAML (этап R1).

Формат — список классов (см. data/content/classes.yaml). Поля совпадают с
ClassProgression; ``levels`` — мапа уровень → {proficiency_bonus, features,
spell_slots}.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from dnd.domain.values.class_progression import ClassLevel, ClassProgression
from dnd.domain.values.ids import FeatureId


class YamlClassRepository:
    def __init__(self, classes_file: Path) -> None:
        self._file = classes_file
        self._by_id: dict[str, ClassProgression] = {}
        if classes_file.exists():
            self._reload()

    def _reload(self) -> None:
        raw = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        if raw is None:
            return
        if not isinstance(raw, list):
            raise ValueError(f"classes file {self._file} must contain a list")
        self._by_id = {}
        for entry in raw:
            cp = self._parse(entry)
            if cp.id in self._by_id:
                raise ValueError(f"duplicate class id {cp.id!r}")
            self._by_id[cp.id] = cp

    def _parse(self, entry: dict[str, Any]) -> ClassProgression:
        levels: dict[int, ClassLevel] = {}
        for lvl_raw, data in entry["levels"].items():
            slots = data.get("spell_slots")
            levels[int(lvl_raw)] = ClassLevel(
                proficiency_bonus=int(data["proficiency_bonus"]),
                features=tuple(FeatureId(f) for f in data.get("features", [])),
                spell_slots={int(k): int(v) for k, v in slots.items()} if slots else None,
            )
        return ClassProgression(
            id=entry["id"], name=entry["name"],
            hit_die=entry["hit_die"], levels=levels,
        )

    def load(self, class_id: str) -> ClassProgression:
        if class_id not in self._by_id:
            raise KeyError(f"unknown class: {class_id!r}")
        return self._by_id[class_id]

    def contains(self, class_id: str) -> bool:
        return class_id in self._by_id

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id.keys()))


__all__ = ["YamlClassRepository"]
```

- [ ] **Step 9: Прогнать — зелёные + mypy + ruff**

Run: `python3 -m pytest tests/integration/content/test_yaml_class_repository.py tests/unit/domain/test_class_progression.py -q && python3 -m mypy src/dnd/application/ports/class_repository.py src/dnd/infrastructure/content/yaml_class_repository.py && python3 -m ruff check src/dnd/application/ports/class_repository.py src/dnd/infrastructure/content/yaml_class_repository.py src/dnd/domain/values/class_progression.py tests/integration/content/test_yaml_class_repository.py tests/unit/domain/test_class_progression.py`
Expected: PASS, mypy/ruff чисто.

- [ ] **Step 10: Commit**

```bash
git add src/dnd/domain/values/class_progression.py src/dnd/application/ports/class_repository.py src/dnd/infrastructure/content/yaml_class_repository.py data/content/classes.yaml tests/unit/domain/test_class_progression.py tests/integration/content/test_yaml_class_repository.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-2): ClassProgression VO + classes.yaml + YamlClassRepository"
```

---

## Task R1-3: XP-кривая (стратегия)

**Files:**
- Create: `src/dnd/application/engine/progression/__init__.py`, `src/dnd/application/engine/progression/xp_curve.py`
- Test: `tests/unit/application/progression/test_xp_curve.py`

- [ ] **Step 1: Тест**

Создать `tests/unit/application/progression/test_xp_curve.py` (и пустой `tests/unit/application/progression/__init__.py` если требуется пакету; обычно pytest без него работает):

```python
"""R1-3: XP-кривые."""
from __future__ import annotations

import pytest

from dnd.application.engine.progression.xp_curve import (
    FastXpCurve,
    MilestoneXpCurve,
    make_xp_curve,
)


def test_fast_thresholds() -> None:
    c = FastXpCurve()
    assert c.threshold(2) == 100
    assert c.threshold(3) == 250
    assert c.threshold(4) == 500


def test_fast_level_for_xp() -> None:
    c = FastXpCurve()
    assert c.level_for_xp(0) == 1
    assert c.level_for_xp(99) == 1
    assert c.level_for_xp(100) == 2
    assert c.level_for_xp(260) == 3
    assert c.level_for_xp(10_000) == 20  # клампится верхним уровнем таблицы


def test_milestone_never_advances_by_xp() -> None:
    c = MilestoneXpCurve()
    assert c.level_for_xp(999) == 1   # milestone: рост по событиям, не по XP


def test_factory() -> None:
    assert isinstance(make_xp_curve("fast"), FastXpCurve)
    with pytest.raises(ValueError):
        make_xp_curve("nope")
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/unit/application/progression/test_xp_curve.py -q`
Expected: FAIL — модуль отсутствует.

- [ ] **Step 3: Реализовать**

Создать `src/dnd/application/engine/progression/__init__.py` (пустой).

Создать `src/dnd/application/engine/progression/xp_curve.py`:

```python
"""XP-кривые (этап R1). Стратегия: какая кривая — задаётся сценарием.

См. docs/PROGRESSION.md §1. Быстрая кривая (fast) — дефолт MVP: короткая партия
даёт 1-й level-up через 1–2 встречи.
"""
from __future__ import annotations

from typing import Protocol


class XpCurve(Protocol):
    def threshold(self, level: int) -> int:
        """Суммарный XP для входа на ``level`` (level=1 → 0)."""
        ...

    def level_for_xp(self, xp: int) -> int:
        """Максимально достижимый уровень при накопленном ``xp``."""
        ...


class _TableXpCurve:
    """База: таблица суммарных порогов {level: cum_xp}."""

    _table: dict[int, int] = {}

    def threshold(self, level: int) -> int:
        if level <= 1:
            return 0
        # за пределами таблицы — последний известный порог
        max_lvl = max(self._table)
        return self._table[min(level, max_lvl)]

    def level_for_xp(self, xp: int) -> int:
        lvl = 1
        for level, cum in sorted(self._table.items()):
            if xp >= cum:
                lvl = level
        return lvl


class FastXpCurve(_TableXpCurve):
    # суммарный XP для входа на уровень (PROGRESSION.md §1.2)
    _table = {2: 100, 3: 250, 4: 500, 5: 900, 20: 900}


class StandardXpCurve(_TableXpCurve):
    _table = {2: 300, 3: 900, 4: 2700, 5: 6500, 20: 6500}


class MilestoneXpCurve:
    """Уровни выдаются по событиям сценария, не по XP — level_for_xp всегда 1."""

    def threshold(self, level: int) -> int:
        return 0

    def level_for_xp(self, xp: int) -> int:
        return 1


def make_xp_curve(name: str) -> XpCurve:
    match name:
        case "fast":
            return FastXpCurve()
        case "standard":
            return StandardXpCurve()
        case "milestone":
            return MilestoneXpCurve()
        case _:
            raise ValueError(f"unknown xp_curve: {name!r}")


__all__ = [
    "FastXpCurve",
    "MilestoneXpCurve",
    "StandardXpCurve",
    "XpCurve",
    "make_xp_curve",
]
```

> Примечание: запись `{20: 900}` означает «на L5+ порог не растёт в R1» — выше L5 контента нет, но `level_for_xp` для огромного XP вернёт 20 (верх таблицы). Это безопасно: R1 доходит до L3.

- [ ] **Step 4: Прогнать — зелёные + mypy + ruff**

Run: `python3 -m pytest tests/unit/application/progression/test_xp_curve.py -q && python3 -m mypy src/dnd/application/engine/progression/xp_curve.py && python3 -m ruff check src/dnd/application/engine/progression/ tests/unit/application/progression/test_xp_curve.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/engine/progression/__init__.py src/dnd/application/engine/progression/xp_curve.py tests/unit/application/progression/
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-3): Xp-кривые (Fast/Standard/Milestone) + фабрика"
```

---

## Task R1-4: события + XpAwardService (kill → LevelUpReady)

**Files:**
- Modify: `src/dnd/application/dto/engine_event.py`
- Create: `src/dnd/application/engine/progression/xp_award.py`
- Test: `tests/integration/engine/test_xp_award.py`

- [ ] **Step 1: Добавить события**

В `src/dnd/application/dto/engine_event.py` (после `SpellCast`/около других событий) добавить:

```python
class LevelUpReady(EngineEvent):
    """XP пересёк порог — существо может прокачаться (PROGRESSION.md §4).

    Само повышение применяет LevelUpService (по выбору игрока: сейчас/после боя).
    """

    event_type: ClassVar[str] = "level_up.ready"
    actor_id: CreatureId
    from_level: int
    to_level: int


class LeveledUp(EngineEvent):
    """Существо повысило уровень (после применения LevelUpService)."""

    event_type: ClassVar[str] = "level_up.done"
    actor_id: CreatureId
    new_level: int
    hp_gained: int
    features_gained: tuple[str, ...] = ()
```

- [ ] **Step 2: Тест XpAwardService**

Создать `tests/integration/engine/test_xp_award.py`:

```python
"""R1-4: XpAwardService — XP за убийство монстра → LevelUpReady при пороге."""
from __future__ import annotations

from dnd.application.dto.engine_event import CreatureDied, LevelUpReady
from dnd.application.engine.progression.xp_award import XpAwardService
from dnd.application.engine.progression.xp_curve import FastXpCurve
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.infrastructure.bus.in_memory_event_bus import InMemoryEventBus


def _pc() -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=14, speed_ft=30,
    )
    c.character_class = "fighter"
    return c


def _gob(cr: float) -> Creature:
    g = Creature.create(
        id_="gob", name="Gob",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30,
    )
    g.challenge_rating = cr
    return g


def _setup() -> tuple[InMemoryEventBus, Creature, Creature, list[LevelUpReady]]:
    bus = InMemoryEventBus()
    pc, gob = _pc(), _gob(1.0)
    participants = {pc.id: pc, gob.id: gob}
    factions = {pc.id: Faction.PARTY, gob.id: Faction.MONSTERS}
    ready: list[LevelUpReady] = []
    bus.subscribe(LevelUpReady, ready.append)
    svc = XpAwardService(
        event_bus=bus, curve=FastXpCurve(),
        participants=participants, factions=factions,
    )
    svc.subscribe()
    return bus, pc, gob, ready


def test_kill_awards_xp_and_triggers_level_up() -> None:
    bus, pc, gob, ready = _setup()
    bus.publish(CreatureDied(actor_id=gob.id))
    assert pc.xp == 100              # CR 1.0 * 100
    assert pc.level == 1            # сам уровень не двигаем — это LevelUpService
    assert ready and ready[0].actor_id == pc.id
    assert ready[0].to_level == 2   # 100 XP → L2 по FastXpCurve


def test_pc_death_does_not_award() -> None:
    bus, pc, gob, ready = _setup()
    # умер сам PC (PARTY) — XP не начисляется никому
    from dnd.application.dto.engine_event import CreatureDied as CD
    bus.publish(CD(actor_id=pc.id))
    assert pc.xp == 0 and not ready
```

> Проверь фактический модуль/класс EventBus: `grep -rn "class .*EventBus" src/dnd/infrastructure src/dnd/application/ports`. Если имя/путь иные (например `InMemoryEventBus` в другом месте) — поправь импорт в тесте.

- [ ] **Step 3: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_xp_award.py -q`
Expected: FAIL — нет `XpAwardService`.

- [ ] **Step 4: Реализовать XpAwardService**

Создать `src/dnd/application/engine/progression/xp_award.py`:

```python
"""XpAwardService — начисление XP и сигнал о готовности к level-up (этап R1).

Подписан на CreatureDied: смерть монстра (фракция ≠ PARTY) даёт XP всем живым
PC (PARTY) по формуле CR*100 (PROGRESSION.md §2). Если XP пересёк порог кривой —
публикует LevelUpReady. Применяет повышение НЕ здесь, а LevelUpService (по выбору
игрока: сейчас/после боя).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import CreatureDied, LevelUpReady

if TYPE_CHECKING:
    from dnd.application.engine.progression.xp_curve import XpCurve
    from dnd.application.ports.event_bus import EventBus
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.ids import CreatureId


class XpAwardService:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        curve: XpCurve,
        participants: dict[CreatureId, Creature],
        factions: dict[CreatureId, Faction],
    ) -> None:
        self._bus = event_bus
        self._curve = curve
        self._participants = participants
        self._factions = factions

    def subscribe(self) -> None:
        self._bus.subscribe(CreatureDied, self._on_died)

    def _on_died(self, event: CreatureDied) -> None:
        from dnd.domain.values.faction import Faction
        dead_faction = self._factions.get(event.actor_id)
        if dead_faction is None or dead_faction is Faction.PARTY:
            return  # XP дают только за не-PARTY
        dead = self._participants.get(event.actor_id)
        if dead is None:
            return
        gained = int(dead.challenge_rating * 100)
        if gained <= 0:
            return
        for cid, cr in self._participants.items():
            if self._factions.get(cid) is not Faction.PARTY or not cr.is_alive:
                continue
            cr.xp += gained
            target_level = self._curve.level_for_xp(cr.xp)
            if target_level > cr.level:
                self._bus.publish(LevelUpReady(
                    actor_id=cid, from_level=cr.level, to_level=target_level,
                ))


__all__ = ["XpAwardService"]
```

- [ ] **Step 5: Прогнать — зелёные + mypy + ruff**

Run: `python3 -m pytest tests/integration/engine/test_xp_award.py -q && python3 -m mypy src/dnd/application/engine/progression/xp_award.py src/dnd/application/dto/engine_event.py && python3 -m ruff check src/dnd/application/engine/progression/xp_award.py src/dnd/application/dto/engine_event.py tests/integration/engine/test_xp_award.py`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/dnd/application/dto/engine_event.py src/dnd/application/engine/progression/xp_award.py tests/integration/engine/test_xp_award.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-4): LevelUpReady/LeveledUp события + XpAwardService (kill→XP→порог)"
```

---

## Task R1-5: FeatureRegistry + реестр ресурсов (каркас)

**Files:**
- Create: `src/dnd/application/engine/features/__init__.py`, `src/dnd/application/engine/features/registry.py`
- Test: `tests/integration/engine/test_features.py`

- [ ] **Step 1: Тест каркаса**

Создать `tests/integration/engine/test_features.py`:

```python
"""R1-7 каркас: FeatureRegistry + ResourceRegistry."""
from __future__ import annotations

import pytest

from dnd.application.engine.features.registry import (
    FeatureRegistry,
    ResourceRegistry,
    ResourceSpec,
)
from dnd.domain.values.ids import FeatureId
from dnd.domain.values.rest import RechargeOn


class _Dummy:
    def __init__(self) -> None:
        self.gained = False

    def on_gain(self, creature: object, ctx: object) -> None:
        self.gained = True


def test_registry_register_get_contains() -> None:
    reg = FeatureRegistry()
    h = _Dummy()
    reg.register(FeatureId("x"), h)
    assert reg.contains(FeatureId("x"))
    assert reg.get(FeatureId("x")) is h


def test_get_unknown_raises() -> None:
    reg = FeatureRegistry()
    with pytest.raises(KeyError):
        reg.get(FeatureId("nope"))


def test_resource_registry() -> None:
    rr = ResourceRegistry()
    rr.register("second_wind", ResourceSpec(max_uses=1, recharge_on=RechargeOn.SHORT_REST))
    spec = rr.get("second_wind")
    assert spec.max_uses == 1 and spec.recharge_on is RechargeOn.SHORT_REST
    assert rr.all_specs()["second_wind"].max_uses == 1
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_features.py -q`
Expected: FAIL — нет модуля.

- [ ] **Step 3: Реализовать каркас**

Создать `src/dnd/application/engine/features/__init__.py` (пустой).

Создать `src/dnd/application/engine/features/registry.py`:

```python
"""FeatureRegistry — реестр классовых фич (этап R1, open/closed).

Каждая фича — feature_id + хендлер (``on_gain``). Регистрируется в
``default_feature_registry``. Новая фича = новый хендлер + регистрация + строка
в classes.yaml, без правки LevelUpService/движка (как SpellEffectRegistry).

``ResourceRegistry`` хранит спеки ограниченных ресурсов (max + recharge_on),
чтобы RestService знал, что и когда восстанавливать, не зная про конкретные фичи.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from dnd.domain.values.rest import RechargeOn

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ids import FeatureId


class FeatureHandler(Protocol):
    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        """Применить фичу при обретении: пассив (модификатор/деривация) или
        регистрация активной способности + инициализация ресурса. ``ctx`` —
        None при применении вне боя (создание PC), иначе текущий ход."""
        ...


class FeatureRegistry:
    def __init__(self) -> None:
        self._by_id: dict[FeatureId, FeatureHandler] = {}

    def register(self, feature_id: FeatureId, handler: FeatureHandler) -> None:
        self._by_id[feature_id] = handler

    def contains(self, feature_id: FeatureId) -> bool:
        return feature_id in self._by_id

    def get(self, feature_id: FeatureId) -> FeatureHandler:
        if feature_id not in self._by_id:
            raise KeyError(f"unknown feature: {feature_id!r}")
        return self._by_id[feature_id]


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    max_uses: int
    recharge_on: RechargeOn


class ResourceRegistry:
    def __init__(self) -> None:
        self._by_key: dict[str, ResourceSpec] = {}

    def register(self, key: str, spec: ResourceSpec) -> None:
        self._by_key[key] = spec

    def get(self, key: str) -> ResourceSpec:
        return self._by_key[key]

    def all_specs(self) -> dict[str, ResourceSpec]:
        return dict(self._by_key)


__all__ = ["FeatureHandler", "FeatureRegistry", "ResourceRegistry", "ResourceSpec"]
```

- [ ] **Step 4: Прогнать — зелёные + mypy + ruff**

Run: `python3 -m pytest tests/integration/engine/test_features.py -q && python3 -m mypy src/dnd/application/engine/features/registry.py && python3 -m ruff check src/dnd/application/engine/features/ tests/integration/engine/test_features.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/engine/features/__init__.py src/dnd/application/engine/features/registry.py tests/integration/engine/test_features.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-5): FeatureRegistry + ResourceRegistry (каркас фич, open/closed)"
```

---

## Task R1-6: RestService

**Files:**
- Create: `src/dnd/application/engine/progression/rest.py`
- Test: `tests/integration/engine/test_rest_service.py`

- [ ] **Step 1: Тест**

Создать `tests/integration/engine/test_rest_service.py`:

```python
"""R1-6: RestService — восстановление ресурсов по recharge_on + HP на LONG."""
from __future__ import annotations

from dnd.application.engine.features.registry import ResourceRegistry, ResourceSpec
from dnd.application.engine.progression.rest import RestService
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.rest import RechargeOn, RestKind


def _c() -> Creature:
    return Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=14, speed_ft=30,
    )


def _rr() -> ResourceRegistry:
    rr = ResourceRegistry()
    rr.register("second_wind", ResourceSpec(1, RechargeOn.SHORT_REST))
    rr.register("daily", ResourceSpec(1, RechargeOn.LONG_REST))
    return rr


def test_short_rest_restores_short_resource_not_long() -> None:
    c = _c()
    c.resource_uses = {"second_wind": 0, "daily": 0}
    RestService(_rr()).apply(c, RestKind.SHORT)
    assert c.resource_uses["second_wind"] == 1   # short восстановлен
    assert c.resource_uses["daily"] == 0         # long НЕ тронут


def test_long_rest_restores_all_and_full_hp() -> None:
    c = _c()
    c.resource_uses = {"second_wind": 0, "daily": 0}
    c.take_damage(DamageInstance(amount=5, type_=DamageType.SLASHING))
    RestService(_rr()).apply(c, RestKind.LONG)
    assert c.resource_uses["second_wind"] == 1 and c.resource_uses["daily"] == 1
    assert c.hit_points.current == c.hit_points.maximum   # полный HP
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_rest_service.py -q`
Expected: FAIL — нет `RestService`.

- [ ] **Step 3: Реализовать**

Создать `src/dnd/application/engine/progression/rest.py`:

```python
"""RestService — восстановление ресурсов и HP по типу отдыха (этап R1).

Архитектура полная: знает только про ``recharge_on`` ресурсов (из
ResourceRegistry), не про конкретные фичи. В R1 единственный триггер —
«отдых между боями» (SHORT на старте encounter), но short/long rest как
внебоевые действия позже зовут ту же ``apply``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.rest import RestKind, recharge_covers

if TYPE_CHECKING:
    from dnd.application.engine.features.registry import ResourceRegistry
    from dnd.domain.entities.creature import Creature


class RestService:
    def __init__(self, resources: ResourceRegistry) -> None:
        self._resources = resources

    def apply(self, creature: Creature, kind: RestKind) -> None:
        # Восстановить ресурсы, чья политика покрыта этим отдыхом.
        for key, spec in self._resources.all_specs().items():
            if key in creature.resource_uses and recharge_covers(kind, spec.recharge_on):
                creature.resource_uses[key] = spec.max_uses
        # Долгий отдых: полный HP (PHB-2024 стр. 39).
        if kind is RestKind.LONG:
            creature.hit_points = creature.hit_points.restore_to_full()


__all__ = ["RestService"]
```

> Проверь API HitPoints для полного восстановления: `grep -n "def restore\|def heal\|maximum\|def full" src/dnd/domain/values/hit_points.py`. Если метода `restore_to_full` нет — используй фактический (например `creature.heal(creature.hit_points.maximum)` или `replace(... current=maximum)`). Подставь реальный способ.

- [ ] **Step 4: Прогнать — зелёные + mypy + ruff**

Run: `python3 -m pytest tests/integration/engine/test_rest_service.py -q && python3 -m mypy src/dnd/application/engine/progression/rest.py && python3 -m ruff check src/dnd/application/engine/progression/rest.py tests/integration/engine/test_rest_service.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/engine/progression/rest.py tests/integration/engine/test_rest_service.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-6): RestService (восстановление ресурсов по recharge_on + HP на LONG)"
```

---

## Task R1-7: LevelUpService + LeveledUp

**Files:**
- Create: `src/dnd/application/engine/progression/level_up.py`
- Test: `tests/integration/engine/test_level_up.py`

- [ ] **Step 1: Тест**

Создать `tests/integration/engine/test_level_up.py`:

```python
"""R1-7: LevelUpService — применение уровней (HP/prof/slots/features)."""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.engine_event import LeveledUp
from dnd.application.engine.features.registry import FeatureRegistry
from dnd.application.engine.progression.level_up import LevelUpService
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ids import FeatureId
from dnd.infrastructure.bus.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.content.yaml_class_repository import YamlClassRepository

_CLASSES = Path(__file__).resolve().parents[3] / "data" / "content" / "classes.yaml"


class _RecordingHandler:
    def __init__(self) -> None:
        self.gained: list[str] = []

    def on_gain(self, creature: Creature, ctx: object) -> None:
        # помечаем, что фича применена (через resource или поле)
        self.gained.append("called")


def _pc() -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=16, speed_ft=30,
    )
    c.character_class = "fighter"
    return c


def _svc(bus: InMemoryEventBus, registry: FeatureRegistry) -> LevelUpService:
    return LevelUpService(
        class_repository=YamlClassRepository(_CLASSES),
        feature_registry=registry, event_bus=bus,
    )


def test_level_up_grants_hp_prof_and_feature() -> None:
    bus = InMemoryEventBus()
    leveled: list[LeveledUp] = []
    bus.subscribe(LeveledUp, leveled.append)
    reg = FeatureRegistry()
    h = _RecordingHandler()
    reg.register(FeatureId("second_wind"), h)   # фича L1 у воина
    pc = _pc()
    # L1→L2: воин получает action_surge (нет хендлера → должен быть зарегистрирован)
    from dnd.application.engine.features.registry import FeatureRegistry as FR  # noqa
    reg.register(FeatureId("action_surge"), _RecordingHandler())
    res = _svc(bus, reg).apply(pc, to_level=2, ctx=None)
    assert pc.level == 2
    # HP: d10 avg(6) + CON mod(+2) = 8 за уровень L2
    assert res.hp_gained == 8
    assert pc.hit_points.maximum == 12 + 8 and pc.hit_points.current == 12 + 8
    assert FeatureId("action_surge") in pc.features
    assert leveled and leveled[0].new_level == 2


def test_level_up_idempotent() -> None:
    bus = InMemoryEventBus()
    reg = FeatureRegistry()
    reg.register(FeatureId("action_surge"), _RecordingHandler())
    pc = _pc()
    svc = _svc(bus, reg)
    svc.apply(pc, to_level=2, ctx=None)
    hp_after_first = pc.hit_points.maximum
    svc.apply(pc, to_level=2, ctx=None)   # повтор — no-op
    assert pc.hit_points.maximum == hp_after_first and pc.level == 2
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_level_up.py -q`
Expected: FAIL — нет `LevelUpService`.

- [ ] **Step 3: Реализовать**

Создать `src/dnd/application/engine/progression/level_up.py`:

```python
"""LevelUpService — применение повышения уровня (этап R1).

Двигает creature.level вперёд по таблице класса, начисляя за каждый уровень:
HP (фикс. среднее кости хитов + mod ТЕЛ), proficiency_bonus, spell_slots, и
обретение фич через FeatureRegistry. Идемпотентно: повторный apply к тому же
to_level — no-op (level уже там). HP — детерминированно (без броска), удобно
для тестов и драмы level-up в бою.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dnd.application.dto.engine_event import LeveledUp
from dnd.domain.values.ability import Ability

if TYPE_CHECKING:
    from dnd.application.engine.features.registry import FeatureRegistry
    from dnd.application.engine.turn_context import TurnContext
    from dnd.application.ports.class_repository import ClassRepository
    from dnd.application.ports.event_bus import EventBus
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ids import FeatureId


@dataclass(frozen=True, slots=True)
class LevelUpResult:
    new_level: int
    hp_gained: int
    features_gained: tuple[FeatureId, ...]
    new_proficiency_bonus: int


class LevelUpService:
    def __init__(
        self,
        *,
        class_repository: ClassRepository,
        feature_registry: FeatureRegistry,
        event_bus: EventBus,
    ) -> None:
        self._classes = class_repository
        self._features = feature_registry
        self._bus = event_bus

    def apply(
        self, creature: Creature, *, to_level: int, ctx: TurnContext | None
    ) -> LevelUpResult:
        assert creature.character_class is not None, "level-up requires a class"
        progression = self._classes.load(creature.character_class)
        con_mod = creature.abilities.modifier(Ability.CON)
        hp_per_level = max(1, progression.hit_die_average() + con_mod)

        total_hp = 0
        gained: list[FeatureId] = []
        while creature.level < to_level:
            next_level = creature.level + 1
            lvl = progression.levels.get(next_level)
            if lvl is None:
                break
            creature.level = next_level
            creature.proficiency_bonus = lvl.proficiency_bonus
            if lvl.spell_slots is not None:
                creature.spell_slots = dict(lvl.spell_slots)
            total_hp += hp_per_level
            for fid in lvl.features:
                creature.features = (*creature.features, fid)
                gained.append(fid)
                self._features.get(fid).on_gain(creature, ctx)

        if total_hp:
            creature.hit_points = creature.hit_points.gain_max(total_hp)

        result = LevelUpResult(
            new_level=creature.level, hp_gained=total_hp,
            features_gained=tuple(gained),
            new_proficiency_bonus=creature.proficiency_bonus,
        )
        if total_hp or gained:
            self._bus.publish(LeveledUp(
                actor_id=creature.id, new_level=creature.level,
                hp_gained=total_hp, features_gained=tuple(str(f) for f in gained),
            ))
        return result


__all__ = ["LevelUpResult", "LevelUpService"]
```

> `creature.hit_points.gain_max(n)` — увеличить и максимум, и текущее на n. Проверь фактический API HitPoints (`grep -n "def \|maximum\|current" src/dnd/domain/values/hit_points.py`). Если метода нет — добавь его в HitPoints (frozen → возвращает новый: `replace(self, maximum=self.maximum+n, current=self.current+n)`) в рамках этого шага и покрой мини-тестом, ЛИБО используй существующий способ (например, через `dataclasses.replace`). Не оставляй несуществующий вызов.

- [ ] **Step 4: Прогнать — зелёные + mypy + ruff**

Run: `python3 -m pytest tests/integration/engine/test_level_up.py -q && python3 -m mypy src/dnd/application/engine/progression/level_up.py && python3 -m ruff check src/dnd/application/engine/progression/level_up.py tests/integration/engine/test_level_up.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/application/engine/progression/level_up.py tests/integration/engine/test_level_up.py
# если правил HitPoints — добавь и его + тест
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-7): LevelUpService (HP/prof/slots/features, идемпотентно) + LeveledUp"
```

---

## Task R1-8: Improved Critical (фича-пассив + правка крита в attack.py)

**Files:**
- Modify: `src/dnd/application/engine/actions/attack.py`
- Create: `src/dnd/application/engine/features/handlers.py` (начать с improved_critical)
- Test: `tests/integration/engine/test_features.py` (дополнить)

- [ ] **Step 1: Тест: крит по crit_range_min + хендлер ставит 19**

Дополнить `tests/integration/engine/test_features.py`:

```python
def test_improved_critical_handler_sets_crit_range() -> None:
    from dnd.application.engine.features.handlers import ImprovedCriticalHandler
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import AbilityScores
    c = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=16, speed_ft=30,
    )
    assert c.crit_range_min == 20
    ImprovedCriticalHandler().on_gain(c, None)
    assert c.crit_range_min == 19
```

И интеграционный тест на attack.py (крит при d20=19 с фичей). Добавить в новый
файл `tests/integration/engine/test_improved_critical.py`:

```python
"""R1-8: Improved Critical меняет порог крита в AttackAction."""
from __future__ import annotations

from dnd.application.dto.engine_event import AttackRolled
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _setup(rolls: list[int]) -> tuple[Creature, Creature, object]:
    a = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    b = Creature.create(
        id_="g", name="G",
        abilities=AbilityScores.of(str_=8, dex=10, con=10, int_=8, wis=8, cha=8),
        max_hp=30, armor_class=5, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(6, 6)
    bf.place_creature(a.id, Square(2, 2))
    bf.place_creature(b.id, Square(3, 2))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS}, deps=deps,
    )
    enc.start()
    for _ in range(12):
        if enc.current_actor_id == a.id:
            break
        enc.start_turn(); enc.end_turn()
    ctx = enc.start_turn()
    return a, b, ctx


def test_d20_19_is_crit_with_improved_critical() -> None:
    # init [20,19], атака d20=19 + урон. Низкий AC цели → попадание в любом случае.
    a, b, ctx = _setup([20, 19, 19, 4, 4])
    a.crit_range_min = 19
    rolled: list[AttackRolled] = []
    ctx.event_bus.subscribe(AttackRolled, rolled.append)
    AttackAction().execute(a, weapon_attack_params(a, b.id), ctx)
    assert rolled and rolled[0].is_critical_hit is True


def test_d20_19_not_crit_by_default() -> None:
    a, b, ctx = _setup([20, 19, 19, 4, 4])
    rolled: list[AttackRolled] = []
    ctx.event_bus.subscribe(AttackRolled, rolled.append)
    AttackAction().execute(a, weapon_attack_params(a, b.id), ctx)
    assert rolled and rolled[0].is_critical_hit is False   # порог по умолчанию 20
```

> Проверь helper построения params атаки: в коде есть `weapon_attack_params(actor, target_id)` (используется в battle.py). Если сигнатура иная — поправь. Кол-во rolls под крит (удвоение костей) уточни прогоном (ScriptedRNG ругнётся на нехватку — добавь значений).

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_improved_critical.py -q`
Expected: FAIL — крит при d20=19 не срабатывает (attack.py смотрит только нат-20); хендлера нет.

- [ ] **Step 3: Правка крита в attack.py**

В `src/dnd/application/engine/actions/attack.py` найти определение `is_crit`
(ищи `is_natural_20`/`is_crit = `). Текущая логика крита по нат-20 заменяется на
порог атакующего. Найди строку, где `is_crit` выставляется по «натуральной 20»
(обычно `is_crit = attack_roll.is_natural_20()` или сравнение `d20_raw == 20`) и
замени на:

```python
        d20_value = attack_roll.d20_raw if attack_roll.d20_raw is not None else 0
        is_crit = d20_value >= actor.crit_range_min
```

(Нат-1 промах `is_crit_miss` и Q-4 авто-крит по лежачему — НЕ трогать; авто-крит
ниже остаётся.) Дефолт `crit_range_min=20` → поведение без фичи не меняется
(регрессия исключена).

> Найди точное место: `grep -n "is_crit\b\|is_natural_20\|is_crit_miss\|d20_raw" src/dnd/application/engine/actions/attack.py`. Меняй только присвоение боевого крита по «20», сохранив существующие нат-1/Q-4 ветки.

- [ ] **Step 4: Хендлер improved_critical**

Создать `src/dnd/application/engine/features/handlers.py`:

```python
"""Хендлеры классовых фич (этап R1). Регистрируются в default_feature_registry.

Каждая фича — отдельный класс. Пассивные правят деривации/вешают модификаторы;
активные инициализируют ресурс и выдают способность (Ability), исполняемую
своим Action (см. second_wind.py / action_surge.py).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


class ImprovedCriticalHandler:
    """Чемпион L3: крит на 19–20. Пассив — ставит crit_range_min=19."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.crit_range_min = 19


__all__ = ["ImprovedCriticalHandler"]
```

- [ ] **Step 5: Прогнать — зелёные + ПЕРЕПРОВЕРКА протухания крита**

Run: `python3 -m pytest tests/integration/engine/test_improved_critical.py tests/integration/engine/test_features.py -q`
Expected: PASS.

ПЕРЕПРОВЕРКА: прогнать ВСЕ тесты атаки/крита — поведение нат-20/нат-1/Q-4 не должно протухнуть:
Run: `python3 -m pytest tests/unit/application/actions/test_attack_action.py tests/integration/engine/test_encounter_dying.py -q`
Expected: PASS. Если что-то упало — значит правка крита изменила смысл; разобраться (вероятно тест полагался на `is_natural_20`-ветку — проверить, что дефолт 20 эквивалентен).

- [ ] **Step 6: mypy + ruff + commit**

Run: `python3 -m mypy src/dnd/application/engine/actions/attack.py src/dnd/application/engine/features/handlers.py && python3 -m ruff check src/dnd/application/engine/actions/attack.py src/dnd/application/engine/features/handlers.py tests/integration/engine/test_improved_critical.py`

```bash
git add src/dnd/application/engine/actions/attack.py src/dnd/application/engine/features/handlers.py tests/integration/engine/test_improved_critical.py tests/integration/engine/test_features.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-8): Improved Critical — крит по crit_range_min (attack.py); хендлер фичи"
```

---

## Task R1-9: Sneak Attack

**Files:**
- Modify: `src/dnd/application/engine/actions/attack.py` (хук после попадания), `src/dnd/domain/entities/creature.py` (флаг once-per-turn), `src/dnd/application/engine/encounter.py` (сброс флага на старте хода), `src/dnd/application/engine/features/handlers.py` (SneakAttackHandler — помечает владельца как «плут со sneak»)
- Test: `tests/integration/engine/test_sneak_attack.py`

- [ ] **Step 1: Решение по модели**

Sneak Attack: `+ceil(level/2)d6` урона того же типа, что оружие, **раз за ход**,
если оружие finesse/ranged И (у атакующего преимущество ИЛИ союзник цели в 5 фт
от цели). Once-per-turn — флаг `sneak_used_this_turn: bool` на Creature,
сбрасывается на старте хода владельца (как combat_stances). Условие «есть фича»
— `FeatureId("sneak_attack") in attacker.features`.

- [ ] **Step 2: Поле флага + сброс**

В `creature.py` рядом с `combat_stances` добавить:

```python
    sneak_used_this_turn: bool = False
    """Sneak Attack плута — раз за ход (PHB-2024). Сбрасывается Encounter'ом
    на старте хода владельца, как combat_stances."""
```

В `encounter.py` найти место сброса `combat_stances` на старте хода
(`grep -n "combat_stances" src/dnd/application/engine/encounter.py`) и рядом
сбросить флаг:

```python
            actor.sneak_used_this_turn = False
```

- [ ] **Step 3: Тест**

Создать `tests/integration/engine/test_sneak_attack.py`:

```python
"""R1-9: Sneak Attack — +Nd6 при условии, раз за ход."""
from __future__ import annotations

from dnd.application.dto.engine_event import DamageDealt
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import FeatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import DAGGER  # finesse


def _setup(rolls: list[int], *, ally: bool) -> tuple[Creature, Creature, object, Encounter]:
    rogue = Creature.create(
        id_="rogue", name="Rogue",
        abilities=AbilityScores.of(str_=10, dex=16, con=12, int_=10, wis=10, cha=10),
        max_hp=16, armor_class=14, speed_ft=30, equipped_weapon=DAGGER,
    )
    rogue.character_class = "rogue"
    rogue.level = 3
    rogue.features = (FeatureId("sneak_attack"),)
    gob = Creature.create(
        id_="gob", name="Gob",
        abilities=AbilityScores.of(str_=8, dex=8, con=10, int_=8, wis=8, cha=8),
        max_hp=40, armor_class=5, speed_ft=30, equipped_weapon=DAGGER,
    )
    participants = {rogue.id: rogue, gob.id: gob}
    factions = {rogue.id: Faction.PARTY, gob.id: Faction.MONSTERS}
    bf = Battlefield(8, 8)
    bf.place_creature(rogue.id, Square(2, 2))
    bf.place_creature(gob.id, Square(3, 2))
    if ally:
        mate = Creature.create(
            id_="mate", name="Mate",
            abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
            max_hp=10, armor_class=14, speed_ft=30, equipped_weapon=DAGGER,
        )
        participants[mate.id] = mate
        factions[mate.id] = Faction.PARTY
        bf.place_creature(mate.id, Square(4, 2))  # рядом с gob (5 фт)
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(participants=participants, factions=factions, deps=deps)
    enc.start()
    for _ in range(12):
        if enc.current_actor_id == rogue.id:
            break
        enc.start_turn(); enc.end_turn()
    ctx = enc.start_turn()
    return rogue, gob, ctx, enc


def test_sneak_attack_adds_dice_when_ally_adjacent() -> None:
    # L3 → 2d6 sneak. rolls: init + attack d20=15 + weapon d4 + 2d6 sneak.
    rogue, gob, ctx, _ = _setup([20, 19, 15, 4, 3, 3], ally=True)
    dmg: list[DamageDealt] = []
    ctx.event_bus.subscribe(DamageDealt, dmg.append)
    AttackAction().execute(rogue, weapon_attack_params(rogue, gob.id), ctx)
    # суммарный raw урон содержит 2d6 (=6) сверх dagger d4
    assert sum(d.raw_amount for d in dmg) >= 4 + 6


def test_no_sneak_without_condition() -> None:
    # без союзника и без преимущества — sneak не срабатывает
    rogue, gob, ctx, _ = _setup([20, 19, 15, 4], ally=False)
    dmg: list[DamageDealt] = []
    ctx.event_bus.subscribe(DamageDealt, dmg.append)
    AttackAction().execute(rogue, weapon_attack_params(rogue, gob.id), ctx)
    assert sum(d.raw_amount for d in dmg) < 4 + 6   # только dagger
```

> Проверь, что `DAGGER` (finesse) существует в `dnd.domain.values.weapon`. Если нет — используй любой finesse-weapon или собери WeaponProfile с finesse=True. Кол-во rolls уточни прогоном.

- [ ] **Step 4: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_sneak_attack.py -q`
Expected: FAIL — sneak не добавляется.

- [ ] **Step 5: Реализовать хук Sneak Attack в attack.py**

В `attack.py` после применения основного урона (после `DamageDealt`-публикации
основного урона, при `hit`) добавить вызов хелпера. Реализация — отдельная
чистая функция в attack.py (или в features/handlers.py — но она трогает ctx/урон,
держим рядом с атакой):

```python
def _maybe_sneak_attack(
    actor: Creature, target: Creature, params: AttackParams,
    attack_ctx: RollContext, ctx: TurnContext, is_crit: bool,
) -> None:
    """Плут: +ceil(level/2)d6 раз за ход при finesse/ranged оружии и
    (преимущество ИЛИ союзник цели рядом с целью). PHB-2024."""
    from dnd.domain.values.ids import FeatureId
    if FeatureId("sneak_attack") not in actor.features:
        return
    if actor.sneak_used_this_turn:
        return
    weapon = actor.equipped_weapon
    if weapon is None or not (weapon.finesse or params.kind is AttackKind.RANGED):
        return
    has_advantage = attack_ctx.advantage and not attack_ctx.disadvantage
    if not (has_advantage or _ally_adjacent_to(target, actor, ctx)):
        return
    n = (actor.level + 1) // 2
    sneak_roll = ctx.dice_roller.roll(
        DiceExpr.parse(f"{n}d6"),
        RollContext(purpose=RollPurpose.DAMAGE, actor_id=actor.id,
                    target_id=target.id, crit=is_crit, tags=("sneak_attack",)),
    )
    actor.sneak_used_this_turn = True
    raw = max(0, sneak_roll.total)
    result = target.take_damage(DamageInstance(amount=raw, type_=params.damage_type))
    ctx.event_bus.publish(DamageDealt(
        attacker_id=actor.id, target_id=target.id,
        damage_roll_id=sneak_roll.roll_id, damage_type=params.damage_type,
        raw_amount=raw, final_amount=result.final_amount, is_critical=is_crit,
        hp_after=target.hit_points.current, hp_max=target.hit_points.maximum,
        was_lethal=result.was_lethal,
    ))


def _ally_adjacent_to(target: Creature, attacker: Creature, ctx: TurnContext) -> bool:
    """Есть ли у цели враждебный ей (= союзный атакующему) сосед в 5 фт,
    кроме самого атакующего (PHB-2024: условие Sneak Attack)."""
    attacker_faction = ctx.factions.get(attacker.id)
    tpos = ctx.battlefield.position_of(target.id)
    for cid, cr in ctx.participants.items():
        if cid in (attacker.id, target.id) or not cr.is_alive:
            continue
        if ctx.factions.get(cid) != attacker_faction:
            continue
        if tpos.distance_to_feet(ctx.battlefield.position_of(cid)) <= 5:
            return True
    return False
```

Вызвать `_maybe_sneak_attack(actor, target, params, attack_ctx, ctx, is_crit)`
в `execute` сразу после публикации основного `DamageDealt` (внутри `if hit:`).

> Проверь имена: переменная контекста атаки (`attack_ctx`), что у `params` есть
`damage_type` и `kind`, что `RollPurpose`/`DiceExpr`/`DamageInstance`/`RollContext`
уже импортированы в attack.py (скорее всего да). При необходимости добери импорт
`FeatureId` вверху файла вместо локального.

- [ ] **Step 6: Прогнать — зелёные**

Run: `python3 -m pytest tests/integration/engine/test_sneak_attack.py -q`
Expected: PASS.

- [ ] **Step 7: SneakAttackHandler (для FeatureRegistry — no-op on_gain)**

Sneak Attack — поведение в attack.py по факту наличия в `features`; хендлер нужен
только чтобы LevelUpService мог его «обрести». Добавить в
`features/handlers.py`:

```python
class SneakAttackHandler:
    """Плут L1: Sneak Attack. Поведение реализовано в AttackAction по наличию
    фичи в creature.features; on_gain — пасс (фича уже добавлена в features)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        return
```

и в `__all__`.

- [ ] **Step 8: ПЕРЕПРОВЕРКА регрессий атаки + mypy + ruff + commit**

Run: `python3 -m pytest tests/integration/engine/test_sneak_attack.py tests/unit/application/actions/test_attack_action.py -q && python3 -m mypy src/dnd/application/engine/actions/attack.py src/dnd/application/engine/features/handlers.py src/dnd/domain/entities/creature.py src/dnd/application/engine/encounter.py && python3 -m ruff check src/dnd/application/engine/actions/attack.py tests/integration/engine/test_sneak_attack.py`
Expected: PASS.

```bash
git add src/dnd/application/engine/actions/attack.py src/dnd/domain/entities/creature.py src/dnd/application/engine/encounter.py src/dnd/application/engine/features/handlers.py tests/integration/engine/test_sneak_attack.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-9): Sneak Attack (+Nd6 раз за ход при преимуществе/союзнике)"
```

---

## Task R1-10: Second Wind (Action + Ability + Intent)

**Files:**
- Create: `src/dnd/application/engine/actions/second_wind.py`
- Modify: `src/dnd/application/dto/player_intent.py`, `src/dnd/application/engine/game_runner.py`, `src/dnd/application/engine/features/handlers.py`
- Test: `tests/integration/engine/test_second_wind.py`

- [ ] **Step 1: Тест**

Создать `tests/integration/engine/test_second_wind.py`:

```python
"""R1-10: Second Wind — bonus action, heal 1d10+level, ресурс 1/short rest."""
from __future__ import annotations

from dnd.application.dto.action import Allowed, Forbidden
from dnd.application.engine.actions.second_wind import (
    SecondWindAction,
    SecondWindParams,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square


def _setup(rolls: list[int]) -> tuple[Creature, object]:
    f = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30,
    )
    f.character_class = "fighter"
    f.level = 2
    f.resource_uses = {"second_wind": 1}
    bf = Battlefield(6, 6)
    bf.place_creature(f.id, Square(2, 2))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(participants={f.id: f}, factions={f.id: Faction.PARTY}, deps=deps)
    enc.start()
    ctx = enc.start_turn()
    return f, ctx


def test_second_wind_heals_and_consumes_use() -> None:
    f, ctx = _setup([20, 7])   # init + heal d10=7
    f.take_damage(DamageInstance(amount=15, type_=DamageType.SLASHING))  # 20→5
    out = SecondWindAction().execute(f, SecondWindParams(), ctx)
    assert out.success
    assert f.hit_points.current == 5 + (7 + 2)   # d10=7 + level 2
    assert f.resource_uses["second_wind"] == 0
    assert ctx.bonus_action_used is True


def test_second_wind_forbidden_without_use() -> None:
    f, ctx = _setup([20, 7])
    f.resource_uses["second_wind"] = 0
    avail = SecondWindAction().can_perform(f, ctx)
    assert isinstance(avail, Forbidden)
```

> Проверь сигнатуру `Action.can_perform`/`execute` и `ActionOutcome` по образцу
`StabilizeAction` (`src/dnd/application/engine/actions/stabilize.py`) — повтори
её точно (методы, ActionParams-базовый класс, ActionEconomyCost).

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_second_wind.py -q`
Expected: FAIL — нет модуля.

- [ ] **Step 3: Реализовать SecondWindAction**

Создать `src/dnd/application/engine/actions/second_wind.py` (по образцу
stabilize.py — повтори фактический контракт Action):

```python
"""SecondWindAction — Воин L1: bonus action, лечение 1d10 + level.

Ресурс ``second_wind`` (1/short rest). Восстанавливается RestService'ом между
боями. Реализация лечения — через Creature.heal (как cure_wounds).
"""
from __future__ import annotations

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import HealingApplied
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import ActionId

_RESOURCE = "second_wind"


class SecondWindParams(ActionParams):
    pass


class SecondWindAction:
    id_value = ActionId("second_wind")
    economy_cost_value = ActionEconomyCost.BONUS_ACTION

    def can_perform(self, actor: Creature, ctx: TurnContext) -> ActionAvailability:
        if actor.resource_uses.get(_RESOURCE, 0) <= 0:
            return Forbidden(reason=ForbiddenReason.CUSTOM, details="second wind used")
        if not ctx.can_spend(ActionEconomyCost.BONUS_ACTION):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        return Allowed()

    def execute(
        self, actor: Creature, params: ActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        if isinstance(self.can_perform(actor, ctx), Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)
        roll = ctx.dice_roller.roll(
            DiceExpr.parse("1d10"),
            RollContext(purpose=RollPurpose.OTHER, actor_id=actor.id,
                        tags=("second_wind",)),
        )
        amount = max(0, roll.total + actor.level)
        result = actor.heal(amount)
        actor.resource_uses[_RESOURCE] -= 1
        ctx.spend(ActionEconomyCost.BONUS_ACTION)
        ctx.event_bus.publish(HealingApplied(
            healer_id=actor.id, target_id=actor.id, amount=result.final_amount,
            hp_after=actor.hit_points.current, hp_max=actor.hit_points.maximum,
        ))
        return ActionOutcome(success=True, consumed=ActionEconomyCost.BONUS_ACTION,
                             notes="second wind")


__all__ = ["SecondWindAction", "SecondWindParams"]
```

> Сверь `ActionOutcome`/`ActionAvailability`/`Forbidden`/`Allowed`/`ForbiddenReason`
и `Creature.heal` сигнатуры с реальностью (stabilize.py + cure_wounds в
handlers.py). Поправь при расхождении.

- [ ] **Step 4: Intent + GameRunner + Ability/ресурс**

В `player_intent.py` добавить `SecondWindIntent`:

```python
class SecondWindIntent(_IntentBase):
    kind: Literal["second_wind"] = "second_wind"
```
и включить в `PlayerIntent` union + `__all__`.

В `game_runner.py` добавить ветку обработки (по образцу `_do_cast`/stabilize):

```python
        elif isinstance(intent, SecondWindIntent):
            self._do_second_wind(actor, ctx)
```
и метод:

```python
    def _do_second_wind(self, actor: Creature, ctx: TurnContext) -> None:
        from dnd.application.engine.actions.second_wind import (
            SecondWindAction, SecondWindParams,
        )
        action = SecondWindAction()
        if isinstance(action.can_perform(actor, ctx), Allowed):
            action.execute(actor, SecondWindParams(), ctx)
        else:
            self._log_rejected(actor, "second_wind", "unavailable")
```
(импорт `SecondWindIntent` вверху game_runner.py + проверь фактическую
структуру диспетчера интентов — повтори её.)

В `features/handlers.py` добавить хендлер, инициализирующий ресурс и выдающий
ability:

```python
class SecondWindHandler:
    """Воин L1: Second Wind. on_gain — инициализирует ресурс и выдаёт ability."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.resource_uses.setdefault("second_wind", 1)
        _grant_ability(creature, "second_wind")
```

Добавить туда же helper выдачи ability (добавляет AbilityId в creature.ability_ids,
если ещё нет):

```python
def _grant_ability(creature: Creature, ability_id: str) -> None:
    from dnd.application.abilities.ability import AbilityId
    aid = AbilityId(ability_id)
    if aid not in creature.ability_ids:
        creature.ability_ids = (*creature.ability_ids, aid)
```

> Реальный модуль AbilityId уточни (`grep -rn "class AbilityId\|AbilityId =" src/dnd/application/abilities src/dnd/domain/values/ability_id.py`). Регистрация ability в AbilityRegistry (чтобы action-bar её показал) — в Task R1-12 (TUI/composition); здесь достаточно добавить id в creature.

- [ ] **Step 5: Прогнать — зелёные + mypy + ruff + commit**

Run: `python3 -m pytest tests/integration/engine/test_second_wind.py -q && python3 -m mypy src/dnd/application/engine/actions/second_wind.py src/dnd/application/engine/game_runner.py src/dnd/application/dto/player_intent.py && python3 -m ruff check src/dnd/application/engine/actions/second_wind.py tests/integration/engine/test_second_wind.py`
Expected: PASS.

```bash
git add src/dnd/application/engine/actions/second_wind.py src/dnd/application/dto/player_intent.py src/dnd/application/engine/game_runner.py src/dnd/application/engine/features/handlers.py tests/integration/engine/test_second_wind.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-10): Second Wind (bonus action, heal 1d10+level, ресурс short_rest)"
```

---

## Task R1-11: Action Surge (доп. действие; ПРОТУХАНИЕ экономики)

**Files:**
- Create: `src/dnd/application/engine/actions/action_surge.py`
- Modify: `src/dnd/application/dto/player_intent.py`, `src/dnd/application/engine/game_runner.py`, `src/dnd/application/engine/features/handlers.py`
- Test: `tests/integration/engine/test_action_surge.py`

- [ ] **Step 1: Тест: даёт второе действие в ходу**

Создать `tests/integration/engine/test_action_surge.py`:

```python
"""R1-11: Action Surge — даёт дополнительное действие в текущем ходу."""
from __future__ import annotations

from dnd.application.dto.action import ActionEconomyCost, Forbidden
from dnd.application.engine.actions.action_surge import (
    ActionSurgeAction,
    ActionSurgeParams,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square


def _setup() -> tuple[Creature, object]:
    f = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30,
    )
    f.character_class = "fighter"
    f.level = 2
    f.resource_uses = {"action_surge": 1}
    bf = Battlefield(6, 6)
    bf.place_creature(f.id, Square(2, 2))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20])
    enc = Encounter(participants={f.id: f}, factions={f.id: Faction.PARTY}, deps=deps)
    enc.start()
    ctx = enc.start_turn()
    return f, ctx


def test_action_surge_refreshes_action() -> None:
    f, ctx = _setup()
    ctx.spend(ActionEconomyCost.ACTION)        # потратили действие
    assert ctx.action_used is True
    out = ActionSurgeAction().execute(f, ActionSurgeParams(), ctx)
    assert out.success
    assert ctx.action_used is False            # действие снова доступно
    assert f.resource_uses["action_surge"] == 0


def test_action_surge_forbidden_without_use() -> None:
    f, ctx = _setup()
    f.resource_uses["action_surge"] = 0
    assert isinstance(ActionSurgeAction().can_perform(f, ctx), Forbidden)
```

- [ ] **Step 2: Прогнать — падает**

Run: `python3 -m pytest tests/integration/engine/test_action_surge.py -q`
Expected: FAIL — нет модуля.

- [ ] **Step 3: Реализовать**

Создать `src/dnd/application/engine/actions/action_surge.py`:

```python
"""ActionSurgeAction — Воин L2: даёт ОДНО дополнительное действие в этом ходу.

PHB-2024: активация Action Surge не стоит действия (FREE), но восстанавливает
возможность взять ещё одно Action в текущем ходу. Ресурс ``action_surge``
(1/short rest).
"""
from __future__ import annotations

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ActionId

_RESOURCE = "action_surge"


class ActionSurgeParams(ActionParams):
    pass


class ActionSurgeAction:
    id_value = ActionId("action_surge")
    economy_cost_value = ActionEconomyCost.FREE

    def can_perform(self, actor: Creature, ctx: TurnContext) -> ActionAvailability:
        if actor.resource_uses.get(_RESOURCE, 0) <= 0:
            return Forbidden(reason=ForbiddenReason.CUSTOM, details="action surge used")
        return Allowed()

    def execute(
        self, actor: Creature, params: ActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        if isinstance(self.can_perform(actor, ctx), Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)
        actor.resource_uses[_RESOURCE] -= 1
        ctx.action_used = False   # доп. действие: освобождаем слот ACTION на этот ход
        return ActionOutcome(success=True, consumed=ActionEconomyCost.FREE,
                             notes="action surge")


__all__ = ["ActionSurgeAction", "ActionSurgeParams"]
```

- [ ] **Step 4: Intent + GameRunner + хендлер**

В `player_intent.py`:
```python
class ActionSurgeIntent(_IntentBase):
    kind: Literal["action_surge"] = "action_surge"
```
включить в union + `__all__`.

В `game_runner.py` ветка + метод (по образцу second_wind):
```python
        elif isinstance(intent, ActionSurgeIntent):
            self._do_action_surge(actor, ctx)
```
```python
    def _do_action_surge(self, actor: Creature, ctx: TurnContext) -> None:
        from dnd.application.engine.actions.action_surge import (
            ActionSurgeAction, ActionSurgeParams,
        )
        action = ActionSurgeAction()
        if isinstance(action.can_perform(actor, ctx), Allowed):
            action.execute(actor, ActionSurgeParams(), ctx)
        else:
            self._log_rejected(actor, "action_surge", "unavailable")
```

В `features/handlers.py`:
```python
class ActionSurgeHandler:
    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.resource_uses.setdefault("action_surge", 1)
        _grant_ability(creature, "action_surge")
```

- [ ] **Step 5: Прогнать — зелёные + ПЕРЕПРОВЕРКА экономики**

Run: `python3 -m pytest tests/integration/engine/test_action_surge.py -q`
Expected: PASS.

ПЕРЕПРОВЕРКА протухания экономики действий: прогнать тесты TurnContext/действий —
refresh `action_used=False` не должен ломать инварианты:
Run: `python3 -m pytest tests/unit/application -k "turn_context or economy or action" -q`
Expected: PASS (или нет совпадений — тогда прогнать весь tests/unit/application).

- [ ] **Step 6: mypy + ruff + commit**

Run: `python3 -m mypy src/dnd/application/engine/actions/action_surge.py src/dnd/application/engine/game_runner.py && python3 -m ruff check src/dnd/application/engine/actions/action_surge.py tests/integration/engine/test_action_surge.py`

```bash
git add src/dnd/application/engine/actions/action_surge.py src/dnd/application/dto/player_intent.py src/dnd/application/engine/game_runner.py src/dnd/application/engine/features/handlers.py tests/integration/engine/test_action_surge.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-11): Action Surge (доп. действие в ходу, ресурс short_rest)"
```

---

## Task R1-12: default_feature_registry + интеграция Encounter (rest + xp) + composition

**Files:**
- Create: `src/dnd/application/engine/features/defaults.py`
- Modify: `src/dnd/application/engine/encounter.py`, `src/dnd/composition.py` (или фактический composition root), `src/dnd/application/abilities/defaults.py` (регистрация second_wind/action_surge ability)
- Test: `tests/integration/engine/test_progression_integration.py`

- [ ] **Step 1: defaults фич + ресурсов**

Создать `src/dnd/application/engine/features/defaults.py`:

```python
"""Дефолтные реестры фич и ресурсов (этап R1)."""
from __future__ import annotations

from dnd.application.engine.features.handlers import (
    ActionSurgeHandler,
    ImprovedCriticalHandler,
    SecondWindHandler,
    SneakAttackHandler,
)
from dnd.application.engine.features.registry import (
    FeatureRegistry,
    ResourceRegistry,
    ResourceSpec,
)
from dnd.domain.values.ids import FeatureId
from dnd.domain.values.rest import RechargeOn


def default_feature_registry() -> FeatureRegistry:
    reg = FeatureRegistry()
    reg.register(FeatureId("improved_critical"), ImprovedCriticalHandler())
    reg.register(FeatureId("sneak_attack"), SneakAttackHandler())
    reg.register(FeatureId("second_wind"), SecondWindHandler())
    reg.register(FeatureId("action_surge"), ActionSurgeHandler())
    return reg


def default_resource_registry() -> ResourceRegistry:
    rr = ResourceRegistry()
    rr.register("second_wind", ResourceSpec(1, RechargeOn.SHORT_REST))
    rr.register("action_surge", ResourceSpec(1, RechargeOn.SHORT_REST))
    return rr


__all__ = ["default_feature_registry", "default_resource_registry"]
```

- [ ] **Step 2: SHORT-rest на старте боя в Encounter**

В `encounter.py` в `start()` (после `_begin_round(1)`, до подписок) добавить
отдых между боями для PC:

```python
        # R1: «отдых между боями» — на старте encounter PC восстанавливают
        # short-rest-ресурсы (Second Wind / Action Surge). Полноценная
        # RestService; будущие внебоевые short/long rest зовут её же.
        from dnd.application.engine.features.defaults import default_resource_registry
        from dnd.application.engine.progression.rest import RestService
        from dnd.domain.values.faction import Faction
        from dnd.domain.values.rest import RestKind
        _rest = RestService(default_resource_registry())
        for cid, cr in self._participants.items():
            if self._factions.get(cid) is Faction.PARTY:
                _rest.apply(cr, RestKind.SHORT)
```

> Проверь имя поля фракций в Encounter (`self._factions` или иное —
`grep -n "factions" src/dnd/application/engine/encounter.py`).

- [ ] **Step 3: XpAwardService подписка в Encounter (опц. — если репо/кривая прокинуты)**

Если у `Encounter` есть доступ к XpCurve (через deps/конфиг сценария) — подписать
`XpAwardService` в `start()` (как `_on_downed`). Если прокидка кривой ещё не
сделана — оставить XP-награду на уровне GameRunner/composition (где собирается
бой) и покрыть интеграционным тестом там. Конкретное место — по фактической
структуре `deps`/composition (см. `grep -n "EncounterDependencies\|deps\." src/dnd/application/engine/encounter.py`). Минимальный путь R1: подписать
XpAwardService там же, где создаётся Encounter в composition/GameRunner, передав
participants/factions/curve.

- [ ] **Step 4: Регистрация ability second_wind/action_surge**

В `src/dnd/application/abilities/defaults.py` (`register_default_abilities`)
добавить регистрацию способностей second_wind и action_surge (icon/hotkey/
intent_factory → SecondWindIntent/ActionSurgeIntent, requires_target=False).
По образцу существующих базовых ability (dodge/dash):

```python
    registry.register(Ability(
        id=AbilityId("second_wind"), name="Second Wind", icon="W",
        default_hotkey="w", economy_cost=ActionEconomyCost.BONUS_ACTION,
        requires_target=False, requires_path=False,
        intent_factory=lambda target_id=None: SecondWindIntent(),
    ))
    registry.register(Ability(
        id=AbilityId("action_surge"), name="Action Surge", icon="S",
        default_hotkey="x", economy_cost=ActionEconomyCost.FREE,
        requires_target=False, requires_path=False,
        intent_factory=lambda target_id=None: ActionSurgeIntent(),
    ))
```

> Сверь фактический конструктор `Ability` и `register_default_abilities` —
повтори точно. Хоткеи `w`/`x` проверь на коллизии с тестом keybindings
(`tests/integration/tui/test_dynamic_keybindings.py` / build_keymap) — при
коллизии выбери свободные.

- [ ] **Step 5: Интеграционный тест полного цикла**

Создать `tests/integration/engine/test_progression_integration.py`:

```python
"""R1-12: интеграция — бой даёт XP→LevelUpReady; SHORT-rest на старте боя."""
from __future__ import annotations

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
# ... собрать Encounter с PC (fighter, resource_uses second_wind=0) и проверить,
# что после enc.start() second_wind восстановлен до 1 (SHORT rest между боями).
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square


def test_short_rest_on_encounter_start_restores_resource() -> None:
    f = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30,
    )
    f.character_class = "fighter"
    f.resource_uses = {"second_wind": 0, "action_surge": 0}
    gob = Creature.create(
        id_="gob", name="Gob",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30,
    )
    bf = Battlefield(6, 6)
    bf.place_creature(f.id, Square(1, 1)); bf.place_creature(gob.id, Square(4, 4))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 10)
    enc = Encounter(
        participants={f.id: f, gob.id: gob},
        factions={f.id: Faction.PARTY, gob.id: Faction.MONSTERS}, deps=deps,
    )
    enc.start()
    assert f.resource_uses["second_wind"] == 1   # SHORT rest между боями
    assert f.resource_uses["action_surge"] == 1
```

- [ ] **Step 6: Прогнать — зелёные + ВЕСЬ набор + mypy + ruff**

Run: `python3 -m pytest tests/integration/engine/test_progression_integration.py -q`
Expected: PASS.

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: PASS, mypy strict чисто, ruff чисто, layering-guard зелёный. Любые
протухшие тесты (крит, экономика, keybindings) — починить по смыслу.

- [ ] **Step 7: Commit**

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-12): default-реестры фич/ресурсов + SHORT-rest на старте боя + ability-регистрация"
```

---

## Task R1-13: TUI LevelUpScreen + контент + docs + аудит

**Files:**
- Create: `src/dnd/interfaces/tui/screens/level_up_screen.py`
- Modify: `src/dnd/interfaces/tui/screens/battle.py`, `src/dnd/interfaces/cli/event_printer.py`, `data/content/monsters.yaml`, `data/content/scenarios.yaml`, `src/dnd/application/dto/templates.py`, `src/dnd/application/engine/builder.py`, `docs/PROGRESSION.md`, `docs/ROADMAP.md`, `docs/ABILITIES.md`
- Test: `tests/integration/tui/test_level_up_screen.py`

- [ ] **Step 1: cr + класс в шаблонах/контенте**

В `templates.py` `MonsterTemplate` добавить `cr: float = 0.0` (Field ge=0) и в
spawn/PC-шаблон — `character_class: str | None = None`, `level: int = 1`. В
`builder.py` пробросить: `creature.challenge_rating = template.cr`; для PC —
`character_class`/`level`. В `monsters.yaml` добавить `cr:` ключевым монстрам
(goblin 0.25, и т.п. по PROGRESSION.md §5). В сценарии PC дать
`character_class: fighter` (или rogue).

> Сверь, как PC попадает в сценарий (`grep -n "party\|player\|character_class\|spawn" src/dnd/application/dto/templates.py data/content/scenarios.yaml`). Прокинь поля по фактической структуре.

- [ ] **Step 2: LeveledUp в EventPrinter**

В `event_printer.py` добавить обработчик `LeveledUp`:

```python
    def _on_leveled_up(self, event: LeveledUp) -> None:
        feats = f" ({', '.join(event.features_gained)})" if event.features_gained else ""
        self._print(
            f"  ⭐ [bold yellow]{event.actor_id} reaches level {event.new_level}![/] "
            f"+{event.hp_gained} HP{feats}"
        )
```
и зарегистрировать в диспетчере событий принтера (по образцу SpellCast). Импорт
`LeveledUp`.

- [ ] **Step 3: Тест LevelUpScreen (unit-уровень логики)**

Создать `tests/integration/tui/test_level_up_screen.py` — проверить, что экран
по выбору «Сейчас» зовёт переданный callback применения, по «После боя» —
callback отложить, по «Подробнее» — не закрывается. Тестировать логику экрана
без полного Pilot, если возможно (мок callbacks), либо pilot по образцу
`test_end_screen.py`:

```python
"""R1-13: LevelUpScreen — выбор «Сейчас/После боя/Подробнее»."""
from __future__ import annotations

# Каркас зависит от фактического API EndScreen-подобных модалок. Реализатору:
# воспроизвести паттерн из tests/integration/tui/test_end_screen.py — собрать
# LevelUpScreen с моками on_now/on_later, нажать клавиши, проверить вызовы.
# НЕ оставлять заглушку: покрыть «Сейчас» → on_now вызван, «После боя» → on_later.
```

> Реализатору: посмотри `tests/integration/tui/test_end_screen.py` и
`src/dnd/interfaces/tui/screens/end_screen.py` — повтори паттерн модалки и теста.

- [ ] **Step 4: LevelUpScreen + wiring в BattleScreen**

Создать `level_up_screen.py` (ModalScreen по образцу EndScreen): показывает
`from_level → to_level`, опции `[Сейчас!] [После боя] [Подробнее]` (bindings
`enter`/`l`/`d` или кнопки). Колбэки `on_now()` (применить LevelUpService +
показать LevelUpResult) и `on_later()` (отложить).

В `battle.py`: подписаться на `LevelUpReady`; копить в очереди; в безопасной
точке (после резолва действия, перед следующим intent — там же, где
обрабатываются прочие пост-событийные модалки/`_concluded`) открывать
`LevelUpScreen`. «Сейчас» → `LevelUpService.apply(actor, to_level=ev.to_level,
ctx=current_ctx)` + лог LeveledUp. «После боя» → запомнить
`pending_level_ups[actor_id]=to_level`, применить на `EncounterEnded`.

> Это самая интеграционная часть. Сверь, как BattleScreen получает сервисы
(spell_repository прокинут — аналогично прокинуть class_repository +
feature_registry + xp_curve через TuiApp/композицию). Опирайся на то, как
сделаны EndScreen-показ и обработка `_concluded`.

- [ ] **Step 5: Прогон TUI + весь набор**

Run: `python3 -m pytest tests/integration/tui/test_level_up_screen.py -q`
Expected: PASS.

Run: `python3 -m pytest -q && python3 -m mypy src && python3 -m ruff check src tests`
Expected: PASS, mypy/ruff чисто.

- [ ] **Step 6: docs**

Обновить:
- `docs/PROGRESSION.md` — отметить, что R1 реализовал (level/xp/класс, fast-кривая,
  level-up в бою, RestService между боями, фичи Improved Crit/Sneak Attack/Second
  Wind/Action Surge); §8 «отложено» — R2 (навыки/Expertise/Fighting Style/Cunning
  Action/Fast Hands), true short/long rest.
- `docs/ROADMAP.md` — R разбит на R1 (✅ после реализации) и R2 (⏳).
- `docs/ABILITIES.md` — Second Wind / Action Surge как классовые ability;
  упомянуть FeatureRegistry (open/closed) и RestService.

- [ ] **Step 7: Commit**

```bash
git add -A
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" commit -m "feat(r1-13): TUI LevelUpScreen + cr/класс в контенте + LeveledUp лог + docs"
```

- [ ] **Step 8: Финальный независимый аудит**

Запустить independent-аудит-субагент (general-purpose) на дельту R1 (`git log`
от первого R1-коммита). Дать спек. Просить классифицировать CRITICAL/MAJOR/
MINOR/NIT. Особое внимание:
- крит-проверка: нет ли регрессии для обычных существ (crit_range_min=20);
- Action Surge: refresh `action_used=False` не ломает экономику/реакции;
- Sneak Attack: ровно раз за ход; условие (преимущество ИЛИ союзник) корректно;
  крит удваивает sneak-кости (crit=is_crit прокинут);
- XP только PARTY за не-PARTY; level-up идемпотентен; «После боя» применяется
  один раз;
- RestService: расширяемость (новый ресурс с recharge_on подхватывается без
  правки сервиса); SHORT на старте боя не задевает long-ресурсы;
- layering (domain не тянет application); реестры open/closed (новая фича/класс =
  данные+хендлер).
Проверить находки самостоятельно (не доверять summary вслепую), применить
CRITICAL/MAJOR, MINOR — по решению. Каждый фикс — отдельный коммит
`fix(r1-audit): ...`.

---

## Self-Review (выполнено при написании плана)

**1. Покрытие спека:**
- §3.1 поля Creature → R1-1 ✓; §3.2 rest VO → R1-1 ✓
- §4 ClassProgression+YAML+репо → R1-2 ✓
- §5 XpCurve → R1-3 ✓
- §6 XpAwardService+события → R1-4 ✓
- §7 LevelUpService → R1-7 ✓
- §8 RestService → R1-6 ✓; триггер на старте боя → R1-12 ✓
- §9 FeatureRegistry+ResourceRegistry → R1-5 ✓
- §10 фичи: Improved Crit → R1-8, Sneak Attack → R1-9, Second Wind → R1-10,
  Action Surge → R1-11 ✓
- §11 TUI LevelUpScreen → R1-13 ✓
- §12 composition → R1-12/R1-13 ✓
- §13 тесты → распределены ✓; §14 инварианты → покрыты тестами ✓

**2. Placeholder-скан:** есть осознанные «сверь фактический API»-пометки
(HitPoints/Ability/Action-контракт/EventBus-путь) — это указания свериться с
реальностью перед написанием кода, не заглушки логики; каждый code-шаг содержит
полный код. Шаблон теста LevelUpScreen (R1-13 Step 3) помечен «не оставлять
заглушку» с указанием образца (test_end_screen.py).

**3. Консистентность типов:** `LevelUpService.apply(creature, *, to_level, ctx)`,
`LevelUpResult(new_level, hp_gained, features_gained, new_proficiency_bonus)`,
`XpAwardService(event_bus, curve, participants, factions)`,
`RestService(resources).apply(creature, kind)`, `FeatureRegistry.get/register/
contains`, `ResourceSpec(max_uses, recharge_on)`, `ResourceRegistry.all_specs()`,
`recharge_covers(kind, recharge)`, события `LevelUpReady(actor_id, from_level,
to_level)` / `LeveledUp(actor_id, new_level, hp_gained, features_gained)`,
ресурсы `"second_wind"`/`"action_surge"`, фичи feature_id
`improved_critical/sneak_attack/second_wind/action_surge` — единообразны во всех
задачах и совпадают с classes.yaml.

**Замечание реализатору:** несколько мест требуют сверки с фактическим API до
кода (помечены «> Проверь …»): `DiceExpr.sides`/parse, `HitPoints.gain_max`/
restore-to-full, контракт `Action`/`ActionOutcome` (образец stabilize.py),
`AbilityId`/`register_default_abilities`/`Ability`-конструктор, `EventBus`-класс/
путь, поле `self._factions` в Encounter, helper `weapon_attack_params`, наличие
`DAGGER`. Это нормальная сверка под реальную кодовую базу, не пробелы плана.
Точные числа rolls в ScriptedRNG-тестах уточняются прогоном (крит удваивает кости).
```
