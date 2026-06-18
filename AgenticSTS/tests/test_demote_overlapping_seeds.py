"""Tests for scripts/demote_overlapping_seeds.py.

Mocks the embedder + StaticSpanIndex so tests do not hit the real API.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.demote_overlapping_seeds import (
    DemotionRecord,
    _demote_one,
    _iter_seed_skills,
    _scan_seeds,
    _write_log,
)
from src.memory.write_gate import StaticSpan


# ── _iter_seed_skills ──────────────────────────────────────────────


class TestIterSeedSkills:
    def test_yields_pairs(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "a.json").write_text(
            json.dumps([{"skill_id": "a1", "name": "A1", "content": "stuff"}]),
            encoding="utf-8",
        )
        out = list(_iter_seed_skills(seeds))
        assert len(out) == 1
        assert out[0][0].name == "a.json"
        assert out[0][1][0]["skill_id"] == "a1"

    def test_skips_malformed_json(self, tmp_path: Path, caplog):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "bad.json").write_text("{not json", encoding="utf-8")
        (seeds / "good.json").write_text(json.dumps([{"x": 1}]), encoding="utf-8")
        out = list(_iter_seed_skills(seeds))
        # Only the good file
        assert {p.name for p, _ in out} == {"good.json"}

    def test_skips_top_level_dict(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "wrong.json").write_text(json.dumps({"oops": "dict"}), encoding="utf-8")
        out = list(_iter_seed_skills(seeds))
        assert out == []


# ── _demote_one ────────────────────────────────────────────────────


class TestDemoteOne:
    def test_sets_confidence_and_legacy(self):
        out = _demote_one(
            {"skill_id": "x", "confidence": 0.9, "name": "X"},
            demoted_confidence=0.30,
        )
        assert out["confidence"] == 0.30
        assert out["legacy"] is True
        # Other fields preserved
        assert out["skill_id"] == "x"
        assert out["name"] == "X"

    def test_does_not_mutate_input(self):
        orig = {"skill_id": "x", "confidence": 0.9}
        out = _demote_one(orig, demoted_confidence=0.30)
        assert orig["confidence"] == 0.9
        assert "legacy" not in orig
        assert out is not orig


# ── _scan_seeds (mocked embedder + index) ─────────────────────────


def _make_static_index_mock(*, return_pairs):
    """Build a mock StaticSpanIndex whose max_similarity returns from a list.

    ``return_pairs`` is consumed in order, one (cosine, span) per
    .max_similarity call.
    """
    idx = MagicMock()
    iterator = iter(return_pairs)
    idx.max_similarity = lambda _vec: next(iterator)
    return idx


def _make_embedder_mock(*, vec_count: int):
    emb = MagicMock()
    # Return as many fake 3-dim vectors as requested.
    emb.embed = lambda texts: [[0.1, 0.2, 0.3]] * len(texts)
    emb.available = lambda: True
    return emb


class TestScanSeeds:
    def test_no_seeds_no_records(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        idx = _make_static_index_mock(return_pairs=[])
        emb = _make_embedder_mock(vec_count=0)
        records, updates = _scan_seeds(
            seeds, static_index=idx, embedder=emb,
            threshold=0.7, demoted_confidence=0.30,
        )
        assert records == []
        assert updates == {}

    def test_demotes_when_above_threshold(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "core.json").write_text(json.dumps([
            {"skill_id": "s1", "name": "S1", "content": "energy resets each turn",
             "confidence": 0.9},
            {"skill_id": "s2", "name": "S2", "content": "totally novel content",
             "confidence": 0.7},
        ]), encoding="utf-8")
        offending_span = StaticSpan(
            span_id="L1:SYSTEM_COMBAT#0",
            text="Energy resets to 3 each turn. Unspent energy is wasted.",
            layer="L1",
            source_file="src/brain/prompts/system.py:SYSTEM_COMBAT",
        )
        idx = _make_static_index_mock(return_pairs=[
            (0.82, offending_span),  # s1 → demote
            (0.30, offending_span),  # s2 → keep
        ])
        emb = _make_embedder_mock(vec_count=2)
        records, updates = _scan_seeds(
            seeds, static_index=idx, embedder=emb,
            threshold=0.70, demoted_confidence=0.30,
        )
        assert len(records) == 1
        assert records[0].skill_id == "s1"
        assert records[0].cosine == 0.82
        assert records[0].old_confidence == 0.9
        assert records[0].new_confidence == 0.30
        assert seeds / "core.json" in updates
        # The updates list should reflect the demoted s1 and untouched s2.
        modified = updates[seeds / "core.json"]
        assert modified[0]["confidence"] == 0.30
        assert modified[0]["legacy"] is True
        assert modified[1]["confidence"] == 0.7
        assert "legacy" not in modified[1]

    def test_skips_already_demoted_seeds(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "core.json").write_text(json.dumps([
            {"skill_id": "old", "name": "O", "content": "x", "legacy": True,
             "confidence": 0.30},
        ]), encoding="utf-8")
        idx = _make_static_index_mock(return_pairs=[])
        emb = MagicMock()
        emb.embed = MagicMock(return_value=[])
        emb.available = lambda: True
        records, updates = _scan_seeds(
            seeds, static_index=idx, embedder=emb,
            threshold=0.70, demoted_confidence=0.30,
        )
        assert records == []
        assert updates == {}
        # Confirm the embedder was not called with the legacy entry.
        emb.embed.assert_not_called()

    def test_below_threshold_not_demoted(self, tmp_path: Path):
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "core.json").write_text(json.dumps([
            {"skill_id": "novel", "name": "N", "content": "totally fresh",
             "confidence": 0.8},
        ]), encoding="utf-8")
        span = StaticSpan(
            span_id="L1:foo#0", text="x", layer="L1", source_file="x",
        )
        idx = _make_static_index_mock(return_pairs=[(0.50, span)])
        emb = _make_embedder_mock(vec_count=1)
        records, updates = _scan_seeds(
            seeds, static_index=idx, embedder=emb,
            threshold=0.70, demoted_confidence=0.30,
        )
        assert records == []
        assert updates == {}


# ── _write_log ─────────────────────────────────────────────────────


class TestWriteLog:
    def test_writes_header_and_rows(self, tmp_path: Path):
        records = [
            DemotionRecord(
                file="src/skills/seeds/a.json",
                skill_id="s1",
                name="S1",
                cosine=0.82,
                span_id="L1:foo",
                span_excerpt="Energy resets...",
                old_confidence=0.9,
                new_confidence=0.30,
            ),
        ]
        path = tmp_path / "report.log"
        _write_log(path, records, dry_run=False)
        text = path.read_text(encoding="utf-8")
        assert "# Legacy demotion run" in text
        assert "dry_run=False, count=1" in text
        assert "s1" in text
        assert "0.820" in text
        assert "L1:foo" in text

    def test_writes_empty_report_when_no_records(self, tmp_path: Path):
        path = tmp_path / "report.log"
        _write_log(path, [], dry_run=True)
        text = path.read_text(encoding="utf-8")
        assert "count=0" in text
        assert "dry_run=True" in text
