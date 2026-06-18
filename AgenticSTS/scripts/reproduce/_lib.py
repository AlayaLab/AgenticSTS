"""Shared utilities for the paper-reproduction scripts.

These helpers read the released trajectory archive (`runs/history.jsonl`),
derive per-run scores from the bounded-memory paper's Eq. (1), and provide
the three confidence-interval helpers used in `tab:fivecond` and the
appendix audit (Wilson 95% for win rates, percentile bootstrap for score
intervals, Clopper-Pearson for the descriptive pooled scaffolded row).

Used by `reproduce_table_2.py`, `reproduce_table_3.py`, `reproduce_fig_3.py`,
`reproduce_fig_4.py`, and `reproduce_app_2.py`.
"""

from __future__ import annotations

import json
import math
import os
import random
from pathlib import Path
from typing import Any

# 5 fixed-A0 cells used by Table 2 / Appendix Table 2 / Figure 3.
# Order matches the published Table 2 row order in the paper.
FIXED_A0_CELLS: list[tuple[str, str]] = [
    ("baseline-strict", "gemini-pilot-2026-05-08-A0-baseline"),
    ("prompt-only", "gemini-pilot-2026-05-09-A0-prompt-only"),
    ("mode-a", "gemini-pilot-2026-05-09-A0-mode-a-makeup"),
    ("mode-b-frozen", "gemini-pilot-2026-05-12-A0-mode-b-frozen"),
    ("full-frozen", "gemini-pilot-2026-05-08-A0-full-frozen"),
]

# Cross-backbone probe cells (Table 3). N=5/cell for Qwen+DeepSeek,
# Gemini cells are reused from the fixed-A0 stream (N=10).
CROSS_BACKBONE_CELLS: list[tuple[str, str, str]] = [
    # (backbone label, baseline tag, full-frozen tag)
    ("Qwen 3.6-27B", "qwen-pilot-2026-05-07-A0-baseline", "qwen-pilot-2026-05-07-A0-full-frozen"),
    ("DeepSeek V4-Pro", "deepseek-pilot-2026-05-07-A0-baseline", "deepseek-pilot-2026-05-07-A0-full-frozen"),
    ("Gemini 3.1-Pro", "gemini-pilot-2026-05-08-A0-baseline", "gemini-pilot-2026-05-08-A0-full-frozen"),
]

# Auto-mode ladder streams (Figure 4 endpoint metric).
#
# Two no-postrun streams (cap at A2-A4, expected) and two postrun-active
# streams (reach A6-A8, matching the paper's `mode-b-*` selection). The
# postrun-active streams have `model_profile.postrun_enabled=True` and
# `memory_enabled=True`/`skills_enabled=True` in `runs/history.jsonl`,
# whereas the originally-named `auto-mode-b` tag
# (`ablation-auto-2026-05-06`) carried `postrun_enabled=False` and so
# only reached A5 — that mislabeling was the cause of the panel-5
# Figure 4 reproducibility gap.
LADDER_STREAMS: list[tuple[str, str]] = [
    # (label, experiment_tag)
    ("auto-prompt-only", "gemini-pilot-2026-05-10-auto-prompt-only"),
    ("auto-mode-a", "gemini-pilot-2026-05-10-auto-mode-a"),
    ("auto-mode-b-fixed", "mode-b-fixed-2026-05-04"),
    ("auto-gem-b-medium", "gem-b-medium-2026-05-01"),
]


def history_path(path: Path | None = None) -> Path:
    """Resolve the location of `runs/history.jsonl`.

    Precedence:
      1. Explicit `path` argument.
      2. `$STS2_DATA_REPO/runs/history.jsonl`.
      3. `<repo root>/data/runs/history.jsonl` (legacy local-only layout).
      4. Monorepo subdir at `<repo root>/AgenticSTS-Data/runs/history.jsonl`.
      5. Sibling repo at `../AgenticSTS-Data/runs/history.jsonl`.
    """
    if path is not None:
        return path

    env = os.environ.get("STS2_DATA_REPO")
    if env:
        p = Path(env) / "runs" / "history.jsonl"
        if p.exists():
            return p

    repo_root = Path(__file__).resolve().parents[2]
    local = repo_root / "data" / "runs" / "history.jsonl"
    if local.exists():
        return local

    monorepo = repo_root / "AgenticSTS-Data" / "runs" / "history.jsonl"
    if monorepo.exists():
        return monorepo

    sibling = repo_root.parent / "AgenticSTS-Data" / "runs" / "history.jsonl"
    if sibling.exists():
        return sibling

    raise FileNotFoundError(
        "Could not locate runs/history.jsonl. Set $STS2_DATA_REPO to the "
        "sibling AgenticSTS-Data checkout, or pass an explicit path. "
        "See README.md § 'Installation'."
    )


