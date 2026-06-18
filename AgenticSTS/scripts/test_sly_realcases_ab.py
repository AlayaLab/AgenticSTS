"""A/B/C test on REAL wrong-Sly-decision cases from logs.

Extracts all hand_select discard scenarios where Sly was available but agent
chose a non-Sly card. Tests four prompt variants on each case:
  ORIG: original prompt (with "can't afford" hint)
  A:    keep "Discard = temporary" only
  B:    remove hint entirely
  C:    A + remove Strategy Skills section

Runs 3 iterations per case per variant.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import httpx

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
REPS = 3  # repetitions per case per variant

ORIG_HINT = "Discard = temporary (you'll draw them again). Discard cards you can't afford this turn or don't need right now."
A_HINT = "Discard = temporary (you'll draw them again)."


def collect_wrong_cases(max_logs: int = 100) -> list[dict]:
    """Scan recent logs for hand_select discard where Sly was available but not chosen."""
    log_dir = Path("logs")
    files = sorted(log_dir.glob("run_*.jsonl"), reverse=True)[:max_logs]
    cases = []

    for path in files:
        with open(path) as f:
            events = [json.loads(line) for line in f if line.strip()]

        llm_events = [e for e in events if e.get("event") == "llm_call"]
        for e in llm_events:
            p = e.get("prompt", "")
            if "Hand Selection" not in p or "Choose a card to Discard" not in p:
                continue

            cards_section = re.findall(r"\[index=(\d+)\]\s*(.+)", p)
            sly_indices = set()
            for idx_str, desc in cards_section:
                # Real Sly cards have "Sly." at the start of their rules_text
                # which appears right after the cost/type prefix in the card line
                # e.g. "Ricochet++ (Attack, cost=2): Sly. Deal 4 damage..."
                colon_pos = desc.find(": ")
                if colon_pos >= 0:
                    rules_part = desc[colon_pos + 2:]
                    if rules_part.startswith("Sly."):
                        sly_indices.add(int(idx_str))

            if not sly_indices:
                continue

            resp = e.get("response", "")
            m = re.search(r'"option_index"\s*:\s*(\d+)', resp)
            if not m:
                m2 = re.search(r'"selected_indices"\s*:\s*\[(\d+)', resp)
                if m2:
                    chosen_idx = int(m2.group(1))
                else:
                    continue
            else:
                chosen_idx = int(m.group(1))

            if chosen_idx in sly_indices:
                continue  # correct decision, skip

            card_map = {}
            for idx_str, desc in cards_section:
                card_map[int(idx_str)] = desc.strip()[:80]

            cases.append({
                "file": path.name,
                "system": e.get("system_prompt", ""),
                "prompt": p,
                "sly_indices": sorted(sly_indices),
                "original_choice": chosen_idx,
                "original_card": card_map.get(chosen_idx, "?"),
                "sly_cards": [card_map.get(i, "?") for i in sorted(sly_indices)],
            })

    return cases


def _strip_skills_section(prompt: str) -> str:
    """Remove ## Strategy Skills ... up to the next ## section."""
    m = re.search(r"## Strategy Skills\b.*?(?=\n## (?!Expert|Strategy)|\Z)", prompt, re.DOTALL)
    if m:
        return prompt[:m.start()] + prompt[m.end():]
    return prompt


_HARMFUL_PATTERNS = [
    r"lose \d+ HP",
    r"take \d+ damage",
    r"Unplayable",
]
_HARMFUL_RE = re.compile("|".join(_HARMFUL_PATTERNS), re.IGNORECASE)


def _build_d_variant(prompt_c: str) -> str:
    """D variant: restructure Cards You Can Select with priority groups + improved Sly hint."""
    # 1. Parse all card lines from "## Cards You Can Select"
    cards_match = re.search(
        r"(## Cards You Can Select\n)(.*?)(\n## )",
        prompt_c,
        re.DOTALL,
    )
    if not cards_match:
        return prompt_c

    header = cards_match.group(1)
    cards_block = cards_match.group(2)
    next_section = cards_match.group(3)

    card_lines = re.findall(r"(- \[index=\d+\].+)", cards_block)
    if not card_lines:
        return prompt_c

    sly_lines = []
    harmful_lines = []
    other_lines = []
    for line in card_lines:
        # Extract rules_text (after "): ")
        colon_m = re.search(r"\):\s*(.+)", line)
        rules = colon_m.group(1) if colon_m else ""
        if rules.startswith("Sly."):
            sly_lines.append(line)
        elif _HARMFUL_RE.search(rules):
            harmful_lines.append(line)
        else:
            other_lines.append(line)

    # 2. Rebuild card section with priority groups
    new_cards = header
    if sly_lines:
        new_cards += "### Discard FIRST — plays for free\n"
        for line in sly_lines:
            new_cards += line + "\n"
        new_cards += "\n"
    if harmful_lines:
        new_cards += "### Discard SECOND — remove harmful cards\n"
        for line in harmful_lines:
            new_cards += line + "\n"
        new_cards += "\n"
    if other_lines:
        new_cards += "### Other\n"
        for line in other_lines:
            new_cards += line + "\n"

    result = prompt_c[:cards_match.start()] + new_cards + next_section + prompt_c[cards_match.end():]

    # 3. Replace Sly tactical flag with clearer wording
    old_sly_flag = re.search(r"Sly cards:.+?PLAYS them for free[!.]*", result)
    if old_sly_flag:
        # Extract card names from the old flag
        names_m = re.search(r"Sly cards:\s*(.+?)\.", old_sly_flag.group(0))
        names = names_m.group(1) if names_m else "?"
        new_flag = (
            f"PRIORITY: Discard a Sly card ({names}) to play it for FREE. "
            f"You must discard THE SLY CARD ITSELF — discarding other cards does NOT trigger Sly."
        )
        result = result[:old_sly_flag.start()] + new_flag + result[old_sly_flag.end():]

    # 4. Remove old discard hint if still present
    result = result.replace(A_HINT, "")

    return result


