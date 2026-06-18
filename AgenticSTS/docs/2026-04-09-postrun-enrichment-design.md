# Post-Run Pipeline Enrichment — Full Spec

> **PARTIALLY SUPERSEDED (2026-04-18).** Sections related to the `propose_prompt_edit` / `PromptPatchStore` / `PromptPatchApplier` / `PromptABTester` pipeline are historical only — the pipeline was removed after 33/33 A/B validation failures. See `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`. Memory / guide / skill / dynamic-tool sections of this spec remain current.

**Date:** 2026-04-09
**Status:** Draft (prompt-evolution sections superseded)
**Goal:** Maximize the learning output of each run by enriching all post-run pipeline components with sufficient context, fixing broken infrastructure (compact profile, counters, retry, telemetry), and targeting ~70-90k input tokens per post-run cycle.

## Problem Statement

Post-run self-evolution is the most important phase of each run — the entire gameplay phase exists to generate data for this learning cycle. Currently:

1. **Evolution context starved**: Hardcoded `compact` profile produces ~2,700 chars (~700 tokens). Evolution sees 1 combat replay (3 rounds), no rules, no guides, no card memories.
2. **Periodic steps gated by high counters**: Guide consolidation (every 5 runs), skill discovery (every 3 runs), rule distillation (every 5 runs). Most runs only execute evolution + build analysis.
3. **Evolution retry fragile**: Single inline retry then silent abort. Gameplay gets infinite retry.
4. **Post-run LLM calls invisible**: Not logged to JSONL. Cannot monitor token usage or diagnose failures.
5. **Skill discovery sees 15 decisions**: Out of 800+ per run. Only last combat card plays, missing all shop/event/map/reward decisions.
6. **No historical comparison**: Evolution doesn't know if this run's combat results are better or worse than average.

## Design Overview

### A. Evolution Engine Context Enrichment

Replace the `compact`/`full` profile system with a single rich context builder. Remove `context_profile` parameter entirely.

#### A1. Smart Combat Selection (no fixed cap)

**Selection rules (all matching combats included):**
- All boss combats (mandatory)
- All elite combats (mandatory)
- Death combat (mandatory)
- Anomalous worse: z-score > 1.5 vs historical avg for that enemy (requires 3+ historical episodes, std > 0)
- Anomalous better: z-score < -1.0 AND historical avg loss > 5 (skip if enemy is trivially easy)

**Per combat includes:**
- `format_analytics()` output (card damage, poison, death cause, enemy timeline, card descriptions)
- Historical comparison line: `"loss=22 vs historical avg=37.5+/-13.8 (z=-1.1, BETTER_THAN_USUAL)"`
- Full rounds (no round cap — the analytics already summarizes, raw rounds give sequence detail)

**Typical count:** 3-8 combats per run. Token estimate: ~500 tokens/combat = ~1,500-4,000 tokens.

#### A2. Combat Guides for Encountered Enemies

Inject the full guide text for every enemy encountered this run that has an existing guide.

```
## Existing Combat Guides (enemies encountered this run)
[Guide: Vantom] WR=92%, 13 episodes, confidence=0.85, v12
  - Block first on multi-hit turns, then chip damage with leftover energy...

[Guide: Knowledge Demon] WR=33%, 15 episodes, confidence=0.80, v8
  - Prioritize Weak on attack turns...
```

This lets evolution evaluate and update guides it previously wrote. Typical: 3-5 guides at ~150 tokens each = ~500-750 tokens.

#### A3. All Strategy Rules

Inject all 50 strategy rules (not just top 5). Let evolution identify outdated, contradicted, or missing rules.

```
## Strategy Rules (50 rules)
1. [id=3926bf4f, conf=0.85] "Prepare for multi-enemy fights by floor 15+..."
2. [id=f7ba934e, conf=0.80] "If a combat takes more than 7 rounds as Silent..."
...
```

~50 rules x ~30 tokens = ~1,500 tokens.

#### A4. Triggered Skills + Outcomes

Record which skills were triggered during gameplay and what happened. Inject a summary.

```
## Skills Triggered This Run
- "Boss and Elite Fight Strategy" → triggered at F17(Vantom: WIN, loss=2), F33(Knowledge Demon: WIN, loss=22)
- "Core Combat Principles" → triggered 12 times, 10 clean wins, 2 high-loss
- "Silent A10 Combat Sequencing" → triggered at F48(Test Subject: DEATH)
```

Typical: 5-10 triggered skills x ~50 tokens = ~250-500 tokens.

