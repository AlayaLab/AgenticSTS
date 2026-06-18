from types import SimpleNamespace

from src.brain.prompts.reward import build_card_reward_prompt
from src.memory.models_v2 import CombatGuide


class _FakeGuideStore:
    def __init__(self, guide: CombatGuide | None):
        self._guide = guide

    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None:
        return self._guide


def _reward_gs(upcoming: list[str]) -> object:
    # Minimal stub — only fields the prompt builder touches in our code paths.
    # Any missing attributes fail loudly in tests to surface plan drift.
    card_opt = SimpleNamespace(
        index=0, stable_id="strike", card_id="strike",
        name="Strike", upgraded=False, card_type="Attack", rarity="Basic",
        costs_x=False, energy_cost=1, rules_text="Deal 6 damage.",
        resolved_rules_text="Deal 6 damage.", dynamic_values=[], alternatives=[],
    )
    reward = SimpleNamespace(
        pending_card_choice=True,
        card_options=[card_opt],
        alternatives=[],
    )
    return SimpleNamespace(
        reward=reward,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=120,
        act=1, floor=4,
        upcoming_boss_enemy_keys=upcoming,
    )


def test_reward_prompt_no_guide_omits_section():
    gs = _reward_gs(["Queen"])
    store = _FakeGuideStore(None)
    text = build_card_reward_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text


def test_reward_prompt_injects_guide_when_present():
    guide = CombatGuide(
        enemy_key="Queen", character="Silent",
        guide_text="Heavy AOE works best round 1.",
        key_patterns=("Stack block turn 2",),
    )
    gs = _reward_gs(["Queen"])
    store = _FakeGuideStore(guide)
    text = build_card_reward_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "## Upcoming Act Boss: Queen" in text
    assert "Heavy AOE works best round 1." in text
    assert "Stack block turn 2" in text


def test_reward_prompt_omits_section_when_no_upcoming_keys():
    gs = _reward_gs([])
    store = _FakeGuideStore(
        CombatGuide(enemy_key="Queen", character="Silent", guide_text="X")
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text
