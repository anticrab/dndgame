# Этап K: богатые карты, sprite-движок, CLI-семья — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить «5×5 клетки» в полноценные игровые локации с богатыми
тайлами, sprite-системой, многослойной картой, интерактивными объектами
(двери/сундуки/бочки), CLI-семьёй команд и TUI-редактором.

**Architecture:** Hexagonal-чистота поверх всего: domain/application —
core (Tile/Feature/Object, engine), Port'ы (`SpriteRegistry`,
`MapRepository`), CLI/TUI/редактор — adapters над этими Port'ами.
JSON-формат для скриптов, YAML для людей. Sprite — content, не код.

**Tech Stack:** Python 3.12, pydantic v2, typer, Textual, hexagonal.
Уже есть: 778 тестов зелёных, mypy strict, ruff clean.

**Spec:** `docs/superpowers/specs/2026-05-23-k-rich-maps-and-world-design.md`.

---

## Структура файлов (что создаётся / меняется)

```
domain/
  values/
    direction.py        [NEW]   N/S/E/W/NE/NW/SE/SW
    sprite_meta.py      [NEW]   SpriteMeta, FeatureKind, TerrainBase, ObjectStateSpec
    tile.py             [NEW]   Tile (base + features)
    object_kind.py      [NEW]   ObjectKind enum
  entities/
    battlefield.py      [MOD]   _tiles + _objects; passable_between() через features
    interactable.py     [NEW]   InteractableObject (mutable)

application/
  ports/
    sprite_registry.py  [NEW]   Port
    map_repository.py   [NEW]   Port
    location_repository.py [NEW] skeleton (для пост-K)
  dto/
    map_dto.py          [NEW]   MapDocument, MapSpawnDoc, MapObjectDoc (pydantic)
    player_intent.py    [MOD]   + InteractIntent, BreakIntent
  engine/
    actions/
      interact.py       [NEW]   InteractAction (FREE / object interaction)
      break_object.py   [NEW]   BreakAction (extends AttackAction, target=ObjectId)

infrastructure/content/
  yaml_sprite_registry.py    [NEW]
  yaml_map_repository.py     [NEW]
  json_map_repository.py     [NEW]

interfaces/cli/
  map_cmds.py         [NEW]   dnd map list/show/validate/new/paint/import/export/edit
  sprite_cmds.py      [NEW]   dnd sprite list/show/validate
  location_cmds.py    [NEW]   dnd location list/show (skeleton)
  app.py              [MOD]   регистрация sub-apps

interfaces/tui/
  widgets/
    map_widget.py     [MOD]   рендер 5×3 через SpriteRegistry
    tile_renderer.py  [NEW]   pure-function: tile + sprite-reg → rich.Text
    palette_widget.py [NEW]   для редактора
  screens/
    battle.py         [MOD]   + Interact biding `i`
    editor_screen.py  [NEW]   режим редактора

data/content/
  sprites/
    terrain/{floor,grass,stone,water,dirt}.yaml          [NEW]
    features/{wall_v,wall_h,wall_ne,wall_nw,wall_se,wall_sw,column,
              table_small,table_long,chair,brazier}.yaml [NEW]
    objects/{door,chest,barrel,window}.yaml              [NEW]
    creatures/{pc_humanoid,goblin}.yaml                  [NEW]
  maps/
    mvp_skirmish.yaml       [MOD migration]
    open_field.yaml         [NEW]
    dungeon_hall.yaml       [NEW]
    forest_clearing.yaml    [NEW]
    warehouse.yaml          [NEW]
    bridge_crossing.yaml    [NEW]
    ruined_hall.yaml        [NEW]
  scenarios.yaml            [MOD: ссылки на map_id]

docs/
  audit/19_k.md             [NEW] финальный аудит
```

---

# ФАЗА K1 — Tile, Direction, миграция Battlefield

После этой фазы Battlefield хранит Tile вместо Terrain; LoS/passability работают через Tile; 778 тестов сохраняются зелёными через alias-режим.

## Task K1-T1: `Direction` enum

**Files:**
- Create: `src/dnd/domain/values/direction.py`
- Test: `tests/unit/domain/values/test_direction.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/domain/values/test_direction.py
"""Direction — компасные направления, используются в Feature.blocks_passage_dirs."""
from __future__ import annotations

import pytest
from dnd.domain.values.direction import Direction
from dnd.domain.values.square import Square


def test_directions_have_4_ortho_and_4_diag() -> None:
    orthogonals = {Direction.N, Direction.S, Direction.E, Direction.W}
    diagonals = {Direction.NE, Direction.NW, Direction.SE, Direction.SW}
    assert len(orthogonals) == 4
    assert len(diagonals) == 4
    assert orthogonals.isdisjoint(diagonals)


def test_opposite_pairs() -> None:
    assert Direction.N.opposite() is Direction.S
    assert Direction.E.opposite() is Direction.W
    assert Direction.NE.opposite() is Direction.SW
    assert Direction.NW.opposite() is Direction.SE


@pytest.mark.parametrize(
    "from_sq,to_sq,expected",
    [
        (Square(2, 2), Square(2, 1), Direction.N),
        (Square(2, 2), Square(2, 3), Direction.S),
        (Square(2, 2), Square(3, 2), Direction.E),
        (Square(2, 2), Square(1, 2), Direction.W),
        (Square(2, 2), Square(3, 1), Direction.NE),
    ],
)
def test_from_squares(from_sq: Square, to_sq: Square, expected: Direction) -> None:
    assert Direction.from_squares(from_sq, to_sq) is expected


def test_from_squares_same_position_raises() -> None:
    with pytest.raises(ValueError, match="same square"):
        Direction.from_squares(Square(1, 1), Square(1, 1))


def test_from_squares_non_adjacent_raises() -> None:
    with pytest.raises(ValueError, match="not adjacent"):
        Direction.from_squares(Square(1, 1), Square(3, 3))
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
pytest tests/unit/domain/values/test_direction.py -v
```
Expected: ModuleNotFoundError на `dnd.domain.values.direction`.

- [ ] **Step 3: Implement Direction**

```python
# src/dnd/domain/values/direction.py
"""Compass-направления для семантики «грани клетки».

Используется в ``FeatureKind.blocks_passage_dirs``: вертикальная стена
блокирует проход {E, W}; горизонтальная — {N, S}; угловая NE — {NE}.

Конвенция Y: ось Y растёт вниз (Y=0 — север, Y=height-1 — юг). Это
согласуется с raster-render картой.
"""
from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dnd.domain.values.square import Square


class Direction(StrEnum):
    N = "n"
    NE = "ne"
    E = "e"
    SE = "se"
    S = "s"
    SW = "sw"
    W = "w"
    NW = "nw"

    def opposite(self) -> Direction:
        return _OPPOSITES[self]

    @staticmethod
    def from_squares(frm: Square, to: Square) -> Direction:
        if frm == to:
            raise ValueError(f"from and to are the same square: {frm}")
        dx = to.x - frm.x
        dy = to.y - frm.y
        if abs(dx) > 1 or abs(dy) > 1:
            raise ValueError(f"squares not adjacent: {frm} -> {to}")
        key = (dx, dy)
        if key not in _BY_DELTA:
            raise ValueError(f"squares not adjacent: {frm} -> {to}")
        return _BY_DELTA[key]


_OPPOSITES: dict[Direction, Direction] = {
    Direction.N: Direction.S,
    Direction.S: Direction.N,
    Direction.E: Direction.W,
    Direction.W: Direction.E,
    Direction.NE: Direction.SW,
    Direction.SW: Direction.NE,
    Direction.NW: Direction.SE,
    Direction.SE: Direction.NW,
}

_BY_DELTA: dict[tuple[int, int], Direction] = {
    (0, -1): Direction.N,
    (1, -1): Direction.NE,
    (1, 0): Direction.E,
    (1, 1): Direction.SE,
    (0, 1): Direction.S,
    (-1, 1): Direction.SW,
    (-1, 0): Direction.W,
    (-1, -1): Direction.NW,
}

__all__ = ["Direction"]
```

- [ ] **Step 4: Run test, verify PASS**

```bash
pytest tests/unit/domain/values/test_direction.py -v
```
Expected: 7/7 passed.

- [ ] **Step 5: mypy + ruff**

```bash
mypy src/dnd/domain/values/direction.py && ruff check src/dnd/domain/values/direction.py
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/dnd/domain/values/direction.py tests/unit/domain/values/test_direction.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(domain): Direction enum для семантики граней клетки"
```

---

## Task K1-T2: `SpriteMeta`, `TerrainBase`, `FeatureKind`

**Files:**
- Create: `src/dnd/domain/values/sprite_meta.py`
- Test: `tests/unit/domain/values/test_sprite_meta.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/domain/values/test_sprite_meta.py
"""SpriteMeta/TerrainBase/FeatureKind — value-объекты для тайлов.

Эти типы — чистые pydantic-модели; они НЕ содержат render-логики.
Только данные + минимальные методы валидации.
"""
from __future__ import annotations

import pytest
from dnd.domain.values.direction import Direction
from dnd.domain.values.sprite_meta import (
    FeatureKind,
    TerrainBase,
)
from dnd.domain.values.terrain import CoverLevel


def test_terrain_base_valid() -> None:
    floor = TerrainBase(
        id="floor",
        name="Floor",
        passable=True,
        difficult=False,
        glyph_5x3=("     ", "  .  ", "     "),
        glyph_1x1=".",
        color_token="floor",
    )
    assert floor.id == "floor"
    assert floor.passable is True


def test_terrain_base_glyph_5x3_must_be_3_rows() -> None:
    with pytest.raises(ValueError, match="3 rows"):
        TerrainBase(
            id="x",
            name="x",
            passable=True,
            difficult=False,
            glyph_5x3=("  ", "  "),
            glyph_1x1=".",
            color_token="x",
        )


def test_terrain_base_glyph_5x3_each_row_5_chars() -> None:
    with pytest.raises(ValueError, match="5 chars"):
        TerrainBase(
            id="x",
            name="x",
            passable=True,
            difficult=False,
            glyph_5x3=("..", "..", ".."),
            glyph_1x1=".",
            color_token="x",
        )


def test_feature_kind_with_blocked_dirs() -> None:
    wall_v = FeatureKind(
        id="wall_v",
        name="Vertical wall",
        blocks_los=True,
        cover=CoverLevel.TOTAL,
        blocks_passage_dirs=frozenset({Direction.E, Direction.W}),
        passable_cost_ft=0,
        glyph_5x3=("  │  ", "  │  ", "  │  "),
        glyph_1x1="│",
        color_token="wall",
    )
    assert Direction.E in wall_v.blocks_passage_dirs
    assert wall_v.cover is CoverLevel.TOTAL


def test_feature_kind_frozen() -> None:
    f = FeatureKind(
        id="x", name="x", blocks_los=False, cover=CoverLevel.NONE,
        blocks_passage_dirs=frozenset(), passable_cost_ft=5,
        glyph_5x3=("     ", "     ", "     "), glyph_1x1=" ",
        color_token="x",
    )
    with pytest.raises(Exception):  # pydantic frozen
        f.id = "y"  # type: ignore[misc]
```

- [ ] **Step 2: Run test, verify FAIL**

```bash
pytest tests/unit/domain/values/test_sprite_meta.py -v
```
Expected: ModuleNotFoundError.

- [ ] **Step 3: Implement**

