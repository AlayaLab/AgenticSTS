"""Aggregate ablation experiment runs into a Markdown comparison table.

Reads data/runs/history.jsonl, filters by --tag, groups by (model_family, skills,
memory, evolution), computes win rate / avg floor / avg fitness / combat win rate
with 95% bootstrap CIs, and emits Markdown to stdout or --out <path>.

Usage:
    python -m scripts.ablation_report --tag ablation-2026-04-21
    python -m scripts.ablation_report --tag ablation-2026-04-21 --out docs/abl-report.md
"""
from __future__ import annotations

import argparse
import logging
import random
import subprocess
from functools import lru_cache
from pathlib import Path
from statistics import mean

from src.runs.history import RunHistoryStore, RunRecord
from src.storage import paths

logger = logging.getLogger(__name__)


def condition_id_from_record(r: RunRecord) -> str:
    """Derive condition ID 'family-{baseline-strict|prompt-only|self-evolve|full|baseline|mixed}'
    from profile fields.
    """
    profile = r.model_profile or {}
    family = profile.get("strategic_family") or profile.get("fast_family") or "unknown"
    skills = bool(profile.get("skills_enabled", r.skills_enabled))
    memory = bool(profile.get("memory_enabled", r.memory_enabled))
    evolution = bool(profile.get("evolution_enabled", False))
    postrun = bool(profile.get("postrun_enabled", False))

    is_baseline_strict = (
        not skills and not memory and not evolution
        and profile.get("prompt_variant") == "baseline"
        and profile.get("prompt_hint_filter")
        and profile.get("knowledge_strict")
        and not profile.get("stm_enabled")
        and not profile.get("combat_conversation_enabled")
        and not profile.get("include_boss_hp")
    )
    is_prompt_only = (
        not skills and not memory and not evolution
        and profile.get("prompt_variant") == "full"
        and not profile.get("prompt_hint_filter")
        and not profile.get("knowledge_strict")
        and not profile.get("stm_enabled")
        and profile.get("combat_conversation_enabled")
        and profile.get("include_boss_hp")
    )
    is_self_evolve = (
        skills and memory and evolution and postrun
        and profile.get("prompt_variant") == "full"
        and profile.get("stm_enabled")
    )
    is_full = (
        skills and memory and evolution and not postrun
    )

    if is_baseline_strict:
        kind = "baseline-strict"
    elif is_prompt_only:
        kind = "prompt-only"
    elif is_self_evolve:
        kind = "self-evolve"
    elif is_full:
        kind = "full"
    elif not skills and not memory and not evolution:
        kind = "baseline"
    else:
        kind = "mixed"
    return f"{family}-{kind}"


@lru_cache(maxsize=None)
def _run_postrun_paths_changed(run_id: str, repo_root: str) -> tuple[str, ...]:
    """Files changed by the postrun commit for ``run_id``.

    Locates the commit by grepping git log for ``run <run_id>`` (the format
    ``RunHistoryStore.commit_run`` writes). Returns ``()`` if no commit is
    found, the directory isn't a git repo, git is unavailable, or the call
    times out — caller treats empty as "unknown".
    """
    if not run_id:
        return ()
    try:
        sha = subprocess.run(
            ["git", "-C", repo_root, "log", "--all", "-F",
             f"--grep=run {run_id}", "--format=%H", "-1"],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout.strip()
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ()
    if not sha:
        return ()
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "diff-tree", "--no-commit-id",
             "--name-only", "-r", sha],
            capture_output=True, text=True, timeout=10, check=False,
        ).stdout
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return ()
    return tuple(line.strip() for line in out.splitlines() if line.strip())


def _self_evolve_isolation_status(record: RunRecord) -> str:
    """Classify a self-evolve run by where its postrun writes landed.

    - ``isolated``: writes only under ``experiments/<tag>/<cond>/`` — clean.
    - ``misdirected``: writes touched root ``memory/``/``skills/``/``evolution/`` —
      contaminated (orchestrator was bypassed, or ``STS2_DATA_REPO`` not set).
    - ``unknown``: no postrun commit found (postrun off / crashed / no git).
    """
    repo_root = str(paths.runs_history_root())
    files = _run_postrun_paths_changed(record.run_id, repo_root)
    if not files:
        return "unknown"
    leaked = any(
        p.startswith(("memory/", "skills/", "evolution/"))
        for p in files
    )
    if leaked:
        return "misdirected"
    isolated = any(p.startswith("experiments/") for p in files)
    return "isolated" if isolated else "unknown"


def condition_id_for_report(
    record: RunRecord, *, check_isolation: bool = True,
) -> str:
    """Report-time classification: same as ``condition_id_from_record`` but
    self-evolve runs whose postrun leaked to the shared root are tagged
    ``self-evolve-misdirected`` so they can be excluded from comparisons.

    Kept separate from ``condition_id_from_record`` because the orchestrator's
    slot-counting (``count_existing_runs`` in ``run_ablation.py``) must keep
    treating misdirected runs as completed self-evolve slots — re-launching
    them would just duplicate effort. Only the report aggregator cares about
    methodological cleanliness.
    """
    cid = condition_id_from_record(record)
    if not check_isolation:
        return cid
    family, _, kind = cid.rpartition("-")
    if kind != "self-evolve":
        return cid
    if _self_evolve_isolation_status(record) == "misdirected":
        return f"{family}-self-evolve-misdirected"
    return cid


