# Archetype → Skill-Driven Deck Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the rigid hardcoded archetype system and replace it with agent-driven build reasoning (strategic thread), skill trigger fixes (for discovered combo skills), and a post-run card assessment + coherence scoring pipeline.

**Architecture:** Four independent layers: (1) prompt changes for build plan in strategic thread, (2) skill trigger mechanism fixes, (3) post-run LLM card assessment via CardBuildMemory, (4) coherence score metric. Plus full archetype system deletion. Layers 3+4 share a single LLM call.

**Tech Stack:** Python 3.11+, pytest, Pydantic-style frozen dataclasses, Anthropic Claude API (Opus 4.6 for post-run analysis)

**Spec:** `docs/superpowers/specs/2026-03-29-archetype-to-skill-evolution-design.md`

---

## File Map

**Create:**
- `tests/test_archetype_removal.py` — tests for Layers 2-4 + deletion verification

**Modify:**
- `src/brain/prompts/system.py` — Layer 1: strategic note rewrite
- `src/brain/prompts/reward.py` — Layer 1: build plan reference
- `src/brain/prompts/shop.py` — Layer 1: build plan reference
- `src/skills/models.py:148-152` — Layer 2a: overlap-weighted scoring
- `src/agent/loop.py:2593-2594` — Layer 2b: deck-based card matching
- `src/memory/models_v2.py:532-617` — Layers 3+4: CardBuildMemory new fields + serialization
- `src/memory/card_build_extractor.py:290-314,446-490` — Layers 3+4: LLM prompt + extraction wiring
- `src/agent/loop.py:35-38,169,755-783,927-928,1068-1069,2762-2794,2852-2873,3124,3153,4239-4250` — Deletion: archetype refs
- `src/brain/v2_engine.py:205-248` — Deletion: archetype_context param
- `src/brain/tool_executor.py:38-45,258-294` — Deletion: tracker refs + _read_guide fallback

**Delete:**
- `src/knowledge/archetype.py` (327 lines)
- `data/knowledge/guides/` (empty directory)

---

### Task 1: Layer 2a — Overlap-weighted requires_cards scoring

**Files:**
- Modify: `src/skills/models.py:148-152`
- Test: `tests/test_archetype_removal.py`

- [ ] **Step 1: Write failing tests for overlap-weighted scoring**

```python
# tests/test_archetype_removal.py
"""Tests for archetype removal: skill trigger fixes, CardBuildMemory extensions."""

from src.skills.models import Skill, SkillTrigger


# ── Layer 2a: Overlap-weighted requires_cards scoring ──


def test_requires_cards_single_match_scores_1_5():
    trigger = SkillTrigger(requires_cards=frozenset({"Catalyst", "Noxious Fumes"}))
    matched, score = trigger.matches(hand_cards=frozenset({"Catalyst", "Strike"}))
    assert matched is True
    assert score == 1.5  # 1 match: 1.5 + 0.5*(1-1) = 1.5


def test_requires_cards_two_matches_scores_2_0():
    trigger = SkillTrigger(requires_cards=frozenset({"Catalyst", "Noxious Fumes"}))
    matched, score = trigger.matches(hand_cards=frozenset({"Catalyst", "Noxious Fumes"}))
    assert matched is True
    assert score == 2.0  # 2 matches: 1.5 + 0.5*(2-1) = 2.0


def test_requires_cards_four_matches_scores_3_0():
    trigger = SkillTrigger(
        requires_cards=frozenset({"A", "B", "C", "D", "E", "F"})
    )
    matched, score = trigger.matches(hand_cards=frozenset({"A", "B", "C", "D"}))
    assert matched is True
    assert score == 3.0  # 4 matches: 1.5 + 0.5*(4-1) = 3.0


def test_requires_cards_no_match_returns_false():
    trigger = SkillTrigger(requires_cards=frozenset({"Catalyst"}))
    matched, score = trigger.matches(hand_cards=frozenset({"Strike", "Defend"}))
    assert matched is False
    assert score == 0.0


def test_requires_cards_six_matches_capped_by_diminishing_returns():
    trigger = SkillTrigger(
        requires_cards=frozenset({"A", "B", "C", "D", "E", "F"})
    )
    matched, score = trigger.matches(
        hand_cards=frozenset({"A", "B", "C", "D", "E", "F"})
    )
    assert matched is True
    assert score == 4.0  # 6 matches: 1.5 + 0.5*(6-1) = 4.0
    # Verify this doesn't eclipse enemy-specific (+2.0) by too much
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_archetype_removal.py -v -k "requires_cards"`
Expected: FAIL — scores will be flat 1.5 for all match counts > 0

