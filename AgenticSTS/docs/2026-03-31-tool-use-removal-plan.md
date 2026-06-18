# Tool-Use Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all tool_use from gameplay LLM calls, replacing with text-only `<decision>` JSON protocol and deterministic enemy pattern injection.

**Architecture:** Gameplay LLM calls become text-in/text-out with tagged `<decision>` JSON blocks. Query tools are removed (context auto-injected). Evolution engine keeps tool_use unchanged. Enemy behavior patterns replace episode summaries in memory.

**Tech Stack:** Python 3.12, Anthropic SDK, httpx (OpenAI-compatible), Pydantic, pytest

**Spec:** `docs/2026-03-31-tool-use-removal-design.md` (Rev 3)

---

## File Map

| File | Role | Change |
|------|------|--------|
| `src/brain/enemy_pattern_injector.py` | **New**: format enemy behavior patterns from combat episodes | Create |
| `src/brain/decision_parser.py` | **New**: extract + validate `<decision>` JSON from LLM text | Create |
| `src/brain/tool_schemas.py` | Repurposed: provider tool schema → local response schema | Modify |
| `src/brain/v2_engine.py` | Core: replace `_agent_loop()` with single-call + repair | Modify |
| `src/brain/prompts/system.py` | Replace tool instructions with `<decision>` format | Modify |
| `src/memory/models_v2.py` | `WorkingContext`: swap `combat_episode_hints` → `enemy_pattern_hints` | Modify |
| `src/memory/retriever.py` | Replace episode formatting with enemy pattern formatting | Modify |
| `src/memory/prompt_injector.py` | Replace `## Past Encounters` with `## Enemy Patterns` | Modify |
| `src/brain/conversation.py` | Remove tool-result merging; add round 2+ upcoming patterns | Modify |
| `src/brain/query_tools.py` | Delete | Delete |
| `src/brain/tool_executor.py` | Remove `_read_guide`, `_assess_potion_value` | Modify |
| `src/brain/evolution_engine.py` | Remove `QUERY_TOOLS` from tool list | Modify |
| `src/agent/loop.py` | Wire new pipeline, remove query tool references | Modify |

---

### Task 1: Enemy Pattern Injector

**Files:**
- Create: `src/brain/enemy_pattern_injector.py`
- Create: `tests/test_enemy_pattern_injector.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_enemy_pattern_injector.py
"""Tests for enemy pattern injector."""
import pytest
from src.brain.enemy_pattern_injector import format_enemy_patterns, format_upcoming_patterns


def _make_round(num: int, intents: tuple[str, ...]) -> dict:
    """Create a minimal CombatRound-like dict for testing."""
    return {"round_num": num, "enemy_intents": intents}


def _make_episode(rounds: list[dict]) -> object:
    """Create a minimal CombatEpisode-like object for testing."""
    class FakeRound:
        def __init__(self, d):
            self.round_num = d["round_num"]
            self.enemy_intents = tuple(d["enemy_intents"])

    class FakeEpisode:
        def __init__(self, rounds):
            self.rounds = [FakeRound(r) for r in rounds]

    return FakeEpisode(rounds)


class TestFormatEnemyPatterns:
    def test_empty_episodes_returns_empty(self):
        result = format_enemy_patterns([], current_round=1)
        assert result == ""

    def test_single_episode_formats_correctly(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12",)),
            _make_round(2, ("Buff",)),
            _make_round(3, ("Attack 18",)),
        ])
        result = format_enemy_patterns([ep], current_round=1)
        assert "## Enemy Patterns" in result
        assert "Current round: R1" in result
        assert "not guaranteed future actions" in result
        assert "R1 Attack 12" in result
        assert "R2 Buff" in result
        assert "R3 Attack 18" in result

    def test_max_episodes_respected(self):
        episodes = [_make_episode([_make_round(1, ("Attack",))]) for _ in range(5)]
        result = format_enemy_patterns(episodes, current_round=1)
        assert result.count("Past fight") <= 3

    def test_max_rounds_per_episode_respected(self):
        rounds = [_make_round(i, (f"Attack {i}",)) for i in range(1, 12)]
        ep = _make_episode(rounds)
        result = format_enemy_patterns([ep], current_round=1)
        # Should cap at 8 rounds
        assert "R9" not in result

    def test_multi_intent_per_round(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12", "Debuff")),
        ])
        result = format_enemy_patterns([ep], current_round=1)
        assert "Attack 12 + Debuff" in result


class TestFormatUpcomingPatterns:
    def test_upcoming_from_round_3(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12",)),
            _make_round(2, ("Buff",)),
            _make_round(3, ("Attack 18",)),
            _make_round(4, ("Multi-Attack 8x3",)),
        ])
        result = format_upcoming_patterns([ep], current_round=3)
        assert "Likely upcoming after R3" in result
        assert "R4 Multi-Attack 8x3" in result
        # Should NOT include past rounds
        assert "R1" not in result
        assert "R2" not in result

    def test_upcoming_empty_when_past_end(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12",)),
            _make_round(2, ("Buff",)),
        ])
        result = format_upcoming_patterns([ep], current_round=5)
        assert result == ""

    def test_upcoming_max_3_rounds(self):
        rounds = [_make_round(i, (f"Move {i}",)) for i in range(1, 10)]
        ep = _make_episode(rounds)
        result = format_upcoming_patterns([ep], current_round=2)
        assert "R3" in result
        assert "R4" in result
        assert "R5" in result
        assert "R6" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_enemy_pattern_injector.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.brain.enemy_pattern_injector'`

