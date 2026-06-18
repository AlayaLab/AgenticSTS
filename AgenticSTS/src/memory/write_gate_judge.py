"""Level 4 batch LLM judge + cross-store conflict detection (commit 2/4).

Implements §4.4 (Level 4 batch judge) and §5 (cross-store conflict detection)
from ``docs/superpowers/specs/2026-04-18-write-gate-and-retriever-filter-design.md``.

The judge runs at end-of-postrun on:
1. All candidates that ``WriteGate.check`` deferred to Level 4.
2. All disputed pairs detected by ``find_structural_conflicts`` over the
   current L4/L5 store.

A single fast-tier LLM call covers everything for the run, returning a
structured JSON list with one entry per (candidate or pair).

Public surface:
    JudgeClient — wraps the fast-tier OpenAI-compatible chat completion call.
    JudgeQueue — accumulates deferred candidates during postrun.
    JudgeRequest / CandidateJudgement / ConflictJudgement — data types.
    batch_judge(client, requests) -> dict — main entry point.
    find_structural_conflicts(entries) -> list[ConflictPair] — §5.1.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Literal, Sequence

import config
from src.memory.write_gate import (
    Candidate,
    ExistingEntry,
    GateDecision,
    StaticSpan,
    _jaccard,
    _normalize_openai_base_url,
    _relay_for_model,
)

logger = logging.getLogger(__name__)


# ── Data types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CandidateNeighbor:
    """A nearest-neighbor for a deferred candidate, with similarity context."""

    entry_id: str
    layer: Literal["L4", "L5"]
    content: str
    cosine: float
    trigger_jaccard: float


@dataclass(frozen=True)
class JudgeRequest:
    """One judgement task for the batch LLM call.

    For candidate judgements: ``kind == 'candidate'``. ``candidate`` is the new
    skill/guide/rule; ``neighbors`` are its top-k existing-entry comparisons
    (sorted by cosine desc); ``l1_spans`` are L1/L2/L3 spans whose cosine to
    the candidate exceeded the §13.2 ``L1_L2_L3_JUDGE_LOWER`` threshold.

    For conflict judgements: ``kind == 'conflict'``. ``pair`` holds the two
    existing entries flagged by the structural detector.
    """

    kind: Literal["candidate", "conflict"]
    request_id: str
    candidate: Candidate | None = None
    neighbors: tuple[CandidateNeighbor, ...] = ()
    l1_spans: tuple[StaticSpan, ...] = ()
    pair: tuple[ExistingEntry, ExistingEntry] | None = None


@dataclass(frozen=True)
class CandidateJudgement:
    request_id: str
    decision: Literal["ADD", "UPDATE", "MERGE", "REJECT"]
    target_id: str | None
    reason: str


@dataclass(frozen=True)
class ConflictJudgement:
    request_id: str
    verdict: Literal["contradiction", "complementary", "redundant"]
    resolution: Literal["keep_higher_confidence", "merge", "both_coexist"]
    reason: str


# ── Conflict detection (§5.1) ────────────────────────────────────────


# Recognised action-predicate phrases. Conservative on purpose — false positives
# here are cheap (the pair just goes to the LLM judge anyway), false negatives
# silently let conflicts slip through. We bias toward recall.
_PREFER_RE = re.compile(r"\b(prefer|favor|favour|always|must|priorit(?:y|ize|ise))\b", re.IGNORECASE)
_AVOID_RE = re.compile(r"\b(avoid|never|skip|don['’]?t|refuse|don\s+not)\b", re.IGNORECASE)


def _has_prefer(text: str) -> bool:
    return bool(_PREFER_RE.search(text))


def _has_avoid(text: str) -> bool:
    return bool(_AVOID_RE.search(text))


@dataclass(frozen=True)
class ConflictPair:
    """A structural-conflict candidate pair from §5.1."""

    a: ExistingEntry
    b: ExistingEntry
    trigger_jaccard: float
    content_cosine: float  # 0.0 when detector ran without embeddings
    reason: str  # short label e.g. "prefer_vs_avoid"


def find_structural_conflicts(
    entries: Sequence[ExistingEntry],
    *,
    min_trigger_jaccard: float = 0.60,
    embedder: object | None = None,
    min_content_cosine: float = 0.60,
) -> list[ConflictPair]:
    """§5.1: pair-wise scan for entries with overlapping triggers, topical
    similarity, AND opposing action predicates.

    Returns each pair at most once (entries are ordered by id within a pair
    to deduplicate). Heuristic — the LLM judge in §5.2 makes the final
    call; this is just a cheap pre-filter so the judge only sees plausibly
    contradictory pairs.

    Topical overlap requirement (added 2026-04-18 from first-run calibration
    data — before this, the detector was flooding the judge with 40+
    false positives per postrun). When an ``embedder`` is provided and
    available, the cheap prefer/avoid filter is further narrowed to pairs
    whose content embeddings sit above ``min_content_cosine``. Two skills
    that happen to share triggers and both use ``always`` / ``never`` but
    are on completely different topics (e.g. "USE ALL POTIONS" vs
    "ALWAYS apply Weak to top attacker") are no longer flagged.

    When ``embedder`` is ``None`` or the embed call fails, the content
    check is skipped and the old pure-lexical behaviour is preserved —
    callers get a ``content_cosine=0.0`` marker in the returned pairs.
    """
    entries = list(entries)
    out: list[ConflictPair] = []
    seen: set[tuple[str, str]] = set()

    # Only embed pairs that pass the trigger+predicate pre-filter, so we
    # don't pay for embeddings on the huge majority of non-conflict pairs.
    # First pass: collect candidate pairs.
    candidate_pairs: list[tuple[ExistingEntry, ExistingEntry, float]] = []
    for i, a in enumerate(entries):
        for b in entries[i + 1:]:
            if a.id == b.id:
                continue
            key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
            if key in seen:
                continue
            j = _jaccard(a.trigger_tags, b.trigger_tags)
            if j < min_trigger_jaccard:
                continue
            a_prefer = _has_prefer(a.content)
            a_avoid = _has_avoid(a.content)
            b_prefer = _has_prefer(b.content)
            b_avoid = _has_avoid(b.content)
            opposed = (a_prefer and b_avoid) or (a_avoid and b_prefer)
            if not opposed:
                continue
            seen.add(key)
            candidate_pairs.append((a, b, j))

    if not candidate_pairs:
        return []

    # Second pass: content-cosine filter. Skipped when no embedder, or when
    # the embedder call fails (graceful degradation).
    use_cosine = embedder is not None and getattr(embedder, "available", lambda: False)()
    content_vecs: dict[str, list[float]] = {}
    if use_cosine:
        unique_texts: dict[str, str] = {}
        for a, b, _ in candidate_pairs:
            unique_texts.setdefault(a.id, a.content)
            unique_texts.setdefault(b.id, b.content)
        try:
            ids = list(unique_texts.keys())
            vecs = embedder.embed([unique_texts[i] for i in ids])
            content_vecs = dict(zip(ids, vecs, strict=True))
        except Exception as exc:
            logger.warning(
                "conflict-detector embed failed (%s) — falling back to "
                "lexical-only (may flag false positives)", exc,
            )
            use_cosine = False

    for a, b, j in candidate_pairs:
        cos = 0.0
        if use_cosine and a.id in content_vecs and b.id in content_vecs:
            # Compute cosine inline (avoid import cycle with write_gate).
            va, vb = content_vecs[a.id], content_vecs[b.id]
            dot = sum(x * y for x, y in zip(va, vb, strict=True))
            na = sum(x * x for x in va) ** 0.5
            nb = sum(y * y for y in vb) ** 0.5
            cos = dot / (na * nb) if na > 0 and nb > 0 else 0.0
            if cos < min_content_cosine:
                continue
        out.append(
            ConflictPair(
                a=a,
                b=b,
                trigger_jaccard=j,
                content_cosine=cos,
                reason="prefer_vs_avoid",
            )
        )
    return out


# ── Judge client ────────────────────────────────────────────────────


class JudgeClient:
    """Thin wrapper around the OpenAI-compatible chat-completion endpoint
    used for the Level 4 batch judge.

    Uses the same fast-tier model + relay configured for the rest of the
    codebase via ``STS2_FAST_MODEL`` and ``STS2_GPT_BASE_URL``. Asks the model
    for a JSON object only — we parse and validate the schema in
    :func:`batch_judge`.

    Raises :class:`JudgeUnavailableError` if no API key is configured.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = (
            model
            or os.getenv("STS2_FAST_MODEL", "").strip()
            or config.LLM_FAST_MODEL
        )
        if not self.model:
            raise JudgeUnavailableError(
                "No fast model resolved for JudgeClient (STS2_FAST_MODEL empty "
                "and config.LLM_FAST_MODEL unset)"
            )
        # Route by model family so Gemini models go to the Gemini relay
        # (STS2_GEMINI_BASE_URL) with the Gemini API key, not the GPT key.
        # Previously hard-coded to GPT relay which produced the
        # "No available channel for model gemini-... under group gpt-az"
        # 503 we actually saw on run 20260418_161738.
        if base_url is None:
            default_base, default_key, provider = _relay_for_model(self.model)
        else:
            default_base, default_key, provider = base_url, "", "explicit"
        self.base_url = _normalize_openai_base_url(default_base)
        self.provider = provider
        if api_key is None:
            self.api_key = default_key
        else:
            self.api_key = api_key

    def available(self) -> bool:
        return bool(self.api_key)

    def call(self, system: str, user: str, *, max_tokens: int = 16384) -> str:
        """Single chat-completion. Returns the assistant's text content.

        ``max_tokens`` default bumped 2026-04-19 from 4096 to 16384 after we
        observed Gemini 3 Flash truncating the structured-JSON response
        mid-string on batches of 15-19 request pairs (first-run evidence:
        rounds 2/3/4 of judge_log.jsonl). Room is cheap; truncation is
        silent and catastrophic.
        """
        if not self.api_key:
            raise JudgeUnavailableError("STS2_GPT_API_KEY not configured")
        from openai import OpenAI  # local import so tests can mock

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        resp = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        choice = resp.choices[0]
        return choice.message.content or ""


