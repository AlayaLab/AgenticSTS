"""Export disabled silent_card_notes seed file into a reviewable markdown.

Each of the 87 seed entries is classified into one of four buckets so a
human reviewer can quickly decide what (if anything) is worth manually
re-authoring as a trace-grounded note in the live store.

Buckets (ordered by descending review priority):

1. **factual_suspect** — note text contradicts ``data/knowledge/cards.md``
   game mechanics (e.g., "draw 2 discard 2" for a card that draws 1).
2. **tactical** — concrete timing / decision / save-for advice that the
   regular postrun pipeline can't easily reconstruct from raw stats.
3. **tier_or_theory** — tier labels ("A-tier", "premium core") or combo
   theory ("pairs with X") with no specific decision rule. Postrun stats
   already capture relative strength via win rate; restate only if a
   specific synergy decision is non-obvious.
4. **mechanic_restate** — note duplicates cost / effect text already
   present in the prompt's ``## Card Mechanics`` section. Drop unless
   the wording adds tactical nuance.

Output: ``docs/reviews/silent_card_notes_review_<UTC>.md``.

Read-only on the seed file; never modifies the live store.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path


_SEED_FILE_DEFAULT = Path("src/skills/seeds/silent_card_notes.json.disabled")
_FALLBACK_SEED_FILE = Path("src/skills/seeds/silent_card_notes.json")
_KNOWLEDGE_CARDS = Path("data/knowledge/cards.md")
_KNOWLEDGE_BEHAVIORS = Path("data/knowledge/card-behaviors.md")


# Heuristic patterns ─────────────────────────────────────────────────
_TIER_LABELS = re.compile(
    r"\b("
    r"S\+?[-\s]?tier|A\+?[-\s]?tier|B\+?[-\s]?tier|C\+?[-\s]?tier|D[-\s]?tier|"
    r"premium|core|foundational|filler|trap)"
    r"\b",
    re.IGNORECASE,
)
_COST_MECHANIC = re.compile(r"^\s*\d+-cost:?\b", re.IGNORECASE)
_TACTICAL_HINTS = re.compile(
    r"\b("
    r"skip|save\s+for|don'?t\s+play|hold|delay|never|always\s+play|"
    r"play\s+(it\s+)?(before|after|when)|"
    r"avoid|invincible|threshold|priority|bias|defer|"
    r"cap\s+at|over[-\s]thin|cycle\s+through|"
    r"opening|first\s+turn\s+only)"
    r"\b",
    re.IGNORECASE,
)


# ── Knowledge cross-check ────────────────────────────────────────────


def load_card_mechanics() -> dict[str, dict[str, str]]:
    """Return ``{lower_name: {row: <header row>, vars: <Vars cell>}}``.

    ``cards.md`` has cost / type / rarity / target; ``card-behaviors.md``
    has the ``Vars`` column (e.g. ``CardsVar(1)``, ``DamageVar(11m)``).
    Both feed factual_suspect_signal — fail-soft on parse errors.
    """
    out: dict[str, dict[str, str]] = {}

    def _parse_pipe_table(path: Path) -> list[list[str]]:
        rows: list[list[str]] = []
        if not path.exists():
            return rows
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.startswith("|"):
                    continue
                cells = [c.strip() for c in line.strip("|").split("|")]
                if len(cells) < 2:
                    continue
                first = cells[0].lower()
                if first in ("name", "card", "----", ""):
                    continue
                if all(re.fullmatch(r"-+", c or "") for c in cells):
                    continue
                rows.append(cells)
        except Exception:
            pass
        return rows

    for cells in _parse_pipe_table(_KNOWLEDGE_CARDS):
        name = cells[0].lower()
        out.setdefault(name, {})["row"] = " | ".join(cells[1:6])

    for cells in _parse_pipe_table(_KNOWLEDGE_BEHAVIORS):
        name = cells[0].lower()
        if len(cells) >= 2:
            out.setdefault(name, {})["vars"] = cells[1]
    return out


# Map var-prefix → claim keywords found in the note text.
# CardsVar=N means "draw N / discard N" (per Acrobatics, Prepared, etc.).
# DamageVar=N means "deal N damage". BlockVar=N means "gain N Block".
_VAR_TO_CLAIMS = {
    "CardsVar": ("draw", "discard"),
    "DamageVar": ("damage", "deal"),
    "BlockVar": ("block",),
}


def _extract_var_value(vars_cell: str, prefix: str) -> int | None:
    """Pull the first int out of e.g. ``CardsVar(1)`` or ``DamageVar(11m, ...)``."""
    m = re.search(rf"{prefix}\s*\(\s*(\d+)", vars_cell)
    return int(m.group(1)) if m else None


def factual_suspect_signal(note: str, mech: dict[str, str] | None) -> str | None:
    """Return a short reason string if the note's numbers contradict ``mech``."""
    if not mech:
        return None
    vars_cell = mech.get("vars") or ""
    if not vars_cell:
        return None
    note_low = note.lower()

    for prefix, claim_keywords in _VAR_TO_CLAIMS.items():
        truth = _extract_var_value(vars_cell, prefix)
        if truth is None:
            continue
        for kw in claim_keywords:
            for m in re.finditer(rf"\b{kw}\s+(\d+)", note_low):
                claimed = int(m.group(1))
                # Only flag inflated claims. A note saying ``discard 1`` for a
                # card whose CardsVar=3 (draw count) is fine — discard count
                # may be hardcoded separately. We only catch outright
                # over-claims like Prepared "draw 2" when CardsVar=1.
                if claimed > truth:
                    return (
                        f"note says '{kw} {claimed}' but mechanic "
                        f"{prefix}={truth}"
                    )
    return None


