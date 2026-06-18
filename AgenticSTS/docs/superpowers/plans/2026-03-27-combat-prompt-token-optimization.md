# Combat Prompt Token Optimization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce combat LLM call input from ~5000 to ~3300 tokens (-34%) by compressing conversation history, delta-injecting keyword glossary, grouping deck listings, compressing computed insights, and compacting round summaries.

**Architecture:** All changes are formatting-only — no new files, no architecture changes. Each task modifies one file's formatting logic and its corresponding test. Combat start message is untouched (critical anchor).

**Tech Stack:** Python 3.11, pytest, Anthropic Messages API

**Spec:** `docs/superpowers/specs/2026-03-27-prompt-token-optimization-design.md`

---

## File Map

| File | Change | Responsibility |
|------|--------|----------------|
| `src/brain/conversation.py` | Modify | keep_recent=1, Key Effects delta, round summary compact, protocol cleanup |
| `src/brain/prompts/_deck_fmt.py` | Modify | Grouped deck listing |
| `src/brain/tool_preprocessor.py` | Modify | Generic hint compression + deduplication |
| `src/skills/composer.py` | Modify | Skill format slimming |
| `data/evolution/tools/deck_bloat_energy_check.py` | Modify | Add APPLICABLE_STATES |
| `data/evolution/tools/rest_site_heal_vs_upgrade_v2.py` | Modify | Add APPLICABLE_STATES |
| `tests/test_conversation_compression.py` | Modify | Update keep_recent=1 expectations |
| `tests/test_token_optimization.py` | Create | New tests for delta effects, deck grouping, hint compression, skill format, round summary |

---

### Task 1: keep_recent=2 → 1

**Files:**
- Modify: `src/brain/conversation.py:562` (compress_history call in add_round_state)
- Modify: `tests/test_conversation_compression.py` (update all keep_recent=2 assertions)

- [ ] **Step 1: Update the auto-compression trigger**

In `src/brain/conversation.py`, line 563, change:
```python
            self.compress_history(keep_recent=2)
```
to:
```python
            self.compress_history(keep_recent=1)
```

- [ ] **Step 2: Update compression tests**

In `tests/test_conversation_compression.py`, update all tests that assert `keep_recent=2` behavior:

1. `test_no_compress_when_few_rounds` (line 174): change `compress_history(keep_recent=2)` to `keep_recent=1`; loop only needs `range(1, 2)` (1 round)
2. `test_compress_single_round_still_produces_summary` (line 193): change to `keep_recent=1`, needs 2 rounds (range 1..3)
3. `test_compress_6_rounds_keep_2` (line 217): rename to `test_compress_6_rounds_keep_1`, change to `keep_recent=1`, update assertions — R5 should now be in summary, only R6 kept intact
4. `test_compressed_through_prevents_recompression` (line 389): update `assert conv._compressed_through == 4` to `== 5` (6 rounds - 1 kept = 5 compressed)
5. All other explicit `compress_history(keep_recent=2)` calls: change to `keep_recent=1`

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_conversation_compression.py -v`
Expected: All pass with updated keep_recent=1 expectations.

- [ ] **Step 4: Commit**

```bash
git add src/brain/conversation.py tests/test_conversation_compression.py
git commit -m "perf: keep_recent=2→1 in combat conversation compression"
```

---

### Task 2: Key Effects Delta Injection

**Files:**
- Modify: `src/brain/conversation.py:109` (add `_injected_effects` to `__init__`)
- Modify: `src/brain/conversation.py:664-703` (Key Effects section in `add_round_state`)
- Modify: `src/brain/conversation.py:430` (reset after `compress_history`)
- Create: `tests/test_token_optimization.py` (new test file)

- [ ] **Step 1: Write failing tests**

Create `tests/test_token_optimization.py`:
```python
"""Tests for P6 prompt token optimization changes."""
from __future__ import annotations

import pytest
from tests.test_conversation_compression import _make_gs, _simulate_round
from src.brain.conversation import CombatConversation


