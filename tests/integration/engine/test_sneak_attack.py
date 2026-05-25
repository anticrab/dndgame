"""R1-9: Sneak Attack — +Nd6 при условии, раз за ход."""
from __future__ import annotations

from dnd.application.dto.engine_event import DamageDealt
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import FeatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import SHORTSWORD  # finesse


def _setup(rolls: list[int], *, ally: bool) -> tuple[Creature, Creature, object]:
    rogue = Creature.create(
        id_="rogue", name="Rogue",
        abilities=AbilityScores.of(str_=10, dex=16, con=12, int_=10, wis=10, cha=10),
        max_hp=16, armor_class=14, speed_ft=30, equipped_weapon=SHORTSWORD,
    )
    rogue.character_class = "rogue"
    rogue.level = 3
    rogue.features = (FeatureId("sneak_attack"),)
    gob = Creature.create(
        id_="gob", name="Gob",
        abilities=AbilityScores.of(str_=8, dex=8, con=10, int_=8, wis=8, cha=8),
        max_hp=40, armor_class=5, speed_ft=30, equipped_weapon=SHORTSWORD,
    )
    participants = {rogue.id: rogue, gob.id: gob}
    factions = {rogue.id: Faction.PARTY, gob.id: Faction.MONSTERS}
    bf = Battlefield(8, 8)
    bf.place_creature(rogue.id, Square(2, 2))
    bf.place_creature(gob.id, Square(3, 2))
    if ally:
        mate = Creature.create(
            id_="mate", name="Mate",
            abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
            max_hp=10, armor_class=14, speed_ft=30, equipped_weapon=SHORTSWORD,
        )
        participants[mate.id] = mate
        factions[mate.id] = Faction.PARTY
        bf.place_creature(mate.id, Square(4, 2))  # рядом с gob (5 фт)
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(participants=participants, factions=factions, deps=deps)
    enc.start()
    for _ in range(12):
        if enc.current_actor_id == rogue.id:
            break
        enc.start_turn()
        enc.end_turn()
    ctx = enc.start_turn()
    return rogue, gob, ctx


def test_sneak_attack_adds_dice_when_ally_adjacent() -> None:
    # 3 участника → 3 инициативы (rogue высший); attack d20=15; weapon d6=4;
    # L3 Sneak = 2d6 = [3,3].
    rogue, gob, ctx = _setup([20, 19, 18, 15, 4, 3, 3], ally=True)
    dmg: list[DamageDealt] = []
    ctx.event_bus.subscribe(DamageDealt, dmg.append)
    AttackAction().execute(rogue, weapon_attack_params(rogue, gob.id), ctx)
    # суммарный raw урон содержит 2d6 (=6) сверх shortsword d6
    assert sum(d.raw_amount for d in dmg) >= 4 + 6
    assert rogue.sneak_used_this_turn is True


def test_no_sneak_without_condition() -> None:
    # без союзника и без преимущества — sneak не срабатывает
    rogue, gob, ctx = _setup([20, 19, 15, 4], ally=False)
    dmg: list[DamageDealt] = []
    ctx.event_bus.subscribe(DamageDealt, dmg.append)
    AttackAction().execute(rogue, weapon_attack_params(rogue, gob.id), ctx)
    assert sum(d.raw_amount for d in dmg) < 4 + 6   # только shortsword
    assert rogue.sneak_used_this_turn is False
