# P3/P4/P5: Skill Lifecycle + Rest Vision + Broken Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 89% skill zero-usage rate through fair competition, deduplication, retirement, and game-native replay evaluation; give rest prompts full route visibility; fix 8 broken self-evolved tools.

**Architecture:** Four-layer skill lifecycle (fair competition → trigger specificity → dedup/merge → game-native replay) + rest prompt route injection + tool test case fixes. Each layer delivers value independently. Game-native replay uses STS2's save/quit/continue API for 100%-accurate A/B testing of skill sets.

**Tech Stack:** Python 3.12, Anthropic Claude API (Sonnet/Haiku), STS2 MCP REST API (save_and_quit/continue_run)

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `src/skills/replay_evaluator.py` | Game-native boss fight replay for skill A/B testing (~120 lines) |
| `scripts/enrich_skill_triggers.py` | One-time batch LLM job to enrich 103 zero-usage skill triggers |
| `tests/test_skill_lifecycle.py` | Tests for tie-breaking, quotas, retirement, dedup |
| `tests/test_replay_evaluator.py` | Tests for replay result comparison and confidence updates |
| `tests/test_rest_route.py` | Tests for full route injection into rest prompt |

### Modified Files
| File | Changes |
|------|---------|
| `src/skills/library.py` | Tie-breaking jitter, slot quotas, `temporary_override()`, `record_replay_outcome()`, retirement sweep |
| `src/skills/models.py` | `with_update()`, `supplements_seed_id`, `status` field (active/probation/deactivated), `version` field |
| `src/skills/discovery.py` | Enhanced trigger prompt, semantic dedup before creation |
| `src/skills/composer.py` | Token budget 600→900, slots 5→7, supplementary skill display |
| `src/brain/prompts/rest.py` | `remaining_route` parameter + full route injection |
| `src/brain/evolution_engine.py` | Dedup check in `_handle_write_skill` |
| `src/brain/write_tools.py` | Trigger validation warnings |
| `src/agent/loop.py` | Store `_route_node_types`, pass to rest prompt, replay call after boss fights |
| `config.py` | `SKILLS_MAX_PER_PROMPT=7`, `SKILLS_MAX_INJECTION_TOKENS=900`, `MAX_ACTIVE_PER_CATEGORY=15` |
| `src/mcp_client/actions.py` | Remove duplicate `save_and_quit`/`continue_run` definitions |
| 8× `data/evolution/tools/*.py` | Fix TEST_CASES expected values |

---

## Task 1: P5 — Fix 8 Broken Tools

**Files:**
- Modify: `data/evolution/tools/block_sufficiency_check.py`
- Modify: `data/evolution/tools/deck_size_removal_urgency.py`
- Modify: `data/evolution/tools/dex_adjusted_block_calc.py`
- Modify: `data/evolution/tools/early_game_survival_gate.py`
- Modify: `data/evolution/tools/frail_block_calc.py`
- Modify: `data/evolution/tools/removal_session_attack_floor.py`
- Modify: `data/evolution/tools/rest_site_heal_vs_upgrade.py`
- Modify: `data/evolution/tools/silent_archetype_score.py`

These tools have correct logic but wrong TEST_CASES expected values. For each tool: read `execute()`, compute correct expected output, fix TEST_CASES.

**Known errors (from DynamicToolRegistry load):**
```
block_sufficiency_check: test 0: 'survives' expected False but got True (hp_after=6 > 0)
deck_size_removal_urgency: test 0: 'urgency_score' expected 7.1 but got 7.8
dex_adjusted_block_calc: test 1: 'deficit' expected 0 but got 4
early_game_survival_gate: test 0: 'decision' expected 'NO-GO' but got 'GO'
frail_block_calc: test 0: 'survives' expected False but got True
removal_session_attack_floor: test 2: 'decision' expected 'GO' but got 'NO-GO'
rest_site_heal_vs_upgrade: test 4: 'decision' expected 'HEAL' but got 'UPGRADE'
silent_archetype_score: test 4: expected_cut_contains 'DO NOT cut' not in result
```

- [ ] **Step 1: For each broken tool, read `execute()` logic and fix the failing TEST_CASES entry**

For each of the 8 tools:
1. Read the `execute()` function
2. Mentally evaluate the failing test case inputs through the logic
3. Fix the `TEST_CASES` expected value to match what the code actually returns
4. Do NOT change the `execute()` logic — only fix test expectations

- [ ] **Step 2: Remove duplicate `save_and_quit`/`continue_run` in `actions.py`**

`src/mcp_client/actions.py` has duplicate definitions:
- Lines 125-134: first `continue_run()` + first `save_and_quit()` under "Menu / Lifecycle"
- Lines 180-190: second `save_and_quit()` + second `continue_run()` under "Save / Continue"

Remove the duplicate section (lines 180-191 — the "Save / Continue" section header and both duplicate functions). The first definitions at lines 125-134 are sufficient.

- [ ] **Step 3: Verify all 8 tools load**

```bash
cd AgenticSTS && python -c "
from src.brain.dynamic_tools import DynamicToolRegistry
reg = DynamicToolRegistry()
count = reg.load_all()
print(f'Loaded: {count}/33 tools')
assert count == 33, f'Still {33-count} broken tools'
print('ALL TOOLS LOAD SUCCESSFULLY')
"
```
Expected: `Loaded: 33/33 tools` and `ALL TOOLS LOAD SUCCESSFULLY`

- [ ] **Step 4: Commit**

