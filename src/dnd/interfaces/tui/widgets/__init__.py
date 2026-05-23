"""Виджеты TUI-боя. См. ``docs/TUI.md`` §6."""

from dnd.interfaces.tui.widgets.action_bar_widget import (
    ActionBarWidget,
    format_action_bar,
)
from dnd.interfaces.tui.widgets.initiative_widget import (
    InitiativeWidget,
    format_initiative,
)
from dnd.interfaces.tui.widgets.log_widget import LogWidget
from dnd.interfaces.tui.widgets.map_widget import MapWidget, render_battlefield
from dnd.interfaces.tui.widgets.mode_hint_widget import ModeHintWidget
from dnd.interfaces.tui.widgets.status_widget import StatusWidget, format_status

__all__ = [
    "ActionBarWidget",
    "InitiativeWidget",
    "LogWidget",
    "MapWidget",
    "ModeHintWidget",
    "StatusWidget",
    "format_action_bar",
    "format_initiative",
    "format_status",
    "render_battlefield",
]
