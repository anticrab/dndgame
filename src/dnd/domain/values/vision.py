"""Виды зрения существа.

Книга 2024, §«Зрение и свет». Влияет на:

* какие клетки существо видит ясно при разном освещении;
* применение помехи на тесты в полу-обскурении;
* возможность видеть невидимых (только TRUESIGHT).

Существо может иметь сразу несколько типов зрения (эльф —
``(NORMAL, DARKVISION_60)``). Радиус указан в футах.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class VisionKind(StrEnum):
    """Категории зрения."""

    NORMAL = "normal"  # обычное зрение: BRIGHT — ясно, DIM — помеха, DARK — нет
    DARKVISION = "darkvision"  # видит DARK как DIM в радиусе
    BLINDSIGHT = "blindsight"  # видит без зрения (эхо, запах) в радиусе
    TRUESIGHT = "truesight"  # видит сквозь иллюзии и невидимость


@dataclass(frozen=True, slots=True)
class Vision:
    """Один тип зрения с радиусом действия."""

    kind: VisionKind
    radius_ft: int = 0
    """Для NORMAL радиус не используется (зрение неограниченное при
    нормальном освещении). Для DARKVISION/BLINDSIGHT/TRUESIGHT — радиус в футах."""

    def __post_init__(self) -> None:
        if self.radius_ft < 0:
            raise ValueError(f"vision radius must be >= 0, got {self.radius_ft}")
        needs_positive = self.kind in {
            VisionKind.DARKVISION,
            VisionKind.BLINDSIGHT,
            VisionKind.TRUESIGHT,
        }
        if needs_positive and self.radius_ft <= 0:
            raise ValueError(f"{self.kind} requires positive radius_ft, got {self.radius_ft}")


NORMAL_VISION: Vision = Vision(kind=VisionKind.NORMAL, radius_ft=0)
"""Удобный экземпляр для большинства существ — обычное зрение."""
