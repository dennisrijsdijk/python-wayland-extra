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

import errno
import socket
import struct
import threading
from collections import deque

from wayland.constants import PROTOCOL_HEADER_SIZE


class RingBuffer:
    def __init__(self, size):
        self.size = size
        self.buffer = deque(maxlen=size)

    def append(self, data):
        if len(data) > self.size:
            data = data[-self.size :]  # Truncate data if larger than buffer
        self.buffer.extend(data)

    def get(self):
        return bytes(self.buffer)

    def consume(self, num_bytes):
        for _ in range(num_bytes):
            self.buffer.popleft()


class UnixSocketConnection(threading.Thread):
    def __init__(self, socket_path, buffer_size=65536):
        super().__init__()

        self.socket_path = socket_path
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.connect(self.socket_path)

        self.buffer_size = buffer_size
        self.ring_buffer = RingBuffer(buffer_size)
        self.stop_event = threading.Event()
        self.buffer_lock = threading.Lock()
        self.socket_lock = threading.Lock()
        self.daemon = True
        self.start()

    def run(self):
        while not self.stop_event.is_set():
            try:
                data = self._socket.recv(4096)
                if data:
                    with self.buffer_lock:
                        self.ring_buffer.append(data)
                else:
                    break
            except OSError as e:
                if e.errno not in {errno.EWOULDBLOCK, errno.EAGAIN}:
                    # Handle other socket errors
                    break

    def stop(self):
        self.stop_event.set()

    def sendmsg(self, buffers, ancillary):
        with self.socket_lock:
            self._socket.sendmsg(buffers, ancillary)

    def sendall(self, data):
        with self.socket_lock:
            self._socket.sendall(data)

    def get_next_message(self):
        with self.buffer_lock:
            buffer_content = self.ring_buffer.get()
            if len(buffer_content) < PROTOCOL_HEADER_SIZE:
                return None  # Not enough data for the smallest message header

            # Get message_size
            _, _, message_size = struct.unpack_from("IHH", buffer_content)

            if len(buffer_content) < message_size:
                return None  # Not enough data for the complete message

            # Extract the full message
            full_message = buffer_content[:message_size]

            # Consume the processed bytes from the buffer
            self.ring_buffer.consume(message_size)

            return full_message

    def get_buffer_content(self):
        with self.buffer_lock:
            return self.ring_buffer.get()
