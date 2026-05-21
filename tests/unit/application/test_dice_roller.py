"""Тесты ``ComputerDiceRoller`` — контракт ENGINE.md §7.

Уровень тестирования — **надстройка** над ``DiceExpr.roll``: двухфазная
модель (RollIssued → RollApplied), ``roll_id``, ``extra_dice``,
проброс флагов из ``RollContext`` в ``DiceExpr.roll`` и обратно в
``EngineRollResult``, теги, изоляция между бросками.

Сама механика костей (advantage = max(2k20), crit удваивает кости и
не модификатор, нат-20/1, advantage только для одиночного d20)
проверяется в ``tests/unit/domain/test_dice.py`` — здесь от неё
проверяем только проброс «флаги в expr и обратно в result».

DTO-валидация (``frozen``, ``extra="forbid"``) — в
``tests/unit/application/test_rolls.py``.
"""

from __future__ import annotations

import logging

import pytest

from dnd.application.dto.engine_event import RollApplied, RollIssued
from dnd.application.dto.ids import CreatureId
from dnd.application.dto.rolls import EngineRollResult, RollContext, RollPurpose
from dnd.application.engine.dice_roller import ComputerDiceRoller
from dnd.application.ports.event_bus import EventBus
from dnd.domain.values.dice import DiceExpr, DiceParseError
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus
from dnd.infrastructure.rng.scripted_rng import ScriptedRNG

# -- фикстуры --------------------------------------------------------------


@pytest.fixture
def bus() -> EventBus:
    return InMemoryEventBus()


def make_roller(rolls: list[int], bus: EventBus) -> ComputerDiceRoller:
    return ComputerDiceRoller(rng=ScriptedRNG(rolls), event_bus=bus)


# -- 1. Базовый бросок: пробрасывание данных --------------------------


def test_basic_d20_attack_roll(bus: EventBus) -> None:
    """Простой 1d20+5: основные поля EngineRollResult заполняются из
    DiceExpr.roll, context копируется без изменений."""
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
    """actor/target из context живут в result.context — это нужно
    DiceStatistics и аудит-логу."""
    roller = make_roller([10], bus)
    ctx = RollContext(
        purpose=RollPurpose.ATTACK,
        actor_id=CreatureId("aelar"),
        target_id=CreatureId("goblin-1"),
    )
    result = roller.roll(DiceExpr.parse("d20"), ctx)
    assert result.context.actor_id == "aelar"
    assert result.context.target_id == "goblin-1"


# -- 2. Двухфазная модель: события ------------------------------------


def test_publishes_issued_then_applied_in_order(bus: EventBus) -> None:
    """Контракт ENGINE.md §7.4: сначала RollIssued, затем RollApplied
    с одинаковым roll_id. Это сердце контракта DiceRoller."""
    timeline: list[str] = []
    issued: list[RollIssued] = []
    applied: list[RollApplied] = []

    def on_issued(e: RollIssued) -> None:
        timeline.append("issued")
        issued.append(e)

    def on_applied(e: RollApplied) -> None:
        timeline.append("applied")
        applied.append(e)

    bus.subscribe(RollIssued, on_issued)
    bus.subscribe(RollApplied, on_applied)

    roller = make_roller([12], bus)
    roller.roll(DiceExpr.parse("1d20"), RollContext(purpose=RollPurpose.SAVE))

    assert timeline == ["issued", "applied"]
    assert issued[0].result.roll_id == applied[0].result.roll_id


def test_each_roll_has_unique_roll_id(bus: EventBus) -> None:
    """Мастеру нужны разные roll_id для адресации (MASTER.md §3)."""
    roller = make_roller([10, 11, 12], bus)
    ctx = RollContext(purpose=RollPurpose.ABILITY_CHECK)
    r1 = roller.roll(DiceExpr.parse("d20"), ctx)
    r2 = roller.roll(DiceExpr.parse("d20"), ctx)
    r3 = roller.roll(DiceExpr.parse("d20"), ctx)
    assert len({r1.roll_id, r2.roll_id, r3.roll_id}) == 3


