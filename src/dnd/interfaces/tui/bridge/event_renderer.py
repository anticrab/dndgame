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
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from textual.css.query import NoMatches

from dnd.application.dto.engine_event import (
    AttackResolved,
    ConditionApplied,
    ConditionRemoved,
    CreatureDied,
    CreatureStabilized,
    DamageDealt,
    DeathSaveRolled,
    EncounterEnded,
    EngineEvent,
    HealingApplied,
    InitiativeRolled,
    LeveledUp,
    LevelUpReady,
    MoveCompleted,
    StanceTaken,
    TurnStarted,
)
from dnd.application.ports.event_bus import EventBus, Unsubscribe
from dnd.domain.values.faction import Faction

if TYPE_CHECKING:
    from dnd.application.engine.encounter import Encounter
    from dnd.application.engine.progression.level_up import LevelUpService
    from dnd.domain.values.ids import CreatureId
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
        level_up_service: LevelUpService | None = None,
    ) -> None:
        self._screen = screen
        self._encounter = encounter
        self._call_raw = call_from_thread
        # Поток, на котором создан renderer = поток приложения (main). События
        # обычно приходят из worker-потока (→ call_from_thread), но колбэк
        # LevelUpScreen «Сейчас!» публикует LeveledUp уже в main-потоке —
        # там call_from_thread бросает RuntimeError, поэтому зовём fn напрямую.
        self._main_thread_id = threading.get_ident()
        self._active_actor: CreatureId | None = None
        self._initiative_order: tuple[Any, ...] = ()
        # R1: применение level-up (по выбору игрока). None — прогрессия не
        # подключена (каркас/старые тесты).
        self._level_up = level_up_service
        self._pending_level_ups: list[LevelUpReady] = []

    def _call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        """Безопасно отправить callback в main-thread.

        Если мы уже в main-потоке (событие опубликовано прямо из колбэка
        UI, напр. level-up «Сейчас!») — call_from_thread бросил бы RuntimeError
        «must run in a different thread»; зовём fn напрямую (REV-3).

        Если event loop уже закрыт (app завершился, worker ещё доигрывает
        оставшиеся события) — call_from_thread кидает RuntimeError; гасим,
        иначе worker-thread пробросит pytest unraisable warning.
        """
        if threading.get_ident() == self._main_thread_id:
            fn(*args, **kwargs)
            return
        try:
            self._call_raw(fn, *args, **kwargs)
        except RuntimeError:
            _log.debug("EventRenderer: call_from_thread on closed loop")

    def subscribe(self, bus: EventBus) -> Unsubscribe:
        return bus.subscribe(EngineEvent, self._on_event)

    # --- dispatch -----------------------------------------------------

    def _on_event(self, event: EngineEvent) -> None:
        handler = _DISPATCH.get(type(event))
        if handler is not None:
            handler(self, event)
        # Лог обновляем для всех событий; виджет резолвится в main-thread.
        self._call(self._dispatch_log, event)

    def _on_initiative(self, event: InitiativeRolled) -> None:
        self._initiative_order = tuple(event.order)
        self._call(self._refresh_initiative_main)
        self._call(self._refresh_map_main)

    def _on_turn_started(self, event: TurnStarted) -> None:
        self._active_actor = event.actor_id
        self._call(self._refresh_initiative_main)
        self._call(self._refresh_status_main)
        if self._encounter.factions.get(event.actor_id) is not Faction.PARTY:
            self._call(self._clear_active_main)
        self._call(self._refresh_map_main)

    def _on_move(self, event: MoveCompleted) -> None:
        del event
        self._call(self._refresh_map_main)

    def _on_damage_or_attack(self, event: DamageDealt | AttackResolved) -> None:
        # HP мог измениться — статус активного актора И панель инициативы
        # (там видны HP всех бойцов; иначе HP цели «отстаёт» до след. хода).
        self._call(self._refresh_status_main)
        self._call(self._refresh_initiative_main)
        if isinstance(event, AttackResolved) and event.downed:
            self._call(self._refresh_map_main)

    def _on_hp_changed(self, event: EngineEvent) -> None:
        # HP/состояние изменились (лечение, level-up +HP, спасбросок от смерти,
        # стабилизация, смерть) — сразу отразить на статусе и в панели
        # инициативы (REV-2), иначе UI отстаёт до следующего хода.
        del event
        self._call(self._refresh_status_main)
        self._call(self._refresh_initiative_main)

    def _on_stance(self, event: StanceTaken) -> None:
        del event
        self._call(self._refresh_status_main)

    def _on_level_up_ready(self, event: LevelUpReady) -> None:
        if self._level_up is None:
            return
        self._call(self._show_level_up_main, event)

    def _on_encounter_ended(self, event: EncounterEnded) -> None:
        # Применить отложенные («После боя») level-up до экрана итога.
        if self._level_up is not None:
            for pending in self._pending_level_ups:
                actor = self._encounter.participants.get(pending.actor_id)
                if actor is not None:
                    self._level_up.apply(actor, to_level=pending.to_level, ctx=None)
            self._pending_level_ups = []
        self._call(self._refresh_map_main)
        self._call(self._refresh_initiative_main)
        self._call(self._show_end_screen_main, event)

    # --- main-thread helpers ------------------------------------------
    # Эти функции исполняются в main-thread (через call_from_thread).
    # Только здесь разрешено query_one и любое обращение к Textual DOM —
    # иначе мы рискуем race между worker'ом и event-loop'ом.

    def _dispatch_log(self, event: EngineEvent) -> None:
        try:
            self._screen.log_widget.handle_event(event)
        except NoMatches:
            return  # экран ещё не смонтирован — initial-event теряется

    def _refresh_map_main(self) -> None:
        try:
            self._screen.map_widget.refresh_from(
                self._encounter.battlefield, self._encounter.factions
            )
        except NoMatches:
            return

    def _refresh_initiative_main(self) -> None:
        try:
            self._screen.initiative_widget.refresh_from(
                self._initiative_order,
                self._encounter.participants,
                active_id=self._active_actor,
            )
        except NoMatches:
            return

    def _refresh_status_main(self) -> None:
        if self._active_actor is None:
            return
        actor = self._encounter.participants.get(self._active_actor)
        if actor is None:
            return
        try:
            # ctx=None: TurnContext знают только сами Action'ы.
            self._screen.status_widget.refresh_from(actor, None)
        except NoMatches:
            return

    def _clear_active_main(self) -> None:
        try:
            self._screen.clear_active_turn()
        except NoMatches:
            return

    def _show_level_up_main(self, event: LevelUpReady) -> None:
        # Импорт здесь — избежать цикла screens→bridge→screens.
        from dnd.interfaces.tui.screens.level_up_screen import LevelUpScreen

        svc = self._level_up
        if svc is None:
            return

        def _now() -> None:
            actor = self._encounter.participants.get(event.actor_id)
            if actor is not None:
                svc.apply(actor, to_level=event.to_level, ctx=None)

        def _later() -> None:
            self._pending_level_ups.append(event)

        try:
            self._screen.app.push_screen(LevelUpScreen(event, on_now=_now, on_later=_later))
        except NoMatches:
            return

    def _show_end_screen_main(self, event: EncounterEnded) -> None:
        # EndScreen — точка фокуса после боя; BattleScreen помечает
        # себя 'concluded', action-биндинги перестают реагировать.
        try:
            self._screen.mark_concluded()
        except NoMatches:
            return
        # Импорт здесь — чтобы избежать цикла screens→bridge→screens.
        from dnd.interfaces.tui.screens.end_screen import EndScreen

        self._screen.app.push_screen(EndScreen(event))


_DISPATCH: dict[type[EngineEvent], Callable[[EventRenderer, Any], None]] = {
    InitiativeRolled: lambda r, e: r._on_initiative(e),
    TurnStarted: lambda r, e: r._on_turn_started(e),
    MoveCompleted: lambda r, e: r._on_move(e),
    DamageDealt: lambda r, e: r._on_damage_or_attack(e),
    AttackResolved: lambda r, e: r._on_damage_or_attack(e),
    HealingApplied: lambda r, e: r._on_hp_changed(e),
    LeveledUp: lambda r, e: r._on_hp_changed(e),
    DeathSaveRolled: lambda r, e: r._on_hp_changed(e),
    CreatureStabilized: lambda r, e: r._on_hp_changed(e),
    CreatureDied: lambda r, e: r._on_hp_changed(e),
    ConditionApplied: lambda r, e: r._on_hp_changed(e),
    ConditionRemoved: lambda r, e: r._on_hp_changed(e),
    StanceTaken: lambda r, e: r._on_stance(e),
    LevelUpReady: lambda r, e: r._on_level_up_ready(e),
    EncounterEnded: lambda r, e: r._on_encounter_ended(e),
}


__all__ = ["EventRenderer"]
