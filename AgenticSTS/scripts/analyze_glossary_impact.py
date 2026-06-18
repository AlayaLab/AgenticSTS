"""One-off analysis: measure keyword glossary impact from mechanics_dll extension.

Loads real card rules_text from recent run logs, then simulates Tier 1
(KW_GLOSSARY) + Tier 2 (mechanics_dll.json) matching under BOTH the old keys
(flat-lowercase, no spaces) and the NEW keys (CamelCase → "camel case").

Outputs: (a) bug verification that old multi-word keys never matched,
(b) trigger frequency per keyword, (c) prompt-level token impact estimate.

Not a production script — debug/audit use only.
"""
from __future__ import annotations

import json
import re
import statistics
from pathlib import Path


def load_cards_from_logs(n_logs: int = 5) -> dict[str, str]:
    """Collect unique {card_name: rules_text} from recent combat logs."""
    logs = sorted(
        Path("logs").glob("run_2026041*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:n_logs]
    print(f"Scanning {len(logs)} recent logs")
    cards: dict[str, str] = {}
    for lp in logs:
        with open(lp, encoding="utf-8") as f:
            for line in f:
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if ev.get("event") != "state":
                    continue
                combat = ev.get("combat") or {}
                player = combat.get("player") or {}
                for c in player.get("hand") or []:
                    n = (c.get("name") or "").strip()
                    rt = (c.get("rules_text") or "").strip()
                    if n and rt and n not in cards:
                        cards[n] = rt
                for co in (ev.get("card_reward_details") or {}).get("card_options") or []:
                    n = (co.get("name") or "").strip()
                    rt = (co.get("rules_text") or "").strip()
                    if n and rt and n not in cards:
                        cards[n] = rt
    return cards


def triggered_entries(entries: dict[str, str], text: str) -> set[str]:
    """Return keys whose regex `\\bkey\\b` matches the (lowercased, apostrophe-stripped) text."""
    clean = text.lower().replace("'", "").replace("\u2019", "")
    return {k for k in entries if re.search(rf"\b{re.escape(k)}\b", clean)}


def main() -> None:
    cards = load_cards_from_logs()
    print(f"Unique cards collected: {len(cards)}")

    # Load NEW extracted mechanics (current file on disk after our fix)
    new_mech = json.loads(
        Path("data/knowledge/upstream/mechanics_dll.json").read_text(encoding="utf-8")
    )
    print(f"Current mechanics_dll.json entries: {len(new_mech)}")

    # Reconstruct OLD format: same entries but with broken flat-lowercase keys.
    # Multi-word keys in new are those containing a space; in old they had
    # the spaces stripped (e.g. "perfect fit" was stored as "perfectfit").
    old_mech: dict[str, str] = {}
    for k, v in new_mech.items():
        if " " in k:
            old_mech[k.replace(" ", "")] = v
        else:
            old_mech[k] = v

    # Trim OLD to roughly match pre-extension count (baseline was 33 entries).
    # Drop entries only present in the new extension (status/curse/focus/stun/
    # temporary focus) to approximate pre-extension state.
    NEW_ONLY_PREFIXES = {
        "burn", "void", "dazed", "wound", "slimed", "infection", "toxic",
        "disintegration", "debris", "beckon", "soot", "frantic escape",
        "frantic", "mind rot", "mindrot", "waste away", "wasteaway", "sloth",
        "decay", "regret", "shame", "doubt", "greed", "normality", "clumsy",
        "injury", "bad luck", "badluck", "ascenders bane", "ascendersbane",
        "curse of the bell", "curseofthebell", "poor sleep", "poorsleep",
        "spore mind", "sporemind", "debt", "enthralled", "folly", "guilty",
        "writhe", "focus", "temporary focus", "temporaryfocus", "stun",
        "stunned",
    }
    old_mech_trimmed = {
        k: v for k, v in old_mech.items()
        if k not in NEW_ONLY_PREFIXES and k not in {"burn", "void", "focus"}
    }
    print(f"Baseline (old keys, pre-extension) entries: {len(old_mech_trimmed)}")

    # ── BUG VERIFICATION ──
    # Old multi-word keys never matched. Confirm with real card data.
    old_multi = [k for k in old_mech if k != k.replace(" ", "") or k in (
        "perfectfit", "royallyapproved", "slumberingessence", "soulspower",
        "tezcatarasember",
    )]
    # In old format these are flat-lowercase. Check each against real text.
    print("\n=== BUG VERIFICATION (old flat-lowercase keys) ===")
    broken_keys_sample = [
        "perfectfit", "royallyapproved", "slumberingessence",
        "soulspower", "tezcatarasember",
    ]
    for k in broken_keys_sample:
        hits = [
            n for n, rt in cards.items()
            if re.search(rf"\b{re.escape(k)}\b", rt.lower().replace("'", ""))
        ]
        status = "BUG CONFIRMED — 0 hits" if not hits else f"{len(hits)} hits"
        print(f"  {k:30s}: {status}")
    print("\n=== SAME KEYS UNDER NEW SPLIT-CAMEL FORMAT ===")
    for k in broken_keys_sample:
        new_k = re.sub(r"(?<!^)(?=[A-Z])", " ",
                       k[0].upper() + k[1:]).lower()
        # Hacky reverse — just use the spaced versions directly
    # Use the actual new keys to check:
    for new_k in (
        "perfect fit", "royally approved", "slumbering essence",
        "souls power", "tezcataras ember",
    ):
        hits = [
            n for n, rt in cards.items()
            if re.search(rf"\b{re.escape(new_k)}\b",
                         rt.lower().replace("'", ""))
        ]
        print(f"  {new_k:30s}: {len(hits)} hits")

    # ── TRIGGER FREQUENCY (new entries only) ──
    new_only_entries = {
        k: v for k, v in new_mech.items()
        if k in NEW_ONLY_PREFIXES or (" " in k and k not in old_mech_trimmed)
    }
    print(f"\n=== NEW ENTRIES TRIGGER FREQUENCY (across {len(cards)} unique cards) ===")
    freq: dict[str, list[str]] = {}
    for name, rt in cards.items():
        trig = triggered_entries(new_only_entries, rt)
        for k in trig:
            freq.setdefault(k, []).append(name)
    for k in sorted(freq.keys(), key=lambda x: -len(freq[x])):
        samples = freq[k][:3]
        print(f"  {k:25s} → {len(freq[k]):3d} cards | e.g. {', '.join(samples)}")

    # ── TOKEN IMPACT ──
    per_card_new = []
    per_card_total_new = []
    per_card_total_old = []
    avg_entry_len = sum(len(v) for v in new_mech.values()) / max(1, len(new_mech))

    for name, rt in cards.items():
        trig_new = triggered_entries(new_mech, rt)
        trig_old = triggered_entries(old_mech_trimmed, rt)
        per_card_new.append(len(trig_new - trig_old))
        per_card_total_new.append(len(trig_new))
        per_card_total_old.append(len(trig_old))

    print(f"\n=== TOKEN IMPACT (single card in isolation) ===")
    print(f"  avg glossary entries per card: old={statistics.mean(per_card_total_old):.2f}, "
          f"new={statistics.mean(per_card_total_new):.2f}, "
          f"delta={statistics.mean(per_card_new):.2f}")
    print(f"  avg entry size: {avg_entry_len:.0f} chars (~{avg_entry_len/4:.0f} tokens)")
    added_tokens_per_card = statistics.mean(per_card_new) * avg_entry_len / 4
    print(f"  avg added tokens per single card shown: {added_tokens_per_card:.1f}")

    # ── PROMPT-LEVEL IMPACT ──
    # Real combat prompt shows 5-10 hand cards together. Glossary dedupes —
    # entries trigger ONCE per prompt even if multiple cards share a keyword.
    import random
    random.seed(42)
    card_list = list(cards.items())
    if len(card_list) < 6:
        print("\n(not enough cards for prompt simulation)")
        return
    simulated_new = []
    simulated_delta = []
    for _ in range(500):
        hand = random.sample(card_list, min(6, len(card_list)))
        combined = " ".join(rt for _, rt in hand)
        trig_new = triggered_entries(new_mech, combined)
        trig_old = triggered_entries(old_mech_trimmed, combined)
        simulated_new.append(len(trig_new))
        simulated_delta.append(len(trig_new - trig_old))

    print(f"\n=== PROMPT-LEVEL IMPACT (simulated hands of 6 cards, 500 trials) ===")
    print(f"  avg unique glossary entries triggered: new={statistics.mean(simulated_new):.2f}")
    print(f"  avg NEW entries that trigger (delta):  {statistics.mean(simulated_delta):.2f}")
    added_tokens_per_prompt = statistics.mean(simulated_delta) * avg_entry_len / 4
    print(f"  avg added tokens per combat prompt:    {added_tokens_per_prompt:.0f}")
    print(f"  max observed delta in a single hand:   {max(simulated_delta)}")

    # Worst-case: all new entries triggered
    max_possible_added = len(NEW_ONLY_PREFIXES & set(new_mech.keys())) * avg_entry_len / 4
    print(f"  worst-case if every new entry triggered: ~{max_possible_added:.0f} tokens")


if __name__ == "__main__":
    main()
