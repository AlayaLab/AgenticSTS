"""Merge pipeline: synthesise merged skills and validate via dual-anchor AB replay."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from src.brain.llm_caller import call_raw
from src.skills.models import AnchorExemplar, Skill
from src.skills.prewrite_ab import (
    RoundJudgeResult,
    aggregate_strict,
    fetch_prompt_a,
    redecide_b,
    run_judge,
)
from src.skills.composer import inject_candidate_into_prompt

logger = logging.getLogger(__name__)


async def validate_on_anchor(
    *,
    merged_skill: Skill,
    anchor: AnchorExemplar,
    log_dir: Path,
    combat_system_prompt: str,
    n_samples: int = 3,
) -> RoundJudgeResult:
    """Run one AB round on one anchor: fetch prompt_a, inject merged skill, redecide, judge.

    Anchor-resolution failures (missing log file, ``LookupError`` from
    ``fetch_prompt_a`` when the seq is out of range) collapse to
    ``RoundJudgeResult(verdict="skill_unclear", hit_count=0)`` so the caller's
    strict-aggregation gate fails closed on partial data.

    LLM-call errors from ``redecide_b`` / ``run_judge`` are **not** caught
    here — they propagate. The dual-anchor orchestrator in ``run_merge_pair``
    (Task 9) is responsible for bounding those.
    """
    log_path = log_dir / f"run_{anchor.run_id}.jsonl"
    if not log_path.exists():
        logger.warning("validate_on_anchor: log %s missing", log_path)
        return RoundJudgeResult(verdict="skill_unclear", hit_count=0)
    try:
        prompt_a = fetch_prompt_a(log_path, seq=anchor.llm_call_seq)
    except LookupError as e:
        logger.warning("validate_on_anchor: %s", e)
        return RoundJudgeResult(verdict="skill_unclear", hit_count=0)

    prompt_b = inject_candidate_into_prompt(
        prompt_a, name=merged_skill.name, content=merged_skill.content,
    )
    decisions_b = await redecide_b(
        prompt_b=prompt_b, system=combat_system_prompt, n=n_samples,
    )
    verdict = await run_judge(
        candidate_name=merged_skill.name,
        candidate_content=merged_skill.content,
        expected_correction=anchor.expected_correction,
        counterfactual_note=anchor.counterfactual_note,
        decision_a="(see log — not shown here)",
        decisions_b=decisions_b,
    )
    return RoundJudgeResult(verdict=verdict.verdict, hit_count=verdict.hit_count)


_MERGE_SYSTEM = (
    "You are a skill curator consolidating two STS2 strategy skills judged "
    "semantically redundant. Either propose a unified skill that covers BOTH "
    "situations, or declare abandon=true if they cannot be safely unified."
)


def build_merge_user_prompt(*, skill_a: Skill, skill_b: Skill) -> str:
    return f"""Two skills have been flagged as redundant by the batch judge:

## Skill A ({skill_a.skill_id})
Name: {skill_a.name}
Content: {skill_a.content}

## Skill B ({skill_b.skill_id})
Name: {skill_b.name}
Content: {skill_b.content}

Task: produce ONE merged skill that applies correctly in BOTH situations.
If the situations differ too much for a safe unified rule, set abandon=true.

Output strict JSON:
{{
  "abandon": false,
  "name": "<<=40 chars, action-phrased>",
  "content": "<<=200 chars, actionable rule>",
  "trigger_tags": ["<tag1>", "<tag2>"],
  "rationale": "<1-2 sentences why this covers both>"
}}

