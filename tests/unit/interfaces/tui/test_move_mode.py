"""MoveModeHandler: курсор + path preview, Enter/Esc/arrows."""
from unittest.mock import MagicMock

from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.move_mode import MoveModeHandler


def _screen_stub(pc_pos: Square | None = None, w: int = 20, h: int = 20):
    s = MagicMock()
    s._current_actor_position = pc_pos if pc_pos is not None else Square(5, 5)
    s._current_battlefield.width = w
    s._current_battlefield.height = h
    s._current_battlefield.terrain_at = MagicMock(
        return_value=MagicMock(difficult=False, passable=True)
    )
    return s


def test_on_enter_cursor_at_actor() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(7, 3)))
    cursor, _, _ = h.overlay_data()
    assert cursor == Square(7, 3)


def test_arrow_moves_cursor_and_builds_path() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(5, 5)))
    assert h.on_key(_screen_stub(Square(5, 5)), "right") is True
    cursor, _, path = h.overlay_data()
    assert cursor == Square(6, 5)
    assert path == (Square(6, 5),)


def test_arrow_clamps_to_world_bounds() -> None:
    h = MoveModeHandler()
    s = _screen_stub(Square(0, 0), w=10, h=10)
    h.on_enter(s)
    assert h.on_key(s, "left") is True
    cursor, _, _ = h.overlay_data()
    assert cursor == Square(0, 0)  # clamped


def test_escape_returns_true_and_marks_cancel() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub())
    assert h.on_key(_screen_stub(), "escape") is True
    assert h.cancelled is True


def test_enter_returns_true_and_marks_confirm() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(5, 5)))
    h.on_key(_screen_stub(Square(5, 5)), "right")
    assert h.on_key(_screen_stub(Square(5, 5)), "enter") is True
    assert h.confirmed_path == (Square(6, 5),)


def test_unknown_key_returns_false() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub())
    assert h.on_key(_screen_stub(), "x") is False
