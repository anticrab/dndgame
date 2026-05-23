"""MoveModeHandler: курсор + walkable path preview, Enter/Esc/arrows."""
from __future__ import annotations

from unittest.mock import MagicMock

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR, WALL
from dnd.interfaces.tui.screens.battle_modes.move_mode import MoveModeHandler


def _screen_stub(
    pc_pos: Square | None = None,
    bf: Battlefield | None = None,
) -> MagicMock:
    """Stub-screen для MoveModeHandler.

    Использует РЕАЛЬНЫЙ Battlefield (не MagicMock), потому что
    find_walkable_path внутри Dijkstra'и зовёт несколько методов
    (in_bounds, terrain_at, passable_between, creatures_at) — мокать
    все одинаково долго и хрупко.
    """
    s = MagicMock()
    s._current_actor_position = pc_pos if pc_pos is not None else Square(5, 5)
    s._current_battlefield = bf if bf is not None else _open_bf(20, 20)
    return s


def _open_bf(w: int, h: int) -> Battlefield:
    """Открытое поле w×h из floor."""
    bf = Battlefield(w, h)
    for y in range(h):
        for x in range(w):
            bf.set_terrain(Square(x, y), FLOOR)
    return bf


def test_on_enter_cursor_at_actor() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(7, 3)))
    cursor, _, _ = h.overlay_data()
    assert cursor == Square(7, 3)


def test_arrow_moves_cursor_and_builds_path() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(5, 5)))
    s = _screen_stub(Square(5, 5))
    assert h.on_key(s, "right") is True
    cursor, _, path = h.overlay_data()
    assert cursor == Square(6, 5)
    assert path == (Square(6, 5),)


def test_arrow_clamps_to_world_bounds() -> None:
    h = MoveModeHandler()
    s = _screen_stub(Square(0, 0), bf=_open_bf(10, 10))
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
    bf = _open_bf(20, 20)
    s = _screen_stub(Square(5, 5), bf=bf)
    h.on_enter(s)
    h.on_key(s, "right")
    assert h.on_key(s, "enter") is True
    assert h.confirmed_path == (Square(6, 5),)


def test_unknown_key_returns_false() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub())
    assert h.on_key(_screen_stub(), "x") is False


def test_path_avoids_walls() -> None:
    """Стена между PC и курсором → путь обходит её, не идёт сквозь."""
    bf = _open_bf(10, 10)
    # Стена-перегородка: x=3, y=0..3 (оставляем y=4..9 проходимыми).
    for y in range(4):
        bf.set_terrain(Square(3, y), WALL)
    h = MoveModeHandler()
    s = _screen_stub(Square(2, 0), bf=bf)
    h.on_enter(s)
    # Сдвигаем курсор по x=5,y=0 — за стеной. Прямой chebyshev был
    # бы (3,0),(4,0),(5,0) (через стену), а walkable должен спуститься.
    for _ in range(3):
        h.on_key(s, "right")
    cursor, _, path = h.overlay_data()
    assert cursor == Square(5, 0)
    # Через стену пути нет → должен пойти в обход вниз.
    assert path, "path should exist around the wall"
    assert Square(3, 0) not in path  # не сквозь стену


def test_unreachable_target_yields_empty_path_and_no_confirm() -> None:
    """Полностью закрытая цель → пустой preview, Enter ничего не подтверждает."""
    bf = _open_bf(6, 6)
    # Запрём клетку (5, 5) стенами со всех сторон.
    for sq in (Square(4, 5), Square(5, 4), Square(4, 4)):
        bf.set_terrain(sq, WALL)
    bf.set_terrain(Square(5, 5), WALL)
    h = MoveModeHandler()
    s = _screen_stub(Square(0, 0), bf=bf)
    h.on_enter(s)
    for _ in range(5):
        h.on_key(s, "right")
        h.on_key(s, "down")
    _cur, _, path = h.overlay_data()
    assert path == ()
    h.on_key(s, "enter")
    assert h.confirmed_path is None, "пустой путь не должен подтверждаться"
