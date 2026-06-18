"""Tests for scripts/audit_skill_library.py — safety rules around seeds."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.audit_skill_library import (
    DupPair,
    SkillRecord,
    _is_same_logical_skill,
    _is_seed_pair,
    _is_seed_record,
    _pick_loser,
    _prune_live_json,
    find_duplicates,
    load_skills,
)


def _rec(
    *,
    skill_id: str,
    content: str = "x",
    trigger_tags: frozenset[str] = frozenset(),
    confidence: float = 0.5,
    usage_count: int = 0,
    is_seed: bool = False,
    source: str = "discovered",
    name: str = "",
    source_file: Path = Path("data/skills/skills.json"),
) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        name=name or skill_id,
        content=content,
        trigger_tags=trigger_tags,
        confidence=confidence,
        usage_count=usage_count,
        source_file=source_file,
        is_seed=is_seed,
        raw={"skill_id": skill_id, "source": source},
    )


# ── Seed-safety helpers ──────────────────────────────────────────


class TestSeedDetection:
    def test_is_seed_record_by_provenance(self):
        r = _rec(skill_id="x", is_seed=True, source="discovered")
        assert _is_seed_record(r) is True

    def test_is_seed_record_by_source_field(self):
        # This is the stat-holder pattern: entry lives in skills.json
        # (is_seed=False) but its source field marks it as seed.
        r = _rec(skill_id="seed_core_combat", is_seed=False, source="seed")
        assert _is_seed_record(r) is True

    def test_is_seed_record_neither(self):
        r = _rec(skill_id="discovered_123", is_seed=False, source="discovered")
        assert _is_seed_record(r) is False

    def test_same_logical_skill_by_id(self):
        a = _rec(skill_id="seed_core_combat", is_seed=True)
        b = _rec(skill_id="seed_core_combat", is_seed=False, source="seed")
        assert _is_same_logical_skill(a, b) is True

    def test_same_logical_skill_empty_ids_false(self):
        a = _rec(skill_id="", name="A")
        b = _rec(skill_id="", name="B")
        assert _is_same_logical_skill(a, b) is False

    def test_seed_pair_detection(self):
        a = _rec(skill_id="a", is_seed=True)
        b = _rec(skill_id="b", is_seed=True)
        assert _is_seed_pair(a, b) is True

        c = _rec(skill_id="c", is_seed=True)
        d = _rec(skill_id="d", is_seed=False, source="discovered")
        assert _is_seed_pair(c, d) is False


# ── _pick_loser safety ────────────────────────────────────────────


class TestPickLoserSafety:
    def test_stat_holder_of_seed_is_never_dropped(self):
        """Regression: skills.json entry with source='seed' is the runtime
        stat-holder for a seed skill. Never pick it as the loser even when
        paired against another 'seed' record."""
        stat_holder = _rec(
            skill_id="seed_core_combat", is_seed=False, source="seed",
            confidence=0.99, usage_count=2716,
        )
        canonical = _rec(
            skill_id="seed_core_combat", is_seed=True, source="seed",
            confidence=0.90, usage_count=0,
        )
        assert _pick_loser(stat_holder, canonical) is None
        assert _pick_loser(canonical, stat_holder) is None

    def test_seed_vs_discovered_drops_discovered(self):
        s = _rec(skill_id="seed_x", is_seed=True, source="seed")
        d = _rec(skill_id="disc_x", is_seed=False, source="discovered")
        assert _pick_loser(s, d) is d
        assert _pick_loser(d, s) is d

    def test_two_discovered_pick_lower_confidence(self):
        a = _rec(skill_id="a", confidence=0.9, usage_count=100)
        b = _rec(skill_id="b", confidence=0.5, usage_count=100)
        assert _pick_loser(a, b) is b
        assert _pick_loser(b, a) is b

    def test_two_discovered_tie_prefers_higher_usage(self):
        a = _rec(skill_id="a", confidence=0.5, usage_count=20)
        b = _rec(skill_id="b", confidence=0.5, usage_count=5)
        assert _pick_loser(a, b) is b

    def test_two_discovered_final_tie_by_id(self):
        a = _rec(skill_id="aaa", confidence=0.5, usage_count=0)
        b = _rec(skill_id="zzz", confidence=0.5, usage_count=0)
        # Larger id string sorts later → picked as loser for stable output.
        assert _pick_loser(a, b) is b


# ── find_duplicates skips same-logical + seed-pair ───────────────


class _IdentityEmbedder:
    """Returns a one-hot vector per unique input so that identical content
    produces cosine=1.0 and disjoint content produces cosine=0.0."""

    def available(self) -> bool:
        return True

    def embed(self, texts):
        # Assign each unique text a distinct basis vector.
        unique = list(dict.fromkeys(texts))
        dim = len(unique)
        idx = {t: i for i, t in enumerate(unique)}
        vecs = []
        for t in texts:
            v = [0.0] * dim
            v[idx[t]] = 1.0
            vecs.append(v)
        return vecs


class TestFindDuplicatesSeedSafety:
    def test_skips_same_skill_id_pair(self):
        """Seed stat-holder vs canonical seed: same content, same id. Never
        flagged as a duplicate (would zero out the stats otherwise)."""
        stat = _rec(skill_id="seed_x", content="alpha",
                    is_seed=False, source="seed")
        canon = _rec(skill_id="seed_x", content="alpha",
                     is_seed=True, source="seed")
        pairs = find_duplicates([stat, canon], _IdentityEmbedder(), dup_cosine=0.5)
        assert pairs == []

    def test_skips_two_seeds(self):
        """Two seed-source records with similar content but different ids
        (e.g. deliberate overlap between seed files) are not pruned — the
        curator wrote them that way."""
        a = _rec(skill_id="seed_a", content="alpha", is_seed=True, source="seed")
        b = _rec(skill_id="seed_b", content="alpha", is_seed=True, source="seed")
        pairs = find_duplicates([a, b], _IdentityEmbedder(), dup_cosine=0.5)
        assert pairs == []

    def test_flags_two_discovered_duplicates(self):
        a = _rec(skill_id="disc_a", content="alpha",
                 is_seed=False, source="discovered")
        b = _rec(skill_id="disc_b", content="alpha",
                 is_seed=False, source="discovered")
        pairs = find_duplicates([a, b], _IdentityEmbedder(), dup_cosine=0.5)
        assert len(pairs) == 1
        assert pairs[0].cosine == pytest.approx(1.0)

    def test_flags_discovered_vs_seed_when_content_identical(self):
        """If a discovered skill really did re-derive a seed's content,
        we want to flag it and drop the discovered side."""
        d = _rec(skill_id="disc_x", content="alpha",
                 is_seed=False, source="discovered")
        s = _rec(skill_id="seed_y", content="alpha",
                 is_seed=True, source="seed")
        pairs = find_duplicates([d, s], _IdentityEmbedder(), dup_cosine=0.5)
        assert len(pairs) == 1
        # _pick_loser should drop the discovered side
        loser = _pick_loser(pairs[0].a, pairs[0].b)
        assert loser is d


# ── _prune_live_json ──────────────────────────────────────────────


class TestPruneLiveJson:
    def test_removes_only_matching_ids(self):
        live = [
            {"skill_id": "a", "content": "x"},
            {"skill_id": "b", "content": "y"},
            {"skill_id": "c", "content": "z"},
        ]
        out = _prune_live_json(live, {"b"})
        assert [r["skill_id"] for r in out] == ["a", "c"]

    def test_preserves_non_dict_entries(self):
        live = [{"skill_id": "a"}, "junk", {"skill_id": "b"}]
        out = _prune_live_json(live, {"a"})
        assert out == ["junk", {"skill_id": "b"}]

    def test_empty_remove_set_is_identity(self):
        live = [{"skill_id": "a"}, {"skill_id": "b"}]
        out = _prune_live_json(live, set())
        assert out == live


# ── load_skills ───────────────────────────────────────────────────


class TestLoadSkills:
    def test_loads_live_and_seeds_with_source_flag(self, tmp_path: Path):
        live = tmp_path / "skills.json"
        live.write_text(json.dumps([
            {"skill_id": "seed_x", "name": "SeedX", "content": "c",
             "confidence": 0.9, "usage_count": 100, "source": "seed"},
            {"skill_id": "disc_1", "name": "Disc1", "content": "c",
             "confidence": 0.5, "usage_count": 2, "source": "discovered"},
        ]), encoding="utf-8")
        seeds = tmp_path / "seeds"
        seeds.mkdir()
        (seeds / "a.json").write_text(json.dumps([
            {"skill_id": "seed_x", "name": "SeedX",
             "content": "c", "source": "seed"},
        ]), encoding="utf-8")

        records, raw = load_skills(live, seeds)
        assert len(records) == 3  # 2 live + 1 seed
        assert len(raw) == 2
        by_id = {(r.skill_id, r.is_seed): r for r in records}
        assert ("seed_x", False) in by_id  # stat-holder in skills.json
        assert ("seed_x", True) in by_id   # canonical seed file
        assert ("disc_1", False) in by_id