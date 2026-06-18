"""Test GPT-5.4 thinking/reasoning effort levels with real post-run prompts.

Tests different reasoning effort levels (none, low, medium, high, xhigh)
against 3 representative post-run tasks:
  1. Rule distillation (win vs loss comparison)
  2. Guide consolidation (combat guide synthesis)
  3. Skill discovery (extract skills from a run)

Usage:
    python -m scripts.test_gpt54_thinking
    python -m scripts.test_gpt54_thinking --efforts medium,high,xhigh
    python -m scripts.test_gpt54_thinking --tasks distill,discovery
    python -m scripts.test_gpt54_thinking --model gpt-5.4
    python -m scripts.test_gpt54_thinking --repeats 2
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Effort levels to test ────────────────────────────────────────────────────

ALL_EFFORTS = ["none", "low", "medium", "high", "xhigh"]
ALL_TASKS = ["distill", "guide", "discovery"]

# ── Realistic test prompts ───────────────────────────────────────────────────

DISTILL_SYSTEM = (
    "You are a Slay the Spire 2 strategy analyst. "
    "Extract reusable strategy rules from run data. "
    "Output a JSON array of rule objects."
)

DISTILL_PROMPT = """\
Analyze these winning vs losing Slay the Spire 2 runs and extract
reusable strategy rules that explain what winners did differently.

## Winning Runs

### Win #1
Character: Silent, Archetype: poison, Result: WIN
Final deck (18 cards): Neutralize, Survivor, Strike, Strike, Defend, Defend, Backstab, Poisoned Stab, Noxious Fumes, Blade Dance, Footwork, Deflect, Acrobatics, Dash, Catalyst, Predator, Concentrate, Wraith Form
Most played: Neutralize(23), Survivor(19), Poisoned Stab(17), Defend(15), Blade Dance(12)
Combats: 14W/0L
Last combat: vs Awakened One, HP 52->31, WON, 8 rounds

### Win #2
Character: Silent, Archetype: shiv_discard, Result: WIN
Final deck (22 cards): Neutralize, Survivor, Strike, Strike, Strike, Defend, Defend, Defend, Backstab, Blade Dance, Blade Dance, Cloak and Dagger, Accuracy, Infinite Blades, After Image, Prepared, Dagger Spray, Escape Plan, Eviscerate, Outmaneuver, Reflex, Finisher
Most played: Blade Dance(31), Neutralize(22), Cloak and Dagger(20), Defend(18), Survivor(16)
Combats: 15W/1L
Last combat: vs Time Eater, HP 38->12, WON, 11 rounds

## Losing Runs

### Loss #1
Character: Silent, Archetype: unknown, Result: LOSS at floor 23
Final deck (26 cards): Neutralize, Survivor, Strike, Strike, Strike, Strike, Strike, Defend, Defend, Defend, Defend, Backstab, Deadly Poison, Dodge and Roll, Leg Sweep, Bane, Slice, Sucker Punch, Backflip, Quick Slash, Caltrops, All-Out Attack, Dagger Spray, Endless Agony, Heel Hook, Well-Laid Plans
Most played: Strike(28), Defend(22), Neutralize(14), Deadly Poison(8), Slice(7)
Combats: 8W/1L
Last combat: vs Gremlin Nob, HP 31->0, LOST, 4 rounds

### Loss #2
Character: Silent, Archetype: unknown, Result: LOSS at floor 34
Final deck (24 cards): Neutralize, Survivor, Strike, Strike, Strike, Defend, Defend, Defend, Backstab, Poisoned Stab, Dodge and Roll, Leg Sweep, Blade Dance, Quick Slash, Prepared, Dagger Spray, Bouncing Flask, Terror, Footwork, Malaise, Backstab, Caltrops, Flying Knee, Underhanded Strike
Most played: Neutralize(34), Defend(28), Strike(25), Poisoned Stab(12), Blade Dance(11)
Combats: 12W/1L
Last combat: vs Collector, HP 44->0, LOST, 6 rounds

## Instructions
Extract 1-5 strategy rules. For each rule, output JSON:
```json
[
  {"rule_text": "...", "context": "combat|map|event|rest|reward|all", "confidence": 0.5}
]
```
Rules should be specific and actionable. Confidence 0.5 = unverified hypothesis.

When comparing wins vs losses, also analyze HP efficiency: runs that minimized \
HP loss through non-boss fights preserved more resources for boss encounters. \
A run that won 5 combats but lost 60% HP in each is weaker than one that won \
5 combats losing 10% HP each, even if both reached the same floor."""


GUIDE_SYSTEM = (
    "You are a Slay the Spire 2 combat strategy analyst. "
    "Synthesize episode data into an actionable combat guide. "
    "Output valid JSON."
)

GUIDE_PROMPT = """\
You are analyzing combat data from a Slay the Spire 2 AI agent.

