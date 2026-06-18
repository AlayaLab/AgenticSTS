"""Standalone A/B test: card_reward Build Trajectory Check.

Compares the original reward prompt (Boss Damage Check only) against a patched
version that adds a Build Trajectory Check section.  Tests against real card_reward
decisions from recent run logs.

Usage:
    python -m scripts.ab_test_reward_trajectory [--cases N] [--model MODEL]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ── Project imports ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src.brain.v2_backend import V2Backend  # noqa: E402
from src.brain.decision_parser import extract_decision, validate_decision  # noqa: E402
from src.storage import paths  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Patch definition ─────────────────────────────────────────

PATCH_NAME = "card_reward_build_trajectory"

# Text that appears in both logged prompts and reward.py output
OLD_TEXT = "SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one."

NEW_TEXT = """\
SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one.

## Build Trajectory Check
Before choosing based on current DPS alone, also consider:
1. **Archetype commitment**: What archetype is your deck building toward? (Check your Strategic Thread / build plan)
2. **Rarity matters**: Rare cards may never appear again this run
3. **Scaling > flat**: Cards that SCALE with future picks (e.g., Knife Trap improves with every Shiv generator added later) beat cards with flat immediate value (e.g., Dagger Throw's fixed 9 damage never grows)
4. **Draft for trajectory**: If the guide recommends an archetype and you've started building it (e.g., you have Blade Dance → Shiv archetype), draft key build-around cards for that trajectory even if current DPS seems low"""

CURRENT_ISSUE = (
    "The reward prompt's Boss Damage Check evaluates cards purely by current DPS impact, "
    "causing the model to pick flat-damage Commons (Dagger Throw) over scaling Rares "
    "(Knife Trap) even when the deck is clearly committed to Shiv archetype. "
    "It ignores card rarity, build trajectory, and future scaling potential."
)

EXPECTED_IMPROVEMENT = (
    "Model should weigh rarity, archetype commitment, and scaling potential alongside "
    "current DPS. Specifically: pick Rare build-around cards (Knife Trap, Accuracy) "
    "over Common flat-damage (Dagger Throw) when the deck has started a Shiv/Poison path. "
    "This should NOT cause the model to skip good immediate-value cards when no archetype "
    "is established yet."
)


# ── Data models ──────────────────────────────────────────────

@dataclass
class TestCase:
    run_id: str
    system_prompt: str
    messages: list[dict]
    prompt: str
    original_response: str
    model: str
    tier: str
    floor: int = 0


@dataclass
class ABResult:
    case: TestCase
    response_a: str = ""
    response_b: str = ""
    thinking_a: str = ""
    thinking_b: str = ""
    decision_a: dict | None = None
    decision_b: dict | None = None
    valid_a: bool = False
    valid_b: bool = False
    judge_verdict: str = ""
    judge_reasoning: str = ""


# ── Extract test cases from logs ─────────────────────────────

def extract_card_reward_cases(log_dir: Path, max_cases: int = 10) -> list[TestCase]:
    """Find card_reward llm_call entries from recent run logs."""
    cases: list[TestCase] = []
    log_files = sorted(log_dir.glob("run_*.jsonl"), reverse=True)

    for log_file in log_files[:15]:  # scan last 15 runs
        run_id = log_file.stem.replace("run_", "")
        try:
            text = log_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue

        for line in text.split("\n"):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("event") != "llm_call":
                continue

            prompt = entry.get("prompt", "")
            # Must be a card_reward prompt AND contain the old_text we're patching
            if "Card Reward" not in prompt or OLD_TEXT not in prompt:
                continue

            # Also check in messages
            messages = entry.get("messages", [])
            all_text = prompt
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str):
                    all_text += " " + content

            if OLD_TEXT not in all_text:
                continue

            # Extract floor from prompt
            floor = 0
            for segment in prompt.split("\n"):
                if "Floor:" in segment:
                    try:
                        floor = int(segment.split("Floor:")[1].strip().split()[0])
                    except (ValueError, IndexError):
                        pass

            cases.append(TestCase(
                run_id=run_id,
                system_prompt=entry.get("system_prompt", ""),
                messages=messages or [{"role": "user", "content": prompt}],
                prompt=prompt,
                original_response=entry.get("response", ""),
                model=entry.get("model", ""),
                tier=entry.get("tier", ""),
                floor=floor,
            ))

            if len(cases) >= max_cases:
                return cases

    return cases


