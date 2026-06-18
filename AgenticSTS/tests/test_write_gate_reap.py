import pytest
from pathlib import Path
from src.memory.write_gate import WriteGate, PendingSkillCandidate
from src.memory.write_gate_judge import BatchJudgeResult, CandidateJudgement
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger, AnchorExemplar


def _mk_pending(skill_id="s_new", request_id="req_0"):
    sk = Skill(skill_id=skill_id, name="n", content="c", trigger=SkillTrigger())
    return PendingSkillCandidate(skill=sk, decision_action="defer_to_judge",
                                  request_id=request_id)


def _mk_gate(tmp_path):
    return WriteGate(log_path=tmp_path / "gate.jsonl")


@pytest.mark.asyncio
async def test_reap_add_persists_skill(tmp_path):
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))
    lib = SkillLibrary()

    result = BatchJudgeResult(
        candidate_judgements={
            "req_0": CandidateJudgement(
                request_id="req_0", decision="ADD", target_id=None, reason="ok"),
        },
        conflict_judgements={},
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=tmp_path / "reap.jsonl",
    )
    assert stats["added"] == 1
    assert lib.get("s_new") is not None
    assert gate.pending_skills() == []


@pytest.mark.asyncio
async def test_reap_reject_drops_skill(tmp_path):
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))
    lib = SkillLibrary()
    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="REJECT", target_id=None, reason="dup")},
        conflict_judgements={},
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=tmp_path / "reap.jsonl",
    )
    assert stats["rejected"] == 1
    assert lib.get("s_new") is None


@pytest.mark.asyncio
async def test_reap_unjudged_drops_conservatively(tmp_path):
    """宁缺毋滥: a pending candidate with no matching judgement is dropped."""
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_missing"))
    lib = SkillLibrary()
    result = BatchJudgeResult(
        candidate_judgements={},
        conflict_judgements={},
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=tmp_path / "reap.jsonl",
    )
    assert stats["unjudged"] == 1
    assert lib.get("s_new") is None


@pytest.mark.asyncio
async def test_reap_merge_invokes_pipeline_and_replaces(tmp_path, monkeypatch):
    from src.memory.write_gate_reap import reap_judge_verdicts
    from src.skills import merge_pipeline as mp

    lib = SkillLibrary()
    target = Skill(skill_id="s_old", name="old", content="co", trigger=SkillTrigger())
    lib.add(target)
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))

    async def fake_merge(**kw):
        return mp.MergeResult(
            outcome="promote",
            merged_skill=Skill(skill_id="s_merged", name="m", content="cm",
                               trigger=SkillTrigger()),
            reason="ok", side_a=(), side_b=(),
        )
    monkeypatch.setattr(
        "src.memory.write_gate_reap.run_merge_pair", fake_merge)

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="MERGE", target_id="s_old",
            reason="redundant")},
        conflict_judgements={},
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=tmp_path / "reap.jsonl",
    )
    assert stats["merged"] == 1
    assert lib.get("s_old").active is False
    assert lib.get("s_merged") is not None


@pytest.mark.asyncio
async def test_reap_merge_ab_failed_drops(tmp_path, monkeypatch):
    from src.memory.write_gate_reap import reap_judge_verdicts
    from src.skills import merge_pipeline as mp
    lib = SkillLibrary()
    target = Skill(skill_id="s_old", name="old", content="co", trigger=SkillTrigger())
    lib.add(target)
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))

    async def fake_merge(**kw):
        return mp.MergeResult(outcome="ab_failed", merged_skill=None,
                              reason="side_b_harmful", side_a=(), side_b=())
    monkeypatch.setattr("src.memory.write_gate_reap.run_merge_pair", fake_merge)

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="MERGE", target_id="s_old",
            reason="redundant")},
        conflict_judgements={},
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=tmp_path / "reap.jsonl",
    )
    assert stats["merge_ab_failed"] == 1
    assert lib.get("s_old").active is True
    assert lib.get("s_new") is None


@pytest.mark.asyncio
async def test_reap_update_replaces(tmp_path):
    from src.memory.write_gate_reap import reap_judge_verdicts
    lib = SkillLibrary()
    lib.add(Skill(skill_id="s_old", name="old", content="co",
                  trigger=SkillTrigger()))
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="UPDATE", target_id="s_old",
            reason="refinement")},
        conflict_judgements={},
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=tmp_path / "reap.jsonl",
    )
    assert stats["updated"] == 1
    assert lib.get("s_old").active is False
    assert lib.get("s_new").active is True


@pytest.mark.asyncio
async def test_reap_merge_exception_drops(tmp_path, monkeypatch):
    """run_merge_pair raising must not abort the reap loop or skip pending-clear."""
    from src.memory.write_gate_reap import reap_judge_verdicts

    lib = SkillLibrary()
    target = Skill(skill_id="s_old", name="old", content="co", trigger=SkillTrigger())
    lib.add(target)
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))

    async def fake(**kw):
        raise RuntimeError("validation timeout")

    monkeypatch.setattr("src.memory.write_gate_reap.run_merge_pair", fake)

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="MERGE", target_id="s_old",
            reason="redundant")},
        conflict_judgements={},
    )
    reap_log = tmp_path / "reap.jsonl"
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=reap_log,
    )
    assert stats["merge_ab_failed"] == 1
    # Target untouched: replace was never reached.
    assert lib.get("s_old").active is True
    # Pending buffer cleared via finally — no double-processing next run.
    assert gate.pending_skills() == []
    # Entry was still written so failure is auditable.
    assert reap_log.exists()
    import json
    entry = json.loads(reap_log.read_text(encoding="utf-8").splitlines()[0])
    assert "merge_exception" in entry["reason"]


@pytest.mark.asyncio
async def test_reap_update_missing_target_falls_back_to_add(tmp_path):
    """UPDATE with unknown target_id falls back to add and tags the reason."""
    from src.memory.write_gate_reap import reap_judge_verdicts

    lib = SkillLibrary()  # empty: target does not exist
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="UPDATE", target_id="nonexistent",
            reason="refinement")},
        conflict_judgements={},
    )
    reap_log = tmp_path / "reap.jsonl"
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
        reap_log_path=reap_log,
    )
    assert stats["added"] == 1
    assert stats["updated"] == 0
    assert lib.get("s_new") is not None
    import json
    entry = json.loads(reap_log.read_text(encoding="utf-8").splitlines()[0])
    assert "missing_target_fallback_add" in entry["reason"]


@pytest.mark.asyncio
async def test_reap_writes_reap_log(tmp_path):
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = _mk_gate(tmp_path)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))
    lib = SkillLibrary()
    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="ADD", target_id=None, reason="ok")},
        conflict_judgements={},
    )
    reap_log = tmp_path / "reap_log.jsonl"
    await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys", reap_log_path=reap_log,
    )
    assert reap_log.exists()
    content = reap_log.read_text(encoding="utf-8").splitlines()
    assert len(content) == 1
    import json
    entry = json.loads(content[0])
    assert entry["decision"] == "ADD"
    assert entry["skill_id"] == "s_new"
