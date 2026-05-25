"""InteractableObject — двери/сундуки/бочки/окна с состояниями."""
from __future__ import annotations

import pytest

from dnd.domain.entities.interactable import InteractableObject
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.ids import ObjectId
from dnd.domain.values.object_kind import ObjectKind
from dnd.domain.values.square import Square


def test_door_starts_closed_can_open() -> None:
    door = InteractableObject(
        id=ObjectId("door-1"),
        kind=ObjectKind.DOOR,
        pos=Square(3, 2),
        state={"open": False, "locked": False, "hp": 10, "ac": 13},
    )
    assert door.state["open"] is False
    door.open()
    assert door.state["open"] is True


def test_door_locked_cannot_be_opened_directly() -> None:
    door = InteractableObject(
        id=ObjectId("door-1"),
        kind=ObjectKind.DOOR,
        pos=Square(3, 2),
        state={"open": False, "locked": True, "hp": 10, "ac": 13},
    )
    with pytest.raises(RuntimeError, match="locked"):
        door.open()


def test_chest_open_returns_loot() -> None:
    chest = InteractableObject(
        id=ObjectId("chest-1"),
        kind=ObjectKind.CHEST,
        pos=Square(4, 4),
        state={"open": False, "contents": ["potion_heal", "gold_50"]},
    )
    loot = chest.open()
    assert loot == ["potion_heal", "gold_50"]
    assert chest.state["open"] is True
    # повторное открытие — пусто
    assert chest.open() == []


def test_barrel_take_damage_can_break() -> None:
    barrel = InteractableObject(
        id=ObjectId("bar-1"),
        kind=ObjectKind.BARREL,
        pos=Square(2, 2),
        state={"hp": 5, "broken": False, "contents": ["bolts_10"]},
    )
    result = barrel.take_damage(DamageInstance(amount=3, type_=DamageType.BLUDGEONING))
    assert result.was_lethal is False
    assert barrel.state["hp"] == 2
    result = barrel.take_damage(DamageInstance(amount=5, type_=DamageType.BLUDGEONING))
    assert result.was_lethal is True
    assert barrel.state["broken"] is True


def test_door_close_returns_to_closed() -> None:
    door = InteractableObject(
        id=ObjectId("d"),
        kind=ObjectKind.DOOR,
        pos=Square(1, 1),
        state={"open": True, "locked": False, "hp": 10, "ac": 13},
    )
    door.close()
    assert door.state["open"] is False


def test_barrel_cannot_be_opened() -> None:
    barrel = InteractableObject(
        id=ObjectId("b"),
        kind=ObjectKind.BARREL,
        pos=Square(0, 0),
        state={"hp": 5, "broken": False, "contents": ["x"]},
    )
    with pytest.raises(RuntimeError, match="cannot be opened"):
        barrel.open()


def test_chest_locked_cannot_open() -> None:
    chest = InteractableObject(
        id=ObjectId("c"),
        kind=ObjectKind.CHEST,
        pos=Square(0, 0),
        state={"open": False, "locked": True, "contents": ["gold"]},
    )
    with pytest.raises(RuntimeError, match="locked"):
        chest.open()


def test_broken_door_is_open() -> None:
    """Сломанная дверь = открытая (HP=0)."""
    door = InteractableObject(
        id=ObjectId("d"),
        kind=ObjectKind.DOOR,
        pos=Square(1, 1),
        state={"open": False, "locked": True, "hp": 3, "ac": 13},
    )
    result = door.take_damage(DamageInstance(amount=10, type_=DamageType.BLUDGEONING))
    assert result.was_lethal is True
    assert door.state["broken"] is True
    assert door.state["open"] is True  # сломанная = открытая
