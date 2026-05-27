"""JsonMapRepository — карты в data/content/maps/{id}.json."""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.map_dto import MapDocument, MapTileDoc
from dnd.infrastructure.content.json_map_repository import JsonMapRepository


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    repo = JsonMapRepository(tmp_path)
    doc = MapDocument(
        id="test",
        name="Test",
        width=3,
        height=3,
        tiles=(MapTileDoc(x=0, y=0, base="floor"),),
        objects=(),
    )
    repo.save(doc)
    assert repo.load("test") == doc


def test_list_ids(tmp_path: Path) -> None:
    repo = JsonMapRepository(tmp_path)
    repo.save(MapDocument(id="a", name="A", width=2, height=2, tiles=(), objects=()))
    repo.save(MapDocument(id="b", name="B", width=2, height=2, tiles=(), objects=()))
    assert set(repo.list_ids()) == {"a", "b"}


def test_load_missing_raises(tmp_path: Path) -> None:
    repo = JsonMapRepository(tmp_path)
    with pytest.raises(KeyError, match="nope"):
        repo.load("nope")


def test_delete(tmp_path: Path) -> None:
    repo = JsonMapRepository(tmp_path)
    repo.save(MapDocument(id="x", name="X", width=2, height=2, tiles=(), objects=()))
    repo.delete("x")
    assert "x" not in repo.list_ids()


def test_delete_missing_noop(tmp_path: Path) -> None:
    repo = JsonMapRepository(tmp_path)
    repo.delete("nope")


def test_creates_dir(tmp_path: Path) -> None:
    d = tmp_path / "fresh"
    assert not d.exists()
    JsonMapRepository(d)
    assert d.is_dir()


def test_implements_protocol(tmp_path: Path) -> None:
    from dnd.application.ports.map_repository import MapRepository

    assert isinstance(JsonMapRepository(tmp_path), MapRepository)


def test_cross_repo_roundtrip(tmp_path: Path) -> None:
    """YamlMap save -> JsonMap load (через model_dump): должны быть равны."""
    from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository

    doc = MapDocument(
        id="x",
        name="X",
        width=4,
        height=3,
        tiles=(MapTileDoc(x=1, y=1, base="grass"),),
        objects=(),
    )
    yrepo = YamlMapRepository(tmp_path / "y")
    jrepo = JsonMapRepository(tmp_path / "j")
    yrepo.save(doc)
    yloaded = yrepo.load("x")
    jrepo.save(yloaded)
    jloaded = jrepo.load("x")
    assert jloaded == doc
