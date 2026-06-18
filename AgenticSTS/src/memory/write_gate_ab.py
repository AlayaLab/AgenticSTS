"""Log-grounded A/B replay for skill/memory candidates (spec §8, commit 4/4).

Validates a candidate against the exact prompt event that produced its
learning signal. Two phases:

Phase 1 (structure, deterministic) — embed the candidate and check it
    does not semantically duplicate any section already present in the
    original prompt. Runs structural conflict detection against the
    existing content. Cheap; no LLM call. Rejects here are the cheapest.

Phase 2 (quality, LLM calls) — sample the decision N times on each of
    ``prompt_A`` (original) and ``prompt_B`` (original + injected
    candidate) at the fast tier. Hard-reject if any B sample fails
    decision-schema validation (the PE-era lesson — §8.4). Otherwise
    submit the 9 cross-pairs to a judge LLM and promote iff
    ``count(BETTER_B) ≥ 2 AND count(WORSE_B) ≤ 1`` across all 9
    judgements.

Observation mode (commit 4 default): results are written to
``data/evolution/ab_replay_log.jsonl`` but the gate does NOT yet block
persistence. Flipping to enforcement is a separate, intentional change.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

import config
from src.brain.decision_parser import extract_decision
from src.memory.write_gate import (
    L1_L2_L3_REJECT_COSINE,
    Candidate,
    EmbeddingClient,
    _cosine,
)
from src.memory.write_gate_judge import (
    JudgeClient,
    JudgeUnavailableError,
    _strip_json_fence,
    find_structural_conflicts,
)

logger = logging.getLogger(__name__)


# ── Thresholds (spec §8) ────────────────────────────────────────────

PHASE1_DUPLICATE_COSINE = 0.70          # same as §4.3 L1 overlap
PHASE2_SAMPLES_PER_SIDE = 3              # user-set; spec §13.2
PHASE2_PROMOTE_BETTER_B_MIN = 2          # across 9 cross-pair judgements
PHASE2_PROMOTE_WORSE_B_MAX = 1

# Sampler tier selection (spec §13.1 OQ #2, revised 2026-04-18):
# Phase 2 *decision sampling* must match the tier that produces the real
# runtime decision — otherwise we'd be measuring skill effectiveness on a
# different model distribution than the one deployed. Default sampler is
# therefore the strategic tier (Gemini 3.1 Pro); the pair *judge* stays
# at fast tier because BETTER_B/SAME/WORSE_B is a classification task
# that does not benefit from deeper reasoning.
DEFAULT_SAMPLER_MODEL_ENV = "STS2_STRATEGIC_MODEL"
DEFAULT_SAMPLER_MODEL_FALLBACK = "gemini-3.1-pro-preview"


def _default_sampler_model() -> str:
    return os.getenv(DEFAULT_SAMPLER_MODEL_ENV, DEFAULT_SAMPLER_MODEL_FALLBACK)


def make_sampler_for_event(event: "LogEvent") -> JudgeClient:
    """Build a JudgeClient whose model matches the logged event's tier.

    Preference order:
    1. ``event.model`` if it's non-empty (exact match with the run's tier).
    2. ``STS2_STRATEGIC_MODEL`` env var.
    3. ``DEFAULT_SAMPLER_MODEL_FALLBACK`` constant.

    This keeps Phase 2 faithful to the production routing in spec §8.3:
    card_reward / shop / rest / event / combat-plan decisions go to
    strategic tier; map-step / potion / hand_select / treasure go to
    fast tier. Using the event's own model captures either correctly.
    """
    if event.model:
        return JudgeClient(model=event.model)
    return JudgeClient(model=_default_sampler_model())


# ── Data types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class LogEvent:
    """A single ``llm_call`` event loaded from a run log.

    Only the fields we need for replay.
    """

    run_id: str
    step: int
    state_type: str
    model: str
    tier: str
    system_prompt: str
    prompt: str
    messages: tuple[dict[str, str], ...]


@dataclass(frozen=True)
class ABReplayCandidate:
    """A write-gate candidate bound to a source log event for replay."""

    candidate: Candidate
    source: LogEvent | None = None            # None → use recent-event fallback
    fallback_events: tuple[LogEvent, ...] = ()


@dataclass(frozen=True)
class Phase1Result:
    passed: bool
    reason: str
    max_cosine: float = 0.0
    offending_excerpt: str = ""
    conflict_count: int = 0


@dataclass(frozen=True)
class Phase2SampleOutcome:
    """One N=3 round of decision sampling on A and B."""

    valid_a: int
    valid_b: int
    invalid_b_responses: tuple[str, ...] = ()


@dataclass(frozen=True)
class Phase2Result:
    passed: bool
    reason: str
    sample: Phase2SampleOutcome | None = None
    better_b: int = 0
    same: int = 0
    worse_b: int = 0


@dataclass(frozen=True)
class ABReplayResult:
    candidate_name: str
    final_action: Literal["promote", "reject"]
    reason: str
    phase1: Phase1Result
    phase2: Phase2Result | None  # None when Phase 1 rejected


# ── Log iteration helpers ───────────────────────────────────────────


def iter_llm_call_events(log_path: Path, *, state_type: str | None = None) -> Iterable[LogEvent]:
    """Stream ``llm_call`` events from a run log JSONL file.

    Filters by ``state_type`` when provided. Gracefully skips malformed
    lines. Yields newest-to-oldest? No — preserves file order, which is
    chronological. Callers that want "recent events" should consume the
    full iterator and slice the tail.
    """
    if not log_path.is_file():
        return
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("event") != "llm_call":
                continue
            st = str(rec.get("state_type") or "")
            if state_type is not None and st and st != state_type:
                continue
            msgs_raw = rec.get("messages") or []
            msgs: list[dict[str, str]] = []
            for m in msgs_raw:
                if isinstance(m, dict):
                    role = str(m.get("role", ""))
                    content = m.get("content", "")
                    if not isinstance(content, str):
                        content = str(content)
                    msgs.append({"role": role, "content": content})
            yield LogEvent(
                run_id=str(rec.get("run_id", "")),
                step=int(rec.get("step", 0)),
                state_type=st,
                model=str(rec.get("model", "")),
                tier=str(rec.get("tier", "")),
                system_prompt=str(rec.get("system_prompt", "")),
                prompt=str(rec.get("prompt", "")),
                messages=tuple(msgs),
            )


def recent_events_for_state(
    log_dir: Path, state_type: str, *, limit: int = 5,
) -> list[LogEvent]:
    """Return the last ``limit`` ``llm_call`` events of ``state_type`` across
    all ``run_*.jsonl`` files in ``log_dir``, newest-first.

    Implements the Phase 2 fallback described in spec §13.1 OQ #3: when a
    candidate has no ``source_log_event``, sample 5 recent same-state events.
    """
    if not log_dir.is_dir():
        return []
    all_events: list[LogEvent] = []
    for path in sorted(log_dir.glob("run_*.jsonl")):
        for ev in iter_llm_call_events(path, state_type=state_type):
            all_events.append(ev)
    # all_events is chronological oldest-first; return newest-last `limit`.
    return all_events[-limit:]


# ── Prompt B construction ───────────────────────────────────────────


_SKILL_HEADER = "## Expert Knowledge (retrieved skills)"
_CAND_HEADER = "## Extra Skill Candidate (under A/B replay)"


def _section_chunks(prompt_a: str) -> list[str]:
    """Split a large prompt into ``##``-header chunks for per-line embedding."""
    if not prompt_a:
        return []
    parts = re.split(r"\n(?=## )", prompt_a)
    return [p.strip() for p in parts if p.strip()]


