"""A/B smoke test: QWEN vs Gemini 3.1 Pro on two real combat states.

Scenario A — Seapunk (Round 4):
  Enemy has 9 HP + 7 Block (16 effective). Intent: Attack(12).
  Hand: Strike x2 + Defend x3. 3 energy.
  QWEN answer: 3× Strike (kills, takes 0 damage). Correct.

Scenario B — Toadpole×2 (Round 2):
  T0: 3 HP, Thorns(2), Attack(3x3=9). T1: 25 HP, Buff.
  Hand: Neutralize(0) + Outbreak(1) + Defend×2 + Strike.
  QWEN answer: Neutralize→Defend→Defend (wasted 1E, block was useless).
  Better line: Neutralize kills T0 (takes 2 Thorns), then Outbreak+Strike+Defend.

Sends the exact same 3-turn conversation (system+combat_start ok+round_state)
to Gemini 3.1 Pro, 3 concurrent runs per scenario.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
import config  # noqa: E402
from src.brain.prompts.system import SYSTEM_COMBAT  # noqa: E402

BASE_URL = config.GEMINI_BASE_URL or config.OPENAI_COMPAT_BASE_URL
API_KEY = config.GEMINI_API_KEY or config.OPENAI_COMPAT_API_KEY
MODEL = "gemini-3.1-pro-preview"
TIMEOUT = 180.0
N = 3  # concurrent runs per scenario

if not BASE_URL or not API_KEY:
    print("ERR: STS2_GEMINI_BASE_URL / STS2_GEMINI_API_KEY not set")
    sys.exit(1)

# ── Scenario A: Seapunk Round 4 ───────────────────────────────

SEAPUNK_COMBAT_START = """\
## Combat Start
Encounter type: monster
Act: 1 | Floor: 2
Enemies: Seapunk
- Seapunk [index=0]: HP 22/44, Block 0

Player HP: 58/58 | Block: 0 | Energy: 3/3

## Current Deck (12 cards)
  [Attack] Strike x4, Follow Through(cost=1), Neutralize(cost=0)
  [Power] Outbreak(cost=1)
  [Skill] Defend x4, Survivor(cost=1)

## Relics (2)
- Ring of the Snake: At the start of each combat, draw 2 additional cards.
- Leafy Poultice: Upon pickup, Transform 1 of your Strikes and 1 of your Defends and lose 12 Max HP.

