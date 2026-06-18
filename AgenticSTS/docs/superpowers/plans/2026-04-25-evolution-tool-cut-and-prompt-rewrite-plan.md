# Evolution Tool Cut & Prompt Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut evolution's write-tool surface from 4 tools to 2, rewrite `write_skill` schema with strict cross-run grounding (`evidence` + `rationale`), wire shared trace cache from Turn 1/2, simplify the dynamic system prompt, and lower round budget — leaving evolution as a focused cross-run skill / tool authoring stage.

**Architecture:** Mechanical deletions (Tasks 1, 2) come first; small static-config and prompt simplifications (Tasks 3, 4) follow; structural change (trace cache wiring, Task 5) and the largest schema rewrite (Task 6) come last. Each commit leaves the system in a working state.

**Tech Stack:** Python 3.12, pytest, anthropic SDK message format. No new libraries.

**Spec:** [`docs/superpowers/specs/2026-04-25-evolution-tool-cut-and-prompt-rewrite-design.md`](../specs/2026-04-25-evolution-tool-cut-and-prompt-rewrite-design.md)

---

## File Map

| File | Action | Notes |
|---|---|---|
| `src/brain/write_tools.py` | Modify | Delete `UPDATE_GUIDE` + `UPDATE_CARD_NOTE` schema constants; remove from `MUTATING_WRITE_TOOLS` list; rewrite `WRITE_SKILL` schema with `evidence` + `rationale` |
| `src/brain/evolution_engine.py` | Modify | Delete `_handle_update_guide` (~140 lines) + `_handle_update_card_note` (~100 lines); rewrite `_handle_write_skill` to consume new fields with strict validation; collapse `_phase_system_prompt` to static `EVOLUTION_SYSTEM_PROMPT`; remove deleted-tool refs from `EVOLUTION_SYSTEM_PROMPT` and `_continuation_prompt`; delete `_render_combat_guides` / `_render_deck_guides` / `_render_card_notes` (3 renderers); drop call sites in `build_evolution_context`; add `combat_trace_text` kwarg to `run_evolution`; restructure first user message to multi-block with cached prefix |
| `src/agent/loop.py` | Modify | `_post_run_evolution` passes `self._pending_combat_trace` into `engine.run_evolution(combat_trace_text=...)` |
| `config.py` | Modify | `EVOLUTION_MAX_ROUNDS` default 6 → 3 |
| `tests/test_evolution_engine.py` | Modify | Delete tests for deleted handlers; update `test_write_skill` / `test_write_skill_missing_fields` to use new schema; add tests for new validation rules; add tests for cached prefix wiring; add tests for section pruning |

`src/skills/merge_pipeline.py`, `src/memory/write_gate*`, `RECALL_ENCOUNTER_SCHEMA`, `GET_PERFORMANCE_STATS`, `AUTHOR_TOOL` and `_handle_author_tool` are untouched.

**Note on round-budget default**: spec §3.6 says current default is 5; actual `config.py:480` shows 6. We follow spec's intent (lower to 3 regardless).

**Sequencing rationale**: Tasks 1–2 are pure deletions and leave the system functional. Tasks 3–4 are static-config / prompt cleanup with no behavioral risk. Task 5 introduces structural change to the user-message shape; running this AFTER cleanup keeps the diff focused. Task 6 (write_skill schema) is the most invasive — placed last so it lands on a smaller, cleaner code surface.

---

## Task 1: Delete `update_guide` + `update_card_note` Tool Surface

**Files:**
- Modify: `src/brain/write_tools.py`
- Modify: `src/brain/evolution_engine.py` (handlers + dispatch + system prompt + continuation_prompt)
- Modify: `tests/test_evolution_engine.py` (delete tests for deleted handlers)

- [ ] **Step 1: Establish baseline test count**

```
pytest tests/test_evolution_engine.py -v 2>&1 | tail -3
```
Note the count for comparison after the delete.

- [ ] **Step 2: Delete the two tool schemas in `write_tools.py`**

Edit `src/brain/write_tools.py`. DELETE:

1. The entire `UPDATE_GUIDE: dict = { ... }` block (currently L133-169).
2. The entire `UPDATE_CARD_NOTE: dict = { ... }` block (currently L201-232).
3. From the docstring at the top of the file, remove the lines:
   ```
   - update_guide: Improve a strategy guide section
   - update_card_note: Replace the experience note for a specific card
   ```
4. From `MUTATING_WRITE_TOOLS` list (L239-244), remove `UPDATE_GUIDE` and `UPDATE_CARD_NOTE` entries. The list should become:
   ```python
   MUTATING_WRITE_TOOLS: list[dict] = [
       AUTHOR_TOOL,
       WRITE_SKILL,
   ]
   ```

After this edit, `MUTATING_WRITE_TOOLS` has 2 entries; `MUTATING_WRITE_TOOL_NAMES` becomes `frozenset({"author_tool", "write_skill"})`.

- [ ] **Step 3: Delete handlers + dispatch entries in `evolution_engine.py`**

Edit `src/brain/evolution_engine.py`:

1. Delete `_handle_update_guide` (currently L1935-2073, ~140 lines). Locate via:
   ```
   grep -n "def _handle_update_guide" src/brain/evolution_engine.py
   ```
   Delete the entire method body.

