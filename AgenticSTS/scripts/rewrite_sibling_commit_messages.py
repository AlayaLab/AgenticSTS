"""Rewrite the sibling ``AgenticSTS-Data`` repo's historical commit messages.

Runs in two phases:

1. **Build**: for every commit, inspect its diff and compute a new message
   using a template picked by what the commit actually did:

   - ``legacy-bulk-import`` — the single mass-import commit that seeded the
     shared brain state (877 runs).
   - ``runs <first>..<last> (N=K) @ legacy-unknown base=<parent-short>`` —
     sync commits that added ≥2 run-ids across the JSONL stores.
   - ``legacy-<N>: <original-subject>`` — everything else (code edits, seed
     data, schema migrations, single-store touch-ups). The original subject
     is kept so provenance isn't lost; the body adds structured stats.

2. **Apply**: invokes ``git filter-repo`` with a callback that maps each
   commit's ``original_id`` to the precomputed message. Rewrites SHAs (as
   filter-repo must), force-push required afterwards.

Preview first::

    python -m scripts.rewrite_sibling_commit_messages --preview

Actually rewrite::

    python -m scripts.rewrite_sibling_commit_messages --apply

The target repo must be clean and the current branch is used as-is.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

JSONL_RUN_SOURCES = (
    "evolution/evolution_log.jsonl",
    "memory/v2/combat_episodes.jsonl",
    "memory/v2/event_memories.jsonl",
    "memory/v2/route_memories.jsonl",
    "memory/v2/card_builds.jsonl",
    "runs/history.jsonl",
)

# Paths whose added-line count we report directly in the stats block.
APPEND_JSONLS = {
    "evolution/evolution_log.jsonl": ("evolution", "log-entries"),
    "memory/v2/combat_episodes.jsonl": ("memory", "combat_ep"),
    "memory/v2/event_memories.jsonl": ("memory", "event"),
    "memory/v2/route_memories.jsonl": ("memory", "route"),
    "memory/v2/card_builds.jsonl": ("memory", "card_build"),
    "runs/history.jsonl": ("runs", "history"),
}

# Dict-JSON files — we only report "changed" (not structural keys) because the
# semantics vary and a per-file parse would be overkill for legacy history.
DICT_JSONS = {
    "memory/rules.json": ("memory", "rules"),
    "memory/v2/guides.json": ("memory", "guides"),
    "memory/v2/card_memories.json": ("memory", "card_memories"),
    "skills/skills.json": ("skills", "skills"),
    "runs/ascension_stats.json": ("runs", "ascension_stats"),
    "evolution/tools/tool_stats.json": ("evolution", "tool_stats"),
    "evolution/tools/retirement_state.json": ("evolution", "retirement_state"),
}

BULK_IMPORT_SUBJECT = "feat(data): seed shared brain state for team collaboration"


def _run(cmd: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True).stdout


def _commit_meta(repo: Path, sha: str) -> dict[str, str]:
    fields = ["%H", "%h", "%an", "%aI", "%s", "%P"]
    out = _run(["git", "show", "-s", f"--format={'%x1f'.join(fields)}", sha], cwd=repo)
    parts = out.strip("\n").split("\x1f", 5)
    while len(parts) < 6:
        parts.append("")
    full, short, author, date, subject, parents = parts
    parent_list = parents.split() if parents else []
    return {
        "sha": full, "short": short, "author": author, "date": date,
        "subject": subject, "parents": parent_list,
    }


def _iter_added_json_lines(repo: Path, sha: str, path: str):
    """Yield parsed JSON objects for each + line under ``path`` in ``sha``'s diff."""
    try:
        diff = _run(["git", "diff", f"{sha}~..{sha}", "--", path], cwd=repo)
    except subprocess.CalledProcessError:
        return
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        body = line[1:].strip()
        if not body.startswith("{"):
            continue
        try:
            yield json.loads(body)
        except json.JSONDecodeError:
            continue