def test_returned_result_equals_published_one(bus: EventBus) -> None:
    """Инвариант: то, что возвращает roll(), идентично тому, что
    лежит в RollApplied. Легко сломать рефактором — поэтому тест."""
    applied: list[EngineRollResult] = []
    bus.subscribe(RollApplied, lambda e: applied.append(e.result))

    roller = make_roller([8], bus)
    result = roller.roll(DiceExpr.parse("d20+2"), RollContext(purpose=RollPurpose.ATTACK))
    assert applied[0] == result


def test_consecutive_rolls_are_independent(bus: EventBus) -> None:
    """TR-G003: два бросков подряд на одном roller'е — отдельные события
    и независимые результаты, состояние между ними не утекает."""
    issued: list[RollIssued] = []
    applied: list[RollApplied] = []
    bus.subscribe(RollIssued, issued.append)
    bus.subscribe(RollApplied, applied.append)

    roller = make_roller([5, 17], bus)
    ctx = RollContext(purpose=RollPurpose.ATTACK)
    r1 = roller.roll(DiceExpr.parse("d20"), ctx)
    r2 = roller.roll(DiceExpr.parse("d20"), ctx)

    assert r1.kept == (5,)
    assert r2.kept == (17,)
    assert r1.roll_id != r2.roll_id
    # 4 события: пара на каждый roll, попарно одинаковые roll_id
    assert len(issued) == 2
    assert len(applied) == 2
    assert issued[0].result.roll_id == applied[0].result.roll_id
    assert issued[1].result.roll_id == applied[1].result.roll_id


# -- 3. Проброс флагов из RollContext в DiceExpr.roll -----------------
#
# Сама механика advantage/disadvantage/crit покрыта в test_dice.py.
# Здесь — только что DiceRoller правильно прокидывает флаги туда и
# обратно.


def test_advantage_flag_passes_through(bus: EventBus) -> None:
    """ctx.advantage=True → DiceExpr.roll получает advantage=True,
    в результате advantage=True и брошены 2 кости."""
    roller = make_roller([7, 19], bus)
    result = roller.roll(
        DiceExpr.parse("d20+5"),
        RollContext(purpose=RollPurpose.ATTACK, advantage=True),
    )
    assert result.advantage is True
    assert len(result.raw) == 2  # двойной бросок d20


def test_disadvantage_flag_passes_through(bus: EventBus) -> None:
    roller = make_roller([7, 19], bus)
    result = roller.roll(
        DiceExpr.parse("d20"),
        RollContext(purpose=RollPurpose.SAVE, disadvantage=True),
    )
    assert result.disadvantage is True
    assert len(result.raw) == 2


def test_crit_flag_passes_through_to_main_expr(bus: EventBus) -> None:
    """ctx.crit=True → DiceExpr.roll(crit=True) → удваивает кости
    основного выражения. Книга стр. 12."""
    roller = make_roller([6, 8], bus)
    result = roller.roll(
        DiceExpr.parse("1d8+3"),
        RollContext(purpose=RollPurpose.DAMAGE, crit=True),
    )
    assert result.crit is True
    assert len(result.raw) == 2  # 1d8 → 2 кости при крите
    assert result.modifier == 3  # сам модификатор не удваивается — забота DiceExpr


def test_advantage_on_non_d20_raises_and_does_not_publish_events(bus: EventBus) -> None:
    """TR-G004 + контракт DiceExpr: advantage только на одиночном d20.

    Дополнительно проверяем, что **не публикуется RollIssued/RollApplied**
    при ошибке валидации — иначе остался бы «висящий» RollIssued без
    RollApplied, что ломает учёт для DiceStatisticsService."""
    issued: list[RollIssued] = []
    applied: list[RollApplied] = []
    bus.subscribe(RollIssued, issued.append)
    bus.subscribe(RollApplied, applied.append)

    roller = make_roller([1, 2], bus)
    with pytest.raises(ValueError, match="single d20"):
        roller.roll(
            DiceExpr.parse("2d6"),
            RollContext(purpose=RollPurpose.DAMAGE, advantage=True),
        )
    assert issued == []
    assert applied == []


