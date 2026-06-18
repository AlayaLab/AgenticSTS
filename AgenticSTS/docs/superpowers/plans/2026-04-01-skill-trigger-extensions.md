# Skill Trigger Situation Extensions — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `SkillTrigger` with situation-level fields (threat_levels, intent_classes, deck_stages, any_of_relics, requires_hand_capabilities) so skills match tighter to combat situations, and add progressive prompt injection that demotes whole-fight guides at R2+ and filters skills by threat level.

**Architecture:** Add 5 new optional `frozenset` fields to `SkillTrigger` + extend `matches()` to score them. `SkillLibrary.query()` passes `SituationTag` through to matching. `prompt_injector.py` gains round-aware and threat-aware formatting. `composer.py` gains threat-level skill filtering. All backward compatible — empty fields match everything.

**Tech Stack:** Python 3.12, frozen dataclasses, no new dependencies.

**Spec:** `docs/2026-03-31-situation-level-retrieval-design.md` Sections 11-12.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/skills/models.py` | MODIFY | Add 5 fields to `SkillTrigger`, extend `matches()`, update `to_dict()`/`from_dict()` |
| `src/skills/library.py` | MODIFY | Pass `situation` to `trigger.matches()` in `query()` |
| `src/skills/composer.py` | MODIFY | Accept `threat_level`, filter survival-only skills at HIGH/LETHAL |
| `src/memory/short_term.py` | MODIFY | Add `get_current_situation_tag()` public accessor |
| `src/memory/prompt_injector.py` | MODIFY | Round-aware guide demotion at R2+, threat banner |
| `src/memory/retriever.py` | MODIFY | Pass `current_round` + `current_threat_level` to WorkingContext (including `_trim_working_context`) |
| `src/memory/models_v2.py` | MODIFY | Add `current_round` + `current_threat_level` fields to `WorkingContext` |
| `src/agent/loop.py` | MODIFY | Pass `SituationTag` to skill query, add relic names to `context_tags`, pass `threat_level` to composer |
| `tests/test_skill_trigger_situation.py` | **CREATE** | Tests for new trigger fields + matching |
| `tests/test_progressive_injection.py` | **CREATE** | Tests for round-aware + threat-aware injection |

---

### Task 1: SkillTrigger New Fields + Matching

**Files:**
- Modify: `src/skills/models.py`
- Create: `tests/test_skill_trigger_situation.py`

- [ ] **Step 1: Write failing tests for new trigger fields**

Create `tests/test_skill_trigger_situation.py`:

```python
"""Tests for SkillTrigger situation-level extensions (Phase 2)."""

from src.skills.models import SkillTrigger


class TestThreatLevelMatching:
    def test_empty_threat_levels_matches_all(self):
        t = SkillTrigger(state_types=frozenset({"monster"}))
        matched, score = t.matches(state_type="monster")
        assert matched is True

    def test_matching_threat_level_boosts_score(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            threat_levels=frozenset({"high", "lethal"}),
        )
        from src.memory.situation import SituationTag
        sit = SituationTag(threat_level="high")
        matched, score = t.matches(state_type="monster", situation=sit)
        assert matched is True
        assert score >= 3.0  # state_type(1.0) + threat_level(2.0)

    def test_non_matching_threat_level_still_matches_lower_score(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            threat_levels=frozenset({"high", "lethal"}),
        )
        from src.memory.situation import SituationTag
        sit = SituationTag(threat_level="low")
        matched, score = t.matches(state_type="monster", situation=sit)
        assert matched is True  # threat_levels is ranking, not hard filter
        assert score < 3.0  # no threat bonus


class TestIntentClassMatching:
    def test_matching_intent_boosts_score(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            intent_classes=frozenset({"attack"}),
        )
        from src.memory.situation import SituationTag
        sit = SituationTag(intent_class="attack")
        matched, score = t.matches(state_type="monster", situation=sit)
        assert matched is True
        assert score >= 2.5  # state_type(1.0) + intent(1.5)