2. Delete `_handle_update_card_note` (currently L2234-2336, ~100 lines). Locate via:
   ```
   grep -n "def _handle_update_card_note" src/brain/evolution_engine.py
   ```
   Delete the entire method body.

3. Find the tool dispatch dict (around L1063-1075). It currently contains entries:
   ```python
   "write_skill": self._handle_write_skill,
   "update_guide": self._handle_update_guide,
   ...
   "update_card_note": self._handle_update_card_note,
   ```
   Delete the `"update_guide"` and `"update_card_note"` entries.

4. Find the docstring listing tool names (around L46-50):
   ```python
   "author_tool", "write_skill", "update_guide",
   "get_performance_stats", "update_card_note",
   ```
   Update to:
   ```python
   "author_tool", "write_skill",
   "get_performance_stats",
   ```

- [ ] **Step 4: Clean `EVOLUTION_SYSTEM_PROMPT`**

In `src/brain/evolution_engine.py`, find `EVOLUTION_SYSTEM_PROMPT = """\` (around L130) and remove the deleted-tool references:

Find and DELETE these lines from inside the docstring (they currently appear in the "Guidelines" section starting around L137):

```
- Update a guide (update_guide) when existing knowledge is WRONG or INCOMPLETE
- Update a card note (update_card_note) to write an experience-based evaluation \
for a card. Prioritize cards without existing notes in the Card Notes section. \
Base your note on: (1) The card's rules_text from the Card Mechanics Reference, \
(2) Observable combat outcomes from the Combat Digest, \
(3) Keyword interactions deducible from card descriptions, \
(4) Act death correlations from Card Memory Stats. \
Evidence thresholds: mechanic discoveries can be low-sample if grounded in rules_text; \
tier ratings and take/skip guidance require >=10 plays AND act death data. \
Do NOT write notes for generated/status cards (Shiv, Burn, Slimed, Wound). \
Only write discoveries logically derivable from card descriptions and gameplay evidence.
```

Adjust the surrounding text so the bullet structure remains coherent (the line above is `- Create a skill (write_skill) when ...` and the line below is `- Query performance stats ...`).

- [ ] **Step 5: Clean `_continuation_prompt`**

Find `_continuation_prompt` (around L913). Look for the strings that mention deleted tools and remove them. Specifically, around L938:

```python
    if not has_mutating_actions:
        return (
            "Diagnosis is sufficient. Move to execution now. "
            "Call the single highest-value mutating tool next: update_guide, update_card_note, "
            "write_skill, or author_tool. "
            ...
        )
```

Replace `update_guide, update_card_note, write_skill, or author_tool` with `write_skill or author_tool`.

If there are other similar mentions in `_continuation_prompt`, clean them too. Use:
```
grep -n "update_guide\|update_card_note" src/brain/evolution_engine.py
```
Expected: after this step, 0 matches in the production code (only references to the deleted strings might remain in tests/comments, which Step 6 handles).

- [ ] **Step 6: Delete tests for deleted handlers in `tests/test_evolution_engine.py`**

```
grep -n "_handle_update_guide\|_handle_update_card_note" tests/test_evolution_engine.py
```

For each test that calls these methods, delete the entire test function. Likely candidates are tests with names like `test_update_guide_*`, `test_update_card_note_*`. Some shared test helpers may also need removal if they were only used by deleted tests.

Also: search for tests that assert dispatch dict keys or `MUTATING_WRITE_TOOL_NAMES` content for the deleted tools, and update those to expect the new 2-entry surface.

- [ ] **Step 7: Run tests**

```
pytest tests/test_evolution_engine.py -v 2>&1 | tail -10
```
Expected: tests pass (count down from baseline by however many you deleted). NO failures from `AttributeError: 'EvolutionEngine' object has no attribute '_handle_update_guide'`.

```
pytest tests/ -q --ignore=tests/regression
```
Expected: no NEW failures attributable to this delete.

- [ ] **Step 8: Commit**

```
git add src/brain/write_tools.py src/brain/evolution_engine.py tests/test_evolution_engine.py
git commit -m "refactor(evolution): delete update_guide and update_card_note tools"
```

---

## Task 2: Section Pruning — Drop `_render_combat_guides` / `_render_deck_guides` / `_render_card_notes`

**Files:**
- Modify: `src/brain/evolution_engine.py` (delete 3 renderer functions + their call sites in `build_evolution_context`; update `EvolutionContextBundle`)
- Test: `tests/test_evolution_engine.py` (update tests that check section keys or content)

- [ ] **Step 1: Locate the renderers**

```
grep -n "^def _render_combat_guides\|^def _render_deck_guides\|^def _render_card_notes\|^def build_evolution_context" src/brain/evolution_engine.py
```
Note exact line numbers (will have shifted after Task 1's deletions). Each renderer is ~30-60 lines.

- [ ] **Step 2: Delete the three renderer functions**

Use the Edit tool, three times (one per function). For each:
1. Locate the function via grep + Read.
2. Delete the entire function body, including its leading docstring and any decorators.
3. After deletion, verify that no other function in the module calls the deleted renderer (besides `build_evolution_context` — handled in Step 3).

```
grep -n "_render_combat_guides\|_render_deck_guides\|_render_card_notes" src/brain/evolution_engine.py
```
Expected after deletion: matches only inside `build_evolution_context` (call sites you'll fix in Step 3).

- [ ] **Step 3: Drop call sites in `build_evolution_context`**

Find the function (around L2624; line will have shifted). Read it carefully. It accumulates section text into a list and tracks per-section stats. For each of the three deleted renderers:
1. Find the line(s) where the renderer is called (e.g., `combat_section, combat_stat = _render_combat_guides(...)`).
2. Delete the call AND any subsequent lines that append the result text/stat to the bundle.

After this edit, `build_evolution_context` should no longer reference any of the three deleted renderers.

- [ ] **Step 4: Adjust `EvolutionContextBundle.summary` keys**

Find `EvolutionContextBundle` dataclass (around L115). Look at how `summary` is constructed in `build_evolution_context`. It is likely a dict with section names as keys (e.g., `{"combat_guides": ..., "deck_guides": ..., "card_notes": ..., ...}`). Remove the three deleted-section keys from the dict construction. The dataclass itself uses generic typing, so no field-level changes needed — only the dict construction in `build_evolution_context`.

- [ ] **Step 5: Update tests that check section presence**

```
grep -n "combat_guides\|deck_guides\|card_notes" tests/test_evolution_engine.py tests/test_combat_delta.py
```

For each match in test code:
- If the test asserts the section IS PRESENT in `build_evolution_context` output → DELETE that assertion (or the entire test if its sole purpose was checking that section).
- If the test asserts the section IS ABSENT (e.g., for an "empty" case) → REMOVE the assertion (the section is unconditionally absent now).

DO NOT touch tests that simply use phrases like "combat guides" in unrelated context.

- [ ] **Step 6: Run tests**

```
pytest tests/test_evolution_engine.py tests/test_combat_delta.py -v 2>&1 | tail -10
```
Expected: PASS (with reduced count).

```
pytest tests/ -q --ignore=tests/regression
```
Expected: no NEW failures.

- [ ] **Step 7: Commit**

```
git add src/brain/evolution_engine.py tests/test_evolution_engine.py tests/test_combat_delta.py
git commit -m "refactor(evolution): drop combat_guides/deck_guides/card_notes section renderers"
```

(If `tests/test_combat_delta.py` was not actually touched, omit it from `git add`.)

---

## Task 3: Lower `EVOLUTION_MAX_ROUNDS` Default 6 → 3

**Files:**
- Modify: `config.py:480`
- Test: `tests/test_evolution_engine.py` (one test asserts attribute exists; verify default is 3)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evolution_engine.py`:

```python
def test_evolution_max_rounds_default_is_three():
    """Per spec #3 §3.6, evolution caps at 1 write round (read_only_rounds=2,
    max_rounds=3). Lowering keeps the LLM from filling rounds with low-quality
    proposals."""
    import importlib
    import os

    # Verify the default is 3 (env override unaffected)
    if "STS2_EVOLUTION_MAX_ROUNDS" in os.environ:
        del os.environ["STS2_EVOLUTION_MAX_ROUNDS"]
    import config as _cfg
    importlib.reload(_cfg)
    assert _cfg.EVOLUTION_MAX_ROUNDS == 3
```

- [ ] **Step 2: Run test, verify it fails**

```
pytest tests/test_evolution_engine.py::test_evolution_max_rounds_default_is_three -v
```
Expected: FAIL — current default is `int(os.getenv("STS2_EVOLUTION_MAX_ROUNDS", "6"))`.

- [ ] **Step 3: Update default**

Edit `config.py:480`. Replace:

```python
EVOLUTION_MAX_ROUNDS = int(os.getenv("STS2_EVOLUTION_MAX_ROUNDS", "6"))
```

with:

```python
EVOLUTION_MAX_ROUNDS = int(os.getenv("STS2_EVOLUTION_MAX_ROUNDS", "3"))
```

- [ ] **Step 4: Run test, verify it passes**

```
pytest tests/test_evolution_engine.py::test_evolution_max_rounds_default_is_three -v
```
Expected: PASS.

- [ ] **Step 5: Run full test suite to check no regressions**

```
pytest tests/ -q --ignore=tests/regression
```
Expected: no NEW failures. If a test had hard-coded `6` as the expected default, update it to `3`.

- [ ] **Step 6: Commit**

```
git add config.py tests/test_evolution_engine.py
git commit -m "config(evolution): lower EVOLUTION_MAX_ROUNDS default 6 → 3"
```

---

## Task 4: Collapse `_phase_system_prompt` to Static Prompt

**Files:**
- Modify: `src/brain/evolution_engine.py:891` (`_phase_system_prompt` method)
- Test: `tests/test_evolution_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evolution_engine.py`:

```python
def test_phase_system_prompt_returns_same_text_in_both_phases():
    """Spec #3 §3.3: the system prompt should be byte-stable across phases
    so that the prompt cache hits within a single postrun. Phase signaling
    moves to user-message land (tool_choice + continuation_prompt)."""
    from src.brain.evolution_engine import EvolutionEngine

    read_only = EvolutionEngine._phase_system_prompt(is_read_phase=True)
    write_phase = EvolutionEngine._phase_system_prompt(is_read_phase=False)
    assert read_only == write_phase, (
        "System prompt MUST be invariant across phases for cache stability."
    )
```

