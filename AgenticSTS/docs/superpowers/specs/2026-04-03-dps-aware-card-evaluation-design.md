# DPS-Aware Card Evaluation Design

**Date**: 2026-04-03
**Status**: Draft
**Scope**: `reward.py`, `shop.py`, `event.py`, `system.py` (DECKBUILD variant), card clarifications

## Problem

The agent systematically fails to evaluate card picks by quantitative damage output.
In run `d0a82ab70421`, the agent died on Floor 17 (Act 1 Boss, Lagavulin Matriarch, 222 HP)
with only 169 total damage dealt across 11 rounds. Root causes:

1. **No DPS awareness**: The agent never estimates its deck's damage output per turn or
   compares it against Boss HP targets. All card evaluation is qualitative ("fills a gap",
   "synergizes with...") rather than quantitative.

2. **Missing card metadata in reward prompt**: Card reward options show only `name: rules_text`,
   missing energy cost, card type (Attack/Skill/Power), rarity, and numeric damage/block values.
   The LLM cannot compare card efficiency without this data.

3. **"Total damage test" bias toward Power cards**: The current prompt says "A card you play
   every cycle contributes far more total damage than a one-shot burst." This systematically
   favors Power cards (permanent effects) while undervaluing high-impact one-shot cards like
   Snakebite (7 Poison = 28 total damage from a single play).

4. **Card mechanic misunderstandings**: Speedster's "Whenever you draw a card" is misread
   as including turn-start draw (5 cards/turn), when it only triggers on draw effects from
   played cards (Backflip, Acrobatics, etc.). Without draw cards, Speedster deals 0 damage.

## Design

### Approach

Pure prompt changes — no Python calculation logic. The LLM is guided to perform rough DPS
estimation itself. If the estimation is unreliable, the self-evolution engine (`EvolutionEngine`)
can author dynamic tools to compute deck DPS precisely.

### Change 1: Card Reward — Enhanced Card Display + DPS Check

**File**: `src/brain/prompts/reward.py`

#### 1a. Card display format

**Current** (line 46):
```
- [index=0] Follow Through: Deal 6 damage to ALL enemies...
```

**New**:
```
- [index=0] Follow Through (1E, Attack, Common): Deal 6 damage to ALL enemies... [6 dmg]
- [index=1] Snakebite (2E, Skill, Common): Retain. Apply 7 Poison. [7 poison]
```

Add energy cost, card type, rarity from `RawRewardCardOptionPayload` fields. Extract
damage/block/hits from `dynamic_values` using the existing `get_damage_block_from_dynamic_values()`
helper (already used in `card_select.py`).

**Payload field availability**: `RawRewardCardOptionPayload` currently has `index`, `card_id`,
`name`, `upgraded`, `rules_text`, `dynamic_values`, `resolved_rules_text`. It does NOT have
`energy_cost`, `card_type`, or `rarity`. These must be added either:
- (Preferred) By extending `RawRewardCardOptionPayload` if the upstream MCP API provides them, or
- By knowledge DB lookup: `GameKnowledge.cards.get(name)` returns `energy_cost`, `card_type`, `rarity`

If neither source is available for a card, omit the metadata and show only name + rules_text
(graceful degradation, same as current behavior).

#### 1b. Replace Evaluation section

**Remove** the current Evaluation block (lines 58-71) including the "Total damage test" line.

**Replace with**:

```
## Evaluation — Boss Damage Check
Before picking, estimate your deck's damage output:
1. Sum each Attack card's base damage in your deck → total attack damage per cycle
2. Deck cycle length = deck_size ÷ 5 turns
3. Poison sources: each "Apply N Poison" card deals ~N×(N+1)/2 total damage per play
4. Your damage per turn ≈ (total attack damage per cycle) ÷ cycle_turns + poison contribution

Boss HP targets: Act 1 ≈ 200, Act 2 ≈ 400, Act 3 ≈ 600. Budget ~10 turns.
→ You need roughly {Boss_HP ÷ 10} damage per turn while also blocking.

Decision rules:
- If your estimated DPS is well below target → PRIORITIZE damage/poison cards over defense/draw/utility
- If DPS is sufficient → take defense/draw/utility, or SKIP to keep deck lean
- Power cards that deal passive damage need draw support to function — factor in whether you have the enablers
- 3 energy per turn limits you to ~2-3 card plays: a 2-cost card must be worth two 1-cost cards

Consider your deck's 4 dimensions (Damage/Defense/Draw/Energy) but weight Damage highest when below target.
Review your Build Plan in the Strategic Thread. Does any card fill a gap?
Adding a card increases deck cycle ({deck_size} → {deck_size + 1} cards).
SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one.
```

The `{deck_size}` and `{deck_size + 1}` are already interpolated in the current code.
The Boss HP target and DPS-per-turn are computed from `gs.act` in Python:
```python
_BOSS_HP = {1: 200, 2: 400, 3: 600}
boss_hp = _BOSS_HP.get(act, 400)
target_dps = boss_hp // 10
```
These are interpolated into the prompt string as concrete numbers (e.g. "need ~20/turn").

