"""Геометрия зон поражения на квадратной сетке (этап P2).

Чистые функции: по центру/origin и направлению возвращают множество клеток
зоны. Без зависимостей от движка/боя — легко тестируются по клеткам. Дистанции
заданы в клетках (футы конвертирует вызывающий слой: ``ft // 5``).

Формы:
* **круг** — chebyshev-диск (квадрат ``(2r+1)×(2r+1)``), см. книжный «cube/sphere»
  на сетке;
* **линия** — луч от origin в направлении, длина N клеток, ширина 1
  (origin НЕ включается);
* **конус** — аппроксимация «расширяющегося перпендикуляра»: на шаге k (1..N)
  по оси направления берётся клетка ± (k-1) по перпендикуляру (ширина 2k-1).
  Детерминирован для всех 8 направлений (вкл. диагонали); origin не включается.
"""
from __future__ import annotations

from dnd.domain.values.direction import Direction
from dnd.domain.values.square import Square

# Единичный вектор направления (dx, dy). y растёт вниз (как на экране):
# N = вверх (0,-1), S = вниз (0,1).
_DELTA: dict[Direction, tuple[int, int]] = {
    Direction.N: (0, -1),
    Direction.NE: (1, -1),
    Direction.E: (1, 0),
    Direction.SE: (1, 1),
    Direction.S: (0, 1),
    Direction.SW: (-1, 1),
    Direction.W: (-1, 0),
    Direction.NW: (-1, -1),
}


def direction_delta(direction: Direction) -> tuple[int, int]:
    """Единичный вектор (dx, dy) направления."""
    return _DELTA[direction]


def circle_squares(center: Square, radius_sq: int) -> frozenset[Square]:
    """Круг (chebyshev-диск) радиуса ``radius_sq`` клеток, включая центр."""
    return frozenset(center.chebyshev_disk(radius_sq))


def line_squares(
    origin: Square, direction: Direction, length_sq: int
) -> frozenset[Square]:
    """Луч от ``origin`` в ``direction`` на ``length_sq`` клеток (origin не входит)."""
    dx, dy = direction_delta(direction)
    return frozenset(
        Square(origin.x + dx * k, origin.y + dy * k)
        for k in range(1, length_sq + 1)
    )


def cone_squares(
    origin: Square, direction: Direction, length_sq: int
) -> frozenset[Square]:
    """Конус от ``origin`` в ``direction``, длина ``length_sq`` (origin не входит).

    На шаге k вдоль оси берётся клетка и ±(k-1) по перпендикуляру → ширина 2k-1.
    """
    dx, dy = direction_delta(direction)
    px, py = -dy, dx  # перпендикуляр (поворот на 90°)
    cells: set[Square] = set()
    for k in range(1, length_sq + 1):
        axis = Square(origin.x + dx * k, origin.y + dy * k)
        for w in range(-(k - 1), k):
            cells.add(Square(axis.x + px * w, axis.y + py * w))
    return frozenset(cells)


__all__ = ["circle_squares", "cone_squares", "direction_delta", "line_squares"]