- [ ] **Step 2: Run test, verify it fails**

```
pytest tests/test_evolution_engine.py::test_phase_system_prompt_returns_same_text_in_both_phases -v
```
Expected: FAIL — current implementation appends a "READ-ONLY DIAGNOSTIC PHASE" suffix when `is_read_phase=True`.

- [ ] **Step 3: Collapse the method**

Edit `src/brain/evolution_engine.py`. Replace the existing `_phase_system_prompt` (around L891-901):

```python
    @staticmethod
    def _phase_system_prompt(is_read_phase: bool) -> str:
        if not is_read_phase:
            return EVOLUTION_SYSTEM_PROMPT
        return (
            EVOLUTION_SYSTEM_PROMPT
            + "\n\nREAD-ONLY DIAGNOSTIC PHASE:\n"
            + "- You are in diagnosis mode.\n"
            + "- You MUST call at least one read/query tool this round.\n"
            + "- Do not attempt to write or mutate memory in this phase.\n"
            + "- Build a concrete problem list first, then gather evidence.\n"
        )
```

with:

```python
    @staticmethod
    def _phase_system_prompt(is_read_phase: bool) -> str:
        """Return the static evolution system prompt.

        Spec #3 §3.3: the prompt is invariant across phases for prompt-
        cache stability. Phase signaling now relies on the API
        ``tool_choice`` parameter (forces tool use in read phase) and
        the per-round ``_continuation_prompt`` (text guidance for the
        next round). The ``is_read_phase`` parameter is retained for
        backwards-compatible call signatures but is not consulted.
        """
        return EVOLUTION_SYSTEM_PROMPT
```

- [ ] **Step 4: Run test, verify it passes**

```
pytest tests/test_evolution_engine.py::test_phase_system_prompt_returns_same_text_in_both_phases -v
```
Expected: PASS.

- [ ] **Step 5: Run full test suite to spot any regressions**

```
pytest tests/ -q --ignore=tests/regression
```
Expected: no NEW failures. If any test asserted that the read-only phase prompt contains the deleted "READ-ONLY DIAGNOSTIC PHASE" string, update or delete that test.

- [ ] **Step 6: Commit**

```
git add src/brain/evolution_engine.py tests/test_evolution_engine.py
git commit -m "refactor(evolution): collapse _phase_system_prompt to static for cache stability"
```

---

## Task 5: Wire Trace Cache Prefix into Evolution

**Files:**
- Modify: `src/brain/evolution_engine.py` (add `combat_trace_text` kwarg to `run_evolution`; restructure first user message)
- Modify: `src/agent/loop.py:4548` (`_post_run_evolution`)
- Test: `tests/test_evolution_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evolution_engine.py`:

```python
def test_run_evolution_accepts_combat_trace_text_kwarg():
    """Spec #3 §3.4: evolution shares the same cached trace prefix that
    Turn 1/2 produce. The first user message becomes a multi-block
    content list with the trace as a cache_control: ephemeral block."""
    import inspect
    from src.brain.evolution_engine import EvolutionEngine

    sig = inspect.signature(EvolutionEngine.run_evolution)
    assert "combat_trace_text" in sig.parameters, (
        "run_evolution must accept combat_trace_text kwarg per Spec #3 §3.4"
    )
    # Default should be None so callers without trace continue to work
    assert sig.parameters["combat_trace_text"].default is None


def test_run_evolution_first_user_message_has_cached_trace_prefix(monkeypatch):
    """When combat_trace_text is provided, the first user message must be
    a multi-block content list whose first block carries
    cache_control: ephemeral and matches the trace verbatim."""
    from unittest.mock import MagicMock
    from src.brain.evolution_engine import EvolutionEngine

    # Build a minimal engine with a fake backend that captures the messages
    fake_backend = MagicMock()
    captured = {}
    def _spy_call(**kwargs):
        captured["messages"] = kwargs["messages"]
        # Stop the loop on first round by returning end_turn with no tool_use
        from types import SimpleNamespace
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )
    fake_backend.call.side_effect = _spy_call

    engine = EvolutionEngine(
        backend=fake_backend,
        tool_executor=MagicMock(),
        dynamic_registry=None,
        skill_library=MagicMock(),
        memory_manager=None,
        tool_preprocessor=None,
        plan_verifier=None,
        snapshot_store=None,
        session_logger=None,
    )
    trace = "TRACE_BYTES_HERE_FOR_CACHE_KEY"
    engine.run_evolution(
        run_context="## Cross-run summary\n...",
        character="silent",
        max_rounds=1,
        read_only_rounds=0,
        min_rounds=0,
        target_input_tokens=0,
        combat_trace_text=trace,
    )

    msgs = captured.get("messages")
    assert msgs is not None and msgs, "Backend must have been called"
    first = msgs[0]
    assert first["role"] == "user"
    content = first["content"]
    assert isinstance(content, list), "Trace path must use multi-block content"
    assert len(content) >= 2
    assert content[0].get("type") == "text"
    assert content[0].get("text") == trace
    assert content[0].get("cache_control") == {"type": "ephemeral"}


def test_run_evolution_without_trace_uses_string_content():
    """When combat_trace_text is None / empty, first user message remains
    a plain string (backwards compatible)."""
    from unittest.mock import MagicMock
    from src.brain.evolution_engine import EvolutionEngine

    fake_backend = MagicMock()
    captured = {}
    def _spy_call(**kwargs):
        captured["messages"] = kwargs["messages"]
        from types import SimpleNamespace
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )
    fake_backend.call.side_effect = _spy_call

    engine = EvolutionEngine(
        backend=fake_backend,
        tool_executor=MagicMock(),
        dynamic_registry=None,
        skill_library=MagicMock(),
        memory_manager=None,
        tool_preprocessor=None,
        plan_verifier=None,
        snapshot_store=None,
        session_logger=None,
    )
    engine.run_evolution(
        run_context="## Cross-run summary\n...",
        character="silent",
        max_rounds=1,
        read_only_rounds=0,
        min_rounds=0,
        target_input_tokens=0,
        # combat_trace_text omitted
    )
    msgs = captured.get("messages")
    first = msgs[0]
    assert isinstance(first["content"], str)
```

