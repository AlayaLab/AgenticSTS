"""Compare mod /state response keys against Pydantic model fields."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def flatten_keys(obj: Any, prefix: str = "") -> set[str]:
    """Flatten nested dict/list keys into dotted paths."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else k
            out.add(key)
            out.update(flatten_keys(v, key))
    elif isinstance(obj, list):
        if obj:
            out.update(flatten_keys(obj[0], f"{prefix}[]"))
    return out


@dataclass
class CoverageReport:
    missing_from_model: set[str]
    unused_in_response: set[str]


def compare(raw_keys: set[str], modeled_keys: set[str]) -> CoverageReport:
    return CoverageReport(
        missing_from_model=raw_keys - modeled_keys,
        unused_in_response=modeled_keys - raw_keys,
    )
