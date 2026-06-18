from src.skills.composer import inject_candidate_into_prompt


def test_inject_appends_to_existing_expert_knowledge_block():
    prompt = "## Something\ntext\n\n## Expert Knowledge\n- skill X: do Y\n\n## Your Task\n..."
    out = inject_candidate_into_prompt(prompt, name="NewSkill", content="Do Z instead of W")
    assert "- skill X: do Y" in out
    assert "NewSkill" in out
    assert "candidate" in out.lower()
    # Original skill still present BEFORE the new one
    i1 = out.index("skill X: do Y")
    i2 = out.index("NewSkill")
    assert i1 < i2


def test_inject_creates_block_when_missing():
    prompt = "## Something\ntext\n\n## Your Task\n..."
    out = inject_candidate_into_prompt(prompt, name="NewSkill", content="Do Z")
    assert "## Expert Knowledge" in out
    assert "NewSkill" in out
    # Block must appear BEFORE Your Task
    assert out.index("## Expert Knowledge") < out.index("## Your Task")


def test_inject_creates_block_when_no_your_task_marker():
    prompt = "Some prompt text with no markers at all."
    out = inject_candidate_into_prompt(prompt, name="X", content="Do X")
    assert "## Expert Knowledge" in out
    assert "X" in out


import json
import tempfile
from pathlib import Path

import pytest


def test_fetch_prompt_a_reads_jsonl_by_seq():
    from src.skills.prewrite_ab import fetch_prompt_a
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "run.jsonl"
        with p.open("w") as f:
            # Event without llm_call is skipped; seq counts only llm_calls
            f.write(json.dumps({"event": "round_end"}) + "\n")
            f.write(json.dumps({"event": "llm_call", "prompt": "PROMPT_0", "tier": "fast"}) + "\n")
            f.write(json.dumps({"event": "combat_start"}) + "\n")
            f.write(json.dumps({"event": "llm_call", "prompt": "PROMPT_1", "tier": "strategic"}) + "\n")
            f.write(json.dumps({"event": "llm_call", "prompt": "PROMPT_2", "tier": "strategic"}) + "\n")
        assert fetch_prompt_a(p, seq=0) == "PROMPT_0"
        assert fetch_prompt_a(p, seq=1) == "PROMPT_1"
        assert fetch_prompt_a(p, seq=2) == "PROMPT_2"


def test_fetch_prompt_a_missing_seq_raises():
    from src.skills.prewrite_ab import fetch_prompt_a
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "run.jsonl"
        p.write_text(json.dumps({"event": "llm_call", "prompt": "only"}) + "\n")
        with pytest.raises(LookupError):
            fetch_prompt_a(p, seq=5)


import asyncio


def test_redecide_b_runs_three_in_parallel(monkeypatch):
    from src.skills.prewrite_ab import redecide_b
    calls: list[str] = []

    async def fake_call_raw(*, system="", prompt="", **kw):
        calls.append(prompt[:20])
        return f"response_for_{len(calls)}", 0.5, 5

    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    result = asyncio.run(redecide_b(
        prompt_b="## Expert Knowledge\n- x\n## Your Task\npick a card",
        system="system prompt",
        n=3,
    ))
    assert len(result) == 3
    assert all("response_for_" in r for r in result)
    assert len(calls) == 3


def test_redecide_b_tolerates_per_sample_exception(monkeypatch):
    """A failing sample returns empty string; other samples still proceed."""
    from src.skills.prewrite_ab import redecide_b

    call_n = {"i": 0}

    async def fake_call_raw(*, system="", prompt="", **kw):
        call_n["i"] += 1
        if call_n["i"] == 2:
            raise RuntimeError("sample 2 blew up")
        return f"ok_{call_n['i']}", 0.5, 5

    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    result = asyncio.run(redecide_b(
        prompt_b="prompt", system="sys", n=3,
    ))
    assert len(result) == 3
    # Exactly one should be empty (the failed one)
    assert result.count("") == 1
    # The other two should start with "ok_"
    assert sum(1 for r in result if r.startswith("ok_")) == 2


def test_build_judge_prompt_contains_all_samples():
    from src.skills.prewrite_ab import build_judge_prompt
    p = build_judge_prompt(
        candidate_name="X", candidate_content="do Y",
        expected_correction="play Defend turn 1",
        counterfactual_note="would have avoided 8 dmg",
        decision_a="played Strike",
        decisions_b=["Defend", "Defend", "Strike"],
    )
    assert "X" in p and "do Y" in p
    assert "## A (" in p and "## B (" in p
    assert "Defend" in p
    assert "skill_helps" in p and "skill_harmful" in p
    assert "hit_count_B" in p


def test_parse_judge_output_valid():
    from src.skills.prewrite_ab import parse_judge_output, JudgeVerdict
    raw = json.dumps({"verdict": "skill_helps", "hit_count_B": 2, "rationale": "B follows correction"})
    v = parse_judge_output(raw)
    assert v.verdict == "skill_helps"
    assert v.hit_count == 2


def test_parse_judge_output_invalid_falls_back_unclear():
    from src.skills.prewrite_ab import parse_judge_output
    v = parse_judge_output("not json")
    assert v.verdict == "skill_unclear"
    assert v.hit_count == 0


