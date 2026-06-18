"""Smoke-test DeepSeek V4 Flash latency: reasoning_effort=high vs max.

Sends a ~5000-token Slay-the-Spire-flavoured prompt to api.deepseek.com twice
(once per effort level), reports wall-clock latency and token usage. Reads
credentials from .env.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx

# ── Load .env ──
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if ENV_PATH.is_file():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

BASE_URL = os.environ.get("STS2_DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
API_KEY = os.environ.get("STS2_DEEPSEEK_API_KEY", "")
if not API_KEY:
    print("ERROR: STS2_DEEPSEEK_API_KEY not set in .env")
    sys.exit(1)

MODEL = "deepseek-v4-flash"

# ── Build a ~5000-token prompt ──
# Rough heuristic: 1 token ≈ 3.5 chars English → ~17500 chars for ~5000 tok.
# Use a realistic STS2-style game-state dump + rules for faithful latency.
GAME_STATE_BLOCK = """
=== TURN 4 ===
Player (Silent): HP 42/65, Block 8, Energy 3/3
Powers: Poison 0, Envenom 1, Strength 0, Weak 0, Vulnerable 0
Relics: Ring of the Snake (+2 draw turn 1), Bag of Preparation (+2 cards start), Boot (3+ damage floored to target), Strange Spoon (50% chance skill cards don't exhaust), Snecko Eye (draw 2, costs random 0-3)

Hand (7 cards, Snecko → random costs):
  [0] Strike+ (cost=2)  — Deal 9 damage
  [1] Neutralize+ (cost=0)  — Deal 4 damage, apply 2 Weak
  [2] Survivor+ (cost=1)  — Gain 10 Block, discard 1 card
  [3] Deadly Poison+ (cost=0)  — Apply 7 Poison
  [4] Acrobatics (cost=1)  — Draw 3, discard 1
  [5] Catalyst (cost=3)  — Double target's poison (exhaust)
  [6] Backstab+ (cost=0)  — Innate, deal 15 damage (exhaust)

Draw pile (8): Strike, Strike, Defend, Defend+, Shiv, Shiv, Poisoned Stab+, Flying Knee+
Discard pile (4): Strike, Defend, Deflect+, Eviscerate
Exhaust pile (2): Prepared, Bane

Enemies:
  [0] Awakened One (boss, phase 1): HP 180/300
      Intent: Attack for 20 next turn, status: "Unawakened" (half damage incoming? no — it's half OUTGOING for the boss in phase 1 per game rules)
      Powers: Curiosity 1 (gains 1 str when a power is played), Regrow (revives on phase 2)

  [1] Cultist minion: HP 48/48
      Intent: Ritual (gain 3 str), status: Vulnerable 2
      Powers: Ritual 3

Incoming damage calc next turn:
  - Awakened One attack 20 base × Curiosity modifiers × (phase 1 half-damage if applicable) = 10
  - Cultist no attack next turn (ritualing)
  → Total incoming: 10 (block 8 needed to negate → 2 overflow)

Deck trajectory: Poison/Shiv hybrid (poison engine primary, Shiv backup via Accuracy). Panache not yet picked. No Wraith Form. Finisher: Catalyst + Deadly Poison stacked.

Boss archetype for this act (Act 3): Awakened One — three phases, phase 2 applies Regrow (revives once), phase 3 has Unawakened removed → full damage output ~40/turn.

Smith visits used: 2 of 3. Rest sites remaining in act: 1.
"""

# Replicate the block enough times to hit ~5000 tokens (~17500 chars).
# Vary turn numbers so the content isn't purely repeated.
turn_blocks = []
for turn in range(1, 11):
    block = GAME_STATE_BLOCK.replace("TURN 4", f"TURN {turn} (replay snapshot)")
    turn_blocks.append(block)
LONG_CONTEXT = "\n".join(turn_blocks)

# Rough token estimate.
approx_tokens = len(LONG_CONTEXT) // 4
print(f"Prompt length: {len(LONG_CONTEXT)} chars (~{approx_tokens} tokens)")

SYSTEM = (
    "You are a Slay the Spire 2 expert combat planner. Given the game state, "
    "propose a concrete 3-action combat plan for the current turn. Output the "
    "plan as a JSON object with keys: plan (list of action strings), rationale "
    "(one sentence), expected_damage_dealt, expected_damage_taken."
)

USER = (
    LONG_CONTEXT
    + "\n\nBased on all 10 replay snapshots above, analyse the turn-4 state and "
    "propose a 3-action combat plan. Output JSON only."
)


def call_once(effort: str) -> tuple[float, dict, str]:
    """Return (elapsed_sec, usage_dict, content_preview)."""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "thinking": {"type": "enabled"},
        "reasoning_effort": effort,
        "max_tokens": 32000 if effort == "max" else 16000,
    }
    t0 = time.monotonic()
    with httpx.Client(timeout=600) as client:
        resp = client.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    elapsed = time.monotonic() - t0
    if resp.status_code != 200:
        return elapsed, {"error": resp.status_code, "body": resp.text[:500]}, ""
    data = resp.json()
    usage = data.get("usage", {})
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message", {}) or {}
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or ""
    preview = (content[:200] + "...") if len(content) > 200 else content
    usage["reasoning_chars"] = len(reasoning)
    usage["content_chars"] = len(content)
    usage["finish_reason"] = choice.get("finish_reason")
    return elapsed, usage, preview


def main() -> None:
    print(f"\nEndpoint: {BASE_URL}")
    print(f"Model:    {MODEL}\n")
    results = {}
    for effort in ("high", "max"):
        print(f"=== reasoning_effort={effort} ===")
        elapsed, usage, preview = call_once(effort)
        print(f"  latency : {elapsed:7.2f}s")
        print(f"  usage   : {json.dumps(usage, ensure_ascii=False)}")
        print(f"  preview : {preview!r}")
        print()
        results[effort] = {"latency": elapsed, "usage": usage}
    if "high" in results and "max" in results:
        dh = results["high"]["latency"]
        dm = results["max"]["latency"]
        print(f"Δ latency (max − high): {dm - dh:+.2f}s  (max is {dm/dh:.2f}× high)")


if __name__ == "__main__":
    main()