- [ ] **Step 3: Implement overlap-weighted scoring**

In `src/skills/models.py`, replace lines 148-152:

```python
        # Card requirement check (overlap-weighted, diminishing returns)
        if self.requires_cards:
            overlap = self.requires_cards.intersection(hand_cards)
            if not overlap:
                return False, 0.0
            score += 1.5 + 0.5 * (len(overlap) - 1)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_archetype_removal.py -v -k "requires_cards"`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/skills/models.py tests/test_archetype_removal.py
git commit -m "feat: overlap-weighted requires_cards scoring in SkillTrigger

Diminishing returns formula: 1.5 + 0.5*(N-1) where N = matching cards.
Prevents card-heavy skills from eclipsing other match dimensions."
```

---

### Task 2: Layer 2b — Deck-based card matching for non-combat states

**Files:**
- Modify: `src/agent/loop.py:2593-2596`
- Test: `tests/test_archetype_removal.py`

- [ ] **Step 1: Write test for deck-based matching logic**

Append to `tests/test_archetype_removal.py`:

```python
# ── Layer 2b: Deck-based card matching ──


def test_deck_cards_used_for_non_combat_skill_matching():
    """Verify the matching logic: non-combat states should use deck, not hand."""
    # This tests the LOGIC, not the full agent loop integration.
    # In card_reward state, hand_cards should be populated from deck contents.
    trigger = SkillTrigger(
        state_types=frozenset({"card_reward"}),
        requires_cards=frozenset({"Catalyst", "Noxious Fumes"}),
    )
    # Simulate: deck contains Catalyst, we're in card_reward state
    deck_cards = frozenset({"Catalyst", "Strike", "Defend", "Survivor"})
    matched, score = trigger.matches(
        state_type="card_reward",
        hand_cards=deck_cards,  # deck contents passed as hand_cards
    )
    assert matched is True
    assert score >= 1.5  # state_type match + 1 card overlap
```

- [ ] **Step 2: Run test to verify it passes (tests trigger logic, not loop wiring)**

Run: `python -m pytest tests/test_archetype_removal.py -v -k "deck_cards"`
Expected: PASS (trigger matching already works, this validates the approach)

- [ ] **Step 3: Implement deck-based matching in loop.py**

In `src/agent/loop.py`, around line 2593. **IMPORTANT structural change**: The `if gs.character` block must move OUTSIDE the `if gs.is_combat` scope so character tags apply to ALL states, not just combat.

Before (lines 2593-2596, inside the try block of `_query_skills`):
```python
            if gs.is_combat and gs.combat and gs.combat.player:
                hand_cards = frozenset(c.name for c in gs.hand)
                if gs.character:
                    context_tags.add(gs.character.lower())
```

After (note: `if gs.character` is now a SEPARATE block at the same indent as `if gs.is_combat`):
```python
            if gs.is_combat and gs.combat and gs.combat.player:
                hand_cards = frozenset(c.name for c in gs.hand)
            elif gs.state_type in ("card_reward", "shop", "card_select") and gs.deck:
                hand_cards = frozenset(c.name for c in gs.deck)

            if gs.character:
                context_tags.add(gs.character.lower())
```

- [ ] **Step 4: Commit**

```bash
git add src/agent/loop.py tests/test_archetype_removal.py
git commit -m "feat: populate hand_cards from deck for non-combat skill matching

