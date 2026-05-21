"""Тесты ``ComputerDiceRoller`` — двухфазная модель, контракт ENGINE.md §7.

Каждый пункт контракта (events FIFO, roll_id, advantage/disadvantage,
crit, extra_dice, tags, прямая привязка к ``DiceExpr``) — отдельный
тест-доказательство.
"""

from __future__ import annotations

import pytest

from dnd.application.dto.engine_event import RollApplied, RollIssued
from dnd.application.dto.ids import CreatureId
from dnd.application.dto.rolls import EngineRollResult, RollContext, RollPurpose
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.ports.event_bus import EventBus
from dnd.domain.values.dice import DiceExpr
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG

# -- фикстуры --------------------------------------------------------------


@pytest.fixture
def bus() -> EventBus:
    return InMemoryEventBus()


def make_roller(rolls: list[int], bus: EventBus) -> ComputerDiceRoller:
    return ComputerDiceRoller(rng=ScriptedRNG(rolls), event_bus=bus)


# -- базовый бросок --------------------------------------------------------


def test_basic_d20_attack_roll(bus: EventBus) -> None:
    roller = make_roller([15], bus)
    ctx = RollContext(purpose=RollPurpose.ATTACK)
    result = roller.roll(DiceExpr.parse("1d20+5"), ctx)

    assert result.raw == (15,)
    assert result.kept == (15,)
    assert result.modifier == 5
    assert result.total == 20
    assert result.advantage is False
    assert result.disadvantage is False
    assert result.crit is False
    assert result.context is ctx


def test_result_carries_actor_and_target(bus: EventBus) -> None:
    roller = make_roller([10], bus)
    ctx = RollContext(
        purpose=RollPurpose.ATTACK,
        actor_id=CreatureId("aelar"),
        target_id=CreatureId("goblin-1"),
    )
    result = roller.roll(DiceExpr.parse("d20"), ctx)
    assert result.context.actor_id == "aelar"
    assert result.context.target_id == "goblin-1"


# -- двухфазная модель: события ------------------------------------------


def test_publishes_issued_then_applied_in_order(bus: EventBus) -> None:
    """Книга-контракт ENGINE.md §7.4: сначала RollIssued, затем RollApplied
    с одинаковым roll_id."""
    timeline: list[str] = []
    issued_events: list[RollIssued] = []
    applied_events: list[RollApplied] = []

    bus.subscribe(RollIssued, lambda e: (timeline.append("issued"), issued_events.append(e)))
    bus.subscribe(RollApplied, lambda e: (timeline.append("applied"), applied_events.append(e)))

    roller = make_roller([12], bus)
    roller.roll(DiceExpr.parse("1d20"), RollContext(purpose=RollPurpose.SAVE))

    assert timeline == ["issued", "applied"]
    assert len(issued_events) == 1
    assert len(applied_events) == 1
    assert issued_events[0].result.roll_id == applied_events[0].result.roll_id


def test_each_roll_has_unique_roll_id(bus: EventBus) -> None:
    roller = make_roller([10, 11, 12], bus)
    ctx = RollContext(purpose=RollPurpose.ABILITY_CHECK)
    r1 = roller.roll(DiceExpr.parse("d20"), ctx)
    r2 = roller.roll(DiceExpr.parse("d20"), ctx)
    r3 = roller.roll(DiceExpr.parse("d20"), ctx)
    assert len({r1.roll_id, r2.roll_id, r3.roll_id}) == 3


def test_returned_result_equals_published_one(bus: EventBus) -> None:
    """То, что возвращает roll(), идентично тому, что лежит в RollApplied."""
    applied: list[EngineRollResult] = []
    bus.subscribe(RollApplied, lambda e: applied.append(e.result))

    roller = make_roller([8], bus)
    result = roller.roll(DiceExpr.parse("d20+2"), RollContext(purpose=RollPurpose.ATTACK))
    assert applied[0] == result