class JudgeUnavailableError(RuntimeError):
    pass


# ── Judge prompt ────────────────────────────────────────────────────


_JUDGE_SYSTEM = """\
You evaluate proposed changes to an autonomous-agent skill/memory store against
existing entries and prompt context. You output ONLY a single JSON object — no
prose, no commentary, no code fences — with the exact schema shown.

For CANDIDATE requests, choose the single best decision among:
- "ADD": the candidate adds material new information; persist as a new entry.
- "UPDATE": the candidate is essentially a refined version of an existing entry
            with the same id (target_id required, must match a neighbor id).
- "MERGE": the candidate is the same concept as an existing entry; consolidate
           into target_id (required) by adding evidence rather than creating a
           new row.
- "REJECT": the candidate restates content already present in the prompt
            context (L1/L2/L3 spans) or in an existing neighbor.

For CONFLICT requests, choose:
- verdict: "contradiction" | "complementary" | "redundant".
- resolution: "keep_higher_confidence" | "merge" | "both_coexist".

Return JSON of shape:
{
  "candidates": [
    {"request_id": "<id>", "decision": "ADD|UPDATE|MERGE|REJECT",
     "target_id": "<neighbor_id or null>", "reason": "<short>"}, ...
  ],
  "conflicts": [
    {"request_id": "<id>",
     "verdict": "contradiction|complementary|redundant",
     "resolution": "keep_higher_confidence|merge|both_coexist",
     "reason": "<short>"}, ...
  ]
}
Both arrays are required (use [] when none).
"""


