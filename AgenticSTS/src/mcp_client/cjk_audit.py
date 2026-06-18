"""CJK leak detector for mod HTTP responses.

After the mod's locale-blind English-output flip, the mod is supposed to emit
English regardless of the player's active in-game locale. This module scans
incoming response payloads (GET /state, POST /action results, SSE events) for
any CJK characters that slipped through, and appends them to a gitignored log
for debugging.

Usage:
    from src.mcp_client import cjk_audit
    cjk_audit.audit("get_state", state_dict)

Configuration (env):
    STS2_CJK_AUDIT     — "true" (default) to enable, "false" to disable.
    STS2_CJK_AUDIT_LOG — override path (default: <repo>/logs/cjk_leaks.jsonl).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# CJK Unified Ideographs (U+4E00–U+9FFF), CJK Extension A (U+3400–U+4DBF), and the
# Hiragana/Katakana blocks (U+3040–U+30FF) — covers Chinese (zhs/zht), Japanese,
# and Korean Hanja. Korean Hangul (U+AC00–U+D7AF) is also added since the game
# supports kor.
_CJK_RE = re.compile(
    r"[぀-ヿ㐀-䶿一-鿿가-힯]"
)

_ENABLED: bool | None = None
_LOG_PATH: Path | None = None
_LOCK = threading.Lock()
_FIRST_LEAK_LOGGED = False
_SEEN_KEYS: set[tuple[str, str]] = set()


def _is_enabled() -> bool:
    global _ENABLED
    if _ENABLED is None:
        flag = os.getenv("STS2_CJK_AUDIT", "true").strip().lower()
        _ENABLED = flag in ("1", "true", "yes", "on")
    return _ENABLED


def _log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        override = os.getenv("STS2_CJK_AUDIT_LOG")
        if override:
            _LOG_PATH = Path(override)
        else:
            # Repo root is two levels up from this file (src/mcp_client/cjk_audit.py).
            repo_root = Path(__file__).resolve().parents[2]
            _LOG_PATH = repo_root / "logs" / "cjk_leaks.jsonl"
    return _LOG_PATH


def _walk(obj: Any, path: str, hits: list[tuple[str, str]]) -> None:
    """Recurse into obj, recording (jsonpath, sample) for any string with CJK."""
    if isinstance(obj, str):
        if _CJK_RE.search(obj):
            # Truncate long values so the log stays readable.
            sample = obj if len(obj) <= 200 else obj[:200] + "…"
            hits.append((path, sample))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            child_path = f"{path}.{k}" if path else str(k)
            _walk(v, child_path, hits)
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _walk(v, f"{path}[{i}]", hits)
        return
    # Numbers, bools, None — never contain CJK.


def audit(source: str, payload: Any) -> list[tuple[str, str]]:
    """Scan payload for CJK characters and log any findings.

    Args:
        source: Origin label (e.g. "get_state", "post_action:play_card",
                "sse:screen_changed"). Recorded verbatim in the log.
        payload: Any JSON-decoded structure (dict, list, str, ...).

    Returns:
        List of (jsonpath, sample) tuples for hits. Empty if no leaks.
    """
    if not _is_enabled():
        return []
    if payload is None:
        return []

    # Fast path: dump to JSON once and check for any CJK char before walking.
    try:
        blob = json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        # Non-serializable values — fall through to recursive walk.
        blob = ""
    if blob and not _CJK_RE.search(blob):
        return []

    hits: list[tuple[str, str]] = []
    _walk(payload, "", hits)
    if not hits:
        return []

    _record(source, hits)
    return hits


def _record(source: str, hits: list[tuple[str, str]]) -> None:
    global _FIRST_LEAK_LOGGED
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "source": source,
        "count": len(hits),
        "hits": [{"path": p, "sample": s} for p, s in hits],
    }
    line = json.dumps(record, ensure_ascii=False)

    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
    except OSError as e:
        logger.warning("CJK audit: failed to write %s: %s", path, e)

    # Surface the first leak per session, plus any new (source, path) pairs at
    # debug level so the warning stream stays usable.
    with _LOCK:
        if not _FIRST_LEAK_LOGGED:
            _FIRST_LEAK_LOGGED = True
            logger.warning(
                "CJK leak detected from mod source=%s at %s -- see %s for details",
                source, hits[0][0], path,
            )
        for p, _sample in hits:
            key = (source, p)
            if key not in _SEEN_KEYS:
                _SEEN_KEYS.add(key)
                logger.debug("CJK leak: source=%s path=%s", source, p)
