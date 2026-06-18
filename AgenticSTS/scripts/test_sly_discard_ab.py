"""A/B test: compare hand_select discard hint variants on the Sly card scenario.

Option A: Keep "Discard = temporary (you'll draw them again)." (remove second sentence)
Option B: Remove the discard hint line entirely

Runs 5 parallel calls per option using gemini-3.1-flash-lite-preview.
"""

from __future__ import annotations

import asyncio
import os
import re
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
N = 5

SYSTEM = "You are a Slay the Spire 2 agent making tactical combat decisions."

# The scenario prompt — shared by both options
SCENARIO_BASE = """\
## Hand Selection (In-Combat)
Mode: combat_hand_select
Prompt: Choose a card to Discard.
HP: 57/76 | Energy: 2 | Block: 0

## Combat Context
Triggered by: Acrobatics+
!! SLY CARDS: Ricochet+ — discard these to play them FREE!
Enemy powers: Scroll of Biting: Paper Cuts=2, Poison=7 | Scroll of Biting: Paper Cuts=2, Poison=10, Strength=2, Weak=1

## Enemies
- Scroll of Biting: 21/38 HP, Intent: Buff
- Scroll of Biting: 16/36 HP, Intent: Attack(5x2=10)

## Cards You Can Select
- [index=0] Memento Mori++ (Attack, cost=1): Deal 11 damage. Deals 5 additional damage for each card discarded this turn.
- [index=1] Eternal Armor (Power, cost=3): Gain 7 Plating.
- [index=2] Ricochet++ (Attack, cost=2): Sly. Deal 4 damage to a random enemy 5 times.
- [index=3] Predator++ (Attack, cost=2): Deal 21 damage. Next turn, draw 2 cards.
- [index=4] Acrobatics++ (Skill, cost=1): Draw 4 cards. Discard 1 card.
- [index=5] Escape Plan (Skill, cost=0): Draw 1 card. If you draw a Skill, gain 5 Block.
- [index=6] Well-Laid Plans (Power, cost=1): At the end of your turn, Retain up to 1 card.
- [index=7] Mirage++ (Skill, cost=0): Gain Block equal to Poison on ALL enemies. (Gain 19 Block) Exhaust.

## Tactical Flags
Sly cards: Ricochet+. Discarding these by a card effect PLAYS them for free.

Discard = temporary (you'll draw them again). Discard cards you can't afford this turn or don't need right now.

"""

SCENARIO_A = SCENARIO_BASE.replace(
    "Discard = temporary (you'll draw them again). Discard cards you can't afford this turn or don't need right now.\n",
    "Discard = temporary (you'll draw them again).\n",
)

SCENARIO_B = SCENARIO_BASE.replace(
    "Discard = temporary (you'll draw them again). Discard cards you can't afford this turn or don't need right now.\n",
    "",
)

DECISION_BLOCK = """\
## Decision Format (hand_select_action)
Valid actions: select_deck_card
Required fields: action, reasoning
Response:
<decision>
{"action": "select_deck_card", "option_index": <N>, "reasoning": "<why>"}
</decision>
"""

PROMPT_A = SCENARIO_A + DECISION_BLOCK
PROMPT_B = SCENARIO_B + DECISION_BLOCK


def extract_index(text: str) -> int | None:
    m = re.search(r'"option_index"\s*:\s*(\d+)', text)
    return int(m.group(1)) if m else None


INDEX_NAMES = {
    0: "Memento Mori++ (Atk,1)",
    1: "Eternal Armor (Pwr,3) ← original wrong choice",
    2: "Ricochet++ (Sly!) ← CORRECT",
    3: "Predator++ (Atk,2)",
    4: "Acrobatics++ (Skl,1)",
    5: "Escape Plan (Skl,0)",
    6: "Well-Laid Plans (Pwr,1)",
    7: "Mirage++ (Skl,0)",
}


async def call_once(client: httpx.AsyncClient, prompt: str, label: str, run_id: int) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 300,
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
    print(f"  [{label}#{run_id}] index={idx} ({INDEX_NAMES.get(idx, '?')})")
    return {"label": label, "run": run_id, "index": idx, "raw": content}


SCENARIO_ORIG = SCENARIO_BASE  # has "can't afford" hint
PROMPT_ORIG = SCENARIO_ORIG + DECISION_BLOCK


async def main():
    print(f"Model: {MODEL}")
    print(f"Runs per option: {N}\n")

    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(1, N + 1):
            tasks.append(call_once(client, PROMPT_ORIG, "ORIG", i))
            tasks.append(call_once(client, PROMPT_A, "A", i))
            tasks.append(call_once(client, PROMPT_B, "B", i))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    buckets: dict[str, list] = {"ORIG": [], "A": [], "B": []}
    for r in results:
        if isinstance(r, Exception):
            print(f"  ERROR: {r}")
            continue
        buckets[r["label"]].append(r["index"])

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    labels = [
        ("ORIG (original, has 'can't afford')", "ORIG"),
        ("A    (keep 'Discard = temporary')", "A"),
        ("B    (remove hint entirely)", "B"),
    ]
    for display, key in labels:
        indices = buckets[key]
        counts = Counter(indices)
        correct = counts.get(2, 0)
        print(f"\nOption {display}:")
        for idx, cnt in sorted(counts.items()):
            name = INDEX_NAMES.get(idx, f"index={idx}")
            marker = " ✓" if idx == 2 else ""
            print(f"  [{idx}] {name}: {cnt}/{N}{marker}")
        print(f"  → Sly correct rate: {correct}/{N}")


if __name__ == "__main__":
    asyncio.run(main())
