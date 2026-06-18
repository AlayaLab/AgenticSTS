# Seed Stub Self-Evolution Design

**Date:** 2026-05-03
**Status:** Draft
**Scope:** Implements Mode B of the 4-condition ablation matrix for the EMNLP paper.

## 1. Background and Goals

The EMNLP paper compares 4 conditions to characterize self-evolving agents:

| Condition | L1/L2 prompts | Seed skills | STM | L4/L5 cross-run | Postrun |
|-----------|---------------|-------------|-----|-----------------|---------|
| baseline | slim (mechanics only) | ✗ | ✗ | ✗ | ✗ |
| Mode A | full | expert (existing 8) | ✗ | ✗ | ✗ |
| **Mode B** | **full** | **agent-written stubs (new 5)** | **✓** | **✓ agent writes** | **✓** |
| full | full | expert | ✓ | ✓ agent writes | ✓ |

This spec covers Mode B's seed stub mechanism. Mode B tests whether the agent
can self-evolve seed-skill-equivalent content from gameplay alone, given only
a topic scaffold (no expert content leakage).

### Goals
- Agent writes character-specific strategy skills via postrun, refining them across runs.
- Generalizable framework: character is a runtime parameter, not hard-coded.
- Clean comparison: 5 agent-written stubs vs the existing 8 expert seeds at the package level.

### Non-Goals
- Refactor existing 8 expert seeds. Mode A keeps using them as-is.
- Replace mistake-driven discovery (different layer: per-mistake fine-grained patches).
- Replace guide consolidator (different layer: per-enemy / per-act / per-archetype specifics).

### Methodological Constraint
The fill-prompt MUST NOT include the full text of expert seed skills. Otherwise
Mode B is just paraphrasing experts, not self-evolving. Topic-level hints
(category names like "energy allocation") are acceptable; specific tactics
(named card sequences, numerical thresholds) are not.

## 2. Layer Separation

| Layer | Granularity | Source | Examples |
|-------|-------------|--------|----------|
| **Skill (this spec)** | Generalized principles | Mode A: expert; Mode B: agent | "Use ALL energy each turn" |
| Guide | Per-enemy / per-act / per-archetype | guide_consolidator (LLM) | "vs Lagavulin, save Defend for R4 wake" |
| Memory | Per-card / per-event statistics | card_memory_extractor (deterministic) | "Strike played 200 times, dealt 1200 damage avg" |
| Mistake skill | Per-mistake patches | mistake_discovery (LLM) | "Don't lead with Strike vs multi-enemy with attack intent" |

Skills are the most general layer. Stubs in Mode B target this layer
exclusively; guides, memory, and mistake skills evolve through their existing
pipelines.

## 3. Stub Taxonomy

5 stubs per character, anchored to state_type clusters:

| Stub | Trigger state_types | Topic |
|------|--------------------|----|
| `stub_{character_id}_combat` | monster, elite, hand_select | Non-boss combat: HP-conservative, focus fire, block-first |
| `stub_{character_id}_boss` | boss | Boss-specific: HP-aggressive, must-kill, scaling commitment |
| `stub_{character_id}_deckbuilding` | card_reward, card_select, shop, treasure, relic_select | Card and deck evaluation framework |
| `stub_{character_id}_map` | map | Forward path-selection strategy |
| `stub_{character_id}_intermission` | rest_site, event | Trade-off evaluation at non-combat nodes |

### Why this taxonomy
- state_type clusters are natural decision boundaries; each LLM decision triggers exactly 1 stub.
- Boss split from combat is mandatory: combat says "minimize HP loss," boss says
  "HP fully restores between acts, must kill — defense alone loses." Mixing
  the two confuses the agent.
- Map is separate from rest+event because map = forward planning, rest+event = at-node trade-off.
- 5 stubs is the minimum that respects these distinctions.

## 4. Stub Schema and Character Parameterization

Templates live in `src/skills/seeds_stubs/`, one per stub:

- `combat.template.json`
- `boss.template.json`
- `deckbuilding.template.json`
- `map.template.json`
- `intermission.template.json`

At Mode B startup, the SkillLibrary instantiates a stub per (template × active
character). For Silent-only experiment: 5 stubs total. For multi-character
extension: 5 × N stubs, automatic.

### Template structure