- [ ] **Step 3: Implement enemy pattern injector**

```python
# src/brain/enemy_pattern_injector.py
"""Format enemy behavior patterns from past combat episodes.

Provides two functions:
- format_enemy_patterns(): Full pattern history for round 1 (via prompt_injector)
- format_upcoming_patterns(): Compact upcoming-only for round 2+ (via CombatConversation)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.memory.models_v2 import CombatEpisode

_MAX_EPISODES = 3
_MAX_ROUNDS = 8
_MAX_UPCOMING = 3


def _format_intents(intents: tuple[str, ...]) -> str:
    """Join multiple intents for a single round."""
    return " + ".join(intents) if intents else "Unknown"


def format_enemy_patterns(
    episodes: list[CombatEpisode],
    current_round: int = 1,
) -> str:
    """Format full enemy patterns for round 1 injection.

    Returns empty string if no episodes exist.
    """
    if not episodes:
        return ""

    lines = [
        "## Enemy Patterns",
        f"Current round: R{current_round}",
        "These are possible move patterns from past fights, not guaranteed future actions.",
        "",
    ]

    for i, ep in enumerate(episodes[:_MAX_EPISODES], 1):
        round_strs = []
        for r in ep.rounds[:_MAX_ROUNDS]:
            intent_str = _format_intents(r.enemy_intents)
            round_strs.append(f"R{r.round_num} {intent_str}")
        lines.append(f"- Past fight {i}: {' → '.join(round_strs)}")

    upcoming = format_upcoming_patterns(episodes, current_round)
    if upcoming:
        lines.append("")
        lines.append(upcoming)

    return "\n".join(lines)


def format_upcoming_patterns(
    episodes: list[CombatEpisode],
    current_round: int,
) -> str:
    """Format upcoming enemy moves for round 2+ injection.

    Extracts 1-3 rounds after current_round from each past episode.
    Returns empty string if no upcoming data exists.
    """
    if not episodes:
        return ""

    patterns: list[str] = []
    for i, ep in enumerate(episodes[:_MAX_EPISODES], 1):
        upcoming_rounds = [
            r for r in ep.rounds
            if r.round_num > current_round
        ][:_MAX_UPCOMING]
        if not upcoming_rounds:
            continue
        round_strs = [
            f"R{r.round_num} {_format_intents(r.enemy_intents)}"
            for r in upcoming_rounds
        ]
        patterns.append(f"- Pattern {chr(64 + i)}: {' → '.join(round_strs)}")

    if not patterns:
        return ""

    lines = [f"Likely upcoming after R{current_round}:"]
    lines.extend(patterns)
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_enemy_pattern_injector.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/enemy_pattern_injector.py tests/test_enemy_pattern_injector.py
git commit -m "feat: add enemy pattern injector for deterministic combat context"
```

---

### Task 2: Decision Parser

**Files:**
- Create: `src/brain/decision_parser.py`
- Create: `tests/test_decision_parser.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_decision_parser.py
"""Tests for <decision> tag extraction and validation."""
import pytest
from src.brain.decision_parser import extract_decision, validate_decision


class TestExtractDecision:
    def test_extracts_tagged_json(self):
        text = 'Some reasoning here.\n\n<decision>\n{"action": "play_card", "card_index": 2, "target_index": 0, "reasoning": "test"}\n</decision>'
        result = extract_decision(text)
        assert result is not None
        assert result["action"] == "play_card"
        assert result["card_index"] == 2

    def test_extracts_last_tag_when_multiple(self):
        text = '<decision>\n{"action": "bad"}\n</decision>\nMore text\n<decision>\n{"action": "good"}\n</decision>'
        result = extract_decision(text)
        assert result["action"] == "good"

    def test_returns_none_on_no_tag(self):
        text = "Just some reasoning without any decision block."
        result = extract_decision(text)
        assert result is None

    def test_returns_none_on_invalid_json(self):
        text = "<decision>\n{not valid json}\n</decision>"
        result = extract_decision(text)
        assert result is None

    def test_handles_whitespace_in_tag(self):
        text = '<decision>  \n  {"action": "end_turn"}  \n  </decision>'
        result = extract_decision(text)
        assert result["action"] == "end_turn"

    def test_handles_nested_json(self):
        text = '<decision>\n{"plan": [{"type": "card", "card": "Strike", "target_index": 0}], "end_turn": true, "reasoning": "test"}\n</decision>'
        result = extract_decision(text)
        assert result["plan"][0]["card"] == "Strike"

    def test_fallback_raw_json_when_no_tag(self):
        text = 'Some text\n```json\n{"action": "play_card", "card_index": 0, "target_index": 0, "reasoning": "x"}\n```'
        result = extract_decision(text, allow_fallback=True)
        assert result is not None
        assert result["action"] == "play_card"


class TestValidateDecision:
    def test_valid_combat_plan(self):
        data = {
            "plan": [{"type": "card", "card": "Strike", "target_index": 0}],
            "end_turn": True,
            "reasoning": "test",
            "analysis": {
                "problem": "need damage",
                "key_observations": ["low hp", "vulnerable"],
                "candidate_lines": ["Strike", "Defend"],
                "chosen_line": "Strike for kill",
            },
        }
        errors = validate_decision(data, "combat_plan")
        assert errors == []

    def test_valid_map_action(self):
        data = {"action": "choose_map_node", "option_index": 2, "reasoning": "test"}
        errors = validate_decision(data, "map_action")
        assert errors == []

    def test_missing_required_field(self):
        data = {"action": "choose_map_node"}
        errors = validate_decision(data, "map_action")
        assert any("option_index" in e for e in errors)

    def test_invalid_action_enum(self):
        data = {"action": "fly_away", "option_index": 0, "reasoning": "test"}
        errors = validate_decision(data, "map_action")
        assert any("action" in e for e in errors)

    def test_combat_plan_missing_plan_key(self):
        data = {"end_turn": True, "reasoning": "test"}
        errors = validate_decision(data, "combat_plan")
        assert any("plan" in e for e in errors)

    def test_analysis_required_for_combat(self):
        data = {
            "plan": [{"type": "card", "card": "Strike", "target_index": 0}],
            "end_turn": True,
            "reasoning": "test",
        }
        errors = validate_decision(data, "combat_plan")
        assert any("analysis" in e for e in errors)

    def test_analysis_optional_for_noncombat(self):
        data = {"action": "choose_map_node", "option_index": 2, "reasoning": "test"}
        errors = validate_decision(data, "map_action")
        assert errors == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_decision_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.brain.decision_parser'`

