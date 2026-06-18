"""Pre-write A/B validation for mistake-driven skill candidates (spec §4).

Pipeline per candidate:
    1. fetch_prompt_a  — byte-exact original prompt from run log (this file, D2)
    2. redecide_b      — N=3 strategic-tier resamples with candidate injected (D3)
    3. run_judge       — analysis-tier verdict on whether B differs from A (D4)
    4. aggregate_strict — strict 2/3 threshold + zero-harmful gate (D5)
    5. validate_candidate — orchestrator (D5)
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_prompt_a(log_path: Path, *, seq: int) -> str:
    """Fetch the N-th llm_call event's prompt from the run log.

    seq is zero-based across all llm_call events — matches the counter
    semantics of src.log.session_logger.SessionLogger.current_llm_call_seq()
    (Task B4). Non-llm_call lines are skipped.

    Raises LookupError when seq exceeds the number of llm_call events
    found in the log.
    """
    count = 0
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("event") != "llm_call":
                continue
            if count == seq:
                return obj.get("prompt", "")
            count += 1
    raise LookupError(
        f"llm_call seq={seq} not found in {log_path} (only {count} events)"
    )


# ---------------------------------------------------------------------------
# §4.1 step 5 — redecide B samples in parallel
# ---------------------------------------------------------------------------

import asyncio

from src.brain.llm_caller import call_raw


async def redecide_b(
    *,
    prompt_b: str,
    system: str,
    n: int = 3,
) -> list[str]:
    """Resample N decisions with candidate-injected prompt.

    All N calls run in parallel via asyncio.gather. Per-sample failures
    degrade gracefully: the failed sample returns an empty string, the
    others still return. Caller (judge, Task D4) treats empty strings
    as non-responses.

    Uses gameplay-strategic tier (effort=medium) so decisions look the
    same as the live agent would produce. openai_relay_profile='default'
    routes through the gameplay-tier relay rather than postrun.
    """
    tasks = [
        call_raw(
            system=system,
            prompt=prompt_b,
            effort="medium",
            call_type="mistake_redecide",
            openai_relay_profile="default",
        )
        for _ in range(n)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    texts: list[str] = []
    for r in results:
        if isinstance(r, BaseException):
            logger.warning("redecide_b sample failed: %s", r)
            texts.append("")
            continue
        text, _latency, _tokens = r
        texts.append(text)
    return texts


# ---------------------------------------------------------------------------
# §4.3 — judge prompt + verdict parsing
# ---------------------------------------------------------------------------

from dataclasses import dataclass


@dataclass(frozen=True)
class JudgeVerdict:
    """Analysis-tier judge's assessment of whether candidate steered B."""
    verdict: str       # "skill_helps" | "skill_unclear" | "skill_harmful"
    hit_count: int     # 0..N (B samples that clearly followed expected_correction)
    rationale: str = ""


_JUDGE_SYSTEM = (
    "You are a strict reviewer evaluating whether a proposed STS2 skill actually "
    "steered the agent's decision."
)


def build_judge_prompt(
    *,
    candidate_name: str,
    candidate_content: str,
    expected_correction: str,
    counterfactual_note: str,
    decision_a: str,
    decisions_b: list[str],
) -> str:
    """Build the judge prompt comparing A (original) vs B (with candidate).

    Per spec §4.3, judge determines whether >=2/3 B samples follow the
    expected correction AND differ from A (skill_helps), are mixed
    (skill_unclear), or perform worse than A (skill_harmful).
    """
    b_block = "\n".join(f"Sample {i+1}: {d}" for i, d in enumerate(decisions_b))
    return f"""You proposed this skill for an STS2 combat round:

{candidate_name}: {candidate_content}

Your stated correction:
"{expected_correction}"
"{counterfactual_note}"

## A (original decision, no skill)
{decision_a}

## B (re-decided with skill injected, {len(decisions_b)} samples)
{b_block}

Did the skill steer the agent toward the correction you proposed?

Output strict JSON:
{{
  "verdict": "skill_helps" | "skill_unclear" | "skill_harmful",
  "hit_count_B": 0..{len(decisions_b)},
  "rationale": "<=2 sentences"
}}

skill_helps:    >=2/3 B samples clearly follow expected_correction AND differ from A
skill_unclear:  1/3 or ambiguous
skill_harmful:  0/3, or B samples perform objectively worse than A
"""


def parse_judge_output(text: str) -> JudgeVerdict:
    """Parse judge JSON output; tolerate malformed/missing fields.

    Non-JSON or unknown verdicts fall back to skill_unclear / hit_count 0
    so the strict aggregation (§D5) treats them as unclear rounds —
    never as helps (which would write bad skills) or harmful (which
    would penalize on parse errors).
    """
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return JudgeVerdict(verdict="skill_unclear", hit_count=0, rationale="unparseable")

    v = obj.get("verdict", "skill_unclear")
    if v not in {"skill_helps", "skill_unclear", "skill_harmful"}:
        v = "skill_unclear"

    raw_hc = obj.get("hit_count_B", 0)
    try:
        hc = int(raw_hc)
    except (TypeError, ValueError):
        hc = 0
    hc = max(0, hc)  # clamp negatives

    return JudgeVerdict(
        verdict=v,
        hit_count=hc,
        rationale=obj.get("rationale", ""),
    )


