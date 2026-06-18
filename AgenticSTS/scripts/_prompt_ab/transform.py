"""B1 transform: relocate `## Available Cards` to the tail (before Evaluation)."""
from __future__ import annotations

import re


class B1TransformError(ValueError):
    """Raised when the transform cannot find both required anchors."""


_AVAILABLE_HEADER = "## Available Cards"
_EVAL_HEADER = "## Evaluation — Boss Damage Check"


def _find_section_span(text: str, header: str) -> tuple[int, int]:
    """Return (start, end) byte offsets of the section starting at ``header``.

    The section ends just before the next top-level `## ` header or at EOF.
    """
    start = text.find(header)
    if start == -1:
        raise B1TransformError(f"section header not found: {header!r}")
    next_match = re.search(r"\n##\s", text[start + len(header):])
    if next_match is None:
        end = len(text)
    else:
        end = start + len(header) + next_match.start() + 1
    return start, end


def apply_b1(user_message: str) -> str:
    """Move the ``## Available Cards`` block to immediately before
    ``## Evaluation — Boss Damage Check``.

    Idempotent: if the block is already directly above the eval block, returns
    the input unchanged. Raises B1TransformError if either anchor is missing.
    """
    avail_start, avail_end = _find_section_span(user_message, _AVAILABLE_HEADER)
    eval_start = user_message.find(_EVAL_HEADER)
    if eval_start == -1:
        raise B1TransformError(f"section header not found: {_EVAL_HEADER!r}")

    between = user_message[avail_end:eval_start]
    if between.strip() == "":
        return user_message

    if avail_start > eval_start:
        return user_message

    avail_block = user_message[avail_start:avail_end]
    avail_block = avail_block.rstrip() + "\n\n"

    before = user_message[:avail_start]
    middle = user_message[avail_end:eval_start]
    after = user_message[eval_start:]

    middle = middle.rstrip() + "\n\n"

    return before + middle + avail_block + after
