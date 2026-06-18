"""Unit tests for combat trace plan grouper."""
from __future__ import annotations


def test_parse_plan_step_extracts_idx_size_card_body():
    from src.memory.combat_trace_plan_grouper import parse_reasoning, ParsedReasoning

    reasoning = (
        "Plan [3/13]: Shiv — Enemy is summoning, so we have a free turn to "
        "set up our scaling and deal massive damage."
    )
    parsed = parse_reasoning(reasoning, {"action": "play_card", "card_index": 5}, "plan")
    assert parsed.kind == "plan_step"
    assert parsed.step_idx == 3
    assert parsed.plan_size == 13
    assert parsed.card_name == "Shiv"
    assert parsed.plan_reasoning_body.startswith("Enemy is summoning")
    assert parsed.raw == reasoning


def test_parse_plan_step_handles_double_plus_card_name():
    from src.memory.combat_trace_plan_grouper import parse_reasoning

    reasoning = "Plan [1/5]: Phantom Blades++ — Set up scaling early."
    parsed = parse_reasoning(reasoning, {"action": "play_card"}, "plan")
    assert parsed.kind == "plan_step"
    assert parsed.card_name == "Phantom Blades++"
    assert parsed.plan_reasoning_body == "Set up scaling early."


def test_parse_sub_action_select_deck_card():
    from src.memory.combat_trace_plan_grouper import parse_reasoning

    reasoning = "Plan discard: Strike+, Defend+ (planned with Hidden Daggers+)"
    parsed = parse_reasoning(reasoning, {"action": "select_deck_card", "option_index": 6}, "plan")
    assert parsed.kind == "sub_action"
    assert parsed.raw == reasoning


def test_parse_sub_action_confirm_selection():
    from src.memory.combat_trace_plan_grouper import parse_reasoning

    parsed = parse_reasoning(
        "Confirm hand selection (1/0)", {"action": "confirm_selection"}, "plan",
    )
    assert parsed.kind == "sub_action"


def test_parse_end_turn_via_action_field():
    from src.memory.combat_trace_plan_grouper import parse_reasoning

    parsed = parse_reasoning(
        "Plan: end turn — retain Piercing Wail for the multi-hit attack.",
        {"action": "end_turn"}, "plan",
    )
    assert parsed.kind == "end_turn"


def test_parse_heuristic_when_source_random():
    from src.memory.combat_trace_plan_grouper import parse_reasoning

    parsed = parse_reasoning(
        "Stuck recovery: dismiss modal via confirm_modal",
        {"action": "confirm_modal"}, "random",
    )
    assert parsed.kind == "heuristic"


def test_parse_heuristic_when_no_pattern_matches():
    from src.memory.combat_trace_plan_grouper import parse_reasoning

    parsed = parse_reasoning(
        "Throw 1 Foul Potion at merchant for 30 gold",
        {"action": "use_potion"}, "plan",
    )
    assert parsed.kind == "heuristic"


def test_parse_plan_step_with_em_dash_in_body_does_not_split_again():
    """Body itself may contain a hyphen — make sure we only split on the FIRST ' — '."""
    from src.memory.combat_trace_plan_grouper import parse_reasoning

    reasoning = "Plan [1/2]: Strike — Deal damage — high-priority target."
    parsed = parse_reasoning(reasoning, {"action": "play_card"}, "plan")
    assert parsed.card_name == "Strike"
    assert parsed.plan_reasoning_body == "Deal damage — high-priority target."


def _dec(step: int, action: dict, reasoning: str, source: str = "plan") -> dict:
    """Helper to build a decision event."""
    return {
        "event": "decision", "floor": 1, "step": step,
        "action": action, "reasoning": reasoning, "source": source,
    }


