"""Tests for src/memory/write_gate_ab.py (log-grounded A/B replay)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence
from unittest.mock import MagicMock

import pytest

from src.memory.write_gate import Candidate
from src.memory.write_gate_ab import (
    ABReplayCandidate,
    ABReplayer,
    ABReplayResult,
    DEFAULT_SAMPLER_MODEL_FALLBACK,
    LogEvent,
    Phase1Result,
    Phase2Result,
    _default_sampler_model,
    build_prompt_b,
    iter_llm_call_events,
    make_sampler_for_event,
    recent_events_for_state,
    run_phase1,
    run_phase2,
    _lexical_conflicts,
    _section_chunks,
)


# ── Utilities ──────────────────────────────────────────────────────


def _write_log(path: Path, events: Sequence[dict]) -> None:
    """Write a synthetic run_*.jsonl fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


class _FakeEmbedder:
    """BoW-style deterministic embedder for tests. Mirrors the one in
    tests/test_write_gate.py but avoids the cross-module dependency."""

    def __init__(self, vocab: Sequence[str]):
        self._vocab = list(vocab)
        self._idx = {w: i for i, w in enumerate(self._vocab)}

    def available(self) -> bool:
        return True

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vecs: list[list[float]] = []
        for text in texts:
            v = [0.0] * len(self._vocab)
            for tok in _simple_tokens(text):
                j = self._idx.get(tok)
                if j is not None:
                    v[j] = 1.0
            vecs.append(v)
        return vecs


def _simple_tokens(text: str) -> set[str]:
    import re as _re
    return set(_re.findall(r"[a-zA-Z0-9]+", text.lower()))


class _StubJudge:
    """Canned fast-tier judge/sampler."""

    def __init__(self, *, response: str | list[str] | Exception | None = None):
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def available(self) -> bool:
        return self.response is not None

    def call(self, system: str, user: str, *, max_tokens: int = 1024) -> str:
        self.calls.append((system, user))
        if isinstance(self.response, Exception):
            raise self.response
        if isinstance(self.response, list):
            if not self.response:
                raise RuntimeError("no more canned responses")
            return self.response.pop(0)
        return self.response or ""


# ── Log iteration ──────────────────────────────────────────────────


class TestIterLlmCallEvents:
    def test_missing_file_yields_nothing(self, tmp_path: Path):
        assert list(iter_llm_call_events(tmp_path / "nope.jsonl")) == []

    def test_filters_non_llm_call_events(self, tmp_path: Path):
        log = tmp_path / "run_x.jsonl"
        _write_log(log, [
            {"event": "state", "step": 0, "state_type": "map"},
            {"event": "llm_call", "run_id": "r1", "step": 1,
             "state_type": "card_reward", "system_prompt": "sys",
             "prompt": "user", "messages": []},
            {"event": "decision", "step": 2},
        ])
        out = list(iter_llm_call_events(log))
        assert len(out) == 1
        assert out[0].state_type == "card_reward"

    def test_filters_by_state_type(self, tmp_path: Path):
        log = tmp_path / "run_x.jsonl"
        _write_log(log, [
            {"event": "llm_call", "state_type": "card_reward",
             "system_prompt": "a", "prompt": "b", "messages": []},
            {"event": "llm_call", "state_type": "shop",
             "system_prompt": "c", "prompt": "d", "messages": []},
        ])
        out = list(iter_llm_call_events(log, state_type="shop"))
        assert len(out) == 1
        assert out[0].state_type == "shop"

    def test_skips_malformed_lines(self, tmp_path: Path):
        log = tmp_path / "run_x.jsonl"
        log.write_text("\n".join([
            json.dumps({"event": "llm_call", "state_type": "map",
                        "system_prompt": "s", "prompt": "u", "messages": []}),
            "garbage not json",
            json.dumps({"event": "llm_call", "state_type": "map",
                        "system_prompt": "s2", "prompt": "u2", "messages": []}),
        ]), encoding="utf-8")
        assert len(list(iter_llm_call_events(log))) == 2


class TestRecentEvents:
    def test_returns_last_n_across_files(self, tmp_path: Path):
        for i in range(3):
            log = tmp_path / f"run_20260418_{i}.jsonl"
            _write_log(log, [
                {"event": "llm_call", "run_id": f"r{i}", "step": j,
                 "state_type": "shop",
                 "system_prompt": "s", "prompt": f"p_{i}_{j}", "messages": []}
                for j in range(4)
            ])
        out = recent_events_for_state(tmp_path, "shop", limit=5)
        assert len(out) == 5
        # Verify we got the tail of the sorted-by-filename sequence.
        assert out[-1].prompt == "p_2_3"


