"""Multi-turn combat conversation manager.

Maintains Anthropic messages format for a single combat encounter.
Each combat produces one CombatConversation that accumulates round-by-round
state, plans, and results as alternating user/assistant messages.

Message flow per round:
  user  (round state)  ->  assistant (plan / tool_use)  ->  user (execution result + enemy turn)

Anthropic API requires strictly alternating user/assistant roles.  If two
user messages would appear in a row (e.g. combat start + first round state),
they are merged into a single user message with a separator.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

from src.brain.card_effects import detect_discard_count
from src.brain.planner import is_draw_card
from src.brain.prompts._card_clarifications import get_inline_warning
from src.brain.prompts._card_name import upgrade_suffix
from src.brain.prompts._deck_fmt import format_deck_section, strip_bbcode
from src.brain.prompts._generated_fmt import format_generated_cards_lines
from src.brain.prompts._intent_fmt import (
    compute_total_incoming,
    format_enemy_intents,
    format_poison_hint,
)
from src.brain.prompts._pile_fmt import format_pile_compact, format_pile_detailed
from src.brain.prompts._target_fmt import describe_target_scope
from src.knowledge.power_lookup import format_power_with_description
from src.mcp_client.upstream_models import RawCombatHandCardPayload
from src.state.game_state import GameState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Card formatting helpers for combat round state
# ---------------------------------------------------------------------------

_RE_TWICE = re.compile(r"\btwice\b|两次", re.IGNORECASE)
_RE_N_TIMES = re.compile(r"(\d+)\s*(?:times|次)")
_TRANSIENT_FUTURE_HAND_PATTERNS = (
    re.compile(r"\bnext turn (?:has|have|holds?|contains?)\b", re.IGNORECASE),
    re.compile(r"\b(?:i|we|you)\s+will\s+have\b.*\bnext turn\b", re.IGNORECASE),
    re.compile(r"\bin hand next turn\b", re.IGNORECASE),
)


# Match a top-level `"reasoning_zh": "..."` field inside a JSON object,
# tolerating escaped quotes. Two-alternative form so we eat at most ONE comma
# (preferring the leading one when both sides have it, to avoid creating
# back-to-back fields with no separator).
_REASONING_ZH_RE = re.compile(
    r',\s*"reasoning_zh"\s*:\s*"(?:[^"\\]|\\.)*"'
    r'|"reasoning_zh"\s*:\s*"(?:[^"\\]|\\.)*"\s*,?',
    re.DOTALL,
)


def _strip_reasoning_zh_from_text(text: str) -> str:
    """Remove `"reasoning_zh": "..."` from any JSON in `text`. Idempotent."""
    if not isinstance(text, str) or "reasoning_zh" not in text:
        return text
    return _REASONING_ZH_RE.sub("", text)


def _strip_reasoning_zh_from_block(block: Any) -> Any:
    """Strip reasoning_zh from a single content block. Pass through non-text blocks."""
    if isinstance(block, dict) and block.get("type") == "text":
        new_text = _strip_reasoning_zh_from_text(block.get("text", ""))
        if new_text == block.get("text"):
            return block
        return {**block, "text": new_text}
    if hasattr(block, "type") and getattr(block, "type", None) == "text":
        cur = getattr(block, "text", "") or ""
        new_text = _strip_reasoning_zh_from_text(cur)
        if new_text == cur:
            return block
        # Fall back to a plain dict; the SDK accepts dicts as content blocks.
        return {"type": "text", "text": new_text}
    return block


def _parse_hits_from_rules(rules_text: str) -> int | None:
    """Parse multi-hit count from rules_text.  Returns None for single-hit."""
    if _RE_TWICE.search(rules_text):
        return 2
    m = _RE_N_TIMES.search(rules_text)
    if m:
        return int(m.group(1))
    return None


def _effective_hits(c: RawCombatHandCardPayload) -> int:
    """Authoritative hit count: DynamicVar hits if >1, else rules_text fallback."""
    if c.hits is not None and c.hits > 1:
        return c.hits
    if c.damage is not None:
        parsed = _parse_hits_from_rules(c.rules_text or "")
        if parsed is not None:
            return parsed
    return c.hits if c.hits is not None else 1


def _format_card_values(c: RawCombatHandCardPayload) -> str:
    """Format structured damage/block values inline, or empty if none."""
    parts: list[str] = []
    if c.damage is not None:
        hits = _effective_hits(c)
        total = (
            c.total_damage
            if (c.total_damage is not None and hits == (c.hits or 1))
            else c.damage * hits
        )
        if hits > 1:
            parts.append(f"{c.damage} dmg x{hits} = {total} total")
        else:
            parts.append(f"{c.damage} dmg")
    if c.block is not None:
        parts.append(f"{c.block} block")
    result = f" [{', '.join(parts)}]" if parts else ""
    if c.replay:
        result += f" [Replay x{c.replay}]"
    return result


def _format_hand_cost(c: RawCombatHandCardPayload) -> str:
    """Format energy cost: 'X' if costs_x, else str(energy_cost)."""
    return "X" if c.costs_x else str(c.energy_cost)




@lru_cache(maxsize=512)
def _lookup_card_type_from_knowledge(card_name: str) -> str:
    """Best-effort lookup for combat hand card type when MCP omits it."""
    try:
        from src.knowledge.knowledge import GameKnowledge

        kb = GameKnowledge.get_instance()
        card = kb.cards.get(card_name)
    except Exception:
        return ""
    if card and card.type:
        return card.type
    return ""


def _build_deck_type_maps(gs: GameState) -> tuple[dict[str, str], dict[str, str]]:
    """Map deck card ids/names to types for combat hand prompt enrichment."""
    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    deck = gs.run.deck if gs.run and gs.run.deck else []
    for card in deck:
        card_type = (getattr(card, "card_type", "") or "").strip()
        if not card_type:
            continue
        card_id = (getattr(card, "card_id", "") or "").strip().lower()
        if card_id:
            by_id.setdefault(card_id, card_type)
        name = (getattr(card, "name", "") or "").rstrip("+").strip().lower()
        if name:
            by_name.setdefault(name, card_type)
    return by_id, by_name


def _format_hand_card_type(
    c: RawCombatHandCardPayload,
    *,
    deck_type_by_id: dict[str, str],
    deck_type_by_name: dict[str, str],
) -> str:
    """Resolve a readable card type for combat hand lines."""
    explicit = (getattr(c, "card_type", "") or "").strip()
    if explicit:
        return explicit
    card_id = (getattr(c, "card_id", "") or "").strip().lower()
    if card_id and card_id in deck_type_by_id:
        return deck_type_by_id[card_id]
    base_name = (c.name or "").rstrip("+").strip().lower()
    if base_name and base_name in deck_type_by_name:
        return deck_type_by_name[base_name]
    return _lookup_card_type_from_knowledge(c.name or "") or "Unknown"


def _creates_potion(c: RawCombatHandCardPayload) -> bool:
    """Heuristic: does this hand card create or procure a potion right now?"""
    name = (c.name or "").strip().lower()
    if name.startswith("alchemize"):
        return True
    text = f"{c.name or ''} {c.rules_text or ''}".lower()
    if "potion" not in text:
        return False
    verbs = ("procure", "create", "obtain", "gain", "add")
    return any(verb in text for verb in verbs)


def _get_hand_card_hints(
    playable: list[RawCombatHandCardPayload],
    energy: int,
) -> list[str]:
    """Generate contextual combat hints based on specific cards in hand.

    Returns a list of hint strings to inject after the Hand section.
    Extensible: add more card-specific checks as needed.
    """
    hints: list[str] = []

    # --- Restlessness: "If your Hand is empty, draw 2 + gain 2 energy" ---
    rest_cards = [c for c in playable if (c.name or "").lower() == "restlessness"]
    if rest_cards:
        other_playable = [c for c in playable if c not in rest_cards]
        other_cost = sum(c.energy_cost for c in other_playable if not c.costs_x)
        if energy >= other_cost:
            hints.append(
                "!! RESTLESSNESS: You have enough energy to play ALL other cards first, "
                "leaving Restlessness as the last card. Playing it with an empty hand "
                "triggers: draw 2 + gain 2 energy (free extra turn). "
                "SEQUENCE: play every other card BEFORE Restlessness."
            )
        else:
            hints.append(
                "!! RESTLESSNESS is in hand. It triggers (draw 2 + gain 2 energy) "
                "only when played as your LAST card (empty hand). "
                "Consider holding it via Retain until you can empty your hand."
            )

    # --- Discard-cost cards: play LAST to reduce/eliminate discard cost ---
    discard_cost_cards = [
        (c, cnt)
        for c in playable
        if (cnt := detect_discard_count(c.rules_text or "")) > 0
    ]
    if discard_cost_cards:
        names = [c.name for c, _ in discard_cost_cards]
        hints.append(
            f"!! DISCARD RULE: {', '.join(names)} — if hand has fewer cards than "
            "the discard cost, you only discard what remains (possibly zero). "
            f"SEQUENCE: play ALL other cards BEFORE {', '.join(names)} so it "
            "discards 0 cards."
        )

    return hints


def _format_powers(powers: list[Any]) -> str:
    """Format a power list with descriptions for prompt output."""
    return ", ".join(
        format_power_with_description(
            power.name,
            power.amount,
            getattr(power, "power_id", ""),
            getattr(power, "description", ""),
        )
        for power in powers
    )


def _format_target_previews(
    card: RawCombatHandCardPayload,
    enemies: list[Any],
    players: list[Any],
) -> list[str]:
    """Per-target damage preview when damage differs by target."""
    if not card.target_previews:
        return []
    if card.target_index_space == "enemies":
        name_map = {e.index: e.name for e in enemies}
    elif card.target_index_space == "players":
        name_map = {i: p.character_name for i, p in enumerate(players)}
    else:
        name_map = {}
    lines: list[str] = []
    for tp in card.target_previews:
        name = name_map.get(tp.target_index, f"target[{tp.target_index}]")
        if tp.hits > 1:
            lines.append(
                f"    vs {name}[{tp.target_index}]: "
                f"{tp.damage} dmg x{tp.hits} = {tp.total_damage} total"
            )
        else:
            lines.append(f"    vs {name}[{tp.target_index}]: {tp.damage} dmg")
    return lines


def _is_transient_future_hand_note(note: str) -> bool:
    """Return True for notes that assert an unstable future hand state."""
    normalized = " ".join(note.strip().split())
    if not normalized:
        return False
    return any(p.search(normalized) for p in _TRANSIENT_FUTURE_HAND_PATTERNS)


# ---------------------------------------------------------------------------
# CombatConversation
# ---------------------------------------------------------------------------

class CombatConversation:
    """Manages multi-turn message history for a single combat encounter.

    Anthropic message format requires alternating user/assistant roles.
    Each round adds:  user (state) -> assistant (plan) -> user (result).

    The conversation is created at combat start and discarded when combat ends.
    ``generate_combat_summary()`` produces a concise string for run-level context.
    """

    def __init__(self, system_prompt: str) -> None:
        self._system: str = system_prompt
        self._messages: list[dict[str, Any]] = []
        self._round_count: int = 0
        self._enemy_key: str = ""
        self._combat_type: str = ""  # "monster" / "elite" / "boss"
        self._hp_at_start: int = 0
        self._max_hp_at_start: int = 0
        self._key_plays: list[str] = []
        self._strategic_notes: list[tuple[int, str]] = []
        self._floors_to_boss: int = 0  # Set externally by loop.py after init
        # ── Compression tracking ──
        self._round_summaries: list[str] = []  # Per-round summary strings
        self._round_msg_starts: list[int] = []  # Message index at start of each round
        self._compressed_through: int = 0  # Number of rounds already compressed

    # -- Properties ---------------------------------------------------------

    @property
    def system_prompt(self) -> str:
        """The system prompt for this combat conversation."""
        return self._system

    @property
    def messages(self) -> list[dict[str, Any]]:
        """Anthropic-format messages list (read-only copy)."""
        return list(self._messages)

    @property
    def llm_messages(self) -> list[dict[str, Any]]:
        """Outbound combat messages for the LLM.

        Always returns exactly ``[combat_start, "ok", latest_user_state]``
        for every model. All prior rounds, stale assistant plans, and
        intermediate re-plan states are dropped — small models (e.g. Qwen)
        misread multi-turn history and misjudge energy/hand state.

        The latest user message MUST be self-contained: ``add_round_state``
        re-injects Strategic Thread, rules, enemy patterns, and potions
        even on re-plan so that the LLM never has to look at prior turns.
        """
        if not self._messages:
            return []

        # Locate the most recent user message (which holds the current
        # round / re-plan state the LLM must respond to).
        last_user_idx = None
        for idx in range(len(self._messages) - 1, -1, -1):
            if self._messages[idx].get("role") == "user":
                last_user_idx = idx
                break

        if last_user_idx is None:
            return []

        # Before any round state exists, combat_start is all we have.
        if last_user_idx == 0:
            return [self._messages[0]]

        return [
            self._messages[0],
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
            self._messages[last_user_idx],
        ]

    @property
    def messages_mut(self) -> list[dict[str, Any]]:
        """Direct reference to internal messages list for in-place mutation.

        Used by V2Engine._agent_loop(mutate_messages=True) so that query
        tool round-trips persist across combat rounds.  Callers MUST
        maintain Anthropic's alternating-role invariant.
        """
        return self._messages

    @property
    def round_count(self) -> int:
        """Number of combat rounds recorded so far."""
        return self._round_count

    @property
    def enemy_key(self) -> str:
        """Identifier for the enemy group (e.g. 'Jaw Worm', 'Louse+Louse')."""
        return self._enemy_key

    @property
    def combat_type(self) -> str:
        """Combat category: 'monster', 'elite', or 'boss'."""
        return self._combat_type

    # -- Internal helpers ---------------------------------------------------

    def _append_user(self, text: str) -> None:
        """Append a user message, merging with previous if also user role."""
        if self._messages and self._messages[-1]["role"] == "user":
            prev = self._messages[-1]
            prev_content = prev["content"]
            if isinstance(prev_content, str):
                prev["content"] = prev_content + "\n\n---\n\n" + text
            elif isinstance(prev_content, list):
                prev_content.append({"type": "text", "text": "\n\n---\n\n" + text})
            else:
                prev["content"] = str(prev_content) + "\n\n---\n\n" + text
        else:
            self._messages.append({"role": "user", "content": text})

    # ──────────────────────────────────────────────────────────────────
    # reasoning_zh is a display-only translation we ask the LLM to produce
    # alongside `reasoning`. We strip it from stored assistant content so
    # subsequent turns of the multi-turn combat conversation see English-only
    # context (per design: input stays English, translation is output-only).
    # ──────────────────────────────────────────────────────────────────

    def _append_assistant(self, content: str | list[dict[str, Any]]) -> None:
        """Append an assistant message with text or content blocks.

        Thinking blocks are stripped before storage.  Anthropic strips
        thinking blocks from context when a non-tool-result user message
        follows, which silently mutates the cached prefix and causes 100%
        cache misses.  By removing them proactively we keep the message
        sequence stable across rounds and preserve prompt cache hits.

        When STS2_DISPLAY_LANGUAGE=zh, the model also emits a `reasoning_zh`
        field inside the <decision> JSON. We strip that field before storing
        so subsequent turns see only English context — Chinese is display-only.
        """
        if isinstance(content, list):
            filtered = [
                b for b in content
                if not (
                    (isinstance(b, dict) and b.get("type") == "thinking")
                    or (hasattr(b, "type") and getattr(b, "type", None) == "thinking")
                )
            ]
            # Strip reasoning_zh from any text block carrying a <decision> JSON.
            filtered = [_strip_reasoning_zh_from_block(b) for b in filtered]
            # Ensure we don't store an empty content list
            if not filtered:
                filtered = [{"type": "text", "text": "(thinking only)"}]
            self._messages.append({"role": "assistant", "content": filtered})
        else:
            self._messages.append(
                {"role": "assistant", "content": _strip_reasoning_zh_from_text(content)},
            )

    def _record_round_summary(
        self,
        actions_taken: list[str],
        gs_after: GameState,
    ) -> None:
        """Build a compact one-line summary for the current round.

        Format: "R1: 3cards HP=52/80 kill:Jaw Worm enemies:Slime(20)"
        """
        round_num = self._round_count
        n_actions = len(actions_taken)
        parts: list[str] = [f"{n_actions}cards"]

        combat = gs_after.combat
        if combat:
            p = combat.player
            parts.append(f"HP={p.current_hp}/{p.max_hp}")

            dead = [e for e in combat.enemies if not e.is_alive]
            if dead:
                parts.append("kill:" + ",".join(e.name for e in dead))

            alive = [e for e in combat.enemies if e.is_alive]
            if alive:
                parts.append(
                    "enemies:" + ",".join(
                        f"{e.name}({e.current_hp})" for e in alive
                    )
                )

        summary = f"R{round_num}: {' '.join(parts)}"
        # Replace last entry if it's the same round (replan/retry), else append.
        # This keeps _round_summaries aligned 1:1 with actual rounds.
        if self._round_summaries and self._round_summaries[-1].startswith(f"R{round_num}:"):
            self._round_summaries[-1] = summary
        else:
            self._round_summaries.append(summary)

    def record_strategic_note(self, round_num: int, note: str) -> None:
        """Record a strategic note from the LLM's combat plan. Keeps last 5."""
        cleaned = note.strip() if note else ""
        if not cleaned:
            return
        if _is_transient_future_hand_note(cleaned):
            logger.debug("Dropping transient future-hand note: %s", cleaned)
            return
        self._strategic_notes.append((round_num, cleaned))
        if len(self._strategic_notes) > 5:
            self._strategic_notes = self._strategic_notes[-5:]

    # -- Compression --------------------------------------------------------

    def compress_history(self, keep_recent: int = 2) -> None:
        """Compress old rounds into a summary, keeping recent rounds intact.

        Preserves msg[0] (combat_start) UNCHANGED for Anthropic prompt cache
        effectiveness.  Old round messages are replaced with a single summary
        user message + a dummy assistant acknowledgement to maintain the
        required alternating user/assistant pattern.

        Args:
            keep_recent: number of recent rounds to preserve in full detail.
        """
        # Use _round_count (actual distinct rounds) instead of
        # len(_round_summaries) which double-counts replans.
        total_rounds = self._round_count
        if total_rounds <= keep_recent:
            return  # Nothing to compress

        # How many rounds to compress (skip already-compressed ones)
        compress_up_to = total_rounds - keep_recent
        if compress_up_to <= self._compressed_through:
            return  # Already compressed this far

        # Build summary text from _round_summaries
        summary_lines = self._round_summaries[:compress_up_to]
        summary_parts: list[str] = []
        if self._strategic_notes:
            summary_parts.insert(0, "Strategic thread: " + " | ".join(
                f"R{r}: {n}" for r, n in self._strategic_notes
                if r <= compress_up_to + keep_recent
            ))
        summary_text = (
            f"## Combat History (Rounds 1-{compress_up_to} compressed)\n"
            + "\n".join(summary_lines)
        )
        if summary_parts:
            summary_text = "\n".join(summary_parts) + "\n" + summary_text

        # Find the message index where the first kept round starts.
        # _round_msg_starts[i] is the msg index at the start of round (i+1).
        # We want to keep rounds from (compress_up_to + 1) onward, which
        # corresponds to _round_msg_starts[compress_up_to] (0-indexed).
        if compress_up_to >= len(self._round_msg_starts):
            # All rounds recorded so far are to be compressed — keep only
            # messages from the very end (there may not be a next round yet)
            return

        keep_from_idx = self._round_msg_starts[compress_up_to]

        # However, the execution_result for round N is added at round N+1 start
        # BEFORE add_round_state records the msg_start index.  So the
        # execution_result message for the last compressed round may sit
        # right before keep_from_idx.  We need to include it in the
        # compressed summary (it's already captured in _round_summaries).
        # If the message right before keep_from_idx is a user execution
        # result that got merged into the round-state user message, it's
        # already part of the message at keep_from_idx (due to _append_user
        # merging).  So keep_from_idx is the correct boundary.

        # Build compressed messages:
        #   [0] combat_start (UNCHANGED — cache anchor)
        #   [1] summary user message
        #   [2] dummy assistant acknowledgement
        #   [3..] recent round messages from keep_from_idx onward
        recent_messages = self._messages[keep_from_idx:]

        # Ensure recent_messages starts with a user message.
        # If the first recent message is an assistant message, we can
        # still produce valid alternation since our dummy assistant
        # message comes right before it — which would break alternation.
        # In that case, skip the dummy assistant and fold the summary
        # into the first user message.
        if recent_messages and recent_messages[0]["role"] == "assistant":
            # Find the assistant plan that belongs to the kept round.
            # This means the user round-state message got merged into
            # the previous execution result.  Shift keep_from_idx back
            # to include that merged user message.
            # Safety: just step back one message to get the user message.
            adjusted_idx = max(1, keep_from_idx - 1)
            if adjusted_idx < keep_from_idx and self._messages[adjusted_idx]["role"] == "user":
                keep_from_idx = adjusted_idx
                recent_messages = self._messages[keep_from_idx:]

        # Collect tool_use IDs from kept assistant messages
        # so we can strip orphaned tool_results from kept user messages
        kept_tool_use_ids: set[str] = set()
        for msg in recent_messages:
            if msg.get("role") == "assistant":
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            kept_tool_use_ids.add(block.get("id", ""))
                        elif hasattr(block, "type") and block.type == "tool_use":
                            kept_tool_use_ids.add(block.id)

        # Strip orphaned tool_result blocks from kept user messages
        cleaned_recent: list[dict[str, Any]] = []
        for msg in recent_messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    cleaned_blocks = [
                        b for b in content
                        if not (isinstance(b, dict) and b.get("type") == "tool_result"
                                and b.get("tool_use_id", "") not in kept_tool_use_ids)
                    ]
                    if cleaned_blocks:
                        cleaned_recent.append({**msg, "content": cleaned_blocks})
                    else:
                        # All blocks were orphaned tool_results — convert to text
                        cleaned_recent.append(
                            {
                                **msg,
                                "content": "[tool results from compressed rounds]",
                            }
                        )
                else:
                    cleaned_recent.append(msg)
            else:
                cleaned_recent.append(msg)

        new_messages: list[dict[str, Any]] = [
            self._messages[0],  # combat_start (UNCHANGED)
            {"role": "user", "content": summary_text},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "text",
                        "text": "ok",
                    }
                ],
            },
        ]
        new_messages.extend(cleaned_recent)

        old_count = len(self._messages)
        self._messages = new_messages

        # Update round_msg_starts for kept rounds:
        # The first kept round now starts at index 3 (after combat_start,
        # summary, and dummy assistant).
        offset = 3 - keep_from_idx
        new_starts: list[int] = []
        for i, start_idx in enumerate(self._round_msg_starts):
            if i < compress_up_to:
                # Compressed rounds — no longer have individual msg indices
                new_starts.append(-1)
            else:
                new_starts.append(start_idx + offset)
        self._round_msg_starts = new_starts

        self._compressed_through = compress_up_to

        logger.info(
            "Compressed combat history: rounds 1-%d summarized, "
            "messages %d -> %d, keeping last %d rounds",
            compress_up_to, old_count, len(self._messages), keep_recent,
        )

    # -- Public API ---------------------------------------------------------

    def add_combat_start(
        self,
        gs: GameState,
        strategic_context: str = "",
        potion_strategy: str = "",
        strategic_thread: str = "",
        combat_type: str = "",
        card_notes: dict[str, str] | None = None,
    ) -> None:
        """Add initial combat state as the first user message.

        Includes: enemy info, player HP, deck size, relics,
        and optional strategic context (skills, boss strategy).

        Args:
            combat_type: Authoritative combat type from agent loop's cached map
                node metadata. Falls back to gs.state_type if empty.
            card_notes: Optional per-card notes from CardMemory for deck cards
                (key = card name, value = note text).
        """
        combat = gs.combat
        if not combat:
            return

        p = combat.player
        self._hp_at_start = p.current_hp
        self._max_hp_at_start = p.max_hp

        # Determine enemy key and combat type
        alive = [e for e in combat.enemies if e.is_alive]
        self._enemy_key = " + ".join(e.name for e in alive) if alive else "unknown"

        # Use authoritative combat_type from agent loop (cached map node metadata).
        # Only fall back to gs.state_type if not provided.
        if combat_type:
            self._combat_type = combat_type
        else:
            native_combat_type = getattr(gs, "combat_type", "")
            if (
                isinstance(native_combat_type, str)
                and native_combat_type in ("monster", "elite", "boss")
            ):
                self._combat_type = native_combat_type
            else:
                st = gs.state_type
                if st in ("boss", "elite"):
                    self._combat_type = st
                else:
                    self._combat_type = "monster"

        boss_stage = getattr(gs, "boss_stage", None)
        if not isinstance(boss_stage, str):
            boss_stage = None

        lines: list[str] = []
        lines.append("## Combat Start")
        lines.append(f"Encounter type: {self._combat_type}")
        if boss_stage:
            lines.append(f"Boss stage: {boss_stage}")
        if gs.run_info:
            lines.append(f"Act: {gs.act} | Floor: {gs.floor}")
        lines.append(f"Enemies: {self._enemy_key}")

        for e in alive:
            powers_str = ""
            if e.powers:
                powers_str = " | powers: " + _format_powers(e.powers)
            lines.append(
                f"- {e.name} [index={e.index}]: HP {e.current_hp}/{e.max_hp}"
                f", Block {e.block}{powers_str}"
            )

        lines.append("")
        lines.append(
            f"Player HP: {p.current_hp}/{p.max_hp} | Block: {p.block} "
            f"| Energy: {p.energy}/{gs.run_info.max_energy if gs.run_info else '?'}"
        )
        stars_str = f" | Stars: {p.stars}" if p.stars else ""
        if stars_str:
            lines[-1] += stars_str

        # Regent-only Sovereign Blade / Forge state block (empty for other characters
        # and for Regent runs without any Forge presence).
        try:
            from src.brain.prompts._forge_fmt import format_forge_state
            forge_lines = format_forge_state(gs)
        except Exception:
            forge_lines = []
        if forge_lines:
            lines.extend(forge_lines)

        if p.powers:
            powers_str = _format_powers(p.powers)
            lines.append(f"Player buffs/debuffs: {powers_str}")

        # Deck overview
        deck_lines = format_deck_section(gs.deck if gs.deck else None)
        lines.extend(deck_lines)

        # Relics
        if gs.relics:
            lines.append("")
            lines.append(f"## Relics ({len(gs.relics)})")
            for r in gs.relics:
                if r.description:
                    lines.append(f"- {strip_bbcode(r.name)}: {strip_bbcode(r.description)[:200]}")
                else:
                    lines.append(f"- {strip_bbcode(r.name)}")

        # Run-level strategic thread (deck-building rationale)
        if strategic_thread:
            lines.append("")
            lines.append("## Strategic Thread")
            lines.append(
                "*Your deck-building decisions so far — fight with this "
                "deck's strengths.*\n"
            )
            lines.append(strategic_thread)

        # Strategic context (skills, boss strategy)
        if strategic_context:
            lines.append("")
            lines.append(strategic_context)

        # Potion strategy (timing classification)
        if potion_strategy:
            lines.append("")
            lines.append(potion_strategy)

        # Per-card notes for deck cards (from CardMemory experience)
        if card_notes:
            lines.append("")
            lines.append("## Card Notes (from experience)")
            for card_name, note_text in card_notes.items():
                lines.append(f"- {card_name}: {note_text}")

        # Combat rules (moved from system prompt for token efficiency)
        lines.append("")
        lines.append("## Combat Rules")
        lines.append("- Only play cards marked [PLAYABLE]. Cards marked [UNPLAYABLE] will fail.")
        lines.append("- Cards show `cost=N` — you need at least N energy remaining to play them.")
        lines.append(
            "- In `plan`, action order is execution order. Earlier plays change your remaining "
            "energy, hand composition, and later card costs."
        )
        lines.append("- Include potions in your combat plan when useful (they don't cost energy).")
        lines.append(
            "- **Discard effects**: If a card requires discarding "
            '(e.g. Survivor), specify with the `"discard"` field. Example: '
            '`{"type": "card", "card": "Survivor", "target_index": -1, '
            '"discard": "Defend"}`'
        )
        lines.append(
            "- **Target priority**: Kill enemies that scale "
            "(Strength-stacking, buffing). Against non-scaling enemies, "
            "block every attack to minimize HP loss."
        )

        self._append_user("\n".join(lines))

        # Insert a dummy assistant turn so that add_round_state() for round 1
        # goes into a SEPARATE message instead of merging into msg[0].
        # This keeps msg[0] static (deck/relics/skills/rules) and lets
        # round 1 data (hand/enemies/effects) be compressed like all other
        # rounds.  Saves ~1,750 tokens per call in long fights.
        self._messages.append({
            "role": "assistant",
            "content": [{"type": "text", "text": "ok"}],
        })

    def add_round_state(
        self,
        gs: GameState,
        *,
        extra_context: str = "",
        replan_context: str = "",
        enemy_episodes: list | None = None,
        card_memory_store: Any | None = None,
        deck_card_names: set[str] | None = None,
    ) -> None:
        """Add new round state as a user message.

        Includes: hand cards (with playable status, damage/block values),
        energy, enemy intents, player HP/block, usable potions.
        Includes combat state data with tactical analysis, keyword glossary,
        and energy budget.

        Args:
            gs: Current game state.
            extra_context: Optional text (e.g. computed insights) prepended
                to the round state within the same user message.
            replan_context: Optional text describing the original plan and
                trigger for re-planning (injected before enemy/hand sections).
        """
        combat = gs.combat
        if not combat:
            return

        actual_round = max(1, gs.combat_round)

        # Detect re-plan BEFORE updating _round_count — a re-plan is a
        # second+ call for the same round (draw-card split, validation retry).
        # Re-plan state is now fully self-contained: `llm_messages` exposes
        # only [combat_start, "ok", this message], so all dynamic sections
        # (Strategic Thread, rules, patterns, potions) are re-injected here.
        is_replan = (self._round_count > 0 and actual_round <= self._round_count)

        # Only advance round tracking when the combat round actually changes.
        # Re-plan prompts within the same turn should not inflate round numbers.
        if actual_round > self._round_count:
            # Compress old rounds before adding the new one (keep last 1-2 intact)
            if self._round_count > 3:
                self.compress_history(keep_recent=1)

            self._round_count = actual_round
            # Track where this round's messages start (before _append_user may merge)
            self._round_msg_starts.append(len(self._messages))

        p = combat.player
        hand = combat.hand
        alive_enemies = [e for e in combat.enemies if e.is_alive]

        stars_str = f" | Stars: {p.stars}" if p.stars else ""
        heading = f"## Round {gs.combat_round} Re-plan" if is_replan else f"## Round {gs.combat_round} State"
        lines: list[str] = [
            heading,
            f"Energy: {p.energy}/{gs.run_info.max_energy if gs.run_info else '?'}"
            f"{stars_str} | HP: {p.current_hp}/{p.max_hp} | Block: {p.block}",
        ]

        # Regent-only Sovereign Blade / Forge state block (empty for other
        # characters and for Regent runs without any Forge presence).
        try:
            from src.brain.prompts._forge_fmt import format_forge_state
            forge_lines = format_forge_state(gs)
        except Exception:
            forge_lines = []
        if forge_lines:
            lines.extend(forge_lines)

        # Re-plan context (injected before enemy/hand sections)
        if replan_context:
            lines.append("")
            lines.append("## Re-plan Context")
            lines.append(replan_context)
            lines.append("")

        # Player powers
        if p.powers:
            powers_str = _format_powers(p.powers)
            lines.append(f"Player buffs/debuffs: {powers_str}")

        # Enemies
        lines.append("")
        lines.append("## Enemies")
        player_powers = p.powers if p.powers else None
        _invincible_hp_threshold = 1_000_000
        has_invincible = any(
            (e.max_hp or 0) >= _invincible_hp_threshold for e in alive_enemies
        )
        for e in alive_enemies:
            intent_str = format_enemy_intents(e)
            poison_hint = format_poison_hint(e.powers, e.current_hp, player_powers)
            powers_str = ""
            if e.powers:
                powers_str = " | powers: " + _format_powers(e.powers)
            invincible_tag = " [INVINCIBLE]" if (e.max_hp or 0) >= _invincible_hp_threshold else ""
            lines.append(
                f"- {e.name} [index={e.index}]: HP {e.current_hp}/{e.max_hp}{invincible_tag}{poison_hint}, "
                f"Block {e.block}, Intent: {intent_str}{powers_str}"
            )

        # Tactical snapshot
        total_incoming = compute_total_incoming(alive_enemies)
        effective_incoming = max(0, total_incoming - p.block)
        lines.append("")
        lines.append(
            f"Incoming damage: {total_incoming} "
            f"(after block: {effective_incoming}) | Your HP: {p.current_hp}"
        )

        if has_invincible:
            lines.append(
                "!! INVINCIBLE ENEMY PHASE -- Skip ALL attack cards. "
                "Do not play exhaust cards — let them discard at end of turn instead. "
                "Use only: sustained potions, Powers, and end turn early if no Powers available."
            )
        elif effective_incoming >= p.current_hp:
            lines.append("!! LETHAL THREAT -- you MUST block or kill to survive!")
        elif effective_incoming > 0:
            pct = effective_incoming / p.current_hp if p.current_hp > 0 else 1.0
            if pct >= 0.4:
                lines.append(
                    f"!! Incoming {effective_incoming} = {pct:.0%} of HP -- "
                    "prioritize defense unless you can kill."
                )

        # Strategic thread from previous rounds (always shown — LLM only
        # sees [combat_start, "ok", this state], so prior-round notes must
        # be re-injected on every call, including re-plans).
        if self._strategic_notes:
            lines.append("")
            lines.append("## Strategic Thread")
            for rnd, note in self._strategic_notes:
                lines.append(f"R{rnd}: {note}")

        # Relic counters (only relics with an active counter, e.g. Nunchaku, BookOfFiveRings)
        counter_relics = [r for r in (gs.relics or []) if getattr(r, "counter", None) is not None]
        if counter_relics:
            lines.append("")
            lines.append("## Relic Counters")
            for r in counter_relics:
                desc = strip_bbcode(r.description or "").strip() if r.description else ""
                desc_part = f" — {desc}" if desc else ""
                lines.append(f"- {r.name}: {r.counter}{desc_part}")

        # Hand
        playable = [c for c in hand if c.playable]
        unplayable = [c for c in hand if not c.playable]
        deck_type_by_id, deck_type_by_name = _build_deck_type_maps(gs)
        # Section-reorder: track offsets so we can move the Hand+UNPLAYABLE
        # block to the tail (just before Energy budget / CRITICAL RULES).
        # Final order: Potions → Piles → Key Effects → Hand → UNPLAYABLE.
        # The keyword glossary (Key Effects) bridges Piles' card text above
        # and Hand's card text below — both reference combat keywords.
        _section_block_start = len(lines)
        _section_hand_start = len(lines)
        lines.append("")
        lines.append(f"## Hand ({len(playable)} playable / {len(hand)} total)")
        if len(hand) >= 8:
            lines.append(
                f"!! HAND SIZE: {len(hand)}/10. Draw/add-to-hand effects cannot exceed "
                "10 cards; at 10 cards, playing a generator usually opens only one slot "
                "before its generated cards try to enter your hand."
            )

        for c in playable:
            target = (
                f" -> targets {describe_target_scope(c.target_index_space, c.target_type)}"
                if c.requires_target
                else ""
            )
            star = f" \u2605{c.star_cost}" if c.star_cost else ""
            upgraded = upgrade_suffix(c)
            cost_str = _format_hand_cost(c)
            vals = _format_card_values(c)
            draw_flag = " DRAWS" if is_draw_card(c.rules_text or "") else ""
            card_type = _format_hand_card_type(
                c,
                deck_type_by_id=deck_type_by_id,
                deck_type_by_name=deck_type_by_name,
            )
            inline_warn = get_inline_warning(c.name)
            warn_suffix = f" {inline_warn}" if inline_warn else ""
            lines.append(
                f"- {c.name}{upgraded} ({card_type}, cost={cost_str}{star}){vals}"
                f"{target}{draw_flag}: {strip_bbcode(c.rules_text) if c.rules_text else ''}"
                f"{warn_suffix}"
            )
            for preview_line in _format_target_previews(
                c, alive_enemies, combat.players
            ):
                lines.append(preview_line)
            lines.extend(format_generated_cards_lines(getattr(c, "generated_cards", []) or []))

        # Discard reminder — prompt LLM to fill "discard" field for cards that trigger discards
        discard_cards = [
            c.name for c in playable
            if detect_discard_count(getattr(c, 'rules_text', '') or '') > 0
        ]
        if discard_cards:
            lines.append(
                f'!! DISCARD: {", ".join(discard_cards)} will require discarding.'
                ' Fill the "discard" field in your plan.'
                ' Use a list when the card discards multiple cards.'
            )
            # Ethereal Status/Curse cards in hand auto-exhaust at end of turn
            # (permanently gone this combat). Discarding them sends them to the
            # discard pile, which gets reshuffled into the draw pile — strictly
            # worse. Mirrors the hand_select fast-tier hint at hand_select.py.
            ethereal_junk = [
                c.name for c in hand
                if (c.card_type or "").lower() in ("status", "curse")
                and "ethereal" in (c.rules_text or "").lower()
            ]
            if ethereal_junk:
                lines.append(
                    f'!! DO NOT DISCARD {", ".join(ethereal_junk)}: Ethereal'
                    ' Status/Curse cards with no harmful held effect auto-exhaust'
                    ' at end of turn (permanently gone this combat). Discarding'
                    ' them reshuffles them into the draw pile — strictly worse.'
                    ' Pick a different card to satisfy the discard cost.'
                )

        # Card-specific combat hints (Restlessness sequencing, Knife Trap, etc.)
        card_hints = _get_hand_card_hints(playable, p.energy)
        if card_hints:
            for hint in card_hints:
                lines.append(hint)

        # Per-card notes for temporary cards only (not in deck)
        if card_memory_store and deck_card_names is not None:
            from src.memory.models_v2 import normalize_character
            char = normalize_character(
                (gs.run_info.character_name if gs.run_info and gs.run_info.character_name else "") or ""
            )
            injected: set[str] = set()
            for c in hand:
                base_name = (c.name or "").rstrip("+")
                if base_name in deck_card_names:
                    continue  # Already injected at COMBAT_START
                if base_name.lower() in injected:
                    continue
                mem = card_memory_store.get(char, base_name)
                if mem and mem.note:
                    injected.add(base_name.lower())
                    lines.append(f"!! {c.name}: {mem.note}")

        # Keyword glossary — include keywords from hand cards + enemy/player powers
        import re as _re
        from src.brain.prompts._keyword_fmt import KW_GLOSSARY, _dll_mechanics
        _KW_GLOSSARY = KW_GLOSSARY
        # Scan hand cards text
        hand_text = " ".join(
            ((c.rules_text or "") + " " + (c.name or "")).lower() for c in hand
        )
        hand_text_orig = " ".join(
            ((c.rules_text or "") + " " + (c.name or "")) for c in hand
        )
        # Also scan enemy and player powers for status effects
        powers_text = ""
        powers_text_orig = ""
        for e in alive_enemies:
            for pw in (e.powers or []):
                powers_text += " " + (pw.name or "").lower()
                powers_text_orig += " " + (pw.name or "")
        if gs.combat and gs.combat.player.powers:
            for pw in gs.combat.player.powers:
                powers_text += " " + (pw.name or "").lower()
                powers_text_orig += " " + (pw.name or "")
        # Scan usable potions too — a Regen Potion in the slot lists "Gain 5
        # Regen" in its description, and the glossary must explain Regen even
        # if the buff isn't active yet. Only `can_use` potions contribute, so
        # locked slots don't pollute the match set.
        potions_text = ""
        potions_text_orig = ""
        for pot in (gs.potions or []):
            if not getattr(pot, "can_use", False):
                continue
            name = pot.name or ""
            desc = pot.description or ""
            potions_text += " " + name.lower() + " " + desc.lower()
            potions_text_orig += " " + name + " " + desc
        search_text = hand_text + " " + powers_text + " " + potions_text
        search_text_orig = (
            hand_text_orig + " " + powers_text_orig + " " + potions_text_orig
        )
        # llm_messages only sends the latest user message to the LLM, so the
        # glossary must be fully present every render (including re-plans).
        new_effects: list[tuple[str, str]] = []
        for kw, desc in _KW_GLOSSARY.items():
            if kw in search_text:
                new_effects.append((kw, desc))
        # Tier 2: DLL-extracted fallback (only for mechanics not in KW_GLOSSARY).
        # Word-boundary + title-case match avoids false positives
        # (e.g. "bound" in "rebound"). Matches format_keyword_glossary in _keyword_fmt.
        for kw, desc in _dll_mechanics.items():
            if kw in _KW_GLOSSARY:
                continue
            title = " ".join(w.capitalize() for w in kw.split())
            if _re.search(rf"\b{_re.escape(title)}\b", search_text_orig):
                new_effects.append((kw, desc))
        _section_key_effects_start = len(lines)
        if new_effects:
            lines.append("")
            lines.append("## Key Effects (active this combat)")
            for kw, desc in new_effects:
                lines.append(f"- {desc}")

        _section_unplayable_start = len(lines)
        if unplayable:
            lines.append("")
            lines.append("UNPLAYABLE cards (cannot use this turn):")
            for c in unplayable:
                cost_str = _format_hand_cost(c)
                rules = f": {c.rules_text}" if c.rules_text else ""
                lines.append(
                    f"- {c.name} (cost={cost_str}, "
                    f"{c.unplayable_reason or 'insufficient energy/stars'}){rules}"
                )

        _section_piles_start = len(lines)
        # Piles — only inject when hand/potions reference them
        # Draw pile: if any card/potion draws cards
        # Discard pile: if any card interacts with discard pile
        # Exhaust pile: if any card interacts with exhaust pile
        av = gs.agent_view
        if av and av.combat:
            _draw_kw = {"draw", "抽", "add to your hand", "put into your hand"}
            _discard_kw = {"discard pile", "弃牌堆", "from discard", "shuffle your discard"}
            _exhaust_kw = {"exhaust pile", "消耗堆", "from exhaust", "exhausted card"}
            scan = hand_text  # already built above (all hand cards' rules_text + names)
            # Also scan potions
            for pot in (gs.potions or []):
                if pot.can_use and pot.description:
                    scan += " " + pot.description.lower()

            show_draw = any(kw in scan for kw in _draw_kw)
            show_discard = any(kw in scan for kw in _discard_kw)
            show_exhaust = any(kw in scan for kw in _exhaust_kw)

            pile_lines: list[str] = []
            # Always show pile SIZES (1 line, cheap) for deck tracking
            draw_n = len(av.combat.draw) if av.combat.draw else 0
            disc_n = len(av.combat.discard) if av.combat.discard else 0
            exh_n = len(av.combat.exhaust) if av.combat.exhaust else 0
            pile_lines.append(f"Piles: Draw {draw_n} | Discard {disc_n} | Exhaust {exh_n}")
            # Show full contents only when hand/potions interact with that pile
            if show_draw and av.combat.draw:
                pile_lines.extend(
                    format_pile_detailed(av.combat.draw, "Draw")
                )
            if show_discard and av.combat.discard:
                pile_lines.append(
                    format_pile_compact(av.combat.discard, "Discard")
                )
            if show_exhaust and av.combat.exhaust:
                pile_lines.append(
                    format_pile_compact(av.combat.exhaust, "Exhaust")
                )
            lines.append("")
            lines.append("## Piles")
            lines.extend(pile_lines)

        _section_potions_start = len(lines)
        # Potions — always included so re-plan state is self-contained.
        self._format_potions(gs, lines, playable, is_replan=False)
        _section_block_end = len(lines)

        # Reorder block: original order is
        #   Hand, Key Effects, UNPLAYABLE, Piles, Potions
        # Target order (Plan B — keep Glossary/Key Effects bridging cards
        # above and below): Potions, Piles, Key Effects, Hand, UNPLAYABLE.
        _hand_block = lines[_section_hand_start:_section_key_effects_start]
        _key_effects_block = lines[_section_key_effects_start:_section_unplayable_start]
        _unplayable_block = lines[_section_unplayable_start:_section_piles_start]
        _piles_block = lines[_section_piles_start:_section_potions_start]
        _potions_block = lines[_section_potions_start:_section_block_end]
        lines[_section_block_start:_section_block_end] = (
            _potions_block + _piles_block + _key_effects_block
            + _hand_block + _unplayable_block
        )

        # Energy budget
        x_cost_cards = [c for c in playable if c.costs_x]
        fixed_cost_cards = [c for c in playable if not c.costs_x]
        total_cost = sum(c.energy_cost for c in fixed_cost_cards)
        x_note = f" (+{len(x_cost_cards)} X-cost)" if x_cost_cards else ""
        lines.append("")
        lines.append(
            f"Energy budget: {p.energy}E available, "
            f"fixed-cost total: {total_cost}E{x_note}"
        )
        if total_cost <= p.energy and not x_cost_cards:
            lines.append("You can play ALL playable cards this turn!")

        # Critical combat rules reminder (always shown — re-plan state is
        # self-contained; LLM does not see the round's original state).
        lines.append("")
        lines.append("CRITICAL RULES:")
        lines.append(
            "- Energy RESETS to full each turn. Unspent energy is WASTED."
        )
        lines.append(
            "- Hand cards are DISCARDED at end of turn. Unplayed cards are WASTED."
        )
        lines.append(
            "- Cards DRAWN or CREATED this turn enter your CURRENT hand now. "
            "If left unplayed, they are discarded/exhausted/retained by their "
            "own rules at the end of THIS turn — they do NOT wait for next turn."
        )
        lines.append(
            f"- Hand size limit is 10 cards. Current hand is {len(hand)}/10; "
            "draw/add-to-hand effects beyond 10 are lost or fail to enter hand."
        )
        lines.append(
            "- Current Block only matters for the upcoming enemy turn. It does "
            "NOT carry into your next turn unless a visible effect explicitly "
            "preserves Block."
        )
        lines.append(
            "- Draw pile order is only a CONDITIONAL forecast. It predicts later "
            "draws only if you stop drawing right now; any draw/add-to-hand "
            "effect changes that forecast immediately."
        )
        lines.append(
            "- The `plan` array is executed top-to-bottom. If a card should be played last "
            "(for example an X-cost card like Malaise), list it last."
        )

        # Upcoming enemy patterns (round 2+, always shown — not in combat_start).
        if enemy_episodes and actual_round >= 2:
            from src.brain.enemy_pattern_injector import format_upcoming_patterns
            upcoming = format_upcoming_patterns(enemy_episodes, actual_round)
            if upcoming:
                lines.append("")
                lines.append(upcoming)

        body = "\n".join(lines)
        if extra_context:
            body = extra_context + "\n\n" + body
        self._append_user(body)

    def _format_potions(
        self,
        gs,
        lines: list[str],
        playable: list,
        is_replan: bool = False,
    ) -> None:
        """Append potion section to `lines` (mutates). No-op if no potions.

        The `is_replan` argument is retained for backward compatibility but
        no longer skips the section — re-plan state is now self-contained.
        """
        potions = gs.potions
        if not potions:
            return
        usable = [pot for pot in potions if pot.can_use]
        filled_slots = sum(1 for pot in potions if pot.occupied)
        total_slots = gs.potion_slots
        open_slots = gs.open_potion_slots
        potion_creators = [c.name for c in playable if _creates_potion(c)]
        if not (total_slots > 0 or usable):
            return
        from src.knowledge.potion_classifier import classify_potion, format_potion_tag
        lines.append("")
        lines.append("## Usable Potions" if usable else "## Potions")
        slot_note = " FULL" if open_slots <= 0 else f" ({open_slots} open)"
        lines.append(f"Potion slots: {filled_slots}/{total_slots}{slot_note}")
        if open_slots <= 0 and potion_creators:
            names = ", ".join(potion_creators)
            lines.append(
                "!! POTION SLOTS FULL: "
                f"{names} will not add a potion unless you free a slot first."
            )
        if open_slots <= 0:
            lines.append(
                "Slots FULL — spend a lower-value potion if it helps this "
                "round; don't waste just to free a slot."
            )
        for pot in usable:
            target_hint = (
                " -> targets "
                f"{describe_target_scope(pot.target_index_space, pot.target_type)} "
                "(target_index required)"
                if pot.requires_target
                else ""
            )
            pot_desc = strip_bbcode(pot.description) if pot.description else ""
            profile = classify_potion(pot.name or "", pot.description or "")
            timing_tag = format_potion_tag(
                profile.timing, self._combat_type, self._floors_to_boss
            )
            lines.append(
                f"- [potion_index={pot.index}] {pot.name} {timing_tag}"
                f"{target_hint}: {pot_desc}"
            )

    def add_assistant_plan(self, content_blocks: list[dict[str, Any]]) -> None:
        """Record the LLM's response (may include text and tool_use blocks).

        content_blocks: raw Anthropic response.content list.
        """
        self._append_assistant(content_blocks)

    def add_validation_error(self, error_msg: str) -> None:
        """Add a plan validation error so the LLM can correct its plan.

        Called when pre-execution validation detects hallucinated cards
        (e.g. plan uses 3x Strike but hand only has 2x).
        """
        self._append_user(
            f"## Plan Validation Error\n{error_msg}\n\n"
            "Generate a corrected plan now."
        )

    def add_execution_result(
        self,
        actions_taken: list[str],
        gs_after: GameState,
    ) -> None:
        """Record what happened when the plan was executed.

        actions_taken: human-readable strings like
            "Bash -> Louse[0] (8 dmg, Vulnerable applied)"
        gs_after: game state after execution (for HP/block/enemy status).

        This no longer appends an execution transcript into prompt history.
        Execution details are retained only in structured round summaries
        and key-play tracking; follow-up prompts should rely on fresh state
        plus strategic notes instead of verbose execution recaps.
        """
        for a in actions_taken:
            if len(self._key_plays) < 10:
                self._key_plays.append(a)

        # Build per-round summary for compression (from structured data, not messages)
        self._record_round_summary(actions_taken, gs_after)

    def add_round_result(self, gs: GameState, hp_before: int) -> None:
        """Add enemy turn results as a user message.

        Summarizes what happened during the enemy phase:
        damage taken, block consumed, status effects applied.

        Args:
            gs: game state after enemy turn
            hp_before: player HP before enemy turn started
        """
        combat = gs.combat
        if not combat:
            return

        p = combat.player
        hp_delta = hp_before - p.current_hp
        alive = [e for e in combat.enemies if e.is_alive]

        lines: list[str] = ["## Enemy Turn Result"]

        if hp_delta > 0:
            lines.append(f"You took {hp_delta} damage. HP: {p.current_hp}/{p.max_hp}")
        elif hp_delta == 0:
            lines.append(f"No damage taken. HP: {p.current_hp}/{p.max_hp}")
        else:
            # Healed (rare, but possible via enemy effects)
            lines.append(
                f"HP changed by +{abs(hp_delta)}. HP: {p.current_hp}/{p.max_hp}"
            )

        lines.append(f"Block: {p.block}")

        if p.powers:
            powers_str = _format_powers(p.powers)
            lines.append(f"Status effects: {powers_str}")
        else:
            lines.append("Status effects: none")

        if alive:
            lines.append("Remaining enemies: " + ", ".join(
                f"{e.name}({e.current_hp}/{e.max_hp})" for e in alive
            ))
        else:
            lines.append("All enemies defeated -- combat ending.")

        self._append_user("\n".join(lines))

    def generate_combat_summary(
        self,
        final_hp: int | None = None,
        final_max_hp: int | None = None,
    ) -> str:
        """At combat end, produce a brief summary for run-level context.

        Returns a string like:
        "Fought Jaw Worm (monster). 4 rounds. HP: 72/80 -> 58/80 (-14).
        Key plays: Bash, Defend, Strike x2. Outcome: won."

        Args:
            final_hp: Player HP after combat. Preferred over message parsing.
            final_max_hp: Player max HP after combat.
        """
        outcome = "won"

        # Use caller-provided HP (reliable) or fall back to message parsing
        if final_hp is not None:
            if final_max_hp is None:
                final_max_hp = self._max_hp_at_start
        else:
            final_hp = self._hp_at_start
            final_max_hp = self._max_hp_at_start
            # Walk messages backwards to find last HP mention
            for msg in reversed(self._messages):
                content = msg.get("content", "")
                if isinstance(content, str) and "HP:" in content:
                    hp_match = _extract_hp(content)
                    if hp_match is not None:
                        final_hp, final_max_hp = hp_match
                        break
                elif isinstance(content, list):
                    for block in reversed(content):
                        if isinstance(block, dict):
                            text = block.get("text", block.get("content", ""))
                            if isinstance(text, str) and "HP:" in text:
                                hp_match = _extract_hp(text)
                                if hp_match is not None:
                                    final_hp, final_max_hp = hp_match
                                    break

        if final_hp <= 0:
            outcome = "lost"

        hp_delta = final_hp - self._hp_at_start
        hp_delta_str = f"+{hp_delta}" if hp_delta >= 0 else str(hp_delta)

        # Deduplicate key plays for brevity
        play_summary = _summarize_plays(self._key_plays) if self._key_plays else "none"

        parts = [
            f"Fought {self._enemy_key} ({self._combat_type})",
            f"{self._round_count} rounds",
            f"HP: {self._hp_at_start}/{self._max_hp_at_start} -> "
            f"{final_hp}/{final_max_hp} ({hp_delta_str})",
            f"Key plays: {play_summary}",
            f"Outcome: {outcome}",
        ]
        return ". ".join(parts) + "."


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _extract_hp(text: str) -> tuple[int, int] | None:
    """Extract (current_hp, max_hp) from text containing 'HP: N/M'."""
    import re

    match = re.search(r"HP:\s*(\d+)/(\d+)", text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def _summarize_plays(plays: list[str]) -> str:
    """Summarize a list of action strings into a compact form.

    Groups repeated card names: ["Strike", "Strike", "Bash"] -> "Strike x2, Bash"
    Extracts just the card/potion name from action strings like
    "Bash -> Louse[0] (8 dmg)" -> "Bash".
    """
    import re
    from collections import Counter

    names: list[str] = []
    for play in plays:
        # Extract the first word/name before " ->" or " ("
        match = re.match(r"^([A-Za-z][A-Za-z0-9 ']*)", play)
        if match:
            names.append(match.group(1).strip())
        else:
            names.append(play[:20])

    counts = Counter(names)
    parts: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        count = counts[name]
        if count > 1:
            parts.append(f"{name} x{count}")
        else:
            parts.append(name)
    return ", ".join(parts)