```bash
git add data/evolution/tools/*.py src/mcp_client/actions.py
git commit -m "fix(P5): correct TEST_CASES in 8 broken self-evolved tools + remove duplicate actions"
```

---

## Task 2: P3 — Rest Prompt Full Route Injection

**Files:**
- Modify: `src/agent/loop.py:119,822,2230,3295,3366,3384` — store `_route_node_types` alongside `_route_coords`
- Modify: `src/brain/prompts/rest.py:16-48` — add `remaining_route` parameter
- Test: `tests/test_rest_route.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_rest_route.py
from unittest.mock import MagicMock

from src.brain.prompts.rest import build_rest_prompt


def _make_mock_gs():
    """Create a minimal mock GameState for rest_site prompts."""
    gs = MagicMock()
    gs.state_type = "rest_site"
    gs.hp = 60
    gs.max_hp = 80
    gs.hp_ratio = 0.75
    gs.floor = 17
    gs.act = 1
    gs.gold = 100
    gs.raw.run.relics = []
    # rest options expected by build_rest_prompt
    gs.rest_options = ["smith", "rest"]
    return gs


def test_rest_prompt_injects_remaining_route():
    """Rest prompt should show full remaining route from current floor to boss."""
    mock_gs = _make_mock_gs()
    prompt = build_rest_prompt(
        gs=mock_gs,
        remaining_route=[
            (18, "Monster"),
            (19, "Elite"),
            (20, "Rest"),
            (21, "Boss"),
        ],
        v2=True,
    )
    assert "## Upcoming Path" in prompt
    assert "F18: Monster" in prompt
    assert "F21: Boss" in prompt
    assert "Rest sites remaining before boss: 1" in prompt


def test_rest_prompt_no_route_no_crash():
    """Without remaining_route, prompt still works (backward compat)."""
    mock_gs = _make_mock_gs()
    prompt = build_rest_prompt(gs=mock_gs, v2=True)
    assert "## Upcoming Path" not in prompt
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_rest_route.py -v
```

- [ ] **Step 3: Add `_route_node_types` storage to `loop.py`**

In `__init__` (after line 119):
```python
self._route_node_types: tuple[str, ...] = ()  # chosen route's node types
```

In `reset_for_new_run` (after line 822):
```python
self._route_node_types = ()
```

At every point where `_route_coords` is set, also set `_route_node_types`:
- Line 3295: add `self._route_node_types = routes[0].nodes`
- Line 3366: add `self._route_node_types = chosen.nodes`
- Line 3384: add `self._route_node_types = routes[0].nodes`

- [ ] **Step 4: Add `remaining_route` to `rest.py`**

In `build_rest_prompt()` signature (line 16-23), add:
```python
remaining_route: list[tuple[int, str]] | None = None,
```

After the upcoming_nodes threat detection block (after line 48), add:
```python
if remaining_route:
    lines.append("")
    lines.append("## Upcoming Path (from route plan)")
    path_parts = []
    rest_floors = []
    for floor_num, node_type in remaining_route:
        path_parts.append(f"F{floor_num}: {node_type}")
        if node_type.lower() == "rest":
            rest_floors.append(floor_num)
    lines.append(" → ".join(path_parts))
    rest_count = len(rest_floors)
    if rest_count > 0:
        rest_locs = ", ".join(f"F{f}" for f in rest_floors)
        lines.append(f"Rest sites remaining before boss: {rest_count} (at {rest_locs})")
        lines.append("You can smith now and heal later, or heal now and smith later.")
    else:
        lines.append("No rest sites remaining before boss. This is your last chance to upgrade or heal.")
```

- [ ] **Step 5: Pass route data in `loop.py` rest prompt call**

At line 2230, modify the `build_rest_prompt()` call:
```python
if gs.state_type == "rest_site":
    # Build remaining route from stored route plan
    remaining = self._build_remaining_route(gs)
    return build_rest_prompt(
        gs,
        deck=deck,
        relics=relics,
        v2=True,
        upcoming_nodes=self._upcoming_node_types,
        remaining_route=remaining,
    )
```

Add helper method to `AgentLoop`:
```python
def _build_remaining_route(self, gs: GameState) -> list[tuple[int, str]] | None:
    """Extract remaining route nodes from current floor to boss.

    RoutePath.coords are (col, row) pairs from the map DAG. The row
    is the actual map grid row (0 = first row of the act), NOT a
    relative offset. The route planner enumerates FUTURE nodes only
    (excluding the current node).

    Floor calculation: act_start_floor + row + 1.
    Act 1 starts at floor 1 (act_start=0), Act 2 at floor 18 (act_start=17),
    Act 3 at floor 35 (act_start=34).
    """
    if not self._route_node_types or not self._route_coords:
        return None
    if len(self._route_node_types) != len(self._route_coords):
        return None

    # Determine act start floor from current floor
    current_floor = gs.floor if hasattr(gs, 'floor') and gs.floor else 0
    act = gs.act if hasattr(gs, 'act') else 1
    act_start_floor = {1: 0, 2: 17, 3: 34}.get(act, 0)

    # Find current row from the map (approximate: current_floor - act_start_floor - 1)
    current_row = max(0, current_floor - act_start_floor - 1)

    result = []
    for ntype, (col, row) in zip(self._route_node_types, self._route_coords):
        if row <= current_row:
            continue  # already visited
        floor_num = act_start_floor + row + 1
        result.append((floor_num, ntype))
    return result if result else None
```

