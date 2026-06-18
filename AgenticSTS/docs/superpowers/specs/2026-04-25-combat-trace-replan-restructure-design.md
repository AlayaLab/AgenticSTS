# Combat Trace Replan/Plan-Block Restructure for Postrun Analysis

**Date:** 2026-04-25
**Status:** Design — pending implementation plan
**Related:**
- `docs/superpowers/specs/2026-04-24-combat-trace-postrun-analysis-design.md` (parent design — established the trace renderer + Turn 1/Turn 2 LLM pipeline)
- `src/memory/combat_trace_renderer.py` (current renderer, target of this restructure)
- `src/agent/loop.py` lines ~6796 / ~6836 (source of the `Plan [N/M]: <card> — <plan.reasoning>` format)

## 1. Problem

The current `combat_trace_renderer._render_plan` flattens every decision event in a round into either a `Plan` line (the first) or a `[REPLAN #N]` line (every subsequent). Each line carries the decision's full `reasoning` string, which itself starts with `Plan [N/M]: <card_name> — <plan.reasoning>`.

This produces three concrete pathologies in the trace consumed by Turn 1 (build_analysis) and Turn 2 (card_note_updater):

1. **`[REPLAN #N]` is misleading.** Most "replans" are not actual replans — they are individual step executions of the same plan. A 13-step plan produces `[REPLAN #1]` through `[REPLAN #12]` even though no replanning happened. The label suggests the agent kept changing its mind 23 times in one round.

2. **Reasoning text is duplicated per step.** A single `plan.reasoning` body of ~430 chars is repeated once per step. A 13-step plan repeats it 13 times. In the Round 1 example for Combat 1 (Fabricator) this alone consumes ~1700 tokens of pure repetition.

3. **Plan boundary signal is buried.** True replans (hand changed, enemy died, plan cut short) are tagged identically to step executions. The LLM cannot distinguish "the agent followed a 5-step plan to completion" from "the agent replanned 5 times in a row."

A secondary problem: state evolution between plans is not surfaced. The LLM sees pre-round hand and per-action plays, but not why a plan ended (Hidden Daggers added 2 Shivs, Adrenaline gave +2 energy, etc.) — which is precisely the information needed to interpret build behavior.

## 2. Scope

**In scope:**
- Restructure `_render_plan` and `_index_decisions` to group decisions into **plan blocks** by parsing the `Plan [N/M]:` prefix.
- Add a **Δ section** per plan block that diffs pre/post snapshots: player energy/block/powers/draw, hand additions and removals, enemy HP/intent/powers.
- Inject **first-appearance descriptions** for cards and powers introduced mid-combat, with per-combat dedup.
- Preserve the existing `Hand:`, `Player powers:`, `Enemies:`, and final `Cards played:` rendering.
- Maintain byte-identical Turn 1 / Turn 2 trace bytes (cache hit requirement from parent design).

**Out of scope:**
- Changing `extract_candidate_cards` (already reads from `combat.hand_at_start_per_round` / `cards_played_per_round`, not the rendered text — unaffected).
- Modifying the V2Backend cache_control plumbing.
- Touching the upstream `loop.py` reasoning format. The renderer reverse-engineers the existing format; no agent-side change required.
- Cross-combat dedup of card/power descriptions. Each combat is self-contained.
- Persisting plan-block boundaries in `CombatTracker` or any data store. Boundaries are derived purely at render time.

## 3. Architecture

### 3.1 Plan-block detection

Walk decisions in chronological order; group into blocks via this state machine:

```python
parsed = parse_reasoning(decision.reasoning)
# kind ∈ {plan_step, sub_action, end_turn, heuristic}
# fields: step_idx, plan_size, card_name, plan_reasoning_body, raw

if parsed.kind == "plan_step":
    is_new_block = (
        current_block is None
        or current_block.kind != "plan"
        or current_block.plan_reasoning_body != parsed.plan_reasoning_body
        or parsed.step_idx == 1   # explicit counter reset = new plan
    )
    if is_new_block:
        flush(current_block)
        current_block = PlanBlock.new(parsed)
    current_block.add_step(parsed, decision)

elif parsed.kind == "sub_action":
    # select_deck_card / confirm_selection — fold into the most recent
    # plan_step within current_block
    current_block.attach_sub_action(parsed, decision)

elif parsed.kind in ("end_turn", "heuristic"):
    flush(current_block)
    current_block = None
    emit_standalone(parsed, decision)
```