def load_history(path: Path | None = None) -> list[dict[str, Any]]:
    """Load every record from `runs/history.jsonl` as a list of dicts."""
    target = history_path(path)
    out: list[dict[str, Any]] = []
    with open(target, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Malformed JSON at {target}:{line_no}: {exc}"
                ) from exc
    return out


# ---------------------------------------------------------------------------
# Score derivation
# ---------------------------------------------------------------------------


def boss_count_from_floor(floor: int, outcome: str) -> int:
    """Return the boss-clear count used by Eq. (1).

    Per appendix `app:configs`: 0 if floor<18, 1 if floor<34, 2 otherwise;
    3 for victories.
    """
    if outcome == "victory":
        return 3
    if floor < 18:
        return 0
    if floor < 34:
        return 1
    return 2


def derive_score(outcome: str, floor: int, bosses: int) -> float:
    """Eq. (1): `s = 100 if victory else floor + (52/3) * bosses`."""
    if outcome == "victory":
        return 100.0
    return float(floor) + (52.0 / 3.0) * float(bosses)


def derived_score_for(record: dict[str, Any]) -> float:
    """Convenience wrapper: derive score directly from a history record."""
    outcome = record.get("outcome") or ""
    floor = int(record.get("final_floor", 0) or 0)
    bosses = boss_count_from_floor(floor, outcome)
    return derive_score(outcome, floor, bosses)


