# ruff: noqa: E501
"""Prompt templates for reward and card selection decisions.

DPS-aware card evaluation with Boss HP targets and card clarifications.
"""

from __future__ import annotations

import config
from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
from src.brain.prompts._card_clarifications import (
    BOSS_HP_TARGETS,
    format_card_notes,
    get_inline_warning,
)
from src.brain.prompts._deck_fmt import format_deck_section, strip_bbcode
from src.brain.prompts._generated_fmt import format_generated_cards_inline
from src.brain.prompts._regent_economy_fmt import (
    annotate_card_note,
    annotate_card_tiers,
    format_regent_economy,
    format_regent_offering_summary,
    regent_star_state,
)
from src.brain.prompts._keyword_fmt import format_keyword_glossary
from src.brain.prompts._potion_slot_fmt import format_potion_slot_decision
from src.brain.prompts._card_name import upgrade_suffix
from src.knowledge.knowledge import GameKnowledge
from src.mcp_client.upstream_models import RawDeckCardPayload, get_damage_block_from_dynamic_values
from src.state.game_state import GameState


def build_card_reward_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
    character: str = "",
    guide_store: object | None = None,
) -> str:
    """Build a prompt for card reward selection.

    Per-card experience notes are injected via the unified memory retriever
    (`## Card-Specific Insights`); no direct card_memory_store read here.

    If ``guide_store`` is provided, a ``## Upcoming Act Boss`` section is
    injected based on ``gs.upcoming_boss_enemy_keys`` + ``character``.
    """
    rw = gs.reward
    if not rw:
        return ""

    # Potion slot decision: slots full + claimable potion reward.
    # May fire even when `pending_card_choice=False` (potion-only reward state).
    potion_candidates: list[tuple[str, str]] = []
    try:
        open_slots = int(getattr(gs, "open_potion_slots", 0) or 0)
    except (TypeError, ValueError):
        open_slots = 1  # treat unknown as "slots available" → skip injection
    if open_slots <= 0:
        potion_items = [
            item for item in (getattr(rw, "rewards", []) or [])
            if getattr(item, "claimable", False)
            and str(getattr(item, "reward_type", "")).lower() == "potion"
        ]
        potion_candidates = [
            (i.description.strip(), "")
            for i in potion_items
            if i.description
        ]

    if not rw.pending_card_choice and not potion_candidates:
        return ""

    deck_size = len(deck) if deck else 0
    act = gs.act

    lines = [
        "## Card Reward",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold}",
    ]

    lines.append(f"Act: {act} | Floor: {gs.floor}")

    lines.extend(format_deck_section(deck, include_descriptions=True))
    lines.extend(format_regent_economy(deck, character))
    # Compute deck-state once for use in tier annotation and offering verdict.
    # When in 'debt' state, consumer tiers are forcibly downgraded to skip.
    _regent_deck_state = regent_star_state(deck, character)

    if relics:
        lines.append("")
        lines.append("## Relics: " + ", ".join(relics))

    if guide_store is not None:
        lines.extend(format_upcoming_boss_guide(gs, character, guide_store))

    if potion_candidates:
        lines.extend(format_potion_slot_decision(gs, potion_candidates))

    if rw.pending_card_choice:
        # Build Glossary + Available Cards into sub-lists; append them at the
        # very end of this builder's output so they sit immediately before the
        # ## Decision Format schema appended by v2_engine. Eval framework /
        # Build Trajectory / Card Notes are emitted to `lines` first, so the
        # tail order becomes:
        #   Eval → Build Trajectory → Card Notes → Glossary → Available Cards
        #   → (## Decision Format from v2_engine)
        glossary_lines: list[str] = []
        options_lines: list[str] = []

        card_texts = [c.rules_text for c in rw.card_options]
        if deck:
            card_texts.extend(d.rules_text or "" for d in deck)
        glossary = format_keyword_glossary(card_texts)
        if glossary:
            glossary_lines.append(glossary)

        options_lines.append("")
        options_lines.append("## Available Cards")

        # Try knowledge DB for card metadata (type, cost, rarity)
        try:
            kb = GameKnowledge.get_instance()
        except Exception:
            kb = None

        for c in rw.card_options:
            upgraded = upgrade_suffix(c)
            display_text = (getattr(c, "resolved_rules_text", "") or c.rules_text or "").strip()
            base_line = f"- [index={c.index}] {c.name}{upgraded}"

            # Prefer enriched fields from upstream-mod payload (e6a90ff partial).
            # Fall back to knowledge DB join for old mods that don't expose them.
            payload_type = getattr(c, "card_type", "") or ""
            payload_rarity = getattr(c, "rarity", "") or ""
            payload_cost = getattr(c, "energy_cost", None)
            payload_costs_x = getattr(c, "costs_x", False)

            if payload_type or payload_rarity or payload_cost is not None:
                cost_str = (
                    "X" if payload_costs_x
                    else (str(payload_cost) if payload_cost is not None else "?")
                )
                ctype = payload_type or "?"
                rarity = payload_rarity or "?"
                base_line += f" ({cost_str}E, {ctype}, {rarity})"
            else:
                # Old-mod fallback: join knowledge DB.
                card_data = kb.cards.get(c.name) if kb else None
                if card_data:
                    cost = card_data.cost or "?"
                    ctype = card_data.type or "?"
                    rarity = card_data.rarity or "?"
                    base_line += f" ({cost}E, {ctype}, {rarity})"

            base_line += f": {display_text}"

            # Append numeric damage/block from dynamic_values
            dvs = getattr(c, "dynamic_values", None) or []
            if dvs:
                d, b, h = get_damage_block_from_dynamic_values(dvs)
                val_parts = []
                if d is not None:
                    val_parts.append(f"{d} dmg")
                if b is not None and b > 0:
                    val_parts.append(f"{b} block")
                if h is not None and h > 1:
                    val_parts.append(f"x{h} hits")
                if val_parts:
                    base_line += f" [{' | '.join(val_parts)}]"

            # Inline warning for commonly misunderstood cards
            if not config.PROMPT_HINT_FILTER:
                inline_warn = get_inline_warning(c.name)
                if inline_warn:
                    base_line += f" {inline_warn}"

            base_line += format_generated_cards_inline(getattr(c, "generated_cards", []) or [])
            base_line += annotate_card_tiers(c.name, character, deck_state=_regent_deck_state)
            base_line += annotate_card_note(c.name, character)
            options_lines.append(base_line)

        # Alternatives: show the exact runtime buttons so the model can choose by index.
        if rw.alternatives:
            for alt in rw.alternatives:
                label = (alt.label or "").strip()
                if label.lower() == "skip":
                    options_lines.append(f"- [ALT index={alt.index}] Skip: Take no card")
                elif label.lower() == "sacrifice":
                    options_lines.append(
                        f"- [ALT index={alt.index}] Sacrifice: Sacrifice this card reward to Pael "
                        "(every 2 sacrifices → gain a Relic. Relics are extremely valuable — "
                        "sacrifice weak offerings aggressively)"
                    )
                else:
                    options_lines.append(f"- [ALT index={alt.index}] {label}")
        else:
            options_lines.append("- No alternative buttons available.")

        # Boss damage check / Build Trajectory — generic character-agnostic
        # guidance. SUPPRESSED for Regent: the boss-DPS framing actively
        # contradicts XecnaR's macro ('skip mediocre commons; basic deck is
        # strong enough') and the Build Trajectory's archetype framing was
        # part of the wrong 'pick Forge or Star' model the new guide
        # explicitly rejects. Regent gets its guidance from the deck-economy
        # block + per-card tier annotations + offering verdict + seed skills.
        is_regent = (character or "").strip().lower() == "the regent"

        # Boss damage check (non-Regent only)
        if config.PROMPT_VARIANT != "baseline" and not is_regent:
            boss_hp = BOSS_HP_TARGETS.get(act, BOSS_HP_TARGETS[2])
            target_dps = boss_hp // 10

            lines.append("")
            lines.append("## Evaluation — Boss Damage Check")
            lines.append("Before picking, estimate your deck's damage output:")
            lines.append("1. Sum each Attack card's base damage in your deck → total attack damage per cycle")
            lines.append("2. Deck cycle length = deck_size ÷ 5 turns")
            lines.append("3. Poison sources: each \"Apply N Poison\" card deals ~N×(N+1)/2 total damage per play")
            lines.append("4. Your damage per turn ≈ (total attack damage per cycle) ÷ cycle_turns + poison contribution")
            lines.append("")
            lines.append(f"Boss HP target: ~{boss_hp} in ~10 turns → need ~{target_dps} damage/turn while also blocking.")
            lines.append("")
            lines.append("Decision rules:")
            lines.append("- If your estimated DPS is well below target → PRIORITIZE damage/poison cards over defense/draw/utility")
            lines.append("- If DPS is sufficient → take defense/draw/utility, or SKIP to keep deck lean")
            lines.append("- Power cards that deal passive damage need enablers (draw cards, attack cards) — factor in whether you have them")
            lines.append("- 3 energy/turn limits you to ~2-3 card plays: a 2-cost card must be worth two 1-cost cards")
            lines.append("")
            lines.append("Consider your deck's 4 dimensions (Damage/Defense/Draw/Energy) but weight Damage highest when below target.")
            lines.append("Review your Build Plan in the Strategic Thread. Does any card fill a gap?")
            lines.append(f"Adding a card increases deck cycle ({deck_size} → {deck_size + 1} cards).")
            lines.append("SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one.")

        # Build trajectory check (non-Regent only — see comment above)
        if config.PROMPT_VARIANT != "baseline" and not is_regent:
            lines.append("")
            lines.append("## Build Trajectory Check")
            lines.append("Before choosing based on current DPS alone, also consider:")
            lines.append("1. **Archetype commitment**: What archetype is your deck building toward? (Check your Strategic Thread / build plan)")
            lines.append("2. **Rarity matters**: Rare cards may never appear again this run — weigh rarity heavily over small immediate DPS gains")
            lines.append("3. **Scaling > flat**: Cards that SCALE with future picks (e.g., Knife Trap improves with every Shiv generator added later) beat cards with flat immediate value (e.g., Dagger Throw's fixed 9 damage never grows)")
            lines.append("4. **Common cards recur**: Common cards will be offered again — don't take a Common over a Rare that fits your build direction")
            lines.append("5. **Draft for trajectory**: If the guide recommends an archetype and you've started building it (e.g., you have Blade Dance → Shiv archetype), draft key build-around cards for that trajectory even if current DPS seems low")

        # Card clarification notes (e.g. Speedster mechanic)
        if not config.PROMPT_HINT_FILTER:
            offered_names = [c.name for c in rw.card_options]
            deck_names = [d.name for d in deck] if deck else []
            notes = format_card_notes(offered_names, deck_names)
            if notes:
                lines.append(notes)

        # Regent-only: offering verdict — explicit Skip recommendation when
        # all offerings are C-tier-or-worse, so the LLM doesn't pick a bad
        # card just because its raw stats look ok. Also overrides S/A
        # consumer recommendations when the deck is in star debt.
        offered_names = [c.name for c in rw.card_options]
        verdict_lines = format_regent_offering_summary(
            offered_names, character, deck_state=_regent_deck_state,
        )

        # Append Glossary + Available Cards + Verdict as the FINAL block of
        # this builder — they sit immediately before the ## Decision Format
        # that v2_engine appends. Options + verdict must be the freshest
        # content the model reads.
        lines.extend(glossary_lines)
        lines.extend(options_lines)
        lines.extend(verdict_lines)

    return "\n".join(lines)


def build_relic_select_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
) -> str:
    """Build a prompt for relic selection (boss relic, etc)."""
    rs = getattr(gs, "relic_select", None)
    if not rs:
        return ""

    lines = [
        "## Relic Selection",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold}",
    ]

    lines.append(f"Act: {gs.act} | Floor: {gs.floor}")

    if rs.prompt:
        lines.append(f"Prompt: {rs.prompt}")

    lines.extend(format_deck_section(deck))
    lines.extend(format_regent_economy(deck, getattr(gs, "character", "") or ""))

    if relics:
        lines.append("Current Relics: " + ", ".join(relics))

    lines.append("")
    lines.append("## Available Relics")
    for r in rs.relic_options if hasattr(rs, "relic_options") else getattr(rs, "relics", []):
        desc = getattr(r, "description", "") or r.rarity
        lines.append(f"- [index={r.index}] {r.name}: {strip_bbcode(desc)}")

    lines.append("- [SKIP] Take no relic")

    lines.append("")
    lines.append("Almost always take a relic. Energy/draw relics are S-tier. Skip only if downside destroys your strategy.")

    return "\n".join(lines)
