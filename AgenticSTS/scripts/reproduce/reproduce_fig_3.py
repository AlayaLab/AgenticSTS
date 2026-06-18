"""Reproduce Figure 3 (bounded-memory token audit, fig_bounded_ablation.pdf).

The figure compares actual per-decision prompt-token usage (bounded by the
contract) against a transcript-appending counterfactual at one quarter of
naive O(c^2) growth: `median tokens/call * c(c+1)/8`.

For each of the five fixed-A0 cells we take two runs (per the figure
caption, 2 runs * 5 cells = 10 runs total) and plot both curves. The
output PDF is written with a `_recomputed` suffix so the submitted bundle's
copy of the figure is preserved.

`runs/history.jsonl` records the total `llm_calls` per run but not
per-call token counts; we therefore use a fixed median tokens/call
(`MEDIAN_TOKENS_PER_CALL`) and compare the resulting totals against the
snapshot at `snapshots/fig_3.json`. If you have a per-call token log
available in the future, point this script at it through the env var
`STS2_TOKEN_LOG_DIR`; otherwise the median-token shortcut is sufficient
for the figure's audit purpose (showing the linearity contrast).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from scripts.reproduce._lib import (
    FIXED_A0_CELLS,
    cli_update_flag,
    compare_to_snapshot,
    filter_cell,
    load_history,
)

# Median strategic-tier tokens per call. The paper's run-cost footnote
# reports "67 strategic calls/run (IQR 27-105)"; a typical strategic-tier
# user message under the bounded contract is ~5000 tokens (system prompt
# uses prompt caching and is not re-billed). This is held constant across
# all cells so the audit only compares decision counts.
MEDIAN_TOKENS_PER_CALL = 5000

# 2 runs/cell for the figure (per caption "two per cell").
RUNS_PER_CELL = 2

# Counterfactual coefficient: 1/4 of naive O(c^2) growth = c(c+1)/8.
# A moderate prompt-caching discount on a transcript-appending baseline.
def counterfactual_tokens(c: int, tokens_per_call: int = MEDIAN_TOKENS_PER_CALL) -> float:
    return tokens_per_call * c * (c + 1) / 8.0


def actual_tokens(c: int, tokens_per_call: int = MEDIAN_TOKENS_PER_CALL) -> float:
    return float(tokens_per_call * c)


def compute_fig_3(records: list[dict]) -> dict:
    cells = []
    for cell_name, tag in FIXED_A0_CELLS:
        rows = filter_cell(records, tag, limit=RUNS_PER_CELL)
        calls = [int(r.get("llm_calls", 0) or 0) for r in rows]
        runs = [
            {
                "run_id": r.get("run_id"),
                "llm_calls": int(r.get("llm_calls", 0) or 0),
                "steps": int(r.get("steps", 0) or 0),
                "outcome": r.get("outcome"),
                "actual_tokens": actual_tokens(int(r.get("llm_calls", 0) or 0)),
                "counterfactual_tokens": counterfactual_tokens(int(r.get("llm_calls", 0) or 0)),
            }
            for r in rows
        ]
        sum_actual = sum(r["actual_tokens"] for r in runs)
        sum_counterfactual = sum(r["counterfactual_tokens"] for r in runs)
        cells.append(
            {
                "cell": cell_name,
                "experiment_tag": tag,
                "n": len(rows),
                "mean_llm_calls": round(sum(calls) / len(calls), 1) if calls else 0.0,
                "sum_actual_tokens": sum_actual,
                "sum_counterfactual_tokens": sum_counterfactual,
                "ratio": (sum_counterfactual / sum_actual) if sum_actual else 0.0,
                "runs": runs,
            }
        )
    return {
        "median_tokens_per_call": MEDIAN_TOKENS_PER_CALL,
        "runs_per_cell": RUNS_PER_CELL,
        "cells": cells,
    }


def plot_fig_3(computed: dict, out_path: Path) -> None:
    try:
        import matplotlib  # noqa: F401
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for reproduce_fig_3 (see pyproject.toml)."
        ) from exc

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(11, 4.2))

    max_c = 0
    for cell in computed["cells"]:
        for run in cell["runs"]:
            max_c = max(max_c, run["llm_calls"])
    max_c = max(max_c, 1)

    # Panel A: per-run growth curves, actual vs counterfactual.
    cmap = ["#8C6BB1", "#2B8CBE", "#31A354", "#F16913", "#D94801"]
    for ci, cell in enumerate(computed["cells"]):
        color = cmap[ci % len(cmap)]
        for run in cell["runs"]:
            c = run["llm_calls"]
            xs = list(range(0, c + 1, max(1, c // 32)))
            if xs[-1] != c:
                xs.append(c)
            ys_actual = [actual_tokens(x) for x in xs]
            ax_a.plot(xs, ys_actual, color=color, alpha=0.85, lw=1.2)

    # Reference counterfactual curve: 1/4 O(c^2) using mean call count.
    xs_cf = list(range(0, max_c + 1, max(1, max_c // 64)))
    if xs_cf[-1] != max_c:
        xs_cf.append(max_c)
    ys_cf = [counterfactual_tokens(x) for x in xs_cf]
    ax_a.plot(xs_cf, ys_cf, color="black", ls="--", lw=1.4,
              label=r"counterfactual $\frac{1}{4} O(c^2)$")

    ax_a.set_xlabel("strategic decisions $c$")
    ax_a.set_ylabel("cumulative prompt tokens")
    ax_a.set_title("(a) Per-run growth")
    ax_a.legend(loc="upper left", fontsize=8)
    ax_a.grid(True, alpha=0.25)

    # Panel B: per-cell totals (actual vs counterfactual).
    cells = computed["cells"]
    names = [c["cell"] for c in cells]
    actuals = [c["sum_actual_tokens"] for c in cells]
    cf = [c["sum_counterfactual_tokens"] for c in cells]

    import numpy as np
    x = np.arange(len(cells))
    width = 0.38
    ax_b.bar(x - width / 2, actuals, width, label="actual (bounded)", color="#2B8CBE")
    ax_b.bar(x + width / 2, cf, width,
             label=r"counterfactual $\frac{1}{4} O(c^2)$",
             color="#A0A0A0", hatch="//")
    ax_b.set_xticks(x)
    ax_b.set_xticklabels(names, rotation=20, ha="right", fontsize=8)
    ax_b.set_ylabel("tokens (sum across 2 runs)")
    ax_b.set_title("(b) Per-cell totals")
    ax_b.legend(loc="upper left", fontsize=8)
    ax_b.grid(True, axis="y", alpha=0.25)

    fig.suptitle(
        "Bounded-memory contract token audit (recomputed from history.jsonl)",
        fontsize=11,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.96])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="pdf", bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str]) -> int:
    update = cli_update_flag(argv)
    snapshot = Path(__file__).parent / "snapshots" / "fig_3.json"

    records = load_history()
    computed = compute_fig_3(records)

    # Plot to figures/v2/fig_bounded_ablation_recomputed.pdf (NOT the
    # submitted bundle's frozen artefact).
    repo_root = Path(__file__).resolve().parents[2]
    out_pdf = (
        repo_root
        / "paper"
        / "STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents"
        / "figures"
        / "v2"
        / "fig_bounded_ablation_recomputed.pdf"
    )
    override = os.environ.get("STS2_REPRODUCE_FIG3_OUTPUT")
    if override:
        out_pdf = Path(override)
    plot_fig_3(computed, out_pdf)
    print(f"wrote {out_pdf}")

    print()
    print("Per-cell token audit (median tokens/call =", MEDIAN_TOKENS_PER_CALL, ")")
    print(f"{'cell':17s}  {'mean_c':>7s}  {'sum actual':>14s}  {'sum 1/4 O(c^2)':>16s}  {'ratio':>7s}")
    print("-" * 72)
    for c in computed["cells"]:
        print(
            f"{c['cell']:17s}  {c['mean_llm_calls']:>7.1f}  "
            f"{c['sum_actual_tokens']:>14,.0f}  "
            f"{c['sum_counterfactual_tokens']:>16,.0f}  "
            f"{c['ratio']:>7.1f}x"
        )

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
