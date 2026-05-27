"""Встроенные резолверы форм зоны (CIRCLE/CONE/LINE) — этап P2.

Зовут чистую геометрию (``domain/values/geometry.py``); отбрасывают клетки вне
границ поля. Новая форма — новый класс здесь + регистрация в defaults.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.geometry import (
    circle_squares,
    cone_squares,
    line_squares,
)

if TYPE_CHECKING:
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.values.direction import Direction
    from dnd.domain.values.spell import TargetingSpec
    from dnd.domain.values.square import Square


def _in_bounds(cells: frozenset[Square], bf: Battlefield) -> frozenset[Square]:
    return frozenset(c for c in cells if bf.in_bounds(c))


class CircleResolver:
    """CIRCLE: chebyshev-диск радиуса ``radius_ft//5`` вокруг origin."""

    def squares(
        self,
        origin: Square,
        direction: Direction | None,
        spec: TargetingSpec,
        battlefield: Battlefield,
    ) -> frozenset[Square]:
        return _in_bounds(circle_squares(origin, spec.radius_ft // 5), battlefield)


class ConeResolver:
    """CONE: конус от origin в направлении, длина ``length_ft//5``."""

    def squares(
        self,
        origin: Square,
        direction: Direction | None,
        spec: TargetingSpec,
        battlefield: Battlefield,
    ) -> frozenset[Square]:
        if direction is None:
            raise ValueError("CONE area requires a direction")
        return _in_bounds(cone_squares(origin, direction, spec.length_ft // 5), battlefield)


class LineResolver:
    """LINE: луч от origin в направлении, длина ``length_ft//5``."""

    def squares(
        self,
        origin: Square,
        direction: Direction | None,
        spec: TargetingSpec,
        battlefield: Battlefield,
    ) -> frozenset[Square]:
        if direction is None:
            raise ValueError("LINE area requires a direction")
        return _in_bounds(line_squares(origin, direction, spec.length_ft // 5), battlefield)


__all__ = ["CircleResolver", "ConeResolver", "LineResolver"]
