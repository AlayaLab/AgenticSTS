"""Build rich post-run decision/replay context from run logs and memory stores."""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config
from src.memory.combat_analytics import format_analytics, historical_comparison
from src.memory.enemy_keys import enemy_key_lookup

logger = logging.getLogger(__name__)

_COMBAT_STATE_TYPES = frozenset({"monster", "elite", "boss", "hand_select"})
_HISTORICAL_Z_RE = re.compile(r"z=([+-]?\d+(?:\.\d+)?)")
_HISTORICAL_LABEL_RE = re.compile(
    r"\((?:[^)]*?,\s*)?(WORSE_THAN_USUAL|BETTER_THAN_USUAL|TYPICAL)(?:,\s*n=\d+)?\)"
)


@dataclass(frozen=True)
class SectionStat:
    """Basic size telemetry for one prompt section."""

    name: str
    chars: int
    estimated_tokens: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "chars": self.chars,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass(frozen=True)
class LoggedState:
    """Relevant slice of a state snapshot from the run JSONL."""

    step: int
    floor: int
    state_type: str
    hp: int
    gold: int
    deck_size: int
    deck: tuple[str, ...]
    summary: str = ""


@dataclass(frozen=True)
class LoggedDecision:
    """A decision enriched with surrounding before/after state."""

    step: int
    floor: int
    state_type: str
    source: str
    action: dict[str, Any]
    reasoning: str
    before_state: LoggedState | None = None
    after_state: LoggedState | None = None
    strategic_note: str = ""


@dataclass(frozen=True)
class DecisionDigest:
    """Shared full-run decision digest for evolution and discovery."""

    text: str
    section_stats: tuple[SectionStat, ...]
    non_combat_decisions: tuple[LoggedDecision, ...]
    combat_episodes: tuple[Any, ...]
    final_deck_cards: tuple[str, ...]
    encountered_enemy_keys: tuple[str, ...]

    @property
    def estimated_tokens(self) -> int:
        return sum(stat.estimated_tokens for stat in self.section_stats)


@dataclass(frozen=True)
class ReplayEntry:
    """One selected replay plus optional same-enemy comparator."""

    episode: Any
    selection_reasons: tuple[str, ...]
    historical_line: str = ""
    anomaly_label: str = ""
    anomaly_score: float | None = None
    comparator_episode: Any | None = None
    comparator_reason: str = ""
    strategic_notes: tuple[tuple[int, str], ...] = ()  # agent intent captured during this combat

    def to_summary_dict(self) -> dict[str, Any]:
        payload = {
            "enemy_key": getattr(self.episode, "enemy_key", ""),
            "floor": getattr(self.episode, "floor", 0),
            "combat_type": getattr(self.episode, "combat_type", ""),
            "selection_reasons": list(self.selection_reasons),
        }
        if self.historical_line:
            payload["historical_line"] = self.historical_line
        if self.anomaly_label:
            payload["anomaly_label"] = self.anomaly_label
        if self.anomaly_score is not None:
            payload["anomaly_score"] = self.anomaly_score
        if self.comparator_episode is not None:
            payload["comparator"] = {
                "enemy_key": getattr(self.comparator_episode, "enemy_key", ""),
                "floor": getattr(self.comparator_episode, "floor", 0),
                "combat_type": getattr(self.comparator_episode, "combat_type", ""),
                "reason": self.comparator_reason,
            }
        return payload


@dataclass(frozen=True)
class ReplayPackage:
    """Selected high-value replay evidence for evolution."""

    entries: tuple[ReplayEntry, ...]
    estimated_tokens: int


def estimate_tokens(text: str) -> int:
    """Rough token estimate used for section budgeting and artifacts."""
    if not text:
        return 0
    return max(1, math.ceil(len(text) / 4))


def _deck_card_name(card_payload: dict[str, Any]) -> str:
    """Normalize logged deck cards into a readable stable name."""
    name = str(card_payload.get("name", "") or "").strip()
    if not name:
        return ""
    if card_payload.get("upgraded") and not name.endswith("+"):
        return f"{name}+"
    return name


def _parse_state_event(event: dict[str, Any]) -> LoggedState | None:
    if event.get("event") != "state":
        return None
    player = event.get("player") or {}
    deck_payload = event.get("deck") or []
    deck_cards = tuple(
        name
        for card in deck_payload
        if isinstance(card, dict)
        for name in (_deck_card_name(card),)
        if name
    )
    return LoggedState(
        step=int(event.get("step", 0) or 0),
        floor=int(event.get("floor", 0) or 0),
        state_type=str(event.get("state_type", "") or ""),
        hp=int(event.get("hp", 0) or 0),
        gold=int(player.get("gold", event.get("gold", 0) or 0) or 0),
        deck_size=int(event.get("deck_size", len(deck_cards)) or 0),
        deck=deck_cards,
        summary=str(event.get("summary", "") or ""),
    )


def load_run_log(run_id: str, *, log_path: Path | None = None) -> tuple[list[LoggedDecision], list[LoggedState]]:
    """Parse the current run JSONL into states and enriched decisions."""
    resolved_path = log_path or (Path(config.LOG_DIR) / f"run_{run_id}.jsonl")
    if not resolved_path.exists():
        logger.warning("Run log not found for %s at %s", run_id, resolved_path)
        return [], []

    events: list[dict[str, Any]] = []
    with resolved_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                events.append(json.loads(raw_line))
            except json.JSONDecodeError:
                logger.warning("Skipping malformed run log line in %s", resolved_path)

    states_by_index: list[tuple[int, LoggedState]] = []
    decision_indices: list[tuple[int, dict[str, Any], LoggedState | None]] = []
    last_state: LoggedState | None = None

    for idx, event in enumerate(events):
        maybe_state = _parse_state_event(event)
        if maybe_state is not None:
            states_by_index.append((idx, maybe_state))
            last_state = maybe_state
            continue
        if event.get("event") == "decision":
            decision_indices.append((idx, event, last_state))

    decisions: list[LoggedDecision] = []
    state_positions = [idx for idx, _ in states_by_index]
    next_state_cursor = 0
    for event_idx, event, before_state in decision_indices:
        while (
            next_state_cursor < len(state_positions)
            and state_positions[next_state_cursor] <= event_idx
        ):
            next_state_cursor += 1
        after_state = None
        if next_state_cursor < len(states_by_index):
            after_state = states_by_index[next_state_cursor][1]
        decisions.append(
            LoggedDecision(
                step=int(event.get("step", 0) or 0),
                floor=int(event.get("floor", 0) or 0),
                state_type=str(event.get("state_type", "") or ""),
                source=str(event.get("source", "") or ""),
                action=event.get("action") if isinstance(event.get("action"), dict) else {},
                reasoning=str(event.get("reasoning", "") or ""),
                before_state=before_state,
                after_state=after_state,
                strategic_note=str(event.get("strategic_note", "") or ""),
            )
        )

    return decisions, [state for _, state in states_by_index]


