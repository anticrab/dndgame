"""Smoke-тесты Textual-каркаса (этап J2).

Запускаем приложение headless через ``App.run_test`` и проверяем,
что:
* компонуется без ошибок;
* подгружается выбранная тема (по пути CSS_PATH);
* экран ``BattleScreen`` поднимается со всеми обязательными виджетами.

Связь с GameRunner (intent_queue, event_bridge) появится на J3 —
здесь её не проверяем.

Async обёртки — через ``asyncio.run`` (без pytest-asyncio: его в dev-deps
нет, и заводить ради двух тестов избыточно).

Импорт ``textual`` в try/except + module-level skip: без textual вся
коллекция в этом файле скипается, других side-effect'ов нет — это
дружественно к среде без TUI-расширения.
"""

from __future__ import annotations

import asyncio

import pytest

try:
    import textual  # noqa: F401  (нужен для importorskip)
except ImportError:  # pragma: no cover — обычно textual установлен
    pytest.skip("textual not installed", allow_module_level=True)

from dnd.interfaces.tui import TuiApp
from dnd.interfaces.tui.themes import theme_css_path
from dnd.interfaces.tui.widgets import (
    InitiativeWidget,
    LogWidget,
    MapWidget,
    StatusWidget,
)


def test_tui_app_starts_with_color_theme() -> None:
    async def _go() -> None:
        app = TuiApp(theme="color")
        async with app.run_test(size=(80, 24)) as pilot:
            screen = pilot.app.screen
            assert screen.query_one("#map", MapWidget) is not None
            assert screen.query_one("#status", StatusWidget) is not None
            assert screen.query_one("#init", InitiativeWidget) is not None
            assert screen.query_one("#log", LogWidget) is not None

    asyncio.run(_go())


def test_tui_app_monochrome_theme_uses_other_css() -> None:
    app = TuiApp(theme="monochrome")
    assert app.CSS_PATH == theme_css_path("monochrome")

    async def _go() -> None:
        async with app.run_test(size=(80, 24)) as pilot:
            assert pilot.app.screen.query_one("#map", MapWidget) is not None

    asyncio.run(_go())


def test_unknown_theme_raises() -> None:
    with pytest.raises(ValueError, match="unknown theme"):
        theme_css_path("phosphor")  # type: ignore[arg-type]


def test_battle_screen_starts_with_medium_zoom() -> None:
    """После K5-T3 default zoom MapWidget'а — medium (UI.md §3.1):
    пользователь видит «красивый» 5×3-рендер сразу, без ручного toggle.
    """
    app = TuiApp()  # без encounter — pure-каркас mode

    async def _go() -> None:
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause(0.1)
            screen = pilot.app.screen
            mw = screen.query_one("#map", MapWidget)
            assert mw.zoom == "medium"

    asyncio.run(_go())


def test_battle_screen_plus_toggles_zoom_small() -> None:
    """`+` переключает medium ↔ small (K5-T3, BattleScreen.BINDINGS).

    Проверяем «туда-обратно»: один toggle → small, второй → medium.
    """
    app = TuiApp()

    async def _go() -> None:
        async with app.run_test(size=(120, 35)) as pilot:
            await pilot.pause(0.1)
            screen = pilot.app.screen
            mw = screen.query_one("#map", MapWidget)
            assert mw.zoom == "medium"
            await pilot.press("plus")
            await pilot.pause(0.05)
            assert mw.zoom == "small"
            await pilot.press("plus")
            await pilot.pause(0.05)
            assert mw.zoom == "medium"

    asyncio.run(_go())
