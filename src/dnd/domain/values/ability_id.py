"""AbilityId — идентификатор runtime-умения.

Вынесено в ``domain/values``, потому что ``Creature`` ссылается на список
``ability_ids`` (этап L2-4). Domain не должен импортировать из
``application``-слоя, иначе ломается hexagonal-направление зависимостей;
поэтому identifier живёт в domain, а описание умения
(:class:`~dnd.application.abilities.ability.Ability` — с intent_factory
и UI-полями) — в application.
"""
from __future__ import annotations

from typing import NewType

AbilityId = NewType("AbilityId", str)


__all__ = ["AbilityId"]