def _base_card_name(name: str) -> str:
    return name[:-1] if name.endswith("+") else name


def _ordered_counter_elements(counter: Counter[str]) -> list[str]:
    items: list[str] = []
    for name in sorted(counter):
        count = counter[name]
        if count <= 0:
            continue
        if count == 1:
            items.append(name)
        else:
            items.append(f"{name} x{count}")
    return items


def _describe_deck_change(action_name: str, before_deck: tuple[str, ...], after_deck: tuple[str, ...]) -> str:
    before_counter = Counter(before_deck)
    after_counter = Counter(after_deck)
    added_counter = after_counter - before_counter
    removed_counter = before_counter - after_counter

    if not added_counter and not removed_counter:
        if "skip" in action_name.lower():
            return "skipped"
        return "no deck change"

    upgrade_pairs: list[str] = []
    for removed_name in sorted(list(removed_counter)):
        upgraded_name = f"{_base_card_name(removed_name)}+"
        if (
            not removed_name.endswith("+")
            and added_counter.get(upgraded_name, 0) > 0
            and _base_card_name(removed_name) == _base_card_name(upgraded_name)
        ):
            removed_counter[removed_name] -= 1
            if removed_counter[removed_name] <= 0:
                del removed_counter[removed_name]
            added_counter[upgraded_name] -= 1
            if added_counter[upgraded_name] <= 0:
                del added_counter[upgraded_name]
            upgrade_pairs.append(f"{removed_name}->{upgraded_name}")

    parts: list[str] = []
    lower_action = action_name.lower()
    if upgrade_pairs:
        parts.append(f"upgraded {', '.join(upgrade_pairs)}")
    if added_counter and removed_counter:
        verb = "transformed" if "transform" in lower_action else "changed"
        parts.append(
            f"{verb}: +{', '.join(_ordered_counter_elements(added_counter))}; "
            f"-{', '.join(_ordered_counter_elements(removed_counter))}"
        )
    else:
        if added_counter:
            if "buy" in lower_action:
                verb = "bought"
            elif "reward" in lower_action or "choose_reward" in lower_action:
                verb = "picked"
            else:
                verb = "added"
            parts.append(f"{verb} {', '.join(_ordered_counter_elements(added_counter))}")
        if removed_counter:
            verb = "removed" if "remove" in lower_action or "purge" in lower_action else "lost"
            parts.append(f"{verb} {', '.join(_ordered_counter_elements(removed_counter))}")
    return "; ".join(parts) if parts else "no deck change"


def _summarize_action(action: dict[str, Any]) -> str:
    if not action:
        return "unknown_action"
    action_name = str(action.get("action", "") or "unknown_action")
    parts: list[str] = []
    for key, value in action.items():
        if key in {"action", "reasoning", "strategic_note", "analysis"}:
            continue
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            rendered = ",".join(str(item) for item in value)
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    if parts:
        return f"{action_name} ({', '.join(parts)})"
    return action_name


def _format_non_combat_decision(decision: LoggedDecision) -> str:
    before = decision.before_state
    after = decision.after_state
    action_name = str(decision.action.get("action", "") or "")
    action_summary = _summarize_action(decision.action)
    before_hp = before.hp if before else 0
    after_hp = after.hp if after else before_hp
    before_gold = before.gold if before else 0
    after_gold = after.gold if after else before_gold
    before_deck_size = before.deck_size if before else len(before.deck) if before else 0
    after_deck_size = after.deck_size if after else before_deck_size
    before_deck = before.deck if before else ()
    after_deck = after.deck if after else before_deck
    deck_change = _describe_deck_change(action_name, before_deck, after_deck)
    reasoning = decision.reasoning.strip() or "(no reasoning captured)"
    source = decision.source or "unknown"

    lines = [
        f"F{decision.floor} [{decision.state_type}] {action_summary} | source={source}",
        f"  HP {before_hp}->{after_hp} | Gold {before_gold}->{after_gold} | "
        f"Deck {before_deck_size}->{after_deck_size}",
        f"  deck_change: {deck_change}",
        f"  reasoning: {reasoning}",
    ]
    if decision.strategic_note:
        lines.append(f"  strategic_note: {decision.strategic_note.strip()}")
    return "\n".join(lines)


def _format_card_delta(event: Any) -> str:
    """Build a compact annotation string for a single card_play event.

    Returns an empty string if there are no observable effects, otherwise
    returns a comma-joined summary such as '3dmg,1Weak' or '+5blk,power:Afterimage'.
    """
    parts: list[str] = []

    # Damage dealt to enemies
    enemy_deltas = list(getattr(event, "enemy_deltas", ()) or ())
    total_dmg = sum(
        int(getattr(d, "hp", 0) or 0)
        for d in enemy_deltas
        if (getattr(d, "hp", 0) or 0) < 0
    )
    if total_dmg < 0:
        parts.append(f"{-total_dmg}dmg")

    # Block gained by player
    block = getattr(event, "block", None)
    if block:
        try:
            block_val = int(block)
            if block_val > 0:
                parts.append(f"+{block_val}blk")
        except (TypeError, ValueError):
            pass

    # Energy gained by player
    energy = getattr(event, "energy", None)
    if energy:
        try:
            energy_val = int(energy)
            if energy_val > 0:
                parts.append(f"+{energy_val}energy")
        except (TypeError, ValueError):
            pass

    # Player powers applied
    player_powers = list(getattr(event, "powers_changed", ()) or ())
    for pw in player_powers:
        pw_str = str(pw).strip()
        if pw_str:
            parts.append(f"power:{pw_str}")

    # Enemy debuffs
    for delta in enemy_deltas:
        enemy_powers = list(getattr(delta, "powers_changed", ()) or ())
        if enemy_powers:
            debuff_count = len(enemy_powers)
            debuff_names = ",".join(str(p).strip() for p in enemy_powers if str(p).strip())
            parts.append(f"{debuff_count}{debuff_names}")

    # Cards exhausted
    exhausted = list(getattr(event, "cards_exhausted", ()) or ())
    if exhausted:
        parts.append(f"exhaust:{len(exhausted)}")

    return ",".join(parts)


