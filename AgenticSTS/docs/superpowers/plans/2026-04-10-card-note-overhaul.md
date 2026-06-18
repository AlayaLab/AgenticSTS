# Card Note System Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Unify `seed_note`/`combat_hint`/`live_summary` into a single `note` field, inject card mechanics into evolution context, enhance combat digest with per-action deltas, and inject card notes into combat prompts.

**Architecture:** Single-authority `note` field on `CardMemory`. `card_memories.json` is the only runtime source. Seeds are bootstrap-only. Evolution LLM sees card `rules_text` from logs + enhanced combat deltas + relic context. Combat agent sees deck card notes at COMBAT_START, temporary card notes in subsequent rounds.

**Tech Stack:** Python 3.14, frozen dataclasses, JSONL log parsing, existing `CombatConversation` / `EvolutionEngine` / `CardMemoryStore` infrastructure.

**Spec:** `docs/superpowers/specs/2026-04-10-card-note-system-overhaul-design.md`

---

### Task 1: Unify CardMemory model — replace three fields with `note`

**Files:**
- Modify: `src/memory/models_v2.py:826-978`
- Modify: `tests/test_card_memory.py:16-98`

- [ ] **Step 1: Update tests for the new `note` field**

Replace all test references to `seed_note`, `combat_hint`, `live_summary` with `note`:

```python
# tests/test_card_memory.py — class TestCardMemory

def test_effective_note_returns_note(self):
    cm = CardMemory(
        character="the silent",
        card_name="backstab",
        note="0-cost innate damage. Strong opener in all matchups.",
    )
    assert cm.effective_note() == "0-cost innate damage. Strong opener in all matchups."

def test_effective_note_empty_when_no_content(self):
    cm = CardMemory(character="the silent", card_name="backstab")
    assert cm.effective_note() == ""

def test_has_content(self):
    assert CardMemory(note="x").has_content
    assert not CardMemory().has_content

def test_merge_run_stats(self):
    cm = CardMemory(
        character="the silent",
        card_name="backstab",
        note="innate damage",
        play_count=10,
        runs_won=2,
        runs_died_act1=1,
        sample_count=3,
    )
    # Victory
    merged = cm.merge_run_stats(
        play_count=5, draw_count=8, unplayed_draw_count=3,
        total_damage=40, victory=True, picked=True,
    )
    assert merged.play_count == 15
    assert merged.runs_won == 3
    assert merged.runs_died_act1 == 1
    assert merged.pick_count == 1
    assert merged.sample_count == 4
    assert merged.note == "innate damage"  # preserved

    # Act 2 death
    merged2 = cm.merge_run_stats(play_count=3, victory=False, final_act=2)
    assert merged2.runs_died_act2 == 1

    # Incomplete run
    merged3 = cm.merge_run_stats(play_count=3, victory=False, final_act=3, incomplete=True)
    assert merged3.runs_died_act3 == 0
    assert merged3.runs_incomplete == 1

def test_serialization_roundtrip(self):
    cm = CardMemory(
        character="the silent", card_name="backstab",
        note="innate", play_count=10, total_damage=200,
    )
    d = cm.to_dict()
    restored = CardMemory.from_dict(d)
    assert restored.note == "innate"
    assert restored.play_count == 10

def test_from_dict_migrates_legacy_fields(self):
    """Backward compat: live_summary > seed_note > empty."""
    # live_summary wins
    d1 = {"card_name": "x", "seed_note": "old", "live_summary": "new"}
    assert CardMemory.from_dict(d1).note == "new"
    # seed_note fallback
    d2 = {"card_name": "x", "seed_note": "old"}
    assert CardMemory.from_dict(d2).note == "old"
    # empty
    d3 = {"card_name": "x"}
    assert CardMemory.from_dict(d3).note == ""
    # new format preserved
    d4 = {"card_name": "x", "note": "direct"}
    assert CardMemory.from_dict(d4).note == "direct"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_card_memory.py::TestCardMemory -v`
Expected: FAIL — `CardMemory` still has old fields.

- [ ] **Step 3: Update CardMemory dataclass**

In `src/memory/models_v2.py`, replace the three text fields and update all methods:

```python
@dataclass(frozen=True)
class CardMemory:
    """Per-card longitudinal memory keyed by (character, card_name).

    Tracks a single ``note`` field (bootstrap from seed, updated by evolution LLM)
    plus deterministic run evidence counters.
    """

    character: str = ""
    card_name: str = ""            # canonical lowercase, e.g. "backstab"
    note: str = ""                 # single source of truth (seed bootstrap → LLM-updated)
    # ── Deterministic counters ───────────────────────────────
    pick_count: int = 0
    buy_count: int = 0
    play_count: int = 0
    sly_play_count: int = 0
    draw_count: int = 0
    unplayed_draw_count: int = 0
    total_damage: int = 0
    total_block: int = 0
    total_energy_gain: int = 0
    debuffs_applied: int = 0
    powers_applied: int = 0
    runs_won: int = 0
    runs_died_act1: int = 0
    runs_died_act2: int = 0
    runs_died_act3: int = 0
    runs_incomplete: int = 0
    sample_count: int = 0
    last_updated: float = field(default_factory=_now)

    def effective_note(self) -> str:
        """Return the note for prompt injection."""
        return self.note

    @property
    def has_content(self) -> bool:
        """Whether this memory has any useful info for injection."""
        return bool(self.note)

    def to_dict(self) -> dict[str, Any]:
        return {
            "character": self.character,
            "card_name": self.card_name,
            "note": self.note,
            "pick_count": self.pick_count,
            "buy_count": self.buy_count,
            "play_count": self.play_count,
            "sly_play_count": self.sly_play_count,
            "draw_count": self.draw_count,
            "unplayed_draw_count": self.unplayed_draw_count,
            "total_damage": self.total_damage,
            "total_block": self.total_block,
            "total_energy_gain": self.total_energy_gain,
            "debuffs_applied": self.debuffs_applied,
            "powers_applied": self.powers_applied,
            "runs_won": self.runs_won,
            "runs_died_act1": self.runs_died_act1,
            "runs_died_act2": self.runs_died_act2,
            "runs_died_act3": self.runs_died_act3,
            "runs_incomplete": self.runs_incomplete,
            "sample_count": self.sample_count,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CardMemory:
        # Migration: note > live_summary > seed_note
        note = d.get("note") or d.get("live_summary") or d.get("seed_note", "")
        return cls(
            character=d.get("character", ""),
            card_name=d.get("card_name", ""),
            note=note,
            pick_count=d.get("pick_count", 0),
            buy_count=d.get("buy_count", 0),
            play_count=d.get("play_count", 0),
            sly_play_count=d.get("sly_play_count", 0),
            draw_count=d.get("draw_count", 0),
            unplayed_draw_count=d.get("unplayed_draw_count", 0),
            total_damage=d.get("total_damage", 0),
            total_block=d.get("total_block", 0),
            total_energy_gain=d.get("total_energy_gain", 0),
            debuffs_applied=d.get("debuffs_applied", 0),
            powers_applied=d.get("powers_applied", 0),
            runs_won=d.get("runs_won", d.get("victory_runs", 0)),
            runs_died_act1=d.get("runs_died_act1", 0),
            runs_died_act2=d.get("runs_died_act2", 0),
            runs_died_act3=d.get("runs_died_act3", 0),
            runs_incomplete=d.get("runs_incomplete", 0),
            sample_count=d.get("sample_count", 0),
            last_updated=d.get("last_updated", _now()),
        )

    def merge_run_stats(self, *, play_count=0, sly_play_count=0, draw_count=0,
                        unplayed_draw_count=0, total_damage=0, total_block=0,
                        total_energy_gain=0, debuffs_applied=0, powers_applied=0,
                        victory=False, final_act=0, incomplete=False,
                        picked=False, bought=False) -> CardMemory:
        """Return a new CardMemory with this run's stats merged in."""
        return CardMemory(
            character=self.character,
            card_name=self.card_name,
            note=self.note,
            pick_count=self.pick_count + (1 if picked else 0),
            buy_count=self.buy_count + (1 if bought else 0),
            play_count=self.play_count + play_count,
            sly_play_count=self.sly_play_count + sly_play_count,
            draw_count=self.draw_count + draw_count,
            unplayed_draw_count=self.unplayed_draw_count + unplayed_draw_count,
            total_damage=self.total_damage + total_damage,
            total_block=self.total_block + total_block,
            total_energy_gain=self.total_energy_gain + total_energy_gain,
            debuffs_applied=self.debuffs_applied + debuffs_applied,
            powers_applied=self.powers_applied + powers_applied,
            runs_won=self.runs_won + (1 if victory and not incomplete else 0),
            runs_died_act1=self.runs_died_act1 + (1 if not victory and not incomplete and final_act == 1 else 0),
            runs_died_act2=self.runs_died_act2 + (1 if not victory and not incomplete and final_act == 2 else 0),
            runs_died_act3=self.runs_died_act3 + (1 if not victory and not incomplete and final_act == 3 else 0),
            runs_incomplete=self.runs_incomplete + (1 if incomplete else 0),
            sample_count=self.sample_count + 1,
            last_updated=_now(),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_card_memory.py::TestCardMemory -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/models_v2.py tests/test_card_memory.py
git commit -m "refactor: unify CardMemory seed_note/combat_hint/live_summary into single note field"
```

---

### Task 2: Update CardMemoryStore seed loading and query

**Files:**
- Modify: `src/memory/card_memory_store.py:46-118`
- Modify: `tests/test_card_memory.py:104-198`

- [ ] **Step 1: Update store tests**

