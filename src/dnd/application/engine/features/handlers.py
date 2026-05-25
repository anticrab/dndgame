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


class SneakAttackHandler:
    """Плут L1: Sneak Attack. Поведение — в AttackAction по наличию фичи в
    creature.features; on_gain — пасс (фича уже добавлена LevelUpService'ом)."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        return


def _grant_ability(creature: Creature, ability_id: str) -> None:
    """Выдать существу активную способность (добавить id в ability_ids)."""
    from dnd.domain.values.ability_id import AbilityId
    aid = AbilityId(ability_id)
    if aid not in creature.ability_ids:
        creature.ability_ids = (*creature.ability_ids, aid)


class SecondWindHandler:
    """Воин L1: Second Wind. on_gain — инициализирует ресурс и выдаёт ability."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.resource_uses.setdefault("second_wind", 1)
        _grant_ability(creature, "second_wind")


class ActionSurgeHandler:
    """Воин L2: Action Surge. on_gain — инициализирует ресурс и выдаёт ability."""

    def on_gain(self, creature: Creature, ctx: TurnContext | None) -> None:
        creature.resource_uses.setdefault("action_surge", 1)
        _grant_ability(creature, "action_surge")


__all__ = [
    "ActionSurgeHandler",
    "ImprovedCriticalHandler",
    "SecondWindHandler",
    "SneakAttackHandler",
]
