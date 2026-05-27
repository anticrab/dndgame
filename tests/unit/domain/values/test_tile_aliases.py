"""Aliases: старые Terrain-константы (FLOOR/WALL/...) воспроизводятся
как готовые Tile. Это нужно для backwards compat до миграции тестов."""

from __future__ import annotations

from dnd.domain.values.direction import Direction
from dnd.domain.values.terrain import CoverLevel
from dnd.domain.values.tile_aliases import (
    DIFFICULT_TILE,
    FLOOR_TILE,
    HIGH_COVER_TILE,
    LOW_COVER_TILE,
    WALL_TILE,
)


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
    assert any(LOW_COVER_TILE.allows_entry_from(d) for d in Direction)
    assert LOW_COVER_TILE.aggregate_cover() is CoverLevel.HALF


def test_high_cover_tile_impassable_three_quarters() -> None:
    for d in Direction:
        assert HIGH_COVER_TILE.allows_entry_from(d) is False
    assert HIGH_COVER_TILE.aggregate_cover() is CoverLevel.THREE_QUARTERS
