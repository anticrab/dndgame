"""Боевые проверки на состязаниях (V2): Shove / Grapple / Hide.

Каждое действие — поверх ``opposed_check`` (Shove/Grapple) или
``roll_ability_check`` (Hide). Атлетика актёра против лучшей из Атлетики/
Акробатики цели; при успехе накладывается состояние через ``ConditionService``:

* **Shove** → Prone (толчок на 5 фт — задел, см. план V).
* **Grapple** → Grappled (скорость 0; guard в ``MoveAction``).
* **Hide** → Hidden (преимущество на следующую атаку; снимается в ``attack.py``).

Новое контест-действие (Disarm, Trip…) = ещё один класс здесь поверх
``opposed_check``, без правки ядра.
"""

from __future__ import annotations

from typing import ClassVar, Final

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import ConditionApplied
from dnd.application.engine.ability_check import (
    opposed_check_raw,
    passive_score,
    roll_ability_check_raw,
)
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import (
    GRAPPLED,
    HIDDEN,
    INCAPACITATED,
    PARALYZED,
    PRONE,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ActionId, ConditionId, CreatureId
from dnd.domain.values.skill import Skill

_ACTION_BLOCKERS: Final = frozenset({INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS})
# Защитные навыки в состязании на Толчок/Захват (PHB-2024 стр. 372).
_CONTEST_DEFENSE: Final[tuple[Skill, ...]] = (Skill.ATHLETICS, Skill.ACROBATICS)


class SkillActionParams(ActionParams):
    """Параметры боевой проверки: цель. Для Hide цель не обязательна."""

    target_id: CreatureId | None = None


def _check_blockers(actor: Creature, ctx: TurnContext) -> ActionAvailability:
    if not ctx.can_spend(ActionEconomyCost.ACTION):
        return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
    for cond in _ACTION_BLOCKERS:
        if actor.has_condition(cond):
            return Forbidden(reason=ForbiddenReason.CONDITION_BLOCKS_ACTION, details=cond)
    return Allowed()


class _ContestAction:
    """Общая база Shove/Grapple: состязание Атлетики в упор (≤5 фт)."""

    id_value: ClassVar[ActionId]
    name_key_value: ClassVar[str]
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.ACTION
    _applied_condition: ClassVar[ConditionId]

    @property
    def id(self) -> ActionId:
        return self.id_value

    @property
    def name_key(self) -> str:
        return self.name_key_value

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return self.economy_cost_value

    def can_perform(self, actor: Creature, ctx: TurnContext) -> ActionAvailability:
        return _check_blockers(actor, ctx)

    def can_perform_against(
        self, actor: Creature, params: SkillActionParams, ctx: TurnContext
    ) -> ActionAvailability:
        base = self.can_perform(actor, ctx)
        if isinstance(base, Forbidden):
            return base
        if params.target_id is None or params.target_id not in ctx.participants:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS, details="no target")
        actor_pos = ctx.battlefield.position_of(actor.id)
        target_pos = ctx.battlefield.position_of(params.target_id)
        if actor_pos.distance_to_feet(target_pos) > 5:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE, details="contest is melee (5 ft)")
        return Allowed()

    def execute(
        self, actor: Creature, params: SkillActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        ctx.spend(ActionEconomyCost.ACTION)
        assert params.target_id is not None
        target = ctx.participants[params.target_id]
        won = opposed_check_raw(
            actor,
            Skill.ATHLETICS,
            target,
            _CONTEST_DEFENSE,
            dice_roller=ctx.dice_roller,
            modifier_applier=ctx.modifier_applier,
            condition_service=ctx.condition_service,
        )
        if not won:
            return ActionOutcome(
                success=False,
                consumed=ActionEconomyCost.ACTION,
                events_published=(),
                notes="contest lost",
            )
        result = ctx.condition_service.apply_with_implies(target, self._applied_condition)
        if result.applied:
            ctx.event_bus.publish(
                ConditionApplied(
                    caster_id=actor.id,
                    target_id=target.id,
                    spell_id=None,
                    conditions=result.applied,
                )
            )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            events_published=("condition.applied",) if result.applied else (),
            notes=f"contest won → {self._applied_condition}",
        )


class ShoveAction(_ContestAction):
    """Толкнуть: Атлетика vs Атлетика/Акробатика → Prone (PHB-2024 стр. 372)."""

    id_value: ClassVar[ActionId] = ActionId("shove")
    name_key_value: ClassVar[str] = "action.shove"
    _applied_condition: ClassVar[ConditionId] = PRONE


class GrappleAction(_ContestAction):
    """Схватить: Атлетика vs Атлетика/Акробатика → Grappled (PHB-2024 стр. 372)."""

    id_value: ClassVar[ActionId] = ActionId("grapple")
    name_key_value: ClassVar[str] = "action.grapple"
    _applied_condition: ClassVar[ConditionId] = GRAPPLED


class HideAction:
    """Спрятаться: Скрытность vs пассивная Внимательность врагов рядом →
    Hidden (преимущество на следующую атаку). PHB-2024 стр. 368."""

    id_value: ClassVar[ActionId] = ActionId("hide")
    name_key_value: ClassVar[str] = "action.hide"
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

    def can_perform(self, actor: Creature, ctx: TurnContext) -> ActionAvailability:
        return _check_blockers(actor, ctx)

    def can_perform_against(
        self, actor: Creature, params: SkillActionParams, ctx: TurnContext
    ) -> ActionAvailability:
        return self.can_perform(actor, ctx)

    def _enemy_passive_perception(self, actor: Creature, ctx: TurnContext) -> int:
        """Порог = макс. пассивная Внимательность среди врагов (иначе 10)."""
        actor_faction = ctx.factions.get(actor.id)
        scores = [
            passive_score(creature, Skill.PERCEPTION)
            for cid, creature in ctx.participants.items()
            if cid != actor.id and ctx.factions.get(cid) != actor_faction
        ]
        return max(scores, default=10)

    def execute(
        self, actor: Creature, params: SkillActionParams, ctx: TurnContext
    ) -> ActionOutcome:
        ctx.spend(ActionEconomyCost.ACTION)
        dc = self._enemy_passive_perception(actor, ctx)
        hid = roll_ability_check_raw(
            actor,
            skill=Skill.STEALTH,
            dc=dc,
            dice_roller=ctx.dice_roller,
            modifier_applier=ctx.modifier_applier,
            condition_service=ctx.condition_service,
        )
        if not hid:
            return ActionOutcome(
                success=False,
                consumed=ActionEconomyCost.ACTION,
                events_published=(),
                notes=f"stealth < passive perception {dc}",
            )
        result = ctx.condition_service.apply_with_implies(actor, HIDDEN)
        if result.applied:
            ctx.event_bus.publish(
                ConditionApplied(
                    caster_id=actor.id,
                    target_id=actor.id,
                    spell_id=None,
                    conditions=result.applied,
                )
            )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            events_published=("condition.applied",) if result.applied else (),
            notes="hidden",
        )


__all__ = ["GrappleAction", "HideAction", "ShoveAction", "SkillActionParams"]
