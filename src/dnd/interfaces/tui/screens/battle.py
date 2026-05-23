"""BattleScreen — основной экран боя.

См. ``docs/TUI.md`` §6 и mockup A.1 (80×24 layout). После L1-T9 экран
не открывает модальные picker'ы для Attack/Move/Interact/Break, а
переключается в inline-mode (``BattleMode.MOVE`` / ``BattleMode.TARGET``)
и делегирует keypress'ы соответствующему ``ModeHandler``-у. См.
spec ``docs/superpowers/specs/2026-05-23-l-inline-ux-and-abilities-design.md``
§4.2.

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
В NORMAL mode action-биндинги переводят экран в нужный mode (после
``can_perform`` check'а), реальный submit Intent'а — после Enter в mode.
"""

from __future__ import annotations

import contextlib
import queue
from typing import TYPE_CHECKING, ClassVar

from textual import events as _events
from textual.app import ComposeResult
from textual.binding import BindingType
from textual.containers import Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Footer, Header

from dnd.application.abilities.ability import Ability
from dnd.application.abilities.defaults import register_default_abilities
from dnd.application.abilities.registry import AbilityRegistry
from dnd.application.dto.action import Allowed, Forbidden, ForbiddenReason
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
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.move_mode import MoveModeHandler
from dnd.interfaces.tui.screens.battle_modes.normal_mode import NormalModeHandler
from dnd.interfaces.tui.screens.battle_modes.protocol import BattleMode, ModeHandler
from dnd.interfaces.tui.screens.battle_modes.target_mode import TargetModeHandler
from dnd.interfaces.tui.screens.keymap import build_keymap
from dnd.interfaces.tui.widgets import (
    ActionBarWidget,
    InitiativeWidget,
    LogWidget,
    MapWidget,
    StatusWidget,
)

