"""ModeHintWidget — однострочная подсказка над/под картой.

В NORMAL mode — пусто (не занимает места). В MOVE — «MOVE: cursor=(15,8)
cost=25/30 ft», в TARGET — «TARGET: g1 (1/3) — Tab next · Enter ok».
BattleScreen вызывает :meth:`set_text` после смены mode/курсора.
"""
from __future__ import annotations

from textual.widgets import Static


class ModeHintWidget(Static):
    DEFAULT_CSS = "ModeHintWidget { height: 1; padding: 0 1; }"

    def set_text(self, text: str) -> None:
        # Static.update принимает Rich markup, так что [yellow]…[/]
        # из handler'а отрендерится корректно.
        self.update(text)


__all__ = ["ModeHintWidget"]
