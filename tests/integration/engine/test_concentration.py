"""REV-1: концентрация прерывается провалом CON-спасброска при уроне (PHB-2024)."""
from __future__ import annotations

from dnd.application.dto.engine_event import (
    ConcentrationBroken,
    DamageDealt,
    EngineEvent,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId, RollId, SpellId
from dnd.domain.values.square import Square


def _caster() -> Creature:
    c = Creature.create(
        id_=CreatureId("mage"), name="Mage",
        abilities=AbilityScores.of(str_=8, dex=12, con=14, int_=16, wis=10, cha=10),
        max_hp=20, armor_class=12, speed_ft=30,
    )
    c.concentration = SpellId("shield_of_faith")
    return c


def _gob() -> Creature:
    return Creature.create(
        id_=CreatureId("gob"), name="Gob",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7, armor_class=13, speed_ft=30,
    )


def _enc(rolls: list[int]) -> tuple[Encounter, Creature]:
    bf = Battlefield(5, 5)
    mage, gob = _caster(), _gob()
    bf.place_creature(mage.id, Square(1, 1))
    bf.place_creature(gob.id, Square(3, 3))
    deps, _bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={mage.id: mage, gob.id: gob},
        factions={mage.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()  # 2 d20 инициативы
    return enc, mage


def _dmg(target: CreatureId, amount: int) -> DamageDealt:
    return DamageDealt(
        attacker_id=CreatureId("gob"), target_id=target,
        damage_roll_id=RollId("00000000-0000-0000-0000-000000000000"),
        damage_type=DamageType.SLASHING, raw_amount=amount, final_amount=amount,
        is_critical=False, hp_after=10, hp_max=20, was_lethal=False,
    )


def test_concentration_broken_on_failed_save() -> None:
    # rolls: init x2, затем CON-save d20=1 → 1+CON(2)=3 < DC max(10, 12//2)=10
    enc, mage = _enc([15, 5, 1])
    broken: list[ConcentrationBroken] = []
    enc.event_bus.subscribe(ConcentrationBroken, broken.append)
    enc.event_bus.publish(_dmg(mage.id, 12))
    assert mage.concentration is None
    assert broken and broken[0].actor_id == mage.id


def test_concentration_held_on_successful_save() -> None:
    # CON-save d20=20 → 22 ≥ 10 → удержали
    enc, mage = _enc([15, 5, 20])
    enc.event_bus.publish(_dmg(mage.id, 12))
    assert mage.concentration == SpellId("shield_of_faith")


def test_no_save_without_concentration() -> None:
    enc, mage = _enc([15, 5])
    mage.concentration = None
    captured: list[EngineEvent] = []
    enc.event_bus.subscribe(ConcentrationBroken, captured.append)
    enc.event_bus.publish(_dmg(mage.id, 12))  # роллов на save не тратим
    assert captured == []
