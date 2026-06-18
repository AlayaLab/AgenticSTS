"""Focused A/B test: Knife Trap vs Dagger Throw scenario.

Runs the exact Floor 7 card_reward case (Knife Trap / Leg Sweep / Dagger Throw)
multiple times with original and patched prompts to see if the Build Trajectory
Check changes the model's pick distribution.

Usage:
    python -m scripts.ab_test_knife_trap [--samples N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src.brain.v2_backend import V2Backend  # noqa: E402
from src.brain.decision_parser import extract_decision, validate_decision  # noqa: E402
from src.storage import paths  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ── Patch ────────────────────────────────────────────────────

OLD_TEXT = "SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one."

NEW_TEXT = """\
SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one.

## Build Trajectory Check
Before choosing based on current DPS alone, also consider:
1. **Archetype commitment**: What archetype is your deck building toward? (Check your Strategic Thread / build plan)
2. **Rarity matters**: Rare cards may never appear again this run
3. **Scaling > flat**: Cards that SCALE with future picks (e.g., Knife Trap improves with every Shiv generator added later) beat cards with flat immediate value (e.g., Dagger Throw's fixed 9 damage never grows)
4. **Common cards recur**: Common cards will be offered again — don't take a Common over a Rare that fits your build direction
5. **Draft for trajectory**: If the guide recommends an archetype and you've started building it (e.g., you have Blade Dance → Shiv archetype), draft key build-around cards for that trajectory even if current DPS seems low"""


# ── Find the exact log entry ────────────────────────────────

def find_knife_trap_case(log_dir: Path) -> dict | None:
    """Find the Knife Trap / Leg Sweep / Dagger Throw case from logs."""
    target_file = log_dir / "run_20260416_103123_90ed9ed1.jsonl"
    if not target_file.exists():
        # Fallback: search all recent logs
        for f in sorted(log_dir.glob("run_*.jsonl"), reverse=True)[:10]:
            result = _search_file(f)
            if result:
                return result
        return None
    return _search_file(target_file)


def _search_file(log_file: Path) -> dict | None:
    try:
        text = log_file.read_text(encoding="utf-8").strip()
    except Exception:
        return None

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
        if "Knife Trap" not in prompt or "Dagger Throw" not in prompt or "Card Reward" not in prompt:
            continue

        # Must have all 3 cards as options
        if "[index=0] Knife Trap" in prompt and "[index=2] Dagger Throw" in prompt:
            return entry

    return None


# ── LLM call ────────────────────────────────────────────────

async def call_llm(
    backend: V2Backend,
    system: str,
    messages: list[dict],
    model: str,
    provider: str,
) -> tuple[str, dict | None, bool]:
    """Call LLM, return (raw_response, decision, is_valid)."""
    try:
        response = await backend.acall(
            system=system,
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=2000,
        )
        text = V2Backend.extract_text(response)
        decision = extract_decision(text, allow_fallback=True) if text else None
        errors = validate_decision(decision, "card_reward_action") if decision else ["no decision"]
        return text, decision, len(errors) == 0
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "", None, False


# ── Main ─────────────────────────────────────────────────────

def apply_patch(text: str) -> str:
    return text.replace(OLD_TEXT, NEW_TEXT)


def apply_patch_msgs(messages: list[dict]) -> list[dict]:
    patched = []
    for msg in messages:
        new_msg = dict(msg)
        content = msg.get("content", "")
        if isinstance(content, str) and OLD_TEXT in content:
            new_msg["content"] = content.replace(OLD_TEXT, NEW_TEXT)
        patched.append(new_msg)
    return patched


CARD_NAMES = {0: "Knife Trap", 1: "Leg Sweep", 2: "Dagger Throw", "skip": "Skip"}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5, help="Samples per variant (default 5)")
    parser.add_argument("--model", type=str, default="", help="Override model")
    args = parser.parse_args()

    model = args.model or config.LLM_STRATEGIC_MODEL
    provider = config.get_tier_provider("strategic")
    n = args.samples

    print(f"Model: {model} (provider: {provider})")
    print(f"Samples per variant: {n}")

    # Find the case
    log_dir = Path(config.LOG_DIR)
    entry = find_knife_trap_case(log_dir)
    if not entry:
        print("ERROR: Knife Trap case not found in logs")
        return

    system_prompt = entry.get("system_prompt", "")
    messages = entry.get("messages", [])
    prompt = entry.get("prompt", "")
    if not messages and prompt:
        messages = [{"role": "user", "content": prompt}]

    # Build patched versions
    patched_system = apply_patch(system_prompt)
    patched_messages = apply_patch_msgs(messages)

    # Verify patch was applied
    orig_text = system_prompt + " ".join(m.get("content", "") for m in messages)
    patch_text = patched_system + " ".join(m.get("content", "") for m in patched_messages)
    if "Build Trajectory Check" not in patch_text:
        print("ERROR: Patch not applied — OLD_TEXT not found in prompt")
        print(f"  Checking system_prompt: {'found' if OLD_TEXT in system_prompt else 'NOT found'}")
        for i, m in enumerate(messages):
            c = m.get("content", "")
            print(f"  Checking msg[{i}]: {'found' if OLD_TEXT in c else 'NOT found'}")
        return

    backend = V2Backend()

    # ── Run variant A (original) ─────────────────────────────
    print(f"\n{'='*60}")
    print(f"Running Variant A (original prompt) x{n}...")
    a_picks: list[int | str] = []
    a_details: list[dict] = []

    a_tasks = [call_llm(backend, system_prompt, messages, model, provider) for _ in range(n)]
    a_results = await asyncio.gather(*a_tasks)

    for i, (raw, dec, valid) in enumerate(a_results):
        if not valid or not dec:
            a_picks.append("invalid")
            a_details.append({"raw": raw[:200]})
            continue
        action = dec.get("action", "")
        idx = dec.get("option_index", "?")
        if "alternative" in action:
            a_picks.append("skip")
        else:
            a_picks.append(idx)
        a_details.append({
            "pick": CARD_NAMES.get(idx, f"index={idx}"),
            "reasoning": dec.get("reasoning", "")[:150],
            "strategic_note": dec.get("strategic_note", "")[:100],
        })

    # ── Run variant B (patched) ──────────────────────────────
    print(f"Running Variant B (patched prompt) x{n}...")
    b_picks: list[int | str] = []
    b_details: list[dict] = []

    b_tasks = [call_llm(backend, patched_system, patched_messages, model, provider) for _ in range(n)]
    b_results = await asyncio.gather(*b_tasks)

    for i, (raw, dec, valid) in enumerate(b_results):
        if not valid or not dec:
            b_picks.append("invalid")
            b_details.append({"raw": raw[:200]})
            continue
        action = dec.get("action", "")
        idx = dec.get("option_index", "?")
        if "alternative" in action:
            b_picks.append("skip")
        else:
            b_picks.append(idx)
        b_details.append({
            "pick": CARD_NAMES.get(idx, f"index={idx}"),
            "reasoning": dec.get("reasoning", "")[:150],
            "strategic_note": dec.get("strategic_note", "")[:100],
        })

    # ── Report ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("KNIFE TRAP A/B TEST RESULTS")
    print(f"{'='*60}")
    print(f"Scenario: Floor 7, Knife Trap (Rare) vs Leg Sweep (Uncommon) vs Dagger Throw (Common)")
    print(f"Deck has: Blade Dance (Shiv generator), Ricochet (Sly), Skewer++")
    print(f"Model: {model}, {n} samples per variant")

    # Variant A
    print(f"\n--- Variant A: Original prompt (Boss Damage Check only) ---")
    a_counts: dict[str, int] = {}
    for p in a_picks:
        name = CARD_NAMES.get(p, str(p))
        a_counts[name] = a_counts.get(name, 0) + 1
    for name, cnt in sorted(a_counts.items(), key=lambda x: -x[1]):
        print(f"  {name}: {cnt}/{n} ({cnt/n*100:.0f}%)")
    for i, d in enumerate(a_details):
        pick = d.get("pick", "?")
        reason = d.get("reasoning", d.get("raw", "?"))
        print(f"  [{i+1}] {pick}: {reason}")

    # Variant B
    print(f"\n--- Variant B: Patched prompt (+Build Trajectory Check) ---")
    b_counts: dict[str, int] = {}
    for p in b_picks:
        name = CARD_NAMES.get(p, str(p))
        b_counts[name] = b_counts.get(name, 0) + 1
    for name, cnt in sorted(b_counts.items(), key=lambda x: -x[1]):
        print(f"  {name}: {cnt}/{n} ({cnt/n*100:.0f}%)")
    for i, d in enumerate(b_details):
        pick = d.get("pick", "?")
        reason = d.get("reasoning", d.get("raw", "?"))
        print(f"  [{i+1}] {pick}: {reason}")

    # Comparison
    print(f"\n--- Comparison ---")
    kt_a = a_counts.get("Knife Trap", 0)
    kt_b = b_counts.get("Knife Trap", 0)
    dt_a = a_counts.get("Dagger Throw", 0)
    dt_b = b_counts.get("Dagger Throw", 0)
    print(f"  Knife Trap:   A={kt_a}/{n} → B={kt_b}/{n}  {'↑' if kt_b > kt_a else '↓' if kt_b < kt_a else '='}")
    print(f"  Dagger Throw: A={dt_a}/{n} → B={dt_b}/{n}  {'↑' if dt_b > dt_a else '↓' if dt_b < dt_a else '='}")

    if kt_b > kt_a:
        print(f"\n  RESULT: Patch IMPROVED Knife Trap selection (+{kt_b - kt_a} picks)")
    elif kt_b == kt_a:
        print(f"\n  RESULT: No change in Knife Trap selection rate")
    else:
        print(f"\n  RESULT: Patch REDUCED Knife Trap selection (-{kt_a - kt_b} picks)")

    # Save
    out_path = paths.ab_test_results_dir() / f"knife_trap_{int(time.time())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "scenario": "knife_trap_vs_dagger_throw_floor7",
        "model": model, "samples": n,
        "variant_a": {"picks": [str(p) for p in a_picks], "counts": a_counts, "details": a_details},
        "variant_b": {"picks": [str(p) for p in b_picks], "counts": b_counts, "details": b_details},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
