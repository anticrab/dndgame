"""Тесты MoveAction — пошаговое перемещение по сетке.

PHB-2024 стр. 22 («Перемещение», «Перемещение около других существ»),
стр. 23 (труднопроходимая местность).

Покрытие:

* can_perform: блокеры состояний, нет движения;
* can_perform_against: пустой путь, не-соседняя клетка, OOB, impassable,
  недостаточно футов с учётом difficult;
* execute: шаг за шагом списывает футы, мутирует Battlefield,
  публикует MoveStepTaken и MoveCompleted;
* difficult terrain ×2 cost;
* opportunity-провокация: outuking из reach живого threatener'а →
  публикуется OpportunityAttackProvoked, один раз за threatener'а;
* Disengage-флаг подавляет провокации;
* мёртвый/обездвиженный threatener не провоцирует;
* events_published в нужном порядке.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.action import (
    ActionEconomyCost,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import (
    EngineEvent,
    MoveCompleted,
    MoveStepTaken,
    OpportunityAttackProvoked,
)
from dnd.application.dto.ids import ConditionId, CreatureId
from dnd.application.engine.actions.move import MoveAction, MoveParams
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import DIFFICULT, WALL
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG

_START = Square(2, 2)


# -- Фабрики ------------------------------------------------------------


def _make_creature(creature_id: str = "actor", *, hp: int = 20) -> Creature:
    return Creature.create(
        id_=CreatureId(creature_id),
        name=creature_id,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=hp,
        armor_class=12,
        speed_ft=30,
    )


def _setup(
    *,
    start: Square = _START,
    others: tuple[tuple[Creature, Square], ...] = (),
    bf_size: tuple[int, int] = (10, 10),
    speed_ft: int = 30,
) -> tuple[Creature, TurnContext, InMemoryEventBus]:
    actor = _make_creature("actor")
    bf = Battlefield(*bf_size)
    bf.place_creature(actor.id, start)
    participants: dict[CreatureId, Creature] = {actor.id: actor}
    for cr, pos in others:
        bf.place_creature(cr.id, pos)
        participants[cr.id] = cr

    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    dice = ComputerDiceRoller(rng=rng, event_bus=bus)
    registry = ConditionRegistry()
    register_default_conditions(registry)

    ctx = TurnContext(
        actor_id=actor.id,
        battlefield=bf,
        dice_roller=dice,
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
        participants=participants,
        movement_remaining_ft=speed_ft,
    )
    return actor, ctx, bus


def _capture(bus: InMemoryEventBus) -> list[EngineEvent]:
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    return captured


# -- can_perform ---------------------------------------------------------


def test_can_perform_allowed_with_movement() -> None:
    _, ctx, _ = _setup()
    assert isinstance(MoveAction().can_perform(_make_creature(), ctx), Allowed)


def test_can_perform_no_movement_remaining() -> None:
    _, ctx, _ = _setup(speed_ft=0)
    av = MoveAction().can_perform(_make_creature(), ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NOT_ENOUGH_MOVEMENT


@pytest.mark.rules
@pytest.mark.parametrize(
    "condition_id",
    ["incapacitated", "stunned", "paralyzed", "unconscious"],
)
def test_can_perform_blocked_by_condition(condition_id: str) -> None:
    """PHB-2024 стр. 367: Incapacitated/Stunned/Paralyzed/Unconscious блокируют
    действия и/или дают speed=0."""
    actor, ctx, _ = _setup()
    actor.apply_condition(ConditionId(condition_id))
    av = MoveAction().can_perform(actor, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.CONDITION_BLOCKS_ACTION


# -- can_perform_against (валидация пути) ------------------------------


def test_empty_path_is_invalid() -> None:
    actor, ctx, _ = _setup()
    av = MoveAction().can_perform_against(
        actor, MoveParams(path=()), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.INVALID_PATH


def test_non_adjacent_step_invalid() -> None:
    """Шаг должен быть соседним."""
    actor, ctx, _ = _setup()
    # Прыжок через клетку
    av = MoveAction().can_perform_against(
        actor, MoveParams(path=(Square(4, 2),)), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.INVALID_PATH


def test_path_out_of_bounds_invalid() -> None:
    actor, ctx, _ = _setup(start=Square(0, 0))
    av = MoveAction().can_perform_against(
        actor, MoveParams(path=(Square(-1, 0),)), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.INVALID_PATH


def test_path_through_wall_impassable() -> None:
    actor, ctx, _ = _setup()
    ctx.battlefield.set_terrain(Square(3, 2), WALL)
    av = MoveAction().can_perform_against(
        actor, MoveParams(path=(Square(3, 2),)), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.IMPASSABLE_TERRAIN


@pytest.mark.rules
def test_difficult_terrain_doubles_cost_in_validation() -> None:
    """6 клеток difficult → 60 фт; со speed 30 — недостаточно."""
    actor, ctx, _ = _setup(speed_ft=30)
    bf = ctx.battlefield
    path: list[Square] = []
    for i in range(1, 7):  # 6 шагов вправо
        sq = Square(2 + i, 2)
        bf.set_terrain(sq, DIFFICULT)
        path.append(sq)
    av = MoveAction().can_perform_against(
        actor, MoveParams(path=tuple(path)), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NOT_ENOUGH_MOVEMENT


def test_valid_path_allowed() -> None:
    actor, ctx, _ = _setup(speed_ft=30)
    av = MoveAction().can_perform_against(
        actor,
        MoveParams(path=(Square(3, 2), Square(4, 2), Square(5, 2))),
        ctx,
    )
    assert isinstance(av, Allowed)


# -- execute (без провокаций) ------------------------------------------


def test_execute_moves_step_by_step_and_publishes() -> None:
    actor, ctx, bus = _setup(speed_ft=30)
    captured = _capture(bus)

    outcome = MoveAction().execute(
        actor,
        MoveParams(path=(Square(3, 2), Square(4, 2))),
        ctx,
    )

    assert outcome.success is True
    assert outcome.consumed is ActionEconomyCost.MOVEMENT
    assert outcome.movement_spent_ft == 10
    assert outcome.events_published == (
        "move.step_taken",
        "move.step_taken",
        "move.completed",
    )

    # Состояние поля
    assert ctx.battlefield.position_of(actor.id) == Square(4, 2)
    assert ctx.movement_remaining_ft == 20

    # Конкретные события
    step1, step2, done = (
        e for e in captured if isinstance(e, (MoveStepTaken, MoveCompleted))
    )
    assert isinstance(step1, MoveStepTaken)
    assert step1.frm == _START and step1.to == Square(3, 2)
    assert step1.cost_ft == 5
    assert step1.difficult is False
    assert isinstance(step2, MoveStepTaken)
    assert step2.frm == Square(3, 2) and step2.to == Square(4, 2)
    assert isinstance(done, MoveCompleted)
    assert done.start_pos == _START and done.end_pos == Square(4, 2)
    assert done.steps == 2 and done.total_spent_ft == 10


@pytest.mark.rules
def test_execute_difficult_terrain_costs_10ft() -> None:
    """PHB-2024 стр. 23: каждый фут в difficult terrain стоит 2 фута."""
    actor, ctx, bus = _setup(speed_ft=30)
    ctx.battlefield.set_terrain(Square(3, 2), DIFFICULT)
    captured = _capture(bus)

    MoveAction().execute(
        actor, MoveParams(path=(Square(3, 2),)), ctx
    )

    step = next(e for e in captured if isinstance(e, MoveStepTaken))
    assert step.cost_ft == 10
    assert step.difficult is True
    assert ctx.movement_remaining_ft == 20  # 30 - 10


def test_execute_rejects_wrong_params_type() -> None:
    from dnd.application.dto.action import NoParams

    actor, ctx, _ = _setup()
    with pytest.raises(TypeError, match="MoveParams"):
        MoveAction().execute(actor, NoParams(), ctx)


def test_execute_diagonal_step_costs_5ft() -> None:
    """Стандарт MVP: диагональ — те же 5 фут (не 5/10/5)."""
    actor, ctx, bus = _setup(speed_ft=30)
    captured = _capture(bus)

    MoveAction().execute(
        actor, MoveParams(path=(Square(3, 3),)), ctx
    )
    step = next(e for e in captured if isinstance(e, MoveStepTaken))
    assert step.cost_ft == 5
    assert ctx.movement_remaining_ft == 25


# -- провокации opportunity attack -------------------------------------


@pytest.mark.rules
def test_opportunity_provoked_when_leaving_reach() -> None:
    """PHB-2024 стр. 22: existo выходит из reach живого недружественного
    threatener'а — провокация."""
    threatener = _make_creature("orc")
    # Threatener стоит в (3,2); reach 5ft = соседи (2..4, 1..3).
    # Actor стартует в (2,2) — внутри reach. Шаг в (1,2) — выход.
    actor, ctx, bus = _setup(others=((threatener, Square(3, 2)),))
    captured = _capture(bus)

    MoveAction().execute(actor, MoveParams(path=(Square(1, 2),)), ctx)

    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert len(aops) == 1
    assert aops[0].threatener_id == threatener.id
    assert aops[0].leaving_square == _START