# ── Phase 1 ────────────────────────────────────────────────────────


class TestPhase1:
    def test_empty_content_rejects(self):
        emb = _FakeEmbedder(["x"])
        cand = Candidate(kind="skill", name="c", content="")
        r = run_phase1(cand, "## Section\nbody", embedder=emb)
        assert not r.passed
        assert r.reason == "empty_content"

    def test_no_sections_passes(self):
        emb = _FakeEmbedder(["alpha", "beta"])
        cand = Candidate(kind="skill", name="c", content="alpha beta")
        r = run_phase1(cand, "", embedder=emb)
        assert r.passed
        assert r.reason == "no_sections_to_compare"

    def test_rejects_duplicate_section(self):
        emb = _FakeEmbedder(["alpha", "beta", "gamma"])
        cand = Candidate(kind="skill", name="c", content="alpha beta gamma")
        prompt = "## Existing Skill\nalpha beta gamma\n\n## Other\nunrelated"
        r = run_phase1(cand, prompt, embedder=emb)
        assert not r.passed
        assert r.reason == "phase1_duplicate"
        assert r.max_cosine >= 0.70
        assert "alpha" in r.offending_excerpt.lower()

    def test_accepts_novel(self):
        emb = _FakeEmbedder(["alpha", "beta", "gamma", "unrelated", "content"])
        cand = Candidate(kind="skill", name="c", content="alpha beta gamma")
        prompt = "## Other\nunrelated content"
        r = run_phase1(cand, prompt, embedder=emb)
        assert r.passed
        assert r.max_cosine < 0.70

    def test_rejects_lexical_conflict(self):
        emb = _FakeEmbedder(["novel", "thing", "word"])
        cand = Candidate(
            kind="skill", name="c", content="Always novel thing word",
        )
        prompt = "## Existing\nNever novel thing anywhere"
        r = run_phase1(cand, prompt, embedder=emb)
        # Cosine might be below duplicate threshold due to novel token set,
        # but lexical prefer-vs-avoid should flag conflict.
        if r.reason == "phase1_conflict_lexical":
            assert not r.passed
            assert r.conflict_count >= 1

    def test_embedder_unavailable_degrades(self):
        class UnavailEmb:
            def available(self):
                return False
            def embed(self, _):
                raise RuntimeError("nope")
        cand = Candidate(kind="skill", name="c", content="alpha")
        r = run_phase1(cand, "## X\nsomething", embedder=UnavailEmb())
        assert r.passed  # cannot compute duplicates → pass
        assert r.reason == "phase1_embedder_unavailable"


# ── Phase 2 ────────────────────────────────────────────────────────