Note: `_route_node_types` and `_route_coords` come from `RoutePath.nodes` and `RoutePath.coords` respectively. The route planner's DFS enumerates FUTURE nodes from the current position to the boss. Row 0 is the first row of the act map grid. `act_start_floor` maps act to the floor before the first row: Act 1 = 0 (floor 1 = row 0), Act 2 = 17 (floor 18 = row 0), Act 3 = 34 (floor 35 = row 0).

- [ ] **Step 6: Run tests — verify PASS**

```bash
pytest tests/test_rest_route.py -v
```

- [ ] **Step 7: Commit**

```bash
git add src/brain/prompts/rest.py src/agent/loop.py tests/test_rest_route.py
git commit -m "feat(P3): rest prompt sees full remaining route to boss"
```

---

## Task 3: P4 Layer 1a — Randomized Tie-Breaking

**Files:**
- Modify: `src/skills/library.py:113-114` — add jitter to scoring
- Test: `tests/test_skill_lifecycle.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_skill_lifecycle.py
def test_tie_breaking_rotates_skills():
    """Skills with identical scores should not always return in same order."""
    library = SkillLibrary()
    # Create 10 skills with identical relevance and priority
    for i in range(10):
        library.add(Skill(
            skill_id=f"skill_{i}", name=f"Skill {i}",
            category="combat", content=f"Content {i}",
            priority=50, confidence=0.5,
        ))

    # Query 20 times, collect first result each time
    first_results = set()
    for _ in range(20):
        results = library.query(state_type="monster", limit=5)
        if results:
            first_results.add(results[0][0].skill_id)

    # With 10 identical skills and random jitter,
    # we should see at least 2 different first results over 20 queries
    assert len(first_results) >= 2, f"Always returned same skill: {first_results}"
```

- [ ] **Step 2: Run test — verify FAIL** (currently deterministic, always same order)

- [ ] **Step 3: Add jitter to `library.py` scoring**

In `query()` method, after computing scores (around line 113-114), add jitter before sorting:
```python
import random
# Jitter breaks ties: skills with identical scores rotate across queries
matches.sort(key=lambda x: (x[1] + random.uniform(0, 0.001)), reverse=True)
```

- [ ] **Step 4: Run test — verify PASS**

- [ ] **Step 5: Commit**

```bash
git add src/skills/library.py tests/test_skill_lifecycle.py
git commit -m "feat(P4-L1a): randomized tie-breaking in skill query"
```

---

## Task 4: P4 Layer 1b — Per-Source Slot Quotas

**Files:**
- Modify: `src/skills/library.py:122-129` — replace single-slot reservation with quota system
- Modify: `config.py:98-99` — update `SKILLS_MAX_PER_PROMPT` and `SKILLS_MAX_INJECTION_TOKENS`
- Modify: `src/skills/composer.py:18` — update `max_tokens` default
- Test: `tests/test_skill_lifecycle.py`

- [ ] **Step 1: Write failing test**

```python
def test_slot_quota_guarantees_nonseed_slots():
    """At least 2 of 7 slots must be non-seed skills."""
    library = SkillLibrary()
    # 5 high-scoring seeds
    for i in range(5):
        library.add(Skill(
            skill_id=f"seed_{i}", name=f"Seed {i}",
            category="combat", content=f"Seed content {i}",
            priority=80, confidence=0.9, source="seed",
        ))
    # 3 lower-scoring discovered skills
    for i in range(3):
        library.add(Skill(
            skill_id=f"disc_{i}", name=f"Discovered {i}",
            category="combat", content=f"Disc content {i}",
            priority=60, confidence=0.5, source="discovered",
        ))

    results = library.query(state_type="monster", limit=7)
    sources = [s.source for s, _ in results]
    seed_count = sources.count("seed")
    nonseed_count = len(sources) - seed_count

    assert seed_count <= 3, f"Too many seeds: {seed_count}"
    assert nonseed_count >= 2, f"Not enough non-seeds: {nonseed_count}"
```

- [ ] **Step 2: Run test — verify FAIL**

- [ ] **Step 3: Implement slot quotas in `library.py`**

Replace the existing non-seed reservation block (lines 122-129) with:
```python
# Slot quota: guarantee min(2, available) non-seed, guarantee min(3, available) seed,
# then fill remaining slots from EITHER pool by best score.
all_seed = [(s, sc) for s, sc in matches if s.source == "seed"]
all_nonseed = [(s, sc) for s, sc in matches if s.source != "seed"]

# Phase 1: guarantee minimum non-seed slots
nonseed_guaranteed = all_nonseed[:min(2, len(all_nonseed))]
# Phase 2: guarantee minimum seed slots
seed_guaranteed = all_seed[:min(3, len(all_seed))]
# Phase 3: fill remaining from ALL leftover candidates by score
used_ids = {s.skill_id for s, _ in nonseed_guaranteed + seed_guaranteed}
remaining_pool = [(s, sc) for s, sc in matches if s.skill_id not in used_ids]
remaining_pool.sort(key=lambda x: x[1] + random.uniform(0, 0.001), reverse=True)
remaining_slots = max(0, limit - len(nonseed_guaranteed) - len(seed_guaranteed))
fill = remaining_pool[:remaining_slots]

combined = nonseed_guaranteed + seed_guaranteed + fill
combined.sort(key=lambda x: x[1] + random.uniform(0, 0.001), reverse=True)
top = combined[:limit]
```

- [ ] **Step 4: Increase tag matching bonus in `models.py`**

