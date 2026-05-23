"""ObjectKind — типы интерактивных объектов на карте."""
from __future__ import annotations

from enum import StrEnum


class ObjectKind(StrEnum):
    DOOR = "door"
    CHEST = "chest"
    BARREL = "barrel"
    WINDOW = "window"


__all__ = ["ObjectKind"]
