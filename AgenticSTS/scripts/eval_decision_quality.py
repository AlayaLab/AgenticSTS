"""LLM-as-judge quality evaluation for STS2 agent decision benchmark.

Loads benchmark results (with response_text) + test cases, then uses Claude
Opus to score each model's decision on a 1-5 rubric across three dimensions:

  action_quality   (1-5) — Is the chosen action sensible given the game state?
                           e.g. correct card played, right map node chosen
  reasoning_depth  (1-5) — Does the analysis show real STS2 mechanics knowledge?
                           e.g. correctly assesses damage, block, scaling
  conciseness      (1-5) — Is the reasoning focused, not bloated or off-topic?

Final quality score = weighted average: 0.5 * action + 0.3 * reasoning + 0.2 * conciseness

The judge sees:
  - The game state (system_prompt + user messages, trimmed to fit context)
  - Each model's full response
  - Rubric instructions

Usage:
    python -m scripts.eval_decision_quality                          # latest results
    python -m scripts.eval_decision_quality --results data/benchmark/results_XYZ.json
    python -m scripts.eval_decision_quality --actions combat_plan    # filter
    python -m scripts.eval_decision_quality --concurrency 4          # parallel judge calls
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

RESULTS_DIR = Path("data/benchmark")
CASES_PATH = Path("data/benchmark/test_cases.json")

# Use main key (Claude Opus) for judging
JUDGE_MODEL = "claude-opus-4-6"
JUDGE_API_KEY = config.LLM_API_KEY  # main key = Claude only
JUDGE_BASE_URL = config.ANTHROPIC_BASE_URL or "https://api.anthropic.com"
JUDGE_TIMEOUT = 120.0
MAX_CONTEXT_CHARS = 6000   # truncate game state to keep judge prompt manageable
MAX_RESPONSE_CHARS = 3000  # truncate model response for judge

JUDGE_SYSTEM = """You are an expert Slay the Spire 2 player evaluating AI agent decisions.
Score each decision on three dimensions (1-5 integer each):

action_quality (weight 0.5):
  5 = Optimal or near-optimal choice given visible game state
  4 = Good choice, minor suboptimality
  3 = Acceptable but clearly not the best line
  2 = Questionable — misses key threats or opportunities
  1 = Wrong / harmful choice (wastes energy, ignores lethal, etc.)

reasoning_depth (weight 0.3):
  5 = Explicitly reasons about damage values, sequencing, scaling, tempo
  4 = Solid reasoning with minor gaps
  3 = Surface-level but not wrong
  2 = Vague or ignores critical mechanics
  1 = No relevant reasoning / hallucinated facts

conciseness (weight 0.2):
  5 = Tight — every sentence is useful
  4 = Mostly focused, minor redundancy
  3 = Some bloat but core reasoning present
  2 = Significant padding or repetition
  1 = Mostly off-topic or extremely verbose

