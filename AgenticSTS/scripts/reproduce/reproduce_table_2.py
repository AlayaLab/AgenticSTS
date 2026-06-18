"""Reproduce Table 2 (fixed-A0 5-cell ablation, headline result).

Reads `$STS2_DATA_REPO/runs/history.jsonl`, selects the first ten
completed games per condition by start time, computes Wilson 95% CIs on
win rate and percentile-bootstrap 95% CIs on the derived score (Eq. (1)),
and prints the table verbatim. Exits non-zero if any computed value
diverges from `snapshots/table_2.json`.

Usage:
    python -m scripts.reproduce.reproduce_table_2
    python -m scripts.reproduce.reproduce_table_2 --update-snapshot
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.reproduce._lib import (
    FIXED_A0_CELLS,
    bootstrap_ci,
    cli_update_flag,
    compare_to_snapshot,
    derived_score_for,
    filter_cell,
    load_history,
    wilson_ci,
)


def compute_table_2(records: list[dict]) -> dict:
    cells = []
    for cell_name, tag in FIXED_A0_CELLS:
        cell_records = filter_cell(records, tag, limit=10)
        n = len(cell_records)
        wins = sum(1 for r in cell_records if r.get("victory"))
        scores = [derived_score_for(r) for r in cell_records]
        mean_score = sum(scores) / n if n else 0.0
        wilson = wilson_ci(wins, n)
        boot = bootstrap_ci(scores)
        cells.append(
            {
                "cell": cell_name,
                "experiment_tag": tag,
                "n": n,
                "wins": wins,
                "mean_score": round(mean_score, 2),
                "wilson95_lo": round(wilson[0], 1),
                "wilson95_hi": round(wilson[1], 1),
                "bootstrap95_lo": round(boot[0], 2),
                "bootstrap95_hi": round(boot[1], 2),
            }
        )
    return {"cells": cells}


def _l5_l4_labels(cell: str) -> tuple[str, str]:
    """Layer-configuration labels for the printed Table 2 columns.

    Mirrors the published `tab:fivecond` columns. `L5` is the skill-library
    mode: `--` (off), `A` (hand-authored seeds, Mode A), `B` (stub-filled,
    Mode B). `L4` is whether the episodic memory store is on (`yes`) or off
    (`--`). The mapping is purely a function of the cell name.
    """
    table = {
        "baseline-strict": ("--", "--"),
        "prompt-only": ("--", "--"),
        "mode-a": ("A", "--"),
        "mode-b-frozen": ("B", "--"),
        "full-frozen": ("A", "yes"),
    }
    return table.get(cell, ("--", "--"))


def print_table(computed: dict) -> None:
    print("Fixed-A0 ablation (N=10 per cell, SHA 1888a62 frozen stores)")
    print()
    print(
        f"{'cell':17s}  {'L5':3s}  {'L4':3s}  {'wins':5s}  {'wilson95':16s}  "
        f"{'mean_score':10s}  {'boot95':18s}"
    )
    print("-" * 86)
    for c in computed["cells"]:
        wilson = f"[{c['wilson95_lo']:.1f}, {c['wilson95_hi']:.1f}]"
        boot = f"[{c['bootstrap95_lo']:.1f}, {c['bootstrap95_hi']:.1f}]"
        l5, l4 = _l5_l4_labels(c["cell"])
        print(
            f"{c['cell']:17s}  {l5:3s}  {l4:3s}  {c['wins']}/{c['n']:<3d}  "
            f"{wilson:16s}  {c['mean_score']:>10.2f}  {boot:18s}"
        )

    cells_by_name = {c["cell"]: c for c in computed["cells"]}
    if "prompt-only" in cells_by_name and "baseline-strict" in cells_by_name:
        d_prompt = cells_by_name["prompt-only"]["wins"] - cells_by_name["baseline-strict"]["wins"]
        print()
        print(f"Delta_prompt = {d_prompt:+d}/10    (strictness, wrappers)")
    if "mode-a" in cells_by_name and "prompt-only" in cells_by_name:
        d_l5 = cells_by_name["mode-a"]["wins"] - cells_by_name["prompt-only"]["wins"]
        print(f"Delta_L5     = {d_l5:+d}/10    (at same prompt setup; main lift)")


def main(argv: list[str]) -> int:
    update = cli_update_flag(argv)
    snapshot = Path(__file__).parent / "snapshots" / "table_2.json"

    records = load_history()
    computed = compute_table_2(records)
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
    print("Inspect with: python -m json.tool scripts/reproduce/snapshots/table_2.json")
    print("Regenerate (if intentional) with --update-snapshot.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
