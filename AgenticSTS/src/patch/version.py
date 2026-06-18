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
