"""Реальный ГПСЧ поверх ``random.Random``."""

from __future__ import annotations

import random

from dnd.application.ports.rng import RNG


class RealRNG(RNG):
    """Тонкая обёртка над ``random.Random`` для соответствия порту."""

    def __init__(self, seed: int | None = None) -> None:
        self._random = random.Random(seed)

    def roll(self, sides: int) -> int:
        if sides < 1:
            raise ValueError(f"число граней должно быть ≥ 1, получено {sides}")
        return self._random.randint(1, sides)

    def random(self) -> float:
        return self._random.random()
