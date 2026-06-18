# Combat Trace Injection for Postrun Build Analysis & Card Note Updates

**Date:** 2026-04-24
**Status:** Design — pending implementation plan
**Related:**
- `docs/superpowers/specs/2026-04-10-card-note-system-overhaul-design.md` (note field contract)
- `docs/superpowers/specs/2026-04-23-character-build-guide-registry.md` (build_role_observations)
- `src/memory/core_engine_extractor.py` (precedent: append-only qualitative observation via LLM)

## 1. Problem

Two independent but tightly coupled gaps in the postrun pipeline:

**Goal A — Build analysis is evidence-starved.**
`card_build_extractor.analyze_build_with_llm` currently feeds the analysis LLM only aggregated
signals (card counts, damage engine tags, weak-point flags). The resulting `build_summary` /
`damage_engine` / `weak_points` fields miss concrete combat reality: which cards actually
carried damage, how the engine behaved turn-over-turn, which replans fired and why. Output
quality is capped by what aggregation preserves.

**Goal B — `CardMemory.note` almost never updates.**
`card_memory_extractor.py` is purely deterministic — it merges counters every run but does
not touch `note`. `note` is therefore effectively a seed-only field (`load_seeds` populates
it once; nothing writes to it afterward). This is the most-injected qualitative per-card
hint for deck decisions (reward / shop / card_select surface all three hint types but
`note` is the one that has content for 90%+ of cards). It is stale relative to the agent's
actual experience with the card.

Both goals share the same expensive context: a faithful, high-fidelity trace of 1-2 real
combats from the run. Producing that trace is the cost; using it twice amortizes it.

## 2. Scope

**In scope:**
- A combat trace renderer that reconstructs the last N combats with hand-level fidelity (per-card values, enchantments, keyword descriptions, intents, powers, relics, agent plans, replans).
- Extending Turn 1 (`analyze_build_with_llm`) to receive the trace as additional user context; output schema unchanged.
- A new Turn 2 postrun LLM call (`card_note_updater`) that shares cached trace context and emits selective `note` rewrites.
- Extending `CardMemory` with `note_history` (audit trail, bounded depth).
- Config gates for staged rollout (trace-off / trace-on/write-off / trace-on/write-on).

**Out of scope:**
- Changes to the two append-only observation tuples (`core_engine_observations`,
  `build_role_observations`) — they have independent extractors with different schemas.
- Auto-rollback tooling for bad notes (deferred to a future CLI).
- Seed-note protection (per prior decision — seeds are overwritable).
- New decision-type injection paths. Existing `deck` decision-type injection already surfaces `note` via `effective_note()`.

## 3. Architecture

### 3.1 Data flow

```
post-run hook
   │
   ├─ combat_trace_renderer.render_last_two_combats(short_term, run_log_events)
   │     └─ returns combat_trace_text: str | None   (~6-10k tokens when present)
   │
   ├─ TURN 1: card_build_extractor.analyze_build_with_llm(..., combat_trace_text=...)
   │     ├─ system: <DECKBUILD baseline>            [cache_control: ephemeral]
   │     ├─ user:   <evidence>
   │     │         <combat_trace_text>               [cache_control: ephemeral]
   │     │         <instructions>
   │     └─ returns BuildAnalysis (schema unchanged)
   │
   ├─ TURN 2: card_note_updater.update_card_notes_from_traces(
   │                short_term, run_log_events, card_memory_store,
   │                combat_trace_text, candidate_cards, ...)
   │     ├─ system: <note_updater system>            [cache_control: ephemeral]
   │     ├─ user:   <combat_trace_text>              [cache HIT from Turn 1 within 5-min TTL]
   │     │         <card memory table>               (per-run, not cached)
   │     │         <instructions>
   │     ├─ parse + validate proposals
   │     └─ store.put(CardMemory.with_new_note(...)) for each kept proposal
   │
   └─ continue postrun (extract_card_build_memory → consolidate_guides → ...)
```

Turn 1 and Turn 2 are both `analysis` tier (default `STS2_ANALYSIS_MODEL`, e.g.
gpt-5.4-thinking / pro-preview). No new tier. Turn 2 is independent — it does not extend
V2Backend for true multi-turn — it is a second API call that reuses Turn 1's trace bytes
inside the 5-minute ephemeral cache TTL.

### 3.2 New modules

**`src/memory/combat_trace_renderer.py`** (new):
- `render_last_two_combats(short_term: ShortTermMemory, run_log_events: list[dict]) -> str | None`
- `extract_candidate_cards(last_two_combats) -> list[str]` — all card names appearing across hand_at_start + played, deduped case-insensitively.
- `_render_single_combat(combat: CompletedCombat, events: list[dict]) -> str` — produces a block per combat.
- `_render_round(round_num: int, hand: list[dict], player_state, enemy_state, intent, plan, replans) -> str`.
- Produces plaintext optimized for LLM readability; no JSON, no BBCode.

