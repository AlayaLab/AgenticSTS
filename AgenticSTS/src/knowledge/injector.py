"""KnowledgeInjector — inject game knowledge into LLM prompts.

Separate token budget from skills (600) and memory (400).
Knowledge budget: 400 tokens for card mechanics, 200 for monster info, 150 for potions.
"""

from __future__ import annotations

import config
from src.knowledge.knowledge import GameKnowledge
from src.mcp_client.upstream_models import (
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawRunPotionPayload,
)
from src.state.game_state import GameState

# Approximate token budgets (1 token ~ 4 chars)
_CARD_BUDGET_CHARS = 1600   # ~400 tokens
_MONSTER_BUDGET_CHARS = 800  # ~200 tokens
_POTION_BUDGET_CHARS = 600   # ~150 tokens
_ENCOUNTER_BUDGET_CHARS = 200  # ~50 tokens


def inject_combat_knowledge(gs: GameState, kb: GameKnowledge) -> str:
    """Build a knowledge section for combat prompts.

    Includes card mechanics for hand cards and monster move patterns
    for current enemies. Returns empty string if no useful knowledge.
    """
    if not gs.combat:
        return ""

    sections: list[str] = []

    # Card mechanics for hand cards
    card_lines = _build_card_mechanics(gs.hand, kb)
    if card_lines:
        sections.append("## Card Mechanics (from game data)")
        sections.extend(card_lines)

    # Monster move patterns
    monster_lines = _build_monster_info(gs.enemies, kb)
    if monster_lines:
        if sections:
            sections.append("")
        sections.append("## Enemy Patterns (from game data)")
        sections.extend(monster_lines)

    # Potion mechanics
    usable = [p for p in gs.potions if p.can_use]
    potion_lines = _build_potion_info(usable, kb)
    if potion_lines:
        if sections:
            sections.append("")
        sections.append("## Potion Mechanics (from game data)")
        sections.extend(potion_lines)

    if not sections:
        return ""
    return "\n".join(sections)


def inject_reward_knowledge(card_names: list[str], kb: GameKnowledge) -> str:
    """Build knowledge section for card reward/select prompts."""
    lines = _build_card_knowledge_lines(card_names, kb, _CARD_BUDGET_CHARS)

    if not lines:
        return ""
    return "## Card Mechanics (from game data)\n" + "\n".join(lines)


def inject_shop_knowledge(card_names: list[str], kb: GameKnowledge) -> str:
    """Build knowledge section for shop prompts."""
    return inject_reward_knowledge(card_names, kb)


def inject_event_knowledge(event_id: str, kb: GameKnowledge) -> str:
    """Inject event-level context (e.g. Ancient flag).

    Per-option descriptions and enchantment effects are emitted by
    ``build_event_prompt`` directly from the runtime ``gs.event`` payload, so
    this function intentionally no longer duplicates a "Known Outcomes"
    section — that produced two near-identical option lists in every event
    prompt.
    """
    if config.KNOWLEDGE_STRICT:
        return ""
    event = kb.events.get_by_event_id(event_id)
    if event is None:
        event = kb.events.get(event_id)
    if event is None:
        return ""
    if event.base_type == "AncientEventModel":
        return "This is a rare Ancient event with powerful choices."
    return ""


def inject_encounter_knowledge(
    enemy_ids: set[str],
    enemy_names: set[str],
    kb: GameKnowledge,
) -> str:
    """Inject encounter composition at combat start."""
    if config.KNOWLEDGE_STRICT:
        return ""
    enc = kb.encounters.get_by_enemy_ids(enemy_ids)
    if enc is None:
        enc = kb.encounters.get_by_enemy_names(enemy_names)
    if enc is None:
        return ""
    parts = [f"## Encounter: {enc.name}"]
    parts.append(f"Type: {enc.room_type} | Act: {enc.act}")
    if enc.is_weak:
        parts.append("(Weak encounter)")
    return "\n".join(parts)


def inject_keyword_glossary(keyword_names: set[str], kb: GameKnowledge) -> str:
    """Inject keyword definitions for hand cards."""
    glossary = kb.keywords.format_glossary(keyword_names)
    if not glossary:
        return ""
    return f"## Keyword Glossary\n{glossary}"


def _build_card_mechanics(
    hand: list[RawCombatHandCardPayload], kb: GameKnowledge
) -> list[str]:
    """Build card mechanic lines within token budget."""
    seen_names: list[str] = []
    seen_keys: set[str] = set()

    for card in hand:
        key = card.name.rstrip("+").lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        seen_names.append(card.name)

    return _build_card_knowledge_lines(seen_names, kb, _CARD_BUDGET_CHARS)


def _build_card_knowledge_lines(
    card_names: list[str],
    kb: GameKnowledge,
    budget: int,
) -> list[str]:
    """Build human-readable additive card knowledge lines within token budget."""
    lines: list[str] = []
    seen: set[str] = set()

    for name in card_names:
        key = name.rstrip("+").lower()
        if key in seen:
            continue
        seen.add(key)

        enrichment = kb.cards.get_enrichment_summary(name)
        if not enrichment:
            continue

        card = kb.cards.get(name)
        display_name = card.name if card is not None else name.rstrip("+")
        line = f"- {display_name}: {enrichment}"
        budget -= len(line)
        if budget < 0:
            break
        lines.append(line)

    return lines


def _build_monster_info(
    enemies: list[RawCombatEnemyPayload], kb: GameKnowledge
) -> list[str]:
    """Build monster info lines within token budget."""
    if config.KNOWLEDGE_STRICT:
        return []
    lines: list[str] = []
    budget = _MONSTER_BUDGET_CHARS
    seen: set[str] = set()

    for enemy in enemies:
        key = enemy.name.lower()
        if key in seen:
            continue
        seen.add(key)

        summary = kb.monsters.get_combat_summary(enemy.name)
        if summary:
            line = f"- {summary}"
            budget -= len(line)
            if budget < 0:
                break
            lines.append(line)

    return lines


def _build_potion_info(
    potions: list[RawRunPotionPayload], kb: GameKnowledge
) -> list[str]:
    """Build potion info lines within token budget."""
    lines: list[str] = []
    budget = _POTION_BUDGET_CHARS

    for potion in potions:
        pot_info = kb.potions.get(potion.name)
        if pot_info and pot_info.on_use:
            line = f"- {pot_info.name}: {pot_info.on_use}"
            budget -= len(line)
            if budget < 0:
                break
            lines.append(line)

    return lines