**Reasoning-text regex** (in `parse_reasoning`):
- `^Plan \[(\d+)/(\d+)\]: (.+?) — (.+)$` → plan_step
- `^Plan discard:` / `^Confirm hand selection` / `^Exhausting` etc. + decision.action ∈ {`select_deck_card`, `confirm_selection`} → sub_action
- `^Plan: end turn` or decision.action == `end_turn` → end_turn
- decision.source ∈ {`heuristic`, `random`} or none of the above → heuristic

**Boundary signals** (any of these starts a new plan block):
- `plan_reasoning_body` text differs from the current block's body
- `step_idx == 1` (counter reset — explicit replan)
- Previous block was `end_turn` or `heuristic`

The text-equality check is the primary signal; the `step_idx == 1` check is a defensive backstop for the rare case where two consecutive plans happen to have identical body text.

### 3.2 Plan-block output format

```
  [A] intended N → <card1>, <card2>, ...
      Reason: <plan_reasoning_body, single occurrence>
      Executed K/N: <executed_card_1>, <card with sub-action: (discarded X, Y)>, ...
      Δ:
        Player: energy A→B, block C→D, drew E; <exhausted/discarded notes>
          +power <Name(N)> — <description, first appearance only>
        Hand:
          +K <CardName> (from <source effect>) — <description, first appearance only>
        Enemy: <Name>: <hp_pre>→<hp_post> HP (-X), intent unchanged|<old>→<new>
          +power <Name(N)> — <description, first appearance only>
```

