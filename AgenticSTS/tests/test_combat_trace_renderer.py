"""Unit tests for the combat trace renderer."""
from __future__ import annotations

from dataclasses import dataclass, field


def _make_short_term_empty():
    from src.memory.short_term import ShortTermMemory
    return ShortTermMemory()


def test_render_returns_none_when_no_combats():
    from src.memory.combat_trace_renderer import render_last_two_combats

    stm = _make_short_term_empty()
    result = render_last_two_combats(stm, run_log_events=[])
    assert result is None


def test_extract_candidate_cards_preserves_case_and_order():
    from src.memory.combat_trace_renderer import extract_candidate_cards

    # Synthetic combat-like shape: list of dicts with hand_at_start + cards_played
    combats = [
        {
            "hand_at_start_per_round": [["Strike", "Defend"], ["Backstab", "STRIKE"]],
            "cards_played_per_round": [["strike"], ["backstab"]],
        },
        {
            "hand_at_start_per_round": [["defend", "SLY"]],
            "cards_played_per_round": [["Sly"]],
        },
    ]
    out = extract_candidate_cards(combats)
    # Case-preserving, first-seen order. Different cases are treated as distinct.
    # hand_at_start_per_round[0]: Strike, Defend
    # hand_at_start_per_round[1]: Backstab, STRIKE (distinct from "Strike")
    # cards_played_per_round[0]: strike (distinct from "Strike" and "STRIKE")
    # cards_played_per_round[1]: backstab (distinct from "Backstab")
    # hand_at_start_per_round[1] (2nd combat): defend (distinct from "Defend"), SLY
    # cards_played_per_round[0] (2nd combat): Sly (distinct from "SLY")
    assert out == ["Strike", "Defend", "Backstab", "STRIKE", "strike", "backstab", "defend", "SLY", "Sly"]


def _make_stm_with_one_combat(round_count: int = 2):
    from src.memory.short_term import (
        CombatTracker, CombatRoundTracker, ShortTermMemory,
    )

    stm = ShortTermMemory()
    tracker = CombatTracker(
        enemy_key="elite:mushroom", combat_type="elite",
        enemy_names=["Mushroom"],
        hp_before=60, deck_size=12,
        relics=["Ring of the Snake", "Snecko Skull"],
        floor=7, act=1, hp_after=50, won=True,
        terminal_reason="win",
    )
    for r in range(1, round_count + 1):
        rnd = CombatRoundTracker(
            round_num=r, energy_available=3,
            hp_start=60 - (r - 1) * 5, hp_end=60 - r * 5,
            enemy_intents=["attack 8"],
            hand_at_start=["strike", "defend", "backstab"],
            cards_played=["strike", "backstab"] if r == 1 else ["defend"],
            damage_dealt=17 if r == 1 else 0,
            damage_taken=5,
            block_gained=5,
            enemy_hp_snapshot=[("e1", "Mushroom", 60, 60)],
            enemy_powers_snapshot=[[]],
        )
        tracker.rounds.append(rnd)
    stm.completed_combats.append(tracker)
    return stm, tracker


def _make_state_event(floor: int, round_num: int, hand_cards: list[dict]) -> dict:
    return {
        "event": "state",
        "floor": floor,
        "state_type": "elite",
        "step": round_num * 10,
        "combat": {
            "round": round_num,
            "player": {
                "hand": hand_cards,
                "powers": [{"name": "Strength", "amount": 2, "description": "+2 dmg"}],
                "relics": [
                    {"name": "Ring of the Snake", "description": "Draw 2 extra", "stack": 1},
                ],
            },
        },
    }


def _make_decision_event(floor: int, step: int, action, reasoning: str, source: str = "plan") -> dict:
    return {
        "event": "decision",
        "floor": floor,
        "step": step,
        "state_type": "elite",
        "action": action if isinstance(action, dict) else {"action": action},
        "reasoning": reasoning,
        "source": source,
    }