In `models.py`, in `SkillTrigger.matches()` (around line 157), change the tag overlap scoring:
```python
# Tag overlap bonus — specific tags greatly boost relevance
if self.tags and context_tags:
    overlap = len(self.tags & context_tags)
    score += overlap * 1.0  # was 0.3 — 1.0 per matching tag
    if overlap >= 2:
        score += 1.0  # bonus for multi-tag match (highly specific)
```

This makes tag-specific skills much more competitive against generic seeds.

- [ ] **Step 5: Update config constants**

In `config.py`:
```python
SKILLS_MAX_PER_PROMPT = int(os.getenv("STS2_SKILLS_MAX_PER_PROMPT", "7"))
SKILLS_MAX_INJECTION_TOKENS = int(os.getenv("STS2_SKILLS_MAX_INJECTION_TOKENS", "900"))
```

In `composer.py` line 18, change default:
```python
def compose_skill_context(skills: list[Skill], max_tokens: int = 900) -> str:
```

- [ ] **Step 6: Run tests — verify PASS**

- [ ] **Step 7: Commit**

```bash
git add src/skills/library.py src/skills/models.py src/skills/composer.py config.py tests/test_skill_lifecycle.py
git commit -m "feat(P4-L1b): per-source slot quotas, tag bonus 1.0, config 7 slots / 900 tokens"
```

---

## Task 5: P4 Layer 2 — Trigger Specificity

**Files:**
- Modify: `src/skills/discovery.py:27-86` — add trigger specificity guidance to prompt
- Modify: `src/brain/write_tools.py:48-98` — add validation warning for generic triggers
- Create: `scripts/enrich_skill_triggers.py` — one-time batch enrichment

- [ ] **Step 1: Enhance discovery prompt**

In `discovery.py`, add to `_DISCOVERY_PROMPT` (around line 60, before the task section):
```python
TRIGGER SPECIFICITY (critical for skill selection):
When defining triggers, be SPECIFIC:
- enemy_names: which enemies does this apply to? (e.g., ["Lagavulin", "Kin Priest"])
- min_act/max_act: which acts? (e.g., 1-1 for Act 1 only)
- tags: situation keywords (low_hp, multi_enemy, poison_build, boss_prep, scaling, etc.)
A generic skill with no enemy names, no act limits, and no tags
competes with 50+ other generic skills and will NEVER be selected.
```

- [ ] **Step 2: Add trigger validation in `write_tools.py`**

After the WRITE_SKILL schema definition, add a validation helper:
```python
def validate_skill_trigger(trigger_data: dict) -> list[str]:
    """Warn about overly generic triggers. Returns warning strings."""
    warnings = []
    state_types = trigger_data.get("state_types", [])
    enemy_names = trigger_data.get("enemy_names", [])
    tags = trigger_data.get("tags", [])
    if len(state_types) >= 3 and not enemy_names and not tags:
        warnings.append(
            "Trigger is too generic (3+ state_types, no enemy_names, no tags). "
            "This skill will compete with 50+ others and rarely be selected."
        )
    return warnings
```

Call this in `evolution_engine.py`'s `_handle_write_skill` and log warnings.

- [ ] **Step 3: Create trigger enrichment script**

```python
# scripts/enrich_skill_triggers.py
"""One-time batch job: enrich 103 zero-usage skills' triggers with specificity."""
```

This script:
1. Loads `skills.json`
2. Filters skills with `usage_count == 0`
3. For each, sends content to Sonnet asking:
   - What specific enemies does this mention?
   - What acts does this apply to?
   - What situation tags describe this? (from: low_hp, multi_enemy, poison_build, shiv_build, boss_prep, scaling, aoe, block_heavy, energy_tight, deck_thin)
4. Updates the skill's trigger fields
5. Saves back to `skills.json`

- [ ] **Step 4: Commit**

```bash
git add src/skills/discovery.py src/brain/write_tools.py scripts/enrich_skill_triggers.py
git commit -m "feat(P4-L2): trigger specificity enforcement + enrichment script"
```

---

## Task 6: P4 Layer 3 — Dedup + Merge + Retirement

**Files:**
- Modify: `src/skills/models.py` — `with_update()`, `status` field, `version` field, `supplements_seed_id`
- Modify: `src/skills/library.py` — dedup check, retirement sweep, category cap
- Modify: `src/brain/evolution_engine.py` — dedup in `_handle_write_skill`
- Test: `tests/test_skill_lifecycle.py`

- [ ] **Step 1: Write failing tests**

```python
def test_skill_with_update_bumps_version():
    s = Skill(skill_id="s1", name="S1", category="combat",
              content="Original", version=1)
    updated = s.with_update(content="Original\n\n[Updated]: New insight", version=2)
    assert updated.version == 2
    assert "[Updated]" in updated.content
    assert updated.confidence == s.confidence  # preserved

def test_retirement_deactivates_low_confidence():
    library = SkillLibrary()
    s = Skill(skill_id="bad", name="Bad", category="combat",
              content="Bad advice", confidence=0.1, usage_count=10,
              success_count=1, failure_count=9, status="active")
    library.add(s)
    library.sweep_retirements()
    assert library.get("bad").status == "deactivated"

def test_category_cap_retires_lowest():
    library = SkillLibrary()
    for i in range(20):
        library.add(Skill(
            skill_id=f"c_{i}", name=f"Combat {i}", category="combat",
            content=f"Content {i}", confidence=0.3 + i * 0.02,
            usage_count=10, status="active",
        ))
    library.enforce_category_caps(max_per_category=15)
    active = [s for s in library.all_skills if s.status == "active" and s.category == "combat"]
    assert len(active) <= 15
```

