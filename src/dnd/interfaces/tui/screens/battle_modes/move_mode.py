"""MoveModeHandler — inline MOVE mode.

См. spec §4.2 и §5. Стрелки двигают cursor по карте (clamp к bounds),
путь строится через A* (find_walkable_path) с учётом стен и difficult
terrain. Confirmation/cancellation выставляют флаги
``confirmed_path`` / ``cancelled`` — BattleScreen проверяет после
on_key и выполняет переход NORMAL.

Раскраска пути (M-2): клетки до budget speed_ft — зелёные, до 2× —
жёлтые (нужен Dash), дальше — красные (overflow). MoveAction
валидирует confirm и отклонит overflow, но UI хочет показать это
заранее. Hint-строка (M-3) показывает «MOVE: cursor=(15,8)
cost=25/30 ft» — мгновенный feedback во время arrow-keys.
Красная подсветка на курсоре (M-4) — когда путь недостижим
(path == ()) для непустого смещения от старта.
"""

from __future__ import annotations

from dnd.application.engine.actions.move_path import (
    find_walkable_path,
    path_cost_ft,
)
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.protocol import (
    ModeScreenContext,
    OverlayData,
)

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
        # Кеш для overlay() — пересчитывается на каждом on_enter/on_key.
        self._budget_ft: int = 0
        self._cost_ft: int = 0
        self.confirmed_path: tuple[Square, ...] | None = None
        self.cancelled: bool = False

    def on_enter(self, screen: ModeScreenContext) -> None:
        self._start = screen._current_actor_position
        self._cursor = self._start
        self._path = ()
        self._budget_ft = screen._current_actor_speed_ft
        self._cost_ft = 0
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
                # is_alive: трупы лежат на карте, но через них можно
                # пройти. Без фильтра pathfinder уходил бы вокруг трупа
                # как от обычного существа.
                walkable = find_walkable_path(
                    bf,
                    self._start,
                    self._cursor,
                    is_alive=screen._is_alive_lookup,
                )
                self._path = walkable if walkable is not None else ()
                self._cost_ft = path_cost_ft(bf, self._path) if self._path else 0
            return True
        if key == "enter":
            # Пустой путь подтверждать нет смысла: либо это клетка
            # самого PC, либо недостижимо. MoveAction всё равно бы
            # отказал; оставим игрока в MOVE mode.
            # Overflow тоже отсекаем — MoveAction вернёт Forbidden,
            # лучше не тратить ход на гарантированно отклонённый intent.
            if self._path and self._cost_ft <= self._budget_ft * 2:
                self.confirmed_path = self._path
            return True
        if key == "escape":
            self.cancelled = True
            return True
        return False

    def overlay(self) -> OverlayData:
        styles: dict[Square, str] = {}
        cumulative: float = 0.0
        # Каждый шаг path'а добавляет cost (5 ft / 10 ft difficult);
        # не имея битфилда тут, пересчитываем равномерно: используем
        # известный итоговый cost и шаги — для UI достаточно линейного
        # распределения. Дешевле, чем тащить battlefield в overlay().
        steps = len(self._path)
        per_step = (self._cost_ft / steps) if steps else 0.0
        for sq in self._path:
            cumulative += per_step
            if cumulative <= self._budget_ft + 1e-6:
                styles[sq] = "green"
            elif cumulative <= self._budget_ft * 2 + 1e-6:
                styles[sq] = "yellow"
            else:
                styles[sq] = "red"

        highlights: dict[Square, str] = {}
        # Невалидная цель — курсор НЕ совпадает с PC, путь пустой.
        unreachable = self._cursor != self._start and not self._path
        if unreachable:
            highlights[self._cursor] = "red reverse"

        hint = self._format_hint(unreachable)
        return OverlayData(
            cursor=self._cursor,
            highlights=highlights,
            path_preview=self._path,
            path_styles=styles,
            hint=hint,
        )

    def _format_hint(self, unreachable: bool) -> str:
        if self._cursor == self._start:
            return f"MOVE: budget {self._budget_ft} ft (стрелки → выбрать клетку)"
        if unreachable:
            return f"MOVE: ({self._cursor.x},{self._cursor.y}) — недостижимо"
        cost = self._cost_ft
        budget = self._budget_ft
        if cost <= budget:
            tag = "[green]ok[/]"
        elif cost <= budget * 2:
            tag = f"[yellow]нужен Dash (+{cost - budget} ft)[/]"
        else:
            tag = "[red]за пределами Dash[/]"
        return f"MOVE: ({self._cursor.x},{self._cursor.y}) cost={cost}/{budget} ft {tag}"


__all__ = ["MoveModeHandler"]