def format_combat_round_digest(episode: Any) -> str:
    """Format one combat as a compact round-by-round digest."""
    result = "WIN" if getattr(episode, "won", False) else "LOSS"
    hp_before = int(getattr(episode, "hp_before", 0) or 0)
    hp_after = int(getattr(episode, "hp_after", 0) or 0)
    loss = max(0, hp_before - hp_after)
    combat_type = getattr(episode, "combat_type", "") or "combat"
    header = (
        f"F{getattr(episode, 'floor', 0)} [{combat_type}] {getattr(episode, 'enemy_key', '')} "
        f"({len(getattr(episode, 'rounds', ()))}R, HP {hp_before}->{hp_after}, "
        f"loss={loss}, {result})"
    )
    round_lines: list[str] = []
    for rnd in getattr(episode, "rounds", ()) or ():
        intents = list(getattr(rnd, "enemy_intents", ()) or ())
        if intents:
            intent_label = "+".join(
                str(intent).replace("Attack", "Atk") for intent in intents
            )
        else:
            intent_label = "?"
        cards = list(getattr(rnd, "cards_played", ()) or ())

        # Build ordered list of card_play event annotations
        card_play_events = [
            ev for ev in (getattr(rnd, "events", ()) or ())
            if getattr(ev, "event_type", "") == "card_play"
        ]
        # Match card_play events to cards by position; annotate each card
        card_annotations: list[str] = []
        for i, card in enumerate(cards):
            annotation = ""
            if i < len(card_play_events):
                annotation = _format_card_delta(card_play_events[i])
            card_annotations.append(f"{card}({annotation})" if annotation else card)

        # Collapse consecutive identical unannotated cards (legacy behaviour preserved)
        collapsed_cards: list[str] = []
        for annotated in card_annotations:
            plain = annotated.split("(")[0].split("*")[0]
            if collapsed_cards and "(" not in annotated and "(" not in collapsed_cards[-1]:
                last = collapsed_cards[-1]
                last_plain = last.split("*")[0]
                if last_plain == plain:
                    if "*" in last:
                        count = int(last.rsplit("*", 1)[-1]) + 1
                        collapsed_cards[-1] = f"{plain}*{count}"
                    else:
                        collapsed_cards[-1] = f"{plain}*2"
                    continue
            collapsed_cards.append(annotated)

        cards_text = "->".join(collapsed_cards) if collapsed_cards else "none"
        round_lines.append(
            f"  R{getattr(rnd, 'round_num', 0)}[{intent_label}]: {cards_text} | "
            f"dealt={getattr(rnd, 'damage_dealt', 0)} taken={getattr(rnd, 'damage_taken', 0)}"
        )
    return header if not round_lines else header + "\n" + "\n".join(round_lines)


def _render_strategic_thread(decisions: tuple[LoggedDecision, ...]) -> str:
    """Render a compact floor-grouped view of strategic_note evolution.

    Dedupes consecutive identical notes and groups by floor so evolution can
    see the agent's intent trajectory without scrolling the full digest.
    """
    notes_by_floor: dict[int, list[tuple[str, str]]] = {}
    for d in decisions:
        note = (d.strategic_note or "").strip()
        if not note:
            continue
        notes_by_floor.setdefault(d.floor, []).append((d.state_type or "", note))

    if not notes_by_floor:
        return ""

    lines = ["## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)"]
    for floor in sorted(notes_by_floor):
        seen_notes: list[tuple[str, str]] = []
        for state_type, note in notes_by_floor[floor]:
            if seen_notes and seen_notes[-1][1] == note:
                continue
            seen_notes.append((state_type, note))
        if not seen_notes:
            continue
        lines.append(f"### F{floor}")
        for state_type, note in seen_notes:
            tag = f"[{state_type}]" if state_type else ""
            lines.append(f"- {tag} {note}".strip())
    return "\n".join(lines)


def build_decision_digest(
    run_state: Any,
    *,
    combat_episodes: list[Any] | tuple[Any, ...] | None = None,
    log_path: Path | None = None,
) -> DecisionDigest:
    """Build a full-run shared digest from the run JSONL and combat episodes."""
    run_id = getattr(run_state, "run_id", "") or ""
    logged_decisions, logged_states = load_run_log(run_id, log_path=log_path)
    all_combat_episodes = tuple(
        sorted(
            (
                ep for ep in (combat_episodes or ())
                if not getattr(ep, "is_aborted", False)
            ),
            key=lambda ep: (getattr(ep, "floor", 0), getattr(ep, "timestamp", 0.0)),
        )
    )

    non_combat = tuple(
        decision
        for decision in logged_decisions
        if decision.state_type not in _COMBAT_STATE_TYPES
    )

    non_combat_text = "\n\n".join(_format_non_combat_decision(decision) for decision in non_combat)
    combat_text = "\n\n".join(format_combat_round_digest(ep) for ep in all_combat_episodes)

    sections: list[str] = ["## Full-run Decision Digest"]
    section_stats: list[SectionStat] = []

    strategic_thread_section = _render_strategic_thread(tuple(logged_decisions))
    if strategic_thread_section:
        sections.append(strategic_thread_section)
        section_stats.append(
            SectionStat(
                name="decision_digest.strategic_thread",
                chars=len(strategic_thread_section),
                estimated_tokens=estimate_tokens(strategic_thread_section),
            )
        )

    combat_header = f"### Combat Decision Digest ({len(all_combat_episodes)} combats)"
    combat_section = combat_header
    if combat_text:
        combat_section += "\n" + combat_text
    else:
        combat_section += "\n(no combat episodes recorded)"
    sections.append(combat_section)
    section_stats.append(
        SectionStat(
            name="decision_digest.combat",
            chars=len(combat_section),
            estimated_tokens=estimate_tokens(combat_section),
        )
    )

    non_combat_header = f"### Non-combat Decisions ({len(non_combat)} decisions)"
    non_combat_section = non_combat_header
    if non_combat_text:
        non_combat_section += "\n" + non_combat_text
    else:
        non_combat_section += "\n(no non-combat decisions recorded)"
    sections.append(non_combat_section)
    section_stats.append(
        SectionStat(
            name="decision_digest.non_combat",
            chars=len(non_combat_section),
            estimated_tokens=estimate_tokens(non_combat_section),
        )
    )

    final_deck = logged_states[-1].deck if logged_states else ()
    encountered_enemy_keys = tuple(
        sorted({str(getattr(ep, "enemy_key", "") or "") for ep in all_combat_episodes if getattr(ep, "enemy_key", "")})
    )

    return DecisionDigest(
        text="\n\n".join(sections),
        section_stats=tuple(section_stats),
        non_combat_decisions=non_combat,
        combat_episodes=all_combat_episodes,
        final_deck_cards=final_deck,
        encountered_enemy_keys=encountered_enemy_keys,
    )


