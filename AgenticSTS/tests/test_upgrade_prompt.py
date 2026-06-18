"""Tests for P0-7: Card upgrade comparison at Smith.

Verifies that build_card_select_prompt injects on_upgrade info from the
knowledge DB when in upgrade mode, and degrades gracefully when knowledge
is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.brain.prompts.card_select import _lookup_upgrade_info, build_card_select_prompt
from src.knowledge.card_lookup import CardKnowledge
from src.state.state_parser import parse_state

# ── Helpers ──────────────────────────────────────────────────────────


def _base_run() -> dict:
    return {
        "character_id": "ironclad",
        "character_name": "Ironclad",
        "floor": 10,
        "current_hp": 60,
        "max_hp": 80,
        "gold": 120,
        "max_energy": 3,
        "base_orb_slots": 0,
        "deck": [],
        "relics": [],
        "players": [],
        "potions": [],
    }


def _card_select_state(*, kind: str = "upgrade", prompt: str = "Choose a card to Upgrade") -> dict:
    """Minimal state payload for a card_select (upgrade) screen."""
    return {
        "state_version": 6,
        "run_id": "run_upgrade_test",
        "screen": "CARD_SELECTION",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "available_actions": ["select_deck_card"],
        "selection": {
            "kind": kind,
            "prompt": prompt,
            "min_select": 1,
            "max_select": 1,
            "selected_count": 0,
            "requires_confirmation": False,
            "can_confirm": False,
            "cards": [
                {
                    "index": 0,
                    "card_id": "bash",
                    "name": "Bash",
                    "upgraded": False,
                    "card_type": "Attack",
                    "rarity": "Common",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 2,
                    "star_cost": 0,
                    "rules_text": "Deal 8 damage. Apply 2 Vulnerable.",
                },
                {
                    "index": 1,
                    "card_id": "defragment",
                    "name": "Defragment",
                    "upgraded": False,
                    "card_type": "Power",
                    "rarity": "Uncommon",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Gain 1 Focus.",
                },
                {
                    "index": 2,
                    "card_id": "alchemize",
                    "name": "Alchemize",
                    "upgraded": False,
                    "card_type": "Skill",
                    "rarity": "Rare",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Obtain a random potion.",
                },
            ],
        },
        "run": _base_run(),
    }


@dataclass(frozen=True)
class _FakeCardLookup:
    """Minimal mock of CardLookup that returns pre-set CardKnowledge."""
    _cards: dict  # name_lower -> CardKnowledge

    def get(self, card_name: str) -> CardKnowledge | None:
        key = card_name.rstrip("+").strip().lower()
        return self._cards.get(key)


@dataclass(frozen=True)
class _FakeKnowledge:
    """Minimal mock of GameKnowledge with a cards lookup."""
    cards: _FakeCardLookup


def _make_knowledge() -> _FakeKnowledge:
    """Create a fake knowledge DB with on_upgrade data for test cards."""
    cards = {
        "bash": CardKnowledge(
            name="Bash",
            cost="2",
            type="Attack",
            rarity="Common",
            on_play="DamageCmd.Attack, PowerCmd.Apply<VulnerablePower>",
            on_upgrade="UpgradeValueBy(2m)",
            vars="DamageVar(8m), PowerVar<VulnerablePower>(2m)",
        ),
        "defragment": CardKnowledge(
            name="Defragment",
            cost="1",
            type="Power",
            rarity="Uncommon",
            on_play="PowerCmd.Apply<FocusPower>",
            on_upgrade="UpgradeValueBy(1m)",
            vars="PowerVar<FocusPower>(1m)",
        ),
        "alchemize": CardKnowledge(
            name="Alchemize",
            cost="1",
            type="Skill",
            rarity="Rare",
            on_play="PotionCmd.TryToProcure",
            on_upgrade="",  # No on_upgrade data
        ),
    }
    return _FakeKnowledge(cards=_FakeCardLookup(_cards=cards))


# ── Unit tests: _lookup_upgrade_info ─────────────────────────────────


def test_lookup_upgrade_info_returns_upgrade_text():
    """Known card with on_upgrade returns readable formatted string."""
    kb = _make_knowledge()
    result = _lookup_upgrade_info("Bash", kb)
    assert "\u2192 UPGRADE:" in result
    assert "+2 to a value" in result


def test_lookup_upgrade_info_strips_plus():
    """Card name with '+' suffix is handled correctly."""
    kb = _make_knowledge()
    result = _lookup_upgrade_info("Bash+", kb)
    assert "\u2192 UPGRADE:" in result
    assert "+2 to a value" in result


def test_lookup_upgrade_info_no_upgrade_data():
    """Card with empty on_upgrade returns empty string."""
    kb = _make_knowledge()
    result = _lookup_upgrade_info("Alchemize", kb)
    assert result == ""


def test_lookup_upgrade_info_unknown_card():
    """Card not in knowledge DB returns empty string."""
    kb = _make_knowledge()
    result = _lookup_upgrade_info("NonexistentCard", kb)
    assert result == ""


def test_lookup_upgrade_info_none_knowledge():
    """None knowledge returns empty string."""
    result = _lookup_upgrade_info("Bash", None)
    assert result == ""


def test_lookup_upgrade_info_no_cards_attr():
    """Object without cards attribute returns empty string."""

    class _NoCards:
        pass

    result = _lookup_upgrade_info("Bash", _NoCards())
    assert result == ""


# ── Integration tests: build_card_select_prompt ──────────────────────


def test_upgrade_prompt_with_knowledge():
    """Upgrade mode + knowledge injects on_upgrade info per card."""
    gs = parse_state(_card_select_state())
    kb = _make_knowledge()
    prompt = build_card_select_prompt(gs, knowledge=kb)

    # Bash has on_upgrade
    assert "\u2192 UPGRADE: +2 to a value" in prompt
    # Defragment has on_upgrade
    assert "Defragment" in prompt
    # Alchemize has empty on_upgrade -- should NOT show arrow
    alchemize_line = [line for line in prompt.split("\n") if "Alchemize" in line][0]
    assert "\u2192 UPGRADE:" not in alchemize_line


def test_upgrade_prompt_without_knowledge():
    """Upgrade mode without knowledge still produces valid prompt."""
    gs = parse_state(_card_select_state())
    prompt = build_card_select_prompt(gs, knowledge=None)

    # No upgrade info injected
    assert "\u2192 UPGRADE:" not in prompt
    # Cards are still listed
    assert "Bash" in prompt
    assert "Defragment" in prompt
    assert "Alchemize" in prompt


def test_non_upgrade_mode_no_upgrade_info():
    """Non-upgrade mode (remove) does NOT inject upgrade info even with knowledge."""
    gs = parse_state(_card_select_state(kind="remove", prompt="Choose a card to Remove"))
    kb = _make_knowledge()
    prompt = build_card_select_prompt(gs, knowledge=kb)

    assert "\u2192 UPGRADE:" not in prompt


def test_v2_upgrade_prompt_with_knowledge_no_lookup_tip():
    """V2 upgrade mode with knowledge does NOT show lookup_card tip (already injected)."""
    gs = parse_state(_card_select_state())
    kb = _make_knowledge()
    prompt = build_card_select_prompt(gs, knowledge=kb)

    # Upgrade info is injected
    assert "\u2192 UPGRADE: +2 to a value" in prompt
    # No "TIP: Use lookup_card" because knowledge already provided
    assert "TIP: Use lookup_card" not in prompt


def test_v2_upgrade_prompt_without_knowledge_shows_upgrade_guidance():
    """V2 upgrade mode without knowledge shows compact upgrade guidance."""
    gs = parse_state(_card_select_state())
    prompt = build_card_select_prompt(gs, knowledge=None)

    assert "biggest dimension boost" in prompt


def test_upgrade_prompt_smith_kind():
    """kind='smith' also triggers upgrade mode."""
    gs = parse_state(_card_select_state(kind="smith", prompt="Smith: Choose a card"))
    kb = _make_knowledge()
    prompt = build_card_select_prompt(gs, knowledge=kb)

    assert "\u2192 UPGRADE: +2 to a value" in prompt
