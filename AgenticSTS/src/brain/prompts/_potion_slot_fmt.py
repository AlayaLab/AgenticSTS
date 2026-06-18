"""Format the Potion Slot Decision subsection for reward/shop prompts.

Injected only when potion slots are full AND new potions are available — gives the
LLM an explicit discard-then-take option instead of silently losing the new potion.
"""

from __future__ import annotations

from src.brain.prompts._deck_fmt import strip_bbcode
from src.knowledge.potion_classifier import classify_potion


def _timing_tag(name: str, desc: str) -> str:
    profile = classify_potion(name or "", desc or "")
    return "[SUSTAINED]" if profile.timing == "sustained" else "[INSTANT]"


def format_potion_slot_decision(
    gs,
    candidate_potions: list[tuple[str, str]],
) -> list[str]:
    """Return subsection lines for the full-slot + new-potion scenario.

    Args:
        gs: GameState-like object with `potions`, `open_potion_slots`.
        candidate_potions: list of (name, description) for new potions available
            to claim/buy. Caller must pre-filter (e.g., affordable in shop).

    Returns:
        [] when slots are not full, or when candidate_potions is empty.
        Otherwise a list of prompt lines ready for `lines.extend(...)`.
    """
    if getattr(gs, "open_potion_slots", 0) > 0:
        return []
    if not candidate_potions:
        return []

    held = [p for p in (getattr(gs, "potions", []) or []) if getattr(p, "occupied", False)]
    held_indices = [p.index for p in held]

    lines: list[str] = ["", "## Potion Slot Decision (slots FULL)", "Currently held:"]
    for pot in held:
        name = (pot.name or "").strip()
        desc = strip_bbcode(pot.description or "").strip() if pot.description else ""
        tag = _timing_tag(name, desc)
        lines.append(f"  [{pot.index}] {name} {tag} — {desc}")

    if len(candidate_potions) == 1:
        cname, cdesc = candidate_potions[0]
        cdesc_clean = strip_bbcode(cdesc or "").strip() if cdesc else ""
        lines.append(
            f"Candidate: {cname} {_timing_tag(cname, cdesc_clean)} — {cdesc_clean}"
        )
    else:
        lines.append("Candidates:")
        for cname, cdesc in candidate_potions:
            cdesc_clean = strip_bbcode(cdesc or "").strip() if cdesc else ""
            lines.append(
                f"  - {cname} {_timing_tag(cname, cdesc_clean)} — {cdesc_clean}"
            )

    idx_list = "/".join(str(i) for i in held_indices)
    lines.append("")
    lines.append(
        "Prefer keep unless the candidate is clearly stronger than your "
        "weakest held potion."
    )
    lines.append(
        f"To take the candidate, discard one of [{idx_list}] first; otherwise skip."
    )
    # Scope-specific schema hint: reward emits a single card_reward_action
    # call with action=discard_potion; shop emits TWO purchases entries in
    # order (discard_potion, buy_potion) — schema documented in shop prompt.
    state_type = (getattr(gs, "state_type", "") or "").lower()
    if state_type == "shop":
        lines.append(
            'Shop swap schema: emit purchases=[{"action":"discard_potion",'
            '"item_name":"<held potion name>","price":0,...}, '
            '{"action":"buy_potion","item_name":"<candidate name>",'
            '"price":<price>,...}] in that order.'
        )
    return lines
