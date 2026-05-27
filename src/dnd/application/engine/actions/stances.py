"""Combat stances: Dodge / Dash / Disengage (этап E4).

См. ACTIONS.md §2 и «Книгу Игрока 2024» стр. 22 («Доступные действия»).

Все три — простые stance-actions без параметров (``NoParams``). Каждое
тратит Action и мутирует состояние хода и/или существа:

* ``DodgeAction`` — ставит ``CombatStance.DODGING`` на actor. Пока
  стойка активна и actor видит атакующего, атаки по нему — с помехой,
  его DEX-спасброски — с преимуществом (PHB-2024 стр. 22).
  Сброс — ``Encounter`` на старте следующего хода actor'а.
  **Реализовано:** ``AttackAction`` читает stance цели и навешивает
  disadvantage. DEX-saves — после реализации SavingThrowAction (вне MVP).
* ``DashAction`` — увеличивает ``ctx.movement_remaining_ft`` на
  ``actor.speed_ft`` (PHB-2024 стр. 22: «удваивает скорость на ход» =
  «дополнительное движение, равное скорости»).
* ``DisengageAction`` — ставит ``ctx.disengaged=True``. До конца хода
  выход из зон угрозы не провоцирует opportunity attacks
  (см. ``MoveAction``).
"""

from __future__ import annotations

from enum import StrEnum
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
from dnd.application.dto.engine_event import StanceTaken
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    PARALYZED,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.ids import ActionId

_ACTION_BLOCKERS: Final = frozenset(
    {INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS}
)


class CombatStance(StrEnum):
    """Значения для ``Creature.combat_stances``."""

    DODGING = "dodging"
    DASHING = "dashing"
    DISENGAGED = "disengaged"


def _check_action_blockers(
    actor: Creature,
    ctx: TurnContext,
    economy: ActionEconomyCost = ActionEconomyCost.ACTION,
) -> ActionAvailability:
    """Общая проверка can_perform: бюджет (по умолчанию ACTION; для Cunning
    Action — BONUS_ACTION) + блокирующие conditions."""
    if not ctx.can_spend(economy):
        return Forbidden(reason=ForbiddenReason.NO_ECONOMY_LEFT)
    for cond in _ACTION_BLOCKERS:
        if actor.has_condition(cond):
            return Forbidden(
                reason=ForbiddenReason.CONDITION_BLOCKS_ACTION,
                details=cond,
            )
    return Allowed()


class DodgeAction:
    """Стойка уклонения. PHB-2024 стр. 22."""

    id_value: ClassVar[ActionId] = ActionId("dodge")
    name_key_value: ClassVar[str] = "action.dodge"
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
        return _check_action_blockers(actor, ctx)

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        ctx.spend(ActionEconomyCost.ACTION)
        actor.combat_stances.add(CombatStance.DODGING.value)
        ctx.event_bus.publish(
            StanceTaken(actor_id=actor.id, stance=CombatStance.DODGING.value)
        )
        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.ACTION,
            events_published=("stance.taken",),
            notes="dodging until next turn",
        )


class DashAction:
    """Доп. движение, равное ``actor.speed_ft`` (PHB-2024 стр. 22).

    Допускается дважды за ход (Action + класс-fea: Cunning Action Плута
    через bonus action). Каждое разрешение тратит свой бюджет и
    прибавляет speed_ft ещё раз.
    """

    id_value: ClassVar[ActionId] = ActionId("dash")
    name_key_value: ClassVar[str] = "action.dash"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.ACTION

    def __init__(
        self, *, economy: ActionEconomyCost = ActionEconomyCost.ACTION
    ) -> None:
        # T4: Cunning Action (Плут L2) выполняет Dash бонусным действием.
        self._economy = economy

    @property
    def id(self) -> ActionId:
        return self.id_value

    @property
    def name_key(self) -> str:
        return self.name_key_value

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return self._economy

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        # Под Paralyzed/Stunned speed=0 — Dash смысла не имеет;
        # _ACTION_BLOCKERS уже это закрывает.
        return _check_action_blockers(actor, ctx, self._economy)

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        ctx.spend(self._economy)
        ctx.movement_remaining_ft += actor.speed_ft
        actor.combat_stances.add(CombatStance.DASHING.value)
        ctx.event_bus.publish(
            StanceTaken(actor_id=actor.id, stance=CombatStance.DASHING.value)
        )
        return ActionOutcome(
            success=True,
            consumed=self._economy,
            events_published=("stance.taken",),
            notes=f"+{actor.speed_ft} ft movement this turn",
        )


class DisengageAction:
    """Отступление: до конца хода твоё движение не провоцирует AoO
    (PHB-2024 стр. 22). Флаг читает ``MoveAction``."""

    id_value: ClassVar[ActionId] = ActionId("disengage")
    name_key_value: ClassVar[str] = "action.disengage"
    economy_cost_value: ClassVar[ActionEconomyCost] = ActionEconomyCost.ACTION

    def __init__(
        self, *, economy: ActionEconomyCost = ActionEconomyCost.ACTION
    ) -> None:
        # T4: Cunning Action (Плут L2) выполняет Disengage бонусным действием.
        self._economy = economy

    @property
    def id(self) -> ActionId:
        return self.id_value

    @property
    def name_key(self) -> str:
        return self.name_key_value

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return self._economy

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        return _check_action_blockers(actor, ctx, self._economy)

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        ctx.spend(self._economy)
        ctx.disengaged = True
        actor.combat_stances.add(CombatStance.DISENGAGED.value)
        ctx.event_bus.publish(
            StanceTaken(actor_id=actor.id, stance=CombatStance.DISENGAGED.value)
        )
        return ActionOutcome(
            success=True,
            consumed=self._economy,
            events_published=("stance.taken",),
            notes="disengaged: no opportunity attacks this turn",
        )


__all__ = [
    "CombatStance",
    "DashAction",
    "DisengageAction",
    "DodgeAction",
]