**`src/memory/card_note_updater.py`** (new):
- `update_card_notes_from_traces(...) -> tuple[int, int, int]` returns `(written, kept_unchanged, invalid)`.
- Builds prompt, calls V2Backend analysis tier, parses JSON, validates per-proposal, writes via `CardMemoryStore.put` + `CardMemory.with_new_note`.

### 3.3 Modified modules

**`src/memory/models_v2.py`** — `CardMemory`:
- New field `note_history: tuple[dict, ...] = ()` where each entry is
  `{note: str, run_id: str, reason: str, trace_citation: str, ts: float}`.
- Capped at 3 most-recent versions (oldest evicted on insert).
- New method `with_new_note(new_note: str, run_id: str, reason: str, trace_citation: str) -> CardMemory` — returns a replace()-produced copy with `note` set to the new value and a new entry prepended to `note_history` (then truncated to 3).
- `to_dict` / `from_dict` serialize `note_history` as list of dicts. `from_dict` tolerates missing field (old files load with `()` — backward compatible).
- `effective_note()` unchanged — continues to return `self.note`.

**`src/memory/card_build_extractor.py`** — `analyze_build_with_llm`:
- New parameter `combat_trace_text: str | None = None`.
- Prompt construction extended: when trace present, append a clearly-delimited section after the evidence block, before the instructions:

  ```
  ## Recent Combat Traces

  The following are full turn-by-turn traces of the 1-2 most recent combats in this run.
  Use them as ground truth for how the deck actually played: which cards carried damage,
  how the engine behaved round-over-round, where the agent replanned and why.

  <combat_trace_text>
  ```

- Output schema (build_summary, damage_engine, weak_points, synergy_notes, win_conditions,
  primary_plan, analysis_confidence) unchanged. The LLM simply has richer context.
- cache_control placed on the user trace message segment so Turn 2 can hit cache.

**`src/log/session_logger.py`** — `_serialize_hand_card`:
- Add fields needed for trace fidelity:
  - `upgraded: bool` — from the card model's upgrade state
  - `star_cost: int | None` — for ★-cost cards
  - `card_type: str` — Attack / Skill / Power
  - `enchantment_name: str | None` — when enchanted
- These are additive; existing consumers keep working.

**`src/agent/loop.py` or `scripts/run_agent.py`** — postrun hook:
- Between build_analysis LLM call and `extract_card_build_memory`, call
  `combat_trace_renderer.render_last_two_combats` once, pass the result into Turn 1,
  then into Turn 2. Single renderer call per run; `None` short-circuits both turns.

### 3.4 Turn 1 prompt append (build_analysis)

Existing build-analysis prompt retains its structure. Added block when trace is present:

```
## Recent Combat Traces (ground truth)

Below are full round-by-round traces of the 1-2 most recent combats. Each round shows
the real hand with exact values and keyword descriptions, the enemy state and intent,
the agent's plan and reasoning, and any replans. Use these to ground your build_summary
and damage_engine in what actually happened rather than what aggregated counts suggest.

<combat_trace_text>
```

No schema change. No instruction rewording.

### 3.5 Turn 2 prompt (card_note_updater) — full contract

**System prompt** (concise, static — cacheable):

```
You review postrun combat traces and selectively propose updates to per-card notes.
A note is a <=200-character deck-building hint surfaced when the card appears in a
reward / shop / card_select decision. It should capture non-obvious role or risk
information that aggregated counters cannot express.

Output STRICTLY a JSON object:
{
  "updates": [
    {
      "card_name": "backstab",
      "new_note": "<=200 chars>",
      "reason": "<1 line — why this note, what trace moment justifies it>",
      "trace_citation": "<exact short quote from trace, e.g. 'Combat 2 Round 3: played Backstab for 11 dmg after Sly>'"
    }
  ]
}

Empty list if nothing in the traces warrants an update. Never invent cards. Only use
card names that appear in the provided candidate list.
```

**User prompt sections** (in order):
1. Combat trace text (bytewise identical to Turn 1 — critical for cache hit).
2. Candidate-card table: `name | current_note | play_count | sly_play | total_damage | total_block`.
3. Instructions: "For each candidate card, decide whether the traces justify a new/updated note. Favor cards where the trace reveals something the current note misses, or where the card has no note yet. Keep notes terse, concrete, and oriented toward future deck-building decisions."

