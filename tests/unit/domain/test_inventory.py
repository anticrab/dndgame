"""Inventory — add/remove/find + slot- и weight-лимиты."""
from __future__ import annotations

import pytest

from dnd.domain.entities.inventory import Inventory
from dnd.domain.values.item import Item, ItemId, ItemKind

_GOLD = Item(
    id=ItemId("gold"), name="Gold piece",
    kind=ItemKind.MISC, weight_lb=0.02, stackable=True,
)
_POTION = Item(
    id=ItemId("potion"), name="Healing Potion",
    kind=ItemKind.CONSUMABLE, weight_lb=0.5, stackable=True,
)
_SWORD = Item(id=ItemId("sword"), name="Sword", kind=ItemKind.WEAPON, weight_lb=3)


# --- queries -----------------------------------------------------


def test_empty_inventory_basics() -> None:
    inv = Inventory()
    assert inv.slot_count() == 0
    assert inv.total_weight_lb() == 0
    assert inv.find_by_id(ItemId("x")) is None
    assert inv.contains(ItemId("x")) is False


# --- add ---------------------------------------------------------


def test_add_stackable_creates_single_slot() -> None:
    inv = Inventory()
    overflow = inv.add(_GOLD, qty=50)
    assert overflow == 0
    assert inv.slot_count() == 1
    assert inv.find_by_id(_GOLD.id).qty == 50  # type: ignore[union-attr]


def test_add_stackable_pools_into_existing_slot() -> None:
    inv = Inventory()
    inv.add(_GOLD, qty=10)
    inv.add(_GOLD, qty=5)
    assert inv.slot_count() == 1
    assert inv.find_by_id(_GOLD.id).qty == 15  # type: ignore[union-attr]


def test_add_non_stackable_creates_one_slot_per_item() -> None:
    inv = Inventory()
    inv.add(_SWORD, qty=3)
    assert inv.slot_count() == 3
    assert all(s.qty == 1 for s in inv.stacks)


def test_add_qty_must_be_positive() -> None:
    with pytest.raises(ValueError, match="qty"):
        Inventory().add(_GOLD, qty=0)


# --- slot limit --------------------------------------------------


def test_slot_limit_blocks_new_non_stackable() -> None:
    inv = Inventory(slot_limit=2)
    overflow = inv.add(_SWORD, qty=5)
    assert inv.slot_count() == 2
    assert overflow == 3


def test_slot_limit_allows_pooling_stackable_after_full() -> None:
    """Пополнение существующего слота не занимает новый — даже когда
    инвентарь забит, можно докинуть монет в уже-открытый кошель."""
    inv = Inventory(slot_limit=1)
    inv.add(_GOLD, qty=10)
    overflow = inv.add(_GOLD, qty=50)
    assert overflow == 0
    assert inv.find_by_id(_GOLD.id).qty == 60  # type: ignore[union-attr]


def test_negative_slot_limit_rejected() -> None:
    with pytest.raises(ValueError):
        Inventory(slot_limit=-1)


# --- weight limit ------------------------------------------------


def test_weight_limit_caps_stackable_qty() -> None:
    """Зелья по 0.5 lb, лимит 2 lb → влезают только 4 зелья."""
    inv = Inventory(weight_limit_lb=2.0)
    overflow = inv.add(_POTION, qty=10)
    assert overflow == 6
    assert inv.find_by_id(_POTION.id).qty == 4  # type: ignore[union-attr]


def test_weight_limit_caps_non_stackable() -> None:
    """Меч 3 lb, лимит 4 lb → ровно один меч."""
    inv = Inventory(weight_limit_lb=4.0)
    overflow = inv.add(_SWORD, qty=3)
    assert overflow == 2
    assert inv.slot_count() == 1


# --- remove ------------------------------------------------------


def test_remove_one_stackable_decrements_qty() -> None:
    inv = Inventory()
    inv.add(_GOLD, qty=10)
    removed = inv.remove_one(_GOLD.id)
    assert removed is _GOLD
    assert inv.find_by_id(_GOLD.id).qty == 9  # type: ignore[union-attr]


def test_remove_one_stackable_to_zero_drops_slot() -> None:
    inv = Inventory()
    inv.add(_GOLD, qty=1)
    inv.remove_one(_GOLD.id)
    assert inv.slot_count() == 0
    assert inv.find_by_id(_GOLD.id) is None


def test_remove_one_non_stackable_drops_one_slot() -> None:
    inv = Inventory()
    inv.add(_SWORD, qty=2)
    inv.remove_one(_SWORD.id)
    assert inv.slot_count() == 1


def test_remove_missing_returns_none() -> None:
    assert Inventory().remove_one(ItemId("ghost")) is None


# --- summary helpers --------------------------------------------


def test_total_weight_after_mixed_load() -> None:
    inv = Inventory()
    inv.add(_GOLD, qty=100)  # 100 × 0.02 = 2 lb
    inv.add(_POTION, qty=2)  # 2 × 0.5 = 1 lb
    inv.add(_SWORD)  # 3 lb
    assert inv.total_weight_lb() == pytest.approx(6.0)
