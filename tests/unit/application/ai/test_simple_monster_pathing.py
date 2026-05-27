"""Регрессия: SimpleMonsterAI не должен крашиться, когда жадный путь к цели
пролегает через клетку, занятую союзником.

Баг (этап D): `_path_towards` бюджетировал каждый шаг по 5 фт, но `MoveAction`
берёт +5 фт за проход сквозь занятую союзником клетку (PHB-2024 стр. 24).
На длинном пути сквозь скучившихся союзников реальная стоимость превышала
бюджет, а `take_monster_turn` вызывал `MoveAction.execute` без проверки
`can_perform_against` → `ValueError: not enough movement` в середине пути.
Это роняло живой бой (демо `demo_skirmish`, где гоблины скучены).
"""
from __future__ import annotations

from dnd.application.engine.ai.simple_monster import (
    is_hostile_from_factions,
    take_monster_turn,
)
from dnd.application.engine.turn_context import TurnContext
from dnd.composition import build_scripted_dependencies
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.faction import Faction
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.domain.values.weapon import LONGSWORD, SCIMITAR


def _goblin(cid: str) -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=7,
        armor_class=13,
        speed_ft=30,
        equipped_weapon=SCIMITAR,
    )


def _warrior(cid: str) -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=16,
        speed_ft=30,
        equipped_weapon=LONGSWORD,
    )


def test_monster_move_through_ally_does_not_crash() -> None:
    """Гоблин в (8,1) идёт к воину в (0,1); союзник стоит в (5,1) на пути.

    6 шагов по 5 фт = 30 фт (весь бюджет), но шаг сквозь союзника стоит 10 →
    реальная стоимость 35 > 30. Старый код падал; новый — двигается на
    допустимую дистанцию без исключения.
    """
    bf = Battlefield(10, 3)
    actor = _goblin("goblin_actor")
    ally = _goblin("goblin_ally")
    warrior = _warrior("warrior")
    bf.place_creature(actor.id, Square(8, 1))
    bf.place_creature(ally.id, Square(5, 1))  # на прямой линии пути на запад
    bf.place_creature(warrior.id, Square(0, 1))

    deps, _bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=[])
    factions = {
        actor.id: Faction.MONSTERS,
        ally.id: Faction.MONSTERS,
        warrior.id: Faction.PARTY,
    }
    ctx = TurnContext(
        actor_id=actor.id,
        battlefield=deps.battlefield,
        dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier,
        condition_service=deps.condition_service,
        event_bus=deps.event_bus,
        rng=deps.rng,
        participants={actor.id: actor, ally.id: ally, warrior.id: warrior},
        movement_remaining_ft=30,
        factions=factions,
    )

    # Не должно бросать ValueError.
    take_monster_turn(actor, ctx, is_hostile=is_hostile_from_factions(actor.id, factions))

    # Гоблин сдвинулся ближе к воину и не ушёл «в минус» по движению.
    assert bf.position_of(actor.id).x < 8, "гоблин должен был сдвинуться к цели"
    assert ctx.movement_remaining_ft >= 0
