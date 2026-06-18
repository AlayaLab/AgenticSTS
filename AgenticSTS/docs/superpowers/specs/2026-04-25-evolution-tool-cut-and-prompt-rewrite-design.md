# Evolution Stage: Tool-Surface Cut and Prompt Rewrite

**Date:** 2026-04-25
**Status:** Design — pending implementation plan
**Hard dependencies:** none. The tools this spec deletes (`update_card_note`, `update_guide`) duplicate capabilities that already exist in main today (Turn 2 `card_note_updater` landed before this spec was written; `guide_consolidator` has been there longer). Spec #1 (core_engine merge) and spec #2 (skills relocation) do not gate any change here.
**Recommended sequence:** land #1 → #2 → #3 in that order for stage-diagram and merge tidiness. None of the file edits across #1/#2/#3 overlap on the same lines, but reasoning about "what does the postrun pipeline look like right now" is easier when each one is reviewed against the previous landed state.
**Related:**
- `src/brain/evolution_engine.py` (2794 lines, the engine being thinned)
- `src/brain/write_tools.py:239` (`MUTATING_WRITE_TOOLS` list being trimmed)
- `src/postrun/context_builder.py` (1058 lines, sections being pruned)
- `docs/superpowers/specs/2026-04-24-combat-trace-postrun-analysis-design.md` (the trace cache being shared)

## 1. Problem

After the recent Turn 2 card-note-updater landing (already in main), evolution's write surface has two tools that duplicate work the memory stage already does:

