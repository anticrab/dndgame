"""Inventory events: ItemPickedUp / ItemDropped / ItemEquipped / ItemUnequipped."""
from __future__ import annotations

from dnd.application.dto.engine_event import (
    ItemDropped,
    ItemEquipped,
    ItemPickedUp,
    ItemUnequipped,
)
from dnd.application.dto.ids import CreatureId


def test_picked_up_serializes_basic() -> None:
    ev = ItemPickedUp(
        actor_id=CreatureId("aelar"), item_id="longsword",
        item_name="Longsword", qty=1, source="chest:chest-1",
    )
    assert ev.event_type == "inventory.item_picked_up"
    assert ev.qty == 1
    assert ev.source.startswith("chest:")


def test_dropped_carries_qty() -> None:
    ev = ItemDropped(
        actor_id=CreatureId("aelar"), item_id="gold",
        item_name="Gold piece", qty=25,
    )
    assert ev.event_type == "inventory.item_dropped"
    assert ev.qty == 25


def test_equip_and_unequip_have_distinct_event_types() -> None:
    eq = ItemEquipped(
        actor_id=CreatureId("aelar"), item_id="sword", item_name="Sword",
    )
    un = ItemUnequipped(
        actor_id=CreatureId("aelar"), item_id="sword", item_name="Sword",
    )
    assert eq.event_type != un.event_type
    assert eq.event_type == "inventory.item_equipped"
    assert un.event_type == "inventory.item_unequipped"


def test_pickup_source_is_open_string() -> None:
    """source — свободная строка-метка ('chest:<id>'|'corpse:<id>'|
    'ground'); никакого pydantic enum'а, потому что UI и логика могут
    добавлять новые источники без миграции DTO."""
    for src in ("chest:c1", "corpse:goblin1", "ground", "shop:merchant1"):
        ev = ItemPickedUp(
            actor_id=CreatureId("a"), item_id="x",
            item_name="X", qty=1, source=src,
        )
        assert ev.source == src
