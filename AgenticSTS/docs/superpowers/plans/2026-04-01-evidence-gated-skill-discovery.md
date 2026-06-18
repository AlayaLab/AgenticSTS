# Evidence-Gated Skill Discovery — Phase 1.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current "LLM proposes → blindly add to library" skill discovery pipeline with an evidence-gated system: LLM proposes candidates → local evidence collection → scoring → classify as confirmed/candidate/rejected. Most candidates start as hypotheses, not active skills.

**Architecture:** Two new modules (`src/skills/dedup.py`, `src/skills/evidence.py`) handle all local evidence logic. `discovery.py` is modified to run candidates through the evidence pipeline before adding to library. A `data/evolution/hypotheses.jsonl` store holds candidates pending future validation. The classification gate enforces: backfill-only evidence cannot confirm; runtime evidence required for promotion.

**Tech Stack:** Python 3.12, frozen dataclasses, no new dependencies. Zero additional API calls for evidence collection.

**Spec:** `docs/2026-03-31-situation-level-retrieval-design.md` Section 17.

**Scope boundary:** This plan covers the evidence gate (Sections 17.3-17.9) and the discovery.py integration (Section 17.12). Hypothesis re-evaluation lifecycle (Section 17.10) and evolution_engine.py integration (Section 17.12 _handle_write_skill) are deferred to Phase 2.5.

**Explicitly deferred from this plan:**
- `trigger_overlap()` does NOT compare `threat_levels` / `intent_classes` dimensions because `SkillTrigger` lacks these fields until Phase 2 adds them. Current dedup uses `state_types`, `enemy_names`, `tags` only.
- `rule_store` overlap checking (`overlapping_rule_ids`) is deferred — rules are free-text and lack structured triggers, making meaningful overlap detection unreliable without LLM.
- Adherence evaluator (spec 17.10) is deferred to Phase 2.5.

**Intentional prompt changes:**
- `{duration}` and `{llm_calls}` format fields removed from discovery prompt — not useful for evidence-gated skill selection and add noise.
- Prompt reduced from "extract 0-3 skills" to "propose 0-2 candidate hypotheses" — quality over quantity.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/skills/dedup.py` | **CREATE** | `content_overlap()`, `trigger_overlap()`, `is_semantic_duplicate()`, `SYSTEM_PROMPT_CONCEPTS`, `_trigger_specificity()`, `common_knowledge_score()`, `is_seed_restatement()` |
| `src/skills/evidence.py` | **CREATE** | `RoundExemplar`, `SkillEvidenceCard`, `is_valid_evidence_round()`, `score_evidence()`, `classify_candidate()` |
| `src/skills/hypothesis_store.py` | **CREATE** | JSONL-backed store for candidate hypotheses (save/load/count) |
| `src/skills/discovery.py` | MODIFY | Revised prompt, evidence pipeline integration, 3-tier output. **Retains** `_DISCOVERY_SYSTEM`, `_format_decisions()`, `_format_existing_skills()` unchanged. Adds `gate_candidates()` for both sync and batch paths. |
| `src/agent/loop.py` | MODIFY | Pass combat_store to discover_skills (sync path), update batch path to use `gate_candidates()` |
| `config.py` | MODIFY | Add `CONFIRMED_THRESHOLD`, `HYPOTHESIS_THRESHOLD`, `MIN_EVIDENCE_SIMILARITY` |
| `tests/test_dedup.py` | **CREATE** | Tests for dedup + common knowledge detection |
| `tests/test_evidence.py` | **CREATE** | Tests for evidence collection + scoring + classification |

---

### Task 1: Config Constants

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Add evidence gate constants**

After the existing `UPCOMING_PATTERN_MIN_CONSISTENCY` line in config.py, add:

```python
# ── Evidence-Gated Skill Discovery ───────────────────────────
CONFIRMED_THRESHOLD = float(os.getenv("STS2_CONFIRMED_THRESHOLD", "4.0"))
HYPOTHESIS_THRESHOLD = float(os.getenv("STS2_HYPOTHESIS_THRESHOLD", "2.0"))
MIN_EVIDENCE_SIMILARITY = float(os.getenv("STS2_MIN_EVIDENCE_SIMILARITY", "3.0"))
HYPOTHESES_DIR = f"{DATA_DIR}/evolution"
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add evidence gate threshold config constants"
```

---

### Task 2: Dedup Module — Tests + Implementation

**Files:**
- Create: `tests/test_dedup.py`
- Create: `src/skills/dedup.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dedup.py
"""Tests for semantic dedup and common knowledge detection."""

from src.skills.dedup import (
    common_knowledge_score,
    content_overlap,
    is_seed_restatement,
    is_semantic_duplicate,
    trigger_overlap,
)
from src.skills.models import Skill, SkillTrigger


class TestContentOverlap:
    def test_identical(self):
        assert content_overlap("block when damage is high", "block when damage is high") > 0.9

    def test_no_overlap(self):
        assert content_overlap("play all attacks", "rest at campfire") == 0.0

    def test_stopwords_ignored(self):
        # "the" and "is" are stopwords — shouldn't inflate overlap
        score = content_overlap("the block is good", "block damage high")
        assert 0.1 < score < 0.5

    def test_empty_string(self):
        assert content_overlap("", "something") == 0.0
        assert content_overlap("something", "") == 0.0


class TestTriggerOverlap:
    def test_identical_triggers(self):
        t = SkillTrigger(state_types=frozenset({"monster"}), enemy_names=frozenset({"Nibbit"}))
        assert trigger_overlap(t, t) == 1.0

    def test_no_overlap(self):
        a = SkillTrigger(state_types=frozenset({"monster"}))
        b = SkillTrigger(state_types=frozenset({"rest_site"}))
        assert trigger_overlap(a, b) == 0.0

    def test_partial_overlap(self):
        a = SkillTrigger(state_types=frozenset({"monster", "elite"}))
        b = SkillTrigger(state_types=frozenset({"monster", "boss"}))
        score = trigger_overlap(a, b)
        assert 0.3 < score < 0.7  # 1/3 overlap on state_types

    def test_empty_triggers(self):
        a = SkillTrigger()
        b = SkillTrigger()
        assert trigger_overlap(a, b) == 0.0  # no dimensions to compare


class TestIsSemanticDuplicate:
    def test_same_trigger_and_content(self):
        candidate = {
            "content": "apply Weak before blocking on high damage rounds",
            "trigger": {"state_types": ["monster"], "enemy_names": ["Nibbit"]},
        }
        existing = Skill(
            content="apply Weak before blocking on high damage rounds",
            trigger=SkillTrigger(
                state_types=frozenset({"monster"}),
                enemy_names=frozenset({"Nibbit"}),
            ),
        )
        assert is_semantic_duplicate(candidate, existing) is True

    def test_different_content(self):
        candidate = {
            "content": "go full offense on buff rounds",
            "trigger": {"state_types": ["monster"]},
        }
        existing = Skill(
            content="apply Weak before blocking",
            trigger=SkillTrigger(state_types=frozenset({"monster"})),
        )
        assert is_semantic_duplicate(candidate, existing) is False

    def test_very_similar_content_different_trigger(self):
        candidate = {
            "content": "block when incoming damage is very high to survive",
            "trigger": {"state_types": ["elite"]},
        }
        existing = Skill(
            content="block when incoming damage is high to survive",
            trigger=SkillTrigger(state_types=frozenset({"monster"})),
        )
        # content_overlap > 0.6 → duplicate even with different trigger
        assert is_semantic_duplicate(candidate, existing) is True