- [ ] **Step 3: Implement decision parser**

```python
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

# Combat decision tool names that require the analysis field
_COMBAT_TOOLS = frozenset({"combat_plan", "combat_action"})

# Required fields per decision tool (field_name -> True if required)
_REQUIRED_FIELDS: dict[str, list[str]] = {
    "combat_plan": ["plan", "end_turn", "reasoning", "analysis"],
    "combat_action": ["action", "card_index", "target_index", "reasoning", "analysis"],
    "map_action": ["action", "option_index", "reasoning"],
    "rest_action": ["action", "option_index", "reasoning"],
    "event_action": ["action", "option_index", "reasoning"],
    "shop_action": ["action", "option_index", "reasoning"],
    "card_reward_action": ["action", "option_index", "reasoning"],
    "card_select_action": ["action", "selected_indices", "reasoning"],
    "hand_select_action": ["action", "selected_indices", "reasoning"],
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
    "shop_action": ["open_shop_inventory", "close_shop_inventory", "buy_card", "buy_relic", "buy_potion", "remove_card_at_shop", "proceed"],
    "card_reward_action": ["choose_reward_card", "skip_reward_cards"],
    "card_select_action": ["select_deck_card"],
    "hand_select_action": ["select_deck_card"],
    "treasure_action": ["choose_treasure_relic", "proceed"],
    "relic_select_action": ["choose_treasure_relic"],
    "potion_action": ["use_potion", "skip_potion"],
}


def extract_decision(text: str, *, allow_fallback: bool = False) -> dict[str, Any] | None:
    """Extract the last <decision> JSON block from LLM text.

    Returns parsed dict or None if no valid block found.
    If allow_fallback=True, also tries raw JSON extraction (code fences, bare JSON).
    """
    matches = _DECISION_RE.findall(text)
    if matches:
        raw = matches[-1].strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            logger.debug("Failed to parse <decision> JSON: %s", raw[:200])

    if allow_fallback:
        return _try_raw_json(text)

    return None


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
    if valid_actions and "action" in data:
        if data["action"] not in valid_actions:
            errors.append(
                f"Invalid action '{data['action']}' — must be one of: {valid_actions}"
            )

    return errors


def format_repair_message(errors: list[str]) -> str:
    """Format a repair prompt for the LLM when validation fails."""
    error_text = "; ".join(errors)
    return (
        f"Your response did not contain a valid <decision> block. "
        f"Error: {error_text}. "
        f"Please respond with a valid <decision> block."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_decision_parser.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/decision_parser.py tests/test_decision_parser.py
git commit -m "feat: add decision parser for <decision> tagged JSON extraction"
```

---

### Task 3: System Prompt Updates (D6 + D9)

**Files:**
- Modify: `src/brain/prompts/system.py:15-30` (replace `_SYSTEM_BASE` query tool section)

- [ ] **Step 1: Replace `_SYSTEM_BASE` — remove tool instructions, add `<decision>` format**

In `src/brain/prompts/system.py`, replace lines 15-30 (the entire `_SYSTEM_BASE` string) with:

