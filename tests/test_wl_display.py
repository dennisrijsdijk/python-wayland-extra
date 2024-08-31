import wayland as wl

wayland = wl.initialise()


def test_display_singleton():
    assert wayland.wl_display.object_id == 1
