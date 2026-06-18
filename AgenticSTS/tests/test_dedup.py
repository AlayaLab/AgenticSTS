"""Tests for src/skills/dedup.py — semantic dedup + common knowledge detection."""

from __future__ import annotations

import pytest

from src.skills.dedup import (
    _trigger_specificity,
    common_knowledge_score,
    content_overlap,
    is_seed_restatement,
    is_semantic_duplicate,
    trigger_overlap,
)
from src.skills.models import Skill, SkillTrigger

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_skill(content: str = "", trigger: SkillTrigger | None = None) -> Skill:
    return Skill(
        name="test",
        content=content,
        trigger=trigger or SkillTrigger(),
    )


def _combat_trigger(**kwargs) -> SkillTrigger:
    return SkillTrigger(state_types=frozenset({"monster"}), **kwargs)


# ── TestContentOverlap ────────────────────────────────────────────────────────


class TestContentOverlap:
    def test_identical_strings_return_one(self):
        text = "play block cards when incoming damage is high"
        assert content_overlap(text, text) == pytest.approx(1.0)

    def test_no_shared_tokens_return_zero(self):
        a = "strike sword attack"
        b = "defend shield protect"
        assert content_overlap(a, b) == pytest.approx(0.0)

    def test_stopwords_are_ignored(self):
        # "the", "is", "and" are stopwords — stripped before comparison
        a = "the block is good"
        b = "block good"
        # Both reduce to {"block", "good"} → Jaccard = 1.0
        assert content_overlap(a, b) == pytest.approx(1.0)

    def test_empty_strings_return_zero(self):
        assert content_overlap("", "") == pytest.approx(0.0)

    def test_one_empty_string_return_zero(self):
        assert content_overlap("block the enemy", "") == pytest.approx(0.0)

    def test_partial_overlap(self):
        a = "play block and attack cards"
        b = "play attack cards for damage"
        # a tokens (no stopwords): {play, block, attack, cards}
        # b tokens (no stopwords): {play, attack, cards, damage}
        # intersection: {play, attack, cards} = 3
        # union: {play, block, attack, cards, damage} = 5
        # Jaccard = 3/5 = 0.6
        result = content_overlap(a, b)
        assert 0.5 < result < 0.8


# ── TestTriggerOverlap ────────────────────────────────────────────────────────


class TestTriggerOverlap:
    def test_identical_triggers_return_one(self):
        t = SkillTrigger(
            state_types=frozenset({"monster", "elite"}),
            enemy_names=frozenset({"Cultist"}),
            requires_hand_capabilities=frozenset({"draw", "exhaust"}),
        )
        assert trigger_overlap(t, t) == pytest.approx(1.0)

    def test_completely_different_triggers_return_zero(self):
        a = SkillTrigger(
            state_types=frozenset({"monster"}),
            enemy_names=frozenset({"Cultist"}),
            requires_hand_capabilities=frozenset({"draw"}),
        )
        b = SkillTrigger(
            state_types=frozenset({"shop"}),
            enemy_names=frozenset({"Ironclad Boss"}),
            requires_hand_capabilities=frozenset({"exhaust"}),
        )
        assert trigger_overlap(a, b) == pytest.approx(0.0)

    def test_partial_overlap_state_types_only(self):
        a = SkillTrigger(state_types=frozenset({"monster", "elite"}))
        b = SkillTrigger(state_types=frozenset({"monster", "boss"}))
        # state_types: |{monster}| / |{monster,elite,boss}| = 1/3
        # enemy_names: both empty → skip
        # requires_hand_capabilities: both empty → skip
        # mean of [1/3] = 1/3 ≈ 0.333
        result = trigger_overlap(a, b)
        assert result == pytest.approx(1 / 3, rel=1e-6)

    def test_empty_triggers_return_zero(self):
        a = SkillTrigger()
        b = SkillTrigger()
        assert trigger_overlap(a, b) == pytest.approx(0.0)

    def test_one_side_empty_dimension_counted(self):
        # a has enemy_names, b does not → dimension is shared (one side non-empty)
        a = SkillTrigger(enemy_names=frozenset({"Cultist"}))
        b = SkillTrigger(enemy_names=frozenset())
        # enemy_names: intersection=0, union={"Cultist"} → score=0
        # state_types and tags: both empty → skip
        result = trigger_overlap(a, b)
        assert result == pytest.approx(0.0)

    def test_full_match_on_all_three_dimensions(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            enemy_names=frozenset({"Gremlin"}),
            requires_hand_capabilities=frozenset({"draw"}),
        )
        assert trigger_overlap(t, t) == pytest.approx(1.0)


