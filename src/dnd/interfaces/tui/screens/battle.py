"""BattleScreen — основной экран боя.

См. ``docs/TUI.md`` §6 и mockup A.1 (80×24 layout).

Раскладка::

    ┌─ STATUS ────────────────────────────────┐
    │ Aelar HP 12/12 AC 16 …                  │
    ├─ MAP ──────────────────────┬─ INIT ──────┤
    │ ##########                 │ 1 ▶ Aelar 14│
    │ #...@....#                 │ 2  Goblin 11│
    │ #..g.g...#                 │             │
    ├─ LOG ──────────────────────┴─ ACTIONS ──┤
    │ > Aelar attacks Goblin A: hit, 9 dmg.   │
    │ ...                                     │
    └─────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header

from dnd.interfaces.tui.widgets import (
    InitiativeWidget,
    LogWidget,
    MapWidget,
    StatusWidget,
)


class BattleScreen(Screen[None]):
    """Главный экран боя. Состояние внутри — только виджеты;
    обновления приходят извне (от EventRenderer)."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("a", "intent_attack", "Attack"),
        ("m", "intent_move", "Move"),
        ("d", "intent_dodge", "Dodge"),
        ("h", "intent_dash", "Dash"),
        ("g", "intent_disengage", "Disengage"),
        ("e", "intent_end_turn", "End turn"),
        ("q", "quit_app", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield StatusWidget(id="status")
        with Horizontal():
            yield MapWidget(id="map")
            with Vertical():
                yield InitiativeWidget(id="init")
        yield LogWidget(id="log", wrap=True, highlight=True, markup=True, max_lines=200)
        yield Footer()

    # --- accessors --------------------------------------------------

    @property
    def map_widget(self) -> MapWidget:
        return self.query_one("#map", MapWidget)

    @property
    def status_widget(self) -> StatusWidget:
        return self.query_one("#status", StatusWidget)

    @property
    def initiative_widget(self) -> InitiativeWidget:
        return self.query_one("#init", InitiativeWidget)

    @property
    def log_widget(self) -> LogWidget:
        return self.query_one("#log", LogWidget)

    # --- action handlers (заглушки на этапе J2) ---------------------

    def action_intent_attack(self) -> None:
        """В J3 заменится на push модального TargetPicker и
        формирование AttackIntent. Сейчас — no-op."""

    def action_intent_move(self) -> None:
        """В J3 заменится на push MovePicker / MoveIntent."""

    def action_intent_dodge(self) -> None:
        """В J3 — отправка DodgeIntent в очередь."""

    def action_intent_dash(self) -> None:
        """В J3 — DashIntent."""

    def action_intent_disengage(self) -> None:
        """В J3 — DisengageIntent."""

    def action_intent_end_turn(self) -> None:
        """В J3 — EndTurnIntent."""

    def action_quit_app(self) -> None:
        """Выход с подтверждением (modal — пост-MVP J2)."""
        self.app.exit()


__all__ = ["BattleScreen"]
