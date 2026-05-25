"""Регистрация встроенных резолверов форм зоны (этап P2)."""
from __future__ import annotations

from dnd.application.engine.spells.area.resolver import AreaShapeRegistry
from dnd.application.engine.spells.area.resolvers import (
    CircleResolver,
    ConeResolver,
    LineResolver,
)
from dnd.domain.values.spell import AreaShape


def default_area_shape_registry() -> AreaShapeRegistry:
    registry = AreaShapeRegistry()
    registry.register(AreaShape.CIRCLE, CircleResolver())
    registry.register(AreaShape.CONE, ConeResolver())
    registry.register(AreaShape.LINE, LineResolver())
    return registry


__all__ = ["default_area_shape_registry"]