def _format_candidate_request(req: JudgeRequest) -> str:
    assert req.candidate is not None, "candidate request needs candidate"
    c = req.candidate
    parts: list[str] = [
        f"### CANDIDATE request_id={req.request_id}",
        f"kind={c.kind} layer={c.target_layer} name={c.name}",
        f"trigger_tags=[{', '.join(sorted(c.trigger_tags))}]",
        "content:",
        c.content.strip(),
    ]
    if req.l1_spans:
        parts.append("\nL1/L2/L3 spans with notable similarity (do NOT restate):")
        for span in req.l1_spans:
            parts.append(
                f"  - [{span.layer} {span.span_id}] {span.text.strip()[:200]}"
            )
    if req.neighbors:
        parts.append("\nExisting neighbors (top by cosine):")
        for n in req.neighbors:
            parts.append(
                f"  - id={n.entry_id} layer={n.layer} cosine={n.cosine:.2f} "
                f"trigger_jaccard={n.trigger_jaccard:.2f}\n    {n.content.strip()[:300]}"
            )
    return "\n".join(parts)


def _format_conflict_request(req: JudgeRequest) -> str:
    assert req.pair is not None, "conflict request needs pair"
    a, b = req.pair
    return "\n".join([
        f"### CONFLICT request_id={req.request_id}",
        f"Two existing entries with overlapping triggers and opposing predicates:",
        f"A id={a.id} layer={a.layer}",
        f"  trigger_tags=[{', '.join(sorted(a.trigger_tags))}]",
        f"  content: {a.content.strip()[:400]}",
        f"B id={b.id} layer={b.layer}",
        f"  trigger_tags=[{', '.join(sorted(b.trigger_tags))}]",
        f"  content: {b.content.strip()[:400]}",
    ])


