"""Tests for src/memory/write_gate_judge.py (Level 4 + cross-store conflict)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.memory.write_gate import (
    Candidate,
    EmbeddingClient,
    ExistingEntry,
    StaticSpan,
    StaticSpanIndex,
    WriteGate,
)
from src.memory.write_gate_judge import (
    BatchJudgeResult,
    CandidateJudgement,
    CandidateNeighbor,
    ConflictJudgement,
    ConflictPair,
    JudgeClient,
    JudgeQueue,
    JudgeRequest,
    JudgeUnavailableError,
    _build_user_prompt,
    _has_avoid,
    _has_prefer,
    _strip_json_fence,
    append_judge_log,
    batch_judge,
    find_structural_conflicts,
    judgement_to_decision,
)


# ── Predicate detector helpers ─────────────────────────────────────


class TestPredicateRegex:
    def test_prefer_phrases(self):
        for s in ("prefer block", "always heal", "must defend", "Priority: AoE", "favor speed"):
            assert _has_prefer(s)
        assert not _has_prefer("Block when low HP")

    def test_avoid_phrases(self):
        for s in ("avoid this card", "never skip rest", "don't pick", "skip elite"):
            assert _has_avoid(s)
        assert not _has_avoid("Pick elite for the relic")


# ── Structural conflict detection (§5.1) ────────────────────────────


class TestFindStructuralConflicts:
    def test_opposing_predicates_with_same_trigger_flagged(self):
        a = ExistingEntry(
            id="a",
            content="Always rest at low HP",
            trigger_tags=frozenset({"rest_site", "low_hp"}),
        )
        b = ExistingEntry(
            id="b",
            content="Avoid resting unless boss next",
            trigger_tags=frozenset({"rest_site", "low_hp"}),
        )
        pairs = find_structural_conflicts([a, b])
        assert len(pairs) == 1
        # Order normalised by id
        assert pairs[0].a.id == "a"
        assert pairs[0].b.id == "b"
        assert pairs[0].reason == "prefer_vs_avoid"
        assert pairs[0].trigger_jaccard == 1.0

    def test_disjoint_triggers_not_flagged(self):
        a = ExistingEntry(
            id="a",
            content="Always block",
            trigger_tags=frozenset({"combat"}),
        )
        b = ExistingEntry(
            id="b",
            content="Never block",
            trigger_tags=frozenset({"map"}),  # disjoint
        )
        pairs = find_structural_conflicts([a, b])
        assert pairs == []

    def test_same_predicate_not_flagged(self):
        a = ExistingEntry(
            id="a",
            content="Always rest",
            trigger_tags=frozenset({"rest_site"}),
        )
        b = ExistingEntry(
            id="b",
            content="Prefer rest",
            trigger_tags=frozenset({"rest_site"}),
        )
        # Both prefer-side; not a contradiction.
        pairs = find_structural_conflicts([a, b])
        assert pairs == []

    def test_dedupes_pair_orientations(self):
        # Should never emit (a,b) AND (b,a).
        a = ExistingEntry(
            id="ent_a",
            content="Always defend",
            trigger_tags=frozenset({"combat"}),
        )
        b = ExistingEntry(
            id="ent_b",
            content="Avoid defending",
            trigger_tags=frozenset({"combat"}),
        )
        # Even with explicit duplication
        pairs = find_structural_conflicts([a, b, a, b])
        assert len(pairs) == 1

    def test_content_cosine_filter_drops_off_topic_false_positives(self):
        """Regression: before this filter, the detector flagged
        "USE ALL POTIONS in boss" vs "ALWAYS apply Weak to top attacker"
        because both share trigger 'combat' and both contain always/never
        words. With an embedder, these should not be flagged."""
        a = ExistingEntry(
            id="a_potion",
            content="Boss fights are critical. Always use all potions.",
            trigger_tags=frozenset({"combat", "boss"}),
        )
        b = ExistingEntry(
            id="b_weak",
            content="When applying Weak, always target the top attacker.",
            trigger_tags=frozenset({"combat", "boss"}),
        )

        class _DisjointEmbedder:
            def available(self):
                return True

            def embed(self, texts):
                # a is [1,0], b is [0,1] → cosine 0 → filter drops this pair.
                vocab = {"potion": 0, "weak": 1}
                out = []
                for t in texts:
                    v = [0.0, 0.0]
                    for w, i in vocab.items():
                        if w in t.lower():
                            v[i] = 1.0
                    out.append(v)
                return out

        pairs = find_structural_conflicts([a, b], embedder=_DisjointEmbedder())
        assert pairs == []

    def test_content_cosine_kept_when_on_topic(self):
        """Same trigger + same topic + opposing predicate → real conflict."""
        a = ExistingEntry(
            id="a",
            content="Always use potions in boss fights.",
            trigger_tags=frozenset({"combat", "boss"}),
        )
        b = ExistingEntry(
            id="b",
            content="Never use potions in boss fights — save for emergencies.",
            trigger_tags=frozenset({"combat", "boss"}),
        )

        class _OverlapEmbedder:
            def available(self):
                return True

            def embed(self, texts):
                # Both map heavily onto the "potion/boss" axis → high cosine.
                vocab = {"potion": 0, "boss": 1, "fight": 2}
                out = []
                for t in texts:
                    v = [0.0, 0.0, 0.0]
                    low = t.lower()
                    for w, i in vocab.items():
                        if w in low:
                            v[i] = 1.0
                    out.append(v)
                return out

        pairs = find_structural_conflicts([a, b], embedder=_OverlapEmbedder())
        assert len(pairs) == 1
        assert pairs[0].content_cosine > 0.5

    def test_no_embedder_falls_back_to_lexical_only(self):
        # Old behaviour preserved when no embedder is supplied. content_cosine
        # should be 0.0 to signal the filter was skipped.
        a = ExistingEntry(
            id="a", content="Always X", trigger_tags=frozenset({"combat"}),
        )
        b = ExistingEntry(
            id="b", content="Never Y", trigger_tags=frozenset({"combat"}),
        )
        pairs = find_structural_conflicts([a, b])  # no embedder
        assert len(pairs) == 1
        assert pairs[0].content_cosine == 0.0

    def test_embedder_failure_falls_back_to_lexical(self):
        class _FailingEmbedder:
            def available(self):
                return True

            def embed(self, texts):
                raise RuntimeError("relay boom")

        a = ExistingEntry(
            id="a", content="Always X", trigger_tags=frozenset({"combat"}),
        )
        b = ExistingEntry(
            id="b", content="Never Y", trigger_tags=frozenset({"combat"}),
        )
        pairs = find_structural_conflicts([a, b], embedder=_FailingEmbedder())
        assert len(pairs) == 1
        assert pairs[0].content_cosine == 0.0


# ── JudgeClient ────────────────────────────────────────────────────


class TestJudgeClient:
    def test_unavailable_when_no_api_key(self, monkeypatch):
        monkeypatch.delenv("STS2_GPT_API_KEY", raising=False)
        monkeypatch.delenv("STS2_GEMINI_API_KEY", raising=False)
        c = JudgeClient(api_key="")
        assert not c.available()
        with pytest.raises(JudgeUnavailableError):
            c.call("sys", "user")

    def test_gemini_model_routes_to_gemini_relay(self, monkeypatch):
        monkeypatch.setenv("STS2_GEMINI_BASE_URL", "https://proxy.example.com")
        monkeypatch.setenv("STS2_GEMINI_API_KEY", "gemini-key-123")
        monkeypatch.setenv("STS2_GPT_BASE_URL", "https://proxy.example.com")
        monkeypatch.setenv("STS2_GPT_API_KEY", "gpt-key-456")

        c = JudgeClient(model="gemini-3-flash-preview")
        assert c.base_url == "https://proxy.example.com/v1"
        assert c.api_key == "gemini-key-123"
        assert c.provider == "gemini"

    def test_gpt_model_routes_to_gpt_relay(self, monkeypatch):
        monkeypatch.setenv("STS2_GPT_BASE_URL", "https://proxy.example.com")
        monkeypatch.setenv("STS2_GPT_API_KEY", "gpt-key-456")

        c = JudgeClient(model="gpt-5.4-mini")
        assert c.base_url == "https://proxy.example.com/v1"
        assert c.api_key == "gpt-key-456"
        assert c.provider == "gpt"

    def test_qwen_model_routes_to_qwen_relay(self, monkeypatch):
        monkeypatch.setenv("STS2_QWEN_BASE_URL", "https://qwen.example.com")
        monkeypatch.setenv("STS2_QWEN_API_KEY", "qwen-key")

        c = JudgeClient(model="qwen-3.5-turbo")
        assert c.base_url == "https://qwen.example.com/v1"
        assert c.api_key == "qwen-key"
        assert c.provider == "qwen"

    def test_explicit_base_url_overrides_routing(self):
        c = JudgeClient(
            model="gemini-3-flash-preview",
            base_url="https://override.example.com",
            api_key="explicit",
        )
        assert c.base_url == "https://override.example.com/v1"
        assert c.api_key == "explicit"

    def test_call_wraps_openai(self):
        c = JudgeClient(api_key="fake")
        with patch("openai.OpenAI") as MockOpenAI:
            inst = MockOpenAI.return_value
            mock_resp = MagicMock()
            mock_resp.choices = [MagicMock()]
            mock_resp.choices[0].message.content = '{"candidates": [], "conflicts": []}'
            inst.chat.completions.create.return_value = mock_resp
            out = c.call("sys", "user")
            assert "candidates" in out
            inst.chat.completions.create.assert_called_once()


# ── JudgeQueue ─────────────────────────────────────────────────────


class TestJudgeQueue:
    def test_enqueue_increments_counter(self):
        q = JudgeQueue()
        cand = Candidate(kind="skill", name="x", content="y")
        rid1 = q.enqueue(cand, [], [])
        rid2 = q.enqueue(cand, [], [])
        assert rid1 != rid2
        assert len(q) == 2

    def test_to_requests(self):
        q = JudgeQueue()
        cand = Candidate(kind="skill", name="x", content="y")
        q.enqueue(cand, [], [])
        reqs = q.to_requests()
        assert len(reqs) == 1
        assert reqs[0].kind == "candidate"
        assert reqs[0].candidate is cand

    def test_clear(self):
        q = JudgeQueue()
        q.enqueue(Candidate(kind="skill", name="x", content="y"), [], [])
        q.clear()
        assert len(q) == 0


# ── batch_judge ────────────────────────────────────────────────────


class _StubClient:
    """Minimal JudgeClient stand-in that returns canned responses."""

    def __init__(self, *, response: str | Exception):
        self._response = response
        self.last_system: str = ""
        self.last_user: str = ""

    def available(self) -> bool:
        return True

    def call(self, system: str, user: str, **_):
        self.last_system = system
        self.last_user = user
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class TestBatchJudge:
    def test_empty_input_no_call(self):
        client = _StubClient(response="")
        result = batch_judge(client, [])
        assert result.candidate_judgements == {}
        assert result.conflict_judgements == {}
        # No actual call was made — last_user remains empty.
        assert client.last_user == ""

    def test_parses_canonical_response(self):
        client = _StubClient(response=json.dumps({
            "candidates": [
                {"request_id": "cand_0001", "decision": "ADD", "target_id": None,
                 "reason": "novel"},
                {"request_id": "cand_0002", "decision": "MERGE", "target_id": "skill_x",
                 "reason": "same_concept"},
            ],
            "conflicts": [
                {"request_id": "conf_001", "verdict": "contradiction",
                 "resolution": "keep_higher_confidence", "reason": "opposed"},
            ],
        }))
        cand = Candidate(kind="skill", name="x", content="y")
        reqs = [
            JudgeRequest(kind="candidate", request_id="cand_0001", candidate=cand),
            JudgeRequest(kind="candidate", request_id="cand_0002", candidate=cand),
            JudgeRequest(
                kind="conflict",
                request_id="conf_001",
                pair=(
                    ExistingEntry(id="a", content="alpha"),
                    ExistingEntry(id="b", content="beta"),
                ),
            ),
        ]
        result = batch_judge(client, reqs)
        assert "cand_0001" in result.candidate_judgements
        assert result.candidate_judgements["cand_0001"].decision == "ADD"
        assert result.candidate_judgements["cand_0002"].target_id == "skill_x"
        assert result.conflict_judgements["conf_001"].verdict == "contradiction"

    def test_strips_code_fence(self):
        client = _StubClient(response='```json\n{"candidates": [], "conflicts": []}\n```')
        result = batch_judge(client, [
            JudgeRequest(kind="candidate", request_id="c1",
                         candidate=Candidate(kind="skill", name="x", content="y")),
        ])
        assert result.error == ""
        assert result.candidate_judgements == {}

    def test_invalid_json_returns_error(self):
        client = _StubClient(response="not json")
        result = batch_judge(client, [
            JudgeRequest(kind="candidate", request_id="c1",
                         candidate=Candidate(kind="skill", name="x", content="y")),
        ])
        assert result.error.startswith("json_decode")
        assert result.candidate_judgements == {}

    def test_call_failure_returns_error(self):
        client = _StubClient(response=RuntimeError("boom"))
        result = batch_judge(client, [
            JudgeRequest(kind="candidate", request_id="c1",
                         candidate=Candidate(kind="skill", name="x", content="y")),
        ])
        assert result.error.startswith("call_failed")

    def test_unknown_decisions_skipped(self):
        client = _StubClient(response=json.dumps({
            "candidates": [
                {"request_id": "good", "decision": "ADD", "target_id": None, "reason": ""},
                {"request_id": "bad", "decision": "TEAPOT", "target_id": None, "reason": ""},
            ],
            "conflicts": [],
        }))
        result = batch_judge(client, [
            JudgeRequest(kind="candidate", request_id="good",
                         candidate=Candidate(kind="skill", name="x", content="y")),
            JudgeRequest(kind="candidate", request_id="bad",
                         candidate=Candidate(kind="skill", name="x", content="y")),
        ])
        assert "good" in result.candidate_judgements
        assert "bad" not in result.candidate_judgements

    def test_user_prompt_includes_l1_spans(self):
        client = _StubClient(response='{"candidates": [], "conflicts": []}')
        cand = Candidate(kind="skill", name="x", content="my new content")
        spans = (StaticSpan(span_id="L1:s1#0", text="big system prompt block",
                            layer="L1", source_file="x"),)
        reqs = [
            JudgeRequest(
                kind="candidate", request_id="c1", candidate=cand, l1_spans=spans,
            ),
        ]
        batch_judge(client, reqs)
        assert "L1:s1#0" in client.last_user
        assert "my new content" in client.last_user


# ── judgement_to_decision ──────────────────────────────────────────


class TestJudgementToDecision:
    def test_add_maps_to_accept(self):
        j = CandidateJudgement(
            request_id="c1", decision="ADD", target_id=None, reason="novel",
        )
        d = judgement_to_decision(j)
        assert d.action == "accept"
        assert d.reason.startswith("judge:")
        assert d.meta["level"] == 4

    def test_merge_carries_target_id(self):
        j = CandidateJudgement(
            request_id="c1", decision="MERGE", target_id="t1", reason="dup",
        )
        d = judgement_to_decision(j)
        assert d.action == "merge"
        assert d.target_id == "t1"


# ── Integration: WriteGate auto-enqueues on defer_to_judge ────────


class TestWriteGateJudgeWiring:
    def test_defer_decision_enqueues(self, tmp_path: Path):
        from src.memory.write_gate import (
            L4_L5_JUDGE_LOWER, L4_L5_MERGE_OR_COEXIST_LOWER,
        )

        # Minimal setup: vocab tuned so candidate vs existing falls in
        # [0.55, 0.70) band (judge zone).
        from tests.test_write_gate import BagOfWordsEmbedder

        vocab = ["wordone", "wordtwo", "wordthree", "wordfour", "wordfive"]
        emb = BagOfWordsEmbedder(vocab, tmp_path=tmp_path)
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        queue = JudgeQueue()
        gate = WriteGate(
            embedder=emb, static_index=idx,
            log_path=tmp_path / "log.jsonl",
            judge_queue=queue,
        )
        cand = Candidate(kind="skill", name="cand", content="wordone wordtwo wordthree")
        existing = [
            ExistingEntry(id="e1", content="wordone wordtwo wordfour wordfive"),
        ]
        d = gate.check(cand, existing)
        cos = d.meta.get("top_cosine") or d.meta.get("cosine") or 0.0
        if L4_L5_JUDGE_LOWER <= cos < L4_L5_MERGE_OR_COEXIST_LOWER:
            assert d.action == "defer_to_judge"
            assert len(queue) == 1
            req = queue.to_requests()[0]
            assert req.kind == "candidate"
            assert req.candidate is cand
            # Top neighbor is captured.
            assert len(req.neighbors) >= 1
            assert req.neighbors[0].entry_id == "e1"


# ── flush_judge_round (WriteGate convenience) ─────────────────────


class TestFlushJudgeRound:
    def test_no_queue_returns_none(self, tmp_path: Path):
        from tests.test_write_gate import _make_gate
        gate = _make_gate(tmp_path, vocab=["foo"])  # no judge_queue
        assert gate.flush_judge_round(_StubClient(response="")) is None

    def test_empty_queue_no_call(self, tmp_path: Path):
        from tests.test_write_gate import BagOfWordsEmbedder
        emb = BagOfWordsEmbedder(["foo"], tmp_path=tmp_path)
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        queue = JudgeQueue()
        gate = WriteGate(
            embedder=emb, static_index=idx,
            log_path=tmp_path / "log.jsonl", judge_queue=queue,
        )
        client = _StubClient(response="")
        out = gate.flush_judge_round(client, round_id="r1")
        assert out is None
        assert client.last_user == ""

    def test_flush_calls_batch_and_clears_queue(self, tmp_path: Path):
        from tests.test_write_gate import BagOfWordsEmbedder
        emb = BagOfWordsEmbedder(["foo"], tmp_path=tmp_path)
        idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
        queue = JudgeQueue()
        gate = WriteGate(
            embedder=emb, static_index=idx,
            log_path=tmp_path / "log.jsonl", judge_queue=queue,
        )
        # Manually enqueue to skip cosine computations.
        queue.enqueue(Candidate(kind="skill", name="x", content="foo"), [], [])
        client = _StubClient(response='{"candidates": [{"request_id": "cand_0001", '
                                       '"decision": "ADD", "target_id": null, "reason": "ok"}], '
                                       '"conflicts": []}')
        result = gate.flush_judge_round(client, round_id="r1")
        assert result is not None
        assert "cand_0001" in result.candidate_judgements
        assert len(queue) == 0
        # judge_log.jsonl should have been written next to write_gate_log.jsonl
        judge_log = tmp_path / "judge_log.jsonl"
        assert judge_log.is_file()


# ── Logging ────────────────────────────────────────────────────────


class TestJudgeLog:
    def test_append_writes_one_jsonl_line(self, tmp_path: Path):
        log = tmp_path / "judge_log.jsonl"
        cand = Candidate(kind="skill", name="x", content="y")
        reqs = [JudgeRequest(kind="candidate", request_id="c1", candidate=cand)]
        result = BatchJudgeResult({}, {}, error="")
        append_judge_log(log, round_id="r1", requests=reqs, result=result)
        assert log.is_file()
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        assert rec["round_id"] == "r1"
        assert rec["request_count"] == 1
        assert rec["candidate_count"] == 1
        assert rec["judged_candidates"] == 0
        assert "raw_response_tail" not in rec  # only present on error

    def test_logs_raw_response_tail_on_parse_error(self, tmp_path: Path):
        log = tmp_path / "judge_log.jsonl"
        cand = Candidate(kind="skill", name="x", content="y")
        reqs = [JudgeRequest(kind="candidate", request_id="c1", candidate=cand)]
        # Simulate a truncated JSON response so we can see diagnostic info.
        long_raw = "{" * 600  # > 500 chars; we should get the last 500
        result = BatchJudgeResult(
            {}, {},
            raw_response=long_raw,
            error="json_decode: Expecting property name at line 1 column 2",
        )
        append_judge_log(log, round_id="r2", requests=reqs, result=result)
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        assert rec["error"].startswith("json_decode")
        assert rec["raw_response_len"] == len(long_raw)
        assert rec["raw_response_tail"].startswith("{")
        assert len(rec["raw_response_tail"]) == 500

    def test_no_raw_tail_when_call_failed_before_response(self, tmp_path: Path):
        log = tmp_path / "judge_log.jsonl"
        cand = Candidate(kind="skill", name="x", content="y")
        reqs = [JudgeRequest(kind="candidate", request_id="c1", candidate=cand)]
        # Error with no raw_response → should not emit the tail field.
        result = BatchJudgeResult({}, {}, raw_response="", error="call_failed: 503")
        append_judge_log(log, round_id="r3", requests=reqs, result=result)
        rec = json.loads(log.read_text(encoding="utf-8").strip())
        assert "raw_response_tail" not in rec
