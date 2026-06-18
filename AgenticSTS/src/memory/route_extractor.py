"""Route memory extractor: converts ShortTermMemory route data into RouteMemories.

Builds one RouteMemory per act from the accumulated route node traversals.
"""

from __future__ import annotations

import logging

from src.memory.models_v2 import RouteMemory, RouteNode, normalize_character
from src.memory.short_term import RouteNodeTracker, ShortTermMemory

logger = logging.getLogger(__name__)


def _build_node_summary(n: RouteNodeTracker) -> str:
    """Build a compact summary string for a route node."""
    hp_delta = n.hp_after - n.hp_before
    gold_delta = n.gold_after - n.gold_before

    parts = [n.node_type]
    if hp_delta != 0:
        parts.append(f"HP{hp_delta:+d}")
    if gold_delta != 0:
        parts.append(f"Gold{gold_delta:+d}")
    if n.cards_gained:
        parts.append(f"+{','.join(n.cards_gained)}")
    if n.relics_gained:
        parts.append(f"relic:{','.join(n.relics_gained)}")
    return " | ".join(parts)


def _tracker_node_to_frozen(n: RouteNodeTracker) -> RouteNode:
    """Convert a mutable RouteNodeTracker to a frozen RouteNode."""
    return RouteNode(
        floor=n.floor,
        node_type=n.node_type,
        hp_before=n.hp_before,
        hp_after=n.hp_after,
        gold_before=n.gold_before,
        gold_after=n.gold_after,
        cards_gained=tuple(n.cards_gained),
        cards_removed=tuple(n.cards_removed),
        relics_gained=tuple(n.relics_gained),
        potions_gained=tuple(n.potions_gained),
        completion_reason=n.completion_reason,
        summary=_build_node_summary(n),
    )


def extract_route_memories(
    short_term: ShortTermMemory,
    run_id: str,
    character: str,
    victory: bool,
    fitness: float,
) -> list[RouteMemory]:
    """Extract RouteMemories from short-term memory, one per act.

    Returns a list of frozen RouteMemory objects ready for long-term storage.
    """
    memories: list[RouteMemory] = []

    for act, node_trackers in sorted(short_term.route_nodes_by_act.items()):
        if not node_trackers:
            continue

        nodes = tuple(_tracker_node_to_frozen(n) for n in node_trackers)

        hp_start = node_trackers[0].hp_before
        hp_end = node_trackers[-1].hp_after
        gold_start = node_trackers[0].gold_before
        gold_end = node_trackers[-1].gold_after

        # Detect boss result from the last node
        last_node = node_trackers[-1]
        if last_node.node_type == "boss":
            if last_node.completion_reason == "aborted":
                boss_result = "aborted"
            else:
                boss_result = "won" if last_node.hp_after > 0 else "lost"
        else:
            boss_result = "not_reached"

        memory = RouteMemory(
            run_id=run_id,
            act=act,
            character=normalize_character(character),
            nodes=nodes,
            hp_start=hp_start,
            hp_end=hp_end,
            gold_start=gold_start,
            gold_end=gold_end,
            boss_result=boss_result,
            victory_run=victory,
            fitness=fitness,
        )
        memories.append(memory)

    logger.info(
        "Extracted %d route memories from run %s (acts: %s)",
        len(memories), run_id[:8] if run_id else "?",
        [m.act for m in memories],
    )
    return memories
