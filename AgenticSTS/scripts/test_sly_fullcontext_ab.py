"""A/B test with REAL full context from logs.

Takes the system prompt + skills + memory prefix from a real run_ff8301b50931 log entry,
injects the user's Acrobatics+Sly+Discard scenario, and tests ORIG/A/B variants.

ORIG: "Discard = temporary (you'll draw them again). Discard cards you can't afford this turn or don't need right now."
A:    "Discard = temporary (you'll draw them again)."
B:    (hint line removed entirely)

Runs 5 parallel calls per option.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import Counter
from pathlib import Path

import httpx

# Load .env manually
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
LOG_DIR = Path("logs")

# ── Load real context from most recent log with hand_select ───

def load_real_context() -> tuple[str, str, str]:
    """Return (system_prompt, prefix_before_hand_select, log_filename).

    Scans logs sorted by mtime (newest first), picks the richest entry
    (Sly + memory preferred, then most context).
    """
    log_files = sorted(LOG_DIR.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    best: dict | None = None
    best_file = ""
    for path in log_files:
        with open(path) as f:
            events = [json.loads(line) for line in f if line.strip()]
        llm_events = [e for e in events if e.get("event") == "llm_call"]
        hs_llm = [e for e in llm_events if "Hand Selection" in str(e.get("prompt", ""))]
        if not hs_llm:
            continue
        # Score each entry: prefer Sly + memory + long prompt
        for e in hs_llm:
            p = e.get("prompt", "")
            score = (
                ("Sly" in p or "SLY" in p) * 10
                + ("Past Experience" in p) * 5
                + len(p) // 500
            )
            if best is None or score > best["score"]:
                best = {"event": e, "score": score}
                best_file = path.name
        if best and best["score"] >= 15:  # Sly + memory found, stop searching
            break

    if best is None:
        raise RuntimeError("No hand_select LLM calls found in any log file")

    e = best["event"]
    system = e["system_prompt"]
    prompt = e["prompt"]
    idx = prompt.find("## Hand Selection")
    prefix = prompt[:idx]
    return system, prefix, best_file

SYSTEM, CONTEXT_PREFIX, LOG_USED = load_real_context()
print(f"Using log: {LOG_USED}")
print(f"System prompt: {len(SYSTEM)} chars")
print(f"Context prefix (skills+memory): {len(CONTEXT_PREFIX)} chars")

# ── The Acrobatics+Sly+Discard scenario ──────────────────────

HAND_SELECT_ORIG = """\
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

## Decision Format (hand_select_action)
Valid actions: select_deck_card
Required fields: action, reasoning
Response:
<decision>
{"action": "select_deck_card", "option_index": <N>, "reasoning": "<why>"}
</decision>
"""

HAND_SELECT_A = HAND_SELECT_ORIG.replace(
    "Discard = temporary (you'll draw them again). Discard cards you can't afford this turn or don't need right now.\n",
    "Discard = temporary (you'll draw them again).\n",
)

HAND_SELECT_B = HAND_SELECT_ORIG.replace(
    "Discard = temporary (you'll draw them again). Discard cards you can't afford this turn or don't need right now.\n",
    "",
)

PROMPT_ORIG = CONTEXT_PREFIX + HAND_SELECT_ORIG
PROMPT_A    = CONTEXT_PREFIX + HAND_SELECT_A
PROMPT_B    = CONTEXT_PREFIX + HAND_SELECT_B

# ── Index legend ──────────────────────────────────────────────

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

# ── API call ──────────────────────────────────────────────────

def extract_index(text: str) -> int | None:
    m = re.search(r'"option_index"\s*:\s*(\d+)', text)
    return int(m.group(1)) if m else None


async def call_once(client: httpx.AsyncClient, system: str, prompt: str, label: str, run_id: int) -> dict:
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 400,
        "temperature": 0.7,
    }
    resp = await client.post(
        f"{BASE_URL}/v1/chat/completions",
        json=payload,
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=40.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    idx = extract_index(content)
    name = INDEX_NAMES.get(idx, f"index={idx}")
    marker = " ✓" if idx == 2 else " ✗"
    print(f"  [{label}#{run_id}]{marker} index={idx} ({name})")
    return {"label": label, "run": run_id, "index": idx, "raw": content}


async def main():
    print(f"\nModel: {MODEL}")
    print("Full prompt sizes:")
    print(f"  ORIG: {len(PROMPT_ORIG)} chars / ~{len(PROMPT_ORIG)//4} tokens")
    print(f"  A:    {len(PROMPT_A)} chars / ~{len(PROMPT_A)//4} tokens")
    print(f"  B:    {len(PROMPT_B)} chars / ~{len(PROMPT_B)//4} tokens")
    print(f"Runs per option: {N}\n")

    sem = asyncio.Semaphore(5)  # Limit to 5 concurrent requests

    async def bounded_call(*args, **kwargs):
        async with sem:
            return await call_once(*args, **kwargs)

    async with httpx.AsyncClient() as client:
        tasks = []
        for i in range(1, N + 1):
            tasks.append(bounded_call(client, SYSTEM, PROMPT_ORIG, "ORIG", i))
            tasks.append(bounded_call(client, SYSTEM, PROMPT_A, "A", i))
            tasks.append(bounded_call(client, SYSTEM, PROMPT_B, "B", i))

        results = await asyncio.gather(*tasks, return_exceptions=True)

    buckets: dict[str, list] = {"ORIG": [], "A": [], "B": []}
    for r in results:
        if isinstance(r, Exception):
            print(f"  ERROR: {type(r).__name__}: {r}")
            continue
        buckets[r["label"]].append(r["index"])

    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)

    rows = [
        ("ORIG (has 'can't afford')", "ORIG"),
        ("A    (keep 'Discard = temporary')", "A"),
        ("B    (remove hint entirely)", "B"),
    ]
    for display, key in rows:
        indices = buckets[key]
        counts = Counter(indices)
        correct = counts.get(2, 0)
        print(f"\nOption {display}:")
        for idx, cnt in sorted(counts.items()):
            name = INDEX_NAMES.get(idx, f"index={idx}")
            marker = " ✓" if idx == 2 else " ✗"
            print(f"  [{idx}]{marker} {name}: {cnt}/{N}")
        print(f"  → Sly correct rate: {correct}/{N}")

    # Print one full response per variant for inspection
    print("\n" + "=" * 70)
    print("SAMPLE REASONING (first call per variant)")
    print("=" * 70)
    for r in results:
        if isinstance(r, dict) and r.get("run") == 1:
            print(f"\n[{r['label']}] index={r['index']}")
            # Extract just the decision block
            raw = r.get("raw", "")
            dec = re.search(r'<decision>.*?</decision>', raw, re.DOTALL)
            if dec:
                print(dec.group(0))
            else:
                print(raw[:400])


if __name__ == "__main__":
    asyncio.run(main())
