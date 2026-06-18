"""Analyze gameplay wall-clock time outside LLM request time.

Works with old logs by deriving timings from existing events, and uses the new
``perf`` events when present for a much cleaner breakdown.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict, deque
from pathlib import Path


LOG_DIR = Path("logs")
LLM_EVENTS = {"llm_request_start", "llm_request_end"}


def _load_events(path: Path) -> list[dict]:
    events: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _pair_llm_spans(events: list[dict], *, gameplay_end_ts: float) -> list[dict]:
    pending: deque[dict] = deque()
    spans: list[dict] = []
    for event in events:
        ts = event.get("ts")
        if not isinstance(ts, (int, float)) or ts > gameplay_end_ts + 1e-6:
            continue
        if event.get("event") == "llm_request_start":
            pending.append(event)
            continue
        if event.get("event") == "llm_request_end" and pending:
            start = pending.popleft()
            spans.append(
                {
                    "start_ts": start["ts"],
                    "end_ts": ts,
                    "duration_s": max(0.0, ts - start["ts"]),
                    "call_type": event.get("call_type") or start.get("call_type") or "",
                    "state_type": event.get("state_type") or start.get("state_type") or "",
                    "status": event.get("status") or "",
                }
            )
    return spans


def _sum_llm_overlap(spans: list[dict], start_ts: float, end_ts: float) -> float:
    total = 0.0
    for span in spans:
        span_start = span["start_ts"]
        span_end = span["end_ts"]
        if span_end <= start_ts or span_start >= end_ts:
            continue
        total += max(0.0, min(end_ts, span_end) - max(start_ts, span_start))
    return total


def _decision_events(events: list[dict], *, gameplay_end_ts: float) -> list[dict]:
    return [
        event
        for event in events
        if event.get("event") == "decision"
        and isinstance(event.get("ts"), (int, float))
        and event["ts"] <= gameplay_end_ts + 1e-6
    ]


def _print_perf_breakdown(events: list[dict], *, gameplay_end_ts: float) -> None:
    perf_events = [
        event
        for event in events
        if event.get("event") == "perf"
        and isinstance(event.get("duration_ms"), (int, float))
        and isinstance(event.get("ts"), (int, float))
        and event["ts"] <= gameplay_end_ts + 1e-6
    ]
    if not perf_events:
        print("No recorded perf events in this log.")
        return

    totals: defaultdict[str, float] = defaultdict(float)
    counts: Counter[str] = Counter()
    for event in perf_events:
        stage = str(event.get("stage") or "")
        totals[stage] += float(event["duration_ms"]) / 1000.0
        counts[stage] += 1

    print("\nPerf stages:")
    for stage, total_s in sorted(totals.items(), key=lambda item: -item[1])[:15]:
        avg_ms = (total_s * 1000.0) / max(1, counts[stage])
        print(f"  {stage:<28} total={total_s:>7.1f}s  count={counts[stage]:>4d}  avg={avg_ms:>7.1f}ms")


def _print_derived_breakdown(events: list[dict], *, gameplay_end_ts: float) -> None:
    spans = _pair_llm_spans(events, gameplay_end_ts=gameplay_end_ts)
    decisions = _decision_events(events, gameplay_end_ts=gameplay_end_ts)
    if len(decisions) < 2:
        print("Not enough decision events for derived breakdown.")
        return

    non_llm_by_action: defaultdict[str, float] = defaultdict(float)
    counts_by_action: Counter[str] = Counter()
    for current, nxt in zip(decisions, decisions[1:]):
        action = ""
        if isinstance(current.get("action"), dict):
            action = str(current["action"].get("action") or "")
        start_ts = float(current["ts"])
        end_ts = float(nxt["ts"])
        llm_s = _sum_llm_overlap(spans, start_ts, end_ts)
        non_llm_s = max(0.0, end_ts - start_ts - llm_s)
        non_llm_by_action[action] += non_llm_s
        counts_by_action[action] += 1

    print("\nDerived non-LLM gaps by action:")
    for action, total_s in sorted(non_llm_by_action.items(), key=lambda item: -item[1])[:15]:
        avg_s = total_s / max(1, counts_by_action[action])
        print(f"  {action or '<unknown>':<28} total={total_s:>7.1f}s  count={counts_by_action[action]:>4d}  avg={avg_s:>6.2f}s")

    by_step: defaultdict[int, list[dict]] = defaultdict(list)
    for event in events:
        step = event.get("step")
        if (
            isinstance(step, int)
            and isinstance(event.get("ts"), (int, float))
            and event["ts"] <= gameplay_end_ts + 1e-6
        ):
            by_step[step].append(event)

    waits: defaultdict[str, list[float]] = defaultdict(list)
    for step, items in by_step.items():
        action_result = next((event for event in items if event.get("event") == "action_result"), None)
        decision = next((event for event in items if event.get("event") == "decision"), None)
        if action_result is None or decision is None:
            continue
        if not isinstance(action_result.get("ts"), (int, float)) or not isinstance(decision.get("ts"), (int, float)):
            continue
        if not isinstance(action_result.get("action"), str):
            continue
        waits[action_result["action"]].append(max(0.0, decision["ts"] - action_result["ts"]))

    print("\nAction-result -> decision waits:")
    for action, values in sorted(waits.items(), key=lambda item: -sum(item[1]))[:10]:
        total_s = sum(values)
        avg_s = total_s / max(1, len(values))
        print(f"  {action:<28} total={total_s:>7.1f}s  count={len(values):>4d}  avg={avg_s:>6.2f}s")


def _summarize(path: Path) -> None:
    events = _load_events(path)
    if not events:
        print(f"\n== {path.name} ==\nNo events.")
        return

    run_start_ts = events[0].get("ts")
    if not isinstance(run_start_ts, (int, float)):
        print(f"\n== {path.name} ==\nMissing run_start timestamp.")
        return

    run_end = next((event for event in events if event.get("event") == "run_end"), None)
    post_run_start = next((event for event in events if event.get("event") == "post_run_start"), None)
    post_run_end = next((event for event in events if event.get("event") == "post_run_end"), None)
    last_ts = next(
        (
            event["ts"]
            for event in reversed(events)
            if isinstance(event.get("ts"), (int, float))
        ),
        run_start_ts,
    )

    gameplay_end_ts = (
        float(run_end["ts"])
        if isinstance(run_end, dict) and isinstance(run_end.get("ts"), (int, float))
        else float(post_run_start["ts"])
        if isinstance(post_run_start, dict) and isinstance(post_run_start.get("ts"), (int, float))
        else float(last_ts)
    )
    gameplay_s = max(0.0, gameplay_end_ts - float(run_start_ts))

    llm_spans = _pair_llm_spans(events, gameplay_end_ts=gameplay_end_ts)
    llm_wall_s = sum(span["duration_s"] for span in llm_spans)
    llm_errors = sum(1 for span in llm_spans if span.get("status") != "ok")

    postrun_start_ts = (
        float(post_run_start["ts"])
        if isinstance(post_run_start, dict) and isinstance(post_run_start.get("ts"), (int, float))
        else None
    )
    postrun_end_ts = (
        float(post_run_end["ts"])
        if isinstance(post_run_end, dict) and isinstance(post_run_end.get("ts"), (int, float))
        else float(last_ts)
        if postrun_start_ts is not None
        else None
    )
    postrun_s = (
        max(0.0, postrun_end_ts - postrun_start_ts)
        if postrun_start_ts is not None and postrun_end_ts is not None
        else 0.0
    )

    print(f"\n== {path.name} ==")
    print(
        "Gameplay: "
        f"{gameplay_s:.1f}s total | {llm_wall_s:.1f}s LLM wall-clock | "
        f"{max(0.0, gameplay_s - llm_wall_s):.1f}s non-LLM"
    )
    print(
        "LLM reqs: "
        f"{len(llm_spans)} total | {llm_errors} non-ok | "
        f"run_end_floor={run_end.get('floor') if isinstance(run_end, dict) else '?'}"
    )
    if postrun_s > 0:
        print(f"Post-run span: {postrun_s:.1f}s")

    _print_perf_breakdown(events, gameplay_end_ts=gameplay_end_ts)
    _print_derived_breakdown(events, gameplay_end_ts=gameplay_end_ts)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="Specific log file to analyze.")
    parser.add_argument("--latest", type=int, default=1, help="Analyze the latest N logs.")
    args = parser.parse_args()

    if args.file:
        paths = [Path(args.file)]
    else:
        paths = sorted(LOG_DIR.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[: args.latest]

    if not paths:
        raise SystemExit("No run logs found.")

    for path in paths:
        _summarize(path)


if __name__ == "__main__":
    main()
