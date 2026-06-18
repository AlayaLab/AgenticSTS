# Upstream Sync — Reward Atomization, Bundle Support, AlphaZero Field Enrichment

**Date**: 2026-04-28
**Status**: Implemented (Rev 2 — post-implementation, divergences noted)
**Sources**: CharTyr/STS2-Agent commits since vendored base `6ccfb251` (2026-04-06)
**Companion to**: `STS2-Agent-Fork/VENDOR.md` (vendor-patches manifest)

## Implementation divergences (2026-04-28 Rev 2)

The implementation deviates from the spec in 5 places. Captured here so
future readers don't get confused by spec/code mismatch.

1. **Skipped Python `choose_bundle` / `confirm_bundle` action builders**
   (spec §"`src/mcp_client/actions.py`"). Our C# fork doesn't have those
   handlers — vendor base predates the upstream commits that added them
   (`473858d`, `5286f2d`), and patch 0001 doesn't carry them either.
   Bundle screen instead routes through `BuildBundleSelectionPayload` →
   `SelectionPayload(kind="bundle_select")` → existing `select_deck_card`
   action. Adding action builders without C# handlers would 400.

2. **Reused `CARD_SELECT_TOOL` instead of the dedicated `BUNDLE_TOOL`
   schema** (spec §"`src/brain/tool_schemas.py`"). Same root cause as
   #1: bundle decision emits `select_deck_card`, so the existing tool
   schema's enum is correct. The `bundle.py` prompt explicitly calls
   out `select_deck_card` as the decision action.

3. **Stricter `TryGetNextClaimableRewardButton` filter** than upstream:
   ```csharp
   (button.Reward is not CardReward
       || (!_cardRewardSkipped && _pendingCardRewardChoice >= 0))
   ```
   (vs upstream's `(!_cardRewardSkipped || button.Reward is not CardReward)`
   which would auto-claim cards by default.) Our local
   `collect_rewards_and_proceed` historically excluded card rewards
   entirely so the agent would handle them explicitly. Adopting upstream's
   pattern verbatim would silently change `collect_rewards_and_proceed`
   semantics. The stricter filter preserves local behavior and only
   admits CardReward when `resolve_rewards` has set
   `_pendingCardRewardChoice >= 0`. Comment in code explains.

4. **Did NOT consume structured pile data downstream** (spec
   §"Structured pile consumption (1B) — optional"). The C# payload now
   exposes `draw_cards` / `discard_cards` / `exhaust_cards` and the
   Python model parses them, but `_pile_fmt.py` and
   `combat_delta.py` still use the legacy textual path. Spec marked this
   optional; deferred.

5. **`085ebc8` (allow CARD_SELECTION as starting screen) is a no-op for
   us**. Our `CanCollectRewardsAndProceed` already returns
   `currentScreen is NRewardsScreen || currentScreen is NCardRewardSelectionScreen`,
   covering both screens. `CanResolveRewards` aliases it. Cherry-pick
   list keeps `085ebc8` for documentation; the actual code change for
   our fork is zero.

Bonus side-fix not in spec: `tests/prompts/test_baseline_variants.py`
`_build_reward_gs` MagicMock fixture was returning auto-attribute
proxies for the new `card_type` / `rarity` / `energy_cost` / `costs_x`
fields, polluting prompt output. Mock now explicitly sets them to
empty/zero so the old-mod fallback path runs.

## Overview

Cherry-pick a curated set of upstream commits into our vendored fork and align the Python agent so we get:

1. **Atomic reward resolution** — collapse the 4–5-step claim/open/pick/proceed loop into one MCP call.
2. **Crystal-Sphere-skip auto-claim bug fix** — defensive even though we haven't repro'd it.
3. **Full Bundle (ScrollBoxes) support** — we have half the C# layer; need the dedicated `bundles[]` payload + a real prompt.
4. **Reward card metadata** (`card_type` / `rarity` / `energy_cost`) — close a real gap in our `RewardCardOptionPayload`.
5. **(Optional) Structured pile data** — `draw_cards` / `discard_cards` / `exhaust_cards` as `[{card_id, upgraded, card_type}]`.

Explicitly **NOT** in scope:
- Capstone screen support (`NCapstoneSubmenuStack` is a compendium/settings shell, not a victory screen).
- Mid-turn card-play counters (user opted out: marginal value, only ~3 deck-archetype cards benefit).
- `enemy_id` / `move_id` enrichment of `agent_view` (we already have these in full state and key on them in HCM).
- `act_id` / `boss_id` aliases (our `boss_encounter_id` is more precise).
- v0.6.1 `GameDataExportService` (large, low short-term ROI).

