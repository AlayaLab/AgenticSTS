# Memory system

Reference for the Hierarchical Categorical Memory (HCM) and the per-decision context composition. For module locations see [`ARCHITECTURE.md`](ARCHITECTURE.md). For postrun extraction pipeline see [`SELF_EVOLUTION.md`](SELF_EVOLUTION.md).

## 5-layer knowledge model

Paper's conceptual spine. Postrun-writable layers in **bold**:

| Layer | Content | Storage | Postrun-writable? |
|-------|---------|---------|-------------------|
| L1 | System prompts (COMBAT / COMBAT_BOSS / DECKBUILD / STRATEGIC) | `src/brain/prompts/system.py` | No (immutable except game-version patches) |
| L2 | Per-decision state prompts (reward, shop, map, event, rest, ...) | `src/brain/prompts/*.py` | No |
| L3 | Game knowledge (~577 cards / 121 monsters / 64 potions / 68 events / 289 relics / 87 encounters) | `data/knowledge/` | No (refreshed per game patch via `scripts/apply_patch.py`) |
| **L4** | **HCM domain stores + extractors + retriever + guides** | `../AgenticSTS-Data/memory/` | **Yes** |
| **L5** | **Skill library** (seeds + Mode B stubs + mistake-discovered) | `../AgenticSTS-Data/skills/` | **Yes** (4-level write gate) |

Plus: dynamic tools at `../AgenticSTS-Data/evolution/tools/` (postrun-writable, AST-sandboxed).

