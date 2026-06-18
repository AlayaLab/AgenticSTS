from types import SimpleNamespace

from src.brain.prompts.shop import build_shop_plan_prompt


def _potion(index, name, desc, occupied=True):
    return SimpleNamespace(index=index, name=name, description=desc, occupied=occupied)


def _shop_potion(name, desc, price):
    # Pads (is_stocked, enough_gold) mirror the stub fields accessed by the
    # existing "## Items For Sale" / gold-budget logic in build_shop_plan_prompt.
    return SimpleNamespace(
        index=0, name=name, description=desc, price=price,
        is_stocked=True, enough_gold=True,
    )


def _shop_gs(held, open_slots, shop_potions, gold=100):
    shop = SimpleNamespace(
        is_open=True, cards=[], relics=[], potions=shop_potions,
        card_removal=None,
    )
    return SimpleNamespace(
        shop=shop,
        potions=held, open_potion_slots=open_slots, potion_slots=3,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=gold,
        act=1, floor=7,
        upcoming_boss_enemy_keys=[],
    )


def test_slot_decision_injected_when_full_and_affordable_potion():
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage."),
        _potion(1, "Block Potion", "Gain 12 block."),
        _potion(2, "Energy Potion", "Gain 2 energy."),
    ]
    gs = _shop_gs(held, open_slots=0, shop_potions=[_shop_potion("Ghost Potion", "Intangible.", price=50)], gold=100)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "## Potion Slot Decision" in text
    assert "Ghost Potion" in text


def test_slot_decision_skipped_when_nothing_affordable():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _shop_gs(held, open_slots=0, shop_potions=[_shop_potion("Ghost Potion", "Intangible.", price=200)], gold=50)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text


def test_slot_decision_skipped_when_slots_open():
    held = [_potion(0, "Fire Potion", "Deal 10 damage.")]
    gs = _shop_gs(held, open_slots=2, shop_potions=[_shop_potion("Ghost Potion", "Intangible.", price=50)], gold=100)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text


def test_slot_decision_skipped_when_shop_has_no_potions():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _shop_gs(held, open_slots=0, shop_potions=[], gold=100)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text
