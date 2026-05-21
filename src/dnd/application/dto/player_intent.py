"""PlayerIntent — намерения игрока за PC в ход.

Discriminated union вариантов: атака / движение / Dodge / Dash /
Disengage / EndTurn. Парсится pydantic'ом по полю ``kind``, как и
``MasterIntent``.

UI/AI собирает intent на каждом шаге хода; ``GameRunner`` транслирует
его в вызов соответствующего Action.

См. ``docs/ACTIONS.md`` §3 / §6.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from dnd.application.dto.ids import CreatureId
from dnd.domain.values.square import Square


class _IntentBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AttackIntent(_IntentBase):
    """Атака экипированным оружием по цели."""

    kind: Literal["attack"] = "attack"
    target_id: CreatureId


class MoveIntent(_IntentBase):
    """Движение по пути. ``path`` — последовательность клеток без
    стартовой; каждая соседняя предыдущей."""

    kind: Literal["move"] = "move"
    path: tuple[Square, ...]


class DodgeIntent(_IntentBase):
    kind: Literal["dodge"] = "dodge"


class DashIntent(_IntentBase):
    kind: Literal["dash"] = "dash"


class DisengageIntent(_IntentBase):
    kind: Literal["disengage"] = "disengage"


class EndTurnIntent(_IntentBase):
    """Игрок завершает ход (явно). GameRunner после этого
    вызывает ``encounter.end_turn``."""

    kind: Literal["end_turn"] = "end_turn"


PlayerIntent = Annotated[
    AttackIntent
    | MoveIntent
    | DodgeIntent
    | DashIntent
    | DisengageIntent
    | EndTurnIntent,
    Field(discriminator="kind"),
]


__all__ = [
    "AttackIntent",
    "DashIntent",
    "DisengageIntent",
    "DodgeIntent",
    "EndTurnIntent",
    "MoveIntent",
    "PlayerIntent",
]
