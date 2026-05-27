"""Compass-направления для семантики «грани клетки».

Используется в ``FeatureKind.blocks_passage_dirs``: вертикальная стена
блокирует проход {E, W}; горизонтальная — {N, S}; угловая NE — {NE}.

Конвенция Y: ось Y растёт вниз (Y=0 — север, Y=height-1 — юг). Это
согласуется с raster-render картой.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dnd.domain.values.square import Square


class Direction(StrEnum):
    N = "n"
    NE = "ne"
    E = "e"
    SE = "se"
    S = "s"
    SW = "sw"
    W = "w"
    NW = "nw"

    def opposite(self) -> Direction:
        return _OPPOSITES[self]

    @staticmethod
    def from_squares(frm: Square, to: Square) -> Direction:
        if frm == to:
            raise ValueError(f"from and to are the same square: {frm}")
        dx = to.x - frm.x
        dy = to.y - frm.y
        if abs(dx) > 1 or abs(dy) > 1:
            raise ValueError(f"squares not adjacent: {frm} -> {to}")
        key = (dx, dy)
        if key not in _BY_DELTA:
            raise ValueError(f"squares not adjacent: {frm} -> {to}")
        return _BY_DELTA[key]


_OPPOSITES: dict[Direction, Direction] = {
    Direction.N: Direction.S,
    Direction.S: Direction.N,
    Direction.E: Direction.W,
    Direction.W: Direction.E,
    Direction.NE: Direction.SW,
    Direction.SW: Direction.NE,
    Direction.NW: Direction.SE,
    Direction.SE: Direction.NW,
}

_BY_DELTA: dict[tuple[int, int], Direction] = {
    (0, -1): Direction.N,
    (1, -1): Direction.NE,
    (1, 0): Direction.E,
    (1, 1): Direction.SE,
    (0, 1): Direction.S,
    (-1, 1): Direction.SW,
    (-1, 0): Direction.W,
    (-1, -1): Direction.NW,
}

__all__ = ["Direction"]
