import wayland

WAYLAND_DELAY = 0.5


def test_get_registry():
    protocols = [
        "wl_shm",
        "xdg_wm_base",
        "wl_compositor",
        "wl_seat",
        "wl_subcompositor",
    ]

    received_protocols = []

    def on_wl_registry_global(name, interface, version):
        nonlocal received_protocols

        received_protocols.append(interface)

    # Hook the event to get the registry results
    wayland.wl_registry.events.global_ += on_wl_registry_global
    wayland.wl_display.get_registry()

    # Check we got some interfaces we should have
    for proto in protocols:
        assert proto in received_protocols
