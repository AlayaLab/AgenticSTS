"""Connect to running mod and report /state schema drift vs Pydantic models."""
from __future__ import annotations

import asyncio
import sys

import httpx

from src.patch.api_coverage import compare, flatten_keys


async def fetch_raw_state(base_url: str = "http://localhost:8128") -> dict:
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(f"{base_url}/state")
        r.raise_for_status()
        return r.json()


def collect_modeled_keys() -> set[str]:
    """Introspect UpstreamGameState Pydantic model for all nested field names."""
    from src.mcp_client.upstream_models import UpstreamGameState
    return _pydantic_keys(UpstreamGameState, "")


def _pydantic_keys(model_cls, prefix: str) -> set[str]:
    out: set[str] = set()
    for name, field in model_cls.model_fields.items():
        key = f"{prefix}.{name}" if prefix else name
        out.add(key)
        ann = field.annotation
        try:
            if hasattr(ann, "model_fields"):
                out.update(_pydantic_keys(ann, key))
        except Exception:
            pass
    return out


def main() -> int:
    try:
        raw = asyncio.run(fetch_raw_state())
    except Exception as exc:
        print(f"ERROR: could not fetch /state — {exc}", file=sys.stderr)
        return 2

    raw_keys = flatten_keys(raw)
    modeled = collect_modeled_keys()
    report = compare(raw_keys, modeled)

    print(f"Raw keys: {len(raw_keys)} | Modeled: {len(modeled)}")
    if report.missing_from_model:
        print("\nFields returned by mod but not in client Pydantic models:")
        for k in sorted(report.missing_from_model):
            print(f"  + {k}")
    if report.unused_in_response:
        print("\nFields modeled by client but not returned by mod (possible schema break):")
        for k in sorted(report.unused_in_response):
            print(f"  - {k}")
    if not report.missing_from_model and not report.unused_in_response:
        print("Schemas aligned.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
