from types import SimpleNamespace

from src.brain.prompts.shop import build_shop_plan_prompt
from src.memory.models_v2 import CombatGuide


class _FakeGuideStore:
    def __init__(self, guide: CombatGuide | None):
        self._guide = guide

    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None:
        return self._guide


def _shop_gs(cards: list, upcoming: list[str]) -> object:
    shop = SimpleNamespace(
        is_open=True, cards=cards, relics=[], potions=[],
        card_removal=None,
    )
    return SimpleNamespace(
        shop=shop,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=120,
        act=1, floor=7,
        upcoming_boss_enemy_keys=upcoming,
    )


def _fake_shop_card(name: str = "Strike"):
    return SimpleNamespace(
        index=0, name=name, card_type="Attack", rarity="Common",
        upgraded=False, costs_x=False, energy_cost=1, rules_text="Deal 6.",
        resolved_rules_text="Deal 6.", dynamic_values=[], price=50,
        is_stocked=True, enough_gold=True, on_sale=False,
    )


def test_shop_prompt_injects_when_cards_and_guide():
    guide = CombatGuide(enemy_key="Queen", character="Silent", guide_text="Burst plan.")
    gs = _shop_gs([_fake_shop_card()], ["Queen"])
    store = _FakeGuideStore(guide)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "## Upcoming Act Boss: Queen" in text


def test_shop_prompt_skips_when_no_cards_for_sale():
    guide = CombatGuide(enemy_key="Queen", character="Silent", guide_text="Burst plan.")
    gs = _shop_gs([], ["Queen"])
    store = _FakeGuideStore(guide)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text


def test_shop_prompt_skips_when_no_guide():
    gs = _shop_gs([_fake_shop_card()], ["Queen"])
    store = _FakeGuideStore(None)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text
