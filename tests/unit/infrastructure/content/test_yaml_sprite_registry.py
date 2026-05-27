"""YamlSpriteRegistry — загружает sprite-YAMLs из каталога."""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


_FLOOR_YAML = """id: floor
category: terrain
name: Floor
passable: true
difficult: false
glyph_5x3:
  - "....."
  - "....."
  - "....."
glyph_1x1: .
color_token: floor
"""

_WALL_V_YAML = """id: wall_v
category: feature
name: Vertical wall
blocks_los: true
cover: total
blocks_passage_dirs: [e, w]
passable_cost_ft: 0
glyph_5x3:
  - "  |  "
  - "  |  "
  - "  |  "
glyph_1x1: "|"
color_token: wall
"""


def test_loads_terrain_from_yaml(tmp_path: Path) -> None:
    _write(tmp_path / "terrain" / "floor.yaml", _FLOOR_YAML)
    reg = YamlSpriteRegistry(tmp_path)
    floor = reg.get_terrain("floor")
    assert floor.id == "floor"
    assert floor.passable is True


def test_loads_feature_with_dirs(tmp_path: Path) -> None:
    _write(tmp_path / "features" / "wall_v.yaml", _WALL_V_YAML)
    reg = YamlSpriteRegistry(tmp_path)
    wall = reg.get_feature("wall_v")
    assert wall.blocks_los is True
    from dnd.domain.values.direction import Direction

    assert Direction.E in wall.blocks_passage_dirs


def test_list_by_category(tmp_path: Path) -> None:
    _write(tmp_path / "terrain" / "floor.yaml", _FLOOR_YAML)
    reg = YamlSpriteRegistry(tmp_path)
    items = reg.list_by_category(SpriteCategory.TERRAIN)
    assert len(items) == 1
    assert items[0].id == "floor"


def test_missing_dir_is_empty_not_error(tmp_path: Path) -> None:
    reg = YamlSpriteRegistry(tmp_path)
    with pytest.raises(KeyError):
        reg.get_terrain("nope")
    assert reg.list_by_category(SpriteCategory.FEATURE) == ()


def test_unknown_feature_raises_keyerror(tmp_path: Path) -> None:
    reg = YamlSpriteRegistry(tmp_path)
    with pytest.raises(KeyError, match="wall_v"):
        reg.get_feature("wall_v")
