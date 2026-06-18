"""Stub evidence assembly for Mode B fill prompts.

Three responsibilities:
1. **Run selection**: pick 1-3 runs from history (current + recent win + recent loss).
2. **Combat replay sampling**: choose combat episodes for combat / boss stubs.
3. **Trajectory + Attribution Summary**: render decision histories for
   deckbuilding / map / intermission stubs.

Spec: ``docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md``
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

logger = logging.getLogger(__name__)

# Outcomes that count as "real losses" for evidence selection. Aborts and
# interrupts are runtime crashes, not legitimate gameplay outcomes.
_VALID_LOSS_OUTCOMES = ("defeat", "max_steps")


# ── 1. Run selection ────────────────────────────────────────────


def select_runs_for_fill(history: Sequence[Any]) -> list[Any]:
    """Pick: current run + most recent win + most recent loss (returns 1-3 runs).

    Args:
        history: ordered newest-first list of run records. Each item must
            have ``.run_id`` and ``.outcome`` attributes.

    Returns:
        Selected runs in order: [current, recent_win?, recent_loss?].
        Win and loss are skipped if absent or duplicate of current.
    """
    if not history:
        return []
    current = history[0]
    selected: list[Any] = [current]

    recent_win = next(
        (r for r in history[1:]
         if r.outcome == "victory" and r.run_id != current.run_id),
        None,
    )
    recent_loss = next(
        (r for r in history[1:]
         if r.outcome in _VALID_LOSS_OUTCOMES and r.run_id != current.run_id),
        None,
    )
    if recent_win is not None:
        selected.append(recent_win)
    if recent_loss is not None:
        selected.append(recent_loss)
    return selected


# ── 2. Combat replay sampling ───────────────────────────────────


def sample_combat_replays_for_stub(
    *,
    stub_id: str,
    run_ids: list[str],
    episodes_by_run: dict[str, list[Any]],
) -> list[Any]:
    """Pick combat episodes to include as evidence for combat / boss stubs.

    - **Combat stub** (id ends ``_combat``): per run, prefer 1 monster + 1
      elite; fall back to 2 monsters if no elite. Boss combats are excluded
      (they belong to the boss stub).
    - **Boss stub** (id ends ``_boss``): include all boss combats per run
      (typically 0-3 depending on how far the run progressed).
    - **Other stubs**: return empty list (deckbuilding / map / intermission
      use trajectory rendering, not replays).

    Each returned episode has its ``run_id`` field stamped with the run it
    came from, so downstream rendering can label it.
    """
    is_boss_stub = stub_id.endswith("_boss")
    is_combat_stub = stub_id.endswith("_combat")
    if not (is_boss_stub or is_combat_stub):
        return []

    sampled: list[Any] = []
    for run_id in run_ids:
        eps = episodes_by_run.get(run_id, [])
        if is_boss_stub:
            for ep in eps:
                if ep.combat_type == "boss":
                    sampled.append(ep)
        else:
            # Combat stub: prefer 1 monster + 1 elite, max 2.
            monsters = [e for e in eps if e.combat_type == "monster"]
            elites = [e for e in eps if e.combat_type == "elite"]
            picked: list[Any] = []
            if monsters:
                picked.append(monsters[0])
            if elites:
                picked.append(elites[0])
            if len(picked) < 2 and len(monsters) >= 2:
                picked.append(monsters[1])
            sampled.extend(picked[:2])
    return sampled


# ── 3. Trajectory + Attribution Summary (non-combat stubs) ─────


_STUB_STATE_TYPE_FILTERS: dict[str, set[str]] = {
    "deckbuilding": {"card_reward", "card_select", "shop", "treasure", "relic_select"},
    "map": {"map"},
    "intermission": {"rest_site", "event"},
}


def _state_types_for_stub(stub_id: str) -> set[str]:
    """Return the state_type filter set for a non-combat stub.

    Returns empty set for combat / boss stubs (they use replay sampling).
    """
    for suffix, st_set in _STUB_STATE_TYPE_FILTERS.items():
        if stub_id.endswith("_" + suffix):
            return st_set
    return set()


def _stub_label(stub_id: str) -> str:
    """e.g. 'stub_the_silent_deckbuilding' -> 'Deckbuilding'."""
    last = stub_id.split("_")[-1]
    return last.capitalize()


def render_trajectory_for_stub(
    *,
    stub_id: str,
    run_id: str,
    outcome: str,
    character: str,
    ascension: int,
    decisions: list[Any],
) -> str:
    """Render a per-run decision trajectory for a non-combat stub.

    Filters decisions to the state_types matching this stub. Each decision
    becomes a multi-line block: floor + state_type, options, choice +
    reasoning, strategic note, HP/Gold/Deck delta.

    Returns empty string for combat / boss stubs (they use replay sampling
    via ``sample_combat_replays_for_stub``).
    """
    relevant = _state_types_for_stub(stub_id)
    if not relevant:
        return ""

    label = _stub_label(stub_id)
    lines: list[str] = [
        f"## {label} Trajectory (run_id={run_id}, {character} A{ascension}, OUTCOME={outcome})",
    ]

    for d in decisions:
        if d.state_type not in relevant:
            continue
        block = [
            f"[{d.floor} {d.state_type}] HP {d.hp_before}, Gold {d.gold_before}, Deck {d.deck_before}",
            f"  Action: {d.action} (option_index={d.option_index})",
        ]
        if getattr(d, "reasoning", ""):
            block.append(f"  Reasoning: \"{d.reasoning}\"")
        if getattr(d, "strategic_note", ""):
            block.append(f"  Strategic note: \"{d.strategic_note}\"")
        if getattr(d, "deck_change", "no change") and d.deck_change != "no change":
            block.append(f"  Deck change: {d.deck_change}")
        block.append(
            f"  Outcome delta: HP {d.hp_before}->{d.hp_after}, "
            f"Gold {d.gold_before}->{d.gold_after}, Deck {d.deck_before}->{d.deck_after}"
        )
        lines.append("\n".join(block))

    return "\n\n".join(lines)


def build_attribution_summary(
    *,
    run_id: str,
    final_deck: list[str],
    final_relics: list[str],
    death_cause: str,
    strategic_thread_evolution: list[tuple[str, str]],
    card_play_stats: dict[str, dict],
) -> str:
    """Render a deterministic Attribution Summary section.

    Pulls from card_memory_store (play counts + damage), run_history (death
    cause), and STM dump (strategic_thread evolution). No LLM call.

    Args:
        card_play_stats: ``card_name -> {"plays": int, "total_damage": int, "total_block": int}``.
        strategic_thread_evolution: list of ``(floor_label, note)`` tuples.

    Returns:
        Markdown-formatted summary string.
    """
    lines = [f"## Attribution Summary (run_id={run_id})"]

    # Top cards by play count
    sorted_cards = sorted(
        card_play_stats.items(),
        key=lambda kv: kv[1].get("plays", 0),
        reverse=True,
    )
    top = sorted_cards[:5]
    if top:
        most_played = ", ".join(
            f"{name} ({s.get('plays', 0)} plays, dmg={s.get('total_damage', 0)}, "
            f"block={s.get('total_block', 0)})"
            for name, s in top
        )
        lines.append(f"- Most-played cards: {most_played}")

    # Rarely-used cards (≤4 plays)
    rarely_used = [name for name, st in card_play_stats.items() if st.get("plays", 0) <= 4]
    if rarely_used:
        lines.append(
            f"- Cards rarely/never used (<=4 plays): {', '.join(rarely_used[:8])}"
        )

    if death_cause:
        lines.append(f"- Death cause: {death_cause}")

    if strategic_thread_evolution:
        thread_str = " | ".join(
            f"{floor}: \"{note[:60]}{'...' if len(note) > 60 else ''}\""
            for floor, note in strategic_thread_evolution[:6]
        )
        lines.append(f"- Strategic Thread evolution: {thread_str}")

    return "\n".join(lines)
