"""Viewport на MapWidget: camera/pan/center_on/visible_rect (pure logic)."""
from dnd.domain.values.square import Square
from dnd.interfaces.tui.widgets.map_widget import MapWidget


def test_default_camera_origin() -> None:
    mw = MapWidget()
    assert mw.camera == Square(0, 0)


def test_pan_shifts_camera() -> None:
    mw = MapWidget()
    mw.set_viewport_size(20, 10)
    mw.set_world_size(40, 20)
    mw.pan(5, 3)
    assert mw.camera == Square(5, 3)


def test_pan_clamps_to_world_bounds() -> None:
    mw = MapWidget()
    mw.set_viewport_size(10, 10)
    mw.set_world_size(15, 15)
    mw.pan(100, 100)
    # camera + viewport не должно превышать world
    assert mw.camera == Square(5, 5)


def test_pan_clamps_to_zero() -> None:
    mw = MapWidget()
    mw.set_viewport_size(10, 10)
    mw.set_world_size(20, 20)
    mw.pan(-5, -5)
    assert mw.camera == Square(0, 0)


def test_center_on_centers_viewport() -> None:
    mw = MapWidget()
    mw.set_viewport_size(10, 10)
    mw.set_world_size(40, 40)
    mw.center_on(Square(20, 20))
    # центр viewport 10×10 на (20,20) → camera (15, 15)
    assert mw.camera == Square(15, 15)


def test_visible_rect_returns_camera_plus_viewport() -> None:
    mw = MapWidget()
    mw.set_viewport_size(8, 6)
    mw.set_world_size(50, 50)
    mw.pan(10, 5)
    assert mw.visible_rect() == (10, 5, 18, 11)


def test_set_viewport_size_rejects_non_positive() -> None:
    import pytest
    mw = MapWidget()
    with pytest.raises(ValueError):
        mw.set_viewport_size(0, 10)
    with pytest.raises(ValueError):
        mw.set_viewport_size(10, -1)
