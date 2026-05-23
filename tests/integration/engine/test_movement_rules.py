"""Интеграционные тесты правил движения PHB-2024 стр. 24.

Покрытие выше unit-тестов `test_move_action.py`: здесь работает
полная связка `MoveAction.execute` поверх настоящего `Battlefield`,
`EventBus`, `DiceRoller`, `ModifierApplier` — с реальными factions
в `TurnContext` (как их выставляет `Encounter`).

Проверяем три правила:
1. Нельзя завершить ход на занятой клетке.
2. Нельзя проходить сквозь враждебного.
3. Проход через союзника = difficult terrain (+5 фт).
"""

from __future__ import annotations

import pytest

from dnd.application.dto.action import Allowed, Forbidden, ForbiddenReason
from dnd.application.dto.engine_event import EngineEvent, MoveCompleted
from dnd.application.dto.ids import CreatureId
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
from dnd.domain.values.faction import Faction
from dnd.domain.values.square import Square
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def _creature(cid: str) -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=10,
        armor_class=12,
        speed_ft=30,
    )


def _ctx(
    actor: Creature,
    *,
    bf: Battlefield,
    others: list[tuple[Creature, Faction]],
    speed_ft: int = 30,
) -> tuple[TurnContext, InMemoryEventBus]:
    participants: dict[CreatureId, Creature] = {actor.id: actor}
    factions: dict[CreatureId, Faction] = {actor.id: Faction.PARTY}
    for cr, f in others:
        participants[cr.id] = cr
        factions[cr.id] = f

    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    registry = ConditionRegistry()
    register_default_conditions(registry)
    ctx = TurnContext(
        actor_id=actor.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
        participants=participants,
        factions=factions,
        movement_remaining_ft=speed_ft,
    )
    return ctx, bus


def _capture(bus: InMemoryEventBus) -> list[EngineEvent]:
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    return captured


@pytest.mark.rules
@pytest.mark.integration
def test_cannot_end_move_on_enemy_square_via_execute() -> None:
    """Финал пути на клетке врага → can_perform_against отказ,
    Battlefield не меняется."""
    bf = Battlefield(5, 5)
    actor = _creature("warrior")
    enemy = _creature("goblin")
    bf.place_creature(actor.id, Square(1, 2))
    bf.place_creature(enemy.id, Square(2, 2))
    ctx, bus = _ctx(actor, bf=bf, others=[(enemy, Faction.MONSTERS)])
    captured = _capture(bus)

    av = MoveAction().can_perform_against(
        actor, MoveParams(path=(Square(2, 2),)), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.SQUARE_OCCUPIED
    assert bf.position_of(actor.id) == Square(1, 2)
    # Никаких MoveCompleted не было опубликовано.
    assert all(not isinstance(e, MoveCompleted) for e in captured)


@pytest.mark.rules
@pytest.mark.integration
def test_cannot_pass_through_hostile_via_execute() -> None:
    """Промежуточная клетка с врагом → отказ."""
    bf = Battlefield(7, 3)
    actor = _creature("warrior")
    enemy = _creature("goblin")
    bf.place_creature(actor.id, Square(1, 1))
    bf.place_creature(enemy.id, Square(2, 1))
    ctx, bus = _ctx(actor, bf=bf, others=[(enemy, Faction.MONSTERS)])
    captured = _capture(bus)

    av = MoveAction().can_perform_against(
        actor, MoveParams(path=(Square(2, 1), Square(3, 1))), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.PATH_THROUGH_HOSTILE
    assert bf.position_of(actor.id) == Square(1, 1)
    assert all(not isinstance(e, MoveCompleted) for e in captured)


@pytest.mark.rules
@pytest.mark.integration
def test_pass_through_ally_costs_extra_5ft_via_execute() -> None:
    """Союзник на пути → +5 фт к стоимости (PHB-2024 стр. 24).

    Путь warrior'а в 2 клетки через ally: 5 (вход через ally — это
    «difficult», +5) + 5 (финал) = 15 ft. С speed=30 хватает; execute
    публикует MoveCompleted с total_spent_ft=15.
    """
    bf = Battlefield(7, 3)
    actor = _creature("warrior")
    ally = _creature("ally")
    bf.place_creature(actor.id, Square(1, 1))
    bf.place_creature(ally.id, Square(2, 1))
    ctx, bus = _ctx(actor, bf=bf, others=[(ally, Faction.PARTY)])
    captured = _capture(bus)

    params = MoveParams(path=(Square(2, 1), Square(3, 1)))
    assert isinstance(
        MoveAction().can_perform_against(actor, params, ctx), Allowed
    )
    MoveAction().execute(actor, params, ctx)

    completed = [e for e in captured if isinstance(e, MoveCompleted)]
    assert len(completed) == 1
    assert completed[0].total_spent_ft == 15
    # Actor реально оказался в конце пути.
    assert bf.position_of(actor.id) == Square(3, 1)


@pytest.mark.rules
@pytest.mark.integration
def test_pass_through_ally_with_speed_too_low_is_rejected() -> None:
    """Если хватает на «прямой» путь, но не на «через союзника» — отказ
    NOT_ENOUGH_MOVEMENT, а не SQUARE_OCCUPIED."""
    bf = Battlefield(7, 3)
    actor = _creature("warrior")
    ally = _creature("ally")
    bf.place_creature(actor.id, Square(1, 1))
    bf.place_creature(ally.id, Square(2, 1))
    ctx, _ = _ctx(actor, bf=bf, others=[(ally, Faction.PARTY)], speed_ft=10)

    params = MoveParams(path=(Square(2, 1), Square(3, 1)))
    av = MoveAction().can_perform_against(actor, params, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NOT_ENOUGH_MOVEMENT
