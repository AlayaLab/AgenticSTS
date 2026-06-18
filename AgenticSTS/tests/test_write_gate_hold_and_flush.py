"""Hold-and-flush pending-buffer tests for WriteGate (Task 5).

These only exercise the buffer primitives. Task 6 wires the buffer into
``filter_skill_batch``; Task 10 wires the reap side.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from src.memory.write_gate import PendingSkillCandidate, WriteGate
from src.skills.models import Skill, SkillTrigger


def _sk(sid: str) -> Skill:
    return Skill(skill_id=sid, name=sid, content="c", trigger=SkillTrigger())


def _make_gate(tmp_path: Path) -> WriteGate:
    return WriteGate(log_path=tmp_path / "gate.jsonl")


def test_pending_skill_candidate_is_frozen():
    import dataclasses

    cand = PendingSkillCandidate(
        skill=_sk("s"),
        decision_action="defer_to_judge",
        request_id="req_1",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cand.request_id = "other"  # type: ignore[misc]


def test_pending_skill_candidate_stores_explicit_decision_action():
    """``decision_action`` is an explicit field — callers must pass it; retained
    as a field (not a default) because future kinds of held actions are
    anticipated (e.g. held-for-merge). Task 5 only covers defer_to_judge."""
    cand = PendingSkillCandidate(
        skill=_sk("s"),
        decision_action="defer_to_judge",
        request_id="req_0",
    )
    assert cand.decision_action == "defer_to_judge"
    assert cand.request_id == "req_0"
    assert cand.skill.skill_id == "s"


def test_enqueue_and_snapshot_returns_order(tmp_path: Path):
    gate = _make_gate(tmp_path)
    gate.enqueue_pending_skill(_sk("s1"), request_id="req_0")
    gate.enqueue_pending_skill(_sk("s2"), request_id="req_1")
    pending = gate.pending_skills()
    assert len(pending) == 2
    assert pending[0].skill.skill_id == "s1"
    assert pending[0].request_id == "req_0"
    assert pending[1].skill.skill_id == "s2"
    assert pending[1].request_id == "req_1"
    for p in pending:
        assert p.decision_action == "defer_to_judge"


def test_pending_skills_returns_snapshot_not_live_reference(tmp_path: Path):
    """Mutating the returned list must not affect the gate's internal buffer."""
    gate = _make_gate(tmp_path)
    gate.enqueue_pending_skill(_sk("s1"), request_id="req_0")
    snapshot = gate.pending_skills()
    snapshot.clear()
    assert len(gate.pending_skills()) == 1


def test_clear_pending_empties_buffer(tmp_path: Path):
    gate = _make_gate(tmp_path)
    gate.enqueue_pending_skill(_sk("s1"), request_id="req_0")
    gate.enqueue_pending_skill(_sk("s2"), request_id="req_1")
    assert len(gate.pending_skills()) == 2
    gate.clear_pending_skills()
    assert gate.pending_skills() == []


def test_enqueue_is_thread_safe(tmp_path: Path):
    """8 workers x 10 enqueues each must produce exactly 80 entries with no
    loss or duplication. Serves as a regression guard on the pending-lock."""
    gate = _make_gate(tmp_path)

    def worker(worker_id: int) -> None:
        for i in range(10):
            gate.enqueue_pending_skill(
                _sk(f"s_{worker_id}_{i}"),
                request_id=f"req_{worker_id}_{i}",
            )

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    pending = gate.pending_skills()
    assert len(pending) == 80
    ids = {p.skill.skill_id for p in pending}
    assert len(ids) == 80  # no duplicates, no losses


def test_filter_skill_batch_enqueues_held_onto_pending_buffer(tmp_path: Path):
    """When ``filter_skill_batch`` routes a candidate to ``held``, the candidate
    must also land on ``pending_skills`` with a non-empty ``request_id``."""
    from unittest.mock import patch
    from src.memory.write_gate import GateDecision, WriteGate

    class _FakeQueue:
        def __init__(self):
            self.calls = 0

        def enqueue(self, candidate, neighbors, spans):
            self.calls += 1
            return f"cand_{self.calls:04d}"

    queue = _FakeQueue()
    gate = WriteGate(log_path=tmp_path / "gate.jsonl", judge_queue=queue)

    defer_decision = GateDecision(
        action="defer_to_judge",
        target_id="",
        reason="below_reject_above_accept",
    )

    def fake_check(candidate, existing):
        gate._last_judge_request_id = queue.enqueue(candidate, [], [])
        return defer_decision

    with patch.object(gate, "check", side_effect=fake_check):
        kept, dropped, held = gate.filter_skill_batch(
            [_sk("s1"), _sk("s2")], [], run_id="r1",
        )

    assert kept == []
    assert dropped == []
    assert len(held) == 2

    pending = gate.pending_skills()
    assert len(pending) == 2
    assert {p.skill.skill_id for p in pending} == {"s1", "s2"}
    assert all(p.request_id for p in pending)
    assert {p.request_id for p in pending} == {"cand_0001", "cand_0002"}


def test_filter_skill_batch_held_without_queue_drops_silently(tmp_path: Path, caplog):
    """When no ``judge_queue`` is wired, held candidates must NOT enter the
    pending buffer (would produce a phantom row the reap step can't resolve)."""
    import logging
    from unittest.mock import patch
    from src.memory.write_gate import GateDecision, WriteGate

    gate = WriteGate(log_path=tmp_path / "gate.jsonl")  # no judge_queue
    defer_decision = GateDecision(
        action="defer_to_judge",
        target_id="",
        reason="below_reject_above_accept",
    )

    def fake_check(candidate, existing):
        # Simulate the real check() path: no queue -> no request_id set
        gate._last_judge_request_id = ""
        return defer_decision

    with patch.object(gate, "check", side_effect=fake_check):
        with caplog.at_level(logging.WARNING, logger="src.memory.write_gate"):
            kept, dropped, held = gate.filter_skill_batch(
                [_sk("s1")], [], run_id="r1",
            )

    assert len(held) == 1
    assert gate.pending_skills() == []
    assert any("held skill with no request_id" in rec.message for rec in caplog.records)
