# Ablation conditions A & B — design

**Date:** 2026-04-28
**Status:** Draft, pending implementation plan
**Supersedes nothing.** Extends [`2026-04-26-ablation-baseline-design.md`](2026-04-26-ablation-baseline-design.md) with two new conditions and per-experiment storage isolation.

## Motivation

The current ablation matrix in `scripts/run_ablation.py` ships only two conditions per model family:

- `{model}-baseline-strict` — stripped prompts, all gates off, `--no-postrun`
- `{model}-full` — full prompts, default gates on, `--no-postrun`

Two important conditions are missing:

1. **Prompt enrichment without accumulated state** — isolate the value of structured prompts + L3 game knowledge from the value of L4/L5 accumulated experience.
2. **Closed-loop self-evolution from blank** — the `full` condition reads `$STS2_DATA_REPO` which has been contaminated by everyday development runs, so it does not actually measure self-evolution. We need a condition that starts from blank L4/L5 and evolves them across runs, with postrun ON.

This document specifies those two conditions and the supporting infrastructure (per-experiment storage, postrun-tier override, dead-code cleanup).

## Decisions locked

| ID | Decision |
|----|----------|
| A1 | Condition A keeps `prompt_variant=full` — identical prompts to the existing `full` condition. |
| A2 | Empty stores produce **no header at all** (suppress entire section). Verified in [`src/memory/prompt_injector.py`](../../../src/memory/prompt_injector.py) and [`src/skills/composer.py`](../../../src/skills/composer.py). No code change needed for this decision. |
| A3 | `RunContextView` is dead code (never read by any prompt or tool path). Remove the class, its instantiation, the `STS2_RUN_CONTEXT_ENABLED` env flag, and all `update_refs()` call sites. |
| A4 | `CombatConversation` is real — it accumulates intra-combat multi-turn history. Stays ON in Conditions A and B (it's working memory inside a single fight, not cross-run accumulation). |
| B1 | Seed skills are **kept** in Condition B — they are authored knowledge, not accumulated. Seed merge is automatic on every agent startup ([`src/agent/loop.py:1914`](../../../src/agent/loop.py)), so a blank per-experiment data dir picks them up for free. |
| B2 | Postrun model = gameplay model. Set `STS2_ANALYSIS_MODEL = STS2_STRATEGIC_MODEL` (and analysis effort = strategic effort). |
| B3 | Per-experiment data subdirectory: `STS2_DATA_REPO=<sibling_repo>/experiments/<tag>/<condition_id>/`, initialized blank. |
| B4 | Start with 10 runs per condition. Use existing tag-based resume — re-running with the same `--tag` continues from where prior history.jsonl entries left off. |
| C1 | Keep the existing `full` condition for now (do not replace). New matrix has 4 conditions per model. Decision on whether to remove `full` later, after seeing data. |
| D2 | Naming: `baseline-strict / prompt-only / self-evolve / full`. |

## Condition matrix (per model family)

| Condition | prompts | L4 mem | L5 skills | STM | combat_conv | postrun | data dir | Notes |
|-----------|---------|--------|-----------|-----|-------------|---------|----------|-------|
| `baseline-strict` | baseline | OFF | OFF | OFF | OFF | OFF | shared (no L4/L5 I/O) | unchanged from current matrix |
| `prompt-only` (NEW) | full | OFF | OFF | OFF | ON | OFF | shared (no L4/L5 I/O) | full prompt structure, zero accumulated state |
| `self-evolve` (NEW) | full | grows from blank | grows from blank (seeds preloaded) | ON | ON | ON, analysis=strategic | per-experiment isolated | closed-loop self-improvement |
| `full` | full | ON | ON | ON | ON | OFF | shared (contaminated) | unchanged; will be evaluated for removal post-data |

The `baseline-strict` and `prompt-only` conditions have all gameplay gates that touch L4/L5 turned off (`STS2_SKILLS_ENABLED=false`, `STS2_MEMORY_ENABLED=false`, `STS2_STM_ENABLED=false`), so no skill/memory I/O happens despite the shared data dir. Run history (`runs/history.jsonl`) and per-run logs (`logs/run_*.jsonl`) are written for all conditions.

The `self-evolve` condition writes everything (memory extracts, skill discoveries, evolution artifacts) into its isolated subdirectory, so concurrent `self-evolve` runs across model families do not corrupt each other.

### Why `combat_conv=ON` in `prompt-only` but `OFF` in `baseline-strict`

`baseline-strict` is supposed to be the maximally stripped condition (single-turn isolated decisions). `prompt-only` is "full prompts minus accumulated state" — intra-fight working memory is not accumulated state, it's part of how the agent plans within a fight. Keeping it on preserves prompt parity with `full`.

## Component changes

### 1. Per-experiment storage isolation ([`src/storage/paths.py`](../../../src/storage/paths.py))

Add an environment-variable–driven override:

```python
def _data_root() -> Path:
    repo = os.getenv("STS2_DATA_REPO")
    if repo:
        return Path(repo)
    return Path(__file__).resolve().parents[2] / "data"
```

The override path is set by `run_ablation.py` per condition:

```
STS2_DATA_REPO=<sibling_repo>/experiments/<tag>/<condition_id>/
```

Subdirectory is created blank if it doesn't exist. `paths.py` currently routes every store accessor through it, so this single override propagates to memory/skills/evolution/runs paths.

**Cross-condition shared file:** `runs/history.jsonl` must remain shared so post-hoc aggregation by `experiment_tag` works. We resolve this by writing run history to the **parent sibling** path (`<sibling_repo>/runs/history.jsonl`), not the per-experiment subdir.

Concretely, add a `_runs_history_root_override` env var (e.g., `STS2_RUNS_HISTORY_REPO`) that `paths.runs_history_file()` honors when set. `run_ablation.py` sets it to the parent sibling. All other paths follow the per-experiment override.

### 2. New `Condition` fields and matrix ([`scripts/run_ablation.py`](../../../scripts/run_ablation.py))

Add fields to the `Condition` dataclass:

```python
@dataclass
class Condition:
    ...
    postrun: bool = False                       # NEW
    data_repo_subpath: str | None = None        # NEW; None = shared
    analysis_eq_strategic: bool = False         # NEW; sets STS2_ANALYSIS_MODEL = STS2_STRATEGIC_MODEL
```

Remove `--no-postrun` from `to_cli_args` when `self.postrun` is `True`. Pass `STS2_DATA_REPO` and `STS2_RUNS_HISTORY_REPO` via `to_env_overrides` when `data_repo_subpath` is set.

When `analysis_eq_strategic` is True, resolve the strategic-tier model from `config._MODEL_FAMILIES[model_family]["strategic"]` and emit `STS2_ANALYSIS_MODEL=<that>` plus the family's strategic effort env var.

`build_condition_matrix` becomes:

```python
for m in models:
    matrix.append(Condition(  # baseline-strict (unchanged)
        condition_id=f"{m}-baseline-strict", model_family=m,
        skills=False, memory=False, evolution=False,
        prompt_variant="baseline", hint_filter=True, knowledge_strict=True,
        stm=False, combat_conv=False, run_ctx=False, boss_hp=False,
        postrun=False,
    ))
    matrix.append(Condition(  # NEW: prompt-only
        condition_id=f"{m}-prompt-only", model_family=m,
        skills=False, memory=False, evolution=False,
        prompt_variant="full", hint_filter=False, knowledge_strict=False,
        stm=False, combat_conv=True, run_ctx=False, boss_hp=True,
        postrun=False,
    ))
    matrix.append(Condition(  # NEW: self-evolve
        condition_id=f"{m}-self-evolve", model_family=m,
        skills=True, memory=True, evolution=True,
        prompt_variant="full", hint_filter=False, knowledge_strict=False,
        stm=True, combat_conv=True, run_ctx=False, boss_hp=True,
        postrun=True, analysis_eq_strategic=True,
        data_repo_subpath="experiments/{tag}/{condition_id}",
    ))
    matrix.append(Condition(  # full (unchanged)
        condition_id=f"{m}-full", model_family=m,
        skills=True, memory=True, evolution=True,
    ))
```

`data_repo_subpath` uses `{tag}` and `{condition_id}` placeholders that get substituted at run time.

### 3. Resume mechanism

Already mostly in place. `run_ablation.py:212-219` already counts existing `(tag, condition_id)` records in `runs/history.jsonl` and computes `remaining = target - existing`. With per-experiment data dirs, resume becomes natural:

- Subdir already exists → `SkillLibrary.load()` reads existing skills, memory stores load existing entries, history counts existing records, agent picks up where it left off.
- Subdir doesn't exist → blank init, seeds merged, run 1 starts fresh.

**No new flag.** Just re-run with the same `--tag`. Document this behavior in the docstring of `run_ablation.py` and in [`CLAUDE.md`](../../../CLAUDE.md) "Running ablation experiments".

### 4. Dead code cleanup: `RunContextView`

Files to modify:

- Delete [`src/brain/run_context.py`](../../../src/brain/run_context.py).
- [`src/agent/loop.py`](../../../src/agent/loop.py): remove imports, `self._v2_run_context = None`, instantiation at line 538, `run_context=` kwargs to `V2Engine` and `ToolExecutor`, all three `update_refs(...)` call sites.
- [`src/brain/v2_engine.py`](../../../src/brain/v2_engine.py): remove `run_context` parameter from `__init__`, the `self._run_context = run_context` line, and the `RunContextView` import.
- [`src/brain/tool_executor.py`](../../../src/brain/tool_executor.py): remove `run_context` parameter and `self._run_context = run_context`.
- [`config.py`](../../../config.py): remove the `STS2_RUN_CONTEXT_ENABLED` entry from `_PRESERVE_IF_SET` (line 54 area), the `RUN_CONTEXT_ENABLED = ...` line, and the `"run_context_enabled"` key in the model-profile dict.
- [`scripts/run_ablation.py`](../../../scripts/run_ablation.py): remove `run_ctx` field from `Condition`, the `STS2_RUN_CONTEXT_ENABLED` line in `to_env_overrides`, and the `run_ctx=` kwargs in `build_condition_matrix`.
- [`scripts/ablation_report.py`](../../../scripts/ablation_report.py): remove `run_context_enabled` check from `condition_id_from_record`.
- [`tests/config/test_flag_defaults.py`](../../../tests/config/test_flag_defaults.py): remove related assertions.
- [`tests/test_run_context_gate.py`](../../../tests/test_run_context_gate.py): delete the file.
- [`tests/test_run_ablation.py`](../../../tests/test_run_ablation.py), [`tests/test_run_ablation_conditions.py`](../../../tests/test_run_ablation_conditions.py): remove `run_ctx` fields from condition fixtures.

### 5. Postrun tier override for `self-evolve`

In Condition B, postrun must use the strategic-tier model. Today `config.py` resolves `LLM_ANALYSIS_MODEL` from `STS2_ANALYSIS_MODEL` env, falling back to family registry. We do **not** need new code in `config.py` — `run_ablation.py` will set `STS2_ANALYSIS_MODEL` and the family-effort env var explicitly when `analysis_eq_strategic=True`.

For families that have no `analysis` tier (e.g., `qwen`), [`config.postrun_effectively_enabled()`](../../../config.py) currently auto-disables postrun. The explicit `STS2_ANALYSIS_MODEL` override flips it back on — verified in `config.postrun_effectively_enabled()` logic which checks for `STS2_ANALYSIS_MODEL` override.

## Concrete commands

Single-model 4-condition pilot (10 runs each):

```bash
python -m scripts.run_ablation \
  --tag pilot-2026-04-29 \
  --runs-per-condition 10 \
  --models gemini \
  --character Silent \
  --ascension auto
```

Per-condition `STS2_DATA_REPO` (auto-set by `run_ablation.py`):

- `baseline-strict` → `<sibling>/` (shared, read-only effective)
- `prompt-only` → `<sibling>/` (shared, read-only effective)
- `self-evolve` → `<sibling>/experiments/pilot-2026-04-29/gemini-self-evolve/`
- `full` → `<sibling>/` (shared, contaminated)

Resume after partial run:

```bash
# Same command — continues to fill remaining runs per condition.
python -m scripts.run_ablation --tag pilot-2026-04-29 ...
```

## Open questions deferred

These are intentionally not resolved in this spec:

- **Run count** — start with 10 per condition, decide larger N (30-50) after seeing variance.
- **Seed repetitions for `self-evolve`** — postrun is stochastic. May need ≥3 reps with different seeds to get stable signal. Decide after first 10-run pilot.
- **Curve analysis methodology** — early-vs-late comparison vs. trajectory metric. Decide based on what the data shape supports.
- **EMNLP framing** (claim (i) "knowledge value" vs (ii) "prompt structure" vs (iii) "trajectory") — decide post-data. May also include cross-model reasoning analysis.
- **Whether to remove `full`** — decide after first pilot. If `full`'s contamination meaningfully shifts numbers, replace with a `full-snapshot` condition that copies a frozen L4/L5 into per-condition subdirs.

## Test plan

- Unit: extend `tests/test_run_ablation.py` to assert the new matrix has 4 conditions per model and that `self-evolve` emits `STS2_DATA_REPO` env override + omits `--no-postrun`.
- Unit: add a test that `paths.py` honors `STS2_RUNS_HISTORY_REPO` independently of `STS2_DATA_REPO`.
- Integration: `--dry-run` smoke for the full 4-condition matrix, verify env exports look right.
- Live smoke: 1-run pilot of `self-evolve` for one model, confirm `experiments/<tag>/<cond>/{memory,skills,evolution}/` populated post-run, and `runs/history.jsonl` (parent path) has the entry.
- Regression: existing `baseline-strict` and `full` conditions still produce identical CLI args after the matrix expansion.

## Out of scope

- Sibling-repo merge driver for `runs/history.jsonl` parallel writes — already covered by the existing `append_dedup` driver per [`CLAUDE.md`](../../../CLAUDE.md) §"For multi-agent parallel runs".
- Cross-condition data normalization in `ablation_report.py` — current report already filters by `experiment_tag`, so no change needed.
- Migration of past contamination out of `full` — deferred to "frozen snapshot" decision in open questions.