- [ ] **Step 2: Run tests — verify FAIL**

- [ ] **Step 3: Add `status`, `version`, `supplements_seed_id` to `Skill`**

In `models.py`, add fields to Skill dataclass:
```python
status: str = "active"  # "active" | "probation" | "deactivated"
version: int = 1
supplements_seed_id: str = ""  # seed skill this supplements (if any)
deactivated_runs: int = 0  # consecutive runs while deactivated
```

Add `with_update()` method:
```python
def with_update(self, *, content: str = "", version: int = 0, **kwargs) -> "Skill":
    """Return updated copy with new content and bumped version."""
    return Skill(
        **{
            **{f.name: getattr(self, f.name) for f in fields(self)},
            "content": content or self.content,
            "version": version or self.version,
            **kwargs,
        }
    )
```

**Also update `to_dict()` and `from_dict()` to persist the new fields.** Without this, skills saved to JSON will lose their `status`, `supplements_seed_id`, and `deactivated_runs` on reload.

In `to_dict()`, add after the `"superseded_by"` entry:
```python
"status": self.status,
"supplements_seed_id": self.supplements_seed_id,
"deactivated_runs": self.deactivated_runs,
```

In `from_dict()`, add after the `superseded_by` line:
```python
status=d.get("status", "active"),
supplements_seed_id=d.get("supplements_seed_id", ""),
deactivated_runs=d.get("deactivated_runs", 0),
```

Also update `with_usage()` and `with_deactivation()` to copy the new fields through (they currently construct Skill with explicit field names and will drop the new fields).

- [ ] **Step 4: Add retirement + category cap to `library.py`**

```python
def sweep_retirements(self) -> list[str]:
    """Deactivate low-confidence skills, delete long-deactivated ones."""
    removed = []
    for skill in list(self._skills.values()):
        if skill.usage_count < 5:
            continue  # exploration period
        rate = skill.success_count / max(skill.usage_count, 1)
        if rate < 0.2 and skill.status == "active":
            self._skills[skill.skill_id] = skill.with_update(status="deactivated")
        elif 0.2 <= rate < 0.5 and skill.status == "active":
            self._skills[skill.skill_id] = skill.with_update(status="probation")
        if skill.status == "deactivated" and skill.deactivated_runs >= 3:
            del self._skills[skill.skill_id]
            removed.append(skill.skill_id)
    return removed

def enforce_category_caps(self, max_per_category: int = 15) -> list[str]:
    """Remove lowest-confidence skills exceeding category cap."""
    from collections import defaultdict
    by_cat = defaultdict(list)
    for s in self._skills.values():
        if s.status != "deactivated":
            by_cat[s.category].append(s)
    removed = []
    for cat, skills in by_cat.items():
        if len(skills) <= max_per_category:
            continue
        skills.sort(key=lambda s: s.confidence)
        for victim in skills[:len(skills) - max_per_category]:
            self._skills[victim.skill_id] = victim.with_update(status="deactivated")
            removed.append(victim.skill_id)
    return removed
```

- [ ] **Step 5: Add dedup check in `evolution_engine.py`**

In `_handle_write_skill`, before creating a new skill:
```python
# Semantic dedup: check if similar skill already exists
existing = self._find_similar_skill(new_skill_name, new_skill_content, category)
if existing:
    if existing.source == "seed":
        # Seeds are IMMUTABLE (Layer 3c). Create the new skill as a supplement
        # that references the seed, rather than merging into it.
        new_skill = Skill(
            name=new_skill_name,
            category=category,
            content=new_skill_content,
            source="discovered",
            supplements_seed_id=existing.skill_id,
            # ... other fields from evolution params ...
        )
        self._skill_library.add(new_skill)
        return f"Created supplement to seed '{existing.name}' (supplements_seed_id={existing.skill_id})"
    elif self._should_merge(existing, new_skill_content):
        merged = existing.with_update(
            content=f"{existing.content}\n\n[Updated]: {new_skill_content}",
            version=existing.version + 1,
        )
        self._skill_library.update(merged)
        return f"Merged into existing skill '{existing.name}' (v{merged.version})"
    else:
        return f"Duplicate of existing skill '{existing.name}' — skipped"
```

`_find_similar_skill` uses keyword overlap (40%+ = duplicate candidate).

**Seed immutability rule:** When the dedup match is a seed skill, do NOT merge into it. Instead, create the new skill with `supplements_seed_id=existing.skill_id`. During prompt composition (Task 8 Step 3), supplementary skills are shown alongside their parent seed.

- [ ] **Step 6: Run tests — verify PASS**

- [ ] **Step 7: Commit**

```bash
git add src/skills/models.py src/skills/library.py src/brain/evolution_engine.py tests/test_skill_lifecycle.py
git commit -m "feat(P4-L3): skill dedup, merge, retirement, category caps"
```

---

## Task 7: P4 Layer 4 — Game-Native Replay Evaluator

