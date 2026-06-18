"""Snapshot tests verifying baseline variants strip strategy content
and full variants are unchanged. Spec:
  docs/superpowers/specs/2026-04-26-ablation-baseline-design.md
"""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager


@contextmanager
def _set_variant(variant: str):
    original = os.environ.get("STS2_PROMPT_VARIANT")
    os.environ["STS2_PROMPT_VARIANT"] = variant
    try:
        import config
        importlib.reload(config)
        from src.brain.prompts import system
        importlib.reload(system)
        yield system
    finally:
        if original is None:
            os.environ.pop("STS2_PROMPT_VARIANT", None)
        else:
            os.environ["STS2_PROMPT_VARIANT"] = original
        import config
        importlib.reload(config)
        from src.brain.prompts import system
        importlib.reload(system)


# ── Baseline variant content checks ──────────────────────────────

def test_baseline_combat_strips_hp_conservation():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("monster")
        assert "HP Conservation" not in prompt
        assert "HP is a run-wide resource" not in prompt
        assert "Save sustained-buff potions" not in prompt


def test_baseline_combat_keeps_core_rules():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("monster")
        assert "Core Combat Rules" in prompt
        assert "Hand resets every turn" in prompt
        assert "Energy resets to 3" in prompt
        assert "Queue plays for generated cards" in prompt


def test_baseline_boss_strips_boss_strategy():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("boss")
        assert "Boss Fight Strategy" not in prompt
        assert "HP fully restores after" not in prompt
        assert "trade HP freely" not in prompt


def test_baseline_deckbuild_strips_two_phase_framework():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("card_reward")
        assert "Two-Phase" not in prompt
        assert "Foundation" not in prompt
        assert "Commitment" not in prompt
        assert "core engine" not in prompt.lower()
        assert "4 dimensions" not in prompt
        assert "## Output: `strategic_note`" not in prompt


def test_baseline_deckbuild_has_minimal_task_header():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("card_reward")
        assert "Deckbuilding Decision" in prompt


def test_baseline_strategic_strips_run_wide_strategy():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("rest_site")
        assert "Run-Wide Strategy" not in prompt
        assert "Upgrade (Smith) by default" not in prompt
        assert "HP is a run-wide resource" not in prompt
        assert "## Output: `strategic_note`" not in prompt


def test_baseline_strategic_has_minimal_task_header():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("event")
        assert "Strategic Decision" in prompt


# ── Full variant unchanged checks ────────────────────────────────

def test_full_combat_keeps_hp_conservation():
    with _set_variant("full") as system:
        prompt = system.get_system_prompt("monster")
        assert "HP Conservation" in prompt
        assert "HP is a run-wide resource" in prompt


def test_full_deckbuild_keeps_two_phase_framework():
    with _set_variant("full") as system:
        prompt = system.get_system_prompt("card_reward")
        assert "Two-Phase Framework" in prompt
        assert "Foundation" in prompt
        assert "Commitment" in prompt


def test_full_strategic_keeps_run_wide():
    with _set_variant("full") as system:
        prompt = system.get_system_prompt("rest_site")
        assert "Run-Wide Strategy" in prompt


# ── reward.py / shop.py ──────────────────────────────────────────

def _build_reward_gs():
    """Minimal GameState with reward state for prompt builder tests."""
    from unittest.mock import MagicMock

    gs = MagicMock()
    gs.act = 1
    gs.floor = 7
    gs.player_hp = 56
    gs.player_max_hp = 70
    gs.hp_ratio = 0.8
    gs.gold = 95
    gs.open_potion_slots = 1

    rw = MagicMock()
    rw.pending_card_choice = True
    rw.alternatives = []
    card = MagicMock()
    card.index = 0
    card.name = "Backflip"
    card.upgraded = False
    card.rules_text = "Gain 5 Block. Draw 2 cards."
    card.resolved_rules_text = card.rules_text
    card.dynamic_values = []
    # Enriched-payload fields (e6a90ff partial). Empty strings/zero exercise
    # the old-mod fallback path so MagicMock auto-attrs don't pollute output.
    card.card_type = ""
    card.rarity = ""
    card.energy_cost = 0
    card.costs_x = False
    rw.card_options = [card]
    rw.rewards = []
    gs.reward = rw
    return gs


