"""TuiIntentProvider — реализация ``PlayerIntentProvider`` поверх
блокирующей очереди ``queue.Queue``.

См. ``docs/TUI.md`` §5. Кратко:

* `GameRunner` крутится в worker-thread и для каждого PC-хода зовёт
  `next_intent`. Метод **блокируется** на ``queue.get()`` без таймаута
  — игроку нужно дать время подумать.
* Главный тред Textual обрабатывает ввод и кладёт сформированный
  ``PlayerIntent`` в очередь — это разблокирует worker.
* `turn_signal` — опциональный callback в main-thread; зовётся через
  ``app.call_from_thread`` (вызывающий передаёт обёрнутую функцию),
  даёт UI шанс обновиться (показать «ход aelar'a», легитимизировать
  меню действий).
"""

from __future__ import annotations

import contextlib
import logging
import queue
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dnd.application.dto.player_intent import PlayerIntent
    from dnd.application.engine.encounter import Encounter
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature

_log = logging.getLogger(__name__)

# Сигнал «новый ход для PC»: UI отображает actor / ctx / encounter и
# открывает меню действий. Callback бесстатусен — он лишь будит UI;
# собранный intent потом приходит через intent_queue.
TurnSignal = Callable[["Creature", "TurnContext", "Encounter"], None]


class TuiIntentProvider:
    """Адаптер ``PlayerIntentProvider`` для Textual.

    Контракт: сначала шлёт ``turn_signal`` (если задан) — UI должен
    обновиться и в итоге положить в `intent_queue` готовый
    ``PlayerIntent``. Метод блокируется на `get()`. Если очередь
    закрыта (`shutdown`), возвращается ``EndTurnIntent`` — это даёт
    GameRunner'у выйти из PC-цикла «по-хорошему».
    """

    def __init__(
        self,
        intent_queue: queue.Queue[PlayerIntent],
        *,
        turn_signal: TurnSignal | None = None,
    ) -> None:
        self._queue = intent_queue
        self._turn_signal = turn_signal
        self._shutdown = False

    def shutdown(self) -> None:
        """Просигналить, что приложение закрывается. Следующий вызов
        ``next_intent`` сразу вернётся EndTurnIntent (worker умрёт)."""
        self._shutdown = True
        # «пустой» элемент-stop разблокирует висящий get(), если он
        # успел встать. Импорт здесь — чтобы не тащить зависимость
        # на модульном уровне (sync с TYPE_CHECKING).
        from dnd.application.dto.player_intent import EndTurnIntent

        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(EndTurnIntent())

    def next_intent(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> PlayerIntent:
        from dnd.application.dto.player_intent import EndTurnIntent

        if self._shutdown:
            return EndTurnIntent()
        if self._turn_signal is not None:
            try:
                self._turn_signal(actor, ctx, encounter)
            except Exception:
                _log.exception("TuiIntentProvider.turn_signal raised; suppressing")
        return self._queue.get()


__all__ = ["TuiIntentProvider", "TurnSignal"]