class TestCommonKnowledgeScore:
    def test_generic_block_advice_high_penalty(self):
        score, concept = common_knowledge_score(
            "block when incoming damage is high and defend",
            trigger={},  # broad — no specifics
            novelty=0.1,
        )
        assert score >= 0.6
        assert concept == "block_when_high_incoming"

    def test_specific_trigger_caps_penalty(self):
        score, concept = common_knowledge_score(
            "Fuzzy Wurm high-threat: Weak before Block to reduce incoming damage",
            trigger={"enemy_names": ["Fuzzy Wurm"], "threat_levels": ["high"]},
            novelty=0.8,
        )
        assert score <= 0.3

    def test_no_overlap_zero_penalty(self):
        score, concept = common_knowledge_score(
            "go full offense on SALIVATE rounds",
            trigger={"enemy_names": ["The Insatiable"]},
            novelty=0.9,
        )
        assert score == 0.0
        assert concept == ""

    def test_seed_restatement(self):
        seed = Skill(
            content="Apply Weak to reduce incoming attack damage by 25%",
            source="seed",
        )
        assert is_seed_restatement(
            "Apply Weak to reduce incoming attack damage", [seed],
        ) is True
        assert is_seed_restatement(
            "Go full offense on buff rounds", [seed],
        ) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_dedup.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement dedup.py**

```python
# src/skills/dedup.py
"""Semantic dedup and common knowledge detection for skill candidates.

Spec: docs/2026-03-31-situation-level-retrieval-design.md Sections 17.7-17.8.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.skills.models import Skill, SkillTrigger

_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "when", "if", "then", "and", "or",
    "to", "in", "on", "at", "for", "with", "this", "that", "it", "of",
    "be", "do", "not", "no", "but", "by", "from", "as", "so",
})


def content_overlap(a_content: str, b_content: str) -> float:
    """Keyword overlap with stopword removal. Returns 0.0-1.0."""
    a_words = set(a_content.lower().split()) - _STOPWORDS
    b_words = set(b_content.lower().split()) - _STOPWORDS
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)


def trigger_overlap(a: SkillTrigger, b: SkillTrigger) -> float:
    """Score 0-1 how similar two triggers are across shared dimensions."""
    score = 0.0
    dimensions = 0

    if a.state_types and b.state_types:
        dimensions += 1
        score += len(a.state_types & b.state_types) / max(len(a.state_types | b.state_types), 1)

    if a.enemy_names and b.enemy_names:
        dimensions += 1
        score += len(a.enemy_names & b.enemy_names) / max(len(a.enemy_names | b.enemy_names), 1)

    if a.tags and b.tags:
        dimensions += 1
        score += len(a.tags & b.tags) / max(len(a.tags | b.tags), 1)

    return score / max(dimensions, 1)


def is_semantic_duplicate(candidate: dict, existing: Skill) -> bool:
    """Check if candidate is semantically equivalent to an existing skill.

    Duplicate if: triggers overlap highly AND content is similar,
    OR content alone is very similar (same advice, different trigger).
    """
    from src.skills.models import SkillTrigger

    c_content = candidate.get("content", "")
    c_overlap = content_overlap(c_content, existing.content)

    # Very similar content → duplicate regardless of trigger
    if c_overlap >= 0.6:
        return True

    # Same trigger + similar content
    trigger_data = candidate.get("trigger", {})
    c_trigger = SkillTrigger.from_dict(trigger_data) if trigger_data else SkillTrigger()
    t_overlap = trigger_overlap(c_trigger, existing.trigger)

    if t_overlap >= 0.7 and c_overlap >= 0.4:
        return True

    return False


# ── Common Knowledge Detection ───────────────────────────────

SYSTEM_PROMPT_CONCEPTS: dict[str, set[str]] = {
    "block_when_high_incoming": {"block", "incoming", "damage", "high", "defend"},
    "energy_management": {"energy", "cost", "0-cost", "free", "spend"},
    "kill_if_possible": {"kill", "lethal", "finish", "one-shot"},
    "vulnerable_before_damage": {"vulnerable", "before", "damage", "apply"},
    "weak_reduces_damage": {"weak", "reduce", "incoming", "less"},
    "dont_waste_energy": {"waste", "energy", "unspent", "leftover"},
    "play_0_cost_first": {"0-cost", "free", "first", "before"},
    "aoe_for_multi_enemy": {"aoe", "all", "enemies", "multi", "area"},
    "draw_before_play": {"draw", "before", "play", "cards", "cycle"},
    "potion_timing": {"potion", "timing", "save", "boss", "emergency"},
}


def _trigger_specificity(trigger: dict) -> float:
    """Score 0-1 how specific a candidate's trigger is."""
    score = 0.0
    if trigger.get("enemy_names"):
        score += 0.3
    if trigger.get("threat_levels"):
        score += 0.2
    if trigger.get("intent_classes"):
        score += 0.2
    if trigger.get("requires_hand_capabilities"):
        score += 0.2
    if trigger.get("deck_stages"):
        score += 0.1
    # Also count existing trigger fields
    if trigger.get("tags"):
        score += 0.1
    if trigger.get("min_act", 0) > 0 or trigger.get("max_act", 99) < 99:
        score += 0.1
    return min(score, 1.0)


def common_knowledge_score(content: str, trigger: dict, novelty: float) -> tuple[float, str]:
    """Score 0-1 effective common knowledge penalty + matched concept name.

    Heavy penalty only when: high keyword overlap + broad trigger + low novelty.
    Specific triggers cap penalty at 0.3.
    Returns (penalty, matched_concept_name).
    """
    words = set(content.lower().split())
    max_overlap = 0.0
    matched_concept = ""
    for concept, keywords in SYSTEM_PROMPT_CONCEPTS.items():
        overlap = len(words & keywords) / len(keywords)
        if overlap > max_overlap:
            max_overlap = overlap
            matched_concept = concept

    if max_overlap < 0.4:
        return 0.0, ""

    specificity = _trigger_specificity(trigger)

    is_broad_trigger = specificity < 0.2
    is_low_novelty = novelty < 0.5
    is_high_overlap = max_overlap >= 0.6

    if is_high_overlap and is_broad_trigger and is_low_novelty:
        return max_overlap, matched_concept

    return min(max_overlap * (1.0 - specificity), 0.3), matched_concept


def is_seed_restatement(content: str, seed_skills: list) -> bool:
    """Check if candidate restates a seed skill."""
    for seed in seed_skills:
        if getattr(seed, "source", "") != "seed":
            continue
        if content_overlap(content, seed.content) >= 0.5:
            return True
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dedup.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/skills/dedup.py tests/test_dedup.py
git commit -m "feat: add semantic dedup + common knowledge detection"
```

