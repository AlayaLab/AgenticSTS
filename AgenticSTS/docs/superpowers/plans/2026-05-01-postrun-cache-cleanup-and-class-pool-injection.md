# Postrun Cache Cleanup + Class-Pool Injection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the no-op postrun `user_cached_prefix` cache hack, then inject per-character class pool reference (~1.7K tokens) into Turn 1 / Turn 2 system prompts and add a third Turn 2 output channel ("bucket B") for up to 3 non-deck card notes per run.

**Architecture:** Two surface areas. (1) Cache cleanup: delete `user_cached_prefix` parameter and branch from `llm_caller.call_raw`, inline `combat_trace_text` directly into the prompt body of `card_build_extractor.analyze_build_with_llm` and `card_note_updater.update_card_notes_from_traces`. (2) Pool injection: new module `src/knowledge/class_pool_injector.py` reads `data/knowledge/upstream/cards.json`, filters by character color, renders a static pipe-delimited table appended to the system prompt of both turns. Bucket B introduces a new `non_deck_updates` JSON channel to Turn 2 with `evidence_type: "skipped" | "combo_inferred"` per entry, validated against a new `extract_skipped_cards` helper that pulls offered-but-not-picked card names from `logs/run_*.jsonl`.

**Tech Stack:** Python 3.14, pytest, existing project conventions (frozen dataclasses, pipe-delimited prompt tables, BBCode stripping via `_strip_bbcode`).

**Spec:** [docs/superpowers/specs/2026-05-01-postrun-cache-cleanup-and-class-pool-injection-design.md](../specs/2026-05-01-postrun-cache-cleanup-and-class-pool-injection-design.md)

---

## File Map

**Create:**
- `src/knowledge/class_pool_injector.py` — pool rendering + canonical-name set
- `tests/test_class_pool_injector.py` — pool tests (uses real cards.json)
- `tests/test_extract_skipped_cards.py` — JSONL extraction tests
- `tests/test_parse_non_deck_updates.py` — bucket B parser tests

**Modify:**
- `src/brain/llm_caller.py` — remove `user_cached_prefix` parameter, branch, telemetry split
- `src/memory/card_build_extractor.py` — inline trace, inject pool into system
- `src/memory/card_note_updater.py` — inline trace, inject pool, add bucket B (parser, system prompt, user prompt, apply path, Turn2Result fields)
- `src/memory/combat_trace_renderer.py` — add `extract_skipped_cards`
- `src/agent/loop.py` — wire `extract_skipped_cards`, add `_pending_skipped_cards`, pass to Turn 2
- `tests/test_card_build_extractor_json.py` — rewrite the two `user_cached_prefix`-asserting tests

**Delete:**
- `tests/test_llm_caller_cache.py`

---

## Task 1: Class pool injector module

**Files:**
- Create: `src/knowledge/class_pool_injector.py`
- Create: `tests/test_class_pool_injector.py`

- [ ] **Step 1.1: Write failing tests**

Create `tests/test_class_pool_injector.py`:

