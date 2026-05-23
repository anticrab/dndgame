"""ItemStack — пара item+qty, защита от qty<1 и от стакания не-stackable."""
from __future__ import annotations

import pytest

from dnd.domain.values.item import Item, ItemId, ItemKind
from dnd.domain.values.item_stack import ItemStack

_POTION = Item(
    id=ItemId("potion"), name="Potion", kind=ItemKind.CONSUMABLE,
    weight_lb=0.5, stackable=True,
)
_SWORD = Item(id=ItemId("sword"), name="Sword", kind=ItemKind.WEAPON)


def test_stack_with_default_qty_is_one() -> None:
    assert ItemStack(_POTION).qty == 1


def test_stack_with_explicit_qty() -> None:
    s = ItemStack(_POTION, qty=5)
    assert s.qty == 5


def test_zero_qty_rejected() -> None:
    """Пустой стак должен быть удалён, а не сохранён — это инвариант
    Inventory (предотвращает 'фантомные слоты')."""
    with pytest.raises(ValueError, match="qty"):
        ItemStack(_POTION, qty=0)


def test_negative_qty_rejected() -> None:
    with pytest.raises(ValueError, match="qty"):
        ItemStack(_POTION, qty=-1)


def test_non_stackable_qty_must_be_one() -> None:
    ItemStack(_SWORD, qty=1)  # ok
    with pytest.raises(ValueError, match="non-stackable"):
        ItemStack(_SWORD, qty=2)


def test_total_weight() -> None:
    assert ItemStack(_POTION, qty=4).total_weight_lb == pytest.approx(2.0)
    assert ItemStack(_SWORD).total_weight_lb == pytest.approx(0.0)


def test_qty_is_mutable() -> None:
    """Mutable qty: операции add/remove внутри Inventory обновляют
    стак на месте, не пересоздают."""
    s = ItemStack(_POTION, qty=3)
    s.qty += 2
    assert s.qty == 5
