"""Helper для построения и оценки пути движения (inline MOVE mode).

MoveAction.can_perform_against валидирует уже-построенный путь. Для
UI-preview нужен прямой chebyshev-путь от старта к курсору + расчёт
стоимости в футах с учётом difficult terrain.
"""
from __future__ import annotations

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square


def find_chebyshev_path(start: Square, target: Square) -> tuple[Square, ...]:
    """Прямой пошаговый путь по chebyshev (8-связность), БЕЗ старта.

    Не проверяет проходимость — это задача MoveAction.can_perform_against.
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


__all__ = ["find_chebyshev_path", "path_cost_ft"]
