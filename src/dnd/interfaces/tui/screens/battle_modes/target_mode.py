"""TargetModeHandler — inline TARGET mode.

Tab/Shift+Tab циклит между достижимыми целями. Выбранная подсвечена
'reverse bold'; остальные доступные — 'bold'. Enter → confirmed_target.

Hint показывает HP/AC и расстояние выбранной цели (N-3) — без этого
игрок не понимает, в кого бить выгоднее (когда целей много).
"""
from __future__ import annotations

from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.creature import Creature
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.protocol import (
    ModeScreenContext,
    OverlayData,
)


class TargetModeHandler:
    def __init__(self) -> None:
        self._targets: list[tuple[CreatureId, Square]] = []
        self._idx: int = 0
        self._actor_pos: Square = Square(0, 0)
        self._participants: dict[CreatureId, Creature] = {}
        self.confirmed_target: CreatureId | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: ModeScreenContext) -> None:
        self._targets = list(screen._reachable_targets)
        self._actor_pos = screen._current_actor_position
        self._participants = screen._participants
        self._idx = 0
        self.confirmed_target = None
        self.cancelled = False

    def on_exit(self, screen: ModeScreenContext) -> None:
        self._targets = []
        self._participants = {}

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
        dist_ft = 5 * max(
            abs(self._actor_pos.x - cur_sq.x),
            abs(self._actor_pos.y - cur_sq.y),
        )
        info = self._target_info(cur_id, dist_ft)
        hint = (
            f"TARGET: {cur_id} {info} ({self._idx + 1}/{len(self._targets)}) — "
            f"Tab next · Enter ok · Esc cancel"
        )
        return OverlayData(
            cursor=cur_sq,
            highlights=highlights,
            hint=hint,
        )

    def _target_info(self, cid: CreatureId, dist_ft: int) -> str:
        """Markup для HP/AC/дистанции цели; пусто если creature
        выпала из participants (теоретически невозможно, но дёшевле
        перестраховаться, чем сломать UI на гонке событий)."""
        creature = self._participants.get(cid)
        if creature is None:
            return ""
        hp = creature.hit_points
        ratio = hp.current / hp.maximum if hp.maximum else 0.0
        if ratio >= 0.5:
            hp_color = "green"
        elif ratio >= 0.25:
            hp_color = "yellow"
        else:
            hp_color = "red"
        return (
            f"[{hp_color}]HP {hp.current}/{hp.maximum}[/] "
            f"AC {creature.armor_class} "
            f"dist={dist_ft}ft"
        )


__all__ = ["TargetModeHandler"]
