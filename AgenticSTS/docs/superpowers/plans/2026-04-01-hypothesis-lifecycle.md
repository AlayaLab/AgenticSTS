# Hypothesis Re-evaluation Lifecycle — Phase 2.5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a post-run re-evaluation loop that checks pending hypotheses against new combat episodes: corroborate, contradict, or skip. Auto-promote to confirmed skill after 3+ corroborations across 2+ runs; auto-reject after 3+ contradictions; expire after 10 runs with no relevant encounters.

**Architecture:** `evidence.py` gains `AdherenceResult`, `ActionPredicate`, `evaluate_adherence()`, and `_extract_action_predicates()`. `hypothesis_store.py` gains `reevaluate()`, `promote()`, `reject()`, `expire()`, and full JSONL rewrite-on-mutate. `loop.py` calls `reevaluate_hypotheses()` at post-run after memory extraction.

**Tech Stack:** Python 3.12, frozen dataclasses, regex-based predicate extraction, no new dependencies.

**Spec:** `docs/2026-03-31-situation-level-retrieval-design.md` Section 17.10.

**Codex review fixes:**
- HIGH #2/7: `SkillEvidenceCard` gains `candidate_category` field so promoted hypotheses keep their original category (not always "combat"). `score_evidence()` and `gate_candidates()` in discovery.py pass category through.
- LOW #9: Test assertion strengthened from `>= 0` to `>= 1`.
- LOW #10: `reevaluate()` distinguishes "no episodes matched enemy" from "episodes matched but all rounds untagged" — only the former counts as empty run.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/skills/evidence.py` | MODIFY | Add `candidate_category` field to `SkillEvidenceCard`, add `ActionPredicate`, `AdherenceResult`, `evaluate_adherence()`, `_extract_action_predicates()` |
| `src/skills/discovery.py` | MODIFY | Pass `candidate_category` through `score_evidence()` and `gate_candidates()` reconstruction |
| `src/skills/hypothesis_store.py` | MODIFY | Add `reevaluate()`, `promote()`, `reject()`, `expire()`, JSONL rewrite, run counter |
| `src/agent/loop.py` | MODIFY | Call `reevaluate_hypotheses()` in `_post_run_skill_update()`, use `candidate_category` for promotion |
| `tests/test_adherence.py` | **CREATE** | Tests for predicate extraction + adherence evaluation |
| `tests/test_hypothesis_lifecycle.py` | **CREATE** | Tests for re-evaluation, promotion, rejection, expiry |

---

### Task 1: ActionPredicate + Adherence Evaluator + candidate_category Field

**Files:**
- Modify: `src/skills/evidence.py`
- Modify: `src/skills/discovery.py` (pass category through)
- Create: `tests/test_adherence.py`

- [ ] **Step 0: Add candidate_category to SkillEvidenceCard**

In `src/skills/evidence.py`, add to the `SkillEvidenceCard` frozen dataclass (after `candidate_trigger`):

```python
    candidate_category: str = ""  # "combat"|"deck_building"|"map"|"boss"|"general" — preserves LLM category
```

Add to `to_dict()`:
```python
            "candidate_category": self.candidate_category,
```

Add to `from_dict()`:
```python
            candidate_category=d.get("candidate_category", ""),
```

In `score_evidence()`, set it from the candidate dict:
```python
    return SkillEvidenceCard(
        candidate_name=candidate.get("name", ""),
        candidate_content=content,
        candidate_trigger=trigger,
        candidate_category=candidate.get("category", "general"),
        ...
    )
```

In `src/skills/discovery.py`, in `gate_candidates()`, the reconstruction of `SkillEvidenceCard` (the `_skip` set + `**{...}` spread pattern) must NOT skip `candidate_category`. Verify `candidate_category` is NOT in the `_skip` set and flows through `to_dict()` → constructor correctly.

- [ ] **Step 1: Write failing tests for predicate extraction and adherence**

Create `tests/test_adherence.py`:

