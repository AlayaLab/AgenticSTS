"""Freeze an existing run log as a regression baseline."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from src.regression.log_replay import LogReplayClient, compute_fingerprint


GOLDEN_DIR = Path("tests/fixtures/golden_logs")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("log", type=Path, help="Source JSONL log to freeze")
    p.add_argument("--game-version", default="v0.5.3",
                   help="Version label for the goldens dir")
    p.add_argument("--name", default=None, help="Label for the frozen log (default: source filename)")
    args = p.parse_args()

    if not args.log.exists():
        print(f"Log not found: {args.log}")
        return 2

    target_dir = GOLDEN_DIR / args.game_version
    target_dir.mkdir(parents=True, exist_ok=True)
    name = args.name or args.log.stem
    dst = target_dir / f"{name}.jsonl"
    shutil.copyfile(args.log, dst)

    client = LogReplayClient(dst)
    fp = compute_fingerprint(list(client.iter_decisions()))
    fp_path = target_dir / f"{name}.fingerprint.json"
    fp_path.write_text(json.dumps(fp, indent=2), encoding="utf-8")

    print(f"Froze {dst}")
    print(f"Fingerprint: {fp_path}")
    print(json.dumps(fp, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
