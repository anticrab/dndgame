"""Textual TUI — фронтенд боя.

Точка входа — :class:`~dnd.interfaces.tui.app.TuiApp`. Подключение к
игровому циклу появится на этапе J3 (см. ``docs/TUI.md``).

Импорт ``textual`` локализован в этом подпакете: ни ``domain``, ни
``application``, ни CLI его не тянут (инвариант ``docs/TUI.md`` §2).
"""

from dnd.interfaces.tui.app import TuiApp
from dnd.interfaces.tui.themes import ThemeName

__all__ = ["ThemeName", "TuiApp"]