- [ ] **Step 2: Run tests, verify they fail**

```
pytest tests/test_evolution_engine.py -k "combat_trace_text or first_user_message_has_cached_trace or without_trace_uses_string" -v
```
Expected: FAIL — `combat_trace_text` parameter does not exist; first user message is always a plain string.

- [ ] **Step 3: Add `combat_trace_text` kwarg + multi-block construction**

Edit `src/brain/evolution_engine.py`. In `run_evolution` (around L506):

1. Add `combat_trace_text: str | None = None,` to the signature, after `seen_card_names`:

```python
    def run_evolution(
        self,
        run_context: str,
        *,
        character: str = "",
        artifact_dir: Path | None = None,
        target_input_tokens: int | None = None,
        min_rounds: int | None = None,
        max_rounds: int | None = None,
        read_only_rounds: int | None = None,
        seen_card_names: tuple[str, ...] = (),
        combat_trace_text: str | None = None,
    ) -> list[EvolutionAction]:
```

2. Find the first user message construction (currently L567-569):

```python
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": run_context},
        ]
```

Replace with:

```python
        # Spec #3 §3.4: when a trace is provided, render the user
        # message as a multi-block list with the trace as a
        # cache_control: ephemeral prefix, sharing Turn 1/2's
        # 5-minute TTL. Without trace, fall back to plain string for
        # backwards compatibility.
        if combat_trace_text:
            first_user_content: str | list[dict] = [
                {
                    "type": "text",
                    "text": combat_trace_text,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": run_context},
            ]
        else:
            first_user_content = run_context
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": first_user_content},
        ]
```

- [ ] **Step 4: Wire `_post_run_evolution` in loop.py**

Edit `src/agent/loop.py`. Find `_post_run_evolution` (around L4548). Locate the `engine.run_evolution(...)` call inside (around L4571-4577 area). It currently passes:

```python
            actions = await asyncio.to_thread(
                engine.run_evolution,
                context_bundle.text,
                character=run_char,
                artifact_dir=artifact_dir,
                target_input_tokens=config.EVOLUTION_TARGET_INPUT_TOKENS,
                min_rounds=config.EVOLUTION_MIN_ROUNDS,
                max_rounds=config.EVOLUTION_MAX_ROUNDS,
                read_only_rounds=config.EVOLUTION_READ_ONLY_ROUNDS,
                seen_card_names=context_bundle.seen_card_names,
            )
```

Add `combat_trace_text=getattr(self, "_pending_combat_trace", None),` as the LAST kwarg before the closing paren:

```python
            actions = await asyncio.to_thread(
                engine.run_evolution,
                context_bundle.text,
                character=run_char,
                artifact_dir=artifact_dir,
                target_input_tokens=config.EVOLUTION_TARGET_INPUT_TOKENS,
                min_rounds=config.EVOLUTION_MIN_ROUNDS,
                max_rounds=config.EVOLUTION_MAX_ROUNDS,
                read_only_rounds=config.EVOLUTION_READ_ONLY_ROUNDS,
                seen_card_names=context_bundle.seen_card_names,
                combat_trace_text=getattr(self, "_pending_combat_trace", None),
            )
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_evolution_engine.py -k "combat_trace_text or first_user_message_has_cached_trace or without_trace_uses_string" -v
```
Expected: 3 PASS.

```
pytest tests/test_evolution_engine.py -v 2>&1 | tail -5
pytest tests/ -q --ignore=tests/regression
```
Expected: existing tests still PASS; broader suite no NEW failures.

- [ ] **Step 6: Commit**

```
git add src/brain/evolution_engine.py src/agent/loop.py tests/test_evolution_engine.py
git commit -m "feat(evolution): wire combat_trace_text as cached prefix in user message"
```

---

## Task 6: Rewrite `write_skill` Schema with `evidence` + `rationale`

