"""Реальный ГПСЧ поверх ``random.Random``."""

from __future__ import annotations

import random

from dnd.domain.ports.rng import RNG


class RealRNG(RNG):
    """Тонкая обёртка над ``random.Random`` для соответствия порту.

    Изоляция через композицию (не наследование) гарантирует, что
    ``random.seed(...)`` глобально нас не затронет.
    """

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def roll(self, sides: int) -> int:
        if sides < 1:
            raise ValueError(f"die sides must be >= 1, got {sides}")
        return self._random.randint(1, sides)