```python
"""Tests for class_pool_injector — uses real upstream cards.json."""
from __future__ import annotations

from src.knowledge.class_pool_injector import (
    class_pool_card_names,
    render_class_pool_section,
)


def test_render_class_pool_section_silent_has_88_lines():
    section = render_class_pool_section("Silent")
    body_lines = [l for l in section.splitlines() if l.startswith("- ")]
    # Format: "- Name | Cost | Type | Rarity | Target | Description"
    assert len(body_lines) == 88
    assert "## Class Pool Reference (Silent — 88 cards)" in section


def test_render_class_pool_section_has_hedge_line():
    section = render_class_pool_section("Silent")
    assert "FULL static class pool" in section
    assert "combo-space awareness only" in section


def test_render_class_pool_section_strips_bbcode():
    section = render_class_pool_section("Silent")
    # No raw BBCode brackets in the rendered text
    assert "[gold]" not in section
    assert "[/gold]" not in section
    assert "[img]" not in section


def test_render_class_pool_section_unknown_character_returns_empty():
    assert render_class_pool_section("banana") == ""
    assert render_class_pool_section("") == ""


def test_render_class_pool_section_excludes_colorless():
    section = render_class_pool_section("Silent")
    # Bandage Up is a colorless card; it must not leak into the silent pool
    assert "Bandage Up" not in section


def test_render_class_pool_section_normalizes_character_alias():
    # "the silent" canonicalizes to silent
    a = render_class_pool_section("Silent")
    b = render_class_pool_section("the silent")
    assert a == b


def test_class_pool_card_names_returns_lowercase_set():
    names = class_pool_card_names("Silent")
    assert isinstance(names, frozenset)
    assert len(names) == 88
    # All lowercase
    assert all(n == n.lower() for n in names)
    assert "backstab" in names
    assert "abrasive" in names


def test_class_pool_card_names_unknown_returns_empty():
    assert class_pool_card_names("banana") == frozenset()


def test_class_pool_section_caches_per_character(monkeypatch):
    """Second call must not re-read the JSON file."""
    import src.knowledge.class_pool_injector as cpi
    cpi._SECTION_CACHE.clear()
    cpi._POOL_CACHE.clear()

    read_count = {"n": 0}
    real_loader = cpi._load_cards_json

    def counting_loader():
        read_count["n"] += 1
        return real_loader()

    monkeypatch.setattr(cpi, "_load_cards_json", counting_loader)
    cpi.render_class_pool_section("Silent")
    cpi.render_class_pool_section("Silent")
    cpi.class_pool_card_names("Silent")
    assert read_count["n"] == 1
```

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
pytest tests/test_class_pool_injector.py -v
```
Expected: All FAIL with `ModuleNotFoundError: No module named 'src.knowledge.class_pool_injector'`.

- [ ] **Step 1.3: Implement the module**

Create `src/knowledge/class_pool_injector.py`:

```python
"""Class pool injector — render the full class card pool as a system-prompt
reference section for postrun Turn 1 / Turn 2.

Reads `data/knowledge/upstream/cards.json` once per process per character;
filters by `color` field. Output is a pipe-delimited table prepended with a
hedge line warning the LLM not to claim cards were in the run.

Gameplay-time prompts (reward, shop, card_select) do NOT use this module.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from src.memory.models_v2 import normalize_character

logger = logging.getLogger(__name__)

_CARDS_JSON = Path(__file__).parent.parent.parent / "data" / "knowledge" / "upstream" / "cards.json"

_SECTION_CACHE: dict[str, str] = {}
_POOL_CACHE: dict[str, frozenset[str]] = {}

# Map our normalized character names to the cards.json `color` field.
# normalize_character("Silent") -> "the silent"; cards.json uses "silent".
_CHARACTER_TO_COLOR: dict[str, str] = {
    "the silent": "silent",
    "the regent":  "regent",
    "the defect":  "defect",
    "ironclad":    "ironclad",
    "necrobinder": "necrobinder",
}

_DISPLAY_NAME: dict[str, str] = {
    "the silent": "Silent",
    "the regent": "Regent",
    "the defect": "Defect",
    "ironclad":   "Ironclad",
    "necrobinder": "Necrobinder",
}


def _strip_bbcode(text: str) -> str:
    """Remove BBCode tags. Keep inner text."""
    text = re.sub(r"\[/?[a-zA-Z_]+(?:=[^\]]*)?\]", "", text)
    text = re.sub(r"\[img\][^\[]*\[/img\]", "", text)
    return text


def _load_cards_json() -> list[dict]:
    """Load and return the upstream cards.json payload (list of dicts)."""
    try:
        with _CARDS_JSON.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        logger.warning("class_pool_injector: failed to read %s", _CARDS_JSON, exc_info=True)
        return []


def _filter_class_cards(character: str) -> list[dict]:
    char_norm = normalize_character(character)
    color = _CHARACTER_TO_COLOR.get(char_norm)
    if not color:
        return []
    cards = _load_cards_json()
    return [c for c in cards if c.get("color") == color]


def _format_card_line(card: dict) -> str:
    name = str(card.get("name") or "").strip()
    cost = card.get("cost")
    cost_str = "X" if card.get("is_x_cost") else (str(cost) if cost is not None else "?")
    typ = str(card.get("type") or "").strip()
    rarity = str(card.get("rarity") or "").strip()
    target = str(card.get("target") or "").strip()
    desc = _strip_bbcode(str(card.get("description") or "")).replace("\n", " ").strip()
    desc = re.sub(r"\s+", " ", desc)
    return f"- {name} | {cost_str} | {typ} | {rarity} | {target} | {desc}"


def render_class_pool_section(character: str) -> str:
    """Return a system-prompt section listing every card in the character's
    class pool. Returns empty string when the character is unknown.

    Format (one body line per card, pipe-delimited):
        - Name | Cost | Type | Rarity | Target | Description

    BBCode is stripped from descriptions; newlines flattened to spaces.
    Section is cached per-character for the lifetime of the process.
    """
    char_norm = normalize_character(character)
    if char_norm in _SECTION_CACHE:
        return _SECTION_CACHE[char_norm]

    cards = _filter_class_cards(character)
    if not cards:
        _SECTION_CACHE[char_norm] = ""
        return ""

    display = _DISPLAY_NAME.get(char_norm, char_norm.title())
    header = f"## Class Pool Reference ({display} — {len(cards)} cards)"
    hedge = (
        "This is the FULL static class pool, not what the run actually saw. "
        "Use as combo-space awareness only. Never claim a card was in this "
        "run unless the trace evidence shows it."
    )
    schema = "Name | Cost | Type | Rarity | Target | Description"
    body = "\n".join(_format_card_line(c) for c in cards)

    section = f"{header}\n\n{hedge}\n\n{schema}\n{body}"
    _SECTION_CACHE[char_norm] = section
    return section


def class_pool_card_names(character: str) -> frozenset[str]:
    """Return a lowercased frozenset of card names in the character's pool.

    Used by Turn 2 bucket-B validation rule 1 (card must be in class pool)
    and rule 2 (card must NOT be in deck — caller intersects manually).
    """
    char_norm = normalize_character(character)
    if char_norm in _POOL_CACHE:
        return _POOL_CACHE[char_norm]
    cards = _filter_class_cards(character)
    names = frozenset(str(c.get("name") or "").strip().lower() for c in cards if c.get("name"))
    _POOL_CACHE[char_norm] = names
    return names
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
pytest tests/test_class_pool_injector.py -v
```
Expected: 9 PASSED.

- [ ] **Step 1.5: Commit**

```bash
git add src/knowledge/class_pool_injector.py tests/test_class_pool_injector.py
git commit -m "feat(knowledge): class pool injector for postrun Turn 1/2"
```

---

## Task 2: Delete the cache hack

**Files:**
- Delete: `tests/test_llm_caller_cache.py`
- Modify: `src/brain/llm_caller.py:48-104,319-325`

- [ ] **Step 2.1: Delete the dedicated cache test file**

```bash
git rm tests/test_llm_caller_cache.py
```

- [ ] **Step 2.2: Modify `src/brain/llm_caller.py` — remove the `user_cached_prefix` parameter and branch**

In `call_raw` signature (line 59), remove `user_cached_prefix: str = "",`:

```python
async def call_raw(
    system: str,
    prompt: str,
    think: bool = False,
    model: str | None = None,
    effort: str = "",
    provider: str | None = None,
    openai_relay_profile: str = "postrun",
    session_logger: object | None = None,
    call_type: str = "",
    call_class: str = "",
    max_tokens: int | None = None,
) -> tuple[str, float, int]:
```

Remove the docstring block describing `user_cached_prefix` (lines 75-80) entirely.

Replace the entire `if user_cached_prefix: ... else: ...` block (lines 88-106) with:

```python
    messages = [{"role": "user", "content": prompt}]
```

Replace the telemetry split (lines 319-327):

```python
    # Post-run telemetry (use explicit param or module-level logger).
    if _sl is not None and call_type and hasattr(_sl, "log_postrun_llm_call"):
```

(i.e. delete the `logged_prompt` reassignment block; pass `prompt` directly to `log_postrun_llm_call`.)

Find and update the call site lower down:

```python
            _sl.log_postrun_llm_call(
                ...
                prompt=prompt,
                ...
            )
```

- [ ] **Step 2.3: Run the test suite to confirm nothing else broke**

```bash
pytest tests/test_llm_caller_cache.py -v 2>&1 || true
pytest tests/ -v -k "llm_caller or call_raw" --no-header 2>&1 | tail -20
```
Expected: cache test file gone (file-not-found is fine); other tests pass.

- [ ] **Step 2.4: Commit**

```bash
git add src/brain/llm_caller.py tests/test_llm_caller_cache.py
git commit -m "refactor(llm): drop no-op user_cached_prefix branch from call_raw"
```

---

## Task 3: Inline combat trace into Turn 1 (build analysis)

**Files:**
- Modify: `src/memory/card_build_extractor.py:612-690`
- Modify: `tests/test_card_build_extractor_json.py:99-164`

- [ ] **Step 3.1: Rewrite the two tests that asserted the old cache contract**

In `tests/test_card_build_extractor_json.py`, replace the two functions `test_analyze_build_with_llm_accepts_combat_trace_text` and `test_analyze_build_with_llm_no_trace_preserves_old_call_shape` with:

```python
def test_analyze_build_with_llm_inlines_combat_trace_into_prompt(monkeypatch):
    """When combat_trace_text is provided, it must appear in the prompt
    body sent to call_raw (single-block user content; no cache hack)."""
    from src.memory import card_build_extractor as cbe

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return ('{"decision":"reject_no_clear_build","target_build_id":"",'
                '"build_summary":"x","primary_plan":"y","damage_engine":"z",'
                '"defense_engine":"z","cycle_engine":"z","energy_engine":"z",'
                '"build_tags":["defeat"],"card_roles":[],"weak_points":"w",'
                '"confidence":0.3,"key_cards":[],"coherence_score":0.5,'
                '"coherence_analysis":"x"}', 100.0, 100)

    monkeypatch.setattr(cbe, "call_raw", _fake_call_raw, raising=False)
    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    evidence = {
        "character": "silent",
        "victory": False,
        "final_floor": 8,
        "fitness": 50.0,
        "deck_size": 20,
        "combats_won": 1,
        "combats_total": 2,
        "final_deck": [],
    }
    asyncio.run(cbe.analyze_build_with_llm(
        evidence, combat_trace_text="FAKE TRACE BLOCK",
    ))

    assert "FAKE TRACE BLOCK" in captured["prompt"]
    assert "user_cached_prefix" not in captured["kwargs"]


def test_analyze_build_with_llm_no_trace_omits_trace_block(monkeypatch):
    """When combat_trace_text is empty, the prompt must not contain the
    instruction note about the trace, and call_raw must not receive
    user_cached_prefix."""
    from src.memory import card_build_extractor as cbe

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return ('{"decision":"reject_no_clear_build","target_build_id":"",'
                '"build_summary":"x","primary_plan":"y","damage_engine":"z",'
                '"defense_engine":"z","cycle_engine":"z","energy_engine":"z",'
                '"build_tags":["defeat"],"card_roles":[],"weak_points":"w",'
                '"confidence":0.3,"key_cards":[],"coherence_score":0.5,'
                '"coherence_analysis":"x"}', 100.0, 100)

    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    evidence = {
        "character": "silent",
        "victory": False,
        "final_floor": 8,
        "fitness": 50.0,
        "deck_size": 20,
        "combats_won": 1,
        "combats_total": 2,
        "final_deck": [],
    }
    asyncio.run(cbe.analyze_build_with_llm(evidence))

    assert "Additional context" not in captured["prompt"]
    assert "user_cached_prefix" not in captured["kwargs"]
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
pytest tests/test_card_build_extractor_json.py::test_analyze_build_with_llm_inlines_combat_trace_into_prompt -v
pytest tests/test_card_build_extractor_json.py::test_analyze_build_with_llm_no_trace_omits_trace_block -v
```
Expected: First test FAILS (trace text not in prompt). Second may PASS or fail depending on prior state — both must fail or pass for the right reason after step 3.3.

- [ ] **Step 3.3: Modify `src/memory/card_build_extractor.py` `analyze_build_with_llm`**

In `analyze_build_with_llm` (line 612), replace the trace-handling block (lines 640-659):

```python
    # Inline the trace at the top of the user message when provided.
    # No cache_control on this block — the previous user_cached_prefix
    # path was a no-op (see 2026-05-01 cache cleanup spec).
    if combat_trace_text:
        instruction_note = (
            "Additional context: a full round-by-round trace of the 1-2 most recent combats "
            "appears at the top of this user message (before the evidence block). Use it as ground "
            "truth for how the deck actually played when choosing build_summary / damage_engine / "
            "weak_points.\n\n"
        )
        prompt = combat_trace_text + "\n\n" + instruction_note + prompt

    raw_text = ""
    for attempt in range(2):
        try:
            raw_text, latency_ms, tokens = await call_raw(
                _BUILD_ANALYSIS_SYSTEM,
                prompt,
                think=False,
                call_type="build_analysis",
            )
```

- [ ] **Step 3.4: Run all extractor tests to verify pass**

```bash
pytest tests/test_card_build_extractor_json.py -v
```
Expected: all PASSED.

- [ ] **Step 3.5: Commit**

```bash
git add src/memory/card_build_extractor.py tests/test_card_build_extractor_json.py
git commit -m "refactor(memory): inline combat trace into Turn 1 build analysis prompt"
```

---

## Task 4: Inject class pool into Turn 1 system prompt

**Files:**
- Modify: `src/memory/card_build_extractor.py:612-660`
- Modify: `tests/test_card_build_extractor_json.py` (append)

- [ ] **Step 4.1: Write failing test**

Append to `tests/test_card_build_extractor_json.py`:

```python
def test_analyze_build_with_llm_appends_class_pool_to_system(monkeypatch):
    """Turn 1's system prompt must include the class pool reference for
    the run's character."""
    from src.memory import card_build_extractor as cbe

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        return ('{"decision":"reject_no_clear_build","target_build_id":"",'
                '"build_summary":"x","primary_plan":"y","damage_engine":"z",'
                '"defense_engine":"z","cycle_engine":"z","energy_engine":"z",'
                '"build_tags":["defeat"],"card_roles":[],"weak_points":"w",'
                '"confidence":0.3,"key_cards":[],"coherence_score":0.5,'
                '"coherence_analysis":"x"}', 100.0, 100)

    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    evidence = {
        "character": "silent",
        "victory": False,
        "final_floor": 8,
        "fitness": 50.0,
        "deck_size": 20,
        "combats_won": 1,
        "combats_total": 2,
        "final_deck": [],
    }
    asyncio.run(cbe.analyze_build_with_llm(evidence))

    assert "## Class Pool Reference (Silent" in captured["system"]
    assert "Backstab" in captured["system"]
