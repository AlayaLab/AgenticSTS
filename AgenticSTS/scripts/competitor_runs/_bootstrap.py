"""Load the repo-root .env so standalone competitor-run tools get STS2_* credentials.

The logging proxy and the Gemini hosts run as plain ``python -m ...`` processes that do
NOT import the main app's config, so the project's ``.env`` is not auto-loaded. Importing
this module loads it (best-effort; a no-op if python-dotenv or ``.env`` is absent).
"""
from __future__ import annotations

from pathlib import Path

try:
    from dotenv import load_dotenv

    _env = Path(__file__).resolve().parents[2] / ".env"
    if _env.exists():
        load_dotenv(_env)
except Exception:  # noqa: BLE001 - env bootstrap must never break the tool.
    pass