```python
_SYSTEM_BASE = """\
You are an autonomous Slay the Spire 2 agent playing a complete run. You make every decision to maximize your chance of defeating the Act 3 boss.

## Output Format
Think through your decision, then output your choice in a <decision> tag containing valid JSON.

Example (map):
<decision>
{"action": "choose_map_node", "option_index": 2, "reasoning": "Elite fight for card reward", "strategic_note": "Need AoE damage for Act 2 hallways"}
</decision>

Example (combat plan):
<decision>
{"plan": [{"type": "card", "card": "Backflip", "target_index": -1}, {"type": "card", "card": "Shiv", "target_index": 0}], "end_turn": true, "reasoning": "Block first, then chip damage", "note_to_future_self": "Poison at 8, need 2 more turns", "analysis": {"problem": "Incoming 15 damage", "key_observations": ["Can block 11 with Backflip", "Shiv for 5 chip"], "candidate_lines": ["Block+Shiv", "All-in damage"], "chosen_line": "Block+Shiv to survive"}}
</decision>

The JSON must match the schema for the current decision type. Every decision requires a "reasoning" field.\
"""
```

- [ ] **Step 2: Update SYSTEM_DECKBUILD strategic_note reference**

In `src/brain/prompts/system.py`, in the `SYSTEM_DECKBUILD` section (around line 83), change:

```python
# OLD:
## Strategic Notes — Build Plan
Every decision tool has a `strategic_note` field. Write a RUNNING BUILD PLAN:
```

to:

```python
# NEW:
## Strategic Notes — Build Plan
Include a `strategic_note` field in your <decision> JSON. Write a RUNNING BUILD PLAN:
```

Apply the same change to `SYSTEM_STRATEGIC` (around line 102).

- [ ] **Step 3: Verify prompts render correctly**

Run: `python -c "from src.brain.prompts.system import get_system_prompt; print(get_system_prompt('map')[:500])"`
Expected: Should show the new `_SYSTEM_BASE` with `<decision>` format, no query tool references.

- [ ] **Step 4: Commit**

```bash
git add src/brain/prompts/system.py
git commit -m "feat: replace tool-use instructions with <decision> JSON format in system prompts"
```

---

### Task 4: WorkingContext + Retriever + Prompt Injector (D1 memory changes)

**Files:**
- Modify: `src/memory/models_v2.py:909-966` (`WorkingContext`)
- Modify: `src/memory/retriever.py:150-177` (combat section)
- Modify: `src/memory/prompt_injector.py:27-37` (`## Past Encounters` section)

- [ ] **Step 1: Update WorkingContext in models_v2.py**

In `src/memory/models_v2.py`, replace `combat_episode_hints` with `enemy_pattern_hints` in the `WorkingContext` dataclass (line 918):

```python
# OLD (line 918):
    combat_episode_hints: tuple[str, ...] = ()

# NEW:
    enemy_pattern_hints: tuple[str, ...] = ()
```

Update all references within the same class — `is_empty` (line 935), `total_hints` (line 946), `estimated_tokens` (line 958):

Replace every occurrence of `combat_episode_hints` with `enemy_pattern_hints` inside the `WorkingContext` class (use replace-all within the class).

- [ ] **Step 2: Update retriever.py — replace episode formatting with enemy patterns**

In `src/memory/retriever.py`, replace the episode hint block (lines ~165-177) with enemy pattern formatting:

```python
# OLD (lines 165-177):
        # 2. Past episodes
        episodes = combat_store.query(
            enemy_key=enemy_key,
            character=character,
            combat_type=combat_type,
            limit=2,
        )
        for ep in episodes:
            rounds_str = f"{len(ep.rounds)} rounds"
            result = "WON" if ep.won else f"LOST (HP {ep.hp_before}→{ep.hp_after})"
            combat_episode_hints.append(
                f"Past: vs {ep.enemy_key} ({rounds_str}): {result}, "
                f"cards played: {ep.total_cards_played}"
            )

# NEW:
        # 2. Enemy patterns (behavior sequences, not win/loss)
        from src.brain.enemy_pattern_injector import format_enemy_patterns
        episodes = combat_store.query(
            enemy_key=enemy_key,
            character=character,
            combat_type=combat_type,
            limit=3,
        )
        if episodes:
            pattern_text = format_enemy_patterns(episodes, current_round=1)
            if pattern_text:
                enemy_pattern_hints.append(pattern_text)
```

Also rename the local variable `combat_episode_hints` to `enemy_pattern_hints` at line 140 and update the `WorkingContext(...)` constructor call at the bottom (around line 276-277):

```python
# OLD:
        combat_episode_hints=tuple(combat_episode_hints),
# NEW:
        enemy_pattern_hints=tuple(enemy_pattern_hints),
```

- [ ] **Step 3: Update prompt_injector.py — replace Past Encounters section**

In `src/memory/prompt_injector.py`, replace the combat section (lines 27-37):

