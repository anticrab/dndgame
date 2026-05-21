"""Тесты ``InMemoryEventBus`` — буквальная проверка контракта ENGINE.md §5.2.

Каждое из четырёх правил контракта — отдельный тест-доказательство.
Если правило где-то нарушится — мы это заметим до того, как любой
другой код начнёт зависеть от него.
"""

from __future__ import annotations

import logging
from typing import ClassVar

import pytest

from dnd.application.dto.engine_event import EngineEvent
from dnd.application.ports.event_bus import EventBus
from dnd.infrastructure.events.in_memory_event_bus import InMemoryEventBus

# -- тестовые события ------------------------------------------------------


class _A(EngineEvent):
    event_type: ClassVar[str] = "test.a"
    value: int = 0


class _B(EngineEvent):
    event_type: ClassVar[str] = "test.b"
    value: int = 0


class _ASub(_A):
    """Подкласс A — для проверки матчинга подписки по базе."""

    event_type: ClassVar[str] = "test.a.sub"


@pytest.fixture
def bus() -> EventBus:
    return InMemoryEventBus()


# -- 1. Базовая доставка ---------------------------------------------------


def test_subscribe_then_publish_delivers(bus: EventBus) -> None:
    received: list[_A] = []
    bus.subscribe(_A, received.append)
    bus.publish(_A(value=1))
    assert received == [_A(value=1)]


def test_no_subscribers_publish_is_noop(bus: EventBus) -> None:
    """Публикация без подписчиков не падает."""
    bus.publish(_A(value=42))  # не должен ничего raise


def test_multiple_subscribers_get_event_in_registration_order(bus: EventBus) -> None:
    seen: list[str] = []
    bus.subscribe(_A, lambda e: seen.append(f"first:{e.value}"))
    bus.subscribe(_A, lambda e: seen.append(f"second:{e.value}"))
    bus.publish(_A(value=7))
    assert seen == ["first:7", "second:7"]


def test_subscribers_only_get_matching_event_type(bus: EventBus) -> None:
    a_seen: list[_A] = []
    b_seen: list[_B] = []
    bus.subscribe(_A, a_seen.append)
    bus.subscribe(_B, b_seen.append)
    bus.publish(_A(value=1))
    bus.publish(_B(value=2))
    assert len(a_seen) == 1 and len(b_seen) == 1


def test_subclass_event_delivered_to_base_subscribers(bus: EventBus) -> None:
    """Подписка на _A получает и _ASub (важно для общих подписчиков
    типа GameLog, который слушает EngineEvent)."""
    seen_a: list[_A] = []
    seen_sub: list[_ASub] = []
    bus.subscribe(_A, seen_a.append)
    bus.subscribe(_ASub, seen_sub.append)

    bus.publish(_ASub(value=1))

    assert len(seen_a) == 1
    assert len(seen_sub) == 1


def test_engineevent_base_subscriber_gets_all(bus: EventBus) -> None:
    """Подписчик на EngineEvent получает все события — это паттерн
    для GameLog writer'а."""
    all_events: list[EngineEvent] = []
    bus.subscribe(EngineEvent, all_events.append)
    bus.publish(_A(value=1))
    bus.publish(_B(value=2))
    assert len(all_events) == 2


# -- 2. FIFO + реентерабельность (правило 1) -------------------------------


def test_nested_publish_is_queued_not_recursive(bus: EventBus) -> None:
    """publish() внутри хендлера ставит событие в **хвост** очереди.

    Сценарий: подписчик на _A публикует _B; подписчик на _B копит
    последовательность. Если бы был рекурсивный вызов — _B-хендлер
    отработал бы внутри _A-хендлера; вместо этого он должен
    отработать ПОСЛЕ _A.
    """
    timeline: list[str] = []

    def on_a(_event: _A) -> None:
        timeline.append("A:start")
        bus.publish(_B(value=99))  # вложенный publish
        timeline.append("A:end")

    def on_b(_event: _B) -> None:
        timeline.append("B")

    bus.subscribe(_A, on_a)
    bus.subscribe(_B, on_b)
    bus.publish(_A(value=1))

    assert timeline == ["A:start", "A:end", "B"]


def test_chain_three_events_controlled(bus: EventBus) -> None:
    """Контролируемая цепочка с явным завершением: A→B→A(финал)."""
    timeline: list[str] = []
    fired = {"a_count": 0}

    def a_handler(_e: _A) -> None:
        timeline.append(f"A{fired['a_count']}")
        fired["a_count"] += 1
        if fired["a_count"] == 1:
            bus.publish(_B(value=10))

    def b_handler(_e: _B) -> None:
        timeline.append("B")
        bus.publish(_A(value=20))

    bus.subscribe(_A, a_handler)
    bus.subscribe(_B, b_handler)
    bus.publish(_A(value=1))

    # Ожидаемая хронология: A0 (публикует B), затем B (публикует A),
    # затем A1 (уже не публикует ничего). Очередь FIFO.
    assert timeline == ["A0", "B", "A1"]


