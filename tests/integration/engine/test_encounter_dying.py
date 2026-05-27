"""Q-2/Q-3/Q-4: lifecycle умирания в Encounter."""

from __future__ import annotations

from dnd.application.dto.engine_event import DamageDealt, DeathSaveRolled
from dnd.application.engine.actions.attack import AttackAction, AttackKind, AttackParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.conditions.builtin import UNCONSCIOUS
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _pc() -> Creature:
    c = Creature.create(
        id_="hero",
        name="Hero",
        abilities=AbilityScores.of(str_=14, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=12,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )
    c.uses_death_saves = True
    return c


def _goblin() -> Creature:
    return Creature.create(
        id_="gob",
        name="Goblin",
        abilities=AbilityScores.of(str_=12, dex=14, con=10, int_=8, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def _enc(pc: Creature, gob: Creature, *, rolls: list[int] | None = None) -> Encounter:
    bf = Battlefield(8, 8)
    bf.place_creature(pc.id, Square(1, 1))
    bf.place_creature(gob.id, Square(6, 6))
    deps, _, _ = build_scripted_dependencies(
        battlefield=bf, rolls=rolls if rolls is not None else [20] * 40
    )
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    return enc


def _lethal(attacker: Creature, target: Creature) -> DamageDealt:
    """Синтетическое DamageDealt(was_lethal=True) — сигнал падения цели.
    Урон сам наносится через ``take_damage`` в тесте; это событие триггерит
    реакцию Encounter (dying/CORPSE), как реальный урон оружием/заклинанием."""
    return DamageDealt(
        attacker_id=attacker.id,
        target_id=target.id,
        damage_roll_id="00000000-0000-0000-0000-000000000000",
        damage_type=DamageType.SLASHING,
        raw_amount=0,
        final_amount=0,
        is_critical=False,
        hp_after=target.hit_points.current,
        hp_max=target.hit_points.maximum,
        was_lethal=True,
    )


def test_pc_dropped_to_zero_enters_dying_not_dead() -> None:
    pc, gob = _pc(), _goblin()
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    enc.event_bus.publish(_lethal(gob, pc))
    assert pc.death_saves is not None
    assert pc.has_condition(UNCONSCIOUS)
    assert not pc.is_dead
    assert not enc.is_concluded  # бой продолжается


def test_dying_pc_gets_implied_prone_and_incapacitated() -> None:
    """REV-7: Unconscious подразумевает Prone и Incapacitated (PHB-2024 стр. 367)
    — накладываются через ConditionService, а не голым apply_condition."""
    from dnd.domain.conditions.builtin import INCAPACITATED, PRONE

    pc, gob = _pc(), _goblin()
    enc = _enc(pc, gob)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    enc.event_bus.publish(_lethal(gob, pc))
    assert pc.has_condition(UNCONSCIOUS)
    assert pc.has_condition(PRONE)
    assert pc.has_condition(INCAPACITATED)


def test_npc_downed_does_not_get_death_saves() -> None:
    pc, gob = _pc(), _goblin()
    enc = _enc(pc, gob)
    gob.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    enc.event_bus.publish(_lethal(pc, gob))
    assert gob.death_saves is None


def test_dying_pc_auto_rolls_death_save_on_turn_start() -> None:
    pc, gob = _pc(), _goblin()
    # rolls: 2 инициативы (PC выше), затем death saves = 15 (успех).
    enc = _enc(pc, gob, rolls=[20, 19] + [15] * 20)
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()

    captured: list[DeathSaveRolled] = []
    enc.event_bus.subscribe(DeathSaveRolled, captured.append)

    for _ in range(12):
        if enc.current_actor_id == pc.id:
            break
        enc.start_turn()
        enc.end_turn()
    assert enc.current_actor_id == pc.id
    enc.start_turn()  # ход PC → авто death save
    assert len(captured) == 1
    assert captured[0].actor_id == pc.id
    assert captured[0].result == "success"
    assert pc.death_saves is not None and pc.death_saves.successes == 1


def test_massive_damage_on_pc_emits_creature_died() -> None:
    """audit M-1: PC, убитый огромным уроном (overflow >= max HP), умирает
    мгновенно И публикует CreatureDied (а не «молча»)."""
    from dnd.application.dto.engine_event import CreatureDied

    pc, gob = _pc(), _goblin()
    enc = _enc(pc, gob)
    died: list[CreatureDied] = []
    enc.event_bus.subscribe(CreatureDied, died.append)
    pc.take_damage(DamageInstance(amount=30, type_=DamageType.SLASHING))  # 30 >> max 10
    assert pc.is_dead
    enc.event_bus.publish(_lethal(gob, pc))
    assert died and died[0].actor_id == pc.id


def test_melee_hit_on_dying_pc_is_auto_crit() -> None:
    pc, gob = _pc(), _goblin()
    bf = Battlefield(8, 8)
    bf.place_creature(pc.id, Square(2, 2))
    bf.place_creature(gob.id, Square(2, 3))  # вплотную (1 клетка = 5 фт)
    # rolls: 2 инициативы (gob выше), атака=10 (+4=14 vs AC12 → hit),
    # урон 1d6→крит 2d6 = два значения ≤6.
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=[19, 20, 10, 3, 3] + [1] * 20)
    enc = Encounter(
        participants={pc.id: pc, gob.id: gob},
        factions={pc.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    pc.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    pc.begin_dying()
    for _ in range(12):
        if enc.current_actor_id == gob.id:
            break
        enc.start_turn()
        enc.end_turn()
    assert enc.current_actor_id == gob.id
    ctx = enc.start_turn()
    before = pc.death_saves.failures
    AttackAction().execute(
        gob,
        AttackParams(
            target_id=pc.id,
            kind=AttackKind.MELEE,
            attack_bonus=4,
            damage_expr="1d6",
            damage_type=DamageType.SLASHING,
            range_ft=5,
        ),
        ctx,
    )
    assert pc.death_saves.failures - before == 2  # авто-крит → 2 провала
