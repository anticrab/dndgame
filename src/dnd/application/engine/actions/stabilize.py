"""StabilizeAction — стабилизировать союзника в 0 HP (Медицина DC 10).

PHB-2024 стр. 27: действие, проверка Мудрость(Медицина) против Сл. 10.
Успех → существо становится стабильным (DeathSaveState.stabilized()):
спасброски прекращаются, но в сознание оно не приходит (нужно лечение).

Cost: ACTION. Reach: 5 фт.
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
from dnd.application.dto.engine_event import CreatureStabilized
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ability import Ability
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import ActionId, CreatureId

_MEDICINE_DC = 10
_REACH_FT = 5


class StabilizeParams(ActionParams):
    target_id: CreatureId


class StabilizeAction:
    """Стабилизация умирающего союзника проверкой Медицины (PHB-2024 стр. 27)."""

    id_value: ClassVar[ActionId] = ActionId("stabilize")
    name_key_value: ClassVar[str] = "action.stabilize"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.ACTION

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
        self,
        actor: Creature,
        params: StabilizeParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        if not ctx.can_spend(ActionEconomyCost.ACTION):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        target = ctx.participants.get(params.target_id)
        if target is None:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        # Стабилизировать можно только умирающего: dying, не stable, не dead.
        if target.death_saves is None or target.death_saves.is_dead or target.death_saves.is_stable:
            return Forbidden(
                reason=ForbiddenReason.NO_VALID_TARGETS,
                details="target is not dying",
            )
        actor_pos = ctx.battlefield.position_of(actor.id)
        target_pos = ctx.battlefield.position_of(target.id)
        if actor_pos.distance_to_feet(target_pos) > _REACH_FT:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        return Allowed()

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        if not isinstance(params, StabilizeParams):
            raise TypeError(f"StabilizeAction expects StabilizeParams, got {type(params).__name__}")
        avail = self.can_perform_against(actor, params, ctx)
        if isinstance(avail, Forbidden):
            return ActionOutcome(success=False, consumed=ActionEconomyCost.FREE)

        ctx.spend(ActionEconomyCost.ACTION)
        target = ctx.participants[params.target_id]
        wis_mod = actor.abilities.modifier(Ability.WIS)
        roll = ctx.dice_roller.roll(
            DiceExpr.parse(f"d20{wis_mod:+d}"),
            RollContext(
                purpose=RollPurpose.ABILITY_CHECK,
                actor_id=actor.id,
                tags=("medicine", "stabilize"),
            ),
        )
        if roll.total >= _MEDICINE_DC and target.death_saves is not None:
            target.death_saves = target.death_saves.stabilized()
            ctx.event_bus.publish(CreatureStabilized(actor_id=target.id, by=actor.id))
            return ActionOutcome(
                success=True,
                consumed=ActionEconomyCost.ACTION,
                events_published=("encounter.creature_stabilized",),
                notes=f"stabilized {target.id} (Medicine {roll.total} vs DC {_MEDICINE_DC})",
            )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            notes=f"stabilize failed (Medicine {roll.total} vs DC {_MEDICINE_DC})",
        )


__all__ = ["StabilizeAction", "StabilizeParams"]
