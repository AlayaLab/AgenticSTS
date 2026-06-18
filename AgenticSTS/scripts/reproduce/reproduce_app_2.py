"""Reproduce Appendix Table 2 (per-cell floor + boss-clear counts).

Mirrors `tab:cell-floor-boss` in `appendix.tex`. Snapshot reference:
`snapshots/app_2.json`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.reproduce._lib import (
    FIXED_A0_CELLS,
    boss_count_from_floor,
    cli_update_flag,
    compare_to_snapshot,
    derived_score_for,
    filter_cell,
    load_history,
)


def compute_app_2(records: list[dict]) -> dict:
    cells = []
    for cell_name, tag in FIXED_A0_CELLS:
        rows = filter_cell(records, tag, limit=10)
        n = len(rows)
        wins = sum(1 for r in rows if r.get("victory"))
        floors = [int(r.get("final_floor", 0) or 0) for r in rows]
        bosses = [
            boss_count_from_floor(int(r.get("final_floor", 0) or 0), r.get("outcome") or "")
            for r in rows
        ]
        scores = [derived_score_for(r) for r in rows]
        cells.append(
            {
                "cell": cell_name,
                "n": n,
                "wins": wins,
                "avg_floor": round(sum(floors) / n, 1) if n else 0.0,
                "avg_bosses": round(sum(bosses) / n, 2) if n else 0.0,
                "avg_score": round(sum(scores) / n, 2) if n else 0.0,
            }
        )
    return {"cells": cells}


def print_table(computed: dict) -> None:
    print("Per-cell floor + boss-clear audit (Appendix Table 2)")
    print()
    print(
        f"{'Cell':17s}  {'N':>3s}  {'Wins':>4s}  {'avg_floor':>9s}  "
        f"{'avg_bosses':>10s}  {'avg_score':>9s}"
    )
    print("-" * 64)
    for c in computed["cells"]:
        print(
            f"{c['cell']:17s}  {c['n']:>3d}  {c['wins']:>4d}  "
            f"{c['avg_floor']:>9.1f}  {c['avg_bosses']:>10.2f}  "
            f"{c['avg_score']:>9.2f}"
        )


def main(argv: list[str]) -> int:
    update = cli_update_flag(argv)
    snapshot = Path(__file__).parent / "snapshots" / "app_2.json"

    records = load_history()
    computed = compute_app_2(records)
    print_table(computed)

    ok = compare_to_snapshot(computed, snapshot, tol=1e-2, update=update)
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
