"""ObjectKind — типы интерактивных объектов на карте."""
from __future__ import annotations

from enum import StrEnum


class ObjectKind(StrEnum):
    DOOR = "door"
    CHEST = "chest"
    BARREL = "barrel"
    WINDOW = "window"
    CORPSE = "corpse"  # труп павшего NPC: контейнер лута (Q-8)


__all__ = ["ObjectKind"]