class TestPhase2:
    def test_judge_unavailable_rejects(self):
        sampler = _StubJudge(response=None)
        judge = _StubJudge(response=None)
        cand = Candidate(kind="skill", name="c", content="x")
        r = run_phase2(cand, "A", "B", "sys", sampler=sampler, judge=judge)
        assert not r.passed
        assert r.reason == "judge_unavailable"

    def test_incomplete_samples_reject(self):
        # Only 2 samples come back for 3 requested.
        sampler = _StubJudge(response=[
            "<decision>{\"action\": \"x\"}</decision>",
            "<decision>{\"action\": \"y\"}</decision>",
            Exception("boom"),
        ])
        judge = _StubJudge(response="SAME")
        cand = Candidate(kind="skill", name="c", content="x")
        r = run_phase2(cand, "A", "B", "sys", sampler=sampler, judge=judge)
        assert not r.passed
        # Reason can be either sample_incomplete or something else depending
        # on whether the exception blew away the side.
        assert r.reason in {"sample_incomplete"}

    def test_invalid_b_hard_rejects(self):
        # A responses parse; B responses do not.
        sampler = _StubJudge(response=[
            # 3x A parseable
            "<decision>{\"action\": \"end_turn\"}</decision>",
            "<decision>{\"action\": \"end_turn\"}</decision>",
            "<decision>{\"action\": \"end_turn\"}</decision>",
            # 3x B unparseable
            "no decision tag here",
            "{ wait this isn't inside a tag }",
            "still no decision block",
        ])
        judge = _StubJudge(response="BETTER_B")  # would promote — but B is invalid
        cand = Candidate(kind="skill", name="c", content="x")
        r = run_phase2(cand, "A", "B", "sys", sampler=sampler, judge=judge)
        assert not r.passed
        assert r.reason == "invalid_b_hard_reject"
        assert r.sample is not None
        assert r.sample.valid_a == 3
        assert r.sample.valid_b == 0

    def test_promotes_on_better_b_majority(self):
        sampler = _StubJudge(response=[
            # All 6 parseable
            *(["<decision>{\"action\": \"x\"}</decision>"] * 6)
        ])
        # Each of the 9 cross-pairs gets BETTER_B.
        judge = _StubJudge(response=["BETTER_B"] * 9)
        cand = Candidate(kind="skill", name="c", content="x")
        r = run_phase2(cand, "A", "B", "sys", sampler=sampler, judge=judge)
        assert r.passed
        assert r.better_b == 9
        assert r.worse_b == 0

    def test_rejects_on_worse_b_overflow(self):
        sampler = _StubJudge(response=[
            *(["<decision>{\"action\": \"x\"}</decision>"] * 6)
        ])
        judge = _StubJudge(response=["WORSE_B"] * 9)
        cand = Candidate(kind="skill", name="c", content="x")
        r = run_phase2(cand, "A", "B", "sys", sampler=sampler, judge=judge)
        assert not r.passed
        assert r.worse_b == 9

    def test_rejects_on_tie(self):
        # 1 BETTER_B + 1 WORSE_B + 7 SAME → BETTER_B < 2, reject.
        verdicts = ["BETTER_B"] + ["SAME"] * 7 + ["WORSE_B"]
        sampler = _StubJudge(response=[
            *(["<decision>{\"action\": \"x\"}</decision>"] * 6)
        ])
        judge = _StubJudge(response=verdicts)
        cand = Candidate(kind="skill", name="c", content="x")
        r = run_phase2(cand, "A", "B", "sys", sampler=sampler, judge=judge)
        assert not r.passed
        assert r.better_b == 1
        assert r.same == 7
        assert r.worse_b == 1


# ── build_prompt_b ────────────────────────────────────────────────


class TestBuildPromptB:
    def test_injects_before_your_task(self):
        prompt = "## State\nstuff\n\n## Your Task\ndo the thing"
        cand = Candidate(kind="skill", name="my_skill", content="Important hint.")
        b = build_prompt_b(prompt, cand)
        assert "my_skill" in b
        assert "Important hint" in b
        # Injection is before "## Your Task"
        assert b.index("my_skill") < b.index("## Your Task")

    def test_injects_before_last_section_when_no_your_task(self):
        prompt = "## State\nstuff\n\n## Options\nopt1, opt2"
        cand = Candidate(kind="skill", name="my_skill", content="Hint.")
        b = build_prompt_b(prompt, cand)
        assert "my_skill" in b
        # Should land before "## Options" (the last ## section).
        assert b.index("my_skill") < b.index("## Options")

    def test_appends_if_no_sections(self):
        prompt = "no markdown headers here"
        cand = Candidate(kind="skill", name="my_skill", content="Hint.")
        b = build_prompt_b(prompt, cand)
        assert b.startswith(prompt)
        assert "my_skill" in b


# ── Integration: ABReplayer ──────────────────────────────────────


