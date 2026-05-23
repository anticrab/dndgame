"""NormalModeHandler — пустой делегатор.

В NORMAL mode никаких overlay'ев нет. Ability hotkey'и обрабатываются
не handler'ом, а самим BattleScreen (через AbilityRegistry в L2-T7).
Этот handler нужен только чтобы state machine всегда имела активный
ModeHandler.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.square import Square

if TYPE_CHECKING:
    from dnd.interfaces.tui.screens.battle import BattleScreen


class NormalModeHandler:
    def on_enter(self, screen: BattleScreen) -> None:
        return None

    def on_exit(self, screen: BattleScreen) -> None:
        return None

    def on_key(self, screen: BattleScreen, key: str) -> bool:
        return False

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        return (None, {}, ())


__all__ = ["NormalModeHandler"]
