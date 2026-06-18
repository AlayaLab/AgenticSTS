"""Stub template loading and character substitution.

Mode B (seed stub self-evolution) uses character-parametric templates that
live in ``src/skills/seeds_stubs/*.template.json``. At Mode B startup the
SkillLibrary instantiates each template once per active character — replacing
``{character}`` / ``{character_id}`` / ``{character_name}`` placeholders with
the run's character.

The framework is character-agnostic: 5 templates × N characters = 5N stubs,
with no per-character code branches.

Spec: ``docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md``
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ── Substitution helpers ────────────────────────────────────────


def _normalize_id(character: str) -> str:
    """e.g. 'the silent' -> 'the_silent'. Lowercase + spaces to underscores."""
    return character.lower().strip().replace(" ", "_")


def _normalize_name(character: str) -> str:
    """e.g. 'the silent' -> 'The Silent'. Title-case each word."""
    return " ".join(w.capitalize() for w in character.lower().strip().split())


def _substitute_in(value: Any, mapping: dict[str, str]) -> Any:
    """Recursively substitute {placeholder} tokens in any nested string field.

    Handles dicts, lists, and bare strings. Non-string values pass through.
    """
    if isinstance(value, str):
        out = value
        for k, v in mapping.items():
            out = out.replace(f"{{{k}}}", v)
        return out
    if isinstance(value, list):
        return [_substitute_in(x, mapping) for x in value]
    if isinstance(value, dict):
        return {k: _substitute_in(v, mapping) for k, v in value.items()}
    return value


def substitute_character(template: dict, character: str) -> dict:
    """Instantiate a stub template for a specific character.

    Two transformations:
    1. Replace {character}, {character_id}, {character_name} placeholders in
       all string fields recursively.
    2. Rename ``*_template`` keys to non-suffixed keys (e.g.
       ``skill_id_template`` -> ``skill_id``).

    The template itself is not mutated; a new dict is returned.
    """
    mapping = {
        "character": character.lower().strip(),
        "character_id": _normalize_id(character),
        "character_name": _normalize_name(character),
    }
    substituted = _substitute_in(template, mapping)

    # Rename *_template keys to final keys
    renamed: dict = {}
    for k, v in substituted.items():
        if k.endswith("_template"):
            renamed[k[: -len("_template")]] = v
        else:
            renamed[k] = v
    return renamed


# ── Template loader ─────────────────────────────────────────────


def load_stub_templates(stub_dir: Path) -> list[dict]:
    """Read all ``*.template.json`` files from a directory.

    Missing directory or unreadable files are logged at WARNING level and
    skipped — never raised. Returns an empty list when nothing was loaded.
    """
    templates: list[dict] = []
    if not stub_dir.exists():
        logger.debug("Stub template directory does not exist: %s", stub_dir)
        return templates
    for path in sorted(stub_dir.glob("*.template.json")):
        try:
            with path.open("r", encoding="utf-8") as f:
                templates.append(json.load(f))
        except Exception as exc:
            logger.warning("Failed to load stub template %s: %s", path, exc)
    return templates
