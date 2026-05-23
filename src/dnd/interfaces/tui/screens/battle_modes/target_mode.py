"""TargetModeHandler — inline TARGET mode.

Tab/Shift+Tab циклит между достижимыми целями. Выбранная подсвечена
'reverse bold'; остальные доступные — 'bold'. Enter → confirmed_target.
"""
from __future__ import annotations

from dnd.application.dto.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.protocol import (
    ModeScreenContext,
    OverlayData,
)


class TargetModeHandler:
    def __init__(self) -> None:
        self._targets: list[tuple[CreatureId, Square]] = []
        self._idx: int = 0
        self.confirmed_target: CreatureId | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: ModeScreenContext) -> None:
        self._targets = list(screen._reachable_targets)
        self._idx = 0
        self.confirmed_target = None
        self.cancelled = False

    def on_exit(self, screen: ModeScreenContext) -> None:
        self._targets = []

    def on_key(self, screen: ModeScreenContext, key: str) -> bool:
        if not self._targets:
            return False
        if key == "tab":
            self._idx = (self._idx + 1) % len(self._targets)
            return True
        if key == "shift+tab":
            self._idx = (self._idx - 1) % len(self._targets)
            return True
        if key == "enter":
            self.confirmed_target = self._targets[self._idx][0]
            return True
        if key == "escape":
            self.cancelled = True
            return True
        return False

    def overlay(self) -> OverlayData:
        if not self._targets:
            return OverlayData()
        highlights: dict[Square, str] = {}
        for i, (_, sq) in enumerate(self._targets):
            highlights[sq] = "reverse bold" if i == self._idx else "bold"
        cur_id, cur_sq = self._targets[self._idx]
        hint = (
            f"TARGET: {cur_id} ({self._idx + 1}/{len(self._targets)}) — "
            f"Tab next · Enter ok · Esc cancel"
        )
        return OverlayData(
            cursor=cur_sq,
            highlights=highlights,
            hint=hint,
        )


__all__ = ["TargetModeHandler"]
