"""Tests for src/memory/write_gate_lifecycle.py (Pareto / prune / history)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.memory.write_gate_lifecycle import (
    PARETO_SLOT_K,
    PRUNE_MIN_USE_COUNT,
    PRUNE_SCORE_THRESHOLD,
    CohortEntry,
    PareReplaceDecision,
    ProposalHistoryEntry,
    PruneDecision,
    evaluate_pareto_admission,
    evaluate_prune,
    format_proposal_history,
    group_by_cohort,
    lifecycle_score,
    pareto_frontier,
    read_recent_proposals,
)


# ── lifecycle_score ────────────────────────────────────────────────


class TestLifecycleScore:
    def test_neutral_at_no_data(self):
        e = CohortEntry(id="x", cohort_key=("c",), confidence=0.5)
        assert lifecycle_score(e) == pytest.approx(0.5)

    def test_perfect_run(self):
        e = CohortEntry(id="x", cohort_key=("c",), confidence=0.9,
                        usage_count=10, success_count=10)
        # (10+1)/(10+2) = 0.917
        assert lifecycle_score(e) == pytest.approx(11 / 12)

    def test_total_failure(self):
        e = CohortEntry(id="x", cohort_key=("c",), confidence=0.1,
                        usage_count=10, success_count=0)
        assert lifecycle_score(e) == pytest.approx(1 / 12)


# ── group_by_cohort & pareto_frontier ──────────────────────────────


def _entry(id_: str, cohort: tuple[str, ...], succ: int = 1, use: int = 2) -> CohortEntry:
    return CohortEntry(
        id=id_, cohort_key=cohort, confidence=0.5,
        usage_count=use, success_count=succ,
    )


class TestPareto:
    def test_group_by_cohort(self):
        es = [
            _entry("a", ("char1", "combat", "early")),
            _entry("b", ("char1", "combat", "early")),
            _entry("c", ("char1", "combat", "late")),
        ]
        groups = group_by_cohort(es)
        assert len(groups) == 2
        assert {e.id for e in groups[("char1", "combat", "early")]} == {"a", "b"}

    def test_pareto_frontier_keeps_top_k(self):
        es = [
            _entry("low", ("c",), succ=0, use=10),    # score ≈ 0.083
            _entry("mid1", ("c",), succ=4, use=10),   # score ≈ 0.417
            _entry("mid2", ("c",), succ=5, use=10),   # score ≈ 0.5
            _entry("high", ("c",), succ=9, use=10),   # score ≈ 0.833
        ]
        front = pareto_frontier(es, k=3)
        ids = [e.id for e in front[("c",)]]
        assert ids == ["high", "mid2", "mid1"]
        assert "low" not in ids


# ── evaluate_pareto_admission ──────────────────────────────────────


class TestParetoAdmission:
    def test_accept_when_room(self):
        cand = _entry("new", ("c",))
        existing = [_entry("a", ("c",))]
        d = evaluate_pareto_admission(cand, existing, k=3)
        assert d.action == "accept"
        assert d.displaced_id is None

    def test_displace_weaker(self):
        cand = _entry("new", ("c",), succ=10, use=10)  # ≈ 0.917
        existing = [
            _entry("a", ("c",), succ=9, use=10),   # ≈ 0.833
            _entry("b", ("c",), succ=8, use=10),   # ≈ 0.75
            _entry("c", ("c",), succ=2, use=10),   # ≈ 0.25 (weakest)
        ]
        d = evaluate_pareto_admission(cand, existing, k=3)
        assert d.action == "displace"
        assert d.displaced_id == "c"

    def test_reject_when_full_and_no_better(self):
        cand = _entry("new", ("c",), succ=1, use=10)  # ≈ 0.167
        existing = [
            _entry("a", ("c",), succ=9, use=10),
            _entry("b", ("c",), succ=8, use=10),
            _entry("c", ("c",), succ=5, use=10),
        ]
        d = evaluate_pareto_admission(cand, existing, k=3)
        assert d.action == "reject"

    def test_tie_goes_to_existing(self):
        cand = _entry("new", ("c",), succ=5, use=10)  # ≈ 0.5
        existing = [
            _entry("a", ("c",), succ=9, use=10),
            _entry("b", ("c",), succ=8, use=10),
            _entry("c", ("c",), succ=5, use=10),  # same score as cand
        ]
        d = evaluate_pareto_admission(cand, existing, k=3)
        assert d.action == "reject"


# ── evaluate_prune ─────────────────────────────────────────────────


class TestPrune:
    def test_demotes_low_score_with_enough_usage(self):
        es = [_entry("loser", ("c",), succ=0, use=15)]  # score ≈ 0.06
        out = evaluate_prune(es)
        assert len(out) == 1
        assert out[0].action == "demote"
        assert out[0].score < PRUNE_SCORE_THRESHOLD
        assert out[0].usage_count >= PRUNE_MIN_USE_COUNT

    def test_keeps_low_score_with_low_usage(self):
        # Score might be low but usage too small to be sure.
        es = [_entry("newbie", ("c",), succ=0, use=2)]  # score ≈ 0.25
        out = evaluate_prune(es)
        assert out[0].action == "keep"

    def test_keeps_high_score(self):
        es = [_entry("winner", ("c",), succ=10, use=10)]
        out = evaluate_prune(es)
        assert out[0].action == "keep"


# ── proposal history ──────────────────────────────────────────────


class TestProposalHistory:
    def test_read_missing_file(self, tmp_path: Path):
        out = read_recent_proposals(tmp_path / "nope.jsonl")
        assert out == []

    def test_reads_last_n(self, tmp_path: Path):
        log = tmp_path / "g.jsonl"
        rows = [
            {"name": f"s{i}", "kind": "skill", "target_layer": "L5",
             "action": "accept", "reason": "ok"}
            for i in range(50)
        ]
        log.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        out = read_recent_proposals(log, window=20)
        assert len(out) == 20
        # Window is the LAST 20 → s30..s49
        assert out[0].name == "s30"
        assert out[-1].name == "s49"

    def test_skips_malformed_rows(self, tmp_path: Path):
        log = tmp_path / "g.jsonl"
        log.write_text(
            "\n".join([
                json.dumps({"name": "s0", "action": "accept"}),
                "{not valid json",
                json.dumps({"name": "s1", "action": "reject"}),
            ]),
            encoding="utf-8",
        )
        out = read_recent_proposals(log, window=10)
        assert [e.name for e in out] == ["s0", "s1"]

    def test_format_empty_returns_empty_string(self):
        assert format_proposal_history([]) == ""

    def test_format_compact_table(self):
        es = [
            ProposalHistoryEntry(name="s0", kind="skill", target_layer="L5",
                                 action="accept", reason="below_all"),
            ProposalHistoryEntry(name="s1", kind="skill", target_layer="L5",
                                 action="reject", reason="l1_overlap:..."),
        ]
        out = format_proposal_history(es)
        assert "s0" in out
        assert "[accept]" in out
        assert "[reject]" in out
        assert "## Recent Write-Gate Decisions" in out