Card reward/shop/card_select states now use full deck contents for
requires_cards trigger matching. Character tag now added for all states."
```

---

### Task 3: Layers 3+4 — CardBuildMemory new fields

**Files:**
- Modify: `src/memory/models_v2.py:532-617`
- Test: `tests/test_archetype_removal.py`

- [ ] **Step 1: Write failing tests for new fields + serialization**

Append to `tests/test_archetype_removal.py`:

```python
from src.memory.models_v2 import CardBuildMemory


# ── Layers 3+4: CardBuildMemory new fields ──


def test_card_build_memory_key_cards_default_empty():
    mem = CardBuildMemory(run_id="r1")
    assert mem.key_cards == ()
    assert mem.coherence_score == 0.0
    assert mem.coherence_analysis == ""


def test_card_build_memory_key_cards_roundtrip():
    mem = CardBuildMemory(
        run_id="r1",
        character="The Silent",
        key_cards=(
            ("Noxious Fumes", "keystone", "Passive poison stacking enabled win condition"),
            ("Strike", "dead_weight", "Never contributed meaningful damage"),
        ),
        coherence_score=0.72,
        coherence_analysis="Clear poison chain but weak draw engine",
    )
    d = mem.to_dict()

    # Verify dict serialization uses named fields
    assert len(d["key_cards"]) == 2
    assert d["key_cards"][0] == {"card": "Noxious Fumes", "role": "keystone", "insight": "Passive poison stacking enabled win condition"}
    assert d["key_cards"][1]["role"] == "dead_weight"
    assert d["coherence_score"] == 0.72
    assert d["coherence_analysis"] == "Clear poison chain but weak draw engine"

    # Roundtrip
    restored = CardBuildMemory.from_dict(d)
    assert restored.key_cards == mem.key_cards
    assert restored.coherence_score == 0.72
    assert restored.coherence_analysis == "Clear poison chain but weak draw engine"


def test_card_build_memory_from_dict_missing_new_fields():
    """Old JSONL records without new fields should load gracefully."""
    d = {"run_id": "old_run", "character": "Ironclad"}
    mem = CardBuildMemory.from_dict(d)
    assert mem.key_cards == ()
    assert mem.coherence_score == 0.0
    assert mem.coherence_analysis == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_archetype_removal.py -v -k "card_build_memory"`
Expected: FAIL — CardBuildMemory has no `key_cards`, `coherence_score`, `coherence_analysis` fields

- [ ] **Step 3: Add fields to CardBuildMemory**

In `src/memory/models_v2.py`, after line 562 (`timestamp` field), add:

```python
    # ── Per-card qualitative assessment (Layer 3) ─────────────────
    key_cards: tuple[tuple[str, str, str], ...] = ()  # (card_name, role, insight)

    # ── Deck coherence metric (Layer 4) ───────────────────────────
    coherence_score: float = 0.0       # 0.0-1.0, how well cards work together
    coherence_analysis: str = ""       # 1 sentence explaining the score
```

In `to_dict()` (after the `"timestamp"` entry), add:

```python
            "key_cards": [{"card": c, "role": r, "insight": i} for c, r, i in self.key_cards],
            "coherence_score": self.coherence_score,
            "coherence_analysis": self.coherence_analysis,
```

In `from_dict()` (after the `timestamp` line), add:

```python
            key_cards=tuple(
                (kc["card"], kc["role"], kc.get("insight", ""))
                for kc in d.get("key_cards", [])
                if isinstance(kc, dict) and "card" in kc
            ),
            coherence_score=d.get("coherence_score", 0.0),
            coherence_analysis=d.get("coherence_analysis", ""),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_archetype_removal.py -v -k "card_build_memory"`
Expected: All 3 tests PASS

- [ ] **Step 5: Run existing build memory tests for regressions**

Run: `python -m pytest tests/test_build_memory.py -v`
Expected: All existing tests PASS (new fields have defaults, no breakage)

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py tests/test_archetype_removal.py
git commit -m "feat: add key_cards + coherence fields to CardBuildMemory

key_cards: per-card qualitative assessment (card, role, insight).
coherence_score: 0-1 metric for deck synergy quality.
coherence_analysis: 1-sentence explanation.
Backward-compatible: defaults to empty for old JSONL records."
```

