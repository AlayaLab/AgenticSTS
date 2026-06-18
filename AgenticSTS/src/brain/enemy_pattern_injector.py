# src/brain/enemy_pattern_injector.py
"""Format enemy behavior patterns from past combat episodes.

Provides two functions:
- format_enemy_patterns(): Full pattern history for round 1 (via prompt_injector)
- format_upcoming_patterns(): Compact upcoming-only for round 2+ (via CombatConversation)
"""

from __future__ import annotations

from src.brain.prompts._intent_fmt import is_move_id_like

_MAX_EPISODES = 3
_MAX_ROUNDS = 8
_MAX_UPCOMING = 3


def _format_intents(intents: tuple[str, ...]) -> str:
    """Join multiple intents for a single round."""
    return " + ".join(intents) if intents else "Unknown"


def _round_has_opaque_move_ids(round_obj) -> bool:
    """True when a stored round only exposes internal move ids."""
    return any(is_move_id_like(intent) for intent in getattr(round_obj, "enemy_intents", ()))


def format_enemy_patterns(
    episodes: list,
    current_round: int = 1,
) -> str:
    """Format full enemy patterns for round 1 injection.

    Returns empty string if no episodes exist.
    """
    if not episodes:
        return ""

    lines = [
        "## Enemy Patterns",
        f"Current round: R{current_round}",
        "These are possible move patterns from past fights, not guaranteed future actions.",
        "",
    ]

    pattern_idx = 1
    for ep in episodes[:_MAX_EPISODES]:
        round_strs = []
        for r in ep.rounds[:_MAX_ROUNDS]:
            if _round_has_opaque_move_ids(r):
                round_strs = []
                break
            intent_str = _format_intents(r.enemy_intents)
            round_strs.append(f"R{r.round_num} {intent_str}")
        if not round_strs:
            continue
        lines.append(f"- Past fight {pattern_idx}: {' → '.join(round_strs)}")
        pattern_idx += 1

    upcoming = format_upcoming_patterns(episodes, current_round)
    if upcoming:
        lines.append("")
        lines.append(upcoming)

    return "\n".join(lines)


def format_upcoming_patterns(
    episodes: list,
    current_round: int,
) -> str:
    """Format upcoming enemy moves for round 2+ injection.

    Extracts 1-3 rounds after current_round from each past episode.
    Returns empty string if no upcoming data exists.
    """
    if not episodes:
        return ""

    patterns: list[str] = []
    pattern_idx = 1
    for ep in episodes[:_MAX_EPISODES]:
        upcoming_rounds = [
            r for r in ep.rounds
            if r.round_num > current_round and not _round_has_opaque_move_ids(r)
        ][:_MAX_UPCOMING]
        if not upcoming_rounds:
            continue
        round_strs = [
            f"R{r.round_num} {_format_intents(r.enemy_intents)}"
            for r in upcoming_rounds
        ]
        patterns.append(f"- Pattern {chr(64 + pattern_idx)}: {' → '.join(round_strs)}")
        pattern_idx += 1

    if not patterns:
        return ""

    lines = [f"Likely upcoming after R{current_round}:"]
    lines.extend(patterns)
    return "\n".join(lines)
