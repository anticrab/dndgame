"""BreakAction — атака по интерактивному объекту (бочка, дверь, окно).

PHB-2024 стр. 27 «Damaging Objects»: объект имеет AC и HP; атакующий
делает обычный attack roll vs object's AC; при попадании урон вычитается
из HP, при 0 HP — объект сломан (для двери = открыта).

Cost: ACTION. В отличие от AttackAction (creature target), BreakAction
имеет ``target_object_id`` и не использует cover/LoS rules (объект
статичен; cover irrelevant) — но reach 5ft melee всё же требуется.
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
from dnd.application.dto.engine_event import ObjectDamaged
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.damage import DamageInstance, DamageType
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import ActionId, ObjectId

_REACH_FT = 5


class BreakParams(ActionParams):
    target_object_id: ObjectId
    attack_bonus: int
    damage_expr: str
    damage_type: DamageType


class BreakAction:
    """Атака по интерактивному объекту с HP."""

    id_value: ClassVar[ActionId] = ActionId("break")
    name_key_value: ClassVar[str] = "action.break"
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

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        if not ctx.can_spend(ActionEconomyCost.ACTION):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        return Allowed()

    def can_perform_against(
        self,
        actor: Creature,
        params: BreakParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        base = self.can_perform(actor, ctx)
        if isinstance(base, Forbidden):
            return base
        try:
            obj = ctx.battlefield.object_at(params.target_object_id)
        except KeyError:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)
        actor_pos = ctx.battlefield.position_of(actor.id)
        if actor_pos.distance_to_feet(obj.pos) > _REACH_FT:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        # Объект должен иметь hp для break-логики (CHEST без hp = не сломать).
        if "hp" not in obj.state:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details=f"{obj.kind.value} has no hp",
            )
        return Allowed()

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        if not isinstance(params, BreakParams):
            raise TypeError(
                f"BreakAction expects BreakParams, got {type(params).__name__}"
            )
        ctx.spend(ActionEconomyCost.ACTION)
        obj = ctx.battlefield.object_at(params.target_object_id)
        ac = int(obj.state.get("ac", 10))

        # Attack roll.
        atk_expr = DiceExpr.parse(f"d20{params.attack_bonus:+d}")
        atk_ctx = RollContext(
            purpose=RollPurpose.ATTACK,
            actor_id=actor.id,
        )
        atk = ctx.dice_roller.roll(atk_expr, atk_ctx)
        hit = atk.total >= ac

        if not hit:
            return ActionOutcome(
                success=True,
                consumed=ActionEconomyCost.ACTION,
                notes=(
                    f"break: miss vs {obj.kind.value} "
                    f"(d20={atk.d20_raw or 0}, ac={ac})"
                ),
            )

        # Damage roll.
        dmg_expr = DiceExpr.parse(params.damage_expr)
        dmg_ctx = RollContext(
            purpose=RollPurpose.DAMAGE,
            actor_id=actor.id,
        )
        dmg = ctx.dice_roller.roll(dmg_expr, dmg_ctx)
        raw = max(0, dmg.total)

        result = obj.take_damage(
            DamageInstance(amount=raw, type_=params.damage_type)
        )

        ctx.event_bus.publish(
            ObjectDamaged(
                attacker_id=actor.id,
                object_id=obj.id,
                raw_amount=raw,
                final_amount=result.final,
                hp_after=int(obj.state.get("hp", 0)),
                broken=result.was_lethal,
            )
        )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            events_published=("object.damaged",),
            notes=f"break: dmg={result.final}, broken={result.was_lethal}",
        )


__all__ = ["BreakAction", "BreakParams"]