**Files:**
- Modify: `src/brain/write_tools.py` (rewrite `WRITE_SKILL` schema)
- Modify: `src/brain/evolution_engine.py` (rewrite `_handle_write_skill` validation)
- Modify: `src/brain/evolution_engine.py:130` (`EVOLUTION_SYSTEM_PROMPT` — add new write_skill instructions)
- Test: `tests/test_evolution_engine.py` (update existing + add new tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_evolution_engine.py`:

```python
def test_write_skill_rejects_missing_rationale():
    """Spec #3 §3.2: write_skill MUST have a rationale explaining why
    mistake_discovery couldn't catch this from a single trace. Missing
    rationale is a hard reject."""
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1", "r2"],
                    "stat_basis": "win rate 18% vs 42% baseline across 30 silent runs",
                    "anchor_episode": "r1:c3",
                },
                # rationale missing
            })
    assert "rationale" in result.lower()
    assert "REJECTED" in result


def test_write_skill_rejects_short_rationale():
    """Rationale below 30 chars (after stripping) → reject as 'too thin'."""
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1", "r2"],
                    "stat_basis": "win rate 18% vs 42% baseline",
                    "anchor_episode": "r1:c3",
                },
                "rationale": "obvious",  # 7 chars — too short
            })
    assert "rationale" in result.lower()
    assert "REJECTED" in result


def test_write_skill_rejects_too_few_run_ids():
    """evidence.run_ids must contain >=2 distinct ids (cross-run)."""
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1"],  # only 1 run
                    "stat_basis": "win rate 18% vs 42% baseline across silent runs",
                    "anchor_episode": "r1:c3",
                },
                "rationale": (
                    "Pattern emerges only across multiple knowledge_demon "
                    "encounters; single run trace lacks the comparator."
                ),
            })
    assert "run_ids" in result.lower() or "cross-run" in result.lower()
    assert "REJECTED" in result


def test_write_skill_rejects_stat_basis_without_numbers():
    """evidence.stat_basis must reference numeric data
    (heuristic: contains a digit AND comparator phrase)."""
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1", "r2"],
                    "stat_basis": "the player loses sometimes against this enemy",  # no numbers
                    "anchor_episode": "r1:c3",
                },
                "rationale": (
                    "Pattern emerges only across multiple runs; single trace "
                    "lacks the comparator. mistake_discovery wouldn't catch it."
                ),
            })
    assert "stat_basis" in result.lower() or "numeric" in result.lower()
    assert "REJECTED" in result


def test_write_skill_accepts_complete_proposal():
    """Happy path: all required fields present and valid."""
    import tempfile
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as td:
        engine, _, lib = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Knowledge demon stall",
                "category": "combat",
                "content": "Against knowledge_demon, prioritize block over damage when HP < 30.",
                "motivation": "Multiple low-HP losses on knowledge_demon",
                "trigger_state_types": ["combat"],
                "trigger_enemy_names": ["knowledge_demon"],
                "evidence": {
                    "run_ids": ["r_alpha", "r_beta", "r_gamma"],
                    "stat_basis": "win rate 18% vs knowledge_demon (30 runs) vs 42% baseline",
                    "anchor_episode": "r_alpha:combat_4",
                },
                "rationale": (
                    "Pattern emerges across 30+ knowledge_demon runs; single-run "
                    "mistake_discovery cannot see the cross-run win-rate gap."
                ),
            })
    assert "REJECTED" not in result
    assert "SUCCESS" in result or "MERGED" in result


def _make_engine_for_skill_test(tools_dir):
    """Helper: minimal EvolutionEngine for write_skill tests."""
    from unittest.mock import MagicMock
    from src.brain.evolution_engine import EvolutionEngine
    from src.skills.library import SkillLibrary

    backend = MagicMock()
    lib = SkillLibrary()
    engine = EvolutionEngine(
        backend=backend,
        tool_executor=MagicMock(),
        dynamic_registry=None,
        skill_library=lib,
        memory_manager=None,
        tool_preprocessor=None,
        plan_verifier=None,
        snapshot_store=None,
        session_logger=None,
    )
    engine._run_context = "(no run context)"
    return engine, backend, lib