# -- 4. extra_dice (DiceBonusEffect из MODIFIERS.md §2.2) -------------


@pytest.mark.rules
def test_extra_dice_added_to_total(bus: EventBus) -> None:
    """MODIFIERS.md §2.2 DiceBonusEffect: дополнительные кости от
    модификатора (например, +1d4 от заклинания Bless к броску атаки)
    добавляются в total."""
    # 15 — основной d20, 3 — d4 от Bless. Конкатенация подчёркивает
    # деление «основной бросок vs extra_dice».
    roller = make_roller([15] + [3], bus)  # noqa: RUF005
    ctx = RollContext(purpose=RollPurpose.ATTACK, extra_dice=("1d4",))
    result = roller.roll(DiceExpr.parse("1d20+5"), ctx)

    assert result.kept == (15,)
    assert result.extra_dice_rolls == (3,)
    assert result.total == 15 + 5 + 3


@pytest.mark.rules
def test_multiple_extra_dice_groups_summed(bus: EventBus) -> None:
    """Несколько независимых DiceBonus от разных источников суммируются.

    Реалистичный сценарий: бросок урона оружием + Divine Smite (Паладин)
    с дополнительными костями. По правилам Sneak Attack — отдельный
    кубик к урону этого же удара (Книга 2024).
    """
    # Основное оружие 1d8: 5; Divine Smite 2d8: 4,6; Hunter's Mark 1d6: 2.
    roller = make_roller([5] + [4, 6] + [2], bus)  # noqa: RUF005
    ctx = RollContext(
        purpose=RollPurpose.DAMAGE,
        extra_dice=("2d8", "1d6"),
    )
    result = roller.roll(DiceExpr.parse("1d8+3"), ctx)

    assert result.kept == (5,)
    assert result.extra_dice_rolls == (4, 6, 2)
    assert result.total == 5 + 3 + 4 + 6 + 2


def test_no_extra_dice_by_default(bus: EventBus) -> None:
    roller = make_roller([10], bus)
    result = roller.roll(DiceExpr.parse("d20"), RollContext(purpose=RollPurpose.ATTACK))
    assert result.extra_dice_rolls == ()


@pytest.mark.rules
def test_crit_doubles_extra_damage_dice(bus: EventBus) -> None:
    """TR-G001: книга стр. 12 «все кости урона удваиваются» — включая
    extra_dice (Sneak Attack 2d6 → 4d6 при крите).

    Сценарий: 1d8+3 оружия + Sneak Attack 2d6, crit=True.
    - Основное 1d8 → 2 кости (DiceExpr.roll(crit=True)).
    - Extra 2d6 → 4 кости (DiceExpr.roll(crit=True)).
    Итого 6 костей.
    """
    # Основное 1d8 (2 кости при крите): 5, 8.
    # Extra 2d6 (4 кости при крите): 6, 4, 3, 2.
    roller = make_roller([5, 8] + [6, 4, 3, 2], bus)  # noqa: RUF005
    ctx = RollContext(
        purpose=RollPurpose.DAMAGE,
        extra_dice=("2d6",),
        crit=True,
    )
    result = roller.roll(DiceExpr.parse("1d8+3"), ctx)

    # Модификатор не удваивается (книга стр. 12).
    assert result.total == 5 + 8 + 3 + 6 + 4 + 3 + 2
    assert result.extra_dice_rolls == (6, 4, 3, 2)
    assert result.crit is True