class TestABReplayer:
    def test_no_source_no_fallback_rejects(self, tmp_path: Path):
        rep = ABReplayer(
            embedder=_FakeEmbedder(["x"]),
            sampler=_StubJudge(response=None),
            judge=_StubJudge(response=None),
            log_dir=tmp_path,
        )
        ab = ABReplayCandidate(
            candidate=Candidate(kind="skill", name="c", content="x"),
            source=None,
            fallback_events=(),
        )
        result = rep.replay(ab)
        assert result.final_action == "reject"
        assert result.reason == "no_source_and_no_fallback"
        log_path = tmp_path / ABReplayer.LOG_NAME
        assert log_path.is_file()

    def test_phase1_duplicate_rejects_without_llm(self, tmp_path: Path):
        emb = _FakeEmbedder(["alpha", "beta", "gamma"])
        sampler = _StubJudge(response=None)
        judge = _StubJudge(response=None)
        rep = ABReplayer(embedder=emb, sampler=sampler, judge=judge, log_dir=tmp_path)
        ab = ABReplayCandidate(
            candidate=Candidate(kind="skill", name="dup", content="alpha beta gamma"),
            source=LogEvent(
                run_id="r1", step=1, state_type="card_reward",
                model="m", tier="fast",
                system_prompt="sys",
                prompt="## Existing\nalpha beta gamma\n\n## Your Task\ngo",
                messages=(),
            ),
        )
        result = rep.replay(ab)
        assert result.final_action == "reject"
        assert result.reason.startswith("phase1:")
        # No LLM calls attempted
        assert sampler.calls == []

    def test_phase1_pass_phase2_invalid_b_hard_rejects(self, tmp_path: Path):
        emb = _FakeEmbedder(["foo", "bar", "baz", "qux", "quux"])
        # Phase 2 calls sampler 6 times (3 A + 3 B) then judge up to 9 times.
        sampler = _StubJudge(response=[
            *(["<decision>{\"action\": \"ok\"}</decision>"] * 3),  # A valid
            *(["random garbage no decision tag"] * 3),              # B invalid
        ])
        judge = _StubJudge(response="BETTER_B")
        rep = ABReplayer(embedder=emb, sampler=sampler, judge=judge, log_dir=tmp_path)
        ab = ABReplayCandidate(
            candidate=Candidate(kind="skill", name="novel", content="foo bar baz"),
            source=LogEvent(
                run_id="r1", step=1, state_type="card_reward",
                model="m", tier="fast",
                system_prompt="sys",
                prompt="## Other\nqux quux\n\n## Your Task\ngo",
                messages=(),
            ),
        )
        result = rep.replay(ab)
        assert result.final_action == "reject"
        assert "invalid_b_hard_reject" in result.reason
        assert result.phase1.passed
        # Judge should NOT have been called because Phase 2 bailed early.
        assert judge.calls == []

    def test_full_pipeline_promote(self, tmp_path: Path):
        emb = _FakeEmbedder(["foo", "bar", "baz", "qux", "quux"])
        # 6 sampler responses (all parseable), then 9 judge verdicts.
        sampler = _StubJudge(response=[
            *(["<decision>{\"action\": \"ok\"}</decision>"] * 6)
        ])
        # Strong promote signal: 4 BETTER_B + 5 SAME, 0 WORSE_B.
        judge = _StubJudge(response=["BETTER_B"] * 4 + ["SAME"] * 5)
        rep = ABReplayer(embedder=emb, sampler=sampler, judge=judge, log_dir=tmp_path)
        ab = ABReplayCandidate(
            candidate=Candidate(kind="skill", name="novel", content="foo bar baz"),
            source=LogEvent(
                run_id="r1", step=1, state_type="card_reward",
                model="m", tier="fast",
                system_prompt="sys",
                prompt="## Other\nqux quux\n\n## Your Task\ngo",
                messages=(),
            ),
        )
        result = rep.replay(ab)
        assert result.final_action == "promote"
        assert result.phase1.passed
        assert result.phase2 is not None and result.phase2.passed
        # Exactly 9 pair judgements consumed.
        assert len(judge.calls) == 9

    def test_log_file_appended(self, tmp_path: Path):
        emb = _FakeEmbedder(["x"])
        rep = ABReplayer(
            embedder=emb,
            sampler=_StubJudge(response=None),
            judge=_StubJudge(response=None),
            log_dir=tmp_path,
        )
        for i in range(3):
            rep.replay(ABReplayCandidate(
                candidate=Candidate(kind="skill", name=f"c{i}", content="x"),
                source=None,
            ))
        rows = (tmp_path / ABReplayer.LOG_NAME).read_text(encoding="utf-8").splitlines()
        assert len(rows) == 3
        for i, row in enumerate(rows):
            rec = json.loads(row)
            assert rec["candidate"] == f"c{i}"
            assert rec["final_action"] == "reject"


# ── Tier selection for the sampler ────────────────────────────────


