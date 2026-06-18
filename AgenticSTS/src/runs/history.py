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

from src.patch.version import get_runtime_version

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

    # Experiment batch identifier (for ablation studies etc.)
    experiment_tag: str = ""

    # Sibling-data-repo provenance (see CLAUDE.md § "Data Repository Split").
    data_repo_sha: str = ""    # sibling HEAD at run start (data version A)
    machine_id: str = ""       # short-host id of the machine that ran this

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
            "experiment_tag": self.experiment_tag,
            "data_repo_sha": self.data_repo_sha,
            "machine_id": self.machine_id,
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
            experiment_tag=d.get("experiment_tag", ""),
            data_repo_sha=d.get("data_repo_sha", ""),
            machine_id=d.get("machine_id", ""),
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
        rv = get_runtime_version()
        d = record.to_dict()
        d.setdefault("game_version", rv.game_version)
        d.setdefault("mod_version", rv.mod_version)
        d.setdefault("data_schema_version", rv.data_schema_version)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(d) + "\n")

    def load_all(self) -> list[RunRecord]:
        return list(self._records)

    def query(
        self,
        *,
        character: str | None = None,
        profile_hash: str | None = None,
        ascension: int | None = None,
        experiment_tag: str | None = None,
    ) -> list[RunRecord]:
        results = self._records
        if character is not None:
            results = [r for r in results if r.character == character]
        if profile_hash is not None:
            results = [r for r in results if r.profile_hash == profile_hash]
        if ascension is not None:
            results = [r for r in results if r.actual_ascension == ascension]
        if experiment_tag is not None:
            results = [r for r in results if r.experiment_tag == experiment_tag]
        return results

    @property
    def count(self) -> int:
        return len(self._records)
