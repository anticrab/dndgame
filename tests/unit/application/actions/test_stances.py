"""Тесты Dodge / Dash / Disengage (этап E4).

PHB-2024 стр. 22 («Доступные действия»).

Покрытие:

* can_perform: блокеры экономики и состояний;
* DodgeAction.execute → ставит "dodging" и тратит Action;
* DashAction.execute → удваивает movement (точнее: +speed_ft);
* DisengageAction.execute → ставит ctx.disengaged + "disengaged";
* интеграция: атака по dodging-цели → disadvantage (берётся меньший d20);
* интеграция: dash после move позволяет двигаться дольше.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dnd.application.dto.action import (
    ActionEconomyCost,
    Allowed,
    Forbidden,
    ForbiddenReason,
    NoParams,
)
from dnd.application.dto.engine_event import AttackRolled, DamageDealt, EngineEvent
from dnd.application.engine.actions.attack import (
    AttackAction,
    AttackKind,
    AttackParams,
)
from dnd.application.engine.actions.move import MoveAction, MoveParams
from dnd.application.engine.actions.stances import (
    CombatStance,
    DashAction,
    DisengageAction,
    DodgeAction,
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
from dnd.domain.values.ids import ConditionId, CreatureId
from dnd.domain.values.square import Square
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG


def _make_creature(creature_id: str = "actor", *, speed: int = 30) -> Creature:
    return Creature.create(
        id_=CreatureId(creature_id),
        name=creature_id,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=10, wis=10, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=speed,
    )


def _make_ctx(actor: Creature, *, movement_ft: int = 30) -> TurnContext:
    bf = Battlefield(10, 10)
    bf.place_creature(actor.id, Square(2, 2))
    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    registry = ConditionRegistry()
    register_default_conditions(registry)
    return TurnContext(
        actor_id=actor.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
        participants={actor.id: actor},
        movement_remaining_ft=movement_ft,
    )


# -- can_perform для всех трёх -----------------------------------------


@pytest.mark.parametrize(
    "action_cls", [DodgeAction, DashAction, DisengageAction]
)
def test_can_perform_allowed_fresh_turn(action_cls: type) -> None:
    actor = _make_creature()
    ctx = _make_ctx(actor)
    assert isinstance(action_cls().can_perform(actor, ctx), Allowed)


@pytest.mark.parametrize(
    "action_cls", [DodgeAction, DashAction, DisengageAction]
)
def test_can_perform_no_economy_left(action_cls: type) -> None:
    actor = _make_creature()
    ctx = _make_ctx(actor)
    ctx.spend(ActionEconomyCost.ACTION)
    av = action_cls().can_perform(actor, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_ECONOMY_LEFT


@pytest.mark.rules
@pytest.mark.parametrize(
    "action_cls", [DodgeAction, DashAction, DisengageAction]
)
@pytest.mark.parametrize(
    "condition_id", ["incapacitated", "stunned", "paralyzed", "unconscious"]
)
def test_can_perform_blocked_by_condition(
    action_cls: type, condition_id: str
) -> None:
    """PHB-2024 стр. 367: Incapacitated блокирует actions."""
    actor = _make_creature()
    ctx = _make_ctx(actor)
    actor.apply_condition(ConditionId(condition_id))
    av = action_cls().can_perform(actor, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.CONDITION_BLOCKS_ACTION


# -- DodgeAction.execute -------------------------------------------------


@pytest.mark.rules
def test_dodge_execute_sets_stance_and_spends_action() -> None:
    actor = _make_creature()
    ctx = _make_ctx(actor)
    outcome = DodgeAction().execute(actor, NoParams(), ctx)

    assert outcome.success is True
    assert outcome.consumed is ActionEconomyCost.ACTION
    assert ctx.action_used is True
    assert CombatStance.DODGING.value in actor.combat_stances


# -- DashAction.execute --------------------------------------------------


@pytest.mark.rules
def test_dash_execute_doubles_movement_budget() -> None:
    """PHB-2024 стр. 22: Dash даёт доп. движение, равное скорости.

    Стартовый ход: ctx.movement_remaining_ft = speed. После Dash —
    speed * 2.
    """
    actor = _make_creature(speed=30)
    ctx = _make_ctx(actor, movement_ft=30)
    DashAction().execute(actor, NoParams(), ctx)
    assert ctx.movement_remaining_ft == 60
    assert CombatStance.DASHING.value in actor.combat_stances


def test_dash_stacks_with_remaining_movement() -> None:
    """Если перед Dash что-то уже потратили — Dash добавляет к остатку."""
    actor = _make_creature(speed=30)
    ctx = _make_ctx(actor, movement_ft=30)
    ctx.spend_movement(10)
    DashAction().execute(actor, NoParams(), ctx)
    assert ctx.movement_remaining_ft == 20 + 30


# -- DisengageAction.execute --------------------------------------------


@pytest.mark.rules
def test_disengage_execute_sets_flag() -> None:
    actor = _make_creature()
    ctx = _make_ctx(actor)
    DisengageAction().execute(actor, NoParams(), ctx)
    assert ctx.disengaged is True
    assert CombatStance.DISENGAGED.value in actor.combat_stances


# -- интеграция: Dodge даёт disadvantage атакующему ---------------------


@pytest.mark.rules
def test_attack_on_dodging_target_gets_disadvantage() -> None:
    """PHB-2024 стр. 22: атаки по Dodging-цели — с помехой
    (берётся меньший d20). RNG: 18, 5 → меньший 5.

    attack_bonus=5, AC цели 14 без cover.
    5+5=10 vs 14 → промах.
    """
    attacker = _make_creature("fighter")
    target = _make_creature("target")
    target.combat_stances.add(CombatStance.DODGING.value)

    bf = Battlefield(10, 10)
    bf.place_creature(attacker.id, Square(1, 1))
    bf.place_creature(target.id, Square(2, 1))
    bus = InMemoryEventBus()
    rng = ScriptedRNG([18, 5])  # два d20 для disadvantage
    _reg = ConditionRegistry()
    register_default_conditions(_reg)
    ctx = TurnContext(
        actor_id=attacker.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(_reg),
        event_bus=bus,
        rng=rng,
        participants={attacker.id: attacker, target.id: target},
        movement_remaining_ft=attacker.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    params = AttackParams(
        target_id=target.id,
        kind=AttackKind.MELEE,
        attack_bonus=5,
        damage_expr="1d8+3",
        damage_type=DamageType.SLASHING,
        range_ft=5,
    )
    AttackAction().execute(attacker, params, ctx)

    atk = next(e for e in captured if isinstance(e, AttackRolled))
    # disadvantage: меньший из 18/5 = 5; 5+5=10 vs AC 14 → промах.
    assert atk.hit is False
    # Damage не должен публиковаться при промахе.
    assert not any(isinstance(e, DamageDealt) for e in captured)


# -- интеграция: Dash + Move работает -----------------------------------


@pytest.mark.rules
def test_dash_then_move_uses_extended_budget() -> None:
    """После Dash actor может пройти двойное расстояние одним движением."""
    actor = _make_creature(speed=30)
    # Поле 15×15 чтобы 8 шагов помещались.
    bf = Battlefield(15, 15)
    bf.place_creature(actor.id, Square(2, 2))
    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    ctx = TurnContext(
        actor_id=actor.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=MagicMock(),
        event_bus=bus,
        rng=rng,
        participants={actor.id: actor},
        movement_remaining_ft=30,
    )

    DashAction().execute(actor, NoParams(), ctx)
    assert ctx.movement_remaining_ft == 60

    # 8 шагов = 40 фт, помещается в 60.
    path = tuple(Square(2 + i, 2) for i in range(1, 9))
    av = MoveAction().can_perform_against(actor, MoveParams(path=path), ctx)
    assert isinstance(av, Allowed)

    MoveAction().execute(actor, MoveParams(path=path), ctx)
    assert ctx.movement_remaining_ft == 60 - 40


# -- интеграция: Disengage отменяет провокацию --------------------------


@pytest.mark.rules
def test_disengage_then_move_does_not_provoke() -> None:
    """Уже покрыто в test_move_action.test_disengage_suppresses_provocation;
    здесь — end-to-end через сам DisengageAction (не флаг вручную).
    """
    from dnd.application.dto.engine_event import OpportunityAttackProvoked

    actor = _make_creature("actor")
    threatener = _make_creature("orc")
    bf = Battlefield(10, 10)
    bf.place_creature(actor.id, Square(2, 2))
    bf.place_creature(threatener.id, Square(3, 2))
    bus = InMemoryEventBus()
    rng = ScriptedRNG([])
    ctx = TurnContext(
        actor_id=actor.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=MagicMock(),
        event_bus=bus,
        rng=rng,
        participants={actor.id: actor, threatener.id: threatener},
        movement_remaining_ft=actor.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    # Dis + Move.
    DisengageAction().execute(actor, NoParams(), ctx)
    # После Dis Action использован; Move не зависит от него.
    MoveAction().execute(actor, MoveParams(path=(Square(1, 2),)), ctx)

    aops = [e for e in captured if isinstance(e, OpportunityAttackProvoked)]
    assert aops == []


# -- ST-R001 (audit 10, S1): Dodge гасится Incapacitated/speed=0 ------


@pytest.mark.rules
@pytest.mark.parametrize(
    "blocker_condition",
    ["incapacitated", "stunned", "paralyzed", "unconscious"],
)
def test_dodge_suppressed_when_target_incapacitated(blocker_condition: str) -> None:
    """PHB-2024 стр. 22: «benefit ends if you are Incapacitated or your
    Speed drops to 0». Stunned/Paralyzed/Unconscious импличат Incapacitated
    и/или speed=0.

    Сценарий: цель в Dodge, потом получает блокирующее условие — атака
    идёт БЕЗ disadvantage. RNG: [5, 18] — без disadvantage берётся 5
    (одиночный d20); с disadvantage было бы [5, 18] → берётся меньший
    из двух = 5. Различить случаи в одном тесте трудно; используем
    одиночный RNG и проверяем, что disadvantage НЕ применился через
    общую длину RNG-очереди.

    Аудит 10 ST-R001.
    """
    attacker = _make_creature("fighter")
    target = _make_creature("target")
    target.combat_stances.add(CombatStance.DODGING.value)
    target.apply_condition(ConditionId(blocker_condition))

    bf = Battlefield(10, 10)
    bf.place_creature(attacker.id, Square(1, 1))
    bf.place_creature(target.id, Square(2, 1))
    bus = InMemoryEventBus()
    # T3: Dodge подавлен (нет disadvantage), но эти состояния cross-creature
    # дают атакующему ПРЕИМУЩЕСТВО (Stunned/Paralyzed/Unconscious; Incapacitated
    # сам по себе — нет). Paralyzed/Unconscious в упор → авто-крит (2 кости).
    advantage_conditions = {"stunned", "paralyzed", "unconscious"}
    crit_conditions = {"paralyzed", "unconscious"}
    d20s = [18, 18] if blocker_condition in advantage_conditions else [18]
    dmg = [5, 5] if blocker_condition in crit_conditions else [5]
    rng = ScriptedRNG(d20s + dmg)
    _reg = ConditionRegistry()
    register_default_conditions(_reg)
    ctx = TurnContext(
        actor_id=attacker.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(_reg),
        event_bus=bus,
        rng=rng,
        participants={attacker.id: attacker, target.id: target},
        movement_remaining_ft=attacker.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    params = AttackParams(
        target_id=target.id,
        kind=AttackKind.MELEE,
        attack_bonus=5,
        damage_expr="1d8+3",
        damage_type=DamageType.SLASHING,
        range_ft=5,
    )
    AttackAction().execute(attacker, params, ctx)

    atk = next(e for e in captured if isinstance(e, AttackRolled))
    # Главное: Dodge подавлен — атака НЕ получает disadvantage (ST-R001).
    assert atk.disadvantage is False, (
        "Dodge должен быть подавлен; атака не должна получать disadvantage"
    )
    assert atk.hit is True
