"""Entity name normalization for cross-version matching."""
from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def slug(name: str) -> str:
    """Normalize an entity name for comparison.

    Lowercase, strip Unicode punctuation, collapse whitespace, strip
    trailing upgrade markers ("+", "++"). Idempotent.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).lower()
    s = s.rstrip("+")
    s = _PUNCT_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    return s
