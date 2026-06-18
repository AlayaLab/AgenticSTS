"""Tests for CombatConversation history compression.

Verifies that:
1. compress_history() preserves msg[0] (combat_start) unchanged
2. Old rounds are replaced with a compact summary
3. Recent rounds are kept in full detail
4. Alternating user/assistant pattern is maintained after compression
5. Message count is reduced significantly
6. Multiple compressions (incremental) work correctly
7. Edge cases: too few rounds, no-op re-compression
"""

from __future__ import annotations

import pytest

from src.brain.conversation import CombatConversation
from src.mcp_client.upstream_models import (
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState

# ---------------------------------------------------------------------------
# Test helpers — build minimal GameState objects for conversation methods
# ---------------------------------------------------------------------------


def _make_gs(
    *,
    hp: int = 60,
    max_hp: int = 80,
    energy: int = 3,
    block: int = 0,
    combat_round: int = 1,
    enemy_hp: int = 40,
    enemy_max_hp: int = 50,
    enemy_name: str = "Jaw Worm",
    enemy_alive: bool = True,
    hand_cards: list[dict] | None = None,
    floor: int = 3,
) -> GameState:
    """Build a minimal GameState with combat data for testing."""
    if hand_cards is None:
        hand_cards = [
            {
                "index": 0,
                "name": "Strike",
                "energy_cost": 1,
                "playable": True,
                "damage": 6,
                "rules_text": "Deal 6 damage.",
            },
            {
                "index": 1,
                "name": "Defend",
                "energy_cost": 1,
                "playable": True,
                "block": 5,
                "rules_text": "Gain 5 Block.",
            },
            {
                "index": 2,
                "name": "Bash",
                "energy_cost": 2,
                "playable": True,
                "damage": 8,
                "rules_text": "Deal 8 damage. Apply 2 Vulnerable.",
            },
        ]

    hand = [RawCombatHandCardPayload(**c) for c in hand_cards]

    enemy = RawCombatEnemyPayload(
        index=0,
        name=enemy_name,
        current_hp=enemy_hp,
        max_hp=enemy_max_hp,
        is_alive=enemy_alive,
        is_hittable=enemy_alive,
    )

    player = RawCombatPlayerPayload(
        current_hp=hp,
        max_hp=max_hp,
        energy=energy,
        block=block,
    )

    combat = RawCombatPayload(player=player, hand=hand, enemies=[enemy])
    run = RawRunPayload(
        floor=floor,
        current_hp=hp,
        max_hp=max_hp,
        gold=100,
        max_energy=3,
        character_id="ironclad",
        character_name="Ironclad",
    )

    upstream = UpstreamGameState(
        screen="COMBAT",
        in_combat=True,
        turn=combat_round,
        available_actions=["play_card", "end_turn"],
        combat=combat,
        run=run,
    )
    return GameState.from_upstream(upstream)


def _simulate_round(
    conv: CombatConversation,
    round_num: int,
    *,
    cards_played: list[str] | None = None,
    hp_after: int = 55,
    enemy_hp_after: int = 30,
    enemy_alive: bool = True,
) -> None:
    """Simulate one full round: add state -> assistant plan -> execution result."""
    if cards_played is None:
        cards_played = ["Strike", "Defend"]

    gs_round = _make_gs(combat_round=round_num, enemy_hp=40)
    conv.add_round_state(gs_round)

    # Simulate assistant plan response
    conv.add_assistant_plan(
        [
            {"type": "text", "text": f"Round {round_num} plan: play {', '.join(cards_played)}"},
            {
                "type": "tool_use",
                "id": f"tool_{round_num}",
                "name": "combat_plan",
                "input": {"actions": [{"card_name": c} for c in cards_played]},
            },
        ]
    )

    # Simulate execution result
    actions_taken = [f"Played {c} -> Jaw Worm[0]" for c in cards_played]
    gs_after = _make_gs(
        hp=hp_after,
        combat_round=round_num,
        enemy_hp=enemy_hp_after,
        enemy_alive=enemy_alive,
    )
    conv.add_execution_result(actions_taken, gs_after)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompressionBasic:
    """Core compression behavior."""

    def test_no_compress_when_few_rounds(self) -> None:
        """Compression should be a no-op when rounds <= keep_recent."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 2):
            _simulate_round(conv, r)

        msg_count_before = len(conv.messages)
        conv.compress_history(keep_recent=1)
        assert len(conv.messages) == msg_count_before, (
            "Should not compress when round count equals keep_recent"
        )

    def test_compress_single_round_still_produces_summary(self) -> None:
        """With 2 rounds and keep_recent=1, round 1 is compressed.

        Compressing just 1 round may not reduce total message count
        (summary + dummy overhead >= 1 merged round's messages), but
        the summary structure should still be created correctly.
        """
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 3):
            _simulate_round(conv, r)

        conv.compress_history(keep_recent=1)
        msgs = conv.messages

        # Should have summary message present
        has_summary = any(
            isinstance(m.get("content"), str) and "Combat History" in m["content"] for m in msgs
        )
        assert has_summary, "Summary message should be present after compression"
        assert conv._compressed_through == 1

    def test_compress_6_rounds_keep_1(self) -> None:
        """Build 6 rounds, verify compression structure.

        Auto-compression fires at round 5 and 6, so after all 6 rounds
        the conversation should already be compressed.
        """
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 7):
            _simulate_round(conv, r, cards_played=[f"Card_R{r}"])

        # Ensure final compression brings us up to date
        conv.compress_history(keep_recent=1)

        msgs = conv.messages

        # msg[0] must be the original combat_start (UNCHANGED)
        assert msgs[0]["role"] == "user"
        content0 = msgs[0]["content"]
        if isinstance(content0, str):
            assert "## Combat Start" in content0
        else:
            text = " ".join(b.get("text", "") for b in content0 if isinstance(b, dict))
            assert "Combat Start" in text

        # msg[1] must be the summary
        assert msgs[1]["role"] == "user"
        summary_content = msgs[1]["content"]
        assert isinstance(summary_content, str)
        assert "Combat History" in summary_content
        assert "compressed" in summary_content
        # Should contain round summaries for R1-R5
        assert "R1:" in summary_content
        assert "R5:" in summary_content
        # Should NOT contain R6 in the summary (that is kept)
        assert "R6:" not in summary_content

        # msg[2] must be the dummy assistant acknowledgement
        assert msgs[2]["role"] == "assistant"
        assistant_content = msgs[2]["content"]
        if isinstance(assistant_content, list):
            text = assistant_content[0].get("text", "")
        else:
            text = str(assistant_content)
        assert text == "ok"

        # Total message count should be bounded:
        # 1 (combat_start) + 1 (summary) + 1 (dummy assistant) +
        # 1 kept round * ~3 messages each = ~6-7 max
        assert len(msgs) <= 9, f"Expected bounded messages, got {len(msgs)}"

        # Verify no consecutive assistant messages
        for i in range(1, len(msgs)):
            if msgs[i]["role"] == "assistant" and msgs[i - 1]["role"] == "assistant":
                pytest.fail(f"Consecutive assistant messages at indices {i - 1} and {i}")

    def test_automatic_compression_at_round_5(self) -> None:
        """Compression fires automatically when round_count > 4."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 5):
            _simulate_round(conv, r)

        # Round 5: this should trigger compression at the START of add_round_state
        _simulate_round(conv, 5)
        # Round 6
        _simulate_round(conv, 6)

        # After 6 rounds with auto-compression, should have fewer messages
        # than 6 * 3 (round_state + assistant + execution) + 1 (combat_start)
        max_uncompressed = 6 * 3 + 1
        assert len(conv.messages) < max_uncompressed, (
            f"Expected compression to reduce messages: got {len(conv.messages)}"
        )

    def test_compress_preserves_round_summaries(self) -> None:
        """Round summaries should appear in the compressed history block."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        _simulate_round(conv, 1, cards_played=["Neutralize", "Strike"])
        _simulate_round(conv, 2, cards_played=["Bash"])
        _simulate_round(conv, 3, cards_played=["Defend", "Defend"])
        _simulate_round(conv, 4, cards_played=["Strike", "Strike"])
        _simulate_round(conv, 5, cards_played=["Bash"])
        _simulate_round(conv, 6, cards_played=["Defend"])

        conv.compress_history(keep_recent=1)

        msgs = conv.messages
        summary = msgs[1]["content"]
        assert "R1:" in summary
        assert "R2:" in summary

    def test_llm_messages_keep_only_anchor_and_current_round(self) -> None:
        """Outbound prompt history should drop prior-round detailed context."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        _simulate_round(conv, 1, cards_played=["Neutralize", "Strike"])
        conv.record_strategic_note(1, "Keep blocking the big hit first.")

        gs_round_2 = _make_gs(combat_round=2, enemy_hp=28)
        conv.add_round_state(gs_round_2)

        llm_messages = conv.llm_messages
        assert len(llm_messages) == 3
        assert llm_messages[0]["role"] == "user"
        assert "## Combat Start" in str(llm_messages[0]["content"])
        assert llm_messages[1]["role"] == "assistant"
        assert llm_messages[2]["role"] == "user"

        current_round = str(llm_messages[2]["content"])
        assert "## Round 2 State" in current_round
        assert "## Strategic Thread" in current_round
        assert "R1: Keep blocking the big hit first." in current_round
        assert "## Round 1 State" not in current_round
        assert "Round 1 plan:" not in current_round

    def test_llm_messages_replan_is_self_contained(self) -> None:
        """Re-plan within the same round: LLM must still see exactly three
        messages — the anchor, an 'ok' ack, and the latest re-plan state
        which must carry Strategic Thread, CRITICAL RULES, and the full
        re-plan context. No dangling 'unchanged from above' reference, no
        truncation of the original plan reasoning, no stale prior user/
        assistant turns."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        # Round 1: initial state → plan
        conv.add_round_state(gs)
        conv.add_assistant_plan(
            [{"type": "text", "text": "Round 1 plan: play Strike then Defend"}]
        )
        conv.record_strategic_note(1, "Bank Block for the incoming big hit.")

        # Re-plan for round 1 (e.g. draw-card split)
        long_reasoning = (
            "Aggressive burst plan — the Giant is at 41 HP and Deathblow is "
            "imminent. Backflip provides 13 block and draws two cards, "
            "bringing Pinpoint to 2 cost. Defend reduces Pinpoint to 1 cost "
            "once three skills are played so we can chain the kill on turn 2."
        )
        replan_ctx = (
            f"Original plan (1/3 completed): {long_reasoning}\n"
            "Trigger: Backflip changed the current hand."
        )
        conv.add_round_state(gs, replan_context=replan_ctx)

        llm_messages = conv.llm_messages
        assert len(llm_messages) == 3, "Re-plan must still send only 3 messages"
        assert llm_messages[0]["role"] == "user"
        assert "## Combat Start" in str(llm_messages[0]["content"])
        assert llm_messages[1]["role"] == "assistant"
        assert llm_messages[2]["role"] == "user"

        latest = str(llm_messages[2]["content"])

        # Full re-plan context is present — no [:200] truncation.
        assert long_reasoning in latest
        # Strategic Thread re-injected on re-plan.
        assert "## Strategic Thread" in latest
        assert "R1: Bank Block for the incoming big hit." in latest
        # CRITICAL RULES still shown on re-plan.
        assert "CRITICAL RULES:" in latest
        # No more dangling reference.
        assert "unchanged from above" not in latest
        # Stale round 1 plan/state must not leak through.
        assert "Round 1 plan: play Strike then Defend" not in latest

    def test_add_execution_result_no_longer_appends_prompt_message(self) -> None:
        """Execution recaps should not be added back into combat prompt history."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)
        conv.add_round_state(gs)
        conv.add_assistant_plan([{"type": "text", "text": "Round 1 plan"}])

        msg_count_before = len(conv.messages)
        conv.add_execution_result(["Played Strike -> Jaw Worm[0]"], _make_gs(combat_round=1))

        assert len(conv.messages) == msg_count_before
        assert all("Executed:" not in str(msg["content"]) for msg in conv.messages)


class TestCompressionEdgeCases:
    """Edge cases and robustness."""

    def test_compress_idempotent(self) -> None:
        """Calling compress_history twice should be a no-op the second time."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 7):
            _simulate_round(conv, r)

        conv.compress_history(keep_recent=1)
        msgs_first = conv.messages
        count_first = len(msgs_first)

        conv.compress_history(keep_recent=1)
        msgs_second = conv.messages
        count_second = len(msgs_second)

        assert count_first == count_second, (
            f"Second compression changed message count: {count_first} -> {count_second}"
        )

    def test_incremental_compression(self) -> None:
        """Compression should work incrementally as more rounds are added."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        # Build 5 rounds and compress
        for r in range(1, 6):
            _simulate_round(conv, r)
        conv.compress_history(keep_recent=1)

        # Add 3 more rounds (total 8) and compress again
        for r in range(6, 9):
            _simulate_round(conv, r)
        conv.compress_history(keep_recent=1)
        count_after_8 = len(conv.messages)

        # After second compression, should have roughly the same or fewer
        # messages as the fixed window (summary + dummy + 1 recent round)
        # The summary grows, but total message count stays bounded.
        assert count_after_8 < 20, f"Expected bounded message count, got {count_after_8}"

    def test_compression_with_empty_rounds(self) -> None:
        """Rounds with no actions should still compress cleanly."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 7):
            gs_round = _make_gs(combat_round=r)
            conv.add_round_state(gs_round)

            conv.add_assistant_plan(
                [
                    {"type": "text", "text": f"Round {r}: end turn"},
                ]
            )

            # Empty execution
            gs_after = _make_gs(hp=55, combat_round=r)
            conv.add_execution_result([], gs_after)

        conv.compress_history(keep_recent=1)
        msgs = conv.messages

        # Should still have valid structure
        assert msgs[0]["role"] == "user"
        assert "Combat Start" in str(msgs[0]["content"])
        assert msgs[1]["role"] == "user"
        assert "Combat History" in str(msgs[1]["content"])

    def test_compressed_through_prevents_recompression(self) -> None:
        """_compressed_through should prevent redundant work."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 7):
            _simulate_round(conv, r)

        conv.compress_history(keep_recent=1)
        assert conv._compressed_through == 5  # 6 rounds - 1 kept = 5 compressed

        # Without new rounds, compress should be a no-op
        conv.compress_history(keep_recent=1)
        assert conv._compressed_through == 5

    def test_generate_summary_after_compression(self) -> None:
        """generate_combat_summary should still work after compression."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 7):
            _simulate_round(conv, r, hp_after=50)

        conv.compress_history(keep_recent=1)

        summary = conv.generate_combat_summary()
        assert "Jaw Worm" in summary
        assert "6 rounds" in summary
        assert "Outcome: won" in summary


class TestRoundSummaryRecording:
    """Verify _record_round_summary builds correct summaries."""

    def test_summary_captures_card_names(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        _simulate_round(conv, 1, cards_played=["Bash", "Strike"])

        assert len(conv._round_summaries) == 1
        summary = conv._round_summaries[0]
        assert "R1:" in summary
        assert "2cards" in summary

    def test_summary_captures_killed_enemies(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        _simulate_round(conv, 1, cards_played=["Bash"], enemy_alive=False)

        summary = conv._round_summaries[0]
        assert "Jaw Worm" in summary

    def test_summary_with_no_actions(self) -> None:
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        gs_round = _make_gs(combat_round=1)
        conv.add_round_state(gs_round)
        conv.add_assistant_plan([{"type": "text", "text": "End turn"}])
        conv.add_execution_result([], _make_gs(combat_round=1))

        assert len(conv._round_summaries) == 1
        assert "0cards" in conv._round_summaries[0]


class TestMessageAlternation:
    """Verify alternating user/assistant pattern is valid for Anthropic API."""

    def test_no_consecutive_assistant_messages(self) -> None:
        """After compression, there should be no consecutive assistant messages."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 9):
            _simulate_round(conv, r)

        conv.compress_history(keep_recent=1)

        msgs = conv.messages
        for i in range(1, len(msgs)):
            if msgs[i]["role"] == "assistant" and msgs[i - 1]["role"] == "assistant":
                pytest.fail(f"Consecutive assistant messages at indices {i - 1} and {i}")

    def test_first_message_is_user(self) -> None:
        """First message must always be user (Anthropic requirement)."""
        conv = CombatConversation("system prompt")
        gs = _make_gs()
        conv.add_combat_start(gs)

        for r in range(1, 9):
            _simulate_round(conv, r)

        conv.compress_history(keep_recent=1)

        msgs = conv.messages
        assert msgs[0]["role"] == "user"