**Files:**
- Create: `src/skills/replay_evaluator.py` — replay orchestrator
- Modify: `src/skills/library.py` — `temporary_override()`, `record_replay_outcome()`
- Modify: `src/agent/loop.py` — call replay after boss fights
- Test: `tests/test_replay_evaluator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_replay_evaluator.py
from src.skills.replay_evaluator import (
    ReplayResult, update_confidence_from_replays, build_alternative_sets,
)

def test_replay_rewards_best_penalizes_worst():
    """Best skill set gets positive signal, worst-only skills get negative."""
    results = [
        ReplayResult("set_a", ("s1", "s2", "s3"), hp_lost=10, rounds=5, potions_used=0, won=True),
        ReplayResult("set_b", ("s1", "s4", "s5"), hp_lost=25, rounds=8, potions_used=1, won=True),
    ]
    # s1 is in both — should not be penalized
    # s2, s3 are in best — should be rewarded
    # s4, s5 are only in worst — should be penalized
    outcomes = compute_confidence_deltas(results)
    assert outcomes["s2"] > 0  # rewarded
    assert outcomes["s3"] > 0  # rewarded
    assert outcomes["s4"] < 0  # penalized
    assert outcomes["s5"] < 0  # penalized
    assert "s1" not in outcomes or outcomes["s1"] >= 0  # shared, not penalized

def test_no_update_when_results_identical():
    """If all skill sets produce same hp_lost, no confidence changes."""
    results = [
        ReplayResult("set_a", ("s1",), hp_lost=15, rounds=5, potions_used=0, won=True),
        ReplayResult("set_b", ("s2",), hp_lost=15, rounds=5, potions_used=0, won=True),
    ]
    outcomes = compute_confidence_deltas(results)
    assert len(outcomes) == 0
```

- [ ] **Step 2: Run tests — verify FAIL**

- [ ] **Step 3: Implement `replay_evaluator.py`**

```python
"""Game-native boss fight replay for skill A/B testing.

Uses STS2's save_and_quit / continue_run to replay the same boss fight
with different skill sets. The game engine handles ALL mechanics — card
effects, status tracking, relic procs, draw pile order (seeded RNG).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass

from src.mcp_client import actions
from src.mcp_client.client import McpClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayResult:
    skill_set_id: str
    skills_used: tuple[str, ...]
    hp_lost: int
    rounds: int
    potions_used: int
    won: bool


def compute_confidence_deltas(
    results: list[ReplayResult],
) -> dict[str, float]:
    """Compare replay results, return per-skill confidence deltas."""
    if len(results) < 2:
        return {}
    scored = sorted(results, key=lambda r: (not r.won, r.hp_lost, r.potions_used))
    best, worst = scored[0], scored[-1]
    if best.hp_lost >= worst.hp_lost:
        return {}

    magnitude = (worst.hp_lost - best.hp_lost) / max(worst.hp_lost, 1)
    deltas: dict[str, float] = {}
    best_set = set(best.skills_used)
    worst_set = set(worst.skills_used)

    # Skills only in best: positive signal
    for sid in best.skills_used:
        if sid not in worst_set:
            deltas[sid] = magnitude * 0.1

    # Skills only in worst: negative signal
    for sid in worst.skills_used:
        if sid not in best_set:
            deltas[sid] = -magnitude * 0.1

    return deltas


def build_alternative_sets(
    library,  # SkillLibrary
    original_skill_ids: tuple[str, ...],
    state_type: str = "boss",
    limit: int = 2,
) -> list[list[str]]:
    """Build alternative skill sets by swapping 2-3 skills from original.

    For each alternative set:
    1. Keep a core subset of original skills (random half)
    2. Replace the rest with unused skills matching the context
    3. Ensure each alternative is meaningfully different from original

    Returns list of skill ID lists (each is a full replacement set).
    """
    import random

    original_set = set(original_skill_ids)
    original_list = list(original_skill_ids)

    # Query library for candidate replacements (skills not in original)
    all_matches = library.query(state_type=state_type, limit=30)
    candidates = [
        s.skill_id for s, _score in all_matches
        if s.skill_id not in original_set
    ]
    if not candidates:
        return []

    alternatives: list[list[str]] = []
    for _ in range(limit):
        if len(original_list) <= 2:
            # Too few original skills to swap — replace all
            swap_count = len(original_list)
        else:
            swap_count = random.randint(2, min(3, len(original_list)))

        # Pick which original skills to swap out
        swap_indices = random.sample(range(len(original_list)), swap_count)
        kept = [sid for i, sid in enumerate(original_list) if i not in swap_indices]

        # Pick replacements from candidates (no repeats across swaps)
        available = [c for c in candidates if c not in kept]
        if len(available) < swap_count:
            continue  # not enough candidates for a meaningful swap
        replacements = random.sample(available, swap_count)

        alt_set = kept + replacements
        alternatives.append(alt_set)

    return alternatives


async def evaluate_boss_skills(
    client: McpClient,
    skill_library,  # SkillLibrary
    original_result: ReplayResult,
    max_alternatives: int = 2,
) -> list[ReplayResult]:
    """Replay same boss fight with alternative skill sets.

    Flow: save → return to menu → continue (same state) → play with alt skills
    → record result → repeat → resume normal play.
    """
    alt_sets = build_alternative_sets(
        skill_library, original_result.skills_used,
        state_type="boss", limit=max_alternatives,
    )
    if not alt_sets:
        logger.info("No alternative skill sets available for replay")
        return [original_result]

    results = [original_result]
    for i, alt_skills in enumerate(alt_sets):
        logger.info("Replay %d/%d with skills: %s", i + 1, len(alt_sets), alt_skills)
        await client.post_action(actions.save_and_quit())
        await asyncio.sleep(2)
        await client.post_action(actions.continue_run())
        await asyncio.sleep(2)
        with skill_library.temporary_override(alt_skills):
            result = await run_single_combat(client, skill_library)
        results.append(result)

    # Resume normal play after all replays
    await client.post_action(actions.save_and_quit())
    await asyncio.sleep(2)
    await client.post_action(actions.continue_run())

    # Update confidence based on comparative results
    update_confidence_from_replays(skill_library, results)
    return results
```