```

- [ ] **Step 4.2: Run test to verify it fails**

```bash
pytest tests/test_card_build_extractor_json.py::test_analyze_build_with_llm_appends_class_pool_to_system -v
```
Expected: FAIL (system has no pool section).

- [ ] **Step 4.3: Modify `analyze_build_with_llm` to append the pool**

Add import near the other imports inside `analyze_build_with_llm` (or at module top with the other lazy imports):

```python
    from src.brain.llm_caller import call_raw
    from src.knowledge.class_pool_injector import render_class_pool_section
```

Then immediately before the `for attempt in range(2)` loop, build the system string:

```python
    pool_section = render_class_pool_section(character)
    system_prompt = (
        _BUILD_ANALYSIS_SYSTEM + "\n\n" + pool_section
        if pool_section else _BUILD_ANALYSIS_SYSTEM
    )
```

Pass `system_prompt` to `call_raw` instead of the bare constant:

```python
            raw_text, latency_ms, tokens = await call_raw(
                system_prompt,
                prompt,
                think=False,
                call_type="build_analysis",
            )
```

- [ ] **Step 4.4: Run test to verify it passes**

```bash
pytest tests/test_card_build_extractor_json.py -v
```
Expected: all PASSED.

- [ ] **Step 4.5: Commit**

```bash
git add src/memory/card_build_extractor.py tests/test_card_build_extractor_json.py
git commit -m "feat(memory): inject class pool into Turn 1 build_analysis system prompt"
```

---

## Task 5: Inline combat trace into Turn 2 (card_note_updater)

**Files:**
- Modify: `src/memory/card_note_updater.py:351-422`
- Modify: `tests/test_card_note_updater.py` (append)

- [ ] **Step 5.1: Write failing test**

Append to `tests/test_card_note_updater.py`:

```python
def test_update_card_notes_inlines_trace_into_prompt(monkeypatch, tmp_path):
    """When combat_trace_text is provided, it must appear in the prompt
    body sent to call_raw."""
    import asyncio
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return ('{"updates": []}', 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)

    store = CardMemoryStore(path=tmp_path / "card_memory.json")
    asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="UNIQUE_TRACE_MARKER_42",
        candidate_cards=["Backstab"],
        run_id="test-run",
        dry_run=True,
    ))

    assert "UNIQUE_TRACE_MARKER_42" in captured["prompt"]
    assert "user_cached_prefix" not in captured["kwargs"]