class TestHandCapabilityMatching:
    def test_any_of_hand_capabilities_hard_filter(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            requires_hand_capabilities=frozenset({"can_apply_weak", "can_block_full_incoming"}),
        )
        from src.memory.situation import SituationTag, HandCapabilityTag
        # Has can_apply_weak → passes (any-of)
        sit = SituationTag(hand_capabilities=HandCapabilityTag(can_apply_weak=True))
        matched, score = t.matches(state_type="monster", situation=sit)
        assert matched is True
        assert score >= 2.0  # state_type(1.0) + hand_cap(1.0)

    def test_no_matching_capabilities_rejects(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            requires_hand_capabilities=frozenset({"can_apply_weak"}),
        )
        from src.memory.situation import SituationTag, HandCapabilityTag
        sit = SituationTag(hand_capabilities=HandCapabilityTag(can_apply_weak=False))
        matched, _ = t.matches(state_type="monster", situation=sit)
        assert matched is False


class TestRelicMatching:
    def test_any_of_relics_hard_filter(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            any_of_relics=frozenset({"Burning Blood", "Pantograph"}),
        )
        # context_tags carries relic names
        matched, score = t.matches(
            state_type="monster",
            context_tags=frozenset({"Burning Blood", "some_tag"}),
        )
        assert matched is True
        assert score >= 1.3  # state_type(1.0) + relic(0.3)

    def test_no_matching_relics_rejects(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            any_of_relics=frozenset({"Burning Blood"}),
        )
        matched, _ = t.matches(
            state_type="monster",
            context_tags=frozenset({"other_tag"}),
        )
        assert matched is False


class TestDeckStageMatching:
    def test_matching_deck_stage_boosts_score(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            deck_stages=frozenset({"scaling", "mature"}),
        )
        from src.memory.situation import SituationTag
        sit = SituationTag(deck_stage="scaling")
        matched, score = t.matches(state_type="monster", situation=sit)
        assert matched is True
        assert score >= 1.5  # state_type(1.0) + deck_stage(0.5)


class TestSerialization:
    def test_new_fields_round_trip(self):
        t = SkillTrigger(
            state_types=frozenset({"monster"}),
            threat_levels=frozenset({"high", "lethal"}),
            intent_classes=frozenset({"attack"}),
            deck_stages=frozenset({"scaling"}),
            any_of_relics=frozenset({"Burning Blood"}),
            requires_hand_capabilities=frozenset({"can_apply_weak"}),
        )
        d = t.to_dict()
        restored = SkillTrigger.from_dict(d)
        assert restored.threat_levels == frozenset({"high", "lethal"})
        assert restored.intent_classes == frozenset({"attack"})
        assert restored.deck_stages == frozenset({"scaling"})
        assert restored.any_of_relics == frozenset({"Burning Blood"})
        assert restored.requires_hand_capabilities == frozenset({"can_apply_weak"})

    def test_empty_new_fields_backward_compat(self):
        d = {"state_types": ["monster"], "enemy_names": []}
        t = SkillTrigger.from_dict(d)
        assert t.threat_levels == frozenset()
        assert t.intent_classes == frozenset()
        assert t.requires_hand_capabilities == frozenset()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_skill_trigger_situation.py -v`
Expected: FAIL — `matches()` doesn't accept `situation` kwarg

- [ ] **Step 3: Add new fields to SkillTrigger**

In `src/skills/models.py`, add 5 new fields after `tags` (line 98):

```python
    tags: frozenset[str] = frozenset()

    # Situation-level triggers (Phase 2). All empty = match all, backward compat.
    threat_levels: frozenset[str] = frozenset()    # {"high", "lethal"} — ranking signal
    intent_classes: frozenset[str] = frozenset()    # {"attack", "mixed"} — ranking signal
    deck_stages: frozenset[str] = frozenset()       # {"building", "scaling"} — ranking signal
    any_of_relics: frozenset[str] = frozenset()     # hard filter: at least ONE must be present
    requires_hand_capabilities: frozenset[str] = frozenset()  # hard filter: at least ONE must be true
```

- [ ] **Step 4: Extend matches() with situation parameter**

Add `situation` kwarg to `matches()` signature (after `context_tags`):

```python
    def matches(
        self,
        state_type: str = "",
        enemy_name: str = "",
        act: int = 1,
        hp_ratio: float = 1.0,
        deck_size: int = 0,
        hand_cards: frozenset[str] = frozenset(),
        context_tags: frozenset[str] = frozenset(),
        *,
        situation: SituationTag | None = None,
    ) -> tuple[bool, float]:
```

Add `TYPE_CHECKING` import at top of models.py:

```python
from typing import TYPE_CHECKING
# ... existing imports ...
if TYPE_CHECKING:
    from src.memory.situation import SituationTag
