# Combat Trace Postrun Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject 1-2 full combat traces into postrun LLM calls so (A) build_analysis is grounded in real per-turn play rather than aggregated counters, and (B) `CardMemory.note` gets selectively updated based on combat witness — closing the "note almost never updates" gap.

**Architecture:** Render one combat trace string per run, share it across two back-to-back analysis-tier LLM calls under ephemeral prompt cache. Turn 1 extends the existing `analyze_build_with_llm` with the trace as additional user context (output schema unchanged). Turn 2 is a new `card_note_updater` module that writes bounded-history `note` updates. Both gated by env flags for staged rollout.

**Tech Stack:** Python 3.12+, dataclasses, asyncio, Anthropic-compatible prompt caching via `cache_control: ephemeral`, pytest.

**Reference spec:** [2026-04-24-combat-trace-postrun-analysis-design.md](../specs/2026-04-24-combat-trace-postrun-analysis-design.md)

---

## File Structure

**Create:**
- `src/memory/combat_trace_renderer.py` — trace renderer (pure, testable, no LLM)
- `src/memory/card_note_updater.py` — Turn 2 module (LLM call + validate + write)
- `tests/test_combat_trace_renderer.py`
- `tests/test_card_note_updater.py`

**Modify:**
- `config.py` — four new env-backed constants
- `src/log/session_logger.py:337-356` — enrich `_serialize_hand_card`
- `src/memory/models_v2.py:1080-1200` — `CardMemory.note_history` + `with_new_note`
- `src/memory/card_build_extractor.py:612-700` — `analyze_build_with_llm` extended
- `src/brain/llm_caller.py:48-120` — `call_raw` gets `user_cached_prefix` kwarg
- `src/agent/loop.py:4016-4200` — `_post_run_hcm_extraction` wires the renderer + both turns
- `tests/test_card_memory.py` — `note_history` serialization + `with_new_note`

**No delete.**

---

## Task 1: Config constants for new env vars

**Files:**
- Modify: `config.py` (append to the postrun section around line 820-860)

- [ ] **Step 1: Add four env-backed constants in config.py**

Append after the existing `POSTRUN_ENABLED` block (around line 830, before `def postrun_effectively_enabled`):

```python
# ── Combat trace postrun analysis ─────────────────────────────
# Master switch for rendering + passing combat traces into postrun
# build_analysis (Turn 1) and card_note_updater (Turn 2). When off,
# Turn 1 runs without trace context (original behavior) and Turn 2
# is skipped entirely.
POSTRUN_COMBAT_TRACE_ENABLED: bool = os.getenv(
    "STS2_POSTRUN_COMBAT_TRACE_ENABLED", "true",
).lower() in ("1", "true", "yes", "on")

# Turn 2 write gate. When off (default), the card_note_updater LLM
# call still runs to produce log-only dry-run output but does NOT
# persist any note changes. Flip to true after manual review of
# several proposal batches confirms quality.
POSTRUN_NOTE_UPDATE_ENABLED: bool = os.getenv(
    "STS2_POSTRUN_NOTE_UPDATE_ENABLED", "false",
).lower() in ("1", "true", "yes", "on")

# Interrupted-run filter. Trace renderer is skipped when the floor
# sum of the last two completed combats is below this threshold —
# avoids spending tokens on short aborted runs whose decks are not
# meaningful enough to inform note updates.
POSTRUN_TRACE_MIN_FLOOR_SUM: int = int(
    os.getenv("STS2_POSTRUN_TRACE_MIN_FLOOR_SUM", "15"),
)

# Per-combat round cap. Combats exceeding this round count are
# dropped from the trace entirely (not truncated mid-combat) to
# avoid rendering an incomplete fight.
POSTRUN_TRACE_MAX_ROUNDS: int = int(
    os.getenv("STS2_POSTRUN_TRACE_MAX_ROUNDS", "30"),
)
```

- [ ] **Step 2: Verify config loads without errors**

Run: `python -c "import config; print(config.POSTRUN_COMBAT_TRACE_ENABLED, config.POSTRUN_NOTE_UPDATE_ENABLED, config.POSTRUN_TRACE_MIN_FLOOR_SUM, config.POSTRUN_TRACE_MAX_ROUNDS)"`
Expected: `True False 15 30`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat(config): add combat trace postrun analysis flags"
```

---

## Task 2: Enrich `_serialize_hand_card` for trace fidelity

**Files:**
- Modify: `src/log/session_logger.py:337-356`
- Test: `tests/test_session_logger_hand.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_session_logger_hand.py`:

```python
"""Verify _serialize_hand_card captures fields needed by trace renderer."""
from __future__ import annotations

from dataclasses import dataclass

from src.log.session_logger import SessionLogger


@dataclass
class _FakeCard:
    index: int = 0
    name: str = ""
    energy_cost: int = 1
    playable: bool = True
    target_type: str = "single"
    rules_text: str = ""
    damage: int | None = None
    block: int | None = None
    hits: int = 1
    total_damage: int | None = None
    target_previews: list = None
    upgraded: bool = False
    star_cost: int | None = None
    card_type: str = "Attack"
    enchantment_name: str | None = None

    def __post_init__(self) -> None:
        if self.target_previews is None:
            self.target_previews = []


def test_serialize_hand_card_has_enrichment_fields() -> None:
    card = _FakeCard(
        index=0, name="backstab", energy_cost=1,
        rules_text="Deal 11 damage. Only playable as first card each turn.",
        damage=11, total_damage=11,
        upgraded=True, card_type="Attack", star_cost=None,
        enchantment_name="swift",
    )
    data = SessionLogger._serialize_hand_card(card)
    assert data["upgraded"] is True
    assert data["card_type"] == "Attack"
    assert data["enchantment_name"] == "swift"
    assert "star_cost" in data
    assert data["star_cost"] is None


def test_serialize_hand_card_star_cost() -> None:
    card = _FakeCard(name="ice_lance", star_cost=1, card_type="Attack", damage=3)
    data = SessionLogger._serialize_hand_card(card)
    assert data["star_cost"] == 1


