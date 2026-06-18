"""Render recent combats as high-fidelity text traces for postrun LLM analysis.

Produces ground-truth combat reconstruction (hand with real values + rules_text,
player/enemy state, intents, agent plans, replans) that Turn 1 (build_analysis)
and Turn 2 (card_note_updater) share under ephemeral prompt cache.

The renderer is pure and does no LLM work. Failures degrade silently:
unrenderable combats are dropped, zero-combat runs return None.
"""

from __future__ import annotations

import logging
from typing import Any

from src.memory.short_term import CombatTracker, ShortTermMemory
from src.memory.combat_trace_plan_grouper import (
    group_decisions_into_blocks,
    format_plan_block_text,
    format_end_turn_block_text,
    format_heuristic_block_text,
    PlanBlock, EndTurnBlock, HeuristicBlock,
)
from src.memory.combat_trace_delta import (
    FirstAppearanceTracker, compute_block_delta, format_block_delta,
)

logger = logging.getLogger(__name__)


def render_last_two_combats(
    short_term: ShortTermMemory,
    run_log_events: list[dict],
    *,
    max_rounds: int = 30,
) -> str | None:
    """Render the 1-2 most recent completed combats as one plaintext trace.

    Returns None when:
    - short_term has zero completed combats
    - all candidate combats are unrenderable (e.g. exceed max_rounds or
      have no matchable state snapshots)

    Otherwise returns a newline-joined plaintext block suitable for
    direct inclusion in a user-message cached prefix.
    """
    completed = list(short_term.completed_combats or [])
    if not completed:
        return None

    # Take up to the last 2 completed combats.
    candidates = completed[-2:]
    rendered_blocks: list[str] = []
    for i, combat in enumerate(candidates, start=1):
        block = _render_single_combat(
            combat_index=i, combat=combat,
            run_log_events=run_log_events, max_rounds=max_rounds,
        )
        if block is not None:
            rendered_blocks.append(block)

    if not rendered_blocks:
        return None

    header = (
        "## Recent Combat Traces (ground truth)\n\n"
        "Below are round-by-round traces of the 1-2 most recent combats. "
        "Each round shows the real hand with exact values and rules_text, "
        "enemy state and intent, the agent's plan and reasoning, and any "
        "replans. Use these to ground downstream reasoning in what actually "
        "happened rather than what aggregated counts suggest.\n"
    )
    return header + "\n\n".join(rendered_blocks)


def extract_candidate_cards(combats: list[Any]) -> list[str]:
    """Return deduplicated, order-preserving list of card names appearing
    across hand_at_start and cards_played of the provided combats.

    Case is preserved; first occurrence determines order.

    Accepts either real CombatTracker objects or dicts with the shape
    ``{hand_at_start_per_round: [[str,...],...], cards_played_per_round: [[str,...],...]}``
    for test convenience.
    """
    seen: dict[str, None] = {}  # insertion-ordered dedup in Python 3.7+
    for combat in combats:
        hand_rounds: list[list[str]] = []
        played_rounds: list[list[str]] = []
        if isinstance(combat, dict):
            hand_rounds = combat.get("hand_at_start_per_round", []) or []
            played_rounds = combat.get("cards_played_per_round", []) or []
        else:
            for rnd in getattr(combat, "rounds", []) or []:
                hand_rounds.append(list(getattr(rnd, "hand_at_start", []) or []))
                played_rounds.append(list(getattr(rnd, "cards_played", []) or []))

        for names in hand_rounds:
            for n in names:
                if n:
                    card_name = str(n).strip()
                    if card_name:
                        seen[card_name] = None
        for names in played_rounds:
            for n in names:
                if n:
                    card_name = str(n).strip()
                    if card_name:
                        seen[card_name] = None
    return list(seen.keys())


