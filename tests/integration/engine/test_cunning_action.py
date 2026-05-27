"""Cunning Action (T4-c): Плут L2 — Dash/Disengage бонусным действием."""

from __future__ import annotations

from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import DashIntent
from dnd.application.engine.actions.stances import DashAction
from dnd.application.engine.features.defaults import default_feature_registry
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.ability_id import AbilityId
from dnd.domain.values.ids import CreatureId, FeatureId


def test_cunning_action_grants_bonus_abilities() -> None:
    reg = default_feature_registry()
    c = Creature.create(
        id_=CreatureId("r"),
        name="r",
        abilities=AbilityScores.of(str_=10, dex=16, con=12, int_=12, wis=10, cha=10),
        max_hp=16,
        armor_class=14,
        speed_ft=30,
    )
    reg.get(FeatureId("cunning_action")).on_gain(c, None)
    assert AbilityId("cunning_dash") in c.ability_ids
    assert AbilityId("cunning_disengage") in c.ability_ids


def test_dash_action_bonus_economy() -> None:
    action = DashAction(economy=ActionEconomyCost.BONUS_ACTION)
    assert action.economy_cost is ActionEconomyCost.BONUS_ACTION
    assert DashAction().economy_cost is ActionEconomyCost.ACTION


def test_dash_intent_carries_bonus_flag() -> None:
    assert DashIntent(bonus_action=True).bonus_action is True
    assert DashIntent().bonus_action is False