Reply ONLY with valid JSON, no other text:
{"action_quality": <1-5>, "reasoning_depth": <1-5>, "conciseness": <1-5>, "justification": "<one sentence>"}"""


def _find_latest_results() -> Path:
    files = sorted(
        RESULTS_DIR.glob("results_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        raise FileNotFoundError("No results files in data/benchmark/")
    return files[0]


def _trim(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + f"\n... [trimmed {len(text)-max_chars} chars] ...\n" + text[-half:]


def _build_judge_prompt(
    *,
    action: str,
    system_prompt: str,
    messages: list[dict],
    model_name: str,
    response_text: str,
) -> str:
    # Build compact game state
    game_state_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = str(msg.get("content", ""))
        game_state_parts.append(f"[{role}]\n{content}")
    game_state = "\n\n".join(game_state_parts)
    game_state_trimmed = _trim(game_state, MAX_CONTEXT_CHARS)

    response_trimmed = _trim(response_text, MAX_RESPONSE_CHARS)

    return (
        f"## Game State (action type: {action})\n\n"
        f"{game_state_trimmed}\n\n"
        f"## Model Response ({model_name})\n\n"
        f"{response_trimmed}"
    )


def judge_one(
    *,
    client: httpx.Client,
    action: str,
    system_prompt: str,
    messages: list[dict],
    model_name: str,
    response_text: str,
) -> dict:
    prompt = _build_judge_prompt(
        action=action,
        system_prompt=system_prompt,
        messages=messages,
        model_name=model_name,
        response_text=response_text,
    )

    payload: dict[str, Any] = {
        "model": JUDGE_MODEL,
        "max_tokens": 256,
        "temperature": 0,
        "system": JUDGE_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = client.post(
            f"{JUDGE_BASE_URL.rstrip('/')}/v1/messages",
            json=payload,
            headers={
                "x-api-key": JUDGE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        data = resp.json()
        text = data["content"][0]["text"].strip()
        # strip markdown code fences if present
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        scores = json.loads(text)
        aq = scores["action_quality"]
        rd = scores["reasoning_depth"]
        co = scores["conciseness"]
        composite = round(0.5 * aq + 0.3 * rd + 0.2 * co, 2)
        return {
            "action_quality": aq,
            "reasoning_depth": rd,
            "conciseness": co,
            "composite": composite,
            "justification": scores.get("justification", ""),
            "error": None,
        }
    except Exception as e:
        return {"error": str(e)}


def run_eval(
    *,
    results_path: Path,
    cases_path: Path,
    action_filter: list[str] | None = None,
    concurrency: int = 4,
) -> dict:
    with open(results_path, encoding="utf-8") as f:
        bench = json.load(f)
    with open(cases_path, encoding="utf-8") as f:
        cases_list = json.load(f)

    models = bench["models"]
    results = bench["results"]
    cases_by_id = {c["id"]: c for c in cases_list}

    # Only evaluate valid decisions with response text
    to_eval = [
        r for r in results
        if r.get("decision_valid")
        and r.get("response_text")
        and (not action_filter or r["action"] in action_filter)
    ]

    print(f"Results file : {results_path.name}")
    print(f"Models       : {models}")
    print(f"To evaluate  : {len(to_eval)} valid decisions")
    print(f"Judge model  : {JUDGE_MODEL}  (concurrency={concurrency})\n")

    client = httpx.Client(
        timeout=httpx.Timeout(timeout=JUDGE_TIMEOUT, connect=30.0),
        follow_redirects=True,
    )
    print_lock = threading.Lock()
    completed = [0]
    total = len(to_eval)

    def _judge_task(r: dict) -> dict:
        case = cases_by_id.get(r["case_id"])
        if not case:
            return {**r, "scores": {"error": "case not found"}}

        scores = judge_one(
            client=client,
            action=r["action"],
            system_prompt=case["system_prompt"],
            messages=case["messages"],
            model_name=r["model"],
            response_text=r["response_text"],
        )

        with print_lock:
            completed[0] += 1
            n = completed[0]
            if scores.get("error"):
                print(f"  [{n:>3}/{total}] {r['model']:<28} [{r['case_id']}]  JUDGE_ERROR: {scores['error'][:60]}")
            else:
                print(
                    f"  [{n:>3}/{total}] {r['model']:<28} [{r['case_id']}]  "
                    f"action={scores['action_quality']}  "
                    f"reason={scores['reasoning_depth']}  "
                    f"concise={scores['conciseness']}  "
                    f"→ {scores['composite']:.2f}  "
                    f"\"{scores['justification'][:60]}\""
                )

        return {**r, "scores": scores}

    scored: list[dict] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(_judge_task, r): r for r in to_eval}
        for fut in as_completed(futures):
            try:
                scored.append(fut.result())
            except Exception as e:
                r = futures[fut]
                print(f"  EXCEPTION {r['model']} [{r['case_id']}]: {e}")

    client.close()

    # Build report
    report = build_quality_report(scored, models, action_filter)

    return {"scored": scored, "report": report}


def build_quality_report(scored: list[dict], models: list[str], action_filter: list[str] | None) -> str:
    lines = []
    W = 90
    lines.append("=" * W)
    lines.append("DECISION QUALITY EVALUATION — STS2 Agent  LLM-as-Judge  (Claude Opus 4.6)")
    lines.append(f"Generated : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if action_filter:
        lines.append(f"Filter    : {action_filter}")
    lines.append("=" * W)
    lines.append("\nScoring: action_quality×0.5 + reasoning_depth×0.3 + conciseness×0.2  (max 5.0)\n")

    # Overall per model
    lines.append("## Overall Quality\n")
    hdr = f"{'Model':<28} {'N':>4} {'Composite':>10} {'Action':>8} {'Reasoning':>10} {'Concise':>9}"
    lines.append(hdr)
    lines.append("-" * len(hdr))

    for model in models:
        mr = [r for r in scored if r["model"] == model and not r["scores"].get("error")]
        if not mr:
            lines.append(f"{model:<28} {'N/A':>4}")
            continue
        composite = [r["scores"]["composite"] for r in mr]
        aq = [r["scores"]["action_quality"] for r in mr]
        rd = [r["scores"]["reasoning_depth"] for r in mr]
        co = [r["scores"]["conciseness"] for r in mr]
        lines.append(
            f"{model:<28} {len(mr):>4} "
            f"{mean(composite):>10.2f} "
            f"{mean(aq):>8.2f} "
            f"{mean(rd):>10.2f} "
            f"{mean(co):>9.2f}"
        )

    # Per action type
    actions = sorted({r["action"] for r in scored})
    for action in actions:
        lines.append(f"\n## Action: {action}\n")
        hdr2 = f"{'Model':<28} {'N':>4} {'Composite':>10} {'Action':>8} {'Reasoning':>10}"
        lines.append(hdr2)
        lines.append("-" * len(hdr2))
        for model in models:
            mr = [r for r in scored if r["model"] == model and r["action"] == action
                  and not r["scores"].get("error")]
            if not mr:
                continue
            composite = [r["scores"]["composite"] for r in mr]
            aq = [r["scores"]["action_quality"] for r in mr]
            rd = [r["scores"]["reasoning_depth"] for r in mr]
            lines.append(
                f"{model:<28} {len(mr):>4} "
                f"{mean(composite):>10.2f} "
                f"{mean(aq):>8.2f} "
                f"{mean(rd):>10.2f}"
            )

    # Per-case detail with justifications
    lines.append("\n## Per-Case Justifications\n")
    case_ids = sorted({r["case_id"] for r in scored})
    for case_id in case_ids:
        cr = [r for r in scored if r["case_id"] == case_id]
        action = cr[0]["action"] if cr else "?"
        lines.append(f"  [{case_id}] {action}")
        for model in models:
            for r in [x for x in cr if x["model"] == model]:
                s = r["scores"]
                if s.get("error"):
                    lines.append(f"    {model:<28}  JUDGE_ERROR: {s['error'][:60]}")
                else:
                    lines.append(
                        f"    {model:<28}  {s['composite']:.2f}  "
                        f"(a={s['action_quality']} r={s['reasoning_depth']} c={s['conciseness']})  "
                        f"\"{s['justification'][:70]}\""
                    )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-as-judge quality eval for benchmark results")
    parser.add_argument("--results", default="", help="Path to results JSON (default: latest)")
    parser.add_argument("--cases", default=str(CASES_PATH))
    parser.add_argument("--actions", default="", help="Comma-separated action filter")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()

    results_path = Path(args.results) if args.results else _find_latest_results()
    action_filter = [a.strip() for a in args.actions.split(",") if a.strip()] or None

    out = run_eval(
        results_path=results_path,
        cases_path=Path(args.cases),
        action_filter=action_filter,
        concurrency=args.concurrency,
    )

    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_out = RESULTS_DIR / f"quality_{ts}.json"
    txt_out = RESULTS_DIR / f"quality_{ts}.txt"

    with open(json_out, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": ts, "scored": out["scored"]},
            f, ensure_ascii=False, indent=2,
        )
    with open(txt_out, "w", encoding="utf-8") as f:
        f.write(out["report"])

    print(f"\nScores  → {json_out}")
    print(f"Report  → {txt_out}")
    print("\n" + out["report"])


if __name__ == "__main__":
    main()
