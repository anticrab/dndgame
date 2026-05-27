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
    id="floor",
    name="F",
    passable=True,
    difficult=False,
    glyph_5x3=("     ", "     ", "     "),
    glyph_1x1=".",
    color_token="floor",
)
WALL_V = FeatureKind(
    id="wall_v",
    name="V",
    blocks_los=True,
    cover=CoverLevel.TOTAL,
    blocks_passage_dirs=frozenset({Direction.E, Direction.W}),
    passable_cost_ft=0,
    glyph_5x3=("  │  ", "  │  ", "  │  "),
    glyph_1x1="│",
    color_token="wall",
)
COLUMN = FeatureKind(
    id="col",
    name="C",
    blocks_los=False,
    cover=CoverLevel.THREE_QUARTERS,
    blocks_passage_dirs=frozenset(),
    passable_cost_ft=5,
    glyph_5x3=("     ", "  ▙  ", "     "),
    glyph_1x1="▙",
    color_token="wall",
)


def test_floor_only_returns_base_glyph() -> None:
    tile = Tile(base=FLOOR, features=())
    out = render_tile_5x3(tile)
    assert out == ("     ", "     ", "     ")


def test_feature_overrides_non_space_base() -> None:
    tile = Tile(base=FLOOR, features=(WALL_V,))
    out = render_tile_5x3(tile)
    assert out == ("  │  ", "  │  ", "  │  ")


def test_multi_feature_last_wins_per_cell() -> None:
    """Если 2 features накладываются — побеждает последний non-space."""
    tile = Tile(base=FLOOR, features=(WALL_V, COLUMN))
    out = render_tile_5x3(tile)
    # column overrides только средний ряд (где у него ▙); WALL_V — три ряда │
    assert out[0] == "  │  "  # только wall_v
    assert out[1] == "  ▙  "  # column перекрыл │
    assert out[2] == "  │  "  # только wall_v


def test_returns_3_rows_of_5_chars() -> None:
    tile = Tile(base=FLOOR, features=())
    out = render_tile_5x3(tile)
    assert len(out) == 3
    for row in out:
        assert len(row) == 5
