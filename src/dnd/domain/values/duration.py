"""Длительность игрового эффекта (X0). Канон — раунд (PHB-2024: 1 раунд = 6 c;
1 мин = 10 раундов; 1 ч = 600). Минуты/часы конвертируются в раунды в одном
месте — потребители (часы, трекер) работают только с раундами.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


class DurationUnit(StrEnum):
    INSTANT = "instant"
    ROUNDS = "rounds"
    MINUTES = "minutes"
    HOURS = "hours"
    CONCENTRATION = "concentration"  # пока держится концентрация (+ потолок мин)
    UNTIL_ENCOUNTER_END = "until_encounter_end"
    PERMANENT = "permanent"


@dataclass(frozen=True, slots=True)
class Duration:
    """Длительность эффекта. ``amount``: число для ROUNDS/MINUTES/HOURS; потолок
    в минутах для CONCENTRATION (0 = без счётного потолка)."""

    unit: DurationUnit
    amount: int = 0

    ROUNDS_PER_MINUTE: ClassVar[int] = 10
    ROUNDS_PER_HOUR: ClassVar[int] = 600

    def __post_init__(self) -> None:
        if (
            self.unit in (DurationUnit.ROUNDS, DurationUnit.MINUTES, DurationUnit.HOURS)
            and self.amount <= 0
        ):
            raise ValueError(f"{self.unit} requires amount > 0, got {self.amount}")
        if self.amount < 0:
            raise ValueError(f"duration amount must be >= 0, got {self.amount}")

    def to_rounds(self) -> int | None:
        """Длительность в раундах. ``None`` — нет счётного предела
        (PERMANENT / UNTIL_ENCOUNTER_END / CONCENTRATION без потолка)."""
        match self.unit:
            case DurationUnit.INSTANT:
                return 0
            case DurationUnit.ROUNDS:
                return self.amount
            case DurationUnit.MINUTES:
                return self.amount * self.ROUNDS_PER_MINUTE
            case DurationUnit.HOURS:
                return self.amount * self.ROUNDS_PER_HOUR
            case DurationUnit.CONCENTRATION:
                return self.amount * self.ROUNDS_PER_MINUTE if self.amount > 0 else None
            case _:
                return None

    @classmethod
    def instant(cls) -> Duration:
        return cls(DurationUnit.INSTANT)

    @classmethod
    def rounds(cls, n: int) -> Duration:
        return cls(DurationUnit.ROUNDS, n)

    @classmethod
    def minutes(cls, n: int) -> Duration:
        return cls(DurationUnit.MINUTES, n)

    @classmethod
    def hours(cls, n: int) -> Duration:
        return cls(DurationUnit.HOURS, n)

    @classmethod
    def concentration(cls, cap_min: int = 0) -> Duration:
        return cls(DurationUnit.CONCENTRATION, cap_min)


__all__ = ["Duration", "DurationUnit"]
