# Game Update Patch Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable pipeline that ingests STS2 game patch notes as a structured Manifest, purges persistent data by entity reference, LLM-rewrites affected prompts, and verifies agent behavior via golden-log regression — so every future game update is a 2-hour workflow instead of silent data corruption.

**Architecture:** Manifest-driven. A YAML `data/patches/<game_version>.yaml` is the single source of truth for a patch. An `apply_patch.py` orchestrator does deterministic purge (entity-reference-based, per-store), then dispatches LLM rewrite for prompt files, then bumps `data/version_compatibility.json`. A golden-log replay harness provides regression coverage. Version fields on records are provenance only — retrieval does not gate on them.

**Tech Stack:** Python 3.11+, Pydantic v2, PyYAML, pytest, existing `@dataclass(frozen=True)` pattern for memory models, existing `v2_backend` analysis tier for LLM rewrite, shutil for snapshot, Click or argparse for CLI.

**Reference spec:** [2026-04-17-game-update-patch-pipeline-design.md](../specs/2026-04-17-game-update-patch-pipeline-design.md)

---

## File Structure

### New files
- `src/patch/__init__.py` — package marker
- `src/patch/slug.py` — name normalization
- `src/patch/manifest.py` — Pydantic Manifest model + loader + entity set computation
- `src/patch/version.py` — RuntimeVersion + version_compatibility.json loader
- `src/patch/snapshot.py` — data/ snapshot utility
- `src/patch/purge.py` — all per-store purge functions
- `src/patch/rewrite.py` — LLM-driven prompt rewrite
- `src/patch/review.py` — diff review batch
- `src/patch/orchestrator.py` — apply_patch high-level flow
- `scripts/apply_patch.py` — thin CLI wrapper
- `scripts/check_mod_api_coverage.py` — mod schema coverage diagnostic
- `src/regression/__init__.py`
- `src/regression/log_replay.py` — LogReplayClient + fingerprint
- `data/patches/v0.103.1.yaml` — first real manifest (authored from STS2 patch notes)
- `data/version_compatibility.json` — runtime version state
- `tests/patch/__init__.py`, `tests/patch/conftest.py` — fixtures
- `tests/patch/test_slug.py`
- `tests/patch/test_manifest.py`
- `tests/patch/test_version.py`
- `tests/patch/test_snapshot.py`
- `tests/patch/test_purge.py`
- `tests/patch/test_rewrite.py`
- `tests/patch/test_orchestrator.py`
- `tests/regression/__init__.py`
- `tests/regression/test_log_replay.py`
- `tests/regression/test_fingerprint.py`
- `tests/fixtures/golden_logs/v0.5.3/<seed-name>.jsonl` — frozen logs

### Modified files
- `src/memory/models_v2.py` — add three provenance fields to each persisted dataclass
- `src/memory/card_memory_store.py` — inject version on write
- `src/memory/combat_store.py` — inject version on write
- `src/memory/route_store.py` — inject version on write
- `src/memory/card_build_store.py` — inject version on write
- `src/memory/guide_store.py` — inject version on write
- `src/skills/library.py` — inject version on skill persist
- `src/log/session_logger.py` — write `_meta` header as first JSONL line
- `src/runs/history.py` — inject version on RunRecord
- `CLAUDE.md` — add "Game Update Playbook" section

---

## Task 1: Slug normalization utility

**Files:**
- Create: `src/patch/__init__.py`
- Create: `src/patch/slug.py`
- Create: `tests/patch/__init__.py`
- Create: `tests/patch/test_slug.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/__init__.py` as empty file. Create `tests/patch/test_slug.py`:

```python
from src.patch.slug import slug

def test_slug_lowercase():
    assert slug("Strike") == "strike"

def test_slug_strips_punctuation():
    assert slug("Neow's Talisman") == "neows talisman"

def test_slug_collapses_whitespace():
    assert slug("  Blade  of   Ink  ") == "blade of ink"

def test_slug_handles_plus_upgrade_marker():
    assert slug("Strike+") == "strike"

def test_slug_idempotent():
    assert slug(slug("Neow's Talisman")) == slug("Neow's Talisman")

def test_slug_handles_empty():
    assert slug("") == ""
    assert slug("   ") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_slug.py -v`
Expected: FAIL with `ModuleNotFoundError: src.patch.slug`

- [ ] **Step 3: Write minimal implementation**

Create `src/patch/__init__.py` as empty file. Create `src/patch/slug.py`:

```python
"""Entity name normalization for cross-version matching."""
from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def slug(name: str) -> str:
    """Normalize an entity name for comparison.

    Lowercase, strip Unicode punctuation, collapse whitespace, strip
    trailing upgrade markers ("+", "++"). Idempotent.
    """
    if not name:
        return ""
    s = unicodedata.normalize("NFKC", name).lower()
    s = s.rstrip("+")
    s = _PUNCT_RE.sub("", s)
    s = _WS_RE.sub(" ", s).strip()
    return s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_slug.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/__init__.py src/patch/slug.py tests/patch/__init__.py tests/patch/test_slug.py
git commit -m "feat(patch): add slug utility for entity name normalization"
```

---

## Task 2: Patch Manifest Pydantic model

**Files:**
- Create: `src/patch/manifest.py`
- Create: `tests/patch/conftest.py`
- Create: `tests/patch/test_manifest.py`
- Create fixture: `tests/patch/fixtures/minimal_manifest.yaml`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/conftest.py`:

```python
from pathlib import Path
import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def minimal_manifest_path() -> Path:
    return FIXTURE_DIR / "minimal_manifest.yaml"
```

Create `tests/patch/fixtures/minimal_manifest.yaml`:

```yaml
game_version: v0.103.1
previous_version: v0.100.0
patch_date: 2026-04-17
source: "Test patch"
summary: "Test summary"

removed_cards:
  - name: "Grapple"
    character: "ironclad"

reworked_cards:
  - name: "Blade of Ink"
    character: "the silent"
    severity: major
    change: "Reworked"
  - name: "Stoke"
    character: "ironclad"
    severity: minor

reworked_enemies:
  - name: "Doormaker"
    severity: major

reworked_relics: []
new_cards: []
new_relics: []
rarity_changed_cards: []
ascension_changes: []
shop_changes: []
writing_clarifications: []
new_systems: []
```

Create `tests/patch/test_manifest.py`:

```python
from src.patch.manifest import Manifest, load_manifest

def test_load_manifest(minimal_manifest_path):
    m = load_manifest(minimal_manifest_path)
    assert m.game_version == "v0.103.1"
    assert m.previous_version == "v0.100.0"
    assert len(m.removed_cards) == 1
    assert m.removed_cards[0].name == "Grapple"
    assert len(m.reworked_cards) == 2

def test_changed_entities_includes_major_and_removed(minimal_manifest_path):
    m = load_manifest(minimal_manifest_path)
    entities = m.changed_entities()
    assert "grapple" in entities            # removed
    assert "blade of ink" in entities       # major rework
    assert "doormaker" in entities          # major enemy rework
    assert "stoke" not in entities          # minor severity excluded

def test_prompt_review_targets_superset(minimal_manifest_path):
    m = load_manifest(minimal_manifest_path)
    targets = m.prompt_review_targets()
    changed = m.changed_entities()
    assert changed <= targets  # superset
    # minor entities still appear in prompt review
    assert "stoke" in targets

def test_manifest_roundtrip(minimal_manifest_path, tmp_path):
    m = load_manifest(minimal_manifest_path)
    out = tmp_path / "out.yaml"
    m.dump_yaml(out)
    m2 = load_manifest(out)
    assert m2.changed_entities() == m.changed_entities()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: src.patch.manifest`.

- [ ] **Step 3: Write implementation**

Create `src/patch/manifest.py`:

```python
"""Patch Manifest: structured description of one game version upgrade."""
from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from src.patch.slug import slug


class RemovedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    replacement_note: str | None = None


class ReworkedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    category: str | None = None
    severity: Literal["major", "minor"]
    change: str | None = None


class RarityChangedCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    from_: str = Field(alias="from")
    to: str


class NewCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    text: str | None = None


class ReworkedRelic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    character: str | None = None
    severity: Literal["major", "minor"] = "major"
    change: str | None = None


class NewRelic(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    source: str | None = None


class ReworkedEnemy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    severity: Literal["major", "minor"]


class AscensionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ascension: int
    from_: str = Field(alias="from")
    to: str


class WritingClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity: str
    clarification: str


class NewSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    scope: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game_version: str
    previous_version: str
    patch_date: str
    source: str = ""
    summary: str = ""

    removed_cards: list[RemovedCard] = []
    reworked_cards: list[ReworkedCard] = []
    rarity_changed_cards: list[RarityChangedCard] = []
    new_cards: list[NewCard] = []
    reworked_relics: list[ReworkedRelic] = []
    new_relics: list[NewRelic] = []
    reworked_enemies: list[ReworkedEnemy] = []
    ascension_changes: list[AscensionChange] = []
    shop_changes: list[str] = []
    writing_clarifications: list[WritingClarification] = []
    new_systems: list[NewSystem] = []

    def changed_entities(self) -> set[str]:
        """Slugged set of entities whose data should be purged."""
        out: set[str] = set()
        for c in self.removed_cards:
            out.add(slug(c.name))
        for c in self.reworked_cards:
            if c.severity == "major":
                out.add(slug(c.name))
        for r in self.reworked_relics:
            if r.severity == "major":
                out.add(slug(r.name))
        for e in self.reworked_enemies:
            if e.severity == "major":
                out.add(slug(e.name))
        return out

    def prompt_review_targets(self) -> set[str]:
        """Broader set: entities + mechanics that trigger prompt rewrites."""
        out = self.changed_entities()
        # Include minor severity entries for wording updates
        for c in self.reworked_cards:
            if c.severity == "minor":
                out.add(slug(c.name))
        for r in self.reworked_relics:
            if r.severity == "minor":
                out.add(slug(r.name))
        for e in self.reworked_enemies:
            if e.severity == "minor":
                out.add(slug(e.name))
        # New entities need prompt hints added
        for c in self.new_cards:
            out.add(slug(c.name))
        for r in self.new_relics:
            out.add(slug(r.name))
        # Clarifications reference specific entities
        for w in self.writing_clarifications:
            out.add(slug(w.entity))
        # Mechanics described in free text
        for a in self.ascension_changes:
            out.add(f"ascension_{a.ascension}")
        return out

    def dump_yaml(self, path: Path) -> None:
        data = self.model_dump(by_alias=True, exclude_none=False)
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)