# -- 3. Изменения подписок во время dispatch (правило 2) -------------------


def test_subscribe_during_dispatch_applies_to_next_publish(bus: EventBus) -> None:
    """Если в хендлере подписать ещё одного — он получит только
    события, опубликованные ПОСЛЕ возврата из текущего хендлера."""
    seen: list[str] = []

    def late_subscriber(event: _A) -> None:
        seen.append(f"late:{event.value}")

    def primary(_event: _A) -> None:
        seen.append("primary")
        bus.subscribe(_A, late_subscriber)

    bus.subscribe(_A, primary)

    # Первая публикация — late_subscriber подписан, но НЕ получает её,
    # потому что в текущей волне late_subscriber подписан во время
    # хендлера primary.
    bus.publish(_A(value=1))
    # Вторая публикация — late_subscriber уже зарегистрирован.
    bus.publish(_A(value=2))

    assert seen == ["primary", "primary", "late:2"]


def test_unsubscribe_during_dispatch_applies_next(bus: EventBus) -> None:
    """Отписка во время текущего dispatch не «выкидывает» того, кому
    уже идёт доставка; применяется со следующей публикации."""
    seen: list[str] = []
    unsub_holder: list = []

    def primary(_e: _A) -> None:
        seen.append("primary")
        unsub_holder[0]()  # отписать secondary

    def secondary(_e: _A) -> None:
        seen.append("secondary")

    bus.subscribe(_A, primary)
    unsub = bus.subscribe(_A, secondary)
    unsub_holder.append(unsub)

    bus.publish(_A(value=1))
    bus.publish(_A(value=2))

    # На первой публикации secondary всё ещё получает, потому что
    # снимок хендлеров сделан перед dispatch. На второй — уже нет.
    assert seen == ["primary", "secondary", "primary"]


def test_unsubscribe_after_dispatch_works(bus: EventBus) -> None:
    """Отписка вне dispatch применяется сразу."""
    seen: list[str] = []
    unsub = bus.subscribe(_A, lambda _e: seen.append("x"))
    bus.publish(_A(value=1))
    unsub()
    bus.publish(_A(value=2))
    assert seen == ["x"]


def test_double_unsubscribe_safe(bus: EventBus) -> None:
    """Повторная отписка не падает."""
    unsub = bus.subscribe(_A, lambda _e: None)
    unsub()
    unsub()  # должно быть безопасно


# -- 4. Исключения подписчика не блокируют остальных (правило 3) -----------


def test_handler_exception_is_isolated(bus: EventBus, caplog: pytest.LogCaptureFixture) -> None:
    """Если первый подписчик кинул исключение, второй всё равно
    получает событие. Само publish ничего не raise. Ошибка
    логируется на уровне ERROR."""
    seen: list[str] = []

    def bad_handler(_e: _A) -> None:
        raise RuntimeError("oops in subscriber")

    def good_handler(_e: _A) -> None:
        seen.append("ok")

    bus.subscribe(_A, bad_handler)
    bus.subscribe(_A, good_handler)

    with caplog.at_level(logging.ERROR):
        bus.publish(_A(value=1))  # не должен ничего raise

    assert seen == ["ok"]
    assert any("subscriber raised" in r.message for r in caplog.records)


def test_handler_exception_does_not_stop_event_queue(
    bus: EventBus, caplog: pytest.LogCaptureFixture
) -> None:
    """Сбой в хендлере одного события не останавливает обработку
    следующих в очереди."""
    seen: list[str] = []

    def crashing(_e: _A) -> None:
        raise ValueError("crash")

    bus.subscribe(_A, crashing)
    bus.subscribe(_B, lambda _e: seen.append("b"))

    with caplog.at_level(logging.ERROR):
        # Запустим _A (упадёт), потом _B (должно обработаться).
        # Чтобы оба попали в одну волну — публикуем _B внутри второго
        # хендлера _A. Используем вспомогательный noop-хендлер.
        def trigger_b(_e: _A) -> None:
            bus.publish(_B(value=2))

        bus.subscribe(_A, trigger_b)
        bus.publish(_A(value=1))

    assert seen == ["b"]


# -- свойственные ----------------------------------------------------------


def test_publish_does_not_reenter_self_with_same_handler(bus: EventBus) -> None:
    """Подписчик на A может опубликовать B; B-хендлер ≠ A-хендлер.
    A-хендлер НЕ получит вторичной доставки внутри своего же вызова."""
    nested_calls: list[int] = []

    def on_a(_e: _A) -> None:
        nested_calls.append(1)
        bus.publish(_B(value=2))  # не должно дёрнуть on_a

    bus.subscribe(_A, on_a)
    bus.subscribe(_B, lambda _e: None)

    bus.publish(_A(value=1))

    assert len(nested_calls) == 1
