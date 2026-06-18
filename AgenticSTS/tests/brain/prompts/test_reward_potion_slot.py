from types import SimpleNamespace

from src.brain.prompts.reward import build_card_reward_prompt


def _potion(index, name, desc, occupied=True):
    return SimpleNamespace(index=index, name=name, description=desc, occupied=occupied)


def _reward_item(reward_type, description="", claimable=True, index=0):
    return SimpleNamespace(
        reward_type=reward_type, description=description,
        claimable=claimable, index=index,
    )


def _reward_gs(potions, open_slots, reward_items):
    reward = SimpleNamespace(
        pending_card_choice=False, card_options=[], alternatives=[],
        rewards=reward_items,
    )
    return SimpleNamespace(
        reward=reward,
        potions=potions, open_potion_slots=open_slots, potion_slots=3,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=120,
        act=1, floor=4,
        upcoming_boss_enemy_keys=[],
    )


def test_slot_decision_injected_when_full_and_potion_reward():
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage."),
        _potion(1, "Block Potion", "Gain 12 block."),
        _potion(2, "Energy Potion", "Gain 2 energy."),
    ]
    gs = _reward_gs(
        potions=held, open_slots=0,
        reward_items=[_reward_item("potion", description="Ghost Potion — Intangible for 1 turn.")],
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], character="Silent")
    assert "## Potion Slot Decision" in text
    assert "Ghost Potion" in text
    # Potion-only reward state: card-specific sections should not appear
    assert "## Available Cards" not in text


def test_potion_only_reward_omits_card_scaffolding():
    """When pending_card_choice=False + only potion candidate, skip the
    card-picking scaffolding so the LLM focuses on the potion decision."""
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage."),
        _potion(1, "Block Potion", "Gain 12 block."),
        _potion(2, "Energy Potion", "Gain 2 energy."),
    ]
    gs = _reward_gs(
        potions=held, open_slots=0,
        reward_items=[_reward_item("potion", description="Ghost Potion — Intangible for 1 turn.")],
    )
    # Already covers pending_card_choice=False via _reward_gs defaults
    text = build_card_reward_prompt(gs, deck=[], relics=[], character="Silent")
    assert "## Potion Slot Decision" in text
    assert "## Available Cards" not in text
    assert "Boss Damage Check" not in text
    assert "Build Trajectory Check" not in text


def test_slot_decision_omitted_when_slots_open():
    held = [_potion(0, "Fire Potion", "Deal 10 damage.")]
    gs = _reward_gs(
        potions=held, open_slots=2,
        reward_items=[_reward_item("potion", description="Ghost Potion — Intangible for 1 turn.")],
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text


def test_slot_decision_omitted_when_no_potion_reward():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _reward_gs(
        potions=held, open_slots=0,
        reward_items=[_reward_item("gold", description="+50 gold")],
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text