def test_baseline_reward_strips_boss_damage_check():
    with _set_variant("baseline") as _:
        from src.brain.prompts.reward import build_card_reward_prompt
        prompt = build_card_reward_prompt(_build_reward_gs(), deck=[], relics=[])
        assert "Boss Damage Check" not in prompt
        assert "Build Trajectory" not in prompt
        assert "Boss HP target" not in prompt
        assert "200" not in prompt
        assert "400" not in prompt
        assert "600" not in prompt


def test_full_reward_keeps_boss_damage_check():
    with _set_variant("full") as _:
        from src.brain.prompts.reward import build_card_reward_prompt
        prompt = build_card_reward_prompt(_build_reward_gs(), deck=[], relics=[])
        assert "Boss Damage Check" in prompt
        assert "Build Trajectory Check" in prompt


def _build_shop_gs():
    """Minimal GameState with shop cards for prompt builder tests."""
    from tests.conftest import make_shop_gs
    gs = make_shop_gs()
    return gs


def test_baseline_shop_strips_guide_block():
    with _set_variant("baseline") as _:
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(_build_shop_gs(), deck=[], relics=[])
        assert "## Guide" not in prompt
        assert "Boss HP" not in prompt
        assert "Build Plan in the Strategic Thread" not in prompt


def test_full_shop_keeps_guide_block():
    with _set_variant("full") as _:
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(_build_shop_gs(), deck=[], relics=[])
        assert "## Guide" in prompt


# ── rest.py / event.py / treasure.py / card_select.py ────────────

def test_baseline_rest_strips_advisory_text():
    from unittest.mock import MagicMock
    gs = MagicMock()
    gs.act = 2
    gs.floor = 22
    gs.player_hp = 25
    gs.player_max_hp = 70
    gs.hp_ratio = 0.36
    gs.gold = 50
    gs.can_proceed = False
    rest = MagicMock()
    rest.options = []
    gs.rest = rest
    # Provide remaining_route with a boss ahead to trigger gated branches
    remaining_route = [(23, "elite"), (24, "boss"), (25, "shop")]

    with _set_variant("baseline") as _:
        from src.brain.prompts.rest import build_rest_prompt
        prompt = build_rest_prompt(gs, deck=[], relics=[], remaining_route=remaining_route)
        # Numeric heal calc retained
        assert "Healing restores" in prompt
        # Advisory phrases stripped (gated branches tested)
        assert "Strongly consider healing" not in prompt
        assert "HP is relatively healthy" not in prompt
        assert "Prioritize healing over upgrading" not in prompt
        assert "Review the Smith upgradeable cards above to assess" not in prompt


def test_baseline_event_strips_trailing_guidance():
    from tests.conftest import make_event_gs
    from src.mcp_client.upstream_models import RawEventOptionPayload
    opts = [
        RawEventOptionPayload(
            index=0, id="OPT_A", title="Option A",
            description="Take 5 HP damage.", is_locked=False,
            is_proceed=False, will_kill_player=False,
        ),
    ]
    gs = make_event_gs(opts)

    with _set_variant("baseline") as _:
        from src.brain.prompts.event import build_event_prompt
        prompt = build_event_prompt(gs, deck=[], relics=[])
        assert "Evaluate each option's risk vs reward" not in prompt
        assert "consider whether your deck needs more damage" not in prompt
        assert "200" not in prompt
        assert "400" not in prompt
        assert "600" not in prompt
        # Live MCP option still rendered
        assert "Option A" in prompt


def test_baseline_treasure_strips_relic_advice():
    from unittest.mock import MagicMock
    gs = MagicMock()
    gs.act = 1
    gs.floor = 9
    gs.player_hp = 60
    gs.player_max_hp = 70
    gs.hp_ratio = 0.86
    gs.gold = 100
    chest = MagicMock()
    relic = MagicMock()
    relic.index = 0
    relic.name = "Anchor"
    relic.rarity = "Common"
    chest.relic_options = [relic]
    gs.chest = chest

    with _set_variant("baseline") as _:
        from src.brain.prompts.treasure import build_treasure_prompt
        prompt = build_treasure_prompt(gs, deck=[], relics=[])
        assert "Almost always take a relic" not in prompt
        assert "Energy/draw relics are S-tier" not in prompt
        assert "Anchor" in prompt  # listing kept


