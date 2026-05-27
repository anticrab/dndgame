"""Дефолтные реестры фич и ресурсов (этап R1)."""

from __future__ import annotations

from dnd.application.engine.features.handlers import (
    ActionSurgeHandler,
    CunningActionHandler,
    FightingStyleHandler,
    ImprovedCriticalHandler,
    NoEffectFeatureHandler,
    SecondWindHandler,
    SneakAttackHandler,
    StyleDefenseHandler,
    SubclassHandler,
    ThiefHandler,
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
    # Improved Critical: один экземпляр на оба id — фича Чемпиона (T4
    # subclass_champion) и legacy-id improved_critical (backward-compat
    # старых шаблонов). Один объект → логика крита правится в одном месте.
    improved_critical = ImprovedCriticalHandler()
    reg.register(FeatureId("improved_critical"), improved_critical)
    reg.register(FeatureId("sneak_attack"), SneakAttackHandler())
    reg.register(FeatureId("second_wind"), SecondWindHandler())
    reg.register(FeatureId("action_surge"), ActionSurgeHandler())
    # T4: боевые стили (Воин L1). Конкретные стили — до мета-фичи.
    reg.register(FeatureId("style_defense"), StyleDefenseHandler())
    reg.register(FeatureId("style_dueling"), NoEffectFeatureHandler())
    reg.register(FeatureId("style_archery"), NoEffectFeatureHandler())
    reg.register(FeatureId("style_gwf"), NoEffectFeatureHandler())
    reg.register(FeatureId("fighting_style"), FightingStyleHandler(reg))
    # T4: подклассы L3. Конкретные подклассы — до мета-фичи.
    reg.register(FeatureId("subclass_champion"), improved_critical)
    reg.register(FeatureId("subclass_thief"), ThiefHandler())
    reg.register(FeatureId("subclass_evoker"), NoEffectFeatureHandler())
    reg.register(FeatureId("subclass"), SubclassHandler(reg))
    # T4: Cunning Action (Плут L2).
    reg.register(FeatureId("cunning_action"), CunningActionHandler())
    return reg


def default_resource_registry() -> ResourceRegistry:
    rr = ResourceRegistry()
    rr.register("second_wind", ResourceSpec(1, RechargeOn.SHORT_REST))
    rr.register("action_surge", ResourceSpec(1, RechargeOn.SHORT_REST))
    return rr


__all__ = ["default_feature_registry", "default_resource_registry"]
