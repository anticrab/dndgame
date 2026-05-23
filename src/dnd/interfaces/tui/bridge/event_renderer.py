"""EventRenderer — подписчик ``EventBus`` для TUI.

Принимает события из worker-thread'а GameRunner'а и шлёт обновления
виджетам **только** через ``app.call_from_thread`` — это thread-safe
API Textual для записи из не-event-loop треда. См. ``docs/TUI.md`` §4.

Ответственность строго ограничена маршрутизацией: какие события в
какие виджеты идут, какие данные собираются из ``Encounter``.
Форматирование строк — внутри самих виджетов (или их форматтеров).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from dnd.application.dto.engine_event import (
    AttackResolved,
    DamageDealt,
    EncounterEnded,
    EngineEvent,
    InitiativeRolled,
    MoveCompleted,
    StanceTaken,
    TurnStarted,
)
from dnd.application.ports.event_bus import EventBus, Unsubscribe
from dnd.domain.values.faction import Faction

if TYPE_CHECKING:
    from dnd.application.dto.ids import CreatureId
    from dnd.application.engine.encounter import Encounter
    from dnd.interfaces.tui.screens.battle import BattleScreen

_log = logging.getLogger(__name__)


class EventRenderer:
    """Маршрутизатор событий → виджеты ``BattleScreen``.

    Принимает функцию-обёртку ``call_from_thread`` — на проде это
    ``app.call_from_thread`` (Textual), в тестах можно подменить на
    прямой вызов для проверки логики без поднятия event-loop.
    """

    def __init__(
        self,
        screen: BattleScreen,
        encounter: Encounter,
        call_from_thread: Callable[..., Any],
    ) -> None:
        self._screen = screen
        self._encounter = encounter
        self._call = call_from_thread
        self._active_actor: CreatureId | None = None
        self._initiative_order: tuple[Any, ...] = ()

    def subscribe(self, bus: EventBus) -> Unsubscribe:
        return bus.subscribe(EngineEvent, self._on_event)

    # --- dispatch -----------------------------------------------------

    def _on_event(self, event: EngineEvent) -> None:
        try:
            handler = _DISPATCH.get(type(event))
            if handler is not None:
                handler(self, event)
            # Лог обновляем для всех событий — он сам решит, что вывести.
            self._call(self._screen.log_widget.handle_event, event)
        except Exception:
            _log.exception("EventRenderer: handler raised on %r", event)

    def _on_initiative(self, event: InitiativeRolled) -> None:
        self._initiative_order = tuple(event.order)
        self._refresh_initiative()
        self._refresh_map()

    def _on_turn_started(self, event: TurnStarted) -> None:
        self._active_actor = event.actor_id
        self._refresh_initiative()
        actor = self._encounter.participants.get(event.actor_id)
        if actor is not None:
            # TurnContext доступен только внутри start_turn(); здесь
            # передаём None — StatusWidget покажет «без экономии».
            self._call(self._screen.status_widget.refresh_from, actor, None)
        # Не-PC ход: убираем активное состояние, action-клавиши
        # будут игнорироваться. set_active_turn вызывается из
        # TuiIntentProvider.turn_signal, когда дойдёт до PC.
        if self._encounter.factions.get(event.actor_id) is not Faction.PARTY:
            self._call(self._screen.clear_active_turn)
        self._refresh_map()

    def _on_move(self, event: MoveCompleted) -> None:
        del event
        self._refresh_map()

    def _on_damage_or_attack(self, event: DamageDealt | AttackResolved) -> None:
        # Перерисовка статуса актуального актора (HP мог измениться).
        if self._active_actor is None:
            return
        actor = self._encounter.participants.get(self._active_actor)
        if actor is not None:
            self._call(self._screen.status_widget.refresh_from, actor, None)
        if isinstance(event, AttackResolved) and event.downed:
            self._refresh_map()
            self._refresh_initiative()

    def _on_stance(self, event: StanceTaken) -> None:
        del event
        if self._active_actor is None:
            return
        actor = self._encounter.participants.get(self._active_actor)
        if actor is not None:
            self._call(self._screen.status_widget.refresh_from, actor, None)

    def _on_encounter_ended(self, event: EncounterEnded) -> None:
        del event
        self._refresh_map()
        self._refresh_initiative()

    # --- helpers ------------------------------------------------------

    def _refresh_map(self) -> None:
        self._call(
            self._screen.map_widget.refresh_from,
            self._encounter.battlefield,
            self._encounter.factions,
        )

    def _refresh_initiative(self) -> None:
        self._call(
            self._screen.initiative_widget.refresh_from,
            self._initiative_order,
            self._encounter.participants,
            self._active_actor,
        )


_DISPATCH: dict[type[EngineEvent], Callable[[EventRenderer, Any], None]] = {
    InitiativeRolled: lambda r, e: r._on_initiative(e),
    TurnStarted: lambda r, e: r._on_turn_started(e),
    MoveCompleted: lambda r, e: r._on_move(e),
    DamageDealt: lambda r, e: r._on_damage_or_attack(e),
    AttackResolved: lambda r, e: r._on_damage_or_attack(e),
    StanceTaken: lambda r, e: r._on_stance(e),
    EncounterEnded: lambda r, e: r._on_encounter_ended(e),
}


__all__ = ["EventRenderer"]