def classify(note: str, mech: dict[str, str] | None) -> tuple[str, list[str]]:
    """Return (bucket, reason_tags)."""
    flags: list[str] = []
    suspect = factual_suspect_signal(note, mech)
    if suspect:
        flags.append(f"FACTUAL: {suspect}")

    if _COST_MECHANIC.search(note):
        flags.append("starts-with-cost-mechanic")
    if _TIER_LABELS.search(note):
        flags.append("tier-label")
    if _TACTICAL_HINTS.search(note):
        flags.append("tactical-keyword")

    if suspect:
        return "factual_suspect", flags
    if "tactical-keyword" in flags:
        return "tactical", flags
    if "tier-label" in flags or "Combos with" in note or "Pairs with" in note:
        return "tier_or_theory", flags
    if "starts-with-cost-mechanic" in flags:
        return "mechanic_restate", flags
    return "tier_or_theory", flags  # fallback: ambiguous → mid-priority


# ── Markdown rendering ────────────────────────────────────────────


_BUCKET_ORDER = ("factual_suspect", "tactical", "tier_or_theory", "mechanic_restate")
_BUCKET_HEADERS = {
    "factual_suspect": "1. Factual suspects — note contradicts game mechanics",
    "tactical": "2. Tactical insight — likely worth re-authoring as trace-grounded note",
    "tier_or_theory": "3. Tier label / combo theory — drop unless specific synergy worth keeping",
    "mechanic_restate": "4. Pure mechanic restate — drop (redundant with `## Card Mechanics`)",
}
_BUCKET_GUIDANCE = {
    "factual_suspect": (
        "These notes contradict `data/knowledge/cards.md`. Either fix the wording "
        "or drop entirely; do **not** re-add to the seed file as-is."
    ),
    "tactical": (
        "Concrete timing / save-for / skip-when advice — the kind of insight "
        "postrun stats alone can't reconstruct. Keep candidates here on a "
        "separate review pass; only re-author into live store if a real run "
        "trace will continue to validate the advice."
    ),
    "tier_or_theory": (
        "Tier labels (A-tier, premium, core) are evaluative — postrun's win-rate "
        "/ play-count stats already encode relative strength. Combo theory "
        '("pairs with X") is mostly inferable from card text. Skip unless a '
        "specific synergy is non-obvious."
    ),
    "mechanic_restate": (
        "These restate cost / effect already shown to the agent in the prompt's "
        "`## Card Mechanics` section. Drop without restoration."
    ),
}


