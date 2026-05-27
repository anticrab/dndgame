"""AreaShapeResolver + AreaShapeRegistry — клетки зоны по форме (этап P2).

Резолвер возвращает множество клеток зоны от origin (центр для AT_POINT-круга
или клетка кастера для FROM_CASTER) в направлении (для конуса/линии). Реестр —
open/closed, как :class:`SpellEffectRegistry`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.values.direction import Direction
    from dnd.domain.values.spell import AreaShape, TargetingSpec
    from dnd.domain.values.square import Square


@runtime_checkable
class AreaShapeResolver(Protocol):
    """Считает клетки зоны заданной формы."""

    def squares(
        self,
        origin: Square,
        direction: Direction | None,
        spec: TargetingSpec,
        battlefield: Battlefield,
    ) -> frozenset[Square]:
        """Клетки зоны (только в границах поля). ``direction`` нужен конусу/линии."""
        ...


class AreaShapeRegistry:
    """Реестр {AreaShape → AreaShapeResolver}."""

    def __init__(self) -> None:
        self._resolvers: dict[AreaShape, AreaShapeResolver] = {}

    def register(self, shape: AreaShape, resolver: AreaShapeResolver) -> None:
        if shape in self._resolvers:
            raise ValueError(f"area shape resolver already registered: {shape}")
        self._resolvers[shape] = resolver

    def get(self, shape: AreaShape) -> AreaShapeResolver:
        if shape not in self._resolvers:
            raise KeyError(f"no resolver registered for area shape: {shape}")
        return self._resolvers[shape]

    def __contains__(self, shape: AreaShape) -> bool:
        return shape in self._resolvers


__all__ = ["AreaShapeRegistry", "AreaShapeResolver"]