if TYPE_CHECKING:
    from dnd.application.engine.encounter import Encounter
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.battlefield import Battlefield
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
        ability_registry: AbilityRegistry | None = None,
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
        # --- state machine (L1-T9) ----------------------------------
        # ModeScreenContext: атрибуты которые handler'ы читают через
        # Protocol. Заполняются в set_active_turn (battlefield/pos) и
        # action_intent_attack/interact/break (reachable targets).
        self._mode: BattleMode = BattleMode.NORMAL
        self._mode_handler: ModeHandler = NormalModeHandler()
        self._current_actor_position: Square = Square(0, 0)
        self._current_battlefield: Battlefield | None = None
        self._reachable_targets: list[tuple[CreatureId, Square]] = []
        # Различает kind intent'а при подтверждении в TARGET mode
        # (attack vs interact vs break). Меняется в action_intent_*
        # и в _trigger_ability (для custom rebound'ов).
        self._pending_target_kind: str = "attack"
        # --- abilities (L2-7) ---------------------------------------
        # Registry — default = 6 базовых (см. register_default_abilities).
        # При custom rebinding (actor.keybindings) build_keymap соберёт
        # маппинг override-хоткея → Ability, и BattleScreen.on_key
        # запустит соответствующее умение через intent_factory.
        if ability_registry is None:
            ability_registry = AbilityRegistry()
            register_default_abilities(ability_registry)
        self._ability_registry: AbilityRegistry = ability_registry
        self._keymap: dict[str, Ability] = {}
        # Ability, ожидающая выбора цели в TARGET mode. None — TARGET
        # был открыт классическим action_intent_attack/interact/break,
        # confirm-логика берёт kind из _pending_target_kind как раньше.
        self._pending_ability: Ability | None = None

    # --- public API для bridge --------------------------------------

    def set_active_turn(
        self,
        actor: Creature,
        ctx: TurnContext,
        encounter: Encounter,
    ) -> None:
        """Bridge зовёт это в main-thread (через call_from_thread)
        каждый раз, когда PC получает ход. Состояние сохраняется
        для action-handlers, статус-виджет обновляется.

        ИНВАРИАНТ §11-2: при смене хода mode сбрасывается в NORMAL —
        иначе залипший MOVE из прошлого хода ловил бы стрелки на
        чужом ходу.
        """
        self._current = (actor, ctx, encounter)
        self._current_battlefield = encounter.battlefield
        self._current_actor_position = encounter.battlefield.position_of(actor.id)
        if self._mode is not BattleMode.NORMAL:
            self.enter_mode(BattleMode.NORMAL)
        self.status_widget.refresh_from(actor, ctx)
        # L2-7: пересобираем keymap под текущего актора (его
        # ability_ids + keybindings override'ы) и обновляем
        # action-bar. Делаем после refresh_from чтобы виджеты были
        # точно смонтированы — query_one на TurnStarted безопасен.
        self._keymap = build_keymap(actor, self._ability_registry)
        # Action-bar может ещё не быть смонтирован в первых event'ах
        # (initial ComposeResult); следующий TurnStarted обновит его.
        with contextlib.suppress(Exception):
            self.action_bar_widget.set_keymap(self._keymap)

    def clear_active_turn(self) -> None:
        """Сбросить состояние (вне-PC ход). Дополнительная защита от
        случайного нажатия action-клавиши на чужом ходу."""
        self._current = None
        # Не-PC ход — выйти из любого активного mode (см. set_active_turn).
        if self._mode is not BattleMode.NORMAL:
            self.enter_mode(BattleMode.NORMAL)

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
        # ActionBarWidget пока скрыт — Textual Footer уже показывает
        # тот же default-набор hotkey'ев из BINDINGS, и две одинаковые
        # полосы внизу путают игрока. Виджет вернём, когда появятся
        # per-creature keybindings/заклинания, которых нет в BINDINGS.
        yield ActionBarWidget(id="action-bar", classes="-hidden")
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

    @property
    def action_bar_widget(self) -> ActionBarWidget:
        return self.query_one("#action-bar", ActionBarWidget)

    # --- intent helpers ---------------------------------------------

    def _put_intent(self, intent: PlayerIntent) -> None:
        if self._intent_queue is not None:
            self._intent_queue.put(intent)
        # Дальнейшие нажатия до начала следующего хода — игнорируем.
        self._current = None

    # --- mode state machine (L1-T9) ---------------------------------

    def enter_mode(self, mode: BattleMode) -> None:
        """Переключить активный mode-handler.

        Порядок: ``on_exit`` старого → смена handler'а → ``on_enter``
        нового → перерисовка карты. Перерисовка нужна, чтобы overlay
        (cursor / highlights) появился/исчез сразу, не дожидаясь
        engine-event'а.
        """
        self._mode_handler.on_exit(self)
        self._mode = mode
        if mode is BattleMode.NORMAL:
            self._mode_handler = NormalModeHandler()
        elif mode is BattleMode.MOVE:
            self._mode_handler = MoveModeHandler()
        elif mode is BattleMode.TARGET:
            self._mode_handler = TargetModeHandler()
        self._mode_handler.on_enter(self)
        self._refresh_map_overlay()

    def _refresh_map_overlay(self) -> None:
        """Перерисовать карту с актуальным overlay-данным от handler'а.

        В NORMAL overlay пустой — карта рисуется «как есть»; в MOVE/TARGET
        cursor/highlights/path_preview приходят из ``overlay_data()``.
        Viewport follow:
        * NORMAL/MOVE — едет за PC (стрелки в MOVE двигают курсор
          относительно карты, follow=actor чтобы PC оставался виден);
        * TARGET — едет за выбранной целью (если все цели за пределами
          viewport на большой карте, игрок не увидел бы подсветку
          через Tab).
        """
        if self._current is None or self._current_battlefield is None:
            return
        cursor, highlights, path_preview = self._mode_handler.overlay_data()
        actor, _ctx, encounter = self._current
        if self._mode is BattleMode.TARGET and cursor is not None:
            follow = cursor
        else:
            follow = self._current_battlefield.position_of(actor.id)
        try:
            self.map_widget.refresh_from(
                self._current_battlefield,
                encounter.factions,
                cursor=cursor,
                highlights=highlights,
                path_preview=path_preview,
                follow=follow,
            )
        except Exception:
            # MapWidget может ещё не быть смонтирован (initial event'ы).
            return

    def on_key(self, event: _events.Key) -> None:
        """Делегировать клавишу активному mode-handler'у.

        В NORMAL mode сначала смотрим custom keymap (rebound hotkey'и
        из ``actor.keybindings``) — default hotkey'и оставляем на
        откуп Textual BINDINGS (то есть action_intent_*), чтобы не
        дублировать поведение и не сломать существующий тест-suite.
        В MOVE/TARGET стрелки/Tab/Enter/Esc — handler'а зона
        ответственности.

        После on_key проверяем флаги handler'а: cancelled → вернуться
        в NORMAL; confirmed_path/target → положить Intent + NORMAL.
        """
        if self._concluded:
            return
        if self._mode is BattleMode.NORMAL:
            ab = self._keymap.get(event.key) if self._keymap else None
            # default hotkey уже обрабатывается соответствующим BINDING'ом
            # (action_intent_attack и т.д.). Запускаем через keymap
            # только override — например, actor.keybindings={"z": ...}.
            if ab is not None and event.key != ab.default_hotkey:
                self._trigger_ability(ab)
                event.stop()
                event.prevent_default()
            return
        handled = self._mode_handler.on_key(self, event.key)
        if not handled:
            return
        event.stop()
        event.prevent_default()
        h = self._mode_handler
        if isinstance(h, MoveModeHandler):
            if h.cancelled:
                self.enter_mode(BattleMode.NORMAL)
                return
            if h.confirmed_path is not None:
                if h.confirmed_path:
                    self._put_intent(MoveIntent(path=h.confirmed_path))
                self.enter_mode(BattleMode.NORMAL)
                return
        elif isinstance(h, TargetModeHandler):
            if h.cancelled:
                self.enter_mode(BattleMode.NORMAL)
                return
            if h.confirmed_target is not None:
                self._submit_target_intent(h.confirmed_target)
                self.enter_mode(BattleMode.NORMAL)
                return
        # просто refresh для arrow/tab — overlay изменился
        self._refresh_map_overlay()

    def _submit_target_intent(self, target: CreatureId) -> None:
        """Сформировать Intent для подтверждённой цели TARGET mode.

        Если в TARGET вошли через custom-ability (``_pending_ability``
        задан), используем её фабрику — это пробрасывает rebound
        hotkey'и через ту же confirm-логику. Иначе fallback на
        ``_pending_target_kind`` (attack/interact/break) — это путь
        через action_intent_attack/interact/break и BINDINGS.
        """
        if self._pending_ability is not None:
            intent = self._pending_ability.intent_factory(target)
            self._pending_ability = None
            self._put_intent(intent)
            return
        kind = self._pending_target_kind
        if kind == "attack":
            self._put_intent(AttackIntent(target_id=target))
        elif kind == "interact":
            self._put_intent(
                InteractIntent(
                    target_object_id=ObjectId(str(target)),
                    interact_kind=InteractKind.OPEN,
                )
            )
        elif kind == "break":
            self._put_intent(
                BreakIntent(target_object_id=ObjectId(str(target)))
            )

    def _trigger_ability(self, ab: Ability) -> None:
        """Запустить ability через её ``intent_factory``.

        * Без target/path — сразу строим intent и кладём в очередь;
        * requires_target — собираем reachable targets (на сейчас:
          живые враги по логике attack-action) и переходим в TARGET mode
          с ``_pending_ability`` — confirm дёрнет factory(target_id);
        * requires_path — TODO (Move сейчас НЕ ability, идёт через
          отдельный hotkey ``m`` → MoveModeHandler). Логируем и выходим.
        """
        if self._current is None:
            return
        actor, ctx, encounter = self._current
        if ab.requires_target:
            targets = _list_reachable_hostiles(actor, ctx, encounter)
            if not targets:
                self.log_widget.write(
                    f"[bold]No targets in reach for {ab.name}.[/]"
                )
                return
            bf = encounter.battlefield
            self._current_battlefield = bf
            self._reachable_targets = [(cid, bf.position_of(cid)) for cid in targets]
            self._pending_ability = ab
            self.enter_mode(BattleMode.TARGET)
            return
        if ab.requires_path:
            self.log_widget.write(
                f"[bold]Path-abilities пока не поддерживаются; "
                f"используйте m для движения ({ab.name}).[/]"
            )
            return
        intent = ab.intent_factory()
        self._put_intent(intent)

    # --- action handlers --------------------------------------------

    def action_intent_attack(self) -> None:
        if self._concluded or self._current is None:
            return
        actor, ctx, encounter = self._current
        # Сначала проверяем что атака в принципе возможна (action / conditions),
        # чтобы дать точный feedback вместо misleading "No reachable targets".
        global_check = AttackAction().can_perform(actor, ctx)
        if isinstance(global_check, Forbidden):
            self.log_widget.write(_explain_forbidden("attack", global_check))
            return
        targets = _list_reachable_hostiles(actor, ctx, encounter)
        if not targets:
            # Здесь точно "нет валидных целей" (action есть, но никого в reach
            # или нет LoS) — посчитаем живых врагов на карте чтобы
            # подсказать «move closer».
            hostile_count = _count_living_hostiles(actor, encounter)
            if hostile_count == 0:
                self.log_widget.write("[bold]No enemies left.[/]")
            else:
                self.log_widget.write(
                    f"[bold]No targets in reach[/] "
                    f"({hostile_count} enemy alive). Move closer (m) first."
                )
            return
        # ИНВАРИАНТ §11-4: TARGET mode НЕ открывается с пустым reach.
        bf = encounter.battlefield
        self._current_battlefield = bf
        self._reachable_targets = [(cid, bf.position_of(cid)) for cid in targets]
        self._pending_target_kind = "attack"
        self.enter_mode(BattleMode.TARGET)

    def action_intent_move(self) -> None:
        if self._concluded or self._current is None:
            return
        actor, ctx, encounter = self._current
        # Проверяем что движение в принципе возможно (есть футы, не Incapacitated).
        from dnd.application.engine.actions.move import MoveAction
        move_check = MoveAction().can_perform(actor, ctx)
        if isinstance(move_check, Forbidden):
            self.log_widget.write(_explain_forbidden("move", move_check))
            return
        self._current_battlefield = encounter.battlefield
        self._current_actor_position = encounter.battlefield.position_of(actor.id)
        self.enter_mode(BattleMode.MOVE)

    def action_intent_dodge(self) -> None:
        if self._concluded or self._current is None:
            return
        actor, ctx, _ = self._current
        from dnd.application.engine.actions.stances import DodgeAction
        check = DodgeAction().can_perform(actor, ctx)
        if isinstance(check, Forbidden):
            self.log_widget.write(_explain_forbidden("dodge", check))
            return
        self._put_intent(DodgeIntent())

    def action_intent_dash(self) -> None:
        if self._concluded or self._current is None:
            return
        actor, ctx, _ = self._current
        from dnd.application.engine.actions.stances import DashAction
        check = DashAction().can_perform(actor, ctx)
        if isinstance(check, Forbidden):
            self.log_widget.write(_explain_forbidden("dash", check))
            return
        self._put_intent(DashIntent())

    def action_intent_disengage(self) -> None:
        if self._concluded or self._current is None:
            return
        actor, ctx, _ = self._current
        from dnd.application.engine.actions.stances import DisengageAction
        check = DisengageAction().can_perform(actor, ctx)
        if isinstance(check, Forbidden):
            self.log_widget.write(_explain_forbidden("disengage", check))
            return
        self._put_intent(DisengageIntent())

    def action_intent_interact(self) -> None:
        """Войти в TARGET mode для выбора объекта в reach (5ft).

        Default kind = OPEN — основной случай (двери, сундуки). CLOSE /
        EXAMINE пока без отдельной клавиши; добавим, если станет нужно.
        Объекты подсвечиваются на карте через highlights TargetModeHandler'а;
        выбор подтверждается Enter, как и у атаки.
        """
        if self._concluded or self._current is None:
            return
        actor, _ctx, encounter = self._current
        bf = encounter.battlefield
        actor_pos = bf.position_of(actor.id)
        # ObjectId/CreatureId оба NewType(str) — для рендера highlights
        # хватает любого str-id. На submit обратно cast'им в ObjectId.
        candidates: list[tuple[CreatureId, Square]] = []
        # 1 клетка = 5ft, chebyshev_disk(1) включает центральную клетку.
        for sq in actor_pos.chebyshev_disk(1):
            if not bf.in_bounds(sq):
                continue
            for obj in bf.objects_at(sq):
                candidates.append((CreatureId(str(obj.id)), sq))
        if not candidates:
            self.log_widget.write("[bold]No interactable objects in reach.[/]")
            return
        self._current_battlefield = bf
        self._reachable_targets = candidates
        self._pending_target_kind = "interact"
        self.enter_mode(BattleMode.TARGET)

    def action_intent_break(self) -> None:
        """TARGET mode для breakable объектов в reach (имеют hp в state)."""
        if self._concluded or self._current is None:
            return
        actor, _ctx, encounter = self._current
        if actor.equipped_weapon is None:
            self.log_widget.write("[bold]No weapon equipped.[/]")
            return
        bf = encounter.battlefield
        actor_pos = bf.position_of(actor.id)
        candidates: list[tuple[CreatureId, Square]] = []
        for sq in actor_pos.chebyshev_disk(1):
            if not bf.in_bounds(sq):
                continue
            for obj in bf.objects_at(sq):
                if "hp" not in obj.state:
                    continue
                candidates.append((CreatureId(str(obj.id)), sq))
        if not candidates:
            self.log_widget.write("[bold]No breakable objects in reach.[/]")
            return
        self._current_battlefield = bf
        self._reachable_targets = candidates
        self._pending_target_kind = "break"
        self.enter_mode(BattleMode.TARGET)

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