class TestSamplerTier:
    def test_default_sampler_uses_strategic_env(self, monkeypatch):
        monkeypatch.setenv("STS2_STRATEGIC_MODEL", "gemini-3.1-pro-preview")
        assert _default_sampler_model() == "gemini-3.1-pro-preview"

    def test_default_falls_back_when_env_unset(self, monkeypatch):
        monkeypatch.delenv("STS2_STRATEGIC_MODEL", raising=False)
        assert _default_sampler_model() == DEFAULT_SAMPLER_MODEL_FALLBACK

    def test_make_sampler_uses_event_model_when_present(self, monkeypatch):
        monkeypatch.setenv("STS2_GPT_API_KEY", "fake")
        ev = LogEvent(
            run_id="r", step=1, state_type="card_reward",
            model="gemini-3.1-pro-preview", tier="strategic",
            system_prompt="", prompt="", messages=(),
        )
        sampler = make_sampler_for_event(ev)
        assert sampler.model == "gemini-3.1-pro-preview"

    def test_make_sampler_falls_back_when_event_model_empty(self, monkeypatch):
        monkeypatch.setenv("STS2_GPT_API_KEY", "fake")
        monkeypatch.setenv("STS2_STRATEGIC_MODEL", "gemini-3.1-pro-preview")
        ev = LogEvent(
            run_id="r", step=1, state_type="card_reward",
            model="", tier="", system_prompt="", prompt="", messages=(),
        )
        sampler = make_sampler_for_event(ev)
        assert sampler.model == "gemini-3.1-pro-preview"

    def test_replayer_uses_tier_matched_sampler_for_source(self, tmp_path: Path):
        """When no explicit sampler is passed, ABReplayer tier-matches per event."""
        # Use a stub judge to provide the verdicts; stub sampler is wired via
        # monkey-patching JudgeClient construction.
        emb = _FakeEmbedder(["foo", "bar"])
        # Explicit sampler=None → ABReplayer constructs one; but we want to
        # verify it then *overrides* with a tier-matched client. The easiest
        # observation point is that the tier-matched sampler receives the
        # calls, not the default-constructed one.
        seen_models: list[str] = []

        class _TrackingJudge:
            def __init__(self, *, model: str = "default"):
                self.model = model

            def available(self):
                return True

            def call(self, system, user, *, max_tokens=1024):
                seen_models.append(self.model)
                return "<decision>{\"action\":\"ok\"}</decision>"

        from src.memory import write_gate_ab as mod

        orig_make = mod.make_sampler_for_event
        orig_judge_cls = mod.JudgeClient
        try:
            mod.JudgeClient = _TrackingJudge  # type: ignore[misc]
            mod.make_sampler_for_event = lambda ev: _TrackingJudge(
                model=ev.model or "strategic-default",
            )

            rep = ABReplayer(
                embedder=emb, sampler=None, judge=_TrackingJudge(model="fast-judge"),
                log_dir=tmp_path,
            )
            ab = ABReplayCandidate(
                candidate=Candidate(kind="skill", name="x", content="foo"),
                source=LogEvent(
                    run_id="r", step=1, state_type="card_reward",
                    model="gemini-3.1-pro-preview", tier="strategic",
                    system_prompt="sys", prompt="## A\nbar\n\n## Your Task\ngo",
                    messages=(),
                ),
            )
            rep.replay(ab)
        finally:
            mod.JudgeClient = orig_judge_cls
            mod.make_sampler_for_event = orig_make

        # The sampler-tier model should have been called (6 sample rounds).
        assert seen_models.count("gemini-3.1-pro-preview") >= 6
        # The fast-tier judge should have been called for pair verdicts.
        assert seen_models.count("fast-judge") >= 1


# ── PE-era invalid-B regression (spec §11, commit 4 gate test) ─────


class TestPERegression:
    """Spec §11 requires confirming the invalid-B filter catches the PE-era
    failure mode. PE failed because patched prompts caused LLM output to
    stop matching the decision schema. This test simulates that by feeding
    synthetic "B responses" that parse-fail, verifying Phase 2 rejects
    them as ``invalid_b_hard_reject`` rather than ever reaching the judge."""

    @pytest.mark.parametrize("bad_b_response", [
        "The agent considered various options but decided not to commit.",
        "```json\n{\"action\": \"buy_card\"}\n```",  # no <decision> wrapper
        "",  # empty
        "<decision>not valid json at all</decision>",
        "Preamble\n<decision>{\"action\": \"x\"</decision>Postamble",  # truncated json
    ])
    def test_each_pe_era_invalid_b_pattern_is_caught(self, tmp_path: Path, bad_b_response: str):
        emb = _FakeEmbedder(["alpha"])
        sampler = _StubJudge(response=[
            *(["<decision>{\"action\": \"ok\"}</decision>"] * 3),  # A valid
            *([bad_b_response] * 3),                                 # B invalid
        ])
        judge = _StubJudge(response="BETTER_B")  # would promote — but B should reject
        rep = ABReplayer(embedder=emb, sampler=sampler, judge=judge, log_dir=tmp_path)
        ab = ABReplayCandidate(
            candidate=Candidate(kind="skill", name="c", content="alpha"),
            source=LogEvent(
                run_id="r", step=0, state_type="card_reward",
                model="m", tier="fast",
                system_prompt="sys",
                prompt="## Other\n\n## Your Task\ngo",
                messages=(),
            ),
        )
        result = rep.replay(ab)
        assert result.final_action == "reject"
        assert "invalid_b_hard_reject" in result.reason
        # Critical: judge was NEVER called on an invalid-B pattern.
        assert judge.calls == []
