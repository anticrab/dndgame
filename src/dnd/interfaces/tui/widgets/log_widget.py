"""LogWidget — журнал событий боя.

См. ``docs/TUI.md`` §6.3.

Принципиальное решение: **переиспользуем форматтер
:class:`EventPrinter` из CLI**. Подаём EventPrinter'у sink-callback
(`RichLog.write` с `markup=True`) — Textual сам интерпретирует
rich-разметку. Это гарантирует, что лог в CLI и TUI идентичен,
и **никаких ANSI escape-кодов** не утекает в TUI.
"""

from __future__ import annotations

from textual.widgets import RichLog

from dnd.application.dto.engine_event import EngineEvent
from dnd.interfaces.cli.event_printer import EventPrinter


class LogWidget(RichLog):
    """RichLog поверх ``EventPrinter`` через sink-callback."""

    DEFAULT_CSS = ""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # EventPrinter без Console (sink); sink — наш write_markup.
        self._printer = EventPrinter(sink=self._write_markup)

    def handle_event(self, event: EngineEvent) -> None:
        self._printer.dispatch_event(event)

    def _write_markup(self, line: str) -> None:
        # RichLog с markup=True сам разберёт [bold red]...[/].
        # Многострочные строки от EventPrinter (например, encounter ended)
        # разбираем по \n.
        for sub in line.splitlines():
            if sub.strip():
                self.write(sub)


__all__ = ["LogWidget"]
