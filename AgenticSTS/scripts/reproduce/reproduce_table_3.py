"""Reproduce Table 3 (cross-backbone probe).

For each backbone (Qwen, DeepSeek, Gemini) reports `baseline-strict` and
`full-frozen` cells side by side: N, wins, mean derived score, and the
percentage score shift `(full - baseline) / baseline * 100`.

Snapshot reference: `snapshots/table_3.json`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.reproduce._lib import (
    CROSS_BACKBONE_CELLS,
    bootstrap_ci,
    cli_update_flag,
    compare_to_snapshot,
    derived_score_for,
    filter_cell,
    load_history,
    wilson_ci,
)


def _cell_stats(records: list[dict], tag: str, limit: int | None) -> dict:
    rows = filter_cell(records, tag, limit=limit)
    n = len(rows)
    wins = sum(1 for r in rows if r.get("victory"))
    scores = [derived_score_for(r) for r in rows]
    mean_score = sum(scores) / n if n else 0.0
    wilson = wilson_ci(wins, n)
    boot = bootstrap_ci(scores)
    return {
        "experiment_tag": tag,
        "n": n,
        "wins": wins,
        "mean_score": round(mean_score, 2),
        "wilson95_lo": round(wilson[0], 1),
        "wilson95_hi": round(wilson[1], 1),
        "bootstrap95_lo": round(boot[0], 2),
        "bootstrap95_hi": round(boot[1], 2),
    }


def compute_table_3(records: list[dict]) -> dict:
    backbones = []
    for label, base_tag, full_tag in CROSS_BACKBONE_CELLS:
        # Gemini cells overlap with Table 2 and use N=10. Qwen+DeepSeek cells
        # are N=5 by design (probe stream, never pooled with the headline).
        limit = 10 if label.startswith("Gemini") else 5
        base = _cell_stats(records, base_tag, limit=limit)
        full = _cell_stats(records, full_tag, limit=limit)
        delta_pct = (
            (full["mean_score"] - base["mean_score"]) / base["mean_score"] * 100.0
            if base["mean_score"]
            else 0.0
        )
        backbones.append(
            {
                "backbone": label,
                "baseline-strict": base,
                "full-frozen": full,
                "delta_pct": round(delta_pct, 1),
            }
        )
    return {"backbones": backbones}


def print_table(computed: dict) -> None:
    print("Cross-backbone probe (diagnostic stream, NEVER pooled with Table 2)")
    print()
    print(
        f"{'Backbone':17s}  {'N':>3s}  {'wins(base→full)':16s}  "
        f"{'score base→full':18s}  {'Δ%':>7s}"
    )
    print("-" * 78)
    for b in computed["backbones"]:
        base = b["baseline-strict"]
        full = b["full-frozen"]
        wins = f"{base['wins']}/{base['n']} → {full['wins']}/{full['n']}"
        score = f"{base['mean_score']:6.2f} → {full['mean_score']:6.2f}"
        print(
            f"{b['backbone']:17s}  {base['n']:>3d}  {wins:16s}  "
            f"{score:18s}  {b['delta_pct']:>+7.1f}%"
        )


def main(argv: list[str]) -> int:
    update = cli_update_flag(argv)
    snapshot = Path(__file__).parent / "snapshots" / "table_3.json"

    records = load_history()
    computed = compute_table_3(records)
    print_table(computed)

    ok = compare_to_snapshot(computed, snapshot, tol=1.0, update=update)
    print()
    if update:
        print(f"snapshot updated: {snapshot}")
        return 0
    if ok:
        print(f"snapshot OK: {snapshot}")
        return 0
    print(f"SNAPSHOT MISMATCH against {snapshot}.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
