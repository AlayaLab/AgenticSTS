"""LLM-driven prompt file rewrite based on manifest-derived targets."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.patch.slug import slug


@dataclass
class FileChangeRequest:
    path: Path
    matched_targets: set[str]
    original_content: str


class LLMBackend(Protocol):
    def complete(self, *, system: str, user: str) -> str: ...


@dataclass
class RewriteResult:
    request: FileChangeRequest
    new_content: str
    changed: bool


_SYSTEM_PROMPT = """You are rewriting a Python prompt file in a game-agent codebase.
The game has been updated. Some entities referenced in this file are now changed.
Produce a minimal rewrite: update only lines that reference changed entities.
Preserve all other content character-for-character, including comments, formatting, imports.
Output the ENTIRE new file content, nothing else. No markdown fences, no explanation.
"""


def scan_prompt_files(root: Path, targets: set[str]) -> list[FileChangeRequest]:
    """Recursively scan .py files under root for references to any target.

    A file is flagged if, after slug-normalization, its content contains
    any target string as substring. Case/punctuation-insensitive by slug.
    """
    requests: list[FileChangeRequest] = []
    if not root.exists():
        return requests
    for p in root.rglob("*.py"):
        content = p.read_text(encoding="utf-8", errors="ignore")
        content_slug = slug(content)
        matched = {t for t in targets if t and t in content_slug}
        if matched:
            requests.append(FileChangeRequest(
                path=p,
                matched_targets=matched,
                original_content=content,
            ))
    return requests


def rewrite_file(request: FileChangeRequest, *, manifest_context: str, backend: LLMBackend) -> RewriteResult:
    """Ask LLM to rewrite the file; return new content."""
    user_prompt = f"""# Changes to apply
{manifest_context}

# Targets detected in this file (slugged)
{sorted(request.matched_targets)}

# Current file content
{request.original_content}
"""
    new_content = backend.complete(system=_SYSTEM_PROMPT, user=user_prompt)
    new_content = _strip_code_fence(new_content)
    return RewriteResult(
        request=request,
        new_content=new_content,
        changed=(new_content.strip() != request.original_content.strip()),
    )


def _strip_code_fence(text: str) -> str:
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)
