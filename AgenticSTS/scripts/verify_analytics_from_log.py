"""Verify combat analytics by reconstructing episodes from raw log files.

Reads raw JSONL logs (which have full GameState including enemy powers,
hand card rules_text, player powers) and builds CombatRound/CombatEpisode
objects with all new analytics fields populated, then runs format_analytics.

Usage:
    python -m scripts.verify_analytics_from_log                              # Latest Insatiable log
    python -m scripts.verify_analytics_from_log --log logs/run_20260408_074337_017bd579.jsonl
    python -m scripts.verify_analytics_from_log --enemy "Terror Eel"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.combat_analytics import analyze_episode, format_analytics
from src.memory.models_v2 import (
    CombatContext,
    CombatDelta,
    CombatEpisode,
    CombatRound,
    EnemyDelta,
)


def _format_power(p: dict) -> str:
    amt = p.get("amount")
    name = p.get("name", "")
    if amt is not None and amt != 0:
        return f"{name}({amt})"
    return name


def _extract_episodes_from_log(
    log_path: Path, enemy_filter: str = "",
) -> list[CombatEpisode]:
    """Parse raw log and reconstruct episodes with full new fields."""
    # Collect all state events
    states: list[dict] = []
    with open(log_path) as f:
        for line in f:
            d = json.loads(line)
            if d.get("event") == "state" and d.get("combat"):
                states.append(d)

    # Also collect LLM call events for card descriptions
    llm_calls: list[dict] = []
    with open(log_path) as f:
        for line in f:
            d = json.loads(line)
            if d.get("event") == "llm_call":
                llm_calls.append(d)

    # Also collect decision events
    decisions: list[dict] = []
    with open(log_path) as f:
        for line in f:
            d = json.loads(line)
            if d.get("event") == "decision":
                decisions.append(d)

    # Group states by combat encounter (detect by enemy change)
    combats: list[list[dict]] = []
    current_combat: list[dict] = []
    prev_enemies = ""

    for s in states:
        combat = s.get("combat", {})
        enemies = combat.get("enemies", [])
        enemy_names = sorted(e.get("name", "") for e in enemies if e.get("alive", True))
        enemy_key = "+".join(enemy_names) if enemy_names else ""

        if enemy_filter and enemy_filter.lower() not in enemy_key.lower():
            if current_combat:
                combats.append(current_combat)
                current_combat = []
            prev_enemies = ""
            continue

        if enemy_key != prev_enemies:
            if current_combat:
                combats.append(current_combat)
            current_combat = [s]
        else:
            current_combat.append(s)
        prev_enemies = enemy_key

    if current_combat:
        combats.append(current_combat)

    # Convert each combat group into an episode
    episodes: list[CombatEpisode] = []
    for combat_states in combats:
        if not combat_states:
            continue

        ep = _build_episode(combat_states)
        if ep and (not enemy_filter or enemy_filter.lower() in ep.enemy_key.lower()):
            episodes.append(ep)

    return episodes


def _build_episode(combat_states: list[dict]) -> CombatEpisode | None:
    """Build a CombatEpisode from a sequence of state snapshots."""
    if not combat_states:
        return None

    first = combat_states[0]
    last = combat_states[-1]
    combat = first.get("combat", {})
    player = combat.get("player", {})
    enemies = combat.get("enemies", [])

    # Enemy key
    enemy_names = sorted(e.get("name", "") for e in enemies)
    if len(enemy_names) == 1:
        enemy_key = enemy_names[0]
    elif len(enemy_names) > 1:
        enemy_key = "multi:" + "+".join(enemy_names)
    else:
        return None

    # Group by round
    rounds_by_num: dict[int, list[dict]] = {}
    for s in combat_states:
        rnd = s.get("combat", {}).get("round", 0)
        rounds_by_num.setdefault(rnd, []).append(s)

    # Build CombatRounds
    built_rounds: list[CombatRound] = []
    for round_num in sorted(rounds_by_num.keys()):
        round_states = rounds_by_num[round_num]
        cr = _build_round(round_num, round_states)
        if cr:
            built_rounds.append(cr)

    if not built_rounds:
        return None

    hp_before = built_rounds[0].hp_start
    hp_after = last.get("hp", 0)
    won = hp_after > 0

    # Build CombatContext with player_powers
    player_powers: tuple[str, ...] = ()
    if player.get("powers"):
        player_powers = tuple(_format_power(p) for p in player["powers"])

    context = CombatContext(
        enemy_key=enemy_key,
        character=first.get("summary", "").split("|")[2].strip() if "|" in first.get("summary", "") else "",
        combat_type=first.get("combat_type", ""),
        player_powers=player_powers,
    )

    return CombatEpisode(
        run_id=first.get("run_id", ""),
        floor=first.get("floor", 0),
        enemy_key=enemy_key,
        character=context.character,
        combat_type=first.get("combat_type", ""),
        rounds=tuple(built_rounds),
        hp_before=hp_before,
        hp_after=hp_after,
        won=won,
        hp_delta=hp_after - hp_before,
        total_damage_dealt=sum(r.damage_dealt for r in built_rounds),
        total_damage_taken=sum(r.damage_taken for r in built_rounds),
        total_cards_played=sum(len(r.cards_played) for r in built_rounds),
        context=context,
    )


def _build_round(round_num: int, states: list[dict]) -> CombatRound | None:
    """Build a CombatRound from state snapshots within that round."""
    if not states:
        return None

    first_s = states[0]
    last_s = states[-1]
    combat_f = first_s.get("combat", {})
    combat_l = last_s.get("combat", {})

    hp_start = combat_f.get("player", {}).get("hp", 0)
    hp_end = combat_l.get("player", {}).get("hp", 0)

    # Enemy powers snapshot from first state of round
    enemy_powers_snapshot: list[tuple[str, ...]] = []
    for e in combat_f.get("enemies", []):
        powers = e.get("powers", [])
        enemy_powers_snapshot.append(
            tuple(_format_power(p) for p in powers) if powers else ()
        )

    # Build events from state transitions
    events: list[CombatDelta] = []
    cards_played: list[str] = []
    total_enemy_hp_before = sum(e.get("hp", 0) for e in combat_f.get("enemies", []))

    for i in range(len(states)):
        s = states[i]
        combat = s.get("combat", {})
        player = combat.get("player", {})
        hand = player.get("hand", [])

        # Detect card plays by energy change / hand size change
        if i > 0:
            prev_s = states[i - 1]
            prev_combat = prev_s.get("combat", {})
            prev_player = prev_combat.get("player", {})
            prev_hand = prev_player.get("hand", [])

            prev_hand_names = set(c.get("name", "") for c in prev_hand)
            cur_hand_names = set(c.get("name", "") for c in hand)

            # Find which card was played (in prev hand, not in current)
            played = prev_hand_names - cur_hand_names
            if played:
                card_name = next(iter(played))
                # Find the card's rules_text from prev hand
                desc = ""
                for c in prev_hand:
                    if c.get("name") == card_name:
                        desc = c.get("rules_text", "")
                        break

                # Compute enemy HP delta
                enemy_deltas: list[EnemyDelta] = []
                prev_enemies = {e.get("name", ""): e for e in prev_combat.get("enemies", [])}
                cur_enemies = {e.get("name", ""): e for e in combat.get("enemies", [])}
                for ename, prev_e in prev_enemies.items():
                    cur_e = cur_enemies.get(ename)
                    if cur_e:
                        hp_diff = cur_e.get("hp", 0) - prev_e.get("hp", 0)
                        # Check poison changes
                        prev_poisons = {p.get("name", ""): p.get("amount", 0) for p in prev_e.get("powers", [])}
                        cur_poisons = {p.get("name", ""): p.get("amount", 0) for p in cur_e.get("powers", [])}
                        powers_changed: list[str] = []
                        for pname, cur_amt in cur_poisons.items():
                            prev_amt = prev_poisons.get(pname)
                            if prev_amt is None:
                                powers_changed.append(f"+{pname}({cur_amt})")
                            elif cur_amt != prev_amt:
                                powers_changed.append(f"{pname}({prev_amt}→{cur_amt})")

                        if hp_diff != 0 or powers_changed:
                            enemy_deltas.append(EnemyDelta(
                                enemy_id=cur_e.get("enemy_id", ename),
                                name=ename,
                                index=cur_e.get("index", 0),
                                hp=hp_diff if hp_diff != 0 else None,
                                powers_changed=tuple(powers_changed),
                            ))

                # Block delta
                prev_block = prev_player.get("block", 0)
                cur_block = player.get("block", 0)
                block_delta = cur_block - prev_block if cur_block != prev_block else None

                events.append(CombatDelta(
                    event_type="card_play",
                    source=card_name,
                    source_description=desc,
                    block=block_delta,
                    enemy_deltas=tuple(enemy_deltas),
                ))
                cards_played.append(card_name)

    # Compute damage dealt/taken for the round
    total_enemy_hp_after = sum(e.get("hp", 0) for e in combat_l.get("enemies", []))
    damage_dealt = max(0, total_enemy_hp_before - total_enemy_hp_after)
    damage_taken = max(0, hp_start - hp_end)

    return CombatRound(
        round_num=round_num,
        energy_available=combat_f.get("player", {}).get("energy", 0),
        hp_start=hp_start,
        hp_end=hp_end,
        damage_dealt=damage_dealt,
        damage_taken=damage_taken,
        events=tuple(events),
        cards_played=tuple(cards_played),
        hand_at_start=tuple(c.get("name", "") for c in combat_f.get("player", {}).get("hand", [])),
        enemy_powers_snapshot=tuple(tuple(ep) for ep in enemy_powers_snapshot),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify analytics from raw log")
    parser.add_argument("--log", help="Specific log file path")
    parser.add_argument("--enemy", default="insatiable", help="Enemy name filter")
    args = parser.parse_args()

    if args.log:
        log_path = Path(args.log)
    else:
        # Find latest log with the enemy
        log_dir = Path("logs")
        candidates = sorted(log_dir.glob("run_*.jsonl"), reverse=True)
        log_path = None
        for lp in candidates:
            with open(lp) as f:
                content = f.read(100000)
                if args.enemy.lower() in content.lower():
                    log_path = lp
                    break
        if not log_path:
            print(f"No log found containing '{args.enemy}'")
            return

    print(f"Processing: {log_path}")
    episodes = _extract_episodes_from_log(log_path, args.enemy)
    print(f"Reconstructed {len(episodes)} episodes")

    for ep in episodes:
        has_events = any(rnd.events for rnd in ep.rounds)
        analytics = analyze_episode(ep)

        print(f"\n{'=' * 70}")
        print(f"{'WIN' if ep.won else 'LOSS'} | {len(ep.rounds)} rounds | "
              f"HP {ep.hp_before}->{ep.hp_after} | Events: {sum(len(r.events) for r in ep.rounds)}")

        text = format_analytics(ep)
        print(text)

        # Sanity
        if has_events:
            total_card_dmg = sum(s.total_damage for s in analytics.card_stats)
            total_round_dmg = sum(r.damage_dealt for r in ep.rounds)
            total_tick = sum(analytics.poison_tick_per_round)
            print(f"\n[Sanity] card_dmg={total_card_dmg} + tick={total_tick} "
                  f"= {total_card_dmg + total_tick} vs round_total={total_round_dmg}")


if __name__ == "__main__":
    main()
