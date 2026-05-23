"""Port: каталог предметов (read-only).

Items в инвентаре, сундуках и на трупах хранятся как ItemId-ссылки;
их полные :class:`Item`-описания (name/weight/kind) приходят из
каталога — отдельного файла YAML / встроенного default'а. Это
позволяет сценарию писать ``contents: [{ item_id: gold, qty: 50 }]``
вместо повторения weight'а и описания каждый раз.

Реализации:
* :class:`YamlItemRepository` (default, читает data/content/items.yaml);
* in-memory для тестов.

Write-операции (создание новых предметов рантайм) пока не нужны —
items.yaml редактируется вручную или TUI-палитрой потом.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from dnd.domain.values.item import Item, ItemId


@runtime_checkable
class ItemRepository(Protocol):
    def list_ids(self) -> tuple[ItemId, ...]:
        """ID всех известных предметов (для UI палитры / валидации)."""
        ...

    def load(self, item_id: ItemId) -> Item:
        """Полное описание предмета. KeyError если неизвестный id."""
        ...

    def contains(self, item_id: ItemId) -> bool:
        ...


__all__ = ["ItemRepository"]
