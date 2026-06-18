"""Smoke test for the health-aware LLM router.

Sends one real LLM call per call_class through a relay to verify:
  - Success / failure / 0tok
  - First-chunk latency
  - Total latency
  - Whether the response can be parsed
  - Whether fallback was triggered
  - Whether circuit breaker state changed

Usage:
    python -m scripts.smoke_router           # run all call classes
    python -m scripts.smoke_router --class gameplay_fast  # single class
    python -m scripts.smoke_router --verbose  # show raw response previews
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time

# Ensure project root is on the path
sys.path.insert(0, ".")

import config
from src.brain.llm_router import (
    FailureType,
    classify_failure,
    get_router,
    relay_profile_for_call_class,
    reset_router,
)

logging.basicConfig(
    level=logging.WARNING,
    format="%(name)s: %(message)s",
)
logger = logging.getLogger("smoke_router")
logger.setLevel(logging.INFO)


# ── Test prompts per call class ────────────────────────────────

_PROMPTS: dict[str, dict] = {
    "gameplay_fast": {
        "system": "You are a game AI. Respond with a JSON decision.",
        "prompt": (
            "The player is at a map node. Available options:\n"
            "0: Monster (floor 3)\n1: Event (floor 3)\n2: Elite (floor 3)\n\n"
            "Pick the safest option. Respond ONLY with:\n"
            '<decision>{"action":"choose_map_node","option_index":0,"reasoning":"safest"}</decision>'
        ),
        "think": False,
    },
    "gameplay_strategic": {
        "system": "You are a game AI. Respond with a JSON combat plan.",
        "prompt": (
            "Combat round 1. Player HP 60/72, Energy 3/3.\n"
            "Hand: Strike (1E, 6dmg), Defend (1E, 5blk), Bash (2E, 8dmg+Vulnerable).\n"
            "Enemy: Jaw Worm HP 42/42, Intent: 11 damage.\n\n"
            "Plan your turn. Respond ONLY with:\n"
            '<decision>{"play_sequence":["Defend","Strike"],"reasoning":"block first"}</decision>'
        ),
        "think": True,
        "effort": "medium",
    },
    "postrun_analysis": {
        "system": "You are a game analysis AI. Provide strategic insight.",
        "prompt": (
            "The player lost a run on floor 12 to an elite (Lagavulin). "
            "They had 35 HP going in and took 28 damage in 4 rounds. "
            "Deck was heavy on attacks with no AoE. "
            "Summarize the key mistake in 1-2 sentences."
        ),
        "think": True,
        "effort": "medium",
    },
    "postrun_summary": {
        "system": "You are a concise game summarizer.",
        "prompt": (
            "Summarize this combat reasoning in 1 sentence:\n\n"
            "The player should play Defend first because the enemy "
            "intends to attack for 11 damage. Then play Strike for 6 damage. "
            "Save Bash for when Vulnerable can be applied before a big attack turn."
        ),
        "think": False,
    },
    "evolution": {
        "system": "You are a self-evolving game agent. Analyze and improve.",
        "prompt": (
            "After reviewing the run, what is ONE concrete improvement "
            "the agent should make? The agent lost because it never blocked "
            "against a 15-damage attack when it had Defend in hand. "
            "Respond in 2-3 sentences."
        ),
        "think": True,
        "effort": "high",
    },
    "monitor_summary": {
        "system": "You are a concise game AI summarizer.",
        "prompt": (
            "Summarize this decision: Played Defend for 5 block against "
            "11 incoming damage, then Strike for 6 damage. Energy used: 2/3."
        ),
        "think": False,
    },
}


# ── Run one smoke test ─────────────────────────────────────────

async def _smoke_one(
    call_class: str,
    verbose: bool = False,
) -> dict:
    """Run one smoke test for a call_class. Returns result dict."""
    from src.brain.v2_backend import V2Backend

    spec = _PROMPTS.get(call_class)
    if spec is None:
        return {"call_class": call_class, "status": "skipped", "reason": "no prompt defined"}

    router = get_router()
    selection = router.select_model(call_class)
    relay_profile = relay_profile_for_call_class(call_class)

    result: dict = {
        "call_class": call_class,
        "model": selection.model,
        "provider": selection.provider,
        "relay_profile": relay_profile,
        "is_probe": selection.is_probe,
    }

    backend = V2Backend()
    messages = [{"role": "user", "content": spec["prompt"]}]
    think = spec.get("think", False)
    effort = spec.get("effort", "")

    t0 = time.monotonic()
    first_chunk_time: float | None = None

    def _on_first_chunk(meta: dict) -> None:
        nonlocal first_chunk_time
        if first_chunk_time is None:
            first_chunk_time = time.monotonic()

    try:
        response = await backend.acall(
            system=spec["system"],
            messages=messages,
            provider=selection.provider,
            model=selection.model,
            think=think,
            effort=effort if think else "",
            on_first_chunk=_on_first_chunk,
            openai_relay_profile=relay_profile,
            allow_hedge=False,  # no hedge for smoke test — measure real latency
        )
        total_ms = (time.monotonic() - t0) * 1000
        first_chunk_ms = (
            (first_chunk_time - t0) * 1000 if first_chunk_time else total_ms
        )

        # Extract text
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text

        usage = getattr(response, "usage", None)
        input_tok = (getattr(usage, "input_tokens", 0) or 0) if usage else 0
        output_tok = (getattr(usage, "output_tokens", 0) or 0) if usage else 0
        total_tok = input_tok + output_tok
        stop_reason = getattr(response, "stop_reason", "") or ""

        # Check for 0tok / empty response
        is_empty = not text.strip() and total_tok == 0
        has_decision = "<decision>" in text.lower() if text else False

        result.update({
            "status": "empty_0tok" if is_empty else "ok",
            "first_chunk_ms": round(first_chunk_ms, 1),
            "total_ms": round(total_ms, 1),
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "stop_reason": stop_reason,
            "has_decision_tag": has_decision,
            "response_len": len(text),
            "fallback_triggered": False,
            "circuit_opened": False,
        })

        if is_empty:
            router.report_failure(
                call_class, selection.provider, selection.model,
                FailureType.HARD, error="empty_0tok",
            )
            result["circuit_opened"] = True
        else:
            router.report_success(call_class, selection.provider, selection.model)

        if verbose and text:
            result["response_preview"] = text[:300]

    except Exception as exc:
        total_ms = (time.monotonic() - t0) * 1000
        ft = classify_failure(exc)
        router.report_failure(
            call_class, selection.provider, selection.model,
            ft, error=str(exc)[:200],
        )

        result.update({
            "status": f"error_{ft.value}",
            "total_ms": round(total_ms, 1),
            "error": str(exc)[:300],
            "fallback_triggered": False,
            "circuit_opened": ft == FailureType.HARD,
        })

    return result


# ── Main ───────────────────────────────────────────────────────

async def main(args: argparse.Namespace) -> None:
    reset_router()
    router = get_router()

    if args.call_class:
        classes = [args.call_class]
    else:
        classes = list(_PROMPTS.keys())

    results: list[dict] = []
    for cc in classes:
        logger.info("Testing %s ...", cc)
        r = await _smoke_one(cc, verbose=args.verbose)
        results.append(r)
        status = r["status"]
        model = r.get("model", "?")
        ms = r.get("total_ms", 0)
        fc_ms = r.get("first_chunk_ms", "")
        tok = r.get("output_tokens", 0)
        fc_str = f"  first_chunk={fc_ms}ms" if fc_ms else ""
        logger.info(
            "  %s: %s  model=%s  %.0fms  %dtok%s",
            cc, status, model, ms, tok, fc_str,
        )
        if r.get("error"):
            logger.warning("  ERROR: %s", r["error"][:200])

    # ── Summary ──
    print("\n" + "=" * 80)
    print("SMOKE TEST SUMMARY")
    print("=" * 80)
    ok = sum(1 for r in results if r["status"] == "ok")
    total = len(results)
    print(f"\nPassed: {ok}/{total}")

    print(f"\n{'Call Class':<25} {'Model':<25} {'Status':<12} {'Total ms':>10} {'1st Chunk':>10} {'Tokens':>8}")
    print("-" * 95)
    for r in results:
        fc = r.get("first_chunk_ms", "")
        fc_str = f"{fc}" if fc else "-"
        tok = r.get("output_tokens", 0)
        print(
            f"{r['call_class']:<25} {r.get('model','?'):<25} {r['status']:<12} "
            f"{r.get('total_ms',0):>10.0f} {fc_str:>10} {tok:>8}"
        )

    # Router health after smoke
    health = router.get_health_snapshot()
    if health:
        print(f"\n{'Model Health Key':<50} {'State':<12} {'Hard Fails':>10} {'Successes':>10}")
        print("-" * 85)
        for key, h in health.items():
            print(
                f"{key:<50} {h['state']:<12} {h['total_hard_fails']:>10} {h['total_successes']:>10}"
            )

    stats = router.get_stats()
    print(f"\nRouter stats: {stats}")

    # Return exit code
    if ok < total:
        print(f"\n⚠  {total - ok} call class(es) failed")
        sys.exit(1)
    else:
        print("\n✓  All call classes passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smoke test the LLM router")
    parser.add_argument("--class", dest="call_class", help="Test single call class")
    parser.add_argument("--verbose", action="store_true", help="Show response previews")
    args = parser.parse_args()
    asyncio.run(main(args))
