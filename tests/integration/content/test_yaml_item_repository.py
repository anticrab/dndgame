"""YamlItemRepository — парсинг каталога предметов из YAML (U2-2 расширил `use:`).

Минимальные проверки: базовый предмет без `use`, и предмет с `use:` —
оба загружаются; `Item.use` корректно собирается из YAML в ``ItemUseSpec``."""

from __future__ import annotations

from pathlib import Path

import pytest

from dnd.domain.values.ids import SpellId
from dnd.domain.values.item import ItemId, ItemKind
from dnd.domain.values.item_use import ItemUseSpec
from dnd.infrastructure.content.yaml_item_repository import YamlItemRepository


def test_loads_plain_item_without_use(tmp_path: Path) -> None:
    f = tmp_path / "items.yaml"
    f.write_text(
        """
- id: gold
  name: "Gold piece"
  kind: misc
  weight_lb: 0.02
  stackable: true
""",
        encoding="utf-8",
    )
    repo = YamlItemRepository(f)
    gold = repo.load(ItemId("gold"))
    assert gold.kind is ItemKind.MISC
    assert gold.use is None


def test_loads_consumable_with_use_potion(tmp_path: Path) -> None:
    f = tmp_path / "items.yaml"
    f.write_text(
        """
- id: healing_potion
  name: "Potion of Healing"
  kind: consumable
  weight_lb: 0.5
  stackable: true
  use:
    effect_id: potion_healing
    economy: bonus_action
""",
        encoding="utf-8",
    )
    repo = YamlItemRepository(f)
    potion = repo.load(ItemId("healing_potion"))
    assert potion.use == ItemUseSpec(
        effect_id=SpellId("potion_healing"),
        economy="bonus_action",
        consumed=True,
        is_scroll=False,
    )


def test_loads_scroll_with_is_scroll_true(tmp_path: Path) -> None:
    f = tmp_path / "items.yaml"
    f.write_text(
        """
- id: scroll_of_fireball
  name: "Scroll of Fireball"
  kind: consumable
  weight_lb: 0.1
  stackable: true
  use:
    effect_id: fireball
    economy: action
    is_scroll: true
""",
        encoding="utf-8",
    )
    repo = YamlItemRepository(f)
    scroll = repo.load(ItemId("scroll_of_fireball"))
    assert scroll.use is not None
    assert scroll.use.is_scroll is True
    assert scroll.use.effect_id == SpellId("fireball")
    assert scroll.use.economy == "action"


def test_use_with_unknown_economy_raises(tmp_path: Path) -> None:
    f = tmp_path / "items.yaml"
    f.write_text(
        """
- id: bad_item
  name: "Bad"
  kind: consumable
  use:
    effect_id: cure_wounds
    economy: reaction
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="economy"):
        YamlItemRepository(f)
