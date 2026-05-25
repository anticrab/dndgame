"""OpportunityAttack — атака по возможности (reaction-action).

PHB-2024 стр. 22 («Перемещение около других существ»).

Триггер — `OpportunityAttackProvoked` (публикует ``MoveAction`` при
выходе цели из reach живого, способного реагировать threatener'а).
Само событие — это **сигнал**, не вызов action'а. Получив сигнал,
``Encounter`` / UI / AI решает, выполнить ли реакцию, и вызывает
``OpportunityAttack.can_perform_against`` → ``execute`` с обычными
``AttackParams``.

Отличия от ``AttackAction``:

* ``economy_cost = REACTION`` — реакция per-creature per-round
  (``Creature.reaction_used``), не per-turn (``TurnContext.reaction_used``).
  Реакция случается в **чужой** ход, ``ctx`` принадлежит двигающемуся,
  поэтому экономика хранится на самой Creature.
* В остальном — та же логика: те же AttackParams, тот же путь
  to-hit → cover → damage → события (``AttackRolled``, ``DamageDealt``,
  ``AttackResolved``).

Сам факт «эта атака — реакция» отражается в ``economy_cost`` и в
``ActionOutcome.consumed``; событие движка не отличается (это всё
ещё стандартный AttackResolved).
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
from dnd.application.engine.actions.attack import (
    AttackAction,
    AttackKind,
    AttackParams,
)
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ActionId


class OpportunityAttack(AttackAction):
    """Атака по возможности — reaction-режим стандартной атаки.

    Параметры — тот же ``AttackParams`` (то же оружие, та же цель).
    """

    id_value: ClassVar[ActionId] = ActionId("opportunity_attack")
    name_key_value: ClassVar[str] = "action.opportunity_attack"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.REACTION

    def can_perform_against(
        self,
        actor: Creature,
        params: AttackParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        """OA — только **melee** атака (PHB-2024 стр. 22: «one melee
        attack»). Ranged-OA через AttackKind.RANGED запрещён.

        Аудит 12 OA-R001.
        """
        if params.kind is not AttackKind.MELEE:
            return Forbidden(
                reason=ForbiddenReason.CUSTOM,
                details="opportunity attack must be melee",
            )
        return super().can_perform_against(actor, params, ctx)

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        """Защита от прямого вызова execute с RANGED-параметрами
        (минуя can_perform_against): аудит 12 OA-R001.
        """
        if isinstance(params, AttackParams) and params.kind is not AttackKind.MELEE:
            raise RuntimeError(
                "contract violation: OpportunityAttack accepts only "
                "AttackKind.MELEE; can_perform_against must be called first"
            )
        return super().execute(actor, params, ctx)

    def _check_economy(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        """Reaction-бюджет: per-creature per-round (PHB-2024 стр. 22).

        Игнорируем ``ctx.reaction_used`` — он принадлежит хозяину
        ``TurnContext`` (двигающемуся), а реактор — это
        **другое** существо, чья реакция расходуется отдельно.
        """
        if actor.reaction_used:
            return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
        return Allowed()

    def _spend_economy(self, actor: Creature, ctx: TurnContext) -> None:
        actor.reaction_used = True


__all__ = ["OpportunityAttack"]
