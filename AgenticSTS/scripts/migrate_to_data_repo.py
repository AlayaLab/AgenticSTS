"""History-preserving migration of dynamic data into the sibling repo.

Splits ``data/memory/``, ``data/skills/``, ``data/evolution/``, ``data/runs/``
out of the main repo's history into a new repo whose root contains
``memory/``, ``skills/``, ``evolution/``, ``runs/``. Static subtrees
(``data/knowledge/``, ``data/patches/``, ``data/version_compatibility.json``,
``data/reports/``, per-machine counters) are intentionally dropped.

Usage::

    # Dry-run: show what will be migrated and where, without touching remote.
    python -m scripts.migrate_to_data_repo --dry-run

    # Full run: creates target repo locally and configures the remote.
    # Does NOT push — print the exact git push command at the end for the
    # user to run after inspecting the result.
    python -m scripts.migrate_to_data_repo

The script never modifies the source repo. It operates on a fresh clone
in a temporary workspace, runs ``git filter-repo`` there, then moves
the result to ``--target``.

Requires ``git-filter-repo`` installed (``pip install git-filter-repo``).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# Paths kept from the main repo, in (source, dest) form. Source paths are
# relative to the repo root; dest paths become the layout of the sibling repo.
PATH_RENAMES: tuple[tuple[str, str], ...] = (
    ("data/memory/", "memory/"),
    ("data/skills/", "skills/"),
    ("data/evolution/", "evolution/"),
    ("data/runs/", "runs/"),
)

# Everything not matching the above is dropped from history. That includes:
#   data/knowledge/   — static, stays in main repo
#   data/patches/     — static, stays in main repo
#   data/reports/     — local audit output
#   data/version_compatibility.json, data/batch_pending.json,
#   data/skill_discovery_counter.json — static/local


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    logger.info("$ %s%s", " ".join(cmd), f"  (in {cwd})" if cwd else "")
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=True)


def _count_commits(repo: Path) -> int:
    out = subprocess.run(
        ["git", "rev-list", "--count", "HEAD"], cwd=repo,
        check=True, text=True, capture_output=True,
    )
    return int(out.stdout.strip() or "0")


def _du_bytes(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            total += p.stat().st_size
    return total


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _locate_filter_repo() -> str:
    venv_bin = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "git-filter-repo"
    if venv_bin.exists():
        return str(venv_bin)
    found = shutil.which("git-filter-repo")
    if found:
        return found
    logger.error(
        "git-filter-repo not found. Install with:\n"
        "    uv pip install --python .venv/bin/python git-filter-repo\n"
        "  or:  brew install git-filter-repo"
    )
    sys.exit(2)


def migrate(
    *,
    source: Path,
    target: Path,
    remote_url: str | None,
    dry_run: bool,
) -> None:
    filter_repo = _locate_filter_repo()

    if not (source / ".git").is_dir():
        logger.error("Source is not a git repo: %s", source)
        sys.exit(2)

    # Refuse to overwrite a non-empty target.
    if target.exists() and any(target.iterdir()):
        logger.error("Target exists and is not empty: %s", target)
        sys.exit(2)

    before_commits = _count_commits(source)
    logger.info("Source HEAD has %d commits", before_commits)

    workspace = Path(tempfile.mkdtemp(prefix="sts2-data-split-"))
    clone_dir = workspace / "clone"
    logger.info("Workspace: %s", workspace)

    try:
        # A fresh local clone ensures the original repo is never touched.
        _run([
            "git", "clone", "--no-local", "--no-hardlinks",
            str(source), str(clone_dir),
        ])

        # Build filter-repo args: --path-rename OLD:NEW for each (src,dst),
        # and --path-glob to restrict to only the kept prefixes. filter-repo
        # drops everything not matched.
        cmd = [filter_repo, "--force"]
        for src, dst in PATH_RENAMES:
            cmd.extend(["--path", src, "--path-rename", f"{src}:{dst}"])
        _run(cmd, cwd=clone_dir)

        after_commits = _count_commits(clone_dir)
        before_bytes = _du_bytes(source / ".git")
        after_bytes = _du_bytes(clone_dir / ".git")

        logger.info("────────── Migration audit ──────────")
        logger.info("Commits kept:  %d  (source had %d)", after_commits, before_commits)
        logger.info("Pack size:     %s → %s",
                    _human_size(before_bytes), _human_size(after_bytes))

        # List top-level files/dirs in the resulting working tree.
        _run(["git", "checkout", "HEAD", "--", "."], cwd=clone_dir)
        top = sorted(p.name for p in clone_dir.iterdir()
                     if p.name != ".git")
        logger.info("Top-level:     %s", ", ".join(top) if top else "(empty)")

        # Show a recent-commits sample so user can verify history looks sane.
        log = subprocess.run(
            ["git", "log", "--oneline", "-n", "10"],
            cwd=clone_dir, check=True, text=True, capture_output=True,
        ).stdout
        logger.info("Last 10 commits in sibling:\n%s", log.strip())

        if dry_run:
            logger.info("Dry-run: leaving workspace at %s (no target created).", workspace)
            logger.info("Review then re-run without --dry-run to materialize.")
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(clone_dir), str(target))
        logger.info("Sibling repo materialized at: %s", target)

        # filter-repo typically wipes the clone's origin remote, but defensively
        # remove any that remains before adding the new one.
        try:
            _run(["git", "remote", "remove", "origin"], cwd=target)
        except subprocess.CalledProcessError:
            pass

        if remote_url:
            _run(["git", "remote", "add", "origin", remote_url], cwd=target)
            logger.info("Remote 'origin' → %s", remote_url)

        logger.info("────────── Next steps ──────────")
        logger.info("1. Inspect:   cd %s && git log --stat -5", target)
        logger.info("2. Verify empty remote: git ls-remote origin")
        logger.info("3. Push:      git push -u origin HEAD:main")
        logger.info("4. Tag both repos post-split: git tag pre-split && git tag post-split")
    finally:
        # Workspace dir gets cleaned only if we moved clone_dir out of it.
        if workspace.exists() and clone_dir.exists():
            # dry_run branch: leave workspace for inspection
            pass
        elif workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path.cwd(),
                   help="Main-repo path (default: cwd)")
    p.add_argument("--target", type=Path,
                   default=Path.cwd().parent / "AgenticSTS-Data",
                   help="Where to materialize the new sibling repo")
    p.add_argument("--remote", type=str,
                   default="https://github.com/ShandaAI/AgenticSTS (data in AgenticSTS-Data/)",
                   help="Remote URL to configure as 'origin' (pass empty to skip)")
    p.add_argument("--dry-run", action="store_true",
                   help="Run filter-repo in a temp workspace; print audit; do not create target.")
    args = p.parse_args(argv)

    migrate(
        source=args.source.resolve(),
        target=args.target.resolve(),
        remote_url=args.remote or None,
        dry_run=args.dry_run,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
