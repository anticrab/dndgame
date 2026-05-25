"""Q-7: StabilizeAction — стабилизация союзника Медициной DC10."""
from __future__ import annotations

from dnd.application.dto.action import Allowed, Forbidden
from dnd.application.dto.engine_event import CreatureStabilized
from dnd.application.engine.actions.stabilize import StabilizeAction, StabilizeParams
from dnd.application.engine.encounter import Encounter
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD


def _ally(id_: str, wis: int = 14) -> Creature:
    c = Creature.create(
        id_=id_, name=id_,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=wis, cha=10),
        max_hp=12, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    c.uses_death_saves = True
    return c


def _setup(rolls: list[int]) -> tuple[Encounter, Creature, Creature, object]:
    healer, downed = _ally("healer"), _ally("downed")
    enemy = Creature.create(
        id_="enemy", name="enemy",
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=7, armor_class=12, speed_ft=30, equipped_weapon=LONGSWORD,
    )
    bf = Battlefield(8, 8)
    bf.place_creature(healer.id, Square(2, 2))
    bf.place_creature(downed.id, Square(2, 3))  # рядом
    bf.place_creature(enemy.id, Square(7, 7))
    deps, _, _ = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    enc = Encounter(
        participants={healer.id: healer, downed.id: downed, enemy.id: enemy},
        factions={healer.id: Faction.PARTY, downed.id: Faction.PARTY,
                  enemy.id: Faction.MONSTERS},
        deps=deps,
    )
    enc.start()
    downed.take_damage(DamageInstance(amount=12, type_=DamageType.SLASHING))
    downed.begin_dying()
    for _ in range(15):
        if enc.current_actor_id == healer.id:
            break
        enc.start_turn()
        enc.end_turn()
    assert enc.current_actor_id == healer.id
    ctx = enc.start_turn()
    return enc, healer, downed, ctx


def test_stabilize_success_makes_target_stable() -> None:
    # 3 инициативы + запас на death saves лежачего + Медицина=20.
    enc, healer, downed, ctx = _setup([20, 19, 18] + [15] * 12 + [20] * 4)
    captured: list[CreatureStabilized] = []
    enc.event_bus.subscribe(CreatureStabilized, captured.append)
    action = StabilizeAction()
    params = StabilizeParams(target_id=downed.id)
    assert isinstance(action.can_perform_against(healer, params, ctx), Allowed)
    out = action.execute(healer, params, ctx)
    assert out.success
    assert downed.death_saves is not None and downed.death_saves.is_stable
    assert captured and captured[0].actor_id == downed.id
    assert captured[0].by == healer.id


def test_stabilize_healthy_target_forbidden() -> None:
    _enc, healer, downed, ctx = _setup([20, 19, 18] + [15] * 12 + [20] * 4)
    downed.heal(5)  # больше не dying
    action = StabilizeAction()
    avail = action.can_perform_against(healer, StabilizeParams(target_id=downed.id), ctx)
    assert isinstance(avail, Forbidden)