# ---------------------------------------------------------------------------
# Confidence intervals
# ---------------------------------------------------------------------------


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI per Eq. (3) in the appendix (eq:wilson).

    Returns a percentage tuple `(lo, hi)` in [0, 100]. For `n == 0` returns
    `(0.0, 0.0)` rather than dividing by zero.
    """
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2.0 * n)) / denom
    half = (z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))) / denom
    lo = max(0.0, center - half) * 100.0
    hi = min(1.0, center + half) * 100.0
    return (lo, hi)


def bootstrap_ci(
    scores: list[float],
    n_resamples: int = 5000,
    seed: int = 42,
) -> tuple[float, float]:
    """Percentile bootstrap 95% CI on the mean of `scores`."""
    if not scores:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(scores)
    means: list[float] = []
    for _ in range(n_resamples):
        sample = [scores[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(0.025 * n_resamples)
    hi_idx = int(0.975 * n_resamples) - 1
    hi_idx = max(0, min(hi_idx, n_resamples - 1))
    return (means[lo_idx], means[hi_idx])


def _ibeta_regularized(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta I_x(a, b), continued-fraction form.

    Used by Clopper-Pearson. We only need modest precision here so a stdlib
    implementation avoids the scipy dependency at script-load time.
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    log_front = a * math.log(x) + b * math.log(1.0 - x) - lbeta
    front = math.exp(log_front) / a

    def _cf(a: float, b: float, x: float) -> float:
        eps = 1e-15
        fpmin = 1e-300
        qab = a + b
        qap = a + 1.0
        qam = a - 1.0
        c = 1.0
        d = 1.0 - qab * x / qap
        if abs(d) < fpmin:
            d = fpmin
        d = 1.0 / d
        h = d
        for m in range(1, 200):
            m2 = 2 * m
            aa = m * (b - m) * x / ((qam + m2) * (a + m2))
            d = 1.0 + aa * d
            if abs(d) < fpmin:
                d = fpmin
            c = 1.0 + aa / c
            if abs(c) < fpmin:
                c = fpmin
            d = 1.0 / d
            h *= d * c
            aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
            d = 1.0 + aa * d
            if abs(d) < fpmin:
                d = fpmin
            c = 1.0 + aa / c
            if abs(c) < fpmin:
                c = fpmin
            d = 1.0 / d
            delta = d * c
            h *= delta
            if abs(delta - 1.0) < eps:
                break
        return h

    # Symmetry trick keeps the continued fraction in its convergent half.
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _cf(a, b, x)
    return 1.0 - math.exp(log_front) / b * _cf(b, a, 1.0 - x)


def clopper_pearson_ci(wins: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """Exact Clopper-Pearson CI for a binomial proportion.

    Used for the descriptive pooled scaffolded row that the paper labels
    explicitly. Returns a percentage tuple `(lo, hi)` in [0, 100].
    """
    if n == 0:
        return (0.0, 0.0)
    if wins == 0:
        lo = 0.0
    else:
        # Inverse of I_lo(wins, n - wins + 1) = alpha / 2 via bisection.
        target = alpha / 2.0
        lo_x, hi_x = 0.0, 1.0
        for _ in range(80):
            mid = 0.5 * (lo_x + hi_x)
            if _ibeta_regularized(wins, n - wins + 1, mid) > target:
                hi_x = mid
            else:
                lo_x = mid
        lo = 0.5 * (lo_x + hi_x)
    if wins == n:
        hi = 1.0
    else:
        target = 1.0 - alpha / 2.0
        lo_x, hi_x = 0.0, 1.0
        for _ in range(80):
            mid = 0.5 * (lo_x + hi_x)
            if _ibeta_regularized(wins + 1, n - wins, mid) < target:
                lo_x = mid
            else:
                hi_x = mid
        hi = 0.5 * (lo_x + hi_x)
    return (lo * 100.0, hi * 100.0)


# ---------------------------------------------------------------------------
# Snapshot comparison
# ---------------------------------------------------------------------------


def _close(a: Any, b: Any, tol: float) -> bool:
    if isinstance(a, (int, bool)) and isinstance(b, (int, bool)) and not isinstance(a, float):
        return a == b
    if isinstance(a, float) or isinstance(b, float):
        try:
            return abs(float(a) - float(b)) <= tol
        except (TypeError, ValueError):
            return False
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        return all(_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(_close(a[k], b[k], tol) for k in a)
    return a == b


def compare_to_snapshot(
    computed: dict[str, Any],
    snapshot_path: Path,
    tol: float = 1e-3,
    update: bool = False,
) -> bool:
    """Compare `computed` against a JSON snapshot.

    If `update` is True (or the snapshot file does not yet exist), writes
    `computed` to disk and returns True. Otherwise returns True iff every
    numeric leaf agrees within `tol`.
    """
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    if update or not snapshot_path.exists():
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(computed, f, indent=2, sort_keys=True)
        return True

    with open(snapshot_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    return _close(computed, expected, tol)


# ---------------------------------------------------------------------------
# Cell filtering
# ---------------------------------------------------------------------------


# Outcomes that the paper does NOT count as "completed" (per
# `methodology.tex` L70: "Completed games are the denominator throughout"
# and `src/runs/ascension_stats.py:18` _ABORT_OUTCOMES). The paper's "298
# completed trajectories" headline corresponds strictly to `victory +
# defeat`, excluding `max_steps` (orchestrator step-budget cutoffs that did
# not reach a natural terminal game state), `agent_abort`, `mcp_error`,
# and `interrupt`.
ABORT_OUTCOMES: frozenset[str] = frozenset(
    {"agent_abort", "mcp_error", "interrupt", "max_steps"}
)


def filter_cell(
    records: list[dict[str, Any]],
    experiment_tag: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return records for a cell, sorted by `started_at` and capped at `limit`.

    Per `methodology.tex`: "the first ten completed games per condition by
    start time". The completion filter (outcome not in `ABORT_OUTCOMES`)
    is applied BEFORE the limit truncation, so the first-N cap operates on
    the same denominator the paper uses.
    """
    matched = [
        r
        for r in records
        if r.get("experiment_tag") == experiment_tag
        and (r.get("outcome") or "") not in ABORT_OUTCOMES
    ]
    matched.sort(key=lambda r: r.get("started_at", 0.0))
    if limit is not None:
        matched = matched[:limit]
    return matched


def cli_update_flag(argv: list[str]) -> bool:
    """Tiny CLI parser shared by the reproduce scripts. Returns whether
    `--update-snapshot` was passed."""
    return "--update-snapshot" in argv
