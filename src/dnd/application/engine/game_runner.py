"""GameRunner — главный цикл боя.

Изолирует «как идёт игра» от «кто принимает решения»:

* PC — спрашивает ``PlayerIntentProvider.next_intent`` повторно, пока
  не получит ``EndTurnIntent``;
* Monsters — делегирует ``take_monster_turn``.

Никакого UI / I/O — это application слой. UI подключается через
provider'ы и подписку на ``event_bus``.

См. ``docs/ACTIONS.md`` §3 (контракт TurnContext), ``docs/ENCOUNTER.md`` §3.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from dnd.application.dto.action import (
    ActionAvailability,
    Allowed,
    Forbidden,
)
from dnd.application.dto.action import NoParams as _NoParams
from dnd.application.dto.player_intent import (
    AttackIntent,
    BreakIntent,
    DashIntent,
    DisengageIntent,
    DodgeIntent,
    EndTurnIntent,
    InteractIntent,
    MoveIntent,
    PlayerIntent,
)
from dnd.application.engine.actions.attack import AttackAction
from dnd.application.engine.actions.break_object import BreakAction, BreakParams
from dnd.application.engine.actions.interact import InteractAction, InteractParams
from dnd.application.engine.actions.move import MoveAction, MoveParams
from dnd.application.engine.actions.stances import (
    DashAction,
    DisengageAction,
    DodgeAction,
)
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.application.engine.ai.simple_monster import (
    is_hostile_from_factions,
    take_monster_turn,
)
from dnd.application.engine.encounter import Encounter
from dnd.application.engine.turn_context import TurnContext
from dnd.application.ports.player_intent_provider import PlayerIntentProvider
from dnd.domain.entities.creature import Creature
from dnd.domain.values.faction import Faction

_log = logging.getLogger(__name__)

# Защита от бесконечного цикла intents за один ход PC — против багов
# провайдера, который никогда не возвращает EndTurnIntent.
_MAX_INTENTS_PER_TURN = 50


class GameRunner:
    """Главный цикл боя.

    Конструктор принимает provider для PC и опциональный обработчик
    хода монстров (по умолчанию — SimpleMonsterAI).
    """

    def __init__(
        self,
        *,
        intent_provider: PlayerIntentProvider,
        monster_turn: Callable[[Creature, TurnContext, Encounter], None]
        | None = None,
    ) -> None:
        self._intent_provider = intent_provider
        self._monster_turn = monster_turn or self._default_monster_turn

    def run(self, encounter: Encounter) -> None:
        """Прогнать бой от ``start()`` до ``EncounterEnded``.

        Encounter должен быть готов к старту (created, не started).
        После возврата ``encounter.is_concluded is True``.
        """
        encounter.start()
        while not encounter.is_concluded:
            actor_id = encounter.current_actor_id
            actor = encounter.participants[actor_id]
            ctx = encounter.start_turn()

            if not actor.is_alive or actor.is_at_zero_hp:
                encounter.end_turn()
                continue

            faction = encounter.factions[actor_id]
            if faction is Faction.PARTY:
                self._run_pc_turn(actor, ctx, encounter)
            else:
                self._monster_turn(actor, ctx, encounter)

            encounter.end_turn()

    # --- PC turn ------------------------------------------------------

    def _run_pc_turn(
        self, actor: Creature, ctx: TurnContext, encounter: Encounter
    ) -> None:
        """Опрашиваем provider до EndTurnIntent или предельного счётчика.

        Аудит 15 CL-R001: после каждого intent перепроверяем
        ``actor.is_alive`` / ``is_at_zero_hp`` — реакция OA (или AoE)
        может убить PC посреди его хода, и крутить дальше intent'ы
        нельзя (все Action'ы упрутся в условия и зациклимся до
        ``_MAX_INTENTS_PER_TURN``).
        """
        for _ in range(_MAX_INTENTS_PER_TURN):
            if not actor.is_alive or actor.is_at_zero_hp:
                return
            # Если исход боя уже решён (последний враг повержен этой
            # атакой) — выходим, не дожидаясь end_turn. Иначе игрок
            # получает ещё один prompt в уже законченном бою.
            if encounter.is_concluded or encounter.outcome_decided():
                return
            intent = self._intent_provider.next_intent(actor, ctx, encounter)
            if isinstance(intent, EndTurnIntent):
                return
            self._apply_intent(actor, intent, ctx, encounter)
        _log.warning(
            "max intents (%d) reached for actor=%s — ending turn",
            _MAX_INTENTS_PER_TURN,
            actor.id,
        )

    def _apply_intent(
        self,
        actor: Creature,
        intent: PlayerIntent,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> None:
        """Выполнить одно намерение. Невыполнимое (нет бюджета, цели,
        LoS) — молча игнорируется (для UI: при выборе действия UI
        должен проверять Allowed заранее; здесь мы безопасно идём
        дальше)."""
        if isinstance(intent, AttackIntent):
            self._do_attack(actor, intent, ctx)
            return
        if isinstance(intent, MoveIntent):
            self._do_move(actor, intent, ctx)
            return
        if isinstance(intent, DodgeIntent):
            self._do_stance(DodgeAction(), actor, ctx)
            return
        if isinstance(intent, DashIntent):
            self._do_stance(DashAction(), actor, ctx)
            return
        if isinstance(intent, DisengageIntent):
            self._do_stance(DisengageAction(), actor, ctx)
            return
        if isinstance(intent, InteractIntent):
            self._do_interact(actor, intent, ctx)
            return
        if isinstance(intent, BreakIntent):
            self._do_break(actor, intent, ctx)
            return
        # EndTurnIntent обрабатывается в _run_pc_turn до вызова.
        # Защита от расширения PlayerIntent без обновления GameRunner.
        raise TypeError(f"unknown PlayerIntent: {type(intent).__name__}")

    def _do_attack(
        self, actor: Creature, intent: AttackIntent, ctx: TurnContext
    ) -> None:
        if actor.equipped_weapon is None:
            self._log_rejected(actor, "attack", "no_equipped_weapon")
            return
        params = weapon_attack_params(actor, intent.target_id)
        attack = AttackAction()
        avail = attack.can_perform_against(actor, params, ctx)
        if isinstance(avail, Allowed):
            attack.execute(actor, params, ctx)
        else:
            self._log_rejected(actor, "attack", _avail_reason(avail))

    def _do_move(
        self, actor: Creature, intent: MoveIntent, ctx: TurnContext
    ) -> None:
        params = MoveParams(path=intent.path)
        move = MoveAction()
        avail = move.can_perform_against(actor, params, ctx)
        if isinstance(avail, Allowed):
            move.execute(actor, params, ctx)
        else:
            self._log_rejected(actor, "move", _avail_reason(avail))

    def _do_interact(
        self, actor: Creature, intent: InteractIntent, ctx: TurnContext
    ) -> None:
        params = InteractParams(
            target_object_id=intent.target_object_id,
            kind=intent.interact_kind,
        )
        action = InteractAction()
        avail = action.can_perform_against(actor, params, ctx)
        if isinstance(avail, Allowed):
            action.execute(actor, params, ctx)
        else:
            self._log_rejected(actor, "interact", _avail_reason(avail))

    def _do_break(
        self, actor: Creature, intent: BreakIntent, ctx: TurnContext
    ) -> None:
        """Атака по объекту экипированным оружием.

        attack_bonus / damage_expr / damage_type берём из
        ``weapon_attack_params`` — это даёт согласованный набор
        бонусов (proficiency + ability_mod) с обычной атакой по
        существу. ``target_id`` в построенном ``AttackParams`` не
        используется — нам нужны только числа, кость и тип урона.
        """
        if actor.equipped_weapon is None:
            self._log_rejected(actor, "break", "no_equipped_weapon")
            return
        # Используем actor.id как «фиктивную» цель для построения
        # AttackParams — нас интересуют поля attack_bonus / damage_expr /
        # damage_type. target_id не дойдёт до execute (BreakAction его
        # не использует).
        atk_params = weapon_attack_params(actor, actor.id)
        params = BreakParams(
            target_object_id=intent.target_object_id,
            attack_bonus=atk_params.attack_bonus,
            damage_expr=atk_params.damage_expr,
            damage_type=atk_params.damage_type,
        )
        action = BreakAction()
        avail = action.can_perform_against(actor, params, ctx)
        if isinstance(avail, Allowed):
            action.execute(actor, params, ctx)
        else:
            self._log_rejected(actor, "break", _avail_reason(avail))

    def _do_stance(
        self,
        action: DodgeAction | DashAction | DisengageAction,
        actor: Creature,
        ctx: TurnContext,
    ) -> None:
        avail = action.can_perform(actor, ctx)
        if isinstance(avail, Allowed):
            action.execute(actor, _NoParams(), ctx)
        else:
            self._log_rejected(
                actor, action.__class__.__name__.lower(), _avail_reason(avail)
            )

    @staticmethod
    def _log_rejected(actor: Creature, action_id: str, reason: str) -> None:
        """Логировать причину Forbidden-intent'а.

        Раньше невыполнимые intents молча проглатывались, и игрок не
        видел причины. Через `_log.info` UI (CLI/TUI) может подключить
        свой handler и показать notify-сообщение без введения нового
        EngineEvent.
        """
        _log.info(
            "intent rejected: actor=%s action=%s reason=%s",
            actor.id,
            action_id,
            reason,
        )

    # --- Monster turn -------------------------------------------------

    @staticmethod
    def _default_monster_turn(
        actor: Creature, ctx: TurnContext, encounter: Encounter
    ) -> None:
        predicate = is_hostile_from_factions(actor.id, encounter.factions)
        take_monster_turn(actor, ctx, is_hostile=predicate)


def _avail_reason(avail: ActionAvailability) -> str:
    if isinstance(avail, Forbidden):
        return f"{avail.reason.value}" + (
            f"({avail.details})" if avail.details else ""
        )
    return "unknown"


__all__ = ["GameRunner"]
