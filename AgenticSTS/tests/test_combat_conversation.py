"""Unit tests for CombatConversation message management.

Covers message construction, merging, summary generation, round tracking,
enemy key inference, and combat type classification.
"""

from __future__ import annotations

from src.brain.conversation import CombatConversation
from src.mcp_client.upstream_models import (
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawCombatPowerPayload,
    RawDeckCardPayload,
    RawRunPayload,
    RawRunPotionPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState


# ── Local helpers (signatures differ from conftest) ──────────────


def _make_enemy(
    name: str = "Test Louse",
    index: int = 0,
    hp: int = 30,
    max_hp: int = 30,
    is_alive: bool = True,
) -> RawCombatEnemyPayload:
    return RawCombatEnemyPayload(
        index=index,
        enemy_id=name.lower().replace(" ", "_"),
        name=name,
        current_hp=hp,
        max_hp=max_hp,
        block=0,
        is_alive=is_alive,
    )


def _make_hand_card(
    name: str = "Strike",
    index: int = 0,
    energy_cost: int = 1,
    playable: bool = True,
    damage: int | None = 6,
    rules_text: str = "Deal 6 damage.",
    requires_target: bool = True,
) -> RawCombatHandCardPayload:
    return RawCombatHandCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        energy_cost=energy_cost,
        playable=playable,
        damage=damage,
        rules_text=rules_text,
        requires_target=requires_target,
        target_index_space="enemies" if requires_target else None,
    )


def _make_deck_card(
    name: str = "Strike",
    index: int = 0,
    card_type: str = "Attack",
    energy_cost: int = 1,
    rarity: str = "Starter",
) -> RawDeckCardPayload:
    return RawDeckCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        card_type=card_type,
        energy_cost=energy_cost,
        rarity=rarity,
        rules_text=f"{name} description.",
    )


def _make_combat_gs(
    enemies: list[RawCombatEnemyPayload] | None = None,
    hand: list[RawCombatHandCardPayload] | None = None,
    player_hp: int = 60,
    player_max_hp: int = 80,
    energy: int = 3,
    floor: int = 6,
    state_type_hint: str = "boss",
    turn: int = 1,
    deck: list[RawDeckCardPayload] | None = None,
    potions: list[RawRunPotionPayload] | None = None,
) -> GameState:
    """Build a GameState suitable for combat tests."""
    if enemies is None:
        enemies = [_make_enemy()]
    if hand is None:
        hand = [
            _make_hand_card("Strike", 0),
            _make_hand_card(
                "Defend", 1, damage=None, rules_text="Gain 5 block.", requires_target=False
            ),
        ]
    if deck is None:
        deck = [_make_deck_card("Strike", 0), _make_deck_card("Defend", 1, card_type="Skill")]

    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(
            current_hp=player_hp,
            max_hp=player_max_hp,
            energy=energy,
        ),
        hand=hand,
        enemies=enemies,
    )

    run = RawRunPayload(
        character_id="ironclad",
        character_name="Ironclad",
        floor=floor,
        current_hp=player_hp,
        max_hp=player_max_hp,
        gold=120,
        max_energy=3,
        deck=deck,
        potions=potions or [],
    )

    raw = UpstreamGameState(
        screen=state_type_hint.upper(),
        in_combat=True,
        turn=turn,
        available_actions=["play_card", "end_turn"],
        combat=combat,
        run=run,
    )

    return GameState(raw=raw, state_type=state_type_hint)


# ═══════════════════════════════════════════════════════════════
# CombatConversation tests
# ═══════════════════════════════════════════════════════════════


