"""InteractAction — взаимодействие с InteractableObject.

PHB-2024 стр. 21 «Object Interaction»: открыть/закрыть дверь, взять
предмет — это **бесплатное** действие, доступно 1 раз в ход. Открытие
запертой двери требует отдельной механики (ключ / Sleight of Hand /
взлом) — это пост-MVP.

Cost: FREE (через TurnContext.use_object_interaction).
Reach: 5ft (стандарт melee).
"""
from __future__ import annotations

from enum import StrEnum
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
from dnd.application.dto.engine_event import ObjectInteracted
from dnd.application.dto.ids import ActionId, ObjectId
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.object_kind import ObjectKind


class InteractKind(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    EXAMINE = "examine"


class InteractParams(ActionParams):
    target_object_id: ObjectId
    kind: InteractKind


_REACH_FT = 5


class InteractAction:
    """Бесплатное взаимодействие с интерактивным объектом (1/ход)."""

    id_value: ClassVar[ActionId] = ActionId("interact")
    name_key_value: ClassVar[str] = "action.interact"
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

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        """Free object-interaction: проверяем что в этом ходу ещё не
        потрачено (PHB-2024 стр. 21)."""
        if not ctx.can_use_object_interaction():
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        return Allowed()

    def can_perform_against(
        self,
        actor: Creature,
        params: InteractParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        base = self.can_perform(actor, ctx)
        if isinstance(base, Forbidden):
            return base
        # Reach 5ft.
        actor_pos = ctx.battlefield.position_of(actor.id)
        try:
            obj = ctx.battlefield.object_at(params.target_object_id)
        except KeyError:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        if actor_pos.distance_to_feet(obj.pos) > _REACH_FT:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        # Дополнительные kind-specific проверки.
        if params.kind is InteractKind.OPEN and obj.kind in (
            ObjectKind.DOOR, ObjectKind.CHEST
        ) and obj.state.get("locked"):
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"{obj.kind.value} is locked",
            )
        if params.kind is InteractKind.CLOSE and obj.kind is not ObjectKind.DOOR:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"{obj.kind.value} cannot be closed",
            )
        return Allowed()

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        if not isinstance(params, InteractParams):
            raise TypeError(
                f"InteractAction expects InteractParams, got {type(params).__name__}"
            )
        ctx.use_object_interaction()
        obj = ctx.battlefield.object_at(params.target_object_id)

        loot: tuple[str, ...] = ()
        if params.kind is InteractKind.OPEN:
            loot = tuple(obj.open())
        elif params.kind is InteractKind.CLOSE:
            obj.close()
        # EXAMINE — пока no-op, для будущего

        ctx.event_bus.publish(
            ObjectInteracted(
                actor_id=actor.id,
                object_id=obj.id,
                kind=params.kind.value,
                loot=loot,
            )
        )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.FREE,
            events_published=("object.interacted",),
            notes=f"interact: {params.kind.value} {obj.kind.value}",
        )


__all__ = ["InteractAction", "InteractKind", "InteractParams"]
