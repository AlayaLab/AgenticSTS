# P6-B: Non-Combat Prompt Token Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce non-combat LLM call tokens and complete deferred P6-A items. Based on actual log analysis (236 calls from a full run).

**Architecture:** Formatting-only changes + dead V1 code removal. No new files, no architecture changes.

**Tech Stack:** Python 3.11, pytest, Anthropic Messages API

**Spec:** `docs/superpowers/specs/2026-03-27-prompt-token-optimization-design.md`

---

## Actual Token Distribution (from logs)

| State Type | Calls | Mean chars | ~Mean tokens | Max chars | Key bloat |
|------------|-------|-----------|-------------|----------|-----------|
| **shop** | 22 | 7,660 | 1,915 | 8,359 | Items listing 1511, Computed Insights 1238 |
| **card_select** | 35 | 6,568 | 1,642 | 8,793 | Available Cards 2114, Knowledge 934 |
| **card_reward** | 19 | 5,368 | 1,342 | 6,032 | Knowledge + skills |
| **map** | 13 | 4,965 | 1,241 | 5,073 | Route plan + skills |
| **rest** | 7 | 4,129 | 1,032 | 4,441 | Skills 1214 (same as combat) |
| **combat** | 121 | 3,629 | 907 | 9,140 | Already optimized in P6-A |
| **treasure** | 6 | 1,956 | 489 | 2,203 | Smallest, OK |

**Biggest non-combat calls:** shop (1915 tok), card_select (1642 tok). These two are the primary targets.

## Common Bloat Across All Non-Combat Prompts (from log section breakdown)

