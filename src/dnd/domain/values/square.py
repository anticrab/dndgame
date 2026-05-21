"""Квадрат боевой карты — value-object для позиционирования.

Решение по ADR-0002: квадратная сетка, 1 клетка = 5 футов, 8 соседей
(4 ортогональных + 4 диагональных), дистанция по Chebyshev — каждая
клетка считается 5 футов независимо от диагонали (правило книги 2024).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

_FEET_PER_SQUARE: Final[int] = 5


@dataclass(frozen=True, slots=True, order=True)
class Square:
    """Координата клетки боевой карты.

    Иммутабельная. ``order=True`` даёт сравнение по `(x, y)` —
    удобно для сортировки и тестов.
    """

    x: int
    y: int

    def distance_to(self, other: Square) -> int:
        """Дистанция в **клетках** (Chebyshev).

        Соответствует правилу книги «каждая клетка движения = 5 футов».
        В футах — :meth:`distance_to_feet`.
        """
        return max(abs(self.x - other.x), abs(self.y - other.y))

    def distance_to_feet(self, other: Square) -> int:
        """Дистанция в футах (для расчёта дальности заклинаний, оружия)."""
        return self.distance_to(other) * _FEET_PER_SQUARE

    def is_adjacent(self, other: Square) -> bool:
        """Соседняя ли клетка (8-соседство, исключая саму клетку)."""
        return self != other and self.distance_to(other) == 1

    def step(self, dx: int, dy: int) -> Square:
        """Сместиться на ``(dx, dy)``. Можно использовать для пути."""
        return Square(self.x + dx, self.y + dy)

    def neighbors(self) -> tuple[Square, ...]:
        """8 соседних клеток (без диагональных дубликатов, без самой клетки)."""
        return tuple(
            Square(self.x + dx, self.y + dy)
            for dy in (-1, 0, 1)
            for dx in (-1, 0, 1)
            if not (dx == 0 and dy == 0)
        )

    def chebyshev_ring(self, radius: int) -> tuple[Square, ...]:
        """Кольцо клеток на Chebyshev-расстоянии ровно ``radius``.

        Полезно для расчёта зоны угрозы (`radius=1`) и для AoE-эффектов
        вокруг клетки (например, «квадрат 15×15 фут» = `radius=1`,
        включая центр).
        """
        if radius < 0:
            raise ValueError(f"radius must be >= 0, got {radius}")
        if radius == 0:
            return (self,)
        # Кольцо — это разница между двумя квадратами: внешний и внутренний.
        return tuple(
            Square(self.x + dx, self.y + dy)
            for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
            if max(abs(dx), abs(dy)) == radius
        )

    def chebyshev_disk(self, radius: int) -> tuple[Square, ...]:
        """Все клетки на Chebyshev-расстоянии **<=** ``radius``, включая центр.

        Это все клетки внутри квадрата ``(2r+1) × (2r+1)``. Используется
        для AoE «cube» эффектов из книги.
        """
        if radius < 0:
            raise ValueError(f"radius must be >= 0, got {radius}")
        return tuple(
            Square(self.x + dx, self.y + dy)
            for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
        )
