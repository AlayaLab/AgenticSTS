"""Sync dynamic data between the local sibling repo and its shared remote.

Two subcommands, one library API.

CLI
---

    python -m scripts.data_sync pull
        Called once at run start. Fetches latest remote, fast-forwards local.
        Handles orphaned uncommitted state from a crashed prior run by snapshot-
        ting it onto an ``orphan/<machine>/<ts>`` branch, then fast-forwarding.

    python -m scripts.data_sync push --run-id <id> [--outcome ...] [--floor N] ...
        Called at run end after postrun completes. Stages working-tree changes,
        composes a structured commit message from the run metadata + diff stats,
        commits, fetches, reconciles via per-file merge drivers if needed, pushes.

Library API
-----------

    from scripts import data_sync
    data_sync.pull()                 -> dict {status, head, data_repo_sha}
    data_sync.push_run(run_record)   -> dict {status, commit_sha, pushed}

Degraded mode: when ``STS2_DATA_REPO`` is unset, or the sibling dir doesn't
exist, or the remote is unreachable, calls return ``{"status": "disabled"}``
and the agent is never blocked.

Merge drivers (§5 of the design) route by file pattern:

    memory/v2/*.jsonl                      → append_dedup
    runs/history.jsonl                     → append_dedup
    evolution/evolution_log.jsonl          → append_dedup
    evolution/reap_log.jsonl etc.          → append_dedup
    memory/rules.json                      → rule_merge          (TODO)
    memory/v2/guides.json                  → dict_counter_merge  (TODO)
    memory/v2/card_memories.json           → dict_counter_merge  (TODO)
    runs/ascension_stats.json              → dict_counter_merge  (TODO)
    skills/skills.json                     → skills_merge        (TODO — queue)
    evolution/tools/*.py                   → tool_merge          (TODO)

Scope of this file: pull/push plumbing + JSONL append_dedup. Dict-merge and
skills/tool strategies land in the next pass; until then, if a non-JSONL
conflict arises the push falls through to an ``orphan/<machine>/<run_id>``
branch so the run's work is not lost.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage import paths  # noqa: E402

logger = logging.getLogger(__name__)


# ───────────────────── config ─────────────────────────────────────────

MAX_PUSH_RETRIES = 5
ORPHAN_BRANCH_PREFIX = "orphan"
DEFAULT_REMOTE = "origin"
DEFAULT_BRANCH = "main"


# ───────────────────── git helpers ────────────────────────────────────


class GitError(RuntimeError):
    pass


def _git(repo: Path, *args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *args]
    logger.debug("git %s (cwd=%s)", " ".join(args), repo)
    return subprocess.run(
        cmd, cwd=repo, check=check, text=True,
        capture_output=capture,
    )


def _git_ok(repo: Path, *args: str) -> bool:
    try:
        _git(repo, *args)
        return True
    except subprocess.CalledProcessError:
        return False


def _head_sha(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _has_working_tree_changes(repo: Path) -> bool:
    out = _git(repo, "status", "--porcelain").stdout
    return bool(out.strip())


def _current_branch(repo: Path) -> str:
    return _git(repo, "branch", "--show-current").stdout.strip()


def _remote_reachable(repo: Path, remote: str = DEFAULT_REMOTE) -> bool:
    return _git_ok(repo, "ls-remote", "--heads", remote)


def _fetch(repo: Path, remote: str = DEFAULT_REMOTE) -> bool:
    try:
        _git(repo, "fetch", remote)
        return True
    except subprocess.CalledProcessError as exc:
        logger.warning("fetch failed: %s", exc.stderr.strip() if exc.stderr else exc)
        return False


# ───────────────────── availability check ────────────────────────────


def sibling_available() -> Path | None:
    """Return sibling repo (git root) path if usable, else None (degraded mode).

    Resolution order:
    1. ``STS2_RUNS_HISTORY_REPO`` (if set and a git repo) — ablation experiments
       isolate L4/L5 stores via ``STS2_DATA_REPO`` pointing at a non-git subdir
       inside the sibling repo. ``STS2_RUNS_HISTORY_REPO`` is the orchestrator's
       explicit handle to the actual git root, so prefer it when present.
    2. ``paths.data_root()`` itself, if it is a git repo (the common
       single-machine case where the user points ``STS2_DATA_REPO`` at the
       sibling clone root).

    Returns ``None`` when neither resolves to a git repo. The previous
    upward-walk fallback was removed — it incorrectly returned the *code*
    repo when only the default ``<project>/data`` path was in play, which
    would commit run data into the wrong repository.
    """
    history_root_env = os.getenv("STS2_RUNS_HISTORY_REPO")
    if history_root_env:
        history_root = paths.runs_history_root()
        if (history_root / ".git").is_dir():
            return history_root
    repo = paths.data_root()
    if (repo / ".git").is_dir():
        return repo
    return None


# ───────────────────── pull ──────────────────────────────────────────


def pull(repo: Path | None = None, *, remote: str = DEFAULT_REMOTE,
         branch: str = DEFAULT_BRANCH) -> dict[str, Any]:
    """Sync local sibling repo from remote at run start.

    Returns ``{"status": ok|disabled|orphaned|error, "head": sha,
               "data_repo_sha": sha}``.
    """
    if repo is None:
        repo = sibling_available()
    if repo is None:
        return {"status": "disabled"}

    if not _remote_reachable(repo, remote):
        logger.warning("Sibling remote %r unreachable — entering read-only mode", remote)
        return {"status": "offline", "head": _head_sha(repo), "data_repo_sha": _head_sha(repo)}

    # If the tree is dirty, something interrupted a previous run mid-write.
    # Quarantine to an orphan branch so we don't lose data, then reset to HEAD
    # before fast-forwarding.
    orphan_note: str | None = None
    if _has_working_tree_changes(repo):
        ts = time.strftime("%Y%m%d_%H%M%S")
        orphan = f"{ORPHAN_BRANCH_PREFIX}/{paths.machine_id()}/{ts}-precrash"
        logger.warning("Dirty working tree on pull — saving to %s", orphan)
        try:
            _git(repo, "checkout", "-b", orphan)
            _git(repo, "add", "-A")
            _git(repo, "commit", "-m", f"orphan pre-crash snapshot {ts} @ {paths.machine_id()}")
            _git(repo, "checkout", branch)
            orphan_note = orphan
        except subprocess.CalledProcessError as exc:
            logger.error("Failed to quarantine dirty tree: %s", exc.stderr if exc.stderr else exc)
            return {"status": "error", "error": "dirty-quarantine-failed"}

    if not _fetch(repo, remote):
        return {"status": "offline", "head": _head_sha(repo), "data_repo_sha": _head_sha(repo)}

    # Fast-forward only; refuse to merge with local unpushed commits here.
    try:
        _git(repo, "merge", "--ff-only", f"{remote}/{branch}")
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or "").strip()
        logger.warning("Pull not fast-forward (%s) — leaving local ahead; push will reconcile", msg)

    head = _head_sha(repo)
    return {
        "status": "ok" if not orphan_note else "orphaned",
        "head": head, "data_repo_sha": head,
        "orphan_branch": orphan_note,
    }


# ───────────────────── merge drivers ──────────────────────────────────


JSONL_APPEND_DEDUP_PATTERNS: tuple[tuple[str, tuple[str, ...], str | None], ...] = (
    # (glob-like prefix match, dedup-key fields, sort-by field)
    ("memory/v2/combat_episodes.jsonl",   ("run_id", "combat_id", "floor"), "ts"),
    ("memory/v2/route_memories.jsonl",    ("run_id", "floor"),              "ts"),
    ("memory/v2/card_builds.jsonl",       ("run_id", "character"),          "ts"),
    ("memory/v2/event_memories.jsonl",    ("run_id", "floor", "event_id"),  "ts"),
    ("runs/history.jsonl",                ("run_id",),                      "ended_at"),
    ("evolution/evolution_log.jsonl",     ("run_id", "timestamp", "tool"),  "timestamp"),
    ("evolution/reap_log.jsonl",          ("run_id", "ts"),                 "ts"),
    ("evolution/write_gate_log.jsonl",    ("run_id", "ts"),                 "ts"),
    ("evolution/judge_log.jsonl",         ("run_id", "ts"),                 "ts"),
    ("evolution/ab_replay_log.jsonl",     ("run_id", "ts"),                 "ts"),
)


def _append_dedup_merge(
    base_text: str, local_text: str, remote_text: str,
    *, id_keys: tuple[str, ...], sort_key: str | None,
) -> str:
    """Union JSONL lines from base+local+remote, dedup by ``id_keys``, sort.

    Lines that don't parse as JSON (corrupted or non-JSONL) are preserved
    from ``local`` but dropped from ``base``/``remote`` for safety.
    """
    seen: dict[tuple, str] = {}
    raw_order: list[tuple] = []

    def _key(obj: dict) -> tuple:
        return tuple(obj.get(k) for k in id_keys)

    for text in (base_text, local_text, remote_text):
        for raw in text.splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            key = _key(obj)
            if key in seen:
                continue  # first-seen wins
            seen[key] = raw
            raw_order.append(key)

    if sort_key:
        def _sort_key(k: tuple) -> Any:
            raw = seen[k]
            try:
                v = json.loads(raw).get(sort_key)
            except json.JSONDecodeError:
                return 0
            return v if v is not None else 0
        raw_order.sort(key=_sort_key)

    return "\n".join(seen[k] for k in raw_order) + ("\n" if seen else "")


# ───────── dict-record delta merge (shared by JSON stores) ──────────


def _merge_scalar(base: Any, local: Any, remote: Any, field: str) -> Any:
    """Three-way merge of a single field from records in the three branches.

    Rules by type (picked to match the dynamic-data semantics):
      int/float : delta-apply  → base + (local-base) + (remote-base)
      bool      : AND          → if any branch set False, result is False
      list      : union-by-equality, preserving local order then appending new-from-remote
      dict      : recurse per-key
      str/None  : local wins on conflict (most-recent author); warn on divergence
    """
    if isinstance(local, bool) or isinstance(remote, bool) or isinstance(base, bool):
        # AND semantics: conservative (e.g., "active" turning off wins over staying on)
        return bool(base) and bool(local) and bool(remote) if base is not None else (bool(local) and bool(remote))
    if isinstance(local, (int, float)) and isinstance(remote, (int, float)):
        b = base if isinstance(base, (int, float)) else 0
        merged = b + (local - b) + (remote - b)
        # Preserve int-ness when all three sides are int.
        if isinstance(base, int) and isinstance(local, int) and isinstance(remote, int):
            return int(merged)
        return merged
    if isinstance(local, list) and isinstance(remote, list):
        # Union preserving local order, appending only remote-new items.
        # Use JSON-stable repr as equality check (handles dicts/lists in lists).
        seen: set[str] = set()
        out: list = []
        for item in local + remote:
            key = json.dumps(item, sort_keys=True, ensure_ascii=False) if not isinstance(item, (str, int, float, bool, type(None))) else item
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
        return out
    if isinstance(local, dict) and isinstance(remote, dict):
        base_d = base if isinstance(base, dict) else {}
        return _merge_dict(base_d, local, remote)
    # Strings / None / heterogeneous: local wins.
    if local != remote and local != base:
        logger.debug("merge_scalar conflict on %r (local=%r remote=%r base=%r) — local wins",
                     field, local, remote, base)
    return local


def _merge_dict(base: dict, local: dict, remote: dict) -> dict:
    out: dict = {}
    keys = set(base) | set(local) | set(remote)
    for k in keys:
        if k in local and k in remote:
            out[k] = _merge_scalar(base.get(k), local[k], remote[k], field=k)
        elif k in local:
            out[k] = local[k]
        elif k in remote:
            out[k] = remote[k]
        # keys only in base (deleted on both sides) → drop
    return out


def _merge_list_of_records(
    base_text: str, local_text: str, remote_text: str,
    *, id_keys: tuple[str, ...], bulk_key: str | None = None,
    field_policies: dict[str, str | tuple[str, str]] | None = None,
) -> str:
    """Three-way merge for JSON files that are a list of records.

    Records are keyed by the tuple of fields in ``id_keys``. If ``bulk_key``
    is set, the top level is a dict with that key holding the list (e.g.
    ``{"records": [...]}`` for ascension_stats.json).

    ``field_policies`` lets individual fields override the generic delta
    semantics. Supported policies:

        "max"                     : max across the three sides
        ("weighted_mean", WF)     : recompute avg from (sum_i * weight_i).
                                    Uses base/local/remote ``WF`` as
                                    weights; ``sum_base = base_avg * base_W``.
                                    Example: ("weighted_mean", "total_runs")
                                    for avg_floor.

    Per-record merge uses :func:`_merge_dict`; records missing from one
    side are taken from the other.
    """
    policies = field_policies or {}
    def _load(text: str) -> tuple[list, dict]:
        if not text.strip():
            return [], {}
        data = json.loads(text)
        if bulk_key:
            records = data.get(bulk_key, []) if isinstance(data, dict) else []
        else:
            records = data if isinstance(data, list) else []
        return records, (data if isinstance(data, dict) else {})

    def _index(records: list) -> dict[tuple, dict]:
        out: dict[tuple, dict] = {}
        for rec in records:
            if not isinstance(rec, dict):
                continue
            key = tuple(rec.get(k) for k in id_keys)
            out[key] = rec
        return out

    base_rec, _          = _load(base_text)
    local_rec, local_env = _load(local_text)
    remote_rec, _        = _load(remote_text)

    base_idx   = _index(base_rec)
    local_idx  = _index(local_rec)
    remote_idx = _index(remote_rec)

    all_keys = list(local_idx.keys()) + [k for k in remote_idx if k not in local_idx]
    merged: list = []
    for key in all_keys:
        b = base_idx.get(key, {})
        l = local_idx.get(key)
        r = remote_idx.get(key)
        if l is not None and r is not None:
            rec = _merge_dict(b, l, r)
            _apply_field_policies(rec, b, l, r, policies)
            merged.append(rec)
        elif l is not None:
            merged.append(l)
        elif r is not None:
            merged.append(r)

    if bulk_key:
        out_env = dict(local_env)
        out_env[bulk_key] = merged
        return json.dumps(out_env, indent=2, ensure_ascii=False) + "\n"
    return json.dumps(merged, indent=2, ensure_ascii=False) + "\n"


def _apply_field_policies(
    record: dict, base: dict, local: dict, remote: dict,
    policies: dict[str, str | tuple[str, str]],
) -> None:
    """Override merged field values for fields with non-additive semantics."""
    for field, policy in policies.items():
        if policy == "max":
            candidates = [
                v for v in (base.get(field), local.get(field), remote.get(field))
                if isinstance(v, (int, float))
            ]
            if candidates:
                record[field] = max(candidates)
        elif isinstance(policy, tuple) and policy[0] == "weighted_mean":
            weight_field = policy[1]
            bw = base.get(weight_field, 0) or 0
            lw = local.get(weight_field, 0) or 0
            rw = remote.get(weight_field, 0) or 0
            # Reconstruct per-side sums from (avg * weight); derive the true
            # merged sum via delta-apply to avoid double-counting the base.
            bs = (base.get(field) or 0) * bw
            ls = (local.get(field) or 0) * lw
            rs = (remote.get(field) or 0) * rw
            merged_sum = bs + (ls - bs) + (rs - bs)
            merged_weight = record.get(weight_field, 0) or 0
            if merged_weight > 0:
                record[field] = merged_sum / merged_weight


# ───────── guides.json: nested dict, queue content conflicts ────────


def _merge_guides_json(base_text: str, local_text: str, remote_text: str) -> str:
    """guides.json = {combat_guides|route_guides|deck_guides|event_guides: {id: guide_obj}}.

    For each section and each guide_id present on both sides, if ``guide_text``
    differs, quarantine the remote version to the merge queue and keep local.
    Non-conflicting inserts are unioned.
    """
    def _load(text: str) -> dict:
        return json.loads(text) if text.strip() else {}

    base   = _load(base_text)
    local  = _load(local_text)
    remote = _load(remote_text)

    queue_entries: list[dict] = []
    out: dict = {}
    for section in set(base) | set(local) | set(remote):
        b = base.get(section, {}) or {}
        l = local.get(section, {}) or {}
        r = remote.get(section, {}) or {}
        merged_section: dict = {}
        for gid in set(b) | set(l) | set(r):
            lg = l.get(gid)
            rg = r.get(gid)
            if lg is None and rg is None:
                continue
            if lg is not None and rg is not None:
                if _guide_text(lg) != _guide_text(rg):
                    queue_entries.append({
                        "ts": time.time(), "file": "memory/v2/guides.json",
                        "section": section, "guide_id": gid,
                        "local": lg, "remote": rg,
                    })
                    merged_section[gid] = lg
                else:
                    merged_section[gid] = lg
            elif lg is not None:
                merged_section[gid] = lg
            else:
                merged_section[gid] = rg
        out[section] = merged_section

    if queue_entries:
        _append_merge_queue(queue_entries)

    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def _guide_text(g: Any) -> str:
    if isinstance(g, dict):
        return g.get("guide_text", "")
    return str(g)


# ───────── skills.json: union + queue on content divergence ─────────


def _merge_skills_json(base_text: str, local_text: str, remote_text: str) -> str:
    """skills.json = list of skill dicts keyed by ``skill_id``.

    For each skill_id present on both sides:
      - If ``content``, ``name``, or ``trigger`` differ → quarantine remote
        record to the merge_queue; keep local.
      - Else merge stats additively (usage_count, success_count, etc.) via
        :func:`_merge_dict`.
    Seed skills (source=seed) are exempt from retirement elsewhere; here
    they behave identically to any other skill for merge purposes.
    """
    def _load(text: str) -> list[dict]:
        if not text.strip():
            return []
        data = json.loads(text)
        return data if isinstance(data, list) else data.get("skills", [])

    base   = _load(base_text)
    local  = _load(local_text)
    remote = _load(remote_text)

    def _by_id(records: list[dict]) -> dict[str, dict]:
        return {r["skill_id"]: r for r in records if isinstance(r, dict) and r.get("skill_id")}

    bi, li, ri = _by_id(base), _by_id(local), _by_id(remote)

    queue_entries: list[dict] = []
    out: list[dict] = []
    all_ids = list(li.keys()) + [k for k in ri if k not in li]
    for sid in all_ids:
        b = bi.get(sid, {})
        l = li.get(sid)
        r = ri.get(sid)
        if l is not None and r is not None:
            content_conflict = (
                l.get("content") != r.get("content")
                or l.get("name") != r.get("name")
                or l.get("trigger") != r.get("trigger")
            )
            if content_conflict:
                queue_entries.append({
                    "ts": time.time(), "file": "skills/skills.json",
                    "skill_id": sid, "local": l, "remote": r,
                })
                # Keep local record; stats still merge additively.
                merged = _merge_dict(b, l, {**r, "content": l.get("content"),
                                            "name": l.get("name"),
                                            "trigger": l.get("trigger")})
                out.append(merged)
            else:
                out.append(_merge_dict(b, l, r))
        elif l is not None:
            out.append(l)
        elif r is not None:
            out.append(r)

    if queue_entries:
        _append_merge_queue(queue_entries)

    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


# ───────── merge queue plumbing ─────────────────────────────────────


def _append_merge_queue(entries: Iterable[dict]) -> None:
    path = paths.merge_queue_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    logger.warning("Queued %d conflict(s) for LLM merge at %s",
                   sum(1 for _ in entries if True), path)


# ───────── driver registry ──────────────────────────────────────────

LIST_RECORD_PATTERNS: tuple[
    tuple[str, tuple[str, ...], str | None, dict[str, Any] | None], ...
] = (
    # (path, id_keys, bulk_key-if-nested, field_policies)
    ("memory/rules.json",             ("rule_id",),                              None,      None),
    ("memory/v2/card_memories.json",  ("character", "card_name"),                None,      None),
    ("runs/ascension_stats.json",     ("profile_hash", "character", "ascension"), "records",
     {"best_floor": "max", "avg_floor": ("weighted_mean", "total_runs")}),
)


def _merge_driver_for(path: str) -> Callable[[str, str, str], str] | None:
    for prefix, id_keys, sort_key in JSONL_APPEND_DEDUP_PATTERNS:
        if path == prefix:
            return lambda b, l, r, _ik=id_keys, _sk=sort_key: _append_dedup_merge(
                b, l, r, id_keys=_ik, sort_key=_sk,
            )
    for prefix, id_keys, bulk_key, field_policies in LIST_RECORD_PATTERNS:
        if path == prefix:
            return lambda b, l, r, _ik=id_keys, _bk=bulk_key, _fp=field_policies: _merge_list_of_records(
                b, l, r, id_keys=_ik, bulk_key=_bk, field_policies=_fp,
            )
    if path == "memory/v2/guides.json":
        return _merge_guides_json
    if path == "skills/skills.json":
        return _merge_skills_json
    return None


# ───────── tool-file (py) driver — operates on filesystem, not text ─


def reconcile_tool_file_collision(repo: Path, path: str, machine: str) -> str:
    """Handle ``evolution/tools/<name>.py`` same-name byte-conflict.

    Rename the remote version to ``<name>__<machine>.py`` and log to
    ``evolution/merge_conflicts.jsonl``. Returns the new filename.
    Caller must ``git add`` both files and mark the original as resolved.
    """
    abs_path = repo / path
    stem = abs_path.stem
    new_name = f"{stem}__{machine}.py"
    new_path = abs_path.parent / new_name
    _git(repo, "mv", path, str(new_path.relative_to(repo)))
    _append_merge_conflicts([{
        "ts": time.time(), "file": path,
        "kind": "tool-rename", "renamed_to": new_name, "machine": machine,
    }])
    return new_name


def _append_merge_conflicts(entries: Iterable[dict]) -> None:
    path = paths.merge_conflicts_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ───────────────────── push ──────────────────────────────────────────


@dataclass
class PushMetadata:
    run_id: str
    machine_id: str
    outcome: str            # victory|defeat|agent_abort|max_steps|interrupt|…
    floor: int
    ascension: int | None
    duration_seconds: float
    code_sha: str           # main-repo HEAD
    mod_version: str
    game_version: str


def _diff_stats(repo: Path, cached: bool = True) -> dict[str, dict[str, int]]:
    """Return {path: {added, deleted}} for each changed file."""
    args = ["diff", "--numstat"]
    if cached:
        args.append("--cached")
    out = _git(repo, *args).stdout
    stats: dict[str, dict[str, int]] = {}
    for line in out.strip().splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, deleted, path = parts
        try:
            stats[path] = {
                "added":   int(added) if added != "-" else 0,
                "deleted": int(deleted) if deleted != "-" else 0,
            }
        except ValueError:
            continue
    return stats


_SECTION_MAP: dict[str, tuple[str, str]] = {
    "memory/v2/combat_episodes.jsonl":    ("memory",    "combat_ep"),
    "memory/v2/route_memories.jsonl":     ("memory",    "route"),
    "memory/v2/card_builds.jsonl":        ("memory",    "card_build"),
    "memory/v2/event_memories.jsonl":     ("memory",    "event"),
    "memory/v2/guides.json":              ("memory",    "guides Δ"),
    "memory/v2/card_memories.json":       ("memory",    "card_memories Δ"),
    "memory/rules.json":                  ("memory",    "rules Δ"),
    "skills/skills.json":                 ("skills",    "skills Δ"),
    "skills/skill_usage.jsonl":           ("skills",    "usage"),
    "evolution/evolution_log.jsonl":      ("evolution", "log-entries"),
    "evolution/reap_log.jsonl":           ("evolution", "reap-entries"),
    "evolution/write_gate_log.jsonl":     ("evolution", "gate-entries"),
    "evolution/judge_log.jsonl":          ("evolution", "judge-entries"),
    "runs/history.jsonl":                 ("runs",      "history"),
    "runs/ascension_stats.json":          ("runs",      "ascension_stats Δ"),
}


_EXPERIMENT_PREFIX_RE = re.compile(r"^experiments/[^/]+/[^/]+/")


def _strip_experiment_prefix(path: str) -> str:
    """Map ``experiments/<tag>/<cond>/foo/bar`` to ``foo/bar`` for ``_SECTION_MAP``.

    Ablation runs isolate L4/L5 writes under ``experiments/<tag>/<cond>/`` while
    sharing ``runs/`` at the repo root (see :func:`sibling_available`). The
    section map only lists the unprefixed canonical paths, so strip the prefix
    before lookup so the commit message summarizes those writes too.
    """
    return _EXPERIMENT_PREFIX_RE.sub("", path, count=1)


def _build_commit_message(
    repo: Path, meta: PushMetadata, *, kind: str = "run",
) -> str:
    base_short = ""
    try:
        base_short = _git(repo, "rev-parse", "--short=7", f"{DEFAULT_REMOTE}/{DEFAULT_BRANCH}").stdout.strip()
    except subprocess.CalledProcessError:
        try:
            base_short = _git(repo, "rev-parse", "--short=7", "HEAD~1").stdout.strip()
        except subprocess.CalledProcessError:
            base_short = "root"

    stats = _diff_stats(repo, cached=True)
    sections: dict[str, list[str]] = {"memory": [], "skills": [], "evolution": [], "runs": []}
    new_tools: list[str] = []

    for path, counts in stats.items():
        added = counts["added"]
        canonical = _strip_experiment_prefix(path)
        if canonical in _SECTION_MAP:
            section, label = _SECTION_MAP[canonical]
            if "Δ" in label or label in ("skills Δ",):
                sections[section].append(label)
            else:
                sections[section].append(f"+{added} {label}")
        elif (canonical.startswith("evolution/tools/")
              and canonical.endswith(".py")):
            new_tools.append(canonical.rsplit("/", 1)[-1])

    if new_tools:
        sections["evolution"].insert(
            0,
            f"+{len(new_tools)} tool" + ("" if len(new_tools) == 1 else "s")
            + (f" ({', '.join(new_tools)})" if len(new_tools) <= 3 else ""),
        )

    subject = f"{kind} {meta.run_id} @ {meta.machine_id}  base={base_short}"

    body_lines: list[str] = []
    label_width = max((len(k) for k, v in sections.items() if v), default=0) + 1
    for key in ("memory", "skills", "evolution", "runs"):
        if not sections[key]:
            continue
        body_lines.append(f"{(key + ':').ljust(label_width + 1)} {', '.join(sections[key])}")

    body_lines.append("")
    body_lines.append(f"run-id:   {meta.run_id}")
    body_lines.append(f"outcome:  {meta.outcome} F{meta.floor}"
                       + (f" A{meta.ascension}" if meta.ascension is not None else "")
                       + f" ({meta.duration_seconds:.0f}s)")
    body_lines.append(f"code-sha: {meta.code_sha[:7]}")
    body_lines.append(f"mod:      {meta.mod_version}  game: {meta.game_version}")

    return subject + "\n\n" + "\n".join(body_lines)


def _reconcile_conflicts(repo: Path) -> tuple[bool, list[str]]:
    """Resolve merge conflicts via per-file drivers. Returns (all_resolved, unresolved_paths)."""
    out = _git(repo, "diff", "--name-only", "--diff-filter=U").stdout
    conflicts = [p for p in out.strip().splitlines() if p.strip()]
    if not conflicts:
        return True, []
    unresolved: list[str] = []
    for path in conflicts:
        # evolution/tools/*.py — filesystem rename-on-collision (not text merge)
        if path.startswith("evolution/tools/") and path.endswith(".py"):
            try:
                new_name = reconcile_tool_file_collision(repo, path, paths.machine_id())
                # local kept as <new_name>; restore remote's version at original path.
                remote_blob = _git(repo, "show", f":3:{path}").stdout
                (repo / path).write_text(remote_blob, encoding="utf-8")
                _git(repo, "add", path)
                logger.info("Tool collision on %s: renamed local to %s, kept remote at %s",
                            path, new_name, path)
            except Exception as exc:
                logger.warning("Tool-file driver failed on %s: %s", path, exc)
                unresolved.append(path)
            continue

        driver = _merge_driver_for(path)
        if driver is None:
            unresolved.append(path)
            continue
        try:
            base    = _git(repo, "show", f":1:{path}").stdout
            local   = _git(repo, "show", f":2:{path}").stdout
            remote  = _git(repo, "show", f":3:{path}").stdout
            merged  = driver(base, local, remote)
            (repo / path).write_text(merged, encoding="utf-8")
            _git(repo, "add", path)
            logger.info("Resolved %s via %s (%d bytes)",
                        path, driver.__name__ if hasattr(driver, "__name__") else "driver",
                        len(merged))
        except Exception as exc:
            logger.warning("Driver failed on %s: %s", path, exc)
            unresolved.append(path)
    return (not unresolved), unresolved


def push_run(meta: PushMetadata, *, repo: Path | None = None,
             remote: str = DEFAULT_REMOTE, branch: str = DEFAULT_BRANCH,
             kind: str = "run") -> dict[str, Any]:
    """Commit run deltas to sibling and push.

    ``kind`` selects the commit subject prefix and is currently one of:

    - ``"run"``: gameplay-end push (history.jsonl + any in-run skill_usage /
      state_snapshot writes). Called immediately after the run record is
      appended so a postrun crash cannot lose the gameplay outcome.
    - ``"postrun"``: postrun-end push (memory/v2/*, skills/skills.json,
      evolution/* deltas produced by ``finalize_session``). Called after
      postrun finishes so its writes actually reach ``main`` instead of
      being orphaned by the next run's ``pull()`` dirty-tree quarantine.

    Returns ``{"status": ok|nochange|disabled|offline|orphaned|error,
               "commit_sha": sha, "pushed": bool, ...}``.
    """
    if repo is None:
        repo = sibling_available()
    if repo is None:
        return {"status": "disabled"}

    if not _has_working_tree_changes(repo):
        return {"status": "nochange", "commit_sha": _head_sha(repo), "pushed": False}

    _git(repo, "add", "-A")
    message = _build_commit_message(repo, meta, kind=kind)
    _git(repo, "commit", "-m", message, "--allow-empty-message")
    commit_sha = _head_sha(repo)
    logger.info("Committed %s to sibling: %s", commit_sha[:7], message.splitlines()[0])

    # Offline → commit stays local, skip push loop.
    if not _remote_reachable(repo, remote):
        return {"status": "offline", "commit_sha": commit_sha, "pushed": False}

    for attempt in range(1, MAX_PUSH_RETRIES + 1):
        _fetch(repo, remote)
        try:
            _git(repo, "push", remote, f"HEAD:{branch}")
            return {"status": "ok", "commit_sha": commit_sha, "pushed": True, "attempts": attempt}
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            if "non-fast-forward" not in stderr and "fetch first" not in stderr:
                logger.error("Push failed non-conflict (attempt %d): %s", attempt, stderr)
                # Unknown failure — bail to orphan.
                break
            logger.info("Push rejected (attempt %d): remote advanced, rebasing…", attempt)

        # Attempt rebase; per-file drivers handle JSONL conflicts.
        try:
            _git(repo, "rebase", f"{remote}/{branch}")
        except subprocess.CalledProcessError:
            pass

        in_rebase = (repo / ".git" / "rebase-merge").exists() or (repo / ".git" / "rebase-apply").exists()
        if in_rebase:
            resolved, unresolved = _reconcile_conflicts(repo)
            if not resolved:
                logger.warning("Cannot auto-resolve: %s", ", ".join(unresolved))
                _git(repo, "rebase", "--abort", check=False)
                break
            try:
                env = os.environ.copy()
                env["GIT_EDITOR"] = "true"  # don't open editor on `rebase --continue`
                subprocess.run(
                    ["git", "rebase", "--continue"], cwd=repo, check=True,
                    text=True, capture_output=True, env=env,
                )
            except subprocess.CalledProcessError as exc:
                logger.warning("Rebase continue failed: %s", (exc.stderr or "").strip())
                _git(repo, "rebase", "--abort", check=False)
                break

        # Loop and retry the push.

    # Fallback: park on an orphan branch so the run's data isn't lost.
    # Include ``kind`` so a postrun-push fallback doesn't collide with the
    # earlier gameplay-push orphan branch for the same run_id.
    orphan_suffix = "" if kind == "run" else f"-{kind}"
    orphan = f"{ORPHAN_BRANCH_PREFIX}/{meta.machine_id}/{meta.run_id}{orphan_suffix}"
    try:
        _git(repo, "branch", orphan)
        _git(repo, "push", remote, f"refs/heads/{orphan}:refs/heads/{orphan}")
        logger.warning("Pushed to orphan branch %s — manual merge required", orphan)
        # Also reset our main back so subsequent runs aren't stuck ahead.
        _git(repo, "reset", "--hard", f"{remote}/{branch}")
        return {
            "status": "orphaned", "commit_sha": commit_sha,
            "pushed": False, "orphan_branch": orphan,
        }
    except subprocess.CalledProcessError as exc:
        logger.error("Even orphan push failed: %s", (exc.stderr or "").strip())
        return {"status": "error", "commit_sha": commit_sha, "pushed": False}


# ───────────────────── CLI ───────────────────────────────────────────


def _cli_pull(args: argparse.Namespace) -> int:
    res = pull()
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") not in ("error",) else 1


def _cli_push(args: argparse.Namespace) -> int:
    meta = PushMetadata(
        run_id=args.run_id,
        machine_id=args.machine_id or paths.machine_id(),
        outcome=args.outcome,
        floor=args.floor,
        ascension=args.ascension,
        duration_seconds=args.duration,
        code_sha=args.code_sha or _current_code_sha(),
        mod_version=args.mod_version,
        game_version=args.game_version,
    )
    res = push_run(meta)
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") in ("ok", "nochange", "disabled", "offline") else 1


def _current_code_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=paths.project_root(), check=True, text=True, capture_output=True,
        ).stdout.strip()
        return out
    except subprocess.CalledProcessError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pull", help="Sync from remote at run start")

    push = sub.add_parser("push", help="Commit run deltas and push")
    push.add_argument("--run-id", required=True)
    push.add_argument("--machine-id", default=None)
    push.add_argument("--outcome", default="unknown")
    push.add_argument("--floor", type=int, default=0)
    push.add_argument("--ascension", type=int, default=None)
    push.add_argument("--duration", type=float, default=0.0)
    push.add_argument("--code-sha", default=None)
    push.add_argument("--mod-version", default="unknown")
    push.add_argument("--game-version", default="unknown")

    args = p.parse_args(argv)
    if args.cmd == "pull":
        return _cli_pull(args)
    if args.cmd == "push":
        return _cli_push(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
