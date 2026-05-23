"""TargetPicker — модальный экран выбора цели атаки.

См. ``docs/TUI.md`` §6.6.

Управление:
* ↑/↓ — выбор цели в списке (ListView сам).
* Enter — подтвердить выбранную (ловится через ``ListView.Selected``).
* Esc — отмена → dismiss(None).

ListView перехватывает Enter и поднимает свой ``Selected``-message;
полагаться на Screen.BINDINGS `enter` ненадёжно (binding не bubble'ит
через consumed key). Поэтому ловим именно событие виджета.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView


class TargetPicker(ModalScreen["str | None"]):
    """Модальное окно: выбор цели. Возвращает id (str) или None.

    Принимает список ``(id, label)``. ``id`` типизирован как ``str``,
    чтобы picker подходил и для ``CreatureId`` (атака), и для
    ``ObjectId`` (interact / break) — оба ``NewType`` поверх ``str``.
    Вызывающий после dismiss приводит результат к нужному NewType.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel", "Cancel"),
        # Дополнительные клавиши подтверждения — если фокус не в
        # ListView (например, начало диалога), space всё равно работает.
        ("space", "confirm", "Confirm"),
    ]

    def __init__(
        self,
        targets: list[tuple[str, str]],
    ) -> None:
        super().__init__()
        self._targets = targets

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Choose target:  (↑/↓, Enter, Esc)", classes="modal-title")
            yield ListView(
                *(ListItem(Label(label)) for _, label in self._targets),
                id="target-list",
            )

    def on_mount(self) -> None:
        # Передаём фокус в ListView, чтобы стрелки/Enter сразу работали.
        self.query_one("#target-list", ListView).focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        listview = self.query_one("#target-list", ListView)
        idx = listview.index or 0
        self.dismiss(self._targets[idx][0])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter в ListView → ListView.Selected. Берём индекс выбранного
        item'а и подтверждаем."""
        del event
        self.action_confirm()


__all__ = ["TargetPicker"]
