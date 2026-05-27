"""Все реальные YAML карты из data/content/maps/ валидно загружаются."""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository

MAPS_DIR = Path(__file__).resolve().parents[3] / "data" / "content" / "maps"


_EXPECTED_MAPS = [
    "mvp_skirmish",
    "open_field",
    "dungeon_hall",
    "forest_clearing",
    "warehouse",
    "bridge_crossing",
    "ruined_hall",
]


def test_all_required_maps_present() -> None:
    repo = YamlMapRepository(MAPS_DIR)
    ids = set(repo.list_ids())
    missing = set(_EXPECTED_MAPS) - ids
    assert not missing, f"missing maps: {missing}"


@pytest.mark.parametrize("map_id", _EXPECTED_MAPS)
def test_map_loads_and_validates(map_id: str) -> None:
    repo = YamlMapRepository(MAPS_DIR)
    doc = repo.load(map_id)
    assert doc.id == map_id
    # sanity: size > 0
    assert doc.width >= 1 and doc.height >= 1
    # все tiles в bounds (это уже валидирует MapDocument, но дублируем)
    for t in doc.tiles:
        assert 0 <= t.x < doc.width
        assert 0 <= t.y < doc.height


def test_warehouse_has_breakables() -> None:
    """Warehouse — флагманский playtest с бочками."""
    doc = YamlMapRepository(MAPS_DIR).load("warehouse")
    breakable_kinds = {o.kind for o in doc.objects if "hp" in o.state}
    assert "barrel" in breakable_kinds or "door" in breakable_kinds, doc.objects


def test_dungeon_hall_has_door() -> None:
    """Dungeon-hall должен иметь хотя бы одну дверь."""
    doc = YamlMapRepository(MAPS_DIR).load("dungeon_hall")
    door_kinds = [o.kind for o in doc.objects if o.kind == "door"]
    assert door_kinds, doc.objects