**Validation rules** (applied in `card_note_updater.parse_note_updates`):
- `card_name` must be in candidate list (case-insensitive match, canonical lowercase stored).
- `new_note` must be non-empty and ≤ 200 characters. Violations → drop that proposal.
- `reason` must be non-empty (≤ 200 chars).
- `trace_citation` must be non-empty. Not checked against trace text (LLM hallucination check is not worth the cost in a closed offline pipeline).
- Bad JSON → discard entire response, log warning, return `(0, 0, 0)`.

**Write path**:

```python
mem = store.get(char, card_name) or CardMemory(character=char, card_name=card_name)
mem = mem.with_new_note(
    new_note=new_note,
    run_id=run_id,
    reason=reason,
    trace_citation=trace_citation,
)
store.put(mem)
```

Cards with no existing memory get a fresh `CardMemory` entry — first note is also the
first `note_history` entry. `with_new_note` prepends to history and truncates to 3.

### 3.6 Interrupted-run gate

Before calling the renderer:
```python
recent = short_term.completed_combats[-2:]
floor_sum = sum(c.floor for c in recent)
if floor_sum < config.POSTRUN_TRACE_MIN_FLOOR_SUM:   # default 15
    return None   # skip renderer; Turn 1 runs without trace; Turn 2 skipped
```

This filters out short aborted runs where deck state is not meaningful enough to inform
note updates.

## 4. Config

Four new env vars:

| var | default | behavior |
|---|---|---|
| `STS2_POSTRUN_COMBAT_TRACE_ENABLED` | `true` | Master switch. Off → Turn 1 runs without trace (current behavior); Turn 2 skipped entirely. |
| `STS2_POSTRUN_NOTE_UPDATE_ENABLED` | `false` | Turn 2 write gate. Off → Turn 2 runs in dry-run mode (logs proposals, no store writes). |
| `STS2_POSTRUN_TRACE_MIN_FLOOR_SUM` | `15` | Floor-sum threshold for interrupted-run filter. |
| `STS2_POSTRUN_TRACE_MAX_ROUNDS` | `30` | Per-combat round cap. Combats exceeding this are dropped (not truncated). |

Rollout plan:
1. Ship with defaults above → observe Turn 1 quality and Turn 2 dry-run proposals for 2-3 days.
2. Flip `STS2_POSTRUN_NOTE_UPDATE_ENABLED=true` after manual spot-check of ≥10 proposal batches.

## 5. Caching

Both turns send `cache_control: {"type": "ephemeral"}` on:
- The static system prompt (already done for Turn 1; new for Turn 2).
- The trace user-message segment (new for both).

Constraints:
- Trace text must be byte-identical between Turn 1 and Turn 2 (same `combat_trace_text` Python string, not re-rendered).
- Turn 2 must be invoked inside the 5-minute TTL from Turn 1 start — `_safe_post_run()` calls them back-to-back with no intervening LLM calls.
- Turn 2's system prompt is independent (not shared with Turn 1), so system-side cache is per-turn.

Expected savings: trace ~6-10k tokens; Turn 2 input cost drops to ~10% of uncached cost on cache hit. Turn 1 also benefits from re-use on subsequent runs where short_term.completed_combats[-2:] is disjoint from prior runs, but cache is ephemeral so this is a secondary effect.

V2Backend support: already accepts `cache_control` on system; extension needed to accept breakpoints on specific user-message segments. Cleanest path — let `analyze_build_with_llm` and `update_card_notes_from_traces` assemble their own pre-structured message lists (list of `{role, content[], cache_control}` dicts) and pass them through a thin backend method rather than the current `prompt: str` + `system: str` signature. If that refactor is too invasive for this change, a narrower extension accepting `user_cache_segments: list[tuple[str, bool]]` (text, cache_breakpoint) is acceptable.

## 6. Error handling

Layered fail-closed policy — any failure degrades to current behavior without aborting the run.

**Renderer layer** (`combat_trace_renderer.py`):
- Missing run_log_events / file unreadable → return `None`, log warning.
- < 1 completed combat available → return `None`.
- Per-combat state-snapshot match failure → drop that combat, keep the other. Both fail → `None`.
- Any single combat exceeds `POSTRUN_TRACE_MAX_ROUNDS` → drop that combat.

**Turn 1 layer** (build_analysis):
- Existing fallback (heuristic build summary) preserved. Trace is purely additive.
- If Turn 1 LLM call fails, Turn 2 is skipped (no cached context to ride on, independent Turn 2 not worth the cost).

**Turn 2 layer** (card_note_updater):
- LLM timeout / empty response → skip writes, log warning, return `(0, 0, 0)`.
- JSON parse failure → skip all writes for this run (no partial salvage — too easy to write garbage).
- Per-proposal validation failure → drop that proposal, continue with the rest. Increments `invalid` counter.
- All proposals invalid → `(0, 0, N)` is a legitimate outcome, not an error.