def build_prompt_b(original_user_prompt: str, candidate: Candidate) -> str:
    """Splice the candidate's content into ``prompt_A`` to simulate retrieval.

    Injects under a dedicated header so the diff is unambiguous. Real
    retrieval would put the candidate under ``## Expert Knowledge``;
    keeping a distinct header here makes the delta computation trivial
    and keeps Phase 1 deterministic.
    """
    new_section = (
        f"{_CAND_HEADER}\n"
        f"**{candidate.name}**\n"
        f"{candidate.content.strip()}\n"
    )
    # Inject before "## Your Task" if present, else append before the last
    # "## " section, else append at end.
    marker = "## Your Task"
    if marker in original_user_prompt:
        idx = original_user_prompt.index(marker)
        return original_user_prompt[:idx] + new_section + "\n" + original_user_prompt[idx:]
    last_section = original_user_prompt.rfind("\n## ")
    if last_section > 0:
        return (
            original_user_prompt[:last_section + 1]
            + new_section + "\n"
            + original_user_prompt[last_section + 1:]
        )
    return original_user_prompt + "\n\n" + new_section


# ── Phase 1: structural check ──────────────────────────────────────


def run_phase1(
    candidate: Candidate,
    prompt_a: str,
    *,
    embedder: EmbeddingClient,
    duplicate_cosine: float = PHASE1_DUPLICATE_COSINE,
) -> Phase1Result:
    """Spec §8.2 — deterministic structure check.

    Embeds the candidate's content and each ``##``-section of the logged
    prompt_A. If any section has cosine ≥ threshold, REJECT. Also runs the
    §5.1 structural conflict detector over the candidate's content vs the
    section bodies (any opposing prefer/avoid under overlapping triggers
    produces a rejection).
    """
    if not candidate.content.strip():
        return Phase1Result(passed=False, reason="empty_content")

    chunks = _section_chunks(prompt_a)
    if not chunks:
        return Phase1Result(passed=True, reason="no_sections_to_compare")

    if not embedder.available():
        # Degrade: can't embed → Phase 1 falls back to pure-lexical conflict
        # detection. Duplicate detection is skipped.
        logger.info("phase1: embedder unavailable — skipping duplicate check")
        lexical_conflicts = _lexical_conflicts(candidate, chunks)
        if lexical_conflicts:
            return Phase1Result(
                passed=False,
                reason="phase1_conflict_lexical",
                conflict_count=len(lexical_conflicts),
            )
        return Phase1Result(passed=True, reason="phase1_embedder_unavailable")

    try:
        vecs = embedder.embed([candidate.content] + chunks)
    except Exception as exc:
        logger.warning("phase1 embed failed: %s — accepting by default", exc)
        return Phase1Result(passed=True, reason=f"embed_failed:{exc}")

    cand_vec = vecs[0]
    section_vecs = vecs[1:]

    max_cos = 0.0
    offending = ""
    for chunk, vec in zip(chunks, section_vecs, strict=True):
        c = _cosine(cand_vec, vec)
        if c > max_cos:
            max_cos = c
            offending = chunk[:160].replace("\n", " ")

    if max_cos >= duplicate_cosine:
        return Phase1Result(
            passed=False,
            reason="phase1_duplicate",
            max_cosine=max_cos,
            offending_excerpt=offending,
        )

    # Structural conflict pass — lexical, cheap.
    lexical_conflicts = _lexical_conflicts(candidate, chunks)
    if lexical_conflicts:
        return Phase1Result(
            passed=False,
            reason="phase1_conflict_lexical",
            max_cosine=max_cos,
            conflict_count=len(lexical_conflicts),
        )

    return Phase1Result(
        passed=True, reason="phase1_passed", max_cosine=max_cos,
    )


