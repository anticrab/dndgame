"""EndScreen — модальный экран «Бой завершён».

Точка фокуса после ``EncounterEnded``: показывает победителя и
survivors, перехватывает ввод (Esc/Enter/Q → exit). Заявлен в
``docs/TUI.md`` §3, §4, §11 как часть MVP J.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

from dnd.application.dto.engine_event import EncounterEnded


class EndScreen(ModalScreen[None]):
    """«Победа!» / «Поражение!» / «Ничья!» оверлей.

    Содержит итог боя (фракция-победитель + список выживших) и
    одну кнопку «Quit» (Enter/Q/Esc).
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "quit", "Quit"),
        ("enter", "quit", "Quit"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, event: EncounterEnded) -> None:
        super().__init__()
        self._event = event

    def compose(self) -> ComposeResult:
        if self._event.winners is None:
            title = "DRAW"
        else:
            title = f"{self._event.winners.value.upper()} WINS"
        if self._event.survivors:
            survivors = ", ".join(self._event.survivors)
            survivors_line = f"Survivors: {survivors}"
        else:
            survivors_line = "No survivors."

        with Vertical(classes="modal-box"):
            yield Label(title, classes="modal-title")
            yield Label(f"Round {self._event.round_number}")
            yield Label(survivors_line)
            yield Label("")
            yield Label("[Enter / Esc / Q] — Quit")

    def action_quit(self) -> None:
        self.app.exit()


__all__ = ["EndScreen"]