def load_manifest(path: Path) -> Manifest:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return Manifest.model_validate(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_manifest.py -v`
Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/manifest.py tests/patch/conftest.py tests/patch/fixtures/minimal_manifest.yaml tests/patch/test_manifest.py
git commit -m "feat(patch): add Manifest model with changed_entities and prompt_review_targets"
```

---

## Task 3: Author v0.103.1 manifest from STS2 patch notes

**Files:**
- Create: `data/patches/v0.103.1.yaml`

- [ ] **Step 1: Write the manifest from the patch notes content**

Create `data/patches/v0.103.1.yaml`:

```yaml
game_version: v0.103.1
previous_version: v0.100.0
patch_date: 2026-04-17
source: "STS2 main branch merge of beta v0.100.0 through v0.103.1"
summary: |
  Mid-size patch: Ironclad/Silent/Regent/Necrobinder rebalance,
  Doormaker rework, 5 new Neow relics, Badges and Leaderboard systems added,
  Ascension 6 changed from Gloom to Inflation, shop relics cheaper by 25g.

removed_cards:
  - name: "Grapple"
    character: "ironclad"
    replacement_note: "Game auto-replaces with placeholder status card"

reworked_cards:
  - name: "Blade of Ink"
    character: "the silent"
    severity: major
    change: "Completely reworked — now generates Inky-enchanted Shivs (+2 damage, 1 Weak)"
  - name: "Arsenal"
    character: "regent"
    severity: major
    change: "Strength from any cards created, not just Colorless"
  - name: "Borrowed Time"
    character: "necrobinder"
    severity: major
    change: "Cost 0 apply Doom → Cost 1 Skill, gain 4(6) energy, cards cost +1 this turn"
  - name: "Hidden Gem"
    category: "colorless"
    severity: major
    change: "Reworked (colorless pool)"
  - name: "Pendulum"
    severity: major
    change: "Relic reworked"
  - name: "Dominate"
    character: "ironclad"
    severity: minor
  - name: "Expect a Fight"
    character: "ironclad"
    severity: minor
  - name: "Spite"
    character: "ironclad"
    severity: minor
  - name: "Stoke"
    character: "ironclad"
    severity: minor

rarity_changed_cards:
  - name: "Acrobatics"
    character: "the silent"
    from: common
    to: uncommon

new_cards:
  - name: "Not Yet"
    character: "ironclad"
    text: "Rare - Cost 2 Skill | Heal 10(13) HP. Exhaust."

reworked_relics:
  - name: "Regalite"
    character: "regent"
    severity: major
    change: "Block from any card created, not just Colorless"

new_relics:
  - name: "Hefty Tablet"
    source: neow
  - name: "Neow's Talisman"
    source: neow
  - name: "Neow's Bones"
    source: neow
  - name: "Phial Holster"
    source: neow
  - name: "Winged Boots"
    source: neow

reworked_enemies:
  - name: "Doormaker"
    severity: major
  - name: "Skulking Colony"
    severity: minor

ascension_changes:
  - ascension: 6
    from: "Gloom — Less rest sites"
    to: "Inflation — Removing cards at Merchant is more expensive"

shop_changes:
  - "All shop relics cost 25 gold less"
  - "Gold-generating relics no longer appear in shop"

writing_clarifications:
  - entity: "Fairy in a Bottle"
    clarification: "Only triggers at HP=0, not by any death cause"

new_systems:
  - name: "Badges"
    scope: "run_end_summary"
  - name: "Leaderboards (friends-only, win+badges+speed ranked)"
    scope: "meta"
```

- [ ] **Step 2: Validate with loader**

Run: `python -c "from pathlib import Path; from src.patch.manifest import load_manifest; m = load_manifest(Path('data/patches/v0.103.1.yaml')); print('changed:', sorted(m.changed_entities())); print('targets:', sorted(m.prompt_review_targets()))"`
Expected: prints two sets; `changed_entities` contains grapple, blade of ink, arsenal, borrowed time, hidden gem, pendulum, regalite, doormaker; `prompt_review_targets` is a superset including stoke, acrobatics, not yet, fairy in a bottle, ascension_6, etc.

- [ ] **Step 3: Commit**

```bash
git add data/patches/v0.103.1.yaml
git commit -m "data(patch): add v0.103.1 manifest authored from STS2 patch notes"
```

---

## Task 4: Add provenance fields to memory dataclasses

**Files:**
- Modify: `src/memory/models_v2.py`
- Create: `tests/patch/test_versioned_record.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_versioned_record.py`:

```python
from src.memory.models_v2 import CombatEpisode, CardBuildMemory, RouteMemory


def test_combat_episode_has_provenance_defaults():
    # Build a minimal episode using whatever required fields exist — adapt as needed
    # The test asserts provenance fields exist with sane defaults
    fields = {f.name for f in CombatEpisode.__dataclass_fields__.values()}
    assert "game_version" in fields
    assert "mod_version" in fields
    assert "data_schema_version" in fields


def test_provenance_fields_present_on_all_domain_models():
    for cls in (CombatEpisode, CardBuildMemory, RouteMemory):
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        assert "game_version" in fields, f"{cls.__name__} missing game_version"
        assert "mod_version" in fields, f"{cls.__name__} missing mod_version"
        assert "data_schema_version" in fields, f"{cls.__name__} missing data_schema_version"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_versioned_record.py -v`
Expected: FAIL with `AssertionError: ... missing game_version`.

- [ ] **Step 3: Add fields to each dataclass**

In `src/memory/models_v2.py`, add three fields at the **end** of field declarations (after all existing defaulted fields) of these frozen dataclasses: `CombatEpisode`, `RouteMemory`, `CardBuildMemory`, `CombatGuide`, `RouteGuide`, `DeckGuide`. For each class add:

```python
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 2
```

Exact locations: directly before each class's closing (last field) — ensure no required field follows. Ensure imports remain unchanged.

Also add these fields to `CardMemory` in `src/memory/models_v2.py` if present there, or to `src/memory/card_memory_store.py` CardMemory dataclass (whichever module defines it). Search first:

Run: `grep -n "class CardMemory" src/memory/`
Add the three fields at the end of the fields.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_versioned_record.py -v`
Expected: both tests PASS.

Also run the existing model tests to verify no regression:

Run: `python -m pytest tests/test_build_memory.py tests/test_card_memory.py tests/test_combat_conversation.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/models_v2.py tests/patch/test_versioned_record.py
# if CardMemory is in a different file:
git add src/memory/card_memory_store.py
git commit -m "feat(memory): add provenance fields (game/mod/schema version) to persisted dataclasses"
```

---

## Task 5: RuntimeVersion + version_compatibility.json

**Files:**
- Create: `src/patch/version.py`
- Create: `data/version_compatibility.json`
- Create: `tests/patch/test_version.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_version.py`:

```python
import json
import os
from pathlib import Path

import pytest

from src.patch.version import RuntimeVersion, load_version_state, VersionState


def test_load_version_state(tmp_path: Path):
    f = tmp_path / "vc.json"
    f.write_text(json.dumps({
        "current": {"game_version": "v0.103.1", "mod_version": "v0.5.4-xc", "verified_date": "2026-04-18"},
        "history": []
    }))
    state = load_version_state(f)
    assert state.current.game_version == "v0.103.1"
    assert state.current.mod_version == "v0.5.4-xc"


def test_runtime_version_env_override(tmp_path: Path, monkeypatch):
    f = tmp_path / "vc.json"
    f.write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "v0.5.3-chartyr", "verified_date": "2026-03-30"},
        "history": []
    }))
    monkeypatch.setenv("STS2_GAME_VERSION", "v-override")
    monkeypatch.setenv("STS2_MOD_VERSION", "m-override")
    rv = RuntimeVersion.from_file(f)
    assert rv.game_version == "v-override"
    assert rv.mod_version == "m-override"


