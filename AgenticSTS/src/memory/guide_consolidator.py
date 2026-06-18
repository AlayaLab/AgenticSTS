"""Guide consolidation pipeline: episodes → Guides via LLM.

Aggregates domain-specific episodes (combat, route, card_build) into
consolidated Guide objects with LLM-generated tactical advice.

Runs periodically (every N runs) after enough episodes accumulate.
Guides are the "self-evolution" output — persistent knowledge that
improves decisions across future runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections import Counter

import config
from src.memory.deck_build_registry import canonical_deck_build_tag
from src.memory.enemy_keys import normalize_enemy_key
from src.memory.event_guide_consolidator import consolidate_event_guides
from src.memory import guide_consolidation_log
from src.memory.models_v2 import (
    CardBuildMemory,
    CombatEpisode,
    CombatGuide,
    DeckGuide,
    EnemyIntentSnapshot,
    EnemyRoundState,
    PowerSnapshot,
    RouteGuide,
    RouteMemory,
    normalize_character,
)
from src.skills.mistake_discovery import loss_ratio

logger = logging.getLogger(__name__)


def _select_combat_keys_for_refresh(
    episodes: list[CombatEpisode],
    current_run_id: str,
    guide_store: object | None = None,  # GuideStore — duck-typed to avoid circular import
) -> set[tuple[str, str]]:
    """Pick (enemy_key, character) keys to refresh this postrun.

    Policy:
    - All boss + elite fights from the current run always refresh.
    - Per act, the single small-monster fight with max HP loss refreshes
      (tie → first-encountered in iteration order).
    - First-encounter bypass: when ``guide_store`` is provided, any key with
      no existing guide and ≥1 non-aborted episode in the current run is
      additionally forced into the refresh set. This ensures self-evolve
      runs from blank stores capture every encountered enemy on the first
      run instead of waiting for a second occurrence.
    - Episodes from other runs or marked aborted are ignored.

    Returns a set of normalized (enemy_key, character) tuples. The caller
    runs the existing refresh pipeline per key.
    """
    run_episodes = [
        ep for ep in episodes
        if ep.run_id == current_run_id and not getattr(ep, "is_aborted", False)
    ]

    selected: set[tuple[str, str]] = set()

    # Boss + elite: always refresh
    for ep in run_episodes:
        if ep.combat_type in ("boss", "elite"):
            selected.add((
                normalize_enemy_key(ep.enemy_key),
                normalize_character(ep.character),
            ))

    # Small monster: per (act, character) pick the single worst HP loss fight
    worst_per_act_char: dict[tuple[int, str], CombatEpisode] = {}
    for ep in run_episodes:
        if ep.combat_type != "monster":
            continue
        hp_loss = ep.hp_before - ep.hp_after
        char = normalize_character(ep.character)
        key = (ep.act, char)
        prev = worst_per_act_char.get(key)
        if prev is None or hp_loss > (prev.hp_before - prev.hp_after):
            worst_per_act_char[key] = ep

    for ep in worst_per_act_char.values():
        selected.add((
            normalize_enemy_key(ep.enemy_key),
            normalize_character(ep.character),
        ))

    # First-encounter bypass: any (key) with no existing guide and ≥1
    # non-aborted episode in the current run is forced into the refresh set.
    if guide_store is not None:
        for ep in run_episodes:
            key = (
                normalize_enemy_key(ep.enemy_key),
                normalize_character(ep.character),
            )
            if guide_store.get_combat_guide(*key) is None:
                selected.add(key)

    return selected


# ── Cleanest-wins selection (inlined from removed cohort_utils) ──
#
# Picks the cleanest `low_loss_subset` episodes from a cohort for inclusion in
# combat guide prompts. Previously lived in src.skills.cohort_utils alongside
# the broader cohort-discovery pipeline; that module is being deleted as part
# of the mistake-driven discovery migration (see 2026-04-19 spec). The guide
# consolidator still wants "show the model the lowest-damage wins" samples, so
# the minimal selection logic is preserved here. Only `low_loss_subset` is
# consumed, so we return the tuple directly instead of the old CohortSelection
# dataclass.


def _round_quality_threshold(combat_type: str) -> float | None:
    if combat_type == "monster":
        return 0.5
    if combat_type == "elite":
        return 0.3
    return None


def _passes_round_quality_filter(ep: CombatEpisode, threshold: float) -> bool:
    tagged = [
        rnd.situation_tag.outcome_quality
        for rnd in ep.rounds
        if rnd.situation_tag is not None
    ]
    if not tagged:
        return True
    good = sum(1 for quality in tagged if quality in {"clean", "acceptable"})
    return (good / len(tagged)) >= threshold


def _select_low_loss_subset(
    episodes: list[CombatEpisode],
) -> tuple[CombatEpisode, ...]:
    """Pick the cleanest winning episodes (lowest relative HP loss).

    Applies combat-type-aware round-quality filtering first, then ranks by
    (loss_ratio, round_count, -hp_before) and takes a bounded percentile.
    Returns an empty tuple if no eligible wins exist.
    """
    if not episodes:
        return ()

    wins = [ep for ep in episodes if ep.won]
    combat_type = episodes[0].combat_type if episodes else ""
    eligible = wins

    threshold = _round_quality_threshold(combat_type)
    if threshold is not None:
        filtered = [ep for ep in wins if _passes_round_quality_filter(ep, threshold)]
        if len(filtered) >= 3:
            eligible = filtered

    ranked = sorted(
        eligible,
        key=lambda ep: (loss_ratio(ep), len(ep.rounds), -ep.hp_before),
    )
    if not ranked:
        return ()
    subset_size = min(
        len(ranked),
        max(
            config.COHORT_LOW_LOSS_MIN,
            min(
                config.COHORT_LOW_LOSS_MAX,
                math.ceil(config.COHORT_LOW_LOSS_PERCENTILE * len(ranked)),
            ),
        ),
    )
    return tuple(ranked[:subset_size])

COMBAT_ANALYST_PROMPT = (
    "You are a Slay the Spire 2 strategy analyst. "
    "Analyze combat data and produce tactical guides."
)
ROUTE_ANALYST_PROMPT = (
    "You are a Slay the Spire 2 strategy analyst. "
    "Analyze route data and produce pathing guides."
)
DECK_ANALYST_PROMPT = (
    "You are a Slay the Spire 2 strategy analyst. "
    "Analyze deck building data and produce guides."
)


# ── Combat Guide Consolidation ────────────────────────────────


def _detect_phase_transitions(episodes: list[CombatEpisode]) -> list[str]:
    """Detect enemy phase transitions from HP/power snapshots across rounds.

    Compares consecutive rounds within each episode. A phase transition is
    detected when an enemy's max_hp changes or its power set changes.
    """
    transitions: list[str] = []
    seen_transitions: set[str] = set()  # dedup across episodes

    for ep in episodes:
        prev_max_hp: dict[str, int] = {}
        prev_powers: dict[str, tuple[str, ...]] = {}

        for rnd in ep.rounds:
            # Detect max_hp changes (boss revival / phase shift)
            for enemy_id, name, _hp, max_hp in rnd.enemy_hp_snapshot:
                key = enemy_id or name
                old_max = prev_max_hp.get(key)
                if old_max is not None and max_hp != old_max:
                    sig = f"{name}:{old_max}->{max_hp}"
                    if sig not in seen_transitions:
                        seen_transitions.add(sig)
                        transitions.append(
                            f"R{rnd.round_num}: {name} max_hp {old_max}->{max_hp}"
                        )
                prev_max_hp[key] = max_hp

            # Detect power set changes (new abilities after revival)
            for i, powers in enumerate(rnd.enemy_powers_snapshot):
                if i < len(rnd.enemy_hp_snapshot):
                    key = rnd.enemy_hp_snapshot[i][0] or rnd.enemy_hp_snapshot[i][1]
                    display = rnd.enemy_hp_snapshot[i][1]
                else:
                    key = str(i)
                    display = key
                old_powers = prev_powers.get(key)
                if old_powers is not None and powers != old_powers:
                    added = set(powers) - set(old_powers)
                    removed = set(old_powers) - set(powers)
                    if added or removed:
                        sig = f"{key}:{'|'.join(sorted(removed))}->{'|'.join(sorted(added))}"
                        if sig not in seen_transitions:
                            seen_transitions.add(sig)
                            parts: list[str] = []
                            if removed:
                                parts.append(
                                    f"lost {', '.join(sorted(removed))}"
                                )
                            if added:
                                parts.append(
                                    f"gained {', '.join(sorted(added))}"
                                )
                            transitions.append(
                                f"R{rnd.round_num}: {display} {'; '.join(parts)}"
                            )
                prev_powers[key] = powers

    return transitions


def _format_power_snapshot(
    power: PowerSnapshot,
    *,
    include_description: bool = True,
    include_debuff_tag: bool = False,
) -> str:
    amount = f"({power.amount})" if power.amount is not None else ""
    text = f"{power.name}{amount}"
    if include_debuff_tag and power.is_debuff:
        text += " [debuff]"
    if include_description and power.description:
        text += f": {power.description}"
    return text


def _format_intent_snapshot(intent: EnemyIntentSnapshot) -> str:
    if intent.intent_type == "Attack":
        if intent.damage is not None:
            hits = intent.hits if intent.hits is not None else 1
            if hits > 1:
                return f"Attack({intent.damage}x{hits}={intent.damage * hits})"
            return f"Attack({intent.damage})"
        if intent.total_damage is not None:
            return f"Attack({intent.total_damage})"
        if intent.label:
            return f"Attack({intent.label})"
        return "Attack(?)"
    if intent.intent_type == "Status" and intent.status_card_count is not None:
        label = intent.label or "Status"
        return f"Status({label}, {intent.status_card_count} cards)"
    if intent.label:
        return f"{intent.intent_type}({intent.label})"
    return intent.intent_type or "Unknown"


def _round_enemy_states(rnd) -> tuple[EnemyRoundState, ...]:
    return rnd.enemy_states if getattr(rnd, "enemy_states", ()) else ()


def _round_player_powers(rnd) -> tuple[PowerSnapshot, ...]:
    return rnd.player_powers_snapshot if getattr(rnd, "player_powers_snapshot", ()) else ()


def _format_enemy_state_line(enemy: EnemyRoundState) -> str:
    intents = ", ".join(_format_intent_snapshot(i) for i in enemy.intents) or "Unknown"
    powers = "; ".join(
        _format_power_snapshot(p, include_description=True)
        for p in enemy.powers
    ) or "none"
    return (
        f"{enemy.name}: HP {enemy.hp}/{enemy.max_hp}, Block {enemy.block} | "
        f"Intent: {intents} | Powers: {powers}"
    )


def _collect_power_defined_rules(episodes: list[CombatEpisode]) -> list[str]:
    # Episode payloads contain whatever the C# mod sent at capture time —
    # including upstream placeholders ("TODO" for ASLEEP_POWER, "A power
    # used by X." for SANDPIT) and unresolved Godot template tokens.
    # Route every description through the same filter/override pipeline the
    # gameplay-time prompts use so postrun guides don't ingest junk.
    from src.knowledge.power_lookup import (
        _is_placeholder_description,
        _sanitize_runtime_description,
        get_power_description,
    )

    power_counts: Counter[str] = Counter()
    details: dict[str, str] = {}
    for ep in episodes:
        for rnd in ep.rounds:
            for enemy in _round_enemy_states(rnd):
                for power in enemy.powers:
                    raw = (power.description or "").strip()
                    if _is_placeholder_description(raw):
                        desc = ""
                    else:
                        desc = _sanitize_runtime_description(raw)
                        if _is_placeholder_description(desc):
                            desc = ""
                    if not desc:
                        # Fall back to curated override / static lookup
                        # (e.g. ASLEEP gets the "Awakens upon losing HP…" text).
                        key_id = (power.power_id or power.name).strip()
                        desc = (get_power_description(key_id.upper()) or "").strip()
                        if not desc and key_id.upper().endswith("_POWER"):
                            desc = (
                                get_power_description(key_id.upper()[: -len("_POWER")])
                                or ""
                            ).strip()
                    if not desc:
                        continue
                    key = (power.power_id or power.name).lower()
                    power_counts[key] += 1
                    details.setdefault(key, f"{power.name}: {desc}")
    return [details[key] for key, _ in power_counts.most_common(8)]


def _collect_round_linked_observations(
    episodes: list[CombatEpisode],
    *,
    max_rounds: int = 8,
) -> list[str]:
    intent_counts: dict[int, Counter[str]] = {}
    debuff_counts: dict[int, Counter[str]] = {}
    status_counts: dict[int, Counter[str]] = {}

    for ep in episodes:
        for rnd in ep.rounds:
            if rnd.round_num > max_rounds:
                continue
            intent_bucket = intent_counts.setdefault(rnd.round_num, Counter())
            debuff_bucket = debuff_counts.setdefault(rnd.round_num, Counter())
            status_bucket = status_counts.setdefault(rnd.round_num, Counter())
            states = _round_enemy_states(rnd)
            if states:
                for enemy in states:
                    for intent in enemy.intents:
                        intent_bucket.update([f"{enemy.name}: {_format_intent_snapshot(intent)}"])
                        if intent.status_card_count:
                            label = intent.label or intent.intent_type or "Status"
                            status_bucket.update(
                                [f"{enemy.name}: {label} ({intent.status_card_count} cards)"]
                            )
            else:
                intent_bucket.update(rnd.enemy_intents)
            for power in _round_player_powers(rnd):
                if power.is_debuff:
                    debuff_bucket.update([_format_power_snapshot(
                        power,
                        include_description=False,
                        include_debuff_tag=False,
                    )])

    lines: list[str] = []
    for round_num in sorted(intent_counts):
        top_intents = ", ".join(
            f"{text}({count})" for text, count in intent_counts[round_num].most_common(3)
        ) or "none"
        parts = [f"R{round_num} common intents: {top_intents}"]
        top_debuffs = ", ".join(
            f"{text}({count})" for text, count in debuff_counts.get(round_num, Counter()).most_common(3)
        )
        if top_debuffs:
            parts.append(f"common player debuffs/timers: {top_debuffs}")
        top_status = ", ".join(
            f"{text}({count})" for text, count in status_counts.get(round_num, Counter()).most_common(2)
        )
        if top_status:
            parts.append(f"status-card pressure: {top_status}")
        lines.append(" | ".join(parts))
    return lines[:8]


def _collect_threshold_trigger_observations(
    episodes: list[CombatEpisode],
) -> list[str]:
    observations: list[str] = []
    seen: set[str] = set()

    for ep in episodes:
        prev_states: dict[str, EnemyRoundState] = {}
        prev_count = 0
        for rnd in ep.rounds:
            states = {
                (state.enemy_id or state.name): state
                for state in _round_enemy_states(rnd)
            }
            if prev_states and len(states) != prev_count:
                sig = f"count:{prev_count}->{len(states)}@R{rnd.round_num}"
                if sig not in seen:
                    seen.add(sig)
                    observations.append(
                        f"R{rnd.round_num}: enemy count changed {prev_count}->{len(states)} "
                        f"(possible summon/death/phase event)."
                    )
            for key, state in states.items():
                prev = prev_states.get(key)
                if prev is None:
                    continue
                if state.max_hp != prev.max_hp:
                    sig = f"maxhp:{key}:{prev.max_hp}->{state.max_hp}@R{rnd.round_num}"
                    if sig not in seen:
                        seen.add(sig)
                        observations.append(
                            f"R{rnd.round_num}: {state.name} max HP changed "
                            f"{prev.max_hp}->{state.max_hp} at HP {state.hp}/{state.max_hp}."
                        )
                prev_powers = {p.name for p in prev.powers}
                curr_powers = {p.name for p in state.powers}
                added = sorted(curr_powers - prev_powers)
                removed = sorted(prev_powers - curr_powers)
                if added or removed:
                    change_parts: list[str] = []
                    if added:
                        change_parts.append(f"gained {', '.join(added)}")
                    if removed:
                        change_parts.append(f"lost {', '.join(removed)}")
                    sig = f"powers:{key}:{'|'.join(added)}:{'|'.join(removed)}@R{rnd.round_num}"
                    if sig not in seen:
                        seen.add(sig)
                        observations.append(
                            f"R{rnd.round_num}: {state.name} {'; '.join(change_parts)} "
                            f"at HP {state.hp}/{state.max_hp}."
                        )
            prev_states = states
            prev_count = len(states)

    return observations[:10]


def _collect_player_pressure_observations(episodes: list[CombatEpisode]) -> list[str]:
    debuff_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()
    for ep in episodes:
        for rnd in ep.rounds:
            for power in _round_player_powers(rnd):
                if power.is_debuff:
                    debuff_counts.update([_format_power_snapshot(
                        power,
                        include_description=True,
                        include_debuff_tag=False,
                    )])
            for enemy in _round_enemy_states(rnd):
                for intent in enemy.intents:
                    if intent.status_card_count:
                        label = intent.label or intent.intent_type or "Status"
                        status_counts.update(
                            [f"{enemy.name}: {label} ({intent.status_card_count} cards)"]
                        )

    lines: list[str] = []
    if debuff_counts:
        lines.append(
            "Common player debuffs/timers: "
            + ", ".join(f"{text}({count})" for text, count in debuff_counts.most_common(5))
        )
    if status_counts:
        lines.append(
            "Common status-card intents: "
            + ", ".join(f"{text}({count})" for text, count in status_counts.most_common(4))
        )
    return lines


def _representative_combat_episodes(episodes: list[CombatEpisode]) -> list[CombatEpisode]:
    selected: list[CombatEpisode] = []
    losses = [ep for ep in episodes if not ep.won]
    wins = [ep for ep in episodes if ep.won]
    for pool in (losses[-1:], wins[-1:]):
        for ep in pool:
            if ep not in selected:
                selected.append(ep)
    for ep in reversed(episodes):
        if ep not in selected:
            selected.append(ep)
        if len(selected) >= 3:
            break
    return selected


def _format_representative_round_snapshots(
    episodes: list[CombatEpisode],
    *,
    max_rounds_per_episode: int = 8,
) -> list[str]:
    lines: list[str] = []
    for ep in _representative_combat_episodes(episodes):
        result = "WIN" if ep.won else "LOSS"
        lines.append(
            f"Episode [{result}] HP {ep.hp_before}->{ep.hp_after}, "
            f"rounds={len(ep.rounds)}, terminal_reason={ep.terminal_reason}"
        )
        for rnd in ep.rounds[:max_rounds_per_episode]:
            lines.append(f"  R{rnd.round_num}:")
            states = _round_enemy_states(rnd)
            if states:
                for enemy in states:
                    lines.append(f"    - {_format_enemy_state_line(enemy)}")
            else:
                intents = ", ".join(rnd.enemy_intents) or "Unknown"
                powers = []
                for power_set in rnd.enemy_powers_snapshot:
                    if power_set:
                        powers.append(", ".join(power_set))
                powers_text = " | ".join(powers) if powers else "none"
                lines.append(f"    - Enemy intents: {intents} | Enemy powers: {powers_text}")
            player_powers = _round_player_powers(rnd)
            if player_powers:
                debuffs = [
                    _format_power_snapshot(p, include_description=True)
                    for p in player_powers if p.is_debuff
                ]
                buffs = [
                    _format_power_snapshot(p, include_description=True)
                    for p in player_powers if not p.is_debuff
                ]
                if debuffs:
                    lines.append(f"    - Player debuffs/timers: {'; '.join(debuffs[:4])}")
                elif buffs:
                    lines.append(f"    - Player powers: {'; '.join(buffs[:3])}")
    return lines


def _format_outcome_anchors(episodes: list[CombatEpisode]) -> list[str]:
    wins = [e for e in episodes if e.won]
    losses = [e for e in episodes if not e.won]
    hp_losses = [max(0, e.hp_before - e.hp_after) for e in episodes]
    lines = [
        f"Episodes={len(episodes)} | wins={len(wins)} | losses={len(losses)}",
        f"Average HP loss={sum(hp_losses) / len(hp_losses):.1f} | "
        f"Average rounds={sum(len(e.rounds) for e in episodes) / len(episodes):.1f}",
    ]
    if losses:
        death_rounds = Counter(len(e.rounds) for e in losses)
        lines.append(
            "Common loss rounds: "
            + ", ".join(f"R{rnd}({count})" for rnd, count in death_rounds.most_common(4))
        )
    return lines


def _format_combat_episodes(episodes: list[CombatEpisode]) -> str:
    """Format enemy-mechanics evidence for combat guide consolidation."""
    lines: list[str] = []

    lines.append("## Recent outcome anchors")
    lines.extend(f"- {line}" for line in _format_outcome_anchors(episodes))

    lines.append("")
    lines.append("## Power-defined rules")
    power_rules = _collect_power_defined_rules(episodes)
    if power_rules:
        lines.extend(f"- {line}" for line in power_rules)
    else:
        lines.append("- No enemy power descriptions captured.")

    lines.append("")
    lines.append("## Round-linked observations")
    round_lines = _collect_round_linked_observations(episodes)
    if round_lines:
        lines.extend(f"- {line}" for line in round_lines)
    else:
        lines.append("- No stable round-linked observations captured.")

    lines.append("")
    lines.append("## HP / death / revive linked observations")
    threshold_lines = _collect_threshold_trigger_observations(episodes)
    if threshold_lines:
        lines.extend(f"- {line}" for line in threshold_lines)
    else:
        lines.append("- No clear HP / death / revive transitions detected.")

    lines.append("")
    lines.append("## Phase transitions")
    phase_transitions = _detect_phase_transitions(episodes)
    if phase_transitions:
        lines.extend(f"- {line}" for line in phase_transitions[:10])
    else:
        lines.append("- No explicit phase transitions detected.")

    lines.append("")
    lines.append("## Status / debuff pressure on player")
    player_pressure = _collect_player_pressure_observations(episodes)
    if player_pressure:
        lines.extend(f"- {line}" for line in player_pressure)
    else:
        lines.append("- No recurring player debuffs or status-card pressure captured.")

    lines.append("")
    lines.append("## Representative round snapshots")
    lines.extend(_format_representative_round_snapshots(episodes))

    return "\n".join(lines)


def build_combat_guide_prompt(
    enemy_key: str,
    character: str,
    episodes: list[CombatEpisode],
    existing_guide: CombatGuide | None = None,
) -> str:
    """Build a prompt for LLM to consolidate combat episodes into a guide."""
    episode_text = _format_combat_episodes(episodes)
    existing_text = ""
    if existing_guide and (
        existing_guide.guide_text
        or existing_guide.mechanic_summary
        or existing_guide.round_triggers
        or existing_guide.threshold_triggers
    ):
        existing_sections = []
        if existing_guide.trigger_model:
            existing_sections.append(f"trigger_model: {existing_guide.trigger_model}")
        if existing_guide.mechanic_summary:
            existing_sections.append(
                "mechanic_summary:\n" + "\n".join(f"- {x}" for x in existing_guide.mechanic_summary)
            )
        if existing_guide.round_triggers:
            existing_sections.append(
                "round_triggers:\n" + "\n".join(f"- {x}" for x in existing_guide.round_triggers)
            )
        if existing_guide.threshold_triggers:
            existing_sections.append(
                "threshold_triggers:\n"
                + "\n".join(f"- {x}" for x in existing_guide.threshold_triggers)
            )
        if existing_guide.danger_windows:
            existing_sections.append(
                "danger_windows:\n" + "\n".join(f"- {x}" for x in existing_guide.danger_windows)
            )
        if existing_guide.failure_modes:
            existing_sections.append(
                "failure_modes:\n" + "\n".join(f"- {x}" for x in existing_guide.failure_modes)
            )
        if existing_guide.guide_text:
            existing_sections.append(f"guide_text:\n{existing_guide.guide_text}")
        existing_text = (
            f"\n## Existing Guide (v{existing_guide.version})\n"
            f"{'\n\n'.join(existing_sections)}\n"
        )

    response_schema = (
        '{"trigger_model": "round_based | threshold_based | death_based | mixed | unclear", '
        '"mechanic_summary": ["mechanic1", "mechanic2", ...], '
        '"round_triggers": ["trigger1", "trigger2", ...], '
        '"threshold_triggers": ["trigger1", "trigger2", ...], '
        '"danger_windows": ["window1", "window2", ...], '
        '"failure_modes": ["mode1", "mode2", ...], '
        '"guide_text": "- Bullet 1\\n- Bullet 2\\n...", '
        '"confidence": 0.5-0.9}'
    )

    return f"""You are a Slay the Spire 2 enemy-mechanics analyst.