def bootstrap_ci(values: list[float], *, n_boot: int = 2000,
                 level: float = 0.95, seed: int = 42) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of `values`."""
    if not values:
        return (0.0, 0.0)
    if len(values) == 1 or all(v == values[0] for v in values):
        return (values[0], values[0])
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int((1 - level) / 2 * n_boot)
    hi_idx = min(int((1 + level) / 2 * n_boot), n_boot - 1)
    return (means[lo_idx], means[hi_idx])


def aggregate_by_condition(
    records: list[RunRecord], *, check_isolation: bool = True,
) -> dict[str, dict]:
    buckets: dict[str, list[RunRecord]] = {}
    skipped = 0
    misdirected = 0
    for r in records:
        cid = condition_id_for_report(r, check_isolation=check_isolation)
        if cid.startswith("unknown-"):
            skipped += 1
            continue
        if cid.endswith("-self-evolve-misdirected"):
            misdirected += 1
        buckets.setdefault(cid, []).append(r)
    if skipped:
        logger.warning(
            "Skipped %d record(s) with no model family in model_profile", skipped
        )
    if misdirected:
        logger.warning(
            "%d self-evolve run(s) flagged misdirected (postrun leaked to shared "
            "root instead of experiments/<tag>/<cond>/) — bucketed separately as "
            "*-self-evolve-misdirected, not counted toward *-self-evolve.",
            misdirected,
        )

    out: dict[str, dict] = {}
    for cid, recs in buckets.items():
        wins = [1.0 if r.victory else 0.0 for r in recs]
        floors = [float(r.final_floor) for r in recs]
        fitnesses = [float(r.fitness) for r in recs]
        combat_wins = sum(r.combats_won for r in recs)
        combat_total = sum(r.combats_total for r in recs)
        out[cid] = {
            "n": len(recs),
            "win_rate": mean(wins) if wins else 0.0,
            "win_rate_ci": bootstrap_ci(wins),
            "avg_floor": mean(floors) if floors else 0.0,
            "avg_fitness": mean(fitnesses) if fitnesses else 0.0,
            "combat_win_rate": (combat_wins / combat_total) if combat_total else 0.0,
        }
    return out


def format_markdown(agg: dict[str, dict], *, tag: str) -> str:
    lines: list[str] = []
    safe_tag = tag.replace("`", "'").replace("\n", " ").strip()
    lines.append(f"# Ablation Report: `{safe_tag}`")
    lines.append("")
    lines.append("| Condition | n | Win rate | 95% CI | Avg floor | Avg fitness | Combat win% |")
    lines.append("|---|---:|---:|---|---:|---:|---:|")

    def _fmt_row(cid: str, s: dict) -> str:
        lo, hi = s["win_rate_ci"]
        return (
            f"| `{cid}` | {s['n']} | {s['win_rate']:.1%} "
            f"| [{lo:.1%}, {hi:.1%}] | {s['avg_floor']:.1f} "
            f"| {s['avg_fitness']:.3f} | {s['combat_win_rate']:.1%} |"
        )

    for cid in sorted(agg.keys()):
        lines.append(_fmt_row(cid, agg[cid]))

    families = sorted({cid.rsplit("-", 1)[0] for cid in agg.keys()})
    lines.append("")
    lines.append("## Δ (full - baseline)")
    lines.append("")
    lines.append("| Family | Δ Win rate | Δ Avg floor | Δ Avg fitness | Δ Combat win% |")
    lines.append("|---|---:|---:|---:|---:|")
    for fam in families:
        b = agg.get(f"{fam}-baseline")
        f = agg.get(f"{fam}-full")
        if not b or not f:
            continue
        lines.append(
            f"| {fam} "
            f"| {f['win_rate'] - b['win_rate']:+.1%} "
            f"| {f['avg_floor'] - b['avg_floor']:+.1f} "
            f"| {f['avg_fitness'] - b['avg_fitness']:+.3f} "
            f"| {f['combat_win_rate'] - b['combat_win_rate']:+.1%} |"
        )

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", type=str, required=True)
    parser.add_argument("--history", type=Path, default=paths.runs_history_file())
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--no-isolation-check", action="store_true",
        help="Skip git lookup that flags self-evolve runs whose postrun writes "
             "leaked to the shared root. Disable when running outside a git "
             "checkout of the data repo.",
    )
    args = parser.parse_args()

    store = RunHistoryStore.load(args.history)
    records = store.query(experiment_tag=args.tag)
    if not records:
        print(f"No records found with experiment_tag={args.tag!r} in {args.history}")
        return 1

    agg = aggregate_by_condition(
        records, check_isolation=not args.no_isolation_check,
    )
    md = format_markdown(agg, tag=args.tag)

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
        print(f"Wrote {args.out}")
    else:
        print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
