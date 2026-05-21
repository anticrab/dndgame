"""MoveAction — пошаговое перемещение по клеткам.

См. ``docs/ACTIONS.md`` §2 и «Книгу Игрока 2024» стр. 22–24
(«Перемещение», «Перемещение около других существ»).

Что делает:

* ``can_perform`` — глобальные блокеры (incapacitated/paralyzed/stunned/
  unconscious снимают возможность двигаться: PHB-2024 стр. 367 для
  Incapacitated прямо — нет; для Paralyzed/Stunned speed=0; на MVP
  трактуем все они как блокер движения).
* ``can_perform_against`` — валидирует путь как набор соседних клеток
  в пределах карты и проходимый, проверяет суммарную стоимость с
  учётом difficult terrain.
* ``execute`` — пошагово перемещает actor по path; для каждого шага
  публикует ``MoveStepTaken``; перед уходом из reach-зоны живого
  threatener'а — ``OpportunityAttackProvoked`` (по одному на threatener'а
  за всё движение, PHB-2024 стр. 22). Disengage-флаг (E4) подавляет
  провокации.

Что **не** делает:

* не выбирает путь — путь приходит готовым в ``MoveParams``;
* не выполняет opportunity attack — публикует только триггер; сам
  reaction обрабатывает ``OpportunityAttack`` (E6);
* не моделирует «прерванное движение из-за реакции» — провокации
  публикуются всем, но реактивная атака приходит ПОСЛЕ MoveCompleted
  через подписку (в MVP — да; в полноценной модели реакция может
  прервать движение, это пост-MVP);
* не моделирует диагональ «5/10/5» из dungeon-руководства — стандарт
  MVP: каждый шаг (ортогональ или диагональ) стоит 5 фут (10, если
  входная клетка difficult).
"""

from __future__ import annotations

from typing import Final

from dnd.application.dto.action import (
    ActionAvailability,
    ActionEconomyCost,
    ActionOutcome,
    ActionParams,
    Allowed,
    Forbidden,
    ForbiddenReason,
)
from dnd.application.dto.engine_event import (
    MoveCompleted,
    MoveStepTaken,
    OpportunityAttackProvoked,
)
from dnd.application.dto.ids import ActionId, CreatureId
from dnd.application.engine.turn_context import TurnContext
from dnd.domain.conditions.builtin import (
    INCAPACITATED,
    PARALYZED,
    STUNNED,
    UNCONSCIOUS,
)
from dnd.domain.entities.creature import Creature
from dnd.domain.values.square import Square

# Состояния, отключающие движение в MVP.
_MOVEMENT_BLOCKERS: Final = frozenset(
    {INCAPACITATED, STUNNED, PARALYZED, UNCONSCIOUS}
)


class MoveParams(ActionParams):
    """Параметры движения.

    ``path`` — последовательность клеток в порядке прохождения,
    **не включая стартовую**. Первая клетка пути обязана быть соседней
    стартовой; каждая следующая — соседней предыдущей. Диагональ
    допустима.
    """

    path: tuple[Square, ...]


