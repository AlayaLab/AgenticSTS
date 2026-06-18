# Ablation conditions A & B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new ablation conditions (`prompt-only` and `self-evolve`) to `scripts/run_ablation.py`, support per-experiment data isolation, and remove the dead `RunContextView` class.

**Architecture:** Three layers of changes. (1) Dead-code cleanup of `RunContextView` removes a dimension from the matrix that toggles 0 bytes today. (2) `paths.py` gains `STS2_RUNS_HISTORY_REPO` so per-experiment data dirs can isolate L4/L5 while sharing `runs/history.jsonl` for cross-condition aggregation. (3) `run_ablation.py` adds `Condition` fields (`postrun`, `data_repo_subpath`, `analysis_eq_strategic`), parameterizes the previously-hardcoded `--no-postrun`, and emits per-condition env overrides.

**Tech Stack:** Python 3.14, pytest, dataclasses, pathlib, subprocess.

**Spec:** [`docs/superpowers/specs/2026-04-28-ablation-conditions-A-B-design.md`](../specs/2026-04-28-ablation-conditions-A-B-design.md)

---

## Task 1: Remove `run_context` parameter from `V2Engine` and `ToolExecutor`

**Files:**
- Modify: `src/brain/v2_engine.py` (remove `run_context` param from `__init__`, remove `RunContextView` import, remove `self._run_context` attr)
- Modify: `src/brain/tool_executor.py` (remove `run_context` param from `__init__`, remove `self._run_context` attr)

- [ ] **Step 1: Remove `run_context` from `V2Engine.__init__`**

In `src/brain/v2_engine.py`, replace:

```python
    def __init__(
        self,
        backend: V2Backend,
        tool_executor: ToolExecutor,
        run_context: RunContextView,
        *,
        session_logger: SessionLogger | None = None,
    ) -> None:
        self._backend = backend
        self._executor = tool_executor
        self._run_context = run_context
        self._session_logger = session_logger
```

with:

```python
    def __init__(
        self,
        backend: V2Backend,
        tool_executor: ToolExecutor,
        *,
        session_logger: SessionLogger | None = None,
    ) -> None:
        self._backend = backend
        self._executor = tool_executor
        self._session_logger = session_logger
```

- [ ] **Step 2: Remove `RunContextView` import from `v2_engine.py`**

Delete the `from src.brain.run_context import RunContextView` line at `src/brain/v2_engine.py:49`. It is the only RunContextView reference left in the file.

- [ ] **Step 3: Remove `run_context` from `ToolExecutor.__init__`**

In `src/brain/tool_executor.py`, replace:

```python
    def __init__(
        self,
        knowledge: GameKnowledge | None = None,
        memory_manager: object | None = None,   # MemoryManager
        skill_library: object | None = None,     # SkillLibrary
        run_context: object | None = None,       # RunContextView
        game_state: GameState | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._memory_manager = memory_manager
        self._skill_library = skill_library
        self._run_context = run_context
        self._game_state = game_state
```

with:

```python
    def __init__(
        self,
        knowledge: GameKnowledge | None = None,
        memory_manager: object | None = None,   # MemoryManager
        skill_library: object | None = None,     # SkillLibrary
        game_state: GameState | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._memory_manager = memory_manager
        self._skill_library = skill_library
        self._game_state = game_state
```

- [ ] **Step 4: Run import smoke**

Run: `python -c "from src.brain.v2_engine import V2Engine; from src.brain.tool_executor import ToolExecutor; print('ok')"`
Expected: `ok` (no ImportError, no missing-attr error during class body construction).

- [ ] **Step 5: Commit**

```bash
git add src/brain/v2_engine.py src/brain/tool_executor.py
git commit -m "refactor: drop dead run_context param from V2Engine and ToolExecutor"
```

---

## Task 2: Remove `RunContextView` from `AgentLoop` and delete the module

**Files:**
- Modify: `src/agent/loop.py` (remove instantiation, kwargs, and `update_refs()` call sites)
- Delete: `src/brain/run_context.py`
- Modify: `config.py` (remove `STS2_RUN_CONTEXT_ENABLED` env, `RUN_CONTEXT_ENABLED` constant, profile dict key, and `_PRESERVE_IF_SET` entry)

- [ ] **Step 1: Remove instantiation and kwargs from `AgentLoop._init_v2`**

In `src/agent/loop.py` (around line 517-583), apply these edits:

Delete line 517: `self._v2_run_context = None  # CombatConversation for current fight` — wait, this is `_v2_combat_conversation`. Read context: the actual line is `self._v2_run_context = None  # RunContextView` at line 518. Delete that line.

Delete `from src.brain.run_context import RunContextView` line in the imports inside `_init_v2`.

Delete the line `self._v2_run_context = RunContextView()` (around line 538).

Remove the `run_context=self._v2_run_context,` kwarg from the `ToolExecutor(...)` call (around line 543) and from the `V2Engine(...)` call (around line 581).

The resulting `_init_v2` body keeps `backend`, `self._v2_tool_executor`, `self._v2_engine`, etc., minus all RunContextView references.

- [ ] **Step 2: Remove `update_refs()` call sites in `AgentLoop`**

In `src/agent/loop.py`, delete these blocks:

Around line 2090-2092:
```python
        if self._v2_run_context is not None:
            self._v2_run_context.update_refs(run_state=None, stm=None)
```

Around line 2117-2119:
```python
        if self._v2_run_context is not None:
            ...
            self._v2_run_context.update_refs(run_state=self._run_state, stm=stm)
```

