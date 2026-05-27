"""Helper для построения и оценки пути движения (inline MOVE mode).

MoveAction.can_perform_against валидирует уже-построенный путь. Для
UI-preview сначала строим chebyshev-«воздушную» линию (для тестов и
fallback'а), затем настоящий обходной маршрут через
:func:`find_walkable_path` — Dijkstra по 8-связному графу с весами
5 ft / 10 ft (difficult) и пропуском непроходимых клеток.
"""

from __future__ import annotations

import heapq
from collections.abc import Callable

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square

_NEIGHBOURS: tuple[tuple[int, int], ...] = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def _cell_blocked_by_creatures(
    battlefield: Battlefield,
    sq: Square,
    is_alive: Callable[[CreatureId], bool] | None,
) -> bool:
    """True если на клетке хоть одно ЖИВОЕ существо. Мёртвые
    (если фильтр передан) рассматриваются как «труп лежит, можно
    переступить» — DM-rule из PHB: prone bodies are difficult
    terrain, но для MVP считаем их полностью проходимыми.

    При ``is_alive is None`` ведёт себя как раньше — любое существо
    блокирует (backward compat для тестов и старых call-sites)."""
    occupants = battlefield.creatures_at(sq)
    if not occupants:
        return False
    if is_alive is None:
        return True
    return any(is_alive(cid) for cid in occupants)


def find_chebyshev_path(start: Square, target: Square) -> tuple[Square, ...]:
    """Прямой пошаговый путь по chebyshev (8-связность), БЕЗ старта.

    Не проверяет проходимость — это задача MoveAction.can_perform_against
    и :func:`find_walkable_path` (для UI preview).
    """
    if start == target:
        return ()
    path: list[Square] = []
    cur = start
    while cur != target:
        dx = (target.x > cur.x) - (target.x < cur.x)
        dy = (target.y > cur.y) - (target.y < cur.y)
        cur = Square(cur.x + dx, cur.y + dy)
        path.append(cur)
    return tuple(path)


def _chebyshev_walkable(
    battlefield: Battlefield,
    start: Square,
    path: tuple[Square, ...],
    is_alive: Callable[[CreatureId], bool] | None,
) -> bool:
    """True если каждый шаг chebyshev-пути проходим (terrain + creatures
    + passable_between). Пустой path считаем «проходимым» тривиально."""
    cur = start
    for nb in path:
        if not battlefield.in_bounds(nb):
            return False
        if not battlefield.terrain_at(nb).passable:
            return False
        if not battlefield.passable_between(cur, nb):
            return False
        if _cell_blocked_by_creatures(battlefield, nb, is_alive):
            return False
        cur = nb
    return True


def find_walkable_path(
    battlefield: Battlefield,
    start: Square,
    target: Square,
    *,
    is_alive: Callable[[CreatureId], bool] | None = None,
) -> tuple[Square, ...] | None:
    """Кратчайший проходимый путь от ``start`` до ``target`` (без старта).

    Алгоритм:

    1. **Fast-path** — пробуем прямой chebyshev (8-связная «воздушная»
       линия). Если он целиком проходим — возвращаем его. Это
       избавляет UI от «странных» обходных путей, когда препятствий
       нет: при равной стоимости Dijkstra может выбрать боковой
       маршрут, и человеку это режет глаз.

    2. **A\\*** (informed Dijkstra) по 8-связному графу. Веса 5 ft /
       10 ft (difficult); эвристика — chebyshev-расстояние × 5 ft.
       Tie-breaker: при равном ``f = g + h`` предпочитается
       наименьший ``h`` (ближе к цели) → меньше «зигзагов».

    Пропускаются клетки за границей карты, непроходимые
    (стена/вода/...) и занятые другими существами.

    Возвращает None если цель недостижима или непроходима.
    """
    if start == target:
        return ()
    if not battlefield.in_bounds(target):
        return None
    if not battlefield.terrain_at(target).passable:
        return None
    if _cell_blocked_by_creatures(battlefield, target, is_alive):
        return None

    direct = find_chebyshev_path(start, target)
    if _chebyshev_walkable(battlefield, start, direct, is_alive):
        return direct

    def _h(sq: Square) -> int:
        # chebyshev-расстояние × минимальная стоимость шага.
        return 5 * max(abs(sq.x - target.x), abs(sq.y - target.y))

    def _cross_bias(sq: Square) -> int:
        # «Отклонение от прямой start→target»: |(sq - target) ×
        # (start - target)|. Чем меньше — тем ближе клетка к
        # воображаемой линии PC→цель. Используется как tie-breaker
        # внутри equal-cost paths — это не меняет optimality
        # Dijkstra'и, но делает обходные пути визуально менее
        # «горбатыми» (UX-репорт «странно обходит стену сверху»).
        dx1 = sq.x - target.x
        dy1 = sq.y - target.y
        dx2 = start.x - target.x
        dy2 = start.y - target.y
        return abs(dx1 * dy2 - dx2 * dy1)

    g_score: dict[Square, int] = {start: 0}
    prev: dict[Square, Square] = {}
    # heap items: (f, cross_bias, h, x, y).
    # 1. Primary order — f = g + h (Dijkstra/A* optimality).
    # 2. Tie-breaker — cross_bias (прямее = раньше).
    # 3. Затем h (ближе к цели), затем (x, y) для детерминизма.
    pq: list[tuple[int, int, int, int, int]] = [
        (_h(start), _cross_bias(start), _h(start), start.x, start.y),
    ]
    while pq:
        _, _, _, x, y = heapq.heappop(pq)
        cur = Square(x, y)
        if cur == target:
            break
        g_cur = g_score[cur]
        for dx, dy in _NEIGHBOURS:
            nb = Square(x + dx, y + dy)
            if not battlefield.in_bounds(nb):
                continue
            terrain = battlefield.terrain_at(nb)
            if not terrain.passable:
                continue
            if not battlefield.passable_between(cur, nb):
                continue
            # CRITICAL fix: A* main loop тоже должен уважать is_alive,
            # иначе труп блокирует обходной маршрут (fast-path выше
            # фильтрует правильно, а Dijkstra — нет). Аудит code-review
            # после O-5: репродуцировано на крипте.
            if _cell_blocked_by_creatures(battlefield, nb, is_alive):
                continue
            cost = 10 if terrain.difficult else 5
            ng = g_cur + cost
            if ng < g_score.get(nb, 10**9):
                g_score[nb] = ng
                prev[nb] = cur
                h_nb = _h(nb)
                heapq.heappush(pq, (ng + h_nb, _cross_bias(nb), h_nb, nb.x, nb.y))

    if target not in g_score:
        return None
    path: list[Square] = []
    node = target
    while node != start:
        path.append(node)
        node = prev[node]
    path.reverse()
    return tuple(path)


def path_cost_ft(battlefield: Battlefield, path: tuple[Square, ...]) -> int:
    """Стоимость пути в футах: 5 ft / step, ×2 на difficult terrain.

    Не учитывает provoked attacks / disengage — это уровень domain.
    Не валидирует bounds — вызывающий код передаёт уже clamped path.
    """
    total = 0
    for sq in path:
        terrain = battlefield.terrain_at(sq)
        total += 10 if terrain.difficult else 5
    return total


__all__ = ["find_chebyshev_path", "find_walkable_path", "path_cost_ft"]
