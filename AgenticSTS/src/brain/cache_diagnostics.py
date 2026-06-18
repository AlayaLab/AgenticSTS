"""Helpers for Anthropic prompt-cache diagnostics."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def _contains_cache_control(obj: Any) -> bool:
    """Return True if ``obj`` contains a ``cache_control`` marker anywhere."""
    if isinstance(obj, dict):
        if "cache_control" in obj:
            return True
        return any(_contains_cache_control(v) for v in obj.values())
    if isinstance(obj, list | tuple):
        return any(_contains_cache_control(v) for v in obj)
    return False


def _json_default(obj: Any) -> Any:
    """Best-effort serializer for SDK block objects in diagnostics."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return vars(obj)
    return repr(obj)


def compute_cache_prefix_hash(
    *,
    tools: list[dict[str, Any]] | None,
    system: list[dict[str, Any]] | None,
    messages: list[dict[str, Any]] | None,
) -> str:
    """Hash the cacheable Anthropic request prefix.

    Anthropic prompt caching considers request content in this order:
    ``tools -> system -> messages`` up to and including the last
    ``cache_control`` breakpoint.  This hash lets us compare whether two
    requests had the same cacheable prefix, independent of the dynamic tail.
    """
    current = {
        "tools": [],
        "system": [],
        "messages": [],
    }
    last_prefix: dict[str, Any] | None = None

    def add(section: str, item: Any) -> None:
        nonlocal last_prefix
        current[section].append(item)
        if _contains_cache_control(item):
            last_prefix = copy.deepcopy(current)

    for tool in tools or []:
        add("tools", tool)
    for block in system or []:
        add("system", block)
    for msg in messages or []:
        add("messages", msg)

    if last_prefix is None:
        return ""

    payload = json.dumps(
        last_prefix,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
