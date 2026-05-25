"""ActionSurgeAction — Воин L2: одно дополнительное действие в этом ходу (R1).

PHB-2024: активация Action Surge не стоит действия (FREE), но восстанавливает
возможность взять ещё одно Action в текущем ходу. Ресурс ``action_surge``
(1/short rest).
"""
from __future__ import annotations

from typing import ClassVar

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ActionId

_RESOURCE = "action_surge"


class ActionSurgeParams(ActionParams):
    pass


class ActionSurgeAction:
    """Воин: Action Surge — даёт дополнительное действие в текущем ходу."""

    id_value: ClassVar[ActionId] = ActionId("action_surge")
    name_key_value: ClassVar[str] = "action.action_surge"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.FREE

    @property
    def id(self) -> ActionId:
        return self.id_value

    @property
    def name_key(self) -> str:
        return self.name_key_value

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return self.economy_cost_value

    def can_perform_against(
        self, actor: Creature, params: ActionParams, ctx: TurnContext
    ) -> ActionAvailability:
        if actor.resource_uses.get(_RESOURCE, 0) <= 0:
            return Forbidden(reason=ForbiddenReason.CUSTOM, details="action surge used")
        return Allowed()

    def execute(
        self, actor: Creature, params: ActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        if isinstance(self.can_perform_against(actor, params, ctx), Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)
        actor.resource_uses[_RESOURCE] -= 1
        # Доп. действие: освобождаем слот ACTION на этот ход (PHB-2024).
        ctx.action_used = False
        return ActionOutcome(
            success=True, consumed=ActionEconomyCost.FREE, notes="action surge"
        )


__all__ = ["ActionSurgeAction", "ActionSurgeParams"]
