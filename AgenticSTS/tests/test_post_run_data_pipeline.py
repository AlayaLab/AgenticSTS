from __future__ import annotations

import json
import tempfile

from src.memory.card_build_extractor import extract_card_build_memory
from src.memory.card_build_store import CardBuildStore
from src.memory.combat_extractor import extract_combat_episodes
from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CardBuildMemory, CombatEpisode, RouteMemory, WorkingContext
from src.memory.retriever import _trim_working_context
from src.memory.route_store import RouteMemoryStore
from src.memory.short_term import ShortTermMemory


def _build_sample_stm() -> ShortTermMemory:
    stm = ShortTermMemory()
    stm.capture_starting_deck(["Strike", "Defend", "Neutralize"])
    stm.start_combat(
        enemy_names=["Jaw Worm"],
        combat_type="monster",
        hp=70,
        deck_size=3,
        relics=[],
        floor=1,
        act=1,
    )
    stm.start_combat_round(round_num=1, energy=3, hp=70, enemy_intents=["Jaw Worm: Attack(11)"])
    stm.record_card_play("Strike", 1)
    stm.record_card_play("Neutralize", 0)
    stm.record_combat_metrics(damage_dealt=9, block_gained=5, hp_after=70)
    return stm


def test_extract_combat_episodes_keeps_damage_and_block_metrics() -> None:
    stm = _build_sample_stm()
    stm.end_combat(won=True, hp_after=70)

    episodes = extract_combat_episodes(stm, run_id="run-1", character="The Silent")

    assert len(episodes) == 1
    episode = episodes[0]
    assert episode.total_damage_dealt == 9
    assert episode.rounds[0].damage_dealt == 9
    assert episode.rounds[0].block_gained == 5


def test_extract_card_build_memory_falls_back_to_completed_combat_rounds() -> None:
    stm = _build_sample_stm()
    stm._card_play_counts.clear()
    stm.end_combat(won=True, hp_after=70)

    memory = extract_card_build_memory(
        short_term=stm,
        run_id="run-1",
        character="The Silent",
        final_deck=["Strike", "Defend", "Neutralize"],
        victory=False,
        final_floor=3,
        fitness=42.0,
    )

    assert ("Strike", 1) in memory.card_play_counts
    assert ("Neutralize", 1) in memory.card_play_counts


def test_combat_store_load_deduplicates_same_run_and_floor() -> None:
    episode_a = CombatEpisode(run_id="run-1", floor=7, enemy_key="Jaw Worm")
    episode_b = CombatEpisode(run_id="run-1", floor=7, enemy_key="Jaw Worm")
    episode_c = CombatEpisode(run_id="run-1", floor=8, enemy_key="Louse")

    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path

        path = Path(td) / "combat.jsonl"
        path.write_text(
            "\n".join(json.dumps(ep.to_dict()) for ep in (episode_a, episode_b, episode_c)),
            encoding="utf-8",
        )

        store = CombatMemoryStore.load(path)

        assert store.count == 2


def test_card_build_store_deduplicates_same_run_id() -> None:
    store = CardBuildStore()
    store.add(CardBuildMemory(run_id="run-1"))
    store.add(CardBuildMemory(run_id="run-1", final_floor=22))

    assert store.count == 1


def test_route_store_deduplicates_same_run_and_act() -> None:
    store = RouteMemoryStore()
    store.add(RouteMemory(run_id="run-1", act=1))
    store.add(RouteMemory(run_id="run-1", act=1, character="The Silent"))
    store.add(RouteMemory(run_id="run-1", act=2))

    assert store.count == 2


def test_trim_working_context_preserves_event_memory_hints() -> None:
    # Regression: prior _trim_working_context silently dropped
    # event_memory_hints (not in all_fields; not passed to rebuilt WC).
    # Event decisions lost their EventGuide + past-event hints whenever
    # est_tokens exceeded budget.
    long_guide = "[Event Guide: NEOW] " + ("verbose guidance text. " * 40)
    past_events = (
        "Neow (Act1 F1): Chose \"Lost Coffer\". Boss impact: +0.3",
        "Neow (Act1 F1): Chose \"Neow's Torment\". Boss impact: +0.5",
        "Neow (Act1 F1): Chose \"Cursed Pearl\".",
    )
    wc = WorkingContext(
        event_memory_hints=(long_guide, *past_events),
    )
    # Shrink budget below full cost so trimming path executes.
    budget = max(1, wc.estimated_tokens() // 2)
    trimmed = _trim_working_context(wc, budget=budget)

    assert trimmed.event_memory_hints, "event_memory_hints dropped by trimmer"
    assert len(trimmed.event_memory_hints) >= 1
    assert trimmed.estimated_tokens() <= budget


def test_finalize_open_state_marks_abort_and_preserves_final_resources() -> None:
    stm = ShortTermMemory()
    stm.start_route_node(floor=8, node_type="monster", hp=34, gold=99)
    stm.start_combat(
        enemy_names=["Chosen"],
        combat_type="elite",
        hp=34,
        deck_size=10,
        relics=[],
        floor=8,
        act=1,
    )

    stm.finalize_open_state(act=1, hp=17, gold=143, combat_terminal_reason="abort")

    assert len(stm.route_nodes_by_act[1]) == 1
    assert len(stm.completed_combats) == 1
    route_node = stm.route_nodes_by_act[1][0]
    combat = stm.completed_combats[0]
    assert route_node.hp_after == 17
    assert route_node.gold_after == 143
    assert route_node.completion_reason == "aborted"
    assert combat.hp_after == 17
    assert combat.terminal_reason == "abort"