---

### Task 4: Layers 3+4 — Extend LLM build analysis prompt + extraction

**Files:**
- Modify: `src/memory/card_build_extractor.py:290-314,446-490`

- [ ] **Step 1: Extend _BUILD_ANALYSIS_PROMPT**

In `src/memory/card_build_extractor.py`, replace the JSON schema section of `_BUILD_ANALYSIS_PROMPT` (lines 296-306). The full new prompt template:

```python
_BUILD_ANALYSIS_PROMPT = """\
Analyze this completed run and describe the deck build.

{evidence_text}

Respond with a JSON object:
{{
  "build_summary": "<1-2 sentence description of what this deck tried to do>",
  "primary_plan": "<short phrase: the main win condition or strategy, e.g. 'poison stacking', 'strength scaling', 'shiv burst', 'block stall'>",
  "damage_engine": "<what generated damage, e.g. 'Poison via Noxious Fumes + Deadly Poison' or 'Strength scaling via Demon Form + Heavy Blade'>",
  "defense_engine": "<what generated defense, e.g. 'Footwork + Backflip' or 'basic Defend cards'>",
  "cycle_engine": "<what enabled card draw/cycling, e.g. 'Backflip + Acrobatics' or 'none observed'>",
  "energy_engine": "<what generated extra energy, e.g. 'Adrenaline + Concentrate' or 'base 3 energy'>",
  "build_tags": ["<short reusable tag>", "..."],
  "weak_points": "<1 sentence: what was this deck worst at?>",
  "confidence": <0.3-0.9 float>,
  "key_cards": [
    {{"card": "<card name>", "role": "<role>", "insight": "<1 sentence why>"}}
  ],
  "coherence_score": <0.0-1.0 float>,
  "coherence_analysis": "<1 sentence: strengths and gaps in card synergy>"
}}

Guidelines:
- build_tags: 2-5 short, lowercase tags that describe this build. Free-form but reusable (e.g. "poison", "shiv", "strength", "block_stall", "thin_cycle", "discard_synergy"). Include outcome: "victory" or "defeat".
- If the run ended very early (floor < 5) or evidence is sparse, use low confidence and fewer tags.
- Be specific to what actually happened, not what the deck could theoretically do.
- For damage_engine, defense_engine, energy_engine: evidence is directly available (top damage/block/energy sources are measured per action). Base your analysis on those traceable signals.
- For cycle_engine: draw/discard events are NOT directly measured. You may infer cycle capability from card names known to draw (e.g. Backflip, Acrobatics, Battle Trance) if they appear in top_played, but mark this as inference. If unsure, write "not observed" rather than guessing.
- key_cards: List 5-8 most notable cards (both positive AND negative contributions).
  Roles: keystone, core_damage, core_defense, draw_engine, energy_engine, utility, dead_weight, bad_pick.
  "keystone": Played rarely but DEFINED the strategy (power cards, scaling enablers). A card played once that enabled 200 damage across 5 combats outranks a card played 20 times for 5 damage each.
  "dead_weight": In final deck but contributed little — should have been removed.
  "bad_pick": Taken during the run but rarely/never played. A deck building mistake.
  Base roles on TRACEABLE evidence (damage/block/power attribution), not play count alone.
- coherence_score (0.0-1.0): How well do the final deck's cards work together?
  0.0-0.3: No clear strategy, random collection. 0.4-0.6: Has direction but significant dead weight or missing pieces. 0.7-0.8: Clear strategy, mostly synergistic, minor gaps. 0.9-1.0: Tight, focused deck with every card serving the win condition.
- coherence_analysis: 1 sentence. Name specific strengths and gaps.
- Respond with ONLY the JSON object."""
```

