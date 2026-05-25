"""Тесты TuiIntentProvider.

Покрытие:
* блокируется на пустой очереди;
* отдаёт intent, положенный в очередь;
* shutdown разблокирует висящий get → EndTurnIntent;
* turn_signal зовётся перед каждым ожиданием;
* исключение в turn_signal не ломает next_intent (логируется).
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable

from dnd.application.dto.player_intent import (
    AttackIntent,
    DodgeIntent,
    EndTurnIntent,
    PlayerIntent,
)
from dnd.domain.values.ids import CreatureId
from dnd.interfaces.tui.bridge.intent_provider import TuiIntentProvider


def _provider(
    *,
    turn_signal: Callable[..., None] | None = None,
) -> tuple[TuiIntentProvider, queue.Queue[PlayerIntent]]:
    q: queue.Queue[PlayerIntent] = queue.Queue()
    return TuiIntentProvider(q, turn_signal=turn_signal), q


def test_returns_intent_put_in_queue() -> None:
    provider, q = _provider()
    intent = DodgeIntent()
    q.put(intent)
    out = provider.next_intent(actor=None, ctx=None, encounter=None)  # type: ignore[arg-type]
    assert out is intent


def test_blocks_until_intent_available() -> None:
    provider, q = _provider()
    result: list[PlayerIntent] = []

    def consume() -> None:
        result.append(provider.next_intent(actor=None, ctx=None, encounter=None))  # type: ignore[arg-type]

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    # Поток должен заблокироваться: нет результата за 50ms.
    t.join(timeout=0.05)
    assert t.is_alive()
    assert result == []

    intent = AttackIntent(target_id=CreatureId("goblin"))
    q.put(intent)
    t.join(timeout=1.0)
    assert result == [intent]


def test_shutdown_unblocks_with_end_turn() -> None:
    provider, _q = _provider()
    result: list[PlayerIntent] = []

    def consume() -> None:
        result.append(provider.next_intent(actor=None, ctx=None, encounter=None))  # type: ignore[arg-type]

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    t.join(timeout=0.05)
    assert t.is_alive()

    provider.shutdown()
    t.join(timeout=1.0)
    assert len(result) == 1
    assert isinstance(result[0], EndTurnIntent)


def test_shutdown_before_next_intent_returns_end_turn_immediately() -> None:
    provider, _q = _provider()
    provider.shutdown()
    out = provider.next_intent(actor=None, ctx=None, encounter=None)  # type: ignore[arg-type]
    assert isinstance(out, EndTurnIntent)


def test_turn_signal_called_before_get() -> None:
    calls: list[tuple[object, object, object]] = []

    def signal(actor: object, ctx: object, enc: object) -> None:
        calls.append((actor, ctx, enc))

    provider, q = _provider(turn_signal=signal)
    q.put(DodgeIntent())
    provider.next_intent(actor="a", ctx="c", encounter="e")  # type: ignore[arg-type]
    assert calls == [("a", "c", "e")]


def test_turn_signal_exception_is_suppressed() -> None:
    def boom(actor: object, ctx: object, enc: object) -> None:
        del actor, ctx, enc
        raise RuntimeError("ui exploded")

    provider, q = _provider(turn_signal=boom)
    intent = DodgeIntent()
    q.put(intent)
    # next_intent НЕ должен пробросить — boom логируется.
    out = provider.next_intent(actor=None, ctx=None, encounter=None)  # type: ignore[arg-type]
    assert out is intent
