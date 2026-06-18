"""Single chokepoint for dynamic-data path resolution.

Resolution order for the data root:

1. ``STS2_DATA_REPO`` — absolute path to the sibling ``AgenticSTS-Data`` repo.
2. ``STS2_DATA_DIR`` — legacy env var pointing to an inline ``data/`` dir.
3. Default: ``<project root>/../AgenticSTS-Data`` (the sibling repo).

The default is required to exist on disk; if it doesn't, ``data_root()`` raises
``FileNotFoundError`` with setup instructions. Explicit ``STS2_DATA_REPO`` /
``STS2_DATA_DIR`` overrides are trusted as-is (the ablation orchestrator
points them at per-experiment dirs that are created on demand).

Every accessor returns an absolute :class:`pathlib.Path`. Accessors never
create files or directories — callers are responsible for ``mkdir(parents=True,
exist_ok=True)`` when writing.

Classification boundary:

- **Dynamic** (lives in the sibling repo): memory/, skills/, evolution/, runs/.
- **Static** (stays in the main repo): knowledge/, patches/,
  version_compatibility.json, src/skills/seeds/.

For the static subtrees, keep using ``config.DATA_DIR`` / direct paths; they
are intentionally not exposed here.
"""

from __future__ import annotations

import os
import re
import socket
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SIBLING = (_PROJECT_ROOT.parent / "AgenticSTS-Data").resolve()


def project_root() -> Path:
    """Main code-repo root. Stable regardless of cwd."""
    return _PROJECT_ROOT


def data_root() -> Path:
    """Resolve the dynamic-data root.

    Precedence: ``STS2_DATA_REPO`` > ``STS2_DATA_DIR`` > sibling ``AgenticSTS-Data``.

    Raises:
        FileNotFoundError: if no env override is set and the default sibling
            repo (``<project root>/../AgenticSTS-Data``) is missing on disk.
    """
    repo = os.getenv("STS2_DATA_REPO")
    if repo:
        return Path(repo).expanduser().resolve()
    legacy = os.getenv("STS2_DATA_DIR")
    if legacy:
        p = Path(legacy).expanduser()
        return p.resolve() if p.is_absolute() else (_PROJECT_ROOT / p).resolve()
    if not _DEFAULT_SIBLING.is_dir():
        raise FileNotFoundError(
            f"Sibling data repo not found at {_DEFAULT_SIBLING}. "
            "Clone it: git clone https://github.com/ShandaAI/AgenticSTS (data in AgenticSTS-Data/) "
            f"{_DEFAULT_SIBLING}  (or set STS2_DATA_REPO to override the path)."
        )
    return _DEFAULT_SIBLING


def runs_history_root() -> Path:
    """Resolve the root for runs/history.jsonl and runs/ascension_stats.json.

    Precedence: ``STS2_RUNS_HISTORY_REPO`` > ``data_root()``.

    Ablation experiments isolate L4/L5 stores per-condition via
    ``STS2_DATA_REPO`` while sharing run history at a parent path so post-hoc
    aggregation by ``experiment_tag`` works across conditions.
    """
    override = os.getenv("STS2_RUNS_HISTORY_REPO")
    if override:
        return Path(override).expanduser().resolve()
    return data_root()


# ── Memory ───────────────────────────────────────────────────────────
def memory_dir() -> Path:
    return data_root() / "memory"


def memory_v2_dir() -> Path:
    return memory_dir() / "v2"


def rules_file() -> Path:
    return memory_dir() / "rules.json"


def guides_file() -> Path:
    return memory_v2_dir() / "guides.json"


def combat_episodes_file() -> Path:
    return memory_v2_dir() / "combat_episodes.jsonl"


def route_memories_file() -> Path:
    return memory_v2_dir() / "route_memories.jsonl"


def card_builds_file() -> Path:
    return memory_v2_dir() / "card_builds.jsonl"


def card_memories_file() -> Path:
    return memory_v2_dir() / "card_memories.json"


def event_memories_file() -> Path:
    return memory_v2_dir() / "event_memories.jsonl"


def guide_consolidation_log_file() -> Path:
    return memory_v2_dir() / "guide_consolidation_log.jsonl"


# ── Skills ───────────────────────────────────────────────────────────
def skills_dir() -> Path:
    return data_root() / "skills"


def skills_file() -> Path:
    return skills_dir() / "skills.json"


def skill_usage_log() -> Path:
    return skills_dir() / "skill_usage.jsonl"


# ── Evolution ────────────────────────────────────────────────────────
def evolution_dir() -> Path:
    return data_root() / "evolution"


def evolution_tools_dir() -> Path:
    return evolution_dir() / "tools"


def evolution_proposals_dir() -> Path:
    return evolution_dir() / "proposals"


def evolution_contexts_dir(run_id: str | None = None) -> Path:
    base = evolution_dir() / "contexts"
    return base / run_id if run_id else base


def evolution_log_file() -> Path:
    return evolution_dir() / "evolution_log.jsonl"


def reap_log_file() -> Path:
    return evolution_dir() / "reap_log.jsonl"


def write_gate_log_file() -> Path:
    return evolution_dir() / "write_gate_log.jsonl"


def judge_log_file() -> Path:
    return evolution_dir() / "judge_log.jsonl"


def ab_replay_log_file() -> Path:
    return evolution_dir() / "ab_replay_log.jsonl"


def l1_l2_l3_index_file() -> Path:
    return evolution_dir() / "l1_l2_l3_index.json"


def embedding_cache_file() -> Path:
    return evolution_dir() / "embedding_cache.json"


def state_snapshots_file() -> Path:
    return evolution_dir() / "state_snapshots.jsonl"


def tool_stats_file() -> Path:
    return evolution_tools_dir() / "tool_stats.json"


def retirement_state_file() -> Path:
    return evolution_tools_dir() / "retirement_state.json"


def ab_test_results_dir() -> Path:
    return evolution_dir() / "ab_test_results"


def merge_queue_file() -> Path:
    """Skill-merge conflict queue; drained by postrun LLM merge stage."""
    return evolution_dir() / "merge_queue.jsonl"


def merge_conflicts_file() -> Path:
    """Tool-filename collisions resolved by auto-rename."""
    return evolution_dir() / "merge_conflicts.jsonl"


# ── Runs ─────────────────────────────────────────────────────────────
def runs_dir() -> Path:
    return runs_history_root() / "runs"


def runs_history_file() -> Path:
    return runs_dir() / "history.jsonl"


def ascension_stats_file() -> Path:
    return runs_dir() / "ascension_stats.json"


# ── Identity ─────────────────────────────────────────────────────────
_MACHINE_ID_RE = re.compile(r"[^a-zA-Z0-9_-]+")


def machine_id() -> str:
    """Normalized identifier for this machine.

    Override via ``STS2_MACHINE_ID``; default is the short hostname
    (lowercased, non-alphanumerics collapsed to ``_``, truncated to 32 chars).
    """
    raw = os.getenv("STS2_MACHINE_ID") or socket.gethostname().split(".")[0]
    normalized = _MACHINE_ID_RE.sub("_", raw).strip("_").lower()[:32]
    return normalized or "unknown"
