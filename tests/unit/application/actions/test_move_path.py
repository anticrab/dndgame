"""Path helper для inline MOVE mode: chebyshev path + стоимость в футах."""

from dnd.application.engine.actions.move_path import (
    find_chebyshev_path,
    path_cost_ft,
)
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import DIFFICULT


def test_chebyshev_straight_horizontal() -> None:
    path = find_chebyshev_path(Square(1, 1), Square(4, 1))
    assert path == (Square(2, 1), Square(3, 1), Square(4, 1))


def test_chebyshev_diagonal() -> None:
    path = find_chebyshev_path(Square(0, 0), Square(2, 2))
    assert path == (Square(1, 1), Square(2, 2))


def test_chebyshev_empty_when_same() -> None:
    assert find_chebyshev_path(Square(3, 3), Square(3, 3)) == ()


def test_cost_floor_5ft_per_step() -> None:
    bf = Battlefield(10, 10)
    path = (Square(1, 0), Square(2, 0))
    assert path_cost_ft(bf, path) == 10


def test_cost_difficult_terrain_doubles() -> None:
    bf = Battlefield(10, 10)
    bf.set_terrain(Square(1, 0), DIFFICULT)
    path = (Square(1, 0), Square(2, 0))
    assert path_cost_ft(bf, path) == 15  # 10 (difficult) + 5 (floor)