Enemy: Gremlin Nob
Character: Silent
Episodes analyzed: 6

### Episode 1 (WON, 4 rounds)
HP: 72->58 (lost 14)
Cards played: Neutralize, Survivor(discard Strike), Backstab, Blade Dance, Deflect, Defend, Poisoned Stab, Leg Sweep
Key: Applied Weak via Neutralize turn 1, maintained block while dealing damage. Finished with shiv burst.

### Episode 2 (LOST, 3 rounds)
HP: 65->0 (lost 65)
Cards played: Strike, Strike, Defend, Defend, Poisoned Stab, Quick Slash
Key: Failed to apply Weak turn 1. Nob used Skull Bash + Berserk, scaling became unmanageable.

### Episode 3 (WON, 5 rounds)
HP: 71->42 (lost 29)
Cards played: Neutralize, Defend, Defend, Survivor, Backstab, Blade Dance, Blade Dance, Footwork, Poisoned Stab, Finisher
Key: Applied Weak immediately. Used Footwork to scale block against increasing damage.

### Episode 4 (WON, 3 rounds)
HP: 68->61 (lost 7)
Cards played: Neutralize, Backstab, Blade Dance, Dash, Predator, Survivor, Cloak and Dagger
Key: Perfect opening — Neutralize + Backstab + Blade Dance dealt 30+ damage turn 1 while applying Weak. Fast kill minimized damage taken.

### Episode 5 (LOST, 4 rounds)
HP: 70->0 (lost 70)
Cards played: Strike, Strike, Strike, Defend, Defend, Defend, Sucker Punch, Bane
Key: No Weak application. All Strikes are attacks that trigger Nob's Enrage, and without Weak the 8-damage scaling destroyed block capacity.

### Episode 6 (WON, 4 rounds)
HP: 66->51 (lost 15)
Cards played: Neutralize, Survivor, Blade Dance, Defend, Backstab, Acrobatics, Poisoned Stab, Concentrate, Dash
Key: Strong opener with Neutralize, then high-value skills. Acrobatics for draw cycling.

Create a combat guide for this enemy. Respond with JSON:
{"guide_text": "...", "key_cards": ["card1", "card2", ...], "confidence": 0.5-0.9}

Keep guide_text under 150 words."""


DISCOVERY_SYSTEM = """\
You are a Slay the Spire 2 strategy researcher analyzing gameplay.

A "skill" is a specific, actionable piece of game knowledge that helps make
better decisions. Skills should be:
1. Specific enough to be useful (not just "play good cards")
2. General enough to apply across multiple situations
3. Testable — you can tell if following the skill helped or hurt

Focus on patterns that led to success or patterns whose absence led to failure.

HP efficiency matters: a fight won without losing HP is better than one where \
HP was lost. Skills should guide the agent to minimize HP loss in every fight, \
not just survive. "Tank the damage" is only acceptable when ALL energy is needed \
for a kill this turn AND there are no 0-cost block options."""

DISCOVERY_PROMPT = """\
## Run Summary
- Result: DEFEAT (floor 31)
- Character: Silent
- Final floor: 31
- Fitness score: 42.3
- Combats: 11/12 won

## Key Decision Points
- Floor 3 (card_reward): chose Poisoned Stab — early damage + poison
- Floor 5 (combat): vs Jaw Worm, played Neutralize first, won losing 5 HP
- Floor 7 (card_reward): chose Blade Dance — multi-hit for shiv synergy
- Floor 8 (rest): chose Rest (HP 41/72) — correct at <60%
- Floor 10 (combat): vs Lagavulin, slow start, lost 22 HP over 6 rounds
- Floor 12 (shop): bought Footwork — block scaling essential
- Floor 15 (boss): vs Hexaghost, won losing 18 HP, used Neutralize + shivs
- Floor 18 (card_reward): chose Catalyst — poison multiplier
- Floor 21 (combat): vs Book of Stabbing, took 28 damage, deck too slow to block multi-attacks
- Floor 25 (elite): vs Nemesis, won but lost 35 HP due to intangible phases
- Floor 28 (rest): chose Upgrade (Footwork+) — doubling block gain
- Floor 31 (boss): vs Collector, died in round 6, couldn't handle minion + boss damage simultaneously

## Existing Skills (avoid duplicates)
- Poison Stack Before Catalyst (combat)
- Weak Priority vs High-Damage Enemies (combat)
- Rest Below 50% HP (rest)
- Skip Curses at Events (event)
- Frontload Damage vs Time-Limited Fights (combat)