- [ ] **Step 2: Add role validation constant**

At module level (after imports), add:

```python
_VALID_ROLES = frozenset({
    "keystone", "core_damage", "core_defense", "draw_engine",
    "energy_engine", "utility", "dead_weight", "bad_pick",
})
```

- [ ] **Step 3: Wire new fields in analyze_build_with_llm()**

In the `analyze_build_with_llm()` function, after the confidence clamping block (~line 361, `analysis["confidence"] = min(0.9, max(0.1, float(conf)))`), add:

```python
        # Validate and normalize key_cards
        raw_key_cards = analysis.get("key_cards", [])
        clean_key_cards = []
        for kc in raw_key_cards:
            if isinstance(kc, dict) and "card" in kc:
                role = kc.get("role", "utility")
                if role not in _VALID_ROLES:
                    role = "utility"
                clean_key_cards.append({
                    "card": kc["card"],
                    "role": role,
                    "insight": kc.get("insight", ""),
                })
        analysis["key_cards"] = clean_key_cards

        # Clamp coherence score
        coh = analysis.get("coherence_score", 0.0)
        analysis["coherence_score"] = min(1.0, max(0.0, float(coh)))
        analysis["coherence_analysis"] = analysis.get("coherence_analysis", "")
```

Also update the fallback dict in the `except` block to include:

```python
            "key_cards": [],
            "coherence_score": 0.0,
            "coherence_analysis": "",
```

- [ ] **Step 4: Wire fields in extract_card_build_memory()**

In `extract_card_build_memory()`, after the `confidence` extraction (~line 461), add:

```python
    key_cards = tuple(
        (kc["card"], kc["role"], kc.get("insight", ""))
        for kc in analysis.get("key_cards", [])
        if isinstance(kc, dict) and "card" in kc
    )
    coherence_score = analysis.get("coherence_score", 0.0)
    coherence_analysis = analysis.get("coherence_analysis", "")
```

Then add these to the `CardBuildMemory(...)` constructor call:

```python
        key_cards=key_cards,
        coherence_score=coherence_score,
        coherence_analysis=coherence_analysis,
```

- [ ] **Step 5: Write validation tests for key_cards extraction**

Append to `tests/test_archetype_removal.py`:

```python
from src.memory.card_build_extractor import _VALID_ROLES


# ── Layer 3+4: Validation logic ──


def test_valid_roles_constant_has_expected_values():
    assert "keystone" in _VALID_ROLES
    assert "dead_weight" in _VALID_ROLES
    assert "bad_pick" in _VALID_ROLES
    assert "core_damage" in _VALID_ROLES
    assert len(_VALID_ROLES) == 8


def test_key_cards_extraction_normalizes_invalid_roles():
    """Simulates what happens when LLM returns an unexpected role."""
    # This tests the extraction logic in extract_card_build_memory
    analysis = {
        "key_cards": [
            {"card": "Demon Form", "role": "keystone", "insight": "test"},
            {"card": "Strike", "role": "garbage_card", "insight": "bad role"},  # invalid role
            {"card": "Defend"},  # missing role and insight
            "not_a_dict",  # malformed entry
        ],
    }
    # Apply same logic as extract_card_build_memory
    key_cards = tuple(
        (kc["card"], kc["role"] if kc.get("role") in _VALID_ROLES else "utility", kc.get("insight", ""))
        for kc in analysis.get("key_cards", [])
        if isinstance(kc, dict) and "card" in kc
    )
    assert len(key_cards) == 3  # "not_a_dict" filtered out
    assert key_cards[0] == ("Demon Form", "keystone", "test")
    assert key_cards[1] == ("Strike", "utility", "bad role")  # normalized
    assert key_cards[2] == ("Defend", "utility", "")  # defaults
```

- [ ] **Step 6: Run all new + existing tests**

