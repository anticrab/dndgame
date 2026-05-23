"""MoveModeHandler: курсор + walkable path preview + path_styles + hint."""
from __future__ import annotations

from unittest.mock import MagicMock

from dnd.domain.entities.battlefield import Battlefield
from dnd.domain.values.square import Square
from dnd.domain.values.terrain import FLOOR, WALL
from dnd.interfaces.tui.screens.battle_modes.move_mode import MoveModeHandler


def _screen_stub(
    pc_pos: Square | None = None,
    bf: Battlefield | None = None,
    speed_ft: int = 30,
) -> MagicMock:
    """Stub-screen для MoveModeHandler.

    Использует РЕАЛЬНЫЙ Battlefield (не MagicMock), потому что
    find_walkable_path внутри Dijkstra'и зовёт несколько методов
    (in_bounds, terrain_at, passable_between, creatures_at) — мокать
    все одинаково долго и хрупко.
    """
    s = MagicMock()
    s._current_actor_position = pc_pos if pc_pos is not None else Square(5, 5)
    s._current_actor_speed_ft = speed_ft
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
    data = h.overlay()
    assert data.cursor == Square(7, 3)


def test_arrow_moves_cursor_and_builds_path() -> None:
    h = MoveModeHandler()
    h.on_enter(_screen_stub(Square(5, 5)))
    s = _screen_stub(Square(5, 5))
    assert h.on_key(s, "right") is True
    data = h.overlay()
    assert data.cursor == Square(6, 5)
    assert data.path_preview == (Square(6, 5),)


def test_arrow_clamps_to_world_bounds() -> None:
    h = MoveModeHandler()
    s = _screen_stub(Square(0, 0), bf=_open_bf(10, 10))
    h.on_enter(s)
    assert h.on_key(s, "left") is True
    assert h.overlay().cursor == Square(0, 0)  # clamped


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
    for y in range(4):
        bf.set_terrain(Square(3, y), WALL)
    h = MoveModeHandler()
    s = _screen_stub(Square(2, 0), bf=bf)
    h.on_enter(s)
    for _ in range(3):
        h.on_key(s, "right")
    data = h.overlay()
    assert data.cursor == Square(5, 0)
    assert data.path_preview, "path should exist around the wall"
    assert Square(3, 0) not in data.path_preview


def test_unreachable_target_yields_empty_path_and_no_confirm() -> None:
    """Полностью закрытая цель → пустой preview, Enter ничего не подтверждает,
    cursor подсвечен красным как невалидный."""
    bf = _open_bf(6, 6)
    for sq in (Square(4, 5), Square(5, 4), Square(4, 4)):
        bf.set_terrain(sq, WALL)
    bf.set_terrain(Square(5, 5), WALL)
    h = MoveModeHandler()
    s = _screen_stub(Square(0, 0), bf=bf)
    h.on_enter(s)
    for _ in range(5):
        h.on_key(s, "right")
        h.on_key(s, "down")
    data = h.overlay()
    assert data.path_preview == ()
    assert "red reverse" in (data.highlights.get(data.cursor) or ""), (
        "недостижимая клетка должна быть подсвечена красным"
    )
    h.on_key(s, "enter")
    assert h.confirmed_path is None


def test_path_styles_color_by_budget() -> None:
    """Шаги в пределах speed_ft → green, до 2× → yellow, дальше → red."""
    bf = _open_bf(20, 1)
    h = MoveModeHandler()
    # speed_ft=15 → 3 клетки green, ещё 3 yellow, остальные red.
    s = _screen_stub(Square(0, 0), bf=bf, speed_ft=15)
    h.on_enter(s)
    for _ in range(8):  # курсор → (8, 0), path = 8 клеток × 5 ft = 40 ft
        h.on_key(s, "right")
    data = h.overlay()
    assert data.cursor == Square(8, 0)
    assert len(data.path_preview) == 8
    # cumulative 5/10/15 → green; 20/25/30 → yellow; 35/40 → red
    colors = [data.path_styles[sq] for sq in data.path_preview]
    assert colors[:3] == ["green", "green", "green"]
    assert colors[3:6] == ["yellow", "yellow", "yellow"]
    assert colors[6:] == ["red", "red"]


def test_enter_blocked_when_overflow_dash() -> None:
    """Путь длиннее 2×speed_ft → Enter НЕ ставит confirmed_path."""
    bf = _open_bf(20, 1)
    h = MoveModeHandler()
    s = _screen_stub(Square(0, 0), bf=bf, speed_ft=10)
    h.on_enter(s)
    for _ in range(6):  # 6 × 5 ft = 30 ft > 2 × 10 ft
        h.on_key(s, "right")
    assert h.on_key(s, "enter") is True
    assert h.confirmed_path is None


def test_hint_mentions_cost_and_budget() -> None:
    h = MoveModeHandler()
    bf = _open_bf(10, 10)
    s = _screen_stub(Square(0, 0), bf=bf, speed_ft=30)
    h.on_enter(s)
    h.on_key(s, "right")
    hint = h.overlay().hint
    assert "MOVE" in hint
    assert "cost=" in hint and "/30 ft" in hint
