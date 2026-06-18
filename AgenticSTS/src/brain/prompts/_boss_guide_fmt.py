"""Format upcoming-act-boss CombatGuide into card_reward / shop prompts."""

from __future__ import annotations

from typing import Protocol

import config
from src.memory.models_v2 import CombatGuide


class _GuideStoreLike(Protocol):
    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None: ...


_FOOTER = (
    "Consider matchup when picking, but don't over-optimize deckbuild for one fight."
)


def _format_guide_body(guide: CombatGuide) -> list[str]:
    """Render the body lines of a single guide (no header)."""
    body: list[str] = []
    if guide.trigger_model:
        body.append(f"Trigger model: {guide.trigger_model}")
    if guide.mechanic_summary:
        body.append("Mechanics:")
        body.extend(f"- {line}" for line in guide.mechanic_summary[:3])
    if guide.round_triggers:
        body.append("Round triggers:")
        body.extend(f"- {line}" for line in guide.round_triggers[:2])
    if guide.threshold_triggers:
        body.append("Threshold / death triggers:")
        body.extend(f"- {line}" for line in guide.threshold_triggers[:2])
    if guide.danger_windows:
        body.append("Danger windows:")
        body.extend(f"- {line}" for line in guide.danger_windows[:2])
    text = (guide.guide_text or "").strip()
    if text:
        body.append(text)
    patterns = [p for p in guide.key_patterns if p]
    if patterns:
        body.append("Legacy key patterns:")
        body.extend(f"- {p}" for p in patterns)
    return body


def format_upcoming_boss_guide(
    gs,
    character: str,
    guide_store: _GuideStoreLike,
) -> list[str]:
    """Return prompt lines injecting CombatGuide(s) for the upcoming act boss(es).

    Returns [] when:
    - gs has no upcoming boss keys (mod missing fields, unknown encounter, etc.)
    - character is empty
    - guide_store has no match for any resolved key
    """
    if config.KNOWLEDGE_STRICT:
        return []
    if not character:
        return []
    keys: list[str] = list(getattr(gs, "upcoming_boss_enemy_keys", []) or [])
    if not keys:
        return []

    # Collect (key, guide) pairs where guide exists
    hits: list[tuple[str, CombatGuide]] = []
    for key in keys:
        guide = guide_store.get_combat_guide(key, character)
        if guide is not None:
            hits.append((key, guide))

    if not hits:
        return []

    lines: list[str] = [""]
    if len(hits) == 1:
        key, guide = hits[0]
        lines.append(f"## Upcoming Act Boss: {key}")
        lines.extend(_format_guide_body(guide))
        lines.append("")
        lines.append(_FOOTER)
    else:
        lines.append("## Upcoming Act Bosses (sequential):")
        for key, guide in hits:
            lines.append("")
            lines.append(f"### {key}")
            lines.extend(_format_guide_body(guide))
        lines.append("")
        lines.append(_FOOTER)
    return lines