## Combat Rules
- Only play cards marked [PLAYABLE].
- Include potions in your combat plan when useful (they don't cost energy).
- **Discard effects**: If a card requires discarding (e.g. Survivor), specify with the "discard" field."""

SEAPUNK_ROUND4 = """\
## Computed Insights
- block_sufficiency_check: recommendation=Full block requires all energy.
- poison_kill_and_survive_check: recommendation=ADD_POISON - No lethal poison (total shortfall: 9)

## Round 4 State
Energy: 3/3 | HP: 58/58 | Block: 0
Player buffs/debuffs: Outbreak(11): Every 10 times you apply Poison, deal damage to ALL enemies.

## Enemies
- Seapunk [index=0]: HP 9/44, Block 7, Intent: Attack(12) | powers: Strength(1): Strength adds additional damage to Attacks.

Incoming damage: 12 (after block: 12) | Your HP: 58

## Strategic Thread
R3: Seapunk at 9 HP after this turn. Next turn likely 12 damage - consider Defend or Survivor if needed. Potentially need 1-2 more damage to finish him.

## Hand (5 playable / 5 total)
- Strike (Attack, cost=1) [6 dmg] -> targets enemies: Deal 6 damage.
- Strike (Attack, cost=1) [6 dmg] -> targets enemies: Deal 6 damage.
- Defend (Skill, cost=1) [5 block]: Gain 5 Block.
- Defend (Skill, cost=1) [5 block]: Gain 5 Block.
- Defend (Skill, cost=1) [5 block]: Gain 5 Block.

## Piles
Piles: Draw 2 | Discard 4 | Exhaust 0

## Potions
Potion slots: 0/3 (3 open)

Energy budget: 3E available, fixed-cost total: 5E

CRITICAL RULES:
- Energy RESETS to full each turn. Unspent energy is WASTED.
- 0-cost cards are FREE — ALWAYS play them.
- The `plan` array is executed top-to-bottom."""

# ── Scenario B: Toadpole×2 Round 2 ───────────────────────────

TOADPOLE_COMBAT_START = """\
## Combat Start
Encounter type: monster
Act: 1 | Floor: 3
Enemies: Toadpole + Toadpole
- Toadpole [index=0]: HP 23/23, Block 0
- Toadpole [index=1]: HP 25/25, Block 0

Player HP: 51/58 | Block: 0 | Energy: 3/3

## Current Deck (13 cards)
  [Attack] Strike x4, Follow Through(cost=1), Neutralize(cost=0)
  [Power] Outbreak(cost=1)
  [Skill] Defend x4, Backflip(cost=1), Survivor(cost=1)

## Relics (2)
- Ring of the Snake: At the start of each combat, draw 2 additional cards.
- Leafy Poultice: Upon pickup, Transform 1 of your Strikes and 1 of your Defends and lose 12 Max HP.

## Past Experience
- Toadpoles cycle between being unbuffed and having 2 Thorns active.
- Thorns are predictably absent on Round 1, activate for Rounds 2 and 3, and drop off on Round 4.

## Combat Rules
- Only play cards marked [PLAYABLE].
- Include potions in your combat plan when useful.
- **Discard effects**: specify with the "discard" field."""

TOADPOLE_ROUND2 = """\
## Computed Insights
- block_sufficiency_check: recommendation=Full block with 2 card(s). 1 energy for offense.
- poison_kill_and_survive_check: recommendation=ADD_POISON - No lethal poison (total shortfall: 28)

## Round 2 State
Energy: 3/3 | HP: 49/58 | Block: 0

## Enemies
- Toadpole [index=0]: HP 3/23, Block 0, Intent: Attack(3x3=9) | powers: Thorns(2): When hit by an attack, deal damage back.
- Toadpole [index=1]: HP 25/25, Block 0, Intent: Buff

Incoming damage: 9 (after block: 9) | Your HP: 49

## Strategic Thread
R1: Thorns activate Rounds 2-3. When they do, prioritize defensive cards and poison over direct damage attacks to avoid recoil damage.

## Hand (5 playable / 5 total)
- Neutralize (Attack, cost=0) [3 dmg] -> targets enemies: Deal 3 damage. Apply 1 Weak.
- Outbreak (Power, cost=1): Every 3 times you apply Poison, deal 11 damage to ALL enemies.
- Defend (Skill, cost=1) [5 block]: Gain 5 Block.
- Defend (Skill, cost=1) [5 block]: Gain 5 Block.
- Strike (Attack, cost=1) [6 dmg] -> targets enemies: Deal 6 damage.

## Key Effects
- Thorns: When hit by an attack, deal damage back.
- Poison: Loses N HP at the start of its turn, before it acts, then decreases by 1. Bypasses Block.

## Piles
Piles: Draw 1 | Discard 5 | Exhaust 0

Energy budget: 3E available, fixed-cost total: 4E

CRITICAL RULES:
- Energy RESETS to full each turn. Unspent energy is WASTED.
- 0-cost cards are FREE — ALWAYS play them.
- The `plan` array is executed top-to-bottom.

Likely upcoming after R2:
- Pattern A: R3 Toadpole: Attack(7) + Toadpole: Attack(3x3=9)
- Pattern B: R3 Toadpole: Attack(7) + Toadpole: Attack(3x3=9)"""

SCENARIOS = {
    "seapunk_r4": {
        "label": "Scenario A — Seapunk R4",
        "qwen": "Strike→Strike→Strike (18 dmg, kills, 0 taken)",
        "correct": "3× Strike (16 eff HP, kills outright)",
        "messages": [
            {"role": "user", "content": SEAPUNK_COMBAT_START},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": SEAPUNK_ROUND4},
        ],
    },
    "toadpole_r2": {
        "label": "Scenario B — Toadpole×2 R2",
        "qwen": "Neutralize→Defend→Defend (1E wasted, 10 block vs no incoming)",
        "correct": "Neutralize kills T0 (takes 2 Thorns), then use 3E on Outbreak/Strike/Defend",
        "messages": [
            {"role": "user", "content": TOADPOLE_COMBAT_START},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": TOADPOLE_ROUND2},
        ],
    },
}


def _extract_plan(text: str) -> list[str] | None:
    m = re.search(r"<decision>(.*?)</decision>", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1).strip())
        plan = data.get("plan", [])
        return [f'{p.get("card","?")}→t{p.get("target_index","?")}' for p in plan]
    except (json.JSONDecodeError, AttributeError):
        return None


async def call_gemini(
    client: httpx.AsyncClient,
    scenario_key: str,
    run_id: int,
) -> dict:
    sc = SCENARIOS[scenario_key]
    t0 = time.monotonic()
    try:
        resp = await client.post(
            f"{BASE_URL}/v1/chat/completions",
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_COMBAT},
                    *sc["messages"],
                ],
                "max_tokens": 2000,
                "temperature": 0.6,
            },
            headers={"Authorization": f"Bearer {API_KEY}"},
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        latency = (time.monotonic() - t0) * 1000
        plan = _extract_plan(content)
        plan_str = " → ".join(plan) if plan else "(no plan parsed)"
        return {
            "scenario": scenario_key,
            "run": run_id,
            "latency_ms": latency,
            "plan": plan,
            "plan_str": plan_str,
            "ok": plan is not None,
            "raw": content[:600],
        }
    except Exception as e:
        latency = (time.monotonic() - t0) * 1000
        return {
            "scenario": scenario_key,
            "run": run_id,
            "latency_ms": latency,
            "plan": None,
            "plan_str": f"ERROR: {type(e).__name__}: {e}",
            "ok": False,
            "raw": "",
        }


async def main() -> None:
    print(f"Model:   {MODEL}")
    print(f"Relay:   {BASE_URL}")
    print(f"Runs:    {N} concurrent per scenario ({N * len(SCENARIOS)} total calls)")
    print("=" * 70)

    async with httpx.AsyncClient() as client:
        tasks = [
            call_gemini(client, sk, i + 1)
            for sk in SCENARIOS
            for i in range(N)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Group by scenario
    buckets: dict[str, list] = {k: [] for k in SCENARIOS}
    for r in results:
        if isinstance(r, Exception):
            print(f"UNCAUGHT: {r}")
            continue
        buckets[r["scenario"]].append(r)

    for sk, sc in SCENARIOS.items():
        print(f"\n{'=' * 70}")
        print(f"  {sc['label']}")
        print(f"  QWEN answer : {sc['qwen']}")
        print(f"  Correct line: {sc['correct']}")
        print("-" * 70)
        runs = buckets[sk]
        for r in runs:
            ok_marker = "✓" if r["ok"] else "✗"
            print(f"  [{ok_marker} run{r['run']}] {r['latency_ms']:.0f}ms | {r['plan_str']}")
        if runs:
            avg_ms = sum(r["latency_ms"] for r in runs) / len(runs)
            parsed = sum(1 for r in runs if r["ok"])
            print(f"  avg latency: {avg_ms:.0f}ms  parsed: {parsed}/{len(runs)}")

    print("\n" + "=" * 70)
    total_ok = sum(1 for r in results if not isinstance(r, Exception) and r.get("ok"))
    total = sum(1 for r in results if not isinstance(r, Exception))
    print(f"  Total: {total_ok}/{total} decisions parsed")


if __name__ == "__main__":
    asyncio.run(main())
