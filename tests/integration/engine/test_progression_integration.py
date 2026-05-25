"""R1-12: интеграция — SHORT-rest на старте боя восстанавливает фичи PC."""
from __future__ import annotations

from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square


def test_short_rest_on_encounter_start_restores_resources() -> None:
    f = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30,
    )
    f.character_class = "fighter"
    f.resource_uses = {"second_wind": 0, "action_surge": 0}
    gob = Creature.create(
        id_="gob", name="Gob",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(f.id, Square(1, 1))
    bf.place_creature(gob.id, Square(6, 6))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20] * 10)
    enc = Encounter(
        participants={f.id: f, gob.id: gob},
        factions={f.id: Faction.PARTY, gob.id: Faction.MONSTERS}, deps=deps,
    )
    enc.start()
    assert f.resource_uses["second_wind"] == 1   # SHORT rest между боями
    assert f.resource_uses["action_surge"] == 1
