"""Probe text-embedding-3-large via the GPT relay.

One-shot test: verify the relay supports embeddings and cosine similarities make
semantic sense. Run from repo root:

    python -m scripts.probe_embedding
"""

from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

# Load .env (same pattern as config.py)
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.is_file():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ[_k.strip()] = _v.strip()

from openai import OpenAI  # noqa: E402

MODEL = "text-embedding-3-large"

CASES: list[tuple[str, str]] = [
    # (category, text)
    ("L1_mechanic",   "Energy resets to 3 each turn. Unspent energy is wasted."),
    ("skill_dup_L1",  "Always use all your energy — unspent energy is permanently wasted every turn."),
    ("skill_unrelated", "After an elite fight, prefer Rest over Smith if HP is below 40%."),
    ("card_note",     "Piercing Wail: A-tier defense. Save/retain for the scariest attack turn; absurd vs multi-hit and still great vs spikes."),
    ("card_note_dup", "piercing wail is a strong defensive skill — best used against multi-hit attacks or spike turns."),
    ("guide_deck",    "Aim for a compact midgame deck around 15-18 cards. Very tiny Act 1 decks died early, but bloated 24-card piles were also weak."),
    ("skill_trigger_same", "When hand has only block cards and enemy intents are all attack, play every block card before ending turn."),
    ("skill_trigger_diff", "When at a rest site before a boss floor, prefer Rest over Smith if HP is below 50%."),
]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    api_key = os.getenv("STS2_GPT_API_KEY")
    base_url = os.getenv("STS2_GPT_BASE_URL", "https://proxy.example.com")
    if not api_key:
        print("ERROR: STS2_GPT_API_KEY not set in env", file=sys.stderr)
        return 1

    # The relay at proxy.example.com uses the OpenAI-compatible v1 path.
    if not base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    client = OpenAI(api_key=api_key, base_url=base_url)

    print(f"relay  : {base_url}")
    print(f"model  : {MODEL}")
    print(f"inputs : {len(CASES)}")
    print()

    inputs = [text for (_, text) in CASES]

    t0 = time.time()
    try:
        resp = client.embeddings.create(model=MODEL, input=inputs)
    except Exception as exc:
        print(f"ERROR calling embeddings.create: {exc}", file=sys.stderr)
        return 2
    latency = time.time() - t0

    vecs: list[list[float]] = [d.embedding for d in resp.data]
    dim = len(vecs[0])
    total_input_tokens = getattr(resp.usage, "prompt_tokens", None) or getattr(resp.usage, "total_tokens", 0)

    print(f"ok     : dim={dim}, latency={latency:.2f}s, input_tokens={total_input_tokens}")
    print()

    # Pairwise cosine table
    labels = [cat for (cat, _) in CASES]
    n = len(labels)
    print("pairwise cosine:")
    header = "             " + "  ".join(f"{i:>3}" for i in range(n))
    print(header)
    for i in range(n):
        row = []
        for j in range(n):
            c = cosine(vecs[i], vecs[j])
            row.append(f"{c:5.2f}")
        print(f"{i} {labels[i][:10]:<10} " + "  ".join(row))
    print()

    # Highlight the pairs that matter for the write-gate decisions
    pairs_of_interest = [
        (0, 1, "L1 mechanic vs candidate restating L1 (should be HIGH)"),
        (0, 2, "L1 mechanic vs unrelated rest-site skill (should be LOW)"),
        (3, 4, "card note vs near-paraphrase card note (should be HIGH)"),
        (5, 0, "deck guide vs L1 mechanic (should be LOW)"),
        (6, 7, "combat skill vs rest-site skill (should be LOW — different scope)"),
    ]
    print("diagnostic pairs:")
    for i, j, desc in pairs_of_interest:
        c = cosine(vecs[i], vecs[j])
        print(f"  cos({labels[i]:<22}, {labels[j]:<22}) = {c:5.3f}   {desc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
