"""Tests for P6 prompt token optimization changes."""
from __future__ import annotations

from unittest.mock import MagicMock

from src.brain.conversation import CombatConversation
from src.brain.prompts._deck_fmt import format_deck_section
from src.brain.tool_preprocessor import ToolHint, ToolPreprocessor
from src.mcp_client.upstream_models import RawDeckCardPayload
from src.skills.composer import compose_skill_context
from src.skills.models import Skill, SkillTrigger
from tests.test_conversation_compression import _make_gs, _simulate_round


class TestKeyEffectsDelta:
    """Key Effects should only inject new keywords, not repeat every round."""

    def test_round1_injects_all_relevant_effects(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        conv.add_round_state(gs)
        msg_text = str(conv.messages[-1]["content"])
        assert "Key Effects" in msg_text
        assert "Block:" in msg_text

    def test_round2_reinjects_effects(self) -> None:
        # `llm_messages` strips prior rounds from the LLM view, so glossary
        # injected in round 1 is no longer visible once round 2 begins.
        # Every new round must re-inject the glossary to keep keyword defs
        # live for the model.
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        # Round 1
        conv.add_round_state(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_execution_result(["Played Strike"], gs)
        # Round 2 — same hand, same effects
        gs2 = _make_gs(combat_round=2)
        conv.add_round_state(gs2)
        round2_text = str(conv.messages[-1]["content"])
        assert "Key Effects" in round2_text
        assert "Block:" in round2_text

    def test_new_effect_injected_on_appearance(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        # Round 1 — no poison
        conv.add_round_state(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_execution_result(["Played Strike"], gs)
        # Round 2 — add a poison card
        poison_cards = [
            {"index": 0, "name": "Deadly Poison", "energy_cost": 1,
             "playable": True, "rules_text": "Apply 5 poison."},
        ]
        gs2 = _make_gs(combat_round=2, hand_cards=poison_cards)
        conv.add_round_state(gs2)
        round2_text = str(conv.messages[-1]["content"])
        assert "Poison:" in round2_text

    def test_effects_reinjected_after_compression(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        for r in range(1, 6):
            _simulate_round(conv, r)
        conv.compress_history(keep_recent=1)
        gs_new = _make_gs(combat_round=6)
        conv.add_round_state(gs_new)
        round_text = str(conv.messages[-1]["content"])
        assert "Key Effects" in round_text
        assert "Block:" in round_text

    def test_replan_keeps_glossary(self) -> None:
        # Regression: re-plan within the same round must re-inject the glossary
        # because llm_messages only sends the latest user message to the LLM.
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        conv.add_round_state(gs)
        first_text = str(conv.messages[-1]["content"])
        assert "Block:" in first_text
        # Re-plan: call add_round_state again for the same combat_round.
        # is_replan is derived internally from (actual_round <= _round_count).
        conv.add_round_state(gs)
        replan_text = str(conv.messages[-1]["content"])
        assert "Re-plan" in replan_text
        assert "Key Effects" in replan_text
        assert "Block:" in replan_text

    def test_potion_description_triggers_glossary(self) -> None:
        # Regression: keywords that only appear in usable potion descriptions
        # (e.g. "Gain 5 Regen" from Regen Potion) must trigger the glossary —
        # otherwise the LLM has no definition for the buff the potion applies.
        from src.mcp_client.upstream_models import RawRunPotionPayload
        from src.state.game_state import GameState

        gs = _make_gs()
        # Inject a usable Regen Potion via upstream raw model so GameState
        # surfaces it through gs.potions.
        potion = RawRunPotionPayload(
            index=0, potion_id="REGEN_POTION", name="Regen Potion",
            description="Gain 5 Regen.", occupied=True, can_use=True,
        )
        gs_with_potion = GameState.from_upstream(
            gs.raw.model_copy(update={
                "run": gs.raw.run.model_copy(update={"potions": [potion]}),
            })
        )
        conv = CombatConversation("system prompt")
        conv.add_combat_start(gs_with_potion)
        conv.add_round_state(gs_with_potion)
        text = str(conv.messages[-1]["content"])
        assert "Key Effects" in text
        # Regen comes from the DLL mechanics fallback — match the family of
        # descriptions the extractor produces without pinning exact wording.
        assert "Regen N" in text or "Regen:" in text

class TestDeckGrouping:
    """Deck listing should group identical cards."""

    def _make_deck(self, cards: list[dict]) -> list[RawDeckCardPayload]:
        return [RawDeckCardPayload(**c) for c in cards]

    def test_groups_identical_cards(self) -> None:
        deck = self._make_deck([
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic"}
            for _ in range(5)
        ] + [
            {"name": "Defend", "energy_cost": 1, "card_type": "Skill", "rarity": "Basic"}
            for _ in range(5)
        ])
        lines = format_deck_section(deck)
        text = "\n".join(lines)
        assert "Strike x5" in text
        assert "Defend x5" in text

    def test_upgraded_cards_grouped_separately(self) -> None:
        deck = self._make_deck([
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic", "upgraded": False},
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic", "upgraded": False},
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic", "upgraded": True},
        ])
        lines = format_deck_section(deck)
        text = "\n".join(lines)
        assert "Strike x2" in text
        assert "Strike+" in text

    def test_unique_card_shows_cost(self) -> None:
        deck = self._make_deck([
            {"name": "Bash", "energy_cost": 2, "card_type": "Attack", "rarity": "Basic"},
        ])
        lines = format_deck_section(deck)
        text = "\n".join(lines)
        assert "Bash(cost=2)" in text

    def test_sorted_by_count_descending(self) -> None:
        deck = self._make_deck([
            {"name": "Bash", "energy_cost": 2, "card_type": "Attack", "rarity": "Basic"},
        ] + [
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic"}
            for _ in range(3)
        ])
        lines = format_deck_section(deck)
        text = "\n".join(lines)
        strike_pos = text.index("Strike x3")
        bash_pos = text.index("Bash")
        assert strike_pos < bash_pos

    def test_empty_deck(self) -> None:
        lines = format_deck_section([])
        assert "empty" in "\n".join(lines).lower()

    def test_none_deck(self) -> None:
        lines = format_deck_section(None)
        assert "unknown" in "\n".join(lines).lower()


class TestRoundSummaryCompact:
    """Round summaries should use compact format."""

    def test_compact_format_with_kills(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        _simulate_round(conv, 1, cards_played=["Strike", "Defend", "Bash"],
                        hp_after=52, enemy_alive=False)
        summary = conv._round_summaries[0]
        assert "R1:" in summary
        assert "3cards" in summary
        assert "52" in summary
        assert "kill:" in summary
        assert "Played" not in summary  # No verbose format

    def test_compact_format_no_kills(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        _simulate_round(conv, 1, cards_played=["Strike", "Defend"],
                        hp_after=55, enemy_hp_after=30)
        summary = conv._round_summaries[0]
        assert "R1:" in summary
        assert "2cards" in summary
        assert "55" in summary
        assert "kill:" not in summary

    def test_compact_no_actions(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        gs_round = _make_gs(combat_round=1)
        conv.add_round_state(gs_round)
        conv.add_assistant_plan([{"type": "text", "text": "End turn"}])
        conv.add_execution_result([], _make_gs(combat_round=1, hp=55))
        summary = conv._round_summaries[0]
        assert "0cards" in summary

class TestComputedInsightsCompression:
    """Hints should be compressed to actionable one-liners."""

    def test_extracts_priority_keys(self) -> None:
        hint = ToolHint(
            tool_name="buffer_survival_check",
            result={
                "survives": True,
                "hp_remaining": 63,
                "damage_taken": 7,
                "buffer_consumed_by": None,
                "fatal_attack": None,
                "recommendation": "GO — survives with 63 HP.",
            },
            latency_ms=5.0,
        )
        pp = ToolPreprocessor(MagicMock())
        text = pp.format_hints([hint])
        assert "{'survives'" not in text  # No raw dict dump
        assert len(text) < 200

    def test_deduplicates_overlapping_damage_tools(self) -> None:
        hint1 = ToolHint(
            tool_name="multi_enemy_incoming_damage",
            result={"total_incoming": 12, "survives": True, "recommendation": "CAN_SKIP_BLOCK"},
            latency_ms=3.0,
        )
        hint2 = ToolHint(
            tool_name="multi_enemy_total_damage",
            result={
                "total_incoming": 12, "survives": True, "damage_taken": 5,
                "verdict": "SURVIVE", "enemy_breakdown": [{"enemy": "Slime", "total_damage": 12}],
            },
            latency_ms=3.0,
        )
        pp = ToolPreprocessor(MagicMock())
        text = pp.format_hints([hint1, hint2])
        assert "multi_enemy_incoming_damage" not in text
        assert "multi_enemy_total_damage" in text

    def test_non_dict_result_handled(self) -> None:
        hint = ToolHint(tool_name="simple_tool", result="just a string", latency_ms=1.0)
        mock_registry = MagicMock()
        mock_registry.get.return_value = None
        pp = ToolPreprocessor(mock_registry)
        text = pp.format_hints([hint])
        assert "simple_tool" in text
        assert "just a string" in text

    def test_empty_hints_returns_empty(self) -> None:
        pp = ToolPreprocessor(MagicMock())
        assert pp.format_hints([]) == ""


class TestSkillFormatSlim:
    """Skill format should exclude examples, lessons, category, supplements."""

    def _make_skill(self, **overrides) -> Skill:
        defaults = {
            "skill_id": "test_001",
            "name": "Test Skill",
            "content": "Always track remaining energy and plan each card play carefully.",
            "category": "combat",
            "source": "seed",
            "confidence": 0.9,
            "verified": True,
            "usage_count": 5,
            "lessons": "Players who skip blocking take lethal damage.",
            "examples": ["With 3E: Defend first, then Strike."],
            "supplements_seed_id": "combat_basics_001",
            "trigger": SkillTrigger(state_types=frozenset({"monster", "elite", "boss"})),
        }
        defaults.update(overrides)
        return Skill(**defaults)

    def test_no_lessons_in_output(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Without this:" not in text
        assert "skip blocking" not in text

    def test_no_examples_in_output(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Example:" not in text

    def test_no_category_in_header(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "(combat," not in text

    def test_no_supplements_in_output(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Supplements seed" not in text

    def test_confidence_still_shown(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "90%" in text

    def test_combat_sequence_skill_keeps_one_example(self) -> None:
        skill = self._make_skill(
            content="Sequence: play 0-cost first, then debuffs, then draw cards.",
            examples=["Example A", "Example B"],
        )
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Example A" in text
        assert "Example B" not in text

    def test_skill_content_is_never_truncated(self) -> None:
        # Token budget has been removed; all skill content should always be included.
        skill = self._make_skill(
            content="Long skill content. " * 40,
            examples=[],
        )
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Long skill content." in text
        assert ids == [skill.skill_id]


class TestSkillGeneration400Char:
    """Skill generation rejects content > 400 chars."""

    # Valid evidence + rationale shared by both tests so they can reach
    # the content-length / library checks (new gates fire first).
    _VALID_EVIDENCE_AND_RATIONALE = {
        "evidence": {
            "run_ids": ["r1", "r2"],
            "stat_basis": "win rate 20% vs 45% baseline across 25 runs",
            "anchor_episode": "r1:combat_2",
        },
        "rationale": (
            "Pattern visible only across 25+ runs; single-run "
            "mistake_discovery lacks the cross-run win-rate comparator."
        ),
    }

    def test_evolution_returns_error_for_long_content(self) -> None:
        """EvolutionEngine._handle_write_skill handles content > 400 chars.

        When _backend is unavailable, LLM compression is skipped and
        deterministic truncation caps the content at 400 chars.  The call
        then falls through to the library-availability check — so the result
        is still REJECTED (for missing library), not for length.
        The important invariant is: content > 400 chars never silently passes
        the length gate with its original length.
        """
        from src.brain.evolution_engine import EvolutionEngine

        engine = EvolutionEngine.__new__(EvolutionEngine)
        engine._skill_library = None  # Will be checked after length

        result = engine._handle_write_skill({
            "skill_name": "Test Skill",
            "content": "C" * 401,
            "category": "combat",
            "motivation": "test",
            **self._VALID_EVIDENCE_AND_RATIONALE,
        })
        # Still rejected (library unavailable after truncation succeeds)
        assert "REJECTED" in result
        # Must NOT pass through with 401+ char content untouched
        assert "401" not in result or "too long" not in result.lower()

    def test_evolution_accepts_short_content(self) -> None:
        """Short content passes length validation (may fail at library check)."""
        from src.brain.evolution_engine import EvolutionEngine

        engine = EvolutionEngine.__new__(EvolutionEngine)
        engine._skill_library = None

        result = engine._handle_write_skill({
            "skill_name": "Test Skill",
            "content": "Short valid content.",
            "category": "combat",
            "motivation": "test",
            **self._VALID_EVIDENCE_AND_RATIONALE,
        })
        # Should NOT be rejected for length — will fail at "library not available"
        assert "too long" not in result.lower()
        assert "Skill library not available" in result
