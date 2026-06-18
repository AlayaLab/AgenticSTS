"""Tests for the build memory architecture (Phase B/C/D).

Covers:
1. Evidence extraction uses only traceable action-level signals
2. No round-level averaging attribution
3. LLM analysis fields are persisted in CardBuildMemory
4. Consolidation prompt includes richer analysis fields
5. Migration marks partial evidence quality
6. Retrieval surfaces build analysis fields
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.memory.card_build_extractor import (
    extract_build_evidence,
    extract_card_build_memory,
    format_evidence_for_llm,
    primary_tag,
)
from src.memory.guide_consolidator import (
    _deck_guide_needs_refresh,
    _deck_guide_source_fingerprint,
    _format_card_builds,
)
from src.memory.models_v2 import (
    CardBuildMemory,
    CombatDelta,
    DeckGuide,
    EnemyDelta,
)

# ── Helpers ──────────────────────────────────────────────────────


def _make_round_tracker(
    cards_played: list[str],
    damage_dealt: int = 0,
    block_gained: int = 0,
    damage_taken: int = 0,
    energy_used: int = 0,
    energy_available: int = 3,
    events: list | None = None,
):
    """Create a mock CombatRoundTracker."""
    mock = MagicMock()
    mock.round_num = 1
    mock.cards_played = cards_played
    mock.potions_used = []
    mock.hp_start = 70
    mock.hp_end = 70 - damage_taken
    mock.damage_dealt = damage_dealt
    mock.block_gained = block_gained
    mock.damage_taken = damage_taken
    mock.energy_used = energy_used
    mock.energy_available = energy_available
    mock.events = events or []
    return mock


def _make_combat_tracker(
    enemy_key: str = "Jaw Worm",
    combat_type: str = "monster",
    rounds: list | None = None,
    won: bool = True,
    hp_before: int = 70,
    hp_after: int = 60,
):
    """Create a mock CombatTracker."""
    mock = MagicMock()
    mock.enemy_key = enemy_key
    mock.combat_type = combat_type
    mock.rounds = rounds or []
    mock.total_rounds = len(mock.rounds)
    mock._won = won
    mock._hp_after = hp_after
    mock.hp_before = hp_before
    mock.floor = 2
    return mock


def _make_short_term(
    combats: list | None = None,
    play_counts: dict | None = None,
    deck_events: list | None = None,
    starting_deck: list | None = None,
):
    """Create a mock ShortTermMemory."""
    stm = MagicMock()
    stm.completed_combats = combats or []
    stm.card_play_counts = play_counts or {}
    stm.deck_events = deck_events or []
    stm.starting_deck = starting_deck or ["Strike", "Strike", "Defend", "Defend"]
    return stm


# ═══════════════════════════════════════════════════════════════
# 1. Evidence extraction: traceable signals only
# ═══════════════════════════════════════════════════════════════


class TestEvidenceExtraction:

    def test_action_level_damage_attribution(self):
        """Damage is only attributed when CombatDelta has source + enemy hp delta."""
        delta_bash = CombatDelta(
            event_type="card_play",
            source="Bash",
            enemy_deltas=(EnemyDelta(enemy_id="jw:0", name="Jaw Worm", hp=-8),),
        )
        delta_defend = CombatDelta(
            event_type="card_play",
            source="Defend",
            block=5,
        )
        rnd = _make_round_tracker(
            ["Bash", "Defend"],
            damage_dealt=8,
            block_gained=5,
            events=[delta_bash, delta_defend],
        )
        combat = _make_combat_tracker(rounds=[rnd])
        stm = _make_short_term(combats=[combat], play_counts={"Bash": 1, "Defend": 1})

        evidence = extract_build_evidence(
            stm, "Ironclad", ["Bash", "Defend"], False, 5, 30.0,
        )

        # Bash should have damage, Defend should not
        damage_cards = dict(evidence["top_damage"])
        assert damage_cards.get("Bash") == 8
        assert "Defend" not in damage_cards

        # Defend should have block, Bash should not
        block_cards = dict(evidence["top_block"])
        assert block_cards.get("Defend") == 5
        assert "Bash" not in block_cards

    def test_no_round_level_averaging(self):
        """When no CombatDelta events, damage/block lists are empty — NOT averaged."""
        rnd = _make_round_tracker(
            ["Strike", "Defend"],
            damage_dealt=10,
            block_gained=5,
            events=[],  # No action-level deltas
        )
        combat = _make_combat_tracker(rounds=[rnd])
        stm = _make_short_term(combats=[combat], play_counts={"Strike": 1, "Defend": 1})

        evidence = extract_build_evidence(
            stm, "Ironclad", ["Strike", "Defend"], False, 3, 20.0,
        )

        # No action deltas → no attribution
        assert evidence["top_damage"] == []
        assert evidence["top_block"] == []
        # But round-level totals still in combat summaries
        assert evidence["combat_summaries"][0]["total_damage_dealt"] == 10

    def test_energy_gain_tracked(self):
        """Energy gain from action deltas is recorded per card."""
        delta = CombatDelta(
            event_type="card_play",
            source="Adrenaline",
            energy=2,
        )
        rnd = _make_round_tracker(["Adrenaline"], events=[delta])
        combat = _make_combat_tracker(rounds=[rnd])
        stm = _make_short_term(combats=[combat], play_counts={"Adrenaline": 1})

        evidence = extract_build_evidence(
            stm, "Silent", ["Adrenaline"], True, 50, 80.0,
        )

        energy_cards = dict(evidence["top_energy_gain"])
        assert energy_cards.get("Adrenaline") == 2

    def test_powers_applied_tracked(self):
        """Powers/statuses applied by cards are recorded."""
        delta = CombatDelta(
            event_type="card_play",
            source="Demon Form",
            powers_changed=("+Strength(2)",),
        )
        rnd = _make_round_tracker(["Demon Form"], events=[delta])
        combat = _make_combat_tracker(rounds=[rnd])
        stm = _make_short_term(combats=[combat], play_counts={"Demon Form": 1})

        evidence = extract_build_evidence(
            stm, "Ironclad", ["Demon Form"], True, 50, 80.0,
        )

        assert len(evidence["top_powers_applied"]) == 1
        card, powers = evidence["top_powers_applied"][0]
        assert card == "Demon Form"
        assert any("+Strength(2)" in p for p, _c in powers)

    def test_enemy_debuffs_tracked(self):
        """Enemy debuffs applied by cards are recorded."""
        delta = CombatDelta(
            event_type="card_play",
            source="Noxious Fumes",
            enemy_deltas=(
                EnemyDelta(
                    enemy_id="jw:0",
                    name="Jaw Worm",
                    powers_changed=("+Poison(2)",),
                ),
            ),
        )
        rnd = _make_round_tracker(["Noxious Fumes"], events=[delta])
        combat = _make_combat_tracker(rounds=[rnd])
        stm = _make_short_term(combats=[combat], play_counts={"Noxious Fumes": 1})

        evidence = extract_build_evidence(
            stm, "Silent", ["Noxious Fumes"], True, 50, 80.0,
        )

        assert len(evidence["top_enemy_debuffs"]) == 1
        card, debuffs = evidence["top_enemy_debuffs"][0]
        assert card == "Noxious Fumes"

    def test_evidence_quality_full_with_deltas(self):
        """Evidence quality is 'full' when action-level deltas are present."""
        delta = CombatDelta(event_type="card_play", source="Strike")
        rnd = _make_round_tracker(["Strike"], events=[delta])
        combat = _make_combat_tracker(rounds=[rnd])
        stm = _make_short_term(combats=[combat], play_counts={"Strike": 1})

        evidence = extract_build_evidence(stm, "Ironclad", ["Strike"], False, 3, 20.0)
        assert evidence["evidence_quality"] == "full"

    def test_evidence_quality_round_summary_without_deltas(self):
        """Evidence quality is 'round_summary_only' when no action-level deltas."""
        rnd = _make_round_tracker(["Strike"], events=[])
        combat = _make_combat_tracker(rounds=[rnd])
        stm = _make_short_term(combats=[combat], play_counts={"Strike": 1})

        evidence = extract_build_evidence(stm, "Ironclad", ["Strike"], False, 3, 20.0)
        assert evidence["evidence_quality"] == "round_summary_only"

    def test_final_deck_payload_is_json_serialisable(self):
        """CardBuildMemory.build_evidence must round-trip through json.dumps.

        Regression guard: earlier revisions stored raw RawDeckCardPayload
        pydantic objects in the evidence dict, which json could not
        serialise and broke postrun persistence.
        """
        import json

        stm = _make_short_term(play_counts={"Strike": 1})

        raw_payload = SimpleNamespace(
            name="Noxious Fumes",
            upgraded=False,
            enchantment_name=None,
            enchantment_id=None,
            resolved_rules_text="At the start of each turn, apply 2 Poison to ALL enemies.",
            rules_text="At the start of each turn, apply {Poison:diff()} Poison...",
            card_type="power",
            rarity="uncommon",
            index=0,
            card_id="NoxiousFumes",
            dynamic_values=[],
            energy_cost=1,
            star_cost=0,
            costs_x=False,
            star_costs_x=False,
        )

        evidence = extract_build_evidence(
            stm, "the silent", ["Noxious Fumes"], False, 5, 20.0,
            final_deck_payload=[raw_payload],
        )

        # Evidence dict must json-serialise cleanly
        encoded = json.dumps(evidence)
        decoded = json.loads(encoded)

        assert decoded["final_deck_payload"] == [{
            "name": "Noxious Fumes",
            "upgraded": False,
            "enchantment_name": "",
            "rules_text": "At the start of each turn, apply 2 Poison to ALL enemies.",
            "card_type": "power",
            "rarity": "uncommon",
        }]


# ═══════════════════════════════════════════════════════════════
# 2. LLM analysis fields persisted in CardBuildMemory
# ═══════════════════════════════════════════════════════════════


class TestBuildAnalysisPersistence:

    def test_all_analysis_fields_stored(self):
        """All LLM analysis fields are persisted when build_analysis is provided."""
        stm = _make_short_term(play_counts={"Bash": 5, "Defend": 3})
        analysis = {
            "build_tags": ("strength", "scaling", "victory"),
            "build_summary": "Strength scaling deck with Demon Form.",
            "primary_plan": "strength scaling",
            "damage_engine": "Demon Form + Heavy Blade",
            "defense_engine": "Barricade + Entrench",
            "cycle_engine": "Battle Trance + Offering",
            "energy_engine": "Offering + base 3",
            "weak_points": "Slow setup, vulnerable to burst",
            "confidence": 0.8,
        }

        mem = extract_card_build_memory(
            stm, "run_123", "Ironclad", ["Bash", "Defend"],
            True, 50, 80.0, build_analysis=analysis,
        )

        assert mem.build_tags == ("strength", "scaling", "victory")
        assert mem.build_summary == "Strength scaling deck with Demon Form."
        assert mem.primary_plan == "strength scaling"
        assert mem.damage_engine == "Demon Form + Heavy Blade"
        assert mem.defense_engine == "Barricade + Entrench"
        assert mem.cycle_engine == "Battle Trance + Offering"
        assert mem.energy_engine == "Offering + base 3"
        assert mem.weak_points == "Slow setup, vulnerable to burst"
        assert mem.analysis_confidence == 0.8

    def test_empty_analysis_produces_empty_fields(self):
        """Without build_analysis, all interpretation fields are empty."""
        stm = _make_short_term(play_counts={"Strike": 1})
        mem = extract_card_build_memory(
            stm, "run_456", "Silent", ["Strike"],
            False, 3, 20.0, build_analysis=None,
        )

        assert mem.build_tags == ()
        assert mem.build_summary == ""
        assert mem.primary_plan == ""
        assert mem.damage_engine == ""
        assert mem.analysis_confidence == 0.0

    def test_to_dict_includes_all_fields(self):
        """to_dict serializes all analysis fields."""
        mem = CardBuildMemory(
            primary_plan="poison stacking",
            damage_engine="Noxious Fumes + Deadly Poison",
            defense_engine="Footwork + Backflip",
            cycle_engine="Acrobatics + Backflip",
            energy_engine="Concentrate",
            weak_points="No AoE",
            analysis_confidence=0.7,
            build_evidence={"evidence_quality": "full"},
        )
        d = mem.to_dict()
        assert d["primary_plan"] == "poison stacking"
        assert d["damage_engine"] == "Noxious Fumes + Deadly Poison"
        assert d["analysis_confidence"] == 0.7
        assert d["build_evidence"]["evidence_quality"] == "full"

    def test_from_dict_restores_all_fields(self):
        """from_dict restores all analysis fields."""
        d = {
            "primary_plan": "shiv burst",
            "damage_engine": "Blade Dance + Accuracy",
            "defense_engine": "After Image",
            "cycle_engine": "Backflip",
            "energy_engine": "Adrenaline",
            "weak_points": "Low block",
            "analysis_confidence": 0.6,
            "build_evidence": {"evidence_quality": "deck_snapshot_only"},
        }
        mem = CardBuildMemory.from_dict(d)
        assert mem.primary_plan == "shiv burst"
        assert mem.damage_engine == "Blade Dance + Accuracy"
        assert mem.analysis_confidence == 0.6
        assert mem.build_evidence["evidence_quality"] == "deck_snapshot_only"

    def test_legacy_archetype_from_primary_plan(self):
        """Legacy archetype is derived from primary_plan."""
        stm = _make_short_term(play_counts={"Strike": 1})
        analysis = {
            "build_tags": ("poison", "victory"),
            "primary_plan": "poison stacking",
            "confidence": 0.7,
        }
        mem = extract_card_build_memory(
            stm, "run_789", "Silent", ["Strike"],
            True, 50, 80.0, build_analysis=analysis,
        )
        assert mem.archetype == "poison stacking"


# ═══════════════════════════════════════════════════════════════
# 3. Consolidation uses richer fields
# ═══════════════════════════════════════════════════════════════


class TestConsolidationFormat:

    def test_format_includes_engines(self):
        """Consolidation format includes damage/defense/cycle engines."""
        mem = CardBuildMemory(
            victory=True,
            final_floor=50,
            fitness=90.0,
            card_play_counts=(("Bash", 15), ("Defend", 10)),
            build_summary="Strength scaling deck.",
            primary_plan="strength scaling",
            damage_engine="Demon Form + Heavy Blade",
            defense_engine="Barricade + Entrench",
            cycle_engine="Battle Trance",
            energy_engine="Offering",
            build_tags=("strength", "scaling", "victory"),
            analysis_confidence=0.8,
            final_deck=("Bash",) * 5,
        )
        text = _format_card_builds([mem])
        assert "Damage: Demon Form + Heavy Blade" in text
        assert "Defense: Barricade + Entrench" in text
        assert "Cycle: Battle Trance" in text
        assert "Plan: strength scaling" in text
        assert "confidence: 0.8" in text

    def test_format_omits_empty_engines(self):
        """Empty engine fields are not shown."""
        mem = CardBuildMemory(
            victory=False,
            final_floor=5,
            fitness=20.0,
            card_play_counts=(("Strike", 3),),
            final_deck=("Strike",) * 3,
        )
        text = _format_card_builds([mem])
        assert "Engines:" not in text
        assert "Plan:" not in text


# ═══════════════════════════════════════════════════════════════
# 4. Evidence quality in migration
# ═══════════════════════════════════════════════════════════════


class TestEvidenceQuality:

    def test_migration_evidence_quality(self):
        """Migration marks historical evidence as deck_snapshot_only."""
        from scripts.migrate_build_tags import _reconstruct_evidence
        data = {
            "character": "Silent",
            "final_deck": ["Strike", "Defend"],
            "card_play_counts": [["Strike", 5]],
            "victory": False,
            "final_floor": 10,
            "fitness": 40.0,
        }
        evidence = _reconstruct_evidence(data)
        assert evidence["evidence_quality"] == "deck_snapshot_only"
        # Action-level signals empty
        assert evidence["top_damage"] == []
        assert evidence["top_block"] == []
        assert evidence["top_energy_gain"] == []
        assert evidence["top_powers_applied"] == []
        assert evidence["top_enemy_debuffs"] == []

    def test_format_shows_quality_warning(self):
        """LLM prompt shows quality warning for non-full evidence."""
        evidence = {
            "character": "Silent",
            "victory": False,
            "final_floor": 10,
            "fitness": 40.0,
            "deck_size": 2,
            "evidence_quality": "deck_snapshot_only",
            "combats_won": 0,
            "combats_total": 0,
            "top_played": [],
            "top_damage": [],
            "top_block": [],
            "top_energy_gain": [],
            "top_exhaust": [],
            "top_powers_applied": [],
            "top_enemy_debuffs": [],
            "deck_events": [],
            "combat_summaries": [],
            "final_deck": [],
        }
        text = format_evidence_for_llm(evidence)
        assert "deck_snapshot_only" in text
        assert "some signals may be unavailable" in text


# ═══════════════════════════════════════════════════════════════
# 5. Primary tag extraction
# ═══════════════════════════════════════════════════════════════


class TestPrimaryTag:

    def test_first_non_outcome_tag(self):
        mem = CardBuildMemory(build_tags=("poison", "thin_cycle", "victory"))
        assert primary_tag(mem) == "poison"

    def test_skips_outcome_tags(self):
        mem = CardBuildMemory(build_tags=("victory",))
        assert primary_tag(mem) == "general"

    def test_fallback_to_primary_plan(self):
        mem = CardBuildMemory(build_tags=("defeat",), primary_plan="shiv burst")
        assert primary_tag(mem) == "shiv_burst"

    def test_fallback_to_general(self):
        mem = CardBuildMemory()
        assert primary_tag(mem) == "general"


# ═══════════════════════════════════════════════════════════════
# 6. Retrieval surfaces richer build analysis
# ═══════════════════════════════════════════════════════════════


class TestDeckRetrieval:

    def _make_retriever_deps(self, memories: list[CardBuildMemory]):
        """Create minimal mock dependencies for query_for_decision."""
        from src.memory.card_build_store import CardBuildStore
        from src.memory.card_memory_store import CardMemoryStore
        from src.memory.combat_store import CombatMemoryStore
        from src.memory.guide_store import GuideStore
        from src.memory.route_store import RouteMemoryStore

        card_build_store = CardBuildStore()
        for m in memories:
            card_build_store.add(m)

        guide_store = GuideStore()
        guide_store.set_deck_guide(DeckGuide(
            character="The Silent",
            archetype="poison",
            guide_text="Focus on poison stacking.",
            confidence=0.7,
        ))
        guide_store.set_deck_guide(DeckGuide(
            character="The Silent",
            archetype="shiv",
            guide_text="Focus on Shiv generation and payoff.",
            confidence=0.7,
        ))
        guide_store.set_deck_guide(DeckGuide(
            character="The Silent",
            archetype="general",
            guide_text="Stale general advice should not be injected.",
            confidence=0.7,
        ))

        combat_store = CombatMemoryStore()
        route_store = RouteMemoryStore()
        card_memory_store = CardMemoryStore()
        short_term = MagicMock()
        short_term.get_deck_summary.return_value = ""
        short_term.get_strategic_thread.return_value = ""
        short_term.completed_combats = []

        return (
            card_build_store,
            guide_store,
            combat_store,
            route_store,
            short_term,
            card_memory_store,
        )

    def test_retrieval_includes_primary_plan(self):
        """Retrieved deck hints should include primary_plan when available."""
        from src.memory.retriever import query_for_decision

        mem = CardBuildMemory(
            run_id="test_run",
            character="The Silent",
            archetype="poison stacking",
            build_tags=("poison", "victory"),
            primary_plan="poison stacking",
            damage_engine="Noxious Fumes + Deadly Poison",
            weak_points="No AoE damage",
            analysis_confidence=0.7,
            card_play_counts=(("Noxious Fumes", 10), ("Deadly Poison", 8)),
            victory=True,
            final_floor=50,
            fitness=90.0,
        )

        deps = self._make_retriever_deps([mem])
        (
            card_build_store, guide_store, combat_store, route_store,
            short_term, _card_memory_store,
        ) = deps

        # Create a mock GameState for card_reward (deck decision type)
        gs = MagicMock()
        gs.is_combat = False
        gs.is_map = False
        gs.state_type = "card_reward"
        gs.character = "The Silent"
        gs.run = MagicMock()
        gs.run.act = 1
        gs.run.deck = []
        gs.reward = None
        gs.shop = None
        gs.selection = None

        wc = query_for_decision(
            gs, short_term,
            combat_store, route_store, card_build_store,
            guide_store,
            archetype="poison",
        )

        # Deck guide should be found (poison guide + matching memory)
        all_hints = " ".join(wc.deck_guide_hints + wc.deck_memory_hints)
        assert "poison" in all_hints.lower()
        # Memory hint should include analysis fields
        assert "Noxious Fumes" in all_hints

    def test_retrieval_omits_empty_analysis(self):
        """When analysis is empty, retrieval still works with basic info."""
        from src.memory.retriever import query_for_decision

        mem = CardBuildMemory(
            run_id="test_run_2",
            character="The Silent",
            card_play_counts=(("Strike", 5),),
            victory=False,
            final_floor=5,
            fitness=20.0,
        )

        deps = self._make_retriever_deps([mem])
        (
            card_build_store, guide_store, combat_store, route_store,
            short_term, _card_memory_store,
        ) = deps

        gs = MagicMock()
        gs.is_combat = False
        gs.is_map = False
        gs.state_type = "card_reward"
        gs.character = "The Silent"
        gs.run = MagicMock()
        gs.run.act = 1
        gs.run.deck = []
        gs.reward = None
        gs.shop = None
        gs.selection = None

        wc = query_for_decision(
            gs, short_term,
            combat_store, route_store, card_build_store,
            guide_store,
        )

        all_hints = " ".join(wc.deck_guide_hints + wc.deck_memory_hints)
        # Should have basic floor/outcome info even without analysis
        assert "F5" in all_hints
        assert "LOSS" in all_hints

    def test_retrieval_uses_strategic_thread_build_signal(self):
        """Build guide retrieval should use run plan signals without explicit archetype."""
        from src.memory.retriever import query_for_decision

        deps = self._make_retriever_deps([])
        (
            card_build_store, guide_store, combat_store, route_store,
            short_term, _card_memory_store,
        ) = deps
        short_term.get_strategic_thread.return_value = (
            "- [card_reward] Win: Poison scaling with Noxious Fumes. "
            "Avoid expensive attacks."
        )

        gs = MagicMock()
        gs.is_combat = False
        gs.is_map = False
        gs.state_type = "card_reward"
        gs.character = "The Silent"
        gs.run = MagicMock()
        gs.run.act = 1
        gs.run.deck = []
        gs.reward = None
        gs.shop = None
        gs.selection = None

        wc = query_for_decision(
            gs, short_term,
            combat_store, route_store, card_build_store,
            guide_store,
        )

        guide_text = " ".join(wc.deck_guide_hints)
        assert "[Deck Guide: poison]" in guide_text
        assert "general" not in guide_text.lower()

    def test_retrieval_does_not_fallback_to_general_without_build_signal(self):
        """No active build signal means no deck guide; Phase 1 relies on framework/card data."""
        from src.memory.retriever import query_for_decision

        deps = self._make_retriever_deps([])
        (
            card_build_store, guide_store, combat_store, route_store,
            short_term, _card_memory_store,
        ) = deps

        gs = MagicMock()
        gs.is_combat = False
        gs.is_map = False
        gs.state_type = "card_reward"
        gs.character = "The Silent"
        gs.run = MagicMock()
        gs.run.act = 1
        gs.run.deck = ["Strike", "Defend", "Backflip"]
        gs.reward = None
        gs.shop = None
        gs.selection = None

        wc = query_for_decision(
            gs, short_term,
            combat_store, route_store, card_build_store,
            guide_store,
        )

        assert wc.deck_guide_hints == ()

    def test_retrieval_uses_offered_card_build_signal(self):
        """A build-defining offered card can summon the relevant build guide."""
        from src.memory.retriever import query_for_decision

        deps = self._make_retriever_deps([])
        (
            card_build_store, guide_store, combat_store, route_store,
            short_term, _card_memory_store,
        ) = deps

        gs = MagicMock()
        gs.is_combat = False
        gs.is_map = False
        gs.state_type = "card_reward"
        gs.character = "The Silent"
        gs.run = MagicMock()
        gs.run.act = 1
        gs.run.deck = ["Strike", "Defend"]
        gs.reward = SimpleNamespace(
            pending_card_choice=True,
            card_options=[SimpleNamespace(name="Accuracy")],
        )
        gs.shop = None
        gs.selection = None

        wc = query_for_decision(
            gs, short_term,
            combat_store, route_store, card_build_store,
            guide_store,
        )

        assert any("[Deck Guide: shiv]" in hint for hint in wc.deck_guide_hints)

    def test_retrieval_uses_card_memory_build_role_signal(self):
        """Offered card build roles should trigger the matching guide."""
        from src.memory.models_v2 import CardMemory
        from src.memory.retriever import query_for_decision

        deps = self._make_retriever_deps([])
        (
            card_build_store, guide_store, combat_store, route_store,
            short_term, card_memory_store,
        ) = deps
        card_memory_store.put(CardMemory(
            character="the silent",
            card_name="grand catalyst",
            build_role_observations=({
                "run_id": "r1",
                "build_id": "poison",
                "role": "payoff",
                "evidence": "Payoff for stacked poison.",
            },),
        ))

        gs = MagicMock()
        gs.is_combat = False
        gs.is_map = False
        gs.state_type = "card_reward"
        gs.character = "The Silent"
        gs.run = MagicMock()
        gs.run.act = 1
        gs.run.deck = ["Strike", "Defend"]
        gs.reward = SimpleNamespace(
            pending_card_choice=True,
            card_options=[SimpleNamespace(name="Grand Catalyst")],
        )
        gs.shop = None
        gs.selection = None

        wc = query_for_decision(
            gs, short_term,
            combat_store, route_store, card_build_store,
            guide_store,
            card_memory_store=card_memory_store,
        )

        assert any("[Deck Guide: poison]" in hint for hint in wc.deck_guide_hints)
        assert any("payoff for poison" in hint for hint in wc.card_memory_hints)


class TestDeckGuideRefresh:
    @staticmethod
    def _build(run_id: str, *, summary: str = "Poison scaling", tags: tuple[str, ...] = ("poison",)) -> CardBuildMemory:
        return CardBuildMemory(
            run_id=run_id,
            character="The Silent",
            build_summary=summary,
            primary_plan="poison",
            build_tags=tags,
            final_deck=("Strike", "Defend", "Deadly Poison"),
            card_play_counts=(("Deadly Poison", 4), ("Defend", 3)),
            fitness=100.0,
            final_floor=20,
        )

    def test_memory_count_shrink_is_stale(self):
        builds = [self._build(f"run_{i}") for i in range(101)]
        guide = DeckGuide(
            character="The Silent",
            archetype="poison",
            memory_count=101,
            source_fingerprint=_deck_guide_source_fingerprint(builds),
        )

        assert _deck_guide_needs_refresh(guide, builds[:96])
        assert not _deck_guide_needs_refresh(guide, builds)
        assert _deck_guide_needs_refresh(guide, builds + [self._build("run_101")])

    def test_same_count_but_changed_build_content_is_stale(self):
        builds = [self._build("run_1"), self._build("run_2")]
        guide = DeckGuide(
            character="The Silent",
            archetype="poison",
            memory_count=2,
            source_fingerprint=_deck_guide_source_fingerprint(builds),
        )

        updated_builds = [
            self._build("run_1", summary="Poison scaling"),
            self._build("run_2", summary="Poison scaling with Footwork support"),
        ]

        assert _deck_guide_needs_refresh(guide, updated_builds)
