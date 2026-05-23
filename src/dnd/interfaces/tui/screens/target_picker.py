"""TargetPicker — модальный экран выбора цели атаки.

См. ``docs/TUI.md`` §6.6. Tab / Shift+Tab — циклит, Enter подтверждает,
Esc отменяет.

Список целей формируется снаружи (в обработчике клавиши `a` на
BattleScreen) — модальный экран только показывает их и возвращает
выбранный ``CreatureId`` через результат.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from dnd.application.dto.ids import CreatureId


class TargetPicker(ModalScreen[CreatureId | None]):
    """Модальное окно: выбор цели. Возвращает CreatureId или None."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm", "Confirm"),
    ]

    def __init__(
        self,
        targets: list[tuple[CreatureId, str]],
    ) -> None:
        super().__init__()
        self._targets = targets

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Choose target:", classes="modal-title")
            yield ListView(
                *(ListItem(Label(label)) for _, label in self._targets),
                id="target-list",
            )

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        listview = self.query_one("#target-list", ListView)
        idx = listview.index or 0
        self.dismiss(self._targets[idx][0])


__all__ = ["TargetPicker"]
