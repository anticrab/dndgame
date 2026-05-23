"""TargetModeHandler: Tab-cycle по достижимым врагам, highlights, Enter."""
from unittest.mock import MagicMock

from dnd.application.dto.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.target_mode import TargetModeHandler


def _screen(targets: list[tuple[CreatureId, Square]]):
    s = MagicMock()
    s._reachable_targets = targets
    return s


def test_initial_target_first_in_list() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    data = h.overlay()
    assert data.cursor == Square(3, 3)
    assert data.highlights.get(Square(3, 3)) == "reverse bold"
    assert data.highlights.get(Square(5, 5)) == "bold"


def test_tab_cycles_to_next() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "tab")
    cursor = h.overlay().cursor
    assert cursor == Square(5, 5)


def test_tab_wraps_around() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "tab")
    h.on_key(_screen(targets), "tab")
    cursor = h.overlay().cursor
    assert cursor == Square(3, 3)


def test_shift_tab_cycles_back() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "shift+tab")
    cursor = h.overlay().cursor
    assert cursor == Square(5, 5)  # wrap-around к последней


def test_enter_records_confirmed_target() -> None:
    targets = [(CreatureId("g1"), Square(3, 3))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "enter")
    assert h.confirmed_target == CreatureId("g1")


def test_escape_marks_cancel() -> None:
    targets = [(CreatureId("g1"), Square(3, 3))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    h.on_key(_screen(targets), "escape")
    assert h.cancelled is True


def test_empty_targets_overlay_is_none() -> None:
    h = TargetModeHandler()
    h.on_enter(_screen([]))
    data = h.overlay()
    assert data.cursor is None
    assert data.highlights == {}


def test_hint_shows_index_and_total() -> None:
    targets = [(CreatureId("g1"), Square(3, 3)), (CreatureId("g2"), Square(5, 5))]
    h = TargetModeHandler()
    h.on_enter(_screen(targets))
    assert "1/2" in h.overlay().hint
    assert "g1" in h.overlay().hint
    h.on_key(_screen(targets), "tab")
    assert "2/2" in h.overlay().hint
    assert "g2" in h.overlay().hint
