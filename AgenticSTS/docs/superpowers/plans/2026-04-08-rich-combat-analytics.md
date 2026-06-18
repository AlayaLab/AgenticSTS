# Rich Combat Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enrich the post-run analysis pipeline with per-card damage/poison attribution, death cause detection, enemy power timelines, and card descriptions so the guide consolidation LLM can learn from combat outcomes.

**Architecture:** Add 3 new fields to existing data models (CombatDelta.source_description, CombatContext.player_powers, CombatRound.enemy_powers_snapshot), create a pure-computation `combat_analytics.py` module that extracts rich analytics from CombatEpisode events, and integrate the formatted output into `guide_consolidator.py`'s episode formatting.

**Tech Stack:** Python 3.12, frozen dataclasses, pytest

---

## File Structure

| File | Role |
|------|------|
| `src/memory/models_v2.py` | Add 3 fields + serialization to existing dataclasses |
| `src/memory/combat_delta.py` | Populate `source_description` and `player_powers` at capture time |
| `src/memory/short_term.py` | Capture `enemy_powers_snapshot` at round start |
| `src/memory/combat_extractor.py` | Pass through `enemy_powers_snapshot` from tracker |
| `src/memory/combat_analytics.py` | **NEW** — Pure analytics: death cause, card stats, poison, tokens, timeline |
| `src/memory/guide_consolidator.py` | Append analytics output to `_format_combat_episodes` |
| `tests/test_combat_analytics.py` | **NEW** — Tests for the analytics module |
| `tests/test_combat_delta.py` | Add tests for new fields |
| `scripts/verify_analytics.py` | **NEW** — Verification script against real episodes |

---

### Task 1: Data Model Changes — `models_v2.py`

**Files:**
- Modify: `src/memory/models_v2.py`
- Test: `tests/test_combat_delta.py`

- [ ] **Step 1: Add `source_description` to CombatDelta**

In `src/memory/models_v2.py`, add the field after `source`:

```python
# In class CombatDelta, after line "source: str = """
    source_description: str = ""      # rules_text from played card (for LLM combo reasoning)
```

Update `to_dict` — add after the `"source"` entry:

```python
        if self.source_description:
            d["source_description"] = self.source_description
```

Update `from_dict` — add to the constructor call:

```python
            source_description=d.get("source_description", ""),
```

- [ ] **Step 2: Add `player_powers` to CombatContext**

In `src/memory/models_v2.py`, add field to `CombatContext` after `enemy_lineup`:

```python
    player_powers: tuple[str, ...] = ()   # ("Noxious Fumes(2)", "Envenom(1)")
```

Update `to_dict` — add:

```python
            "player_powers": list(self.player_powers),
```

Update `from_dict` — add to the constructor call:

```python
            player_powers=tuple(d.get("player_powers", ())),
```

- [ ] **Step 3: Add `enemy_powers_snapshot` to CombatRound**

In `src/memory/models_v2.py`, add field to `CombatRound` after `situation_tag`:

```python
    enemy_powers_snapshot: tuple[tuple[str, ...], ...] = ()  # per-enemy powers at round start
```

Update `to_dict` — add inside the method, before `return d`:

```python
        if self.enemy_powers_snapshot:
            d["enemy_powers_snapshot"] = [list(ep) for ep in self.enemy_powers_snapshot]
```

Update `from_dict` — add to constructor call:

```python
            enemy_powers_snapshot=tuple(
                tuple(ep) for ep in d.get("enemy_powers_snapshot", ())
            ),
```

- [ ] **Step 4: Add serialization tests**

In `tests/test_combat_delta.py`, add after the existing serialization tests:

