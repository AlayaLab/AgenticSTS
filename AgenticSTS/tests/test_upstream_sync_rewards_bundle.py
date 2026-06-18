"""Tests for the 2026-04-28 upstream sync — reward atomization + bundle support
+ enriched payload fields. See
docs/superpowers/specs/2026-04-28-upstream-sync-rewards-bundle-design.md.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import config
from src.brain.models import LLMDecision
from src.brain.prompts.bundle import build_bundle_selection_prompt
from src.mcp_client import actions
from src.mcp_client.upstream_models import (
    RawBundleCardPayload,
    RawBundlePayload,
    RawCombatPlayerPayload,
    RawPileCardPayload,
    RawRewardAlternativePayload,
    RawRewardCardOptionPayload,
    RawRewardPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState
from src.state.upstream_game_state import derive_state_type

from tests.conftest import make_loop


# ── action builder ─────────────────────────────────────────


def test_resolve_rewards_pick():
    assert actions.resolve_rewards(option_index=2) == {
        "action": "resolve_rewards",
        "option_index": 2,
    }


def test_resolve_rewards_skip():
    assert actions.resolve_rewards(option_index=-1) == {
        "action": "resolve_rewards",
        "option_index": -1,
    }


def test_resolve_rewards_default():
    # Absent → mod-side default (skip card during drain). No option_index key.
    assert actions.resolve_rewards() == {"action": "resolve_rewards"}


# ── state derivation ───────────────────────────────────────


def _make_bundle_gs() -> GameState:
    bundles = [
        RawBundlePayload(
            index=0,
            cards=[
                RawBundleCardPayload(
                    index=0, card_id="STRIKE", name="Strike",
                    card_type="Attack", rarity="Starter", energy_cost=1,
                    rules_text="Deal 6 damage.",
                    resolved_rules_text="Deal 6 damage.",
                ),
                RawBundleCardPayload(
                    index=1, card_id="DEFEND", name="Defend",
                    card_type="Skill", rarity="Starter", energy_cost=1,
                    rules_text="Gain 5 Block.",
                    resolved_rules_text="Gain 5 Block.",
                ),
            ],
        ),
        RawBundlePayload(
            index=1,
            cards=[
                RawBundleCardPayload(
                    index=0, card_id="POISONED_STAB", name="Poisoned Stab",
                    card_type="Attack", rarity="Common", energy_cost=1,
                    rules_text="Deal 6 damage. Apply 3 Poison.",
                ),
            ],
        ),
    ]
    run = RawRunPayload(
        character_id="silent", character_name="The Silent",
        floor=2, current_hp=70, max_hp=70, gold=0, max_energy=3,
    )
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        available_actions=["select_deck_card"],
        run=run,
        bundles=bundles,
    )
    return GameState.from_upstream(raw)


def test_bundle_state_type_derived():
    gs = _make_bundle_gs()
    assert derive_state_type(gs.raw) == "bundle_select"
    assert gs.state_type == "bundle_select"
    assert len(gs.bundles) == 2


def test_bundle_prompt_renders():
    gs = _make_bundle_gs()
    out = build_bundle_selection_prompt(gs)
    assert "Bundle Selection" in out
    assert "ScrollBoxes" in out
    assert "Strike" in out and "Defend" in out and "Poisoned Stab" in out
    assert "Bundle [0]" in out and "Bundle [1]" in out
    assert "select_deck_card" in out


# ── enriched reward card model ─────────────────────────────


def test_reward_card_payload_enriched_fields():
    rc = RawRewardCardOptionPayload(
        index=0, card_id="STRIKE", name="Strike",
        card_type="Attack", rarity="Common", energy_cost=1, costs_x=False,
        rules_text="Deal 6 damage.",
    )
    assert rc.card_type == "Attack"
    assert rc.rarity == "Common"
    assert rc.energy_cost == 1
    assert rc.costs_x is False


def test_reward_card_payload_defaults_for_old_mod():
    rc = RawRewardCardOptionPayload(
        index=0, card_id="STRIKE", name="Strike", rules_text="Deal 6 damage.",
    )
    # Defaults for old-mod compat — Pydantic fills empty
    assert rc.card_type == ""
    assert rc.rarity == ""
    assert rc.energy_cost == 0


# ── structured pile cards ──────────────────────────────────


def test_pile_card_payload_round_trip():
    p = RawCombatPlayerPayload(
        draw_cards=[
            RawPileCardPayload(card_id="STRIKE", upgraded=True, card_type="Attack"),
            RawPileCardPayload(card_id="DEFEND", upgraded=False, card_type="Skill"),
        ],
        discard_cards=[],
        exhaust_cards=[
            RawPileCardPayload(card_id="ASCENDERS_BANE", upgraded=False, card_type="Curse"),
        ],
    )
    assert len(p.draw_cards) == 2
    assert p.draw_cards[0].card_id == "STRIKE" and p.draw_cards[0].upgraded
    assert p.exhaust_cards[0].card_type == "Curse"


# ── atomization translator ─────────────────────────────────


def _make_card_reward_gs(*, has_resolve: bool = True) -> GameState:
    avail = ["choose_reward_card", "skip_reward_cards", "choose_reward_alternative"]
    if has_resolve:
        avail.append("resolve_rewards")
    run = RawRunPayload(
        character_id="silent", character_name="The Silent",
        floor=5, current_hp=70, max_hp=70, gold=80, max_energy=3,
    )
    reward = RawRewardPayload(
        pending_card_choice=True,
        can_proceed=False,
        card_options=[
            RawRewardCardOptionPayload(
                index=0, card_id="STRIKE", name="Strike", card_type="Attack",
            ),
            RawRewardCardOptionPayload(
                index=1, card_id="DEFEND", name="Defend", card_type="Skill",
            ),
            RawRewardCardOptionPayload(
                index=2, card_id="BLUDGEON", name="Bludgeon", card_type="Attack",
            ),
        ],
        alternatives=[
            RawRewardAlternativePayload(index=0, label="Skip"),
        ],
    )
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        available_actions=avail,
        run=run,
        reward=reward,
    )
    return GameState.from_upstream(raw)


def test_atomize_card_reward_pick(monkeypatch):
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", True)
    loop = make_loop(MagicMock())
    gs = _make_card_reward_gs(has_resolve=True)
    dec = LLMDecision(
        action_name="choose_reward_card",
        params={"option_index": 2},
        reasoning="Bludgeon is the boss-killer",
    )
    out = loop._maybe_atomize_card_reward(gs, dec)
    assert out == {"action": "resolve_rewards", "option_index": 2}


def test_atomize_card_reward_skip_via_skip_action(monkeypatch):
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", True)
    loop = make_loop(MagicMock())
    gs = _make_card_reward_gs(has_resolve=True)
    dec = LLMDecision(
        action_name="skip_reward_cards", params={}, reasoning="all junk",
    )
    out = loop._maybe_atomize_card_reward(gs, dec)
    assert out == {"action": "resolve_rewards", "option_index": -1}


def test_atomize_card_reward_skip_via_alternative(monkeypatch):
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", True)
    loop = make_loop(MagicMock())
    gs = _make_card_reward_gs(has_resolve=True)
    dec = LLMDecision(
        action_name="choose_reward_alternative",
        params={"option_index": 0},
        reasoning="skip",
    )
    out = loop._maybe_atomize_card_reward(gs, dec)
    assert out == {"action": "resolve_rewards", "option_index": -1}


def test_atomize_falls_through_for_sacrifice(monkeypatch):
    """sacrifice_reward_cards has no atomic equivalent → must NOT atomize."""
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", True)
    loop = make_loop(MagicMock())
    gs = _make_card_reward_gs(has_resolve=True)
    dec = LLMDecision(
        action_name="sacrifice_reward_cards", params={}, reasoning="pael",
    )
    out = loop._maybe_atomize_card_reward(gs, dec)
    assert out is None


def test_atomize_disabled_when_old_mod(monkeypatch):
    """Mod missing resolve_rewards → must NOT atomize."""
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", True)
    loop = make_loop(MagicMock())
    gs = _make_card_reward_gs(has_resolve=False)
    dec = LLMDecision(
        action_name="choose_reward_card",
        params={"option_index": 1},
        reasoning="defend please",
    )
    out = loop._maybe_atomize_card_reward(gs, dec)
    assert out is None


def test_atomize_disabled_when_flag_off(monkeypatch):
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", False)
    loop = make_loop(MagicMock())
    gs = _make_card_reward_gs(has_resolve=True)
    dec = LLMDecision(
        action_name="choose_reward_card",
        params={"option_index": 0},
        reasoning="strike",
    )
    out = loop._maybe_atomize_card_reward(gs, dec)
    assert out is None


def test_atomize_disabled_when_multi_pile_combat_rewards(monkeypatch):
    """When parent combat_rewards bundle held >=2 Card piles (Orrery, Question
    Card-style relics, some boss/elite drops), atomization MUST fall through to
    the non-atomic flow so _handle_rewards can drain the remaining piles.
    Otherwise resolve_rewards' drain silently discards every CardReward button
    after the first pick.
    """
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", True)
    loop = make_loop(MagicMock())
    # Simulate _handle_rewards opening the first of >=2 Card piles.
    loop._card_reward_count_before_open = 2
    gs = _make_card_reward_gs(has_resolve=True)

    # Pick path: must NOT atomize (would drop pile 2+).
    dec_pick = LLMDecision(
        action_name="choose_reward_card",
        params={"option_index": 1},
        reasoning="multi-pile pick",
    )
    assert loop._maybe_atomize_card_reward(gs, dec_pick) is None

    # Skip-via-skip-action path: must NOT atomize either.
    dec_skip = LLMDecision(
        action_name="skip_reward_cards", params={}, reasoning="skip",
    )
    assert loop._maybe_atomize_card_reward(gs, dec_skip) is None

    # Skip-via-alternative path: must NOT atomize either.
    dec_alt = LLMDecision(
        action_name="choose_reward_alternative",
        params={"option_index": 0},
        reasoning="skip via alt",
    )
    assert loop._maybe_atomize_card_reward(gs, dec_alt) is None

    # Sanity: clearing the multi-pile flag re-enables atomize for the LAST pile.
    loop._card_reward_count_before_open = 1
    assert loop._maybe_atomize_card_reward(gs, dec_pick) == {
        "action": "resolve_rewards", "option_index": 1,
    }


def test_atomize_disabled_when_not_card_reward_state(monkeypatch):
    monkeypatch.setattr(config, "RESOLVE_REWARDS_ATOMIC", True)
    loop = make_loop(MagicMock())
    # State that is NOT card_reward (e.g. map) shouldn't trigger.
    raw = UpstreamGameState(
        screen="MAP",
        available_actions=["resolve_rewards", "choose_reward_card"],
        run=RawRunPayload(
            character_id="silent", character_name="The Silent",
            floor=1, current_hp=70, max_hp=70,
        ),
    )
    gs = GameState.from_upstream(raw)
    dec = LLMDecision(
        action_name="choose_reward_card",
        params={"option_index": 0},
        reasoning="x",
    )
    out = loop._maybe_atomize_card_reward(gs, dec)
    assert out is None
