"""TuiApp — главный объект Textual-приложения.

На этапе J2 — каркас: запускает один ``BattleScreen``, прикладывает
выбранную тему (`color` или `monochrome`). Подключение к движку
(worker-thread + intent_queue + event_bridge) добавляется на J3.

См. ``docs/TUI.md`` §4 (архитектура «два потока, один движок»).
"""

from __future__ import annotations

from textual.app import App

from dnd.interfaces.tui.screens import BattleScreen
from dnd.interfaces.tui.themes import ThemeName, theme_css_path


class TuiApp(App[None]):
    """Главное Textual-приложение.

    На J2 — только каркас (compose, темы, заглушки key bindings в
    BattleScreen). Worker-thread с GameRunner и intent_queue —
    подключается на J3 (см. ``docs/TUI.md`` §4–5).
    """

    TITLE = "D&D 5e — Console"
    SUB_TITLE = "MVP"

    def __init__(self, *, theme: ThemeName = "color") -> None:
        # CSS_PATH в Textual читается из атрибутов экземпляра при __init__,
        # поэтому подменяем его до super().__init__() — иначе Textual
        # не подхватит пользовательскую тему. Атрибут объявлен на классе
        # как ClassVar; перезаписываем именно атрибут экземпляра.
        object.__setattr__(self, "CSS_PATH", theme_css_path(theme))
        super().__init__()
        self._theme: ThemeName = theme

    def on_mount(self) -> None:
        self.push_screen(BattleScreen())


__all__ = ["TuiApp"]