```

Add situation scoring block before the final `return True, max(score, 0.1)`:

```python
        # Situation-level matching (Phase 2)
        if situation is not None:
            if self.threat_levels:
                if situation.threat_level in self.threat_levels:
                    score += 2.0

            if self.intent_classes:
                if situation.intent_class in self.intent_classes:
                    score += 1.5

            if self.deck_stages:
                if situation.deck_stage in self.deck_stages:
                    score += 0.5

            if self.requires_hand_capabilities and situation.hand_capabilities:
                hc = situation.hand_capabilities
                has_any = any(getattr(hc, cap, False) for cap in self.requires_hand_capabilities)
                if not has_any:
                    return False, 0.0
                score += 1.0

        # Relic matching: any_of_relics uses context_tags (relics passed via tags)
        if self.any_of_relics:
            relic_overlap = self.any_of_relics & context_tags
            if not relic_overlap:
                return False, 0.0
            score += 0.3 * len(relic_overlap)

        return True, max(score, 0.1)
```

- [ ] **Step 5: Update to_dict() and from_dict()**

In `to_dict()`, add after `"tags"`:

```python
            "threat_levels": sorted(self.threat_levels),
            "intent_classes": sorted(self.intent_classes),
            "deck_stages": sorted(self.deck_stages),
            "any_of_relics": sorted(self.any_of_relics),
            "requires_hand_capabilities": sorted(self.requires_hand_capabilities),
```

In `from_dict()`, add after `tags=`:

```python
            threat_levels=frozenset(d.get("threat_levels", ())),
            intent_classes=frozenset(d.get("intent_classes", ())),
            deck_stages=frozenset(d.get("deck_stages", ())),
            any_of_relics=frozenset(d.get("any_of_relics", ())),
            requires_hand_capabilities=frozenset(d.get("requires_hand_capabilities", ())),
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_skill_trigger_situation.py -v`
Expected: All PASS

- [ ] **Step 7: Run full suite to check no regressions**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/skills/models.py tests/test_skill_trigger_situation.py
git commit -m "feat: add situation-level fields to SkillTrigger (threat, intent, deck_stage, relics, hand_caps)"
```

---

### Task 2: SkillLibrary.query() Passes Situation + Relic Tags

**Files:**
- Modify: `src/skills/library.py`
- Modify: `src/memory/short_term.py` (add public accessor for situation_tag)
- Modify: `src/agent/loop.py` (wire situation + add relic names to context_tags)

- [ ] **Step 1: Add situation parameter to SkillLibrary.query()**

In `src/skills/library.py`, add `situation` kwarg to `query()` (after `limit`):

```python
    def query(
        self,
        state_type: str = "",
        enemy_name: str = "",
        act: int = 1,
        hp_ratio: float = 1.0,
        deck_size: int = 0,
        hand_cards: frozenset[str] = frozenset(),
        context_tags: frozenset[str] = frozenset(),
        category: str = "",
        limit: int = 5,
        *,
        situation: SituationTag | None = None,
    ) -> list[tuple[Skill, float]]:
```

Add TYPE_CHECKING import:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.memory.situation import SituationTag
```

Pass `situation` to `trigger.matches()` (line ~115):

```python
            triggered, relevance = skill.trigger.matches(
                state_type=state_type,
                enemy_name=enemy_name,
                act=act,
                hp_ratio=hp_ratio,
                deck_size=deck_size,
                hand_cards=hand_cards,
                context_tags=context_tags,
                situation=situation,
            )
```

- [ ] **Step 2: Add public accessor to ShortTermMemory**

In `src/memory/short_term.py`, add a public method to `ShortTermMemory` (after the `get_strategic_thread` method):

```python
    def get_current_situation_tag(self):
        """Get the situation tag for the current combat round, or None."""
        if self._combat and self._combat._current_round:
            return self._combat._current_round.situation_tag
        return None
```

This avoids cross-module access to `_current_round` private attribute.

- [ ] **Step 3: Add relic names to context_tags in loop.py**

In `src/agent/loop.py`, find `_build_decision_context()` where `context_tags` is built (~line 2660-2679). After the existing tags, add relic names:

```python
            # Add relic names for any_of_relics matching (Phase 2)
            if self._cached_relics:
                for r in self._cached_relics:
                    relic_name = r.split(" (")[0]  # "Name (description)" → "Name"
                    context_tags.add(relic_name)
