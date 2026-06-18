# Architecture

Module-level reference for AgenticSTS. Cross-refs:
- [`SELF_EVOLUTION.md`](SELF_EVOLUTION.md) — Skill discovery, write gate, Mode B, evolution engine
- [`MEMORY_SYSTEM.md`](MEMORY_SYSTEM.md) — HCM domain stores, combat conversation, scoped strategic notes
- [`ABLATION.md`](ABLATION.md) — 5-condition ablation matrix
- [`REPO_LAYOUT.md`](REPO_LAYOUT.md) — Sibling repos (data + mod), paths, game update playbook
- [`CHANGELOG.md`](CHANGELOG.md) — Dated progress entries

## Decision flow (one round)

1. Agent loop (`src/agent/loop.py`) observes via MCP client → parses to `GameState`
2. State type → `_get_v2_tier(state_type)` chooses fast / strategic tier (or `simple=True` forces fast on trivial-hand combat plans)
3. V2Engine builds prompt:
   - Combat: through `CombatConversation.add_round_state` then `llm_messages` (only `[combat_start, "ok", latest_user_state]` is sent — see [`MEMORY_SYSTEM.md`](MEMORY_SYSTEM.md))
   - Non-combat: `decide_noncombat` builds fresh `messages = [{"role": "user", "content": user_content}]`
4. Backend (`v2_backend.py`) sends to provider (anthropic / openai_compatible), validates `<decision>` JSON
5. Action dispatched to MCP, state refreshed via SSE

## Top-level layout

```
scripts/                      # Entry points + ops scripts (run_agent, run_ablation, apply_patch, ...)
src/                          # Main agent codebase
config.py                     # Centralized configuration (env vars, model families, feature gates)
frontend/                     # React 19 + TypeScript monitor dashboard (:8081)
data/                         # Static data (game knowledge, patch manifests, version compat) — see REPO_LAYOUT.md
docs/                         # Specs, plans, reference (this file lives here), archive
../AgenticSTS-Data/            # Sibling: dynamic data (memory, skills, evolution, runs) — see REPO_LAYOUT.md
../AgenticSTS-Mod/            # Sibling: C# mod fork — see REPO_LAYOUT.md
```

## src/ tree