Your job is NOT to analyze deck quality, card choices, or player build.
Your job IS to identify this enemy's fixed fight mechanics, trigger rules,
phase structure, and danger windows.

Enemy: {enemy_key}
Character: {character}
{existing_text}
{episode_text}

Task:
Identify the enemy's mechanic model and produce a concise combat guide.

You must answer these questions:
1. Is this enemy primarily round-driven, HP-threshold-driven, death-driven, or mixed?
2. Which mechanics are explicitly defined by enemy powers?
3. Which mechanics are inferred from repeating intent patterns by round?
4. Which mechanics are triggered by HP thresholds, death, revive, summon, or phase change?
5. What are the main danger windows?
6. What should the agent pay attention to when fighting this enemy?

Important:
- Focus on the ENEMY only.
- Do not discuss specific player cards, archetypes, or build plans.
- Do not rank cards or mention "top cards in wins".
- Prefer enemy power descriptions as the highest-confidence source of truth.
- Use repeating round patterns as secondary evidence.
- Use HP/death/phase transitions as evidence for threshold-based mechanics.
- If evidence is weak or conflicting, say so explicitly.
- If both round-based and threshold-based mechanics exist, describe both and explain which one appears to override the other.
- mechanic_summary describes ONLY enemy behavior and fight structure, not advice.
- round_triggers / threshold_triggers must be factual trigger statements, not recommendations.
- guide_text should stay tactical and enemy-specific, but grounded in the mechanics above.

