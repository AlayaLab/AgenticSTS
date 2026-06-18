# Postrun Cache Cleanup + Class-Pool Injection (Turn 1 / Turn 2)

**Date:** 2026-05-01
**Status:** Design — pending implementation plan
**Related:**
- `docs/superpowers/specs/2026-04-24-combat-trace-postrun-analysis-design.md` (Turn 1 / Turn 2 pipeline this spec modifies)
- `docs/superpowers/specs/2026-04-25-core-engine-merge-to-turn2-design.md` (Turn 2 already gained a second output channel; this spec adds a third)
- `src/memory/card_build_extractor.py` (Turn 1)
- `src/memory/card_note_updater.py` (Turn 2)
- `src/brain/llm_caller.py` (`user_cached_prefix` branch being deleted)

## 1. Problem

Two independent issues, bundled because they touch the same two files (Turn 1 / Turn 2) and the same prompts.

### 1.1 The `user_cached_prefix` cache hack does not work

`card_build_extractor.analyze_build_with_llm` and `card_note_updater.update_card_notes_from_traces` both pass `combat_trace_text` to `call_raw(user_cached_prefix=...)`. The intent was Anthropic prompt-cache reuse across the two turns within the 5-minute TTL. In practice it is a no-op for two compounding reasons:

1. **Provider mismatch.** The default postrun analysis family is Gemini, dispatched via the `openai_compatible` relay. `cache_control: {"type": "ephemeral"}` is silently dropped by every OpenAI-compatible upstream the relay routes to. `llm_caller.py:79-80` documents this explicitly. The two turns currently run with zero cache hits.
2. **System-prompt mismatch.** Even if the family were switched back to Anthropic, Turn 1 uses `_BUILD_ANALYSIS_SYSTEM` and Turn 2 uses `_NOTE_UPDATER_SYSTEM`. Anthropic's prompt cache is keyed on the consecutive prefix up to each `cache_control` breakpoint; with different `system` blocks the user-prefix cache entries are different cache keys. Cross-turn reuse is impossible without a shared system prompt.

Net effect: the two-block user-message marshalling, the dual telemetry codepath in `llm_caller.py:319-325`, and three tests exist to support a feature that produces no cache hits.

### 1.2 Postrun has no class-pool visibility

Both Turn 1 and Turn 2 see only cards that appeared in the rendered combat trace (deck cards that were drawn or played). The full class card pool — 88 cards for Silent, 88 for Regent — is not in scope of either prompt. Two consequences:

- **Turn 1 (build analysis)** judges `weak_points` and `damage_engine` against only the cards the deck actually has. It cannot reason about counterfactuals ("the deck lacked AoE; Catalyst / Caltrops were available in the pool") because it does not know what the pool contains.
- **Turn 2 (card_note_updater)** writes notes only for cards that appeared in the trace. Notes about cards the run *rejected* (skipped at reward / shop) and notes capturing build-relative pool intuition ("Catalyst is the canonical poison-build payoff; take whenever offered") cannot exist. The current `candidate_cards` is the deck-subset that played, and the system prompt forbids inventing cards outside the candidate list.

The information cost of injecting the pool is small: ~88 cards × ~80 chars/card ≈ 7 KB ≈ 1.7 K tokens for one character. The class is per-run (one character per run), so we inject only that character's pool. No Colorless.

## 2. Scope

**In scope:**

1. Delete `user_cached_prefix` parameter from `call_raw`, the multi-block branch in `llm_caller.py:88-104`, and the matching telemetry branch (`llm_caller.py:319-325`). Remove `tests/test_llm_caller_cache.py` entirely. Rewrite the two `test_card_build_extractor_json.py` tests that asserted the old cache contract to instead assert the trace is inlined into `prompt`.
2. Inline `combat_trace_text` into the user-message body of Turn 1 and Turn 2 (one text block instead of two). Existing system-prompt language ("trace appears at the top of this user message") remains accurate.
3. Inject a static **Class Pool Reference** section into the system prompt of both Turn 1 (`_BUILD_ANALYSIS_SYSTEM`) and Turn 2 (`_NOTE_UPDATER_SYSTEM`), built per-character at call time from `data/knowledge/upstream/cards.json`.
4. Add **Bucket B** to Turn 2's note channel: up to 3 non-deck card notes per run, each carrying an `evidence_type` field (`"skipped" | "combo_inferred"`).
5. Add `extract_skipped_cards(run_log_events)` helper that pulls offered-but-not-picked card names from `card_reward` / `shop` decisions in `logs/run_*.jsonl`. Wire it into `_analyze_build_async` so the candidate set passed to Turn 2 carries both played and skipped cards (with the latter tagged so Turn 2 knows the difference).

