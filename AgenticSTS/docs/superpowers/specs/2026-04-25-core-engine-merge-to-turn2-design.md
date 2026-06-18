# Core-Engine Stage Merge into Turn 2 (card_note_updater)

**Date:** 2026-04-25
**Status:** Design — pending implementation plan
**Related:**
- `docs/superpowers/specs/2026-04-24-combat-trace-postrun-analysis-design.md` (Turn 1 / Turn 2 pipeline this spec extends)
- `src/memory/core_engine_extractor.py` (existing extractor; partially retained, partially deleted)
- `src/agent/loop.py:4353` `_post_run_core_engine_update` (the stage being removed)

## 1. Problem

The postrun pipeline currently has four stages: `memory` → `core_engine` → `skills` → `evolution`. The `core_engine` stage has three independent issues:

1. **Trigger is too narrow.** Fires only on Act 3 boss victory. Most runs never reach it, so the entire stage is dead weight on losing runs.
2. **Does not reuse the Turn 1 / Turn 2 trace cache.** It builds its own context (`_load_run_log_events_for_core_engine` + `package_round_context` + a custom prompt) instead of consuming the `combat_trace_text` that Turn 1 already rendered. Two trace renderings + two cache misses on the same run.
3. **Routed to the wrong model tier (silent bug).** `_post_run_core_engine_update` calls `call_raw(call_type="core_engine_summary", ...)`. The router's name heuristic (`llm_caller.py:111-117`) sees the substring `"summary"` and routes the call to `postrun_summary`, which is the monitor's lightweight chain (`gpt-5.4-mini`) rather than the analysis tier (`gemini-3.1-pro-preview`). It is the only call site in the codebase that accidentally trips this heuristic.

The output of the stage — per-card `core_engine_observations` (role-tagged, append-only) — is genuinely useful at deck-time retrieval (`retriever.py:651-660`). The data is not the problem; the dispatch is.

## 2. Scope

**In scope:**
- Delete the `core_engine` postrun stage and its method `_post_run_core_engine_update`.
- Extend `card_note_updater` (Turn 2) to optionally emit a `core_engine` block in the **same LLM call**, gated on the run being an Act 3 boss victory.
- Reuse `core_engine_extractor.apply_to_card_memory` to persist the merged output to per-card `CardMemory.core_engine_observations`.
- Delete the now-unused prompt-building functions in `core_engine_extractor.py` (`build_analysis_prompt`, `package_round_context`, `select_top_damage_rounds`, `extract_core_engine`).
- Bundle the model-tier routing bug fix: by removing the offending call site, the bug ceases to exist. No code is added to the heuristic.

