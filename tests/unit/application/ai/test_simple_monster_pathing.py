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
    _find_nearest_hostile,
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


def _downed_pc(cid: str) -> Creature:
    """PC, лежащий без сознания (0 HP, спасброски от смерти, ещё жив)."""
    from dnd.domain.values.death_save_state import DeathSaveState

    pc = _warrior(cid)
    pc.uses_death_saves = True
    pc.hit_points = pc.hit_points.take_damage(pc.hit_points.maximum)
    pc.death_saves = DeathSaveState()
    return pc


def _ctx_for(actor: Creature, participants: dict[CreatureId, Creature],
             factions: dict[CreatureId, Faction], bf: Battlefield,
             rolls: list[int]) -> TurnContext:
    deps, _bus, _rng = build_scripted_dependencies(battlefield=bf, rolls=rolls)
    return TurnContext(
        actor_id=actor.id, battlefield=deps.battlefield, dice_roller=deps.dice_roller,
        modifier_applier=deps.modifier_applier, condition_service=deps.condition_service,
        event_bus=deps.event_bus, rng=deps.rng, participants=participants,
        movement_remaining_ft=actor.speed_ft, factions=factions,
    )


def test_monster_finishes_downed_enemy_when_no_conscious() -> None:
    """Нет живых целей → гоблин добивает лежачего PC (иначе бой висит до
    round-limit). Удар в упор = авто-крит = 2 провала спасброска."""
    bf = Battlefield(6, 3)
    goblin = _goblin("g")
    pc = _downed_pc("hero")
    bf.place_creature(goblin.id, Square(1, 1))
    bf.place_creature(pc.id, Square(2, 1))  # смежно — рукопашная достаёт
    participants = {goblin.id: goblin, pc.id: pc}
    factions = {goblin.id: Faction.MONSTERS, pc.id: Faction.PARTY}
    # d20=19 (попадание) + 2 кубика урона (крит удваивает 1d6 скимитара).
    ctx = _ctx_for(goblin, participants, factions, bf, rolls=[19, 3, 3])

    take_monster_turn(goblin, ctx, is_hostile=is_hostile_from_factions(goblin.id, factions))

    assert pc.death_saves is not None
    assert pc.death_saves.failures == 2, "удар по лежачему в упор = 2 провала"


def test_monster_prefers_conscious_over_downed() -> None:
    """Если есть живой враг — добивать лежачего не идём."""
    bf = Battlefield(8, 3)
    goblin = _goblin("g")
    downed = _downed_pc("downed")
    alive = _warrior("alive")
    bf.place_creature(goblin.id, Square(1, 1))
    bf.place_creature(downed.id, Square(2, 1))   # лежачий ближе
    bf.place_creature(alive.id, Square(5, 1))    # живой дальше
    participants = {goblin.id: goblin, downed.id: downed, alive.id: alive}
    factions = {
        goblin.id: Faction.MONSTERS,
        downed.id: Faction.PARTY,
        alive.id: Faction.PARTY,
    }
    ctx = _ctx_for(goblin, participants, factions, bf, rolls=[])

    target = _find_nearest_hostile(
        goblin, ctx, is_hostile_from_factions(goblin.id, factions)
    )
    assert target is not None and target.id == alive.id


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
