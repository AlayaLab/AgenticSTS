# Enemy Phase Transition Tracking for Guide Consolidation

**Date**: 2026-04-16
**Status**: Implementing
**Priority**: High — blocks accurate boss mechanic learning

## Problem

Post-run guide consolidation fails to capture boss phase transitions (e.g., Test Subject has 3 phases: kills -> revives with different abilities/max_hp). The resulting guides say vague things like "recurring heavy burst windows" instead of "boss has 3 phases, revives after death with new abilities."

### Root Cause Analysis

1. **Data model gap**: `CombatRound` stores `enemy_powers_snapshot` (per-round powers) but NOT enemy HP/max_hp. When a boss revives with max_hp 100->300, this change is invisible in stored data.

2. **Formatting gap**: `_format_combat_episodes()` in `guide_consolidator.py` gives the LLM only aggregate stats (win/loss, HP delta, top cards) for most episodes. Enemy state data is only included for the last 3 episodes via `format_analytics()`, and even then it's just a power timeline -- not explicit phase transition markers.

**Result**: The LLM literally cannot see phase transitions in the data it receives.

### Evidence

From log `run_20260416_085553_b70f8b05.jsonl` (Test Subject fight):
- Round 1: enemy powers `Adaptable(1), Enrage(2)`, max_hp=100
- Phase 2: powers change to `Nemesis(1), Intangible(1)`, max_hp=300
- The game state clearly shows `Adaptable: When this creature would be defeated, it instead revives even stronger.`
- But guide consolidation output only sees: `[WIN] 12 rounds, HP 82->55 (-27), cards: Defend, Shiv...`

## Solution: 5 Changes across 5 files

### Change 1: `src/memory/models_v2.py` — Add `enemy_hp_snapshot` field to CombatRound
### Change 2: `src/memory/short_term.py` — Add field to tracker + STM parameter
### Change 3: `src/memory/combat_extractor.py` — Copy field in frozen conversion
### Change 4: `src/agent/loop.py` — Capture enemy HP from game state (uses `e.current_hp`, `e.max_hp`)
### Change 5: `src/memory/guide_consolidator.py` — Add `_detect_phase_transitions()` + surface for ALL episodes

## Expected Output

After these changes, guide consolidation will receive:
```
Enemy phase transitions:
  R5: Test Subject max_hp changed 100->300
  R5: TEST_SUBJECT lost Adaptable(1), Enrage(2); gained Nemesis(1), Intangible(1)
  R9: Test Subject max_hp changed 300->200
  R9: TEST_SUBJECT lost Nemesis(1); gained Fury(3)
```

## Files Modified

| File | Change | Risk |
|------|--------|------|
| `src/memory/models_v2.py` | Add `enemy_hp_snapshot` field | Low — additive, backward compatible |
| `src/memory/short_term.py` | Add field + parameter | Low — additive |
| `src/memory/combat_extractor.py` | Copy field in frozen conversion | Low — additive |
| `src/agent/loop.py` | Capture enemy HP from game state | Low — read-only from existing data |
| `src/memory/guide_consolidator.py` | Add phase detection + formatting | Low — additive to prompt |
