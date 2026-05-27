"""P2-2: геометрия зон (круг/линия/конус) по клеткам."""

from __future__ import annotations

from dnd.domain.values.direction import Direction
from dnd.domain.values.geometry import (
    circle_squares,
    cone_squares,
    direction_delta,
    line_squares,
)
from dnd.domain.values.square import Square


def test_circle_radius0_is_center() -> None:
    assert circle_squares(Square(3, 3), 0) == frozenset({Square(3, 3)})


def test_circle_radius1_is_9_cells() -> None:
    cells = circle_squares(Square(5, 5), 1)
    assert len(cells) == 9
    assert Square(5, 5) in cells
    assert Square(4, 4) in cells and Square(6, 6) in cells


def test_line_east() -> None:
    cells = line_squares(Square(2, 2), Direction.E, 3)
    assert cells == frozenset({Square(3, 2), Square(4, 2), Square(5, 2)})
    assert Square(2, 2) not in cells  # origin не входит


def test_line_diagonal_ne() -> None:
    cells = line_squares(Square(2, 5), Direction.NE, 2)
    # NE = (1,-1)
    assert cells == frozenset({Square(3, 4), Square(4, 3)})


def test_direction_delta_all_eight() -> None:
    assert direction_delta(Direction.N) == (0, -1)
    assert direction_delta(Direction.S) == (0, 1)
    assert direction_delta(Direction.SW) == (-1, 1)


def test_cone_east_length2() -> None:
    # k=1: (1,0); k=2: ось (2,0) ± перп (0,1) → (2,-1),(2,0),(2,1)
    cells = cone_squares(Square(0, 0), Direction.E, 2)
    assert cells == frozenset(
        {
            Square(1, 0),
            Square(2, -1),
            Square(2, 0),
            Square(2, 1),
        }
    )
    assert Square(0, 0) not in cells


def test_cone_north_widens() -> None:
    # N=(0,-1), перп=(1,0). k=1:(0,-1); k=2:(−1,−2),(0,−2),(1,−2)
    cells = cone_squares(Square(0, 0), Direction.N, 2)
    assert Square(0, -1) in cells
    assert {Square(-1, -2), Square(0, -2), Square(1, -2)} <= cells
    # ширина растёт: на k=1 одна клетка, на k=2 — три
    assert len(cells) == 4
