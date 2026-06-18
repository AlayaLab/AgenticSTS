"""Tests for the per-card memory system (CardMemory, CardMemoryStore, extractor, retriever)."""

# ruff: noqa: E501
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from src.memory.build_role_memory import (
    apply_build_roles_to_card_memory,
    format_build_role_hint,
    role_observations_from_analysis,
)
from src.memory.card_memory_store import CardMemoryStore
from src.memory.models_v2 import CardMemory, WorkingContext

# ── CardMemory model tests ──────────────────────────────────────


class TestCardMemory:
    def test_effective_note_returns_note(self):
        cm = CardMemory(
            character="the silent",
            card_name="backstab",
            note="Played 45 times across 8 runs; strong opener.",
        )
        assert cm.effective_note() == "Played 45 times across 8 runs; strong opener."

    def test_effective_note_empty_when_no_content(self):
        cm = CardMemory(character="the silent", card_name="backstab")
        assert cm.effective_note() == ""

    def test_has_content(self):
        assert CardMemory(note="x").has_content
        assert CardMemory(
            build_role_observations=({"build_id": "poison", "role": "core"},),
        ).has_content
        assert not CardMemory().has_content

    def test_merge_run_stats(self):
        cm = CardMemory(
            character="the silent",
            card_name="backstab",
            note="innate damage",
            play_count=10,
            runs_won=2,
            runs_died_act1=1,
            sample_count=3,
        )
        # Victory
        merged = cm.merge_run_stats(
            play_count=5,
            draw_count=8,
            unplayed_draw_count=3,
            total_damage=40,
            victory=True,
            picked=True,
        )
        assert merged.play_count == 15
        assert merged.draw_count == 8
        assert merged.unplayed_draw_count == 3
        assert merged.total_damage == 40
        assert merged.runs_won == 3
        assert merged.runs_died_act1 == 1
        assert merged.pick_count == 1
        assert merged.sample_count == 4
        assert merged.note == "innate damage"  # preserved

        # Act 2 death
        merged2 = cm.merge_run_stats(play_count=3, victory=False, final_act=2)
        assert merged2.runs_won == 2
        assert merged2.runs_died_act2 == 1

        # Incomplete run
        merged3 = cm.merge_run_stats(play_count=3, victory=False, final_act=3, incomplete=True)
        assert merged3.runs_won == 2
        assert merged3.runs_died_act3 == 0  # not counted
        assert merged3.runs_incomplete == 1

    def test_merge_with_sums_counters_and_picks_newer_note(self):
        a = CardMemory(
            character="the silent",
            card_name="pinpoint",
            note="old base-name note",
            play_count=10,
            total_damage=50,
            sample_count=3,
            runs_won=1,
            last_updated=1000.0,
        )
        b = CardMemory(
            character="the silent",
            card_name="pinpoint+",
            note="new upgrade-variant note",
            play_count=0,
            total_damage=0,
            sample_count=0,
            last_updated=2000.0,
        )
        merged = a.merge_with(b)
        # Newer last_updated wins for note + card_name
        assert merged.note == "new upgrade-variant note"
        assert merged.card_name == "pinpoint+"
        # Counters summed
        assert merged.play_count == 10
        assert merged.total_damage == 50
        assert merged.sample_count == 3
        assert merged.runs_won == 1
        assert merged.last_updated == 2000.0

    def test_merge_with_history_interleaved_and_capped(self):
        a = CardMemory(
            character="the silent", card_name="pinpoint",
            note_history=(
                {"note": "n1", "ts": 100.0},
                {"note": "n3", "ts": 50.0},
            ),
            last_updated=100.0,
        )
        b = CardMemory(
            character="the silent", card_name="pinpoint+",
            note_history=(
                {"note": "n2", "ts": 80.0},
                {"note": "n4", "ts": 30.0},
            ),
            last_updated=80.0,
        )
        merged = a.merge_with(b)
        # Sorted by ts desc, capped at 3
        assert len(merged.note_history) == 3
        assert [e["note"] for e in merged.note_history] == ["n1", "n2", "n3"]

    def test_merge_with_rejects_character_mismatch(self):
        import pytest as _pytest
        a = CardMemory(character="the silent", card_name="strike")
        b = CardMemory(character="the ironclad", card_name="strike")
        with _pytest.raises(ValueError):
            a.merge_with(b)

    def test_merge_with_observations_preserved(self):
        obs1 = {"run_id": "r1", "build_id": "poison", "role": "core"}
        obs2 = {"run_id": "r2", "build_id": "shiv", "role": "support"}
        a = CardMemory(
            character="the silent", card_name="pinpoint",
            build_role_observations=(obs1,), last_updated=2000.0,
        )
        b = CardMemory(
            character="the silent", card_name="pinpoint+",
            build_role_observations=(obs2,), last_updated=1000.0,
        )
        merged = a.merge_with(b)
        # Both preserved (primary's first)
        assert merged.build_role_observations == (obs1, obs2)

    def test_serialization_roundtrip(self):
        cm = CardMemory(
            character="the silent",
            card_name="backstab",
            note="innate",
            play_count=10,
            total_damage=200,
        )
        d = cm.to_dict()
        restored = CardMemory.from_dict(d)
        assert restored.character == "the silent"
        assert restored.card_name == "backstab"
        assert restored.note == "innate"
        assert restored.play_count == 10
        assert restored.total_damage == 200

    def test_build_role_observations_roundtrip_and_preserved_by_merge(self):
        obs = {"run_id": "r1", "build_id": "poison", "role": "core"}
        cm = CardMemory(
            character="the silent",
            card_name="noxious fumes",
            build_role_observations=(obs,),
        )

        restored = CardMemory.from_dict(cm.to_dict())
        assert restored.build_role_observations == (obs,)

        merged = restored.merge_run_stats(play_count=1)
        assert merged.build_role_observations == (obs,)

    def test_apply_and_format_build_role_observation(self):
        store = CardMemoryStore()
        analysis = {
            "target_build_id": "poison",
            "confidence": 0.8,
            "card_roles": [
                {
                    "card": "Noxious Fumes+",
                    "role": "core",
                    "phase": "commitment",
                    "evidence": "Recurring poison scaling carried boss fights.",
                },
            ],
        }

        observations = role_observations_from_analysis(
            analysis, character="the silent", run_id="r1",
        )
        updated = apply_build_roles_to_card_memory(
            observations, store, character="the silent",
        )

        assert updated == 1
        memory = store.get("the silent", "noxious fumes")
        assert memory is not None
        assert memory.build_role_observations[0]["build_id"] == "poison"
        assert memory.build_role_observations[0]["role"] == "core"
        assert "core for poison" in format_build_role_hint(memory, ("poison",))

    def test_from_dict_migrates_legacy_fields(self):
        """Backward compat: old records with seed_note/live_summary/combat_hint → note."""
        # live_summary takes priority over seed_note
        d_live = {
            "character": "the silent",
            "card_name": "backstab",
            "seed_note": "old seed",
            "combat_hint": "old hint",
            "live_summary": "live experience note",
            "play_count": 5,
        }
        cm_live = CardMemory.from_dict(d_live)
        assert cm_live.note == "live experience note"

        # Falls back to seed_note when no live_summary
        d_seed = {
            "character": "the silent",
            "card_name": "pounce",
            "seed_note": "combo card",
            "combat_hint": "play before skills",
        }
        cm_seed = CardMemory.from_dict(d_seed)
        assert cm_seed.note == "combo card"

        # New format with note field
        d_new = {
            "character": "the silent",
            "card_name": "footwork",
            "note": "permanent dexterity scaling",
        }
        cm_new = CardMemory.from_dict(d_new)
        assert cm_new.note == "permanent dexterity scaling"


