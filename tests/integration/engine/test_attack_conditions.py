"""Атака учитывает состояния цели/атакующего (T3)."""

from __future__ import annotations

from dnd.application.dto.engine_event import AttackRolled, EngineEvent
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import PARALYZED, POISONED
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _enc(rolls: list[int]) -> tuple[Encounter, Creature, Creature, list[EngineEvent]]:
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
    gob = Creature.create(
        id_=CreatureId("g"),
        name="g",
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=30,
        armor_class=13,
        speed_ft=30,
    )
    bf.place_creature(hero.id, Square(1, 2))
    bf.place_creature(gob.id, Square(2, 2))
    deps, bus, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={hero.id: hero, gob.id: gob},
        factions={hero.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    enc.start()
    return enc, hero, gob, captured


def test_attack_against_paralyzed_has_advantage() -> None:
    # advantage → 2 d20; цель Paralyzed в упор → авто-крит → 2 кости урона.
    enc, hero, gob, captured = _enc([18, 1, 5, 19, 7, 7])
    gob.apply_condition(PARALYZED)
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    assert actor.id == hero.id
    AttackAction().execute(actor, weapon_attack_params(actor, gob.id), ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.advantage is True


def test_poisoned_attacker_has_disadvantage() -> None:
    enc, hero, gob, captured = _enc([18, 1, 19, 5, 7])
    hero.apply_condition(POISONED)
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    AttackAction().execute(actor, weapon_attack_params(actor, gob.id), ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.disadvantage is True


def test_melee_point_blank_vs_paralyzed_is_auto_crit() -> None:
    # advantage от Paralyzed → 2 d20 (10,10, не нат-20), цель в упор → авто-крит.
    enc, _hero, gob, captured = _enc([18, 1, 10, 10, 4, 4])
    gob.apply_condition(PARALYZED)
    ctx = enc.start_turn()
    actor = enc.participants[enc.current_actor_id]
    AttackAction().execute(actor, weapon_attack_params(actor, gob.id), ctx)
    ar = next(e for e in captured if isinstance(e, AttackRolled))
    assert ar.hit is True
    assert ar.is_critical_hit is True