def _render_single_combat(
    *,
    combat_index: int,
    combat: CombatTracker,
    run_log_events: list[dict],
    max_rounds: int,
) -> str | None:
    """Render one combat. Returns None if the combat has too many rounds
    or cannot be matched against any state snapshot."""
    rounds = getattr(combat, "rounds", []) or []
    if not rounds:
        return None
    if len(rounds) > max_rounds:
        logger.info(
            "postrun_trace: combat %d dropped (rounds=%d > max=%d)",
            combat_index, len(rounds), max_rounds,
        )
        return None

    lines: list[str] = []
    lines.append(
        f"## Combat {combat_index} — {combat.enemy_key} "
        f"(floor {combat.floor}, {combat.act}, {combat.combat_type})"
    )

    # Pre-combat relic block (from first matched snapshot, else from tracker).
    first_snapshot = _find_first_snapshot_for_combat(run_log_events, combat)
    relics_block = _render_relics(first_snapshot, combat)
    if relics_block:
        lines.append(relics_block)

    lines.append(
        f"HP before: {combat.hp_before} → after: {combat.hp_after}. "
        f"Deck size at start: {combat.deck_size}."
    )

    # Initialize per-combat first-appearance tracker from round 1's snapshot.
    tracker = _init_tracker(first_snapshot)

    # Build a lookup of decisions and replans by (floor, round_num)
    decisions_by_round = _index_decisions(run_log_events, combat.floor)

    for rnd in rounds:
        block = _render_round(
            combat=combat, round_obj=rnd,
            run_log_events=run_log_events,
            decisions=decisions_by_round.get(rnd.round_num, []),
            tracker=tracker,
        )
        lines.append(block)

    return "\n".join(lines)


def _init_tracker(first_snapshot: dict | None) -> FirstAppearanceTracker:
    if first_snapshot is None:
        return FirstAppearanceTracker.from_starting_state([], [])
    player = ((first_snapshot.get("combat") or {}).get("player") or {})
    return FirstAppearanceTracker.from_starting_state(
        player.get("hand") or [],
        player.get("powers") or [],
    )


def _render_round(
    *,
    combat: CombatTracker,
    round_obj: Any,
    run_log_events: list[dict],
    decisions: list[dict],
    tracker: FirstAppearanceTracker,
) -> str:
    """Render a single combat round."""
    from src.memory.core_engine_extractor import _find_matching_state_snapshot

    snapshot = _find_matching_state_snapshot(
        run_log_events, floor=combat.floor, round_num=round_obj.round_num,
    )
    lines: list[str] = []
    lines.append(
        f"\n-- Round {round_obj.round_num} -- "
        f"energy {round_obj.energy_available}, "
        f"hp {round_obj.hp_start}→{round_obj.hp_end}, "
        f"dmg_dealt {round_obj.damage_dealt}, "
        f"dmg_taken {round_obj.damage_taken}, "
        f"block_gained {round_obj.block_gained}"
    )

    # Hand with real values + rules_text
    hand_block = _render_hand(snapshot, round_obj)
    if hand_block:
        lines.append("Hand:\n" + hand_block)

    # Player powers
    powers_block = _render_player_powers(snapshot)
    if powers_block:
        lines.append("Player powers: " + powers_block)

    # Enemies with intents + powers
    enemies_block = _render_enemies(round_obj)
    if enemies_block:
        lines.append("Enemies:\n" + enemies_block)

    # Agent plan blocks with Δ
    plans_block = _render_plans_section(
        decisions=decisions, run_log_events=run_log_events,
        floor=combat.floor, tracker=tracker,
    )
    if plans_block:
        lines.append(plans_block)

    # Cards actually played
    if round_obj.cards_played:
        lines.append(
            f"Cards played this round ({len(round_obj.cards_played)}): "
            + ", ".join(round_obj.cards_played)
        )

    return "\n".join(lines)


