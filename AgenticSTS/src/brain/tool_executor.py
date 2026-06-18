"""Tool executor: dispatches query tool calls from LLM responses.

Wraps existing backend functions (knowledge lookups, memory stores, skill
library) behind a unified execute() interface. Each handler returns a
plain-text result string and NEVER raises exceptions.

Used by the reasoner when the LLM invokes query tools (recall_encounter,
read_guide, etc.) during its reasoning process.
"""

from __future__ import annotations

import logging
from typing import Any

from src.knowledge.knowledge import GameKnowledge
from src.state.game_state import GameState

logger = logging.getLogger(__name__)


# ── Query tool schemas (reused by EvolutionEngine) ─────────────

RECALL_ENCOUNTER_SCHEMA: dict = {
    "name": "recall_encounter",
    "description": (
        "Recall past combat encounters from memory. Returns up to 3 episodes "
        "with round-by-round details (cards played, enemy intents, damage taken). "
        "Use BEFORE writing skills to verify historical evidence."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "enemy_key": {
                "type": "string",
                "description": "Enemy name to search for (e.g., 'Phrog Parasite').",
            },
            "character": {
                "type": "string",
                "description": "Character name to filter by (e.g., 'the silent').",
            },
        },
    },
}

QUERY_TOOL_SCHEMAS: list[dict] = [RECALL_ENCOUNTER_SCHEMA]


class ToolExecutor:
    """Dispatches query tool calls from LLM responses.

    Each handler wraps an existing backend function (knowledge DB, memory
    store, skill library) and returns a plain-text result. Handlers never
    raise -- all exceptions are caught and returned as error strings.
    """

    def __init__(
        self,
        knowledge: GameKnowledge | None = None,
        memory_manager: object | None = None,   # MemoryManager
        skill_library: object | None = None,     # SkillLibrary
        game_state: GameState | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._memory_manager = memory_manager
        self._skill_library = skill_library
        self._game_state = game_state

        # Handler dispatch table: tool_name -> method
        self._handlers: dict[str, Any] = {
            "recall_encounter": self._recall_encounter,
        }

    def set_game_state(self, gs: GameState) -> None:
        """Update current game state for context-dependent tools."""
        self._game_state = gs

    def execute(self, tool_name: str, tool_input: dict) -> str:
        """Execute a static query tool and return result text.

        Only dispatches to the built-in query tool handlers.
        Dynamic tools are handled by EvolutionEngine directly (not here).
        Never raises.
        """
        handler = self._handlers.get(tool_name)
        if handler is not None:
            try:
                return handler(tool_input)
            except Exception as exc:
                logger.warning("Tool %s failed: %s", tool_name, exc, exc_info=True)
                return f"Tool {tool_name} error: {exc}"

        return f"Unknown tool: {tool_name}"

    # ── Handlers ────────────────────────────────────────────────

    def _recall_encounter(self, tool_input: dict) -> str:
        """Recall past combat encounters from V2 HCM combat store."""
        if self._memory_manager is None:
            return "No past encounters found (memory not available)."

        # Access combat_store via the MemoryManager's property
        combat_store = getattr(self._memory_manager, "combat_store", None)
        if combat_store is None:
            return "No past encounters found (combat store not available)."

        enemy_key = tool_input.get("enemy_key", "").strip()
        character = tool_input.get("character", "").strip()

        if not enemy_key and not character:
            return "No enemy_key or character provided for encounter recall."

        episodes = combat_store.query(
            enemy_key=enemy_key,
            character=character,
            limit=3,
        )

        if not episodes:
            target = enemy_key or character
            return f"No past encounters found for: {target}"

        lines = [f"Past {len(episodes)} encounters with {enemy_key or 'this enemy'}:"]
        for ep in episodes:
            outcome = "Won" if ep.won else "Lost"
            rounds = len(ep.rounds)
            hp_delta = ep.hp_after - ep.hp_before
            lines.append(
                f"  [{outcome}] {ep.enemy_key} ({ep.combat_type}, F{ep.floor}): "
                f"{rounds}R, HP {ep.hp_before}->{ep.hp_after} ({hp_delta:+d})"
            )
            # Include round details (up to 5 rounds) for tactical insight
            for r in ep.rounds[:5]:
                cards = ", ".join(r.cards_played) if r.cards_played else "none"
                dmg_info = f" → -{r.damage_taken}hp" if r.damage_taken else ""
                intent_str = ""
                if r.enemy_intents:
                    intent_str = " | Enemy: " + "; ".join(r.enemy_intents)
                lines.append(f"    R{r.round_num}: [{cards}]{intent_str}{dmg_info}")
            if len(ep.rounds) > 5:
                lines.append(f"    ... (+{len(ep.rounds) - 5} more rounds)")
        return "\n".join(lines)

