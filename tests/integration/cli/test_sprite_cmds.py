"""dnd sprite ... — list/show/validate."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from dnd.interfaces.cli.app import app

runner = CliRunner()


def test_sprite_list_default_table() -> None:
    result = runner.invoke(app, ["sprite", "list"])
    assert result.exit_code == 0
    assert "floor" in result.stdout  # terrain id


def test_sprite_list_json_format() -> None:
    result = runner.invoke(app, ["sprite", "list", "--format=json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert any(s["id"] == "floor" for s in data)


def test_sprite_show_renders_preview() -> None:
    result = runner.invoke(app, ["sprite", "show", "wall_v"])
    assert result.exit_code == 0
    assert "wall_v" in result.stdout
    assert "│" in result.stdout  # glyph_5x3 visible


def test_sprite_validate_ok() -> None:
    result = runner.invoke(app, ["sprite", "validate", "floor"])
    assert result.exit_code == 0


def test_sprite_validate_missing_fails() -> None:
    result = runner.invoke(app, ["sprite", "validate", "nope_does_not_exist"])
    assert result.exit_code != 0


def test_sprite_list_filtered_by_category() -> None:
    result = runner.invoke(app, ["sprite", "list", "--category=feature", "--format=json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert all(s["category"] == "feature" for s in data)
    assert any(s["id"] == "wall_v" for s in data)
