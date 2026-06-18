# Self-evolution

Reference for the postrun pipeline that updates L4 memory and L5 skills. For module locations see [`ARCHITECTURE.md`](ARCHITECTURE.md). For dated rollout entries see [`CHANGELOG.md`](CHANGELOG.md).

## Postrun stage order

In `src/agent/loop.py::_safe_post_run` (gated by `config.postrun_effectively_enabled()`):

1. **Memory extract** + guide consolidation (cadence-gated, every N runs)
   - HCM domain stores: combat episodes, route memories, card builds, event memories, per-card statistics
   - Guides: `CombatGuide`, `RouteGuide`, `DeckGuide`, `EventGuide` consolidated by LLM
2. **Skill scoring + discovery**
   - `noncombat_scorer.run_noncombat_scoring` — non-combat skill confidence updates (cumulative boss-kill bonuses)
   - `mistake_discovery.run_mistake_discovery` — mistake-driven combat skill discovery
3. **Mode B stub fill** (`_post_run_fill_stubs`) — gated by `STS2_SEED_STUB_FILL_ENABLED` (default off)
4. **Self-evolution** (`EvolutionEngine`) — gated by `STS2_EVOLUTION_ENABLED`

Removed: rule distillation (2026-04-23, with `rule_store.py` / `rule_distiller.py` / `prompts/distill.py`); non-combat skill discovery (2026-04-23).

## Mistake-driven combat skill discovery

`src/skills/mistake_discovery.py` (sole skill-producing path as of 2026-04-23). Pipeline:

1. **Mistake detection.** Per-combat `loss_ratio` (HP lost / max HP) compared against:
   - Baseline A: enemy-median across all character runs vs the same enemy
   - Baseline B: act × combat_type × character mean
   - Both exceed thresholds → episode flagged as mistake
2. **LLM critic** (`src/skills/critic_prompt.py`) reads the round-by-round trace of the mistake combat. Produces one of:
   - `candidate(skill_id, name, content, trigger, mistake_round_indices)` — propose a new skill
   - `no_skill_needed` / `bad_luck` / `unavoidable_mechanic` / `descriptive_rhythm` — reject
3. **Candidate validator** enforces name/content/trigger format constraints.
4. **Pre-write A/B** (`src/skills/prewrite_ab.py`): for each mistake round, resample B=3 decisions with the candidate skill injected. Pass criteria: zero `skill_harmful` verdicts AND `sum(hits) >= ceil(total × 2/3)`.
5. **4-level write gate** (next section). Survivors enter with:
   - `confidence = 0.40 + 0.05 × len(mistake_round_indices)`
   - `status = "probation"`

Seed skills (`src/skills/seeds/core_*.json`, `silent_*`, `regent_*`) are exempt from `apply_retirement_policy` deactivation (floored at 0.40).

## Write gate (4-level cascade)

`src/memory/write_gate.py` (split into 5 modules: main + judge + lifecycle + ab + reap). Cascade levels:

1. **Exact ID** match → REJECT (never duplicate IDs)
2. **Cosine vs static index** (L1/L2/L3 prompts + game knowledge) — high overlap → REJECT (don't re-state what's already in prompts)
3. **Cosine + trigger Jaccard vs existing L4/L5 store** — overlap → `defer_to_judge` (let LLM decide)
4. **LLM batch judge** (`write_gate_judge.py`) — verdict ∈ `{ADD, UPDATE, MERGE, REJECT}`

`defer_to_judge` candidates accumulate on `WriteGate._pending_skills` until `flush_judge_round` is called. Lifecycle handled by `write_gate_lifecycle.py`.

## Reap + merge (verdict execution)

`src/memory/write_gate_reap.py::reap_judge_verdicts`:

- `ADD` — persist as new
- `UPDATE` — replace target (falls back to add on missing target)
- `REJECT` — drop
- `MERGE` — delegate to `src/skills/merge_pipeline.py::run_merge_pair`. LLM merge produces a candidate; **dual-anchor A/B validation** runs the merged skill against both source anchors and requires strict 2/3 + zero-harmful on **both sides**.

Gated by `STS2_WRITE_GATE_REAP_ENABLED` (default false; observation-mode persistence preserved when off). Audit trail: `evolution/reap_log.jsonl`. Wired through `AgentLoop._flush_write_gate_judge` (async).

## Mode B (seed stub self-evolution, 2026-05-04)

The EMNLP ablation's "self-evolve" condition: agent self-evolves seed-skill-equivalent content from gameplay alone, given only a topic scaffold (no expert content).

### 5-stub taxonomy

Anchored to `state_type` clusters. Each template at `src/skills/seeds_stubs/<topic>.template.json` is character-parametric (`{character}` / `{character_id}` / `{character_name}` substitution at instantiation).

| Stub | State types covered |
|------|---------------------|
| `combat` | monster, elite, hand_select |
| `boss` | boss combat |
| `deckbuilding` | card_reward, card_select, shop, treasure, relic_select |
| `map` | map (Scenario A + B) |
| `intermission` | rest_site, event |

### Lifecycle

```
(source="stub", status="pending_fill") at startup
  → first fill via postrun stage 5 (StubFiller)
  → (source="stub_filled", status="active", version=1)
  → subsequent runs refine same entry (version++, content updated in place)
```

`SkillLibrary.query()` skips entries with `status="pending_fill"` so no "TBD" placeholder ever reaches a prompt.

### 4-layer isolation

Mistake-driven discovery and self-evolution must not corrupt stubs:

1. **Namespace prefix** — stub IDs use `stub_*`. Source labels (`seed`, `stub` / `stub_filled`, `evolved`, `agent`) are mutually exclusive.
2. **write_gate guards** — `src/memory/write_gate.py` rejects any candidate skill whose name starts with `stub_` from the mistake-discovery / self-evolution paths, and strips `stub_*` neighbors from the dedup-existing list.
3. **Library write lock** — `SkillLibrary._lock` held during stage 5; stage 6 (self-evolution) only starts after release.
4. **Fill bypasses write_gate** — `StubFiller` calls `library.put(updated_stub)` directly. Quality control via `stub_validators.py` (7 warn-only checks), not dual-anchor A/B (which is for fine-grained mistake skills).

### End-to-end fill flow

Startup:
- With `STS2_USE_SEED_STUBS=true` and `STS2_DISABLE_SKILL_SEEDS=true`, expert seeds are skipped
- `_lazy_load_seed_stubs` instantiates the 5 templates with character substitution at first character-detection step

Postrun stage 5 (`_post_run_fill_stubs` → `StubFiller.afill_all_stubs`):

1. **Run selection** (`stub_filler.py` helpers) — pick the just-finished run + most-recent win + most-recent loss, scoped by `experiment_tag`
2. **Evidence gathering** (`stub_evidence.py`):
   - Combat / boss stubs: sample full combat replays
   - Deckbuilding / map / intermission stubs: render per-state-type trajectories + Attribution Summary
3. **Prompt assembly** (`stub_prompts.py`) — 4-part fill / update prompt structure
4. **LLM call** routed to analysis tier
5. **JSON parse** + 7 warn-only validators (`stub_validators.py`)
6. **Library write** — `library.put(updated_stub)`
7. **Audit log** — append to `evolution/stub_fill_log.jsonl`

5 stubs filled concurrently (`afill_all_stubs`) — ~5x speedup vs sequential.

### Empirical (as of 2026-05-07)

41 Mode B runs total across two experiments:
- `mode-b-smoke-2026-05-03`: 21 runs, 5 wins, max actual A5
- `mode-b-fixed-2026-05-04`: 20 runs, 6 wins, A6 attempted

Per-experiment skill stores isolated under `../AgenticSTS-Data/experiments/mode-b-*/`.

## Evolution engine

`src/brain/evolution_engine.py` + helpers (`evolution_handlers.py`, `evolution_validators.py`, `evolution_artifacts.py`). Postrun read+write tool-use loop:

- **Read tools** (5 static query): `recall_encounter`, etc.
- **Write tools** (5 in `write_tools.py`): `author_tool`, `write_skill`, `update_guide`, `update_card_note`, `get_performance_stats`
- **Dynamic tools** consumed via direct dispatch (NOT exposed to gameplay LLM)

Model: Gemini 3.1 Pro primary (analysis tier, high effort), GPT-5.4 Thinking fallback. Prompts treated as immutable — postrun never edits source-code prompts, only writes to L4 memory / L5 skills / dynamic tools.

## Dynamic tools

`src/brain/dynamic_tools.py` — `DynamicToolRegistry`:

- AST-sandboxed `.py` tool files at `evolution/tools/`
- Allowlist: `math`, `collections`, `itertools`, `functools`. Blocks dunder access + forbidden names.
- 6-stage registry validation + Stage 1 binding dry-run against real GameState snapshots + Stage 2 LLM quality judge
- Consumed via:
  - `ToolPreprocessor` — pre-LLM hints injected as `## Computed Insights`
  - `PlanVerifier` — post-plan checks; severity `"critical"` → `needs_replan=True`
  - `EvolutionEngine` — direct dispatch postrun
- **NOT exposed to gameplay LLM** — gameplay tool API is fixed at 6 (5 static query + 1 decision)

## PE deprecation (2026-04-18, negative result)

Prompt evolution removed after empirical finding: **33/33 postrun-proposed prompt patches failed A/B validation** over a 10-day run span (primarily INVALID_B decision-schema violations).

Conclusion: postrun LLM critiques applied to authoring-layer prompt edits produce fragile modifications the validation gate correctly but exhaustively rejects.

Architecture simplified:
- L1 system / L2 state prompts: human-authored + immutable to postrun (only changed via human PR or `scripts/apply_patch.py` for game-version patches)
- L4 memory / L5 skills / dynamic tools: only postrun-writable layers

See `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md` for full analysis.

## Skill replay evaluation

`src/skills/replay_evaluator.py` — boss replay save/quit/continue cycle for A/B testing skill effects. Currently disabled by default (`STS2_SKILL_EVAL=false`):

- Code fixes (2026-04-18): `_eval_current_index=-1` sentinel makes `[0]` slot testable; single-entry schedules compare baseline vs alt; save/quit reload re-seeds `CombatConversation._strategic_notes` and passes `strategic_thread=` from STM
- **Pending**: live boss fight with `STS2_SKILL_EVAL=true` to confirm A/B signal is distinguishable, then flip default on

## Key config gates

| Env var | Default | What it does |
|---------|---------|--------------|
| `STS2_POSTRUN_ENABLED` | true | Master postrun switch |
| `STS2_EVOLUTION_ENABLED` | true | Stage 4 (self-evolution) |
| `STS2_WRITE_GATE_REAP_ENABLED` | false | Apply ADD/UPDATE/MERGE/REJECT verdicts (else observation-only) |
| `STS2_SEED_STUB_FILL_ENABLED` | false | Mode B postrun stage 5 |
| `STS2_USE_SEED_STUBS` | false | Load `seeds_stubs/*.template.json` instead of expert seeds |
| `STS2_DISABLE_SKILL_SEEDS` | false | Skip expert seeds (`seeds/*.json`) |
| `STS2_SKILL_EVAL` | false | Boss replay skill evaluation |
| `STS2_STM_ENABLED` | true | Short-term memory + Strategic Thread |
| `STS2_COMBAT_CONVERSATION_ENABLED` | true | Persistent CombatConversation per fight (else fresh per-round) |