**Out of scope:**
- Changes to the `core_engine_observations` schema on `CardMemory`. Existing data on disk is preserved bit-for-bit.
- Changes to retriever-side injection (`format_core_engine_hint`).
- Decoupling `consolidation_count` from `mistake_discovery` (covered in spec #2 / #3).
- Touching the `llm_caller.py:111-117` heuristic itself. It will keep working for the call sites that genuinely want the summary chain (monitor); we just remove the only erroneous consumer.

## 3. Architecture

### 3.1 Stage diagram

Before:
```
postrun:
  memory (Turn 1 build_analysis + Turn 2 card_note_updater + guides + mistake_discovery)
  core_engine  ← deleted by this spec
  skills
  evolution
```

After:
```
postrun:
  memory (Turn 1 + Turn 2[expanded] + guides + mistake_discovery)
  skills
  evolution
```

### 3.2 Turn 2 call expansion

`update_card_notes_from_traces` gains one new parameter and one new output channel:

```python
async def update_card_notes_from_traces(
    *,
    store: CardMemoryStore,
    character: str,
    combat_trace_text: str,
    candidate_cards: list[str],
    run_id: str,
    is_act3_boss_victory: bool = False,   # NEW
    final_deck: list[str] | None = None,  # NEW — only used when is_act3_boss_victory
    final_relics: list[str] | None = None,# NEW — only used when is_act3_boss_victory
    dry_run: bool = False,
) -> Turn2Result:                          # NEW return type
    ...
```

Where:
```python
@dataclass(frozen=True)
class Turn2Result:
    notes_written: int
    notes_kept_unchanged: int
    notes_invalid: int
    core_engine_applied: int   # cards updated via apply_to_card_memory
    core_engine_emitted: bool  # True iff LLM produced a non-empty core_engine block
```

There is exactly one call site (`loop.py:4337`). It is updated to consume the new `Turn2Result` return type directly. No backward-compat adapter is introduced.

### 3.3 Prompt extension

System prompt (cacheable) gains one paragraph at the end:

```
Additionally, when the calling instructions explicitly state "this run won
the Act 3 final boss", you MUST also output a `core_engine` field with this
shape:
  "core_engine": {
    "engine_mechanic": "<abstract description of how the deck scaled, e.g.
      'stacking continuous passive debuff damage while stalling'>",
    "core_cards": ["<1-3 card or relic names that provided multiplicative
      scaling>"],
    "support_cards": ["<cards that generated, applied, or cycled the
      mechanic; may be empty>"],
    "notes": "<1-2 sentences describing the synergy concretely>"
  }

Rules: (1) core_cards must reference cards in the provided final deck or
relics. (2) engine_mechanic is abstract — do NOT use archetype labels
(shiv/poison/panache/etc.); describe the action or trigger. (3) If the
win came from raw tempo with no clear scaling engine, engine_mechanic
should say so and core_cards may be empty. (4) Omit the `core_engine`
field entirely when the calling instructions do not say "Act 3 final
boss".
```

User-message tail (after the existing candidate-card table) gains a
conditional section, only when `is_act3_boss_victory=True`:

```
## This run won the Act 3 final boss

Final deck (at end of run):
- <card 1>
- <card 2>
...

Final relics:
- <relic 1>
- <relic 2>
...

Identify the core engine of this winning deck per the rules in the
system prompt. Output the `core_engine` field alongside `updates`.
```

When `is_act3_boss_victory=False`, this section is **not rendered** and the system-prompt rule prevents the LLM from emitting `core_engine`. We do not validate by absence — we validate by ignoring the field if the gate is off (defensive: a misbehaving LLM does not corrupt the store).

### 3.4 Output schema

```json
{
  "updates": [
    { "card_name": "...", "new_note": "...", "reason": "...", "trace_citation": "..." }
  ],
  "core_engine": {
    "engine_mechanic": "...",
    "core_cards": ["..."],
    "support_cards": ["..."],
    "notes": "..."
  }
}
```

`core_engine` is optional. When absent, parsed value is `None` and no `core_engine_observations` writes occur.

### 3.5 Parsing & validation

`parse_note_updates` is extended (or a sibling `parse_turn2_response` is
introduced) to also extract `core_engine`. Reuses
`core_engine_extractor.parse_analysis_response` for the inner-block
parsing — that parser is already tolerant of code-fence wrapping, missing
fields, and non-dict roots; same parser, same validation.

Gate logic in the updater:
- If `is_act3_boss_victory` is `False` and the LLM emits `core_engine`
  anyway → log warning, drop the block (do not call `apply_to_card_memory`).
- If `is_act3_boss_victory` is `True` and the LLM emits an empty / no
  `engine_mechanic` and no `core_cards` → log info "no clear engine
  identified", no writes. This is a legitimate outcome (per existing
  rule 3 in core_engine_extractor's prompt).
- If `is_act3_boss_victory` is `True` and the parsed `core_engine` is
  well-formed → call `apply_to_card_memory(result, store,
  character=..., run_id=...)`. The existing function handles the role
  tagging and observation append.

### 3.6 Caller wiring (loop.py)

`_post_run_memory_update` (or the surrounding caller of Turn 2) computes
`is_act3_boss_victory` from `short_term.completed_combats`:

```python
recent = short_term.completed_combats
is_act3_boss_victory = bool(
    recent
    and recent[-1].act == 3
    and recent[-1].combat_type == "boss"
    and recent[-1].won
    and run_state.victory  # belt-and-suspenders
)
```

`final_deck` and `final_relics` are taken from the same combat episode's
`context.deck_cards` and `relics` (already populated by gameplay).

The `_post_run_core_engine_update` method (loop.py:4353-4451) and the
`_load_run_log_events_for_core_engine` helper (loop.py:4453-4480) are
deleted. The `core_engine` stage logging block in `_safe_post_run`
(loop.py:2856-2883) is deleted. The `session_logger.log_post_run_stage`
calls go from 4 known stages to 3.

### 3.7 Files affected

**Modified:**
- `src/memory/card_note_updater.py` — extended prompt, extended parser, extended return type, optional `core_engine` apply.
- `src/agent/loop.py` — delete `_post_run_core_engine_update`,
  `_load_run_log_events_for_core_engine`; delete the `core_engine` stage
  block in `_safe_post_run`; extend the Turn 2 call site to pass
  `is_act3_boss_victory` + final deck/relics; consume new
  `Turn2Result` return type.
- `src/memory/core_engine_extractor.py` — delete unused prompt-build /
  context-package functions. Keep `find_final_boss_combat` (still useful
  as a helper if a caller wants the predicate explicitly), keep
  `apply_to_card_memory` and `_append_observation`, keep `empty_result`
  and `parse_analysis_response` (now invoked from card_note_updater).
- `src/log/session_logger.py` — `log_post_run_stage` callers / monitor
  table no longer expect a `core_engine` row.

**Deleted:**
- The four prompt-building / round-packaging functions in
  `core_engine_extractor.py`: `build_analysis_prompt`,
  `package_round_context`, `select_top_damage_rounds`,
  `extract_core_engine`.

**Untouched:**
- `CardMemory.core_engine_observations` schema (`models_v2.py`).
- `format_core_engine_hint` injector (`core_engine_extractor.py:472`).
- `retriever.py` retrieval pipeline.
- Existing on-disk `card_memories.json` content.

## 4. Config

No new env vars. The existing `STS2_POSTRUN_COMBAT_TRACE_ENABLED` and
`STS2_POSTRUN_NOTE_UPDATE_ENABLED` continue to gate the merged Turn 2
exactly as today.

When `STS2_POSTRUN_NOTE_UPDATE_ENABLED=false` (dry-run mode), both
`note` updates and `core_engine` writes are dropped — neither is
written. Logging surfaces both proposed counts.

## 5. Caching

Turn 2 still passes `combat_trace_text` as `user_cached_prefix` and
hits Turn 1's cache as today. The new prompt content (system-prompt
paragraph + conditional user-message tail) is appended outside the
cached prefix — adding it does not invalidate the cache hit.

