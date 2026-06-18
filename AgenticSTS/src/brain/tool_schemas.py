"""Response schemas for local validation of LLM <decision> JSON output.

Each game state type has a corresponding schema definition used to validate
the JSON content of <decision> blocks in LLM text responses.

These schemas were originally provider tool definitions. They are now
repurposed as local validation schemas (no longer sent to the LLM API).
"""

from __future__ import annotations

_VISIBLE_COMBAT_ANALYSIS_SCHEMA = {
    "type": "object",
    "description": (
        "Compact visible scratchpad. Use this instead of hidden thinking: "
        "state the tactical problem, compare at least two lines, and explain "
        "why the chosen sequence is best. Keep each field short and concrete."
    ),
    "properties": {
        "problem": {
            "type": "string",
            "description": "Main tactical problem to solve this turn.",
        },
        "key_observations": {
            "type": "array",
            "description": (
                "2-4 short observations driving the turn, including exact block math, "
                "sequencing constraints, or resource preservation."
            ),
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 4,
        },
        "candidate_lines": {
            "type": "array",
            "description": "At least two candidate lines considered before choosing.",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 3,
        },
        "chosen_line": {
            "type": "string",
            "description": "Why the selected line beats the alternatives.",
        },
    },
    "required": ["problem", "key_observations", "candidate_lines", "chosen_line"],
    "additionalProperties": False,
}

# ── Combat (single-card fallback) ─────────────────────────────

COMBAT_TOOL = {
    "name": "combat_action",
    "description": "Choose the next card to play in combat, or end your turn.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play_card", "end_turn"],
            },
            "card_index": {
                "type": "integer",
                "description": "Hand index of card to play (0-based). Use -1 for end_turn.",
            },
            "target_index": {
                "type": "integer",
                "description": (
                    "Index of target enemy (from enemies array). "
                    "Use -1 if no target needed."
                ),
            },
            "reasoning": {
                "type": "string",
                "description": "1-2 sentence decision summary.",
            },
            "analysis": {
                **_VISIBLE_COMBAT_ANALYSIS_SCHEMA,
            },
        },
        "required": ["action", "card_index", "target_index", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Combat Plan (full turn) ──────────────────────────────────

COMBAT_PLAN_TOOL = {
    "name": "combat_plan",
    "description": "Plan the full combat turn: cards to play and potions to use, in order.",
    "input_schema": {
        "type": "object",
        "properties": {
            "plan": {
                "type": "array",
                "description": (
                    "Ordered sequence of actions in exact execution order. "
                    "The first item is executed first, then the second, etc. "
                    "Each is either a card play or potion use."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["card", "potion"],
                            "description": "'card' to play a hand card, 'potion' to use a potion.",
                        },
                        "card": {
                            "type": "string",
                            "description": "Card name (for type=card only). Not used for potions.",
                        },
                        "potion_index": {
                            "type": "integer",
                            "description": (
                                "Potion slot index (for type=potion only). "
                                "Not used for cards."
                            ),
                        },
                        "target_index": {
                            "type": "integer",
                            "description": "Target enemy index. Use -1 if no target needed.",
                        },
                        "discard": {
                            "oneOf": [
                                {
                                    "type": "string",
                                    "description": "Single card name to discard.",
                                },
                                {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "All card names to discard for multi-discard effects "
                                        "(e.g. Prepared+ discarding 2 cards)."
                                    ),
                                },
                            ],
                            "description": (
                                "Card name(s) to discard when this card requires discarding. "
                                "Use a string for one discard or an array for multiple discards. "
                                "Omit if the card has no discard effect."
                            ),
                        },
                    },
                    "required": ["type", "target_index"],
                    "additionalProperties": False,
                },
            },
            "end_turn": {
                "type": "boolean",
                "description": "Whether to end turn after executing the plan.",
            },
            "reasoning": {
                "type": "string",
                "description": "1-2 sentence decision summary for the plan.",
            },
            "analysis": {
                **_VISIBLE_COMBAT_ANALYSIS_SCHEMA,
            },
            "note_to_future_self": {
                "type": "string",
                "description": (
                    "One sentence for future rounds about durable combat "
                    "strategy only. Use stable facts like poison clocks, kill "
                    "windows, saved potions, or enemy scaling. Do NOT claim "
                    "specific cards will be in next turn's hand unless a "
                    "visible Retain/return effect guarantees it. Do NOT "
                    "assume current Block carries over unless a visible effect "
                    "says so. E.g. 'Poison at 15, survive 2 more rounds.' or "
                    "'Save Catalyst for when Vulnerable lands.'"
                ),
            },
        },
        "required": ["plan", "end_turn", "reasoning"],
        "additionalProperties": False,
    },
}