async def run_judge(
    *,
    candidate_name: str,
    candidate_content: str,
    expected_correction: str,
    counterfactual_note: str,
    decision_a: str,
    decisions_b: list[str],
) -> JudgeVerdict:
    """Invoke the analysis-tier judge for one (A, B[:3]) comparison.

    Failures collapse to skill_unclear/0 — never crash the A/B pipeline.
    """
    prompt = build_judge_prompt(
        candidate_name=candidate_name,
        candidate_content=candidate_content,
        expected_correction=expected_correction,
        counterfactual_note=counterfactual_note,
        decision_a=decision_a,
        decisions_b=decisions_b,
    )
    try:
        text, _lat, _tok = await call_raw(
            system=_JUDGE_SYSTEM,
            prompt=prompt,
            effort="high",
            call_type="mistake_judge",
        )
    except Exception as e:
        logger.warning("judge call failed: %s", e)
        return JudgeVerdict(
            verdict="skill_unclear",
            hit_count=0,
            rationale=f"call_error:{e}",
        )
    return parse_judge_output(text)


# ---------------------------------------------------------------------------
# §D5 — strict aggregation + per-candidate validator orchestrator
# ---------------------------------------------------------------------------

import math


@dataclass(frozen=True)
class RoundJudgeResult:
    """Per-round judge verdict aggregated across N=3 B samples."""
    verdict: str    # "skill_helps" | "skill_unclear" | "skill_harmful"
    hit_count: int  # 0..samples_per_round


def aggregate_strict(
    per_round: list[RoundJudgeResult],
    *,
    samples_per_round: int = 3,
) -> bool:
    """Strict 'ning-que-wu-lan' aggregation rule (spec §4.1).

    Pass iff:
      1. No round's verdict is 'skill_harmful', AND
      2. sum(hit_count) >= ceil(total_samples * 2/3)
    where total_samples = len(per_round) * samples_per_round.

    Empty per_round → False (nothing to pass).
    """
    if not per_round:
        return False
    if any(r.verdict == "skill_harmful" for r in per_round):
        return False
    total_samples = len(per_round) * samples_per_round
    threshold = math.ceil(total_samples * 2 / 3)
    total_hits = sum(r.hit_count for r in per_round)
    return total_hits >= threshold


async def validate_candidate(
    *,
    candidate: dict,              # skill sub-dict returned by critic validator
    episode,                      # CombatEpisode
    log_path,                     # Path to logs/run_<id>.jsonl
    combat_system_prompt: str,    # system prompt the live agent used
) -> tuple[bool, list[RoundJudgeResult], int]:
    """Run A/B validation for one candidate across all its mistake rounds.

    For each mistake_round_idx (1-based to match CombatRound.round_num):
        1. Fetch original prompt via llm_call_seq from the run log
        2. Inject candidate; redecide B×3
        3. Judge verdict (skill_helps / unclear / harmful, hit_count 0..3)

    Returns (passed, per_round_results, total_hits) where passed is the
    strict aggregation outcome.
    """
    from src.skills.composer import inject_candidate_into_prompt

    round_indices = candidate.get("mistake_round_indices") or []
    per_round: list[RoundJudgeResult] = []
    total_hits = 0

    for idx in round_indices:
        # 1-based index → 0-based list access
        zero_idx = idx - 1
        if zero_idx < 0 or zero_idx >= len(episode.rounds):
            logger.warning(
                "validate_candidate: round %s out of range for episode %s",
                idx, getattr(episode, "episode_id", "?"),
            )
            per_round.append(RoundJudgeResult(verdict="skill_unclear", hit_count=0))
            continue

        rnd = episode.rounds[zero_idx]
        try:
            prompt_a = fetch_prompt_a(log_path, seq=rnd.llm_call_seq)
        except LookupError as e:
            logger.warning(
                "validate_candidate: skipping round idx=%s: %s", idx, e,
            )
            per_round.append(RoundJudgeResult(verdict="skill_unclear", hit_count=0))
            continue

        prompt_b = inject_candidate_into_prompt(
            prompt_a, name=candidate["name"], content=candidate["content"],
        )
        decisions_b = await redecide_b(
            prompt_b=prompt_b, system=combat_system_prompt, n=3,
        )
        verdict = await run_judge(
            candidate_name=candidate["name"],
            candidate_content=candidate["content"],
            expected_correction=candidate.get("expected_correction", ""),
            counterfactual_note=candidate.get("counterfactual_note", ""),
            decision_a="(see log — not shown here)",
            decisions_b=decisions_b,
        )
        per_round.append(
            RoundJudgeResult(verdict=verdict.verdict, hit_count=verdict.hit_count)
        )
        total_hits += verdict.hit_count

    return aggregate_strict(per_round), per_round, total_hits
