# ruff: noqa: E501
"""Prompt template for potion decisions at the start of each combat turn.

Type-aware potion evaluation with tactical context.
Designed for Qwen 3.5 9B -- explicit decision rules, not vague heuristics.
"""

from __future__ import annotations

import config

from src.brain.prompts._intent_fmt import (
    compute_total_incoming,
    format_enemy_intents,
    format_poison_hint,
)
from src.brain.prompts._target_fmt import describe_target_scope
from src.brain.prompts._card_name import upgrade_suffix
from src.knowledge.power_lookup import format_power_with_description
from src.state.game_state import GameState


def _format_hand_cost(c) -> str:
    """Format energy cost for a hand card: 'X' if costs_x, else str(energy_cost)."""
    return "X" if c.costs_x else str(c.energy_cost)


def build_potion_prompt(gs: GameState) -> str:
    """Build a prompt asking the LLM whether to use a potion this turn.

    Called at the start of each new combat turn, BEFORE card play decisions.
    The LLM sees the full combat state and decides whether a potion would
    help this turn, or whether to save it for later.
    """
    combat = gs.combat
    if not combat:
        return ""

    p = combat.player
    hand = combat.hand
    potions = gs.potions
    usable_potions = [pot for pot in potions if pot.can_use]
    if not usable_potions:
        return ""

    stars_str = f" | Stars: {p.stars}" if p.stars else ""
    lines = [
        "## Combat State (Turn Start -- Potion Decision)",
        f"Round: {gs.combat_round} | Energy: {p.energy}/{gs.run_info.max_energy if gs.run_info else '?'}{stars_str} | HP: {p.current_hp}/{p.max_hp} | Block: {p.block}",
    ]

    # Player powers
    if p.powers:
        powers_str = ", ".join(
            format_power_with_description(
                pw.name,
                pw.amount,
                getattr(pw, "power_id", ""),
                getattr(pw, "description", ""),
            )
            for pw in p.powers
        )
        lines.append(f"Player buffs/debuffs: {powers_str}")

    # Enemies
    lines.append("")
    lines.append("## Enemies")
    player_powers = p.powers if p.powers else None
    for e in combat.enemies:
        if not e.is_alive:
            continue
        intent_str = format_enemy_intents(e)
        poison_hint = format_poison_hint(e.powers, e.current_hp, player_powers)
        powers_str = ""
        if e.powers:
            powers_str = " | powers: " + ", ".join(
                format_power_with_description(
                    pw.name,
                    pw.amount,
                    getattr(pw, "power_id", ""),
                    getattr(pw, "description", ""),
                )
                for pw in e.powers
            )
        lines.append(f"- {e.name} [index={e.index}]: HP {e.current_hp}/{e.max_hp}{poison_hint}, Block {e.block}, Intent: {intent_str}{powers_str}")

    # Hand
    lines.append("")
    lines.append(f"## Hand ({len(hand)} cards)")
    for c in hand:
        playable = "PLAYABLE" if c.playable else "UNPLAYABLE"
        star = f" ★{c.star_cost}" if c.star_cost else ""
        upgraded = upgrade_suffix(c)
        cost_str = _format_hand_cost(c)
        lines.append(f"- [{c.index}] {c.name}{upgraded} (cost={cost_str}{star}) [{playable}]: {c.rules_text}")

    # Available potions
    lines.append("")
    lines.append("## Available Potions")
    for pot in usable_potions:
        target_hint = (
            f" (targets: {describe_target_scope(pot.target_index_space, pot.target_type)})"
            if pot.requires_target else ""
        )
        lines.append(f"- [index={pot.index}] {pot.name}{target_hint}: {pot.description}")

    # Tactical analysis
    alive_enemies = [e for e in combat.enemies if e.is_alive]
    total_incoming = compute_total_incoming(alive_enemies)
    effective_incoming = max(0, total_incoming - p.block)
    hp_ratio = p.current_hp / p.max_hp if p.max_hp > 0 else 1.0

    lines.append("")
    lines.append("## Threat Assessment")
    lines.append(f"HP: {p.current_hp}/{p.max_hp} ({hp_ratio:.0%}) | Incoming damage: {total_incoming} (after block: {effective_incoming})")
    if config.PROMPT_VARIANT != "baseline":
        if effective_incoming >= p.current_hp:
            lines.append("LETHAL -- you will DIE this turn without Block Potion or killing attackers!")
        elif hp_ratio < 0.25:
            lines.append(f"CRITICAL HP ({p.current_hp}/{p.max_hp} = {hp_ratio:.0%}) -- defensive/healing potions are high priority.")
        elif effective_incoming > 0:
            pct = effective_incoming / p.current_hp if p.current_hp > 0 else 1.0
            if pct >= 0.5:
                lines.append(f"Incoming {effective_incoming} = {pct:.0%} of HP -- defensive potions are valuable.")

    # Decision framework
    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        lines.append("## Potion Decision Framework")
        lines.append("")
        lines.append("Classify each potion, then match to the situation:")
        lines.append("")
        lines.append("| Potion Type | Examples | USE when... |")
        lines.append("|-------------|---------|-------------|")
        lines.append("| Damage | Fire, Explosive, Poison | Kills an enemy this turn, or elite/boss fight |")
        lines.append("| Block/Defense | Block Potion, Ghost in Jar | Facing lethal or heavy incoming damage |")
        lines.append("| Buff (Str/Dex) | Strength, Dexterity, Flex | Turn with 3+ attacks (Str) or 3+ blocks (Dex) to maximize value |")
        lines.append("| Heal | Blood, Regen, Fruit Juice | HP is low and no immediate lethal threat |")
        lines.append("| Utility | Energy, Duplicator, Gambler | Enables a critical play you otherwise cannot afford |")
        lines.append("")
        lines.append("USE potion when:")
        lines.append("- Facing LETHAL damage (highest priority -- use any defensive potion)")
        lines.append("- Elite or boss fight (potions exist to win hard fights -- use them)")
        lines.append("- Buff potion + multiple matching cards in hand (Strength + 3 attacks = big value)")
        lines.append("- Using the potion lets you kill an enemy, reducing future incoming damage")
        lines.append("- Potion belt is full and you might gain a better potion from this fight")
        lines.append("")
        lines.append("SAVE potion when:")
        lines.append("- Normal hallway fight you can win comfortably without it")
        lines.append("- Buff potion but only 0-1 matching cards in hand (low value)")
        lines.append("- Fairy in a Bottle (save as HP=0 insurance only — does NOT trigger on other death causes like Insatiable, so still USE on certain-death turns where damage is the threat)")
        lines.append("")
        lines.append("Golden rule: dying with unused potions is the worst outcome. When in doubt, USE.")
    lines.append("")
    lines.append("## Your Task")
    lines.append("Decide whether to use a potion NOW, or skip.")
    lines.append('Use: {"action": "use_potion", "params": {"option_index": <int>, "target_index": <int or null>}, "reasoning": "..."}')
    lines.append('Skip: {"action": "skip_potion", "params": {}, "reasoning": "..."}')
    lines.append("Keep reasoning SHORT (1 sentence).")

    return "\n".join(lines)
