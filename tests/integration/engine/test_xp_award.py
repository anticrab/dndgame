"""R1-4: XpAwardService — XP за убийство монстра → LevelUpReady при пороге."""
from __future__ import annotations

from dnd.application.dto.engine_event import CreatureDied, LevelUpReady
from dnd.application.engine.progression.xp_award import XpAwardService
from dnd.application.engine.progression.xp_curve import FastXpCurve
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus


def _pc() -> Creature:
    c = Creature.create(
        id_="hero", name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=12, armor_class=14, speed_ft=30,
    )
    c.character_class = "fighter"
    return c


def _gob(cr: float) -> Creature:
    g = Creature.create(
        id_="gob", name="Gob",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30,
    )
    g.challenge_rating = cr
    return g


def _setup() -> tuple[InMemoryEventBus, Creature, Creature, list[LevelUpReady]]:
    bus = InMemoryEventBus()
    pc, gob = _pc(), _gob(1.0)
    participants = {pc.id: pc, gob.id: gob}
    factions = {pc.id: Faction.PARTY, gob.id: Faction.MONSTERS}
    ready: list[LevelUpReady] = []
    bus.subscribe(LevelUpReady, ready.append)
    svc = XpAwardService(
        event_bus=bus, curve=FastXpCurve(),
        participants=participants, factions=factions,
    )
    svc.subscribe()
    return bus, pc, gob, ready


def test_kill_awards_xp_and_triggers_level_up() -> None:
    bus, pc, _gob, ready = _setup()
    bus.publish(CreatureDied(actor_id="gob"))
    assert pc.xp == 100              # CR 1.0 * 100
    assert pc.level == 1             # сам уровень не двигаем — это LevelUpService
    assert ready and ready[0].actor_id == pc.id
    assert ready[0].to_level == 2    # 100 XP → L2 по FastXpCurve


def test_pc_death_does_not_award() -> None:
    bus, pc, _gob, ready = _setup()
    bus.publish(CreatureDied(actor_id="hero"))  # умер сам PC (PARTY)
    assert pc.xp == 0 and not ready