| Section | Typical chars | Source | Every non-combat call? |
|---------|-------------|--------|----------------------|
| Expert Knowledge (skills) | ~1214 | composer.py | Yes |
| Computed Insights | ~1238 | tool_preprocessor.py | Yes (combat-irrelevant filtered in P6-A) |
| Strategy Rules (memory) | ~280 | prompt_injector.py | Yes (if rules exist) |
| Run Context | ~400 | run_context.py | Yes |
| Game Knowledge (cards) | ~400-934 | injector.py | card_reward/shop/card_select only |
| State-specific prompt | 57-2114 | prompts/*.py | Varies |

**Key insight:** Skills (1214 chars) and Computed Insights (1238 chars) are the two biggest sections in EVERY non-combat call. P6-A already compressed Insights for combat — but the non-combat tools (deck_bloat, rest_site) still produce verbose output when they DO run (in their applicable states).

---

## Plan

### Task 1: Remove Dead V1 Code from All Prompt Files

**Rationale:** All calls use `v2=True`. V1 branches are ~18,500 chars of dead code across 8 files. While this doesn't save runtime tokens (V1 code is never executed), it:
- Eliminates maintenance burden
- Prevents confusion when reading code
- Makes future optimization clearer (only V2 paths matter)

**Files:**
- Modify: `src/brain/prompts/rest.py` — remove V1 branch (~2940 chars code)
- Modify: `src/brain/prompts/shop.py` — remove V1 branch (~1370 chars code)
- Modify: `src/brain/prompts/reward.py` — remove V1 branches (~4375 chars code, 2 functions)
- Modify: `src/brain/prompts/card_select.py` — remove V1 branch (~3507 chars code)
- Modify: `src/brain/prompts/event.py` — remove V1 branch (~2275 chars code)
- Modify: `src/brain/prompts/hand_select.py` — remove V1 branch (~2237 chars code)
- Modify: `src/brain/prompts/treasure.py` — remove V1 branch (~1788 chars code)
- Modify: `src/brain/prompts/map.py` — remove V1 branch (has v2 param, called with v2=True)
- Delete: `src/brain/prompts/route_plan.py` — entire file is dead code (zero call sites, route planning uses route_planner.py)
- Modify: `src/agent/loop.py` — remove `v2=True` from all call sites

**Approach:**
- Remove the `v2` parameter from each `build_*_prompt()` function signature
- Keep only the V2 branch content
- Remove the V1 `else:` / `elif not v2:` blocks entirely
- Remove the `v2=True` argument from all call sites in `loop.py`
- Delete `route_plan.py` entirely — `build_route_plan_prompt()` has zero call sites (route planning already uses `route_planner.py` DFS + lightweight LLM)
- Do NOT change `potion.py` (has no V2 branch — separate task)

**Tests:**
- `tests/test_upgrade_prompt.py`: lines 241, 252 pass `v2=True` explicitly — remove the kwarg. Lines that call without `v2` will now get V2 output instead of V1 — verify assertions still hold
- Run full test suite — any test using `v2=False` should be updated or removed
- Grep for `v2=False` in tests — if found, remove those test paths

**Commit:** `refactor: remove dead V1 prompt code (all calls use v2=True)`

---

### Task 2: Computed Insights Non-Combat Compression

**Rationale:** From logs, Computed Insights is ~1238 chars in shop/card_select/rest. P6-A compressed the combat format in `format_hints()`, but the non-combat dynamic tools (`deck_bloat_energy_check`, `rest_site_heal_vs_upgrade_v2`) still produce full dict output. They now only run in their applicable states (P6-A added APPLICABLE_STATES), but when they DO run, they dump full dicts.

**Reality check:** P6-A already changed `format_hints()` to extract priority keys. So ALL tools (combat AND non-combat) now get the compressed format. The 1238 chars in logs is from BEFORE P6-A was applied. After P6-A, non-combat insights should already be ~300-500 chars.

**Action:** No code changes needed — verify via log analysis after running with P6-A changes. If still bloated, investigate which tools produce large output for non-combat states.

**This task is verification-only, not implementation.**

---

### Task 3: Skill Generation 400-Char Validation + Retry

**Rationale:** From agreed design — prevent future skill bloat at source. Currently no length limit on LLM-generated skill content.

**Files:**
- Modify: `src/skills/discovery.py` — add content length validation in `_parse_discovered_skills()`
- Modify: `src/brain/write_tools.py` — add content validation note in WRITE_SKILL description
- Modify: `src/brain/evolution_engine.py` — add validation when processing write_skill results

**Approach for discovery.py (post-run skill extraction):**

In `_parse_discovered_skills()`, after line 215 (after the existing `if not name or not content: continue` guard):
```python
        # Validate content length (prevent bloat at source)
        if len(content) > 400:
            logger.info(
                "Skill '%s' content too long (%d chars > 400), skipping",
                name, len(content),
            )
            continue
```

**Spec deviation note:** The design spec says "retry once with compression prompt, then reject." For discovery.py we skip directly without retry because: (1) discovery runs post-run via Opus (expensive, ~$0.15/call), (2) adding a retry loop would roughly double cost for a rare edge case, (3) the prompt already instructs "2-4 sentences" which naturally stays under 400 chars. The retry approach IS used in the evolution engine path (see below).

In `_DISCOVERY_PROMPT`, add to the task instructions (after "2-4 sentences"):
```
- Content MUST be under 400 characters. Be concise — rules only, no examples.
```

**Approach for write_tools.py (evolution engine skill writing):**

In WRITE_SKILL description, update the `content` field description:
```python
"description": (
    "The strategy knowledge in natural language. Will be injected "
    "into LLM prompts. MUST be under 400 characters. "
    "Be concise: rules only, no examples or negative cases."
),
```

**Approach for evolution_engine.py (`_handle_write_skill` at line 460):**

In `_handle_write_skill()`, after line 471 (after the `if not skill_name or not content` check), add validation that returns an error string to the LLM for retry:
```python
        if len(content) > 400:
            return {"error": f"Content too long ({len(content)} chars). Must be ≤400 chars. Compress to concise rules only and retry."}
```

This gives the evolution LLM feedback to retry with a shorter version within its existing tool-use loop (max 5 rounds). The three-stage dispatch catches return dicts and feeds them back as tool results.

**Tests:**
- Add to `tests/test_token_optimization.py`:
  - `test_discovery_rejects_long_content` — skill with 500-char content is skipped
  - `test_discovery_accepts_short_content` — skill with 300-char content is accepted

**Commit:** `feat: 400-char content limit for LLM-generated skills`

---

### Task 4: Shop Prompt — Items Listing Compression

**Rationale:** Shop prompts are the #1 biggest non-combat call (7660 chars mean). From logs, `## Items For Sale` is 1511 chars. This contains full card details with rules_text for every shop card.

**Files:**
- Modify: `src/brain/prompts/shop.py` — compress item listings

**Approach:**

Read `shop.py` to understand the current item listing format. The V2 path should:
- Show card name + cost + energy cost in one line (no full rules_text)
- rules_text is already available via knowledge injection (## Game Knowledge section)
- Relics: name + description (compact)
- Card removal: just the option + gold cost

**Example compression:**
```
# Before (actual format, per card): ~120 chars
- [index=3] Backstab (Card: Attack, Uncommon, cost=0, 75g) [CAN BUY]: Deal 11 damage. Innate. Exhaust.

# After (per card): ~65 chars
- [index=3] Backstab (0E, 75g) [CAN BUY] [11 dmg, Innate, Exhaust]
```

Note: Shop relics already show minimal info (name + rarity + price, no description). No compression needed for relics.

**Risk:** Removing rules_text from shop items means the LLM only sees knowledge injection for card details. Knowledge injection has a 1600-char budget (cards only) — if the shop has 6+ cards, some may not fit in the knowledge section.

**Mitigation:** Keep a 1-line summary per card (damage/block value + keywords) instead of full rules_text. This is ~60 chars vs ~150 chars per card, still self-contained.

**Tests:**
- Existing tests that assert shop prompt format (search for them)
- Manual verification with a log comparison

**Commit:** `perf: compress shop item listings (name+cost+summary vs full rules_text)`

---

### Task 5: Card Select — Available Cards Compression

**Rationale:** card_select is #2 biggest (6568 chars mean). `## Available Cards` is 2114 chars — showing full card details for upgrade/remove/transform choices.

**Files:**
- Modify: `src/brain/prompts/card_select.py` — compress available cards listing

**Approach:**

Similar to Task 4 — reduce per-card format:
```
# Before: ~200 chars per card
- [index=0] Strike+ (Attack, Basic, cost=1): Deal 9 damage. → Upgrade: Deal 12 damage.

# After: ~80 chars per card
- [index=0] Strike+ (1E) [9 dmg] → Upgrade: [12 dmg]
```

For remove mode: cards don't need upgrade info, just name + cost + brief summary.
For upgrade mode: show current → upgraded values inline.

**Tests:**
- Search for existing card_select tests
- Add format verification test

**Commit:** `perf: compress card_select available cards listing`

---

### Task 6: Verify Combat Card Knowledge Overlap

**Rationale:** Deferred from P6-A. In combat, hand cards already show structured `[N dmg]`/`[N block]` + full `rules_text` inline. Knowledge injection adds card mechanics (~400 tokens) that may duplicate this.

**This is research, not implementation.** Examine a combat prompt from logs and compare:
1. What does `## Game Knowledge > Card Mechanics` section show?
2. What does the hand section show per card?
3. Is there unique info in knowledge that's NOT in hand cards?

**If overlap >80%:** Create a follow-up task to skip card knowledge in combat.
**If unique info exists:** Document what's unique and decide if it's worth 400 tokens.

**No commit — just a finding that informs future work.**

---

### Task 7: Integration Verification

**Files:** None (verification only)

- [ ] Run full test suite: `python -m pytest tests/ -v`
- [ ] Verify no regressions in non-combat prompt formatting
- [ ] Spot-check that V1 code removal doesn't break any existing paths

**Commit:** Final verification marker if needed.

---

## Future TODOs (Not In This Plan)

- [ ] Rest remaining route truncation (show next 5 nodes only) — low priority, rest only 7 calls/run
- [ ] Route plan fallback top-1 only — P3, rare JSON parse failure case
- [ ] potion.py V2 branch — needs separate design (currently no v2 param)
- [ ] Combat card knowledge skip — pending Task 6 verification results

## Summary

| Task | Type | Savings | Risk |
|------|------|---------|------|
| 1. V1 dead code removal | Refactor | 0 runtime tokens, cleaner code | Low (v2 always True) |
| 2. Non-combat insights verification | Verify | Already done by P6-A | None |
| 3. Skill generation 400-char limit | Feature | Prevents future bloat | Low |
| 4. Shop items compression | Optimize | ~375 tokens/shop call | Medium (info density) |
| 5. Card select compression | Optimize | ~250 tokens/card_select call | Medium (info density) |
| 6. Combat card knowledge overlap | Research | Informs future ~400 token savings | None |
| 7. Integration verification | Verify | — | None |