- [ ] **Step 4: Add `temporary_override()` and `record_replay_outcome()` to `library.py`**

```python
from contextlib import contextmanager

@contextmanager
def temporary_override(self, skill_ids: list[str]):
    """Temporarily override active skills for replay evaluation."""
    original = self._active_override
    self._active_override = set(skill_ids)
    try:
        yield
    finally:
        self._active_override = original

def record_replay_outcome(self, skill_id: str, *, success: bool, quality: float):
    """Record outcome from replay evaluation (stronger signal than normal usage)."""
    skill = self._skills.get(skill_id)
    if not skill:
        return
    # Replay outcomes count as 2 normal uses (stronger signal)
    updated = skill.with_usage(success=success)
    if not success:
        updated = updated.with_usage(success=False)  # double-count failures
    self._skills[skill_id] = updated
```

- [ ] **Step 5: Wire replay into `loop.py` post-boss**

In the combat end handler, after a boss fight:
```python
if combat_type == "boss" and self._skill_library and REPLAY_ENABLED:
    original_result = ReplayResult(
        skill_set_id="original",
        skills_used=tuple(self._combat_skill_ids),
        hp_lost=abs(hp_delta),
        rounds=round_count,
        potions_used=potions_used_count,
        won=won,
    )
    asyncio.create_task(
        evaluate_boss_skills(self._client, self._skill_library, original_result)
    )
```

- [ ] **Step 6: Run tests — verify PASS**

- [ ] **Step 7: Commit**

```bash
git add src/skills/replay_evaluator.py src/skills/library.py src/agent/loop.py tests/test_replay_evaluator.py
git commit -m "feat(P4-L4): game-native boss replay for skill A/B testing"
```

---

## Task 8: Integration Wiring + Config

**Files:**
- Modify: `config.py` — add new constants
- Modify: `src/agent/loop.py` — wire retirement sweep into post-run
- Modify: `src/skills/composer.py` — handle supplementary skills

- [ ] **Step 1: Add config constants**

```python
# config.py
MAX_ACTIVE_PER_CATEGORY = int(os.getenv("STS2_MAX_SKILLS_PER_CATEGORY", "15"))
REPLAY_ENABLED = os.getenv("STS2_REPLAY_ENABLED", "true").lower() == "true"
REPLAY_MAX_ALTERNATIVES = int(os.getenv("STS2_REPLAY_MAX_ALTERNATIVES", "2"))
```

- [ ] **Step 2: Wire retirement sweep into post-run in `loop.py`**

In `_post_run_skill_update()`, after saving confidence:
```python
# Retirement sweep
removed = self._skill_library.sweep_retirements()
if removed:
    logger.info("Retired %d skills: %s", len(removed), removed)
capped = self._skill_library.enforce_category_caps(MAX_ACTIVE_PER_CATEGORY)
if capped:
    logger.info("Category cap deactivated %d skills: %s", len(capped), capped)
```

- [ ] **Step 3: Handle supplementary skills in `composer.py`**

When composing skill context, if a skill has `supplements_seed_id`, show the seed first, then the supplement indented:
```python
if skill.supplements_seed_id:
    # Find the seed and show it first (if not already shown)
    seed = next((s for s in skills if s.skill_id == skill.supplements_seed_id), None)
    if seed and seed.skill_id not in shown:
        lines.append(format_skill(seed))
        shown.add(seed.skill_id)
    lines.append(f"  [Supplement to {skill.supplements_seed_id}]:")
    lines.append(f"  {skill.content[:200]}")
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/test_skill_lifecycle.py tests/test_replay_evaluator.py tests/test_rest_route.py -v
```

- [ ] **Step 5: Commit**

```bash
git add config.py src/agent/loop.py src/skills/composer.py
git commit -m "feat(P4): integration wiring — retirement sweep, category caps, config"
```

---

## Task 9: P4 Layer 4d — Quality-Based `record_outcome`

**Files:**
- Modify: `src/skills/library.py` — `record_outcome()` gains `quality_score` parameter
- Modify: `src/agent/loop.py` — compute quality metric per decision type and pass to `record_outcome()`
- Test: `tests/test_skill_lifecycle.py`

Per the spec (Layer 4d), `record_outcome` should accept a `quality_score: float` (0.0-1.0) instead of just binary `success: bool`. Each decision type computes its own quality score:

| Decision Type | Quality Metric | When Evaluated |
|---|---|---|
| Card reward | Card played-count in subsequent combats (0 = dead weight) | Run end |
| Card removal | Deck cycle improvement (cards/turn) + subsequent combat hp_delta | After 3 combats |
| Rest: smith | Upgraded card's play count + combat performance delta | After next combat |
| Rest: heal | Survival in next combat (binary) | After next combat |
| Map routing | HP at boss / HP at act end | Act end |
| Shop purchase | Item usage frequency (cards played, potions used, relic procs) | Run end |
| Event | Net HP/gold/card value of chosen option | Immediate |

- [ ] **Step 1: Write failing test**