```
mcp_client/
  client.py                 # Async httpx REST client (localhost:8128)
  actions.py                # Action builders — upstream API names (play_card, buy_card, etc.)
  upstream_models.py        # Pydantic models for upstream /state payload
  sse_client.py             # SSE event notifications → triggers state refresh

state/
  game_state.py             # GameState wrapper (frozen Pydantic)
  upstream_game_state.py    # UpstreamStateView convenience wrapper
  state_parser.py           # parse_state() raw JSON → GameState
  run_state.py              # RunState accumulator (decisions/snapshots/run_id; no fitness fn)

brain/
  models.py                 # Shared LLMDecision + DecisionSource
  llm_caller.py             # call_raw() adapter wrapping V2Backend for post-run callers
  planner.py                # CombatPlan: card-name resolution, draw-card detection
  tool_schemas.py           # 6 gameplay tool definitions (5 query + 1 decision per state type)
  batch.py                  # Drain-only Anthropic Batch API (no production submits since 2026-04-23)
  v2_engine.py              # V2Engine: tier-routing decision engine; simple=True forces fast on trivial-hand combat plans
  v2_backend.py             # Multi-provider backend: Anthropic + OpenAI-compatible, streaming, tool routing, 120s timeout, prompt caching
  conversation.py           # CombatConversation: internal _messages accumulator; llm_messages property emits [combat_start, "ok", latest_user_state] only — LLM never sees prior rounds
  tool_executor.py          # Dispatches 5 static query tool handlers (no dynamic fallback)
  dynamic_tools.py          # DynamicToolRegistry: AST-sandboxed agent-authored tools
  write_tools.py            # 5 write-side tool schemas (author_tool, write_skill, update_guide, etc.)
  evolution_engine.py       # Post-run self-evolution: read+write tool-use loop
  evolution_handlers.py     # Per-tool dispatch handlers for write-side actions
  evolution_validators.py   # Validation for skill / tool / guide write requests
  evolution_artifacts.py    # Artifact persistence for evolution outputs
  llm_router.py             # Per-tier provider/model selector
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
    system.py               # 4 primary system prompts (COMBAT/COMBAT_BOSS/DECKBUILD/STRATEGIC) + 4 BASELINE variants for baseline-strict ablation
    bundle.py               # Bundle prompt assembly helper
    crystal_sphere.py       # Crystal Sphere mechanic prompt block
    potion.py               # Type-classified potion decisions (damage/block/buff/heal)
    map.py                  # Map: Scenario A (route selection) + Scenario B (step walking)
    event.py                # 6-factor event scoring framework
    rest.py                 # 5-factor rest scoring (Smith default, relic-aware)
    shop.py                 # Gold-budget-aware shop decisions
    reward.py               # 5-factor card evaluation + act-aware guidance + upcoming-boss hints
    card_select.py          # Deck-coherence-aware tier evaluation (upgrade/remove/enchant)
    hand_select.py          # Mode-aware hand selection (discard vs exhaust)
    treasure.py             # 4-factor relic evaluation
    _relic_fmt.py           # Relic synergy hints (context-filtered, ~100 tokens)
    _intent_fmt.py          # Structured intent parsing (compute_total_incoming)
    _deck_fmt.py            # Deck formatting helper
    _pile_fmt.py            # Conditional draw/discard/exhaust pile formatting
    _target_fmt.py          # Target scope descriptions
    _card_clarifications.py # Card mechanic clarifications for commonly misunderstood cards
    _card_name.py           # Canonical card-name normalization for prompt rendering
    _keyword_fmt.py         # Keyword glossary: scan rules_text → inject concise definitions
    _boss_guide_fmt.py      # Upcoming boss guide injection for reward/shop
    _potion_slot_fmt.py     # Potion-slot decision hint (full-slot swap awareness)
    _regent_economy_fmt.py  # Regent gold/forge economy hints
    _forge_fmt.py           # Forge-aware combat/deckbuild hints
    _generated_fmt.py       # Generated-card prompt formatting helper

runs/
  history.py                # RunRecord + RunHistoryStore (append-only JSONL at runs/history.jsonl)
  ascension_stats.py        # AscensionStats aggregate cache (profile × character × ascension)

skills/
  models.py                 # Skill + SkillTrigger frozen dataclasses; scaffold field + pending_fill status (Mode B)
  library.py                # SkillLibrary: load, query, persist, merge seeds; load_seed_stubs (Mode B); query() skips pending_fill
  composer.py               # Compose retrieved skills into prompt context
  mistake_discovery.py      # Mistake-driven combat skill discovery (sole skill-producing path as of 2026-04-23)
  critic_prompt.py          # LLM critic for mistake review + skill candidate proposal
  prewrite_ab.py            # Pre-write A/B validation (resample B×3, strict 2/3 + zero-harmful)
  lifecycle.py              # Skill confidence update + retirement policy (seeds floored at 0.40)
  noncombat_scorer.py       # Per-run non-combat skill scoring (progress + HP efficiency + cumulative boss-kill bonuses)
  replay_evaluator.py       # Boss replay evaluation (save/quit/continue cycle, kill detection)
  combat_quality.py         # Combat outcome weight for skill confidence updates
  dedup.py                  # Semantic dedup for skill candidates (content_overlap, seed_restatement)
  merge_pipeline.py         # run_merge_pair: LLM merge + dual-anchor A/B validation
  stub_template.py          # Mode B: load + character-substitute seed stub templates
  stub_filler.py            # Mode B: StubFiller orchestrator (postrun stage 5 fill / update; concurrent per-stub LLM calls)
  stub_validators.py        # Mode B: 7 warn-only stub quality checks
  stub_evidence.py          # Mode B: combat replay sampling + non-combat trajectory rendering
  stub_prompts.py           # Mode B: 4-part fill / update prompt assembly
  seeds/
    core_combat.json        # Core combat principles
    core_boss_strategy.json # Boss/elite fight strategy
    core_deck_building.json # Deck building across the run
    core_map_routing.json   # Map routing and path planning
    core_rest_decision.json # Rest site and event decisions
    silent_a10_guide.json   # Silent character Act 1-end guide
    silent_card_notes.json.disabled # (deactivated; Silent card notes now via run-derived guides)
    regent_a10_guide.json   # Regent Act 1-end guide
    regent_card_notes.json  # Regent-specific card tier notes
    regent_starting_deck.json # Regent starting-deck override
  seeds_stubs/              # Mode B: 5 character-parametric stub templates
    combat.template.json
    boss.template.json
    deckbuilding.template.json
    map.template.json
    intermission.template.json

memory/
  models_v2.py              # HCM models: CombatEpisode, RouteMemory, CardBuildMemory, CardMemory, EventMemory, etc.
  short_term.py             # Mutable working memory: combat/route/deck/event trackers + scoped strategic notes (list[StrategicNote])
  combat_store.py           # CombatMemoryStore: CombatEpisode store (enemy_key×character retrieval)
  route_store.py            # RouteMemoryStore: RouteMemory store (act×character retrieval)
  card_build_store.py       # CardBuildMemory store (character×archetype retrieval)
  card_memory_store.py      # Per-card longitudinal memory (character×card_name; base-name keyed: Strike/Strike+/Strike++ share one slot)
  card_memory_extractor.py  # Post-run per-card statistics extraction (no LLM, additive merging)
  card_note_updater.py      # LLM-driven per-card note text refinement (postrun)
  event_models.py           # EventMemory dataclasses (EventOptionSnapshot, RelicReward, CardReward, PotionReward)
  event_extractor.py        # ShortTermMemory → EventMemory extraction
  event_store.py            # EventMemory store (event_id × character retrieval)
  event_guide_consolidator.py # Per-event consolidated guide (LLM, stage-aware knowledge-rich prompt)
  guide_store.py            # Consolidated guides (CombatGuide, RouteGuide, DeckGuide, EventGuide)
  guide_consolidator.py     # episodes → Guide via LLM
  guide_consolidation_log.py # Append-only log of consolidation runs
  retriever.py              # Decision-type-aware unified retrieval → WorkingContext
  combat_extractor.py       # ShortTermMemory → CombatEpisode extraction
  route_extractor.py        # ShortTermMemory → RouteMemory extraction
  card_build_extractor.py   # ShortTermMemory → CardBuildMemory extraction
  combat_trace_renderer.py  # Render combat round trace for postrun prompts
  combat_trace_plan_grouper.py # Group consecutive plan turns within a combat trace
  combat_trace_delta.py     # Delta-formatted combat trace (state diffs only)
  combat_analytics.py       # Cross-run combat statistics aggregator
  enemy_keys.py             # Canonical enemy key derivation
  build_role_memory.py      # Deck-archetype role assignment memory
  deck_build_registry.py    # Cross-run deck archetype registry
  combat_delta.py           # Per-action state diff (HP, block, energy, powers) between snapshots
  situation.py              # Per-round tags: hand_capabilities, damage_taken, outcome_quality
  hint_sanitizer.py         # Drop known-bad legacy deck-guide lines from prompt output
  memory_manager.py         # Unified facade: HCM domain stores + guides
  write_gate.py             # 4-level cascade write gate (exact ID → static cosine → existing-store cosine+Jaccard → LLM batch judge)
  write_gate_judge.py       # LLM batch judge for cascade level 4
  write_gate_lifecycle.py   # Pending-skill lifecycle (defer_to_judge → reap)
  write_gate_ab.py          # Log-grounded skill / memory A/B replay
  write_gate_reap.py        # Reap verdicts: ADD / UPDATE / MERGE / REJECT
  prompt_injector.py        # HCM prompt injection (format_working_context)

knowledge/
  parser.py                 # Markdown table parser for knowledge data files
  card_lookup.py            # Card metadata + behavior + Vars lookup (~577 cards)
  monster_lookup.py         # Monster HP range + move pattern lookup (~121 monsters)
  potion_lookup.py          # Potion metadata + behavior lookup (~64 potions)
  potion_classifier.py      # Potion type classification (damage/block/buff/heal/utility)
  power_lookup.py           # Power/debuff metadata + descriptions
  event_lookup.py           # Event type lookup (~68 events)
  act_lookup.py             # Act metadata (id, name, bosses, encounters) from upstream acts.json
  relic_lookup.py           # Relic metadata (name, description, rarity) from upstream relics.json
  enchantment_lookup.py     # Enchantment metadata from upstream enchantments.json
  encounter_lookup.py       # Fight compositions (room_type, act, monsters) from decompiled source
  keyword_lookup.py         # Keyword definitions from upstream keywords.json
  knowledge.py              # GameKnowledge singleton facade
  injector.py               # KnowledgeInjector: token-budgeted prompt injection
  web_searcher.py           # Claude web search for boss strategy guides

postrun/
  context_builder.py        # Postrun evolution-context renderer (replay + Strategic Thread + per-stub anchors)

storage/
  paths.py                  # Sibling-data-repo path resolver (STS2_DATA_REPO routing)
  postrun_lock.py           # Cross-process file lock for postrun stages
  merge_queue.py            # Merge-driver queue helper for parallel-machine runs

patch/                      # Game-update pipeline (manifest → snapshot → purge → rewrite → version bump)
  manifest.py
  orchestrator.py
  purge.py
  rewrite.py
  snapshot.py
  version.py
  slug.py
  api_coverage.py
  review.py

agent/
  loop.py                   # Core agent loop: observe → decide → act
  state_machine.py          # Phase transition tracking

monitor/
  event_bus.py              # Thread-safe broadcast EventBus (MonitorEvent with run_id)
  server.py                 # FastAPI WebSocket server + REST history + AI summarizer startup
  summarizer.py             # Background Haiku 4.5 summarizer for LLM thinking + combat plans

log/
  session_logger.py         # JSONL structured logging (full state snapshots + EventBus push)

eval/                       # LLM-as-judge decision quality scoring (1-5 rubric)
launcher/                   # Game subprocess launcher (--launch-game / --api-port=auto)
visual/                     # Optional visual capture utilities
cli/                        # CLI helpers
regression/                 # Golden log fingerprint regression harness
```

## Key entry points

- `python -m scripts.run_agent --steps 500 --runs 1` — single run
- `python -m scripts.run_ablation --tag <tag> --runs-per-condition N` — 5-condition ablation (see [`ABLATION.md`](ABLATION.md))
- `python -m scripts.apply_patch --manifest data/patches/v<new>.yaml` — game update pipeline (see [`REPO_LAYOUT.md`](REPO_LAYOUT.md))
- `python -m scripts.inspect_memory` — memory state inspector
- `python -m scripts.sync_upstream_data --game-version v<new>` — refresh `data/knowledge/` from mod
- `python -m scripts.check_mod_api_coverage` — verify mod API ↔ Python state parser coverage

## Key decisions cross-ref

For load-bearing architectural facts that change agent behavior, see CLAUDE.md "Key Decisions" section.