Respond with JSON:
{response_schema}

Keep the guide_text under 180 words. Be specific to this enemy, not generic combat advice."""


def parse_combat_guide_response(
    raw_text: str,
    enemy_key: str,
    character: str,
    episode_count: int,
    win_rate: float,
    existing_guide: CombatGuide | None = None,
) -> CombatGuide | None:
    """Parse LLM response into a CombatGuide."""
    import json

    try:
        # Find JSON in response
        start = raw_text.index("{")
        end = raw_text.rindex("}") + 1
        data = json.loads(raw_text[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse combat guide response")
        return None

    def _string_list(value: object) -> tuple[str, ...]:
        if not isinstance(value, list):
            return ()
        return tuple(
            " ".join(str(item).strip().split())
            for item in value
            if str(item).strip()
        )

    guide_text = data.get("guide_text", "")
    trigger_model = str(data.get("trigger_model", "")).strip()
    mechanic_summary = _string_list(data.get("mechanic_summary", []))
    round_triggers = _string_list(data.get("round_triggers", []))
    threshold_triggers = _string_list(data.get("threshold_triggers", []))
    danger_windows = _string_list(data.get("danger_windows", []))
    failure_modes = _string_list(data.get("failure_modes", []))
    confidence = min(0.9, max(0.3, float(data.get("confidence", 0.5))))

    if not guide_text:
        return None

    version = (existing_guide.version + 1) if existing_guide else 1

    return CombatGuide(
        enemy_key=normalize_enemy_key(enemy_key),
        character=character,
        guide_text=guide_text,
        trigger_model=trigger_model,
        mechanic_summary=mechanic_summary,
        round_triggers=round_triggers,
        threshold_triggers=threshold_triggers,
        danger_windows=danger_windows,
        failure_modes=failure_modes,
        key_patterns=existing_guide.key_patterns if existing_guide else (),
        win_rate=win_rate,
        episode_count=episode_count,
        confidence=confidence,
        version=version,
    )


# ── Route Guide Consolidation ─────────────────────────────────


def _format_route_memories(memories: list[RouteMemory]) -> str:
    """Format route memories into a summary for LLM consolidation."""
    lines = []
    victories = [m for m in memories if m.victory_run]
    aborted = [m for m in memories if not m.victory_run and getattr(m, "boss_result", "") == "aborted"]
    defeats = [m for m in memories if not m.victory_run and getattr(m, "boss_result", "") != "aborted"]
    lines.append(
        f"## Route Data: {len(memories)} memories "
        f"({len(victories)} from wins, {len(defeats)} from losses"
        + (f", {len(aborted)} aborted)" if aborted else ")")
    )

    for mem in memories[-5:]:
        if mem.victory_run:
            result = "WIN"
        elif getattr(mem, "boss_result", "") == "aborted":
            result = "ABORTED"
        else:
            result = "LOSS"
        node_types = [n.node_type for n in mem.nodes]
        type_counts = {}
        for t in node_types:
            type_counts[t] = type_counts.get(t, 0) + 1
        types_str = ", ".join(f"{t}:{c}" for t, c in sorted(type_counts.items()))
        lines.append(
            f"- [{result}] HP {mem.hp_start}→{mem.hp_end}, Gold {mem.gold_start}→{mem.gold_end}, "
            f"Boss: {mem.boss_result}, Nodes: {types_str}"
        )

    # Win vs loss patterns
    if victories:
        win_patterns = [" → ".join(n.node_type for n in m.nodes) for m in victories[-3:]]
        lines.append(f"Winning routes: {'; '.join(win_patterns)}")

    return "\n".join(lines)


def build_route_guide_prompt(
    act: int,
    character: str,
    memories: list[RouteMemory],
    existing_guide: RouteGuide | None = None,
) -> str:
    """Build a prompt for LLM to consolidate route memories into a guide."""
    memory_text = _format_route_memories(memories)
    existing_text = ""
    if existing_guide and existing_guide.guide_text:
        existing_text = (
            f"\n## Existing Guide (v{existing_guide.version})\n"
            f"{existing_guide.guide_text}\n"
        )

    guide_request = (
        "Based on the route data above, write a SHORT routing guide "
        f"(3-5 bullet points) for Act {act} as {character}."
    )
    response_schema = (
        '{"guide_text": "- Bullet 1\\n- Bullet 2\\n...", '
        '"preferred_pattern": "monster→elite→rest→...→boss", '
        '"confidence": 0.5-0.9}'
    )

    return f"""You are analyzing route/pathing data from a Slay the Spire 2 AI agent.

