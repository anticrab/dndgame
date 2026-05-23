"""Item value-object — frozen + минимальная валидация."""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from dnd.domain.values.item import Item, ItemId, ItemKind


def test_item_is_frozen() -> None:
    it = Item(id=ItemId("longsword"), name="Longsword", kind=ItemKind.WEAPON)
    with pytest.raises(FrozenInstanceError):
        it.name = "X"  # type: ignore[misc]


def test_item_kinds_cover_expected_set() -> None:
    """5 базовых категорий — все use-case'ы Inventory сводятся к ним."""
    assert {k.value for k in ItemKind} == {
        "weapon", "armor", "consumable", "quest", "misc",
    }


def test_negative_weight_rejected() -> None:
    with pytest.raises(ValueError, match="weight_lb"):
        Item(
            id=ItemId("ghost"), name="Ghost",
            kind=ItemKind.MISC, weight_lb=-1.0,
        )


def test_empty_id_rejected() -> None:
    with pytest.raises(ValueError, match="id"):
        Item(id=ItemId(""), name="x", kind=ItemKind.MISC)


def test_empty_name_rejected() -> None:
    with pytest.raises(ValueError, match="name"):
        Item(id=ItemId("x"), name="", kind=ItemKind.MISC)


def test_stackable_defaults_to_false() -> None:
    """Случайное стакование оружий было бы багом — default безопасный."""
    it = Item(id=ItemId("sword"), name="Sword", kind=ItemKind.WEAPON)
    assert it.stackable is False


def test_consumable_with_stackable_true_ok() -> None:
    potion = Item(
        id=ItemId("healing_potion"), name="Healing Potion",
        kind=ItemKind.CONSUMABLE, weight_lb=0.5, stackable=True,
    )
    assert potion.stackable is True
    assert potion.weight_lb == 0.5
