"""RestService — восстановление ресурсов и HP по типу отдыха (этап R1).

Архитектура полная: знает только про ``recharge_on`` ресурсов (из
ResourceRegistry), не про конкретные фичи. В R1 единственный триггер —
«отдых между боями» (SHORT на старте encounter), но short/long rest как
внебоевые действия позже зовут ту же ``apply``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.rest import RestKind, recharge_covers

if TYPE_CHECKING:
    from dnd.application.engine.features.registry import ResourceRegistry
    from dnd.domain.entities.creature import Creature


class RestService:
    def __init__(self, resources: ResourceRegistry) -> None:
        self._resources = resources

    def apply(self, creature: Creature, kind: RestKind) -> None:
        # Восстановить ресурсы, чья политика покрыта этим отдыхом.
        for key, spec in self._resources.all_specs().items():
            if key in creature.resource_uses and recharge_covers(kind, spec.recharge_on):
                creature.resource_uses[key] = spec.max_uses
        # Долгий отдых: полный HP (PHB-2024 стр. 39). heal клампится к maximum.
        if kind is RestKind.LONG:
            creature.hit_points = creature.hit_points.heal(creature.hit_points.maximum)


__all__ = ["RestService"]
