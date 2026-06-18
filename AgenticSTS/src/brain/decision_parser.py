# src/brain/decision_parser.py
"""Extract and validate <decision> JSON blocks from LLM text responses.

Replaces tool_use protocol for gameplay decisions.
Schemas are sourced from tool_schemas.py (repurposed as local validation schemas).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Match the last <decision>...</decision> block in the text
_DECISION_RE = re.compile(
    r"<decision>\s*(.*?)\s*</decision>",
    re.DOTALL,
)

# Required fields per decision tool (field_name -> True if required)
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "combat_plan": ["plan", "end_turn", "reasoning"],
    "combat_action": ["action", "card_index", "target_index", "reasoning"],
    "map_action": ["action", "option_index", "reasoning"],
    "rest_action": ["action", "option_index", "reasoning"],
    "event_action": ["action", "option_index", "reasoning"],
    "shop_plan": ["purchases", "skipped_items", "reasoning"],
    "card_reward_action": ["action", "reasoning"],
    "card_select_action": ["action", "reasoning"],
    "hand_select_action": ["action", "reasoning"],
    "treasure_action": ["action", "option_index", "reasoning"],
    "relic_select_action": ["action", "option_index", "reasoning"],
    "potion_action": ["action", "option_index", "target_index", "reasoning"],
}

# Valid action enums per decision tool
_ACTION_ENUMS: dict[str, list[str]] = {
    "combat_action": ["play_card", "end_turn"],
    "map_action": ["choose_map_node"],
    "rest_action": ["choose_rest_option"],
    "event_action": ["choose_event_option"],
    "card_reward_action": ["choose_reward_card", "choose_reward_alternative", "discard_potion"],
    "card_select_action": ["select_deck_card", "confirm_selection"],
    "hand_select_action": ["select_deck_card", "confirm_selection"],
    "treasure_action": ["choose_treasure_relic", "proceed"],
    "relic_select_action": ["choose_treasure_relic"],
    "potion_action": ["use_potion", "skip_potion"],
}


def normalize_decision_payload(
    data: dict[str, Any], tool_name: str,
) -> dict[str, Any]:
    """Normalize recoverable schema drift before validation.

    Combat plans are the main case in practice: some models omit
    ``end_turn`` even though the executor/parser already treats it as
    ``True`` by default, and they may emit ``reasoning`` as a list of
    bullet strings instead of a single sentence.
    """
    if tool_name != "combat_plan":
        return data

    normalized = dict(data)
    normalized.setdefault("end_turn", True)

    reasoning = normalized.get("reasoning")
    if isinstance(reasoning, list | tuple):
        normalized["reasoning"] = " ".join(
            text for item in reasoning if (text := str(item).strip())
        )
    elif reasoning is None:
        normalized["reasoning"] = ""
    elif not isinstance(reasoning, str):
        normalized["reasoning"] = str(reasoning)

    if not normalized.get("reasoning"):
        analysis = normalized.get("analysis")
        chosen_line = analysis.get("chosen_line") if isinstance(analysis, dict) else None
        if chosen_line:
            normalized["reasoning"] = str(chosen_line)

    return normalized


_DOUBLE_COLON_RE = re.compile(
    r'("(?:[^"\\]|\\.)*"\s*:\s*"(?:[^"\\]|\\.)*")(\s*:\s*(?:true|false|null|-?\d[\d.eE+\-]*))'
)


def _preprocess_json(raw: str) -> str:
    """Lightweight text fixes before JSON parsing.

    Handles known Qwen generation glitches:
    - "type": "end_turn": true  →  "type": "end_turn"
      (model conflates plan-item key with top-level boolean field)
    """
    fixed = _DOUBLE_COLON_RE.sub(r"\1", raw)
    return fixed


def _repair_unclosed_arrays(text: str) -> str:
    """Fix JSON where ] was replaced by } in the trailing bracket sequence.

    Qwen 35b sometimes emits }}}} instead of }}]} — simultaneously generating
    an extra } and omitting the ] that closes the plan array.  We trim the extra
    } from the trailing run and try every insertion point for the missing ].
    """
    in_string = False
    escape_next = False
    open_braces = 0
    open_brackets = 0
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            open_braces += 1
        elif ch == "}":
            open_braces -= 1
        elif ch == "[":
            open_brackets += 1
        elif ch == "]":
            open_brackets -= 1
    if open_brackets <= 0:
        return text
    stripped = text.rstrip()
    i = len(stripped)
    while i > 0 and stripped[i - 1] == "}":
        i -= 1
    # Trim extra } (model emitted one extra for each missing ])
    extra_close = max(0, -open_braces)
    body = stripped[:i]
    trailing = stripped[i:]
    if extra_close:
        trailing = trailing[extra_close:]
    closing = "]" * open_brackets
    for pos in range(len(trailing) + 1):
        candidate = body + trailing[:pos] + closing + trailing[pos:]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            continue
    return text


def extract_decision(text: str, *, allow_fallback: bool = False) -> dict[str, Any] | None:
    """Extract the last <decision> JSON block from LLM text.

    Returns parsed dict or None if no valid block found.
    If allow_fallback=True, also tries raw JSON extraction (code fences, bare JSON).
    """
    matches = _DECISION_RE.findall(text)
    if matches:
        raw = matches[-1].strip()
        preprocessed = _preprocess_json(raw)
        for candidate in dict.fromkeys([preprocessed, _repair_unclosed_arrays(preprocessed)]):
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    if candidate != raw:
                        logger.debug("Repaired <decision> JSON")
                    return _flatten_params(parsed)
            except json.JSONDecodeError:
                pass
        logger.debug("Failed to parse <decision> JSON: %s", raw[:200])

    if allow_fallback:
        result = _try_raw_json(text)
        if result is not None:
            return _flatten_params(result)

    return None


def _flatten_params(data: dict[str, Any]) -> dict[str, Any]:
    """Flatten a nested ``"params"`` wrapper into the top-level dict.

    Some models (Gemini) wrap fields like ``option_index`` inside a
    ``"params"`` object instead of placing them at the top level.
    E.g. ``{"action": "buy_card", "params": {"option_index": 0}}``
    → ``{"action": "buy_card", "option_index": 0}``.

    Top-level keys always take precedence over keys inside ``params``.
    """
    params = data.get("params")
    if not isinstance(params, dict):
        return data
    merged = {k: v for k, v in params.items() if k not in data}
    merged.update({k: v for k, v in data.items() if k != "params"})
    return merged


def _try_raw_json(text: str) -> dict[str, Any] | None:
    """Fallback: try to extract JSON from code fences or bare text."""
    stripped = text.strip()

    # Strip markdown code fences
    if "```" in stripped:
        lines = stripped.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        parsed = json.loads(stripped[start:end + 1])
        if isinstance(parsed, dict) and parsed:
            return parsed
    except json.JSONDecodeError:
        pass

    return None


def validate_decision(data: dict[str, Any], tool_name: str) -> list[str]:
    """Validate a parsed decision dict against its schema.

    Returns list of error strings. Empty list = valid.
    """
    errors: list[str] = []

    required = _REQUIRED_FIELDS.get(tool_name, [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: {field}")

    valid_actions = _ACTION_ENUMS.get(tool_name)
    allowed_actions = list(valid_actions) if valid_actions else []
    if tool_name == "card_reward_action":
        allowed_actions.extend(["skip_reward_cards", "sacrifice_reward_cards"])
    if allowed_actions and "action" in data:
        if data["action"] not in allowed_actions:
            errors.append(
                f"Invalid action '{data['action']}' — must be one of: {allowed_actions}"
            )

    if tool_name == "card_reward_action":
        if data.get("action") in {"choose_reward_card", "choose_reward_alternative"} and "option_index" not in data:
            errors.append(
                f"Missing required field: option_index (required for {data.get('action')})"
            )

    if tool_name == "card_select_action":
        action = data.get("action")
        selected = data.get("selected_indices")
        if (
            action == "select_deck_card"
            and "selected_indices" not in data
            and "option_index" not in data
        ):
            errors.append("Missing required field: selected_indices or option_index")
        if action == "confirm_selection" and "selected_indices" in data:
            errors.append("selected_indices must be omitted when action=confirm_selection")
        if selected is not None and not isinstance(selected, list):
            errors.append("selected_indices must be an array when provided")

    if tool_name == "hand_select_action":
        action = data.get("action")
        selected = data.get("selected_indices")
        if action == "select_deck_card" and "selected_indices" not in data:
            errors.append("Missing required field: selected_indices")
        if action == "confirm_selection" and "selected_indices" in data:
            errors.append("selected_indices must be omitted when action=confirm_selection")
        if selected is not None and not isinstance(selected, list):
            errors.append("selected_indices must be an array when provided")

    return errors


def format_repair_message(errors: list[str], tool_name: str = "") -> str:
    """Format a repair prompt for the LLM when validation fails."""
    error_text = "; ".join(errors)
    hint = ""
    if tool_name == "card_reward_action" and "option_index" in error_text:
        hint = (
            ' Example: <decision>{"action": "choose_reward_card", '
            '"option_index": 0, "reasoning": "..."}</decision>'
        )
    if tool_name == "hand_select_action" and "selected_indices" in error_text:
        hint = (
            ' selected_indices must be an array of integer card indices. '
            'Example: <decision>{"action": "select_deck_card", '
            '"selected_indices": [2], "reasoning": "..."}</decision>'
        )
    return (
        f"Your response did not contain a valid <decision> block. "
        f"Error: {error_text}. "
        f"Please respond with a valid <decision> block.{hint}"
    )


def format_decision_schema_hint(
    tool_name: str,
    *,
    allowed_actions: list[str] | None = None,
) -> str:
    """Format a compact schema hint for the decision tool.

    Injects valid action names + required fields so the model knows the
    exact format without relying on examples in the system prompt.
    Returns empty string for combat_plan (schema shown in system prompt).

    *allowed_actions* overrides the static ``_ACTION_ENUMS`` when the tool
    schema has been dynamically adjusted (e.g. mandatory hand_select).
    """
    if tool_name == "combat_plan":
        return ""
    required = list(_REQUIRED_FIELDS.get(tool_name, []))
    actions = allowed_actions or _ACTION_ENUMS.get(tool_name)
    if not required:
        return ""

    # For mandatory hand_select/card_select (confirm_selection stripped from schema),
    # selected_indices is effectively required — add it to the displayed fields so
    # the model knows it must be included.
    is_mandatory_select = (
        tool_name in {"card_select_action", "hand_select_action"}
        and actions is not None
        and "select_deck_card" in actions
        and "confirm_selection" not in actions
        and "selected_indices" not in required
    )
    if is_mandatory_select:
        required = required + ["selected_indices"]

    parts = [f"## Decision Format ({tool_name})"]
    if actions:
        parts.append(f"Valid actions: {' | '.join(actions)}")
    parts.append(f"Required fields: {', '.join(required)}")
    if tool_name in {"card_select_action", "hand_select_action"} and actions:
        if "confirm_selection" in actions:
            parts.append(
                "If action=select_deck_card, include selected_indices (array of card indices). "
                "If action=confirm_selection, omit selected_indices."
            )
        elif "select_deck_card" in actions:
            # Mandatory selection — give a concrete format reminder
            parts.append(
                "selected_indices must be an array of integer card indices "
                "(e.g. [2] to select card at index 2, [0, 3] to select two cards)."
            )
    if tool_name == "card_reward_action":
        parts.append(
            "If action=choose_reward_card or choose_reward_alternative, "
            "option_index is REQUIRED (the card index or alt index to pick)."
        )
    _STRATEGIC_NOTE_TOOLS = {
        "map_action", "rest_action", "event_action",
        "shop_plan", "card_reward_action", "card_select_action",
    }
    if tool_name in _STRATEGIC_NOTE_TOOLS:
        parts.append(
            "Optional: strategic_note, note_scope (turn|combat|run), "
            "note_triggers (combat|deck_building|routing|all)"
        )
        parts.append("strategic_note must be plain prose, not JSON or key-value fields.")
    return "\n".join(parts)