@pytest.mark.rules
def test_opportunity_not_provoked_while_staying_in_reach() -> None:
    """Шаг внутри reach зоны — не провокация."""
    threatener = _make_creature("orc")
    actor, ctx, bus = _setup(others=((threatener, Square(4, 2)),))
    # Стартуем в (3,2), шагаем в (3,3) — обе клетки в reach (4,2).
    ctx.battlefield.move_creature(actor.id, Square(3, 2))
    captured = _capture(bus)

    MoveAction().execute(actor, MoveParams(path=(Square(3, 3),)), ctx)

    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert aops == []


@pytest.mark.rules
def test_opportunity_provoked_once_per_threatener_in_one_move() -> None:
    """PHB-2024: провокация — одна на threatener'а за движение, даже
    если existo дважды пересекает его reach."""
    threatener = _make_creature("orc")
    actor, ctx, bus = _setup(others=((threatener, Square(4, 4)),))
    # Стартуем в (3,4) (в reach), идём (2,4) (вне reach), (3,4) (снова в),
    # (2,4) (снова вне). Тригер должен сработать ОДИН раз.
    ctx.battlefield.move_creature(actor.id, Square(3, 4))
    captured = _capture(bus)

    MoveAction().execute(
        actor,
        MoveParams(
            path=(Square(2, 4), Square(3, 4), Square(2, 4))
        ),
        ctx,
    )
    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert len(aops) == 1