def render_markdown(entries: list[dict], mechanics: dict[str, dict[str, str]]) -> str:
    classified: dict[str, list[dict]] = {b: [] for b in _BUCKET_ORDER}
    for e in entries:
        name = (e.get("card_name") or "").strip()
        note = (e.get("note") or "").strip()
        if not note:
            continue
        mech = mechanics.get(name.lower())
        bucket, flags = classify(note, mech)
        classified[bucket].append({
            "card_name": name,
            "note": note,
            "mech_row": (mech or {}).get("row"),
            "mech_vars": (mech or {}).get("vars"),
            "flags": flags,
        })

    today = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
    lines: list[str] = []
    lines.append(f"# Silent card seed-notes review ({today})")
    lines.append("")
    lines.append(
        "Source: `src/skills/seeds/silent_card_notes.json.disabled` (the file "
        "that was auto-injected into `card_memory_store` on every startup; "
        "disabled 2026-04-28 because the entries were encyclopedic / partly "
        "factually wrong, and bypassed the `with_new_note` audit trail)."
    )
    lines.append("")
    lines.append(
        f"Total entries: **{len(entries)}** "
        f"({sum(len(v) for v in classified.values())} with non-empty note)."
    )
    lines.append("")
    lines.append("Bucket sizes:")
    for b in _BUCKET_ORDER:
        lines.append(f"- `{b}`: {len(classified[b])}")
    lines.append("")
    lines.append(
        "Review pass: walk the **factual_suspect** and **tactical** buckets. "
        "For each entry you want to keep, manually call "
        "`CardMemoryStore.with_new_note` on a real run trace, or rewrite the "
        "note inline in the next postrun's `card_note_updater` MANDATORY-first-"
        "note output. **Do not** restore the seed file as a whole — its "
        "auto-inject path bypassed audit and is the bug we are removing."
    )
    lines.append("")

    for b in _BUCKET_ORDER:
        items = classified[b]
        lines.append(f"## {_BUCKET_HEADERS[b]} ({len(items)})")
        lines.append("")
        lines.append(f"_{_BUCKET_GUIDANCE[b]}_")
        lines.append("")
        if not items:
            lines.append("(none)")
            lines.append("")
            continue
        for it in sorted(items, key=lambda x: x["card_name"].lower()):
            lines.append(f"### {it['card_name']}")
            if it["mech_row"]:
                lines.append(f"- card row: `{it['mech_row']}`")
            if it["mech_vars"]:
                lines.append(f"- vars: `{it['mech_vars']}`")
            if it["flags"]:
                lines.append(f"- flags: {', '.join(it['flags'])}")
            lines.append("")
            lines.append(f"> {it['note']}")
            lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--seed-file", type=Path, default=None,
        help="Override seed file path. Default tries .disabled then .json.",
    )
    p.add_argument(
        "--out", type=Path, default=None,
        help="Output markdown path. Default: docs/reviews/silent_card_notes_review_<UTC>.md",
    )
    args = p.parse_args(argv)

    seed_path = args.seed_file
    if seed_path is None:
        if _SEED_FILE_DEFAULT.exists():
            seed_path = _SEED_FILE_DEFAULT
        elif _FALLBACK_SEED_FILE.exists():
            seed_path = _FALLBACK_SEED_FILE
        else:
            print(
                "No seed file found at either "
                f"{_SEED_FILE_DEFAULT} or {_FALLBACK_SEED_FILE}",
                file=sys.stderr,
            )
            return 1

    entries = json.loads(seed_path.read_text(encoding="utf-8"))
    mechanics = load_card_mechanics()
    md = render_markdown(entries, mechanics)

    out = args.out
    if out is None:
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d")
        out = Path("docs") / "reviews" / f"silent_card_notes_review_{ts}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
