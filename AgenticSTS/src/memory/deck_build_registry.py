"""Character-specific deck build registry helpers.

This is intentionally small for the first pass: it gives runtime retrieval
and postrun consolidation one shared source for active build identities.
"""

from __future__ import annotations

import re

from src.memory.models_v2 import normalize_character

_TAG_RE = re.compile(r"[^a-z0-9]+")

ACTIVE_DECK_BUILDS: dict[str, tuple[str, ...]] = {
    "the silent": ("shiv", "poison"),
}

_DEPRECATED_BUILD_TAGS = frozenset({
    "",
    "general",
    "thin_deck",
    "small_deck",
    "thin_cycle",
    "lean_deck",
})

_BUILD_TAG_ALIASES: dict[str, dict[str, str]] = {
    "the silent": {
        "shiv_burst": "shiv",
        "shiv_cycle": "shiv",
        "shiv_deck": "shiv",
        "zero_cost_attack": "shiv",
        "zero_cost_attacks": "shiv",
        "poison_stacking": "poison",
        "poison_scaling": "poison",
        "poison_control": "poison",
        "poison_deck": "poison",
    },
}


def normalize_build_tag(tag: str) -> str:
    """Normalize a free-form build label to a stable slug."""
    return _TAG_RE.sub("_", (tag or "").strip().lower()).strip("_")


def active_deck_builds(character: str) -> tuple[str, ...]:
    """Return active build guide tags for a character."""
    return ACTIVE_DECK_BUILDS.get(normalize_character(character), ())


def canonical_deck_build_tag(character: str, tag: str) -> str:
    """Map a free-form build tag to an allowed build-guide tag.

    Characters with an active registry only allow registered tags. Characters
    without one may still bootstrap non-deprecated tags during postrun.
    """
    char = normalize_character(character)
    normalized = normalize_build_tag(tag)
    normalized = _BUILD_TAG_ALIASES.get(char, {}).get(normalized, normalized)

    if normalized in _DEPRECATED_BUILD_TAGS:
        return ""

    active = active_deck_builds(char)
    if active and normalized not in active:
        return ""

    return normalized

