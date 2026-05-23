"""MoveModeHandler — inline MOVE mode.

См. spec §4.2 и §5. Стрелки двигают cursor по карте (clamp к bounds),
path рисуется chebyshev'ом. Confirmation/cancellation выставляют
флаги `confirmed_path` / `cancelled` — BattleScreen проверяет после
on_key и выполняет переход NORMAL.
"""
from __future__ import annotations

from dnd.application.engine.actions.move_path import find_walkable_path
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.protocol import ModeScreenContext

_ARROW_DELTAS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}


class MoveModeHandler:
    """Состояние MOVE: cursor + path preview. Confirmation через флаги."""

    def __init__(self) -> None:
        self._start: Square = Square(0, 0)
        self._cursor: Square = Square(0, 0)
        self._path: tuple[Square, ...] = ()
        self.confirmed_path: tuple[Square, ...] | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: ModeScreenContext) -> None:
        self._start = screen._current_actor_position
        self._cursor = self._start
        self._path = ()
        self.confirmed_path = None
        self.cancelled = False

    def on_exit(self, screen: ModeScreenContext) -> None:
        self._path = ()

    def on_key(self, screen: ModeScreenContext, key: str) -> bool:
        if key in _ARROW_DELTAS:
            dx, dy = _ARROW_DELTAS[key]
            new = Square(self._cursor.x + dx, self._cursor.y + dy)
            # BattleScreen инвариант: enter_mode(MOVE) случается только
            # из action_intent_move, где battlefield уже установлен.
            assert screen._current_battlefield is not None
            bf = screen._current_battlefield
            if 0 <= new.x < bf.width and 0 <= new.y < bf.height:
                self._cursor = new
                # Dijkstra с учётом стен и difficult terrain;
                # None означает недостижимую клетку — preview пустой.
                walkable = find_walkable_path(bf, self._start, self._cursor)
                self._path = walkable if walkable is not None else ()
            return True
        if key == "enter":
            # Пустой путь подтверждать нет смысла — это либо клетка
            # самого PC, либо недостижимая цель. В обоих случаях
            # action MoveAction.can_perform_against всё равно отказал бы.
            # Оставим игрока в MOVE mode — пусть выберет другую клетку.
            if self._path:
                self.confirmed_path = self._path
            return True
        if key == "escape":
            self.cancelled = True
            return True
        return False

    def overlay_data(
        self,
    ) -> tuple[Square | None, dict[Square, str], tuple[Square, ...]]:
        return (self._cursor, {}, self._path)


__all__ = ["MoveModeHandler"]
