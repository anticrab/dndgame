"""BattleMode enum + ModeHandler Protocol — каркас state machine."""

from dnd.interfaces.tui.screens.battle_modes.protocol import (
    BattleMode,
    ModeHandler,
    OverlayData,
)


def test_battle_mode_values() -> None:
    assert BattleMode.NORMAL.value == "normal"
    assert BattleMode.MOVE.value == "move"
    assert BattleMode.TARGET.value == "target"


def test_mode_handler_is_protocol() -> None:
    # Любой класс с правильными методами должен подойти как ModeHandler.
    class StubHandler:
        def on_enter(self, screen: object) -> None: ...
        def on_exit(self, screen: object) -> None: ...
        def on_key(self, screen: object, key: str) -> bool:
            return False

        def overlay(self) -> OverlayData:
            return OverlayData()

    h: ModeHandler = StubHandler()  # type: ignore[assignment]
    assert h.on_key(object(), "x") is False


def test_overlay_data_defaults_are_empty() -> None:
    od = OverlayData()
    assert od.cursor is None
    assert od.highlights == {}
    assert od.path_preview == ()
    assert od.path_styles == {}
    assert od.hint == ""