Around line 5861-5863:
```python
                if self._v2_run_context and self._run_state:
                    ...
                    self._v2_run_context.update_refs(run_state=self._run_state, stm=stm)
```

Use `grep -n "_v2_run_context" src/agent/loop.py` to confirm zero remaining references after edits.

- [ ] **Step 3: Delete `src/brain/run_context.py`**

```bash
rm src/brain/run_context.py
```

- [ ] **Step 4: Remove `RUN_CONTEXT_ENABLED` from `config.py`**

Three edits in `config.py`:

(a) Remove `"STS2_RUN_CONTEXT_ENABLED",` from the `_PRESERVE_IF_SET` set (line 55).

(b) Remove these two lines (around line 562-563):
```python
RUN_CONTEXT_ENABLED = os.getenv("STS2_RUN_CONTEXT_ENABLED", "true").lower() in ("true", "1", "yes")
"""When False, RunContextView.format_run_summary returns empty."""
```

(c) Remove `"run_context_enabled": RUN_CONTEXT_ENABLED,` from the `build_model_profile()` dict (around line 644).

- [ ] **Step 5: Run smoke**

```bash
python -c "import config; from src.agent.loop import AgentLoop; print('ok')"
```
Expected: `ok` (no ImportError, no AttributeError).

```bash
grep -rn "RunContextView\|RUN_CONTEXT_ENABLED\|run_context_enabled\|_v2_run_context" src/ config.py 2>/dev/null
```
Expected: empty output (zero matches).

- [ ] **Step 6: Commit**

```bash
git add src/agent/loop.py src/brain/run_context.py config.py
git commit -m "refactor: remove dead RunContextView class and STS2_RUN_CONTEXT_ENABLED gate"
```

---

## Task 3: Update tests after `RunContextView` removal

**Files:**
- Delete: `tests/test_run_context_gate.py`
- Modify: `tests/test_prompt_cleanup.py` (remove RunContextView mock + assertion)
- Modify: `tests/test_tool_executor.py` (remove `TestRunContextView` class + import)
- Modify: `tests/config/test_flag_defaults.py` (remove `run_context_enabled` assertion)

- [ ] **Step 1: Delete `test_run_context_gate.py`**

```bash
rm tests/test_run_context_gate.py
```

- [ ] **Step 2: Update `tests/test_prompt_cleanup.py`**

Remove this import:
```python
from src.brain.run_context import RunContextView
```

In `test_decide_noncombat_does_not_call_or_render_run_context` (around line 242-268), drop the RunContextView mock and assertion. Replace:

```python
    run_context = MagicMock(spec=RunContextView)
    run_context.format_run_summary = MagicMock(return_value="## Run Progress (test)")

    engine = V2Engine(
        backend=backend,
        tool_executor=ToolExecutor(),
        run_context=run_context,
    )

    result = asyncio.run(engine.decide_noncombat(_make_noncombat_gs(), "Choose a map node."))

    assert result is not None
    run_context.format_run_summary.assert_not_called()
    user_prompt = backend.acall.await_args.kwargs["messages"][0]["content"]
    assert "## Run Context" not in user_prompt
```

with:

```python
    engine = V2Engine(
        backend=backend,
        tool_executor=ToolExecutor(),
    )

    result = asyncio.run(engine.decide_noncombat(_make_noncombat_gs(), "Choose a map node."))

    assert result is not None
    user_prompt = backend.acall.await_args.kwargs["messages"][0]["content"]
    assert "## Run Context" not in user_prompt
```

The remaining assertion (`"## Run Context" not in user_prompt`) preserves the original property under test — that the prompt stays free of run-context text.

- [ ] **Step 3: Update `tests/test_tool_executor.py`**

Remove this import line:
```python
from src.brain.run_context import RunContextView
```

Delete the `class TestRunContextView:` block (around line 154-230) and the docstring lines at the top of the file referring to RunContextView. Use `grep -n "RunContextView\|format_run_summary" tests/test_tool_executor.py` to locate residual references; remove them all.

- [ ] **Step 4: Update `tests/config/test_flag_defaults.py`**

Delete the `test_run_context_enabled_defaults_to_true` test function (around line 58). In the test that asserts `build_model_profile()` keys (around line 100-110), remove `"run_context_enabled",` from the expected-keys list.

- [ ] **Step 5: Run the test suite to confirm green**

```bash
python -m pytest tests/test_prompt_cleanup.py tests/test_tool_executor.py tests/config/test_flag_defaults.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add tests/test_run_context_gate.py tests/test_prompt_cleanup.py tests/test_tool_executor.py tests/config/test_flag_defaults.py
git commit -m "test: drop RunContextView test coverage after class removal"
```

---

## Task 4: Add `STS2_RUNS_HISTORY_REPO` override in `paths.py`

**Files:**
- Modify: `src/storage/paths.py` (add `runs_history_root()` resolver, route `runs_history_file()` and `ascension_stats_file()` through it)
- Test: `tests/storage/test_paths_runs_history_root.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/storage/test_paths_runs_history_root.py`:

```python
"""Tests for STS2_RUNS_HISTORY_REPO override in paths.py.

This env var lets ablation experiments isolate L4/L5 stores (memory, skills,
evolution) per-condition while sharing runs/history.jsonl + ascension_stats.json
across conditions for post-hoc aggregation by experiment_tag.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.storage import paths


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure each test starts with a clean slate."""
    for k in ("STS2_DATA_REPO", "STS2_DATA_DIR", "STS2_RUNS_HISTORY_REPO"):
        monkeypatch.delenv(k, raising=False)


def test_runs_history_file_falls_back_to_data_root_when_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("STS2_DATA_REPO", str(tmp_path))
    expected = (tmp_path / "runs" / "history.jsonl").resolve()
    assert paths.runs_history_file() == expected


def test_runs_history_file_uses_override_when_set(monkeypatch, tmp_path):
    data_dir = tmp_path / "experiments" / "tag-a" / "cond-1"
    history_dir = tmp_path  # parent shared dir
    monkeypatch.setenv("STS2_DATA_REPO", str(data_dir))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_dir))

    expected = (history_dir / "runs" / "history.jsonl").resolve()
    assert paths.runs_history_file() == expected


def test_ascension_stats_file_uses_override_when_set(monkeypatch, tmp_path):
    data_dir = tmp_path / "experiments" / "tag-a" / "cond-1"
    history_dir = tmp_path
    monkeypatch.setenv("STS2_DATA_REPO", str(data_dir))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_dir))

    expected = (history_dir / "runs" / "ascension_stats.json").resolve()
    assert paths.ascension_stats_file() == expected


def test_other_paths_unaffected_by_override(monkeypatch, tmp_path):
    """STS2_RUNS_HISTORY_REPO must NOT redirect memory/skills/evolution."""
    data_dir = tmp_path / "data"
    history_dir = tmp_path / "shared"
    monkeypatch.setenv("STS2_DATA_REPO", str(data_dir))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_dir))

    assert paths.skills_file() == (data_dir / "skills" / "skills.json").resolve()
    assert paths.memory_dir() == (data_dir / "memory").resolve()
    assert paths.evolution_dir() == (data_dir / "evolution").resolve()
```

Create the parent directory if it doesn't exist:
```bash
mkdir -p tests/storage
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/storage/test_paths_runs_history_root.py -v
```
Expected: `test_runs_history_file_uses_override_when_set` and `test_ascension_stats_file_uses_override_when_set` FAIL — current code reads from `data_root() / "runs"` regardless of override.

- [ ] **Step 3: Add `runs_history_root()` resolver and route `runs_history_file()` / `ascension_stats_file()` through it**

Modify `src/storage/paths.py`. After the `data_root()` definition (around line 53), insert:

```python
def runs_history_root() -> Path:
    """Resolve the root for runs/history.jsonl and runs/ascension_stats.json.

    Precedence: ``STS2_RUNS_HISTORY_REPO`` > ``data_root()``.

    Ablation experiments isolate L4/L5 stores per-condition via
    ``STS2_DATA_REPO`` while sharing run history at a parent path so post-hoc
    aggregation by ``experiment_tag`` works across conditions.
    """
    override = os.getenv("STS2_RUNS_HISTORY_REPO")
    if override:
        return Path(override).expanduser().resolve()
    return data_root()
```

Then replace the `runs_dir` / `runs_history_file` / `ascension_stats_file` definitions (around lines 178-187):

```python
# ── Runs ─────────────────────────────────────────────────────────────
def runs_dir() -> Path:
    return runs_history_root() / "runs"


def runs_history_file() -> Path:
    return runs_dir() / "history.jsonl"


def ascension_stats_file() -> Path:
    return runs_dir() / "ascension_stats.json"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/storage/test_paths_runs_history_root.py -v
```
Expected: all 4 tests pass.

- [ ] **Step 5: Run wider test sweep to ensure no regression**

```bash
python -m pytest tests/storage/ tests/test_paths.py -v 2>&1 | tail -30
```
Expected: no new failures (any pre-existing failures unrelated).

- [ ] **Step 6: Commit**

```bash
git add src/storage/paths.py tests/storage/test_paths_runs_history_root.py
git commit -m "feat(paths): add STS2_RUNS_HISTORY_REPO override for ablation isolation"
```

---

## Task 5: Extend `Condition` dataclass with new fields, drop `run_ctx`

**Files:**
- Modify: `scripts/run_ablation.py` (Condition dataclass: drop `run_ctx`, add `postrun`/`data_repo_subpath`/`analysis_eq_strategic`)
- Modify: `tests/test_run_ablation.py` (drop `run_ctx=` kwargs)
- Modify: `tests/test_run_ablation_conditions.py` (drop `run_ctx=` kwargs)

- [ ] **Step 1: Update `Condition` dataclass in `scripts/run_ablation.py`**

Locate the `Condition` dataclass (around line 55-68). Replace:

```python
@dataclass
class Condition:
    condition_id: str
    model_family: str
    skills: bool
    memory: bool
    evolution: bool
    # Ablation baseline gates (added 2026-04-26)
    prompt_variant: str = "full"
    hint_filter: bool = False
    knowledge_strict: bool = False
    stm: bool = True
    combat_conv: bool = True
    run_ctx: bool = True
    boss_hp: bool = True
```

with:

```python
@dataclass
class Condition:
    condition_id: str
    model_family: str
    skills: bool
    memory: bool
    evolution: bool
    # Ablation baseline gates (added 2026-04-26; run_ctx dropped 2026-04-28)
    prompt_variant: str = "full"
    hint_filter: bool = False
    knowledge_strict: bool = False
    stm: bool = True
    combat_conv: bool = True
    boss_hp: bool = True
    # Conditions A & B fields (added 2026-04-28)
    postrun: bool = False
    data_repo_subpath: str | None = None
    analysis_eq_strategic: bool = False
```

