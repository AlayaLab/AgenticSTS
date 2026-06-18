"""Audit the skill library: find structural conflicts + auto-duplicates.

Two modes of operation:

1. Default (read-only): scan ``data/skills/skills.json`` + seeds, compute
   pairwise cosines on content, run the structural-conflict detector, and
   optionally submit conflicts to the batch LLM judge for verdicts. Print a
   structured report; don't modify anything.

2. --prune (write): also rewrite ``data/skills/skills.json`` to remove
   discovered skills that are auto-duplicates of each other or of a seed.
   Seeds are never modified by this script.

Usage::

    python -m scripts.audit_skill_library                 # read-only report
    python -m scripts.audit_skill_library --judge         # + LLM judge on conflicts
    python -m scripts.audit_skill_library --prune         # remove discovered dupes
    python -m scripts.audit_skill_library --prune --apply # actually write the file
    python -m scripts.audit_skill_library --dup-cosine 0.80  # tune threshold

The prune rule (kept deliberately conservative):

- A *discovered* skill is considered a duplicate of another entry when
  their content cosine ≥ ``--dup-cosine`` (default 0.85 — same as the
  §4.3 L4/L5 auto-reject).
- If the duplicate pair is (discovered, seed) → remove the discovered one.
  Seeds are the curated baseline; new discoveries should add value beyond
  them, not re-derive them.
- If the duplicate pair is (discovered, discovered) → keep the one with
  higher ``confidence``; tie-break by higher ``usage_count``; final tie
  goes to the skill_id that sorts first (stable).
- Seeds are never removed by this script. If you want to demote a seed
  that turned out to overlap L1, use ``scripts.demote_overlapping_seeds``.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Iterable, Sequence

# Load .env (same pattern as our other scripts).
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
    ExistingEntry,
    _cosine,
)
from src.memory.write_gate_judge import (  # noqa: E402
    JudgeClient,
    JudgeRequest,
    batch_judge,
    find_structural_conflicts,
)

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────


@dataclass(frozen=True)
class SkillRecord:
    """Subset of a skill dict that we need for the audit."""

    skill_id: str
    name: str
    content: str
    trigger_tags: frozenset[str]
    confidence: float
    usage_count: int
    source_file: Path
    is_seed: bool
    raw: dict  # full original dict for rewriting

    @property
    def short_id(self) -> str:
        """Compact identifier for logs. Seed skills share the ``seed_*``
        prefix so we show enough characters to distinguish them, not just
        the first 10."""
        sid = self.skill_id or self.name
        return sid[:32]


@dataclass(frozen=True)
class DupPair:
    a: SkillRecord
    b: SkillRecord
    cosine: float


# ── Data loaders ──────────────────────────────────────────────────


def _flatten_trigger(trigger: dict | None) -> frozenset[str]:
    if not trigger:
        return frozenset()
    tags: set[str] = set()
    for attr in ("state_types", "enemy_names", "tags", "threat_levels",
                 "intent_classes", "requires_hand_capabilities", "deck_stages"):
        for v in trigger.get(attr) or []:
            if isinstance(v, str) and v:
                tags.add(f"{attr}:{v}")
    return frozenset(tags)


def load_skills(
    live_path: Path | None = None,
    seeds_dir: Path = Path("src/skills/seeds"),
) -> tuple[list[SkillRecord], list[dict]]:
    if live_path is None:
        live_path = paths.skills_file()
    """Load live + seed skills.

    Returns ``(all_records, live_raw_list)``. ``live_raw_list`` is the exact
    object loaded from ``skills.json`` so we can rewrite it in place without
    losing fields we don't model.
    """
    out: list[SkillRecord] = []
    live_raw: list[dict] = []

    if live_path.is_file():
        try:
            data = json.loads(live_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                live_raw = data
                for s in data:
                    if not isinstance(s, dict):
                        continue
                    content = str(s.get("content", "")).strip()
                    if not content:
                        continue
                    out.append(SkillRecord(
                        skill_id=str(s.get("skill_id", s.get("name", ""))),
                        name=str(s.get("name", "")),
                        content=content,
                        trigger_tags=_flatten_trigger(s.get("trigger")),
                        confidence=float(s.get("confidence", 0.5)),
                        usage_count=int(s.get("usage_count", 0)),
                        source_file=live_path,
                        is_seed=False,
                        raw=s,
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
                out.append(SkillRecord(
                    skill_id=str(s.get("skill_id", s.get("name", ""))),
                    name=str(s.get("name", "")),
                    content=content,
                    trigger_tags=_flatten_trigger(s.get("trigger")),
                    confidence=float(s.get("confidence", 0.5)),
                    usage_count=int(s.get("usage_count", 0)),
                    source_file=seed_path,
                    is_seed=True,
                    raw=s,
                ))
    return out, live_raw


# ── Analysis ──────────────────────────────────────────────────────


def _is_same_logical_skill(a: SkillRecord, b: SkillRecord) -> bool:
    """Two records represent the SAME logical skill if they share a skill_id.

    This happens intentionally for seed skills: the canonical content lives
    in ``src/skills/seeds/*.json`` while the runtime-tracked stats
    (usage_count, success_count, confidence) live in
    ``data/skills/skills.json`` under the same ``skill_id``.
    ``SkillLibrary.merge_seeds()`` explicitly merges those at load time,
    preserving stats. Treating them as duplicates and pruning one would
    reset accumulated stats to zero — we must skip them here.
    """
    if not a.skill_id or not b.skill_id:
        return False
    return a.skill_id == b.skill_id


def _is_seed_pair(a: SkillRecord, b: SkillRecord) -> bool:
    """True when both records are seed-source (canonical curated knowledge).

    Seed-vs-seed pairs across different seed files are intentional — the
    library curator wrote them that way — so we never prune them here.
    If a seed really does overlap, it should be demoted via
    ``scripts.demote_overlapping_seeds``, not deleted.
    """
    return _is_seed_record(a) and _is_seed_record(b)


def _is_seed_record(r: SkillRecord) -> bool:
    """Seed by either provenance (seed file) or recorded source field."""
    return r.is_seed or str(r.raw.get("source", "")).lower() == "seed"


def find_duplicates(
    skills: Sequence[SkillRecord],
    embedder: EmbeddingClient,
    *,
    dup_cosine: float = 0.85,
) -> list[DupPair]:
    """Return all pairs with content cosine ≥ ``dup_cosine``.

    Skips pairs that:
    - Share a skill_id (same logical skill — seed content vs stat holder).
    - Are both seed-source (curated overlap, handled by demotion tooling).
    """
    if len(skills) < 2:
        return []
    vecs = embedder.embed([s.content for s in skills])
    out: list[DupPair] = []
    for i, j in combinations(range(len(skills)), 2):
        a, b = skills[i], skills[j]
        if _is_same_logical_skill(a, b):
            continue
        if _is_seed_pair(a, b):
            continue
        c = _cosine(vecs[i], vecs[j])
        if c >= dup_cosine:
            out.append(DupPair(a=a, b=b, cosine=c))
    out.sort(key=lambda p: p.cosine, reverse=True)
    return out


def _to_existing_entry(s: SkillRecord) -> ExistingEntry:
    return ExistingEntry(
        id=s.skill_id or s.name, content=s.content,
        trigger_tags=s.trigger_tags, layer="L5",
    )


def _pick_loser(a: SkillRecord, b: SkillRecord) -> SkillRecord | None:
    """Pick the skill to remove from a duplicate pair.

    Safety rules:
    - Never prune a seed-source record (checked via ``_is_seed_record``,
      which looks at both file provenance AND the ``source`` field). This
      protects the skills.json stat-holders whose ``skill_id`` starts with
      ``seed_`` — deleting them would reset accumulated usage_count /
      success_count stats that seeds rely on.
    - If exactly one side is seed-source, drop the other (discovered).
    - If neither is seed-source (both discovered), pick the one with lower
      confidence; tie-break by lower usage_count; final tie by id order.
    """
    a_seed = _is_seed_record(a)
    b_seed = _is_seed_record(b)
    if a_seed and b_seed:
        return None  # never prune two seeds — handled by demotion tooling
    if a_seed and not b_seed:
        return b
    if b_seed and not a_seed:
        return a
    # Both discovered: keep higher confidence, then higher usage, then id order.
    if a.confidence != b.confidence:
        return a if a.confidence < b.confidence else b
    if a.usage_count != b.usage_count:
        return a if a.usage_count < b.usage_count else b
    return a if (a.skill_id or "") > (b.skill_id or "") else b


# ── Report rendering ─────────────────────────────────────────────


def _print_dup_pair(pair: DupPair, loser: SkillRecord | None) -> None:
    a, b = pair.a, pair.b
    tag = "DROP" if loser is not None else "KEEP-BOTH"
    print(f"  cos={pair.cosine:.3f}  [{tag}]")
    print(f"    A {a.short_id:<34} conf={a.confidence:.2f} use={a.usage_count:>5} "
          f"{'[SEED]' if a.is_seed else '[DISC]'} {a.name[:48]}")
    print(f"         {a.content[:140]}")
    print(f"    B {b.short_id:<34} conf={b.confidence:.2f} use={b.usage_count:>5} "
          f"{'[SEED]' if b.is_seed else '[DISC]'} {b.name[:48]}")
    print(f"         {b.content[:140]}")
    if loser is not None:
        tag_src = "SEED" if loser.is_seed else "DISC"
        print(f"    → would remove {loser.short_id} [{tag_src}] {loser.source_file.name} "
              f"({loser.name[:48]})")
    print()


def _print_conflict(i: int, pair, verdict: str, resolution: str, reason: str) -> None:
    print(f"{i}. trig_j={pair.trigger_jaccard:.2f} "
          f"content_cos={pair.content_cosine:.2f} "
          f"verdict={verdict or 'UNJUDGED':<14} resolution={resolution or '-':<22}")
    print(f"    A [{pair.a.id[:12]}]: {pair.a.content[:180]}")
    print(f"    B [{pair.b.id[:12]}]: {pair.b.content[:180]}")
    if reason:
        print(f"    reason: {reason[:200]}")
    print()


# ── Prune ─────────────────────────────────────────────────────────


def _prune_live_json(
    live_raw: list[dict],
    remove_ids: set[str],
) -> list[dict]:
    """Return a new list with any record whose skill_id/name is in
    ``remove_ids`` omitted."""
    kept: list[dict] = []
    for s in live_raw:
        if not isinstance(s, dict):
            kept.append(s)
            continue
        sid = str(s.get("skill_id", s.get("name", "")))
        if sid in remove_ids:
            continue
        kept.append(s)
    return kept


# ── Main ──────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-path", type=Path,
                        default=paths.skills_file())
    parser.add_argument("--seeds-dir", type=Path,
                        default=Path("src/skills/seeds"))
    parser.add_argument("--dup-cosine", type=float, default=0.85,
                        help="Content cosine threshold to flag a duplicate pair.")
    parser.add_argument("--judge", action="store_true",
                        help="Submit detected conflicts to the batch LLM judge.")
    parser.add_argument("--prune", action="store_true",
                        help="Propose removals for discovered-skill duplicates.")
    parser.add_argument("--apply", action="store_true",
                        help="Actually rewrite skills.json (requires --prune).")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    embedder = EmbeddingClient()
    if not embedder.available():
        print("STS2_GPT_API_KEY not configured — cannot embed; aborting.", file=sys.stderr)
        return 2

    skills, live_raw = load_skills(args.skills_path, args.seeds_dir)
    live = [s for s in skills if not s.is_seed]
    seeds = [s for s in skills if s.is_seed]
    print(f"Loaded {len(skills)} skills ({len(live)} live, {len(seeds)} seeds)")
    print()

    # ── Duplicates ──────────────────────────────────────
    dups = find_duplicates(skills, embedder, dup_cosine=args.dup_cosine)
    print(f"## Auto-duplicate pairs (cosine ≥ {args.dup_cosine:.2f})  n={len(dups)}")
    print()

    remove_ids: set[str] = set()
    removal_log: list[tuple[SkillRecord, DupPair]] = []
    for pair in dups:
        loser = _pick_loser(pair.a, pair.b)
        _print_dup_pair(pair, loser)
        if loser is not None:
            # Don't double-remove the same id if it appears in multiple pairs.
            loser_key = loser.skill_id or loser.name
            if loser_key not in remove_ids:
                remove_ids.add(loser_key)
                removal_log.append((loser, pair))

    # ── Conflicts ──────────────────────────────────────
    entries = [_to_existing_entry(s) for s in skills]
    conflicts = find_structural_conflicts(entries, embedder=embedder)
    print(f"## Structural conflicts  n={len(conflicts)}")
    print()

    verdicts_by_rid: dict = {}
    if args.judge and conflicts:
        judge = JudgeClient()
        if not judge.available():
            print("WARN: judge unavailable; skipping LLM verdicts.")
        else:
            reqs = [
                JudgeRequest(
                    kind="conflict",
                    request_id=f"conf_{i:04d}",
                    pair=(p.a, p.b),
                )
                for i, p in enumerate(conflicts, start=1)
            ]
            print(f"Submitting {len(reqs)} conflicts to the batch judge "
                  f"({judge.model} via {judge.provider}) — this may take a minute...")
            result = batch_judge(judge, reqs)
            if result.error:
                print(f"judge error: {result.error}")
            verdicts_by_rid = result.conflict_judgements

    for i, p in enumerate(conflicts, start=1):
        rid = f"conf_{i:04d}"
        v = verdicts_by_rid.get(rid)
        verdict = v.verdict if v else ""
        resolution = v.resolution if v else ""
        reason = v.reason if v else ""
        _print_conflict(i, p, verdict, resolution, reason)

    # ── Summary ────────────────────────────────────────
    print("## Summary")
    print(f"  duplicate pairs:     {len(dups)}  (would remove {len(remove_ids)} discovered skills)")
    print(f"  structural conflicts: {len(conflicts)}")
    if args.judge and verdicts_by_rid:
        from collections import Counter
        verdict_counts = Counter(v.verdict for v in verdicts_by_rid.values())
        print(f"  judge verdicts:      {dict(verdict_counts)}")
    print()

    # ── Prune ──────────────────────────────────────────
    if args.prune and remove_ids:
        print("## Prune plan")
        for loser, pair in removal_log:
            print(f"  - REMOVE {loser.short_id}  {loser.name[:60]}")
            print(f"       matches {pair.a.short_id if pair.a is not loser else pair.b.short_id} "
                  f"(cos={pair.cosine:.3f})")
        print()

        if args.apply:
            before = len(live_raw)
            after_list = _prune_live_json(live_raw, remove_ids)
            after = len(after_list)
            if after < before:
                args.skills_path.write_text(
                    json.dumps(after_list, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                print(f"✓ Rewrote {args.skills_path}: {before} → {after} entries.")
            else:
                print(f"(no live-json entries were in remove set; {args.skills_path} unchanged)")
        else:
            print("--apply not set; no files modified. Rerun with --prune --apply to commit.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