```

- [ ] **Step 5.2: Run test to verify it fails**

```bash
pytest tests/test_card_note_updater.py::test_update_card_notes_inlines_trace_into_prompt -v
```
Expected: FAIL (trace marker missing from prompt).

- [ ] **Step 5.3: Modify `update_card_notes_from_traces` to inline trace and drop the cache kwarg**

In `update_card_notes_from_traces` (line 351), find the prompt assembly (lines 384-396):

```python
    char_norm = normalize_character(character)
    candidate_table = _render_candidate_table(store, char_norm, candidate_cards)
    prompt = _UPDATER_PROMPT_TEMPLATE.format(candidate_table=candidate_table)

    if is_act3_boss_victory:
        prompt = (
            prompt
            + "\n\n"
            + _render_act3_victory_section(
                list(final_deck or []), list(final_relics or []),
            )
        )

    # Inline the trace at the top — single-block user content.
    prompt = combat_trace_text + "\n\n" + prompt
```

Then update the `call_raw` invocation (lines 410-419) to drop `user_cached_prefix`:

```python
        raw_text, latency_ms, tokens = await call_raw(
            _NOTE_UPDATER_SYSTEM,
            prompt,
            think=True,
            effort=_config.LLM_THINK_EFFORT_ANALYSIS or "high",
            call_type="card_note_update",
            max_tokens=24000,
        )
```

Also update the comment block (lines 397-409) that explains the `think=False → think=True` change to remove the now-stale reference to `user_cached_prefix`.

- [ ] **Step 5.4: Run test to verify it passes**

```bash
pytest tests/test_card_note_updater.py -v
```
Expected: all PASSED.

- [ ] **Step 5.5: Commit**

```bash
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "refactor(memory): inline combat trace into Turn 2 card_note prompt"
```

---

## Task 6: Inject class pool into Turn 2 system prompt

**Files:**
- Modify: `src/memory/card_note_updater.py`
- Modify: `tests/test_card_note_updater.py` (append)

- [ ] **Step 6.1: Write failing test**

Append to `tests/test_card_note_updater.py`:

```python
def test_update_card_notes_appends_class_pool_to_system(monkeypatch, tmp_path):
    import asyncio
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        return ('{"updates": []}', 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)

    store = CardMemoryStore(path=tmp_path / "card_memory.json")
    asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="trace",
        candidate_cards=["Backstab"],
        run_id="test-run",
        dry_run=True,
    ))

    assert "## Class Pool Reference (Silent" in captured["system"]
```

- [ ] **Step 6.2: Run test to verify it fails**

```bash
pytest tests/test_card_note_updater.py::test_update_card_notes_appends_class_pool_to_system -v
```
Expected: FAIL.

- [ ] **Step 6.3: Modify `update_card_notes_from_traces` to append pool to system**

Right after `char_norm = normalize_character(character)`, build the system prompt:

```python
    from src.knowledge.class_pool_injector import render_class_pool_section
    pool_section = render_class_pool_section(char_norm)
    system_prompt = (
        _NOTE_UPDATER_SYSTEM + "\n\n" + pool_section
        if pool_section else _NOTE_UPDATER_SYSTEM
    )
```

Pass `system_prompt` to `call_raw` instead of the bare constant:

```python
        raw_text, latency_ms, tokens = await call_raw(
            system_prompt,
            prompt,
            think=True,
            effort=_config.LLM_THINK_EFFORT_ANALYSIS or "high",
            call_type="card_note_update",
            max_tokens=24000,
        )
```

- [ ] **Step 6.4: Run tests to verify they pass**

```bash
pytest tests/test_card_note_updater.py -v
```
Expected: all PASSED.

- [ ] **Step 6.5: Commit**

```bash
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(memory): inject class pool into Turn 2 card_note system prompt"
```

---

## Task 7: extract_skipped_cards from JSONL

**Files:**
- Modify: `src/memory/combat_trace_renderer.py`
- Create: `tests/test_extract_skipped_cards.py`

- [ ] **Step 7.1: Write failing tests**

Create `tests/test_extract_skipped_cards.py`:

```python
"""Tests for combat_trace_renderer.extract_skipped_cards."""
from __future__ import annotations

from src.memory.combat_trace_renderer import extract_skipped_cards


def test_extract_skipped_cards_card_reward_event():
    """A card_reward decision with 3 options and 1 picked → 2 skipped."""
    events = [{
        "type": "decision",
        "decision_type": "card_reward",
        "decision": {
            "options": ["Catalyst", "Footwork", "Eviscerate"],
            "picked_alternative": 2,  # index 2 = Eviscerate picked
        },
    }]
    skipped = extract_skipped_cards(events)
    assert set(skipped) == {"Catalyst", "Footwork"}


def test_extract_skipped_cards_card_reward_skip_alternative():
    """When the run skipped the reward entirely, all cards are skipped."""
    events = [{
        "type": "decision",
        "decision_type": "card_reward",
        "decision": {
            "options": ["Catalyst", "Footwork", "Eviscerate"],
            "picked_alternative": -1,  # skip
        },
    }]
    skipped = extract_skipped_cards(events)
    assert set(skipped) == {"Catalyst", "Footwork", "Eviscerate"}


def test_extract_skipped_cards_shop_event():
    events = [{
        "type": "decision",
        "decision_type": "shop",
        "decision": {
            "card_options": ["Adrenaline", "Calculated Gamble"],
            "purchased_cards": ["Adrenaline"],
        },
    }]
    skipped = extract_skipped_cards(events)
    assert skipped == ["Calculated Gamble"]


def test_extract_skipped_cards_dedupes_across_events():
    events = [
        {"type": "decision", "decision_type": "card_reward",
         "decision": {"options": ["Catalyst", "X"], "picked_alternative": 1}},
        {"type": "decision", "decision_type": "card_reward",
         "decision": {"options": ["Catalyst", "Y"], "picked_alternative": 1}},
    ]
    skipped = extract_skipped_cards(events)
    # Catalyst skipped twice — appears once
    assert skipped.count("Catalyst") == 1


def test_extract_skipped_cards_preserves_first_seen_order():
    events = [
        {"type": "decision", "decision_type": "card_reward",
         "decision": {"options": ["A", "B", "C"], "picked_alternative": 2}},
        {"type": "decision", "decision_type": "card_reward",
         "decision": {"options": ["D", "E"], "picked_alternative": 1}},
    ]
    skipped = extract_skipped_cards(events)
    assert skipped == ["A", "B", "D"]


