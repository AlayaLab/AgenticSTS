"""Smoke test: Qwen family on SiliconFlow — all 5 tests run in parallel.

Matches `config._MODEL_FAMILIES["qwen"]`:
  fast      → Qwen/Qwen3.5-35B-A3B  (effort=low,    thinking=on/low)
  strategic → Qwen/Qwen3.5-35B-A3B  (effort=medium, thinking=on/medium + tool_use)
Both tiers use the same model; effort differentiates reasoning depth.

Tests (all dispatched concurrently; test 5 fans out to 3 more workers,
so peak concurrency ≈ 7 live SiliconFlow calls):
  1. Fast tier: 9B + low thinking (raw-text completion).
  2. Strategic tier: 35B-A3B + medium thinking (raw-text completion).
  3. Strategic tier: 35B-A3B + thinking + tool_use (V2 engine critical path).
  4. Fast tier + tool_use: 9B + low thinking + tool_use (map step / single-card).
  5. Concurrency: 3 parallel strategic + tool_use calls (rate-limit + warm-path).

Per-call timeout = 180s (fails fast rather than hanging).
Thread-safe tagged logging so progress is visible while tests run.

Reads STS2_QWEN_API_KEY from .env, overrides base_url to SiliconFlow.
Does NOT touch repo config.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

env_path = Path(__file__).parent.parent / ".env"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("STS2_QWEN_API_KEY", "")
BASE_URL = "https://api.siliconflow.cn/v1"
FAST_MODEL = "Qwen/Qwen3.5-35B-A3B"
STRATEGIC_MODEL = "Qwen/Qwen3.5-35B-A3B"
PER_CALL_TIMEOUT_SEC = 180.0

# --no-think: disable thinking + inject response_format=json_object (tests Option A)
NO_THINK = "--no-think" in sys.argv

if not API_KEY:
    print("ERR: STS2_QWEN_API_KEY not set")
    sys.exit(1)

try:
    from openai import OpenAI
except ImportError:
    print("ERR: openai package not installed. Run: pip install openai")
    sys.exit(1)

client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=PER_CALL_TIMEOUT_SEC)

_print_lock = threading.Lock()


def _think_kwargs(budget: int = 8192) -> dict:
    """Return extra_body / response_format kwargs based on NO_THINK flag."""
    if NO_THINK:
        return {
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
            "response_format": {"type": "json_object"},
        }
    return {
        "extra_body": {
            "chat_template_kwargs": {"enable_thinking": True},
            "thinking_budget": budget,
        },
    }


def _make_log(tag: str) -> Callable[[str], None]:
    def log(msg: str) -> None:
        with _print_lock:
            for line in msg.rstrip("\n").split("\n"):
                print(f"[{tag}] {line}")
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

SINGLE_CARD_TOOL = [
    {
        "type": "function",
        "function": {
            "name": "pick_single_card",
            "description": "Pick one card from hand to play next.",
            "parameters": {
                "type": "object",
                "properties": {
                    "card_index": {"type": "integer", "minimum": 0},
                    "target": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["card_index", "target", "reason"],
            },
        },
    }
]


def test_1_fast_tier() -> bool:
    log = _make_log("test1:fast-raw")
    mode = "no-think+json_object" if NO_THINK else "low thinking"
    log(f"dispatch → {FAST_MODEL} + {mode}")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": "You are a Slay the Spire 2 tactical advisor. Respond in JSON with key 'advice'."},
                {"role": "user", "content": "I have 30 HP and a Jaw Worm (40 HP) is attacking for 11. Should I block or attack?"},
            ],
            max_tokens=8192,
            **_think_kwargs(4096),
        )
        dt = (time.time() - t0) * 1000
        msg = resp.choices[0].message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None) or ""
        log(f"latency={dt:.0f}ms  in={resp.usage.prompt_tokens} out={resp.usage.completion_tokens}  reasoning_len={len(reasoning)}  content_len={len(content)}")
        log(f"content: {content[:250]}")
        return bool(content)
    except Exception as e:
        log(f"FAIL after {(time.time()-t0)*1000:.0f}ms: {type(e).__name__}: {e}")
        return False


def test_2_strategic_tier() -> bool:
    log = _make_log("test2:strat-raw")
    mode = "no-think+json_object" if NO_THINK else "medium thinking"
    log(f"dispatch → {STRATEGIC_MODEL} + {mode}")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=STRATEGIC_MODEL,
            messages=[
                {"role": "system", "content": "You are a Slay the Spire 2 combat planner. Output JSON with key 'plan'."},
                {"role": "user", "content": (
                    "Combat state: player 18/50 HP, 3 energy, 0 block. "
                    "Enemies: Cultist (40/48 HP, buffing 3 str next turn), Louse A (12/15 HP, attacks for 6). "
                    "Hand: Strike (6 dmg, 1e), Strike (6 dmg, 1e), Defend (5 blk, 1e), Bash (8 dmg + 2 Vuln, 2e), Survivor (8 blk + discard, 1e). "
                    "Plan this turn. Prioritize."
                )},
            ],
            max_tokens=20000,
            **_think_kwargs(8192),
        )
        dt = (time.time() - t0) * 1000
        msg = resp.choices[0].message
        content = msg.content or ""
        reasoning = getattr(msg, "reasoning_content", None) or ""
        log(f"latency={dt:.0f}ms  in={resp.usage.prompt_tokens} out={resp.usage.completion_tokens}  reasoning_len={len(reasoning)}  content_len={len(content)}")
        log(f"content: {content[:250]}")
        return bool(content)
    except Exception as e:
        log(f"FAIL after {(time.time()-t0)*1000:.0f}ms: {type(e).__name__}: {e}")
        return False


def test_3_strategic_tool_use() -> bool:
    log = _make_log("test3:strat-tool")
    log(f"dispatch → {STRATEGIC_MODEL} + medium thinking + tool_use")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=STRATEGIC_MODEL,
            messages=[
                {"role": "system", "content": "You are the STS2 combat engine. Always call submit_plan with your turn plan."},
                {"role": "user", "content": (
                    "State: HP 22/50, energy 3, block 0. "
                    "Enemies: Gremlin Nob (HP 82/82, Enrage — attacks for 16 next, gains 2 str on any skill play). "
                    "Hand: Strike x2 (6 dmg, 1e), Defend (5 blk, 1e), Body Slam (deal dmg=block, 1e), Shrug It Off (8 blk + draw 1, 1e). "
                    "Plan turn."
                )},
            ],
            tools=SUBMIT_PLAN_TOOL,
            tool_choice="auto",
            max_tokens=20000,
            **_think_kwargs(8192),
        )
        dt = (time.time() - t0) * 1000
        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        reasoning = getattr(msg, "reasoning_content", None) or ""
        log(f"latency={dt:.0f}ms  out={resp.usage.completion_tokens}  reasoning_len={len(reasoning)}  tool_calls={len(tool_calls)}")
        if tool_calls:
            try:
                args = json.loads(tool_calls[0].function.arguments)
                log(f"args: {json.dumps(args, ensure_ascii=False)[:300]}")
            except json.JSONDecodeError as e:
                log(f"JSON parse FAIL: {e}")
                return False
            return True
        log(f"no tool_calls; content={(msg.content or '(empty)')[:200]}")
        return False
    except Exception as e:
        log(f"FAIL after {(time.time()-t0)*1000:.0f}ms: {type(e).__name__}: {e}")
        return False


def test_4_fast_tool_use() -> bool:
    log = _make_log("test4:fast-tool")
    log(f"dispatch → {FAST_MODEL} + low thinking + tool_use")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=FAST_MODEL,
            messages=[
                {"role": "system", "content": "You are the STS2 single-card engine. Call pick_single_card."},
                {"role": "user", "content": (
                    "State: HP 45/50, energy 2, block 0. Enemy Cultist (40/48 HP, attacks for 6). "
                    "Hand: [0] Strike (6 dmg, 1e), [1] Defend (5 blk, 1e), [2] Neutralize (3 dmg + 1 Weak, 0e)."
                )},
            ],
            tools=SINGLE_CARD_TOOL,
            tool_choice="auto",
            max_tokens=8192,
            **_think_kwargs(4096),
        )
        dt = (time.time() - t0) * 1000
        msg = resp.choices[0].message
        tool_calls = msg.tool_calls or []
        reasoning = getattr(msg, "reasoning_content", None) or ""
        log(f"latency={dt:.0f}ms  out={resp.usage.completion_tokens}  reasoning_len={len(reasoning)}  tool_calls={len(tool_calls)}")
        if tool_calls:
            try:
                args = json.loads(tool_calls[0].function.arguments)
                log(f"args: {json.dumps(args, ensure_ascii=False)[:250]}")
            except json.JSONDecodeError as e:
                log(f"JSON parse FAIL: {e}")
                return False
            return True
        log(f"no tool_calls; content={(msg.content or '(empty)')[:200]}")
        return False
    except Exception as e:
        log(f"FAIL after {(time.time()-t0)*1000:.0f}ms: {type(e).__name__}: {e}")
        return False


def _concurrent_worker(idx: int) -> dict:
    log = _make_log(f"test5:worker{idx}")
    log("dispatch")
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=STRATEGIC_MODEL,
            messages=[
                {"role": "system", "content": "You are the STS2 combat engine. Always call submit_plan."},
                {"role": "user", "content": (
                    f"[worker {idx}] State: HP 30/50, energy 3, block 0. "
                    "Enemies: Jaw Worm (40/40 HP, attacks for 11). "
                    "Hand: Strike x2 (6 dmg, 1e), Defend (5 blk, 1e), Bash (8 dmg + 2 Vuln, 2e), Survivor (8 blk + discard, 1e). "
                    "Plan turn."
                )},
            ],
            tools=SUBMIT_PLAN_TOOL,
            tool_choice="auto",
            max_tokens=20000,
            **_think_kwargs(8192),
        )
        dt = (time.time() - t0) * 1000
        tool_calls = resp.choices[0].message.tool_calls or []
        ok = bool(tool_calls)
        log(f"{'OK' if ok else 'FAIL'}  latency={dt:.0f}ms  out={resp.usage.completion_tokens}  tool_calls={len(tool_calls)}")
        return {"idx": idx, "latency_ms": dt, "ok": ok, "error": None, "out_tokens": resp.usage.completion_tokens}
    except Exception as e:
        dt = (time.time() - t0) * 1000
        log(f"FAIL after {dt:.0f}ms: {type(e).__name__}: {e}")
        return {"idx": idx, "latency_ms": dt, "ok": False, "error": f"{type(e).__name__}: {e}"}


def test_5_concurrency() -> bool:
    log = _make_log("test5:concurrency")
    log(f"spawning 3 parallel workers → {STRATEGIC_MODEL}")
    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(_concurrent_worker, range(3)))
    wall = (time.time() - t0) * 1000
    latencies = [r["latency_ms"] for r in results if r.get("ok")]
    all_ok = all(r.get("ok") for r in results)
    log(f"wall={wall:.0f}ms  serial_sum={sum(r['latency_ms'] for r in results):.0f}ms  "
        f"pass={sum(1 for r in results if r.get('ok'))}/3")
    if latencies:
        log(f"  min={min(latencies):.0f}ms  max={max(latencies):.0f}ms  "
            f"speedup={(sum(latencies) / wall):.2f}x")
    return all_ok


if __name__ == "__main__":
    print(f"base_url:        {BASE_URL}")
    print(f"fast model:      {FAST_MODEL}")
    print(f"strategic model: {STRATEGIC_MODEL}")
    print(f"api_key:         {API_KEY[:12]}...{API_KEY[-4:]}")
    print(f"per-call timeout: {PER_CALL_TIMEOUT_SEC}s")
    print(f"thinking mode:   {'OFF (json_object)' if NO_THINK else 'ON (thinking_budget)'}")
    print("\nAll 5 tests run concurrently. Test 5 fans out to 3 more workers → 7 peak live calls.")
    print("=" * 70)

    tests = [
        ("fast tier raw (35B + low)",         test_1_fast_tier),
        ("strategic tier raw (35B + medium)", test_2_strategic_tier),
        ("strategic + tool_use (35B)",        test_3_strategic_tool_use),
        ("fast + tool_use (35B + low)",       test_4_fast_tool_use),
        ("concurrency x3 (35B)",              test_5_concurrency),
    ]

    results: dict[str, tuple[bool, float]] = {}
    wall_t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tests)) as executor:
        future_to_name = {executor.submit(fn): name for name, fn in tests}
        for future in concurrent.futures.as_completed(future_to_name):
            name = future_to_name[future]
            try:
                ok = future.result()
            except Exception as e:
                ok = False
                with _print_lock:
                    print(f"[{name}] UNCAUGHT: {type(e).__name__}: {e}")
            results[name] = (ok, 0.0)
    wall = (time.time() - wall_t0) * 1000

    print("\n" + "=" * 70 + "\n  SUMMARY\n" + "=" * 70)
    for name, (ok, _) in results.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"\n  wall (all tests parallel): {wall:.0f}ms")
    sys.exit(0 if all(ok for ok, _ in results.values()) else 1)
