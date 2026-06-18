"""A/B test: Ethereal keyword fix for Unplayable+Ethereal cards (Ascender's Bane).

Reproduces the bug where agent discards Ascender's Bane instead of keeping it
to auto-exhaust (permanent removal). Enemy is Buffing, 1 energy available.

CORRECT: discard a Strike (index=7 or 8) — keep Bane in hand to auto-exhaust
WRONG:   discard Ascender's Bane (index=5) — sends it back to draw pile

Option A (ORIG): current Ethereal definition — "You must play it or lose it."
Option B (FIX):  updated definition — Unplayable Ethereal cards: keep, auto-exhaust removes them.
"""

from __future__ import annotations

import asyncio
import os
import re
from collections import Counter
from pathlib import Path

import sys

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402

BASE_URL = config.GEMINI_BASE_URL or config.OPENAI_COMPAT_BASE_URL
API_KEY = config.GEMINI_API_KEY or config.OPENAI_COMPAT_API_KEY
MODEL = os.getenv("STS2_FAST_MODEL", "gemini-3-flash-preview")
N = 8

SYSTEM = "You are a Slay the Spire 2 agent making tactical combat decisions."

SCENARIO = """\
## Hand Selection (In-Combat)
Mode: combat_hand_select
Prompt: Choose a card to Discard.
HP: 44/75 | Energy: 1 | Block: 0

## Combat Context
Triggered by: Acrobatics+
Enemy powers: Vantom: Weak=1
Strategic intent (R3): Slippery is gone, start stacking damage.

## Enemies
- Vantom: 20/173 HP, Intent: Buff

## Cards You Can Select
- [index=0] Cloak and Dagger (Skill, cost=1): Gain 6 Block. Add 1 Shiv into your Hand.
- [index=1] Defend++ (Skill, cost=1): Gain 8 Block.
- [index=2] Defend (Skill, cost=1): Gain 5 Block.
- [index=3] Survivor (Skill, cost=1): Gain 8 Block. Discard 1 card.
- [index=4] Defend (Skill, cost=1): Gain 5 Block.
- [index=5] Ascender's Bane (Curse, cost=-1): Unplayable. Ethereal. Eternal.
- [index=6] Defend++ (Skill, cost=1): Gain 8 Block.
- [index=7] Strike (Attack, cost=1): Deal 6 damage.
- [index=8] Strike (Attack, cost=1): Deal 6 damage.

"""

KEYWORD_GLOSSARY_ORIG = """\
## Keyword Glossary
- Block: Absorbs damage until your next turn, then resets to 0.
- Ethereal: Exhausted if still in hand at end of turn. You must play it or lose it.
- Eternal: Cannot be removed or transformed from your deck.
- Unplayable: Cannot be played from hand. Only for discard/exhaust synergies.

"""

KEYWORD_GLOSSARY_FIX = """\
## Keyword Glossary
- Block: Absorbs damage until your next turn, then resets to 0.
- Ethereal: Exhausted if still in hand at end of turn. If Unplayable, keep it — auto-exhaust removes it this combat. Don't discard it.
- Eternal: Cannot be removed or transformed from your deck.
- Unplayable: Cannot be played from hand. Only for discard/exhaust synergies.

"""

DECISION_BLOCK = """\
Discard = temporary (you'll draw them again).

## Decision Format (hand_select_action)
Valid actions: select_deck_card
Required fields: action, reasoning
Response:
<decision>
{"action": "select_deck_card", "option_index": <N>, "reasoning": "<why>"}
</decision>
"""

PROMPT_ORIG = SCENARIO + KEYWORD_GLOSSARY_ORIG + DECISION_BLOCK
PROMPT_FIX = SCENARIO + KEYWORD_GLOSSARY_FIX + DECISION_BLOCK

INDEX_NAMES = {
    0: "Cloak and Dagger (Skl)",
    1: "Defend++ (Skl)",
    2: "Defend (Skl)",
    3: "Survivor (Skl)",
    4: "Defend (Skl)",
    5: "Ascender's Bane ← WRONG (send back to draw)",
    6: "Defend++ (Skl)",
    7: "Strike (Atk) ← CORRECT (keep Bane to exhaust)",
    8: "Strike (Atk) ← CORRECT (keep Bane to exhaust)",
}

CORRECT_INDICES = {2, 4, 7, 8}  # anything except Ascender's Bane (5) is acceptable
WRONG_INDICES = {5}


def extract_index(text: str) -> int | None:
    m = re.search(r'"option_index"\s*:\s*(\d+)', text)
    return int(m.group(1)) if m else None


async def call_once(client: httpx.AsyncClient, prompt: str, label: str, run_id: int) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 600,
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
    idx = extract_index(content)
    marker = " ✓" if idx in CORRECT_INDICES else (" ✗" if idx in WRONG_INDICES else "")
    print(f"  [{label}#{run_id}] index={idx} ({INDEX_NAMES.get(idx, '?')}){marker}")
    return {"label": label, "run": run_id, "index": idx}


async def main():
    print(f"Model: {MODEL}")
    print(f"Runs per option: {N}")
    print(f"Correct: discard a Strike (index 7 or 8) — keep Bane to auto-exhaust")
    print(f"Wrong:   discard Ascender's Bane (index 5)\n")

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
        buckets[r["label"]].append(r["index"])

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    for label, indices in buckets.items():
        counts = Counter(indices)
        correct = sum(counts.get(i, 0) for i in CORRECT_INDICES)
        wrong = sum(counts.get(i, 0) for i in WRONG_INDICES)
        print(f"\nOption {label}:")
        for idx, cnt in sorted(counts.items(), key=lambda x: (x[0] is None, x[0])):
            name = INDEX_NAMES.get(idx, f"index={idx}")
            marker = " ✓" if idx in CORRECT_INDICES else (" ✗" if idx in WRONG_INDICES else "")
            print(f"  [{idx}] {name}: {cnt}/{N}{marker}")
        print(f"  → Correct rate: {correct}/{N} | Wrong (Bane) rate: {wrong}/{N}")


if __name__ == "__main__":
    asyncio.run(main())