class TestCombatConversation:
    """Tests for CombatConversation message management."""

    def test_combat_start_creates_user_message(self):
        """add_combat_start should produce a role=user message with enemy/player info."""
        gs = _make_combat_gs()
        conv = CombatConversation(system_prompt="You are a test agent.")
        conv.add_combat_start(gs)

        msgs = conv.messages
        # combat_start (user) + dummy assistant separator
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

        content = msgs[0]["content"]
        assert isinstance(content, str)
        assert "Combat Start" in content
        assert "Test Louse" in content
        assert "60/80" in content  # Player HP

    def test_round_state_adds_user_message(self):
        """add_round_state should create a user message with hand/energy info."""
        gs = _make_combat_gs()
        conv = CombatConversation(system_prompt="test")
        # Start combat first, then add round state
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)

        msgs = conv.messages
        # combat_start(user) + dummy_asst + assistant_plan(assistant) + round_state(user)
        assert len(msgs) == 4
        assert msgs[3]["role"] == "user"

        content = msgs[3]["content"]
        assert "Round" in content
        assert "Energy" in content

    def test_round_state_emphasizes_turn_bound_hand_and_block_rules(self):
        """Round state should remind the model that hand/block do not persist by default."""
        gs = _make_combat_gs()
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)

        content = conv.messages[-1]["content"]
        assert "Cards DRAWN or CREATED this turn enter your CURRENT hand now." in content
        assert "Hand size limit is 10 cards." in content
        assert "Current Block only matters for the upcoming enemy turn." in content
        assert "Draw pile order is only a CONDITIONAL forecast." in content

    def test_invincible_phase_discourages_all_exhaust_cards_without_zero_cost_rule(self):
        """Setup-phase prompt should not push one-shot resources just because cost is 0."""
        gs = _make_combat_gs(
            enemies=[_make_enemy("Phase Gate", hp=999999999, max_hp=999999999)],
            hand=[
                _make_hand_card(
                    "Setup Tool",
                    energy_cost=0,
                    damage=None,
                    rules_text="Draw 2 cards. Exhaust.",
                    requires_target=False,
                )
            ],
        )
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        conv.add_round_state(gs)

        content = str(conv.messages[-1]["content"])
        assert "Do not play exhaust cards" in content
        assert "Do not play exhaust attack cards" not in content
        assert "0-cost cards" not in content
        assert "ALWAYS play them" not in content

    def test_round_state_warns_when_hand_near_cap(self):
        """Large hands should warn that generated cards may be lost to the 10-card cap."""
        hand = [
            _make_hand_card("Defend", i, damage=None, rules_text="Gain 5 block.", requires_target=False)
            for i in range(8)
        ]
        gs = _make_combat_gs(hand=hand)
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)

        content = conv.messages[-1]["content"]
        assert "!! HAND SIZE: 8/10." in content
        assert "draw/add-to-hand effects beyond 10 are lost" in content

    def test_round_state_infers_hand_card_types_from_deck(self):
        """Combat hand lines should include Attack/Skill/Power style types."""
        gs = _make_combat_gs(
            hand=[
                _make_hand_card(
                    "Pinpoint",
                    0,
                    energy_cost=2,
                    damage=17,
                    rules_text=(
                        "Deal 17 damage. Costs 1 less 1 energy for each Skill played this turn."
                    ),
                ),
                _make_hand_card(
                    "Deadly Poison++",
                    1,
                    energy_cost=1,
                    damage=None,
                    rules_text="Apply 7 Poison.",
                ),
                _make_hand_card(
                    "Echoing Slash",
                    2,
                    energy_cost=1,
                    damage=10,
                    rules_text="Deal 10 damage to ALL enemies.",
                    requires_target=False,
                ),
            ],
            deck=[
                _make_deck_card("Pinpoint", 0, card_type="Attack", energy_cost=2),
                _make_deck_card("Deadly Poison", 1, card_type="Skill", energy_cost=1),
                _make_deck_card("Echoing Slash", 2, card_type="Attack", energy_cost=1),
            ],
        )
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)

        content = conv.messages[-1]["content"]
        assert "Pinpoint (Attack, cost=2)" in content
        assert "Deadly Poison+++ (Skill, cost=1)" not in content
        assert "Deadly Poison++ (Skill, cost=1)" in content
        assert "Echoing Slash (Attack, cost=1)" in content

    def test_round_state_warns_when_potion_slots_are_full(self):
        """Combat prompt should warn that Alchemize fizzles into a full inventory."""
        gs = _make_combat_gs(
            hand=[
                _make_hand_card(
                    "Alchemize",
                    0,
                    energy_cost=1,
                    damage=None,
                    rules_text="Procure a random potion. Exhaust.",
                    requires_target=False,
                ),
            ],
            deck=[
                _make_deck_card("Alchemize", 0, card_type="Skill", energy_cost=1),
            ],
            potions=[
                RawRunPotionPayload(index=0, name="Energy Potion", occupied=True, can_use=True),
                RawRunPotionPayload(index=1, name="Weak Potion", occupied=True, can_use=True),
                RawRunPotionPayload(index=2, name="Weak Potion", occupied=True, can_use=True),
            ],
        )
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)

        content = conv.messages[-1]["content"]
        assert "Potion slots: 3/3 FULL" in content
        assert "!! POTION SLOTS FULL: Alchemize will not add a potion" in content

    def test_round_state_prepends_extra_context(self):
        """add_round_state should prepend computed insights into the user message."""
        gs = _make_combat_gs()
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])

        extra = "## Computed Insights\n**turn_lethal_check**: NO-GO"
        conv.add_round_state(gs, extra_context=extra)

        content = conv.messages[-1]["content"]
        assert isinstance(content, str)
        assert content.startswith(extra)
        assert "## Round" in content

    def test_round_state_uses_poison_description_without_poison_lethal_banner(self):
        """Enemy Poison should explain timing without adding a loud special-case banner."""
        enemy = RawCombatEnemyPayload(
            index=0,
            enemy_id="test_louse",
            name="Test Louse",
            current_hp=30,
            max_hp=30,
            block=0,
            is_alive=True,
            powers=[
                RawCombatPowerPayload(
                    index=0,
                    power_id="Poison",
                    name="Poison",
                    amount=12,
                    is_debuff=True,
                )
            ],
        )
        gs = _make_combat_gs(enemies=[enemy])
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)

        content = conv.messages[-1]["content"]
        assert "Poison(12): Loses N HP at the start of its turn, before it acts" in content
        assert "POISON LETHAL" not in content

    def test_assistant_plan_adds_assistant_message(self):
        """add_assistant_plan should record an assistant message."""
        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs()
        conv.add_combat_start(gs)

        blocks = [{"type": "text", "text": "play Strike on enemy 0"}]
        conv.add_assistant_plan(blocks)

        msgs = conv.messages
        assert len(msgs) == 3  # combat_start + dummy_asst + plan
        assert msgs[2]["role"] == "assistant"
        assert msgs[2]["content"] == blocks

    def test_record_strategic_note_rejects_unstable_future_hand_claim(self):
        """Future-hand certainty should not be persisted into later rounds."""
        conv = CombatConversation(system_prompt="test")
        conv.record_strategic_note(
            1,
            "Next turn has Deadly Poison, Blade Dance, Dagger Spray + 3 energy.",
        )

        assert conv._strategic_notes == []

    def test_record_strategic_note_keeps_durable_combat_plan(self):
        """Durable tactical notes should still carry forward."""
        conv = CombatConversation(system_prompt="test")
        conv.record_strategic_note(2, "Poison at 15 — survive 2 more rounds.")

        assert conv._strategic_notes == [(2, "Poison at 15 — survive 2 more rounds.")]

    def test_combat_start_separated_from_round_state(self):
        """Round state should NOT merge into combat_start (dummy assistant separator)."""
        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs()

        conv.add_combat_start(gs)
        conv.add_round_state(gs)

        msgs = conv.messages
        # combat_start(user) + dummy_asst + round_state(user)
        assert len(msgs) == 3
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"
        assert msgs[2]["role"] == "user"
        # Combat start in msg[0], round state in msg[2]
        assert "Combat Start" in msgs[0]["content"]
        assert "Round" in msgs[2]["content"]

    def test_messages_mut_returns_internal_ref(self):
        """messages_mut should return the SAME internal list (not a copy)."""
        conv = CombatConversation(system_prompt="test")
        ref1 = conv.messages_mut
        ref2 = conv.messages_mut
        assert ref1 is ref2
        # Mutating the returned list should affect the conversation
        ref1.append({"role": "user", "content": "test"})
        assert len(conv.messages_mut) == 1

    def test_messages_returns_copy(self):
        """messages (property) should return a DIFFERENT list each time."""
        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs()
        conv.add_combat_start(gs)

        copy1 = conv.messages
        copy2 = conv.messages
        assert copy1 is not copy2
        assert copy1 == copy2
        # Mutating copy should not affect original
        copy1.append({"role": "assistant", "content": "extra"})
        assert len(conv.messages) == 2  # combat_start + dummy_asst

    def test_execution_result_recorded(self):
        """add_execution_result should update summaries without appending prompt text."""
        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs()
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])

        actions = ["Strike -> Test Louse[0] (6 dmg)"]
        conv.add_execution_result(actions, gs)

        msgs = conv.messages
        assert len(msgs) == 3  # combat_start + dummy_asst + plan
        assert "Strike -> Test Louse[0]" not in str(msgs)
        assert conv._round_summaries
        assert "1cards" in conv._round_summaries[0]

    def test_execution_result_no_actions(self):
        """add_execution_result with empty actions should still record a round summary only."""
        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs()
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])

        conv.add_execution_result([], gs)

        msgs = conv.messages
        assert len(msgs) == 3
        assert all("No actions were executed" not in str(msg["content"]) for msg in msgs)
        assert conv._round_summaries
        assert "0cards" in conv._round_summaries[0]

    def test_generate_combat_summary(self):
        """Summary should contain enemy key, rounds, HP delta, outcome."""
        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs(enemies=[_make_enemy("Jaw Worm", 0, 42, 42)])
        conv.add_combat_start(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)
        conv.add_assistant_plan([{"type": "text", "text": "plan 2"}])
        conv.add_round_state(_make_combat_gs(enemies=[_make_enemy("Jaw Worm", 0, 42, 42)], turn=2))

        summary = conv.generate_combat_summary()
        assert "Jaw Worm" in summary
        assert "2 rounds" in summary
        assert "boss" in summary.lower()

    def test_round_count_tracks_actual_combat_round(self):
        """Same-round replans should not inflate round_count."""
        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs()
        assert conv.round_count == 0

        conv.add_combat_start(gs)
        conv.add_round_state(gs)
        assert conv.round_count == 1

        # Same combat round: should remain at 1 for re-plan/retry prompts.
        conv.add_assistant_plan([{"type": "text", "text": "plan"}])
        conv.add_round_state(gs)
        assert conv.round_count == 1

        # Next real combat round should advance.
        gs_round_2 = _make_combat_gs(turn=2)
        conv.add_assistant_plan([{"type": "text", "text": "plan 2"}])
        conv.add_round_state(gs_round_2)
        assert conv.round_count == 2

    def test_system_prompt_stored(self):
        """system_prompt property should return the value passed to __init__."""
        conv = CombatConversation(system_prompt="My custom system prompt")
        assert conv.system_prompt == "My custom system prompt"

    def test_enemy_key_set_from_combat_start(self):
        """enemy_key should reflect the enemies present at combat start."""
        enemies = [
            _make_enemy("Louse", 0, 20, 20),
            _make_enemy("Louse", 1, 18, 18),
        ]
        gs = _make_combat_gs(enemies=enemies)
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)

        assert conv.enemy_key == "Louse + Louse"

    def test_combat_type_boss(self):
        """combat_type should be 'boss' when state_type contains 'boss'."""
        gs = _make_combat_gs(state_type_hint="boss")
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        assert conv.combat_type == "boss"

    def test_combat_type_monster(self):
        """combat_type should be 'monster' for non-boss/non-elite."""
        gs = _make_combat_gs(state_type_hint="monster")
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)
        assert conv.combat_type == "monster"

    def test_combat_start_includes_boss_stage_context(self):
        gs = _make_combat_gs(state_type_hint="boss", floor=51)
        conv = CombatConversation(system_prompt="test")
        conv.add_combat_start(gs)

        content = conv.messages[0]["content"]
        assert "Encounter type: boss" in content
        assert "Boss stage: final_boss" in content
        assert "Act: 3 | Floor: 51" in content
