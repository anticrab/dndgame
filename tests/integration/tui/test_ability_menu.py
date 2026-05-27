"""AbilityMenuScreen — навигация, применение, перебинд (этап S).

Pilot-харнесс через ``asyncio.run`` (как в test_app_smoke — без pytest-asyncio).
"""
from __future__ import annotations

import asyncio

import pytest

try:
    import textual  # noqa: F401
except ImportError:  # pragma: no cover
    pytest.skip("textual not installed", allow_module_level=True)

from textual.app import App

from dnd.application.abilities.ability import Ability
from dnd.application.dto.action import ActionEconomyCost
from dnd.application.dto.player_intent import EndTurnIntent
from dnd.domain.values.ability_id import AbilityId
from dnd.interfaces.tui.screens.ability_menu_screen import AbilityMenuScreen, AbilityRow


def _ab(aid: str) -> Ability:
    return Ability(
        id=AbilityId(aid),
        name=aid,
        icon="*",
        default_hotkey="",
        economy_cost=ActionEconomyCost.ACTION,
        requires_target=False,
        requires_path=False,
        intent_factory=lambda: EndTurnIntent(),
    )


class _Host(App[None]):
    """Минимальный хост, который сразу выталкивает тестируемую модалку."""

    def __init__(self, screen: AbilityMenuScreen) -> None:
        super().__init__()
        self._screen = screen

    def on_mount(self) -> None:
        self.push_screen(self._screen)


def test_navigation_and_apply_selects_row() -> None:
    applied: list[Ability] = []
    rows = [AbilityRow(_ab("a"), "a", True), AbilityRow(_ab("b"), "b", True)]
    scr = AbilityMenuScreen(rows, on_apply=applied.append, on_rebind=lambda *_: None)

    async def _go() -> None:
        async with _Host(scr).run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("down")  # курсор → строка 1
            await pilot.press("enter")  # применить
            await pilot.pause()

    asyncio.run(_go())
    assert len(applied) == 1
    assert applied[0] is rows[1].ability


def test_unavailable_row_not_applied() -> None:
    applied: list[Ability] = []
    rows = [AbilityRow(_ab("a"), "a", False)]  # недоступна
    scr = AbilityMenuScreen(rows, on_apply=applied.append, on_rebind=lambda *_: None)

    async def _go() -> None:
        async with _Host(scr).run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("enter")
            await pilot.pause()

    asyncio.run(_go())
    assert applied == []


def test_rebind_captures_next_key() -> None:
    bound: list[tuple[str, str]] = []
    rows = [AbilityRow(_ab("atk"), "a", True)]
    scr = AbilityMenuScreen(
        rows, on_apply=lambda *_: None, on_rebind=lambda ab, k: bound.append((ab.id, k))
    )

    async def _go() -> None:
        async with _Host(scr).run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.1)
            await pilot.press("b")  # режим «нажмите клавишу»
            await pilot.press("z")  # назначить z
            await pilot.pause()

    asyncio.run(_go())
    assert bound == [("atk", "z")]
