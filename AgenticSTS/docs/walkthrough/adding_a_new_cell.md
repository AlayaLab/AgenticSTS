# Adding a new cell to the ablation matrix

Step-by-step procedure for extending the published 5-cell ablation with a
sixth experimental cell. Audience: researchers who have already run
`python -m scripts.reproduce.reproduce_table_2` successfully and want to
probe a hypothesis the paper does not test.

This walkthrough is procedural; for the design rationale of the existing
cells see [`paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/methodology.tex`](../../paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/methodology.tex)
§ "The 5-condition decomposition at fixed A0" and
[`docs/reference/ABLATION.md`](../reference/ABLATION.md).

---

## What you'll build

A worked example: a `no-strategic-thread` cell. Identical to `mode-a`
except `STS2_STM_ENABLED=false` — strategic-thread notes are turned off.
This isolates the hypothesis:

> Does the Strategic Thread (`STM._strategic_notes`) contribute any of the
> L5 lift, or is the lift entirely from triggered L5 skills?

`mode-a` is the natural control: full prompts, expert L5 seeds, no L4
memory, no postrun. The new cell flips exactly one knob — `stm` — so any
difference falls on that single mechanism.

You will not commit a fork of the paper; you'll add a new cell to the
running matrix locally, generate 10 trajectories under your own
`experiment_tag`, and add a row to the reproduce pipeline so the new cell
appears next to the published five.

---

## Step 1: Decide the config

The cell is fully specified by the `Condition` dataclass fields at
[`scripts/run_ablation.py:106`](../../scripts/run_ablation.py). Every
field maps to an env var via `Condition.to_env_overrides()` at
[`scripts/run_ablation.py:163`](../../scripts/run_ablation.py); these
overrides are passed into the per-run subprocess and pinned by
`_PRESERVE_IF_SET` in `config.py` so `.env` cannot leak through.

Knob-by-knob diff against `mode-a`:

```
field                          mode-a       no-strategic-thread
condition_id                   {m}-mode-a   {m}-no-strategic-thread
skills                         True         True
memory                         False        False
evolution                      False        False
prompt_variant                 "full"       "full"
hint_filter                    False        False
knowledge_strict               False        False
stm                            False        False           # mode-a already off
combat_conv                    True         True
boss_hp                        True         True
postrun                        False        False
disable_skill_seeds            False        False
use_seed_stubs                 False        False
seed_stub_fill_enabled         False        False
```

Re-read the diff: in `mode-a` the field `stm` is already `False`. The
"vs `mode-a`" example is the cleanest worked diff *structurally* but
isolates no new variable — `mode-a` itself already answers the question.
For a non-trivial cell pick a knob the existing five do not flip. A
better worked example: `mode-a-with-stm`, i.e. `mode-a` plus
`STS2_STM_ENABLED=true`:

```
field                          mode-a       mode-a-with-stm
condition_id                   {m}-mode-a   {m}-mode-a-with-stm
skills                         True         True
memory                         False        False
evolution                      False        False
prompt_variant                 "full"       "full"
hint_filter                    False        False
knowledge_strict               False        False
stm                            False        True            # flipped
combat_conv                    True         True
boss_hp                        True         True
postrun                        False        False
disable_skill_seeds            False        False
use_seed_stubs                 False        False
seed_stub_fill_enabled         False        False
```

Use `mode-a-with-stm` for the remainder of this walkthrough. A single
flipped knob, no surprise downstream effects, matches an actual unanswered
question from the paper.

Before continuing, confirm you have read
[`docs/reference/ABLATION.md`](../reference/ABLATION.md) §
"Experiment isolation rules". The five rules there apply to your new
cell verbatim.

---

## Step 2: Pick an experiment tag

Existing tags use the pattern `{family}-pilot-{date}-A{ascension}-{cell}`,
see [`scripts/reproduce/_lib.py:24`](../../scripts/reproduce/_lib.py):

```python
FIXED_A0_CELLS: list[tuple[str, str]] = [
    ("baseline-strict", "gemini-pilot-2026-05-08-A0-baseline"),
    ("prompt-only",     "gemini-pilot-2026-05-09-A0-prompt-only"),
    ("mode-a",          "gemini-pilot-2026-05-09-A0-mode-a-makeup"),
    ("mode-b-frozen",   "gemini-pilot-2026-05-12-A0-mode-b-frozen"),
    ("full-frozen",     "gemini-pilot-2026-05-08-A0-full-frozen"),
]
```

