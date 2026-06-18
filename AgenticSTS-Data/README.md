# AgenticSTS-Data

This directory is the **frozen, SHA-anchored** data snapshot that backs the
paper. It contains the L4 (episodic memory) and L5 (skill) stores, the
evolution artifacts, and the run-level archive used to compute every table and
figure. The frozen-store commit is SHA `1888a62`.

## Contents

- `memory/` — L4 hierarchical categorical episodic memory stores.
- `skills/` — L5 retrieval-augmented skill library.
- `evolution/` — Post-run self-evolution artifacts.
- `runs/history.jsonl` — Run-level archive. One JSON object per line.
- `runs/ascension_stats.json` — Per-character ascension progression stats.
- `experiments/` — Per-condition experiment groupings.

## The run archive

**Run counts (298 / 312 / 385 — the same explanation appears on the repo and HF dataset).**
`runs/history.jsonl` holds **385 run-level rows**, of which **298** are completed games
(outcome `victory` or `defeat`) that enter the paper corpus. The remaining rows are
non-completing harness rows (aborts, interrupts, decision-caps) kept for audit and
reproducibility; they are excluded from the paper's statistics. The Hugging Face dataset
`ShandaAI/AgenticSTS-trajectories` packages a **312-record analysis superset** — the 298
paper games plus **14** decision-capped (`max_steps`) runs — with full per-decision logs
(298 + 14 = 312).

## Reproducing the paper

The scripts under `AgenticSTS/scripts/reproduce/` recompute the paper's tables
and figures directly from `runs/history.jsonl`. Point `STS2_DATA_REPO` at this
directory (or rely on the monorepo-subdir / sibling-checkout fallback) and run
the reproduce scripts.

## Full trajectories

The **full per-decision trajectories (305 gzipped logs)** plus the
**competitor capture archives** are not stored here. They live in the Hugging
Face dataset `ShandaAI/AgenticSTS-trajectories`
(https://huggingface.co/datasets/ShandaAI/AgenticSTS-trajectories), currently
**private**. It will be made public when the paper's anonymity period lifts.

## License

The data in this directory is released under **CC-BY-4.0** (see `LICENSE`).
