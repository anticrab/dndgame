"""TuiApp — главный объект Textual-приложения.

Собирает intent_queue + TuiIntentProvider + EventRenderer +
RunnerWorker вокруг переданного Encounter и запускает игру в
фоновом треде. См. ``docs/TUI.md`` §4–5.
"""

from __future__ import annotations

import contextlib
import queue
from typing import TYPE_CHECKING

from textual.app import App

from dnd.application.abilities.defaults import register_default_abilities
from dnd.application.abilities.registry import AbilityRegistry
from dnd.application.dto.player_intent import PlayerIntent
from dnd.application.engine.game_runner import GameRunner
from dnd.application.ports.event_bus import Unsubscribe
from dnd.application.ports.item_repository import ItemRepository
from dnd.interfaces.tui.bridge import (
    EventRenderer,
    RunnerWorker,
    TuiIntentProvider,
)
from dnd.interfaces.tui.screens import BattleScreen
from dnd.interfaces.tui.themes import ThemeName, theme_css_path

if TYPE_CHECKING:
    from dnd.application.dto.map_dto import MapDocument
    from dnd.application.engine.encounter import Encounter
    from dnd.application.engine.turn_context import TurnContext
    from dnd.application.ports.map_repository import MapRepository
    from dnd.application.ports.sprite_registry import SpriteRegistry
    from dnd.domain.entities.creature import Creature

    EditorBundle = tuple[MapDocument, MapRepository, SpriteRegistry]


class TuiApp(App[None]):
    """Главное Textual-приложение для одного боя.

    Параметры:
      * ``encounter`` — собранный, ещё не запущенный Encounter
        (``encounter.start()`` будет вызван внутри RunnerWorker'а
        через ``GameRunner.run``).
      * ``theme`` — `color` (по умолчанию) или `monochrome`.

    Если ``encounter is None`` — это «голый» каркас (для тестов
    темы / каркаса); подключение к движку не выполняется.
    """

    TITLE = "D&D 5e — Console"
    SUB_TITLE = "MVP"

    def __init__(
        self,
        *,
        encounter: Encounter | None = None,
        theme: ThemeName = "color",
        editor: EditorBundle | None = None,
        ability_registry: AbilityRegistry | None = None,
        item_repository: ItemRepository | None = None,
    ) -> None:
        # CSS_PATH читается из атрибутов экземпляра в __init__ Textual.
        # Подставляем тему до super().__init__.
        object.__setattr__(self, "CSS_PATH", theme_css_path(theme))
        super().__init__()
        self._theme: ThemeName = theme
        self._encounter = encounter
        self._editor = editor
        # Если registry не передан — собираем дефолтный с 6 базовыми
        # умениями. Прокидываем в BattleScreen для динамического keymap
        # и action-bar (L2-7).
        if ability_registry is None:
            ability_registry = AbilityRegistry()
            register_default_abilities(ability_registry)
        self._ability_registry: AbilityRegistry = ability_registry
        # ItemRepository прокидывается в GameRunner — нужен для
        # PickupAction'а (O-8). None допустимо: PickupIntent тогда
        # отклоняется с понятной причиной 'no_item_repository'.
        self._item_repository: ItemRepository | None = item_repository
        self._intent_queue: queue.Queue[PlayerIntent] | None = None
        self._provider: TuiIntentProvider | None = None
        self._renderer: EventRenderer | None = None
        self._renderer_unsubscribe: Unsubscribe | None = None
        self._worker: RunnerWorker | None = None
        self._battle_screen: BattleScreen | None = None

    def on_mount(self) -> None:
        if self._editor is not None:
            from dnd.interfaces.tui.screens.editor_screen import EditorScreen
            doc, repo, sprites = self._editor
            self.push_screen(EditorScreen(doc=doc, repo=repo, sprites=sprites))
            return

        if self._encounter is None:
            self.push_screen(BattleScreen(
                ability_registry=self._ability_registry,
                item_repository=self._item_repository,
            ))
            return

        self._intent_queue = queue.Queue()
        self._battle_screen = BattleScreen(
            intent_queue=self._intent_queue,
            ability_registry=self._ability_registry,
            item_repository=self._item_repository,
        )
        self.push_screen(self._battle_screen)
        # Bridge + worker запускаются на BattleScreen.Ready (см.
        # _on_battle_screen_ready): иначе worker может выпустить
        # InitiativeRolled раньше, чем виджеты будут доступны через
        # query_one.

    def on_battle_screen_ready(self, message: BattleScreen.Ready) -> None:
        del message
        # «Голый» каркас (encounter is None) — bridge не нужен.
        if self._encounter is None:
            return
        self._start_bridge_and_worker()

    def _start_bridge_and_worker(self) -> None:
        # Guard от повторного срабатывания (на случай повторного mount).
        if self._worker is not None:
            return
        assert self._encounter is not None
        assert self._battle_screen is not None
        assert self._intent_queue is not None

        screen = self._battle_screen
        encounter = self._encounter

        def _turn_signal(
            actor: Creature, ctx: TurnContext, enc: Encounter
        ) -> None:
            self.call_from_thread(screen.set_active_turn, actor, ctx, enc)

        self._provider = TuiIntentProvider(
            self._intent_queue, turn_signal=_turn_signal
        )
        self._renderer = EventRenderer(
            screen, encounter, call_from_thread=self.call_from_thread
        )
        self._renderer_unsubscribe = self._renderer.subscribe(
            encounter.event_bus
        )

        runner = GameRunner(
            intent_provider=self._provider,
            item_repository=self._item_repository,
        )
        self._worker = RunnerWorker(
            target=lambda: runner.run(encounter),
            on_finished=self._on_runner_finished,
        )
        self._worker.start()

    def on_unmount(self) -> None:
        # Отписать renderer от шины первым делом: после exit Textual
        # закрывает event loop, и любой call_from_thread из worker'a
        # уйдёт в never-awaited coroutine. Отписка снимает источник.
        if self._renderer_unsubscribe is not None:
            self._renderer_unsubscribe()
            self._renderer_unsubscribe = None
        # Разблокировать висящий provider.next_intent → worker увидит
        # EndTurnIntent и выйдет из GameRunner.
        if self._provider is not None:
            self._provider.shutdown()

    def _on_runner_finished(self, exc: BaseException | None) -> None:
        # Победа/поражение показывается через EndScreen (push'ает
        # EventRenderer на EncounterEnded). Здесь reагируем только на
        # незапланированное исключение в worker'е.
        if exc is None or self._battle_screen is None:
            return
        with contextlib.suppress(Exception):  # app мог уже закрыться
            self.call_from_thread(
                self._battle_screen.log_widget.write,
                f"[bold red]— Runner error: {exc!r}; press Q to exit —[/]",
            )


def run_tui(
    *,
    encounter: Encounter,
    theme: ThemeName = "color",
    item_repository: ItemRepository | None = None,
) -> None:
    """Создать TuiApp вокруг готового Encounter и запустить блокирующе.

    Используется из ``dnd play --tui``: собираем services + scenario +
    encounter в `app.play`, передаём сюда — функция возвращается
    после закрытия приложения.
    """
    TuiApp(
        encounter=encounter, theme=theme, item_repository=item_repository,
    ).run()


__all__ = ["TuiApp", "run_tui"]
