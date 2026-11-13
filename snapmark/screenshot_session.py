"""Session-only clipboard screenshot gate; no screenshot persists past restart."""
from __future__ import annotations
import time

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 32 * 1024 * 1024


class ScreenshotSession:
    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._png = None
        self._captured = None

    def clear(self):
        self._png = None
        self._captured = None

    def record(self, png: bytes):
        if not isinstance(png, bytes) or not png.startswith(PNG_MAGIC) or len(png) > MAX_PNG_BYTES:
            self.clear()
            return False
        self._png = png
        self._captured = self._clock()
        return True

    def eligible(self, timeout_seconds: int) -> bool:
        """A zero-second limit disables the quick action; history remains usable."""
        return (type(timeout_seconds) is int and 0 < timeout_seconds <= 3600
                and self._captured is not None and self._png is not None
                and 0 <= self._clock() - self._captured < timeout_seconds)

    def current_png(self, timeout_seconds: int) -> bytes | None:
        return self._png if self.eligible(timeout_seconds) else None
