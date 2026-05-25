"""SecondWindAction — Воин L1: bonus action, лечение 1d10 + level (этап R1).

Ресурс ``second_wind`` (1/short rest). Восстанавливается RestService'ом между
боями. Лечение — через Creature.heal (как cure_wounds).
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
from dnd.application.dto.engine_event import HealingApplied
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import ActionId

_RESOURCE = "second_wind"


class SecondWindParams(ActionParams):
    pass


class SecondWindAction:
    """Воин: Second Wind — bonus action, лечение 1d10 + уровень."""

    id_value: ClassVar[ActionId] = ActionId("second_wind")
    name_key_value: ClassVar[str] = "action.second_wind"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.BONUS_ACTION

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
            return Forbidden(reason=ForbiddenReason.CUSTOM, details="second wind used")
        if not ctx.can_spend(ActionEconomyCost.BONUS_ACTION):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        return Allowed()

    def execute(
        self, actor: Creature, params: ActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        if isinstance(self.can_perform_against(actor, params, ctx), Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)
        roll = ctx.dice_roller.roll(
            DiceExpr.parse("1d10"),
            RollContext(
                purpose=RollPurpose.OTHER, actor_id=actor.id, tags=("second_wind",)
            ),
        )
        amount = max(0, roll.total + actor.level)
        result = actor.heal(amount)
        actor.resource_uses[_RESOURCE] -= 1
        ctx.spend(ActionEconomyCost.BONUS_ACTION)
        ctx.event_bus.publish(
            HealingApplied(
                healer_id=actor.id, target_id=actor.id, amount=result.final_amount,
                hp_after=actor.hit_points.current, hp_max=actor.hit_points.maximum,
            )
        )
        return ActionOutcome(
            success=True, consumed=ActionEconomyCost.BONUS_ACTION, notes="second wind"
        )


__all__ = ["SecondWindAction", "SecondWindParams"]
