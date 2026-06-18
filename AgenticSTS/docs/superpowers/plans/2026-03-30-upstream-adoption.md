# Upstream Adoption Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt game data, API improvements, and soft-lock prevention from CharTyr/STS2-Agent v0.5.3 and Gennadiyev/STS2MCP v0.3.2.

**Architecture:** Download 16 structured JSON files from upstream into `data/knowledge/upstream/`. Create new lookup modules following the existing `@dataclass(frozen=True, slots=True)` + singleton lookup class pattern. Enrich existing card/monster lookups by merging JSON fields after markdown load. Upgrade upstream Pydantic models for v0.5.3 `dynamic_values[]`. Add overlay catch-all for soft-lock prevention.

**Tech Stack:** Python 3.11, Pydantic v2, frozen dataclasses, httpx async client

**Spec:** `docs/superpowers/specs/2026-03-30-upstream-adoption-design.md`

---

## Phase 1: Game Data JSON Integration

### Task 1: Download Upstream JSON Files

**Files:**
- Create: `data/knowledge/upstream/` (directory + 16 JSON files)
- Create: `scripts/sync_upstream_data.py`

- [ ] **Step 1: Create download script**

```python
# scripts/sync_upstream_data.py
"""Download game data JSON files from CharTyr/STS2-Agent repository."""
import json
import base64
import urllib.request
from pathlib import Path

REPO = "CharTyr/STS2-Agent"
BRANCH = "main"
DATA_PATH = "mcp_server/data/eng"
OUTPUT_DIR = Path("data/knowledge/upstream")

FILES = [
    "cards.json", "relics.json", "monsters.json", "potions.json",
    "events.json", "encounters.json", "powers.json", "enchantments.json",
    "acts.json", "keywords.json", "characters.json", "epochs.json",
    "intents.json", "afflictions.json", "modifiers.json", "ascensions.json",
]

def download_file(filename: str) -> None:
    url = f"https://api.github.com/repos/{REPO}/contents/{DATA_PATH}/{filename}?ref={BRANCH}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.v3+json"})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
        content = base64.b64decode(data["content"])
        out_path = OUTPUT_DIR / filename
        out_path.write_bytes(content)
        print(f"  {filename}: {len(content):,} bytes")

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {len(FILES)} files from {REPO}...")
    for f in FILES:
        download_file(f)
    print("Done.")

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run download script**

Run: `cd AgenticSTS && python scripts/sync_upstream_data.py`
Expected: 16 JSON files downloaded to `data/knowledge/upstream/`

- [ ] **Step 3: Verify files exist and are valid JSON**

Run: `python -c "import json; from pathlib import Path; [json.loads((Path('data/knowledge/upstream') / f).read_text()) for f in ['cards.json','relics.json','monsters.json','events.json','encounters.json','acts.json','keywords.json','enchantments.json']]; print('All valid')"`
Expected: "All valid"

- [ ] **Step 4: Commit**

```bash
git add data/knowledge/upstream/ scripts/sync_upstream_data.py
git commit -m "chore: download 16 upstream game data JSON files from CharTyr/STS2-Agent v0.5.3"
```

---

### Task 2: Relic Lookup Module

**Files:**
- Create: `src/knowledge/relic_lookup.py`

- [ ] **Step 1: Create relic lookup module**

Follow the exact pattern from `card_lookup.py` / `monster_lookup.py`:

```python
# src/knowledge/relic_lookup.py
"""Full relic knowledge database from upstream JSON (289 relics)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RelicKnowledge:
    name: str
    id: str = ""
    description: str = ""
    rarity: str = ""
    pool: str = ""
    flavor: str = ""


class RelicLookup:
    """O(1) relic lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._lookup: dict[str, RelicKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        json_path = data_dir / "upstream" / "relics.json"
        if not json_path.exists():
            logger.warning("Relic JSON not found: %s", json_path)
            return
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            name = entry.get("name", "")
            if not name:
                continue
            rk = RelicKnowledge(
                name=name,
                id=entry.get("id", ""),
                description=entry.get("description", ""),
                rarity=entry.get("rarity", ""),
                pool=entry.get("pool", ""),
                flavor=entry.get("flavor", ""),
            )
            self._lookup[name.lower()] = rk
        logger.info("Loaded %d relics from upstream JSON", len(self._lookup))

    def get(self, relic_name: str) -> RelicKnowledge | None:
        return self._lookup.get(relic_name.lower())

    @property
    def count(self) -> int:
        return len(self._lookup)
```

- [ ] **Step 2: Verify module loads**

Run: `cd AgenticSTS && python -c "from pathlib import Path; from src.knowledge.relic_lookup import RelicLookup; rl = RelicLookup(Path('data/knowledge')); print(f'Loaded {rl.count} relics'); r = rl.get('Burning Blood'); print(f'Burning Blood: {r.description[:80] if r else \"NOT FOUND\"}')" `
Expected: ~289 relics loaded, Burning Blood found with description

- [ ] **Step 3: Commit**

```bash
git add src/knowledge/relic_lookup.py
git commit -m "feat: add relic lookup module (289 relics from upstream JSON)"
```

---

### Task 3: Refactor Relic Formatting

**Files:**
- Modify: `src/brain/prompts/_relic_fmt.py`

- [ ] **Step 1: Add relic_lookup fallback to format_relic_hints**

The existing `RELIC_EFFECTS` dict (~40 entries with curated strategic hints) stays. Add a fallback path that uses `RelicLookup` descriptions for non-curated relics:

In `_relic_fmt.py`, after `_RELIC_LOOKUP` is built (line ~199):

```python
# Add at module top:
from src.knowledge.knowledge import GameKnowledge

# Context keywords for non-curated relic filtering
_CONTEXT_KEYWORDS: dict[str, list[str]] = {
    "combat": ["damage", "block", "attack", "enemy", "hit", "kill", "strength", "dexterity", "energy", "card", "play", "turn"],
    "rest": ["rest", "heal", "hp", "smith", "upgrade", "max hp"],
    "map": ["map", "path", "route", "floor", "room", "elite", "boss", "event"],
    "shop": ["gold", "buy", "shop", "price", "cost", "discount", "remove"],
    "reward": ["card", "reward", "relic", "upgrade", "add"],
    "event": ["event", "option", "choice", "gold", "hp"],
}
```

Then modify `format_relic_hints()` to add upstream fallback:

After the curated lookup loop, add:
```python
    # Fallback: upstream descriptions for non-curated relics
    if len(hints) < 6:
        upstream = GameKnowledge.get_instance().relics
        if upstream and upstream.count > 0:
            ctx_kws = _CONTEXT_KEYWORDS.get(context, [])
            for relic_str in relics:
                if len(hints) >= 6:
                    break
                rname = relic_str.split(" (")[0].strip()
                if rname.lower() in _RELIC_LOOKUP:
                    continue  # already handled by curated hints
                rk = upstream.get(rname)
                if rk and rk.description:
                    desc_lower = rk.description.lower()
                    if not context or any(kw in desc_lower for kw in ctx_kws):
                        hints.append(f"- **{rk.name}**: {rk.description}")
```

- [ ] **Step 2: Test relic hint expansion**

Run: `cd AgenticSTS && python -c "
from src.brain.prompts._relic_fmt import format_relic_hints
# Test with a mix of curated and non-curated relics
relics = ['Burning Blood (desc)', 'Amethyst Aubergine (desc)', 'Happy Flower (desc)', 'Unknown Relic 123 (desc)']
result = format_relic_hints(relics, 'rest')
print(result)
print(f'Hint count: {result.count(chr(10))}')
"`
Expected: Curated relics show strategic hints, upstream relics show descriptions

- [ ] **Step 3: Commit**

```bash
git add src/brain/prompts/_relic_fmt.py
git commit -m "feat: expand relic hints with upstream descriptions (289 relics, context-filtered)"
```

---

### Task 4: Encounter Lookup Module

**Files:**
- Create: `src/knowledge/encounter_lookup.py`

- [ ] **Step 1: Create encounter lookup module**

```python
# src/knowledge/encounter_lookup.py
"""Fight composition database from upstream JSON (87 encounters)."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EncounterKnowledge:
    name: str
    id: str = ""
    room_type: str = ""  # "Monster" / "Elite" / "Boss"
    act: str = ""
    monsters: tuple[str, ...] = ()
    is_weak: bool = False
    tags: tuple[str, ...] = ()


class EncounterLookup:
    """Encounter lookup by monster set or encounter ID."""

    def __init__(self, data_dir: Path) -> None:
        self._by_id: dict[str, EncounterKnowledge] = {}
        self._by_monster_set: dict[frozenset[str], EncounterKnowledge] = {}
        self._by_name_set: dict[frozenset[str], EncounterKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        json_path = data_dir / "upstream" / "encounters.json"
        if not json_path.exists():
            logger.warning("Encounters JSON not found: %s", json_path)
            return
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            monsters_raw = entry.get("monsters", [])
            monster_ids = tuple(m.get("id", "") for m in monsters_raw)
            monster_names = tuple(m.get("name", "") for m in monsters_raw)
            ek = EncounterKnowledge(
                name=entry.get("name", ""),
                id=entry.get("id", ""),
                room_type=entry.get("room_type", ""),
                act=entry.get("act", ""),
                monsters=monster_names,
                is_weak=entry.get("is_weak", False),
                tags=tuple(entry.get("tags", [])),
            )
            self._by_id[ek.id] = ek
            if monster_ids:
                self._by_monster_set[frozenset(monster_ids)] = ek
            if monster_names:
                self._by_name_set[frozenset(n.lower() for n in monster_names)] = ek
        logger.info("Loaded %d encounters from upstream JSON", len(self._by_id))

    def get_by_id(self, encounter_id: str) -> EncounterKnowledge | None:
        return self._by_id.get(encounter_id)

    def get_by_enemy_ids(self, enemy_ids: set[str]) -> EncounterKnowledge | None:
        """Primary lookup: match by enemy_id set from combat state."""
        return self._by_monster_set.get(frozenset(enemy_ids))

    def get_by_enemy_names(self, names: set[str]) -> EncounterKnowledge | None:
        """Fallback lookup: match by display name set."""
        return self._by_name_set.get(frozenset(n.lower() for n in names))

    @property
    def count(self) -> int:
        return len(self._by_id)
```

- [ ] **Step 2: Verify encounter module loads**

Run: `cd AgenticSTS && python -c "from pathlib import Path; from src.knowledge.encounter_lookup import EncounterLookup; el = EncounterLookup(Path('data/knowledge')); print(f'Loaded {el.count} encounters'); e = el.get_by_enemy_names({'Jaw Worm'}); print(f'Jaw Worm encounter: {e}' if e else 'Not found (may need different name)')"`
Expected: ~87 encounters loaded

- [ ] **Step 3: Commit**

```bash
git add src/knowledge/encounter_lookup.py
git commit -m "feat: add encounter lookup module (87 fight compositions from upstream)"
```

---

### Task 5: Event Knowledge Upgrade

**Files:**
- Modify: `src/knowledge/event_lookup.py`

- [ ] **Step 1: Extend EventKnowledge dataclass and EventLookup**

Add upstream JSON enrichment to the existing event module. The existing markdown-based lookup stays; upstream JSON supplements it with structured options.

```python
# Add to EventKnowledge dataclass:
@dataclass(frozen=True, slots=True)
class EventOption:
    id: str = ""
    title: str = ""
    description: str = ""

@dataclass(frozen=True, slots=True)
class EventKnowledge:
    name: str
    base_type: str = ""
    # New fields from upstream JSON:
    event_id: str = ""
    act: str = ""
    options: tuple[EventOption, ...] = ()
```

Add `self._by_event_id: dict[str, EventKnowledge] = {}` to `EventLookup.__init__()`.

Then add to `EventLookup._load()` after markdown loading:
```python
    # Enrich with upstream JSON
    json_path = data_dir / "upstream" / "events.json"
    if json_path.exists():
        import json
        with open(json_path, encoding="utf-8") as f:
            upstream = json.load(f)
        for entry in upstream:
            eid = entry.get("id", "")
            ename = entry.get("name", "")
            opts = tuple(
                EventOption(
                    id=o.get("id", ""),
                    title=o.get("title", ""),
                    description=o.get("description", ""),
                )
                for o in entry.get("options", [])
            )
            key = ename.lower()
            existing = self._events.get(key)
            self._events[key] = EventKnowledge(
                name=existing.name if existing else ename,
                base_type=existing.base_type if existing else "",
                event_id=eid,
                act=entry.get("act", ""),
                options=opts,
            )
            # Also index by event_id for direct lookup
            if eid:
                self._by_event_id[eid.lower()] = self._events[key]
        logger.info("Enriched events with %d upstream entries", len(upstream))
```

Add new lookup method:
```python
    def get_by_event_id(self, event_id: str) -> EventKnowledge | None:
        return self._by_event_id.get(event_id.lower())
```

- [ ] **Step 2: Verify enriched events**

Run: `cd AgenticSTS && python -c "from pathlib import Path; from src.knowledge.event_lookup import EventLookup; el = EventLookup(Path('data/knowledge')); print(f'Loaded {el.count} events'); e = el.get_by_event_id('CRYSTAL_SPHERE'); print(f'Crystal Sphere: {len(e.options)} options' if e else 'Not found by ID')"`
Expected: events loaded with options from upstream

- [ ] **Step 3: Commit**

```bash
git add src/knowledge/event_lookup.py
git commit -m "feat: enrich event knowledge with structured options from upstream JSON"
```

---

### Task 6: Card Knowledge Enrichment

**Files:**
- Modify: `src/knowledge/card_lookup.py`

- [ ] **Step 1: Extend CardKnowledge with new fields**

Add to the `CardKnowledge` dataclass:
```python
@dataclass(frozen=True, slots=True)
class CardKnowledge:
    name: str
    cost: str = ""
    type: str = ""
    rarity: str = ""
    target: str = ""
    on_play: str = ""
    on_upgrade: str = ""
    vars: str = ""
    # New fields from upstream JSON:
    powers_applied: tuple[tuple[str, int], ...] = ()  # (power_name, amount) pairs
    spawns_cards: tuple[str, ...] = ()
    upgrade_deltas: tuple[tuple[str, str], ...] = ()  # (var_name, delta_str) pairs
    base_hit_count: int | None = None
```

- [ ] **Step 2: Add upstream JSON merge in _load()**

After the existing markdown merge loop, add:
```python
        # Enrich with upstream JSON
        json_path = data_dir / "upstream" / "cards.json"
        if json_path.exists():
            import json as json_mod
            with open(json_path, encoding="utf-8") as f:
                upstream = json_mod.load(f)
            enriched = 0
            for entry in upstream:
                uname = entry.get("name", "")
                key = uname.lower().rstrip("+")
                existing = self._cards.get(key)
                if existing is None:
                    continue
                pa = tuple(
                    (p.get("power", ""), p.get("amount", 0))
                    for p in (entry.get("powers_applied") or [])
                )
                sc = tuple(entry.get("spawns_cards") or [])
                ud = tuple(
                    (k, str(v))
                    for k, v in (entry.get("upgrade") or {}).items()
                )
                hc = entry.get("hit_count")
                self._cards[key] = CardKnowledge(
                    name=existing.name,
                    cost=existing.cost,
                    type=existing.type,
                    rarity=existing.rarity,
                    target=existing.target,
                    on_play=existing.on_play,
                    on_upgrade=existing.on_upgrade,
                    vars=existing.vars,
                    powers_applied=pa,
                    spawns_cards=sc,
                    upgrade_deltas=ud,
                    base_hit_count=hc,
                )
                enriched += 1
            logger.info("Enriched %d cards with upstream JSON data", enriched)
```

- [ ] **Step 3: Add enrichment summary method**

```python
    def get_enrichment_summary(self, card_name: str) -> str | None:
        """Return structured effect info for card reward/shop prompts."""
        card = self.get(card_name)
        if card is None:
            return None
        parts = []
        if card.powers_applied:
            effects = ", ".join(f"{p[1]} {p[0]}" for p in card.powers_applied)
            parts.append(f"Applies: {effects}")
        if card.spawns_cards:
            parts.append(f"Creates: {', '.join(card.spawns_cards)}")
        if card.upgrade_deltas:
            deltas = ", ".join(f"{d[0]}: {d[1]}" for d in card.upgrade_deltas)
            parts.append(f"Upgrade: {deltas}")
        return " | ".join(parts) if parts else None
```

- [ ] **Step 4: Verify enrichment**

Run: `cd AgenticSTS && python -c "from pathlib import Path; from src.knowledge.card_lookup import CardLookup; cl = CardLookup(Path('data/knowledge')); c = cl.get('Bash'); print(f'Bash: powers={c.powers_applied}, upgrade={c.upgrade_deltas}' if c else 'NOT FOUND'); s = cl.get_enrichment_summary('Bash'); print(f'Summary: {s}')"`
Expected: Card found with powers_applied and upgrade_deltas populated

- [ ] **Step 5: Commit**

```bash
git add src/knowledge/card_lookup.py
git commit -m "feat: enrich card knowledge with powers_applied, spawns_cards, upgrade deltas"
```

---

### Task 7: Monster Knowledge Enrichment

**Files:**
- Modify: `src/knowledge/monster_lookup.py`

- [ ] **Step 1: Extend MonsterKnowledge with damage values**

```python
@dataclass(frozen=True, slots=True)
class MonsterKnowledge:
    name: str
    min_hp: int | None = None
    max_hp: int | None = None
    moves: str = ""
    passive: str = ""
    # New fields from upstream JSON:
    monster_type: str = ""  # "Normal" / "Elite" / "Boss"
    damage_values: tuple[tuple[str, int, int], ...] = ()  # (move, normal_dmg, ascension_dmg)
    block_values: tuple[tuple[str, int], ...] = ()  # (move, block)
```

- [ ] **Step 2: Add upstream JSON merge in _load()**

After the existing markdown merge loop:
```python
        # Enrich with upstream JSON
        json_path = data_dir / "upstream" / "monsters.json"
        if json_path.exists():
            import json as json_mod
            with open(json_path, encoding="utf-8") as f:
                upstream = json_mod.load(f)
            enriched = 0
            for entry in upstream:
                uname = entry.get("name", "")
                key = uname.lower()
                existing = self._monsters.get(key)
                if existing is None:
                    continue
                dv_raw = entry.get("damage_values") or {}
                dv = tuple(
                    (move, vals.get("normal", 0), vals.get("ascension", 0))
                    for move, vals in dv_raw.items()
                    if isinstance(vals, dict)
                )
                bv_raw = entry.get("block_values") or {}
                bv = tuple(
                    (move, val) for move, val in bv_raw.items()
                    if isinstance(val, int)
                )
                self._monsters[key] = MonsterKnowledge(
                    name=existing.name,
                    min_hp=existing.min_hp,
                    max_hp=existing.max_hp,
                    moves=existing.moves,
                    passive=existing.passive,
                    monster_type=entry.get("type", ""),
                    damage_values=dv,
                    block_values=bv,
                )
                enriched += 1
            logger.info("Enriched %d monsters with upstream damage values", enriched)
```

- [ ] **Step 3: Extend get_combat_summary to include damage values (preserve existing logic)**

Add new fields to the **existing** `get_combat_summary()` method. Do NOT replace the method — insert the new lines after the existing HP formatting and before the Moves line. The existing HP formatting handles `lo == hi` (single value) and `lo is None` fallback — preserve it.

Insert after the HP line and before the Moves line:
```python
        # New: type classification from upstream
        if m.monster_type:
            parts.append(f"[{m.monster_type}]")
        # New: per-move damage values from upstream
        if m.damage_values:
            dmg_parts = [f"{mv}={n}" for mv, n, _ in m.damage_values]
            parts.append(f"Damage=[{', '.join(dmg_parts)}]")
        if m.block_values:
            blk_parts = [f"{mv}={b}" for mv, b in m.block_values]
            parts.append(f"Block=[{', '.join(blk_parts)}]")
```

Keep the existing guard `if not monster.moves and not monster.passive: return None` intact.

- [ ] **Step 4: Verify enrichment**

Run: `cd AgenticSTS && python -c "from pathlib import Path; from src.knowledge.monster_lookup import MonsterLookup; ml = MonsterLookup(Path('data/knowledge')); m = ml.get('Jaw Worm'); print(f'Jaw Worm: type={m.monster_type}, damage={m.damage_values}' if m else 'NOT FOUND'); s = ml.get_combat_summary('Jaw Worm'); print(f'Summary: {s}')"`
Expected: Monster found with damage_values populated

- [ ] **Step 5: Commit**

```bash
git add src/knowledge/monster_lookup.py
git commit -m "feat: enrich monster knowledge with per-move damage values from upstream"
```

---

### Task 8: New Reference Modules (Acts, Enchantments, Keywords)

**Files:**
- Create: `src/knowledge/act_lookup.py`
- Create: `src/knowledge/enchantment_lookup.py`
- Create: `src/knowledge/keyword_lookup.py`

- [ ] **Step 1: Create act lookup**

```python
# src/knowledge/act_lookup.py
"""Act definitions from upstream JSON — bosses, encounters, events per act."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ActKnowledge:
    id: str = ""
    name: str = ""
    bosses: tuple[str, ...] = ()
    encounters: tuple[str, ...] = ()
    events: tuple[str, ...] = ()


class ActLookup:
    def __init__(self, data_dir: Path) -> None:
        self._by_id: dict[str, ActKnowledge] = {}
        self._by_name: dict[str, ActKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        json_path = data_dir / "upstream" / "acts.json"
        if not json_path.exists():
            logger.warning("Acts JSON not found: %s", json_path)
            return
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            ak = ActKnowledge(
                id=entry.get("id", ""),
                name=entry.get("name", ""),
                bosses=tuple(entry.get("bosses", [])),
                encounters=tuple(entry.get("encounters", [])),
                events=tuple(entry.get("events", [])),
            )
            self._by_id[ak.id] = ak
            self._by_name[ak.name.lower()] = ak
        logger.info("Loaded %d acts from upstream JSON", len(self._by_id))

    def get(self, act_name_or_id: str) -> ActKnowledge | None:
        return self._by_id.get(act_name_or_id) or self._by_name.get(act_name_or_id.lower())

    @property
    def count(self) -> int:
        return len(self._by_id)
```

- [ ] **Step 2: Create enchantment lookup**

```python
# src/knowledge/enchantment_lookup.py
"""Card enchantment types from upstream JSON."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EnchantmentKnowledge:
    id: str = ""
    name: str = ""
    description: str = ""
    card_type: str = ""
    is_stackable: bool = False


class EnchantmentLookup:
    def __init__(self, data_dir: Path) -> None:
        self._lookup: dict[str, EnchantmentKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        json_path = data_dir / "upstream" / "enchantments.json"
        if not json_path.exists():
            logger.warning("Enchantments JSON not found: %s", json_path)
            return
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            ek = EnchantmentKnowledge(
                id=entry.get("id", ""),
                name=entry.get("name", ""),
                description=entry.get("description", ""),
                card_type=entry.get("card_type", ""),
                is_stackable=entry.get("is_stackable", False),
            )
            self._lookup[ek.name.lower()] = ek
        logger.info("Loaded %d enchantments from upstream JSON", len(self._lookup))

    def get(self, name: str) -> EnchantmentKnowledge | None:
        return self._lookup.get(name.lower())

    @property
    def count(self) -> int:
        return len(self._lookup)
```

- [ ] **Step 3: Create keyword lookup**

```python
# src/knowledge/keyword_lookup.py
"""Card keyword definitions from upstream JSON."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KeywordKnowledge:
    id: str = ""
    name: str = ""
    description: str = ""


class KeywordLookup:
    def __init__(self, data_dir: Path) -> None:
        self._lookup: dict[str, KeywordKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        json_path = data_dir / "upstream" / "keywords.json"
        if not json_path.exists():
            logger.warning("Keywords JSON not found: %s", json_path)
            return
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        for entry in data:
            kk = KeywordKnowledge(
                id=entry.get("id", ""),
                name=entry.get("name", ""),
                description=entry.get("description", ""),
            )
            self._lookup[kk.name.lower()] = kk
        logger.info("Loaded %d keywords from upstream JSON", len(self._lookup))

    def get(self, name: str) -> KeywordKnowledge | None:
        return self._lookup.get(name.lower())

    def format_glossary(self, keyword_names: set[str]) -> str:
        """Format keyword definitions for prompt injection."""
        defs = []
        for name in sorted(keyword_names):
            kk = self.get(name)
            if kk and kk.description:
                defs.append(f"- **{kk.name}**: {kk.description}")
        return "\n".join(defs) if defs else ""

    @property
    def count(self) -> int:
        return len(self._lookup)
```

- [ ] **Step 4: Verify all three modules**

Run: `cd AgenticSTS && python -c "
from pathlib import Path
from src.knowledge.act_lookup import ActLookup
from src.knowledge.enchantment_lookup import EnchantmentLookup
from src.knowledge.keyword_lookup import KeywordLookup
d = Path('data/knowledge')
print(f'Acts: {ActLookup(d).count}')
print(f'Enchantments: {EnchantmentLookup(d).count}')
print(f'Keywords: {KeywordLookup(d).count}')
"`
Expected: Acts ~4, Enchantments ~22, Keywords ~8

- [ ] **Step 5: Commit**

```bash
git add src/knowledge/act_lookup.py src/knowledge/enchantment_lookup.py src/knowledge/keyword_lookup.py
git commit -m "feat: add act, enchantment, and keyword lookup modules from upstream"
```

---

### Task 9: Knowledge Facade Update

**Files:**
- Modify: `src/knowledge/knowledge.py`

- [ ] **Step 1: Add new lookup instances to GameKnowledge**

Import new modules and add to `__init__`:
```python
from src.knowledge.relic_lookup import RelicLookup
from src.knowledge.encounter_lookup import EncounterLookup
from src.knowledge.act_lookup import ActLookup
from src.knowledge.enchantment_lookup import EnchantmentLookup
from src.knowledge.keyword_lookup import KeywordLookup

class GameKnowledge:
    def __init__(self, data_dir: Path | None = None) -> None:
        if data_dir is None:
            data_dir = _DEFAULT_DATA_DIR
        self.cards = CardLookup(data_dir)
        self.monsters = MonsterLookup(data_dir)
        self.potions = PotionLookup(data_dir)
        self.events = EventLookup(data_dir)
        # New lookups from upstream JSON:
        self.relics = RelicLookup(data_dir)
        self.encounters = EncounterLookup(data_dir)
        self.acts = ActLookup(data_dir)
        self.enchantments = EnchantmentLookup(data_dir)
        self.keywords = KeywordLookup(data_dir)
```

Update the log line to include new counts.

- [ ] **Step 2: Verify facade loads all modules**

Run: `cd AgenticSTS && python -c "from src.knowledge.knowledge import GameKnowledge; GameKnowledge.reset(); kb = GameKnowledge.get_instance(); print(f'Cards: {kb.cards.count}, Monsters: {kb.monsters.count}, Relics: {kb.relics.count}, Encounters: {kb.encounters.count}, Acts: {kb.acts.count}, Enchantments: {kb.enchantments.count}, Keywords: {kb.keywords.count}')"`
Expected: All counts printed, no errors

- [ ] **Step 3: Commit**

```bash
git add src/knowledge/knowledge.py
git commit -m "feat: add relic, encounter, act, enchantment, keyword lookups to GameKnowledge facade"
```

---

### Task 10: Prompt Injection Wiring

**Files:**
- Modify: `src/knowledge/injector.py` — add encounter and keyword injection
- Modify: `src/brain/prompts/event.py` — inject event option knowledge
- Modify: `src/brain/conversation.py` — inject encounter data at combat start

- [ ] **Step 1: Add encounter injection to injector.py**

Add new function:
```python
_ENCOUNTER_BUDGET_CHARS = 200  # ~50 tokens

def inject_encounter_knowledge(enemy_ids: set[str], enemy_names: set[str], kb: GameKnowledge) -> str:
    """Inject encounter composition at combat start."""
    enc = kb.encounters.get_by_enemy_ids(enemy_ids)
    if enc is None:
        enc = kb.encounters.get_by_enemy_names(enemy_names)
    if enc is None:
        return ""
    parts = [f"## Encounter: {enc.name}"]
    parts.append(f"Type: {enc.room_type} | Act: {enc.act}")
    if enc.is_weak:
        parts.append("(Weak encounter)")
    return "\n".join(parts)
```

- [ ] **Step 2: Add keyword glossary injection to injector.py**

```python
def inject_keyword_glossary(keyword_names: set[str], kb: GameKnowledge) -> str:
    """Inject keyword definitions for hand cards."""
    glossary = kb.keywords.format_glossary(keyword_names)
    if not glossary:
        return ""
    return f"## Keyword Glossary\n{glossary}"
```

- [ ] **Step 3: Add event option injection to injector.py**

Update `inject_event_knowledge()`:
```python
def inject_event_knowledge(event_id: str, kb: GameKnowledge) -> str:
    """Inject event context including structured options when available."""
    parts = []
    event = kb.events.get_by_event_id(event_id)
    if event is None:
        event = kb.events.get(event_id)
    if event is None:
        return ""
    if event.base_type == "AncientEventModel":
        parts.append("This is a rare Ancient event with powerful choices.")
    if event.options:
        parts.append("## Known Outcomes")
        for opt in event.options:
            title = opt.title or opt.id
            desc = opt.description
            if desc:
                parts.append(f"- **{title}**: {desc[:150]}")
            else:
                parts.append(f"- **{title}**")
    return "\n".join(parts)
```

- [ ] **Step 4: Wire encounter data into conversation.py combat start**

In `add_combat_start()`, after the enemy section, inject encounter knowledge:
```python
# After enemy info block, before strategic thread:
from src.knowledge.injector import inject_encounter_knowledge
enemy_ids = {e.enemy_id for e in gs.enemies if e.enemy_id}
enemy_names = {e.name for e in gs.enemies if e.name}
enc_section = inject_encounter_knowledge(enemy_ids, enemy_names, kb)
if enc_section:
    parts.append(enc_section)
```

Note: `kb` (GameKnowledge instance) needs to be passed into `add_combat_start()` or accessed via singleton.

- [ ] **Step 5: Wire keyword glossary into conversation.py round state**

In `add_round_state()`, after the Key Effects section, add keyword definitions:
```python
from src.knowledge.injector import inject_keyword_glossary
# Collect keywords from hand cards
# Prefer agent_view keywords field if available; fall back to rules_text scan
hand_keywords: set[str] = set()
if hasattr(gs, 'agent_view') and gs.agent_view and hasattr(gs.agent_view, 'combat'):
    for card in (gs.agent_view.combat.hand if gs.agent_view.combat else []):
        hand_keywords.update(getattr(card, 'keywords', []) or [])
if not hand_keywords:
    # Fallback: scan rules_text for known keywords from keyword_lookup
    all_kw_names = {kk.name for kk in kb.keywords._lookup.values()} if kb.keywords.count > 0 else set()
    for card in gs.hand:
        for kw in all_kw_names:
            if kw.lower() in (card.rules_text or "").lower():
                hand_keywords.add(kw)
kw_section = inject_keyword_glossary(hand_keywords, kb)
if kw_section:
    parts.append(kw_section)
```

- [ ] **Step 6: Wire event option injection into event prompt or loop.py**

In `_query_knowledge()` in `loop.py`, the event path already calls `inject_event_knowledge()` — the updated function will automatically include structured options when available from the enriched `EventLookup`.

- [ ] **Step 7: Wire card enrichment summaries into reward/shop knowledge**

Update `inject_reward_knowledge()` in `injector.py`:
```python
def inject_reward_knowledge(card_names: list[str], kb: GameKnowledge) -> str:
    lines = []
    total_chars = 0
    for name in card_names:
        summary = kb.cards.get_mechanic_summary(name)
        enrichment = kb.cards.get_enrichment_summary(name)
        if summary:
            line = f"- {summary}"
            if enrichment:
                line += f" [{enrichment}]"
            if total_chars + len(line) > _CARD_BUDGET_CHARS:
                break
            lines.append(line)
            total_chars += len(line)
    if not lines:
        return ""
    return "## Card Mechanics (from game data)\n" + "\n".join(lines)
```

- [ ] **Step 8: Verify injection produces output**

Run: `cd AgenticSTS && python -c "
from src.knowledge.knowledge import GameKnowledge
GameKnowledge.reset()
kb = GameKnowledge.get_instance()
from src.knowledge.injector import inject_event_knowledge, inject_keyword_glossary
print('--- Event ---')
print(inject_event_knowledge('CRYSTAL_SPHERE', kb)[:300])
print('--- Keywords ---')
print(inject_keyword_glossary({'Exhaust', 'Ethereal', 'Retain'}, kb))
"`
Expected: Event options and keyword definitions printed

- [ ] **Step 9: Commit**

```bash
git add src/knowledge/injector.py src/brain/conversation.py
git commit -m "feat: wire encounter, keyword, and enriched event/card knowledge into prompts"
```

---

## Phase 2: v0.5.3 API Upgrade

### Task 11: DynamicValue Model & Card Payload Upgrade

**Files:**
- Modify: `src/mcp_client/upstream_models.py`

- [ ] **Step 1: Add DynamicValue model**

```python
class DynamicValue(UpstreamModel):
    """v0.5.3 per-card dynamic value (damage, block, hits, etc.)."""
    name: str = ""
    base_value: float = 0
    current_value: float = 0
    enchanted_value: float | None = None
    is_modified: bool = False
    was_just_upgraded: bool = False
```

- [ ] **Step 2: Add dynamic_values and resolved_rules_text to non-hand card payloads**

Add to `RawDeckCardPayload`:
```python
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
```

Add to `RawSelectionCardPayload`:
```python
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
```

Add to `RawRewardCardOptionPayload`:
```python
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
```

Add to `RawShopCardPayload`:
```python
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
```

- [ ] **Step 3: Add helper to extract damage/block from dynamic_values**

```python
def get_damage_block_from_dynamic_values(
    dvs: list[DynamicValue],
) -> tuple[int | None, int | None, int | None]:
    """Extract (damage, block, hits) from DynamicValue list.

    Returns (None, None, None) if dynamic_values is empty (v0.5.2 compat).
    """
    if not dvs:
        return None, None, None
    damage = block = hits = None
    for dv in dvs:
        nl = dv.name.lower()
        if nl in ("damage", "calculateddamage"):
            damage = int(dv.current_value)
        elif nl in ("block", "calculatedblock"):
            block = int(dv.current_value)
        elif nl in ("hits", "calculatedhits"):
            hits = int(dv.current_value)
    return damage, block, hits
```

- [ ] **Step 4: Verify parsing with mock data**

Run: `cd AgenticSTS && python -c "
from src.mcp_client.upstream_models import RawDeckCardPayload, DynamicValue, get_damage_block_from_dynamic_values
# v0.5.3 payload
card = RawDeckCardPayload(name='Strike', dynamic_values=[
    DynamicValue(name='Damage', base_value=6, current_value=9, is_modified=True),
    DynamicValue(name='Block', base_value=0, current_value=0),
])
d, b, h = get_damage_block_from_dynamic_values(card.dynamic_values)
print(f'Strike: damage={d}, block={b}, hits={h}')
# v0.5.2 backward compat
card2 = RawDeckCardPayload(name='Strike')
d2, b2, h2 = get_damage_block_from_dynamic_values(card2.dynamic_values)
print(f'v0.5.2 compat: damage={d2}, block={b2}, hits={h2}')
"`
Expected: `Strike: damage=9, block=0, hits=None` and `v0.5.2 compat: damage=None, block=None, hits=None`

- [ ] **Step 5: Commit**

```bash
git add src/mcp_client/upstream_models.py
git commit -m "feat: add DynamicValue model and dynamic_values to all card payloads (v0.5.3)"
```

---

### Task 11b: Card Select Prompt — Show Upgrade Values via DynamicValue

**Files:**
- Modify: `src/brain/prompts/card_select.py`

This addresses the existing TODO: "Card upgrade comparison not shown at Smith."

- [ ] **Step 1: Add dynamic_values formatting to card_select prompt**

In `build_card_select_prompt()`, when displaying cards available for upgrade/remove/enchant, check for `dynamic_values` on `RawSelectionCardPayload`. If available, show current values:

```python
from src.mcp_client.upstream_models import get_damage_block_from_dynamic_values

# Inside the card list formatting:
for card in gs.selection.cards:
    parts = [f"{card.index}. {card.name}"]
    if card.upgraded:
        parts.append("[Upgraded]")
    # v0.5.3: show dynamic values when available
    if card.dynamic_values:
        d, b, h = get_damage_block_from_dynamic_values(card.dynamic_values)
        val_parts = []
        if d is not None:
            val_parts.append(f"{d} dmg")
        if b is not None and b > 0:
            val_parts.append(f"{b} block")
        if h is not None and h > 1:
            val_parts.append(f"x{h} hits")
        if val_parts:
            parts.append(f"[{' | '.join(val_parts)}]")
    if card.rules_text or card.resolved_rules_text:
        text = card.resolved_rules_text or card.rules_text
        parts.append(f"— {text[:100]}")
```

- [ ] **Step 2: Verify card_select shows values**

Manual verification during gameplay — card select screen should show damage/block numbers inline when connected to v0.5.3 server.

- [ ] **Step 3: Commit**

```bash
git add src/brain/prompts/card_select.py
git commit -m "feat: show card dynamic values in card_select prompt (v0.5.3 Smith upgrade comparison)"
```

---

### Task 12: `/actions/available` Endpoint

**Files:**
- Modify: `src/mcp_client/client.py`

- [ ] **Step 1: Add get_available_actions method**

```python
    async def get_available_actions(self) -> dict:
        """Get available actions with parameter hints (v0.5.3+).

        Returns empty dict if endpoint not available (v0.5.2 compat).
        """
        try:
            return await self._get("/actions/available")
        except Exception:
            return {}
```

**Note:** This is an API stub only. Integration into validation pipeline (using parameter hints for pre-validation in `_force_unstick()` or pre-action checks) is deferred to a future plan once we confirm the v0.5.3 endpoint behavior in practice.

- [ ] **Step 2: Commit**

```bash
git add src/mcp_client/client.py
git commit -m "feat: add /actions/available endpoint stub (v0.5.3, integration deferred)"
```

---

## Phase 3: Soft-lock Prevention

### Task 13: Overlay Catch-all in Force Unstick

**Files:**
- Modify: `src/agent/loop.py`

- [ ] **Step 1: Add modal catch-all to _force_unstick()**

At the **beginning** of `_force_unstick()` (before any state-specific logic), add:

```python
        # Overlay catch-all: dismiss unknown modals/overlays
        avail = set(gs.available_actions) if gs.available_actions else set()
        if "confirm_modal" in avail:
            logger.warning("Force-unstick: dismissing modal via confirm_modal")
            return Decision(action=confirm_modal(), source="random")
        if "dismiss_modal" in avail:
            logger.warning("Force-unstick: dismissing modal via dismiss_modal")
            return Decision(action=dismiss_modal(), source="random")
```

- [ ] **Step 2: Verify Crystal Sphere handling exists**

Search loop.py for `_is_crystal_sphere_event` and `_handle_crystal_sphere_event`. If they exist and are wired into the main decision path, no additional Crystal Sphere work is needed. If not wired, add detection in the main event handler.

- [ ] **Step 3: Add bundle selection fallback**

In the card_select / hand_select handler section of the decision loop, add a check:
```python
        # Bundle selection: if selection.kind indicates bundle, select first option
        if gs.selection and "bundle" in (gs.selection.kind or "").lower():
            logger.info("Bundle selection detected, selecting first option")
            return Decision(action=select_deck_card(0), source="heuristic")
```

- [ ] **Step 4: Commit**

```bash
git add src/agent/loop.py
git commit -m "fix: add overlay catch-all and bundle selection fallback for soft-lock prevention"
```

---

### Task 14: Final Integration Verification

**Files:**
- No new files — verification only

- [ ] **Step 1: Run full module import check**

Run: `cd AgenticSTS && python -c "
from src.knowledge.knowledge import GameKnowledge
from src.knowledge.relic_lookup import RelicLookup
from src.knowledge.encounter_lookup import EncounterLookup
from src.knowledge.act_lookup import ActLookup
from src.knowledge.enchantment_lookup import EnchantmentLookup
from src.knowledge.keyword_lookup import KeywordLookup
from src.knowledge.injector import inject_combat_knowledge, inject_encounter_knowledge, inject_keyword_glossary, inject_event_knowledge, inject_reward_knowledge
from src.mcp_client.upstream_models import DynamicValue, get_damage_block_from_dynamic_values
GameKnowledge.reset()
kb = GameKnowledge.get_instance()
print(f'All imports OK. Knowledge loaded: cards={kb.cards.count} monsters={kb.monsters.count} relics={kb.relics.count} encounters={kb.encounters.count} events={kb.events.count} acts={kb.acts.count} enchantments={kb.enchantments.count} keywords={kb.keywords.count}')
"`
Expected: All imports succeed, all counts printed

- [ ] **Step 2: Update CLAUDE.md with new knowledge modules**

Add to the Knowledge section of CLAUDE.md:
- New lookup modules (relic_lookup, encounter_lookup, act_lookup, enchantment_lookup, keyword_lookup)
- v0.5.3 DynamicValue model
- Upstream data directory (`data/knowledge/upstream/`)

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "docs: update CLAUDE.md with upstream adoption changes"
```