def test_baseline_card_select_strips_mode_hint():
    from tests.conftest import make_card_select_gs
    gs = make_card_select_gs(prompt="Choose a card to upgrade.")

    with _set_variant("baseline") as _:
        from src.brain.prompts.card_select import build_card_select_prompt
        prompt = build_card_select_prompt(gs, deck=[], relics=[])
        assert "biggest dimension boost" not in prompt
        assert "cost reduction > doubled" not in prompt
        assert "Curses/Statuses first" not in prompt
        assert "card most central to your win condition" not in prompt


# ── Full variant counterparts for task 4 ────────────────────────────

def test_full_rest_keeps_advisory_text():
    from unittest.mock import MagicMock
    gs = MagicMock()
    gs.act = 2
    gs.floor = 22
    gs.player_hp = 25
    gs.player_max_hp = 70
    gs.hp_ratio = 0.36
    gs.gold = 50
    gs.can_proceed = False
    rest = MagicMock()
    rest.options = []
    gs.rest = rest
    # Use remaining_route with boss to trigger boss_imminent branch
    remaining_route = [(23, "elite"), (24, "boss"), (25, "shop")]

    with _set_variant("full") as _:
        from src.brain.prompts.rest import build_rest_prompt
        prompt = build_rest_prompt(gs, deck=[], relics=[], remaining_route=remaining_route)
        # Advisory text PRESENT in full mode (boss branch has: "Boss is next — HP matters...")
        assert "Boss is next" in prompt
        assert "HP matters more than one more upgrade" in prompt


def test_full_event_keeps_trailing_guidance():
    from tests.conftest import make_event_gs
    from src.mcp_client.upstream_models import RawEventOptionPayload
    opts = [
        RawEventOptionPayload(
            index=0, id="OPT_A", title="Option A",
            description="Take 5 HP damage.", is_locked=False,
            is_proceed=False, will_kill_player=False,
        ),
    ]
    gs = make_event_gs(opts)

    with _set_variant("full") as _:
        from src.brain.prompts.event import build_event_prompt
        prompt = build_event_prompt(gs, deck=[], relics=[])
        # Advisory text PRESENT in full mode
        assert "Evaluate each option's risk vs reward" in prompt


def test_full_treasure_keeps_relic_advice():
    from unittest.mock import MagicMock
    gs = MagicMock()
    gs.act = 1
    gs.floor = 9
    gs.player_hp = 60
    gs.player_max_hp = 70
    gs.hp_ratio = 0.86
    gs.gold = 100
    chest = MagicMock()
    relic = MagicMock()
    relic.index = 0
    relic.name = "Anchor"
    relic.rarity = "Common"
    chest.relic_options = [relic]
    gs.chest = chest

    with _set_variant("full") as _:
        from src.brain.prompts.treasure import build_treasure_prompt
        prompt = build_treasure_prompt(gs, deck=[], relics=[])
        # Advisory text PRESENT in full mode
        assert "Almost always take a relic" in prompt
        assert "Energy/draw relics are S-tier" in prompt


def test_full_card_select_keeps_mode_hint():
    from tests.conftest import make_card_select_gs
    gs = make_card_select_gs(prompt="Choose a card to upgrade.")

    with _set_variant("full") as _:
        from src.brain.prompts.card_select import build_card_select_prompt
        prompt = build_card_select_prompt(gs, deck=[], relics=[])
        # Advisory text PRESENT in full mode (upgrade branch)
        assert "biggest dimension boost" in prompt


# ── potion.py ────────────────────────────────────────────────────

def _build_potion_gs():
    from tests.conftest import make_combat_gs, make_hand_card
    from src.mcp_client.upstream_models import RawRunPotionPayload
    potions = [
        RawRunPotionPayload(
            index=0, potion_id="block_potion", name="Block Potion",
            description="Gain 12 Block.", can_use=True, requires_target=False,
        ),
    ]
    return make_combat_gs(
        hand=[make_hand_card("Strike", 0, playable=True, rules_text="Deal 6 damage.")],
        potions=potions,
    )


def test_baseline_potion_strips_decision_framework():
    with _set_variant("baseline") as _:
        from src.brain.prompts.potion import build_potion_prompt
        prompt = build_potion_prompt(_build_potion_gs())
        assert "Potion Decision Framework" not in prompt
        assert "USE potion when" not in prompt
        assert "SAVE potion when" not in prompt
        assert "Golden rule" not in prompt
        assert "dying with unused potions is the worst outcome" not in prompt


