"""Хендлеры классовых фич (этап R1). Регистрируются в default_feature_registry.

Каждая фича — отдельный класс. Пассивные правят деривации/вешают модификаторы;
активные инициализируют ресурс и выдают способность (Ability), исполняемую
своим Action (см. second_wind.py / action_surge.py).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


class ImprovedCriticalHandler:
    """Чемпион L3: крит на 19–20. Пассив — ставит crit_range_min=19."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.crit_range_min = 19


__all__ = ["ImprovedCriticalHandler"]