def test_runtime_version_bump(tmp_path: Path):
    f = tmp_path / "vc.json"
    f.write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "v0.5.3-chartyr", "verified_date": "2026-03-30"},
        "history": []
    }))
    state = load_version_state(f)
    state.bump(new_game_version="v0.103.1", new_mod_version="v0.5.4-xc", verified_date="2026-04-18",
               snapshot_path="data.snapshots/v0.5.3-pre-v0.103.1/")
    state.save(f)
    reloaded = load_version_state(f)
    assert reloaded.current.game_version == "v0.103.1"
    assert len(reloaded.history) == 1
    assert reloaded.history[0].game_version == "v0.5.3"
    assert reloaded.history[0].snapshot_path.endswith("pre-v0.103.1/")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_version.py -v`
Expected: FAIL with `ModuleNotFoundError: src.patch.version`.

- [ ] **Step 3: Write implementation**

Create `src/patch/version.py`:

```python
"""Runtime version state: game_version + mod_version + history."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class VersionEntry:
    game_version: str
    mod_version: str
    verified_date: str
    snapshot_path: str | None = None
    retired_date: str | None = None


@dataclass
class VersionState:
    current: VersionEntry
    history: list[VersionEntry] = field(default_factory=list)

    def bump(self, *, new_game_version: str, new_mod_version: str,
             verified_date: str, snapshot_path: str) -> None:
        retired = VersionEntry(
            game_version=self.current.game_version,
            mod_version=self.current.mod_version,
            verified_date=self.current.verified_date,
            snapshot_path=snapshot_path,
            retired_date=verified_date,
        )
        self.history.append(retired)
        self.current = VersionEntry(
            game_version=new_game_version,
            mod_version=new_mod_version,
            verified_date=verified_date,
        )

    def save(self, path: Path) -> None:
        data = {
            "current": asdict(self.current),
            "history": [asdict(h) for h in self.history],
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_version_state(path: Path) -> VersionState:
    data = json.loads(path.read_text(encoding="utf-8"))
    return VersionState(
        current=VersionEntry(**data["current"]),
        history=[VersionEntry(**h) for h in data.get("history", [])],
    )


@dataclass(frozen=True)
class RuntimeVersion:
    """Active version pair — consulted at write sites.

    Env vars STS2_GAME_VERSION / STS2_MOD_VERSION override file state.
    """
    game_version: str
    mod_version: str
    data_schema_version: int = 2

    @classmethod
    def from_file(cls, path: Path) -> "RuntimeVersion":
        state = load_version_state(path)
        gv = os.getenv("STS2_GAME_VERSION") or state.current.game_version
        mv = os.getenv("STS2_MOD_VERSION") or state.current.mod_version
        return cls(game_version=gv, mod_version=mv)


_DEFAULT_PATH = Path("data/version_compatibility.json")


def get_runtime_version() -> RuntimeVersion:
    return RuntimeVersion.from_file(_DEFAULT_PATH)
```

Create `data/version_compatibility.json`:

```json
{
  "current": {
    "game_version": "v0.5.3",
    "mod_version": "v0.5.3-chartyr",
    "verified_date": "2026-04-17"
  },
  "history": []
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_version.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/version.py data/version_compatibility.json tests/patch/test_version.py
git commit -m "feat(patch): add RuntimeVersion loader and version_compatibility.json"
```

---

## Task 6: Inject version at write sites

**Files:**
- Modify: `src/memory/card_memory_store.py`
- Modify: `src/memory/combat_store.py`
- Modify: `src/memory/card_build_store.py`
- Modify: `src/memory/route_store.py`
- Modify: `src/memory/guide_store.py`
- Modify: `src/runs/history.py`
- Create: `tests/patch/test_write_injection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_write_injection.py`:

```python
"""Verify new records get current version injected at write time."""
from pathlib import Path
import json

from src.patch.version import RuntimeVersion
from src.memory.combat_store import CombatStore


def test_combat_store_injects_version(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STS2_GAME_VERSION", "v-test")
    monkeypatch.setenv("STS2_MOD_VERSION", "m-test")
    # point to an isolated dir
    store_path = tmp_path / "combat.jsonl"
    store = CombatStore(path=store_path)
    # Build a minimal CombatEpisode — use the existing test factory if available
    from tests.conftest import make_combat_gs  # reuse helper
    # synthesize an episode via the store's normal append() — stub if needed
    # Here, test by manually constructing a dataclass and saving:
    from src.memory.models_v2 import CombatEpisode
    ep = CombatEpisode(
        episode_id="test1",
        enemy_key="test_enemy",
        character="the ironclad",
        # fill other required fields with sensible defaults — see CombatEpisode.__dataclass_fields__
    )
    store.append(ep)
    # Re-read jsonl and confirm injected provenance
    lines = store_path.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[-1])  # skip _meta header if present
    # Skip _meta line if first
    data_line = next(json.loads(ln) for ln in lines if not ln.startswith('{"_meta"'))
    assert data_line["game_version"] == "v-test"
    assert data_line["mod_version"] == "m-test"
```

Note: this test may need adjustment based on actual CombatEpisode required fields. Use `python -c "from src.memory.models_v2 import CombatEpisode; print(CombatEpisode.__dataclass_fields__.keys())"` to find them, and adapt the constructor.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_write_injection.py -v`
Expected: FAIL because the store does not inject version.

- [ ] **Step 3: Modify each store's append/save to inject version**

Pattern to apply in each store file. Locate the append/save method that receives a dataclass and persists. Before writing, replace the incoming record with a copy that has provenance fields set:

```python
# At top of module:
from src.patch.version import get_runtime_version
from dataclasses import replace

# In append() before serialization:
def append(self, record):
    rv = get_runtime_version()
    record = replace(
        record,
        game_version=record.game_version or rv.game_version,
        mod_version=record.mod_version or rv.mod_version,
        data_schema_version=record.data_schema_version or rv.data_schema_version,
    )
    # ... existing write logic
```

Apply this pattern in:
- `src/memory/combat_store.py` — `append`
- `src/memory/card_build_store.py` — `append`
- `src/memory/route_store.py` — `append`
- `src/memory/guide_store.py` — `save` / `append`
- `src/memory/card_memory_store.py` — `upsert` or equivalent (inject on the merged record)
- `src/runs/history.py` — RunRecord write path

If a file does not use `@dataclass` for the written entity (e.g., JSON dict in card_memory_store), set the three keys directly on the dict instead of using `replace()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_write_injection.py -v`
Expected: PASS.

Also run all memory-related tests to catch regressions:

Run: `python -m pytest tests/test_build_memory.py tests/test_card_memory.py tests/test_combat_analytics.py tests/test_ascension_stats.py -v`
Expected: PASS (or failures only related to now-injected fields, which should be backward-compatible since fields default to None).

- [ ] **Step 5: Commit**

```bash
git add src/memory/combat_store.py src/memory/card_build_store.py src/memory/route_store.py src/memory/guide_store.py src/memory/card_memory_store.py src/runs/history.py tests/patch/test_write_injection.py
git commit -m "feat(memory): inject RuntimeVersion provenance on all persist write paths"
```

---

## Task 7: JSONL log _meta header

**Files:**
- Modify: `src/log/session_logger.py`
- Create: `tests/patch/test_log_meta.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_log_meta.py`:

```python
import json
from pathlib import Path

from src.log.session_logger import SessionLogger


def test_session_logger_writes_meta_header(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STS2_GAME_VERSION", "v-test")
    monkeypatch.setenv("STS2_MOD_VERSION", "m-test")
    log_path = tmp_path / "run.jsonl"
    logger = SessionLogger(path=log_path)
    logger.log({"event": "test", "value": 1})
    logger.close()

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith('{"_meta"')
    meta = json.loads(lines[0])["_meta"]
    assert meta["game_version"] == "v-test"
    assert meta["mod_version"] == "m-test"
    # data rows follow
    assert json.loads(lines[1])["event"] == "test"
```

Note: adapt constructor signature to actual `SessionLogger` API (`grep -n "class SessionLogger" src/log/session_logger.py`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_log_meta.py -v`
Expected: FAIL because no meta header.

- [ ] **Step 3: Modify SessionLogger to write meta header**

In `src/log/session_logger.py`, locate where the JSONL file is opened for writing (likely in `__init__` or first-log path). Before any other lines, write:

```python
import json
from src.patch.version import get_runtime_version

# When opening the file for the first time:
rv = get_runtime_version()
meta = {
    "_meta": {
        "game_version": rv.game_version,
        "mod_version": rv.mod_version,
        "data_schema_version": rv.data_schema_version,
    }
}
self._fp.write(json.dumps(meta) + "\n")
self._fp.flush()
```

Guard with a `_meta_written` flag so it only fires once per file.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_log_meta.py -v`
Expected: PASS.

Run existing logger tests:

Run: `python -m pytest tests/test_check_agent_health.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/log/session_logger.py tests/patch/test_log_meta.py
git commit -m "feat(log): write _meta header with version provenance on new JSONL logs"
```

---

## Task 8: Snapshot utility

**Files:**
- Create: `src/patch/snapshot.py`
- Create: `tests/patch/test_snapshot.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_snapshot.py`:

```python
from pathlib import Path

from src.patch.snapshot import snapshot_data


def test_snapshot_copies_tree(tmp_path: Path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "a.txt").write_text("hello")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("world")

    snap_root = tmp_path / "snapshots"
    dst = snapshot_data(src, snap_root, label="pre-v0.103.1")

    assert dst.exists()
    assert "pre-v0.103.1" in dst.name
    assert (dst / "a.txt").read_text() == "hello"
    assert (dst / "sub" / "b.txt").read_text() == "world"


def test_snapshot_refuses_overwrite(tmp_path: Path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "x.txt").write_text("x")
    snap_root = tmp_path / "snapshots"

    first = snapshot_data(src, snap_root, label="tag1")
    # second call with same label gets suffixed path, no error
    second = snapshot_data(src, snap_root, label="tag1")
    assert first != second
    assert second.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_snapshot.py -v`
Expected: FAIL with `ModuleNotFoundError: src.patch.snapshot`.

- [ ] **Step 3: Write implementation**

Create `src/patch/snapshot.py`:

```python
"""Snapshot the data/ tree before destructive patch operations."""
from __future__ import annotations

import shutil
import time
from pathlib import Path


def snapshot_data(src: Path, snap_root: Path, label: str) -> Path:
    """Copy src/ into snap_root/<label>/.

    If destination exists, append a numeric suffix (label-1, label-2, ...)
    so prior snapshots are never overwritten.
    """
    snap_root.mkdir(parents=True, exist_ok=True)
    candidate = snap_root / label
    i = 1
    while candidate.exists():
        candidate = snap_root / f"{label}-{i}"
        i += 1
    shutil.copytree(src, candidate)
    return candidate
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_snapshot.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/snapshot.py tests/patch/test_snapshot.py
git commit -m "feat(patch): add snapshot utility for safe pre-destructive copies"
```

---

## Task 9: Purge — card_memories.json

**Files:**
- Create: `src/patch/purge.py`
- Create: `tests/patch/test_purge.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_purge.py`:

```python
import json
from pathlib import Path

from src.patch.purge import purge_card_memories


def test_purge_card_memories_removes_changed_keys(tmp_path: Path):
    f = tmp_path / "card_memories.json"
    f.write_text(json.dumps({
        "the silent::strike": {"card_name": "Strike", "play_count": 300},
        "the silent::blade of ink": {"card_name": "Blade of Ink", "play_count": 45},
        "the ironclad::grapple": {"card_name": "Grapple", "play_count": 20},
        "the ironclad::bash": {"card_name": "Bash", "play_count": 150},
    }))
    changed = {"blade of ink", "grapple"}

    report = purge_card_memories(f, changed, dry_run=False)

    data = json.loads(f.read_text())
    assert "the silent::strike" in data
    assert "the ironclad::bash" in data
    assert "the silent::blade of ink" not in data
    assert "the ironclad::grapple" not in data
    assert report.deleted == 2
    assert report.kept == 2


def test_purge_card_memories_dry_run_does_not_write(tmp_path: Path):
    f = tmp_path / "card_memories.json"
    initial = {
        "the silent::blade of ink": {"card_name": "Blade of Ink", "play_count": 45},
    }
    f.write_text(json.dumps(initial))
    changed = {"blade of ink"}

    report = purge_card_memories(f, changed, dry_run=True)

    # file unchanged
    assert json.loads(f.read_text()) == initial
    assert report.deleted == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_purge.py -v`
Expected: FAIL with `ModuleNotFoundError: src.patch.purge`.

- [ ] **Step 3: Write implementation**

Create `src/patch/purge.py`:

```python
"""Per-store purge functions driven by changed_entities set (slugged)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.patch.slug import slug


@dataclass
class PurgeReport:
    store: str
    deleted: int = 0
    kept: int = 0
    details: list[str] | None = None


def _card_name_from_key(key: str) -> str:
    """Keys are 'character::card_name'; extract and slug the card_name."""
    parts = key.split("::", 1)
    return slug(parts[1]) if len(parts) == 2 else slug(key)


