# Development Phases (Archive)

Archived from CLAUDE.md on 2026-04-05.

- [x] Phase 1: MCP Client (models, client, actions, state parser)
- [x] Phase 2: LLM Brain (V2Engine, prompts, agent loop)
- [x] Phase 3: Skill Library (5 core seeds + discovered/evolved skills, 5 characters)
- [x] Phase 4: Memory System (HCM domain stores: combat, route, card build, rules, guides)
- [x] Phase 4b: HCM Memory — extractors wired, stores accumulating
- [x] Phase 4c: Prompt rewrite — all 11 prompts with multi-factor frameworks + relic synergy
- [x] Phase 5 (HCM): Guide consolidation pipeline (episode → Guide via LLM)
- [x] Claude API migration Phase 1: model routing + extended thinking + prompt caching
- [x] Claude API Phase 2: tool_use for structured output (12 tools, eliminate JSON parsing failures)
- [x] Claude API Phase 3: Batch API for post-run analysis (reflection/distillation/discovery, 50% savings)
- [x] Pre-boss web search: background fetch at COMBAT_START + format_boss_strategy()
- [x] Memory system bug fixes: 6 disconnected hooks wired + damage_taken tracking
- [x] MCP migration: CharTyr/STS2-Agent v0.5.2+ upstream models, no translation layer, upstream action names
- [x] rules_text resolution: C# GetDescriptionForPile + NormalizeCardRulesText, templates fully resolved
- [x] Target damage previews: DynamicVarPreview per target, CalculatedDamageVar for Vulnerable-aware damage
- [x] Structured card previews: card-level damage/block/hits/total_damage + enhanced target_previews with hits
- [x] V2 Prompt Architecture: multi-turn combat + tool-use agent + 5 query tools + prompt caching
- [x] V2 bug fixes: V1 residue removal, empty response retry, single-card confirm, energy_used
- [x] Monitor Dashboard: React frontend with WebSocket streaming, run_id on SSE envelope, 13 event types
- [x] Monitor AI Summary: Haiku 4.5 background summarizer for LLM thinking + combat plans
- [x] Route Planning Fix: coords in route plan, map prompt recommends exact next node
- [x] Query Tool Cleanup: removed lookup_card + lookup_enemy (info in prompt), structured combat intent recording
- [x] P0-A: Combat context coherence (strategic notes, discard matching, enemy-death re-plan)
- [x] P0-B: Hardcoded removal (35 threshold values replaced with dynamic context)
- [x] P1: Potion timing (potion_classifier.py, assess_potion_value tool, timing tags)
- [x] P1-partial: Relic descriptions in prompts (combat + non-combat) + re-plan thinking fix
- [x] P3: Rest route vision (full remaining path injected into rest prompts)
- [x] P4: Skill lifecycle (dedup, retirement, exploration bonus, noncombat scoring, boss replay eval)
- [x] P5: Broken tools fixed (33/33 dynamic tools loading, 8 test cases corrected)
- [x] System prompt optimization (6461→3869 chars, -40%, status effects moved to dynamic context)
- [x] System prompt split: 4 variants (COMBAT/COMBAT_BOSS/DECKBUILD/STRATEGIC) by state_type
- [x] Treasure auto-shortcut: always mechanical (only ever 1 relic), saves ~7500 tokens/run
- [x] Conditional pile injection (draw/discard/exhaust only shown when hand cards reference them)
- [x] P6-A: Combat prompt optimization (-34% combat tokens)
- [x] P6-B: Non-combat prompt optimization (V1 dead code removal, skill generation 400-char limit)
- [x] P7: Strategic Thread — run-level decision coherence via strategic_note in tool schemas
- [x] P2a: Self-evolution Phase 1 — DynamicToolRegistry + EvolutionEngine + 5 write tools + pipeline fixes
- [x] P2a+: Architecture layering — gameplay surface cleanup, three-stage dispatch, schema normalization, ToolPreprocessor
- [x] V1 removal: brain + memory V2-only migration (reasoner, strategy_selector, V1 stores deleted)
- [x] P8: Archetype → Skill-driven deck intelligence (remove ArchetypeTracker, add build plan in strategic thread)
- [x] P9: Route plan refactor — annotation-based multi-key sort, condition-triggered re-plan, dual-scenario map prompts

## Active / Pending
- [ ] P1-remaining: Card upgrade comparison at Smith
- [ ] P1.5: Multi-LLM provider support — OpenAIToolBackend for GPT-5.4/Gemini 3.1 Pro/Qwen 3.5
- [ ] P2b: Self-evolution Phase 2 — validation runs (10-20 games), prompt tuning, tool creation verification
- [ ] Phase 5 (NeurIPS): Evaluation framework — win rate tracking, floor progress, skill evolution metrics
- [ ] Phase 6: CLI + polish