```json
{
  "skill_id_template": "stub_{character_id}_combat",
  "name_template": "{character_name} - Combat Principles",
  "category": "combat",
  "tier": "general",
  "trigger": {
    "state_types": ["monster", "elite", "hand_select"],
    "character": ["{character}"]
  },
  "source": "stub",
  "status": "pending_fill",
  "scaffold": {
    "topic": "Strategic approach to non-boss combat for this character",
    "scope": "Generalizable principles applying to MOST hallway and elite encounters, regardless of the specific enemy.",
    "dimensions_to_consider": [
      "How to allocate energy each turn (offense / defense / setup)",
      "How to read enemy intents and react to multi-enemy boards",
      "HP loss MINIMIZATION across the run — every point lost is a point the boss might end you with. What lines reliably hit 0 damage taken? When is taking 1-3 damage acceptable?",
      "Card sequencing within a turn (which card types resolve first)",
      "When to spend potions in non-boss combat",
      "How character-specific tempo levers work (free plays, discard, etc.)"
    ],
    "out_of_scope": [
      "Per-enemy mechanics (round triggers, threshold patterns) → belongs in combat_guides",
      "Per-card play recipes or specific combos → belongs in card_memory notes",
      "Specific numerical thresholds tied to one situation"
    ],
    "format_constraints": {
      "token_budget": "400-700 tokens",
      "structure": "5-8 numbered principles. Each = one imperative declarative sentence + one short concrete example demonstrating application.",
      "voice": "Imperative, second-person, not descriptive."
    },
    "leakage_guard": {
      "max_distinct_card_names": 8,
      "max_distinct_enemy_names": 3,
      "no_specific_damage_thresholds": true
    }
  },
  "content": "TBD — filled by Mode B postrun",
  "version": 0,
  "confidence": 0.5
}
```

### Character substitution

At runtime:
- `{character}` → raw trigger value, e.g. "the silent"
- `{character_id}` → lowercase + space-replaced, e.g. "the_silent"
- `{character_name}` → title case, e.g. "The Silent"

### Per-stub `dimensions_to_consider` (Silent example)

| Stub | dimensions_to_consider |
|------|----------------------|
| combat | energy allocation / intent reading / **HP loss minimization (anchor)** / card sequencing / potion use / character-specific tempo levers |
| boss | **must kill, defense alone loses (anchor)** / HP-potion philosophy inversion / front-loaded vs scaling / when to commit Powers / recognizing under-damaged decks |
| deckbuilding | card value dimensions / archetype commitment vs flexibility / removal priority / shop budget / when to skip |
| map | node priority hierarchy / HP-buffer-driven path adjustment / boss-distance routing / shop and rest pacing |
| intermission | rest investment trade-offs (smith vs heal vs other) / event trade-off framing / which deck gaps to fill at non-combat nodes |

The two "anchor" dimensions in combat / boss are deliberate — they enforce the
HP-philosophy inversion the agent must learn.

## 5. Lifecycle State Machine

```
[创建]  status="pending_fill", content="TBD", source="stub"
   |
   |  Mode B postrun triggers (run_count >= 1 for this character)
   v
[首填]  fill prompt → LLM → parse → validators warn → write
       status="active", source="stub_filled", confidence from LLM, version=1
   |
   |  every postrun (active state)
   v
[更新]  update prompt (current content as reference + new evidence) → LLM
       → parse → warn → overwrite, version+=1
```

### Library retrieval changes

[`SkillLibrary.query()`](../../src/skills/library.py) skips skills with
`status == "pending_fill"`. Stubs in pending state stay in `_skills` (so fill
can update the same entry) but are not eligible for retrieval — no "TBD"
placeholder text reaches LLM prompts.

```python
# src/skills/library.py: query()
if skill.status == "pending_fill":
    continue  # not yet filled, don't inject
```

Once a stub is filled (`status="active"`), it behaves like any other skill in
retrieval: filtered by trigger, scored by relevance × priority, subject to
slot quotas.

## 6. Fill Prompt Design

The fill prompt has 4 parts. Same skeleton for all 5 stubs; Part B's evidence
shape differs by state_type cluster.

### Part A — Role + Constraints (system prompt)

