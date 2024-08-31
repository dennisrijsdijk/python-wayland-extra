import wayland

WAYLAND_DELAY = 0.5


def test_display_singleton():
    assert wayland.wl_display.object_id == 1
