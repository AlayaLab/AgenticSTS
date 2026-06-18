# Ascension Progression & Run Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build experiment-grade per-run analytics with append-only history, per-model ascension progression, and CLI-driven ascension control.

**Architecture:** Two-layer data — `data/runs/history.jsonl` (append-only source of truth, one line per run) and `data/runs/ascension_stats.json` (derived aggregate cache keyed by `(profile_hash, character, ascension)`, rebuildable). Model attribution via `config.build_model_profile()` snapshot + 8-char hash. Ascension manipulation by calling `increase_ascension`/`decrease_ascension` actions one step at a time on the character_select screen before embarking.

**Tech Stack:** Python 3.11+, dataclasses (frozen), JSON/JSONL persistence, httpx async client, argparse CLI

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/config.py` | Modify | Add `build_model_profile()`, `model_profile_hash()`, `model_profile_label()` |
| `src/runs/__init__.py` | Create | Package marker |
| `src/runs/history.py` | Create | `RunRecord` frozen dataclass + `RunHistoryStore` append-only JSONL |
| `src/runs/ascension_stats.py` | Create | `AscensionRecord` frozen dataclass + `AscensionStats` aggregate cache |
| `src/mcp_client/actions.py` | Modify | Add `increase_ascension()`, `decrease_ascension()` |
| `src/mcp_client/upstream_models.py` | Modify | Add `ascension: int = 0` to `RawRunPayload` |
| `src/state/game_state.py` | Modify | Add `ascension` property |
| `src/state/run_state.py` | Modify | Replace `ascension: int = 0` with `target_ascension` / `actual_ascension` |
| `src/mcp_client/client.py` | Modify | Add `ascension` param to `start_new_run()` |
| `src/agent/loop.py` | Modify | Populate `actual_ascension` from game state |
| `scripts/run_agent.py` | Modify | Add `--ascension` CLI arg, recording, auto-progression |
| `tests/test_run_history.py` | Create | Tests for `RunRecord` + `RunHistoryStore` |
| `tests/test_ascension_stats.py` | Create | Tests for `AscensionRecord` + `AscensionStats` |

---

### Task 1: Config — Model Profile Helpers

**Files:**
- Modify: `src/config.py` (append after line ~297, before helper functions)

- [ ] **Step 1: Write the test**

Create `tests/test_model_profile.py`:

```python
"""Tests for config.build_model_profile / model_profile_hash."""
import src.config as config


def test_build_model_profile_returns_dict_with_required_keys():
    profile = config.build_model_profile()
    assert isinstance(profile, dict)
    for key in (
        "fast_model", "strategic_model", "analysis_model",
        "fast_provider", "strategic_provider",
        "memory_enabled", "skills_enabled", "evolution_enabled",
    ):
        assert key in profile, f"missing key: {key}"


def test_model_profile_hash_is_stable():
    p1 = config.build_model_profile()
    p2 = config.build_model_profile()
    h1 = config.model_profile_hash(p1)
    h2 = config.model_profile_hash(p2)
    assert h1 == h2
    assert len(h1) == 8
    assert all(c in "0123456789abcdef" for c in h1)


def test_model_profile_hash_changes_with_different_config():
    p1 = config.build_model_profile()
    p2 = {**p1, "strategic_model": "totally-different-model"}
    assert config.model_profile_hash(p1) != config.model_profile_hash(p2)


def test_model_profile_label_contains_models():
    profile = config.build_model_profile()
    label = config.model_profile_label(profile)
    assert profile["strategic_model"] in label
    assert profile["fast_model"] in label
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd AgenticSTS && python -m pytest tests/test_model_profile.py -v`
Expected: FAIL — `AttributeError: module 'src.config' has no attribute 'build_model_profile'`

- [ ] **Step 3: Implement in config.py**

Add after the `ACTION_DELAY` constant (around line 297), before the helper functions section:

```python
# ── Model profile (run attribution) ───────────────────────────────
def build_model_profile() -> dict:
    """Snapshot of current model routing config for run attribution."""
    return {
        "fast_model": LLM_FAST_MODEL,
        "strategic_model": LLM_STRATEGIC_MODEL,
        "analysis_model": LLM_ANALYSIS_MODEL,
        "fast_provider": LLM_FAST_PROVIDER,
        "strategic_provider": LLM_STRATEGIC_PROVIDER,
        "memory_enabled": MEMORY_ENABLED,
        "skills_enabled": SKILLS_ENABLED,
        "evolution_enabled": EVOLUTION_ENABLED,
    }


