"""YamlItemRepository — каталог предметов из одного YAML-файла.

Формат файла: список items (без header'а карты — items независимы и
не образуют document). Пример:

.. code-block:: yaml

    - id: gold
      name: "Gold piece"
      kind: misc
      weight_lb: 0.02
      stackable: true
    - id: longsword
      name: "Longsword"
      kind: weapon
      weight_lb: 3.0
      description: "Versatile martial weapon."

Один файл вместо «папка на предмет» — каталог редкий и читается
целиком при старте; одиночный yaml парсится быстрее и проще
просматривается. Если станет большим (>200 items) — разобьём
по категориям (weapons.yaml / armor.yaml / consumables.yaml).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from dnd.domain.values.item import Item, ItemId, ItemKind


class YamlItemRepository:
    def __init__(self, items_file: Path) -> None:
        self._file = items_file
        self._by_id: dict[ItemId, Item] = {}
        if items_file.exists():
            self._reload()

    def _reload(self) -> None:
        raw = yaml.safe_load(self._file.read_text(encoding="utf-8"))
        if raw is None:
            return  # пустой файл
        if not isinstance(raw, list):
            raise ValueError(f"items file {self._file} must contain a list, got {type(raw)}")
        self._by_id = {}
        for entry in raw:
            item = self._parse(entry)
            if item.id in self._by_id:
                raise ValueError(f"duplicate item id {item.id!r} in {self._file}")
            self._by_id[item.id] = item

    def _parse(self, entry: dict[str, Any]) -> Item:
        return Item(
            id=ItemId(entry["id"]),
            name=entry["name"],
            kind=ItemKind(entry["kind"]),
            weight_lb=float(entry.get("weight_lb", 0.0)),
            description=entry.get("description", ""),
            stackable=bool(entry.get("stackable", False)),
        )

    def list_ids(self) -> tuple[ItemId, ...]:
        return tuple(sorted(self._by_id.keys()))

    def load(self, item_id: ItemId) -> Item:
        if item_id not in self._by_id:
            raise KeyError(f"unknown item: {item_id!r}")
        return self._by_id[item_id]

    def contains(self, item_id: ItemId) -> bool:
        return item_id in self._by_id


__all__ = ["YamlItemRepository"]