# ── Apply patch to prompt ────────────────────────────────────

def apply_patch(text: str) -> str:
    """Apply the Build Trajectory Check substitution."""
    return text.replace(OLD_TEXT, NEW_TEXT)


def apply_patch_to_messages(messages: list[dict]) -> list[dict]:
    """Apply patch to all message contents."""
    patched = []
    for msg in messages:
        new_msg = dict(msg)
        content = msg.get("content", "")
        if isinstance(content, str) and OLD_TEXT in content:
            new_msg["content"] = content.replace(OLD_TEXT, NEW_TEXT)
        patched.append(new_msg)
    return patched


# ── LLM calls ────────────────────────────────────────────────

async def call_llm(
    backend: V2Backend,
    system: str,
    messages: list[dict],
    model: str,
    provider: str,
) -> tuple[str, str]:
    """Call LLM, return (text_response, thinking_text)."""
    try:
        response = await backend.acall(
            system=system,
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=2000,
        )
        text = V2Backend.extract_text(response)
        # Extract thinking from OpenAI-compatible response if available
        thinking = ""
        if hasattr(response, "choices"):
            for choice in getattr(response, "choices", []):
                msg = getattr(choice, "message", None)
                if msg and hasattr(msg, "reasoning_content"):
                    thinking = getattr(msg, "reasoning_content", "") or ""
                    break
        elif hasattr(response, "content"):
            for block in getattr(response, "content", []):
                if getattr(block, "type", "") == "thinking":
                    thinking = getattr(block, "thinking", "") or ""
                    break
        return text, thinking
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "", ""


async def run_ab_pair(
    backend: V2Backend,
    case: TestCase,
    model: str,
    provider: str,
) -> ABResult:
    """Run A (original) and B (patched) concurrently."""
    result = ABResult(case=case)

    # Build patched versions
    patched_system = apply_patch(case.system_prompt)
    patched_messages = apply_patch_to_messages(case.messages)

    # Run A and B concurrently
    (resp_a, think_a), (resp_b, think_b) = await asyncio.gather(
        call_llm(backend, case.system_prompt, case.messages, model, provider),
        call_llm(backend, patched_system, patched_messages, model, provider),
    )

    result.response_a = resp_a
    result.response_b = resp_b
    result.thinking_a = think_a
    result.thinking_b = think_b

    # Validate decisions
    dec_a = extract_decision(resp_a, allow_fallback=True) if resp_a else None
    dec_b = extract_decision(resp_b, allow_fallback=True) if resp_b else None

    result.decision_a = dec_a
    result.decision_b = dec_b

    errors_a = validate_decision(dec_a, "card_reward_action") if dec_a else ["no decision"]
    errors_b = validate_decision(dec_b, "card_reward_action") if dec_b else ["no decision"]

    result.valid_a = len(errors_a) == 0
    result.valid_b = len(errors_b) == 0

    return result


# ── Judge ────────────────────────────────────────────────────

JUDGE_PROMPT = """\
You are evaluating two AI responses for a Slay the Spire 2 card reward decision.

## Issue Being Tested
{current_issue}

## Expected Improvement
{expected_improvement}

## Game Context (abbreviated)
{context_summary}

## Response A (original prompt — Boss Damage Check only)
{response_a}

## Response B (patched prompt — Boss Damage Check + Build Trajectory Check)
{response_b}

Compare both responses. Focus on:
1. **Decision quality**: Which card pick is strategically correct for this game state?
   - Consider deck archetype, card rarity, scaling potential, and immediate value
2. **Reasoning quality**: Does the response show awareness of build trajectory, not just current DPS?
3. **The specific issue**: Does B avoid the "flat-value Common over scaling Rare" trap?

IMPORTANT: If both responses make the same pick and the pick is reasonable, rate SAME.
Only rate BETTER_B if B makes a clearly superior pick OR shows significantly better reasoning.
Only rate WORSE_B if B makes a clearly worse pick (e.g., takes a useless Rare over an urgently needed card).

First provide a 2-3 sentence analysis, then on a new line output exactly one of: BETTER_B, SAME, WORSE_B"""


