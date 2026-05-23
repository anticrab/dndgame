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

from dnd.application.dto.player_intent import PlayerIntent
from dnd.application.engine.game_runner import GameRunner
from dnd.interfaces.tui.bridge import (
    EventRenderer,
    RunnerWorker,
    TuiIntentProvider,
)
from dnd.interfaces.tui.screens import BattleScreen
from dnd.interfaces.tui.themes import ThemeName, theme_css_path

if TYPE_CHECKING:
    from dnd.application.engine.encounter import Encounter
    from dnd.application.engine.turn_context import TurnContext
    from dnd.domain.entities.creature import Creature


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
    ) -> None:
        # CSS_PATH читается из атрибутов экземпляра в __init__ Textual.
        # Подставляем тему до super().__init__.
        object.__setattr__(self, "CSS_PATH", theme_css_path(theme))
        super().__init__()
        self._theme: ThemeName = theme
        self._encounter = encounter
        self._intent_queue: queue.Queue[PlayerIntent] | None = None
        self._provider: TuiIntentProvider | None = None
        self._renderer: EventRenderer | None = None
        self._worker: RunnerWorker | None = None
        self._battle_screen: BattleScreen | None = None

    def on_mount(self) -> None:
        if self._encounter is None:
            self.push_screen(BattleScreen())
            return

        self._intent_queue = queue.Queue()
        self._battle_screen = BattleScreen(intent_queue=self._intent_queue)
        self.push_screen(self._battle_screen)

        screen = self._battle_screen
        encounter = self._encounter

        def _turn_signal(
            actor: Creature, ctx: TurnContext, enc: Encounter
        ) -> None:
            # worker-thread → main-thread.
            self.call_from_thread(screen.set_active_turn, actor, ctx, enc)

        self._provider = TuiIntentProvider(
            self._intent_queue, turn_signal=_turn_signal
        )
        self._renderer = EventRenderer(
            screen, encounter, call_from_thread=self.call_from_thread
        )
        self._renderer.subscribe(encounter.event_bus)

        runner = GameRunner(intent_provider=self._provider)
        self._worker = RunnerWorker(
            target=lambda: runner.run(encounter),
            on_finished=self._on_runner_finished,
        )
        self._worker.start()

    def on_unmount(self) -> None:
        # Сигналим worker'у завершиться, разблокируем висящий
        # provider.next_intent → worker увидит is_concluded и выйдет.
        if self._provider is not None:
            self._provider.shutdown()

    def _on_runner_finished(self, exc: BaseException | None) -> None:
        del exc
        # Вызывается в worker-thread; в main-thread шлём через
        # call_from_thread (по требованию Textual).
        # На MVP J просто помечаем в логе; full Victory/Defeat overlay
        # — пост-MVP. Если приложение уже не в активном состоянии,
        # call_from_thread может выбросить — суммируем и игнорим.
        if self._battle_screen is None:
            return
        with contextlib.suppress(Exception):  # app мог уже закрыться
            self.call_from_thread(
                self._battle_screen.log_widget.write,
                "[bold cyan]— Encounter complete; press Q to exit —[/]",
            )


def run_tui(
    *,
    encounter: Encounter,
    theme: ThemeName = "color",
) -> None:
    """Создать TuiApp вокруг готового Encounter и запустить блокирующе.

    Используется из ``dnd play --tui``: собираем services + scenario +
    encounter в `app.play`, передаём сюда — функция возвращается
    после закрытия приложения.
    """
    TuiApp(encounter=encounter, theme=theme).run()


__all__ = ["TuiApp", "run_tui"]
