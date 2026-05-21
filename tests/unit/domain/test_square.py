"""Тесты Square — координаты клеток боевой карты."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dnd.domain.values.square import Square

_coords = st.integers(min_value=-1000, max_value=1000)
_squares = st.builds(Square, x=_coords, y=_coords)


def test_distance_to_self_is_zero() -> None:
    s = Square(5, 5)
    assert s.distance_to(s) == 0


@pytest.mark.rules
@pytest.mark.parametrize(
    "a,b,expected",
    [
        # 1 клетка по диагонали = 1 клетка (Chebyshev — правило книги)
        ((0, 0), (1, 1), 1),
        # 2 по горизонтали
        ((3, 7), (5, 7), 2),
        # 3 по диагонали
        ((0, 0), (3, 3), 3),
        # «1 + 2» = max(1, 2) = 2
        ((0, 0), (1, 2), 2),
        # большое расстояние
        ((0, 0), (10, 6), 10),
    ],
)
def test_distance_chebyshev(a: tuple[int, int], b: tuple[int, int], expected: int) -> None:
    assert Square(*a).distance_to(Square(*b)) == expected


def test_distance_to_feet_is_5x_squares() -> None:
    assert Square(0, 0).distance_to_feet(Square(3, 3)) == 15


def test_is_adjacent_8_directions() -> None:
    centre = Square(0, 0)
    for n in centre.neighbors():
        assert centre.is_adjacent(n) is True
    # сама клетка — не adjacent
    assert centre.is_adjacent(centre) is False
    # клетка дальше 1 — не adjacent
    assert centre.is_adjacent(Square(2, 0)) is False


def test_neighbors_count_is_8() -> None:
    assert len(Square(0, 0).neighbors()) == 8


def test_step() -> None:
    s = Square(3, 5).step(2, -1)
    assert s == Square(5, 4)


def test_chebyshev_ring_radius_0_is_self() -> None:
    assert Square(0, 0).chebyshev_ring(0) == (Square(0, 0),)


def test_chebyshev_ring_radius_1_is_neighbors() -> None:
    centre = Square(0, 0)
    ring = set(centre.chebyshev_ring(1))
    assert ring == set(centre.neighbors())
    assert len(ring) == 8


def test_chebyshev_ring_radius_2() -> None:
    """Кольцо радиуса 2: квадрат 5×5 минус квадрат 3×3 = 16 клеток."""
    ring = Square(0, 0).chebyshev_ring(2)
    assert len(ring) == 16
    # все элементы на ровно Chebyshev-расстоянии 2
    assert all(max(abs(p.x), abs(p.y)) == 2 for p in ring)


def test_chebyshev_ring_rejects_negative() -> None:
    with pytest.raises(ValueError):
        Square(0, 0).chebyshev_ring(-1)


def test_chebyshev_disk_radius_0_is_self() -> None:
    assert Square(0, 0).chebyshev_disk(0) == (Square(0, 0),)


def test_chebyshev_disk_radius_1_is_3x3() -> None:
    disk = Square(0, 0).chebyshev_disk(1)
    assert len(disk) == 9


def test_chebyshev_disk_radius_2_is_5x5() -> None:
    disk = Square(0, 0).chebyshev_disk(2)
    assert len(disk) == 25


def test_chebyshev_disk_rejects_negative() -> None:
    with pytest.raises(ValueError):
        Square(0, 0).chebyshev_disk(-1)


def test_square_is_orderable() -> None:
    """`order=True` даёт нам сортировку по (x, y) — нужно для детерминизма тестов."""
    squares = [Square(2, 1), Square(0, 0), Square(1, 1)]
    assert sorted(squares) == [Square(0, 0), Square(1, 1), Square(2, 1)]


# ---------- Property-based --------------------------------------------------


@pytest.mark.property
@given(a=_squares, b=_squares)
def test_property_distance_symmetric(a: Square, b: Square) -> None:
    """Дистанция симметрична: d(a, b) == d(b, a)."""
    assert a.distance_to(b) == b.distance_to(a)


@pytest.mark.property
@given(a=_squares, b=_squares)
def test_property_distance_non_negative(a: Square, b: Square) -> None:
    assert a.distance_to(b) >= 0


@pytest.mark.property
@given(a=_squares, b=_squares, c=_squares)
def test_property_triangle_inequality(a: Square, b: Square, c: Square) -> None:
    """Неравенство треугольника: d(a, c) <= d(a, b) + d(b, c).

    Это база любой метрики; на Chebyshev — выполняется.
    """
    assert a.distance_to(c) <= a.distance_to(b) + b.distance_to(c)


@pytest.mark.property
@given(a=_squares, b=_squares)
def test_property_distance_zero_iff_equal(a: Square, b: Square) -> None:
    assert (a.distance_to(b) == 0) == (a == b)


@pytest.mark.property
@given(centre=_squares, radius=st.integers(min_value=0, max_value=10))
def test_property_disk_contains_ring(centre: Square, radius: int) -> None:
    disk = set(centre.chebyshev_disk(radius))
    ring = set(centre.chebyshev_ring(radius))
    assert ring <= disk


@pytest.mark.property
@given(centre=_squares, radius=st.integers(min_value=0, max_value=10))
def test_property_disk_size_is_square(centre: Square, radius: int) -> None:
    """Размер диска радиуса r — это (2r+1)²."""
    expected = (2 * radius + 1) ** 2
    assert len(centre.chebyshev_disk(radius)) == expected


@pytest.mark.property
@given(centre=_squares, radius=st.integers(min_value=1, max_value=10))
def test_property_ring_size_for_radius_n(centre: Square, radius: int) -> None:
    """Размер кольца радиуса r: (2r+1)² − (2r−1)² = 8r."""
    assert len(centre.chebyshev_ring(radius)) == 8 * radius
