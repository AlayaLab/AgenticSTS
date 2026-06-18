"""A/B test: compare retain prompt variants on real game scenarios.

Option A (OLD): "keep only a card that is clearly stronger next turn than a fresh draw. It is valid to keep nothing."
Option B (NEW): Retain = extra options, default retain as many as allowed.

Runs N parallel calls per option per case using gemini-3.1-flash-lite-preview.
Evaluates: does the LLM retain cards (good) vs skip (bad)?
For harmful cases: does it correctly skip harmful cards?
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

import httpx

# Manually load .env
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BASE_URL = os.getenv("OPENAI_COMPAT_BASE_URL", "https://proxy.example.com")
API_KEY = os.getenv("OPENAI_COMPAT_API_KEY", "")
MODEL = os.getenv("STS2_FAST_MODEL", "gemini-3.1-flash-lite-preview")
N = 5  # runs per option per case

SYSTEM = "You are a Slay the Spire 2 agent making tactical combat decisions."

DECISION_BLOCK = """\
## Decision Format (hand_select_action)
Valid actions: select_deck_card | confirm_selection
Required fields: action, reasoning
If action=select_deck_card, include selected_indices (array of card indices to retain).
If action=confirm_selection, omit selected_indices (retain nothing).
Response:
<decision>
{"action": "select_deck_card", "selected_indices": [<indices>], "reasoning": "<why>"}
</decision>
or
<decision>
{"action": "confirm_selection", "reasoning": "<why>"}
</decision>
"""

HINT_OLD = (
    'This is a "combat_hand_select" selection. Pick what you need least.\n'
    "Retain choice: keep only a card that is clearly stronger next turn "
    "than a fresh draw. It is valid to keep nothing."
)

HINT_NEW = (
    "Retain = keep cards for next turn. You still draw your normal 5 cards "
    "(hand limit 10), so retained cards are EXTRA options \u2014 not replacements. "
    "Default: retain as many cards as allowed. More retained = more choices next turn. "
    "Do NOT retain: Status cards, Curses, or cards that deal self-damage. "
    "Note: end-of-turn discard does NOT trigger Sly \u2014 only card-effect discards do."
)

_HARMFUL_RE = re.compile(r"lose \d+ HP|take \d+ damage", re.IGNORECASE)


def _is_harmful(card: dict) -> bool:
    ct = card.get("card_type", "")
    rt = card.get("rules_text", "") or ""
    return ct in ("Status", "Curse") or bool(_HARMFUL_RE.search(rt))


def _is_sly(card: dict) -> bool:
    return (card.get("rules_text", "") or "").startswith("Sly.")


def build_scenario(case: dict) -> str:
    """Build the shared scenario body from a test case (without the hint)."""
    cards = case["cards"]
    max_sel = case["max_select"]
    min_sel = case.get("min_select", 0)

    lines = [
        "## Hand Selection (In-Combat)",
        "Mode: combat_hand_select",
        "Prompt: Choose cards to Retain.",
        f"Select: {min_sel} to {max_sel} cards. Return ALL chosen indices in `selected_indices` array.",
    ]

    if min_sel == 0:
        lines.append(
            "You may choose zero cards. If keeping nothing is best, respond with "
            '`{"action":"confirm_selection","reasoning":"..."}`.'
        )

    lines.append(f"HP: {case['hp']}/{case['hp_max']} | Energy: 0 | Block: 0")
    lines.append(f"Context: {case['summary']}")
    lines.append("")
    lines.append("## Cards You Can Select")

    for c in cards:
        up = "+" if c.get("upgraded") else ""
        ct = c.get("card_type", "?")
        cost = c.get("energy_cost", "?")
        rt = c.get("rules_text", "")
        lines.append(f"- [index={c['index']}] {c['name']}{up} ({ct}, cost={cost}): {rt}")

    lines.append("")
    return "\n".join(lines)


def extract_action(text: str) -> dict:
    """Extract action and selected_indices from LLM response."""
    # Try to find decision block
    m = re.search(r"<decision>\s*(\{.*?\})\s*</decision>", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: find JSON-like content
    m = re.search(r'\{[^{}]*"action"[^{}]*\}', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass

    # Check if it mentions confirm_selection
    if "confirm_selection" in text:
        return {"action": "confirm_selection", "selected_indices": []}
    return {"action": "unknown", "selected_indices": []}


async def call_once(
    client: httpx.AsyncClient,
    prompt: str,
    label: str,
    case_id: int,
    run_id: int,
) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 400,
        "temperature": 0.7,
    }
    try:
        resp = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=30.0,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return {"label": label, "case": case_id, "run": run_id, "error": str(e)}

    parsed = extract_action(content)
    action = parsed.get("action", "unknown")
    indices = parsed.get("selected_indices", [])
    if not isinstance(indices, list):
        indices = [indices] if isinstance(indices, int) else []

    return {
        "label": label,
        "case": case_id,
        "run": run_id,
        "action": action,
        "indices": indices,
        "reasoning": parsed.get("reasoning", ""),
        "raw": content,
    }


def evaluate_result(result: dict, case: dict) -> str:
    """Evaluate a single result. Returns 'GOOD', 'BAD', or 'PARTIAL'."""
    if result.get("error"):
        return "ERROR"

    cards = case["cards"]
    max_sel = case["max_select"]
    indices = result.get("indices", [])
    action = result.get("action", "")

    harmful_indices = {c["index"] for c in cards if _is_harmful(c)}
    good_indices = {c["index"] for c in cards if not _is_harmful(c)}

    # If confirm_selection (retain nothing)
    if action == "confirm_selection" or not indices:
        if not good_indices:
            return "GOOD"  # all cards are harmful, correct to skip
        return "BAD"  # had good cards to retain but skipped

    retained = set(indices)

    # Check: did it retain any harmful card?
    retained_harmful = retained & harmful_indices
    if retained_harmful:
        return "BAD"  # retained harmful cards

    # Check: did it retain good cards?
    retained_good = retained & good_indices
    if not retained_good:
        return "BAD"  # retained nothing good

    # Ideal: retain as many good cards as possible (up to max_select)
    max_possible = min(max_sel, len(good_indices))
    if len(retained_good) >= max_possible:
        return "GOOD"  # retained maximum possible good cards
    if len(retained_good) >= 1:
        return "PARTIAL"  # retained some but not max
    return "BAD"


async def main():
    # Load test cases
    cases_path = Path(__file__).parent / "retain_test_cases.json"
    if not cases_path.exists():
        print(f"ERROR: {cases_path} not found. Run the case extraction first.")
        sys.exit(1)

    cases = json.loads(cases_path.read_text())
    print(f"Model: {MODEL}")
    print(f"Runs per option per case: {N}")
    print(f"Test cases: {len(cases)}")
    print()

    # Show case summaries
    for i, case in enumerate(cases):
        cards = case["cards"]
        harmful = [c["name"] for c in cards if _is_harmful(c)]
        sly = [c["name"] for c in cards if _is_sly(c)]
        tags = []
        if harmful:
            tags.append(f"HARMFUL:{','.join(harmful)}")
        if sly:
            tags.append(f"SLY:{','.join(sly)}")
        print(
            f"  Case {i}: {len(cards)} cards, sel=0-{case['max_select']}, "
            f"HP={case['hp']}/{case['hp_max']} "
            f"{'| ' + ' '.join(tags) if tags else ''}"
        )
    print()

    async with httpx.AsyncClient() as client:
        tasks = []
        for ci, case in enumerate(cases):
            scenario = build_scenario(case)
            prompt_a = scenario + HINT_OLD + "\n\n" + DECISION_BLOCK
            prompt_b = scenario + HINT_NEW + "\n\n" + DECISION_BLOCK

            for run_id in range(1, N + 1):
                tasks.append(call_once(client, prompt_a, "OLD", ci, run_id))
                tasks.append(call_once(client, prompt_b, "NEW", ci, run_id))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    old_results: dict[int, list] = {i: [] for i in range(len(cases))}
    new_results: dict[int, list] = {i: [] for i in range(len(cases))}

    for r in results:
        if isinstance(r, Exception):
            print(f"  EXCEPTION: {r}")
            continue
        ci = r["case"]
        if r["label"] == "OLD":
            old_results[ci].append(r)
        else:
            new_results[ci].append(r)

    # Summary
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)

    old_total = Counter()
    new_total = Counter()

    for ci, case in enumerate(cases):
        cards = case["cards"]
        harmful = [c["name"] for c in cards if _is_harmful(c)]
        sly = [c["name"] for c in cards if _is_sly(c)]
        tag = ""
        if harmful:
            tag = f" [HARMFUL: {','.join(harmful)}]"
        elif sly:
            tag = f" [SLY: {','.join(sly)}]"

        print(f"\nCase {ci}: {len(cards)} cards, sel=0-{case['max_select']}{tag}")

        for label, bucket, total_counter in [
            ("OLD", old_results[ci], old_total),
            ("NEW", new_results[ci], new_total),
        ]:
            evals = [evaluate_result(r, case) for r in bucket]
            counts = Counter(evals)
            total_counter.update(evals)

            good = counts.get("GOOD", 0)
            partial = counts.get("PARTIAL", 0)
            bad = counts.get("BAD", 0)
            err = counts.get("ERROR", 0)

            # Show what was retained
            retained_counts = Counter()
            confirm_count = 0
            for r in bucket:
                if r.get("action") == "confirm_selection" or not r.get("indices"):
                    confirm_count += 1
                else:
                    for idx in r.get("indices", []):
                        card = next((c for c in cards if c["index"] == idx), None)
                        if card:
                            retained_counts[card["name"]] += 1

            detail = ""
            if confirm_count:
                detail += f"skip={confirm_count} "
            for name, cnt in retained_counts.most_common(5):
                detail += f"{name}={cnt} "

            print(
                f"  {label}: GOOD={good} PARTIAL={partial} BAD={bad} "
                f"ERR={err} | {detail.strip()}"
            )

    print("\n" + "=" * 70)
    print("TOTALS")
    print("=" * 70)
    for label, counter in [("OLD", old_total), ("NEW", new_total)]:
        total = sum(counter.values())
        good = counter.get("GOOD", 0)
        partial = counter.get("PARTIAL", 0)
        bad = counter.get("BAD", 0)
        good_rate = (good + partial) / total * 100 if total else 0
        print(
            f"  {label}: GOOD={good} PARTIAL={partial} BAD={bad} "
            f"| retain rate: {good_rate:.0f}% ({good + partial}/{total})"
        )


if __name__ == "__main__":
    asyncio.run(main())