```python
# OLD:
    if wc.combat_guide_hints or wc.combat_episode_hints:
        parts.append("## Enemy Intel")
        parts.append("*Adapt these insights to the current situation.*\n")
        if wc.combat_guide_hints:
            for hint in wc.combat_guide_hints:
                parts.append(f"- {hint}")
        if wc.combat_episode_hints:
            parts.append("\n**Past Encounters:**")
            for hint in wc.combat_episode_hints:
                parts.append(f"- {hint}")
        parts.append("")

# NEW:
    if wc.combat_guide_hints or wc.enemy_pattern_hints:
        parts.append("## Enemy Intel")
        parts.append("*Adapt these insights to the current situation.*\n")
        if wc.combat_guide_hints:
            for hint in wc.combat_guide_hints:
                parts.append(f"- {hint}")
        if wc.enemy_pattern_hints:
            for hint in wc.enemy_pattern_hints:
                parts.append(hint)
        parts.append("")
```

Note: `enemy_pattern_hints` items are full formatted blocks (with headers), so no `- ` prefix needed.

- [ ] **Step 4: Verify module imports work**

Run: `python -c "from src.memory.models_v2 import WorkingContext; wc = WorkingContext(enemy_pattern_hints=('test',)); print(wc.is_empty, wc.total_hints)"`
Expected: `False 1`

- [ ] **Step 5: Commit**

```bash
git add src/memory/models_v2.py src/memory/retriever.py src/memory/prompt_injector.py
git commit -m "feat: replace combat_episode_hints with enemy_pattern_hints in memory system"
```

---

### Task 5: CombatConversation — Round 2+ Upcoming Patterns (D4)

**Files:**
- Modify: `src/brain/conversation.py:607-613` (`add_round_state`)
- Modify: `src/brain/conversation.py:897-911` (`add_tool_result` — delete)

- [ ] **Step 1: Add upcoming pattern injection to `add_round_state()`**

In `src/brain/conversation.py`, add an `enemy_episodes` parameter to `add_round_state()` and inject upcoming patterns.

Change the method signature (line 607):

```python
# OLD:
    def add_round_state(
        self,
        gs: GameState,
        *,
        extra_context: str = "",
        replan_context: str = "",
    ) -> None:

# NEW:
    def add_round_state(
        self,
        gs: GameState,
        *,
        extra_context: str = "",
        replan_context: str = "",
        enemy_episodes: list | None = None,
    ) -> None:
```

At the end of the round state message assembly (before the final `self._append_user(...)` call), add:

```python
        # Upcoming enemy patterns (round 2+)
        if enemy_episodes and self._round_count >= 2:
            from src.brain.enemy_pattern_injector import format_upcoming_patterns
            upcoming = format_upcoming_patterns(enemy_episodes, self._round_count)
            if upcoming:
                lines.append("")
                lines.append(upcoming)
```

- [ ] **Step 2: Delete `add_tool_result()` method**

Delete the `add_tool_result()` method at lines 897-911.

- [ ] **Step 3: Remove tool-result merge guard from `_append_user()`**

In `_append_user()` (around line 226-228), remove the `tool_result` block check that prevents merging:

```python
# DELETE these lines (226-230):
            if isinstance(prev_content, list) and any(
                (isinstance(b, dict) and b.get("type") == "tool_result")
                for b in prev_content
            ):
                # Don't merge into tool_result messages
```

After deletion, the method will always try to merge consecutive user messages (which is correct for text-only protocol).

- [ ] **Step 4: Verify conversation still compiles**

Run: `python -c "from src.brain.conversation import CombatConversation; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/brain/conversation.py
git commit -m "feat: add upcoming enemy patterns to round state; remove tool-result handling"
```

---

### Task 6: V2Engine — Replace Agent Loop with Single Call (D2 + D3 + D10)

**Files:**
- Modify: `src/brain/v2_engine.py` (major refactor of core loop)

This is the largest task. It replaces `_agent_loop()` (lines 485-893) with a simpler `_single_call()` + repair pattern.

- [ ] **Step 1: Add imports for decision parser**

At the top of `src/brain/v2_engine.py`, add:

```python
from src.brain.decision_parser import extract_decision, validate_decision, format_repair_message
```

Remove the import of `is_query_tool` from `src.brain.query_tools` (line 30):

```python
# DELETE line 30:
from src.brain.query_tools import is_query_tool
```

Remove the import of `get_v2_combat_tools, get_v2_tools` from `src.brain.tool_schemas` (line 31):

```python
# OLD line 31:
from src.brain.tool_schemas import get_v2_combat_tools, get_v2_tools

# NEW:
from src.brain.tool_schemas import get_tool_for_state
```

- [ ] **Step 2: Delete `QueryToolRecord`, `_PARAM_REMAP`, `_remap_params`, `_execute_query_tool`**

Delete:
- `QueryToolRecord` dataclass (lines 45-52)
- `_PARAM_REMAP` dict (lines 60-62)
- `_remap_params()` function (find it near lines 64-75)
- `_execute_query_tool()` method (lines 912-940)

- [ ] **Step 3: Replace `_agent_loop()` with `_single_call()`**

Delete the entire `_agent_loop()` method (lines 485-893). Replace with:

