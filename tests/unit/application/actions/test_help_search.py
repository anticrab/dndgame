"""Тесты Help / Search (этап E5).

PHB-2024 стр. 22.

Покрытие:

* HelpAction: ставит ally.helped_against; AttackAction даёт advantage
  на следующую атаку ally по target и one-shot сбрасывает;
* Help.can_perform_against: 5 ft до цели; NO_VALID_TARGETS;
* SearchAction: ABILITY_CHECK через DiceRoller, публикует SearchPerformed;
* блокеры состояний.
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
from dnd.application.dto.engine_event import (
    AttackRolled,
    EngineEvent,
    HelpGranted,
    RollIssued,
    SearchPerformed,
)
from dnd.application.engine.actions.attack import (
    AttackAction,
    AttackKind,
    AttackParams,
)
from dnd.application.engine.actions.help_search import (
    HelpAction,
    HelpParams,
    SearchAction,
    SearchKind,
    SearchParams,
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


def _make_creature(cid: str = "actor") -> Creature:
    return Creature.create(
        id_=CreatureId(cid),
        name=cid,
        abilities=AbilityScores.of(str_=12, dex=12, con=12, int_=12, wis=14, cha=10),
        max_hp=20,
        armor_class=14,
        speed_ft=30,
    )


def _setup_three(
    helper_pos: Square,
    ally_pos: Square,
    target_pos: Square,
    *,
    rng_rolls: list[int] | None = None,
) -> tuple[Creature, Creature, Creature, TurnContext, InMemoryEventBus]:
    helper = _make_creature("helper")
    ally = _make_creature("ally")
    target = _make_creature("target")
    bf = Battlefield(10, 10)
    bf.place_creature(helper.id, helper_pos)
    bf.place_creature(ally.id, ally_pos)
    bf.place_creature(target.id, target_pos)
    bus = InMemoryEventBus()
    rng = ScriptedRNG(rng_rolls or [])
    registry = ConditionRegistry()
    register_default_conditions(registry)
    ctx = TurnContext(
        actor_id=helper.id,
        battlefield=bf,
        dice_roller=ComputerDiceRoller(rng=rng, event_bus=bus),
        modifier_applier=ModifierApplier(ModifierBag()),
        condition_service=ConditionService(registry),
        event_bus=bus,
        rng=rng,
        participants={helper.id: helper, ally.id: ally, target.id: target},
        movement_remaining_ft=30,
    )
    return helper, ally, target, ctx, bus


# -- Help.can_perform ---------------------------------------------------


def test_help_can_perform_allowed() -> None:
    helper, _ally, _target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    av = HelpAction().can_perform(helper, ctx)
    assert isinstance(av, Allowed)


def test_help_can_perform_no_economy() -> None:
    helper, _, _, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    ctx.spend(ActionEconomyCost.ACTION)
    av = HelpAction().can_perform(helper, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_ECONOMY_LEFT


@pytest.mark.rules
def test_help_against_no_valid_ally() -> None:
    helper, _ally, target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    av = HelpAction().can_perform_against(
        helper,
        HelpParams(
            ally_id=CreatureId("ghost"),
            target_id=target.id,
        ),
        ctx,
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_VALID_TARGETS


@pytest.mark.rules
def test_help_against_self_is_forbidden() -> None:
    helper, _ally, target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    av = HelpAction().can_perform_against(
        helper, HelpParams(ally_id=helper.id, target_id=target.id), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.NO_VALID_TARGETS


@pytest.mark.rules
def test_help_requires_within_5ft_of_target() -> None:
    """PHB-2024 стр. 22: helper в 5 фт от ЦЕЛИ. Здесь helper в (1,1),
    target в (5,1) → 20 фт → запрет."""
    helper, ally, target, ctx, _ = _setup_three(Square(1, 1), Square(4, 1), Square(5, 1))
    av = HelpAction().can_perform_against(
        helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx
    )
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.OUT_OF_RANGE


# -- Help.execute -------------------------------------------------------


@pytest.mark.rules
def test_help_execute_sets_helped_against_and_publishes() -> None:
    helper, ally, target, ctx, bus = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    outcome = HelpAction().execute(helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx)

    assert outcome.success is True
    assert outcome.consumed is ActionEconomyCost.ACTION
    assert outcome.events_published == ("help.granted",)
    assert ally.helped_against == target.id
    evt = next(e for e in captured if isinstance(e, HelpGranted))
    assert evt.helper_id == helper.id
    assert evt.ally_id == ally.id
    assert evt.target_id == target.id


# -- Help + Attack интеграция ------------------------------------------


@pytest.mark.rules
def test_helped_ally_gets_advantage_on_attack_target_one_shot() -> None:
    """После Help.execute: следующая атака ally по target идёт с
    advantage; поле сбрасывается one-shot."""
    helper, ally, target, ctx, bus = _setup_three(
        Square(1, 1),
        Square(2, 1),
        Square(2, 2),
        rng_rolls=[5, 18, 4],  # advantage берёт 18; damage 4
    )
    HelpAction().execute(helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx)
    assert ally.helped_against == target.id

    # Ally атакует target — должен получить advantage и попасть.
    # Подменяем actor_id и используем тот же ctx (упрощённо).
    ctx_for_ally = TurnContext(
        actor_id=ally.id,
        battlefield=ctx.battlefield,
        dice_roller=ctx.dice_roller,
        modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service,
        event_bus=ctx.event_bus,
        rng=ctx.rng,
        participants=ctx.participants,
        movement_remaining_ft=ally.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    AttackAction().execute(
        ally,
        AttackParams(
            target_id=target.id,
            kind=AttackKind.MELEE,
            attack_bonus=5,
            damage_expr="1d8+3",
            damage_type=DamageType.SLASHING,
            range_ft=5,
        ),
        ctx_for_ally,
    )

    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.hit is True  # advantage берёт 18 — попадание
    # One-shot: после атаки поле обнулилось.
    assert ally.helped_against is None


@pytest.mark.rules
def test_helped_ally_no_advantage_on_different_target() -> None:
    """Help — для конкретного target_id, не для других."""
    helper, ally, target, ctx, bus = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    other = _make_creature("other")
    ctx.battlefield.place_creature(other.id, Square(3, 1))
    ctx.participants[other.id] = other

    HelpAction().execute(helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx)
    # ScriptedRNG только один d20 — значит advantage НЕ применился
    # (если бы применился, нужно было бы 2 значения и тест упал бы
    # IndexError).
    ctx_for_ally = TurnContext(
        actor_id=ally.id,
        battlefield=ctx.battlefield,
        dice_roller=ComputerDiceRoller(rng=ScriptedRNG([10, 4]), event_bus=bus),
        modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service,
        event_bus=bus,
        rng=ctx.rng,
        participants=ctx.participants,
        movement_remaining_ft=ally.speed_ft,
    )

    AttackAction().execute(
        ally,
        AttackParams(
            target_id=other.id,  # другая цель!
            kind=AttackKind.MELEE,
            attack_bonus=5,
            damage_expr="1d8+3",
            damage_type=DamageType.SLASHING,
            range_ft=5,
        ),
        ctx_for_ally,
    )
    # ally.helped_against всё ещё на target (не использован)
    assert ally.helped_against == target.id


# -- Search -------------------------------------------------------------


def test_search_can_perform_allowed() -> None:
    actor, _ally, _target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    assert isinstance(SearchAction().can_perform(actor, ctx), Allowed)


@pytest.mark.rules
@pytest.mark.parametrize("condition_id", ["incapacitated", "stunned", "paralyzed", "unconscious"])
def test_search_blocked_by_condition(condition_id: str) -> None:
    actor, _ally, _target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    actor.apply_condition(ConditionId(condition_id))
    av = SearchAction().can_perform(actor, ctx)
    assert isinstance(av, Forbidden)
    assert av.reason is ForbiddenReason.CONDITION_BLOCKS_ACTION


@pytest.mark.rules
def test_search_execute_publishes_event_and_rolls() -> None:
    actor, _ally, _target, ctx, bus = _setup_three(
        Square(1, 1),
        Square(2, 1),
        Square(2, 2),
        rng_rolls=[14],
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    outcome = SearchAction().execute(
        actor, SearchParams(kind=SearchKind.PERCEPTION, skill_mod=3), ctx
    )

    assert outcome.success is True
    assert outcome.events_published == ("search.performed",)
    # Roll: 14 + 3 = 17
    search = next(e for e in captured if isinstance(e, SearchPerformed))
    assert search.total == 17
    assert search.skill_kind == "perception"
    # Также сам бросок опубликован через DiceRoller
    roll = next(e for e in captured if isinstance(e, RollIssued))
    assert roll.result.total == 17


def test_search_rejects_wrong_params() -> None:
    actor, _ally, _target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    with pytest.raises(TypeError, match="SearchParams"):
        SearchAction().execute(actor, NoParams(), ctx)


def test_search_survival_kind() -> None:
    # Аудит 16 HS-R-NEW-002: PHB-2024 стр. 357 называет Insight /
    # Medicine / Perception / Survival (все Wisdom). Investigation
    # (Int) в книге для Search не упомянут.
    actor, _ally, _target, ctx, bus = _setup_three(
        Square(1, 1),
        Square(2, 1),
        Square(2, 2),
        rng_rolls=[10],
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)
    SearchAction().execute(
        actor,
        SearchParams(kind=SearchKind.SURVIVAL, skill_mod=2),
        ctx,
    )
    search = next(e for e in captured if isinstance(e, SearchPerformed))
    assert search.skill_kind == "survival"


def test_help_rejects_wrong_params() -> None:
    helper, _ally, _target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    with pytest.raises(TypeError, match="HelpParams"):
        HelpAction().execute(helper, NoParams(), ctx)


def test_help_execute_contract_violation() -> None:
    """Если ally нет в participants — RuntimeError."""
    helper, _ally, target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    bad = HelpParams(ally_id=CreatureId("ghost"), target_id=target.id)
    with pytest.raises(RuntimeError, match="contract violation"):
        HelpAction().execute(helper, bad, ctx)


def test_help_mock_condition_service_unused() -> None:
    """Helper.condition_service не должен дёргаться в Help — мок проверяет."""
    helper, ally, target, ctx, _ = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    mock_service = MagicMock()
    ctx.condition_service = mock_service
    HelpAction().execute(helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx)
    mock_service.assert_not_called()


# -- HS-R001 (audit 11, S0): helper должен быть в 5ft в момент атаки ---


@pytest.mark.rules
def test_help_advantage_lost_when_helper_moves_away_before_attack() -> None:
    """PHB-2024 стр. 22: «if the target is no longer within 5 feet of you
    when the attack is made, you lose the benefit».

    Сценарий: helper делает Help, потом отходит. Когда ally атакует —
    advantage НЕ применяется (helper > 5ft от target). Поле сбрасывается.

    Аудит 11 HS-R001.
    """
    helper, ally, target, ctx, bus = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    HelpAction().execute(helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx)
    assert ally.helped_against == target.id
    assert ally.helped_by == helper.id

    # Helper отошёл далеко — теперь > 5ft от target (2,2).
    ctx.battlefield.move_creature(helper.id, Square(8, 8))

    # ally атакует target. Если бы advantage применился — RNG нужно бы
    # ДВА d20; даём один + damage. Если применился — IndexError.
    ctx_for_ally = TurnContext(
        actor_id=ally.id,
        battlefield=ctx.battlefield,
        dice_roller=ComputerDiceRoller(rng=ScriptedRNG([14, 4]), event_bus=bus),
        modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service,
        event_bus=bus,
        rng=ctx.rng,
        participants=ctx.participants,
        movement_remaining_ft=ally.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    AttackAction().execute(
        ally,
        AttackParams(
            target_id=target.id,
            kind=AttackKind.MELEE,
            attack_bonus=5,
            damage_expr="1d8+3",
            damage_type=DamageType.SLASHING,
            range_ft=5,
        ),
        ctx_for_ally,
    )

    atk = next(e for e in captured if isinstance(e, AttackRolled))
    # 14+5=19 vs AC 14 → попал; но advantage не применялся (только 1 d20
    # бросился — иначе RNG бы исчерпался на d20 и не хватило damage).
    assert atk.hit is True
    # Поле сброшено (one-shot бонус «теряется»).
    assert ally.helped_against is None
    assert ally.helped_by is None


@pytest.mark.rules
def test_help_advantage_applied_when_helper_still_within_5ft() -> None:
    """Sanity: если helper не отошёл, advantage срабатывает (как раньше)."""
    helper, ally, target, ctx, bus = _setup_three(
        Square(1, 1),
        Square(2, 1),
        Square(2, 2),
        rng_rolls=[5, 18, 4],  # advantage берёт 18
    )
    HelpAction().execute(helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx)
    # Helper НЕ двигался — остался в (1,1), target в (2,2). distance =
    # max(|1-2|, |1-2|) = 1 клетка = 5 фут. OK.

    ctx_for_ally = TurnContext(
        actor_id=ally.id,
        battlefield=ctx.battlefield,
        dice_roller=ctx.dice_roller,
        modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service,
        event_bus=ctx.event_bus,
        rng=ctx.rng,
        participants=ctx.participants,
        movement_remaining_ft=ally.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    AttackAction().execute(
        ally,
        AttackParams(
            target_id=target.id,
            kind=AttackKind.MELEE,
            attack_bonus=5,
            damage_expr="1d8+3",
            damage_type=DamageType.SLASHING,
            range_ft=5,
        ),
        ctx_for_ally,
    )
    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.hit is True  # advantage 18 → попал
    assert ally.helped_against is None
    assert ally.helped_by is None


@pytest.mark.rules
def test_help_advantage_lost_when_helper_removed_from_battlefield() -> None:
    """Если helper'а вообще больше нет на поле (сценарий: погиб и
    removed) — advantage не действует."""
    helper, ally, target, ctx, bus = _setup_three(Square(1, 1), Square(2, 1), Square(2, 2))
    HelpAction().execute(helper, HelpParams(ally_id=ally.id, target_id=target.id), ctx)
    ctx.battlefield.remove_creature(helper.id)

    ctx_for_ally = TurnContext(
        actor_id=ally.id,
        battlefield=ctx.battlefield,
        dice_roller=ComputerDiceRoller(rng=ScriptedRNG([14, 4]), event_bus=bus),
        modifier_applier=ctx.modifier_applier,
        condition_service=ctx.condition_service,
        event_bus=bus,
        rng=ctx.rng,
        participants=ctx.participants,
        movement_remaining_ft=ally.speed_ft,
    )
    captured: list[EngineEvent] = []
    bus.subscribe(EngineEvent, captured.append)

    AttackAction().execute(
        ally,
        AttackParams(
            target_id=target.id,
            kind=AttackKind.MELEE,
            attack_bonus=5,
            damage_expr="1d8+3",
            damage_type=DamageType.SLASHING,
            range_ft=5,
        ),
        ctx_for_ally,
    )
    # 14+5=19 — попал без advantage.
    atk = next(e for e in captured if isinstance(e, AttackRolled))
    assert atk.hit is True
    # Поле всё равно очищается.
    assert ally.helped_against is None