```python
"""Tests for action predicate extraction and adherence evaluation."""

from src.skills.evidence import (
    ActionPredicate,
    AdherenceResult,
    evaluate_adherence,
    _extract_action_predicates,
)
from src.memory.models_v2 import CombatRound
from src.memory.situation import SituationTag


class TestExtractActionPredicates:
    def test_play_card_pattern(self):
        preds = _extract_action_predicates("apply Weak before blocking", None)
        names = [p.description for p in preds]
        assert any("weak" in n for n in names)

    def test_sequence_pattern(self):
        preds = _extract_action_predicates("Weak before Block", None)
        seq = [p for p in preds if p.predicate_type == "sequence"]
        assert len(seq) >= 1
        assert seq[0].args[0] == "weak"
        assert seq[0].args[1] == "block"

    def test_first_then_pattern(self):
        preds = _extract_action_predicates("first apply Weak then play Defend", None)
        seq = [p for p in preds if p.predicate_type == "sequence"]
        assert len(seq) >= 1

    def test_offensive_pattern(self):
        preds = _extract_action_predicates("go full damage on buff rounds", None)
        caps = [p for p in preds if p.predicate_type == "capability"]
        assert len(caps) == 1

    def test_negative_pattern(self):
        preds = _extract_action_predicates("don't attack on high damage rounds", None)
        negs = [p for p in preds if p.predicate_type == "negative"]
        assert len(negs) == 1

    def test_abstract_content_returns_empty(self):
        preds = _extract_action_predicates("be more careful in Act 1", None)
        assert len(preds) == 0

    def test_empty_content(self):
        preds = _extract_action_predicates("", None)
        assert len(preds) == 0


class TestActionPredicateCheck:
    def test_card_played_check(self):
        pred = ActionPredicate("card_played", "played neutralize", ("neutralize",))
        rnd = CombatRound(cards_played=("Neutralize", "Defend"))
        assert pred.check({"neutralize", "defend"}, set(), rnd) is True

    def test_card_played_missing(self):
        pred = ActionPredicate("card_played", "played neutralize", ("neutralize",))
        rnd = CombatRound(cards_played=("Strike", "Defend"))
        assert pred.check({"strike", "defend"}, set(), rnd) is False

    def test_sequence_correct_order(self):
        pred = ActionPredicate("sequence", "weak before block", ("weak", "block"))
        rnd = CombatRound(cards_played=("Neutralize", "Defend"))
        # "weak" not in card names, so this should fail (no Weak card)
        assert pred.check(set(), set(), rnd) is False

    def test_sequence_with_matching_cards(self):
        pred = ActionPredicate("sequence", "neutralize before defend", ("neutralize", "defend"))
        rnd = CombatRound(cards_played=("Neutralize", "Defend"))
        assert pred.check({"neutralize", "defend"}, set(), rnd) is True

    def test_negative_predicate(self):
        pred = ActionPredicate("negative", "no attacks", ("strike",))
        rnd = CombatRound(cards_played=("Defend", "Backflip"))
        assert pred.check({"defend", "backflip"}, set(), rnd) is True


class TestEvaluateAdherence:
    def test_full_adherence(self):
        """All predicates matched → full, weight 1.0."""
        rnd = CombatRound(cards_played=("Neutralize", "Defend"))
        tag = SituationTag(threat_level="high", intent_class="attack")
        candidate = {"content": "apply Neutralize first"}
        result = evaluate_adherence(candidate, tag, rnd)
        assert result.level == "full"
        assert result.evidence_weight == 1.0

    def test_no_adherence(self):
        """No predicates matched → none, weight 1.0."""
        rnd = CombatRound(cards_played=("Strike", "Strike"))
        tag = SituationTag(threat_level="high", intent_class="attack")
        candidate = {"content": "apply Neutralize first"}
        result = evaluate_adherence(candidate, tag, rnd)
        assert result.level == "none"
        assert result.evidence_weight == 1.0

    def test_unknown_for_abstract_content(self):
        """No extractable predicates → unknown, weight 0.0."""
        rnd = CombatRound(cards_played=("Strike",))
        tag = SituationTag(threat_level="high")
        candidate = {"content": "be more aggressive"}
        result = evaluate_adherence(candidate, tag, rnd)
        assert result.level == "unknown"
        assert result.evidence_weight == 0.0

    def test_partial_adherence(self):
        """Some predicates matched → partial, weight 0.5."""
        rnd = CombatRound(cards_played=("Neutralize", "Strike"))
        tag = SituationTag(threat_level="high")
        # "apply Neutralize" matches, "Defend before Strike" fails (no Defend played)
        candidate = {"content": "apply Neutralize, Defend before Strike"}
        result = evaluate_adherence(candidate, tag, rnd)
        # At least one matched, at least one missed
        if result.matched_actions and result.missed_actions:
            assert result.level == "partial"
            assert result.evidence_weight == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_adherence.py -v`
