"""E2E T3: парализованная цель — атака союзника с преимуществом и авто-критом."""

from __future__ import annotations

import pytest

from dnd.application.dto.engine_event import AttackRolled, EngineEvent
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


@pytest.mark.e2e
def test_paralyzed_target_attacked_with_advantage_and_autocrit() -> None:
    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("hero"),
        name="hero",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    foe = Creature.create(
        id_=CreatureId("foe"),
        name="foe",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=40,
        armor_class=14,
        speed_ft=30,
    )
    foe.apply_condition(PARALYZED)
    bf.place_creature(hero.id, Square(1, 2))
    bf.place_creature(foe.id, Square(2, 2))
    # init hero=18, foe=1; атака advantage → 2 d20 (10,10), авто-крит → 2 d8.
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[18, 1, 10, 10, 5, 5])
    enc = Encounter(
        participants={hero.id: hero, foe.id: foe},
        factions={hero.id: Faction.PARTY, foe.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.start()
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    assert actor.id == hero.id
    AttackAction().execute(actor, weapon_attack_params(actor, foe.id), ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.advantage is True
    assert ar.is_critical_hit is True
