"""Helper для построения и оценки пути движения (inline MOVE mode).

MoveAction.can_perform_against валидирует уже-построенный путь. Для
UI-preview сначала строим chebyshev-«воздушную» линию (для тестов и
fallback'а), затем настоящий обходной маршрут через
:func:`find_walkable_path` — Dijkstra по 8-связному графу с весами
5 ft / 10 ft (difficult) и пропуском непроходимых клеток.
"""
from __future__ import annotations

import heapq

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square

_NEIGHBOURS: tuple[tuple[int, int], ...] = (
    (-1, -1), (-1, 0), (-1, 1),
    (0, -1),           (0, 1),
    (1, -1),  (1, 0),  (1, 1),
)


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


def find_walkable_path(
    battlefield: Battlefield,
    start: Square,
    target: Square,
) -> tuple[Square, ...] | None:
    """Кратчайший проходимый путь от ``start`` до ``target`` (без старта).

    Dijkstra по 8-связному графу. Веса:
    * 5 ft за обычную проходимую клетку,
    * 10 ft за difficult terrain.

    Пропускаются клетки:
    * за границей карты;
    * непроходимый terrain (стена, вода без bridge и т.п.);
    * содержащие другое существо (кроме самого target — туда можно
      «прийти на 5 ft», но в MOVE intent'е этого пока нет, поэтому
      на занятую клетку маршрут не строится).

    Возвращает None если цель недостижима (нет пути или непроходимый
    target).
    """
    if start == target:
        return ()
    if not battlefield.in_bounds(target):
        return None
    if not battlefield.terrain_at(target).passable:
        return None
    if battlefield.creatures_at(target):
        return None

    dist: dict[Square, int] = {start: 0}
    prev: dict[Square, Square] = {}
    # heap items: (distance, x, y) — x, y нужны как tie-breakers
    # (Square не сравнима), а не для логики
    pq: list[tuple[int, int, int]] = [(0, start.x, start.y)]
    while pq:
        d, x, y = heapq.heappop(pq)
        cur = Square(x, y)
        if cur == target:
            break
        if d > dist.get(cur, 10**9):
            continue
        for dx, dy in _NEIGHBOURS:
            nb = Square(x + dx, y + dy)
            if not battlefield.in_bounds(nb):
                continue
            terrain = battlefield.terrain_at(nb)
            if not terrain.passable:
                continue
            if not battlefield.passable_between(cur, nb):
                continue
            if battlefield.creatures_at(nb):
                continue
            cost = 10 if terrain.difficult else 5
            nd = d + cost
            if nd < dist.get(nb, 10**9):
                dist[nb] = nd
                prev[nb] = cur
                heapq.heappush(pq, (nd, nb.x, nb.y))

    if target not in dist:
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
