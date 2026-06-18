"""Aggregate API cost / token usage across a competitor's runs (Workstream C).

For every capture dir whose run-id starts with a given prefix, sums the
provider-reported token usage (from llm_calls.jsonl) and reports per-run + an
aggregate over the COMPLETED games (victory/defeat) — mean/median tokens/run and
mean $/run. Token counts are exact; the $ uses an estimated per-million rate
(COMPETITOR_PRICE_IN / COMPETITOR_PRICE_OUT env, default 1.25 / 10.0) which should be
calibrated against the relay billing delta. This is the "cost statistic" for the paper.

Usage:
  python -m scripts.competitor_runs.cost_report competitor-sts2mcp-gemini-A0
  python -m scripts.competitor_runs.cost_report competitor-sts2mcp-gemini-A0 competitor-chartyr-gemini-A0
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from pathlib import Path

CAPTURES = Path(__file__).resolve().parent / "captures"
PRICE_IN = float(os.environ.get("COMPETITOR_PRICE_IN", "1.25"))
PRICE_OUT = float(os.environ.get("COMPETITOR_PRICE_OUT", "10.0"))
# Cached prompt tokens are billed at a fraction of fresh input (Gemini implicit caching).
# 75-90% of competitor prompt tokens are cache hits, so pricing everything at PRICE_IN
# would overstate dollar cost severalfold.
PRICE_CACHED = float(os.environ.get("COMPETITOR_PRICE_CACHED", str(PRICE_IN * 0.25)))


def _run_tokens(run_id: str) -> dict | None:
    p = CAPTURES / run_id / "llm_calls.jsonl"
    if not p.exists():
        return None
    ti = to = tot = cached = calls = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
        except json.JSONDecodeError:
            continue
        calls += 1
        u = (c.get("response") or {}).get("usage") or {}
        ti += int(u.get("prompt_tokens", 0) or 0)
        to += int(u.get("completion_tokens", 0) or 0)
        tot += int(u.get("total_tokens", 0) or 0)
        cached += int(((u.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0)
    fresh = ti - cached
    return {
        "run_id": run_id, "calls": calls, "in": ti, "out": to, "total": tot,
        "cached": cached, "fresh": fresh,
        "est_usd": fresh / 1e6 * PRICE_IN + cached / 1e6 * PRICE_CACHED + to / 1e6 * PRICE_OUT,
    }


def _outcome(run_id: str) -> str:
    p = CAPTURES / run_id / "run_summary.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("outcome") or "?"
        except (json.JSONDecodeError, OSError):
            return "?"
    return "?"


def report(prefixes: list[str]) -> None:
    for prefix in prefixes:
        runs = sorted(d.name for d in CAPTURES.iterdir() if d.is_dir() and d.name.startswith(prefix)) if CAPTURES.exists() else []
        print(f"\n===== {prefix}  ({len(runs)} capture dirs) =====")
        print(f"  {'run_id':44} {'outcome':12} {'calls':>5} {'in_tok':>11} {'cached':>11} {'out_tok':>8} {'$est':>7}")
        completed = []
        for rid in runs:
            r = _run_tokens(rid)
            if not r:
                continue
            oc = _outcome(rid)
            print(f"  {rid:44} {oc:12} {r['calls']:>5} {r['in']:>11,} {r['cached']:>11,} {r['out']:>8,} {r['est_usd']:>7.2f}")
            if oc in ("victory", "defeat"):
                completed.append(r)
        if completed:
            totals = [r["total"] for r in completed]
            usd = [r["est_usd"] for r in completed]
            print(
                f"  -- completed games: {len(completed)} | "
                f"mean tokens/run={statistics.mean(totals):,.0f} median={statistics.median(totals):,.0f} | "
                f"mean $/run={statistics.mean(usd):.2f}  total=${sum(usd):.2f}  "
                f"(@ ${PRICE_IN}/M fresh-in, ${PRICE_CACHED}/M cached-in, ${PRICE_OUT}/M out — estimate)"
            )
        else:
            print("  -- no completed (victory/defeat) games yet.")


def main(argv: list[str] | None = None) -> int:
    a = argv if argv is not None else sys.argv[1:]
    if not a:
        print("usage: python -m scripts.competitor_runs.cost_report <run_id_prefix> [...]")
        return 0
    report(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