```python
# tests/test_card_memory.py — class TestCardMemoryStore

def test_put_and_get(self):
    store = CardMemoryStore()
    cm = CardMemory(character="the silent", card_name="Backstab", note="strong")
    store.put(cm)
    assert store.count == 1
    result = store.get("the silent", "Backstab")
    assert result is not None
    assert result.note == "strong"

def test_get_case_insensitive(self):
    store = CardMemoryStore()
    store.put(CardMemory(character="The Silent", card_name="BACKSTAB", note="x"))
    result = store.get("the silent", "backstab")
    assert result is not None

def test_query_cards_only_returns_offered(self):
    store = CardMemoryStore()
    store.put(CardMemory(character="the silent", card_name="backstab", note="good opener"))
    store.put(CardMemory(character="the silent", card_name="pounce", note="combo card"))
    store.put(CardMemory(character="the silent", card_name="footwork", note="defense scaling"))
    results = store.query_cards("the silent", ["Backstab", "Footwork"])
    assert len(results) == 2

def test_query_cards_skips_empty_content(self):
    store = CardMemoryStore()
    store.put(CardMemory(character="the silent", card_name="backstab"))  # no note
    results = store.query_cards("the silent", ["Backstab"])
    assert len(results) == 0

def test_load_seeds_no_overwrite(self):
    store = CardMemoryStore()
    store.put(CardMemory(
        character="the silent", card_name="backstab",
        note="existing note", play_count=10, sample_count=3,
    ))
    seeds = [CardMemory(character="the silent", card_name="backstab", note="new seed")]
    loaded = store.load_seeds(seeds)
    assert loaded == 0
    existing = store.get("the silent", "backstab")
    assert existing.note == "existing note"

def test_load_seeds_fills_empty_note(self):
    store = CardMemoryStore()
    store.put(CardMemory(
        character="the silent", card_name="backstab",
        note="", play_count=10,
    ))
    seeds = [CardMemory(character="the silent", card_name="backstab", note="new seed")]
    loaded = store.load_seeds(seeds)
    assert loaded == 1
    existing = store.get("the silent", "backstab")
    assert existing.note == "new seed"
    assert existing.play_count == 10  # stats preserved

def test_load_seeds_creates_new(self):
    store = CardMemoryStore()
    seeds = [CardMemory(character="the silent", card_name="pounce", note="combo")]
    loaded = store.load_seeds(seeds)
    assert loaded == 1
    assert store.get("the silent", "pounce") is not None

def test_persistence_roundtrip(self):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "card_memories.json"
        store = CardMemoryStore()
        store.put(CardMemory(character="the silent", card_name="backstab", note="good", play_count=5))
        store.put(CardMemory(character="the silent", card_name="pounce", note="combo", total_damage=100))
        store.save(path)
        loaded = CardMemoryStore.load(path)
        assert loaded.count == 2
        bs = loaded.get("the silent", "backstab")
        assert bs.play_count == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_card_memory.py::TestCardMemoryStore -v`
Expected: FAIL — store still references old fields.

- [ ] **Step 3: Update CardMemoryStore**

In `src/memory/card_memory_store.py`, update `load_seeds()` and `query_cards()`:

```python
def query_cards(self, character: str, card_names: list[str]) -> list[CardMemory]:
    """Retrieve card memories for a list of offered card names.

    Only returns memories that have useful content (non-empty note).
    """
    with self._lock:
        results: list[CardMemory] = []
        char_lower = character.lower().strip()
        for name in card_names:
            k = f"{char_lower}::{name.lower().strip()}"
            mem = self._memories.get(k)
            if mem is not None and mem.has_content:
                results.append(mem)
        return results

def load_seeds(self, seeds: list[CardMemory]) -> int:
    """Load seed memories — bootstrap only, never overwrites existing notes.

    - Entry does not exist → create from seed.
    - Entry exists but note is empty → fill note from seed.
    - Entry exists and note is non-empty → skip (persisted data wins).
    """
    loaded = 0
    with self._lock:
        for seed in seeds:
            k = _key(seed.character, seed.card_name)
            existing = self._memories.get(k)
            if existing is None:
                self._memories[k] = seed
                loaded += 1
            elif not existing.note and seed.note:
                # Fill empty note from seed, preserve all stats
                self._memories[k] = CardMemory(
                    character=existing.character,
                    card_name=existing.card_name,
                    note=seed.note,
                    pick_count=existing.pick_count,
                    buy_count=existing.buy_count,
                    play_count=existing.play_count,
                    sly_play_count=existing.sly_play_count,
                    draw_count=existing.draw_count,
                    unplayed_draw_count=existing.unplayed_draw_count,
                    total_damage=existing.total_damage,
                    total_block=existing.total_block,
                    total_energy_gain=existing.total_energy_gain,
                    debuffs_applied=existing.debuffs_applied,
                    powers_applied=existing.powers_applied,
                    runs_won=existing.runs_won,
                    runs_died_act1=existing.runs_died_act1,
                    runs_died_act2=existing.runs_died_act2,
                    runs_died_act3=existing.runs_died_act3,
                    runs_incomplete=existing.runs_incomplete,
                    sample_count=existing.sample_count,
                    last_updated=existing.last_updated,
                )
                loaded += 1
    return loaded
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_card_memory.py::TestCardMemoryStore -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/card_memory_store.py tests/test_card_memory.py
git commit -m "refactor: update CardMemoryStore for unified note field"
```

---

### Task 3: Update seed JSON and remaining test references

**Files:**
- Modify: `src/skills/seeds/silent_card_notes.json`
- Modify: `tests/test_card_memory.py` (remaining test classes)

- [ ] **Step 1: Update seed JSON**

Script to convert `silent_card_notes.json`:

```python
import json
with open("src/skills/seeds/silent_card_notes.json") as f:
    data = json.load(f)
for entry in data:
    entry["note"] = entry.pop("seed_note", "")
    entry.pop("combat_hint", None)
with open("src/skills/seeds/silent_card_notes.json", "w") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 2: Fix remaining test references**

Search all tests for `seed_note`, `combat_hint`, `live_summary` and update:
- `TestSilentSeedNotes`: update to check `note` field
- `TestCardMemoryExtractor.test_update_card_memories_from_run`: already uses `runs_won` (updated earlier)
- `TestRetrieverCardMemory`: update `seed_note=` → `note=` in fixture construction

Run: `grep -rn "seed_note\|combat_hint\|live_summary" tests/test_card_memory.py` to find all remaining references.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/test_card_memory.py -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/skills/seeds/silent_card_notes.json tests/test_card_memory.py
git commit -m "refactor: migrate seed JSON to unified note field, update all tests"
```

---

### Task 4: Update evolution engine — `_handle_update_card_note` and `_render_card_notes`

