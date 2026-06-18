# Flexible Potion Usage — Design

**Status:** Draft
**Date:** 2026-04-18
**Owner:** AgenticSTS Contributors

## 1. Goal

Stop silently skipping potion rewards / shop purchases when potion slots are full. Instead, let the LLM decide whether to discard an existing potion and take the new one, or skip. Also add a short combat-prompt hint that biases the agent toward spending low-value potions when slots are full — but only when spending actually helps the round.

Underlying principle (design rationale, not in prompt): maximize potion utilization by avoiding hoarding, so we rarely end up throwing away high-value rewards just because slots are full.

## 2. Scope

- In scope:
  - Reward-path potion claim when slots full (currently auto-skipped)
  - Shop potion purchase when slots full
  - Combat prompt hint when slots full
- Not in scope:
  - Passive mid-run potion management outside reward/shop/combat (e.g. event-granted potions handled by event flow, no change here)
  - Mechanical discard scoring (no "auto-discard weakest" heuristic — LLM decides)

## 3. Non-Goals

- Compound single-action discard-and-take primitive (would require new C# API). Keep `discard_potion` and `claim_reward` / `buy_potion` as two separate actions executed across two state ticks.
- Long prompt rationale explaining why to use potions aggressively (agent should figure out from the single-line hint + current state)

## 4. Architecture

```
[Reward Path]                                          [Shop Path]
loop._try_mechanical_rewards                           loop._handle_shop
  (current: silent skip when full)                      (current: no discard-to-buy logic)
           │                                                  │
           ▼                                                  ▼
    Detect "potion reward + slots FULL"                Detect "shop has potion + slots FULL"
           │                                                  │
           └──► Route to LLM (reward.py prompt)         ──►   LLM (shop.py prompt)
                    with "## Potion Slot Decision" subsection
                                  │
                                  ▼
                     LLM returns one of:
                     - action=discard_potion(idx=J)   → next tick auto-re-enters reward/shop flow
                     - action=claim_reward / skip      (keep existing potions)
                     - action=buy_potion / skip        (shop)

[Combat Path]
conversation._format_potions
           │
           ▼
     Existing "Potion slots: N/M FULL" line
     (new) When FULL: append single line:
     "Slots FULL — spend a lower-value potion if it helps this round;
      don't waste just to free a slot."
```

**Key invariant:** `discard_potion` and `claim_reward` / `buy_potion` are independent actions. The LLM returns ONE action per decision; the agent loop naturally re-enters reward/shop flow on the next tick (now with an open slot), where the LLM picks up / buys the new potion in a normal decision.

## 5. Components

### 5.1 Reward-Path: No Code Change to `_try_mechanical_rewards`

Re-reading `src/agent/loop.py:7556-7568`:

```python
open_potion_slots = gs.open_potion_slots
for item in rewards.rewards:
    if not item.claimable:
        continue
    rtype = item.reward_type.lower()
    if rtype == "potion" and open_potion_slots <= 0:
        logger.info("Skipping potion reward (no open slots): %s", item.description)
        continue   # <-- falls through to next reward item in the same call
    if rtype in ("gold", "potion", "relic", "specialcard"):
        action = actions.claim_reward(item.index)
        ...
```

The `continue` is an item-level skip inside the mechanical loop, not a permanent skip of the potion. Flow today:

1. Tick N: reward has `[gold, potion]`, slots full. Mechanical loop claims gold → returns.
2. Tick N+1: reward has `[potion]`, slots full. Mechanical loop `continue`s past potion → loop ends with no claim → function returns `None`.
3. Main loop: routes to LLM reward prompt path.
4. Today the prompt does not include a discard-and-claim option; LLM typically chooses "skip" → potion lost.

**Change is purely additive (step 3): the prompt path gains a new `## Potion Slot Decision` subsection** that gives LLM the `discard_potion(J)` option. After the discard executes, tick N+2 enters the reward state with one open slot; subsection no longer applicable; LLM claims the potion normally (or mechanical loop does if no other reasoning needed). No deletion / rewrite of `_try_mechanical_rewards`.

### 5.2 Shop Path (`src/agent/loop.py`)

`_handle_shop` currently lets the LLM pick from all items. Regardless of whether the server blocks buy-when-full or errors silently, the prompt-side addition is the same: when `open_potion_slots == 0` AND `shop_has_affordable_potions`, inject the slot-decision subsection so the LLM can opt to discard first. No code change to `_handle_shop` itself; only the prompt builder is extended.

### 5.3 Shared Prompt Helper (`src/brain/prompts/_potion_slot_fmt.py` — new)

```python
def format_potion_slot_decision(
    gs: GameState,
    candidate_potions: list[str],   # names of new potions available to claim/buy
) -> list[str]:
    """Return lines for the slot-decision subsection, or [] if inapplicable.
    Applicable when: open_potion_slots == 0 AND candidate_potions is non-empty."""
```

Output format:

```
## Potion Slot Decision (slots FULL)
Currently held:
  [0] Fire Potion — damage
  [1] Block Potion — block
  [2] Energy Potion — resource
Candidate: Ghost Potion (buff, intangible for 1 turn)

Prefer keep unless the candidate is clearly stronger than your weakest held potion.
To take the candidate, discard one of [0/1/2] first; otherwise skip.
```

Types (`damage`/`block`/`buff`/`heal`/`resource`/`utility`) are reused from the existing `potion_classifier`.

### 5.4 Injection Sites

- `src/brain/prompts/reward.py::build_card_reward_prompt` — append slot-decision subsection when the reward contains a claimable potion AND slots are full. Card reward prompt already covers non-card rewards when `rewards.rewards` contains mixed types.
- `src/brain/prompts/shop.py::build_shop_prompt` — same logic using shop's `potions` list, filtering affordable candidates (`gold >= price`). If shop has potions but none affordable, skip subsection.

### 5.5 Combat Prompt Hint (`src/brain/conversation.py`)

In the existing `_format_potions` path (around line 1067-1081), after the existing "Potion slots: N/M FULL" line and the existing "POTION SLOTS FULL: X will not add a potion" warning, add:

```python
if open_slots <= 0:
    lines.append(
        "Slots FULL — spend a lower-value potion if it helps this round; "
        "don't waste just to free a slot."
    )
```

The hint is only shown when slots are actually full (zero cost otherwise).

## 6. Data Flow

### Reward example (full slots, potion reward present)

1. Tick N: reward state `[gold, potion]`, slots full. Mechanical loop claims gold (first claimable non-potion item), returns → `claim_reward(gold)` executed.
2. Tick N+1: reward state `[potion]`, slots full. Mechanical loop `continue`s past potion (existing behavior), returns `None`.
3. Main loop routes to LLM reward-prompt path. With the change, the prompt now includes `## Potion Slot Decision` subsection listing held potions + candidate.
4. LLM returns `discard_potion(idx=J)` (e.g. discarding a block potion).
5. Tick N+2: reward still shows `[potion]`, slots now have one open. Subsection no longer applicable; mechanical loop claims the potion (or LLM does via normal flow).

If LLM instead returns `skip`, reward advances and the new potion is lost — same as today, but now an explicit choice rather than silent drop.

### Shop example (full slots, potion for sale)

Similar but two-action: LLM picks `discard_potion(idx=J)` → next tick, slot open → LLM picks `buy_potion(idx=K)` via normal shop flow.

### Combat example

Every combat tick with full slots gets the appended line. Agent's round-by-round decision (play card, use potion, etc.) now has a subtle nudge to spend marginal potions.

## 7. Error Handling

| Condition | Behavior |
|---|---|
| LLM returns `discard_potion` with out-of-range index | Action fails validation (existing invalid-action path); agent retries with feedback |
| LLM returns `skip` | Reward advances; potion is lost (current behavior, now explicit) |
| Discard succeeds but next-tick reward list no longer contains the potion | Natural: state has changed; LLM re-decides with fresh context |
| Shop: LLM discards but cannot afford the new potion | Discard stands (user's design: LLM owns the tradeoff) |
| State not reward/shop | Helper not called |
| `open_slots > 0` | Neither subsection nor combat hint appears |
| Shop has potions but none affordable | Subsection skipped |

## 8. Testing

### Unit

- `test_loop_mechanics.py::test_potion_reward_full_slots_routes_to_llm` — mock `gs.open_potion_slots=0` + claimable potion in reward → `_try_mechanical_rewards` returns `None` (no silent skip), allowing LLM path to take over.
- `test_potion_slot_fmt.py::test_empty_when_not_full` — helper returns `[]` when slots have room.
- `test_potion_slot_fmt.py::test_empty_when_no_candidates` — returns `[]` when slots full but no new potions.
- `test_potion_slot_fmt.py::test_subsection_format` — returns well-formed subsection with held potions + candidate + instruction line.
- `test_reward_prompt.py::test_slot_decision_injected` — `build_card_reward_prompt` contains `## Potion Slot Decision` when slot-full + potion reward.
- `test_shop_prompt.py::test_slot_decision_skipped_when_no_affordable_potion` — subsection omitted when gold < cheapest potion price.
- `test_combat_conversation.py::test_combat_hint_on_full_slots` — combat prompt contains the new hint line when full.
- `test_combat_conversation.py::test_no_combat_hint_when_slots_open` — line absent otherwise.

### Integration (live)

- Run an agent until potion slots fill (usually by mid-act-1). Verify silent-skip no longer occurs in logs; next potion reward prompt contains `## Potion Slot Decision`.
- Observe at least one live `discard_potion` decision followed by the expected claim/buy on the next tick.
- Verify combat prompt hint appears only when slots full; monitor potion usage rate shifts across 5–10 runs.

## 9. Rollout

1. Pure-Python change; no mod modification required. Can ship independently of Spec 1.
2. Feature is zero-cost when slots are not full — no flag needed.
3. Monitor: ratio of `discard_potion` decisions; runs where agent ends with full slots (should decrease).
