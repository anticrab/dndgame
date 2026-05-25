"""MultiTargetModeHandler — inline MULTI_TARGET mode (этап P2b).

Выбор нескольких целей заклинания как **мультимножество**: Tab/Shift+Tab
циклят кандидатов, Space добавляет одно «попадание» текущей цели (повтор —
повторным Space, если spell разрешает повторы), Backspace снимает последнее,
Enter подтверждает набор, Esc отменяет. Никакого ввода чисел — повторы
задаются повторным выбором; на экране счётчик попаданий ✦×N и остаток.
"""
from __future__ import annotations

from collections import Counter

from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.protocol import (
    ModeScreenContext,
    OverlayData,
)


class MultiTargetModeHandler:
    def __init__(self) -> None:
        self._targets: list[tuple[CreatureId, Square]] = []
        self._idx: int = 0
        self._actor_pos: Square = Square(0, 0)
        self._participants: dict[CreatureId, Creature] = {}
        self._max: int = 1
        self._allow_repeat: bool = False
        self._picks: list[CreatureId] = []
        self.confirmed_picks: tuple[CreatureId, ...] | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: ModeScreenContext) -> None:
        self._targets = list(screen._reachable_targets)
        self._actor_pos = screen._current_actor_position
        self._participants = screen._participants
        self._max = screen._multi_max_targets
        self._allow_repeat = screen._multi_allow_repeat
        self._idx = 0
        self._picks = []
        self.confirmed_picks = None
        self.cancelled = False

    def on_exit(self, screen: ModeScreenContext) -> None:
        self._targets = []
        self._participants = {}
        self._picks = []

    def on_key(self, screen: ModeScreenContext, key: str) -> bool:
        if not self._targets:
            return False
        if key == "tab":
            self._idx = (self._idx + 1) % len(self._targets)
            return True
        if key == "shift+tab":
            self._idx = (self._idx - 1) % len(self._targets)
            return True
        if key == "space":
            self._add_current()
            return True
        if key == "backspace":
            if self._picks:
                self._picks.pop()
            return True
        if key == "enter":
            if self._picks:
                self.confirmed_picks = tuple(self._picks)
            return True
        if key == "escape":
            self.cancelled = True
            return True
        return False

    def _add_current(self) -> None:
        if len(self._picks) >= self._max:
            return
        cid = self._targets[self._idx][0]
        if not self._allow_repeat and cid in self._picks:
            return
        self._picks.append(cid)

    def overlay(self) -> OverlayData:
        if not self._targets:
            return OverlayData()
        counts = Counter(self._picks)
        highlights: dict[Square, str] = {}
        for i, (cid, sq) in enumerate(self._targets):
            if i == self._idx:
                highlights[sq] = "reverse bold"
            elif cid in counts:
                highlights[sq] = "green bold"
            else:
                highlights[sq] = "bold"
        _cur_id, cur_sq = self._targets[self._idx]
        picked_str = ", ".join(
            f"{cid} {'✦' * counts[cid]}" for cid in counts
        ) or "—"
        remaining = self._max - len(self._picks)
        hint = (
            f"MULTI: [{picked_str}] — выбери ещё {remaining} (макс {self._max}) · "
            f"Tab цель · Space добавить · Bksp снять · Enter каст · Esc отмена · "
            f"осталось {remaining}"
        )
        return OverlayData(cursor=cur_sq, highlights=highlights, hint=hint)


__all__ = ["MultiTargetModeHandler"]