# ── TestIsSemanticDuplicate ───────────────────────────────────────────────────


class TestIsSemanticDuplicate:
    def test_same_trigger_and_content_is_duplicate(self):
        trigger = SkillTrigger(
            state_types=frozenset({"monster"}),
            enemy_names=frozenset({"Cultist"}),
        )
        existing = _make_skill(
            content="always play block before attacking when cultist burns you",
            trigger=trigger,
        )
        candidate = {
            "content": "always play block before attacking when cultist burns you",
            "trigger": {"state_types": ["monster"], "enemy_names": ["Cultist"]},
        }
        assert is_semantic_duplicate(candidate, existing) is True

    def test_very_similar_content_regardless_of_trigger(self):
        # content_overlap >= 0.6 alone triggers duplicate
        existing = _make_skill(
            content="play block cards to reduce incoming damage from enemies",
        )
        candidate = {
            "content": "play block cards reduce incoming damage enemies",
            "trigger": {"state_types": ["shop"]},
        }
        assert is_semantic_duplicate(candidate, existing) is True

    def test_different_content_different_trigger_not_duplicate(self):
        existing = _make_skill(
            content="always pick strike when you have no attacks",
            trigger=SkillTrigger(state_types=frozenset({"card_reward"}), requires_hand_capabilities=frozenset({"draw"})),
        )
        candidate = {
            "content": "save potions for boss fights and emergencies",
            "trigger": {"state_types": ["monster"], "requires_hand_capabilities": ["exhaust"]},
        }
        assert is_semantic_duplicate(candidate, existing) is False

    def test_high_trigger_overlap_low_content_not_duplicate(self):
        # trigger >= 0.7 but content < 0.4 → NOT a duplicate
        trigger = SkillTrigger(
            state_types=frozenset({"monster"}),
            enemy_names=frozenset({"Cultist"}),
            requires_hand_capabilities=frozenset({"draw"}),
        )
        existing = _make_skill(
            content="exploit cultist vulnerability with multi-hit attacks",
            trigger=trigger,
        )
        candidate = {
            "content": "draw cards cycle through deck",
            "trigger": {"state_types": ["monster"], "enemy_names": ["Cultist"], "requires_hand_capabilities": ["draw"]},
        }
        result = is_semantic_duplicate(candidate, existing)
        assert result is False

    def test_high_content_overlap_is_always_duplicate(self):
        # Even with completely mismatched triggers, high content overlap → duplicate
        existing = _make_skill(
            content="use aoe cards against multiple enemies to deal damage efficiently",
            trigger=SkillTrigger(state_types=frozenset({"monster"})),
        )
        candidate = {
            "content": "aoe cards multiple enemies deal damage efficiently",
            "trigger": {"state_types": ["boss"], "enemy_names": ["Queen"]},
        }
        assert is_semantic_duplicate(candidate, existing) is True


# ── TestCommonKnowledgeScore ──────────────────────────────────────────────────