### Change 2: Shop — Add DPS Check

**File**: `src/brain/prompts/shop.py`

Replace the `## Guide` section (lines 158-160) with an expanded version that includes the
Boss Damage Check. The shop already shows card costs and rules_text, so the card display
format is adequate. The key addition is the DPS awareness:

```
## Guide
Best purchase = biggest power spike for remaining run.

Boss HP: Act 1 ≈ 200, Act 2 ≈ 400, Act 3 ≈ 600 in ~10 turns → need ~{target_dps}/turn.
Estimate your deck's damage output first. If below target, prioritize damage/poison cards
and card removal (faster cycle = more damage cards drawn). If above target, invest in
defense, draw, relics, or save gold.

Review your Build Plan in the Strategic Thread. Prioritize purchases that fill gaps.
```

### Change 3: Event — Lightweight DPS Reminder

**File**: `src/brain/prompts/event.py`

Append to the evaluation guidance (after line 57):

```
If an option offers a card or card-related benefit: consider whether your deck needs more
damage to handle upcoming bosses (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600 in ~10 turns).
Prefer damage/poison options when your deck's attack output is low.
```

### Change 4: System Prompt — Remove Power Card Bias

**File**: `src/brain/prompts/system.py`

In `SYSTEM_DECKBUILD` (line 80), remove or revise:
> "A strong deck needs all 4 dimensions in balance."

Replace with:
> "A strong deck needs enough damage to kill bosses in ~10 turns (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600) while surviving. Damage is the primary constraint — defense, draw, and energy support damage output."

This reframes the 4-dimension model from "balanced equally" to "damage-first, others support."

### Change 5: Card Clarifications Knowledge System

**New data**: A dictionary of cards with commonly misunderstood mechanics. Initially just
Speedster, extensible as more are discovered.

**Location**: New constant in `reward.py` (or a shared module if preferred). A simple dict:

```python
CARD_CLARIFICATIONS: dict[str, str] = {
    "Speedster": (
        "Turn-start draw does NOT trigger Speedster. Only draw effects from played cards "
        "(Backflip, Acrobatics, etc.) count. Without draw cards in deck, Speedster deals "
        "0 damage/turn. Value scales with draw card density."
    ),
}
```

**Injection logic**: When building card reward, shop, or combat prompts, scan both the
offered cards AND the current deck for cards in `CARD_CLARIFICATIONS`. If found, append
a `## Card Notes` section:

```
## Card Notes
- Speedster: Turn-start draw does NOT trigger. Only draw from card effects
  (Backflip, Acrobatics) counts. Value depends entirely on draw card density.
```

**Injection points**:
- `reward.py` — `build_card_reward_prompt()`: scan `rw.card_options` names + `deck` names
- `shop.py` — `build_shop_prompt()`: scan `shop.cards` names + `deck` names
- Combat conversation init (`conversation.py`): scan hand cards + deck for notes

The dict is small (initially 1 entry), so scanning is O(1) per card. As more clarifications
are discovered during gameplay, they can be added to the dict.

## Files Changed

| File | Change |
|------|--------|
| `src/brain/prompts/reward.py` | Enhanced card display format, replace Evaluation with DPS Check, add Card Notes injection |
| `src/brain/prompts/shop.py` | Replace Guide with DPS-aware Guide, add Card Notes injection |
| `src/brain/prompts/event.py` | Append DPS reminder to evaluation guidance |
| `src/brain/prompts/system.py` | Revise SYSTEM_DECKBUILD to damage-first framing |

## Token Impact

| Prompt | Current | After | Delta |
|--------|---------|-------|-------|
| card_reward | ~400 tokens | ~480 tokens | +80 |
| shop | ~350 tokens | ~410 tokens | +60 |
| event | ~200 tokens | ~230 tokens | +30 |
| system (DECKBUILD) | ~280 tokens | ~290 tokens | +10 |

Per-run impact: ~10 card selection events × ~80 avg increase = **~800 tokens/run** (negligible).

## Not Changed

- `card_select.py` — upgrade/remove screens: not a card acquisition decision
- `rest.py` — rest/smith decision: not directly about DPS
- `system.py` COMBAT/BOSS/STRATEGIC variants — not deck-building contexts
- No Python DPS calculation logic — LLM estimates from prompt guidance
- No new query tools — self-evolution engine can create them if needed

## Success Criteria

1. Agent performs rough DPS estimation in card reward reasoning (visible in logs)
2. Agent takes damage/poison cards when deck DPS is below Boss HP targets
3. Agent SKIPs card rewards when DPS is sufficient and offered cards don't improve a weak dimension
4. Agent correctly evaluates Speedster as conditional (needs draw cards) rather than unconditional scaling
5. No systematic Power card bias — Power cards chosen only when they genuinely improve DPS with existing deck support