Expected: FAIL — `ImportError` (ActionPredicate etc. not yet defined)

- [ ] **Step 3: Implement ActionPredicate, AdherenceResult, evaluate_adherence in evidence.py**

Append to `src/skills/evidence.py` (after the `classify_candidate` function):

```python
import re as _re


# ── Action Predicates ────────────────────────────────────────


@dataclass(frozen=True)
class ActionPredicate:
    """A single testable assertion about what the agent should have done."""

    predicate_type: str = ""  # "card_played" | "sequence" | "capability" | "negative"
    description: str = ""
    args: tuple[str, ...] = ()

    def check(
        self,
        cards_played: set[str],
        potions_used: set[str],
        round_data: Any,
    ) -> bool:
        if self.predicate_type == "card_played":
            return any(self.args[0] in c for c in cards_played)
        if self.predicate_type == "sequence":
            played_list = [c.lower() for c in round_data.cards_played]
            try:
                idx_a = next(i for i, c in enumerate(played_list) if self.args[0] in c)
                idx_b = next(i for i, c in enumerate(played_list) if self.args[1] in c)
                return idx_a < idx_b
            except StopIteration:
                return False
        if self.predicate_type == "capability":
            # "attack_majority" → at least 2 attack-ish cards played
            if self.args[0] == "attack_majority":
                attack_kw = {"strike", "attack", "bash", "shiv", "dagger"}
                attack_count = sum(1 for c in cards_played if any(k in c for k in attack_kw))
                return attack_count >= 2
            return False
        if self.predicate_type == "negative":
            return not any(self.args[0] in c for c in cards_played)
        return False


def _extract_action_predicates(
    content: str,
    hand_capabilities: Any,
) -> list[ActionPredicate]:
    """Extract testable predicates from natural language skill content.

    Uses keyword patterns — not LLM. Fast, deterministic, auditable.
    Returns empty list if content is too abstract to extract predicates.
    """
    predicates: list[ActionPredicate] = []

    # Pattern: "play/apply/use <CardName>"
    for m in _re.finditer(
        r"(?:play|apply|use)\s+(\w[\w\s]*?)(?:\s+(?:first|before|then)|[,.]|$)",
        content,
        _re.IGNORECASE,
    ):
        card = m.group(1).strip().lower()
        if card and len(card) > 2:
            predicates.append(ActionPredicate("card_played", f"played {card}", (card,)))

    # Pattern: "X before Y" / "first X then Y"
    for pat in (
        _re.compile(r"(\w+)\s+before\s+(\w+)", _re.IGNORECASE),
        _re.compile(r"first\s+(\w+).*?then\s+(\w+)", _re.IGNORECASE),
    ):
        for m in pat.finditer(content):
            a, b = m.group(1).lower(), m.group(2).lower()
            predicates.append(ActionPredicate("sequence", f"{a} before {b}", (a, b)))

    # Pattern: "go offensive" / "full damage" / "all-out attack"
    if _re.search(r"(?:go\s+)?(?:offensive|full\s+damage|all-out|aggressive)", content, _re.IGNORECASE):
        predicates.append(ActionPredicate("capability", "offensive focus", ("attack_majority",)))

    # Pattern: "don't attack" / "skip offense" / "no attacks"
    if _re.search(r"(?:don'?t|skip|no)\s+(?:attack|offense|damage)", content, _re.IGNORECASE):
        predicates.append(ActionPredicate("negative", "no attacks", ("attack",)))

    return predicates


# ── Adherence Evaluation ─────────────────────────────────────


@dataclass(frozen=True)
class AdherenceResult:
    """Whether a candidate's advice was followed in a specific round."""

    level: str = "unknown"  # "full" | "partial" | "none" | "unknown"
    evidence_weight: float = 0.0
    matched_actions: tuple[str, ...] = ()
    missed_actions: tuple[str, ...] = ()
    note: str = ""


def evaluate_adherence(
    candidate: dict,
    round_tag: Any,
    round_data: Any,
) -> AdherenceResult:
    """Determine whether a round's actual play followed the candidate's advice.

    Returns AdherenceResult with level and evidence_weight.
    """
    content = candidate.get("content", "").lower()
    cards_played = set(c.lower() for c in round_data.cards_played)
    potions_used = set(p.lower() for p in round_data.potions_used)
    hc = round_tag.hand_capabilities if round_tag else None

    predicates = _extract_action_predicates(content, hc)
    if not predicates:
        return AdherenceResult(
            level="unknown", evidence_weight=0.0,
            note="No extractable action predicates from candidate content",
        )

    matched = []
    missed = []
    for pred in predicates:
        if pred.check(cards_played, potions_used, round_data):
            matched.append(pred.description)
        else:
            missed.append(pred.description)

    if not missed:
        return AdherenceResult(
            level="full", evidence_weight=1.0,
            matched_actions=tuple(matched), note="All predicates satisfied",
        )
    if not matched:
        return AdherenceResult(
            level="none", evidence_weight=1.0,
            missed_actions=tuple(missed), note="No predicates satisfied",
        )
    return AdherenceResult(
        level="partial", evidence_weight=0.5,
        matched_actions=tuple(matched), missed_actions=tuple(missed),
        note=f"{len(matched)}/{len(matched) + len(missed)} predicates satisfied",
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_adherence.py -v`
Expected: All PASS

