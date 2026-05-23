"""Тесты RunnerWorker (daemon-thread обёртка для GameRunner.run)."""

from __future__ import annotations

import threading
import time

from dnd.interfaces.tui.bridge.runner_worker import RunnerWorker


def test_worker_runs_target_and_calls_on_finished_without_exception() -> None:
    done = threading.Event()
    seen: list[BaseException | None] = []

    def target() -> None:
        done.set()

    def on_finished(exc: BaseException | None) -> None:
        seen.append(exc)

    w = RunnerWorker(target=target, on_finished=on_finished)
    w.start()
    w.join(timeout=2.0)
    assert done.is_set()
    assert seen == [None]
    assert not w.is_alive()


def test_worker_captures_exception_and_passes_to_on_finished() -> None:
    seen: list[BaseException | None] = []

    def target() -> None:
        raise ValueError("boom")

    def on_finished(exc: BaseException | None) -> None:
        seen.append(exc)

    w = RunnerWorker(target=target, on_finished=on_finished)
    w.start()
    w.join(timeout=2.0)
    assert len(seen) == 1
    assert isinstance(seen[0], ValueError)
    assert str(seen[0]) == "boom"


def test_worker_is_daemon() -> None:
    """Демоничность важна: если процесс закрывается до завершения
    GameRunner.run, поток не блокирует выход."""
    w = RunnerWorker(target=lambda: time.sleep(0.01))
    assert w._thread.daemon is True
    w.start()
    w.join()
