"""GameSession: общие часы поверх боя; Encounter двигает их на границе раунда (X0-6)."""

from __future__ import annotations

from dnd.application.engine.encounter import Encounter, noop_reaction_policy
from dnd.application.engine.game_session import GameSession
from dnd.composition import build_default_runtime_services
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square


def _combatant(name: str) -> Creature:
    return Creature.create(
        id_=CreatureId(name),
        name=name,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=12,
        speed_ft=30,
    )


def test_session_clock_is_shared_with_services() -> None:
    services = build_default_runtime_services()
    session = GameSession(party={}, services=services)
    assert session.clock is services.clock
    assert session.clock.now_round == 0


def test_encounter_from_session_advances_shared_clock_on_round_end() -> None:
    services = build_default_runtime_services()
    a = _combatant("a")
    b = _combatant("b")
    session = GameSession(party={a.id: a}, services=services)

    bf = Battlefield(4, 4)
    bf.place_creature(a.id, Square(0, 0))
    bf.place_creature(b.id, Square(3, 3))
    deps = services.with_battlefield(bf)
    assert deps.clock is session.clock  # общий объект часов

    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS},
        deps=deps,
        reaction_policy=noop_reaction_policy,
    )
    enc.start()
    # Прогнать полный раунд: оба ходят; на закрытии раунда часы +1.
    for _ in range(len(enc.initiative_order)):
        enc.start_turn()
        enc.end_turn()
    assert session.clock.now_round == 1
