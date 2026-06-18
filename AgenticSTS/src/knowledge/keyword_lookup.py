"""Keyword knowledge lookup — keyword definitions from upstream keywords.json."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class KeywordKnowledge:
    """Keyword metadata from upstream JSON."""
    id: str
    name: str
    description: str = ""


class KeywordLookup:
    """O(1) keyword lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._lookup: dict[str, KeywordKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        path = data_dir / "upstream" / "keywords.json"
        if not path.exists():
            logger.warning("Keywords data file not found: %s", path)
            return

        try:
            with path.open(encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse keywords JSON: %s", exc)
            return

        for entry in raw:
            name: str = entry.get("name", "")
            if not name:
                continue
            self._lookup[name.lower()] = KeywordKnowledge(
                id=entry.get("id", ""),
                name=name,
                description=entry.get("description", "") or "",
            )

        logger.info("Loaded %d keywords", len(self._lookup))

    def get(self, name: str) -> KeywordKnowledge | None:
        """Lookup by keyword name (case-insensitive)."""
        return self._lookup.get(name.lower())

    def format_glossary(self, keyword_names: set[str]) -> str:
        """Format keyword definitions for prompt injection."""
        defs = []
        for name in sorted(keyword_names):
            kk = self.get(name)
            if kk and kk.description:
                defs.append(f"- **{kk.name}**: {kk.description}")
        return "\n".join(defs) if defs else ""

    @property
    def count(self) -> int:
        return len(self._lookup)
