"""YamlMapRepository: load/save/list карт в data/content/maps/{id}.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.dto.map_dto import MapDocument, MapTileDoc
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository


def test_save_then_load_roundtrip(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    doc = MapDocument(
        id="test",
        name="Test",
        width=3,
        height=3,
        tiles=(MapTileDoc(x=0, y=0, base="floor"),),
        objects=(),
    )
    repo.save(doc)
    loaded = repo.load("test")
    assert loaded == doc


def test_list_ids_returns_saved(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    repo.save(MapDocument(id="a", name="A", width=2, height=2, tiles=(), objects=()))
    repo.save(MapDocument(id="b", name="B", width=2, height=2, tiles=(), objects=()))
    assert set(repo.list_ids()) == {"a", "b"}


def test_load_missing_raises(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    with pytest.raises(KeyError, match="nope"):
        repo.load("nope")


def test_delete_removes_file(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    repo.save(MapDocument(id="x", name="X", width=2, height=2, tiles=(), objects=()))
    repo.delete("x")
    assert "x" not in repo.list_ids()


def test_delete_missing_is_noop(tmp_path: Path) -> None:
    repo = YamlMapRepository(tmp_path)
    repo.delete("does_not_exist")  # no exception


def test_creates_dir_if_missing(tmp_path: Path) -> None:
    new_dir = tmp_path / "fresh_maps"
    assert not new_dir.exists()
    YamlMapRepository(new_dir)
    assert new_dir.is_dir()


def test_implements_protocol() -> None:
    import tempfile
    from pathlib import Path

    from dnd.application.ports.map_repository import MapRepository

    with tempfile.TemporaryDirectory() as d:
        assert isinstance(YamlMapRepository(Path(d)), MapRepository)