```python
# tests/test_skill_lifecycle.py
def test_record_outcome_quality_score():
    """record_outcome with quality_score adjusts confidence proportionally."""
    library = SkillLibrary()
    s = Skill(skill_id="q1", name="Q1", category="combat",
              content="Quality test", confidence=0.5, usage_count=5,
              success_count=2, failure_count=3)
    library.add(s)

    # High quality success should boost confidence more than low quality
    library.record_outcome(["q1"], success=True, quality_score=0.9)
    high_conf = library.get("q1").confidence

    # Reset and try low quality
    library.add(s)  # reset to original
    library.record_outcome(["q1"], success=True, quality_score=0.2)
    low_conf = library.get("q1").confidence

    assert high_conf > low_conf, "Higher quality should produce higher confidence"
```

- [ ] **Step 2: Run test — verify FAIL**

- [ ] **Step 3: Update `record_outcome` in `library.py`**

```python
def record_outcome(
    self, skill_ids: list[str], success: bool,
    quality_score: float = 1.0,
) -> None:
    """Record outcome for skills that were active during a decision.

    Args:
        skill_ids: Skill IDs that were injected into the prompt.
        success: Whether the decision led to a positive outcome.
        quality_score: 0.0-1.0 quality metric (default 1.0 for backward compat).
            Used to weight the confidence update: high quality success
            boosts more, low quality success boosts less.
    """
    for sid in skill_ids:
        skill = self._skills.get(sid)
        if skill and skill.active:
            self._skills[sid] = skill.with_usage(success, quality_score=quality_score)
```

- [ ] **Step 4: Update `with_usage` in `models.py` to accept `quality_score`**

Add `quality_score: float = 1.0` parameter to `Skill.with_usage()`. Use it to scale the confidence blend weight:
```python
def with_usage(self, success: bool, quality_score: float = 1.0) -> Skill:
    # ... existing counting logic ...
    # Scale confidence update by quality_score
    if total_tracked >= 3:
        observed = (new_success + 1) / (total_tracked + 2)
        weight = min(total_tracked / 10.0, 1.0) * max(0.1, quality_score)
        new_confidence = (1 - weight) * self.confidence + weight * observed
    # ... rest unchanged ...
```

- [ ] **Step 5: Wire quality metric computation in `loop.py`**

Add per-decision-type quality computation helpers:
```python
def _compute_card_reward_quality(self, card_name: str) -> float:
    """Run-end: ratio of combats where card was played vs total combats."""
    # Tracked via _stm.combat_card_plays or similar
    if not self._stm or not self._stm.combat_history:
        return 0.5
    combats_with_play = sum(1 for c in self._stm.combat_history if card_name in c.cards_played)
    return min(1.0, combats_with_play / max(len(self._stm.combat_history), 1))

def _compute_map_quality(self) -> float:
    """Act-end: HP ratio at boss relative to max HP."""
    gs = self._last_gs
    if not gs:
        return 0.5
    return gs.hp_ratio if hasattr(gs, 'hp_ratio') else 0.5

def _compute_rest_smith_quality(self, card_name: str) -> float:
    """After next combat: was the upgraded card played?"""
    # Binary: 1.0 if played, 0.3 if not
    if not self._stm or not self._stm.last_combat:
        return 0.5
    return 1.0 if card_name in self._stm.last_combat.cards_played else 0.3
```

Wire these into the appropriate post-decision and post-run hooks.

- [ ] **Step 6: Run tests — verify PASS**

- [ ] **Step 7: Commit**

```bash
git add src/skills/library.py src/skills/models.py src/agent/loop.py tests/test_skill_lifecycle.py
git commit -m "feat(P4-L4d): quality-based record_outcome with per-decision-type metrics"
```

---

## Execution Order & Dependencies

```
Task 1 (P5: broken tools)     — independent, do first
Task 2 (P3: rest route)       — independent
Task 3 (P4-L1a: tie-breaking) — independent
Task 4 (P4-L1b: slot quotas)  — depends on Task 3 (same file)
Task 5 (P4-L2: triggers)      — independent
Task 6 (P4-L3: dedup/retire)  — depends on Task 4 (models.py fields)
Task 7 (P4-L4: replay)        — depends on Task 6 (library methods)
Task 8 (integration)          — depends on Tasks 4, 6, 7
Task 9 (P4-L4d: quality)      — depends on Task 6 (models.py with_usage)
```

**Parallelizable:** Tasks 1, 2, 3, 5 can all run in parallel.
**Sequential chain:** 3 → 4 → 6 → 7 → 8; also 6 → 9

---

## Validation Checklist

After all tasks complete:

- [ ] `DynamicToolRegistry().load_all()` returns 33/33
- [ ] No duplicate `save_and_quit`/`continue_run` in `actions.py`
- [ ] Rest prompt at a rest site shows "## Upcoming Path" with full route
- [ ] `library.query(limit=7)` returns mix of seeds and non-seeds
- [ ] 20 consecutive `query()` calls show rotation (different first skill)
- [ ] Tag overlap bonus uses 1.0 per match (not 0.3) with +1.0 for overlap >= 2
- [ ] `sweep_retirements()` deactivates skills with <20% success rate
- [ ] `enforce_category_caps(15)` removes excess skills per category
- [ ] `build_alternative_sets()` returns valid alternative skill combinations with 2-3 swapped skills
- [ ] `evaluate_boss_skills()` orchestrates save/continue replay loop
- [ ] `compute_confidence_deltas()` rewards best, penalizes worst-only
- [ ] `record_outcome(quality_score=0.9)` produces higher confidence than `quality_score=0.2`
- [ ] New Skill fields (`status`, `supplements_seed_id`, `deactivated_runs`) survive save/load cycle
- [ ] Dedup against seed skill creates supplement (not merge)
- [ ] Full agent run completes without errors (smoke test)
