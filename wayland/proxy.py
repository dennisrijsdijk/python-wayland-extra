# Copyright (c) 2024 Graham R King
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice (including the
# next paragraph) shall be included in all copies or substantial
# portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
# BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
# ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import json
import keyword
import socket
import struct

from wayland.log import log


class Proxy:
    class Method:
        def __init__(self, parent, name, args, opcode):
            self.name = name
            self.method_args = args
            self.opcode = opcode
            self.method = True
            self.event = False
            self.parent = parent

        @classmethod
        def _pad(cls, data):
            if isinstance(data, str):
                data = data.encode("utf-8")
            data += b"\x00"
            padding = ((len(data) + 3) & ~3) - len(data)
            data += b"\x00" * padding
            return data

        def __call__(self, *args):
            args = list(args)

            # Read some properties from the class to which this method is bound
            parent_interface = self.parent._name
            object_id = self.parent.object_id
            scope = self.parent._scope
            state = self.parent._state

            packet = b""
            values = []
            interface = None
            ancillary = None
            return_value = None
            for arg in self.method_args:
                # Remember any interface value we see
                if arg["name"] == "interface":
                    interface = args.pop(0)
                    value = interface
                elif arg["type"] == "new_id":
                    # use the object type of the new_id arg if possible
                    if arg.get("interface"):
                        interface = arg.get("interface")

                    # Create a new object to return as
                    new_object_id, new_object = state.new_object(scope[interface])
                    return_value = new_object_id
                    value = new_object_id

                else:
                    # A normal argument, just grab the value
                    value = args.pop(0)

                # Pack the argument
                packet, value = self._pack_argument(packet, arg["type"], value)
                ancillary = self._handle_fd_argument(arg["type"], value, ancillary)

                # Debug info
                values.append(self._format_debug_arg(value, arg["type"]))

            log.method(
                f"{parent_interface}#{object_id}.{self.name}({', '.join(values)})"
            )

            # Send the wayland request
            state.send_wayland_message(object_id, self.opcode, packet, ancillary)

            if return_value:
                return_value = state.object_id_to_object_reference(return_value)
            return return_value

        def _pack_argument(self, packet, arg_type, value):
            if arg_type in ("new_id", "uint", "enum"):
                packet += struct.pack("I", value)
            elif arg_type == "object":
                packet += struct.pack("I", getattr(value, "object_id", 0))
            elif arg_type == "int":
                packet += struct.pack("i", value)
            elif arg_type == "string":
                length = len(value) + 1
                value = self._pad(value)
                packet += struct.pack(f"I{len(value)}s", length, value)
            elif arg_type == "fixed":
                integer_part = int(value) << 8
                fractional_part = int((value - int(value)) * 256)
                value = integer_part | (fractional_part & 0xFF)
                packet += struct.pack("I", value)

            return packet, value

        def _handle_fd_argument(self, arg_type, value, ancillary):
            if arg_type == "fd":
                ancillary = [
                    (socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack("I", value))
                ]
            return ancillary

        def _format_debug_arg(self, value, arg_type):
            if arg_type == "object" and isinstance(value, object):
                return f"{value._name}#{value.object_id}"
            return str(value)

    class Events:
        pass

    class Event:
        def __init__(self, parent, name, args, opcode):
            self.name = name
            self.parent = parent
            self.method_args = args
            self.opcode = opcode
            self.method = False
            self.event = True
            self._handlers = []

        def __iadd__(self, handler):
            """Registers a new handler to be called when the event is triggered."""
            if callable(handler):
                self._handlers.append(handler)
            return self

        def __isub__(self, handler):
            """Unregisters an existing handler."""
            if handler in self._handlers:
                self._handlers.remove(handler)
            return self

        def __call__(self, packet):
            # Read some properties from the class to which this method is bound
            parent_interface = self.parent._name
            object_id = self.parent.object_id

            kwargs = {}
            for arg in self.method_args:
                arg_type = arg["type"]
                # Get the value
                packet, value = self._unpack_argument(packet, arg_type)
                # Save the argument
                kwargs[arg["name"]] = value

                # For new_id on events, pass the interface as an argument to the event handler too
                if arg_type == "new_id" and arg.get("interface"):
                    # Get the interface name
                    interface = arg.get("interface")
                    # Save the argument
                    kwargs["interface"] = interface
                    # TODO: we don't expand object id to an actual object instance
                    msg = "No events like this to test yet"
                    raise NotImplementedError(msg)

            values = []
            for k, v in kwargs.items():
                values.append(f"{k} = {v}")

            log.event(
                f"{parent_interface}#{object_id}.{self.name}({', '.join(values)})"
            )
            for handler in self._handlers:
                handler(**kwargs)

        def _unpack_argument(self, packet, arg_type):
            read = 0
            if arg_type in ("new_id", "uint", "object", "enum"):
                (value,) = struct.unpack_from("I", packet)
                read = 4
            elif arg_type == "int":
                (value,) = struct.unpack_from("i", packet)
                read = 4
            elif arg_type == "fd":
                # we packed the file descriptor on the end of the data
                (value,) = struct.unpack_from("I", packet[-4:])
            elif arg_type == "string":
                (length,) = struct.unpack_from("I", packet)
                packet = packet[4:]
                padded_length = (length + 3) & ~3
                (value,) = struct.unpack_from(f"{padded_length}s", packet)
                value = value[: length - 1].decode("utf-8")
                read = padded_length
            elif arg_type == "array":
                (length,) = struct.unpack_from("I", packet)
                packet = packet[4:]
                padded_length = (length + 3) & ~3
                (value,) = struct.unpack_from(f"{padded_length}s", packet)
                value = value[: length - 1]
                read = padded_length
            elif arg_type == "fixed":
                (value,) = struct.unpack_from("I", packet)
                read = 4
                integer_part = value >> 8
                fractional_part = value & 0xFF
                value = integer_part + fractional_part / 256.0
            else:
                raise ValueError("Unknown type " + arg_type)

            return packet[read:], value

    class DynamicObject:
        @property
        def object_id(self):
            return self._object_id

        @object_id.setter
        def object_id(self, value):
            self._object_id = value
            log.protocol(f"{self._name} assigned object_id {self._object_id}")

        def __init__(self, name, scope, methods, events):
            self._name = name
            self._scope = scope
            self._state = scope.get("state")
            self._methods = methods
            self._events = events
            self._object_id = 0
            # Special wayland case
            if name == "wl_display":
                self.object_id, _ = self._state.new_object(self)
            # Bind methods and events
            self.events = Proxy.Events()
            self._bind_methods(methods)
            self._bind_events(events)

        def copy(self):
            return self.__class__(self._name, self._scope, self._methods, self._events)

        def _bind_methods(self, methods):
            for method in methods:
                # Avoid python keyword naming collisions
                attr_name = method["name"]
                if keyword.iskeyword(attr_name):
                    attr_name += "_"

                # Create a new method
                method_obj = Proxy.Method(
                    self, attr_name, method["args"], method["opcode"]
                )
                # Set the method with the correct binding
                setattr(self, attr_name, method_obj)

        def _bind_events(self, events):
            for event in events:
                # Avoid python keyword naming collisions
                attr_name = event["name"]
                if keyword.iskeyword(attr_name):
                    attr_name += "_"

                # Create a new event
                method_obj = Proxy.Event(
                    self, attr_name, event["args"], event["opcode"]
                )
                # Set the method with the correct binding
                setattr(self.events, attr_name, method_obj)

        def __bool__(self):
            return self.object_id > 0

    def __init__(self):
        self.state = None
        self.scope = None

    def initialise(self, scope, path, state):
        self.state = state
        self.scope = scope
        try:
            with open(f"{path}/protocols.json", encoding="utf-8") as infile:
                structure = json.load(infile)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            msg = f"Error loading structure: {e}"
            raise FileNotFoundError(msg) from e

        for class_name, details in structure.items():
            # Process requests
            methods = details.get("methods", [])
            events = details.get("events", [])
            dynamic_class = type(class_name, (Proxy.DynamicObject,), {})
            instance = dynamic_class(class_name, self.scope, methods, events)
            # Inject instance into scope
            scope[class_name] = instance
