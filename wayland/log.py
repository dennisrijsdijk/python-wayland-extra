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

from __future__ import annotations

import logging
import os
from typing import Any

# Custom log levels
CUSTOM_LEVELS = {"PROTOCOL": 7, "EVENT": 8, "REQUEST": 9}

for name, level in CUSTOM_LEVELS.items():
    logging.addLevelName(level, name)


class WaylandLogger(logging.Logger):
    def __init__(self, name: str):
        super().__init__(name)
        self._enabled_flags: dict[str, bool] = {
            name.lower(): True for name in CUSTOM_LEVELS
        }

    def _log_if_enabled(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        level_name = logging.getLevelName(level).lower()
        if self.isEnabledFor(level) and self._enabled_flags.get(level_name, True):
            self.log(level, msg, *args, **kwargs)

    def protocol(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log_if_enabled(CUSTOM_LEVELS["PROTOCOL"], msg, *args, **kwargs)

    def event(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log_if_enabled(CUSTOM_LEVELS["EVENT"], msg, *args, **kwargs)

    def request(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log_if_enabled(CUSTOM_LEVELS["REQUEST"], msg, *args, **kwargs)

    def toggle_level(self, level_name: str, enable: bool) -> None:
        self._enabled_flags[level_name.lower()] = enable

    def enable(self, level: int = logging.INFO) -> None:
        self.setLevel(level)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        formatter = logging.Formatter("%(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        self.addHandler(console_handler)


logging.setLoggerClass(WaylandLogger)
log = logging.getLogger("wayland")

if not log.hasHandlers() and os.getenv("WAYLAND_DEBUG") == "1":
    log.enable(CUSTOM_LEVELS["PROTOCOL"])