```python
    async def _single_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        decision_tool_name: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        effort: str = "",
        state_type_hint: str = "",
    ) -> tuple[dict | None, str, float, int]:
        """Single LLM call with <decision> extraction and repair.

        Returns (decision_dict, raw_text, latency_ms, token_count).
        decision_dict is None if extraction + repair both fail.
        """
        use_provider = provider or config.get_tier_provider("strategic")
        use_model = model or config.LLM_STRATEGIC_MODEL
        use_think = effort != ""

        tier_name = self._V2_TIER_MAP.get(state_type_hint, "strategic")

        t0 = time.monotonic()
        total_tokens = 0
        raw_text = ""

        # ── Main call ──────────────────────────────────────────
        try:
            response = await self._backend.acall(
                system=system,
                messages=messages,
                provider=use_provider,
                model=use_model,
                think=use_think,
                effort=effort,
            )
        except Exception as exc:
            logger.error("V2Engine: LLM call failed: %s", exc)
            return None, "", 0.0, 0

        latency_ms = (time.monotonic() - t0) * 1000
        total_tokens += getattr(getattr(response, "usage", None), "output_tokens", 0)

        # Extract text from response
        raw_text = self._extract_text(response)

        # ── Extract <decision> ─────────────────────────────────
        decision = extract_decision(raw_text, allow_fallback=True)
        if decision is not None:
            errors = validate_decision(decision, decision_tool_name)
            if not errors:
                logger.info(
                    "V2Engine[%s/%s]: decision extracted (%.0fms, %d tok)",
                    tier_name, state_type_hint, latency_ms, total_tokens,
                )
                return decision, raw_text, latency_ms, total_tokens

            # Validation failed — try repair
            logger.warning(
                "V2Engine: decision validation failed: %s", errors,
            )
        else:
            errors = ["No <decision> block found in response"]
            logger.warning("V2Engine: no <decision> block in response")

        # ── Repair turn ────────────────────────────────────────
        repair_msg = format_repair_message(errors)
        repair_messages = list(messages) + [
            {"role": "assistant", "content": raw_text},
            {"role": "user", "content": repair_msg},
        ]

        try:
            t1 = time.monotonic()
            repair_response = await self._backend.acall(
                system=system,
                messages=repair_messages,
                provider=use_provider,
                model=use_model,
                think=False,
                effort="",
            )
            repair_latency = (time.monotonic() - t1) * 1000
            latency_ms += repair_latency
            total_tokens += getattr(
                getattr(repair_response, "usage", None), "output_tokens", 0,
            )

            repair_text = self._extract_text(repair_response)
            decision = extract_decision(repair_text, allow_fallback=True)
            if decision is not None:
                errors = validate_decision(decision, decision_tool_name)
                if not errors:
                    logger.info(
                        "V2Engine[%s/%s]: decision extracted after repair (%.0fms, %d tok)",
                        tier_name, state_type_hint, latency_ms, total_tokens,
                    )
                    return decision, repair_text, latency_ms, total_tokens

            logger.error("V2Engine: repair failed, returning None")
        except Exception as exc:
            logger.error("V2Engine: repair call failed: %s", exc)

        return None, raw_text, latency_ms, total_tokens

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Extract text content from an LLM response object."""
        content = getattr(response, "content", None)
        if content is None:
            return ""
        if isinstance(content, str):
            return content
        # Anthropic Message: list of content blocks
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif hasattr(block, "text"):
                    parts.append(block.text)
            return "\n".join(parts)
        return str(content)
```

- [ ] **Step 4: Update `decide_noncombat()` to use `_single_call()` instead of `_agent_loop()`**

In `decide_noncombat()` (around lines 397-407), replace the `_agent_loop()` call:

```python
# OLD:
        tools, decision_tool_name = get_v2_tools(state_type)
        if not tools or decision_tool_name is None:
            logger.warning(...)
            return None
        # ...
        decision_input, _, latency_ms, tokens = await self._agent_loop(
            system=system_prompt,
            messages=messages,
            tools=tools,
            decision_tool_name=decision_tool_name,
            provider=provider,
            model=model,
            effort=effort,
            state_type_hint=state_type,
        )

# NEW:
        decision_tool = get_tool_for_state(state_type)
        if decision_tool is None:
            logger.warning("V2Engine: no decision tool for state_type=%s", state_type)
            return None
        decision_tool_name = decision_tool["name"]

        decision_input, raw_text, latency_ms, tokens = await self._single_call(
            system=system_prompt,
            messages=messages,
            decision_tool_name=decision_tool_name,
            provider=provider,
            model=model,
            effort=effort,
            state_type_hint=state_type,
        )
```

- [ ] **Step 5: Update `generate_combat_plan()` to use `_single_call()`**

In `generate_combat_plan()` (around lines 444-474), replace:

```python
# OLD:
        tools, decision_tool_name = get_v2_combat_tools(combat_state_type)
        decision_input, content, latency_ms, tokens = await self._agent_loop(
            system=system,
            messages=conversation.messages,
            tools=tools,
            decision_tool_name=decision_tool_name,
            mutate_messages=True,
            ...
        )
        # Record final assistant response
        if content:
            conversation._messages.append({"role": "assistant", "content": content})
            ...

# NEW:
        decision_tool_name = "combat_plan"
        decision_input, raw_text, latency_ms, tokens = await self._single_call(
            system=system,
            messages=conversation.messages,
            decision_tool_name=decision_tool_name,
            provider=provider,
            model=model,
            effort=effort,
            state_type_hint=combat_state_type,
        )
        # Record assistant response in conversation
        if raw_text:
            conversation._messages.append({"role": "assistant", "content": raw_text})
```

