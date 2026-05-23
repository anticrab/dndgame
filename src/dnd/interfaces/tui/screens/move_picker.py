"""MovePicker — модальный экран выбора клетки для движения.

См. ``docs/TUI.md`` §6.7. Курсор сдвигается стрелками, Enter подтверждает,
Esc отменяет. Путь строится прямой chebyshev-линией от стартовой
клетки.

MovePicker не валидирует путь — это делает MoveAction.can_perform_against.
Картой и стартовой клеткой делится с BattleScreen.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.interfaces.tui.widgets.map_widget import render_battlefield

if False:  # only for typing
    from dnd.application.dto.ids import CreatureId
    from dnd.domain.values.faction import Faction


def _chebyshev_path(start: Square, target: Square) -> tuple[Square, ...]:
    """Прямой пошаговый путь по диагонали от start к target. Не
    проверяет проходимость — MoveAction.can_perform_against это
    сделает."""
    if start == target:
        return ()
    path: list[Square] = []
    cur = start
    while cur != target:
        dx = (target.x > cur.x) - (target.x < cur.x)
        dy = (target.y > cur.y) - (target.y < cur.y)
        nxt = Square(cur.x + dx, cur.y + dy)
        path.append(nxt)
        cur = nxt
    return tuple(path)


class MovePicker(ModalScreen["tuple[Square, ...] | None"]):
    """Выбор целевой клетки для движения. Возвращает chebyshev-путь
    (без стартовой клетки) или None при отмене."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("escape", "cancel", "Cancel"),
        ("enter", "confirm", "Confirm"),
        ("up", "move_cursor(0,-1)", "Up"),
        ("down", "move_cursor(0,1)", "Down"),
        ("left", "move_cursor(-1,0)", "Left"),
        ("right", "move_cursor(1,0)", "Right"),
    ]

    cursor: reactive[Square] = reactive(Square(0, 0))

    def __init__(
        self,
        battlefield: Battlefield,
        factions: dict[CreatureId, Faction],
        start: Square,
    ) -> None:
        super().__init__()
        self._battlefield = battlefield
        self._factions = factions
        self._start = start
        self.cursor = start

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("Move to (arrows / Enter / Esc):", classes="modal-title")
            yield Static(id="picker-map")
            yield Label("", id="picker-info")
        # Текст обновим в on_mount после монтирования виджетов.

    def on_mount(self) -> None:
        self._rerender()

    def watch_cursor(self, _old: Square, _new: Square) -> None:
        # reactive: вызывается на любое изменение cursor; перерендерим.
        if self.is_mounted:
            self._rerender()

    def action_move_cursor(self, dx: int, dy: int) -> None:
        nx = self.cursor.x + dx
        ny = self.cursor.y + dy
        if 0 <= nx < self._battlefield.width and 0 <= ny < self._battlefield.height:
            self.cursor = Square(nx, ny)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        self.dismiss(_chebyshev_path(self._start, self.cursor))

    # --- private ----------------------------------------------------

    def _rerender(self) -> None:
        body = self.query_one("#picker-map", Static)
        info = self.query_one("#picker-info", Label)
        body.update(
            render_battlefield(self._battlefield, self._factions, cursor=self.cursor)
        )
        steps = len(_chebyshev_path(self._start, self.cursor))
        info.update(f"Cursor: {self.cursor}  |  Path: {steps} step(s)")


__all__ = ["MovePicker"]
