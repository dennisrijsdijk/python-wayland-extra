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

import array
import errno
import fcntl
import socket
import struct
import threading
import time
from collections import deque

from wayland.constants import PROTOCOL_HEADER_SIZE


class UnixSocketConnection(threading.Thread):
    READ_BUFFER_SIZE = 4096

    def __init__(self, socket_path, buffer_size=2**18):
        super().__init__()
        self.buffer = deque(maxlen=buffer_size)

        self.socket_path = socket_path
        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.connect(self.socket_path)

        self.stop_event = threading.Event()

        self.read_lock = threading.Lock()
        self.write_lock = threading.Lock()
        self.buffer_lock = threading.Lock()

        self.daemon = True
        self.start()

    def _read(self):
        while True:
            peek = self._socket.recv(PROTOCOL_HEADER_SIZE, socket.MSG_PEEK)
            if len(peek) < PROTOCOL_HEADER_SIZE:
                time.sleep(0.01)
                continue

            _, _, message_size = struct.unpack_from("IHH", peek)
            data_size = struct.unpack(
                "I", fcntl.ioctl(self._socket, 0x541B, struct.pack("I", 0))
            )[0]
            if data_size < message_size:
                time.sleep(0.01)
                continue
            break

        fdsize = array.array("i").itemsize

        data, ancdata, _, _ = self._socket.recvmsg(
            message_size, socket.CMSG_LEN(fdsize)
        )

        fd = None
        for cmsg_level, cmsg_type, cmsg_data in ancdata:
            if cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS:
                fd = struct.unpack("i", cmsg_data)[0]
                break

        return data, fd

    def read(self):
        with self.read_lock:
            data, fd = self._read()
            with self.buffer_lock:
                self.buffer.append((data, fd))

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.read()
            except OSError as e:
                if e.errno not in {errno.EWOULDBLOCK, errno.EAGAIN}:
                    break
            except Exception:
                break

    def stop(self):
        self.stop_event.set()
        self.join()

    def sendmsg(self, buffers, ancillary):
        with self.write_lock:
            self._socket.sendmsg(buffers, ancillary)

    def sendall(self, data):
        with self.write_lock:
            self._socket.sendall(data)

    def get_next_message(self):
        with self.buffer_lock:
            if not self.buffer:
                return None
            data, fd = self.buffer.popleft()

        if fd is not None:
            data += struct.pack("I", fd)

        return data
