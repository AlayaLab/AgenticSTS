"""Focused A/B test: Nightmare (bad Rare) vs Dagger Throw scenario.

Tests whether the Build Trajectory Check v1 causes the model to blindly pick
Rare cards even when they don't fit the build. Uses the same Floor 7 game state
but swaps Knife Trap → Nightmare (3-cost, doesn't synergize with Shiv deck).

Usage:
    python -m scripts.ab_test_nightmare [--samples N]
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

# ── Patch (v1 full version) ──────────────────────────────────

OLD_TEXT = "SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one."

NEW_TEXT = """\
SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one.

## Build Trajectory Check
Before choosing based on current DPS alone, also consider:
1. **Archetype commitment**: What archetype is your deck building toward? (Check your Strategic Thread / build plan)
2. **Rarity matters**: Rare cards may never appear again this run — weigh rarity heavily over small immediate DPS gains
3. **Scaling > flat**: Cards that SCALE with future picks (e.g., Knife Trap improves with every Shiv generator added later) beat cards with flat immediate value (e.g., Dagger Throw's fixed 9 damage never grows)
4. **Common cards recur**: Common cards will be offered again — don't take a Common over a Rare that fits your build direction
5. **Draft for trajectory**: If the guide recommends an archetype and you've started building it (e.g., you have Blade Dance → Shiv archetype), draft key build-around cards for that trajectory even if current DPS seems low"""

# ── Card swap: Knife Trap → Nightmare ────────────────────────

KNIFE_TRAP_LINE = "- [index=0] Knife Trap (2E, Skill, Rare): Play every Shiv in your Exhaust Pile on the enemy."
NIGHTMARE_LINE = "- [index=0] Nightmare (3E, Skill, Rare): Choose a card. Next turn, add 3 copies of that card into your Hand."

# Also swap card experience notes
KNIFE_TRAP_NOTE = "- knife trap: Replays EVERY Shiv in Exhaust Pile for free. Burst finisher after Blade Dance or Cloak and Dagger exhaust Shivs. With Accuracy, each replayed Shiv deals 4+N×4 damage. Upgrade is significant. Requires Shiv generators to have value — does nothing without exhausted Shivs."
NIGHTMARE_NOTE = "- nightmare: 3-cost Rare that copies a card 3 times into next turn's hand. Extremely expensive at 3 energy. Requires a high-value target card and a turn where you can afford to spend 3 energy doing nothing. Best with 0-cost cards or powerful scaling effects. In a Shiv deck, there are no good copy targets — Shivs exhaust and Blade Dance already exhausts."

# Swap in skill retrieval too
KNIFE_TRAP_SKILL_REF = "Knife Trap"


def swap_to_nightmare(text: str) -> str:
    """Replace Knife Trap with Nightmare in prompt text."""
    result = text
    result = result.replace(KNIFE_TRAP_LINE, NIGHTMARE_LINE)
    result = result.replace(KNIFE_TRAP_NOTE, NIGHTMARE_NOTE)
    # Also replace any remaining "Knife Trap" mentions in card notes / skills
    # but be careful not to break the patch text itself
    return result


def apply_patch(text: str) -> str:
    return text.replace(OLD_TEXT, NEW_TEXT)


def apply_to_messages(messages: list[dict], transform) -> list[dict]:
    patched = []
    for msg in messages:
        new_msg = dict(msg)
        content = msg.get("content", "")
        if isinstance(content, str):
            new_msg["content"] = transform(content)
        patched.append(new_msg)
    return patched


# ── Find base case ───────────────────────────────────────────

def find_knife_trap_case(log_dir: Path) -> dict | None:
    target_file = log_dir / "run_20260416_103123_90ed9ed1.jsonl"
    if not target_file.exists():
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
        if "[index=0] Knife Trap" in prompt and "[index=2] Dagger Throw" in prompt:
            return entry
    return None


CARD_NAMES = {0: "Nightmare", 1: "Leg Sweep", 2: "Dagger Throw", "skip": "Skip"}


async def call_llm(
    backend: V2Backend, system: str, messages: list[dict],
    model: str, provider: str,
) -> tuple[str, dict | None, bool]:
    try:
        response = await backend.acall(
            system=system, messages=messages,
            provider=provider, model=model, max_tokens=2000,
        )
        text = V2Backend.extract_text(response)
        decision = extract_decision(text, allow_fallback=True) if text else None
        errors = validate_decision(decision, "card_reward_action") if decision else ["no decision"]
        return text, decision, len(errors) == 0
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "", None, False


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--model", type=str, default="")
    args = parser.parse_args()

    model = args.model or config.LLM_STRATEGIC_MODEL
    provider = config.get_tier_provider("strategic")
    n = args.samples

    print(f"Model: {model} (provider: {provider})")
    print(f"Samples per variant: {n}")
    print(f"Test: Nightmare (bad Rare, 3-cost, no Shiv synergy) vs Dagger Throw (good Common)")

    # Find base case and swap Knife Trap → Nightmare
    entry = find_knife_trap_case(Path(config.LOG_DIR))
    if not entry:
        print("ERROR: Base case not found")
        return

    system_prompt = entry.get("system_prompt", "")
    messages = entry.get("messages", [])
    if not messages:
        messages = [{"role": "user", "content": entry.get("prompt", "")}]

    # Create the Nightmare variant (swap card in prompt)
    nightmare_system = swap_to_nightmare(system_prompt)
    nightmare_messages = apply_to_messages(messages, swap_to_nightmare)

    # Create the patched Nightmare variant (swap card + add trajectory check)
    patched_system = apply_patch(swap_to_nightmare(system_prompt))
    patched_messages = apply_to_messages(messages, lambda t: apply_patch(swap_to_nightmare(t)))

    # Verify swaps
    all_b = patched_system + " ".join(m.get("content", "") for m in patched_messages)
    if "Nightmare (3E" not in all_b:
        print("ERROR: Nightmare swap not applied")
        return
    if "Build Trajectory" not in all_b:
        print("ERROR: Patch not applied")
        return
    if "Knife Trap (2E" in all_b:
        print("WARNING: Knife Trap still in prompt text")

    backend = V2Backend()

    # ── Variant A: Original prompt + Nightmare ───────────────
    print(f"\n{'='*60}")
    print(f"Running Variant A (original prompt, Nightmare instead of Knife Trap) x{n}...")
    a_picks, a_details = [], []
    a_results = await asyncio.gather(*[
        call_llm(backend, nightmare_system, nightmare_messages, model, provider)
        for _ in range(n)
    ])
    for raw, dec, valid in a_results:
        if not valid or not dec:
            a_picks.append("invalid")
            a_details.append({"raw": raw[:200]})
            continue
        action = dec.get("action", "")
        idx = dec.get("option_index", "?")
        a_picks.append("skip" if "alternative" in action else idx)
        a_details.append({
            "pick": CARD_NAMES.get(idx, f"index={idx}"),
            "reasoning": dec.get("reasoning", "")[:200],
        })

    # ── Variant B: Patched prompt + Nightmare ────────────────
    print(f"Running Variant B (patched v1, Nightmare instead of Knife Trap) x{n}...")
    b_picks, b_details = [], []
    b_results = await asyncio.gather(*[
        call_llm(backend, patched_system, patched_messages, model, provider)
        for _ in range(n)
    ])
    for raw, dec, valid in b_results:
        if not valid or not dec:
            b_picks.append("invalid")
            b_details.append({"raw": raw[:200]})
            continue
        action = dec.get("action", "")
        idx = dec.get("option_index", "?")
        b_picks.append("skip" if "alternative" in action else idx)
        b_details.append({
            "pick": CARD_NAMES.get(idx, f"index={idx}"),
            "reasoning": dec.get("reasoning", "")[:200],
        })

    # ── Report ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("NIGHTMARE A/B TEST RESULTS")
    print(f"{'='*60}")
    print(f"Scenario: Floor 7, Nightmare (Rare, BAD) vs Leg Sweep vs Dagger Throw (Common, GOOD)")
    print(f"Key question: Does v1 patch blindly pick Nightmare just because it's Rare?")
    print(f"Expected correct answer: Dagger Throw (Nightmare doesn't fit Shiv build)")

    print(f"\n--- Variant A: Original prompt ---")
    a_counts: dict[str, int] = {}
    for p in a_picks:
        name = CARD_NAMES.get(p, str(p))
        a_counts[name] = a_counts.get(name, 0) + 1
    for name, cnt in sorted(a_counts.items(), key=lambda x: -x[1]):
        print(f"  {name}: {cnt}/{n} ({cnt/n*100:.0f}%)")
    for i, d in enumerate(a_details):
        print(f"  [{i+1}] {d.get('pick','?')}: {d.get('reasoning', d.get('raw','?'))}")

    print(f"\n--- Variant B: Patched v1 (+Build Trajectory + rarity rules) ---")
    b_counts: dict[str, int] = {}
    for p in b_picks:
        name = CARD_NAMES.get(p, str(p))
        b_counts[name] = b_counts.get(name, 0) + 1
    for name, cnt in sorted(b_counts.items(), key=lambda x: -x[1]):
        print(f"  {name}: {cnt}/{n} ({cnt/n*100:.0f}%)")
    for i, d in enumerate(b_details):
        print(f"  [{i+1}] {d.get('pick','?')}: {d.get('reasoning', d.get('raw','?'))}")

    # Comparison
    print(f"\n--- Comparison ---")
    nm_a = a_counts.get("Nightmare", 0)
    nm_b = b_counts.get("Nightmare", 0)
    dt_a = a_counts.get("Dagger Throw", 0)
    dt_b = b_counts.get("Dagger Throw", 0)
    print(f"  Nightmare:    A={nm_a}/{n} → B={nm_b}/{n}  {'↑ BAD' if nm_b > nm_a else '=' if nm_b == nm_a else '↓ GOOD'}")
    print(f"  Dagger Throw: A={dt_a}/{n} → B={dt_b}/{n}")

    if nm_b > nm_a:
        print(f"\n  RESULT: REGRESSION — Patch caused {nm_b - nm_a} false Nightmare picks (rarity bias too strong)")
    elif nm_b == nm_a == 0:
        print(f"\n  RESULT: PASS — Patch correctly rejected bad Rare in both variants")
    else:
        print(f"\n  RESULT: OK — No increase in bad Rare picks")

    out_path = paths.ab_test_results_dir() / f"nightmare_{int(time.time())}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "scenario": "nightmare_bad_rare_vs_dagger_throw",
        "model": model, "samples": n,
        "variant_a": {"picks": [str(p) for p in a_picks], "counts": a_counts, "details": a_details},
        "variant_b": {"picks": [str(p) for p in b_picks], "counts": b_counts, "details": b_details},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
