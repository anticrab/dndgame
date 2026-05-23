"""BattleScreen — основной экран боя.

См. ``docs/TUI.md`` §6 и mockup A.1 (80×24 layout).

Раскладка::

    ┌─ STATUS ────────────────────────────────┐
    │ Aelar HP 12/12 AC 16 …                  │
    ├─ MAP ──────────────────────┬─ INIT ──────┤
    │ ##########                 │ 1 ▶ Aelar 14│
    │ #...@....#                 │ 2  Goblin 11│
    │ #..g.g...#                 │             │
    ├─ LOG ──────────────────────┴─ ACTIONS ──┤
    │ > Aelar attacks Goblin A: hit, 9 dmg.   │
    │ ...                                     │
    └─────────────────────────────────────────┘

Action-меню — через `BINDINGS` (см. ниже). Handlers формируют
`PlayerIntent` и кладут его в `intent_queue` (см. TuiIntentProvider).
Для Attack/Move открываются модальные picker'ы; всё остальное —
без диалога.
"""

from __future__ import annotations

import queue
from typing import TYPE_CHECKING, ClassVar

from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Header

from dnd.application.dto.action import Allowed
from dnd.application.dto.ids import CreatureId, ObjectId
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
from dnd.application.engine.actions.interact import InteractKind
from dnd.application.engine.actions.weapon_attack import weapon_attack_params
from dnd.domain.values.faction import Faction
from dnd.interfaces.tui.screens.move_picker import MovePicker
from dnd.interfaces.tui.screens.target_picker import TargetPicker
from dnd.interfaces.tui.widgets import (
    InitiativeWidget,
    LogWidget,
    MapWidget,
    StatusWidget,
)

if TYPE_CHECKING:
    from dnd.application.engine.encounter import Encounter
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


