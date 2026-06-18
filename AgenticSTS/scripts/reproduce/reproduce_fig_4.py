"""Reproduce Figure 4 (auto-mode ascension ladder, fig5_ascension_ladder.pdf).

For each ladder stream, plot `target_ascension` against run index (run
order is `started_at`). Per the README headline: postrun-active streams
reach A6-A8, no-postrun streams stop at A2-A4. The endpoint metric is
the highest attempted ascension per stream.

The output PDF is written with a `_recomputed` suffix so the submitted
bundle's frozen artefact is preserved at `figures/v2/fig5_ascension_ladder.pdf`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from scripts.reproduce._lib import (
    LADDER_STREAMS,
    cli_update_flag,
    compare_to_snapshot,
    filter_cell,
    load_history,
)


def compute_fig_4(records: list[dict]) -> dict:
    streams = []
    for label, tag in LADDER_STREAMS:
        rows = filter_cell(records, tag)
        runs = [
            {
                "run_id": r.get("run_id"),
                "started_at": r.get("started_at"),
                "target_ascension": r.get("target_ascension"),
                "actual_ascension": r.get("actual_ascension"),
                "outcome": r.get("outcome"),
                "final_floor": r.get("final_floor"),
                "victory": bool(r.get("victory")),
            }
            for r in rows
        ]
        targets = [r["target_ascension"] for r in runs if r["target_ascension"] is not None]
        actuals = [r["actual_ascension"] for r in runs if r["actual_ascension"] is not None]
        streams.append(
            {
                "stream": label,
                "experiment_tag": tag,
                "n": len(runs),
                "max_target_ascension": max(targets) if targets else None,
                "max_actual_ascension": max(actuals) if actuals else None,
                "wins": sum(1 for r in runs if r["victory"]),
                "runs": runs,
            }
        )
    return {"streams": streams}


def plot_fig_4(computed: dict, out_path: Path) -> None:
    try:
        import matplotlib  # noqa: F401
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError(
            "matplotlib is required for reproduce_fig_4 (see pyproject.toml)."
        ) from exc

    fig, ax = plt.subplots(figsize=(8, 4.5))
    colors = ["#8C6BB1", "#2B8CBE", "#D94801"]
    markers = ["o", "s", "D"]

    for i, stream in enumerate(computed["streams"]):
        runs = stream["runs"]
        if not runs:
            continue
        xs = list(range(1, len(runs) + 1))
        ys = [r["target_ascension"] for r in runs]
        wins = [r["victory"] for r in runs]
        color = colors[i % len(colors)]
        marker = markers[i % len(markers)]
        # Connect with a line; mark wins as filled, losses as hollow.
        ax.plot(xs, ys, color=color, lw=1.0, alpha=0.6, zorder=1)
        for x, y, w in zip(xs, ys, wins):
            ax.scatter(
                [x],
                [y],
                color=color if w else "white",
                edgecolor=color,
                marker=marker,
                s=55,
                lw=1.5,
                zorder=3,
            )
        ax.scatter([], [], color=color, marker=marker, label=stream["stream"], s=55, lw=1.5)

    ax.set_xlabel("run index (sorted by start time)")
    ax.set_ylabel("target ascension")
    ax.set_yticks(list(range(0, 11)))
    ax.set_ylim(-0.5, 10.5)
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=9, title="stream")
    ax.set_title(
        "Auto-mode ascension ladder (filled = victory)",
        fontsize=11,
    )
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="pdf", bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str]) -> int:
    update = cli_update_flag(argv)
    snapshot = Path(__file__).parent / "snapshots" / "fig_4.json"

    records = load_history()
    computed = compute_fig_4(records)

    repo_root = Path(__file__).resolve().parents[2]
    out_pdf = (
        repo_root
        / "paper"
        / "STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents"
        / "figures"
        / "v2"
        / "fig5_ascension_ladder_recomputed.pdf"
    )
    override = os.environ.get("STS2_REPRODUCE_FIG4_OUTPUT")
    if override:
        out_pdf = Path(override)
    plot_fig_4(computed, out_pdf)
    print(f"wrote {out_pdf}")

    print()
    print("Auto-mode ladder endpoints")
    print(
        f"{'stream':18s}  {'N':>3s}  {'wins':>5s}  {'max_target':>11s}  {'max_actual':>11s}"
    )
    print("-" * 60)
    for s in computed["streams"]:
        max_t = s["max_target_ascension"]
        max_a = s["max_actual_ascension"]
        print(
            f"{s['stream']:18s}  {s['n']:>3d}  {s['wins']:>5d}  "
            f"{('A' + str(max_t) if max_t is not None else '-'): >11s}  "
            f"{('A' + str(max_a) if max_a is not None else '-'): >11s}"
        )

    # For snapshot comparison, the per-run list contains floats (started_at)
    # we cannot compare with tol=1.0 because started_at is a unix timestamp.
    # Round/drop volatile fields before comparing.
    snapshot_view = {
        "streams": [
            {
                k: v
                for k, v in s.items()
                if k != "runs"
            }
            | {
                "run_targets": [r["target_ascension"] for r in s["runs"]],
                "run_outcomes": [r["outcome"] for r in s["runs"]],
            }
            for s in computed["streams"]
        ]
    }
    ok = compare_to_snapshot(snapshot_view, snapshot, tol=1.0, update=update)
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
