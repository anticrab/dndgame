from dnd.interfaces.tui.screens.battle_modes.normal_mode import NormalModeHandler


def test_normal_mode_no_overlay() -> None:
    h = NormalModeHandler()
    cursor, highlights, path = h.overlay_data()
    assert cursor is None
    assert highlights == {}
    assert path == ()


def test_normal_mode_doesnt_eat_keys() -> None:
    h = NormalModeHandler()
    # screen=None — handler не должен на него полагаться в этой версии
    assert h.on_key(None, "x") is False  # type: ignore[arg-type]