```

Also UPDATE the existing `test_write_skill` and `test_write_skill_missing_fields` tests in the same file. Find them via grep:
```
grep -n "def test_write_skill" tests/test_evolution_engine.py
```

The existing `test_write_skill` (around L129) currently passes a proposal without `evidence` / `rationale`. Update it to pass valid `evidence` + `rationale` so it remains a "happy path" test. The existing `test_write_skill_missing_fields` (around L147) still works — it tests empty `skill_name` rejection, which stays a hard reject regardless of new fields.

- [ ] **Step 2: Run tests, verify they fail**

```
pytest tests/test_evolution_engine.py -k "write_skill" -v
```
Expected: the 5 new tests FAIL with messages like "REJECTED: ..." not present, or non-existent assertions failing because validation gates aren't in place yet. The existing `test_write_skill` may also now fail (expected — schema is changing).

- [ ] **Step 3: Update `WRITE_SKILL` schema in `write_tools.py`**

Edit `src/brain/write_tools.py`. Replace the existing `WRITE_SKILL` schema body (around L48-115) with:

```python
WRITE_SKILL: dict = {
    "name": "write_skill",
    "description": (
        "Create a natural language strategy skill grounded in CROSS-RUN "
        "evidence. Skills are procedural knowledge injected into decision "
        "prompts when their trigger conditions match the game state. "
        "Spec #3: every proposal MUST carry `evidence` (run_ids + stat_basis "
        "+ anchor_episode) and a `rationale` explaining why this pattern "
        "is invisible to single-run mistake_discovery."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "skill_name": {
                "type": "string",
                "description": "Human-readable skill name (e.g., 'Poison lethal timing').",
            },
            "category": {
                "type": "string",
                "description": "Skill category.",
                "enum": [
                    "combat", "deck_building", "map", "rest",
                    "shop", "event", "boss", "character", "general",
                ],
            },
            "content": {
                "type": "string",
                "maxLength": 400,
                "description": (
                    "The strategy knowledge in natural language (≤400 chars). "
                    "Will be injected into LLM prompts. Be specific and actionable."
                ),
            },
            "trigger_state_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "State types that trigger this skill. Empty = always active.",
            },
            "trigger_enemy_names": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Enemy names that trigger this skill. Empty = all enemies.",
            },
            "trigger_requires_cards": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Card names that must be in hand or deck. REQUIRED when content "
                    "mentions specific cards."
                ),
            },
            "trigger_character": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Characters this skill applies to. Empty = all.",
            },
            "motivation": {
                "type": "string",
                "description": "What gameplay experience motivated this skill.",
            },
            "evidence": {
                "type": "object",
                "description": (
                    "Cross-run evidence. ALL three sub-fields required."
                ),
                "properties": {
                    "run_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 2,
                        "description": (
                            "≥2 distinct run ids that exhibit this pattern."
                        ),
                    },
                    "stat_basis": {
                        "type": "string",
                        "description": (
                            "1-line description of the cross-run statistic, with "
                            "concrete numbers (e.g. 'win rate 18% vs 42% baseline')."
                        ),
                    },
                    "anchor_episode": {
                        "type": "string",
                        "description": (
                            "Closest single concrete episode, format '<run_id>:<combat_id>'."
                        ),
                    },
                },
                "required": ["run_ids", "stat_basis", "anchor_episode"],
            },
            "rationale": {
                "type": "string",
                "maxLength": 300,
                "description": (
                    "≤300 chars: why mistake_discovery cannot catch this from a "
                    "single run's trace. If you cannot answer this, do not propose."
                ),
            },
        },
        "required": [
            "skill_name", "category", "content", "motivation",
            "evidence", "rationale",
        ],
        "additionalProperties": False,
    },
}
```

- [ ] **Step 4: Add validation logic to `_handle_write_skill`**

Edit `src/brain/evolution_engine.py`. In `_handle_write_skill` (around L1372 after Task 1's earlier edits — line will have shifted), add new validation IMMEDIATELY at the function entry, BEFORE the existing `if not skill_name or not content:` check:

```python
        # ── Spec #3 §3.2: cross-run grounding gates ─────────────
        rationale = (tool_input.get("rationale") or "").strip()
        if not rationale:
            return (
                "REJECTED: missing `rationale`. Per Spec #3, every "
                "proposal must explain why mistake_discovery cannot catch "
                "this from a single run's trace."
            )
        if len(rationale) < 30:
            return (
                "REJECTED: `rationale` too thin "
                f"({len(rationale)} chars; minimum 30). Articulate the "
                "cross-run angle concretely."
            )
        if len(rationale) > 300:
            return (
                "REJECTED: `rationale` too long "
                f"({len(rationale)} chars; maximum 300). Be terse."
            )

        evidence = tool_input.get("evidence") or {}
        if not isinstance(evidence, dict):
            return "REJECTED: `evidence` must be an object."
        run_ids = evidence.get("run_ids") or []
        if not isinstance(run_ids, list) or len({str(r) for r in run_ids if r}) < 2:
            return (
                "REJECTED: `evidence.run_ids` must contain ≥2 distinct "
                "run ids. Cross-run signal is by-construction; single-run "
                "patterns belong to mistake_discovery."
            )
        stat_basis = (evidence.get("stat_basis") or "").strip()
        if not stat_basis:
            return "REJECTED: `evidence.stat_basis` is required."

        # Heuristic: stat_basis must contain a digit AND at least one
        # comparator phrase. Cross-run patterns have measured baselines.
        _has_digit = any(ch.isdigit() for ch in stat_basis)
        _comparator_words = ("rate", "%", "vs", "baseline", "average", "median")
        _has_comparator = any(w in stat_basis.lower() for w in _comparator_words)
        if not (_has_digit and _has_comparator):
            return (
                "REJECTED: `evidence.stat_basis` must reference numeric "
                "cross-run data (digits + a comparator like 'rate', '%', "
                "'vs', 'baseline'). Use get_performance_stats first."
            )

        anchor_episode = (evidence.get("anchor_episode") or "").strip()
        if not anchor_episode:
            return "REJECTED: `evidence.anchor_episode` is required."

        # Surviving the gates → continue to existing validation chain.