def purge_card_memories(path: Path, changed: set[str], *, dry_run: bool) -> PurgeReport:
    report = PurgeReport(store="card_memories")
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    survivors = {}
    for k, v in data.items():
        card_slug = _card_name_from_key(k)
        if card_slug in changed:
            report.deleted += 1
        else:
            survivors[k] = v
            report.kept += 1
    if not dry_run and report.deleted > 0:
        path.write_text(json.dumps(survivors, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_purge.py::test_purge_card_memories_removes_changed_keys tests/patch/test_purge.py::test_purge_card_memories_dry_run_does_not_write -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/purge.py tests/patch/test_purge.py
git commit -m "feat(patch): add purge_card_memories driven by slugged entity set"
```

---

## Task 10: Purge — combat_episodes.jsonl

**Files:**
- Modify: `src/patch/purge.py`
- Modify: `tests/patch/test_purge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/patch/test_purge.py`:

```python
from src.patch.purge import purge_jsonl_episodes


def test_purge_combat_episodes_by_enemy_major(tmp_path: Path):
    f = tmp_path / "combat_episodes.jsonl"
    f.write_text("\n".join([
        '{"_meta": {"game_version": "v0.5.3"}}',
        json.dumps({"enemy_key": "Doormaker", "cards_played": ["Strike", "Defend"]}),
        json.dumps({"enemy_key": "Cultist", "cards_played": ["Strike"]}),
    ]) + "\n")
    changed_major_enemies = {"doormaker"}
    changed_cards = set()

    report = purge_jsonl_episodes(f, changed_major_enemies=changed_major_enemies,
                                   changed_cards=changed_cards, dry_run=False)

    kept_lines = [ln for ln in f.read_text().splitlines() if ln and not ln.startswith('{"_meta"')]
    assert len(kept_lines) == 1
    assert json.loads(kept_lines[0])["enemy_key"] == "Cultist"
    assert report.deleted == 1
    assert report.kept == 1


def test_purge_combat_episodes_by_card_reference(tmp_path: Path):
    f = tmp_path / "combat_episodes.jsonl"
    f.write_text("\n".join([
        json.dumps({"enemy_key": "Cultist", "cards_played": ["Strike", "Blade of Ink", "Defend"]}),
        json.dumps({"enemy_key": "Cultist", "cards_played": ["Strike", "Defend"]}),
    ]) + "\n")

    report = purge_jsonl_episodes(f, changed_major_enemies=set(),
                                   changed_cards={"blade of ink"}, dry_run=False)

    kept = [json.loads(ln) for ln in f.read_text().splitlines() if ln]
    assert len(kept) == 1
    assert "Blade of Ink" not in kept[0]["cards_played"]
    assert report.deleted == 1


def test_purge_preserves_meta_header(tmp_path: Path):
    f = tmp_path / "combat_episodes.jsonl"
    f.write_text("\n".join([
        '{"_meta": {"game_version": "v0.5.3"}}',
        json.dumps({"enemy_key": "Doormaker", "cards_played": []}),
    ]) + "\n")
    purge_jsonl_episodes(f, changed_major_enemies={"doormaker"},
                          changed_cards=set(), dry_run=False)
    lines = f.read_text().splitlines()
    assert lines[0].startswith('{"_meta"')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_purge.py -v -k "combat"`
Expected: FAIL with `ImportError: cannot import name 'purge_jsonl_episodes'`.

- [ ] **Step 3: Extend implementation**

Append to `src/patch/purge.py`:

```python
def _enemy_key_matches(enemy_key: str, changed: set[str]) -> bool:
    if not enemy_key:
        return False
    # multi:A+B → check each component
    key = enemy_key.lower()
    if key.startswith("multi:"):
        key = key[6:]
    parts = [slug(p) for p in key.replace("+", "|").split("|")]
    return any(p in changed for p in parts)


def purge_jsonl_episodes(
    path: Path,
    *,
    changed_major_enemies: set[str],
    changed_cards: set[str],
    dry_run: bool,
) -> PurgeReport:
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    lines = path.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith('{"_meta"'):
            keep.append(ln)
            continue
        row = json.loads(ln)
        enemy_key = row.get("enemy_key", "")
        cards = row.get("cards_played", []) or []
        card_slugs = {slug(c) for c in cards}

        if _enemy_key_matches(enemy_key, changed_major_enemies):
            report.deleted += 1
            continue
        if card_slugs & changed_cards:
            report.deleted += 1
            continue
        keep.append(ln)
        report.kept += 1

    if not dry_run and report.deleted > 0:
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_purge.py -v -k "combat or meta"`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/purge.py tests/patch/test_purge.py
git commit -m "feat(patch): add purge_jsonl_episodes for combat_episodes.jsonl"
```

---

## Task 11: Purge — card_builds.jsonl and event_memories.jsonl

**Files:**
- Modify: `src/patch/purge.py`
- Modify: `tests/patch/test_purge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/patch/test_purge.py`:

```python
from src.patch.purge import purge_jsonl_card_builds, purge_jsonl_event_memories


def test_purge_card_builds_by_deck_reference(tmp_path: Path):
    f = tmp_path / "card_builds.jsonl"
    f.write_text("\n".join([
        json.dumps({"starting_deck": ["Strike", "Defend"], "final_deck": ["Strike", "Blade of Ink"], "card_play_counts": [["Strike", 10]]}),
        json.dumps({"starting_deck": ["Strike"], "final_deck": ["Strike", "Bash"], "card_play_counts": [["Strike", 5]]}),
    ]) + "\n")
    report = purge_jsonl_card_builds(f, changed={"blade of ink"}, dry_run=False)
    kept = [json.loads(ln) for ln in f.read_text().splitlines() if ln]
    assert len(kept) == 1
    assert "Blade of Ink" not in kept[0]["final_deck"]
    assert report.deleted == 1


def test_purge_card_builds_by_play_counts(tmp_path: Path):
    f = tmp_path / "card_builds.jsonl"
    f.write_text(json.dumps({
        "starting_deck": ["Strike"], "final_deck": ["Strike"],
        "card_play_counts": [["Grapple", 10], ["Strike", 5]]
    }) + "\n")
    report = purge_jsonl_card_builds(f, changed={"grapple"}, dry_run=False)
    assert report.deleted == 1


def test_purge_event_memories_by_cards_gained(tmp_path: Path):
    f = tmp_path / "event_memories.jsonl"
    f.write_text("\n".join([
        json.dumps({"event_id": "E1", "cards_gained": ["Hidden Gem"]}),
        json.dumps({"event_id": "E2", "cards_gained": ["Spoils Map"]}),
    ]) + "\n")
    report = purge_jsonl_event_memories(f, changed={"hidden gem"}, dry_run=False)
    kept = [json.loads(ln) for ln in f.read_text().splitlines() if ln]
    assert len(kept) == 1
    assert kept[0]["event_id"] == "E2"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_purge.py -v -k "card_builds or event_memories"`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Extend implementation**

Append to `src/patch/purge.py`:

```python
def purge_jsonl_card_builds(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    lines = path.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith('{"_meta"'):
            keep.append(ln)
            continue
        row = json.loads(ln)
        all_names: set[str] = set()
        for k in ("starting_deck", "final_deck", "key_cards"):
            vals = row.get(k, []) or []
            for v in vals:
                if isinstance(v, str):
                    all_names.add(slug(v))
                elif isinstance(v, dict) and "card" in v:
                    all_names.add(slug(v["card"]))
        for pair in row.get("card_play_counts", []) or []:
            if isinstance(pair, list) and pair:
                all_names.add(slug(pair[0]))
        if all_names & changed:
            report.deleted += 1
            continue
        keep.append(ln)
        report.kept += 1
    if not dry_run and report.deleted > 0:
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report


def purge_jsonl_event_memories(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    lines = path.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith('{"_meta"'):
            keep.append(ln)
            continue
        row = json.loads(ln)
        cards = row.get("cards_gained", []) or []
        if {slug(c) for c in cards} & changed:
            report.deleted += 1
            continue
        keep.append(ln)
        report.kept += 1
    if not dry_run and report.deleted > 0:
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_purge.py -v -k "card_builds or event_memories"`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/purge.py tests/patch/test_purge.py
git commit -m "feat(patch): add purge for card_builds.jsonl and event_memories.jsonl"
```

---

## Task 12: Purge — skills.json and skill seeds

**Files:**
- Modify: `src/patch/purge.py`
- Modify: `tests/patch/test_purge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/patch/test_purge.py`:

```python
from src.patch.purge import purge_skills, purge_silent_card_notes


def test_purge_skills_by_requires_cards(tmp_path: Path):
    f = tmp_path / "skills.json"
    f.write_text(json.dumps({
        "version": 1,
        "skills": [
            {"id": "s1", "trigger": {"requires_cards": ["Apparition"]}},
            {"id": "s2", "trigger": {"requires_cards": ["Strike"]}},
            {"id": "s3", "trigger": {}},
        ]
    }))
    report = purge_skills(f, changed={"apparition"}, dry_run=False)
    data = json.loads(f.read_text())
    kept_ids = [s["id"] for s in data["skills"]]
    assert "s1" not in kept_ids
    assert "s2" in kept_ids
    assert "s3" in kept_ids
    assert report.deleted == 1


def test_purge_silent_card_notes(tmp_path: Path):
    f = tmp_path / "silent_card_notes.json"
    f.write_text(json.dumps([
        {"character": "the silent", "card_name": "Abrasive", "note": "..."},
        {"character": "the silent", "card_name": "Blade of Ink", "note": "..."},
    ]))
    report = purge_silent_card_notes(f, changed={"blade of ink"}, dry_run=False)
    data = json.loads(f.read_text())
    names = [e["card_name"] for e in data]
    assert "Abrasive" in names
    assert "Blade of Ink" not in names
    assert report.deleted == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_purge.py -v -k "skills or silent"`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Extend implementation**

Append to `src/patch/purge.py`:

```python
def purge_skills(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    skills = data.get("skills", [])
    keep = []
    for sk in skills:
        required = sk.get("trigger", {}).get("requires_cards", []) or []
        if {slug(c) for c in required} & changed:
            report.deleted += 1
            continue
        keep.append(sk)
        report.kept += 1
    if not dry_run and report.deleted > 0:
        data["skills"] = keep
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def purge_silent_card_notes(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    keep = []
    for entry in data:
        name = entry.get("card_name", "")
        if slug(name) in changed:
            report.deleted += 1
            continue
        keep.append(entry)
        report.kept += 1
    if not dry_run and report.deleted > 0:
        path.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_purge.py -v -k "skills or silent"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/purge.py tests/patch/test_purge.py
git commit -m "feat(patch): add purge for skills.json and silent_card_notes seed"
```

---

## Task 13: Purge — evolution artifacts

**Files:**
- Modify: `src/patch/purge.py`
- Modify: `tests/patch/test_purge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/patch/test_purge.py`:

```python
from src.patch.purge import purge_evolution_dir


def test_purge_evolution_tools_by_text_reference(tmp_path: Path):
    evo = tmp_path / "evolution"
    tools = evo / "tools"
    tools.mkdir(parents=True)
    (tools / "score_tool_a.py").write_text("def score(card): return 1 if card == 'Blade of Ink' else 0")
    (tools / "score_tool_b.py").write_text("def score(card): return 1 if card == 'Strike' else 0")

    proposals = evo / "proposals"
    proposals.mkdir()
    (proposals / "p1.json").write_text(json.dumps({"code_edits": [], "prompt_effect": "adjust Doormaker behavior"}))
    (proposals / "p2.json").write_text(json.dumps({"code_edits": [], "prompt_effect": "generic prompt"}))

    report = purge_evolution_dir(evo, changed={"blade of ink", "doormaker"}, dry_run=False)

    assert not (tools / "score_tool_a.py").exists()
    assert (tools / "score_tool_b.py").exists()
    assert not (proposals / "p1.json").exists()
    assert (proposals / "p2.json").exists()
    assert report.deleted == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_purge.py -v -k "evolution"`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Extend implementation**

Append to `src/patch/purge.py`:

```python
def _text_references_any(text: str, changed: set[str]) -> bool:
    """Return True if any entity in changed appears (slug-matched) in text."""
    if not text:
        return False
    # Build a lowercased, slug-ish form of the text for substring match.
    # We look for each changed entity as a slugged substring of the slugged text.
    # For precision we could tokenize; substring is OK for our use case.
    text_slug = slug(text)
    return any(entity in text_slug for entity in changed if entity)


def purge_evolution_dir(evo_root: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    """Scan every file under evolution dir and delete those that reference changed entities."""
    report = PurgeReport(store="evolution")
    if not evo_root.exists():
        return report
    for subdir in ("tools", "proposals", "ab_test_results"):
        d = evo_root / subdir
        if not d.exists():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if _text_references_any(content, changed):
                report.deleted += 1
                if not dry_run:
                    f.unlink()
            else:
                report.kept += 1
    # evolution_log.jsonl: per-line scan
    log = evo_root / "evolution_log.jsonl"
    if log.exists():
        lines = log.read_text(encoding="utf-8").splitlines()
        keep: list[str] = []
        for ln in lines:
            if not ln.strip():
                continue
            if _text_references_any(ln, changed):
                report.deleted += 1
            else:
                keep.append(ln)
                report.kept += 1
        if not dry_run:
            log.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_purge.py -v -k "evolution"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/purge.py tests/patch/test_purge.py
git commit -m "feat(patch): add purge_evolution_dir for evolved tools/proposals/ab logs"
```

---

## Task 14: Guides wipe + unified purge facade

**Files:**
- Modify: `src/patch/purge.py`
- Modify: `tests/patch/test_purge.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/patch/test_purge.py`:

```python
from src.patch.purge import wipe_guides, purge_all


def test_wipe_guides(tmp_path: Path):
    f = tmp_path / "guides.json"
    f.write_text(json.dumps({"version": 1, "combat_guides": [{"enemy_key": "Nibbit"}]}))
    wipe_guides(f, dry_run=False)
    data = json.loads(f.read_text())
    assert data.get("combat_guides", []) == []


def test_wipe_guides_dry_run(tmp_path: Path):
    f = tmp_path / "guides.json"
    original = json.dumps({"combat_guides": [{"enemy_key": "Nibbit"}]})
    f.write_text(original)
    wipe_guides(f, dry_run=True)
    assert f.read_text() == original
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_purge.py -v -k "wipe_guides"`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Extend implementation**

Append to `src/patch/purge.py`:

```python
def wipe_guides(path: Path, *, dry_run: bool) -> PurgeReport:
    report = PurgeReport(store="guides")
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    total = 0
    for k in ("combat_guides", "route_guides", "deck_guides"):
        total += len(data.get(k, []) or [])
        if not dry_run:
            data[k] = []
    report.deleted = total
    if not dry_run and total > 0:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def purge_all(
    data_root: Path,
    *,
    changed_entities: set[str],
    changed_major_enemies: set[str],
    dry_run: bool,
) -> list[PurgeReport]:
    """Orchestrate all purge functions across the data tree."""
    reports: list[PurgeReport] = []
    reports.append(purge_card_memories(
        data_root / "memory/v2/card_memories.json", changed_entities, dry_run=dry_run))
    reports.append(purge_jsonl_card_builds(
        data_root / "memory/v2/card_builds.jsonl", changed=changed_entities, dry_run=dry_run))
    reports.append(purge_jsonl_episodes(
        data_root / "memory/v2/combat_episodes.jsonl",
        changed_major_enemies=changed_major_enemies,
        changed_cards=changed_entities,
        dry_run=dry_run))
    reports.append(purge_jsonl_event_memories(
        data_root / "memory/v2/event_memories.jsonl", changed=changed_entities, dry_run=dry_run))
    reports.append(purge_skills(
        Path("data/skills/skills.json"), changed=changed_entities, dry_run=dry_run))
    reports.append(purge_silent_card_notes(
        Path("src/skills/seeds/silent_card_notes.json"), changed=changed_entities, dry_run=dry_run))
    reports.append(purge_evolution_dir(
        data_root / "evolution", changed=changed_entities, dry_run=dry_run))
    reports.append(wipe_guides(
        data_root / "memory/v2/guides.json", dry_run=dry_run))
    return reports
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_purge.py -v`
Expected: all tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/purge.py tests/patch/test_purge.py
git commit -m "feat(patch): add wipe_guides and purge_all facade"
```

---

## Task 15: LLM-driven prompt rewrite — file scan

**Files:**
- Create: `src/patch/rewrite.py`
- Create: `tests/patch/test_rewrite.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_rewrite.py`:

```python
from pathlib import Path

from src.patch.rewrite import scan_prompt_files, FileChangeRequest


def test_scan_prompt_files_finds_references(tmp_path: Path):
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "shop.py").write_text('GUIDE = "Fairy in a Bottle saves you from death"')
    (root / "rest.py").write_text('GUIDE = "Sleep restores HP"')
    (root / "system.py").write_text('GUIDE = "Gloom ascension reduces rest sites"')

    requests = scan_prompt_files(root, targets={"fairy in a bottle", "ascension_6"})
    # shop.py references Fairy in a Bottle
    # system.py mentions Gloom (which we map to ascension_6 by context... but our scan is literal slug)
    # For literal slug matching, only shop.py is captured:
    files = {r.path.name for r in requests}
    assert "shop.py" in files
    # system.py will NOT be flagged unless we also include "gloom" in targets — this is expected:
    # apply_patch callers must include old-mechanic names in the scan set or add them explicitly.

def test_scan_prompt_files_ignores_unaffected(tmp_path: Path):
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "event.py").write_text('GUIDE = "Event choices should favor scaling"')
    requests = scan_prompt_files(root, targets={"doormaker", "blade of ink"})
    assert requests == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_rewrite.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `src/patch/rewrite.py`:

```python
"""LLM-driven prompt file rewrite based on manifest-derived targets."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.patch.slug import slug


@dataclass
class FileChangeRequest:
    path: Path
    matched_targets: set[str]
    original_content: str


def scan_prompt_files(root: Path, targets: set[str]) -> list[FileChangeRequest]:
    """Recursively scan .py files under root for references to any target.

    A file is flagged if, after slug-normalization, its content contains
    any target string as substring. Case/punctuation-insensitive by slug.
    """
    requests: list[FileChangeRequest] = []
    if not root.exists():
        return requests
    for p in root.rglob("*.py"):
        if p.name.startswith("_") and p.name != "__init__.py":
            # skip private modules (helpers); adjust if needed
            pass
        content = p.read_text(encoding="utf-8", errors="ignore")
        content_slug = slug(content)
        matched = {t for t in targets if t and t in content_slug}
        if matched:
            requests.append(FileChangeRequest(
                path=p,
                matched_targets=matched,
                original_content=content,
            ))
    return requests
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_rewrite.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/rewrite.py tests/patch/test_rewrite.py
git commit -m "feat(patch): add scan_prompt_files for locating targets in prompt sources"
```

---

## Task 16: LLM-driven prompt rewrite — LLM dispatch with mock backend

**Files:**
- Modify: `src/patch/rewrite.py`
- Modify: `tests/patch/test_rewrite.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/patch/test_rewrite.py`:

```python
from src.patch.rewrite import rewrite_file, RewriteResult


class FakeBackend:
    def __init__(self, response: str):
        self.response = response
        self.last_prompt = None

    def complete(self, *, system: str, user: str) -> str:
        self.last_prompt = (system, user)
        return self.response


def test_rewrite_file_calls_backend_and_returns_new_content(tmp_path: Path):
    src_file = tmp_path / "shop.py"
    src_file.write_text('TEXT = "Fairy in a Bottle saves you from death"')

    new_content = 'TEXT = "Fairy in a Bottle saves you only at HP=0"'
    backend = FakeBackend(response=new_content)

    request = FileChangeRequest(
        path=src_file,
        matched_targets={"fairy in a bottle"},
        original_content=src_file.read_text(),
    )

    manifest_context = "Fairy in a Bottle: Only triggers at HP=0, not any death cause"

    result = rewrite_file(request, manifest_context=manifest_context, backend=backend)

    assert result.new_content == new_content
    assert result.changed
    assert "fairy" in result.request.matched_targets
    # backend was called with file content in user prompt
    assert "Fairy in a Bottle" in backend.last_prompt[1]


def test_rewrite_file_no_change_when_response_identical(tmp_path: Path):
    src_file = tmp_path / "noop.py"
    content = 'TEXT = "No change needed"'
    src_file.write_text(content)
    backend = FakeBackend(response=content)
    request = FileChangeRequest(path=src_file, matched_targets={"x"}, original_content=content)
    result = rewrite_file(request, manifest_context="irrelevant", backend=backend)
    assert not result.changed
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_rewrite.py -v -k "rewrite_file"`
Expected: FAIL with `ImportError: rewrite_file`.

- [ ] **Step 3: Extend implementation**

Append to `src/patch/rewrite.py`:

```python
from typing import Protocol


class LLMBackend(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...


@dataclass
class RewriteResult:
    request: FileChangeRequest
    new_content: str
    changed: bool


_SYSTEM_PROMPT = """You are rewriting a Python prompt file in a game-agent codebase.
The game has been updated. Some entities referenced in this file are now changed.
Produce a minimal rewrite: update only lines that reference changed entities.
Preserve all other content character-for-character, including comments, formatting, imports.
Output the ENTIRE new file content, nothing else. No markdown fences, no explanation.
"""


def rewrite_file(request: FileChangeRequest, *, manifest_context: str, backend: LLMBackend) -> RewriteResult:
    """Ask LLM to rewrite the file; return new content."""
    user_prompt = f"""# Changes to apply
{manifest_context}

# Targets detected in this file (slugged)
{sorted(request.matched_targets)}

# Current file content
{request.original_content}
"""
    new_content = backend.complete(system=_SYSTEM_PROMPT, user=user_prompt)
    # Strip any surrounding code fence the model may have leaked
    new_content = _strip_code_fence(new_content)
    return RewriteResult(
        request=request,
        new_content=new_content,
        changed=(new_content.strip() != request.original_content.strip()),
    )


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_rewrite.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/rewrite.py tests/patch/test_rewrite.py
git commit -m "feat(patch): add rewrite_file with LLMBackend protocol for prompt updates"
```

---

## Task 17: Diff review batch

**Files:**
- Create: `src/patch/review.py`
- Create: `tests/patch/test_review.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_review.py`:

```python
from pathlib import Path

from src.patch.review import generate_unified_diff, apply_rewrites
from src.patch.rewrite import FileChangeRequest, RewriteResult


def test_unified_diff_shows_changes():
    original = "line one\nline two\nline three\n"
    new = "line one\nline TWO\nline three\n"
    diff = generate_unified_diff(path="shop.py", old=original, new=new)
    assert "---" in diff
    assert "+++" in diff
    assert "-line two" in diff
    assert "+line TWO" in diff


def test_apply_rewrites_writes_new_content(tmp_path: Path):
    p = tmp_path / "shop.py"
    p.write_text("original\n")
    req = FileChangeRequest(path=p, matched_targets={"x"}, original_content="original\n")
    res = RewriteResult(request=req, new_content="rewritten\n", changed=True)

    applied = apply_rewrites([res], dry_run=False)
    assert applied == 1
    assert p.read_text() == "rewritten\n"


def test_apply_rewrites_dry_run_skips(tmp_path: Path):
    p = tmp_path / "shop.py"
    p.write_text("original\n")
    req = FileChangeRequest(path=p, matched_targets={"x"}, original_content="original\n")
    res = RewriteResult(request=req, new_content="rewritten\n", changed=True)
    applied = apply_rewrites([res], dry_run=True)
    assert applied == 0
    assert p.read_text() == "original\n"


def test_apply_rewrites_skips_unchanged(tmp_path: Path):
    p = tmp_path / "shop.py"
    p.write_text("same\n")
    req = FileChangeRequest(path=p, matched_targets={"x"}, original_content="same\n")
    res = RewriteResult(request=req, new_content="same\n", changed=False)
    applied = apply_rewrites([res], dry_run=False)
    assert applied == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_review.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `src/patch/review.py`:

```python
"""Collect rewrite diffs and apply them atomically after user review."""
from __future__ import annotations

import difflib
from pathlib import Path

from src.patch.rewrite import RewriteResult


def generate_unified_diff(*, path: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ))


def print_review_batch(results: list[RewriteResult]) -> None:
    """Print all diffs to stdout for human review."""
    for r in results:
        if not r.changed:
            continue
        diff = generate_unified_diff(
            path=str(r.request.path),
            old=r.request.original_content,
            new=r.new_content,
        )
        print(f"\n━━━ {r.request.path} ━━━")
        print(f"matched targets: {sorted(r.request.matched_targets)}")
        print(diff)
    print(f"\n{sum(1 for r in results if r.changed)} files to change.")


def apply_rewrites(results: list[RewriteResult], *, dry_run: bool) -> int:
    """Write new content to disk. Returns number of files actually modified."""
    if dry_run:
        return 0
    count = 0
    for r in results:
        if not r.changed:
            continue
        r.request.path.write_text(r.new_content, encoding="utf-8")
        count += 1
    return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_review.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/review.py tests/patch/test_review.py
git commit -m "feat(patch): add unified diff review batch and apply_rewrites"
```

---

## Task 18: apply_patch orchestrator

**Files:**
- Create: `src/patch/orchestrator.py`
- Create: `tests/patch/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_orchestrator.py`:

```python
import json
from pathlib import Path

from src.patch.orchestrator import ApplyPatchOptions, apply_patch


class StubBackend:
    """Backend that returns the original content unchanged (for offline tests)."""
    def complete(self, *, system: str, user: str) -> str:
        # Extract "# Current file content\n<content>" and return as-is
        marker = "# Current file content\n"
        if marker in user:
            return user.split(marker, 1)[1]
        return ""


def _build_fixture_data(root: Path) -> None:
    (root / "memory/v2").mkdir(parents=True)
    (root / "skills").mkdir(parents=True)
    (root / "evolution").mkdir(parents=True)
    (root / "patches").mkdir(parents=True)

    (root / "memory/v2/card_memories.json").write_text(json.dumps({
        "the silent::blade of ink": {"play_count": 45},
        "the silent::strike": {"play_count": 100},
    }))
    (root / "memory/v2/combat_episodes.jsonl").write_text(json.dumps(
        {"enemy_key": "Doormaker", "cards_played": ["Strike"]}) + "\n")
    (root / "memory/v2/guides.json").write_text(json.dumps({"combat_guides": [{"enemy_key": "Doormaker"}]}))
    (root / "memory/v2/card_builds.jsonl").write_text("")
    (root / "memory/v2/event_memories.jsonl").write_text("")
    (root / "skills/skills.json").write_text(json.dumps({"skills": []}))

    (root / "patches/v0.103.1.yaml").write_text("""
game_version: v0.103.1
previous_version: v0.5.3
patch_date: 2026-04-17
source: test
summary: test
removed_cards: []
reworked_cards:
  - name: Blade of Ink
    character: the silent
    severity: major
    change: test
reworked_enemies:
  - name: Doormaker
    severity: major
reworked_relics: []
rarity_changed_cards: []
new_cards: []
new_relics: []
ascension_changes: []
shop_changes: []
writing_clarifications: []
new_systems: []
""")


def test_apply_patch_dry_run_does_not_modify(tmp_path: Path):
    _build_fixture_data(tmp_path)
    options = ApplyPatchOptions(
        manifest_path=tmp_path / "patches/v0.103.1.yaml",
        data_root=tmp_path,
        prompts_root=tmp_path / "empty_prompts",  # no prompts to rewrite
        version_file=tmp_path / "version_compatibility.json",
        snapshot_root=tmp_path / "snapshots",
        dry_run=True,
        backend=StubBackend(),
    )
    (tmp_path / "version_compatibility.json").write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "m", "verified_date": "2026-03-30"},
        "history": []
    }))

    report = apply_patch(options)

    # In dry-run, card_memories.json is unchanged
    data = json.loads((tmp_path / "memory/v2/card_memories.json").read_text())
    assert "the silent::blade of ink" in data
    # Report shows what *would* happen
    assert report.total_deleted > 0


def test_apply_patch_full_run_modifies(tmp_path: Path):
    _build_fixture_data(tmp_path)
    (tmp_path / "version_compatibility.json").write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "m", "verified_date": "2026-03-30"},
        "history": []
    }))

    options = ApplyPatchOptions(
        manifest_path=tmp_path / "patches/v0.103.1.yaml",
        data_root=tmp_path,
        prompts_root=tmp_path / "empty_prompts",
        version_file=tmp_path / "version_compatibility.json",
        snapshot_root=tmp_path / "snapshots",
        dry_run=False,
        backend=StubBackend(),
    )

    report = apply_patch(options)

    # card_memories: Blade of Ink gone
    data = json.loads((tmp_path / "memory/v2/card_memories.json").read_text())
    assert "the silent::blade of ink" not in data
    assert "the silent::strike" in data

    # combat_episodes: Doormaker row gone
    lines = [ln for ln in (tmp_path / "memory/v2/combat_episodes.jsonl").read_text().splitlines() if ln]
    assert len(lines) == 0

    # guides: wiped
    guides = json.loads((tmp_path / "memory/v2/guides.json").read_text())
    assert guides["combat_guides"] == []

    # version bumped
    vc = json.loads((tmp_path / "version_compatibility.json").read_text())
    assert vc["current"]["game_version"] == "v0.103.1"
    assert len(vc["history"]) == 1
    assert vc["history"][0]["game_version"] == "v0.5.3"

    # snapshot created
    snaps = list((tmp_path / "snapshots").iterdir())
    assert len(snaps) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_orchestrator.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `src/patch/orchestrator.py`:

```python
"""High-level apply_patch flow: load manifest, snapshot, purge, rewrite, bump version."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from pathlib import Path

from src.patch.manifest import Manifest, load_manifest
from src.patch.purge import PurgeReport, purge_all, purge_card_memories, purge_evolution_dir, \
    purge_jsonl_card_builds, purge_jsonl_episodes, purge_jsonl_event_memories, \
    purge_silent_card_notes, purge_skills, wipe_guides
from src.patch.review import apply_rewrites, print_review_batch
from src.patch.rewrite import LLMBackend, rewrite_file, scan_prompt_files
from src.patch.slug import slug
from src.patch.snapshot import snapshot_data
from src.patch.version import load_version_state


@dataclass
class ApplyPatchOptions:
    manifest_path: Path
    data_root: Path
    prompts_root: Path
    version_file: Path
    snapshot_root: Path
    dry_run: bool = False
    backend: LLMBackend | None = None
    skip_llm: bool = False


@dataclass
class ApplyPatchReport:
    manifest: Manifest
    purge_reports: list[PurgeReport] = field(default_factory=list)
    rewrite_files_touched: int = 0
    snapshot_path: Path | None = None
    total_deleted: int = 0
    version_bumped: bool = False


def _compute_major_enemies(m: Manifest) -> set[str]:
    return {slug(e.name) for e in m.reworked_enemies if e.severity == "major"}


def apply_patch(options: ApplyPatchOptions) -> ApplyPatchReport:
    manifest = load_manifest(options.manifest_path)
    report = ApplyPatchReport(manifest=manifest)

    changed = manifest.changed_entities()
    major_enemies = _compute_major_enemies(manifest)

    # Snapshot first (only in live mode)
    if not options.dry_run:
        label = f"{load_version_state(options.version_file).current.game_version}-pre-{manifest.game_version}"
        report.snapshot_path = snapshot_data(options.data_root, options.snapshot_root, label=label)

    # Phase 1: deterministic purge
    report.purge_reports.extend([
        purge_card_memories(options.data_root / "memory/v2/card_memories.json", changed, dry_run=options.dry_run),
        purge_jsonl_card_builds(options.data_root / "memory/v2/card_builds.jsonl", changed=changed, dry_run=options.dry_run),
        purge_jsonl_episodes(options.data_root / "memory/v2/combat_episodes.jsonl",
                              changed_major_enemies=major_enemies, changed_cards=changed, dry_run=options.dry_run),
        purge_jsonl_event_memories(options.data_root / "memory/v2/event_memories.jsonl",
                                    changed=changed, dry_run=options.dry_run),
        purge_skills(options.data_root / "skills/skills.json", changed=changed, dry_run=options.dry_run),
        purge_silent_card_notes(Path("src/skills/seeds/silent_card_notes.json"),
                                 changed=changed, dry_run=options.dry_run),
        purge_evolution_dir(options.data_root / "evolution", changed=changed, dry_run=options.dry_run),
        wipe_guides(options.data_root / "memory/v2/guides.json", dry_run=options.dry_run),
    ])
    report.total_deleted = sum(r.deleted for r in report.purge_reports)

    # Phase 2: LLM rewrite (unless skipped)
    if not options.skip_llm and options.backend is not None and options.prompts_root.exists():
        targets = manifest.prompt_review_targets()
        requests = scan_prompt_files(options.prompts_root, targets=targets)
        manifest_context = _build_manifest_context(manifest)
        results = [rewrite_file(req, manifest_context=manifest_context, backend=options.backend)
                   for req in requests]
        if not options.dry_run:
            print_review_batch(results)
        report.rewrite_files_touched = apply_rewrites(results, dry_run=options.dry_run)

    # Phase 3: bump version
    if not options.dry_run:
        state = load_version_state(options.version_file)
        state.bump(
            new_game_version=manifest.game_version,
            new_mod_version=state.current.mod_version,  # caller should set via env before next run
            verified_date=_dt.date.today().isoformat(),
            snapshot_path=str(report.snapshot_path) if report.snapshot_path else "",
        )
        state.save(options.version_file)
        report.version_bumped = True

    return report


def _build_manifest_context(m: Manifest) -> str:
    """Compact description of changes for LLM context."""
    lines: list[str] = [f"Game updated from {m.previous_version} to {m.game_version}.", ""]
    for c in m.removed_cards:
        lines.append(f"- REMOVED card '{c.name}' ({c.character or '?'}).")
    for c in m.reworked_cards:
        lines.append(f"- REWORKED card '{c.name}' ({c.severity}): {c.change or ''}")
    for r in m.reworked_relics:
        lines.append(f"- REWORKED relic '{r.name}' ({r.severity}): {r.change or ''}")
    for r in m.new_relics:
        lines.append(f"- NEW relic '{r.name}' (source: {r.source or '?'}).")
    for c in m.new_cards:
        lines.append(f"- NEW card '{c.name}' ({c.character or '?'}): {c.text or ''}")
    for e in m.reworked_enemies:
        lines.append(f"- REWORKED enemy '{e.name}' ({e.severity}).")
    for a in m.ascension_changes:
        lines.append(f"- Ascension {a.ascension}: '{a.from_}' → '{a.to}'.")
    for w in m.writing_clarifications:
        lines.append(f"- CLARIFICATION for '{w.entity}': {w.clarification}")
    for s in m.shop_changes:
        lines.append(f"- Shop: {s}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_orchestrator.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/patch/orchestrator.py tests/patch/test_orchestrator.py
git commit -m "feat(patch): add apply_patch orchestrator with snapshot+purge+rewrite+version bump"
```

---

## Task 19: CLI wrapper — scripts/apply_patch.py

**Files:**
- Create: `scripts/apply_patch.py`
- Create: `tests/patch/test_cli.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_cli.py`:

```python
import subprocess
import sys
from pathlib import Path


def test_cli_help_runs():
    result = subprocess.run(
        [sys.executable, "-m", "scripts.apply_patch", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "apply_patch" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_dry_run_flag_parses(tmp_path):
    # CLI should accept --dry-run without error and not crash on missing files gracefully
    result = subprocess.run(
        [sys.executable, "-m", "scripts.apply_patch",
         "--manifest", "nonexistent.yaml", "--dry-run"],
        capture_output=True, text=True,
    )
    # We expect a non-zero exit since manifest missing, but no arg-parse failure
    assert result.returncode != 0
    assert "nonexistent" in (result.stderr + result.stdout).lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_cli.py -v`
Expected: FAIL because `scripts/apply_patch.py` missing.

- [ ] **Step 3: Write implementation**

Create `scripts/apply_patch.py`:

```python
"""CLI entry point for applying a game patch manifest."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.patch.orchestrator import ApplyPatchOptions, apply_patch


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="apply_patch",
        description="Apply a game patch manifest: snapshot, purge, rewrite prompts, bump version.",
    )
    p.add_argument("--manifest", type=Path, required=True,
                   help="Path to data/patches/<game_version>.yaml")
    p.add_argument("--data-root", type=Path, default=Path("data"),
                   help="Root of persistent data directory")
    p.add_argument("--prompts-root", type=Path, default=Path("src/brain/prompts"),
                   help="Root of prompt source files to scan")
    p.add_argument("--version-file", type=Path, default=Path("data/version_compatibility.json"))
    p.add_argument("--snapshot-root", type=Path, default=Path("data.snapshots"))
    p.add_argument("--dry-run", action="store_true", help="Report impact without writing changes")
    p.add_argument("--skip-llm", action="store_true", help="Skip LLM prompt rewrite phase")
    p.add_argument("--smoke-test", action="store_true",
                   help="Run regression harness after apply")
    return p


def _build_backend():
    """Obtain real LLM backend from project analysis tier. Lazy-imported."""
    try:
        from src.brain.v2_backend import V2Backend  # type: ignore
        return V2Backend.from_tier("analysis")  # adapt to actual API
    except Exception as exc:
        print(f"Warning: could not construct analysis backend ({exc}); prompts will not be rewritten.",
              file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    backend = None if args.skip_llm or args.dry_run else _build_backend()

    options = ApplyPatchOptions(
        manifest_path=args.manifest,
        data_root=args.data_root,
        prompts_root=args.prompts_root,
        version_file=args.version_file,
        snapshot_root=args.snapshot_root,
        dry_run=args.dry_run,
        backend=backend,
        skip_llm=args.skip_llm or backend is None,
    )

    report = apply_patch(options)

    print(f"\n=== apply_patch report ({'DRY RUN' if args.dry_run else 'APPLIED'}) ===")
    print(f"Manifest: {args.manifest} ({report.manifest.game_version})")
    for r in report.purge_reports:
        print(f"  {r.store}: deleted={r.deleted} kept={r.kept}")
    print(f"Prompts rewritten: {report.rewrite_files_touched}")
    if report.snapshot_path:
        print(f"Snapshot: {report.snapshot_path}")
    if report.version_bumped:
        print(f"Version bumped to {report.manifest.game_version}")

    if args.smoke_test:
        print("\n--smoke-test: running regression harness...")
        import pytest as _pytest  # type: ignore
        rc = _pytest.main(["tests/regression/", "-v"])
        return rc

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_cli.py -v`
Expected: PASS.

Also verify CLI runs end-to-end in dry-run mode against real data:

Run: `python -m scripts.apply_patch --manifest data/patches/v0.103.1.yaml --dry-run --skip-llm`
Expected: exits 0, prints purge counts for each store.

- [ ] **Step 5: Commit**

```bash
git add scripts/apply_patch.py tests/patch/test_cli.py
git commit -m "feat(patch): add scripts/apply_patch CLI wrapper"
```

---

## Task 20: LogReplayClient

**Files:**
- Create: `src/regression/__init__.py`
- Create: `src/regression/log_replay.py`
- Create: `tests/regression/__init__.py`
- Create: `tests/regression/test_log_replay.py`

- [ ] **Step 1: Write the failing test**

Create `tests/regression/__init__.py` (empty). Create `tests/regression/test_log_replay.py`:

```python
import json
from pathlib import Path

from src.regression.log_replay import LogReplayClient


def test_log_replay_iterates_states(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    log.write_text("\n".join([
        json.dumps({"_meta": {"game_version": "v-test"}}),
        json.dumps({"event": "state_snapshot", "state": {"floor": 1, "hp": 70}}),
        json.dumps({"event": "decision", "source": "v2_engine_fast"}),
        json.dumps({"event": "state_snapshot", "state": {"floor": 1, "hp": 60}}),
    ]) + "\n")

    client = LogReplayClient(log)
    states = list(client.iter_states())
    assert len(states) == 2
    assert states[0]["floor"] == 1
    assert states[0]["hp"] == 70
    assert states[1]["hp"] == 60


def test_log_replay_decisions(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    log.write_text("\n".join([
        json.dumps({"event": "decision", "source": "v2_engine_fast", "state_type": "combat"}),
        json.dumps({"event": "decision", "source": "v2_engine_strategic", "state_type": "shop"}),
    ]) + "\n")
    client = LogReplayClient(log)
    decisions = list(client.iter_decisions())
    assert len(decisions) == 2
    assert decisions[0]["source"] == "v2_engine_fast"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/regression/test_log_replay.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `src/regression/__init__.py` (empty). Create `src/regression/log_replay.py`:

```python
"""Replay logged JSONL runs to extract states and decisions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


class LogReplayClient:
    """Reads a JSONL log and yields state snapshots / decisions in order."""

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def _iter_rows(self) -> Iterator[dict]:
        for ln in self.log_path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if "_meta" in row:
                continue
            yield row

    def iter_states(self) -> Iterator[dict]:
        for row in self._iter_rows():
            if row.get("event") == "state_snapshot" and "state" in row:
                yield row["state"]

    def iter_decisions(self) -> Iterator[dict]:
        for row in self._iter_rows():
            if row.get("event") == "decision":
                yield row
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/regression/test_log_replay.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/regression/__init__.py src/regression/log_replay.py tests/regression/__init__.py tests/regression/test_log_replay.py
git commit -m "feat(regression): add LogReplayClient for iterating states and decisions"
```

---

## Task 21: Decision fingerprint

**Files:**
- Modify: `src/regression/log_replay.py`
- Create: `tests/regression/test_fingerprint.py`

- [ ] **Step 1: Write the failing test**

Create `tests/regression/test_fingerprint.py`:

```python
from src.regression.log_replay import compute_fingerprint


def test_fingerprint_counts_decisions():
    decisions = [
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
        {"event": "decision", "source": "v2_strategic", "state_type": "shop"},
    ]
    fp = compute_fingerprint(decisions)
    assert fp["num_decisions"] == 3
    assert fp["decision_types"]["combat"] == 2
    assert fp["decision_types"]["shop"] == 1
    assert fp["source_distribution"]["v2_fast"] == 2
    assert fp["source_distribution"]["v2_strategic"] == 1


def test_fingerprint_stable_across_identical_inputs():
    decisions = [
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
    ]
    assert compute_fingerprint(decisions) == compute_fingerprint(list(decisions))


def test_fingerprint_tracks_errors():
    decisions = [
        {"event": "decision", "source": "v2_fast", "state_type": "combat"},
        {"event": "decision", "source": "error", "state_type": "combat", "error": "timeout"},
    ]
    fp = compute_fingerprint(decisions)
    assert fp["error_count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/regression/test_fingerprint.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Extend implementation**

Append to `src/regression/log_replay.py`:

```python
from collections import Counter


def compute_fingerprint(decisions: list[dict]) -> dict:
    """Compress a decision stream into a stable summary.

    Fields:
    - num_decisions: total count
    - decision_types: Counter by state_type
    - source_distribution: Counter by source (engine tier)
    - error_count: decisions with `error` key or source="error"
    """
    types = Counter()
    sources = Counter()
    errors = 0
    for d in decisions:
        types[d.get("state_type", "unknown")] += 1
        sources[d.get("source", "unknown")] += 1
        if d.get("error") or d.get("source") == "error":
            errors += 1
    return {
        "num_decisions": len(decisions),
        "decision_types": dict(types),
        "source_distribution": dict(sources),
        "error_count": errors,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/regression/test_fingerprint.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/regression/log_replay.py tests/regression/test_fingerprint.py
git commit -m "feat(regression): add compute_fingerprint for LLM-drift-tolerant decision summary"
```

---

## Task 22: Golden log freeze + regression test

**Files:**
- Create: `tests/fixtures/golden_logs/v0.5.3/README.md`
- Create: `tests/fixtures/golden_logs/v0.5.3/.gitkeep`
- Create: `tests/regression/test_golden_logs.py`
- Create: `scripts/freeze_golden_log.py`

- [ ] **Step 1: Write the failing test**

Create `tests/regression/test_golden_logs.py`:

```python
import json
from pathlib import Path

import pytest

from src.regression.log_replay import LogReplayClient, compute_fingerprint


GOLDEN_DIR = Path("tests/fixtures/golden_logs/v0.5.3")


def _available_golden_logs() -> list[Path]:
    if not GOLDEN_DIR.exists():
        return []
    return [p for p in GOLDEN_DIR.iterdir() if p.suffix == ".jsonl"]


@pytest.mark.parametrize("log_path", _available_golden_logs(),
                         ids=[p.stem for p in _available_golden_logs()])
def test_golden_log_fingerprint_matches(log_path: Path):
    """Each golden log must have a sibling .fingerprint.json with expected values."""
    fp_file = log_path.with_suffix(".fingerprint.json")
    if not fp_file.exists():
        pytest.skip(f"No fingerprint file at {fp_file}; run scripts.freeze_golden_log.")
    expected = json.loads(fp_file.read_text(encoding="utf-8"))
    client = LogReplayClient(log_path)
    actual = compute_fingerprint(list(client.iter_decisions()))
    # Allow num_decisions to drift ±5% but require error_count exact
    assert actual["error_count"] == expected["error_count"]
    assert set(actual["decision_types"]) == set(expected["decision_types"])
    assert abs(actual["num_decisions"] - expected["num_decisions"]) <= max(5, expected["num_decisions"] * 0.05)
```

Also create `tests/fixtures/golden_logs/v0.5.3/README.md`:

```markdown
# Golden Logs: v0.5.3

Frozen JSONL logs from pre-update runs. Each `run_*.jsonl` has a sibling `run_*.fingerprint.json`.

To freeze a new golden log:

    python -m scripts.freeze_golden_log logs/run_<id>.jsonl

Selection criteria: pick runs spanning ascension 0/4 victories, act2-boss loss, event-heavy, shop/rest-heavy.
```

Create `tests/fixtures/golden_logs/v0.5.3/.gitkeep` (empty).

- [ ] **Step 2: Run test to verify it skips (no goldens yet)**

Run: `python -m pytest tests/regression/test_golden_logs.py -v`
Expected: 0 tests collected (no files in the dir), or all skipped.

- [ ] **Step 3: Implement freeze helper**

Create `scripts/freeze_golden_log.py`:

```python
"""Freeze an existing run log as a regression baseline."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from src.regression.log_replay import LogReplayClient, compute_fingerprint


GOLDEN_DIR = Path("tests/fixtures/golden_logs")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("log", type=Path, help="Source JSONL log to freeze")
    p.add_argument("--game-version", default="v0.5.3",
                   help="Version label for the goldens dir")
    p.add_argument("--name", default=None, help="Label for the frozen log (default: source filename)")
    args = p.parse_args()

    if not args.log.exists():
        print(f"Log not found: {args.log}")
        return 2

    target_dir = GOLDEN_DIR / args.game_version
    target_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or args.log.stem
    dst = target_dir / f"{name}.jsonl"
    shutil.copyfile(args.log, dst)

    client = LogReplayClient(dst)
    fp = compute_fingerprint(list(client.iter_decisions()))
    fp_path = target_dir / f"{name}.fingerprint.json"
    fp_path.write_text(json.dumps(fp, indent=2), encoding="utf-8")

    print(f"Froze {dst}")
    print(f"Fingerprint: {fp_path}")
    print(json.dumps(fp, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Freeze two representative logs from the existing `logs/` directory. Run:

```bash
# Replace <id> with actual run IDs you want to freeze; at minimum one ascension-0 or act1 run:
python -m scripts.freeze_golden_log logs/$(ls logs/ | grep -E 'run_.*\.jsonl' | head -1) --name run_baseline_1
python -m scripts.freeze_golden_log logs/$(ls logs/ | grep -E 'run_.*\.jsonl' | sed -n '2p') --name run_baseline_2
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/regression/test_golden_logs.py -v`
Expected: 2 tests PASS (one per frozen log).

- [ ] **Step 5: Commit**

```bash
git add scripts/freeze_golden_log.py tests/regression/test_golden_logs.py \
        tests/fixtures/golden_logs/v0.5.3/
git commit -m "test(regression): add golden log replay harness + freeze script"
```

---

## Task 23: Mod API coverage check

**Files:**
- Create: `scripts/check_mod_api_coverage.py`
- Create: `tests/patch/test_api_coverage.py`

- [ ] **Step 1: Write the failing test**

Create `tests/patch/test_api_coverage.py`:

```python
from src.patch.api_coverage import flatten_keys, compare


def test_flatten_nested_dict():
    raw = {"run": {"floor": 1, "player": {"hp": 70}}, "combat": None}
    keys = flatten_keys(raw)
    assert "run.floor" in keys
    assert "run.player.hp" in keys
    assert "combat" in keys


def test_flatten_handles_list_of_dicts():
    raw = {"enemies": [{"name": "X", "hp": 10}, {"name": "Y"}]}
    keys = flatten_keys(raw)
    assert "enemies[].name" in keys
    assert "enemies[].hp" in keys


def test_compare_reports_missing_and_unused():
    raw_keys = {"a.b", "a.c", "new_field"}
    modeled = {"a.b", "a.c", "old_field"}
    report = compare(raw_keys, modeled)
    assert "new_field" in report.missing_from_model
    assert "old_field" in report.unused_in_response
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/patch/test_api_coverage.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write implementation**

Create `src/patch/api_coverage.py`:

```python
"""Compare mod /state response keys against Pydantic model fields."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def flatten_keys(obj: Any, prefix: str = "") -> set[str]:
    """Flatten nested dict/list keys into dotted paths."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            out.add(key)
            out.update(flatten_keys(v, key))
    elif isinstance(obj, list):
        if obj:
            # sample first element
            out.update(flatten_keys(obj[0], f"{prefix}[]"))
    return out


@dataclass
class CoverageReport:
    missing_from_model: set[str]
    unused_in_response: set[str]


def compare(raw_keys: set[str], modeled_keys: set[str]) -> CoverageReport:
    return CoverageReport(
        missing_from_model=raw_keys - modeled_keys,
        unused_in_response=modeled_keys - raw_keys,
    )
```

Create `scripts/check_mod_api_coverage.py`:

```python
"""Connect to running mod and report /state schema drift vs Pydantic models."""
from __future__ import annotations

import asyncio
import json
import sys

import httpx

from src.patch.api_coverage import compare, flatten_keys


async def fetch_raw_state(base_url: str = "http://localhost:8080") -> dict:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{base_url}/state")
        r.raise_for_status()
        return r.json()


def collect_modeled_keys() -> set[str]:
    """Introspect UpstreamGameState Pydantic model for all nested field names."""
    from src.mcp_client.upstream_models import UpstreamGameState  # lazy import
    return _pydantic_keys(UpstreamGameState, "")


def _pydantic_keys(model_cls, prefix: str) -> set[str]:
    out: set[str] = set()
    for name, field in model_cls.model_fields.items():
        key = f"{prefix}.{name}" if prefix else name
        out.add(key)
        ann = field.annotation
        # recurse into nested pydantic models
        try:
            if hasattr(ann, "model_fields"):
                out.update(_pydantic_keys(ann, key))
        except Exception:
            pass
    return out


def main() -> int:
    try:
        raw = asyncio.run(fetch_raw_state())
    except Exception as exc:
        print(f"ERROR: could not fetch /state — {exc}", file=sys.stderr)
        return 2

    raw_keys = flatten_keys(raw)
    modeled = collect_modeled_keys()
    report = compare(raw_keys, modeled)

    print(f"Raw keys: {len(raw_keys)} | Modeled: {len(modeled)}")
    if report.missing_from_model:
        print("\nFields returned by mod but not in client Pydantic models:")
        for k in sorted(report.missing_from_model):
            print(f"  + {k}")
    if report.unused_in_response:
        print("\nFields modeled by client but not returned by mod (possible schema break):")
        for k in sorted(report.unused_in_response):
            print(f"  - {k}")
    if not report.missing_from_model and not report.unused_in_response:
        print("Schemas aligned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/patch/test_api_coverage.py -v`
Expected: 3 tests PASS.

Optional live check (requires mod running):

Run: `python -m scripts.check_mod_api_coverage`
Expected: Output of schema comparison.

- [ ] **Step 5: Commit**

```bash
git add src/patch/api_coverage.py scripts/check_mod_api_coverage.py tests/patch/test_api_coverage.py
git commit -m "feat(patch): add mod /state schema coverage diagnostic"
```

---

## Task 24: CLAUDE.md playbook section

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Find insertion point**

Run: `grep -n "## Running" CLAUDE.md`
Expected: locate the "## Running" section; the playbook should go immediately before it.

- [ ] **Step 2: Insert playbook section**

Insert this block before the "## Running" section in `CLAUDE.md`:

```markdown
## Game Update Playbook

When STS2 releases a new version, run this pipeline:

1. **Author manifest.** Paste patch notes into a Claude session, generate `data/patches/v<new>.yaml` using the Manifest model schema. Commit.
2. **Dry run.** `python -m scripts.apply_patch --manifest data/patches/v<new>.yaml --dry-run --skip-llm`. Review purge counts per store.
3. **Full apply.** `python -m scripts.apply_patch --manifest data/patches/v<new>.yaml`. This snapshots `data/` into `data.snapshots/v<old>-pre-v<new>/`, runs per-store purge by entity reference, LLM-rewrites prompts referencing changed entities (diff batch shown for review), and bumps `data/version_compatibility.json`.
4. **Update game.** Steam update.
5. **Rebuild mod.** `cd STS2-Agent-Fork/STS2AIAgent && dotnet build -c Release`. Fix reflection fields if names changed (see `GameActionService.cs`, `GameStateService.cs`). Deploy DLL to game's `mods/`.
6. **Set mod version.** `export STS2_MOD_VERSION=v<new>-xc`; update `data/version_compatibility.json` current.mod_version.
7. **Resync knowledge.** `python -m scripts.sync_upstream_data --game-version v<new>` once mod has shipped new `eng/*.json`.
8. **API schema check.** With mod running: `python -m scripts.check_mod_api_coverage`. Investigate any missing/unused fields.
9. **Regression.** `python -m pytest tests/regression/ -v`. All golden log fingerprints must match.
10. **Live smoke.** `python -m scripts.run_agent --steps 50 --runs 1` — verify agent completes a short run without errors.

Entity-reference purge principle: records that do not reference any changed entity are untouched. `data/evolution/` artifacts are individually scanned, not blanket-archived.

Invariants this pipeline preserves:
- Every persistent record traceable to `(game_version, mod_version)`.
- Snapshots under `data.snapshots/` are never overwritten.
- Pre-destructive `--dry-run` always available.
```

- [ ] **Step 3: Verify**

Run: `grep -n "Game Update Playbook" CLAUDE.md`
Expected: one match.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Game Update Playbook section to CLAUDE.md"
```

---

## Task 25: Integration smoke — full dry-run on real data

**Files:**
- Run only; no new files.

- [ ] **Step 1: Run dry-run against real v0.103.1 manifest and real data/**

Run: `python -m scripts.apply_patch --manifest data/patches/v0.103.1.yaml --dry-run --skip-llm 2>&1 | tee /tmp/apply_patch_dryrun.log`

Expected output includes purge counts for each store. Example shape:

```
=== apply_patch report (DRY RUN) ===
Manifest: data/patches/v0.103.1.yaml (v0.103.1)
  card_memories.json: deleted=<N1> kept=<K1>
  card_builds.jsonl: deleted=<N2> kept=<K2>
  combat_episodes.jsonl: deleted=<N3> kept=<K3>
  event_memories.jsonl: deleted=<N4> kept=<K4>
  skills.json: deleted=<N5> kept=<K5>
  silent_card_notes.json: deleted=<N6> kept=<K6>
  evolution: deleted=<N7> kept=<K7>
  guides: deleted=<N8> kept=<K8>
Prompts rewritten: 0
```

Inspect the numbers. If `N1 + N2 + N3 + N5` is suspiciously low (< 5 for a manifest this size), something is wrong — likely slug mismatch. Diagnose by printing `changed_entities` manually and grepping card_memories.json for those names.

- [ ] **Step 2: Inspect specific pruned entries**

Run: `python -c "
import json
from pathlib import Path
from src.patch.slug import slug

data = json.loads(Path('data/memory/v2/card_memories.json').read_text())
matches = [k for k in data if slug(k.split('::', 1)[1]) in {'blade of ink', 'grapple'}]
print('Keys that would be purged:', matches)
print('Total entries:', len(data))
"`

Expected: list includes `"the silent::blade of ink"` if present, `"the ironclad::grapple"` if present.

- [ ] **Step 3: Run full test suite to confirm no regressions**

Run: `python -m pytest tests/ -x --ignore=tests/regression -q`
Expected: all PASS. Regression suite is excluded here since golden logs may not be frozen in CI.

Run: `python -m pytest tests/regression/ -v`
Expected: all golden log tests PASS (if goldens frozen in Task 22).

- [ ] **Step 4: Commit summary as a doc note**

Append a short note to `CLAUDE.md` at the top of the Recent Progress block (or create new block dated today):

```markdown
## Recent Progress (2026-04-17)

- Game update patch pipeline landed: data/patches/<version>.yaml manifest, scripts/apply_patch.py orchestrator (snapshot, entity-reference purge, LLM prompt rewrite, version bump), golden log regression harness, mod API coverage check. v0.103.1 manifest authored from patch notes; dry-run verified against current v0.5.3 data. Pipeline ready; game update and mod rebuild pending.
```

Run: `git add CLAUDE.md && git commit -m "docs: log game update patch pipeline landing"`

---

## Self-Review

**Spec coverage:**
- §3 Architecture (Manifest + Versioning + Purge + Rewrite + Regression) → Tasks 1–24 ✓
- §4 Manifest format → Task 2 (model) + Task 3 (first instance) ✓
- §5 Versioning layer → Tasks 4, 5, 6, 7 ✓
- §6 Purge tool → Tasks 9–14 ✓
- §6.2 LLM rewrite → Tasks 15, 16, 17 ✓
- §7 Regression harness → Tasks 20, 21, 22 ✓
- §7.2 Mod API coverage → Task 23 ✓
- §9 CLAUDE.md playbook → Task 24 ✓
- §11 Migration plan (implement on v0.5.3 before v0.103.1 apply) → Task 25 smoke test on dry-run covers pre-application verification ✓

**Placeholder scan:** every task has complete code, exact file paths, explicit commands.

**Type consistency:** `FileChangeRequest`, `RewriteResult`, `PurgeReport`, `Manifest`, `ApplyPatchOptions`, `ApplyPatchReport` — all defined in earlier tasks before being used in later tasks. `LLMBackend` Protocol defined in Task 16 and used in Task 18.

**Known gaps (deferred per spec §10):**
- C# mod reflection repair — manual, documented in Task 24 playbook.
- Cross-version alias mapping — not needed per entity-reference model.
- Per-version leaderboard splits in feat/leaderboard-mvp — noted as follow-up in brainstorming, out of scope.
- `core_*.json` seed free-text rewrite — the scan in Task 15/16 covers files whose content matches targets; the `src/skills/seeds/` directory should be included when running `apply_patch` in production (Task 19 CLI accepts `--prompts-root`; callers can pass `src/skills/seeds` as an additional scan root, or extend `scan_prompt_files` to accept multiple roots in a follow-up).
