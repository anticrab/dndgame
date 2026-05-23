"""LogWidget — журнал событий боя.

См. ``docs/TUI.md`` §6.3.

Принципиальное решение: **переиспользуем форматтер
:class:`EventPrinter` из CLI**. Заводим под него rich-консоль с
in-memory выводом, забираем готовые строки, шлём в Textual
``RichLog``. Это гарантирует, что лог в CLI и TUI идентичен.
"""

from __future__ import annotations

from io import StringIO

from rich.console import Console
from textual.widgets import RichLog

from dnd.application.dto.engine_event import EngineEvent
from dnd.interfaces.cli.event_printer import EventPrinter


class LogWidget(RichLog):
    """RichLog поверх ``EventPrinter``.

    ``handle_event`` форматирует событие так же, как CLI, и пишет
    результат в собственный список строк. Вызывать **из main-thread
    Textual** (через ``app.call_from_thread`` из worker-треда).
    """

    DEFAULT_CSS = ""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        # Каждое событие пишется в отдельный буфер: один rich-Console
        # на событие, чтобы стили не «протекали» между записями.
        self._printer_factory = _make_isolated_printer

    def handle_event(self, event: EngineEvent) -> None:
        buf = StringIO()
        console = Console(file=buf, width=120, force_terminal=True, color_system="truecolor")
        printer = self._printer_factory(console)
        printer._on_event(event)
        text = buf.getvalue().rstrip("\n")
        if text:
            for line in text.splitlines():
                self.write(line)


def _make_isolated_printer(console: Console) -> EventPrinter:
    """Фабрика EventPrinter, чтобы внешний код мог подменить в тестах."""
    return EventPrinter(console=console)


__all__ = ["LogWidget"]
