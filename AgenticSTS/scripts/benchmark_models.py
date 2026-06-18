"""Multi-model benchmark for AgenticSTS <decision> protocol quality and latency.

Tests models via the OpenAI-compatible endpoint at proxy.example.com using real prompts
extracted from game logs. The new protocol (v2_single_call) sends system + user
messages with NO tools — the model must output a <decision>JSON</decision> block.

Usage:
    python -m scripts.benchmark_models
    python -m scripts.benchmark_models --models kimi-k2.5,glm-5,gpt-5.4,gemini-3.1-pro-preview
    python -m scripts.benchmark_models --runs 2                 # repeat each case N times
    python -m scripts.benchmark_models --actions combat_plan    # filter by action type
    python -m scripts.benchmark_models --api-key sk-xxx         # override API key

Metrics:
    latency_ms          total round-trip time
    tokens_in/out       reported token counts
    decision_valid      response contains parseable <decision> with correct action type
    action_returned     action field from parsed decision (or None)
    response_chars      full response length (includes visible reasoning)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

DEFAULT_MODELS = ["kimi-k2.5", "glm-5", "gpt-5.4", "gemini-3.1-pro-preview"]
DEFAULT_CASES = Path("data/benchmark/test_cases.json")
RESULTS_DIR = Path("data/benchmark")

MAX_TOKENS = 8192
API_TIMEOUT = 180.0

# Thinking models need temperature=1 (they ignore 0)
_THINKING_MODELS = {"o1", "o3", "o4", "gpt-5.4"}

_DECISION_RE = re.compile(r"<decision>\s*(\{.*?\})\s*</decision>", re.DOTALL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_thinking_model(model: str) -> bool:
    return any(t in model.lower() for t in ("thinking", "o1", "o3", "o4-mini"))


def _get_endpoint() -> str:
    base = (config.OPENAI_COMPAT_BASE_URL or "https://proxy.example.com").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _make_client(api_key: str | None = None) -> httpx.Client:
    # OPENAI_COMPAT_API_KEY works for all models (glm, gpt, gemini, kimi)
    # LLM_API_KEY (ANTHROPIC_API_KEY) is restricted to "claude-code" group = Claude only
    key = api_key or config.OPENAI_COMPAT_API_KEY or config.LLM_API_KEY
    return httpx.Client(
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        timeout=httpx.Timeout(timeout=API_TIMEOUT, connect=30.0),
        follow_redirects=True,
    )


def _to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    """Prepend system message; content is always a plain string in new protocol."""
    result: list[dict] = [{"role": "system", "content": system}]
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            # flatten content blocks (shouldn't happen in new protocol, but safe)
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif isinstance(block, str):
                    parts.append(block)
            content = "\n".join(parts)
        result.append({"role": role, "content": str(content)})
    return result


def _parse_decision(response: str) -> tuple[dict | None, str | None]:
    """Return (decision_dict, error_str)."""
    m = _DECISION_RE.search(response)
    if not m:
        return None, "no <decision> block in response"
    try:
        d = json.loads(m.group(1))
        return d, None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON in <decision>: {e}"


def _action_from_decision(d: dict) -> str:
    action = d.get("action")
    if action:
        return action
    if "plan" in d:
        return "combat_plan"
    return "unknown"


# ── Single call ───────────────────────────────────────────────────────────────

def call_model(
    *,
    client: httpx.Client,
    model: str,
    system_prompt: str,
    messages: list[dict],
    endpoint: str,
    expected_action: str,
) -> dict:
    oai_messages = _to_openai_messages(system_prompt, messages)
    temperature = 1 if _is_thinking_model(model) else 0

    payload: dict[str, Any] = {
        "model": model,
        "messages": oai_messages,
        "max_tokens": MAX_TOKENS,
        "temperature": temperature,
    }

    t0 = time.perf_counter()
    error: str | None = None
    response_data: dict = {}
    status_code = 0

    try:
        resp = client.post(endpoint, json=payload)
        status_code = resp.status_code
        latency_ms = (time.perf_counter() - t0) * 1000
        if resp.status_code != 200:
            error = f"HTTP {resp.status_code}: {resp.text[:300]}"
        else:
            response_data = resp.json()
    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - t0) * 1000
        error = f"timeout after {latency_ms:.0f}ms"
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        error = f"request error: {e}"

    # Extract text content
    response_text = ""
    if response_data.get("choices"):
        msg = response_data["choices"][0].get("message", {})
        response_text = msg.get("content") or ""

    # Parse <decision> block
    decision, parse_error = _parse_decision(response_text)
    action_returned = _action_from_decision(decision) if decision else None

    # Validate: decision exists, parses, and matches expected action type
    decision_valid = (
        decision is not None
        and parse_error is None
        and action_returned == expected_action
    )

    usage = response_data.get("usage", {})
    tokens_in = usage.get("prompt_tokens", 0)
    tokens_out = usage.get("completion_tokens", 0)
    # tok/s: output generation speed (key metric — explains latency variation)
    toks_per_sec = round(tokens_out / (latency_ms / 1000), 1) if tokens_out > 0 and latency_ms > 0 else 0.0

    combined_error = " | ".join(filter(None, [error, parse_error]))
    return {
        "model": model,
        "latency_ms": round(latency_ms, 1),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "toks_per_sec": toks_per_sec,
        "decision_valid": decision_valid,
        "action_returned": action_returned,
        "response_text": response_text,
        "response_chars": len(response_text),
        "status_code": status_code,
        "error": combined_error or None,
    }


# ── Benchmark runner ──────────────────────────────────────────────────────────

def run_benchmark(
    *,
    models: list[str],
    cases: list[dict],
    runs_per_case: int = 1,
    action_filter: list[str] | None = None,
    api_key: str | None = None,
    concurrency: int = 8,
) -> list[dict]:
    if action_filter:
        cases = [c for c in cases if c["action"] in action_filter]
        print(f"Filtered to {len(cases)} cases: {action_filter}")

    endpoint = _get_endpoint()
    total = len(models) * len(cases) * runs_per_case
    print(f"\nEndpoint    : {endpoint}")
    print(f"Models      : {models}")
    print(f"Cases       : {len(cases)}")
    print(f"Runs each   : {runs_per_case}")
    print(f"Total calls : {total}  (concurrency={concurrency})\n")

    # Build flat task list; each task is independent
    tasks: list[dict] = []
    for model in models:
        for case in cases:
            for run_i in range(runs_per_case):
                tasks.append({"model": model, "case": case, "run_i": run_i})

    print_lock = threading.Lock()
    completed = [0]

    def _run_task(task: dict) -> dict:
        model = task["model"]
        case = task["case"]
        run_i = task["run_i"]
        # Each thread gets its own httpx client (not thread-safe to share)
        client = _make_client(api_key=api_key)
        try:
            r = call_model(
                client=client,
                model=model,
                system_prompt=case["system_prompt"],
                messages=case["messages"],
                endpoint=endpoint,
                expected_action=case["expected_action"],
            )
        finally:
            client.close()

        r.update({
            "case_id": case["id"],
            "action": case["action"],
            "context_chars": case["context_chars"],
            "run_i": run_i,
            "original_latency_ms": case.get("original_latency_ms", 0),
        })

        with print_lock:
            completed[0] += 1
            n = completed[0]
            if r["error"] and not r["action_returned"]:
                status = f"ERROR  {r['latency_ms']:>8.0f}ms  {r['error'][:60]}"
            else:
                tag = "OK " if r["decision_valid"] else "BAD"
                tps = r.get("toks_per_sec", 0)
                status = (
                    f"{tag}    {r['latency_ms']:>8.0f}ms  "
                    f"action={r['action_returned'] or 'none':<22}  "
                    f"out={r['tokens_out']:>4}  {f'{tps:.0f}tok/s' if tps else '':>8}"
                )
            print(f"  [{n:>3}/{total}] {model:<28} [{case['id']}]  {status}")

        return r

    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_run_task, t): t for t in tasks}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as e:
                task = futures[fut]
                print(f"  EXCEPTION {task['model']} [{task['case']['id']}]: {e}")

    # Sort by model then case_id for stable report ordering
    results.sort(key=lambda r: (models.index(r["model"]), r["case_id"], r["run_i"]))
    return results


# ── Report ────────────────────────────────────────────────────────────────────

def _pct(n: int, total: int) -> str:
    return f"{n/total*100:.0f}%" if total else "N/A"


def build_report(results: list[dict], models: list[str]) -> str:
    lines = []
    W = 82
    lines.append("=" * W)
    lines.append("BENCHMARK — STS2 Agent  <decision> Protocol  Model Comparison")
    lines.append(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * W)

    # Overall
    lines.append("\n## Overall Summary\n")
    hdr = f"{'Model':<28} {'Calls':>6} {'Valid%':>7} {'Median':>9} {'Mean':>9} {'P95':>9} {'TokIn':>7} {'TokOut':>7} {'tok/s':>6}"
    lines.append(hdr)
    lines.append("-" * len(hdr))

    for model in models:
        mr = [r for r in results if r["model"] == model]
        if not mr:
            lines.append(f"  {model:<26} (no results)")
            continue
        n = len(mr)
        valid = sum(1 for r in mr if r["decision_valid"])
        lats = sorted(r["latency_ms"] for r in mr if not r.get("error") or r["action_returned"])
        tin = [r["tokens_in"] for r in mr if r["tokens_in"] > 0]
        tout = [r["tokens_out"] for r in mr if r["tokens_out"] > 0]
        tps = [r["toks_per_sec"] for r in mr if r.get("toks_per_sec", 0) > 0]
        p95 = f"{sorted(lats)[int(len(lats)*0.95)]:.0f}ms" if lats else "N/A"
        lines.append(
            f"{model:<28} {n:>6} {_pct(valid,n):>7} "
            f"{f'{median(lats):.0f}ms' if lats else 'N/A':>9} "
            f"{f'{mean(lats):.0f}ms' if lats else 'N/A':>9} "
            f"{p95:>9} "
            f"{f'{mean(tin):.0f}' if tin else 'N/A':>7} "
            f"{f'{mean(tout):.0f}' if tout else 'N/A':>7} "
            f"{f'{mean(tps):.1f}' if tps else 'N/A':>6}"
        )

    # Per action type
    actions = sorted({r["action"] for r in results})
    for action in actions:
        lines.append(f"\n## Action: {action}\n")
        hdr2 = f"{'Model':<28} {'Valid%':>7} {'Median':>9} {'Mean':>9} {'Errors':>7}"
        lines.append(hdr2)
        lines.append("-" * len(hdr2))
        for model in models:
            mr = [r for r in results if r["model"] == model and r["action"] == action]
            if not mr:
                continue
            n = len(mr)
            valid = sum(1 for r in mr if r["decision_valid"])
            lats = sorted(r["latency_ms"] for r in mr if not r.get("error") or r["action_returned"])
            errs = sum(1 for r in mr if r["error"] and not r["action_returned"])
            lines.append(
                f"{model:<28} {_pct(valid,n):>7} "
                f"{f'{median(lats):.0f}ms' if lats else 'N/A':>9} "
                f"{f'{mean(lats):.0f}ms' if lats else 'N/A':>9} "
                f"{errs:>7}"
            )

    # Per-case detail
    lines.append("\n## Per-Case Detail\n")
    for case_id in sorted({r["case_id"] for r in results}):
        cr = [r for r in results if r["case_id"] == case_id]
        action = cr[0]["action"] if cr else "?"
        ctx = cr[0]["context_chars"] if cr else 0
        orig = cr[0]["original_latency_ms"] if cr else 0
        lines.append(f"  [{case_id}] {action} — {ctx} chars (original kimi: {orig:.0f}ms)")
        for model in models:
            for r in [x for x in cr if x["model"] == model]:
                if r["error"] and not r["action_returned"]:
                    lines.append(f"    {model:<28} ERROR: {r['error'][:70]}")
                else:
                    tag = "OK " if r["decision_valid"] else "BAD"
                    tps = r.get("toks_per_sec", 0)
                    lines.append(
                        f"    {model:<28} {tag} {r['latency_ms']:>8.0f}ms "
                        f"action={r['action_returned'] or 'none':<22} "
                        f"out={r['tokens_out']:>4} {f'{tps:.0f}tok/s' if tps else '':>8}"
                    )

    # Errors
    errs = [r for r in results if r["error"] and not r["action_returned"]]
    if errs:
        lines.append(f"\n## Hard Errors ({len(errs)})\n")
        for r in errs:
            lines.append(f"  {r['model']:<28} [{r['case_id']}] {r['error'][:90]}")

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument("--cases", default=str(DEFAULT_CASES))
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--actions", default="", help="Comma-separated action filter")
    parser.add_argument("--api-key", default="", help="Override API key")
    parser.add_argument("--concurrency", type=int, default=8,
                        help="Max parallel API calls (default: 8)")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    action_filter = [a.strip() for a in args.actions.split(",") if a.strip()] or None

    cases_path = Path(args.cases)
    if not cases_path.exists():
        print(f"No test cases at {cases_path}. Run: python -m scripts.extract_benchmark_cases")
        sys.exit(1)

    with open(cases_path, encoding="utf-8") as f:
        cases = json.load(f)
    print(f"Loaded {len(cases)} test cases from {cases_path}")

    results = run_benchmark(
        models=models,
        cases=cases,
        runs_per_case=args.runs,
        action_filter=action_filter,
        api_key=args.api_key.strip() or None,
        concurrency=args.concurrency,
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = RESULTS_DIR / f"results_{ts}.json"
    txt_path = RESULTS_DIR / f"results_{ts}.txt"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"models": models, "timestamp": ts, "results": results}, f,
                  ensure_ascii=False, indent=2)

    report = build_report(results, models)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nResults → {json_path}")
    print(f"Report  → {txt_path}")
    print("\n" + report)


if __name__ == "__main__":
    main()
