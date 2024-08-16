import wayland


def test_display_singleton():
    assert wayland.wl_display.object_id == 1


def test_get_registry():
    wayland.wl_display.get_registry(None)
