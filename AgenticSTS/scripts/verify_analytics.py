"""Verify combat analytics against real episode data.

Usage:
    python -m scripts.verify_analytics                    # All Insatiable episodes
    python -m scripts.verify_analytics --enemy "Fogmog"   # Specific enemy
    python -m scripts.verify_analytics --last 5            # Last 5 episodes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.combat_analytics import analyze_episode, format_analytics
from src.memory.models_v2 import CombatEpisode
from src.storage import paths


def load_episodes(path: Path, enemy_filter: str = "") -> list[CombatEpisode]:
    """Load episodes from JSONL file."""
    episodes: list[CombatEpisode] = []
    with open(path) as f:
        for line in f:
            data = json.loads(line)
            if enemy_filter and enemy_filter.lower() not in data.get("enemy_key", "").lower():
                continue
            episodes.append(CombatEpisode.from_dict(data))
    return episodes


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify combat analytics")
    parser.add_argument("--enemy", default="insatiable", help="Enemy name filter")
    parser.add_argument("--last", type=int, default=5, help="Number of recent episodes")
    parser.add_argument("--all", action="store_true", help="Show all episodes")
    args = parser.parse_args()

    data_path = paths.combat_episodes_file()
    if not data_path.exists():
        print(f"File not found: {data_path}")
        return

    episodes = load_episodes(data_path, args.enemy)
    print(f"Found {len(episodes)} episodes matching '{args.enemy}'")

    if not args.all:
        episodes = episodes[-args.last:]

    for ep in episodes:
        has_events = any(rnd.events for rnd in ep.rounds)
        analytics = analyze_episode(ep)

        print(f"\n{'=' * 60}")
        print(f"Run: {ep.run_id[:20]} | {'WIN' if ep.won else 'LOSS'} | "
              f"{len(ep.rounds)} rounds | HP {ep.hp_before}->{ep.hp_after} | "
              f"Events: {'YES' if has_events else 'NO'}")

        if analytics.death_cause:
            print(f"Death: {analytics.death_cause} - {analytics.death_detail}")

        if has_events or any(rnd.enemy_powers_snapshot for rnd in ep.rounds):
            text = format_analytics(ep)
            print(text)

        # Sanity checks
        if has_events:
            total_card_dmg = sum(s.total_damage for s in analytics.card_stats)
            total_round_dmg = sum(r.damage_dealt for r in ep.rounds)
            total_tick = sum(analytics.poison_tick_per_round)
            print(f"\n[Sanity] card_dmg={total_card_dmg} + tick={total_tick} "
                  f"vs round_total={total_round_dmg} "
                  f"(diff={total_round_dmg - total_card_dmg - total_tick})")


if __name__ == "__main__":
    main()
