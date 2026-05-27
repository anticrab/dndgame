"""Hide → Hidden → атака с преимуществом, Hidden снят после атаки (V2)."""

from __future__ import annotations

from dnd.application.dto.engine_event import AttackRolled, EngineEvent
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.skill_actions import HideAction, SkillActionParams
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import HIDDEN, register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.skill import Skill
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import SCIMITAR


def test_hide_then_attack_has_advantage_and_clears_hidden() -> None:
    bf = Battlefield(5, 5)
    rogue = Creature.create(
        id_=CreatureId("rogue"),
        name="rogue",
        abilities=AbilityScores.of(str_=10, dex=18, con=12, int_=12, wis=10, cha=10),
        max_hp=16,
        armor_class=14,
        speed_ft=30,
        equipped_weapon=SCIMITAR,
    )
    rogue.skill_proficiencies = frozenset({Skill.STEALTH})
    gob = Creature.create(
        id_=CreatureId("g"),
        name="g",
        abilities=AbilityScores.of(str_=10, dex=10, con=10, int_=10, wis=10, cha=8),
        max_hp=12,
        armor_class=10,
        speed_ft=30,
    )
    bf.place_creature(rogue.id, Square(1, 1))
    bf.place_creature(gob.id, Square(2, 1))
    # Stealth d20=18 vs пассивная Внимательность гоблина (10) → спрятался;
    # атака с преимуществом → 2 d20 (5, 19) → 19; затем кость урона.
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[18, 5, 19, 4])
    reg = ConditionRegistry()
    register_default_conditions(reg)
    ctx = TurnContext(
        actor_id=rogue.id,
        battlefield=bf,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=ConditionService(reg),
        event_bus=bus,
        rng=deps.rng,
        participants={rogue.id: rogue, gob.id: gob},
        factions={rogue.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        movement_remaining_ft=30,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    HideAction().execute(rogue, SkillActionParams(), ctx)
    assert rogue.has_condition(HIDDEN)

    # Hide и атака — два разных действия (в реальной игре: следующий ход).
    # Сбрасываем бюджет действия, чтобы проверить связку Hidden → атака.
    ctx.action_used = False
    AttackAction().execute(rogue, weapon_attack_params(rogue, gob.id), ctx)
    rolled = next(e for e in captured if isinstance(e, AttackRolled))
    assert rolled.advantage is True
    assert not rogue.has_condition(HIDDEN)  # снят после удара
