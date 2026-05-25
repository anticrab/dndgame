"""P2b-7: MultiTargetModeHandler — выбор мультимножества целей с клавиатуры."""
from __future__ import annotations

from dnd.domain.values.ids import CreatureId
from dnd.domain.values.square import Square
from dnd.interfaces.tui.screens.battle_modes.multi_target_mode import (
    MultiTargetModeHandler,
)


class _Screen:
    """Минимальный мок ModeScreenContext для MULTI_TARGET."""

    def __init__(self, max_targets: int, allow_repeat: bool) -> None:
        self._current_actor_position = Square(2, 2)
        self._reachable_targets = [
            (CreatureId("A"), Square(3, 2)),
            (CreatureId("B"), Square(4, 2)),
        ]
        self._participants: dict[CreatureId, object] = {}
        self._multi_max_targets = max_targets
        self._multi_allow_repeat = allow_repeat


def test_pick_three_distinct_no_repeat() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=2, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "space")          # add A (cursor at idx0)
    h.on_key(screen, "tab")            # cursor → B
    h.on_key(screen, "space")          # add B
    h.on_key(screen, "enter")          # confirm
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("B"))


def test_no_repeat_ignores_duplicate() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "space")          # add A
    h.on_key(screen, "space")          # повтор A игнорируется (no-repeat)
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"),)


def test_repeat_allows_same_target_twice() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A снова (repeat ok)
    h.on_key(screen, "tab")
    h.on_key(screen, "space")          # B
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("A"), CreatureId("B"))


def test_max_targets_caps_picks() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=2, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # сверх лимита → игнор
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"), CreatureId("A"))


def test_backspace_removes_last_pick() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    h.on_key(screen, "backspace")      # снять последнее A
    h.on_key(screen, "enter")
    assert h.confirmed_picks == (CreatureId("A"),)


def test_enter_with_no_picks_does_not_confirm() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "enter")
    assert h.confirmed_picks is None


def test_escape_cancels() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=False)
    h.on_enter(screen)
    h.on_key(screen, "escape")
    assert h.cancelled is True


def test_overlay_shows_counts() -> None:
    h = MultiTargetModeHandler()
    screen = _Screen(max_targets=3, allow_repeat=True)
    h.on_enter(screen)
    h.on_key(screen, "space")          # A
    h.on_key(screen, "space")          # A
    data = h.overlay()
    assert "осталось" in data.hint.lower() or "выбери" in data.hint.lower()
    # выбранная клетка A подсвечена
    assert screen._reachable_targets[0][1] in data.highlights
