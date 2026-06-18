"""
Concurrent quality comparison: gpt-5.4 (baseline) vs gpt-5.4-mini vs gpt-5.4-nano
on real prompts extracted from recent gameplay logs.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

# Load .env
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            k, _, v = _line.partition("=")
            os.environ[k.strip()] = v.strip()

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.brain.v2_backend import V2Backend

# ── Config ────────────────────────────────────────────────────────────────────
MODELS = [
    ("gpt-5.4",        "medium"),   # baseline
    ("gpt-5.4-mini",   ""),         # candidate A (no thinking)
    ("gpt-5.4-nano",   ""),         # candidate B (no thinking)
]
LOG_DIR = Path("logs")
N_CASES = 10


# ── Collect real cases from logs ───────────────────────────────────────────────
def collect_cases(n: int) -> list[dict]:
    logs = sorted(
        [f for f in os.listdir(LOG_DIR) if f.startswith("run_2026")],
        reverse=True,
    )[:10]
    cases = []
    seen = set()
    for log_name in logs:
        path = LOG_DIR / log_name
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                    except Exception:
                        continue
                    if e.get("event") != "llm_call":
                        continue
                    prompt = e.get("prompt", "")
                    system = e.get("system_prompt", "")
                    response = e.get("response", "")
                    if len(prompt) < 200 or not response:
                        continue
                    key = prompt[:120]
                    if key in seen:
                        continue
                    seen.add(key)
                    cases.append({
                        "system": system,
                        "prompt": prompt,
                        "response": response,
                        "orig_model": e.get("model", "?"),
                        "tier": e.get("tier", "?"),
                        "orig_tokens": e.get("tokens", 0),
                        "orig_latency_ms": e.get("latency_ms", 0),
                    })
        except Exception:
            pass
        if len(cases) >= n:
            break
    # Prefer strategic, then fast
    strategic = [c for c in cases if c["tier"] == "strategic"]
    fast = [c for c in cases if c["tier"] == "fast"]
    selected = (strategic[:8] + fast[:2])[:n]
    return selected


# ── Single model call ──────────────────────────────────────────────────────────
async def call_model(
    backend: V2Backend,
    system: str,
    prompt: str,
    model: str,
    effort: str,
    case_idx: int,
) -> dict:
    t0 = time.monotonic()
    try:
        resp = await backend.acall(
            system=system,
            messages=[{"role": "user", "content": prompt}],
            provider="openai_compatible",
            model=model,
            think=bool(effort),
            effort=effort,
        )
        text = backend.extract_text(resp)
        usage = getattr(resp, "usage", None)
        tok = (
            (getattr(usage, "input_tokens", 0) or 0)
            + (getattr(usage, "output_tokens", 0) or 0)
        ) if usage else 0
        latency = (time.monotonic() - t0) * 1000
        return {
            "model": model,
            "case_idx": case_idx,
            "ok": True,
            "response": text,
            "tokens": tok,
            "latency_ms": latency,
        }
    except Exception as exc:
        latency = (time.monotonic() - t0) * 1000
        return {
            "model": model,
            "case_idx": case_idx,
            "ok": False,
            "response": f"ERROR: {exc}",
            "tokens": 0,
            "latency_ms": latency,
        }


# ── Quality scoring ────────────────────────────────────────────────────────────
def score_response(response: str, case: dict) -> dict:
    """
    Heuristic scoring vs the baseline gpt-5.4 response.
    Checks:
    1. valid_json      — response contains parseable JSON (or <decision> block)
    2. has_action      — JSON has an "action" or "plan" field
    3. has_reasoning   — response contains meaningful reasoning text
    4. len_ratio       — output length relative to baseline (0.5–2.0 is OK)
    5. action_match    — top-level action/plan matches baseline
    """
    orig = case.get("response", "")

    # Extract JSON from <decision> block or raw
    def extract_json(text: str) -> dict | None:
        import re
        m = re.search(r"<decision>(.*?)</decision>", text, re.DOTALL)
        raw = m.group(1).strip() if m else text.strip()
        # Try to find first { ... }
        start = raw.find("{")
        if start == -1:
            return None
        # Find matching closing brace
        depth = 0
        for i, ch in enumerate(raw[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start : i + 1])
                    except Exception:
                        return None
        return None

    resp_json = extract_json(response)
    orig_json = extract_json(orig)

    valid_json = resp_json is not None
    has_action = valid_json and (
        "action" in resp_json or "plan" in resp_json
    )

    # reasoning: look for non-JSON text
    import re
    text_outside = re.sub(r"<decision>.*?</decision>", "", response, flags=re.DOTALL).strip()
    reasoning_in_json = valid_json and bool(
        resp_json.get("reasoning") or resp_json.get("end_turn_reasoning")
    )
    has_reasoning = bool(text_outside) or reasoning_in_json

    # length ratio
    len_ratio = len(response) / max(len(orig), 1)

    # action match
    action_match = False
    if orig_json and resp_json:
        orig_action = orig_json.get("action") or (
            "plan" if "plan" in orig_json else None
        )
        resp_action = resp_json.get("action") or (
            "plan" if "plan" in resp_json else None
        )
        action_match = orig_action == resp_action

    # composite score 0-100
    score = 0
    if valid_json:
        score += 40
    if has_action:
        score += 20
    if has_reasoning:
        score += 20
    if 0.3 <= len_ratio <= 3.0:
        score += 10
    if action_match:
        score += 10

    return {
        "score": score,
        "valid_json": valid_json,
        "has_action": has_action,
        "has_reasoning": has_reasoning,
        "len_ratio": round(len_ratio, 2),
        "action_match": action_match,
    }


# ── Main ───────────────────────────────────────────────────────────────────────
async def main() -> None:
    print("Collecting real gameplay cases from logs...")
    cases = collect_cases(N_CASES)
    print(f"  → {len(cases)} cases selected")
    for i, c in enumerate(cases):
        print(f"  [{i}] tier={c['tier']} orig={c['orig_model']} "
              f"prompt_len={len(c['prompt'])} orig_latency={c['orig_latency_ms']:.0f}ms")
    print()

    backend = V2Backend()

    # Build all tasks
    tasks = []
    for case_idx, case in enumerate(cases):
        for model, effort in MODELS:
            tasks.append(
                call_model(
                    backend,
                    case["system"],
                    case["prompt"],
                    model,
                    effort,
                    case_idx,
                )
            )

    print(f"Running {len(tasks)} concurrent calls ({len(cases)} cases × {len(MODELS)} models)...")
    t_start = time.monotonic()
    results = await asyncio.gather(*tasks)
    total_time = time.monotonic() - t_start
    print(f"Done in {total_time:.1f}s\n")

    # Organise results: results[case_idx][model]
    by_case: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in results:
        by_case[r["case_idx"]][r["model"]] = r

    # Print per-case comparison
    model_scores: dict[str, list[int]] = defaultdict(list)
    model_latencies: dict[str, list[float]] = defaultdict(list)
    model_tokens: dict[str, list[int]] = defaultdict(list)

    for case_idx, case in enumerate(cases):
        print(f"═══ Case {case_idx} | tier={case['tier']} | orig={case['orig_model']} "
              f"| orig_latency={case['orig_latency_ms']:.0f}ms ═══")
        print(f"  Prompt snippet: {case['prompt'][:120].strip()!r}")
        print(f"  Baseline resp : {case['response'][:120].strip()!r}")
        print()

        case_results = by_case[case_idx]
        for model, effort in MODELS:
            r = case_results.get(model, {})
            if not r:
                continue
            sc = score_response(r["response"], case)
            model_scores[model].append(sc["score"])
            model_latencies[model].append(r["latency_ms"])
            if r["tokens"]:
                model_tokens[model].append(r["tokens"])

            status = "OK" if r["ok"] else "ERR"
            print(
                f"  [{model:<22}] {status} | "
                f"lat={r['latency_ms']:6.0f}ms | "
                f"tok={r['tokens']:5} | "
                f"score={sc['score']:3}/100 "
                f"(json={sc['valid_json']!s:5} act={sc['has_action']!s:5} "
                f"rsn={sc['has_reasoning']!s:5} amatch={sc['action_match']!s:5})"
            )
            resp_snippet = r["response"][:150].replace("\n", " ").strip()
            print(f"  {'':24}   resp: {resp_snippet!r}")
        print()

    # Summary
    print("═══════════════════════════════════════════")
    print("SUMMARY")
    print("═══════════════════════════════════════════")
    print(f"{'Model':<24} {'AvgScore':>9} {'AvgLat(ms)':>12} {'AvgTok':>8}")
    print("-" * 56)
    for model, effort in MODELS:
        scores = model_scores[model]
        lats = model_latencies[model]
        toks = model_tokens[model]
        avg_score = sum(scores) / len(scores) if scores else 0
        avg_lat = sum(lats) / len(lats) if lats else 0
        avg_tok = sum(toks) / len(toks) if toks else 0
        print(f"  {model:<22} {avg_score:8.1f} {avg_lat:11.0f} {avg_tok:8.0f}")


if __name__ == "__main__":
    asyncio.run(main())
