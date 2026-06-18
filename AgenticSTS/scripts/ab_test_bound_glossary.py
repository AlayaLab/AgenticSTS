"""A/B test: does adding the 'Bound' keyword explanation to combat prompts
prevent the model from planning 2+ Bound cards in one turn?

Scenario: Round 9 Queen boss fight (log run_20260418_161738_0781b4e5.jsonl).
Hand has 3 Bound cards (Piercing Wail, Neutralize++, Knife Trap).
Only 1 Bound card can be played per turn — playing more is wasted energy.

Usage:
    python -m scripts.ab_test_bound_glossary [--samples N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src.brain.v2_backend import V2Backend  # noqa: E402
from src.brain.decision_parser import extract_decision  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LOG_FILE = "run_20260418_161738_0781b4e5.jsonl"
ROUND_MARKER = "Round 9 State"
BOUND_CARDS = {"Piercing Wail", "Neutralize", "Knife Trap"}  # matched with startswith after '+' strip

# Patch target: inject Bound definition into the "## Key Effects" section.
OLD_KEY_EFFECTS_ANCHOR = "- Frail: Block from cards reduced by 25%."
BOUND_LINE = (
    "- Bound: Only 1 Bound card can be played each turn. "
    "Cards are un-Bound at end of turn. Applied by Chains of Binding to the first N drawn cards."
)


def find_target(log_path: Path) -> dict | None:
    for line in log_path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except Exception:
            continue
        if e.get("event") != "llm_call":
            continue
        p = e.get("prompt", "")
        if "Knife Trap" in p and ROUND_MARKER in p and "Chains of Binding" in p:
            return e
    return None


def patch_text(text: str) -> str:
    if OLD_KEY_EFFECTS_ANCHOR not in text:
        return text
    return text.replace(
        OLD_KEY_EFFECTS_ANCHOR,
        OLD_KEY_EFFECTS_ANCHOR + "\n" + BOUND_LINE,
    )


def patch_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        nm = dict(m)
        c = m.get("content", "")
        if isinstance(c, str):
            nm["content"] = patch_text(c)
        elif isinstance(c, list):
            new_blocks = []
            for b in c:
                if isinstance(b, dict) and isinstance(b.get("text"), str):
                    nb = dict(b)
                    nb["text"] = patch_text(b["text"])
                    new_blocks.append(nb)
                else:
                    new_blocks.append(b)
            nm["content"] = new_blocks
        out.append(nm)
    return out


def count_bound_in_plan(decision: dict | None) -> tuple[int, list[str]]:
    if not decision:
        return -1, []
    plan = decision.get("plan", [])
    bound_cards_played: list[str] = []
    for step in plan:
        if not isinstance(step, dict) or step.get("type") != "card":
            continue
        card_name = (step.get("card") or "").rstrip("+")
        if any(card_name.startswith(b) for b in BOUND_CARDS):
            bound_cards_played.append(step.get("card") or "")
    return len(bound_cards_played), bound_cards_played


async def call_once(backend: V2Backend, system: str, messages: list[dict], model: str, provider: str):
    try:
        resp = await backend.acall(
            system=system,
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=3000,
        )
        text = V2Backend.extract_text(resp)
        dec = extract_decision(text, allow_fallback=True) if text else None
        return text, dec
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "", None


async def run_variant(name: str, n: int, backend, system, messages, model, provider):
    print(f"\n[Variant {name}] running {n} samples...")
    tasks = [call_once(backend, system, messages, model, provider) for _ in range(n)]
    results = await asyncio.gather(*tasks)
    stats = {"ok": 0, "bound_le_1": 0, "bound_ge_2": 0, "invalid": 0, "samples": []}
    for i, (raw, dec) in enumerate(results):
        cnt, names = count_bound_in_plan(dec)
        if cnt < 0:
            stats["invalid"] += 1
            stats["samples"].append({"i": i, "status": "invalid", "raw": raw[:200]})
            continue
        stats["ok"] += 1
        if cnt >= 2:
            stats["bound_ge_2"] += 1
        else:
            stats["bound_le_1"] += 1
        stats["samples"].append({
            "i": i, "bound_count": cnt, "bound_cards": names,
            "reasoning": (dec or {}).get("reasoning", "")[:140],
        })
    return stats


def print_report(name: str, s: dict):
    total = s["ok"] + s["invalid"]
    print(f"\n=== Variant {name} ===")
    print(f"  ok={s['ok']} invalid={s['invalid']} total={total}")
    if s["ok"]:
        print(f"  plans with >=2 Bound: {s['bound_ge_2']}/{s['ok']} ({100*s['bound_ge_2']/s['ok']:.0f}%)")
        print(f"  plans with <=1 Bound: {s['bound_le_1']}/{s['ok']} ({100*s['bound_le_1']/s['ok']:.0f}%)")
    for smp in s["samples"]:
        if smp.get("status") == "invalid":
            print(f"  [{smp['i']}] INVALID: {smp['raw'][:100]}")
        else:
            print(f"  [{smp['i']}] bound={smp['bound_count']} cards={smp['bound_cards']} :: {smp['reasoning']}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    model = args.model or config.LLM_STRATEGIC_MODEL
    provider = config.get_tier_provider("strategic")
    print(f"Model: {model} (provider: {provider})  samples={args.samples}")

    log_path = Path(config.LOG_DIR) / LOG_FILE
    entry = find_target(log_path)
    if not entry:
        print(f"ERROR: target not found in {log_path}")
        return

    system_prompt = entry.get("system_prompt") or ""
    messages = entry.get("messages") or []

    # Sanity: confirm Bound appears in prompt but no explanation does.
    joined = system_prompt + " " + " ".join(
        (m.get("content", "") if isinstance(m.get("content"), str)
         else " ".join(b.get("text", "") for b in m.get("content", []) if isinstance(b, dict)))
        for m in messages
    )
    assert "Bound" in joined, "prompt missing Bound — wrong entry?"
    assert "Only 1 Bound card" not in joined, "Bound already explained — wrong baseline"

    patched_system = patch_text(system_prompt)
    patched_messages = patch_messages(messages)
    patched_joined = patched_system + " " + " ".join(
        (m.get("content", "") if isinstance(m.get("content"), str)
         else " ".join(b.get("text", "") for b in m.get("content", []) if isinstance(b, dict)))
        for m in patched_messages
    )
    assert "Only 1 Bound card" in patched_joined, "patch did not apply — anchor missing"
    print("patch anchor OK; Bound explanation present in variant B.")

    backend = V2Backend()
    a = await run_variant("A (original)", args.samples, backend, system_prompt, messages, model, provider)
    b = await run_variant("B (+Bound gloss)", args.samples, backend, patched_system, patched_messages, model, provider)
    print_report("A (original)", a)
    print_report("B (+Bound gloss)", b)

    print("\n=== SUMMARY ===")
    if a["ok"] and b["ok"]:
        ra = a["bound_ge_2"] / a["ok"]
        rb = b["bound_ge_2"] / b["ok"]
        print(f"  >=2 Bound rate:  A={ra:.0%}   B={rb:.0%}   delta={rb-ra:+.0%}")


if __name__ == "__main__":
    asyncio.run(main())
