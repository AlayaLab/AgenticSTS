# Ablation experiments

Reference for the EMNLP paper's ablation harness. For module locations see [`ARCHITECTURE.md`](ARCHITECTURE.md). For Mode B mechanics see [`SELF_EVOLUTION.md`](SELF_EVOLUTION.md#mode-b-seed-stub-self-evolution-2026-05-04).

## 5-condition matrix (current)

`scripts/run_ablation.py` runs these conditions per model family. The kind is the suffix of `condition_id` after the model prefix (e.g. `gemini-self-evolve` has kind `self-evolve`):

| Kind | Prompts | Seeds (L5) | L4 memory | Postrun | Data dir |
|------|---------|-----------|-----------|---------|----------|
| `baseline-strict` | BASELINE variants (stripped) | none | none | off | shared |
| `prompt-only` | full | none | none | off | shared |
| `mode-a` | full | expert seeds | none | off | shared |
| `self-evolve` | full | Mode B stubs (no expert seeds) | active | on (analysis=strategic) | per-experiment |
| `full` | full | expert seeds | active | on | shared |

`baseline-strict` uses the BASELINE prompt variants in `src/brain/prompts/system.py` and per-state-type files, gated by `PROMPT_VARIANT=baseline` (also `KNOWLEDGE_STRICT=true`).

`self-evolve` (Mode B) is the headline self-evolution condition — the agent self-evolves seed-skill content from gameplay alone given only topic scaffolds.

## Cell-name reconciliation (paper-headline ↔ code-level)

The paper's `tab:fivecond` and the public README use **paper-headline** cell names that emphasize the frozen-store guarantee at SHA `1888a62`. The orchestrator script `scripts/run_ablation.py` and the matrix above use **code-level** names that describe the runtime configuration. The two name spaces refer to the same five cells:

| Paper-headline (`tab:fivecond`, README, `scripts/reproduce/_lib.py:FIXED_A0_CELLS`) | Code-level (`run_ablation.py --conditions`, this matrix) | Notes |
|---|---|---|
| `baseline-strict` | `baseline-strict` | identical |
| `prompt-only` | `prompt-only` | identical |
| `mode-a` | `mode-a` | identical |
| `mode-b-frozen` | `self-evolve` | code-level runs Mode B live; "-frozen" means the published cell snapshots the L4/L5 stores at SHA `1888a62` for reproducibility |
| `full-frozen` | `full` | same: "-frozen" denotes the SHA `1888a62` store anchoring |

If you run `python -m scripts.run_ablation --conditions self-evolve` and then read README's Table 2 looking for a `self-evolve` row, you will not find one — look at the `mode-b-frozen` row instead. The same applies to `full` ↔ `full-frozen`.

## Experiment isolation rules

To stay separated from personal-progression state and support `--ascension auto` fairly across conditions:

1. **Always pass `--experiment-tag <tag>`.** Activates session-local AscensionStats in `scripts/run_agent.py::_load_ascension_stats_for_session()`. Stats derive from `runs/history.jsonl` filtered by tag — never from global `runs/ascension_stats.json`.
2. **`--ascension auto` is recommended.** Each condition starts at A0 (no matching history) and auto-advances on its own wins. Fixed `--ascension N` works for "test this ascension specifically" experiments. Mixed forms `auto-N` / `reset-N` also valid.
3. **Stats writes skipped under `experiment_tag`.** Per-condition / per-ascension win rates derived post-hoc from `runs/history.jsonl` filtered by `(experiment_tag, actual_ascension, model_profile.*)`. Global `ascension_stats.json` cache untouched.
4. **`--no-postrun` for non-postrun-testing experiments.** Otherwise postrun would write skills/memory to L4/L5 stores during the experiment, contaminating later runs.
5. **`--abandon-existing` flips meaning.** Default: only first run abandons; subsequent re-enter saved state. Experiment mode: every run abandons, ensuring clean slate.

## Per-experiment data isolation (`self-evolve` only)

The `self-evolve` condition writes growing L4/L5 stores. The orchestrator points it at `<sibling_repo>/experiments/<tag>/<condition_id>/` via `STS2_DATA_REPO` while keeping `runs/history.jsonl` at the parent sibling root via `STS2_RUNS_HISTORY_REPO`. Other conditions inherit shared `STS2_DATA_REPO` but have all L4/L5 gates off, so they neither read nor write skill/memory/evolution data.

## Multi-agent parallel runs

