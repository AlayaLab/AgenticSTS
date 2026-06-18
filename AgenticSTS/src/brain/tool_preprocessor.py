"""ToolPreprocessor: run state-derived dynamic tools before LLM calls.

Binds parameters from GameState, executes applicable tools locally, and
returns results as hint text for prompt injection. This is the gameplay
consumption path for agent-authored dynamic tools.

Flow:
  1. Filter to state_derived tools only
  2. Check state_type applicability (from description or APPLICABLE_STATES)
  3. Auto-bind parameters from GameState
  4. Execute each tool in sandbox (with timeout)
  5. Format results as "## Computed Insights" section
  6. Record usage telemetry for evolution agent feedback

Design decisions:
  - Only state_derived tools run here (plan_evaluator tools need P2)
  - Parameter binding failures silently skip the tool (graceful degradation)
  - Max 5 tools per call, 500ms total budget
  - Results formatted as compact hint text (~200 tokens)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.brain.dynamic_tools import (
    AUTO_BINDABLE,
    DynamicToolRegistry,
    classify_tool_runtime_mode,
)
from src.state.game_state import GameState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolHint:
    """Result of a single preprocessed tool execution."""

    tool_name: str
    result: Any
    latency_ms: float


@dataclass
class ToolUsageRecord:
    """Telemetry record for a single tool execution."""

    tool_name: str
    state_type: str
    success: bool
    latency_ms: float
    timestamp: float = field(default_factory=time.time)
    error: str = ""


# ── State type inference from description ──────────────────────

_COMBAT_KEYWORDS = frozenset({
    "block", "attack", "damage", "hp", "combat", "turn", "enemy",
    "lethal", "survive", "incoming", "defense", "offensive",
    "poison", "shiv", "strength", "weak", "frail", "energy",
    "vulnerable", "dexterity", "buffer", "plan",
})

_DECK_KEYWORDS = frozenset({
    "deck", "card", "removal", "bloat", "archetype", "strike",
})

_MAP_KEYWORDS = frozenset({
    "map", "route", "rest", "heal", "upgrade", "floor", "event",
    "shop", "gold",
})


def _infer_applicable_states(schema: dict) -> set[str]:
    """Infer which state types a tool is applicable to from its description.

    Returns an empty set if no clear match — callers should skip the tool
    rather than running it everywhere. This surfaces bad metadata early
    instead of creating noisy hints in unrelated states.
    """
    desc = schema.get("description", "").lower()
    name = schema.get("name", "").lower()
    text = f"{desc} {name}"

    states: set[str] = set()

    combat_score = sum(1 for kw in _COMBAT_KEYWORDS if kw in text)
    deck_score = sum(1 for kw in _DECK_KEYWORDS if kw in text)
    map_score = sum(1 for kw in _MAP_KEYWORDS if kw in text)

    if combat_score >= 2:
        states.update({"monster", "elite", "boss"})
    if deck_score >= 1:
        states.update({"card_select", "card_reward", "shop"})
    if map_score >= 1:
        states.update({"map", "rest_site", "shop", "event"})

    # Empty set = no clear match → tool will be skipped.
    # LLM-authored tools with vague descriptions should add explicit
    # APPLICABLE_STATES to opt in rather than running everywhere.
    return states


# ── Parameter binding from GameState ───────────────────────────

def _get_power_amount(powers: list, name: str) -> int:
    """Get a named power's amount from a powers list."""
    for p in powers:
        if p.name == name:
            return p.amount if p.amount is not None else 1
    return 0


def _has_power(powers: list, name: str) -> bool:
    """Check if a power is present."""
    return any(p.name == name for p in powers)


def _compute_incoming_damage(gs: GameState) -> int:
    """Compute total incoming damage from all enemy intents."""
    total = 0
    for enemy in gs.enemies:
        for intent in (enemy.intents or []):
            if intent.total_damage is not None:
                total += intent.total_damage
            elif intent.damage is not None:
                hits = intent.hits if intent.hits else 1
                total += intent.damage * hits
    return total


def _build_enemy_attacks(gs: GameState) -> list[dict]:
    """Build enemy attacks list for multi-enemy tools."""
    attacks = []
    for enemy in gs.enemies:
        for intent in (enemy.intents or []):
            if intent.damage is not None:
                attacks.append({
                    "name": enemy.name,
                    "hit_count": intent.hits or 1,
                    "damage_per_hit": intent.damage,
                })
    return attacks


def _build_hand_cards(gs: GameState) -> list[dict]:
    """Build hand cards list with block info."""
    cards = []
    for c in gs.hand:
        cards.append({
            "name": c.name,
            "block": c.block or 0,
            "cost": c.energy_cost if c.energy_cost is not None else 0,
        })
    return cards