def _count_added_lines(repo: Path, sha: str, path: str) -> int:
    """Count JSONL '+' lines (excluding diff header) for ``path`` at ``sha``."""
    return sum(1 for _ in _iter_added_json_lines(repo, sha, path))


def _changed_files(repo: Path, sha: str) -> list[str]:
    out = _run(["git", "show", "--name-only", "--pretty=format:", sha], cwd=repo)
    return [p for p in out.splitlines() if p.strip()]


_SENTINEL_RUN_IDS = {"unknown", "run-aborted", "aborted", "legacy"}


def _collect_run_ids(repo: Path, sha: str) -> list[str]:
    """Collect + dedup + chronologically sort valid run_ids from this commit."""
    dedup: set[str] = set()
    for path in JSONL_RUN_SOURCES:
        for obj in _iter_added_json_lines(repo, sha, path):
            rid = obj.get("run_id")
            if not rid or rid in _SENTINEL_RUN_IDS:
                continue
            # run_id format is YYYYMMDD_HHMMSS_<8hex> — lexicographic = chronological.
            if len(rid) < 15 or not rid[:8].isdigit():
                continue
            dedup.add(rid)
    return sorted(dedup)


def _new_tool_files(repo: Path, sha: str) -> list[str]:
    """.py files under evolution/tools/ that are newly added at ``sha``."""
    try:
        out = _run(
            ["git", "diff-tree", "--no-commit-id", "--name-status", "-r", sha],
            cwd=repo,
        )
    except subprocess.CalledProcessError:
        return []
    new: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts
        if status.strip() == "A" and path.startswith("evolution/tools/") and path.endswith(".py"):
            new.append(path.rsplit("/", 1)[-1])
    return new


def _compute_stats(repo: Path, sha: str) -> dict:
    stats: dict[str, list[str]] = defaultdict(list)
    changed = set(_changed_files(repo, sha))

    for path, (section, label) in APPEND_JSONLS.items():
        if path in changed:
            n = _count_added_lines(repo, sha, path)
            if n > 0:
                stats[section].append(f"+{n} {label}")

    for path, (section, label) in DICT_JSONS.items():
        if path in changed:
            stats[section].append(f"{label} Δ")

    tools = _new_tool_files(repo, sha)
    if tools:
        if len(tools) <= 3:
            stats["evolution"].insert(0, f"+{len(tools)} tool ({', '.join(tools)})")
        else:
            stats["evolution"].insert(0, f"+{len(tools)} tools")

    return dict(stats)


def _render_stats_block(stats: dict, indent: str = "") -> str:
    if not stats:
        return ""
    order = ("memory", "skills", "evolution", "runs")
    label_width = max(len(k) for k in order if k in stats) + 1
    lines = []
    for key in order:
        if key not in stats:
            continue
        label = (key + ":").ljust(label_width + 1)
        lines.append(f"{indent}{label} {', '.join(stats[key])}")
    return "\n".join(lines)


def _compose_legacy(n: int, meta: dict, stats: dict) -> str:
    subject = f"legacy-{n:02d}: {meta['subject']}"
    body_lines = []
    stats_block = _render_stats_block(stats)
    if stats_block:
        body_lines.append(stats_block)
        body_lines.append("")
    body_lines.extend([
        "@ legacy-unknown",
        f"source-sha: {meta['short']}",
        f"author:     {meta['author']}",
        f"date:       {meta['date']}",
    ])
    return f"{subject}\n\n" + "\n".join(body_lines)


def _compose_bulk(meta: dict, stats: dict, run_count: int) -> str:
    subject = f"legacy-bulk-import: seed shared brain state ({run_count} runs)"
    body_lines = []
    stats_block = _render_stats_block(stats)
    if stats_block:
        body_lines.append(stats_block)
        body_lines.append("")
    body_lines.extend([
        "@ legacy-unknown",
        f"source-sha: {meta['short']}",
        f"author:     {meta['author']}",
        f"date:       {meta['date']}",
    ])
    return f"{subject}\n\n" + "\n".join(body_lines)


