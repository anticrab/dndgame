"""Подменный ГПСЧ для тестов: возвращает заранее заданные значения."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from dnd.domain.ports.rng import RNG


class ScriptedRNG(RNG):
    """Возвращает броски из очереди.

    Удобен для проверки конкретных веток правил («что если выпадет натуральная
    20, потом 1, потом 7»). Если кости кончились — поднимает ``IndexError``,
    чтобы баг в тесте проявился сразу. Если значение вне диапазона ``[1, sides]``
    — ``ValueError``.
    """

    def __init__(self, rolls: Iterable[int]) -> None:
        self._rolls: deque[int] = deque(rolls)

    def roll(self, sides: int) -> int:
        if not self._rolls:
            raise IndexError("ScriptedRNG: scripted rolls exhausted")
        value = self._rolls.popleft()
        if not 1 <= value <= sides:
            raise ValueError(f"ScriptedRNG: value {value} is out of range 1..{sides}")
        return value
