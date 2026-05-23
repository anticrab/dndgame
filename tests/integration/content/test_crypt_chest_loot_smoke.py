"""Smoke: загрузка крипты + парсинг chest contents через items.yaml.

Подтверждает, что миграция YAML карт на canonical loot формат не
сломала боевой content-pipeline: каждый сундук в crypt'е резолвится
через items.yaml в реальные ItemStack'и.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.application.inventory.loot_helpers import parse_loot
from dnd.infrastructure.content.yaml_item_repository import YamlItemRepository
from dnd.infrastructure.content.yaml_map_repository import YamlMapRepository

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MAPS_DIR = _REPO_ROOT / "data" / "content" / "maps"
_ITEMS_YAML = _REPO_ROOT / "data" / "content" / "items.yaml"


@pytest.mark.skipif(
    not _ITEMS_YAML.exists(), reason="items.yaml not present"
)
def test_crypt_chest_contents_resolve_to_real_items() -> None:
    items = YamlItemRepository(_ITEMS_YAML)
    maps = YamlMapRepository(_MAPS_DIR)
    doc = maps.load("crypt_of_black_candle")

    chests = [o for o in doc.objects if o.kind == "chest"]
    assert chests, "в крипте должны быть сундуки"

    total_stacks = 0
    seen_kinds: set[str] = set()
    for obj in chests:
        loot = parse_loot(obj.state.get("contents"), items)
        # Хотим увидеть хотя бы что-то лутаемое в каждом сундуке
        assert loot, f"chest {obj.id} без лута — крипта стала пустой"
        for stack in loot:
            assert stack.qty >= 1
            seen_kinds.add(stack.item.kind.value)
            total_stacks += 1
    # Проверяем разнообразие — лут в крипте должен содержать
    # минимум валюту и что-то ещё (зелье / оружие / quest).
    assert "misc" in seen_kinds  # gold/silver
    assert seen_kinds - {"misc"}, (
        f"кроме валюты в сундуках должны быть и другие kinds: {seen_kinds}"
    )
    assert total_stacks >= len(chests)


@pytest.mark.skipif(
    not _ITEMS_YAML.exists(), reason="items.yaml not present"
)
def test_no_chest_in_real_maps_references_unknown_item() -> None:
    """Bus check для всех карт: каждый chest contents resolves через
    каталог. Падает фастом если в карту попал тип, которого нет в
    items.yaml."""
    items = YamlItemRepository(_ITEMS_YAML)
    maps = YamlMapRepository(_MAPS_DIR)
    for map_id in maps.list_ids():
        doc = maps.load(map_id)
        for obj in doc.objects:
            if obj.kind != "chest":
                continue
            # Если parse_loot бросит KeyError — тест упадёт с понятной
            # ошибкой 'unknown item <X> in chest <Y> of map <Z>'.
            try:
                parse_loot(obj.state.get("contents"), items)
            except KeyError as e:
                raise AssertionError(
                    f"unknown item id in chest {obj.id} of map {map_id}: {e}"
                ) from e
