# Seed Stub Self-Evolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Mode B of the 4-condition ablation: 5 character-parametric seed stubs that the agent self-fills via postrun, replacing expert seeds with agent-written principles.

**Architecture:** Stubs are JSON templates instantiated per-character at startup with `pending_fill` status. After every postrun, a new pipeline stage selects 1-3 representative runs (current + recent_win + recent_loss), renders evidence (combat replays for combat/boss stubs; trajectory + Attribution Summary for deckbuilding/map/intermission stubs), calls the LLM with a no-leakage scaffold prompt, parses the response into principles, runs warn-only validators, and persists. Stub IDs use `stub_*` namespace; write_gate guards prevent other postrun stages from corrupting them.

**Tech Stack:** Python 3.14, pytest 9, existing `SkillLibrary` / `WriteGate` / evolution backend (Gemini 3.1 Pro / GPT-5.4 fallback).

**Spec:** [docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md](../specs/2026-05-03-seed-stub-self-evolution-design.md)

---

## File Structure

### New files

| Path | Responsibility |
|------|----------------|
| `src/skills/seeds_stubs/combat.template.json` | Combat stub template |
| `src/skills/seeds_stubs/boss.template.json` | Boss stub template |
| `src/skills/seeds_stubs/deckbuilding.template.json` | Deckbuilding stub template |
| `src/skills/seeds_stubs/map.template.json` | Map stub template |
| `src/skills/seeds_stubs/intermission.template.json` | Rest+Event stub template |
| `src/skills/stub_template.py` | Template loading + character substitution |
| `src/skills/stub_validators.py` | 7 warn-only validators |
| `src/skills/stub_evidence.py` | Run selection + combat replay sampling + trajectory rendering + Attribution Summary |
| `src/skills/stub_filler.py` | Fill orchestration: build evidence → render prompt → call LLM → parse → validate → persist |
| `src/skills/stub_prompts.py` | Fill / update prompt assembly (Parts A/B/C/D) |
| `tests/test_stub_template.py` | Template substitution tests |
| `tests/test_stub_library_retrieval.py` | Library skip-pending-fill tests |
| `tests/test_stub_write_gate_isolation.py` | Write gate isolation tests |
| `tests/test_stub_validators.py` | Validator tests |
| `tests/test_stub_evidence.py` | Evidence rendering tests |
| `tests/test_stub_filler.py` | Filler integration test (mock backend) |

### Modified files

| Path | Change |
|------|--------|
| `src/skills/models.py` | Add `scaffold` field + `pending_fill` to status enum |
| `src/skills/library.py` | Add `load_seed_stubs()`, `query()` skips `pending_fill` |
| `src/skills/write_gate.py` | Reject ADD with `stub_*` prefix; reject UPDATE/MERGE on `stub`/`stub_filled` source |
| `src/agent/loop.py` | New `_post_run_fill_stubs()` helper, called from `_safe_post_run` between stage 4 and 6 |
| `config.py` | Add `SEED_STUB_FILL_ENABLED`, `USE_SEED_STUBS`, `STM_ENABLED` env vars |
| `scripts/run_ablation.py` | Reconcile condition names; add Mode B condition |

---

## Task 1: Extend Skill model for stubs

**Files:**
- Modify: `src/skills/models.py`
- Test: `tests/test_stub_template.py` (new file)

- [ ] **Step 1: Read existing Skill dataclass** to understand current fields:
  Run: `grep -n "class Skill\b" AgenticSTS/src/skills/models.py`

- [ ] **Step 2: Write failing test for new scaffold field**

```python
# tests/test_stub_template.py
import pytest
from src.skills.models import Skill, SkillTrigger


def test_skill_accepts_scaffold_field():
    """Skill model must accept a scaffold dict (used by stubs)."""
    skill = Skill(
        skill_id="stub_the_silent_combat",
        name="The Silent - Combat Principles",
        category="combat",
        trigger=SkillTrigger(
            state_types=frozenset(["monster", "elite"]),
            character=frozenset(["the silent"]),
        ),
        content="TBD",
        source="stub",
        status="pending_fill",
        scaffold={
            "topic": "combat principles",
            "scope": "Generalizable principles...",
            "dimensions_to_consider": ["energy", "intent"],
            "out_of_scope": ["per-enemy"],
            "format_constraints": {"token_budget": "400-700"},
            "leakage_guard": {"max_distinct_card_names": 8},
        },
    )
    assert skill.scaffold["topic"] == "combat principles"
    assert skill.status == "pending_fill"
    assert skill.source == "stub"
```