def _compose_multirun(meta: dict, stats: dict, run_ids: list[str]) -> str:
    parent_short = meta["parents"][0][:7] if meta["parents"] else "root"
    # YYYYMMDD_HHMMSS — 15 chars, drop the _<hex> suffix for readability.
    first = run_ids[0][:15]
    last = run_ids[-1][:15]
    subject = f"runs {first}..{last} (N={len(run_ids)}) @ legacy-unknown  base={parent_short}"
    body_lines = []
    stats_block = _render_stats_block(stats)
    if stats_block:
        body_lines.append(stats_block)
        body_lines.append("")
    body_lines.append("run-ids:")
    for rid in run_ids:
        body_lines.append(f"  {rid}")
    body_lines.append("")
    body_lines.extend([
        f"source-sha: {meta['short']}",
        f"author:     {meta['author']}",
        f"date:       {meta['date']}",
    ])
    return f"{subject}\n\n" + "\n".join(body_lines)


def build_message_map(repo: Path) -> dict[str, str]:
    """Return ``{original_sha: new_message}`` for every commit in ``repo``."""
    shas = _run(["git", "log", "--reverse", "--format=%H"], cwd=repo).strip().split()
    msgs: dict[str, str] = {}
    for n, sha in enumerate(shas, start=1):
        meta = _commit_meta(repo, sha)
        stats = _compute_stats(repo, sha)
        run_ids = _collect_run_ids(repo, sha)

        if len(run_ids) >= 100:
            msgs[sha] = _compose_bulk(meta, stats, run_count=len(run_ids))
        elif len(run_ids) >= 2:
            msgs[sha] = _compose_multirun(meta, stats, run_ids)
        else:
            msgs[sha] = _compose_legacy(n, meta, stats)
    return msgs


def apply_rewrite(repo: Path, msg_map: dict[str, str]) -> None:
    """Invoke git-filter-repo with a callback that replaces each message."""
    map_file = repo.parent / ".sts2_msg_map.json"
    map_file.write_text(json.dumps(msg_map), encoding="utf-8")

    callback_src = f'''
import json
_map = json.loads(open({str(map_file)!r}).read())
orig = commit.original_id.decode("utf-8") if commit.original_id else None
if orig and orig in _map:
    commit.message = (_map[orig] + "\\n").encode("utf-8")
'''

    filter_repo = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "git-filter-repo"
    if not filter_repo.exists():
        logger.error("git-filter-repo not found at %s", filter_repo)
        sys.exit(2)

    cmd = [str(filter_repo), "--force", "--commit-callback", callback_src, "--preserve-commit-encoding"]
    logger.info("Invoking git-filter-repo in %s", repo)
    subprocess.run(cmd, cwd=repo, check=True)
    map_file.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=Path.cwd().parent / "AgenticSTS-Data")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--preview", action="store_true",
                   help="Print what every commit's new message would be.")
    g.add_argument("--apply", action="store_true",
                   help="Rewrite in place (destructive; force-push needed after).")
    args = p.parse_args(argv)

    repo = args.repo.resolve()
    if not (repo / ".git").is_dir():
        logger.error("Not a git repo: %s", repo)
        return 2

    logger.info("Building message map for %s", repo)
    msg_map = build_message_map(repo)
    logger.info("Built %d messages", len(msg_map))

    if args.preview:
        shas = _run(["git", "log", "--reverse", "--format=%H"], cwd=repo).strip().split()
        for sha in shas:
            print("\n" + "═" * 72)
            print(f"orig {sha[:7]}  (→ new message below)")
            print("─" * 72)
            print(msg_map[sha])
        return 0

    apply_rewrite(repo, msg_map)
    logger.info("Rewrite complete. Verify with: git log -n 10 --stat")
    logger.info("Push with: git push --force origin main && git push --force origin --tags")
    return 0


if __name__ == "__main__":
    sys.exit(main())
