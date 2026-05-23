"""CSS-темы TUI. См. ``docs/TUI.md`` §7 и ``docs/UI.md`` §3."""

from importlib.resources import files
from typing import Literal

ThemeName = Literal["color", "monochrome"]

_THEMES: dict[str, str] = {
    "color": "color.tcss",
    "monochrome": "monochrome.tcss",
}


def theme_css_path(theme: ThemeName) -> str:
    """Абсолютный путь до .tcss-файла темы — для Textual ``CSS_PATH``."""
    if theme not in _THEMES:
        raise ValueError(f"unknown theme: {theme!r}; expected color|monochrome")
    return str(files("dnd.interfaces.tui.themes").joinpath(_THEMES[theme]))


__all__ = ["ThemeName", "theme_css_path"]
