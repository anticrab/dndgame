"""E2E T2: маг усыпляет гоблина (Sleep) через CastSpellAction."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.action import Allowed
from dnd.application.dto.engine_event import ConditionApplied
from dnd.application.engine.actions.cast_spell import CastSpellAction, CastSpellParams
from dnd.application.engine.effects.ongoing_effect_tracker import OngoingEffectTracker
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability, AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, SpellId
from dnd.domain.values.square import Square
from dnd.infrastructure.content.yaml_spell_repository import YamlSpellRepository


@pytest.mark.e2e
def test_mage_sleeps_goblin() -> None:
    bf = Battlefield(8, 8)
    mage = Creature.create(
        id_=CreatureId("mage"), name="mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=12, int_=16, wis=10, cha=10),
        max_hp=14, armor_class=12, speed_ft=30,
    )
    mage.spellcasting_ability = Ability.INT
    mage.known_spells = (SpellId("sleep"),)
    mage.spell_slots = {1: 2}
    gob = Creature.create(
        id_=CreatureId("g"), name="g",
        abilities=AbilityScores.of(str_=8, dex=12, con=10, int_=8, wis=8, cha=8),
        max_hp=6, armor_class=12, speed_ft=30,
    )
    bf.place_creature(mage.id, Square(1, 1))
    bf.place_creature(gob.id, Square(2, 2))
    # init: mage=20, gob=1; затем пул 5d8 = 5×2 = 10 (хватает на гоблина 6 HP).
    deps, bus, _ = build_scripted_dependencies(
        battlefield=bf, rolls=[20, 1, 2, 2, 2, 2, 2]
    )
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    OngoingEffectTracker(
        participants=enc.participants, event_bus=enc.event_bus,
        dice_roller=deps.dice_roller, modifier_applier=deps.modifier_applier,
    ).subscribe()
    applied: list[ConditionApplied] = []
    bus.subscribe(ConditionApplied, applied.append)
    enc.start()
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    assert enc.factions[actor.id] is Faction.PARTY  # маг ходит первым

    spell_repo = YamlSpellRepository(Path("data/content/spells.yaml"))
    action = CastSpellAction(spell_repository=spell_repo)
    params = CastSpellParams(spell_id=SpellId("sleep"), target_point=Square(2, 2))
    assert isinstance(action.can_perform_against(actor, params, ctx), Allowed)
    action.execute(actor, params, ctx)

    assert gob.has_condition(UNCONSCIOUS)
    assert applied and applied[-1].target_id == gob.id