class TestCommonKnowledgeScore:
    def test_generic_block_advice_gets_heavy_penalty(self):
        # Matches "block_when_high_incoming", broad trigger, low novelty
        content = "defend block high incoming damage"
        trigger: dict = {}  # fully generic (specificity=0.0)
        novelty = 0.3       # low

        penalty, concept = common_knowledge_score(content, trigger, novelty)

        assert penalty >= 0.6
        assert concept == "block_when_high_incoming"

    def test_specific_trigger_caps_penalty(self):
        # Same content concept but trigger has enemy_names → specificity >= 0.3
        content = "defend block high incoming damage"
        trigger = {"enemy_names": ["Cultist", "Jaw Worm"], "requires_enemy_powers": ["strength"]}
        novelty = 0.3

        penalty, concept = common_knowledge_score(content, trigger, novelty)

        # Heavy penalty NOT triggered (specificity >= 0.2)
        assert penalty <= 0.3

    def test_high_novelty_caps_penalty(self):
        # Same concept but novelty is high → heavy penalty not triggered
        content = "defend block high incoming damage"
        trigger: dict = {}  # broad trigger
        novelty = 0.8

        penalty, concept = common_knowledge_score(content, trigger, novelty)

        assert penalty <= 0.3

    def test_no_concept_match_returns_zero(self):
        # Deliberately avoid any keyword from SYSTEM_PROMPT_CONCEPTS
        content = "niche synergy cultivating unique archetype via niche mechanic"
        trigger: dict = {}
        novelty = 0.2

        penalty, concept = common_knowledge_score(content, trigger, novelty)

        assert penalty == pytest.approx(0.0)
        assert concept == ""

    def test_energy_concept_matched(self):
        content = "spend all energy 0-cost free cards first"
        trigger: dict = {}
        novelty = 0.2

        penalty, concept = common_knowledge_score(content, trigger, novelty)

        assert concept in ("energy_management", "play_0_cost_first", "dont_waste_energy")

    def test_seed_restatement_check(self):
        # is_seed_restatement is a separate function but we test it here
        seed = _make_skill(content="always prioritize killing the enemy before defending")
        candidate_content = "prioritize killing enemies before defending always"
        assert is_seed_restatement(candidate_content, [seed]) is True


# ── TestIsSemanticDuplicate (edge cases) ──────────────────────────────────────


class TestIsSeedRestatement:
    def test_identical_to_seed_is_restatement(self):
        seed = _make_skill(content="use vulnerable before striking the enemy")
        assert is_seed_restatement("use vulnerable before striking the enemy", [seed]) is True

    def test_similar_above_threshold_is_restatement(self):
        seed = _make_skill(content="apply vulnerable then deal damage to the enemy")
        candidate = "apply vulnerable deal damage enemy"
        assert is_seed_restatement(candidate, [seed]) is True

    def test_different_content_not_restatement(self):
        seed = _make_skill(content="save potion for boss fight")
        candidate = "prioritize card draw early in the run"
        assert is_seed_restatement(candidate, [seed]) is False

    def test_empty_seed_list_returns_false(self):
        assert is_seed_restatement("some skill content", []) is False

    def test_accepts_dict_seeds(self):
        seed_dict = {"content": "use vulnerable before striking the enemy"}
        assert is_seed_restatement("use vulnerable before striking enemy", [seed_dict]) is True


# ── TestTriggerSpecificity (internal, but valuable to test directly) ──────────


class TestTriggerSpecificity:
    def test_empty_trigger_is_zero(self):
        assert _trigger_specificity({}) == pytest.approx(0.0)

    def test_enemy_names_adds_0_3(self):
        t = {"enemy_names": ["Cultist"]}
        assert _trigger_specificity(t) == pytest.approx(0.3)

    def test_all_fields_capped_at_one(self):
        t = {
            "enemy_names": ["Cultist"],
            "requires_cards": ["Strike"],
            "requires_hand_capabilities": ["draw"],
            "requires_enemy_powers": ["strength"],
            "any_of_relics": ["Burning Blood"],
            "min_act": 2,
            "max_act": 2,
        }
        # 0.3+0.2+0.2+0.1+0.1+0.1 = 1.0 (already at cap)
        assert _trigger_specificity(t) == pytest.approx(1.0)

    def test_narrow_act_range_adds_specificity(self):
        # min_act=2, max_act=3 → range=1 ≤ 3 → +0.1
        t = {"min_act": 2, "max_act": 3}
        assert _trigger_specificity(t) == pytest.approx(0.1)

    def test_wide_act_range_no_bonus(self):
        t = {"min_act": 0, "max_act": 99}
        assert _trigger_specificity(t) == pytest.approx(0.0)