def _build_block_cards_in_hand(gs: GameState) -> list[dict]:
    """Build list of block-generating cards in hand.

    Output keys match agent-authored tool expectations:
    - block_amount: base block value (before Dex/Frail)
    - energy_cost: card energy cost
    """
    return [
        {
            "name": c.name,
            "block_amount": c.block or 0,
            "energy_cost": c.energy_cost if c.energy_cost is not None else 0,
        }
        for c in gs.hand
        if c.block is not None and c.block > 0
    ]


def _build_enemies_list(gs: GameState) -> list[dict]:
    """Build enemies list for multi-enemy tools."""
    result = []
    for e in gs.enemies:
        intent_type = "unknown"
        damage = 0
        hits = 1
        is_weak = _has_power(e.powers, "Weak")

        if e.intents:
            first = e.intents[0]
            intent_type = first.intent_type or "unknown"
            damage = first.damage or 0
            hits = first.hits or 1

        result.append({
            "name": e.name,
            "hp": e.current_hp,
            "max_hp": e.max_hp,
            "block": e.block or 0,
            "intent": intent_type.lower(),
            "damage": damage,
            "hits": hits,
            "damage_per_turn": damage * hits,
            "is_weak": is_weak,
        })
    return result


def _build_deck_cards(gs: GameState) -> list[dict]:
    """Build deck cards list for deck analysis tools."""
    cards = []
    for c in gs.deck or []:
        card_type = getattr(c, "card_type", "unknown") or "unknown"
        is_basic = c.rarity == "Basic" if hasattr(c, "rarity") and c.rarity else False
        cards.append({
            "name": c.name,
            "type": card_type.lower(),
            "cost": c.energy_cost if hasattr(c, "energy_cost") and c.energy_cost is not None else 0,
            "is_basic": is_basic,
        })
    return cards


def _get_declared_type(pname: str, schema: dict | None) -> str | None:
    """Extract the declared type of a parameter from the tool's SCHEMA.

    Checks both nested (parameters.properties.X.type) and flat
    (parameters.X.type) formats.  Returns None when the schema does
    not declare the parameter's type.
    """
    if schema is None:
        return None
    params = schema.get("parameters", {})
    # Nested: {"parameters": {"properties": {"X": {"type": "array"}}}}
    props = params.get("properties", {})
    if pname in props and isinstance(props[pname], dict):
        return props[pname].get("type")
    # Flat: {"parameters": {"X": {"type": "array"}}}
    if pname in params and isinstance(params[pname], dict):
        return params[pname].get("type")
    return None


def bind_params(
    param_names: dict[str, Any],
    gs: GameState,
    schema: dict | None = None,
) -> dict[str, Any] | None:
    """Attempt to bind all parameter names from GameState.

    When *schema* is provided, declared ``type: "array"`` parameters
    receive list values (across all enemies) instead of scalars.

    Returns bound params dict, or None if any parameter cannot be bound.
    """
    combat = gs.raw.combat if gs.raw and hasattr(gs.raw, "combat") else None
    player = combat.player if combat else None
    player_powers = player.powers if player else []

    bindings: dict[str, Any] = {}

    for pname in param_names:
        if pname not in AUTO_BINDABLE:
            return None  # Cannot bind this param

        declared_type = _get_declared_type(pname, schema)
        val = _bind_single_param(pname, gs, combat, player, player_powers,
                                 declared_type=declared_type)
        if val is _UNBOUND:
            return None
        bindings[pname] = val

    return bindings


_UNBOUND = object()  # Sentinel for unbindable params