Pick a tag that does not collide with any published tag. Suggested form
for a personal experiment:

```
{your-handle}-{date}-A0-mode-a-with-stm
```

Concrete:

```
ada-2026-06-01-A0-mode-a-with-stm
```

The tag is the only thing that lets your runs be retrieved after the fact
— `filter_cell()` in `_lib.py:328` selects records by exact tag string.
Tags also drive `scripts/run_agent.py::_load_ascension_stats_for_session()`
to keep ascension tracking session-local (your run will not contaminate
the global `ascension_stats.json`).

If you intend to publish, re-run an existing cell alongside the new one
under the same date prefix (e.g. `ada-2026-06-01-A0-mode-a-control`) so
your backbone-drift control is matched to your treatment.

---

## Step 3: Wire `run_ablation.py`

Open [`scripts/run_ablation.py`](../../scripts/run_ablation.py) and find
`build_condition_matrix` at line 230. The existing cells are appended in
order inside `for m in models:`. Add a sixth `matrix.append(Condition(...))`
inside the loop, after the `mode-a` block (line 272) and before the
`self-evolve` block (line 276):

```python
        # mode-a-with-stm: like mode-a but Strategic Thread on.
        # Isolates the STM contribution at the L5-only setup
        # (no L4, no postrun, expert seeds load).
        matrix.append(Condition(
            condition_id=f"{m}-mode-a-with-stm", model_family=m,
            skills=True,           # expert seeds load
            memory=False,          # no L4 cross-run
            evolution=False,       # no postrun evolution
            prompt_variant="full",
            hint_filter=False,
            knowledge_strict=False,
            stm=True,              # ← the only flip vs mode-a
            combat_conv=True,
            boss_hp=True,
            postrun=False,         # no postrun stage
        ))
```

A few requirements the snippet has to honor for the existing harness to
pick it up:

- `condition_id` MUST start with `f"{m}-"`. The kind filter in
  `filter_matrix_by_conditions` at `scripts/run_ablation.py:316` splits
  on the first hyphen and matches the suffix, so a missing `{m}-` prefix
  means `--conditions` will never select your cell.
- Use the dataclass field defaults — every flag has one — and only
  override the knobs you intend to differ from defaults. This keeps the
  diff against the paper readable in a `git diff`.
- Do not change the order of existing `matrix.append(...)` blocks.
  Downstream resume logic identifies cells by `condition_id` not by
  index, but reviewer diff readability still benefits.

Also update the help text for `--conditions` at
`scripts/run_ablation.py:373` and the docstring at the top of the file
(line 6 onward) so future readers see your kind listed. Optional but
helpful when collaborating.

While editing, do NOT touch the existing five conditions. Reproducibility
of the published numbers depends on their dataclass fields staying byte-
identical to the SHA `1888a62` snapshot.

---

## Step 4: Run the experiment

Single-model, 10 runs, isolated tag, only your new condition:

```bash
python -m scripts.run_ablation \
  --tag ada-2026-06-01-A0-mode-a-with-stm \
  --runs-per-condition 10 \
  --models gemini \
  --conditions mode-a-with-stm \
  --character Silent \
  --ascension 0 \
  --launch-game \
  --api-port=auto \
  --monitor-port=auto
```

Notes:

- `--ascension 0` pins the ladder to A0, matching the published headline
  cells. Do not use `--ascension auto` if you want the cell to be pooled
  with the fixed-A0 stream. See `docs/reference/ABLATION.md`
  § "Experiment isolation rules".
- `--launch-game` plus `--api-port=auto` / `--monitor-port=auto` lets
  multiple parallel orchestrators coexist by claiming distinct TCP ports.
  See [`docs/reference/ABLATION.md`](../reference/ABLATION.md)
  § "Multi-agent parallel runs". Two-three concurrent instances are
  routine on a single workstation.
- Wall-clock per run on the fixed-A0 Gemini cells is roughly 75-90
  minutes. 10 runs single-threaded ≈ 13-15 hours. Three concurrent
  agents ≈ 5 hours.
- Resume is automatic. Ctrl-C, then re-run with the same `--tag`. The
  orchestrator counts existing matching records in
  `runs/history.jsonl` and only fills the remaining slots
  (`count_existing_runs` at `scripts/run_ablation.py:61`).
- Aborted runs (`agent_abort`, `mcp_error`, `interrupt`) are not counted
  toward the 10. The harness retries each slot up to 3 times before
  giving up — see `RETRY_CAP_PER_SLOT` at line 58.

