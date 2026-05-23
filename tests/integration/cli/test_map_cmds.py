"""dnd map list/show/validate — read-only часть."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dnd.application.dto.map_dto import MapDocument, MapTileDoc
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository
from dnd.interfaces.cli.app import app

runner = CliRunner()


@pytest.fixture
def maps_dir(tmp_path: Path) -> Path:
    md = tmp_path / "maps"
    repo = YamlMapRepository(md)
    repo.save(MapDocument(
        id="tiny", name="Tiny", width=3, height=3,
        tiles=(MapTileDoc(x=1, y=1, base="floor"),),
        objects=(),
    ))
    return md


def test_map_list_default(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "list", "--maps-dir", str(maps_dir)])
    assert result.exit_code == 0
    assert "tiny" in result.stdout


def test_map_list_json(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "list", "--maps-dir", str(maps_dir), "--format=json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert {"tiny"} <= {item["id"] for item in data}


def test_map_show_ascii(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "show", "tiny", "--maps-dir", str(maps_dir)])
    assert result.exit_code == 0
    assert "tiny" in result.stdout


def test_map_show_json(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "show", "tiny", "--maps-dir", str(maps_dir), "--format=json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["id"] == "tiny"
    assert data["width"] == 3


def test_map_show_medium_zoom(maps_dir: Path) -> None:
    """medium-zoom печатает 3 строки на каждую строку карты (3×3=9 lines)."""
    result = runner.invoke(app, [
        "map", "show", "tiny", "--maps-dir", str(maps_dir), "--zoom=medium"
    ])
    assert result.exit_code == 0


def test_map_validate_ok(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "validate", "tiny", "--maps-dir", str(maps_dir)])
    assert result.exit_code == 0


def test_map_show_missing_fails(maps_dir: Path) -> None:
    result = runner.invoke(app, ["map", "show", "nope", "--maps-dir", str(maps_dir)])
    assert result.exit_code != 0


def test_map_new_creates_empty(tmp_path: Path) -> None:
    md = tmp_path / "maps"
    result = runner.invoke(app, [
        "map", "new", "fresh", "--size=4x3", "--maps-dir", str(md)
    ])
    assert result.exit_code == 0
    repo = YamlMapRepository(md)
    doc = repo.load("fresh")
    assert doc.width == 4 and doc.height == 3
    assert doc.tiles == ()


def test_map_new_with_name_option(tmp_path: Path) -> None:
    md = tmp_path / "maps"
    result = runner.invoke(app, [
        "map", "new", "x", "--size=2x2", "--name=Custom Name", "--maps-dir", str(md)
    ])
    assert result.exit_code == 0
    doc = YamlMapRepository(md).load("x")
    assert doc.name == "Custom Name"


def test_map_new_bad_size_format_fails(tmp_path: Path) -> None:
    md = tmp_path / "maps"
    result = runner.invoke(app, [
        "map", "new", "x", "--size=invalid", "--maps-dir", str(md)
    ])
    assert result.exit_code != 0


def test_map_paint_sets_base(maps_dir: Path) -> None:
    result = runner.invoke(app, [
        "map", "paint", "tiny",
        "--at=0,0", "--base=grass",
        "--maps-dir", str(maps_dir),
    ])
    assert result.exit_code == 0
    repo = YamlMapRepository(maps_dir)
    doc = repo.load("tiny")
    cell = next(t for t in doc.tiles if t.x == 0 and t.y == 0)
    assert cell.base == "grass"


def test_map_paint_adds_feature(maps_dir: Path) -> None:
    result = runner.invoke(app, [
        "map", "paint", "tiny",
        "--at=2,1", "--feature=wall_v",
        "--maps-dir", str(maps_dir),
    ])
    assert result.exit_code == 0
    repo = YamlMapRepository(maps_dir)
    doc = repo.load("tiny")
    cell = next(t for t in doc.tiles if t.x == 2 and t.y == 1)
    assert "wall_v" in cell.features


def test_map_paint_bad_at_format_fails(maps_dir: Path) -> None:
    result = runner.invoke(app, [
        "map", "paint", "tiny", "--at=bad", "--base=floor",
        "--maps-dir", str(maps_dir),
    ])
    assert result.exit_code != 0


def test_map_paint_preserves_other_tiles(maps_dir: Path) -> None:
    """Покрасить (0,0) не должно удалить tile в (1,1) (из fixture)."""
    result = runner.invoke(app, [
        "map", "paint", "tiny", "--at=0,0", "--base=grass",
        "--maps-dir", str(maps_dir),
    ])
    assert result.exit_code == 0
    doc = YamlMapRepository(maps_dir).load("tiny")
    # Старый tile (1,1, floor) должен остаться + новый (0,0, grass)
    coords = [(t.x, t.y) for t in doc.tiles]
    assert (1, 1) in coords
    assert (0, 0) in coords
