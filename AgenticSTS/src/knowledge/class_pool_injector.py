"""Class pool injector — render the full class card pool as a system-prompt
reference section for postrun Turn 1 / Turn 2.

Reads `data/knowledge/upstream/cards.json` once per process per character;
filters by `color` field. Output is a pipe-delimited table prepended with a
hedge line warning the LLM not to claim cards were in the run.

Gameplay-time prompts (reward, shop, card_select) do NOT use this module.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.memory.models_v2 import normalize_character

logger = logging.getLogger(__name__)

_CARDS_JSON = (
    Path(__file__).parent.parent.parent
    / "data" / "knowledge" / "upstream" / "cards.json"
)

_SECTION_CACHE: dict[str, str] = {}
_POOL_CACHE: dict[str, frozenset[str]] = {}
_CARDS_JSON_CACHE: list[dict] | None = None

# Map normalize_character() output to the cards.json `color` field.
# normalize_character("Silent") -> "the silent"; cards.json uses "silent".
_CHARACTER_TO_COLOR: dict[str, str] = {
    "the silent": "silent",
    "the regent": "regent",
    "the defect": "defect",
    "the ironclad": "ironclad",
    "the necrobinder": "necrobinder",
}

_DISPLAY_NAME: dict[str, str] = {
    "the silent": "Silent",
    "the regent": "Regent",
    "the defect": "Defect",
    "the ironclad": "Ironclad",
    "the necrobinder": "Necrobinder",
}


def _strip_bbcode(text: str) -> str:
    """Remove BBCode tags. Keep inner text."""
    text = re.sub(r"\[img\][^\[]*\[/img\]", "", text)
    text = re.sub(r"\[/?[a-zA-Z_]+(?:=[^\]]*)?\]", "", text)
    return text


def _load_cards_json() -> list[dict]:
    """Load and return the upstream cards.json payload (list of dicts)."""
    try:
        with _CARDS_JSON.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        logger.warning(
            "class_pool_injector: failed to read %s", _CARDS_JSON, exc_info=True,
        )
        return []


def _filter_class_cards(character: str) -> list[dict]:
    global _CARDS_JSON_CACHE
    char_norm = normalize_character(character)
    color = _CHARACTER_TO_COLOR.get(char_norm)
    if not color:
        return []
    if _CARDS_JSON_CACHE is None:
        _CARDS_JSON_CACHE = _load_cards_json()
    return [c for c in _CARDS_JSON_CACHE if c.get("color") == color]


def _format_card_line(card: dict) -> str:
    name = str(card.get("name") or "").strip()
    cost = card.get("cost")
    if card.get("is_x_cost"):
        cost_str = "X"
    elif cost is not None:
        cost_str = str(cost)
    else:
        cost_str = "?"
    typ = str(card.get("type") or "").strip()
    rarity = str(card.get("rarity") or "").strip()
    target = str(card.get("target") or "").strip()
    desc = _strip_bbcode(str(card.get("description") or "")).replace("\n", " ").strip()
    desc = re.sub(r"\s+", " ", desc)
    return f"- {name} | {cost_str} | {typ} | {rarity} | {target} | {desc}"


def render_class_pool_section(character: str) -> str:
    """Return a system-prompt section listing every card in the character's
    class pool. Returns empty string when the character is unknown.

    Format (one body line per card, pipe-delimited):
        - Name | Cost | Type | Rarity | Target | Description

    BBCode is stripped from descriptions; newlines flattened to spaces.
    Section is cached per-character for the lifetime of the process.
    """
    char_norm = normalize_character(character)
    if char_norm in _SECTION_CACHE:
        return _SECTION_CACHE[char_norm]

    cards = _filter_class_cards(character)
    if not cards:
        _SECTION_CACHE[char_norm] = ""
        return ""

    display = _DISPLAY_NAME.get(char_norm, char_norm.title())
    header = f"## Class Pool Reference ({display} — {len(cards)} cards)"
    hedge = (
        "This is the FULL static class pool, not what the run actually saw. "
        "Use as combo-space awareness only. Never claim a card was in this "
        "run unless the trace evidence shows it."
    )
    schema = "Name | Cost | Type | Rarity | Target | Description"
    body = "\n".join(_format_card_line(c) for c in cards)

    section = f"{header}\n\n{hedge}\n\n{schema}\n{body}"
    _SECTION_CACHE[char_norm] = section
    return section


def class_pool_card_names(character: str) -> frozenset[str]:
    """Return a lowercased frozenset of card names in the character's pool.

    Used by Turn 2 bucket-B validation rule 1 (card must be in class pool)
    and rule 2 (card must NOT be in deck — caller intersects manually).
    """
    char_norm = normalize_character(character)
    if char_norm in _POOL_CACHE:
        return _POOL_CACHE[char_norm]
    cards = _filter_class_cards(character)
    names = frozenset(
        str(c.get("name") or "").strip().lower()
        for c in cards if c.get("name")
    )
    _POOL_CACHE[char_norm] = names
    return names