# -- advantage / disadvantage / crit -------------------------------------


@pytest.mark.rules
def test_advantage_picks_higher_of_two_d20(bus: EventBus) -> None:
    roller = make_roller([7, 19], bus)
    result = roller.roll(
        DiceExpr.parse("d20+5"),
        RollContext(purpose=RollPurpose.ATTACK, advantage=True),
    )
    assert result.raw == (7, 19)
    assert result.kept == (19,)
    assert result.total == 24
    assert result.advantage is True


@pytest.mark.rules
def test_disadvantage_picks_lower(bus: EventBus) -> None:
    roller = make_roller([7, 19], bus)
    result = roller.roll(
        DiceExpr.parse("d20"),
        RollContext(purpose=RollPurpose.SAVE, disadvantage=True),
    )
    assert result.kept == (7,)
    assert result.disadvantage is True


@pytest.mark.rules
def test_advantage_and_disadvantage_cancel(bus: EventBus) -> None:
    """Книга стр. 11: «Если обстоятельства одновременно дают и преимущество,
    и помеху, то бросок не имеет ни того, ни другого»."""
    roller = make_roller([12], bus)
    result = roller.roll(
        DiceExpr.parse("d20"),
        RollContext(purpose=RollPurpose.ATTACK, advantage=True, disadvantage=True),
    )
    assert result.kept == (12,)
    assert result.advantage is False
    assert result.disadvantage is False


@pytest.mark.rules
def test_crit_doubles_damage_dice(bus: EventBus) -> None:
    """Книга стр. 12: «кости урона удваиваются»."""
    roller = make_roller([6, 8], bus)
    result = roller.roll(
        DiceExpr.parse("1d8+3"),
        RollContext(purpose=RollPurpose.DAMAGE, crit=True),
    )
    assert result.raw == (6, 8)
    assert result.total == 6 + 8 + 3  # модификатор не удваивается
    assert result.crit is True


def test_advantage_on_non_d20_raises(bus: EventBus) -> None:
    """Контракт DiceExpr — advantage/disadvantage только для одиночного d20."""
    roller = make_roller([1, 2], bus)
    with pytest.raises(ValueError, match="single d20"):
        roller.roll(
            DiceExpr.parse("2d6"),
            RollContext(purpose=RollPurpose.DAMAGE, advantage=True),
        )


# -- extra_dice (ModifierApplier prep) -----------------------------------


def test_extra_dice_are_added_to_total(bus: EventBus) -> None:
    """Bless даёт +1d4 к атаке. ModifierApplier добавит это в context.extra_dice."""
    # 15 — основной d20, 3 — d4 от Bless
    roller = make_roller([15, 3], bus)
    ctx = RollContext(
        purpose=RollPurpose.ATTACK,
        extra_dice=("1d4",),
    )
    result = roller.roll(DiceExpr.parse("1d20+5"), ctx)
    assert result.kept == (15,)
    assert result.extra_dice_rolls == (3,)
    assert result.total == 15 + 5 + 3


def test_multiple_extra_dice(bus: EventBus) -> None:
    """Sneak Attack 2d6 + Bless 1d4 — две отдельные группы доп. костей."""
    # основной 1d8: 5; 2d6: 4,6; 1d4: 2
    roller = make_roller([5, 4, 6, 2], bus)
    ctx = RollContext(
        purpose=RollPurpose.DAMAGE,
        extra_dice=("2d6", "1d4"),
    )
    result = roller.roll(DiceExpr.parse("1d8+3"), ctx)
    assert result.kept == (5,)
    assert result.extra_dice_rolls == (4, 6, 2)
    assert result.total == 5 + 3 + 4 + 6 + 2


def test_no_extra_dice_by_default(bus: EventBus) -> None:
    roller = make_roller([10], bus)
    result = roller.roll(DiceExpr.parse("d20"), RollContext(purpose=RollPurpose.ATTACK))
    assert result.extra_dice_rolls == ()


