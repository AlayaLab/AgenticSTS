"""Shared pile formatting for combat prompts (draw / discard / exhaust).

Extracts card names from ``AgentViewCardStackItem.line`` and formats
piles as compact single-line summaries for token-efficient prompt injection.

Typical .line formats from the upstream C# mod (Chinese-localized cost
annotation; we translate to English before injecting into prompts):
  - "Defend [1费]：Gain 5 Block."         → "Defend [1 cost]: Gain 5 Block."
  - "Defend*3 [1费]：Gain 5 Block."       (copy marker *N in pile views)
  - "Strike+ [1费]：Deal 9 damage."        (upgraded card)
  - "Neutralize [0费]：Deal 3 damage. Apply 1 Weak."
"""

from __future__ import annotations

import re
from collections import Counter

from src.mcp_client.upstream_models import AgentViewCardStackItem

_COST_BRACKET_RE = re.compile(r"\[(\d+|X)费")


def _normalize_card_line(line: str) -> str:
    """Translate the upstream Chinese cost annotation + full-width colon.

    Upstream emits ``"[1费]：Deal 6 damage."`` with the Chinese ``费``
    character and the full-width colon ``：``. Inject English equivalents so
    LLM prompts stay monolingual.
    """
    if not line:
        return line
    line = _COST_BRACKET_RE.sub(r"[\1 cost", line)
    return line.replace("：", ": ")


def extract_card_name(line: str) -> str:
    """Extract just the card name from an AgentViewCardStackItem.line string.

    Strips the copy marker (*N), cost bracket ([N费]), and description.

    Examples:
        >>> extract_card_name("Defend*3 [1费]：Gain 5 Block.")
        'Defend'
        >>> extract_card_name("Strike+ [1费]：Deal 9 damage.")
        'Strike+'
        >>> extract_card_name("Neutralize [0费]：Deal 3 damage.")
        'Neutralize'
        >>> extract_card_name("Ice Lance [1费|★1]：Channel 3 Frost.")
        'Ice Lance'
        >>> extract_card_name("")
        ''
    """
    if not line:
        return ""

    # Take everything before the first " [" (cost bracket)
    bracket_idx = line.find(" [")
    name_part = line[:bracket_idx] if bracket_idx != -1 else line

    # Strip copy marker (*N) at the end of the name, e.g. "Defend*3" -> "Defend"
    name_part = re.sub(r"\*\d+$", "", name_part)

    return name_part.strip()


def format_pile_compact(
    items: list[AgentViewCardStackItem],
    pile_name: str,
) -> str:
    """Format a pile as a compact single-line summary.

    Groups cards by name with counts for brevity.

    Args:
        items: list of AgentViewCardStackItem from agent_view.combat
        pile_name: display name like "Draw", "Discard", "Exhaust"

    Returns:
        Single line like "Draw (7): Strike x3, Defend x2, Bash, Footwork"
        or empty string if the pile is empty.
    """
    if not items:
        return ""

    names: list[str] = []
    for item in items:
        name = extract_card_name(item.line)
        if name:
            names.append(name)

    if not names:
        return ""

    # Count occurrences, preserving first-seen order
    counts = Counter(names)
    seen: set[str] = set()
    parts: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        count = counts[name]
        if count > 1:
            parts.append(f"{name} x{count}")
        else:
            parts.append(name)

    return f"{pile_name} ({len(items)}): {', '.join(parts)}"


def format_pile_detailed(
    items: list[AgentViewCardStackItem],
    pile_name: str,
) -> list[str]:
    """Format a pile as multi-line with full cost + description + enchantments.

    Dedup key is ``(card_name, tuple(mods))`` so differently-enchanted copies of
    the same card are listed separately. Preserves first-seen order; suffixes
    ``xN`` when the same (name, mods) combination repeats.

    Enchantments / card modifiers from ``item.mods`` are rendered inline as
    ``[Mods: A, B]`` when non-empty.

    Returns a list of lines (no ``## Piles`` header — caller owns that):
        ["Draw (4):",
         "  - Strike [1 cost]: Deal 6 damage.",
         "  - Strike [1 cost]: Deal 6 damage. [Mods: Keen Edge] x2",
         "  - Defend [1 cost]: Gain 5 Block."]
        or [] if the pile is empty.
    """
    if not items:
        return []

    first_line: dict[tuple[str, tuple[str, ...]], str] = {}
    first_mods: dict[tuple[str, tuple[str, ...]], tuple[str, ...]] = {}
    counts: Counter[tuple[str, tuple[str, ...]]] = Counter()
    order: list[tuple[str, tuple[str, ...]]] = []
    for item in items:
        name = extract_card_name(item.line)
        if not name:
            continue
        mods = tuple(item.mods or ())
        key = (name, mods)
        if key not in first_line:
            first_line[key] = _normalize_card_line(item.line)
            first_mods[key] = mods
            order.append(key)
        counts[key] += 1

    if not order:
        return []

    lines = [f"{pile_name} ({len(items)}):"]
    for key in order:
        # Strip any "*N" copy marker from the displayed line; we use our own xN.
        display = re.sub(r"\*\d+(?=\s*\[)", "", first_line[key], count=1)
        mods_part = (
            f" [Mods: {', '.join(first_mods[key])}]" if first_mods[key] else ""
        )
        count = counts[key]
        count_part = f" x{count}" if count > 1 else ""
        lines.append(f"  - {display}{mods_part}{count_part}")

    return lines


def format_piles_section(
    draw: list[AgentViewCardStackItem],
    discard: list[AgentViewCardStackItem],
    exhaust: list[AgentViewCardStackItem],
) -> list[str]:
    """Format all three combat piles as prompt lines.

    Returns a list of lines (including the "## Piles" header) if any pile
    is non-empty, or an empty list if all piles are empty.
    """
    pile_lines: list[str] = []
    for items, name in [
        (draw, "Draw"),
        (discard, "Discard"),
        (exhaust, "Exhaust"),
    ]:
        line = format_pile_compact(items, name)
        if line:
            pile_lines.append(line)

    if not pile_lines:
        return []

    return ["", "## Piles"] + pile_lines
