"""Combat analytics: extract rich insights from CombatEpisode events.

Pure computation module — no I/O, no LLM calls. Converts raw CombatDelta
event data into structured analytics for post-run LLM consumption.

Covers:
- Death cause detection (HP damage vs Sandpit timer vs other mechanic)
- Per-card damage/block/poison attribution
- Per-round unattributed damage (poison ticks, power effects)
- Token source attribution (Blade Dance vs Infinite Blades Shivs)
- Enemy power timeline (Sandpit countdown, Strength scaling)
- Card descriptions for indirect effect reasoning
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.memory.enemy_keys import enemy_key_lookup
from src.memory.models_v2 import CombatEpisode

# ── Data Models ──────────────────────────────────────────────


@dataclass(frozen=True)
class CardStats:
    """Aggregated stats for a single card across the fight."""

    name: str = ""
    description: str = ""           # rules_text
    plays: int = 0
    total_damage: int = 0           # sum of enemy HP deltas
    total_block: int = 0            # player block gained
    poison_stacks_applied: int = 0  # sum of Poison delta
    exhausts: bool = False          # "Exhaust" in description
    tokens_generated: int = 0       # parsed from "Add N Shivs" etc.


@dataclass(frozen=True)
class CombatAnalytics:
    """Rich analytics extracted from a single CombatEpisode."""

    death_cause: str = ""           # "hp_damage" | "sandpit" | "mechanic" | ""
    death_detail: str = ""
    card_stats: tuple[CardStats, ...] = ()
    poison_by_card: tuple[tuple[str, int], ...] = ()   # (card_name, stacks)
    poison_tick_per_round: tuple[int, ...] = ()
    enemy_power_timeline: tuple[dict[str, str], ...] = ()
    unique_cards_with_desc: tuple[tuple[str, str], ...] = ()
    active_powers: tuple[str, ...] = ()


# ── Poison Parsing ───────────────────────────────────────────

_RE_POISON_NEW = re.compile(r"\+Poison\((\d+)\)")
_RE_POISON_CHANGE = re.compile(r"Poison\((\d+)→(\d+)\)")
_RE_TOKEN_GEN = re.compile(r"Add (\d+) Shivs?", re.IGNORECASE)


def _parse_poison_delta(power_str: str) -> int:
    """Parse poison stacks added from a powers_changed entry."""
    m = _RE_POISON_NEW.match(power_str)
    if m:
        return int(m.group(1))
    m = _RE_POISON_CHANGE.match(power_str)
    if m:
        return max(0, int(m.group(2)) - int(m.group(1)))
    return 0


def _parse_token_count(description: str) -> int:
    """Parse token generation count from rules_text."""
    m = _RE_TOKEN_GEN.search(description)
    return int(m.group(1)) if m else 0


# ── Power Snapshot Parsing ───────────────────────────────────

_RE_POWER_VALUE = re.compile(r"^(.+?)\((-?\d+)\)$")


def _parse_power_snapshot(
    snapshot: tuple[tuple[str, ...], ...],
) -> dict[str, str]:
    """Extract power name→value map from enemy_powers_snapshot.

    Merges all enemies into one dict. For multi-enemy fights, prefixes
    with enemy index if the same power name appears on multiple enemies.
    Powers without numeric amounts (binary flags) are stored as "on".
    """
    from collections import Counter

    # Pre-pass: count how many enemies have each power name
    name_count: Counter[str] = Counter()
    for powers in snapshot:
        for p in powers:
            m = _RE_POWER_VALUE.match(p)
            name_count[m.group(1) if m else p] += 1

    result: dict[str, str] = {}
    for idx, powers in enumerate(snapshot):
        for p in powers:
            m = _RE_POWER_VALUE.match(p)
            if m:
                name, val = m.group(1), m.group(2)
                key = f"{name}[{idx}]" if name_count[name] > 1 else name
                result[key] = val
            else:
                # Binary flag power (no numeric amount)
                key = f"{p}[{idx}]" if name_count[p] > 1 else p
                result[key] = "on"
    return result


# ── Death Cause Detection ────────────────────────────────────


def detect_death_cause(episode: CombatEpisode) -> tuple[str, str]:
    """Determine how the agent died.

    Returns (cause, detail) where cause is one of:
    - "": not a death (won or hp_after > 0)
    - "hp_damage": killed by enemy damage
    - "sandpit": killed by Sandpit death timer
    - "mechanic": killed by unknown mechanic (HP was healthy)
    """
    if episode.is_aborted:
        return ("", "")

    if episode.won or episode.hp_after > 0:
        return ("", "")

    if not episode.rounds:
        return ("hp_damage", "No round data available.")

    last = episode.rounds[-1]

    # Check Sandpit FIRST — it kills regardless of HP, so even if
    # damage was also taken, Sandpit reaching 0 is the true cause.
    if last.enemy_powers_snapshot:
        for powers in last.enemy_powers_snapshot:
            for p in powers:
                if "Sandpit" in p:
                    return (
                        "sandpit",
                        f"Sandpit timer reached 0. "
                        f"HP was {last.hp_start} when killed.",
                    )

    # No Sandpit — check if HP damage explains the death
    if last.hp_start <= last.damage_taken + 5:
        return (
            "hp_damage",
            f"Killed by damage. HP {last.hp_start} -> 0, "
            f"took {last.damage_taken} damage.",
        )

    return (
        "mechanic",
        f"Died with HP={last.hp_start}, "
        f"damage_taken={last.damage_taken}. Likely mechanic kill.",
    )


# ── Per-Card Stats ───────────────────────────────────────────


def compute_card_stats(episode: CombatEpisode) -> tuple[CardStats, ...]:
    """Aggregate per-card damage, block, poison, and metadata."""
    acc: dict[str, dict[str, Any]] = {}

    for rnd in episode.rounds:
        for ev in rnd.events:
            if ev.event_type not in ("card_play", "potion_use"):
                continue

            name = ev.source
            if not name:
                continue

            if name not in acc:
                desc = ev.source_description or ""
                acc[name] = {
                    "plays": 0,
                    "damage": 0,
                    "block": 0,
                    "poison": 0,
                    "desc": desc,
                    "exhausts": "Exhaust" in desc,
                    "tokens": _parse_token_count(desc),
                }
            else:
                # Update description if we didn't have one before
                if not acc[name]["desc"] and ev.source_description:
                    desc = ev.source_description
                    acc[name]["desc"] = desc
                    acc[name]["exhausts"] = "Exhaust" in desc
                    acc[name]["tokens"] = _parse_token_count(desc)

            entry = acc[name]
            if ev.event_type == "card_play":
                entry["plays"] += 1

            # Damage from enemy HP deltas
            for ed in ev.enemy_deltas:
                if ed.hp is not None and ed.hp < 0:
                    entry["damage"] += abs(ed.hp)
                # Poison stacks
                for p in ed.powers_changed:
                    stacks = _parse_poison_delta(p)
                    if stacks > 0:
                        entry["poison"] += stacks

            # Block from player delta
            if ev.block is not None and ev.block > 0:
                entry["block"] += ev.block

    return tuple(
        CardStats(
            name=name,
            description=data["desc"],
            plays=data["plays"],
            total_damage=data["damage"],
            total_block=data["block"],
            poison_stacks_applied=data["poison"],
            exhausts=data["exhausts"],
            tokens_generated=data["tokens"],
        )
        for name, data in sorted(acc.items(), key=lambda x: -x[1]["damage"])
    )


# ── Poison Tracking ──────────────────────────────────────────


def compute_poison_tracking(
    episode: CombatEpisode,
) -> tuple[tuple[str, int], ...]:
    """Per-card poison stacks applied across the fight."""
    poison_map: dict[str, int] = {}
    for rnd in episode.rounds:
        for ev in rnd.events:
            if not ev.source:
                continue
            for ed in ev.enemy_deltas:
                for p in ed.powers_changed:
                    stacks = _parse_poison_delta(p)
                    if stacks > 0:
                        poison_map[ev.source] = poison_map.get(ev.source, 0) + stacks

    return tuple(sorted(poison_map.items(), key=lambda x: -x[1]))


def compute_poison_tick_per_round(
    episode: CombatEpisode,
) -> tuple[int, ...]:
    """Per-round unattributed damage (poison ticks + power effects).

    Computed as: round.damage_dealt - sum(event enemy HP deltas).
    """
    ticks: list[int] = []
    for rnd in episode.rounds:
        event_dmg = 0
        for ev in rnd.events:
            for ed in ev.enemy_deltas:
                if ed.hp is not None and ed.hp < 0:
                    event_dmg += abs(ed.hp)
        tick = max(0, rnd.damage_dealt - event_dmg)
        ticks.append(tick)
    return tuple(ticks)


# ── Enemy Power Timeline ────────────────────────────────────


def compute_enemy_power_timeline(
    episode: CombatEpisode,
) -> tuple[dict[str, str], ...]:
    """Per-round enemy power values from snapshots."""
    timeline: list[dict[str, str]] = []
    for rnd in episode.rounds:
        if rnd.enemy_powers_snapshot:
            timeline.append(_parse_power_snapshot(rnd.enemy_powers_snapshot))
        else:
            timeline.append({})
    return tuple(timeline)


# ── Token Attribution ────────────────────────────────────────


def compute_token_attribution(
    episode: CombatEpisode,
    active_powers: tuple[str, ...] = (),
) -> dict[str, dict[str, int]]:
    """Attribute token plays (Shivs) to generator sources.

    Returns {generator_name: {"generated": N, "attributed_damage": D}}.
    """
    ib_active = any("Infinite Blades" in p for p in active_powers)

    result: dict[str, dict[str, int]] = {}
    total_shiv_damage = 0
    total_shiv_plays = 0

    for rnd in episode.rounds:
        round_generators: dict[str, int] = {}
        round_shiv_plays = 0
        round_shiv_damage = 0

        # Start-of-turn generators
        if ib_active:
            round_generators["Infinite Blades"] = (
                round_generators.get("Infinite Blades", 0) + 1
            )

        for ev in rnd.events:
            if ev.event_type != "card_play":
                continue
            name = ev.source
            desc = ev.source_description or ""

            # Check if this card generates tokens
            token_count = _parse_token_count(desc)
            if token_count > 0:
                round_generators[name] = (
                    round_generators.get(name, 0) + token_count
                )

            # Count Shiv plays and damage
            if name in ("Shiv", "Shiv+"):
                round_shiv_plays += 1
                for ed in ev.enemy_deltas:
                    if ed.hp is not None and ed.hp < 0:
                        round_shiv_damage += abs(ed.hp)

        total_shiv_plays += round_shiv_plays
        total_shiv_damage += round_shiv_damage

        # Attribute Shivs to generators by declared count
        remaining = round_shiv_plays
        for gen_name, gen_count in round_generators.items():
            attributed = min(gen_count, remaining)
            if attributed > 0:
                if gen_name not in result:
                    result[gen_name] = {"generated": 0, "attributed_damage": 0}
                result[gen_name]["generated"] += attributed
                remaining -= attributed

        if remaining > 0:
            if "other" not in result:
                result["other"] = {"generated": 0, "attributed_damage": 0}
            result["other"]["generated"] += remaining

    # Distribute damage proportionally
    if total_shiv_plays > 0 and total_shiv_damage > 0:
        avg_shiv_dmg = total_shiv_damage / total_shiv_plays
        for gen_data in result.values():
            gen_data["attributed_damage"] = round(gen_data["generated"] * avg_shiv_dmg)

    return result


# ── Main Analyzer ────────────────────────────────────────────


def analyze_episode(episode: CombatEpisode) -> CombatAnalytics:
    """Run full analytics on a single episode."""
    has_events = any(rnd.events for rnd in episode.rounds)
    has_power_snapshots = any(rnd.enemy_powers_snapshot for rnd in episode.rounds)
    death_cause, death_detail = detect_death_cause(episode)

    if not has_events and not has_power_snapshots:
        return CombatAnalytics(death_cause=death_cause, death_detail=death_detail)

    card_stats = compute_card_stats(episode)
    poison_tracking = compute_poison_tracking(episode)
    tick_per_round = compute_poison_tick_per_round(episode)
    timeline = compute_enemy_power_timeline(episode)

    # Collect unique cards with descriptions
    cards_seen: dict[str, str] = {}
    for rnd in episode.rounds:
        for ev in rnd.events:
            if ev.event_type == "card_play" and ev.source and ev.source not in cards_seen:
                cards_seen[ev.source] = ev.source_description or ""

    # Active powers from CombatContext
    active_powers: tuple[str, ...] = ()
    if episode.context and episode.context.player_powers:
        active_powers = episode.context.player_powers

    return CombatAnalytics(
        death_cause=death_cause,
        death_detail=death_detail,
        card_stats=card_stats,
        poison_by_card=poison_tracking,
        poison_tick_per_round=tick_per_round,
        enemy_power_timeline=timeline,
        unique_cards_with_desc=tuple(cards_seen.items()),
        active_powers=active_powers,
    )


# ── Text Formatter ───────────────────────────────────────────


def historical_comparison(
    episode: CombatEpisode,
    all_episodes: list[CombatEpisode],
) -> str | None:
    """Compare episode HP loss to historical average for the same enemy.

    Returns a one-line comparison string, or None if insufficient data (< 3 history).
    Uses z-score: (loss - mean) / std.  Labels: BETTER_THAN_USUAL / WORSE_THAN_USUAL / TYPICAL.
    """
    import math

    enemy_lower = enemy_key_lookup(episode.enemy_key)
    def _hp_loss(ep: CombatEpisode) -> int:
        """Compute HP loss, preferring hp_before/hp_after over hp_delta."""
        if ep.hp_before > 0:
            return max(0, ep.hp_before - ep.hp_after)
        return max(0, -ep.hp_delta)

    historical = [
        ep for ep in all_episodes
        if enemy_key_lookup(ep.enemy_key) == enemy_lower
        and ep.episode_id != episode.episode_id
        and ep.run_id != episode.run_id  # exclude same-run to avoid self-skewing
        and not ep.is_aborted
    ]
    if len(historical) < 3:
        return None

    losses = [_hp_loss(ep) for ep in historical]
    mean = sum(losses) / len(losses)
    variance = sum((x - mean) ** 2 for x in losses) / len(losses)
    std = math.sqrt(variance)
    if std == 0:
        return None

    this_loss = _hp_loss(episode)
    z = (this_loss - mean) / std

    if z > 1.5:
        label = "WORSE_THAN_USUAL"
    elif z < -1.0 and mean > 5:
        label = "BETTER_THAN_USUAL"
    else:
        label = "TYPICAL"

    return (
        f"loss={this_loss} vs historical avg={mean:.1f}+/-{std:.1f} "
        f"(z={z:.1f}, {label}, n={len(historical)})"
    )


def format_analytics(episode: CombatEpisode) -> str:
    """Format episode analytics as text for LLM consumption."""
    analytics = analyze_episode(episode)
    result_str = "WIN" if episode.won else "LOSS"
    lines: list[str] = []
    lines.append(
        f"## Combat Analytics: {episode.enemy_key} "
        f"({result_str} - {len(episode.rounds)} rounds)"
    )

    # Death cause
    if analytics.death_cause:
        lines.append(f"Death cause: {analytics.death_detail}")

    # Cards played with descriptions
    if analytics.unique_cards_with_desc:
        lines.append("\nCards played (with descriptions):")
        for name, desc in analytics.unique_cards_with_desc:
            stat = next((s for s in analytics.card_stats if s.name == name), None)
            parts: list[str] = []
            if stat:
                parts.append(f"{stat.plays} plays")
                if stat.total_damage > 0:
                    parts.append(f"{stat.total_damage} dmg")
                if stat.total_block > 0:
                    parts.append(f"{stat.total_block} block")
                if stat.poison_stacks_applied > 0:
                    parts.append(f"+{stat.poison_stacks_applied} poison")
                if stat.exhausts:
                    parts.append("EXHAUST")
                if stat.tokens_generated > 0:
                    parts.append(f"generates {stat.tokens_generated} Shivs")
            stat_str = ", ".join(parts) if parts else ""
            desc_str = f' "{desc}"' if desc else ""
            lines.append(f"  {name}{desc_str} -> {stat_str}")

    # Active player powers
    if analytics.active_powers:
        lines.append(f"\nActive powers: {', '.join(analytics.active_powers)}")

    # Token attribution
    active_powers = analytics.active_powers
    token_attr = compute_token_attribution(episode, active_powers)
    if token_attr:
        lines.append("\nToken attribution (Shivs):")
        for gen_name, data in sorted(
            token_attr.items(), key=lambda x: -x[1]["attributed_damage"]
        ):
            lines.append(
                f"  {gen_name}: {data['generated']} Shivs -> ~{data['attributed_damage']} dmg"
            )

    # Poison tracking
    if analytics.poison_by_card:
        lines.append("\nPoison stacks applied per card:")
        for card_name, stacks in analytics.poison_by_card:
            lines.append(f"  {card_name}: {stacks} stacks")
        total_tick = sum(analytics.poison_tick_per_round)
        if total_tick > 0:
            tick_parts = [
                f"R{i + 1}:{t}"
                for i, t in enumerate(analytics.poison_tick_per_round)
                if t > 0
            ]
            lines.append(f"Total poison/power tick damage: {total_tick}")
            lines.append(f"  Per round: {' '.join(tick_parts)}")

    # Enemy power timeline
    has_timeline = any(t for t in analytics.enemy_power_timeline)
    if has_timeline:
        all_powers: set[str] = set()
        for t in analytics.enemy_power_timeline:
            all_powers.update(t.keys())
        if all_powers:
            lines.append("\nEnemy power timeline:")
            for power_name in sorted(all_powers):
                values = [
                    t.get(power_name, "-") for t in analytics.enemy_power_timeline
                ]
                line = " -> ".join(f"R{i + 1}:{v}" for i, v in enumerate(values))
                lines.append(f"  {power_name}: {line}")

    # Unattributed damage (even without poison cards, catches power effects)
    tick_total = sum(analytics.poison_tick_per_round)
    if tick_total > 0 and not analytics.poison_by_card:
        tick_parts = [
            f"R{i + 1}:{t}"
            for i, t in enumerate(analytics.poison_tick_per_round)
            if t > 0
        ]
        lines.append(f"\nUnattributed damage (power/passive effects): {tick_total}")
        lines.append(f"  Per round: {' '.join(tick_parts)}")

    return "\n".join(lines)
