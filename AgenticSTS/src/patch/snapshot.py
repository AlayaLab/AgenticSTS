"""Snapshot the data/ tree before destructive patch operations."""
from __future__ import annotations

import shutil
from pathlib import Path


def snapshot_data(src: Path, snap_root: Path, label: str) -> Path:
    """Copy src/ into snap_root/<label>/.

    If destination exists, append a numeric suffix (label-1, label-2, ...)
    so prior snapshots are never overwritten.

    If snap_root is a subdirectory of src, that subtree is automatically
    excluded from the copy to prevent infinite recursion.
    """
    # Sanitize label to prevent path traversal
    label = label.replace("/", "_").replace("\\", "_").replace("..", "__").strip()
    if not label:
        label = "unnamed"

    snap_root.mkdir(parents=True, exist_ok=True)
    candidate = snap_root / label
    i = 1
    while candidate.exists():
        candidate = snap_root / f"{label}-{i}"
        i += 1

    # Build an ignore function that skips snap_root if it lives inside src.
    ignore = None
    try:
        snap_root_rel = snap_root.resolve().relative_to(src.resolve())
        # snap_root is inside src — ignore its top-level name at the right depth.
        top_level_name = snap_root_rel.parts[0]

        def ignore(directory: str, contents: list[str]) -> set[str]:  # type: ignore[misc]
            if Path(directory).resolve() == src.resolve():
                return {top_level_name}
            return set()

    except ValueError:
        pass  # snap_root is outside src — no ignore needed

    shutil.copytree(src, candidate, ignore=ignore)
    return candidate
