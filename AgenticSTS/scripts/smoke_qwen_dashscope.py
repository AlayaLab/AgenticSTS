"""Smoke test: Qwen3.6-35B-A3B on Alibaba Cloud DashScope (OpenAI-compatible).

Primary goal: verify `enable_thinking=False` actually disables thinking
(vs SiliconFlow where the budget param is ignored).

DashScope quirks vs SiliconFlow:
  - base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  - model id: qwen3.6-35b-a3b  (lowercase, dashes; NOT Qwen/Qwen3.6-35B-A3B)
  - enable_thinking: extra_body={"enable_thinking": False}  (flat key, NOT nested in chat_template_kwargs)
  - default: thinking ENABLED

Tests (all parallel):
  1. thinking=OFF raw-text       (expected: fast, no reasoning_content)
  2. thinking=ON  raw-text        (expected: slower, reasoning_content populated)
  3. thinking=OFF tool_use        (expected: fast tool call)
  4. thinking=ON  tool_use        (expected: tool call + reasoning)
  5. concurrency × 3 thinking=OFF (rate-limit + warm-path check)

Reads CLI arg or STS2_DASHSCOPE_API_KEY env. Does NOT touch repo config.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

env_path = Path(__file__).parent.parent / ".env"
if env_path.is_file():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

parser = argparse.ArgumentParser()
parser.add_argument("--api-key", default=os.environ.get("STS2_DASHSCOPE_API_KEY", ""),
                    help="DashScope API key (or set STS2_DASHSCOPE_API_KEY)")
parser.add_argument("--model", default="qwen3.6-35b-a3b")
parser.add_argument("--timeout", type=float, default=180.0)
args = parser.parse_args()

API_KEY = args.api_key
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = args.model
PER_CALL_TIMEOUT_SEC = args.timeout

if not API_KEY:
    print("ERR: API key not provided. Pass --api-key or set STS2_DASHSCOPE_API_KEY")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("ERR: openai package not installed. Run: pip install openai")
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=PER_CALL_TIMEOUT_SEC)

_print_lock = threading.Lock()


def _make_log(tag: str) -> Callable[[str], None]:
    def log(msg: str) -> None:
        with _print_lock:
            for ln in msg.rstrip("\n").split("\n"):
                print(f"[{tag}] {ln}")
                sys.stdout.flush()
    return log


SUBMIT_PLAN_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "submit_plan",
            "description": "Submit the ordered card play plan for this turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plays": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "card_name": {"type": "string"},
                                "target": {"type": "string", "description": "enemy name or 'self'"},
                                "reason": {"type": "string"},
                            },
                            "required": ["card_name", "target", "reason"],
                        },
                    },
                    "end_turn_rationale": {"type": "string"},
                },
                "required": ["plays", "end_turn_rationale"],
            },
        },
    }
]


COMBAT_PROMPT = (
    "Combat state: player 18/50 HP, 3 energy, 0 block. "
    "Enemies: Cultist (40/48 HP, buffing 3 str next turn), Louse A (12/15 HP, attacks for 6). "
    "Hand: Strike (6 dmg, 1e), Strike (6 dmg, 1e), Defend (5 blk, 1e), "
    "Bash (8 dmg + 2 Vuln, 2e), Survivor (8 blk + discard, 1e). "
    "Plan this turn. Prioritize."
)


def _run_raw(tag: str, enable_thinking: bool, max_tokens: int) -> bool:
    log = _make_log(tag)
    log(f"dispatch → {MODEL} enable_thinking={enable_thinking}")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are a Slay the Spire 2 combat planner."},
                {"role": "user", "content": COMBAT_PROMPT},
            ],
            extra_body={"enable_thinking": enable_thinking},
            max_tokens=max_tokens,
        )
        dt = (time.time() - t0) * 1000
        msg = resp.choices[0].message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None) or ""
        log(f"latency={dt:.0f}ms  in={resp.usage.prompt_tokens} out={resp.usage.completion_tokens}  "
            f"reasoning_len={len(reasoning)}  content_len={len(content)}")
        log(f"content: {content[:250]}")
        if enable_thinking is False and len(reasoning) > 0:
            log(f"WARN: enable_thinking=False but reasoning_content leaked ({len(reasoning)} chars)")
        return bool(content)
    except Exception as e:
        log(f"FAIL after {(time.time()-t0)*1000:.0f}ms: {type(e).__name__}: {e}")
        return False


def _run_tool(tag: str, enable_thinking: bool, max_tokens: int) -> bool:
    log = _make_log(tag)
    log(f"dispatch → {MODEL} enable_thinking={enable_thinking} +tool_use")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are the STS2 combat engine. Always call submit_plan."},
                {"role": "user", "content": COMBAT_PROMPT},
            ],
            tools=SUBMIT_PLAN_TOOL,
            tool_choice="auto",
            extra_body={"enable_thinking": enable_thinking},
            max_tokens=max_tokens,
        )
        dt = (time.time() - t0) * 1000
        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        reasoning = getattr(msg, "reasoning_content", None) or ""
        log(f"latency={dt:.0f}ms  out={resp.usage.completion_tokens}  "
            f"reasoning_len={len(reasoning)}  tool_calls={len(tool_calls)}")
        if enable_thinking is False and len(reasoning) > 0:
            log(f"WARN: enable_thinking=False but reasoning_content leaked ({len(reasoning)} chars)")
        if tool_calls:
            try:
                a = json.loads(tool_calls[0].function.arguments)
                log(f"args: {json.dumps(a, ensure_ascii=False)[:300]}")
                return True
            except json.JSONDecodeError as e:
                log(f"JSON parse FAIL: {e}")
                return False
        log(f"no tool_calls; content={(msg.content or '(empty)')[:200]}")
        return False
    except Exception as e:
        log(f"FAIL after {(time.time()-t0)*1000:.0f}ms: {type(e).__name__}: {e}")
        return False


def test_1_nothink_raw() -> bool:  return _run_raw("t1:nothink-raw", False, 4096)
def test_2_think_raw() -> bool:    return _run_raw("t2:think-raw",   True,  20000)
def test_3_nothink_tool() -> bool: return _run_tool("t3:nothink-tool", False, 4096)
def test_4_think_tool() -> bool:   return _run_tool("t4:think-tool",   True,  20000)


def _concurrent_worker(idx: int) -> dict:
    log = _make_log(f"t5:worker{idx}")
    log("dispatch (enable_thinking=False)")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": "You are the STS2 combat engine. Always call submit_plan."},
                {"role": "user", "content": f"[worker {idx}] {COMBAT_PROMPT}"},
            ],
            tools=SUBMIT_PLAN_TOOL,
            tool_choice="auto",
            extra_body={"enable_thinking": False},
            max_tokens=4096,
        )
        dt = (time.time() - t0) * 1000
        tool_calls = resp.choices[0].message.tool_calls or []
        ok = bool(tool_calls)
        log(f"{'OK' if ok else 'FAIL'} latency={dt:.0f}ms out={resp.usage.completion_tokens}")
        return {"idx": idx, "latency_ms": dt, "ok": ok, "out": resp.usage.completion_tokens}
    except Exception as e:
        dt = (time.time() - t0) * 1000
        log(f"FAIL after {dt:.0f}ms: {type(e).__name__}: {e}")
        return {"idx": idx, "latency_ms": dt, "ok": False, "error": str(e)}


def test_5_concurrency() -> bool:
    log = _make_log("t5:concurrency")
    log("spawning 3 parallel nothink+tool workers")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(_concurrent_worker, range(3)))
    wall = (time.time() - t0) * 1000
    passed = sum(1 for r in results if r.get("ok"))
    latencies = [r["latency_ms"] for r in results if r.get("ok")]
    log(f"wall={wall:.0f}ms pass={passed}/3  "
        f"serial_sum={sum(r['latency_ms'] for r in results):.0f}ms")
    if latencies:
        log(f"  min={min(latencies):.0f}ms max={max(latencies):.0f}ms "
            f"speedup={(sum(latencies)/wall):.2f}x")
    return passed == 3


if __name__ == "__main__":
    print(f"base_url: {BASE_URL}")
    print(f"model:    {MODEL}")
    print(f"api_key:  {API_KEY[:12]}...{API_KEY[-4:]}")
    print(f"timeout:  {PER_CALL_TIMEOUT_SEC}s")
    print("\nAll 5 tests run concurrently.")
    print("=" * 70)

    tests = [
        ("nothink raw",       test_1_nothink_raw),
        ("think raw",         test_2_think_raw),
        ("nothink tool_use",  test_3_nothink_tool),
        ("think tool_use",    test_4_think_tool),
        ("concurrency x3",    test_5_concurrency),
    ]

    results: dict[str, bool] = {}
    wall_t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tests)) as ex:
        future_to_name = {ex.submit(fn): name for name, fn in tests}
        for fut in concurrent.futures.as_completed(future_to_name):
            name = future_to_name[fut]
            try:
                results[name] = fut.result()
            except Exception as e:
                with _print_lock:
                    print(f"[{name}] UNCAUGHT: {type(e).__name__}: {e}")
                results[name] = False
    wall = (time.time() - wall_t0) * 1000

    print("\n" + "=" * 70 + "\n  SUMMARY\n" + "=" * 70)
    for name, ok in results.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n  wall (all tests parallel): {wall:.0f}ms")
    sys.exit(0 if all(results.values()) else 1)
