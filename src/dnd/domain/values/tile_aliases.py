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
    id="floor",
    name="Floor",
    passable=True,
    difficult=False,
    glyph_5x3=("     ", "     ", "     "),
    glyph_1x1=".",
    color_token="floor",
)
_GRASS = TerrainBase(
    id="grass",
    name="Grass",
    passable=True,
    difficult=True,
    glyph_5x3=(",.,.,", ".,.,.", ",.,.,"),
    glyph_1x1=",",
    color_token="grass",
)
_STONE = TerrainBase(
    id="stone",
    name="Stone",
    passable=True,
    difficult=False,
    glyph_5x3=("     ", "     ", "     "),
    glyph_1x1=".",
    color_token="floor",
)

# --- FeatureKind константы ---

_WALL_FULL = FeatureKind(
    id="wall_full",
    name="Wall",
    blocks_los=True,
    cover=CoverLevel.TOTAL,
    blocks_passage_dirs=frozenset(Direction),
    passable_cost_ft=0,
    glyph_5x3=("█████", "█████", "█████"),
    glyph_1x1="#",
    color_token="wall",
)
_LOW_COVER_FEATURE = FeatureKind(
    id="low_cover_obj",
    name="Low cover",
    blocks_los=False,
    cover=CoverLevel.HALF,
    blocks_passage_dirs=frozenset(),
    passable_cost_ft=5,
    glyph_5x3=("     ", " /-\\ ", "     "),
    glyph_1x1="=",
    color_token="object",
)
_HIGH_COVER_FEATURE = FeatureKind(
    id="high_cover_obj",
    name="High cover",
    blocks_los=False,
    cover=CoverLevel.THREE_QUARTERS,
    blocks_passage_dirs=frozenset(Direction),  # непроходимо
    passable_cost_ft=0,
    glyph_5x3=("  ▙  ", "  ▙  ", "  ▙  "),
    glyph_1x1="H",
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