def make_variants(prompt: str) -> dict[str, str]:
    """Create ORIG / A / B / C / D variants of a prompt."""
    has_orig = ORIG_HINT in prompt
    prompt_a = prompt.replace(ORIG_HINT, A_HINT) if has_orig else prompt
    prompt_c = _strip_skills_section(prompt_a)
    prompt_d = _build_d_variant(prompt_c)
    return {
        "ORIG": prompt,
        "A": prompt_a,
        "C": prompt_c,
        "D": prompt_d,
    }


def extract_index(text: str) -> int | None:
    # Try all known index field names
    for pat in [
        r'"option_index"\s*:\s*(\d+)',
        r'"card_index"\s*:\s*(\d+)',
        r'"index"\s*:\s*(\d+)',
        r'"selected_indices"\s*:\s*\[(\d+)',
    ]:
        m = re.search(pat, text)
        if m:
            return int(m.group(1))
    return None


async def call_once(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    system: str,
    prompt: str,
    label: str,
    case_id: int,
    rep: int,
) -> dict:
    async with sem:
        payload = {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": system},
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
                timeout=40.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            idx = extract_index(content)
            return {"label": label, "case": case_id, "rep": rep, "index": idx, "raw": content}
        except Exception as e:
            return {"label": label, "case": case_id, "rep": rep, "index": None, "error": str(e), "raw": ""}


async def main():
    cases = collect_wrong_cases()
    print(f"Found {len(cases)} wrong-Sly cases from logs")
    print(f"Model: {MODEL}, Reps: {REPS}")

    # Check how many have the hint line
    has_hint = sum(1 for c in cases if ORIG_HINT in c["prompt"])
    print(f"Cases with original hint line: {has_hint}/{len(cases)}")
    print()

    for i, c in enumerate(cases):
        sly_str = ", ".join(f"idx={s}" for s in c["sly_indices"])
        print(f"  Case {i}: orig chose idx={c['original_choice']} ({c['original_card'][:40]})")
        print(f"           Sly available: {sly_str}")

    print()
    sem = asyncio.Semaphore(5)
    async with httpx.AsyncClient() as client:
        tasks = []
        for i, c in enumerate(cases):
            variants = make_variants(c["prompt"])
            for label, prompt in variants.items():
                for rep in range(REPS):
                    tasks.append(call_once(client, sem, c["system"], prompt, label, i, rep))

        print(f"Launching {len(tasks)} API calls...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # Aggregate
    # per-variant: how many times chose Sly
    variant_sly: dict[str, int] = defaultdict(int)
    variant_total: dict[str, int] = defaultdict(int)
    variant_errors: dict[str, int] = defaultdict(int)
    # per-case per-variant
    case_results: dict[int, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for r in results:
        if isinstance(r, Exception):
            continue
        if r.get("error"):
            variant_errors[r["label"]] += 1
            continue
        label = r["label"]
        case_id = r["case"]
        idx = r["index"]
        sly_set = set(cases[case_id]["sly_indices"])
        is_sly = idx in sly_set
        variant_total[label] += 1
        if is_sly:
            variant_sly[label] += 1
        case_results[case_id][label].append(idx)

    print()
    print("=" * 70)
    print("AGGREGATE RESULTS")
    print("=" * 70)
    for label in ["ORIG", "A", "C", "D"]:
        total = variant_total[label]
        sly = variant_sly[label]
        errs = variant_errors[label]
        pct = f"{100*sly/total:.0f}%" if total else "N/A"
        print(f"  {label:5s}: Sly chosen {sly}/{total} ({pct}) | errors: {errs}")

    print()
    print("=" * 70)
    print("PER-CASE BREAKDOWN")
    print("=" * 70)
    for i, c in enumerate(cases):
        sly_set = set(c["sly_indices"])
        print(f"\nCase {i}: originally chose idx={c['original_choice']} | Sly={c['sly_indices']}")
        print(f"  {c['original_card'][:60]}")
        for label in ["ORIG", "A", "C", "D"]:
            indices = case_results[i][label]
            sly_count = sum(1 for idx in indices if idx in sly_set)
            idx_str = ", ".join(str(x) for x in indices)
            print(f"  {label:5s}: [{idx_str}] → Sly {sly_count}/{len(indices)}")


    # Show sample None responses
    print()
    print("=" * 70)
    print("SAMPLE NONE RESPONSES (first 3)")
    print("=" * 70)
    none_count = 0
    for r in results:
        if isinstance(r, Exception) or r.get("error"):
            continue
        if r["index"] is None and none_count < 3:
            print(f"\n[{r['label']} case={r['case']} rep={r['rep']}]")
            print(r.get("raw", "")[:500])
            none_count += 1


if __name__ == "__main__":
    asyncio.run(main())
