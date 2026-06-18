"""Lifecycle management for L4 memory + L5 skills (commit 2/4).

Implements §6 from the write-gate spec:
- §6.1 Pareto frontier per cohort: each (character, decision_type, deck_stage)
       cohort holds at most ``k = 3`` entries, ranked by lifecycle_score; new
       admissions must beat the weakest slot.
- §6.2 EvolveR-style confidence prune: entries with ``s < 0.30 AND c_use >= 10``
       are demoted to ``archive`` (kept on disk for analysis, removed from
       retrieval).
- §6.3 Proposal-history injection: tail of the write-gate observation log
       (last ``N = 20`` proposals + dispositions) made available for the
       discovery prompt.

Stateless helper functions — they operate on duck-typed inputs (anything with
``.id``, ``.confidence``, ``.usage_count``, ``.success_count``, ``.cohort_key``)
so we don't couple the lifecycle layer to specific model classes. Callers
adapt their stores via ``CohortEntry`` adaptors.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)


# ── Constants from spec §13.2 ──────────────────────────────────────

PARETO_SLOT_K = 3                # max entries per cohort
PRUNE_SCORE_THRESHOLD = 0.30     # EvolveR
PRUNE_MIN_USE_COUNT = 10         # don't prune until enough usage signal
PROPOSAL_HISTORY_WINDOW = 20     # last N proposals fed back into discovery


# ── Adapter type ───────────────────────────────────────────────────


@dataclass(frozen=True)
class CohortEntry:
    """Lifecycle adapter for a skill / guide / rule.

    ``cohort_key`` should be a tuple-able discriminator (e.g.
    ``(character, decision_type, deck_stage)``). Identity is by ``id``.
    """

    id: str
    cohort_key: tuple[str, ...]
    confidence: float
    usage_count: int = 0
    success_count: int = 0


def lifecycle_score(entry: CohortEntry) -> float:
    """EvolveR's success-rate-with-prior: ``(c_succ + 1) / (c_use + 2)``.

    Mass at ``c_use=0`` is 0.5 — neutral starting belief.
    """
    return (entry.success_count + 1) / (entry.usage_count + 2)


# ── Pareto frontier (§6.1) ─────────────────────────────────────────


def group_by_cohort(
    entries: Iterable[CohortEntry],
) -> dict[tuple[str, ...], list[CohortEntry]]:
    by: dict[tuple[str, ...], list[CohortEntry]] = {}
    for e in entries:
        by.setdefault(tuple(e.cohort_key), []).append(e)
    return by


def pareto_frontier(
    entries: Iterable[CohortEntry], *, k: int = PARETO_SLOT_K,
) -> dict[tuple[str, ...], list[CohortEntry]]:
    """Return per-cohort top-``k`` by lifecycle_score (descending)."""
    out: dict[tuple[str, ...], list[CohortEntry]] = {}
    for ck, members in group_by_cohort(entries).items():
        ranked = sorted(members, key=lifecycle_score, reverse=True)
        out[ck] = ranked[:k]
    return out


@dataclass(frozen=True)
class PareReplaceDecision:
    """Decision returned by :func:`evaluate_pareto_admission`."""

    action: str  # "accept" | "displace" | "reject"
    displaced_id: str | None = None
    reason: str = ""


def evaluate_pareto_admission(
    candidate: CohortEntry,
    cohort_members: Sequence[CohortEntry],
    *,
    k: int = PARETO_SLOT_K,
) -> PareReplaceDecision:
    """Decide whether ``candidate`` may join its cohort.

    Rules:
    - cohort has fewer than ``k`` members → accept.
    - cohort full → candidate must beat the weakest member's lifecycle_score.
      Tie goes to the existing member (stability).
    """
    if len(cohort_members) < k:
        return PareReplaceDecision(action="accept", reason="cohort_has_room")
    weakest = min(cohort_members, key=lifecycle_score)
    cand_score = lifecycle_score(candidate)
    if cand_score > lifecycle_score(weakest):
        return PareReplaceDecision(
            action="displace",
            displaced_id=weakest.id,
            reason=(
                f"cand_score={cand_score:.2f}>weakest={lifecycle_score(weakest):.2f}"
            ),
        )
    return PareReplaceDecision(
        action="reject",
        reason="weakest_holds_slot",
    )


# ── Confidence prune (§6.2) ────────────────────────────────────────


@dataclass(frozen=True)
class PruneDecision:
    id: str
    action: str  # "demote" | "keep"
    score: float
    usage_count: int
    reason: str = ""


def evaluate_prune(
    entries: Iterable[CohortEntry],
    *,
    score_threshold: float = PRUNE_SCORE_THRESHOLD,
    min_use_count: int = PRUNE_MIN_USE_COUNT,
) -> list[PruneDecision]:
    """For each entry, decide demote vs keep.

    Demote requires both insufficient score AND enough usage data — entries
    with a few unlucky early uses don't get killed prematurely.
    """
    out: list[PruneDecision] = []
    for e in entries:
        s = lifecycle_score(e)
        if e.usage_count >= min_use_count and s < score_threshold:
            out.append(
                PruneDecision(
                    id=e.id,
                    action="demote",
                    score=s,
                    usage_count=e.usage_count,
                    reason=(
                        f"score={s:.2f}<{score_threshold:.2f}"
                        f" with usage={e.usage_count}>={min_use_count}"
                    ),
                )
            )
        else:
            out.append(
                PruneDecision(id=e.id, action="keep", score=s, usage_count=e.usage_count)
            )
    return out


# ── Proposal history (§6.3) ────────────────────────────────────────


@dataclass(frozen=True)
class ProposalHistoryEntry:
    """One row from the write-gate observation log."""

    name: str
    kind: str
    target_layer: str
    action: str
    reason: str


def read_recent_proposals(
    log_path: Path,
    *,
    window: int = PROPOSAL_HISTORY_WINDOW,
) -> list[ProposalHistoryEntry]:
    """Read the last ``window`` rows of the write-gate observation log.

    Returns oldest-first within the window so the discovery LLM sees
    chronological "tried X → got Y" pairs. Missing log → empty list.
    Malformed rows are skipped silently.
    """
    if not log_path.is_file():
        return []
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        logger.warning("proposal history read failed: %s", exc)
        return []
    out: list[ProposalHistoryEntry] = []
    for raw in lines[-window:]:
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        out.append(
            ProposalHistoryEntry(
                name=str(rec.get("name", "")),
                kind=str(rec.get("kind", "")),
                target_layer=str(rec.get("target_layer", "")),
                action=str(rec.get("action", "")),
                reason=str(rec.get("reason", ""))[:120],
            )
        )
    return out


def format_proposal_history(entries: Sequence[ProposalHistoryEntry]) -> str:
    """Render a compact table for injection into the discovery prompt.

    Format chosen for low token cost: one line per entry,
    ``[action] kind/name → reason``. Empty input returns "" so callers can
    safely concatenate.
    """
    if not entries:
        return ""
    lines = [
        "## Recent Write-Gate Decisions (avoid re-proposing rejected/merged ideas)",
    ]
    for e in entries:
        line = f"- [{e.action}] {e.kind}/{e.name} → {e.reason}"
        lines.append(line)
    return "\n".join(lines)