```

After this insertion, the existing `skill_name = tool_input.get("skill_name", "").strip()` and the rest of the function body run as today.

- [ ] **Step 5: Update `EVOLUTION_SYSTEM_PROMPT` to instruct on new schema**

Edit `src/brain/evolution_engine.py:130` (EVOLUTION_SYSTEM_PROMPT). Find the bullet about skills (around L140-142):

```
- Create a skill (write_skill) when you need STRATEGIC KNOWLEDGE (when to rest, \
boss patterns, deck building heuristics, etc.)
```

Replace with:

```
- Create a skill (write_skill) when you need STRATEGIC KNOWLEDGE (when to rest, \
boss patterns, deck building heuristics, etc.). Per Spec #3, every skill MUST \
include `evidence` (run_ids ≥2 distinct, stat_basis with numeric cross-run data, \
anchor_episode in '<run_id>:<combat_id>' format) AND `rationale` (≤300 chars: \
why mistake_discovery couldn't catch this from a single trace). Use \
get_performance_stats BEFORE proposing to ensure the cross-run pattern is \
real and measurable.
```

- [ ] **Step 6: Run tests**

```
pytest tests/test_evolution_engine.py -k "write_skill" -v
```
Expected: 6 PASS (5 new + the updated existing).

```
pytest tests/test_evolution_engine.py -v 2>&1 | tail -5
pytest tests/ -q --ignore=tests/regression
```
Expected: no NEW failures elsewhere.

- [ ] **Step 7: Commit**

```
git add src/brain/write_tools.py src/brain/evolution_engine.py tests/test_evolution_engine.py
git commit -m "feat(evolution): rewrite write_skill schema with cross-run evidence + rationale"
```

---

## Task 7: Final Verification

**Files:** none modified.

- [ ] **Step 1: Full test suite**

```
pytest tests/ -q --ignore=tests/regression
```
Expected: same baseline as before this plan — no NEW failures introduced by the 6 implementation tasks.

- [ ] **Step 2: Confirm tool surface**

```
python -c "from src.brain.write_tools import MUTATING_WRITE_TOOL_NAMES; print(sorted(MUTATING_WRITE_TOOL_NAMES))"
```
Expected: `['author_tool', 'write_skill']`.

- [ ] **Step 3: Confirm round budget default**

```
python -c "import config; print(config.EVOLUTION_MAX_ROUNDS)"
```
Expected: `3` (assuming `STS2_EVOLUTION_MAX_ROUNDS` env var is unset).

- [ ] **Step 4: Confirm system prompt is invariant**

```
python -c "from src.brain.evolution_engine import EvolutionEngine as E; print(E._phase_system_prompt(True) == E._phase_system_prompt(False))"
```
Expected: `True`.

- [ ] **Step 5: Confirm `combat_trace_text` plumbing**

```
python -c "import inspect; from src.brain.evolution_engine import EvolutionEngine; print('combat_trace_text' in inspect.signature(EvolutionEngine.run_evolution).parameters)"
```
Expected: `True`.

```
grep -n "combat_trace_text" src/agent/loop.py
```
Expected: at least 1 match (the kwarg passed to `engine.run_evolution`).

- [ ] **Step 6: Confirm deletions are clean**

```
grep -rn "_handle_update_guide\|_handle_update_card_note\|UPDATE_GUIDE\|UPDATE_CARD_NOTE\|_render_combat_guides\|_render_deck_guides\|_render_card_notes" src/
```
Expected: 0 matches.

```
grep -rn "update_guide\|update_card_note" src/brain/
```
Expected: 0 matches in production code (test references are OK if they were intentionally retained as comments).

- [ ] **Step 7: Sanity import check**

```
python -c "from src.brain.evolution_engine import EvolutionEngine, build_evolution_context; print('imports OK')"
```
Expected: `imports OK`.

- [ ] **Step 8: Git status clean**

```
git status
```
Expected: clean working tree (only untracked / .log files unrelated to this plan).

- [ ] **Step 9: Commit log review**

```
git log --oneline 1a7bd04..HEAD
```
Expected: 6 commits matching Tasks 1–6 (no commit for Task 7 — it is verification only).

---

## Spec Coverage Self-Check

| Spec section | Task(s) |
|---|---|
| §2 Scope: delete `update_card_note` and `update_guide` | Task 1 |
| §2 Scope: rewrite `write_skill` schema with evidence/rationale | Task 6 |
| §2 Scope: rewrite system prompt to static cacheable shape | Task 4 |
| §2 Scope: wire shared `combat_trace_text` cache | Task 5 |
| §2 Scope: cut context_builder sections | Task 2 |
| §2 Scope: round budget 5/6 → 3 | Task 3 |
| §3.1 Tool surface (4 schemas after) | Tasks 1, 6 |
| §3.2 New `write_skill` schema (evidence + rationale) | Task 6 |
| §3.3 Cacheable system prompt (invariant across phases) | Task 4 |
| §3.4 Shared trace cache (multi-block first user message) | Task 5 |
| §3.5 Section pruning | Task 2 |
| §3.6 Round budget | Task 3 |
| §3.7 Files affected | Tasks 1–6 |
| §3.8 Migration of in-flight data | Implicit (no schema change to existing data) |
| §4 Config (no new env vars) | covered by absence |
| §5 Caching | Tasks 4, 5 |
| §6 Error handling (per-tool fail-closed) | Task 6 (validation logic) |
| §7 Risks | covered by tests + comments |
| §8 Testing strategy | Tasks 1–6 (each adds tests) |
| §9 Non-goals | covered by absence (RECALL_ENCOUNTER_SCHEMA, AUTHOR_TOOL, write_gate, etc. untouched) |
