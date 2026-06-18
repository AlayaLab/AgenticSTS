"""Event memory extractor: converts ShortTermMemory event data into EventMemory.

Pure data conversion — no LLM calls. Downstream event-guide consolidation
scores decisions using the ``run_victory`` / ``run_final_floor`` outcome
anchor stamped onto every memory here.
"""

from __future__ import annotations

import logging

from src.memory.models_v2 import normalize_character
from src.memory.event_models import (
    EventMemory,
    EventOptionSnapshot,
)
from src.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)


def extract_event_memories(
    short_term: ShortTermMemory,
    run_id: str,
    character: str,
    run_victory: bool = False,
    run_final_floor: int = 0,
) -> list[EventMemory]:
    """Extract EventMemory instances from completed events in short-term memory.

    Returns frozen EventMemory objects ready for long-term storage.

    Args:
        run_victory: Outcome flag of the run the events belong to. Stamped on
            every extracted memory so guide consolidation can score each
            decision against the eventual outcome without a separate LLM pass.
        run_final_floor: Floor the run ended on (0 when unknown).
    """
    memories: list[EventMemory] = []

    for tracker in short_term.completed_events:
        memory = EventMemory(
            run_id=run_id,
            floor=tracker.floor,
            act=tracker.act,
            event_id=tracker.event_id,
            event_title=tracker.event_title,
            character=normalize_character(character),
            chosen_option_index=tracker.chosen_option_index,
            chosen_option_text=tracker.chosen_option_text,
            all_options=tuple(tracker.all_options),
            hp_before=tracker.hp_before,
            hp_after=tracker.hp_after,
            gold_before=tracker.gold_before,
            gold_after=tracker.gold_after,
            cards_gained=tuple(tracker.cards_gained),
            cards_lost=tuple(tracker.cards_lost),
            relics_gained=tuple(tracker.relics_gained),
            potions_gained=tuple(tracker.potions_gained),
            all_option_details=tuple(
                EventOptionSnapshot.from_dict(od)
                for od in tracker.all_option_details
            ),
            run_victory=run_victory,
            run_final_floor=run_final_floor,
        )
        memories.append(memory)

    logger.info(
        "Extracted %d event memories from run %s",
        len(memories), run_id[:8] if run_id else "?",
    )
    return memories