## Context

### Current vendor state

- Vendor base: `6ccfb251c06cf6e8f7729a2afe85d2ad2db9a3bf` (CharTyr main @ 2026-04-06)
- 8 custom patches preserved in `STS2-Agent-Fork/vendor-patches/0001..0008.patch`
- Active patch with most overlap risk: **`0008-fix-mod-unblock-discard_potion-on-reward-and-card_re.patch`** — touches `GameActionService.ExecuteDiscardPotionAsync` screen-gating, **disjoint** from `DrainRewardFlowAsync` / `TryGetNextClaimableRewardButton`. No conflict expected.

### Current Python reward flow (`src/agent/loop.py:8361` `_handle_rewards`)

```
state=combat_rewards  → claim_reward(idx)  ×N (gold/relic/potion, mechanical)
                      → claim_reward(card_idx) opens card_reward
state=card_reward     → LLM picks → choose_reward_card(N) | skip_reward_cards
                      → state returns to combat_rewards
state=combat_rewards  → claim_reward(idx) for any remaining items
                      → collect_rewards_and_proceed
```

Profiled on a 24-reward run: 115 total reward-flow actions, avg 4.8 per reward instance.

### Upstream `resolve_rewards` semantics (post-`b7a8271`)

Single call to `DrainRewardFlowAsync(20s timeout)` that:
1. Auto-claims every gold / relic / potion (potion gated on `HasOpenPotionSlots`).
2. When it hits a card_reward screen, consults `_pendingCardRewardChoice`:
   - `-2`: click skip-alternative (and set `_cardRewardSkipped = true`).
   - `0..options.Count-1`: pick that card.
   - `-1` or out-of-range: pick first card (default).
3. Drains back to `NRewardsScreen`, clicks proceed.
4. Returns when off the reward stack.

API: `resolve_rewards(option_index=N | -1)` — `option_index=-1` is "skip", `N≥0` is "pick that card index". `card_index` is a **deprecated alias** for the pick case (no `-1` semantics on the alias).

The starting screen can be either `NRewardsScreen` (combat_rewards) **or** `NCardRewardSelectionScreen` (card_reward) — `085ebc8` added that flexibility. **Therefore we'll call it from `card_reward` after the LLM has seen the cards**, eliminating blind precommit.

## Cherry-pick set

