"""Replay the Hidden Gem shop decision (run_20260417_050958, line 8118)
with and without a deeper-thinking directive to see whether the agent
still skips Hidden Gem.

The original run (Gemini 3.1 Pro, strategic tier) skipped Hidden Gem
at 178g with the reason "deck too large (24 cards), too RNG-dependent".
Hidden Gem grants Replay 2 on a random Draw Pile card, which in a
Silent poison build containing Noxious Fumes++ / Accelerant++ / Deadly
Poison is potentially very strong.

Two variants:
  - original: logged system + user prompt, strategic effort=medium (same as run).
  - deep   : appends a directive requiring per-item concrete simulation
             for every rare card, then calls with effort=high.

Usage:
    python -m scripts.test_hidden_gem_shop_ab --runs 3 --log logs/run_20260417_050958_0d6882de.jsonl --line 8118
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from src.brain.prompts._keyword_fmt import KW_GLOSSARY  # noqa: E402
from src.brain.v2_backend import V2Backend  # noqa: E402


DEEP_DIRECTIVE = """

## Deep-Analysis Override (AB test)
Before outputting the <decision>, you MUST:
1. List EVERY affordable item. For each rare card or relic, simulate
   its concrete effect in this specific deck:
   - Name the exact cards it interacts with in our current deckbuild.
   - Estimate the expected value (damage/block/poison/draw) gained
     per fight, given our current relics and archetype.
   - State explicitly whether its variance is acceptable given our
     win condition.
2. For Hidden Gem specifically: enumerate which cards in our Draw Pile
   are the BEST Replay 2 targets, the probability of hitting one,
   and the concrete poison/damage/block output if we hit each. Then
   compare this expected value to the 178g cost and to the next-best
   purchase at that price tier.
3. Only after that enumeration, output the final <decision> block.
   The reasoning field should reflect the simulation, not vibes.
