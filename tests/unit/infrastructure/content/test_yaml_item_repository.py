"""YamlItemRepository — каталог items из одного YAML."""
from __future__ import annotations

from pathlib import Path

import pytest

from dnd.domain.values.item import ItemId, ItemKind
from dnd.infrastructure.content.yaml_item_repository import YamlItemRepository


def _write(tmp: Path, body: str) -> Path:
    p = tmp / "items.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_empty_file_yields_empty_repository(tmp_path: Path) -> None:
    f = _write(tmp_path, "")
    repo = YamlItemRepository(f)
    assert repo.list_ids() == ()


def test_missing_file_yields_empty_repository(tmp_path: Path) -> None:
    """Конструктор не должен падать на пустом каталоге — полезно
    в TUI-стартапе до того, как пользователь сделал items.yaml."""
    repo = YamlItemRepository(tmp_path / "no-such.yaml")
    assert repo.list_ids() == ()


def test_loads_minimum_item(tmp_path: Path) -> None:
    f = _write(tmp_path, """
- id: gold
  name: "Gold"
  kind: misc
  stackable: true
""")
    repo = YamlItemRepository(f)
    item = repo.load(ItemId("gold"))
    assert item.name == "Gold"
    assert item.kind is ItemKind.MISC
    assert item.stackable is True
    assert item.weight_lb == 0.0


def test_loads_with_weight_and_description(tmp_path: Path) -> None:
    f = _write(tmp_path, """
- id: sword
  name: "Longsword"
  kind: weapon
  weight_lb: 3.0
  description: "1d8 slashing."
""")
    repo = YamlItemRepository(f)
    sword = repo.load(ItemId("sword"))
    assert sword.weight_lb == 3.0
    assert sword.description == "1d8 slashing."


def test_missing_id_raises_key_error(tmp_path: Path) -> None:
    f = _write(tmp_path, "")
    repo = YamlItemRepository(f)
    with pytest.raises(KeyError):
        repo.load(ItemId("ghost"))


def test_contains_distinguishes_known_from_unknown(tmp_path: Path) -> None:
    f = _write(tmp_path, """
- id: gold
  name: Gold
  kind: misc
  stackable: true
""")
    repo = YamlItemRepository(f)
    assert repo.contains(ItemId("gold"))
    assert not repo.contains(ItemId("nope"))


def test_duplicate_ids_rejected(tmp_path: Path) -> None:
    """Защита от опечатки в каталоге — иначе один из дубликатов
    тихо потеряется."""
    f = _write(tmp_path, """
- id: gold
  name: Gold
  kind: misc
  stackable: true
- id: gold
  name: "Gold (copy)"
  kind: misc
  stackable: true
""")
    with pytest.raises(ValueError, match="duplicate"):
        YamlItemRepository(f)


def test_invalid_top_level_rejected(tmp_path: Path) -> None:
    f = _write(tmp_path, "not_a_list: foo\n")
    with pytest.raises(ValueError, match="must contain a list"):
        YamlItemRepository(f)


def test_real_data_content_items_loads() -> None:
    """Smoke на data/content/items.yaml — реальный набор парсится."""
    p = Path(__file__).resolve().parents[4] / "data" / "content" / "items.yaml"
    if not p.exists():
        pytest.skip(f"no real items.yaml at {p}")
    repo = YamlItemRepository(p)
    assert ItemId("gold_piece") in repo.list_ids()
    assert ItemId("healing_potion") in repo.list_ids()
    assert repo.load(ItemId("longsword")).kind is ItemKind.WEAPON
    assert repo.load(ItemId("healing_potion")).stackable is True
