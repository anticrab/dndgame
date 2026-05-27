"""Helpers для перевода ``state["contents"]`` в ``tuple[ItemStack, ...]``.

Сундуки/трупы в YAML-картах хранят список «what's inside» в свободной
форме внутри ``InteractableObject.state["contents"]``. Этап O-6
формализует структуру:

* Новый канонический формат:
  ``contents: [{item_id: <ItemId>, qty: <int>}, ...]``;
* Старый legacy формат (бывал в warehouse.yaml etc):
  ``contents: ["gold", "gold", "longsword"]`` — список строк.
  Поддерживается для обратной совместимости карт; на сохранении
  ``dump_loot_entries`` всегда пишет новый формат.

``parse_loot`` берёт raw data + ItemRepository и возвращает
сериализованные ``ItemStack``-и, готовые к UI-показу и Inventory.add.
``dump_loot_entries`` делает обратную операцию для редактора карт.

Не входит сюда: сами Pickup/Drop intents (O-8) — они работают уже
с распарсенным tuple[ItemStack, ...], а не с YAML-сырьём.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from dnd.application.ports.item_repository import ItemRepository
from dnd.domain.values.item import ItemId
from dnd.domain.values.item_stack import ItemStack


def parse_loot(raw: Any, repo: ItemRepository) -> tuple[ItemStack, ...]:
    """Распарсить ``state["contents"]`` в ``tuple[ItemStack, ...]``.

    Принимает:
    * None / отсутствие ключа → пустой tuple;
    * list[str] (legacy) → каждая строка = item_id, qty=1; повторы
      strings для stackable items сворачиваются в один ItemStack
      с суммой qty;
    * list[dict] (canonical) → каждый entry = {item_id, qty};
      qty по умолчанию 1.

    Неизвестные item_id → KeyError из ItemRepository (fail-fast, чтобы
    карта с битой ссылкой падала при загрузке, а не при первом open
    в середине боя).
    """
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError(f"chest contents must be a list, got {type(raw).__name__}")
    if not raw:
        return ()

    # legacy: list[str] — посчитаем повторы для stackable
    if all(isinstance(x, str) for x in raw):
        counts: Counter[str] = Counter(raw)
        out: list[ItemStack] = []
        for item_id_str, n in counts.items():
            item = repo.load(ItemId(item_id_str))
            if item.stackable:
                out.append(ItemStack(item, qty=n))
            else:
                # non-stackable: n отдельных стаков qty=1
                out.extend(ItemStack(item, qty=1) for _ in range(n))
        return tuple(out)

    # canonical: list[dict]
    out2: list[ItemStack] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError(f"chest contents: expected dict entry, got {type(entry).__name__}")
        item_id = ItemId(entry["item_id"])
        qty = int(entry.get("qty", 1))
        item = repo.load(item_id)
        out2.append(ItemStack(item, qty=qty))
    return tuple(out2)


def dump_loot_entries(
    stacks: tuple[ItemStack, ...] | list[ItemStack],
) -> list[dict[str, Any]]:
    """Сериализовать ItemStack-и для записи в ``state["contents"]``.

    Возвращает canonical-формат (list[dict]) — никаких list[str]
    мы больше не пишем (legacy только читаем).
    """
    return [{"item_id": s.item.id, "qty": s.qty} for s in stacks]


__all__ = ["dump_loot_entries", "parse_loot"]