| Order | SHA | Title | Files | Conflicts |
|---|---|---|---|---|
| 1 | `b5066cc` | Fix collect_rewards skip auto-claim bug | `GameActionService.cs` | None |
| 2 | `a219174` | Phase 2C: resolve_rewards atomic action | `GameActionService.cs` | None |
| 3 | `085ebc8` | Allow CARD_SELECTION as starting screen | `GameActionService.cs` | None |
| 4 | `58c8522` | Expose resolve_rewards in available_actions | `GameStateService.cs` | None |
| 5 | `b7a8271` | PR 35 reward + counter regressions | `GameActionService.cs`, `GameStateService.cs`, `mcp_server/*` (skipped — we don't use upstream mcp_server) | Mid-turn counter machinery — see §Counter Carve-out |
| 6 | `2acef18` | Bundle card data for `NChooseABundleSelectionScreen` | `GameStateService.cs` | None (we have `BuildBundleSelectionPayload` already; this adds dedicated `bundles[]`) |
| 7 | `e6a90ff` (partial) | AlphaZero payload — **only 1B + 1C** | `GameStateService.cs` | Cherry-pick the structured-pile + reward-card-metadata hunks; **drop** the 1A (counters) and 1D (potion_id agent_view) hunks |

### Counter carve-out (in `b7a8271` and `e6a90ff`)

`b7a8271` mixes a counter refactor (`SyncCardPlayCounters`) with the resolve_rewards API rename (`card_index` → `option_index=-1`). We want the API rename; we don't want the counter machinery (user-decided not needed).

**Strategy**: cherry-pick the API hunks; drop the `_pendingCardRewardChoice` semantic stays; delete the `SyncCardPlayCounters` / `CardsPlayedThisTurn` / `AttacksPlayedThisTurn` / `SkillsPlayedThisTurn` / `LastTurnNumber` lines and the `play_card` increment block.

`e6a90ff`: take only `BuildStructuredPileCards` + the `RewardCardOptionPayload` `card_type/rarity/energy_cost` additions. Drop `cards_played_this_turn` / `attacks_played_this_turn` / `skills_played_this_turn` from `agent_view.player`, drop `potion_id` agent_view enrichment.

## C# changes — concrete

### `STS2AIAgent/Game/GameActionService.cs`

#### Add (b5066cc)
```csharp
private static bool _cardRewardSkipped;
```
- Set `true` in `ExecuteSkipRewardCardsAsync` (after the alternative click).
- Set `false` in `ExecuteChooseRewardCardAsync` (after card click) and on screen exit.
- Filter in `TryGetNextClaimableRewardButton`:
  ```csharp
  (!_cardRewardSkipped || button.Reward is not CardReward)
  ```

#### Add (a219174 + 085ebc8 + b7a8271)
```csharp
private static int _pendingCardRewardChoice = -1; // -2 skip, -1 default, ≥0 pick

"resolve_rewards" => ExecuteResolveRewardsAsync(request),
```

`ExecuteResolveRewardsAsync` body:
- Reject if `!CanCollectRewardsAndProceed(currentScreen)` AND `currentScreen is not NCardRewardSelectionScreen` (the 085ebc8 relaxation).
- Read `request.option_index` (primary) with `request.card_index` as deprecated alias.
- `option_index == -1` → `_pendingCardRewardChoice = -2`, `_cardRewardSkipped = true`.
- `option_index ≥ 0` → `_pendingCardRewardChoice = option_index`, `_cardRewardSkipped = false`.
- absent → `_pendingCardRewardChoice = -1`.
- `await DrainRewardFlowAsync(20s)` and return.

`TryResolveCardRewardAsync` updated:
- If `_pendingCardRewardChoice == -2`: click first alternative button, set `_cardRewardSkipped = true`, await screen exit.
- If `_pendingCardRewardChoice ≥ 0` and within range: pick that card holder.
- Else: pick first card.

### `STS2AIAgent/Game/GameStateService.cs`

#### Add (58c8522)
In `BuildAvailableActionDescriptors` (or wherever we accumulate descriptors), when `CanCollectRewardsAndProceed(currentScreen) || currentScreen is NCardRewardSelectionScreen`:
```csharp
descriptors.Add(new ActionDescriptor {
    name = "resolve_rewards",
    requires_target = false,
    requires_index = false  // option_index is optional
});
```

#### Add (2acef18) — Bundle payload

New top-level field on `GameStatePayload`:
```csharp
public BundlePayload[]? bundles { get; init; }
```

`BuildStatePayload` populates it via new `BuildBundlePayload(currentScreen)`:
- Returns `null` if not on `NChooseABundleSelectionScreen`.
- Iterates `GetBundleSelectionOptions(bundleScreen)`.
- For each `NCardBundle`: extract `bundle.Bundle` (a `IReadOnlyList<CardModel>`) → list of cards.
- Each card uses the existing card payload builder (`card_id`, `name`, `upgraded`, `energy_cost`, `rules_text`, `resolved_rules_text`, `dynamic_values`).

`BundlePayload`:
```csharp
internal sealed class BundlePayload {
    public int index { get; init; }
    public BundleCardPayload[] cards { get; init; } = Array.Empty<BundleCardPayload>();
}

internal sealed class BundleCardPayload {
    public int index { get; init; }            // index within the bundle
    public string card_id { get; init; }
    public string name { get; init; }
    public bool upgraded { get; init; }
    public int energy_cost { get; init; }
    public string rules_text { get; init; }
    public string resolved_rules_text { get; init; }
    public CardDynamicValuePayload[] dynamic_values { get; init; } = Array.Empty<...>();
}
```

`agent_view` rendering: `BuildAgentBundlePayload(bundles, glossaryTerms)` — group by bundle index, format each card via `BuildAgentChoiceCardPayload`. Wire into agent_view.

**Note**: keep our existing `BuildBundleSelectionPayload` (selection-payload path) intact for backward compatibility; new `bundles[]` is additive.

#### Add (e6a90ff partial — 1B + 1C)

`RewardCardOptionPayload` adds:
```csharp
public string card_type { get; init; } = string.Empty;
public string rarity { get; init; } = string.Empty;
public int energy_cost { get; init; }
```

Populated in `BuildRewardCardOptionPayload` from `holder.CardModel.Type.ToString()`, `Rarity.ToString()`, `EnergyCost.GetWithModifiers(CostModifiers.All)`.

`CombatPlayerPayload` and `CombatPlayerSummaryPayload` (for opt-in callers) get **structured pile fields** (parallel to the existing string-based `draw`/`discard`/`exhaust`):
```csharp
public PileCardPayload[] draw_cards { get; init; } = Array.Empty<PileCardPayload>();
public PileCardPayload[] discard_cards { get; init; } = Array.Empty<PileCardPayload>();
public PileCardPayload[] exhaust_cards { get; init; } = Array.Empty<PileCardPayload>();

internal sealed class PileCardPayload {
    public string card_id { get; init; } = string.Empty;
    public bool upgraded { get; init; }
    public string card_type { get; init; } = string.Empty;
}
```

Built via new helper `BuildStructuredPileCards(CardModel[])` mirroring upstream's signature.

#### NOT added
- `CardsPlayedThisTurn` / `AttacksPlayedThisTurn` / `SkillsPlayedThisTurn` (counters)
- `agent_view.player.cards_played_this_turn` etc.
- `agent_view.run.potions[].potion_id` (we already have it on full state)
- `agent_view.run.act_id` / `boss_id`
- `agent_view.combat.enemies[].enemy_id` / `move_id`

## Python changes — concrete

### `src/mcp_client/upstream_models.py`

```python
# Reward card option enrichment (1C)
class RawRewardCardOptionPayload(UpstreamModel):
    index: int = 0
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    rules_text: str = ""
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
    card_type: str = ""           # NEW
    rarity: str = ""              # NEW
    energy_cost: int = 0          # NEW

# Structured pile card (1B)
class RawPileCardPayload(UpstreamModel):
    card_id: str = ""
    upgraded: bool = False
    card_type: str = ""

class RawCombatPlayerPayload(UpstreamModel):
    # ... existing fields ...
    draw_cards: list[RawPileCardPayload] = Field(default_factory=list)      # NEW
    discard_cards: list[RawPileCardPayload] = Field(default_factory=list)   # NEW
    exhaust_cards: list[RawPileCardPayload] = Field(default_factory=list)   # NEW

# Bundle (2acef18)
class RawBundleCardPayload(UpstreamModel):
    index: int = 0
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    energy_cost: int = 0
    rules_text: str = ""
    resolved_rules_text: str = ""
    dynamic_values: list[DynamicValue] = Field(default_factory=list)

class RawBundlePayload(UpstreamModel):
    index: int = 0
    cards: list[RawBundleCardPayload] = Field(default_factory=list)

class UpstreamGameState(UpstreamModel):
    # ... existing fields ...
    bundles: list[RawBundlePayload] = Field(default_factory=list)   # NEW
```

### `src/state/game_state.py`

```python
@property
def bundles(self) -> list[RawBundlePayload]:
    return list(self.raw.bundles or [])
```

### `src/state/upstream_game_state.py` — derive_state_type

```python
# Crystal Sphere already added 2026-04-28. Add bundle_select sibling.
if raw.crystal_sphere is not None:
    return "crystal_sphere"
if raw.bundles:
    return "bundle_select"   # NEW — preferred when bundles[] is non-empty
```

Add `bundle_select` to `CHOICE_PHASES`.

### `src/mcp_client/actions.py`

```python
def resolve_rewards(option_index: int | None = None) -> dict:
    """Atomic reward resolution.

    option_index=-1 → skip the card reward
    option_index=N (≥0) → pick that card
    option_index=None → leave default (mod picks first card)
    """
    payload: dict = {"action": "resolve_rewards"}
    if option_index is not None:
        payload["option_index"] = option_index
    return payload


def choose_bundle(option_index: int) -> dict:
    return {"action": "choose_bundle", "option_index": option_index}


def confirm_bundle() -> dict:
    return {"action": "confirm_bundle"}
```

### `src/agent/loop.py` — reward atomization (minimal-invasion)

Gate on a config flag for safe rollout:

```python
# config.py
RESOLVE_REWARDS_ATOMIC: bool = os.getenv("STS2_RESOLVE_REWARDS_ATOMIC", "true").lower() == "true"
```

In `_execute_llm_decision`, **just before** calling `llm_dec.to_action()`:

```python
def _maybe_atomize_card_reward(
    self, gs: GameState, llm_dec: LLMDecision
) -> dict | None:
    """Translate card_reward LLM output into resolve_rewards atomic call.

    Returns the action dict to execute, or None to fall through to legacy.
    """
    if not config.RESOLVE_REWARDS_ATOMIC:
        return None
    if gs.state_type != "card_reward":
        return None
    avail = gs.available_actions or []
    if "resolve_rewards" not in avail:
        return None  # old mod, fall back

    if llm_dec.action_name == "choose_reward_card":
        idx = self._safe_int(llm_dec.params.get("option_index"))
        if idx is None or idx < 0:
            return None
        return actions.resolve_rewards(option_index=idx)

    if llm_dec.action_name == "skip_reward_cards":
        return actions.resolve_rewards(option_index=-1)

    if llm_dec.action_name == "choose_reward_alternative":
        # Only atomize the SKIP alternative; sacrifice paths stay multi-step
        # because resolve_rewards has no sacrifice semantics.
        if self._is_skip_alternative_decision(gs, llm_dec):
            return actions.resolve_rewards(option_index=-1)
        return None

    return None
```

Wire it where `action = llm_dec.to_action()` in `_execute_llm_decision`:

```python
atomic_override = self._maybe_atomize_card_reward(gs, llm_dec)
action = atomic_override if atomic_override is not None else llm_dec.to_action()
```

`_handle_rewards` (mechanical drain on `combat_rewards`) **stays** as-is. Reasoning:
- It already efficiently auto-claims with no LLM call.
- After the atomic card_reward call, screen transitions directly past combat_rewards → next floor, so `_handle_rewards` rarely re-fires.
- We keep it for rare paths (combat_rewards opened with no card_options because all cards already taken / proceed-only state).

### `src/agent/loop.py` — Bundle support

Replace the `_is_pack_selection` heuristic for the bundle case:

```python
def _is_bundle_selection(self, gs: GameState) -> bool:
    return gs.state_type == "bundle_select" and bool(gs.bundles)
```

Add new dispatch branch in the V2 prompt builder (`_build_state_prompt_v2`):

```python
if gs.state_type == "bundle_select":
    return build_bundle_selection_prompt(gs, deck=deck, relics=relics)
```

Add to `_V2_TIER_MAP`: `"bundle_select": "strategic"`.

Add to `_STATE_SYSTEM_MAP` and `_STATE_SYSTEM_MAP_BASELINE`: `"bundle_select": SYSTEM_DECKBUILD`.

### `src/brain/prompts/bundle.py` (new file)

```python
"""Prompt template for ScrollBoxes bundle selection.

Triggered by the Ancient relic ScrollBoxes: drains all gold and presents
3 bundles of cards. Player picks ONE bundle; all its cards go into deck.
"""

def build_bundle_selection_prompt(
    gs: GameState,
    *,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
) -> str:
    bundles = gs.bundles
    if not bundles:
        return "## Bundle Selection\n(no bundles)\n"

    sections = ["## Bundle Selection (ScrollBoxes)"]
    sections.append(
        f"HP: {gs.player_hp}/{gs.player_max_hp} | Gold: {gs.gold} (just lost all to ScrollBoxes) | Floor: {gs.floor}"
    )
    sections.append(format_deck_section(deck) or "")
    if relics:
        sections.append("Relics: " + ", ".join(relics))

    sections.append("\nChoose **one** bundle. ALL cards in that bundle enter your deck.\n")
    for b in bundles:
        sections.append(f"### Bundle [{b.index}] ({len(b.cards)} cards)")
        for c in b.cards:
            cost = "X" if False else c.energy_cost
            up = "+" * (1 if c.upgraded else 0)
            text = c.resolved_rules_text or c.rules_text
            sections.append(f"  - [{c.index}] {c.name}{up} (cost={cost}): {text}")

    sections.append("\n## Output (JSON inside <decision>)")
    sections.append('`{"action": "choose_bundle", "option_index": <bundle_index>, "reasoning": "..."}`')

    return "\n\n".join(sections)
```

### `src/brain/tool_schemas.py`

```python
BUNDLE_TOOL = {
    "name": "bundle_action",
    "description": "Pick one bundle from a ScrollBoxes choice. All cards in the chosen bundle enter your deck.",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["choose_bundle"]},
            "option_index": {"type": "integer"},
            "reasoning": {"type": "string"},
            "strategic_note": {"type": "string", "description": _STRATEGIC_NOTE_DESCRIPTION},
            **_NOTE_SCOPE_SCHEMA,
        },
        "required": ["action", "option_index", "reasoning"],
        "additionalProperties": False,
    },
}

_STATE_TOOL_MAP["bundle_select"] = BUNDLE_TOOL
```

### `src/agent/loop.py` — choose_bundle execution

Add to `_execute_llm_decision` validation: action `choose_bundle` is in `available_actions` (no other special validation — the C# layer handles bounds).

After `await self._execute(action)` for `choose_bundle`, the C# `confirm_bundle` step happens automatically because our existing `selection.requires_confirmation` flow on the back-end already calls confirm. **Verify**: if `confirm_bundle` action stays explicit in upstream's flow (post `5286f2d`), we may need a follow-up `confirm_bundle` call. Test live before deciding.

### Reward card metadata consumption (1C)

Update `src/brain/prompts/reward.py` `build_card_reward_prompt` to use the new fields directly instead of joining knowledge DB:

```python
# Before:
card_meta = lookup_card(card.card_id, knowledge)  # cost/type/rarity from kb

# After:
cost_str = "X" if False else str(card.energy_cost)
type_str = card.card_type
rarity_str = card.rarity
```

Fall back to knowledge DB join only when fields are empty (old mod compat).

### Structured pile consumption (1B) — optional

`src/brain/prompts/_pile_fmt.py`: prefer `combat.player.draw_cards` (structured) over parsing the textual `draw` strings. Falls back when empty (old mod or when not on full state).

`src/memory/combat_delta.py` and `src/memory/combat_trace_delta.py`: use `card_id` from structured fields where available — eliminates the fragile `Strike+`-vs-`Strike` string parsing.

## Migration / backward compatibility

All Python changes must work against **both** the old mod (no `bundles[]`, no `resolve_rewards`, no enriched reward card fields) and the new mod, because:
- A user can downgrade.
- Tests run without a live mod.

Pattern: every consumer guards on field presence:

```python
if "resolve_rewards" in gs.available_actions:
    # new path
else:
    # legacy multi-step
```

Pydantic field defaults (`= ""` / `= 0` / `Field(default_factory=list)`) make missing fields silently empty, which the consumers treat as "fall back to legacy".

`config.RESOLVE_REWARDS_ATOMIC` defaults `true`. Set `false` to disable atomization for a run (e.g. comparing wall-clock between modes).

## Test plan

### Unit tests

| Test | What it verifies |
|---|---|
| `test_resolve_rewards_action_builder` | `actions.resolve_rewards(option_index=N)` shape; `option_index=-1` shape; absent param shape |
| `test_atomize_card_reward_pick` | `_maybe_atomize_card_reward` translates `choose_reward_card(2)` → `resolve_rewards(option_index=2)` when `resolve_rewards` in avail |
| `test_atomize_card_reward_skip` | translates `skip_reward_cards` → `resolve_rewards(option_index=-1)` |
| `test_atomize_falls_through_old_mod` | when `resolve_rewards` not in avail, returns `None` and legacy path runs |
| `test_atomize_skip_alternative_only_skip` | sacrifice alternative does NOT atomize |
| `test_bundle_selection_state_derived` | `gs.bundles` populated → `state_type == "bundle_select"` |
| `test_bundle_prompt_renders` | All bundles + cards present, decision schema reference present |
| `test_choose_bundle_action_builder` | `actions.choose_bundle(2)` shape |
| `test_reward_card_payload_card_type` | `RawRewardCardOptionPayload.card_type` round-trips |
| `test_pile_card_payload` | Structured pile field round-trips |
| `test_collect_rewards_skip_flag_irrelevant_when_unused` | Existing reward path tests continue to pass — verifies the b5066cc fix is no-op when skip never called |

### Integration tests

Re-run existing reward flow tests in `tests/test_loop_post_run.py`, `tests/test_loop_card_selection.py`, `tests/test_state_parser_*.py` (whatever exists) — must all pass.

### C# build verification

```bash
cd STS2-Agent-Fork/STS2AIAgent && dotnet build -c Release
```
Zero warnings, zero errors.

### Live smoke

Pre-deploy:
1. `python -m pytest tests/ --no-header -q` — full suite green (modulo the 2 pre-existing `test_loop_post_run` failures from the unrelated `finalize_session` refactor).
2. C# build clean.

Post-deploy (mod DLL copied to game's `mods/`):
1. **Reward atomization smoke**: `STS2_RESOLVE_REWARDS_ATOMIC=true python -m scripts.run_agent --steps 200 --runs 1 --no-postrun`. After first combat, inspect log: every card reward should produce **exactly one** `decision` with `action.action == "resolve_rewards"`, replacing the old 4–5-step sequence.
2. **Atomization regression**: `STS2_RESOLVE_REWARDS_ATOMIC=false python -m scripts.run_agent ...` — old multi-step flow still works.
3. **Bundle smoke**: optional — only triggers on ScrollBoxes (Ancient relic). Best-effort: enable `STS2_DEBUG_FORCE_RELIC=ScrollBoxes` if mod supports it, otherwise wait for natural occurrence and verify agent picks a bundle without getting stuck.
4. **Skip-card no-auto-claim**: in a card_reward state, manually trigger skip via debug; verify the skipped card is NOT in deck on next state.

### Regression invariants

- `runs/history.jsonl` keeps appending; no schema change to `RunRecord` needed.
- Memory extraction (`combat_delta.py`, `card_memory_extractor.py`) sees the same data shapes (additive fields only).
- Postrun stages (mistake_discovery, evolution) do not depend on missing-by-default counter fields.

## Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| `resolve_rewards` 20s timeout exceeded on slow machines | M | Mod side has `IsRewardFlowStable()` fallback returning current state; agent treats "pending" status the same as completed and re-polls next loop iteration |
| Atomic call fails mid-drain (e.g. mod-game desync) | L | Outer `_execute` already retries; if state is partial, next loop iteration sees partial state and `_handle_rewards` mechanical drain finishes the job |
| LLM picks `option_index` out of range | L | Mod falls back to first card (existing behavior); agent's `_validate_llm_decision` would have caught it earlier |
| Bundle screen never seen in testing | L | Add `STS2_DEBUG_FORCE_BUNDLE_SCREEN=1` flag (mod-side stub) OR rely on first natural occurrence; spec calls out as known gap |
| `confirm_bundle` step needed after `choose_bundle` | M | Smoke test confirms; if needed, add `await self._execute(actions.confirm_bundle())` after choose_bundle in loop |
| Cherry-pick conflicts with patch 0008 (`discard_potion`) | L | Different code regions; verified manually. If conflict appears at apply, resolve in favor of 0008 (our fix) and re-verify |
| Counter carve-out leaves dead code | L | Manually delete `_pendingCardRewardChoice` counter increments after cherry-pick; delete in same commit so no orphan branches |
| Tests reference removed counter fields | L | Counter fields aren't in our codebase yet, so no Python tests reference them. C# tests don't exist for these. No-op risk |

## Rollout

1. **Branch**: `upstream-sync-rewards-bundle-2026-04-28`
2. **C# patch series** (one commit per logical hunk):
   - `feat(mod): add resolve_rewards atomic action and skip-claim guard`
   - `feat(mod): add bundle dedicated payload`
   - `feat(mod): add reward card type/rarity/cost + structured pile cards`
3. **Python series** (logical units):
   - `feat(mcp): add resolve_rewards / choose_bundle / confirm_bundle action builders`
   - `feat(state): add bundle_select state_type and bundles[] payload model`
   - `feat(state): add structured pile + enriched reward card models`
   - `feat(prompts): add bundle prompt and decision tool`
   - `feat(loop): atomize card_reward decision via resolve_rewards under flag`
   - `feat(prompts): use structured reward card metadata`
4. **Update `STS2-Agent-Fork/VENDOR.md`**: bump merge-base, add 5 new patch numbers (or document as a single 0009 patch series).
5. **Run full pytest + dotnet build + 200-step live smoke** before merge.
6. **Default `STS2_RESOLVE_REWARDS_ATOMIC=true`** but document the env-var escape hatch.

## Out of scope / future

- Capstone screen — re-evaluate when STS2 actually adds a victory choice.
- Mid-turn counters — re-evaluate if Pinpoint/Stomp/Conflagration starts looking misplayed in mistake_discovery output.
- v0.6.1 GameDataExportService — re-evaluate when next major game version forces knowledge re-sync.
- Bundle/ScrollBoxes integration with skill-discovery (treating bundle pick as a deck-shaping decision worth retrospective scoring) — separate spec.
