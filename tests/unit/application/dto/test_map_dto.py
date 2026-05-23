"""MapDocument — pydantic DTO для YAML/JSON формата карт.

Формат: { id, name, width, height, tiles[], objects[] }
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from dnd.application.dto.map_dto import (
    MapDocument,
    MapObjectDoc,
    MapTileDoc,
)


def test_minimal_map_document() -> None:
    doc = MapDocument(
        id="test_map",
        name="Test",
        width=5,
        height=5,
        tiles=(
            MapTileDoc(x=0, y=0, base="floor"),
            MapTileDoc(x=1, y=0, base="stone", features=("wall_v",)),
        ),
        objects=(),
    )
    assert doc.width == 5
    assert len(doc.tiles) == 2


def test_object_doc_with_state() -> None:
    obj = MapObjectDoc(
        id="door-1",
        kind="door",
        x=3,
        y=2,
        state={"open": False, "locked": True, "hp": 10, "ac": 13},
    )
    assert obj.state["locked"] is True


def test_negative_dim_rejected() -> None:
    with pytest.raises(ValidationError):
        MapDocument(id="x", name="x", width=0, height=5, tiles=(), objects=())


def test_tile_out_of_bounds_rejected() -> None:
    with pytest.raises(ValueError, match="out of bounds"):
        MapDocument(
            id="x", name="x", width=3, height=3,
            tiles=(MapTileDoc(x=5, y=0, base="floor"),),
            objects=(),
        )


def test_object_pos_out_of_bounds_rejected() -> None:
    with pytest.raises(ValueError, match="out of bounds"):
        MapDocument(
            id="x", name="x", width=3, height=3,
            tiles=(),
            objects=(MapObjectDoc(id="d", kind="door", x=10, y=0, state={}),),
        )


def test_map_document_frozen() -> None:
    doc = MapDocument(id="x", name="x", width=3, height=3, tiles=(), objects=())
    with pytest.raises(ValidationError):
        doc.width = 5  # type: ignore[misc]