**Files:**
- Modify: `src/brain/evolution_engine.py:139-142, 1987-2068, 2258-2317, 2459-2469`
- Modify: `src/brain/write_tools.py:233-263`

- [ ] **Step 1: Update write_tools.py tool schema**

```python
UPDATE_CARD_NOTE: dict = {
    "name": "update_card_note",
    "description": (
        "Write an experience-based evaluation for a card based on gameplay evidence "
        "and card mechanics. The note replaces any existing note in all future prompts. "
        "Base insights on rules_text descriptions and observable combat data."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "card_name": {
                "type": "string",
                "description": "Card name in lowercase (e.g. 'haze', 'backstab')",
            },
            "note": {
                "type": "string",
                "maxLength": 400,
                "description": (
                    "Updated card evaluation based on gameplay evidence (≤400 chars). "
                    "Include: mechanic discoveries, combo interactions, scenario-based "
                    "strength, and take/skip guidance grounded in rules_text and combat data."
                ),
            },
            "motivation": {
                "type": "string",
                "description": "What gameplay evidence led to this update (stats, outcomes, patterns)",
            },
        },
        "required": ["card_name", "note", "motivation"],
        "additionalProperties": False,
    },
}
```

- [ ] **Step 2: Update `_handle_update_card_note` in evolution_engine.py**

Change `live_summary` references to `note`. Update validation limit from 200 to 400:

```python
def _handle_update_card_note(self, tool_input: dict) -> str:
    """Handle update_card_note: overwrite note for a card."""
    from src.memory.models_v2 import CardMemory, normalize_character

    card_name = (tool_input.get("card_name") or "").strip().lower()
    note = (tool_input.get("note") or "").strip()
    motivation = (tool_input.get("motivation") or "").strip()

    if not card_name:
        return "REJECTED: card_name is required."
    if not note:
        return "REJECTED: note is required."
    if len(note) > 400:
        return f"REJECTED: note exceeds 400 chars ({len(note)})."
    if not motivation:
        return "REJECTED: motivation is required."

    if self._memory is None:
        return "REJECTED: Memory manager not available."

    card_memory_store = getattr(self._memory, "card_memory_store", None)
    if card_memory_store is None:
        return "REJECTED: Card memory store not available."

    character = normalize_character(
        getattr(self, "_run_character", "") or ""
    )
    if not character:
        return "REJECTED: No character context available."

    existing = card_memory_store.get(character, card_name)
    if existing is None:
        existing = CardMemory(character=character, card_name=card_name)

    updated = CardMemory(
        character=existing.character,
        card_name=existing.card_name,
        note=note,
        pick_count=existing.pick_count,
        buy_count=existing.buy_count,
        play_count=existing.play_count,
        sly_play_count=existing.sly_play_count,
        draw_count=existing.draw_count,
        unplayed_draw_count=existing.unplayed_draw_count,
        total_damage=existing.total_damage,
        total_block=existing.total_block,
        total_energy_gain=existing.total_energy_gain,
        debuffs_applied=existing.debuffs_applied,
        powers_applied=existing.powers_applied,
        runs_won=existing.runs_won,
        runs_died_act1=existing.runs_died_act1,
        runs_died_act2=existing.runs_died_act2,
        runs_died_act3=existing.runs_died_act3,
        runs_incomplete=existing.runs_incomplete,
        sample_count=existing.sample_count,
        last_updated=time.time(),
    )
    card_memory_store.put(updated)

    card_path = Path(config.DATA_DIR) / "memory" / "v2" / "card_memories.json"
    card_memory_store.save(card_path)

    old_note = existing.effective_note()
    old_preview = (old_note[:40] + "...") if len(old_note) > 40 else old_note
    logger.info(
        "Card note updated: %s (%s) — old='%s' new='%s'",
        card_name, character, old_preview, note[:60],
    )
    return (
        f"SUCCESS: Card '{card_name}' ({character}) note updated. "
        f"Motivation: {motivation[:80]}"
    )
```

- [ ] **Step 3: Update `_render_card_notes` to accept `seen_cards`**

Change the function signature and iteration target. Also update the stats display format — remove `[LIVE]` tag (no longer meaningful with unified note), update header:

```python
def _render_card_notes(
    memory_manager: Any,
    character: str,
    seen_cards: tuple[str, ...],
) -> tuple[str, tuple[SectionStat, ...], int, int]:
    lines = ["## Card Notes (seen this run)"]
    stats_lines = [
        "## Card Memory Stats (seen this run)",
        "card | note | plays | sly | draws | unplayed | dmg | outcomes",
    ]
    card_memory_store = getattr(memory_manager, "card_memory_store", None)
    if card_memory_store is None or not seen_cards:
        lines.append("(no card notes)")
        stats_lines.append("(no card memory stats)")
        note_text, note_stat = _section("card_notes", "\n".join(lines))
        stats_text, stats_stat = _section("card_stats", "\n".join(stats_lines))
        return "\n\n".join([note_text, stats_text]), (
            SectionStat("card_notes", note_stat.chars, note_stat.estimated_tokens),
            SectionStat("card_stats", stats_stat.chars, stats_stat.estimated_tokens),
        ), 0, 0

    from src.memory.models_v2 import normalize_character

    char_norm = normalize_character(character)
    seen_keys: set[str] = set()
    note_count = 0
    stat_count = 0
    for card_name in seen_cards:
        base_name = card_name[:-1] if card_name.endswith("+") else card_name
        if base_name.lower() in seen_keys:
            continue
        seen_keys.add(base_name.lower())
        memory = card_memory_store.get(char_norm, base_name)
        if memory is None:
            continue
        if memory.note:
            note_count += 1
            lines.append(f"- {base_name}: {memory.note}")
        stats_lines.append(
            f"- {base_name} | {memory.note[:50] if memory.note else '(none)'} | "
            f"{memory.play_count} | {memory.sly_play_count} | "
            f"{memory.draw_count} | {memory.unplayed_draw_count} | {memory.total_damage} | "
            f"{memory.runs_won}W|A1:{memory.runs_died_act1},A2:{memory.runs_died_act2},A3:{memory.runs_died_act3}"
            + (f",inc:{memory.runs_incomplete}" if memory.runs_incomplete else "")
        )
        stat_count += 1
    if note_count == 0:
        lines.append("(no card notes)")
    if stat_count == 0:
        stats_lines.append("(no card memory stats)")
    note_text, note_stat = _section("card_notes", "\n".join(lines))
    stats_text, stats_stat = _section("card_stats", "\n".join(stats_lines))
    combined_text = "\n\n".join([note_text, stats_text])
    combined_stats = (
        SectionStat("card_notes", note_stat.chars, note_stat.estimated_tokens),
        SectionStat("card_stats", stats_stat.chars, stats_stat.estimated_tokens),
    )
    return combined_text, combined_stats, note_count, stat_count
```

- [ ] **Step 4: Update evolution system prompt**

In the `EVOLUTION_SYSTEM_PROMPT` (around line 139), replace the card note guidance:

```python
"- Update a card note (update_card_note) to write an experience-based evaluation "
"for a card. Prioritize cards without existing notes in the Card Notes section. "
"Base your note on: "
"(1) The card's rules_text from the Card Mechanics Reference, "
"(2) Observable combat outcomes from the Combat Digest, "
"(3) Keyword interactions deducible from card descriptions, "
"(4) Act death correlations from Card Memory Stats. "
"Evidence thresholds: mechanic discoveries can be low-sample if grounded in rules_text; "
"tier ratings and take/skip guidance require >=10 plays AND act death data. "
"Do NOT write notes for generated/status cards (Shiv, Burn, Slimed, Wound). "
"Only write discoveries logically derivable from card descriptions and gameplay evidence."
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_card_memory.py tests/test_evolution_engine.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/brain/evolution_engine.py src/brain/write_tools.py
git commit -m "refactor: update evolution engine for unified note field and seen_cards"
```

---

### Task 5: Build card mechanics section from run logs

**Files:**
- Modify: `src/postrun/context_builder.py`
- Create: `tests/test_card_mechanics_section.py`

- [ ] **Step 1: Write test**

```python
# tests/test_card_mechanics_section.py
import json
import tempfile
from pathlib import Path
from src.postrun.context_builder import build_card_mechanics_section

def test_extracts_cards_from_log():
    """Extract unique card names and rules_text from a run log."""
    log_lines = [
        json.dumps({"event": "state", "state_type": "combat", "combat": {
            "player": {"hand": [
                {"name": "Strike", "rules_text": "Deal 6 damage."},
                {"name": "Defend", "rules_text": "Gain 5 Block."},
                {"name": "Strike", "rules_text": "Deal 6 damage."},  # dupe
            ], "hp": 50, "max_hp": 70, "block": 0, "energy": 3, "max_energy": 3,
               "stars": 0, "gold": 50, "powers": [], "potions": [], "relics": []},
            "enemies": [], "round": 1, "is_play_phase": True,
            "draw_pile_size": 5, "discard_pile_size": 0, "exhaust_pile_size": 0,
        }}),
        json.dumps({"event": "state", "state_type": "card_reward",
            "card_reward_details": {"card_options": [
                {"index": 0, "name": "Haze", "rules_text": "Sly. Apply 4 Poison to ALL enemies."},
            ]},
        }),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for line in log_lines:
            f.write(line + "\n")
        path = Path(f.name)

    section, seen_cards = build_card_mechanics_section(path, "test_run")
    assert "Strike" in section
    assert "Defend" in section
    assert "Haze" in section
    assert "Sly" in section  # keyword glossary triggered
    assert len(seen_cards) == 3  # Strike, Defend, Haze (deduplicated)
    path.unlink()

def test_empty_log():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"event": "run_start"}) + "\n")
        path = Path(f.name)
    section, seen_cards = build_card_mechanics_section(path, "test_run")
    assert len(seen_cards) == 0
    path.unlink()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_card_mechanics_section.py -v`
Expected: FAIL — `build_card_mechanics_section` not yet defined.

- [ ] **Step 3: Implement `build_card_mechanics_section`**

Add to `src/postrun/context_builder.py`:

```python
def build_card_mechanics_section(
    log_path: Path,
    run_id: str,
) -> tuple[str, tuple[str, ...]]:
    """Extract card mechanics from run log.

    Returns (formatted_section, seen_card_names) where seen_card_names
    is the deduplicated tuple of all card names encountered in the run.
    """
    from src.brain.prompts._keyword_fmt import KW_GLOSSARY

    seen: dict[str, str] = {}  # card_name_lower -> rules_text

    if not log_path.exists():
        return "", ()

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("event") != "state":
                continue

            # Combat hand cards
            combat = d.get("combat")
            if combat:
                player = combat.get("player", {})
                for card in player.get("hand", []):
                    _collect_card(seen, card)

            # Card reward options
            crd = d.get("card_reward_details")
            if crd:
                for card in crd.get("card_options", []):
                    _collect_card(seen, card)

            # Card select options
            sd = d.get("selection_details")
            if sd:
                for card in sd.get("cards", []):
                    _collect_card(seen, card)

    if not seen:
        return "", ()

    # Build section
    lines = ["## Card Mechanics Reference (seen this run)"]
    for name in sorted(seen.keys()):
        lines.append(f"- {name}: {seen[name]}")

    # Keyword glossary
    all_text = " ".join(rt.lower() for rt in seen.values())
    matched_kw = [
        desc for kw, desc in KW_GLOSSARY.items()
        if kw in all_text
    ]
    if matched_kw:
        lines.append("")
        lines.append("### Keywords")
        for desc in matched_kw:
            lines.append(f"- {desc}")

    seen_card_names = tuple(seen.keys())
    return "\n".join(lines), seen_card_names


def _collect_card(seen: dict[str, str], card: dict) -> None:
    """Add a card to the seen dict if it has a rules_text."""
    name = card.get("name", "")
    rules_text = card.get("rules_text", "")
    if not name or not rules_text:
        return
    key = name.rstrip("+")
    if key not in seen:
        seen[key] = rules_text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_card_mechanics_section.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/postrun/context_builder.py tests/test_card_mechanics_section.py
git commit -m "feat: build_card_mechanics_section extracts rules_text from run logs"
```

---

### Task 6: Enhance combat digest with per-action deltas

**Files:**
- Modify: `src/postrun/context_builder.py:344-380`

- [ ] **Step 1: Write test**

```python
# tests/test_card_mechanics_section.py — add to existing file

def test_format_combat_round_digest_includes_deltas():
    """Per-action deltas appear in round digest."""
    from src.postrun.context_builder import format_combat_round_digest
    from unittest.mock import MagicMock

    # Build a mock episode with one round, two card plays
    ep = MagicMock()
    ep.won = True
    ep.hp_before = 50
    ep.hp_after = 50
    ep.floor = 5
    ep.combat_type = "monster"
    ep.enemy_key = "Slime"

    delta1 = MagicMock()
    delta1.event_type = "card_play"
    delta1.source = "Neutralize"
    delta1.block = None
    delta1.energy = None
    delta1.powers_changed = []
    delta1.cards_exhausted = []
    enemy_d1 = MagicMock()
    enemy_d1.hp = -3
    enemy_d1.powers_changed = ["Weak"]
    delta1.enemy_deltas = [enemy_d1]

    delta2 = MagicMock()
    delta2.event_type = "card_play"
    delta2.source = "Defend"
    delta2.block = 5
    delta2.energy = None
    delta2.powers_changed = []
    delta2.cards_exhausted = []
    delta2.enemy_deltas = []

    round1 = MagicMock()
    round1.round_num = 1
    round1.enemy_intents = ("Slime: Attack(6)",)
    round1.cards_played = ("Neutralize", "Defend")
    round1.damage_dealt = 3
    round1.damage_taken = 0
    round1.events = (delta1, delta2)

    ep.rounds = (round1,)

    text = format_combat_round_digest(ep)
    assert "Neutralize(3dmg,1Weak)" in text
    assert "Defend(+5blk)" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_card_mechanics_section.py::test_format_combat_round_digest_includes_deltas -v`
Expected: FAIL — current `format_combat_round_digest` doesn't include deltas.

- [ ] **Step 3: Implement enhanced digest**

Modify `format_combat_round_digest()` in `context_builder.py`. Build a lookup from `round.events` to annotate each card in `cards_played`:

