"""Prompt injector: selectively inserts memory hints into LLM prompts.

V2 (HCM): decision-type-aware injection with domain-specific headers:
- Combat: "## Enemy Intel" + "## Past Encounters" + "## Current Combat"
- Route:  "## Route Intelligence"
- Deck:   "## Deck Building Insights"
- Rest/Event: "## Strategy Hints"
"""

from __future__ import annotations

from src.memory.hint_sanitizer import sanitize_deck_guide_hints
from src.memory.models_v2 import WorkingContext


def format_working_context(wc: WorkingContext) -> str:
    """Format a WorkingContext into a prompt-ready string (V2 HCM).

    Uses decision-type-aware section headers for better prompt structure.
    At R2+, demotes the combat guide header to a background-reference note
    (so Past Experience stays visually primary), but the guide text itself
    is no longer truncated — mid-sentence ``...`` cuts were dropping the
    actionable half of the hint. Budget enforcement happens upstream in
    ``_trim_working_context``; this formatter is presentation only.
    Adds a SURVIVAL PRIORITY banner for high/lethal threat.
    Returns empty string if no hints are available.
    """
    if wc.is_empty:
        return ""

    parts: list[str] = []
    is_r2_plus = wc.current_round >= 2
    is_high_threat = wc.current_threat_level in ("high", "lethal")

    # Past-experience mechanics (highest priority at R2+)
    if wc.situation_hints:
        parts.append("## Past Experience")
        parts.append("*Enemy mechanics and fight structure from past encounters.*\n")
        if is_high_threat:
            parts.append(f"**SURVIVAL PRIORITY**: {wc.current_threat_level} threat.\n")
        for hint in wc.situation_hints:
            parts.append(hint)
        parts.append("")

    # Combat domain — demote header at R2+ but keep full guide text.
    if wc.combat_guide_hints or wc.enemy_pattern_hints:
        parts.append("## Combat Guide")
        if is_r2_plus:
            parts.append("*Background reference — past experience above takes priority.*\n")
        else:
            parts.append("*Tactical advice from past encounters.*\n")
        if wc.combat_guide_hints:
            for hint in wc.combat_guide_hints:
                parts.append(f"- {hint}")
        if wc.enemy_pattern_hints:
            for hint in wc.enemy_pattern_hints:
                parts.append(hint)
        parts.append("")

    # Route domain (unchanged)
    if wc.route_guide_hints or wc.route_memory_hints:
        parts.append("## Route Intelligence")
        parts.append("*Consider these route patterns.*\n")
        if wc.route_guide_hints:
            for hint in wc.route_guide_hints:
                parts.append(f"- {hint}")
        if wc.route_memory_hints:
            parts.append("\n**Past Routes:**")
            for hint in wc.route_memory_hints:
                parts.append(f"- {hint}")
        parts.append("")

    # Deck domain (unchanged)
    deck_guide_hints = sanitize_deck_guide_hints(wc.deck_guide_hints)
    if deck_guide_hints or wc.deck_memory_hints:
        parts.append("## Deck Building Insights")
        parts.append("*Adapt to your current deck and situation.*\n")
        if deck_guide_hints:
            for hint in deck_guide_hints:
                parts.append(f"- {hint}")
        if wc.deck_memory_hints:
            parts.append("\n**Past Builds:**")
            for hint in wc.deck_memory_hints:
                parts.append(f"- {hint}")
        parts.append("")

    # Per-card insights (unchanged)
    if wc.card_memory_hints:
        parts.append("## Card-Specific Insights")
        parts.append("*Per-card experience — consider alongside your build plan.*\n")
        for hint in wc.card_memory_hints:
            parts.append(f"- {hint}")
        parts.append("")

    # Event memory (past event decisions and boss impact)
    if wc.event_memory_hints:
        parts.append("## Past Event Experience")
        parts.append("*Outcomes from previous encounters with this event.*\n")
        for hint in wc.event_memory_hints:
            parts.append(f"- {hint}")
        parts.append("")

    # Short-term context (unchanged)
    if wc.short_term_hints:
        parts.append("## Strategic Thread")
        parts.append("*Your deck-building rationale — maintain coherence across decisions.*\n")
        for hint in wc.short_term_hints:
            parts.append(hint)
        parts.append("")

    return "\n".join(parts)


def inject_working_context_into_prompt(prompt: str, wc: WorkingContext) -> str:
    """Insert HCM working context into an existing prompt (V2).

    Inserts before the ## Your Task section if present,
    otherwise appends before the last section.
    """
    if wc.is_empty:
        return prompt

    hints = format_working_context(wc)
    if not hints:
        return prompt

    return _insert_before_task(prompt, hints)


def _insert_before_task(prompt: str, hints: str) -> str:
    """Insert hints text before ## Your Task or last ## section."""
    marker = "## Your Task"
    if marker in prompt:
        idx = prompt.index(marker)
        return prompt[:idx] + hints + prompt[idx:]

    last_section = prompt.rfind("\n## ")
    if last_section > 0:
        return prompt[:last_section + 1] + hints + prompt[last_section + 1:]

    return hints + prompt
