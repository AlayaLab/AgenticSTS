"""Demote seed skills / consolidated guides that overlap L1/L2/L3 (spec §9).

One-shot pass: embed every seed skill in ``src/skills/seeds/*.json`` plus every
consolidated guide on disk, and run them through the L1/L2/L3 static span
index. Anything with ``cosine >= L1_L2_L3_REJECT_COSINE`` gets:

    confidence = 0.30      (so newer skills can outcompete it on the §6.1 Pareto frontier)
    legacy = true          (metadata flag for ablation comparisons)

The seed JSON files are rewritten in place. A diagnostic report is written
to ``data/evolution/legacy_demotion_<YYYY-MM-DD>.log``. Originals are
preserved automatically by git history; you can also pass ``--dry-run`` to
inspect proposed changes without writing.

Usage::

    python -m scripts.demote_overlapping_seeds              # apply
    python -m scripts.demote_overlapping_seeds --dry-run    # preview only
    python -m scripts.demote_overlapping_seeds --threshold 0.65  # tune

Prerequisites: ``STS2_GPT_API_KEY`` configured (the embedder must be
available — see write_gate.EmbeddingClient). If unavailable, the script
exits without modifying any file.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

# Load .env (same pattern as config.py + scripts/probe_embedding.py).
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.is_file():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ[_k.strip()] = _v.strip()

import config  # noqa: E402
from src.memory.write_gate import (  # noqa: E402
    L1_L2_L3_REJECT_COSINE,
    EmbeddingClient,
    StaticSpanIndex,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DemotionRecord:
    """One row written to the legacy_demotion log."""

    file: str
    skill_id: str
    name: str
    cosine: float
    span_id: str
    span_excerpt: str
    old_confidence: float
    new_confidence: float


def _iter_seed_skills(seeds_dir: Path):
    for path in sorted(seeds_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("skipping malformed seed file %s: %s", path, exc)
            continue
        if not isinstance(data, list):
            logger.warning("seed file %s: top-level not a list, skipping", path)
            continue
        yield path, data


def _demote_one(skill: dict, *, demoted_confidence: float) -> dict:
    new = dict(skill)
    new["confidence"] = demoted_confidence
    new["legacy"] = True
    return new


def _scan_seeds(
    seeds_dir: Path,
    *,
    static_index: StaticSpanIndex,
    embedder: EmbeddingClient,
    threshold: float,
    demoted_confidence: float,
) -> tuple[list[DemotionRecord], dict[Path, list[dict]]]:
    """Return (demotion records, updated-skill-list per modified file)."""
    records: list[DemotionRecord] = []
    updates_per_file: dict[Path, list[dict]] = {}

    for path, skills in _iter_seed_skills(seeds_dir):
        if not isinstance(skills, list) or not skills:
            continue
        # Only embed skills not already demoted.
        to_embed: list[tuple[int, str]] = [
            (i, s.get("content", "")) for i, s in enumerate(skills)
            if isinstance(s, dict)
            and s.get("content")
            and not s.get("legacy", False)
        ]
        if not to_embed:
            continue
        try:
            vecs = embedder.embed([content for _, content in to_embed])
        except Exception as exc:
            logger.warning("embed failed for %s: %s — skipping", path, exc)
            continue

        modified = list(skills)
        modified_any = False
        for (i, _), vec in zip(to_embed, vecs, strict=True):
            cos, span = static_index.max_similarity(vec)
            if cos < threshold or span is None:
                continue
            old_conf = float(skills[i].get("confidence", 0.5))
            modified[i] = _demote_one(skills[i], demoted_confidence=demoted_confidence)
            modified_any = True
            records.append(
                DemotionRecord(
                    file=str(path.as_posix()),
                    skill_id=str(skills[i].get("skill_id", "")),
                    name=str(skills[i].get("name", "")),
                    cosine=cos,
                    span_id=span.span_id,
                    span_excerpt=span.text.strip()[:120],
                    old_confidence=old_conf,
                    new_confidence=demoted_confidence,
                )
            )
        if modified_any:
            updates_per_file[path] = modified

    return records, updates_per_file


def _write_log(report_path: Path, records: list[DemotionRecord], *, dry_run: bool) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", encoding="utf-8") as fh:
        fh.write(f"# Legacy demotion run — {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        fh.write(f"# dry_run={dry_run}, count={len(records)}\n")
        fh.write("# columns: file | skill_id | name | cosine | span_id | excerpt\n")
        for r in records:
            fh.write(
                f"{r.file}\t{r.skill_id}\t{r.name}\t{r.cosine:.3f}\t"
                f"{r.span_id}\t{r.span_excerpt}\n"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Scan and report; do not modify any seed file.")
    parser.add_argument("--threshold", type=float, default=L1_L2_L3_REJECT_COSINE,
                        help=f"Cosine threshold for demotion (default {L1_L2_L3_REJECT_COSINE}).")
    parser.add_argument("--demoted-confidence", type=float, default=0.30,
                        help="Confidence to assign demoted seeds (default 0.30).")
    parser.add_argument("--seeds-dir", type=Path, default=Path("src/skills/seeds"),
                        help="Where seed JSON files live.")
    parser.add_argument("--report-path", type=Path, default=None,
                        help="Override legacy demotion report file path.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    embedder = EmbeddingClient()
    if not embedder.available():
        print("STS2_GPT_API_KEY not configured — cannot embed; aborting.", file=sys.stderr)
        return 2

    static_index = StaticSpanIndex(embedder)
    static_index.rebuild_if_stale()
    if static_index.span_count == 0:
        print("Static span index is empty — embedding probably failed.", file=sys.stderr)
        return 3

    if not args.seeds_dir.is_dir():
        print(f"seeds dir not found: {args.seeds_dir}", file=sys.stderr)
        return 4

    print(
        f"Scanning {args.seeds_dir} against {static_index.span_count} L1/L2/L3 spans"
        f" (threshold={args.threshold:.2f}, demoted_confidence={args.demoted_confidence:.2f})"
    )

    records, updates_per_file = _scan_seeds(
        args.seeds_dir,
        static_index=static_index,
        embedder=embedder,
        threshold=args.threshold,
        demoted_confidence=args.demoted_confidence,
    )

    print(f"Demotion candidates: {len(records)}")
    for r in records:
        print(
            f"  - {r.skill_id} (cos={r.cosine:.2f}) -> matches {r.span_id}: "
            f"{r.span_excerpt[:80]}"
        )

    report_path = args.report_path or (
        Path(config.EVOLUTION_DIR) / f"legacy_demotion_{time.strftime('%Y-%m-%d')}.log"
    )
    _write_log(report_path, records, dry_run=args.dry_run)
    print(f"Report -> {report_path}")

    if args.dry_run:
        print("--dry-run: skipping file writes.")
        return 0

    for path, updated_skills in updates_per_file.items():
        path.write_text(
            json.dumps(updated_skills, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Rewrote {path}")
    print(f"Modified {len(updates_per_file)} seed files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