_PREFER_RE = re.compile(r"\b(prefer|favor|favour|always|must|priorit(?:y|ize|ise))\b", re.IGNORECASE)
_AVOID_RE = re.compile(r"\b(avoid|never|skip|don['’]?t|refuse|don\s+not)\b", re.IGNORECASE)


def _lexical_conflicts(candidate: Candidate, chunks: Sequence[str]) -> list[str]:
    """Return chunk excerpts that lexically oppose the candidate's stance."""
    cand_prefer = bool(_PREFER_RE.search(candidate.content))
    cand_avoid = bool(_AVOID_RE.search(candidate.content))
    if not (cand_prefer or cand_avoid):
        return []
    hits: list[str] = []
    for ch in chunks:
        ch_prefer = bool(_PREFER_RE.search(ch))
        ch_avoid = bool(_AVOID_RE.search(ch))
        opposed = (cand_prefer and ch_avoid) or (cand_avoid and ch_prefer)
        if opposed:
            hits.append(ch[:120].replace("\n", " "))
    return hits


# ── Phase 2: quality check ─────────────────────────────────────────


_JUDGE_SYSTEM = """\
You are evaluating two responses to the same game-state prompt. One was made
with an extra skill hint (B) and one without (A). Judge whether B's decision
is better, the same, or worse than A, considering the reasoning quality and
the correctness of the final action for the game state shown.

Respond with EXACTLY ONE WORD, chosen from: BETTER_B, SAME, WORSE_B.
No JSON, no punctuation, no explanation.
"""