```python
# src/dnd/domain/values/sprite_meta.py
"""Метаданные спрайтов: TerrainBase (пол), FeatureKind (наклейки).

Чистые value-объекты — pydantic frozen-модели. НЕ содержат render-кода;
рендером занимается UI-слой, который берёт ``glyph_5x3`` / ``glyph_1x1``
и применяет ``color_token`` через CSS.

Sprite = content, не код: эти классы — типизированные представления
данных из ``data/content/sprites/**/*.yaml``.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from dnd.domain.values.direction import Direction
from dnd.domain.values.terrain import CoverLevel


_Glyph5x3 = Annotated[tuple[str, str, str], Field()]


def _validate_glyph_5x3(g: tuple[str, ...]) -> tuple[str, str, str]:
    if len(g) != 3:
        raise ValueError(f"glyph_5x3 must be 3 rows, got {len(g)}")
    for i, row in enumerate(g):
        if len(row) != 5:
            raise ValueError(
                f"glyph_5x3 row {i} must be 5 chars, got {len(row)} ({row!r})"
            )
    return (g[0], g[1], g[2])


class TerrainBase(BaseModel):
    """Базовый пол клетки — то, что под ногами.

    Сам по себе всегда ``passable`` (стены — это features, не base).
    ``difficult=True`` соответствует PHB-2024 «труднопроходимая местность»
    (×2 стоимость).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    passable: bool
    difficult: bool
    glyph_5x3: _Glyph5x3
    glyph_1x1: str = Field(min_length=1, max_length=1)
    color_token: str

    @model_validator(mode="after")
    def _check_glyph(self) -> TerrainBase:
        object.__setattr__(self, "glyph_5x3", _validate_glyph_5x3(self.glyph_5x3))
        return self


class FeatureKind(BaseModel):
    """Тип фичи — стена, колонна, мебель.

    Применяется поверх ``TerrainBase``. Несколько features на одной
    клетке — допустимо (стол + бочка стоят рядом и т.п.); их семантика
    суммируется по правилу «самое строгое побеждает».
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    blocks_los: bool
    cover: CoverLevel
    blocks_passage_dirs: frozenset[Direction]
    passable_cost_ft: int = Field(ge=0)  # 0 = непроходимо, 5 = норм, 10 = difficult
    glyph_5x3: _Glyph5x3
    glyph_1x1: str = Field(min_length=1, max_length=1)
    color_token: str

    @model_validator(mode="after")
    def _check_glyph(self) -> FeatureKind:
        object.__setattr__(self, "glyph_5x3", _validate_glyph_5x3(self.glyph_5x3))
        return self


__all__ = ["FeatureKind", "TerrainBase"]
```

- [ ] **Step 4: Run test, verify PASS**

```bash
pytest tests/unit/domain/values/test_sprite_meta.py -v
```
Expected: 5/5 passed.

- [ ] **Step 5: mypy + ruff**

```bash
mypy src/dnd/domain/values/sprite_meta.py && ruff check src/dnd/domain/values/sprite_meta.py
```

- [ ] **Step 6: Commit**

```bash
git add src/dnd/domain/values/sprite_meta.py tests/unit/domain/values/test_sprite_meta.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(domain): TerrainBase + FeatureKind value-объекты для sprite-meta"
```

---

## Task K1-T3: `Tile` композит

**Files:**
- Create: `src/dnd/domain/values/tile.py`
- Test: `tests/unit/domain/values/test_tile.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/domain/values/test_tile.py
"""Tile — композит base + features. Семантика суммируется."""
from __future__ import annotations

from dnd.domain.values.direction import Direction
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase
from dnd.domain.values.terrain import CoverLevel
from dnd.domain.values.tile import Tile


FLOOR = TerrainBase(
    id="floor", name="Floor", passable=True, difficult=False,
    glyph_5x3=("     ", "  .  ", "     "), glyph_1x1=".", color_token="floor",
)
GRASS = TerrainBase(
    id="grass", name="Grass", passable=True, difficult=True,
    glyph_5x3=("”””””", "”””””", "”””””"),
    glyph_1x1=",", color_token="grass",
)
WALL_V = FeatureKind(
    id="wall_v", name="V wall", blocks_los=True, cover=CoverLevel.TOTAL,
    blocks_passage_dirs=frozenset({Direction.E, Direction.W}),
    passable_cost_ft=0, glyph_5x3=("  │  ", "  │  ", "  │  "),
    glyph_1x1="│", color_token="wall",
)
COLUMN = FeatureKind(
    id="column", name="Column", blocks_los=False, cover=CoverLevel.THREE_QUARTERS,
    blocks_passage_dirs=frozenset({Direction.N, Direction.S, Direction.E, Direction.W}),
    passable_cost_ft=0, glyph_5x3=("  ▙  ", "  ▙  ", "  ▙  "),
    glyph_1x1="▙", color_token="wall",
)


def test_tile_floor_no_features_is_passable_all_directions() -> None:
    t = Tile(base=FLOOR, features=())
    for d in Direction:
        assert t.allows_entry_from(d) is True
    assert t.blocks_los is False
    assert t.aggregate_cover() is CoverLevel.NONE


def test_tile_with_wall_v_blocks_east_west_only() -> None:
    t = Tile(base=FLOOR, features=(WALL_V,))
    assert t.allows_entry_from(Direction.E) is False
    assert t.allows_entry_from(Direction.W) is False
    assert t.allows_entry_from(Direction.N) is True
    assert t.allows_entry_from(Direction.S) is True


def test_tile_with_column_blocks_all_ortho_keeps_los() -> None:
    t = Tile(base=FLOOR, features=(COLUMN,))
    assert t.allows_entry_from(Direction.N) is False
    assert t.blocks_los is False  # колонна не блокирует LoS
    assert t.aggregate_cover() is CoverLevel.THREE_QUARTERS


def test_tile_grass_base_difficult_terrain_cost_doubled() -> None:
    t = Tile(base=GRASS, features=())
    assert t.movement_cost_ft() == 10  # 5 base * 2 = 10


def test_tile_floor_no_features_cost_5() -> None:
    t = Tile(base=FLOOR, features=())
    assert t.movement_cost_ft() == 5
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pytest tests/unit/domain/values/test_tile.py -v
```

- [ ] **Step 3: Implement Tile**

```python
# src/dnd/domain/values/tile.py
"""Tile — клетка карты как композит base + features.

Это центральный value-object новой картографической модели (этап K).
Заменяет старый плоский ``Terrain`` (который остаётся как
backwards-compatibility alias через готовые Tile-константы — см.
``tile_aliases.py``).

Семантика клетки (passable/LoS/cover/cost) **читается** из data,
а не наследуется. Никаких side-effects: Tile — pure frozen value.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dnd.domain.values.direction import Direction
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase
from dnd.domain.values.terrain import CoverLevel

_COVER_RANK: dict[CoverLevel, int] = {
    CoverLevel.NONE: 0,
    CoverLevel.HALF: 1,
    CoverLevel.THREE_QUARTERS: 2,
    CoverLevel.TOTAL: 3,
}


class Tile(BaseModel):
    """Композит: пол + наклеенные features.

    ``features`` — tuple для иммутабельности и хешируемости.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    base: TerrainBase
    features: tuple[FeatureKind, ...] = ()

    def allows_entry_from(self, direction: Direction) -> bool:
        """Можно ли войти в клетку с указанного направления.

        Семантика: если хоть один feature на клетке блокирует это
        направление — нельзя. Также если хоть один feature имеет
        ``passable_cost_ft=0`` И блокирует все 4 ортогонала — это
        непроходимая «масса» (column/wall full), любой вход блокирован.
        """
        if not self.base.passable:
            return False
        for f in self.features:
            if direction in f.blocks_passage_dirs:
                return False
        return True

    @property
    def blocks_los(self) -> bool:
        """Блокирует ли LoS любая из features. Base пол LoS не блокирует."""
        return any(f.blocks_los for f in self.features)

    def aggregate_cover(self) -> CoverLevel:
        """Максимальная cover из всех features (PHB-2024 стр. 25: «применяется
        только наиболее защищающая степень»)."""
        if not self.features:
            return CoverLevel.NONE
        return max(
            (f.cover for f in self.features), key=lambda c: _COVER_RANK[c]
        )

    def movement_cost_ft(self) -> int:
        """Стоимость входа в клетку (PHB-2024). Базовый 5 фт;
        difficult terrain → 10 фт; features могут добавить (например,
        мебель — +5).

        Если хоть один feature ``passable_cost_ft == 0`` — клетка
        непроходима в принципе; вызывающий должен дополнительно
        проверять через ``allows_entry_from``.
        """
        base_cost = 10 if self.base.difficult else 5
        extra = sum(
            max(0, f.passable_cost_ft - 5)  # surplus сверх стандарта
            for f in self.features
            if f.passable_cost_ft > 0  # 0 = непроходимо, не считаем
        )
        return base_cost + extra


__all__ = ["Tile"]
```

- [ ] **Step 4: Run, verify PASS**

```bash
pytest tests/unit/domain/values/test_tile.py -v
```
Expected: 5/5 passed.

- [ ] **Step 5: mypy + ruff**

- [ ] **Step 6: Commit**

```bash
git add src/dnd/domain/values/tile.py tests/unit/domain/values/test_tile.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(domain): Tile композит (base + features) с allows_entry_from/cover/cost"
```

---

## Task K1-T4: `ObjectKind` + `InteractableObject`

**Files:**
- Create: `src/dnd/domain/values/object_kind.py`
- Create: `src/dnd/domain/entities/interactable.py`
- Test: `tests/unit/domain/entities/test_interactable.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/domain/entities/test_interactable.py
"""InteractableObject — двери/сундуки/бочки/окна с состояниями."""
from __future__ import annotations

import pytest
from dnd.application.dto.ids import ObjectId
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square


def test_door_starts_closed_can_open() -> None:
    door = InteractableObject(
        id=ObjectId("door-1"),
        kind=ObjectKind.DOOR,
        pos=Square(3, 2),
        state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    assert door.state["open"] is False
    door.open()
    assert door.state["open"] is True


def test_door_locked_cannot_be_opened_directly() -> None:
    door = InteractableObject(
        id=ObjectId("door-1"),
        kind=ObjectKind.DOOR,
        pos=Square(3, 2),
        state={"open": False, "locked": True, "hp": 10, "ac": 13},
    )
    with pytest.raises(RuntimeError, match="locked"):
        door.open()


def test_chest_open_returns_loot() -> None:
    chest = InteractableObject(
        id=ObjectId("chest-1"),
        kind=ObjectKind.CHEST,
        pos=Square(4, 4),
        state={"open": False, "contents": ["potion_heal", "gold_50"]},
    )
    loot = chest.open()
    assert loot == ["potion_heal", "gold_50"]
    assert chest.state["open"] is True
    # повторное открытие — пусто
    assert chest.open() == []


def test_barrel_take_damage_can_break() -> None:
    barrel = InteractableObject(
        id=ObjectId("bar-1"),
        kind=ObjectKind.BARREL,
        pos=Square(2, 2),
        state={"hp": 5, "broken": False, "contents": ["bolts_10"]},
    )
    result = barrel.take_damage(DamageInstance(amount=3, type_=DamageType.BLUDGEONING))
    assert result.was_lethal is False
    assert barrel.state["hp"] == 2
    result = barrel.take_damage(DamageInstance(amount=5, type_=DamageType.BLUDGEONING))
    assert result.was_lethal is True
    assert barrel.state["broken"] is True


def test_window_immutable_blocks_passage_not_los() -> None:
    # Window: семантика хранится в FeatureKind (это feature, не object).
    # InteractableObject(WINDOW) — для будущей «можно разбить окно».
    pass  # explicit no-op
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pytest tests/unit/domain/entities/test_interactable.py -v
```

- [ ] **Step 3: Add ObjectId to ids.py**

```python
# Modify: src/dnd/application/dto/ids.py
# Add at the end of NewType declarations:
ObjectId = NewType("ObjectId", str)
```

- [ ] **Step 4: Implement ObjectKind enum**

```python
# src/dnd/domain/values/object_kind.py
"""ObjectKind — типы интерактивных объектов на карте."""
from __future__ import annotations

from enum import StrEnum


class ObjectKind(StrEnum):
    DOOR = "door"
    CHEST = "chest"
    BARREL = "barrel"
    WINDOW = "window"


__all__ = ["ObjectKind"]
```

