# Prompt Evolution (PE) Deprecation — Negative Result

**Date:** 2026-04-18
**Status:** Implemented. Code removed; historical data archived under `data.snapshots/pe-deprecated-2026-04-18/`.

## TL;DR

Over a 10-day period (2026-04-06 to 2026-04-16), the postrun "Prompt Evolution" pipeline proposed **33 prompt patches**, of which **0 were promoted** and **0 were applied to source files**. Every patch was either rejected on A/B replay (30/33 for making the LLM produce schema-invalid decisions; 2/33 for no improvement on positive cases; 1/33 for insufficient test coverage), or pre-filtered. The backup directory that `PromptPatchApplier` would have written to (`data/evolution/patch_backups/`) was never created — no patch ever survived promotion to reach the apply step.

We remove the entire PE pipeline (`src/brain/prompt_patch_store.py`, `src/brain/prompt_patch_applier.py`, `src/brain/prompt_ab_tester.py`, the `propose_prompt_edit` evolution tool, and all PE-specific config, loop hooks, and tests). The A/B replay validation gate worked correctly — it refused to promote broken patches. The upstream generator (the postrun evolution LLM authoring prompt edits) was the failure point: critiques grounded in gameplay logs cannot reliably produce prompt edits that preserve downstream decision-schema validity.

## What PE was

The pipeline, introduced 2026-04-13, worked as follows:

1. During postrun evolution, the LLM could call `propose_prompt_edit` with structured `code_edits` (exact `old_text` → `new_text` targeting `.py` prompt source files) and `prompt_effect` (the corresponding text-level change in the assembled prompt).
2. `PromptPatchStore` persisted candidates to `data/evolution/prompt_patches/prompt_patches.jsonl` with a lifecycle (`pending` → `promoted`/`rejected` → `applied`).
3. On the following run's postrun, `PromptABTester` replayed each pending patch against 3 positive and 7 negative cases sampled from `logs/run_*.jsonl`, called the LLM with both A (original) and B (patched) prompts, validated the B-response against the decision-schema parser, and asked an analysis-tier LLM judge to rate `BETTER_B` / `SAME` / `WORSE_B` / `INVALID_B`.
4. Patches with sufficient `BETTER_B` on positive cases *and* no regression (≤ 1 `WORSE_B` on negatives) were promoted.
5. `PromptPatchApplier` wrote promoted patches to the source files, with backups.

## Empirical results

Source: `data/evolution/prompt_patches/prompt_patches.jsonl` (now at `data.snapshots/pe-deprecated-2026-04-18/prompt_patches/`).

| Metric | Value |
|---|---|
| Total unique patches proposed | 33 |
| Status distribution | 33 rejected, 0 promoted, 0 applied |
| Backups written | 0 (the `patch_backups/` directory never existed) |

Rejection-reason breakdown:

| Reason | Count |
|---|---:|
| `INVALID_B: N response(s) failed decision validation` (any N) | 30 |
| `no improvement on positive cases (need ≥1 BETTER_B)` | 2 |
| `insufficient test cases (0/5)` | 1 |

A representative rejection (patch `47936239…`, `src/brain/prompts/rest.py`): the LLM proposed adding a lookahead rule — "count every fight until the next guaranteed rest site; bias Rest over non-run-defining upgrades when an elite chain is imminent." On replay, 3 of 3 positive cases produced `BETTER_B` judgments, but 7 of 7 negative cases produced `INVALID_B` — the modified prompt destabilized decision output to the point where the downstream parser could no longer extract an action.

This pattern dominates. In 30 of 33 cases, the proposed edit (whatever its stated intent) caused the decision-emitting LLM to produce outputs that the schema parser could not decode at all.

## Why the pipeline failed

The validation gate functioned correctly. The failure is upstream:

1. **The generator lacks the right grounding.** The postrun LLM sees `logs/run_*.jsonl` — state transitions, decisions, outcomes. It sees *what happened* but not *why a specific prompt wording led to a specific reasoning chain*. To propose an edit that preserves schema validity and improves decisions, it would need a model of how the exact phrasing of the prompt shapes the decision-model's output format — information that is not recoverable from logs.

2. **Prompt edits are a high-dimensional structured intervention.** A skill is a free-form string retrieved on trigger match; a small error degrades retrieval quality but does not break downstream parsing. A prompt edit mutates the input to a structured-output LLM call; a small error breaks the output schema. The blast radius is asymmetric.

3. **The A/B gate exhibits survivorship bias.** Because so many patches fail `INVALID_B` on negative cases, the gate never sees a patch whose behavioral effect could be evaluated. We get no signal on whether *any* prompt edit the postrun LLM could propose would improve decisions if it first cleared the schema bar.

4. **Most improvements the postrun LLM actually wants to make are not prompt-level.** Inspection of the 33 proposals shows the intent is usually "teach the agent a contextual heuristic" (when to rest, which cards synergize, how to weight an option). These are naturally skills with triggers, not universal prompt modifications. The pipeline was mis-routing these inputs.

## Decision

Remove PE. All learning flows into L4 memory and L5 skills:

- L1 (system prompts) and L2 (state-specific prompt templates) are **human-authored and immutable** except for game-version patches (via `scripts/apply_patch.py`, which handles STS2 version updates — unrelated to PE).
- L4 (memory) accumulates episodic facts, per-enemy / per-card / per-event longitudinal records, consolidated guides.
- L5 (skills) accumulates trigger-matched tactical rules with a hypothesis lifecycle.
- Dynamic tools (`data/evolution/tools/*.py`) continue to be authored by postrun.

A future "L1/L2 slimming" task (tracked in `CLAUDE.md` Active TODOs) will migrate heuristics currently embedded in L1/L2 prompts (4-dimension card evaluation, Boss DPS check, Build Trajectory Check, Smith-default, HP conservation, potion timing) into seed skills. After that migration, L1/L2 contain only game mechanics and output schema. All adjustable heuristics live in L5 where postrun evolution already has a working write path.

## Why this is a contribution, not a failure

PE's 10-day, 33/0 record is a clean empirical finding worth reporting in the EMNLP submission:

> We implemented a closed-loop prompt-evolution pipeline (structured code edits + A/B replay validation on logged gameplay) for a self-evolving LLM agent, and found that 33 of 33 autonomously proposed patches failed validation — almost entirely because the patched prompt destabilized the downstream decision schema. We argue that postrun LLM critique, when applied to authoring-layer prompt text without a grounded model of the prompt-to-decision mapping, produces fragile edits that a correctly designed validation gate must exhaustively reject. Our resulting architecture confines self-evolution to retrieval-augmented layers (L4 memory, L5 skills) and dynamic tools, each with its own evidence-gated write path, and treats the system prompt as an immutable human-authored contract.

This framing supports a cleaner cross-model generalization story (C2) and personality analysis (C4) in the paper — L1/L2 are fixed per experiment, so observed model differences reflect the model's reasoning, not divergent prompt evolution.

## What was removed

Source files (1053 lines):

- `src/brain/prompt_patch_store.py` (296 lines)
- `src/brain/prompt_patch_applier.py` (166 lines)
- `src/brain/prompt_ab_tester.py` (591 lines)

Test files (3):

- `tests/test_prompt_patch_store.py`
- `tests/test_prompt_patch_applier.py`
- `tests/test_prompt_ab_tester.py`

References removed from:

- `src/agent/loop.py` — `_prompt_ab_task` instance var, `_harvest_prompt_ab_results`, `_run_prompt_ab_test`, both call sites.
- `src/brain/evolution_engine.py` — `_handle_propose_prompt_edit` (85 lines), `_render_prompt_source` (68 lines), `_render_pending_proposals` (26 lines), tool-dispatch entry, system-prompt guidance mentioning PE, `proposal_count` field, plus state-type-tracking code that only fed `_render_prompt_source`.
- `src/brain/write_tools.py` — `PROPOSE_PROMPT_EDIT` schema (~95 lines), `MUTATING_WRITE_TOOLS` entry, module docstring line.
- `config.py` — `PROMPT_EVOLUTION_ENABLED`, `PROMPT_AB_*`, `PROMPT_PATCH_DIR` (14 lines).
- `tests/test_evolution_engine.py` — `test_propose_prompt_edit`, `test_pending_proposals_included`, `test_logged_decision_digest_renders_prompt_source_without_dict_access`; tool-count/names assertions updated from 6 tools to 5.
- `tests/test_session_logger.py` — replaced `"propose_prompt_edit"` in an `action_types` example with `"write_skill"`.

Docs updated:

- `CLAUDE.md` — removed PE directory listing, added 2026-04-18 progress entry, deprecated the 2026-04-13 progress entry, added "L1/L2 slimming" and "write gate + retriever scope filter" to Active TODOs.
- `AGENTS.md` — Current Project Status section rewritten.
- `docs/2026-04-09-postrun-enrichment-design.md` — top banner marks PE sections as superseded.
- `docs/archive/detailed-technical-decisions.md` — deprecation note at top.
- `docs/skills_tools_audit_cn.md` — deprecation note at top (Chinese).

Data archived to `data.snapshots/pe-deprecated-2026-04-18/`:

- `prompt_patches/prompt_patches.jsonl` — the 33 rejected patches with full A/B verdicts.
- `proposals/prompt_edit_*.json` — legacy NL proposals.

Kept (unrelated to PE despite similar naming):

- `scripts/apply_patch.py` — STS2 game version update pipeline.
- `scripts/ab_test_*.py` — standalone one-shot A/B experiments (do not depend on PE infrastructure).
- `data/evolution/ab_test_results/` — output of those one-shot scripts.

## Verification

All 1356 tests pass (1395 before − 39 deleted = 1356) after removal. No runtime callers remain for any PE symbol (`grep -E "prompt_patch|prompt_ab|PromptPatch|PromptAB|propose_prompt_edit|PROMPT_EVOLUTION|PROMPT_AB_|PROMPT_PATCH_DIR|_prompt_ab_task|_harvest_prompt_ab_results|_run_prompt_ab_test"` across `src/` returns empty).