def test_render_one_combat_contains_expected_sections():
    from src.memory.combat_trace_renderer import render_last_two_combats

    stm, tracker = _make_stm_with_one_combat(round_count=2)
    run_log_events = [
        _make_state_event(7, 1, [
            {
                "name": "Strike", "energy_cost": 1, "card_type": "Attack",
                "rules_text": "Deal 6 damage.",
                "damage": 6, "total_damage": 6, "hits": 1,
                "upgraded": False, "star_cost": None, "enchantment_name": None,
            },
            {
                "name": "Defend", "energy_cost": 1, "card_type": "Skill",
                "rules_text": "Gain 5 Block.",
                "damage": None, "block": 5,
                "upgraded": False, "star_cost": None, "enchantment_name": None,
            },
            {
                "name": "Backstab", "energy_cost": 1, "card_type": "Attack",
                "rules_text": "Deal 11 damage. First-turn only.",
                "damage": 11, "total_damage": 11, "hits": 1,
                "upgraded": True, "star_cost": None, "enchantment_name": "swift",
            },
        ]),
        _make_decision_event(7, 15, {"action": "play_card", "card_index": 2},
                             "Plan [1/2]: Backstab — lead with Backstab for burst"),
        _make_decision_event(7, 17, {"action": "play_card", "card_index": 0},
                             "Plan [2/2]: Strike — lead with Backstab for burst"),
        _make_state_event(7, 2, []),
    ]
    out = render_last_two_combats(stm, run_log_events)
    assert out is not None
    assert "## Combat 1 — elite:mushroom" in out
    assert "(floor 7, 1, elite)" in out
    assert "Ring of the Snake" in out
    assert "Round 1" in out
    assert "Strike (Attack, cost=1) dmg=6: Deal 6 damage." in out
    assert "Backstab+" in out  # upgraded marker
    assert "[swift]" in out     # enchantment bracket
    assert "Plans this round:" in out
    assert "[A] intended 2 → Backstab, Strike" in out
    assert "Cards played this round" in out
    assert "strike, backstab" in out  # ground-truth list still present


def test_render_drops_combat_exceeding_max_rounds():
    from src.memory.combat_trace_renderer import render_last_two_combats

    stm, _ = _make_stm_with_one_combat(round_count=5)
    out = render_last_two_combats(stm, run_log_events=[], max_rounds=3)
    assert out is None


def test_render_two_combats_both_present():
    from src.memory.combat_trace_renderer import render_last_two_combats
    from src.memory.short_term import (
        CombatTracker, CombatRoundTracker, ShortTermMemory,
    )

    stm = ShortTermMemory()
    for idx, floor in enumerate([6, 10], start=1):
        t = CombatTracker(
            enemy_key=f"monster_{idx}", combat_type="monster",
            enemy_names=["Goon"], hp_before=60, deck_size=10,
            floor=floor, act=1, hp_after=55, won=True,
        )
        t.rounds.append(CombatRoundTracker(
            round_num=1, energy_available=3,
            hp_start=60, hp_end=55,
            enemy_intents=[], hand_at_start=[], cards_played=["strike"],
            enemy_hp_snapshot=[("g", "Goon", 40, 40)],
            enemy_powers_snapshot=[[]],
        ))
        stm.completed_combats.append(t)
    out = render_last_two_combats(stm, run_log_events=[])
    assert out is not None
    assert "## Combat 1 — monster_1" in out
    assert "## Combat 2 — monster_2" in out


