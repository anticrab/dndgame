"""Инкапаситированный актёр (Paralyzed/Unconscious) не действует (T2)."""

from __future__ import annotations

from dnd.application.engine.ai.simple_monster import (
    is_hostile_from_factions,
    take_monster_turn,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import SCIMITAR


def test_paralyzed_monster_does_nothing() -> None:
    bf = Battlefield(5, 5)
    hero = Creature.create(
        id_=CreatureId("hero"),
        name="hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=15,
        speed_ft=30,
    )
    gob = Creature.create(
        id_=CreatureId("g"),
        name="g",
        abilities=AbilityScores.of(str_=10, dex=12, con=10, int_=8, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=SCIMITAR,
    )
    gob.apply_condition(PARALYZED)
    bf.place_creature(hero.id, Square(1, 2))
    bf.place_creature(gob.id, Square(2, 2))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 1])
    enc = Encounter(
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    hp_before = hero.hit_points.current
    if enc.factions[actor.id] is Faction.MONSTERS:
        take_monster_turn(actor, ctx, is_hostile=is_hostile_from_factions(actor.id, enc.factions))
    # Парализованный гоблин не атакует — герой целым.
    assert hero.hit_points.current == hp_before