# ── CardMemoryStore tests ────────────────────────────────────────


class TestCardMemoryStore:
    def test_put_and_get(self):
        store = CardMemoryStore()
        cm = CardMemory(character="the silent", card_name="Backstab", note="strong")
        store.put(cm)
        assert store.count == 1
        result = store.get("the silent", "Backstab")
        assert result is not None
        assert result.note == "strong"

    def test_get_case_insensitive(self):
        store = CardMemoryStore()
        store.put(CardMemory(character="The Silent", card_name="BACKSTAB", note="x"))
        result = store.get("the silent", "backstab")
        assert result is not None

    def test_query_cards_only_returns_offered(self):
        store = CardMemoryStore()
        store.put(CardMemory(character="the silent", card_name="backstab", note="good opener"))
        store.put(CardMemory(character="the silent", card_name="pounce", note="combo card"))
        store.put(CardMemory(character="the silent", card_name="footwork", note="defense scaling"))

        # Only query for backstab and footwork
        results = store.query_cards("the silent", ["Backstab", "Footwork"])
        names = {r.card_name for r in results}
        assert "backstab" in names or "Backstab" in names.union({r.card_name.lower() for r in results})
        assert len(results) == 2

    def test_query_cards_skips_empty_content(self):
        store = CardMemoryStore()
        store.put(CardMemory(character="the silent", card_name="backstab"))  # no note
        results = store.query_cards("the silent", ["Backstab"])
        assert len(results) == 0

    def test_load_seeds_no_overwrite(self):
        store = CardMemoryStore()
        # Existing with a note already set
        store.put(CardMemory(
            character="the silent",
            card_name="backstab",
            note="existing note",
            play_count=10,
            sample_count=3,
        ))
        # Try to load new seed — should not overwrite because existing already has note
        seeds = [CardMemory(character="the silent", card_name="backstab", note="new seed")]
        loaded = store.load_seeds(seeds)
        assert loaded == 0
        existing = store.get("the silent", "backstab")
        assert existing.note == "existing note"

    def test_load_seeds_updates_empty_note(self):
        store = CardMemoryStore()
        # Existing with stats but no note
        store.put(CardMemory(
            character="the silent",
            card_name="backstab",
            play_count=10,
        ))
        seeds = [CardMemory(character="the silent", card_name="backstab", note="new seed")]
        loaded = store.load_seeds(seeds)
        assert loaded == 1
        existing = store.get("the silent", "backstab")
        assert existing.note == "new seed"
        assert existing.play_count == 10

    def test_load_seeds_creates_new(self):
        store = CardMemoryStore()
        seeds = [CardMemory(character="the silent", card_name="pounce", note="combo")]
        loaded = store.load_seeds(seeds)
        assert loaded == 1
        assert store.get("the silent", "pounce") is not None

    def test_key_strips_upgrade_suffix(self):
        """Strike, Strike+, and Strike++ all hit the same slot."""
        store = CardMemoryStore()
        store.put(CardMemory(character="the silent", card_name="Strike", note="base"))
        # All three lookups hit the same slot
        assert store.get("the silent", "strike") is not None
        assert store.get("the silent", "Strike+") is not None
        assert store.get("the silent", "STRIKE++") is not None
        assert store.count == 1

    def test_put_normalizes_stored_card_name(self):
        store = CardMemoryStore()
        store.put(CardMemory(character="the silent", card_name="Pinpoint++", note="x"))
        mem = store.get("the silent", "pinpoint")
        assert mem is not None
        assert mem.card_name == "pinpoint"  # canonicalized on put

    def test_put_replace_with_upgrade_variant(self):
        """Putting Strike+ after Strike replaces (not duplicates)."""
        store = CardMemoryStore()
        store.put(CardMemory(character="the silent", card_name="strike", note="old", play_count=5))
        store.put(CardMemory(character="the silent", card_name="Strike+", note="new", play_count=3))
        assert store.count == 1
        mem = store.get("the silent", "strike")
        assert mem.note == "new"
        assert mem.play_count == 3  # replace semantics, not merge

    def test_query_cards_handles_upgrade_variants(self):
        store = CardMemoryStore()
        store.put(CardMemory(character="the silent", card_name="pinpoint", note="combo finisher"))
        # Query with the upgraded runtime names — both resolve to the
        # same canonical slot and the result is deduped.
        results = store.query_cards("the silent", ["Pinpoint+", "Pinpoint++"])
        assert len(results) == 1
        assert results[0].note == "combo finisher"

    def test_load_merges_upgrade_variant_duplicates(self):
        """Legacy data may have separate slots for Strike and Strike+ —
        load() must collapse them into one base-name entry."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "card_memories.json"
            # Hand-craft legacy JSON with both variants present
            data = [
                {
                    "character": "the silent",
                    "card_name": "pinpoint",
                    "note": "older note",
                    "play_count": 10,
                    "total_damage": 50,
                    "sample_count": 3,
                    "last_updated": 1000.0,
                },
                {
                    "character": "the silent",
                    "card_name": "Pinpoint+",
                    "note": "newer note from LLM",
                    "play_count": 0,
                    "total_damage": 0,
                    "sample_count": 0,
                    "last_updated": 2000.0,
                },
            ]
            path.write_text(json.dumps(data), encoding="utf-8")

            loaded = CardMemoryStore.load(path)
            assert loaded.count == 1
            mem = loaded.get("the silent", "pinpoint")
            assert mem is not None
            assert mem.card_name == "pinpoint"
            # Newer last_updated wins for note
            assert mem.note == "newer note from LLM"
            # Stats summed
            assert mem.play_count == 10
            assert mem.total_damage == 50
            assert mem.sample_count == 3

    def test_persistence_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "card_memories.json"
            store = CardMemoryStore()
            store.put(CardMemory(character="the silent", card_name="backstab", note="good", play_count=5))
            store.put(CardMemory(character="the silent", card_name="pounce", note="combo", total_damage=100))
            store.save(path)

            loaded = CardMemoryStore.load(path)
            assert loaded.count == 2
            bs = loaded.get("the silent", "backstab")
            assert bs is not None
            assert bs.play_count == 5
            pn = loaded.get("the silent", "pounce")
            assert pn is not None
            assert pn.total_damage == 100


# ── Card memory extractor tests ─────────────────────────────────


class TestCardMemoryExtractor:
    def test_extract_per_card_stats(self):
        from src.memory.card_memory_extractor import extract_per_card_stats
        from src.memory.short_term import (
            CombatRoundTracker,
            CombatTracker,
            DeckChangeRecord,
            ShortTermMemory,
        )

        stm = ShortTermMemory()
        # Simulate some card plays
        stm._card_play_counts = {"Backstab": 5, "Defend": 8, "Strike": 3}

        # Simulate a combat with hand tracking
        tracker = CombatTracker(enemy_key="Slime", combat_type="monster")
        round1 = CombatRoundTracker(
            round_num=1,
            hand_at_start=["Backstab", "Defend", "Defend", "Strike", "Strike"],
            cards_played=["Backstab", "Defend", "Strike"],
        )
        round2 = CombatRoundTracker(
            round_num=2,
            hand_at_start=["Defend", "Strike", "Acrobatics"],
            cards_played=["Defend", "Acrobatics"],
        )
        tracker.rounds = [round1, round2]
        tracker._won = True
        tracker._hp_after = 60
        stm._completed_combats = [tracker]

        # Simulate deck events
        stm._deck_events = [
            DeckChangeRecord(floor=3, event_type="add", card_name="Backstab", source="combat_reward"),
            DeckChangeRecord(floor=5, event_type="add", card_name="Footwork", source="shop"),
        ]

        stats = extract_per_card_stats(stm, "the silent", ["Backstab", "Defend", "Strike"], True)

        assert "backstab" in stats
        assert stats["backstab"]["play_count"] == 5
        assert stats["backstab"]["draw_count"] == 1  # appeared once in hand
        assert stats["backstab"]["unplayed_draw_count"] == 0  # was played
        assert stats["backstab"]["picked"] is True

        assert "defend" in stats
        assert stats["defend"]["draw_count"] == 3  # 2 in round1, 1 in round2
        assert stats["defend"]["unplayed_draw_count"] == 1  # 1 unplayed in round1

        assert "strike" in stats
        assert stats["strike"]["draw_count"] == 3  # 2 in round1, 1 in round2
        assert stats["strike"]["unplayed_draw_count"] == 2  # 1 in round1, 1 in round2

        assert "footwork" in stats
        assert stats["footwork"]["bought"] is True

    def test_update_card_memories_from_run(self):
        from src.memory.card_memory_extractor import update_card_memories_from_run
        from src.memory.short_term import (
            CombatRoundTracker,
            CombatTracker,
            ShortTermMemory,
        )

        store = CardMemoryStore()
        # Pre-existing note
        store.put(CardMemory(character="the silent", card_name="backstab", note="innate"))

        stm = ShortTermMemory()
        stm._card_play_counts = {"Backstab": 3}
        tracker = CombatTracker(enemy_key="Slime", combat_type="monster")
        tracker.rounds = [CombatRoundTracker(round_num=1)]
        tracker._won = True
        tracker._hp_after = 60
        stm._completed_combats = [tracker]

        updated = update_card_memories_from_run(
            store, stm, "the silent", ["Backstab", "Defend"],
            victory=True, final_act=0, incomplete=False,
        )
        assert updated > 0

        bs = store.get("the silent", "backstab")
        assert bs is not None
        assert bs.play_count == 3
        assert bs.runs_won == 1
        assert bs.sample_count == 1
        assert bs.note == "innate"  # preserved


# ── WorkingContext card_memory_hints tests ────────────────────────


class TestWorkingContextCardMemory:
    def test_card_memory_hints_in_working_context(self):
        wc = WorkingContext(
            card_memory_hints=("Backstab: strong opener", "Footwork: defense scaling"),
        )
        assert not wc.is_empty
        assert wc.total_hints == 2
        assert wc.estimated_tokens() > 0

    def test_empty_card_memory_hints(self):
        wc = WorkingContext()
        assert wc.is_empty
        assert wc.total_hints == 0


# ── Prompt injector tests ─────────────────────────────────────────


class TestPromptInjectorCardMemory:
    def test_format_card_memory_section(self):
        from src.memory.prompt_injector import format_working_context

        wc = WorkingContext(
            card_memory_hints=(
                "Backstab: 0-cost innate damage",
                "Footwork: permanent Dexterity scaling",
            ),
        )
        result = format_working_context(wc)
        assert "## Card-Specific Insights" in result
        assert "Backstab: 0-cost innate damage" in result
        assert "Footwork: permanent Dexterity scaling" in result

    def test_no_card_section_when_empty(self):
        from src.memory.prompt_injector import format_working_context

        wc = WorkingContext(
            deck_guide_hints=("some deck guide",),
        )
        result = format_working_context(wc)
        assert "## Card-Specific Insights" not in result


# ── Retriever integration tests ────────────────────────────────


class TestRetrieverCardMemory:
    def _make_gs(self, state_type: str, character: str = "the silent"):
        """Create a minimal mock GameState."""
        gs = MagicMock()
        gs.state_type = state_type
        gs.is_combat = state_type in ("monster", "elite", "boss")
        gs.is_map = state_type == "map"
        gs.character = character
        gs.act = 1
        gs.floor = 5
        gs.enemies = []
        gs.hand = []

        # Card reward mock
        if state_type == "card_reward":
            option1 = MagicMock()
            option1.name = "Backstab"
            option2 = MagicMock()
            option2.name = "Footwork"
            option3 = MagicMock()
            option3.name = "InfiniteBlades"
            rw = MagicMock()
            rw.pending_card_choice = True
            rw.card_options = [option1, option2, option3]
            gs.reward = rw
        else:
            gs.reward = None

        gs.shop = None
        gs.selection = None
        return gs

    def test_card_memory_injected_for_card_reward(self):
        from src.memory.card_build_store import CardBuildStore
        from src.memory.combat_store import CombatMemoryStore
        from src.memory.guide_store import GuideStore
        from src.memory.retriever import query_for_decision
        from src.memory.route_store import RouteMemoryStore
        from src.memory.short_term import ShortTermMemory

        gs = self._make_gs("card_reward")
        stm = ShortTermMemory()
        card_mem_store = CardMemoryStore()
        card_mem_store.put(CardMemory(
            character="the silent", card_name="backstab", note="strong opener",
        ))
        card_mem_store.put(CardMemory(
            character="the silent", card_name="footwork", note="defense scaling",
        ))
        # InfiniteBlades has no memory — should not appear

        wc = query_for_decision(
            gs=gs,
            short_term=stm,
            combat_store=CombatMemoryStore(),
            route_store=RouteMemoryStore(),
            card_build_store=CardBuildStore(),
            guide_store=GuideStore(),
            card_memory_store=card_mem_store,
        )

        assert len(wc.card_memory_hints) == 2
        hint_text = " ".join(wc.card_memory_hints)
        assert "backstab" in hint_text.lower()
        assert "footwork" in hint_text.lower()
        assert "infiniteblades" not in hint_text.lower()

    def test_no_card_memory_for_combat(self):
        from src.memory.card_build_store import CardBuildStore
        from src.memory.combat_store import CombatMemoryStore
        from src.memory.guide_store import GuideStore
        from src.memory.retriever import query_for_decision
        from src.memory.route_store import RouteMemoryStore
        from src.memory.short_term import ShortTermMemory

        gs = self._make_gs("monster")
        card_mem_store = CardMemoryStore()
        card_mem_store.put(CardMemory(
            character="the silent", card_name="backstab", note="strong",
        ))

        wc = query_for_decision(
            gs=gs,
            short_term=ShortTermMemory(),
            combat_store=CombatMemoryStore(),
            route_store=RouteMemoryStore(),
            card_build_store=CardBuildStore(),
            guide_store=GuideStore(),
            card_memory_store=card_mem_store,
        )

        assert len(wc.card_memory_hints) == 0


# Silent seed notes loading test was removed 2026-05-04: the seed file
# ``src/skills/seeds/silent_card_notes.json`` was renamed to
# ``.disabled`` on 2026-04-29 (commit 6aed3ca) to support the from-zero
# intent of the self-evolve experiment condition, and never re-enabled.
# Card-note knowledge now lives exclusively in the live card_memory_store
# (auto-populated by postrun extraction) — there is no static seed loader
# left to test.


# ── Hand tracking telemetry tests ─────────────────────────────


class TestHandTracking:
    def test_hand_at_start_recorded(self):
        from src.memory.short_term import ShortTermMemory

        stm = ShortTermMemory()
        stm.start_combat(["Slime"], "monster", 70, 10, [], 1, 1)
        stm.start_combat_round(1, 3, 70, ["Slime: Attack 6"], hand_cards=["Backstab", "Defend", "Strike"])

        assert stm.current_combat is not None
        assert stm.current_combat._current_round is not None
        assert stm.current_combat._current_round.hand_at_start == ["Backstab", "Defend", "Strike"]

    def test_hand_at_start_defaults_empty(self):
        from src.memory.short_term import ShortTermMemory

        stm = ShortTermMemory()
        stm.start_combat(["Slime"], "monster", 70, 10, [], 1, 1)
        stm.start_combat_round(1, 3, 70, ["Slime: Attack 6"])

        assert stm.current_combat._current_round.hand_at_start == []


# ── note_history audit trail tests (Task 3 – 2026-04-24) ─────────


def test_card_memory_with_new_note_appends_to_history() -> None:
    """with_new_note creates a new instance with updated note + history."""
    from src.memory.models_v2 import CardMemory

    mem = CardMemory(character="silent", card_name="backstab", note="seed note")
    updated = mem.with_new_note(
        new_note="played 5x in 3 combats, always first-turn",
        run_id="run_20260424_01",
        reason="trace shows reliable first-turn damage",
        trace_citation="Combat 1 R1: Backstab for 11 dmg",
    )
    assert updated.note == "played 5x in 3 combats, always first-turn"
    assert len(updated.note_history) == 1
    entry = updated.note_history[0]
    assert entry["note"] == "played 5x in 3 combats, always first-turn"
    assert entry["run_id"] == "run_20260424_01"
    assert entry["reason"] == "trace shows reliable first-turn damage"
    assert entry["trace_citation"] == "Combat 1 R1: Backstab for 11 dmg"
    assert isinstance(entry["ts"], float) and entry["ts"] > 0
    # Original unchanged (immutable)
    assert mem.note == "seed note"
    assert mem.note_history == ()


def test_card_memory_note_history_caps_at_three() -> None:
    from src.memory.models_v2 import CardMemory

    mem = CardMemory(character="silent", card_name="sly")
    for i in range(5):
        mem = mem.with_new_note(
            new_note=f"note v{i}",
            run_id=f"run_{i}",
            reason=f"r{i}",
            trace_citation=f"c{i}",
        )
    assert len(mem.note_history) == 3
    # Newest first
    assert mem.note_history[0]["note"] == "note v4"
    assert mem.note_history[1]["note"] == "note v3"
    assert mem.note_history[2]["note"] == "note v2"
    # Oldest (v0, v1) evicted
    assert mem.note == "note v4"


def test_card_memory_note_history_serialization_roundtrip() -> None:
    from src.memory.models_v2 import CardMemory

    mem = CardMemory(character="silent", card_name="backstab")
    mem = mem.with_new_note(
        new_note="new note",
        run_id="run_x",
        reason="r",
        trace_citation="c",
    )
    d = mem.to_dict()
    assert "note_history" in d
    assert isinstance(d["note_history"], list)
    assert d["note_history"][0]["note"] == "new note"
    restored = CardMemory.from_dict(d)
    assert restored.note == "new note"
    assert restored.note_history == mem.note_history


def test_card_memory_from_dict_backward_compat_no_note_history() -> None:
    """Existing stored JSON with no note_history field parses cleanly."""
    from src.memory.models_v2 import CardMemory

    legacy = {
        "character": "silent", "card_name": "strike",
        "note": "seed", "pick_count": 2, "play_count": 5,
        # no note_history field
    }
    mem = CardMemory.from_dict(legacy)
    assert mem.note == "seed"
    assert mem.note_history == ()


def test_merge_run_stats_preserves_note_history() -> None:
    """merge_run_stats must forward note_history forward (regression for the
    same silent-drop pattern that already affected other fields)."""
    from src.memory.models_v2 import CardMemory

    mem = CardMemory(character="silent", card_name="backstab")
    mem = mem.with_new_note(
        new_note="trace-sourced",
        run_id="run_a",
        reason="r",
        trace_citation="c",
    )
    # merge_run_stats is typically called with a counter dict. Use a minimal
    # update that touches a counter, not the note, and confirm note_history
    # survives.
    merged = mem.merge_run_stats(
        play_count=1,
    )
    assert merged.note_history == mem.note_history
    assert len(merged.note_history) == 1
    assert merged.note_history[0]["note"] == "trace-sourced"