def _bind_single_param(
    pname: str,
    gs: GameState,
    combat: Any,
    player: Any,
    player_powers: list,
    *,
    declared_type: str | None = None,
) -> Any:
    """Bind a single parameter from GameState. Returns _UNBOUND if not possible.

    When *declared_type* is ``"array"``, per-enemy parameters return a list
    across all enemies instead of a scalar from ``enemies[0]``.
    """
    want_array = declared_type == "array"

    # Player vitals
    if pname in ("current_hp", "player_hp"):
        return gs.player_hp
    if pname == "max_hp":
        return gs.player_max_hp
    if pname == "current_block":
        return player.block if player else 0
    if pname in ("energy", "energy_available", "current_energy"):
        return gs.energy if gs.is_combat else 3
    if pname == "energy_per_turn":
        return gs.raw.run.max_energy if gs.raw and gs.raw.run else 3

    # Buffs/debuffs
    if pname == "dexterity":
        return _get_power_amount(player_powers, "Dexterity")
    if pname in ("strength", "current_strength"):
        return _get_power_amount(player_powers, "Strength")
    if pname == "frailed":
        return _has_power(player_powers, "Frail")
    if pname == "buffer_active":
        return _has_power(player_powers, "Buffer")
    if pname == "accuracy_stacks":
        return _get_power_amount(player_powers, "Accuracy")

    # Enemy info — array-aware bindings
    if pname == "enemies":
        return _build_enemies_list(gs)
    if pname == "enemy_hp":
        if want_array:
            return [e.current_hp for e in gs.enemies]
        return gs.enemies[0].current_hp if gs.enemies else 0
    if pname == "enemy_block":
        if want_array:
            return [e.block or 0 for e in gs.enemies]
        return gs.enemies[0].block if gs.enemies else 0
    if pname == "num_enemies":
        return len(gs.enemies)
    if pname == "enemy_vulnerable":
        if want_array:
            return [_has_power(e.powers, "Vulnerable") for e in gs.enemies]
        if gs.enemies:
            return _has_power(gs.enemies[0].powers, "Vulnerable")
        return False
    if pname == "poison_stacks":
        if want_array:
            return [_get_power_amount(e.powers, "Poison") for e in gs.enemies]
        if gs.enemies:
            return _get_power_amount(gs.enemies[0].powers, "Poison")
        return 0

    # Intents
    if pname in ("incoming_damage", "incoming_damage_per_turn"):
        return _compute_incoming_damage(gs)
    if pname == "enemy_damage":
        if gs.enemies and gs.enemies[0].intents:
            return gs.enemies[0].intents[0].damage or 0
        return 0
    if pname == "hits_per_turn":
        if gs.enemies and gs.enemies[0].intents:
            return gs.enemies[0].intents[0].hits or 1
        return 1
    if pname == "enemy_attacks":
        return _build_enemy_attacks(gs)

    # Deck / hand
    if pname in ("deck", "deck_cards", "cards"):
        if pname == "cards":
            # silent_archetype_score expects list of card name strings
            return [c.name for c in (gs.deck or [])]
        return _build_deck_cards(gs)
    if pname == "card_names":
        return [c.name for c in (gs.deck or [])]
    if pname == "deck_size":
        return gs.deck_size
    if pname == "basic_card_count":
        count = 0
        for c in (gs.deck or []):
            if hasattr(c, "rarity") and c.rarity == "Basic":
                count += 1
        return count
    if pname == "hand":
        return _build_hand_cards(gs)
    if pname == "block_cards_in_hand":
        cards = _build_block_cards_in_hand(gs)
        # Tool expects int count, not the list itself
        return len(cards) if isinstance(cards, list) else cards

    # Run progress
    if pname in ("floor", "current_floor"):
        return gs.floor
    if pname == "act":
        return gs.act
    if pname in ("current_gold", "gold"):
        return gs.gold

    return _UNBOUND


# ── Preprocessor ───────────────────────────────────────────────

