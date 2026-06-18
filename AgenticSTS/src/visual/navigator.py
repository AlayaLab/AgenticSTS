"""Visual menu navigator — VLM + Windows API for game restart.

Uses:
  1. MCP API to detect current screen state (reliable)
  2. VLM (Qwen 3.5 9B vision) to locate buttons on screenshot
  3. Windows API (pyautogui) mouse clicks to interact

This replaces the unreliable C# reflection-based embark/menu navigation.
The MCP API is still used for all in-game actions (combat, map, etc.).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import time

import cv2
import numpy as np
import ollama
import pyautogui

from src.visual.capture import ScreenCapture
from src.visual.mouse import GameInput
from src.visual.window import GameWindow

logger = logging.getLogger(__name__)

# VLM config
VLM_MODEL = "qwen3.5:9b"
VLM_BASE_URL = "http://localhost:11434"
JPEG_QUALITY = 85

# Prompts for each menu screen
LOCATE_PROMPT = (
    "You are looking at a Slay the Spire 2 game screenshot.\n"
    "Find the {target} on this screen.\n"
    "Reply ONLY in this exact format:\n"
    "FOUND: yes/no\n"
    "X: <relative x position 0.0-1.0 from left>\n"
    "Y: <relative y position 0.0-1.0 from top>\n"
)

# Known button targets for each state
MENU_TARGETS = {
    "menu_main": "Singleplayer button (text that says 'Singleplayer')",
    "menu_singleplayer": "Standard mode card (the leftmost card that says 'Standard')",
    "character_select": (
        "Embark button (the checkmark/tick icon at the bottom-right corner "
        "of the screen)"
    ),
    "game_over": "clickable area to dismiss the game over screen (center of screen)",
    "overlay": "Continue button at the bottom center of the Defeat/Victory screen",
    "timeline_back": (
        "Back arrow button (red arrow pointing left) in the bottom-left corner "
        "of the screen"
    ),
    "timeline_epoch": (
        "the glowing or pulsing purple locked epoch tile in the center area of "
        "the timeline. It has chains and a lock icon and is "
        "brighter/highlighted compared to other tiles"
    ),
    "timeline_unlock": "Close button or Continue button or OK button to dismiss the unlock popup",
    "epoch_inspect": "Close button at the bottom center of the screen (text says 'Close')",
    "unknown_screen": (
        "the most prominent clickable button on screen "
        "(Continue, OK, Close, Back, or any button)"
    ),
}

# Hardcoded fallback positions (relative coords) if VLM fails
FALLBACK_POSITIONS: dict[str, tuple[float, float]] = {
    "menu_main": (0.42, 0.47),  # Singleplayer text
    "menu_singleplayer": (0.29, 0.40),  # Standard card
    "character_select": (0.96, 0.78),  # Embark checkmark
    "game_over": (0.50, 0.50),  # Center click
    "overlay": (0.50, 0.72),  # Continue button on Defeat screen
    "timeline_back": (0.04, 0.78),  # Back arrow bottom-left
    "timeline_epoch": (0.49, 0.78),  # Glowing purple epoch center
    "timeline_unlock": (0.50, 0.72),  # Close/OK button center-bottom
    "epoch_inspect": (0.50, 0.72),  # Close button center-bottom
    "unknown_screen": (0.50, 0.72),  # Generic center-bottom click
}


class VisualNavigator:
    """Navigates STS2 menus using VLM vision + mouse clicks.

    Immutable config — all state is in the underlying window/capture objects.
    """

    def __init__(self) -> None:
        self._window = GameWindow()
        self._capture: ScreenCapture | None = None
        self._input: GameInput | None = None
        self._vlm = ollama.Client(host=VLM_BASE_URL)
        self._initialized = False

    def _ensure_init(self) -> bool:
        """Lazy-init: find window and set up capture/input."""
        if self._initialized:
            return True

        hwnd = self._window.find()
        if hwnd is None:
            logger.error("Cannot find STS2 window")
            return False

        self._capture = ScreenCapture(self._window)
        self._input = GameInput(self._window)
        self._initialized = True
        logger.info("VisualNavigator initialized (hwnd=%d)", hwnd)
        return True

    def _screenshot(self) -> np.ndarray | None:
        """Take a screenshot of the game window."""
        if not self._ensure_init():
            return None
        try:
            return self._capture.grab()
        except Exception:
            logger.exception("Screenshot failed")
            return None

    def _locate_element(self, frame: np.ndarray, description: str) -> tuple[float, float] | None:
        """Use VLM to locate a UI element on the screenshot.

        Returns (rx, ry) relative coords, or None if not found.
        """
        prompt = LOCATE_PROMPT.format(target=description)
        img_b64 = _encode_frame(frame)

        try:
            t0 = time.perf_counter()
            response = self._vlm.chat(
                model=VLM_MODEL,
                messages=[{"role": "user", "content": prompt, "images": [img_b64]}],
                think=False,
                options={"temperature": 0.1, "num_predict": 128},
            )
            elapsed = (time.perf_counter() - t0) * 1000

            text = response.message.content or ""
            if "</think>" in text:
                text = text.split("</think>")[-1].strip()

            logger.debug("VLM locate [%.0fms]: %s", elapsed, text[:100])

            x, y, found = None, None, False
            for line in text.strip().splitlines():
                upper = line.strip().upper()
                if upper.startswith("X:"):
                    m = re.search(r"[\d.]+", line.split(":", 1)[1])
                    if m:
                        x = float(m.group())
                elif upper.startswith("Y:"):
                    m = re.search(r"[\d.]+", line.split(":", 1)[1])
                    if m:
                        y = float(m.group())
                elif upper.startswith("FOUND:"):
                    found = "yes" in line.lower()

            if found and x is not None and y is not None:
                if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                    logger.info("VLM located '%s' at (%.3f, %.3f)", description, x, y)
                    return (x, y)

            logger.debug("VLM could not locate '%s'", description)
            return None

        except Exception:
            logger.exception("VLM locate failed for '%s'", description)
            return None

    def _click_at(self, rx: float, ry: float) -> None:
        """Click at relative coordinates on the game window."""
        if self._input is not None:
            self._input.click_relative(rx, ry)

    def click_for_state(self, state_key: str) -> bool:
        """Screenshot → VLM locate → click for a given menu state.

        state_key: one of menu_main, menu_singleplayer, character_select, etc.
        Returns True if a click was performed.
        """
        if not self._ensure_init():
            return False

        frame = self._screenshot()
        if frame is None:
            return False

        # Try VLM first
        target_desc = MENU_TARGETS.get(state_key, "")
        if target_desc:
            pos = self._locate_element(frame, target_desc)
            if pos is not None:
                self._click_at(pos[0], pos[1])
                return True

        # Fallback to hardcoded position
        fallback = FALLBACK_POSITIONS.get(state_key)
        if fallback is not None:
            logger.info(
                "Using fallback position for '%s': (%.3f, %.3f)",
                state_key,
                fallback[0],
                fallback[1],
            )
            self._click_at(fallback[0], fallback[1])
            return True

        logger.warning("No target for state_key='%s'", state_key)
        return False

    def _press_escape(self) -> None:
        """Press Escape key as fallback for dismissing screens."""
        if not self._ensure_init():
            return
        self._window.activate()
        time.sleep(0.1)
        pyautogui.press("escape")
        logger.info("Pressed ESC as fallback")
        time.sleep(0.3)

    async def start_new_run(
        self,
        mcp_client,
        character: str | None = None,
        max_attempts: int = 40,
    ) -> bool:
        """Navigate from any non-run state to a new run using visual clicks.

        Uses MCP API to know the current state, visual clicks to navigate.
        If stuck on the same state for too many attempts, uses ESC as fallback.
        """
        in_run_states = {
            "map",
            "monster",
            "elite",
            "boss",
            "event",
            "rest_site",
            "shop",
            "combat_rewards",
            "card_reward",
            "card_select",
            "relic_select",
            "treasure",
            "hand_select",
        }

        prev_state = ""
        same_state_count = 0

        for attempt in range(1, max_attempts + 1):
            try:
                raw = await mcp_client.get_state()
                state_type = raw.get("state_type", "unknown")
                submenu = raw.get("submenu", "")
            except Exception as e:
                logger.warning("start_new_run: MCP state error: %s", e)
                await asyncio.sleep(2.0)
                continue

            logger.info(
                "Visual nav [%d/%d]: state=%s submenu=%s",
                attempt,
                max_attempts,
                state_type,
                submenu,
            )

            # Already in a run
            if state_type in in_run_states:
                logger.info("Already in a run (state=%s)", state_type)
                return True

            # Track stuck detection
            state_sig = f"{state_type}:{submenu}"
            if state_sig == prev_state:
                same_state_count += 1
            else:
                same_state_count = 0
                prev_state = state_sig

            # If stuck on same state for 5+ attempts, try ESC
            if same_state_count >= 5:
                logger.warning(
                    "Stuck on '%s' for %d attempts, trying ESC",
                    state_type,
                    same_state_count,
                )
                self._press_escape()
                await asyncio.sleep(2.0)
                same_state_count = 0  # Reset after ESC attempt
                continue

            # Map state to click target (pass full raw data for epoch detection)
            state_key = self._map_state_to_key(state_type, submenu, raw)

            # epoch_inspect / timeline_unlock: ESC is fastest and most reliable
            if state_key in ("epoch_inspect", "timeline_unlock"):
                self._press_escape()
                await asyncio.sleep(2.0)
                continue

            # Visual click
            clicked = self.click_for_state(state_key)
            if clicked:
                logger.info("Clicked for '%s', waiting for transition...", state_key)
            else:
                logger.warning("Click failed for '%s'", state_key)

            # Wait for animation/transition
            await asyncio.sleep(3.0)

        logger.error("Visual start_new_run failed after %d attempts", max_attempts)
        return False

    @staticmethod
    def _map_state_to_key(
        state_type: str,
        submenu: str,
        raw: dict | None = None,
    ) -> str:
        """Map MCP state_type + submenu to our state_key for clicking.

        Uses raw MCP data to distinguish timeline states (epoch to reveal vs back).
        """
        if state_type == "menu":
            if submenu == "singleplayer":
                return "menu_singleplayer"
            return "menu_main"
        if state_type == "character_select":
            return "character_select"
        if state_type in ("game_over", "victory"):
            return "game_over"
        if state_type == "overlay":
            return "overlay"
        if state_type == "timeline":
            # Check if there are epochs waiting to be revealed
            obtained = (raw or {}).get("obtained_epochs", 0)
            has_queued = (raw or {}).get("has_queued_screens", False)
            if obtained > 0 or has_queued:
                return "timeline_epoch"
            return "timeline_back"
        if state_type == "timeline_unlock":
            return "timeline_unlock"
        if state_type == "epoch_inspect":
            return "epoch_inspect"
        # For any unrecognized non-run state, try VLM-based button finding
        return "unknown_screen"


def _encode_frame(frame: np.ndarray) -> str:
    """Encode BGR numpy array to base64 JPEG string."""
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
    if not ok:
        raise ValueError("Failed to encode frame to JPEG")
    return base64.b64encode(buf).decode("ascii")
