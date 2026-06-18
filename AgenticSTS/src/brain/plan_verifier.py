"""PlanVerifier: verify combat plans with plan_evaluator tools.

Contains PlanParamBinder (extracts params from CombatPlan + GameState),
PlanVerifier (runs applicable plan_evaluator tools post-plan), and a
built-in Regent star-budget check that runs ahead of dynamic tools.

Flow:
  1. Run built-in checks (currently: Regent star_check)
  2. Filter to plan_evaluator tools only (via classify_tool_runtime_mode)
  3. Check APPLICABLE_STATES for combat_state_type match
  4. Bind parameters from CombatPlan + GameState (via bind_plan_params)
  5. Execute each tool, classify result severity
  6. Return VerificationResult with needs_replan flag + warnings/hints
  7. Record usage telemetry for evolution stats

Design decisions:
  - Only plan_evaluator tools run here (state_derived tools handled by ToolPreprocessor)
  - Max 5 tools, 500ms total budget (same constraints as ToolPreprocessor)
  - severity "critical" in result dict -> needs_replan=True
  - Deactivated tools and tools with wrong APPLICABLE_STATES are skipped
  - Built-in checks run regardless of registry contents and gate on character
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ── Plan-bindable parameters ──────────────────────────────────

# Tier 1: Trivially derivable from CombatPlan structure alone
AUTO_BINDABLE_FROM_PLAN_T1: frozenset[str] = frozenset({
    "play_sequence",      # list[str] — card names in plan order
    "num_cards_played",   # int — len(card actions)
    "ends_turn",          # bool — plan.end_turn
    "has_potion_use",     # bool — any potion action in plan
})

# Tier 2: Requires cross-referencing plan card names against GameState.hand
AUTO_BINDABLE_FROM_PLAN_T2: frozenset[str] = frozenset({
    "planned_block",      # sum of c.block for cards in plan
    "planned_damage",     # sum of c.damage for cards in plan (base only)
    "total_energy_spent", # sum of c.energy_cost for cards in plan
})

ALL_PLAN_BINDABLE = AUTO_BINDABLE_FROM_PLAN_T1 | AUTO_BINDABLE_FROM_PLAN_T2


# ── PlanParamBinder ──────────────────────────────────────────

def bind_plan_params(
    plan: Any,  # CombatPlan — use Any to avoid circular import
    gs: Any,    # GameState — use Any to avoid circular import
    *,
    required_params: set[str],
) -> dict[str, Any] | None:
    """Bind parameters from CombatPlan + GameState.

    Returns dict of bound params, or None if any required param is unbindable.
    Combines plan-derived params with state-derived params (via existing bind_params).
    """
    from src.brain.dynamic_tools import AUTO_BINDABLE
    from src.brain.tool_preprocessor import bind_params as bind_state_params

    bindings: dict[str, Any] = {}
    card_actions = [a for a in plan.actions if a.action_type == "card"]

    # Build name->card lookup from hand for Tier 2
    hand_lookup: dict[str, Any] = {}
    for c in gs.hand:
        hand_lookup[c.name] = c

    for pname in required_params:
        # Try plan Tier 1
        if pname in AUTO_BINDABLE_FROM_PLAN_T1:
            bindings[pname] = _bind_plan_t1(pname, plan, card_actions)
            continue
        # Try plan Tier 2
        if pname in AUTO_BINDABLE_FROM_PLAN_T2:
            bindings[pname] = _bind_plan_t2(pname, card_actions, hand_lookup)
            continue
        # Try state binding (reuse existing infrastructure)
        if pname in AUTO_BINDABLE:
            state_result = bind_state_params({pname: {}}, gs)
            if state_result is not None and pname in state_result:
                bindings[pname] = state_result[pname]
                continue
        # Unbindable
        return None

    return bindings


def _bind_plan_t1(pname: str, plan: Any, card_actions: list) -> Any:
    """Bind Tier 1 params from CombatPlan structure."""
    if pname == "play_sequence":
        return [a.card_name for a in card_actions]
    if pname == "num_cards_played":
        return len(card_actions)
    if pname == "ends_turn":
        return plan.end_turn
    if pname == "has_potion_use":
        return any(a.action_type == "potion" for a in plan.actions)
    return None


def _bind_plan_t2(pname: str, card_actions: list, hand_lookup: dict) -> Any:
    """Bind Tier 2 params by cross-referencing plan with hand cards."""
    total = 0
    for action in card_actions:
        card = hand_lookup.get(action.card_name)
        if card is None:
            continue  # Card not in hand (drawn mid-plan), 0 contribution
        if pname == "planned_block":
            total += getattr(card, "block", 0) or 0
        elif pname == "planned_damage":
            total += getattr(card, "damage", 0) or 0
        elif pname == "total_energy_spent":
            total += getattr(card, "energy_cost", 0) or 0
    return total


# ── Built-in: Regent star-budget check ────────────────────────

# Heuristic credit per provider card played in sequence. Most Regent providers
# grant +1 Star (Venerate, Hidden Cache, etc.); a few uncommon/rare providers
# grant more, but the conservative +1 keeps the check from greenlighting plans
# that miscount on outliers. A false negative (plan barely fits) is acceptable
# because the LLM still bears the final responsibility.
_PROVIDER_STAR_GRANT = 1


def _normalize_character(name: str | None) -> str:
    return (name or "").strip().lower()


def _check_regent_star_budget(plan: Any, gs: Any) -> dict[str, Any] | None:
    """Verify that a Regent plan does not overspend Stars.

    Walks the plan's card actions in order, simulating Star deltas:
      * each card's ``star_cost`` is debited in sequence
      * X-cost (``star_costs_x=True``) cards spend the entire pool
      * cards classified as Star ``provider`` credit ``+1`` (heuristic)

    Returns ``None`` when the plan is sound, or a dict with::

        {"severity": "high", "warning": "Plan needs N stars, only K available; ..."}

    Returns ``None`` for non-Regent runs, non-combat states, and empty plans.
    """
    if not plan or not getattr(plan, "actions", None):
        return None
    if _normalize_character(getattr(gs, "character", None)) != "the regent":
        return None

    raw = getattr(gs, "raw", None)
    combat = getattr(raw, "combat", None) if raw is not None else None
    player = getattr(combat, "player", None) if combat is not None else None
    if player is None:
        return None
    available = int(getattr(player, "stars", 0) or 0)

    hand_lookup: dict[str, Any] = {c.name: c for c in getattr(gs, "hand", [])}

    # Lazy import to avoid circular deps with prompts/ at module load.
    from src.brain.prompts._regent_economy_fmt import classify_card

    stars = available
    min_stars_seen = available
    consumer_count = 0
    overspend_card: str | None = None
    wasted_x_card: str | None = None

    for action in plan.actions:
        if getattr(action, "action_type", "card") != "card":
            continue
        card_name = action.card_name
        card = hand_lookup.get(card_name)
        if card is None:
            # Not in hand (drawn mid-plan or unresolvable name) — skip.
            continue

        cost = int(getattr(card, "star_cost", 0) or 0)
        x_cost = bool(getattr(card, "star_costs_x", False))

        if x_cost:
            consumer_count += 1
            # X-cost at 0 Stars is a wasted card play (X resolves to 0). Flag
            # separately because the running balance never goes negative.
            if stars <= 0 and wasted_x_card is None:
                wasted_x_card = card_name
            stars = 0
        elif cost > 0:
            consumer_count += 1
            stars -= cost
            if stars < 0 and overspend_card is None:
                overspend_card = card_name

        # Provider credit (heuristic +1) applied AFTER spend so the warning
        # fires on plans that consume before the Star arrives.
        star_role, _ = classify_card(card_name)
        if star_role == "provider":
            stars += _PROVIDER_STAR_GRANT

        if stars < min_stars_seen:
            min_stars_seen = stars

    if min_stars_seen < 0:
        short = -min_stars_seen
        msg = (
            f"Plan overspends Stars: short by {short} at "
            f"\"{overspend_card or 'unknown'}\" "
            f"(start={available}, projected min={min_stars_seen}, consumers={consumer_count}). "
            "Reorder Star providers earlier or drop a Star-cost card."
        )
        return {"severity": "high", "warning": msg}

    if wasted_x_card is not None:
        msg = (
            f"X-cost Star card \"{wasted_x_card}\" played with 0 Stars "
            f"(start={available}, consumers={consumer_count}). The card resolves "
            "to 0 effect — defer it until Stars are available or replace it."
        )
        return {"severity": "high", "warning": msg}

    return None


# ── Built-in: Regent Sovereign Blade safety check ─────────────

# Sovereign Blade's base damage. Anything above this means the Blade has been
# Forged at least once and exhausting/transforming it loses the Forge stack.
_SOVEREIGN_BLADE_BASE_DAMAGE = 10
_SOVEREIGN_BLADE_CARD_ID = "sovereign_blade"


def _is_sovereign_blade_target(target: Any) -> bool:
    """Return True if a discard/exhaust target string names Sovereign Blade."""
    if not target:
        return False
    if isinstance(target, str):
        candidates = (target,)
    elif isinstance(target, list | tuple):
        candidates = tuple(target)
    else:
        return False
    for t in candidates:
        if not t:
            continue
        s = str(t).strip().lower()
        if "sovereign blade" in s or "sovereign_blade" in s:
            return True
    return False


def _check_regent_forge_safety(plan: Any, gs: Any) -> dict[str, Any] | None:
    """Reject plans that exhaust/transform a Forged Sovereign Blade.

    Trigger conditions (all must hold):
      * character is The Regent
      * Sovereign Blade is in hand with damage > 10 (Forged at least once)
      * the plan plays a card whose ``discard`` field targets Sovereign Blade
        (the LLM specifies hand-card targets via PlannedAction.discard, used
        by Survivor/Prepared/Forge-exhaust-style cards)

    Edge case allowed: an unbuffed (damage == 10) Sovereign Blade can be
    exhausted to spawn a fresh copy — sometimes a deliberate strategy when
    new Forge buffs reapply. Only Forged blades are protected.

    Returns ``{"severity": "high", "warning": ...}`` or None.
    """
    if not plan or not getattr(plan, "actions", None):
        return None
    if _normalize_character(getattr(gs, "character", None)) != "the regent":
        return None

    raw = getattr(gs, "raw", None)
    combat = getattr(raw, "combat", None) if raw is not None else None
    if combat is None:
        return None

    sb_card: Any | None = None
    for c in getattr(combat, "hand", []) or []:
        if (getattr(c, "card_id", "") or "").lower() == _SOVEREIGN_BLADE_CARD_ID:
            sb_card = c
            break
    if sb_card is None:
        return None

    damage = getattr(sb_card, "damage", None)
    if damage is None or damage <= _SOVEREIGN_BLADE_BASE_DAMAGE:
        return None  # Not Forged — exhausting it is a valid reset strategy.

    for action in plan.actions:
        if getattr(action, "action_type", "card") != "card":
            continue
        if _is_sovereign_blade_target(getattr(action, "discard", "")):
            msg = (
                f"Plan would exhaust/transform Sovereign Blade ({damage} damage) via "
                f"\"{action.card_name}\" — all Forge stacks would be LOST. "
                "Pick a different exhaust target, or play the Blade first."
            )
            return {"severity": "high", "warning": msg}

    return None


# ── VerificationResult ─────────────────────────────────────────

@dataclass(frozen=True)
class VerificationResult:
    """Result of plan verification."""

    needs_replan: bool
    warnings: list[str]  # Critical issues that triggered re-plan
    hints: list[str]     # Non-critical observations (logged only)


# ── PlanVerifier ───────────────────────────────────────────────

class PlanVerifier:
    """Post-plan verification using plan_evaluator tools.

    Runs applicable plan_evaluator dynamic tools against a CombatPlan
    to detect critical issues (missed lethal, insufficient block, etc.).
    Critical findings set needs_replan=True; non-critical go to hints.
    """

    def __init__(
        self,
        registry: Any,  # DynamicToolRegistry
        *,
        max_tools: int = 5,
        timeout_ms: float = 500,
    ) -> None:
        self._registry = registry
        self._max_tools = max_tools
        self._timeout_ms = timeout_ms
        self._usage_records: list = []

    def verify(
        self,
        plan: Any,  # CombatPlan
        gs: Any,    # GameState
        *,
        combat_state_type: str = "monster",
    ) -> VerificationResult:
        """Run applicable plan_evaluator tools against a combat plan.

        Returns VerificationResult with needs_replan flag and collected warnings.
        """
        from src.brain.dynamic_tools import classify_tool_runtime_mode
        from src.brain.tool_preprocessor import ToolUsageRecord

        warnings: list[str] = []
        hints: list[str] = []

        # ── Built-in checks (run regardless of dynamic registry contents) ──
        for rule_name, rule_fn in (
            ("star_check", _check_regent_star_budget),
            ("forge_safety_check", _check_regent_forge_safety),
        ):
            try:
                rule_result = rule_fn(plan, gs)
            except Exception:
                logger.debug("%s failed", rule_name, exc_info=True)
                continue
            if rule_result is None:
                continue
            sev = rule_result.get("severity")
            msg = rule_result.get("warning") or rule_result.get("note") or ""
            if sev in ("high", "critical"):
                warnings.append(f"[{rule_name}] {msg}")
            elif msg:
                hints.append(f"[{rule_name}] {msg}")

        budget_start = time.monotonic()
        tools_run = 0

        for name in sorted(self._registry.names()):
            if tools_run >= self._max_tools:
                break
            elapsed_ms = (time.monotonic() - budget_start) * 1000
            if elapsed_ms > self._timeout_ms:
                break

            # Only plan_evaluator tools
            mode = classify_tool_runtime_mode(name, self._registry)
            if mode != "plan_evaluator":
                continue

            tool = self._registry.get(name)
            if tool is None or tool.deactivated:
                continue

            # Check APPLICABLE_STATES
            applicable = tool.schema.get("APPLICABLE_STATES", [])
            if applicable and combat_state_type not in applicable:
                continue

            # Try to bind params
            param_info = self._registry.get_param_info(name)
            if param_info is None:
                continue

            bound = bind_plan_params(plan, gs, required_params=set(param_info.keys()))
            if bound is None:
                continue  # Can't bind all params, skip this tool

            # Execute
            t0 = time.monotonic()
            try:
                result = tool.execute_raw(**bound)
                latency = (time.monotonic() - t0) * 1000
                tools_run += 1

                self._usage_records.append(ToolUsageRecord(
                    tool_name=name,
                    state_type=combat_state_type,
                    success=True,
                    latency_ms=latency,
                ))

                # Classify severity
                if isinstance(result, dict) and result.get("severity") == "critical":
                    warning_msg = result.get("warning", result.get("reason", str(result)))
                    warnings.append(f"[{name}] {warning_msg}")
                elif isinstance(result, dict):
                    hint_msg = result.get("note", result.get("recommendation", str(result)[:100]))
                    hints.append(f"[{name}] {hint_msg}")

            except Exception as exc:
                latency = (time.monotonic() - t0) * 1000
                self._usage_records.append(ToolUsageRecord(
                    tool_name=name,
                    state_type=combat_state_type,
                    success=False,
                    latency_ms=latency,
                    error=str(exc),
                ))
                logger.debug("PlanVerifier: %s failed: %s", name, exc)

        return VerificationResult(
            needs_replan=len(warnings) > 0,
            warnings=warnings,
            hints=hints,
        )

    def reset(self) -> None:
        """Clear telemetry for a new run."""
        self._usage_records.clear()

    def get_telemetry_summary(self) -> dict:
        """Return aggregated telemetry for evolution stats."""
        if not self._usage_records:
            return {}
        by_tool: dict[str, dict] = {}
        for rec in self._usage_records:
            if rec.tool_name not in by_tool:
                by_tool[rec.tool_name] = {"runs": 0, "successes": 0, "state_types": set()}
            entry = by_tool[rec.tool_name]
            entry["runs"] += 1
            if rec.success:
                entry["successes"] += 1
            entry["state_types"].add(rec.state_type)
        return {
            name: {
                "runs": d["runs"],
                "successes": d["successes"],
                "state_types": sorted(d["state_types"]),
            }
            for name, d in by_tool.items()
        }
