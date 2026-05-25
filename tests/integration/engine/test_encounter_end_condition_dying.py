"""Q-5: end-condition с учётом dying (downed PC ≠ поражение)."""
from __future__ import annotations

from dnd.application.dto.engine_event import EncounterEnded
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _mk(id_: str, hp: int, *, dsave: bool) -> Creature:
    c = Creature.create(
        id_=id_, name=id_,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=hp, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    c.uses_death_saves = dsave
    return c


def _enc(pc: Creature, gob: Creature) -> Encounter:
    bf = Battlefield(6, 6)
    bf.place_creature(pc.id, Square(1, 1))
    bf.place_creature(gob.id, Square(4, 4))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[20, 19] + [10] * 30)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc


def test_downed_pc_does_not_end_encounter() -> None:
    pc, gob = _mk("hero", 10, dsave=True), _mk("gob", 7, dsave=False)
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    assert not enc.outcome_decided()  # PC лежит, но спасаем → бой идёт


def test_dead_pc_ends_encounter_as_defeat() -> None:
    pc, gob = _mk("hero", 10, dsave=True), _mk("gob", 7, dsave=False)
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    pc.death_saves = pc.death_saves.apply_save_roll(5)
    pc.death_saves = pc.death_saves.apply_save_roll(5)
    pc.death_saves = pc.death_saves.apply_save_roll(5)  # 3 провала
    assert pc.is_dead
    assert enc.outcome_decided()
    ended: list[EncounterEnded] = []
    enc.event_bus.subscribe(EncounterEnded, ended.append)
    enc.start_turn()
    enc.end_turn()
    assert ended and ended[0].winners is Faction.MONSTERS


def test_all_enemies_dead_while_pc_dying_is_party_win() -> None:
    pc, gob = _mk("hero", 10, dsave=True), _mk("gob", 7, dsave=False)
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    gob.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))  # враг мёртв
    assert enc.outcome_decided()
    ended: list[EncounterEnded] = []
    enc.event_bus.subscribe(EncounterEnded, ended.append)
    enc.start_turn()
    enc.end_turn()
    assert ended and ended[0].winners is Faction.PARTY