## Task
Analyze this run and extract 0-2 new strategic skills that would help in future runs.
For each skill, provide:
- A concise name
- Category: combat | deck_building | map | event | rest | boss
- Tier: "general" (applies broadly) or "specific" (specific situation)
- When it should activate (state type, enemy name, HP threshold, etc.)
- The specific strategic advice (2-4 sentences, MUST be under 400 characters)
- What goes wrong when this skill is NOT followed (1 sentence lesson)
- A concrete example
- positive_rounds: list of round descriptions where following this skill worked
- negative_rounds: list of round descriptions where NOT following this skill hurt
- not_covered_by: list of existing skill names that do NOT already cover this advice

Return a JSON array of skills (or empty array [] if no new skills to add):
[
  {
    "name": "Skill Name",
    "category": "combat",
    "tier": "specific",
    "trigger": {
      "state_types": ["monster", "elite"],
      "enemy_names": [],
      "tags": ["relevant", "tags"]
    },
    "content": "The strategic advice...",
    "lessons": "What goes wrong without this skill...",
    "examples": ["Concrete example of applying this skill"],
    "positive_rounds": ["Floor 5 vs Cultist: played Neutralize+Poison to prevent 12 dmg"],
    "negative_rounds": ["Floor 8 vs Lagavulin: tanked 18 dmg due to no block sequence"],
    "not_covered_by": ["Existing Skill Name"]
  }
]

