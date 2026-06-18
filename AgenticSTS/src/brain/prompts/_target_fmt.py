"""Shared formatting helpers for target labels in prompts."""

from __future__ import annotations


def describe_target_scope(target_index_space: str | None, target_type: str | None = None) -> str:
    """Return a human-readable target scope label for cards and potions."""
    if target_index_space == "enemies":
        return "enemies"
    if target_index_space == "players":
        return "players"

    if target_type in {"AnyEnemy", "Enemy"}:
        return "enemies"
    if target_type in {"AnyPlayer", "AnyAlly", "Player", "Ally"}:
        return "players"

    if target_index_space:
        return target_index_space
    if target_type:
        return target_type
    return "indexed target"
