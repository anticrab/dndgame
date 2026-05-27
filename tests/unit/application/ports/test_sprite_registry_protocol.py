"""Protocol-проверка: SpriteRegistry имеет нужную форму."""

from __future__ import annotations

from dnd.application.ports.sprite_registry import (
    SpriteCategory,
    SpriteRegistry,
)


def test_sprite_category_values() -> None:
    assert SpriteCategory.TERRAIN.value == "terrain"
    assert SpriteCategory.FEATURE.value == "feature"
    assert SpriteCategory.OBJECT.value == "object"
    assert SpriteCategory.CREATURE.value == "creature"


def test_protocol_runtime_checkable() -> None:
    class _Stub:
        def get_terrain(self, id_: str): ...
        def get_feature(self, id_: str): ...
        def list_by_category(self, c): ...

    assert isinstance(_Stub(), SpriteRegistry)