def _build_user_prompt(requests: Sequence[JudgeRequest]) -> str:
    blocks: list[str] = []
    for req in requests:
        if req.kind == "candidate":
            blocks.append(_format_candidate_request(req))
        else:
            blocks.append(_format_conflict_request(req))
    return "\n\n".join(blocks)


# ── Batch judge ─────────────────────────────────────────────────────


def _strip_json_fence(text: str) -> str:
    """If the model wrapped JSON in ```json ... ``` fences, strip them."""
    text = text.strip()
    if text.startswith("```"):
        # Drop opening fence line
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        # Drop trailing ``` if present
        while lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


@dataclass(frozen=True)
class BatchJudgeResult:
    candidate_judgements: dict[str, CandidateJudgement]
    conflict_judgements: dict[str, ConflictJudgement]
    raw_response: str = ""
    error: str = ""


def batch_judge(
    client: JudgeClient,
    requests: Sequence[JudgeRequest],
) -> BatchJudgeResult:
    """Submit a single batched judge call.

    Empty input → empty result without making any API call.
    Errors (network, unparseable JSON, schema mismatch) are caught and
    returned as ``BatchJudgeResult(..., error=...)`` so callers can degrade
    gracefully (commit 2 keeps observation mode for unparseable batches).
    """
    if not requests:
        return BatchJudgeResult({}, {})

    user = _build_user_prompt(requests)
    try:
        raw = client.call(_JUDGE_SYSTEM, user)
    except JudgeUnavailableError as exc:
        return BatchJudgeResult({}, {}, error=f"unavailable: {exc}")
    except Exception as exc:
        return BatchJudgeResult({}, {}, error=f"call_failed: {exc}")

    try:
        payload = json.loads(_strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        return BatchJudgeResult({}, {}, raw_response=raw, error=f"json_decode: {exc}")
    if not isinstance(payload, dict):
        return BatchJudgeResult({}, {}, raw_response=raw, error="payload_not_dict")

    cands = payload.get("candidates") or []
    confs = payload.get("conflicts") or []

    cand_out: dict[str, CandidateJudgement] = {}
    for entry in cands:
        if not isinstance(entry, dict):
            continue
        rid = str(entry.get("request_id", ""))
        decision = str(entry.get("decision", "")).upper()
        if decision not in {"ADD", "UPDATE", "MERGE", "REJECT"}:
            continue
        target_id = entry.get("target_id")
        target_id = str(target_id) if target_id else None
        reason = str(entry.get("reason", ""))[:300]
        if rid:
            cand_out[rid] = CandidateJudgement(
                request_id=rid, decision=decision, target_id=target_id, reason=reason,
            )

    conf_out: dict[str, ConflictJudgement] = {}
    for entry in confs:
        if not isinstance(entry, dict):
            continue
        rid = str(entry.get("request_id", ""))
        verdict = str(entry.get("verdict", "")).lower()
        if verdict not in {"contradiction", "complementary", "redundant"}:
            continue
        resolution = str(entry.get("resolution", "")).lower()
        if resolution not in {"keep_higher_confidence", "merge", "both_coexist"}:
            continue
        reason = str(entry.get("reason", ""))[:300]
        if rid:
            conf_out[rid] = ConflictJudgement(
                request_id=rid, verdict=verdict, resolution=resolution, reason=reason,
            )

    return BatchJudgeResult(cand_out, conf_out, raw_response=raw)


# ── Judge queue (collected during postrun, flushed at end) ──────────


@dataclass
class _QueuedCandidate:
    candidate: Candidate
    neighbors: tuple[CandidateNeighbor, ...]
    l1_spans: tuple[StaticSpan, ...]
    request_id: str = ""


class JudgeQueue:
    """Per-postrun accumulator for candidates that hit the judge zone.

    Use ``enqueue`` whenever ``WriteGate.check`` returns
    ``action == 'defer_to_judge'``. Call ``flush`` once at end-of-postrun to
    submit a single batched judge request and return resolved decisions per
    candidate id.
    """

    def __init__(self) -> None:
        self._queue: list[_QueuedCandidate] = []
        self._counter = 0

    def __len__(self) -> int:
        return len(self._queue)

    def enqueue(
        self,
        candidate: Candidate,
        neighbors: Sequence[CandidateNeighbor],
        l1_spans: Sequence[StaticSpan] = (),
    ) -> str:
        """Add a deferred candidate to the queue. Returns the request_id."""
        self._counter += 1
        rid = f"cand_{self._counter:04d}"
        self._queue.append(
            _QueuedCandidate(
                candidate=candidate,
                neighbors=tuple(neighbors),
                l1_spans=tuple(l1_spans),
                request_id=rid,
            )
        )
        return rid

    def to_requests(self) -> list[JudgeRequest]:
        return [
            JudgeRequest(
                kind="candidate",
                request_id=q.request_id,
                candidate=q.candidate,
                neighbors=q.neighbors,
                l1_spans=q.l1_spans,
            )
            for q in self._queue
        ]

    def candidates_by_request_id(self) -> dict[str, Candidate]:
        return {q.request_id: q.candidate for q in self._queue}

    def clear(self) -> None:
        self._queue.clear()


# ── Convert judge output to GateDecision ────────────────────────────


def judgement_to_decision(j: CandidateJudgement) -> GateDecision:
    """Map a judge output back into the gate's decision vocabulary."""
    action_map = {"ADD": "accept", "UPDATE": "update", "MERGE": "merge", "REJECT": "reject"}
    return GateDecision(
        action=action_map[j.decision],
        target_id=j.target_id,
        reason=f"judge:{j.reason}",
        meta={"level": 4, "raw_decision": j.decision},
    )


# ── Logging helper for judge rounds ────────────────────────────────


def append_judge_log(
    log_path: "os.PathLike[str] | str",
    *,
    round_id: str,
    requests: Sequence[JudgeRequest],
    result: BatchJudgeResult,
) -> None:
    """Append one JSONL row summarising a judge round (for diagnostics).

    On parse failure (result.error starts with "json_decode"), we persist a
    truncated tail of the raw response so we can diagnose what the model
    actually returned. Previously this information was lost and we had no
    way to tell whether the issue was truncation, malformed JSON, or an
    unexpected response shape.
    """
    record: dict[str, Any] = {
        "ts": round(time.time(), 3),
        "round_id": round_id,
        "request_count": len(requests),
        "candidate_count": sum(1 for r in requests if r.kind == "candidate"),
        "conflict_count": sum(1 for r in requests if r.kind == "conflict"),
        "judged_candidates": len(result.candidate_judgements),
        "judged_conflicts": len(result.conflict_judgements),
        "error": result.error,
    }
    # On parse error, record the last 500 chars of the raw response so we can
    # tell at a glance whether the model truncated mid-string, emitted prose,
    # or hit a refusal.
    if result.error and result.raw_response:
        record["raw_response_tail"] = result.raw_response[-500:]
        record["raw_response_len"] = len(result.raw_response)
    try:
        from pathlib import Path

        p = Path(log_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        logger.warning("judge log write failed: %s", exc)
