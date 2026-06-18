# ruff: noqa: E501
"""Prompt template for the Crystal Sphere minigame.

Crystal Sphere is a small-grid divination puzzle. The agent picks a
divination tool (big or small) and reveals hidden cells; revealed
items can be beneficial (relic / gold / potion) or hostile (curse).
The agent decides each step (set tool / click cell / proceed).
"""

from __future__ import annotations

from src.brain.prompts._deck_fmt import format_deck_section
from src.mcp_client.upstream_models import RawDeckCardPayload
from src.state.game_state import GameState


_DECISION_OUTPUT = """## Output (JSON inside <decision>)
Pick one action per turn:

- `{"action": "crystal_sphere_set_tool", "tool": "big" | "small", "reasoning": "...", "strategic_note": "..."}`
- `{"action": "crystal_sphere_click_cell", "x": <int>, "y": <int>, "reasoning": "...", "strategic_note": "..."}`
- `{"action": "crystal_sphere_proceed", "reasoning": "...", "strategic_note": "..."}`

A tool MUST be set before any cells can be clicked. Once `can_proceed`
is true, you may stop the minigame at any moment to lock in the
revealed rewards. Locked options cannot be selected.
"""


def _format_grid(cs) -> str:
    """Render the grid as a compact ASCII diagram.

    `?` = hidden cell, `+` = revealed beneficial, `-` = revealed harmful,
    `.` = revealed neutral / unknown polarity.
    """
    if cs.grid_width <= 0 or cs.grid_height <= 0 or not cs.cells:
        return "(grid empty)"

    matrix = [["·" for _ in range(cs.grid_width)] for _ in range(cs.grid_height)]
    for cell in cs.cells:
        if not (0 <= cell.x < cs.grid_width and 0 <= cell.y < cs.grid_height):
            continue
        if cell.is_hidden:
            matrix[cell.y][cell.x] = "?"
        elif cell.is_good is True:
            matrix[cell.y][cell.x] = "+"
        elif cell.is_good is False:
            matrix[cell.y][cell.x] = "-"
        else:
            matrix[cell.y][cell.x] = "."

    lines: list[str] = []
    header = "    " + " ".join(f"{x}" for x in range(cs.grid_width))
    lines.append(header)
    for y, row in enumerate(matrix):
        lines.append(f" y{y} " + " ".join(row))
    return "\n".join(lines)


def build_crystal_sphere_prompt(
    gs: GameState,
    *,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
) -> str:
    """Build the user-message prompt for Crystal Sphere decisions."""
    cs = gs.crystal_sphere
    if cs is None:
        return "## Crystal Sphere\n(state not available)\n"

    sections: list[str] = []
    sections.append("## Crystal Sphere")

    if cs.instructions_title:
        sections.append(f"**{cs.instructions_title}**")
    if cs.instructions_description:
        sections.append(cs.instructions_description)

    status_bits: list[str] = []
    status_bits.append(f"Active tool: **{cs.tool}**")
    if cs.divinations_left_text:
        status_bits.append(cs.divinations_left_text)
    else:
        status_bits.append(f"Divinations left: {cs.divinations_left}")
    status_bits.append(
        f"Tools available: big={'yes' if cs.can_use_big_tool else 'no'}, "
        f"small={'yes' if cs.can_use_small_tool else 'no'}"
    )
    status_bits.append(f"Can proceed: {'yes' if cs.can_proceed else 'no'}")
    sections.append(" | ".join(status_bits))

    sections.append(f"Grid: {cs.grid_width} × {cs.grid_height}")
    sections.append("```\n" + _format_grid(cs) + "\n```")
    sections.append(
        "Legend: `?`=hidden, `+`=revealed-good, `-`=revealed-harmful, "
        "`.`=revealed-neutral, `·`=out-of-grid."
    )

    if cs.revealed_items:
        sections.append("### Revealed so far")
        for item in cs.revealed_items:
            polarity = "good" if item.is_good else "harmful"
            sections.append(
                f"- ({item.x},{item.y}) {item.item_type} — {polarity}"
            )
    else:
        sections.append("_No cells revealed yet._")

    if cs.clickable_cells:
        coords = ", ".join(f"({c.x},{c.y})" for c in cs.clickable_cells)
        sections.append(f"### Clickable cells ({len(cs.clickable_cells)})")
        sections.append(coords)
    else:
        sections.append("_No cells are currently clickable._ "
                        "(Set a tool first, or proceed to leave.)")

    sections.append("### Run context")
    run_lines: list[str] = []
    run_lines.append(
        f"HP: {gs.player_hp}/{gs.player_max_hp} | Gold: {gs.gold} | "
        f"Floor: {gs.run.floor if gs.run else '?'} | Act: {gs.act}"
    )
    sections.append("\n".join(run_lines))

    if deck is not None:
        deck_lines = format_deck_section(deck)
        if deck_lines:
            sections.append("\n".join(deck_lines))

    if relics:
        sections.append("### Relics")
        sections.append(", ".join(relics))

    sections.append(_DECISION_OUTPUT)

    sections.append(
        "## How to think about this\n"
        "- Each divination consumes one charge. Big tool reveals more cells "
        "per click but uses one charge. Small tool reveals one cell per click.\n"
        "- Some cells are harmful (curses, HP loss). Once revealed, they apply.\n"
        "- Stop early if revealed rewards are already strong and remaining "
        "unknowns risk net negative value.\n"
        "- Adjacent cells often hide the same kind (good clusters near good, "
        "bad clusters near bad). Use revealed neighbors as evidence.\n"
        "- If the divination payment plan attached a curse, you MUST finish "
        "the budgeted divinations or the run-state is wasted gold."
    )

    return "\n\n".join(sections)