```python
def test_combat_delta_source_description_roundtrip():
    """source_description survives serialize/deserialize."""
    delta = CombatDelta(
        event_type="card_play",
        source="Blade Dance",
        source_description="Add 3 Shivs into your Hand. Exhaust.",
    )
    d = delta.to_dict()
    assert d["source_description"] == "Add 3 Shivs into your Hand. Exhaust."
    restored = CombatDelta.from_dict(d)
    assert restored.source_description == delta.source_description


def test_combat_delta_source_description_backward_compat():
    """Old data without source_description loads fine."""
    d = {"event_type": "card_play", "source": "Strike"}
    restored = CombatDelta.from_dict(d)
    assert restored.source_description == ""


def test_combat_context_player_powers_roundtrip():
    """player_powers survives serialize/deserialize."""
    ctx = CombatContext(
        enemy_key="Nibbit",
        character="the silent",
        player_powers=("Noxious Fumes(2)", "Envenom(1)"),
    )
    d = ctx.to_dict()
    assert d["player_powers"] == ["Noxious Fumes(2)", "Envenom(1)"]
    restored = CombatContext.from_dict(d)
    assert restored.player_powers == ctx.player_powers


def test_combat_context_player_powers_backward_compat():
    """Old data without player_powers loads fine."""
    d = {"enemy_key": "Nibbit", "character": "the silent"}
    restored = CombatContext.from_dict(d)
    assert restored.player_powers == ()


def test_combat_round_enemy_powers_snapshot_roundtrip():
    """enemy_powers_snapshot survives serialize/deserialize."""
    rnd = CombatRound(
        round_num=1,
        enemy_powers_snapshot=(("Sandpit(4)", "Strength(2)"),),
    )
    d = rnd.to_dict()
    assert d["enemy_powers_snapshot"] == [["Sandpit(4)", "Strength(2)"]]
    restored = CombatRound.from_dict(d)
    assert restored.enemy_powers_snapshot == rnd.enemy_powers_snapshot


def test_combat_round_enemy_powers_snapshot_backward_compat():
    """Old data without enemy_powers_snapshot loads fine."""
    d = {"round_num": 1, "damage_dealt": 10}
    restored = CombatRound.from_dict(d)
    assert restored.enemy_powers_snapshot == ()
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_combat_delta.py -v -x`
Expected: All new + existing tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py tests/test_combat_delta.py
git commit -m "feat: add source_description, player_powers, enemy_powers_snapshot to combat data models"
```

---

### Task 2: Populate New Fields at Capture Time

**Files:**
- Modify: `src/memory/combat_delta.py`
- Modify: `src/memory/short_term.py`
- Modify: `src/memory/combat_extractor.py`

- [ ] **Step 1: Populate `source_description` in `compute_combat_delta`**

In `src/memory/combat_delta.py`, function `compute_combat_delta`, add after the existing parameters:

```python
def compute_combat_delta(
    pre: GameState,
    post: GameState,
    event_type: str,
    source: str,
    target: str | None = None,
) -> CombatDelta | None:
```

Add a `source_description` lookup before the `# ── Assemble` section (around line 206):

```python
    # ── Source description (rules_text for played card) ─────────
    source_description = ""
    if event_type == "card_play" and pre_combat:
        for card in pre_combat.player.hand:
            if card.name == source:
                source_description = card.rules_text or ""
                break
```

Then add `source_description=source_description` to the `CombatDelta(...)` constructor call at the bottom.

- [ ] **Step 2: Populate `player_powers` in `build_combat_context`**

In `src/memory/combat_delta.py`, function `build_combat_context`, add before the `return CombatContext(...)`:

```python
    # Player powers at combat start
    player_powers: tuple[str, ...] = ()
    if combat.player.powers:
        player_powers = tuple(_format_power(p) for p in combat.player.powers)
```

Then add `player_powers=player_powers` to the `CombatContext(...)` constructor call.

- [ ] **Step 3: Add `enemy_powers_snapshot` to CombatRoundTracker and capture it**

In `src/memory/short_term.py`, add field to `CombatRoundTracker`:

```python
@dataclass
class CombatRoundTracker:
    ...
    situation_tag: SituationTag | None = None
    enemy_powers_snapshot: list[tuple[str, ...]] = field(default_factory=list)  # NEW
```

In `src/memory/short_term.py`, update `start_combat_round` to accept and store enemy powers:

```python
    def start_combat_round(
        self,
        round_num: int,
        energy: int,
        hp: int,
        enemy_intents: list[str],
        hand_cards: list[str] | None = None,
        *,
        situation_tag: SituationTag | None = None,
        enemy_powers: list[tuple[str, ...]] | None = None,
    ) -> None:
        """Begin a new round in the current combat."""
        if self._combat is not None:
            self._combat.start_round(round_num, energy, hp, enemy_intents, hand_cards)
            if situation_tag is not None:
                self._combat.set_round_situation_tag(situation_tag)
            if enemy_powers is not None and self._combat._current_round is not None:
                self._combat._current_round.enemy_powers_snapshot = list(enemy_powers)
```

- [ ] **Step 4: Pass enemy powers from agent loop**

In `src/agent/loop.py`, find the `stm.start_combat_round(...)` call (around line 2322). Add the enemy powers extraction before it:

```python
        # Capture enemy powers snapshot for analytics
        enemy_powers: list[tuple[str, ...]] | None = None
        if gs.raw and gs.raw.combat:
            enemy_powers = []
            for e in gs.raw.combat.enemies:
                powers = tuple(
                    f"{p.name}({p.amount})" if p.amount else p.name
                    for p in e.powers
                ) if e.powers else ()
                enemy_powers.append(powers)

        stm.start_combat_round(
            round_num=gs.combat_round,
            energy=gs.energy,
            hp=gs.player_hp,
            enemy_intents=intents,
            hand_cards=hand_cards,
            situation_tag=sit_tag,
            enemy_powers=enemy_powers,
        )
```

- [ ] **Step 5: Pass through in combat_extractor**

In `src/memory/combat_extractor.py`, update `_tracker_round_to_frozen`:

```python
def _tracker_round_to_frozen(r) -> CombatRound:
    """Convert a mutable CombatRoundTracker to a frozen CombatRound."""
    return CombatRound(
        round_num=r.round_num,
        energy_available=r.energy_available,
        energy_used=r.energy_used,
        hp_start=r.hp_start,
        hp_end=r.hp_end,
        block_gained=r.block_gained,
        enemy_intents=tuple(r.enemy_intents),
        cards_played=tuple(r.cards_played),
        potions_used=tuple(r.potions_used),
        damage_dealt=r.damage_dealt,
        damage_taken=r.damage_taken,
        events=tuple(r.events),
        hand_at_start=tuple(r.hand_at_start),
        situation_tag=r.situation_tag,
        enemy_powers_snapshot=tuple(
            tuple(ep) for ep in r.enemy_powers_snapshot
        ) if r.enemy_powers_snapshot else (),
    )
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_combat_delta.py -v -x`
Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memory/combat_delta.py src/memory/short_term.py src/memory/combat_extractor.py src/agent/loop.py
git commit -m "feat: populate source_description, player_powers, enemy_powers_snapshot at capture time"
```

---

### Task 3: Combat Analytics Module

**Files:**
- Create: `src/memory/combat_analytics.py`
- Create: `tests/test_combat_analytics.py`

- [ ] **Step 1: Write tests for death cause detection**

Create `tests/test_combat_analytics.py`:

```python
"""Tests for combat analytics module."""
from __future__ import annotations

import pytest

from src.memory.models_v2 import (
    CombatDelta,
    CombatEpisode,
    CombatRound,
    EnemyDelta,
)
from src.memory.combat_analytics import (
    analyze_episode,
    detect_death_cause,
    compute_card_stats,
    compute_poison_tracking,
    compute_poison_tick_per_round,
    compute_enemy_power_timeline,
    format_analytics,
)


# ── Helpers ──────────────────────────────────────────────────


def _make_episode(
    won: bool = True,
    hp_before: int = 70,
    hp_after: int = 50,
    rounds: list[CombatRound] | None = None,
) -> CombatEpisode:
    return CombatEpisode(
        enemy_key="The Insatiable",
        character="the silent",
        combat_type="boss",
        won=won,
        hp_before=hp_before,
        hp_after=hp_after,
        hp_delta=hp_after - hp_before,
        rounds=tuple(rounds or []),
    )


def _make_round(
    round_num: int = 1,
    hp_start: int = 70,
    hp_end: int = 70,
    damage_dealt: int = 0,
    damage_taken: int = 0,
    events: list[CombatDelta] | None = None,
    enemy_powers_snapshot: tuple[tuple[str, ...], ...] = (),
) -> CombatRound:
    return CombatRound(
        round_num=round_num,
        hp_start=hp_start,
        hp_end=hp_end,
        damage_dealt=damage_dealt,
        damage_taken=damage_taken,
        events=tuple(events or []),
        enemy_powers_snapshot=enemy_powers_snapshot,
    )


def _card_event(
    source: str,
    enemy_hp: int | None = None,
    poison_change: str = "",
    source_description: str = "",
    block: int | None = None,
) -> CombatDelta:
    enemy_deltas = ()
    if enemy_hp is not None or poison_change:
        powers_changed = (poison_change,) if poison_change else ()
        enemy_deltas = (EnemyDelta(
            enemy_id="E0", name="Boss", index=0,
            hp=enemy_hp, powers_changed=powers_changed,
        ),)
    return CombatDelta(
        event_type="card_play",
        source=source,
        source_description=source_description,
        enemy_deltas=enemy_deltas,
        block=block,
    )


# ── Death Cause ──────────────────────────────────────────────


class TestDeathCause:
    def test_win_returns_empty(self):
        ep = _make_episode(won=True)
        cause, detail = detect_death_cause(ep)
        assert cause == ""

    def test_hp_damage_death(self):
        r = _make_round(hp_start=10, hp_end=0, damage_taken=10)
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        cause, detail = detect_death_cause(ep)
        assert cause == "hp_damage"

    def test_sandpit_death(self):
        r = _make_round(
            hp_start=31, hp_end=0, damage_taken=0,
            enemy_powers_snapshot=(("Sandpit(1)", "Strength(2)"),),
        )
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        cause, detail = detect_death_cause(ep)
        assert cause == "sandpit"
        assert "31" in detail

    def test_mechanic_death_no_sandpit(self):
        r = _make_round(hp_start=25, hp_end=0, damage_taken=3)
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        cause, detail = detect_death_cause(ep)
        assert cause == "mechanic"


# ── Card Stats ───────────────────────────────────────────────


