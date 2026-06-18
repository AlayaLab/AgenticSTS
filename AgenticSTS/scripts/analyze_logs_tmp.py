#!/usr/bin/env python3
"""Temporary script to analyze STS2 agent log files."""

import json
import statistics
from collections import Counter, defaultdict


def parse_jsonl(filepath):
    events = []
    with open(filepath, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [PARSE ERROR] Line {i}: {e}")
    return events


def analyze_log(filepath, label):
    print(f"\n{'=' * 80}")
    print(f"  LOG: {label}")
    print(f"  File: {filepath}")
    print(f"{'=' * 80}")

    events = parse_jsonl(filepath)
    print(f"\nTotal events: {len(events)}")

    # Event type distribution
    event_types = Counter(e.get("event") for e in events)
    print("\nEvent types:")
    for et, cnt in event_types.most_common():
        print(f"  {et}: {cnt}")

    # Time range
    timestamps = [e["ts"] for e in events if "ts" in e]
    duration = 0
    if timestamps:
        duration = timestamps[-1] - timestamps[0]
        print(f"\nDuration: {duration:.0f}s ({duration / 60:.1f} min)")

    # Floor progression
    floors = [e.get("floor") for e in events if e.get("floor")]
    if floors:
        print(f"Floor range: {min(floors)} - {max(floors)}")

    # HP progression
    hps = [(e.get("floor", "?"), e.get("hp"), e.get("hp_max")) for e in events if e.get("hp")]
    if hps:
        print(f"HP range: {min(h[1] for h in hps)} - {max(h[1] for h in hps)} (max: {hps[0][2]})")

    # Character
    for e in events:
        summary = e.get("summary", "")
        if "Silent" in summary:
            print("Character: The Silent")
            break
        elif "Ironclad" in summary:
            print("Character: Ironclad")
            break
        elif "Defect" in summary:
            print("Character: Defect")
            break
        elif "Regent" in summary:
            print("Character: Regent")
            break
        elif "Necrobinder" in summary:
            print("Character: Necrobinder")
            break

    # =========================================================================
    # 1. WARNINGS AND ERRORS
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("1. WARNINGS AND ERRORS")
    print(f"{'=' * 60}")

    warnings = [e for e in events if e.get("event") == "warning"]
    errors = [e for e in events if e.get("event") == "error"]

    # Also check for error status in action_results
    action_errors = [
        e for e in events if e.get("event") == "action_result" and e.get("status") != "ok"
    ]

    # Check for fallback decisions
    fallback_decisions = [
        e
        for e in events
        if e.get("event") == "decision" and e.get("source") in ("random", "mechanical", "heuristic")
    ]

    # Check for retry attempts
    retry_calls = [e for e in events if e.get("event") == "llm_call" and e.get("attempt", 1) > 1]

    # Check for stuck events
    stuck_events = [e for e in events if "stuck" in str(e.get("event", "")).lower()]

    # LLM errors
    llm_error_calls = [
        e for e in events if e.get("event") == "llm_call" and e.get("stop_reason") == "error"
    ]

    # Decisions with error in reasoning
    error_decisions = [
        e
        for e in events
        if e.get("event") == "decision" and "error" in str(e.get("reasoning", "")).lower()
    ]

    print(f"\nWarning events: {len(warnings)}")
    if warnings:
        warning_msgs = Counter()
        for w in warnings:
            msg = w.get("message", w.get("warning", ""))
            if not msg:
                msg = str({k: v for k, v in w.items() if k not in ("ts", "dt", "run_id")})[:120]
            warning_msgs[msg[:120]] += 1
        for msg, cnt in warning_msgs.most_common(15):
            print(f"  [{cnt}x] {msg}")

    print(f"\nError events: {len(errors)}")
    if errors:
        error_msgs = Counter()
        for e in errors:
            msg = e.get("message", e.get("error", ""))
            if not msg:
                msg = str({k: v for k, v in e.items() if k not in ("ts", "dt", "run_id")})[:120]
            error_msgs[msg[:120]] += 1
        for msg, cnt in error_msgs.most_common(15):
            print(f"  [{cnt}x] {msg}")

    print(f"\nAction errors (non-OK status): {len(action_errors)}")
    if action_errors:
        for ae in action_errors[:10]:
            msg = ae.get("mcp_message", "")[:100]
            print(
                f"  step={ae.get('step')} action={ae.get('action')} "
                f"status={ae.get('status')} msg={msg}"
            )

    print(f"\nLLM retries (attempt > 1): {len(retry_calls)}")
    if retry_calls:
        for rc in retry_calls[:5]:
            step = rc.get("step", "?")
            call_type = rc.get("call_type")
            attempt = rc.get("attempt")
            model = rc.get("model")
            print(
                f"  step={step} type={call_type} attempt={attempt} model={model}"
            )

    print(f"\nFallback decisions (random/mechanical/heuristic): {len(fallback_decisions)}")
    fallback_sources = Counter(d.get("source") for d in fallback_decisions)
    for src, cnt in fallback_sources.most_common():
        print(f"  {src}: {cnt}")
    fallback_states = Counter(d.get("state_type") for d in fallback_decisions)
    for st, cnt in fallback_states.most_common():
        print(f"  -> state_type={st}: {cnt}")

    print(f"\nStuck events: {len(stuck_events)}")
    print(f"LLM error responses: {len(llm_error_calls)}")
    print(f"Decisions with error in reasoning: {len(error_decisions)}")
    if error_decisions:
        for ed in error_decisions[:5]:
            reasoning = ed.get("reasoning", "")[:150]
            print(
                f"  step={ed.get('step')} state={ed.get('state_type')} "
                f"reasoning={reasoning}"
            )

    # =========================================================================
    # 2. V2 FALLBACK FREQUENCY
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("2. V2 FALLBACK FREQUENCY")
    print(f"{'=' * 60}")

    llm_calls = [e for e in events if e.get("event") == "llm_call"]
    decisions = [e for e in events if e.get("event") == "decision"]

    v2_calls = [c for c in llm_calls if "v2" in str(c.get("call_type", "")).lower()]
    non_v2_calls = [c for c in llm_calls if "v2" not in str(c.get("call_type", "")).lower()]

    print(f"\nTotal LLM calls: {len(llm_calls)}")
    print(f"  V2 calls: {len(v2_calls)}")
    print(f"  Non-V2 calls: {len(non_v2_calls)}")

    # Call types
    call_types = Counter(c.get("call_type") for c in llm_calls)
    print("\nLLM call types:")
    for ct, cnt in call_types.most_common():
        print(f"  {ct}: {cnt}")

    # Decision sources
    decision_sources = Counter(d.get("source") for d in decisions)
    print("\nDecision sources:")
    for src, cnt in decision_sources.most_common():
        print(f"  {src}: {cnt}")

    # V2 decisions by state type
    v2_decisions = [d for d in decisions if d.get("source") == "v2"]
    print(f"\nV2 decisions: {len(v2_decisions)}")
    v2_states = Counter(d.get("state_type") for d in v2_decisions)
    for st, cnt in v2_states.most_common():
        print(f"  {st}: {cnt}")

    # Non-LLM decision state types
    non_llm = [
        d
        for d in decisions
        if d.get("source") in ("random", "mechanical", "heuristic", "shortcut", "auto")
    ]
    fallback_state_types = Counter(d.get("state_type") for d in non_llm)
    print(f"\nNon-LLM decisions ({len(non_llm)} total):")
    for st, cnt in fallback_state_types.most_common():
        print(f"  {st}: {cnt}")

    # =========================================================================
    # 3. CACHE PERFORMANCE
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("3. CACHE PERFORMANCE")
    print(f"{'=' * 60}")

    cache_reads = [c.get("cache_read_tokens", 0) for c in llm_calls]
    total_tokens_all = [c.get("tokens", 0) for c in llm_calls]

    cache_nonzero = [c for c in cache_reads if c and c > 0]
    cache_hit_pct = 100 * len(cache_nonzero) / max(1, len(llm_calls))
    print(f"\nTotal LLM calls: {len(llm_calls)}")
    print(f"Calls with cache_read > 0: {len(cache_nonzero)} ({cache_hit_pct:.1f}%)")
    print(f"Calls with cache_read = 0: {len(llm_calls) - len(cache_nonzero)}")

    if cache_nonzero:
        print("\nCache read token distribution (non-zero only):")
        print(f"  Min: {min(cache_nonzero)}")
        print(f"  Max: {max(cache_nonzero)}")
        print(f"  Mean: {statistics.mean(cache_nonzero):.0f}")
        print(f"  Median: {statistics.median(cache_nonzero):.0f}")
        print(f"  Total cached tokens: {sum(cache_nonzero):,}")

    total_input = sum(t for t in total_tokens_all if t)
    total_cached = sum(c for c in cache_reads if c)
    print(f"\nTotal tokens across all calls: {total_input:,}")
    print(f"Total cache_read_tokens: {total_cached:,}")
    if total_input > 0:
        print(f"Cache hit rate (by tokens): {100 * total_cached / total_input:.1f}%")

    # Cache by call type
    cache_by_type = defaultdict(lambda: {"calls": 0, "cached": 0, "total": 0})
    for c in llm_calls:
        ct = c.get("call_type", "unknown")
        cache_by_type[ct]["calls"] += 1
        cache_by_type[ct]["cached"] += c.get("cache_read_tokens", 0) or 0
        cache_by_type[ct]["total"] += c.get("tokens", 0) or 0

    print("\nCache by call type:")
    for ct, d in sorted(cache_by_type.items(), key=lambda x: -x[1]["calls"]):
        pct = 100 * d["cached"] / d["total"] if d["total"] > 0 else 0
        summary = (
            f"  {ct}: {d['calls']} calls, "
            f"{d['cached']:,} cached / {d['total']:,} total ({pct:.1f}%)"
        )
        print(summary)

    # =========================================================================
    # 4. LATENCY ANALYSIS
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("4. LATENCY ANALYSIS")
    print(f"{'=' * 60}")

    latencies_by_call_type = defaultdict(list)
    all_latencies = []

    # Build state_type mapping from step
    state_at_step = {}
    for e in events:
        if e.get("event") == "state" and e.get("step"):
            state_at_step[e["step"]] = e.get("state_type")

    latencies_by_state = defaultdict(list)

    for c in llm_calls:
        lat = c.get("latency_ms", 0)
        if lat and lat > 0:
            ct = c.get("call_type", "unknown")
            step = c.get("step", "?")
            model = c.get("model", "?")
            latencies_by_call_type[ct].append(lat)
            all_latencies.append((lat, ct, model, step))

            if step in state_at_step:
                latencies_by_state[state_at_step[step]].append(lat)

    print(f"\nTotal LLM calls with latency: {len(all_latencies)}")
    if all_latencies:
        lats = [a[0] for a in all_latencies]
        overall_mean_s = statistics.mean(lats) / 1000
        overall_median_ms = statistics.median(lats)
        overall_median_s = overall_median_ms / 1000
        print(
            f"  Overall mean: {statistics.mean(lats):.0f}ms ({overall_mean_s:.1f}s)"
        )
        print(f"  Overall median: {overall_median_ms:.0f}ms ({overall_median_s:.1f}s)")
        print(f"  Min: {min(lats):.0f}ms")
        print(f"  Max: {max(lats):.0f}ms")
        print(f"  Total LLM time: {sum(lats) / 1000:.0f}s ({sum(lats) / 60000:.1f}min)")

    print("\nLatency by call type:")
    for ct, lats in sorted(latencies_by_call_type.items(), key=lambda x: -statistics.mean(x[1])):
        print(f"  {ct} ({len(lats)} calls):")
        print(f"    Mean: {statistics.mean(lats):.0f}ms ({statistics.mean(lats) / 1000:.1f}s)")
        print(f"    Median: {statistics.median(lats):.0f}ms")
        print(f"    Min/Max: {min(lats):.0f} / {max(lats):.0f}ms")

    if latencies_by_state:
        print("\nLatency by state type:")
        for st, lats in sorted(latencies_by_state.items(), key=lambda x: -statistics.mean(x[1])):
            print(f"  {st} ({len(lats)} calls):")
            print(f"    Mean: {statistics.mean(lats):.0f}ms ({statistics.mean(lats) / 1000:.1f}s)")
            print(f"    Median: {statistics.median(lats):.0f}ms")
            print(f"    Min/Max: {min(lats):.0f} / {max(lats):.0f}ms")

    # Top 10 slowest calls
    all_latencies.sort(key=lambda x: -x[0])
    print("\nTop 10 slowest LLM calls:")
    for lat, ct, model, step in all_latencies[:10]:
        st = state_at_step.get(step, "?")
        print(f"  {lat:.0f}ms ({lat / 1000:.1f}s) - {ct} [{model}] step={step} state={st}")

    # =========================================================================
    # 5. MODEL ROUTING
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("5. MODEL ROUTING")
    print(f"{'=' * 60}")

    model_usage = Counter(c.get("model") for c in llm_calls)
    print("\nModel usage:")
    for m, cnt in model_usage.most_common():
        print(f"  {m}: {cnt} calls")

    # Tier usage
    tier_usage = Counter(c.get("tier") for c in llm_calls)
    print("\nTier usage:")
    for t, cnt in tier_usage.most_common():
        print(f"  {t}: {cnt} calls")

    # Model by state type
    model_by_state = defaultdict(Counter)
    tier_by_state = defaultdict(Counter)
    for c in llm_calls:
        step = c.get("step")
        if step and step in state_at_step:
            st = state_at_step[step]
            model_by_state[st][c.get("model", "unknown")] += 1
            tier_by_state[st][c.get("tier", "unknown")] += 1

    print("\nModel x Tier by state type:")
    for st in sorted(model_by_state.keys()):
        print(f"  {st}:")
        for m, cnt in model_by_state[st].most_common():
            # Find tier for this model+state combo
            print(f"    {m}: {cnt} calls")
        for t, cnt in tier_by_state[st].most_common():
            print(f"    tier={t}: {cnt}")

    # Think budget distribution
    think_budgets = [c.get("think_budget", 0) for c in llm_calls if c.get("think_budget")]
    if think_budgets:
        print("\nThink budget distribution:")
        budget_dist = Counter(think_budgets)
        for b, cnt in sorted(budget_dist.items()):
            print(f"  budget={b}: {cnt} calls")

    # =========================================================================
    # 6. TOKEN COST
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("6. TOKEN COST ESTIMATE")
    print(f"{'=' * 60}")

    tokens_by_model = defaultdict(
        lambda: {"input": 0, "output": 0, "cache": 0, "calls": 0, "thinking": 0}
    )

    for c in llm_calls:
        model = c.get("model", "unknown")
        total_tok = c.get("tokens", 0) or 0
        cache_tok = c.get("cache_read_tokens", 0) or 0
        input_tok = c.get("input_tokens", 0) or 0
        output_tok = c.get("output_tokens", 0) or 0
        thinking_tok = c.get("thinking_tokens", 0) or 0

        if input_tok == 0 and output_tok == 0 and total_tok > 0:
            # Estimate split based on thinking presence
            thinking_text = c.get("thinking_text", "")
            if thinking_text:
                # Rough: 4 chars per token
                est_thinking = len(thinking_text) // 4
                est_response = len(str(c.get("response", ""))) // 4
                output_tok = est_thinking + est_response + 200  # tool use overhead
                input_tok = max(0, total_tok - output_tok)
            else:
                input_tok = int(total_tok * 0.85)
                output_tok = total_tok - input_tok

        tokens_by_model[model]["input"] += input_tok
        tokens_by_model[model]["output"] += output_tok
        tokens_by_model[model]["cache"] += cache_tok
        tokens_by_model[model]["calls"] += 1
        tokens_by_model[model]["thinking"] += thinking_tok

    grand_input = sum(d["input"] for d in tokens_by_model.values())
    grand_output = sum(d["output"] for d in tokens_by_model.values())
    grand_cache = sum(d["cache"] for d in tokens_by_model.values())

    print("\nTotal tokens (estimated):")
    print(f"  Input: {grand_input:,}")
    print(f"  Output: {grand_output:,}")
    print(f"  Cache read: {grand_cache:,}")
    print(f"  Grand total: {grand_input + grand_output:,}")

    total_cost = 0
    print("\nCost by model:")
    for model, d in sorted(tokens_by_model.items(), key=lambda x: -x[1]["calls"]):
        if "opus" in model.lower():
            inp_rate, cache_rate, out_rate = 15.0, 1.5, 75.0
        elif "sonnet" in model.lower():
            inp_rate, cache_rate, out_rate = 3.0, 0.3, 15.0
        elif "haiku" in model.lower():
            inp_rate, cache_rate, out_rate = 1.0, 0.1, 5.0
        else:
            inp_rate, cache_rate, out_rate = 3.0, 0.3, 15.0

        non_cached = max(0, d["input"] - d["cache"])
        cost_input = (non_cached / 1_000_000) * inp_rate
        cost_cache = (d["cache"] / 1_000_000) * cache_rate
        cost_output = (d["output"] / 1_000_000) * out_rate
        cost = cost_input + cost_cache + cost_output
        total_cost += cost

        print(f"  {model}: {d['calls']} calls")
        print(f"    Input: {d['input']:,} (non-cached: {non_cached:,}, cached: {d['cache']:,})")
        print(f"    Output: {d['output']:,}")
        print(
            f"    Cost: ${cost:.4f} "
            f"(in: ${cost_input:.4f}, cache: ${cost_cache:.4f}, out: ${cost_output:.4f})"
        )

    print(f"\n  >>> TOTAL ESTIMATED COST: ${total_cost:.4f}")
    per_minute = total_cost / (duration / 60) if duration > 60 else 0
    print(f"  >>> Cost per minute: ${per_minute:.4f}")

    # =========================================================================
    # 7. STUCK LOOPS
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("7. STUCK LOOP DETECTION")
    print(f"{'=' * 60}")

    state_sequence = []
    for e in events:
        if e.get("event") == "state":
            state_sequence.append(
                {
                    "step": e.get("step"),
                    "state_type": e.get("state_type"),
                    "floor": e.get("floor"),
                    "hp": e.get("hp"),
                    "summary": e.get("summary", "")[:100],
                }
            )

    if state_sequence:
        # Find runs of same state_type + floor
        runs = []
        current_run = [state_sequence[0]]
        for s in state_sequence[1:]:
            if (
                s["state_type"] == current_run[-1]["state_type"]
                and s["floor"] == current_run[-1]["floor"]
            ):
                current_run.append(s)
            else:
                if len(current_run) > 3:
                    runs.append(list(current_run))
                current_run = [s]
        if len(current_run) > 3:
            runs.append(list(current_run))

        # Filter: combat states with >3 at same floor are normal (multiple rounds)
        # Only flag non-combat with >3, or combat with >20
        flagged = []
        for run in runs:
            st = run[0]["state_type"]
            ln = len(run)
            if st == "monster" and ln > 20:
                flagged.append(run)
            elif st != "monster" and ln > 3:
                flagged.append(run)

        if flagged:
            print(f"\nPotentially stuck sequences ({len(flagged)} found):")
            for run in flagged:
                start_step = run[0]["step"]
                end_step = run[-1]["step"]
                print(
                    f"  {run[0]['state_type']} @ F{run[0]['floor']}: "
                    f"{len(run)} consecutive states (steps {start_step}-{end_step})"
                )
                print(f"    HP: {run[0]['hp']} -> {run[-1]['hp']}")
        else:
            print("\nNo stuck loops detected")
            print(
                "  (Longest combat at single floor: "
                f"{max((len(r) for r in runs if r[0]['state_type'] == 'monster'), default=0)} "
                "rounds)"
            )
            non_combat_runs = [r for r in runs if r[0]["state_type"] != "monster"]
            if non_combat_runs:
                longest_nc = max(non_combat_runs, key=len)
                print(
                    "  (Longest non-combat repeat: "
                    f"{len(longest_nc)}x {longest_nc[0]['state_type']} "
                    f"@ F{longest_nc[0]['floor']})"
                )
    else:
        print("  No state events found")

    # =========================================================================
    # 8. QUERY TOOL USAGE
    # =========================================================================
    print(f"\n{'=' * 60}")
    print("8. QUERY TOOL USAGE")
    print(f"{'=' * 60}")

    tool_events = [e for e in events if e.get("event") in ("tool_use", "tool_call", "tool_result")]

    # Check stop_reason for tool_use
    stop_reasons = Counter(c.get("stop_reason") for c in llm_calls)
    print("\nLLM call stop reasons:")
    for sr, cnt in stop_reasons.most_common():
        print(f"  {sr}: {cnt}")

    tool_use_calls = sum(1 for c in llm_calls if c.get("stop_reason") == "tool_use")
    end_turn_calls = sum(1 for c in llm_calls if c.get("stop_reason") == "end_turn")
    tool_use_pct = 100 * tool_use_calls / max(1, len(llm_calls))

    print(f"\nTool use stop: {tool_use_calls} calls ({tool_use_pct:.1f}% of LLM calls)")
    print(f"End turn stop: {end_turn_calls} calls")

    # Scan for query tool names in all event fields
    query_tools = [
        "lookup_card",
        "lookup_enemy",
        "lookup_potion",
        "recall_encounter",
        "get_deck_analysis",
        "get_run_progress",
        "search_strategy",
        "read_guide",
    ]

    tool_mentions = Counter()
    for e in events:
        text = json.dumps(e, ensure_ascii=False)
        for tool in query_tools:
            if tool in text:
                tool_mentions[tool] += 1

    print("\nQuery tool mentions (across all event fields):")
    if tool_mentions:
        for tool, cnt in tool_mentions.most_common():
            print(f"  {tool}: {cnt} mentions")
    else:
        print("  No query tool mentions found")

    # Check for tool_call events specifically
    print(f"\nTool-specific events: {len(tool_events)}")
    if tool_events:
        for te in tool_events[:10]:
            payload = str(
                {k: v for k, v in te.items() if k not in ("ts", "dt", "run_id")}
            )[:120]
            print(
                f"  {te.get('event')}: {payload}"
            )

    # Check for V2 agent loop calls with tool interactions
    v2_agent_calls = [c for c in llm_calls if c.get("call_type") == "v2_agent_loop"]
    print(f"\nV2 agent loop calls: {len(v2_agent_calls)}")
    if v2_agent_calls:
        # Check how many had tool_use as stop reason
        v2_tool_use = sum(1 for c in v2_agent_calls if c.get("stop_reason") == "tool_use")
        v2_end_turn = sum(1 for c in v2_agent_calls if c.get("stop_reason") == "end_turn")
        print(f"  With tool_use stop: {v2_tool_use}")
        print(f"  With end_turn stop: {v2_end_turn}")

    # Run outcome
    print(f"\n{'=' * 60}")
    print("RUN OUTCOME")
    print(f"{'=' * 60}")

    # Check for game_over or run_end
    outcomes = [e for e in events if e.get("event") in ("run_end", "game_over", "death", "victory")]
    if outcomes:
        for o in outcomes:
            payload = str({k: v for k, v in o.items() if k not in ("ts", "dt")})[:200]
            print(
                f"  {o.get('event')}: {payload}"
            )
    else:
        # Check last few events
        last_states = [e for e in events[-10:] if e.get("event") == "state"]
        if last_states:
            ls = last_states[-1]
            print(f"  Last state: {ls.get('summary', '')[:100]}")
            print(f"  Floor: {ls.get('floor')}, HP: {ls.get('hp')}/{ls.get('hp_max')}")

    return {
        "events": len(events),
        "llm_calls": len(llm_calls),
        "decisions": len(decisions),
        "duration_s": duration,
        "total_cost": total_cost,
        "total_tokens": grand_input + grand_output,
        "cache_hit_pct": 100 * grand_cache / grand_input if grand_input > 0 else 0,
    }


# Main
# dev script — log paths resolved relative to repo root via __file__.
from pathlib import Path as _Path  # noqa: E402
_LOG_DIR = _Path(__file__).resolve().parents[1] / "logs"
files = [
    (str(_LOG_DIR / "run_3055a1e4d209.jsonl"), "Main Run (834 events)"),
    (str(_LOG_DIR / "run_002c637c3692.jsonl"), "Short Run (189 events)"),
]

summaries = []
for filepath, label in files:
    s = analyze_log(filepath, label)
    summaries.append((label, s))

print(f"\n{'=' * 80}")
print("  CROSS-LOG COMPARISON SUMMARY")
print(f"{'=' * 80}")
print(f"\n{'Metric':<25} {'Main Run':>15} {'Short Run':>15}")
print(f"{'-' * 55}")
for key in [
    "events",
    "llm_calls",
    "decisions",
    "duration_s",
    "total_tokens",
    "cache_hit_pct",
    "total_cost",
]:
    v1 = summaries[0][1][key]
    v2 = summaries[1][1][key]
    if key == "duration_s":
        print(f"{key:<25} {v1:>12.0f}s {v2:>12.0f}s")
    elif key == "total_cost":
        print(f"{key:<25} ${v1:>13.4f} ${v2:>13.4f}")
    elif key == "cache_hit_pct":
        print(f"{key:<25} {v1:>14.1f}% {v2:>14.1f}%")
    elif key == "total_tokens":
        print(f"{key:<25} {v1:>15,} {v2:>15,}")
    else:
        print(f"{key:<25} {v1:>15} {v2:>15}")
