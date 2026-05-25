"""Дефолтные реестры фич и ресурсов (этап R1)."""
from __future__ import annotations

from dnd.application.engine.features.handlers import (
    ActionSurgeHandler,
    ImprovedCriticalHandler,
    SecondWindHandler,
    SneakAttackHandler,
)
from dnd.application.engine.features.registry import (
    FeatureRegistry,
    ResourceRegistry,
    ResourceSpec,
)
from dnd.domain.values.ids import FeatureId
from dnd.domain.values.rest import RechargeOn


def default_feature_registry() -> FeatureRegistry:
    reg = FeatureRegistry()
    reg.register(FeatureId("improved_critical"), ImprovedCriticalHandler())
    reg.register(FeatureId("sneak_attack"), SneakAttackHandler())
    reg.register(FeatureId("second_wind"), SecondWindHandler())
    reg.register(FeatureId("action_surge"), ActionSurgeHandler())
    return reg


def default_resource_registry() -> ResourceRegistry:
    rr = ResourceRegistry()
    rr.register("second_wind", ResourceSpec(1, RechargeOn.SHORT_REST))
    rr.register("action_surge", ResourceSpec(1, RechargeOn.SHORT_REST))
    return rr


__all__ = ["default_feature_registry", "default_resource_registry"]
