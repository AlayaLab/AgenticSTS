"""Card memory extractor: post-run per-card statistics extraction.

Extracts deterministic per-card evidence from ShortTermMemory and merges
it into the CardMemoryStore. No LLM calls — purely additive stat merging.
"""

from __future__ import annotations

import logging
from collections import Counter

from src.memory.card_memory_store import CardMemoryStore
from src.memory.models_v2 import CardMemory, normalize_character
from src.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)


def _strip_upgrade(name: str) -> str:
    """Remove trailing '+' from card names for canonical lookup."""
    return name.rstrip("+").strip()


def extract_per_card_stats(
    short_term: ShortTermMemory,
    character: str,
    final_deck: list[str],
    victory: bool,
) -> dict[str, dict]:
    """Extract per-card deterministic stats from a completed run.

    Returns a dict keyed by canonical card name (lowercase, no '+'),
    with stat dicts containing play_count, draw_count, unplayed_draw_count,
    total_damage, total_block, total_energy_gain, debuffs_applied,
    powers_applied, picked, bought.
    """
    stats: dict[str, dict] = {}

    def _ensure(card_name: str) -> dict:
        key = _strip_upgrade(card_name).lower()
        if key not in stats:
            stats[key] = {
                "play_count": 0,
                "sly_play_count": 0,
                "draw_count": 0,
                "unplayed_draw_count": 0,
                "total_damage": 0,
                "total_block": 0,
                "total_energy_gain": 0,
                "debuffs_applied": 0,
                "powers_applied": 0,
                "picked": False,
                "bought": False,
            }
        return stats[key]

    # 1. Play counts from global tracker
    for card_name, count in short_term.card_play_counts.items():
        s = _ensure(card_name)
        s["play_count"] += count

    # 1b. Sly play counts (subset of play_count triggered via Sly discard)
    for card_name, count in short_term.sly_play_counts.items():
        s = _ensure(card_name)
        s["sly_play_count"] += count

    # 2. Per-action combat deltas (traceable damage/block/energy)
    for tracker in short_term.completed_combats:
        if getattr(tracker, "terminal_reason", "") == "abort":
            continue
        for rnd in tracker.rounds:
            # Hand tracking: cards drawn and unplayed
            if rnd.hand_at_start:
                played_set = Counter(rnd.cards_played)
                hand_counter = Counter(rnd.hand_at_start)
                for card_name, count in hand_counter.items():
                    s = _ensure(card_name)
                    s["draw_count"] += count
                    played_of_this = played_set.get(card_name, 0)
                    unplayed = max(0, count - played_of_this)
                    s["unplayed_draw_count"] += unplayed

            # Per-action deltas
            for delta in rnd.events:
                if delta.event_type != "card_play" or not delta.source:
                    continue
                card_name = delta.source
                s = _ensure(card_name)

                # Damage
                for ed in delta.enemy_deltas:
                    if ed.hp is not None and ed.hp < 0:
                        s["total_damage"] += abs(ed.hp)
                    if ed.powers_changed:
                        s["debuffs_applied"] += len(ed.powers_changed)

                # Block
                if delta.block is not None and delta.block > 0:
                    s["total_block"] += delta.block

                # Energy
                if delta.energy is not None and delta.energy > 0:
                    s["total_energy_gain"] += delta.energy

                # Player powers
                if delta.powers_changed:
                    s["powers_applied"] += len(delta.powers_changed)

    # 3. Deck events: pick/buy tracking
    for event in short_term.deck_events:
        if event.event_type == "add":
            s = _ensure(event.card_name)
            if event.source in ("combat_reward", "boss_reward"):
                s["picked"] = True
            elif event.source == "shop":
                s["bought"] = True

    return stats


def update_card_memories_from_run(
    card_memory_store: CardMemoryStore,
    short_term: ShortTermMemory,
    character: str,
    final_deck: list[str],
    victory: bool,
    final_act: int = 0,
    incomplete: bool = False,
) -> int:
    """Extract per-card stats and merge into card memory store.

    Args:
        victory: True if run was a win.
        final_act: 1/2/3 — the act where the agent died.
        incomplete: True if run was aborted (max_steps, etc.).

    Returns the number of card memories updated.
    """
    char = normalize_character(character)
    per_card = extract_per_card_stats(short_term, char, final_deck, victory)

    updated = 0
    for card_name_lower, run_stats in per_card.items():
        # Only update cards that were actually in the final deck or played
        if run_stats["play_count"] == 0 and card_name_lower not in {
            _strip_upgrade(c).lower() for c in final_deck
        }:
            continue

        existing = card_memory_store.get(char, card_name_lower)
        if existing is None:
            existing = CardMemory(
                character=char,
                card_name=card_name_lower,
            )

        merged = existing.merge_run_stats(
            play_count=run_stats["play_count"],
            sly_play_count=run_stats["sly_play_count"],
            draw_count=run_stats["draw_count"],
            unplayed_draw_count=run_stats["unplayed_draw_count"],
            total_damage=run_stats["total_damage"],
            total_block=run_stats["total_block"],
            total_energy_gain=run_stats["total_energy_gain"],
            debuffs_applied=run_stats["debuffs_applied"],
            powers_applied=run_stats["powers_applied"],
            victory=victory,
            final_act=final_act,
            incomplete=incomplete,
            picked=run_stats["picked"],
            bought=run_stats["bought"],
        )
        card_memory_store.put(merged)
        updated += 1

    logger.info(
        "Card memory update: %d cards updated for %s (%s)",
        updated, char, "victory" if victory else "defeat",
    )
    return updated