async def judge_pair(
    backend: V2Backend,
    result: ABResult,
    model: str,
    provider: str,
) -> None:
    """Judge an A/B pair and set verdict."""
    # Summarize the game context (first 600 chars of user prompt)
    context = result.case.prompt[:600]

    prompt = JUDGE_PROMPT.format(
        current_issue=CURRENT_ISSUE,
        expected_improvement=EXPECTED_IMPROVEMENT,
        context_summary=context,
        response_a=result.response_a[:1500],
        response_b=result.response_b[:1500],
    )

    try:
        response = await backend.acall(
            system="You are an expert Slay the Spire 2 player evaluating AI decisions. Be fair and precise.",
            messages=[{"role": "user", "content": prompt}],
            provider=provider,
            model=model,
            max_tokens=300,
        )
        text = V2Backend.extract_text(response)

        # Parse verdict from last line
        lines = text.strip().split("\n")
        last_line = lines[-1].strip().upper()

        if "BETTER_B" in last_line:
            result.judge_verdict = "BETTER_B"
        elif "WORSE_B" in last_line:
            result.judge_verdict = "WORSE_B"
        else:
            result.judge_verdict = "SAME"

        result.judge_reasoning = "\n".join(lines[:-1]).strip()

    except Exception as exc:
        logger.warning("Judge call failed: %s", exc)
        result.judge_verdict = "JUDGE_ERROR"
        result.judge_reasoning = str(exc)


# ── Main ─────────────────────────────────────────────────────

def print_report(results: list[ABResult]) -> None:
    """Print detailed A/B test report."""
    print("\n" + "=" * 80)
    print(f"A/B TEST REPORT: {PATCH_NAME}")
    print("=" * 80)

    counts = {"BETTER_B": 0, "SAME": 0, "WORSE_B": 0, "INVALID_B": 0, "INVALID_A": 0, "JUDGE_ERROR": 0}

    for i, r in enumerate(results):
        print(f"\n{'─' * 60}")
        print(f"Case {i+1}: run={r.case.run_id[:12]} floor={r.case.floor}")

        # Show picks
        pick_a = r.decision_a.get("option_index", "?") if r.decision_a else "INVALID"
        pick_b = r.decision_b.get("option_index", "?") if r.decision_b else "INVALID"
        action_a = r.decision_a.get("action", "?") if r.decision_a else "?"
        action_b = r.decision_b.get("action", "?") if r.decision_b else "?"

        print(f"  A (original):  action={action_a}, index={pick_a}, valid={r.valid_a}")
        print(f"  B (patched):   action={action_b}, index={pick_b}, valid={r.valid_b}")

        # Show reasoning snippets
        reason_a = (r.decision_a or {}).get("reasoning", "")[:120]
        reason_b = (r.decision_b or {}).get("reasoning", "")[:120]
        if reason_a:
            print(f"  A reasoning: {reason_a}")
        if reason_b:
            print(f"  B reasoning: {reason_b}")

        # Show thinking snippets
        if r.thinking_a:
            print(f"  A thinking: {r.thinking_a[:200]}...")
        if r.thinking_b:
            print(f"  B thinking: {r.thinking_b[:200]}...")

        # Verdict
        if not r.valid_b:
            verdict = "INVALID_B"
        elif not r.valid_a:
            verdict = "INVALID_A"
        else:
            verdict = r.judge_verdict

        counts[verdict] = counts.get(verdict, 0) + 1
        print(f"  VERDICT: {verdict}")
        if r.judge_reasoning:
            print(f"  Judge: {r.judge_reasoning[:200]}")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    total = len(results)
    print(f"Total cases: {total}")
    for v, c in sorted(counts.items()):
        if c > 0:
            pct = c / total * 100
            print(f"  {v}: {c} ({pct:.0f}%)")

    # Verdict
    better = counts["BETTER_B"]
    worse = counts["WORSE_B"]
    invalid = counts["INVALID_B"]
    same = counts["SAME"]

    print()
    if invalid > 0:
        print(f"RESULT: INCONCLUSIVE — {invalid} INVALID_B (patch broke decision format)")
    elif worse > better:
        print(f"RESULT: REJECT — more regressions ({worse}) than improvements ({better})")
    elif better > 0 and worse == 0:
        print(f"RESULT: PROMOTE — {better} improvements, 0 regressions, {same} same")
    elif better > worse:
        print(f"RESULT: MARGINAL — {better} improvements vs {worse} regressions")
    else:
        print(f"RESULT: NEUTRAL — no clear difference ({same} same)")


