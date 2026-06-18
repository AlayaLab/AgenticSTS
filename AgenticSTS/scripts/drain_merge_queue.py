"""Drain the sibling-repo merge queue (manual).

Processes entries in ``<data_repo>/evolution/merge_queue.jsonl`` that
``scripts/data_sync.py`` quarantined during reconcile. Skills entries run
through :func:`src.skills.merge_pipeline.run_merge_pair` (LLM-backed).
Guides and other sections are currently left for manual review.

Usage::

    python -m scripts.drain_merge_queue            # default cap: 2
    python -m scripts.drain_merge_queue --cap 5
    python -m scripts.drain_merge_queue --all      # no cap

The queue file is rewritten in place: successful merges are removed,
failures with a retry_count < 3 stay for the next attempt, and entries
with unrecognized shape are dropped.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.storage import merge_queue


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group()
    g.add_argument("--cap", type=int, default=merge_queue.DEFAULT_CAP,
                   help="Max entries to process this invocation")
    g.add_argument("--all", action="store_true",
                   help="Drain every entry (no cap)")
    args = p.parse_args(argv)

    cap = None if args.all else args.cap
    result = merge_queue.drain_sync(cap=cap)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["processed"] >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