class BattleScreen(Screen[None]):
    """Главный экран боя.

    Конструктор:
      * ``intent_queue`` — куда складывать intent'ы для worker'a;
      * ``state_provider`` — функция, возвращающая (actor, ctx, encounter)
        текущего хода. Вызывается из обработчиков клавиш сразу при
        нажатии — состояние всегда свежее. Полю присваивается
        EventRenderer'ом в TurnStarted.

    После полного монтирования (виджеты доступны через query_one)
    шлёт ``Ready`` сообщение — TuiApp ловит и стартует bridge+worker.
    Это снимает гонку «event пришёл раньше, чем DOM собран».
    """

    class Ready(Message):
        """Экран смонтирован, виджеты готовы к обновлению."""

    BINDINGS: ClassVar[list[BindingType]] = [
        ("a", "intent_attack", "Attack"),
        ("m", "intent_move", "Move"),
        ("d", "intent_dodge", "Dodge"),
        ("h", "intent_dash", "Dash"),
        ("g", "intent_disengage", "Disengage"),
        ("i", "intent_interact", "Interact"),
        ("k", "intent_break", "Break"),
        ("e", "intent_end_turn", "End turn"),
        # Zoom-toggle (K5-T3, medium ↔ small). Три формы клавиши: `+` и
        # `=` (на большинстве раскладок `+` — это Shift+`=`, но Textual
        # видит литерал `=` как `equals_sign`), `-` для симметрии.
        ("plus", "toggle_zoom", "Zoom"),
        ("equals_sign", "toggle_zoom", "Zoom"),
        ("minus", "toggle_zoom", "Zoom"),
        ("q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        *,
        intent_queue: queue.Queue[PlayerIntent] | None = None,
    ) -> None:
        super().__init__()
        self._intent_queue = intent_queue
        # Заполняется TuiIntentProvider'ом через turn_signal: даёт
        # обработчикам клавиш доступ к свежим actor / ctx / encounter
        # без таскания их через виджеты.
        self._current: tuple[Creature, TurnContext, Encounter] | None = None
        # Помечается renderer'ом после EncounterEnded — action-биндинги
        # сразу выходят, чтобы игрок не «жал в пустоту» после победы.
        self._concluded: bool = False

    # --- public API для bridge --------------------------------------

    def set_active_turn(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> None:
        """Bridge зовёт это в main-thread (через call_from_thread)
        каждый раз, когда PC получает ход. Состояние сохраняется
        для action-handlers, статус-виджет обновляется."""
        self._current = (actor, ctx, encounter)
        self.status_widget.refresh_from(actor, ctx)

    def clear_active_turn(self) -> None:
        """Сбросить состояние (вне-PC ход). Дополнительная защита от
        случайного нажатия action-клавиши на чужом ходу."""
        self._current = None

    def mark_concluded(self) -> None:
        """Бой завершён — action-биндинги перестают реагировать."""
        self._concluded = True
        self._current = None

    # --- compose ----------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield StatusWidget(id="status")
        with Horizontal(id="battle-row"):
            yield MapWidget(id="map")
            yield InitiativeWidget(id="init")
        yield LogWidget(id="log", wrap=True, highlight=True, markup=True, max_lines=200)
        yield Footer()

    def on_mount(self) -> None:
        # Все виджеты уже смонтированы — можно сигналить bridge.
        self.post_message(self.Ready())

    # --- accessors --------------------------------------------------

    @property
    def map_widget(self) -> MapWidget:
        return self.query_one("#map", MapWidget)

    @property
    def status_widget(self) -> StatusWidget:
        return self.query_one("#status", StatusWidget)

    @property
    def initiative_widget(self) -> InitiativeWidget:
        return self.query_one("#init", InitiativeWidget)

    @property
    def log_widget(self) -> LogWidget:
        return self.query_one("#log", LogWidget)

    # --- intent helpers ---------------------------------------------

    def _put_intent(self, intent: PlayerIntent) -> None:
        if self._intent_queue is not None:
            self._intent_queue.put(intent)
        # Дальнейшие нажатия до начала следующего хода — игнорируем.
        self._current = None

    # --- action handlers --------------------------------------------

    def action_intent_attack(self) -> None:
        if self._concluded or self._current is None:
            return
        actor, ctx, encounter = self._current
        targets = _list_reachable_hostiles(actor, ctx, encounter)
        if not targets:
            # bold вместо цвета — работает в обеих темах.
            self.log_widget.write("[bold]No reachable targets.[/]")
            return

        # TargetPicker принимает list[tuple[str, str]] — оборачиваем
        # CreatureId в str (NewType → str), а на выходе обратно в
        # CreatureId. Это нужно, чтобы тот же picker подошёл и для
        # ObjectId (Interact / Break).
        labels: list[tuple[str, str]] = [
            (
                str(cid),
                f"{cid} (HP {encounter.participants[cid].hit_points.current}/"
                f"{encounter.participants[cid].hit_points.maximum})",
            )
            for cid in targets
        ]

        def _on_pick(result: str | None) -> None:
            if result is None:
                return
            self._put_intent(AttackIntent(target_id=CreatureId(result)))

        self.app.push_screen(TargetPicker(labels), _on_pick)

    def action_intent_move(self) -> None:
        if self._concluded or self._current is None:
            return
        actor, _ctx, encounter = self._current
        start = encounter.battlefield.position_of(actor.id)

        from dnd.domain.values.square import Square

        def _on_pick(path: tuple[Square, ...] | None) -> None:
            if path is None or len(path) == 0:
                return
            self._put_intent(MoveIntent(path=tuple(path)))

        self.app.push_screen(
            MovePicker(encounter.battlefield, encounter.factions, start),
            _on_pick,
        )

    def action_intent_dodge(self) -> None:
        if self._concluded or self._current is None:
            return
        self._put_intent(DodgeIntent())

    def action_intent_dash(self) -> None:
        if self._concluded or self._current is None:
            return
        self._put_intent(DashIntent())

    def action_intent_disengage(self) -> None:
        if self._concluded or self._current is None:
            return
        self._put_intent(DisengageIntent())

    def action_intent_interact(self) -> None:
        """Открыть picker по интерактивным объектам в reach (5ft).

        Default kind = OPEN — основной случай (двери, сундуки). CLOSE /
        EXAMINE пока без отдельной клавиши; добавим, если станет нужно.
        """
        if self._concluded or self._current is None:
            return
        actor, _ctx, encounter = self._current
        bf = encounter.battlefield
        actor_pos = bf.position_of(actor.id)
        candidates: list[tuple[str, str]] = []
        # 1 клетка = 5ft, chebyshev_disk(1) включает центральную клетку.
        for sq in actor_pos.chebyshev_disk(1):
            if not bf.in_bounds(sq):
                continue
            for obj in bf.objects_at(sq):
                label = f"{obj.id} ({obj.kind.value})"
                candidates.append((str(obj.id), label))
        if not candidates:
            self.log_widget.write("[bold]No interactable objects in reach.[/]")
            return

        def _on_pick(result: str | None) -> None:
            if result is None:
                return
            self._put_intent(
                InteractIntent(
                    target_object_id=ObjectId(result),
                    interact_kind=InteractKind.OPEN,
                )
            )

        self.app.push_screen(TargetPicker(candidates), _on_pick)

    def action_intent_break(self) -> None:
        """Picker по breakable объектам в reach (имеют hp в state)."""
        if self._concluded or self._current is None:
            return
        actor, _ctx, encounter = self._current
        if actor.equipped_weapon is None:
            self.log_widget.write("[bold]No weapon equipped.[/]")
            return
        bf = encounter.battlefield
        actor_pos = bf.position_of(actor.id)
        candidates: list[tuple[str, str]] = []
        for sq in actor_pos.chebyshev_disk(1):
            if not bf.in_bounds(sq):
                continue
            for obj in bf.objects_at(sq):
                if "hp" not in obj.state:
                    continue
                label = (
                    f"{obj.id} ({obj.kind.value}, HP {obj.state['hp']})"
                )
                candidates.append((str(obj.id), label))
        if not candidates:
            self.log_widget.write("[bold]No breakable objects in reach.[/]")
            return

        def _on_pick(result: str | None) -> None:
            if result is None:
                return
            self._put_intent(BreakIntent(target_object_id=ObjectId(result)))

        self.app.push_screen(TargetPicker(candidates), _on_pick)

    def action_intent_end_turn(self) -> None:
        if self._concluded or self._current is None:
            return
        self._put_intent(EndTurnIntent())

    def action_toggle_zoom(self) -> None:
        """Переключить zoom MapWidget'а (medium ↔ small).

        Сразу перерисовать карту мы не можем — у screen'а нет ссылки
        на encounter (она живёт в EventRenderer'е). Это сознательно:
        viewer-state хранится в виджете, и ближайший
        ``EventRenderer._refresh_map_main`` уже использует
        ``self._zoom`` — игрок увидит новый zoom на следующем событии
        движка (turn / move / damage). В простое (между ходами) рендер
        не моргает зря — это feature, не bug. Если когда-нибудь
        потребуется немедленный отклик — храним последний bf/factions
        в MapWidget'е и зовём refresh_from без параметров.
        """
        if self._concluded:
            return
        self.map_widget.toggle_zoom()

    def action_quit_app(self) -> None:
        """Выход. TuiApp на on_unmount позаботится о shutdown
        provider'a и worker'a."""
        self.app.exit()


def _list_reachable_hostiles(
    actor: Creature,
    ctx: TurnContext,
    encounter: Encounter,
) -> list[CreatureId]:
    """Список валидных целей: живые враги, по которым актор может
    атаковать сию секунду (LoS, range, cover — через
    AttackAction.can_perform_against). Параллельно с CLI-логикой."""
    if actor.equipped_weapon is None:
        return []
    actor_faction = encounter.factions.get(actor.id)
    attack = AttackAction()
    result: list[CreatureId] = []
    for cid, cr in encounter.participants.items():
        if cid == actor.id or not cr.is_alive:
            continue
        other_faction = encounter.factions.get(cid)
        if other_faction == actor_faction:
            continue
        if other_faction is Faction.NEUTRAL:
            continue
        try:
            params = weapon_attack_params(actor, cid)
        except ValueError:
            continue
        if isinstance(attack.can_perform_against(actor, params, ctx), Allowed):
            result.append(cid)
    return result


__all__ = ["BattleScreen"]
