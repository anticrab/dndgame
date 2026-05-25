"""Port: каталог заклинаний (read-only).

Существа хранят заклинания как :class:`SpellId`-ссылки (``known_spells``);
полные :class:`Spell`-описания приходят из каталога. Реализации:
* :class:`YamlSpellRepository` (читает data/content/spells.yaml);
* in-memory для тестов.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from dnd.domain.values.ids import SpellId
from dnd.domain.values.spell import Spell


@runtime_checkable
class SpellRepository(Protocol):
    def list_ids(self) -> tuple[SpellId, ...]:
        """ID всех известных заклинаний (для UI / валидации)."""
        ...

    def load(self, spell_id: SpellId) -> Spell:
        """Полное описание. KeyError если неизвестный id."""
        ...

    def contains(self, spell_id: SpellId) -> bool:
        ...


__all__ = ["SpellRepository"]
