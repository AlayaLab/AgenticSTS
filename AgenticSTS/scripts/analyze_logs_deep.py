#!/usr/bin/env python3
"""Deeper analysis of llm_calls, retries, and query-tool usage."""

import json
import statistics
from collections import Counter, defaultdict


def parse_jsonl(filepath):
    events = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def analyze_deep(filepath, label):
    print(f"\n{'=' * 80}")
    print(f"  DEEP ANALYSIS: {label}")
    print(f"{'=' * 80}")

    events = parse_jsonl(filepath)

    llm_calls = [e for e in events if e.get("event") == "llm_call"]
    decisions = [e for e in events if e.get("event") == "decision"]

    # =========================================================================
    # A. MAP LLM CALLS TO STATE TYPE VIA TIMESTAMPS
    # =========================================================================
    print("\n--- LLM Call to State Type Mapping (via nearest prior state event) ---")

    # For each llm_call, find the nearest state event before it
    state_timeline = []
    for e in events:
        if e.get("event") == "state":
            state_timeline.append((e["ts"], e.get("state_type"), e.get("floor"), e.get("step")))

    llm_state_map = []
    for c in llm_calls:
        ts = c["ts"]
        # Find nearest state event before this timestamp
        best = None
        for st_ts, st_type, st_floor, st_step in state_timeline:
            if st_ts <= ts:
                best = (st_type, st_floor, st_step)
            else:
                break
        if best:
            llm_state_map.append(
                {
                    "state_type": best[0],
                    "floor": best[1],
                    "step": best[2],
                    "model": c.get("model"),
                    "tier": c.get("tier"),
                    "latency_ms": c.get("latency_ms", 0),
                    "tokens": c.get("tokens", 0),
                    "cache_read": c.get("cache_read_tokens", 0),
                    "think_budget": c.get("think_budget", 0),
                    "attempt": c.get("attempt", 1),
                    "stop_reason": c.get("stop_reason", ""),
                    "call_type": c.get("call_type", ""),
                }
            )

    # Latency by state type
    lat_by_state = defaultdict(list)
    for m in llm_state_map:
        if m["latency_ms"] and m["latency_ms"] > 0:
            lat_by_state[m["state_type"]].append(m["latency_ms"])

    print("\nLatency by state type (via timestamp correlation):")
    for st, lats in sorted(lat_by_state.items(), key=lambda x: -statistics.mean(x[1])):
        print(f"  {st} ({len(lats)} calls):")
        print(f"    Mean: {statistics.mean(lats):.0f}ms ({statistics.mean(lats) / 1000:.1f}s)")
        print(
            f"    Median: {statistics.median(lats):.0f}ms ({statistics.median(lats) / 1000:.1f}s)"
        )
        print(f"    Min/Max: {min(lats):.0f} / {max(lats):.0f}ms")
        print(f"    Total: {sum(lats) / 1000:.0f}s ({sum(lats) / 60000:.1f}min)")

    # Model by state type
    model_by_state = defaultdict(Counter)
    tier_by_state = defaultdict(Counter)
    for m in llm_state_map:
        model_by_state[m["state_type"]][m["model"]] += 1
        tier_by_state[m["state_type"]][m["tier"]] += 1

    print("\nModel routing by state type:")
    for st in sorted(model_by_state.keys()):
        print(f"  {st}:")
        for model, cnt in model_by_state[st].most_common():
            tier = "?"
            for m in llm_state_map:
                if m["state_type"] == st and m["model"] == model:
                    tier = m["tier"]
                    break
            print(f"    {model} (tier={tier}): {cnt} calls")

    # Think budget by state type
    think_by_state = defaultdict(Counter)
    for m in llm_state_map:
        think_by_state[m["state_type"]][m["think_budget"]] += 1

    print("\nThink budget by state type:")
    for st in sorted(think_by_state.keys()):
        print(f"  {st}: {dict(think_by_state[st])}")

    # =========================================================================
    # B. RETRY ANALYSIS
    # =========================================================================
    print("\n--- Retry Analysis ---")

    retries_by_state = defaultdict(list)
    for m in llm_state_map:
        if m["attempt"] > 1:
            retries_by_state[m["state_type"]].append(m["attempt"])

    total_retries = sum(len(v) for v in retries_by_state.values())
    print(f"\nTotal retry calls: {total_retries}")
    for st, attempts in sorted(retries_by_state.items(), key=lambda x: -len(x[1])):
        print(f"  {st}: {len(attempts)} retries, max attempt: {max(attempts)}")
        attempt_dist = Counter(attempts)
        for a, cnt in sorted(attempt_dist.items()):
            print(f"    attempt={a}: {cnt}")

    # What model were retries on?
    retry_models = Counter()
    for m in llm_state_map:
        if m["attempt"] > 1:
            retry_models[m["model"]] += 1
    print(f"\nRetries by model: {dict(retry_models)}")

    # =========================================================================
    # C. DECISION SOURCE BY STATE TYPE
    # =========================================================================
    print("\n--- Decision Source by State Type ---")

    src_by_state = defaultdict(Counter)
    for d in decisions:
        src_by_state[d.get("state_type", "?")][d.get("source", "?")] += 1

    for st in sorted(src_by_state.keys()):
        total = sum(src_by_state[st].values())
        print(f"  {st} ({total} decisions):")
        for src, cnt in src_by_state[st].most_common():
            pct = 100 * cnt / total
            print(f"    {src}: {cnt} ({pct:.0f}%)")

    # =========================================================================
    # D. COMBAT SUMMARIES
    # =========================================================================
    print("\n--- Combat Summaries ---")

    combat_summaries = [e for e in events if e.get("event") == "combat_summary"]
    for cs in combat_summaries:
        # Print key fields
        summary_data = {k: v for k, v in cs.items() if k not in ("ts", "dt", "run_id", "event")}
        print(f"  Floor {summary_data.get('floor', '?')}:")
        for k, v in summary_data.items():
            if k == "floor":
                continue
            val_str = str(v)
            if len(val_str) > 150:
                val_str = val_str[:150] + "..."
            print(f"    {k}: {val_str}")

    # =========================================================================
    # E. QUERY TOOL DEEP DIVE
    # =========================================================================
    print("\n--- Query Tool Deep Dive ---")

    # Scan llm_call prompts and responses for tool references
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

    # Check response field and thinking_text field
    tool_in_response = Counter()
    tool_in_thinking = Counter()
    tool_in_prompt = Counter()

    for c in llm_calls:
        response = str(c.get("response", ""))
        thinking = str(c.get("thinking_text", ""))
        prompt = str(c.get("prompt", ""))

        for tool in query_tools:
            if tool in response:
                tool_in_response[tool] += 1
            if tool in thinking:
                tool_in_thinking[tool] += 1
            if tool in prompt:
                tool_in_prompt[tool] += 1

    print("\nQuery tools in LLM response text:")
    for tool, cnt in tool_in_response.most_common():
        print(f"  {tool}: {cnt}")

    print("\nQuery tools in thinking text:")
    for tool, cnt in tool_in_thinking.most_common():
        print(f"  {tool}: {cnt}")

    print("\nQuery tools in prompt text:")
    for tool, cnt in tool_in_prompt.most_common():
        print(f"  {tool}: {cnt}")

    # =========================================================================
    # F. STOP REASON ANALYSIS
    # =========================================================================
    print("\n--- Stop Reason by State Type ---")

    stop_by_state = defaultdict(Counter)
    for m in llm_state_map:
        stop_by_state[m["state_type"]][m["stop_reason"]] += 1

    for st in sorted(stop_by_state.keys()):
        print(f"  {st}: {dict(stop_by_state[st])}")

    # =========================================================================
    # G. CACHE HIT BY STATE TYPE
    # =========================================================================
    print("\n--- Cache Performance by State Type ---")

    cache_by_state = defaultdict(lambda: {"calls": 0, "cached": 0, "total": 0, "hits": 0})
    for m in llm_state_map:
        st = m["state_type"]
        cache_by_state[st]["calls"] += 1
        cache_by_state[st]["cached"] += m.get("cache_read", 0) or 0
        cache_by_state[st]["total"] += m.get("tokens", 0) or 0
        if (m.get("cache_read", 0) or 0) > 0:
            cache_by_state[st]["hits"] += 1

    for st, d in sorted(cache_by_state.items(), key=lambda x: -x[1]["calls"]):
        hit_pct = 100 * d["hits"] / d["calls"] if d["calls"] > 0 else 0
        token_pct = 100 * d["cached"] / d["total"] if d["total"] > 0 else 0
        summary = (
            f"  {st}: {d['calls']} calls, "
            f"{d['hits']} cache hits ({hit_pct:.0f}%), "
            f"{d['cached']:,} cached / {d['total']:,} total ({token_pct:.1f}%)"
        )
        print(summary)

    # =========================================================================
    # H. FLOOR PROGRESSION TIMELINE
    # =========================================================================
    print("\n--- Floor Progression ---")

    prev_floor = None
    for e in events:
        if e.get("event") == "state":
            f = e.get("floor")
            if f != prev_floor:
                hp = e.get("hp", "?")
                hp_max = e.get("hp_max", "?")
                st = e.get("state_type", "?")
                print(f"  Floor {f}: {st} (HP: {hp}/{hp_max})")
                prev_floor = f

    # =========================================================================
    # I. SLOWEST CALLS WITH CONTEXT
    # =========================================================================
    print("\n--- Top 5 Slowest Calls with Context ---")

    # Sort by latency
    sorted_by_lat = sorted(llm_state_map, key=lambda x: -(x.get("latency_ms") or 0))
    for i, m in enumerate(sorted_by_lat[:5]):
        print(f"\n  #{i + 1}: {m['latency_ms']:.0f}ms ({m['latency_ms'] / 1000:.1f}s)")
        print(f"    State: {m['state_type']} @ Floor {m['floor']}")
        print(f"    Model: {m['model']} (tier={m['tier']}, think={m['think_budget']})")
        print(f"    Tokens: {m['tokens']}, Cache: {m['cache_read']}")
        print(f"    Attempt: {m['attempt']}, Stop: {m['stop_reason']}")

    # =========================================================================
    # J. MAX TOKENS ANALYSIS
    # =========================================================================
    print("\n--- Max Tokens / Truncation ---")

    max_token_calls = [c for c in llm_calls if c.get("stop_reason") == "max_tokens"]
    print(f"  Calls stopped by max_tokens: {len(max_token_calls)}")
    for c in max_token_calls:
        print(f"    tokens={c.get('tokens')}, model={c.get('model')}, type={c.get('call_type')}")

    empty_stop = [c for c in llm_calls if not c.get("stop_reason")]
    print(f"  Calls with empty stop_reason: {len(empty_stop)}")

    # =========================================================================
    # K. COMBAT REWARDS ANALYSIS
    # =========================================================================
    print("\n--- Combat Rewards (random fallback deep dive) ---")

    reward_decisions = [d for d in decisions if d.get("state_type") == "combat_rewards"]
    print(f"  Total combat_rewards decisions: {len(reward_decisions)}")
    reward_sources = Counter(d.get("source") for d in reward_decisions)
    for src, cnt in reward_sources.most_common():
        print(f"    {src}: {cnt}")

    # Show what actions were taken
    reward_actions = Counter()
    for d in reward_decisions:
        action = d.get("action", {})
        if isinstance(action, dict):
            reward_actions[action.get("action", str(action))] += 1
        else:
            reward_actions[str(action)] += 1
    print("  Actions taken:")
    for a, cnt in reward_actions.most_common():
        print(f"    {a}: {cnt}")


# dev script — log paths resolved relative to repo root via __file__.
from pathlib import Path as _Path  # noqa: E402
_LOG_DIR = _Path(__file__).resolve().parents[1] / "logs"
for filepath, label in [
    (str(_LOG_DIR / "run_3055a1e4d209.jsonl"), "Main Run (834 events)"),
    (str(_LOG_DIR / "run_002c637c3692.jsonl"), "Short Run (189 events)"),
]:
    analyze_deep(filepath, label)
