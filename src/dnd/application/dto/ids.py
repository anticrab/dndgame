"""Типизированные идентификаторы.

Используем ``NewType`` поверх ``str`` / ``UUID`` для статической
типизации: ``CreatureId`` нельзя случайно передать туда, где ждут
``PlayerId``. На рантайме это обычные ``str``/``UUID``.
"""

from __future__ import annotations

from typing import NewType
from uuid import UUID

CreatureId = NewType("CreatureId", str)
PlayerId = NewType("PlayerId", str)
SpellId = NewType("SpellId", str)
ItemId = NewType("ItemId", str)
ScenarioId = NewType("ScenarioId", str)
LocationId = NewType("LocationId", str)
EncounterId = NewType("EncounterId", str)
ActionId = NewType("ActionId", str)
ConditionId = NewType("ConditionId", str)
FeatureId = NewType("FeatureId", str)
ObjectId = NewType("ObjectId", str)
SessionId = NewType("SessionId", UUID)
RollId = NewType("RollId", UUID)
