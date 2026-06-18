"""Combat turn planner: plan-then-execute architecture for combat.

Instead of asking the LLM for one card at a time (slow, loses context),
the planner asks for a full turn's card sequence. Card names are used
instead of indices since indices shift after each play.

Key features:
- Card-name resolution: plan uses names, resolved to indices at execution time
- Draw-card splitting: if a planned card draws/adds cards, the plan is
  discarded after that card and a new plan is generated with the new hand
- Energy tracking: plan respects energy budget
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.brain.card_effects import detect_draws_cards
from src.state.game_state import GameState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlannedAction:
    """A single planned action within a turn: card play or potion use."""

    action_type: str = "card"  # "card" or "potion"
    card_name: str = ""  # for type=card
    potion_index: int | None = None  # for type=potion
    potion_name: str = ""  # fallback for type=potion when the model omits the index
    target_index: int | None = None  # enemy index or None
    discard: str | tuple[str, ...] = ""  # discard target(s) for Survivor/Prepared-like effects

    @property
    def is_potion(self) -> bool:
        return self.action_type == "potion"


@dataclass(frozen=True)
class CombatPlan:
    """A full turn plan: sequence of card plays + end_turn flag."""

    actions: tuple[PlannedAction, ...]
    end_turn: bool = True
    reasoning: str = ""
    reasoning_zh: str = ""  # Display-only translation; empty unless STS2_DISPLAY_LANGUAGE=zh
    analysis: dict[str, Any] | None = None
    note_to_future_self: str = ""
    # Diagnostic trace populated by V2Engine._parse_combat_plan when available.
    # Keys: ``raw_text`` (LLM output), ``decision_input`` (parsed dict that fed
    # the parser). Read by zh-loss anomaly dumper in agent loop. Excluded from
    # equality / repr to keep CombatPlan a value type.
    _debug_trace: dict[str, Any] | None = field(default=None, compare=False, repr=False)

    @property
    def is_empty(self) -> bool:
        return len(self.actions) == 0


def is_draw_card(description: str) -> bool:
    """Check if a card's description suggests it draws or adds cards to hand.

    These cards change the hand unpredictably, so the combat plan must be
    split at this point — execute up to and including this card, then re-plan.
    """
    return detect_draws_cards(description)


def resolve_card_name(card_name: str, gs: GameState) -> int | None:
    """Resolve a card name to its current index in hand.

    Returns the index of the first playable card matching the name,
    or None if not found / not playable.

    Matching is case-insensitive and handles upgraded cards (Name+).
    """
    if not gs.hand:
        return None

    name_lower = card_name.lower().rstrip("+")

    # First pass: exact match on playable cards
    for card in gs.hand:
        if not card.playable:
            continue
        card_lower = card.name.lower().rstrip("+")
        if card_lower == name_lower:
            return card.index

    # Second pass: plan name as substring of card name (e.g. "Falling Star" matches "Falling Star+")
    # Only checks plan-name-in-card-name direction to avoid false positives
    # (e.g. card "Ball" should NOT match plan "Fireball")
    for card in gs.hand:
        if not card.playable:
            continue
        card_lower = card.name.lower()
        if name_lower in card_lower:
            return card.index

    return None


def parse_combat_plan(raw_text: str) -> CombatPlan | None:
    """Parse LLM response into a CombatPlan.

    Expected format:
    {
      "plan": [
        {"card": "Falling Star", "target_index": 0},
        {"card": "Venerate", "target_index": -1},
        {"card": "Gather Light", "target_index": -1}
      ],
      "end_turn": true,
      "reasoning": "Apply debuff first, then block"
    }
    """
    text = raw_text.strip()

    # Strip markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Extract JSON from mixed text
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try recovery: extract plan array
        data = _recover_plan_json(text)
        if not data:
            logger.warning("Combat plan: invalid JSON: %s", raw_text[:300])
            return None

    plan_list = data.get("plan", [])
    if not isinstance(plan_list, list):
        logger.warning("Combat plan: 'plan' is not a list")
        return None

    planned_actions = []
    for item in plan_list:
        if not isinstance(item, dict):
            continue

        # Parse target_index (shared by both types)
        raw_target = item.get("target_index")
        if isinstance(raw_target, int):
            target_index = raw_target if raw_target >= 0 else None
        elif isinstance(raw_target, str):
            try:
                val = int(raw_target)
                target_index = val if val >= 0 else None
            except ValueError:
                target_index = None
        else:
            target_index = None

        action_type = item.get("type", "card")

        if action_type == "potion":
            potion_idx = item.get("potion_index")
            potion_name = str(item.get("potion") or item.get("name") or "").strip()
            if isinstance(potion_idx, str):
                try:
                    potion_idx = int(potion_idx)
                except ValueError:
                    potion_idx = None
            if potion_idx is None and not potion_name:
                logger.warning("Combat plan: potion entry missing potion_index, skipping")
                continue
            planned_actions.append(PlannedAction(
                action_type="potion",
                potion_index=potion_idx,
                potion_name=potion_name,
                target_index=target_index,
            ))
        else:
            # Default: card type (also handles plans without explicit "type" field)
            card_name = item.get("card", "")
            if not card_name:
                continue
            discard = _normalize_discard_field(item.get("discard", ""))
            planned_actions.append(PlannedAction(
                action_type="card", card_name=card_name, target_index=target_index,
                discard=discard,
            ))

    end_turn = data.get("end_turn", True)
    reasoning = data.get("reasoning", "")
    if isinstance(reasoning, list | tuple):
        reasoning = " ".join(
            text for item in reasoning if (text := str(item).strip())
        )
    elif reasoning is None:
        reasoning = ""
    elif not isinstance(reasoning, str):
        reasoning = str(reasoning)
    reasoning_zh_raw = data.get("reasoning_zh", "")
    reasoning_zh = reasoning_zh_raw if isinstance(reasoning_zh_raw, str) else ""
    analysis = data.get("analysis")
    if not isinstance(analysis, dict):
        analysis = {}
    if not reasoning and analysis.get("chosen_line"):
        reasoning = str(analysis["chosen_line"])
    note = data.get("note_to_future_self", "") or ""

    if not planned_actions:
        # Preserve the model's explicit end_turn choice so callers can decide
        # whether to fall back when the parsed action list ended up empty.
        return CombatPlan(
            actions=(),
            end_turn=bool(end_turn),
            reasoning=reasoning or "No cards to play",
            reasoning_zh=reasoning_zh,
            analysis=analysis,
            note_to_future_self=note,
        )

    return CombatPlan(
        actions=tuple(planned_actions),
        end_turn=bool(end_turn),
        reasoning=reasoning,
        reasoning_zh=reasoning_zh,
        analysis=analysis,
        note_to_future_self=note,
    )


def _normalize_discard_field(raw_discard: Any) -> str | tuple[str, ...]:
    """Normalize discard output from the model.

    The model sometimes emits a single card name and sometimes a list for
    multi-discard effects such as Prepared+. Preserve both forms.
    """
    if isinstance(raw_discard, str):
        return raw_discard.strip()

    if isinstance(raw_discard, list | tuple):
        cleaned = tuple(
            text
            for item in raw_discard
            if (text := str(item).strip())
        )
        if len(cleaned) == 1:
            return cleaned[0]
        return cleaned

    return ""


def _recover_plan_json(text: str) -> dict | None:
    """Try to recover a combat plan from truncated/malformed JSON."""
    # Try to find the plan array
    plan_match = re.search(r'"plan"\s*:\s*(\[[\s\S]*?\])', text)
    if not plan_match:
        return None

    try:
        plan_array = json.loads(plan_match.group(1))
    except json.JSONDecodeError:
        return None

    # Extract end_turn
    end_turn_match = re.search(r'"end_turn"\s*:\s*(true|false)', text, re.IGNORECASE)
    end_turn = True
    if end_turn_match:
        end_turn = end_turn_match.group(1).lower() == "true"

    # Extract reasoning
    reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*)', text)
    reasoning = reasoning_match.group(1) if reasoning_match else "(recovered)"

    return {"plan": plan_array, "end_turn": end_turn, "reasoning": reasoning}
