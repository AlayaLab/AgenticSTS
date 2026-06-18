# Detailed Technical Decisions (Archive)

Archived from CLAUDE.md on 2026-04-05. See CLAUDE.md Key Decisions for the condensed version.

> **Note (2026-04-18):** Any references below to `propose_prompt_edit` / `PromptPatchStore` / `PromptPatchApplier` / `PromptABTester` describe a pipeline that was removed after 33/33 A/B validation failures. See `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`.

## LLM Model Routing
- **Fast tier** (Sonnet 4.6): combat single-card, potions — low effort, no thinking
- **Strategic tier** (Sonnet 4.6): map/rest/shop/event/reward/card_select + combat plans — effort=medium, streaming thinking
- **Analysis tier** (Opus 4.6): post-run reflection, rule distillation, guide consolidation, skill discovery — effort=high
- **Evolution tier** (Opus 4.6): post-run self-evolution (author tools/skills) — effort=high, independent config
- Gameplay uses Sonnet (~200-400 calls/run), post-run uses Opus (<10 calls/run)
- Thinking: DISABLED for fast tier. ENABLED for strategic tier via streaming (`messages.stream().get_final_message()`) — bypasses proxy.example.com proxy block stripping.
- Proxy workaround: proxy.example.com non-streaming aggregation drops non-first content blocks. Streaming preserves all blocks (thinking + text + tool_use). Verified empirically.
- `call_raw` (non-streaming, no tools) still strips proxy-injected `<thinking>` tags from text responses
- Extended thinking: adaptive mode with `output_config.effort` (4.6+) for text-only calls
- Prompt caching: system prompt cached via `cache_control: {"type": "ephemeral"}` (90% input savings)

## Prompt Design
- All prompts use explicit scoring rubrics (not vague guidelines)
- 4 system prompts: COMBAT (HP conservation), COMBAT_BOSS (all-out win), DECKBUILD (4-dim card eval), STRATEGIC (run-wide resource)
- `get_system_prompt(state_type)` auto-selects; combat conversation uses cached map node type for boss detection
- Rest: 5-factor scoring (-2 to +2) with "Smith is default" conviction + relic-awareness
- Card select: Build-plan-aware tier evaluation (win condition + gaps + avoid)
- Potion: Type-classified (damage/block/buff/heal) with per-type guidance
- Relic synergy: 35 relics with context-filtered hints injected into rest/map/shop prompts
- Relic descriptions from MCP state (`RawRunRelicPayload.description`) injected into prompts
- `_cached_relics` stores `"Name (description)"` format, BBCode stripped via `strip_bbcode()`

## Skills
- 5 core seed skills: hand-authored expert STS2 knowledge (combat, boss, deck, map, rest/event)
- 2 character-specific seeds: silent_a10_guide.json, silent_card_notes.json
- Combo/synergy skills are discovered post-run, not seeded — skill library grows from gameplay experience
- Context-aware retrieval: SkillTrigger matches state_type, enemy, HP, cards, act
- Overlap-weighted scoring: `1.5 + 0.5*(N-1)` bonus for requires_cards overlap (N matched cards)
- Token-budgeted prompt injection (max 600 tokens, priority by relevance × confidence)
- Confidence tracking: Laplace-smoothed success rate with seed-blend warmup
- Noncombat scoring: quality_score from compute_noncombat_score (progress + HP efficiency)
- Exploration bonus: +5.0 for usage_count==0 to ensure untested skills get tried
- Retirement sweep: deactivate low-confidence skills, delete after 3 runs inactive
- Category caps: MAX_ACTIVE_PER_CATEGORY=15, slot quotas (max 3 seeds, min 2 non-seed per prompt)

## Strategic Thread
- Every non-combat decision tool has optional `strategic_note` field (combat uses `note_to_future_self`)
- Notes stored in ShortTermMemory._strategic_thread (max 10, last 5 injected into prompts)
- Injected as `## Strategic Thread` in all prompts (replaces old `## Current Progress` factual summaries)
- Combat conversation init receives full thread for deck-building context awareness
- System prompt guides LLM to frame notes as running build plans: win condition + key pieces + gaps + avoid (50-word limit)
- Zero additional API calls — extracted from existing decision tool responses

## Combat Planning
- LLM generates full-turn plan in one call (vs 3-5 single-card calls)
- Plan items can be `type=card` or `type=potion` — potions planned inline with cards
- Combat plans use **strategic tier** (Sonnet + thinking) for quality — called once per round
- Single-card fallback uses **fast tier** (Haiku, no thinking) for speed
- Card names (not indices) in plans — resolved to indices at execution time
- Draw-card splitting: cards that draw/add to hand discard remaining plan, trigger re-plan
- Re-plans use **strategic model + low effort thinking** (budget=2000)
- Dynamic threat-level guidance: LETHAL/HEAVY/SAFE turns get different planning instructions