def test_render_uses_plan_blocks_not_replan_markers():
    """End-to-end: a 3-step plan produces one [A] block, not Plan + 2 REPLAN."""
    from src.memory.combat_trace_renderer import render_last_two_combats
    from src.memory.short_term import (
        CombatTracker, CombatRoundTracker, ShortTermMemory,
    )

    stm = ShortTermMemory()
    tracker = CombatTracker(
        enemy_key="monster:goon", combat_type="monster",
        enemy_names=["Goon"], hp_before=60, deck_size=10,
        floor=3, act=1, hp_after=58, won=True, terminal_reason="win",
    )
    tracker.rounds.append(CombatRoundTracker(
        round_num=1, energy_available=3, hp_start=60, hp_end=58,
        enemy_intents=["Attack 8"], hand_at_start=["Strike", "Defend", "Backstab"],
        cards_played=["Strike", "Defend", "Backstab"],
        damage_dealt=20, damage_taken=2, block_gained=5,
        enemy_hp_snapshot=[("e1", "Goon", 50, 50)],
        enemy_powers_snapshot=[[]],
    ))
    stm.completed_combats.append(tracker)

    body = "Lead with damage."
    run_log_events = [
        _make_state_event(3, 1, [
            {"name": "Strike", "energy_cost": 1, "card_type": "Attack",
             "rules_text": "Deal 6 damage.", "damage": 6, "total_damage": 6,
             "hits": 1, "upgraded": False, "star_cost": None, "enchantment_name": None},
            {"name": "Defend", "energy_cost": 1, "card_type": "Skill",
             "rules_text": "Gain 5 Block.", "damage": None, "block": 5,
             "upgraded": False, "star_cost": None, "enchantment_name": None},
            {"name": "Backstab", "energy_cost": 1, "card_type": "Attack",
             "rules_text": "Deal 11 damage.", "damage": 11, "total_damage": 11,
             "hits": 1, "upgraded": False, "star_cost": None, "enchantment_name": None},
        ]),
        _make_decision_event(3, 10, {"action": "play_card", "card_index": 0},
                             f"Plan [1/3]: Strike — {body}"),
        _make_decision_event(3, 11, {"action": "play_card", "card_index": 1},
                             f"Plan [2/3]: Defend — {body}"),
        _make_decision_event(3, 12, {"action": "play_card", "card_index": 2},
                             f"Plan [3/3]: Backstab — {body}"),
    ]
    out = render_last_two_combats(stm, run_log_events)
    assert out is not None
    assert "[A] intended 3 → Strike, Defend, Backstab" in out
    assert "Reason: Lead with damage." in out
    assert "Executed 3/3:" in out
    # Old format markers must not appear
    assert "[REPLAN #" not in out
    # Final ground-truth line still present
    assert "Cards played" in out


def test_render_omits_delta_when_pre_snapshot_missing():
    """Plan block with no matching state event for first_step → Reason +
    Executed only, no Δ."""
    from src.memory.combat_trace_renderer import render_last_two_combats
    from src.memory.short_term import (
        CombatTracker, CombatRoundTracker, ShortTermMemory,
    )

    stm = ShortTermMemory()
    tracker = CombatTracker(
        enemy_key="monster:goon", combat_type="monster",
        enemy_names=["Goon"], hp_before=60, deck_size=10,
        floor=3, act=1, hp_after=58, won=True, terminal_reason="win",
    )
    tracker.rounds.append(CombatRoundTracker(
        round_num=1, energy_available=3, hp_start=60, hp_end=58,
        enemy_intents=["Attack 8"], hand_at_start=["Strike"],
        cards_played=["Strike"], damage_dealt=6, damage_taken=2, block_gained=0,
        enemy_hp_snapshot=[("e1", "Goon", 50, 44)],
        enemy_powers_snapshot=[[]],
    ))
    stm.completed_combats.append(tracker)

    # Decision exists at step 99 with NO state event at step 99 (so pre=None),
    # but a state event at step 100 exists (so post is found via the fallback
    # `cur_last + 1` path). This isolates the pre-missing branch from the
    # post-missing branch.
    run_log_events = [
        _make_state_event(3, 1, []),  # state at step 10 (= 1 × 10 per _make_state_event)
        _make_decision_event(3, 99, {"action": "play_card", "card_index": 0},
                             "Plan [1/1]: Strike — Lead."),
        # Post-snapshot at step 100 (= 99 + 1) → _next_block_pre_snapshot fallback finds it
        {
            "event": "state",
            "floor": 3,
            "state_type": "elite",
            "step": 100,
            "combat": {
                "round": 1,
                "player": {"hand": [], "powers": [], "energy": 3, "block": 0,
                           "hp": 60, "max_hp": 60, "draw_pile": [],
                           "discard_pile": [], "exhaust_pile": []},
                "enemies": [],
            },
        },
    ]
    out = render_last_two_combats(stm, run_log_events)
    assert out is not None
    # Plan block renders without Δ section
    assert "[A] intended 1 → Strike" in out
    assert "Reason: Lead." in out
    assert "Executed 1/1: Strike" in out
    # No Δ emitted
    assert "Δ:" not in out
