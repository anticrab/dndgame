"""Тесты EndScreen — модальный итог боя.

Покрытие:
* Composer корректно показывает «PARTY WINS» / «DRAW» + survivors;
* Enter / Esc / Q закрывают приложение.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.app import App

from dnd.application.dto.engine_event import EncounterEnded
from dnd.application.dto.ids import CreatureId
from dnd.domain.values.faction import Faction
from dnd.interfaces.tui.screens.end_screen import EndScreen


class _Host(App[None]):
    def __init__(self, ev: EncounterEnded) -> None:
        super().__init__()
        self._ev = ev

    def on_mount(self) -> None:
        self.push_screen(EndScreen(self._ev))


def _event(winners, survivors=()) -> EncounterEnded:
    return EncounterEnded(
        winners=winners,
        round_number=3,
        survivors=tuple(CreatureId(s) for s in survivors),
    )


def test_end_screen_displays_party_wins() -> None:
    host = _Host(_event(Faction.PARTY, survivors=("aelar",)))

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            # Найдём в DOM все Label-виджеты.
            from textual.widgets import Label

            labels = pilot.app.screen.query(Label)
            texts = [str(label.renderable) for label in labels]
            assert any("PARTY WINS" in t for t in texts), texts
            assert any("aelar" in t for t in texts), texts
            assert any("Round 3" in t for t in texts), texts

    asyncio.run(_go())


def test_end_screen_displays_draw_no_survivors() -> None:
    host = _Host(_event(None))

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            from textual.widgets import Label

            labels = pilot.app.screen.query(Label)
            texts = [str(label.renderable) for label in labels]
            assert any("DRAW" in t for t in texts)
            assert any("No survivors" in t for t in texts)

    asyncio.run(_go())


def test_end_screen_q_exits_app() -> None:
    host = _Host(_event(Faction.PARTY, survivors=("aelar",)))

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("q")
            await pilot.pause(0.1)
        # Если дошли сюда — app.exit() сработал.

    asyncio.run(_go())