def test_serialize_hand_card_missing_fields_defaults() -> None:
    """Cards without new attributes must not crash serialization."""
    card = _FakeCard(name="strike", damage=6)
    # Simulate an older card object missing upgraded/star_cost/etc.
    for attr in ("upgraded", "star_cost", "card_type", "enchantment_name"):
        if hasattr(card, attr):
            delattr(card, attr)
    data = SessionLogger._serialize_hand_card(card)
    assert data["upgraded"] is False
    assert data["star_cost"] is None
    assert data["card_type"] == ""
    assert data["enchantment_name"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_session_logger_hand.py -v`
Expected: FAIL with `KeyError: 'upgraded'` or `KeyError: 'star_cost'` etc.

- [ ] **Step 3: Enrich `_serialize_hand_card`**

Replace `src/log/session_logger.py:337-356` with:

```python
    @staticmethod
    def _serialize_hand_card(c) -> dict:
        """Serialize a hand card with full value fields for replay.

        Fields beyond the base set are needed by the postrun combat trace
        renderer so Turn 1 / Turn 2 LLM calls see upgrade / star-cost /
        enchantment state that plain counters cannot express.
        """
        card: dict = {
            "index": c.index, "name": c.name,
            "energy_cost": c.energy_cost, "playable": c.playable,
            "target_type": c.target_type,
            "rules_text": c.rules_text,
            "damage": c.damage, "block": c.block,
            "hits": c.hits, "total_damage": c.total_damage,
            "upgraded": bool(getattr(c, "upgraded", False)),
            "star_cost": getattr(c, "star_cost", None),
            "card_type": getattr(c, "card_type", "") or "",
            "enchantment_name": getattr(c, "enchantment_name", None),
        }
        if c.target_previews:
            card["target_previews"] = [
                {
                    "target_index": tp.target_index,
                    "damage": tp.damage, "hits": tp.hits,
                    "total_damage": tp.total_damage,
                }
                for tp in c.target_previews
            ]
        return card
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_session_logger_hand.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Run the broader session logger suite to check for regressions**

Run: `pytest tests/ -k "session_logger" -v`
Expected: all prior tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/log/session_logger.py tests/test_session_logger_hand.py
git commit -m "feat(log): enrich hand card with upgraded/star_cost/card_type/enchantment_name"
```

---

## Task 3: Add `note_history` + `with_new_note` to `CardMemory`

**Files:**
- Modify: `src/memory/models_v2.py:1080-1200` (CardMemory dataclass)
- Modify: `tests/test_card_memory.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_card_memory.py`:

```python
def test_card_memory_with_new_note_appends_to_history() -> None:
    """with_new_note creates a new instance with updated note + history."""
    from src.memory.models_v2 import CardMemory

    mem = CardMemory(character="silent", card_name="backstab", note="seed note")
    updated = mem.with_new_note(
        new_note="played 5x in 3 combats, always first-turn",
        run_id="run_20260424_01",
        reason="trace shows reliable first-turn damage",
        trace_citation="Combat 1 R1: Backstab for 11 dmg",
    )
    assert updated.note == "played 5x in 3 combats, always first-turn"
    assert len(updated.note_history) == 1
    entry = updated.note_history[0]
    assert entry["note"] == "played 5x in 3 combats, always first-turn"
    assert entry["run_id"] == "run_20260424_01"
    assert entry["reason"] == "trace shows reliable first-turn damage"
    assert entry["trace_citation"] == "Combat 1 R1: Backstab for 11 dmg"
    assert isinstance(entry["ts"], float) and entry["ts"] > 0
    # Original unchanged (immutable)
    assert mem.note == "seed note"
    assert mem.note_history == ()


def test_card_memory_note_history_caps_at_three() -> None:
    from src.memory.models_v2 import CardMemory

    mem = CardMemory(character="silent", card_name="sly")
    for i in range(5):
        mem = mem.with_new_note(
            new_note=f"note v{i}",
            run_id=f"run_{i}",
            reason=f"r{i}",
            trace_citation=f"c{i}",
        )
    assert len(mem.note_history) == 3
    # Newest first
    assert mem.note_history[0]["note"] == "note v4"
    assert mem.note_history[1]["note"] == "note v3"
    assert mem.note_history[2]["note"] == "note v2"
    # Oldest (v0, v1) evicted
    assert mem.note == "note v4"


def test_card_memory_note_history_serialization_roundtrip() -> None:
    from src.memory.models_v2 import CardMemory

    mem = CardMemory(character="silent", card_name="backstab")
    mem = mem.with_new_note(
        new_note="new note",
        run_id="run_x",
        reason="r",
        trace_citation="c",
    )
    d = mem.to_dict()
    assert "note_history" in d
    assert isinstance(d["note_history"], list)
    assert d["note_history"][0]["note"] == "new note"
    restored = CardMemory.from_dict(d)
    assert restored.note == "new note"
    assert restored.note_history == mem.note_history


def test_card_memory_from_dict_backward_compat_no_note_history() -> None:
    """Existing stored JSON with no note_history field parses cleanly."""
    from src.memory.models_v2 import CardMemory

    legacy = {
        "character": "silent", "card_name": "strike",
        "note": "seed", "pick_count": 2, "play_count": 5,
        # no note_history field
    }
    mem = CardMemory.from_dict(legacy)
    assert mem.note == "seed"
    assert mem.note_history == ()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_card_memory.py -v -k "note_history or with_new_note"`
Expected: 4 FAILED with `AttributeError: 'CardMemory' object has no attribute 'note_history'` / `with_new_note`.

- [ ] **Step 3: Add `note_history` field and `with_new_note` method**

In `src/memory/models_v2.py`, locate the `CardMemory` dataclass (around line 1080). Add the `note_history` field before `last_updated` (keeping the qualitative observation tuple fields adjacent):

```python
    # Audit trail for postrun note updates (§2026-04-24 combat-trace pipeline).
    # Each entry: {note, run_id, reason, trace_citation, ts}. Newest first.
    # Capped at 3 most-recent versions to bound growth per card.
    note_history: tuple[dict, ...] = ()
```

Add the `with_new_note` method inside `CardMemory` (near `effective_note`):

```python
    def with_new_note(
        self,
        *,
        new_note: str,
        run_id: str,
        reason: str,
        trace_citation: str,
    ) -> "CardMemory":
        """Return a replace()-produced copy with note replaced and a new
        history entry prepended.  Caps history at 3 most-recent entries.

        Used by the postrun card_note_updater (Turn 2) to apply selective
        note rewrites grounded in combat trace evidence.
        """
        import time as _time
        from dataclasses import replace as _replace

        entry = {
            "note": new_note,
            "run_id": run_id,
            "reason": reason,
            "trace_citation": trace_citation,
            "ts": _time.time(),
        }
        new_history: tuple[dict, ...] = (entry,) + self.note_history
        if len(new_history) > 3:
            new_history = new_history[:3]
        return _replace(self, note=new_note, note_history=new_history)
```

Update `to_dict` — locate it in the same dataclass and add the serialization of `note_history` in the dict (as a list of dicts):

```python
    def to_dict(self) -> dict[str, Any]:
        return {
            "character": self.character,
            "card_name": self.card_name,
            "note": self.note,
            # ... existing fields preserved ...
            "core_engine_observations": list(self.core_engine_observations),
            "build_role_observations": list(self.build_role_observations),
            "note_history": [dict(e) for e in self.note_history],
            # ... trailing fields preserved ...
        }
```

Update `from_dict` to tolerate missing field:

```python
    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CardMemory":
        return cls(
            # ... existing fields ...
            core_engine_observations=tuple(d.get("core_engine_observations", ())),
            build_role_observations=tuple(d.get("build_role_observations", ())),
            note_history=tuple(d.get("note_history", ())),
            # ... trailing fields ...
        )
```

NOTE: when editing, keep every existing field in place. Only insert the three new references (field, to_dict line, from_dict line). The exact existing dict is in `models_v2.py` — patch by inserting adjacent to existing `core_engine_observations`/`build_role_observations` references.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_card_memory.py -v -k "note_history or with_new_note"`
Expected: 4 PASSED.

- [ ] **Step 5: Run the full card_memory test to check for regressions**

Run: `pytest tests/test_card_memory.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py tests/test_card_memory.py
git commit -m "feat(card-memory): add note_history audit trail and with_new_note"
```

---

## Task 4: Add `user_cached_prefix` kwarg to `call_raw`

**Files:**
- Modify: `src/brain/llm_caller.py:48-120`
- Test: `tests/test_llm_caller_cache.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_caller_cache.py`:

```python
"""Verify call_raw builds multi-block user content when user_cached_prefix is set."""
from __future__ import annotations

import pytest


def test_call_raw_builds_multi_block_when_user_cached_prefix_set(monkeypatch):
    """When user_cached_prefix is non-empty, call_raw must emit a
    content-block list on the user message with cache_control on the
    prefix block so downstream Anthropic cache picks it up."""
    from src.brain import llm_caller

    captured: dict = {}

    class _FakeResponse:
        class _Usage:
            input_tokens = 100
            output_tokens = 10
        usage = _Usage()
        content = [type("B", (), {"text": '{"ok": true}'})()]

    class _FakeBackend:
        async def acall(self, **kwargs):
            captured.update(kwargs)
            return _FakeResponse()

    async def _fake_to_thread(fn, *a, **kw):
        return fn(*a, **kw)

    monkeypatch.setattr(llm_caller, "_get_or_create_backend", lambda: _FakeBackend())
    router = llm_caller.get_router()
    # Force router not to switch model; assume selection returns whatever we pass.

    import asyncio
    asyncio.run(
        llm_caller.call_raw(
            system="sys",
            prompt="tail-only",
            user_cached_prefix="CACHED TRACE",
            call_type="build_analysis",
        )
    )

    messages = captured.get("messages") or []
    assert len(messages) == 1
    content = messages[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[0]["text"] == "CACHED TRACE"
    assert content[0].get("cache_control") == {"type": "ephemeral"}
    assert content[1]["type"] == "text"
    assert content[1]["text"] == "tail-only"
    assert "cache_control" not in content[1]


def test_call_raw_backward_compat_no_prefix_single_string():
    """When user_cached_prefix is empty (default), messages keep the
    original single-string content form."""
    from src.brain import llm_caller
    # Just assert the signature accepts the kwarg and default is "".
    import inspect
    sig = inspect.signature(llm_caller.call_raw)
    assert "user_cached_prefix" in sig.parameters
    assert sig.parameters["user_cached_prefix"].default == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_llm_caller_cache.py -v`
Expected: FAIL with `TypeError: call_raw() got an unexpected keyword argument 'user_cached_prefix'`.

- [ ] **Step 3: Add the kwarg to `call_raw`**

In `src/brain/llm_caller.py`, extend the `call_raw` signature (around line 48) by adding `user_cached_prefix: str = ""` to the parameter list. Then replace the line `messages = [{"role": "user", "content": prompt}]` (around line 80) with:

```python
    if user_cached_prefix:
        # Multi-block user content: put the cacheable prefix (e.g. the
        # shared combat trace for Turn 1 / Turn 2) on its own block with
        # ephemeral cache_control, then the per-call tail uncached.
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_cached_prefix,
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ]
    else:
        messages = [{"role": "user", "content": prompt}]
```

Also update the docstring to mention the new kwarg:

```python
    """Call LLM and return (response_text, latency_ms, total_tokens).

    ... existing docstring ...

    Args:
        ... existing args ...
        user_cached_prefix: When non-empty, the user message is split into
            two content blocks: the prefix (cache_control=ephemeral) and the
            trailing ``prompt`` (uncached). Used by Turn 1 / Turn 2 of the
            postrun combat-trace pipeline to share a cached trace string
            inside the 5-minute Anthropic TTL. No effect on OpenAI-compatible
            providers (cache_control is ignored upstream).
    """
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_llm_caller_cache.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Smoke-run the broader test suite around llm_caller**

Run: `pytest tests/ -k "llm_caller or call_raw" -v`
Expected: existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add src/brain/llm_caller.py tests/test_llm_caller_cache.py
git commit -m "feat(llm): add user_cached_prefix kwarg to call_raw for shared-cache turns"
```

---

## Task 5: Combat trace renderer module

**Files:**
- Create: `src/memory/combat_trace_renderer.py`
- Test: `tests/test_combat_trace_renderer.py`

- [ ] **Step 1: Write the failing test — empty/insufficient cases**

Create `tests/test_combat_trace_renderer.py`:

```python
"""Unit tests for the combat trace renderer."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest


def _make_short_term_empty():
    from src.memory.short_term import ShortTermMemory
    return ShortTermMemory()


def test_render_returns_none_when_no_combats():
    from src.memory.combat_trace_renderer import render_last_two_combats

    stm = _make_short_term_empty()
    result = render_last_two_combats(stm, run_log_events=[])
    assert result is None


def test_extract_candidate_cards_dedupes_case_insensitively():
    from src.memory.combat_trace_renderer import extract_candidate_cards

    # Synthetic combat-like shape: list of dicts with hand_at_start + cards_played
    combats = [
        {
            "hand_at_start_per_round": [["Strike", "Defend"], ["Backstab", "STRIKE"]],
            "cards_played_per_round": [["strike"], ["backstab"]],
        },
        {
            "hand_at_start_per_round": [["defend", "SLY"]],
            "cards_played_per_round": [["Sly"]],
        },
    ]
    out = extract_candidate_cards(combats)
    assert sorted(out) == ["backstab", "defend", "sly", "strike"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_combat_trace_renderer.py -v`
Expected: FAIL with `ModuleNotFoundError: src.memory.combat_trace_renderer`.

- [ ] **Step 3: Create the renderer module — minimal skeleton**

Create `src/memory/combat_trace_renderer.py`:

```python
"""Render recent combats as high-fidelity text traces for postrun LLM analysis.

Produces ground-truth combat reconstruction (hand with real values + rules_text,
player/enemy state, intents, agent plans, replans) that Turn 1 (build_analysis)
and Turn 2 (card_note_updater) share under ephemeral prompt cache.

The renderer is pure and does no LLM work. Failures degrade silently:
unrenderable combats are dropped, zero-combat runs return None.
"""

from __future__ import annotations

import logging
from typing import Any

from src.memory.short_term import CombatTracker, ShortTermMemory

logger = logging.getLogger(__name__)


def render_last_two_combats(
    short_term: ShortTermMemory,
    run_log_events: list[dict],
    *,
    max_rounds: int = 30,
) -> str | None:
    """Render the 1-2 most recent completed combats as one plaintext trace.

    Returns None when:
    - short_term has zero completed combats
    - all candidate combats are unrenderable (e.g. exceed max_rounds or
      have no matchable state snapshots)

    Otherwise returns a newline-joined plaintext block suitable for
    direct inclusion in a user-message cached prefix.
    """
    completed = list(short_term.completed_combats or [])
    if not completed:
        return None

    # Take up to the last 2 completed combats.
    candidates = completed[-2:]
    rendered_blocks: list[str] = []
    for i, combat in enumerate(candidates, start=1):
        block = _render_single_combat(
            combat_index=i, combat=combat,
            run_log_events=run_log_events, max_rounds=max_rounds,
        )
        if block is not None:
            rendered_blocks.append(block)

    if not rendered_blocks:
        return None

    header = (
        "## Recent Combat Traces (ground truth)\n\n"
        "Below are round-by-round traces of the 1-2 most recent combats. "
        "Each round shows the real hand with exact values and rules_text, "
        "enemy state and intent, the agent's plan and reasoning, and any "
        "replans. Use these to ground downstream reasoning in what actually "
        "happened rather than what aggregated counts suggest.\n"
    )
    return header + "\n\n".join(rendered_blocks)


def extract_candidate_cards(combats: list[Any]) -> list[str]:
    """Return the set of card names (canonical lowercase) appearing across
    hand_at_start and cards_played of the provided combats, deduped.

    Accepts either real CombatTracker objects or dicts with the shape
    ``{hand_at_start_per_round: [[str,...],...], cards_played_per_round: [[str,...],...]}``
    for test convenience.
    """
    seen: set[str] = set()
    for combat in combats:
        hand_rounds: list[list[str]] = []
        played_rounds: list[list[str]] = []
        if isinstance(combat, dict):
            hand_rounds = combat.get("hand_at_start_per_round", []) or []
            played_rounds = combat.get("cards_played_per_round", []) or []
        else:
            for rnd in getattr(combat, "rounds", []) or []:
                hand_rounds.append(list(getattr(rnd, "hand_at_start", []) or []))
                played_rounds.append(list(getattr(rnd, "cards_played", []) or []))

        for names in hand_rounds:
            for n in names:
                if n:
                    seen.add(str(n).strip().lower())
        for names in played_rounds:
            for n in names:
                if n:
                    seen.add(str(n).strip().lower())
    return sorted(seen)


def _render_single_combat(
    *,
    combat_index: int,
    combat: CombatTracker,
    run_log_events: list[dict],
    max_rounds: int,
) -> str | None:
    """Render one combat. Returns None if the combat has too many rounds
    or cannot be matched against any state snapshot."""
    rounds = getattr(combat, "rounds", []) or []
    if not rounds:
        return None
    if len(rounds) > max_rounds:
        logger.info(
            "postrun_trace: combat %d dropped (rounds=%d > max=%d)",
            combat_index, len(rounds), max_rounds,
        )
        return None

    lines: list[str] = []
    lines.append(
        f"### Combat {combat_index}: {combat.enemy_key} "
        f"(Act {combat.act}, Floor {combat.floor}, "
        f"{combat.combat_type}) — {'WON' if combat.won else 'LOST'}"
    )

    # Pre-combat relic block (from first matched snapshot, else from tracker).
    first_snapshot = _find_first_snapshot_for_combat(run_log_events, combat)
    relics_block = _render_relics(first_snapshot, combat)
    if relics_block:
        lines.append(relics_block)

    lines.append(
        f"HP before: {combat.hp_before} → after: {combat.hp_after}. "
        f"Deck size at start: {combat.deck_size}."
    )

    # Build a lookup of decisions and replans by (floor, round_num)
    decisions_by_round = _index_decisions(run_log_events, combat.floor)

    for rnd in rounds:
        block = _render_round(
            combat=combat, round_obj=rnd,
            run_log_events=run_log_events,
            decisions=decisions_by_round.get(rnd.round_num, []),
        )
        lines.append(block)

    return "\n".join(lines)


def _render_round(
    *,
    combat: CombatTracker,
    round_obj: Any,
    run_log_events: list[dict],
    decisions: list[dict],
) -> str:
    """Render a single combat round."""
    from src.memory.core_engine_extractor import _find_matching_state_snapshot

    snapshot = _find_matching_state_snapshot(
        run_log_events, floor=combat.floor, round_num=round_obj.round_num,
    )
    lines: list[str] = []
    lines.append(
        f"\n-- Round {round_obj.round_num} -- "
        f"energy {round_obj.energy_available}, "
        f"hp {round_obj.hp_start}→{round_obj.hp_end}, "
        f"dmg_dealt {round_obj.damage_dealt}, "
        f"dmg_taken {round_obj.damage_taken}, "
        f"block_gained {round_obj.block_gained}"
    )

    # Hand with real values + rules_text
    hand_block = _render_hand(snapshot, round_obj)
    if hand_block:
        lines.append("Hand:\n" + hand_block)

    # Player powers
    powers_block = _render_player_powers(snapshot)
    if powers_block:
        lines.append("Player powers: " + powers_block)

    # Enemies with intents + powers
    enemies_block = _render_enemies(round_obj)
    if enemies_block:
        lines.append("Enemies:\n" + enemies_block)

    # Agent plan + reasoning from decision events
    plan_block = _render_plan(decisions)
    if plan_block:
        lines.append(plan_block)

    # Cards actually played
    if round_obj.cards_played:
        lines.append("Played: " + ", ".join(round_obj.cards_played))

    return "\n".join(lines)


def _render_hand(snapshot: dict | None, round_obj: Any) -> str:
    """Render hand cards with full details when a state snapshot is
    available, otherwise fall back to name-only listing."""
    if snapshot:
        combat_state = (snapshot.get("combat") or {})
        player = (combat_state.get("player") or {})
        hand = player.get("hand") or []
        if hand:
            lines: list[str] = []
            for c in hand:
                lines.append(_format_hand_card_line(c))
            return "\n".join(lines)
    names = list(getattr(round_obj, "hand_at_start", []) or [])
    if not names:
        return ""
    return ", ".join(names) + "  (details unavailable)"


def _format_hand_card_line(card: dict) -> str:
    """Format one hand card in high-density form:
    ``- Strike+ (Attack, cost=1) dmg=9, block=0: Deal 9 damage.``
    """
    name = card.get("name") or "?"
    if card.get("upgraded"):
        name = name + "+"
    enchant = card.get("enchantment_name") or ""
    if enchant:
        name = f"{name} [{enchant}]"
    cost = card.get("energy_cost")
    star = card.get("star_cost")
    cost_str = str(cost) if cost is not None else "?"
    if star:
        cost_str = f"{cost_str}★{star}"
    card_type = card.get("card_type") or card.get("type") or "?"

    value_bits: list[str] = []
    if card.get("damage") is not None:
        total = card.get("total_damage")
        if total is not None and total != card.get("damage"):
            value_bits.append(f"dmg={card['damage']}×{card.get('hits', 1)}={total}")
        else:
            value_bits.append(f"dmg={card.get('damage')}")
    if card.get("block") is not None:
        value_bits.append(f"block={card.get('block')}")
    values = " " + ", ".join(value_bits) if value_bits else ""

    rules = card.get("rules_text") or card.get("description") or ""
    return f"- {name} ({card_type}, cost={cost_str}){values}: {rules}"


def _render_relics(snapshot: dict | None, combat: CombatTracker) -> str:
    if not snapshot:
        if combat.relics:
            return "Relics: " + "; ".join(combat.relics)
        return ""
    player = (snapshot.get("combat") or {}).get("player") or {}
    relics = player.get("relics") or []
    if not relics:
        if combat.relics:
            return "Relics: " + "; ".join(combat.relics)
        return ""
    parts = []
    for r in relics:
        name = r.get("name") or "?"
        desc = r.get("description") or ""
        stack = r.get("stack")
        stack_str = f" ×{stack}" if stack and stack != 1 else ""
        parts.append(f"{name}{stack_str} — {desc}" if desc else f"{name}{stack_str}")
    return "Relics:\n- " + "\n- ".join(parts)


def _render_player_powers(snapshot: dict | None) -> str:
    if not snapshot:
        return ""
    player = (snapshot.get("combat") or {}).get("player") or {}
    powers = player.get("powers") or []
    if not powers:
        return ""
    parts = []
    for p in powers:
        name = p.get("name") or "?"
        amount = p.get("amount")
        desc = p.get("description") or ""
        head = f"{name}({amount})" if amount is not None else name
        parts.append(f"{head} — {desc}" if desc else head)
    return "; ".join(parts)


def _render_enemies(round_obj: Any) -> str:
    lines: list[str] = []
    intents = list(getattr(round_obj, "enemy_intents", []) or [])
    enemy_hp = list(getattr(round_obj, "enemy_hp_snapshot", []) or [])
    enemy_powers = list(getattr(round_obj, "enemy_powers_snapshot", []) or [])
    for i, entry in enumerate(enemy_hp):
        try:
            eid, name, hp, max_hp = entry
        except Exception:
            continue
        intent = intents[i] if i < len(intents) else ""
        powers = enemy_powers[i] if i < len(enemy_powers) else []
        power_str = f" [{', '.join(powers)}]" if powers else ""
        intent_str = f" intent={intent}" if intent else ""
        lines.append(f"- {name} ({hp}/{max_hp}){power_str}{intent_str}")
    return "\n".join(lines)


def _render_plan(decisions: list[dict]) -> str:
    if not decisions:
        return ""
    lines: list[str] = []
    # Decisions are chronological. First is plan; subsequent are replans.
    for i, dec in enumerate(decisions):
        tag = "Plan" if i == 0 else f"[REPLAN #{i}]"
        reasoning = (dec.get("reasoning") or "").strip()
        action = dec.get("action") or ""
        lines.append(f"{tag}: {action}")
        if reasoning:
            lines.append(f"  reason: {reasoning}")
    return "\n".join(lines)


def _index_decisions(run_log_events: list[dict], floor: int) -> dict[int, list[dict]]:
    """Return decisions on the given floor, indexed by combat round number."""
    by_round: dict[int, list[dict]] = {}
    for ev in run_log_events:
        if ev.get("event") != "decision":
            continue
        if ev.get("floor") != floor:
            continue
        # combat round is stored on the state event, not decision. We attribute
        # the decision to the most recent state event's round_num by scanning.
        round_num = _derive_decision_round(ev, run_log_events)
        if round_num is None:
            continue
        by_round.setdefault(round_num, []).append(ev)
    return by_round


def _derive_decision_round(
    decision_event: dict, run_log_events: list[dict],
) -> int | None:
    """Find the most recent 'state' event before this decision event
    (same floor) and return its combat.round value."""
    step = decision_event.get("step", -1)
    floor = decision_event.get("floor")
    best: int | None = None
    for ev in run_log_events:
        if ev.get("event") != "state":
            continue
        if ev.get("floor") != floor:
            continue
        ev_step = ev.get("step", -1)
        if ev_step > step:
            continue
        round_num = ((ev.get("combat") or {}).get("round"))
        if round_num is not None:
            best = round_num
    return best


def _find_first_snapshot_for_combat(
    run_log_events: list[dict], combat: CombatTracker,
) -> dict | None:
    from src.memory.core_engine_extractor import _find_matching_state_snapshot

    if not combat.rounds:
        return None
    return _find_matching_state_snapshot(
        run_log_events, floor=combat.floor, round_num=combat.rounds[0].round_num,
    )
```

- [ ] **Step 4: Re-run the two minimal tests to check skeleton passes**

Run: `pytest tests/test_combat_trace_renderer.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Add higher-fidelity tests — 1-combat render + max_rounds drop**

Append to `tests/test_combat_trace_renderer.py`:

```python
def _make_stm_with_one_combat(round_count: int = 2):
    from src.memory.short_term import (
        CombatTracker, CombatRoundTracker, ShortTermMemory,
    )

    stm = ShortTermMemory()
    tracker = CombatTracker(
        enemy_key="elite:mushroom", combat_type="elite",
        enemy_names=["Mushroom"],
        hp_before=60, deck_size=12,
        relics=["Ring of the Snake", "Snecko Skull"],
        floor=7, act=1, hp_after=50, won=True,
        terminal_reason="win",
    )
    for r in range(1, round_count + 1):
        rnd = CombatRoundTracker(
            round_num=r, energy_available=3,
            hp_start=60 - (r - 1) * 5, hp_end=60 - r * 5,
            enemy_intents=["attack 8"],
            hand_at_start=["strike", "defend", "backstab"],
            cards_played=["strike", "backstab"] if r == 1 else ["defend"],
            damage_dealt=17 if r == 1 else 0,
            damage_taken=5,
            block_gained=5,
            enemy_hp_snapshot=[("e1", "Mushroom", 60, 60)],
            enemy_powers_snapshot=[[]],
        )
        tracker.rounds.append(rnd)
    stm.completed_combats.append(tracker)
    return stm, tracker


def _make_state_event(floor: int, round_num: int, hand_cards: list[dict]) -> dict:
    return {
        "event": "state",
        "floor": floor,
        "state_type": "elite",
        "step": round_num * 10,
        "combat": {
            "round": round_num,
            "player": {
                "hand": hand_cards,
                "powers": [{"name": "Strength", "amount": 2, "description": "+2 dmg"}],
                "relics": [
                    {"name": "Ring of the Snake", "description": "Draw 2 extra", "stack": 1},
                ],
            },
        },
    }


def _make_decision_event(floor: int, step: int, action: str, reasoning: str) -> dict:
    return {
        "event": "decision",
        "floor": floor,
        "step": step,
        "state_type": "elite",
        "action": action,
        "reasoning": reasoning,
        "source": "llm",
    }


def test_render_one_combat_contains_expected_sections():
    from src.memory.combat_trace_renderer import render_last_two_combats

    stm, tracker = _make_stm_with_one_combat(round_count=2)
    run_log_events = [
        _make_state_event(7, 1, [
            {
                "name": "Strike", "energy_cost": 1, "card_type": "Attack",
                "rules_text": "Deal 6 damage.",
                "damage": 6, "total_damage": 6, "hits": 1,
                "upgraded": False, "star_cost": None, "enchantment_name": None,
            },
            {
                "name": "Defend", "energy_cost": 1, "card_type": "Skill",
                "rules_text": "Gain 5 Block.",
                "damage": None, "block": 5,
                "upgraded": False, "star_cost": None, "enchantment_name": None,
            },
            {
                "name": "Backstab", "energy_cost": 1, "card_type": "Attack",
                "rules_text": "Deal 11 damage. First-turn only.",
                "damage": 11, "total_damage": 11, "hits": 1,
                "upgraded": True, "star_cost": None, "enchantment_name": "swift",
            },
        ]),
        _make_decision_event(7, 15, "plan", "lead with Backstab for burst"),
        _make_decision_event(7, 17, "replan", "Strike instead after observing block"),
        _make_state_event(7, 2, []),
    ]
    out = render_last_two_combats(stm, run_log_events)
    assert out is not None
    assert "Combat 1: elite:mushroom" in out
    assert "Ring of the Snake" in out
    assert "Round 1" in out
    assert "Strike (Attack, cost=1) dmg=6: Deal 6 damage." in out
    assert "Backstab+" in out  # upgraded marker
    assert "[swift]" in out     # enchantment bracket
    assert "Plan:" in out
    assert "[REPLAN #1]" in out
    assert "Played: strike, backstab" in out
    assert "WON" in out


def test_render_drops_combat_exceeding_max_rounds():
    from src.memory.combat_trace_renderer import render_last_two_combats

    stm, _ = _make_stm_with_one_combat(round_count=5)
    out = render_last_two_combats(stm, run_log_events=[], max_rounds=3)
    assert out is None


def test_render_two_combats_both_present():
    from src.memory.combat_trace_renderer import render_last_two_combats
    from src.memory.short_term import (
        CombatTracker, CombatRoundTracker, ShortTermMemory,
    )

    stm = ShortTermMemory()
    for idx, floor in enumerate([6, 10], start=1):
        t = CombatTracker(
            enemy_key=f"monster_{idx}", combat_type="monster",
            enemy_names=["Goon"], hp_before=60, deck_size=10,
            floor=floor, act=1, hp_after=55, won=True,
        )
        t.rounds.append(CombatRoundTracker(
            round_num=1, energy_available=3,
            hp_start=60, hp_end=55,
            enemy_intents=[], hand_at_start=[], cards_played=["strike"],
            enemy_hp_snapshot=[("g", "Goon", 40, 40)],
            enemy_powers_snapshot=[[]],
        ))
        stm.completed_combats.append(t)
    out = render_last_two_combats(stm, run_log_events=[])
    assert out is not None
    assert "Combat 1: monster_1" in out
    assert "Combat 2: monster_2" in out
```

- [ ] **Step 6: Run all renderer tests**

Run: `pytest tests/test_combat_trace_renderer.py -v`
Expected: 5 PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/memory/combat_trace_renderer.py tests/test_combat_trace_renderer.py
git commit -m "feat(memory): add combat trace renderer for postrun LLM context"
```

---

## Task 6: Extend `analyze_build_with_llm` to accept `combat_trace_text`

**Files:**
- Modify: `src/memory/card_build_extractor.py:496-650`
- Test: extend `tests/test_card_build_extractor_json.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_card_build_extractor_json.py`:

```python
def test_analyze_build_with_llm_accepts_combat_trace_text(monkeypatch):
    """analyze_build_with_llm must accept combat_trace_text kwarg and pass
    it to call_raw as user_cached_prefix."""
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
    # The import inside analyze_build_with_llm is "from src.brain.llm_caller
    # import call_raw". Patch that path.
    import src.brain.llm_caller as llm_caller
    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    import asyncio
    evidence = {"character": "silent", "victory": False, "final_floor": 8}
    asyncio.run(cbe.analyze_build_with_llm(
        evidence, combat_trace_text="FAKE TRACE BLOCK",
    ))

    assert captured["kwargs"].get("user_cached_prefix") == "FAKE TRACE BLOCK"


def test_analyze_build_with_llm_no_trace_preserves_old_call_shape(monkeypatch):
    from src.memory import card_build_extractor as cbe
    import src.brain.llm_caller as llm_caller

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["kwargs"] = kwargs
        return ('{"decision":"reject_no_clear_build","target_build_id":"",'
                '"build_summary":"x","primary_plan":"y","damage_engine":"z",'
                '"defense_engine":"z","cycle_engine":"z","energy_engine":"z",'
                '"build_tags":["defeat"],"card_roles":[],"weak_points":"w",'
                '"confidence":0.3,"key_cards":[],"coherence_score":0.5,'
                '"coherence_analysis":"x"}', 100.0, 100)

    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    import asyncio
    asyncio.run(cbe.analyze_build_with_llm({"character": "silent"}))
    # Default: user_cached_prefix should be "" (or absent)
    assert captured["kwargs"].get("user_cached_prefix", "") == ""
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_card_build_extractor_json.py -v -k "combat_trace or preserves_old"`
Expected: FAIL with `TypeError: analyze_build_with_llm() got an unexpected keyword argument 'combat_trace_text'`.

- [ ] **Step 3: Extend `analyze_build_with_llm`**

Modify `src/memory/card_build_extractor.py`. Update the signature (line 612) and insert a trace-appending block before the `prompt = ...format(...)` call (around line 623). Replace the current function header and prompt construction:

```python
async def analyze_build_with_llm(
    evidence: dict[str, Any],
    *,
    combat_trace_text: str | None = None,
) -> dict[str, Any]:
    """Call the analysis-tier LLM to interpret build evidence.

    Returns a dict with build_summary, build_tags, primary_plan, etc.
    On failure, returns a minimal fallback dict with low confidence.

    Args:
        evidence: Deterministic evidence dict from ``extract_build_evidence``.
        combat_trace_text: Optional high-fidelity trace of the last 1-2
            combats (from ``combat_trace_renderer``). When present, it is
            passed as the user-message cached prefix so Turn 2 of the
            postrun pipeline can hit the same Anthropic cache entry within
            the 5-minute TTL. Output schema is unchanged — the trace only
            supplies extra grounding context.
    """
    from src.brain.llm_caller import call_raw

    evidence_text = format_evidence_for_llm(evidence)
    character = normalize_character(str(evidence.get("character", "")))
    registry_text = _format_build_registry_for_llm(character)
    prompt = _BUILD_ANALYSIS_PROMPT.format(
        evidence_text=evidence_text,
        build_registry_text=registry_text,
    )
    # When a trace is present, append a small instruction note so the LLM
    # knows to use it. The trace text itself rides in the cached prefix.
    if combat_trace_text:
        prompt = (
            "Additional context: a full round-by-round trace of the 1-2 most "
            "recent combats appears at the top of this user message (before "
            "the evidence block). Use it as ground truth for how the deck "
            "actually played when choosing build_summary / damage_engine / "
            "weak_points.\n\n" + prompt
        )
```

Update the `call_raw` invocation (around line 631) to pass the kwarg:

```python
            raw_text, latency_ms, tokens = await call_raw(
                _BUILD_ANALYSIS_SYSTEM,
                prompt,
                think=False,
                call_type="build_analysis",
                user_cached_prefix=(combat_trace_text or ""),
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_card_build_extractor_json.py -v -k "combat_trace or preserves_old"`
Expected: 2 PASSED.

- [ ] **Step 5: Run the broader card_build_extractor test suite**

Run: `pytest tests/test_card_build_extractor_json.py tests/test_build_memory.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memory/card_build_extractor.py tests/test_card_build_extractor_json.py
git commit -m "feat(build-analysis): accept combat_trace_text as cached prefix"
```

---

## Task 7: Card note updater module (Turn 2)

**Files:**
- Create: `src/memory/card_note_updater.py`
- Test: `tests/test_card_note_updater.py`

- [ ] **Step 1: Write the failing test — module + parse_note_updates**

Create `tests/test_card_note_updater.py`:

```python
"""Unit tests for the Turn 2 card note updater."""
from __future__ import annotations

import pytest


def test_parse_note_updates_returns_valid_proposals():
    from src.memory.card_note_updater import parse_note_updates

    raw = '{"updates": [{"card_name": "backstab", "new_note": "reliable first-turn 11", "reason": "saw it", "trace_citation": "C1 R1"}]}'
    candidates = {"backstab", "strike"}
    proposals, invalid = parse_note_updates(raw, candidates)
    assert len(proposals) == 1
    assert invalid == 0
    assert proposals[0]["card_name"] == "backstab"


def test_parse_note_updates_drops_unknown_card():
    from src.memory.card_note_updater import parse_note_updates

    raw = '{"updates": [{"card_name": "phantom_card", "new_note": "x", "reason": "r", "trace_citation": "c"}]}'
    proposals, invalid = parse_note_updates(raw, {"backstab"})
    assert proposals == []
    assert invalid == 1


def test_parse_note_updates_drops_oversized_new_note():
    from src.memory.card_note_updater import parse_note_updates

    long_note = "x" * 201
    raw = f'{{"updates": [{{"card_name": "strike", "new_note": "{long_note}", "reason": "r", "trace_citation": "c"}}]}}'
    proposals, invalid = parse_note_updates(raw, {"strike"})
    assert proposals == []
    assert invalid == 1


def test_parse_note_updates_drops_empty_fields():
    from src.memory.card_note_updater import parse_note_updates

    cases = [
        '{"updates":[{"card_name":"strike","new_note":"","reason":"r","trace_citation":"c"}]}',
        '{"updates":[{"card_name":"strike","new_note":"x","reason":"","trace_citation":"c"}]}',
        '{"updates":[{"card_name":"strike","new_note":"x","reason":"r","trace_citation":""}]}',
    ]
    for raw in cases:
        proposals, invalid = parse_note_updates(raw, {"strike"})
        assert proposals == []
        assert invalid == 1


def test_parse_note_updates_bad_json_returns_empty():
    from src.memory.card_note_updater import parse_note_updates

    proposals, invalid = parse_note_updates("not json {", {"strike"})
    assert proposals == []
    assert invalid == 0  # whole-response failure is not counted as invalid proposals


def test_parse_note_updates_mixed_batch():
    from src.memory.card_note_updater import parse_note_updates

    raw = (
        '{"updates": ['
        '{"card_name": "strike", "new_note": "good", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "ghost_card", "new_note": "x", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "defend", "new_note": "ok", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "sly", "new_note": "", "reason": "r", "trace_citation": "c"}'
        ']}'
    )
    proposals, invalid = parse_note_updates(raw, {"strike", "defend", "sly"})
    # strike + defend valid, ghost unknown, sly empty
    assert len(proposals) == 2
    assert {p["card_name"] for p in proposals} == {"strike", "defend"}
    assert invalid == 2


def test_apply_note_updates_writes_and_creates_missing_cards(tmp_path):
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import apply_note_updates

    store = CardMemoryStore()
    proposals = [
        {"card_name": "backstab", "new_note": "n1", "reason": "r1", "trace_citation": "c1"},
        {"card_name": "strike",   "new_note": "n2", "reason": "r2", "trace_citation": "c2"},
    ]
    written = apply_note_updates(
        store, character="silent", proposals=proposals, run_id="run_X",
    )
    assert written == 2
    assert store.get("silent", "backstab").note == "n1"
    assert store.get("silent", "strike").note == "n2"
    assert len(store.get("silent", "backstab").note_history) == 1


def test_apply_note_updates_dry_run_does_not_write(tmp_path):
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import apply_note_updates

    store = CardMemoryStore()
    proposals = [
        {"card_name": "backstab", "new_note": "n1", "reason": "r1", "trace_citation": "c1"},
    ]
    written = apply_note_updates(
        store, character="silent", proposals=proposals, run_id="run_X",
        dry_run=True,
    )
    assert written == 0
    assert store.get("silent", "backstab") is None
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_card_note_updater.py -v`
Expected: FAIL with `ModuleNotFoundError: src.memory.card_note_updater`.

- [ ] **Step 3: Create the module**

Create `src/memory/card_note_updater.py`:

```python
"""Turn 2 of the combat-trace postrun pipeline.

Consumes the same combat trace string that Turn 1 (build_analysis) used,
calls the analysis-tier LLM to selectively propose per-card note updates,
validates each proposal, and writes kept updates to the CardMemoryStore
via ``CardMemory.with_new_note`` (bounded 3-version history).

Shares Anthropic ephemeral cache with Turn 1 by passing the trace through
``call_raw(user_cached_prefix=...)``. The two turns must be invoked within
the 5-minute TTL with no intervening LLM traffic that would evict the
cache entry.

Gated by ``config.POSTRUN_NOTE_UPDATE_ENABLED`` — when False, the LLM
call still runs but proposals are logged and dropped (no writes).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.memory.card_memory_store import CardMemoryStore
from src.memory.models_v2 import CardMemory, normalize_character

logger = logging.getLogger(__name__)

_MAX_NOTE_CHARS = 200

_NOTE_UPDATER_SYSTEM = (
    "You review postrun combat traces and selectively propose updates to "
    "per-card notes. A note is a <=200-character deck-building hint that "
    "surfaces when the card appears in a reward / shop / card_select "
    "decision. It should capture non-obvious role or risk information that "
    "aggregated counters cannot express.\n\n"
    "Output STRICTLY a JSON object with this shape:\n"
    "{\n"
    '  "updates": [\n'
    "    {\n"
    '      "card_name": "<one of the provided candidates, lowercase>",\n'
    '      "new_note": "<= 200 chars, concrete and forward-looking",\n'
    '      "reason": "<1 line — why this note, what trace moment justifies it>",\n'
    '      "trace_citation": "<short quote from trace, e.g. \'Combat 2 R3: '
    "played Backstab for 11 dmg after Sly'>\"\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Empty list if nothing in the traces warrants an update. Never invent "
    "cards. Only use card names that appear in the provided candidate list."
)


_UPDATER_PROMPT_TEMPLATE = """\
## Candidate cards (name | current_note | play_count | sly_play | total_damage | total_block)

{candidate_table}

## Instructions

For each candidate card, decide whether the traces at the top of this user
message justify a new or updated note. Favor cards where the trace reveals
something the current note misses, or where the card has no note yet. Keep
new_note terse (<=200 chars), concrete, and oriented toward future deck-
building decisions. Never invent cards not in the candidate list.

Respond with ONLY the JSON object.
"""


def _render_candidate_table(
    store: CardMemoryStore, character: str, candidate_cards: list[str],
) -> str:
    """Render the candidate card table as a pipe-delimited list."""
    lines: list[str] = []
    for name in candidate_cards:
        mem = store.get(character, name)
        if mem is None:
            lines.append(f"- {name} | (no memory yet) | 0 | 0 | 0 | 0")
            continue
        lines.append(
            f"- {name} | {(mem.note or '(empty)')[:120]} | "
            f"{mem.play_count} | {mem.sly_play_count} | "
            f"{mem.total_damage} | {mem.total_block}"
        )
    return "\n".join(lines) if lines else "(no candidates)"


def parse_note_updates(
    raw_text: str, candidate_cards: set[str],
) -> tuple[list[dict], int]:
    """Parse LLM response into validated proposals.

    Returns ``(proposals, invalid_count)``. Whole-response JSON failure
    returns ``([], 0)`` — not counted as invalid proposals because no
    proposals existed in the first place.
    """
    raw = (raw_text or "").strip()
    if raw.startswith("```"):
        # Strip code fences.
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("card_note_updater: failed to parse LLM JSON")
        return [], 0

    updates = parsed.get("updates") if isinstance(parsed, dict) else None
    if not isinstance(updates, list):
        return [], 0

    candidate_lower = {c.lower() for c in candidate_cards}
    valid: list[dict] = []
    invalid = 0
    for u in updates:
        if not isinstance(u, dict):
            invalid += 1
            continue
        card = str(u.get("card_name", "")).strip().lower()
        new_note = str(u.get("new_note", "")).strip()
        reason = str(u.get("reason", "")).strip()
        citation = str(u.get("trace_citation", "")).strip()
        if card not in candidate_lower:
            invalid += 1
            continue
        if not new_note or len(new_note) > _MAX_NOTE_CHARS:
            invalid += 1
            continue
        if not reason or len(reason) > _MAX_NOTE_CHARS:
            invalid += 1
            continue
        if not citation:
            invalid += 1
            continue
        valid.append({
            "card_name": card,
            "new_note": new_note,
            "reason": reason,
            "trace_citation": citation,
        })
    return valid, invalid


def apply_note_updates(
    store: CardMemoryStore,
    *,
    character: str,
    proposals: list[dict],
    run_id: str,
    dry_run: bool = False,
) -> int:
    """Persist validated proposals to the store. Returns written count.

    When ``dry_run`` is True, logs each proposal but performs no writes."""
    char_norm = normalize_character(character)
    written = 0
    for p in proposals:
        card_name = p["card_name"]
        if dry_run:
            logger.info(
                "card_note_updater[DRY_RUN]: would update %s/%s -> %s (reason=%s)",
                char_norm, card_name, p["new_note"][:60], p["reason"][:60],
            )
            continue
        existing = store.get(char_norm, card_name) or CardMemory(
            character=char_norm, card_name=card_name,
        )
        updated = existing.with_new_note(
            new_note=p["new_note"],
            run_id=run_id,
            reason=p["reason"],
            trace_citation=p["trace_citation"],
        )
        store.put(updated)
        written += 1
    return written


async def update_card_notes_from_traces(
    *,
    store: CardMemoryStore,
    character: str,
    combat_trace_text: str,
    candidate_cards: list[str],
    run_id: str,
    dry_run: bool = False,
) -> tuple[int, int, int]:
    """Turn 2 entry point. Calls LLM, parses, applies.

    Returns ``(written, kept_unchanged, invalid)``. ``kept_unchanged`` is
    ``len(candidate_cards) - len(proposals)`` (cards the LLM chose not to
    touch); ``invalid`` counts per-proposal validation failures.
    """
    from src.brain.llm_caller import call_raw

    if not combat_trace_text or not candidate_cards:
        return 0, 0, 0

    char_norm = normalize_character(character)
    candidate_table = _render_candidate_table(store, char_norm, candidate_cards)
    prompt = _UPDATER_PROMPT_TEMPLATE.format(candidate_table=candidate_table)

    try:
        raw_text, latency_ms, tokens = await call_raw(
            _NOTE_UPDATER_SYSTEM,
            prompt,
            think=False,
            call_type="card_note_update",
            user_cached_prefix=combat_trace_text,
        )
    except Exception:
        logger.warning("card_note_updater: LLM call failed", exc_info=True)
        return 0, 0, 0

    logger.info(
        "card_note_updater: LLM call %.0fms, %d tokens", latency_ms, tokens,
    )

    candidate_set = {c.lower() for c in candidate_cards}
    proposals, invalid = parse_note_updates(raw_text, candidate_set)
    written = apply_note_updates(
        store, character=char_norm,
        proposals=proposals, run_id=run_id, dry_run=dry_run,
    )
    kept_unchanged = max(0, len(candidate_cards) - len(proposals) - invalid)
    logger.info(
        "postrun_trace: turn2 proposals written=%d kept_unchanged=%d invalid=%d "
        "(dry_run=%s)",
        written, kept_unchanged, invalid, dry_run,
    )
    return written, kept_unchanged, invalid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_card_note_updater.py -v`
Expected: 8 PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(memory): add card_note_updater (Turn 2 of combat-trace pipeline)"
```

---

## Task 8: Wire trace + both turns into `_post_run_hcm_extraction`

**Files:**
- Modify: `src/agent/loop.py:4016-4200`
- Test: extend `tests/test_post_run_data_pipeline.py` or add `tests/test_post_run_trace_wiring.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_post_run_trace_wiring.py`:

```python
"""Integration test for the combat-trace postrun wiring.

Asserts that when `_post_run_hcm_extraction` runs:
  - combat_trace_renderer is called once.
  - analyze_build_with_llm receives combat_trace_text.
  - update_card_notes_from_traces is called iff trace is non-None and
    floor_sum >= threshold.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_trace_disabled_skips_pipeline(monkeypatch):
    """When POSTRUN_COMBAT_TRACE_ENABLED=False, renderer is not called and
    analyze_build_with_llm is called without trace."""
    import config
    monkeypatch.setattr(config, "POSTRUN_COMBAT_TRACE_ENABLED", False)

    from src.agent import loop as loop_mod
    # We test the helper in isolation rather than instantiating AgentLoop.
    # Extract the branch under test — loop.py introduces a helper
    # `_maybe_render_combat_trace(stm, run_log_events, threshold)` that
    # returns None when disabled. Test this helper directly.
    assert hasattr(loop_mod, "_maybe_render_combat_trace"), \
        "AgentLoop helper _maybe_render_combat_trace must be exposed at module level"

    out = loop_mod._maybe_render_combat_trace(stm=None, run_log_events=[], floor_sum=100)
    assert out is None


def test_floor_sum_gate_skips_pipeline(monkeypatch):
    """When floor_sum < threshold, renderer is not invoked."""
    import config
    monkeypatch.setattr(config, "POSTRUN_COMBAT_TRACE_ENABLED", True)
    monkeypatch.setattr(config, "POSTRUN_TRACE_MIN_FLOOR_SUM", 15)

    from src.agent import loop as loop_mod

    class _FakeSTM:
        completed_combats = []

    out = loop_mod._maybe_render_combat_trace(
        stm=_FakeSTM(), run_log_events=[], floor_sum=10,
    )
    assert out is None


def test_render_called_when_conditions_met(monkeypatch):
    """When enabled and floor_sum passes, renderer is invoked."""
    import config
    monkeypatch.setattr(config, "POSTRUN_COMBAT_TRACE_ENABLED", True)
    monkeypatch.setattr(config, "POSTRUN_TRACE_MIN_FLOOR_SUM", 15)
    monkeypatch.setattr(config, "POSTRUN_TRACE_MAX_ROUNDS", 30)

    from src.agent import loop as loop_mod
    from src.memory import combat_trace_renderer as ctr

    called = {"count": 0}
    def _fake_render(stm, run_log_events, *, max_rounds=30):
        called["count"] += 1
        return "RENDERED TRACE"
    monkeypatch.setattr(ctr, "render_last_two_combats", _fake_render)
    monkeypatch.setattr(loop_mod, "render_last_two_combats", _fake_render, raising=False)

    class _FakeSTM:
        completed_combats = ["c1", "c2"]

    out = loop_mod._maybe_render_combat_trace(
        stm=_FakeSTM(), run_log_events=[], floor_sum=20,
    )
    assert out == "RENDERED TRACE"
    assert called["count"] == 1
```

- [ ] **Step 2: Run the test to verify failure**

Run: `pytest tests/test_post_run_trace_wiring.py -v`
Expected: FAIL with `AttributeError: module 'src.agent.loop' has no attribute '_maybe_render_combat_trace'`.

- [ ] **Step 3: Add the helper + wire into `_post_run_hcm_extraction`**

In `src/agent/loop.py`:

(a) Add a module-level helper (place near the top of the file, after imports). If imports of `render_last_two_combats` don't exist yet, add to the top imports:

```python
from src.memory.combat_trace_renderer import render_last_two_combats
```

(b) Add the helper at module scope (above `class AgentLoop`):

```python
def _maybe_render_combat_trace(
    *,
    stm,
    run_log_events: list[dict],
    floor_sum: int,
) -> str | None:
    """Return a rendered combat trace or None when gated off.

    Gates (in order):
      1. ``config.POSTRUN_COMBAT_TRACE_ENABLED`` master switch.
      2. floor_sum threshold (``config.POSTRUN_TRACE_MIN_FLOOR_SUM``).
      3. Renderer produces a non-None string (else skip).
    """
    if not config.POSTRUN_COMBAT_TRACE_ENABLED:
        return None
    if stm is None:
        return None
    if floor_sum < config.POSTRUN_TRACE_MIN_FLOOR_SUM:
        logger.info(
            "postrun_trace: skipped (floor_sum=%d < threshold=%d)",
            floor_sum, config.POSTRUN_TRACE_MIN_FLOOR_SUM,
        )
        return None
    try:
        return render_last_two_combats(
            stm, run_log_events,
            max_rounds=config.POSTRUN_TRACE_MAX_ROUNDS,
        )
    except Exception:
        logger.warning("postrun_trace: renderer raised", exc_info=True)
        return None
```

(c) In `_post_run_hcm_extraction` (around lines 4092-4115) where `extract_card_build_memory` / `analyze_build_with_llm` are called: render the trace before build analysis and pass it through. The current code calls the extractor but not directly the LLM — find the call site that actually invokes `analyze_build_with_llm`. Looking at the flow: `extract_card_build_memory` is deterministic; there's a separate async call elsewhere that invokes `analyze_build_with_llm`. Grep for it first.

Run `grep -n "analyze_build_with_llm" src/agent/loop.py` to locate the call site. Find the `_post_run_memory_update` or similar method that does the async LLM step, and insert the trace render + pass-through right before the `analyze_build_with_llm` call.

(d) After the `analyze_build_with_llm` call, invoke Turn 2. Example insertion pattern (adapt to exact surrounding code):

```python
# Render trace ONCE; share with both turns under ephemeral cache.
stm = self._hcm_short_term()
run_log_events = self._read_run_log_events() if hasattr(self, "_read_run_log_events") else []
recent = list(stm.completed_combats[-2:]) if stm else []
floor_sum = sum(getattr(c, "floor", 0) for c in recent)
combat_trace_text = _maybe_render_combat_trace(
    stm=stm, run_log_events=run_log_events, floor_sum=floor_sum,
)
if combat_trace_text:
    logger.info(
        "postrun_trace: rendered %d combats, %d chars",
        len(recent), len(combat_trace_text),
    )

# Turn 1 — build analysis with trace as cached prefix.
build_analysis = await analyze_build_with_llm(
    evidence, combat_trace_text=combat_trace_text,
)

# Turn 2 — card note updates sharing the cache.
if combat_trace_text and self._memory and self._memory.card_memory_store:
    from src.memory.card_note_updater import update_card_notes_from_traces
    from src.memory.combat_trace_renderer import extract_candidate_cards
    candidates = extract_candidate_cards(recent)
    if candidates:
        dry = not config.POSTRUN_NOTE_UPDATE_ENABLED
        try:
            await update_card_notes_from_traces(
                store=self._memory.card_memory_store,
                character=character,
                combat_trace_text=combat_trace_text,
                candidate_cards=candidates,
                run_id=run_id,
                dry_run=dry,
            )
        except Exception:
            logger.warning("postrun_trace: Turn 2 failed", exc_info=True)
```

NOTE: If `_read_run_log_events` does not exist on AgentLoop, add a minimal helper that reads the current run's JSONL file. Grep existing postrun for how run_log_events is obtained for `core_engine_extractor` and reuse that path. If core_engine does `self._session_logger.read_run_events()`, use the same API.

Grep first: `grep -n "run_log_events\|read_events\|read_run_events\|session_logger\." src/agent/loop.py | head -30`. Use whatever the existing core-engine postrun uses — do not invent a new reader.

- [ ] **Step 4: Run the integration test to verify it passes**

Run: `pytest tests/test_post_run_trace_wiring.py -v`
Expected: 3 PASSED.

- [ ] **Step 5: Run the broader postrun test suite for regressions**

Run: `pytest tests/ -k "post_run or postrun" -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/agent/loop.py tests/test_post_run_trace_wiring.py
git commit -m "feat(postrun): wire combat trace into build_analysis + card_note_updater"
```

---

## Task 9: Live smoke run (observation mode)

**Files:** none — operational check.

- [ ] **Step 1: Run a short live run with NOTE_UPDATE_ENABLED=false (default)**

```bash
STS2_POSTRUN_COMBAT_TRACE_ENABLED=true python -m scripts.run_agent --steps 120 --runs 1
```

Watch the log for:
- `postrun_trace: rendered N combats, M chars` — trace was produced
- `card_note_updater: LLM call ...ms, ... tokens` — Turn 2 ran
- `postrun_trace: turn2 proposals written=0 kept_unchanged=... invalid=... (dry_run=True)` — dry-run logged proposals without writing

Expected: zero exceptions, non-zero trace char count, non-empty proposals logged in dry-run mode, CardMemoryStore file unchanged (diff with HEAD).

- [ ] **Step 2: Inspect dry-run proposal lines**

Filter the log for `card_note_updater[DRY_RUN]` lines and eyeball quality. Proposals must:
- Name only cards that actually appeared in the combats
- Be ≤ 200 chars
- Contain a citation referencing a concrete round

- [ ] **Step 3: Flip write gate if dry-run quality is acceptable across ≥3 runs**

```bash
# In .env or shell
export STS2_POSTRUN_NOTE_UPDATE_ENABLED=true
python -m scripts.run_agent --steps 120 --runs 1
```

Check the CardMemoryStore JSON file diff — note_history entries should appear for cards the LLM updated.

---

## Self-review

**Spec coverage:**
- §2 in-scope: renderer (Task 5) ✓, Turn 1 extension (Task 6) ✓, Turn 2 module (Task 7) ✓, `note_history` (Task 3) ✓, config gates (Task 1) ✓.
- §2 out-of-scope: observation tuples untouched ✓, no auto-rollback tool ✓, no seed protection ✓.
- §3.3 session_logger enrichment (upgraded / star_cost / card_type / enchantment_name): Task 2 ✓.
- §3.4 Turn 1 prompt append: Task 6 prompt prefix injection ✓.
- §3.5 Turn 2 contract (system prompt, candidate table, validation rules, write path): Task 7 ✓.
- §3.6 floor-sum gate: Task 8 `_maybe_render_combat_trace` ✓.
- §4 config: Task 1 four env vars ✓.
- §5 caching: Task 4 `user_cached_prefix` ✓; shared trace string passed through both turns in Task 8 ✓.
- §6 error handling: wrapped in try/except + logging at every layer (renderer, Turn 2 LLM call, write path, postrun wiring) ✓.
- §7 observability: `postrun_trace: rendered ...`, `turn2 proposals written=... kept_unchanged=... invalid=... (dry_run=...)` log lines present ✓.
- §8 tests: renderer tests (Task 5), note_updater tests (Task 7), note_history tests (Task 3), session_logger tests (Task 2), wiring tests (Task 8) ✓.
- §9 risks: mitigations live in Task 8 (single-call render, shared string) and Task 9 (two-stage rollout).

**Placeholder scan:** no TBD/TODO; every code block is concrete. Task 8 has one "grep first" instruction for locating the exact call site — this is necessary investigation, not a placeholder. The prompt in Task 7 is fully written.

**Type consistency:** `CardMemory.with_new_note` signature matches across Task 3 (definition), Task 7 (usage in `apply_note_updates`). `call_raw` `user_cached_prefix` kwarg matches across Task 4 (definition), Task 6 (usage in `analyze_build_with_llm`), Task 7 (usage in `update_card_notes_from_traces`). `render_last_two_combats(stm, run_log_events, *, max_rounds=30)` signature matches across Task 5 (definition) and Task 8 (call in `_maybe_render_combat_trace`). `extract_candidate_cards` accepts both CombatTracker and dict form — Task 5 tests both, Task 8 passes real trackers.

**Conventions:** TDD (test first, verify failure, implement, verify pass), one commit per task, exact paths given throughout, no speculative features beyond spec scope.
