"""Combat quality scoring for online skill-confidence updates."""

from __future__ import annotations


def compute_combat_quality_score(
    combat_type: str,
    hp_before: int,
    hp_after: int,
    *,
    won: bool,
) -> float:
    """Return a combat outcome weight for confidence updates.

    For wins, this is a discrete quality multiplier.
    For losses, returning 1.0 means "apply the full failure weight" rather than
    "this was high quality".
    """
    if not won:
        return 1.0

    ratio = max(0, hp_before - hp_after) / max(hp_before, 1)

    if combat_type == "monster":
        if ratio <= 0.05:
            return 1.0
        if ratio <= 0.20:
            return 0.75
        return 0.45

    if combat_type == "elite":
        if ratio <= 0.10:
            return 1.0
        if ratio <= 0.30:
            return 0.75
        return 0.55

    if combat_type == "boss":
        if ratio <= 0.20:
            return 1.0
        if ratio <= 0.45:
            return 0.80
        return 0.65

    return 1.0
