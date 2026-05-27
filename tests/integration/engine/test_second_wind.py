"""R1-10: Second Wind — bonus action, heal 1d10+level, ресурс 1/short rest."""

from __future__ import annotations

from dnd.application.dto.action import Forbidden
from dnd.application.engine.actions.second_wind import (
    SecondWindAction,
    SecondWindParams,
)
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square


def _setup(rolls: list[int]) -> tuple[Creature, object]:
    f = Creature.create(
        id_="f",
        name="F",
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
    )
    f.character_class = "fighter"
    f.level = 2
    f.resource_uses = {"second_wind": 1}
    gob = Creature.create(
        id_="gob",
        name="Gob",
        abilities=AbilityScores.of(str_=8, dex=8, con=10, int_=8, wis=8, cha=8),
        max_hp=12,
        armor_class=13,
        speed_ft=30,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(f.id, Square(1, 1))
    bf.place_creature(gob.id, Square(6, 6))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={f.id: f, gob.id: gob},
        factions={f.id: Faction.PARTY, gob.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    for _ in range(12):
        if enc.current_actor_id == f.id:
            break
        enc.start_turn()
        enc.end_turn()
    ctx = enc.start_turn()
    return f, ctx


def test_second_wind_heals_and_consumes_use() -> None:
    f, ctx = _setup([20, 1, 7])  # init f=20, gob=1 + heal d10=7
    f.take_damage(DamageInstance(amount=15, type_=DamageType.SLASHING))  # 20→5
    out = SecondWindAction().execute(f, SecondWindParams(), ctx)
    assert out.success
    assert f.hit_points.current == 5 + (7 + 2)  # d10=7 + level 2
    assert f.resource_uses["second_wind"] == 0
    assert ctx.bonus_action_used is True


def test_second_wind_forbidden_without_use() -> None:
    f, ctx = _setup([20, 1])
    f.resource_uses["second_wind"] = 0
    avail = SecondWindAction().can_perform_against(f, SecondWindParams(), ctx)
    assert isinstance(avail, Forbidden)