def test_extract_skipped_cards_returns_empty_on_malformed_event():
    events = [
        {"type": "decision", "decision_type": "card_reward"},  # missing decision
        {"type": "decision", "decision_type": "card_reward",
         "decision": {"options": "not a list", "picked_alternative": 0}},
        {"type": "decision", "decision_type": "card_reward",
         "decision": {"options": [], "picked_alternative": 0}},
    ]
    skipped = extract_skipped_cards(events)
    assert skipped == []


def test_extract_skipped_cards_ignores_non_card_decisions():
    events = [
        {"type": "decision", "decision_type": "map", "decision": {"options": ["a", "b"]}},
        {"type": "decision", "decision_type": "rest", "decision": {"options": ["x", "y"]}},
    ]
    skipped = extract_skipped_cards(events)
    assert skipped == []


def test_extract_skipped_cards_empty_input():
    assert extract_skipped_cards([]) == []
```

- [ ] **Step 7.2: Run tests to verify they fail**

```bash
pytest tests/test_extract_skipped_cards.py -v
```
Expected: All FAIL with ImportError.

- [ ] **Step 7.3: Implement `extract_skipped_cards`**

In `src/memory/combat_trace_renderer.py`, append:

```python
def extract_skipped_cards(run_log_events: list[dict]) -> list[str]:
    """Return cards offered at card_reward / shop but not picked in this run.

    Reads the run JSONL log events directly (same source the trace renderer
    consumes). Returns deduplicated list, order preserved by first
    appearance. Returns ``[]`` on any parse failure — degraded behavior is
    fail-safe for bucket B (validation will reject all "skipped" claims).

    Recognized event shapes:
      card_reward decision:
        decision = {"options": [str,...], "picked_alternative": int}
        picked_alternative == -1 means the run skipped the reward; all
        options are then "skipped".
      shop decision:
        decision = {"card_options": [str,...], "purchased_cards": [str,...]}
    """
    seen: dict[str, None] = {}
    for event in run_log_events or []:
        if not isinstance(event, dict):
            continue
        if event.get("type") != "decision":
            continue
        dtype = event.get("decision_type")
        decision = event.get("decision")
        if not isinstance(decision, dict):
            continue
        if dtype == "card_reward":
            options = decision.get("options")
            if not isinstance(options, list) or not options:
                continue
            picked_idx = decision.get("picked_alternative")
            try:
                picked_idx = int(picked_idx)
            except (TypeError, ValueError):
                continue
            for i, name in enumerate(options):
                if not isinstance(name, str) or not name.strip():
                    continue
                if i == picked_idx:
                    continue
                seen.setdefault(name.strip(), None)
        elif dtype == "shop":
            card_options = decision.get("card_options") or []
            purchased = set(decision.get("purchased_cards") or [])
            if not isinstance(card_options, list):
                continue
            for name in card_options:
                if not isinstance(name, str) or not name.strip():
                    continue
                if name in purchased:
                    continue
                seen.setdefault(name.strip(), None)
    return list(seen.keys())
```

- [ ] **Step 7.4: Run tests to verify they pass**

```bash
pytest tests/test_extract_skipped_cards.py -v
```
Expected: 8 PASSED.

- [ ] **Step 7.5: Commit**

```bash
git add src/memory/combat_trace_renderer.py tests/test_extract_skipped_cards.py
git commit -m "feat(memory): extract_skipped_cards reads card_reward/shop offers from JSONL"
```

---

## Task 8: Bucket B parsing function

**Files:**
- Modify: `src/memory/card_note_updater.py` (append `parse_non_deck_updates`)
- Create: `tests/test_parse_non_deck_updates.py`

- [ ] **Step 8.1: Write failing tests**

Create `tests/test_parse_non_deck_updates.py`:

```python
"""Tests for bucket B parser (card_note_updater.parse_non_deck_updates)."""
from __future__ import annotations

import json

from src.memory.card_note_updater import parse_non_deck_updates


def _make_payload(entries: list[dict]) -> str:
    return json.dumps({"updates": [], "non_deck_updates": entries})


def test_parse_non_deck_updates_accepts_valid_skipped_entry():
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "Top poison-build payoff; take whenever offered.",
        "evidence_type": "skipped",
        "reason": "Skipped at card_reward floor 9.",
        "trace_citation": "Combat 3 R1: skipped Catalyst, picked Strike+",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst", "footwork"}),
        final_deck=frozenset({"strike", "defend"}),
        final_relics=frozenset(),
        skipped_cards=frozenset({"Catalyst"}),
    )
    assert dropped == 0
    assert len(proposals) == 1
    assert proposals[0]["card_name"] == "catalyst"
    assert proposals[0]["reason"].startswith("[skipped] ")