**Implementation:** The skill trigger mechanism already exists. We need a lightweight accumulator in the agent loop that records `(skill_name, floor, enemy, result)` tuples, then formats them in `build_evolution_context`.

#### A5. Card Memories for Deck Cards

Inject card memory notes for cards that were in this run's deck.

```
## Card Notes (this run's deck)
- Blade Dance: "Efficient early damage via Shivs, exhausts — limited boss value"
- Footwork+: "Core defensive scaling, prioritize in Act 1-2"
- Deadly Poison: "Strong poison applicator, 5 stacks per play"
```

~25 cards x ~30 tokens = ~750 tokens.

#### A6. Dynamic Tools + Execution Stats

Inject tool names, brief description, and this run's execution stats.

```
## Dynamic Tools (5 active)
- block_sufficiency_check: 45 calls, all ok
- poison_kill_and_survive_check: 12 calls, all ok
- poison_survival_analysis: 8 calls, all ok
- poison_block_survival_plan: 3 calls, all ok
- poison_turns_to_kill: 6 calls, all ok
```

~5 tools x ~50 tokens = ~250 tokens.

#### A7. Pending Prompt Proposals

Show recent unresolved prompt edit proposals so evolution can follow up or refine.

```
## Pending Prompt Proposals (5 most recent of 21)
- combat_plan: "On lethal-pressure turns, lock survival line before setup..."
- shop_decision: "Factor remaining path length into gold budgeting..."
```

~5 proposals x ~40 tokens = ~200 tokens.

#### A8. Evolution Context Token Budget

| Section | Tokens |
|---------|--------|
| A1. Combat analytics (3-8 fights) | ~3,000 |
| A2. Enemy combat guides | ~600 |
| A3. All strategy rules | ~1,500 |
| A4. Triggered skills | ~400 |
| A5. Card memories | ~750 |
| A6. Dynamic tools | ~250 |
| A7. Prompt proposals | ~200 |
| Existing sections (run summary, decisions, focus) | ~1,000 |
| System prompt + tool schemas | ~2,850 |
| **First round context** | **~10,550** |
| **Multi-turn cumulative (4 rounds)** | **~38,000-42,000** |

---

### B. Skill Discovery Decision Enrichment

Replace the current "last 15 decisions" with full-run decision coverage in compressed format.

#### B1. Full Decision Sampling

Include ALL decisions from the run. Combat decisions compressed into round summaries; non-combat decisions retain full reasoning.

**Combat format (compressed):**
```
F22 [monster] The Obscura (7R, HP 68->47, loss=21)
  R1[Buff]: Acrobatics+->Footwork+->Blade Dance->Shiv*3 | dealt=40 taken=0
  R2[Atk 12x2]: Defend->Defend->Pinpoint | dealt=20 taken=8
  R3[Atk 28]: Defend->Backflip+->Neutralize+ | dealt=6 taken=10
  ...
```

**Non-combat format (full reasoning):**
```
F15 [shop] HP=57 Gold=280->130 Deck=18
  Buy Footwork+ (150g) | "Core defensive scaling, must-buy at this price"
F16 [event] HP=57 Gold=130 Deck=18
  Choose option 2: Take 333 Gold + Curse | "Economic advantage, remove curse at shop"
F18 [map] HP=57 Gold=463 Deck=19
  Choose elite path | "Need card reward, HP is healthy"
F20 [card_reward] HP=57 Gold=463 Deck=20
  Take Deadly Poison, skip Blade Dance | "Poison scaling > exhaust token for boss"
```

**State changes:** Each decision includes HP, Gold, Deck size. Combat summaries show HP before/after.

**Token estimate:** ~830 decisions compressed to ~18,000 tokens (combat rounds ~12k, non-combat ~6k).

---

### C. Guide Consolidation Enhancement

#### C1. Increase Episode Window

Change `episodes[-5:]` to `episodes[-15:]` in `_format_combat_episodes`. More statistical data for pattern detection.

+500 tokens per consolidation call.

---

### D. Infrastructure Fixes

#### D1. Remove compact/full Profile System

Delete the `context_profile` parameter from `build_evolution_context()` and `_post_run_evolution()`. Single rich context always.

#### D2. All Counters to 1

```python
CONSOLIDATION_EVERY_N_RUNS = 1  # was 5
DISTILL_EVERY_N_RUNS = 1        # was 5
SKILLS_DISCOVERY_EVERY_N_RUNS = 1  # was 3
```

Every run triggers every post-run step.

#### D3. Evolution Retry-Forever

