# Energy Soft Warning: Cost-Changing Card Tolerance

**Date**: 2026-04-03
**Status**: Approved
**Scope**: `loop.py` (_validate_combat_plan, _generate_combat_plan), `conversation.py`

## Problem

Cards like Bullet Time (3E, makes all hand cards cost 0) break the energy order validator. The validator sees subsequent cards' original cost exceeding remaining energy and hard-rejects the plan. The LLM then replans without the cost-changing sequence, producing strictly worse plans.

Root cause: `_card_changes_energy()` regex only matches "gain energy" patterns, not "change card costs" effects. Writing a unified detector for all cost-changing cards (Bullet Time, Madness, etc.) is infeasible — their rules_text varies too widely.

**Impact**: In run 324af558f2a4, Bullet Time plans were rejected 14 times out of 19 attempts, forcing the agent into suboptimal play throughout Act 1 and contributing to death at the Act 1 boss.

## Solution

Replace hard rejection with a **soft warning + LLM self-check** when energy validation fails. The LLM knows whether a preceding card changes costs; let it confirm or revise.

### Return Type Convention

`_validate_combat_plan()` returns `str | None` (unchanged type signature):
- `None` → plan is valid
- String starting with `"ENERGY_CHECK:"` → soft warning (energy uncertainty)
- Any other string → hard error (card not in hand, count mismatch)

### Validation Changes (`_validate_combat_plan`)

1. Add `skip_energy_check: bool = False` parameter
2. Card existence check (first pass) → unchanged, always hard errors
3. Energy order check (second pass):
   - When `skip_energy_check=True` → skip entirely, return None
   - When `fixed_cost > current_energy` → return `ENERGY_CHECK:` prefixed warning instead of hard error

### Caller Changes (`_generate_combat_plan`)

```
validation_error = _validate_combat_plan(plan, gs)
if error:
    is_soft = error.startswith("ENERGY_CHECK:")
    if soft → conversation.add_energy_check(error)   # gentle prompt
    else   → conversation.add_validation_error(error) # hard correction

    replan via generate_combat_plan(is_replan=True)

    if new plan exists:
        re-validate with skip_energy_check=is_soft
        (soft: trust LLM, skip energy; hard: full re-validation)
```

### Conversation Message (`add_energy_check`)

Gentle prompt that allows the LLM to confirm its plan:

> **Energy Sequence Check**
> {warning details}
>
> If a preceding card changes costs of subsequent cards (e.g. Bullet Time
> makes all hand cards cost 0), your plan is correct — regenerate the SAME
> plan unchanged. Otherwise, revise your plan to fit within the energy budget.

Key difference from `add_validation_error`: does NOT say "Invalid plan" or "Generate a corrected plan". Allows confirmation.

## Files Changed

| File | Change |
|------|--------|
| `src/agent/loop.py` | `_validate_combat_plan`: add `skip_energy_check` param, return `ENERGY_CHECK:` prefix for energy failures |
| `src/agent/loop.py` | `_generate_combat_plan`: distinguish soft/hard, skip energy re-check on soft retry |
| `src/brain/conversation.py` | New `add_energy_check()` method |

## Design Decisions

- **No cost-changing card detection**: entirely LLM-driven judgment. Avoids fragile regex.
- **skip_energy_check on retry**: prevents infinite loop (same plan → same warning → same replan).
- **Zero extra API calls**: reuses existing `generate_combat_plan(is_replan=True)` path.
- **Backward compatible**: hard errors (card not in hand) behavior unchanged.
