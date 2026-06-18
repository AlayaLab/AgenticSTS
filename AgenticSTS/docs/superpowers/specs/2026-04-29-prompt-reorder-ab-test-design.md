# Prompt Reorder A/B Test — Design

**Date**: 2026-04-29
**Status**: Approved (B1 only; B2 deferred pending B1 results)
**Author**: Claude + xc

## Problem

Current `card_reward` prompts (and likely other strategic builders) place `## Available Cards` — the actual decision options — in the middle of the user message, sandwiched between retrieved knowledge (top) and the evaluation framework (bottom). Empirical observation matches Liu et al. 2024's "Lost in the Middle" finding: information in the middle of long contexts is recalled with ~30% lower accuracy than information at start or end.

A representative `card_reward` user message (verified from `logs/run_20260429_103038_40df2787.jsonl`, prompt length 8943 chars) has this header order:

```
1.  ## Expert Knowledge (retrieved skills)     [TOP]
2.  ## Deck Building Insights
3.  ## Card-Specific Insights
4.  ## Strategic Thread
5.  ## Game Knowledge
6.  ## Card Mechanics
7.  ## Card Reward                              [decision header — MID]
8.  ## Current Deck (12 cards)
9.  ## Relics: ...
10. ## Upcoming Act Boss
11. ## Available Cards                          [THE OPTIONS — MID, U-shape worst zone]
12. ## Keyword Glossary
13. ## Evaluation — Boss Damage Check           [TAIL]
14. ## Build Trajectory Check
15. ## Decision Format
```

`## Available Cards` is the highest-stakes content in the prompt (the model literally must read each card precisely to choose), but it sits exactly where attention is weakest.

## Hypothesis (B1)

Moving `## Available Cards` from its current mid position to immediately before `## Evaluation — Boss Damage Check` will improve decision quality without regressing reasoning quality. This is the smallest possible change: a single section move within `src/brain/prompts/reward.py`, no other files touched.

Resulting tail cluster:

```
...
## Upcoming Act Boss
## Keyword Glossary
## Available Cards                              ← moved here ★
## Evaluation — Boss Damage Check
## Build Trajectory Check
## Decision Format
```

Why this specific move:
1. The options are now adjacent to the evaluation rubric — the model reads "here are the choices" → "here's how to evaluate" → "here's the output schema" as a single coherent decision block.
2. `## Keyword Glossary` stays before `## Available Cards` because the glossary defines terms that appear in card text — keeping that order preserves dictionary-before-use semantics.
3. `## Upcoming Act Boss` stays where it is — it informs but does not directly evaluate the cards.

## Non-Goals

- B2 (full structural reordering) is deferred. If B1 passes, we may extend; if B1 fails, B2 is unlikely to fare better.
- Combat plan, shop, rest, event, map prompts are not touched in this experiment.
- System prompts (`SYSTEM_COMBAT`, `SYSTEM_DECKBUILD`, etc.) are not modified.
- Retrieval logic (`compose_skill_context`, `format_working_context`) is not modified.

## A/B Harness Design

### Data source

`logs/run_*.jsonl` contains `llm_call` events with full `system_prompt`, `prompt` (user message), `response`, `model`, and `call_type='v2_single_call'`. We sample `card_reward` calls by checking whether the `## Card Reward` header appears in the user message.

### Sample selection

- **N = 30** card_reward calls
- Source: most recent 100 run files with `len(prompt) > 5000` (filter out trivial cases)
- Stratify across acts (Act 1, 2, 3) at roughly 10/10/10 to cover all boss-target ranges
- Stratify across characters when available

### Treatment construction

For each sampled call:
- **A (control)**: use `prompt` field verbatim from the JSONL
- **B (treatment)**: regex-relocate the `## Available Cards` block to immediately before `## Evaluation — Boss Damage Check`. The move preserves all content, only changes position. Implementation: a pure-text reorder helper that finds the two sections and swaps the slice.

### Sampling and judging

For each (call, version) pair:
1. Send to the **same gameplay model** that originally produced the response (recorded in `model` field). Same `system_prompt`. Temperature 0.3 (slight noise floor).
2. Sample **3 times** per version → 6 responses per call → 180 total responses for N=30.
3. **L1 — decision agreement**: extract `option_index` from each response's `<decision>` block. For each call, compute (a) within-version agreement rate and (b) cross-version agreement rate.
4. **L2 — blind quality judge**: for calls where A and B picked different options ≥1 time, send (game_state_summary, A_response, B_response) to a stronger model (Opus 4.7 or GPT-5.4 thinking) with rubric. Judge does NOT know which version is which (randomize order, label "Option 1" / "Option 2").

