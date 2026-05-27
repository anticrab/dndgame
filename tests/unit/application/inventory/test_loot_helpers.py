"""parse_loot / dump_loot_entries — canonical vs legacy формат chest contents."""

from __future__ import annotations

import pytest

from dnd.application.inventory.loot_helpers import dump_loot_entries, parse_loot
from dnd.application.ports.item_repository import ItemRepository
from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.item_stack import ItemStack


class _FakeRepo:
    """In-memory ItemRepository для unit-тестов."""

    def __init__(self, items: list[Item]) -> None:
        self._by_id = {i.id: i for i in items}

    def list_ids(self) -> tuple[ItemId, ...]:
        return tuple(self._by_id.keys())

    def load(self, item_id: ItemId) -> Item:
        return self._by_id[item_id]

    def contains(self, item_id: ItemId) -> bool:
        return item_id in self._by_id


_GOLD = Item(id=ItemId("gold"), name="Gold", kind=ItemKind.MISC, weight_lb=0.02, stackable=True)
_SWORD = Item(id=ItemId("sword"), name="Sword", kind=ItemKind.WEAPON, weight_lb=3.0)
_POTION = Item(
    id=ItemId("potion"), name="Potion", kind=ItemKind.CONSUMABLE, weight_lb=0.5, stackable=True
)


def _repo() -> ItemRepository:
    return _FakeRepo([_GOLD, _SWORD, _POTION])


# --- canonical ---------------------------------------------------


def test_canonical_dict_form() -> None:
    raw = [
        {"item_id": "gold", "qty": 50},
        {"item_id": "sword"},  # qty по умолчанию 1
    ]
    stacks = parse_loot(raw, _repo())
    assert len(stacks) == 2
    assert stacks[0].item.id == ItemId("gold")
    assert stacks[0].qty == 50
    assert stacks[1].item.id == ItemId("sword")
    assert stacks[1].qty == 1


def test_canonical_with_qty_string_coerces_int() -> None:
    """Иногда YAML отдаёт '5' (строка) при ручной правке — int()
    конвертирует, иначе ItemStack бросит на типе."""
    raw = [{"item_id": "gold", "qty": "5"}]
    stacks = parse_loot(raw, _repo())
    assert stacks[0].qty == 5


# --- legacy list[str] --------------------------------------------


def test_legacy_string_list_collapses_stackable() -> None:
    """Старый формат list[str]: повторы стакаются для stackable."""
    raw = ["gold", "gold", "gold"]
    stacks = parse_loot(raw, _repo())
    assert len(stacks) == 1
    assert stacks[0].qty == 3


def test_legacy_string_list_keeps_non_stackable_separate() -> None:
    """Non-stackable не сворачиваются — два меча = два слота."""
    raw = ["sword", "sword"]
    stacks = parse_loot(raw, _repo())
    assert len(stacks) == 2
    assert all(s.qty == 1 for s in stacks)


def test_legacy_mixed_kinds() -> None:
    raw = ["gold", "gold", "sword", "potion"]
    stacks = parse_loot(raw, _repo())
    by_id = {s.item.id: s for s in stacks if s.item.stackable}
    swords = [s for s in stacks if s.item.id == ItemId("sword")]
    assert by_id[ItemId("gold")].qty == 2
    assert by_id[ItemId("potion")].qty == 1
    assert len(swords) == 1


# --- edge cases --------------------------------------------------


def test_none_yields_empty() -> None:
    assert parse_loot(None, _repo()) == ()


def test_empty_list_yields_empty() -> None:
    assert parse_loot([], _repo()) == ()


def test_non_list_rejected() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        parse_loot({"item_id": "gold"}, _repo())


def test_unknown_item_id_raises() -> None:
    """Битая ссылка в карте должна падать сразу при загрузке."""
    raw = [{"item_id": "ghost", "qty": 1}]
    with pytest.raises(KeyError):
        parse_loot(raw, _repo())


def test_mixed_legacy_with_unknown_raises() -> None:
    raw = ["gold", "ghost"]
    with pytest.raises(KeyError):
        parse_loot(raw, _repo())


# --- dump round-trip --------------------------------------------


def test_dump_round_trip() -> None:
    stacks = (
        ItemStack(_GOLD, qty=42),
        ItemStack(_SWORD, qty=1),
    )
    entries = dump_loot_entries(stacks)
    assert entries == [
        {"item_id": "gold", "qty": 42},
        {"item_id": "sword", "qty": 1},
    ]
    # parse → dump → parse даёт тот же набор
    reparsed = parse_loot(entries, _repo())
    assert len(reparsed) == 2
    assert reparsed[0].qty == 42 and reparsed[0].item.id == _GOLD.id