_FORBIDDEN_MESSAGES: dict[ForbiddenReason, str] = {
    ForbiddenReason.NO_ECONOMY_LEFT: (
        "[bold]Action already used this turn.[/] "
        "Press [bold]e[/] to end turn, or use bonus action."
    ),
    ForbiddenReason.INCAPACITATED: "[bold]Incapacitated — cannot act.[/]",
    ForbiddenReason.CONDITION_BLOCKS_ACTION: (
        "[bold]Blocked by condition.[/] Wait it out (end turn)."
    ),
    ForbiddenReason.NOT_ENOUGH_MOVEMENT: (
        "[bold]No movement left.[/] Try [bold]Dash[/] (h) for extra movement."
    ),
}


def _explain_forbidden(action_name: str, forbidden: Forbidden) -> str:
    """Перевести Forbidden причину в дружелюбное сообщение для лога."""
    msg = _FORBIDDEN_MESSAGES.get(forbidden.reason)
    if msg is None:
        details = f" ({forbidden.details})" if forbidden.details else ""
        msg = f"[bold]Cannot {action_name}: {forbidden.reason.value}{details}[/]"
    return msg


def _count_living_hostiles(actor: Creature, encounter: Encounter) -> int:
    actor_faction = encounter.factions.get(actor.id)
    count = 0
    for cid, cr in encounter.participants.items():
        if cid == actor.id or not cr.is_alive:
            continue
        other_faction = encounter.factions.get(cid)
        if other_faction is None or other_faction == actor_faction:
            continue
        from dnd.domain.values.faction import Faction as _F
        if other_faction is _F.NEUTRAL:
            continue
        count += 1
    return count


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