- [ ] **Step 6: Delete `_try_json_fallback()` method**

Delete the static method `_try_json_fallback()` (lines 943-985) — its functionality is now in `decision_parser.py`.

- [ ] **Step 7: Verify engine compiles**

Run: `python -c "from src.brain.v2_engine import V2Engine; print('OK')"`
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add src/brain/v2_engine.py
git commit -m "refactor: replace V2Engine agent loop with single-call <decision> protocol"
```

---

### Task 7: Query Tools Removal + Evolution Compatibility (D1 delete + D7)

**Files:**
- Delete: `src/brain/query_tools.py`
- Modify: `src/brain/tool_executor.py` (remove `_read_guide`, `_assess_potion_value`)
- Modify: `src/brain/tool_schemas.py` (remove query tool functions)
- Modify: `src/brain/evolution_engine.py` (remove `QUERY_TOOLS` from tool list)

- [ ] **Step 1: Delete `src/brain/query_tools.py`**

```bash
git rm src/brain/query_tools.py
```

- [ ] **Step 2: Clean up `tool_executor.py`**

In `src/brain/tool_executor.py`:

Remove `_read_guide` and `_assess_potion_value` handlers and their dispatch entries. The handler dispatch table (line 46-49) becomes:

```python
        self._handlers: dict[str, Any] = {
            "recall_encounter": self._recall_encounter,
        }
```

Delete the `_read_guide()` method (lines 122-230) and `_handle_assess_potion_value()` method (lines 232-304).

Remove the unused import `from src.skills.composer import compose_skill_context` (line 17).

- [ ] **Step 3: Clean up `tool_schemas.py`**

In `src/brain/tool_schemas.py`:

Update the module docstring (lines 1-11) — replace with:

```python
"""Response schemas for local validation of LLM <decision> JSON output.

Each game state type has a corresponding schema definition used to validate
the JSON content of <decision> blocks in LLM text responses.

These schemas were originally provider tool definitions. They are now
repurposed as local validation schemas (no longer sent to the LLM API).
"""
```

Delete the following functions and constants:
- `get_tool_choice()` (lines 518-526)
- `_QUERY_TOOL_RELEVANCE` dict (lines 531-544)
- `get_v2_tools()` (lines 549-571)
- `get_v2_combat_tools()` (lines 574-584)

Keep `get_tool_for_state()` and `_STATE_TOOL_MAP` — they're still used for schema lookup.

- [ ] **Step 4: Update `evolution_engine.py`**

In `src/brain/evolution_engine.py`:

In `run_evolution()` (around line 333), remove `QUERY_TOOLS` import and usage:

```python
# OLD (lines 333-340):
        from src.brain.query_tools import QUERY_TOOLS
        from src.brain.write_tools import WRITE_TOOL_NAMES, WRITE_TOOLS

        all_tools = list(QUERY_TOOLS) + list(WRITE_TOOLS)

# NEW:
        from src.brain.write_tools import WRITE_TOOL_NAMES, WRITE_TOOLS

        all_tools = list(WRITE_TOOLS)
```

In `_execute_tool()` (around line 462), remove stage-2 query tool dispatch:

```python
# OLD (lines 463-471):
        from src.brain.query_tools import QUERY_TOOL_NAMES

        # Stage 2: Static query tools
        if name in QUERY_TOOL_NAMES:
            if self._tool_executor is not None:
                from src.brain.v2_engine import _remap_params
                remapped = _remap_params(name, tool_input)
                return self._tool_executor.execute(name, remapped)
            return f"Query tool {name} unavailable: no executor."

# NEW:
        # Stage 2: Static query tools (removed — evolution no longer advertises them)
```

- [ ] **Step 5: Verify all imports resolve**

Run: `python -c "from src.brain.v2_engine import V2Engine; from src.brain.evolution_engine import EvolutionEngine; from src.brain.tool_schemas import get_tool_for_state; print('OK')"`
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git rm src/brain/query_tools.py
git add src/brain/tool_executor.py src/brain/tool_schemas.py src/brain/evolution_engine.py
git commit -m "refactor: delete query tools, clean up evolution engine compatibility"
```

---

### Task 8: Agent Loop Integration (wiring)

**Files:**
- Modify: `src/agent/loop.py`

- [ ] **Step 1: Remove query tool imports and ToolExecutor query wiring**

Search for and remove any imports of `query_tools`, `QUERY_TOOLS`, or `is_query_tool` in `loop.py`. These should not exist (confirmed by exploration), but verify.

In `_init_v2()` (around line 205), the `ToolExecutor` init stays — it's still used for `recall_encounter` in evolution. No change needed here.

- [ ] **Step 2: Wire enemy episodes into `generate_combat_plan()` call path**

Find where `add_round_state()` is called in `loop.py`. Add `enemy_episodes` parameter:

Search for `add_round_state(` in `loop.py`. At each call site, add the enemy episodes:

