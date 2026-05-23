"""После этапа L default zoom = small (1×1), пользователь явно сказал."""
from dnd.interfaces.tui.widgets.map_widget import MapWidget


def test_default_zoom_is_small() -> None:
    mw = MapWidget()
    assert mw.zoom == "small", "L1: default zoom returned to 1×1 tactical"