def _render_hand(snapshot: dict | None, round_obj: Any) -> str:
    """Render hand cards with full details when a state snapshot is
    available, otherwise fall back to name-only listing."""
    if snapshot:
        combat_state = (snapshot.get("combat") or {})
        player = (combat_state.get("player") or {})
        hand = player.get("hand") or []
        if hand:
            lines: list[str] = []
            for c in hand:
                lines.append(_format_hand_card_line(c))
            return "\n".join(lines)
    names = list(getattr(round_obj, "hand_at_start", []) or [])
    if not names:
        return ""
    return ", ".join(names) + "  (details unavailable)"


def _format_hand_card_line(card: dict) -> str:
    """Format one hand card in high-density form:
    ``- Strike+ (Attack, cost=1) dmg=9, block=0: Deal 9 damage.``
    """
    name = card.get("name") or "?"
    if card.get("upgraded"):
        name = name + "+"
    enchant = card.get("enchantment_name") or ""
    if enchant:
        name = f"{name} [{enchant}]"
    cost = card.get("energy_cost")
    star = card.get("star_cost")
    cost_str = str(cost) if cost is not None else "?"
    if star:
        cost_str = f"{cost_str}★{star}"
    card_type = card.get("card_type") or card.get("type") or "?"

    value_bits: list[str] = []
    if card.get("damage") is not None:
        total = card.get("total_damage")
        if total is not None and total != card.get("damage"):
            value_bits.append(f"dmg={card['damage']}×{card.get('hits', 1)}={total}")
        else:
            value_bits.append(f"dmg={card.get('damage')}")
    if card.get("block") is not None:
        value_bits.append(f"block={card.get('block')}")
    values = " " + ", ".join(value_bits) if value_bits else ""

    rules = card.get("rules_text") or card.get("description") or ""
    return f"- {name} ({card_type}, cost={cost_str}){values}: {rules}"


def _render_relics(snapshot: dict | None, combat: CombatTracker) -> str:
    if not snapshot:
        if combat.relics:
            return "Relics: " + "; ".join(combat.relics)
        return ""
    player = (snapshot.get("combat") or {}).get("player") or {}
    relics = player.get("relics") or []
    if not relics:
        if combat.relics:
            return "Relics: " + "; ".join(combat.relics)
        return ""
    parts = []
    for r in relics:
        name = r.get("name") or "?"
        desc = r.get("description") or ""
        stack = r.get("stack")
        stack_str = f" ×{stack}" if stack and stack != 1 else ""
        parts.append(f"{name}{stack_str} — {desc}" if desc else f"{name}{stack_str}")
    return "Relics:\n- " + "\n- ".join(parts)


def _render_player_powers(snapshot: dict | None) -> str:
    if not snapshot:
        return ""
    player = (snapshot.get("combat") or {}).get("player") or {}
    powers = player.get("powers") or []
    if not powers:
        return ""
    parts = []
    for p in powers:
        name = p.get("name") or "?"
        amount = p.get("amount")
        desc = p.get("description") or ""
        head = f"{name}({amount})" if amount is not None else name
        parts.append(f"{head} — {desc}" if desc else head)
    return "; ".join(parts)


def _render_enemies(round_obj: Any) -> str:
    lines: list[str] = []
    intents = list(getattr(round_obj, "enemy_intents", []) or [])
    enemy_hp = list(getattr(round_obj, "enemy_hp_snapshot", []) or [])
    enemy_powers = list(getattr(round_obj, "enemy_powers_snapshot", []) or [])
    for i, entry in enumerate(enemy_hp):
        try:
            eid, name, hp, max_hp = entry
        except Exception:
            continue
        intent = intents[i] if i < len(intents) else ""
        powers = enemy_powers[i] if i < len(enemy_powers) else []
        power_str = f" [{', '.join(powers)}]" if powers else ""
        intent_str = f" intent={intent}" if intent else ""
        lines.append(f"- {name} ({hp}/{max_hp}){power_str}{intent_str}")
    return "\n".join(lines)


