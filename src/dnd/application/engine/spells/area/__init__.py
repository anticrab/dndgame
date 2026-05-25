"""Резолверы форм зоны (AoE, этап P2) — open/closed реестр.

Новая форма зоны = новый :class:`AreaShapeResolver` + регистрация в
:func:`default_area_shape_registry`, без правки ``CastSpellAction``.
"""
from __future__ import annotations

from dnd.application.engine.spells.area.defaults import default_area_shape_registry
from dnd.application.engine.spells.area.resolver import (
    AreaShapeRegistry,
    AreaShapeResolver,
)

__all__ = [
    "AreaShapeRegistry",
    "AreaShapeResolver",
    "default_area_shape_registry",
]