- [ ] **Step 2: Drop `run_ctx` from existing matrix entries in `build_condition_matrix`**

In `scripts/run_ablation.py` (around line 116-136), the baseline-strict entry currently has `run_ctx=False,`. Remove that kwarg. Leave `full` unchanged (it didn't pass `run_ctx`). The new conditions get added in Task 8.

- [ ] **Step 3: Drop `STS2_RUN_CONTEXT_ENABLED` from `to_env_overrides`**

In the `to_env_overrides` method (around line 110-112), remove this line:
```python
            "STS2_RUN_CONTEXT_ENABLED": "true" if self.run_ctx else "false",
```

- [ ] **Step 4: Drop `run_ctx` kwargs from existing test fixtures**

In `tests/test_run_ablation.py`, find every `run_ctx=` and remove it (line 37, 71, 136, 178). Also delete the `"run_context_enabled": run_ctx,` line from the expected-profile dict at line 154 and remove the `run_ctx` parameter from any helper function signatures.

In `tests/test_run_ablation_conditions.py`, remove the `run_ctx=False,` line at line 19 and the `assert baseline.run_ctx is False` line at line 78.

- [ ] **Step 5: Run tests to confirm green**

```bash
python -m pytest tests/test_run_ablation.py tests/test_run_ablation_conditions.py -v
```
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_ablation.py tests/test_run_ablation.py tests/test_run_ablation_conditions.py
git commit -m "refactor(ablation): drop run_ctx field, add postrun/data_repo_subpath/analysis_eq_strategic"
```

---

## Task 6: Parameterize `--no-postrun` in `to_cli_args`

**Files:**
- Modify: `scripts/run_ablation.py` (`Condition.to_cli_args`)
- Test: `tests/test_run_ablation.py` (new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_ablation.py`:

```python
def test_to_cli_args_omits_no_postrun_when_postrun_true():
    """Condition.postrun=True must not pass --no-postrun on the CLI."""
    from scripts.run_ablation import Condition

    cond = Condition(
        condition_id="test-self-evolve", model_family="gemini",
        skills=True, memory=True, evolution=True,
        postrun=True,
    )
    args = cond.to_cli_args(tag="t", character="Silent", ascension="auto", steps=100)
    assert "--no-postrun" not in args


def test_to_cli_args_includes_no_postrun_when_postrun_false():
    """Condition.postrun=False (default) must pass --no-postrun."""
    from scripts.run_ablation import Condition

    cond = Condition(
        condition_id="test-baseline", model_family="gemini",
        skills=False, memory=False, evolution=False,
    )
    args = cond.to_cli_args(tag="t", character="Silent", ascension="auto", steps=100)
    assert "--no-postrun" in args
```

- [ ] **Step 2: Run test to verify they fail**

```bash
python -m pytest tests/test_run_ablation.py::test_to_cli_args_omits_no_postrun_when_postrun_true -v
```
Expected: FAIL — current code unconditionally appends `--no-postrun`.

- [ ] **Step 3: Update `to_cli_args` to honor `self.postrun`**

In `scripts/run_ablation.py`, modify the `to_cli_args` method (around line 70-94). Replace:

```python
        args: list[str] = [
            "--model-family", self.model_family,
            "--character", character,
            "--ascension", str(ascension),
            "--runs", "1",
            "--steps", str(steps),
            "--experiment-tag", tag,
            "--no-postrun",
            # Always start each subprocess from a clean game state. Without
            # this a timed-out / killed prior subprocess leaves an active run
            # that the next condition's subprocess would inherit.
            "--abandon-existing",
        ]
```

with:

```python
        args: list[str] = [
            "--model-family", self.model_family,
            "--character", character,
            "--ascension", str(ascension),
            "--runs", "1",
            "--steps", str(steps),
            "--experiment-tag", tag,
            # Always start each subprocess from a clean game state. Without
            # this a timed-out / killed prior subprocess leaves an active run
            # that the next condition's subprocess would inherit.
            "--abandon-existing",
        ]
        if not self.postrun:
            args.append("--no-postrun")
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_run_ablation.py -v
```
Expected: all pass, including the two new ones.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_ablation.py tests/test_run_ablation.py
git commit -m "feat(ablation): parameterize --no-postrun via Condition.postrun"
```

---

## Task 7: Emit per-experiment data env in `to_env_overrides`

**Files:**
- Modify: `scripts/run_ablation.py` (`Condition.to_env_overrides`, helper to resolve subpath)
- Test: `tests/test_run_ablation.py` (new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_ablation.py`:

```python
def test_to_env_overrides_emits_data_repo_when_subpath_set(tmp_path, monkeypatch):
    """When data_repo_subpath is set, STS2_DATA_REPO and STS2_RUNS_HISTORY_REPO
    must be emitted with the subpath substituted."""
    from scripts.run_ablation import Condition

    monkeypatch.setenv("STS2_DATA_REPO", str(tmp_path))
    cond = Condition(
        condition_id="gemini-self-evolve", model_family="gemini",
        skills=True, memory=True, evolution=True,
        postrun=True,
        data_repo_subpath="experiments/{tag}/{condition_id}",
    )
    overrides = cond.to_env_overrides(tag="pilot-x")

    expected_data_repo = str((tmp_path / "experiments" / "pilot-x" / "gemini-self-evolve").resolve())
    assert overrides["STS2_DATA_REPO"] == expected_data_repo
    assert overrides["STS2_RUNS_HISTORY_REPO"] == str(tmp_path.resolve())


def test_to_env_overrides_omits_data_repo_when_subpath_unset():
    """Conditions without data_repo_subpath inherit shared STS2_DATA_REPO."""
    from scripts.run_ablation import Condition

    cond = Condition(
        condition_id="gemini-baseline-strict", model_family="gemini",
        skills=False, memory=False, evolution=False,
    )
    overrides = cond.to_env_overrides(tag="pilot-x")
    assert "STS2_DATA_REPO" not in overrides
    assert "STS2_RUNS_HISTORY_REPO" not in overrides


def test_to_env_overrides_emits_analysis_model_when_eq_strategic():
    """analysis_eq_strategic=True copies strategic model+effort to analysis env."""
    from scripts.run_ablation import Condition

    cond = Condition(
        condition_id="gpt-self-evolve", model_family="gpt",
        skills=True, memory=True, evolution=True,
        postrun=True,
        analysis_eq_strategic=True,
    )
    overrides = cond.to_env_overrides(tag="pilot-x")
    # gpt strategic = gpt-5.4 medium per _MODEL_FAMILIES in config.py
    assert overrides["STS2_ANALYSIS_MODEL"] == "gpt-5.4"
    assert overrides["STS2_THINK_EFFORT_ANALYSIS"] == "medium"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_run_ablation.py::test_to_env_overrides_emits_data_repo_when_subpath_set -v
```
Expected: FAIL — current `to_env_overrides` does not accept a `tag` kwarg and does not emit `STS2_DATA_REPO` / `STS2_RUNS_HISTORY_REPO` / `STS2_ANALYSIS_MODEL`.

- [ ] **Step 3: Update `to_env_overrides` signature and body**

In `scripts/run_ablation.py`, replace the existing `to_env_overrides` method (around line 96-113):

```python
    def to_env_overrides(self) -> dict[str, str]:
        """Env-var overrides that pin STS2_*_ENABLED to the condition values.

        These are passed to subprocess.run's env kwarg. Paired with
        _PRESERVE_IF_SET in config.py so .env cannot override them.
        """
        return {
            "STS2_SKILLS_ENABLED": "true" if self.skills else "false",
            "STS2_MEMORY_ENABLED": "true" if self.memory else "false",
            "STS2_EVOLUTION_ENABLED": "true" if self.evolution else "false",
            "STS2_PROMPT_VARIANT": self.prompt_variant,
            "STS2_PROMPT_HINT_FILTER": "true" if self.hint_filter else "false",
            "STS2_KNOWLEDGE_STRICT": "true" if self.knowledge_strict else "false",
            "STS2_STM_ENABLED": "true" if self.stm else "false",
            "STS2_COMBAT_CONVERSATION_ENABLED": "true" if self.combat_conv else "false",
            "STS2_INCLUDE_BOSS_HP": "true" if self.boss_hp else "false",
        }
```

with:

```python
    def to_env_overrides(self, *, tag: str = "") -> dict[str, str]:
        """Env-var overrides that pin STS2_*_ENABLED to the condition values.

        These are passed to subprocess.run's env kwarg. Paired with
        _PRESERVE_IF_SET in config.py so .env cannot override them.

        When ``data_repo_subpath`` is set, emits STS2_DATA_REPO (per-condition
        isolated subdir) and STS2_RUNS_HISTORY_REPO (shared parent for cross-
        condition aggregation). When ``analysis_eq_strategic`` is True, emits
        STS2_ANALYSIS_MODEL + STS2_THINK_EFFORT_ANALYSIS pinning the postrun
        model to the gameplay strategic-tier model.
        """
        import config

        out = {
            "STS2_SKILLS_ENABLED": "true" if self.skills else "false",
            "STS2_MEMORY_ENABLED": "true" if self.memory else "false",
            "STS2_EVOLUTION_ENABLED": "true" if self.evolution else "false",
            "STS2_PROMPT_VARIANT": self.prompt_variant,
            "STS2_PROMPT_HINT_FILTER": "true" if self.hint_filter else "false",
            "STS2_KNOWLEDGE_STRICT": "true" if self.knowledge_strict else "false",
            "STS2_STM_ENABLED": "true" if self.stm else "false",
            "STS2_COMBAT_CONVERSATION_ENABLED": "true" if self.combat_conv else "false",
            "STS2_INCLUDE_BOSS_HP": "true" if self.boss_hp else "false",
        }

        if self.data_repo_subpath:
            shared_root = Path(os.environ.get("STS2_DATA_REPO") or paths.data_root())
            shared_root = shared_root.expanduser().resolve()
            subpath = self.data_repo_subpath.format(
                tag=tag, condition_id=self.condition_id,
            )
            isolated = (shared_root / subpath).resolve()
            out["STS2_DATA_REPO"] = str(isolated)
            out["STS2_RUNS_HISTORY_REPO"] = str(shared_root)

        if self.analysis_eq_strategic:
            tier = config._MODEL_FAMILIES.get(self.model_family, {}).get("strategic")
            if tier is None:
                raise ValueError(
                    f"analysis_eq_strategic=True but family {self.model_family!r} "
                    f"has no 'strategic' tier in config._MODEL_FAMILIES"
                )
            out["STS2_ANALYSIS_MODEL"] = tier["model"]
            out["STS2_THINK_EFFORT_ANALYSIS"] = tier["effort"]

        return out
```

This requires `from src.storage import paths` and `from pathlib import Path` at the top of `run_ablation.py`. Check if these imports are already present; add them if not.

- [ ] **Step 4: Update `run_single` to pass `tag` to `to_env_overrides`**

In `scripts/run_ablation.py`, locate the `run_single` function (around line 139-163). Find the line:
```python
    env = {**os.environ, **_ABLATION_FIXED_ENV, **cond.to_env_overrides()}
```

Replace with:
```python
    env = {**os.environ, **_ABLATION_FIXED_ENV, **cond.to_env_overrides(tag=tag)}
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_run_ablation.py -v
```
Expected: all pass, including the three new tests.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_ablation.py tests/test_run_ablation.py
git commit -m "feat(ablation): emit per-experiment STS2_DATA_REPO and analysis-tier overrides"
```

---

## Task 8: Add `prompt-only` and `self-evolve` to the condition matrix

**Files:**
- Modify: `scripts/run_ablation.py` (`build_condition_matrix`)
- Test: `tests/test_run_ablation_conditions.py` (new test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_run_ablation_conditions.py`:

```python
def test_matrix_has_four_conditions_per_model():
    """Each model produces baseline-strict / prompt-only / self-evolve / full."""
    from scripts.run_ablation import build_condition_matrix

    matrix = build_condition_matrix(("gemini",))
    ids = [c.condition_id for c in matrix]
    assert ids == [
        "gemini-baseline-strict",
        "gemini-prompt-only",
        "gemini-self-evolve",
        "gemini-full",
    ]


def test_prompt_only_keeps_full_prompts_zero_state():
    from scripts.run_ablation import build_condition_matrix

    matrix = build_condition_matrix(("gemini",))
    cond = next(c for c in matrix if c.condition_id == "gemini-prompt-only")
    # Full prompt structure
    assert cond.prompt_variant == "full"
    assert cond.hint_filter is False
    assert cond.knowledge_strict is False
    assert cond.boss_hp is True
    assert cond.combat_conv is True   # intra-fight working memory stays on
    # Zero accumulated state
    assert cond.skills is False
    assert cond.memory is False
    assert cond.evolution is False
    assert cond.stm is False
    # No postrun, no isolated data dir
    assert cond.postrun is False
    assert cond.data_repo_subpath is None


def test_self_evolve_blank_start_with_postrun():
    from scripts.run_ablation import build_condition_matrix

    matrix = build_condition_matrix(("gemini",))
    cond = next(c for c in matrix if c.condition_id == "gemini-self-evolve")
    assert cond.skills is True
    assert cond.memory is True
    assert cond.evolution is True
    assert cond.stm is True
    assert cond.combat_conv is True
    assert cond.postrun is True
    assert cond.analysis_eq_strategic is True
    assert cond.data_repo_subpath == "experiments/{tag}/{condition_id}"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_run_ablation_conditions.py::test_matrix_has_four_conditions_per_model -v
```
Expected: FAIL — matrix currently has 2 conditions per model.

- [ ] **Step 3: Update `build_condition_matrix`**

In `scripts/run_ablation.py`, replace `build_condition_matrix` (around line 116-136) with:

```python
def build_condition_matrix(models: tuple[str, ...] = ("qwen", "gemini")) -> list[Condition]:
    matrix: list[Condition] = []
    for m in models:
        # baseline-strict: every gate set to baseline value, no postrun, shared data dir
        matrix.append(Condition(
            condition_id=f"{m}-baseline-strict", model_family=m,
            skills=False, memory=False, evolution=False,
            prompt_variant="baseline",
            hint_filter=True,
            knowledge_strict=True,
            stm=False,
            combat_conv=False,
            boss_hp=False,
            postrun=False,
        ))
        # prompt-only (NEW): full prompts, zero accumulated state, no postrun
        matrix.append(Condition(
            condition_id=f"{m}-prompt-only", model_family=m,
            skills=False, memory=False, evolution=False,
            prompt_variant="full",
            hint_filter=False,
            knowledge_strict=False,
            stm=False,
            combat_conv=True,
            boss_hp=True,
            postrun=False,
        ))
        # self-evolve (NEW): blank-start, postrun on, isolated data dir,
        # postrun model = gameplay strategic model
        matrix.append(Condition(
            condition_id=f"{m}-self-evolve", model_family=m,
            skills=True, memory=True, evolution=True,
            prompt_variant="full",
            hint_filter=False,
            knowledge_strict=False,
            stm=True,
            combat_conv=True,
            boss_hp=True,
            postrun=True,
            analysis_eq_strategic=True,
            data_repo_subpath="experiments/{tag}/{condition_id}",
        ))
        # full: defaults preserve current behavior; data dir shared (contaminated)
        matrix.append(Condition(
            condition_id=f"{m}-full", model_family=m,
            skills=True, memory=True, evolution=True,
        ))
    return matrix
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_run_ablation_conditions.py tests/test_run_ablation.py -v
```
Expected: all pass.

- [ ] **Step 5: Dry-run smoke**

```bash
python -m scripts.run_ablation --dry-run --tag smoke-2026-04-28 --models gemini --runs-per-condition 1
```
Expected: prints 4 condition launches for gemini family, no errors.

- [ ] **Step 6: Commit**

```bash
git add scripts/run_ablation.py tests/test_run_ablation_conditions.py
git commit -m "feat(ablation): add prompt-only and self-evolve conditions"
```

---

## Task 9: Update `condition_id_from_record` in `ablation_report.py`

**Files:**
- Modify: `scripts/ablation_report.py` (drop `run_context_enabled` check, add detection for `prompt-only` and `self-evolve`)
- Test: `tests/test_ablation_report.py` (new file or extend existing)

- [ ] **Step 1: Check if existing test file exists**

```bash
ls tests/test_ablation_report.py 2>/dev/null || echo "does not exist"
```

If it exists, append to it. If not, create it.

- [ ] **Step 2: Write the failing test**

Append (or create) `tests/test_ablation_report.py`:

```python
"""Tests for condition_id_from_record in ablation_report.py."""
from __future__ import annotations

from src.runs.history import RunRecord
from scripts.ablation_report import condition_id_from_record


def _record(profile: dict, **overrides) -> RunRecord:
    """Build a minimal RunRecord with the given model_profile."""
    base = dict(
        run_id="r1",
        ts="2026-04-28T00:00:00",
        character="Silent",
        target_ascension=0,
        actual_ascension=0,
        outcome="defeat",
        victory=False,
        final_floor=5,
        steps=100,
        experiment_tag="t",
        model_profile=profile,
        skills_enabled=bool(profile.get("skills_enabled")),
        memory_enabled=bool(profile.get("memory_enabled")),
    )
    base.update(overrides)
    return RunRecord(**base)


def _gemini_profile(**kw) -> dict:
    base = dict(
        strategic_family="gemini",
        skills_enabled=False, memory_enabled=False, evolution_enabled=False,
        prompt_variant="full", prompt_hint_filter=False, knowledge_strict=False,
        stm_enabled=False, combat_conversation_enabled=True, include_boss_hp=True,
    )
    base.update(kw)
    return base


def test_baseline_strict_detected():
    p = _gemini_profile(
        prompt_variant="baseline", prompt_hint_filter=True, knowledge_strict=True,
        stm_enabled=False, combat_conversation_enabled=False, include_boss_hp=False,
    )
    assert condition_id_from_record(_record(p)) == "gemini-baseline-strict"


def test_prompt_only_detected():
    p = _gemini_profile()
    assert condition_id_from_record(_record(p)) == "gemini-prompt-only"


def test_self_evolve_detected():
    p = _gemini_profile(
        skills_enabled=True, memory_enabled=True, evolution_enabled=True,
        stm_enabled=True, postrun_enabled=True,
    )
    assert condition_id_from_record(_record(p)) == "gemini-self-evolve"


def test_full_detected():
    p = _gemini_profile(
        skills_enabled=True, memory_enabled=True, evolution_enabled=True,
        stm_enabled=True, postrun_enabled=False,
    )
    assert condition_id_from_record(_record(p)) == "gemini-full"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_ablation_report.py -v
```
Expected: most tests fail — `prompt-only` and `self-evolve` don't exist as branches; current code has `run_context_enabled` in the baseline-strict check which won't be in the new profile.

- [ ] **Step 4: Update `condition_id_from_record`**

In `scripts/ablation_report.py`, replace the function (around line 25-49):

```python
def condition_id_from_record(r: RunRecord) -> str:
    """Derive condition ID 'family-{baseline-strict|prompt-only|self-evolve|full|baseline|mixed}'
    from profile fields.
    """
    profile = r.model_profile or {}
    family = profile.get("strategic_family") or profile.get("fast_family") or "unknown"
    skills = bool(profile.get("skills_enabled", r.skills_enabled))
    memory = bool(profile.get("memory_enabled", r.memory_enabled))
    evolution = bool(profile.get("evolution_enabled", False))
    postrun = bool(profile.get("postrun_enabled", False))

    is_baseline_strict = (
        not skills and not memory and not evolution
        and profile.get("prompt_variant") == "baseline"
        and profile.get("prompt_hint_filter")
        and profile.get("knowledge_strict")
        and not profile.get("stm_enabled")
        and not profile.get("combat_conversation_enabled")
        and not profile.get("include_boss_hp")
    )
    is_prompt_only = (
        not skills and not memory and not evolution
        and profile.get("prompt_variant") == "full"
        and not profile.get("prompt_hint_filter")
        and not profile.get("knowledge_strict")
        and not profile.get("stm_enabled")
        and profile.get("combat_conversation_enabled")
        and profile.get("include_boss_hp")
    )
    is_self_evolve = (
        skills and memory and evolution and postrun
        and profile.get("prompt_variant") == "full"
        and profile.get("stm_enabled")
    )
    is_full = (
        skills and memory and evolution and not postrun
    )

    if is_baseline_strict:
        kind = "baseline-strict"
    elif is_prompt_only:
        kind = "prompt-only"
    elif is_self_evolve:
        kind = "self-evolve"
    elif is_full:
        kind = "full"
    elif not skills and not memory and not evolution:
        kind = "baseline"
    else:
        kind = "mixed"
    return f"{family}-{kind}"
```

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/test_ablation_report.py -v
```
Expected: all 4 new tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/ablation_report.py tests/test_ablation_report.py
git commit -m "feat(ablation-report): detect prompt-only and self-evolve conditions"
```

---

## Task 10: Document the new conditions and resume behavior in `CLAUDE.md` and `run_ablation.py`

**Files:**
- Modify: `CLAUDE.md` (Running ablation experiments section)
- Modify: `scripts/run_ablation.py` (module docstring resume note)

- [ ] **Step 0: Update the `run_ablation.py` module docstring**

In `scripts/run_ablation.py`, locate the top-of-file docstring (lines 1-13 area). Append a paragraph after the existing usage example:

```python
"""
... existing docstring ...

Resume:
    Re-run with the same --tag. The orchestrator counts existing
    (experiment_tag, condition_id) records in runs/history.jsonl and only
    launches the remaining runs per condition. For self-evolve, the
    per-experiment data dir at <STS2_DATA_REPO>/experiments/<tag>/<cond>/
    already contains accumulated skills/memory, so the next run picks up
    where the prior one left off.
"""
```

- [ ] **Step 1: Locate the existing section**

In `CLAUDE.md`, find the section starting with `## Running ablation experiments`. Identify the rules block (currently rules 1-6) and the canonical pilot command block.

- [ ] **Step 2: Update rule 1 to reflect 4-condition matrix**

Replace the section's intro paragraph and bullet points with text that:

- Lists the 4 conditions per model: `baseline-strict`, `prompt-only`, `self-evolve`, `full`.
- Notes that `self-evolve` writes to `experiments/<tag>/<condition_id>/` and uses `STS2_RUNS_HISTORY_REPO` so `runs/history.jsonl` lives at the parent shared path.
- Notes that resume is automatic: re-running with the same `--tag` continues from existing per-condition history counts; isolated data dirs are picked up unchanged.

Concrete edit — append after rule 6 in the existing block:

```markdown
7. **Per-experiment data isolation (`self-evolve` only).** This condition
   writes growing L4/L5 stores. The orchestrator points it at
   `<sibling_repo>/experiments/<tag>/<condition_id>/` via `STS2_DATA_REPO`
   while keeping `runs/history.jsonl` at the parent sibling root via
   `STS2_RUNS_HISTORY_REPO`. Other conditions inherit the shared
   `STS2_DATA_REPO` but have all L4/L5 gates off, so they neither read nor
   write skill/memory/evolution data.

8. **Resume.** Re-running `python -m scripts.run_ablation --tag <same>` is the
   resume mechanism. The orchestrator counts existing
   `(experiment_tag, condition_id)` records in `runs/history.jsonl` and only
   launches the remaining runs per condition. For `self-evolve`, the
   per-experiment data dir already contains accumulated skills/memory, so the
   next run picks up where the prior one left off.

9. **Postrun model parity for `self-evolve`.** The condition sets
   `STS2_ANALYSIS_MODEL` and `STS2_THINK_EFFORT_ANALYSIS` to the gameplay
   strategic-tier values (via `analysis_eq_strategic=True` in the
   `Condition` dataclass), so the same model that plays the game also runs
   memory extraction, skill discovery, guide consolidation, and evolution.
```

- [ ] **Step 3: Update the canonical pilot command**

Replace the existing canonical pilot command block (the `# Terminal 1 — baseline-strict` / `# Terminal 2 — full` block) with:

```bash
# Single-command 4-condition pilot (gemini, 10 runs each)
python -m scripts.run_ablation \
  --tag pilot-2026-04-29 \
  --runs-per-condition 10 \
  --models gemini \
  --character Silent \
  --ascension auto

# Adds two new conditions to the matrix:
#   - {model}-prompt-only:  full prompts, zero accumulated state, no postrun
#   - {model}-self-evolve:  blank L4/L5 start, postrun on (analysis=strategic),
#                           isolated data dir at experiments/<tag>/<cond>/
```

- [ ] **Step 4: Run a smoke test of the docs change**

```bash
python -m scripts.run_ablation --dry-run --tag smoke-doc-test --models gemini --runs-per-condition 1
```
Expected: prints 4 condition launches; matches the documented behavior.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update ablation section for 4-condition matrix and resume behavior"
```

---

## Verification (after all tasks)

Run the full test suite touched by this work:

```bash
python -m pytest \
  tests/storage/test_paths_runs_history_root.py \
  tests/test_run_ablation.py \
  tests/test_run_ablation_conditions.py \
  tests/test_ablation_report.py \
  tests/test_prompt_cleanup.py \
  tests/test_tool_executor.py \
  tests/config/test_flag_defaults.py \
  -v
```

Expected: all tests pass.

Verify dead-code removal is complete:

```bash
grep -rn "RunContextView\|RUN_CONTEXT_ENABLED\|run_context_enabled\|_v2_run_context\|_run_context " src/ config.py scripts/ tests/ 2>/dev/null
```
Expected: empty output. (Note the trailing space in `_run_context ` to avoid matching `_run_context_enabled` substrings — already removed but defensive.)

Verify the matrix:

```bash
python -m scripts.run_ablation --dry-run --tag verify-2026-04-28 --models gemini --runs-per-condition 1 2>&1 | grep "DRY-RUN"
```
Expected: 4 lines, one per condition (`gemini-baseline-strict`, `gemini-prompt-only`, `gemini-self-evolve`, `gemini-full`).

## Optional: live smoke for `self-evolve`

After the test suite is green and dry-run looks correct, run a single live `self-evolve` to validate the full path:

```bash
python -m scripts.run_ablation \
  --tag livesmoke-2026-04-28 \
  --runs-per-condition 1 \
  --models gemini \
  --character Silent \
  --ascension 0
```

Expected post-run state:

- `<STS2_DATA_REPO>/experiments/livesmoke-2026-04-28/gemini-self-evolve/` exists and contains `memory/`, `skills/`, `evolution/` subdirs with new content.
- `<STS2_DATA_REPO>/runs/history.jsonl` (parent path, not the per-experiment subdir) contains at least 4 new records (one per condition).
- `STS2_RUNS_HISTORY_REPO` was set in env for `self-evolve` (visible in the orchestrator log line).

This step is optional because it spawns the game and uses LLM credit. Skip it for code-only verification; run it before merging to main.