```python
def format_combat_round_digest(episode: Any) -> str:
    """Format one combat as a compact round-by-round digest with per-action deltas."""
    result = "WIN" if getattr(episode, "won", False) else "LOSS"
    hp_before = int(getattr(episode, "hp_before", 0) or 0)
    hp_after = int(getattr(episode, "hp_after", 0) or 0)
    loss = max(0, hp_before - hp_after)
    combat_type = getattr(episode, "combat_type", "") or "combat"
    header = (
        f"F{getattr(episode, 'floor', 0)} [{combat_type}] {getattr(episode, 'enemy_key', '')} "
        f"({len(getattr(episode, 'rounds', ()))}R, HP {hp_before}->{hp_after}, "
        f"loss={loss}, {result})"
    )
    round_lines: list[str] = []
    for rnd in getattr(episode, "rounds", ()) or ():
        intents = list(getattr(rnd, "enemy_intents", ()) or ())
        if intents:
            intent_label = "+".join(
                str(intent).replace("Attack", "Atk") for intent in intents
            )
        else:
            intent_label = "?"

        # Build per-card delta annotations from events
        card_deltas: dict[int, str] = {}  # index in cards_played -> annotation
        events = list(getattr(rnd, "events", ()) or ())
        play_idx = 0
        for ev in events:
            if getattr(ev, "event_type", "") != "card_play" or not getattr(ev, "source", ""):
                continue
            annotation = _format_card_delta(ev)
            if annotation:
                card_deltas[play_idx] = annotation
            play_idx += 1

        cards = list(getattr(rnd, "cards_played", ()) or ())
        annotated: list[str] = []
        for i, card in enumerate(cards):
            ann = card_deltas.get(i, "")
            if ann:
                annotated.append(f"{card}({ann})")
            else:
                annotated.append(card)

        # Collapse consecutive duplicates
        collapsed: list[str] = []
        for entry in annotated:
            if collapsed and collapsed[-1].startswith(f"{entry}*"):
                name, raw_count = collapsed[-1].rsplit("*", 1)
                collapsed[-1] = f"{name}*{int(raw_count) + 1}"
            elif collapsed and collapsed[-1] == entry:
                collapsed[-1] = f"{entry}*2"
            else:
                collapsed.append(entry)

        cards_text = "->".join(collapsed) if collapsed else "none"
        round_lines.append(
            f"  R{getattr(rnd, 'round_num', 0)}[{intent_label}]: {cards_text} | "
            f"dealt={getattr(rnd, 'damage_dealt', 0)} taken={getattr(rnd, 'damage_taken', 0)}"
        )
    return header if not round_lines else header + "\n" + "\n".join(round_lines)


def _format_card_delta(ev: Any) -> str:
    """Format a card_play event into a compact annotation string."""
    parts: list[str] = []

    # Damage to enemies
    total_dmg = 0
    enemy_debuffs: list[str] = []
    for ed in getattr(ev, "enemy_deltas", ()) or ():
        hp = getattr(ed, "hp", None)
        if hp is not None and hp < 0:
            total_dmg += abs(hp)
        for p in getattr(ed, "powers_changed", ()) or ():
            enemy_debuffs.append(str(p))
    if total_dmg:
        parts.append(f"{total_dmg}dmg")

    # Block gained
    block = getattr(ev, "block", None)
    if block is not None and block > 0:
        parts.append(f"+{block}blk")

    # Energy gained
    energy = getattr(ev, "energy", None)
    if energy is not None and energy > 0:
        parts.append(f"+{energy}energy")

    # Player powers applied
    for p in getattr(ev, "powers_changed", ()) or ():
        parts.append(f"power:{p}")

    # Enemy debuffs
    from collections import Counter
    debuff_counts = Counter(enemy_debuffs)
    for debuff, count in debuff_counts.items():
        parts.append(f"{count}{debuff}")

    # Exhausted cards
    exhausted = getattr(ev, "cards_exhausted", ()) or ()
    if exhausted:
        parts.append(f"exhaust:{len(exhausted)}")

    return ",".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_card_mechanics_section.py::test_format_combat_round_digest_includes_deltas -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/postrun/context_builder.py tests/test_card_mechanics_section.py
git commit -m "feat: enhance combat digest with per-action card deltas"
```

---

### Task 7: Add relic context extraction

**Files:**
- Modify: `src/postrun/context_builder.py`

- [ ] **Step 1: Write test**

```python
# tests/test_card_mechanics_section.py — add

def test_build_relic_context():
    import json, tempfile
    from pathlib import Path
    from src.postrun.context_builder import build_relic_context

    log_lines = [
        json.dumps({"event": "state", "state_type": "combat", "combat": {
            "player": {"hand": [], "hp": 50, "max_hp": 70, "block": 0,
                       "energy": 3, "max_energy": 3, "stars": 0, "gold": 50,
                       "powers": [], "potions": [],
                       "relics": [
                           {"name": "Runic Pyramid", "description": "No longer discard hand at end of turn."},
                           {"name": "Shuriken", "description": "Play 3 Attacks in a turn: gain 1 Strength."},
                       ]},
            "enemies": [], "round": 1, "is_play_phase": True,
            "draw_pile_size": 5, "discard_pile_size": 0, "exhaust_pile_size": 0,
        }}),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for line in log_lines:
            f.write(line + "\n")
        path = Path(f.name)

    section = build_relic_context(path, "test_run")
    assert "Runic Pyramid" in section
    assert "Shuriken" in section
    path.unlink()
```

- [ ] **Step 2: Implement**

```python
def build_relic_context(log_path: Path, run_id: str) -> str:
    """Extract relic list with descriptions from the first combat state in log."""
    if not log_path.exists():
        return ""

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("event") != "state":
                continue
            combat = d.get("combat")
            if not combat:
                continue
            relics = combat.get("player", {}).get("relics", [])
            if not relics:
                continue
            lines = ["## Run Relics"]
            for r in relics:
                name = r.get("name", "")
                desc = r.get("description", "")
                if name:
                    lines.append(f"- {name}: {desc}" if desc else f"- {name}")
            return "\n".join(lines)
    return ""
```

- [ ] **Step 3: Run test**

Run: `pytest tests/test_card_mechanics_section.py::test_build_relic_context -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/postrun/context_builder.py tests/test_card_mechanics_section.py
git commit -m "feat: extract relic context from run log for evolution"
```

---

### Task 8: Wire new sections into evolution context

**Files:**
- Modify: `src/brain/evolution_engine.py` — `build_evolution_context()` around line 2459

- [ ] **Step 1: Update build_evolution_context to call new builders and pass seen_cards**

In `build_evolution_context()`, after the decision digest is built (around line 2416), add calls to the new builders and pass `seen_card_names` to `_render_card_notes`:

```python
# After decision_digest is built, extract card mechanics and relics from log
from src.postrun.context_builder import build_card_mechanics_section, build_relic_context

card_mechanics_text = ""
seen_card_names: tuple[str, ...] = decision_digest.final_deck_cards  # fallback
if log_path is not None:
    card_mechanics_text, seen_card_names_from_log = build_card_mechanics_section(log_path, run_id)
    if seen_card_names_from_log:
        seen_card_names = seen_card_names_from_log

relic_text = ""
if log_path is not None:
    relic_text = build_relic_context(log_path, run_id)
```

