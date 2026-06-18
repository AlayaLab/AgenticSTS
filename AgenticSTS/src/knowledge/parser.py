"""Markdown table parser for knowledge data files."""

from __future__ import annotations

from pathlib import Path


def parse_md_table(path: Path) -> list[dict[str, str]]:
    """Parse a markdown table file into a list of row dicts.

    Expects standard markdown table format:
        | Col1 | Col2 | Col3 |
        | --- | --- | --- |
        | val1 | val2 | val3 |

    Returns list of dicts keyed by header names. Empty cells become "".
    """
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, str]] = []
    headers: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue

        cells = [c.strip() for c in stripped.split("|")[1:-1]]

        if not headers:
            headers = cells
            continue

        # Skip separator row (| --- | --- |)
        if all(c.replace("-", "").replace(":", "") == "" for c in cells):
            continue

        row = {}
        for i, h in enumerate(headers):
            row[h] = cells[i] if i < len(cells) else ""
        rows.append(row)

    return rows
