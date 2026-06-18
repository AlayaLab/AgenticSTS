# AgenticSTSMCP

Self-evolving autonomous agent for Slay the Spire 2. Target: EMNLP paper (switched from NeurIPS 2026-04-17).
Core contribution: LLM + retrieval-augmented skills + hierarchical categorical memory for training-free self-evolution.

## Quick Reference

```bash
# Requires .env: ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL
python -m scripts.run_agent --steps 500 --runs 1           # Single run
python -m scripts.run_agent --steps 500                    # Infinite loop
python -m scripts.run_agent --steps 500 --character Regent # Specify character
python -m scripts.run_agent --steps 500 --ascension 5      # Fixed ascension
python -m scripts.run_agent --steps 500 --ascension auto    # Auto-progress
python -m scripts.run_agent --steps 500 --no-skills --no-memory --no-llm  # flags
python -m scripts.inspect_memory                           # View memory state
```

Key config env vars: `STS2_MODEL_FAMILY` (gemini/gpt/qwen/claude), `STS2_POSTRUN_ENABLED`, `STS2_FAST_MODEL`, `STS2_STRATEGIC_MODEL`, `STS2_ANALYSIS_MODEL`, `STS2_EVOLUTION_MODEL`, `STS2_<FAMILY>_EFFORT_<TIER>`, `STS2_EVOLUTION_ENABLED`, `STS2_WEB_SEARCH`, `STS2_MONITOR_ENABLED`, `STS2_SKILL_EVAL`, `STS2_DATA_REPO` (sibling data repo path), `STS2_MACHINE_ID` (defaults to short hostname)

Data: `logs/run_*.jsonl` (local) | sibling repo `../AgenticSTS-Data` → `memory/` `skills/` `evolution/` `runs/`

## Data Repository Split

As of 2026-04-22, dynamic data lives in a **sibling repo** (`ShandaAI/AgenticSTS-Data`,
cloned to `../AgenticSTS-Data`) so multiple machines can evolve the agent in parallel.
The main repo keeps only code + static data; everything the agent writes at runtime
or postrun (memory stores, evolved skills, authored tools, run history) is in the sibling.

**Dynamic (sibling repo)** — paths are at sibling root, no `data/` prefix:
- `memory/rules.json`, `memory/v2/{combat_episodes,route_memories,card_builds,event_memories}.jsonl`, `memory/v2/{guides,card_memories}.json`
- `skills/skills.json`, `skills/skill_usage.jsonl`
- `evolution/evolution_log.jsonl`, `evolution/tools/*.py`, `evolution/proposals/`, `evolution/reap_log.jsonl`, etc.
- `runs/history.jsonl`, `runs/ascension_stats.json`

**Static (main repo)** — stays under `data/`:
- `data/knowledge/` (upstream-synced game DB), `data/patches/` (authored manifests),
  `data/version_compatibility.json`, `data/reports/` (local audit output)

**Per-machine operational state** — local only, gitignored on both sides:
- `data/batch_pending.json`, `logs/run_*.jsonl` (`data/skill_discovery_counter.json` was retired with the non-combat discovery pipeline — file may still exist on disk from older runs but is no longer read or written)

**Path resolution** — every store accessor routes through `src/storage/paths.py`.
Set `STS2_DATA_REPO=<abs path>` to point at the sibling. Unset → falls back to
`<main repo>/data` for local-only development. `STS2_MACHINE_ID` defaults to the
short hostname; override per machine for clear provenance.

**Setup for a new machine**:
```bash
git clone git@github.com:<user>/AgenticSTS.git
git clone git@github.com:ShandaAI/AgenticSTS-Data.git   # must be at ../AgenticSTS-Data
export STS2_DATA_REPO=$(cd ../AgenticSTS-Data && pwd)
export STS2_MACHINE_ID=$(hostname -s)  # optional; default is auto-derived
```

Sync protocol + per-file merge drivers (for multi-machine reconcile) are in flight
(Step 3). For now, the sibling is a plain shared repo — pull/push manually.

## Mod Repository Split

