"""Write-side tool schemas for the post-run evolution stage.

These tools allow the LLM to modify the agent's own capabilities:
- author_tool: Write a new Python computational tool
- write_skill: Create or update a strategy skill
- get_performance_stats: Query historical performance data

All schemas follow Anthropic tool_use format.
"""

from __future__ import annotations

AUTHOR_TOOL: dict = {
    "name": "author_tool",
    "description": (
        "Write a new Python computational tool for future runs. "
        "Must be pure computation (no I/O, no LLM calls, no network). "
        "Include SCHEMA dict, execute() function, and TEST_CASES list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Snake_case tool name (e.g., 'poison_lethal_check').",
            },
            "code": {
                "type": "string",
                "description": (
                    "Complete Python file with SCHEMA dict, execute() function, "
                    "and TEST_CASES list. Only math/collections/itertools/functools "
                    "imports allowed."
                ),
            },
            "motivation": {
                "type": "string",
                "description": "What gameplay failure motivated creating this tool.",
            },
        },
        "required": ["tool_name", "code", "motivation"],
        "additionalProperties": False,
    },
}


WRITE_SKILL: dict = {
    "name": "write_skill",
    "description": (
        "Create a natural language strategy skill grounded in CROSS-RUN "
        "evidence. Skills are procedural knowledge injected into decision "
        "prompts when their trigger conditions match the game state. "
        "Spec #3: every proposal MUST carry `evidence` (run_ids + stat_basis "
        "+ anchor_episode) and a `rationale` explaining why this pattern "
        "is invisible to single-run mistake_discovery."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Human-readable skill name (e.g., 'Poison lethal timing').",
            },
            "category": {
                "type": "string",
                "description": "Skill category.",
                "enum": [
                    "combat", "deck_building", "map", "rest",
                    "shop", "event", "boss", "character", "general",
                ],
            },
            "content": {
                "type": "string",
                "maxLength": 400,
                "description": (
                    "The strategy knowledge in natural language (≤400 chars). "
                    "Will be injected into LLM prompts. Be specific and actionable."
                ),
            },
            "trigger_state_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "State types that trigger this skill. Empty = always active.",
            },
            "trigger_enemy_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Enemy names that trigger this skill. Empty = all enemies.",
            },
            "trigger_requires_cards": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Card names that must be in hand or deck. REQUIRED when content "
                    "mentions specific cards."
                ),
            },
            "trigger_character": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Characters this skill applies to. Empty = all.",
            },
            "motivation": {
                "type": "string",
                "description": "What gameplay experience motivated this skill.",
            },
            "evidence": {
                "type": "object",
                "description": (
                    "Cross-run evidence. ALL three sub-fields required."
                ),
                "properties": {
                    "run_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": (
                            "≥2 distinct run ids that exhibit this pattern."
                        ),
                    },
                    "stat_basis": {
                        "type": "string",
                        "description": (
                            "1-line description of the cross-run statistic, with "
                            "concrete numbers (e.g. 'win rate 18% vs 42% baseline')."
                        ),
                    },
                    "anchor_episode": {
                        "type": "string",
                        "description": (
                            "Closest single concrete episode, format '<run_id>:<combat_id>'."
                        ),
                    },
                },
                "required": ["run_ids", "stat_basis", "anchor_episode"],
            },
            "rationale": {
                "type": "string",
                "maxLength": 300,
                "description": (
                    "≤300 chars: why mistake_discovery cannot catch this from a "
                    "single run's trace. If you cannot answer this, do not propose."
                ),
            },
        },
        "required": [
            "skill_name", "category", "content", "motivation",
            "evidence", "rationale",
        ],
        "additionalProperties": False,
    },
}


def validate_skill_trigger(trigger_data: dict) -> list[str]:
    """Warn about overly generic triggers. Returns warning strings."""
    warnings = []
    state_types = trigger_data.get("state_types", [])
    enemy_names = trigger_data.get("enemy_names", [])
    tags = trigger_data.get("tags", [])
    if len(state_types) >= 3 and not enemy_names and not tags:
        warnings.append(
            "Trigger is too generic (3+ state_types, no enemy_names, no tags). "
            "This skill will compete with 50+ others and rarely be selected."
        )
    return warnings


GET_PERFORMANCE_STATS: dict = {
    "name": "get_performance_stats",
    "description": (
        "Query historical performance data: win rate, floor progress, "
        "common death causes, tool usage statistics."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "metric": {
                "type": "string",
                "description": "What to query.",
                "enum": [
                    "win_rate", "floor_progress", "death_causes",
                    "tool_usage", "tool_preprocessing",
                    "skill_usage", "recent_runs",
                ],
            },
            "character": {
                "type": "string",
                "description": "Optional: filter by character name.",
            },
        },
        "required": ["metric"],
        "additionalProperties": False,
    },
}


# ── Aggregated exports ──────────────────────────────────────────

READ_PHASE_TOOLS: list[dict] = [GET_PERFORMANCE_STATS]

MUTATING_WRITE_TOOLS: list[dict] = [
    AUTHOR_TOOL,
    WRITE_SKILL,
]

WRITE_TOOLS: list[dict] = [
    *MUTATING_WRITE_TOOLS,
    *READ_PHASE_TOOLS,
]

WRITE_TOOL_NAMES: frozenset[str] = frozenset(tool["name"] for tool in WRITE_TOOLS)
READ_PHASE_TOOL_NAMES: frozenset[str] = frozenset(
    tool["name"] for tool in READ_PHASE_TOOLS
)
MUTATING_WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    tool["name"] for tool in MUTATING_WRITE_TOOLS
)
