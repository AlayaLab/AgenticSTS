"""Enemy-key normalization helpers for memory retrieval and consolidation."""

from __future__ import annotations

import re

_MULTI_PREFIX = "multi:"
_TEST_SUBJECT_SUFFIX_RE = re.compile(r"\s+#c\d+\s*$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_enemy_name(name: str) -> str:
    """Normalize a single enemy display name for matching.

    Current special case:
    - ``Test Subject #C10`` and similar variants collapse to ``Test Subject``.
    """
    text = (name or "").replace("_", " ").strip()
    if not text:
        return ""
    text = _WHITESPACE_RE.sub(" ", text)
    if text.lower().startswith("test subject"):
        text = _TEST_SUBJECT_SUFFIX_RE.sub("", text).strip()
    return text


def normalize_enemy_key(enemy_key: str) -> str:
    """Normalize a combat enemy key while preserving display-friendly casing."""
    text = (enemy_key or "").strip()
    if not text:
        return ""
    if text.lower().startswith(_MULTI_PREFIX):
        raw_names = [part.strip() for part in text[len(_MULTI_PREFIX):].split("+")]
        names: list[str] = []
        for part in raw_names:
            normalized = normalize_enemy_name(part)
            if normalized:
                names.append(normalized)
        if not names:
            return "unknown"
        return _MULTI_PREFIX + "+".join(sorted(names, key=str.lower))
    return normalize_enemy_name(text)


def enemy_key_lookup(enemy_key: str) -> str:
    """Normalize an enemy key for dictionary lookup / equality checks."""
    return normalize_enemy_key(enemy_key).lower()