class ToolPreprocessor:
    """Runs state-derived dynamic tools before LLM calls, injects results as hints."""

    def __init__(
        self,
        registry: DynamicToolRegistry,
        *,
        max_tools: int = 5,
        timeout_ms: float = 500,
    ) -> None:
        self._registry = registry
        self._max_tools = max_tools
        self._timeout_ms = timeout_ms
        self._usage_records: list[ToolUsageRecord] = []

    @property
    def usage_records(self) -> list[ToolUsageRecord]:
        """Return all telemetry records for the current run."""
        return list(self._usage_records)

    def reset(self) -> None:
        """Clear telemetry records for a new run.

        Called from AgentLoop.reset_for_new_run() so that
        get_telemetry_summary() describes the current run only.
        """
        self._usage_records.clear()

    def run_applicable(
        self,
        state_type: str,
        gs: GameState,
    ) -> list[ToolHint]:
        """Run applicable state-derived tools, return results as hints.

        Skips tools that:
        - Are classified as plan_evaluator
        - Don't match this state_type
        - Can't have inputs auto-filled from GameState
        - Fail during execution
        - Exceed timeout
        """
        hints: list[ToolHint] = []
        budget_start = time.monotonic()

        for name in sorted(self._registry.names()):
            if len(hints) >= self._max_tools:
                break

            # Budget check
            elapsed_ms = (time.monotonic() - budget_start) * 1000
            if elapsed_ms > self._timeout_ms:
                logger.debug("Preprocessor budget exhausted at %.0fms", elapsed_ms)
                break

            # Classification check
            mode = classify_tool_runtime_mode(name, self._registry)
            if mode != "state_derived":
                continue

            # State applicability check
            tool = self._registry.get(name)
            if tool is None:
                continue
            applicable = tool.schema.get("APPLICABLE_STATES")
            if applicable:
                if state_type not in applicable:
                    continue
            else:
                inferred = _infer_applicable_states(tool.schema)
                if state_type not in inferred:
                    continue

            # Parameter binding
            param_info = self._registry.get_param_info(name)
            if param_info is None:
                continue
            bound = bind_params(param_info, gs, schema=tool.schema)
            if bound is None:
                logger.debug("Preprocessor: cannot bind params for %s", name)
                continue

            # Execute
            t0 = time.monotonic()
            tool = self._registry.get(name)
            if tool is None:
                continue
            try:
                result = tool.execute_raw(**bound)
                latency_ms = (time.monotonic() - t0) * 1000
                success = True
                error = ""
            except Exception as exc:
                latency_ms = (time.monotonic() - t0) * 1000
                result = ""
                success = False
                error = str(exc)
                logger.debug("Preprocessor: %s failed: %s", name, exc)

            # Record telemetry
            self._usage_records.append(ToolUsageRecord(
                tool_name=name,
                state_type=state_type,
                success=success,
                latency_ms=latency_ms,
                error=error,
            ))

            if success and result:
                # Guard: _DynamicTool.execute() swallows exceptions and
                # returns "Tool X execution error: ..." strings.  These look
                # like success to the preprocessor — filter them out.
                result_str_check = str(result)
                if "execution error:" in result_str_check:
                    success = False
                    error = result_str_check
                    self._usage_records[-1] = ToolUsageRecord(
                        tool_name=name,
                        state_type=state_type,
                        success=False,
                        latency_ms=latency_ms,
                        error=error,
                    )
                else:
                    hints.append(ToolHint(
                        tool_name=name,
                        result=result,
                        latency_ms=latency_ms,
                    ))

        return hints

    def format_hints(self, hints: list[ToolHint], *, max_chars: int = 2000) -> str:
        """Format tool hints into a compact prompt section.

        Extracts actionable keys from results, deduplicates overlapping
        damage tools, and formats as concise one-liners.
        """
        if not hints:
            return ""

        # Deduplicate: if multiple tools have "total_incoming", keep the one
        # with more keys (more detailed)
        seen_incoming = False
        deduped: list[ToolHint] = []
        sorted_hints = sorted(
            hints,
            key=lambda h: len(h.result) if isinstance(h.result, dict) else 0,
            reverse=True,
        )
        for hint in sorted_hints:
            if isinstance(hint.result, dict) and "total_incoming" in hint.result:
                if seen_incoming:
                    continue
                seen_incoming = True
            deduped.append(hint)

        _PRIORITY_KEYS = {
            "recommendation", "verdict", "decision", "note",
            "survives", "hp_remaining", "hp_after", "damage_taken",
            "total_incoming", "net_damage", "lethal_turn",
        }

        lines = ["## Computed Insights"]
        total_chars = len(lines[0])

        for hint in deduped:
            # Try FORMAT_COMPACT first
            tool_obj = self._registry.get(hint.tool_name)
            if tool_obj and tool_obj.format_compact_fn:
                try:
                    result_str = tool_obj.format_compact_fn(hint.result)
                except Exception:
                    result_str = str(hint.result)[:200]
            elif isinstance(hint.result, dict):
                extracted = {
                    k: v for k, v in hint.result.items()
                    if k in _PRIORITY_KEYS and v is not None
                }
                if not extracted:
                    extracted = dict(list(hint.result.items())[:3])
                parts = [f"{k}={v}" for k, v in extracted.items()]
                result_str = ", ".join(parts)
            else:
                result_str = str(hint.result)[:200]

            line = f"- {hint.tool_name}: {result_str}"
            if total_chars + len(line) + 1 > max_chars:
                break
            lines.append(line)
            total_chars += len(line) + 1

        return "\n".join(lines) if len(lines) > 1 else ""

    def get_telemetry_summary(self) -> dict:
        """Return telemetry summary for evolution agent's get_performance_stats."""
        if not self._usage_records:
            return {}

        by_tool: dict[str, dict] = {}
        for rec in self._usage_records:
            if rec.tool_name not in by_tool:
                by_tool[rec.tool_name] = {
                    "runs": 0,
                    "successes": 0,
                    "total_latency_ms": 0.0,
                    "state_types": set(),
                }
            entry = by_tool[rec.tool_name]
            entry["runs"] += 1
            if rec.success:
                entry["successes"] += 1
            entry["total_latency_ms"] += rec.latency_ms
            entry["state_types"].add(rec.state_type)

        # Convert sets to lists for serialization
        return {
            name: {
                "runs": data["runs"],
                "successes": data["successes"],
                "avg_latency_ms": data["total_latency_ms"] / data["runs"],
                "state_types": sorted(data["state_types"]),
            }
            for name, data in by_tool.items()
        }