---

### Task 3: Evidence Models + Similarity Gate + Scoring

**Files:**
- Create: `tests/test_evidence.py`
- Create: `src/skills/evidence.py`

- [ ] **Step 1: Write failing tests for evidence models and classification**

```python
# tests/test_evidence.py
"""Tests for evidence collection, scoring, and classification gate."""

from src.skills.evidence import (
    CONFIRMED_THRESHOLD,
    HYPOTHESIS_THRESHOLD,
    RoundExemplar,
    SkillEvidenceCard,
    classify_candidate,
    is_valid_evidence_round,
    score_evidence,
)
from src.memory.models_v2 import CombatEpisode, CombatRound
from src.memory.situation import HandCapabilityTag, SituationTag


class TestIsValidEvidenceRound:
    def test_matching_enemy_and_threat(self):
        tag = SituationTag(threat_level="high", intent_class="attack", tag_source="runtime")
        ep = CombatEpisode(enemy_key="Nibbit", combat_type="monster")
        trigger = {"enemy_names": ["Nibbit"], "state_types": ["monster"]}
        valid, score = is_valid_evidence_round(trigger, tag, ep)
        assert valid is True
        assert score >= 3.0

    def test_wrong_enemy_rejected(self):
        tag = SituationTag(threat_level="high", intent_class="attack")
        ep = CombatEpisode(enemy_key="Fogmog", combat_type="monster")
        trigger = {"enemy_names": ["Nibbit"]}
        valid, _ = is_valid_evidence_round(trigger, tag, ep)
        assert valid is False

    def test_backfill_needs_higher_threshold(self):
        tag = SituationTag(threat_level="high", intent_class="attack", tag_source="backfill")
        ep = CombatEpisode(enemy_key="Nibbit", combat_type="monster")
        # This trigger matches combat_type (+1.0) + threat (+2.0) = 3.0
        # Backfill threshold is 4.0, so this should fail
        trigger = {"enemy_names": ["Nibbit"], "state_types": ["monster"]}
        valid, score = is_valid_evidence_round(trigger, tag, ep)
        # score = 1.0 (combat_type) + 2.0 (threat) = 3.0
        # backfill threshold = 3.0 + 1.0 = 4.0
        # 3.0 < 4.0 → should fail without intent match
        if score < 4.0:
            assert valid is False

    def test_runtime_passes_at_standard_threshold(self):
        tag = SituationTag(
            threat_level="high", intent_class="attack", tag_source="runtime",
        )
        ep = CombatEpisode(enemy_key="Nibbit", combat_type="monster")
        trigger = {"enemy_names": ["Nibbit"], "state_types": ["monster"]}
        valid, score = is_valid_evidence_round(trigger, tag, ep)
        # score = 1.0 (combat_type) + 2.0 (threat) = 3.0 >= 3.0 threshold
        assert valid is True


class TestScoreEvidence:
    def test_no_evidence_all_zeros(self):
        card = score_evidence(
            candidate={"name": "test", "content": "test advice", "trigger": {}},
            positive=[],
            negative=[],
            cross_run_refs=[],
            contradictions=[],
            overlap_skills=[],
            existing_skills=[],
            novelty_override=None,
        )
        assert card.evidence_support_score == 0.0
        assert card.negative_case_score == 0.0

    def test_one_positive_example(self):
        pos = [RoundExemplar(episode_id="a", run_id="r1", tag_source="runtime")]
        card = score_evidence(
            candidate={"name": "test", "content": "test advice", "trigger": {}},
            positive=pos,
            negative=[],
            cross_run_refs=[],
            contradictions=[],
            overlap_skills=[],
            existing_skills=[],
            novelty_override=None,
        )
        assert card.evidence_support_score == 0.3  # 1 positive from current run

    def test_cross_run_boosts_score(self):
        pos = [RoundExemplar(episode_id="a", run_id="r1", tag_source="runtime")]
        card = score_evidence(
            candidate={"name": "test", "content": "test advice", "trigger": {}},
            positive=pos,
            negative=[],
            cross_run_refs=["ep_from_old_run"],
            contradictions=[],
            overlap_skills=[],
            existing_skills=[],
            novelty_override=None,
        )
        assert card.cross_run_support_score >= 0.3


class TestClassifyCandidate:
    def test_no_evidence_rejected(self):
        card = SkillEvidenceCard(evidence_support_score=0.0)
        assert classify_candidate(card) == "rejected"

    def test_high_common_knowledge_rejected(self):
        card = SkillEvidenceCard(
            evidence_support_score=0.5,
            common_knowledge_penalty=0.8,
        )
        assert classify_candidate(card) == "rejected"

    def test_low_execution_clarity_rejected(self):
        card = SkillEvidenceCard(
            evidence_support_score=0.5,
            execution_clarity_score=0.2,
        )
        assert classify_candidate(card) == "rejected"

    def test_strong_evidence_with_runtime_confirmed(self):
        card = SkillEvidenceCard(
            evidence_support_score=0.7,
            negative_case_score=0.5,
            cross_run_support_score=0.5,
            novelty_score=0.8,
            execution_clarity_score=0.8,
            overlap_penalty=0.0,
            common_knowledge_penalty=0.0,
            positive_examples=(
                RoundExemplar(tag_source="runtime"),
            ),
        )
        assert card.candidacy_score >= CONFIRMED_THRESHOLD
        assert classify_candidate(card) == "confirmed"

    def test_backfill_only_caps_at_candidate(self):
        card = SkillEvidenceCard(
            evidence_support_score=0.7,
            negative_case_score=0.5,
            cross_run_support_score=0.5,
            novelty_score=0.8,
            execution_clarity_score=0.8,
            overlap_penalty=0.0,
            common_knowledge_penalty=0.0,
            positive_examples=(
                RoundExemplar(tag_source="backfill"),
            ),
        )
        assert card.candidacy_score >= CONFIRMED_THRESHOLD
        assert classify_candidate(card) == "candidate"  # NOT confirmed

    def test_moderate_score_hypothesis(self):
        card = SkillEvidenceCard(
            evidence_support_score=0.3,
            negative_case_score=0.3,
            novelty_score=0.5,
            execution_clarity_score=0.6,
            positive_examples=(RoundExemplar(tag_source="runtime"),),
        )
        score = card.candidacy_score
        assert HYPOTHESIS_THRESHOLD <= score < CONFIRMED_THRESHOLD
        assert classify_candidate(card) == "candidate"

    def test_duplicate_with_low_novelty_rejected(self):
        card = SkillEvidenceCard(
            evidence_support_score=0.5,
            overlap_penalty=0.8,
            novelty_score=0.2,
            execution_clarity_score=0.6,
        )
        assert classify_candidate(card) == "rejected"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement evidence.py**

```python
# src/skills/evidence.py
"""Evidence collection, scoring, and classification for skill candidates.

Spec: docs/2026-03-31-situation-level-retrieval-design.md Sections 17.4-17.6.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import config
from src.memory.situation import SituationTag, _adjacent_threat

logger = logging.getLogger(__name__)


# ── Models ───────────────────────────────────────────────────


@dataclass(frozen=True)
class RoundExemplar:
    """A specific round used as evidence for/against a skill candidate."""

    episode_id: str = ""
    run_id: str = ""
    enemy_key: str = ""
    round_num: int = 0
    threat_level: str = ""
    intent_class: str = ""
    hand_capabilities_summary: str = ""
    cards_played: tuple[str, ...] = ()
    damage_taken: int = 0
    outcome_quality: str = ""
    relevance_note: str = ""
    tag_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "run_id": self.run_id,
            "enemy_key": self.enemy_key,
            "round_num": self.round_num,
            "threat_level": self.threat_level,
            "intent_class": self.intent_class,
            "hand_capabilities_summary": self.hand_capabilities_summary,
            "cards_played": list(self.cards_played),
            "damage_taken": self.damage_taken,
            "outcome_quality": self.outcome_quality,
            "relevance_note": self.relevance_note,
            "tag_source": self.tag_source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoundExemplar:
        return cls(
            episode_id=d.get("episode_id", ""),
            run_id=d.get("run_id", ""),
            enemy_key=d.get("enemy_key", ""),
            round_num=d.get("round_num", 0),
            threat_level=d.get("threat_level", ""),
            intent_class=d.get("intent_class", ""),
            hand_capabilities_summary=d.get("hand_capabilities_summary", ""),
            cards_played=tuple(d.get("cards_played", ())),
            damage_taken=d.get("damage_taken", 0),
            outcome_quality=d.get("outcome_quality", ""),
            relevance_note=d.get("relevance_note", ""),
            tag_source=d.get("tag_source", ""),
        )


@dataclass(frozen=True)
class SkillEvidenceCard:
    """Structured evidence supporting or refuting a candidate skill."""

    candidate_name: str = ""
    candidate_content: str = ""
    candidate_trigger: dict = field(default_factory=dict)  # shallow-frozen (matches CardBuildMemory.build_evidence pattern)

    positive_examples: tuple[RoundExemplar, ...] = ()
    negative_examples: tuple[RoundExemplar, ...] = ()
    supporting_memory_refs: tuple[str, ...] = ()
    contradicting_examples: tuple[RoundExemplar, ...] = ()

    overlapping_skill_ids: tuple[str, ...] = ()
    overlap_type: str = ""

    is_system_prompt_knowledge: bool = False
    system_prompt_evidence: str = ""

    evidence_support_score: float = 0.0
    negative_case_score: float = 0.0
    cross_run_support_score: float = 0.0
    novelty_score: float = 0.0
    execution_clarity_score: float = 0.0
    overlap_penalty: float = 0.0
    common_knowledge_penalty: float = 0.0

    decision: str = ""
    rejection_reason: str = ""
    source_run_id: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def candidacy_score(self) -> float:
        raw = (
            self.evidence_support_score * 2.0
            + self.negative_case_score * 1.5
            + self.cross_run_support_score * 1.0
            + self.novelty_score * 1.0
            + self.execution_clarity_score * 0.5
            - self.overlap_penalty * 2.0
            - self.common_knowledge_penalty * 2.0
        )
        return max(0.0, raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_name": self.candidate_name,
            "candidate_content": self.candidate_content,
            "candidate_trigger": self.candidate_trigger,
            "positive_examples": [e.to_dict() for e in self.positive_examples],
            "negative_examples": [e.to_dict() for e in self.negative_examples],
            "supporting_memory_refs": list(self.supporting_memory_refs),
            "contradicting_examples": [e.to_dict() for e in self.contradicting_examples],
            "overlapping_skill_ids": list(self.overlapping_skill_ids),
            "overlap_type": self.overlap_type,
            "is_system_prompt_knowledge": self.is_system_prompt_knowledge,
            "evidence_support_score": self.evidence_support_score,
            "negative_case_score": self.negative_case_score,
            "cross_run_support_score": self.cross_run_support_score,
            "novelty_score": self.novelty_score,
            "execution_clarity_score": self.execution_clarity_score,
            "overlap_penalty": self.overlap_penalty,
            "common_knowledge_penalty": self.common_knowledge_penalty,
            "candidacy_score": self.candidacy_score,
            "decision": self.decision,
            "rejection_reason": self.rejection_reason,
            "source_run_id": self.source_run_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkillEvidenceCard:
        return cls(
            candidate_name=d.get("candidate_name", ""),
            candidate_content=d.get("candidate_content", ""),
            candidate_trigger=d.get("candidate_trigger", {}),
            positive_examples=tuple(
                RoundExemplar.from_dict(e) for e in d.get("positive_examples", ())
            ),
            negative_examples=tuple(
                RoundExemplar.from_dict(e) for e in d.get("negative_examples", ())
            ),
            supporting_memory_refs=tuple(d.get("supporting_memory_refs", ())),
            contradicting_examples=tuple(
                RoundExemplar.from_dict(e) for e in d.get("contradicting_examples", ())
            ),
            overlapping_skill_ids=tuple(d.get("overlapping_skill_ids", ())),
            overlap_type=d.get("overlap_type", ""),
            is_system_prompt_knowledge=d.get("is_system_prompt_knowledge", False),
            evidence_support_score=d.get("evidence_support_score", 0.0),
            negative_case_score=d.get("negative_case_score", 0.0),
            cross_run_support_score=d.get("cross_run_support_score", 0.0),
            novelty_score=d.get("novelty_score", 0.0),
            execution_clarity_score=d.get("execution_clarity_score", 0.0),
            overlap_penalty=d.get("overlap_penalty", 0.0),
            common_knowledge_penalty=d.get("common_knowledge_penalty", 0.0),
            decision=d.get("decision", ""),
            rejection_reason=d.get("rejection_reason", ""),
            source_run_id=d.get("source_run_id", ""),
            timestamp=d.get("timestamp", 0.0),
        )


# ── Similarity Gate ──────────────────────────────────────────


def is_valid_evidence_round(
    trigger: dict,
    tag: SituationTag,
    episode: Any,  # CombatEpisode
) -> tuple[bool, float]:
    """Check whether a round is situationally similar enough for evidence.

    Returns (qualifies, similarity_score).
    Backfill/legacy rounds need +1.0 higher threshold.
    """
    # Hard filter: enemy must match
    candidate_enemies = {n.lower() for n in trigger.get("enemy_names", [])}
    if candidate_enemies and episode.enemy_key.lower() not in candidate_enemies:
        return False, 0.0

    score = 0.0

    # combat_type
    candidate_types = set(trigger.get("state_types", []))
    if candidate_types and episode.combat_type in candidate_types:
        score += 1.0

    if tag is None:
        threshold = config.MIN_EVIDENCE_SIMILARITY
        return score >= threshold, score

    # threat_level
    candidate_threats = set(trigger.get("threat_levels", []))
    if candidate_threats:
        if tag.threat_level in candidate_threats:
            score += 2.0
        elif any(_adjacent_threat(tag.threat_level, t) for t in candidate_threats):
            score += 0.5

    # intent_class (skip unknown)
    candidate_intents = set(trigger.get("intent_classes", []))
    if candidate_intents and tag.intent_class != "unknown":
        if tag.intent_class in candidate_intents:
            score += 1.5

    # hand_capability overlap
    candidate_caps = set(trigger.get("requires_hand_capabilities", []))
    if candidate_caps and tag.hand_capabilities:
        matches = sum(1 for cap in candidate_caps if getattr(tag.hand_capabilities, cap, False))
        score += matches * 0.2

    # deck_stage
    candidate_stages = set(trigger.get("deck_stages", []))
    if candidate_stages and tag.deck_stage in candidate_stages:
        score += 0.5

    # Provenance-adjusted threshold
    threshold = config.MIN_EVIDENCE_SIMILARITY
    if tag.tag_source != "runtime":
        threshold += 1.0

    return score >= threshold, score


# ── Scoring ──────────────────────────────────────────────────

_PROVENANCE_WEIGHT = {"runtime": 1.0, "backfill": 0.5, "": 0.5}


def _provenance_multiplier(tag_source: str) -> float:
    return _PROVENANCE_WEIGHT.get(tag_source, 0.5)


def score_evidence(
    candidate: dict,
    positive: list[RoundExemplar],
    negative: list[RoundExemplar],
    cross_run_refs: list[str],
    contradictions: list[RoundExemplar],
    overlap_skills: list[str],
    existing_skills: list,
    novelty_override: float | None = None,
) -> SkillEvidenceCard:
    """Score a candidate's evidence into a SkillEvidenceCard.

    All scoring is local — zero API calls.
    """
    from src.skills.dedup import (
        common_knowledge_score,
        content_overlap,
        is_semantic_duplicate,
        is_seed_restatement,
    )

    content = candidate.get("content", "")
    trigger = candidate.get("trigger", {})

    # ── evidence_support_score ──
    weighted_positive = sum(_provenance_multiplier(p.tag_source) for p in positive)
    distinct_runs = len({p.run_id for p in positive if p.run_id})
    if weighted_positive == 0:
        evidence_support = 0.0
    elif weighted_positive < 1.0:
        evidence_support = 0.3
    elif distinct_runs >= 2 and weighted_positive >= 2.0:
        evidence_support = 1.0 if weighted_positive >= 3.0 else 0.7
    elif weighted_positive >= 1.5:
        evidence_support = 0.5
    else:
        evidence_support = 0.3

    # ── negative_case_score ──
    weighted_negative = sum(_provenance_multiplier(n.tag_source) for n in negative)
    neg_runs = len({n.run_id for n in negative if n.run_id})
    if weighted_negative == 0:
        negative_score = 0.0
    elif weighted_negative >= 1.5 and neg_runs >= 2:
        negative_score = 1.0
    elif weighted_negative >= 1.0:
        negative_score = 0.7 if neg_runs >= 2 else 0.5
    elif weighted_negative >= 0.5:
        negative_score = 0.3
    else:
        negative_score = 0.0

    # ── cross_run_support_score ──
    n_cross = len(cross_run_refs)
    n_contra = len(contradictions)
    if n_cross == 0:
        cross_run_score = 0.0
    elif n_cross >= 3 and n_contra == 0:
        cross_run_score = 1.0
    elif n_cross >= 2:
        cross_run_score = 0.6
    else:
        cross_run_score = 0.3

    # ── novelty_score ──
    if novelty_override is not None:
        novelty = novelty_override
    else:
        max_overlap = 0.0
        dup_type = "novel"
        for skill in existing_skills:
            if is_semantic_duplicate(candidate, skill):
                max_overlap = 1.0
                dup_type = "semantic_duplicate"
                break
            c_ov = content_overlap(content, skill.content)
            if c_ov > max_overlap:
                max_overlap = c_ov
        if max_overlap >= 0.6:
            novelty = 0.0
            dup_type = "semantic_duplicate"
        elif max_overlap >= 0.4:
            novelty = 0.2
            dup_type = "strict_subset"
        elif max_overlap >= 0.2:
            novelty = 0.5
            dup_type = "partial_overlap"
        else:
            novelty = 0.8
            dup_type = "novel"

    # ── execution_clarity_score ──
    # Heuristic: score by specificity indicators in content
    lower_content = content.lower()
    exec_score = 0.3  # base: at least directional advice
    if any(kw in lower_content for kw in ("when ", "if ", "vs ")):
        exec_score = 0.6  # conditional
    if any(kw in lower_content for kw in ("before ", "first ", "then ")):
        exec_score = 0.8  # sequencing
    if trigger.get("enemy_names") and trigger.get("threat_levels"):
        exec_score = max(exec_score, 0.8)

    # ── overlap_penalty ──
    if overlap_skills:
        overlap_penalty = min(len(overlap_skills) * 0.3, 1.0)
    else:
        overlap_penalty = 0.0
    if is_seed_restatement(content, existing_skills):
        overlap_penalty = max(overlap_penalty, 0.6)

    # ── common_knowledge_penalty ──
    ck_penalty, ck_concept = common_knowledge_score(content, trigger, novelty)

    return SkillEvidenceCard(
        candidate_name=candidate.get("name", ""),
        candidate_content=content,
        candidate_trigger=trigger,
        positive_examples=tuple(positive),
        negative_examples=tuple(negative),
        supporting_memory_refs=tuple(cross_run_refs),
        contradicting_examples=tuple(contradictions),
        overlapping_skill_ids=tuple(overlap_skills),
        overlap_type=dup_type if novelty_override is None else "",
        is_system_prompt_knowledge=ck_penalty >= 0.6,
        system_prompt_evidence=ck_concept,
        evidence_support_score=evidence_support,
        negative_case_score=negative_score,
        cross_run_support_score=cross_run_score,
        novelty_score=novelty,
        execution_clarity_score=exec_score,
        overlap_penalty=overlap_penalty,
        common_knowledge_penalty=ck_penalty,
        source_run_id=candidate.get("source_run_id", ""),
    )


# ── Classification Gate ──────────────────────────────────────


def classify_candidate(card: SkillEvidenceCard) -> str:
    """Classify candidate into confirmed | candidate | rejected.

    Key rules:
    - Backfill-only evidence cannot confirm (caps at candidate)
    - Without negative evidence, cannot confirm (unless strong cross-run)
    - Hard rejections for common knowledge, duplicates, no evidence, vague
    """
    score = card.candidacy_score

    # Hard rejections
    if card.common_knowledge_penalty >= 0.8:
        return "rejected"
    if card.overlap_penalty >= 0.8 and card.novelty_score < 0.3:
        return "rejected"
    if card.evidence_support_score == 0.0:
        return "rejected"
    if card.execution_clarity_score < 0.3:
        return "rejected"

    has_positive = card.evidence_support_score >= 0.3
    has_negative = card.negative_case_score >= 0.3
    has_strong_cross_run = (
        card.cross_run_support_score >= 0.8
        and card.evidence_support_score >= 0.7
    )
    has_runtime_evidence = any(
        ex.tag_source == "runtime"
        for ex in card.positive_examples
    )

    if not has_positive:
        return "rejected"

    if score >= config.CONFIRMED_THRESHOLD:
        if not has_runtime_evidence:
            return "candidate"
        if has_negative:
            return "confirmed"
        if has_strong_cross_run:
            return "confirmed"
        return "candidate"

    if score >= config.HYPOTHESIS_THRESHOLD:
        return "candidate"
    return "rejected"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_evidence.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/skills/evidence.py tests/test_evidence.py
git commit -m "feat: add evidence models, similarity gate, scoring, classification gate"
```

---

### Task 4: Hypothesis Store

**Files:**
- Create: `src/skills/hypothesis_store.py`

- [ ] **Step 1: Implement hypothesis store**

```python
# src/skills/hypothesis_store.py
"""JSONL-backed store for candidate hypotheses pending validation.

