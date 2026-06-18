"""Resolve the STS2 executable path and launch the game with a chosen API port.

Used by scripts/run_agent.py when --launch-game is passed so the agent owns
the game subprocess lifecycle and port assignment. Supports multi-instance
on one machine: each invocation picks its own free port and spawns its own
game process.

Resolution priority:
  1. STS2_GAME_PATH env var (explicit override; ~/ expanded).
  2. OS-default Steam install locations.
  3. Any Steam library listed in steamapps/libraryfolders.vdf.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import socket
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_APP_NAME = "Slay the Spire 2"


def _default_candidates() -> list[Path]:
    home = Path.home()
    sysname = platform.system()
    if sysname == "Darwin":
        return [
            home / "Library/Application Support/Steam/steamapps/common"
                 / _APP_NAME / "SlayTheSpire2.app/Contents/MacOS/Slay the Spire 2",
        ]
    if sysname == "Windows":
        return [
            Path("C:/Program Files (x86)/Steam/steamapps/common") / _APP_NAME / "SlayTheSpire2.exe",
            Path("C:/Program Files/Steam/steamapps/common") / _APP_NAME / "SlayTheSpire2.exe",
        ]
    return [
        home / ".steam/steam/steamapps/common" / _APP_NAME / "SlayTheSpire2.x86_64",
        home / ".local/share/Steam/steamapps/common" / _APP_NAME / "SlayTheSpire2.x86_64",
    ]


def _libraryfolders_vdf() -> Path:
    sysname = platform.system()
    if sysname == "Darwin":
        return Path.home() / "Library/Application Support/Steam/steamapps/libraryfolders.vdf"
    if sysname == "Windows":
        return Path("C:/Program Files (x86)/Steam/steamapps/libraryfolders.vdf")
    return Path.home() / ".steam/steam/steamapps/libraryfolders.vdf"


def _steam_libraries() -> list[Path]:
    vdf = _libraryfolders_vdf()
    if not vdf.exists():
        return []
    text = vdf.read_text(encoding="utf-8", errors="replace")
    return [Path(p) for p in re.findall(r'"path"\s+"([^"]+)"', text)]


def _exe_inside_library(lib: Path) -> Path:
    base = lib / "steamapps/common" / _APP_NAME
    if platform.system() == "Darwin":
        return base / "SlayTheSpire2.app/Contents/MacOS/Slay the Spire 2"
    if platform.system() == "Windows":
        return base / "SlayTheSpire2.exe"
    return base / "SlayTheSpire2.x86_64"


def resolve_game_path() -> Path:
    """Locate the STS2 game executable. Raises FileNotFoundError if absent."""
    if override := os.environ.get("STS2_GAME_PATH"):
        p = Path(override).expanduser()
        if not p.exists():
            raise FileNotFoundError(f"STS2_GAME_PATH does not exist: {p}")
        return p
    for cand in _default_candidates():
        if cand.exists():
            return cand
    for lib in _steam_libraries():
        cand = _exe_inside_library(lib)
        if cand.exists():
            return cand
    raise FileNotFoundError(
        "Could not locate Slay the Spire 2. Set STS2_GAME_PATH to the executable "
        "(the Mach-O binary inside the .app on macOS, not the .app itself)."
    )


def pick_free_port() -> int:
    """Ask the OS for a free TCP port on 127.0.0.1."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pick_free_port_in_range(start: int, end: int) -> int | None:
    """Return the lowest free TCP port in [start, end], or None if all are busy.

    Used for the monitor port so the frontend's auto-scan (which covers a
    fixed range) can discover the agent without manual configuration.
    """
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


# Module-level handle to the most-recent launched game subprocess.
# Populated by ``launch_game``, consumed by ``terminate_launched_game``.
# Stored here (instead of in run_agent.py) so the postrun watchdog in
# ``src/agent/loop.py`` can also kill the game before ``os._exit`` —
# without this, a 60-min watchdog kill leaves the game orphaned because
# ``os._exit`` bypasses the cleanup at end of ``run_agent.__main__``.
_launched_proc: subprocess.Popen | None = None


def launch_game(exe: Path, port: int) -> subprocess.Popen:
    """Spawn the game subprocess with STS2_API_PORT set. Caller owns the handle.

    Also stashes the Popen in ``_launched_proc`` so ``terminate_launched_game``
    can be called from any module (e.g. the postrun watchdog) without having
    to thread the handle through.
    """
    global _launched_proc
    env = {**os.environ, "STS2_API_PORT": str(port)}
    proc = subprocess.Popen(
        [str(exe)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _launched_proc = proc
    return proc


def terminate_launched_game() -> None:
    """Terminate the game subprocess launched by ``launch_game``. Idempotent.

    Safe to call from anywhere — main()'s post-gameplay early kill, the
    end-of-``__main__`` cleanup in run_agent.py, and the postrun watchdog
    ``os._exit`` path in ``src/agent/loop.py``. The ``poll()`` guard makes
    second / third calls no-ops, so registering this as the canonical kill
    path avoids double-terminate races.

    Catches ``BaseException`` (not just ``Exception``) so a stray
    ``KeyboardInterrupt`` mid-cleanup can't leave the game orphaned —
    cleanup must complete even when the user is actively Ctrl-C'ing.
    """
    global _launched_proc
    proc = _launched_proc
    if proc is None:
        return
    try:
        if proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass
        except BaseException:
            pass
    finally:
        _launched_proc = None


async def wait_for_ready(
    base_url: str,
    timeout: float = 120.0,
    proc: subprocess.Popen | None = None,
) -> bool:
    """Poll /health until the mod responds or timeout elapses.

    If ``proc`` is supplied, abort early when the game process has died so the
    caller gets a prompt failure instead of waiting out the full timeout.
    """
    deadline = time.monotonic() + timeout
    url = f"{base_url.rstrip('/')}/health"
    async with httpx.AsyncClient(timeout=2.0) as client:
        while time.monotonic() < deadline:
            if proc is not None and proc.poll() is not None:
                return False
            try:
                resp = await client.get(url)
                if resp.status_code < 500:
                    return True
            except (httpx.ConnectError, httpx.ReadTimeout,
                    httpx.RemoteProtocolError, httpx.ConnectTimeout):
                pass
            await asyncio.sleep(0.5)
    return False