Insert `card_mechanics_text` and `relic_text` into sections list (before card notes).

Update the `_render_card_notes` call site from:
```python
card_text, card_stats, card_note_count, card_stat_count = _render_card_notes(
    memory_manager, character, decision_digest.final_deck_cards,
)
```
to:
```python
card_text, card_stats, card_note_count, card_stat_count = _render_card_notes(
    memory_manager, character, seen_card_names,
)
```

- [ ] **Step 2: Run evolution engine tests**

Run: `pytest tests/test_evolution_engine.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add src/brain/evolution_engine.py
git commit -m "feat: wire card mechanics reference and relic context into evolution"
```

---

### Task 9: Combat injection — deck notes at COMBAT_START

**Files:**
- Modify: `src/brain/conversation.py:568-707`
- Modify: `src/agent/loop.py` — call site for `add_combat_start`

- [ ] **Step 1: Modify `add_combat_start` to accept and inject card notes**

Add a `card_notes: dict[str, str] | None = None` parameter to `add_combat_start()`. After the deck info section, append:

```python
# Card notes from experience
if card_notes:
    parts.append("")
    parts.append("## Card Notes (from experience)")
    for card_name, note_text in card_notes.items():
        parts.append(f"- {card_name}: {note_text}")
```

- [ ] **Step 2: Update loop.py to pass card notes**

At the call site where `add_combat_start` is called, build the card notes dict from `CardMemoryStore`:

```python
# Build card notes for combat start
card_notes = {}
if self._memory and getattr(self._memory, "card_memory_store", None):
    deck_names = [c.name for c in gs.deck] if gs.deck else []
    memories = self._memory.card_memory_store.query_cards(
        self._run_state.character, deck_names,
    )
    card_notes = {m.card_name: m.note for m in memories if m.note}
```

Pass `card_notes=card_notes` to `add_combat_start()`.

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -q --ignore=tests/test_agent_loop_fixes.py --ignore=tests/test_combat_delta.py --ignore=tests/test_seed_character_guides.py --ignore=tests/test_v2_backend.py -x`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/brain/conversation.py src/agent/loop.py
git commit -m "feat: inject deck card notes at COMBAT_START"
```

---

### Task 10: Combat injection — temporary card notes in subsequent rounds

**Files:**
- Modify: `src/brain/conversation.py:718-882` — `add_round_state()`
- Modify: `src/agent/loop.py` — remove `_get_combat_hints()`, update call site

- [ ] **Step 1: Remove `combat_hints` parameter from `add_round_state`**

Replace the `combat_hints` parameter with `card_memory_store` and `deck_card_names`:

```python
def add_round_state(
    self,
    gs: GameState,
    *,
    extra_context: str = "",
    replan_context: str = "",
    enemy_episodes: list | None = None,
    card_memory_store: Any | None = None,
    deck_card_names: set[str] | None = None,
) -> None:
```

Replace the old combat_hints injection (lines ~874-882) with:

```python
# Per-card notes for temporary cards only (not in deck)
if card_memory_store and deck_card_names is not None:
    from src.memory.models_v2 import normalize_character
    char = normalize_character(self._character or "")
    injected = set()
    for c in hand:
        base_name = (c.name or "").rstrip("+")
        if base_name in deck_card_names:
            continue  # Already injected at COMBAT_START
        if base_name.lower() in injected:
            continue
        mem = card_memory_store.get(char, base_name)
        if mem and mem.note:
            injected.add(base_name.lower())
            lines.append(f"!! {c.name}: {mem.note}")
```

- [ ] **Step 2: Remove `_get_combat_hints` from loop.py**

Delete the `_get_combat_hints` method (~lines 372-392) and update the call site (~line 5553-5559) to pass the new parameters:

```python
# Build deck card name set for temporary card detection
deck_card_names = {c.name.rstrip("+") for c in gs.deck} if gs.deck else set()

self._v2_combat_conversation.add_round_state(
    gs,
    extra_context=extra_context,
    replan_context=replan_ctx,
    enemy_episodes=self._get_enemy_episodes(gs),
    card_memory_store=getattr(self._memory, "card_memory_store", None) if self._memory else None,
    deck_card_names=deck_card_names,
)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/ -q --ignore=tests/test_agent_loop_fixes.py --ignore=tests/test_combat_delta.py --ignore=tests/test_seed_character_guides.py --ignore=tests/test_v2_backend.py -x`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/brain/conversation.py src/agent/loop.py
git commit -m "feat: inject temporary card notes in combat rounds, remove combat_hints"
```

---

### Task 11: Fix remaining references and full test sweep

**Files:**
- Grep across entire `src/` and `tests/` for any remaining `seed_note`, `combat_hint`, `live_summary` references.

- [ ] **Step 1: Search for remaining references**

```bash
grep -rn "seed_note\|combat_hint\|live_summary" src/ tests/ --include="*.py" --include="*.json"
```

Fix each occurrence:
- `card_memory_extractor.py`: if `extract_per_card_stats` or `update_card_memories_from_run` log messages reference old fields, update them.
- `evolution_engine.py`: any remaining `live_summary` or `seed_note` in the tool dispatch map.
- Any test fixtures still using old field names.

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -q --ignore=tests/test_agent_loop_fixes.py --ignore=tests/test_combat_delta.py --ignore=tests/test_seed_character_guides.py --ignore=tests/test_v2_backend.py
```

Expected: All pass (excluding pre-existing failures in ignored files).

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: clean up all remaining seed_note/combat_hint/live_summary references"
```
