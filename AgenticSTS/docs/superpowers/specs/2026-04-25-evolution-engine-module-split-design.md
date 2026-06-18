# Evolution Engine Module Split

**Date:** 2026-04-25
**Status:** Design — pending implementation plan
**Hard dependency:** `2026-04-25-evolution-tool-cut-and-prompt-rewrite-design.md` (#3) must land first. Splitting before the tool cut would mean splitting code that #3 then deletes — wasted effort, larger merge surface.
**Starting state assumed by this spec:** main + #1 + #2 + #3 all landed. Concretely:
- `_handle_update_guide` and `_handle_update_card_note` are gone (deleted by #3)
- `_render_combat_guides`, `_render_deck_guides`, `_render_card_notes` are gone (deleted by #3)
- `_phase_system_prompt` is now a static constant (rewritten by #3)
- `EvolutionContextBundle.summary` keys are pruned (per #3 §3.7)

LOC estimates below reflect the post-#3 size of `evolution_engine.py` (~2350 lines), not today's 2794.

## 1. Problem

`src/brain/evolution_engine.py` is ~2350 lines (post-#3). It mixes six unrelated concerns in one file:

1. The `EvolutionEngine` class proper — driver loop, tool dispatch, round bookkeeping (~600 lines).
2. Tool handlers — `_handle_write_skill` (rewritten by #3), `_handle_author_tool`, `_handle_performance_stats` (~400 lines).
3. Skill validators — `_validate_skill_facts`, `_validate_skill_injection`, `_check_skill_overmatch`, `_validate_skill_quality`, `_validate_skill`, `_validate_tool_binding`, `_validate_tool_quality` (~500 lines).
4. Skill dedup helpers — `_find_similar_skill`, `_compress_skill_content`, `_auto_classify_triggers`, `_extract_relevant_replay` (~300 lines).
5. Context rendering — `_render_summary`, `_render_dynamic_tools`, `_render_replay_package`, `_render_triggered_skills`, `build_evolution_context`, `format_combat_replay`, `_format_enemy_deltas`, `_format_delta_line`, `_select_smart_episodes`, `_truncate_at_boundary` (~550 lines after #3 deletes the three guide/note renderers). **Most of this duplicates concerns already split into `src/postrun/context_builder.py`** — the file boundary between the two is messy.
6. Serialization + artifact writers — `_serialize_*`, `_write_round_*_artifact`, `_emit_artifact`, `_save_proposal` (~200 lines).

The size makes targeted edits (like spec #3) noisy: every diff touches the same gigantic file, hot-spot conflicts pile up, and onboarding readers must scroll through unrelated concerns.

## 2. Scope

**In scope:**
- A mechanical, behavior-preserving split of `evolution_engine.py` into 4 sibling modules under `src/brain/`, plus consolidation of context-rendering into the existing `src/postrun/context_builder.py`.
- Updated import sites (callers of `EvolutionEngine`, `build_evolution_context`, `format_combat_replay`, `EvolutionAction`, etc.).
- A re-export shim in `src/brain/evolution_engine.py` for backward-compat imports during the migration window.

**Out of scope:**
- Any behavior change. No prompt edits. No new tools. No schema changes. No new tests beyond import-path adjustments.
- Class-level redesign. `EvolutionEngine` stays one class; we just relocate its methods to free helper modules where the methods don't depend on `self`.
- Splitting `context_builder.py`. It absorbs material; it does not get split itself in this spec.

## 3. Architecture

### 3.1 Target file layout

| File | Responsibility | Approx LOC | Actual after merge |
|---|---|---:|---:|
| `src/brain/evolution_engine.py` | `EvolutionEngine` class + `run_evolution` driver loop + `EvolutionAction` dataclass + `EVOLUTION_SYSTEM_PROMPT` constant (~150 LOC) + 26 thin delegators + re-export shim. `EvolutionContextBundle` MOVED to context_builder. | ~700 | **938** |
| `src/brain/evolution_handlers.py` | Tool-handler functions: `handle_write_skill`, `handle_author_tool`, `handle_performance_stats` + `compute_performance_stats` + `phase_system_prompt` + `continuation_prompt`. All accept the `EvolutionEngine` instance as first arg; no longer methods. | ~600 | **524** |
| `src/brain/evolution_validators.py` | Skill validation + dedup + auto-classify: `validate_skill_facts`, `validate_skill_injection`, `check_skill_overmatch`, `validate_skill_quality`, `validate_skill`, `validate_tool_binding`, `validate_tool_quality`, `find_similar_skill`, `compress_skill_content`, `auto_classify_triggers`, `extract_relevant_replay`. All free functions. | ~700 | **699** |
| `src/brain/evolution_artifacts.py` | Serialization + artifact writers: `serialize_message`, `serialize_response`, `serialize_content`, `filter_response_content`, `write_round_1_prompt_artifact`, `write_round_artifact`, `emit_artifact`, `save_proposal`. | ~200 | **215** |
| `src/postrun/context_builder.py` | **Absorbs** the surviving evolution-context renderers from `evolution_engine.py`: `_render_summary`, `_render_dynamic_tools`, `_render_replay_package`, `_render_triggered_skills`, plus `build_evolution_context`, `format_combat_replay`, `_format_enemy_deltas`, `_format_delta_line`, `_select_smart_episodes`, `_truncate_at_boundary`, `_section`. After absorption it becomes the single home for evolution-context rendering. (`_current_run_build` was deleted as dead code in spec #3.) | +550 | **+374 (1058 → 1432)** |

The "Approx LOC" target underestimated `evolution_engine.py` by ~240 lines because the large `EVOLUTION_SYSTEM_PROMPT` constant (~150 LOC) plus 26 delegators (each 2 lines) stay in the file. This is intentional — the spec lists `EVOLUTION_SYSTEM_PROMPT` among items kept in the engine.

(The three renderers `_render_combat_guides`, `_render_deck_guides`, `_render_card_notes` are already gone — deleted by #3. They never appear in the `context_builder.py` absorbed set.)

### 3.2 Method-to-function conversion

`EvolutionEngine` methods that don't materially depend on instance state become free functions:

| Method | Becomes | Self-deps |
|---|---|---|
| `_filter_response_content` | `staticmethod` already; move out as free function | none |
| `_continuation_prompt` | `staticmethod` already; move to `evolution_handlers.py` (or new `evolution_prompts.py`) | none |
| `_serialize_*` | move to `evolution_artifacts.py` | none |
| `_write_round_*_artifact`, `_emit_artifact`, `_save_proposal` | move to `evolution_artifacts.py`, accept `engine: EvolutionEngine` arg | reads `self._artifact_dir` etc. |
| `_handle_*` | move to `evolution_handlers.py`, accept `engine: EvolutionEngine` arg | reads `self._dynamic_registry`, `self._skill_library`, `self._memory_manager` |
| `_validate_*`, `_find_similar_skill`, `_compress_skill_content`, `_auto_classify_triggers`, `_extract_relevant_replay` | move to `evolution_validators.py`, accept narrow context (e.g., `skill_library`, `memory_manager`, `replay_package`) instead of full engine | targeted reads only |

The class retains:
- `__init__`
- `run_evolution`
- `_execute_tool` and `_execute_write_tool` — thin dispatchers that call out to handler functions
- Members: `self._backend`, `self._tool_executor`, `self._dynamic_registry`, `self._skill_library`, `self._memory_manager`, `self._tool_preprocessor`, `self._plan_verifier`, `self._snapshot_store`, `self._session_logger`, `self._artifact_dir`, `self._last_session_summary`, etc.

### 3.3 Backward-compat shim

To avoid breaking `from src.brain.evolution_engine import build_evolution_context` and similar imports across the codebase mid-PR, the existing `evolution_engine.py` keeps re-export aliases for one PR cycle:

```python
# src/brain/evolution_engine.py (after split)
from src.postrun.context_builder import (
    build_evolution_context,
    format_combat_replay,
    EvolutionContextBundle,  # if it stays here, OR re-export from context_builder
)
from src.brain.evolution_handlers import (
    handle_write_skill, handle_author_tool, handle_performance_stats,
)
# ... EvolutionEngine class body remains here
```

A follow-up cleanup PR removes the shim once all import sites are updated. No deprecation warning needed; the migration window is short (one PR) since the project has no external consumers.

### 3.4 Import-site audit

Sites that import from `src.brain.evolution_engine`:

- `src/agent/loop.py:4565` — `from src.brain.evolution_engine import EvolutionEngine, build_evolution_context`. After split: import `EvolutionEngine` from `src.brain.evolution_engine`, import `build_evolution_context` from `src.postrun.context_builder`.
- `src/postrun/context_builder.py` — `ReplayPackage`, `build_decision_digest`, `build_replay_package` already live here; they keep their public exports.
- Any test file in `tests/test_evolution*` — adjust imports.
- `frontend/` — does not import Python modules.

The audit is a `grep` away. The number of import-site touches is small (~5-10 lines).

### 3.5 Dataclass placement

- `EvolutionAction` → stays in `src/brain/evolution_engine.py`. Used by callers (loop.py) and is the *output* of evolution.
- `EvolutionContextBundle` → moves to `src/postrun/context_builder.py`. It is the *output* of `build_evolution_context`, which lives there.

### 3.6 Files affected (summary)

**Created:**
- `src/brain/evolution_handlers.py`
- `src/brain/evolution_validators.py`
- `src/brain/evolution_artifacts.py`

**Modified:**
- `src/brain/evolution_engine.py` (drastically smaller; keeps `EvolutionEngine`, `EvolutionAction`, re-export shim).
- `src/postrun/context_builder.py` (gains `EvolutionContextBundle`, `build_evolution_context`, surviving `_render_*`, `format_combat_replay`).
- `src/agent/loop.py` (one-line import shift for `build_evolution_context`).
- `tests/test_evolution_engine.py` (and any sibling test files) — import-path adjustments only.

**Deleted:**
- None. Pure relocation.

## 4. Config

No new config. No env vars touched.

## 5. Caching

No effect on caching. Pure refactor.

## 6. Error handling

No effect. Behavior preserved.

## 7. Testing strategy

This is a **mechanical refactor**. Validation strategy:

1. Run the **full** test suite before split to capture baseline pass/fail.
2. Apply split. Update imports.
3. Run the full test suite. Diff against baseline. New failures must trace to import errors only.
4. **No new tests are written**. If a function had no test before, it gets none now.

Optionally:
- A `tests/test_evolution_imports.py` smoke test that imports each new module and asserts the public symbols exist. Catches import-time errors (circular imports, missing symbols) without exercising behavior.

## 8. Risks

- **Circular imports.** Splitting handlers + validators + artifacts can introduce cycles (`evolution_engine → evolution_handlers → evolution_validators → evolution_engine`). Mitigation: handlers import validators (one direction); engine imports handlers (one direction); validators do NOT import handlers or engine. Define the dependency direction up front and forbid edges that would close a cycle.
- **Hidden self-state coupling.** A method that looks free-function-able may actually depend on a `self` field via a deep call chain. Mitigation: when in doubt, pass `engine: EvolutionEngine` as the first arg rather than dissecting dependencies; tighten later.
- **Test-import drift.** Tests that mock `src.brain.evolution_engine._handle_write_skill` directly will break. Mitigation: grep tests for these names and update mock targets.
- **Re-export shim becoming permanent.** Without a follow-up, the shim accretes dead aliases forever. Mitigation: schedule cleanup PR in same week as split; spec ends with cleanup as a non-goal here, called out as TODO.

## 9. Non-goals (explicit)

- No semantic refactor: nothing about how evolution works, what it writes, or what it reads changes.
- No new prompt content, no new validation rule, no new tool, no schema change.
- No restructure of `context_builder.py` itself. It absorbs more code; its internal organization is left for a future spec if needed.
- No removal of the re-export shim within this spec — that is a follow-up cleanup PR.
- No subdir-style restructure (`src/brain/evolution/...`). Flat siblings are simpler and avoid the `__init__.py` plumbing question for this codebase's import style.