async def main() -> None:
    parser = argparse.ArgumentParser(description="A/B test: card_reward Build Trajectory Check")
    parser.add_argument("--cases", type=int, default=10, help="Max test cases (default 10)")
    parser.add_argument("--model", type=str, default="", help="Override test model")
    parser.add_argument("--judge-model", type=str, default="", help="Override judge model")
    parser.add_argument("--provider", type=str, default="", help="Override provider")
    args = parser.parse_args()

    # Use strategic model for testing (same tier as actual card_reward decisions)
    test_model = args.model or config.LLM_STRATEGIC_MODEL
    test_provider = args.provider or config.get_tier_provider("strategic")
    judge_model = args.judge_model or config.LLM_ANALYSIS_MODEL
    judge_provider = config.get_tier_provider("analysis")

    print(f"Test model: {test_model} (provider: {test_provider})")
    print(f"Judge model: {judge_model} (provider: {judge_provider})")

    # Extract test cases
    log_dir = Path(config.LOG_DIR)
    cases = extract_card_reward_cases(log_dir, max_cases=args.cases)
    print(f"Found {len(cases)} card_reward test cases from logs")

    if not cases:
        print("ERROR: No card_reward test cases found. Run some games first.")
        return

    # Initialize backend
    backend = V2Backend()

    # Run A/B pairs
    print(f"\nRunning {len(cases)} A/B pairs...")
    t0 = time.time()

    results: list[ABResult] = []
    # Run pairs in batches of 3 to avoid overwhelming the API
    batch_size = 3
    for batch_start in range(0, len(cases), batch_size):
        batch = cases[batch_start:batch_start + batch_size]
        batch_tasks = [
            run_ab_pair(backend, case, test_model, test_provider)
            for case in batch
        ]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        for r in batch_results:
            if isinstance(r, Exception):
                logger.warning("A/B pair failed: %s", r)
            else:
                results.append(r)
        print(f"  Completed {min(batch_start + batch_size, len(cases))}/{len(cases)} pairs")

    elapsed_ab = time.time() - t0
    print(f"A/B calls done in {elapsed_ab:.1f}s")

    # Judge pairs
    print(f"\nJudging {len(results)} pairs...")
    t1 = time.time()

    judge_tasks = []
    for r in results:
        if r.valid_a and r.valid_b:
            judge_tasks.append(judge_pair(backend, r, judge_model, judge_provider))

    if judge_tasks:
        await asyncio.gather(*judge_tasks)

    elapsed_judge = time.time() - t1
    print(f"Judging done in {elapsed_judge:.1f}s")

    # Report
    print_report(results)

    # Save detailed results
    out_path = paths.ab_test_results_dir() / f"reward_trajectory_{int(time.time())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_data = {
        "patch_name": PATCH_NAME,
        "test_model": test_model,
        "judge_model": judge_model,
        "n_cases": len(results),
        "timestamp": time.time(),
        "results": [
            {
                "run_id": r.case.run_id,
                "floor": r.case.floor,
                "decision_a": r.decision_a,
                "decision_b": r.decision_b,
                "valid_a": r.valid_a,
                "valid_b": r.valid_b,
                "thinking_a": r.thinking_a,
                "thinking_b": r.thinking_b,
                "judge_verdict": r.judge_verdict,
                "judge_reasoning": r.judge_reasoning,
            }
            for r in results
        ],
    }
    out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nDetailed results saved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