Act: {act}
Character: {character}
{existing_text}
{memory_text}

{guide_request}

Focus on:
1. What node patterns led to wins vs losses?
2. How many elites is optimal for this act?
3. When to prioritize rest sites vs shops?
4. HP/gold management across the act

Respond with JSON:
{response_schema}

Keep guide_text under 150 words."""


def parse_route_guide_response(
    raw_text: str,
    act: int,
    character: str,
    memory_count: int,
    existing_guide: RouteGuide | None = None,
) -> RouteGuide | None:
    """Parse LLM response into a RouteGuide."""
    import json

    try:
        start = raw_text.index("{")
        end = raw_text.rindex("}") + 1
        data = json.loads(raw_text[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse route guide response")
        return None

    guide_text = data.get("guide_text", "")
    preferred_pattern = data.get("preferred_pattern", "")
    confidence = min(0.9, max(0.3, float(data.get("confidence", 0.5))))

    if not guide_text:
        return None

    version = (existing_guide.version + 1) if existing_guide else 1

    return RouteGuide(
        act=act,
        character=character,
        guide_text=guide_text,
        preferred_pattern=preferred_pattern,
        memory_count=memory_count,
        confidence=confidence,
        version=version,
    )


# ── Deck Guide Consolidation ──────────────────────────────────


def _format_card_builds(builds: list[CardBuildMemory]) -> str:
    """Format card build memories into a summary for LLM consolidation.

    Includes LLM-generated build analysis fields when available.
    """
    lines = []
    victories = [b for b in builds if b.victory]
    defeats = [b for b in builds if not b.victory]
    lines.append(
        f"## Deck Data: {len(builds)} builds "
        f"({len(victories)} wins, {len(defeats)} losses)"
    )

    for b in builds[-5:]:
        result = "WIN" if b.victory else "LOSS"
        top_played = sorted(b.card_play_counts, key=lambda x: -x[1])[:5]
        top_str = ", ".join(f"{c}({n})" for c, n in top_played) if top_played else "none"
        final_size = len(b.final_deck)
        # Core stats line
        line = f"- [{result}] Floor {b.final_floor}, {final_size} cards, Fitness: {b.fitness:.1f}"
        line += f", Top cards: {top_str}"
        # Structured LLM analysis fields (when available)
        if b.build_summary:
            line += f"\n  Summary: {b.build_summary}"
        if b.primary_plan:
            line += f"\n  Plan: {b.primary_plan}"
        engines = []
        if b.damage_engine:
            engines.append(f"Damage: {b.damage_engine}")
        if b.defense_engine:
            engines.append(f"Defense: {b.defense_engine}")
        if b.cycle_engine:
            engines.append(f"Cycle: {b.cycle_engine}")
        if b.energy_engine:
            engines.append(f"Energy: {b.energy_engine}")
        if engines:
            line += f"\n  Engines: {' | '.join(engines)}"
        if b.weak_points:
            line += f"\n  Weak: {b.weak_points}"
        if b.build_tags:
            line += f"\n  Tags: {', '.join(b.build_tags)}"
        if b.analysis_confidence > 0:
            line += f" (confidence: {b.analysis_confidence:.1f})"
        lines.append(line)

    return "\n".join(lines)


def build_deck_guide_prompt(
    character: str,
    archetype: str,
    builds: list[CardBuildMemory],
    existing_guide: DeckGuide | None = None,
) -> str:
    """Build a prompt for LLM to consolidate card build memories into a guide."""
    build_text = _format_card_builds(builds)
    existing_text = ""
    if existing_guide and existing_guide.guide_text:
        existing_text = (
            f"\n## Existing Guide (v{existing_guide.version})\n"
            f"{existing_guide.guide_text}\n"
        )

    guide_request = (
        "Based on the deck data above, write a SHORT deck building guide "
        f"(3-5 bullet points) for {character} builds tagged '{archetype or 'general'}'."
    )
    response_schema = (
        '{"guide_text": "- Bullet 1\\n- Bullet 2\\n...", '
        '"key_cards": ["card1", "card2", ...], '
        '"confidence": 0.5-0.9}'
    )

    return f"""You are analyzing deck building data from a Slay the Spire 2 AI agent.