# Shared note scope + trigger fields for strategic note tools
_NOTE_SCOPE_SCHEMA = {
    "note_scope": {
        "type": "string",
        "enum": ["turn", "combat", "run"],
        "description": (
            "How long this note stays relevant. "
            "turn = this combat turn only, combat = until this fight ends, "
            "run = entire run. Default: run."
        ),
    },
    "note_triggers": {
        "type": "array",
        "items": {
            "type": "string",
            "enum": ["combat", "deck_building", "routing", "all"],
        },
        "description": (
            "Which decision types should see this note. "
            "combat = during fights, deck_building = card rewards/shop/card select, "
            "routing = map/rest/event, all = everywhere. Default: ['all']."
        ),
    },
}

_STRATEGIC_NOTE_DESCRIPTION = (
    "One natural-language sentence, not JSON/key-value fields: current deck game plan, "
    "how to pilot its strengths, main missing piece, and what to avoid."
)

# ── Map ───────────────────────────────────────────────────────

MAP_TOOL = {
    "name": "map_action",
    "description": "Choose which map node to visit next.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["choose_map_node"],
            },
            "option_index": {
                "type": "integer",
                "description": "Index of the map node to visit.",
            },
            "reasoning": {
                "type": "string",
            },
            "strategic_note": {
                "type": "string",
                "description": _STRATEGIC_NOTE_DESCRIPTION,
            },
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["action", "option_index", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Rest Site ─────────────────────────────────────────────────

REST_TOOL = {
    "name": "rest_action",
    "description": "Choose a rest site option: smith (upgrade), rest (heal), lift, dig, etc.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["choose_rest_option"],
            },
            "option_index": {
                "type": "integer",
                "description": "Index of the rest option to choose (0-based).",
            },
            "reasoning": {
                "type": "string",
            },
            "strategic_note": {
                "type": "string",
                "description": _STRATEGIC_NOTE_DESCRIPTION,
            },
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["action", "option_index", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Event ─────────────────────────────────────────────────────

EVENT_TOOL = {
    "name": "event_action",
    "description": "Choose an event option by index.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["choose_event_option"],
            },
            "option_index": {
                "type": "integer",
                "description": "Index of the event option to choose.",
            },
            "reasoning": {
                "type": "string",
            },
            "strategic_note": {
                "type": "string",
                "description": _STRATEGIC_NOTE_DESCRIPTION,
            },
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["action", "option_index", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Crystal Sphere ───────────────────────────────────────────

CRYSTAL_SPHERE_TOOL = {
    "name": "crystal_sphere_action",
    "description": (
        "Decide the next move in the Crystal Sphere minigame. "
        "Pick exactly one of: switch divination tool, click a hidden cell, "
        "or proceed to leave the minigame."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "crystal_sphere_set_tool",
                    "crystal_sphere_click_cell",
                    "crystal_sphere_proceed",
                ],
            },
            "tool": {
                "type": "string",
                "enum": ["big", "small"],
                "description": (
                    "Required when action=crystal_sphere_set_tool. "
                    "'big' reveals a 2x2 area; 'small' reveals a single cell."
                ),
            },
            "x": {
                "type": "integer",
                "description": "Required when action=crystal_sphere_click_cell. Grid X coordinate.",
            },
            "y": {
                "type": "integer",
                "description": "Required when action=crystal_sphere_click_cell. Grid Y coordinate.",
            },
            "reasoning": {
                "type": "string",
            },
            "strategic_note": {
                "type": "string",
                "description": _STRATEGIC_NOTE_DESCRIPTION,
            },
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["action", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Shop Plan ────────────────────────────────────────────────

SHOP_PLAN_TOOL = {
    "name": "shop_plan",
    "description": "Plan all shop purchases in one shot. List every item to buy in order, tracking gold after each step.",
    "input_schema": {
        "type": "object",
        "properties": {
            "purchases": {
                "type": "array",
                "description": (
                    "Ordered list of purchases to make. First item is bought first. "
                    "Each entry must include gold_after — the expected remaining gold "
                    "after this purchase completes. Empty array = buy nothing."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "enum": ["buy_card", "buy_relic", "buy_potion", "remove_card", "discard_potion"],
                            "description": (
                                "Purchase type. Use discard_potion (with item_name = held-potion name) "
                                "to free a slot BEFORE a buy_potion when slots are full."
                            ),
                        },
                        "item_name": {
                            "type": "string",
                            "description": (
                                "Exact item name from the shop listing, OR for discard_potion: "
                                "name of the held potion to discard."
                            ),
                        },
                        "price": {
                            "type": "integer",
                            "description": "Item price in gold.",
                        },
                        "gold_after": {
                            "type": "integer",
                            "description": "Expected remaining gold AFTER this purchase.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why this purchase matters for the run.",
                        },
                    },
                    "required": ["action", "item_name", "price", "gold_after", "reason"],
                    "additionalProperties": False,
                },
            },
            "skipped_items": {
                "type": "array",
                "description": (
                    "Affordable items you chose NOT to buy and why. "
                    "Include every affordable item not in the purchases list."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "item_name": {
                            "type": "string",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why you are skipping this item.",
                        },
                    },
                    "required": ["item_name", "reason"],
                    "additionalProperties": False,
                },
            },
            "reasoning": {
                "type": "string",
                "description": "Overall shop strategy summary: budget allocation, deck needs, priority ordering.",
            },
            "strategic_note": {
                "type": "string",
                "description": _STRATEGIC_NOTE_DESCRIPTION,
            },
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["purchases", "skipped_items", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Card Reward ───────────────────────────────────────────────

CARD_REWARD_TOOL = {
    "name": "card_reward_action",
    "description": "Pick a card reward, a reward alternative, or discard a held potion to free a slot for a new reward potion.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["choose_reward_card", "choose_reward_alternative", "discard_potion"],
            },
            "option_index": {
                "type": "integer",
                "description": (
                    "For choose_reward_card: card index to pick. "
                    "For choose_reward_alternative: alternative index. "
                    "For discard_potion: held-potion slot index (0/1/2)."
                ),
            },
            "reasoning": {
                "type": "string",
            },
            "strategic_note": {
                "type": "string",
                "description": _STRATEGIC_NOTE_DESCRIPTION,
            },
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["action", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Card Select (upgrade/remove/enchant) ─────────────────────

CARD_SELECT_TOOL = {
    "name": "card_select_action",
    "description": "Select one or more cards to upgrade, remove, or enchant.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["select_deck_card"],
            },
            "selected_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Ordered list of card indices to select. "
                    "For multi-card selection (e.g. 'Choose 5 cards to Remove'), "
                    "include ALL required indices in one call. "
                    "For single-card, use a one-element array."
                ),
            },
            "reasoning": {
                "type": "string",
            },
            "strategic_note": {
                "type": "string",
                "description": _STRATEGIC_NOTE_DESCRIPTION,
            },
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["action", "selected_indices", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Hand Select (discard/exhaust) ─────────────────────────────

HAND_SELECT_TOOL = {
    "name": "hand_select_action",
    "description": (
        "Select one or more cards from hand, or confirm without selecting "
        "when the prompt allows choosing zero cards."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["select_deck_card", "confirm_selection"],
            },
            "selected_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": (
                    "Ordered list of card indices to select. "
                    "For multi-card (e.g. 'Discard 2'), include ALL indices. "
                    "For single-card, use a one-element array. "
                    "Omit this field when using confirm_selection to keep zero cards."
                ),
            },
            "reasoning": {
                "type": "string",
            },
        },
        "required": ["action", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Treasure ──────────────────────────────────────────────────

TREASURE_TOOL = {
    "name": "treasure_action",
    "description": "Claim or skip a treasure relic.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["choose_treasure_relic", "proceed"],
            },
            "option_index": {
                "type": "integer",
                "description": "Index of the relic to claim. Use -1 for proceed/skip.",
            },
            "reasoning": {
                "type": "string",
            },
        },
        "required": ["action", "option_index", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Relic Select ──────────────────────────────────────────────

RELIC_SELECT_TOOL = {
    "name": "relic_select_action",
    "description": "Select a relic from the offered options.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["choose_treasure_relic"],
            },
            "option_index": {
                "type": "integer",
                "description": "Index of the relic to select.",
            },
            "reasoning": {
                "type": "string",
            },
        },
        "required": ["action", "option_index", "reasoning"],
        "additionalProperties": False,
    },
}

# ── Potion ────────────────────────────────────────────────────

POTION_TOOL = {
    "name": "potion_action",
    "description": "Use a potion or skip.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["use_potion", "skip_potion"],
            },
            "option_index": {
                "type": "integer",
                "description": "Potion slot index. Use -1 for skip.",
            },
            "target_index": {
                "type": "integer",
                "description": (
                    "Index of target enemy (from enemies array). "
                    "Use -1 if not targeted."
                ),
            },
            "reasoning": {
                "type": "string",
            },
        },
        "required": ["action", "option_index", "target_index", "reasoning"],
        "additionalProperties": False,
    },
}


