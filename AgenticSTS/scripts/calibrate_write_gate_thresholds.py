"""Calibrate write-gate §4.3 thresholds from existing offline data.

Uses three data sources we already have on disk (no new runs needed):

1. ``data/skills/skills.json`` + ``src/skills/seeds/*.json`` — every skill
   currently in the library. Pairwise cosines over their content give the
   natural "different skills in production" distribution.

2. ``data.snapshots/pe-deprecated-2026-04-18/prompt_patches/prompt_patches.jsonl``
   — 33 historical PE proposed_change strings, known to be changes the
   evolution LLM thought useful. Their cosine to L1 spans is a real-world
   "candidate vs authoritative prompt" distribution.

3. Trigger-tag sets from the same skill library — Jaccard histogram to
   pick the §4.3 ``TRIGGER_JACCARD_SAME_CONTEXT`` threshold.

Output is a human-readable report (printed to stdout, plus an optional
``--output`` JSON dump). No data is modified. The embedder API is called,
but all embeddings are cached by ``EmbeddingClient`` so re-runs are free.

Usage::

    python -m scripts.calibrate_write_gate_thresholds
    python -m scripts.calibrate_write_gate_thresholds --output calibration.json
    python -m scripts.calibrate_write_gate_thresholds --max-pairs 2000  # sample cap
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import statistics
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Iterable, Sequence

# Load .env (same pattern as config.py / other scripts).
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.is_file():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ[_k.strip()] = _v.strip()

import config  # noqa: E402
from src.storage import paths  # noqa: E402
from src.memory.write_gate import (  # noqa: E402
    EmbeddingClient,
    StaticSpanIndex,
    _cosine,
    _jaccard,
)

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────


@dataclass(frozen=True)
class SkillRow:
    """One row for the skill-pair distribution."""

    skill_id: str
    source_file: str
    content: str
    trigger_tags: frozenset[str]


@dataclass
class DistSummary:
    """Percentile summary of a 1-D distribution."""

    name: str
    count: int
    minv: float = 0.0
    p10: float = 0.0
    p25: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    maxv: float = 0.0
    mean: float = 0.0
    stdev: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name, "count": self.count,
            "min": self.minv, "p10": self.p10, "p25": self.p25,
            "p50": self.p50, "p75": self.p75, "p90": self.p90,
            "p95": self.p95, "p99": self.p99, "max": self.maxv,
            "mean": self.mean, "stdev": self.stdev,
        }


# ── Data loaders ──────────────────────────────────────────────────


def _flatten_trigger(trigger: dict | None) -> frozenset[str]:
    """Turn a SkillTrigger dict into a trigger-tag frozenset (consistent with
    ``write_gate._trigger_tags_from_skill``)."""
    if not trigger:
        return frozenset()
    tags: set[str] = set()
    for attr in ("state_types", "enemy_names", "tags", "threat_levels",
                 "intent_classes", "requires_hand_capabilities", "deck_stages"):
        vals = trigger.get(attr) or ()
        for v in vals:
            if isinstance(v, str) and v:
                tags.add(f"{attr}:{v}")
    return frozenset(tags)


def load_skills(
    live_path: Path | None = None,
    seeds_dir: Path = Path("src/skills/seeds"),
) -> list[SkillRow]:
    if live_path is None:
        live_path = paths.skills_file()
    """Load discovered skills + seed skills into a single list."""
    out: list[SkillRow] = []

    if live_path.is_file():
        try:
            data = json.loads(live_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                for s in data:
                    if not isinstance(s, dict):
                        continue
                    content = str(s.get("content", "")).strip()
                    if not content:
                        continue
                    out.append(SkillRow(
                        skill_id=str(s.get("skill_id", s.get("name", ""))),
                        source_file=str(live_path),
                        content=content,
                        trigger_tags=_flatten_trigger(s.get("trigger")),
                    ))
        except json.JSONDecodeError as exc:
            logger.warning("skills.json malformed: %s", exc)

    if seeds_dir.is_dir():
        for seed_path in sorted(seeds_dir.glob("*.json")):
            try:
                data = json.loads(seed_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            if not isinstance(data, list):
                continue
            for s in data:
                if not isinstance(s, dict):
                    continue
                content = str(s.get("content", "")).strip()
                if not content:
                    continue
                out.append(SkillRow(
                    skill_id=str(s.get("skill_id", s.get("name", ""))),
                    source_file=str(seed_path),
                    content=content,
                    trigger_tags=_flatten_trigger(s.get("trigger")),
                ))

    return out


def load_pe_candidates(
    patches_path: Path = Path(
        "data.snapshots/pe-deprecated-2026-04-18/prompt_patches/prompt_patches.jsonl"
    ),
) -> list[str]:
    """Extract ``proposed_change`` text from PE-era patch records.

    Returns the latest proposed_change per patch_id (the JSONL file has
    one row per lifecycle transition, so each patch_id appears multiple
    times).
    """
    if not patches_path.is_file():
        return []
    latest_per_id: dict[str, str] = {}
    with patches_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = rec.get("patch_id", "")
            change = rec.get("proposed_change", "") or rec.get("current_issue", "")
            if pid and change:
                latest_per_id[pid] = str(change).strip()
    return [v for v in latest_per_id.values() if v]


# ── Statistics ────────────────────────────────────────────────────


def summarise(name: str, values: Sequence[float]) -> DistSummary:
    if not values:
        return DistSummary(name=name, count=0)
    sv = sorted(values)
    def pct(p: float) -> float:
        # Linear-interpolation percentile.
        if len(sv) == 1:
            return sv[0]
        k = (len(sv) - 1) * p
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sv[int(k)]
        return sv[f] + (sv[c] - sv[f]) * (k - f)
    try:
        sd = statistics.stdev(values) if len(values) > 1 else 0.0
    except statistics.StatisticsError:
        sd = 0.0
    return DistSummary(
        name=name,
        count=len(values),
        minv=sv[0], p10=pct(0.10), p25=pct(0.25),
        p50=pct(0.50), p75=pct(0.75), p90=pct(0.90),
        p95=pct(0.95), p99=pct(0.99), maxv=sv[-1],
        mean=sum(values) / len(values),
        stdev=sd,
    )


def print_summary(s: DistSummary, *, indent: str = "  ") -> None:
    print(f"{s.name}: n={s.count}")
    if s.count == 0:
        return
    for pname, pval in [
        ("min", s.minv), ("p10", s.p10), ("p25", s.p25),
        ("p50", s.p50), ("p75", s.p75), ("p90", s.p90),
        ("p95", s.p95), ("p99", s.p99), ("max", s.maxv),
        ("mean", s.mean), ("stdev", s.stdev),
    ]:
        print(f"{indent}{pname:<6} {pval:.3f}")


def histogram_lines(values: Sequence[float], *, bins: int = 10,
                    width: int = 40) -> list[str]:
    """ASCII histogram for the terminal report."""
    if not values:
        return ["(empty)"]
    lo, hi = min(values), max(values)
    if hi == lo:
        return [f"{lo:.3f}  all values identical (n={len(values)})"]
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(int((v - lo) / step), bins - 1)
        counts[idx] += 1
    cmax = max(counts) or 1
    lines: list[str] = []
    for i, c in enumerate(counts):
        edge_lo = lo + step * i
        edge_hi = lo + step * (i + 1)
        bar = "#" * round(width * c / cmax)
        lines.append(f"  [{edge_lo:.2f}, {edge_hi:.2f})  {bar} {c}")
    return lines


# ── Threshold recommendations ─────────────────────────────────────


@dataclass
class ThresholdRecommendation:
    skill_auto_reject: tuple[float, float]  # range
    l1_overlap_reject: tuple[float, float]
    trigger_jaccard: tuple[float, float]
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_auto_reject": list(self.skill_auto_reject),
            "l1_overlap_reject": list(self.l1_overlap_reject),
            "trigger_jaccard": list(self.trigger_jaccard),
            "notes": self.notes,
        }


def recommend(
    skill_pair_summary: DistSummary,
    cand_l1_summary: DistSummary,
    trigger_summary: DistSummary,
) -> ThresholdRecommendation:
    """Produce a candidate threshold range + sanity notes.

    Heuristics (explicit so you can argue with them):
    - L4/L5 auto-reject should sit around the p95-p99 of pairwise skill
      cosines. Below that we'd reject legitimately-distinct skills that
      just happen to overlap lexically. Above p99 we'd miss near-dups.
    - L1-overlap reject should sit around the p75-p90 of candidate-vs-L1
      cosines. Candidates in the upper tail are the ones most likely
      restating L1 content.
    - Trigger Jaccard should sit around the p75 of existing pairwise
      Jaccards — that's the boundary between "this trigger is a variant"
      and "this trigger is a new context".
    """
    notes: list[str] = []

    skill_recommendation = (
        round(skill_pair_summary.p95, 2),
        round(skill_pair_summary.p99, 2),
    )
    if skill_pair_summary.count < 20:
        notes.append(
            "Skill-pair sample size is small (n<20). Treat skill_auto_reject as "
            "very rough; resample after more skills accumulate."
        )

    l1_recommendation = (
        round(cand_l1_summary.p75, 2),
        round(cand_l1_summary.p90, 2),
    )
    if cand_l1_summary.count < 10:
        notes.append(
            "Candidate-vs-L1 sample size is small. Consider also embedding "
            "discovered skills vs L1 to enlarge the sample."
        )

    trigger_recommendation = (
        round(trigger_summary.p75, 2),
        round(trigger_summary.p90, 2),
    )

    return ThresholdRecommendation(
        skill_auto_reject=skill_recommendation,
        l1_overlap_reject=l1_recommendation,
        trigger_jaccard=trigger_recommendation,
        notes=notes,
    )


# ── Main pipeline ────────────────────────────────────────────────


def _pair_cosines(skills: Sequence[SkillRow], embedder: EmbeddingClient,
                  *, max_pairs: int | None = None, seed: int = 0) -> list[float]:
    """Compute pairwise cosines of skill contents. Caps to ``max_pairs``
    uniformly-sampled pairs to keep embeddings bounded."""
    if len(skills) < 2:
        return []
    texts = [s.content for s in skills]
    vecs = embedder.embed(texts)
    all_pairs = list(combinations(range(len(skills)), 2))
    if max_pairs is not None and len(all_pairs) > max_pairs:
        rng = random.Random(seed)
        all_pairs = rng.sample(all_pairs, max_pairs)
    return [_cosine(vecs[i], vecs[j]) for i, j in all_pairs]


def _trigger_jaccards(skills: Sequence[SkillRow]) -> list[float]:
    if len(skills) < 2:
        return []
    out: list[float] = []
    for i, j in combinations(range(len(skills)), 2):
        out.append(_jaccard(skills[i].trigger_tags, skills[j].trigger_tags))
    return out


def _candidate_vs_l1(candidates: Sequence[str], static: StaticSpanIndex,
                     embedder: EmbeddingClient) -> list[tuple[float, str]]:
    """Return (max_cosine, offending_span_id) per candidate, sorted by
    max_cosine descending."""
    if not candidates:
        return []
    vecs = embedder.embed(list(candidates))
    out: list[tuple[float, str]] = []
    for vec in vecs:
        cos, span = static.max_similarity(vec)
        out.append((cos, span.span_id if span else ""))
    out.sort(reverse=True)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-path", type=Path,
                        default=paths.skills_file())
    parser.add_argument("--seeds-dir", type=Path,
                        default=Path("src/skills/seeds"))
    parser.add_argument("--pe-patches",  type=Path,
                        default=Path(
                            "data.snapshots/pe-deprecated-2026-04-18/"
                            "prompt_patches/prompt_patches.jsonl"
                        ))
    parser.add_argument("--output", type=Path, default=None,
                        help="Optional path to dump the raw numbers as JSON.")
    parser.add_argument("--max-pairs", type=int, default=None,
                        help="Cap for skill-pair sampling (default: all pairs).")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    embedder = EmbeddingClient()
    if not embedder.available():
        print("STS2_GPT_API_KEY not configured — cannot embed; aborting.", file=sys.stderr)
        return 2

    static = StaticSpanIndex(embedder)
    static.rebuild_if_stale()
    if static.span_count == 0:
        print("StaticSpanIndex empty — L1 embedding probably failed.", file=sys.stderr)
        return 3

    skills = load_skills(args.skills_path, args.seeds_dir)
    pe_candidates = load_pe_candidates(args.pe_patches)

    print(f"Loaded {len(skills)} skills and {len(pe_candidates)} PE candidates.")
    print(f"L1 span index: {static.span_count} spans.")
    print()

    # (a) Skill-pair cosines
    pair_cosines = _pair_cosines(skills, embedder, max_pairs=args.max_pairs, seed=args.seed)
    sk_summary = summarise("skill_pair_cosines", pair_cosines)

    # (b) Candidate-vs-L1
    cand_vs_l1_pairs = _candidate_vs_l1(pe_candidates, static, embedder)
    cand_l1_values = [c for c, _ in cand_vs_l1_pairs]
    cand_summary = summarise("candidate_vs_l1_cosine", cand_l1_values)

    # (c) Trigger Jaccards
    tj = _trigger_jaccards(skills)
    tj_summary = summarise("trigger_jaccard", tj)

    print("## Skill-pair cosine distribution")
    print_summary(sk_summary)
    for line in histogram_lines(pair_cosines):
        print(line)
    print()

    print("## Candidate (PE patch) cosine vs L1 spans")
    print_summary(cand_summary)
    for line in histogram_lines(cand_l1_values):
        print(line)
    print()

    if cand_vs_l1_pairs:
        print("Top-5 PE candidates by L1 cosine:")
        for cos, span_id in cand_vs_l1_pairs[:5]:
            print(f"  {cos:.3f}  <- {span_id}")
        print()

    print("## Trigger-tag Jaccard distribution (pairwise over skills)")
    print_summary(tj_summary)
    for line in histogram_lines(tj):
        print(line)
    print()

    rec = recommend(sk_summary, cand_summary, tj_summary)
    print("## Threshold recommendation ranges")
    print(f"  L4/L5 auto-reject cosine: {rec.skill_auto_reject[0]:.2f}–{rec.skill_auto_reject[1]:.2f}"
          f"   (spec §13.2 starting value: 0.85)")
    print(f"  L1 overlap reject cosine: {rec.l1_overlap_reject[0]:.2f}–{rec.l1_overlap_reject[1]:.2f}"
          f"   (spec §13.2 starting value: 0.70)")
    print(f"  Trigger Jaccard same-context: {rec.trigger_jaccard[0]:.2f}–{rec.trigger_jaccard[1]:.2f}"
          f"   (spec §13.2 starting value: 0.60)")
    for note in rec.notes:
        print(f"  note: {note}")

    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "skill_pair_summary": sk_summary.to_dict(),
            "candidate_vs_l1_summary": cand_summary.to_dict(),
            "trigger_jaccard_summary": tj_summary.to_dict(),
            "recommendation": rec.to_dict(),
            "skill_count": len(skills),
            "pe_candidate_count": len(pe_candidates),
            "l1_span_count": static.span_count,
        }
        args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nRaw numbers written to {args.output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
