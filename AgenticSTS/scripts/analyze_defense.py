"""Analyze combat logs for suboptimal defense decisions.

Finds rounds where the agent had enough block cards to fully negate
incoming damage but chose to play attack cards instead, resulting in
unnecessary HP loss.

Usage:
    python -m scripts.analyze_defense [--files N] [--verbose]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


# ── Data models ──────────────────────────────────────────────────

@dataclass(frozen=True)
class HandCard:
    index: int
    name: str
    energy_cost: int
    playable: bool
    block: int | None  # None for non-block cards
    damage: int | None  # None for non-attack cards
    hits: int | None
    total_damage: int | None


@dataclass(frozen=True)
class EnemyIntent:
    name: str
    hp: int
    intent_type: str
    damage: int | None
    hits: int | None
    total_damage: int | None


@dataclass
class RoundStart:
    """Snapshot of the game state at the beginning of a round (first state event)."""
    run_id: str
    floor: int
    combat_round: int
    state_type: str
    enemy_key: str  # e.g. "Seapunk" or "Toadpole+Toadpole"
    player_hp: int
    player_max_hp: int
    player_block: int
    player_energy: int
    max_energy: int
    hand: list[HandCard]
    enemies: list[EnemyIntent]  # flattened: one entry per intent
    total_incoming: int  # sum of all attack intent total_damage


@dataclass
class RoundOutcome:
    """What actually happened during the round (from combat_summary or next round state)."""
    hp_start: int
    hp_end: int
    damage_taken: int
    block_gained: int
    cards_played: list[str]
    energy_used: int


@dataclass
class SuboptimalDefenseCase:
    """A round where full block was possible but not used."""
    run_id: str
    floor: int
    combat_round: int
    enemy_key: str
    state_type: str
    total_incoming: int
    available_block: int  # total block from all block cards in hand
    block_energy_cost: int  # energy needed to play enough block cards
    player_energy: int
    existing_block: int  # block already on player at round start
    block_deficit: int  # incoming - existing_block
    # What block cards could have covered the deficit
    sufficient_block_combos: list[list[str]]  # card name lists
    # What actually happened
    cards_played: list[str]
    attack_cards_played: list[str]
    block_cards_played: list[str]
    block_gained: int
    hp_before: int
    hp_after: int
    hp_lost: int
    reasoning: str  # LLM reasoning excerpt


# ── Parsing helpers ──────────────────────────────────────────────

def parse_hand_card(c: dict) -> HandCard:
    return HandCard(
        index=c.get("index", 0),
        name=c.get("name", ""),
        energy_cost=c.get("energy_cost", 0) or 0,
        playable=c.get("playable", False),
        block=c.get("block"),
        damage=c.get("damage"),
        hits=c.get("hits"),
        total_damage=c.get("total_damage"),
    )


def parse_enemy_intents(enemies: list[dict]) -> tuple[list[EnemyIntent], int]:
    """Parse enemies into flattened intent list and total incoming damage."""
    intents: list[EnemyIntent] = []
    total_incoming = 0
    for e in enemies:
        for i in e.get("intents", []):
            intent = EnemyIntent(
                name=e.get("name", ""),
                hp=e.get("hp", 0),
                intent_type=i.get("type", ""),
                damage=i.get("damage"),
                hits=i.get("hits"),
                total_damage=i.get("total_damage"),
            )
            intents.append(intent)
            if i.get("type") == "Attack" and i.get("total_damage"):
                total_incoming += i["total_damage"]
            elif i.get("type") == "Attack" and i.get("damage"):
                # Fallback: damage * (hits or 1)
                total_incoming += i["damage"] * (i.get("hits") or 1)
    return intents, total_incoming


def compute_available_block(hand: list[HandCard], energy: int) -> tuple[int, int, list[list[str]]]:
    """Compute total available block and find combos that could cover incoming.

    Returns:
        (total_block, min_energy_for_all_block, list_of_block_card_names)
    """
    block_cards = [c for c in hand if c.block and c.block > 0 and c.playable]
    total_block = sum(c.block for c in block_cards)
    total_energy = sum(c.energy_cost for c in block_cards)
    # Sort by efficiency (block per energy, with 0-cost first)
    sorted_cards = sorted(block_cards, key=lambda c: (c.energy_cost, -c.block))
    combos = [[c.name for c in sorted_cards]]  # all block cards
    return total_block, total_energy, combos


def find_minimal_block_combos(
    hand: list[HandCard],
    energy: int,
    deficit: int,
) -> list[list[str]]:
    """Find minimal sets of block cards that cover the deficit within energy budget.

    Uses a greedy approach: sort by block/energy efficiency, pick until deficit covered.
    Returns up to 3 different orderings to show options.
    """
    if deficit <= 0:
        return [[]]  # no block needed

    block_cards = [c for c in hand if c.block and c.block > 0 and c.playable]
    if not block_cards:
        return []

    results: list[list[str]] = []

    # Strategy 1: Most block per energy (efficiency)
    sorted_by_eff = sorted(block_cards, key=lambda c: (-c.block / max(c.energy_cost, 0.1), c.energy_cost))
    combo = _greedy_pick(sorted_by_eff, energy, deficit)
    if combo:
        results.append(combo)

    # Strategy 2: Cheapest first (save energy)
    sorted_by_cost = sorted(block_cards, key=lambda c: (c.energy_cost, -c.block))
    combo = _greedy_pick(sorted_by_cost, energy, deficit)
    if combo and combo not in results:
        results.append(combo)

    # Strategy 3: Fewest cards
    sorted_by_block = sorted(block_cards, key=lambda c: -c.block)
    combo = _greedy_pick(sorted_by_block, energy, deficit)
    if combo and combo not in results:
        results.append(combo)

    return results


def _greedy_pick(cards: list[HandCard], energy: int, deficit: int) -> list[str] | None:
    """Greedily pick cards until deficit is covered or energy runs out."""
    picked: list[str] = []
    remaining_energy = energy
    remaining_deficit = deficit
    for c in cards:
        if remaining_deficit <= 0:
            break
        if c.energy_cost <= remaining_energy:
            picked.append(c.name)
            remaining_energy -= c.energy_cost
            remaining_deficit -= (c.block or 0)
    return picked if remaining_deficit <= 0 else None


def classify_card(name: str, hand: list[HandCard]) -> str:
    """Classify a played card as attack/block/other based on hand data."""
    for c in hand:
        if c.name == name:
            if c.block and c.block > 0 and (c.damage is None or c.damage == 0):
                return "block"
            elif c.damage and c.damage > 0 and (c.block is None or c.block == 0):
                return "attack"
            elif c.block and c.damage:
                return "hybrid"
            else:
                return "other"
    # Fallback heuristics
    lower = name.lower()
    block_keywords = ["defend", "block", "deflect", "survivor", "backflip", "footwork", "dodge"]
    attack_keywords = ["strike", "stab", "slash", "throw", "claw", "bash"]
    if any(kw in lower for kw in block_keywords):
        return "block"
    if any(kw in lower for kw in attack_keywords):
        return "attack"
    return "other"


# ── Main analysis ────────────────────────────────────────────────

def load_log_events(path: Path) -> list[dict]:
    """Load all events from a JSONL log file."""
    events: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def analyze_log_file(path: Path) -> list[SuboptimalDefenseCase]:
    """Analyze a single log file for suboptimal defense decisions."""
    events = load_log_events(path)
    run_id = path.stem.replace("run_", "")
    cases: list[SuboptimalDefenseCase] = []

    # Phase 1: Collect round-start states (first state event per combat round)
    # Key = (floor, round) → RoundStart
    round_starts: dict[tuple[int, int], RoundStart] = {}
    # Track which (floor, round) we've already seen
    seen_rounds: set[tuple[int, int]] = set()

    for ev in events:
        if ev.get("event") != "state":
            continue
        combat = ev.get("combat")
        if not combat:
            continue
        if not combat.get("is_play_phase"):
            continue
        player = combat.get("player", {})
        hand_data = player.get("hand", [])
        enemies_data = combat.get("enemies", [])
        if not hand_data or not enemies_data:
            continue

        floor = ev.get("floor", 0)
        rnd = combat.get("round", 0)
        key = (floor, rnd)

        # Only take the first state per round (full hand, before any plays)
        if key in seen_rounds:
            continue
        seen_rounds.add(key)

        hand = [parse_hand_card(c) for c in hand_data]
        intents, total_incoming = parse_enemy_intents(enemies_data)

        # Build enemy_key
        enemy_names = list(dict.fromkeys(e.get("name", "") for e in enemies_data))
        enemy_key = "+".join(enemy_names) if len(enemy_names) > 1 else (enemy_names[0] if enemy_names else "Unknown")

        round_starts[key] = RoundStart(
            run_id=run_id,
            floor=floor,
            combat_round=rnd,
            state_type=ev.get("state_type", ""),
            enemy_key=enemy_key,
            player_hp=player.get("hp", 0),
            player_max_hp=player.get("max_hp", 0),
            player_block=player.get("block", 0),
            player_energy=player.get("energy", 0),
            max_energy=player.get("max_energy", 0),
            hand=hand,
            enemies=intents,
            total_incoming=total_incoming,
        )

    # Phase 2: Collect round outcomes from combat_summary
    round_outcomes: dict[tuple[int, int], RoundOutcome] = {}
    for ev in events:
        if ev.get("event") != "combat_summary":
            continue
        floor = ev.get("floor", 0)
        for r in ev.get("rounds", []):
            rnd = r.get("round", 0)
            key = (floor, rnd)
            round_outcomes[key] = RoundOutcome(
                hp_start=r.get("hp_start", 0),
                hp_end=r.get("hp_end", 0),
                damage_taken=r.get("damage_taken", 0),
                block_gained=r.get("block_gained", 0),
                cards_played=r.get("cards_played", []),
                energy_used=r.get("energy_used", 0),
            )

    # Phase 3: Collect decision reasoning per (floor, round)
    # Use the first decision per round that has a plan reasoning
    round_reasoning: dict[tuple[int, int], str] = {}
    for ev in events:
        if ev.get("event") != "decision":
            continue
        if ev.get("state_type") not in ("monster", "elite", "boss"):
            continue
        floor = ev.get("floor", 0)
        reasoning = ev.get("reasoning", "")

        # Match to round via step correlation
        # Find which round this step belongs to
        matched_round = None
        for (f, r), rs in round_starts.items():
            if f == floor:
                if matched_round is None or r > matched_round:
                    # Check if this step could belong to this round
                    # We just take the latest round for this floor that we've seen
                    matched_round = r
        # Better approach: use the round_starts keys sorted and find which round
        # contains this step
        # For simplicity, extract the round from the state at or just before this step
        for (f, r), rs in round_starts.items():
            if f == floor:
                key = (f, r)
                if key not in round_reasoning and reasoning:
                    # We'll collect all reasonings per floor and assign to rounds later
                    pass

    # Simpler reasoning collection: get first decision reasoning per (floor, round)
    # by tracking the round from concurrent state events
    current_combat_floor = 0
    current_combat_round = 0
    for ev in events:
        if ev.get("event") == "state" and ev.get("combat"):
            current_combat_floor = ev.get("floor", 0)
            current_combat_round = ev["combat"].get("round", 0)
        elif ev.get("event") == "decision" and ev.get("state_type") in ("monster", "elite", "boss"):
            key = (current_combat_floor, current_combat_round)
            if key not in round_reasoning:
                reasoning = ev.get("reasoning", "")
                if reasoning:
                    round_reasoning[key] = reasoning

    # Phase 4: Find suboptimal defense rounds
    for key, rs in round_starts.items():
        outcome = round_outcomes.get(key)
        if not outcome:
            continue

        # Skip rounds with no incoming damage
        if rs.total_incoming <= 0:
            continue

        # Skip rounds where no damage was taken
        if outcome.damage_taken <= 0:
            continue

        # Compute the block deficit (incoming minus existing block)
        block_deficit = rs.total_incoming - rs.player_block
        if block_deficit <= 0:
            continue  # existing block already covers it

        # Compute available block from hand
        total_block, block_energy, _ = compute_available_block(rs.hand, rs.player_energy)

        # Could full block have been achieved?
        # total_block (from playable block cards) + existing block >= incoming
        if total_block + rs.player_block < rs.total_incoming:
            continue  # not enough block cards in hand

        # Check if we had enough energy to play sufficient block cards
        combos = find_minimal_block_combos(rs.hand, rs.player_energy, block_deficit)
        if not combos:
            continue  # can't afford enough block within energy

        # This is a case where full block was possible!
        # Now check what was actually played
        cards_played = outcome.cards_played
        attack_cards = [c for c in cards_played if classify_card(c, rs.hand) == "attack"]
        block_cards = [c for c in cards_played if classify_card(c, rs.hand) in ("block", "hybrid")]

        # Only flag if attack cards were played (agent chose offense over defense)
        if not attack_cards:
            continue

        reasoning = round_reasoning.get(key, "(no reasoning captured)")

        case = SuboptimalDefenseCase(
            run_id=rs.run_id,
            floor=rs.floor,
            combat_round=rs.combat_round,
            enemy_key=rs.enemy_key,
            state_type=rs.state_type,
            total_incoming=rs.total_incoming,
            available_block=total_block + rs.player_block,
            block_energy_cost=block_energy,
            player_energy=rs.player_energy,
            existing_block=rs.player_block,
            block_deficit=block_deficit,
            sufficient_block_combos=combos,
            cards_played=cards_played,
            attack_cards_played=attack_cards,
            block_cards_played=block_cards,
            block_gained=outcome.block_gained,
            hp_before=outcome.hp_start,
            hp_after=outcome.hp_end,
            hp_lost=outcome.damage_taken,
            reasoning=reasoning,
        )
        cases.append(case)

    return cases


def get_recent_log_files(n: int = 10) -> list[Path]:
    """Get the N most recent log files from today (March 26, 2026)."""
    if not LOG_DIR.exists():
        return []
    files = sorted(LOG_DIR.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Filter to today's files (March 26, 2026) — check file modification time
    from datetime import datetime
    today_files = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime.date() == datetime.now().date():
            today_files.append(f)
    # Fall back to most recent if no today files
    target = today_files if today_files else files
    return target[:n]


def format_case(case: SuboptimalDefenseCase, verbose: bool = False) -> str:
    """Format a SuboptimalDefenseCase for display."""
    lines = []
    lines.append(f"  Run: {case.run_id}  Floor: {case.floor}  Round: {case.combat_round}")
    lines.append(f"  Enemy: {case.enemy_key} ({case.state_type})")
    lines.append(f"  Incoming damage: {case.total_incoming}  |  Available block: {case.available_block} "
                  f"(existing: {case.existing_block}, hand: {case.available_block - case.existing_block})")
    lines.append(f"  Energy: {case.player_energy}  |  Block deficit: {case.block_deficit}")
    lines.append(f"  Block combos that would have covered: {case.sufficient_block_combos}")
    lines.append(f"  Actually played: {case.cards_played}")
    lines.append(f"  - Attack cards: {case.attack_cards_played}")
    lines.append(f"  - Block cards:  {case.block_cards_played}")
    lines.append(f"  Block gained: {case.block_gained}  |  HP: {case.hp_before} -> {case.hp_after} "
                  f"(lost {case.hp_lost})")
    # Reasoning excerpt (truncated)
    reasoning = case.reasoning
    if len(reasoning) > 300 and not verbose:
        reasoning = reasoning[:300] + "..."
    lines.append(f"  Reasoning: {reasoning}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze combat logs for suboptimal defense decisions")
    parser.add_argument("--files", type=int, default=10, help="Number of recent log files to analyze")
    parser.add_argument("--verbose", action="store_true", help="Show full reasoning text")
    parser.add_argument("--all-dates", action="store_true", help="Include logs from all dates, not just today")
    args = parser.parse_args()

    if args.all_dates:
        files = sorted(LOG_DIR.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:args.files]
    else:
        files = get_recent_log_files(args.files)

    if not files:
        print("No log files found.")
        sys.exit(1)

    print(f"Analyzing {len(files)} log files...\n")

    all_cases: list[SuboptimalDefenseCase] = []
    total_combat_rounds = 0
    total_damage_rounds = 0

    for f in files:
        events = load_log_events(f)
        # Count combat rounds in this file
        seen: set[tuple[int, int]] = set()
        damage_rounds = 0
        for ev in events:
            if ev.get("event") == "combat_summary":
                for r in ev.get("rounds", []):
                    key = (ev.get("floor", 0), r.get("round", 0))
                    if key not in seen:
                        seen.add(key)
                        total_combat_rounds += 1
                        if r.get("damage_taken", 0) > 0:
                            damage_rounds += 1
                            total_damage_rounds += 1

        cases = analyze_log_file(f)
        if cases:
            all_cases.extend(cases)

    # ── Summary ──────────────────────────────────────────────────
    print("=" * 72)
    print("SUBOPTIMAL DEFENSE ANALYSIS")
    print("=" * 72)
    print(f"Log files analyzed:      {len(files)}")
    print(f"Total combat rounds:     {total_combat_rounds}")
    print(f"Rounds with HP loss:     {total_damage_rounds}")
    print(f"Suboptimal defense:      {len(all_cases)}")
    if total_damage_rounds > 0:
        pct = len(all_cases) / total_damage_rounds * 100
        print(f"  (% of HP-loss rounds): {pct:.1f}%")
    total_hp_lost = sum(c.hp_lost for c in all_cases)
    print(f"Total preventable HP:    {total_hp_lost}")
    print()

    if not all_cases:
        print("No suboptimal defense cases found.")
        return

    # ── Per-case details ─────────────────────────────────────────
    # Sort by HP lost (worst first)
    all_cases.sort(key=lambda c: -c.hp_lost)

    print("-" * 72)
    print("CASES (sorted by HP lost, worst first)")
    print("-" * 72)
    for i, case in enumerate(all_cases, 1):
        print(f"\n[{i}]")
        print(format_case(case, verbose=args.verbose))

    # ── Aggregation by enemy ─────────────────────────────────────
    print("\n" + "-" * 72)
    print("AGGREGATION BY ENEMY")
    print("-" * 72)
    enemy_stats: dict[str, dict[str, Any]] = {}
    for c in all_cases:
        key = c.enemy_key
        if key not in enemy_stats:
            enemy_stats[key] = {"count": 0, "total_hp_lost": 0, "floors": []}
        enemy_stats[key]["count"] += 1
        enemy_stats[key]["total_hp_lost"] += c.hp_lost
        enemy_stats[key]["floors"].append(c.floor)

    for enemy, stats in sorted(enemy_stats.items(), key=lambda x: -x[1]["total_hp_lost"]):
        print(f"  {enemy}: {stats['count']} rounds, {stats['total_hp_lost']} HP lost "
              f"(floors: {stats['floors']})")

    # ── Common patterns ──────────────────────────────────────────
    print("\n" + "-" * 72)
    print("COMMON PATTERNS IN REASONING")
    print("-" * 72)
    # Look for common phrases in reasoning
    kill_oriented = sum(1 for c in all_cases if any(kw in c.reasoning.lower() for kw in
                        ["kill", "lethal", "finish", "finish off", "damage total"]))
    hp_fine = sum(1 for c in all_cases if any(kw in c.reasoning.lower() for kw in
                  ["fine at", "safe at", "acceptable", "can take"]))
    tempo = sum(1 for c in all_cases if any(kw in c.reasoning.lower() for kw in
                ["tempo", "pressure", "aggressive", "front-loaded"]))
    no_block_needed = sum(1 for c in all_cases if any(kw in c.reasoning.lower() for kw in
                          ["no block needed", "no need for block", "don't need block"]))

    print(f"  Kill-oriented reasoning:     {kill_oriented}/{len(all_cases)}")
    print(f"  'HP is fine' reasoning:      {hp_fine}/{len(all_cases)}")
    print(f"  Tempo/aggressive reasoning:  {tempo}/{len(all_cases)}")
    print(f"  'No block needed' reasoning: {no_block_needed}/{len(all_cases)}")

    # ── State type breakdown ─────────────────────────────────────
    print("\n" + "-" * 72)
    print("BY COMBAT TYPE")
    print("-" * 72)
    type_stats: dict[str, dict[str, int]] = {}
    for c in all_cases:
        st = c.state_type
        if st not in type_stats:
            type_stats[st] = {"count": 0, "hp_lost": 0}
        type_stats[st]["count"] += 1
        type_stats[st]["hp_lost"] += c.hp_lost
    for st, stats in sorted(type_stats.items(), key=lambda x: -x[1]["hp_lost"]):
        print(f"  {st}: {stats['count']} rounds, {stats['hp_lost']} HP lost")


if __name__ == "__main__":
    main()