```
You are a strategy-skill author for an autonomous Slay the Spire 2 agent.
Your job is to write a GENERALIZED skill describing this character's
strategic principles for {state_type_cluster}.

A "skill" is the most general layer of agent knowledge:
- It describes principles applying to MOST decisions, not specific situations.
- Per-enemy mechanics belong in combat_guides (already exist).
- Per-card stats belong in card_memory (already exist).
- Per-mistake patches belong in fine-grained skills (already exist).
Your skill complements but DOES NOT duplicate these layers.

Topic: {scaffold.topic}
Scope: {scaffold.scope}
Out of scope: {scaffold.out_of_scope}
Token budget: {scaffold.format_constraints.token_budget}
```

### Part B — Evidence: 1-3 full-fidelity snapshots from selected runs

Selection: current run + most recent win + most recent loss (1-3 runs depending on history).

#### Combat / Boss stubs
For each selected run, sample combats and inject full `format_combat_replay`
output (relics, deck, hand-by-hand, intent, agent plan, cards played with
damage/block/enemy_deltas, power timeline, outcome).

Sampling strategy:
- **Combat stub**: up to 2 combats per run, prefer 1 hallway + 1 elite if both
  reached; else use what's available (early-aborted runs may have fewer).
- **Boss stub**: include all boss combats per run (typically 0-3 depending on
  how far the run progressed). If no boss combats in any selected run, the
  stub keeps `pending_fill` for that postrun.

Total replays per fill: 0-6 across 1-3 runs. Tokens: ~2-3K per replay × up to
6 = up to 18K per stub. Acceptable since postrun token cost is not the
bottleneck.

#### Deckbuilding / Map / Intermission stubs (思路 3 trajectory)

For each selected run, render a full per-state-type-cluster trajectory:

```
## Deckbuilding Trajectory N (run_id=..., {character} A{ascension}, OUTCOME={outcome})
Final deck (size N): {sorted card names}
Final relics: {names}
Build archetype emerged: {label or "unclassified"}

[F{floor} {state_type}] HP {hp}/{max_hp}, Gold {gold}, Deck size {n}
  Options: {0=..., 1=..., 2=...}
  Chose: {index} ({option name})
  Reasoning: "{LLM reasoning at decision time}"
  Strategic note: "{strategic_note at decision time}"
  Outcome delta: {hp/gold/deck before -> after}

... (10-15 decisions) ...

## Attribution Summary (deterministic, from card_memory + run_history)
- Most-played cards: {name (plays, dmg/block totals)}
- Cards never used: {names}
- Death cause: {floor enemy mechanic}
- Strategic Thread evolution: F{N}: "{note}", F{M}: "{note}", ...
```

Tokens: ~7-12K per stub for deckbuilding/map/intermission.

The Attribution Summary is purely deterministic (counts from card_memory,
death cause from run_history, thread from STM dump). No additional LLM call.

### Part C — Dimensions hint

```
Cover these dimensions if your data supports them; skip if data is too thin:
{scaffold.dimensions_to_consider}
```

### Part D — Output schema + format rules

```
Output JSON:
{
  "principles": [
    {"text": "<imperative principle>", "example": "<concrete example>"},
    ...
  ],
  "confidence": 0.5-0.9,
  "dimensions_covered": ["energy_allocation", "intent_reading", ...],
  "evidence_basis": "<1-sentence justification citing run-history patterns>"
}

Constraints:
- {format_constraints.structure}
- {format_constraints.voice}
- max_distinct_card_names: {leakage_guard.max_distinct_card_names}
- max_distinct_enemy_names: {leakage_guard.max_distinct_enemy_names}
- DO NOT include specific HP thresholds or damage numbers
- DO NOT name cards/enemies that don't appear in your evidence
```

### Update mode (status was already "active")

Same 4 parts plus a leading section:

```
## Existing Content (v{version})
{current content}

Refine this content based on new run data. If new evidence contradicts
existing principles, REPLACE rather than append. Avoid accreting low-
confidence rules from each run. Early-run content is expected to be coarse;
rewrite freely as evidence accumulates.
```

## 7. Run Selection

```python
def select_runs_for_fill(character: str, history: list[RunRecord]) -> list[RunRecord]:
    """Pick current + most recent win + most recent loss. Returns 1-3 runs."""
    current = history[0]  # just-completed run
    
    recent_win = next(
        (r for r in history[1:] if r.outcome == "victory" and r.run_id != current.run_id),
        None
    )
    recent_loss = next(
        (r for r in history[1:] if r.outcome in ("defeat", "max_steps") and r.run_id != current.run_id),
        None
    )
    
    selected = [current]
    if recent_win: selected.append(recent_win)
    if recent_loss: selected.append(recent_loss)
    return selected
```

