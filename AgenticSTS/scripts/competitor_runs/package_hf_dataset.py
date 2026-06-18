"""Package the competitor-comparison raw captures as a Hugging Face dataset.

The captures (~2.3GB raw; full per-call LLM prompts/responses + per-step game I/O for
the STS2MCP and CharTyr N=5 baselines) are too large for the git repository, so they
are distributed as a HF dataset. This script stages the dataset directory (zstd-
compressed per-run archives + dataset card) and prints the upload command.

Usage:
  python -m scripts.competitor_runs.package_hf_dataset --out dist/hf_dataset
  # then, after `hf auth login` with an account in the target org:
  hf upload <org>/AgenticSTS-competitor-captures dist/hf_dataset --repo-type dataset

Privacy note: capture records contain only {seq, ts, latency_ms, request{messages,
model, tools, tool_choice}, response, usage} — no auth headers, no API keys, no
relay hostnames (verified by the release audit 2026-06-11).
"""
from __future__ import annotations

import argparse
import json
import tarfile
from pathlib import Path

CAPTURES = Path(__file__).resolve().parent / "captures"
RUN_PREFIXES = ("competitor-sts2mcp-gemini-A0-a", "competitor-chartyr-gemini-A0-a")

CARD = """---
license: cc-by-4.0
language: [en]
pretty_name: AgenticSTS competitor-baseline captures (STS2MCP, CharTyr)
tags: [llm-agents, game-playing, slay-the-spire-2, agent-trajectories]
---

# AgenticSTS competitor-baseline captures

Raw capture archives for the two open-source accumulating-context Slay the Spire 2
agents (STS2MCP, CharTyr) evaluated as baselines in the AgenticSTS paper: N=5
completed games each, Gemini 3.1 Pro, Ascension 0, The Silent.

Each `<run_id>.tar.zst` (zstd) / `.tar.gz` unpacks to:

| File | Contents |
|---|---|
| `llm_calls.jsonl` | every LLM request/response (full prompts, token usage, latency) |
| `game_io.jsonl`   | per-step game state, chosen action, action result |
| `run_summary.json`| outcome, final floor, act, steps, duration |

`manifest.json` lists per-run outcomes and token totals. Analysis conventions and
aggregate results: `docs/experiments/competitor_comparison/RESULTS.md` in the
[AgenticSTS repository](https://github.com/ShandaAI/AgenticSTS).
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist/hf_dataset")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "README.md").write_text(CARD, encoding="utf-8")

    manifest = []
    runs = [d for d in sorted(CAPTURES.iterdir())
            if d.is_dir() and d.name.startswith(RUN_PREFIXES) and (d / "run_summary.json").exists()]
    for d in runs:
        summary = json.loads((d / "run_summary.json").read_text(encoding="utf-8"))
        arc = out / f"{d.name}.tar.gz"
        with tarfile.open(arc, "w:gz", compresslevel=6) as tf:
            for f in sorted(d.iterdir()):
                tf.add(f, arcname=f"{d.name}/{f.name}")
        manifest.append({"run_id": d.name, "outcome": summary.get("outcome"),
                         "final_floor": summary.get("final_floor"),
                         "steps": summary.get("steps"),
                         "archive": arc.name, "bytes": arc.stat().st_size})
        print(f"packed {arc.name}  ({arc.stat().st_size/1e6:.0f} MB)")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nstaged {len(manifest)} runs -> {out}")
    print("upload:  hf upload <org>/AgenticSTS-competitor-captures", out, "--repo-type dataset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