Conservative stance: prefer abandon=true over a vague union."""


@dataclass(frozen=True)
class MergedSkillOutput:
    abandon: bool
    name: str = ""
    content: str = ""
    trigger_tags: tuple[str, ...] = ()
    rationale: str = ""


def parse_merge_output(text: str) -> MergedSkillOutput:
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return MergedSkillOutput(abandon=True, rationale="unparseable")
    if not isinstance(obj, dict):
        return MergedSkillOutput(abandon=True, rationale="non_object_root")
    abandon_raw = obj.get("abandon", False)
    if abandon_raw is True or (
        isinstance(abandon_raw, str) and abandon_raw.strip().lower() == "true"
    ):
        return MergedSkillOutput(
            abandon=True, rationale=str(obj.get("rationale", ""))
        )
    tags_raw = obj.get("trigger_tags", ())
    if not isinstance(tags_raw, (list, tuple)):
        tags_raw = ()
    return MergedSkillOutput(
        abandon=False,
        name=str(obj.get("name", ""))[:40],
        content=str(obj.get("content", ""))[:400],
        trigger_tags=tuple(str(t) for t in tags_raw),
        rationale=str(obj.get("rationale", "")),
    )


async def run_merge_llm(*, skill_a: Skill, skill_b: Skill) -> MergedSkillOutput:
    prompt = build_merge_user_prompt(skill_a=skill_a, skill_b=skill_b)
    try:
        text, _lat, _tok = await call_raw(
            system=_MERGE_SYSTEM,
            prompt=prompt,
            effort="high",
            call_type="skill_merge",
        )
    except Exception as e:
        logger.warning("run_merge_llm: call failed: %s", e)
        return MergedSkillOutput(abandon=True, rationale=f"call_error:{e}")
    return parse_merge_output(text)


@dataclass(frozen=True)
class MergeResult:
    outcome: str   # "promote" | "abandoned" | "ab_failed"
    merged_skill: Skill | None
    reason: str
    side_a: tuple[RoundJudgeResult, ...]
    side_b: tuple[RoundJudgeResult, ...]


async def _validate_side(
    *,
    merged_skill: Skill,
    anchors: tuple[AnchorExemplar, ...],
    log_dir: Path,
    combat_system_prompt: str,
) -> tuple[RoundJudgeResult, ...]:
    if not anchors:
        return ()
    tasks = [
        validate_on_anchor(
            merged_skill=merged_skill,
            anchor=a,
            log_dir=log_dir,
            combat_system_prompt=combat_system_prompt,
        )
        for a in anchors
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[RoundJudgeResult] = []
    for r in results:
        if isinstance(r, BaseException):
            logger.warning("_validate_side: exception %s", r)
            out.append(RoundJudgeResult(verdict="skill_unclear", hit_count=0))
        else:
            out.append(r)
    return tuple(out)


async def run_merge_pair(
    *,
    skill_a: Skill,
    skill_b: Skill,
    log_dir: Path,
    combat_system_prompt: str,
) -> MergeResult:
    """Merge two skills; validate the merged skill against BOTH anchor sets.

    Strict aggregation (ceil(2/3) hits + zero skill_harmful) must pass on BOTH
    sides. Any failure → ``ab_failed``, nothing persists.
    """
    merged_out = await run_merge_llm(skill_a=skill_a, skill_b=skill_b)
    if merged_out.abandon:
        return MergeResult(
            outcome="abandoned", merged_skill=None,
            reason=merged_out.rationale or "llm_abandon",
            side_a=(), side_b=(),
        )

    parent = skill_a if skill_a.confidence >= skill_b.confidence else skill_b
    merged_skill = Skill(
        skill_id=f"sk_merged_{uuid.uuid4().hex[:8]}",
        name=merged_out.name,
        category=skill_a.category,
        content=merged_out.content,
        trigger=skill_a.trigger,
        anchor_exemplars=tuple(skill_a.anchor_exemplars) + tuple(skill_b.anchor_exemplars),
        priority=parent.priority,
        source="merged",
        source_run_ids=tuple(skill_a.source_run_ids) + tuple(skill_b.source_run_ids),
        confidence=0.70,
    )

    side_a, side_b = await asyncio.gather(
        _validate_side(
            merged_skill=merged_skill, anchors=skill_a.anchor_exemplars,
            log_dir=log_dir, combat_system_prompt=combat_system_prompt,
        ),
        _validate_side(
            merged_skill=merged_skill, anchors=skill_b.anchor_exemplars,
            log_dir=log_dir, combat_system_prompt=combat_system_prompt,
        ),
    )
    pass_a = aggregate_strict(list(side_a), samples_per_round=3) if side_a else False
    pass_b = aggregate_strict(list(side_b), samples_per_round=3) if side_b else False
    if pass_a and pass_b:
        return MergeResult(
            outcome="promote", merged_skill=merged_skill,
            reason="both_sides_pass", side_a=side_a, side_b=side_b,
        )
    return MergeResult(
        outcome="ab_failed", merged_skill=None,
        reason=f"pass_a={pass_a} pass_b={pass_b}",
        side_a=side_a, side_b=side_b,
    )