def _hp_loss(episode: Any) -> int:
    hp_before = int(getattr(episode, "hp_before", 0) or 0)
    hp_after = int(getattr(episode, "hp_after", 0) or 0)
    if hp_before > 0:
        return max(0, hp_before - hp_after)
    return max(0, -(int(getattr(episode, "hp_delta", 0) or 0)))


def _historical_details(episode: Any, all_episodes: list[Any]) -> tuple[str, str, float | None]:
    line = historical_comparison(episode, all_episodes) or ""
    if not line:
        return "", "", None
    label_match = _HISTORICAL_LABEL_RE.search(line)
    z_match = _HISTORICAL_Z_RE.search(line)
    label = label_match.group(1) if label_match else ""
    z_score = float(z_match.group(1)) if z_match else None
    return line, label, z_score


def _pick_same_enemy_comparator(
    episode: Any,
    all_episodes: list[Any],
    *,
    prefer: str = "recent",
) -> tuple[Any | None, str]:
    same_enemy = [
        hist
        for hist in all_episodes
        if enemy_key_lookup(getattr(hist, "enemy_key", "")) == enemy_key_lookup(
            getattr(episode, "enemy_key", "")
        )
        and getattr(hist, "run_id", "") != getattr(episode, "run_id", "")
        and not getattr(hist, "is_aborted", False)
    ]
    if not same_enemy:
        return None, ""

    this_loss = _hp_loss(episode)
    if prefer == "better":
        candidates = [hist for hist in same_enemy if _hp_loss(hist) < this_loss]
        if candidates:
            candidates.sort(key=lambda hist: (-float(getattr(hist, "timestamp", 0.0) or 0.0), _hp_loss(hist)))
            return candidates[0], "recent better same-enemy comparator"
    elif prefer == "worse":
        candidates = [hist for hist in same_enemy if _hp_loss(hist) > this_loss]
        if candidates:
            candidates.sort(key=lambda hist: (-float(getattr(hist, "timestamp", 0.0) or 0.0), -_hp_loss(hist)))
            return candidates[0], "recent worse/typical same-enemy comparator"

    same_enemy.sort(key=lambda hist: -float(getattr(hist, "timestamp", 0.0) or 0.0))
    return same_enemy[0], "recent same-enemy comparator"


def _estimate_replay_entry_tokens(entry: ReplayEntry) -> int:
    chunks = [
        format_combat_replay(
            entry.episode,
            max_rounds=999,
            strategic_notes=list(entry.strategic_notes),
        ),
        format_analytics(entry.episode),
    ]
    if entry.historical_line:
        chunks.append(f"Historical: {entry.historical_line}")
    if entry.comparator_episode is not None:
        chunks.append(format_combat_replay(entry.comparator_episode, max_rounds=999))
        chunks.append(format_analytics(entry.comparator_episode))
    return estimate_tokens("\n\n".join(chunk for chunk in chunks if chunk))


def build_replay_package(
    memory_manager: Any,
    run_id: str,
    *,
    anomaly_worse_limit: int = 2,
    anomaly_better_limit: int = 2,
    replay_token_budget: int = 22000,
    log_path: Path | None = None,
) -> ReplayPackage:
    """Select high-value mandatory and anomalous replays with same-enemy comparators."""
    combat_store = getattr(memory_manager, "combat_store", None)
    if combat_store is None:
        return ReplayPackage(entries=(), estimated_tokens=0)

    all_episodes = [
        ep for ep in combat_store.get_all()
        if not getattr(ep, "is_aborted", False)
    ]
    run_episodes = [
        ep for ep in all_episodes
        if getattr(ep, "run_id", "") == run_id
    ]
    run_episodes.sort(key=lambda ep: (getattr(ep, "floor", 0), getattr(ep, "timestamp", 0.0)))
    if not run_episodes:
        return ReplayPackage(entries=(), estimated_tokens=0)

    strategic_notes_map = load_combat_strategic_notes(run_id, log_path=log_path)

    selected_entries: list[ReplayEntry] = []
    selected_ids: set[str] = set()

    def _maybe_add(entry: ReplayEntry, *, mandatory: bool = False) -> None:
        episode_id = str(getattr(entry.episode, "episode_id", "") or "")
        if episode_id in selected_ids:
            return
        entry_tokens = _estimate_replay_entry_tokens(entry)
        current_tokens = sum(_estimate_replay_entry_tokens(existing) for existing in selected_entries)
        if not mandatory and current_tokens + entry_tokens > replay_token_budget:
            return
        selected_ids.add(episode_id)
        selected_entries.append(entry)

    anomaly_candidates: list[tuple[str, float, ReplayEntry]] = []

    for episode in run_episodes:
        reasons: list[str] = []
        if getattr(episode, "combat_type", "") == "boss":
            reasons.append("boss")
        if getattr(episode, "combat_type", "") == "elite":
            reasons.append("elite")
        if not getattr(episode, "won", False):
            reasons.append("death")
        hist_line, anomaly_label, anomaly_score = _historical_details(episode, all_episodes)
        prefer = "recent"
        if anomaly_label == "WORSE_THAN_USUAL":
            prefer = "better"
        elif anomaly_label == "BETTER_THAN_USUAL":
            prefer = "worse"
        comparator, comparator_reason = _pick_same_enemy_comparator(
            episode,
            all_episodes,
            prefer=prefer,
        )
        episode_key = (
            int(getattr(episode, "floor", 0) or 0),
            str(getattr(episode, "enemy_key", "") or ""),
        )
        ep_notes = tuple(strategic_notes_map.get(episode_key, ()))
        entry = ReplayEntry(
            episode=episode,
            selection_reasons=tuple(reasons) if reasons else ("run_combat",),
            historical_line=hist_line,
            anomaly_label=anomaly_label,
            anomaly_score=anomaly_score,
            comparator_episode=comparator,
            comparator_reason=comparator_reason,
            strategic_notes=ep_notes,
        )
        if reasons:
            _maybe_add(entry, mandatory=True)
        elif anomaly_label == "WORSE_THAN_USUAL" and anomaly_score is not None:
            anomaly_candidates.append(("worse", anomaly_score, entry))
        elif anomaly_label == "BETTER_THAN_USUAL" and anomaly_score is not None:
            anomaly_candidates.append(("better", anomaly_score, entry))

    worse = sorted(
        (candidate for candidate in anomaly_candidates if candidate[0] == "worse"),
        key=lambda item: item[1],
        reverse=True,
    )[:anomaly_worse_limit]
    better = sorted(
        (candidate for candidate in anomaly_candidates if candidate[0] == "better"),
        key=lambda item: item[1],
    )[:anomaly_better_limit]

    for _kind, _score, entry in worse + better:
        _maybe_add(entry, mandatory=False)

    selected_entries.sort(
        key=lambda entry: (
            getattr(entry.episode, "floor", 0),
            float(getattr(entry.episode, "timestamp", 0.0) or 0.0),
        )
    )
    estimated_tokens = sum(_estimate_replay_entry_tokens(entry) for entry in selected_entries)
    return ReplayPackage(entries=tuple(selected_entries), estimated_tokens=estimated_tokens)