**Write layer**:
- `CardMemoryStore.put` already thread-safe. `with_new_note` handles 3-version cap internally. Disk errors on save propagate to the outer postrun error boundary — no special handling.

## 7. Observability

Postrun log emits:
- `postrun_trace: rendered %d combats, %d chars, %d candidate cards` on successful render.
- `postrun_trace: skipped (floor_sum=%d < threshold=%d)` on gate failure.
- `postrun_trace: turn2 proposals written=%d kept_unchanged=%d invalid=%d` per run.
- Every persisted note change carries `reason` + `trace_citation` in `note_history` — inspect via `jq` on the CardMemoryStore JSON file.

No new metrics endpoint. First version is inspect-by-file.

## 8. Testing strategy

**Unit tests** (new `tests/test_combat_trace_renderer.py`):
- Fixture: synthetic 2-combat short_term (elite + boss) with matching run_log_events containing hand_at_start_enriched, decision events with replans, plan reasoning.
- Assertions:
  - Output contains relic names + descriptions.
  - Each round renders full hand with damage/block values AND rules_text (matches CombatConversation density).
  - Replans are tagged visibly (e.g. `[REPLAN]` marker).
  - `max_rounds` exceeded → combat dropped from output.
  - 1-combat case handled (returns rendered text, not `None`).
  - 0-combat case returns `None`.
  - `extract_candidate_cards` dedupes case-insensitively across hand + played across combats.

**Unit tests** (new `tests/test_card_note_updater.py`):
- Fixture: pre-rendered trace text + prepared CardMemoryStore + mocked V2Backend returning fixed JSON.
- Assertions:
  - Valid proposal writes successfully; `note_history` grows by 1.
  - `new_note` > 200 chars → dropped; `invalid` counter increments.
  - Unknown card name → dropped.
  - Mixed batch (2 valid, 2 invalid) → 2 writes, 2 invalid, store saves cleanly.
  - Card with no existing memory → `CardMemory` created from scratch with first note.
  - `note_history` at capacity (3) → oldest evicted on new insert.
  - Bad JSON response → `(0, 0, 0)`, no writes.

**Unit tests** (append to `tests/test_card_memory.py`):
- `CardMemory.with_new_note` appends to history, caps at 3.
- `to_dict` / `from_dict` roundtrip `note_history`.
- `from_dict` on a dict missing `note_history` yields an empty tuple (backward compat with existing JSON files).

**Integration test** (optional, new `tests/test_postrun_trace_integration.py`):
- Write a realistic run_log_events.jsonl via session_logger fixtures.
- Run full renderer → Turn 1 (mocked) → Turn 2 (mocked) → assert final CardMemoryStore state.

No regression or E2E tests needed — feature does not enter the decision-making hot path.

## 9. Risks

- **Trace fidelity gap**: if hand_at_start_enriched is incomplete for certain card types (enchanted / star-cost / upgraded), trace will misrepresent the combat. Mitigation: session_logger changes in §3.3 cover the known gaps. Pre-implementation audit of 3 combat logs recommended.
- **Cache miss on trace byte mismatch**: if Turn 1 and Turn 2 re-derive the trace independently, the resulting Python strings may differ by a newline or spacing. Mitigation: renderer is called exactly once, result is passed through memory to both turns.
- **Note quality regression**: Turn 2 LLM may produce notes that are worse than seeds. Mitigation: `STS2_POSTRUN_NOTE_UPDATE_ENABLED=false` default for initial rollout; manual review of ≥10 batches before flipping on; `note_history` preserves prior versions for manual audit / future rollback tool.
- **Token budget on analysis tier**: two trace-bearing calls per run at ~10k tokens each. Mitigation: ephemeral cache hit on Turn 2 trace; existing `STS2_POSTRUN_ENABLED` master switch still applies.
- **Silent failure accumulation**: if renderer has a subtle bug that drops one combat silently, Turn 1 & Turn 2 degrade without visible symptom. Mitigation: logger line on every render records combat count — spot-check in logs after rollout.

## 10. Non-goals (explicit)

- Modifying `core_engine_observations` or `build_role_observations` — separate pipelines, different schemas, different triggers.
- Injecting `note` into combat prompts — current injection scope (deck-type decisions only) is unchanged.
- Auto-rollback of bad notes — `note_history` provides manual audit; CLI rollback tool deferred.
- Making seed notes immutable — per prior decision, seeds are overwritable; write path does not special-case them.
- Multi-run trace aggregation — this feature acts on the current run only. Cross-run evidence remains the job of append-only observation tuples with their own extractors.
