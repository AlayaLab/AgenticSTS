# Evolution Engine Module Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mechanical, behavior-preserving split of the 2433-line `src/brain/evolution_engine.py` into 4 sibling modules + absorb context-rendering into `src/postrun/context_builder.py`. Final `evolution_engine.py` shrinks to ~700 LOC.

**Architecture:** "Move body, keep delegator" pattern — for each `EvolutionEngine.*` method we relocate, the class retains a 2-line delegator that calls into the new module, so existing test code (`engine._handle_write_skill(...)`, etc.) keeps working with zero changes. Top-level helpers (`build_evolution_context`, `EvolutionContextBundle`, `format_combat_replay`) get a re-export shim at the top of `evolution_engine.py` so `from src.brain.evolution_engine import ...` callers stay green.

**Tech Stack:** Python 3.12, pytest. No new libraries.

**Spec:** [`docs/superpowers/specs/2026-04-25-evolution-engine-module-split-design.md`](../specs/2026-04-25-evolution-engine-module-split-design.md)

---

## File Map

| File | Action | Notes |
|---|---|---|
| `src/postrun/context_builder.py` | Modify (absorb) | Gains 8 renderer / formatter functions + `build_evolution_context` + `EvolutionContextBundle` from `evolution_engine.py` |
| `src/brain/evolution_engine.py` | Modify (extract) | Drastically smaller (~2433 → ~700 LOC); keeps `EvolutionEngine` class + `__init__` + `run_evolution` + dispatchers + `EvolutionAction` + `EVOLUTION_SYSTEM_PROMPT` + re-export shim |
| `src/brain/evolution_artifacts.py` | Create | Serialization + artifact writers (~200 LOC) |
| `src/brain/evolution_validators.py` | Create | Skill / tool validators + dedup + auto-classify (~700 LOC) |
| `src/brain/evolution_handlers.py` | Create | Tool-handler functions: `handle_write_skill`, `handle_author_tool`, `handle_performance_stats` + `compute_performance_stats` + `continuation_prompt` (~600 LOC) |
| `src/agent/loop.py:4484` | Modify | One-line import shift: `build_evolution_context` from `src.postrun.context_builder` instead of `src.brain.evolution_engine` (after Task 1; before Task 1 the shim makes it work either way) |
| `tests/test_*.py` | NO modifications | The "delegator" pattern + re-export shim keeps every test import working as-is. Tests are pure import-path-stable across this refactor. |

**Sequencing rationale**: each task is independent (different functions). Order chosen to land smallest dependency footprint first:
1. Context renderers (Task 1) — most independent, biggest LOC reduction.
2. Artifacts (Task 2) — independent, simple.
3. Validators (Task 3) — independent, large.
4. Handlers (Task 4) — depends on validators (handlers call them) but only via `engine._validate_*` delegators which still exist after Task 3, so order doesn't strictly matter; we put it last to land the smallest surface change first.
5. Final verification (Task 5) — non-implementation, just verify import shifts in `loop.py` + smoke tests.

Each commit leaves the system fully working.

**Delegator pattern reference** (used in Tasks 2-4):

```python
# Before:
class EvolutionEngine:
    def _handle_write_skill(self, tool_input):
        # ... 200 lines of logic accessing self.X ...

# After (Task 4):
# evolution_handlers.py
def handle_write_skill(engine, tool_input):
    """Free-function form. `engine` is the calling EvolutionEngine."""
    # ... same 200 lines, with `self` replaced by `engine` ...

# evolution_engine.py
class EvolutionEngine:
    def _handle_write_skill(self, tool_input):
        from src.brain.evolution_handlers import handle_write_skill
        return handle_write_skill(self, tool_input)
```

The class method is the ONLY surviving caller of the old method API. Tests calling `engine._handle_write_skill(...)` flow transparently through the delegator.

---

## Task 1: Absorb Context Renderers into `context_builder.py`

**Files:**
- Modify: `src/postrun/context_builder.py` (absorbs)
- Modify: `src/brain/evolution_engine.py` (extracts + adds re-export shim)
- Test: existing tests should pass without modification (verified by re-export shim).