Run: `python -m pytest tests/test_archetype_removal.py tests/test_build_memory.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/memory/card_build_extractor.py tests/test_archetype_removal.py
git commit -m "feat: extend build analysis with key_cards + coherence score

LLM now assesses per-card importance (keystone/dead_weight/bad_pick etc.)
and deck coherence (0-1 synergy metric). Same Opus 4.6 post-run call,
~230 extra output tokens. Role validation normalizes LLM output."
```

---

### Task 5: Layer 1 — Strategic Thread build plan prompt changes

**Files:**
- Modify: `src/brain/prompts/system.py:43-49`
- Modify: `src/brain/prompts/reward.py:57-61`
- Modify: `src/brain/prompts/shop.py:100-101`

- [ ] **Step 1: Rewrite strategic note section in system.py**

In `src/brain/prompts/system.py`, replace lines 43-49:

```python
## Strategic Notes
Every decision tool includes an optional `strategic_note` field. Use it to record:
- WHY you made this choice (not what you chose — that's in the action)
- How this advances your deck's win condition
- What your deck still needs (unfilled Jobs: frontload damage, block, scaling, draw)
Keep under 25 words. This note will be shown to you in every future decision this run.
Example: "Took Noxious Fumes — scaling solved. Still need block density (currently ~20%)."
```

With:

```python
## Strategic Notes — Build Plan
Every non-combat decision tool has a `strategic_note` field. Write a RUNNING BUILD PLAN:
1. **Win condition**: How do you kill bosses? (e.g., "Poison stacking via Noxious Fumes + Catalyst burst")
2. **Key pieces**: Cards that define your build
3. **Gaps**: What's missing? (e.g., "No draw engine yet")
4. **Avoid**: What doesn't fit your win condition
Keep under 50 words. Revise when you take or skip a pivotal card. This note persists across ALL future decisions this run.
Example: "Win: Strength scaling (Demon Form). Key: Demon Form, Pummel. Gap: draw engine, need Offering/Battle Trance. Avoid: expensive non-scaling attacks."
```

- [ ] **Step 2: Add build plan reference in reward.py**

In `src/brain/prompts/reward.py`, after line 58 (`"Which dimension does your deck lack most? Does any offered card address it?"`), add:

```python
    lines.append("Review your Build Plan in the Strategic Thread. Does any card fill a gap or strengthen your win condition?")
```

- [ ] **Step 3: Add build plan reference in shop.py**

In `src/brain/prompts/shop.py`, after line 101 (`"Best purchase = biggest power spike..."`), add:

```python
    lines.append("Review your Build Plan in the Strategic Thread. Prioritize purchases that fill gaps in your win condition.")
```

- [ ] **Step 4: Commit**

```bash
git add src/brain/prompts/system.py src/brain/prompts/reward.py src/brain/prompts/shop.py
git commit -m "feat: enhance strategic note as running build plan

Guides agent to maintain win condition + key pieces + gaps + avoid.
Word limit 25→50. Card reward and shop prompts reference the build plan."
```

---

### Task 6: Delete archetype system — archetype.py + loop.py cleanup

This is the largest task. Work methodically through each reference.

**Files:**
- Delete: `src/knowledge/archetype.py`
- Delete: `data/knowledge/guides/` (if exists)
- Modify: `src/agent/loop.py` (~38 references)

- [ ] **Step 1: Run grep to inventory all archetype references**

```bash
grep -rn "archetype" src/ --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
```

Review output and confirm all references are covered by the spec.

- [ ] **Step 2: Delete archetype.py**

```bash
rm src/knowledge/archetype.py
rm -rf data/knowledge/guides/
```

- [ ] **Step 3: Clean loop.py — remove import**

Remove the import block at line 35-38:

```python
from src.knowledge.archetype import (
    ArchetypeTracker,
    load_guide,
)
```

- [ ] **Step 4: Clean loop.py — remove field declarations**

Remove/modify these field initializations in `__init__`:
- `self._archetype_tracker` → delete
- `self._character_guide` → delete
- `self._character_guide_loaded` → delete