- `update_card_note` — duplicates `card_note_updater` (Turn 2). Same source data (the run's combat trace), competing writes to `CardMemory.note`.
- `update_guide` — duplicates `guide_consolidator`. Worse, evolution `update_guide` writes targeted patches that the next consolidator cycle will silently overwrite, creating a write-write race across stages.

(Note: `core_engine_observations` is written by `core_engine_extractor.apply_to_card_memory` directly — there has never been an `update_card_observations` tool in evolution. Spec #1 moves that write into Turn 2; evolution is unaffected either way.)

The remaining write tools are `write_skill` and `author_tool`. Both have unique value the memory stage can't replicate:
- `write_skill` from evolution sees **cross-run aggregates** (`get_performance_stats`) that single-run mistake_discovery cannot.
- `author_tool` is the only path for new dynamic Python tools.

Beyond the tool cut, evolution's prompt and context plumbing have drifted out of sync with the post-trace pipeline:
- The system prompt is reconstructed per phase (`_phase_system_prompt`) with embedded dynamic strings — no caching.
- The user message (built by `context_builder.py`) does not reuse the rendered combat trace from Turn 1/2, so it pays the trace tokens twice.
- `write_skill` accepts loose multi-field input with validation scattered across 1500+ lines of `_handle_write_skill` branches — no schema-strict shape forcing the LLM to ground its proposals.
- 5-round budget (2 read-only + 3 write) was sized for 4 write tools; with 2, three rounds of writing is over-provisioned.

## 2. Scope

**In scope:**
- Delete two tools from `MUTATING_WRITE_TOOLS`: `update_card_note`, `update_guide`. Delete their handlers (`_handle_update_card_note`, `_handle_update_guide`).
- Rewrite the `write_skill` tool **schema** to require structured `evidence` + `rationale` fields per proposal.
- Rewrite the evolution **system prompt** to a static, cacheable shape — phase distinction collapsed to a one-line `## Phase: read-only` / `## Phase: write` marker that does NOT invalidate the cached prefix.
- Wire evolution to consume the **same `combat_trace_text`** Turn 1/2 produced, as a `cache_control: ephemeral` user-message prefix, sharing the 5-minute TTL across the three calls.
- Cut evolution context bundle (`context_builder.py`) to only sections evolution still needs: cross-run summary, replay package (kept, evolution-unique), dynamic-tools list, triggered-skills log. Drop card-notes section, drop deck-guide section (both now consumed inside Turn 1/2).
- Reduce round budget from 5 to 3 (read_only ≤ 2, write ≤ 1).

**Out of scope:**
- Splitting `evolution_engine.py` into smaller modules. Mechanical refactor; covered in spec #4.
- Touching `author_tool` or its validation pipeline.
- Touching the 4-level write gate or merge pipeline (`src/skills/merge_pipeline.py`). New `write_skill` proposals continue to flow through the gate unchanged.
- Touching `RECALL_ENCOUNTER_SCHEMA` (gameplay query tool that evolution borrows). Stays.
- Adding new query tools (e.g., `get_card_play_stats`). Future spec if needed.

## 3. Architecture

### 3.1 Tool surface before / after

Before (evolution sees 6 tool schemas):
| Tool | Source | Status |
|---|---|---|
| `recall_encounter` | `tool_executor.py: QUERY_TOOL_SCHEMAS` | Kept |
| `get_performance_stats` | `write_tools.py: READ_PHASE_TOOLS` | Kept |
| `author_tool` | `write_tools.py: MUTATING_WRITE_TOOLS` | Kept |
| `write_skill` | `write_tools.py: MUTATING_WRITE_TOOLS` | **Schema rewrite** |
| `update_guide` | `write_tools.py: MUTATING_WRITE_TOOLS` | **Delete** |
| `update_card_note` | `write_tools.py: MUTATING_WRITE_TOOLS` | **Delete** |

After (4 schemas):
- Read-phase tools: `recall_encounter`, `get_performance_stats`.
- Write-phase tools: `write_skill` (rewritten), `author_tool`.

### 3.2 New `write_skill` schema (strict)

Current schema accepts a loose dict with optional fields. New schema enforces:

```json
{
  "skill_name": "human-readable name (e.g. 'Poison lethal timing')",
  "category": "combat | deck_building | map | rest | shop | event | boss | character | general",
  "trigger_state_types": ["combat | deck_select | reward | ..."],
  "trigger_enemy_names": ["..."],
  "trigger_requires_cards": ["..."],
  "trigger_character": ["..."],
  "content": "≤ 400 chars, second-person imperative, concrete and trigger-shaped",
  "motivation": "what gameplay experience motivated this",
  "evidence": {
    "run_ids": ["..."],
    "stat_basis": "1-line description of the cross-run stat that motivates this skill, e.g. 'win rate 18% on knowledge_demon vs 42% baseline across silent runs'",
    "anchor_episode": "<run_id>:<combat_id> — the closest single concrete episode to the abstract pattern"
  },
  "rationale": "≤ 300 chars — why mistake_discovery cannot have caught this from a single run's trace. If you cannot answer this, do not propose."
}
```

**Note on schema shape**: trigger fields are flat (`trigger_state_types`, `trigger_enemy_names`, etc.) at the top level rather than nested under a `trigger` object. This preserves the pre-existing schema contract that the downstream `SkillTrigger` extraction logic expects. `content` length cap is 400 (not 600) — also preserved from before this spec.

The `rationale` field is the gate-keeper: it forces the LLM to articulate "this is a cross-run pattern, not a single-trace mistake." If the LLM cannot fill it convincingly, the proposal should not exist. Validation in code:
- Empty / placeholder rationale → reject (return error string to LLM as `rejected: rationale insufficient`).
- `evidence.run_ids` must contain ≥ 2 distinct ids (cross-run by construction).
- `evidence.stat_basis` must reference a stat the LLM could only have learned via `get_performance_stats` (presence of digits + comparator words like "rate", "%", "vs", "baseline" — heuristic, not strict).

The existing 4-level write gate, dedup, and dual-anchor merge pipeline run unchanged downstream.

### 3.3 Cacheable system prompt

Today: `_phase_system_prompt(is_read_phase: bool) -> str` returns one of two distinct strings, ~200 chars different. Different bytes → different cache hit.

After: one static system prompt covering both phases. Phase is signaled by a one-line `## Current phase: read-only` / `## Current phase: write` line in the **user message tail** (after the cached trace prefix). The system prompt body becomes invariant per evolution call, with `cache_control: {"type": "ephemeral"}` set on the system block.

Net: system prompt cache hit rate goes from 0% (per-phase variation) to >90% (within 5-min TTL across the 3 rounds of one postrun).

### 3.4 Shared trace cache

The user message structure becomes:

```
[user]
  cache_control: ephemeral  ←── combat_trace_text  (BYTE-IDENTICAL to Turn 1/2)
  ───────────────────────────
  (uncached tail)
  ## Current phase: read-only | write
  ## Cross-run summary
  ...
  ## Replay package (anomalies)
  ...
  ## Triggered-skill log (this run)
  ...
  ## Dynamic tools (current registry)
  ...
  ## Task
  ...
```

The trace prefix is the same Python string passed to Turn 1 and Turn 2. Evolution is invoked AFTER skills stage but still within the 5-minute TTL of Turn 1's first emission, so the cache hit applies. (Per the existing combat-trace spec, the cache TTL is the binding constraint; postrun fires the three calls back-to-back with no intervening LLM traffic.)

Implication for `build_evolution_context` (in `evolution_engine.py` today; relocated to `context_builder.py` by spec #4): it stops emitting trace-equivalent material. The `_render_replay_package` / `_render_combat_guides` / `_render_card_notes` helpers that overlapped with the trace either go away or shrink to cross-run-only content. The first three live in `evolution_engine.py` at the time spec #3 lands; spec #3 deletes the latter two outright and trims `_render_replay_package`.

### 3.5 Evolution-context section pruning

(Sections are emitted by `build_evolution_context` and its `_render_*` helpers in `evolution_engine.py`; spec #4 will move the surviving ones to `context_builder.py` afterwards.)

| Section | Before | After |
|---|---|---|
| Run summary | ~200 tokens | ~200 tokens (kept) |
| Dynamic tools list | ~150 tokens | ~150 tokens (kept) |
| Replay package (cross-episode anomalies) | ~12-22k tokens | ~6-10k tokens (kept; capped to **anomalies only**, drop normal-mode replays) |
| Combat guides | ~3-6k tokens | **0** (consolidator owns guides; evolution does not write them anymore) |
| Deck guides | ~1-3k tokens | **0** (Turn 1 reads its own; evolution does not need) |
| Card notes | ~2-5k tokens | **0** (Turn 2 reads / writes; evolution does not need) |
| Triggered-skills log | ~500 tokens | ~500 tokens (kept; cross-run pattern signal) |

Estimated cut: 30-50% of `build_evolution_context` output size. Concretely: `EVOLUTION_REPLAY_TOKEN_BUDGET=40000` may be lowered to ~25000 after this change, but the budget knob is left as-is in this spec to avoid coupling.

### 3.6 Round budget

Today: `EVOLUTION_READ_ONLY_ROUNDS=2`, `EVOLUTION_MAX_ROUNDS=6`. Net 4 write rounds available.

After: `EVOLUTION_READ_ONLY_ROUNDS=2`, `EVOLUTION_MAX_ROUNDS=3`. Net 1 write round.

Rationale: with two write tools and a strict schema demanding cross-run grounding, any given postrun produces at most one well-supported skill *or* one new dynamic tool. Allowing more write rounds invites the LLM to lower its bar to fill rounds.

The constants live in `config.py` as `EVOLUTION_READ_ONLY_ROUNDS` / `EVOLUTION_MAX_ROUNDS`. Update defaults; keep env-var override.

### 3.7 Files affected

**Modified:**
- `src/brain/write_tools.py`:
  - Remove `UPDATE_CARD_NOTE`, `UPDATE_GUIDE` from `MUTATING_WRITE_TOOLS`.
  - Rewrite `WRITE_SKILL` schema per §3.2.
- `src/brain/evolution_engine.py`:
  - Delete `_handle_update_guide` (~140 lines, L1935-2073).
  - Delete `_handle_update_card_note` (~100 lines, L2234-2336).
  - Rewrite `_handle_write_skill` (~160 lines L1372-1533) for the new schema. Keep downstream calls (validation, dedup, merge pipeline). Add per-field validation for `evidence`, `rationale`, plus the rationale-quality heuristic.
  - Replace `_phase_system_prompt` with a single static `EVOLUTION_SYSTEM_PROMPT` constant.
  - Pass `combat_trace_text` into the engine and route it through `call_raw(user_cached_prefix=...)` — extends `V2Backend.acall` plumbing if needed (or use the same `user_cached_prefix` path the analysis-tier helper exposes).
- `src/brain/evolution_engine.py` (renderer deletion sites):
  - Drop `_render_combat_guides` (L2473), `_render_deck_guides` (L2503), `_render_card_notes` (L2543) outright. They emit removed sections; spec #4 will not need to relocate them.
  - Drop their call sites in `build_evolution_context` (also in `evolution_engine.py` at L2624 today; spec #4 relocates the surviving renderers + builder to `context_builder.py`).
  - Adjust `EvolutionContextBundle.summary` keys to drop those section stats.
- `src/agent/loop.py:4548` `_post_run_evolution`:
  - Read the rendered `combat_trace_text` from where Turn 1/2 stashed it (e.g., `self._pending_combat_trace`) and pass into `engine.run_evolution(..., combat_trace_text=...)`.
- `config.py`:
  - `EVOLUTION_MAX_ROUNDS` default 5 → 3.

**Untouched:**
- `RECALL_ENCOUNTER_SCHEMA`.
- `GET_PERFORMANCE_STATS` and `_handle_performance_stats`.
- `AUTHOR_TOOL` and `_handle_author_tool`.
- `src/skills/merge_pipeline.py`, `src/memory/write_gate*`.

### 3.8 Migration of in-flight data

- Existing `data/evolution/evolution_log.jsonl` continues to load fine (we add no fields, only stop emitting two tool names).
- Existing dynamic tools (authored via `author_tool`) keep working.
- Existing skills written by the OLD `write_skill` schema remain in `skills.json`; the new schema only constrains *new* writes.

## 4. Config

| Var | Old default | New default | Notes |
|---|---|---|---|
| `EVOLUTION_MAX_ROUNDS` | 5 | 3 | env override unchanged |
| `EVOLUTION_READ_ONLY_ROUNDS` | 2 | 2 | unchanged |
| `EVOLUTION_TARGET_INPUT_TOKENS` | (current) | (unchanged for now) | naturally drops after §3.5; tighten in a follow-up |
| `EVOLUTION_REPLAY_TOKEN_BUDGET` | 40000 | (unchanged for now) | naturally drops; tighten in a follow-up |

No new env vars.

## 5. Caching

- System prompt: marked `cache_control: ephemeral` once, content is invariant across phases.
- User-message trace prefix: same `cache_control: ephemeral` blob Turn 1/2 emit.
- All three evolution rounds within one postrun share the same trace prefix → cache hits on rounds 2 and 3 (~2 cache hits within evolution).

**What does NOT happen** (correction from earlier draft): Anthropic prompt cache is keyed on the FULL prefix including the system prompt. Turn 1/2 use `_NOTE_UPDATER_SYSTEM` while evolution uses `EVOLUTION_SYSTEM_PROMPT` — different system prompts mean different cache keys, so the trace bytes alone do NOT make Turn 1/2's emit and evolution's emit share a cache entry. Trace cache reuse is intra-stage (within evolution's 3 rounds), not cross-stage. The savings are modest but real (~33% input cost reduction across rounds 2-3 of evolution).

## 6. Error handling

Existing per-tool fail-closed behavior preserved:
- Tool exceptions return error strings to the LLM, which can retry with corrected input or move on.
- Round-level exceptions are caught in `run_evolution` and emit a meta log entry.

New layer: schema validation on `write_skill` proposals.
- Missing required field → return `rejected: missing field <name>` to the LLM.
- `evidence.run_ids` < 2 distinct → `rejected: evidence requires ≥2 cross-run ids`.
- `rationale` empty or trivial (e.g., < 30 chars, contains no negation referring to mistake_discovery) → `rejected: rationale must justify cross-run origin`.

The LLM has the rest of the round to retry. With write_rounds=1, retry consumes the round; the engine logs `noop` if no proposal lands.

## 7. Risks

- **Cache TTL miss between Turn 2 and evolution.** If mistake_discovery in the skills stage runs long enough to push evolution past the 5-minute TTL, the trace prefix cache is stale and the savings disappear. Mitigation: monitor cache-hit rate via existing telemetry; if miss rate is high on consolidation cycles, the fix is to skip mistake_discovery on a fraction of cycles or to run evolution in parallel (out of scope here).
- **Schema rigor → empty postruns.** A strict `write_skill` schema combined with a 1-write-round budget will produce many no-op evolution rounds. This is the intended tradeoff (quality over quantity), but visible as "evolution done, 0 actions" in the monitor. Mitigation: surface `noop` clearly in artifact logs; document the expected drop in commit message.
- **Section pruning regressions.** If evolution silently relied on a removed context section (e.g., references a card name surfaced only in `_render_card_notes`), proposals may degrade. Mitigation: a small audit before merge — grep for the dropped section content within `evolution_engine.py` and check no internal logic depends on it.
- **Round budget too tight.** 3 rounds total may not be enough when read-only investigation truly needs >2 turns. Mitigation: default 3, but env-overridable up to 5 for power users / ablation runs.
- **Stale tool docs / external references.** External docs / monitor frontend may still reference `update_guide` / `update_card_note`. Mitigation: grep `frontend/` and `docs/` for the tool names; update.

## 8. Testing strategy

**Unit tests:**
- `tests/test_write_tools.py`: schema-validation tests for the new `write_skill` shape — required fields, rationale length, run_ids cardinality.
- `tests/test_evolution_engine.py` (existing or new): assert that calling `engine.run_evolution(...)` with a stub backend that emits a malformed `write_skill` returns the expected `rejected: ...` string, and the LLM's retry on the same round actually retries.
- `tests/test_context_builder.py` (new or extend): assert `build_evolution_context(...)` emits sections per §3.5 and excludes the dropped sections; assert returned bundle's section stats keys match.

**Integration test (light):**
- A fully mocked postrun cycle with a fake backend that:
  1. Round 0 (read-only) calls `get_performance_stats`.
  2. Round 1 (read-only) calls `recall_encounter`.
  3. Round 2 (write) emits one `write_skill` proposal with valid schema.
  Assert: 3 rounds total; cache prefix matches Turn 1/2 emit; one skill candidate hits the write_gate.

**Smoke (deferred):**
- Single live postrun on a known-good run with `STS2_LOG_LEVEL=DEBUG` to confirm cache_hit telemetry on rounds 1 and 2.

## 9. Non-goals (explicit)

- Adding new query tools. The cross-run signal toolkit (`get_performance_stats` + `recall_encounter`) is held constant. Future spec.
- Splitting `evolution_engine.py` (spec #4 mechanical refactor).
- Replacing the 4-level write gate / merge pipeline. Out of scope.
- Re-enabling `update_guide` as a "patch" tool with conflict resolution against the consolidator. The race is real and not worth working around; consolidator owns guides.
- Re-introducing `update_card_note` as an evolution tool. Turn 2 owns it; evolution can't add value (single-run trace already saturates the per-card hint signal).
- Letting evolution write `core_engine_observations`. Turn 2 (after spec #1) owns it; same reasoning.
