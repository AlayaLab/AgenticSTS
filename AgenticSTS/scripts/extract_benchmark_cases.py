"""Extract LLM test cases from recent run logs for model benchmarking.

Reads the N most recent logs with v2_single_call events (new <decision> protocol)
and selects a representative sample across decision types.

Output: data/benchmark/test_cases.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

LOG_DIR = Path("logs")
DEFAULT_OUT = Path("data/benchmark/test_cases.json")

# Target counts per action type
ACTION_TARGETS = {
    "combat_plan": 4,
    "choose_reward_card": 2,
    "choose_map_node": 2,
    "choose_event_option": 2,
    "buy_card": 1,
    "choose_rest_option": 1,
}

_DECISION_RE = re.compile(r"<decision>\s*(\{.*?\})\s*</decision>", re.DOTALL)


def _parse_decision(response: str) -> dict | None:
    m = _DECISION_RE.search(response)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _action_type(decision: dict) -> str:
    action = decision.get("action")
    if action:
        return action
    # combat_plan uses "plan" key instead of "action"
    if "plan" in decision:
        return "combat_plan"
    return "unknown"


def _total_chars(messages: list[dict]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages)


def load_events(path: Path) -> list[dict]:
    events = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if (
                    obj.get("event") == "llm_call"
                    and obj.get("call_type") == "v2_single_call"
                    and obj.get("response")
                    and obj.get("messages")
                    and "<decision>" in str(obj.get("response", ""))
                ):
                    decision = _parse_decision(str(obj["response"]))
                    if decision:
                        obj["_decision"] = decision
                        obj["_action"] = _action_type(decision)
                        events.append(obj)
            except json.JSONDecodeError:
                continue
    return events


def find_recent_logs(n: int) -> list[Path]:
    logs = sorted(
        LOG_DIR.glob("run_*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return logs[:n]


def extract_cases(max_logs: int = 10) -> list[dict]:
    logs = find_recent_logs(max_logs)
    print(f"Scanning {len(logs)} most recent logs...")

    all_events: list[dict] = []
    for log_path in logs:
        evts = load_events(log_path)
        if evts:
            print(f"  {log_path.name}: {len(evts)} valid decision events")
        all_events.extend(evts)

    # Group by action type
    by_action: dict[str, list[dict]] = {}
    for e in all_events:
        a = e["_action"]
        by_action.setdefault(a, []).append(e)

    print("\nAvailable action types:")
    for a, evts in sorted(by_action.items(), key=lambda x: -len(x[1])):
        chars_list = [_total_chars(e.get("messages") or []) for e in evts]
        avg_c = sum(chars_list) // len(chars_list) if chars_list else 0
        lats = [e.get("latency_ms", 0) for e in evts]
        avg_l = sum(lats) // len(lats) if lats else 0
        print(f"  {a}: {len(evts)} events, avg {avg_c} chars, avg {avg_l:.0f}ms")

    test_cases: list[dict] = []
    case_idx = 0

    for action, target_count in ACTION_TARGETS.items():
        items = by_action.get(action, [])
        if not items:
            print(f"  WARNING: no events for action '{action}'")
            continue

        # Sort by context size and pick distributed samples
        items_sorted = sorted(items, key=lambda e: _total_chars(e.get("messages") or []))
        n = len(items_sorted)
        if n <= target_count:
            selected = items_sorted
        else:
            step = n / target_count
            indices = [int(i * step) for i in range(target_count)]
            selected = [items_sorted[i] for i in indices]

        for e in selected:
            msgs = e.get("messages") or []
            chars = _total_chars(msgs)
            case_idx += 1
            case_id = f"{action}_{case_idx:03d}"

            test_cases.append({
                "id": case_id,
                "action": action,
                "tier": e.get("tier", "strategic"),
                "system_prompt": e.get("system_prompt", ""),
                "messages": msgs,
                "expected_action": action,
                "context_chars": chars,
                "original_model": e.get("model", "kimi-k2.5"),
                "original_latency_ms": e.get("latency_ms", 0),
                "original_tokens": e.get("tokens", 0),
                "run_id": e.get("run_id", ""),
            })
            print(
                f"  [{case_id}] {action}: {chars} chars, "
                f"original_lat={e.get('latency_ms', 0):.0f}ms"
            )

    print(f"\nTotal test cases: {len(test_cases)}")
    return test_cases


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract benchmark test cases from recent logs")
    parser.add_argument("--logs", type=int, default=10, help="Number of recent logs to scan")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    cases = extract_cases(max_logs=args.logs)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(cases)} test cases → {out_path}")


if __name__ == "__main__":
    main()