## Game Knowledge Database
- Parsed from decompiled STS2 source (577 cards, 121 monsters, 64 potions, 68 events)
- Card mechanics: OnPlay/OnUpgrade/Vars (damage/block values) injected inline
- Monster patterns: move states + passives + HP range injected with enemy info
- Separate token budgets: cards (1600 chars/~400 tokens), monsters (800 chars/~200), potions (600 chars/~150)
- O(1) lookup by name (case-insensitive), loaded once at startup
- Additional knowledge: acts, relics, enchantments, encounters, keywords (from upstream JSON files)

## Self-Evolution Architecture
- `DynamicToolRegistry`: loads `.py` files from `data/evolution/tools/`, AST sandbox validation
- AST whitelist: only `math`, `collections`, `itertools`, `functools` imports allowed
- Restricted builtins: no `open`, `exec`, `eval`, `os`, `sys`, `subprocess`, `__` dunder access
- Tool file format: `SCHEMA` dict + `execute()` function + `TEST_CASES` list
- `EvolutionEngine`: independent sync tool-use loop (Opus 4.6 + effort=high)
  - Three-stage dispatch: write tools → static query tools (ToolExecutor) → dynamic tools (DynamicToolRegistry)
  - 5 write tools: `author_tool`, `write_skill`, `update_guide`, `propose_prompt_edit`, `get_performance_stats`
- **Architecture separation**: Gameplay API = 6 tools (5 static query + 1 decision) — dynamic tools NOT in live API
- **Schema normalization**: `get_param_info()`, `get_normalized_schema()` — handles 3 SCHEMA formats
- **Runtime classification**: `classify_tool_runtime_mode()` → `state_derived` | `plan_evaluator`
  - AUTO_BINDABLE params (HP, block, energy, deck, enemies, etc.) → state_derived
  - Plan-dependent params (planned_block, card_to_remove, etc.) → plan_evaluator
- **ToolPreprocessor**: runs state-derived tools before LLM calls, hints as `## Computed Insights`
- **PlanVerifier**: runs plan_evaluator tools post-combat-plan, severity "critical" → needs_replan=True
- **StateSnapshotStore**: ring-buffer capture of real GameState snapshots for tool validation

## Memory (HCM)
- Short-term memory: mutable combat/route/deck trackers within a run
- Domain stores: CombatMemoryStore, RouteMemoryStore, CardBuildStore, CardMemoryStore (per-card longitudinal)
- Extractors called at post-run: finalize in-progress combat/route → extract → save
- Decision-type-aware retrieval: per-type token budgets (combat 300, route 250, deck 200, rest 150)
- **Guide consolidation**: episodes → LLM → CombatGuide/RouteGuide/DeckGuide
  - Runs every CONSOLIDATION_EVERY_N_RUNS (5), requires CONSOLIDATION_MIN_EPISODES (3) per group
  - Groups by: enemy_key×character (combat), act×character (route), character×archetype (deck)
  - Guides are versioned, incrementally updated, persisted to `guides.json`

## Cohort-Based Skill Discovery
- `cohort_discovery.py`: clusters low-loss combat episodes by enemy×deck-stage, LLM extracts skills from each cohort
- `hypothesis_store.py`: candidate skills re-evaluated each post-run (corroborate/contradict/auto-promote/expire)
- `evidence.py`: RoundExemplar collection + scoring for skill candidates
- `situation.py`: per-round tags (threat level, intent class, hand capabilities, deck stage) — zero API calls
- Replaces simple post-run discovery with evidence-gated lifecycle

## MCP API Contract
- CharTyr STS2-Agent v0.5.2+ REST at localhost:8080
- Endpoints: `GET /health`, `GET /state`, `POST /action`, `GET /events/stream`
- Response envelope: `{ok, request_id, data}` — client unwraps `data`
- Actions use upstream names directly: `play_card`, `end_turn`, `buy_card`, `choose_reward_card`, `proceed`, etc.
- Shop flow: `open_shop_inventory` → `buy_card`/`buy_relic`/`buy_potion` → `close_shop_inventory` → `proceed`
- Game session: `save_and_quit` (during any active run), `continue_run` (from main menu with saved run)
- `available_actions`: lists possible action *types*, NOT currently executable actions — always check `can_proceed`, `is_enabled`

## Multi-LLM Provider Adaptation Plan (Pending — P1.5)
Goal: Add OpenAIToolBackend for GPT-5.4, Gemini 3.1 Pro, Qwen 3.5 via OpenAI-compatible endpoints.
Provider matrix, implementation steps, and why not LiteLLM: see CLAUDE.md as of 2026-03-28.