Functions/classes being moved (from `src/brain/evolution_engine.py` to `src/postrun/context_builder.py`):
- `EvolutionContextBundle` dataclass (around L115)
- `_format_enemy_deltas` (L236)
- `_format_delta_line` (L255)
- `format_combat_replay` (L284)
- `_select_smart_episodes` (L372)
- `_truncate_at_boundary` (L445)
- `_section` (L2216)
- `_render_summary` (L2221)
- `_render_dynamic_tools` (L2236)
- `_render_replay_package` (L2254)
- `_render_triggered_skills` (L2288)
- `build_evolution_context` (L2308)

(Line numbers as of commit `74e7241`. Verify before each move with `grep -n`.)

- [ ] **Step 1: Read context_builder.py top to understand existing imports + structure**

```
head -40 src/postrun/context_builder.py
```

Note the existing imports (`config`, `Path`, etc.); the new functions will reuse them.

- [ ] **Step 2: Move `EvolutionContextBundle` dataclass to context_builder.py**

In `src/postrun/context_builder.py`, append (or insert in a reasonable location near other dataclasses):

```python
from dataclasses import dataclass, field
# (verify these imports already exist; add if missing)


@dataclass
class EvolutionContextBundle:
    """Output bundle of build_evolution_context."""
    text: str
    section_stats: tuple = ()
    summary: dict = field(default_factory=dict)
    seen_card_names: tuple[str, ...] = ()

    @property
    def estimated_tokens(self) -> int:
        return sum(section.estimated_tokens for section in self.section_stats)
```

Use the EXACT class body from `src/brain/evolution_engine.py:115-127`. Verify with `Read` first — the body may include subtle details not shown above (additional fields, methods).

- [ ] **Step 3: Move format / render / select helpers to context_builder.py**

For each of these 11 free functions, copy the function body from `src/brain/evolution_engine.py` into `src/postrun/context_builder.py`:

1. `_format_enemy_deltas`
2. `_format_delta_line`
3. `format_combat_replay`
4. `_select_smart_episodes`
5. `_truncate_at_boundary`
6. `_section`
7. `_render_summary`
8. `_render_dynamic_tools`
9. `_render_replay_package`
10. `_render_triggered_skills`
11. `build_evolution_context`

For each: locate via grep, Read the body, paste into context_builder.py preserving all imports and references. After each, verify the function compiles by running:

```
python -c "from src.postrun.context_builder import _format_enemy_deltas; print('ok')"
```

(Substitute the function name being verified.)