Character: {character}
Build category: {archetype or "general"}
{existing_text}
{build_text}

{guide_request}

Focus on:
1. Which cards and strategies appeared most in winning decks?
2. What deck sizes and compositions worked best?
3. What cards should be prioritized or avoided early?
4. Key upgrade targets and card synergies

Respond with JSON:
{response_schema}

Keep guide_text under 150 words."""


def _deck_guide_source_fingerprint(builds: list[CardBuildMemory]) -> str:
    """Hash the evidence cohort so same-count content edits still refresh guides."""
    cohort = [
        {
            "run_id": build.run_id,
            "character": normalize_character(build.character),
            "build_tags": list(build.build_tags),
            "build_summary": build.build_summary,
            "primary_plan": build.primary_plan,
            "damage_engine": build.damage_engine,
            "defense_engine": build.defense_engine,
            "cycle_engine": build.cycle_engine,
            "energy_engine": build.energy_engine,
            "weak_points": build.weak_points,
            "analysis_confidence": round(float(build.analysis_confidence or 0.0), 4),
            "starting_deck": list(build.starting_deck),
            "final_deck": list(build.final_deck),
            "card_play_counts": [list(p) for p in build.card_play_counts],
            "victory": build.victory,
            "completion_reason": build.completion_reason,
            "final_floor": build.final_floor,
            "fitness": round(float(build.fitness or 0.0), 4),
            "key_cards": [list(kc) for kc in build.key_cards],
            "coherence_score": round(float(build.coherence_score or 0.0), 4),
            "coherence_analysis": build.coherence_analysis,
        }
        for build in sorted(builds, key=lambda item: (item.run_id, item.memory_id))
    ]
    payload = json.dumps(cohort, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _select_deck_keys_for_refresh(
    builds: list[CardBuildMemory],
    current_run_id: str,
) -> set[tuple[str, str]]:
    """Pick (character, archetype) deck-guide keys touched by the current run only."""
    from src.memory.card_build_extractor import primary_tag as _primary_tag

    selected: set[tuple[str, str]] = set()
    for build in builds:
        if build.run_id != current_run_id:
            continue
        raw_tag = _primary_tag(build) if build.build_tags else (build.archetype or "general")
        character = normalize_character(build.character)
        tag = canonical_deck_build_tag(character, raw_tag)
        if not tag:
            continue
        selected.add((character, tag))
    return selected


def parse_deck_guide_response(
    raw_text: str,
    character: str,
    archetype: str,
    memory_count: int,
    source_fingerprint: str,
    existing_guide: DeckGuide | None = None,
) -> DeckGuide | None:
    """Parse LLM response into a DeckGuide."""
    try:
        start = raw_text.index("{")
        end = raw_text.rindex("}") + 1
        data = json.loads(raw_text[start:end])
    except (ValueError, json.JSONDecodeError):
        logger.warning("Failed to parse deck guide response")
        return None

    guide_text = data.get("guide_text", "")
    key_cards = tuple(data.get("key_cards", []))
    confidence = min(0.9, max(0.3, float(data.get("confidence", 0.5))))

    if not guide_text:
        return None

    version = (existing_guide.version + 1) if existing_guide else 1

    return DeckGuide(
        character=character,
        archetype=archetype,
        guide_text=guide_text,
        key_cards=key_cards,
        memory_count=memory_count,
        source_fingerprint=source_fingerprint,
        confidence=confidence,
        version=version,
    )


def _deck_guide_needs_refresh(existing: DeckGuide | None, builds: list[CardBuildMemory]) -> bool:
    """Return whether a deck guide should be regenerated for this group."""
    if existing is None:
        return True
    if existing.memory_count != len(builds):
        return True
    return existing.source_fingerprint != _deck_guide_source_fingerprint(builds)


# ── Orchestrator ──────────────────────────────────────────────



async def consolidate_guides(
    memory_manager: object,
    *,
    current_run_id: str,
) -> dict[str, int]:
    """Run the full consolidation pipeline.

    Checks each domain store for enough episodes, then calls LLM to
    generate/update Guides. Returns counts of guides created/updated.

    Args:
        memory_manager: MemoryManager with V2 stores.
        current_run_id: Run ID used by run-scoped refresh selection
            (see _select_combat_keys_for_refresh and
            _select_deck_keys_for_refresh).
    """
    from src.brain.llm_caller import call_raw as llm_call_raw

    stats = {"combat": 0, "route": 0, "deck": 0, "event": 0}

    if not hasattr(memory_manager, "combat_store") or not memory_manager.v2_enabled:
        return stats

    min_episodes = config.CONSOLIDATION_MIN_EPISODES
    guide_store = memory_manager.guide_store
    if not guide_store:
        return stats

    # ── Combat guides ─────────────────────────────────────────
    # Run-scoped selection: boss + elite always, per-act worst monster.
    # See docs/superpowers/specs/2026-04-23-combat-guide-selective-refresh-design.md
    combat_store = memory_manager.combat_store
    if combat_store:
        all_episodes = combat_store.get_all()
        selected_keys = _select_combat_keys_for_refresh(
            all_episodes, current_run_id, guide_store=guide_store,
        )

        for (enemy_key, character) in sorted(selected_keys):
            # LLM still sees full cross-run history for this key
            episodes = [
                ep for ep in all_episodes
                if normalize_enemy_key(ep.enemy_key) == enemy_key
                and normalize_character(ep.character) == character
                and not getattr(ep, "is_aborted", False)
            ]
            existing = guide_store.get_combat_guide(enemy_key, character)

            # First-encounter bypass: skip min_episodes gate when no existing guide.
            if existing is None and len(episodes) >= 1:
                pass
            elif len(episodes) < min_episodes:
                continue

            # Skip if guide is up-to-date (same episode count AND has mechanic_summary)
            if existing and existing.episode_count >= len(episodes) and existing.mechanic_summary:
                continue

            wins = sum(1 for e in episodes if e.won)
            win_rate = wins / len(episodes) if episodes else 0.0

            prompt = build_combat_guide_prompt(enemy_key, character, episodes, existing)
            try:
                raw, _latency, _tokens = await llm_call_raw(
                    COMBAT_ANALYST_PROMPT,
                    prompt,
                    think=True,
                    call_type="guide_combat",
                )
                guide = parse_combat_guide_response(
                    raw,
                    enemy_key,
                    character,
                    len(episodes),
                    win_rate,
                    existing,
                )
                if guide:
                    guide_store.set_combat_guide(guide)
                    guide_consolidation_log.append_combat(
                        enemy_key=guide.enemy_key,
                        character=guide.character,
                        version=guide.version,
                        episode_count=guide.episode_count,
                        win_rate=guide.win_rate,
                    )
                    stats["combat"] += 1
                    logger.info(
                        "Consolidated combat guide: %s (%s) v%d",
                        enemy_key, character, guide.version,
                    )
            except Exception:
                logger.warning(
                    "Combat guide consolidation failed for %s", enemy_key, exc_info=True,
                )

    # ── Route guides ──────────────────────────────────────────
    route_store = memory_manager.route_store
    if route_store:
        groups_r: dict[tuple[int, str], list[RouteMemory]] = {}
        for mem in route_store.get_all():
            if mem.boss_result == "aborted" or any(node.is_aborted for node in mem.nodes):
                continue
            key = (mem.act, normalize_character(mem.character))
            groups_r.setdefault(key, []).append(mem)

        for (act, character), memories in groups_r.items():
            existing = guide_store.get_route_guide(act, character)

            # First-encounter bypass: skip min_episodes gate when no existing
            # guide. Memories here are already non-aborted (filtered upstream
            # at groups_r construction).
            if existing is None and len(memories) >= 1:
                pass
            elif len(memories) < min_episodes:
                continue

            if existing and existing.memory_count >= len(memories):
                continue

            prompt = build_route_guide_prompt(act, character, memories, existing)
            try:
                raw, _latency, _tokens = await llm_call_raw(
                    ROUTE_ANALYST_PROMPT,
                    prompt,
                    think=True,
                    call_type="guide_route",
                )
                guide = parse_route_guide_response(
                    raw,
                    act,
                    character,
                    len(memories),
                    existing,
                )
                if guide:
                    guide_store.set_route_guide(guide)
                    guide_consolidation_log.append_route(
                        act=guide.act,
                        character=guide.character,
                        version=guide.version,
                        memory_count=len(memories),
                    )
                    stats["route"] += 1
                    logger.info(
                        "Consolidated route guide: Act %d (%s) v%d",
                        act,
                        character,
                        guide.version,
                    )
            except Exception:
                logger.warning("Route guide consolidation failed for Act %d", act, exc_info=True)

    # ── Deck guides ───────────────────────────────────────────
    card_build_store = memory_manager.card_build_store
    if card_build_store:
        from src.memory.card_build_extractor import primary_tag as _primary_tag

        all_builds = card_build_store.get_all()
        selected_keys = _select_deck_keys_for_refresh(all_builds, current_run_id)
        groups_d: dict[tuple[str, str], list[CardBuildMemory]] = {}
        for build in all_builds:
            # Use evidence-based primary_tag if build_tags available,
            # else fall back to legacy archetype field
            raw_tag = _primary_tag(build) if build.build_tags else (build.archetype or "general")
            character = normalize_character(build.character)
            tag = canonical_deck_build_tag(character, raw_tag)
            if not tag:
                continue
            key = (character, tag)
            if key not in selected_keys:
                continue
            groups_d.setdefault(key, []).append(build)

        for (character, archetype), builds in groups_d.items():
            existing = guide_store.get_deck_guide(character, archetype)

            # First-encounter bypass: skip min_episodes gate when no existing
            # guide. CardBuildMemory has no is_aborted field today.
            non_aborted = [
                b for b in builds if not getattr(b, "is_aborted", False)
            ]
            if existing is None and len(non_aborted) >= 1:
                pass
            elif len(builds) < min_episodes:
                continue

            source_fingerprint = _deck_guide_source_fingerprint(builds)
            if not _deck_guide_needs_refresh(existing, builds):
                continue

            prompt = build_deck_guide_prompt(character, archetype, builds, existing)
            try:
                raw, _latency, _tokens = await llm_call_raw(
                    DECK_ANALYST_PROMPT,
                    prompt,
                    think=True,
                    call_type="guide_deck",
                )
                guide = parse_deck_guide_response(
                    raw,
                    character,
                    archetype,
                    len(builds),
                    source_fingerprint,
                    existing,
                )
                if guide:
                    guide_store.set_deck_guide(guide)
                    guide_consolidation_log.append_deck(
                        character=guide.character,
                        archetype=guide.archetype,
                        version=guide.version,
                        build_count=len(builds),
                    )
                    stats["deck"] += 1
                    logger.info(
                        "Consolidated deck guide: %s/%s v%d",
                        character,
                        archetype,
                        guide.version,
                    )
            except Exception:
                logger.warning(
                    "Deck guide consolidation failed for %s/%s",
                    character,
                    archetype,
                    exc_info=True,
                )

    # ── Event guides (run-scoped, delegated) ─────────────────────
    # See docs/superpowers/specs/2026-04-24-event-guide-consolidation-rework-design.md
    stats["event"] += await consolidate_event_guides(
        memory_manager,
        current_run_id=current_run_id,
        min_episodes=min_episodes,
        llm_call_raw=llm_call_raw,
    )

    return stats
