"""AreaModeHandler — inline AREA mode (выбор зоны AoE-заклинания, этап P2).

Два под-режима по ``origin`` заклинания:
* **AT_POINT**: курсор свободно двигается по полю (clamp в границы + дальность),
  превью подсвечивает задетые клетки. Enter → ``confirmed_point``.
* **FROM_CASTER**: Tab/Shift+Tab циклят 8 направлений (стрелки — ортогональные),
  превью рисует форму от кастера. Enter → ``confirmed_direction``.

Esc → ``cancelled``. Превью клеток считается тем же :class:`AreaShapeRegistry`,
что и боевой резолвинг — UI и движок не расходятся.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dnd.domain.values.direction import Direction
from dnd.domain.values.spell import OriginMode
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.protocol import (
    ModeScreenContext,
    OverlayData,
)

if TYPE_CHECKING:
    from dnd.application.engine.spells.area import AreaShapeRegistry
    from dnd.domain.entities.battlefield import Battlefield
    from dnd.domain.values.spell import TargetingSpec

# Порядок цикла направлений (по часовой от N). Стрелки → ортогональные.
_DIR_CYCLE: tuple[Direction, ...] = (
    Direction.N,
    Direction.NE,
    Direction.E,
    Direction.SE,
    Direction.S,
    Direction.SW,
    Direction.W,
    Direction.NW,
)
_ARROW_DIR: dict[str, Direction] = {
    "up": Direction.N,
    "down": Direction.S,
    "left": Direction.W,
    "right": Direction.E,
}
_ARROW_DELTA: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


class AreaModeHandler:
    def __init__(self) -> None:
        self._spec: TargetingSpec | None = None
        self._bf: Battlefield | None = None
        self._actor_pos: Square = Square(0, 0)
        self._range_sq: int = 0
        self._registry: AreaShapeRegistry | None = None
        # AT_POINT:
        self._cursor: Square = Square(0, 0)
        # FROM_CASTER:
        self._dir_idx: int = 2  # E по умолчанию
        self.confirmed_point: Square | None = None
        self.confirmed_direction: Direction | None = None
        self.cancelled: bool = False

    @property
    def _at_point(self) -> bool:
        return self._spec is not None and self._spec.origin is OriginMode.AT_POINT

    def on_enter(self, screen: ModeScreenContext) -> None:
        self._spec = screen._pending_area_spec
        self._bf = screen._current_battlefield
        self._actor_pos = screen._current_actor_position
        self._range_sq = screen._pending_area_range_ft // 5
        self._registry = screen._area_registry
        self._cursor = self._actor_pos
        self._dir_idx = 2
        self.confirmed_point = None
        self.confirmed_direction = None
        self.cancelled = False

    def on_exit(self, screen: ModeScreenContext) -> None:
        self._spec = None
        self._bf = None
        self._registry = None

    def on_key(self, screen: ModeScreenContext, key: str) -> bool:
        if self._spec is None:
            return False
        if key == "escape":
            self.cancelled = True
            return True
        if self._at_point:
            return self._on_key_point(key)
        return self._on_key_direction(key)

    def _on_key_point(self, key: str) -> bool:
        if key in _ARROW_DELTA and self._bf is not None:
            dx, dy = _ARROW_DELTA[key]
            nxt = Square(self._cursor.x + dx, self._cursor.y + dy)
            # clamp: в границах поля и в пределах дальности от кастера.
            if self._bf.in_bounds(nxt) and self._in_range(nxt):
                self._cursor = nxt
            return True
        if key == "enter":
            self.confirmed_point = self._cursor
            return True
        return False

    def _on_key_direction(self, key: str) -> bool:
        if key == "tab":
            self._dir_idx = (self._dir_idx + 1) % len(_DIR_CYCLE)
            return True
        if key == "shift+tab":
            self._dir_idx = (self._dir_idx - 1) % len(_DIR_CYCLE)
            return True
        if key in _ARROW_DIR:
            self._dir_idx = _DIR_CYCLE.index(_ARROW_DIR[key])
            return True
        if key == "enter":
            self.confirmed_direction = _DIR_CYCLE[self._dir_idx]
            return True
        return False

    def _in_range(self, sq: Square) -> bool:
        cheb = max(abs(sq.x - self._actor_pos.x), abs(sq.y - self._actor_pos.y))
        return cheb <= self._range_sq

    def _preview(self) -> frozenset[Square]:
        if self._spec is None or self._bf is None or self._registry is None:
            return frozenset()
        assert self._spec.shape is not None
        resolver = self._registry.get(self._spec.shape)
        if self._at_point:
            return resolver.squares(self._cursor, None, self._spec, self._bf)
        return resolver.squares(self._actor_pos, _DIR_CYCLE[self._dir_idx], self._spec, self._bf)

    def overlay(self) -> OverlayData:
        if self._spec is None:
            return OverlayData()
        highlights = {sq: "red" for sq in self._preview()}
        if self._at_point:
            highlights[self._cursor] = "magenta reverse"
            hint = (
                f"AREA: точка ({self._cursor.x},{self._cursor.y}) — "
                f"стрелки двигают · Enter каст · Esc отмена"
            )
            cursor = self._cursor
        else:
            d = _DIR_CYCLE[self._dir_idx]
            hint = f"AREA: направление {d.value.upper()} — Tab/стрелки · Enter каст · Esc отмена"
            cursor = None
        return OverlayData(cursor=cursor, highlights=highlights, hint=hint)


__all__ = ["AreaModeHandler"]