def _render_plans_section(
    *, decisions: list[dict], run_log_events: list[dict],
    floor: int, tracker: FirstAppearanceTracker,
) -> str:
    if not decisions:
        return ""

    blocks = group_decisions_into_blocks(decisions)
    if not blocks:
        return ""

    block_texts: list[str] = []
    for i, block in enumerate(blocks):
        if isinstance(block, PlanBlock):
            text = format_plan_block_text(block)
            pre = _state_event_at_step(run_log_events, floor, block.first_step)
            post = _next_block_pre_snapshot(blocks, i, run_log_events, floor)
            played = [step.card_name for step in block.executed]
            delta = compute_block_delta(pre, post, played)
            delta_text = format_block_delta(delta, tracker) if delta is not None else ""
            if delta_text:
                text = text + "\n" + delta_text
            block_texts.append(text)
        elif isinstance(block, EndTurnBlock):
            block_texts.append(format_end_turn_block_text(block))
        elif isinstance(block, HeuristicBlock):
            block_texts.append(format_heuristic_block_text(block))

    if not block_texts:
        return ""
    return "Plans this round:\n" + "\n\n".join(block_texts)


_COMBAT_STATE_TYPES = ("boss", "monster", "elite")


def _state_event_at_step(
    run_log_events: list[dict], floor: int, step: int,
) -> dict | None:
    """Return the combat-state event at exactly the given step on the given floor.

    Filters by `state_type ∈ ("boss", "monster", "elite")` to avoid returning
    transient non-combat states that may share the same step.
    """
    for ev in run_log_events:
        if ev.get("event") != "state":
            continue
        if ev.get("floor") != floor:
            continue
        if ev.get("state_type") not in _COMBAT_STATE_TYPES:
            continue
        if ev.get("step") == step:
            return ev
    return None


def _next_block_pre_snapshot(
    blocks: list[PlanBlock | EndTurnBlock | HeuristicBlock],
    idx: int, run_log_events: list[dict], floor: int,
) -> dict | None:
    """Snapshot used as 'post' for blocks[idx]."""
    for j in range(idx + 1, len(blocks)):
        nxt = blocks[j]
        nxt_step = _block_first_step(nxt)
        if nxt_step is None:
            continue
        snap = _state_event_at_step(run_log_events, floor, nxt_step)
        if snap is not None:
            return snap
    # Fall back: state event at last_step + 1 of this block
    cur = blocks[idx]
    cur_last = _block_last_step(cur)
    if cur_last is None:
        return None
    return _state_event_at_step(run_log_events, floor, cur_last + 1)


def _block_first_step(block) -> int | None:
    if isinstance(block, PlanBlock):
        return block.first_step if block.first_step >= 0 else None
    if isinstance(block, (EndTurnBlock, HeuristicBlock)):
        return block.decision_step if block.decision_step >= 0 else None
    return None


def _block_last_step(block) -> int | None:
    if isinstance(block, PlanBlock):
        return block.last_step if block.last_step >= 0 else None
    if isinstance(block, (EndTurnBlock, HeuristicBlock)):
        return block.decision_step if block.decision_step >= 0 else None
    return None


def _index_decisions(run_log_events: list[dict], floor: int) -> dict[int, list[dict]]:
    """Return decisions on the given floor, indexed by combat round number."""
    by_round: dict[int, list[dict]] = {}
    for ev in run_log_events:
        if ev.get("event") != "decision":
            continue
        if ev.get("floor") != floor:
            continue
        # combat round is stored on the state event, not decision. We attribute
        # the decision to the most recent state event's round_num by scanning.
        round_num = _derive_decision_round(ev, run_log_events)
        if round_num is None:
            continue
        by_round.setdefault(round_num, []).append(ev)
    return by_round


def _derive_decision_round(
    decision_event: dict, run_log_events: list[dict],
) -> int | None:
    """Find the most recent 'state' event before this decision event
    (same floor) and return its combat.round value."""
    step = decision_event.get("step", -1)
    floor = decision_event.get("floor")
    best: int | None = None
    for ev in run_log_events:
        if ev.get("event") != "state":
            continue
        if ev.get("floor") != floor:
            continue
        ev_step = ev.get("step", -1)
        if ev_step > step:
            continue
        round_num = ((ev.get("combat") or {}).get("round"))
        if round_num is not None:
            best = round_num
    return best