Field rules:
- **Header line** (`[X] intended N → ...`): always emitted. `X` is letter A, B, C, ... assigned in plan order within a round. The `intended` list is the M card names parsed from `Plan [N/M]:` prefixes; uses `×N` collapse for repeated identical names (`Shiv×4`).
- **Reason line**: emitted once per block, never duplicated. Plain prose, line-wrapped at ~80 chars in code (no hard requirement on the renderer to wrap; downstream LLMs handle either).
- **Executed line**: cards in chronological order; sub-actions folded into parens after the parent card (`Hidden Daggers+ (discarded Strike+, Defend+)`). Always shows `K/N` where K is executed count and N is intended count.
- **Δ section**: only emit non-empty subsections. Player line is emitted if any player field changed. Hand subsection is emitted if any card was added or removed beyond the played cards (e.g., card-generation effects, draws). Enemy line is emitted per enemy that exists in the snapshot, even if HP/intent unchanged (so the LLM can confirm "no damage" rather than infer it).
- **Sub-action attribution in Executed line**:
  - `select_deck_card` after Hidden Daggers / Calculated Gamble → `(discarded X, Y)`
  - `select_deck_card` after Purity / exhaust effect → `(exhausted X)`
  - `confirm_selection` → suppressed entirely (folded into the preceding sub-action's note)

### 3.3 Δ computation (per plan block)

Snapshot lookup contract (from parent design):
- A `state` event with `step == decision.step` represents pre-decision world state.
- The next `state` event with `step == decision.step + 1` represents post-decision world state.

For a plan block spanning decisions `[d_first ... d_last]`:

| Boundary | Snapshot |
|---|---|
| pre-Δ  | `state` event at `step == d_first.step` |
| post-Δ | next plan block's pre-Δ snapshot, OR `state` event at `step == d_last.step + 1`, OR (last plan in round) `state` event at next round's first decision step |

Field-level diff:

| Source | Diff rule |
|---|---|
| `player.energy` | absolute pre→post (e.g., `3→0`) |
| `player.block` | absolute pre→post |
| `player.hp` | only emit if changed |
| `player.powers` | by name: new → `+power X(N)`; stack changed → `X(N)→(M)`; removed → `-power X` |
| `player.hand` | set diff by rendered name; emit `+K <name>` for additions, suppress played cards (already in Executed) |
| `draw_pile` size | emit `drew K` when `len(post.draw_pile) < len(pre.draw_pile)` AND new cards appear in hand |
| `discard_pile` / `exhaust_pile` | emit `<card> exhausted` / `<card> discarded` when an entry appears in the post-pile that isn't in pre and matches a played card with that effect (Adrenaline, Blade Dance, Purity, etc.); otherwise suppress |
| `enemies[i].hp` | per enemy: pre→post; suffix `(-X)` when damaged. If post.hp ≤ 0 or enemy absent in post snapshot while present in pre, suffix `(killed)` and omit this enemy from subsequent rounds' Δ |
| `enemies[i].intent` | emit `intent <pre>→<post>` if changed, else `intent unchanged (<value>)` |
| `enemies[i].powers` | same rules as player.powers |

**Hand-add attribution heuristic**:
- If a play in the block is a known card-generation effect (Hidden Daggers → 2 Shivs+, Blade Dance → 4 Shivs, Backflip → 2 draws, Adrenaline → 2 draws), attribute additions to that card.
- If the block has multiple draw sources, fall back to `(drawn this plan)` without attributing to a specific card.
- Detection of "card-generation effect" is text-pattern based on the played card's `rules_text` (`/draw \d+ cards?/i`, `/Add \d+ .* into your Hand/i`, etc.). No hardcoded card list.

### 3.4 First-appearance card / power description

Maintain two per-combat sets initialized at the start of `_render_single_combat`:

```python
seen_cards: set[str] = set()
seen_powers: set[str] = set()
```

**Seeding** (entities considered "already shown" without re-description):
- Every card name in Round 1's `Hand:` block (the existing `_render_hand` already prints full descriptions there).
- Every power name in Round 1's `Player powers:` block (existing `_render_player_powers` prints descriptions).

Enemy powers are **not seeded**. The current `_render_enemies` only prints power names without descriptions, so enemy powers always go through the first-appearance path in Δ subsections (their description is fetched from the snapshot's `enemies[i].powers[j].description` field on first encounter).

**Δ rendering**:
- When a card or power appears in a Δ subsection, look up its name in the relevant set.
- If absent: emit `<name> — <description>` and add the name to the set.
- If present: emit `<name>` only.

**Identity**:
- Cards: rendered name including `+` and any `[Enchantment]` tag. `Shiv` and `Shiv+` are different identities.
- Powers: bare power name. `Phantom Blades(1)` and `Phantom Blades(2)` share an identity (only first occurrence carries description).

**Description source**: pulled from the same snapshot fields the existing renderer uses (`rules_text`, `description`). No `GameKnowledge` lookup. If the snapshot lacks the description for a card/power not seen before, emit the name without description and do not mark it seen (so a later snapshot that does carry the description gets one chance to render it).

### 3.5 End-turn handling

`end_turn` decisions become a standalone block (not a plan block):

```
  [end_turn] Reason: <decision.reasoning, prefix-stripped>
    Δ at turn end: <retained-cards summary if any> | hand discarded
```

Retention computation:
- If the next round's `hand_at_start` is available: retained = intersection of (pre-end_turn hand) and (next round hand_at_start).
- If retention count > 0: emit `<N> cards retained (Runic Pyramid) — <comma-separated names>`.
- If retention count == 0 and a hand existed: emit `hand discarded`.
- If next round is unavailable (e.g., last round of combat, killing blow): suppress `Δ at turn end` entirely.

Heuristic blocks (stuck recovery, foul-potion shop entry) get a single line: `[heuristic: <source>] <action> — <reasoning>`. No Δ.

### 3.6 Round output skeleton

The full per-round output preserves the existing top sections and replaces only the trailing plan area:

```
-- Round R -- energy E, hp H1→H2, dmg_dealt D, dmg_taken T, block_gained B
Hand:
- <card lines unchanged>
Player powers: <unchanged>
Enemies:
- <enemy lines unchanged>

Plans this round:
  [A] intended ...
      Reason: ...
      Executed K/N: ...
      Δ:
        Player: ...
        Hand: ...
        <Enemy>: ...

  [B] intended ...
      ...

  [end_turn] Reason: ...
    Δ at turn end: ...

Cards played this round (M): <chronological list with ×N collapse>
```

The final `Cards played` line is retained as a ground-truth fallback for the LLM.

## 4. Performance impact

### 4.1 Token budget

Empirical estimate against the Combat 1 / Round 1 / Fabricator example in conversation:

| Section | Old | New | Δ |
|---|---|---|---|
| Plan reasoning (24 decisions, 9 unique reasonings, 4 plan bodies × repetition) | ~8550 chars | 0 chars | -8550 |
| Plan reasoning (single occurrence per plan, 4 blocks) | 0 chars | ~1190 chars | +1190 |
| `[REPLAN #N]:` markers + action prefixes (24 lines) | ~1500 chars | 0 chars | -1500 |
| Plan headers `[X] intended N → ...` (4 blocks) | 0 chars | ~280 chars | +280 |
| Executed lines (4 blocks) | 0 chars | ~340 chars | +340 |
| Δ sections (4 blocks × ~3 lines × ~85 chars) | 0 chars | ~700 chars | +700 |
| First-appearance descriptions (5 cards + 1 power, ~75 chars each) | 0 chars | ~450 chars | +450 |
| `[end_turn]` block + Δ at turn end | ~280 chars (bare reasoning) | ~380 chars | +100 |
| `Cards played` line | ~200 chars | ~200 chars | 0 |
| **Round total** | **~10250 chars (~2560 tok)** | **~3540 chars (~885 tok)** | **-65%** |

The dominant savings come from collapsing repeated plan reasoning (4×430 + 12×430 = 6880 chars saved on plans A and C alone). The Δ section and first-appearance descriptions add ~1150 chars per round but stay well below the savings.

### 4.2 Round-shape sensitivity

| Round shape | Δ vs old |
|---|---|
| 1 plan, fully executed, no replan, ≤3 actions | +50 to +80 tokens (Δ overhead on minimal old-format size) |
| 1 plan, fully executed, ≥5 actions | -30% to -50% |
| Multi-plan with replans (typical mid/late-fight rounds) | -50% to -65% |
| Stuck-recovery heavy round | small net change (heuristic blocks render comparably) |

Aggregated over a typical 6-10 round combat trace, expected net change is **-30% to -50% tokens** with no loss of decision-relevant information.

### 4.3 Compute cost

- Plan-block grouping: O(D) per round, single pass over decisions.
- Snapshot diff: 2 lookups per block × O(E) over events (existing `_find_matching_state_snapshot`). For a typical 4-block round, 8 lookups × ~500 events ≈ 4000 list scans. Acceptable; can be optimized to O(log E) with pre-sorted index if needed (deferred).
- Per-combat `seen_cards` / `seen_powers` sets: trivial.

## 5. Error handling

Layered fail-closed: any failure degrades to current-format trace or omitted Δ rather than aborting render.

**Renderer-internal failures**:

| Condition | Behavior |
|---|---|
| `parse_reasoning` cannot match any pattern | Treat as `heuristic`, emit single line, do not group |
| `step_idx > plan_size` (malformed prefix) | Force new plan block, log warning, continue |
| pre-snapshot for plan block missing | Skip Δ for this block; emit Reason + Executed only |
| post-snapshot missing for non-final plan block | Skip Δ for this block (cannot meaningfully diff a single mid-round plan against round aggregates) |
| post-snapshot missing for the **last** plan block of a round | Emit partial Δ using `CombatTracker.rounds[i]` round aggregates: player hp/block deltas and per-enemy hp deltas computed against the round's start values; suppress hand/draw/power diffs (round aggregates do not capture these); mark `Δ: (round-aggregate fallback)` |
| Snapshot present but `combat` field malformed | Skip Δ for the block |
| Card/power description missing in snapshot | Emit name without description; do not mark as seen |
| Sub-action without preceding plan_step in block | Emit as standalone line `(sub-action: <reasoning>)`; do not crash |

**No graceful upgrade path** for legacy traces: the renderer is the single source. Existing in-flight runs that already produced traces are unaffected (this is a render-only change; no persisted data shape changes).

## 6. Testing strategy

Extend `tests/test_combat_trace_renderer.py` (currently exists per parent design) with:

**Plan-block grouping**:
- Single plan block, all steps executed → one `[A]` block, no replans
- Two plan blocks separated by hand change → `[A]` + `[B]`, body text differs
- Plan body identical but `step_idx` resets to 1 → forced new block (regression guard)
- Sub-action interleaved with plan steps → folded into parent's Executed line, not its own block
- Heuristic decision (source=heuristic / random) → standalone block, no plan grouping

**Δ computation**:
- Hidden Daggers played → `Hand: +2 Shiv+ (Hidden Daggers)` with description on first appearance
- Power gained from Power-card play → `+power X(1) — desc`
- Power stack increased on subsequent play → `X(1)→(2)` no description
- Enemy damage applied → `<Enemy>: 150→126 HP (-24)`
- Enemy intent unchanged → `intent unchanged (<value>)`
- Multiple enemies, one dies → dead enemy emits `(killed)` and is omitted from subsequent rounds' Δ

**Snapshot mismatch fallbacks**:
- Pre-snapshot missing → block renders without Δ
- Post-snapshot missing, CombatTracker round summary present → partial Δ with player aggregates only
- Both snapshots missing → block renders Reason + Executed only

**First-appearance dedup**:
- Card in Round 1 starting hand → not re-described when re-played in Round 2 Δ
- Card generated by Blade Dance in Round 1 → described once in Round 1 Δ, not again in Round 2 Δ
- Power gained in Round 1, lost in Round 2, regained in Round 3 → described only once (in Round 1)

**End-turn handling**:
- end_turn with Runic Pyramid + 4 retained cards + next round available → emits retained-cards line with names
- end_turn without Runic Pyramid → emits `hand discarded`
- end_turn at killing blow (no next round) → suppresses Δ at turn end

No integration test required — the renderer is pure (no LLM, no I/O beyond the events list).

## 7. Risks

- **Reasoning regex brittleness.** If `loop.py` changes the `Plan [N/M]: <card> — <body>` format, plan-block grouping silently regresses to per-decision flat output. **Mitigation**: unit test asserts the regex against the live format string in `loop.py:6796` (test imports the format and reformats it back). If the format changes, test fails loudly.
- **Hand-add attribution misattributes drawn cards.** If a plan plays multiple draw cards, attribution may be wrong. **Mitigation**: spec mandates `(drawn this plan)` fallback when ambiguous; never emit a wrong attribution.
- **Description source missing for new card types.** Enchanted cards or cards added by future game updates may lack `rules_text` in snapshots. **Mitigation**: emit name only and do not mark seen, so a later snapshot with the description gets a chance.
- **Trace bytes mismatch between Turn 1 and Turn 2.** This restructure does not change the call site; the renderer is invoked once per run and the resulting string is passed to both turns. Cache hit invariant from parent design is preserved.
- **LLM may treat `intent unchanged` as filler and ignore Δ.** If postrun analysis quality does not improve despite the restructure, follow-up may shorten unchanged Enemy lines further. Tracked via Turn 1 quality spot-check post-rollout.

## 8. Non-goals (explicit)

- No upstream `loop.py` change. The renderer reverse-engineers the existing format.
- No agent-side persistence of plan-block boundaries. Boundaries are render-time derivations.
- No cross-combat description dedup. Each combat is a self-contained block in the trace.
- No support for non-V2 engine traces. V2 is the sole engine per CLAUDE.md.
- No JSON-formatted trace output. Plaintext only, optimized for LLM readability.
- No knock-on changes to `extract_candidate_cards` or `card_note_updater`. They consume `combat.cards_played_per_round` directly, not the rendered text.

## 9. Rollout

Single-step rollout — restructure is render-side only, no config gate, no data migration:

1. Land implementation + unit tests on a feature branch.
2. Manual smoke: run `python -m scripts.run_agent --steps 50 --runs 1` on Silent, inspect emitted trace bytes against this spec.
3. Side-by-side spot check: run Turn 1 (build_analysis) on the same combat with old vs new trace, compare `build_summary` quality.
4. Merge to main once smoke passes.

Rollback: revert the renderer commit. No persisted state to undo.
