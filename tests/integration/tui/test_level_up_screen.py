"""R1-13: LevelUpScreen — выбор «Сейчас / После боя / Подробнее»."""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.app import App

from dnd.application.dto.engine_event import LevelUpReady
from dnd.interfaces.tui.screens.level_up_screen import LevelUpScreen


class _Host(App[None]):
    def __init__(self) -> None:
        super().__init__()
        self.now_called = 0
        self.later_called = 0

    def on_mount(self) -> None:
        ev = LevelUpReady(actor_id="hero", from_level=1, to_level=2)
        self.push_screen(LevelUpScreen(
            ev,
            on_now=self._on_now,
            on_later=self._on_later,
            details="+8 HP, Action Surge",
        ))

    def _on_now(self) -> None:
        self.now_called += 1

    def _on_later(self) -> None:
        self.later_called += 1


def test_displays_level_transition() -> None:
    host = _Host()

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            from textual.widgets import Label
            texts = [str(lbl.renderable) for lbl in pilot.app.screen.query(Label)]
            assert any("уровень 2" in t for t in texts), texts

    asyncio.run(_go())


def test_now_applies_immediately() -> None:
    host = _Host()

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("n")
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.now_called == 1 and host.later_called == 0


def test_later_defers() -> None:
    host = _Host()

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("l")
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.later_called == 1 and host.now_called == 0


def test_details_toggle_does_not_close() -> None:
    host = _Host()

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("d")
            await pilot.pause(0.1)
            from textual.widgets import Label
            texts = [str(lbl.renderable) for lbl in pilot.app.screen.query(Label)]
            assert any("Action Surge" in t for t in texts), texts
            # экран ещё открыт → колбэки не вызваны
            assert host.now_called == 0 and host.later_called == 0

    asyncio.run(_go())