- [ ] **Step 3: Run test — expect failure (scaffold field doesn't exist)**

Run: `python -m pytest tests/test_stub_template.py::test_skill_accepts_scaffold_field -v`
Expected: FAIL — `Skill.__init__() got an unexpected keyword argument 'scaffold'`

- [ ] **Step 4: Add `scaffold` field to Skill dataclass**

In `src/skills/models.py`, find the `@dataclass class Skill` definition (search for `class Skill` near the top after `SkillTrigger`). Add the field with default empty dict, and ensure `pending_fill` is documented as a valid status:

```python
@dataclass(frozen=True)
class Skill:
    # ... existing fields ...
    scaffold: dict = field(default_factory=dict)  # Stub metadata (topic/scope/dims/...). Empty for non-stubs.
    # status field already exists; add 'pending_fill' to its valid values
    # in any docstring/enum
```

Update `Skill.from_dict` and `Skill.to_dict` to round-trip `scaffold`:

```python
def to_dict(self) -> dict:
    d = {...existing...}
    if self.scaffold:
        d["scaffold"] = self.scaffold
    return d

@classmethod
def from_dict(cls, d: dict) -> Skill:
    return cls(
        ...existing...,
        scaffold=d.get("scaffold", {}),
    )
```

- [ ] **Step 5: Run test — expect pass**

Run: `python -m pytest tests/test_stub_template.py::test_skill_accepts_scaffold_field -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/skills/models.py tests/test_stub_template.py
git commit -m "feat(skills): add scaffold field + pending_fill status for stubs"
```

---

## Task 2: Stub template character substitution

**Files:**
- Create: `src/skills/stub_template.py`
- Test: `tests/test_stub_template.py` (extend)

- [ ] **Step 1: Write failing test for substitution**

Append to `tests/test_stub_template.py`:

```python
def test_substitute_character_in_template():
    """Template strings with {character_id}, {character}, {character_name} placeholders
    must substitute cleanly for any character."""
    from src.skills.stub_template import substitute_character

    template = {
        "skill_id_template": "stub_{character_id}_combat",
        "name_template": "{character_name} - Combat Principles",
        "trigger": {
            "state_types": ["monster"],
            "character": ["{character}"],
        },
    }
    result = substitute_character(template, character="the silent")
    assert result["skill_id"] == "stub_the_silent_combat"
    assert result["name"] == "The Silent - Combat Principles"
    assert result["trigger"]["character"] == ["the silent"]


def test_substitute_handles_multi_word_character():
    """Multi-word character names normalize: spaces -> underscores in id, title case in name."""
    from src.skills.stub_template import substitute_character

    template = {
        "skill_id_template": "stub_{character_id}_boss",
        "name_template": "{character_name} - Boss Strategy",
        "trigger": {"character": ["{character}"]},
    }
    result = substitute_character(template, character="the regent")
    assert result["skill_id"] == "stub_the_regent_boss"
    assert result["name"] == "The Regent - Boss Strategy"
```

- [ ] **Step 2: Run tests — expect failure (module doesn't exist)**

Run: `python -m pytest tests/test_stub_template.py -v`
Expected: FAIL — `ModuleNotFoundError: src.skills.stub_template`

- [ ] **Step 3: Implement substitution module**

Create `src/skills/stub_template.py`:

```python
"""Stub template loading and character substitution.

Templates live in src/skills/seeds_stubs/*.template.json with placeholders
{character}, {character_id}, {character_name}. At Mode B startup these are
instantiated per active character.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_id(character: str) -> str:
    """e.g. 'the silent' -> 'the_silent'"""
    return character.lower().strip().replace(" ", "_")


def _normalize_name(character: str) -> str:
    """e.g. 'the silent' -> 'The Silent'"""
    return " ".join(w.capitalize() for w in character.lower().strip().split())


def _substitute_in(value: Any, mapping: dict[str, str]) -> Any:
    """Recursively substitute {placeholder} tokens in strings."""
    if isinstance(value, str):
        out = value
        for k, v in mapping.items():
            out = out.replace(f"{{{k}}}", v)
        return out
    if isinstance(value, list):
        return [_substitute_in(x, mapping) for x in value]
    if isinstance(value, dict):
        return {k: _substitute_in(v, mapping) for k, v in value.items()}
    return value


def substitute_character(template: dict, character: str) -> dict:
    """Instantiate a stub template for a specific character.

    Replaces {character}, {character_id}, {character_name} placeholders in all
    string fields recursively. Renames `*_template` keys to non-suffixed
    final keys (e.g. skill_id_template -> skill_id).
    """
    mapping = {
        "character": character.lower().strip(),
        "character_id": _normalize_id(character),
        "character_name": _normalize_name(character),
    }
    substituted = _substitute_in(template, mapping)

    # Rename *_template keys to final keys
    renamed: dict = {}
    for k, v in substituted.items():
        if k.endswith("_template"):
            renamed[k[: -len("_template")]] = v
        else:
            renamed[k] = v
    return renamed


def load_stub_templates(stub_dir: Path) -> list[dict]:
    """Read all *.template.json files from a directory."""
    templates: list[dict] = []
    if not stub_dir.exists():
        return templates
    for path in sorted(stub_dir.glob("*.template.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                templates.append(json.load(f))
        except Exception as exc:
            logger.warning("Failed to load stub template %s: %s", path, exc)
    return templates
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_template.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/skills/stub_template.py tests/test_stub_template.py
git commit -m "feat(skills): stub template loader + character substitution"
```

---

## Task 3: Create 5 stub template JSON files

**Files:**
- Create: `src/skills/seeds_stubs/combat.template.json`
- Create: `src/skills/seeds_stubs/boss.template.json`
- Create: `src/skills/seeds_stubs/deckbuilding.template.json`
- Create: `src/skills/seeds_stubs/map.template.json`
- Create: `src/skills/seeds_stubs/intermission.template.json`
- Test: `tests/test_stub_template.py` (extend)

- [ ] **Step 1: Write failing test verifying 5 templates load and instantiate**

Append to `tests/test_stub_template.py`:

```python
def test_all_5_stub_templates_load_for_silent():
    """Sanity check: 5 templates exist, all instantiate cleanly for 'the silent'."""
    from pathlib import Path
    from src.skills.stub_template import load_stub_templates, substitute_character

    stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
    templates = load_stub_templates(stub_dir)
    assert len(templates) == 5, f"Expected 5 templates, got {len(templates)}"

    expected_ids = {
        "stub_the_silent_combat",
        "stub_the_silent_boss",
        "stub_the_silent_deckbuilding",
        "stub_the_silent_map",
        "stub_the_silent_intermission",
    }
    actual_ids = set()
    for t in templates:
        instance = substitute_character(t, character="the silent")
        actual_ids.add(instance["skill_id"])
        assert instance["status"] == "pending_fill"
        assert instance["source"] == "stub"
        assert instance["content"].startswith("TBD")
        assert "scaffold" in instance
        assert "dimensions_to_consider" in instance["scaffold"]
        assert "leakage_guard" in instance["scaffold"]
    assert actual_ids == expected_ids
```

- [ ] **Step 2: Run test — expect failure (no templates)**

Run: `python -m pytest tests/test_stub_template.py::test_all_5_stub_templates_load_for_silent -v`
Expected: FAIL — assertion `len(templates) == 5`

- [ ] **Step 3: Create combat template**

Create `src/skills/seeds_stubs/combat.template.json`:

```json
{
  "skill_id_template": "stub_{character_id}_combat",
  "name_template": "{character_name} - Combat Principles",
  "category": "combat",
  "tier": "general",
  "trigger": {
    "state_types": ["monster", "elite", "hand_select"],
    "character": ["{character}"]
  },
  "source": "stub",
  "status": "pending_fill",
  "scaffold": {
    "topic": "Strategic approach to non-boss combat for this character",
    "scope": "Generalizable principles applying to MOST hallway and elite encounters, regardless of the specific enemy.",
    "dimensions_to_consider": [
      "How to allocate energy each turn (offense / defense / setup)",
      "How to read enemy intents and react to multi-enemy boards",
      "HP loss MINIMIZATION across the run — every point lost is a point the boss might end you with. What lines reliably hit 0 damage taken? When is taking 1-3 damage acceptable?",
      "Card sequencing within a turn (which card types resolve first)",
      "When to spend potions in non-boss combat",
      "How character-specific tempo levers work (free plays, discard, etc.)"
    ],
    "out_of_scope": [
      "Per-enemy mechanics (round triggers, threshold patterns) -> belongs in combat_guides",
      "Per-card play recipes or specific combos -> belongs in card_memory notes",
      "Specific numerical thresholds tied to one situation"
    ],
    "format_constraints": {
      "token_budget": "400-700 tokens",
      "structure": "5-8 numbered principles. Each = one imperative declarative sentence + one short concrete example demonstrating application.",
      "voice": "Imperative, second-person, not descriptive."
    },
    "leakage_guard": {
      "max_distinct_card_names": 8,
      "max_distinct_enemy_names": 3,
      "no_specific_damage_thresholds": true
    }
  },
  "content": "TBD — filled by Mode B postrun",
  "version": 0,
  "confidence": 0.5,
  "priority": 90
}
```

- [ ] **Step 4: Create boss template**

Create `src/skills/seeds_stubs/boss.template.json`:

```json
{
  "skill_id_template": "stub_{character_id}_boss",
  "name_template": "{character_name} - Boss Strategy",
  "category": "boss",
  "tier": "general",
  "trigger": {
    "state_types": ["boss"],
    "character": ["{character}"]
  },
  "source": "stub",
  "status": "pending_fill",
  "scaffold": {
    "topic": "Strategic approach to boss fights for this character",
    "scope": "Principles for act-ending boss encounters, where HP fully restores between acts.",
    "dimensions_to_consider": [
      "Why boss combat is fundamentally different — defense alone loses (boss scaling outpaces sustained block). The agent MUST kill the boss; running out the clock is not a viable strategy.",
      "How HP and potion philosophy invert vs hallway combat",
      "Front-loaded burst vs scaling commitment trade-offs",
      "When to commit to a Power card vs continue applying pressure",
      "How to recognize when the current build cannot kill the boss in time and what to do (potions, all-in, etc.)"
    ],
    "out_of_scope": [
      "Per-boss mechanics or specific phase counters -> belongs in combat_guides",
      "Specific Power-card play orders -> belongs in card_memory",
      "Specific HP / damage thresholds tied to one boss"
    ],
    "format_constraints": {
      "token_budget": "300-600 tokens",
      "structure": "4-7 numbered principles. Each = one imperative declarative sentence + one short concrete example.",
      "voice": "Imperative, second-person."
    },
    "leakage_guard": {
      "max_distinct_card_names": 6,
      "max_distinct_enemy_names": 3,
      "no_specific_damage_thresholds": true
    }
  },
  "content": "TBD — filled by Mode B postrun",
  "version": 0,
  "confidence": 0.5,
  "priority": 92
}
```

- [ ] **Step 5: Create deckbuilding template**

Create `src/skills/seeds_stubs/deckbuilding.template.json`:

```json
{
  "skill_id_template": "stub_{character_id}_deckbuilding",
  "name_template": "{character_name} - Deckbuilding Principles",
  "category": "deck_building",
  "tier": "general",
  "trigger": {
    "state_types": ["card_reward", "card_select", "shop", "treasure", "relic_select"],
    "character": ["{character}"]
  },
  "source": "stub",
  "status": "pending_fill",
  "scaffold": {
    "topic": "How this character evaluates card and deck choices",
    "scope": "Principles for adding, removing, and upgrading cards across the run; relic and shop decisions.",
    "dimensions_to_consider": [
      "What dimensions of card value matter most for this character",
      "Archetype commitment vs flexibility — when to commit to a build, when to stay open",
      "Card removal priority and timing",
      "Shop budgeting and gold allocation",
      "When to skip rather than pick"
    ],
    "out_of_scope": [
      "Specific card tier lists — belongs in card_memory notes",
      "Specific archetype recipes — belongs in deck_guides",
      "Specific gold thresholds tied to one shop visit"
    ],
    "format_constraints": {
      "token_budget": "400-700 tokens",
      "structure": "5-8 numbered principles, each one imperative sentence + concrete example.",
      "voice": "Imperative, second-person."
    },
    "leakage_guard": {
      "max_distinct_card_names": 8,
      "max_distinct_enemy_names": 2,
      "no_specific_damage_thresholds": true
    }
  },
  "content": "TBD — filled by Mode B postrun",
  "version": 0,
  "confidence": 0.5,
  "priority": 88
}
```

- [ ] **Step 6: Create map template**

Create `src/skills/seeds_stubs/map.template.json`:

```json
{
  "skill_id_template": "stub_{character_id}_map",
  "name_template": "{character_name} - Path Selection",
  "category": "map",
  "tier": "general",
  "trigger": {
    "state_types": ["map"],
    "character": ["{character}"]
  },
  "source": "stub",
  "status": "pending_fill",
  "scaffold": {
    "topic": "How this character selects between map nodes",
    "scope": "Forward-looking path selection given current run state.",
    "dimensions_to_consider": [
      "Node priority hierarchy for this character",
      "How HP buffer should adjust path choice",
      "Boss-distance routing (when to start prioritizing rest, removal, or scaling)",
      "Shop and rest pacing across an act"
    ],
    "out_of_scope": [
      "Per-act specific patterns — belongs in route_guides",
      "Specific HP thresholds for path choice"
    ],
    "format_constraints": {
      "token_budget": "300-600 tokens",
      "structure": "4-7 numbered principles + concrete example each.",
      "voice": "Imperative, second-person."
    },
    "leakage_guard": {
      "max_distinct_card_names": 4,
      "max_distinct_enemy_names": 3,
      "no_specific_damage_thresholds": true
    }
  },
  "content": "TBD — filled by Mode B postrun",
  "version": 0,
  "confidence": 0.5,
  "priority": 85
}
```

- [ ] **Step 7: Create intermission template**

Create `src/skills/seeds_stubs/intermission.template.json`:

```json
{
  "skill_id_template": "stub_{character_id}_intermission",
  "name_template": "{character_name} - Rest & Event Decisions",
  "category": "rest",
  "tier": "general",
  "trigger": {
    "state_types": ["rest_site", "event"],
    "character": ["{character}"]
  },
  "source": "stub",
  "status": "pending_fill",
  "scaffold": {
    "topic": "How this character makes trade-off decisions at non-combat nodes",
    "scope": "Resource investment and trade-off framing at rest sites and events.",
    "dimensions_to_consider": [
      "Rest investment trade-offs (smith vs heal vs other)",
      "Event trade-off framing (HP for relic, deck pollution for gold, etc.)",
      "Which deck gaps to fill at non-combat nodes"
    ],
    "out_of_scope": [
      "Specific event option tier lists — belongs in event_guides",
      "Per-card upgrade priorities — belongs in card_memory"
    ],
    "format_constraints": {
      "token_budget": "300-600 tokens",
      "structure": "4-7 numbered principles + concrete example each.",
      "voice": "Imperative, second-person."
    },
    "leakage_guard": {
      "max_distinct_card_names": 6,
      "max_distinct_enemy_names": 2,
      "no_specific_damage_thresholds": true
    }
  },
  "content": "TBD — filled by Mode B postrun",
  "version": 0,
  "confidence": 0.5,
  "priority": 85
}
```

- [ ] **Step 8: Run test — expect pass**

Run: `python -m pytest tests/test_stub_template.py::test_all_5_stub_templates_load_for_silent -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add src/skills/seeds_stubs/ tests/test_stub_template.py
git commit -m "feat(skills): add 5 stub templates (combat/boss/deckbuilding/map/intermission)"
```

---

## Task 4: Library `load_seed_stubs()` method

**Files:**
- Modify: `src/skills/library.py`
- Test: `tests/test_stub_library_retrieval.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_stub_library_retrieval.py`:

```python
"""Library-level tests for seed stub loading and retrieval."""

import pytest
from pathlib import Path
from src.skills.library import SkillLibrary


def test_load_seed_stubs_creates_5_pending_stubs_for_silent():
    """load_seed_stubs() reads templates and instantiates them per character."""
    lib = SkillLibrary()
    stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
    n = lib.load_seed_stubs(stub_dir, character="the silent")
    assert n == 5

    all_skills = lib.get_all()
    stub_ids = {s.skill_id for s in all_skills if s.skill_id.startswith("stub_")}
    expected = {
        "stub_the_silent_combat",
        "stub_the_silent_boss",
        "stub_the_silent_deckbuilding",
        "stub_the_silent_map",
        "stub_the_silent_intermission",
    }
    assert stub_ids == expected
    for s in all_skills:
        if s.skill_id.startswith("stub_"):
            assert s.status == "pending_fill"
            assert s.source == "stub"
```

- [ ] **Step 2: Run test — expect failure**

Run: `python -m pytest tests/test_stub_library_retrieval.py::test_load_seed_stubs_creates_5_pending_stubs_for_silent -v`
Expected: FAIL — `AttributeError: 'SkillLibrary' object has no attribute 'load_seed_stubs'`

- [ ] **Step 3: Implement `load_seed_stubs`**

Find the existing `load_seeds` method in `src/skills/library.py` (around line 438) for reference pattern. Add a new instance method:

```python
def load_seed_stubs(self, stub_dir: Path, character: str) -> int:
    """Load stub templates from stub_dir and instantiate them for `character`.

    Each template is character-substituted then converted to a Skill via
    Skill.from_dict and added to the library. Returns the count loaded.
    """
    from src.skills.stub_template import load_stub_templates, substitute_character

    templates = load_stub_templates(stub_dir)
    loaded = 0
    with self._lock:
        for tpl in templates:
            instance = substitute_character(tpl, character=character)
            skill = Skill.from_dict(instance)
            if skill.skill_id in self._skills:
                logger.debug("Stub %s already loaded, skipping", skill.skill_id)
                continue
            self._skills[skill.skill_id] = skill
            loaded += 1
    logger.info("Loaded %d seed stubs for character=%s", loaded, character)
    return loaded
```

- [ ] **Step 4: Run test — expect pass**

Run: `python -m pytest tests/test_stub_library_retrieval.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/skills/library.py tests/test_stub_library_retrieval.py
git commit -m "feat(skills): SkillLibrary.load_seed_stubs() — instantiate templates per character"
```

---

## Task 5: Library `query()` skips `pending_fill` stubs

**Files:**
- Modify: `src/skills/library.py`
- Test: `tests/test_stub_library_retrieval.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/test_stub_library_retrieval.py`:

```python
def test_query_skips_pending_fill_stubs():
    """pending_fill stubs must not appear in retrieval (don't pollute prompts with TBD)."""
    lib = SkillLibrary()
    stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
    lib.load_seed_stubs(stub_dir, character="the silent")

    # Query for combat — would normally match stub_the_silent_combat
    results = lib.query(
        state_type="monster",
        context_tags=frozenset(["the silent"]),
        limit=10,
    )
    skill_ids = {s.skill_id for s, _ in results}
    assert "stub_the_silent_combat" not in skill_ids, (
        "pending_fill stubs leaked into retrieval"
    )


def test_query_includes_active_stubs():
    """After a stub is filled (status=active), it appears in retrieval."""
    from dataclasses import replace
    lib = SkillLibrary()
    stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
    lib.load_seed_stubs(stub_dir, character="the silent")

    # Manually flip one stub to active
    combat_stub = lib.get("stub_the_silent_combat")
    assert combat_stub is not None
    activated = replace(
        combat_stub,
        status="active",
        source="stub_filled",
        content="1. Use ALL energy each turn. Example: even with 1 energy left, play a 1-cost.",
    )
    lib.put(activated)

    results = lib.query(
        state_type="monster",
        context_tags=frozenset(["the silent"]),
        limit=10,
    )
    skill_ids = {s.skill_id for s, _ in results}
    assert "stub_the_silent_combat" in skill_ids
```

- [ ] **Step 2: Run tests — expect failure (pending stubs leak through)**

Run: `python -m pytest tests/test_stub_library_retrieval.py::test_query_skips_pending_fill_stubs -v`
Expected: FAIL — stub_the_silent_combat IS in skill_ids (no skip yet)

- [ ] **Step 3: Add skip in `query()`**

In `src/skills/library.py`, find the `for skill in self._skills.values():` loop in `query()` (around line 137). Add the new skip immediately after the existing `if skill.status == "deactivated":` block:

```python
for skill in self._skills.values():
    if not skill.active:
        continue
    if skill.status == "deactivated":
        continue
    if skill.status == "pending_fill":  # ← NEW
        continue  # stub not yet filled by Mode B postrun
    # ... rest of existing logic ...
```

Also ensure the library has a `get(skill_id)` method (search for `def get(self`); add if missing):

```python
def get(self, skill_id: str) -> Skill | None:
    with self._lock:
        return self._skills.get(skill_id)
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_library_retrieval.py -v`
Expected: 3 tests pass (load + skip + active inclusion)

- [ ] **Step 5: Commit**

```bash
git add src/skills/library.py tests/test_stub_library_retrieval.py
git commit -m "feat(skills): SkillLibrary.query() skips pending_fill stubs"
```

---

## Task 6: write_gate isolation guards

**Files:**
- Modify: `src/skills/write_gate.py`
- Test: `tests/test_stub_write_gate_isolation.py` (new)

- [ ] **Step 1: Inspect current write_gate API**

Run: `grep -n "def persist\|def add\|def update\|class WriteGate\|class WriteGateResult" AgenticSTS/src/skills/write_gate.py`

- [ ] **Step 2: Write failing tests**

Create `tests/test_stub_write_gate_isolation.py`:

```python
"""Verify that mistake_discovery / self-evolution write paths cannot
modify or create stub-namespace skills.
"""
from dataclasses import replace
from pathlib import Path

import pytest

from src.skills.library import SkillLibrary
from src.skills.write_gate import WriteGate
from src.skills.models import Skill, SkillTrigger


def _new_lib_with_stubs() -> SkillLibrary:
    lib = SkillLibrary()
    stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
    lib.load_seed_stubs(stub_dir, character="the silent")
    # Promote one to active so it has source=stub_filled
    s = lib.get("stub_the_silent_combat")
    lib.put(replace(s, status="active", source="stub_filled", content="x"))
    return lib


def test_write_gate_rejects_add_with_stub_prefix():
    """Even if mistake_discovery proposes a skill named stub_*, it should be rejected."""
    lib = _new_lib_with_stubs()
    gate = WriteGate(library=lib)
    fake_skill = Skill(
        skill_id="stub_evil_attempt",
        name="Evil Attempt",
        category="combat",
        trigger=SkillTrigger(state_types=frozenset(["monster"])),
        content="...",
        source="evolved",
    )
    result = gate.persist(fake_skill, action="add")
    assert not result.accepted
    assert "stub_" in result.reason.lower() or "reserved" in result.reason.lower()


def test_write_gate_rejects_update_targeting_stub():
    """UPDATE to a stub_filled skill from outside the stub pipeline should be rejected."""
    lib = _new_lib_with_stubs()
    gate = WriteGate(library=lib)
    fake_skill = Skill(
        skill_id="stub_the_silent_combat",  # target an existing stub_filled
        name="hijack",
        category="combat",
        trigger=SkillTrigger(state_types=frozenset(["monster"])),
        content="hijacked content",
        source="evolved",
    )
    result = gate.persist(fake_skill, action="update", target_id="stub_the_silent_combat")
    assert not result.accepted
    assert "stub" in result.reason.lower()


def test_write_gate_allows_normal_add():
    """Non-stub skills add normally."""
    lib = _new_lib_with_stubs()
    gate = WriteGate(library=lib)
    fake_skill = Skill(
        skill_id="evolved_legit_skill",
        name="Legit",
        category="combat",
        trigger=SkillTrigger(state_types=frozenset(["monster"])),
        content="hp conservation: prefer no-damage line",
        source="evolved",
    )
    result = gate.persist(fake_skill, action="add")
    assert result.accepted
```

- [ ] **Step 3: Run tests — expect failure (no guards yet)**

Run: `python -m pytest tests/test_stub_write_gate_isolation.py -v`
Expected: 2 FAILs (the two reject tests; allow-test may pass or fail depending on existing API).

- [ ] **Step 4: Add guards to WriteGate.persist**

In `src/skills/write_gate.py`, find the `persist` method. At the very top of the method body (before any other logic), add:

```python
def persist(self, skill: Skill, action: str = "add", target_id: str | None = None, **kwargs) -> WriteGateResult:
    # Bug A2 / stub isolation guards (Mode B): prevent mistake_discovery and
    # self-evolution from corrupting Mode B-managed seed stubs.
    if action == "add" and skill.skill_id.startswith("stub_"):
        return WriteGateResult(
            accepted=False,
            reason="skill_id with 'stub_' prefix is reserved for the seed stub pipeline; use stub_filler instead.",
        )
    if action in ("update", "merge") and target_id:
        target = self._library.get(target_id)
        if target is not None and target.source in ("stub", "stub_filled"):
            return WriteGateResult(
                accepted=False,
                reason=f"target_id={target_id} is a seed stub managed by Mode B fill pipeline; "
                       f"write here is not allowed. Use a different skill_id.",
            )
    # ... existing persist logic ...
```

If the existing `persist` signature differs (e.g., takes a candidate object, not action/target separately), adapt to that shape — preserve the same intent.

- [ ] **Step 5: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_write_gate_isolation.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add src/skills/write_gate.py tests/test_stub_write_gate_isolation.py
git commit -m "feat(write_gate): isolate stub_* skills from mistake_discovery / self-evolution writes"
```

---

## Task 7: Stub validators (warn-only)

**Files:**
- Create: `src/skills/stub_validators.py`
- Test: `tests/test_stub_validators.py` (new)

- [ ] **Step 1: Write failing tests**

Create `tests/test_stub_validators.py`:

```python
"""Tests for warn-only stub validators."""
from src.skills.stub_validators import run_stub_validators


SCAFFOLD = {
    "format_constraints": {"token_budget": "400-700 tokens"},
    "leakage_guard": {
        "max_distinct_card_names": 8,
        "max_distinct_enemy_names": 3,
        "no_specific_damage_thresholds": True,
    },
}


def _principles(*texts):
    return [{"text": t, "example": "ex"} for t in texts]


def test_token_count_in_range_no_warning():
    parsed = {
        "principles": _principles(*[("Word " * 80)] * 5),  # ~400 tokens
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert not any("token_count" in w for w in warnings)


def test_token_count_too_low_warns():
    parsed = {"principles": _principles("Tiny."), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("token_count_out_of_range" in w for w in warnings)


def test_principle_count_too_few_warns():
    parsed = {"principles": _principles("a", "b", "c"), "confidence": 0.7}  # 3 < 5
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("principle_count_off" in w for w in warnings)


def test_principle_count_too_many_warns():
    parsed = {"principles": _principles(*list("abcdefghi")), "confidence": 0.7}  # 9 > 8
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("principle_count_off" in w for w in warnings)


def test_card_name_density_warns(monkeypatch):
    """If extracted cards exceed max_distinct_card_names, warn."""
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names",
        lambda text: ["Strike", "Defend", "Backstab", "Pinpoint", "Pounce",
                      "Footwork", "Acrobatics", "Survivor", "Cloak"],  # 9 distinct
    )
    parsed = {"principles": _principles("a"), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("card_name_density" in w for w in warnings)


def test_enemy_name_density_warns(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names",
        lambda text: ["Lagavulin", "Mecha Knight", "Slimed Berserker", "Toadpole"],  # 4 > 3
    )
    parsed = {"principles": _principles("a"), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("enemy_name_density" in w for w in warnings)


def test_specific_damage_threshold_warns():
    parsed = {
        "principles": [
            {"text": "Block 12 damage before round 4.", "example": "ex"},
        ],
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("specific_thresholds_found" in w for w in warnings)


def test_imperative_voice_warns_on_descriptive():
    parsed = {
        "principles": [
            {"text": "Energy resets each turn.", "example": "ex"},
            {"text": "HP carries between fights.", "example": "ex"},
            {"text": "Block resets every turn.", "example": "ex"},
            {"text": "Use ALL energy each turn.", "example": "ex"},
            {"text": "Read intents first.", "example": "ex"},
        ],
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("voice_check" in w for w in warnings)


def test_confidence_out_of_range_warns():
    parsed = {"principles": _principles("a", "b", "c", "d", "e"), "confidence": 0.99}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("confidence_out_of_range" in w for w in warnings)


def test_clean_input_yields_no_warnings(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names",
        lambda text: ["Strike", "Defend"],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names",
        lambda text: ["Lagavulin"],
    )
    parsed = {
        "principles": [
            {"text": "Use ALL energy each turn.", "example": "If 1 energy left, play a 1-cost."},
            {"text": "Read intents BEFORE deciding offense vs defense.", "example": "When the enemy buffs, use that turn for setup."},
            {"text": "Prefer the no-damage block line over a faster line.", "example": "vs Lagavulin, take the 0-damage turn."},
            {"text": "Sequence free plays first to gain tempo.", "example": "Use a free Strike before a costed skill."},
            {"text": "Save buff potions for boss fights.", "example": "Don't use Strength Potion on a hallway."},
        ],
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert warnings == [], f"Expected no warnings, got: {warnings}"
```

- [ ] **Step 2: Run tests — expect failure (module doesn't exist)**

Run: `python -m pytest tests/test_stub_validators.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement validators**

Create `src/skills/stub_validators.py`:

```python
"""Warn-only validators for filled seed stubs.

All checks emit warning strings; none reject. Warnings are accumulated in
stub._metadata.warnings for post-hoc review.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 characters (English-leaning)."""
    return max(1, len(text) // 4)


def _parse_token_range(spec: str) -> tuple[int, int]:
    """e.g. '400-700 tokens' -> (400, 700)."""
    m = re.search(r"(\d+)\s*-\s*(\d+)", spec)
    if not m:
        return (0, 10**9)
    return (int(m.group(1)), int(m.group(2)))


def _flatten_text(parsed: dict) -> str:
    """Concat all principle text+example into one searchable string."""
    parts: list[str] = []
    for p in parsed.get("principles", []):
        parts.append(p.get("text", ""))
        parts.append(p.get("example", ""))
    return " ".join(parts)


def _extract_card_names(text: str) -> list[str]:
    """Extract card names mentioned in text, using GameKnowledge card pool."""
    try:
        from src.knowledge.knowledge import GameKnowledge
        gk = GameKnowledge.instance()
        all_card_names = list(gk.all_card_names())
    except Exception:
        # Fallback: empty list if knowledge unavailable; tests can monkeypatch
        return []
    found: list[str] = []
    for name in all_card_names:
        # Word-boundary match, case-insensitive
        if re.search(rf"\b{re.escape(name)}\b", text, flags=re.IGNORECASE):
            found.append(name)
    return found


def _extract_enemy_names(text: str) -> list[str]:
    """Extract enemy names mentioned in text, using GameKnowledge monster pool."""
    try:
        from src.knowledge.knowledge import GameKnowledge
        gk = GameKnowledge.instance()
        all_enemy_names = list(gk.all_monster_names())
    except Exception:
        return []
    found: list[str] = []
    for name in all_enemy_names:
        if re.search(rf"\b{re.escape(name)}\b", text, flags=re.IGNORECASE):
            found.append(name)
    return found


def _starts_imperative(text: str) -> bool:
    """Heuristic: principle text starts with an imperative verb."""
    if not text:
        return False
    first = text.strip().split()[0].rstrip(",.!?;:").lower()
    # Common descriptive starters that indicate non-imperative voice
    descriptive_starters = {
        "energy", "hp", "block", "the", "a", "an", "this", "that",
        "your", "you", "it", "there", "every", "each",
    }
    if first in descriptive_starters:
        return False
    # Imperative verbs typically appear bare (no -s, no auxiliaries)
    return True


def run_stub_validators(parsed: dict, scaffold: dict) -> list[str]:
    """Run all warn-only validators on a parsed fill response.

    parsed: {"principles": [...], "confidence": float, ...}
    scaffold: stub.scaffold dict
    Returns list of warning strings (may be empty).
    """
    warnings: list[str] = []
    text = _flatten_text(parsed)
    principles = parsed.get("principles", [])

    # 1. Token count
    actual = _estimate_tokens(text)
    budget = scaffold.get("format_constraints", {}).get("token_budget", "0-999999")
    lo, hi = _parse_token_range(budget)
    if actual < lo or actual > hi:
        warnings.append(f"token_count_out_of_range: {actual} not in [{lo},{hi}]")

    # 2. Principle count (5-8 default)
    if not (4 <= len(principles) <= 8):  # boss/map/intermission allow 4
        warnings.append(f"principle_count_off: got {len(principles)}, want 4-8")

    # 3. Card name density
    cards = _extract_card_names(text)
    max_cards = scaffold.get("leakage_guard", {}).get("max_distinct_card_names", 8)
    if len(set(cards)) > max_cards:
        warnings.append(f"card_name_density_high: {len(set(cards))} distinct cards (max {max_cards})")

    # 4. Enemy name density
    enemies = _extract_enemy_names(text)
    max_enemies = scaffold.get("leakage_guard", {}).get("max_distinct_enemy_names", 3)
    if len(set(enemies)) > max_enemies:
        warnings.append(f"enemy_name_density_high: {len(set(enemies))} distinct enemies (max {max_enemies})")

    # 5. Specific damage thresholds
    if scaffold.get("leakage_guard", {}).get("no_specific_damage_thresholds", True):
        nums = re.findall(r"\b\d+\s+(?:damage|HP|hp|block)\b", text)
        if nums:
            warnings.append(f"specific_thresholds_found: {nums}")

    # 6. Imperative voice
    descriptive = sum(1 for p in principles if not _starts_imperative(p.get("text", "")))
    if descriptive > 2:
        warnings.append(f"voice_check: {descriptive}/{len(principles)} principles non-imperative")

    # 7. Confidence sanity
    confidence = parsed.get("confidence", 0.5)
    if not (0.3 <= confidence <= 0.95):
        warnings.append(f"confidence_out_of_range: {confidence}")

    return warnings
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_validators.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/skills/stub_validators.py tests/test_stub_validators.py
git commit -m "feat(skills): warn-only stub validators (token / count / leakage / voice / confidence)"
```

---

## Task 8: Run selection helper

**Files:**
- Create: `src/skills/stub_evidence.py`
- Test: `tests/test_stub_evidence.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_stub_evidence.py`:

```python
"""Tests for stub evidence assembly: run selection, replay sampling, trajectory."""
from dataclasses import dataclass

from src.skills.stub_evidence import select_runs_for_fill


@dataclass
class FakeRun:
    run_id: str
    outcome: str
    started_at: float


def test_select_runs_returns_only_current_for_first_run():
    history = [FakeRun("r1", "victory", 1.0)]
    selected = select_runs_for_fill(history)
    assert [r.run_id for r in selected] == ["r1"]


def test_select_runs_picks_current_plus_recent_win_plus_recent_loss():
    history = [
        FakeRun("r5", "defeat", 5.0),     # current (newest)
        FakeRun("r4", "victory", 4.0),
        FakeRun("r3", "defeat", 3.0),
        FakeRun("r2", "victory", 2.0),
        FakeRun("r1", "defeat", 1.0),
    ]
    selected = select_runs_for_fill(history)
    ids = [r.run_id for r in selected]
    assert ids[0] == "r5"  # current
    assert "r4" in ids     # most recent win (excluding current)
    assert "r3" in ids     # most recent loss (excluding current)
    assert len(selected) == 3


def test_select_runs_skips_aborts_and_interrupts():
    history = [
        FakeRun("r3", "defeat", 3.0),       # current
        FakeRun("r2", "agent_abort", 2.0),  # not a real loss
        FakeRun("r1", "interrupt", 1.0),    # not a real loss
    ]
    selected = select_runs_for_fill(history)
    # only current; no win/loss in history that qualifies
    assert [r.run_id for r in selected] == ["r3"]


def test_select_runs_includes_current_even_if_current_is_win():
    history = [
        FakeRun("r3", "victory", 3.0),
        FakeRun("r2", "defeat", 2.0),
        FakeRun("r1", "victory", 1.0),
    ]
    selected = select_runs_for_fill(history)
    ids = [r.run_id for r in selected]
    assert "r3" in ids
    assert "r2" in ids  # most recent loss
    # No "second" win needed if current is win; only loss is added
    assert len(selected) == 2
```

- [ ] **Step 2: Run tests — expect failure**

Run: `python -m pytest tests/test_stub_evidence.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Create `src/skills/stub_evidence.py` with run selection (other functions added in later tasks):

```python
"""Stub evidence assembly: run selection, replay sampling, trajectory rendering,
Attribution Summary.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)

_VALID_LOSS_OUTCOMES = ("defeat", "max_steps")


def select_runs_for_fill(history: Sequence[Any]) -> list[Any]:
    """Pick: current run + most recent win + most recent loss (1-3 runs).

    history: ordered newest-first. Each item must have .run_id and .outcome.
    """
    if not history:
        return []
    current = history[0]
    selected: list[Any] = [current]

    recent_win = next(
        (r for r in history[1:] if r.outcome == "victory" and r.run_id != current.run_id),
        None,
    )
    recent_loss = next(
        (r for r in history[1:] if r.outcome in _VALID_LOSS_OUTCOMES and r.run_id != current.run_id),
        None,
    )
    if recent_win is not None:
        selected.append(recent_win)
    if recent_loss is not None:
        selected.append(recent_loss)
    return selected
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_evidence.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/skills/stub_evidence.py tests/test_stub_evidence.py
git commit -m "feat(skills): run selection for stub fill (current + recent_win + recent_loss)"
```

---

## Task 9: Combat replay sampling

**Files:**
- Modify: `src/skills/stub_evidence.py`
- Test: `tests/test_stub_evidence.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/test_stub_evidence.py`:

```python
def test_sample_combat_replays_for_combat_stub():
    """Combat stub samples up to 2 hallway/elite combats per run."""
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    # Mock episodes per run
    episodes_by_run = {
        "r1": [
            _ep("monster", "Toadpole"),
            _ep("monster", "Crusher"),
            _ep("elite", "Lagavulin"),
            _ep("boss", "The Insatiable"),
        ],
        "r2": [
            _ep("monster", "Slimed"),
            _ep("boss", "Vantom"),
        ],
    }
    selected_run_ids = ["r1", "r2"]
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_combat",
        run_ids=selected_run_ids,
        episodes_by_run=episodes_by_run,
    )
    # Combat stub: 2 per run preferred (1 hallway + 1 elite if present)
    assert len(replays) == 3  # r1 yields 2 (monster + elite), r2 yields 1 (monster only)
    types_r1 = sorted(e.combat_type for e in replays if e.run_id == "r1")
    assert types_r1 == ["elite", "monster"]


def test_sample_combat_replays_for_boss_stub():
    """Boss stub samples ALL boss combats per run (typically 0-3)."""
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    episodes_by_run = {
        "r1": [_ep("monster", "x"), _ep("boss", "Insatiable"), _ep("boss", "Champ")],
        "r2": [_ep("monster", "y")],  # never reached boss
    }
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_boss",
        run_ids=["r1", "r2"],
        episodes_by_run=episodes_by_run,
    )
    assert len(replays) == 2  # both bosses from r1, none from r2


# ── helper for tests ─────
def _ep(combat_type: str, enemy_key: str):
    from types import SimpleNamespace
    return SimpleNamespace(
        combat_type=combat_type,
        enemy_key=enemy_key,
        run_id="",
    )
```

- [ ] **Step 2: Run tests — expect failure**

Run: `python -m pytest tests/test_stub_evidence.py::test_sample_combat_replays_for_combat_stub -v`
Expected: FAIL — function not defined

- [ ] **Step 3: Implement combat sampling**

Append to `src/skills/stub_evidence.py`:

```python
def sample_combat_replays_for_stub(
    *,
    stub_id: str,
    run_ids: list[str],
    episodes_by_run: dict[str, list[Any]],
) -> list[Any]:
    """Sample combat episodes for a combat or boss stub.

    Combat stub: per run, prefer 1 monster + 1 elite (max 2). Hand_select fights
                 are skipped (no enemy interaction at the level we want).
    Boss stub:   all boss episodes per run (typically 0-3).
    """
    is_boss_stub = stub_id.endswith("_boss")
    is_combat_stub = stub_id.endswith("_combat")
    if not (is_boss_stub or is_combat_stub):
        return []

    sampled: list[Any] = []
    for run_id in run_ids:
        eps = episodes_by_run.get(run_id, [])
        if is_boss_stub:
            picks = [e for e in eps if e.combat_type == "boss"]
            for p in picks:
                p.run_id = run_id
                sampled.append(p)
        else:
            # combat stub: max 2, prefer 1 monster + 1 elite
            monsters = [e for e in eps if e.combat_type == "monster"]
            elites = [e for e in eps if e.combat_type == "elite"]
            picked: list[Any] = []
            if monsters:
                picked.append(monsters[0])
            if elites:
                picked.append(elites[0])
            if len(picked) < 2 and len(monsters) >= 2:
                picked.append(monsters[1])
            for p in picked[:2]:
                p.run_id = run_id
                sampled.append(p)
    return sampled
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_evidence.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/skills/stub_evidence.py tests/test_stub_evidence.py
git commit -m "feat(skills): sample combat replays for combat/boss stubs (2/run + all boss)"
```

---

## Task 10: Non-combat trajectory rendering + Attribution Summary

**Files:**
- Modify: `src/skills/stub_evidence.py`
- Test: `tests/test_stub_evidence.py` (extend)

- [ ] **Step 1: Write failing test for trajectory rendering**

Append to `tests/test_stub_evidence.py`:

```python
def test_render_trajectory_for_deckbuilding_stub():
    """Trajectory: list of decisions from one run, filtered to deckbuilding state_types."""
    from src.skills.stub_evidence import render_trajectory_for_stub

    decisions = [
        _dec("F1", "card_reward", action="resolve_rewards", option_index=1,
             reasoning="Backstab is premium",
             strategic_note="Foundation: frontload damage",
             hp_before=70, hp_after=70, gold_before=0, gold_after=0,
             deck_before=12, deck_after=13, deck_change="+Backstab"),
        _dec("F2", "monster", action="play_card", reasoning="ignored",
             strategic_note="", hp_before=70, hp_after=65),
        _dec("F3", "shop", action="buy_card", option_index=0,
             reasoning="Removal is cheap here",
             strategic_note="Foundation: keep deck thin",
             hp_before=65, hp_after=65, gold_before=88, gold_after=13,
             deck_before=14, deck_after=15, deck_change="+Footwork"),
    ]
    rendered = render_trajectory_for_stub(
        stub_id="stub_the_silent_deckbuilding",
        run_id="r1",
        outcome="defeat",
        character="the silent",
        ascension=0,
        decisions=decisions,
    )
    # Should only include card_reward and shop, not monster
    assert "[F1 card_reward]" in rendered
    assert "[F3 shop]" in rendered
    assert "monster" not in rendered  # filtered out
    assert "Backstab" in rendered      # reasoning preserved
    assert "Foundation: frontload" in rendered  # strategic note preserved


def _dec(floor, state_type, **kwargs):
    from types import SimpleNamespace
    return SimpleNamespace(
        floor=floor,
        state_type=state_type,
        action=kwargs.get("action", ""),
        option_index=kwargs.get("option_index", -1),
        reasoning=kwargs.get("reasoning", ""),
        strategic_note=kwargs.get("strategic_note", ""),
        hp_before=kwargs.get("hp_before", 0),
        hp_after=kwargs.get("hp_after", 0),
        gold_before=kwargs.get("gold_before", 0),
        gold_after=kwargs.get("gold_after", 0),
        deck_before=kwargs.get("deck_before", 0),
        deck_after=kwargs.get("deck_after", 0),
        deck_change=kwargs.get("deck_change", "no change"),
    )
```

- [ ] **Step 2: Run test — expect failure**

Run: `python -m pytest tests/test_stub_evidence.py::test_render_trajectory_for_deckbuilding_stub -v`
Expected: FAIL — function not defined

- [ ] **Step 3: Implement trajectory rendering**

Append to `src/skills/stub_evidence.py`:

```python
_STUB_STATE_TYPE_FILTERS = {
    "stub_*_deckbuilding": {"card_reward", "card_select", "shop", "treasure", "relic_select"},
    "stub_*_map": {"map"},
    "stub_*_intermission": {"rest_site", "event"},
}


def _state_types_for_stub(stub_id: str) -> set[str]:
    """Look up the state_type cluster for a non-combat stub."""
    if stub_id.endswith("_deckbuilding"):
        return _STUB_STATE_TYPE_FILTERS["stub_*_deckbuilding"]
    if stub_id.endswith("_map"):
        return _STUB_STATE_TYPE_FILTERS["stub_*_map"]
    if stub_id.endswith("_intermission"):
        return _STUB_STATE_TYPE_FILTERS["stub_*_intermission"]
    return set()


def render_trajectory_for_stub(
    *,
    stub_id: str,
    run_id: str,
    outcome: str,
    character: str,
    ascension: int,
    decisions: list[Any],
) -> str:
    """Render a per-run decision trajectory for a non-combat stub.

    Filters decisions to the state_types that match this stub. Each decision
    becomes a multi-line block: floor + state_type, options, choice + reasoning,
    strategic note, HP/Gold/Deck delta.
    """
    relevant = _state_types_for_stub(stub_id)
    if not relevant:
        return ""

    label = stub_id.split("_")[-1].title()  # "deckbuilding" / "Map" / "Intermission"
    lines: list[str] = [
        f"## {label} Trajectory (run_id={run_id}, {character} A{ascension}, OUTCOME={outcome})",
    ]

    for d in decisions:
        if d.state_type not in relevant:
            continue
        block = [f"[{d.floor} {d.state_type}] HP {d.hp_before}/?  Gold {d.gold_before}  Deck {d.deck_before}"]
        block.append(f"  Action: {d.action} (option_index={d.option_index})")
        if d.reasoning:
            block.append(f"  Reasoning: \"{d.reasoning}\"")
        if d.strategic_note:
            block.append(f"  Strategic note: \"{d.strategic_note}\"")
        if d.deck_change and d.deck_change != "no change":
            block.append(f"  Deck change: {d.deck_change}")
        block.append(f"  Outcome delta: HP {d.hp_before}->{d.hp_after}, Gold {d.gold_before}->{d.gold_after}, Deck {d.deck_before}->{d.deck_after}")
        lines.append("\n".join(block))

    return "\n\n".join(lines)


def build_attribution_summary(
    *,
    run_id: str,
    final_deck: list[str],
    final_relics: list[str],
    death_cause: str,
    strategic_thread_evolution: list[tuple[str, str]],  # (floor_label, note)
    card_play_stats: dict[str, dict],  # card_name -> {plays, total_damage, total_block}
) -> str:
    """Render the deterministic Attribution Summary section.

    All inputs come from existing stores (run_history, card_memory, STM dump).
    No LLM call.
    """
    lines = ["## Attribution Summary"]

    # Most-played cards
    sorted_cards = sorted(
        card_play_stats.items(),
        key=lambda kv: kv[1].get("plays", 0),
        reverse=True,
    )
    top = sorted_cards[:5]
    most_played_strs = [
        f"{name} ({stats.get('plays', 0)} plays, dmg={stats.get('total_damage', 0)}, block={stats.get('total_block', 0)})"
        for name, stats in top
    ]
    lines.append("- Most-played cards: " + ", ".join(most_played_strs))

    unused = [name for name, st in card_play_stats.items() if st.get("plays", 0) <= 4]
    if unused:
        lines.append(f"- Cards rarely/never used (≤4 plays): {', '.join(unused[:8])}")

    if death_cause:
        lines.append(f"- Death cause: {death_cause}")

    if strategic_thread_evolution:
        thread_str = " | ".join(
            f"{floor}: \"{note[:60]}{'...' if len(note) > 60 else ''}\""
            for floor, note in strategic_thread_evolution[:6]
        )
        lines.append(f"- Strategic Thread evolution: {thread_str}")

    return "\n".join(lines)
```

- [ ] **Step 4: Add Attribution Summary test**

Append to `tests/test_stub_evidence.py`:

```python
def test_attribution_summary_renders_top_cards_and_thread():
    from src.skills.stub_evidence import build_attribution_summary

    summary = build_attribution_summary(
        run_id="r1",
        final_deck=["Strike", "Defend", "Backstab"],
        final_relics=["Burning Blood"],
        death_cause="F33 Champ unblocked R5 Strike(28)",
        strategic_thread_evolution=[("F1", "Foundation: frontload damage"), ("F12", "Committed: poison")],
        card_play_stats={
            "Backstab": {"plays": 22, "total_damage": 286, "total_block": 0},
            "Defend": {"plays": 40, "total_damage": 0, "total_block": 200},
            "Pinpoint": {"plays": 1, "total_damage": 8, "total_block": 0},
        },
    )
    assert "Most-played cards" in summary
    assert "Backstab" in summary
    assert "Pinpoint" in summary  # in unused list (1 play <= 4)
    assert "Death cause" in summary
    assert "Foundation" in summary
```

- [ ] **Step 5: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_evidence.py -v`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add src/skills/stub_evidence.py tests/test_stub_evidence.py
git commit -m "feat(skills): trajectory rendering + Attribution Summary for non-combat stubs"
```

---

## Task 11: Fill prompt assembly (Parts A/B/C/D)

**Files:**
- Create: `src/skills/stub_prompts.py`
- Test: `tests/test_stub_prompts.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_stub_prompts.py`:

```python
"""Tests for fill / update prompt assembly."""
from src.skills.stub_prompts import build_fill_prompt, build_update_prompt


SCAFFOLD = {
    "topic": "Combat principles for this character",
    "scope": "Generalizable principles for hallway and elite encounters.",
    "out_of_scope": ["Per-enemy mechanics belong in combat_guides"],
    "dimensions_to_consider": [
        "Energy allocation",
        "Intent reading",
        "HP loss MINIMIZATION",
    ],
    "format_constraints": {
        "token_budget": "400-700 tokens",
        "structure": "5-8 numbered principles + concrete example each",
        "voice": "Imperative, second-person",
    },
    "leakage_guard": {
        "max_distinct_card_names": 8,
        "max_distinct_enemy_names": 3,
    },
}


def test_fill_prompt_contains_role_topic_scope_dimensions():
    prompt = build_fill_prompt(
        scaffold=SCAFFOLD,
        state_type_cluster="non-boss combat",
        evidence="## Combat Replay 1 ...",
        is_update=False,
    )
    assert "strategy-skill author" in prompt.lower()
    assert "combat principles" in prompt.lower() or "topic" in prompt.lower()
    assert "Energy allocation" in prompt
    assert "HP loss MINIMIZATION" in prompt
    assert "## Combat Replay 1" in prompt
    assert "max_distinct_card_names: 8" in prompt
    assert "## Existing Content" not in prompt  # fill mode, no existing


def test_update_prompt_includes_existing_content_section():
    prompt = build_update_prompt(
        scaffold=SCAFFOLD,
        state_type_cluster="non-boss combat",
        evidence="## Combat Replay 1 ...",
        existing_content="1. Use ALL energy each turn.\n2. Read intents first.",
        existing_version=3,
    )
    assert "## Existing Content (v3)" in prompt
    assert "Use ALL energy each turn" in prompt
    assert "REPLACE rather than append" in prompt
```

- [ ] **Step 2: Run tests — expect failure**

Run: `python -m pytest tests/test_stub_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement prompt assembly**

Create `src/skills/stub_prompts.py`:

```python
"""Fill / update prompt assembly for seed stubs (Parts A/B/C/D)."""

from __future__ import annotations

from typing import Any


_SYSTEM_INTRO = """\
You are a strategy-skill author for an autonomous Slay the Spire 2 agent.
Your job is to write a GENERALIZED skill describing this character's
strategic principles for {state_type_cluster}.

A "skill" is the most general layer of agent knowledge:
- It describes principles applying to MOST decisions, not specific situations.
- Per-enemy mechanics belong in combat_guides (already exist).
- Per-card stats belong in card_memory (already exist).
- Per-mistake patches belong in fine-grained skills (already exist).
Your skill complements but DOES NOT duplicate these layers."""

_OUTPUT_SCHEMA = """\
Output JSON only:
{
  "principles": [
    {"text": "<imperative principle, one sentence>", "example": "<concrete example showing application>"},
    ...
  ],
  "confidence": 0.5-0.9,
  "dimensions_covered": ["dim1", "dim2", ...],
  "evidence_basis": "<one-sentence justification citing run-history patterns>"
}

Constraints:
- {structure}
- {voice}
- max_distinct_card_names: {max_cards}
- max_distinct_enemy_names: {max_enemies}
- DO NOT include specific HP thresholds or damage numbers (e.g. "Block 12 damage").
- DO NOT name cards or enemies that don't appear in your evidence."""

_UPDATE_PREFIX = """\

## Existing Content (v{version})
{existing_content}

Refine this content based on new run data. If new evidence contradicts existing
principles, REPLACE rather than append. Avoid accreting low-confidence rules
from each run. Early-run content is expected to be coarse; rewrite freely as
evidence accumulates.
"""


def _format_dimensions(dims: list[str]) -> str:
    return "\n".join(f"- {d}" for d in dims)


def _format_out_of_scope(items: list[str]) -> str:
    return "\n".join(f"- {it}" for it in items)


def _build_core(scaffold: dict, state_type_cluster: str, evidence: str) -> str:
    fc = scaffold.get("format_constraints", {})
    lg = scaffold.get("leakage_guard", {})
    return "\n\n".join([
        _SYSTEM_INTRO.format(state_type_cluster=state_type_cluster),
        f"Topic: {scaffold.get('topic', '')}",
        f"Scope: {scaffold.get('scope', '')}",
        "Out of scope:\n" + _format_out_of_scope(scaffold.get("out_of_scope", [])),
        f"Token budget: {fc.get('token_budget', '300-700 tokens')}",
        "## Evidence\n" + evidence,
        "## Cover these dimensions if your data supports them; skip if data is too thin:\n"
        + _format_dimensions(scaffold.get("dimensions_to_consider", [])),
        _OUTPUT_SCHEMA.format(
            structure=fc.get("structure", "5-8 numbered principles + example each"),
            voice=fc.get("voice", "Imperative, second-person"),
            max_cards=lg.get("max_distinct_card_names", 8),
            max_enemies=lg.get("max_distinct_enemy_names", 3),
        ),
    ])


def build_fill_prompt(
    *,
    scaffold: dict,
    state_type_cluster: str,
    evidence: str,
    is_update: bool = False,
) -> str:
    """Build the first-fill prompt (no existing content reference)."""
    return _build_core(scaffold, state_type_cluster, evidence)


def build_update_prompt(
    *,
    scaffold: dict,
    state_type_cluster: str,
    evidence: str,
    existing_content: str,
    existing_version: int,
) -> str:
    """Build the update prompt with existing content as reference."""
    core = _build_core(scaffold, state_type_cluster, evidence)
    update_clause = _UPDATE_PREFIX.format(
        version=existing_version,
        existing_content=existing_content,
    )
    return core + update_clause
```

- [ ] **Step 4: Run tests — expect pass**

Run: `python -m pytest tests/test_stub_prompts.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/skills/stub_prompts.py tests/test_stub_prompts.py
git commit -m "feat(skills): fill / update prompt assembly for seed stubs"
```

---

## Task 12: stub_filler orchestrator

**Files:**
- Create: `src/skills/stub_filler.py`
- Test: `tests/test_stub_filler.py` (new)

- [ ] **Step 1: Write failing test with mock backend**

Create `tests/test_stub_filler.py`:

```python
"""Integration tests for stub fill orchestration with a mock backend."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.skills.library import SkillLibrary
from src.skills.stub_filler import StubFiller


def _stub_lib(character: str = "the silent") -> SkillLibrary:
    lib = SkillLibrary()
    stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
    lib.load_seed_stubs(stub_dir, character=character)
    return lib


def test_filler_promotes_pending_stub_to_active_after_first_fill():
    lib = _stub_lib()
    fake_response_payload = {
        "principles": [
            {"text": "Use ALL energy each turn.", "example": "If 1 energy left, play a 1-cost."},
            {"text": "Read intents BEFORE deciding offense vs defense.", "example": "When the enemy buffs, set up."},
            {"text": "Prefer the 0-damage line over a faster line.", "example": "Take a defensive turn."},
            {"text": "Sequence free plays first.", "example": "Free Strike before a costed skill."},
            {"text": "Save buff potions for boss fights.", "example": "Don't use Strength Potion on a hallway."},
        ],
        "confidence": 0.7,
        "dimensions_covered": ["energy_allocation", "intent_reading"],
        "evidence_basis": "Cross-run pattern: low-HP runs spent energy on inefficient block.",
    }
    fake_backend = MagicMock()
    fake_backend.call.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(fake_response_payload))],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=5000, output_tokens=600),
    )

    filler = StubFiller(library=lib, backend=fake_backend)
    # Empty evidence is fine for unit test; orchestrator just calls backend with whatever
    summary = filler.fill_all_stubs(
        character="the silent",
        evidence_by_stub={s.skill_id: "## Evidence stub" for s in lib.get_all() if s.skill_id.startswith("stub_")},
    )

    assert summary["filled_count"] == 5
    for s in lib.get_all():
        if s.skill_id.startswith("stub_"):
            assert s.status == "active"
            assert s.source == "stub_filled"
            assert s.version >= 1
            assert "Use ALL energy" in s.content
```

- [ ] **Step 2: Run test — expect failure**

Run: `python -m pytest tests/test_stub_filler.py::test_filler_promotes_pending_stub_to_active_after_first_fill -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement orchestrator**

Create `src/skills/stub_filler.py`:

```python
"""Stub fill orchestration: prompt -> LLM -> parse -> validate -> persist."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import replace
from typing import Any

from src.skills.library import SkillLibrary
from src.skills.models import Skill
from src.skills.stub_prompts import build_fill_prompt, build_update_prompt
from src.skills.stub_validators import run_stub_validators

logger = logging.getLogger(__name__)


class StubFiller:
    """Fill / update Mode B seed stubs via LLM postrun call."""

    def __init__(self, library: SkillLibrary, backend: Any):
        self._library = library
        self._backend = backend

    def fill_all_stubs(
        self,
        *,
        character: str,
        evidence_by_stub: dict[str, str],
    ) -> dict[str, Any]:
        """Fill every stub for `character`. Returns summary dict for audit log."""
        stubs = [
            s for s in self._library.get_all()
            if s.skill_id.startswith("stub_") and s.trigger.character and character in s.trigger.character
        ]
        filled = 0
        skipped = 0
        warnings_by_stub: dict[str, list[str]] = {}

        for stub in stubs:
            evidence = evidence_by_stub.get(stub.skill_id, "")
            if not evidence:
                logger.info("No evidence for %s, skipping fill", stub.skill_id)
                skipped += 1
                continue

            try:
                new_skill, warnings = self._fill_one(stub, evidence)
            except Exception as exc:
                logger.warning("Fill failed for %s: %s", stub.skill_id, exc, exc_info=True)
                skipped += 1
                continue

            self._library.put(new_skill)
            warnings_by_stub[stub.skill_id] = warnings
            filled += 1

        return {
            "filled_count": filled,
            "skipped_count": skipped,
            "warnings_by_stub": warnings_by_stub,
        }

    def _fill_one(self, stub: Skill, evidence: str) -> tuple[Skill, list[str]]:
        scaffold = stub.scaffold or {}
        cluster = self._cluster_label(stub.skill_id)
        is_update = (stub.status == "active")

        if is_update:
            prompt = build_update_prompt(
                scaffold=scaffold,
                state_type_cluster=cluster,
                evidence=evidence,
                existing_content=stub.content or "",
                existing_version=stub.version,
            )
        else:
            prompt = build_fill_prompt(
                scaffold=scaffold,
                state_type_cluster=cluster,
                evidence=evidence,
            )

        response = self._backend.call(
            system="You write strategy skills for an autonomous game-playing agent.",
            messages=[{"role": "user", "content": prompt}],
        )
        text = self._extract_text(response)
        parsed = self._parse_json(text)
        if parsed is None:
            raise ValueError(f"Could not parse JSON from response: {text[:200]}")

        warnings = run_stub_validators(parsed, scaffold)
        new_content = self._render_principles_to_content(parsed.get("principles", []))

        new_metadata = dict(stub.scaffold) if stub.scaffold else {}
        # Don't put warnings into scaffold; track them separately
        new_skill = replace(
            stub,
            content=new_content,
            source="stub_filled",
            status="active",
            confidence=float(parsed.get("confidence", 0.5)),
            version=stub.version + 1,
        )
        return new_skill, warnings

    @staticmethod
    def _cluster_label(stub_id: str) -> str:
        if stub_id.endswith("_combat"):
            return "non-boss combat (hallway and elite encounters)"
        if stub_id.endswith("_boss"):
            return "boss combat (act-ending fights with HP fully restoring after)"
        if stub_id.endswith("_deckbuilding"):
            return "deck-building decisions (card_reward, shop, treasure, relic_select)"
        if stub_id.endswith("_map"):
            return "map / path-selection decisions"
        if stub_id.endswith("_intermission"):
            return "rest_site and event decisions (resource trade-offs at non-combat nodes)"
        return "<unknown cluster>"

    @staticmethod
    def _extract_text(response: Any) -> str:
        for block in getattr(response, "content", []):
            if getattr(block, "type", None) == "text":
                return block.text
        return ""

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Find the first JSON object in `text` and return it as a dict."""
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start: i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def _render_principles_to_content(principles: list[dict]) -> str:
        lines = []
        for i, p in enumerate(principles, start=1):
            lines.append(f"{i}. {p.get('text', '')}")
            if p.get("example"):
                lines.append(f"   Example: {p['example']}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run test — expect pass**

Run: `python -m pytest tests/test_stub_filler.py -v`
Expected: 1 passed

- [ ] **Step 5: Add update test**

Append to `tests/test_stub_filler.py`:

```python
def test_filler_update_passes_existing_content_to_prompt():
    """Second fill on an active stub uses build_update_prompt, includes existing content."""
    lib = _stub_lib()
    # Promote one stub to active manually
    s = lib.get("stub_the_silent_combat")
    lib.put(replace(s, status="active", source="stub_filled", content="1. Old principle.", version=1))

    captured_prompts = []
    def _capture(**kwargs):
        captured_prompts.append(kwargs["messages"][0]["content"])
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps({
                "principles": [{"text": f"P{i}", "example": "ex"} for i in range(5)],
                "confidence": 0.7,
            }))],
            stop_reason="end_turn",
        )
    fake_backend = MagicMock()
    fake_backend.call.side_effect = _capture

    filler = StubFiller(library=lib, backend=fake_backend)
    filler.fill_all_stubs(
        character="the silent",
        evidence_by_stub={"stub_the_silent_combat": "## Evidence"},
    )

    assert any("Old principle" in p for p in captured_prompts), "update prompt didn't include existing"
    assert any("Existing Content (v1)" in p for p in captured_prompts)
```

- [ ] **Step 6: Run all tests — expect pass**

Run: `python -m pytest tests/test_stub_filler.py -v`
Expected: 2 passed

- [ ] **Step 7: Commit**

```bash
git add src/skills/stub_filler.py tests/test_stub_filler.py
git commit -m "feat(skills): StubFiller orchestrator (fill + update with mock-backend tests)"
```

---

## Task 13: config.py env vars

**Files:**
- Modify: `config.py`
- Test: inline (config import test)

- [ ] **Step 1: Write failing test**

Create `tests/test_stub_config.py`:

```python
"""Verify Mode B env vars exist with correct defaults."""
import importlib
import os


def test_seed_stub_fill_enabled_default_false():
    for k in ("STS2_SEED_STUB_FILL_ENABLED", "STS2_USE_SEED_STUBS", "STS2_STM_ENABLED"):
        os.environ.pop(k, None)
    import config as _cfg
    importlib.reload(_cfg)
    assert _cfg.SEED_STUB_FILL_ENABLED is False
    assert _cfg.USE_SEED_STUBS is False
    # STM defaults true (existing default behavior preserved)
    assert _cfg.STM_ENABLED is True


def test_seed_stub_fill_enabled_can_be_toggled():
    os.environ["STS2_SEED_STUB_FILL_ENABLED"] = "true"
    os.environ["STS2_USE_SEED_STUBS"] = "true"
    os.environ["STS2_STM_ENABLED"] = "false"
    import config as _cfg
    importlib.reload(_cfg)
    try:
        assert _cfg.SEED_STUB_FILL_ENABLED is True
        assert _cfg.USE_SEED_STUBS is True
        assert _cfg.STM_ENABLED is False
    finally:
        for k in ("STS2_SEED_STUB_FILL_ENABLED", "STS2_USE_SEED_STUBS", "STS2_STM_ENABLED"):
            os.environ.pop(k, None)
```

- [ ] **Step 2: Run test — expect failure**

Run: `python -m pytest tests/test_stub_config.py -v`
Expected: FAIL — `AttributeError: module 'config' has no attribute 'SEED_STUB_FILL_ENABLED'`

- [ ] **Step 3: Add env vars in config.py**

Find the `# ── Evolution (self-authoring) ──` block in `config.py` (around line 552). After that block, add:

```python
# ── Mode B: seed stub self-evolution ──────────────────────
SEED_STUB_FILL_ENABLED = os.getenv("STS2_SEED_STUB_FILL_ENABLED", "false").lower() in ("true", "1", "yes")
USE_SEED_STUBS = os.getenv("STS2_USE_SEED_STUBS", "false").lower() in ("true", "1", "yes")
SEED_STUB_DIR = str(PROJECT_ROOT / "src/skills/seeds_stubs")
SEED_STUB_FILL_LOG = str(_paths.evolution_dir() + "/stub_fill_log.jsonl") if hasattr(_paths.evolution_dir(), '__add__') else str(Path(_paths.evolution_dir()) / "stub_fill_log.jsonl")

# ── STM toggle (for baseline / Mode A which disable Strategic Thread) ──
STM_ENABLED = os.getenv("STS2_STM_ENABLED", "true").lower() in ("true", "1", "yes")
```

(Adjust the SEED_STUB_FILL_LOG line if `_paths.evolution_dir()` already returns a Path — use `Path(...)` wrapping consistently with existing patterns nearby.)

- [ ] **Step 4: Run test — expect pass**

Run: `python -m pytest tests/test_stub_config.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_stub_config.py
git commit -m "feat(config): Mode B env vars (SEED_STUB_FILL_ENABLED, USE_SEED_STUBS, STM_ENABLED)"
```

---

## Task 14: STM gating (Strategic Thread injection skip)

**Files:**
- Modify: `src/memory/prompt_injector.py` (or wherever Strategic Thread is injected)
- Test: `tests/test_stm_gating.py` (new)

- [ ] **Step 1: Find where Strategic Thread is injected**

Run: `grep -rn "Strategic Thread\|format_strategic_thread\|_strategic_thread" AgenticSTS/src/memory/ --include="*.py" | head -10`

The injection point is in `src/memory/prompt_injector.py` (or similar). Read the function that adds the `## Strategic Thread` section.

- [ ] **Step 2: Write failing test**

Create `tests/test_stm_gating.py`:

```python
"""Verify STM_ENABLED=false suppresses Strategic Thread injection."""
import importlib
import os


def test_strategic_thread_injected_when_stm_enabled():
    os.environ.pop("STS2_STM_ENABLED", None)
    import config as _cfg
    importlib.reload(_cfg)

    from src.memory.prompt_injector import format_working_context
    # Build a minimal working context with a strategic thread note
    ctx = _make_working_context(strategic_thread=["F1: foundation plan"])
    out = format_working_context(ctx)
    assert "Strategic Thread" in out
    assert "foundation plan" in out


def test_strategic_thread_NOT_injected_when_stm_disabled():
    os.environ["STS2_STM_ENABLED"] = "false"
    try:
        import config as _cfg
        importlib.reload(_cfg)

        from src.memory.prompt_injector import format_working_context
        ctx = _make_working_context(strategic_thread=["F1: foundation plan"])
        out = format_working_context(ctx)
        assert "Strategic Thread" not in out
        assert "foundation plan" not in out
    finally:
        os.environ.pop("STS2_STM_ENABLED", None)


def _make_working_context(*, strategic_thread):
    """Helper: synthesize the WorkingContext-like object used by format_working_context.
    Adapt to actual structure when implementing."""
    from types import SimpleNamespace
    return SimpleNamespace(strategic_thread=strategic_thread)
```

- [ ] **Step 3: Run test — expect failure**

Run: `python -m pytest tests/test_stm_gating.py -v`
Expected: FAIL — strategic thread always injected.

- [ ] **Step 4: Add gating in `format_working_context`**

In the function that renders the Strategic Thread section, wrap the section emission in a config check:

```python
# At the top of format_working_context (or wherever strategic thread is rendered):
import config
# ...
if config.STM_ENABLED and ctx.strategic_thread:
    # existing code that emits "## Strategic Thread\n..."
    sections.append("## Strategic Thread\n" + "\n".join(...))
# else: skip the section entirely
```

If the helper function `_make_working_context` in the test doesn't match real `WorkingContext` shape, adapt the test fixture to match the actual class. The key assertion (Strategic Thread section absent when STM disabled) stays.

- [ ] **Step 5: Run test — expect pass**

Run: `python -m pytest tests/test_stm_gating.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/memory/prompt_injector.py tests/test_stm_gating.py
git commit -m "feat(memory): gate Strategic Thread injection by STM_ENABLED"
```

---

## Task 15: Postrun stage 5 wiring + audit log

**Files:**
- Modify: `src/agent/loop.py`
- Create: helper module if needed
- Test: integration smoke (covered by Task 17)

- [ ] **Step 1: Find `_safe_post_run` and the existing stage order**

Run: `grep -n "_safe_post_run\|mistake_discovery\|_post_run_evolution" AgenticSTS/src/agent/loop.py | head -20`

- [ ] **Step 2: Add `_post_run_fill_stubs` helper**

In `src/agent/loop.py`, add a new method on AgentLoop (place it near `_post_run_evolution`):

```python
async def _post_run_fill_stubs(self, run_id: str, character: str) -> None:
    """Postrun stage 5: fill / update Mode B seed stubs.

    Runs after mistake_discovery (stage 4), before self-evolution (stage 6).
    No-op when SEED_STUB_FILL_ENABLED is false.
    """
    if not config.SEED_STUB_FILL_ENABLED:
        return

    try:
        from src.skills.stub_evidence import (
            select_runs_for_fill,
            sample_combat_replays_for_stub,
            render_trajectory_for_stub,
            build_attribution_summary,
        )
        from src.skills.stub_filler import StubFiller
        from src.memory.combat_trace_renderer import format_combat_replay  # existing renderer
    except Exception:
        logger.warning("Stub fill imports failed; skipping stage 5", exc_info=True)
        return

    library = self._skill_library
    if library is None:
        return

    # Get character history and select runs
    history = self._run_history_store.recent(character=character, limit=30) if self._run_history_store else []
    if not history:
        logger.info("No run history for stub fill; skipping")
        return
    selected_runs = select_runs_for_fill(history)

    # Build evidence per stub
    stubs = [s for s in library.get_all() if s.skill_id.startswith("stub_")]
    evidence_by_stub: dict[str, str] = {}

    for stub in stubs:
        if stub.skill_id.endswith(("_combat", "_boss")):
            replays = sample_combat_replays_for_stub(
                stub_id=stub.skill_id,
                run_ids=[r.run_id for r in selected_runs],
                episodes_by_run=self._load_episodes_for_runs([r.run_id for r in selected_runs]),
            )
            evidence_by_stub[stub.skill_id] = "\n\n".join(
                format_combat_replay(ep) for ep in replays
            )
        else:
            # Non-combat: render trajectories
            parts = []
            for r in selected_runs:
                decisions = self._load_decisions_for_run(r.run_id)
                traj = render_trajectory_for_stub(
                    stub_id=stub.skill_id,
                    run_id=r.run_id,
                    outcome=r.outcome,
                    character=character,
                    ascension=r.actual_ascension or 0,
                    decisions=decisions,
                )
                if traj:
                    parts.append(traj)
            # Append Attribution Summary for the current run
            current = selected_runs[0]
            attribution = build_attribution_summary(
                run_id=current.run_id,
                final_deck=getattr(current, "final_deck", []),
                final_relics=getattr(current, "final_relics", []),
                death_cause=getattr(current, "death_cause", ""),
                strategic_thread_evolution=self._load_strategic_thread_for_run(current.run_id),
                card_play_stats=self._load_card_play_stats_for_run(current.run_id),
            )
            evidence_by_stub[stub.skill_id] = "\n\n".join(parts + [attribution])

    # Run filler
    filler = StubFiller(library=library, backend=self._evolution_backend)
    summary = filler.fill_all_stubs(character=character, evidence_by_stub=evidence_by_stub)

    # Audit log
    self._write_stub_fill_log(run_id=run_id, character=character, summary=summary)

    # Save library
    library.save(Path(self._skill_library_path))


def _write_stub_fill_log(self, *, run_id: str, character: str, summary: dict) -> None:
    """Append audit entry to evolution/stub_fill_log.jsonl."""
    import json
    from pathlib import Path
    log_path = Path(config.SEED_STUB_FILL_LOG)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_id": run_id,
        "character": character,
        "filled_count": summary.get("filled_count", 0),
        "skipped_count": summary.get("skipped_count", 0),
        "warnings_by_stub": summary.get("warnings_by_stub", {}),
        "timestamp": time.time(),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

The helper methods `_load_episodes_for_runs`, `_load_decisions_for_run`, `_load_strategic_thread_for_run`, `_load_card_play_stats_for_run` will need adapters that read from existing stores. Look at how other postrun stages access these — likely:
- episodes from `self._memory_manager.combat_store.get_run(run_id)` or similar
- decisions from the per-run JSONL log
- strategic_thread from STM dump
- card_play_stats from card_memory_store

If any helper doesn't exist, stub it with a TODO and a logger.warning, but ensure the orchestrator handles empty data gracefully (already does — empty evidence skips that stub).

- [ ] **Step 3: Wire into `_safe_post_run`**

Find where `_post_run_evolution` is called in `_safe_post_run`. Insert the stub fill stage **before** `_post_run_evolution`:

```python
# In _safe_post_run:
# ... existing stages 1-4 ...

# Stage 5: Mode B seed stub fill
try:
    await self._post_run_fill_stubs(run_id=current_run_id, character=current_character)
except Exception:
    logger.warning("Stage 5 (stub fill) failed", exc_info=True)
    # Don't block stage 6

# Stage 6: existing self-evolution
await self._post_run_evolution(...)
```

- [ ] **Step 4: Verify imports + syntax**

Run: `python -c "from src.agent.loop import AgentLoop; print(hasattr(AgentLoop, '_post_run_fill_stubs'))"`
Expected: `True`

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(loop): postrun stage 5 — fill_seed_stubs (Mode B only)"
```

---

## Task 16: load_seed_stubs called at agent startup (Mode B only)

**Files:**
- Modify: `src/agent/loop.py` (skill library init path)
- Test: smoke verification

- [ ] **Step 1: Find skill library init**

Run: `grep -n "_init_skill_library\|load_seeds\|SkillLibrary.load" AgenticSTS/src/agent/loop.py | head -10`

- [ ] **Step 2: Modify init to honor USE_SEED_STUBS**

In `_init_skill_library` (or equivalent — around line 2156 per spec), add a stub-loading branch:

```python
def _init_skill_library(self, character: str) -> None:
    """Initialize skill library based on Mode A/B config."""
    library = SkillLibrary()

    if config.USE_SEED_STUBS:
        # Mode B: load stubs templates only; skip expert seeds
        from pathlib import Path
        stub_dir = Path(config.SEED_STUB_DIR)
        n = library.load_seed_stubs(stub_dir, character=character)
        logger.info("Mode B: loaded %d seed stubs (skipped expert seeds)", n)
    elif not config.DISABLE_SKILL_SEEDS:
        # Mode A / full: load expert seeds as before
        # ... existing code ...
        seed_lib = SkillLibrary.load_seeds(Path(config.SEED_DIR))
        library.merge_seeds(seed_lib)

    self._skill_library = library
```

If `DISABLE_SKILL_SEEDS` doesn't exist yet as a config flag, add it (parallel to other env-gated flags):

```python
# config.py
DISABLE_SKILL_SEEDS = os.getenv("STS2_DISABLE_SKILL_SEEDS", "false").lower() in ("true", "1", "yes")
```

- [ ] **Step 3: Sanity test**

Run smoke: with `STS2_USE_SEED_STUBS=true` and `STS2_DISABLE_SKILL_SEEDS=true` set, library should contain 5 stubs only:

```bash
STS2_USE_SEED_STUBS=true STS2_DISABLE_SKILL_SEEDS=true python -c "
from pathlib import Path
import config, importlib
importlib.reload(config)
from src.skills.library import SkillLibrary
lib = SkillLibrary()
lib.load_seed_stubs(Path(config.SEED_STUB_DIR), character='the silent')
print(f'stubs loaded: {len([s for s in lib.get_all() if s.skill_id.startswith(\"stub_\")])}')"
```
Expected: `stubs loaded: 5`

- [ ] **Step 4: Commit**

```bash
git add src/agent/loop.py config.py
git commit -m "feat(loop): load seed stubs when USE_SEED_STUBS=true (Mode B init)"
```

---

## Task 17: run_ablation.py 4-condition matrix update

**Files:**
- Modify: `scripts/run_ablation.py`

- [ ] **Step 1: Inspect existing ablation conditions**

Run: `grep -n "Condition\|baseline-strict\|prompt-only\|self-evolve\|full" AgenticSTS/scripts/run_ablation.py | head -20`

- [ ] **Step 2: Add new 4 conditions**

In `scripts/run_ablation.py`, add the 4-condition definitions matching the spec table:

```python
# Mode B and friends — replaces / supplements existing condition list.
# baseline:  slim L1/L2, no seeds, no STM, no postrun
# Mode A:    full L1/L2, expert seeds, no STM, no postrun
# Mode B:    full L1/L2, agent-written stubs, full STM, postrun on
# full:      full L1/L2, expert seeds, full STM, postrun on (current production)

SPEC_CONDITIONS = [
    Condition(
        kind="baseline",
        env_overrides={
            "STS2_PROMPT_VARIANT": "baseline",
            "STS2_DISABLE_SKILL_SEEDS": "true",
            "STS2_USE_SEED_STUBS": "false",
            "STS2_SEED_STUB_FILL_ENABLED": "false",
            "STS2_MEMORY_ENABLED": "false",
            "STS2_SKILLS_ENABLED": "false",
            "STS2_STM_ENABLED": "false",
            "STS2_POSTRUN_ENABLED": "false",
        },
    ),
    Condition(
        kind="mode_a",
        env_overrides={
            "STS2_PROMPT_VARIANT": "full",
            "STS2_DISABLE_SKILL_SEEDS": "false",
            "STS2_USE_SEED_STUBS": "false",
            "STS2_SEED_STUB_FILL_ENABLED": "false",
            "STS2_MEMORY_ENABLED": "false",
            "STS2_SKILLS_ENABLED": "true",
            "STS2_STM_ENABLED": "false",
            "STS2_POSTRUN_ENABLED": "false",
        },
    ),
    Condition(
        kind="mode_b",
        env_overrides={
            "STS2_PROMPT_VARIANT": "full",
            "STS2_DISABLE_SKILL_SEEDS": "true",
            "STS2_USE_SEED_STUBS": "true",
            "STS2_SEED_STUB_FILL_ENABLED": "true",
            "STS2_MEMORY_ENABLED": "true",
            "STS2_SKILLS_ENABLED": "true",
            "STS2_STM_ENABLED": "true",
            "STS2_POSTRUN_ENABLED": "true",
        },
        analysis_eq_strategic=True,
        per_experiment_data_isolation=True,
    ),
    Condition(
        kind="full",
        env_overrides={
            "STS2_PROMPT_VARIANT": "full",
            "STS2_DISABLE_SKILL_SEEDS": "false",
            "STS2_USE_SEED_STUBS": "false",
            "STS2_SEED_STUB_FILL_ENABLED": "false",
            "STS2_MEMORY_ENABLED": "true",
            "STS2_SKILLS_ENABLED": "true",
            "STS2_STM_ENABLED": "true",
            "STS2_POSTRUN_ENABLED": "true",
        },
        analysis_eq_strategic=True,
    ),
]
```

If existing conditions (baseline-strict / prompt-only / self-evolve / full) need to coexist for backward compatibility, keep them but mark them deprecated. Add a `--use-spec-conditions` flag to switch.

- [ ] **Step 3: Smoke check**

Run: `python -m scripts.run_ablation --tag dryrun-2026-05-03 --runs-per-condition 0 --conditions mode_b --models gemini --character Silent --dry-run`
Expected: prints the 4-condition matrix without launching runs.

(If `--dry-run` doesn't exist as a flag, just verify the script imports cleanly: `python -c "import scripts.run_ablation"`.)

- [ ] **Step 4: Commit**

```bash
git add scripts/run_ablation.py
git commit -m "feat(ablation): 4-condition matrix (baseline/mode_a/mode_b/full) with stub config"
```

---

## Task 18: Single-run integration smoke

**Files:**
- Test: `tests/integration/test_mode_b_smoke.py` (new, can be skipped in CI by marker)

- [ ] **Step 1: Write integration smoke test**

Create `tests/integration/test_mode_b_smoke.py`:

```python
"""Integration smoke: with Mode B env vars and a mock LLM backend, verify that
after one postrun, the 5 stubs all transition pending_fill -> active.

This runs against fake GameStates (no real game), mocking the LLM backend so
we can assert the lifecycle end-to-end without 10+ minutes of real gameplay.
"""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.skills.library import SkillLibrary
from src.skills.stub_filler import StubFiller


@pytest.mark.integration
def test_mode_b_end_to_end_one_run():
    # Setup: load library with stubs
    lib = SkillLibrary()
    stub_dir = Path(__file__).resolve().parents[2] / "src/skills/seeds_stubs"
    lib.load_seed_stubs(stub_dir, character="the silent")

    pending_before = sum(1 for s in lib.get_all() if s.status == "pending_fill")
    assert pending_before == 5

    # Mock backend: returns a valid 5-principle JSON for every call
    payload = {
        "principles": [
            {"text": f"Principle {i}.", "example": f"Example {i}."}
            for i in range(5)
        ],
        "confidence": 0.7,
        "dimensions_covered": ["d1", "d2"],
        "evidence_basis": "Cross-run trend.",
    }
    backend = MagicMock()
    backend.call.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=5000, output_tokens=600),
    )

    # Build evidence per stub (stub-pretend strings)
    stub_ids = [s.skill_id for s in lib.get_all() if s.skill_id.startswith("stub_")]
    evidence = {sid: f"## Evidence for {sid}\n(Sample data...)" for sid in stub_ids}

    # Run filler
    filler = StubFiller(library=lib, backend=backend)
    summary = filler.fill_all_stubs(character="the silent", evidence_by_stub=evidence)

    # Verify
    assert summary["filled_count"] == 5
    pending_after = sum(1 for s in lib.get_all() if s.status == "pending_fill")
    assert pending_after == 0
    active_after = sum(1 for s in lib.get_all() if s.status == "active")
    assert active_after >= 5
    for s in lib.get_all():
        if s.skill_id.startswith("stub_"):
            assert "Principle" in s.content
            assert s.version == 1
```

- [ ] **Step 2: Run**

Run: `python -m pytest tests/integration/test_mode_b_smoke.py -v -m integration`
Expected: 1 passed

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_mode_b_smoke.py
git commit -m "test(integration): Mode B end-to-end smoke (5 stubs filled in one postrun)"
```

---

## Task 19: Live game smoke (manual)

This task is performed by the human, NOT automated by the agent.

- [ ] **Step 1: Set Mode B env vars**

```bash
export STS2_PROMPT_VARIANT=full
export STS2_DISABLE_SKILL_SEEDS=true
export STS2_USE_SEED_STUBS=true
export STS2_SEED_STUB_FILL_ENABLED=true
export STS2_MEMORY_ENABLED=true
export STS2_STM_ENABLED=true
export STS2_POSTRUN_ENABLED=true
export STS2_DATA_REPO=AgenticSTS-Data
export STS2_MACHINE_ID=mode-b-smoke
```

- [ ] **Step 2: Run a short real run**

```bash
python -m scripts.run_agent --launch-game --api-port=auto --steps 100 --runs 1 --ascension 0 --character Silent
```

- [ ] **Step 3: Verify postrun stub fill output**

```bash
tail -1 AgenticSTS-Data/evolution/stub_fill_log.jsonl
```

Expected: a JSON entry with `filled_count >= 1` and per-stub warning lists.

- [ ] **Step 4: Inspect stub content quality**

Read the actual content written into the library. Verify:
- 5 stubs all show `status="active"` and non-TBD content.
- Content reads like "principles + examples", not specific tactics.
- Warnings (if any) are intelligible (not parser noise).

If quality is low or warnings flag actual leakage (specific cards / enemies / numbers), capture findings as feedback and iterate on the scaffold's `dimensions_to_consider` field.

---

## Self-Review

Spec coverage:
- §3 Stub taxonomy: Tasks 3 (templates), 16 (loaded at startup) ✓
- §4 Schema and parameterization: Tasks 1 (model field), 2 (substitution), 3 (templates) ✓
- §5 Lifecycle: Task 5 (query skip), Task 12 (transitions in filler) ✓
- §6 Fill prompt: Tasks 11 (assembly), 12 (filler uses it) ✓
- §7 Run selection: Task 8 ✓
- §8 Triggering: Task 15 ✓
- §9 Validators: Task 7 ✓
- §10 Isolation: Task 6 (write_gate), Task 12 (filler bypasses gate), Task 15 (audit log) ✓
- §11 Configuration: Tasks 13 (env vars), 17 (run_ablation) ✓
- §12 Implementation plan: covered through tasks 1-18 ✓
- §13 Out of scope: respected (no LLM post-mortem, no expert seed refactor) ✓

Placeholder scan:
- Task 13 has a slightly fragile `SEED_STUB_FILL_LOG` construction line that depends on `_paths.evolution_dir()` return type. Engineer should adapt to actual API.
- Task 14 helper `_make_working_context` is a placeholder fixture; engineer adapts to real `WorkingContext`.
- Task 15 helpers (`_load_episodes_for_runs`, etc.) explicitly TODO'd if the methods don't already exist. This is intentional — the engineer reads existing stores and wires accordingly.

Type consistency:
- `Skill.scaffold` (Task 1) used consistently in Tasks 7, 11, 12.
- `WriteGateResult.accepted` / `.reason` consistent in Task 6.
- `select_runs_for_fill` returns list of objects with `.run_id` and `.outcome`; consistent across Tasks 8, 15.

---

**Plan complete and saved to `docs/superpowers/plans/2026-05-03-seed-stub-self-evolution.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