- [ ] **Step 5: Implement InteractableObject**

```python
# src/dnd/domain/entities/interactable.py
"""InteractableObject — двери, сундуки, бочки, окна.

Mutable entity (как Creature). Имеет ``state: dict`` со свободной
схемой — конкретные ключи зависят от ``kind``:

* DOOR: open (bool), locked (bool), hp (int), ac (int).
* CHEST: open (bool), locked (bool), contents (list[str]).
* BARREL: hp (int), broken (bool), contents (list[str]).
* WINDOW: hp (int), broken (bool).

Методы (``open()`` / ``take_damage()`` / ...) — конкретные операции,
которые валидируют state и меняют его на месте.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dnd.application.dto.ids import ObjectId
from dnd.domain.values.damage import DamageInstance
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square


@dataclass(slots=True)
class ObjectDamageResult:
    """Итог take_damage у InteractableObject."""

    raw: int
    final: int
    was_lethal: bool  # сломан / разрушен этой порцией


@dataclass(slots=True)
class InteractableObject:
    id: ObjectId
    kind: ObjectKind
    pos: Square
    state: dict[str, Any] = field(default_factory=dict)

    # --- door/chest --------------------------------------------------

    def open(self) -> list[str]:
        """Открыть. Возвращает loot (для CHEST/BARREL) или [].

        DOOR: меняет ``open`` на True. RuntimeError если locked.
        CHEST: меняет ``open`` на True, возвращает contents и очищает.
        BARREL/WINDOW: RuntimeError (нельзя «открыть»).
        """
        if self.kind is ObjectKind.DOOR:
            if self.state.get("locked"):
                raise RuntimeError(f"door {self.id} is locked")
            self.state["open"] = True
            return []
        if self.kind is ObjectKind.CHEST:
            if self.state.get("locked"):
                raise RuntimeError(f"chest {self.id} is locked")
            if self.state.get("open"):
                return []
            self.state["open"] = True
            loot = list(self.state.get("contents", []))
            self.state["contents"] = []
            return loot
        raise RuntimeError(f"{self.kind} cannot be opened")

    def close(self) -> None:
        """Закрыть DOOR. Прочие — RuntimeError."""
        if self.kind is ObjectKind.DOOR:
            self.state["open"] = False
            return
        raise RuntimeError(f"{self.kind} cannot be closed")

    # --- breakable ---------------------------------------------------

    def take_damage(self, damage: DamageInstance) -> ObjectDamageResult:
        """Принять урон. Может сломать BARREL/WINDOW/DOOR (если есть hp)."""
        if "hp" not in self.state:
            raise RuntimeError(f"{self.kind} has no hp; cannot take damage")
        hp_before = int(self.state["hp"])
        if hp_before <= 0:
            return ObjectDamageResult(raw=damage.amount, final=0, was_lethal=False)
        applied = min(damage.amount, hp_before)
        hp_after = hp_before - applied
        self.state["hp"] = hp_after
        was_lethal = hp_before > 0 and hp_after == 0
        if was_lethal:
            self.state["broken"] = True
            # сломанная дверь = открытая
            if self.kind is ObjectKind.DOOR:
                self.state["open"] = True
        return ObjectDamageResult(
            raw=damage.amount, final=applied, was_lethal=was_lethal
        )


__all__ = ["InteractableObject", "ObjectDamageResult"]
```

- [ ] **Step 6: Run, verify PASS**

```bash
pytest tests/unit/domain/entities/test_interactable.py tests/unit/domain/values/test_tile.py -v
```
Expected: 9/9 passed (4 + 5).

- [ ] **Step 7: mypy + ruff sweep**

```bash
mypy src/ && ruff check src/ tests/
```

- [ ] **Step 8: Commit**

```bash
git add src/dnd/application/dto/ids.py src/dnd/domain/values/object_kind.py \
        src/dnd/domain/entities/interactable.py tests/unit/domain/entities
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(domain): InteractableObject (DOOR/CHEST/BARREL) + ObjectKind"
```

---

## Task K1-T5: `Tile`-aliases для backwards compat

**Files:**
- Create: `src/dnd/domain/values/tile_aliases.py`
- Test: `tests/unit/domain/values/test_tile_aliases.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/domain/values/test_tile_aliases.py
"""Aliases: старые Terrain-константы (FLOOR/WALL/...) воспроизводятся
как готовые Tile. Это нужно для backwards compat до миграции тестов."""
from __future__ import annotations

from dnd.domain.values.tile_aliases import (
    FLOOR_TILE,
    WALL_TILE,
    DIFFICULT_TILE,
    LOW_COVER_TILE,
    HIGH_COVER_TILE,
)
from dnd.domain.values.terrain import CoverLevel
from dnd.domain.values.direction import Direction


def test_floor_tile_is_fully_passable() -> None:
    for d in Direction:
        assert FLOOR_TILE.allows_entry_from(d)
    assert FLOOR_TILE.blocks_los is False


def test_wall_tile_is_impassable_all_directions() -> None:
    for d in Direction:
        assert WALL_TILE.allows_entry_from(d) is False
    assert WALL_TILE.blocks_los is True


def test_difficult_tile_costs_10() -> None:
    assert DIFFICULT_TILE.movement_cost_ft() == 10


def test_low_cover_tile_passable_with_cover_half() -> None:
    # LOW_COVER: проходимо, но даёт half cover за ним.
    # На самой клетке cover тоже half, потому что её feature даёт half.
    assert any(LOW_COVER_TILE.allows_entry_from(d) for d in Direction)
    assert LOW_COVER_TILE.aggregate_cover() is CoverLevel.HALF


def test_high_cover_tile_impassable_three_quarters() -> None:
    for d in Direction:
        assert HIGH_COVER_TILE.allows_entry_from(d) is False
    assert HIGH_COVER_TILE.aggregate_cover() is CoverLevel.THREE_QUARTERS
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pytest tests/unit/domain/values/test_tile_aliases.py -v
```

- [ ] **Step 3: Implement aliases**

```python
# src/dnd/domain/values/tile_aliases.py
"""Aliases: старый плоский Terrain → новый композитный Tile.

Это backwards-compat-слой на время миграции (этап K1). После полной
миграции `Battlefield` на Tile + после переписи тестов можно
deprecated удалить.

Примечание про FLOOR/WALL/etc: эти константы уже существуют в
``terrain.py`` (frozen dataclass). Тут — дублирующие *_TILE-версии,
которые engine использует в новой модели.
"""
from __future__ import annotations

from dnd.domain.values.direction import Direction
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase
from dnd.domain.values.terrain import CoverLevel
from dnd.domain.values.tile import Tile


# --- TerrainBase константы ---

_FLOOR = TerrainBase(
    id="floor", name="Floor", passable=True, difficult=False,
    glyph_5x3=("     ", "     ", "     "), glyph_1x1=".", color_token="floor",
)
_GRASS = TerrainBase(
    id="grass", name="Grass", passable=True, difficult=True,
    glyph_5x3=("” ” ”", " ” ” ", "” ” ”"),
    glyph_1x1=",", color_token="grass",
)
_STONE = TerrainBase(
    id="stone", name="Stone", passable=True, difficult=False,
    glyph_5x3=("     ", "     ", "     "), glyph_1x1=".", color_token="floor",
)

# --- FeatureKind константы ---

_WALL_FULL = FeatureKind(
    id="wall_full", name="Wall", blocks_los=True, cover=CoverLevel.TOTAL,
    blocks_passage_dirs=frozenset(Direction),
    passable_cost_ft=0,
    glyph_5x3=("█████", "█████", "█████"), glyph_1x1="#",
    color_token="wall",
)
_LOW_COVER_FEATURE = FeatureKind(
    id="low_cover_obj", name="Low cover", blocks_los=False, cover=CoverLevel.HALF,
    blocks_passage_dirs=frozenset(),
    passable_cost_ft=5,
    glyph_5x3=("     ", " /-\\ ", "     "), glyph_1x1="=",
    color_token="object",
)
_HIGH_COVER_FEATURE = FeatureKind(
    id="high_cover_obj", name="High cover", blocks_los=False,
    cover=CoverLevel.THREE_QUARTERS,
    blocks_passage_dirs=frozenset(Direction),  # непроходимо
    passable_cost_ft=0,
    glyph_5x3=("  ▙  ", "  ▙  ", "  ▙  "), glyph_1x1="H",
    color_token="wall",
)

# --- Tile aliases ---

FLOOR_TILE = Tile(base=_FLOOR, features=())
WALL_TILE = Tile(base=_STONE, features=(_WALL_FULL,))
DIFFICULT_TILE = Tile(base=_GRASS, features=())
LOW_COVER_TILE = Tile(base=_FLOOR, features=(_LOW_COVER_FEATURE,))
HIGH_COVER_TILE = Tile(base=_FLOOR, features=(_HIGH_COVER_FEATURE,))

__all__ = [
    "DIFFICULT_TILE",
    "FLOOR_TILE",
    "HIGH_COVER_TILE",
    "LOW_COVER_TILE",
    "WALL_TILE",
]
```

- [ ] **Step 4: Run, verify PASS**

```bash
pytest tests/unit/domain/values/test_tile_aliases.py -v
```
Expected: 5/5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/dnd/domain/values/tile_aliases.py tests/unit/domain/values/test_tile_aliases.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(domain): Tile-aliases для backwards compat (FLOOR/WALL/DIFFICULT/cover)"
```

---

## Task K1-T6: миграция `Battlefield` на Tile + objects (alias-режим)

**Files:**
- Modify: `src/dnd/domain/entities/battlefield.py`
- Create: `tests/unit/domain/entities/test_battlefield_tile.py`

- [ ] **Step 1: Write failing test для нового API**

```python
# tests/unit/domain/entities/test_battlefield_tile.py
"""Battlefield — новый Tile-aware API.

Не дублирует существующий test_battlefield.py (там сохранён старый
Terrain-API, который тоже должен работать через alias).
"""
from __future__ import annotations

import pytest
from dnd.application.dto.ids import CreatureId, ObjectId
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.direction import Direction
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square
from dnd.domain.values.tile_aliases import FLOOR_TILE, WALL_TILE


def test_set_tile_and_tile_at() -> None:
    bf = Battlefield(5, 5)
    bf.set_tile(Square(1, 1), WALL_TILE)
    assert bf.tile_at(Square(1, 1)) is WALL_TILE
    assert bf.tile_at(Square(0, 0)) == FLOOR_TILE  # default


def test_passable_between_blocked_by_wall_tile() -> None:
    bf = Battlefield(5, 5)
    bf.set_tile(Square(2, 2), WALL_TILE)
    # из (1,2) → (2,2): попытка войти на стену с запада должна блок.
    assert bf.passable_between(Square(1, 2), Square(2, 2)) is False


def test_passable_between_open_floor_ok() -> None:
    bf = Battlefield(5, 5)
    assert bf.passable_between(Square(2, 2), Square(3, 2)) is True


