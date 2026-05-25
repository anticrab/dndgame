"""R1-8: Improved Critical меняет порог крита в AttackAction."""
from __future__ import annotations

from dnd.application.dto.engine_event import AttackRolled
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _setup(rolls: list[int]) -> tuple[Creature, Creature, object]:
    a = Creature.create(
        id_="f", name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20, armor_class=16, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    b = Creature.create(
        id_="g", name="G",
        abilities=AbilityScores.of(str_=8, dex=10, con=10, int_=8, wis=8, cha=8),
        max_hp=30, armor_class=5, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(6, 6)
    bf.place_creature(a.id, Square(2, 2))
    bf.place_creature(b.id, Square(3, 2))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={a.id: a, b.id: b},
        factions={a.id: Faction.PARTY, b.id: Faction.MONSTERS}, deps=deps,
    )
    enc.start()
    for _ in range(12):
        if enc.current_actor_id == a.id:
            break
        enc.start_turn()
        enc.end_turn()
    ctx = enc.start_turn()
    return a, b, ctx


def test_d20_19_is_crit_with_improved_critical() -> None:
    # init [20,19], атака d20=19 + урон (крит → удвоение костей: 2 значения).
    a, b, ctx = _setup([20, 19, 19, 4, 4])
    a.crit_range_min = 19
    rolled: list[AttackRolled] = []
    ctx.event_bus.subscribe(AttackRolled, rolled.append)
    AttackAction().execute(a, weapon_attack_params(a, b.id), ctx)
    assert rolled and rolled[0].is_critical_hit is True


def test_d20_19_not_crit_by_default() -> None:
    a, b, ctx = _setup([20, 19, 19, 4])
    rolled: list[AttackRolled] = []
    ctx.event_bus.subscribe(AttackRolled, rolled.append)
    AttackAction().execute(a, weapon_attack_params(a, b.id), ctx)
    assert rolled and rolled[0].is_critical_hit is False   # порог по умолчанию 20