Replace the single inline retry with retry-forever logic matching gameplay:
- Exponential backoff: 3s base, 30s max
- Retry on: 502, 503, 504, 524, timeout, connection error
- Break only on: 400 (schema/validation) — won't self-heal
- Log each retry attempt

#### D4. Evolution Model Fallback

When the primary model (`gpt-5.4`) fails after N retries on the same relay, try fallback model names:

```python
EVOLUTION_FALLBACK_MODELS = ["gpt-5.4-thinking", "gpt-5.4-high"]
```

Implementation: after 3 consecutive failures on the primary model, cycle to the next fallback model and retry. This handles relay routing issues where one model name doesn't work but another does.

The fallback list is configurable via `STS2_EVOLUTION_FALLBACK_MODELS` env var (comma-separated).

#### D5. Evolution Telemetry in JSONL

Add a new `log_evolution_round()` method to `SessionLogger`. Called after each evolution round with:

```json
{
  "event": "evolution_round",
  "run_id": "...",
  "round": 1,
  "model": "gpt-5.4",
  "provider": "openai_compatible",
  "relay": "proxy.example.com",
  "input_tokens": 3850,
  "output_tokens": 1200,
  "thinking_tokens": 800,
  "tool_calls": 2,
  "tool_names": ["get_performance_stats", "write_skill"],
  "stop_reason": "tool_use",
  "latency_ms": 12500,
  "error": null
}
```

Also log evolution start/end summary:
```json
{
  "event": "evolution_summary",
  "run_id": "...",
  "total_rounds": 4,
  "total_input_tokens": 19350,
  "total_output_tokens": 4800,
  "actions_taken": 3,
  "action_types": ["write_skill", "update_guide", "propose_prompt_edit"],
  "model": "gpt-5.4",
  "fallbacks_used": 0,
  "duration_ms": 45000
}
```

This requires passing the `SessionLogger` instance to `EvolutionEngine` (similar to how V2Engine gets it).

#### D6. Post-Run LLM Telemetry for Other Steps

`call_raw()` in `llm_caller.py` is used by guide consolidation, skill discovery, rule distillation, build analysis. It currently does not log to JSONL.

Add optional `session_logger` parameter to `call_raw()`. When provided, log each call:
```json
{
  "event": "postrun_llm_call",
  "call_type": "guide_consolidation",
  "model": "gpt-5.4",
  "input_tokens": 2000,
  "output_tokens": 800,
  "latency_ms": 8500
}
```

---

### E. Token Budget Summary

| Component | Before | After | Notes |
|-----------|--------|-------|-------|
| Evolution Engine | 20,000 | ~40,000 | Rich context + multi-turn |
| Skill Discovery | 1,200 | ~18,000 | Full decisions compressed |
| Guide Consolidation | 5,000 | ~8,000 | 15 episodes + analytics |
| Cohort Discovery | 6,300 | 6,300 | Unchanged |
| Rule Distillation | 1,300 | 1,300 | Unchanged |
| Build Analysis | 1,200 | 1,200 | Unchanged |
| **Total** | **~35,000** | **~75,000** | Target: 70-90k |

---

## Files Changed

| File | Change |
|------|--------|
| `src/brain/evolution_engine.py` | Rich context builder (A1-A7), retry-forever (D3), model fallback (D4), telemetry hooks (D5) |
| `src/agent/loop.py` | Remove `context_profile`, pass session_logger to evolution, skill trigger accumulator (A4) |
| `src/skills/discovery.py` | Full decision sampling with compression (B1) |
| `src/memory/guide_consolidator.py` | 15 episodes (C1) |
| `src/log/session_logger.py` | `log_evolution_round()`, `log_evolution_summary()`, `log_postrun_llm_call()` (D5, D6) |
| `src/brain/llm_caller.py` | Optional session_logger for telemetry (D6) |
| `config.py` | Counters to 1 (D2), `EVOLUTION_FALLBACK_MODELS` (D4) |
| `src/memory/combat_analytics.py` | Add `historical_comparison()` function for z-score annotation (A1) |

## Backward Compatibility

- Old episodes: analytics gracefully degrades (no source_description/enemy_powers_snapshot)
- Counter changes: no data impact, just frequency
- Telemetry: additive (new event types in JSONL, old parsers ignore them)
- Fallback models: only tried after primary fails, no impact on happy path

## Testing

1. Run `verify_analytics_from_log.py` on recent logs to confirm analytics output quality
2. Run one live game with all changes, inspect JSONL for evolution telemetry
3. Verify post-run token usage matches ~75k estimate via new telemetry
4. Confirm all 6 post-run steps execute (check JSONL events)
5. Test model fallback by temporarily setting primary to a non-existent model name