Hypotheses are skill candidates that didn't meet the confirmed threshold
but had enough evidence to be worth tracking. They're re-evaluated
against new episodes in Phase 2.5.

Spec: Section 17.10.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import config
from src.skills.evidence import SkillEvidenceCard

logger = logging.getLogger(__name__)


class HypothesisStore:
    """Append-only JSONL store for candidate hypotheses."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(config.HYPOTHESES_DIR) / "hypotheses.jsonl"
        self._hypotheses: list[SkillEvidenceCard] = []
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8").strip()
            for line in text.split("\n"):
                if line.strip():
                    self._hypotheses.append(
                        SkillEvidenceCard.from_dict(json.loads(line))
                    )
            logger.info("Loaded %d hypotheses from %s", len(self._hypotheses), self._path)
        except Exception:
            logger.warning("Failed to load hypotheses", exc_info=True)

    def save(self, card: SkillEvidenceCard) -> None:
        """Append a hypothesis to the store."""
        self._hypotheses.append(card)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(card.to_dict(), ensure_ascii=False) + "\n")
        logger.info(
            "Saved hypothesis: %s (score=%.1f)",
            card.candidate_name, card.candidacy_score,
        )

    @property
    def count(self) -> int:
        return len(self._hypotheses)

    @property
    def all_hypotheses(self) -> list[SkillEvidenceCard]:
        return list(self._hypotheses)
```

- [ ] **Step 2: Commit**

```bash
git add src/skills/hypothesis_store.py
git commit -m "feat: add JSONL hypothesis store for candidate skills"
```

---

### Task 5: Discovery Pipeline Integration

**Files:**
- Modify: `src/skills/discovery.py`
- Modify: `src/agent/loop.py`

**Key design**: Extract evidence gating into a standalone `gate_candidates()` function that accepts raw candidate dicts + combat_store + existing skills, and returns (confirmed, evidence_cards). Both the async `discover_skills()` path (sync discovery) AND the batch result processing path call this same function. This fixes the batch path breakage.

**Retained unchanged from current discovery.py**: `_DISCOVERY_SYSTEM`, `_format_decisions()`, `_format_existing_skills()`.

- [ ] **Step 1: Revise discovery.py prompt and add evidence pipeline**

Replace `_DISCOVERY_PROMPT`, `discover_skills`, and `_parse_discovered_skills`. Add `gate_candidates()` and `_parse_discovered_candidates()`. Keep everything else.

```python
_DISCOVERY_PROMPT = """\
## Run Summary
- Result: {result}
- Character: {character}
- Final floor: {final_floor}
- Fitness score: {fitness:.1f}
- Combats: {combats_won}/{combats_total} won

