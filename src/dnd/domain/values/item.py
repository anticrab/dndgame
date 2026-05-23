"""Item — frozen value object для одного предмета инвентаря.

Минимальная модель этапа O-1:
* identity через ``id`` (для словаря по ItemRepository / DB);
* категория через :class:`ItemKind` (управляет, что можно делать —
  equip, use, drop);
* ``weight_lb`` — фунты, для расчёта encumbrance (PHB-2024 стр. 122);
* ``description`` — UI-строка (отображается в InventoryScreen).

Не входит сюда (будет в отдельных value-объектах позже):
* статы оружия (damage, range) — ``WeaponProfile`` уже существует
  отдельно; этап O-1 не объединяет их, чтобы не делать большой
  refactor в одном task'е. На O-8/O-9 свяжем через ``equipped_item_id``.
* charges/uses у consumable'ов — в state-машине Inventory (O-3).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import NewType

ItemId = NewType("ItemId", str)


class ItemKind(StrEnum):
    """Категория предмета. Управляет UI-операциями и validation:
    * WEAPON — можно equip (привязка к WeaponProfile по id);
    * ARMOR — можно equip (одну за раз; броню оставим на этап Armor);
    * CONSUMABLE — можно use (потратится одна charge);
    * QUEST — нельзя drop (защита от нечаянного выбрасывания);
    * MISC — нельзя equip/use; можно только drop/lootать (валюта,
      сувениры).
    """

    WEAPON = "weapon"
    ARMOR = "armor"
    CONSUMABLE = "consumable"
    QUEST = "quest"
    MISC = "misc"


@dataclass(frozen=True, slots=True)
class Item:
    id: ItemId
    name: str
    kind: ItemKind
    weight_lb: float = 0.0
    description: str = ""
    stackable: bool = False
    """Можно ли объединять в стак. Монеты/зелья/факелы — True;
    оружие/броня — False (даже два меча в инвентаре — два отдельных
    стака по 1). Стакование делается в Inventory.add (O-3)."""

    def __post_init__(self) -> None:
        if self.weight_lb < 0:
            raise ValueError(
                f"item {self.id}: weight_lb must be >= 0, got {self.weight_lb}"
            )
        if not self.id:
            raise ValueError("item id must be non-empty")
        if not self.name:
            raise ValueError(f"item {self.id}: name must be non-empty")


__all__ = ["Item", "ItemId", "ItemKind"]
