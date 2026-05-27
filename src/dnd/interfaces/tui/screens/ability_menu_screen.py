"""AbilityMenuScreen — меню выбора/перебинда способностей (этап S).

Экран НЕ обращается к движку: контроллер (BattleScreen) передаёт готовые
``rows`` (способность + текущий хоткей + доступность) и колбэки apply/rebind.
↑↓ — выбор, Enter — применить, b — назначить клавишу, Esc — закрыть.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label

from dnd.application.abilities.ability import Ability


@dataclass(frozen=True)
class AbilityRow:
    """Строка меню: способность + её текущая клавиша + доступность сейчас."""

    ability: Ability
    hotkey: str  # текущая привязка или "" (нет хоткея)
    available: bool  # хватает ли экономии действия


class AbilityMenuScreen(ModalScreen[None]):
    """Список способностей активного PC с применением и перебиндом."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("up", "cursor_up", "Up"),
        ("down", "cursor_down", "Down"),
        ("enter", "apply", "Apply"),
        ("b", "rebind", "Bind"),
        ("escape", "close", "Close"),
    ]

    def __init__(
        self,
        rows: list[AbilityRow],
        *,
        on_apply: Callable[[Ability], None],
        on_rebind: Callable[[Ability, str], None],
    ) -> None:
        super().__init__()
        self._rows = rows
        self._on_apply = on_apply
        self._on_rebind = on_rebind
        self._cursor = 0
        self._awaiting_key = False  # режим «нажмите клавишу» для перебинда

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label("СПОСОБНОСТИ", classes="modal-title")
            yield Label("", id="ability-list")
            yield Label(
                "[↑↓] выбор  [Enter] применить  [b] назначить клавишу  [Esc] закрыть",
                id="ability-help",
            )

    def on_mount(self) -> None:
        self._refresh_list()

    def _refresh_list(self) -> None:
        lines: list[str] = []
        for i, row in enumerate(self._rows):
            marker = ">" if i == self._cursor else " "
            key = f"[{row.hotkey}]" if row.hotkey else "[—]"
            name = f"{row.ability.icon} {row.ability.name}"
            if row.available:
                lines.append(f"{marker} {key:<5} {name}")
            else:
                lines.append(f"[dim]{marker} {key:<5} {name}  (недоступно)[/dim]")
        body = "\n".join(lines) if lines else "(нет способностей)"
        if self._awaiting_key:
            body += "\n\nНажмите клавишу для назначения… (Esc — отмена)"
        self.query_one("#ability-list", Label).update(body)

    # --- actions (BINDINGS) -------------------------------------------

    def action_cursor_up(self) -> None:
        if self._awaiting_key or not self._rows:
            return
        self._cursor = (self._cursor - 1) % len(self._rows)
        self._refresh_list()

    def action_cursor_down(self) -> None:
        if self._awaiting_key or not self._rows:
            return
        self._cursor = (self._cursor + 1) % len(self._rows)
        self._refresh_list()

    def action_apply(self) -> None:
        if self._awaiting_key or not self._rows:
            return
        row = self._rows[self._cursor]
        if not row.available:
            return
        self.dismiss()
        self._on_apply(row.ability)

    def action_rebind(self) -> None:
        if self._awaiting_key or not self._rows:
            return
        self._awaiting_key = True
        self._refresh_list()

    def action_close(self) -> None:
        if self._awaiting_key:
            self._awaiting_key = False
            self._refresh_list()
            return
        self.dismiss()

    # --- raw key capture для перебинда --------------------------------

    def on_key(self, event: events.Key) -> None:
        """В режиме «нажмите клавишу» перехватываем буквенно-цифровую клавишу
        как назначаемый хоткей (приоритетнее BINDINGS). Esc обрабатывает
        action_close."""
        if not self._awaiting_key or event.key == "escape":
            return
        if len(event.key) == 1 and event.key.isalnum():
            ability = self._rows[self._cursor].ability
            self._awaiting_key = False
            event.stop()
            event.prevent_default()
            self.dismiss()
            self._on_rebind(ability, event.key)
