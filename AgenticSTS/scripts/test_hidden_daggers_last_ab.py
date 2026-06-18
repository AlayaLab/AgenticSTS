"""A/B test: Hidden Daggers "play last" sequencing hint.

ORIG: no sequencing guidance — only the partial-discard rule
NEW : adds SEQUENCE: play ALL other cards BEFORE Hidden Daggers so it discards 0 cards.

Correct answer: plan must play Ultimate Strike++ and Dagger Spray BEFORE Hidden Daggers.
Wrong answer  : Hidden Daggers played first (discarding the two attacks).
"""

from __future__ import annotations

import asyncio
import os
import re
from collections import Counter
from pathlib import Path

import httpx

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BASE_URL = os.getenv("STS2_GEMINI_BASE_URL", os.getenv("OPENAI_COMPAT_BASE_URL", "https://proxy.example.com"))
API_KEY  = os.getenv("STS2_GEMINI_API_KEY",  os.getenv("OPENAI_COMPAT_API_KEY", ""))
MODEL    = os.getenv("STS2_STRATEGIC_MODEL", "gemini-3.1-pro-preview")
N        = 3

SYSTEM = """\
You are an autonomous Slay the Spire 2 agent playing a complete run. You make every decision to maximize your chance of defeating the Act 3 boss.

## Output Format
Think through your decision, then output your choice in a <decision> tag containing valid JSON.

Example (combat plan):
<decision>
{"plan": [{"type": "card", "card": "Backflip", "target_index": -1}, {"type": "card", "card": "Shiv", "target_index": 0}], "end_turn": true, "reasoning": "Block first, then chip damage"}
</decision>

For combat plans, the `plan` array is the exact execution order.

## Core Combat Rules
- Energy resets to 3 each turn. Unspent energy is wasted.
- Hand cards discarded at end of turn — unplayed cards are wasted.
- Cards DRAWN or CREATED this turn enter your hand immediately and can be played now.
- 0-cost cards (Shivs, etc.) are FREE — ALWAYS play them.
- If a card generates new cards (e.g. Hidden Daggers generates Shivs), queue their plays in the same plan AFTER the generator."""

SCENARIO_BASE = """\
## Round 2 Re-plan
Energy: 3/3 | HP: 66/73 | Block: 13

## Relics
- Unceasing Top: Whenever you have no cards in Hand during your turn, draw a card.
- Ornamental Fan: Every time you play 3 Attacks in a single turn, gain 4 Block.

## Re-plan Context
Original plan (5/7 completed): The enemy is not attacking this turn (Intent: StatusCard), so I can focus entirely on damage and setup. I play Production first to gain 2 energy, giving me 5 total energy to play my entire hand. I play Cloak and Dagger++ to generate two Shivs (and gain some block). I play both Shivs. Then I use Dagger Throw, discarding Piercing Wail as it's not needed this turn and I want to cycle my deck. I then play Ultimate Strike++ and Dagger Spray to maximize damage.
Trigger: Dagger Throw changed the current hand. Hidden Daggers was drawn.

## Enemies
- Mecha Knight [index=0]: HP 275/300, Block 0, Intent: StatusCard(4) | powers: Artifact(1)

Incoming damage: 0 (after block: 0)

## Hand (3 playable / 3 total)
- Ultimate Strike++ (Attack, cost=1): Deal 23 damage to Mecha Knight[0].
- Dagger Spray (Attack, cost=1): Deal 4 damage to ALL enemies twice (8 total).
- Hidden Daggers (Skill, cost=0): Discard 2 cards. Add 2 Shivs into your Hand.
!! DISCARD: Hidden Daggers will require discarding. Fill the "discard" field in your plan. Use a list when the card discards multiple cards.
"""

# Shiv stats for context (shared)
SHIV_LINE = "  (Each Shiv deals 4 damage to a single target for 0 energy)\n"

DISCARD_RULE_ORIG = (
    "!! DISCARD RULE: Hidden Daggers — if hand has fewer cards than "
    "the discard cost, you only discard what remains (possibly zero).\n"
)

DISCARD_RULE_NEW = (
    "!! DISCARD RULE: Hidden Daggers — if hand has fewer cards than "
    "the discard cost, you only discard what remains (possibly zero). "
    "SEQUENCE: play ALL other cards BEFORE Hidden Daggers so it "
    "discards 0 cards.\n"
)

DECISION_BLOCK = """\

## Decision
Respond with a combat plan. Include all cards you intend to play this turn in the correct execution order.
<decision>
{"plan": [...], "end_turn": true, "reasoning": "..."}
</decision>
"""

PROMPT_ORIG = SCENARIO_BASE + SHIV_LINE + DISCARD_RULE_ORIG + DECISION_BLOCK
PROMPT_NEW  = SCENARIO_BASE + SHIV_LINE + DISCARD_RULE_NEW  + DECISION_BLOCK


def classify(text: str) -> str:
    """Classify the plan order: CORRECT if attacks precede Hidden Daggers, WRONG otherwise."""
    plan_m = re.search(r'"plan"\s*:\s*(\[.*?\])', text, re.DOTALL)
    if not plan_m:
        return "NO_DECISION"
    plan_text = plan_m.group(1)
    cards_in_order = re.findall(r'"card"\s*:\s*"([^"]+)"', plan_text)
    try:
        hd_pos = next(i for i, c in enumerate(cards_in_order) if "Hidden Daggers" in c)
    except StopIteration:
        return "NO_HD"
    attacks_before = [
        c for c in cards_in_order[:hd_pos]
        if any(x in c for x in ("Ultimate Strike", "Dagger Spray"))
    ]
    attacks_after = [
        c for c in cards_in_order[hd_pos + 1:]
        if any(x in c for x in ("Ultimate Strike", "Dagger Spray"))
    ]
    if attacks_before and not attacks_after:
        return "CORRECT"
    if attacks_after:
        return "WRONG (attacks after HD)"
    if not attacks_before and not attacks_after:
        return "HD_ONLY (attacks discarded)"
    return f"PARTIAL ({len(attacks_before)} before, {len(attacks_after)} after)"


async def call_once(
    client: httpx.AsyncClient, prompt: str, label: str, run_id: int
) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        "max_tokens": 600,
        "temperature": 0.7,
    }
    resp = await client.post(
        f"{BASE_URL}/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=60.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    verdict = classify(content)
    print(f"  [{label}#{run_id}] {verdict}")
    return {"label": label, "run": run_id, "verdict": verdict, "raw": content}


async def main() -> None:
    print(f"Model : {MODEL}")
    print(f"N     : {N} per option\n")

    async with httpx.AsyncClient() as client:
        tasks = [
            call_once(client, PROMPT_ORIG, "ORIG", i)
            for i in range(1, N + 1)
        ] + [
            call_once(client, PROMPT_NEW, "NEW", i)
            for i in range(1, N + 1)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    buckets: dict[str, list[str]] = {"ORIG": [], "NEW": []}
    for r in results:
        if isinstance(r, Exception):
            print(f"  ERROR: {r}")
            continue
        buckets[r["label"]].append(r["verdict"])

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    for label, verdicts in buckets.items():
        counts = Counter(verdicts)
        correct = counts.get("CORRECT", 0)
        print(f"\nOption {label} ({N} runs):")
        for v, cnt in sorted(counts.items()):
            marker = " ✓" if v == "CORRECT" else ""
            print(f"  {v}: {cnt}/{N}{marker}")
        print(f"  → Correct rate: {correct}/{N}")


if __name__ == "__main__":
    asyncio.run(main())
