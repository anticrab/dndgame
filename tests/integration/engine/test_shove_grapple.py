"""Shove → Prone, Grapple → Grappled (V2)."""

from __future__ import annotations

from dnd.application.engine.actions.skill_actions import (
    GrappleAction,
    ShoveAction,
    SkillActionParams,
)
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import GRAPPLED, PRONE, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square


def _setup(rolls: list[int]) -> tuple[Creature, Creature, TurnContext]:
    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("hero"),
        name="hero",
        abilities=AbilityScores.of(str_=18, dex=10, con=12, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
    )
    gob = Creature.create(
        id_=CreatureId("g"),
        name="g",
        abilities=AbilityScores.of(str_=8, dex=8, con=10, int_=8, wis=8, cha=8),
        max_hp=12,
        armor_class=12,
        speed_ft=30,
    )
    bf.place_creature(hero.id, Square(1, 1))
    bf.place_creature(gob.id, Square(2, 1))
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    reg = ConditionRegistry()
    register_default_conditions(reg)
    ctx = TurnContext(
        actor_id=hero.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=ConditionService(reg),
        event_bus=bus,
        rng=deps.rng,
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        movement_remaining_ft=30,
    )
    return hero, gob, ctx


def test_shove_success_makes_prone() -> None:
    # hero Athletics 18+4 d20=18 → 22; gob кидает 2 защитных навыка (d20=3,3)
    # → лучшее ≈ 2 → hero > gob → Prone.
    hero, gob, ctx = _setup([18, 3, 3])
    out = ShoveAction().execute(hero, SkillActionParams(target_id=gob.id), ctx)
    assert out.success is True
    assert gob.has_condition(PRONE)


def test_shove_failure_no_effect() -> None:
    # hero d20=1 + 4 = 5; gob защита d20=20,20 → лучшее 19 → промах → без эффекта.
    hero, gob, ctx = _setup([1, 20, 20])
    ShoveAction().execute(hero, SkillActionParams(target_id=gob.id), ctx)
    assert not gob.has_condition(PRONE)


def test_grapple_success_grapples() -> None:
    hero, gob, ctx = _setup([18, 3, 3])
    GrappleAction().execute(hero, SkillActionParams(target_id=gob.id), ctx)
    assert gob.has_condition(GRAPPLED)


def test_shove_out_of_reach_forbidden() -> None:
    from dnd.application.dto.action import Forbidden

    hero, gob, ctx = _setup([18, 3])
    ctx.battlefield.move_creature(gob.id, Square(4, 4))  # дальше 5 фт
    avail = ShoveAction().can_perform_against(hero, SkillActionParams(target_id=gob.id), ctx)
    assert isinstance(avail, Forbidden)