### Judge rubric

Score each response on 4 dimensions, 1–5 scale, with one-line justification:
1. **Decision soundness** — does the chosen card improve the deck given current state and boss matchup?
2. **Reasoning coverage** — does the response cite the relevant deck dimensions (Damage/Defense/Draw/Energy), boss DPS target, and rarity considerations?
3. **Strategic coherence** — does it align with the Strategic Thread / build trajectory?
4. **Risk awareness** — does it acknowledge what's being given up (skipped cards, deck bloat, archetype dilution)?

Final score = sum of the 4 dimensions (max 20). Judge picks a winner: A, B, or tie.

### Pass criteria

Tier ordering, evaluated in sequence:

1. **Hard regression check** — if B's mean L2 total score is **> 1 point lower** than A's (out of 20), or if B causes **>10% increase in malformed JSON / missing fields**, reject and stop.
2. **Decision agreement** — if A/B agree on the same option in **≥80%** of calls, the change is essentially silent. Inconclusive: ship as quality-neutral if L2 also non-regressing.
3. **Win signal** — if B's L2 win rate (excluding ties) is **≥0.55** with N≥15 disagreements, this is the green-light signal. Binomial p < 0.10 is sufficient evidence at this sample size.
4. **Mixed** — if B wins on some dimensions but loses on others, log details and bring back to brainstorm before rolling out.

### Cost estimate

- Gameplay model resamples: 30 calls × 2 versions × 3 samples = 180 calls. At ~$0.01 per Strategic-tier call (Gemini 2.5 Pro / GPT-5.4), ~$1.80.
- Judge calls: ~15 disagreements × 1 judge call (Opus 4.7) ≈ ~$1.50.
- **Total: ~$3-5.**

## Rollout Plan (if B1 passes)

1. Modify `src/brain/prompts/reward.py::build_card_reward_prompt`:
   - Move the `## Available Cards` block (currently lines ~88-148) to immediately before the `## Evaluation — Boss Damage Check` block (currently line ~181).
   - Preserve all content. Pure reorder.
2. Update affected golden snapshots in `tests/regression/` — verify each diff is a pure reorder, no content drift.
3. Add a brief CHANGELOG entry pointing at this spec.
4. Smoke run: `python -m scripts.run_agent --steps 50 --runs 1` to verify no exception.
5. Optional: run as new condition in next ablation round (`pilot-2026-04-30-prompt-reorder`) for end-to-end win-rate signal across 10-20 runs.

If B1 passes, **defer** decision on B2 (the larger structural change) until we have at least one ablation round of B1 vs current. Reason: B1 + B2 conflate two effects; isolating B1 first preserves attribution.

## Implementation Files

A/B harness (new):
- `scripts/prompt_ab_test.py` — main entry point. Samples calls, generates B variants, runs harness, prints summary.
- `scripts/_prompt_ab/` — package
  - `sampler.py` — load JSONL, filter card_reward, stratify, return list of (run_id, call_index, system_prompt, user_message, original_response, model)
  - `transform.py` — `apply_b1(user_message: str) -> str` (single regex relocate of `## Available Cards`)
  - `judge.py` — blind A/B judge with rubric, calls Opus 4.7 / GPT-5.4
  - `report.py` — aggregate scores, decision agreement, malformed-rate, write JSON + markdown summary

Production change (gated on harness pass):
- `src/brain/prompts/reward.py` — single block relocation in `build_card_reward_prompt`.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| B1 also affects malformed-output rate | L1 includes JSON validity check; rejected if >10% increase |
| Different gameplay models behave differently | Resample using the SAME model that produced the original response |
| 3 samples per call has high variance | Document confidence intervals; if borderline, increase to 5 samples |
| Judge model bias toward longer / shorter responses | Rubric weights coverage but caps at 5; rubric is fixed in prompt |
| The original response in JSONL was already good — reorder makes it worse | This IS what we want to detect; pass criteria reject regressions |

## Spec Self-Review Notes

- ✅ No "TBD" placeholders.
- ✅ Internal consistency: B1 scope, harness design, and rollout plan all reference the single section move.
- ✅ Scope check: focused enough — one builder change, one experiment, deferred B2 explicitly.
- ✅ Ambiguity: pass criteria are numerically explicit (80%, 55%, p<0.10, 1-point regression).
- ✅ The "non-goals" section explicitly lists what's NOT in scope to prevent scope creep during implementation.
