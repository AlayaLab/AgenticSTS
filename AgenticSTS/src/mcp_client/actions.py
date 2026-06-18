"""Action builders for the STS2-Agent REST API.

Each function returns a dict ready for McpClient.post_action().
All action names and parameter names match the upstream API contract.
"""

from __future__ import annotations

# ── Combat ───────────────────────────────────────────────────


def play_card(card_index: int, target_index: int | None = None) -> dict:
    body: dict = {"action": "play_card", "card_index": card_index}
    if target_index is not None:
        body["target_index"] = target_index
    return body


def end_turn() -> dict:
    return {"action": "end_turn"}


def use_potion(option_index: int, target_index: int | None = None) -> dict:
    body: dict = {"action": "use_potion", "option_index": option_index}
    if target_index is not None:
        body["target_index"] = target_index
    return body


def discard_potion(option_index: int) -> dict:
    return {"action": "discard_potion", "option_index": option_index}


def select_deck_card(option_index: int) -> dict:
    return {"action": "select_deck_card", "option_index": option_index}


def confirm_selection() -> dict:
    return {"action": "confirm_selection"}


def cancel_selection() -> dict:
    return {"action": "cancel_selection"}


def close_cards_view() -> dict:
    return {"action": "close_cards_view"}


# ── Rewards ──────────────────────────────────────────────────


def claim_reward(option_index: int) -> dict:
    return {"action": "claim_reward", "option_index": option_index}


def choose_reward_card(option_index: int) -> dict:
    return {"action": "choose_reward_card", "option_index": option_index}


def choose_reward_alternative(option_index: int) -> dict:
    return {"action": "choose_reward_alternative", "option_index": option_index}


def skip_reward_cards() -> dict:
    return {"action": "skip_reward_cards"}


def sacrifice_reward_cards() -> dict:
    """Sacrifice this card reward (Pael's Wing relic: every 2 sacrifices → 1 relic)."""
    return {"action": "sacrifice_reward_cards"}


def collect_rewards_and_proceed() -> dict:
    return {"action": "collect_rewards_and_proceed"}


def resolve_rewards(option_index: int | None = None) -> dict:
    """Atomic reward resolution.

    The mod auto-claims gold/relic/potion (potion gated on slots) and
    handles the card reward in one round-trip.

    option_index semantics:
      -1   → skip the card reward (mod clicks the skip alternative)
      >= 0 → pick that card index from the card_reward screen
      None → leave the card un-picked (combat_rewards drain only)
    """
    payload: dict = {"action": "resolve_rewards"}
    if option_index is not None:
        payload["option_index"] = option_index
    return payload


def proceed() -> dict:
    return {"action": "proceed"}


# ── Navigation & Events ─────────────────────────────────────


def choose_map_node(option_index: int) -> dict:
    return {"action": "choose_map_node", "option_index": option_index}


def choose_event_option(option_index: int) -> dict:
    return {"action": "choose_event_option", "option_index": option_index}


def crystal_sphere_set_tool(tool: str) -> dict:
    return {"action": "crystal_sphere_set_tool", "tool": tool}


def crystal_sphere_click_cell(x: int, y: int) -> dict:
    return {"action": "crystal_sphere_click_cell", "x": x, "y": y}


def crystal_sphere_proceed() -> dict:
    return {"action": "crystal_sphere_proceed"}


def choose_rest_option(option_index: int) -> dict:
    return {"action": "choose_rest_option", "option_index": option_index}


# ── Shop ─────────────────────────────────────────────────────


def open_shop_inventory() -> dict:
    return {"action": "open_shop_inventory"}


def close_shop_inventory() -> dict:
    return {"action": "close_shop_inventory"}


def buy_card(option_index: int) -> dict:
    return {"action": "buy_card", "option_index": option_index}


def buy_relic(option_index: int) -> dict:
    return {"action": "buy_relic", "option_index": option_index}


def buy_potion(option_index: int) -> dict:
    return {"action": "buy_potion", "option_index": option_index}


def remove_card_at_shop() -> dict:
    return {"action": "remove_card_at_shop"}


# ── Treasure ─────────────────────────────────────────────────


def open_chest() -> dict:
    return {"action": "open_chest"}


def choose_treasure_relic(option_index: int) -> dict:
    return {"action": "choose_treasure_relic", "option_index": option_index}


# ── Menu / Lifecycle ─────────────────────────────────────────


def continue_run() -> dict:
    return {"action": "continue_run"}


def abandon_run() -> dict:
    return {"action": "abandon_run"}


def save_and_quit() -> dict:
    return {"action": "save_and_quit"}


def return_to_main_menu() -> dict:
    return {"action": "return_to_main_menu"}


def open_character_select() -> dict:
    return {"action": "open_character_select"}


def select_character(option_index: int) -> dict:
    body: dict = {"action": "select_character"}
    if option_index is not None:
        body["option_index"] = option_index
    return body


def increase_ascension() -> dict:
    """Increment ascension level by 1 on character select screen."""
    return {"action": "increase_ascension"}


def decrease_ascension() -> dict:
    """Decrement ascension level by 1 on character select screen."""
    return {"action": "decrease_ascension"}


def embark() -> dict:
    return {"action": "embark"}


def open_timeline() -> dict:
    return {"action": "open_timeline"}


def close_main_menu_submenu() -> dict:
    return {"action": "close_main_menu_submenu"}


def choose_timeline_epoch(option_index: int = 0) -> dict:
    return {"action": "choose_timeline_epoch", "option_index": option_index}


def confirm_timeline_overlay() -> dict:
    return {"action": "confirm_timeline_overlay"}


def confirm_modal() -> dict:
    return {"action": "confirm_modal"}


def dismiss_modal() -> dict:
    return {"action": "dismiss_modal"}