def test_baseline_potion_strips_threat_labels_keeps_numbers():
    with _set_variant("baseline") as _:
        from src.brain.prompts.potion import build_potion_prompt
        prompt = build_potion_prompt(_build_potion_gs())
        # Numeric line retained
        assert "Incoming damage:" in prompt
        # Advisory labels stripped
        assert "LETHAL" not in prompt
        assert "CRITICAL HP" not in prompt
        assert "defensive potions are valuable" not in prompt


def test_full_potion_keeps_decision_framework():
    with _set_variant("full") as _:
        from src.brain.prompts.potion import build_potion_prompt
        prompt = build_potion_prompt(_build_potion_gs())
        assert "Potion Decision Framework" in prompt
        assert "Golden rule" in prompt


# ── hand_select.py ────────────────────────────────────────────────


def _build_hand_select_gs(prompt_text="Discard 1 card.", kind="hand"):
    """Minimal GameState with combat + selection for hand_select prompt."""
    from unittest.mock import MagicMock
    from src.mcp_client.upstream_models import RawSelectionCardPayload
    sel_cards = [
        RawSelectionCardPayload(
            index=0, stable_id="strike::0", card_id="strike", name="Strike",
            card_type="Attack", energy_cost=1, rules_text="Deal 6 damage.",
        ),
        RawSelectionCardPayload(
            index=1, stable_id="sly_card::1", card_id="sly_card", name="Sly Test",
            card_type="Skill", energy_cost=1, rules_text="Sly. Test sly card.",
        ),
        RawSelectionCardPayload(
            index=2, stable_id="curse::2", card_id="curse", name="Bad Curse",
            card_type="Curse", energy_cost=0, rules_text="Take 5 HP damage.",
        ),
    ]
    gs = MagicMock()
    sel = MagicMock()
    sel.kind = kind
    sel.prompt = prompt_text
    sel.min_select = 1
    sel.max_select = 1
    sel.selected_count = 0
    sel.can_confirm = False
    sel.cards = sel_cards
    sel.selectable_cards = sel_cards
    sel.selected_cards = []
    gs.selection = sel
    gs.combat = MagicMock()
    gs.combat.player = MagicMock(
        current_hp=40, max_hp=70, energy=3, block=0, powers=[],
    )
    gs.run_info = MagicMock(max_energy=3)
    gs.enemies = []
    return gs


def test_baseline_hand_select_strips_priority_grouping():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        assert "### Discard FIRST" not in prompt
        assert "### Discard SECOND" not in prompt
        assert "plays for free" not in prompt


def test_baseline_hand_select_strips_tactical_flags():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        assert "## Tactical Flags" not in prompt
        assert "Sandpit" not in prompt
        assert "DEATH COUNTDOWN" not in prompt
        assert "PRIORITY: Discard a Sly card" not in prompt


def test_baseline_hand_select_keeps_mechanic_only_mode_hint():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        # Mechanic statement kept
        assert "Discard = temporary" in prompt
        # Strategy advice stripped — there's no strategy advice for plain discard mode,
        # but verify retain mode strips "Retain every non-harmful card"
        retain_prompt = build_hand_select_prompt(_build_hand_select_gs(prompt_text="Retain up to 2 cards."))
        assert "Retain every non-harmful card" not in retain_prompt


def test_baseline_hand_select_lists_all_cards_flat():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        # All 3 cards still appear, just without priority groupings
        assert "Strike" in prompt
        assert "Sly Test" in prompt
        assert "Bad Curse" in prompt


def test_full_hand_select_keeps_priority_grouping():
    with _set_variant("full") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        assert "### Discard FIRST" in prompt or "plays for free" in prompt


# ── PROMPT_HINT_FILTER ───────────────────────────────────────────