def _sample_responses(
    sampler: JudgeClient, system: str, user: str, *, n: int,
) -> list[str]:
    """Strategic-tier completions used as A or B samples (N=3 per side).

    ``sampler`` should be a JudgeClient configured with the strategic-tier
    model (or ideally the exact model that produced the source log event —
    see :func:`make_sampler_for_event`). That way the decisions we grade
    come from the same distribution as the agent's real runtime output.
    """
    out: list[str] = []
    for _ in range(n):
        try:
            out.append(sampler.call(system, user, max_tokens=1024))
        except JudgeUnavailableError:
            return out
        except Exception as exc:
            logger.warning("sample call failed: %s", exc)
    return out


def _pair_judge_responses(
    judge: JudgeClient, *, context: str, response_a: str, response_b: str,
) -> str:
    """Call the pair judge once. Returns the raw verdict string."""
    user = (
        f"## Game State (prompt excerpt)\n{context[:1800]}\n\n"
        f"## Response A (without extra skill)\n{response_a[:1200]}\n\n"
        f"## Response B (with extra skill)\n{response_b[:1200]}\n"
    )
    raw = judge.call(_JUDGE_SYSTEM, user, max_tokens=16)
    return _strip_json_fence(raw).strip().upper()


def run_phase2(
    candidate: Candidate,
    prompt_a: str,
    prompt_b: str,
    system_prompt: str,
    *,
    sampler: JudgeClient,
    judge: JudgeClient,
    n_samples: int = PHASE2_SAMPLES_PER_SIDE,
) -> Phase2Result:
    """Spec §8.3 — LLM quality check.

    1. Sample N decisions on A and B.
    2. Parse through decision_parser. Hard-reject if any B sample fails.
    3. Judge the N×N cross-pairs.
    4. Promote iff ``count(BETTER_B) ≥ 2 AND count(WORSE_B) ≤ 1``.
    """
    if not sampler.available() or not judge.available():
        return Phase2Result(passed=False, reason="judge_unavailable")

    resp_a = _sample_responses(sampler, system_prompt, prompt_a, n=n_samples)
    resp_b = _sample_responses(sampler, system_prompt, prompt_b, n=n_samples)
    if len(resp_a) < n_samples or len(resp_b) < n_samples:
        return Phase2Result(passed=False, reason="sample_incomplete")

    # Strict parsing (no code-fence fallback) — this is the PE-era failure
    # mode we're catching: the patched prompt causes the model to emit JSON
    # outside the <decision> tag, and the runtime rejects it downstream.
    # Phase 2 mirrors runtime's strictest path.
    valid_a = sum(1 for r in resp_a if extract_decision(r, allow_fallback=False) is not None)
    valid_b = sum(1 for r in resp_b if extract_decision(r, allow_fallback=False) is not None)
    invalid_b_texts = tuple(
        r for r in resp_b if extract_decision(r, allow_fallback=False) is None
    )
    sample = Phase2SampleOutcome(valid_a=valid_a, valid_b=valid_b,
                                 invalid_b_responses=invalid_b_texts)

    # §8.3 step 3 — hard reject on any invalid B (the PE-era lesson).
    if valid_b < n_samples:
        return Phase2Result(
            passed=False,
            reason="invalid_b_hard_reject",
            sample=sample,
        )

    # Cross-pair judgements (N×N = 9 when n_samples=3).
    better_b = 0
    same = 0
    worse_b = 0
    for a in resp_a:
        for b in resp_b:
            try:
                verdict = _pair_judge_responses(
                    judge, context=prompt_a[:1800], response_a=a, response_b=b,
                )
            except Exception as exc:
                logger.warning("pair judge failed: %s", exc)
                continue
            if verdict.startswith("BETTER_B"):
                better_b += 1
            elif verdict.startswith("WORSE_B"):
                worse_b += 1
            elif verdict.startswith("SAME"):
                same += 1
            # Unrecognised verdicts → ignored (counted as neither)

    promote = better_b >= PHASE2_PROMOTE_BETTER_B_MIN and worse_b <= PHASE2_PROMOTE_WORSE_B_MAX
    return Phase2Result(
        passed=promote,
        reason=(
            f"promote better_b={better_b} worse_b={worse_b}"
            if promote
            else f"reject better_b={better_b} worse_b={worse_b}"
        ),
        sample=sample,
        better_b=better_b,
        same=same,
        worse_b=worse_b,
    )


