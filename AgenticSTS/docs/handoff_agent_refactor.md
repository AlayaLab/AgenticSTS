# Handoff Prompt: Align Python Agent with MCP v0.3.0

Copy everything below the line into a new Claude Code session.

---

## Task

Refactor the Python autonomous agent (`AgenticSTS\src\`) to fully leverage the STS2MCP mod v0.3.0 REST API features. The mod was recently refactored (service-oriented architecture, SSE streaming, structured intents, `available_actions`, enriched state fields), but the Python agent only partially uses these new capabilities.

## What's Already Working

The agent already uses:
- **SSE streaming**: `wait_for_state_change()` and `wait_for_play_phase()` in `src/mcp_client/client.py` (10 call sites in `loop.py`)
- **Structured intents**: `src/brain/prompts/_intent_fmt.py` uses `damage`/`hits`/`total_damage` fields with label fallback
- **Knowledge database**: `src/knowledge/` (577 cards, 121 monsters, 64 potions, 68 events)
- **`available_actions`**: Pydantic model has the field, `game_state.py` has property — but **never checked by agent loop**

## What Needs to Change

### 1. Use `available_actions` for Action Validation (HIGH PRIORITY)

The agent currently uses `state_type` if-else chains to decide what handler to call. The mod now returns `available_actions` in every state response — use it.

**Current pattern** (in `src/agent/loop.py` `_decide_and_act()`):
```python
if gs.state_type in ("monster", "elite", "boss"):
    return await self._handle_combat(gs)
elif gs.state_type == "map":
    return await self._handle_map(gs)
elif gs.state_type == "event":
    ...
```

**Target pattern**:
```python
actions = gs.available_actions  # list[str] from mod

# Pre-validate before sending any action
if "play_card" in actions or "end_turn" in actions:
    return await self._handle_combat(gs)
elif "choose_map_node" in actions:
    return await self._handle_map(gs)
elif "choose_event_option" in actions or "advance_dialogue" in actions:
    return await self._handle_event(gs)
...
```

**Key changes:**
- In `_decide_and_act()`: dispatch based on `available_actions` instead of `state_type`
- Before each `post_action()` call: validate the action name is in `available_actions`
- Pass `available_actions` to LLM prompts so the model knows what's legal
- Handle edge cases: `available_actions` may be empty during transitions

**Files to modify:**
- `src/agent/loop.py` — main dispatch + pre-validation
- `src/state/game_state.py` — add helper methods like `can_play_card()`, `can_end_turn()`, etc.

### 2. Improve Menu Navigation with Atomic Actions (MEDIUM)

The agent currently calls `start_new_run` in a retry loop with sleeps (5-10 calls, ~2.5s delay each). The mod now supports atomic menu actions.

**Current** (in `scripts/run_agent.py`):
```python
async def _ensure_run_started(client, character):
    for attempt in range(20):
        result = await client.post_action(actions.start_new_run(character))
        await asyncio.sleep(2.5)
        state = await client.get_state()
        if state.get("state_type") not in ("menu", "game_over", ...):
            return True
    return False
```

**Target**: Use atomic actions from `src/mcp_client/actions.py`:
```python
async def _ensure_run_started(client, character):
    state = await client.get_state()
    avail = state.get("available_actions", [])

    if "return_to_main_menu" in avail:
        await client.post_action(actions.return_to_main_menu())
        await client.wait_for_state_change("game_over")

    state = await client.get_state()
    avail = state.get("available_actions", [])

    if "open_character_select" in avail:
        await client.post_action(actions.open_character_select())
        await asyncio.sleep(1.0)

    state = await client.get_state()
    avail = state.get("available_actions", [])

    if "select_character" in avail:
        await client.post_action(actions.select_character(character=character))
        await asyncio.sleep(0.5)

    if "embark" in avail or ...:
        await client.post_action(actions.embark(character=character))
        await client.wait_for_state_change("character_select")
```

The actions are already defined in `src/mcp_client/actions.py` (lines 114-173):
- `return_to_main_menu()`
- `open_character_select()`
- `select_character(character=...)`
- `embark(character=...)`
- `open_timeline()`
- `close_main_menu_submenu()`
- `choose_timeline_epoch(option_index=...)`
- `confirm_timeline_overlay()`

### 3. Pass `available_actions` to LLM Prompts (MEDIUM)

Currently, LLM prompts describe valid actions in static text. Injecting the actual `available_actions` list would reduce hallucinated actions.

**Files to modify:**
- `src/brain/prompts/combat.py` — add available actions list
- `src/brain/prompts/combat_plan.py` — same
- `src/brain/prompts/event.py` — same
- `src/brain/prompts/rest.py` — same
- `src/brain/prompts/shop.py` — same
- `src/brain/prompts/reward.py` — same
- `src/brain/reasoner.py` — pass `available_actions` through to prompt builders

### 4. Use `unplayable_reason` for Smarter Card Selection (LOW)

The mod now returns `unplayable_reason` as a snake_case code on each hand card. The agent currently only checks if a card is playable (boolean). Using the reason allows better LLM reasoning.

**Current** (in combat prompts):
```
Hand: [0] Strike (1E) [1] Defend (1E) [UNPLAYABLE] [2] Carnage (2E)
```

**Target**:
```
Hand: [0] Strike (1E) [1] Defend (1E) [UNPLAYABLE: not_enough_energy] [2] Carnage (2E)
```

**File:** `src/brain/prompts/combat.py`, `combat_plan.py` — include `unplayable_reason` in hand card formatting.

### 5. Use `character` Field in Run Info (LOW)

The mod now returns `character` in the run info. Use this in prompts instead of detecting it from relics or other heuristics.

**File:** `src/mcp_client/models.py` — `RunInfo` already has `character: str = ""`
**File:** Various prompt files — can reference `gs.run.character` directly

## Files Reference

### Python Agent (to modify)
```
src/
  mcp_client/
    client.py          — McpClient (get_state, post_action, wait_for_*)
    models.py          — Pydantic models (GameStateResponse, etc.)
    actions.py         — 18 action builders (play_card, end_turn, etc.)
    sse_client.py      — SSE stream client
  state/
    game_state.py      — GameState wrapper
  agent/
    loop.py            — Core agent loop (main refactoring target)
  brain/
    reasoner.py        — LLM prompt builder
    prompts/           — All prompt templates
scripts/
  run_agent.py         — Entry point with multi-run loop
```

### MCP Mod REST API (read-only reference)
```
Base URL: http://localhost:15526
GET  /api/v1/singleplayer              — game state (?format=json|markdown)
POST /api/v1/singleplayer              — execute action {"action": "...", ...}
GET  /api/v1/events                    — SSE event stream
GET  /api/v1/multiplayer               — multiplayer state
POST /api/v1/multiplayer               — multiplayer action
```

### API Doc
```
AgenticSTS\STS2MCP\docs\raw_api.md     — full API reference
```

### available_actions by state_type
```
monster/elite/boss  → play_card, end_turn, combat_select_card, combat_confirm_selection, use_potion
hand_select         → combat_select_card, combat_confirm_selection
combat_rewards      → claim_reward, select_card_reward, skip_card_reward, proceed
card_reward         → select_card_reward, skip_card_reward
map                 → choose_map_node
event               → choose_event_option, advance_dialogue
rest_site           → choose_rest_option, proceed
shop                → shop_purchase, proceed
card_select         → select_card, confirm_selection, cancel_selection
relic_select        → select_relic, skip_relic_selection
treasure            → claim_treasure_relic, proceed
menu (various)      → open_character_select, open_timeline, start_new_run, etc.
```

### Structured Intent Fields
```json
{
  "intent_type": "attack",
  "damage": 12,
  "hits": 3,
  "total_damage": 36,
  "status_card_count": null
}
```
Already used in `src/brain/prompts/_intent_fmt.py`.

## Execution Order

1. **available_actions dispatch** — refactor `loop.py` `_decide_and_act()` to use actions-based dispatch
2. **Pre-validation** — add validation before every `post_action()` call
3. **GameState helpers** — add `can_play_card()`, `can_end_turn()`, etc. to `game_state.py`
4. **Menu navigation** — replace `start_new_run` loop with atomic actions in `run_agent.py`
5. **LLM prompt injection** — pass `available_actions` to prompt builders
6. **unplayable_reason + character** — minor prompt improvements
7. **Test** — run agent for 2-3 runs to verify no regressions

## Constraints

- **DO NOT modify any C# mod code** — mod is stable at v0.3.0
- **Preserve existing LLM/skill/memory integration** — only change how actions are dispatched/validated
- **Keep backward compatibility** — `available_actions` may be empty on older mod versions, fall back to state_type dispatch
- **Preserve immutability** — all Pydantic models use `frozen=True`
- **No new dependencies** — use existing httpx, pydantic, etc.
- Run with: `python -m scripts.run_agent --steps 500 --runs 1`