As of 2026-04-29, the C# mod lives in a **sibling repo**
(`ShandaAI/AgenticSTS-Mod`, cloned to `../AgenticSTS-Mod`) — a proper fork of
[CharTyr/STS2-Agent](https://github.com/CharTyr/STS2-Agent) at merge-base
`30e39ea`. The split lets the mod sync with upstream cleanly
(plain `git merge upstream/main`) without dragging the outer agent repo
through merges.

**Setup for a new machine** (in addition to the data-repo setup above):
```bash
git clone git@github.com:ShandaAI/AgenticSTS-Mod.git ../AgenticSTS-Mod
```

**Upstream sync** (in `../AgenticSTS-Mod`):
```bash
git fetch upstream                            # CharTyr/STS2-Agent
git merge upstream/main                       # resolve, commit
cd STS2AIAgent && dotnet build -c Release    # rebuild
git tag upstream-sync-$(date +%Y-%m-%d) upstream/main
git push origin main --tags
```

Why merge (not rebase): multiple machines pull from `ShandaAI/AgenticSTS-Mod`;
force-pushes after rebase break their clones. See `../AgenticSTS-Mod/VENDOR.md`
for the full sync workflow. Tag `fork-base` permanently anchors the merge-base
commit (`30e39ea`).

## C# Mod

The mod is a .NET 9 / Godot 4.5 / Harmony fork of CharTyr/STS2-Agent
maintained at `ShandaAI/AgenticSTS-Mod`. Local checkout: `../AgenticSTS-Mod/`.

**Build:**
```bash
cd ../AgenticSTS-Mod/STS2AIAgent
dotnet build -c Release
# Requires STS2 game DLLs at: C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2/data_sts2_windows_x86_64/
# Override path: set STS2_DATA_DIR env var before building
```

**Deploy:** Copy `../AgenticSTS-Mod/STS2AIAgent/bin/Release/net9.0/STS2AIAgent.dll` → game's `mods/` directory, then launch STS2. (Pre-built DLL + .pck are also tracked at `../AgenticSTS-Mod/build/mods/STS2AIAgent/` for clone-and-deploy workflows.)

**Custom files** (our modifications): `Game/GameActionService.cs`, `Game/GameStateService.cs`

**API:** HTTP REST at `localhost:8128` — `GET /state`, `POST /action`, `GET /events/stream`. Mod default changed from 8080 → 8128 on 2026-04-28 to avoid Clash / common proxy collisions; `--api-port=auto` still picks any free port via `STS2_API_PORT`.

**Reverse-engineering rule:** For C# mod work, inspect `data_sts2_windows_x86_64/sts2.dll` with `ilspycmd` before assuming behavior is UI-only. Prefer model-level extraction over hover-node scraping; use the upstream mod's `mcp_server/data/eng/*.json` (from CharTyr/STS2-Agent; not bundled in the trimmed `AgenticSTS-Mod/`) as fallback only for opaque random rewards.

**Event preview finding:** Event hover previews are sourced from `MegaCrit.Sts2.Core.Events.EventOption.HoverTips`, and `NEventOptionButton.OnFocus()` only renders those tips through `NHoverTipSet.CreateAndShow(...)`. `CardHoverTip.Card` exposes a real `CardModel`; potion and relic hover tips expose `CanonicalModel`, which can be checked for `PotionModel` / `RelicModel`.

## Architecture

```
scripts/run_agent.py          # Entry point (--steps, --runs, --character, --no-llm, --no-memory, --no-skills)
scripts/inspect_memory.py     # Memory system inspector
src/
  mcp_client/
    client.py                 # Async httpx REST client (localhost:8128)
    actions.py                # Action builders — upstream API names (play_card, buy_card, etc.)
    upstream_models.py        # Pydantic models for upstream /state payload
    sse_client.py             # SSE event notifications → triggers state refresh
  state/
    game_state.py             # GameState wrapper (frozen Pydantic)
    upstream_game_state.py    # UpstreamStateView convenience wrapper
    state_parser.py           # parse_state() raw JSON → GameState
    run_state.py              # RunState accumulator + fitness function
  brain/
    models.py                 # Shared LLMDecision + DecisionSource
    llm_caller.py             # call_raw() adapter wrapping V2Backend for post-run callers
    planner.py                # CombatPlan: card-name resolution, draw-card detection
    tool_schemas.py           # 6 gameplay tool definitions (5 query + 1 decision per state type)
    batch.py                  # Anthropic Batch API: submit/check post-run analysis
    v2_engine.py              # V2Engine: multi-turn combat + tool-use agent (sole decision engine)
    v2_backend.py             # Multi-provider backend: Anthropic + OpenAI-compatible, streaming, tool routing, 120s timeout, prompt caching
    conversation.py           # CombatConversation: multi-turn message history within a single combat
    run_context.py            # RunContextView: read-only run summary injected into user messages
    tool_executor.py          # Dispatches 5 static query tool handlers (no dynamic fallback)
    dynamic_tools.py          # DynamicToolRegistry: AST-sandboxed agent-authored tools
    write_tools.py            # 5 write-side tool schemas (author_tool, write_skill, update_guide, etc.)
    evolution_engine.py       # Post-run self-evolution: three-stage dispatch (write → query → dynamic)
    tool_preprocessor.py      # ToolPreprocessor: state-derived tools → local execution → prompt hints
    plan_verifier.py          # PlanVerifier: post-plan plan_evaluator tools → severity → needs_replan flag
    route_planner.py          # DFS route enumeration + annotation-based multi-key sorting
    route_checker.py          # Condition-triggered re-plan checker (HP danger, gold surplus, deviation)
    decision_parser.py        # Extract and validate <decision> JSON blocks from LLM text responses
    enemy_pattern_injector.py # Format enemy behavior patterns from past episodes for combat prompts
    state_snapshot_store.py   # Ring-buffer capture of real GameState snapshots for tool validation
    proxy_compat.py           # Helpers for probing proxy compatibility across Claude API variants
    cache_diagnostics.py      # Anthropic prompt-cache diagnostics helpers
    card_effects.py           # Runtime card effect detection (draw/discard from rules_text)
    prompts/
      system.py               # 4 system prompts: COMBAT, COMBAT_BOSS, DECKBUILD, STRATEGIC
      potion.py               # Type-classified potion decisions (damage/block/buff/heal)
      map.py                  # Map: Scenario A (route selection) + Scenario B (step walking)
      event.py                # 6-factor event scoring framework
      rest.py                 # 5-factor rest scoring (Smith default, relic-aware)
      shop.py                 # Gold-budget-aware shop decisions
      reward.py               # 5-factor card evaluation + act-aware guidance
      card_select.py          # Deck-coherence-aware tier evaluation (upgrade/remove/enchant)
      hand_select.py          # Mode-aware hand selection (discard vs exhaust)
      treasure.py             # 4-factor relic evaluation
      distill.py              # Cross-run rule distillation prompt
      _relic_fmt.py           # Relic synergy hints (context-filtered, ~100 tokens)
      _intent_fmt.py          # Structured intent parsing (compute_total_incoming)
      _deck_fmt.py            # Deck formatting helper
      _pile_fmt.py            # Conditional draw/discard/exhaust pile formatting
      _target_fmt.py          # Target scope descriptions
      _card_clarifications.py # Card mechanic clarifications for commonly misunderstood cards
      _keyword_fmt.py         # Keyword glossary: scan rules_text → inject concise definitions
  runs/
    history.py                  # RunRecord + RunHistoryStore (append-only JSONL at data/runs/history.jsonl)
    ascension_stats.py          # AscensionStats aggregate cache (profile × character × ascension)
  skills/
    models.py                 # Skill + SkillTrigger frozen dataclasses
    library.py                # SkillLibrary: load, query, persist, merge seeds
    composer.py               # Compose retrieved skills into prompt context
    mistake_discovery.py      # Mistake-driven combat skill discovery (sole skill-producing path as of 2026-04-23)
    critic_prompt.py          # LLM critic for mistake review + skill candidate proposal
    prewrite_ab.py            # Pre-write A/B validation (resample B×3, strict 2/3 + zero-harmful)
    lifecycle.py              # Skill confidence update + retirement policy
    noncombat_scorer.py       # Per-run non-combat skill scoring (progress + HP efficiency)
    replay_evaluator.py       # Boss replay evaluation (save/quit/continue cycle, kill detection)
    combat_quality.py         # Combat outcome weight for skill confidence updates
    dedup.py                  # Semantic dedup for skill candidates (content_overlap, seed_restatement)
    merge_pipeline.py         # run_merge_pair: LLM merge + dual-anchor A/B validation
    seeds/
      core_combat.json        # Core combat principles
      core_boss_strategy.json # Boss/elite fight strategy
      core_deck_building.json # Deck building across the run
      core_map_routing.json   # Map routing and path planning
      core_rest_decision.json # Rest site and event decisions
      silent_a10_guide.json   # Silent character Act 1-end guide
      silent_card_notes.json  # Silent-specific card tier notes
  memory/
    models_v2.py              # HCM models: CombatEpisode, RouteMemory, CardBuildMemory, CardMemory, etc.
    short_term.py             # Mutable working memory: combat/route/deck trackers + strategic thread
    rule_store.py             # Strategy rules with self-verification
    combat_store.py           # CombatEpisode store (enemy_key×character retrieval)
    route_store.py            # RouteMemory store (act×character retrieval)
    card_build_store.py       # CardBuildMemory store (character×archetype retrieval)
    card_memory_store.py      # Per-card longitudinal memory (character×card_name), JSON persistence
    card_memory_extractor.py  # Post-run per-card statistics extraction (no LLM, additive merging)
    guide_store.py            # Consolidated guides (CombatGuide, RouteGuide, DeckGuide)
    guide_consolidator.py     # Phase 5: episodes → Guide via LLM
    retriever.py              # Decision-type-aware unified retrieval → WorkingContext
    combat_extractor.py       # ShortTermMemory → CombatEpisode extraction
    route_extractor.py        # ShortTermMemory → RouteMemory extraction
    card_build_extractor.py   # ShortTermMemory → CardBuildMemory extraction
    combat_delta.py           # Per-action state diff (HP, block, energy, powers) between snapshots
    situation.py              # Per-round tags (threat level, intent class, hand capabilities, deck stage)
    hint_sanitizer.py         # Drop known-bad legacy deck-guide lines from prompt output
    memory_manager.py         # Unified facade: HCM domain stores + rules + guides
    rule_distiller.py         # Cross-run: LLM rule extraction from V2 domain data
    prompt_injector.py        # HCM prompt injection (format_working_context)
  knowledge/
    parser.py                 # Markdown table parser for knowledge data files
    card_lookup.py            # Card metadata + behavior + Vars lookup (577 cards)
    monster_lookup.py         # Monster HP range + move pattern lookup (121 monsters)
    potion_lookup.py          # Potion metadata + behavior lookup (64 potions)
    potion_classifier.py      # Potion type classification (damage/block/buff/heal/utility)
    power_lookup.py           # Power/debuff metadata + descriptions
    event_lookup.py           # Event type lookup (68 events)
    act_lookup.py             # Act metadata (id, name, bosses, encounters) from upstream acts.json
    relic_lookup.py           # Relic metadata (name, description, rarity) from upstream relics.json
    enchantment_lookup.py     # Enchantment metadata from upstream enchantments.json
    encounter_lookup.py       # Fight compositions (room_type, act, monsters) from decompiled source
    keyword_lookup.py         # Keyword definitions from upstream keywords.json
    knowledge.py              # GameKnowledge singleton facade
    injector.py               # KnowledgeInjector: token-budgeted prompt injection
    web_searcher.py           # Claude web search (Opus 4.6) for boss strategy guides
  agent/
    loop.py                   # Core agent loop: observe → decide → act
    state_machine.py          # Phase transition tracking
  monitor/
    event_bus.py              # Thread-safe broadcast EventBus (MonitorEvent with run_id)
    server.py                 # FastAPI WebSocket server + REST history + AI summarizer startup
    summarizer.py             # Background Haiku 4.5 summarizer for LLM thinking + combat plans
  log/
    session_logger.py         # JSONL structured logging (full state snapshots + EventBus push)
config.py                     # Global configuration
frontend/                     # React 19 + TypeScript + Vite + Tailwind CSS monitor dashboard (:8081)
../AgenticSTS-Mod/STS2AIAgent/ # C# game mod source — sibling repo (see "Mod Repository Split" / "C# Mod" sections above)
data/knowledge/               # Game knowledge database (cards.md, monsters.md, potions.md, events.md)
data/evolution/               # Self-evolution artifacts (tools/, proposals/, evolution_log.jsonl)
docs/archive/                 # Archived CLAUDE.md sections (bugs-fixed, dev-phases, detailed-decisions)
```

## Key Decisions

**Model routing** — `_get_v2_tier(state_type)` in v2_engine.py dispatches to one of four tiers:
- Fast: combat single-card, potions, hand_select, treasure, map step
- Strategic (streaming): combat plans, rest, shop, event, card_reward, card_select, route selection
- Analysis: post-run reflection, distillation, guide consolidation, skill discovery
- Evolution: self-evolution tool-use loop

**Model family registry** (`config._MODEL_FAMILIES`) — pick a family via `STS2_MODEL_FAMILY` / `--model-family` and tier→model→effort resolves automatically. Declared families: `gemini` (default), `gpt`, `qwen`, `claude`. Each entry is `{model, effort}`; families without an `analysis` entry (e.g. `qwen`) auto-disable postrun. Peer fallback chains are derived from `MODEL_FAMILY_FALLBACK` (default `gemini,gpt,qwen,claude`). Provider (anthropic vs openai_compatible) comes from `_FAMILY_PROVIDER`. Escape hatches: per-tier family override (`STS2_MODEL_FAMILY_FAST`), per-family effort override (`STS2_QWEN_EFFORT_STRATEGIC`), direct model override (`STS2_FAST_MODEL`), per-family credentials (`STS2_GPT_API_KEY`, `STS2_GPT_BASE_URL`, ...).

**Postrun switch** — `config.postrun_effectively_enabled()` is False when (1) `STS2_POSTRUN_ENABLED=false` / `--no-postrun`, or (2) the active family has no `analysis` tier and no `STS2_ANALYSIS_MODEL` override. When False, `_safe_post_run()` short-circuits before memory/skills/evolution/judge stages — useful for weak-model test runs where postrun would poison L4/L5 stores. Gameplay-time JSONL logging is unaffected.

**Tool architecture** — Gameplay API = 6 tools only (5 static query + 1 decision). Dynamic tools NOT exposed to gameplay. Dynamic tools consumed via ToolPreprocessor (pre-LLM hints) and PlanVerifier (post-plan checks) and EvolutionEngine (direct dispatch).

**Prompt caching** — 4 system prompts (COMBAT/COMBAT_BOSS/DECKBUILD/STRATEGIC) are STATIC. Run-specific context always in user messages only. `cache_control: {"type": "ephemeral"}` on system prompt.

**Combat conversation** — `CombatConversation` accumulates multi-turn history within a fight. Plans execute → round results added → next round sees full history. Generates summary at combat end for memory extraction.

**Strategic thread** — `strategic_note` extracted from tool response params → STM._strategic_thread → `## Strategic Thread` injected into all prompts. Intent-driven run context (win condition + key pieces + gaps + avoid), 50-word limit.

**Self-evolution** — Post-run EvolutionEngine (Gemini 3.1 Pro primary, GPT-5.4 Thinking fallback): three-stage dispatch (write tools → static query → dynamic). AST-sandboxed `.py` tool files. Mistake-driven combat skill discovery (`src/skills/mistake_discovery.py` — replaced the cohort/hypothesis-store path on 2026-04-19): per-combat loss_ratio vs. enemy/act baselines → LLM critic → pre-write A/B (B×3 resample, strict 2/3 + zero-harmful) → 4-level write gate → dual-anchor merge pipeline. **Prompts are treated as immutable by postrun** — postrun only writes to L4 memory / L5 skills / dynamic tools, never edits source-code prompts. See `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`.

## Recent Progress (2026-04-20)

- Write-gate reap + skill-merge pipeline landed. `defer_to_judge` candidates now hold on `WriteGate._pending_skills` until `flush_judge_round` returns verdicts; `ADD` persists, `UPDATE` replaces (falls back to add on missing target), `REJECT` drops, and `MERGE` delegates to `src/skills/merge_pipeline.py::run_merge_pair` with dual-anchor A/B validation (strict 2/3 + zero-harmful on both sides). Wired through `AgentLoop._flush_write_gate_judge` (now `async`) and gated by `STS2_WRITE_GATE_REAP_ENABLED` (default off, observation-mode persistence preserved). Audit trail at `data/evolution/reap_log.jsonl`. Pending live smoke at `STS2_WRITE_GATE_REAP_ENABLED=true python -m scripts.run_agent --steps 80 --runs 1` before flipping the default on.
- `SituationTag` fields simplified: `threat_level`, `intent_class`, `deck_stage` were removed from `src/memory/situation.py` as part of the mistake-driven skill discovery redesign; `SituationTag.from_dict` is tolerant to unknown keys so existing stored episodes keep parsing with defaults. Only `hand_capabilities`, `damage_taken`, and `outcome_quality` remain.

## Recent Progress (2026-04-19)

- Skill discovery path replaced: cohort-based combat skill discovery (`cohort_discovery.py`, `cohort_utils.py`, `evidence.py`, `hypothesis_store.py`) was removed in favor of mistake-driven discovery. New pipeline (`src/skills/mistake_discovery.py` + `critic_prompt.py` + `prewrite_ab.py`): (1) per-combat `loss_ratio` vs. enemy-median Baseline A and act×combat_type×character Baseline B flags high-loss episodes; (2) LLM critic reads the round trace and either proposes a candidate skill or emits `no_skill_needed` / `bad_luck` / `unavoidable_mechanic` / `descriptive_rhythm`; (3) candidate validator enforces name/content/trigger constraints; (4) pre-write A/B resamples B=3 decisions per mistake round with the candidate injected, requires zero `skill_harmful` verdicts and `sum(hits) >= ceil(total × 2/3)`; (5) survivors enter the 4-level write gate with `confidence = 0.40 + 0.05 × len(mistake_round_indices)` and `status="probation"`. Seed skills are now exempt from deactivation (floored at 0.40) in `apply_retirement_policy`.

## Recent Progress (2026-04-18)

- Prompt evolution (PE) removed. Empirical finding: 33/33 postrun-proposed prompt patches failed A/B validation over a 10-day run span (primarily INVALID_B decision-schema violations). Evidence-supported conclusion: postrun LLM critiques applied to authoring-layer prompt edits produce fragile modifications the validation gate correctly but exhaustively rejects. Architecture simplified — only two modifiable knowledge stores remain (L4 memory, L5 skills); L1 system / L2 state prompts are now human-authored + immutable except for game-version patches. See `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`.
- Two prompt duplication sources removed: `## Strategy Skills` double-header bug (three call sites prepending to composer output that already had its own header); `## Card Experience Notes` in reward.py/shop.py that read `card_memory_store` directly and produced entries identical to the unified memory retriever's `## Card-Specific Insights`.
- Postrun Strategic Thread injection landed: `Decision.strategic_note` now persists to JSONL via `log_decision`; `context_builder._render_strategic_thread` emits a floor-grouped section into evolution context. Per-combat decision chain mirrored into `CombatTracker.strategic_notes`, emitted on `combat_summary`, attached to `ReplayEntry`, and rendered per-round as `Agent plan (hypothesis): …` lines in `format_combat_replay`. `EVOLUTION_REPLAY_TOKEN_BUDGET` raised 22k → 40k.
- Skill replay eval bugs fixed: `_eval_current_index` gained `-1` sentinel for the baseline slot, so `_eval_skill_sets[0]` is now tested and single-entry schedules compare baseline vs alt (prior behavior skipped `[0]` and collapsed 1-entry schedules back to original). Save/quit reload now snapshots `_v2_combat_conversation._strategic_notes` beforehand, re-injects them into the new conversation, and passes `strategic_thread=` from STM so replays preserve both intra-combat and run-level context. `STS2_SKILL_EVAL` stays `false` until a live boss fight verifies the A/B signal.

## Recent Progress (2026-04-17)

- Game update patch pipeline landed: `data/patches/<version>.yaml` manifest schema, `scripts/apply_patch.py` orchestrator (snapshot → entity-reference purge → LLM prompt rewrite → version bump), golden log regression harness, mod API coverage check. v0.103.1 manifest authored from patch notes; dry-run verified against current v0.5.3 data. Fixed purge handlers for new list-based card_memories.json and skills.json formats. Pipeline ready; game update and mod rebuild pending user action.

## Recent Progress (2026-04-13)

- Prompt patch lifecycle landed: structured prompt-edit proposals, JSONL patch store, replay-based A/B tester, and next-run auto-apply of promoted patches. **(Removed 2026-04-18 — see deprecation note above.)**
- Reward handling now follows runtime alternatives more faithfully: `choose_reward_alternative` is recognized in parser/state inference, prompts show exact alt indices, and stuck recovery only clicks an explicit Skip alternative.
- Route planning is now gold-aware: high-gold routes without shops are penalized earlier, and route progress fallback uses floor/act when map coordinates are missing.
- Retain prompts were tightened: retained cards are treated as free extras, so the default bias is to keep all non-harmful cards.
- Prompt-memory injection was simplified: past experience is injected directly instead of being nested under an extra wrapper heading.
- Event decision enhancement work advanced at the design level: the plan/spec now cover concrete event outcome diffs, post-run boss-impact analysis, EventGuide consolidation, and event-aware skill discovery. Most of that pipeline is still TODO in code.
- Event payload reverse engineering made a concrete runtime discovery: event option hover data is not transient UI-only state. The canonical source is `EventOption.HoverTips`, so future C# event payload work should use hover tips as the primary extraction path and reserve text/local-data fallbacks for random rewards.

## Active TODOs

- [ ] Event decision enhancement implementation: EventMemory/EventGuide pipeline (Python side), boss-impact analysis, and event-aware skill discovery. NB: C# `EventOption.HoverTips` primary extraction path already landed in `GameStateService.cs` (`GetEventHoverTips` + `ExtractEventHoverTipCards/Relics/Potions`) with reflection fallback for subclasses.
- [ ] Card upgrade comparison at Smith (only post-upgrade version visible)
- [ ] P2b: Self-evolution validation runs (10-20 games), tool creation verification
- [ ] Phase 5 (EMNLP): Evaluation framework — win rate, floor progress, skill evolution metrics
- [ ] Manual review: evolved tools/skills in `data/evolution/archive_manual_review/`
- [ ] Potion card_select: Discovery-type potions trigger card_select mid-combat — needs combat-aware context
- [ ] Batch API: not supported by proxy.example.com proxy — sync fallback used; Batch API for Anthropic-direct only
- [ ] Act-boss-aware reward/shop card selection: inject current act's boss (and elites) info into card_reward / shop prompts so picks favor matchups against the upcoming boss (e.g. prioritize AoE vs multi-enemy bosses, block vs high-damage bosses)
- [ ] Flexible potion usage: when potion slots are full and a held potion offers net benefit in the current state, use it proactively; allow discarding a weaker potion to pick up a better one at reward/shop instead of skipping
- [ ] L1/L2 prompt slimming: migrate heuristics (4-dimension eval, Boss DPS check, Build Trajectory, Smith-default, HP conservation, potion timing) from system.py / reward.py / shop.py / rest.py into seed skills (L5). Goal: L1/L2 only contain game mechanics + output schema; all heuristics live in L4/L5 where postrun can evolve them.
- [ ] Write gate + retriever scope filter (Sections 2 & 3 of the dedup/conflict design) — cascade dedup (exact → Jaccard on trigger-tags → embedding → LLM judge) with concrete thresholds from literature (EvolveR, EvoSkill, WebXSkill), plus decision-type-aware scope filter on Strategic Thread retrieval
- [ ] Skill replay eval — live verification. Code fixes landed (sentinel `_eval_current_index=-1` baseline; schedule[0] now tested; single-entry schedules compare baseline vs alt; save/quit reload re-seeds `CombatConversation._strategic_notes` and passes `strategic_thread=` from STM so replays keep both intra-combat and run-level context). Still need a live boss fight with `STS2_SKILL_EVAL=true` to confirm the A/B signal is distinguishable now, then flip the default back on.
- [ ] Non-replay skill differentiation (urgent if replay stays off): current `record_outcome` / `record_noncombat_outcome` use whole-run win/loss as the only signal — skills converge to similar confidence. Options: (A) floor-weighted noncombat scoring (early ×0.5, mid ×1.0, deep ×1.5); (B) decision-impact coefficient — weight confidence update by skill's appearance frequency in high-stakes decisions (boss/elite/low-HP); (C) per-combat skill attribution — postrun evolution LLM reads combat_conversation + strategic_thread and emits `record_combat_attribution(skill_id, delta)` for each skill actually used. Option C overlaps with the P1 postrun injection below.

## Conventions

- **Stuck recovery**: `_force_unstick()` checks `gs.can_proceed`, uses `available_actions`, always resets counter. NEVER terminate a run due to LLM failures.
- **Card index**: out-of-range → validation error → retry with feedback (no silent substitution)
- **Intent parsing**: `compute_total_incoming()` is the single source of truth for damage calculation
- **Attack detection**: `c.damage is not None` (structured) with text-heuristic fallback
- **Multi-card select**: `_card_select_selected` set tracks indices per session. Fallback: `_parse_select_count_from_prompt()` when `max_select=0`. Auto-confirm after target count reached.
- **Combat type cache**: `_cached_map_node_type` set at map node selection, used at COMBAT_START (MCP API lacks map data during combat)
- **available_actions**: lists possible action *types*, NOT currently executable actions — always check `can_proceed`, `is_enabled`
- **BBCode**: `strip_bbcode()` applied to selection prompts (card_select, hand_select, event, reward)
- **Character normalization**: always use `normalize_character()` when storing to memory stores (prevents fragmentation)
- **Relic format**: `_cached_relics` stores `"Name (description)"`, `format_relic_hints` extracts name via `split(" (")[0]`
- **No mechanical fallbacks** for shop/rest/card/event/map — LLM must decide (mechanical only for treasure/hand_select)
- **Post-run order**: memory extract → distill rules (every 5 runs) → guide consolidation (every 5 runs) → mistake-driven combat skill discovery (every run) → self-evolution. Non-combat skill discovery was removed 2026-04-23 — non-combat knowledge now comes from authored seeds + run-derived guides only.
- **Ascension tracking**: `--ascension auto` reads `AscensionStats.next_ascension(profile_hash, character)`. Stats recorded post-run to `data/runs/`. Keyed by `(profile_hash, character, ascension)` for model isolation. **Experiment runs (with `--experiment-tag`) bypass this entirely** — see "Running ablation experiments" below.
- **Run history**: every completed/aborted run appends to `data/runs/history.jsonl`. Fields include `model_profile` snapshot, `outcome` (victory/defeat/agent_abort/interrupt/max_steps), `target_ascension`/`actual_ascension`.

## Running ablation experiments

Experiment runs (ablations, evals, reproducibility tests) follow these rules to stay isolated from personal-progression state, support `--ascension auto` fairly across conditions, and be safe under parallel multi-agent execution:

1. **Always pass `--experiment-tag <tag>`.** This activates session-local AscensionStats behavior in `scripts/run_agent.py::_load_ascension_stats_for_session()`. The session derives stats from `runs/history.jsonl` filtered by this tag — never from the global `runs/ascension_stats.json`. Implications: (a) personal play history never shifts the experiment's starting ascension; (b) the global cache is never written, so concurrent parallel agents cannot race on a file without a merge driver (`dict_counter_merge` is TODO in data_sync); (c) a resumed session with the same tag picks up where the prior session left off because history.jsonl is its source of truth.

2. **`--ascension auto` is the recommended mode for fair comparisons.** Each condition starts at A0 (no matching history yet) and auto-advances on its own wins, so baseline and full progress independently and fairly. Fixed `--ascension N` still works for targeted "test this ascension specifically" experiments. The mixed forms `auto-N` / `reset-N` also work.

3. **Stats writes are skipped when `experiment_tag` is set.** Per-condition / per-ascension win rates are derived post-hoc from `runs/history.jsonl` filtered by `(experiment_tag, actual_ascension, model_profile.*)`. The `runs/ascension_stats.json` cache stays untouched.

4. **Always pass `--no-postrun`** unless the experiment specifically tests postrun behavior. Otherwise postrun would write new skills/memory to L4/L5 stores during the experiment, contaminating later runs of the same condition.

5. **`--abandon-existing` flips meaning under experiment mode.** Default: only the first run of a session abandons; subsequent runs re-enter saved state if any. Experiment mode: every run abandons, ensuring each starts from a clean slate.

6. **For multi-agent parallel runs**: each agent launches its own game subprocess via `--launch-game --api-port=auto --monitor-port=auto`. This gives independent TCP ports + monitor dashboards. Set distinct `STS2_MACHINE_ID` per agent (e.g., `desktop-baseline`, `desktop-full`) so commit messages in the sibling repo are attributable. The single shared file across parallel agents is `runs/history.jsonl`, which has the `append_dedup` merge driver and is parallel-safe.

7. **Per-experiment data isolation (`self-evolve` only).** This condition writes growing L4/L5 stores. The orchestrator points it at `<sibling_repo>/experiments/<tag>/<condition_id>/` via `STS2_DATA_REPO` while keeping `runs/history.jsonl` at the parent sibling root via `STS2_RUNS_HISTORY_REPO`. Other conditions inherit the shared `STS2_DATA_REPO` but have all L4/L5 gates off, so they neither read nor write skill/memory/evolution data.

8. **Resume.** Re-running `python -m scripts.run_ablation --tag <same>` is the resume mechanism. The orchestrator counts existing `(experiment_tag, condition_id)` records in `runs/history.jsonl` and only launches the remaining runs per condition. For `self-evolve`, the per-experiment data dir already contains accumulated skills/memory, so the next run picks up where the prior one left off.

9. **Postrun model parity for `self-evolve`.** The condition sets `STS2_ANALYSIS_MODEL` to the gameplay strategic-tier model (via `analysis_eq_strategic=True` in the `Condition` dataclass), so the same model that plays the game also runs memory extraction, skill discovery, guide consolidation, and evolution. **Effort is NOT synced** — `STS2_THINK_EFFORT_ANALYSIS` defers to your shell env or the family default. This lets you run "cheap gameplay + thoughtful postrun" experiments by setting `STS2_THINK_EFFORT_STRATEGIC=low STS2_THINK_EFFORT_ANALYSIS=high` independently.

10. **Filtering conditions.** Pass `--conditions <kind>` (or comma-separated list) to `run_ablation.py` to run only some kinds. Available kinds: `baseline-strict`, `prompt-only`, `self-evolve`, `full`. Example: `--conditions self-evolve --models gemini` runs only `gemini-self-evolve`.

Canonical pilot command (single-command 4-condition pilot for gemini, 10 runs each, auto-progression):

```bash
# Single-command 4-condition pilot
python -m scripts.run_ablation \
  --tag pilot-2026-04-29 \
  --runs-per-condition 10 \
  --models gemini \
  --character Silent \
  --ascension auto

# Adds two new conditions to the matrix:
#   - {model}-prompt-only:  full prompts, zero accumulated state, no postrun
#   - {model}-self-evolve:  blank L4/L5 start, postrun on (analysis=strategic),
#                           isolated data dir at experiments/<tag>/<cond>/
```

Post-hoc aggregation by `(condition, actual_ascension)`:

```bash
python -c "
import json
from collections import defaultdict
buckets = defaultdict(list)
with open('../AgenticSTS-Data/runs/history.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('experiment_tag') != 'pilot-2026-04-27': continue
        if r.get('outcome') in {'agent_abort', 'mcp_error', 'interrupt'}: continue
        cond = 'baseline-strict' if r['model_profile'].get('prompt_variant') == 'baseline' else 'full'
        buckets[(cond, r.get('actual_ascension', 0))].append(r)
for (cond, asc), runs in sorted(buckets.items()):
    wins = sum(1 for r in runs if r.get('victory'))
    floors = [r.get('final_floor', 0) for r in runs]
    avg_floor = sum(floors)/len(floors) if floors else 0
    print(f'{cond} @ A{asc}: {len(runs)} runs, {wins}W, avg_floor={avg_floor:.1f}, max_floor={max(floors)}')
"
```

The aggregation explicitly filters out `agent_abort` / `mcp_error` / `interrupt` records — those are crashes, not legitimate gameplay outcomes.

## Game Update Playbook

When STS2 releases a new version, run this pipeline:

1. **Author manifest.** Paste patch notes into a Claude session, generate `data/patches/v<new>.yaml` using the Manifest model schema. Commit.
2. **Dry run.** `python -m scripts.apply_patch --manifest data/patches/v<new>.yaml --dry-run --skip-llm`. Review purge counts per store.
3. **Full apply.** `python -m scripts.apply_patch --manifest data/patches/v<new>.yaml`. This snapshots `data/` into `data.snapshots/v<old>-pre-v<new>/`, runs per-store purge by entity reference, LLM-rewrites prompts referencing changed entities (diff batch shown for review), and bumps `data/version_compatibility.json`.
4. **Update game.** Steam update.
5. **Rebuild mod.** `cd ../AgenticSTS-Mod/STS2AIAgent && dotnet build -c Release`. Fix reflection fields if names changed (see `GameActionService.cs`, `GameStateService.cs`). Deploy DLL to game's `mods/`.
6. **Set mod version.** `export STS2_MOD_VERSION=v<new>-xc`; update `data/version_compatibility.json` current.mod_version.
7. **Resync knowledge.** `python -m scripts.sync_upstream_data --game-version v<new>` once mod has shipped new `eng/*.json`.
8. **API schema check.** With mod running: `python -m scripts.check_mod_api_coverage`. Investigate any missing/unused fields.
9. **Regression.** `python -m pytest tests/regression/ -v`. All golden log fingerprints must match.
10. **Live smoke.** `python -m scripts.run_agent --steps 50 --runs 1` — verify agent completes a short run without errors.

Entity-reference purge principle: records that do not reference any changed entity are untouched. `data/evolution/` artifacts are individually scanned, not blanket-archived.

Invariants this pipeline preserves:
- Every persistent record traceable to `(game_version, mod_version)`.
- Snapshots under `data.snapshots/` are never overwritten.
- Pre-destructive `--dry-run` always available.

## Running

```bash
# Claude API (default) — requires .env with ANTHROPIC_API_KEY and ANTHROPIC_BASE_URL
python -m scripts.run_agent --steps 500 --runs 1           # Single run
python -m scripts.run_agent --steps 500                    # Infinite loop
python -m scripts.run_agent --steps 500 --character Regent # Specify character
python -m scripts.run_agent --steps 500 --no-skills        # Disable skills
python -m scripts.run_agent --steps 500 --no-llm           # Random fallback only
python -m scripts.run_agent --steps 500 --no-memory        # Disable memory
python -m scripts.inspect_memory                           # View memory state

# Model family (single switch — all tiers resolve from the registry)
python -m scripts.run_agent --model-family gemini    # default
python -m scripts.run_agent --model-family qwen      # auto-disables postrun
python -m scripts.run_agent --model-family claude --no-postrun

# Fine-grained overrides still work (env beats registry default)
STS2_FAST_MODEL=claude-haiku-4-5 STS2_STRATEGIC_MODEL=claude-sonnet-4-6 python -m scripts.run_agent
STS2_QWEN_EFFORT_STRATEGIC=high python -m scripts.run_agent --model-family qwen

# Skill evaluation
STS2_SKILL_EVAL=true     # Enable boss replay skill evaluation
STS2_SKILL_EXPLORATION_BONUS=5.0  # Score bonus for untested skills
```

Config: MCP server at `localhost:8128`, ACTION_DELAY `0.6s`, thinking disabled for fast tier (proxy compat), thinking enabled (streaming) for strategic tier.