## Key Decision Points
{decision_points}

## Existing Skills (avoid duplicates)
{existing_skills}

## Task
Propose 0-2 candidate skill hypotheses from this run. Quality over quantity.

For each candidate, you MUST provide:
1. The specific rounds/situations that motivated this hypothesis
2. At least one round where NOT following this advice led to worse outcomes
3. Why this is NOT already covered by existing skills or the system prompt

TRIGGER SPECIFICITY (critical):
- enemy_names: which enemies? (e.g., ["Lagavulin", "Kin Priest"])
- tags: situation keywords (low_hp, multi_enemy, poison_build, etc.)
A generic skill with no enemy names, no act limits, and no tags
competes with 50+ other generic skills and will NEVER be selected.

Return a JSON array (or empty []):
[
  {{
    "name": "Skill Name",
    "category": "combat",
    "tier": "specific",
    "trigger": {{
      "state_types": ["monster", "elite"],
      "enemy_names": [],
      "tags": ["relevant", "tags"]
    }},
    "content": "Strategic advice (MUST be ≤400 chars, concise rules only)",
    "lessons": "What goes wrong without this skill",
    "positive_rounds": [{{"round": 3, "floor": 8, "description": "what happened"}}],
    "negative_rounds": [{{"round": 3, "floor": 8, "description": "what went wrong"}}],
    "not_covered_by": "Why existing skills/system prompt don't cover this"
  }}
]

