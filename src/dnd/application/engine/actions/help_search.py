"""Help и Search actions (этап E5).

PHB-2024 стр. 22:

* **Help** — даёт союзнику advantage на следующую атаку по конкретной
  цели (или дублирует ability-check, в MVP делаем только attack-вариант).
  Соблюдается реалистичное правило: ``helper`` должен быть в 5 фт от цели
  (PHB-2024: «within 5 feet of the creature being attacked»). Алли
  должен видеть цель — на MVP не проверяем (UI/AI решит).
* **Search** — бросок Wisdom (Perception) или Intelligence
  (Investigation). Конкретное «что найдено» — забота сценария-handler'а,
  подписанного на ``SearchPerformed``.

В MVP:

* HelpAction.execute ставит ``ally.helped_against = target_id``;
  AttackAction.execute читает поле и обнуляет его после использования.
* SearchAction.execute бросает d20 + ``skill_mod`` (приходит в params,
  как ability+proficiency), публикует ``SearchPerformed`` с roll_id.
  Сценарий-подписчик потом решает, что обнаружено.
"""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar, Final

from pydantic import Field

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import HelpGranted, SearchPerformed
from dnd.application.dto.rolls import RollContext, RollPurpose
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    PARALYZED,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.dice import DiceExpr
from dnd.domain.values.ids import ActionId, CreatureId

_ACTION_BLOCKERS: Final = frozenset({INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS})

_HELP_REACH_FT = 5  # PHB-2024 стр. 22: «within 5 feet of the creature being attacked»


# -- Help ----------------------------------------------------------------


class HelpParams(ActionParams):
    """Параметры Help: помогающий вручает преимущество ``ally`` на
    следующую атаку по ``target``."""

    ally_id: CreatureId
    target_id: CreatureId


class HelpAction:
    """Помощь союзнику в атаке.

    PHB-2024 стр. 22, вариант «assist an attack».
    """

    id_value: ClassVar[ActionId] = ActionId("help")
    name_key_value: ClassVar[str] = "action.help"
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
        if not ctx.can_spend(ActionEconomyCost.ACTION):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        for cond in _ACTION_BLOCKERS:
            if actor.has_condition(cond):
                return Forbidden(
                    reason=ForbiddenReason.CONDITION_BLOCKS_ACTION,
                    details=cond,
                )
        return Allowed()

    def can_perform_against(
        self,
        actor: Creature,
        params: HelpParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        base = self.can_perform(actor, ctx)
        if isinstance(base, Forbidden):
            return base

        ally = ctx.participants.get(params.ally_id)
        target = ctx.participants.get(params.target_id)
        if ally is None or target is None or ally.id == actor.id:
            return Forbidden(reason=ForbiddenReason.NO_VALID_TARGETS)

        # Helper должен быть в 5 фт от **цели** (PHB-2024).
        helper_pos = ctx.battlefield.position_of(actor.id)
        target_pos = ctx.battlefield.position_of(target.id)
        if helper_pos.distance_to_feet(target_pos) > _HELP_REACH_FT:
            return Forbidden(reason=ForbiddenReason.OUT_OF_RANGE)
        return Allowed()

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        if not isinstance(params, HelpParams):
            raise TypeError(f"HelpAction expects HelpParams, got {type(params).__name__}")
        ally = ctx.participants.get(params.ally_id)
        if ally is None:
            raise RuntimeError(
                f"contract violation: ally {params.ally_id!r} not in "
                f"participants; HelpAction.can_perform_against must be called"
            )

        ctx.spend(ActionEconomyCost.ACTION)
        ally.helped_against = params.target_id
        ally.helped_by = actor.id

        ctx.event_bus.publish(
            HelpGranted(
                helper_id=actor.id,
                ally_id=params.ally_id,
                target_id=params.target_id,
            )
        )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            events_published=("help.granted",),
            notes=f"{actor.id} helps {params.ally_id} vs {params.target_id}",
        )


# -- Search --------------------------------------------------------------


class SearchKind(StrEnum):
    """Навыки действия Search по PHB-2024 стр. 357.

    Книга прямо называет четыре варианта, все на основе Wisdom: Insight,
    Medicine, Perception, Survival. Investigation (Intelligence) в этой
    таблице **не упомянут** и относится к другим способам поиска (вне
    действия Search).
    """

    INSIGHT = "insight"  # Wisdom (Insight) — «прочитать намерения»
    MEDICINE = "medicine"  # Wisdom (Medicine) — «понять состояние»
    PERCEPTION = "perception"  # Wisdom (Perception) — «заметить»
    SURVIVAL = "survival"  # Wisdom (Survival) — «найти следы»


class SearchParams(ActionParams):
    """Параметры Search.

    ``skill_mod`` — сборный модификатор: Wisdom-mod + proficiency (если
    есть). Ситуативные модификаторы — через ModifierApplier.
    """

    kind: SearchKind
    skill_mod: int = Field(ge=-10, le=20)


class SearchAction:
    """Поиск чего-то скрытого. Бросок ability-check; конкретные DC и
    «что нашли» — на стороне сценария."""

    id_value: ClassVar[ActionId] = ActionId("search")
    name_key_value: ClassVar[str] = "action.search"
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
        if not ctx.can_spend(ActionEconomyCost.ACTION):
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        for cond in _ACTION_BLOCKERS:
            if actor.has_condition(cond):
                return Forbidden(
                    reason=ForbiddenReason.CONDITION_BLOCKS_ACTION,
                    details=cond,
                )
        return Allowed()

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        if not isinstance(params, SearchParams):
            raise TypeError(f"SearchAction expects SearchParams, got {type(params).__name__}")

        ctx.spend(ActionEconomyCost.ACTION)

        expr = DiceExpr.parse(f"d20{params.skill_mod:+d}")
        roll_ctx = RollContext(
            purpose=RollPurpose.ABILITY_CHECK,
            actor_id=actor.id,
            tags=(params.kind.value,),
        )
        roll = ctx.dice_roller.roll(expr, roll_ctx)

        ctx.event_bus.publish(
            SearchPerformed(
                actor_id=actor.id,
                skill_kind=params.kind.value,
                roll_id=roll.roll_id,
                total=roll.total,
            )
        )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            events_published=("search.performed",),
            notes=f"{params.kind.value} check = {roll.total}",
        )


__all__ = [
    "HelpAction",
    "HelpParams",
    "SearchAction",
    "SearchKind",
    "SearchParams",
]
