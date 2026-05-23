"""Все реальные sprite-YAML'ы из data/content/sprites/ валидно загружаются."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.ports.sprite_registry import SpriteCategory
from dnd.infrastructure.content.yaml_sprite_registry import YamlSpriteRegistry

CONTENT = Path(__file__).resolve().parents[3] / "data" / "content" / "sprites"


def test_real_sprites_load_without_error() -> None:
    reg = YamlSpriteRegistry(CONTENT)
    terrains = reg.list_by_category(SpriteCategory.TERRAIN)
    features = reg.list_by_category(SpriteCategory.FEATURE)
    # Минимум 5 terrain + 10 feature должно загрузиться (K2-T3).
    assert len(terrains) >= 5, [t.id for t in terrains]
    assert len(features) >= 10, [f.id for f in features]


@pytest.mark.parametrize(
    "terrain_id",
    ["floor", "grass", "stone", "water", "dirt"],
)
def test_required_terrains_present(terrain_id: str) -> None:
    reg = YamlSpriteRegistry(CONTENT)
    t = reg.get_terrain(terrain_id)
    assert t.id == terrain_id


@pytest.mark.parametrize(
    "feature_id",
    ["wall_v", "wall_h", "wall_full", "column", "table_small", "low_cover_obj"],
)
def test_required_features_present(feature_id: str) -> None:
    reg = YamlSpriteRegistry(CONTENT)
    f = reg.get_feature(feature_id)
    assert f.id == feature_id