class TestCardStats:
    def test_basic_damage_attribution(self):
        events = [
            _card_event("Strike", enemy_hp=-6, source_description="Deal 6 damage."),
            _card_event("Strike", enemy_hp=-6, source_description="Deal 6 damage."),
            _card_event("Defend", block=8, source_description="Gain 8 Block."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        strike = next(s for s in stats if s.name == "Strike")
        assert strike.plays == 2
        assert strike.total_damage == 12

    def test_exhaust_detected_from_description(self):
        events = [
            _card_event("Blade Dance", enemy_hp=-2,
                        source_description="Add 3 Shivs into your Hand. Exhaust."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        bd = next(s for s in stats if s.name == "Blade Dance")
        assert bd.exhausts is True

    def test_poison_stacks_tracked(self):
        events = [
            _card_event("Poisoned Stab", enemy_hp=-6, poison_change="+Poison(3)",
                        source_description="Deal 6 damage. Apply 3 Poison."),
            _card_event("Deadly Poison", poison_change="Poison(3\u21925)",
                        source_description="Apply 5 Poison."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        ps = next(s for s in stats if s.name == "Poisoned Stab")
        assert ps.poison_stacks_applied == 3
        dp = next(s for s in stats if s.name == "Deadly Poison")
        assert dp.poison_stacks_applied == 2  # 5 - 3


# ── Poison Tick ──────────────────────────────────────────────


class TestPoisonTick:
    def test_tick_is_unattributed_damage(self):
        events = [_card_event("Defend", block=8)]
        r = _make_round(
            damage_dealt=15,  # total round damage
            events=events,    # 0 damage from events
        )
        ep = _make_episode(rounds=[r])
        ticks = compute_poison_tick_per_round(ep)
        assert ticks == (15,)

    def test_no_tick_when_events_match(self):
        events = [_card_event("Strike", enemy_hp=-10)]
        r = _make_round(damage_dealt=10, events=events)
        ep = _make_episode(rounds=[r])
        ticks = compute_poison_tick_per_round(ep)
        assert ticks == (0,)


# ── Enemy Power Timeline ────────────────────────────────────


class TestEnemyPowerTimeline:
    def test_sandpit_timeline(self):
        rounds = [
            _make_round(round_num=1, enemy_powers_snapshot=(("Sandpit(4)",),)),
            _make_round(round_num=2, enemy_powers_snapshot=(("Sandpit(3)",),)),
            _make_round(round_num=3, enemy_powers_snapshot=(("Sandpit(2)",),)),
        ]
        ep = _make_episode(rounds=rounds)
        timeline = compute_enemy_power_timeline(ep)
        assert len(timeline) == 3
        assert timeline[0]["Sandpit"] == "4"
        assert timeline[2]["Sandpit"] == "2"


# ── Format ───────────────────────────────────────────────────


class TestFormat:
    def test_format_includes_death_cause(self):
        r = _make_round(
            hp_start=31, hp_end=0, damage_taken=0,
            enemy_powers_snapshot=(("Sandpit(1)",),),
        )
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        text = format_analytics(ep)
        assert "sandpit" in text.lower() or "Sandpit" in text

    def test_format_empty_for_no_events(self):
        r = _make_round()
        ep = _make_episode(rounds=[r])
        text = format_analytics(ep)
        # Should still produce basic output (death cause at minimum)
        assert isinstance(text, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_combat_analytics.py -v -x`
Expected: FAIL (module `combat_analytics` not found).

- [ ] **Step 3: Create `combat_analytics.py` implementation**

Create `src/memory/combat_analytics.py`:

```python
"""Combat analytics: extract rich insights from CombatEpisode events.

Pure computation module — no I/O, no LLM calls. Converts raw CombatDelta
event data into structured analytics for post-run LLM consumption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from src.memory.models_v2 import CombatDelta, CombatEpisode, CombatRound


# ── Data Models ──────────────────────────────────────────────


@dataclass(frozen=True)
class CardStats:
    """Aggregated stats for a single card across the fight."""

    name: str = ""
    description: str = ""           # rules_text
    plays: int = 0
    total_damage: int = 0           # sum of enemy HP deltas
    total_block: int = 0            # player block gained
    poison_stacks_applied: int = 0  # sum of Poison delta
    exhausts: bool = False          # "Exhaust" in description
    tokens_generated: int = 0       # parsed from "Add N Shivs" etc.


@dataclass(frozen=True)
class CombatAnalytics:
    """Rich analytics extracted from a single CombatEpisode."""

    death_cause: str = ""           # "hp_damage" | "sandpit" | "mechanic" | ""
    death_detail: str = ""
    card_stats: tuple[CardStats, ...] = ()
    poison_by_card: tuple[tuple[str, int], ...] = ()   # (card_name, stacks)
    poison_tick_per_round: tuple[int, ...] = ()
    enemy_power_timeline: tuple[dict[str, str], ...] = ()
    unique_cards_with_desc: tuple[tuple[str, str], ...] = ()
    active_powers: tuple[str, ...] = ()


# ── Poison Parsing ───────────────────────────────────────────

_RE_POISON_NEW = re.compile(r"\+Poison\((\d+)\)")
_RE_POISON_CHANGE = re.compile(r"Poison\((\d+)\u2192(\d+)\)")
_RE_TOKEN_GEN = re.compile(r"Add (\d+) Shivs?", re.IGNORECASE)


def _parse_poison_delta(power_str: str) -> int:
    """Parse poison stacks added from a powers_changed entry."""
    m = _RE_POISON_NEW.match(power_str)
    if m:
        return int(m.group(1))
    m = _RE_POISON_CHANGE.match(power_str)
    if m:
        return max(0, int(m.group(2)) - int(m.group(1)))
    return 0


def _parse_token_count(description: str) -> int:
    """Parse token generation count from rules_text."""
    m = _RE_TOKEN_GEN.search(description)
    return int(m.group(1)) if m else 0


# ── Power Snapshot Parsing ───────────────────────────────────

_RE_POWER_VALUE = re.compile(r"^(.+?)\((-?\d+)\)$")


def _parse_power_snapshot(
    snapshot: tuple[tuple[str, ...], ...],
) -> dict[str, str]:
    """Extract power name→value map from enemy_powers_snapshot.

    Merges all enemies into one dict. For multi-enemy fights, prefixes
    with enemy index if there are duplicates.
    """
    result: dict[str, str] = {}
    for enemy_idx, powers in enumerate(snapshot):
        for p in powers:
            m = _RE_POWER_VALUE.match(p)
            if m:
                name, val = m.group(1), m.group(2)
                if name in result and len(snapshot) > 1:
                    result[f"{name}[{enemy_idx}]"] = val
                else:
                    result[name] = val
    return result


# ── Death Cause Detection ────────────────────────────────────


def detect_death_cause(episode: CombatEpisode) -> tuple[str, str]:
    """Determine how the agent died.

    Returns (cause, detail) where cause is one of:
    - "": not a death (won or hp_after > 0)
    - "hp_damage": killed by enemy damage
    - "sandpit": killed by Sandpit death timer
    - "mechanic": killed by unknown mechanic (HP was healthy)
    """
    if episode.won or episode.hp_after > 0:
        return ("", "")

    if not episode.rounds:
        return ("hp_damage", "No round data available.")

    last = episode.rounds[-1]

    # Check if HP damage explains the death
    if last.hp_start <= last.damage_taken + 5:
        return (
            "hp_damage",
            f"Killed by damage. HP {last.hp_start} -> 0, "
            f"took {last.damage_taken} damage.",
        )

    # HP was healthy but died — check for Sandpit
    if last.enemy_powers_snapshot:
        for powers in last.enemy_powers_snapshot:
            for p in powers:
                if "Sandpit" in p:
                    return (
                        "sandpit",
                        f"Sandpit timer reached 0. "
                        f"HP was {last.hp_start} when killed.",
                    )

    return (
        "mechanic",
        f"Died with HP={last.hp_start}, "
        f"damage_taken={last.damage_taken}. Likely mechanic kill.",
    )


# ── Per-Card Stats ───────────────────────────────────────────


def compute_card_stats(episode: CombatEpisode) -> tuple[CardStats, ...]:
    """Aggregate per-card damage, block, poison, and metadata."""
    # Accumulators: name -> {plays, damage, block, poison, desc, exhausts, tokens}
    acc: dict[str, dict[str, Any]] = {}

    for rnd in episode.rounds:
        for ev in rnd.events:
            if ev.event_type not in ("card_play", "potion_use"):
                continue

            name = ev.source
            if not name:
                continue

            if name not in acc:
                desc = ev.source_description or ""
                acc[name] = {
                    "plays": 0,
                    "damage": 0,
                    "block": 0,
                    "poison": 0,
                    "desc": desc,
                    "exhausts": "Exhaust" in desc,
                    "tokens": _parse_token_count(desc),
                }

            entry = acc[name]
            if ev.event_type == "card_play":
                entry["plays"] += 1

            # Damage from enemy HP deltas
            for ed in ev.enemy_deltas:
                if ed.hp is not None and ed.hp < 0:
                    entry["damage"] += abs(ed.hp)
                # Poison stacks
                for p in ed.powers_changed:
                    stacks = _parse_poison_delta(p)
                    if stacks > 0:
                        entry["poison"] += stacks

            # Block from player delta
            if ev.block is not None and ev.block > 0:
                entry["block"] += ev.block

    return tuple(
        CardStats(
            name=name,
            description=data["desc"],
            plays=data["plays"],
            total_damage=data["damage"],
            total_block=data["block"],
            poison_stacks_applied=data["poison"],
            exhausts=data["exhausts"],
            tokens_generated=data["tokens"],
        )
        for name, data in sorted(acc.items(), key=lambda x: -x[1]["damage"])
    )


# ── Poison Tracking ──────────────────────────────────────────


def compute_poison_tracking(
    episode: CombatEpisode,
) -> tuple[tuple[str, int], ...]:
    """Per-card poison stacks applied across the fight."""
    poison_map: dict[str, int] = {}
    for rnd in episode.rounds:
        for ev in rnd.events:
            if not ev.source:
                continue
            for ed in ev.enemy_deltas:
                for p in ed.powers_changed:
                    stacks = _parse_poison_delta(p)
                    if stacks > 0:
                        poison_map[ev.source] = poison_map.get(ev.source, 0) + stacks

    return tuple(sorted(poison_map.items(), key=lambda x: -x[1]))


def compute_poison_tick_per_round(
    episode: CombatEpisode,
) -> tuple[int, ...]:
    """Per-round unattributed damage (poison ticks + power effects).

    Computed as: round.damage_dealt - sum(event enemy HP deltas).
    """
    ticks: list[int] = []
    for rnd in episode.rounds:
        event_dmg = 0
        for ev in rnd.events:
            for ed in ev.enemy_deltas:
                if ed.hp is not None and ed.hp < 0:
                    event_dmg += abs(ed.hp)
        tick = max(0, rnd.damage_dealt - event_dmg)
        ticks.append(tick)
    return tuple(ticks)


# ── Enemy Power Timeline ────────────────────────────────────


def compute_enemy_power_timeline(
    episode: CombatEpisode,
) -> tuple[dict[str, str], ...]:
    """Per-round enemy power values from snapshots."""
    timeline: list[dict[str, str]] = []
    for rnd in episode.rounds:
        if rnd.enemy_powers_snapshot:
            timeline.append(_parse_power_snapshot(rnd.enemy_powers_snapshot))
        else:
            timeline.append({})
    return tuple(timeline)


# ── Token Attribution ────────────────────────────────────────


def compute_token_attribution(
    episode: CombatEpisode,
    active_powers: tuple[str, ...] = (),
) -> dict[str, dict[str, int]]:
    """Attribute token plays (Shivs) to generator sources.

    Returns {generator_name: {"generated": N, "attributed_damage": D}}.
    """
    # Detect active start-of-turn generators from powers
    ib_active = any("Infinite Blades" in p for p in active_powers)

    result: dict[str, dict[str, int]] = {}
    total_shiv_damage = 0
    total_shiv_plays = 0

    for rnd in episode.rounds:
        round_generators: dict[str, int] = {}  # generator -> count this round
        round_shiv_plays = 0
        round_shiv_damage = 0

        # Start-of-turn generators
        if ib_active:
            round_generators["Infinite Blades"] = round_generators.get("Infinite Blades", 0) + 1

        for ev in rnd.events:
            if ev.event_type != "card_play":
                continue
            name = ev.source
            desc = ev.source_description or ""

            # Check if this card generates tokens
            token_count = _parse_token_count(desc)
            if token_count > 0:
                round_generators[name] = round_generators.get(name, 0) + token_count

            # Count Shiv plays and damage
            if name == "Shiv" or name == "Shiv+":
                round_shiv_plays += 1
                for ed in ev.enemy_deltas:
                    if ed.hp is not None and ed.hp < 0:
                        round_shiv_damage += abs(ed.hp)

        total_shiv_plays += round_shiv_plays
        total_shiv_damage += round_shiv_damage

        # Attribute Shivs to generators (by declared generation count)
        remaining = round_shiv_plays
        for gen_name, gen_count in round_generators.items():
            attributed = min(gen_count, remaining)
            if attributed > 0:
                if gen_name not in result:
                    result[gen_name] = {"generated": 0, "attributed_damage": 0}
                result[gen_name]["generated"] += attributed
                remaining -= attributed

        # Leftover Shivs (from unknown sources)
        if remaining > 0:
            if "other" not in result:
                result["other"] = {"generated": 0, "attributed_damage": 0}
            result["other"]["generated"] += remaining

    # Distribute damage proportionally based on generated counts
    total_gen = sum(v["generated"] for v in result.values())
    if total_gen > 0 and total_shiv_damage > 0:
        avg_shiv_dmg = total_shiv_damage / max(1, total_shiv_plays)
        for gen_data in result.values():
            gen_data["attributed_damage"] = round(gen_data["generated"] * avg_shiv_dmg)

    return result


# ── Main Analyzer ────────────────────────────────────────────


def analyze_episode(episode: CombatEpisode) -> CombatAnalytics:
    """Run full analytics on a single episode."""
    has_events = any(rnd.events for rnd in episode.rounds)
    if not has_events:
        death_cause, death_detail = detect_death_cause(episode)
        return CombatAnalytics(death_cause=death_cause, death_detail=death_detail)

    death_cause, death_detail = detect_death_cause(episode)
    card_stats = compute_card_stats(episode)
    poison_tracking = compute_poison_tracking(episode)
    tick_per_round = compute_poison_tick_per_round(episode)
    timeline = compute_enemy_power_timeline(episode)

    # Collect unique cards with descriptions
    cards_seen: dict[str, str] = {}
    for rnd in episode.rounds:
        for ev in rnd.events:
            if ev.event_type == "card_play" and ev.source and ev.source not in cards_seen:
                cards_seen[ev.source] = ev.source_description or ""

    # Active powers from CombatContext
    active_powers: tuple[str, ...] = ()
    if episode.context and episode.context.player_powers:
        active_powers = episode.context.player_powers

    return CombatAnalytics(
        death_cause=death_cause,
        death_detail=death_detail,
        card_stats=card_stats,
        poison_by_card=poison_tracking,
        poison_tick_per_round=tick_per_round,
        enemy_power_timeline=timeline,
        unique_cards_with_desc=tuple(cards_seen.items()),
        active_powers=active_powers,
    )


# ── Text Formatter ───────────────────────────────────────────


def format_analytics(episode: CombatEpisode) -> str:
    """Format episode analytics as text for LLM consumption."""
    analytics = analyze_episode(episode)
    result_str = "WIN" if episode.won else "LOSS"
    lines: list[str] = []
    lines.append(
        f"## Combat Analytics: {episode.enemy_key} "
        f"({result_str} - {len(episode.rounds)} rounds)"
    )

    # Death cause
    if analytics.death_cause:
        lines.append(f"Death cause: {analytics.death_detail}")

    # Cards played with descriptions
    if analytics.unique_cards_with_desc:
        lines.append("\nCards played (with descriptions):")
        for name, desc in analytics.unique_cards_with_desc:
            stat = next((s for s in analytics.card_stats if s.name == name), None)
            parts: list[str] = []
            if stat:
                parts.append(f"{stat.plays} plays")
                if stat.total_damage > 0:
                    parts.append(f"{stat.total_damage} dmg")
                if stat.total_block > 0:
                    parts.append(f"{stat.total_block} block")
                if stat.poison_stacks_applied > 0:
                    parts.append(f"+{stat.poison_stacks_applied} poison")
                if stat.exhausts:
                    parts.append("EXHAUST")
                if stat.tokens_generated > 0:
                    parts.append(f"generates {stat.tokens_generated} Shivs")
            stat_str = ", ".join(parts) if parts else ""
            desc_str = f' "{desc}"' if desc else ""
            lines.append(f"  {name}{desc_str} -> {stat_str}")

    # Active player powers
    if analytics.active_powers:
        lines.append(f"\nActive powers: {', '.join(analytics.active_powers)}")

    # Poison tracking
    if analytics.poison_by_card:
        lines.append("\nPoison stacks applied per card:")
        for card_name, stacks in analytics.poison_by_card:
            lines.append(f"  {card_name}: {stacks} stacks")
        total_tick = sum(analytics.poison_tick_per_round)
        if total_tick > 0:
            tick_parts = [
                f"R{i + 1}:{t}" for i, t in enumerate(analytics.poison_tick_per_round) if t > 0
            ]
            lines.append(f"Total poison/power tick damage: {total_tick}")
            lines.append(f"  Per round: {' '.join(tick_parts)}")

    # Enemy power timeline
    has_timeline = any(t for t in analytics.enemy_power_timeline)
    if has_timeline:
        # Find powers that change across rounds
        all_powers: set[str] = set()
        for t in analytics.enemy_power_timeline:
            all_powers.update(t.keys())
        if all_powers:
            lines.append("\nEnemy power timeline:")
            for power_name in sorted(all_powers):
                values = [
                    t.get(power_name, "-") for t in analytics.enemy_power_timeline
                ]
                line = " -> ".join(
                    f"R{i + 1}:{v}" for i, v in enumerate(values)
                )
                lines.append(f"  {power_name}: {line}")

    # Unattributed damage per round (even without poison, this catches power effects)
    tick_total = sum(analytics.poison_tick_per_round)
    if tick_total > 0 and not analytics.poison_by_card:
        tick_parts = [
            f"R{i + 1}:{t}" for i, t in enumerate(analytics.poison_tick_per_round) if t > 0
        ]
        lines.append(f"\nUnattributed damage (power/passive effects): {tick_total}")
        lines.append(f"  Per round: {' '.join(tick_parts)}")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_combat_analytics.py -v -x`
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/combat_analytics.py tests/test_combat_analytics.py
git commit -m "feat: add combat_analytics module — death cause, card stats, poison, timeline"
```

---

### Task 4: Integrate into Guide Consolidator

**Files:**
- Modify: `src/memory/guide_consolidator.py`

- [ ] **Step 1: Add analytics import and append to `_format_combat_episodes`**

In `src/memory/guide_consolidator.py`, add import at the top:

```python
from src.memory.combat_analytics import format_analytics
```

Then modify `_format_combat_episodes` — add after the existing "Cleanest wins" section (before `return "\n".join(lines)`, around line 128):

```python
    # ── Rich analytics for recent episodes with events data ──
    for ep in episodes[-3:]:
        has_events = any(rnd.events for rnd in ep.rounds)
        if has_events:
            analytics_text = format_analytics(ep)
            if analytics_text:
                lines.append("")
                lines.append(analytics_text)
```

- [ ] **Step 2: Update guide prompt focus points**

In `build_combat_guide_prompt`, extend the "Focus on:" section (around line 165) to include analytics-aware points:

```python
    return f"""You are analyzing combat data from a Slay the Spire 2 AI agent.

Enemy: {enemy_key}
Character: {character}
{existing_text}
{episode_text}

{guide_request}

Focus on:
1. What round-level action patterns produced LOW HP LOSS, not just wins.
2. What went wrong in losses and in high-damage winning rounds.
3. Key sequencing advice (what to play first on attack rounds vs buff rounds).
4. Block vs damage balance for this enemy, with HP preservation prioritized.
5. Any patterns in enemy behavior to exploit.
6. Death cause analysis — was the death from direct damage or a mechanic like Sandpit? What could prevent it?
7. Card value in boss fights — which cards contributed most total damage? Which exhaust cards had limited impact?
8. Enemy mechanic management — how well were time-critical mechanics (Sandpit etc.) handled?

Important:
- Do NOT treat a card as bad merely because it appears less often in wins.
- Prefer conclusions supported by the cleanest wins and lowest-damage rounds.
- If aggressive lines win but lose more HP, say so explicitly instead of recommending them unconditionally.
- Avoid overfitting to raw card frequency when deck composition differs across episodes.
- Pay attention to card descriptions to understand indirect effects (e.g. draw-triggered poison, poison multiplication).
- Exhaust cards can only be played once per fight — evaluate their total-fight contribution, not per-play damage.

Respond with JSON:
{response_schema}

Keep the guide_text under 250 words. Be specific to this enemy, not generic combat advice."""
```

Note: word limit increased from 200 to 250 to accommodate the richer analytics.

- [ ] **Step 3: Run existing tests**

Run: `python -m pytest tests/ -v -x -k "combat"`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/memory/guide_consolidator.py
git commit -m "feat: integrate combat analytics into guide consolidation pipeline"
```

---

### Task 5: Verification Script

**Files:**
- Create: `scripts/verify_analytics.py`

- [ ] **Step 1: Create verification script**

Create `scripts/verify_analytics.py`:

```python
"""Verify combat analytics against real episode data.

Usage:
    python -m scripts.verify_analytics                    # All Insatiable episodes
    python -m scripts.verify_analytics --enemy "Fogmog"   # Specific enemy
    python -m scripts.verify_analytics --last 5            # Last 5 episodes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.models_v2 import CombatEpisode
from src.memory.combat_analytics import analyze_episode, format_analytics


def load_episodes(path: Path, enemy_filter: str = "") -> list[CombatEpisode]:
    """Load episodes from JSONL file."""
    episodes: list[CombatEpisode] = []
    with open(path) as f:
        for line in f:
            data = json.loads(line)
            if enemy_filter and enemy_filter.lower() not in data.get("enemy_key", "").lower():
                continue
            episodes.append(CombatEpisode.from_dict(data))
    return episodes


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify combat analytics")
    parser.add_argument("--enemy", default="insatiable", help="Enemy name filter")
    parser.add_argument("--last", type=int, default=5, help="Number of recent episodes")
    parser.add_argument("--all", action="store_true", help="Show all episodes")
    args = parser.parse_args()

    data_path = Path("data/memory/v2/combat_episodes.jsonl")
    if not data_path.exists():
        print(f"File not found: {data_path}")
        return

    episodes = load_episodes(data_path, args.enemy)
    print(f"Found {len(episodes)} episodes matching '{args.enemy}'")

    if not args.all:
        episodes = episodes[-args.last:]

    for ep in episodes:
        has_events = any(rnd.events for rnd in ep.rounds)
        analytics = analyze_episode(ep)

        print(f"\n{'=' * 60}")
        print(f"Run: {ep.run_id[:20]} | {'WIN' if ep.won else 'LOSS'} | "
              f"{len(ep.rounds)} rounds | HP {ep.hp_before}->{ep.hp_after} | "
              f"Events: {'YES' if has_events else 'NO'}")

        if analytics.death_cause:
            print(f"Death: {analytics.death_cause} - {analytics.death_detail}")

        if has_events:
            text = format_analytics(ep)
            print(text)

        # Sanity checks
        if has_events:
            total_card_dmg = sum(s.total_damage for s in analytics.card_stats)
            total_round_dmg = sum(r.damage_dealt for r in ep.rounds)
            total_tick = sum(analytics.poison_tick_per_round)
            print(f"\n[Sanity] card_dmg={total_card_dmg} + tick={total_tick} "
                  f"vs round_total={total_round_dmg} "
                  f"(diff={total_round_dmg - total_card_dmg - total_tick})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run verification**

Run: `python -m scripts.verify_analytics --enemy insatiable --last 3`

Expected: Formatted analytics output for 3 recent Insatiable episodes. Review:
- Death cause correctly identifies Sandpit vs HP deaths
- Per-card damage sums approximately match round totals
- Poison stacks per card are non-negative
- Enemy power timeline shows Sandpit countdown
- No crashes on episodes without events data

- [ ] **Step 3: Commit**

```bash
git add scripts/verify_analytics.py
git commit -m "feat: add combat analytics verification script"
```

---

### Task 6: Final Integration Test

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v -x`
Expected: All tests PASS.

- [ ] **Step 2: Run verification against diverse enemies**

```bash
python -m scripts.verify_analytics --enemy insatiable --last 3
python -m scripts.verify_analytics --enemy "Corpse Slug" --last 2
python -m scripts.verify_analytics --enemy "Terror Eel" --last 2
```

Review analytics output for quality and accuracy across different fight types.

- [ ] **Step 3: Commit all**

```bash
git add -A
git commit -m "feat: rich combat analytics — death cause, card attribution, poison tracking, enemy timeline

Gives post-run LLM visibility into why fights were won/lost:
- Death cause detection (Sandpit vs HP damage)
- Per-card damage and poison attribution from CombatDelta events
- Per-round poison tick damage (unattributed)
- Enemy power timeline (Sandpit countdown, Strength scaling)
- Card descriptions for indirect effect reasoning (Envenom, Catalyst, etc.)
- Token attribution (Blade Dance vs Infinite Blades Shivs)"
```
