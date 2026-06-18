"""PID + heartbeat advisory lock for postrun stages.

Replaces the original ``filelock``-backed implementation. The OS file lock
released only when the holder process *terminates*, which left the lock
permanently held when a peer process was alive but stuck (e.g. blocked on a
synchronous LLM HTTP read with no timeout). A live agent then queued forever.

This implementation makes liveness explicit: the holder writes its PID and a
``heartbeat_at`` timestamp to ``<data_root>/.postrun.lock`` and refreshes the
heartbeat every ``HEARTBEAT_INTERVAL_S`` seconds from a background asyncio
task. A waiter takes over when (a) the holder PID is no longer alive or
(b) the heartbeat is older than ``STALE_THRESHOLD_S``.

Disable with ``STS2_POSTRUN_LOCK_DISABLED=true`` (single-process runs).

Companion: ``_safe_post_run`` in ``src/agent/loop.py`` runs an independent
hard-wall watchdog (``WATCHDOG_KILL_S``). If the postrun coroutine wedges in
sync code where the heartbeat task can't run either, the watchdog hits
``os._exit`` and OS handle teardown releases this lock.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from src.storage.paths import data_root, machine_id

logger = logging.getLogger(__name__)

# Tunables — see docs/superpowers chat 2026-04-28 for the empirical basis
# (last-5-days postrun p99 ≈ 33 min).
HEARTBEAT_INTERVAL_S = 30.0
STALE_THRESHOLD_S = 5 * 60.0       # 300s — heartbeat-stale trigger
WAITER_POLL_INTERVAL_S = 5.0
WAITER_TOTAL_TIMEOUT_S = 65 * 60.0  # 65 min — > watchdog kill (60 min)


def _lock_path() -> Path:
    root = data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root / ".postrun.lock"


def _is_disabled() -> bool:
    return os.getenv("STS2_POSTRUN_LOCK_DISABLED", "").strip().lower() in {"1", "true", "yes"}


def _pid_alive(pid: int) -> bool:
    """Cross-platform PID liveness check without psutil."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259  # GetExitCodeProcess sentinel for "still running"

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        OpenProcess = kernel32.OpenProcess
        OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        OpenProcess.restype = wintypes.HANDLE
        GetExitCodeProcess = kernel32.GetExitCodeProcess
        GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        GetExitCodeProcess.restype = wintypes.BOOL
        CloseHandle = kernel32.CloseHandle
        CloseHandle.argtypes = [wintypes.HANDLE]
        CloseHandle.restype = wintypes.BOOL

        h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            ok = GetExitCodeProcess(h, ctypes.byref(code))
            if not ok:
                return False
            return code.value == STILL_ACTIVE
        finally:
            CloseHandle(h)
    else:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write JSON via tmp + os.replace so readers never see torn content."""
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{uuid.uuid4().hex[:6]}")
    data = json.dumps(payload).encode("utf-8")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)


def _read_lock(path: Path) -> dict | None:
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return None


def _make_payload(token: str) -> dict:
    now = time.time()
    return {
        "pid": os.getpid(),
        "machine_id": machine_id(),
        "host": socket.gethostname(),
        "token": token,
        "acquired_at": now,
        "heartbeat_at": now,
    }


def _try_takeover(path: Path, token: str, prior: dict | None) -> bool:
    """Attempt to claim a stale or vacant lock.

    Atomically writes our payload via os.replace, then re-reads after a small
    delay to confirm no other waiter beat us. Returns True on confirmed
    ownership.
    """
    payload = _make_payload(token)
    try:
        _atomic_write_json(path, payload)
    except OSError as exc:
        logger.warning("postrun_lock: write failed during takeover: %s", exc)
        return False

    # CAS verify — sleep a tiny random-ish window then re-read. If two waiters
    # race, the later writer wins os.replace; the loser's re-read shows a
    # different token and gives up. Token is unique per waiter.
    time.sleep(0.05)
    current = _read_lock(path)
    if not current or current.get("token") != token:
        if prior:
            logger.info(
                "postrun_lock: lost takeover race (current pid=%s token=%s)",
                current.get("pid") if current else None,
                (current.get("token") if current else None),
            )
        return False
    return True


def _refresh_heartbeat(path: Path, token: str) -> bool:
    """Update heartbeat_at if we still own the lock. Returns False if our
    ownership was stolen (someone else's takeover beat the heartbeat)."""
    current = _read_lock(path)
    if not current or current.get("token") != token:
        return False
    current["heartbeat_at"] = time.time()
    try:
        _atomic_write_json(path, current)
    except OSError:
        return False
    return True


async def _heartbeat_loop(path: Path, token: str) -> None:
    while True:
        try:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
        except asyncio.CancelledError:
            return
        ok = await asyncio.to_thread(_refresh_heartbeat, path, token)
        if not ok:
            logger.warning(
                "postrun_lock: heartbeat lost ownership (taken over by another process)"
            )
            return


@asynccontextmanager
async def postrun_lock() -> AsyncIterator[bool]:
    """Acquire the global postrun advisory lock.

    Yields True when the lock is held, False when disabled or after the
    waiter total timeout (caller proceeds without serialization rather than
    abandoning postrun entirely — the watchdog in _safe_post_run is the
    backstop).
    """
    if _is_disabled():
        yield False
        return

    path = _lock_path()
    token = uuid.uuid4().hex
    started = time.monotonic()
    held = False

    while not held:
        existing = await asyncio.to_thread(_read_lock, path)
        can_takeover = False

        if existing is None:
            can_takeover = True
        else:
            holder_pid = existing.get("pid")
            holder_machine = existing.get("machine_id") or "?"
            heartbeat_at = float(existing.get("heartbeat_at") or 0.0)
            age = time.time() - heartbeat_at if heartbeat_at else float("inf")

            # Only PID-check if the holder is on the same physical host.
            # Use hostname (not machine_id, which is a user-configurable
            # provenance label and may differ between agents on one box).
            # Cross-host lockfiles (sibling-repo on a network share) can't
            # be checked via local PID — fall back to heartbeat age only.
            same_host = (existing.get("host") == socket.gethostname())
            pid_dead = same_host and isinstance(holder_pid, int) and not _pid_alive(holder_pid)
            stale = age > STALE_THRESHOLD_S

            if pid_dead:
                logger.warning(
                    "postrun_lock: holder pid=%s machine=%s is dead, taking over",
                    holder_pid, holder_machine,
                )
                can_takeover = True
            elif stale:
                logger.warning(
                    "postrun_lock: holder pid=%s machine=%s heartbeat stale (%.0fs > %.0fs), taking over",
                    holder_pid, holder_machine, age, STALE_THRESHOLD_S,
                )
                can_takeover = True

        if can_takeover:
            ok = await asyncio.to_thread(_try_takeover, path, token, existing)
            if ok:
                held = True
                break

        elapsed = time.monotonic() - started
        if elapsed >= WAITER_TOTAL_TIMEOUT_S:
            logger.error(
                "postrun_lock: gave up after %.0fs waiting for %s; proceeding without lock",
                elapsed, path,
            )
            yield False
            return

        if existing:
            logger.info(
                "postrun_lock: holder pid=%s machine=%s alive, heartbeat age %.0fs, waited %.0fs",
                existing.get("pid"),
                existing.get("machine_id"),
                time.time() - float(existing.get("heartbeat_at") or 0.0),
                elapsed,
            )
        await asyncio.sleep(WAITER_POLL_INTERVAL_S)

    # Lock acquired — start heartbeat task.
    logger.info(
        "postrun_lock: acquired (waited %.1fs, pid=%d machine=%s)",
        time.monotonic() - started,
        os.getpid(),
        machine_id(),
    )
    hb_task = asyncio.create_task(_heartbeat_loop(path, token))
    try:
        yield True
    finally:
        hb_task.cancel()
        try:
            await hb_task
        except (asyncio.CancelledError, Exception):
            pass
        # Only delete the lock file if we still own it. If a waiter took over
        # (heartbeat lost ownership), don't stomp their state.
        try:
            current = _read_lock(path)
            if current and current.get("token") == token:
                try:
                    path.unlink()
                except OSError:
                    pass
        except Exception:
            logger.warning("postrun_lock: release cleanup failed", exc_info=True)