class MoveAction:
    """Действие перемещения. ``economy_cost = MOVEMENT`` (тратит футы,
    не Action).

    Один экземпляр на приложение — без состояния.
    """

    economy_cost_value: Final = ActionEconomyCost.MOVEMENT

    @property
    def id(self) -> ActionId:
        return ActionId("move")

    @property
    def name_key(self) -> str:
        return "action.move"

    @property
    def economy_cost(self) -> ActionEconomyCost:
        return self.economy_cost_value

    # --- can_perform ---------------------------------------------------

    def can_perform(
        self, actor: Creature, ctx: TurnContext
    ) -> ActionAvailability:
        for cond in _MOVEMENT_BLOCKERS:
            if actor.has_condition(cond):
                return Forbidden(
                    reason=ForbiddenReason.CONDITION_BLOCKS_ACTION,
                    details=cond,
                )
        if ctx.movement_remaining_ft <= 0:
            return Forbidden(reason=ForbiddenReason.NOT_ENOUGH_MOVEMENT)
        return Allowed()

    def can_perform_against(
        self,
        actor: Creature,
        params: MoveParams,
        ctx: TurnContext,
    ) -> ActionAvailability:
        """Проверка конкретного пути."""
        base = self.can_perform(actor, ctx)
        if isinstance(base, Forbidden):
            return base
        if not params.path:
            return Forbidden(
                reason=ForbiddenReason.INVALID_PATH,
                details="empty path",
            )

        start = ctx.battlefield.position_of(actor.id)
        prev = start
        total_cost = 0
        for step in params.path:
            if not ctx.battlefield.in_bounds(step):
                return Forbidden(
                    reason=ForbiddenReason.INVALID_PATH,
                    details=f"{step} out of bounds",
                )
            if not prev.is_adjacent(step):
                return Forbidden(
                    reason=ForbiddenReason.INVALID_PATH,
                    details=f"{prev} -> {step} not adjacent",
                )
            terrain = ctx.battlefield.terrain_at(step)
            if not terrain.passable:
                return Forbidden(
                    reason=ForbiddenReason.IMPASSABLE_TERRAIN,
                    details=str(step),
                )
            total_cost += 10 if terrain.difficult else 5
            prev = step

        if total_cost > ctx.movement_remaining_ft:
            return Forbidden(
                reason=ForbiddenReason.NOT_ENOUGH_MOVEMENT,
                details=f"need {total_cost}, have {ctx.movement_remaining_ft}",
            )
        return Allowed()

    # --- execute -------------------------------------------------------

    def execute(
        self,
        actor: Creature,
        params: ActionParams,
        ctx: TurnContext,
    ) -> ActionOutcome:
        if not isinstance(params, MoveParams):
            raise TypeError(
                f"MoveAction expects MoveParams, got {type(params).__name__}"
            )

        start_pos = ctx.battlefield.position_of(actor.id)
        prev = start_pos
        published: list[str] = []
        total_cost = 0

        # Кто потенциально угрожает на старте — собираем «реакторов»,
        # чтобы провоцировать каждого максимум один раз за всё движение
        # (PHB-2024 стр. 22: «provokes an opportunity attack» — одно
        # реакция-окно от threatener'а на одно действие движения).
        # Disengage подавляет всю эту механику.
        already_provoked: set[CreatureId] = set()
        threateners = (
            {}
            if ctx.disengaged
            else self._collect_threateners(actor, ctx)
        )

        for step in params.path:
            terrain = ctx.battlefield.terrain_at(step)
            cost = 10 if terrain.difficult else 5

            # Провокации: для тех threatener'ов, в чьей reach был prev,
            # но не будет step.
            for threat_id, reach_squares in threateners.items():
                if threat_id in already_provoked:
                    continue
                if prev in reach_squares and step not in reach_squares:
                    ctx.event_bus.publish(
                        OpportunityAttackProvoked(
                            actor_id=actor.id,
                            threatener_id=threat_id,
                            leaving_square=prev,
                        )
                    )
                    published.append("opportunity_attack.provoked")
                    already_provoked.add(threat_id)

            ctx.spend_movement(cost)
            ctx.battlefield.move_creature(actor.id, step)
            total_cost += cost

            ctx.event_bus.publish(
                MoveStepTaken(
                    actor_id=actor.id,
                    frm=prev,
                    to=step,
                    cost_ft=cost,
                    difficult=terrain.difficult,
                )
            )
            published.append("move.step_taken")
            prev = step

        ctx.event_bus.publish(
            MoveCompleted(
                actor_id=actor.id,
                start_pos=start_pos,
                end_pos=prev,
                steps=len(params.path),
                total_spent_ft=total_cost,
            )
        )
        published.append("move.completed")

        return ActionOutcome(
            success=True,
            consumed=ActionEconomyCost.MOVEMENT,
            events_published=tuple(published),
            movement_spent_ft=total_cost,
            notes=f"moved {len(params.path)} step(s), {total_cost} ft",
        )

    # --- helpers ------------------------------------------------------

    def _collect_threateners(
        self, actor: Creature, ctx: TurnContext
    ) -> dict[CreatureId, frozenset[Square]]:
        """Кто из живых participants на поле угрожает actor'у.

        Returns: map threatener_id → frozenset клеток его reach-зоны.
        Учитываем стандартный reach 5 фт; индивидуальный reach (глефа)
        придёт через данные существа, когда Character заведёт оружие.
        """
        result: dict[CreatureId, frozenset[Square]] = {}
        for other_id, other in ctx.participants.items():
            if other_id == actor.id or not other.is_alive:
                continue
            if not ctx.battlefield.has_creature(other_id):
                continue
            for blocker in _MOVEMENT_BLOCKERS:
                if other.has_condition(blocker):
                    break
            else:
                result[other_id] = ctx.battlefield.threatens_squares(other_id)
        return result


__all__ = ["MoveAction", "MoveParams"]
