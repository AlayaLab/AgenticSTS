"""Parse card_reward decisions from LLM response text."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionVerdict:
    """Parsed decision from one resample response."""
    action: str = ""
    option_index: int | None = None
    is_skip: bool = False
    malformed: bool = False
    raw_decision: str = ""


_DECISION_RE = re.compile(r"<decision>\s*(\{.*?\})\s*</decision>", re.DOTALL)


def parse_card_reward_decision(response_text: str) -> DecisionVerdict:
    """Extract action + option_index from a card_reward response.

    Returns ``malformed=True`` if no <decision> block, invalid JSON, or
    missing required fields.
    """
    if not response_text:
        return DecisionVerdict(malformed=True)
    m = _DECISION_RE.search(response_text)
    if m is None:
        return DecisionVerdict(malformed=True)
    raw = m.group(1)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return DecisionVerdict(malformed=True, raw_decision=raw)
    action = str(obj.get("action") or "")
    option_index = obj.get("option_index")
    if action not in ("choose_reward_card", "choose_reward_alternative", "discard_potion"):
        return DecisionVerdict(malformed=True, raw_decision=raw)
    if action != "discard_potion":
        if not isinstance(option_index, int):
            return DecisionVerdict(malformed=True, action=action, raw_decision=raw)
    is_skip = action == "choose_reward_alternative"
    return DecisionVerdict(
        action=action,
        option_index=option_index if isinstance(option_index, int) else None,
        is_skip=is_skip,
        malformed=False,
        raw_decision=raw,
    )