**Out of scope:**

- Changing the per-card `CardMemory` schema. `with_new_note` continues to write the same fields; `evidence_type` is recorded inside the human-readable `reason` text (e.g. `"[skipped] traded Catalyst for Footwork at floor 9"`) rather than as a typed field, to avoid a store-format migration.
- Injecting upgraded card stats. Reflection on "should I have upgraded X?" is left to a future iteration; V1 omits upgrade deltas to keep token volume to ~1.7 K.
- Injecting Colorless cards.
- Touching gameplay-time prompts (`reward.py`, `shop.py`, `card_select.py`). This spec is postrun-only.
- `src/brain/cache_diagnostics.py` — used only on the gameplay path, untouched.

## 3. Architecture

### 3.1 Cache-cleanup edits

| File | Change |
| --- | --- |
| `src/brain/llm_caller.py` | Drop the `user_cached_prefix` parameter, the `if user_cached_prefix:` branch (lines 88-104), and the matching telemetry branch (lines 319-325). `messages` always becomes the single-string form `[{"role": "user", "content": prompt}]`. |
| `src/memory/card_build_extractor.py` | In `analyze_build_with_llm`, when `combat_trace_text` is non-empty, prepend it to `prompt` directly (with the existing `instruction_note` immediately before the evidence block). Remove `user_cached_prefix=` from the `call_raw` call. |
| `src/memory/card_note_updater.py` | In `update_card_notes_from_traces`, prepend `combat_trace_text + "\n\n"` to the rendered `prompt`. Remove `user_cached_prefix=` from the `call_raw` call. The system prompt's "traces at the top of this user message" wording stays valid. |
| `tests/test_llm_caller_cache.py` | Delete. |
| `tests/test_card_build_extractor_json.py` | Replace the two `user_cached_prefix`-asserting tests with assertions that the trace text appears as a substring of the captured `prompt`. |

No other call site uses `user_cached_prefix=` (verified via grep across `src/`).

### 3.2 Class pool injector

New module: `src/knowledge/class_pool_injector.py`.