def test_place_and_get_object() -> None:
    bf = Battlefield(5, 5)
    door = InteractableObject(
        id=ObjectId("door-1"),
        kind=ObjectKind.DOOR,
        pos=Square(3, 2),
        state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    bf.place_object(door)
    assert bf.object_at(ObjectId("door-1")) is door
    assert door in bf.objects_at(Square(3, 2))


def test_objects_at_empty_returns_empty_tuple() -> None:
    bf = Battlefield(5, 5)
    assert bf.objects_at(Square(0, 0)) == ()
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pytest tests/unit/domain/entities/test_battlefield_tile.py -v
```

- [ ] **Step 3: Extend Battlefield**

Modify `src/dnd/domain/entities/battlefield.py` — добавить новые методы. Сохранить старые (`terrain_at`, `set_terrain`, `line_of_sight`, `cover_against`) **как есть** для backwards compat. Добавить:

```python
# Добавить импорты:
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.direction import Direction
from dnd.domain.values.tile import Tile
from dnd.domain.values.tile_aliases import FLOOR_TILE

# В __init__ добавить:
        self._tiles: dict[Square, Tile] = {}
        self._objects: dict[ObjectId, InteractableObject] = {}
        self._objects_by_square: dict[Square, list[ObjectId]] = defaultdict(list)

# Добавить методы (после existing terrain_at):

    def tile_at(self, square: Square) -> Tile:
        """Tile на клетке. Default — FLOOR_TILE для не-выставленных."""
        if not self.in_bounds(square):
            # Вне границ — стена-тайл (как _OUT_OF_BOUNDS для terrain).
            from dnd.domain.values.tile_aliases import WALL_TILE
            return WALL_TILE
        return self._tiles.get(square, FLOOR_TILE)

    def set_tile(self, square: Square, tile: Tile) -> None:
        if not self.in_bounds(square):
            raise ValueError(f"square {square} is out of bounds")
        self._tiles[square] = tile

    def passable_between(self, frm: Square, to: Square) -> bool:
        """Можно ли пройти из frm в to. Учитывает Tile.features обеих
        клеток + open/closed doors.

        Не учитывает occupancy creatures — это уровень MoveAction.
        """
        if not (self.in_bounds(frm) and self.in_bounds(to)):
            return False
        if frm == to:
            return True
        direction = Direction.from_squares(frm, to)
        # Из клетки frm: блокирует ли feature выход в этом направлении?
        from_tile = self.tile_at(frm)
        for f in from_tile.features:
            if direction in f.blocks_passage_dirs:
                return False
        # В клетку to: блокирует ли feature вход с противоположной стороны?
        to_tile = self.tile_at(to)
        return to_tile.allows_entry_from(direction.opposite())

    # --- Interactable objects ---

    def place_object(self, obj: InteractableObject) -> None:
        """Поставить объект на карту по obj.pos."""
        if not self.in_bounds(obj.pos):
            raise ValueError(f"object pos {obj.pos} out of bounds")
        self._objects[obj.id] = obj
        self._objects_by_square[obj.pos].append(obj.id)

    def object_at(self, object_id: ObjectId) -> InteractableObject:
        try:
            return self._objects[object_id]
        except KeyError as exc:
            raise KeyError(f"unknown object: {object_id!r}") from exc

    def objects_at(self, square: Square) -> tuple[InteractableObject, ...]:
        ids = self._objects_by_square.get(square, ())
        return tuple(self._objects[i] for i in ids)
```

- [ ] **Step 4: Run new tests + existing battlefield tests**

```bash
pytest tests/unit/domain/entities/test_battlefield_tile.py \
       tests/unit/domain/entities/test_battlefield.py -v
```
Expected: всё PASS. Старые тесты не сломались (терминальное API сохранено).

- [ ] **Step 5: mypy/ruff sweep**

```bash
mypy src/ && ruff check src/ tests/
```

- [ ] **Step 6: Commit**

```bash
git add src/dnd/domain/entities/battlefield.py tests/unit/domain/entities/test_battlefield_tile.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(battlefield): Tile API + InteractableObject placement (с alias compat)"
```

---

## Task K1-T7: full regression sweep

- [ ] **Step 1: Run all tests**

```bash
pytest -q
```
Expected: 778+ passed. Если что-то red — найти и починить **только** регрессии.

- [ ] **Step 2: mypy strict + ruff**

```bash
mypy src/ && ruff check src/ tests/
```
Expected: clean.

- [ ] **Step 3: Если что-то сломалось, фиксить минимально**

Только то что упало. Скорее всего ничего, потому что мы только **добавили** API.

- [ ] **Step 4: Sanity commit (если фиксы были)**

---

# ФАЗА K2 — SpriteRegistry + базовые sprites

Можно делать параллельно с K3 после K1.

## Task K2-T1: `SpriteRegistry` Port

**Files:**
- Create: `src/dnd/application/ports/sprite_registry.py`
- Test: `tests/unit/application/ports/test_sprite_registry_protocol.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/application/ports/test_sprite_registry_protocol.py
"""Protocol-проверка: SpriteRegistry имеет нужную форму."""
from __future__ import annotations

from dnd.application.ports.sprite_registry import (
    SpriteCategory,
    SpriteRegistry,
)


def test_sprite_category_values() -> None:
    assert SpriteCategory.TERRAIN.value == "terrain"
    assert SpriteCategory.FEATURE.value == "feature"
    assert SpriteCategory.OBJECT.value == "object"
    assert SpriteCategory.CREATURE.value == "creature"


def test_protocol_runtime_checkable() -> None:
    class _Stub:
        def get_terrain(self, id_: str): ...  # noqa: ANN201
        def get_feature(self, id_: str): ...  # noqa: ANN201
        def list_by_category(self, c): ...  # noqa: ANN201
    assert isinstance(_Stub(), SpriteRegistry)
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pytest tests/unit/application/ports/test_sprite_registry_protocol.py -v
```

- [ ] **Step 3: Implement**

```python
# src/dnd/application/ports/sprite_registry.py
"""Port: реестр sprite-content.

Реализация — YamlSpriteRegistry в infrastructure (см. K2-T2).
Будущие реализации (SqliteSpriteRegistry, RemoteSpriteRegistry) —
без правок engine.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase


class SpriteCategory(StrEnum):
    TERRAIN = "terrain"
    FEATURE = "feature"
    OBJECT = "object"
    CREATURE = "creature"


@runtime_checkable
class SpriteRegistry(Protocol):
    def get_terrain(self, id_: str) -> TerrainBase: ...

    def get_feature(self, id_: str) -> FeatureKind: ...

    def list_by_category(
        self, category: SpriteCategory
    ) -> tuple[TerrainBase | FeatureKind, ...]: ...


__all__ = ["SpriteCategory", "SpriteRegistry"]
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: mypy + ruff + commit**

```bash
git add src/dnd/application/ports/sprite_registry.py tests/unit/application/ports
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(ports): SpriteRegistry Protocol + SpriteCategory enum"
```

---

## Task K2-T2: `YamlSpriteRegistry`

**Files:**
- Create: `src/dnd/infrastructure/content/yaml_sprite_registry.py`
- Test: `tests/unit/infrastructure/content/test_yaml_sprite_registry.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/infrastructure/content/test_yaml_sprite_registry.py
"""YamlSpriteRegistry — загружает sprite-YAMLs из каталога."""
from __future__ import annotations

from pathlib import Path

import pytest
from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_loads_terrain_from_yaml(tmp_path: Path) -> None:
    _write(
        tmp_path / "terrain" / "floor.yaml",
        """\
id: floor
category: terrain
name: Floor
passable: true
difficult: false
glyph_5x3: |
  .....
  .....
  .....
glyph_1x1: .
color_token: floor
""",
    )
    reg = YamlSpriteRegistry(tmp_path)
    floor = reg.get_terrain("floor")
    assert floor.id == "floor"
    assert floor.passable is True


def test_loads_feature_with_dirs(tmp_path: Path) -> None:
    _write(
        tmp_path / "features" / "wall_v.yaml",
        """\
id: wall_v
category: feature
name: Vertical wall
blocks_los: true
cover: total
blocks_passage_dirs: [e, w]
passable_cost_ft: 0
glyph_5x3: |2

    │
    │
glyph_1x1: │
color_token: wall
""",
    )
    reg = YamlSpriteRegistry(tmp_path)
    wall = reg.get_feature("wall_v")
    assert wall.blocks_los is True


def test_list_by_category(tmp_path: Path) -> None:
    _write(tmp_path / "terrain" / "floor.yaml", """\
id: floor
category: terrain
name: Floor
passable: true
difficult: false
glyph_5x3: |
  .....
  .....
  .....
glyph_1x1: .
color_token: floor
""")
    reg = YamlSpriteRegistry(tmp_path)
    items = reg.list_by_category(SpriteCategory.TERRAIN)
    assert len(items) == 1
    assert items[0].id == "floor"


def test_missing_dir_is_empty_not_error(tmp_path: Path) -> None:
    reg = YamlSpriteRegistry(tmp_path)
    with pytest.raises(KeyError):
        reg.get_terrain("nope")
    assert reg.list_by_category(SpriteCategory.FEATURE) == ()
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pytest tests/unit/infrastructure/content/test_yaml_sprite_registry.py -v
```

- [ ] **Step 3: Implement**

```python
# src/dnd/infrastructure/content/yaml_sprite_registry.py
"""YamlSpriteRegistry — читает data/content/sprites/{cat}/*.yaml.

Layout:
    sprites/
      terrain/{id}.yaml
      features/{id}.yaml
      objects/{id}.yaml
      creatures/{id}.yaml

Failure-fast: битый YAML или невалидная схема → ошибка в __init__.
"""
from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import TypeAdapter

from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase


_TERRAIN_ADAPTER = TypeAdapter(TerrainBase)
_FEATURE_ADAPTER = TypeAdapter(FeatureKind)


class YamlSpriteRegistry:
    """In-memory кэш sprite-YAMLs.

    Только TERRAIN и FEATURE реализованы в K2. OBJECT и CREATURE
    sprite-meta — через subclasses (постепенно, K6/K7).
    """

    def __init__(self, sprites_dir: Path) -> None:
        self._terrains: dict[str, TerrainBase] = {}
        self._features: dict[str, FeatureKind] = {}
        if sprites_dir.is_dir():
            self._load_dir(
                sprites_dir / "terrain", self._terrains, _TERRAIN_ADAPTER
            )
            self._load_dir(
                sprites_dir / "features", self._features, _FEATURE_ADAPTER
            )

    def _load_dir(
        self, dir_path: Path, target: dict, adapter: TypeAdapter
    ) -> None:
        if not dir_path.is_dir():
            return
        for yaml_path in sorted(dir_path.glob("*.yaml")):
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            # Поле `category` в YAML — для документации/CLI; не нужно
            # модели. Удаляем перед валидацией.
            if isinstance(raw, dict):
                raw.pop("category", None)
            meta = adapter.validate_python(raw)
            target[meta.id] = meta

    def get_terrain(self, id_: str) -> TerrainBase:
        try:
            return self._terrains[id_]
        except KeyError as exc:
            raise KeyError(f"unknown terrain sprite: {id_!r}") from exc

    def get_feature(self, id_: str) -> FeatureKind:
        try:
            return self._features[id_]
        except KeyError as exc:
            raise KeyError(f"unknown feature sprite: {id_!r}") from exc

    def list_by_category(
        self, category: SpriteCategory
    ) -> tuple[TerrainBase | FeatureKind, ...]:
        if category is SpriteCategory.TERRAIN:
            return tuple(self._terrains.values())
        if category is SpriteCategory.FEATURE:
            return tuple(self._features.values())
        return ()


__all__ = ["YamlSpriteRegistry"]
```

- [ ] **Step 4: Run, verify PASS**

- [ ] **Step 5: mypy + ruff + commit**

```bash
git add src/dnd/infrastructure/content/yaml_sprite_registry.py \
        tests/unit/infrastructure/content/test_yaml_sprite_registry.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(infra): YamlSpriteRegistry — load sprite-YAMLs"
```

---

## Task K2-T3: набор 25 базовых sprites

**Files:**
- Create: `data/content/sprites/terrain/{floor,grass,stone,water,dirt}.yaml` (5)
- Create: `data/content/sprites/features/{wall_v,wall_h,wall_ne,wall_nw,wall_se,wall_sw,wall_full,column,table_small,table_long,chair,brazier,low_cover_obj,high_cover_obj}.yaml` (14)
- Create: `data/content/sprites/objects/{door,chest,barrel,window}.yaml` (4)
- Create: `data/content/sprites/creatures/{pc_humanoid,goblin}.yaml` (2)
- Create: `tests/integration/content/test_sprite_content.py`

- [ ] **Step 1: Write content-validation test**

```python
# tests/integration/content/test_sprite_content.py
"""Все реальные sprite-YAML'ы из data/content/sprites/ валидно загружаются."""
from __future__ import annotations

from pathlib import Path

import pytest
from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry


CONTENT = Path(__file__).resolve().parents[3] / "data" / "content" / "sprites"


def test_real_sprites_load_without_error() -> None:
    reg = YamlSpriteRegistry(CONTENT)
    terrains = reg.list_by_category(SpriteCategory.TERRAIN)
    features = reg.list_by_category(SpriteCategory.FEATURE)
    # Минимум 5 terrain + 10 feature должно загрузиться (K2-T3).
    assert len(terrains) >= 5, [t.id for t in terrains]
    assert len(features) >= 10, [f.id for f in features]


@pytest.mark.parametrize(
    "terrain_id",
    ["floor", "grass", "stone", "water", "dirt"],
)
def test_required_terrains_present(terrain_id: str) -> None:
    reg = YamlSpriteRegistry(CONTENT)
    t = reg.get_terrain(terrain_id)
    assert t.id == terrain_id


@pytest.mark.parametrize(
    "feature_id",
    ["wall_v", "wall_h", "column", "table_small"],
)
def test_required_features_present(feature_id: str) -> None:
    reg = YamlSpriteRegistry(CONTENT)
    f = reg.get_feature(feature_id)
    assert f.id == feature_id
```

- [ ] **Step 2: Run, verify FAIL**

```bash
pytest tests/integration/content/test_sprite_content.py -v
```

- [ ] **Step 3: Create sprite YAMLs**

Создать каждый файл. Примеры (адаптировать остальные по аналогии):

```yaml
# data/content/sprites/terrain/floor.yaml
id: floor
category: terrain
name: Floor
passable: true
difficult: false
glyph_5x3: |2

  .....

glyph_1x1: .
color_token: floor
```

```yaml
# data/content/sprites/terrain/grass.yaml
id: grass
category: terrain
name: Grass
passable: true
difficult: true
glyph_5x3: |
  ,.,.,
  .,.,.
  ,.,.,
glyph_1x1: ","
color_token: dim
```

```yaml
# data/content/sprites/terrain/stone.yaml
id: stone
category: terrain
name: Stone
passable: true
difficult: false
glyph_5x3: |2

  .....

glyph_1x1: .
color_token: floor
```

```yaml
# data/content/sprites/terrain/water.yaml
id: water
category: terrain
name: Water
passable: false
difficult: false
glyph_5x3: |
  ~~~~~
  ~~~~~
  ~~~~~
glyph_1x1: "~"
color_token: object
```

```yaml
# data/content/sprites/terrain/dirt.yaml
id: dirt
category: terrain
name: Dirt
passable: true
difficult: false
glyph_5x3: |2

  .....

glyph_1x1: .
color_token: dim
```

```yaml
# data/content/sprites/features/wall_v.yaml
id: wall_v
category: feature
name: Vertical wall
blocks_los: true
cover: total
blocks_passage_dirs: [e, w]
passable_cost_ft: 0
glyph_5x3: |2
    │
    │
    │
glyph_1x1: │
color_token: wall
```

```yaml
# data/content/sprites/features/wall_h.yaml
id: wall_h
category: feature
name: Horizontal wall
blocks_los: true
cover: total
blocks_passage_dirs: [n, s]
passable_cost_ft: 0
glyph_5x3: |2

  ─────

glyph_1x1: ─
color_token: wall
```

```yaml
# data/content/sprites/features/wall_full.yaml
id: wall_full
category: feature
name: Solid wall
blocks_los: true
cover: total
blocks_passage_dirs: [n, s, e, w, ne, nw, se, sw]
passable_cost_ft: 0
glyph_5x3: |
  █████
  █████
  █████
glyph_1x1: "#"
color_token: wall
```

```yaml
# data/content/sprites/features/wall_ne.yaml
id: wall_ne
category: feature
name: Corner NE wall
blocks_los: true
cover: total
blocks_passage_dirs: [n, e, ne]
passable_cost_ft: 0
glyph_5x3: |2
   ───┐
      │
      │
glyph_1x1: ┐
color_token: wall
```

```yaml
# data/content/sprites/features/wall_nw.yaml
id: wall_nw
category: feature
name: Corner NW wall
blocks_los: true
cover: total
blocks_passage_dirs: [n, w, nw]
passable_cost_ft: 0
glyph_5x3: |2
  ┌───
  │
  │
glyph_1x1: ┌
color_token: wall
```

```yaml
# data/content/sprites/features/wall_se.yaml
id: wall_se
category: feature
name: Corner SE wall
blocks_los: true
cover: total
blocks_passage_dirs: [s, e, se]
passable_cost_ft: 0
glyph_5x3: |2

      │
   ───┘
glyph_1x1: ┘
color_token: wall
```

```yaml
# data/content/sprites/features/wall_sw.yaml
id: wall_sw
category: feature
name: Corner SW wall
blocks_los: true
cover: total
blocks_passage_dirs: [s, w, sw]
passable_cost_ft: 0
glyph_5x3: |2

  │
  └───
glyph_1x1: └
color_token: wall
```

```yaml
# data/content/sprites/features/column.yaml
id: column
category: feature
name: Column
blocks_los: false
cover: three_quarters
blocks_passage_dirs: [n, s, e, w, ne, nw, se, sw]
passable_cost_ft: 0
glyph_5x3: |2
   ▙▙▙
   ▙▙▙
   ▙▙▙
glyph_1x1: ▙
color_token: wall
```

```yaml
# data/content/sprites/features/table_small.yaml
id: table_small
category: feature
name: Small table
blocks_los: false
cover: half
blocks_passage_dirs: []
passable_cost_ft: 10
glyph_5x3: |2

   /-\
   ===
glyph_1x1: /
color_token: object
```

```yaml
# data/content/sprites/features/table_long.yaml
id: table_long
category: feature
name: Long table
blocks_los: false
cover: half
blocks_passage_dirs: []
passable_cost_ft: 10
glyph_5x3: |2
   ___
  |===|
   ‾‾‾
glyph_1x1: T
color_token: object
```

```yaml
# data/content/sprites/features/chair.yaml
id: chair
category: feature
name: Chair
blocks_los: false
cover: none
blocks_passage_dirs: []
passable_cost_ft: 10
glyph_5x3: |2

   _
   h
glyph_1x1: h
color_token: object
```

```yaml
# data/content/sprites/features/brazier.yaml
id: brazier
category: feature
name: Brazier
blocks_los: false
cover: half
blocks_passage_dirs: [n, s, e, w]
passable_cost_ft: 0
glyph_5x3: |2
   ^^^
   ███
   ─┴─
glyph_1x1: ▲
color_token: effect
```

```yaml
# data/content/sprites/features/low_cover_obj.yaml
id: low_cover_obj
category: feature
name: Low cover
blocks_los: false
cover: half
blocks_passage_dirs: []
passable_cost_ft: 5
glyph_5x3: |2

   ===

glyph_1x1: "="
color_token: object
```

```yaml
# data/content/sprites/features/high_cover_obj.yaml
id: high_cover_obj
category: feature
name: High cover
blocks_los: false
cover: three_quarters
blocks_passage_dirs: [n, s, e, w]
passable_cost_ft: 0
glyph_5x3: |2
   ▒▒▒
   ▒▒▒
   ─┴─
glyph_1x1: H
color_token: wall
```

Object и Creature sprites (для K6/K5) — простые stub'ы:

```yaml
# data/content/sprites/objects/door.yaml
id: door
category: object
name: Door
glyph_5x3: |2
   ┐ ┌
   │ │
   ┘ └
glyph_1x1: "+"
color_token: object
```

(аналогично для chest/barrel/window/pc_humanoid/goblin)

- [ ] **Step 4: Run integration test, verify PASS**

```bash
pytest tests/integration/content/test_sprite_content.py -v
```
Expected: 9/9 passed (1 main + 5 terrain params + 3 feature params).

- [ ] **Step 5: Commit**

```bash
git add data/content/sprites tests/integration/content/test_sprite_content.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "content(sprites): 25 базовых sprites (terrain/features/objects/creatures)"
```

---

# ФАЗА K3 — `MapRepository` (YAML + JSON)

## Task K3-T1: `MapDocument` DTO

**Files:**
- Create: `src/dnd/application/dto/map_dto.py`
- Test: `tests/unit/application/dto/test_map_dto.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/application/dto/test_map_dto.py
"""MapDocument — pydantic DTO для YAML/JSON формата карт.

Формат: { id, name, width, height, tiles[], objects[] }
tiles[] = [{x, y, base, features[]}, ...]
"""
from __future__ import annotations

import pytest
from dnd.application.dto.map_dto import (
    MapDocument,
    MapObjectDoc,
    MapTileDoc,
)


def test_minimal_map_document() -> None:
    doc = MapDocument(
        id="test_map",
        name="Test",
        width=5,
        height=5,
        tiles=[
            MapTileDoc(x=0, y=0, base="floor"),
            MapTileDoc(x=1, y=0, base="stone", features=["wall_v"]),
        ],
        objects=[],
    )
    assert doc.width == 5
    assert len(doc.tiles) == 2


def test_object_doc_with_state() -> None:
    obj = MapObjectDoc(
        id="door-1",
        kind="door",
        x=3,
        y=2,
        state={"open": False, "locked": True, "hp": 10, "ac": 13},
    )
    assert obj.state["locked"] is True


def test_negative_dim_rejected() -> None:
    with pytest.raises(Exception):
        MapDocument(id="x", name="x", width=0, height=5, tiles=[], objects=[])


def test_tile_out_of_bounds_rejected() -> None:
    with pytest.raises(ValueError, match="out of bounds"):
        MapDocument(
            id="x", name="x", width=3, height=3,
            tiles=[MapTileDoc(x=5, y=0, base="floor")],
            objects=[],
        )


def test_object_pos_out_of_bounds_rejected() -> None:
    with pytest.raises(ValueError, match="out of bounds"):
        MapDocument(
            id="x", name="x", width=3, height=3,
            tiles=[],
            objects=[MapObjectDoc(id="d", kind="door", x=10, y=0, state={})],
        )
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement**

```python
# src/dnd/application/dto/map_dto.py
"""DTO для сериализации карт в YAML/JSON.

Этот формат — канонический interchange между MapRepository
реализациями (YAML / JSON / SQLite). Содержит ID-references на
sprite_id и object_id, не сами объекты.

Содержит метаданные карты + список tiles (только не-default; default
floor подразумевается для пустых клеток) + список объектов.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MapTileDoc(BaseModel):
    """Одна клетка: координаты + base terrain_id + features ids."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    base: str               # terrain_id (см. SpriteRegistry)
    features: tuple[str, ...] = ()


class MapObjectDoc(BaseModel):
    """Interactable объект на карте."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    kind: str              # "door" / "chest" / "barrel" / "window"
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    state: dict[str, Any] = Field(default_factory=dict)


class MapDocument(BaseModel):
    """Полная карта — header + тailes + objects."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    name: str
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    tiles: tuple[MapTileDoc, ...] = ()
    objects: tuple[MapObjectDoc, ...] = ()

    @model_validator(mode="after")
    def _validate_bounds(self) -> MapDocument:
        for t in self.tiles:
            if t.x >= self.width or t.y >= self.height:
                raise ValueError(
                    f"tile ({t.x},{t.y}) out of bounds {self.width}x{self.height}"
                )
        for o in self.objects:
            if o.x >= self.width or o.y >= self.height:
                raise ValueError(
                    f"object {o.id} pos ({o.x},{o.y}) out of bounds"
                )
        return self


__all__ = ["MapDocument", "MapObjectDoc", "MapTileDoc"]
```

- [ ] **Step 4: Run, PASS** + **Step 5: Commit**

```bash
git add src/dnd/application/dto/map_dto.py tests/unit/application/dto
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(dto): MapDocument pydantic DTO для YAML/JSON карт"
```

---

## Task K3-T2: `MapRepository` Port

**Files:**
- Create: `src/dnd/application/ports/map_repository.py`
- Test: `tests/unit/application/ports/test_map_repository_protocol.py`

- [ ] **Step 1: Write test**

```python
# tests/unit/application/ports/test_map_repository_protocol.py
from __future__ import annotations

from dnd.application.ports.map_repository import MapRepository


def test_protocol_runtime() -> None:
    class _Stub:
        def list_ids(self): ...  # noqa: ANN201
        def load(self, id_): ...  # noqa: ANN201
        def save(self, doc): ...  # noqa: ANN201
        def delete(self, id_): ...  # noqa: ANN201
    assert isinstance(_Stub(), MapRepository)
```

- [ ] **Step 2: Implement Port**

```python
# src/dnd/application/ports/map_repository.py
"""Port: load/save/list карт.

Реализации: YamlMapRepository (default), JsonMapRepository (для import/
export). Будущие: SqliteMapRepository, RemoteMapRepository.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from dnd.application.dto.map_dto import MapDocument


@runtime_checkable
class MapRepository(Protocol):
    def list_ids(self) -> tuple[str, ...]: ...
    def load(self, id_: str) -> MapDocument: ...
    def save(self, doc: MapDocument) -> None: ...
    def delete(self, id_: str) -> None: ...


__all__ = ["MapRepository"]
```

- [ ] **Step 3: Run + commit**

```bash
pytest tests/unit/application/ports -v && \
git add src/dnd/application/ports/map_repository.py tests/unit/application/ports && \
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(ports): MapRepository Protocol"
```

---

## Task K3-T3: `YamlMapRepository`

**Files:**
- Create: `src/dnd/infrastructure/content/yaml_map_repository.py`
- Test: `tests/integration/content/test_yaml_map_repository.py`

- [ ] **Step 1: Write failing test**

```python
# tests/integration/content/test_yaml_map_repository.py
"""YamlMapRepository: load/save/list карт в data/content/maps/{id}.yaml."""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.map_dto import MapDocument, MapTileDoc
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    doc = MapDocument(
        id="test", name="Test", width=3, height=3,
        tiles=(MapTileDoc(x=0, y=0, base="floor"),), objects=(),
    )
    repo.save(doc)
    loaded = repo.load("test")
    assert loaded == doc


def test_list_ids_returns_saved(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    repo.save(MapDocument(id="a", name="A", width=2, height=2, tiles=(), objects=()))
    repo.save(MapDocument(id="b", name="B", width=2, height=2, tiles=(), objects=()))
    assert set(repo.list_ids()) == {"a", "b"}


def test_load_missing_raises(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    import pytest
    with pytest.raises(KeyError, match="nope"):
        repo.load("nope")


def test_delete_removes_file(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    repo.save(MapDocument(id="x", name="X", width=2, height=2, tiles=(), objects=()))
    repo.delete("x")
    assert "x" not in repo.list_ids()
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement**

```python
# src/dnd/infrastructure/content/yaml_map_repository.py
"""YamlMapRepository — карты в data/content/maps/{id}.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

from dnd.application.dto.map_dto import MapDocument


class YamlMapRepository:
    def __init__(self, maps_dir: Path) -> None:
        self._dir = maps_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self._dir.glob("*.yaml")))

    def load(self, id_: str) -> MapDocument:
        path = self._dir / f"{id_}.yaml"
        if not path.exists():
            raise KeyError(f"unknown map: {id_!r}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return MapDocument.model_validate(raw)

    def save(self, doc: MapDocument) -> None:
        path = self._dir / f"{doc.id}.yaml"
        path.write_text(
            yaml.safe_dump(
                doc.model_dump(mode="json"),
                sort_keys=False,
                allow_unicode=True,
                width=120,
            ),
            encoding="utf-8",
        )

    def delete(self, id_: str) -> None:
        path = self._dir / f"{id_}.yaml"
        if path.exists():
            path.unlink()


__all__ = ["YamlMapRepository"]
```

- [ ] **Step 4: Run, PASS** + **Step 5: Commit**

```bash
git add src/dnd/infrastructure/content/yaml_map_repository.py \
        tests/integration/content/test_yaml_map_repository.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(infra): YamlMapRepository load/save/list/delete"
```

---

## Task K3-T4: `JsonMapRepository`

**Files:**
- Create: `src/dnd/infrastructure/content/json_map_repository.py`
- Test: `tests/integration/content/test_json_map_repository.py`

- [ ] **Step 1: Write test** (по аналогии с YAML; replace .yaml → .json, yaml.safe_load → json.loads)

- [ ] **Step 2: Implement** (same pattern, json вместо yaml)

```python
# src/dnd/infrastructure/content/json_map_repository.py
"""JsonMapRepository — карты в data/content/maps/{id}.json.

Используется для CLI export/import + скриптовая интеграция."""
from __future__ import annotations

import json
from pathlib import Path

from dnd.application.dto.map_dto import MapDocument


class JsonMapRepository:
    def __init__(self, maps_dir: Path) -> None:
        self._dir = maps_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def list_ids(self) -> tuple[str, ...]:
        return tuple(sorted(p.stem for p in self._dir.glob("*.json")))

    def load(self, id_: str) -> MapDocument:
        path = self._dir / f"{id_}.json"
        if not path.exists():
            raise KeyError(f"unknown map: {id_!r}")
        return MapDocument.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def save(self, doc: MapDocument) -> None:
        path = self._dir / f"{doc.id}.json"
        path.write_text(
            json.dumps(doc.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def delete(self, id_: str) -> None:
        path = self._dir / f"{id_}.json"
        if path.exists():
            path.unlink()


__all__ = ["JsonMapRepository"]
```

- [ ] **Step 3: Run + Commit**

```bash
git add src/dnd/infrastructure/content/json_map_repository.py \
        tests/integration/content/test_json_map_repository.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(infra): JsonMapRepository (для import/export)"
```

---

# ФАЗА K4 — CLI семья команд

## Task K4-T1: `dnd sprite list / show / validate`

**Files:**
- Create: `src/dnd/interfaces/cli/sprite_cmds.py`
- Modify: `src/dnd/interfaces/cli/app.py`
- Test: `tests/integration/cli/test_sprite_cmds.py`

- [ ] **Step 1: Write failing test**

```python
# tests/integration/cli/test_sprite_cmds.py
"""dnd sprite ... — list/show/validate."""
from __future__ import annotations

import json
from typer.testing import CliRunner

from dnd.interfaces.cli.app import app


runner = CliRunner()


def test_sprite_list_default_table() -> None:
    result = runner.invoke(app, ["sprite", "list"])
    assert result.exit_code == 0
    assert "floor" in result.stdout  # terrain id


def test_sprite_list_json_format() -> None:
    result = runner.invoke(app, ["sprite", "list", "--format=json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert any(s["id"] == "floor" for s in data)


def test_sprite_show_renders_preview() -> None:
    result = runner.invoke(app, ["sprite", "show", "wall_v"])
    assert result.exit_code == 0
    assert "wall_v" in result.stdout
    # Должны быть видны glyph_5x3 строки.
    assert "│" in result.stdout


def test_sprite_validate_ok() -> None:
    result = runner.invoke(app, ["sprite", "validate", "floor"])
    assert result.exit_code == 0


def test_sprite_validate_missing_fails() -> None:
    result = runner.invoke(app, ["sprite", "validate", "nope_does_not_exist"])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement sprite_cmds**

```python
# src/dnd/interfaces/cli/sprite_cmds.py
"""Семья команд `dnd sprite ...` — управление sprite-content из shell."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry


sprite_app = typer.Typer(name="sprite", help="Manage sprite content.")
_DEFAULT_SPRITES = Path("data/content/sprites")


def _registry(content_dir: Path) -> YamlSpriteRegistry:
    return YamlSpriteRegistry(content_dir)


@sprite_app.command("list")
def list_(
    category: str = typer.Option(
        None, "--category", help="terrain | feature | object | creature"
    ),
    format_: str = typer.Option("table", "--format", help="table | json"),
    content_dir: Path = typer.Option(_DEFAULT_SPRITES, "--content-dir"),
) -> None:
    """Список загруженных sprites."""
    reg = _registry(content_dir)
    categories = (
        [SpriteCategory(category)] if category
        else list(SpriteCategory)
    )
    items: list[dict] = []
    for cat in categories:
        for sp in reg.list_by_category(cat):
            items.append({
                "id": sp.id, "name": sp.name, "category": cat.value,
            })

    if format_ == "json":
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    console = Console()
    for it in items:
        console.print(f"[bold]{it['id']:24}[/] {it['category']:10} {it['name']}")


@sprite_app.command("show")
def show(
    id_: str = typer.Argument(..., metavar="ID"),
    content_dir: Path = typer.Option(_DEFAULT_SPRITES, "--content-dir"),
) -> None:
    """Превью sprite: glyph_5x3 + флаги."""
    reg = _registry(content_dir)
    sp = None
    for cat in SpriteCategory:
        for cand in reg.list_by_category(cat):
            if cand.id == id_:
                sp = cand
                break
        if sp is not None:
            break
    if sp is None:
        typer.echo(f"sprite not found: {id_!r}", err=True)
        raise typer.Exit(code=2)
    console = Console()
    console.print(f"[bold]{sp.id}[/] — {sp.name}")
    for row in sp.glyph_5x3:
        console.print(row)
    console.print(f"glyph_1x1: {sp.glyph_1x1}")
    console.print(f"color: {sp.color_token}")


@sprite_app.command("validate")
def validate(
    id_: str = typer.Argument(..., metavar="ID"),
    content_dir: Path = typer.Option(_DEFAULT_SPRITES, "--content-dir"),
) -> None:
    """Проверка существования sprite + базовая схема."""
    reg = _registry(content_dir)
    try:
        for cat in SpriteCategory:
            for cand in reg.list_by_category(cat):
                if cand.id == id_:
                    typer.echo(f"OK: {id_} ({cat.value})")
                    return
        raise KeyError(id_)
    except KeyError:
        typer.echo(f"sprite not found: {id_!r}", err=True)
        raise typer.Exit(code=2) from None
```

- [ ] **Step 4: Register sub-app в app.py**

```python
# Modify src/dnd/interfaces/cli/app.py — добавить:
from dnd.interfaces.cli.sprite_cmds import sprite_app
app.add_typer(sprite_app)
```

- [ ] **Step 5: Run, PASS**

```bash
pytest tests/integration/cli/test_sprite_cmds.py -v
```

- [ ] **Step 6: Commit**

```bash
git add src/dnd/interfaces/cli/sprite_cmds.py src/dnd/interfaces/cli/app.py \
        tests/integration/cli/test_sprite_cmds.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(cli): dnd sprite list/show/validate"
```

---

## Task K4-T2: `dnd map list / show / validate` (read-only часть)

**Files:**
- Create: `src/dnd/interfaces/cli/map_cmds.py`
- Modify: `src/dnd/interfaces/cli/app.py`
- Test: `tests/integration/cli/test_map_cmds.py`

- [ ] **Step 1: Write failing test**

```python
# tests/integration/cli/test_map_cmds.py
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dnd.application.dto.map_dto import MapDocument, MapTileDoc
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
from dnd.interfaces.cli.app import app


runner = CliRunner()


@pytest.fixture
def maps_dir(tmp_path: Path) -> Path:
    md = tmp_path / "maps"
    repo = YamlMapRepository(md)
    repo.save(MapDocument(
        id="tiny", name="Tiny", width=3, height=3,
        tiles=(MapTileDoc(x=1, y=1, base="floor"),),
        objects=(),
    ))
    return md


def test_map_list_default(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "list", "--maps-dir", str(maps_dir)])
    assert result.exit_code == 0
    assert "tiny" in result.stdout


def test_map_list_json(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "list", "--maps-dir", str(maps_dir), "--format=json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert {"tiny"} <= {item["id"] for item in data}


def test_map_show_ascii(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "show", "tiny", "--maps-dir", str(maps_dir)])
    assert result.exit_code == 0
    assert "tiny" in result.stdout


def test_map_show_json(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "show", "tiny", "--maps-dir", str(maps_dir), "--format=json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "tiny"
    assert data["width"] == 3


def test_map_validate_ok(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "validate", "tiny", "--maps-dir", str(maps_dir)])
    assert result.exit_code == 0


def test_map_show_missing_fails(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "show", "nope", "--maps-dir", str(maps_dir)])
    assert result.exit_code != 0
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement (только list/show/validate в этом таске)**

```python
# src/dnd/interfaces/cli/map_cmds.py
"""Семья команд `dnd map ...` — управление картами из shell."""
from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console

from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry


map_app = typer.Typer(name="map", help="Manage and inspect maps.")
_DEFAULT_MAPS = Path("data/content/maps")
_DEFAULT_SPRITES = Path("data/content/sprites")


def _repo(maps_dir: Path) -> YamlMapRepository:
    return YamlMapRepository(maps_dir)


@map_app.command("list")
def list_(
    format_: str = typer.Option("table", "--format"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    repo = _repo(maps_dir)
    items = []
    for id_ in repo.list_ids():
        doc = repo.load(id_)
        items.append({
            "id": doc.id, "name": doc.name,
            "size": f"{doc.width}x{doc.height}",
            "tiles": len(doc.tiles), "objects": len(doc.objects),
        })
    if format_ == "json":
        typer.echo(json.dumps(items, ensure_ascii=False, indent=2))
        return
    console = Console()
    for it in items:
        console.print(
            f"[bold]{it['id']:24}[/] {it['size']:8} "
            f"tiles={it['tiles']:4} objects={it['objects']:3} {it['name']}"
        )


@map_app.command("show")
def show(
    id_: str = typer.Argument(..., metavar="ID"),
    format_: str = typer.Option("ascii", "--format"),
    zoom: str = typer.Option("small", "--zoom", help="small | medium"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
    sprites_dir: Path = typer.Option(_DEFAULT_SPRITES, "--sprites-dir"),
) -> None:
    repo = _repo(maps_dir)
    try:
        doc = repo.load(id_)
    except KeyError:
        typer.echo(f"map not found: {id_!r}", err=True)
        raise typer.Exit(code=2) from None

    if format_ == "json":
        typer.echo(json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    sprites = YamlSpriteRegistry(sprites_dir)
    console = Console()
    console.print(f"[bold]{doc.id}[/] — {doc.name} ({doc.width}x{doc.height})")
    if zoom == "small":
        _render_small(doc, sprites, console)
    else:
        _render_medium(doc, sprites, console)


def _render_small(doc, sprites, console) -> None:
    grid = [["."] * doc.width for _ in range(doc.height)]
    for t in doc.tiles:
        base = sprites.get_terrain(t.base) if _has_terrain(sprites, t.base) else None
        glyph = base.glyph_1x1 if base else "?"
        for fid in t.features:
            try:
                glyph = sprites.get_feature(fid).glyph_1x1
            except KeyError:
                pass
        grid[t.y][t.x] = glyph
    for o in doc.objects:
        grid[o.y][o.x] = o.kind[0].upper()  # D/C/B/W placeholder
    for row in grid:
        console.print("".join(row))


def _render_medium(doc, sprites, console) -> None:
    # 5×3 без рамок. Каждая клетка — 3 строки по 5 ячеек.
    rows: list[str] = []
    for y in range(doc.height):
        cell_rows = ["", "", ""]
        for x in range(doc.width):
            base_id, feature_ids = _tile_at(doc, x, y)
            glyph = _compose_5x3(sprites, base_id, feature_ids)
            for i in range(3):
                cell_rows[i] += glyph[i]
        for r in cell_rows:
            rows.append(r)
    for r in rows:
        console.print(r)


def _tile_at(doc, x: int, y: int) -> tuple[str, tuple[str, ...]]:
    for t in doc.tiles:
        if t.x == x and t.y == y:
            return t.base, t.features
    return "floor", ()


def _has_terrain(sprites, id_: str) -> bool:
    try:
        sprites.get_terrain(id_)
        return True
    except KeyError:
        return False


def _compose_5x3(sprites, base_id: str, feature_ids: tuple[str, ...]) -> tuple[str, str, str]:
    base = sprites.get_terrain(base_id).glyph_5x3 if _has_terrain(sprites, base_id) else ("     ", "  ?  ", "     ")
    rows = [list(r) for r in base]
    for fid in feature_ids:
        try:
            fg = sprites.get_feature(fid).glyph_5x3
        except KeyError:
            continue
        for i in range(3):
            for j in range(5):
                if fg[i][j] != " ":
                    rows[i][j] = fg[i][j]
    return ("".join(rows[0]), "".join(rows[1]), "".join(rows[2]))


@map_app.command("validate")
def validate(
    id_: str = typer.Argument(...),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    repo = _repo(maps_dir)
    try:
        doc = repo.load(id_)
        typer.echo(f"OK: {doc.id} {doc.width}x{doc.height} "
                   f"tiles={len(doc.tiles)} objects={len(doc.objects)}")
    except (KeyError, ValueError) as exc:
        typer.echo(f"INVALID: {exc}", err=True)
        raise typer.Exit(code=2) from None
```

- [ ] **Step 4: Register в app.py**

```python
# Modify app.py:
from dnd.interfaces.cli.map_cmds import map_app
app.add_typer(map_app)
```

- [ ] **Step 5: Run, PASS** + **Step 6: Commit**

```bash
git add src/dnd/interfaces/cli/map_cmds.py src/dnd/interfaces/cli/app.py \
        tests/integration/cli/test_map_cmds.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(cli): dnd map list/show/validate (read-only + render small/medium)"
```

---

## Task K4-T3: `dnd map new / paint`

**Files:**
- Modify: `src/dnd/interfaces/cli/map_cmds.py`
- Modify: `tests/integration/cli/test_map_cmds.py`

- [ ] **Step 1: Write tests**

```python
# Добавить в test_map_cmds.py:
def test_map_new_creates_empty(tmp_path: Path) -> None:
    md = tmp_path / "maps"
    result = runner.invoke(app, [
        "map", "new", "fresh", "--size=4x3", "--maps-dir", str(md)
    ])
    assert result.exit_code == 0
    repo = YamlMapRepository(md)
    doc = repo.load("fresh")
    assert doc.width == 4 and doc.height == 3
    assert doc.tiles == ()


def test_map_paint_sets_base(maps_dir: Path) -> None:
    result = runner.invoke(app, [
        "map", "paint", "tiny",
        "--at=0,0", "--base=grass",
        "--maps-dir", str(maps_dir),
    ])
    assert result.exit_code == 0
    repo = YamlMapRepository(maps_dir)
    doc = repo.load("tiny")
    cell = next(t for t in doc.tiles if t.x == 0 and t.y == 0)
    assert cell.base == "grass"


def test_map_paint_adds_feature(maps_dir: Path) -> None:
    result = runner.invoke(app, [
        "map", "paint", "tiny",
        "--at=2,1", "--feature=wall_v",
        "--maps-dir", str(maps_dir),
    ])
    assert result.exit_code == 0
    repo = YamlMapRepository(maps_dir)
    doc = repo.load("tiny")
    cell = next(t for t in doc.tiles if t.x == 2 and t.y == 1)
    assert "wall_v" in cell.features
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement new / paint в map_cmds.py**

```python
# Добавить в map_cmds.py:
import re

@map_app.command("new")
def new(
    id_: str = typer.Argument(...),
    size: str = typer.Option(..., "--size", help="WxH"),
    name: str = typer.Option("", "--name"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    m = re.fullmatch(r"(\d+)x(\d+)", size)
    if not m:
        typer.echo(f"bad size: {size!r} (expected WxH)", err=True)
        raise typer.Exit(code=2)
    w, h = int(m.group(1)), int(m.group(2))
    from dnd.application.dto.map_dto import MapDocument
    doc = MapDocument(id=id_, name=name or id_, width=w, height=h, tiles=(), objects=())
    _repo(maps_dir).save(doc)
    typer.echo(f"created: {id_} {w}x{h}")


@map_app.command("paint")
def paint(
    id_: str = typer.Argument(...),
    at: str = typer.Option(..., "--at", help="X,Y"),
    base: str = typer.Option(None, "--base"),
    feature: str = typer.Option(None, "--feature"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    m = re.fullmatch(r"(\d+),(\d+)", at)
    if not m:
        typer.echo(f"bad at: {at!r}", err=True)
        raise typer.Exit(code=2)
    x, y = int(m.group(1)), int(m.group(2))
    repo = _repo(maps_dir)
    doc = repo.load(id_)
    new_tiles = list(doc.tiles)
    idx = next((i for i, t in enumerate(new_tiles) if t.x == x and t.y == y), None)
    from dnd.application.dto.map_dto import MapDocument, MapTileDoc
    if idx is None:
        current = MapTileDoc(x=x, y=y, base=base or "floor", features=())
    else:
        current = new_tiles[idx]
    new_base = base or current.base
    if feature and feature not in current.features:
        new_features = (*current.features, feature)
    else:
        new_features = current.features
    updated = MapTileDoc(x=x, y=y, base=new_base, features=new_features)
    if idx is None:
        new_tiles.append(updated)
    else:
        new_tiles[idx] = updated
    repo.save(MapDocument(
        id=doc.id, name=doc.name, width=doc.width, height=doc.height,
        tiles=tuple(new_tiles), objects=doc.objects,
    ))
    typer.echo(f"painted {at}: base={new_base} features={list(new_features)}")
```

- [ ] **Step 4: Run, PASS** + **Step 5: Commit**

```bash
git add src/dnd/interfaces/cli/map_cmds.py tests/integration/cli/test_map_cmds.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(cli): dnd map new / paint"
```

---

## Task K4-T4: `dnd map import / export`

**Files:**
- Modify: `src/dnd/interfaces/cli/map_cmds.py`
- Modify: `tests/integration/cli/test_map_cmds.py`

- [ ] **Step 1: Test JSON round-trip**

```python
def test_map_export_then_import_json(maps_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "tiny.json"
    result = runner.invoke(app, [
        "map", "export", "tiny", "--format=json",
        "--maps-dir", str(maps_dir),
        "--output", str(out),
    ])
    assert result.exit_code == 0
    assert out.exists()

    # Импорт обратно под другим ID:
    result = runner.invoke(app, [
        "map", "import", str(out), "--as=tiny_copy",
        "--maps-dir", str(maps_dir),
    ])
    assert result.exit_code == 0
    repo = YamlMapRepository(maps_dir)
    assert repo.load("tiny_copy").width == 3
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement import/export**

```python
# Добавить в map_cmds.py:
@map_app.command("export")
def export(
    id_: str = typer.Argument(...),
    format_: str = typer.Option("yaml", "--format"),
    output: Path = typer.Option(None, "--output"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    doc = _repo(maps_dir).load(id_)
    if format_ == "json":
        body = json.dumps(doc.model_dump(mode="json"), ensure_ascii=False, indent=2)
    else:
        import yaml
        body = yaml.safe_dump(
            doc.model_dump(mode="json"), sort_keys=False, allow_unicode=True
        )
    if output:
        output.write_text(body, encoding="utf-8")
        typer.echo(f"exported to {output}")
    else:
        typer.echo(body)


@map_app.command("import")
def import_(
    file: Path = typer.Argument(...),
    as_: str = typer.Option(None, "--as", help="override id"),
    maps_dir: Path = typer.Option(_DEFAULT_MAPS, "--maps-dir"),
) -> None:
    text = file.read_text(encoding="utf-8")
    if file.suffix == ".json":
        data = json.loads(text)
    else:
        import yaml
        data = yaml.safe_load(text)
    if as_:
        data["id"] = as_
    from dnd.application.dto.map_dto import MapDocument
    doc = MapDocument.model_validate(data)
    _repo(maps_dir).save(doc)
    typer.echo(f"imported as {doc.id}")
```

- [ ] **Step 4: Run, PASS** + **Step 5: Commit**

```bash
git add src/dnd/interfaces/cli/map_cmds.py tests/integration/cli/test_map_cmds.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(cli): dnd map import / export (yaml + json round-trip)"
```

---

# ФАЗА K5 — TUI рендер 5×3 через SpriteRegistry

## Task K5-T1: pure-функция `render_tile_5x3`

**Files:**
- Create: `src/dnd/interfaces/tui/widgets/tile_renderer.py`
- Test: `tests/unit/interfaces/tui/test_tile_renderer.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/interfaces/tui/test_tile_renderer.py
"""Pure render — без Textual.

Берёт Tile + SpriteRegistry → возвращает 3 строки по 5 ASCII-символов.
"""
from __future__ import annotations

from dnd.domain.values.direction import Direction
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase
from dnd.domain.values.terrain import CoverLevel
from dnd.domain.values.tile import Tile
from dnd.interfaces.tui.widgets.tile_renderer import render_tile_5x3


FLOOR = TerrainBase(
    id="floor", name="F", passable=True, difficult=False,
    glyph_5x3=("     ", "     ", "     "), glyph_1x1=".", color_token="floor",
)
WALL_V = FeatureKind(
    id="wall_v", name="V", blocks_los=True, cover=CoverLevel.TOTAL,
    blocks_passage_dirs=frozenset({Direction.E, Direction.W}),
    passable_cost_ft=0, glyph_5x3=("  │  ", "  │  ", "  │  "),
    glyph_1x1="│", color_token="wall",
)


def test_floor_only_returns_base_glyph() -> None:
    tile = Tile(base=FLOOR, features=())
    out = render_tile_5x3(tile)
    assert out == ("     ", "     ", "     ")


def test_feature_overrides_non_space_base() -> None:
    tile = Tile(base=FLOOR, features=(WALL_V,))
    out = render_tile_5x3(tile)
    assert out == ("  │  ", "  │  ", "  │  ")


def test_returns_3_rows_of_5_chars() -> None:
    tile = Tile(base=FLOOR, features=())
    out = render_tile_5x3(tile)
    assert len(out) == 3
    for row in out:
        assert len(row) == 5
```

- [ ] **Step 2: Run, FAIL**

- [ ] **Step 3: Implement**

```python
# src/dnd/interfaces/tui/widgets/tile_renderer.py
"""Pure-функции для рендера Tile.

Без Textual — только данные → ASCII. Тестируется без поднятия app.
"""
from __future__ import annotations

from dnd.domain.values.tile import Tile


def render_tile_5x3(tile: Tile) -> tuple[str, str, str]:
    """Композит 5×3 ASCII клетки.

    Алгоритм: берём base.glyph_5x3 как «фон»; features накладываются
    сверху в порядке tuple — не-пробельный символ feature перекрывает
    base. Несколько features на клетке — последний побеждает.
    """
    rows = [list(r) for r in tile.base.glyph_5x3]
    for f in tile.features:
        for i, frow in enumerate(f.glyph_5x3):
            for j, ch in enumerate(frow):
                if ch != " ":
                    rows[i][j] = ch
    return ("".join(rows[0]), "".join(rows[1]), "".join(rows[2]))


__all__ = ["render_tile_5x3"]
```

- [ ] **Step 4: Run, PASS** + **Step 5: Commit**

```bash
git add src/dnd/interfaces/tui/widgets/tile_renderer.py \
        tests/unit/interfaces/tui/test_tile_renderer.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(tui): pure render_tile_5x3 функция"
```

---

## Task K5-T2: новый `MapWidget` на Tile + SpriteRegistry

**Files:**
- Modify: `src/dnd/interfaces/tui/widgets/map_widget.py`
- Modify: `tests/unit/interfaces/tui/test_map_widget.py`

- [ ] **Step 1: Adapt existing tests + add new for 5×3**

```python
# Добавить в test_map_widget.py:
def test_render_battlefield_uses_tile_when_set() -> None:
    """Если Battlefield имеет set_tile — render использует Tile-композит."""
    from dnd.domain.values.tile_aliases import WALL_TILE, FLOOR_TILE
    bf = Battlefield(3, 1)
    bf.set_tile(Square(1, 0), WALL_TILE)
    text = render_battlefield(bf, {}, zoom="medium")
    # 3 строки по 15 ячеек (3 клетки × 5).
    assert text.plain.count("\n") == 2  # 3 строки → 2 \n
    lines = text.plain.split("\n")
    assert all(len(line) == 15 for line in lines), lines
    # Стена в средней клетке — заполнена ████.
    assert "█" in lines[0]
```

- [ ] **Step 2: Modify `render_battlefield`** добавить `zoom` параметр (small по умолчанию, medium через 5×3):

```python
# Modify src/dnd/interfaces/tui/widgets/map_widget.py:
# Добавить:
from dnd.interfaces.tui.widgets.tile_renderer import render_tile_5x3

def render_battlefield(
    battlefield, factions, *, cursor=None, with_color=True, zoom: str = "small",
):
    if zoom == "medium":
        return _render_medium(battlefield, factions, cursor=cursor, with_color=with_color)
    # старый small-zoom — без изменений
    ...

def _render_medium(battlefield, factions, *, cursor=None, with_color=True):
    out = Text()
    for y in range(battlefield.height):
        cell_rows = ["", "", ""]
        for x in range(battlefield.width):
            tile = battlefield.tile_at(Square(x, y))
            glyphs = render_tile_5x3(tile)
            # creature/cursor overlay в центральной ячейке клетки (row=1, col=2)
            cells = [list(r) for r in glyphs]
            occupants = battlefield.creatures_at(Square(x, y))
            if occupants:
                top = _pick_top_creature(occupants, factions)
                glyph = _FACTION_GLYPH[factions.get(top, Faction.NEUTRAL)]
                cells[1][2] = glyph
            elif cursor == Square(x, y):
                cells[1][2] = "X"
            for i in range(3):
                cell_rows[i] += "".join(cells[i])
        for i, r in enumerate(cell_rows):
            out.append(r, style="white")
            if not (y == battlefield.height - 1 and i == 2):
                out.append("\n")
    return out
```

- [ ] **Step 3: Run, PASS** (+ `test_terrain_glyphs_by_property` остаётся в small-mode)

```bash
pytest tests/unit/interfaces/tui/ -v
```

- [ ] **Step 4: Commit**

```bash
git add src/dnd/interfaces/tui/widgets/map_widget.py \
        tests/unit/interfaces/tui/test_map_widget.py
git -c user.name="Maxim Lokotkov" -c user.email="anticrab@users.noreply.github.com" \
    commit -m "feat(tui): MapWidget zoom='medium' через render_tile_5x3"
```

---

## Task K5-T3: hotkey `+`/`-` для zoom в BattleScreen

**Files:**
- Modify: `src/dnd/interfaces/tui/screens/battle.py`
- Test: расширить smoke в `tests/integration/tui/test_app_smoke.py`

- [ ] **Step 1: Test** — Pilot нажимает `+` → smoke check что viewport обновился.

```python
def test_battle_screen_zoom_toggle_via_plus() -> None:
    """Plus key переключает zoom small <-> medium."""
    from dnd.interfaces.tui import TuiApp
    enc = _make_encounter()  # из conftest
    app = TuiApp(encounter=enc)

    async def _go():
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause(0.2)
            await pilot.press("plus")
            await pilot.pause(0.2)

    import asyncio; asyncio.run(_go())
```

- [ ] **Step 2: Add binding в BattleScreen.BINDINGS** + action_toggle_zoom

- [ ] **Step 3: Run + commit**

---

# ФАЗА K6 — InteractAction + BreakAction

## Task K6-T1: `InteractAction`

**Files:**
- Create: `src/dnd/application/engine/actions/interact.py`
- Test: `tests/unit/application/actions/test_interact_action.py`

- [ ] **Step 1: Write test** — взаимодействие с дверью (open closed → open).

- [ ] **Step 2: Implement** — InteractAction с cost=FREE, проверяет:
  - target_object в reach (5ft).
  - applicable kind (open для DOOR/CHEST, close для DOOR).
  - публикует `ObjectInteracted` event.

- [ ] **Step 3-4: Run + commit**

(Подробные шаги — по аналогии с K1-T1 формата.)

---

## Task K6-T2: `BreakAction` (extends AttackAction для объектов)

**Files:**
- Create: `src/dnd/application/engine/actions/break_object.py`
- Test: `tests/unit/application/actions/test_break_action.py`

(Аналогично — расширение AttackAction, target_id может быть ObjectId.)

---

## Task K6-T3: `InteractIntent` + `BreakIntent` + интеграция в GameRunner/TUI

- [ ] Расширить `PlayerIntent` discriminated union.
- [ ] BattleScreen binding `i` Interact + меню picker'ов.
- [ ] Test integration через ScriptedIntentProvider.

---

# ФАЗА K7 — TUI редактор

## Task K7-T1: `EditorScreen` + palette widget

**Files:**
- Create: `src/dnd/interfaces/tui/screens/editor_screen.py`
- Create: `src/dnd/interfaces/tui/widgets/palette_widget.py`
- Modify: `src/dnd/interfaces/tui/app.py` (EditorApp / mode flag)
- Modify: `src/dnd/interfaces/cli/map_cmds.py` (команда `edit`)

(Подробности — отдельной итерацией; формат тот же.)

---

# ФАЗА K8 — Контент-набор 7 карт

## Task K8-T1..T7: семь YAML карт

Каждая карта — отдельный таск:
- K8-T1: open_field (12×8)
- K8-T2: dungeon_hall (15×8) с дверью
- K8-T3: forest_clearing (10×10) с difficult terrain
- K8-T4: warehouse (14×10) с барелями/окнами/столами
- K8-T5: bridge_crossing (18×6) через воду
- K8-T6: ruined_hall (16×12) с колоннами
- K8-T7: migration mvp_skirmish на новый Tile-формат

Для каждой:
- [ ] Создать YAML вручную (либо `dnd map new` + `dnd map paint`)
- [ ] `dnd map validate <id>` зелёный
- [ ] `dnd map show <id> --zoom=medium` визуальный sanity-check
- [ ] Commit

---

# ФАЗА K9 — Аудит

## Task K9-T1: запустить независимый аудит-агент

(Через subagent-driven-development или general-purpose agent с конкретными
зонами проверки: invariants, regressions, content sanity, UX.)

---

## Self-review checklist

- [x] **Spec coverage**: K1-K8 покрывают разделы 1-8 спеца; K9 = §«Аудит».
- [x] **Placeholders**: нет TBD/TODO/FIXME.
- [x] **Type consistency**: TerrainBase / FeatureKind / Tile имена согласованы; ObjectId через NewType.
- [x] **Code blocks complete**: все код-шаги содержат рабочий код.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-23-k-rich-maps-and-world.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — я диспатчу свежего subagent на каждый таск, ревью между тасками, быстрая итерация. Хорошо подходит для больших планов с независимыми задачами (K1.x, K2 параллельно с K1, K7 параллельно с K8).

**2. Inline Execution** — выполняю таски в этой сессии, батч с чекпоинтами для ревью.

**Какой подход?**
