"""End-to-end integration: ``_flush_write_gate_judge`` → ``flush_judge_round``
→ ``reap_judge_verdicts``.

Verifies that when ``WRITE_GATE_REAP_ENABLED=True`` and ``flush_judge_round``
returns a non-error ``BatchJudgeResult``, the reap step:
  - persists ADD verdicts into the live skill library;
  - clears the gate's ``_pending_skills`` buffer;
  - writes an audit row to the configured reap log.

Construction follows the same minimal-loop pattern used by
``tests/test_seed_character_guides.py`` so we don't need a live MCP client.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
from src.agent.loop import AgentLoop
from src.memory.write_gate import PendingSkillCandidate
from src.memory.write_gate_judge import BatchJudgeResult, CandidateJudgement
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger


def _make_loop() -> AgentLoop:
    """Construct a minimal AgentLoop with no MCP / LLM / knowledge wiring."""
    with (
        patch.object(AgentLoop, "_init_knowledge", return_value=None),
        patch.object(AgentLoop, "_init_web_searcher", return_value=None),
        patch.object(AgentLoop, "_load_counter", return_value=0),
        patch.object(AgentLoop, "_init_skill_library", return_value=None),
        patch.object(AgentLoop, "_init_v2", return_value=None),
    ):
        loop = AgentLoop(client=MagicMock(), use_llm=False)
    return loop


def _mk_pending(skill_id: str = "s_int", request_id: str = "req_int") -> PendingSkillCandidate:
    sk = Skill(
        skill_id=skill_id,
        name=skill_id,
        content="integration content",
        trigger=SkillTrigger(),
    )
    return PendingSkillCandidate(
        skill=sk, decision_action="defer_to_judge", request_id=request_id
    )


@pytest.mark.asyncio
async def test_flush_write_gate_judge_invokes_reap_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: pending candidate + ADD verdict → library.add + buffer cleared
    + reap_log.jsonl row written.
    """
    loop = _make_loop()

    # Wire a fresh library and seed one pending candidate on the gate.
    loop._skill_library = SkillLibrary()
    loop._write_gate._pending_skills.append(_mk_pending("s_int", "req_int"))

    # Stub the judge queue length check so the early-return is bypassed.
    # In production, _write_gate_queue mirrors _pending_skills (both are
    # populated when a candidate hits defer_to_judge); for the integration
    # test we mirror that invariant via a length-only stub.
    class _StubQueue:
        def __len__(self) -> int:
            return 1

    loop._write_gate_queue = _StubQueue()

    # Stub flush_judge_round so we don't make a real LLM call.
    fake_result = BatchJudgeResult(
        candidate_judgements={
            "req_int": CandidateJudgement(
                request_id="req_int",
                decision="ADD",
                target_id=None,
                reason="ok",
            )
        },
        conflict_judgements={},
    )

    def _stub_flush_judge_round(client, *, round_id, conflict_pairs):  # noqa: ARG001
        return fake_result

    monkeypatch.setattr(
        loop._write_gate, "flush_judge_round", _stub_flush_judge_round
    )

    # Stub JudgeClient so we pass the .available() gate without an env key.
    class _StubJudgeClient:
        def available(self) -> bool:  # noqa: D401 — protocol stub
            return True

    monkeypatch.setattr(
        "src.memory.write_gate_judge.JudgeClient", _StubJudgeClient
    )

    # Redirect the reap log to tmp_path so the assertion is hermetic.
    # paths.reap_log_file() is now the sole source of the log path.
    reap_log = tmp_path / "reap_log.jsonl"
    monkeypatch.setattr(
        "src.memory.write_gate_reap.paths.reap_log_file", lambda: reap_log
    )

    # Point LOG_DIR at tmp_path (validate_on_anchor reads logs/run_*.jsonl;
    # we don't need real anchors for ADD, but keep it isolated regardless).
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))

    # Enable reap.
    monkeypatch.setattr(config, "WRITE_GATE_REAP_ENABLED", True)

    await loop._flush_write_gate_judge()

    # Skill persisted.
    assert loop._skill_library.get("s_int") is not None
    # Pending buffer drained.
    assert loop._write_gate.pending_skills() == []
    # Audit trail written.
    assert reap_log.exists()
    rows = reap_log.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 1
    entry = json.loads(rows[0])
    assert entry["decision"] == "ADD"
    assert entry["skill_id"] == "s_int"


@pytest.mark.asyncio
async def test_flush_write_gate_judge_skips_reap_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reap is gated: when WRITE_GATE_REAP_ENABLED is False, pending candidates
    stay in the buffer (legacy observation-mode behaviour).
    """
    loop = _make_loop()
    loop._skill_library = SkillLibrary()
    loop._write_gate._pending_skills.append(_mk_pending("s_int2", "req_int2"))

    class _StubQueue:
        def __len__(self) -> int:
            return 1

    loop._write_gate_queue = _StubQueue()

    fake_result = BatchJudgeResult(
        candidate_judgements={
            "req_int2": CandidateJudgement(
                request_id="req_int2",
                decision="ADD",
                target_id=None,
                reason="ok",
            )
        },
        conflict_judgements={},
    )
    monkeypatch.setattr(
        loop._write_gate,
        "flush_judge_round",
        lambda client, **kw: fake_result,  # noqa: ARG005
    )

    class _StubJudgeClient:
        def available(self) -> bool:
            return True

    monkeypatch.setattr(
        "src.memory.write_gate_judge.JudgeClient", _StubJudgeClient
    )

    reap_log = tmp_path / "reap_log.jsonl"
    monkeypatch.setattr(
        "src.memory.write_gate_reap.paths.reap_log_file", lambda: reap_log
    )
    monkeypatch.setattr(config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(config, "WRITE_GATE_REAP_ENABLED", False)

    await loop._flush_write_gate_judge()

    # Skill NOT added; pending still in buffer (observation mode).
    assert loop._skill_library.get("s_int2") is None
    assert len(loop._write_gate.pending_skills()) == 1
    # No reap log written.
    assert not reap_log.exists()