Verify before launch:

```bash
python -m scripts.run_ablation \
  --tag ada-2026-06-01-A0-mode-a-with-stm \
  --models gemini \
  --conditions mode-a-with-stm \
  --dry-run
```

Dry-run prints the resolved CLI args per condition without launching the
game. The line should mention `--no-postrun`, `--no-memory`, and
`--no-evolution` (since `postrun`, `memory`, `evolution` all default
`False` on your new cell), and the env overrides should include
`STS2_STM_ENABLED=true`.

---

## Step 5: Add a row to the reproduce pipeline

Append your cell to `FIXED_A0_CELLS` in
[`scripts/reproduce/_lib.py:24`](../../scripts/reproduce/_lib.py):

```python
FIXED_A0_CELLS: list[tuple[str, str]] = [
    ("baseline-strict", "gemini-pilot-2026-05-08-A0-baseline"),
    ("prompt-only",     "gemini-pilot-2026-05-09-A0-prompt-only"),
    ("mode-a",          "gemini-pilot-2026-05-09-A0-mode-a-makeup"),
    ("mode-b-frozen",   "gemini-pilot-2026-05-12-A0-mode-b-frozen"),
    ("full-frozen",     "gemini-pilot-2026-05-08-A0-full-frozen"),
    ("mode-a-with-stm", "ada-2026-06-01-A0-mode-a-with-stm"),
]
```

This single edit propagates to every reproduce script: `reproduce_table_2`,
`reproduce_fig_3`, `reproduce_fig_4`, and `reproduce_app_2` all iterate
`FIXED_A0_CELLS`. `reproduce_table_3` uses a separate `CROSS_BACKBONE_CELLS`
list and is unaffected.

Run the recompute pipeline to bake the new row into the snapshot:

```bash
python -m scripts.reproduce.reproduce_table_2 --update-snapshot
python -m scripts.reproduce.reproduce_app_2 --update-snapshot
python -m scripts.reproduce.reproduce_fig_3 --update-snapshot
python -m scripts.reproduce.reproduce_fig_4 --update-snapshot
```

Or in one shot:

```bash
bash scripts/reproduce/recompute_all.sh --update-snapshot
```

`--update-snapshot` overwrites the JSON snapshots in
`scripts/reproduce/snapshots/` with the just-computed values. WITHOUT
the flag, the scripts compare against the snapshot and exit non-zero on
drift — which is the regression-test behavior used in CI. Update only
when you intend the new row to be part of the recorded baseline.

If you want the new row to be additive without touching the published
snapshots, keep `FIXED_A0_CELLS` as-is and instead make a copy of
`reproduce_table_2.py` named `reproduce_my_table.py` that imports an
extended list. The paper's snapshots stay byte-identical.

---

## Step 6: Sanity checks

Before you treat the result as a hypothesis answer:

```bash
# 1. Confirm your cell has exactly 10 valid records (no aborted runs).
python -c "
import json
from collections import Counter
tag = 'ada-2026-06-01-A0-mode-a-with-stm'
outcomes = Counter()
n = 0
with open('../AgenticSTS-Data/runs/history.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('experiment_tag') != tag: continue
        outcomes[r.get('outcome', 'unknown')] += 1
        n += 1
print('records:', n)
print('outcomes:', dict(outcomes))
"
```

Expect `outcomes` to show `victory` + `defeat` + `max_steps` summing to
10. Any `agent_abort` / `mcp_error` / `interrupt` records mean the
orchestrator filled the slot but the underlying run crashed; rerun those
slots manually (re-launch with the same `--tag`).

```bash
# 2. Confirm the cell appears in reproduce_table_2 output.
python -m scripts.reproduce.reproduce_table_2
```

You should see your row next to the published five. The Wilson 95% CI
column is the one to look at: if your new cell's interval overlaps with
the cell you flipped one knob against (e.g. `mode-a`), you cannot reject
"this knob has no effect" at the published sample size.

```bash
# 3. Confirm the full recompute pipeline still passes.
bash scripts/reproduce/recompute_all.sh
```

A non-zero exit means you forgot `--update-snapshot` on an earlier step,
or the snapshots and `_lib.py` are out of sync. Run with
`--update-snapshot` once to bring them back into agreement.

