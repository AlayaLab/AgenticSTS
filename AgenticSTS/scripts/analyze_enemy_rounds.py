"""Round-level combat analysis for a specific enemy matchup.

Focuses on per-round patterns rather than whole-combat outcomes so we can
inspect which cards/actions correlate with low-HP-loss turns.

Usage:
    python -m scripts.analyze_enemy_rounds --enemy "Fuzzy Wurm Crawler" --character "the silent"
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

MEMORY_V2 = Path(__file__).resolve().parent.parent / "data" / "memory" / "v2"
EPISODES_PATH = MEMORY_V2 / "combat_episodes.jsonl"


@dataclass(frozen=True)
class RoundRow:
    run_id: str
    episode_id: str
    won: bool
    round_num: int
    hp_before: int
    hp_after: int
    damage_taken: int
    enemy_intents: tuple[str, ...]
    cards_played: tuple[str, ...]


def _load_rows(enemy_key: str, character: str) -> tuple[list[dict], list[RoundRow]]:
    episodes: list[dict] = []
    rows: list[RoundRow] = []
    with EPISODES_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            obj = json.loads(line)
            if obj.get("enemy_key") != enemy_key or obj.get("character") != character:
                continue
            episodes.append(obj)
            for rnd in obj.get("rounds", []):
                rows.append(
                    RoundRow(
                        run_id=obj.get("run_id", ""),
                        episode_id=obj.get("episode_id", ""),
                        won=bool(obj.get("won", False)),
                        round_num=int(rnd.get("round_num", 0)),
                        hp_before=int(rnd.get("hp_start", 0)),
                        hp_after=int(rnd.get("hp_end", 0)),
                        damage_taken=int(rnd.get("damage_taken", 0)),
                        enemy_intents=tuple(rnd.get("enemy_intents", [])),
                        cards_played=tuple(rnd.get("cards_played", [])),
                    )
                )
    return episodes, rows


def _fmt_counter(counter: Counter[str], limit: int = 8) -> str:
    if not counter:
        return "(none)"
    return ", ".join(f"{name}({count})" for name, count in counter.most_common(limit))


def _contains_any(cards: tuple[str, ...], names: set[str]) -> bool:
    return any(card in names for card in cards)


def build_report(enemy_key: str, character: str) -> str:
    episodes, rows = _load_rows(enemy_key, character)
    if not episodes:
        return f"No episodes found for enemy={enemy_key!r}, character={character!r}."

    wins = [ep for ep in episodes if ep.get("won")]
    losses = [ep for ep in episodes if not ep.get("won")]
    low_loss_rows = [r for r in rows if r.damage_taken == 0]
    chip_rows = [r for r in rows if 0 < r.damage_taken <= 3]
    high_loss_rows = [r for r in rows if r.damage_taken >= 6]

    lines: list[str] = []
    lines.append(f"Enemy: {enemy_key} | Character: {character}")
    lines.append(
        f"Episodes: {len(episodes)} total | Wins: {len(wins)} | Losses: {len(losses)}"
    )
    if wins:
        avg_win_hp_loss = sum(ep.get("total_damage_taken", 0) for ep in wins) / len(wins)
        lines.append(f"Average HP loss in wins: {avg_win_hp_loss:.2f}")
    if losses:
        avg_loss_hp_loss = sum(ep.get("total_damage_taken", 0) for ep in losses) / len(losses)
        lines.append(f"Average HP loss in losses: {avg_loss_hp_loss:.2f}")

    lines.append("")
    lines.append("Round buckets:")
    lines.append(f"- Zero-damage rounds: {len(low_loss_rows)}")
    lines.append(f"- Chip-damage rounds (1-3): {len(chip_rows)}")
    lines.append(f"- High-loss rounds (6+): {len(high_loss_rows)}")

    bucket_map = [
        ("Zero-damage rounds", low_loss_rows),
        ("Chip-damage rounds", chip_rows),
        ("High-loss rounds", high_loss_rows),
    ]
    for label, bucket in bucket_map:
        card_counts: Counter[str] = Counter()
        intent_counts: Counter[str] = Counter()
        for row in bucket:
            card_counts.update(row.cards_played)
            intent_counts.update(row.enemy_intents)
        lines.append("")
        lines.append(f"{label}:")
        lines.append(f"- Top cards: {_fmt_counter(card_counts)}")
        lines.append(f"- Top intents: {_fmt_counter(intent_counts)}")

    defend_cards = {"Defend", "Defend+", "Survivor", "Survivor+"}
    weak_cards = {"Neutralize", "Neutralize+", "Sucker Punch", "Sucker Punch+"}
    strike_cards = {"Strike", "Strike+"}

    archetype_buckets: dict[str, list[RoundRow]] = defaultdict(list)
    for row in rows:
        flags: list[str] = []
        if _contains_any(row.cards_played, weak_cards):
            flags.append("weak")
        if _contains_any(row.cards_played, defend_cards):
            flags.append("block")
        if _contains_any(row.cards_played, strike_cards):
            flags.append("strike")
        archetype_buckets["+".join(flags) if flags else "other"].append(row)

    lines.append("")
    lines.append("Per-round card-pattern buckets:")
    for key, bucket in sorted(archetype_buckets.items(), key=lambda item: (-len(item[1]), item[0])):
        avg_taken = sum(r.damage_taken for r in bucket) / len(bucket)
        lines.append(f"- {key}: {len(bucket)} rounds | avg damage taken {avg_taken:.2f}")

    lines.append("")
    lines.append("Lowest-loss winning combats:")
    best_wins = sorted(
        wins,
        key=lambda ep: (ep.get("total_damage_taken", 0), len(ep.get("rounds", [])), ep.get("hp_before", 0)),
    )[:5]
    for ep in best_wins:
        round_summaries = []
        for rnd in ep.get("rounds", []):
            cards = ",".join(rnd.get("cards_played", [])) or "none"
            round_summaries.append(
                f"R{rnd.get('round_num')}[{cards}] -{rnd.get('damage_taken', 0)}"
            )
        lines.append(
            f"- HP {ep.get('hp_before')}→{ep.get('hp_after')} | rounds {len(ep.get('rounds', []))} | "
            + " | ".join(round_summaries[:6])
        )

    if high_loss_rows:
        lines.append("")
        lines.append("Representative high-loss rounds:")
        for row in sorted(high_loss_rows, key=lambda r: (-r.damage_taken, r.round_num, r.run_id))[:5]:
            cards = ", ".join(row.cards_played) or "none"
            intents = "; ".join(row.enemy_intents) or "?"
            lines.append(
                f"- run {row.run_id[:8]} R{row.round_num}: dmg {row.damage_taken}, intents [{intents}], cards [{cards}]"
            )

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze round-level enemy combat patterns.")
    parser.add_argument("--enemy", required=True, help="Enemy key, e.g. 'Fuzzy Wurm Crawler'")
    parser.add_argument("--character", default="the silent", help="Character name")
    args = parser.parse_args()

    print(build_report(args.enemy, args.character))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
