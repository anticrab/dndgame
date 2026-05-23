"""NormalModeHandler — пустой делегатор.

В NORMAL mode никаких overlay'ев нет. Ability hotkey'и обрабатываются
не handler'ом, а самим BattleScreen (через AbilityRegistry в L2-T7).
Этот handler нужен только чтобы state machine всегда имела активный
ModeHandler.
"""
from __future__ import annotations

from dnd.interfaces.tui.screens.battle_modes.protocol import (
    ModeScreenContext,
    OverlayData,
)


class NormalModeHandler:
    def on_enter(self, screen: ModeScreenContext) -> None:
        return None

    def on_exit(self, screen: ModeScreenContext) -> None:
        return None

    def on_key(self, screen: ModeScreenContext, key: str) -> bool:
        return False

    def overlay(self) -> OverlayData:
        return OverlayData()


__all__ = ["NormalModeHandler"]
