"""RunnerWorker — обёртка для запуска ``GameRunner.run`` в отдельном
треде.

В Textual event-loop крутится в основном треде; блокирующий
``next_intent`` на ``queue.get()`` затормозил бы UI. Поэтому
``GameRunner.run(encounter)`` уезжает в daemon-thread, а Textual
получает обновления через ``EventRenderer`` (он шлёт callbacks
через ``app.call_from_thread``).

См. ``docs/TUI.md`` §4.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

_log = logging.getLogger(__name__)


class RunnerWorker:
    """Демонический фон для одного `GameRunner.run` запуска.

    ``start`` стартует поток; ``join`` ждёт завершения; ``is_alive`` —
    статус. ``on_finished`` (опционально) — callback, который зовётся
    в **worker-тред** сразу после завершения `run`. UI должен оборачивать
    его в ``app.call_from_thread``, чтобы обновить экран Победы.
    """

    def __init__(
        self,
        target: Callable[[], None],
        *,
        on_finished: Callable[[BaseException | None], None] | None = None,
    ) -> None:
        self._target = target
        self._on_finished = on_finished
        self._thread = threading.Thread(
            target=self._run, name="dnd-game-runner", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def _run(self) -> None:
        exc: BaseException | None = None
        try:
            self._target()
        except BaseException as e:
            _log.exception("RunnerWorker: game runner raised")
            exc = e
        finally:
            if self._on_finished is not None:
                try:
                    self._on_finished(exc)
                except Exception:
                    _log.exception(
                        "RunnerWorker.on_finished raised; suppressing"
                    )


__all__ = ["RunnerWorker"]
