"""A/B test: does adding an explicit Ethereal-Status/Curse rule to the discard
hint prevent the model from discarding Ascender's Bane (and similar)?

Scenario: hand_select (Discard 2) at log idx=10001 of
run_20260502_094730_03580e82.jsonl. Hand contains [index=7] Ascender's Bane
(Curse, Unplayable, Ethereal, Eternal). Discarding it puts it back in the
discard pile — the model could re-draw it. Letting it auto-exhaust at end of
turn removes it permanently for the rest of combat.

Usage:
    python -m scripts.ab_test_ethereal_discard [--samples N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402
from src.brain.v2_backend import V2Backend  # noqa: E402
from src.brain.decision_parser import extract_decision  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

LOG_FILE = "run_20260502_094730_03580e82.jsonl"
TARGET_LINE_INDEX = 10001  # 0-based line in JSONL

# Patch target inside the user message. The current source line is:
OLD_DISCARD_HINT = "Discard = temporary (you'll draw them again)."
# Replace with the new line that scopes the rule to Ethereal Status/Curse:
NEW_DISCARD_HINT = (
    "Discard = temporary (you'll draw them again). "
    "If an Ethereal Status or Curse card has no harmful effect while held "
    "(e.g. Ascender's Bane), DO NOT discard it — let it auto-exhaust at end of "
    "turn so it's permanently gone this combat instead of being reshuffled "
    "into the draw pile."
)


def patch_text(text: str) -> str:
    if OLD_DISCARD_HINT not in text:
        return text
    return text.replace(OLD_DISCARD_HINT, NEW_DISCARD_HINT, 1)


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


def find_ascender_index(text: str) -> int | None:
    m = re.search(r"\[index=(\d+)\] Ascender", text)
    return int(m.group(1)) if m else None


def selected_indices(decision: dict | None) -> list[int]:
    if not decision:
        return []
    raw = decision.get("selected_indices") or []
    out: list[int] = []
    for v in raw:
        try:
            out.append(int(v))
        except Exception:
            pass
    return out


async def call_once(backend: V2Backend, system: str, messages: list[dict], model: str, provider: str):
    try:
        resp = await backend.acall(
            system=system,
            messages=messages,
            provider=provider,
            model=model,
            max_tokens=8000,
        )
        text = V2Backend.extract_text(resp)
        dec = extract_decision(text, allow_fallback=True) if text else None
        return text, dec
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
        return "", None


async def run_variant(
    name: str,
    n: int,
    backend,
    system,
    messages,
    model,
    provider,
    ascender_idx: int,
):
    print(f"\n[Variant {name}] running {n} samples in parallel...")
    tasks = [call_once(backend, system, messages, model, provider) for _ in range(n)]
    results = await asyncio.gather(*tasks)
    stats = {"ok": 0, "discarded_ascender": 0, "kept_ascender": 0, "invalid": 0, "samples": []}
    for i, (raw, dec) in enumerate(results):
        sel = selected_indices(dec)
        if not sel:
            stats["invalid"] += 1
            stats["samples"].append({"i": i, "status": "invalid", "raw": (raw or "")[:200]})
            continue
        stats["ok"] += 1
        if ascender_idx in sel:
            stats["discarded_ascender"] += 1
        else:
            stats["kept_ascender"] += 1
        stats["samples"].append({
            "i": i,
            "selected": sel,
            "ascender_discarded": ascender_idx in sel,
            "reasoning": (dec or {}).get("reasoning", "")[:200],
        })
    return stats


def print_report(name: str, s: dict):
    total = s["ok"] + s["invalid"]
    print(f"\n=== Variant {name} ===")
    print(f"  ok={s['ok']} invalid={s['invalid']} total={total}")
    if s["ok"]:
        print(f"  discarded Ascender:  {s['discarded_ascender']}/{s['ok']}")
        print(f"  KEPT Ascender:       {s['kept_ascender']}/{s['ok']}")
    for smp in s["samples"]:
        if smp.get("status") == "invalid":
            print(f"  [{smp['i']}] INVALID: {smp['raw'][:120]}")
        else:
            mark = "DISCARD" if smp["ascender_discarded"] else "kept   "
            print(f"  [{smp['i']}] {mark} sel={smp['selected']} :: {smp['reasoning'][:140]}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--model", default="")
    args = parser.parse_args()

    model = args.model or config.LLM_FAST_MODEL
    provider = config.get_tier_provider("fast")
    print(f"Model: {model} (provider: {provider})  samples per variant = {args.samples}")

    log_path = Path(config.LOG_DIR) / LOG_FILE
    with log_path.open(encoding="utf-8") as f:
        lines = f.readlines()
    entry = json.loads(lines[TARGET_LINE_INDEX])

    system_prompt = entry.get("system_prompt") or ""
    messages = entry.get("messages") or []

    joined = system_prompt + " " + " ".join(
        (m.get("content", "") if isinstance(m.get("content"), str)
         else " ".join(b.get("text", "") for b in m.get("content", []) if isinstance(b, dict)))
        for m in messages
    )
    ascender_idx = find_ascender_index(joined)
    if ascender_idx is None:
        print("ERROR: Ascender's Bane not found in target prompt")
        return
    assert OLD_DISCARD_HINT in joined, "baseline missing old discard hint — wrong entry?"
    print(f"Target: log line {TARGET_LINE_INDEX}, Ascender's Bane at index={ascender_idx}")

    patched_system = patch_text(system_prompt)
    patched_messages = patch_messages(messages)
    patched_joined = patched_system + " " + " ".join(
        (m.get("content", "") if isinstance(m.get("content"), str)
         else " ".join(b.get("text", "") for b in m.get("content", []) if isinstance(b, dict)))
        for m in patched_messages
    )
    assert "DO NOT discard it" in patched_joined, "patch did not apply — anchor missing"
    print("patch anchor OK; new Ethereal-Status/Curse rule present in variant B.")

    backend = V2Backend()
    a_task = run_variant("A (baseline)", args.samples, backend, system_prompt, messages, model, provider, ascender_idx)
    b_task = run_variant("B (+ethereal rule)", args.samples, backend, patched_system, patched_messages, model, provider, ascender_idx)
    a, b = await asyncio.gather(a_task, b_task)
    print_report("A (baseline)", a)
    print_report("B (+ethereal rule)", b)

    print("\n=== SUMMARY ===")
    if a["ok"] and b["ok"]:
        ra = a["discarded_ascender"] / a["ok"]
        rb = b["discarded_ascender"] / b["ok"]
        print(f"  Ascender-discard rate:  A={ra:.0%}   B={rb:.0%}   delta={rb-ra:+.0%}")


if __name__ == "__main__":
    asyncio.run(main())