class TestKeyEffectsDelta:
    """Key Effects should only inject new keywords, not repeat every round."""

    def test_round1_injects_all_relevant_effects(self) -> None:
        """First round should inject all matching keywords."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        conv.add_round_state(gs)

        msg_text = str(conv.messages[-1]["content"])
        assert "Key Effects" in msg_text
        # "block" and "vulnerable" should appear (from Defend + Bash rules_text)
        assert "Block:" in msg_text

    def test_round2_skips_already_injected_effects(self) -> None:
        """Second round should NOT re-inject keywords from round 1."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        # Round 1
        conv.add_round_state(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_execution_result(["Played Strike"], gs)

        # Round 2 — same hand, same effects
        gs2 = _make_gs(combat_round=2)
        conv.add_round_state(gs2)

        round2_text = str(conv.messages[-1]["content"])
        # Should NOT have Key Effects section (all effects already injected in R1)
        assert "Key Effects" not in round2_text

    def test_new_effect_injected_on_appearance(self) -> None:
        """If a new keyword appears in round 3, it should be injected."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        # Round 1 — no poison
        conv.add_round_state(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_execution_result(["Played Strike"], gs)

        # Round 2 — add a poison card to hand
        poison_cards = [
            {"index": 0, "name": "Deadly Poison", "energy_cost": 1,
             "playable": True, "rules_text": "Apply 5 poison."},
        ]
        gs2 = _make_gs(combat_round=2, hand_cards=poison_cards)
        conv.add_round_state(gs2)

        round2_text = str(conv.messages[-1]["content"])
        # "Poison:" should appear since it's new
        assert "Poison:" in round2_text

    def test_effects_reset_after_compression(self) -> None:
        """After compress_history, effects should be re-injected."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 6):
            _simulate_round(conv, r)

        # Force compression
        conv.compress_history(keep_recent=1)

        # _injected_effects should be reset
        assert len(conv._injected_effects) == 0

    def test_effects_reinjected_after_compression(self) -> None:
        """After compression resets tracking, next round re-injects effects."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 6):
            _simulate_round(conv, r)

        conv.compress_history(keep_recent=1)
        assert len(conv._injected_effects) == 0

        # Add a new round — effects should be re-injected
        gs_new = _make_gs(combat_round=6)
        conv.add_round_state(gs_new)

        round_text = str(conv.messages[-1]["content"])
        assert "Key Effects" in round_text
        assert "Block:" in round_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_token_optimization.py::TestKeyEffectsDelta -v`
Expected: FAIL — `_injected_effects` doesn't exist yet.

- [ ] **Step 3: Implement delta injection**

In `src/brain/conversation.py`:

3a. Add to `__init__` (after line 123):
```python
        self._injected_effects: set[str] = set()  # Delta tracking for Key Effects
```

3b. Replace the Key Effects section in `add_round_state` (lines 664-703) with:
```python
        # Keyword glossary — delta injection: only inject NEW keywords
        _KW_GLOSSARY = {
            "block": "Block: Absorbs damage until your next turn, then resets to 0.",
            "weak": "Weak: Target deals 25% less Attack damage for N turns.",
            "vulnerable": "Vulnerable: Target takes 50% more Attack damage for N turns.",
            "poison": (
                "Poison: Loses N HP at the start of its turn, before it acts "
                "(attack or buff), then decreases by 1. Bypasses Block."
            ),
            "strength": "Strength: Adds N damage to each Attack hit. Multi-hit cards benefit enormously.",
            "dexterity": "Dexterity: Adds N Block to each Block card.",
            "frail": "Frail: Block from cards reduced by 25%.",
            "artifact": "Artifact: Negates N debuffs. Check enemy Artifact before applying debuffs — they'll be wasted.",
            "sly": "Sly: If discarded BY A CARD EFFECT (e.g. Survivor, Acrobatics), this card is PLAYED FOR FREE. End-of-turn auto-discard does NOT trigger Sly.",
            "ethereal": "Ethereal: Exhausted if still in hand at end of turn. You must play it or lose it.",
            "retain": "Retain: Stays in hand at end of turn instead of being discarded.",
            "exhaust": "Exhaust: Removed from combat permanently after use. Thins deck mid-fight.",
            "innate": "Innate: Always in your opening hand.",
            "eternal": "Eternal: Cannot be removed or transformed from your deck.",
            "unplayable": "Unplayable: Cannot be played from hand. Only for discard/exhaust synergies.",
        }
        # Scan hand cards text
        hand_text = " ".join(
            ((c.rules_text or "") + " " + (c.name or "")).lower() for c in hand
        )
        # Also scan enemy and player powers for status effects
        powers_text = ""
        for e in alive_enemies:
            for pw in (e.powers or []):
                powers_text += " " + (pw.name or "").lower()
        if gs.combat and gs.combat.player.powers:
            for pw in gs.combat.player.powers:
                powers_text += " " + (pw.name or "").lower()
        search_text = hand_text + " " + powers_text

        # Only inject keywords not previously injected in this combat
        new_effects = [
            (kw, desc) for kw, desc in _KW_GLOSSARY.items()
            if kw in search_text and kw not in self._injected_effects
        ]
        if new_effects:
            lines.append("")
            lines.append("## Key Effects (active this combat)")
            for kw, desc in new_effects:
                lines.append(f"- {desc}")
                self._injected_effects.add(kw)
```

3c. Add reset in `compress_history`, after line 430 (`self._compressed_through = compress_up_to`):
```python
        # Reset delta tracking — old definitions lost in compression
        self._injected_effects.clear()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_token_optimization.py::TestKeyEffectsDelta -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/brain/conversation.py tests/test_token_optimization.py
git commit -m "perf: delta-inject Key Effects (skip unchanged keywords after R1)"
```

---

### Task 3: Deck Listing Grouping

**Files:**
- Modify: `src/brain/prompts/_deck_fmt.py:34-61` (format_deck_section)
- Modify: `tests/test_token_optimization.py` (add deck grouping tests)

- [ ] **Step 1: Write failing test**

Add to `tests/test_token_optimization.py`:
```python
from src.brain.prompts._deck_fmt import format_deck_section
from src.mcp_client.upstream_models import RawDeckCardPayload


class TestDeckGrouping:
    """Deck listing should group identical cards."""

    def _make_deck(self, cards: list[dict]) -> list[RawDeckCardPayload]:
        return [RawDeckCardPayload(**c) for c in cards]

    def test_groups_identical_cards(self) -> None:
        deck = self._make_deck([
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic"}
            for _ in range(5)
        ] + [
            {"name": "Defend", "energy_cost": 1, "card_type": "Skill", "rarity": "Basic"}
            for _ in range(5)
        ])
        lines = format_deck_section(deck)
        text = "\n".join(lines)
        assert "Strike x5" in text
        assert "Defend x5" in text
        # Should NOT have 5 separate "Strike" lines
        assert text.count("Strike") == 1  # Only one line with "Strike x5"

    def test_upgraded_cards_grouped_separately(self) -> None:
        deck = self._make_deck([
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic",
             "upgraded": False},
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic",
             "upgraded": False},
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic",
             "upgraded": True},
        ])
        lines = format_deck_section(deck)
        text = "\n".join(lines)
        assert "Strike x2" in text
        assert "Strike+ x1" in text

    def test_sorted_by_count_descending(self) -> None:
        deck = self._make_deck([
            {"name": "Bash", "energy_cost": 2, "card_type": "Attack", "rarity": "Basic"},
        ] + [
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack", "rarity": "Basic"}
            for _ in range(3)
        ])
        lines = format_deck_section(deck)
        text = "\n".join(lines)
        strike_pos = text.index("Strike x3")
        bash_pos = text.index("Bash x1")
        assert strike_pos < bash_pos  # Higher count first

    def test_empty_deck(self) -> None:
        lines = format_deck_section([])
        assert "empty" in "\n".join(lines).lower()

    def test_none_deck(self) -> None:
        lines = format_deck_section(None)
        assert "unknown" in "\n".join(lines).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_token_optimization.py::TestDeckGrouping -v`
Expected: FAIL — current format lists cards individually, not grouped.

- [ ] **Step 3: Implement grouped deck format**

Replace `format_deck_section` in `src/brain/prompts/_deck_fmt.py` (lines 34-61):
```python
def format_deck_section(deck: list[RawDeckCardPayload] | None) -> list[str]:
    """Format the master deck as prompt lines.

    Groups identical cards (e.g. "Strike x5") sorted by count descending
    within each card type. Upgrade markers preserved: "Strike+ x2".
    """
    if deck is None:
        return ["", "## Current Deck (unknown — data not available)"]

    if not deck:
        return ["", "## Current Deck (empty — no cards yet)"]

    lines = ["", f"## Current Deck ({len(deck)} cards)"]

    # Group by card_type
    by_type: dict[str, list[RawDeckCardPayload]] = {}
    for card in deck:
        by_type.setdefault(card.card_type, []).append(card)

    for card_type in sorted(by_type):
        cards = by_type[card_type]
        # Count by display name (with upgrade marker)
        counts: dict[str, int] = {}
        cost_map: dict[str, str] = {}
        for c in cards:
            display = c.name + ("+" if c.upgraded else "")
            counts[display] = counts.get(display, 0) + 1
            star = f" ★{c.star_cost}" if c.star_cost else ""
            cost_map[display] = f"cost={_format_cost(c)}{star}"

        # Sort by count descending, then name
        sorted_cards = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        # Include cost for unique cards (count=1) to preserve strategic info
        card_strs = []
        for name, count in sorted_cards:
            cost_info = cost_map.get(name, "")
            if count == 1 and cost_info:
                card_strs.append(f"{name}({cost_info})")
            else:
                card_strs.append(f"{name} x{count}")
        lines.append(f"  [{card_type}] {', '.join(card_strs)}")

    return lines
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_token_optimization.py::TestDeckGrouping -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Run existing tests that may use format_deck_section**

Run: `python -m pytest tests/ -v -k "deck or conversation or compression"`
Expected: All pass. (If any tests assert per-card format, update them.)

- [ ] **Step 6: Commit**

```bash
git add src/brain/prompts/_deck_fmt.py tests/test_token_optimization.py
git commit -m "perf: group identical cards in deck listing (Strike x5 vs per-card)"
```

---

### Task 4: Round Summary Compact Format

**Files:**
- Modify: `src/brain/conversation.py:221-268` (_record_round_summary)
- Modify: `tests/test_token_optimization.py` (add compact summary tests)

- [ ] **Step 1: Write failing test**

Add to `tests/test_token_optimization.py`:
```python
class TestRoundSummaryCompact:
    """Round summaries should use compact format."""

    def test_compact_format_with_kills(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        _simulate_round(conv, 1, cards_played=["Strike", "Defend", "Bash"],
                        hp_after=52, enemy_alive=False)

        summary = conv._round_summaries[0]
        # Compact: "R1: 3cards -8HP(60→52) kill:Jaw Worm"
        assert "R1:" in summary
        assert "3cards" in summary
        assert "52" in summary
        assert "kill:" in summary
        # Should NOT have verbose "Played Strike, Defend, Bash"
        assert "Played" not in summary

    def test_compact_format_no_kills(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        _simulate_round(conv, 1, cards_played=["Strike", "Defend"],
                        hp_after=55, enemy_hp_after=30)

        summary = conv._round_summaries[0]
        assert "R1:" in summary
        assert "2cards" in summary
        assert "55" in summary
        assert "kill:" not in summary

    def test_compact_no_actions(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        gs_round = _make_gs(combat_round=1)
        conv.add_round_state(gs_round)
        conv.add_assistant_plan([{"type": "text", "text": "End turn"}])
        conv.add_execution_result([], _make_gs(combat_round=1, hp=55))

        summary = conv._round_summaries[0]
        assert "0cards" in summary
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_optimization.py::TestRoundSummaryCompact -v`
Expected: FAIL — current format uses "Played Strike, Defend".

- [ ] **Step 3: Implement compact summary**

Replace `_record_round_summary` in `src/brain/conversation.py` (lines 221-269):
```python
    def _record_round_summary(
        self,
        actions_taken: list[str],
        gs_after: GameState,
    ) -> None:
        """Build a compact one-line summary for the current round.

        Format: "R1: 3cards -8HP(60→52) kill:Jaw Worm | enemies: Slime(20)"
        """
        round_num = self._round_count

        # Count cards/potions played
        n_actions = len(actions_taken)

        parts: list[str] = [f"{n_actions}cards"]

        combat = gs_after.combat
        if combat:
            p = combat.player
            parts.append(f"HP={p.current_hp}/{p.max_hp}")

            dead = [e for e in combat.enemies if not e.is_alive]
            if dead:
                parts.append("kill:" + ",".join(e.name for e in dead))

            alive = [e for e in combat.enemies if e.is_alive]
            if alive:
                parts.append(
                    "enemies:" + ",".join(
                        f"{e.name}({e.current_hp})" for e in alive
                    )
                )

        summary = f"R{round_num}: {' '.join(parts)}"
        self._round_summaries.append(summary)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_token_optimization.py::TestRoundSummaryCompact tests/test_conversation_compression.py -v`
Expected: All pass. Note: `test_summary_captures_card_names` in `test_conversation_compression.py` may fail because it asserts `"Bash" in summary` — the compact format no longer includes card names. Update that test: assert `"2cards"` instead of card names.

- [ ] **Step 5: Update broken existing tests**

In `tests/test_conversation_compression.py`:

- `test_summary_captures_card_names` (line 415-426): remove assertion for card names, assert `"R1:"` and action count format (`"2cards"`)
- `test_compress_preserves_round_summaries` (line 283-301): update assertions — summary won't contain "Neutralize" anymore, assert `"R1:"` presence instead
- `test_summary_with_no_actions` (line 438-449): change `"No actions"` assertion to `"0cards"`

- [ ] **Step 6: Commit**

```bash
git add src/brain/conversation.py tests/test_token_optimization.py tests/test_conversation_compression.py
git commit -m "perf: compact round summaries (R1: 3cards HP=52/80 kill:Slime)"
```

---

### Task 5: Computed Insights Compression + Filtering

**Files:**
- Modify: `src/brain/tool_preprocessor.py:478-500` (format_hints)
- Modify: `data/evolution/tools/deck_bloat_energy_check.py` (add APPLICABLE_STATES)
- Modify: `data/evolution/tools/rest_site_heal_vs_upgrade_v2.py` (add APPLICABLE_STATES)
- Modify: `tests/test_token_optimization.py` (add hint compression tests)

- [ ] **Step 1: Write failing test**

Add to `tests/test_token_optimization.py`:
```python
from src.brain.tool_preprocessor import ToolHint, ToolPreprocessor


class TestComputedInsightsCompression:
    """Hints should be compressed to actionable one-liners."""

    def test_extracts_priority_keys(self) -> None:
        hint = ToolHint(
            tool_name="buffer_survival_check",
            result={
                "survives": True,
                "hp_remaining": 63,
                "damage_taken": 7,
                "buffer_consumed_by": None,
                "fatal_attack": None,
                "recommendation": "GO — survives with 63 HP.",
            },
            latency_ms=5.0,
        )
        from unittest.mock import MagicMock
        pp = ToolPreprocessor(MagicMock())
        text = pp.format_hints([hint])
        # Should contain compressed form, not raw dict
        assert "recommendation" not in text.lower() or "GO" in text
        assert "{'survives'" not in text  # No raw dict dump
        assert len(text) < 200  # Compact

    def test_deduplicates_overlapping_damage_tools(self) -> None:
        hint1 = ToolHint(
            tool_name="multi_enemy_incoming_damage",
            result={"total_incoming": 12, "survives": True, "recommendation": "CAN_SKIP_BLOCK"},
            latency_ms=3.0,
        )
        hint2 = ToolHint(
            tool_name="multi_enemy_total_damage",
            result={
                "total_incoming": 12, "survives": True, "damage_taken": 5,
                "verdict": "SURVIVE", "enemy_breakdown": [{"enemy": "Slime", "total_damage": 12}],
            },
            latency_ms=3.0,
        )
        from unittest.mock import MagicMock
        pp = ToolPreprocessor(MagicMock())
        text = pp.format_hints([hint1, hint2])
        # Should only have one damage-related entry (the more detailed one)
        # The less detailed tool (multi_enemy_incoming_damage) should be dropped
        assert "multi_enemy_incoming_damage" not in text
        assert "multi_enemy_total_damage" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_optimization.py::TestComputedInsightsCompression -v`
Expected: FAIL — current format dumps raw dict.

- [ ] **Step 3: Add APPLICABLE_STATES to irrelevant tools**

In `data/evolution/tools/deck_bloat_energy_check.py`, add after the SCHEMA dict:
```python
APPLICABLE_STATES = ["card_reward", "shop", "rest", "card_select"]
```

In `data/evolution/tools/rest_site_heal_vs_upgrade_v2.py`, add after the SCHEMA dict:
```python
APPLICABLE_STATES = ["rest"]
```

- [ ] **Step 4: Implement compressed hint formatting**

Replace `format_hints` in `src/brain/tool_preprocessor.py` (lines 478-500):
```python
    def format_hints(self, hints: list[ToolHint], *, max_chars: int = 2000) -> str:
        """Format tool hints into a compact prompt section.

        Extracts actionable keys from results, deduplicates overlapping
        damage tools, and formats as concise one-liners.
        """
        if not hints:
            return ""

        # Deduplicate: if multiple tools have "total_incoming", keep the one
        # with more keys (more detailed)
        seen_incoming = False
        deduped: list[ToolHint] = []
        # Sort by key count descending so the most detailed comes first
        sorted_hints = sorted(
            hints,
            key=lambda h: len(h.result) if isinstance(h.result, dict) else 0,
            reverse=True,
        )
        for hint in sorted_hints:
            if isinstance(hint.result, dict) and "total_incoming" in hint.result:
                if seen_incoming:
                    continue  # Skip less detailed duplicate
                seen_incoming = True
            deduped.append(hint)

        _PRIORITY_KEYS = {
            "recommendation", "verdict", "decision", "note",
            "survives", "hp_remaining", "hp_after", "damage_taken",
            "total_incoming", "net_damage", "lethal_turn",
        }

        lines = ["## Computed Insights"]
        total_chars = len(lines[0])

        for hint in deduped:
            if isinstance(hint.result, dict):
                # Extract only actionable keys
                extracted = {
                    k: v for k, v in hint.result.items()
                    if k in _PRIORITY_KEYS and v is not None
                }
                if not extracted:
                    # Fallback: take first 3 keys
                    extracted = dict(list(hint.result.items())[:3])
                parts = [f"{k}={v}" for k, v in extracted.items()]
                result_str = ", ".join(parts)
            else:
                result_str = str(hint.result)[:200]

            line = f"- {hint.tool_name}: {result_str}"
            if total_chars + len(line) + 1 > max_chars:
                break
            lines.append(line)
            total_chars += len(line) + 1

        return "\n".join(lines) if len(lines) > 1 else ""
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_token_optimization.py::TestComputedInsightsCompression tests/test_tool_preprocessor.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/brain/tool_preprocessor.py data/evolution/tools/deck_bloat_energy_check.py data/evolution/tools/rest_site_heal_vs_upgrade_v2.py tests/test_token_optimization.py
git commit -m "perf: compress computed insights + filter irrelevant tools in combat"
```

---

### Task 6: Skill Format Slimming

**Files:**
- Modify: `src/skills/composer.py:39-80` (compose_skill_context format)
- Modify: `tests/test_token_optimization.py` (add skill format tests)

- [ ] **Step 1: Write failing test**

Add to `tests/test_token_optimization.py`:
```python
from src.skills.models import Skill, SkillTrigger
from src.skills.composer import compose_skill_context


class TestSkillFormatSlim:
    """Skill format should exclude examples, lessons, category, supplements."""

    def _make_skill(self, **overrides) -> Skill:
        defaults = {
            "skill_id": "test_001",
            "name": "Test Skill",
            "content": "Always block before attacking.",
            "category": "combat",
            "source": "seed",
            "confidence": 0.9,
            "verified": True,
            "usage_count": 5,
            "lessons": "Players who skip blocking take lethal damage.",
            "examples": ["With 3E: Defend first, then Strike."],
            "supplements_seed_id": "combat_basics_001",
            "trigger": SkillTrigger(state_types=frozenset({"monster", "elite", "boss"})),
        }
        defaults.update(overrides)
        return Skill(**defaults)

    def test_no_lessons_in_output(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Without this:" not in text
        assert "skip blocking" not in text

    def test_no_examples_in_output(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Example:" not in text

    def test_no_category_in_header(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "(combat," not in text

    def test_no_supplements_in_output(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "Supplements seed" not in text

    def test_confidence_still_shown(self) -> None:
        skill = self._make_skill()
        text, ids = compose_skill_context([(skill, 1.0)])
        assert "90%" in text

    def test_combat_sequence_skill_keeps_one_example(self) -> None:
        skill = self._make_skill(
            content="Sequence: play 0-cost first, then debuffs, then draw cards.",
            examples=["Example A", "Example B"],
        )
        text, ids = compose_skill_context([(skill, 1.0)])
        # Should keep 1 example for sequencing skills
        assert "Example A" in text
        # Should NOT have second example
        assert "Example B" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_token_optimization.py::TestSkillFormatSlim -v`
Expected: FAIL — current format includes lessons, examples, category.

- [ ] **Step 3: Implement slim format**

Replace the formatting loop in `src/skills/composer.py` (lines 39-80):
```python
    for skill, score in skills:
        # Format this skill — slim format (no examples, no lessons, no category)
        lines: list[str] = []
        if skill.usage_count > 0:
            confidence_str = f"{skill.confidence:.0%}"
        else:
            confidence_str = "seed" if skill.source == "seed" else "new"
        verified_str = "" if skill.verified else " ⚠unverified"
        lines.append(f"**{skill.name}** ({confidence_str}{verified_str})")
        lines.append(skill.content)

        # Exception: combat sequencing skills keep 1 example
        _SEQ_KEYWORDS = {"sequence", "order", "先", "then", "before"}
        if (
            skill.category == "combat"
            and skill.examples
            and any(kw in skill.content.lower() for kw in _SEQ_KEYWORDS)
        ):
            lines.append(f"  - Example: {skill.examples[0]}")

        lines.append("")

        block = "\n".join(lines)
        block_tokens = len(block) // 4

        # Check token budget
        if token_count + block_tokens > max_tokens:
            # Try minimal (name + content only)
            minimal = f"**{skill.name}** ({confidence_str})\n{skill.content}\n"
            minimal_tokens = len(minimal) // 4
            if token_count + minimal_tokens <= max_tokens:
                parts.append(minimal)
                included_ids.append(skill.skill_id)
                token_count += minimal_tokens
            continue

        parts.append(block)
        included_ids.append(skill.skill_id)
        token_count += block_tokens
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_token_optimization.py::TestSkillFormatSlim -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/composer.py tests/test_token_optimization.py
git commit -m "perf: slim skill format (remove examples/lessons/category/supplements)"
```

---

### Task 7: Protocol Message Cleanup

**Files:**
- Modify: `src/brain/conversation.py:184-186` (_append_user dummy assistant)
- Modify: `src/brain/conversation.py:405-408` (compress_history dummy acknowledgement)

- [ ] **Step 1: Replace verbose protocol messages**

In `src/brain/conversation.py`:

Line 185 — change `"Acknowledged."` to `"ok"`:
```python
                    "content": [{"type": "text", "text": "ok"}],
```

Line 407 — change `f"Understood. Continuing from round {compress_up_to + 1}."` to `"ok"`:
```python
                        "text": "ok",
```

- [ ] **Step 2: Update tests that check for "Continuing from round"**

In `tests/test_conversation_compression.py`:
- `test_compress_6_rounds_keep_1` (renamed in Task 1, originally line 250): change `assert "Continuing from round" in text` to `assert text == "ok"`
- Any other test asserting `"Continuing from round"` or `"Acknowledged"`: update to `"ok"`

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_conversation_compression.py -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/brain/conversation.py tests/test_conversation_compression.py
git commit -m "perf: protocol messages Acknowledged/Understood → ok"
```

---

### Task 8: Integration Verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: All tests pass. Fix any failures.

- [ ] **Step 2: Spot-check token savings**

Manually inspect a combat conversation by constructing a 6-round test and measuring message sizes:

```python
python -c "
from tests.test_conversation_compression import _make_gs, _simulate_round
from src.brain.conversation import CombatConversation

conv = CombatConversation('system prompt')
gs = _make_gs()
conv.add_combat_start(gs)
for r in range(1, 7):
    _simulate_round(conv, r)

total = sum(len(str(m.get('content', ''))) for m in conv.messages)
print(f'Total message chars after 6 rounds: {total}')
print(f'Message count: {len(conv.messages)}')
print(f'Compressed through: {conv._compressed_through}')
"
```

Expected: significantly fewer chars than baseline.

- [ ] **Step 3: Commit integration marker**

```bash
git add -A
git commit -m "perf(P6): combat prompt token optimization complete — target -34% input tokens"
```

---

## Future TODOs (Non-Combat, Not In This Plan)

The following optimizations from the spec are deferred to a future plan:

- [ ] **Skill generation validation**: 400-char content limit + LLM retry in `discovery.py` and `write_tools.py`
- [ ] **Combat card knowledge skip**: Skip card knowledge injection in combat (verify overlap first)
- [ ] **Route plan fallback compaction**: Store top-1 route on JSON parse failure
- [ ] **Non-combat prompt optimization**: Past Builds compression, RunContextView conditional injection
- [ ] **Skill format at generation time**: Prompt instructions for "no examples, no negative cases"