def load_combat_strategic_notes(
    run_id: str,
    *,
    log_path: Path | None = None,
) -> dict[tuple[int, str], list[tuple[int, str]]]:
    """Load strategic_notes per combat from combat_summary events.

    Returns a map from (floor, enemy_key) to a list of (round, note) tuples.
    When the same (floor, enemy_key) appears more than once in a run (e.g.
    save/quit replay), later entries append to the existing list — good enough
    for evolution readability without introducing a stricter occurrence index.
    """
    resolved_path = log_path or (Path(config.LOG_DIR) / f"run_{run_id}.jsonl")
    if not resolved_path.exists():
        return {}
    notes_map: dict[tuple[int, str], list[tuple[int, str]]] = {}
    with resolved_path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                event = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if event.get("event") != "combat_summary":
                continue
            raw_notes = event.get("strategic_notes") or []
            if not raw_notes:
                continue
            floor = int(event.get("floor", 0) or 0)
            enemy_key = str(event.get("enemy_key", "") or "")
            key = (floor, enemy_key)
            bucket = notes_map.setdefault(key, [])
            for item in raw_notes:
                if not isinstance(item, dict):
                    continue
                try:
                    rnd = int(item.get("round", 0) or 0)
                except (TypeError, ValueError):
                    rnd = 0
                note = str(item.get("note", "") or "").strip()
                if note:
                    bucket.append((rnd, note))
    return notes_map


def format_combat_replay(
    episode: Any,
    max_rounds: int = 5,
    *,
    strategic_notes: list[tuple[int, str]] | None = None,
) -> str:
    """Format a CombatEpisode as readable replay text with all events.

    If ``strategic_notes`` is provided, each note is printed under its round as
    an "Intent (agent hypothesis, not ground truth)" line so the evolution LLM
    can compare agent intent vs outcome without confusing them with real events.
    """
    lines: list[str] = []
    combat_type = getattr(episode, "combat_type", "") or "combat"
    lines.append(
        f"## Combat Replay: vs {getattr(episode, 'enemy_key', '')} "
        f"(Floor {getattr(episode, 'floor', 0)}, {combat_type})"
    )
    context = getattr(episode, "context", None)
    if context is not None:
        relics = getattr(context, "relics", ()) or ()
        if relics:
            lines.append(
                "Relics: " + ", ".join(
                    f"{relic.name} (stack={relic.stack})" if getattr(relic, "stack", None) is not None else relic.name
                    for relic in relics
                )
            )
        deck_cards = getattr(context, "deck_cards", ()) or ()
        if deck_cards:
            deck_counts = Counter(deck_cards)
            rendered = ", ".join(
                f"{name} x{count}" if count > 1 else name
                for name, count in sorted(deck_counts.items(), key=lambda item: (-item[1], item[0]))
            )
            lines.append(f"Deck ({len(deck_cards)}): {rendered}")
        enemy_lineup = getattr(context, "enemy_lineup", ()) or ()
        if enemy_lineup:
            lines.append(
                "Enemies: " + ", ".join(
                    f"{enemy.name} HP={enemy.hp}/{enemy.max_hp}"
                    for enemy in enemy_lineup
                )
            )
    lines.append("")

    notes_by_round: dict[int, list[str]] = {}
    for rnd_num, note in strategic_notes or ():
        notes_by_round.setdefault(int(rnd_num), []).append(note)

    rounds = list(getattr(episode, "rounds", ()) or ())
    if max_rounds > 0 and len(rounds) > max_rounds:
        rounds = rounds[-max_rounds:]
    for rnd in rounds:
        round_num = int(getattr(rnd, "round_num", 0) or 0)
        lines.append(f"### Round {round_num}")
        agent_notes = notes_by_round.get(round_num) or []
        for note in agent_notes:
            lines.append(f"Agent plan (hypothesis): {note}")
        intents = list(getattr(rnd, "enemy_intents", ()) or ())
        if intents:
            lines.append("Intent: " + ", ".join(str(intent) for intent in intents))
        events = list(getattr(rnd, "events", ()) or ())
        if events:
            for delta in events:
                source = getattr(delta, "source", None) or getattr(delta, "event_type", "")
                target = f" -> {getattr(delta, 'target', '')}" if getattr(delta, "target", "") else ""
                parts = [f"  {source}{target}"]
                details: list[str] = []
                if getattr(delta, "energy", None) is not None:
                    details.append(f"energy {getattr(delta, 'energy'):+d}")
                if getattr(delta, "hp", None) is not None:
                    details.append(f"hp {getattr(delta, 'hp'):+d}")
                if getattr(delta, "block", None) is not None:
                    details.append(f"block {getattr(delta, 'block'):+d}")
                power_changes = list(getattr(delta, "powers_changed", ()) or ())
                details.extend(str(change) for change in power_changes)
                exhausted = list(getattr(delta, "cards_exhausted", ()) or ())
                if exhausted:
                    details.append("exhausted: " + ", ".join(str(card) for card in exhausted))
                enemy_deltas = list(getattr(delta, "enemy_deltas", ()) or ())
                if enemy_deltas:
                    details.append(
                        "enemy_deltas: " + "; ".join(
                            _format_enemy_delta(enemy_delta) for enemy_delta in enemy_deltas
                        )
                    )
                if details:
                    parts.append("    " + " | ".join(details))
                lines.extend(parts)
        else:
            cards = ", ".join(getattr(rnd, "cards_played", ()) or ()) or "none"
            lines.append(
                f"  cards: {cards}, dealt={getattr(rnd, 'damage_dealt', 0)}, "
                f"taken={getattr(rnd, 'damage_taken', 0)}"
            )
        lines.append("")

    return "\n".join(lines).strip()


