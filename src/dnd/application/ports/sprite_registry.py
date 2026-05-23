"""Port: реестр sprite-content.

Реализация — YamlSpriteRegistry в infrastructure (см. K2-T2).
Будущие реализации (SqliteSpriteRegistry, RemoteSpriteRegistry) —
без правок engine.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable

from dnd.domain.values.sprite_meta import FeatureKind, TerrainBase


class SpriteCategory(StrEnum):
    TERRAIN = "terrain"
    FEATURE = "feature"
    OBJECT = "object"
    CREATURE = "creature"


@runtime_checkable
class SpriteRegistry(Protocol):
    def get_terrain(self, id_: str) -> TerrainBase: ...

    def get_feature(self, id_: str) -> FeatureKind: ...

    def list_by_category(
        self, category: SpriteCategory
    ) -> tuple[TerrainBase | FeatureKind, ...]: ...


__all__ = ["SpriteCategory", "SpriteRegistry"]
