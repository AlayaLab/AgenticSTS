"""Tests for pure helpers in scripts/calibrate_write_gate_thresholds.py."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.calibrate_write_gate_thresholds import (
    DistSummary,
    SkillRow,
    ThresholdRecommendation,
    _flatten_trigger,
    _pair_cosines,
    _trigger_jaccards,
    histogram_lines,
    load_pe_candidates,
    load_skills,
    recommend,
    summarise,
)


# ── summarise ──────────────────────────────────────────────────────


class TestSummarise:
    def test_empty(self):
        s = summarise("x", [])
        assert s.count == 0
        assert s.mean == 0.0
        assert s.p50 == 0.0

    def test_single_value(self):
        s = summarise("x", [0.42])
        assert s.count == 1
        assert s.minv == 0.42
        assert s.maxv == 0.42
        assert s.mean == pytest.approx(0.42)

    def test_uniform_distribution_percentiles(self):
        # 11 values 0..1 step 0.1 → p50=0.5, p90=0.9
        vs = [i / 10.0 for i in range(11)]
        s = summarise("x", vs)
        assert s.p50 == pytest.approx(0.5)
        assert s.p90 == pytest.approx(0.9)
        assert s.p10 == pytest.approx(0.1)
        assert s.minv == pytest.approx(0.0)
        assert s.maxv == pytest.approx(1.0)

    def test_to_dict_roundtrip(self):
        s = summarise("x", [0.1, 0.2, 0.3])
        d = s.to_dict()
        assert d["name"] == "x"
        assert d["count"] == 3
        assert set(d.keys()) >= {"min", "p50", "max", "mean"}


# ── histogram_lines ───────────────────────────────────────────────


class TestHistogramLines:
    def test_empty(self):
        out = histogram_lines([])
        assert out == ["(empty)"]

    def test_identical_values_short_circuits(self):
        out = histogram_lines([0.5, 0.5, 0.5], bins=10)
        assert len(out) == 1
        assert "identical" in out[0]

    def test_bins_produce_expected_count(self):
        values = [i / 10.0 for i in range(20)]
        out = histogram_lines(values, bins=5, width=10)
        assert len(out) == 5
        # Total of all counts should equal input length
        total = 0
        for line in out:
            total += int(line.strip().split()[-1])
        assert total == 20


# ── _flatten_trigger ───────────────────────────────────────────────


class TestFlattenTrigger:
    def test_none_returns_empty(self):
        assert _flatten_trigger(None) == frozenset()
        assert _flatten_trigger({}) == frozenset()

    def test_flattens_across_all_known_fields(self):
        tags = _flatten_trigger({
            "state_types": ["monster", "elite"],
            "tags": ["tactical"],
            "threat_levels": ["high"],
        })
        assert "state_types:monster" in tags
        assert "state_types:elite" in tags
        assert "tags:tactical" in tags
        assert "threat_levels:high" in tags

    def test_ignores_non_string_values(self):
        tags = _flatten_trigger({"state_types": [1, "monster", None, ""]})
        assert tags == frozenset({"state_types:monster"})


# ── load_skills ───────────────────────────────────────────────────


class TestLoadSkills:
    def test_merges_live_and_seeds(self, tmp_path: Path):
        live = tmp_path / "skills.json"
        live.write_text(json.dumps([
            {"skill_id": "live_1", "content": "live content",
             "trigger": {"state_types": ["monster"]}},
        ]), encoding="utf-8")

        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "a.json").write_text(json.dumps([
            {"skill_id": "seed_1", "content": "seed one content"},
            {"skill_id": "seed_2", "content": "seed two content"},
        ]), encoding="utf-8")

        rows = load_skills(live, seeds)
        assert len(rows) == 3
        ids = {r.skill_id for r in rows}
        assert ids == {"live_1", "seed_1", "seed_2"}

    def test_skips_empty_content(self, tmp_path: Path):
        live = tmp_path / "skills.json"
        live.write_text(json.dumps([
            {"skill_id": "keep", "content": "non empty"},
            {"skill_id": "drop", "content": ""},
            {"skill_id": "drop2"},  # no content key
        ]), encoding="utf-8")
        rows = load_skills(live, tmp_path / "nonexistent_seeds")
        assert [r.skill_id for r in rows] == ["keep"]

    def test_missing_skills_json_still_loads_seeds(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "a.json").write_text(
            json.dumps([{"skill_id": "seed", "content": "x"}]),
            encoding="utf-8",
        )
        rows = load_skills(tmp_path / "missing.json", seeds)
        assert len(rows) == 1
        assert rows[0].skill_id == "seed"

    def test_malformed_seed_file_skipped(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "bad.json").write_text("{not json", encoding="utf-8")
        (seeds / "good.json").write_text(
            json.dumps([{"skill_id": "x", "content": "y"}]),
            encoding="utf-8",
        )
        rows = load_skills(tmp_path / "missing.json", seeds)
        assert len(rows) == 1
        assert rows[0].skill_id == "x"


# ── load_pe_candidates ────────────────────────────────────────────


class TestLoadPECandidates:
    def test_missing_file_empty(self, tmp_path: Path):
        assert load_pe_candidates(tmp_path / "nope.jsonl") == []

    def test_dedups_by_patch_id_keeping_latest(self, tmp_path: Path):
        path = tmp_path / "patches.jsonl"
        rows = [
            {"patch_id": "p1", "proposed_change": "first draft"},
            {"patch_id": "p1", "proposed_change": "revised"},
            {"patch_id": "p2", "proposed_change": "other"},
            {"patch_id": "p3", "current_issue": "fallback field"},
        ]
        path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
        out = load_pe_candidates(path)
        assert "revised" in out
        assert "first draft" not in out  # replaced by revised
        assert "other" in out
        assert "fallback field" in out
        assert len(out) == 3

    def test_skips_malformed_rows(self, tmp_path: Path):
        path = tmp_path / "patches.jsonl"
        path.write_text("\n".join([
            json.dumps({"patch_id": "p1", "proposed_change": "ok"}),
            "not valid json",
            json.dumps({"patch_id": "p2", "proposed_change": "also ok"}),
        ]), encoding="utf-8")
        out = load_pe_candidates(path)
        assert set(out) == {"ok", "also ok"}


# ── _trigger_jaccards ─────────────────────────────────────────────


class TestTriggerJaccards:
    def test_empty_input(self):
        assert _trigger_jaccards([]) == []

    def test_single_skill_no_pairs(self):
        s = SkillRow(skill_id="x", source_file="f", content="c",
                     trigger_tags=frozenset({"a"}))
        assert _trigger_jaccards([s]) == []

    def test_pairwise_count(self):
        rows = [
            SkillRow(skill_id=f"s{i}", source_file="f",
                     content=str(i), trigger_tags=frozenset({str(i)}))
            for i in range(4)
        ]
        # C(4,2) = 6 pairs expected
        assert len(_trigger_jaccards(rows)) == 6


# ── _pair_cosines ─────────────────────────────────────────────────


class _FakeEmbedder:
    def __init__(self, vocab):
        self._idx = {w: i for i, w in enumerate(vocab)}
        self._dim = len(vocab)

    def embed(self, texts):
        out = []
        for t in texts:
            v = [0.0] * self._dim
            for tok in t.lower().split():
                j = self._idx.get(tok)
                if j is not None:
                    v[j] = 1.0
            out.append(v)
        return out


class TestPairCosines:
    def test_empty(self):
        assert _pair_cosines([], _FakeEmbedder(["a"])) == []

    def test_single_skill_no_pairs(self):
        rows = [SkillRow(skill_id="x", source_file="", content="a",
                          trigger_tags=frozenset())]
        assert _pair_cosines(rows, _FakeEmbedder(["a"])) == []

    def test_respects_max_pairs_cap(self):
        rows = [
            SkillRow(skill_id=f"s{i}", source_file="",
                     content=f"w{i}", trigger_tags=frozenset())
            for i in range(10)
        ]
        # C(10,2) = 45 pairs; cap at 5.
        out = _pair_cosines(rows, _FakeEmbedder([f"w{i}" for i in range(10)]),
                             max_pairs=5, seed=42)
        assert len(out) == 5


# ── recommend ─────────────────────────────────────────────────────


class TestRecommend:
    def test_small_sample_adds_note(self):
        small = summarise("x", [0.1, 0.2, 0.3])
        rec = recommend(small, small, small)
        assert any("small" in n.lower() for n in rec.notes)

    def test_recommends_around_percentiles(self):
        big = summarise("x", [i / 100.0 for i in range(100)])
        rec = recommend(big, big, big)
        # skill_auto_reject ~ (p95, p99) = (0.94, 0.98) roughly
        lo, hi = rec.skill_auto_reject
        assert 0.90 <= lo <= hi <= 1.0

    def test_to_dict_roundtrip(self):
        s = summarise("x", [0.1, 0.2, 0.3])
        rec = recommend(s, s, s)
        d = rec.to_dict()
        assert "skill_auto_reject" in d
        assert "notes" in d
        assert isinstance(d["notes"], list)