"""


def load_record(log_path: Path, line_no: int) -> dict:
    with open(log_path, "r", encoding="utf-8") as f:
        for i, raw in enumerate(f, 1):
            if i == line_no:
                return json.loads(raw)
    raise RuntimeError(f"line {line_no} not found in {log_path}")


def extract_user_text(messages: list[dict]) -> str:
    m0 = messages[0]
    c = m0["content"]
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(p.get("text", "") for p in c if isinstance(p, dict))
    raise RuntimeError("unexpected message content shape")


def refresh_glossary(user_text: str, keyword: str) -> tuple[str, bool]:
    """Replace an old glossary line with the current KW_GLOSSARY entry.

    The logged user_text contains the glossary line as it existed at log time.
    To test a glossary wording change without rebuilding the full prompt, we
    swap the logged bullet for the current value from KW_GLOSSARY.
    Returns (new_text, replaced).
    """
    current = KW_GLOSSARY.get(keyword.lower())
    if not current:
        return user_text, False
    needle_prefix = f"- {keyword[:1].upper()}{keyword[1:].lower()} N:"
    lines = user_text.splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(needle_prefix):
            new_line = f"- {current}"
            if ln == new_line:
                return user_text, False
            lines[i] = new_line
            return "\n".join(lines), True
    return user_text, False


def parse_decision(text: str) -> dict | None:
    m = re.search(r"<decision>\s*(\{.*?\})\s*</decision>", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def hidden_gem_verdict(decision: dict | None) -> str:
    if decision is None:
        return "UNPARSED"
    for p in decision.get("purchases", []) or []:
        if "hidden gem" in str(p.get("item_name", "")).lower():
            return "BOUGHT"
    for s in decision.get("skipped_items", []) or []:
        if "hidden gem" in str(s.get("item_name", "")).lower():
            return "SKIPPED"
    return "NOT_MENTIONED"


def hidden_gem_reason(decision: dict | None) -> str:
    if decision is None:
        return ""
    for p in decision.get("purchases", []) or []:
        if "hidden gem" in str(p.get("item_name", "")).lower():
            return p.get("reason", "")
    for s in decision.get("skipped_items", []) or []:
        if "hidden gem" in str(s.get("item_name", "")).lower():
            return s.get("reason", "")
    return ""


def run_variant(
    backend: V2Backend,
    system: str,
    user_text: str,
    *,
    model: str,
    provider: str,
    effort: str,
    variant: str,
) -> dict:
    messages = [{"role": "user", "content": user_text}]
    t0 = time.monotonic()
    resp = backend.call(
        system=system,
        messages=messages,
        provider=provider,
        model=model,
        think=True,
        effort=effort,
        tools=None,
        max_tokens=8192,
        openai_relay_profile="default",
    )
    latency_ms = (time.monotonic() - t0) * 1000

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in resp.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
        elif btype == "thinking":
            thinking_parts.append(getattr(block, "thinking", "") or "")
    full_text = "\n".join(text_parts)
    decision = parse_decision(full_text)
    return {
        "variant": variant,
        "latency_ms": round(latency_ms, 1),
        "stop_reason": resp.stop_reason,
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "text": full_text,
        "thinking": "\n".join(thinking_parts),
        "decision": decision,
        "hidden_gem": hidden_gem_verdict(decision),
        "hidden_gem_reason": hidden_gem_reason(decision),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AB-test Hidden Gem shop decision")
    parser.add_argument("--log", default="logs/run_20260417_050958_0d6882de.jsonl")
    parser.add_argument("--line", type=int, default=8118)
    parser.add_argument("--runs", type=int, default=3, help="Runs per variant")
    parser.add_argument(
        "--variants",
        default="original,deep",
        help="Comma-separated variants to run",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override model (defaults to logged model)",
    )
    parser.add_argument(
        "--provider",
        default="openai_compatible",
        help="Backend provider (default: openai_compatible)",
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.is_absolute():
        log_path = ROOT / log_path
    rec = load_record(log_path, args.line)
    system = rec.get("system_prompt") or ""
    user_text = extract_user_text(rec.get("messages") or [])
    user_text, replay_swapped = refresh_glossary(user_text, "replay")
    logged_model = rec.get("model") or "gemini-3.1-pro-preview"
    model = args.model or logged_model

    print("=== Hidden Gem Shop AB Test ===")
    print(f"Log: {log_path.name} line {args.line}")
    print(f"Model: {model}  Provider: {args.provider}")
    print(f"Logged tier: {rec.get('tier')}  think_budget: {rec.get('think_budget')}")
    print(f"Original verdict: SKIPPED (178g Hidden Gem, deck-size excuse)")
    print(f"Replay glossary refreshed: {replay_swapped}")
    print(f"User message: {len(user_text)} chars   System: {len(system)} chars")
    print()

    backend = V2Backend()
    variants = [v.strip() for v in args.variants.split(",") if v.strip()]
    all_results: list[dict] = []

    for variant in variants:
        if variant == "original":
            effort = "medium"
            prompt_text = user_text
        elif variant == "deep":
            effort = "high"
            prompt_text = user_text + DEEP_DIRECTIVE
        elif variant == "prompt_only":
            effort = "medium"
            prompt_text = user_text + DEEP_DIRECTIVE
        elif variant == "effort_only":
            effort = "high"
            prompt_text = user_text
        else:
            print(f"Unknown variant {variant!r}, skipping.")
            continue

        print(f"--- Variant: {variant}  (effort={effort}) ---")
        for i in range(args.runs):
            try:
                r = run_variant(
                    backend,
                    system,
                    prompt_text,
                    model=model,
                    provider=args.provider,
                    effort=effort,
                    variant=variant,
                )
            except Exception as e:
                print(f"  run {i+1}: ERROR {type(e).__name__}: {e}")
                all_results.append({"variant": variant, "error": str(e)})
                continue
            all_results.append(r)
            hg = r["hidden_gem"]
            reason = (r["hidden_gem_reason"] or "")[:200]
            dec = r["decision"] or {}
            purchases = dec.get("purchases") or []
            purchased_names = [p.get("item_name") for p in purchases]
            print(
                f"  run {i+1}: hidden_gem={hg}  "
                f"out_tok={r['output_tokens']}  lat={r['latency_ms']:.0f}ms"
            )
            print(f"         purchases: {purchased_names}")
            if reason:
                print(f"         hidden_gem_reason: {reason}")
            if r["thinking"]:
                print(f"         thinking_len: {len(r['thinking'])}")
        print()

    # Summary
    print("=== Summary ===")
    from collections import Counter
    per_variant: dict[str, Counter] = {}
    for r in all_results:
        v = r.get("variant", "?")
        hg = r.get("hidden_gem", "ERROR") if "error" not in r else "ERROR"
        per_variant.setdefault(v, Counter())[hg] += 1
    for v, c in per_variant.items():
        print(f"  {v}: {dict(c)}")

    # Save full output
    out_path = ROOT / "data" / "hidden_gem_ab_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nFull output: {out_path}")


if __name__ == "__main__":
    main()