```

- [ ] **Step 4: Wire situation from loop.py into skill query**

In the same `_build_decision_context()` method, before the skill query call (~line 2691):

```python
            # Compute situation for skill matching (Phase 2)
            sit = None
            if gs.is_combat:
                stm = self._hcm_short_term()
                if stm:
                    sit = stm.get_current_situation_tag()

            matches = self._skill_library.query(
                state_type=gs.state_type,
                enemy_name=enemy_name,
                act=gs.act if gs.run else 1,
                hp_ratio=gs.hp_ratio,
                deck_size=len(gs.deck) if gs.deck else 0,
                hand_cards=hand_cards,
                context_tags=frozenset(context_tags),
                category=category,
                limit=config.SKILLS_MAX_PER_PROMPT,
                situation=sit,
            )
```

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/skills/library.py src/memory/short_term.py src/agent/loop.py
git commit -m "feat: pass SituationTag through skill library query + relic tags for situation-aware matching"
```

---

### Task 3: Progressive Prompt Injection

**Files:**
- Modify: `src/memory/models_v2.py`
- Modify: `src/memory/retriever.py`
- Modify: `src/memory/prompt_injector.py`
- Create: `tests/test_progressive_injection.py`

- [ ] **Step 1: Add current_round + threat_level to WorkingContext**

In `src/memory/models_v2.py`, add two fields to `WorkingContext` after `situation_hints`:

```python
    situation_hints: tuple[str, ...] = ()
    # Progressive injection metadata
    current_round: int = 0          # 0 = non-combat; >0 = combat round number
    current_threat_level: str = ""  # "lethal"|"high"|"medium"|"low"|"" (non-combat)
```

These do NOT need to be in `is_empty`, `total_hints`, or `estimated_tokens` — they're metadata, not content.

- [ ] **Step 2: Set current_round + threat_level in retriever**

In `src/memory/retriever.py`, make two changes:

**Change 2a:** Before the `if current_round > 0:` block (~line 179), initialize tracking variables:

```python
    _inject_round = current_round if decision_type == "combat" else 0
    _inject_threat = ""
```

Inside the `if current_round > 0:` block, after `current_situation` is built, capture threat:

```python
            _inject_threat = current_situation.threat_level
```

**Change 2b:** In the `wc = WorkingContext(...)` construction (~line 248), add these two fields alongside the existing ones:

```python
        situation_hints=tuple(situation_hints),
        current_round=_inject_round,
        current_threat_level=_inject_threat,
    )
```

**Change 2c:** In `_trim_working_context()` (~line 345), add these fields to the reconstruction return. They are metadata (not trimmable content), so pass them through unchanged:

```python
    return WorkingContext(
        combat_guide_hints=kept.get("combat_guide_hints", ()),
        # ... existing kept fields ...
        situation_hints=kept.get("situation_hints", ()),
        current_round=wc.current_round,
        current_threat_level=wc.current_threat_level,
    )
```

- [ ] **Step 3: Write tests for progressive injection**

Create `tests/test_progressive_injection.py`:

```python
"""Tests for progressive prompt injection (Phase 2)."""

from src.memory.models_v2 import WorkingContext
from src.memory.prompt_injector import format_working_context


class TestGuideProgression:
    def test_r1_shows_full_guide(self):
        """At R1, combat guide is shown in full."""
        wc = WorkingContext(
            combat_guide_hints=("[Guide: Nibbit] Lead with Bash to apply Vulnerable early.",),
            situation_hints=("### Similar Past Situation\n- Intent: Attack 12",),
            current_round=1,
        )
        text = format_working_context(wc)
        assert "## Enemy Intel" in text
        assert "Lead with Bash" in text

    def test_r2_plus_demotes_guide_to_summary(self):
        """At R2+, combat guide is shown as 1-line summary, not full text."""
        wc = WorkingContext(
            combat_guide_hints=("[Guide: Nibbit] Lead with Bash to apply Vulnerable early. Pommel Strike is MVP. Block is largely unnecessary. Prioritize raw damage output.",),
            situation_hints=("### Similar Past Situation\n- Intent: Attack 12",),
            current_round=3,
        )
        text = format_working_context(wc)
        # Guide should be present but truncated
        assert "## Enemy Intel" in text
        # Situation Intel should come first
        assert text.index("## Situation Intel") < text.index("## Enemy Intel")

    def test_non_combat_shows_full_guide(self):
        """Non-combat (current_round=0) shows guide normally."""
        wc = WorkingContext(
            route_guide_hints=("[Route Guide Act 1] Prioritize elites early.",),
            current_round=0,
        )
        text = format_working_context(wc)
        assert "Prioritize elites" in text


class TestThreatBanner:
    def test_high_threat_adds_survival_banner(self):
        """HIGH/LETHAL threat adds a survival priority banner."""
        wc = WorkingContext(
            situation_hints=("### Similar Past Situation",),
            current_round=2,
            current_threat_level="lethal",
        )
        text = format_working_context(wc)
        assert "SURVIVAL PRIORITY" in text

    def test_low_threat_no_banner(self):
        """LOW threat does not add survival banner."""
        wc = WorkingContext(
            situation_hints=("### Similar Past Situation",),
            current_round=2,
            current_threat_level="low",
        )
        text = format_working_context(wc)
        assert "SURVIVAL PRIORITY" not in text
```

