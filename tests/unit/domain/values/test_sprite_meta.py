"""SpriteMeta/TerrainBase/FeatureKind — value-объекты для тайлов.

Эти типы — чистые pydantic-модели; они НЕ содержат render-логики.
Только данные + минимальные методы валидации.
"""

from __future__ import annotations

import pytest

from dnd.domain.values.direction import Direction
from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase
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
        id="x",
        name="x",
        blocks_los=False,
        cover=CoverLevel.NONE,
        blocks_passage_dirs=frozenset(),
        passable_cost_ft=5,
        glyph_5x3=("     ", "     ", "     "),
        glyph_1x1=" ",
        color_token="x",
    )
    with pytest.raises(Exception):  # pydantic frozen  # noqa: B017
        f.id = "y"  # type: ignore[misc]