def test_parse_judge_output_unknown_verdict_falls_back_unclear():
    from src.skills.prewrite_ab import parse_judge_output
    raw = json.dumps({"verdict": "bogus_value", "hit_count_B": 5})
    v = parse_judge_output(raw)
    assert v.verdict == "skill_unclear"
    assert v.hit_count == 5  # hit_count passed through even when verdict unknown


def test_parse_judge_output_negative_hit_clamped():
    from src.skills.prewrite_ab import parse_judge_output
    raw = json.dumps({"verdict": "skill_helps", "hit_count_B": -3})
    v = parse_judge_output(raw)
    assert v.hit_count == 0  # negative clamped to 0


def test_strict_aggregation_passes():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    per_round = [
        RoundJudgeResult(verdict="skill_helps", hit_count=3),
        RoundJudgeResult(verdict="skill_helps", hit_count=1),  # 4/6 total
    ]
    assert aggregate_strict(per_round, samples_per_round=3) is True


def test_strict_aggregation_fails_below_threshold():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    per_round = [
        RoundJudgeResult(verdict="skill_helps", hit_count=2),
        RoundJudgeResult(verdict="skill_unclear", hit_count=1),  # 3/6
    ]
    assert aggregate_strict(per_round, samples_per_round=3) is False


def test_strict_aggregation_fails_on_any_harmful_round():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    per_round = [
        RoundJudgeResult(verdict="skill_helps", hit_count=3),
        RoundJudgeResult(verdict="skill_harmful", hit_count=0),
    ]
    assert aggregate_strict(per_round, samples_per_round=3) is False


def test_strict_aggregation_single_round_needs_two_of_three():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    # 1 round × 3 samples = 3 total; ceil(3 * 2/3) = 2
    assert aggregate_strict([RoundJudgeResult("skill_helps", 2)], samples_per_round=3) is True
    assert aggregate_strict([RoundJudgeResult("skill_unclear", 1)], samples_per_round=3) is False


def test_strict_aggregation_empty_rounds_fails():
    from src.skills.prewrite_ab import aggregate_strict
    assert aggregate_strict([], samples_per_round=3) is False


def test_validate_candidate_happy_path(monkeypatch, tmp_path):
    """End-to-end: 2 mistake rounds, mocked LLM cooperates, strict aggregation passes."""
    from src.skills.prewrite_ab import validate_candidate
    from src.memory.models_v2 import CombatEpisode, CombatRound

    # Build an episode with rounds at seq=1 and seq=2 (1-based indices 1,2)
    r1 = CombatRound(round_num=1, llm_call_seq=1)
    r2 = CombatRound(round_num=2, llm_call_seq=2)
    ep = CombatEpisode(
        run_id="rx", enemy_key="Rat", combat_type="monster",
        character="silent", act=1, hp_before=50,
        rounds=(r1, r2),
    )

    # Run log with 3 llm_call events (seq 0, 1, 2)
    log = tmp_path / "run.jsonl"
    with log.open("w") as f:
        for i in range(3):
            f.write(json.dumps({"event": "llm_call", "prompt": f"P{i}"}) + "\n")

    candidate = {
        "name": "TestSkill",
        "content": "Do X",
        "expected_correction": "play Defend",
        "counterfactual_note": "would save 5 dmg",
        "mistake_round_indices": [1, 2],  # 1-based: round_num 1 and 2
    }

    async def fake_call_raw(*, system="", prompt="", call_type="", **kw):
        if call_type == "mistake_redecide":
            return "response: Defend -> self", 0.1, 1
        if call_type == "mistake_judge":
            return json.dumps({"verdict": "skill_helps", "hit_count_B": 2, "rationale": "ok"}), 0.1, 1
        return "", 0.0, 0

    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    passed, per_round, hits = asyncio.run(validate_candidate(
        candidate=candidate, episode=ep, log_path=log,
        combat_system_prompt="system",
    ))

    # 2 rounds × 3 samples = 6; threshold = ceil(6 × 2/3) = 4; hits = 2 + 2 = 4 → pass
    assert passed is True
    assert hits == 4
    assert len(per_round) == 2


def test_validate_candidate_fails_on_missing_seq(monkeypatch, tmp_path):
    """A round with llm_call_seq pointing to a missing log entry becomes unclear, not crash."""
    from src.skills.prewrite_ab import validate_candidate
    from src.memory.models_v2 import CombatEpisode, CombatRound

    r1 = CombatRound(round_num=1, llm_call_seq=99)  # seq 99 not in log
    ep = CombatEpisode(
        run_id="rx", enemy_key="Rat", combat_type="monster",
        character="silent", act=1, hp_before=50,
        rounds=(r1,),
    )
    log = tmp_path / "run.jsonl"
    log.write_text(json.dumps({"event": "llm_call", "prompt": "P0"}) + "\n")

    candidate = {
        "name": "X", "content": "do X", "expected_correction": "y",
        "counterfactual_note": "z", "mistake_round_indices": [1],
    }

    # call_raw should never be called (LookupError comes first)
    async def fake_call_raw(**kw): raise AssertionError("should not be called")
    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    passed, per_round, hits = asyncio.run(validate_candidate(
        candidate=candidate, episode=ep, log_path=log, combat_system_prompt="s",
    ))
    assert passed is False
    assert len(per_round) == 1
    assert per_round[0].verdict == "skill_unclear"
    assert hits == 0
