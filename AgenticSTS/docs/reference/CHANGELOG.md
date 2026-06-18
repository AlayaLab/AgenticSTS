# Changelog

Dated progress entries, newest first. Reference doc for architectural changes — for per-task design rationale see `docs/superpowers/specs/<date>-<topic>-design.md`.

## 2026-05-06

- Combat: discarding ethereal Status / Curse cards is now blocked at the planner — they exhaust at end-of-turn anyway, but Voodoo-style discard slots were being wasted on them (commit `0358560`).
- Postrun: termination centralized in `_safe_post_run` so stub fill, evolution, and judge cleanup all run under one watchdog; watchdog extended 6h → 12h to accommodate Mode B's 5 concurrent LLM calls + analysis tier (commit `dd5e9e6`).

## 2026-05-04 — Mode B seed stub self-evolution

- Mode B added for the EMNLP ablation (replaces the old `self-evolve` condition's free-form skill output): the agent self-evolves seed-skill-equivalent content from gameplay alone, given only a topic scaffold (5 stub templates per character: combat / boss / deckbuilding / map / intermission). Spec + plan: `docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md`, `docs/superpowers/plans/2026-05-03-seed-stub-self-evolution.md`. See [`SELF_EVOLUTION.md`](SELF_EVOLUTION.md) for full details.
- Lifecycle: `(source="stub", status="pending_fill")` at startup → first fill via postrun stage 5 → `(source="stub_filled", status="active", version=1)` → subsequent runs refine the same entry. `SkillLibrary.query()` skips `pending_fill` so no "TBD" placeholder reaches a prompt.
- 4 layers of isolation prevent mistake-discovery / self-evolution from corrupting stubs: (1) `stub_*` namespace prefix; (2) `write_gate` guards in `src/memory/write_gate.py` rejecting both creation and update of `stub_*` IDs from other stages; (3) `SkillLibrary._lock` held for stage 5 duration; (4) fill bypasses write_gate (calls `library.put` directly with coarse-grained warn-only validators).
- Postrun wiring: `src/agent/loop.py::_post_run_fill_stubs` between mistake-discovery and self-evolution. `StubFiller.afill_all_stubs` runs 5 stubs concurrently (~5x speedup). Combat / boss stubs use combat replay sampling; deckbuilding / map / intermission stubs use trajectory rendering + Attribution Summary.
- Code: `src/skills/{stub_template,stub_filler,stub_validators,stub_evidence,stub_prompts}.py` + `src/skills/seeds_stubs/{combat,boss,deckbuilding,map,intermission}.template.json`. Ablation matrix updated to **5 conditions** in `scripts/run_ablation.py` (commit `a0393ad`): `baseline-strict`, `prompt-only`, `mode-a` (NEW; full prompts + expert seeds), `self-evolve` (now uses Mode B stubs instead of free-form), `full`.
- Config keys: `STS2_USE_SEED_STUBS`, `STS2_SEED_STUB_FILL_ENABLED`, `STS2_DISABLE_SKILL_SEEDS`, `STS2_STM_ENABLED`. Audit log: `evolution/stub_fill_log.jsonl`.
- Empirical (as of 2026-05-07): 41 Mode B runs in two experiments. `mode-b-smoke-2026-05-03`: 21 runs, 5 wins, max actual A5. `mode-b-fixed-2026-05-04`: 20 runs, 6 wins, A6 attempted. Per-experiment skill stores isolated under `../AgenticSTS-Data/experiments/mode-b-*/`.

## 2026-04-30

- Trivial-hand combat plans (≤2 playable cards) now route to fast tier via `simple=True` in `_get_v2_tier`. Avoids burning strategic-tier reasoning on near-empty hands (commits `3196c6b`, `a2f9e15`, `5eeef29`).
- Class-pool injection landed in postrun Turn 1/2 + bucket B for non-deck card notes (commits `20e4455`–`6414b4d`): postrun LLM sees the upcoming-class card pool when proposing per-card notes, not just the current deck.

## 2026-04-29

- Mod repository split: C# mod moved from in-tree `STS2-Agent-Fork/` to sibling repo `ShandaAI/AgenticSTS:AgenticSTS-Mod` (proper fork of `CharTyr/STS2-Agent` at merge-base `30e39ea`). Plain `git merge upstream/main` workflow, no force-pushes. See [`REPO_LAYOUT.md`](REPO_LAYOUT.md).
- Regent character support: 3 new seed files (`regent_a10_guide.json`, `regent_card_notes.json`, `regent_starting_deck.json`), `_regent_economy_fmt.py` for gold/forge hints, A10 guide rewrite, STAR DEBT veto in card pickers, Sovereign Blade / Forge awareness in combat plans.

## 2026-04-26 to 2026-04-28

- Ablation harness landed: `scripts/run_ablation.py` orchestrator with resume support, per-experiment data dir for `self-evolve`, baseline-strict prompt variants in `prompts/system.py` and per-state-type files (`PROMPT_VARIANT` env var gate). See [`ABLATION.md`](ABLATION.md).
- Mod default port changed 8080 → 8128 (2026-04-28) to avoid Clash / common proxy collisions.

## 2026-04-25

- Card memory keys collapsed to **base name only**: Strike / Strike+ / Strike++ now share one slot in `card_memory_store`. Eliminates fragmentation across upgrade tiers; per-card statistics aggregate over all upgrade levels.

## 2026-04-23

- Non-combat skill discovery removed. The discovery pipeline (cohort + non-combat both) was simplified to a single mistake-driven combat path. Non-combat knowledge now comes from authored seed skills (L5) + run-derived guides (`CombatGuide` / `RouteGuide` / `DeckGuide` / `EventGuide`). `data/skill_discovery_counter.json` is no longer read or written. `src/brain/batch.py` reduced to drain-only (no production code submits new batches).

## 2026-04-22

- Dynamic data split into sibling repo `ShandaAI/AgenticSTS:AgenticSTS-Data` so multiple machines can evolve in parallel. Code stays in main repo; `memory/`, `skills/`, `evolution/`, `runs/` move to sibling. Path resolution via `src/storage/paths.py`. `STS2_DATA_REPO` env var routes accessors. Static `data/knowledge/` + `data/patches/` + `data/version_compatibility.json` stay in main repo. See [`REPO_LAYOUT.md`](REPO_LAYOUT.md).

## 2026-04-20

- Write-gate reap + skill-merge pipeline landed. `defer_to_judge` candidates hold on `WriteGate._pending_skills` until `flush_judge_round` returns verdicts; `ADD` persists, `UPDATE` replaces (falls back to add on missing target), `REJECT` drops, and `MERGE` delegates to `src/skills/merge_pipeline.py::run_merge_pair` with dual-anchor A/B validation. Wired through `AgentLoop._flush_write_gate_judge` (now `async`) and gated by `STS2_WRITE_GATE_REAP_ENABLED` (default off). Audit trail at `evolution/reap_log.jsonl`. Subsequent split into 5 modules: `write_gate.py`, `write_gate_judge.py`, `write_gate_lifecycle.py`, `write_gate_ab.py`, `write_gate_reap.py`.
- `SituationTag` fields simplified: `threat_level`, `intent_class`, `deck_stage` removed from `src/memory/situation.py`; only `hand_capabilities`, `damage_taken`, and `outcome_quality` remain. `SituationTag.from_dict` is tolerant to unknown keys so existing stored episodes keep parsing with defaults.

## 2026-04-19

- Skill discovery path replaced: cohort-based combat skill discovery (`cohort_discovery.py`, `cohort_utils.py`, `evidence.py`, `hypothesis_store.py`) was removed in favor of mistake-driven discovery. New pipeline (`src/skills/mistake_discovery.py` + `critic_prompt.py` + `prewrite_ab.py`): per-combat `loss_ratio` vs. enemy-median Baseline A and act×combat_type×character Baseline B → LLM critic → candidate validator → pre-write A/B (B=3 resample, zero `skill_harmful` + `sum(hits) ≥ ceil(total × 2/3)`) → 4-level write gate. Survivors enter with `confidence = 0.40 + 0.05 × len(mistake_round_indices)` and `status="probation"`. Seed skills are exempt from deactivation (floored at 0.40). See [`SELF_EVOLUTION.md`](SELF_EVOLUTION.md).

## 2026-04-18

- **Prompt evolution (PE) removed.** Empirical finding: 33/33 postrun-proposed prompt patches failed A/B validation over a 10-day run span (primarily INVALID_B decision-schema violations). Architecture simplified — only L4 memory / L5 skills / dynamic tools are postrun-writable. L1 system / L2 state prompts are now human-authored + immutable except for game-version patches. See `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`.
- Two prompt duplication sources removed: `## Strategy Skills` double-header bug; `## Card Experience Notes` in reward.py/shop.py duplicating retriever's `## Card-Specific Insights`.
- Postrun Strategic Thread injection landed: `Decision.strategic_note` now persists to JSONL via `log_decision`; `context_builder._render_strategic_thread` emits a floor-grouped section into evolution context. `EVOLUTION_REPLAY_TOKEN_BUDGET` raised 22k → 40k.
- Skill replay eval bugs fixed: `_eval_current_index` gained `-1` sentinel for the baseline slot; save/quit reload now snapshots `_v2_combat_conversation._strategic_notes` and re-injects them into the new conversation. `STS2_SKILL_EVAL` stays `false` until a live boss fight verifies the A/B signal.

## 2026-04-17

- Game update patch pipeline landed: `data/patches/<version>.yaml` manifest schema, `scripts/apply_patch.py` orchestrator (snapshot → entity-reference purge → LLM prompt rewrite → version bump), golden log regression harness, mod API coverage check. v0.103.1 manifest authored from patch notes; dry-run verified against current v0.5.3 data. Pipeline ready; game update and mod rebuild pending user action. See [`REPO_LAYOUT.md`](REPO_LAYOUT.md).
- Paper target switched: NeurIPS → EMNLP.

## 2026-04-13

- Reward handling now follows runtime alternatives more faithfully: `choose_reward_alternative` is recognized in parser/state inference, prompts show exact alt indices, and stuck recovery only clicks an explicit Skip alternative.
- Route planning is now gold-aware: high-gold routes without shops are penalized earlier, and route progress fallback uses floor/act when map coordinates are missing.
- Retain prompts were tightened: retained cards are treated as free extras, so the default bias is to keep all non-harmful cards.
- Prompt-memory injection was simplified: past experience injected directly instead of nested under an extra wrapper heading.
- Event payload reverse engineering: event option hover data is sourced from `MegaCrit.Sts2.Core.Events.EventOption.HoverTips`. Future C# event payload work should use hover tips as primary extraction path.
- (DEPRECATED 2026-04-18) Prompt patch lifecycle landed: structured prompt-edit proposals, JSONL patch store, replay-based A/B tester, next-run auto-apply of promoted patches. Removed when PE was deprecated.

## Earlier history

For 2026-03-* and earlier development phases see:
- `docs/archive/development-phases.md`
- `docs/archive/bugs-fixed.md`
- `docs/archive/detailed-technical-decisions.md`