# -- tags -----------------------------------------------------------------


def test_tags_propagate_to_events(bus: EventBus) -> None:
    """tags из context копируются на оба события — нужно для аудита
    master_intervention и фильтрации в логе."""
    captured_issued: list[RollIssued] = []
    captured_applied: list[RollApplied] = []
    bus.subscribe(RollIssued, captured_issued.append)
    bus.subscribe(RollApplied, captured_applied.append)

    roller = make_roller([10], bus)
    ctx = RollContext(purpose=RollPurpose.ATTACK, tags=("master_intervention", "reroll"))
    roller.roll(DiceExpr.parse("d20"), ctx)

    assert captured_issued[0].tags == ("master_intervention", "reroll")
    assert captured_applied[0].tags == ("master_intervention", "reroll")


# -- d20_raw для статистики ----------------------------------------------


def test_d20_raw_for_single_d20(bus: EventBus) -> None:
    """DiceStatisticsService опирается на result.d20_raw для расчёта удачи."""
    roller = make_roller([14], bus)
    result = roller.roll(DiceExpr.parse("1d20+5"), RollContext(purpose=RollPurpose.ATTACK))
    assert result.d20_raw == 14


def test_d20_raw_none_for_damage_roll(bus: EventBus) -> None:
    roller = make_roller([3, 5], bus)
    result = roller.roll(DiceExpr.parse("2d6"), RollContext(purpose=RollPurpose.DAMAGE))
    assert result.d20_raw is None


def test_d20_raw_for_d20_with_advantage(bus: EventBus) -> None:
    """Сырое значение — то, которое попало в kept (после max/min)."""
    roller = make_roller([7, 18], bus)
    result = roller.roll(
        DiceExpr.parse("d20"), RollContext(purpose=RollPurpose.ATTACK, advantage=True)
    )
    assert result.d20_raw == 18


@pytest.mark.rules
def test_is_natural_20_and_1(bus: EventBus) -> None:
    """Натуральная 20 для криков; натуральная 1 для автопромаха
    (книга стр. 11)."""
    roller = make_roller([20, 1], bus)
    crit = roller.roll(DiceExpr.parse("d20+5"), RollContext(purpose=RollPurpose.ATTACK))
    fumble = roller.roll(DiceExpr.parse("d20+5"), RollContext(purpose=RollPurpose.ATTACK))
    assert crit.is_natural_20() is True
    assert crit.is_natural_1() is False
    assert fumble.is_natural_20() is False
    assert fumble.is_natural_1() is True


# -- purpose проброс -----------------------------------------------------


@pytest.mark.parametrize(
    "purpose",
    [
        RollPurpose.ATTACK,
        RollPurpose.DAMAGE,
        RollPurpose.SAVE,
        RollPurpose.ABILITY_CHECK,
        RollPurpose.INITIATIVE,
        RollPurpose.HIT_DICE,
        RollPurpose.DEATH_SAVE,
        RollPurpose.STATS_GEN,
        RollPurpose.LOOT,
        RollPurpose.OTHER,
    ],
)
def test_purpose_kinds_supported(bus: EventBus, purpose: RollPurpose) -> None:
    roller = make_roller([10], bus)
    result = roller.roll(DiceExpr.parse("d20"), RollContext(purpose=purpose))
    assert result.context.purpose is purpose


# -- иммутабельность и валидация DTO -------------------------------------


def test_engine_roll_result_is_frozen(bus: EventBus) -> None:
    roller = make_roller([10], bus)
    result = roller.roll(DiceExpr.parse("d20"), RollContext(purpose=RollPurpose.ATTACK))
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        result.total = 99  # type: ignore[misc]


def test_roll_context_rejects_extra_fields() -> None:
    """`extra='forbid'` защищает от опечаток (typo в имени поля)."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Extra inputs"):
        RollContext.model_validate({"purpose": "attack", "advantage": True, "typo_field": "what"})