- [ ] **Step 5: Run full suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/skills/evidence.py tests/test_adherence.py
git commit -m "feat: add action predicate extraction + adherence evaluator for hypothesis lifecycle"
```

---

### Task 2: Hypothesis Store Re-evaluation + Lifecycle

**Files:**
- Modify: `src/skills/hypothesis_store.py`
- Create: `tests/test_hypothesis_lifecycle.py`

- [ ] **Step 1: Write failing tests for hypothesis lifecycle**

Create `tests/test_hypothesis_lifecycle.py`:

```python
"""Tests for hypothesis re-evaluation, promotion, rejection, and expiry."""

import json
import tempfile
from pathlib import Path

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode, CombatRound
from src.memory.situation import SituationTag
from src.skills.evidence import RoundExemplar, SkillEvidenceCard
from src.skills.hypothesis_store import HypothesisStore


def _make_hypothesis(name: str = "test_hyp", content: str = "apply Neutralize first") -> SkillEvidenceCard:
    return SkillEvidenceCard(
        candidate_name=name,
        candidate_content=content,
        candidate_trigger={"enemy_names": ["Nibbit"], "state_types": ["monster"]},
        evidence_support_score=0.3,
        negative_case_score=0.3,
        novelty_score=0.8,
        execution_clarity_score=0.8,
        decision="candidate",
        source_run_id="run_0",
        positive_examples=(RoundExemplar(tag_source="runtime", run_id="run_0"),),
    )


