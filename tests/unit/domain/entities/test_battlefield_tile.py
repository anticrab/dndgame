"""Battlefield — новый Tile-aware API.

Не дублирует существующий test_battlefield.py (там сохранён старый
Terrain-API, который тоже должен работать через alias).
"""

from __future__ import annotations

import pytest

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.ids import ObjectId
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


def test_passable_between_same_square_is_true() -> None:
    bf = Battlefield(5, 5)
    assert bf.passable_between(Square(2, 2), Square(2, 2)) is True


def test_passable_between_out_of_bounds_is_false() -> None:
    bf = Battlefield(5, 5)
    assert bf.passable_between(Square(0, 0), Square(-1, 0)) is False


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


def test_object_at_missing_raises_keyerror() -> None:
    bf = Battlefield(5, 5)
    with pytest.raises(KeyError, match="nope"):
        bf.object_at(ObjectId("nope"))


def test_objects_at_empty_returns_empty_tuple() -> None:
    bf = Battlefield(5, 5)
    assert bf.objects_at(Square(0, 0)) == ()


def test_place_object_out_of_bounds_raises() -> None:
    bf = Battlefield(5, 5)
    door = InteractableObject(
        id=ObjectId("d"),
        kind=ObjectKind.DOOR,
        pos=Square(10, 10),  # out of bounds
        state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    with pytest.raises(ValueError, match="out of bounds"):
        bf.place_object(door)


def test_set_tile_out_of_bounds_raises() -> None:
    bf = Battlefield(3, 3)
    with pytest.raises(ValueError, match="out of bounds"):
        bf.set_tile(Square(5, 5), WALL_TILE)
