import pytest
from pathlib import Path
from src.skills.models import AnchorExemplar, Skill, SkillTrigger


@pytest.mark.asyncio
async def test_validate_on_anchor_happy_path(monkeypatch, tmp_path: Path):
    from src.skills import merge_pipeline as mp

    # Create a synthetic run log with one llm_call event at seq=0
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "run_abc.jsonl"
    log_path.write_text(
        '{"event":"llm_call","prompt":"original prompt body"}\n',
        encoding="utf-8",
    )

    # Mock redecide_b + run_judge
    async def fake_redecide(*, prompt_b, system, n):
        return ["decision1"] * n

    async def fake_judge(**kw):
        from src.skills.prewrite_ab import JudgeVerdict
        return JudgeVerdict(verdict="skill_helps", hit_count=3, rationale="ok")

    monkeypatch.setattr(mp, "redecide_b", fake_redecide)
    monkeypatch.setattr(mp, "run_judge", fake_judge)

    skill = Skill(skill_id="s", name="merged", content="tip", trigger=SkillTrigger())
    anchor = AnchorExemplar(run_id="abc", llm_call_seq=0, expected_correction="X")

    round_result = await mp.validate_on_anchor(
        merged_skill=skill, anchor=anchor, log_dir=log_dir,
        combat_system_prompt="sys",
    )
    assert round_result.verdict == "skill_helps"
    assert round_result.hit_count == 3


@pytest.mark.asyncio
async def test_validate_on_anchor_missing_log_returns_unclear(tmp_path):
    from src.skills import merge_pipeline as mp
    skill = Skill(skill_id="s", name="m", content="c", trigger=SkillTrigger())
    anchor = AnchorExemplar(run_id="ghost", llm_call_seq=0, expected_correction="X")

    result = await mp.validate_on_anchor(
        merged_skill=skill, anchor=anchor, log_dir=tmp_path,
        combat_system_prompt="sys",
    )
    assert result.verdict == "skill_unclear"
    assert result.hit_count == 0


def test_parse_merge_output_happy():
    from src.skills.merge_pipeline import parse_merge_output
    raw = '{"abandon": false, "name": "merged", "content": "tip", ' \
          '"trigger_tags": ["elite", "low_hp"], "rationale": "covers both"}'
    out = parse_merge_output(raw)
    assert out.abandon is False
    assert out.name == "merged"
    assert out.trigger_tags == ("elite", "low_hp")


def test_parse_merge_output_abandon():
    from src.skills.merge_pipeline import parse_merge_output
    out = parse_merge_output('{"abandon": true, "rationale": "too different"}')
    assert out.abandon is True


def test_parse_merge_output_malformed_defaults_to_abandon():
    from src.skills.merge_pipeline import parse_merge_output
    out = parse_merge_output("not json at all")
    assert out.abandon is True  # conservative: drop on parse error


def test_parse_merge_output_abandon_as_string_true():
    """LLM may stringify the bool — ``"true"`` / ``"True"`` must still abandon."""
    from src.skills.merge_pipeline import parse_merge_output
    out = parse_merge_output('{"abandon": "true", "rationale": "oops"}')
    assert out.abandon is True
    out2 = parse_merge_output('{"abandon": "True"}')
    assert out2.abandon is True


def test_parse_merge_output_non_dict_root_defaults_to_abandon():
    """JSON root may be null / list / scalar — must not crash."""
    from src.skills.merge_pipeline import parse_merge_output
    for raw in ("null", "42", "[]", '"just a string"'):
        out = parse_merge_output(raw)
        assert out.abandon is True, f"raw={raw!r} should abandon"


def test_parse_merge_output_non_list_trigger_tags_defaults_to_empty():
    """Malformed ``trigger_tags`` (int / dict / None) must not raise."""
    from src.skills.merge_pipeline import parse_merge_output
    out = parse_merge_output(
        '{"abandon": false, "name": "ok", "content": "c", "trigger_tags": 42}'
    )
    assert out.abandon is False
    assert out.trigger_tags == ()
    out2 = parse_merge_output(
        '{"abandon": false, "name": "ok", "content": "c", "trigger_tags": {"a": 1}}'
    )
    assert out2.trigger_tags == ()


@pytest.mark.asyncio
async def test_run_merge_llm_happy(monkeypatch):
    from src.skills import merge_pipeline as mp
    from src.skills.models import Skill, SkillTrigger

    async def fake_call_raw(**kw):
        return ('{"abandon": false, "name": "merged", "content": "c", '
                '"trigger_tags": ["x"], "rationale": "r"}', 0.1, {})
    monkeypatch.setattr(mp, "call_raw", fake_call_raw)

    sk_a = Skill(skill_id="a", name="A", content="ca", trigger=SkillTrigger())
    sk_b = Skill(skill_id="b", name="B", content="cb", trigger=SkillTrigger())
    out = await mp.run_merge_llm(skill_a=sk_a, skill_b=sk_b)
    assert out.abandon is False
    assert out.name == "merged"