IMPORTANT: Return ONLY the JSON array."""


async def discover_skills(
    run_state: RunState,
    existing_skills: list[Skill] | None = None,
    *,
    combat_store: Any | None = None,
) -> tuple[list[Skill], list[SkillEvidenceCard]]:
    """Analyze a completed run and discover new skills via evidence gate.

    Returns (confirmed_skills, all_evidence_cards).
    Confirmed skills should be added to library.
    Evidence cards are for audit trail (hypotheses saved separately).
    """
    from src.brain.llm_caller import call_raw as llm_call_raw
    from src.skills.evidence import (
        RoundExemplar,
        SkillEvidenceCard,
        classify_candidate,
        is_valid_evidence_round,
        score_evidence,
    )
    from src.skills.hypothesis_store import HypothesisStore

    all_skills = existing_skills or []
    result = "VICTORY" if run_state.victory else f"DEFEAT (floor {run_state.final_floor})"

    prompt = _DISCOVERY_PROMPT.format(
        result=result,
        character=run_state.character or "Unknown",
        final_floor=run_state.final_floor,
        fitness=run_state.fitness(),
        combats_won=run_state.combats_won,
        combats_total=run_state.combats_total,
        decision_points=_format_decisions(run_state),
        existing_skills=_format_existing_skills(all_skills),
    )

    try:
        raw_text, latency, tokens = await llm_call_raw(
            _DISCOVERY_SYSTEM, prompt, think=True,
        )
        logger.info("Skill discovery LLM call: %.0fms, %d tokens", latency, tokens)
    except Exception:
        logger.warning("Skill discovery failed", exc_info=True)
        return [], []

    candidates = _parse_discovered_candidates(raw_text)
    if not candidates:
        return [], []

    # Delegate to shared gate_candidates() — same function used by batch path
    return gate_candidates(
        candidates=candidates,
        run_id=run_state.run_id,
        combat_store=combat_store,
        existing_skills=all_skills,
    )


def gate_candidates(
    candidates: list[dict],
    run_id: str,
    combat_store: Any | None = None,
    existing_skills: list[Skill] | None = None,
) -> tuple[list[Skill], list[SkillEvidenceCard]]:
    """Run evidence gate on raw candidate dicts. Used by BOTH sync and batch paths.

    This is the shared entry point that replaces the old _parse_discovered_skills().
    Both discover_skills() and the batch result processing in loop.py call this.

    Returns (confirmed_skills, all_evidence_cards).
    """
    from src.skills.evidence import (
        RoundExemplar,
        SkillEvidenceCard,
        classify_candidate,
        is_valid_evidence_round,
        score_evidence,
    )
    from src.skills.dedup import is_semantic_duplicate
    from src.skills.hypothesis_store import HypothesisStore

    all_skills = existing_skills or []
    confirmed_skills: list[Skill] = []
    evidence_cards: list[SkillEvidenceCard] = []
    hypothesis_store = HypothesisStore()

    # Collect all episodes for evidence
    all_episodes = combat_store.get_all() if combat_store else []
    current_run_episodes = [ep for ep in all_episodes if ep.run_id == run_id]
    other_episodes = [ep for ep in all_episodes if ep.run_id != run_id]

    for candidate in candidates:
        trigger = candidate.get("trigger", {})
        positive: list[RoundExemplar] = []
        negative: list[RoundExemplar] = []
        cross_run_refs: list[str] = []

        # Evidence from current run
        for ep in current_run_episodes:
            for rnd in ep.rounds:
                tag = rnd.situation_tag
                if tag is None:
                    continue
                valid, _ = is_valid_evidence_round(trigger, tag, ep)
                if not valid:
                    continue
                exemplar = RoundExemplar(
                    episode_id=ep.episode_id,
                    run_id=ep.run_id,
                    enemy_key=ep.enemy_key,
                    round_num=rnd.round_num,
                    threat_level=tag.threat_level,
                    intent_class=tag.intent_class,
                    cards_played=rnd.cards_played,
                    damage_taken=rnd.damage_taken,
                    outcome_quality=tag.outcome_quality,
                    tag_source=tag.tag_source,
                )
                if tag.outcome_quality in ("clean", "acceptable"):
                    positive.append(exemplar)
                elif tag.outcome_quality in ("bad", "disaster"):
                    negative.append(exemplar)

        # Cross-run support from memory
        for ep in other_episodes:
            for rnd in ep.rounds:
                tag = rnd.situation_tag
                if tag is None:
                    continue
                valid, _ = is_valid_evidence_round(trigger, tag, ep)
                if valid and tag.outcome_quality in ("clean", "acceptable"):
                    cross_run_refs.append(ep.episode_id)
                    break  # one per episode

        overlap_ids = [
            s.skill_id for s in all_skills
            if is_semantic_duplicate(candidate, s)
        ]

        card = score_evidence(
            candidate=candidate,
            positive=positive,
            negative=negative,
            cross_run_refs=cross_run_refs,
            contradictions=[],
            overlap_skills=overlap_ids,
            existing_skills=all_skills,
        )

        decision = classify_candidate(card)
        card = SkillEvidenceCard(
            candidate_name=card.candidate_name,
            candidate_content=card.candidate_content,
            candidate_trigger=card.candidate_trigger,
            positive_examples=card.positive_examples,
            negative_examples=card.negative_examples,
            supporting_memory_refs=card.supporting_memory_refs,
            contradicting_examples=card.contradicting_examples,
            overlapping_skill_ids=card.overlapping_skill_ids,
            overlap_type=card.overlap_type,
            is_system_prompt_knowledge=card.is_system_prompt_knowledge,
            system_prompt_evidence=card.system_prompt_evidence,
            evidence_support_score=card.evidence_support_score,
            negative_case_score=card.negative_case_score,
            cross_run_support_score=card.cross_run_support_score,
            novelty_score=card.novelty_score,
            execution_clarity_score=card.execution_clarity_score,
            overlap_penalty=card.overlap_penalty,
            common_knowledge_penalty=card.common_knowledge_penalty,
            decision=decision,
            source_run_id=run_id,
        )
        evidence_cards.append(card)

        if decision == "confirmed":
            trigger_data = candidate.get("trigger", {})
            skill = Skill(
                name=candidate.get("name", ""),
                category=candidate.get("category", "general"),
                trigger=SkillTrigger.from_dict(trigger_data) if trigger_data else SkillTrigger(),
                tier=candidate.get("tier", "specific"),
                content=candidate.get("content", ""),
                lessons=candidate.get("lessons", ""),
                examples=tuple(candidate.get("examples", ())),
                priority=60,
                source="discovered",
                source_run_ids=(run_id,),
                confidence=0.5,
                verified=False,
            )
            confirmed_skills.append(skill)
            logger.info("CONFIRMED: %s (score=%.1f)", candidate.get("name"), card.candidacy_score)
        elif decision == "candidate":
            hypothesis_store.save(card)
            logger.info("HYPOTHESIS: %s (score=%.1f)", candidate.get("name"), card.candidacy_score)
        else:
            logger.info("REJECTED: %s (score=%.1f)", candidate.get("name"), card.candidacy_score)

    return confirmed_skills, evidence_cards


def _parse_discovered_candidates(raw_text: str) -> list[dict]:
    """Parse LLM response into candidate dicts (not Skill objects yet)."""
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        logger.warning("Skill discovery: no JSON array found")
        return []

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        logger.warning("Skill discovery: invalid JSON: %s", e)
        return []

    if not isinstance(data, list):
        return []

    result = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name", "")
        content = item.get("content", "")
        if not name or not content:
            continue
        if len(content) > 400:
            logger.info("Candidate '%s' content too long (%d > 400), skipping", name, len(content))
            continue
        result.append(item)

    return result
```

- [ ] **Step 2: Update loop.py — BOTH sync and batch paths**

**Sync path** in `_post_run_skill_update()` (around line 2301-2308):

```python
            if should_discover:
                from src.skills.discovery import discover_skills

                existing = list(self._skill_library.all_skills)
                combat_st = self._memory.combat_store if self._memory else None
                new_skills, _evidence = await discover_skills(
                    self._run_state,
                    existing_skills=existing,
                    combat_store=combat_st,
                )
                self._skill_run_count = 0
                self._save_counter("skill_discovery", 0)
                if new_skills:
                    added = self._skill_library.add_batch(new_skills)
                    if added > 0:
                        logger.info("Discovered %d new skills (evidence-gated)", added)
                        self._skill_library.save(skill_path)
                if evidence_cards:
                    logger.info(
                        "Evidence cards: %d confirmed, %d hypothesis, %d rejected",
                        sum(1 for c in evidence_cards if c.decision == "confirmed"),
                        sum(1 for c in evidence_cards if c.decision == "candidate"),
                        sum(1 for c in evidence_cards if c.decision == "rejected"),
                    )
```

**Batch result processing path** (around line ~2082 in loop.py). This path currently does:

```python
from src.skills.discovery import _parse_discovered_skills
skills = _parse_discovered_skills(raw_text, task["run_id"])
```

Replace with:

```python
from src.skills.discovery import _parse_discovered_candidates, gate_candidates
candidates = _parse_discovered_candidates(raw_text)
combat_st = self._memory.combat_store if self._memory else None
existing = list(self._skill_library.all_skills)
new_skills, evidence_cards = gate_candidates(
    candidates=candidates,
    run_id=task["run_id"],
    combat_store=combat_st,
    existing_skills=existing,
)
# Replace old: self._skill_library.add_batch(skills)
```

This ensures batch-discovered candidates go through the same evidence gate as sync-discovered ones. The `gate_candidates()` function handles hypothesis saving and rejection logging internally.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/skills/discovery.py src/agent/loop.py
git commit -m "feat: wire evidence-gated pipeline into skill discovery"
```

---

### Task 6: Integration Test

**Files:**
- Add to: `tests/test_evidence.py`

- [ ] **Step 1: Add integration test for full pipeline**

Append to `tests/test_evidence.py`:

```python
class TestFullPipeline:
    """Integration test: candidate → evidence → score → classify."""

    def test_single_positive_no_negative_rejected(self):
        """1 positive + 0 negative → score ~1.8 < HYPOTHESIS_THRESHOLD (2.0) → rejected.

        This tests the conservative design: a single observation from one run
        is NOT enough to even become a hypothesis without any negative evidence.
        """
        pos = [RoundExemplar(
            episode_id="ep1", run_id="r1", enemy_key="Nibbit",
            round_num=3, threat_level="high", intent_class="attack",
            damage_taken=3, outcome_quality="clean", tag_source="runtime",
        )]
        card = score_evidence(
            candidate={
                "name": "Nibbit_R3_weak_first",
                "content": "When facing Nibbit at high-threat attack round, apply Weak before Block",
                "trigger": {"enemy_names": ["Nibbit"], "threat_levels": ["high"]},
            },
            positive=pos,
            negative=[],
            cross_run_refs=[],
            contradictions=[],
            overlap_skills=[],
            existing_skills=[],
        )
        # evidence=0.3*2 + negative=0 + cross_run=0 + novelty=0.8 + exec=0.8*0.5 = 1.8
        assert card.candidacy_score < HYPOTHESIS_THRESHOLD
        assert classify_candidate(card) == "rejected"

    def test_positive_plus_negative_becomes_hypothesis(self):
        """1 positive + 1 negative → score ~2.55 → hypothesis."""
        pos = [RoundExemplar(
            episode_id="ep1", run_id="r1", tag_source="runtime",
        )]
        neg = [RoundExemplar(
            episode_id="ep2", run_id="r1", tag_source="runtime",
        )]
        card = score_evidence(
            candidate={
                "name": "test_hypothesis",
                "content": "When facing Nibbit at high threat, first apply Weak then Block",
                "trigger": {"enemy_names": ["Nibbit"], "threat_levels": ["high"]},
            },
            positive=pos,
            negative=neg,
            cross_run_refs=[],
            contradictions=[],
            overlap_skills=[],
            existing_skills=[],
        )
        # evidence=0.3*2 + negative=0.3*1.5 + novelty=0.8 + exec=0.8*0.5 = 2.55
        assert HYPOTHESIS_THRESHOLD <= card.candidacy_score < CONFIRMED_THRESHOLD
        assert classify_candidate(card) == "candidate"

    def test_strong_contrastive_evidence_confirmed(self):
        """Strong positive + negative + runtime → confirmed."""
        pos = [
            RoundExemplar(tag_source="runtime", run_id="r1"),
            RoundExemplar(tag_source="runtime", run_id="r1"),
            RoundExemplar(tag_source="runtime", run_id="r2"),
        ]
        neg = [
            RoundExemplar(tag_source="runtime", run_id="r1"),
            RoundExemplar(tag_source="runtime", run_id="r2"),
        ]
        card = score_evidence(
            candidate={
                "name": "test_strong",
                "content": "When facing Nibbit at high threat, first apply Weak then Block",
                "trigger": {"enemy_names": ["Nibbit"], "threat_levels": ["high"]},
            },
            positive=pos,
            negative=neg,
            cross_run_refs=["old_ep1", "old_ep2"],
            contradictions=[],
            overlap_skills=[],
            existing_skills=[],
        )
        decision = classify_candidate(card)
        assert decision == "confirmed"
        assert card.candidacy_score >= CONFIRMED_THRESHOLD
```

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/test_dedup.py tests/test_evidence.py -v`
Expected: All PASS

- [ ] **Step 3: Run full suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_evidence.py
git commit -m "test: add integration tests for evidence-gated discovery pipeline"
```

---

## Self-Review

**Spec coverage check:**
- 17.3 Three-tier output: ✅ Task 3 (classify_candidate → confirmed/candidate/rejected)
- 17.4 Evidence models: ✅ Task 3 (SkillEvidenceCard, RoundExemplar with tag_source)
- 17.5 Evidence pipeline: ✅ Task 3 (is_valid_evidence_round, score_evidence) + Task 5 (gate_candidates shared function)
- 17.5 Step 4 Classification gate: ✅ Task 3 (classify_candidate with provenance gate)
- 17.6 Evidence minimum: ✅ Built into scoring thresholds
- 17.7 Semantic dedup: ✅ Task 2 (content_overlap, trigger_overlap, is_semantic_duplicate). Note: trigger_overlap limited to state_types/enemy_names/tags — threat_levels/intent_classes deferred to Phase 2 when SkillTrigger gains these fields.
- 17.8 Common knowledge: ✅ Task 2 (common_knowledge_score with trigger specificity, returns matched concept name for audit)
- 17.9 Rejection cases: ✅ Covered by classification gate tests
- 17.10 Hypothesis lifecycle: Hypothesis store created (Task 4), re-evaluation deferred to Phase 2.5 as scoped
- 17.12 Integration: ✅ Task 5 (gate_candidates shared by sync + batch paths in loop.py)
- Provenance weighting: ✅ Built into scoring (_PROVENANCE_WEIGHT) + classification gate (has_runtime_evidence)
- Rule overlap (overlapping_rule_ids): ❌ Explicitly deferred — rules are free-text without structured triggers

**Codex review fixes applied:**
- CRITICAL #1: Added `gate_candidates()` shared function, batch path updated to call it instead of deleted `_parse_discovered_skills`
- CRITICAL #2: Removed `collect_evidence()` from file structure table, replaced with `score_evidence()` and `gate_candidates()`
- HIGH #3: Explicitly documented that `_DISCOVERY_SYSTEM`, `_format_decisions`, `_format_existing_skills` are retained unchanged
- HIGH #4: Documented trigger_overlap limitation in scope boundary section
- HIGH #5: Removed `rule_store` param from `discover_skills` (deferred to Phase 2.5)
- HIGH #6: Documented prompt field removal as intentional in scope boundary section
- MEDIUM #7: Renamed misleading test, added new `test_positive_plus_negative_becomes_hypothesis` for the hypothesis path
- MEDIUM #8: Documented `candidate_trigger: dict` as shallow-frozen (matches existing project pattern)
- LOW #10: `common_knowledge_score` now returns matched concept name; `system_prompt_evidence` populated in evidence card
- LOW #11: Explicitly stated helper retention in Task 5

**Placeholder scan:** No TBDs found. All steps have code.

**Type consistency:** `discover_skills` returns `tuple[list[Skill], list[SkillEvidenceCard]]`. `gate_candidates` returns same type. Batch path calls `gate_candidates` directly. `score_evidence` returns `SkillEvidenceCard`. `common_knowledge_score` returns `tuple[float, str]`. All consistent.
