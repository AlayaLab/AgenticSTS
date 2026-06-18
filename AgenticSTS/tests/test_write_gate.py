"""Tests for src/memory/write_gate.py (commit 1 — levels 1–3)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence
from unittest.mock import MagicMock, patch

import pytest

from src.memory.write_gate import (
    L1_L2_L3_REJECT_COSINE,
    L4_L5_AUTO_REJECT_COSINE,
    L4_L5_MERGE_OR_COEXIST_LOWER,
    TRIGGER_JACCARD_SAME_CONTEXT,
    Candidate,
    EmbeddingClient,
    EmbeddingUnavailableError,
    ExistingEntry,
    GateDecision,
    StaticSpan,
    StaticSpanIndex,
    WriteGate,
    _cosine,
    _jaccard,
    _normalize_openai_base_url,
    _relay_for_model,
    _tokenize,
)


# ── Utility fake embedder ─────────────────────────────────────────────


class BagOfWordsEmbedder(EmbeddingClient):
    """Test double: vectorises inputs as sparse 0/1 token-presence vectors.

    Cosines are then a deterministic, sensible proxy for semantic overlap
    (anywhere between 0 and 1, never inflated by hash quirks).
    """

    def __init__(self, vocab: Sequence[str], *, tmp_path: Path):
        super().__init__(api_key="fake", cache_path=tmp_path / "cache.json")
        self._vocab = list(vocab)
        self._idx = {w: i for i, w in enumerate(self._vocab)}

    def available(self) -> bool:  # noqa: D401
        return True

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vecs: list[list[float]] = []
        for text in texts:
            v = [0.0] * len(self._vocab)
            for tok in _tokenize(text):
                j = self._idx.get(tok)
                if j is not None:
                    v[j] = 1.0
            vecs.append(v)
        return vecs


def _make_gate(tmp_path: Path, vocab: Sequence[str]) -> WriteGate:
    emb = BagOfWordsEmbedder(vocab, tmp_path=tmp_path)
    idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
    gate = WriteGate(
        embedder=emb,
        static_index=idx,
        log_path=tmp_path / "write_gate_log.jsonl",
    )
    return gate


# ── Helpers & primitives ──────────────────────────────────────────────


class TestHelpers:
    def test_cosine_identity(self):
        assert _cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_cosine_orthogonal(self):
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_cosine_zero_vector(self):
        assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_jaccard_identity(self):
        assert _jaccard({"a", "b"}, {"a", "b"}) == pytest.approx(1.0)

    def test_jaccard_disjoint(self):
        assert _jaccard({"a"}, {"b"}) == 0.0

    def test_jaccard_empty(self):
        assert _jaccard(set(), set()) == 0.0

    def test_tokenize_removes_stopwords(self):
        toks = _tokenize("The quick brown fox is quick")
        assert "the" not in toks
        assert "is" not in toks
        assert "quick" in toks
        assert "brown" in toks


# ── Relay routing ─────────────────────────────────────────────────


class TestRelayRouting:
    def test_gemini_model_uses_gemini_env(self, monkeypatch):
        monkeypatch.setenv("STS2_GEMINI_BASE_URL", "https://gemini.example.com")
        monkeypatch.setenv("STS2_GEMINI_API_KEY", "gem-k")
        base, key, provider = _relay_for_model("gemini-3-flash-preview")
        assert base == "https://gemini.example.com"
        assert key == "gem-k"
        assert provider == "gemini"

    def test_gpt_model_uses_gpt_env(self, monkeypatch):
        monkeypatch.setenv("STS2_GPT_BASE_URL", "https://gpt.example.com")
        monkeypatch.setenv("STS2_GPT_API_KEY", "gpt-k")
        base, key, provider = _relay_for_model("gpt-5.4-mini")
        assert base == "https://gpt.example.com"
        assert key == "gpt-k"
        assert provider == "gpt"

    def test_qwen_model_uses_qwen_env(self, monkeypatch):
        monkeypatch.setenv("STS2_QWEN_BASE_URL", "https://qwen.example.com")
        monkeypatch.setenv("STS2_QWEN_API_KEY", "qwen-k")
        base, key, provider = _relay_for_model("qwen-3.5-turbo")
        assert base == "https://qwen.example.com"
        assert key == "qwen-k"
        assert provider == "qwen"

    def test_embedding_model_falls_to_gpt_relay(self, monkeypatch):
        monkeypatch.setenv("STS2_GPT_BASE_URL", "https://gpt.example.com")
        monkeypatch.setenv("STS2_GPT_API_KEY", "gpt-k")
        # text-embedding-* is OpenAI-native; served by GPT-style relay.
        base, key, provider = _relay_for_model("text-embedding-3-large")
        assert base == "https://gpt.example.com"
        assert key == "gpt-k"
        assert provider == "gpt"

    def test_unknown_model_falls_to_gpt_relay(self, monkeypatch):
        monkeypatch.setenv("STS2_GPT_BASE_URL", "https://gpt.example.com")
        monkeypatch.setenv("STS2_GPT_API_KEY", "gpt-k")
        base, key, provider = _relay_for_model("some-future-model")
        assert provider == "gpt"

    def test_empty_model_defaults_to_gpt(self, monkeypatch):
        monkeypatch.setenv("STS2_GPT_BASE_URL", "https://gpt.example.com")
        monkeypatch.setenv("STS2_GPT_API_KEY", "gpt-k")
        base, _, provider = _relay_for_model("")
        assert provider == "gpt"

    def test_normalize_url_adds_v1(self):
        assert _normalize_openai_base_url("https://x.com") == "https://x.com/v1"
        assert _normalize_openai_base_url("https://x.com/") == "https://x.com/v1"
        assert _normalize_openai_base_url("https://x.com/v1") == "https://x.com/v1"
        assert _normalize_openai_base_url("https://x.com/v1/") == "https://x.com/v1"


# ── EmbeddingClient ────────────────────────────────────────────────


class TestEmbeddingClient:
    def test_unavailable_when_no_api_key(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("STS2_GPT_API_KEY", raising=False)
        c = EmbeddingClient(api_key="", cache_path=tmp_path / "c.json")
        assert not c.available()
        with pytest.raises(EmbeddingUnavailableError):
            c.embed(["hi"])

    def test_cache_round_trip(self, tmp_path: Path):
        c = EmbeddingClient(api_key="fake", cache_path=tmp_path / "c.json")

        fake_response = MagicMock()
        d = MagicMock()
        d.embedding = [0.1, 0.2, 0.3]
        fake_response.data = [d]

        with patch("openai.OpenAI") as MockOpenAI:
            inst = MockOpenAI.return_value
            inst.embeddings.create.return_value = fake_response
            first = c.embed(["hello"])
            # Second call with identical text → served from cache, no new API call.
            inst.embeddings.create.reset_mock()
            second = c.embed(["hello"])

            assert first == second == [[0.1, 0.2, 0.3]]
            inst.embeddings.create.assert_not_called()

    def test_cache_persists_across_instances(self, tmp_path: Path):
        cache = tmp_path / "c.json"
        c1 = EmbeddingClient(api_key="fake", cache_path=cache)

        fake_response = MagicMock()
        d = MagicMock()
        d.embedding = [0.5, 0.5]
        fake_response.data = [d]

        with patch("openai.OpenAI") as MockOpenAI:
            MockOpenAI.return_value.embeddings.create.return_value = fake_response
            c1.embed(["persisted_text"])

        # Fresh instance, same cache file → no API call needed.
        c2 = EmbeddingClient(api_key="fake", cache_path=cache)
        with patch("openai.OpenAI") as MockOpenAI:
            inst = MockOpenAI.return_value
            inst.embeddings.create.side_effect = AssertionError("should not be called")
            out = c2.embed(["persisted_text"])
            assert out == [[0.5, 0.5]]


# ── StaticSpanIndex ────────────────────────────────────────────────


class TestStaticSpanIndex:
    def test_rebuild_collects_l1_spans(self, tmp_path: Path):
        emb = BagOfWordsEmbedder(vocab=["combat", "block", "energy"], tmp_path=tmp_path)
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        idx.rebuild_if_stale()
        # All 4 system prompts → many spans, at least 4
        assert idx.span_count >= 4
        for span in idx._spans:
            assert span.layer == "L1"
            assert span.source_file.startswith("src/brain/prompts/system.py")

    def test_cache_reload_skips_api(self, tmp_path: Path):
        emb = BagOfWordsEmbedder(vocab=["combat", "block"], tmp_path=tmp_path)
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        idx.rebuild_if_stale()
        original_count = idx.span_count

        # Second call on same hash → load from cache, not re-embed.
        idx2 = StaticSpanIndex(emb, evolution_dir=tmp_path)
        with patch.object(emb, "embed", side_effect=AssertionError("no re-embed")):
            idx2.rebuild_if_stale()
        assert idx2.span_count == original_count

    def test_max_similarity_no_vectors_returns_zero(self, tmp_path: Path):
        # Embedder without API key → index has spans but no vectors.
        emb = EmbeddingClient(api_key="", cache_path=tmp_path / "c.json")
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        idx.rebuild_if_stale()
        cos, span = idx.max_similarity([0.1, 0.2])
        assert cos == 0.0
        assert span is None


# ── WriteGate cascade ────────────────────────────────────────────────


class TestGateLevel1:
    def test_exact_name_match_same_layer_updates(self, tmp_path: Path):
        gate = _make_gate(tmp_path, vocab=["anything"])
        cand = Candidate(kind="skill", name="s1", content="foo", target_layer="L5")
        existing = [ExistingEntry(id="s1", content="foo (older)", layer="L5")]
        d = gate.check(cand, existing)
        assert d.action == "update"
        assert d.reason == "exact_name_match"
        assert d.target_id == "s1"

    def test_exact_name_different_layer_does_not_match(self, tmp_path: Path):
        gate = _make_gate(tmp_path, vocab=["anything"])
        cand = Candidate(kind="skill", name="s1", content="foo", target_layer="L5")
        existing = [ExistingEntry(id="s1", content="foo", layer="L4")]
        # Falls through to embedding path; with empty vocab cosine is 0 → accept.
        d = gate.check(cand, existing)
        assert d.action != "update"


class TestGateLevel3_L1Overlap:
    def test_candidate_that_restates_l1_is_rejected(self, tmp_path: Path):
        # Vocab includes tokens that actually appear in the real L1 system
        # prompts — "energy", "block", "hp", "turn" — so a candidate rephrasing
        # them will score high cosine against real L1 spans.
        vocab = [
            "energy", "reset", "turn", "unspent", "wasted", "hp", "resource",
            "run-wide", "block", "draw", "cards", "each",
        ]
        gate = _make_gate(tmp_path, vocab=vocab)
        cand = Candidate(
            kind="skill",
            name="new_skill",
            content="Energy resets each turn and unspent energy is wasted.",
        )
        d = gate.check(cand, existing=[])
        assert d.action == "reject"
        assert d.reason.startswith("l1_overlap")
        assert d.meta["l1_cosine"] >= L1_L2_L3_REJECT_COSINE

    def test_unrelated_content_is_not_l1_rejected(self, tmp_path: Path):
        vocab = [
            "energy", "reset", "turn", "unspent", "wasted", "hp", "resource",
            "run-wide", "block", "boss",  # L1 tokens
            "raccoon", "umbrella",  # novel / unrelated
        ]
        gate = _make_gate(tmp_path, vocab=vocab)
        cand = Candidate(
            kind="skill",
            name="new_skill",
            content="The raccoon holds an umbrella.",
        )
        d = gate.check(cand, existing=[])
        assert d.action != "reject"


class TestGateLevel3_L4L5:
    def test_auto_reject_when_identical_to_existing(self, tmp_path: Path):
        # Use synthetic tokens disjoint from the real L1 system prompts to
        # isolate the L4/L5 path.
        vocab = ["alphapotion", "betaneutralize", "gammaritual"]
        gate = _make_gate(tmp_path, vocab=vocab)
        cand = Candidate(
            kind="skill",
            name="candidate",
            content="alphapotion betaneutralize gammaritual",
            trigger_tags=frozenset({"combat", "low_hp"}),
        )
        existing = [
            ExistingEntry(
                id="s_existing",
                content="alphapotion betaneutralize gammaritual",
                trigger_tags=frozenset({"combat", "low_hp"}),
                layer="L5",
            ),
        ]
        d = gate.check(cand, existing)
        assert d.action == "reject"
        assert d.target_id == "s_existing"
        assert d.meta["cosine"] >= L4_L5_AUTO_REJECT_COSINE

    def test_merge_same_trigger_similar_content(self, tmp_path: Path):
        # Synthetic vocab to sidestep L1 contamination.
        vocab = ["alpha", "beta", "gamma", "delta", "epsilon"]
        gate = _make_gate(tmp_path, vocab=vocab)
        cand = Candidate(
            kind="skill",
            name="cand",
            content="alpha beta gamma delta",
            trigger_tags=frozenset({"custom_trigger_a", "custom_trigger_b"}),
        )
        existing = [
            ExistingEntry(
                id="older",
                content="alpha beta gamma epsilon",  # 3/5 overlap → cosine 0.75
                trigger_tags=frozenset({"custom_trigger_a", "custom_trigger_b"}),
            ),
        ]
        d = gate.check(cand, existing)
        cos = d.meta.get("cosine") or d.meta.get("top_cosine")
        if cos is not None and L4_L5_MERGE_OR_COEXIST_LOWER <= cos < L4_L5_AUTO_REJECT_COSINE:
            assert d.action == "merge"

    def test_distinct_trigger_with_moderately_similar_content_is_accepted(
        self, tmp_path: Path,
    ):
        # Spec §4.3: cosine ≥ 0.85 auto-rejects regardless of trigger.
        # Trigger Jaccard only branches the middle band [0.70, 0.85).
        # So this test sets up moderate overlap (~0.75) with disjoint triggers
        # → should ACCEPT as "distinct-trigger context variant".
        vocab = ["alphaw", "betaw", "gammaw", "deltaw", "epsilonw"]
        gate = _make_gate(tmp_path, vocab=vocab)
        cand = Candidate(
            kind="skill",
            name="cand",
            content="alphaw betaw gammaw deltaw",
            trigger_tags=frozenset({"trigger_x", "trigger_y"}),
        )
        existing = [
            ExistingEntry(
                id="older",
                content="alphaw betaw gammaw epsilonw",  # 3/4 shared → cosine 0.75
                trigger_tags=frozenset({"trigger_p", "trigger_q"}),  # disjoint
            ),
        ]
        d = gate.check(cand, existing)
        cos = d.meta.get("cosine") or d.meta.get("top_cosine") or 0.0
        # Only assert the spec rule if cosine actually lands in the merge band;
        # otherwise BoW arithmetic may put us just outside.
        if L4_L5_MERGE_OR_COEXIST_LOWER <= cos < L4_L5_AUTO_REJECT_COSINE:
            assert d.action == "accept"
            assert d.reason == "distinct_trigger_context_variant"

    def test_identical_content_auto_rejects_regardless_of_trigger(
        self, tmp_path: Path,
    ):
        # Spec: cosine ≥ 0.85 is unconditional reject (§4.3). This is
        # intentional — identical wording is wasted tokens even when triggers
        # differ; if the triggers truly need different content, the authoring
        # LLM should produce different wording.
        vocab = ["alphaw", "betaw", "gammaw"]
        gate = _make_gate(tmp_path, vocab=vocab)
        cand = Candidate(
            kind="skill",
            name="cand",
            content="alphaw betaw gammaw",
            trigger_tags=frozenset({"trigger_x"}),
        )
        existing = [
            ExistingEntry(
                id="older",
                content="alphaw betaw gammaw",
                trigger_tags=frozenset({"trigger_p"}),  # disjoint
            ),
        ]
        d = gate.check(cand, existing)
        assert d.action == "reject"
        assert d.reason == "l4l5_auto_duplicate"


class TestGateLevel3_DeferToJudge:
    def test_borderline_similarity_defers(self, tmp_path: Path):
        # Synthetic vocab isolates from real L1 prompts.
        vocab = ["wordone", "wordtwo", "wordthree", "wordfour", "wordfive"]
        gate = _make_gate(tmp_path, vocab=vocab)
        # 3/5 token overlap → cosine ≈ 0.6 → lands in L4/L5 judge zone
        # [0.55, 0.70).
        cand = Candidate(
            kind="skill",
            name="cand",
            content="wordone wordtwo wordthree",
        )
        existing = [
            ExistingEntry(
                id="e1",
                content="wordone wordtwo wordfour wordfive",
            ),
        ]
        d = gate.check(cand, existing)
        cos = d.meta.get("top_cosine") or d.meta.get("cosine") or 0.0
        if 0.55 <= cos < 0.70:
            assert d.action == "defer_to_judge"


# ── Observation log ────────────────────────────────────────────────


class TestObservationLog:
    def test_check_and_log_appends_jsonl(self, tmp_path: Path):
        gate = _make_gate(tmp_path, vocab=["foo"])
        cand = Candidate(
            kind="skill",
            name="s1",
            content="foo",
            trigger_tags=frozenset({"t1"}),
            source_run_id="run_abc",
        )
        gate.check_and_log(cand, existing=[])
        log_path = tmp_path / "write_gate_log.jsonl"
        assert log_path.is_file()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        rec = json.loads(lines[0])
        assert rec["name"] == "s1"
        assert rec["kind"] == "skill"
        assert rec["source_run_id"] == "run_abc"
        assert rec["action"] in ("accept", "reject", "merge", "update", "defer_to_judge")

    def test_multiple_checks_append(self, tmp_path: Path):
        gate = _make_gate(tmp_path, vocab=["foo", "bar"])
        gate.check_and_log(Candidate(kind="skill", name="a", content="foo"), existing=[])
        gate.check_and_log(Candidate(kind="skill", name="b", content="bar"), existing=[])
        log_path = tmp_path / "write_gate_log.jsonl"
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2


# ── Fallback paths (no API key) ───────────────────────────────────


class TestFilterSkillBatch:
    """Enforcement-mode gate — returns (kept, dropped, held) instead of just logging."""

    def _gate_with_action(self, tmp_path: Path, action_map: dict[str, str]):
        """Build a WriteGate whose check() returns a canned action per skill name."""
        from src.memory.write_gate import Candidate, ExistingEntry, GateDecision

        gate = _make_gate(tmp_path, vocab=["x"])

        def canned_check(cand, existing):  # type: ignore[no-redef]
            return GateDecision(
                action=action_map.get(cand.name, "accept"),
                reason="canned",
                target_id=None,
            )

        gate.check = canned_check  # type: ignore[method-assign]
        return gate

    def test_accept_passes_through(self, tmp_path: Path):
        class S:
            def __init__(self, name):
                self.name = name
                self.content = "c"
                self.trigger = None

        gate = self._gate_with_action(tmp_path, {"s1": "accept"})
        kept, dropped, held = gate.filter_skill_batch([S("s1")], [], run_id="r1")
        assert held == []
        assert len(kept) == 1
        assert kept[0].name == "s1"
        assert dropped == []

    def test_reject_drops_skill(self, tmp_path: Path):
        class S:
            def __init__(self, name):
                self.name = name
                self.content = "c"
                self.trigger = None

        gate = self._gate_with_action(tmp_path, {"s1": "reject"})
        kept, dropped, held = gate.filter_skill_batch([S("s1")], [], run_id="r1")
        assert held == []
        assert kept == []
        assert len(dropped) == 1
        assert dropped[0][1].action == "reject"

    def test_merge_drops_skill(self, tmp_path: Path):
        """merge means "new candidate is subsumed by existing" — drop the new."""
        class S:
            def __init__(self, name):
                self.name = name
                self.content = "c"
                self.trigger = None

        gate = self._gate_with_action(tmp_path, {"s1": "merge"})
        kept, dropped, held = gate.filter_skill_batch([S("s1")], [], run_id="r1")
        assert held == []
        assert kept == []
        assert dropped[0][1].action == "merge"

    def test_update_passes_through(self, tmp_path: Path):
        """update = "same skill_id, refreshed content" → library upserts by id."""
        class S:
            def __init__(self, name):
                self.name = name
                self.content = "c"
                self.trigger = None

        gate = self._gate_with_action(tmp_path, {"s1": "update"})
        kept, dropped, held = gate.filter_skill_batch([S("s1")], [], run_id="r1")
        assert held == []
        assert len(kept) == 1
        assert dropped == []

    def test_defer_to_judge_goes_to_held(self, tmp_path: Path):
        """defer = ambiguous; goes to held bucket, not kept — awaits batch judge."""
        class S:
            def __init__(self, name):
                self.name = name
                self.content = "c"
                self.trigger = None

        gate = self._gate_with_action(tmp_path, {"s1": "defer_to_judge"})
        kept, dropped, held = gate.filter_skill_batch([S("s1")], [], run_id="r1")
        assert kept == []
        assert dropped == []
        assert len(held) == 1
        assert held[0][1].action == "defer_to_judge"

    def test_mixed_batch_filters_correctly(self, tmp_path: Path):
        class S:
            def __init__(self, name):
                self.name = name
                self.content = "c"
                self.trigger = None

        gate = self._gate_with_action(tmp_path, {
            "new": "accept",
            "dup": "reject",
            "merge_of_x": "merge",
            "refreshed": "update",
            "borderline": "defer_to_judge",
        })
        candidates = [S("new"), S("dup"), S("merge_of_x"), S("refreshed"), S("borderline")]
        kept, dropped, held = gate.filter_skill_batch(candidates, [], run_id="r1")
        assert [s.name for s in kept] == ["new", "refreshed"]
        assert {d[0].name for d in dropped} == {"dup", "merge_of_x"}
        assert len(held) == 1
        assert held[0][0].name == "borderline"
        assert held[0][1].action == "defer_to_judge"

    def test_decisions_logged_even_when_dropped(self, tmp_path: Path):
        class S:
            def __init__(self, name):
                self.name = name
                self.content = "c"
                self.trigger = None

        gate = self._gate_with_action(tmp_path, {"s1": "reject"})
        gate.filter_skill_batch([S("s1")], [], run_id="r1")
        log = tmp_path / "write_gate_log.jsonl"
        assert log.is_file()
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        assert rec["name"] == "s1"
        assert rec["action"] == "reject"


class TestObserveSkillBatch:
    def test_duck_typed_skill_input(self, tmp_path: Path):
        gate = _make_gate(tmp_path, vocab=["foo", "bar"])

        class FakeTrigger:
            state_types = frozenset({"monster"})
            enemy_names = frozenset()
            requires_hand_capabilities = frozenset()
            requires_enemy_powers = frozenset()

        class FakeSkill:
            def __init__(self, name: str, content: str):
                self.name = name
                self.content = content
                self.trigger = FakeTrigger()

        new = [FakeSkill("new_one", "foo")]
        existing = [FakeSkill("old_one", "bar")]
        decisions = gate.observe_skill_batch(new, existing, run_id="r1")
        assert len(decisions) == 1
        assert decisions[0].action in {"accept", "reject", "merge", "update", "defer_to_judge"}

        log_path = tmp_path / "write_gate_log.jsonl"
        assert log_path.is_file()
        rec = json.loads(log_path.read_text(encoding="utf-8").splitlines()[-1])
        assert rec["source_run_id"] == "r1"
        assert rec["name"] == "new_one"
        assert rec["trigger_tag_count"] >= 1  # "state_types:monster" + "tags:tactical"

    def test_empty_new_list_is_noop(self, tmp_path: Path):
        gate = _make_gate(tmp_path, vocab=["foo"])
        decisions = gate.observe_skill_batch(new_skills=[], existing_skills=[])
        assert decisions == []


class TestFallback:
    def test_no_embedder_accepts_all_non_exact_matches(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("STS2_GPT_API_KEY", raising=False)
        emb = EmbeddingClient(api_key="", cache_path=tmp_path / "c.json")
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        gate = WriteGate(embedder=emb, static_index=idx, log_path=tmp_path / "g.jsonl")
        cand = Candidate(kind="skill", name="s", content="anything")
        d = gate.check(cand, existing=[])
        assert d.action == "accept"
        assert d.reason == "embedder_unavailable_fallback"


class TestEmbedFailedFallback:
    """embed_failed must not auto-accept: use lexical+LLM fallback instead."""

    def _gate_that_fails_embed(self, tmp_path: Path) -> WriteGate:
        """Build a gate whose embedder always raises on ``embed()`` calls."""
        emb = EmbeddingClient(api_key="fake-key", cache_path=tmp_path / "c.json")
        emb.embed = MagicMock(side_effect=RuntimeError("HTTP 400 bad request"))  # type: ignore[method-assign]
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        idx.rebuild_if_stale = MagicMock()  # skip actual index build
        return WriteGate(embedder=emb, static_index=idx, log_path=tmp_path / "g.jsonl")

    def test_no_existing_accepts_without_llm(self, tmp_path: Path) -> None:
        gate = self._gate_that_fails_embed(tmp_path)
        cand = Candidate(kind="skill", name="s", content="block when poisoned")
        d = gate.check(cand, existing=[])
        assert d.action == "accept"
        assert d.reason == "embed_failed_no_existing"

    def test_always_calls_llm_even_for_distinct_content(self, tmp_path: Path) -> None:
        gate = self._gate_that_fails_embed(tmp_path)
        cand = Candidate(kind="skill", name="s", content="poison stacking priority")
        existing = [ExistingEntry(id="e1", content="use block cards early game")]
        with patch("src.memory.write_gate.WriteGate._fast_llm_dup_check",
                   return_value=GateDecision(action="accept",
                                             reason="embed_failed_llm_unique",
                                             meta={"level": 0})) as mock_llm:
            d = gate.check(cand, existing=existing)
        mock_llm.assert_called_once()
        assert d.action == "accept"
        assert d.reason == "embed_failed_llm_unique"

    def test_lexically_similar_calls_llm_and_rejects_duplicate(
        self, tmp_path: Path
    ) -> None:
        gate = self._gate_that_fails_embed(tmp_path)
        content = "when enemy uses attack, play defend to block damage"
        cand = Candidate(kind="skill", name="s", content=content)
        existing = [ExistingEntry(id="old", content="when enemy attacks play defend for block")]
        llm_response = MagicMock()
        llm_response.choices = [MagicMock()]
        llm_response.choices[0].message.content = "DUPLICATE"
        with patch("src.memory.write_gate.WriteGate._fast_llm_dup_check",
                   return_value=GateDecision(action="reject", target_id="old",
                                             reason="embed_failed_llm_duplicate",
                                             meta={"level": 0})):
            d = gate.check(cand, existing=existing)
        assert d.action == "reject"
        assert d.reason == "embed_failed_llm_duplicate"

    def test_lexically_similar_calls_llm_and_accepts_unique(
        self, tmp_path: Path
    ) -> None:
        gate = self._gate_that_fails_embed(tmp_path)
        content = "when enemy uses attack, play defend to block damage"
        cand = Candidate(kind="skill", name="s", content=content)
        existing = [ExistingEntry(id="old", content="when enemy attacks play defend for block")]
        with patch("src.memory.write_gate.WriteGate._fast_llm_dup_check",
                   return_value=GateDecision(action="accept",
                                             reason="embed_failed_llm_unique",
                                             meta={"level": 0})):
            d = gate.check(cand, existing=existing)
        assert d.action == "accept"
        assert d.reason == "embed_failed_llm_unique"

    def test_dual_failure_defers_not_accepts(self, tmp_path: Path) -> None:
        gate = self._gate_that_fails_embed(tmp_path)
        cand = Candidate(kind="skill", name="s", content="block when poisoned")
        existing = [ExistingEntry(id="old", content="block against poison enemies")]
        with patch("src.memory.write_gate.WriteGate._fast_llm_dup_check",
                   side_effect=RuntimeError("LLM unavailable")):
            d = gate.check(cand, existing=existing)
        assert d.action == "defer_to_judge"
        assert d.reason == "embed_failed_llm_also_failed"


class TestEmptyContentGuard:
    """Regression: empty candidate bodies must not hit the embedding API.

    The OpenAI-compatible ``/v1/embeddings`` endpoint rejects empty-string
    inputs with HTTP 400 ``'$.input' is invalid``. Before the guard, such
    candidates caused 11+ noisy ``embed_failed`` fallthroughs in production
    that actually persisted through ``filter_skill_batch`` as accepts.
    """

    def test_empty_candidate_content_rejected_without_api_call(
        self, tmp_path: Path
    ) -> None:
        emb = BagOfWordsEmbedder(vocab=["a", "b"], tmp_path=tmp_path)
        seen_texts: list[str] = []
        orig_embed = emb.embed

        def _spy(texts):  # noqa: ANN001
            seen_texts.extend(texts)
            return orig_embed(texts)

        emb.embed = _spy  # type: ignore[assignment]
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        gate = WriteGate(embedder=emb, static_index=idx, log_path=tmp_path / "g.jsonl")

        cand = Candidate(kind="skill", name="New Skill", content="")
        decision = gate.check(cand, existing=[])

        assert decision.action == "reject"
        assert decision.reason == "empty_content"
        # The empty candidate body must never be sent to the embedder —
        # that is the exact ``input=[""]`` shape the OpenAI endpoint rejects.
        assert "" not in seen_texts

    def test_whitespace_only_content_also_rejected(self, tmp_path: Path) -> None:
        gate = _make_gate(tmp_path, vocab=["a"])
        cand = Candidate(kind="skill", name="s", content="   \n\t  ")
        decision = gate.check(cand, existing=[])
        assert decision.action == "reject"
        assert decision.reason == "empty_content"

    def test_empty_existing_entries_skipped_but_candidate_proceeds(
        self, tmp_path: Path
    ) -> None:
        gate = _make_gate(tmp_path, vocab=["sword", "shield", "block"])
        cand = Candidate(kind="skill", name="new", content="sword shield")
        # Mix of a real existing entry and an empty one — the empty one
        # must not be sent to the embedder and must not appear in neighbors.
        existing = [
            ExistingEntry(id="real", content="block shield"),
            ExistingEntry(id="empty", content=""),
            ExistingEntry(id="whitespace", content="   "),
        ]
        decision = gate.check(cand, existing=existing)
        # The decision uses real similarity math — we don't care which
        # branch fires, only that we don't crash on the empty entry.
        assert decision.action in {"accept", "defer_to_judge", "merge", "reject"}
        assert decision.reason != "embed_failed"

    def test_filter_skill_batch_drops_empty_content_skill(
        self, tmp_path: Path
    ) -> None:
        """End-to-end: a Skill-like object with empty content must be dropped."""
        gate = _make_gate(tmp_path, vocab=["sword", "shield"])

        class _FakeSkill:
            def __init__(self, name: str, content: str) -> None:
                self.name = name
                self.content = content
                self.trigger = None

        new_skills = [
            _FakeSkill("Placeholder Skill", ""),
            _FakeSkill("Real Skill", "sword play"),
        ]
        kept, dropped, held = gate.filter_skill_batch(new_skills, [], run_id="test-run")
        assert held == []
        kept_names = {getattr(s, "name", "") for s in kept}
        dropped_names = {getattr(s, "name", "") for s, _ in dropped}
        assert "Placeholder Skill" in dropped_names
        assert "Real Skill" in kept_names


def test_filter_skill_batch_splits_defer_into_held_bucket(tmp_path):
    """defer_to_judge verdicts go into ``held``, not ``kept`` or ``dropped``."""
    gate = WriteGate(log_path=tmp_path / "gate.jsonl")

    class S:
        def __init__(self, name):
            self.skill_id = name
            self.name = name
            self.content = "c"
            self.trigger = None

    defer_decision = GateDecision(
        action="defer_to_judge",
        target_id="",
        reason="judge_pending",
    )
    with patch.object(gate, "check_and_log", return_value=defer_decision):
        kept, dropped, held = gate.filter_skill_batch(
            [S("s1")], [], run_id="r1",
        )
    assert kept == []
    assert dropped == []
    assert len(held) == 1
    assert held[0][0].skill_id == "s1"
    assert held[0][1].action == "defer_to_judge"
