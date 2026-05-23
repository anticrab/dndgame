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
    glyph_5x3=(",.,.,", ".,.,.", ",.,.,"),
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
    assert t.blocks_los is False
    assert t.aggregate_cover() is CoverLevel.THREE_QUARTERS


def test_tile_grass_base_difficult_terrain_cost_doubled() -> None:
    t = Tile(base=GRASS, features=())
    assert t.movement_cost_ft() == 10  # 5 base * 2 = 10


def test_tile_floor_no_features_cost_5() -> None:
    t = Tile(base=FLOOR, features=())
    assert t.movement_cost_ft() == 5