```python
def render_class_pool_section(character: str, kb: GameKnowledge | None = None) -> str:
    """Return a system-prompt section listing every card in the character's
    class pool. Empty string when character is unknown or pool is empty.

    Format (one line per card, pipe-delimited):
        Name | Cost | Type | Rarity | Target | Description

    BBCode is stripped from descriptions. Newlines inside descriptions are
    flattened to spaces. Section is wrapped in a `## Class Pool Reference`
    header plus a hedge line.
    """
```

Structure of the rendered section:

```
## Class Pool Reference (Silent — 88 cards)

This is the FULL static class pool, not what the run actually saw. Use as
combo-space awareness only. Never claim a card was in this run unless the
trace evidence shows it.

Name | Cost | Type | Rarity | Target | Description
Abrasive | 3 | Power | Rare | Self | Gain 1 Dexterity. Gain 4 Thorns.
Accelerant | 1 | Power | Rare | Self | Poison is triggered 1 additional time.
...
```

**Source of truth.** Read from `data/knowledge/upstream/cards.json` (576 cards), filter by `color == normalize_character(character)` (e.g. "silent"), exclude `color == "colorless"`. Produce 88 lines for Silent / Regent / Defect / Necrobinder, 87 for Ironclad. Cache the rendered string in-process keyed by character — the JSON is patch-immutable, so one read per process is enough.

**Character coverage.** Auto-detect from `evidence.character` (Turn 1) or the `character` argument (Turn 2). When the character has no entries (unknown class), the section returns `""` and nothing is injected — this is a strict additive change that fails open.

**Token cost.** Silent is 6970 chars (~1742 tokens) measured against current cards.json. Other classes within ~10%. This sits inside the static system block; on Anthropic with `cache_control: ephemeral` (planned future migration) it caches once. On Gemini, the implicit cache covers the same prefix.

### 3.3 Turn 1 + Turn 2 prompt assembly

```
system = _BUILD_ANALYSIS_SYSTEM | _NOTE_UPDATER_SYSTEM
       + "\n\n"
       + render_class_pool_section(character)

user = combat_trace_text          # only when present (gated by floor_sum)
     + "\n\n"
     + per-turn prompt body as today
```

The Turn 1 `instruction_note` stays unchanged — its "trace appears at the top of this user message" wording stays accurate (the trace really is at the top of the single inlined block), and its "use as ground truth" sentence is the part that matters.

### 3.4 Bucket B (non-deck card notes)

Turn 2's system prompt grows a third write channel beyond the existing `updates` and `core_engine`:

```jsonc
{
  "updates":            [...],          // bucket A (deck cards in trace), unchanged
  "non_deck_updates":   [...],          // bucket B (this section), new
  "core_engine":        {...}           // act3 victory only, unchanged
}
```

Each `non_deck_updates` entry:

```jsonc
{
  "card_name":      "Catalyst",
  "new_note":       "<= 200 chars",
  "evidence_type":  "skipped" | "combo_inferred",
  "reason":         "<= 200 chars; for skipped, must reference the
                     decision floor; for combo_inferred, must name the
                     specific deck card or relic it combos with",
  "trace_citation": "<short quote — required for skipped; empty
                     string allowed for combo_inferred>"
}
```

**Per-run cap:** **3** entries. Excess proposals are dropped (logged at WARN with `[bucket_b_overflow]`). Choosing 3 is intentionally tighter than the 5-cap floated in chat — start strict, audit, loosen later.

**Validation rules** (`parse_note_updates` extension):

1. `card_name` must be in `class_pool` for the run's character. Reject if it is.
2. `card_name` must NOT be in the run's `final_deck`. Bucket B is non-deck only; deck cards are bucket A's job.
3. For `evidence_type == "skipped"`: `card_name` must appear in the `skipped_cards` list passed in by the caller, AND `trace_citation` must be non-empty.
4. For `evidence_type == "combo_inferred"`: `reason` must contain at least one card-name or relic-name token from the run's `final_deck` ∪ `final_relics`. This is a cheap substring check, not deep parsing — sufficient to filter out vacuous combo claims.
5. Standard length checks: `new_note` ≤ 200 chars, `reason` ≤ 200 chars.

**Persistence.** Each surviving entry is written via `CardMemory.with_new_note` exactly like bucket A, using `note = new_note` and `reason = f"[{evidence_type}] {reason}"`. The leading `[skipped]` / `[combo_inferred]` token is the audit hook — `scripts/audit_card_notes.py` can grep for it to compute bucket-B note share, drift, and quality.

**Telemetry.** `Turn2Result` gains two fields:

```python
non_deck_written: int = 0
non_deck_dropped: int = 0      # validation failures + overflow
```

Logged at INFO alongside the existing `notes_written` / `core_engine_applied` line.

### 3.5 Skipped-card extraction

New function in `src/memory/combat_trace_renderer.py` (same module as `extract_candidate_cards`, since the data sources are siblings):

```python
def extract_skipped_cards(run_log_events: list[dict]) -> list[str]:
    """Return cards that were offered at card_reward / shop but not picked
    in this run. Reads card_reward and shop decisions from the run JSONL.
    Returns deduplicated list, order preserved by first appearance.

    For each card_reward event:
      - Pull the option list from event['decision']['options'] / similar.
      - Identify the picked option by matching event['decision']['picked']
        (or the alternative-index path).
      - Add every non-picked card name to the result.

    For each shop event: similar — every offered card not bought is skipped.
    """
```

This is wired into `_analyze_build_async` (`src/agent/loop.py:4324-4336`) as a sibling call to `extract_candidate_cards`:

```python
self._pending_trace_candidates = extract_candidate_cards(recent_combats)
self._pending_skipped_cards    = extract_skipped_cards(run_log_events)
```

Both lists are stored on the loop instance (initialized in `__init__`, cleared in the same places `_pending_trace_candidates` is cleared) and passed to `update_card_notes_from_traces` as a new `skipped_cards: list[str]` parameter.

**Failure mode.** If JSONL parsing fails or the schema is unfamiliar, `extract_skipped_cards` returns `[]`. Bucket B with `evidence_type="skipped"` then produces zero entries (validation rejects them all for missing skipped-list membership), which is the correct degraded behavior — `combo_inferred` continues to work.

## 4. Data flow

```
postrun stage 1 (memory):
  ├── _post_run_hcm_extraction  (no change)
  │     └── pending_trace_candidates = extract_candidate_cards(recent_combats)
  │     └── pending_skipped_cards    = extract_skipped_cards(run_log_events)   ◀── NEW
  │
  └── _analyze_build_async
        ├── Turn 1: analyze_build_with_llm
        │     - system   = _BUILD_ANALYSIS_SYSTEM + class_pool_section(char)   ◀── NEW
        │     - user     = trace + instruction_note + evidence_block            ◀── inlined (was 2-block)
        │
        └── Turn 2: update_card_notes_from_traces
              - system   = _NOTE_UPDATER_SYSTEM + class_pool_section(char)     ◀── NEW
              - user     = trace + candidate_table + bucket_b_block            ◀── inlined; bucket_b_block NEW
              - parse    = bucket_a (updates) + bucket_b (non_deck_updates)     ◀── parser extended
                         + core_engine (act3 only, unchanged)
```

## 5. Prompt changes

### 5.1 `_BUILD_ANALYSIS_SYSTEM` (Turn 1)

Append after the existing system text:

```
{class_pool_section}    # rendered string, may be empty
```

No instructions added — the pool's role ("counterfactual context for weak_points and damage_engine reasoning") is already implied by the section's hedge line. Minimal-surface change.

### 5.2 `_NOTE_UPDATER_SYSTEM` (Turn 2)

Two additions:

1. Append `{class_pool_section}` (same as Turn 1).
2. Add a paragraph describing bucket B output, the cap, and `evidence_type` semantics:

```
Additionally, you MAY emit up to 3 entries in `non_deck_updates` for cards
that are NOT in the run's deck but where the trace or class-pool context
justifies a forward-looking note:

  - evidence_type "skipped": the run was offered this card at card_reward
    or shop and rejected it. trace_citation MUST quote the rejection.
  - evidence_type "combo_inferred": this card is in the class pool and has
    a concrete combo with a card or relic the run actually used. `reason`
    MUST name that deck card or relic.

Cap: 3 entries total. Be stingy. Prefer "skipped" when both apply.
```

### 5.3 `_UPDATER_PROMPT_TEMPLATE` (user-side)

A new section at the bottom listing the cards Turn 2 is allowed to label as `skipped`:

```
## Cards offered but not picked this run (eligible for evidence_type="skipped")

- Catalyst (offered at card_reward floor 9)
- Footwork (offered at shop floor 14)
...
```

When `skipped_cards` is empty, the section emits a single `(none)` line — the LLM still sees that bucket B exists but knows the `skipped` channel is unavailable for this run.

## 6. Testing

**Unit (new):**

- `test_render_class_pool_section_silent_88_lines` — load real cards.json, assert 88 lines for `silent`, no Colorless.
- `test_render_class_pool_section_unknown_character_returns_empty` — pass `"banana"`, expect `""`.
- `test_render_class_pool_section_strips_bbcode` — Catalyst's description loses `[gold]...[/gold]`.
- `test_extract_skipped_cards_pulls_card_reward_offers` — fixture JSONL with one card_reward event (3 options, 1 picked) → 2 skipped cards.
- `test_extract_skipped_cards_handles_shop_events` — shop fixture.
- `test_extract_skipped_cards_returns_empty_on_malformed_event` — robustness gate.
- `test_parse_note_updates_accepts_bucket_b_payload` — well-formed `non_deck_updates` entry passes.
- `test_parse_note_updates_rejects_bucket_b_card_in_deck` — bucket B rule 2.
- `test_parse_note_updates_rejects_bucket_b_skipped_without_membership` — bucket B rule 3.
- `test_parse_note_updates_rejects_bucket_b_combo_without_deck_token` — bucket B rule 4.
- `test_parse_note_updates_caps_bucket_b_at_three` — 5 entries → 3 written, 2 dropped.

**Unit (rewritten):**

- `test_analyze_build_with_llm_inlines_combat_trace_into_prompt` (replaces `_accepts_combat_trace_text`).
- `test_analyze_build_with_llm_no_trace_omits_trace_block` (replaces `_no_trace_preserves_old_call_shape`).

**Unit (deleted):**

- `tests/test_llm_caller_cache.py` (entire file).

**Integration:**

- `test_turn2_full_pipeline_with_bucket_b_skipped` — hand-built trace + skipped list + LLM mock returning one bucket-B entry → assert it lands in `CardMemoryStore` with `[skipped]` reason prefix.
- `test_turn2_writes_zero_bucket_b_when_skipped_list_empty_and_combo_off` — degraded path.

**Live smoke:** one Silent run with `STS2_POSTRUN_ENABLED=true --no-skills --no-evolution`, verify:
1. Turn 1 + Turn 2 logs each show ~1.7K extra system tokens.
2. `data/reports/card_notes_2026-05-XX.txt` shows at least one bucket-B entry tagged `[skipped]` or `[combo_inferred]`.
3. Postrun JSONL has no `<<<CACHED_PREFIX>>>` markers (telemetry codepath gone).

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| LLM hallucinates `combo_inferred` notes citing cards not in deck | Validation rule 4 (deck-token substring check) catches the most common shape. Audit via `[combo_inferred]` reason prefix in `scripts/audit_card_notes.py`. |
| `skipped_cards` extractor schema-drifts when the JSONL log format changes | Returns `[]` on any parse failure; bucket B with `evidence_type="skipped"` degrades to empty, which is fail-safe. |
| Pool injection inflates token cost on Gemini (no implicit cache hit) | Single character pool ≈ 1.7K tokens. Two postrun calls per run → ~3.4K extra input tokens / run, charged at Gemini analysis-tier rates. Acceptable. Mitigated entirely once the family flips back to Anthropic + ephemeral cache. |
| Bucket B notes overwrite valuable bucket A notes via `with_new_note` history rotation (3-version cap) | Bucket B is hard-capped at 3 writes per run; bucket A is unbounded. In a worst case both buckets target the same card, but bucket B forbids deck cards (rule 2), so they never collide. |
| Non-Silent characters get a wrong-class pool injected | `render_class_pool_section` filters by `color == normalize_character(character)`; `evidence.character` is already normalized upstream. Unit-tested. |

## 8. Migration notes

- No `CardMemory` schema migration. The `[skipped]` / `[combo_inferred]` prefix is conventional, parsed only by audit scripts.
- No data-store migration. Existing notes remain; new ones land alongside via the standard `with_new_note` rotation.
- `STS2_POSTRUN_ENABLED` continues to gate the entire flow. No new config flag — bucket B is unconditionally on when Turn 2 runs. Rationale: a flag would only delay the audit signal; we want bucket B's evidence the moment we ship it.

## 9. Decision log

| Decision | Chosen | Considered alternative |
| --- | --- | --- |
| Cache hack | Delete entirely | Keep as a no-op for future Anthropic migration. Rejected: dead code is worse than re-adding when needed. |
| Pool injection scope | Turn 1 + Turn 2 system prompt | User message tail. Rejected: system is the right home for static, patch-immutable reference data; future cache hits depend on it. |
| Bucket B cap | 3 | 5 (mid-discussion default). Tightened to start strict; loosen after audit. |
| Skipped-card data source | `logs/run_*.jsonl` via new extractor | Track in STM directly. Rejected: trace renderer already consumes the same log; one source is simpler. |
| `evidence_type` channel | `reason` text prefix `[skipped]` / `[combo_inferred]` | New typed field on `CardMemory`. Rejected: avoids a store-format migration. |
| Character coverage | Auto-detect from `evidence.character` | Silent-only V1. Rejected: same code, broader coverage. |
| Upgraded card stats | Excluded V1 | Included. Rejected: ~30% token bloat for marginal value at Turn 1/2 (no upgrade decisions happen here). |
| Colorless cards | Excluded | Included. Rejected: doubles the static block; not the design's primary win. |