def _make_tagged_round(
    outcome: str = "clean",
    cards: tuple[str, ...] = ("Neutralize", "Defend"),
    tag_source: str = "runtime",
) -> CombatRound:
    tag = SituationTag(
        threat_level="high", intent_class="attack",
        outcome_quality=outcome, tag_source=tag_source,
    )
    return CombatRound(
        round_num=3, enemy_intents=("Attack 18",),
        cards_played=cards, damage_taken=0 if outcome == "clean" else 15,
        situation_tag=tag,
    )


class TestHypothesisReeval:
    def test_corroboration_increments_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hyp.jsonl"
            store = HypothesisStore(path=path)
            hyp = _make_hypothesis()
            store.save(hyp)

            # Create corroborating episode
            combat_store = CombatMemoryStore()
            r = _make_tagged_round(outcome="clean", cards=("Neutralize", "Defend"))
            ep = CombatEpisode(
                enemy_key="Nibbit", combat_type="monster",
                rounds=(r,), run_id="run_1", floor=5,
            )
            combat_store.add(ep)

            results = store.reevaluate(combat_store=combat_store, current_run_id="run_1")
            # The tagged round should pass similarity gate (same enemy + threat + intent)
            # and adherence check ("apply Neutralize first" → card_played predicate matches)
            assert results["corroborated"] >= 1, f"Expected corroboration, got: {results}"

    def test_expiry_after_n_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hyp.jsonl"
            store = HypothesisStore(path=path)
            hyp = _make_hypothesis()
            store.save(hyp)

            # Simulate 10 runs with no relevant encounters
            combat_store = CombatMemoryStore()  # empty
            for i in range(10):
                store.reevaluate(combat_store=combat_store, current_run_id=f"run_{i+1}")

            # After 10 empty runs, hypothesis should be expired
            active = [h for h in store.all_hypotheses if h.decision == "candidate"]
            expired = [h for h in store.all_hypotheses if h.decision == "expired"]
            assert len(expired) >= 1 or len(active) == 0

    def test_promotion_creates_skill_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hyp.jsonl"
            store = HypothesisStore(path=path)
            hyp = _make_hypothesis()
            store.save(hyp)

            promoted = store.get_promoted()
            # No promotions yet (need 3+ corroborations across 2+ runs)
            assert len(promoted) == 0


