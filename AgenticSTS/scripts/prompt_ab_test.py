"""B1 prompt reorder A/B test driver.

Usage:
    python -m scripts.prompt_ab_test --n 30 --logs-glob 'logs/run_*.jsonl'
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import logging
import random
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from scripts._prompt_ab.decision import parse_card_reward_decision
from scripts._prompt_ab.judge import judge_pair
from scripts._prompt_ab.report import SampleResult, summarize, write_report
from scripts._prompt_ab.runner import resample_pair
from scripts._prompt_ab.sampler import iter_card_reward_calls
from scripts._prompt_ab.transform import apply_b1


logger = logging.getLogger(__name__)


def _act_for(sample) -> str:
    m = sample.user_message
    for marker in ("Act: 1 |", "Act: 2 |", "Act: 3 |"):
        if marker in m:
            return marker[5]
    return "?"


def _stratify_by_act(samples: list, n: int, seed: int) -> list:
    """Sort samples into per-act buckets, then round-robin sample up to n."""
    rng = random.Random(seed)

    buckets: dict[str, list] = {"1": [], "2": [], "3": [], "?": []}
    for s in samples:
        buckets[_act_for(s)].append(s)
    for v in buckets.values():
        rng.shuffle(v)

    out: list = []
    while len(out) < n:
        added = 0
        for act in ("1", "2", "3", "?"):
            if buckets[act] and len(out) < n:
                out.append(buckets[act].pop())
                added += 1
        if added == 0:
            break
    return out


async def _run(args: argparse.Namespace) -> int:
    logs = sorted(Path().glob(args.logs_glob))
    if not logs:
        print(f"no logs match {args.logs_glob}")
        return 2

    all_samples = list(iter_card_reward_calls(logs, min_prompt_len=args.min_prompt_len))
    print(f"found {len(all_samples)} card_reward calls in {len(logs)} log files", flush=True)
    if not all_samples:
        return 2

    selected = _stratify_by_act(all_samples, args.n, seed=args.seed)
    act_dist = Counter(_act_for(s) for s in selected)
    print(f"selected {len(selected)} samples (act distribution: {dict(act_dist)})", flush=True)

    # Per-sample checkpoint file: lets us inspect partial results during a long
    # run without waiting for the final report. Written after every sample.
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("data/reports/prompt_ab")
    out_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = out_dir / f"prompt_ab_b1_{timestamp}.partial.json"
    print(f"checkpoint: {checkpoint_path}", flush=True)

    results: list[SampleResult] = []
    for idx, s in enumerate(selected, 1):
        try:
            user_b = apply_b1(s.user_message)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{idx}/{len(selected)}] transform failed: {exc} — skipping")
            continue

        # Resample model: explicit override beats whatever was recorded in the
        # JSONL (older logs may carry fallback-drift models like qwen that
        # a relay_gemini doesn't host).
        resample_model = args.gameplay_model or s.model
        a_results, b_results = await resample_pair(
            system_prompt=s.system_prompt,
            user_a=s.user_message,
            user_b=user_b,
            model=resample_model,
            samples_per_version=args.samples_per_version,
            concurrency=args.concurrency,
        )

        a_decisions = [parse_card_reward_decision(r.response_text) for r in a_results]
        b_decisions = [parse_card_reward_decision(r.response_text) for r in b_results]
        a_indices = [d.option_index for d in a_decisions]
        b_indices = [d.option_index for d in b_decisions]
        a_malformed = sum(1 for d in a_decisions if d.malformed)
        b_malformed = sum(1 for d in b_decisions if d.malformed)

        sr = SampleResult(
            run_id=s.run_id,
            log_path=s.log_path,
            line_index=s.line_index,
            a_decisions=a_indices,
            b_decisions=b_indices,
            a_malformed=a_malformed,
            b_malformed=b_malformed,
        )

        if a_results[0].response_text and b_results[0].response_text:
            verdict = await judge_pair(
                user_message=s.user_message,
                response_a=a_results[0].response_text,
                response_b=b_results[0].response_text,
                seed=args.seed + idx,
            )
            sr.judge_winner = verdict.winner
            sr.judge_score_a_total = sum(int(v) for v in verdict.score_a.values())
            sr.judge_score_b_total = sum(int(v) for v in verdict.score_b.values())
            sr.judge_rationale = verdict.rationale

        results.append(sr)
        print(
            f"  [{idx}/{len(selected)}] A={a_indices} B={b_indices} "
            f"malformed=A{a_malformed}/B{b_malformed} judge={sr.judge_winner or '-'}",
            flush=True,
        )

        # Checkpoint: rewrite partial JSON after every sample
        partial_summary = summarize(results)
        checkpoint_path.write_text(
            json.dumps(
                {
                    "summary": asdict(partial_summary),
                    "samples": [asdict(r) for r in results],
                    "completed": idx,
                    "total": len(selected),
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    summary = summarize(results)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("data/reports/prompt_ab")
    json_path, md_path = write_report(
        out_dir=out_dir, samples=results, summary=summary, timestamp=timestamp
    )

    print()
    print(f"VERDICT: {summary.pass_verdict}")
    print(f"  disagreements: {summary.n_disagreements}/{summary.n_samples}")
    print(
        f"  judge wins — A: {summary.judge_a_wins}, "
        f"B: {summary.judge_b_wins}, tie: {summary.judge_ties}"
    )
    print(
        f"  mean score — A: {summary.judge_a_mean_total:.2f}, "
        f"B: {summary.judge_b_mean_total:.2f}"
    )
    print(
        f"  malformed — A: {summary.a_malformed_rate:.2%}, "
        f"B: {summary.b_malformed_rate:.2%}"
    )
    for n in summary.notes:
        print(f"  - {n}")
    print()
    print(f"json: {json_path}")
    print(f"md:   {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="B1 prompt reorder A/B test")
    p.add_argument("--n", type=int, default=30, help="number of samples (default 30)")
    p.add_argument("--logs-glob", default="logs/run_*.jsonl")
    p.add_argument("--min-prompt-len", type=int, default=5000)
    p.add_argument("--samples-per-version", type=int, default=3)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--gameplay-model",
        default="gemini-3.1-pro-preview",
        help="Override the model used for A/B resampling. Default keeps every "
             "sample on gemini-3.1-pro-preview via STS2_a relay_GEMINI_*. "
             "Pass empty string to honour the model recorded in each JSONL.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
