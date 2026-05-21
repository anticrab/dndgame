"""Тесты OpportunityAttack (этап E6).

PHB-2024 стр. 22.

Покрытие:

* economy: REACTION тратится из Creature.reaction_used (per-round);
* двойная реакция в одном раунде → NO_ECONOMY_LEFT;
* execute переиспользует логику AttackAction (hit/miss/damage/события);
* интеграция: после MoveAction публикует OpportunityAttackProvoked,
  и подписчик может выполнить OpportunityAttack у threatener'а;
* TurnContext.reaction_used **не** мешает OpportunityAttack
  (контекст принадлежит двигающемуся).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dnd.application.dto.action import (
    ActionEconomyCost,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import (
    AttackResolved,
    AttackRolled,
    EngineEvent,
    OpportunityAttackProvoked,
)
from dnd.application.dto.ids import CreatureId
from dnd.application.engine.actions.attack import (
    AttackKind,
    AttackParams,
)
from dnd.application.engine.actions.move import MoveAction, MoveParams
from dnd.application.engine.actions.opportunity_attack import (
    OpportunityAttack,
)
from dnd.application.engine.condition_service import ConditionService
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.engine.modifier_applier import ModifierApplier, ModifierBag
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import register_default_conditions
from dnd.domain.conditions.registry import ConditionRegistry
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import AbilityScores
from dnd.domain.values.damage import DamageType
from dnd.domain.values.square import Square
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def _make_fighter(cid: str = "fighter") -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=16, dex=12, con=14, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=15,
        speed_ft=30,
    )


def _make_goblin(cid: str = "goblin", *, hp: int = 20, ac: int = 14) -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=8, dex=14, con=10, int_=10, wis=8, cha=8),
        max_hp=hp,
        armor_class=ac,
        speed_ft=30,
    )


def _attack_params(target_id: CreatureId) -> AttackParams:
    return AttackParams(
        target_id=target_id,
        kind=AttackKind.MELEE,
        attack_bonus=5,
        damage_expr="1d8+3",
        damage_type=DamageType.SLASHING,
        range_ft=5,
    )


def _setup(
    *,
    rng_rolls: list[int],
    bf_size: tuple[int, int] = (10, 10),
) -> tuple[Creature, Creature, TurnContext, InMemoryEventBus]:
    """Двое: fighter (реактор) в (3,2), goblin (двигающийся) в (2,2)."""
    fighter = _make_fighter()
    goblin = _make_goblin()
    bf = Battlefield(*bf_size)
    bf.place_creature(fighter.id, Square(3, 2))
    bf.place_creature(goblin.id, Square(2, 2))
    bus = InMemoryEventBus()
    rng = ScriptedRNG(rng_rolls)
    registry = ConditionRegistry()
    register_default_conditions(registry)
    # Хозяин TurnContext — goblin (двигающийся); fighter будет реагировать.
    ctx = TurnContext(
        actor_id=goblin.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
        participants={fighter.id: fighter, goblin.id: goblin},
        movement_remaining_ft=30,
    )
    return fighter, goblin, ctx, bus


# -- economy: REACTION per-round --------------------------------------


def test_can_perform_when_reaction_unused() -> None:
    fighter, _goblin, ctx, _ = _setup(rng_rolls=[])
    av = OpportunityAttack().can_perform(fighter, ctx)
    assert isinstance(av, Allowed)


@pytest.mark.rules
def test_can_perform_blocked_when_reaction_already_used() -> None:
    """PHB-2024 стр. 22: одна реакция в раунд."""
    fighter, _goblin, ctx, _ = _setup(rng_rolls=[])
    fighter.reaction_used = True
    av = OpportunityAttack().can_perform(fighter, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_ECONOMY_LEFT


def test_ctx_reaction_used_does_not_block_oa() -> None:
    """TurnContext.reaction_used принадлежит двигающемуся; OA реактора
    к нему не привязан."""
    fighter, _goblin, ctx, _ = _setup(rng_rolls=[])
    ctx.reaction_used = True  # это про goblin, не про fighter
    av = OpportunityAttack().can_perform(fighter, ctx)
    assert isinstance(av, Allowed)


# -- execute: то же что у AttackAction, но трату REACTION --------------


@pytest.mark.rules
def test_execute_consumes_reaction_and_returns_reaction_outcome() -> None:
    """OpportunityAttack тратит actor.reaction_used, не ctx.action_used."""
    fighter, goblin, ctx, _ = _setup(rng_rolls=[14, 5])

    outcome = OpportunityAttack().execute(
        fighter, _attack_params(goblin.id), ctx
    )

    assert outcome.success is True
    assert outcome.consumed is ActionEconomyCost.REACTION
    assert fighter.reaction_used is True
    # ctx.action_used не трогаем — это бюджет ДРУГОГО (goblin'а)
    assert ctx.action_used is False


def test_execute_publishes_attack_events_like_normal_attack() -> None:
    fighter, goblin, ctx, bus = _setup(rng_rolls=[14, 5])
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    OpportunityAttack().execute(
        fighter, _attack_params(goblin.id), ctx
    )

    types = [type(e).__name__ for e in captured]
    assert "AttackRolled" in types
    assert "DamageDealt" in types
    assert "AttackResolved" in types
    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.attacker_id == fighter.id
    assert atk.target_id == goblin.id
    res = next(e for e in captured if isinstance(e, AttackResolved))
    assert res.hit is True


@pytest.mark.rules
def test_execute_twice_in_round_raises_through_economy() -> None:
    """Хочешь две OA в раунд — нельзя (PHB-2024 стр. 22)."""
    fighter, goblin, ctx, _ = _setup(rng_rolls=[14, 5])
    OpportunityAttack().execute(fighter, _attack_params(goblin.id), ctx)
    # Второй — должна быть отвергнута can_perform.
    av = OpportunityAttack().can_perform(fighter, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_ECONOMY_LEFT


# -- интеграция: Move → publish provoked → handler OA -----------------


@pytest.mark.rules
def test_move_triggers_provoked_and_handler_executes_oa() -> None:
    """End-to-end: goblin выходит из reach fighter'а; подписанный
    handler выполняет OpportunityAttack у fighter'а.

    Это **демонстрация** того, как Encounter (этап F) свяжет
    OpportunityAttackProvoked с OpportunityAttack.execute.
    """
    fighter, goblin, ctx, bus = _setup(rng_rolls=[14, 5])
    oa = OpportunityAttack()
    executed: list[OpportunityAttackProvoked] = []

    def reactor_handler(evt: OpportunityAttackProvoked) -> None:
        # Простой авто-handler: если реактор — fighter, делаем OA.
        if evt.threatener_id != fighter.id:
            return
        executed.append(evt)
        oa.execute(fighter, _attack_params(goblin.id), ctx)

    bus.subscribe(OpportunityAttackProvoked, reactor_handler)

    # Goblin уходит из (2,2) в (1,2) — fighter в (3,2) теряет его из reach.
    MoveAction().execute(
        goblin, MoveParams(path=(Square(1, 2),)), ctx
    )

    assert len(executed) == 1
    assert executed[0].threatener_id == fighter.id
    assert fighter.reaction_used is True
    # Goblin получил урон от OA, движение тоже прошло.
    assert goblin.hit_points.current < goblin.hit_points.maximum
    assert ctx.battlefield.position_of(goblin.id) == Square(1, 2)


def test_oa_uses_same_attack_logic_as_regular_attack() -> None:
    """OpportunityAttack — подкласс AttackAction; крит-логика, cover,
    damage — тот же путь. Smoke: критический удар."""
    fighter, _goblin, ctx, bus = _setup(rng_rolls=[20, 4, 5])
    target = _make_goblin(ac=50, hp=50)
    ctx.battlefield.place_creature(target.id, Square(3, 3))
    ctx.participants[target.id] = target

    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    OpportunityAttack().execute(fighter, _attack_params(target.id), ctx)

    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.is_critical_hit is True
    assert atk.hit is True


# -- наследование properties ------------------------------------------


def test_oa_metadata() -> None:
    oa = OpportunityAttack()
    assert oa.id == "opportunity_attack"
    assert oa.name_key == "action.opportunity_attack"
    assert oa.economy_cost is ActionEconomyCost.REACTION


def test_oa_inherits_can_perform_against() -> None:
    """can_perform_against унаследован — те же проверки LoS/cover/range
    что и у обычной атаки."""
    fighter, goblin, ctx, _ = _setup(rng_rolls=[])
    av = OpportunityAttack().can_perform_against(
        fighter, _attack_params(goblin.id), ctx
    )
    assert isinstance(av, Allowed)


def test_oa_can_perform_does_not_use_condition_service() -> None:
    """Sanity: condition_service не должен вызываться в can_perform."""
    fighter, _goblin, ctx, _ = _setup(rng_rolls=[])
    ctx.condition_service = MagicMock()
    OpportunityAttack().can_perform(fighter, ctx)
    ctx.condition_service.assert_not_called()