def build_card_mechanics_section(
    log_path: Path,
    run_id: str,
) -> tuple[str, tuple[str, ...]]:
    """Extract card mechanics from run log.

    Returns (formatted_section, seen_card_names) where seen_card_names
    is the deduplicated tuple of all card names encountered in the run.
    """
    from src.brain.prompts._keyword_fmt import KW_GLOSSARY

    seen: dict[str, str] = {}  # card_base_name -> rules_text

    if not log_path.exists():
        return "", ()

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("event") != "state":
                continue

            # Combat hand cards
            combat = d.get("combat")
            if combat:
                for card in combat.get("player", {}).get("hand", []):
                    _collect_card(seen, card)

            # Card reward options
            crd = d.get("card_reward_details")
            if crd:
                for card in crd.get("card_options", []):
                    _collect_card(seen, card)

            # Card select options
            sd = d.get("selection_details")
            if sd:
                for card in sd.get("cards", []):
                    _collect_card(seen, card)

            # Shop cards
            shop = d.get("shop_details")
            if shop:
                for card in shop.get("cards", []):
                    _collect_card(seen, card)

    if not seen:
        return "", ()

    # Build output: show both base and upgraded versions when both exist
    lines = ["## Card Mechanics Reference (seen this run)"]
    for name in sorted(seen.keys()):
        lines.append(f"- {name}: {seen[name]}")

    # Keyword glossary
    all_text = " ".join(rt.lower() for rt in seen.values())
    matched_kw = [desc for kw, desc in KW_GLOSSARY.items() if kw in all_text]
    if matched_kw:
        lines.append("")
        lines.append("### Keywords")
        for desc in matched_kw:
            lines.append(f"- {desc}")

    # seen_card_names: deduplicate by base name (strip '+') for note/stats lookup
    base_names: dict[str, None] = {}
    for name in seen:
        base_names[name.rstrip("+")] = None
    return "\n".join(lines), tuple(base_names.keys())


