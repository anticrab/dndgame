"""Типизированные идентификаторы (доменный фундамент).

``NewType`` поверх ``str`` / ``UUID`` для статической типизации:
``CreatureId`` нельзя случайно передать туда, где ждут ``PlayerId``. На
рантайме это обычные ``str`` / ``UUID``.

Живут в ``domain``, а не в ``application``: id-типы — часть доменной модели
(``Creature`` / ``Spell`` / ``Condition`` оперируют ими напрямую), поэтому
domain не должен зависеть от application ради них (гексагональная архитектура).
Application и infrastructure импортируют их отсюда.
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID

CreatureId = NewType("CreatureId", str)
PlayerId = NewType("PlayerId", str)
SpellId = NewType("SpellId", str)
# ItemId намеренно живёт в dnd.domain.values.item — это часть доменного
# фундамента инвентаря (этап O). Импортируйте: `from dnd.domain.values.item`.
ScenarioId = NewType("ScenarioId", str)
LocationId = NewType("LocationId", str)
EncounterId = NewType("EncounterId", str)
ActionId = NewType("ActionId", str)
ConditionId = NewType("ConditionId", str)
FeatureId = NewType("FeatureId", str)
ObjectId = NewType("ObjectId", str)
SessionId = NewType("SessionId", UUID)
RollId = NewType("RollId", UUID)


__all__ = [
    "ActionId",
    "ConditionId",
    "CreatureId",
    "EncounterId",
    "FeatureId",
    "LocationId",
    "ObjectId",
    "PlayerId",
    "RollId",
    "ScenarioId",
    "SessionId",
    "SpellId",
]
