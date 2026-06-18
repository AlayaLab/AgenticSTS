"""Combat prompt should append a short hint when potion slots are full."""
from types import SimpleNamespace

import pytest

from src.brain.conversation import CombatConversation


def _combat_gs(open_slots, filled_slots=3, total_slots=3):
    potions = []
    for i in range(filled_slots):
        potions.append(SimpleNamespace(
            index=i, name=f"Pot{i}", description=f"Effect {i}.",
            occupied=True, can_use=True, requires_target=False,
            target_index_space="", target_type="",
        ))
    return SimpleNamespace(
        potions=potions, potion_slots=total_slots, open_potion_slots=open_slots,
    )


@pytest.fixture
def conversation():
    # Thin wrapper: real CombatConversation constructor may require more setup.
    # If constructor is heavy, use __new__ to bypass and set only fields the method uses.
    c = CombatConversation.__new__(CombatConversation)
    c._combat_type = "normal"
    c._floors_to_boss = 5
    return c


def test_combat_hint_present_when_slots_full(conversation):
    gs = _combat_gs(open_slots=0, filled_slots=3, total_slots=3)
    lines: list[str] = []
    conversation._format_potions(gs, lines, playable=[], is_replan=False)
    text = "\n".join(lines)
    assert "Potion slots: 3/3 FULL" in text
    assert "Slots FULL — spend a lower-value potion" in text


def test_combat_hint_absent_when_slots_open(conversation):
    gs = _combat_gs(open_slots=1, filled_slots=2, total_slots=3)
    lines: list[str] = []
    conversation._format_potions(gs, lines, playable=[], is_replan=False)
    text = "\n".join(lines)
    assert "Potion slots: 2/3 (1 open)" in text
    assert "Slots FULL —" not in text