def build_relic_context(log_path: Path, run_id: str) -> str:
    """Extract all relics seen across the entire run from combat state snapshots.

    Scans every combat state to catch relics picked up later in the run.
    The log only records relic name + stack (no description), so descriptions
    are best-effort from whichever source provides them.
    """
    if not log_path.exists():
        return ""

    # Collect all unique relics in order of first appearance
    seen_relics: dict[str, str] = {}  # name -> description (may be empty)

    with open(log_path, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if d.get("event") != "state":
                continue
            combat = d.get("combat")
            if not combat:
                continue
            relics = combat.get("player", {}).get("relics", [])
            for r in relics:
                name = r.get("name", "")
                if not name:
                    continue
                desc = r.get("description", "")
                # Keep first non-empty description, or update if we find one later
                if name not in seen_relics or (not seen_relics[name] and desc):
                    seen_relics[name] = desc

    if not seen_relics:
        return ""

    lines = ["## Run Relics"]
    for name, desc in seen_relics.items():
        lines.append(f"- {name}: {desc}" if desc else f"- {name}")
    return "\n".join(lines)


def _collect_card(seen: dict[str, str], card: dict) -> None:
    """Add a card to the seen dict if it has rules_text.

    Keeps base and upgraded versions separate (keyed by exact name).
    The caller deduplicates for seen_card_names by stripping '+'.
    """
    name = card.get("name", "")
    rules_text = card.get("rules_text", "")
    if not name or not rules_text:
        return
    if name not in seen:
        seen[name] = rules_text


def _format_enemy_delta(enemy_delta: Any) -> str:
    label = getattr(enemy_delta, "name", "") or getattr(enemy_delta, "enemy_id", "") or "enemy"
    parts: list[str] = []
    if getattr(enemy_delta, "hp", None) is not None:
        parts.append(f"hp {getattr(enemy_delta, 'hp'):+d}")
    if getattr(enemy_delta, "block", None) is not None:
        parts.append(f"block {getattr(enemy_delta, 'block'):+d}")
    power_changes = list(getattr(enemy_delta, "powers_changed", ()) or ())
    parts.extend(str(change) for change in power_changes)
    if getattr(enemy_delta, "died", False):
        parts.append("DIED")
    return f"{label}: {', '.join(parts)}" if parts else label


# ── Evolution context renderers (absorbed from evolution_engine.py) ──────────


@dataclass(frozen=True)
class EvolutionContextBundle:
    """Rendered evolution prompt plus artifact-ready section metadata."""

    text: str
    section_stats: tuple[SectionStat, ...]
    summary: dict[str, Any]
    seen_card_names: tuple[str, ...] = ()

    @property
    def estimated_tokens(self) -> int:
        return sum(section.estimated_tokens for section in self.section_stats)


def _truncate_at_boundary(text: str, max_chars: int) -> str:
    """Truncate *text* to *max_chars* at the nearest natural boundary.

    Tries sentence end (". "), clause end ("; "), newline, then word boundary
    in that order.  Never truncates below half of *max_chars* to avoid
    over-aggressive cuts.  Used as a deterministic fallback when LLM-based
    auto-compression fails.
    """
    if len(text) <= max_chars:
        return text
    floor = max_chars // 2
    chunk = text[:max_chars]
    for sep in (". ", ".\n", "; ", ";\n", "\n", ", ", " "):
        idx = chunk.rfind(sep)
        if idx >= floor:
            return chunk[:idx + len(sep)].rstrip()
    # Last resort: hard cut
    return chunk.rstrip()


def _format_delta_line(delta: Any) -> str:
    """Format one CombatDelta event as an indented text line."""
    # Action header: "  play CardName → Target[idx]" or "  end_turn → round N+1"
    source = delta.source or delta.event_type
    target_str = f" → {delta.target}" if delta.target else ""
    header = f"  {source}{target_str}"

    # Collect non-None player deltas
    parts: list[str] = []
    if delta.energy is not None:
        parts.append(f"Δ energy: {delta.energy:+d}")
    if delta.hp is not None:
        parts.append(f"Δ hp: {delta.hp:+d}")
    if delta.block is not None:
        parts.append(f"Δ block: {delta.block:+d}")
    if delta.powers_changed:
        parts.extend(delta.powers_changed)
    if delta.cards_exhausted:
        parts.append(f"exhausted: {', '.join(delta.cards_exhausted)}")
    if delta.relic_changes:
        parts.append(f"relic: {', '.join(delta.relic_changes)}")
    if delta.enemy_deltas:
        parts.append(_format_enemy_deltas(delta.enemy_deltas))

    if parts:
        return f"{header}\n    {' | '.join(parts)}"
    return header


def _format_enemy_deltas(deltas: tuple[Any, ...]) -> str:
    """Compact per-enemy changes like 'Toadpole: hp -6'."""
    parts: list[str] = []
    for ed in deltas:
        pieces: list[str] = []
        if ed.hp is not None:
            pieces.append(f"hp {ed.hp:+d}")
        if ed.block is not None:
            pieces.append(f"block {ed.block:+d}")
        if ed.powers_changed:
            pieces.extend(ed.powers_changed)
        if ed.died:
            pieces.append("DIED")
        if pieces:
            label = ed.name or ed.enemy_id or f"enemy[{ed.index}]"
            parts.append(f"{label}: {', '.join(pieces)}")
    return " | ".join(parts)


def _select_smart_episodes(
    memory_manager: Any,
    run_id: str,
) -> list[Any]:
    """Smart combat selection: all boss + elite + death + z-score anomalies.

    No fixed cap. Selection rules:
    - All boss combats (mandatory)
    - All elite combats (mandatory)
    - Death combat (mandatory)
    - Anomalous worse: z-score > 1.5 vs historical avg (requires 3+ history)
    - Anomalous better: z-score < -1.0 AND historical avg loss > 5

    Only returns episodes with non-empty events in at least one round.
    """
    combat_store = getattr(memory_manager, "combat_store", None)
    if combat_store is None:
        return []

    all_episodes = combat_store.get_all()
    run_episodes = [
        ep for ep in all_episodes
        if ep.run_id == run_id and not getattr(ep, "is_aborted", False)
    ]

    if not run_episodes:
        return []

    def _has_events(ep: Any) -> bool:
        return any(rnd.events for rnd in ep.rounds)

    candidates = [ep for ep in run_episodes if _has_events(ep)]

    selected_ids: set[str] = set()
    selected: list[Any] = []

    def _add(ep: Any) -> None:
        if ep.episode_id not in selected_ids:
            selected_ids.add(ep.episode_id)
            selected.append(ep)

    # 1. All boss combats
    for ep in candidates:
        if ep.combat_type == "boss":
            _add(ep)

    # 2. All elite combats
    for ep in candidates:
        if ep.combat_type == "elite":
            _add(ep)

    # 3. Death combat(s)
    for ep in candidates:
        if not ep.won:
            _add(ep)

    # 4. Z-score anomalies — delegate to historical_comparison (single source of truth)
    for ep in candidates:
        if ep.episode_id in selected_ids:
            continue
        result = historical_comparison(ep, all_episodes)
        if result and ("WORSE_THAN_USUAL" in result or "BETTER_THAN_USUAL" in result):
            _add(ep)

    # Sort by floor for readability
    selected.sort(key=lambda ep: ep.floor)
    return selected


def _section(name: str, text: str) -> tuple[str, SectionStat]:
    clean = text.strip()
    return clean, SectionStat(name=name, chars=len(clean), estimated_tokens=estimate_tokens(clean))


def _render_summary(run_state: Any) -> tuple[str, SectionStat]:
    character = getattr(run_state, "character", "Unknown")
    victory = getattr(run_state, "victory", False)
    final_floor = getattr(run_state, "final_floor", 0)
    fitness = run_state.fitness() if hasattr(run_state, "fitness") else 0.0
    result_str = "VICTORY" if victory else f"DEFEAT at Floor {final_floor}"
    text = (
        f"You just completed a Slay the Spire 2 run as {character}.\n"
        f"Result: {result_str} (fitness: {fitness:.1f})\n"
        f"Combats won: {getattr(run_state, 'combats_won', 0)}/{getattr(run_state, 'combats_total', 0)}\n"
        f"Run duration: {getattr(run_state, 'duration_seconds', 0.0):.1f}s"
    )
    return _section("run_summary", text)


def _render_dynamic_tools(dynamic_registry: Any | None) -> tuple[str, SectionStat]:
    lines = ["## Dynamic Tools"]
    if dynamic_registry is None:
        lines.append("None yet.")
        return _section("dynamic_tools", "\n".join(lines))
    stats = dynamic_registry.stats()
    if not stats:
        lines.append("None yet.")
        return _section("dynamic_tools", "\n".join(lines))
    for name, data in sorted(stats.items()):
        if not isinstance(data, dict):
            continue
        usage_count = int(data.get("usage_count", 0) or 0)
        success_count = int(data.get("success_count", 0) or 0)
        lines.append(f"- {name}: {usage_count} calls, {success_count} successes")
    return _section("dynamic_tools", "\n".join(lines))


def _render_replay_package(replay_package: ReplayPackage) -> tuple[str, SectionStat]:
    lines = [f"## Selected Replay Package ({len(replay_package.entries)} replays)"]
    if not replay_package.entries:
        lines.append("(no replay package available)")
        return _section("replay_package", "\n".join(lines))
    for entry in replay_package.entries:
        reasons = ", ".join(entry.selection_reasons)
        header = (
            f"[Selected: {reasons}] {getattr(entry.episode, 'enemy_key', '')} "
            f"(F{getattr(entry.episode, 'floor', 0)}, {getattr(entry.episode, 'combat_type', '')})"
        )
        lines.append(header)
        if entry.historical_line:
            lines.append(f"Historical: {entry.historical_line}")
        lines.append(
            format_combat_replay(
                entry.episode,
                max_rounds=999,
                strategic_notes=list(getattr(entry, "strategic_notes", ()) or ()),
            )
        )
        analytics = format_analytics(entry.episode)
        if analytics:
            lines.append(analytics)
        if entry.comparator_episode is not None:
            lines.append(f"Comparator ({entry.comparator_reason}):")
            lines.append(format_combat_replay(entry.comparator_episode, max_rounds=999))
            comparator_analytics = format_analytics(entry.comparator_episode)
            if comparator_analytics:
                lines.append(comparator_analytics)
        lines.append("")
    return _section("replay_package", "\n".join(lines))


def _render_triggered_skills(skill_triggers: list[dict[str, Any]] | None) -> tuple[str, SectionStat]:
    lines = ["## Triggered Skills This Run"]
    if not skill_triggers:
        lines.append("(no triggered skills captured)")
        return _section("triggered_skills", "\n".join(lines))
    grouped: dict[str, list[str]] = {}
    for trigger in skill_triggers:
        skill_name = str(trigger.get("skill_name", "unknown") or "unknown")
        floor_num = trigger.get("floor", "?")
        enemy = str(trigger.get("enemy", "") or "")
        result = str(trigger.get("result", "") or "")
        grouped.setdefault(skill_name, [])
        grouped[skill_name].append(
            f"F{floor_num}({enemy}: {result})" if enemy else f"F{floor_num}({result})"
        )
    for skill_name, items in sorted(grouped.items()):
        lines.append(f"- {skill_name}: {', '.join(items)}")
    return _section("triggered_skills", "\n".join(lines))


def build_evolution_context(
    run_state: Any,
    decision_digest: DecisionDigest | Any | None = None,
    replay_package: ReplayPackage | Any | None = None,
    *,
    dynamic_registry: Any | None = None,
    memory_manager: Any | None = None,
    skill_triggers: list[dict[str, Any]] | None = None,
    log_path: Path | None = None,
    return_bundle: bool = False,
) -> str | EvolutionContextBundle:
    """Build the heavy evolution prompt from shared decision/replay builders."""
    if decision_digest is not None and not isinstance(decision_digest, DecisionDigest):
        dynamic_registry = decision_digest if dynamic_registry is None else dynamic_registry
        decision_digest = None
    if replay_package is not None and not isinstance(replay_package, ReplayPackage):
        memory_manager = replay_package if memory_manager is None else memory_manager
        replay_package = None

    run_id = getattr(run_state, "run_id", "") or ""
    character = getattr(run_state, "character", "Unknown")
    if decision_digest is None:
        combat_episodes = []
        if memory_manager is not None and getattr(memory_manager, "combat_store", None) is not None:
            combat_episodes = [
                ep for ep in memory_manager.combat_store.get_all()
                if getattr(ep, "run_id", "") == run_id
                and not getattr(ep, "is_aborted", False)
            ]
        decision_digest = build_decision_digest(
            run_state,
            combat_episodes=combat_episodes,
            log_path=log_path,
        )
    if replay_package is None:
        replay_package = (
            build_replay_package(
                memory_manager,
                run_id,
                anomaly_worse_limit=config.EVOLUTION_ANOMALY_WORSE_LIMIT,
                anomaly_better_limit=config.EVOLUTION_ANOMALY_BETTER_LIMIT,
                replay_token_budget=config.EVOLUTION_REPLAY_TOKEN_BUDGET,
                log_path=log_path,
            )
            if memory_manager is not None
            else ReplayPackage(entries=(), estimated_tokens=0)
        )

    card_mechanics_text = ""
    seen_card_names: tuple[str, ...] = decision_digest.final_deck_cards  # fallback
    if log_path is not None:
        _cm_text, _cm_names = build_card_mechanics_section(log_path, run_id)
        if _cm_text:
            card_mechanics_text = _cm_text
        if _cm_names:
            seen_card_names = _cm_names

    relic_text = ""
    if log_path is not None:
        relic_text = build_relic_context(log_path, run_id)

    sections: list[str] = []
    section_stats: list[SectionStat] = []

    summary_text, summary_stat = _render_summary(run_state)
    sections.append(summary_text)
    section_stats.append(summary_stat)

    sections.append(decision_digest.text)
    section_stats.extend(decision_digest.section_stats)

    replay_text, replay_stat = _render_replay_package(replay_package)
    sections.append(replay_text)
    section_stats.append(replay_stat)

    if memory_manager is not None:
        if card_mechanics_text:
            cm_text, cm_stat = _section("card_mechanics", card_mechanics_text)
            sections.append(cm_text)
            section_stats.append(cm_stat)

        if relic_text:
            rel_text, rel_stat = _section("relics", relic_text)
            sections.append(rel_text)
            section_stats.append(rel_stat)

    triggered_text, triggered_stat = _render_triggered_skills(skill_triggers)
    sections.append(triggered_text)
    section_stats.append(triggered_stat)

    dynamic_tools_text, dynamic_tools_stat = _render_dynamic_tools(dynamic_registry)
    sections.append(dynamic_tools_text)
    section_stats.append(dynamic_tools_stat)

    focus_text, focus_stat = _section(
        "focus",
        "## Focus\n"
        "Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, "
        "write the smallest number of high-value improvements that fix the observed mistakes. "
        "When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.",
    )
    sections.append(focus_text)
    section_stats.append(focus_stat)

    summary = {
        "run_id": run_id,
        "section_stats": [section.to_dict() for section in section_stats],
        "decision_digest": {
            "estimated_tokens": decision_digest.estimated_tokens,
            "non_combat_decisions": len(decision_digest.non_combat_decisions),
            "combat_episodes": len(decision_digest.combat_episodes),
            "encountered_enemy_keys": list(decision_digest.encountered_enemy_keys),
            "final_deck_cards": list(decision_digest.final_deck_cards),
        },
        "replay_package": {
            "estimated_tokens": replay_package.estimated_tokens,
            "entries": [entry.to_summary_dict() for entry in replay_package.entries],
        },
    }
    bundle = EvolutionContextBundle(
        text="\n\n".join(section for section in sections if section),
        section_stats=tuple(section_stats),
        summary=summary,
        seen_card_names=seen_card_names,
    )
    return bundle if return_bundle else bundle.text
