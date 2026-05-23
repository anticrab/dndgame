"""BattleMode enum + ModeHandler Protocol.

См. spec docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md §4.2.
"""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from dnd.domain.values.square import Square
    from dnd.interfaces.tui.screens.battle import BattleScreen


class BattleMode(Enum):
    NORMAL = "normal"
    MOVE = "move"
    TARGET = "target"


class ModeHandler(Protocol):
    """Контракт для mode-handler'а. BattleScreen делегирует keypress'ы."""

    def on_enter(self, screen: BattleScreen) -> None:
        """Вызывается при входе в mode (после прошлого on_exit)."""
        ...

    def on_exit(self, screen: BattleScreen) -> None:
        """Вызывается при выходе. Очистка cursor/highlights."""
        ...

    def on_key(self, screen: BattleScreen, key: str) -> bool:
        """True если handler съел клавишу. False → bubble дальше."""
        ...

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        """(cursor, highlights, path_preview) для MapWidget.refresh_from."""
        ...


__all__ = ["BattleMode", "ModeHandler"]