The system prompt grows by ~120 words. It is also marked
`cache_control: ephemeral`, so the system-side cache is also preserved
as long as the prompt content is byte-identical run-to-run.

## 6. Error handling

Layered fail-closed, mirrors Turn 2's existing policy:

- LLM call failure → `Turn2Result(0, 0, 0, 0, False)`. No writes anywhere.
- JSON parse failure → same as above.
- `updates` valid but `core_engine` malformed → `updates` written
  normally, `core_engine_applied=0`, `core_engine_emitted=False`. We
  do not let a bad engine block poison good note updates.
- `is_act3_boss_victory=True` but LLM emits empty engine block →
  legitimate outcome, `core_engine_applied=0`, `core_engine_emitted=True`.
- `is_act3_boss_victory=False` but LLM emits engine block anyway →
  warning logged, block dropped, `core_engine_applied=0`,
  `core_engine_emitted=False`.

## 7. Observability

Postrun log emits one consolidated line per Turn 2 invocation:

```
postrun_trace: turn2 notes_written=%d kept=%d invalid=%d  engine_applied=%d engine_emitted=%s
```

The monitor's stage table loses the `core_engine` row entirely. This is
a UI-visible change; mention in commit message.

`log_postrun_artifact` continues to emit per-write artifacts, with a
new `kind="core_engine_observation"` for engine-applied cards (carries
role + engine_mechanic in the artifact summary).

