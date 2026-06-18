# ruff: noqa: E501
"""Prompt templates for map navigation decisions.

Two scenarios:
- Scenario A (build_route_selection_prompt): Full-context route selection
  at act start or on re-plan trigger.
- Scenario B (build_map_step_prompt): Compact step-by-step walking with
  existing plan.
"""

from __future__ import annotations

import config
from src.brain.prompts._relic_fmt import format_relic_hints
from src.brain.route_planner import RoutePath
from src.mcp_client.upstream_models import RawMapNodePayload
from src.state.game_state import GameState


def build_route_selection_prompt(
    gs: GameState,
    routes_text: str,
    relics: list[str] | None = None,
    strategic_thread: str = "",
    replan_reason: str = "",
) -> str:
    """Build Scenario A prompt: full-context route selection.

    Used at act start or when re-plan is triggered. Includes full game
    state so the LLM can make an informed route choice.
    """
    lines = [
        "## Route Selection",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold} | Act: {gs.act} | Floor: {gs.floor}",
    ]

    if gs.character:
        lines.append(f"Character: {gs.character} | Deck: {gs.deck_size} cards")

    # Potions
    if gs.potions:
        potion_names = [p.name for p in gs.potions if p.name]
        if potion_names:
            lines.append(f"Potions: [{', '.join(potion_names)}]")

    # Relics
    if not config.PROMPT_HINT_FILTER:
        relic_section = format_relic_hints(relics or [], context="map")
        if relic_section:
            lines.append(relic_section)

    # Strategic thread
    if strategic_thread:
        lines.append(f"\nStrategic Thread: {strategic_thread}")

    # Re-plan reason
    if replan_reason:
        lines.append(f"\n**Re-routing because:** {replan_reason}")

    # Candidate routes
    lines.append("")
    lines.append("## Candidate Routes (from current position to Boss)")
    lines.append(routes_text)

    # Response schema
    lines.append("")
    lines.append("Choose the route that best fits your current state. Respond with:")
    lines.append('```json')
    lines.append('{"route": <number>, "reasoning": "..."}')
    lines.append('```')

    return "\n".join(lines)


def build_map_step_prompt(
    gs: GameState,
    route: RoutePath,
    current_step_index: int,
    options: list[RawMapNodePayload],
    relics: list[str] | None = None,
) -> str:
    """Build Scenario B prompt: compact step-by-step walking.

    Used for normal per-node decisions when a plan exists and no re-plan
    is triggered. Shows the route with a [HERE] marker and recommends
    the next node.
    """
    lines = [
        "## Map Navigation",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold} | Act: {gs.act} | Floor: {gs.floor}",
    ]

    # Show route with [HERE] marker
    route_parts: list[str] = []
    for i, ntype in enumerate(route.nodes):
        if i == current_step_index:
            route_parts.append("[HERE]")
        route_parts.append(ntype)
    if current_step_index >= len(route.nodes):
        route_parts.append("[HERE]")

    lines.append(f"\nCurrent route: {' -> '.join(route_parts)}")

    # Recommend next node
    next_idx = current_step_index
    if next_idx < len(route.nodes):
        next_type = route.nodes[next_idx]
        next_coord = route.coords[next_idx]
        lines.append(f"Next recommended: {next_type}(c{next_coord[0]},r{next_coord[1]}) -- step {next_idx + 1} of route")

    # Available options
    lines.append("\nAvailable nodes:")
    recommended_coord = route.coords[next_idx] if next_idx < len(route.coords) else None
    for opt in options:
        marker = "  <- route recommends" if (opt.col, opt.row) == recommended_coord else ""
        lines.append(f"- [index={opt.index}] {opt.node_type} at c{opt.col},r{opt.row}{marker}")

    if not config.PROMPT_HINT_FILTER:
        relic_section = format_relic_hints(relics or [], context="map")
        if relic_section:
            lines.append("")
            lines.append(relic_section)

    lines.append("\nYou may deviate from the route. Explain why if you do.")

    return "\n".join(lines)
