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

import logging
import os

# Define custom log levels
PROTOCOL_LEVEL = 7
EVENT_LEVEL = 14
METHOD_LEVEL = 15

# PROTOCOL: 7
# DEBUG: 10
# EVENT: 14
# METHOD: 15
# INFO: 20
# WARNING: 30
# ERROR: 40
# CRITICAL: 50

logging.addLevelName(PROTOCOL_LEVEL, "PROTOCOL")
logging.addLevelName(METHOD_LEVEL, "METHOD")
logging.addLevelName(EVENT_LEVEL, "EVENT")


class WaylandLogger(logging.Logger):
    def __init__(self, name):
        super().__init__(name)
        self._protocol_enabled = True  # Flag to enable/disable PROTOCOL logging
        self._method_enabled = True  # Flag to enable/disable METHOD logging
        self._event_enabled = True  # Flag to enable/disable EVENT logging

    # Standard logging methods (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    def debug(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.DEBUG):
            self.log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.INFO):
            self.log(logging.INFO, message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.WARNING):
            self.log(logging.WARNING, message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.ERROR):
            self.log(logging.ERROR, message, *args, **kwargs)

    def critical(self, message, *args, **kwargs):
        if self.isEnabledFor(logging.CRITICAL):
            self.log(logging.CRITICAL, message, *args, **kwargs)

    # Custom logging methods (PROTOCOL, METHOD)
    def protocol(self, message, *args, **kwargs):
        if self.isEnabledFor(PROTOCOL_LEVEL) and self._protocol_enabled:
            self.log(PROTOCOL_LEVEL, message, *args, **kwargs)

    def method(self, message, *args, **kwargs):
        if self.isEnabledFor(METHOD_LEVEL) and self._method_enabled:
            self.log(METHOD_LEVEL, message, *args, **kwargs)

    def event(self, message, *args, **kwargs):
        if self.isEnabledFor(EVENT_LEVEL) and self._event_enabled:
            self.log(EVENT_LEVEL, message, *args, **kwargs)

    # Methods to enable/disable custom levels
    def disable_protocol(self):
        self._protocol_enabled = False

    def enable_protocol(self):
        self._protocol_enabled = True

    def disable_method(self):
        self._method_enabled = False

    def enable_method(self):
        self._method_enabled = True

    def disable_event(self):
        self._event_enabled = False

    def enable_event(self):
        self._event_enabled = True

    def enable(self, level=logging.INFO):
        log.setLevel(level)

        console_handler = logging.StreamHandler()

        console_handler.setLevel(level)

        formatter = logging.Formatter("%(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)

        log.addHandler(console_handler)


# Register the custom logger class
logging.setLoggerClass(WaylandLogger)

# Create a logger instance
log = logging.getLogger("wayland")
# log.disable_protocol()

if not log.hasHandlers() and os.getenv("WAYLAND_DEBUG", "0") == "1":
    log.enable(PROTOCOL_LEVEL)