## 8. Testing strategy

**Unit tests** (extend `tests/test_card_note_updater.py`):
- `is_act3_boss_victory=True` + LLM emits valid engine → engine
  applied, `core_engine_applied` matches `len(core_cards)+len(support_cards)`.
- `is_act3_boss_victory=True` + LLM emits empty engine → no writes,
  `core_engine_emitted=True`.
- `is_act3_boss_victory=True` + LLM omits engine field → no writes,
  `core_engine_emitted=False`.
- `is_act3_boss_victory=False` + LLM emits engine anyway → engine
  dropped, warning logged, no writes.
- Mixed batch: valid notes + valid engine in same response → both
  applied, both counters non-zero.
- Mixed batch: valid notes + malformed engine → notes applied, engine
  not applied, `notes_written>0` and `core_engine_applied=0`.

**Unit tests** (`tests/test_core_engine_extractor.py`):
- Drop tests covering the deleted functions (`build_analysis_prompt`,
  `package_round_context`, `select_top_damage_rounds`,
  `extract_core_engine`).
- Keep tests for `find_final_boss_combat`, `apply_to_card_memory`,
  `parse_analysis_response`, `empty_result`. These are the surviving
  contract.

**Integration test** (optional new test or extension of existing):
- A run-log fixture that ends with an Act 3 boss victory, exercise the
  full memory stage, assert that both `note` and `core_engine_observations`
  are written.

No regression / E2E tests required — feature does not enter the
decision-making hot path.

## 9. Risks

- **Prompt complexity.** Turn 2 now juggles two output channels with
  different semantics. Risk: LLM produces good `updates` but bad
  `core_engine`, or vice versa. Mitigation: per-channel parse + apply,
  no atomic all-or-nothing. Documented in §6.
- **Schema drift.** Future changes to either channel must keep the JSON
  envelope stable; renaming `updates` or `core_engine` would require
  a rolling parser change. Mitigation: name the keys defensively in
  the parser (`parsed.get("updates", [])`, `parsed.get("core_engine")`)
  — already the pattern.
- **Quality regression on engine identification.** The old core_engine
  prompt fed only the top-3 highest-damage rounds with custom
  packaging. The new merged prompt feeds the *full combat trace*
  (already rendered for Turn 1/2 use). Net direction is more context,
  not less — but the engineered focus on top-damage rounds is gone.
  Mitigation: the system prompt's existing rules ("identify multiplicative
  scaling", "abstract — no archetype labels") remain literal; the LLM
  has more material to apply them to, not less.
- **Bug fix is implicit.** The model-tier routing bug is fixed by
  *removing the buggy call site*, not by patching the heuristic. If
  someone later adds a new postrun call with a `*_summary` `call_type`,
  they will silently re-enter the same trap. Mitigation: prepend a
  `# WARNING:` comment **immediately above the `if not call_class:`
  block at `llm_caller.py:108`** (the first line of the heuristic),
  stating that callers whose `call_type` contains the substrings
  "summary" or "consolidat" but who actually want the analysis tier
  must pass explicit `call_class="postrun_analysis"` to bypass the
  heuristic.

## 10. Non-goals (explicit)

- Cleaning up the `llm_caller.py` heuristic. Too easy to break the
  monitor summarizer that legitimately wants the summary chain. Out of
  scope for this spec.
- Re-introducing top-damage round selection inside the new prompt.
  The full trace already includes per-round damage numbers; the LLM
  can pick what it cares about.
- Cross-run engine aggregation. Each run still produces one
  observation per contributing card; the engine-injection retriever
  surfaces all observations for the queried character/card. No new
  aggregation logic.
- Touching `core_engine_observations` schema. New writes use the
  existing field, including the existing `co_cards` array and the
  existing role tags.