def _find_first_snapshot_for_combat(
    run_log_events: list[dict], combat: CombatTracker,
) -> dict | None:
    from src.memory.core_engine_extractor import _find_matching_state_snapshot

    if not combat.rounds:
        return None
    return _find_matching_state_snapshot(
        run_log_events, floor=combat.floor, round_num=combat.rounds[0].round_num,
    )


# ── Bucket B (postrun): cards offered but not picked ──────────


def extract_skipped_cards(run_log_events: list[dict] | None) -> list[str]:
    """Return cards offered at card_reward / shop but not picked in this run.

    Reads the run JSONL log events directly (same source the trace renderer
    consumes). Returns deduplicated list, order preserved by first
    appearance. Returns ``[]`` on any parse failure — degraded behavior is
    fail-safe for bucket B (validation will then reject all "skipped"
    claims).

    Walks events in order, pairing each ``state`` event of state_type
    "card_reward" / "shop" with its following ``decision`` event(s) of the
    same state_type:

      card_reward: ``decision.action.option_index`` selects ONE card from
        ``state.card_reward_details.card_options``. Any card whose
        ``index`` does not match is treated as skipped. If the picked
        index does not match any card (e.g. the player chose the "skip"
        alternative), every card is skipped. If the run aborts before a
        decision, every card in the un-resolved offer is also skipped.

      shop: each ``decision`` with ``action.action == "buy_card"`` adds
        ``option_index`` to the purchased set; on the next state change
        (or end-of-run) all unsold cards are skipped.
    """
    if not run_log_events:
        return []

    seen: dict[str, None] = {}

    def _flush(entry: tuple[list[tuple[int, str]], set[int]] | None) -> None:
        if not entry:
            return
        offers, picks = entry
        for idx, name in offers:
            if idx in picks:
                continue
            if name:
                seen.setdefault(name, None)

    pending: dict[str, tuple[list[tuple[int, str]], set[int]]] = {}

    for event in run_log_events:
        if not isinstance(event, dict):
            continue
        ev = event.get("event")
        st = event.get("state_type")
        if ev == "state" and st in ("card_reward", "shop"):
            _flush(pending.pop(st, None))
            if st == "card_reward":
                details = event.get("card_reward_details") or {}
                opts = details.get("card_options")
            else:
                details = event.get("shop_details") or {}
                opts = details.get("cards")
            offers: list[tuple[int, str]] = []
            if isinstance(opts, list):
                for opt in opts:
                    if not isinstance(opt, dict):
                        continue
                    idx = opt.get("index")
                    name = opt.get("name")
                    if not isinstance(idx, int) or not isinstance(name, str):
                        continue
                    name = name.strip()
                    if not name:
                        continue
                    offers.append((idx, name))
            if offers:
                pending[st] = (offers, set())
        elif ev == "decision" and st in ("card_reward", "shop"):
            entry = pending.get(st)
            if not entry:
                continue
            _, picks = entry
            action = event.get("action")
            if not isinstance(action, dict):
                continue
            action_name = str(action.get("action", "")).lower()
            if st == "card_reward":
                # Any decision targeting this state resolves it (one-shot).
                # Picked index must match a card's index; if it doesn't
                # (e.g. "skip" alternative), picks stays empty → all skipped.
                idx = action.get("option_index")
                if isinstance(idx, int):
                    picks.add(idx)
                _flush(pending.pop(st, None))
            else:  # shop
                if action_name == "buy_card":
                    idx = action.get("option_index")
                    if isinstance(idx, int):
                        picks.add(idx)
                # leave_shop / etc. doesn't add a pick; flush on the
                # transition out, handled by the next state change above.

    # Flush anything still pending (run ended mid-decision).
    for entry in pending.values():
        _flush(entry)

    return list(seen.keys())