If a moved function references symbols that exist in `evolution_engine.py` but not yet in `context_builder.py` (e.g., `SectionStat` is in context_builder but `ReplayPackage` is also in context_builder), no work needed. If it references something that lives ONLY in evolution_engine.py (e.g., a private helper this task didn't move), you'll need to either move that helper too or import it explicitly.

- [ ] **Step 4: DELETE the moved functions from `evolution_engine.py`**

For each of the 11 functions + `EvolutionContextBundle` dataclass: delete the original definition in `src/brain/evolution_engine.py`. Use Edit tool with the exact function header + body as the search pattern.

- [ ] **Step 5: Add re-export shim to `evolution_engine.py`**

At the TOP of `src/brain/evolution_engine.py`, after the existing `from __future__` and `import` statements, add a re-export block:

```python
# ── Re-exports for backwards compatibility ──────────────────────
# Spec #4: the following identifiers used to live here but were
# absorbed into context_builder. Callers using
# `from src.brain.evolution_engine import build_evolution_context`
# (and friends) continue to work via this shim. Cleanup pass after
# spec #4 lands removes the shim and migrates direct importers.
from src.postrun.context_builder import (
    EvolutionContextBundle,
    _format_delta_line,
    _format_enemy_deltas,
    _render_dynamic_tools,
    _render_replay_package,
    _render_summary,
    _render_triggered_skills,
    _section,
    _select_smart_episodes,
    _truncate_at_boundary,
    build_evolution_context,
    format_combat_replay,
)
```

Place the shim AFTER any standard imports but BEFORE the module-level `__all__` (if any), and before the `EvolutionAction` dataclass.

- [ ] **Step 6: Run tests**

```
pytest tests/test_evolution_engine.py tests/test_combat_delta.py tests/test_loop_post_run.py -v 2>&1 | tail -10
```
Expected: PASS (existing test counts maintained — these tests import via the shim).

```
pytest tests/ -q --ignore=tests/regression 2>&1 | tail -3
```
Expected: same baseline (1912 PASS / 1 skipped / 0 fail). No NEW failures.

If any test fails because of a circular import (e.g., context_builder → evolution_engine → context_builder), the moved function probably needs to import from `evolution_engine` lazily inside the function body. Check for cycle and resolve with deferred imports.

- [ ] **Step 7: Commit**

```
git add src/postrun/context_builder.py src/brain/evolution_engine.py
git commit -m "refactor(evolution): absorb context renderers into context_builder"
```

---

## Task 2: Extract Artifacts + Serialization into `evolution_artifacts.py`

**Files:**
- Create: `src/brain/evolution_artifacts.py`
- Modify: `src/brain/evolution_engine.py` (replace method bodies with delegators)
- Test: existing tests should pass without modification.

Methods being extracted (from `EvolutionEngine` to `evolution_artifacts.py`):
- `_filter_response_content` (staticmethod, L919) → `filter_response_content`
- `_serialize_message` (classmethod, L1013) → `serialize_message`
- `_serialize_response` (classmethod, L1021) → `serialize_response`
- `_serialize_content` (classmethod, L1034) → `serialize_content`
- `_write_round_1_prompt_artifact` (L968) → `write_round_1_prompt_artifact(engine, *, system_prompt, run_context)`
- `_write_round_artifact` (L979) → `write_round_artifact(engine, **kwargs)`
- `_emit_artifact` (L2162) → `emit_artifact(engine, **kwargs)`
- `_save_proposal` (L2194) → `save_proposal(engine, proposal_type, data)`

(Line numbers as of commit `74e7241`. Verify with `grep -n` after Task 1 has shifted things.)

- [ ] **Step 1: Create `src/brain/evolution_artifacts.py`**

Use Write tool to create the file with this skeleton:

```python
"""Serialization and artifact-writing helpers for the evolution stage.

Spec #4 module split: these functions used to live as methods of
EvolutionEngine. They moved here because they don't materially depend on
the class's full state — they read narrowly from the engine instance
(artifact_dir, session_logger, etc.) and write to disk / log streams.

Each engine method now retains a 2-line delegator into the matching
function below. Tests calling engine._serialize_message(...) etc.
flow through the delegators unchanged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Function bodies will be added in Step 2.
```

- [ ] **Step 2: Move function bodies into `evolution_artifacts.py`**

For each of the 8 methods listed above:

a. Locate the method in `evolution_engine.py` via grep.
b. Read the method body.
c. In `evolution_artifacts.py`, define a free function with the same body but:
   - For `staticmethod` / `classmethod` → define as plain free function (drop `self` / `cls` param)
   - For instance methods (`self`-using) → first param becomes `engine: Any` (matches `EvolutionEngine` instance duck-type)
   - Replace every `self.X` reference with `engine.X`
   - Replace every `cls.method(...)` reference with the new free-function name
d. Preserve the docstring; add a brief note "(extracted from EvolutionEngine.<orig_name>)".

Example transformation for `_emit_artifact`:

```python
# Before (in evolution_engine.py):
class EvolutionEngine:
    def _emit_artifact(self, *, kind, action, target, summary, before="", after="",
                        details=None, source="evolution"):
        if self._session_logger is None:
            return
        try:
            self._session_logger.log_postrun_artifact(
                stage=...,
                kind=kind,
                ...
            )
        except Exception:
            logger.warning("Failed to emit artifact", exc_info=True)
```

```python
# After (in evolution_artifacts.py):
def emit_artifact(engine, *, kind, action, target, summary, before="", after="",
                   details=None, source="evolution"):
    """(Extracted from EvolutionEngine._emit_artifact.) Emit a postrun artifact."""
    if engine._session_logger is None:
        return
    try:
        engine._session_logger.log_postrun_artifact(
            stage=...,
            kind=kind,
            ...
        )
    except Exception:
        logger.warning("Failed to emit artifact", exc_info=True)
```

- [ ] **Step 3: Replace method bodies in `evolution_engine.py` with delegators**

For each of the 8 methods, REPLACE the entire method body with a 2-line delegator:

For staticmethod / classmethod (`_filter_response_content`, `_serialize_*`):

```python
    @staticmethod
    def _filter_response_content(response):
        from src.brain.evolution_artifacts import filter_response_content
        return filter_response_content(response)

    @classmethod
    def _serialize_message(cls, message):
        from src.brain.evolution_artifacts import serialize_message
        return serialize_message(message)

    @classmethod
    def _serialize_response(cls, response):
        from src.brain.evolution_artifacts import serialize_response
        return serialize_response(response)

    @classmethod
    def _serialize_content(cls, content):
        from src.brain.evolution_artifacts import serialize_content
        return serialize_content(content)
```

For instance methods (`_write_round_*_artifact`, `_emit_artifact`, `_save_proposal`):

```python
    def _write_round_1_prompt_artifact(self, *, system_prompt, run_context):
        from src.brain.evolution_artifacts import write_round_1_prompt_artifact
        return write_round_1_prompt_artifact(
            self, system_prompt=system_prompt, run_context=run_context,
        )

    def _write_round_artifact(self, **kwargs):
        from src.brain.evolution_artifacts import write_round_artifact
        return write_round_artifact(self, **kwargs)

    def _emit_artifact(self, **kwargs):
        from src.brain.evolution_artifacts import emit_artifact
        return emit_artifact(self, **kwargs)

    def _save_proposal(self, proposal_type, data):
        from src.brain.evolution_artifacts import save_proposal
        return save_proposal(self, proposal_type, data)
```

NOTE: read the original method signatures carefully — some have positional-only or keyword-only kwargs. Match them in the delegator exactly.

- [ ] **Step 4: Run tests**

```
pytest tests/test_evolution_engine.py -v 2>&1 | tail -10
```
Expected: PASS (existing counts).

```
pytest tests/ -q --ignore=tests/regression 2>&1 | tail -3
```
Expected: 1912 PASS / 1 skipped / 0 fail.

- [ ] **Step 5: Commit**

```
git add src/brain/evolution_artifacts.py src/brain/evolution_engine.py
git commit -m "refactor(evolution): extract artifacts/serialization into evolution_artifacts module"
```

---

## Task 3: Extract Validators into `evolution_validators.py`

**Files:**
- Create: `src/brain/evolution_validators.py`
- Modify: `src/brain/evolution_engine.py` (replace method bodies with delegators)
- Test: existing tests pass without modification.

Methods being extracted (from `EvolutionEngine` to `evolution_validators.py`):
- `_validate_tool_binding` (L1154) → `validate_tool_binding`
- `_validate_tool_quality` (L1218) → `validate_tool_quality`
- `_find_similar_skill` (L1304) → `find_similar_skill`
- `_compress_skill_content` (L1339) → `compress_skill_content`
- `_auto_classify_triggers` (L1598) → `auto_classify_triggers`
- `_validate_skill` (L1678) → `validate_skill`
- `_extract_relevant_replay` (L1714) → `extract_relevant_replay`
- `_validate_skill_facts` (L1741) → `validate_skill_facts`
- `_validate_skill_injection` (L1799) → `validate_skill_injection`
- `_check_skill_overmatch` (L1894) → `check_skill_overmatch`
- `_validate_skill_quality` (L1940) → `validate_skill_quality`

(Line numbers shift after Task 1 + Task 2; verify with `grep -n`.)

- [ ] **Step 1: Create `src/brain/evolution_validators.py`**

Use Write tool to create the file with this skeleton:

```python
"""Validators for the evolution stage.

Spec #4 module split: these functions used to live as methods of
EvolutionEngine. They moved here because their dependencies on the
engine instance are narrow (skill_library, memory_manager, _run_context
for some) and they are conceptually a single layer.

Each engine method now retains a 2-line delegator into the matching
function below. Tests calling engine._validate_*, engine._find_similar_skill,
engine._auto_classify_triggers, etc. flow through the delegators unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Function bodies will be added in Step 2.
```

- [ ] **Step 2: Move method bodies into `evolution_validators.py`**

For each of the 11 methods, transform method → free function with `engine` as first param. Same pattern as Task 2 Step 2:

- Replace `self` with `engine`
- Replace `self.X` with `engine.X`
- Replace internal calls like `self._compress_skill_content(...)` with the corresponding free-function call: e.g. `compress_skill_content(engine, ...)` if cross-module, OR with a direct `engine._compress_skill_content(...)` (which delegates back). Prefer the cross-module direct-call style to avoid extra hops.

NOTE: validators that call `self._handle_*` (handlers, in Task 4 still on the class) should keep using `engine._handle_*` since those are class methods. The delegator pattern works in both directions: validators call class methods via `engine.method`, and class methods call validators via the new module's free functions. That's fine.

- [ ] **Step 3: Replace method bodies in `evolution_engine.py` with delegators**

For each of the 11 methods, replace the body with a 2-line delegator. Example for the most complex one:

```python
    def _validate_skill(self, skill_name, content, motivation, trigger):
        from src.brain.evolution_validators import validate_skill
        return validate_skill(self, skill_name, content, motivation, trigger)
```

For simpler ones:

```python
    def _validate_tool_binding(self, tool):
        from src.brain.evolution_validators import validate_tool_binding
        return validate_tool_binding(self, tool)

    def _find_similar_skill(self, content, category, skill_name):
        from src.brain.evolution_validators import find_similar_skill
        return find_similar_skill(self, content, category, skill_name)
```

Be careful to PRESERVE the original method's parameter signatures (positional, keyword-only markers, defaults). The delegator must accept the same call shapes as the old method.

- [ ] **Step 4: Run tests**

```
pytest tests/test_evolution_engine.py tests/test_tool_validation.py -v 2>&1 | tail -10
```
Expected: PASS.

```
pytest tests/ -q --ignore=tests/regression 2>&1 | tail -3
```
Expected: 1912 PASS / 1 skipped / 0 fail.

- [ ] **Step 5: Commit**

```
git add src/brain/evolution_validators.py src/brain/evolution_engine.py
git commit -m "refactor(evolution): extract validators into evolution_validators module"
```

---

## Task 4: Extract Handlers into `evolution_handlers.py`

**Files:**
- Create: `src/brain/evolution_handlers.py`
- Modify: `src/brain/evolution_engine.py` (replace method bodies with delegators; update `_execute_tool` / `_execute_write_tool` to call new module)
- Test: existing tests pass without modification.

Methods being extracted (from `EvolutionEngine` to `evolution_handlers.py`):
- `_continuation_prompt` (staticmethod, L929) → `continuation_prompt`
- `_phase_system_prompt` (staticmethod, L906) → `phase_system_prompt`
- `_handle_author_tool` (L1097) → `handle_author_tool`
- `_handle_write_skill` (L1384) → `handle_write_skill`
- `_handle_performance_stats` (L1999) → `handle_performance_stats`
- `_compute_performance_stats` (L2017) → `compute_performance_stats`

The class retains:
- `_execute_tool` and `_execute_write_tool` — UPDATE these dispatchers to call the new module's free functions instead of self-methods. (See Step 4.)

- [ ] **Step 1: Create `src/brain/evolution_handlers.py`**

Use Write tool:

```python
"""Tool handlers for the evolution stage.

Spec #4 module split: these handlers used to live as methods of
EvolutionEngine. They moved here as the largest concentration of LOC
in the original file (~600 lines). Each retains a 2-line delegator on
the class so existing test code (engine._handle_write_skill, etc.)
continues to work.

The dispatchers (_execute_tool, _execute_write_tool) STAY on
EvolutionEngine and now call into this module's free functions
directly (skipping the delegator hop for the hot path).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# Function bodies will be added in Step 2.
```

- [ ] **Step 2: Move method bodies into `evolution_handlers.py`**

For each of the 6 methods listed: paste body, replace `self` with `engine`, etc. Same pattern as Tasks 2-3.

For staticmethods (`_continuation_prompt`, `_phase_system_prompt`): they have no `self` at all. Just rename without the staticmethod decorator and with no leading underscore in the new location:

```python
def continuation_prompt(*, next_is_read_phase, has_mutating_actions,
                        enforce_target_tokens, target_input_tokens,
                        total_input_tokens, min_rounds, round_number):
    """(Extracted from EvolutionEngine._continuation_prompt — staticmethod.)"""
    # ... body ...

def phase_system_prompt(is_read_phase: bool) -> str:
    """(Extracted from EvolutionEngine._phase_system_prompt — staticmethod.)"""
    from src.brain.evolution_engine import EVOLUTION_SYSTEM_PROMPT
    return EVOLUTION_SYSTEM_PROMPT
```

NOTE: `phase_system_prompt` references the constant `EVOLUTION_SYSTEM_PROMPT` which lives in `evolution_engine.py`. Use a deferred import inside the function to avoid circular imports.

- [ ] **Step 3: Replace method bodies in `evolution_engine.py` with delegators**

```python
    @staticmethod
    def _phase_system_prompt(is_read_phase: bool) -> str:
        from src.brain.evolution_handlers import phase_system_prompt
        return phase_system_prompt(is_read_phase)

    @staticmethod
    def _continuation_prompt(**kwargs):
        from src.brain.evolution_handlers import continuation_prompt
        return continuation_prompt(**kwargs)

    def _handle_author_tool(self, tool_input):
        from src.brain.evolution_handlers import handle_author_tool
        return handle_author_tool(self, tool_input)

    def _handle_write_skill(self, tool_input):
        from src.brain.evolution_handlers import handle_write_skill
        return handle_write_skill(self, tool_input)

    def _handle_performance_stats(self, tool_input):
        from src.brain.evolution_handlers import handle_performance_stats
        return handle_performance_stats(self, tool_input)

    def _compute_performance_stats(self, metric, character):
        from src.brain.evolution_handlers import compute_performance_stats
        return compute_performance_stats(self, metric, character)
```

- [ ] **Step 4: Leave `_execute_tool` and `_execute_write_tool` AS-IS (delegator hop is fine)**

The existing dispatchers call `self._handle_write_skill(...)` etc. After Step 3, those calls flow through the new 2-line delegators into the `evolution_handlers` module. The extra stack frame per tool call is negligible.

Verify by reading `_execute_tool` (around L1053) and `_execute_write_tool` (around L1079) — they should continue to work without modification. Do NOT rewrite them in this task. If a future cleanup wants to elide the delegator hop in the dispatchers, it's a separate refactor.

- [ ] **Step 5: Run tests**

```
pytest tests/test_evolution_engine.py tests/test_token_optimization.py -v 2>&1 | tail -10
```
Expected: PASS.

```
pytest tests/ -q --ignore=tests/regression 2>&1 | tail -3
```
Expected: 1912 PASS / 1 skipped / 0 fail.

- [ ] **Step 6: Commit**

```
git add src/brain/evolution_handlers.py src/brain/evolution_engine.py
git commit -m "refactor(evolution): extract handlers into evolution_handlers module"
```

---

## Task 5: Update `loop.py` Import + Final Verification

**Files:**
- Modify: `src/agent/loop.py:4484` (one-line import shift)
- Test: full pytest

- [ ] **Step 1: Locate the import**

```
grep -n "from src.brain.evolution_engine import" src/agent/loop.py
```
Expected: 1 match around L4484:

```python
            from src.brain.evolution_engine import EvolutionEngine, build_evolution_context
```

- [ ] **Step 2: Split the import**

The shim makes both forms work, but per spec §3.4 we should migrate `loop.py` to import `build_evolution_context` from its new home:

Replace:

```python
            from src.brain.evolution_engine import EvolutionEngine, build_evolution_context
```

with:

```python
            from src.brain.evolution_engine import EvolutionEngine
            from src.postrun.context_builder import build_evolution_context
```

- [ ] **Step 3: Verify file sizes**

```
wc -l src/brain/evolution_engine.py src/postrun/context_builder.py src/brain/evolution_artifacts.py src/brain/evolution_validators.py src/brain/evolution_handlers.py
```

Expected approximate line counts:
- `evolution_engine.py`: ~700 (down from 2433)
- `context_builder.py`: ~1600 (up from 1058)
- `evolution_artifacts.py`: ~200
- `evolution_validators.py`: ~700
- `evolution_handlers.py`: ~600

- [ ] **Step 4: Full test suite**

```
pytest tests/ -q --ignore=tests/regression
```
Expected: 1912 PASS / 1 skipped / 0 fail.

- [ ] **Step 5: Sanity import check**

```
python -c "from src.brain.evolution_engine import EvolutionEngine, EvolutionAction, build_evolution_context, EvolutionContextBundle; from src.brain.evolution_handlers import handle_write_skill, handle_author_tool, handle_performance_stats; from src.brain.evolution_validators import validate_skill, find_similar_skill, compress_skill_content; from src.brain.evolution_artifacts import emit_artifact, serialize_message; print('all imports OK')"
```
Expected: `all imports OK`.

- [ ] **Step 6: Smoke check the shim**

```
python -c "from src.brain.evolution_engine import build_evolution_context, EvolutionContextBundle, format_combat_replay; print('shim imports OK')"
```
Expected: `shim imports OK` (re-exports from context_builder still resolve through the shim).

- [ ] **Step 7: Git status clean**

```
git status
```
Expected: clean working tree (only untracked / .log files unrelated).

- [ ] **Step 8: Commit log review**

```
git log --oneline 74e7241..HEAD
```
Expected: 5 commits matching Tasks 1-4 + this one (since Task 5 only touches loop.py, it gets its own commit OR can be folded into a final cleanup commit — see Step 9).

- [ ] **Step 9: Commit (if loop.py modified)**

```
git add src/agent/loop.py
git commit -m "refactor(loop): import build_evolution_context from new home"
```

If `loop.py` was unchanged in Step 2 (e.g., the shim was deemed sufficient), skip this commit and document the decision in the verification report.

---

## Spec Coverage Self-Check

| Spec section | Task(s) |
|---|---|
| §2 Scope: mechanical split into 4 sibling modules | Tasks 1-4 |
| §2 Scope: absorb context-rendering into context_builder.py | Task 1 |
| §2 Scope: re-export shim for backward-compat | Task 1 (Step 5) |
| §3.1 Target file layout (~700 LOC engine, ~600 handlers, ~700 validators, ~200 artifacts) | Tasks 1-4 (verified in Task 5 Step 3) |
| §3.2 Method-to-function conversion (engine first arg) | Tasks 2, 3, 4 (delegator pattern) |
| §3.3 Backward-compat shim | Task 1 Step 5 |
| §3.4 Import-site audit | Task 5 Step 2 |
| §3.5 Dataclass placement (EvolutionAction stays; EvolutionContextBundle moves) | Task 1 Step 2 |
| §3.6 Files affected | Tasks 1-4 (created files), Task 5 (modified loop.py) |
| §4 Config (no new) | Covered by absence |
| §5 Caching (no effect) | Covered by absence |
| §6 Error handling (no effect) | Covered by absence |
| §7 Testing strategy: full pytest before/after, no new tests | Tasks 1-5 (each runs pytest) |
| §8 Risks: circular imports, hidden self-state coupling, test-import drift, shim becoming permanent | Tasks 1-4 (deferred imports inside method bodies prevent cycles); shim cleanup is explicitly a follow-up |
| §9 Non-goals (no semantic refactor, no new prompts/tools, etc.) | Covered by mechanical-only edits |