```bash
# 4. Confirm your model_profile snapshot in history.jsonl matches expectation.
python -c "
import json
tag = 'ada-2026-06-01-A0-mode-a-with-stm'
with open('../AgenticSTS-Data/runs/history.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('experiment_tag') != tag: continue
        p = r.get('model_profile', {})
        print({k: p.get(k) for k in
            ['prompt_variant', 'stm_enabled', 'combat_conversation_enabled',
             'skills_enabled', 'memory_enabled', 'evolution_enabled',
             'postrun_enabled', 'knowledge_strict']})
        break
"
```

`stm_enabled` must be `True`; everything else must match the `mode-a`
profile. If `stm_enabled` is `False`, the env override did not reach
the subprocess — verify your `Condition` field name is exactly `stm`
(not `stm_enabled`) and that `to_env_overrides()` is being called
(it is, by `run_single()` at `scripts/run_ablation.py:334`).

---

## Step 7: Document the cell

For an internal experiment that will not be published, no documentation
is required beyond the inline comment in `build_condition_matrix`.

For a result you intend to share, the cell should be cited:

- Add a row to the public README's ablation summary table (in
  `README.md` near line 80; mirror the format of the existing five).
- Add a one-paragraph entry to
  [`docs/reference/ABLATION.md`](../reference/ABLATION.md) under
  "5-condition matrix (current)" — the section heading should become
  "6-condition matrix" once your cell is upstream.
- If the result lands the hypothesis cleanly (significant
  non-overlapping CI, or a clear no-effect with tight CI), open an issue
  upstream proposing the cell as a permanent addition. Provide the
  trajectory tag, the snapshot diff, and the one-sentence hypothesis.
- A new cell does NOT belong in the EMNLP submitted bundle — that bundle
  is frozen at SHA `1888a62`. Any new cell is a follow-up paper or
  arXiv revision (see [`paper/CLAUDE.md`](../../paper/CLAUDE.md)
  § "Post-submission workstreams").

---

## Anti-patterns

Common mistakes that invalidate the result:

- **Reusing a published `experiment_tag`.** The paper's tags appear in
  `_lib.py`; pulling in your own records under those tags pools your
  runs into the published cell counts. Always pick a fresh tag.
- **Pooling fixed-A0 cells with auto-mode (ladder) cells.** The auto-mode
  streams advance ascension; fixed-A0 streams pin it. `_lib.py`
  separates them into `FIXED_A0_CELLS` and `LADDER_STREAMS` for that
  reason. A new cell belongs in exactly one stream.
- **Changing the `52/3` score coefficient** in `_lib.py:122`
  (`derive_score`). The coefficient is the published score formula
  (Eq. 1 in the paper). Changing it silently re-scales every cell's
  mean_score and breaks comparability with Table 2.
- **Enabling `postrun=True` on a fixed-A0 cell.** Postrun writes to
  L4/L5 stores during the experiment. The published cells either have
  postrun off (everything except `self-evolve`) or live in their own
  isolated `data_repo_subpath` (`self-evolve` only). Mixing the two
  modes invalidates the frozen-store comparability that anchors the
  `mode-b-frozen` and `full-frozen` rows.
- **Forgetting the matched control.** Backbone drift over weeks is real.
  If you compare a fresh `mode-a-with-stm` (June) against the published
  `mode-a` (May), an upstream model update can move both means by 10+
  points. Run your control alongside the treatment under the same date
  prefix.
- **Counting `agent_abort` / `mcp_error` / `interrupt` toward N.** The
  orchestrator already filters them in `count_existing_runs`; do the
  same when you aggregate manually. The aggregation snippet in
  `docs/reference/ABLATION.md` § "Post-hoc aggregation" demonstrates the
  filter.
- **Editing the existing five `matrix.append(...)` blocks.** Even a
  whitespace change in the existing dataclass fields makes a future
  reviewer worry the snapshot mismatch was caused by your cell. Append
  only.

---

## Where to ask questions

- Mechanics of the existing five cells:
  [`docs/reference/ABLATION.md`](../reference/ABLATION.md) and
  [`paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/methodology.tex`](../../paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/methodology.tex).
- Memory contract semantics (L1-L5 layers):
  [`docs/reference/MEMORY_SYSTEM.md`](../reference/MEMORY_SYSTEM.md).
- Self-evolution / Mode B mechanics:
  [`docs/reference/SELF_EVOLUTION.md`](../reference/SELF_EVOLUTION.md).
- Trajectory archive schema: every row of `runs/history.jsonl` is one
  `RunRecord` (`src/runs/history.py`).
- Bugs in the harness, suggestions for new cells, or a proposed upstream
  contribution: file an issue against `ShandaAI/AgenticSTSMCP`.