# ── State type → tool mapping ─────────────────────────────────

_STATE_TOOL_MAP: dict[str, dict] = {
    "monster": COMBAT_TOOL,
    "elite": COMBAT_TOOL,
    "boss": COMBAT_TOOL,
    "map": MAP_TOOL,
    "rest_site": REST_TOOL,
    "event": EVENT_TOOL,
    "crystal_sphere": CRYSTAL_SPHERE_TOOL,
    "shop": SHOP_PLAN_TOOL,
    "card_reward": CARD_REWARD_TOOL,
    "card_select": CARD_SELECT_TOOL,
    "bundle_select": CARD_SELECT_TOOL,
    "hand_select": HAND_SELECT_TOOL,
    "treasure": TREASURE_TOOL,
    "relic_select": RELIC_SELECT_TOOL,
    "potion": POTION_TOOL,
}


def get_tool_for_state(state_type: str, *, gs=None) -> dict | None:
    """Get the tool definition for a game state type, or None if not mapped.

    When *gs* is provided and state_type is ``hand_select``, the returned
    tool schema is adjusted based on ``gs.selection.min_select``:
    - min_select > 0 (mandatory discard): only ``select_deck_card`` allowed
    - min_select == 0 (optional): both ``select_deck_card`` and ``confirm_selection``
    This prevents the LLM from choosing ``confirm_selection`` when the game
    only accepts ``select_deck_card`` (mandatory selections).
    """
    import copy

    tool = _STATE_TOOL_MAP.get(state_type)
    if tool is None:
        return None

    # Dynamically restrict hand_select actions based on game state
    if state_type == "hand_select" and gs is not None:
        sel = gs.selection
        if sel and sel.min_select and sel.min_select > 0:
            # Mandatory selection: strip confirm_selection from enum
            tool = copy.deepcopy(tool)
            action_prop = tool["input_schema"]["properties"]["action"]
            action_prop["enum"] = ["select_deck_card"]
            # Also make selected_indices required for mandatory selections
            required = tool["input_schema"].get("required", [])
            if "selected_indices" not in required:
                tool["input_schema"]["required"] = list(required) + ["selected_indices"]

    # Dynamically allow confirm_selection for "any number" card_select (min=0)
    if state_type == "card_select" and gs is not None:
        sel = gs.selection
        if sel and (not sel.min_select or sel.min_select == 0):
            # Optional selection: allow confirm_selection to skip
            tool = copy.deepcopy(tool)
            action_prop = tool["input_schema"]["properties"]["action"]
            action_prop["enum"] = ["select_deck_card", "confirm_selection"]
            required = tool["input_schema"].get("required", [])
            tool["input_schema"]["required"] = [
                field for field in required if field != "selected_indices"
            ]

    return tool


