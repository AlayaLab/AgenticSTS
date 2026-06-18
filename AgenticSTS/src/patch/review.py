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
