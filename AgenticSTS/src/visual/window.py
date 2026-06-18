"""Game window detection via ctypes (no pywin32 dependency).

Pure ctypes implementation adapted from STS2Agent.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import time

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

# Constants
SW_RESTORE = 9
GW_HWNDNEXT = 2

# Callback type for EnumWindows
WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
)


class GameWindow:
    """Finds and tracks the Slay the Spire 2 window using ctypes."""

    def __init__(self, title_fragment: str = "Slay the Spire 2") -> None:
        self._title_fragment = title_fragment
        self._hwnd: int | None = None

    @property
    def hwnd(self) -> int | None:
        return self._hwnd

    def find(self) -> int | None:
        """Search for the game window by title substring."""
        results: list[int] = []

        @WNDENUMPROC
        def _enum_cb(hwnd, _lparam):
            if user32.IsWindowVisible(hwnd):
                buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(hwnd, buf, 256)
                title = buf.value
                if self._title_fragment in title:
                    results.append(hwnd)
            return True

        user32.EnumWindows(_enum_cb, 0)

        if results:
            self._hwnd = results[0]
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(self._hwnd, buf, 256)
            logger.info("Found window: hwnd=%d title=%r", self._hwnd, buf.value)
            return self._hwnd

        logger.warning("Window not found: %r", self._title_fragment)
        return None

    def get_rect(self) -> tuple[int, int, int, int]:
        """Return (left, top, width, height) of the client area in screen coords."""
        if self._hwnd is None:
            raise RuntimeError("Window not found. Call find() first.")

        rect = ctypes.wintypes.RECT()
        user32.GetClientRect(self._hwnd, ctypes.byref(rect))
        width = rect.right - rect.left
        height = rect.bottom - rect.top

        # Convert client (0,0) to screen coords
        pt = ctypes.wintypes.POINT(0, 0)
        user32.ClientToScreen(self._hwnd, ctypes.byref(pt))

        return (pt.x, pt.y, width, height)

    def activate(self) -> bool:
        """Bring the game window to the foreground."""
        if self._hwnd is None:
            return False
        try:
            if user32.GetForegroundWindow() == self._hwnd:
                return True

            # Alt key trick to bypass foreground lock
            user32.keybd_event(0x12, 0, 0, 0)       # Alt down
            user32.keybd_event(0x12, 0, 0x0002, 0)   # Alt up

            user32.ShowWindow(self._hwnd, SW_RESTORE)
            user32.SetForegroundWindow(self._hwnd)

            time.sleep(0.05)
            if user32.GetForegroundWindow() != self._hwnd:
                user32.SetForegroundWindow(self._hwnd)
                time.sleep(0.05)

            return user32.GetForegroundWindow() == self._hwnd
        except Exception:
            logger.debug("Window activation failed", exc_info=True)
            return False
