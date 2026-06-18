from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import config
from src.brain.prompts._relic_fmt import format_relic_hints
from src.brain.prompts.shop import build_shop_plan_prompt
from src.brain.tool_executor import ToolExecutor
from src.brain.v2_engine import V2Engine
from src.knowledge.injector import inject_combat_knowledge, inject_reward_knowledge
from src.knowledge.knowledge import GameKnowledge
from src.mcp_client.upstream_models import (
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawDeckCardPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.memory.card_build_store import CardBuildStore
from src.memory.card_memory_store import CardMemoryStore
from src.memory.combat_store import CombatMemoryStore
from src.memory.guide_store import GuideStore
from src.memory.models_v2 import CardMemory, DeckGuide
from src.memory.prompt_injector import format_working_context
from src.memory.retriever import query_for_decision
from src.memory.route_store import RouteMemoryStore
from src.state.game_state import GameState
from src.state.state_parser import parse_state


class _MockTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class _MockUsage:
    def __init__(self):
        self.input_tokens = 100
        self.output_tokens = 50
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class _MockMessage:
    def __init__(self, text: str):
        self.content = [_MockTextBlock(text)]
        self.stop_reason = "end_turn"
        self.usage = _MockUsage()


def _decision_text(payload: dict) -> str:
    import json

    return f"<decision>{json.dumps(payload)}</decision>"


def _extract_text(response: _MockMessage) -> str:
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text.strip()
    return ""


def _make_noncombat_gs(state_type: str = "map") -> GameState:
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=13,
        current_hp=44,
        max_hp=78,
        gold=474,
        max_energy=3,
        deck=[
            RawDeckCardPayload(
                index=0,
                card_id="neutralize",
                name="Neutralize",
                card_type="Attack",
                rarity="Starter",
                energy_cost=0,
                rules_text="Deal 3 damage. Apply 1 Weak.",
            )
        ],
    )
    raw = UpstreamGameState(
        screen=state_type.upper(),
        in_combat=False,
        available_actions=["choose_map_node"],
        run=run,
    )
    return GameState(raw=raw, state_type=state_type)


def _make_shop_state(
    *,
    card_names: list[str],
    relic_description: str | None = None,
    potion_description: str | None = None,
) -> GameState:
    cards = []
    for index, name in enumerate(card_names):
        cards.append(
            {
                "index": index,
                "category": "card",
                "card_id": name.lower().replace(" ", "_"),
                "name": name,
                "upgraded": False,
                "card_type": "Skill",
                "rarity": "Common",
                "costs_x": False,
                "star_costs_x": False,
                "energy_cost": 1,
                "star_cost": 0,
                "rules_text": f"{name} rules text.",
                "price": 50,
                "on_sale": False,
                "is_stocked": True,
                "enough_gold": True,
            }
        )

    relics = []
    if relic_description is not None:
        relics.append(
            {
                "index": 0,
                "relic_id": "vajra",
                "name": "Vajra",
                "description": relic_description,
                "rarity": "Common",
                "price": 150,
                "is_stocked": True,
                "enough_gold": True,
            }
        )

    potions = []
    if potion_description is not None:
        potions.append(
            {
                "index": 0,
                "potion_id": "fysh_oil",
                "name": "Fysh Oil",
                "description": potion_description,
                "rarity": "Common",
                "usage": "Combat",
                "price": 75,
                "is_stocked": True,
                "enough_gold": True,
            }
        )

    return parse_state(
        {
            "state_version": 6,
            "run_id": "run_test",
            "screen": "SHOP",
            "session": {
                "mode": "singleplayer",
                "phase": "run",
                "control_scope": "local_player",
            },
            "in_combat": False,
            "turn": None,
            "available_actions": ["buy_card", "buy_relic", "buy_potion", "proceed"],
            "run": {
                "character_id": "silent",
                "character_name": "The Silent",
                "floor": 13,
                "current_hp": 44,
                "max_hp": 78,
                "gold": 474,
                "max_energy": 3,
                "base_orb_slots": 0,
                "deck": [
                    {
                        "index": 0,
                        "card_id": "neutralize",
                        "name": "Neutralize",
                        "upgraded": True,
                        "card_type": "Attack",
                        "rarity": "Starter",
                        "costs_x": False,
                        "star_costs_x": False,
                        "energy_cost": 0,
                        "star_cost": 0,
                        "rules_text": "Deal 4 damage. Apply 2 Weak.",
                    }
                ],
                "relics": [],
                "players": [],
                "potions": [],
            },
            "shop": {
                "is_open": True,
                "can_open": False,
                "can_close": True,
                "cards": cards,
                "relics": relics,
                "potions": potions,
                "card_removal": {
                    "price": 75,
                    "available": True,
                    "used": False,
                    "enough_gold": True,
                },
            },
        }
    )


def _make_shop_memory_gs(card_names: list[str]) -> MagicMock:
    gs = MagicMock()
    gs.state_type = "shop"
    gs.is_combat = False
    gs.is_map = False
    gs.character = "the silent"
    gs.act = 1
    gs.floor = 13
    gs.enemies = []
    gs.hand = []
    gs.reward = None
    gs.selection = None

    shop = MagicMock()
    shop.cards = []
    for name in card_names:
        card = MagicMock()
        card.name = name
        card.is_stocked = True
        shop.cards.append(card)
    gs.shop = shop
    return gs


