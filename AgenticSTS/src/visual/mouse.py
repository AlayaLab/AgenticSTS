"""Mouse input via pyautogui.

Adapted from the upstream input/mouse.py.
Simplified for menu navigation only.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pyautogui

if TYPE_CHECKING:
    from src.visual.window import GameWindow

logger = logging.getLogger(__name__)

pyautogui.PAUSE = 0.0
pyautogui.FAILSAFE = True

CLICK_DELAY = 0.3


class GameInput:
    """Translates game coordinates to screen coordinates and performs clicks."""

    def __init__(self, window: GameWindow) -> None:
        self._window = window

    def click_relative(self, rx: float, ry: float) -> None:
        """Click at relative coordinates (0.0-1.0)."""
        rx = max(0.0, min(1.0, rx))
        ry = max(0.0, min(1.0, ry))
        self._window.activate()
        time.sleep(0.1)
        left, top, width, height = self._window.get_rect()
        sx = left + int(rx * width)
        sy = top + int(ry * height)
        logger.info("click_relative(%.3f, %.3f) -> screen(%d, %d)", rx, ry, sx, sy)
        pyautogui.moveTo(sx, sy)
        time.sleep(0.05)
        pyautogui.mouseDown()
        time.sleep(0.06)
        pyautogui.mouseUp()
        time.sleep(CLICK_DELAY)