- [ ] **Step 5: Clean loop.py — remove _ensure_character_guide()**

Delete the entire `_ensure_character_guide()` method (~lines 755-783).

- [ ] **Step 6: Clean loop.py — remove _build_archetype_context()**

Delete the entire `_build_archetype_context()` method (~lines 2852-2873).

- [ ] **Step 7: Clean loop.py — remove archetype_context from decision context**

In `_build_decision_context()` or wherever `ctx["archetype_context"]` is set (~lines 2791-2794), remove the archetype_context block.

Remove the `"archetype_context": 800` entry from the context size config dict (~line 69).

Remove all `ctx.get("archetype_context")` references in strategic_parts injection (~lines 1068-1069, 1573-1574).

Remove archetype from event emit (~line 2818).

- [ ] **Step 8: Clean loop.py — remove card tracking calls**

Remove `self._archetype_tracker.record_card_taken(c.name)` (~line 4240) and
`self._archetype_tracker.record_card_skipped()` (~line 4250).

- [ ] **Step 9: Clean loop.py — remove run reset**

Remove `self._archetype_tracker.reset()` from `reset_for_new_run()` (~lines 927-928).

- [ ] **Step 10: Clean loop.py — remove archetype from memory query**

At ~line 2764, the memory query passes `archetype=detected_archetype`. Change to `archetype=""`.

- [ ] **Step 11: Clean loop.py — remove call to _ensure_character_guide**

Find the call site where `_ensure_character_guide()` is called (character detection section) and remove it.

- [ ] **Step 12: Document archetype parameter change in retriever.py + memory_manager.py**

In `src/memory/retriever.py` (~line 81), the `query_for_decision()` method has an `archetype` parameter. Add a comment:

```python
    archetype: str = "",  # Legacy: was tracker-detected, now "" (general matching)
```

In `src/memory/memory_manager.py` (~line 82), same treatment for the `archetype` parameter.

No logic changes needed — empty string triggers general (non-archetype-filtered) retrieval, which is the desired behavior.

- [ ] **Step 13: Verify loop.py compiles**

```bash
python -c "from src.agent.loop import AgentLoop; print('OK')"
```

Expected: `OK` with no import errors.

- [ ] **Step 14: Commit**

```bash
git add -A
git commit -m "refactor: remove archetype system from agent loop

Delete archetype.py (327 lines), guides/ directory, and ~38 references
in loop.py. Agent now drives build direction via strategic thread
instead of hardcoded archetype labels."
```

---

### Task 7: Delete archetype references — v2_engine.py + tool_executor.py

**Files:**
- Modify: `src/brain/v2_engine.py:205-248`
- Modify: `src/brain/tool_executor.py:38-45,258-294`

- [ ] **Step 1: Clean v2_engine.py**

Remove `archetype_context` parameter from `decide_noncombat()` (line ~205) and `_build_noncombat_message()` or equivalent. Remove the `if archetype_context:` block that appends it to sections (~line 247-248).

- [ ] **Step 2: Clean tool_executor.py — remove tracker field**

Remove `archetype_tracker` from constructor parameter and `self._archetype_tracker` field.

- [ ] **Step 3: Clean tool_executor.py — delete _read_guide section 2**

In `_handle_read_guide()` (lines ~271-294), the archetype tracker is used to read character guide data. Delete this entire "section 2" fallback that reads `self._archetype_tracker._guide`. Keep section 1 (guide store) and section 3 (skill library fallback).

Note: `_handle_search_strategy()` does NOT reference the archetype tracker directly — the tracker reference is in `_read_guide()`.

- [ ] **Step 4: Clean tool_executor.py — remove remaining tracker refs**

Search for any remaining `self._archetype_tracker` references in the file (e.g., in `_handle_search_strategy` lines ~258-261 where detected_archetype is read for deck guide lookup). Replace with `archetype = ""` (empty string fallback).