def test_decide_noncombat_does_not_call_or_render_run_context():
    backend = MagicMock()
    backend.extract_text = MagicMock(side_effect=_extract_text)
    backend._is_openai_failover_error = MagicMock(return_value=False)
    backend.acall = AsyncMock(
        return_value=_MockMessage(
            _decision_text(
                {"action": "choose_map_node", "option_index": 1, "reasoning": "best path"}
            )
        )
    )

    engine = V2Engine(
        backend=backend,
        tool_executor=ToolExecutor(),
    )

    result = asyncio.run(engine.decide_noncombat(_make_noncombat_gs(), "Choose a map node."))

    assert result is not None
    user_prompt = backend.acall.await_args.kwargs["messages"][0]["content"]
    assert "## Run Context" not in user_prompt


def test_shop_card_memory_survives_budget_and_legacy_general_guide_is_ignored(monkeypatch):
    card_names = ["Prepared", "Untouchable", "Accuracy", "Echoing Slash", "Grand Finale"]
    gs = _make_shop_memory_gs(card_names)

    card_store = CardMemoryStore()
    for name in card_names:
        card_store.put(
            CardMemory(
                character="the silent",
                card_name=name.lower(),
                note=f"{name} note",
            )
        )

    guide_store = GuideStore()
    guide_store.set_deck_guide(
        DeckGuide(
            character="the silent",
            archetype="general",
            guide_text=(
                "- CRITICAL FAILURE: take card rewards.\n"
                "- Prioritize damage cards in first 3 fights: Blade Dance, Backstab, "
                "Dagger Spray, Poisoned Stab, Quick Slash, Sucker Punch. Base Strikes "
                "cannot kill enemies before they overwhelm you.\n"
                "- Add block cards by Floor 4: Deflect, Backflip, Dodge and Roll, "
                "Leg Sweep. You cannot survive on Survivor alone.\n"
                "- Keep enough draw and block to stabilize."
            ),
            confidence=0.9,
        )
    )

    short_term = MagicMock()
    short_term.get_strategic_thread.return_value = "Strategic Thread\n" + ("long filler " * 40)
    short_term.completed_combats = []

    monkeypatch.setattr(config, "DECK_MEMORY_TOKENS", 70)

    wc = query_for_decision(
        gs=gs,
        short_term=short_term,
        combat_store=CombatMemoryStore(),
        route_store=RouteMemoryStore(),
        card_build_store=CardBuildStore(),
        guide_store=guide_store,
        card_memory_store=card_store,
    )

    assert list(wc.card_memory_hints) == [
        "prepared: Prepared note",
        "untouchable: Untouchable note",
        "accuracy: Accuracy note",
        "echoing slash: Echoing Slash note",
        "grand finale: Grand Finale note",
    ]

    formatted = format_working_context(wc)
    assert "CRITICAL FAILURE" not in formatted
    assert "Prioritize damage cards in first 3 fights" not in formatted
    assert "Add block cards by Floor 4" not in formatted
    assert "Keep enough draw and block to stabilize." not in formatted


def test_card_knowledge_uses_structured_summary_without_decompiler_opcodes():
    kb = GameKnowledge.get_instance()

    reward_text = inject_reward_knowledge(["Prepared", "Accuracy", "Grand Finale"], kb)
    assert "Prepared: Upgrade: Cards +1" in reward_text
    # Accuracy buffs Shivs but does not spawn them — spawns_cards=() in game data
    assert "Accuracy: Applies: 4 Accuracy | Upgrade: Accuracy +2" in reward_text
    assert "Grand Finale" not in reward_text

    combat_gs = GameState(
        raw=UpstreamGameState(
            screen="COMBAT",
            in_combat=True,
            turn=1,
            available_actions=["play_card", "end_turn"],
            combat=RawCombatPayload(
                player=RawCombatPlayerPayload(current_hp=44, max_hp=78, energy=3),
                hand=[
                    RawCombatHandCardPayload(
                        index=0,
                        card_id="prepared",
                        name="Prepared",
                        energy_cost=0,
                        rules_text="Draw 1 card. Discard 1 card.",
                        playable=True,
                    ),
                    RawCombatHandCardPayload(
                        index=1,
                        card_id="accuracy",
                        name="Accuracy",
                        energy_cost=1,
                        rules_text="Shivs deal 4 additional damage.",
                        playable=True,
                    ),
                ],
                enemies=[
                    RawCombatEnemyPayload(
                        index=0,
                        enemy_id="louse",
                        name="Louse",
                        current_hp=10,
                        max_hp=10,
                        is_alive=True,
                    )
                ],
            ),
            run=RawRunPayload(
                character_id="silent",
                character_name="The Silent",
                floor=13,
                current_hp=44,
                max_hp=78,
                gold=474,
                max_energy=3,
                deck=[],
            ),
        ),
        state_type="monster",
    )

    combat_text = inject_combat_knowledge(combat_gs, kb)
    for token in ("CardPileCmd", "PowerCmd", "CreatureCmd", "PotionCmd"):
        assert token not in reward_text
        assert token not in combat_text


def test_shop_prompt_shows_clean_relic_and_potion_descriptions():
    gs = _make_shop_state(
        card_names=["Prepared"],
        relic_description="Start each combat with [blue]1[/blue] [gold]Strength[/gold].",
        potion_description="[gold]Deal[/gold] [blue]20[/blue] damage.",
    )

    prompt = build_shop_plan_prompt(gs, deck=gs.deck, relics=["Cursed Pearl"])

    assert "Start each combat with 1 Strength." in prompt
    assert "Deal 20 damage." in prompt
    assert "Upon pickup, receive Greed. Gain 333 Gold." in prompt
    assert "[red]" not in prompt
    assert "[blue]" not in prompt
    assert "[gold]" not in prompt


def test_relic_hint_fallback_strips_bbcode():
    hints = format_relic_hints(["Cursed Pearl"], context="shop")

    assert "Upon pickup, receive Greed. Gain 333 Gold." in hints
    assert "[red]" not in hints
    assert "[blue]" not in hints
    assert "[gold]" not in hints