Startup runs (1-2 total runs of history): selection returns 1-2 runs.
Acceptable since experiment scale is 10-20 runs.

## 8. Triggering Logic

Mode B postrun pipeline order (extends existing pipeline):

```
1. memory extract (combat episodes, deck builds, card memory)
2. distill rules (every 5 runs)
3. guide consolidation
4. mistake-driven combat skill discovery
5. fill_seed_stubs ← NEW (Mode B only)
6. self-evolution
```

Stage 5 fires after stage 4 (so fill prompt can reference newly-written
mistake skills as "don't duplicate this layer"), before stage 6 (so
self-evolution can't accidentally write to stub IDs).

Trigger condition (per stub, per postrun):
- If `STS2_SEED_STUB_FILL_ENABLED=true` AND character has ≥1 completed run.
- No `min_runs_before_fill` threshold beyond that. Run 1 fills with
  rough content; updates each subsequent run refine it.

Implementation: new helper `_post_run_fill_stubs()` in
[`src/agent/loop.py`](../../src/agent/loop.py), called from `_safe_post_run`.

## 9. Validators (warn-only, no reject)

After fill produces content, run validators. All emit warnings; none block
the write. Warnings accumulate in `stub._metadata.warnings` for later review.

| Validator | Threshold | Warning if |
|-----------|-----------|-----------|
| token_count | scaffold.format_constraints.token_budget (e.g. 400-700) | actual outside range |
| principle_count | 5-8 | count outside range |
| card_name_density | scaffold.leakage_guard.max_distinct_card_names (8) | exceeded |
| enemy_name_density | scaffold.leakage_guard.max_distinct_enemy_names (3) | exceeded |
| specific_damage_thresholds | regex `\b\d+\s+(damage\|HP\|hp\|block)\b` | matches found |
| imperative_voice | heuristic on principle.text first word | >2/N principles non-imperative |
| confidence_sanity | 0.3 ≤ confidence ≤ 0.95 | outside range |

Card and enemy name extraction uses the existing
[`GameKnowledge`](../../src/knowledge/knowledge.py) lookups for substring
matching.

## 10. Isolation from Other Write Stages

Four layers prevent mistake_discovery / self-evolution from corrupting stubs:

### Layer 1 — Namespace prefix
All stub IDs use `stub_*` prefix. Stub source transitions atomically with
status: `(source="stub", status="pending_fill")` → `(source="stub_filled",
status="active")` on successful first fill, then stays at `stub_filled` /
`active` through subsequent updates. mistake_discovery uses source
`evolved`; self-evolution uses source `agent`. These four source labels
(`seed`, `stub`/`stub_filled`, `evolved`, `agent`) are mutually exclusive.

### Layer 2 — write_gate guards

[`src/skills/write_gate.py`](../../src/skills/write_gate.py):

```python
def persist(self, skill, action, target_id=None):
    if action in ("update", "merge"):
        target = self._library.get(target_id) if target_id else None
        if target and target.source in ("stub", "stub_filled"):
            return WriteGateResult(
                accepted=False,
                reason=f"target_id={target_id} is a seed stub managed by Mode B fill pipeline.",
            )
    if action == "add" and skill.skill_id.startswith("stub_"):
        return WriteGateResult(
            accepted=False,
            reason="skill_id with 'stub_' prefix is reserved for the seed stub pipeline.",
        )
    # ... existing logic
```

### Layer 3 — Library write lock during stage 5
`fill_seed_stubs` acquires the existing `SkillLibrary._lock` for its duration.
Stage 6 (self-evolution) starts after stage 5 releases the lock. Sequential
execution makes this redundant in practice but guards against future
parallelism.

### Layer 4 — fill bypasses write_gate
Stub fill calls `library.put(updated_stub)` directly, not via write_gate.
The dual-anchor A/B validation that write_gate enforces is for fine-grained
skills with high false-positive risk; stubs are coarse-grained and warn-only.

Audit logged to `evolution/stub_fill_log.jsonl` (separate file from
`evolution/evolution_log.jsonl`):

```jsonl
{"run_id": "...", "stub_id": "stub_the_silent_combat", "action": "first_fill"|"update", "version_before": 0, "version_after": 1, "warnings": [...], "input_tokens": ..., "output_tokens": ..., "timestamp": ...}
```

## 11. Configuration Matrix

Env vars:

| Var | Default | Purpose |
|-----|---------|---------|
| `STS2_SEED_STUB_FILL_ENABLED` | false | Enables stage 5 (fill_seed_stubs) |
| `STS2_USE_SEED_STUBS` | false | Loads templates from `seeds_stubs/` |
| `STS2_DISABLE_SKILL_SEEDS` | false | Skips loading expert `seeds/` |
| `STS2_PROMPT_VARIANT` | full | full or baseline (existing) |
| `STS2_MEMORY_ENABLED` | true | Existing flag |
| `STS2_POSTRUN_ENABLED` | true | Existing flag |
| `STS2_STM_ENABLED` (new) | true | Disables Strategic Thread injection when false |

4-condition table:

| Condition | PROMPT_VARIANT | DISABLE_SKILL_SEEDS | USE_SEED_STUBS | SEED_STUB_FILL_ENABLED | MEMORY_ENABLED | STM_ENABLED | POSTRUN_ENABLED |
|-----------|----------------|---------------------|----------------|------------------------|----------------|-------------|------------------|
| baseline | baseline | true | false | false | false | false | false |
| Mode A | full | false | false | false | false | false | false |
| Mode B | full | true | true | true | true | true | true |
| full | full | false | false | false | true | true | true |

## 12. Implementation Plan

### New files
- `src/skills/seeds_stubs/combat.template.json`
- `src/skills/seeds_stubs/boss.template.json`
- `src/skills/seeds_stubs/deckbuilding.template.json`
- `src/skills/seeds_stubs/map.template.json`
- `src/skills/seeds_stubs/intermission.template.json`
- `src/skills/stub_filler.py` — fill orchestration: select runs, build evidence, render prompt, parse, validate, persist
- `src/skills/stub_validators.py` — 7 warn-only validators
- `src/skills/stub_evidence.py` — combat replay sampling, deckbuilding/map/intermission trajectory rendering, Attribution Summary
- `src/skills/stub_template.py` — character substitution for templates

### Modified files
- `src/skills/library.py` — `load_seed_stubs()`, query() skip pending_fill
- `src/skills/write_gate.py` — Layer 2 guards
- `src/agent/loop.py` — `_post_run_fill_stubs()`, wired into `_safe_post_run`
- `config.py` — new env vars
- `scripts/run_ablation.py` — reconcile existing condition names
  (`baseline-strict`, `prompt-only`, `self-evolve`, `full`) with this spec's
  4-condition matrix (`baseline`, `Mode A`, `Mode B`, `full`). Likely renames
  `baseline-strict` → `baseline`, drops or repurposes `prompt-only`, splits
  `self-evolve` → `Mode A` (no postrun) + `Mode B` (postrun + stubs)

### Test plan
- Unit tests:
  - Template instantiation with character substitution
  - Library retrieval skips pending_fill stubs
  - write_gate rejects stub manipulation from other stages
  - Each validator emits expected warnings on synthetic input
- Integration tests:
  - Single-run smoke: stubs go from pending_fill to active with rough content
  - 5-run pilot: stub content stabilizes across updates, warnings stay bounded

### Implementation order
1. Templates + character substitution (fast, isolated)
2. library.py changes + retrieval skip (small surgical change)
3. write_gate guards (isolation, must land before stub fill goes live)
4. Stub evidence rendering (read existing renderers, add deckbuilding/map/intermission trajectory)
5. Validators (mostly regex/heuristic, fast)
6. stub_filler orchestration + LLM call (uses existing evolution backend pattern)
7. loop.py wiring (postrun stage 5)
8. config.py env vars + run_ablation.py condition update
9. Tests (unit then integration)

## 13. Out of Scope (deferred for future work)

- LLM-generated post-mortem attribution (deferred; user will review actual fill outputs first and add only if needed)
- Heuristic enrichment beyond Attribution Summary
- Refactoring the existing 8 expert seeds into a 5-stub taxonomy (Mode A keeps current shape)
- Multi-character stub instantiation logic for any character beyond Silent (templates support it; not exercised until needed)
- Build-archetype-aware run selection (current selection is outcome-based: current + recent_win + recent_loss)