- [ ] **Step 4: Implement progressive injection in prompt_injector.py**

Update `format_working_context()`:

```python
def format_working_context(wc: WorkingContext) -> str:
    if wc.is_empty:
        return ""

    parts: list[str] = []
    is_r2_plus = wc.current_round >= 2
    is_high_threat = wc.current_threat_level in ("high", "lethal")

    # Situation intel (highest priority at R2+)
    if wc.situation_hints:
        parts.append("## Situation Intel")
        parts.append("*Adapt to your CURRENT hand and threat level.*\n")
        if is_high_threat:
            parts.append(f"**SURVIVAL PRIORITY**: {wc.current_threat_level} threat.\n")
        for hint in wc.situation_hints:
            parts.append(hint)
        parts.append("")

    # Combat domain — demote guide at R2+
    if wc.combat_guide_hints or wc.enemy_pattern_hints:
        parts.append("## Enemy Intel")
        if is_r2_plus:
            parts.append("*Background reference — situation intel above takes priority.*\n")
        else:
            parts.append("*Adapt these insights to the current situation.*\n")
        if wc.combat_guide_hints:
            for hint in wc.combat_guide_hints:
                if is_r2_plus:
                    # Truncate to first sentence for R2+ (1-line summary)
                    first_sentence = hint.split(". ")[0] + "." if ". " in hint else hint
                    # Cap at 80 chars
                    if len(first_sentence) > 80:
                        first_sentence = first_sentence[:77] + "..."
                    parts.append(f"- {first_sentence}")
                else:
                    parts.append(f"- {hint}")
        if wc.enemy_pattern_hints:
            for hint in wc.enemy_pattern_hints:
                parts.append(hint)
        parts.append("")

    # Route domain (unchanged)
    if wc.route_guide_hints or wc.route_memory_hints:
        parts.append("## Route Intelligence")
        parts.append("*Consider these route patterns.*\n")
        if wc.route_guide_hints:
            for hint in wc.route_guide_hints:
                parts.append(f"- {hint}")
        if wc.route_memory_hints:
            parts.append("\n**Past Routes:**")
            for hint in wc.route_memory_hints:
                parts.append(f"- {hint}")
        parts.append("")

    # Deck domain (unchanged)
    if wc.deck_guide_hints or wc.deck_memory_hints:
        parts.append("## Deck Building Insights")
        parts.append("*Adapt to your current deck and situation.*\n")
        if wc.deck_guide_hints:
            for hint in wc.deck_guide_hints:
                parts.append(f"- {hint}")
        if wc.deck_memory_hints:
            parts.append("\n**Past Builds:**")
            for hint in wc.deck_memory_hints:
                parts.append(f"- {hint}")
        parts.append("")

    # Per-card insights (unchanged)
    if wc.card_memory_hints:
        parts.append("## Card-Specific Insights")
        parts.append("*Per-card experience — consider alongside your build plan.*\n")
        for hint in wc.card_memory_hints:
            parts.append(f"- {hint}")
        parts.append("")

    # Short-term context (unchanged)
    if wc.short_term_hints:
        parts.append("## Strategic Thread")
        parts.append("*Your deck-building rationale — maintain coherence across decisions.*\n")
        for hint in wc.short_term_hints:
            parts.append(hint)
        parts.append("")

    # Strategy rules (unchanged)
    if wc.rule_hints:
        parts.append("## Strategy Rules")
        for hint in wc.rule_hints:
            parts.append(f"- {hint}")
        parts.append("")

    return "\n".join(parts)
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_progressive_injection.py -v`
Expected: All PASS