```python
# Add a helper near the combat plan section to fetch enemy episodes:
def _get_enemy_episodes(self, gs: GameState) -> list:
    """Fetch past combat episodes for current enemy."""
    if not self._memory or not gs.enemies:
        return []
    combat_store = getattr(self._memory, "combat_store", None)
    if not combat_store:
        return []
    names = [e.name for e in gs.enemies]
    enemy_key = names[0] if len(names) == 1 else "multi:" + "+".join(sorted(names))
    return combat_store.query(
        enemy_key=enemy_key,
        character=gs.character or "",
        limit=3,
    )
```

Then at each `add_round_state()` call, pass:

```python
# OLD:
self._v2_combat_conversation.add_round_state(gs, extra_context=extra, replan_context=replan)

# NEW:
self._v2_combat_conversation.add_round_state(
    gs, extra_context=extra, replan_context=replan,
    enemy_episodes=self._get_enemy_episodes(gs),
)
```

- [ ] **Step 3: Update strategic_note extraction**

Find `_record_strategic_note()` (line 1812). Currently it reads from `decision.params.get("strategic_note", "")`. The `decision.params` dict now comes from the `<decision>` JSON block instead of tool_use input — but the field name is the same. **No code change needed** — `_parse_decision()` already puts all non-action/reasoning fields into `params`.

Verify `note_to_future_self` extraction (line 3334) similarly reads from `plan.note_to_future_self`. This is parsed from the `<decision>` JSON by `parse_combat_plan()`. **No code change needed** as long as the field is in the JSON.

- [ ] **Step 4: Verify agent loop compiles**

Run: `python -c "from src.agent.loop import AgentLoop; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat: wire enemy pattern episodes into combat conversation rounds"
```

---

### Task 9: Cleanup and Verification

**Files:**
- All modified files

- [ ] **Step 1: Run full import chain verification**

```bash
python -c "
from src.brain.v2_engine import V2Engine
from src.brain.v2_backend import V2Backend
from src.brain.decision_parser import extract_decision, validate_decision
from src.brain.enemy_pattern_injector import format_enemy_patterns, format_upcoming_patterns
from src.brain.conversation import CombatConversation
from src.brain.prompts.system import get_system_prompt, SYSTEM_COMBAT, SYSTEM_COMBAT_BOSS, SYSTEM_DECKBUILD, SYSTEM_STRATEGIC
from src.brain.tool_schemas import get_tool_for_state
from src.brain.evolution_engine import EvolutionEngine
from src.memory.models_v2 import WorkingContext
from src.memory.retriever import query_for_decision
from src.memory.prompt_injector import format_working_context
from src.agent.loop import AgentLoop
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 2: Run all existing tests**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | head -80
```

Expected: No import errors. Some tests may fail due to removed interfaces — fix those in next step.

- [ ] **Step 3: Fix any broken test imports**

Search tests for references to deleted modules/functions:

```bash
grep -rn "query_tools\|get_v2_tools\|get_v2_combat_tools\|get_tool_choice\|combat_episode_hints\|_agent_loop\|add_tool_result" tests/
```

For each match: update to use new interfaces or delete if testing removed functionality.

- [ ] **Step 4: Verify no stale references in codebase**

```bash
grep -rn "from src.brain.query_tools\|import query_tools\|QUERY_TOOLS\|QUERY_TOOL_NAMES\|is_query_tool\|combat_episode_hints" src/ --include="*.py"
```

Expected: No matches (all references removed).

- [ ] **Step 5: Run new tests**

```bash
python -m pytest tests/test_enemy_pattern_injector.py tests/test_decision_parser.py -v
```

Expected: ALL PASS

- [ ] **Step 6: Commit final cleanup**

```bash
git add -A
git commit -m "chore: fix broken tests and remove stale query_tools references"
```

---

### Task 10: Integration Test with Live LLM

**Files:** None (manual testing)

- [ ] **Step 1: Run a single game step to verify `<decision>` protocol works**

```bash
python -m scripts.run_agent --steps 5 --runs 1 2>&1 | tail -30
```

Watch for:
- `V2Engine[...]: decision extracted` log messages (success)
- `V2Engine: no <decision> block` log messages (failure → triggers repair)
- No `tool_use` or `tool_choice` in logs

- [ ] **Step 2: Run a full combat encounter**

```bash
python -m scripts.run_agent --steps 50 --runs 1 2>&1 | grep -E "decision extracted|repair|fallback"
```

Expected: Mostly "decision extracted" with occasional repairs. Zero fallbacks in a good run.

- [ ] **Step 3: Verify enemy patterns appear in logs**

```bash
python -m scripts.run_agent --steps 100 --runs 1 2>&1 | grep -E "Enemy Patterns|Likely upcoming"
```

Expected: Enemy pattern sections appear in combat after the agent has fought the same enemy type at least once.

- [ ] **Step 4: If issues found, fix and re-test**

Common issues:
- Kimi 2.5 ignores `<decision>` tag → strengthen system prompt example
- JSON malformed → check repair loop fires correctly
- Enemy patterns too verbose → reduce `_MAX_ROUNDS` or `_MAX_EPISODES`

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "test: verify tool-use removal with live Kimi 2.5 integration"
```