# ---------------------------------------------------------------------------
# Helpers for Task 9 tests
# ---------------------------------------------------------------------------

def _mk_sk(skill_id: str, *, run_id: str) -> Skill:
    """One-anchor test skill."""
    return Skill(
        skill_id=skill_id, name=skill_id.upper(), content="c",
        trigger=SkillTrigger(),
        anchor_exemplars=(AnchorExemplar(run_id=run_id, llm_call_seq=0,
                                         expected_correction=f"x_{run_id}"),),
    )


def _mk_sk_with_n_anchors(skill_id: str, run_id: str, n: int) -> Skill:
    """N-anchor test skill for strict-aggregation tests."""
    return Skill(
        skill_id=skill_id, name=skill_id.upper(), content="c",
        trigger=SkillTrigger(),
        anchor_exemplars=tuple(
            AnchorExemplar(run_id=run_id, llm_call_seq=i,
                           expected_correction=f"x_{run_id}_{i}")
            for i in range(n)
        ),
    )


# ---------------------------------------------------------------------------
# Task 9 tests: run_merge_pair
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_merge_pair_promote_path(monkeypatch, tmp_path):
    from src.skills import merge_pipeline as mp
    from src.skills.models import Skill, SkillTrigger, AnchorExemplar
    from src.skills.prewrite_ab import RoundJudgeResult

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "run_a.jsonl").write_text(
        '{"event":"llm_call","prompt":"pa"}\n', encoding="utf-8")
    (log_dir / "run_b.jsonl").write_text(
        '{"event":"llm_call","prompt":"pb"}\n', encoding="utf-8")

    async def fake_merge_llm(**kw):
        return mp.MergedSkillOutput(
            abandon=False, name="U", content="c",
            trigger_tags=("t",), rationale="ok")

    async def fake_validate(**kw):
        return RoundJudgeResult(verdict="skill_helps", hit_count=3)

    monkeypatch.setattr(mp, "run_merge_llm", fake_merge_llm)
    monkeypatch.setattr(mp, "validate_on_anchor", fake_validate)

    sk_a = Skill(
        skill_id="sa", name="A", content="ca", trigger=SkillTrigger(),
        anchor_exemplars=(AnchorExemplar(run_id="a", llm_call_seq=0,
                                         expected_correction="xa"),))
    sk_b = Skill(
        skill_id="sb", name="B", content="cb", trigger=SkillTrigger(),
        anchor_exemplars=(AnchorExemplar(run_id="b", llm_call_seq=0,
                                         expected_correction="xb"),))

    result = await mp.run_merge_pair(
        skill_a=sk_a, skill_b=sk_b, log_dir=log_dir,
        combat_system_prompt="sys",
    )
    assert result.outcome == "promote"
    assert result.merged_skill is not None
    # Union anchors
    assert len(result.merged_skill.anchor_exemplars) == 2
    # Inherits A's trigger
    assert result.merged_skill.trigger == sk_a.trigger


@pytest.mark.asyncio
async def test_run_merge_pair_abandoned(monkeypatch, tmp_path):
    from src.skills import merge_pipeline as mp

    async def fake_merge_llm(**kw):
        return mp.MergedSkillOutput(abandon=True, rationale="too different")
    monkeypatch.setattr(mp, "run_merge_llm", fake_merge_llm)

    sk_a = _mk_sk("sa", run_id="a")
    sk_b = _mk_sk("sb", run_id="b")
    result = await mp.run_merge_pair(
        skill_a=sk_a, skill_b=sk_b, log_dir=tmp_path, combat_system_prompt="sys")
    assert result.outcome == "abandoned"
    assert result.merged_skill is None


@pytest.mark.asyncio
async def test_run_merge_pair_ab_failed_side_a(monkeypatch, tmp_path):
    """Side A passes, Side B returns skill_harmful → strict aggregation drops pair."""
    from src.skills import merge_pipeline as mp
    from src.skills.prewrite_ab import RoundJudgeResult

    async def fake_merge_llm(**kw):
        return mp.MergedSkillOutput(abandon=False, name="U", content="c",
                                    trigger_tags=(), rationale="ok")

    call_count = {"n": 0}
    async def fake_validate(**kw):
        call_count["n"] += 1
        # first 3 calls (side A) pass; rest (side B) return harmful
        if call_count["n"] <= 3:
            return RoundJudgeResult(verdict="skill_helps", hit_count=3)
        return RoundJudgeResult(verdict="skill_harmful", hit_count=0)

    monkeypatch.setattr(mp, "run_merge_llm", fake_merge_llm)
    monkeypatch.setattr(mp, "validate_on_anchor", fake_validate)
    sk_a = _mk_sk_with_n_anchors("sa", "a", 3)
    sk_b = _mk_sk_with_n_anchors("sb", "b", 3)
    result = await mp.run_merge_pair(
        skill_a=sk_a, skill_b=sk_b, log_dir=tmp_path, combat_system_prompt="sys")
    assert result.outcome == "ab_failed"
    assert result.merged_skill is None
