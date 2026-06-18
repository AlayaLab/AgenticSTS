# Split Past Experience from Combat Guide

## Spec

### Problem
Past Experience 和 Combat Guide 职责混淆。Past Experience 应该只描述敌人机制/战斗结构（"这个怪会做什么"），Combat Guide 只描述战术应对（"你应该怎么打"）。当前代码已有 `mechanic_summary` 字段和 consolidation prompt 的区分，但注入层存在 fallback 混用和 header 不一致。

### Goal
- Past Experience = `mechanic_summary` only — 敌人机制/战斗结构
- Combat Guide = `guide_text` only — 战术应对建议
- 两者都在 combat start (R1) 注入到 strategic_context
- Enemy Intel (round-by-round patterns) 保持现状不变

### Out of Scope
- Rules / rule triggers / A/B promotion
- Combat Guide 内容质量调整
- enemy_pattern_injector.py (round-by-round 序列、Likely upcoming) 保持现状

---

## Plan

### Step 1: Stale guide reconsolidation gate
**File:** `src/memory/guide_consolidator.py`
**Line ~550**

Current skip logic:
```python
if existing and existing.episode_count >= len(episodes):
    continue
```

Add: if `existing.mechanic_summary` is empty, don't skip — force reconsolidation even if episode_count matches.

```python
if existing and existing.episode_count >= len(episodes) and existing.mechanic_summary:
    continue
```

### Step 2: Remove key_patterns fallback in retriever
**File:** `src/memory/retriever.py`
**Line ~373**

Current:
```python
mechanic_summary = guide.mechanic_summary or guide.key_patterns
```

Change to:
```python
mechanic_summary = guide.mechanic_summary
```

This ensures Past Experience only contains fight-structure mechanics, never tactical patterns from `key_patterns`.

### Step 3: Unify prompt_injector headers
**File:** `src/memory/prompt_injector.py`
**Lines ~31-61**

Current `situation_hints` renders as `## Fight Mechanics`. Rename to `## Past Experience` for label consistency. The `combat_guide_hints` section stays as `## Enemy Intel`.

Change:
```python
parts.append("## Fight Mechanics")
parts.append("*Overall fight structure, backed by repeated readable past fights.*\n")
```
To:
```python
parts.append("## Past Experience")
parts.append("*Enemy mechanics and fight structure from past encounters.*\n")
```

### Step 4: Strengthen consolidation prompt constraints (optional, soft)
**File:** `src/memory/guide_consolidator.py`
**Lines ~179-191**

Add explicit forbidden-content constraints to the consolidation prompt for `mechanic_summary`:

```
- mechanic_summary MUST NOT contain: card names, "play/use/hold/prioritize" advice,
  current-turn intent commentary, or next-turn predictions.
- mechanic_summary describes only: phase order, add/summon relationships,
  recurring punish windows, death timers, transformation/reset rules.
```

This is a soft constraint (LLM may not perfectly obey) but sets the right direction.

---

## Test Plan

1. **Stale reconsolidation**: Load a guide with empty `mechanic_summary` and `episode_count >= len(episodes)` — verify it gets reconsolidated.
2. **No key_patterns fallback**: Guide with empty `mechanic_summary` but non-empty `key_patterns` — verify `situation_hints` is empty (not falling back).
3. **Header naming**: Verify prompt output contains `## Past Experience` (not `## Fight Mechanics`) when `situation_hints` is present.
4. **R1 injection**: Verify Past Experience appears at round 1 (existing gate is `current_round >= 1`, already satisfied).
5. **Combat Guide unchanged**: Verify `## Enemy Intel` section still contains `combat_guide_hints` with guide_text content.
6. **Enemy patterns unchanged**: Verify `enemy_pattern_hints` still renders in `## Enemy Intel` with round-by-round sequences.

## Files Changed

| File | Change |
|------|--------|
| `src/memory/guide_consolidator.py` | +1 line stale check, +2 lines prompt constraint |
| `src/memory/retriever.py` | -1 line (remove `or guide.key_patterns`) |
| `src/memory/prompt_injector.py` | Rename header `Fight Mechanics` → `Past Experience` |
| `tests/test_*` | Regression tests for above |