PE deprecation (2026-04-18) made L1/L2 immutable to postrun. See [`SELF_EVOLUTION.md`](SELF_EVOLUTION.md#pe-deprecation-2026-04-18-negative-result).

## Per-decision stateless context composition

Architecture invariant: every LLM call gets a freshly composed user message. No history accumulates across decisions.

### Combat decisions

`CombatConversation` (`src/brain/conversation.py`) is created at COMBAT_START and destroyed at COMBAT_END. It maintains internal `_messages: list[dict]` for compression / summary bookkeeping, but the `llm_messages` property at `conversation.py:343-377` truncates to:

```python
[combat_start, {"role": "assistant", "content": "ok"}, latest_user_state]
```

Prior round assistant plans, validation errors, and execution results sit in `_messages` but are **never sent to the LLM**. Per the docstring at `conversation.py:347-353`:

> All prior rounds, stale assistant plans, and intermediate re-plan states are dropped — small models (e.g. Qwen) misread multi-turn history and misjudge energy/hand state. The latest user message MUST be self-contained.

`add_round_state` re-injects on every round (including re-plans):
- Strategic Thread (from `_strategic_notes`)
- Combat rules
- Enemy patterns (from past episodes, via `enemy_pattern_injector`)
- Potions
- Keyword glossary

The `combat_start` + `"ok"` prefix is a **static cache anchor** for Anthropic prompt caching, not accumulated history.

When `STS2_COMBAT_CONVERSATION_ENABLED=false`, `_generate_combat_plan` builds a fresh per-round CombatConversation and discards it — making the architecture *literally* stateless even by `_messages` accumulation. This is the ablation-baseline branch.

### Non-combat decisions

`V2Engine.decide_noncombat` at `v2_engine.py:474+` builds:

```python
messages: list[dict] = [{"role": "user", "content": user_content}]
```

Fresh every call. No state crosses decision boundaries.

### What does cross decision boundaries?

Three things — all are **rebuilt-from-store, not message-history**, so the LLM never sees deltas:

1. **In-prompt rebuilt state**: Strategic Thread, retriever-built `memory_context`, `skill_context`, `card_notes`, cached relics — all flow into the *current* user message text. Re-rendered fresh from `ShortTermMemory` / domain stores each call.
2. **Within-decision repair turns**: `_single_call` may append one repair turn for validation retry. Bounded by single decision; no leakage.
3. **Cached metadata**: `V2Engine.__init__` holds only `_backend`, `_executor`, `_session_logger`. No message cache. `_v2_combat_conversation` lives on `AgentLoop`, destroyed at combat end.

## Strategic thread (scoped notes)

`Decision.strategic_note` (string field on `src/state/run_state.py::Decision`) flows into `ShortTermMemory.record_strategic_note(note, *, scope, context_type, ...)` → `STM._strategic_notes: list[StrategicNote]` (`src/memory/short_term.py:455`).

### Scopes

| Scope | Lifetime | Use case |
|-------|----------|----------|
| `turn` | One turn | Within-combat tactical hypothesis |
| `combat` | One fight | Cross-turn combat plan |
| `run` | Entire run | Build identity, win condition, key pieces, gaps |

Notes have `triggers` (context types) for per-decision-type filtering — only relevant notes inject into a given prompt.

### Three injection sites

1. `src/brain/conversation.py` — combat user message (`add_round_state`)
2. `src/memory/prompt_injector.py::format_working_context` — non-combat HCM injection
3. `src/postrun/context_builder.py::_render_strategic_thread` — evolution context (floor-grouped)

### Save/quit replay persistence

When the agent reloads a save (skill eval boss replay path), `_v2_combat_conversation._strategic_notes` is snapshotted before the reload and re-injected into the new conversation. `strategic_thread=` from STM is also passed to `decide_noncombat` so non-combat replays preserve run-level context.

## HCM domain stores

All under `../AgenticSTS-Data/memory/v2/`. Each store has model + extractor + storage class:

| Store | Model | Extractor | Retrieval key | Persistence |
|-------|-------|-----------|--------------|-------------|
| `combat_episodes.jsonl` | `CombatEpisode` | `combat_extractor.py` | enemy_key × character | `CombatMemoryStore` |
| `route_memories.jsonl` | `RouteMemory` | `route_extractor.py` | act × character | `RouteMemoryStore` |
| `card_builds.jsonl` | `CardBuildMemory` | `card_build_extractor.py` | character × archetype | `CardBuildStore` |
| `event_memories.jsonl` | `EventMemory` | `event_extractor.py` | event_id × character | `EventStore` |
| `card_memories.json` | `CardMemory` | `card_memory_extractor.py` | character × **base card name** | `CardMemoryStore` |
| `guides.json` | `CombatGuide` / `RouteGuide` / `DeckGuide` / `EventGuide` | `guide_consolidator.py`, `event_guide_consolidator.py` | various | `GuideStore` |

### Card memory: base name canonical (2026-04-25)

`Strike` / `Strike+` / `Strike++` share **one** slot in `card_memory_store`. Per-card statistics aggregate over all upgrade levels. Eliminates fragmentation across upgrades.

### Combat trace rendering

For postrun analysis prompts, combat traces are rendered through:
- `combat_trace_renderer.py` — main trace renderer
- `combat_trace_plan_grouper.py` — group consecutive plan turns
- `combat_trace_delta.py` — delta-formatted (state diffs only) variant

`combat_delta.py` provides per-action HP / block / energy / powers diffs between snapshots; `situation.py` tags rounds with `hand_capabilities` + `damage_taken` + `outcome_quality` (only — `threat_level` / `intent_class` / `deck_stage` removed 2026-04-20).

## Retriever (decision-type-aware)

`src/memory/retriever.py::retrieve_for(gs, ...)` returns a `WorkingContext` with fields filtered by decision type:

- `_classify_decision_type(gs)` derives the decision type from `GameState`
- Per-decision-type retrieval picks relevant guides / episodes / card memories / strategic notes
- `prompt_injector.py::format_working_context` renders into a `## ...` block structure for prompt injection

Trim contract: any new field added to `WorkingContext` must be registered in `_trim_working_context`'s `all_fields` AND `rebuild` kwargs (otherwise lost on trimming).

## Short-term memory

`ShortTermMemory` (`src/memory/short_term.py`) holds mutable working state for the **current run**:

- Combat tracker (current fight in progress)
- Route nodes by act
- Deck events (additions, removals, upgrades, transformations)
- Card play counts (with Sly-specific subset)
- Starting deck snapshot
- Completed events
- Strategic notes (`list[StrategicNote]`)
- Deck identity string

Cleared on `reset_run()`. Persisted to JSONL log (not memory store) for postrun extraction.

`STS2_STM_ENABLED=false` disables STM entirely (Strategic Thread also gone). Used in baseline ablation conditions.

## Postrun extraction flow

After each run (in `_post_run_memory_update`):

1. Read JSONL log for the run
2. For each domain extractor, derive episodes / memories from the trace
3. Write to domain store via `MemoryManager` facade
4. Cadence-gated: every N runs, run guide consolidators (LLM)
5. Cadence-gated: card_note_updater refines per-card notes (LLM, postrun bucket B for non-deck cards)

`MemoryManager` (`src/memory/memory_manager.py`) is the unified facade for all HCM stores + guides.
