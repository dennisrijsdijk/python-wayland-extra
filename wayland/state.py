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

import os
import string
import struct

from wayland.constants import PROTOCOL_HEADER_SIZE
from wayland.log import log
from wayland.unixsocket import UnixSocketConnection


class SingletonMeta(type):
    _instance = None

    def __call__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__call__(*args, **kwargs)
        return cls._instance


class WaylandState(metaclass=SingletonMeta):
    """
    WaylandState tracks Wayland object instances and sends and receives
    Wayland messages.

    Incoming messages are dispatched to event handlers,
    outgoing messages are sent to the local unix socket.

    WaylandState is a singleton, exposed as wayland.state.
    """

    def __init__(self):
        path = os.getenv("XDG_RUNTIME_DIR")
        display = os.getenv("WAYLAND_DISPLAY")
        if not display:
            display = "wayland-0"  # fallback
        if not path:
            msg = "XDG_RUNTIME_DIR environment variable not set."
            raise ValueError(msg)

        self._socket_path = f"{path}/{display}"
        self._socket = UnixSocketConnection(self._socket_path)

        self._next_object_id = 1
        self._object_id_to_instance = {}
        self._instance_to_object_id = {}
        self._event_handlers = []

    def new_object(self, object_reference):
        object_id = self._next_object_id
        self._next_object_id += 1
        # Don't overwrite objects
        if object_reference.object_id:
            object_reference = object_reference.copy()
            self.add_object_reference(object_id, object_reference)
        else:
            self.add_object_reference(object_id, object_reference)

        return object_id, object_reference

    def object_exists(self, object_id, object_reference):
        if object_id in self._object_id_to_instance:
            if self._object_id_to_instance[object_id] is not object_reference:
                msg = "Object ID does not match expected object reference"
                raise ValueError(msg)
            if object_reference in self._instance_to_object_id:
                if object_id != self._instance_to_object_id[object_reference]:
                    msg = "Object reference does not match expected object id"
                    raise ValueError(msg)
                return True
        return False

    def add_object_reference(self, object_id, object_reference):
        object_reference.object_id = object_id
        if not self.object_exists(object_id, object_reference):
            self._object_id_to_instance[object_id] = object_reference
            self._instance_to_object_id[object_reference] = object_id
        else:
            msg = "Duplicate object id"
            raise ValueError(msg)

    def delete_object_reference(self, object_id, object_reference):
        if self.object_exists(object_id, object_reference):
            del self._object_id_to_instance[object_id]
            del self._instance_to_object_id[object_reference]

    def object_id_to_object_reference(self, object_id):
        return self._object_id_to_instance.get(object_id, None)

    def object_reference_to_object_id(self, object_reference):
        return self._instance_to_object_id.get(object_reference, 0)

    def object_id_to_event(self, object_id, event_id):
        obj = self.object_id_to_object_reference(object_id)
        if obj and hasattr(obj, "events"):
            obj = obj.events
            for attribute_name in dir(obj):
                if attribute_name.startswith("_"):
                    continue
                attribute = getattr(obj, attribute_name)
                if (
                    callable(attribute)
                    and hasattr(attribute, "opcode")
                    and attribute.opcode == event_id
                    and attribute.event
                ):
                    return attribute
        return None

    def _debug_packet(self, data: bytes, ancillary=None):
        for i in range(0, len(data), 4):
            group = data[i : i + 4]
            # Convert each byte in the group to a hex string and join them
            hex_group = ""
            string_group = ""
            for byte in group:
                hex_group += f"{byte:02X} "
                if (
                    chr(byte)
                    in string.digits + string.ascii_letters + string.punctuation
                ):
                    string_group += chr(byte)
                else:
                    string_group += "."
            integer_value = int.from_bytes(group, byteorder="little")
            hex_group = f"{hex_group}    {string_group}    {integer_value}"
            log.protocol(f"    {hex_group}")
        if ancillary:
            log.protocol(f"    Plus ancillary file descriptor data: {ancillary}")

    def _send(self, message, ancillary=None):
        if ancillary:
            self._debug_packet(message, ancillary)
            self._socket.sendmsg([message], ancillary)
        else:
            self._debug_packet(message)
            self._socket.sendall(message)

    def send_wayland_message(
        self, wayland_object, wayland_method, packet=b"", ancillary=None
    ):
        if not wayland_object:
            msg = "NULL object passed as Wayland object"
            raise ValueError(msg)

        # Pack the message header (4 bytes for object, 2 bytes for method, 2 bytes for size)
        header = b""
        header += struct.pack("I", wayland_object)
        header += struct.pack("H", wayland_method)
        header += struct.pack("H", len(packet) + PROTOCOL_HEADER_SIZE)
        self._send(header + packet, ancillary)

    def get_next_message(self):
        packet = self._socket.get_next_message()
        if not packet:
            return

        wayland_object, opcode, _ = struct.unpack_from("IHH", packet)
        packet = packet[PROTOCOL_HEADER_SIZE:]

        event = self.object_id_to_event(wayland_object, opcode)
        if event:
            event(packet)
            return True

        log.event(f"Unhandled event {wayland_object}#{opcode}")
        return True

    def process_messages(self):
        """Process all pending wayland messages"""
        while self.get_next_message():
            pass


state = WaylandState()
