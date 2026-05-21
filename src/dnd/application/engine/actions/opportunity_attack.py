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
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.ids import ActionId
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.entities.creature import Creature


class OpportunityAttack(AttackAction):
    """Атака по возможности — reaction-режим стандартной атаки.

    Параметры — тот же ``AttackParams`` (то же оружие, та же цель).
    """

    id_value: ClassVar[ActionId] = ActionId("opportunity_attack")
    name_key_value: ClassVar[str] = "action.opportunity_attack"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.REACTION

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
