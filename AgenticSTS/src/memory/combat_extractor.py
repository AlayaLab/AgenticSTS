"""Combat episode extractor: converts ShortTermMemory combat data into CombatEpisodes.

Extracts rich per-combat episodes with round-by-round timelines from the
short-term memory accumulated during gameplay.
"""

from __future__ import annotations

import logging

from src.memory.enemy_keys import normalize_enemy_key
from src.memory.models_v2 import CombatEpisode, CombatRound, normalize_character
from src.memory.short_term import CombatTracker, ShortTermMemory

logger = logging.getLogger(__name__)


def _build_enemy_key(tracker: CombatTracker) -> str:
    """Build a canonical enemy key for memory indexing."""
    if not tracker.enemy_names:
        return normalize_enemy_key(tracker.enemy_key or "unknown")
    if len(tracker.enemy_names) == 1:
        return normalize_enemy_key(tracker.enemy_names[0])
    return normalize_enemy_key("multi:" + "+".join(sorted(tracker.enemy_names)))


def _tracker_round_to_frozen(r) -> CombatRound:
    """Convert a mutable CombatRoundTracker to a frozen CombatRound."""
    return CombatRound(
        round_num=r.round_num,
        energy_available=r.energy_available,
        energy_used=r.energy_used,
        hp_start=r.hp_start,
        hp_end=r.hp_end,
        block_gained=r.block_gained,
        enemy_intents=tuple(r.enemy_intents),
        cards_played=tuple(r.cards_played),
        potions_used=tuple(r.potions_used),
        damage_dealt=r.damage_dealt,
        damage_taken=r.damage_taken,
        events=tuple(r.events),
        hand_at_start=tuple(r.hand_at_start),
        situation_tag=r.situation_tag,
        enemy_states=tuple(r.enemy_states),
        player_powers_snapshot=tuple(r.player_powers_snapshot),
        enemy_powers_snapshot=tuple(
            tuple(ep) for ep in r.enemy_powers_snapshot
        ) if r.enemy_powers_snapshot else (),
        enemy_hp_snapshot=tuple(
            tuple(eh) for eh in r.enemy_hp_snapshot
        ) if r.enemy_hp_snapshot else (),
        block_before=r.block_before,
        draw_pile_size=r.draw_pile_size,
        discard_pile_size=r.discard_pile_size,
        exhaust_pile_size=r.exhaust_pile_size,
        usable_potions=tuple(r.usable_potions),
        incoming_damage=r.incoming_damage,
        agent_plan=tuple(r.agent_plan),
        llm_call_seq=r.llm_call_seq,
    )


def extract_combat_episodes(
    short_term: ShortTermMemory,
    run_id: str,
    character: str,
) -> list[CombatEpisode]:
    """Extract CombatEpisodes from completed combats in short-term memory.

    Returns a list of frozen CombatEpisode objects ready for long-term storage.
    """
    episodes: list[CombatEpisode] = []

    for tracker in short_term.completed_combats:
        rounds = tuple(_tracker_round_to_frozen(r) for r in tracker.rounds)

        hp_before = tracker.hp_before
        hp_after = getattr(tracker, "hp_after", getattr(tracker, "_hp_after", hp_before))
        won = getattr(tracker, "won", getattr(tracker, "_won", True))
        terminal_reason = getattr(
            tracker,
            "terminal_reason",
            getattr(tracker, "_terminal_reason", "win" if won else "loss"),
        )

        total_dmg_dealt = sum(r.damage_dealt for r in rounds)
        total_dmg_taken = sum(r.damage_taken for r in rounds)
        total_cards = sum(len(r.cards_played) for r in rounds)

        episode = CombatEpisode(
            run_id=run_id,
            floor=tracker.floor,
            act=tracker.act,
            enemy_key=_build_enemy_key(tracker),
            character=normalize_character(character),
            combat_type=tracker.combat_type,
            rounds=rounds,
            hp_before=hp_before,
            hp_after=hp_after,
            won=won,
            terminal_reason=terminal_reason,
            hp_delta=hp_after - hp_before,
            total_damage_dealt=total_dmg_dealt,
            total_damage_taken=total_dmg_taken,
            total_cards_played=total_cards,
            deck_size=tracker.deck_size,
            relics=tuple(tracker.relics),
            context=tracker.combat_context,
            retrieved_skill_ids=tuple(getattr(tracker, "retrieved_skill_ids", [])),
        )
        episodes.append(episode)

    logger.info(
        "Extracted %d combat episodes from run %s",
        len(episodes), run_id[:8] if run_id else "?",
    )
    return episodes
