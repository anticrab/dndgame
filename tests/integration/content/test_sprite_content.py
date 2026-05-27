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


# K9 S1-2: objects/ и creatures/ должны загружаться как FeatureKind
# (чтобы `dnd sprite show door` / list работали).


@pytest.mark.parametrize(
    "object_id",
    ["door", "chest", "barrel", "window"],
)
def test_required_objects_present(object_id: str) -> None:
    reg = YamlSpriteRegistry(CONTENT)
    items = reg.list_by_category(SpriteCategory.OBJECT)
    assert object_id in {i.id for i in items}
    # get_feature ищет в объединённом пространстве feature+object+creature.
    assert reg.get_feature(object_id).id == object_id


@pytest.mark.parametrize(
    "creature_id",
    ["pc_humanoid", "goblin"],
)
def test_required_creatures_present(creature_id: str) -> None:
    reg = YamlSpriteRegistry(CONTENT)
    items = reg.list_by_category(SpriteCategory.CREATURE)
    assert creature_id in {i.id for i in items}
    assert reg.get_feature(creature_id).id == creature_id


def test_sprite_show_door_cli_works() -> None:
    """`dnd sprite show door` — smoke через CliRunner.

    До K9 S1-2 объекты грузились как ничего — show падал «sprite not found».
    """
    from typer.testing import CliRunner

    from dnd.interfaces.cli.app import app

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["sprite", "show", "door", "--content-dir", str(CONTENT)],
    )
    assert result.exit_code == 0, result.output
    assert "door" in result.output.lower()
    assert "Door" in result.output
