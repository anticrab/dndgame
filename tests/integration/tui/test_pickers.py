"""Тесты модальных picker'ов (TargetPicker / MovePicker).

Покрытие:
* TargetPicker — Tab циклит, Enter возвращает выбранный CreatureId,
  Esc — None;
* MovePicker — стрелки сдвигают курсор, Enter возвращает
  chebyshev-путь, Esc — None, границы карты соблюдаются.

Запускаются через App.run_test → push_screen → pilot.press; результат
читается из dismiss-coroutine (через App.push_screen-result).
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("textual")

from textual.app import App

from dnd.application.dto.ids import CreatureId
from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.move_picker import (
    MovePicker,
    _chebyshev_path,
)
from dnd.interfaces.tui.screens.target_picker import TargetPicker


def test_chebyshev_path_diagonal() -> None:
    assert _chebyshev_path(Square(1, 1), Square(3, 3)) == (
        Square(2, 2),
        Square(3, 3),
    )


def test_chebyshev_path_same_cell_is_empty() -> None:
    assert _chebyshev_path(Square(1, 1), Square(1, 1)) == ()


def test_chebyshev_path_straight() -> None:
    assert _chebyshev_path(Square(0, 0), Square(0, 3)) == (
        Square(0, 1),
        Square(0, 2),
        Square(0, 3),
    )


class _HostApp(App[None]):
    def __init__(self, screen) -> None:
        super().__init__()
        self._screen_to_push = screen
        self.result: object = "PENDING"

    def on_mount(self) -> None:
        self.push_screen(self._screen_to_push, self._on_dismiss)

    def _on_dismiss(self, value: object) -> None:
        self.result = value
        self.exit()


def test_target_picker_enter_returns_first() -> None:
    """Enter в ListView ловится через ``ListView.Selected``-handler
    в TargetPicker — выбор первой цели подтверждается."""
    targets = [(CreatureId("g1"), "g1"), (CreatureId("g2"), "g2")]
    picker = TargetPicker(targets)
    host = _HostApp(picker)

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("enter")
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.result == CreatureId("g1")


def test_target_picker_arrow_down_then_enter_returns_second() -> None:
    """↓ в ListView переключает выбор; Enter подтверждает."""
    targets = [(CreatureId("g1"), "g1"), (CreatureId("g2"), "g2")]
    picker = TargetPicker(targets)
    host = _HostApp(picker)

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("down")
            await pilot.press("enter")
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.result == CreatureId("g2")


def test_target_picker_escape_returns_none() -> None:
    targets = [(CreatureId("g1"), "g1")]
    host = _HostApp(TargetPicker(targets))

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("escape")
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.result is None


def test_move_picker_arrow_moves_cursor_and_enter_returns_path() -> None:
    bf = Battlefield(5, 5)
    start = Square(2, 2)
    host = _HostApp(MovePicker(bf, {}, start))

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("right")  # курсор → (3,2)
            await pilot.press("right")  # курсор → (4,2)
            await pilot.press("enter")
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.result == (Square(3, 2), Square(4, 2))


def test_move_picker_cursor_does_not_exit_map_bounds() -> None:
    bf = Battlefield(3, 3)
    start = Square(0, 0)
    host = _HostApp(MovePicker(bf, {}, start))

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.05)
            # Пытаемся уйти за левую границу — курсор остаётся в (0,0).
            await pilot.press("left")
            await pilot.press("left")
            await pilot.press("up")
            await pilot.press("enter")  # path остаётся пустым (Square(0,0))
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.result == ()


def test_move_picker_escape_returns_none() -> None:
    bf = Battlefield(5, 5)
    host = _HostApp(MovePicker(bf, {}, Square(2, 2)))

    async def _go() -> None:
        async with host.run_test(size=(80, 24)) as pilot:
            await pilot.pause(0.05)
            await pilot.press("escape")
            await pilot.pause(0.1)

    asyncio.run(_go())
    assert host.result is None