def model_profile_hash(profile: dict) -> str:
    """Stable 8-char hex hash for grouping runs by config."""
    import hashlib
    blob = json.dumps(profile, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def model_profile_label(profile: dict) -> str:
    """Human-readable label: 'gemini-3.1-pro / flash-lite'."""
    return f"{profile.get('strategic_model', '?')} / {profile.get('fast_model', '?')}"
```

Also add `import json` at the top of `config.py` if not already present (check first — it may already be imported).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd AgenticSTS && python -m pytest tests/test_model_profile.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_model_profile.py
git commit -m "feat: add build_model_profile/hash/label helpers to config"
```

---

### Task 2: RunRecord Dataclass + RunHistoryStore

**Files:**
- Create: `src/runs/__init__.py`
- Create: `src/runs/history.py`
- Create: `tests/test_run_history.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_run_history.py`:

```python
"""Tests for RunRecord and RunHistoryStore."""
import time
from pathlib import Path

from src.runs.history import RunRecord, RunHistoryStore


def _make_record(**overrides) -> RunRecord:
    defaults = dict(
        run_id="test_001",
        started_at=time.time() - 300,
        ended_at=time.time(),
        profile_hash="a1b2c3d4",
        profile_label="gemini-pro / flash-lite",
        model_profile={"strategic_model": "gemini-pro", "fast_model": "flash-lite"},
        character="the silent",
        target_ascension=3,
        actual_ascension=3,
        outcome="victory",
        victory=True,
        final_floor=51,
        final_hp=45,
        final_max_hp=72,
        final_gold=320,
        fitness=185.0,
        score=185,
        duration_seconds=300.0,
        steps=450,
        llm_calls=120,
        total_actions=200,
        combats_won=15,
        combats_total=15,
        completion_reason="completed",
        end_reason="victory",
        use_llm=True,
        memory_enabled=True,
        skills_enabled=True,
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_run_record_is_frozen():
    rec = _make_record()
    try:
        rec.victory = False
        assert False, "should raise"
    except AttributeError:
        pass


def test_run_record_roundtrip():
    rec = _make_record()
    d = rec.to_dict()
    restored = RunRecord.from_dict(d)
    assert restored.run_id == rec.run_id
    assert restored.victory == rec.victory
    assert restored.profile_hash == rec.profile_hash
    assert restored.actual_ascension == rec.actual_ascension
    assert restored.model_profile == rec.model_profile


def test_history_store_append_and_load(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    r1 = _make_record(run_id="run_001", victory=True)
    r2 = _make_record(run_id="run_002", victory=False, outcome="defeat")
    store.append(r1)
    store.append(r2)
    assert store.count == 2

    reloaded = RunHistoryStore.load(path)
    assert reloaded.count == 2
    all_records = reloaded.load_all()
    assert all_records[0].run_id == "run_001"
    assert all_records[1].run_id == "run_002"


def test_history_store_query_filters(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    store.append(_make_record(run_id="r1", character="the silent", profile_hash="aaa"))
    store.append(_make_record(run_id="r2", character="the ironclad", profile_hash="aaa"))
    store.append(_make_record(run_id="r3", character="the silent", profile_hash="bbb"))

    silent_only = store.query(character="the silent")
    assert len(silent_only) == 2

    aaa_only = store.query(profile_hash="aaa")
    assert len(aaa_only) == 2

    combined = store.query(character="the silent", profile_hash="aaa")
    assert len(combined) == 1
    assert combined[0].run_id == "r1"


def test_history_store_empty_path(tmp_path: Path):
    path = tmp_path / "nonexistent.jsonl"
    store = RunHistoryStore.load(path)
    assert store.count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd AgenticSTS && python -m pytest tests/test_run_history.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.runs'`

- [ ] **Step 3: Create the package and implementation**

Create `src/runs/__init__.py` (empty file).

Create `src/runs/history.py`:

```python
"""Append-only per-run history store.

Primary data layer: one JSONL line per completed run at data/runs/history.jsonl.
This is the source of truth — aggregate caches are derived from it.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunRecord:
    """Immutable record of a single completed (or aborted) run."""

    # Identity
    run_id: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0

    # Model attribution
    profile_hash: str = ""
    profile_label: str = ""
    model_profile: dict = field(default_factory=dict)

    # Game context
    character: str = ""
    target_ascension: int | None = None
    actual_ascension: int | None = None

    # Outcome
    outcome: str = ""  # victory | defeat | agent_abort | mcp_error | interrupt | max_steps
    victory: bool = False
    final_floor: int = 0
    final_hp: int = 0
    final_max_hp: int = 0
    final_gold: int = 0
    fitness: float = 0.0
    score: int = 0

    # Run metadata
    duration_seconds: float = 0.0
    steps: int = 0
    llm_calls: int = 0
    total_actions: int = 0
    combats_won: int = 0
    combats_total: int = 0
    completion_reason: str = ""  # completed | aborted
    end_reason: str = ""  # victory, defeat, max_steps, interrupt, ...

    # Config flags
    use_llm: bool = True
    memory_enabled: bool = True
    skills_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "profile_hash": self.profile_hash,
            "profile_label": self.profile_label,
            "model_profile": self.model_profile,
            "character": self.character,
            "target_ascension": self.target_ascension,
            "actual_ascension": self.actual_ascension,
            "outcome": self.outcome,
            "victory": self.victory,
            "final_floor": self.final_floor,
            "final_hp": self.final_hp,
            "final_max_hp": self.final_max_hp,
            "final_gold": self.final_gold,
            "fitness": self.fitness,
            "score": self.score,
            "duration_seconds": self.duration_seconds,
            "steps": self.steps,
            "llm_calls": self.llm_calls,
            "total_actions": self.total_actions,
            "combats_won": self.combats_won,
            "combats_total": self.combats_total,
            "completion_reason": self.completion_reason,
            "end_reason": self.end_reason,
            "use_llm": self.use_llm,
            "memory_enabled": self.memory_enabled,
            "skills_enabled": self.skills_enabled,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RunRecord:
        return cls(
            run_id=d.get("run_id", ""),
            started_at=d.get("started_at", 0.0),
            ended_at=d.get("ended_at", 0.0),
            profile_hash=d.get("profile_hash", ""),
            profile_label=d.get("profile_label", ""),
            model_profile=d.get("model_profile", {}),
            character=d.get("character", ""),
            target_ascension=d.get("target_ascension"),
            actual_ascension=d.get("actual_ascension"),
            outcome=d.get("outcome", ""),
            victory=d.get("victory", False),
            final_floor=d.get("final_floor", 0),
            final_hp=d.get("final_hp", 0),
            final_max_hp=d.get("final_max_hp", 0),
            final_gold=d.get("final_gold", 0),
            fitness=d.get("fitness", 0.0),
            score=d.get("score", 0),
            duration_seconds=d.get("duration_seconds", 0.0),
            steps=d.get("steps", 0),
            llm_calls=d.get("llm_calls", 0),
            total_actions=d.get("total_actions", 0),
            combats_won=d.get("combats_won", 0),
            combats_total=d.get("combats_total", 0),
            completion_reason=d.get("completion_reason", ""),
            end_reason=d.get("end_reason", ""),
            use_llm=d.get("use_llm", True),
            memory_enabled=d.get("memory_enabled", True),
            skills_enabled=d.get("skills_enabled", True),
        )


class RunHistoryStore:
    """Append-only JSONL store for run records."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._records: list[RunRecord] = []

    @classmethod
    def load(cls, path: Path) -> RunHistoryStore:
        store = cls(path)
        if not path.exists():
            return store
        try:
            with open(path, encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        store._records.append(RunRecord.from_dict(d))
                    except (json.JSONDecodeError, KeyError, TypeError) as exc:
                        logger.warning("Skipping corrupt line %d in %s: %s", lineno, path, exc)
            logger.info("Loaded %d run records from %s", len(store._records), path)
        except Exception as exc:
            logger.warning("Failed to load run history from %s: %s", path, exc)
        return store

    def append(self, record: RunRecord) -> None:
        self._records.append(record)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record.to_dict()) + "\n")

    def load_all(self) -> list[RunRecord]:
        return list(self._records)

    def query(
        self,
        *,
        character: str | None = None,
        profile_hash: str | None = None,
        ascension: int | None = None,
    ) -> list[RunRecord]:
        results = self._records
        if character is not None:
            results = [r for r in results if r.character == character]
        if profile_hash is not None:
            results = [r for r in results if r.profile_hash == profile_hash]
        if ascension is not None:
            results = [r for r in results if r.actual_ascension == ascension]
        return results

    @property
    def count(self) -> int:
        return len(self._records)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd AgenticSTS && python -m pytest tests/test_run_history.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/runs/__init__.py src/runs/history.py tests/test_run_history.py
git commit -m "feat: add RunRecord and RunHistoryStore (append-only JSONL)"
```

---

### Task 3: AscensionRecord + AscensionStats Aggregate Cache

**Files:**
- Create: `src/runs/ascension_stats.py`
- Create: `tests/test_ascension_stats.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_ascension_stats.py`:

```python
"""Tests for AscensionRecord and AscensionStats."""
import time
from pathlib import Path

from src.runs.ascension_stats import AscensionRecord, AscensionStats
from src.runs.history import RunRecord


def _make_record(**overrides) -> RunRecord:
    defaults = dict(
        run_id="test_001",
        started_at=time.time() - 300,
        ended_at=time.time(),
        profile_hash="a1b2c3d4",
        profile_label="gemini-pro / flash-lite",
        model_profile={},
        character="the silent",
        target_ascension=0,
        actual_ascension=0,
        outcome="victory",
        victory=True,
        final_floor=51,
        final_hp=45,
        final_max_hp=72,
        final_gold=320,
        fitness=185.0,
        score=185,
        duration_seconds=300.0,
        steps=450,
        llm_calls=120,
        total_actions=200,
        combats_won=15,
        combats_total=15,
        completion_reason="completed",
        end_reason="victory",
        use_llm=True,
        memory_enabled=True,
        skills_enabled=True,
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_ascension_record_is_frozen():
    rec = AscensionRecord(profile_hash="abc", character="the silent", ascension=0)
    try:
        rec.wins = 5
        assert False, "should raise"
    except AttributeError:
        pass


def test_stats_record_and_query():
    stats = AscensionStats()
    r1 = _make_record(run_id="r1", actual_ascension=0, victory=True, final_floor=51)
    r2 = _make_record(run_id="r2", actual_ascension=0, victory=False, final_floor=30, outcome="defeat")
    stats.record_run(r1)
    stats.record_run(r2)

    rec = stats.get("a1b2c3d4", "the silent", 0)
    assert rec.wins == 1
    assert rec.losses == 1
    assert rec.aborts == 0
    assert rec.total_runs == 2
    assert rec.best_floor == 51


def test_stats_aborts_tracked_separately():
    stats = AscensionStats()
    r = _make_record(run_id="r1", outcome="agent_abort", victory=False, completion_reason="aborted")
    stats.record_run(r)

    rec = stats.get("a1b2c3d4", "the silent", 0)
    assert rec.losses == 0
    assert rec.aborts == 1
    assert rec.total_runs == 1


def test_highest_cleared_and_next():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=0, victory=True))
    stats.record_run(_make_record(run_id="r2", actual_ascension=1, victory=True))
    stats.record_run(_make_record(run_id="r3", actual_ascension=2, victory=False, outcome="defeat"))

    assert stats.highest_cleared("a1b2c3d4", "the silent") == 1
    assert stats.next_ascension("a1b2c3d4", "the silent", max_asc=20) == 2


def test_highest_cleared_no_wins():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=0, victory=False, outcome="defeat"))
    assert stats.highest_cleared("a1b2c3d4", "the silent") == -1
    assert stats.next_ascension("a1b2c3d4", "the silent") == 0


def test_next_ascension_capped():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=20, victory=True))
    assert stats.next_ascension("a1b2c3d4", "the silent", max_asc=20) == 20


def test_profile_isolation():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", profile_hash="aaa", actual_ascension=0, victory=True))
    stats.record_run(_make_record(run_id="r2", profile_hash="bbb", actual_ascension=0, victory=False, outcome="defeat"))

    assert stats.highest_cleared("aaa", "the silent") == 0
    assert stats.highest_cleared("bbb", "the silent") == -1


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "stats.json"
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=0, victory=True))
    stats.record_run(_make_record(run_id="r2", actual_ascension=1, victory=False, outcome="defeat"))
    stats.save(path)

    reloaded = AscensionStats.load(path)
    rec = reloaded.get("a1b2c3d4", "the silent", 0)
    assert rec.wins == 1
    assert rec.total_runs == 1


def test_rebuild_from_history():
    records = [
        _make_record(run_id="r1", actual_ascension=0, victory=True),
        _make_record(run_id="r2", actual_ascension=0, victory=False, outcome="defeat"),
        _make_record(run_id="r3", actual_ascension=1, victory=True),
    ]
    stats = AscensionStats.rebuild_from_history(records)
    a0 = stats.get("a1b2c3d4", "the silent", 0)
    assert a0.wins == 1
    assert a0.losses == 1
    a1 = stats.get("a1b2c3d4", "the silent", 1)
    assert a1.wins == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd AgenticSTS && python -m pytest tests/test_ascension_stats.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.runs.ascension_stats'`

- [ ] **Step 3: Implement ascension_stats.py**

Create `src/runs/ascension_stats.py`:

```python
"""Derived aggregate cache for ascension progression.

Keyed by (profile_hash, character, ascension). Rebuildable from RunHistoryStore.
Stored at data/runs/ascension_stats.json.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.runs.history import RunRecord

logger = logging.getLogger(__name__)

_ABORT_OUTCOMES = frozenset({"agent_abort", "mcp_error", "interrupt", "max_steps"})


@dataclass(frozen=True)
class AscensionRecord:
    """Aggregate stats for one (profile_hash, character, ascension) triple."""

    profile_hash: str = ""
    character: str = ""
    ascension: int = 0
    wins: int = 0
    losses: int = 0
    aborts: int = 0
    best_floor: int = 0
    avg_floor: float = 0.0
    total_runs: int = 0

    @property
    def win_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.wins / self.total_runs

    def _with_run(self, *, victory: bool, is_abort: bool, final_floor: int) -> AscensionRecord:
        new_wins = self.wins + (1 if victory else 0)
        new_losses = self.losses + (1 if not victory and not is_abort else 0)
        new_aborts = self.aborts + (1 if is_abort else 0)
        new_total = self.total_runs + 1
        new_best = max(self.best_floor, final_floor)
        new_avg = (self.avg_floor * self.total_runs + final_floor) / new_total
        return AscensionRecord(
            profile_hash=self.profile_hash,
            character=self.character,
            ascension=self.ascension,
            wins=new_wins,
            losses=new_losses,
            aborts=new_aborts,
            best_floor=new_best,
            avg_floor=round(new_avg, 1),
            total_runs=new_total,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_hash": self.profile_hash,
            "character": self.character,
            "ascension": self.ascension,
            "wins": self.wins,
            "losses": self.losses,
            "aborts": self.aborts,
            "best_floor": self.best_floor,
            "avg_floor": self.avg_floor,
            "total_runs": self.total_runs,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AscensionRecord:
        return cls(
            profile_hash=d.get("profile_hash", ""),
            character=d.get("character", ""),
            ascension=d.get("ascension", 0),
            wins=d.get("wins", 0),
            losses=d.get("losses", 0),
            aborts=d.get("aborts", 0),
            best_floor=d.get("best_floor", 0),
            avg_floor=d.get("avg_floor", 0.0),
            total_runs=d.get("total_runs", 0),
        )


_Key = tuple[str, str, int]  # (profile_hash, character, ascension)


class AscensionStats:
    """Aggregate cache keyed by (profile_hash, character, ascension)."""

    def __init__(self) -> None:
        self._records: dict[_Key, AscensionRecord] = {}

    @classmethod
    def load(cls, path: Path) -> AscensionStats:
        stats = cls()
        if not path.exists():
            return stats
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for entry in data.get("records", []):
                rec = AscensionRecord.from_dict(entry)
                stats._records[(rec.profile_hash, rec.character, rec.ascension)] = rec
            logger.info("Loaded %d ascension records from %s", len(stats._records), path)
        except Exception as exc:
            logger.warning("Failed to load ascension stats from %s: %s", path, exc)
        return stats

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "records": [
                r.to_dict()
                for r in sorted(
                    self._records.values(),
                    key=lambda r: (r.profile_hash, r.character, r.ascension),
                )
            ]
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def get(self, profile_hash: str, character: str, ascension: int) -> AscensionRecord:
        key: _Key = (profile_hash, character, ascension)
        return self._records.get(
            key,
            AscensionRecord(profile_hash=profile_hash, character=character, ascension=ascension),
        )

    def record_run(self, record: RunRecord) -> AscensionRecord:
        asc = record.actual_ascension if record.actual_ascension is not None else 0
        key: _Key = (record.profile_hash, record.character, asc)
        existing = self._records.get(
            key,
            AscensionRecord(profile_hash=record.profile_hash, character=record.character, ascension=asc),
        )
        is_abort = record.outcome in _ABORT_OUTCOMES
        updated = existing._with_run(
            victory=record.victory,
            is_abort=is_abort,
            final_floor=record.final_floor,
        )
        self._records[key] = updated
        return updated

    def highest_cleared(self, profile_hash: str, character: str) -> int:
        max_cleared = -1
        for (ph, ch, asc), rec in self._records.items():
            if ph == profile_hash and ch == character and rec.wins > 0:
                max_cleared = max(max_cleared, asc)
        return max_cleared

    def next_ascension(self, profile_hash: str, character: str, max_asc: int = 20) -> int:
        cleared = self.highest_cleared(profile_hash, character)
        return min(cleared + 1, max_asc)

    def stats_for(
        self,
        *,
        profile_hash: str | None = None,
        character: str | None = None,
    ) -> list[AscensionRecord]:
        results = list(self._records.values())
        if profile_hash is not None:
            results = [r for r in results if r.profile_hash == profile_hash]
        if character is not None:
            results = [r for r in results if r.character == character]
        return sorted(results, key=lambda r: (r.character, r.ascension))

    @classmethod
    def rebuild_from_history(cls, records: list[RunRecord]) -> AscensionStats:
        stats = cls()
        for rec in records:
            stats.record_run(rec)
        return stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd AgenticSTS && python -m pytest tests/test_ascension_stats.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add src/runs/ascension_stats.py tests/test_ascension_stats.py
git commit -m "feat: add AscensionStats aggregate cache with profile isolation"
```

---

### Task 4: Action Builders — increase/decrease Ascension

**Files:**
- Modify: `src/mcp_client/actions.py` (after `select_character` at line ~163)

- [ ] **Step 1: Write the test**

Append to an existing test file or create `tests/test_ascension_actions.py`:

```python
"""Tests for ascension action builders."""
from src.mcp_client import actions as act


def test_increase_ascension():
    result = act.increase_ascension()
    assert result == {"action": "increase_ascension"}


def test_decrease_ascension():
    result = act.decrease_ascension()
    assert result == {"action": "decrease_ascension"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd AgenticSTS && python -m pytest tests/test_ascension_actions.py -v`
Expected: FAIL — `AttributeError: module 'src.mcp_client.actions' has no attribute 'increase_ascension'`

- [ ] **Step 3: Add to actions.py**

Insert after `select_character` (around line 163), before `embark`:

```python
def increase_ascension() -> dict:
    """Increment ascension level by 1 on character select screen."""
    return {"action": "increase_ascension"}


def decrease_ascension() -> dict:
    """Decrement ascension level by 1 on character select screen."""
    return {"action": "decrease_ascension"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd AgenticSTS && python -m pytest tests/test_ascension_actions.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/mcp_client/actions.py tests/test_ascension_actions.py
git commit -m "feat: add increase/decrease_ascension action builders"
```

---

### Task 5: Upstream Model + GameState Property

**Files:**
- Modify: `src/mcp_client/upstream_models.py:209` (add field to `RawRunPayload`)
- Modify: `src/state/game_state.py:478` (add `ascension` property)

- [ ] **Step 1: Add `ascension` field to RawRunPayload**

In `src/mcp_client/upstream_models.py`, add after `floor: int = 0` (line 209):

```python
    ascension: int = 0
```

So the class becomes:
```python
class RawRunPayload(UpstreamModel):
    character_id: str = ""
    character_name: str = ""
    floor: int = 0
    ascension: int = 0          # v0.5.4+
    current_hp: int = 0
    ...
```

- [ ] **Step 2: Add `ascension` property to GameState**

In `src/state/game_state.py`, add after the `character_id` property (after line 478, before the `# ── Map convenience` comment):

```python
    @property
    def ascension(self) -> int:
        """Current ascension level (from run payload, fallback to character select)."""
        if self.raw.run is not None:
            return self.raw.run.ascension
        if self.raw.character_select is not None:
            return self.raw.character_select.ascension
        return 0
```

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `cd AgenticSTS && python -m pytest tests/ -x -q --timeout=30 2>&1 | head -30`
Expected: All existing tests still pass

- [ ] **Step 4: Commit**

```bash
git add src/mcp_client/upstream_models.py src/state/game_state.py
git commit -m "feat: expose ascension in RawRunPayload and GameState"
```

---

### Task 6: RunState — target_ascension / actual_ascension

**Files:**
- Modify: `src/state/run_state.py:59` (replace `ascension` field)

- [ ] **Step 1: Modify RunState**

In `src/state/run_state.py`, replace line 59 (`ascension: int = 0`) with:

```python
    target_ascension: int | None = None
    actual_ascension: int | None = None
```

Add a backward-compatible property after the `_highest_floor` field (around line 72):

```python
    @property
    def ascension(self) -> int:
        """Effective ascension: actual if known, else target, else 0."""
        if self.actual_ascension is not None:
            return self.actual_ascension
        if self.target_ascension is not None:
            return self.target_ascension
        return 0
```

- [ ] **Step 2: Run existing tests**

Run: `cd AgenticSTS && python -m pytest tests/ -x -q --timeout=30 2>&1 | head -30`
Expected: All pass. No existing code reads `run_state.ascension` as a writable field (it was never set).

- [ ] **Step 3: Commit**

```bash
git add src/state/run_state.py
git commit -m "refactor: split RunState.ascension into target/actual with None semantics"
```

---

### Task 7: Client — Ascension Manipulation in start_new_run

**Files:**
- Modify: `src/mcp_client/client.py` (the `start_new_run` method, lines 303-525)

- [ ] **Step 1: Add `ascension` parameter to `start_new_run` signature**

Change line 303-308 from:
```python
    async def start_new_run(
        self,
        character: str | None = None,
        max_attempts: int = 30,
        step_delay: float = 1.5,
        abandon_existing: bool = False,
    ) -> bool:
```
to:
```python
    async def start_new_run(
        self,
        character: str | None = None,
        ascension: int | None = None,
        max_attempts: int = 30,
        step_delay: float = 1.5,
        abandon_existing: bool = False,
    ) -> bool:
```

- [ ] **Step 2: Add saved-run conflict handling**

In the `continue_run` branch (around lines 351-374), add ascension-aware logic. When `ascension is not None` and a saved run exists, abandon it instead of continuing:

Find the block that handles `"continue_run" in avail` and add before the existing continue logic:

```python
            # If ascension is specified, don't silently continue a saved run
            # (its ascension may not match the target)
            if "continue_run" in avail and ascension is not None and not abandon_existing:
                logger.info(
                    "Saved run exists but --ascension=%d specified; abandoning saved run",
                    ascension,
                )
                abandon_existing = True
```

- [ ] **Step 3: Add ascension adjustment loop before embark**

Find the location where `embark()` is about to be called (both the branch where character is already selected and the standalone `"embark" in avail` branch). Insert this ascension adjustment block just BEFORE calling `embark()`:

```python
                # -- Ascension adjustment (before embark) --
                if ascension is not None:
                    char_select = raw_state.get("character_select", {})
                    current_asc = char_select.get("ascension", 0)
                    max_asc = char_select.get("max_ascension", 20)
                    target_asc = min(ascension, max_asc)
                    if current_asc != target_asc:
                        if target_asc > current_asc and char_select.get("can_increase_ascension", False):
                            logger.info("Adjusting ascension %d -> %d (incrementing)", current_asc, target_asc)
                            await self.post_action(act.increase_ascension())
                            await asyncio.sleep(0.3)
                            continue  # re-enter loop to check updated state
                        elif target_asc < current_asc and char_select.get("can_decrease_ascension", False):
                            logger.info("Adjusting ascension %d -> %d (decrementing)", current_asc, target_asc)
                            await self.post_action(act.decrease_ascension())
                            await asyncio.sleep(0.3)
                            continue  # re-enter loop to check updated state
                        else:
                            logger.warning(
                                "Cannot adjust ascension from %d to %d (can_inc=%s, can_dec=%s)",
                                current_asc, target_asc,
                                char_select.get("can_increase_ascension"),
                                char_select.get("can_decrease_ascension"),
                            )
```

Also ensure `import asyncio` and `from src.mcp_client import actions as act` are available at the top of client.py (verify — `act` may already be imported).

- [ ] **Step 4: Run existing tests**

Run: `cd AgenticSTS && python -m pytest tests/ -x -q --timeout=30 2>&1 | head -30`
Expected: All pass (the new `ascension` param defaults to `None`, so no callers break)

- [ ] **Step 5: Commit**

```bash
git add src/mcp_client/client.py
git commit -m "feat: add ascension manipulation to start_new_run"
```

---

### Task 8: Agent Loop — Populate actual_ascension

**Files:**
- Modify: `src/agent/loop.py` (after line 2256, the character detection block)

- [ ] **Step 1: Add actual_ascension population**

After the existing character detection block (lines 2251-2256):

```python
                    # Detect character + load guide
                    if not self._run_state.character:
                        char = gs.character
                        if char:
                            from src.memory.models_v2 import normalize_character
                            self._run_state.character = normalize_character(char)
```

Add immediately below:

```python
                    # Populate actual ascension from game state (once)
                    if self._run_state.actual_ascension is None and gs.ascension > 0:
                        self._run_state.actual_ascension = gs.ascension
```

- [ ] **Step 2: Run existing tests**

Run: `cd AgenticSTS && python -m pytest tests/ -x -q --timeout=30 2>&1 | head -30`
Expected: All pass

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat: populate RunState.actual_ascension from game state"
```

---

### Task 9: CLI Integration — --ascension + Recording

**Files:**
- Modify: `scripts/run_agent.py`

This is the integration task that wires everything together. Apply changes in order:

- [ ] **Step 1: Add --ascension argument to argparse (around line 222)**

After the `--no-skills` argument, add:

```python
    parser.add_argument(
        "--ascension", type=str, default=None,
        help='Ascension level: integer (0-20) or "auto" for auto-progression',
    )
```

- [ ] **Step 2: Add imports and initialization in main()**

At the top of the `main()` function (after `setup_logging`, around line 82), add:

```python
    from pathlib import Path
    from src.runs.history import RunRecord, RunHistoryStore
    from src.runs.ascension_stats import AscensionStats
    import src.config as config

    # -- Run analytics --
    runs_dir = Path(config.DATA_DIR) / "runs"
    history_store = RunHistoryStore.load(runs_dir / "history.jsonl")
    ascension_stats = AscensionStats.load(runs_dir / "ascension_stats.json")
    model_profile = config.build_model_profile()
    profile_hash = config.model_profile_hash(model_profile)
    profile_label = config.model_profile_label(model_profile)
    logger.info("Model profile: %s [%s]", profile_label, profile_hash)
```

- [ ] **Step 3: Parse ascension argument and resolve target**

After the initialization block, add:

```python
    # -- Ascension target resolution --
    ascension_mode = args.ascension if hasattr(args, "ascension") else None
    ascension_target: int | None = None
    ascension_auto = False

    if ascension_mode is not None:
        if ascension_mode.lower() == "auto":
            ascension_auto = True
        else:
            try:
                ascension_target = int(ascension_mode)
            except ValueError:
                logger.error("Invalid --ascension value: %s (use integer or 'auto')", ascension_mode)
                return
```

- [ ] **Step 4: Resolve auto-ascension before each run**

Before the `_ensure_run_started` call (around line 145), add:

```python
            # Resolve auto-ascension for this run
            effective_ascension = ascension_target
            if ascension_auto:
                from src.memory.models_v2 import normalize_character
                norm_char = normalize_character(character or "Silent")
                effective_ascension = ascension_stats.next_ascension(
                    profile_hash, norm_char, max_asc=20,
                )
                logger.info("Auto-ascension for %s: targeting A%d", norm_char, effective_ascension)
```

- [ ] **Step 5: Pass ascension to _ensure_run_started and client.start_new_run**

Update the `_ensure_run_started` function signature (line ~54) to accept and forward `ascension`:

```python
async def _ensure_run_started(
    client: McpClient,
    character: str | None,
    logger,
    abandon_existing: bool = False,
    ascension: int | None = None,
) -> bool:
```

In its body, forward `ascension` to `client.start_new_run`:

```python
    return await client.start_new_run(
        character=character,
        ascension=ascension,
        abandon_existing=abandon_existing,
    )
```

Update all call sites of `_ensure_run_started` and `client.start_new_run` in `main()` to pass `ascension=effective_ascension`.

- [ ] **Step 6: Set target_ascension on RunState**

After `agent.run()` returns (or alternatively before the run starts via the agent), set target on the RunState. The simplest location is right after `agent.reset_for_new_run()`:

```python
            agent.reset_for_new_run()
            if effective_ascension is not None and agent._run_state is not None:
                agent._run_state.target_ascension = effective_ascension
```

Note: `_run_state` is created inside `agent.run()`, not after `reset_for_new_run()`. Instead, access it after `run()` returns. Actually, the cleanest approach: inside `run()`, `_run_state` is created at line 1869. We can't easily inject target_ascension there. Instead, record it post-run from the effective_ascension variable:

```python
            run_state = await agent.run()
            # Ensure target_ascension is recorded even if game didn't report it
            if effective_ascension is not None and run_state.target_ascension is None:
                run_state.target_ascension = effective_ascension
```

Wait — RunState is frozen=False (it's a mutable dataclass), so this is fine.

- [ ] **Step 7: Build RunRecord and record after each run**

After `_log_run_summary` (around line 168), add the recording block:

```python
            # -- Record run to history --
            outcome = _map_outcome(
                agent._run_completion_reason,
                agent._run_end_reason,
                run_state.victory,
            )
            record = RunRecord(
                run_id=run_state.run_id,
                started_at=run_state.start_time,
                ended_at=run_state.end_time or time.time(),
                profile_hash=profile_hash,
                profile_label=profile_label,
                model_profile=model_profile,
                character=run_state.character,
                target_ascension=run_state.target_ascension,
                actual_ascension=run_state.actual_ascension,
                outcome=outcome,
                victory=run_state.victory,
                final_floor=run_state.final_floor,
                final_hp=run_state.final_hp,
                final_max_hp=run_state.final_max_hp,
                final_gold=run_state.final_gold,
                fitness=run_state.fitness(),
                score=run_state.final_score,
                duration_seconds=run_state.duration_seconds,
                steps=run_state.total_actions,
                llm_calls=run_state.llm_calls,
                total_actions=run_state.total_actions,
                combats_won=run_state.combats_won,
                combats_total=run_state.combats_total,
                completion_reason=agent._run_completion_reason or "",
                end_reason=agent._run_end_reason or "",
                use_llm=use_llm,
                memory_enabled=config.MEMORY_ENABLED,
                skills_enabled=config.SKILLS_ENABLED,
            )
            history_store.append(record)
            asc_rec = ascension_stats.record_run(record)
            ascension_stats.save(runs_dir / "ascension_stats.json")
            logger.info(
                "Recorded: %s A%d — %d/%d wins (best floor %d)",
                asc_rec.character, asc_rec.ascension,
                asc_rec.wins, asc_rec.total_runs, asc_rec.best_floor,
            )
```

- [ ] **Step 8: Add the _map_outcome helper**

Add this function near the top of `run_agent.py`, after `_log_run_summary`:

```python
def _map_outcome(completion_reason: str, end_reason: str, victory: bool) -> str:
    """Map agent loop reasons to a clean outcome label."""
    if victory:
        return "victory"
    if completion_reason == "completed":
        return "defeat"
    if end_reason == "max_steps":
        return "max_steps"
    if end_reason == "interrupt":
        return "interrupt"
    # agent_abort covers: unknown_state_terminal, RuntimeError, loop_exit
    return "agent_abort"
```

- [ ] **Step 9: Add ascension to _log_run_summary**

In `_log_run_summary` (around line 40), after the character log line, add:

```python
    logger.info("  Ascension: A%d", run_state.ascension)
```

- [ ] **Step 10: Add session-end ascension summary**

At the session end logging (around line 197), add:

```python
        if character:
            from src.memory.models_v2 import normalize_character
            norm_char = normalize_character(character)
            char_stats = ascension_stats.stats_for(
                profile_hash=profile_hash, character=norm_char,
            )
            if char_stats:
                cleared = ascension_stats.highest_cleared(profile_hash, norm_char)
                logger.info("Highest cleared ascension for %s [%s]: A%d", norm_char, profile_hash, cleared)
                for s in char_stats:
                    logger.info(
                        "  A%d: %d/%d wins (%.0f%%), best floor %d",
                        s.ascension, s.wins, s.total_runs, s.win_rate * 100, s.best_floor,
                    )
```

- [ ] **Step 11: Run full test suite**

Run: `cd AgenticSTS && python -m pytest tests/ -x -q --timeout=30 2>&1 | head -40`
Expected: All pass

- [ ] **Step 12: Commit**

```bash
git add scripts/run_agent.py
git commit -m "feat: wire --ascension CLI with run history recording and auto-progression"
```

---

### Task 10: CLAUDE.md Update

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add to Quick Reference section**

After the existing run commands, add:

```
python -m scripts.run_agent --steps 500 --ascension 5      # Fixed ascension
python -m scripts.run_agent --steps 500 --ascension auto    # Auto-progress
```

- [ ] **Step 2: Add to Architecture section**

In the architecture tree, add under `src/`:

```
  runs/
    history.py                  # RunRecord + RunHistoryStore (append-only JSONL)
    ascension_stats.py          # AscensionStats aggregate cache (profile × character × ascension)
```

Add data paths:

```
Data: ... | `data/runs/history.jsonl` | `data/runs/ascension_stats.json`
```

- [ ] **Step 3: Add to Conventions section**

```
- **Ascension tracking**: `--ascension auto` reads `AscensionStats.next_ascension(profile_hash, character)`. Stats recorded post-run to `data/runs/`. Keyed by `(profile_hash, character, ascension)` for model isolation.
- **Run history**: every completed/aborted run appends to `data/runs/history.jsonl`. Fields include `model_profile` snapshot, `outcome` (victory/defeat/agent_abort/interrupt/max_steps), `target_ascension`/`actual_ascension`.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add ascension tracking and run analytics to CLAUDE.md"
```

---

## Verification Checklist

After all tasks are complete:

1. **Unit tests**: `python -m pytest tests/test_model_profile.py tests/test_run_history.py tests/test_ascension_stats.py tests/test_ascension_actions.py -v` — all pass
2. **Full suite**: `python -m pytest tests/ -x -q --timeout=30` — no regressions
3. **Smoke test**: `python -m scripts.run_agent --steps 5 --runs 1 --ascension 0` — verify `data/runs/history.jsonl` is created with one entry and `data/runs/ascension_stats.json` is created
4. **Auto mode**: Manually create a history entry with a victory at A0, then `python -m scripts.run_agent --steps 5 --runs 1 --ascension auto` — verify it targets A1
5. **No-flag compat**: `python -m scripts.run_agent --steps 5 --runs 1` — verify unchanged behavior, history still recorded with `target_ascension: null`
