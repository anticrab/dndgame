"""GrappledCondition / HiddenCondition (V2)."""

from __future__ import annotations

from dnd.domain.conditions.builtin import (
    GRAPPLED,
    HIDDEN,
    GrappledCondition,
    HiddenCondition,
)
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.modifiers import AdvantageEffect, ModifierTargetKind


def test_grappled_has_no_combat_flags() -> None:
    g = GrappledCondition()
    assert g.id == GRAPPLED
    assert g.grants_advantage_to_attackers is False
    assert g.melee_advantage_ranged_disadvantage is False
    assert g.provides_modifiers(CreatureId("c")) == ()


def test_hidden_grants_self_attack_advantage() -> None:
    assert HiddenCondition().id == HIDDEN
    mods = HiddenCondition().provides_modifiers(CreatureId("c"))
    assert len(mods) == 1
    assert isinstance(mods[0].effect, AdvantageEffect)
    assert mods[0].target_kind is ModifierTargetKind.ATTACK_ROLL


def test_grappled_blocks_movement() -> None:
    from dnd.application.dto.action import Forbidden
    from dnd.application.engine.actions.move import MoveAction
    from dnd.application.engine.condition_service import ConditionService
    from dnd.application.engine.turn_context import TurnContext
    from dnd.composition import build_scripted_dependencies
    from dnd.domain.conditions.builtin import register_default_conditions
    from dnd.domain.conditions.registry import ConditionRegistry
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.entities.creature import Creature
    from dnd.domain.values.ability import AbilityScores
    from dnd.domain.values.faction import Faction
    from dnd.domain.values.square import Square

    reg = ConditionRegistry()
    register_default_conditions(reg)

    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("h"),
        name="h",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=12,
        speed_ft=30,
    )
    bf.place_creature(hero.id, Square(1, 1))
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[])
    ctx = TurnContext(
        actor_id=hero.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=ConditionService(reg),
        event_bus=bus,
        rng=deps.rng,
        participants={hero.id: hero},
        factions={hero.id: Faction.PARTY},
        movement_remaining_ft=30,
    )
    hero.apply_condition(GRAPPLED)
    assert isinstance(MoveAction().can_perform(hero, ctx), Forbidden)