- [ ] **Step 5: Verify imports work**

```bash
python -c "from src.brain.v2_engine import V2Engine; from src.brain.tool_executor import ToolExecutor; print('OK')"
```

- [ ] **Step 6: Commit**

```bash
git add src/brain/v2_engine.py src/brain/tool_executor.py
git commit -m "refactor: remove archetype refs from v2_engine + tool_executor

Remove archetype_context param from V2Engine.build_user_message().
Remove tracker field + _read_guide section 2 fallback from ToolExecutor."
```

---

### Task 8: Verify web_searcher.py dead code

**Files:**
- Inspect: `src/knowledge/web_searcher.py`

- [ ] **Step 1: Check for remaining callers of archetype methods**

```bash
grep -rn "search_character_guide\|search_card_ratings" src/ --include="*.py" | grep -v web_searcher.py | grep -v __pycache__
```

If no callers exist outside web_searcher.py, the methods are dead code.

- [ ] **Step 2: Mark or delete dead methods**

If no callers: delete `search_character_guide()` and `search_card_ratings()` from `web_searcher.py`. Keep `search_boss_strategy()`.

If callers exist: leave methods but add `# DEPRECATED: archetype system removed` comment.

- [ ] **Step 3: Commit**

```bash
git add src/knowledge/web_searcher.py
git commit -m "refactor: remove dead archetype methods from web_searcher

search_character_guide() and search_card_ratings() had no callers
after archetype system removal. Boss strategy search preserved."
```

---

### Task 9: Run full test suite + verify no archetype references remain

**Files:**
- Test: all existing tests

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: All tests PASS. If any test imports from `src.knowledge.archetype`, it will fail — fix by removing the import/test.

- [ ] **Step 2: Verify no archetype imports remain**

```bash
grep -rn "from src.knowledge.archetype" src/ --include="*.py" | grep -v __pycache__
grep -rn "archetype_tracker" src/ --include="*.py" | grep -v __pycache__
grep -rn "ArchetypeTracker" src/ --include="*.py" | grep -v __pycache__
```

Expected: Zero matches for all three.

- [ ] **Step 3: Verify guide_consolidator still imports cleanly**

```bash
python -c "from src.memory.guide_consolidator import GuideConsolidator; print('OK')"
```

Expected: `OK`. Guide consolidator groups by `CardBuildMemory.archetype` (populated from `primary_plan`). No code change needed but verify no hidden import of archetype.py.

- [ ] **Step 4: Verify archetype references in tests**

```bash
grep -rn "archetype" tests/ --include="*.py" | grep -v __pycache__ | grep -v test_archetype_removal
```

Fix any remaining references (likely in `test_build_memory.py` which may reference archetype field — this is fine as CardBuildMemory.archetype is kept as legacy).

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "fix: clean up remaining archetype references in tests"
```

---

### Task 10: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture diagram**

Remove `archetype.py` entry from the file listing. Add `key_cards` and `coherence_score/coherence_analysis` to the CardBuildMemory description in the models_v2.py entry.

- [ ] **Step 2: Remove archetype system from Key Technical Decisions**

Remove or significantly trim the "Web Search + Archetype System" bullet. Keep boss web search if still active. Remove all ArchetypeTracker references.

- [ ] **Step 3: Update Agent Loop Flow**

Remove "Character detection → load_guide → ArchetypeTracker" from the per-run flow. Remove "Post-execute: track card taken/skipped → update ArchetypeTracker".

- [ ] **Step 4: Update Important Patterns**

Remove "Archetype tracking", "Archetype injection", "Card select: Archetype identification" patterns. Add: "Build plan: Agent maintains running build plan via strategic_note (win condition + gaps + avoid)".

- [ ] **Step 5: Update Known Issues / Development Phases**

Remove archetype-related TODOs. Add completed phase entry for this work.

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for archetype removal + deck intelligence layers

Remove archetype system references. Document key_cards, coherence_score,
and strategic build plan mechanism."
```
