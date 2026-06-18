"""A/B test: Ascender's Bane shown with rules_text in UNPLAYABLE section.

Reproduces the bug where agent picks "discard": "Ascender's Bane" for Survivor
in a combat plan, even though Bane should be kept to auto-exhaust.

ORIG: - Ascender's Bane (cost=-1, unplayable)
FIX:  - Ascender's Bane (cost=-1, unplayable): Unplayable. Ethereal. Eternal.

CORRECT: discard field = any card OTHER than Ascender's Bane
WRONG:   discard field = "Ascender's Bane"
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from collections import Counter
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

BASE_URL = config.GEMINI_BASE_URL or config.OPENAI_COMPAT_BASE_URL
API_KEY = config.GEMINI_API_KEY or config.OPENAI_COMPAT_API_KEY
MODEL = os.getenv("STS2_STRATEGIC_MODEL", "gemini-3.1-pro-preview")
N = 8

SYSTEM = "You are a Slay the Spire 2 agent making tactical combat decisions."

# Shared scenario — Round 3, same as the logged bug
SCENARIO_BASE = """\
## Round 3 State
Energy: 3/3 | HP: 56/57 | Block: 0

## Enemies
- Toadpole [index=0]: HP 5/23, Block 0, Intent: Attack(7)
- Toadpole [index=1]: HP 16/25, Block 0, Intent: Attack(3x3=9) | powers: Thorns(2)

Incoming damage: 16 | Your HP: 56

## Hand (4 playable / 5 total)
- Defend (Skill, cost=1): Gain 5 Block.
- Survivor (Skill, cost=1): Gain 8 Block. Discard 1 card.
- Strike (Attack, cost=1): Deal 6 damage.
- Strike (Attack, cost=1): Deal 6 damage.

!! DISCARD: Survivor will require discarding. Fill the "discard" field in your plan.
!! DISCARD RULE: Choose the least valuable card to discard — prefer unplayable or redundant cards.

## Key Effects
- Block: Absorbs damage until your next turn, then resets to 0.
- Ethereal: Exhausted if still in hand at end of turn. If Unplayable, keep it — auto-exhaust removes it this combat. Don't discard it.
- Eternal: Cannot be removed or transformed from your deck.
- Unplayable: Cannot be played from hand. Only for discard/exhaust synergies.
- Thorns: When hit by an attack, deal damage back.

"""

UNPLAYABLE_ORIG = """\
UNPLAYABLE cards (cannot use this turn):
- Ascender's Bane (cost=-1, unplayable)

"""

UNPLAYABLE_FIX = """\
UNPLAYABLE cards (cannot use this turn):
- Ascender's Bane (cost=-1, unplayable): Unplayable. Ethereal. Eternal.

"""

DECISION_BLOCK = """\
## Decision Format
Output a combat plan as JSON in a <decision> tag.
Required fields: plan (array), end_turn (bool), reasoning (string).
For Survivor, include "discard": "<card_name>" in its plan entry.

Example:
<decision>
{"plan": [{"type": "card", "card": "Strike", "target_index": 0}, {"type": "card", "card": "Survivor", "target_index": -1, "discard": "Defend"}], "end_turn": true, "reasoning": "Kill T0, then block."}
</decision>
"""

PROMPT_ORIG = SCENARIO_BASE + UNPLAYABLE_ORIG + DECISION_BLOCK
PROMPT_FIX = SCENARIO_BASE + UNPLAYABLE_FIX + DECISION_BLOCK


def extract_discard(text: str) -> str | None:
    m = re.search(r'"discard"\s*:\s*"([^"]+)"', text)
    return m.group(1) if m else None


WRONG_VALUE = "Ascender's Bane"


async def call_once(client: httpx.AsyncClient, prompt: str, label: str, run_id: int) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 2000,
        "temperature": 0.7,
    }
    resp = await client.post(
        f"{BASE_URL}/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    discard = extract_discard(content)
    is_wrong = discard == WRONG_VALUE
    marker = " ✗ WRONG" if is_wrong else (" ✓" if discard else " ?no-discard")
    if run_id == 1 and label == "ORIG":
        print(f"\n  [DEBUG ORIG#1]:\n{content[:500]}\n")
    print(f"  [{label}#{run_id}] discard={discard!r}{marker}")
    return {"label": label, "run": run_id, "discard": discard}


async def main():
    print(f"Model: {MODEL}")
    print(f"Runs per option: {N}")
    print(f'Wrong: discard="Ascender\'s Bane" | Correct: any other card or no discard field\n')

    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(1, N + 1):
            tasks.append(call_once(client, PROMPT_ORIG, "ORIG", i))
            tasks.append(call_once(client, PROMPT_FIX, "FIX ", i))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    buckets: dict[str, list] = {"ORIG": [], "FIX ": []}
    for r in results:
        if isinstance(r, Exception):
            print(f"  ERROR: {r}")
            continue
        buckets[r["label"]].append(r["discard"])

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    for label, discards in buckets.items():
        counts = Counter(discards)
        wrong = counts.get(WRONG_VALUE, 0)
        correct = sum(cnt for val, cnt in counts.items() if val != WRONG_VALUE)
        print(f"\nOption {label}:")
        for val, cnt in sorted(counts.items(), key=lambda x: (x[0] is None, x[0] or "")):
            marker = " ✗" if val == WRONG_VALUE else " ✓"
            print(f"  discard={val!r}: {cnt}/{N}{marker}")
        print(f"  → Correct: {correct}/{N} | Wrong (Bane): {wrong}/{N}")


if __name__ == "__main__":
    asyncio.run(main())