@contextmanager
def _set_hint_filter(value: bool):
    original = os.environ.get("STS2_PROMPT_HINT_FILTER")
    os.environ["STS2_PROMPT_HINT_FILTER"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        # Reload prompt modules that read PROMPT_HINT_FILTER
        from src.brain.prompts import reward, shop, rest
        from src.brain.prompts import map as map_prompts
        for m in (reward, shop, rest, map_prompts):
            importlib.reload(m)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_PROMPT_HINT_FILTER", None)
        else:
            os.environ["STS2_PROMPT_HINT_FILTER"] = original
        import config
        importlib.reload(config)
        from src.brain.prompts import reward, shop, rest
        from src.brain.prompts import map as map_prompts
        for m in (reward, shop, rest, map_prompts):
            importlib.reload(m)


def test_hint_filter_strips_relic_synergies_in_shop():
    from tests.conftest import make_shop_gs
    gs = make_shop_gs(relic_name="Anchor")

    with _set_hint_filter(True):
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(gs, deck=[], relics=["Anchor"])
        assert "## Relic Synergies" not in prompt
        assert "safe turn 1" not in prompt  # Anchor's strategy hint


def test_hint_filter_strips_card_notes_in_reward():
    gs = _build_reward_gs()
    from unittest.mock import MagicMock
    speedster = MagicMock()
    speedster.index = 1
    speedster.name = "Speedster"
    speedster.upgraded = False
    speedster.rules_text = "Whenever you draw a card, deal 2 damage."
    speedster.resolved_rules_text = speedster.rules_text
    speedster.dynamic_values = []
    gs.reward.card_options.append(speedster)

    with _set_hint_filter(True):
        from src.brain.prompts.reward import build_card_reward_prompt
        prompt = build_card_reward_prompt(gs, deck=[], relics=[])
        assert "## Card Notes" not in prompt
        assert "Turn-start draw does NOT trigger" not in prompt


def test_hint_filter_off_keeps_hints():
    from tests.conftest import make_shop_gs
    gs = make_shop_gs(relic_name="Burning Blood")

    with _set_hint_filter(False):
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(gs, deck=[], relics=["Burning Blood"])
        assert "## Relic Synergies" in prompt


# ── KNOWLEDGE_STRICT ─────────────────────────────────────────────


@contextmanager
def _set_knowledge_strict(value: bool):
    original = os.environ.get("STS2_KNOWLEDGE_STRICT")
    os.environ["STS2_KNOWLEDGE_STRICT"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        from src.knowledge import injector
        from src.brain.prompts import _boss_guide_fmt
        importlib.reload(injector)
        importlib.reload(_boss_guide_fmt)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_KNOWLEDGE_STRICT", None)
        else:
            os.environ["STS2_KNOWLEDGE_STRICT"] = original
        import config
        importlib.reload(config)


def test_knowledge_strict_strips_event_outcomes():
    with _set_knowledge_strict(True):
        from src.knowledge.injector import inject_event_knowledge
        from unittest.mock import MagicMock
        kb = MagicMock()
        result = inject_event_knowledge("BUGSLAYER", kb)
        assert result == ""


def test_knowledge_strict_strips_monster_patterns():
    with _set_knowledge_strict(True):
        from src.knowledge.injector import _build_monster_info
        from unittest.mock import MagicMock
        kb = MagicMock()
        enemy = MagicMock()
        enemy.name = "Chomper"
        result = _build_monster_info([enemy], kb)
        assert result == []


def test_knowledge_strict_strips_encounter_classification():
    with _set_knowledge_strict(True):
        from src.knowledge.injector import inject_encounter_knowledge
        from unittest.mock import MagicMock
        kb = MagicMock()
        result = inject_encounter_knowledge({"chomper"}, {"Chomper"}, kb)
        assert result == ""


def test_knowledge_strict_strips_upcoming_boss_guide():
    with _set_knowledge_strict(True):
        from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
        from unittest.mock import MagicMock
        gs = MagicMock()
        gs.upcoming_boss_enemy_keys = ["FrogKnight"]
        store = MagicMock()
        result = format_upcoming_boss_guide(gs, "Silent", store)
        assert result == []


def test_knowledge_strict_off_runs_normally():
    with _set_knowledge_strict(False):
        from src.knowledge.injector import _build_monster_info
        from unittest.mock import MagicMock
        kb = MagicMock()
        kb.monsters.get_combat_summary.return_value = "Chomper: HP 30, attacks 12"
        enemy = MagicMock()
        enemy.name = "Chomper"
        result = _build_monster_info([enemy], kb)
        assert len(result) == 1
        assert "Chomper" in result[0]