- [ ] **Step 6: Run full suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/memory/models_v2.py src/memory/retriever.py src/memory/prompt_injector.py tests/test_progressive_injection.py
git commit -m "feat: progressive prompt injection — R2+ guide demotion, threat survival banner"
```

---

### Task 4: Threat-Aware Skill Filtering in Composer

**Files:**
- Modify: `src/skills/composer.py`
- Modify: `src/agent/loop.py`

- [ ] **Step 1: Add threat_level parameter to compose_skill_context**

In `src/skills/composer.py`, add `threat_level` parameter:

```python
def compose_skill_context(
    skills: list[tuple[Skill, float]],
    max_tokens: int = 900,
    *,
    threat_level: str = "",
) -> tuple[str, list[str]]:
```

Add filtering logic at the start, before the loop:

```python
    if not skills:
        return "", []

    # At HIGH/LETHAL threat, filter to survival-relevant skills only.
    # Survival skills: combat/boss category, or have threat_levels/hand_capabilities triggers.
    if threat_level in ("high", "lethal"):
        _SURVIVAL_CATEGORIES = {"combat", "boss"}
        filtered = []
        for skill, score in skills:
            is_survival_cat = skill.category in _SURVIVAL_CATEGORIES
            has_threat_trigger = bool(skill.trigger.threat_levels)
            has_hand_trigger = bool(skill.trigger.requires_hand_capabilities)
            if is_survival_cat or has_threat_trigger or has_hand_trigger:
                filtered.append((skill, score))
        # Keep at least 1 skill even if none pass filter
        if filtered:
            skills = filtered
```

- [ ] **Step 2: Wire threat_level from loop.py to composer**

In `src/agent/loop.py`, find where `compose_skill_context` is called (in `_build_decision_context`). Pass `threat_level`:

```python
            # After getting matches from skill library...
            from src.skills.composer import compose_skill_context
            threat_lvl = ""
            if sit and hasattr(sit, "threat_level"):
                threat_lvl = sit.threat_level
            skill_text, skill_ids = compose_skill_context(
                matches,
                max_tokens=config.SKILLS_MAX_TOKENS,
                threat_level=threat_lvl,
            )
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -x -q --tb=short -k "not test_real_tools_produce_hints"`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/skills/composer.py src/agent/loop.py
git commit -m "feat: threat-aware skill filtering — survival-only at HIGH/LETHAL threat"
```

---

## Self-Review

**Spec coverage:**
- Section 12 (SkillTrigger new fields): ✅ Task 1 (5 new fields + matches() + serialization)
- Section 12 (matches() scoring): ✅ Task 1 (threat +2.0, intent +1.5, deck_stage +0.5, relics +0.3, hand_caps hard filter +1.0)
- Section 11 (progressive injection R1 vs R2+): ✅ Task 3 (guide demotion, 1-line summary)
- Section 11 (HIGH/LETHAL threat banner): ✅ Task 3 (SURVIVAL PRIORITY banner)
- Section 11 (threat-aware skill filtering): ✅ Task 4 (composer filters at HIGH/LETHAL)
- Section 13 Phase 2 (library.query passes situation): ✅ Task 2
- Section 13 Phase 2 (loop.py wiring): ✅ Tasks 2 + 4

**Codex review fixes applied:**
- Q2 (any_of_relics never matches): Task 2 Step 3 adds relic names to `context_tags` from `self._cached_relics`
- Q3 (current_round/threat_level not passed to WorkingContext): Task 3 Step 2 explicitly shows retriever construction + `_trim_working_context` pass-through
- Q5 (private `_current_round` access): Task 2 Step 2 adds `ShortTermMemory.get_current_situation_tag()` public accessor; Task 2 Step 4 uses it from loop.py

**Placeholder scan:** No TBDs. All steps have code.

**Type consistency:** `SituationTag` used consistently as kwarg named `situation` in matches() and query(). `threat_level` string used in composer and prompt_injector. `current_round` int on WorkingContext. All consistent.