def test_group_single_plan_block_all_steps():
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks, PlanBlock

    body = "Free turn, set up scaling."
    decisions = [
        _dec(10, {"action": "play_card", "card_index": 0}, f"Plan [1/3]: Strike — {body}"),
        _dec(11, {"action": "play_card", "card_index": 1}, f"Plan [2/3]: Defend — {body}"),
        _dec(12, {"action": "play_card", "card_index": 2}, f"Plan [3/3]: Backstab — {body}"),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 1
    block = blocks[0]
    assert isinstance(block, PlanBlock)
    assert block.letter == "A"
    assert block.intended == ["Strike", "Defend", "Backstab"]
    assert block.plan_reasoning_body == body
    assert [step.card_name for step in block.executed] == ["Strike", "Defend", "Backstab"]
    assert block.first_step == 10
    assert block.last_step == 12


def test_group_two_plans_split_by_different_body():
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks

    decisions = [
        _dec(10, {"action": "play_card", "card_index": 0}, "Plan [1/2]: Strike — Body A."),
        _dec(11, {"action": "play_card", "card_index": 1}, "Plan [2/2]: Defend — Body A."),
        _dec(12, {"action": "play_card", "card_index": 2}, "Plan [1/1]: Backstab — Body B."),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 2
    assert blocks[0].letter == "A"
    assert blocks[0].intended == ["Strike", "Defend"]
    assert blocks[0].plan_reasoning_body == "Body A."
    assert blocks[1].letter == "B"
    assert blocks[1].intended == ["Backstab"]
    assert blocks[1].plan_reasoning_body == "Body B."


def test_group_two_plans_split_by_step_idx_reset_even_if_body_matches():
    """Defensive backstop: identical body but step_idx resets to 1 → new block."""
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks

    body = "Identical body for both plans."
    decisions = [
        _dec(10, {"action": "play_card"}, f"Plan [1/2]: Strike — {body}"),
        _dec(11, {"action": "play_card"}, f"Plan [2/2]: Defend — {body}"),
        _dec(12, {"action": "play_card"}, f"Plan [1/1]: Backstab — {body}"),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 2


def test_group_sub_action_folds_into_parent_plan_step():
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks, PlanBlock

    decisions = [
        _dec(10, {"action": "play_card", "card_index": 0}, "Plan [1/2]: Hidden Daggers — Set up Shivs."),
        _dec(11, {"action": "select_deck_card", "option_index": 6}, "Plan discard: Strike+, Defend+ (planned with Hidden Daggers)"),
        _dec(12, {"action": "play_card", "card_index": 5}, "Plan [2/2]: Shiv — Set up Shivs."),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 1
    block = blocks[0]
    assert isinstance(block, PlanBlock)
    assert len(block.executed) == 2
    assert block.executed[0].card_name == "Hidden Daggers"
    assert len(block.executed[0].sub_actions) == 1
    assert block.executed[0].sub_actions[0].raw.startswith("Plan discard")
    assert block.executed[1].card_name == "Shiv"
    assert block.executed[1].sub_actions == []


def test_group_end_turn_emits_standalone_block():
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks, PlanBlock, EndTurnBlock

    decisions = [
        _dec(10, {"action": "play_card", "card_index": 0}, "Plan [1/1]: Strike — Lead."),
        _dec(11, {"action": "end_turn"}, "Plan: end turn — Done with damage."),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 2
    assert isinstance(blocks[0], PlanBlock)
    assert isinstance(blocks[1], EndTurnBlock)
    assert blocks[1].reasoning == "Plan: end turn — Done with damage."


def test_group_heuristic_emits_standalone_block():
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks, HeuristicBlock

    decisions = [
        _dec(10, {"action": "confirm_modal"}, "Stuck recovery: dismiss modal", source="random"),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 1
    assert isinstance(blocks[0], HeuristicBlock)
    assert blocks[0].action == {"action": "confirm_modal"}
    assert blocks[0].source == "random"


def test_group_letter_resets_per_call():
    """A new call starts at letter A again — letters are per-round."""
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks

    decisions = [
        _dec(10, {"action": "play_card"}, "Plan [1/1]: Strike — One."),
        _dec(11, {"action": "play_card"}, "Plan [1/1]: Defend — Two."),
        _dec(12, {"action": "play_card"}, "Plan [1/1]: Backstab — Three."),
    ]
    blocks_round1 = group_decisions_into_blocks(decisions)
    assert [b.letter for b in blocks_round1] == ["A", "B", "C"]
    blocks_round2 = group_decisions_into_blocks(decisions)
    assert [b.letter for b in blocks_round2] == ["A", "B", "C"]


def test_group_orphan_sub_action_emits_as_heuristic_not_crash():
    """Sub-action with no preceding plan step → heuristic, not a crash."""
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks, HeuristicBlock

    decisions = [
        _dec(10, {"action": "select_deck_card"}, "Plan discard: Strike+ (orphan)"),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 1
    assert isinstance(blocks[0], HeuristicBlock)


def test_group_plan_block_captures_intended_size_from_prefix():
    """`intended_size` reflects the original M from Plan [N/M], not the
    observed step count — important for partial-execution display."""
    from src.memory.combat_trace_plan_grouper import group_decisions_into_blocks

    # Plan [N/5] body, but only 2 steps observed before a different body
    # (simulating a hand-change replan that cut the plan short)
    decisions = [
        _dec(10, {"action": "play_card"}, "Plan [1/5]: Strike — Plan A body."),
        _dec(11, {"action": "play_card"}, "Plan [2/5]: Defend — Plan A body."),
        _dec(12, {"action": "play_card"}, "Plan [1/1]: Backstab — Plan B body."),
    ]
    blocks = group_decisions_into_blocks(decisions)
    assert len(blocks) == 2
    # Plan A: original size 5, but only 2 executed
    assert blocks[0].intended_size == 5
    assert blocks[0].intended == ["Strike", "Defend"]
    assert len(blocks[0].executed) == 2
    # Plan B: original size 1, 1 executed
    assert blocks[1].intended_size == 1
    assert blocks[1].intended == ["Backstab"]


# ---------------------------------------------------------------------------
# Task 3: Text formatters
# ---------------------------------------------------------------------------

def test_format_plan_block_basic():
    from src.memory.combat_trace_plan_grouper import (
        PlanBlock, ExecutedStep, format_plan_block_text,
    )
    block = PlanBlock(
        letter="A",
        intended=["Strike", "Defend", "Backstab"],
        plan_reasoning_body="Free turn, set up scaling.",
        first_step=10, last_step=12,
        intended_size=3,
        executed=[
            ExecutedStep(card_name="Strike", decision_step=10, action={}),
            ExecutedStep(card_name="Defend", decision_step=11, action={}),
            ExecutedStep(card_name="Backstab", decision_step=12, action={}),
        ],
    )
    out = format_plan_block_text(block)
    assert "[A] intended 3 → Strike, Defend, Backstab" in out
    assert "Reason: Free turn, set up scaling." in out
    assert "Executed 3/3: Strike, Defend, Backstab" in out


def test_format_plan_block_collapses_repeated_cards_with_x_notation():
    from src.memory.combat_trace_plan_grouper import (
        PlanBlock, ExecutedStep, format_plan_block_text,
    )
    block = PlanBlock(
        letter="C", intended=["Accuracy", "Shiv", "Shiv", "Shiv", "Shiv", "Backflip"],
        plan_reasoning_body="Dump shivs.", first_step=10, last_step=15,
        intended_size=6,
        executed=[
            ExecutedStep(card_name="Accuracy", decision_step=10, action={}),
            ExecutedStep(card_name="Shiv", decision_step=11, action={}),
            ExecutedStep(card_name="Shiv", decision_step=12, action={}),
            ExecutedStep(card_name="Shiv", decision_step=13, action={}),
            ExecutedStep(card_name="Shiv", decision_step=14, action={}),
            ExecutedStep(card_name="Backflip", decision_step=15, action={}),
        ],
    )
    out = format_plan_block_text(block)
    assert "[C] intended 6 → Accuracy, Shiv×4, Backflip" in out
    assert "Executed 6/6: Accuracy, Shiv×4, Backflip" in out


def test_format_plan_block_partial_execution():
    """Plan was cut short: intended_size=5, but only 2 names observed and executed."""
    from src.memory.combat_trace_plan_grouper import (
        PlanBlock, ExecutedStep, format_plan_block_text,
    )
    block = PlanBlock(
        letter="A", intended=["Strike", "Defend"],   # only the 2 observed
        plan_reasoning_body="Plan A.", first_step=10, last_step=11,
        intended_size=5,                              # original M from prefix
        executed=[
            ExecutedStep(card_name="Strike", decision_step=10, action={}),
            ExecutedStep(card_name="Defend", decision_step=11, action={}),
        ],
    )
    out = format_plan_block_text(block)
    # We don't know the unexecuted names, so the "intended" line lists only
    # what we observed. The count uses intended_size (5).
    assert "[A] intended 5 → Strike, Defend" in out
    assert "Executed 2/5: Strike, Defend" in out


def test_format_plan_block_folds_sub_actions_into_parent():
    from src.memory.combat_trace_plan_grouper import (
        PlanBlock, ExecutedStep, ParsedReasoning, format_plan_block_text,
    )
    block = PlanBlock(
        letter="A", intended=["Hidden Daggers", "Shiv"],
        plan_reasoning_body="Set up shivs.", first_step=10, last_step=12,
        intended_size=2,
        executed=[
            ExecutedStep(
                card_name="Hidden Daggers", decision_step=10, action={},
                sub_actions=[ParsedReasoning(
                    kind="sub_action",
                    raw="Plan discard: Strike+, Defend+ (planned with Hidden Daggers)",
                )],
            ),
            ExecutedStep(card_name="Shiv", decision_step=12, action={}),
        ],
    )
    out = format_plan_block_text(block)
    assert "Executed 2/2: Hidden Daggers (discarded Strike+, Defend+), Shiv" in out


def test_format_plan_block_folds_purity_exhaust_sub_action():
    from src.memory.combat_trace_plan_grouper import (
        PlanBlock, ExecutedStep, ParsedReasoning, format_plan_block_text,
    )
    block = PlanBlock(
        letter="D", intended=["Purity"],
        plan_reasoning_body="Thin Strike.", first_step=20, last_step=22,
        intended_size=1,
        executed=[
            ExecutedStep(
                card_name="Purity", decision_step=20, action={},
                sub_actions=[
                    ParsedReasoning(
                        kind="sub_action",
                        raw="Exhausting the Strike to thin the deck.",
                    ),
                    ParsedReasoning(kind="sub_action", raw="Confirm hand selection (1/0)"),
                ],
            ),
        ],
    )
    out = format_plan_block_text(block)
    assert "Executed 1/1: Purity (exhausted Strike)" in out


def test_format_end_turn_block_strips_prefix():
    from src.memory.combat_trace_plan_grouper import EndTurnBlock, format_end_turn_block_text

    block = EndTurnBlock(
        reasoning="Plan: end turn — Retain Wail for next turn.",
        decision_step=99,
    )
    out = format_end_turn_block_text(block)
    assert out.startswith("  [end_turn] Reason:")
    assert "Retain Wail for next turn." in out
    assert "Plan: end turn —" not in out  # prefix stripped


def test_format_heuristic_block():
    from src.memory.combat_trace_plan_grouper import HeuristicBlock, format_heuristic_block_text

    block = HeuristicBlock(
        reasoning="Stuck recovery: dismiss modal via confirm_modal",
        decision_step=42, action={"action": "confirm_modal"}, source="random",
    )
    out = format_heuristic_block_text(block)
    assert "[heuristic: random]" in out
    assert "confirm_modal" in out
    assert "dismiss modal" in out
