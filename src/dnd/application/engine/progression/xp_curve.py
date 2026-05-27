"""XP-кривые (этап R1). Стратегия: какая кривая — задаётся сценарием.

См. docs/PROGRESSION.md §1. Быстрая кривая (fast) — дефолт MVP: короткая партия
даёт 1-й level-up через 1–2 встречи.
"""

from __future__ import annotations

from typing import ClassVar, Protocol


class XpCurve(Protocol):
    def threshold(self, level: int) -> int:
        """Суммарный XP для входа на ``level`` (level=1 → 0)."""
        ...

    def level_for_xp(self, xp: int) -> int:
        """Максимально достижимый уровень при накопленном ``xp``."""
        ...


class _TableXpCurve:
    """База: таблица суммарных порогов {level: cum_xp}."""

    _table: ClassVar[dict[int, int]] = {}

    def threshold(self, level: int) -> int:
        if level <= 1:
            return 0
        max_lvl = max(self._table)
        return self._table[min(level, max_lvl)]

    def level_for_xp(self, xp: int) -> int:
        lvl = 1
        for level, cum in sorted(self._table.items()):
            if xp >= cum:
                lvl = level
        return lvl


class FastXpCurve(_TableXpCurve):
    # суммарный XP для входа на уровень (PROGRESSION.md §1.2)
    _table: ClassVar[dict[int, int]] = {2: 100, 3: 250, 4: 500, 5: 900, 20: 900}


class StandardXpCurve(_TableXpCurve):
    _table: ClassVar[dict[int, int]] = {2: 300, 3: 900, 4: 2700, 5: 6500, 20: 6500}


class MilestoneXpCurve:
    """Уровни выдаются по событиям сценария, не по XP — level_for_xp всегда 1."""

    def threshold(self, level: int) -> int:
        return 0

    def level_for_xp(self, xp: int) -> int:
        return 1


def make_xp_curve(name: str) -> XpCurve:
    match name:
        case "fast":
            return FastXpCurve()
        case "standard":
            return StandardXpCurve()
        case "milestone":
            return MilestoneXpCurve()
        case _:
            raise ValueError(f"unknown xp_curve: {name!r}")


__all__ = [
    "FastXpCurve",
    "MilestoneXpCurve",
    "StandardXpCurve",
    "XpCurve",
    "make_xp_curve",
]
