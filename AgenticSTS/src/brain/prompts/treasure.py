# ruff: noqa: E501
"""Prompt template for treasure chest relic decisions.

Multi-factor relic evaluation framework.
Designed for Qwen 3.5 9B -- explicit scoring, auditable reasoning.
"""

from __future__ import annotations

import config

from src.brain.prompts._deck_fmt import format_deck_section
from src.mcp_client.upstream_models import RawDeckCardPayload
from src.state.game_state import GameState


def build_treasure_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
) -> str:
    """Build a prompt for treasure chest relic claiming.

    Treasure chests can offer one or more relics. The LLM decides which
    to take (or whether to skip if possible).
    """
    tr = gs.chest
    if not tr or not tr.relic_options:
        return ""

    lines = [
        "## Treasure Chest",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold}",
    ]

    lines.append(f"Act: {gs.act} | Floor: {gs.floor}")

    lines.extend(format_deck_section(deck))

    if relics:
        lines.append("")
        lines.append("## Current Relics: " + ", ".join(relics))

    lines.append("")
    lines.append("## Available Relics")
    for r in tr.relic_options:
        lines.append(f"- [index={r.index}] {r.name} ({r.rarity})")

    # Compact guidance
    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        lines.append("Almost always take a relic — relics compound across every remaining combat.")
        lines.append("Energy/draw relics are S-tier. Skip only if the downside directly destroys your strategy.")

    return "\n".join(lines)