def test_parse_non_deck_updates_accepts_valid_combo_entry():
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "Doubles existing poison; pick when Noxious Fumes is in deck.",
        "evidence_type": "combo_inferred",
        "reason": "Doubles Noxious Fumes stacks for one-turn payoff.",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst", "noxious fumes"}),
        final_deck=frozenset({"noxious fumes"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert dropped == 0
    assert len(proposals) == 1
    assert proposals[0]["reason"].startswith("[combo_inferred] ")


def test_parse_non_deck_updates_rejects_card_in_deck():
    """Bucket B rule 2: card must not be in deck."""
    raw = _make_payload([{
        "card_name": "Strike",
        "new_note": "x" * 50,
        "evidence_type": "combo_inferred",
        "reason": "synergy with Strike",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"strike"}),
        final_deck=frozenset({"strike"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_card_outside_pool():
    """Bucket B rule 1: card must be in class pool."""
    raw = _make_payload([{
        "card_name": "Bandage Up",  # colorless, not in silent pool
        "new_note": "x" * 50,
        "evidence_type": "combo_inferred",
        "reason": "synergy with Strike",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"strike"}),
        final_deck=frozenset({"strike"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_skipped_without_membership():
    """Bucket B rule 3: skipped requires skipped_cards membership."""
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "skipped",
        "reason": "skipped at floor 9",
        "trace_citation": "Combat 3: skipped Catalyst",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst"}),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset(),  # empty — Catalyst was not actually skipped
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_skipped_without_citation():
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "skipped",
        "reason": "skipped at floor 9",
        "trace_citation": "",  # required for skipped
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst"}),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset({"Catalyst"}),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_combo_without_deck_token():
    """Bucket B rule 4: combo_inferred reason must mention a deck card or relic."""
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "combo_inferred",
        "reason": "generally good in poison builds",  # no deck card name
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst", "noxious fumes"}),
        final_deck=frozenset({"noxious fumes"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_caps_at_three(monkeypatch):
    entries = [
        {
            "card_name": f"Card{i}",
            "new_note": "x" * 50,
            "evidence_type": "combo_inferred",
            "reason": f"Combo with Strike {i}",
            "trace_citation": "",
        }
        for i in range(5)
    ]
    raw = _make_payload(entries)
    pool = frozenset({f"card{i}" for i in range(5)})
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=pool,
        final_deck=frozenset({"strike"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert len(proposals) == 3
    assert dropped == 2  # 2 over the cap


def test_parse_non_deck_updates_returns_empty_when_field_missing():
    raw = json.dumps({"updates": []})  # no non_deck_updates
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset(),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 0


def test_parse_non_deck_updates_returns_empty_on_malformed_json():
    proposals, dropped = parse_non_deck_updates(
        "not json",
        class_pool=frozenset(),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 0
```

- [ ] **Step 8.2: Run tests to verify they fail**

```bash
pytest tests/test_parse_non_deck_updates.py -v
```
Expected: All FAIL with ImportError.

- [ ] **Step 8.3: Implement `parse_non_deck_updates`**

Append to `src/memory/card_note_updater.py`:

```python
_BUCKET_B_CAP = 3


def parse_non_deck_updates(
    raw_text: str,
    *,
    class_pool: frozenset[str],
    final_deck: frozenset[str],
    final_relics: frozenset[str],
    skipped_cards: frozenset[str],
) -> tuple[list[dict], int]:
    """Parse the bucket B (`non_deck_updates`) channel.

    Returns ``(proposals, dropped_count)``. Each surviving proposal has
    ``reason`` already prefixed with ``[skipped]`` or ``[combo_inferred]``
    so the apply path is identical to bucket A.

    Validation rules:
      1. card_name canonicalized; must be in class_pool.
      2. card_name must NOT be in final_deck.
      3. evidence_type "skipped": card_name must be in skipped_cards
         (case-preserved comparison via lowercased token); trace_citation
         must be non-empty.
      4. evidence_type "combo_inferred": reason must contain at least one
         lowercased token from final_deck ∪ final_relics.
      5. new_note <= 200 chars; reason <= 200 chars.

    Cap: at most _BUCKET_B_CAP entries are returned. Excess entries count
    toward dropped_count.

    Returns ``([], 0)`` on whole-response JSON failure (sentinel — bucket A
    parser handles the same payload and will log its own warning).
    """
    raw = (raw_text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        return [], 0
    if not isinstance(parsed, dict):
        return [], 0

    entries = parsed.get("non_deck_updates")
    if not isinstance(entries, list):
        return [], 0

    skipped_lower = {s.strip().lower() for s in skipped_cards if s}
    deck_relic_tokens = {t.lower() for t in (final_deck | final_relics) if t}

    valid: list[dict] = []
    dropped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            dropped += 1
            continue
        card = _canonical_card_name(str(entry.get("card_name", "")))
        new_note = str(entry.get("new_note", "")).strip()
        evidence_type = str(entry.get("evidence_type", "")).strip().lower()
        reason = str(entry.get("reason", "")).strip()
        citation = str(entry.get("trace_citation", "")).strip()

        # Rule 5: length bounds
        if not new_note or len(new_note) > _MAX_NOTE_CHARS:
            dropped += 1
            continue
        if not reason or len(reason) > _MAX_NOTE_CHARS:
            dropped += 1
            continue

        # Rule 1: in class pool
        if not card or card not in class_pool:
            dropped += 1
            continue

        # Rule 2: NOT in deck
        if card in final_deck:
            dropped += 1
            continue

        # Rule 3 / 4: per-evidence-type checks
        if evidence_type == "skipped":
            if card not in skipped_lower:
                dropped += 1
                continue
            if not citation:
                dropped += 1
                continue
        elif evidence_type == "combo_inferred":
            reason_lower = reason.lower()
            if not any(tok in reason_lower for tok in deck_relic_tokens):
                dropped += 1
                continue
        else:
            dropped += 1
            continue

        valid.append({
            "card_name": card,
            "new_note": new_note,
            "reason": f"[{evidence_type}] {reason}",
            "trace_citation": citation,
        })

    if len(valid) > _BUCKET_B_CAP:
        dropped += len(valid) - _BUCKET_B_CAP
        valid = valid[:_BUCKET_B_CAP]

    return valid, dropped
```

- [ ] **Step 8.4: Run tests to verify they pass**

```bash
pytest tests/test_parse_non_deck_updates.py -v
```
Expected: 10 PASSED.

- [ ] **Step 8.5: Commit**

```bash
git add src/memory/card_note_updater.py tests/test_parse_non_deck_updates.py
git commit -m "feat(memory): bucket B parser for non-deck card notes (Turn 2)"
```

---

## Task 9: Wire bucket B into update_card_notes_from_traces

**Files:**
- Modify: `src/memory/card_note_updater.py` (system prompt, user template, signature, body)
- Modify: `tests/test_card_note_updater.py` (append integration test)

- [ ] **Step 9.1: Write failing integration test**

Append to `tests/test_card_note_updater.py`:

```python
def test_update_card_notes_writes_bucket_b_skipped_entry(monkeypatch, tmp_path):
    """End-to-end: a valid bucket B 'skipped' entry lands in the store
    with reason prefixed [skipped]."""
    import asyncio
    import json
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    payload = {
        "updates": [],
        "non_deck_updates": [{
            "card_name": "Catalyst",
            "new_note": "Top poison payoff; take whenever offered.",
            "evidence_type": "skipped",
            "reason": "Skipped at card_reward floor 9.",
            "trace_citation": "Combat 3 R1: skipped Catalyst",
        }],
    }

    async def _fake_call_raw(system, prompt, **kwargs):
        return (json.dumps(payload), 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)
    # Bypass the gate so writes actually happen
    monkeypatch.setattr("config.POSTRUN_NOTE_UPDATE_ENABLED", True, raising=False)

    store_path = tmp_path / "card_memory.json"
    store = CardMemoryStore(path=store_path)
    result = asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="trace text",
        candidate_cards=["Backstab"],
        run_id="test-run",
        skipped_cards=["Catalyst"],
        final_deck=["Strike", "Defend"],
        final_relics=[],
        dry_run=False,
    ))

    assert result.non_deck_written == 1
    assert result.non_deck_dropped == 0
    written = store.get("the silent", "Catalyst")
    assert written is not None
    assert written.note.startswith("Top poison payoff")
    history = list(written.note_history) if written.note_history else []
    # The most recent entry's reason should carry the [skipped] prefix
    assert any("[skipped]" in (h.reason or "") for h in history)


def test_update_card_notes_drops_bucket_b_when_skipped_cards_empty(monkeypatch, tmp_path):
    """With no skipped_cards passed in, a 'skipped'-type entry must be dropped."""
    import asyncio
    import json
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    payload = {
        "updates": [],
        "non_deck_updates": [{
            "card_name": "Catalyst",
            "new_note": "x" * 50,
            "evidence_type": "skipped",
            "reason": "skipped",
            "trace_citation": "cite",
        }],
    }

    async def _fake_call_raw(system, prompt, **kwargs):
        return (json.dumps(payload), 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)
    monkeypatch.setattr("config.POSTRUN_NOTE_UPDATE_ENABLED", True, raising=False)

    store = CardMemoryStore(path=tmp_path / "card_memory.json")
    result = asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="trace",
        candidate_cards=["Backstab"],
        run_id="test-run",
        skipped_cards=[],  # empty
        final_deck=["Strike"],
        final_relics=[],
        dry_run=False,
    ))

    assert result.non_deck_written == 0
    assert result.non_deck_dropped == 1
```

- [ ] **Step 9.2: Run tests to verify they fail**

```bash
pytest tests/test_card_note_updater.py::test_update_card_notes_writes_bucket_b_skipped_entry tests/test_card_note_updater.py::test_update_card_notes_drops_bucket_b_when_skipped_cards_empty -v
```
Expected: FAIL — `update_card_notes_from_traces` does not yet accept `skipped_cards` / `final_deck` / `final_relics` params for bucket B.

- [ ] **Step 9.3: Extend `Turn2Result`**

In `src/memory/card_note_updater.py`, modify the `Turn2Result` dataclass (line 32) to add two fields:

```python
@dataclass(frozen=True)
class Turn2Result:
    notes_written: int = 0
    notes_kept_unchanged: int = 0
    notes_invalid: int = 0
    core_engine_applied: int = 0
    core_engine_emitted: bool = False
    non_deck_written: int = 0
    non_deck_dropped: int = 0
```

- [ ] **Step 9.4: Extend `_NOTE_UPDATER_SYSTEM` with bucket B instructions**

Append to the `_NOTE_UPDATER_SYSTEM` constant (after the `core_engine` rules block, before the closing `)`):

```python
    "\n\nAdditionally, you MAY emit up to 3 entries in `non_deck_updates` "
    "for cards that are NOT in the run's deck but where the trace or "
    "class-pool context justifies a forward-looking note:\n\n"
    "- evidence_type \"skipped\": the run was offered this card at "
    "card_reward or shop and rejected it. trace_citation MUST quote the "
    "rejection.\n"
    "- evidence_type \"combo_inferred\": this card is in the class pool "
    "and has a concrete combo with a card or relic the run actually used. "
    "`reason` MUST name that deck card or relic.\n\n"
    "Cap: 3 entries total. Be stingy. Prefer \"skipped\" when both apply.\n\n"
    "Each non_deck_updates entry has the same shape as `updates` plus an "
    "`evidence_type` field. Card_name must be a card in the class pool "
    "shown at the top of this system prompt; it must NOT be in the deck."
```

- [ ] **Step 9.5: Extend `_UPDATER_PROMPT_TEMPLATE` with the skipped-cards section placeholder**

Replace the `_UPDATER_PROMPT_TEMPLATE` constant (line 100) with:

```python
_UPDATER_PROMPT_TEMPLATE = """\
## Candidate cards (name | current_note | play_count | sly_play | total_damage | total_block)

{candidate_table}

## Cards offered but not picked this run (eligible for evidence_type="skipped")

{skipped_section}

## Instructions

For each candidate card, decide whether the traces at the top of this user
message justify a new or updated note.

**MANDATORY first-note rule:** For any candidate card whose `current_note`
column shows `(empty)` or `(no memory yet)` AND that appears at least once
in the trace (drawn, played, discarded, exhausted, or retained), you MUST
propose a `new_note`. Skip only if the card is in the candidate list but
the trace contains no evidence of it being interacted with.

For cards that already have a `current_note`, propose updates only when the
trace reveals something the current note misses. Keep new_note terse
(<=200 chars), concrete, and oriented toward future deck-building decisions.
Never invent cards not in the candidate list.

You MAY also emit up to 3 entries in `non_deck_updates` per the rules in
the system prompt.

Respond with ONLY the JSON object.
"""
```

- [ ] **Step 9.6: Extend `update_card_notes_from_traces` signature and body**

Update the function signature (line 351) to accept the new args:

```python
async def update_card_notes_from_traces(
    *,
    store: CardMemoryStore,
    character: str,
    combat_trace_text: str,
    candidate_cards: list[str],
    run_id: str,
    is_act3_boss_victory: bool = False,
    final_deck: list[str] | None = None,
    final_relics: list[str] | None = None,
    skipped_cards: list[str] | None = None,
    dry_run: bool = False,
    session_logger: object | None = None,
) -> Turn2Result:
```

In the body, after `candidate_table = _render_candidate_table(...)`, render the skipped section:

```python
    skipped_list = list(skipped_cards or [])
    if skipped_list:
        skipped_section = "\n".join(f"- {c}" for c in skipped_list)
    else:
        skipped_section = "(none)"
    prompt = _UPDATER_PROMPT_TEMPLATE.format(
        candidate_table=candidate_table,
        skipped_section=skipped_section,
    )
```

After the existing `proposals, invalid = parse_note_updates(...)` line, add bucket B parsing:

```python
    # Bucket B (non-deck card notes)
    from src.knowledge.class_pool_injector import class_pool_card_names
    class_pool = class_pool_card_names(char_norm)
    final_deck_canonical = frozenset(
        _canonical_card_name(c) for c in (final_deck or []) if c
    )
    final_relics_lower = frozenset(
        str(r).strip().lower() for r in (final_relics or []) if r
    )
    skipped_canonical = frozenset(
        _canonical_card_name(c) for c in skipped_list if c
    )
    non_deck_proposals, non_deck_dropped = parse_non_deck_updates(
        raw_text,
        class_pool=class_pool,
        final_deck=final_deck_canonical,
        final_relics=final_relics_lower,
        skipped_cards=skipped_canonical,
    )
    non_deck_written = apply_note_updates(
        store, character=char_norm,
        proposals=non_deck_proposals, run_id=run_id, dry_run=dry_run,
    )
```

In the final `Turn2Result(...)` return, add the two new fields:

```python
    return Turn2Result(
        notes_written=written,
        notes_kept_unchanged=kept_unchanged,
        notes_invalid=invalid,
        core_engine_applied=engine_applied,
        core_engine_emitted=engine_emitted,
        non_deck_written=non_deck_written,
        non_deck_dropped=non_deck_dropped,
    )
```

In the closing `logger.info` (the `postrun_trace: turn2 ...` line), add bucket B telemetry:

```python
    logger.info(
        "postrun_trace: turn2 notes_written=%d kept=%d invalid=%d  "
        "engine_applied=%d engine_emitted=%s  "
        "non_deck_written=%d non_deck_dropped=%d  (dry_run=%s)",
        written, kept_unchanged, invalid,
        engine_applied, engine_emitted,
        non_deck_written, non_deck_dropped, dry_run,
    )
```

- [ ] **Step 9.7: Run all card_note_updater tests to verify they pass**

```bash
pytest tests/test_card_note_updater.py tests/test_parse_non_deck_updates.py -v
```
Expected: all PASSED.

- [ ] **Step 9.8: Commit**

```bash
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(memory): wire bucket B into Turn 2 (non-deck card notes)"
```

---

## Task 10: Wire skipped_cards through agent/loop.py

**Files:**
- Modify: `src/agent/loop.py:569-572,2315-2317,4097-4099,4324-4336,4385-4533`

- [ ] **Step 10.1: Add `_pending_skipped_cards` instance state**

In `src/agent/loop.py` `__init__` block around line 571, add:

```python
        self._pending_skipped_cards: list[str] = []  # offered-but-not-picked cards from this run's logs
```

In the two state-reset sites (around lines 2317 and 4099) that already clear `_pending_trace_candidates`, add:

```python
        self._pending_skipped_cards = []
```

- [ ] **Step 10.2: Populate the skipped-cards list during HCM extraction**

In `_post_run_hcm_extraction` (around line 4324), after the existing `extract_candidate_cards` call, add the import and the populate call:

```python
                from src.memory.combat_trace_renderer import (
                    extract_candidate_cards,
                    extract_skipped_cards,
                )
                self._pending_combat_trace = _maybe_render_combat_trace(...)
                if self._pending_combat_trace:
                    self._pending_trace_candidates = extract_candidate_cards(recent_combats)
                    self._pending_skipped_cards = extract_skipped_cards(_run_log_events)
                    logger.info(
                        "postrun_trace: rendered %d combats, %d chars, %d candidates, %d skipped",
                        len(recent_combats), len(self._pending_combat_trace),
                        len(self._pending_trace_candidates),
                        len(self._pending_skipped_cards),
                    )
```

(Adjust the existing `extract_candidate_cards` import line to add `extract_skipped_cards` if it is imported earlier in the file — grep first.)

- [ ] **Step 10.3: Forward skipped cards to Turn 2 in `_analyze_build_async`**

Around line 4401-4403, consume the new field alongside the existing pending-trace state:

```python
        combat_trace_text = self._pending_combat_trace
        candidates = self._pending_trace_candidates
        skipped_cards = self._pending_skipped_cards
        self._pending_combat_trace = None
        self._pending_trace_candidates = []
        self._pending_skipped_cards = []
```

In the `update_card_notes_from_traces` call (around line 4515), pass the new parameter:

```python
                        result = await update_card_notes_from_traces(
                            store=self._memory.card_memory_store,
                            character=build_mem.character,
                            combat_trace_text=combat_trace_text,
                            candidate_cards=candidates,
                            run_id=build_mem.run_id,
                            is_act3_boss_victory=is_act3,
                            final_deck=final_deck,
                            final_relics=final_relics,
                            skipped_cards=skipped_cards,
                            dry_run=dry,
                            session_logger=self._session_logger,
                        )
```

- [ ] **Step 10.4: Run the full postrun test suite to confirm no regressions**

```bash
pytest tests/ -v -k "postrun or card_note or build_extractor or trace" --no-header 2>&1 | tail -40
```
Expected: all PASSED.

- [ ] **Step 10.5: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(agent): wire skipped_cards from log into Turn 2 bucket B"
```

---

## Task 11: Live smoke + final verification

**Files:** none modified — verification only.

- [ ] **Step 11.1: Run the entire test suite**

```bash
pytest tests/ --no-header 2>&1 | tail -5
```
Expected: all PASSED, 0 failures.

- [ ] **Step 11.2: Sanity-check token cost on a real Silent run**

Confirm pool injection actually fires by inspecting a postrun log. Run a short live run with tracing enabled (replaces a manual smoke test):

```bash
# In a separate shell; requires live mod + STS2_DATA_REPO etc. configured
STS2_POSTRUN_ENABLED=true python -m scripts.run_agent --steps 80 --runs 1 --character Silent --no-skills --no-evolution
```

When the run finishes, inspect the latest `logs/run_*.jsonl` for postrun_llm_call entries:

```bash
python -c "
import json, glob, os
latest = max(glob.glob('logs/run_*.jsonl'), key=os.path.getmtime)
with open(latest) as f:
    for line in f:
        e = json.loads(line)
        if e.get('event_type') != 'postrun_llm_call': continue
        ct = e.get('call_type', '')
        if ct in ('build_analysis', 'card_note_update'):
            sys_len = len(e.get('system_prompt', ''))
            has_pool = '## Class Pool Reference' in e.get('system_prompt', '')
            has_cached_marker = '<<<CACHED_PREFIX>>>' in e.get('prompt', '')
            print(f'{ct}: sys_len={sys_len} has_pool={has_pool} has_cached_marker={has_cached_marker}')
"
```
Expected output:
```
build_analysis: sys_len=<>~9000 has_pool=True has_cached_marker=False
card_note_update: sys_len=<>~9000 has_pool=True has_cached_marker=False
```
The `<<<CACHED_PREFIX>>>` marker MUST be False (telemetry codepath gone). `has_pool` MUST be True for both.

- [ ] **Step 11.3: Verify bucket B audit hook works**

If the run was non-trivial (Silent reached at least Act 1 boss), check `data/reports/card_notes_<date>.txt` for `[skipped]` or `[combo_inferred]` prefixed reasons:

```bash
ls -t data/reports/card_notes_*.txt 2>/dev/null | head -1 | xargs -I {} grep -E '\[(skipped|combo_inferred)\]' {} | head -5
```
Expected: zero or more `[skipped]` / `[combo_inferred]` lines. Zero is fine on a short run; the absence is not a failure — bucket B is opt-in for the LLM and the cap is 3.

- [ ] **Step 11.4: Final commit (only if any tweaks needed)**

If steps 11.1-11.3 surface tweaks, fix them. Otherwise no commit needed.

- [ ] **Step 11.5: Done**

This task has no commit unless step 11.4 produced changes. The plan is complete.

---

## Self-Review Checklist (filled in by the planner)

**Spec coverage:**
- §3.1 cache cleanup edits → Tasks 2, 3, 5 (split per-file)
- §3.2 class pool injector → Task 1
- §3.3 prompt assembly → Tasks 4 (Turn 1), 6 (Turn 2)
- §3.4 bucket B → Tasks 8 (parser), 9 (integration)
- §3.5 skipped extraction → Task 7
- §4 data flow → Task 10 (wiring)
- §5 prompt changes → Tasks 4, 6, 9
- §6 testing → covered per-task; smoke is Task 11
- §7 risks → mitigations are baked into validation rules (rule 4 for combo, fail-safe `[]` for extract_skipped_cards, hard cap)
- §8 migration → no migration; tasks naturally additive
- §9 decision log → respected (cap=3, evidence_type as reason prefix, auto-detect character, no upgraded stats, no Colorless)

**Type consistency:**
- `Turn2Result` fields used consistently across Tasks 9 / 11.
- `class_pool_card_names` returns `frozenset[str]` (Task 1) — consumed as `frozenset` in `parse_non_deck_updates` (Task 8) and converted with `frozenset(...)` in Task 9 wiring.
- `skipped_cards` parameter is `list[str]` at the public boundary (Task 9, Task 10), narrowed to `frozenset` inside parser (Task 8 / Task 9 step 9.6).

**Placeholder scan:** No `TODO`, `TBD`, "implement appropriate", or "similar to Task N" references. All code blocks are concrete.