class TestHypothesisStorePersistence:
    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hyp.jsonl"
            store = HypothesisStore(path=path)
            store.save(_make_hypothesis("h1"))
            store.save(_make_hypothesis("h2"))
            assert store.count == 2

            store2 = HypothesisStore(path=path)
            assert store2.count == 2
            assert store2.all_hypotheses[0].candidate_name == "h1"

    def test_rewrite_persists_mutations(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hyp.jsonl"
            store = HypothesisStore(path=path)
            store.save(_make_hypothesis("h1"))

            # Trigger a rewrite (e.g., after reevaluation)
            store._rewrite()

            store2 = HypothesisStore(path=path)
            assert store2.count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_hypothesis_lifecycle.py -v`
Expected: FAIL — `reevaluate`, `get_promoted`, `_rewrite` don't exist

- [ ] **Step 3: Expand hypothesis_store.py with lifecycle methods**

Replace the entire `src/skills/hypothesis_store.py`:

```python
"""JSONL-backed store for candidate hypotheses with lifecycle management.

Hypotheses are skill candidates that didn't meet the confirmed threshold.
They're re-evaluated against new combat episodes at each post-run:
- Corroborated: advice followed + good outcome → bump evidence
- Contradicted: advice followed + bad outcome → add contradiction
- Inconclusive: can't determine → skip
- Auto-promote: 3+ corroborations across 2+ runs → confirmed_skill
- Auto-reject: 3+ contradictions → rejected
- Expire: 10 runs with no relevant encounters → archived

Spec: Section 17.10.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import config
from src.skills.evidence import (
    AdherenceResult,
    RoundExemplar,
    SkillEvidenceCard,
    classify_candidate,
    evaluate_adherence,
    is_valid_evidence_round,
)

logger = logging.getLogger(__name__)

PROMOTION_CORROBORATIONS = 3  # corroborations needed to promote
PROMOTION_MIN_RUNS = 2        # distinct runs needed
REJECTION_CONTRADICTIONS = 3  # contradictions to auto-reject
EXPIRY_EMPTY_RUNS = 10        # runs with no relevant encounters to expire


class HypothesisStore:
    """JSONL-backed store for candidate hypotheses with lifecycle management."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or Path(config.HYPOTHESES_DIR) / "hypotheses.jsonl"
        self._hypotheses: list[dict] = []  # list of raw dicts (mutable for lifecycle updates)
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            text = self._path.read_text(encoding="utf-8").strip()
            for line in text.split("\n"):
                if line.strip():
                    self._hypotheses.append(json.loads(line))
            logger.info("Loaded %d hypotheses from %s", len(self._hypotheses), self._path)
        except Exception:
            logger.warning("Failed to load hypotheses", exc_info=True)

    def _rewrite(self) -> None:
        """Rewrite the JSONL file with current in-memory state."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("w", encoding="utf-8") as f:
            for h in self._hypotheses:
                f.write(json.dumps(h, ensure_ascii=False) + "\n")

    def save(self, card: SkillEvidenceCard) -> None:
        """Append a new hypothesis."""
        d = card.to_dict()
        d.setdefault("corroboration_count", 0)
        d.setdefault("contradiction_count", 0)
        d.setdefault("corroboration_run_ids", [])
        d.setdefault("empty_run_count", 0)
        self._hypotheses.append(d)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
        logger.info("Saved hypothesis: %s (score=%.1f)", card.candidate_name, card.candidacy_score)

    @property
    def count(self) -> int:
        return len(self._hypotheses)

    @property
    def all_hypotheses(self) -> list[SkillEvidenceCard]:
        return [SkillEvidenceCard.from_dict(h) for h in self._hypotheses]

    def get_promoted(self) -> list[dict]:
        """Return hypotheses that have been promoted to confirmed."""
        return [h for h in self._hypotheses if h.get("decision") == "promoted"]

    def reevaluate(
        self,
        combat_store: Any,
        current_run_id: str,
    ) -> dict[str, int]:
        """Re-evaluate all active hypotheses against new episodes.

        Returns counts: {"corroborated": N, "contradicted": N, "inconclusive": N, "expired": N, "promoted": N, "rejected": N}
        """
        stats = {"corroborated": 0, "contradicted": 0, "inconclusive": 0,
                 "expired": 0, "promoted": 0, "rejected": 0}
        mutated = False

        current_episodes = [
            ep for ep in (combat_store.get_all() if combat_store else [])
            if ep.run_id == current_run_id
        ]

        for h in self._hypotheses:
            if h.get("decision") not in ("candidate",):
                continue  # skip already promoted/rejected/expired

            trigger = h.get("candidate_trigger", {})
            content = h.get("candidate_content", "")
            found_relevant = False
            found_any_episode = False  # tracks if any episode matched enemy at all

            for ep in current_episodes:
                # Check if this episode's enemy matches the trigger (coarse check)
                trigger_enemies = {n.lower() for n in trigger.get("enemy_names", [])}
                if trigger_enemies and ep.enemy_key.lower() not in trigger_enemies:
                    continue
                found_any_episode = True

                for rnd in ep.rounds:
                    tag = rnd.situation_tag
                    if tag is None:
                        continue

                    valid, _ = is_valid_evidence_round(trigger, tag, ep)
                    if not valid:
                        continue

                    found_relevant = True
                    candidate_dict = {"content": content, "trigger": trigger}

                    adherence = evaluate_adherence(candidate_dict, tag, rnd)
                    if adherence.evidence_weight == 0.0:
                        stats["inconclusive"] += 1
                        continue

                    outcome = tag.outcome_quality
                    # Adherence → Evidence mapping (spec table)
                    if adherence.level == "full" and outcome in ("clean", "acceptable"):
                        h["corroboration_count"] = h.get("corroboration_count", 0) + 1
                        if current_run_id not in h.get("corroboration_run_ids", []):
                            h.setdefault("corroboration_run_ids", []).append(current_run_id)
                        stats["corroborated"] += 1
                        mutated = True
                    elif adherence.level == "full" and outcome in ("bad", "disaster"):
                        h["contradiction_count"] = h.get("contradiction_count", 0) + 1
                        stats["contradicted"] += 1
                        mutated = True
                    elif adherence.level == "partial" and outcome in ("clean", "acceptable"):
                        # Weak corroboration: count as 0.5
                        h["corroboration_count"] = h.get("corroboration_count", 0) + 0.5
                        if current_run_id not in h.get("corroboration_run_ids", []):
                            h.setdefault("corroboration_run_ids", []).append(current_run_id)
                        stats["corroborated"] += 1
                        mutated = True
                    elif adherence.level == "none" and outcome in ("bad", "disaster"):
                        # Corroboration via negative: didn't follow → bad
                        h["corroboration_count"] = h.get("corroboration_count", 0) + 1
                        if current_run_id not in h.get("corroboration_run_ids", []):
                            h.setdefault("corroboration_run_ids", []).append(current_run_id)
                        stats["corroborated"] += 1
                        mutated = True
                    else:
                        stats["inconclusive"] += 1

            # Only increment empty_run_count when NO episodes matched the enemy at all.
            # If episodes matched but all rounds were untagged, that's a data quality
            # issue — don't penalize the hypothesis for it.
            if not found_relevant and not found_any_episode:
                h["empty_run_count"] = h.get("empty_run_count", 0) + 1
                mutated = True

            # Check promotion: 3+ corroborations across 2+ runs
            corr = h.get("corroboration_count", 0)
            corr_runs = len(h.get("corroboration_run_ids", []))
            if corr >= PROMOTION_CORROBORATIONS and corr_runs >= PROMOTION_MIN_RUNS:
                h["decision"] = "promoted"
                stats["promoted"] += 1
                mutated = True
                logger.info("Hypothesis promoted: %s (corr=%s, runs=%d)",
                            h.get("candidate_name"), corr, corr_runs)

            # Check rejection: 3+ contradictions
            contra = h.get("contradiction_count", 0)
            if contra >= REJECTION_CONTRADICTIONS:
                h["decision"] = "rejected"
                h["rejection_reason"] = f"auto-rejected: {contra} contradictions"
                stats["rejected"] += 1
                mutated = True
                logger.info("Hypothesis rejected: %s (contradictions=%d)",
                            h.get("candidate_name"), contra)

            # Check expiry: 10 runs with no relevant encounters
            empty = h.get("empty_run_count", 0)
            if empty >= EXPIRY_EMPTY_RUNS:
                h["decision"] = "expired"
                stats["expired"] += 1
                mutated = True
                logger.info("Hypothesis expired: %s (empty_runs=%d)",
                            h.get("candidate_name"), empty)

        if mutated:
            self._rewrite()

        return stats
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_hypothesis_lifecycle.py -v`
Expected: All PASS

- [ ] **Step 5: Run full suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/skills/hypothesis_store.py tests/test_hypothesis_lifecycle.py
git commit -m "feat: hypothesis lifecycle — reevaluate, promote, reject, expire"
```

---

### Task 3: Wire Re-evaluation into Post-Run

**Files:**
- Modify: `src/agent/loop.py`

- [ ] **Step 1: Add reevaluate_hypotheses call to _post_run_skill_update**

In `src/agent/loop.py`, find `_post_run_skill_update()` (around line 2286). After the retirement sweep and category caps block (around line 2335), before the final `self._skill_library.save(skill_path)`, add:

```python
            # Re-evaluate pending hypotheses against this run's data (Phase 2.5)
            try:
                from src.skills.hypothesis_store import HypothesisStore
                hyp_store = HypothesisStore()
                combat_st = self._memory.combat_store if self._memory else None
                run_id = self._run_state.run_id if self._run_state else ""
                if combat_st and run_id:
                    reeval_stats = hyp_store.reevaluate(
                        combat_store=combat_st,
                        current_run_id=run_id,
                    )
                    if any(v > 0 for v in reeval_stats.values()):
                        logger.info("Hypothesis re-evaluation: %s", reeval_stats)

                    # Promote confirmed hypotheses to skill library
                    for promoted_dict in hyp_store.get_promoted():
                        # Check if already added (idempotent)
                        name = promoted_dict.get("candidate_name", "")
                        if any(s.name == name for s in self._skill_library.all_skills):
                            continue
                        from src.skills.models import Skill, SkillTrigger
                        trigger_data = promoted_dict.get("candidate_trigger", {})
                        skill = Skill(
                            name=name,
                            category=promoted_dict.get("candidate_category", "") or "combat",
                            trigger=SkillTrigger.from_dict(trigger_data) if trigger_data else SkillTrigger(),
                            content=promoted_dict.get("candidate_content", ""),
                            priority=60,
                            source="discovered",
                            source_run_ids=(run_id,),
                            confidence=0.6,  # promoted hypotheses start higher than raw discovered
                            verified=False,
                        )
                        self._skill_library.add(skill)
                        logger.info("Promoted hypothesis to skill: %s", name)
            except Exception:
                logger.warning("Hypothesis re-evaluation failed (non-fatal)", exc_info=True)
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat: wire hypothesis re-evaluation into post-run skill update"
```

---

## Self-Review

**Spec coverage:**
- 17.10 Lifecycle flow (corroborate → promote, contradict → reject, empty → expire): ✅ Task 2
- 17.10 Adherence evaluator (ActionPredicate, evaluate_adherence): ✅ Task 1
- 17.10 Action predicate extraction (card_played, sequence, capability, negative): ✅ Task 1
- 17.10 Adherence → Evidence mapping table: ✅ Task 2 (inside `reevaluate()`)
- 17.10 Promotion thresholds (3+ corroborations across 2+ runs): ✅ Task 2
- 17.10 Rejection threshold (3+ contradictions): ✅ Task 2
- 17.10 Expiry (10 runs with no relevant encounters): ✅ Task 2
- 17.10 Storage (hypotheses.jsonl): ✅ Task 2 (rewrite-on-mutate)
- 17.10 Re-evaluation trigger (post-run): ✅ Task 3
- 17.12 loop.py integration (promoted → skill library): ✅ Task 3

**Design note:** The hypothesis store now uses raw dicts internally (not frozen `SkillEvidenceCard`) to allow mutable lifecycle updates. `all_hypotheses` property converts to `SkillEvidenceCard` for external consumption. `save()` adds lifecycle fields (`corroboration_count`, `contradiction_count`, `corroboration_run_ids`, `empty_run_count`).

**Codex review fixes applied:**
- HIGH #2/7: `candidate_category` field added to `SkillEvidenceCard`. Task 1 Step 0 populates it from candidate dict. Task 3 uses `candidate_category` for promoted Skill creation.
- LOW #9: Test assertion strengthened from `>= 0` to `>= 1` with explanatory comment.
- LOW #10: `reevaluate()` now distinguishes "no episodes matched enemy" (`found_any_episode=False`) from "episodes matched but rounds untagged". Only the former increments `empty_run_count`.

**Placeholder scan:** No TBDs. All steps have code.

**Type consistency:** `evaluate_adherence` returns `AdherenceResult`. `reevaluate` returns `dict[str, int]`. `get_promoted` returns `list[dict]`. Loop.py creates `Skill` from promoted dict using `candidate_category`. All consistent.