IMPORTANT: Return ONLY the JSON array. No markdown, no explanation outside JSON."""


# ── Test case registry ───────────────────────────────────────────────────────

TASKS = {
    "distill": {"system": DISTILL_SYSTEM, "prompt": DISTILL_PROMPT, "desc": "Rule distillation"},
    "guide": {"system": GUIDE_SYSTEM, "prompt": GUIDE_PROMPT, "desc": "Combat guide synthesis"},
    "discovery": {"system": DISCOVERY_SYSTEM, "prompt": DISCOVERY_PROMPT, "desc": "Skill discovery"},
}


# ── Result model ─────────────────────────────────────────────────────────────

@dataclass
class TestResult:
    task: str
    effort: str
    model: str
    latency_ms: float = 0
    total_tokens: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    response_chars: int = 0
    json_valid: bool = False
    json_items: int = 0
    error: str = ""
    raw_response: str = ""


# ── Core test runner ─────────────────────────────────────────────────────────

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL)


async def run_single_test(
    task_name: str,
    effort: str,
    model: str,
) -> TestResult:
    """Run a single task with a given effort level."""
    from src.brain.v2_backend import V2Backend

    task_cfg = TASKS[task_name]
    result = TestResult(task=task_name, effort=effort, model=model)

    backend = V2Backend()
    messages = [{"role": "user", "content": task_cfg["prompt"]}]
    think = effort != "none"

    start = time.monotonic()
    try:
        response = await backend.acall(
            system=task_cfg["system"],
            messages=messages,
            provider="openai_compatible",
            model=model,
            think=think,
            effort=effort if think else "",
            openai_relay_profile="postrun",
        )
    except Exception as exc:
        result.error = str(exc)[:300]
        result.latency_ms = (time.monotonic() - start) * 1000
        return result

    result.latency_ms = (time.monotonic() - start) * 1000

    # Extract text
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text
    # Strip thinking tags injected by proxy
    if think and "<thinking>" in text:
        text = _THINKING_TAG_RE.sub("", text).strip()
    result.raw_response = text
    result.response_chars = len(text)

    # Token usage
    if response.usage:
        result.input_tokens = getattr(response.usage, "input_tokens", 0)
        result.output_tokens = getattr(response.usage, "output_tokens", 0)
        result.total_tokens = result.input_tokens + result.output_tokens
        # Some providers expose reasoning tokens
        if hasattr(response.usage, "completion_tokens_details"):
            details = response.usage.completion_tokens_details
            result.reasoning_tokens = getattr(details, "reasoning_tokens", 0)

    # Validate JSON output
    try:
        # Find JSON in response
        json_str = text
        # Try markdown code block first
        m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if m:
            json_str = m.group(1).strip()
        else:
            # Try bare JSON array/object
            m = re.search(r"[\[{].*[\]}]", text, re.DOTALL)
            if m:
                json_str = m.group(0).strip()

        parsed = json.loads(json_str)
        result.json_valid = True
        if isinstance(parsed, list):
            result.json_items = len(parsed)
        elif isinstance(parsed, dict):
            result.json_items = 1
    except (json.JSONDecodeError, ValueError):
        result.json_valid = False

    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def print_results_table(results: list[TestResult]) -> None:
    """Print results as a formatted comparison table."""
    # Group by task
    tasks_seen = []
    for r in results:
        if r.task not in tasks_seen:
            tasks_seen.append(r.task)

    header = f"{'Task':<12} {'Effort':<8} {'Latency':>9} {'Tokens':>8} {'In':>7} {'Out':>7} {'Reason':>7} {'Chars':>7} {'JSON':>5} {'Items':>5} {'Error'}"
    print("\n" + "=" * len(header))
    print(header)
    print("-" * len(header))

    for task in tasks_seen:
        task_results = [r for r in results if r.task == task]
        for r in task_results:
            json_ok = "OK" if r.json_valid else "FAIL"
            err = r.error[:40] if r.error else ""
            print(
                f"{r.task:<12} {r.effort:<8} {r.latency_ms:>8.0f}ms {r.total_tokens:>7d} "
                f"{r.input_tokens:>7d} {r.output_tokens:>7d} {r.reasoning_tokens:>7d} "
                f"{r.response_chars:>7d} {json_ok:>5} {r.json_items:>5} {err}"
            )
        print("-" * len(header))

    print("=" * len(header))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test GPT-5.4 reasoning efforts")
    parser.add_argument(
        "--efforts",
        default=",".join(ALL_EFFORTS),
        help="Comma-separated effort levels to test (default: all)",
    )
    parser.add_argument(
        "--tasks",
        default=",".join(ALL_TASKS),
        help="Comma-separated tasks to test (default: all)",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.4",
        help="Model name (default: gpt-5.4)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of repeats per combination (default: 1)",
    )
    parser.add_argument(
        "--save",
        default="data/benchmark/gpt54_thinking_test.jsonl",
        help="Path to save results JSONL",
    )
    args = parser.parse_args()

    efforts = [e.strip() for e in args.efforts.split(",")]
    tasks = [t.strip() for t in args.tasks.split(",")]

    # Validate
    for e in efforts:
        if e not in ALL_EFFORTS:
            print(f"Unknown effort: {e}. Choose from: {ALL_EFFORTS}")
            sys.exit(1)
    for t in tasks:
        if t not in TASKS:
            print(f"Unknown task: {t}. Choose from: {list(TASKS.keys())}")
            sys.exit(1)

    total = len(tasks) * len(efforts) * args.repeats
    print(f"\nTesting {args.model} with {len(efforts)} effort levels x {len(tasks)} tasks x {args.repeats} repeats = {total} calls")
    print(f"Tasks: {tasks}")
    print(f"Efforts: {efforts}")
    print()

    results: list[TestResult] = []
    save_path = Path(args.save)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    for rep in range(args.repeats):
        if args.repeats > 1:
            print(f"\n--- Repeat {rep + 1}/{args.repeats} ---")

        for task in tasks:
            for effort in efforts:
                desc = TASKS[task]["desc"]
                print(f"  [{task}] effort={effort} ... ", end="", flush=True)
                r = await run_single_test(task, effort, args.model)
                results.append(r)

                status = "OK" if r.json_valid else ("ERR" if r.error else "BAD_JSON")
                print(
                    f"{r.latency_ms:.0f}ms, "
                    f"{r.total_tokens} tok (in={r.input_tokens} out={r.output_tokens} reason={r.reasoning_tokens}), "
                    f"json={status}, items={r.json_items}"
                )
                if r.error:
                    print(f"    ERROR: {r.error[:200]}")

                # Save incrementally
                with open(save_path, "a", encoding="utf-8") as f:
                    row = {
                        "task": r.task,
                        "effort": r.effort,
                        "model": r.model,
                        "latency_ms": round(r.latency_ms, 1),
                        "total_tokens": r.total_tokens,
                        "input_tokens": r.input_tokens,
                        "output_tokens": r.output_tokens,
                        "reasoning_tokens": r.reasoning_tokens,
                        "response_chars": r.response_chars,
                        "json_valid": r.json_valid,
                        "json_items": r.json_items,
                        "error": r.error,
                        "repeat": rep,
                    }
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print_results_table(results)

    # Save raw responses for quality review
    raw_dir = save_path.parent / "gpt54_raw_responses"
    raw_dir.mkdir(exist_ok=True)
    for r in results:
        if r.raw_response:
            fname = f"{r.task}_{r.effort}.txt"
            (raw_dir / fname).write_text(r.raw_response, encoding="utf-8")
    print(f"\nRaw responses saved to: {raw_dir}")
    print(f"Results JSONL saved to: {save_path}")


if __name__ == "__main__":
    asyncio.run(main())
