"""Inspect V2 HCM domain stores.

Usage:
    python -m scripts.inspect_memory [--dir data/memory]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, ".")

import config
from src.memory.memory_manager import MemoryManager


def main(data_dir: str | None = None) -> None:
    base = Path(data_dir) if data_dir else Path(config.MEMORY_DIR)
    if not base.exists():
        print(f"Memory directory not found: {base}")
        print("No memory data yet. Run the agent to generate memories.")
        return

    mm = MemoryManager(data_dir=base)
    stats = mm.stats()

    print("=" * 60)
    print("  STS2 Agent Memory Inspector")
    print("=" * 60)
    print()

    # Overview
    print(f"  Combat episodes:   {stats.get('v2_combat_episodes', 0)}")
    print(f"  Route memories:    {stats.get('v2_route_memories', 0)}")
    print(f"  Card builds:       {stats.get('v2_card_builds', 0)}")
    # Guide stats
    for key, val in stats.items():
        if key.startswith("v2_") and key not in (
            "v2_combat_episodes", "v2_route_memories", "v2_card_builds",
        ):
            label = key.replace("v2_", "").replace("_", " ").title()
            print(f"  {label}:  {val}")
    print()

    # V2 combat episode summary
    if mm.combat_store and mm.combat_store.count > 0:
        print("-" * 60)
        print("  Combat Episode Summary")
        print("-" * 60)
        all_episodes = mm.combat_store.get_all()
        by_enemy: dict[str, int] = {}
        for ep in all_episodes:
            by_enemy[ep.enemy_key] = by_enemy.get(ep.enemy_key, 0) + 1
        for enemy, count in sorted(by_enemy.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"    {enemy}: {count}")
        print()

    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect STS2 agent memory")
    parser.add_argument("--dir", type=str, default=None, help="Memory data directory")
    args = parser.parse_args()
    main(data_dir=args.dir)
