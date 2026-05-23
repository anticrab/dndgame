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