Each agent launches its own game subprocess via `--launch-game --api-port=auto --monitor-port=auto`. Independent TCP ports + monitor dashboards. Set distinct `STS2_MACHINE_ID` per agent (e.g. `desktop-baseline`, `desktop-full`) for clear sibling-repo commit attribution.

Single shared file across parallel agents: `runs/history.jsonl`, with `append_dedup` merge driver — parallel-safe.

## Resume

Re-running `python -m scripts.run_ablation --tag <same>` is the resume mechanism. The orchestrator counts existing `(experiment_tag, condition_id)` records in `runs/history.jsonl` and only launches the remaining runs per condition. For `self-evolve`, the per-experiment data dir already contains accumulated skills/memory, so the next run picks up where prior left off.

## Postrun model parity

`self-evolve` sets `STS2_ANALYSIS_MODEL = LLM_STRATEGIC_MODEL` via `analysis_eq_strategic=True` in the `Condition` dataclass — the same model that plays the game also runs memory extraction, skill discovery, guide consolidation, and evolution.

**Effort is NOT synced** — `STS2_THINK_EFFORT_ANALYSIS` defers to shell env or family default. Lets you run "cheap gameplay + thoughtful postrun" by setting `STS2_THINK_EFFORT_STRATEGIC=low STS2_THINK_EFFORT_ANALYSIS=high` independently.

## Filtering conditions

```bash
# All 5 conditions (default)
python -m scripts.run_ablation --tag <tag> --runs-per-condition 10 --models gemini

# Subset
python -m scripts.run_ablation --tag <tag> --conditions self-evolve --models gemini
python -m scripts.run_ablation --tag <tag> --conditions baseline-strict,full --models gemini
```

Available kinds: `baseline-strict`, `prompt-only`, `mode-a`, `self-evolve`, `full`.

## Canonical pilot

```bash
python -m scripts.run_ablation \
  --tag pilot-2026-05-XX \
  --runs-per-condition 10 \
  --models gemini \
  --character Silent \
  --ascension auto

# Produces 5 conditions × 10 runs = 50 runs:
#   - gemini-baseline-strict: stripped prompts, no L4/L5, no postrun
#   - gemini-prompt-only:     full prompts, zero accumulated state, no postrun
#   - gemini-mode-a:          full prompts + expert seeds, no postrun
#   - gemini-self-evolve:     Mode B stubs, postrun on, isolated data dir
#   - gemini-full:            full prompts + expert seeds + postrun on
```

## Post-hoc aggregation

```bash
python -c "
import json
from collections import defaultdict
buckets = defaultdict(list)
with open('../AgenticSTS-Data/runs/history.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r.get('experiment_tag') != '<tag>': continue
        if r.get('outcome') in {'agent_abort', 'mcp_error', 'interrupt'}: continue
        cond = r.get('experiment_condition_id', 'unknown')
        buckets[(cond, r.get('actual_ascension', 0))].append(r)
for (cond, asc), runs in sorted(buckets.items()):
    wins = sum(1 for r in runs if r.get('victory'))
    floors = [r.get('final_floor', 0) for r in runs]
    avg_floor = sum(floors)/len(floors) if floors else 0
    print(f'{cond} @ A{asc}: {len(runs)} runs, {wins}W, avg_floor={avg_floor:.1f}, max_floor={max(floors)}')
"
```

The aggregation explicitly filters out `agent_abort` / `mcp_error` / `interrupt` records — those are crashes, not legitimate gameplay outcomes.

`scripts/ablation_report.py::condition_id_from_record` is the canonical helper for deriving condition_id from a history record.

## Active empirical results (as of 2026-05-07)

Mode B preliminary:
- `mode-b-smoke-2026-05-03`: 21 runs, 5 wins, max actual A5 (ceiling)
- `mode-b-fixed-2026-05-04`: 20 runs, 6 wins, A6 attempted

Per-experiment skill stores at `../AgenticSTS-Data/experiments/mode-b-*/`. Audit logs (`stub_fill_log.jsonl`) at the same paths.

## Eval scripts

- `scripts/run_ablation.py` — orchestrator
- `scripts/eval_decision_quality.py` — LLM-as-judge 1-5 rubric on individual decisions
- `scripts/ablation_report.py` — helper for condition_id derivation + aggregation

## Pending paper-figure work

See CLAUDE.md "Active TODOs". Raw data in `runs/history.jsonl` + per-experiment `evolution/` dirs; aggregator + plot scripts pending.
