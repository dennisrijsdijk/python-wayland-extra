# libwayland

__This is in early prototype stage__

A Python implementation of the Wayland protocol, from scratch, with no external dependencies, including no dependencies on any Wayland libraries.

This seeks to be a Python implementation of libwayland-client. The server/compositor perspective hasn't been considered.

## Objectives

* No external dependencies, needs no Wayland libraries, and only Python standard libraries at runtime. This is a replacement for libwayland-client, not a wrapper for it.
* Intellisense code completion support for methods and events.
* All stable and staging Wayland protocols built in.
* A design that makes using https://wayland.app as a reference straightforward.
* Can optionally refresh protocols from local or official online sources.

## Notes

Wayland identifiers that collide with Python builtin keywords are renamed to end with an underscore. The list of changes is:

* `wl_registry.events.global` becomes `wl_registry.events.global_`

## Making Wayland Requests

As documented in the wayland protocol, with the exception that `new_id` arguments should be omitted. Wayland methods instead return a Python object reference to be slightly more Pythonic.

```python
registry = wayland.wl_display.get_registry()
```

## Event Handlers

Events are collected together under the `events` attribute of an interface. Define event handlers:

```python
    def on_error(self, object_id, code, message):
        print(f"Fatal error: {object_id} {code} {message}")
        sys.exit(1)
```

Register an event handler by add adding it to the relevant event:

```python
    wayland.wl_display.events.error += self.on_error
```

The order of parameters in the event handler doesn't matter.

## Processing Events

To process all pending wayland events and call any registered event handlers:

```python
wayland.process_messages()
```

## Refreshing Protocols

The package is installed with the Wayland stable and staging protocols already built-in. Refreshing the protocol definitions is optional. It requires some additional Python dependencies:

* `pip install lxml`
* `pip install requests`

To rebuild the Wayland protocols from the locally installed protocol definitions:

```bash
python -m wayland
```

To rebuild the protocols directly from the online sources:

```bash
python -m wayland --download
```

## Thanks

Thanks to Philippe Gaultier, whose article [Wayland From Scratch](https://gaultier.github.io/blog/wayland_from_scratch.html) inspired this project.