@pytest.mark.rules
def test_advantage_does_not_leak_into_extra_dice(bus: EventBus) -> None:
    """TR-G002: преимущество применяется только к одиночному d20
    основного броска. Bless'овский +1d4 НЕ получает advantage —
    иначе DiceExpr.roll(advantage=True) на 1d4 упадёт с ValueError.

    Сценарий: d20 с advantage (2 кости d20) + extra_dice=("1d4",).
    Если advantage случайно протечёт в extra — `extra_expr.roll(advantage=True)`
    упадёт. Если не протечёт (правильное поведение) — d4 бросится один раз.
    """
    roller = make_roller([7, 19, 3], bus)
    ctx = RollContext(
        purpose=RollPurpose.ATTACK,
        advantage=True,
        extra_dice=("1d4",),
    )
    result = roller.roll(DiceExpr.parse("d20+5"), ctx)

    assert result.kept == (19,)  # advantage берёт max
    assert result.extra_dice_rolls == (3,)  # одна d4, не две
    assert result.total == 19 + 5 + 3


def test_invalid_extra_dice_raises_dice_parse_error(bus: EventBus) -> None:
    """TR-G005: невалидное extra_dice пробрасывается как DiceParseError,
    не глотается. Контракт: ModifierApplier обязан передавать корректные
    выражения; ошибка должна быть видна сразу в CI, не у игрока."""
    roller = make_roller([10], bus)
    ctx = RollContext(
        purpose=RollPurpose.ATTACK,
        extra_dice=("garbage",),
    )
    with pytest.raises(DiceParseError):
        roller.roll(DiceExpr.parse("d20"), ctx)


# -- 5. tags + d20_raw (нужно мастер-логу и статистике) ---------------


def test_tags_propagate_to_both_events(bus: EventBus) -> None:
    """tags из context попадают на оба события — для фильтрации
    'master_intervention'-записей в логе и т.п."""
    captured_issued: list[RollIssued] = []
    captured_applied: list[RollApplied] = []
    bus.subscribe(RollIssued, captured_issued.append)
    bus.subscribe(RollApplied, captured_applied.append)

    roller = make_roller([10], bus)
    ctx = RollContext(
        purpose=RollPurpose.ATTACK,
        tags=("master_intervention", "reroll"),
    )
    roller.roll(DiceExpr.parse("d20"), ctx)

    assert captured_issued[0].tags == ("master_intervention", "reroll")
    assert captured_applied[0].tags == ("master_intervention", "reroll")


def test_d20_raw_available_for_statistics(bus: EventBus) -> None:
    """DiceStatisticsService опирается на result.d20_raw для расчёта удачи."""
    roller = make_roller([14], bus)
    result = roller.roll(DiceExpr.parse("1d20+5"), RollContext(purpose=RollPurpose.ATTACK))
    assert result.d20_raw == 14


def test_d20_raw_none_for_non_d20(bus: EventBus) -> None:
    """Бросок урона 2d6 — это не d20-тест, статистика «удачи» его игнорирует."""
    roller = make_roller([3, 5], bus)
    result = roller.roll(DiceExpr.parse("2d6"), RollContext(purpose=RollPurpose.DAMAGE))
    assert result.d20_raw is None


# -- 6. Изоляция исключений в подписчиках -----------------------------


def test_crashing_issued_subscriber_does_not_block_applied(
    bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """TR-G006: контракт EventBus гарантирует изоляцию исключений
    (§5.2 п.3). На стыке с DiceRoller это значит: если подписчик
    RollIssued падает — RollApplied всё равно публикуется, roll()
    возвращает нормальный результат, ошибка ловится логом."""
    applied_received: list[RollApplied] = []

    def crashing(_event: RollIssued) -> None:
        raise RuntimeError("issued handler crash")

    bus.subscribe(RollIssued, crashing)
    bus.subscribe(RollApplied, applied_received.append)

    roller = make_roller([10], bus)
    with caplog.at_level(logging.ERROR):
        result = roller.roll(DiceExpr.parse("d20"), RollContext(purpose=RollPurpose.ATTACK))

    assert result.kept == (10,)
    assert len(applied_received) == 1
    assert any("subscriber raised" in r.message for r in caplog.records)
