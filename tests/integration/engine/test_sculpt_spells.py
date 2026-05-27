"""Эвокатор Sculpt Spells (T4-b): союзники кастера не получают урон его AoE."""
from __future__ import annotations

from pathlib import Path

from dnd.application.dto.action import Allowed
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, FeatureId, SpellId
from dnd.domain.values.square import Square
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository


def _ctx(creatures: dict[str, Creature], factions: dict[str, Faction],
         bf: Battlefield, actor_id: str) -> TurnContext:
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[1] * 30)
    reg = ConditionRegistry()
    register_default_conditions(reg)
    return TurnContext(
        actor_id=CreatureId(actor_id), battlefield=bf,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
        condition_service=ConditionService(reg), event_bus=deps.event_bus,
        rng=deps.rng,
        participants={CreatureId(k): v for k, v in creatures.items()},
        factions={CreatureId(k): f for k, f in factions.items()},
        movement_remaining_ft=30,
    )


def test_sculpt_excludes_caster_ally() -> None:
    bf = Battlefield(8, 8)
    mage = Creature.create(
        id_=CreatureId("mage"), name="mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=14, armor_class=12, speed_ft=30,
    )
    mage.spellcasting_ability = Ability.INT
    mage.known_spells = (SpellId("fireball"),)
    mage.spell_slots = {3: 1}
    mage.subclass = FeatureId("subclass_evoker")
    mage.features = (FeatureId("subclass_evoker"),)
    ally = Creature.create(
        id_=CreatureId("ally"), name="ally",
        abilities=AbilityScores.of(str_=12, dex=10, con=12, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30,
    )
    foe = Creature.create(
        id_=CreatureId("foe"), name="foe",
        abilities=AbilityScores.of(str_=12, dex=10, con=12, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30,
    )
    bf.place_creature(mage.id, Square(0, 0))
    bf.place_creature(ally.id, Square(5, 5))
    bf.place_creature(foe.id, Square(6, 5))
    ctx = _ctx(
        {"mage": mage, "ally": ally, "foe": foe},
        {"mage": Faction.PARTY, "ally": Faction.PARTY, "foe": Faction.MONSTERS},
        bf, "mage",
    )
    spells = YamlSpellRepository(Path("data/content/spells.yaml"))
    action = CastSpellAction(spell_repository=spells)
    params = CastSpellParams(spell_id=SpellId("fireball"), target_point=Square(5, 5))
    assert isinstance(action.can_perform_against(mage, params, ctx), Allowed)
    action.execute(mage, params, ctx)
    assert ally.hit_points.current == ally.hit_points.maximum  # союзник невредим
    assert foe.hit_points.current < foe.hit_points.maximum     # враг получил урон
