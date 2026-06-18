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