# ── Replayer ────────────────────────────────────────────────────────


class ABReplayer:
    """End-to-end A/B replay for a single candidate.

    Observation-mode: result is returned to the caller; a diagnostic row
    is appended to ``data/evolution/ab_replay_log.jsonl``. The caller
    decides whether to act on ``result.final_action``.
    """

    LOG_NAME = "ab_replay_log.jsonl"

    def __init__(
        self,
        *,
        embedder: EmbeddingClient | None = None,
        sampler: JudgeClient | None = None,
        judge: JudgeClient | None = None,
        log_dir: Path | None = None,
    ) -> None:
        self._embedder = embedder or EmbeddingClient()
        # If the caller did not pass an explicit sampler, default to
        # strategic tier (see DEFAULT_SAMPLER_MODEL_ENV / spec §8.3).
        # When ``replay()`` has access to a concrete source event, we
        # upgrade to a tier-matched client via ``make_sampler_for_event``.
        self._sampler = sampler or JudgeClient(model=_default_sampler_model())
        self._judge = judge or JudgeClient()  # fast tier for verdicts
        self._explicit_sampler = sampler is not None
        self._log_path = (
            (log_dir or Path(config.EVOLUTION_DIR)) / self.LOG_NAME
        )
        self._lock = threading.Lock()

    def replay(self, ab: ABReplayCandidate) -> ABReplayResult:
        source = ab.source
        if source is None:
            if ab.fallback_events:
                source = ab.fallback_events[0]
            else:
                result = ABReplayResult(
                    candidate_name=ab.candidate.name,
                    final_action="reject",
                    reason="no_source_and_no_fallback",
                    phase1=Phase1Result(passed=False, reason="no_source_and_no_fallback"),
                    phase2=None,
                )
                self._log(result)
                return result

        # Phase 1
        p1 = run_phase1(ab.candidate, source.prompt, embedder=self._embedder)
        if not p1.passed:
            result = ABReplayResult(
                candidate_name=ab.candidate.name,
                final_action="reject",
                reason=f"phase1:{p1.reason}",
                phase1=p1,
                phase2=None,
            )
            self._log(result)
            return result

        # Phase 2 — if the caller didn't pre-configure a sampler, pick one
        # that matches the source event's tier/model. Keeps the sampling
        # distribution aligned with production routing (spec §8.3 / §13.1
        # OQ #2 revision).
        sampler = self._sampler if self._explicit_sampler else make_sampler_for_event(source)
        prompt_b = build_prompt_b(source.prompt, ab.candidate)
        p2 = run_phase2(
            ab.candidate,
            source.prompt,
            prompt_b,
            source.system_prompt,
            sampler=sampler,
            judge=self._judge,
        )
        final = "promote" if p2.passed else "reject"
        result = ABReplayResult(
            candidate_name=ab.candidate.name,
            final_action=final,
            reason=f"phase2:{p2.reason}",
            phase1=p1,
            phase2=p2,
        )
        self._log(result)
        return result

    # ── log ───────────────────────────────────────────────

    def _log(self, result: ABReplayResult) -> None:
        record: dict[str, Any] = {
            "ts": round(time.time(), 3),
            "candidate": result.candidate_name,
            "final_action": result.final_action,
            "reason": result.reason,
            "phase1": {
                "passed": result.phase1.passed,
                "reason": result.phase1.reason,
                "max_cosine": round(result.phase1.max_cosine, 3),
                "conflict_count": result.phase1.conflict_count,
            },
        }
        if result.phase2 is not None:
            record["phase2"] = {
                "passed": result.phase2.passed,
                "reason": result.phase2.reason,
                "better_b": result.phase2.better_b,
                "same": result.phase2.same,
                "worse_b": result.phase2.worse_b,
                "valid_a": result.phase2.sample.valid_a if result.phase2.sample else None,
                "valid_b": result.phase2.sample.valid_b if result.phase2.sample else None,
            }
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock, self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("ab_replay log failed: %s", exc)
