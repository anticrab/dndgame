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