@pytest.mark.rules
def test_disengage_suppresses_provocation() -> None:
    """PHB-2024 стр. 22: Disengage — твой ход не провоцирует opportunity
    attacks до конца хода."""
    threatener = _make_creature("orc")
    actor, ctx, bus = _setup(others=((threatener, Square(3, 2)),))
    ctx.disengaged = True
    captured = _capture(bus)

    MoveAction().execute(actor, MoveParams(path=(Square(1, 2),)), ctx)

    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert aops == []


def test_dead_threatener_does_not_provoke() -> None:
    threatener = _make_creature("orc", hp=1)
    threatener.take_damage(DamageInstance(amount=10, type_=DamageType.SLASHING))
    assert threatener.is_alive is False
    actor, ctx, bus = _setup(others=((threatener, Square(3, 2)),))
    captured = _capture(bus)

    MoveAction().execute(actor, MoveParams(path=(Square(1, 2),)), ctx)
    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert aops == []


@pytest.mark.rules
def test_incapacitated_threatener_does_not_provoke() -> None:
    """PHB-2024 стр. 367: Incapacitated → не может реагировать."""
    threatener = _make_creature("orc")
    threatener.apply_condition(ConditionId("incapacitated"))
    actor, ctx, bus = _setup(others=((threatener, Square(3, 2)),))
    captured = _capture(bus)

    MoveAction().execute(actor, MoveParams(path=(Square(1, 2),)), ctx)
    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert aops == []
