"""Game window capture using ctypes + mss (no pywin32 dependency).

Uses mss for screen capture since PrintWindow requires pywin32 DC objects.
mss is reliable for non-occluded windows (game should be visible).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import mss
import numpy as np

if TYPE_CHECKING:
    from src.visual.window import GameWindow

logger = logging.getLogger(__name__)


class ScreenCapture:
    """Captures game frames as BGR numpy arrays via mss."""

    def __init__(self, window: GameWindow) -> None:
        self._window = window
        self._sct = mss.mss()

    def grab(self) -> np.ndarray:
        """Capture the full game window. Returns BGR (H, W, 3)."""
        left, top, width, height = self._window.get_rect()
        monitor = {"left": left, "top": top, "width": width, "height": height}
        raw = self._sct.grab(monitor)
        # mss returns BGRA; drop alpha channel
        frame = np.array(raw, dtype=np.uint8)[:, :, :3]
        return frame
