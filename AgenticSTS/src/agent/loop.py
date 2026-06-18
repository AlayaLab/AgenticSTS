"""Agent loop: observe → decide → act.

LLM brain with thinking mode for all strategic decisions,
skill-augmented prompts for expert knowledge injection,
random fallback for purely mechanical states.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re as _re
import time
import uuid
from collections import Counter as _Counter
from dataclasses import dataclass, field
from pathlib import Path

import config
from src.agent.state_machine import GameStateMachine, PhaseTransition
from src.brain.models import DecisionSource, LLMDecision
from src.brain.planner import CombatPlan, PlannedAction, is_draw_card, resolve_card_name
from src.brain.prompts._deck_fmt import strip_bbcode
from src.brain.prompts._intent_fmt import compute_total_incoming, format_enemy_intents_for_memory
from src.brain.prompts.bundle import build_bundle_selection_prompt
from src.brain.prompts.card_select import build_card_select_prompt, build_pack_selection_prompt
from src.brain.prompts.crystal_sphere import build_crystal_sphere_prompt
from src.brain.prompts.event import build_event_prompt
from src.brain.prompts.hand_select import build_hand_select_prompt
from src.brain.prompts.map import build_map_step_prompt, build_route_selection_prompt
from src.brain.prompts.rest import build_rest_prompt
from src.brain.prompts.reward import build_card_reward_prompt, build_relic_select_prompt
from src.brain.prompts.shop import build_shop_plan_prompt
from src.brain.route_checker import ReplanReason, check_replan_needed
from src.brain.route_planner import (
    RoutePath,
    enumerate_routes,
    format_routes_for_prompt,
    is_rest_node,
    sort_routes,
)
from src.log.session_logger import SessionLogger
from src.mcp_client import actions
from src.mcp_client.client import McpActionError, McpClient, McpError, McpTimeout
from src.mcp_client.upstream_models import RawDeckCardPayload
from src.state.game_state import GameState
from src.state.run_state import Decision, RunState
from src.state.state_parser import StateParseError, parse_state
from src.memory.combat_trace_renderer import (
    extract_candidate_cards,
    extract_skipped_cards,
    render_last_two_combats,
)
from src.storage import paths
from src.storage.postrun_lock import postrun_lock

logger = logging.getLogger(__name__)


def _maybe_render_combat_trace(
    *,
    stm,
    run_log_events: list[dict],
    floor_sum: int,
) -> "str | None":
    """Return a rendered combat trace or None when gated off.

    Gates (in order):
      1. ``config.POSTRUN_COMBAT_TRACE_ENABLED`` master switch.
      2. ``stm`` non-None.
      3. floor_sum >= ``config.POSTRUN_TRACE_MIN_FLOOR_SUM``.
      4. Renderer produces a non-None string (else skip).
    """
    if not config.POSTRUN_COMBAT_TRACE_ENABLED:
        return None
    if stm is None:
        return None
    if floor_sum < config.POSTRUN_TRACE_MIN_FLOOR_SUM:
        logger.info(
            "postrun_trace: skipped (floor_sum=%d < threshold=%d)",
            floor_sum, config.POSTRUN_TRACE_MIN_FLOOR_SUM,
        )
        return None
    try:
        return render_last_two_combats(
            stm, run_log_events,
            max_rounds=config.POSTRUN_TRACE_MAX_ROUNDS,
        )
    except Exception:
        logger.warning("postrun_trace: renderer raised", exc_info=True)
        return None


# Keywords in rules_text that indicate a card creates/adds new cards to hand.
_GENERATE_PATTERN = _re.compile(
    r"add.+to.+hand|put.+into.+hand|create|generate|gain.+shiv",
    _re.IGNORECASE,
)
_ENERGY_GAIN_PATTERN = _re.compile(
    r"gain.+energy|energy_icon|gain\s+\d+\s+energy",
    _re.IGNORECASE,
)
_X_COST_PATTERN = _re.compile(r"(?<![A-Za-z])X(?![A-Za-z])")


def _card_generates(rules_text: str) -> bool:
    """Return True if rules_text suggests the card adds new cards to hand."""
    return bool(_GENERATE_PATTERN.search(rules_text))


def _card_changes_energy(rules_text: str) -> bool:
    """Return True if rules_text suggests the action changes current energy."""
    return bool(_ENERGY_GAIN_PATTERN.search(strip_bbcode(rules_text or "")))


def _card_is_x_cost(card: object) -> bool:
    """Heuristic detection for X-cost cards from upstream hand payloads."""
    rules_text = strip_bbcode(getattr(card, "rules_text", "") or "")
    energy_cost = getattr(card, "energy_cost", 0)
    return energy_cost == 0 and bool(_X_COST_PATTERN.search(rules_text))


STUCK_THRESHOLD = 15  # Force fallback after this many identical state repeats

# Grace period before auto-closing a stray UI overlay (deck view, map-from-topbar,
# card/relic inspect zoom, pause menu).  Lets the human supervisor open these
# briefly to inspect run state without the agent immediately fighting the click.
# Set to 0 to disable the grace (close immediately); set high to almost never
# auto-close (manual escape only).
OVERLAY_AUTO_CLOSE_GRACE_SECONDS = float(os.getenv("STS2_OVERLAY_GRACE_SECONDS", "30"))

# Action names exposed by the mod that close stray UI overlays.  Treated as
# "escape only" actions — they are NOT part of normal play, so when the avail
# set consists only of these (plus save_and_quit), the agent is in a degenerate
# overlay state caused by a stray click rather than legitimate gameplay.
_OVERLAY_ESCAPE_ACTIONS = ("close_pause_menu", "close_capstone_overlay")

_SHOP_RELIC_TRANSITION_TIMEOUTS = {
    "dolly's mirror": 4.0,
    "dolly\u2018s mirror": 4.0,
    "kifuda": 4.0,
    "orrery": 4.0,
}
_FOUL_POTION_ID = "FOUL_POTION"
_FOUL_POTION_NAME = "foul potion"

# Hard character caps for context fields in _build_decision_context().
# Prevents prompt bloat when injecting skills, knowledge, etc.
_CONTEXT_CHAR_CAPS: dict[str, int] = {
    "knowledge_context": 1600,   # ~400 tokens
    "boss_strategy": 1600,       # ~400 tokens
    "extra_context": 2000,       # ~500 tokens (ToolPreprocessor hints)
}

# Maps MCP action names to combat delta event types.
# Actions not listed here (proceed, buy_card, etc.) are silently skipped.
_ACTION_TO_EVENT_TYPE: dict[str, str] = {
    "play_card": "card_play",
    "use_potion": "potion_use",
    "end_turn": "end_turn",
    "select_deck_card": "card_select",
    "confirm_selection": "selection_confirm",
}


@dataclass
class ShopPlanItem:
    """One planned purchase in a shop visit."""
    action: str       # "buy_card" | "buy_relic" | "buy_potion" | "remove_card_at_shop" | "discard_potion"
    item_name: str    # Shop item name, OR for discard_potion: held-potion name
    price: int
    gold_after: int   # Expected gold after purchase
    reason: str = ""


@dataclass(frozen=True, slots=True)
class SelectionCardSpec:
    """Best-effort stable identity for one planned selection target."""

    requested_index: int | None
    stable_id: str = ""
    card_id: str = ""
    name: str = ""
    upgraded: bool = False


@dataclass
class ShopPlan:
    """Full purchase plan for a shop visit."""
    items: list[ShopPlanItem] = field(default_factory=list)
    current_index: int = 0
    reasoning: str = ""
    strategic_note: str = ""

    @property
    def is_complete(self) -> bool:
        return self.current_index >= len(self.items)

    @property
    def current_item(self) -> ShopPlanItem | None:
        if self.is_complete:
            return None
        return self.items[self.current_index]

    def advance(self) -> None:
        self.current_index += 1

# ── Event outcome diff helpers ─────────────────────────────────


def _card_display_name(card) -> str:
    name = getattr(card, "name", "") or ""
    return f"{name}+" if getattr(card, "upgraded", False) and not name.endswith("+") else name


def _occupied_potion_names(gs) -> list[str]:
    if gs is None:
        return []
    return [
        p.name for p in getattr(gs, "potions", [])
        if getattr(p, "occupied", False) and getattr(p, "name", None)
    ]


def _multiset_added_removed(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    before_counter = _Counter(before)
    after_counter = _Counter(after)
    gained = list((after_counter - before_counter).elements())
    lost = list((before_counter - after_counter).elements())
    return sorted(gained), sorted(lost)


def _compute_event_state_diff(prev_gs, gs) -> dict[str, list[str]]:
    """Compute concrete deck/relic/potion diffs between two game states."""
    if gs is None:
        return {
            "cards_gained": [],
            "cards_lost": [],
            "relics_gained": [],
            "potions_gained": [],
        }

    prev_deck = [_card_display_name(c) for c in getattr(prev_gs, "deck", [])]
    next_deck = [_card_display_name(c) for c in getattr(gs, "deck", [])]
    cards_gained, cards_lost = _multiset_added_removed(prev_deck, next_deck)

    prev_relics = [r.name for r in getattr(prev_gs, "relics", []) if getattr(r, "name", "")]
    next_relics = [r.name for r in getattr(gs, "relics", []) if getattr(r, "name", "")]
    relics_gained, _ = _multiset_added_removed(prev_relics, next_relics)

    prev_potions = _occupied_potion_names(prev_gs)
    next_potions = _occupied_potion_names(gs)
    potions_gained, _ = _multiset_added_removed(prev_potions, next_potions)

    return {
        "cards_gained": cards_gained,
        "cards_lost": cards_lost,
        "relics_gained": relics_gained,
        "potions_gained": potions_gained,
    }


def _record_injected_skills(short_term, skill_ids) -> None:
    """Append retrieved skill IDs to the active CombatTracker (if any).

    Safe no-op when no combat is active, ``short_term`` is None, or
    ``skill_ids`` is empty. Duplicates are permitted — downstream lifecycle
    (spec §6.1) reads the list set-wise when attributing per-combat baseline
    outcomes to skills that were actually injected during the combat.

    Only combat retrievals feed this list. Non-combat decisions
    (map/event/shop/rest/card_reward) are tracked separately.
    """
    if not skill_ids:
        return
    if short_term is None:
        return
    try:
        tracker_fn = getattr(short_term, "active_combat_tracker", None)
        if tracker_fn is None:
            return
        tracker = tracker_fn()
    except Exception:
        logger.debug("active_combat_tracker lookup failed", exc_info=True)
        return
    if tracker is None:
        return
    try:
        tracker.retrieved_skill_ids.extend(skill_ids)
    except Exception:
        logger.debug("extend retrieved_skill_ids failed", exc_info=True)


def _skill_matching_card_names(gs: GameState) -> frozenset[str]:
    """Return card names available for skill `requires_cards` matching.

    Non-combat deck-building skills can be about cards already in the deck or
    cards currently offered for selection/purchase, so include both surfaces.
    """
    names: set[str] = set()

    def add(name: object) -> None:
        if not isinstance(name, str) or not name:
            return
        base_name = name.rstrip("+")
        names.add(name)
        names.add(name.lower())
        names.add(base_name)
        names.add(base_name.lower())

    if gs.is_combat and gs.combat and gs.combat.player:
        for card in gs.hand or []:
            add(getattr(card, "name", ""))
        return frozenset(names)

    for card in gs.deck or []:
        add(getattr(card, "name", ""))

    if gs.state_type == "card_reward" and gs.reward:
        for card in getattr(gs.reward, "card_options", []) or []:
            add(getattr(card, "name", ""))

    if gs.state_type == "shop" and gs.shop:
        for card in getattr(gs.shop, "cards", []) or []:
            if getattr(card, "is_stocked", True):
                add(getattr(card, "name", ""))

    if gs.state_type == "card_select" and gs.selection:
        for card in getattr(gs.selection, "cards", []) or []:
            add(getattr(card, "name", ""))

    return frozenset(names)


def _build_event_option_detail(option: object) -> dict:
    """Convert a mod-side EventOption payload into the dict shape
    EventOptionSnapshot.from_dict expects.

    BBCode is stripped from all user-visible text fields. Reward lists
    (relics_offered / cards_offered / potions_offered) are forwarded as
    dicts; downstream EventOptionSnapshot.from_dict handles the mod→Python
    key rename (type→card_type, is_upgraded→upgraded, type→potion_type).

    Bare-string reward entries (legacy or from reduced payloads) are
    wrapped as ``{"name": s}`` so downstream parsing treats them uniformly.
    """
    raw_desc = (
        getattr(option, "effect_description", "")
        or getattr(option, "description", "")
    )
    detail: dict = {
        "index": getattr(option, "index", 0),
        "title": strip_bbcode(getattr(option, "title", "") or ""),
        "description": strip_bbcode(raw_desc or ""),
    }
    hp_cost = getattr(option, "hp_cost", None)
    if hp_cost is not None:
        detail["hp_cost"] = hp_cost
    gold_cost = getattr(option, "gold_cost", None)
    if gold_cost is not None:
        detail["gold_cost"] = gold_cost

    def _coerce_reward(item: object, text_keys: tuple) -> dict:
        if isinstance(item, dict):
            out = dict(item)
            for k in text_keys:
                if k in out and isinstance(out[k], str):
                    out[k] = strip_bbcode(out[k])
            return out
        # Fallback: bare-string name
        return {"name": str(item) if item is not None else ""}

    for src_attr, text_keys in (
        ("relics_offered", ("description",)),
        ("cards_offered", ("rules_text",)),
        ("potions_offered", ("description",)),
    ):
        raw_list = getattr(option, src_attr, None) or []
        if raw_list:
            detail[src_attr] = [_coerce_reward(it, text_keys) for it in raw_list]

    return detail


def _plan_decision_reasoning(
    en_prefix: str,
    plan: CombatPlan,
    *,
    card_name: str | None = None,
) -> tuple[str, str]:
    """Build (reasoning, reasoning_zh) for a plan-derived per-action decision.

    The English form is ``"{en_prefix} — {plan.reasoning}"``. The Chinese form
    reuses the LLM-emitted ``plan.reasoning_zh`` verbatim (already proper
    prose) instead of letting session_logger fall back to mechanical
    entity-name substitution on the English text — the latter produces
    broken bilingual output like
    ``"The remaining 噬尸蛞蝓 has 20 HP. 君王之剑 deals 17 damage..."``.

    When ``card_name`` is provided, its English form in the prefix is
    replaced with the Chinese name (via ``LocaleTranslator.to_chinese``)
    in the zh prefix. ``reasoning_zh`` is empty when ``plan.reasoning_zh``
    is empty so callers can leave it unset on the Decision.
    """
    reasoning = f"{en_prefix} — {plan.reasoning}" if plan.reasoning else en_prefix
    if not plan.reasoning_zh:
        return reasoning, ""
    zh_prefix = en_prefix
    body_zh = plan.reasoning_zh
    try:
        from src.knowledge.locale_translator import get_translator
        translator = get_translator()
        if card_name:
            zh_name = translator.to_chinese(card_name)
            if zh_name and zh_name != card_name:
                zh_prefix = en_prefix.replace(card_name, zh_name, 1)
        # Localize any English entity names the LLM left verbatim in
        # reasoning_zh (the prompt asks it to keep names English so we can
        # translate them locally — same pass v2_engine applies to LLM-direct
        # decisions via _localize_reasoning_zh).
        body_zh = translator.translate_summary(body_zh)
    except Exception:
        pass
    reasoning_zh = f"{zh_prefix} — {body_zh}"
    return reasoning, reasoning_zh


class AgentLoop:
    """Core agent loop with LLM brain and skill-augmented decisions.

    Continuously polls game state, retrieves relevant skills,
    decides on an action via V2Engine (multi-turn tool-use agent),
    and executes it.

    Augmented with:
    - Skill library: procedural knowledge modules for expert decisions
    - Memory system: cross-run learning (V2 HCM domain stores + guides)
    """

    def __init__(
        self,
        client: McpClient,
        max_steps: int = 2000,
        use_llm: bool = True,
        memory_manager: object | None = None,
        experiment_tag: str = "",
    ) -> None:
        self._client = client
        self._max_steps = max_steps
        self._use_llm = use_llm
        # Carried through postrun stages so cross-run helpers (Mode B stub fill,
        # any future cross-run aggregator) can scope ``runs/history.jsonl``
        # queries to the current ablation slice. Empty string means "personal
        # / dev play" — the same scope rule applies, just selecting untagged
        # records instead of a specific experiment.
        self._experiment_tag = (experiment_tag or "").strip()
        self._running = False
        self._run_state: RunState | None = None
        self._state_machine = GameStateMachine()
        self._session_logger: SessionLogger | None = None
        self._current_step: int = 0
        self._stuck_key: str = ""
        self._stuck_count: int = 0
        self._last_run_aborted: bool = False  # Set on RuntimeError abort; cleared by reset_for_new_run
        self._run_completion_reason: str = ""
        self._run_end_reason: str = ""
        # Multi-card selection tracking (card_select/hand_select with N>1 required)
        self._card_select_target: int = 0  # Required number (parsed from prompt)
        self._card_select_progress: int = 0  # Picks made in current session
        self._card_select_selected: set[int] = set()  # Stable indices selected in current session
        self._pack_selection_key: tuple[str, ...] | None = None
        self._pack_last_clicked_option: int | None = None
        self._pack_previews: dict[int, list] = {}
        self._last_combat_round: int = -1  # Track round for potion decisions
        self._end_turn_sent_round: int = -1  # Track round we already sent end_turn
        self._planned_act: int = -1  # Which act we've planned for
        # Combat turn plan: plan-then-execute architecture
        self._combat_plan: CombatPlan | None = None
        self._combat_plan_index: int = 0  # Next action to execute in current plan
        self._combat_plan_round: int = -1  # Round the plan was generated for
        self._no_target_replan_round: int = -1  # Round we entered no-target replan mode
        self._prev_combat_plan: CombatPlan | None = None  # Saved before any same-round re-plan
        self._replan_trigger_desc: str = ""  # Human-readable trigger phrase for the prompt
        self._replan_trigger_kind: str = ""  # Structured trigger label for logs/monitor
        self._combat_plan_alive: set[int] = set()  # Enemy indices alive when plan was created
        # Snapshot of enemy_id list at plan-creation time, positional.
        # Used to remap plan-time target_index → current index when enemies
        # die mid-plan and the mod renumbers survivors (see _remap_plan_target).
        self._combat_plan_enemy_ids: tuple[str, ...] | None = None
        # Skill eval mode (boss replay A/B testing)
        self._skill_eval_state: str = "idle"  # "idle" | "active" | "final"
        self._eval_results: list = []
        self._eval_skill_sets: list[list[str]] = []
        self._eval_current_index: int = 0
        self._eval_original_skill_ids: list[str] = []
        self._eval_combat_start_hp: int = 0
        self._eval_round_count: int = 0
        self._eval_potions_used: int = 0
        self._last_played_card_name: str = ""  # Last card played (for re-plan context)
        self._last_played_card_rules: str = ""  # rules_text of last played card
        self._last_played_plan_action: PlannedAction | None = None  # Survives plan invalidation
        # V2: track executed actions per round for conversation feedback
        self._v2_round_actions: list[str] = []
        self._route_plan: RoutePath | None = None  # Selected route for current act
        self._live_remaining_route: list[tuple[int, str]] | None = None  # Updated from live map data every map step
        # Per-act offset such that ``floor = act_start_floor + row + 1`` for the
        # current map. Derived from runtime data (gs.floor - is_current.row - 1)
        # so it stays correct if the game changes act lengths in a future patch.
        self._act_start_floor_cache: dict[int, int] = {}
        # Relic cache: "Name (description)" or "Name" per relic, updated every step.
        # format_relic_hints() extracts the name before " (" for lookup matching.
        self._cached_relics: list[str] = []
        # Deck payload cache: last observed RawDeckCardPayload list. Needed at
        # postrun time so the build analyst can see enchantments + resolved
        # rules text that the plain name-only final_deck reconstruction drops.
        self._cached_deck_payload: list[RawDeckCardPayload] = []
        # Runtime card-rules accumulator: name → resolved_rules_text (stripped).
        # Populated from every card-bearing gs payload (deck/hand/shop/reward/
        # selection). Preferred over the card knowledge lookup at postrun time
        # because game balance patches make the lookup drift — the live payload
        # is always what this run actually saw. Cleared per run.
        self._seen_card_rules: dict[str, str] = {}
        # Track card reward items already opened (to avoid re-open loop)
        self._opened_card_rewards: set[int] = set()
        # Track card count before opening a card reward (for pick vs skip detection)
        self._card_reward_count_before_open: int | None = None
        self._last_opened_card_index: int | None = None
        # Shop visit state: auto-open at most once, then honor leave intent.
        self._shop_auto_opened_this_visit: bool = False
        self._shop_pending_leave: bool = False
        self._shop_plan: ShopPlan | None = None  # Active shop purchase plan
        # Cache upcoming node types from last map state (for rest/shop threat assessment)
        self._upcoming_node_types: list[str] = []
        # Cache the chosen map node's combat type before entering combat
        # (MCP API doesn't return map data during combat, so we cache it here)
        self._cached_map_node_type: str = ""
        # Stray UI overlay tracker (deck view, map-from-topbar, inspect zoom,
        # pause menu).  Holds the close action name as a token and the
        # monotonic timestamp when the overlay was first observed, so we can
        # respect a grace period before auto-closing — the human supervisor
        # may have opened the overlay deliberately to inspect state.
        self._overlay_grace_started_at: float | None = None
        self._overlay_grace_token: str | None = None
        # Non-combat skill scoring: track healing and boss kills per run
        self._act_heal_total: int = 0  # Total HP healed via rest in current act
        self._bosses_killed: list[int] = []  # Act numbers of bosses killed
        self._last_boss_entry_hp: int | None = None  # HP at last boss fight entry
        self._last_boss_heal_total: int = 0  # _act_heal_total snapshot at boss entry
        self._last_seen_act: int = 0  # Track act changes to reset heal total
        self._last_combat_type: str = ""  # "monster", "elite", "boss" — set at COMBAT_START
        self._current_combat_start_hp: int = 0
        self._last_known_enemies: list = []  # Cached enemies from last monster state (for hand_select)
        # Memory system (optional)
        self._memory = memory_manager  # MemoryManager or None
        # Game knowledge database
        self._knowledge = self._init_knowledge()
        # Web search
        self._web_searcher = self._init_web_searcher()
        # Boss strategy (from web search, injected into boss combat prompts)
        self._boss_strategy: str = ""
        self._boss_search_task: asyncio.Task | None = None
        # Write gate (observation mode — commits 1-3 of the write-gate spec).
        # The shared JudgeQueue lets check() / observe_skill_batch enqueue
        # candidates that hit the §4.3 judge zone; flush_judge_round() drains
        # the queue with one batch LLM call at end of postrun.
        from src.memory.write_gate import WriteGate as _WriteGate
        from src.memory.write_gate_judge import JudgeQueue as _JudgeQueue
        self._write_gate_queue = _JudgeQueue()
        self._write_gate = _WriteGate(judge_queue=self._write_gate_queue)
        # Skill system
        self._skill_library = None
        self._active_skill_ids: list[str] = []  # Skills injected in current decision
        self._combat_skill_ids: set[str] = set()  # All skills used during current combat
        self._noncombat_skill_ids: set[str] = set()  # Skills used in non-combat decisions
        self._noncombat_skill_counts: dict[str, int] = {}  # Per-skill injection count this act
        self._skill_trigger_log: list[dict[str, object]] = []  # (A4) skill trigger accumulator
        self._pending_build_mem: tuple | None = None  # (CardBuildMemory, evidence_dict)
        self._pending_combat_trace: str | None = None  # rendered trace text for Turn 2
        self._pending_trace_candidates: list[str] = []  # candidate cards scoped to the trace
        self._pending_skipped_cards: list[str] = []  # offered-but-not-picked cards from this run's logs (bucket B)
        self._postrun_consolidation_active: bool = False  # Spec #2: cadence snapshot for skills-stage mistake_discovery
        self._prev_event_gs: GameState | None = None  # snapshot before event decision for diff
        if config.SKILLS_ENABLED:
            self._skill_library = self._init_skill_library()

        # Monitor event bus (optional, for real-time dashboard)
        self._event_bus = None

        # ── V2 architecture (multi-turn combat + tool-use agent) ──
        self._v2_engine = None
        self._v2_combat_conversation = None  # CombatConversation for current fight
        self._v2_tool_executor = None  # ToolExecutor
        self._dynamic_registry = None
        self._tool_preprocessor = None
        # These were formerly only initialized inside _init_v2(); hoisting to
        # __init__ so reset_for_new_run() works on --no-llm paths too.
        self._plan_verifier = None
        self._snapshot_store = None
        if config.gameplay_supports_v2() and use_llm:
            self._init_v2()

    def _init_v2(self) -> None:
        """Initialize V2 architecture components. Called once from __init__."""
        try:
            from src.brain.tool_executor import ToolExecutor
            from src.brain.v2_backend import V2Backend
            from src.brain.v2_engine import V2Engine

            backend = V2Backend()
            self._v2_tool_executor = ToolExecutor(
                knowledge=self._knowledge,
                memory_manager=self._memory,
                skill_library=self._skill_library,
            )

            # Dynamic tool registry: load agent-authored tools from disk.
            # Dynamic tools are not exposed as live API tools or ToolExecutor
            # handlers; they are consumed locally by EvolutionEngine and the
            # ToolPreprocessor.
            self._dynamic_registry = None
            self._tool_preprocessor = None
            self._plan_verifier = None
            self._snapshot_store = None
            if config.EVOLUTION_ENABLED:
                try:
                    from src.brain.dynamic_tools import DynamicToolRegistry
                    from src.brain.tool_preprocessor import ToolPreprocessor

                    registry = DynamicToolRegistry(config.EVOLUTION_TOOLS_DIR)
                    loaded = registry.load_all()
                    registry.load_stats()  # Restore usage counts from previous runs
                    self._dynamic_registry = registry
                    if loaded:
                        logger.info("Dynamic tool registry: %d tools loaded", loaded)
                    # Initialize unconditionally so runtime-authored tools and
                    # telemetry are available even when the registry starts empty.
                    self._tool_preprocessor = ToolPreprocessor(registry)
                    # PlanVerifier: post-plan validation via plan_evaluator tools.
                    # Initialized here but NOT wired into combat flow yet.
                    from src.brain.plan_verifier import PlanVerifier
                    self._plan_verifier = PlanVerifier(registry)
                    # StateSnapshotStore: capture real GameState for tool validation.
                    from src.brain.state_snapshot_store import StateSnapshotStore
                    self._snapshot_store = StateSnapshotStore()
                except Exception as exc:
                    logger.warning("Dynamic tool registry init failed: %s", exc)

            self._v2_engine = V2Engine(
                backend=backend,
                tool_executor=self._v2_tool_executor,
            )
            logger.info("V2 architecture initialized (multi-turn + tool-use)")
        except Exception as exc:
            logger.error("V2 init failed: %s", exc)
            self._v2_engine = None

    def _maybe_create_combat_conversation(self, gs: "GameState") -> object | None:
        """Create a CombatConversation for the current fight, or None when
        STS2_COMBAT_CONVERSATION_ENABLED=false. Call sites already check
        ``self._v2_combat_conversation`` for truthy before use."""
        if not config.COMBAT_CONVERSATION_ENABLED:
            return None
        from src.brain.conversation import CombatConversation
        from src.brain.prompts.system import get_system_prompt

        resolved_combat_type = self._resolve_combat_type(gs)
        return CombatConversation(get_system_prompt(resolved_combat_type))

    def set_event_bus(self, event_bus: object) -> None:
        """Attach monitor event bus for real-time dashboard streaming."""
        self._event_bus = event_bus

    def _emit_monitor(self, event_type: str, data: dict) -> None:
        """Emit to monitor event bus. Never raises."""
        if self._event_bus is not None:
            try:
                run_id = getattr(self._run_state, "run_id", None) if self._run_state else None
                self._event_bus.emit(event_type, data, run_id=run_id)
            except Exception:
                pass

    def _build_combat_plan_event(
        self, plan: CombatPlan, *, no_target_mode: bool = False,
        trigger_kind: str = "",
    ) -> dict:
        """Assemble a combat_plan monitor payload with bilingual enrichment.

        When STS2_DISPLAY_LANGUAGE=zh, each item also carries a `card_zh`
        field (English-name → Chinese via the localization translator) and a
        prebuilt `text` summary so stream-ui's display chain (message > text
        > reasoning > summary) renders Chinese ahead of English fields.
        """
        import config
        items: list[dict] = []
        zh_mode = config.DISPLAY_LANGUAGE == "zh"
        translator = None
        if zh_mode:
            try:
                from src.knowledge.locale_translator import get_translator
                translator = get_translator()
            except Exception:
                translator = None
        kb = None
        try:
            from src.knowledge.knowledge import GameKnowledge
            kb = GameKnowledge.get_instance()
        except Exception:
            kb = None

        for a in plan.actions:
            entry = {
                "type": a.action_type,
                "card": a.card_name,
                "target": a.target_index,
            }
            if translator is not None:
                zh_name = translator.to_chinese(a.card_name) if a.card_name else None
                if zh_name:
                    entry["card_zh"] = zh_name
                t_zh = translator.translate_plan_item_type(a.action_type)
                if t_zh:
                    entry["type_zh"] = t_zh
            if kb is not None and a.card_name:
                try:
                    if a.action_type == "potion":
                        looked = kb.potions.get(a.card_name) if hasattr(kb, "potions") else None
                    else:
                        looked = kb.cards.get(a.card_name)
                    rarity = getattr(looked, "rarity", "") if looked else ""
                    if rarity:
                        entry["rarity"] = rarity
                except Exception:
                    pass
            items.append(entry)

        payload: dict = {
            "items": items,
            "end_turn": plan.end_turn,
            "reasoning": plan.reasoning[:500],
            "reasoning_zh": (plan.reasoning_zh or "")[:500],
        }
        if no_target_mode:
            payload["no_target_mode"] = True
        if trigger_kind:
            payload["trigger_kind"] = trigger_kind

        # zh-loss anomaly detection: in zh display mode, plan.reasoning is
        # populated but plan.reasoning_zh is empty. Dump the LLM trace so we
        # can root-cause whether the loss is in the model output, the
        # decision parser, or the tool-call path (combat_plan tool schema
        # has no reasoning_zh property).
        if zh_mode and plan.reasoning and not plan.reasoning_zh:
            self._dump_zh_loss_trace(plan, trigger_kind=trigger_kind)

        if zh_mode:
            type_labels = {"card": "卡牌", "potion": "药水"}
            lines: list[str] = []
            for i, entry in enumerate(items, start=1):
                t_label = type_labels.get(entry["type"], entry["type"])
                name = entry.get("card_zh") or entry.get("card") or ""
                target = entry.get("target")
                tail = f" → 目标 {target}" if target is not None else ""
                if name:
                    lines.append(f"{i}. [{t_label}] {name}{tail}")
                else:
                    lines.append(f"{i}. [{t_label}]")
            if plan.end_turn:
                lines.append("→ 结束回合")
            if lines:
                payload["text"] = "\n".join(lines)

        # Inline markup for the plan's reasoning paragraph (display-only, on a
        # new `reasoning_marked` field — keeps `reasoning` / `reasoning_zh`
        # clean for memory and multi-turn LLM context).
        try:
            from src.knowledge.locale_translator import get_translator
            translator = get_translator()
            src_text = plan.reasoning_zh or plan.reasoning
            if src_text:
                marked = translator.apply_inline_markup(src_text)
                if marked and marked != src_text:
                    payload["reasoning_marked"] = marked[:500]
        except Exception:
            pass

        return payload

    def _dump_zh_loss_trace(
        self, plan: CombatPlan, *, trigger_kind: str = "",
    ) -> None:
        """Persist a zh-loss diagnostic record to ``<data>/evolution/debug/zh_loss/``.

        Fires from ``_build_combat_plan_event`` when the agent is in zh display
        mode but the plan reached event emission with empty ``reasoning_zh``.
        Captures the trace attached at parse time (raw LLM text, decision_input
        dict) so we can determine whether the LLM never emitted reasoning_zh,
        the decision parser dropped it, or the tool-call path (which has no
        reasoning_zh property in its schema) was taken instead of the
        text-decision path. Writes one JSON file per occurrence; never raises.
        """
        try:
            run_id = getattr(self._run_state, "run_id", "") if self._run_state else ""
            step = self._current_step
            floor = (
                getattr(self._run_state, "_highest_floor", 0)
                or getattr(self._run_state, "final_floor", 0)
                if self._run_state else 0
            )
            ts = time.strftime("%Y%m%d_%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
            trace = plan._debug_trace or {}
            decision_input = trace.get("decision_input") if isinstance(trace, dict) else None
            decision_input_keys = (
                sorted(decision_input.keys())
                if isinstance(decision_input, dict)
                else []
            )
            had_reasoning_zh_in_input = (
                isinstance(decision_input, dict)
                and bool(decision_input.get("reasoning_zh"))
            )
            record = {
                "ts": ts,
                "run_id": run_id,
                "step": step,
                "floor": floor,
                "trigger_kind": trigger_kind,
                "plan": {
                    "actions": [
                        {
                            "type": a.action_type,
                            "card": a.card_name,
                            "potion_index": a.potion_index,
                            "target_index": a.target_index,
                        }
                        for a in plan.actions
                    ],
                    "end_turn": plan.end_turn,
                    "reasoning": plan.reasoning,
                    "reasoning_zh": plan.reasoning_zh,
                    "note_to_future_self": plan.note_to_future_self,
                },
                "diagnosis": {
                    "had_reasoning_zh_in_decision_input": had_reasoning_zh_in_input,
                    "decision_input_keys": decision_input_keys,
                    "trace_present": bool(trace),
                },
                "decision_input": decision_input,
                "raw_text": trace.get("raw_text", "") if isinstance(trace, dict) else "",
            }
            out_dir = paths.evolution_dir() / "debug" / "zh_loss"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{ts}_{run_id or 'unknown'}_step{step}.json"
            out_path.write_text(
                json.dumps(record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.warning(
                "zh-loss: plan.reasoning set but plan.reasoning_zh empty in "
                "DISPLAY_LANGUAGE=zh mode. step=%d floor=%d trigger=%r "
                "input_had_zh=%s input_keys=%s dump=%s",
                step, floor, trigger_kind, had_reasoning_zh_in_input,
                decision_input_keys, out_path,
            )
        except Exception as exc:
            logger.debug("zh-loss dump failed: %s", exc)

    def _get_short_term_ref(self) -> object | None:
        """Return the short-term memory store when available."""
        import config
        if not config.STM_ENABLED:
            return None
        if self._memory and hasattr(self._memory, "short_term"):
            return self._memory.short_term
        return None

    def _get_enemy_episodes(self, gs: "GameState") -> list:
        """Fetch past combat episodes for current enemy for pattern injection."""
        if not self._memory or not gs.enemies:
            return []
        combat_store = getattr(self._memory, "combat_store", None)
        if not combat_store:
            return []
        names = [e.name for e in gs.enemies]
        enemy_key = names[0] if len(names) == 1 else "multi:" + "+".join(sorted(names))
        # Use exact-match retrieval — cross-enemy patterns are noise for behavior prediction
        episodes = combat_store.get_by_enemy(enemy_key)
        episodes.sort(key=lambda e: e.timestamp, reverse=True)
        return episodes[:3]

    @staticmethod
    def _card_energy_cost(card: object) -> int:
        """Return a card's energy cost when the payload exposes it."""
        return card.energy_cost if hasattr(card, "energy_cost") else 0

    @staticmethod
    def _extract_state_markers(raw_state: object) -> tuple[int, str]:
        """Extract ``(state_version, screen)`` from raw MCP state payloads."""
        payload = raw_state.get("data", raw_state) if isinstance(raw_state, dict) else {}
        if not isinstance(payload, dict):
            return 0, ""
        return payload.get("state_version", 0), payload.get("screen", "")

    def _log_perf_duration(
        self,
        stage: str,
        started_at: float,
        *,
        step: int | None = None,
        **details: object,
    ) -> None:
        """Emit a runtime timing event when session logging is active."""
        if self._session_logger is None:
            return
        perf_step = self._current_step if step is None else step
        self._session_logger.log_perf(
            stage,
            (time.monotonic() - started_at) * 1000,
            step=perf_step if perf_step > 0 else None,
            **details,
        )

    @staticmethod
    def _decision_action_name(decision: Decision | None) -> str:
        """Return the MCP action name from a Decision payload."""
        if decision is None or not isinstance(decision.action, dict):
            return ""
        action_name = decision.action.get("action", "")
        return action_name if isinstance(action_name, str) else ""

    def _post_decision_delay_seconds(self, decision: Decision) -> float:
        """Return the cooldown to apply after a successful decision."""
        action_name = self._decision_action_name(decision)
        if action_name in {"end_turn", "choose_map_node", "buy_relic"}:
            return 0.0
        return config.ACTION_DELAY

    async def _wait_for_play_phase_timed(self, *, reason: str) -> None:
        """Wait for player control to return and log the wall-clock cost."""
        started_at = time.monotonic()
        try:
            await self._client.wait_for_play_phase()
        finally:
            self._log_perf_duration("wait.play_phase", started_at, reason=reason)

    async def _wait_for_state_change_timed(
        self,
        prev_state_type: str,
        *,
        reason: str,
        timeout: float | None = None,
    ) -> None:
        """Wait for a state transition and log the wall-clock cost."""
        started_at = time.monotonic()
        kwargs = {"timeout": timeout} if timeout is not None else {}
        try:
            await self._client.wait_for_state_change(prev_state_type, **kwargs)
        finally:
            self._log_perf_duration(
                "wait.state_change",
                started_at,
                reason=reason,
                prev_state_type=prev_state_type,
                timeout_s=timeout,
            )

    @staticmethod
    def _enemy_snapshot(gs: GameState | None) -> dict[str, tuple[int, int]]:
        """Snapshot enemy HP/block keyed by stable enemy id when available."""
        if gs is None or not gs.is_combat or not gs.enemies:
            return {}

        snap: dict[str, tuple[int, int]] = {}
        for idx, enemy in enumerate(gs.enemies):
            key = getattr(enemy, "enemy_id", "") or f"{enemy.name}:{idx}"
            snap[key] = (
                max(0, getattr(enemy, "current_hp", 0)),
                max(0, getattr(enemy, "block", 0)),
            )
        return snap

    @staticmethod
    def _state_from_action_result(result: dict | None) -> GameState | None:
        """Parse the post-action MCP state embedded by _execute(), if present."""
        if not isinstance(result, dict):
            return None
        raw_state = result.get("state")
        if not isinstance(raw_state, dict):
            return None
        try:
            return parse_state(raw_state)
        except Exception:
            return None

    @staticmethod
    def _hand_card_identity(card) -> tuple[str, str, bool]:
        """Stable-enough identity for comparing pre/post hand contents."""
        return (
            getattr(card, "card_id", "") or "",
            getattr(card, "name", "") or "",
            bool(getattr(card, "upgraded", False)),
            # Keep this nearby for future use, but do not include it in identity:
            # rules_text is a dynamic preview affected by Strength/Dex/Tender/etc.
            # getattr(card, "rules_text", "") or "",
        )

    @classmethod
    def _played_card_changed_current_hand(
        cls,
        pre_state: GameState,
        post_state: GameState | None,
        played_card,
    ) -> bool:
        """Return True when MCP shows a card play changed this turn's hand.

        A normal card play removes exactly the played card. If the post-action
        hand has extra cards, or contains identities not present in the
        expected remaining hand, the card drew/generated/transformed the hand
        and the current combat plan should be split.
        """
        if post_state is None or post_state.raw.combat is None:
            return False

        pre_hand = pre_state.hand
        post_hand = post_state.hand
        expected_count = max(0, len(pre_hand) - 1)
        if len(post_hand) > expected_count:
            return True

        expected = _Counter(cls._hand_card_identity(c) for c in pre_hand)
        played_identity = cls._hand_card_identity(played_card)
        if expected[played_identity] > 0:
            expected[played_identity] -= 1
            if expected[played_identity] <= 0:
                del expected[played_identity]

        post = _Counter(cls._hand_card_identity(c) for c in post_hand)
        return bool(post - expected)

    @classmethod
    def _plan_consumes_generated_cards(
        cls,
        pre_state: GameState,
        post_state: GameState | None,
        played_card,
        remaining_plan_actions,
    ) -> bool:
        """Return True when newly-generated cards are already queued in the plan.

        A card like Blade Dance or Cloak And Dagger generates Shivs into
        the current hand. If the agent's plan already queued enough Shiv
        plays to consume every generated card, the hand change was
        anticipated and no re-plan is needed — avoids the replan-every-
        Shiv-generator thrash the user reported.

        Counts generated cards by normalized name (case-insensitive,
        stripped upgrade marker) and compares against the remaining plan
        card plays by the same key.
        """
        if post_state is None or post_state.raw.combat is None:
            return False

        expected = _Counter(cls._hand_card_identity(c) for c in pre_state.hand)
        played_identity = cls._hand_card_identity(played_card)
        if expected[played_identity] > 0:
            expected[played_identity] -= 1
            if expected[played_identity] <= 0:
                del expected[played_identity]
        post = _Counter(cls._hand_card_identity(c) for c in post_state.hand)
        added = post - expected
        if not added:
            return False

        remaining_by_name: dict[str, int] = {}
        for a in remaining_plan_actions:
            if getattr(a, "is_potion", False):
                continue
            name = (getattr(a, "card_name", "") or "").strip().lower().rstrip("+")
            if not name:
                continue
            remaining_by_name[name] = remaining_by_name.get(name, 0) + 1

        mismatches: list[str] = []
        # Copy so we can mutate while iterating and still log the original
        # remaining-plan snapshot at the end.
        remaining_mut = dict(remaining_by_name)
        for identity, count in added.items():
            # identity = (card_id, name, upgraded, rules_text)
            added_name = str(identity[1] or "").strip().lower().rstrip("+")
            if not added_name:
                mismatches.append(f"unnamed-generated×{count}")
                continue
            available = remaining_mut.get(added_name, 0)
            if available < count:
                mismatches.append(
                    f"{added_name}: need≥{count}, plan has {available}"
                )
                continue
            remaining_mut[added_name] = available - count

        if mismatches:
            # Diagnostic: helps explain why a generated-card play still
            # triggered a replan. Keeps a single INFO line.
            logger.info(
                "Plan-anticipated check FAILED for '%s': generated=%s; remaining_plan=%s; mismatches=%s",
                getattr(played_card, "name", "?"),
                {str(i[1]): c for i, c in added.items()},
                remaining_by_name,
                mismatches,
            )
            return False

        return True

    def _trigger_replan(
        self,
        kind: str,
        desc: str,
        *,
        gs_after: GameState,
    ) -> None:
        """Centralised handler for "discard remaining plan and re-plan".

        Every trigger site (enemy death, hand change, future ones) MUST call
        this so the four side-effects stay in lock-step:
          1. set the structured trigger label  -> ``_replan_trigger_kind``
          2. set the prompt-facing trigger phrase -> ``_replan_trigger_desc``
          3. flush the buffered round actions into the conversation so the
             replan sees what was already played this turn
          4. snapshot the current plan into ``_prev_combat_plan`` and clear
             ``_combat_plan`` so the next loop iteration enters the planner
        """
        self._replan_trigger_kind = kind
        self._replan_trigger_desc = desc
        if self._v2_combat_conversation and self._v2_round_actions:
            self._v2_combat_conversation.add_execution_result(
                self._v2_round_actions, gs_after,
            )
            self._v2_round_actions = []
        self._prev_combat_plan = self._combat_plan
        self._combat_plan = None

    def _record_combat_action_metrics(
        self,
        pre_state: GameState | None,
        post_state: GameState | None,
    ) -> None:
        """Record per-action combat deltas into short-term memory."""
        stm = self._hcm_short_term()
        if stm is None:
            return
        if not (
            (pre_state is not None and pre_state.is_combat)
            or (post_state is not None and post_state.is_combat)
        ):
            return

        pre_enemies = self._enemy_snapshot(pre_state)
        post_enemies = self._enemy_snapshot(post_state)
        # Skip when post_state has no enemies (e.g. card_select mid-combat)
        # — using default (0,0) would count all pre_hp as damage dealt.
        if pre_enemies and not post_enemies:
            return
        damage_dealt = 0
        for key, (pre_hp, _pre_block) in pre_enemies.items():
            post_hp = post_enemies.get(key, (0, 0))[0]
            damage_dealt += max(0, pre_hp - post_hp)

        pre_block = (
            pre_state.combat.player.block
            if pre_state is not None and pre_state.is_combat and pre_state.combat
            else 0
        )
        post_block = (
            post_state.combat.player.block
            if post_state is not None and post_state.is_combat and post_state.combat
            else 0
        )
        block_gained = max(0, post_block - pre_block)
        hp_after = post_state.player_hp if post_state is not None else None

        stm.record_combat_metrics(
            damage_dealt=damage_dealt,
            block_gained=block_gained,
            hp_after=hp_after,
        )

    def _record_combat_delta(
        self,
        pre_state: GameState | None,
        post_state: GameState | None,
        action_name: str = "",
        delta_source: str | None = None,
        delta_target: str | None = None,
    ) -> None:
        """Record fine-grained per-action combat delta from pre/post state diff."""
        stm = self._hcm_short_term()
        if stm is None or pre_state is None or post_state is None:
            return

        # Broad combat check: raw.combat present in EITHER state
        # Covers hand_select/card_select mid-combat and combat→reward transitions
        pre_has_combat = pre_state.raw.combat is not None
        post_has_combat = post_state.raw.combat is not None
        if not pre_has_combat and not post_has_combat:
            return

        event_type = _ACTION_TO_EVENT_TYPE.get(action_name)
        if event_type is None:
            return

        try:
            from src.memory.combat_delta import compute_combat_delta
            delta = compute_combat_delta(
                pre_state, post_state, event_type,
                delta_source or action_name, delta_target,
            )
            if delta is not None:
                stm.record_combat_delta(delta)
        except Exception:
            logger.debug("Combat delta recording failed", exc_info=True)

    @staticmethod
    def _resolve_delta_target(gs: GameState, target_index: int | None) -> str | None:
        """Look up enemy display name by target index for delta recording."""
        if target_index is None:
            return None
        for e in gs.enemies:
            if e.index == target_index:
                return f"{e.name}[{target_index}]"
        return None


    @staticmethod
    def _pick_potion_to_discard(gs: GameState):
        """Choose a discardable potion slot when discard is the only exit."""
        discardable = [
            potion
            for potion in gs.potions
            if getattr(potion, "occupied", False) and getattr(potion, "can_discard", False)
        ]
        if not discardable:
            return None

        # Prefer potions that cannot currently be used, then keep slot order stable.
        discardable.sort(
            key=lambda potion: (
                bool(getattr(potion, "can_use", False)),
                getattr(potion, "index", 0),
            )
        )
        return discardable[0]

    @staticmethod
    def _is_foul_potion(potion: object) -> bool:
        """Return True for the event potion that can be sold to the merchant."""
        potion_id = (getattr(potion, "potion_id", "") or "").strip().upper()
        if potion_id == _FOUL_POTION_ID:
            return True

        name = (getattr(potion, "name", "") or "").strip().lower()
        if name == _FOUL_POTION_NAME:
            return True

        description = strip_bbcode(getattr(potion, "description", "") or "").lower()
        return "merchant" in description and "100" in description and "gold" in description

    @classmethod
    def _find_shop_foul_potion(cls, gs: GameState):
        """Return a usable Foul Potion before opening the merchant inventory."""
        for potion in gs.potions:
            if not getattr(potion, "occupied", False):
                continue
            if not getattr(potion, "can_use", False):
                continue
            if cls._is_foul_potion(potion):
                return potion
        return None

    async def _handle_shop_foul_potion(self, gs: GameState) -> Decision | None:
        """Throw Foul Potion at the merchant, then auto-open the shop if applicable."""
        if (
            gs.state_type != "shop"
            or not gs.shop
            or gs.shop.is_open
            or self._shop_pending_leave
            or "use_potion" not in gs.available_actions
        ):
            return None

        current_state = gs
        used_count = 0
        total_gold_gained = 0
        last_action: dict | None = None

        while True:
            potion = self._find_shop_foul_potion(current_state)
            if potion is None:
                break

            action = actions.use_potion(potion.index)
            result = await self._execute(
                action,
                delta_source=potion.name or f"potion_{potion.index}",
            )
            if result is None:
                logger.warning(
                    "Merchant Foul Potion auto-use failed for slot %s; continuing with shop flow",
                    potion.index,
                )
                break

            used_count += 1
            total_gold_gained += 100
            last_action = action

            post_state: GameState | None = None
            post_raw = result.get("state") if isinstance(result, dict) else None
            if isinstance(post_raw, dict):
                try:
                    post_state = parse_state(post_raw)
                except Exception:
                    post_state = None

            if post_state is None:
                try:
                    post_state = parse_state(await self._client.get_state())
                except Exception:
                    post_state = None

            if (
                post_state is None
                or post_state.state_type != "shop"
                or not post_state.shop
                or post_state.shop.is_open
                or "use_potion" not in post_state.available_actions
            ):
                current_state = post_state
                break

            current_state = post_state

        if used_count == 0 or last_action is None:
            return None

        if (
            self._use_llm
            and self._v2_engine
            and current_state
            and current_state.state_type == "shop"
            and current_state.shop
            and not current_state.shop.is_open
            and not self._shop_auto_opened_this_visit
            and "open_shop_inventory" in current_state.available_actions
        ):
            open_action = actions.open_shop_inventory()
            open_result = await self._execute(open_action)
            if open_result is not None:
                self._shop_auto_opened_this_visit = True
                await asyncio.sleep(0.3)
                return Decision(
                    floor=gs.run.floor if gs.run else 0,
                    state_type=gs.state_type,
                    action=open_action,
                    reasoning=(
                        f"Throw {used_count} Foul Potion"
                        f"{'' if used_count == 1 else 's'} at merchant for "
                        f"{total_gold_gained} gold, then open shop"
                    ),
                    source="heuristic",
                )

        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=last_action,
            reasoning=(
                f"Throw {used_count} Foul Potion"
                f"{'' if used_count == 1 else 's'} at merchant for {total_gold_gained} gold"
            ),
            source="heuristic",
        )

    def _finalize_incomplete_run(
        self,
        gs: GameState | None,
        *,
        step: int,
        reason: str,
    ) -> None:
        """Best-effort finalization for aborted or interrupted runs."""
        if self._run_state is None or self._run_state.end_time > 0 or gs is None:
            return

        self._last_run_aborted = True
        self._run_completion_reason = "aborted"
        self._run_end_reason = reason
        self._run_state.finalize(gs, False)
        if self._session_logger is not None:
            try:
                self._session_logger.log_run_end(
                    False,
                    self._run_state.final_floor,
                    self._run_state.fitness(),
                    ascension=self._run_state.ascension,
                    completion_reason=self._run_completion_reason,
                    end_reason=reason,
                )
            except Exception:
                logger.debug("Failed to log incomplete run end", exc_info=True)

        logger.info(
            "Run finalized as incomplete at floor %d after %s (step=%d, fitness=%.1f)",
            self._run_state.final_floor,
            reason,
            step,
            self._run_state.fitness(),
        )

    def _finalize_completed_run(
        self,
        gs: GameState,
        *,
        victory: bool,
        step: int,
        reason: str,
    ) -> None:
        """Finalize a natural run end and capture structured reason metadata."""
        if self._run_state is None or self._run_state.end_time > 0:
            return

        self._last_run_aborted = False
        self._run_completion_reason = "completed"
        self._run_end_reason = reason
        self._run_state.finalize(gs, victory)
        if self._session_logger is not None:
            self._session_logger.log_run_end(
                victory,
                self._run_state.final_floor,
                self._run_state.fitness(),
                ascension=self._run_state.ascension,
                completion_reason=self._run_completion_reason,
                end_reason=reason,
            )

    async def _handle_forced_potion_discard(self, gs: GameState) -> Decision:
        """Discard a potion when this is the only action that can unblock the run."""
        potion = self._pick_potion_to_discard(gs)
        if potion is None:
            raise RuntimeError(
                "discard_potion required but no discardable potion slot was exposed"
            )

        action = actions.discard_potion(potion.index)
        result = await self._execute(action)
        if result is None:
            raise RuntimeError(
                f"discard_potion failed for slot {potion.index}; aborting to avoid dead loop"
            )

        potion_name = potion.name or f"potion_{potion.index}"
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=f"Forced potion discard: {potion_name}",
            source="heuristic",
        )

    # ── Multi-card selection helpers ─────────────────────────────

    @staticmethod
    def _parse_select_count_from_prompt(prompt: str) -> int:
        """Parse required selection count from prompt text.

        Handles prompts like "Choose [blue]2[/blue] cards to Remove"
        or "Choose 2 cards to Remove" or "Choose a card" (→ 1).
        Returns 0 for "any number" / unrecognized patterns so that
        the caller falls through to max_select.
        """
        import re
        # Strip BBCode tags first
        clean = re.sub(r"\[/?[a-zA-Z_]+\]", "", prompt)
        # "Choose any number of cards" → 0 (unlimited, defer to max_select)
        if re.search(r"[Cc]hoose\s+any\s+number", clean):
            return 0
        # Look for "Choose N ... card" pattern (N may be followed by adjectives like "Common")
        m = re.search(r"[Cc]hoose\s+(\d+)\s+\w*\s*[Cc]ard", clean)
        if m:
            return int(m.group(1))
        # "Choose a card" → 1
        if re.search(r"[Cc]hoose\s+a\s+card", clean):
            return 1
        return 0

    def _reset_card_select_tracking(self) -> None:
        """Reset multi-card selection counter (call on state change away from card_select)."""
        self._card_select_target = 0
        self._card_select_progress = 0
        self._card_select_selected.clear()
        self._pack_selection_key = None
        self._pack_last_clicked_option = None
        self._pack_previews.clear()

    def _pack_selection_session_key(self, gs: GameState) -> tuple[str, ...] | None:
        selection = gs.selection
        if not selection or not selection.cards:
            return None
        prompt = strip_bbcode(selection.prompt or "").strip().lower()
        option_names = tuple(f"{card.index}:{card.name}" for card in selection.cards)
        return (
            gs.raw.run_id,
            selection.kind or "",
            prompt,
            *option_names,
        )

    def _sync_pack_selection_session(self, gs: GameState) -> None:
        key = self._pack_selection_session_key(gs)
        if key is None:
            self._pack_selection_key = None
            self._pack_last_clicked_option = None
            self._pack_previews.clear()
            return
        if self._pack_selection_key != key:
            self._pack_selection_key = key
            self._pack_last_clicked_option = None
            self._pack_previews.clear()

    def _is_pack_selection(self, gs: GameState) -> bool:
        selection = gs.selection
        if gs.state_type != "card_select" or not selection or not selection.cards:
            return False
        kind = (selection.kind or "").lower()
        prompt = strip_bbcode(selection.prompt or "").lower()
        if "pack" in kind or "bundle" in kind:
            return True
        return "pack" in prompt or "bundle" in prompt

    def _record_pack_preview_from_selection(self, gs: GameState) -> None:
        if not self._is_pack_selection(gs):
            return
        self._sync_pack_selection_session(gs)
        selection = gs.selection
        if (
            selection is None
            or not getattr(selection, "preview_cards", None)
            or self._pack_last_clicked_option is None
        ):
            return
        # Selection.preview_cards can lag one click behind the currently highlighted
        # bundle. Keep the first captured preview unless a fresher source overrides it.
        if self._pack_last_clicked_option not in self._pack_previews:
            self._pack_previews[self._pack_last_clicked_option] = list(selection.preview_cards)

    def _record_pack_preview_from_raw_state(
        self,
        option_index: int | None,
        raw_state: dict | None,
        *,
        overwrite: bool = False,
    ) -> None:
        if option_index is None or not isinstance(raw_state, dict):
            return
        try:
            gs = parse_state(raw_state)
        except StateParseError:
            return

        preview_cards = []
        if gs.cards_view and gs.cards_view.cards:
            preview_cards = list(gs.cards_view.cards)
        elif self._is_pack_selection(gs) and gs.selection and gs.selection.preview_cards:
            preview_cards = list(gs.selection.preview_cards)

        if not preview_cards:
            return
        if not overwrite and option_index in self._pack_previews:
            return
        self._pack_previews[option_index] = preview_cards

    def _all_pack_previews_collected(self, gs: GameState) -> bool:
        selection = gs.selection
        if not selection or not selection.cards:
            return False
        option_indices = {card.index for card in selection.cards}
        return bool(option_indices) and option_indices.issubset(self._pack_previews.keys())

    async def _handle_pack_selection_preview(self, gs: GameState) -> Decision | None:
        if not self._is_pack_selection(gs) or not gs.selection or not gs.selection.cards:
            return None

        self._sync_pack_selection_session(gs)
        self._record_pack_preview_from_selection(gs)
        remaining = [card for card in gs.selection.cards if card.index not in self._pack_previews]
        if not remaining:
            return None

        next_pack = remaining[0]
        action = actions.select_deck_card(next_pack.index)
        result = await self._execute(action, delta_source=next_pack.name)
        if isinstance(result, dict):
            self._record_pack_preview_from_raw_state(
                next_pack.index,
                result.get("state"),
                overwrite=True,
            )
        self._pack_last_clicked_option = next_pack.index
        self._card_select_selected.clear()
        self._card_select_progress = 0
        self._card_select_target = 0
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=(
                f"Preview pack {next_pack.name} "
                f"({len(self._pack_previews) + 1}/{len(gs.selection.cards)})"
            ),
            source="heuristic",
        )

    async def _handle_cards_view(self, gs: GameState) -> Decision | None:
        cards_view = gs.cards_view
        if cards_view and self._pack_last_clicked_option is not None and cards_view.cards:
            self._pack_previews[self._pack_last_clicked_option] = list(cards_view.cards)

        if "close_cards_view" in gs.available_actions:
            action = actions.close_cards_view()
            reasoning = "Close cards view"
        elif "confirm_selection" in gs.available_actions:
            action = actions.confirm_selection()
            reasoning = "Confirm cards view"
        elif gs.can_proceed:
            # Some event result screens (for example Darv -> Pandora's Box) reuse
            # CARDS_VIEW but expose only a proceed button instead of BackButton.
            action = actions.proceed()
            reasoning = "Proceed from cards view"
        elif "cancel_selection" in gs.available_actions:
            action = actions.cancel_selection()
            reasoning = "Cancel cards view"
        else:
            logger.warning(
                "Cards view has no supported exit action (title=%s, actions=%s)",
                getattr(cards_view, "title", ""),
                gs.available_actions,
            )
            return None

        await self._execute(action)
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=reasoning,
            source="heuristic",
        )

    @staticmethod
    def _payload_has_field(payload: object | None, field_name: str) -> bool:
        """Whether a parsed payload explicitly contained a given field."""
        if payload is None:
            return False
        fields_set = getattr(payload, "model_fields_set", None)
        if isinstance(fields_set, set):
            return field_name in fields_set
        return hasattr(payload, field_name)

    @staticmethod
    def _selection_cards(selection: object | None) -> list:
        """Return all cards exposed on a selection payload."""
        if selection is None:
            return []
        return list(getattr(selection, "cards", None) or [])

    @classmethod
    def _selection_selected_cards(cls, selection: object | None) -> list:
        """Return cards currently marked as already selected."""
        if selection is None:
            return []
        if cls._payload_has_field(selection, "selected_cards"):
            return list(getattr(selection, "selected_cards", None) or [])
        cards = cls._selection_cards(selection)
        return [card for card in cards if getattr(card, "is_selected", False)]

    @classmethod
    def _selection_selectable_cards(cls, selection: object | None) -> list:
        """Return cards that remain clickable in the current selection state."""
        if selection is None:
            return []
        if cls._payload_has_field(selection, "selectable_cards"):
            return list(getattr(selection, "selectable_cards", None) or [])
        cards = cls._selection_cards(selection)
        flagged = [card for card in cards if getattr(card, "is_selectable", True)]
        if len(flagged) != len(cards) or any(getattr(card, "is_selected", False) for card in cards):
            return flagged
        return cards

    @staticmethod
    def _selection_selected_count(selection: object | None) -> int:
        """Best-effort count of cards currently selected in the upstream UI."""
        if selection is None:
            return 0
        raw_count = getattr(selection, "selected_count", 0)
        try:
            parsed = max(int(raw_count or 0), 0)
        except (TypeError, ValueError):
            parsed = 0
        return max(parsed, len(AgentLoop._selection_selected_cards(selection)))

    @classmethod
    def _selection_indices_are_stable(cls, gs: GameState | None) -> bool:
        """Whether selection indices remain tied to the same cards across picks.

        Retain-style selections (combat_hand_select) REMOVE the selected card
        from the payload and re-index the remaining cards, so indices are NOT
        stable despite being a hand-select variant.  Only true hand_select
        (discard from hand) keeps indices stable because selected cards stay
        in the list with ``is_selected=True``.
        """
        if gs is None or gs.selection is None:
            return False
        kind = (getattr(gs.selection, "kind", "") or "").lower()
        # Retain selections remove picked cards → indices shift.
        if "combat_hand_select" in kind:
            # Check: if selected_count > 0 but selected_cards is empty,
            # the game removes picked cards from the list → unstable indices.
            sel_count = getattr(gs.selection, "selected_count", 0) or 0
            if sel_count > 0 and not cls._selection_selected_cards(gs.selection):
                return False
            # Before any pick, assume stable; after first pick we'll detect.
            return True
        if gs.state_type == "hand_select":
            return True
        if "combat_hand" in kind:
            return True
        return False

    def _selection_session_progress(self, selection: object | None = None) -> int:
        """Return the best-known pick count for the current selection session."""
        upstream = self._selection_selected_count(selection)
        current_progress = getattr(self, "_card_select_progress", 0)
        if upstream > current_progress:
            self._card_select_progress = upstream
            current_progress = upstream
        return max(current_progress, upstream)

    def _selection_has_choice_made(self, selection: object | None) -> bool:
        """Whether either the game UI or our local tracker shows a chosen card."""
        return (
            self._selection_selected_count(selection) > 0
            or getattr(self, "_card_select_progress", 0) > 0
            or bool(self._card_select_selected)
        )

    def _record_selection_choice(self, gs: GameState | None, option_index: int | None) -> int:
        """Record one successful card pick in the current selection session."""
        current = self._selection_session_progress(getattr(gs, "selection", None) if gs else None)
        self._card_select_progress = max(getattr(self, "_card_select_progress", 0), current + 1)
        if option_index is not None and self._selection_indices_are_stable(gs):
            self._card_select_selected.add(option_index)
        return self._card_select_progress

    def _resolve_selection_choice(
        self,
        gs: GameState,
        requested: SelectionCardSpec,
    ) -> tuple[int | None, str]:
        """Resolve the next requested pick against the latest selection payload."""
        selection = gs.selection
        cards = self._selection_selectable_cards(selection)
        if not cards:
            return requested.requested_index, requested.name

        indices_stable = self._selection_indices_are_stable(gs)
        excluded = self._card_select_selected if indices_stable else set()
        if indices_stable and requested.requested_index is not None:
            for card in cards:
                if card.index == requested.requested_index and card.index not in excluded:
                    return card.index, card.name

        for card in cards:
            if getattr(card, "index", None) in excluded:
                continue
            if self._selection_card_matches_spec(requested, card):
                return card.index, card.name

        if requested.name:
            resolved = self._resolve_discard_name(
                requested.name,
                cards,
                excluded_indices=excluded,
            )
            if resolved is not None:
                return resolved.index, resolved.name

        if (
            requested.requested_index is not None
            and not requested.stable_id
            and not requested.card_id
            and not requested.name
        ):
            for card in cards:
                if card.index == requested.requested_index:
                    return card.index, card.name

        return None, requested.name

    async def _refresh_selection_state(self) -> GameState | None:
        """Best-effort re-poll of the current selection state.

        Useful after a selection click because upstream may re-index the
        remaining options before the next click.
        """
        try:
            raw = await self._client.get_state()
            fresh = parse_state(raw)
        except Exception:
            return None
        if fresh.state_type not in ("card_select", "hand_select") or not fresh.selection:
            return None
        return fresh

    async def _wait_for_post_shop_relic_transition(
        self,
        gs: GameState,
        option_index: int | None,
    ) -> None:
        """Give follow-up relic screens time to replace the shop before the next LLM call."""
        if gs.state_type != "shop" or not gs.shop or option_index is None:
            return

        relic = next((r for r in gs.shop.relics if r.index == option_index), None)
        if relic is None:
            started_at = time.monotonic()
            await asyncio.sleep(0.3)
            self._log_perf_duration(
                "wait.shop_relic_transition",
                started_at,
                reason="missing_relic",
            )
            return

        relic_name = (relic.name or "").strip()
        timeout = _SHOP_RELIC_TRANSITION_TIMEOUTS.get(relic_name.lower())
        if timeout is None:
            started_at = time.monotonic()
            await asyncio.sleep(0.3)
            self._log_perf_duration(
                "wait.shop_relic_transition",
                started_at,
                reason="default_cooldown",
                relic_name=relic_name or None,
            )
            return

        try:
            await self._wait_for_state_change_timed(
                "shop",
                timeout=timeout,
                reason=f"shop_relic:{relic_name}",
            )
            logger.info(
                "Detected post-purchase screen transition for shop relic '%s'",
                relic_name,
            )
        except McpTimeout:
            logger.warning(
                "Shop relic '%s' stayed on shop screen past %.1fs; continuing with next poll",
                relic_name,
                timeout,
            )

    @staticmethod
    def _selection_specs_from_indices(
        selection: object | None,
        raw_indices: object,
    ) -> list[SelectionCardSpec]:
        """Capture the originally intended selection cards from the current UI."""
        if selection is None or not isinstance(raw_indices, list):
            return []
        card_map = {
            getattr(card, "index", None): card
            for card in AgentLoop._selection_selectable_cards(selection)
        }
        specs: list[SelectionCardSpec] = []
        for raw_idx in raw_indices:
            idx = AgentLoop._safe_int(raw_idx)
            if idx is None:
                continue
            card = card_map.get(idx)
            specs.append(
                SelectionCardSpec(
                    requested_index=idx,
                    stable_id=getattr(card, "stable_id", "") if card is not None else "",
                    card_id=getattr(card, "card_id", "") if card is not None else "",
                    name=getattr(card, "name", "") if card is not None else "",
                    upgraded=bool(getattr(card, "upgraded", False)) if card is not None else False,
                )
            )
        return specs

    @staticmethod
    def _selection_card_matches_spec(spec: SelectionCardSpec, card: object) -> bool:
        """Match a live selection card to the originally requested target."""
        card_stable_id = (getattr(card, "stable_id", "") or "").strip()
        if spec.stable_id:
            return bool(card_stable_id) and spec.stable_id == card_stable_id

        card_id = (getattr(card, "card_id", "") or "").strip().lower()
        if spec.card_id and card_id and spec.card_id.lower() == card_id:
            return bool(getattr(card, "upgraded", False)) == spec.upgraded

        requested_name = (spec.name or "").strip().lower()
        if not requested_name:
            return False
        card_name = (getattr(card, "name", "") or "").strip().lower()
        if requested_name == card_name:
            return True
        return requested_name.rstrip("+") == card_name.rstrip("+")

    @staticmethod
    def _resolve_usable_potion_index(gs: GameState, planned: PlannedAction) -> int | None:
        """Resolve a planned potion by slot first, then by name if the slot is missing."""
        usable_potions = [p for p in gs.potions if p.can_use]
        usable_indices = {p.index for p in usable_potions}
        if planned.potion_index in usable_indices:
            return planned.potion_index

        planned_name = (planned.potion_name or "").strip().lower()
        if not planned_name:
            return planned.potion_index

        exact = [
            p.index
            for p in usable_potions
            if (p.name or "").strip().lower() == planned_name
        ]
        if exact:
            return exact[0]

        fuzzy = [
            p.index
            for p in usable_potions
            if planned_name in (p.name or "").strip().lower()
            or (p.name or "").strip().lower() in planned_name
        ]
        if fuzzy:
            return fuzzy[0]

        return planned.potion_index

    @staticmethod
    def _normalize_discard_specs(discard_spec: object) -> list[str]:
        """Normalize a planned discard field to a flat list of card names."""
        if isinstance(discard_spec, str):
            spec = discard_spec.strip()
            return [spec] if spec else []

        if isinstance(discard_spec, list | tuple):
            normalized: list[str] = []
            for item in discard_spec:
                spec = str(item).strip()
                if spec:
                    normalized.append(spec)
            return normalized

        return []

    @staticmethod
    def _resolve_discard_name(
        discard_spec: str,
        sel_cards: list,
        *,
        excluded_indices: set[int] | None = None,
    ) -> object | None:
        """Resolve planned discard name to card in selection. 3-tier: exact > base > substring."""
        excluded = excluded_indices or set()
        spec_lower = discard_spec.lower().strip()
        spec_base = spec_lower.rstrip("+")

        # Tier 1: exact match
        for c in sel_cards:
            if getattr(c, "index", None) in excluded:
                continue
            if c.name.lower() == spec_lower:
                return c

        # Tier 2: base name match (strip +/++ from both)
        for c in sel_cards:
            if getattr(c, "index", None) in excluded:
                continue
            if c.name.lower().rstrip("+") == spec_base:
                return c

        # Tier 3: substring match
        for c in sel_cards:
            if getattr(c, "index", None) in excluded:
                continue
            if spec_base in c.name.lower():
                return c

        return None

    # ── Target resolution ────────────────────────────────────────

    # _resolve_target_index and _translate_llm_action removed.
    # LLM now outputs target_index (int) and upstream action names directly.

    @staticmethod
    def _poison_kills_all_enemies(gs) -> bool:
        """Check if poison ticks at start of enemy turn will kill all enemies.

        In STS2, poison deals damage equal to stacks at the start of the
        enemy's turn, then decreases by 1. If poison >= enemy HP (after
        accounting for block), the enemy will die from poison alone.
        """
        if not gs.enemies:
            return False
        for e in gs.enemies:
            if not e.is_alive:
                continue
            poison = 0
            for p in (e.powers or []):
                if p.name and p.name.lower() == "poison":
                    poison = p.amount or 0
                    break
            effective_hp = e.current_hp + (e.block or 0)
            if poison < effective_hp:
                return False  # This enemy survives poison
        return True  # All alive enemies will die from poison

    @staticmethod
    def _classify_map_node(node) -> str:
        """Classify a map node as monster/elite/boss from its metadata.

        Returns "" for fog-of-war (Unknown) nodes so the caller can fall
        back to encounter-based detection once combat actually starts.
        """
        nt = node.node_type.lower() if hasattr(node, "node_type") else ""
        is_boss = getattr(node, "is_boss", False)
        is_second_boss = getattr(node, "is_second_boss", False)
        if "boss" in nt or is_boss or is_second_boss:
            return "boss"
        if nt == "elite":
            return "elite"
        if nt in ("unknown", ""):
            return ""  # fog-of-war — defer to encounter lookup at combat start
        return "monster"

    def _resolve_combat_type(self, gs: GameState) -> str:
        """Resolve combat type using upstream metadata, cache, lookup, or state_type.

        Priority:
        1. Upstream-native combat_type metadata from the mod
        2. Cached map node type (set at node selection, authoritative when available)
        3. Boss-floor fallback (combat on floor 17/34/51 is always a boss)
        4. Encounter knowledge lookup by enemy names (handles fog-of-war nodes)
        5. gs.state_type fallback (tries map data, defaults to 'monster')
        """
        if gs.combat_type:
            self._cached_map_node_type = gs.combat_type
            return gs.combat_type

        if self._cached_map_node_type:
            return self._cached_map_node_type

        if gs.is_combat and gs.floor in (17, 34, 51):
            self._cached_map_node_type = "boss"
            return "boss"

        # Try encounter lookup by enemy names
        if self._knowledge and gs.combat and gs.combat.enemies:
            enemy_names = {e.name for e in gs.combat.enemies if e.name}
            if enemy_names:
                enc = self._knowledge.encounters.get_by_enemy_names(enemy_names)
                if enc and enc.room_type:
                    resolved = enc.room_type.lower()
                    logger.info(
                        "Combat type resolved via encounter lookup: %s (enemies: %s)",
                        resolved, enemy_names,
                    )
                    # Cache the resolved type for rest of combat
                    self._cached_map_node_type = resolved
                    return resolved

        return gs.state_type

    def _resolve_combat_type_for_logging(self, gs: GameState) -> str | None:
        """Resolve combat type for state/transition logs without leaking stale combat cache.

        ``_last_combat_type`` is authoritative once we are already inside an ongoing
        combat, but it can still refer to the previous fight on the very first poll of
        a new encounter (before the state machine emits ``COMBAT_START``). In that case
        we must re-resolve from the current state so monitor events do not show a stale
        ``monster``/``elite``/``boss`` label.
        """
        if not gs.is_combat:
            return None
        if gs.combat_type:
            return gs.combat_type
        if self._state_machine.in_combat and self._last_combat_type:
            return self._last_combat_type
        return self._resolve_combat_type(gs)

    @staticmethod
    def _init_knowledge():
        """Initialize game knowledge database."""
        try:
            from src.knowledge.knowledge import GameKnowledge
            return GameKnowledge.get_instance()
        except Exception as exc:
            logger.warning("Game knowledge failed to initialize: %s", exc)
            return None

    @staticmethod
    def _init_web_searcher():
        """Initialize Anthropic-only web searcher when that runtime is active."""
        if not config.WEB_SEARCH_ENABLED or config.LLM_PROVIDER != "anthropic":
            return None
        try:
            from src.knowledge.web_searcher import WebSearcher
            return WebSearcher()
        except Exception as exc:
            logger.warning("Web searcher failed to initialize: %s", exc)
            return None

    async def _fetch_boss_strategy_bg(self, boss_name: str, character: str) -> None:
        """Background task: fetch boss strategy via web search.

        Result stored in self._boss_strategy and injected into subsequent
        combat plan prompts. Non-blocking — first round uses seed boss skills.
        """
        try:
            from src.knowledge.web_searcher import WebSearcher
            raw = await asyncio.to_thread(
                self._web_searcher.search_boss_strategy, boss_name, character,
            )
            if raw:
                formatted = WebSearcher.format_boss_strategy(raw)
                if formatted:
                    self._boss_strategy = formatted
                    logger.info(
                        "Background: boss strategy fetched for %s vs %s (%d chars)",
                        boss_name, character, len(formatted),
                    )
        except Exception as e:
            logger.warning("Background boss strategy failed for %s: %s", boss_name, e)

    def _query_knowledge(self, gs: GameState) -> str:
        """Query game knowledge for prompt injection.

        Returns knowledge section text, or "" if not available.
        """
        if not self._knowledge:
            return ""
        try:
            from src.knowledge.injector import (
                inject_combat_knowledge,
                inject_event_knowledge,
                inject_reward_knowledge,
            )

            if gs.is_combat:
                return inject_combat_knowledge(gs, self._knowledge)

            if gs.state_type == "card_reward" and gs.reward and gs.reward.pending_card_choice:
                names = [c.name for c in gs.reward.card_options]
                return inject_reward_knowledge(names, self._knowledge)

            if gs.state_type == "shop" and gs.shop:
                names = [c.name for c in gs.shop.cards]
                return inject_reward_knowledge(names, self._knowledge)

            if gs.state_type == "event" and gs.event:
                return inject_event_knowledge(gs.event.event_id, self._knowledge)

            if gs.state_type == "card_select" and gs.selection:
                names = [c.name for c in self._selection_selectable_cards(gs.selection)]
                return inject_reward_knowledge(names, self._knowledge)

        except Exception:
            logger.warning("Knowledge query failed", exc_info=True)
        return ""

    def _init_skill_library(self):
        """Initialize skill library: load persisted + merge seeds (or skip seeds for Mode B / baseline)."""
        try:
            from src.skills.library import SkillLibrary

            # Load persisted skills (from previous runs)
            skill_path = paths.skills_file()
            library = SkillLibrary.load(skill_path)

            # Mode B / baseline: skip expert seed loading. Mode B then loads
            # character-parametric stubs lazily once the character is known
            # (see _lazy_load_seed_stubs).
            if config.DISABLE_SKILL_SEEDS:
                logger.info(
                    "DISABLE_SKILL_SEEDS=true — skipping expert seed dir; "
                    "library carries persisted skills only (count=%d)",
                    library.count,
                )
                return library

            # Default: merge seed skills (only adds new ones, preserves runtime updates)
            seed_dir = Path(config.SKILLS_SEED_DIR)
            seeds = SkillLibrary.load_seeds(seed_dir)
            added = library.merge_seeds(seeds)
            if added > 0:
                logger.info("Merged %d new seed skills", added)

            logger.info("Skill library: %s", library.stats())
            return library
        except Exception as exc:
            logger.warning("Skill library failed to initialize: %s", exc)
            return None

    def _lazy_load_seed_stubs(self, character: str) -> None:
        """Load Mode B seed stub templates for a character (idempotent).

        Called the first time the agent observes a concrete character from the
        game state. No-op unless ``USE_SEED_STUBS=true``. Safe to call repeatedly
        — ``SkillLibrary.load_seed_stubs`` skips already-loaded ids.

        Spec: docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md
        """
        if not config.USE_SEED_STUBS:
            return
        if getattr(self, "_skill_library", None) is None:
            return
        if not character:
            return
        try:
            from pathlib import Path as _Path
            stub_dir = _Path(config.SEED_STUB_DIR)
            n = self._skill_library.load_seed_stubs(stub_dir, character=character)
            if n > 0:
                logger.info(
                    "Mode B: loaded %d seed stubs for character=%s", n, character,
                )
        except Exception:
            logger.warning("Mode B: seed stub lazy-load failed", exc_info=True)

    @staticmethod
    def _load_counter(name: str) -> int:
        """Load a persisted counter from data dir (survives process restarts)."""
        path = Path(config.DATA_DIR) / f"{name}_counter.json"
        if path.exists():
            try:
                import json
                data = json.loads(path.read_text(encoding="utf-8"))
                return int(data.get("count", 0))
            except Exception:
                pass
        return 0

    @staticmethod
    def _save_counter(name: str, value: int) -> None:
        """Persist a counter to data dir."""
        import json
        path = Path(config.DATA_DIR) / f"{name}_counter.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"count": value}), encoding="utf-8")

    def _accumulate_card_rules(self, gs: GameState) -> None:
        """Capture every card's runtime rules_text into self._seen_card_rules.

        Walks every card-bearing payload on *gs* (deck / hand / shop / reward /
        selection) and stores ``name → stripped(resolved_rules_text or
        rules_text)``. Last-write-wins. Enables postrun build analysis to use
        the game's own text instead of a potentially-stale knowledge-base
        lookup, mirroring how relic descriptions are sourced live from the
        run payload.
        """
        def _store(card) -> None:
            name = getattr(card, "name", "") or ""
            if not name:
                return
            raw = (
                getattr(card, "resolved_rules_text", "")
                or getattr(card, "rules_text", "")
                or ""
            ).strip()
            if not raw:
                return
            cleaned = strip_bbcode(raw)
            if cleaned:
                self._seen_card_rules[name] = cleaned

        for c in gs.deck or []:
            _store(c)
        for c in gs.hand or []:
            _store(c)

        shop = gs.shop
        if shop is not None:
            for c in getattr(shop, "cards", None) or []:
                _store(c)

        reward = gs.reward
        if reward is not None:
            for c in getattr(reward, "card_options", None) or []:
                _store(c)

        selection = gs.selection
        if selection is not None:
            for bucket_name in ("cards", "selectable_cards", "preview_cards"):
                for c in getattr(selection, bucket_name, None) or []:
                    _store(c)

    def reset_for_new_run(self) -> None:
        """Reset per-run internal state so the AgentLoop can be reused."""
        self._running = False
        self._run_state = None
        self._state_machine.reset()
        self._session_logger = None
        self._session_finalized = False
        self._stuck_key = ""
        self._stuck_count = 0
        self._locked_event_fails = 0
        self._last_run_aborted = False
        self._run_completion_reason = ""
        self._run_end_reason = ""
        self._card_select_target = 0
        self._card_select_selected.clear()
        self._pack_selection_key = None
        self._pack_last_clicked_option = None
        self._pack_previews.clear()
        self._last_combat_round = -1
        self._end_turn_sent_round = -1
        self._planned_act = -1
        self._route_plan = None
        self._cached_map_node_type = ""
        self._combat_plan = None
        self._combat_plan_index = 0
        self._combat_plan_round = -1
        self._no_target_replan_round = -1
        self._prev_combat_plan = None
        self._replan_trigger_desc = ""
        self._replan_trigger_kind = ""
        self._combat_plan_alive = set()
        # Snapshot of enemy_id list at plan-creation time, positional.
        # Used to remap plan-time target_index → current index when enemies
        # die mid-plan and the mod renumbers survivors (see _remap_plan_target).
        self._combat_plan_enemy_ids: tuple[str, ...] | None = None
        self._last_played_card_name = ""
        self._last_played_card_rules = ""
        self._last_played_plan_action = None
        self._opened_card_rewards.clear()
        self._card_reward_count_before_open = None
        self._last_opened_card_index = None
        self._shop_auto_opened_this_visit = False
        self._shop_pending_leave = False
        self._shop_plan = None
        self._smith_preview_cards: list | None = None
        self._active_skill_ids.clear()
        self._combat_skill_ids.clear()
        self._noncombat_skill_ids.clear()
        self._noncombat_skill_counts = {}
        self._skill_trigger_log.clear()
        self._pending_build_mem = None
        self._pending_combat_trace = None
        self._pending_trace_candidates = []
        self._pending_skipped_cards = []
        self._prev_event_gs = None
        # Non-combat scoring reset
        self._act_heal_total = 0
        self._bosses_killed = []
        self._last_boss_entry_hp = None
        self._last_boss_heal_total = 0
        self._last_seen_act = 0
        self._last_combat_type = ""
        self._current_combat_start_hp = 0
        self._last_known_enemies = []
        # Reset runtime card-rules accumulator + deck payload cache so the
        # previous run's state cannot leak into postrun build analysis when
        # the new run's first frames arrive before gs.deck is populated
        # (character-select / menu). _cached_relics is intentionally left
        # alone — its non-reset behavior is pre-existing and relied on by
        # other call sites.
        self._seen_card_rules.clear()
        self._cached_deck_payload = []
        # Reset boss strategy
        self._boss_strategy = ""
        if self._boss_search_task and not self._boss_search_task.done():
            self._boss_search_task.cancel()
        self._boss_search_task = None
        # Reset V2 short-term memory
        if self._memory and hasattr(self._memory, "reset_short_term"):
            self._memory.reset_short_term()
        # Reset preprocessor telemetry for the new run.
        if self._tool_preprocessor:
            self._tool_preprocessor.reset()
        # Reset plan verifier telemetry for the new run.
        if self._plan_verifier:
            self._plan_verifier.reset()
        # Clear in-memory snapshots (keep disk); done before flush in post-run.
        if hasattr(self, "_snapshot_store") and self._snapshot_store:
            self._snapshot_store.clear_memory()
        # Skill eval reset
        self._skill_eval_state = "idle"
        self._eval_results = []
        self._eval_skill_sets = []
        self._eval_current_index = 0
        self._eval_original_skill_ids = []
        self._eval_combat_start_hp = 0
        self._eval_round_count = 0
        self._eval_potions_used = 0
        if self._skill_library:
            self._skill_library.clear_active_override()
        # Reset V2 architecture state
        self._v2_combat_conversation = None

    async def run(self) -> RunState:
        """Execute a full game run. Returns the accumulated RunState."""
        self._running = True
        run_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        self._run_state = RunState(run_id=run_id)
        self._state_machine.reset()
        self._session_logger = SessionLogger(run_id, event_bus=self._event_bus)
        self._run_completion_reason = ""
        self._run_end_reason = ""
        self._last_run_aborted = False
        # Tag MCP client events with current run_id for monitor
        if hasattr(self._client, "set_run_id"):
            self._client.set_run_id(run_id)
        if self._memory and hasattr(self._memory, "reload_prompt_context"):
            try:
                self._memory.reload_prompt_context()
            except Exception:
                logger.warning("Failed to reload prompt context at run start", exc_info=True)
        step = 0
        self._current_step = 0
        last_gs: GameState | None = None

        # V2: wire session logger
        if self._v2_engine is not None and hasattr(self._v2_engine, "set_session_logger"):
            self._v2_engine.set_session_logger(self._session_logger)

        logger.info("Agent loop started (run_id=%s, llm=%s)", run_id, self._use_llm)

        # Check for completed batch results from previous runs (Anthropic Batch API)
        if config.get_tier_provider("analysis") == "anthropic":
            await self._check_pending_batches()

        try:
            while self._running and step < self._max_steps:
                step += 1
                self._current_step = step
                try:
                    # 1. Observe
                    observe_get_state_started = time.monotonic()
                    raw = await self._client.get_state()
                    self._log_perf_duration("observe.get_state", observe_get_state_started, step=step)

                    observe_parse_started = time.monotonic()
                    gs = parse_state(raw)
                    self._log_perf_duration("observe.parse_state", observe_parse_started, step=step)
                    last_gs = gs

                    # Capture combat state snapshots for tool validation
                    if getattr(self, "_snapshot_store", None) and gs.is_combat:
                        self._snapshot_store.capture(gs.state_type, raw)

                    if gs.state_type != "shop":
                        self._shop_auto_opened_this_visit = False
                        self._shop_pending_leave = False
                        if self._shop_plan is None or self._shop_plan.is_complete:
                            self._shop_plan = None

                    # Reset multi-card selection tracking when leaving card_select/hand_select
                    if gs.state_type not in ("card_select", "hand_select"):
                        if (
                            self._card_select_target > 0
                            or getattr(self, "_card_select_progress", 0) > 0
                            or self._card_select_selected
                        ):
                            self._reset_card_select_tracking()

                    # Track act changes: reset per-act heal total
                    current_act = gs.act if gs.act else 0
                    if current_act != self._last_seen_act and current_act > 0:
                        if self._last_seen_act > 0:
                            self._act_heal_total = 0  # reset heal tracking per act
                            # _noncombat_skill_counts is run-level, don't reset
                        self._last_seen_act = current_act

                    # Event tracking: start/end lifecycle
                    self._track_event_lifecycle(gs)

                    # Log full state every step for post-run replay
                    combat_type_override = self._resolve_combat_type_for_logging(gs)
                    log_state_started = time.monotonic()
                    self._session_logger.log_state(
                        gs, step, combat_type_override=combat_type_override
                    )
                    self._log_perf_duration(
                        "observe.log_state",
                        log_state_started,
                        step=step,
                        state_type=gs.state_type,
                    )

                    # Track transitions
                    transition = self._state_machine.update(gs)
                    if transition != PhaseTransition.NONE:
                        self._session_logger.log_transition(
                            transition.value,
                            gs,
                            step=step,
                            combat_type_override=combat_type_override,
                        )
                        # Reset round trackers when entering new combat
                        if transition == PhaseTransition.COMBAT_START:
                            self._last_combat_round = -1
                            self._end_turn_sent_round = -1
                            self._combat_plan = None
                            self._combat_plan_index = 0
                            self._combat_plan_round = -1
                            self._no_target_replan_round = -1
                            self._prev_combat_plan = None
                            self._replan_trigger_desc = ""
                            self._replan_trigger_kind = ""
                            self._opened_card_rewards.clear()
                            self._card_reward_count_before_open = None
                            self._last_opened_card_index = None
                            self._combat_skill_ids.clear()
                            self._last_combat_type = self._resolve_combat_type(gs)
                            self._current_combat_start_hp = gs.player_hp
                            # Record HP + heal total at boss entry for end-of-run scoring
                            if self._last_combat_type == "boss":
                                self._last_boss_entry_hp = gs.player_hp
                                self._last_boss_heal_total = self._act_heal_total
                            # V2: start combat tracking in short-term memory
                            self._hcm_start_combat(gs)
                            # V2 architecture: start combat conversation
                            if self._v2_engine:
                                try:
                                    self._v2_combat_conversation = self._maybe_create_combat_conversation(gs)
                                    # Build strategic context for combat start
                                    strategic_parts: list[str] = []
                                    ctx = self._build_decision_context(gs)
                                    if ctx.get("skill_context"):
                                        strategic_parts.append(ctx["skill_context"])
                                    wc = ctx.get("working_context")
                                    if wc is not None:
                                        from dataclasses import replace as dc_replace

                                        from src.memory.prompt_injector import (
                                            format_working_context,
                                        )
                                        # Strip short_term_hints to avoid duplicate Strategic Thread
                                        # (STM thread already injected via add_combat_start's strategic_thread param)
                                        wc_no_thread = dc_replace(wc, short_term_hints=())
                                        mem_str = format_working_context(wc_no_thread)
                                        if mem_str:
                                            strategic_parts.append(mem_str)
                                    if ctx.get("boss_strategy"):
                                        strategic_parts.append(
                                            f"## Boss Strategy\n{ctx['boss_strategy']}"
                                        )
                                    strategic_context = "\n\n".join(strategic_parts)

                                    # Build potion strategy section with timing classification
                                    from src.knowledge.potion_classifier import (
                                        classify_potion,
                                        format_potion_tag,
                                    )
                                    act = gs.act if gs.act else 1
                                    floor = gs.floor if gs.floor else 0
                                    _boss_floors = {1: 17, 2: 34, 3: 51}
                                    floors_to_boss = max(0, _boss_floors.get(act, 51) - floor)
                                    prompt_combat_type = self._last_combat_type
                                    potion_strat = ""
                                    if gs.potions:
                                        pot_lines = ["## Potion Strategy"]
                                        pot_lines.append(
                                            "Fight: "
                                            f"{prompt_combat_type} | Boss: {floors_to_boss} floors away"
                                        )
                                        for p_obj in gs.potions:
                                            if not p_obj.occupied and not p_obj.can_use:
                                                continue
                                            name = p_obj.name or ""
                                            desc = p_obj.description or ""
                                            if not name:
                                                continue
                                            profile = classify_potion(name, desc)
                                            tag = format_potion_tag(
                                                profile.timing,
                                                prompt_combat_type,
                                                floors_to_boss,
                                            )
                                            pot_lines.append(f"- {name} {tag}: {strip_bbcode(desc)}")
                                        if len(pot_lines) > 2:
                                            potion_strat = "\n".join(pot_lines)

                                    if self._v2_combat_conversation is not None:
                                        # Persistent multi-turn conversation: prime with
                                        # combat-start context.  Skipped when
                                        # COMBAT_CONVERSATION_ENABLED=false (None); the
                                        # per-turn fresh conversation is built lazily in
                                        # _generate_combat_plan instead.
                                        self._v2_combat_conversation._floors_to_boss = floors_to_boss
                                        # Get strategic thread for combat context
                                        stm_thread = ""
                                        stm = self._hcm_short_term()
                                        if stm is not None:
                                            stm_thread = stm.get_strategic_thread(
                                                max_entries=7, current_context=gs.state_type,
                                            )
                                        # Build card notes for deck cards from CardMemory
                                        card_notes: dict[str, str] = {}
                                        if self._memory and getattr(self._memory, "card_memory_store", None) and self._run_state:
                                            deck_names = [c.name for c in gs.deck] if gs.deck else []
                                            memories = self._memory.card_memory_store.query_cards(
                                                self._run_state.character, deck_names,
                                            )
                                            card_notes = {m.card_name: m.note for m in memories if m.note}
                                        self._v2_combat_conversation.add_combat_start(
                                            gs,
                                            strategic_context=strategic_context,
                                            potion_strategy=potion_strat,
                                            strategic_thread=stm_thread,
                                            combat_type=self._last_combat_type,
                                            card_notes=card_notes or None,
                                        )
                                        logger.info("V2: combat conversation started")
                                except Exception as exc:
                                    logger.exception("V2 combat conversation init failed: %s", exc)
                                    self._session_logger.log_error(
                                        f"V2 combat conversation init failed: {exc}", step,
                                    )
                                    self._v2_combat_conversation = None
                            # Skill eval: activate for boss fights with untested skills
                            if (
                                config.SKILL_EVAL_ENABLED
                                and self._last_combat_type == "boss"
                                and self._skill_library
                                and self._skill_eval_state == "idle"
                            ):
                                self._try_activate_skill_eval(gs)
                        # Track combat results for run statistics
                        elif transition == PhaseTransition.COMBAT_END:
                            # If we're alive after combat, we won
                            combat_won = gs.player_hp > 0
                            self._run_state.record_combat_result(combat_won)
                            # Track boss kills for non-combat scoring
                            if combat_won and self._last_combat_type == "boss":
                                act = gs.act if gs.act else self._last_seen_act
                                if act and act not in self._bosses_killed:
                                    self._bosses_killed.append(act)
                            # Update skill confidence from combat outcome
                            if self._skill_library and self._combat_skill_ids:
                                # Discrete combat-type-aware buckets:
                                # wins get lower weights when they are costly;
                                # losses use 1.0 to apply full failure weight.
                                quality_score = self._combat_quality_score(
                                    combat_won, gs.player_hp,
                                )
                                self._skill_library.record_outcome(
                                    list(self._combat_skill_ids),
                                    combat_won,
                                    quality_score=quality_score,
                                )
                                logger.info(
                                    "Skill outcome: %s for %d skills (quality=%.2f)",
                                    "win" if combat_won else "loss",
                                    len(self._combat_skill_ids),
                                    quality_score,
                                )
                            # A4: backfill combat result into skill trigger log
                            enemy_key_str = "_".join(
                                e.name for e in (self._last_known_enemies or [])
                            ) or self._last_combat_type
                            self._update_skill_trigger_results(combat_won, enemy_key_str)
                            self._current_combat_start_hp = 0
                            self._last_known_enemies = []  # Clear stale enemy data
                            # V2: end combat tracking in short-term memory
                            self._hcm_end_combat(combat_won, gs.player_hp)
                            # Log combat summary from completed tracker
                            self._log_combat_summary(step)
                            # V2 architecture: flush final round + end conversation
                            if self._v2_combat_conversation:
                                try:
                                    # Flush last round's execution results before summary
                                    if self._v2_round_actions:
                                        self._v2_combat_conversation.add_execution_result(
                                            self._v2_round_actions, gs,
                                        )
                                        self._v2_round_actions = []
                                    summary = self._v2_combat_conversation.generate_combat_summary(
                                        final_hp=gs.player_hp,
                                        final_max_hp=gs.player_max_hp,
                                    )
                                    if summary:
                                        logger.info("V2 combat summary: %s", summary[:200])
                                except Exception:
                                    pass
                                self._v2_combat_conversation = None
                            self._last_combat_type = ""
                            # Skill eval: handle combat end during eval
                            if self._skill_eval_state == "active":
                                # Combat ended naturally (poison tick, thorns, etc.)
                                # while eval is still running — record result and
                                # save/reload if more alternative sets remain.
                                won = gs.player_hp > 0
                                await self._handle_eval_terminal(gs, won=won)
                                if self._skill_eval_state in ("active", "final"):
                                    # Save/reload succeeded — skip normal COMBAT_END
                                    # processing and re-enter the combat loop.
                                    continue
                            elif self._skill_eval_state == "final":
                                logger.info(
                                    "Skill eval: final run complete, returning to idle"
                                )
                                self._skill_eval_state = "idle"
                                if self._skill_library:
                                    self._skill_library.clear_active_override()
                                self._eval_results = []
                                self._eval_skill_sets = []
                        # V2: Track route node on floor change
                        if transition in (
                            PhaseTransition.FLOOR_CHANGE,
                            PhaseTransition.ACT_CHANGE,
                        ):
                            # End previous route node, start new one
                            self._hcm_end_route_node(gs)
                            node_type = self._resolve_combat_type(gs) if gs.is_combat else gs.state_type
                            self._hcm_start_route_node(gs, node_type)
                        logger.info("Step %d: %s [%s]", step, gs.summary(), transition.value)
                    elif step % 20 == 1:
                        logger.info("Step %d: %s", step, gs.summary())

                    # Cache relics with descriptions (available from run payload)
                    # Format: "Name (description)" when description available
                    # format_relic_hints() extracts the name before the first "("
                    if gs.relics:
                        _MAX_RELIC_DESC = 200
                        self._cached_relics = [
                            f"{strip_bbcode(r.name)} ({strip_bbcode(r.description)[:_MAX_RELIC_DESC]})"
                            if r.description else strip_bbcode(r.name)
                            for r in gs.relics
                        ]

                    # Cache deck payload for postrun build analysis (carries
                    # enchantments + resolved rules_text that the name-only
                    # reconstruction from stm.deck_events cannot preserve).
                    if gs.deck:
                        self._cached_deck_payload = list(gs.deck)

                    # Accumulate runtime card rules_text from every card-bearing
                    # payload. Last-write-wins so upgraded variants overwrite
                    # their base text once seen.
                    self._accumulate_card_rules(gs)

                    # Cache enemies from combat states (hand_select states lack combat data)
                    if gs.is_combat and gs.enemies:
                        self._last_known_enemies = list(gs.enemies)

                    stm = self._hcm_short_term()
                    if stm is not None and gs.deck:
                        stm.capture_starting_deck([c.name for c in gs.deck])

                    # Record floor snapshot
                    self._run_state.record_floor(gs)

                    # 2. Check terminal conditions
                    if gs.is_game_over or gs.is_menu:
                        victory = gs.state_type == "victory"
                        self._finalize_completed_run(
                            gs,
                            victory=victory,
                            step=step,
                            reason="victory" if victory else "defeat",
                        )
                        logger.info(
                            "Run ended: %s at floor %d (steps=%d, fitness=%.1f)",
                            "VICTORY" if victory else "DEFEAT",
                            self._run_state.final_floor,
                            step,
                            self._run_state.fitness(),
                        )
                        break

                    # Detect invalid start: game was already over when agent woke up
                    # (e.g. resumed into a dead run where HP=0 but state is not game_over)
                    if step == 1 and gs.player_hp == 0 and gs.player_max_hp > 0:
                        logger.warning(
                            "Invalid run start: HP=0 at step 1 (state=%s, floor=%d)"
                            " — skipping run without post-run processing",
                            gs.state_type,
                            gs.floor or 0,
                        )
                        self._finalize_incomplete_run(
                            gs, step=step, reason="invalid_start"
                        )
                        break

                    # Detect stuck in unknown state (run ended but not detected)
                    if gs.state_type == "unknown" and not gs.available_actions:
                        self._unknown_state_count = getattr(self, "_unknown_state_count", 0) + 1
                        if self._unknown_state_count >= 5:
                            logger.warning(
                                "Stuck in unknown state for %d steps — treating as run end",
                                self._unknown_state_count,
                            )
                            self._finalize_incomplete_run(
                                gs,
                                step=step,
                                reason="unknown_state_terminal",
                            )
                            break
                    else:
                        self._unknown_state_count = 0

                    # Detect character + load guide
                    if not self._run_state.character:
                        char = gs.character
                        if char:
                            from src.memory.models_v2 import normalize_character
                            self._run_state.character = normalize_character(char)
                            # Mode B: lazy-load character-parametric stubs now
                            # that the character is known.
                            self._lazy_load_seed_stubs(self._run_state.character)

                    # Populate actual ascension from game state (once).
                    # Use gs.raw.run to distinguish "real A0" from "no data".
                    if self._run_state.actual_ascension is None and gs.raw.run is not None:
                        self._run_state.actual_ascension = gs.ascension

                    # 3. Decide + Act
                    decide_started = time.monotonic()
                    decision = await self._decide_and_act(gs, step)
                    self._log_perf_duration(
                        "main.decide_and_act",
                        decide_started,
                        step=step,
                        state_type=gs.state_type,
                        has_decision=decision is not None,
                    )
                    if decision:
                        self._run_state.record_decision(decision)
                        self._session_logger.log_decision(decision, step)
                        # Reset stuck counter on any successful action
                        self._stuck_key = ""
                        self._stuck_count = 0
                        # Let game animations play before next action
                        delay_s = self._post_decision_delay_seconds(decision)
                        if delay_s > 0:
                            action_delay_started = time.monotonic()
                            await asyncio.sleep(delay_s)
                            self._log_perf_duration(
                                "main.action_delay",
                                action_delay_started,
                                step=step,
                                action=self._decision_action_name(decision) or None,
                                delay_s=delay_s,
                            )
                    else:
                        # Only count as "stuck" when we tried to decide but couldn't.
                        # Skip transient states: enemy turn, animations, unknown screens.
                        is_transient = (
                            (gs.is_combat and not gs.is_play_phase)
                            or gs.state_type == "unknown"
                        )
                        if is_transient:
                            transient_sleep_started = time.monotonic()
                            await asyncio.sleep(config.MCP_POLL_INTERVAL)
                            self._log_perf_duration(
                                "main.transient_poll_sleep",
                                transient_sleep_started,
                                step=step,
                                state_type=gs.state_type,
                                delay_s=config.MCP_POLL_INTERVAL,
                            )
                        else:
                            state_key = f"{gs.state_type}:{gs.run.floor if gs.run else 0}"
                            if state_key == self._stuck_key:
                                self._stuck_count += 1
                            else:
                                self._stuck_key = state_key
                                self._stuck_count = 1

                            if self._stuck_count >= STUCK_THRESHOLD:
                                logger.warning(
                                    "Stuck detected (%d repeats at %s), forcing unstick",
                                    self._stuck_count, state_key,
                                )
                                unstick = await self._force_unstick(gs)
                                if unstick:
                                    self._run_state.record_decision(unstick)
                                    self._session_logger.log_decision(unstick, step)
                                # Always reset to avoid infinite _force_unstick loop
                                self._stuck_count = 0
                                unstick_sleep_started = time.monotonic()
                                await asyncio.sleep(0.3)
                                self._log_perf_duration(
                                    "main.unstick_delay",
                                    unstick_sleep_started,
                                    step=step,
                                    delay_s=0.3,
                                )
                                continue

                except McpError as e:
                    err_str = str(e) or f"{type(e).__name__}"
                    logger.error("MCP error at step %d: %s", step, err_str)
                    self._session_logger.log_error(err_str, step)
                    await asyncio.sleep(1.0)
                except StateParseError as e:
                    err_str = str(e) or f"{type(e).__name__}"
                    logger.error("Parse error at step %d: %s", step, err_str)
                    self._session_logger.log_error(err_str, step)
                    await asyncio.sleep(0.5)
                except RuntimeError as e:
                    # RuntimeError = intentional abort (V2 failed, action unstable, etc.)
                    # Don't retry — terminate the run immediately
                    err_str = str(e) or f"{type(e).__name__}: {repr(e)}"
                    logger.error("Fatal error at step %d, terminating run: %s", step, err_str)
                    self._session_logger.log_error(err_str, step)
                    self._finalize_incomplete_run(last_gs, step=step, reason=err_str)
                    self._last_run_aborted = True
                    self._running = False
                    break
                except Exception as e:
                    err_str = str(e) or f"{type(e).__name__}: {repr(e)}"
                    logger.exception("Unexpected error at step %d", step)
                    self._session_logger.log_error(err_str, step)
                    await asyncio.sleep(1.0)

            if step >= self._max_steps:
                logger.warning("Max steps (%d) reached, stopping", self._max_steps)
                # Finalize with last known state
                try:
                    raw = await self._client.get_state()
                    final_gs = parse_state(raw)
                    self._finalize_incomplete_run(final_gs, step=step, reason="max_steps")
                except Exception:
                    logger.warning("Could not fetch final state for finalization", exc_info=True)
                    self._finalize_incomplete_run(last_gs, step=step, reason="max_steps")

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.warning("Run interrupted by user (Ctrl+C)")
            self._finalize_incomplete_run(last_gs, step=step, reason="interrupt")
            self._running = False
        finally:
            self._running = False
            self._finalize_incomplete_run(last_gs, step=step, reason="loop_exit")
            # Postrun + session-log close are deferred to ``finalize_session()``,
            # invoked by the caller AFTER it records the run to history.jsonl.
            # This way a postrun crash (LLM hang, watchdog os._exit, etc.)
            # cannot lose the run record.

        assert self._run_state is not None, "RunState should be initialized before loop"
        return self._run_state

    async def finalize_session(self) -> None:
        """Run postrun stages (memory / skills / evolution) and close the
        session log. Must be called by the orchestrator (scripts/run_agent.py)
        AFTER persisting the run record to history.jsonl, so any postrun
        failure (LLM hang, watchdog kill, exception) does not lose the
        gameplay outcome.

        Idempotent: a second call is a no-op (postrun runs at most once
        per gameplay run; log close is itself idempotent).
        """
        if getattr(self, "_session_finalized", False):
            return
        self._session_finalized = True
        if self._run_state is not None:
            await self._safe_post_run()
        if self._session_logger:
            self._session_logger.close()
            logger.info("Log saved: %s", self._session_logger.log_path)

    async def _safe_post_run(self) -> None:
        """Run post-run processing (memory, skills, evolution).

        Catches KeyboardInterrupt/CancelledError so Ctrl+C during gameplay
        still triggers memory extraction and self-evolution.

        Short-circuits entirely when ``config.postrun_effectively_enabled()``
        is False — either ``STS2_POSTRUN_ENABLED=false`` or the active model
        family has no ``analysis`` tier. Gameplay-time JSONL logs are
        written independently and are unaffected.
        """
        session_logger = self._session_logger

        if not config.postrun_effectively_enabled():
            reason = config.postrun_disabled_reason() or "disabled"
            logger.info("Postrun disabled (%s); skipping memory/skills/evolution stages", reason)
            if session_logger:
                session_logger.log_post_run_start(
                    completion_reason=self._run_completion_reason or None,
                    end_reason=self._run_end_reason or None,
                )
                session_logger.log_post_run_stage(
                    "memory", "skipped", reason=reason,
                )
                session_logger.log_post_run_stage(
                    "skills", "skipped", reason=reason,
                )
                session_logger.log_post_run_stage(
                    "evolution", "skipped", reason=reason,
                )
                session_logger.log_post_run_end()
            return

        # Cross-process advisory lock: when two agents (e.g. Silent +
        # Ironclad) run in parallel and both reach postrun near-simultaneously,
        # serialize the integral-JSON store rewrites (skills.json, guides.json,
        # card_memories.json, rules.json, ascension_stats.json). Gameplay is
        # unaffected; only postrun stages are gated. Disable with
        # STS2_POSTRUN_LOCK_DISABLED=true. Held inline (not via async-with)
        # to avoid re-indenting the entire postrun try/except/finally block.
        _postrun_lock_cm = postrun_lock()
        await _postrun_lock_cm.__aenter__()

        # Hard watchdog: ultimate safety net for genuine deadlocks (sync code
        # holding the asyncio loop, threaded HTTP client wedged with no
        # timeout, etc.). Run record is persisted in scripts/run_agent.py
        # BEFORE finalize_session() is called, so a watchdog kill loses the
        # postrun stages (memory/skills/stub_fill/evolution) but not the
        # gameplay outcome.
        #
        # 2026-05-06: bumped 1h → 12h. The proxy relay (proxy.example.com) has
        # observed read-timeout windows of 2-3 hours. With LLM_RETRY_FOREVER
        # + LLM_DISABLE_FALLBACK, a 1h watchdog killed 4/13 mode-b-fixed
        # postruns mid-retry-loop instead of waiting for the relay to recover
        # — losing stub_fill and evolution updates that would have succeeded
        # after the outage cleared. Killing+respawn doesn't help because the
        # relay is shared, so a fresh run hits the same outage. 12h gives
        # 4× headroom over observed outages while still bounding genuine
        # asyncio-level deadlocks. Override per-experiment via env var.
        _watchdog_kill_s = float(os.getenv("STS2_POSTRUN_WATCHDOG_S", str(12 * 60 * 60)))

        async def _watchdog():
            try:
                await asyncio.sleep(_watchdog_kill_s)
            except asyncio.CancelledError:
                return
            logger.error(
                "postrun watchdog: postrun exceeded %.0fs, force-exiting process to release lock",
                _watchdog_kill_s,
            )
            try:
                from src.storage.paths import data_root as _dr
                marker = _dr() / f".postrun.watchdog.{os.getpid()}.{int(time.time())}"
                marker.write_text(
                    f"pid={os.getpid()} killed after {_watchdog_kill_s}s\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            # Kill the launched game subprocess (if any) before os._exit so a
            # watchdog-triggered termination doesn't orphan the game on
            # Windows. os._exit bypasses every Python-level cleanup including
            # the end-of-__main__ block in scripts/run_agent.py, so without
            # this call the game keeps running with no parent. Idempotent —
            # if the early-kill path in run_agent.py main() already cleared
            # the handle, this is a no-op.
            try:
                from src.launcher.game_launcher import terminate_launched_game
                terminate_launched_game()
            except BaseException:
                pass
            os._exit(1)

        _watchdog_task = asyncio.create_task(_watchdog())
        try:
            # Enable telemetry for post-run LLM calls (guide consolidation, etc.)
            from src.brain.llm_caller import set_session_logger as _set_llm_logger
            _set_llm_logger(session_logger)

            if session_logger:
                session_logger.log_post_run_start(
                    completion_reason=self._run_completion_reason or None,
                    end_reason=self._run_end_reason or None,
                )

            # Skip post-run processing for invalid starts (game was already over
            # when the agent woke up — no gameplay data worth extracting).
            if self._run_end_reason == "invalid_start":
                logger.info("Skipping post-run processing for invalid_start run")
                return

            if self._memory:
                if session_logger:
                    session_logger.log_post_run_stage("memory", "start")
                try:
                    await self._post_run_memory_update()
                except Exception as exc:
                    if session_logger:
                        session_logger.log_post_run_stage(
                            "memory",
                            "failed",
                            error=str(exc) or type(exc).__name__,
                        )
                    logger.warning("Post-run memory stage failed", exc_info=True)
                else:
                    if session_logger:
                        session_logger.log_post_run_stage("memory", "done")
            elif session_logger:
                session_logger.log_post_run_stage("memory", "skipped")

            if self._skill_library:
                if session_logger:
                    session_logger.log_post_run_stage("skills", "start")
                try:
                    await self._post_run_skill_update()
                except Exception as exc:
                    if session_logger:
                        session_logger.log_post_run_stage(
                            "skills",
                            "failed",
                            error=str(exc) or type(exc).__name__,
                        )
                    logger.warning("Post-run skill stage failed", exc_info=True)
                else:
                    if session_logger:
                        session_logger.log_post_run_stage("skills", "done")
            elif session_logger:
                session_logger.log_post_run_stage("skills", "skipped")

            # Stage 5: Mode B seed stub fill (no-op unless SEED_STUB_FILL_ENABLED).
            # Runs after mistake_discovery (stage 4) so fill prompt can reference
            # newly-written mistake skills, before self-evolution (stage 6) so
            # self-evolution cannot accidentally write to stub IDs.
            if config.SEED_STUB_FILL_ENABLED:
                if session_logger:
                    session_logger.log_post_run_stage("stub_fill", "start")
                try:
                    await self._post_run_fill_stubs()
                except Exception as exc:
                    if session_logger:
                        session_logger.log_post_run_stage(
                            "stub_fill",
                            "failed",
                            error=str(exc) or type(exc).__name__,
                        )
                    logger.warning("Post-run stub fill stage failed", exc_info=True)
                else:
                    if session_logger:
                        session_logger.log_post_run_stage("stub_fill", "done")

            # Post-run evolution (self-authoring tools/skills)
            if (
                config.EVOLUTION_ENABLED
                and config.provider_supports_tool_loop(config.get_tier_provider("evolution"))
                and self._use_llm
            ):
                if session_logger:
                    session_logger.log_post_run_stage(
                        "evolution",
                        "start",
                        context_profile="heavy",
                    )
                try:
                    evo_result = await self._post_run_evolution()
                except Exception as exc:
                    if session_logger:
                        session_logger.log_post_run_stage(
                            "evolution",
                            "failed",
                            context_profile="heavy",
                            error=str(exc) or type(exc).__name__,
                        )
                    logger.warning("Post-run evolution stage failed", exc_info=True)
                else:
                    status = evo_result.get("status", "done") if isinstance(evo_result, dict) else "done"
                    details = evo_result if isinstance(evo_result, dict) else {}
                    if session_logger:
                        session_logger.log_post_run_stage(
                            "evolution",
                            status if status in {"done", "failed", "skipped"} else "done",
                            context_profile=details.get("context_profile", "heavy"),
                            context_chars=details.get("context_chars"),
                            action_count=details.get("action_count"),
                            error=details.get("error"),
                        )
            elif session_logger:
                session_logger.log_post_run_stage("evolution", "skipped")

        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.warning("Interrupted during post-run — saving memory before exit")
            # Memory/skill updates are sync-safe; try to save what we can
            try:
                if self._memory:
                    await self._post_run_memory_update()
            except Exception:
                pass
            raise  # Re-raise so the outer loop still exits
        except Exception as exc:
            logger.error("Post-run processing failed: %s", exc, exc_info=True)
        finally:
            # Flush write-gate judge queue (observation mode — commit 2 spec
            # §4.4 / §5). One batched fast-tier LLM call covering every
            # candidate that hit the judge zone during this postrun, plus
            # any structural cross-store conflicts found in the live skill
            # library. Result is logged but not yet enforced (commit 4).
            await self._flush_write_gate_judge()
            # Consolidation cadence reset (Spec #2 §3.2). Happens here
            # rather than inside the memory stage so it survives every
            # skip path (memory-only run, skills-stage exception,
            # evolution-stage exception). Always clears the snapshot
            # flag for the next run regardless of whether reset fired.
            if (
                getattr(self, "_postrun_consolidation_active", False)
                and self._memory is not None
            ):
                try:
                    self._memory.reset_consolidation_count()
                except Exception:
                    logger.warning(
                        "Post-run consolidation_count reset failed",
                        exc_info=True,
                    )
            self._postrun_consolidation_active = False
            # Drain any merge-queue entries that data_sync quarantined during
            # a prior reconcile. Bounded per-run so the postrun stays fast;
            # manual `python -m scripts.drain_merge_queue --all` unblocks the
            # rest if it grows.
            try:
                from src.storage import merge_queue as _mq
                mq_result = await _mq.drain(cap=_mq.DEFAULT_CAP)
                if mq_result["processed"] or mq_result["remaining"]:
                    logger.info("merge_queue postrun drain: %s", mq_result)
            except Exception as _mq_exc:
                logger.warning("merge_queue drain failed (non-fatal): %s", _mq_exc)
            if session_logger:
                session_logger.log_post_run_end()
            # Cancel the watchdog before releasing the lock — postrun completed.
            _watchdog_task.cancel()
            try:
                await _watchdog_task
            except (asyncio.CancelledError, Exception):
                pass
            # Release the cross-process postrun lock acquired at entry.
            try:
                await _postrun_lock_cm.__aexit__(None, None, None)
            except Exception:
                logger.warning("postrun_lock release failed", exc_info=True)

    async def _flush_write_gate_judge(self) -> None:
        """Drain the write-gate judge queue at end of postrun.

        Wrapped in try/except so judge errors never bubble into the agent
        loop. Skips silently when the queue is empty AND no structural
        conflicts are detected, so no LLM call is wasted on an empty round.

        When ``config.WRITE_GATE_REAP_ENABLED`` is True and the judge call
        returned a non-error ``BatchJudgeResult``, we follow up by calling
        :func:`reap_judge_verdicts` to apply the verdicts to held
        ``defer_to_judge`` candidates and structural-conflict pairs.
        """
        try:
            from src.memory.write_gate_judge import (
                JudgeClient,
                find_structural_conflicts,
            )

            queue_len = len(self._write_gate_queue) if self._write_gate_queue else 0
            conflict_pairs: list = []
            if self._skill_library is not None:
                from src.memory.write_gate import ExistingEntry
                from src.memory.write_gate_judge import _has_avoid, _has_prefer  # noqa: F401

                # Build duck-typed entries for the in-memory skill library.
                live_entries: list = []
                for s in self._skill_library.all_skills:
                    tags: set[str] = set()
                    trig = getattr(s, "trigger", None)
                    if trig is not None:
                        for attr in ("state_types", "enemy_names",
                                     "requires_hand_capabilities",
                                     "requires_enemy_powers"):
                            for v in getattr(trig, attr, ()) or ():
                                if isinstance(v, str) and v:
                                    tags.add(f"{attr}:{v}")
                    live_entries.append(
                        ExistingEntry(
                            id=getattr(s, "name", "") or getattr(s, "skill_id", ""),
                            content=getattr(s, "content", ""),
                            trigger_tags=frozenset(tags),
                            layer="L5",
                        )
                    )
                # Pass the gate's embedder so the detector can filter
                # pairs by content cosine (avoids flooding the judge with
                # pairs that share triggers but are on unrelated topics).
                conflict_pairs = find_structural_conflicts(
                    live_entries,
                    embedder=getattr(self._write_gate, "_embedder", None),
                )

            if queue_len == 0 and not conflict_pairs:
                return

            client = JudgeClient()
            if not client.available():
                logger.info(
                    "write_gate.flush_judge: skipping — STS2_GPT_API_KEY unset"
                )
                return

            run_id = self._run_state.run_id if self._run_state else ""
            result = self._write_gate.flush_judge_round(
                client,
                round_id=f"postrun_{run_id}",
                conflict_pairs=conflict_pairs,
            )
            if result is not None:
                if result.error:
                    logger.warning("write_gate.flush_judge error: %s", result.error)
                else:
                    logger.info(
                        "write_gate.flush_judge: %d candidates, %d conflicts judged",
                        len(result.candidate_judgements),
                        len(result.conflict_judgements),
                    )

            # Apply verdicts to held pending candidates (Task 11). Gated by
            # STS2_WRITE_GATE_REAP_ENABLED so the legacy observation-mode
            # behaviour (pass-through persistence) remains the default until
            # the live smoke confirms the reap pipeline.
            if (
                result is not None
                and not result.error
                and config.WRITE_GATE_REAP_ENABLED
                and self._skill_library is not None
            ):
                from src.brain.prompts.system import SYSTEM_COMBAT
                from src.memory.write_gate_reap import reap_judge_verdicts

                try:
                    stats = await reap_judge_verdicts(
                        gate=self._write_gate,
                        library=self._skill_library,
                        batch_result=result,
                        log_dir=Path(config.LOG_DIR),
                        combat_system_prompt=SYSTEM_COMBAT,
                    )
                    logger.info("write_gate.reap: %s", stats)
                except Exception:
                    logger.warning("write_gate.reap failed", exc_info=True)
        except Exception:
            logger.warning("write_gate.flush_judge failed", exc_info=True)

    def stop(self) -> None:
        self._running = False

    # ── HCM (V2) short-term memory hooks ─────────────────────

    def _hcm_short_term(self):
        """Get V2 short-term memory, or None."""
        import config
        if not config.STM_ENABLED:
            return None
        if self._memory and hasattr(self._memory, "short_term"):
            return self._memory.short_term
        return None

    def _track_event_lifecycle(self, gs: GameState) -> None:
        """Track event encounter start/end for memory extraction.

        Multi-stage events (e.g. Darv: choose relic → Proceed) are handled
        by detecting the is_finished=false → is_finished=true transition
        within the same event_id+floor.  At that transition the real choice
        is still the most recent decision, so we finalize stage 1 immediately
        and start a fresh tracker for the Proceed closing page.
        """
        if not self._memory:
            return
        stm = self._hcm_short_term()
        if stm is None:
            return

        if gs.state_type == "event" and gs.event:
            current = stm.current_event
            if current is None or (
                current.event_id != gs.event.event_id
                or current.floor != gs.floor
            ):
                # New event or different event — start fresh tracker
                deck_names = [
                    f"{_card_display_name(c)}"
                    for c in gs.deck
                ]
                stm.start_event(
                    event_id=gs.event.event_id,
                    event_title=gs.event.title,
                    floor=gs.floor,
                    act=gs.act,
                    hp=gs.player_hp,
                    gold=gs.gold,
                    deck=deck_names,
                )
                self._prev_event_gs = gs

            elif (
                self._prev_event_gs is not None
                and self._prev_event_gs.event is not None
                and not self._prev_event_gs.event.is_finished
                and gs.event.is_finished
            ):
                # Multi-stage transition: real options → Proceed (is_finished)
                # decisions[-1] is still the REAL choice (Proceed hasn't been
                # submitted yet), so finalize stage 1 now.
                self._finalize_event_stage(stm, gs)

                # Start fresh tracker for the Proceed closing page
                deck_names = [
                    f"{_card_display_name(c)}"
                    for c in gs.deck
                ]
                stm.start_event(
                    event_id=gs.event.event_id,
                    event_title=gs.event.title,
                    floor=gs.floor,
                    act=gs.act,
                    hp=gs.player_hp,
                    gold=gs.gold,
                    deck=deck_names,
                )
                self._prev_event_gs = gs

        elif self._prev_event_gs is not None and stm.current_event is not None:
            # We left the event screen — finalize with outcome diffs
            self._finalize_event_stage(stm, gs)
            self._prev_event_gs = None

    def _finalize_event_stage(self, stm, gs) -> None:
        """Finalize the current event tracker stage with outcome diffs.

        Looks up the most recent choose_event_option decision for chosen
        option, and diffs prev_event_gs against *gs* for card/relic/potion
        changes.
        """
        diff = _compute_event_state_diff(self._prev_event_gs, gs)

        # Debug: log relic diff to diagnose capture timing
        prev_relics = [r.name for r in getattr(self._prev_event_gs, "relics", [])]
        curr_relics = [r.name for r in getattr(gs, "relics", [])]
        if prev_relics != curr_relics:
            logger.info("Event relic diff detected: prev=%s curr=%s gained=%s",
                        prev_relics, curr_relics, diff["relics_gained"])
        elif diff.get("cards_gained") or diff.get("relics_gained"):
            logger.info("Event diff: cards=%s relics=%s potions=%s",
                        diff["cards_gained"], diff["relics_gained"], diff["potions_gained"])
        else:
            logger.debug("Event finalized with no detected diffs (prev_relics=%s curr_relics=%s)",
                         prev_relics, curr_relics)

        # Find the most recent choose_event_option decision
        chosen_index = -1
        chosen_text = ""
        if self._run_state and self._run_state.decisions:
            for dec in reversed(self._run_state.decisions):
                action_dict = dec.action if isinstance(dec.action, dict) else {}
                if action_dict.get("action") == "choose_event_option":
                    chosen_index = action_dict.get("option_index", -1)
                    break

        all_opts: list[str] = []
        if self._prev_event_gs.event:
            all_opts = [o.title for o in self._prev_event_gs.event.options]
            if 0 <= chosen_index < len(all_opts):
                chosen_text = all_opts[chosen_index]

        all_details: list[dict] = []
        is_proceed_only = False
        if self._prev_event_gs.event:
            opts = self._prev_event_gs.event.options or []

            def _looks_proceed(o: object) -> bool:
                if getattr(o, "is_proceed", False):
                    return True
                title = (getattr(o, "title", "") or "").strip().lower()
                return title == "proceed"

            if opts and all(_looks_proceed(o) for o in opts):
                is_proceed_only = True
            else:
                for o in opts:
                    all_details.append(_build_event_option_detail(o))

        if is_proceed_only:
            logger.debug(
                "Dropping Proceed-only event stage for %s F%d",
                self._prev_event_gs.event.event_id if self._prev_event_gs.event else "?",
                getattr(self._prev_event_gs, "floor", 0),
            )
            stm.cancel_event()
            return

        stm.end_event(
            chosen_index=chosen_index,
            option_text=chosen_text,
            hp_after=gs.player_hp,
            gold_after=gs.gold,
            all_options=all_opts,
            cards_gained=diff["cards_gained"],
            cards_lost=diff["cards_lost"],
            relics_gained=diff["relics_gained"],
            potions_gained=diff["potions_gained"],
            all_option_details=all_details,
        )

    def _try_activate_skill_eval(self, gs: GameState) -> None:
        """Check for untested skills and activate eval mode if appropriate."""
        from src.skills.replay_evaluator import build_eval_schedule

        original_ids = list(self._combat_skill_ids)
        if not original_ids:
            return

        # Build pool of candidate skills (active, trigger-matching boss context)
        boss_name = max(
            (e.name for e in gs.enemies), key=lambda n: len(n), default="",
        )
        all_active = [
            (s.skill_id, s.usage_count)
            for s in self._skill_library.all_skills
            if s.status == "active"
            and s.skill_id not in original_ids
            and s.trigger.matches(
                state_type=gs.state_type,
                enemy_name=boss_name,
            )[0]  # trigger must match boss context
        ]
        # Filter to those with usage_count == 0 first (untested)
        untested = [(sid, uc) for sid, uc in all_active if uc == 0]
        if not untested:
            logger.info("Skill eval: no untested skills, staying idle")
            return

        schedule = build_eval_schedule(
            original_skill_ids=original_ids,
            all_skills_pool=untested,
            max_replays=config.SKILL_EVAL_MAX_REPLAYS,
        )
        if not schedule:
            return

        self._skill_eval_state = "active"
        self._eval_results = []
        self._eval_skill_sets = schedule
        # Sentinel -1: current combat runs with original/baseline skills.
        # After the first terminal, index advances to 0 and schedule[0] is applied.
        self._eval_current_index = -1
        self._eval_original_skill_ids = original_ids
        self._eval_combat_start_hp = gs.player_hp
        self._eval_round_count = 0
        self._eval_potions_used = 0
        logger.info(
            "Skill eval ACTIVATED: %d alternative sets to test (%d untested skills)",
            len(schedule),
            len(untested),
        )

    async def _handle_eval_terminal(self, gs: GameState, *, won: bool) -> None:
        """Record eval result and either swap to next skill set or finish eval."""
        import hashlib

        from src.skills.replay_evaluator import ReplayResult

        # Record this replay's result.
        # _eval_current_index == -1: baseline (original) just ran.
        # 0..N-1: _eval_skill_sets[i] just ran.
        if self._eval_current_index < 0:
            current_skills = tuple(sorted(self._eval_original_skill_ids))
        else:
            current_skills = tuple(sorted(self._eval_skill_sets[self._eval_current_index]))

        hp_lost = max(0, self._eval_combat_start_hp - gs.player_hp)
        result = ReplayResult(
            skill_set_id=hashlib.md5(str(current_skills).encode()).hexdigest()[:8],
            skills_used=current_skills,
            hp_lost=hp_lost,
            rounds=self._eval_round_count,
            potions_used=self._eval_potions_used,
            won=won,
        )
        self._eval_results.append(result)
        logger.info(
            "Skill eval result: set=%s won=%s hp_lost=%d rounds=%d",
            result.skill_set_id, won, hp_lost, self._eval_round_count,
        )

        # Snapshot in-combat strategic notes BEFORE save/quit so the replay
        # conversation can re-inject them — save/quit wipes the conversation
        # object below, so without this the LLM replays the combat with zero
        # memory of its own prior plans and the A/B signal gets confounded.
        saved_strategic_notes: list[tuple[int, str]] = []
        if self._v2_combat_conversation is not None:
            saved_strategic_notes = list(
                getattr(self._v2_combat_conversation, "_strategic_notes", []) or []
            )

        # Save and reload from the same save point
        try:
            from src.mcp_client import actions as mcp_actions

            await self._client.post_action(mcp_actions.save_and_quit())
            await asyncio.sleep(2)
            await self._client.post_action(mcp_actions.continue_run())
            await asyncio.sleep(2)
        except Exception as e:
            logger.warning("Skill eval save/swap failed: %s — aborting eval", e)
            self._skill_eval_state = "idle"
            if self._skill_library:
                self._skill_library.clear_active_override()
            return

        # Reset combat tracking for the new replay
        self._v2_combat_conversation = None
        self._combat_plan = None
        self._combat_plan_index = 0
        self._combat_plan_round = -1
        self._no_target_replan_round = -1
        self._v2_round_actions = []
        self._last_combat_round = -1
        self._end_turn_sent_round = -1
        self._eval_round_count = 0
        self._eval_potions_used = 0

        # Re-initialize combat conversation after reload (mirrors COMBAT_START handler)
        if self._v2_engine:
            try:
                raw_fresh = await self._client.get_state()
                gs_fresh = parse_state(raw_fresh)
                self._eval_combat_start_hp = gs_fresh.player_hp

                self._v2_combat_conversation = self._maybe_create_combat_conversation(gs_fresh)

                if self._v2_combat_conversation is not None:
                    # Build strategic context
                    strategic_parts: list[str] = []
                    ctx = self._build_decision_context(gs_fresh)
                    if ctx.get("skill_context"):
                        strategic_parts.append(ctx["skill_context"])
                    wc = ctx.get("working_context")
                    if wc is not None:
                        from dataclasses import replace as dc_replace

                        from src.memory.prompt_injector import format_working_context
                        wc_no_thread = dc_replace(wc, short_term_hints=())
                        mem_str = format_working_context(wc_no_thread)
                        if mem_str:
                            strategic_parts.append(mem_str)
                    if ctx.get("boss_strategy"):
                        strategic_parts.append(
                            f"## Boss Strategy\n{ctx['boss_strategy']}"
                        )
                    strategic_context = "\n\n".join(strategic_parts)

                    # Build potion strategy
                    from src.knowledge.potion_classifier import classify_potion, format_potion_tag
                    act = gs_fresh.act if gs_fresh.act else 1
                    floor = gs_fresh.floor if gs_fresh.floor else 0
                    _boss_floors = {1: 17, 2: 34, 3: 51}
                    floors_to_boss = max(0, _boss_floors.get(act, 51) - floor)
                    combat_type = gs_fresh.state_type
                    potion_strat = ""
                    if gs_fresh.potions:
                        pot_lines = ["## Potion Strategy"]
                        pot_lines.append(
                            f"Fight: {combat_type} | Boss: {floors_to_boss} floors away"
                        )
                        for p_obj in gs_fresh.potions:
                            if not p_obj.occupied and not p_obj.can_use:
                                continue
                            name = p_obj.name or ""
                            desc = p_obj.description or ""
                            if not name:
                                continue
                            profile = classify_potion(name, desc)
                            tag = format_potion_tag(
                                profile.timing, combat_type, floors_to_boss
                            )
                            pot_lines.append(f"- {name} {tag}: {strip_bbcode(desc)}")
                        if len(pot_lines) > 2:
                            potion_strat = "\n".join(pot_lines)

                    self._v2_combat_conversation._floors_to_boss = floors_to_boss
                    # Pull run-level strategic thread so the replay conversation starts
                    # with the same run context the baseline combat had.
                    stm_thread_replay = ""
                    stm_replay = self._hcm_short_term()
                    if stm_replay is not None:
                        stm_thread_replay = stm_replay.get_strategic_thread(
                            max_entries=7, current_context=gs_fresh.state_type,
                        )
                    # Build card notes for deck cards from CardMemory
                    eval_card_notes: dict[str, str] = {}
                    if self._memory and getattr(self._memory, "card_memory_store", None) and self._run_state:
                        deck_names = [c.name for c in gs_fresh.deck] if gs_fresh.deck else []
                        memories = self._memory.card_memory_store.query_cards(
                            self._run_state.character, deck_names,
                        )
                        eval_card_notes = {m.card_name: m.note for m in memories if m.note}
                    self._v2_combat_conversation.add_combat_start(
                        gs_fresh,
                        strategic_context=strategic_context,
                        potion_strategy=potion_strat,
                        strategic_thread=stm_thread_replay,
                        combat_type=self._last_combat_type,
                        card_notes=eval_card_notes or None,
                    )
                    # Re-seed the intra-combat strategic notes captured before
                    # save/quit so the replay sees its own prior-round plans.
                    for rnd_num, note in saved_strategic_notes:
                        self._v2_combat_conversation.record_strategic_note(rnd_num, note)
                    logger.info(
                        "V2: combat conversation re-initialized after eval reload "
                        "(restored %d strategic notes, thread=%s chars)",
                        len(saved_strategic_notes), len(stm_thread_replay),
                    )
            except Exception as exc:
                logger.warning("V2 combat conversation re-init failed: %s", exc)
                self._v2_combat_conversation = None

        # Advance to next skill set. Semantics: index -1 = baseline, 0..N-1 = schedule[i].
        # Move forward by one and either apply the corresponding schedule entry,
        # or — when we've exhausted all slots — enter the final run with the
        # best-performing set from all recorded results (baseline + alternatives).
        self._eval_current_index += 1
        if self._eval_current_index < len(self._eval_skill_sets):
            next_skills = self._eval_skill_sets[self._eval_current_index]
            self._skill_library.set_active_override(next_skills)
            logger.info(
                "Skill eval: swapping to set %d/%d: %s",
                self._eval_current_index + 1, len(self._eval_skill_sets),
                next_skills,
            )
        else:
            # All alternatives tested — enter FINAL_RUN with best set.
            self._skill_eval_state = "final"
            self._update_eval_confidence()
            if self._eval_results:
                best = min(self._eval_results, key=lambda r: (not r.won, r.hp_lost))
                self._skill_library.set_active_override(list(best.skills_used))
                logger.info(
                    "Skill eval: FINAL RUN with best set %s (hp_lost=%d, %d results compared)",
                    best.skill_set_id, best.hp_lost, len(self._eval_results),
                )
            else:
                self._skill_library.clear_active_override()
                self._skill_eval_state = "idle"

    def _update_eval_confidence(self) -> None:
        """Update skill confidence based on all eval results."""
        from src.skills.replay_evaluator import compute_confidence_deltas

        if not self._skill_library or len(self._eval_results) < 2:
            return

        deltas = compute_confidence_deltas(self._eval_results)
        for sid, delta in deltas.items():
            success = delta > 0
            quality = abs(delta)
            self._skill_library.record_replay_outcome(sid, success=success, quality=quality)
            logger.info("Skill eval confidence: %s → %+.3f", sid, delta)

    def _hcm_start_combat(self, gs: GameState) -> None:
        """Hook: COMBAT_START — begin tracking + boss web search."""
        enemy_names = [e.name for e in gs.enemies] if gs.enemies else []
        combat_type = self._resolve_combat_type(gs)

        # V2 short-term memory tracking (optional — requires memory system)
        stm = self._hcm_short_term()
        if stm is not None:
            hp = gs.player_hp
            deck_size = gs.deck_size
            relic_names = [r.name for r in gs.relics] if gs.relics else []
            floor = gs.run.floor if gs.run else 0
            act = gs.act if gs.run else 1
            gold = gs.gold
            stm.start_combat(enemy_names, combat_type, hp, deck_size, relic_names, floor, act)
            # Also record as route node so route memory includes combat encounters
            stm.start_route_node(floor, combat_type, hp, gold)
            if gs.deck:
                stm.capture_starting_deck([c.name for c in gs.deck])
            # Attach CombatContext snapshot for delta recording
            try:
                from src.memory.combat_delta import build_combat_context
                ctx = build_combat_context(
                    gs, self._run_state.character if self._run_state else "",
                )
                if ctx is not None and stm.current_combat is not None:
                    stm.current_combat.combat_context = ctx
            except Exception:
                logger.debug("Combat context capture failed", exc_info=True)

        # Boss fight: clear previous strategy + fire background web search
        # (independent of memory system — works even with --no-memory)
        self._boss_strategy = ""
        if combat_type == "boss" and self._web_searcher and enemy_names:
            boss_enemy = max(gs.enemies, key=lambda e: e.max_hp)
            character = self._run_state.character if self._run_state else ""
            if character:
                # Cancel previous task if still running (prevents stale writes)
                if self._boss_search_task and not self._boss_search_task.done():
                    self._boss_search_task.cancel()
                self._boss_search_task = asyncio.create_task(
                    self._fetch_boss_strategy_bg(boss_enemy.name, character)
                )

    def _hcm_end_combat(self, won: bool, hp_after: int) -> None:
        """Hook: COMBAT_END — finalize combat tracking."""
        stm = self._hcm_short_term()
        if stm is not None:
            # Finalize last round's damage_taken from HP delta
            combat = stm.current_combat
            if combat is not None and combat._current_round is not None:
                prev = combat._current_round
                prev.hp_end = hp_after
                prev.damage_taken = max(0, prev.hp_start - hp_after)
            stm.end_combat(won, hp_after)
            stm.expire_combat_notes()
            # Close the route node opened in _hcm_start_combat
            gold = self._cached_gold if hasattr(self, "_cached_gold") else 0
            act = self._cached_act if hasattr(self, "_cached_act") else 1
            stm.end_route_node(hp_after, gold, act)

    def _combat_quality_score(self, won: bool, hp_after: int) -> float:
        """Map combat outcome to a discrete confidence-update weight."""
        from src.skills.combat_quality import compute_combat_quality_score

        return compute_combat_quality_score(
            self._last_combat_type,
            self._current_combat_start_hp,
            hp_after,
            won=won,
        )

    def _log_combat_summary(self, step: int) -> None:
        """Log combat summary from the most recently completed combat tracker."""
        if not self._session_logger:
            return
        stm = self._hcm_short_term()
        if stm is None or not stm.completed_combats:
            return
        tracker = stm.completed_combats[-1]
        try:
            self._session_logger.log_combat_summary(tracker, step)
        except Exception:
            pass  # Log never crashes agent

    def _track_rest_heal(self, gs: GameState, option_title: str) -> None:
        """Track HP restored via rest for non-combat skill scoring.

        Called when a rest option is executed. If the option is a heal
        (title contains 'rest', case-insensitive), approximate the heal
        amount as 30% of max HP and add to the act total.
        """
        if option_title and "rest" in option_title.lower():
            heal_amt = int(gs.player_max_hp * 0.3)
            self._act_heal_total += heal_amt
            logger.debug(
                "Rest heal tracked: +%d HP (act total: %d)",
                heal_amt, self._act_heal_total,
            )

    def _score_noncombat_skills_end_of_run(self) -> None:
        """Compute non-combat score once at run end and record it."""
        if not self._skill_library or not self._noncombat_skill_counts:
            return
        try:
            from src.skills.noncombat_scorer import compute_noncombat_score

            final_floor = (
                (self._run_state.final_floor or self._run_state._highest_floor)
                if self._run_state else 0
            )
            max_hp = self._run_state.final_max_hp if self._run_state else 70
            score = compute_noncombat_score(
                final_floor=final_floor,
                bosses_killed=list(self._bosses_killed),
                last_boss_entry_hp=self._last_boss_entry_hp,
                max_hp=max_hp,
                last_act_heal_total=self._last_boss_heal_total,
            )
            # Only score skills injected 3+ times across the run (real influence)
            skill_ids = [
                sid for sid, count in self._noncombat_skill_counts.items()
                if count >= 3
            ]
            if not skill_ids:
                logger.info("Non-combat score: no high-frequency skills to score")
                return
            self._skill_library.record_noncombat_outcome(skill_ids, score)
            logger.info(
                "Non-combat end-of-run score: %.1f for %d skills (floor=%d, boss_hp=%s, bosses=%s)",
                score, len(skill_ids), final_floor,
                self._last_boss_entry_hp, self._bosses_killed,
            )
        except Exception as exc:
            logger.warning("Non-combat scoring failed: %s", exc)

    def _hcm_start_round(self, gs: GameState) -> None:
        """Hook: new combat round — start round tracking.

        Also finalizes previous round's damage_taken from HP delta.
        """
        stm = self._hcm_short_term()
        if stm is None or not gs.combat:
            return
        stm.expire_turn_notes()

        # Finalize previous round's damage_taken from HP delta
        combat = stm.current_combat
        if combat is not None and combat._current_round is not None:
            prev = combat._current_round
            prev.hp_end = gs.player_hp
            prev.damage_taken = max(0, prev.hp_start - gs.player_hp)

        # Extract enemy intents (structured: damage/hits, not raw move names)
        intents = []
        agent_view_enemies = {}
        if gs.agent_view and gs.agent_view.combat:
            for av_enemy in gs.agent_view.combat.enemies:
                agent_view_enemies[av_enemy.i] = av_enemy

        for e in gs.enemies:
            av_enemy = agent_view_enemies.get(e.index)
            if av_enemy is None and gs.agent_view and gs.agent_view.combat:
                av_enemy = next(
                    (cand for cand in gs.agent_view.combat.enemies if cand.name == e.name),
                    None,
                )
            intent_text = format_enemy_intents_for_memory(
                e,
                fallback_intent=getattr(av_enemy, "intent", None),
            )
            intents.append(f"{e.name}: {intent_text}")
        # Extract hand card names for drawn-but-not-played tracking
        hand_cards: list[str] = []
        if gs.hand:
            hand_cards = [c.name for c in gs.hand if c.name]

        # Compute situation tag for round-level retrieval (Phase 1).
        # threat_level / intent_class / deck_stage were removed in the
        # 2026-04-20 mistake-driven redesign (Task A5); only
        # hand_capabilities is carried forward for skill retrieval.
        sit_tag = None
        try:
            from src.brain.prompts._intent_fmt import compute_total_incoming as _sit_incoming
            from src.memory.situation import (
                SituationTag as _SitTag,
            )
            from src.memory.situation import (
                compute_hand_capabilities as _sit_compute_hand,
            )

            total_inc = _sit_incoming(gs.enemies) if gs.enemies else 0
            lowest_ehp = min((e.hp for e in gs.enemies if e.is_alive), default=0) if gs.enemies else 0
            hand_cap = _sit_compute_hand(
                gs.hand or [], total_inc, lowest_ehp, gs.energy or 3,
            )
            sit_tag = _SitTag(
                hand_capabilities=hand_cap,
                tag_source="runtime",
            )
        except Exception:
            logger.debug("Situation tag computation failed", exc_info=True)

        # Capture rich round-start enemy/player state for mechanic-oriented
        # combat guide distillation, alongside the legacy lightweight
        # snapshots still consumed by older analytics helpers.
        enemy_states = None
        player_powers_snapshot = None
        enemy_powers: list[tuple[str, ...]] | None = None
        if gs.raw and gs.raw.combat:
            from src.knowledge.power_lookup import get_power_description as _get_power_desc
            from src.memory.combat_delta import _format_power as _fmt_power
            from src.memory.models_v2 import (
                EnemyIntentSnapshot,
                EnemyRoundState,
                PowerSnapshot,
            )

            def _snapshot_power(power) -> PowerSnapshot:
                desc = (getattr(power, "description", "") or "").strip()
                if not desc:
                    lookup_key = getattr(power, "power_id", "") or getattr(power, "name", "")
                    if lookup_key:
                        desc = _get_power_desc(lookup_key) or ""
                return PowerSnapshot(
                    power_id=getattr(power, "power_id", "") or "",
                    name=getattr(power, "name", "") or "",
                    amount=getattr(power, "amount", None),
                    description=desc,
                    is_debuff=bool(getattr(power, "is_debuff", False)),
                )

            enemy_powers = []
            enemy_states = []
            for e in gs.raw.combat.enemies:
                powers = tuple(
                    _fmt_power(p) for p in e.powers
                ) if e.powers else ()
                enemy_powers.append(powers)
                enemy_states.append(EnemyRoundState(
                    enemy_id=e.enemy_id or e.name,
                    name=e.name,
                    hp=e.current_hp,
                    max_hp=e.max_hp,
                    block=e.block,
                    powers=tuple(_snapshot_power(p) for p in e.powers),
                    intents=tuple(
                        EnemyIntentSnapshot(
                            intent_type=intent.intent_type,
                            label=intent.label or "",
                            damage=intent.damage,
                            hits=intent.hits,
                            total_damage=intent.total_damage,
                            status_card_count=intent.status_card_count,
                        )
                        for intent in e.intents
                    ),
                ))
            player_powers_snapshot = [
                _snapshot_power(p) for p in gs.raw.combat.player.powers
            ]

        # Capture enemy HP snapshot for phase transition detection
        enemy_hp: list[tuple[str, str, int, int]] | None = None
        if gs.raw and gs.raw.combat:
            enemy_hp = [
                (
                    e.enemy_id or e.name,
                    e.name,
                    e.current_hp,
                    e.max_hp,
                )
                for e in gs.raw.combat.enemies
            ]

        stm.start_combat_round(
            round_num=gs.combat_round,
            energy=gs.energy,
            hp=gs.player_hp,
            enemy_intents=intents,
            hand_cards=hand_cards,
            situation_tag=sit_tag,
            enemy_states=enemy_states,
            player_powers_snapshot=player_powers_snapshot,
            enemy_powers=enemy_powers,
            enemy_hp=enemy_hp,
        )

    def _hcm_record_card_play(self, card_name: str, energy_cost: int = 0) -> None:
        """Hook: card played — record in short-term memory."""
        stm = self._hcm_short_term()
        if stm is not None:
            stm.record_card_play(card_name, energy_cost)

    def _hcm_record_sly_play(self, card_name: str) -> None:
        """Hook: Sly-triggered play — record in short-term memory."""
        stm = self._hcm_short_term()
        if stm is not None:
            stm.record_sly_play(card_name)

    @staticmethod
    def _is_sly_discard(card, gs: GameState) -> bool:
        """Check if selecting this card for discard would trigger Sly.

        Only true when: card has Sly keyword AND selection is a discard
        (not exhaust). End-of-turn auto-discard never routes through
        hand_select, so any hand_select discard is a card-effect discard.
        """
        if not (card.rules_text and card.rules_text.startswith("Sly.")):
            return False
        sel = gs.selection
        if not sel:
            return False
        kind_lower = (sel.kind or "").lower()
        prompt_lower = (sel.prompt or "").lower()
        is_discard = "discard" in kind_lower or "discard" in prompt_lower
        is_exhaust = "exhaust" in kind_lower or "exhaust" in prompt_lower
        return is_discard and not is_exhaust

    def _hcm_record_potion_use(self, potion_name: str) -> None:
        """Hook: potion used — record in short-term memory."""
        stm = self._hcm_short_term()
        if stm is not None:
            stm.record_potion_use(potion_name)

    def _hcm_record_deck_change(
        self, floor: int, event_type: str, card_name: str, source: str,
    ) -> None:
        """Hook: deck modified — record in short-term memory."""
        stm = self._hcm_short_term()
        if stm is not None:
            stm.record_deck_change(floor, event_type, card_name, source)

    _STRATEGIC_NOTE_STATE_TYPES = frozenset({
        "card_reward", "shop", "map", "rest_site", "event", "card_select",
    })

    def _record_strategic_note(self, decision: "LLMDecision", context_type: str) -> None:
        """Extract strategic_note from decision params and record in STM.

        Only records for state types that have strategic_note in their tool
        schema. Parses optional note_scope and note_triggers from the LLM.
        """
        if context_type not in self._STRATEGIC_NOTE_STATE_TYPES:
            return
        note = decision.params.get("strategic_note", "")
        if not note or not isinstance(note, str):
            return
        stm = self._hcm_short_term()
        if stm is None:
            return

        from src.memory.short_term import NoteScope

        # Parse scope (default: run)
        raw_scope = decision.params.get("note_scope", "run")
        try:
            scope = NoteScope(raw_scope)
        except ValueError:
            scope = NoteScope.RUN

        # Parse triggers. LLMs almost always default note_triggers to ["all"]
        # which under the prior implementation made the trigger filter a no-op
        # — every note showed during every state type. We now treat both
        # "key absent" and explicit ["all"] as a request to auto-infer from
        # context_type (so a card_reward note doesn't leak into map prompts).
        # An LLM that returns a specific list (e.g. ["combat", "routing"])
        # still keeps full control.
        triggers: tuple[str, ...] | None = None
        raw_triggers = decision.params.get("note_triggers")
        if isinstance(raw_triggers, list):
            valid_triggers = {"combat", "deck_building", "routing", "all"}
            cleaned = tuple(t for t in raw_triggers if t in valid_triggers)
            if cleaned and cleaned != ("all",):
                triggers = cleaned

        floor = self._run_state.floor if self._run_state and hasattr(self._run_state, "floor") else 0
        combat_round = (
            self._v2_combat_conversation._round_count
            if self._v2_combat_conversation else 0
        )

        stm.record_strategic_note(
            context_type, note,
            scope=scope, triggers=triggers,
            floor=floor, combat_round=combat_round,
        )
        logger.debug(
            "Strategic note [%s] scope=%s triggers=%s: %s",
            context_type, scope.value, triggers or "(auto)", note[:80],
        )

    def _hcm_start_route_node(self, gs: GameState, node_type: str) -> None:
        """Hook: entering a map node — start route node tracking."""
        stm = self._hcm_short_term()
        if stm is not None and gs.run:
            stm.start_route_node(
                floor=gs.run.floor,
                node_type=node_type,
                hp=gs.player_hp,
                gold=gs.gold,
            )

    def _hcm_end_route_node(self, gs: GameState) -> None:
        """Hook: leaving a map node — finalize route node."""
        stm = self._hcm_short_term()
        if stm is not None:
            act = gs.act if gs.run else 1
            stm.end_route_node(hp=gs.player_hp, gold=gs.gold, act=act)

    # ── Post-run memory ─────────────────────────────────────────

    async def _post_run_memory_update(self) -> None:
        """Extract V2 HCM domain memories and update rules after a run.

        Best-effort: errors are logged but do not affect the run result.
        """
        if not self._memory or not self._run_state:
            return

        try:
            # V2 (HCM): extract domain-specific memories from short-term first so
            # the current run is included in immediate post-run distillation.
            self._pending_build_mem = None
            self._pending_combat_trace = None
            self._pending_trace_candidates = []
            self._pending_skipped_cards = []
            self._post_run_hcm_extraction()

            # LLM-based build analysis (async) — runs after sync extraction
            if self._pending_build_mem and self._use_llm:
                await self._analyze_build_async()

            # Consolidate guides periodically (every N runs).
            # Snapshot the decision BEFORE consolidate_guides runs so that
            # an exception in consolidate_guides does not prevent the
            # skills-stage mistake_discovery from firing on this cadence
            # cycle (Spec #2 §3.4 bundled improvement).
            self._memory.increment_consolidation_count()
            self._postrun_consolidation_active = self._memory.should_consolidate
            if self._postrun_consolidation_active:
                try:
                    from src.memory.guide_consolidator import consolidate_guides
                    guide_stats = await consolidate_guides(
                        self._memory,
                        current_run_id=self._run_state.run_id if self._run_state else "",
                    )
                    total_guides = sum(guide_stats.values())
                    if total_guides > 0:
                        logger.info("Guide consolidation: %s", guide_stats)
                        if self._session_logger is not None and hasattr(
                            self._session_logger, "log_postrun_artifact",
                        ):
                            try:
                                self._session_logger.log_postrun_artifact(
                                    stage="guides",
                                    kind="guide_consolidation",
                                    action="update",
                                    summary=(
                                        f"combat={guide_stats.get('combat', 0)}, "
                                        f"route={guide_stats.get('route', 0)}, "
                                        f"deck={guide_stats.get('deck', 0)}"
                                    ),
                                    after=dict(guide_stats),
                                    source="guide_consolidator",
                                )
                            except Exception:
                                pass
                except Exception:
                    logger.warning("Guide consolidation failed", exc_info=True)
            # mistake_discovery moved to _post_run_skill_update (Spec #2 §3.1).
            # consolidation_count reset moved to _safe_post_run finally
            # block (Spec #2 §3.2).

            # Periodic maintenance
            self._memory.maintenance()

            # Save to disk
            self._memory.save_all()

            logger.info(
                "Memory updated: stats=%s",
                self._memory.stats(),
            )
        except Exception:
            logger.warning("Post-run memory update failed", exc_info=True)
            raise

    async def _check_pending_batches(self) -> None:
        """Drain legacy in-flight batch results from the Anthropic Batch API.

        The only surviving task type is 'distillation' — kept so that batches
        submitted by older versions of the agent still get processed rather
        than silently hanging on the proxy. No new batches are submitted after
        the non-combat skill discovery removal.
        """
        if config.get_tier_provider("analysis") != "anthropic":
            return
        from src.brain.batch import check_completed

        try:
            completed = check_completed()
        except Exception:
            logger.warning("Batch check failed", exc_info=True)
            return

        for tasks_meta, results in completed:
            for task in tasks_meta:
                custom_id = f"{task['type'][:7]}-{task.get('run_id', 'unknown')}"
                # Find matching result (custom_id prefix matching)
                raw_text = None
                for cid, text in results.items():
                    if cid.startswith(task["type"][:7]):
                        raw_text = text
                        break

                if not raw_text:
                    continue

                try:
                    # No active batch task types after the 2026-04-23 distillation
                    # removal. check_completed still runs so legacy batch state files
                    # get cleaned up; no branch handles the results.
                    pass

                except Exception:
                    logger.warning(
                        "Failed to process batch result %s", custom_id, exc_info=True,
                    )

    def _post_run_hcm_extraction(self) -> None:
        """Extract V2 domain memories from short-term memory into stores."""
        if not self._memory or not self._run_state:
            return
        stm = self._hcm_short_term()
        if stm is None:
            return

        # Finalize any in-progress route node or combat (last node/combat before death/victory)
        act = self._planned_act if self._planned_act > 0 else 1
        completion_reason = self._run_completion_reason or (
            "aborted" if self._last_run_aborted else "completed"
        )
        combat_terminal_reason = "win" if self._run_state.victory else "loss"
        if completion_reason != "completed":
            combat_terminal_reason = "abort"
        stm.finalize_open_state(
            act=act,
            hp=self._run_state.final_hp,
            gold=self._run_state.final_gold,
            combat_terminal_reason=combat_terminal_reason,
        )

        try:
            from src.memory.card_build_extractor import extract_card_build_memory
            from src.memory.combat_extractor import extract_combat_episodes
            from src.memory.route_extractor import extract_route_memories

            run_id = self._run_state.run_id
            character = self._run_state.character
            victory = self._run_state.victory
            fitness = self._run_state.fitness()

            # Combat episodes
            combat_eps = extract_combat_episodes(stm, run_id, character)
            if combat_eps and self._memory.combat_store:
                self._memory.combat_store.add_batch(combat_eps)

            # Route memories
            route_mems = extract_route_memories(
                stm, run_id, character, victory, fitness,
            )
            if route_mems and self._memory.route_store:
                self._memory.route_store.add_batch(route_mems)

            # Card build memory
            final_deck = []
            # Get final deck from last known game state
            if self._run_state.floor_snapshots:
                # Deck is not in FloorSnapshot, use the deck from GameState
                # We'll grab it from the short-term memory's events instead
                starting = stm.starting_deck
                final_deck = list(starting)
                for event in stm.deck_events:
                    if event.event_type == "add":
                        final_deck.append(event.card_name)
                    elif event.event_type == "remove" and event.card_name in final_deck:
                        final_deck.remove(event.card_name)
                    elif event.event_type == "upgrade":
                        # Replace card with upgraded version
                        if event.card_name in final_deck:
                            final_deck.remove(event.card_name)
                            final_deck.append(event.card_name + "+")

            final_floor = self._run_state.final_floor or 0
            # Allow learning from runs that progressed enough (>= 10 floors),
            # even if aborted by max_steps or other non-fatal reasons.
            allow_run_learning = (
                completion_reason == "completed" or final_floor >= 10
            )
            is_incomplete = completion_reason != "completed"
            # Determine which act the agent died in (for card memory stats)
            final_act = max(1, (final_floor - 1) // 17 + 1) if final_floor > 0 else 0
            if final_act > 3:
                final_act = 3

            if allow_run_learning and (final_deck or stm.deck_events):
                from src.memory.card_build_extractor import extract_build_evidence

                build_mem = extract_card_build_memory(
                    stm, run_id, character, final_deck,
                    victory, self._run_state.final_floor, fitness,
                    completion_reason=completion_reason,
                    relics=list(self._cached_relics),
                    final_deck_payload=list(self._cached_deck_payload),
                    card_rules=dict(self._seen_card_rules),
                )
                if self._memory.card_build_store:
                    self._memory.card_build_store.add(build_mem)
                # Extract evidence now (immutable dict) — don't hold stm reference
                evidence = extract_build_evidence(
                    stm, character, final_deck,
                    victory, self._run_state.final_floor, fitness,
                    completion_reason=completion_reason,
                    relics=list(self._cached_relics),
                    final_deck_payload=list(self._cached_deck_payload),
                    card_rules=dict(self._seen_card_rules),
                )
                self._pending_build_mem = (build_mem, evidence)

                # Combat trace rendering — gated by config flags and floor_sum.
                # Runs synchronously here while stm is still valid; result
                # stored for _analyze_build_async to forward to both turns.
                recent_combats = list(stm.completed_combats[-2:]) if stm else []
                _floor_sum = sum(getattr(c, "floor", 0) for c in recent_combats)
                import json as _json
                from pathlib import Path as _Path
                _log_path = _Path(config.LOG_DIR) / f"run_{run_id}.jsonl"
                _run_log_events: list[dict] = []
                if _log_path.exists():
                    try:
                        with open(_log_path, encoding="utf-8") as _lf:
                            for _line in _lf:
                                _line = _line.strip()
                                if _line:
                                    try:
                                        _run_log_events.append(_json.loads(_line))
                                    except _json.JSONDecodeError:
                                        continue
                    except Exception:
                        logger.warning("Failed to load run log for combat trace", exc_info=True)
                self._pending_combat_trace = _maybe_render_combat_trace(
                    stm=stm,
                    run_log_events=_run_log_events,
                    floor_sum=_floor_sum,
                )
                # Candidates scoped to the same combats the trace covers.
                if self._pending_combat_trace:
                    self._pending_trace_candidates = extract_candidate_cards(recent_combats)
                    # Bucket B (non-deck card notes) consumes the run-wide
                    # set of cards offered at card_reward / shop but not picked.
                    self._pending_skipped_cards = extract_skipped_cards(_run_log_events)
                    logger.info(
                        "postrun_trace: rendered %d combats, %d chars, %d candidates, %d skipped",
                        len(recent_combats), len(self._pending_combat_trace),
                        len(self._pending_trace_candidates),
                        len(self._pending_skipped_cards),
                    )

            # Per-card memory update (deterministic stats)
            card_mem_updated = 0
            if allow_run_learning and self._memory.card_memory_store and stm:
                try:
                    from src.memory.card_memory_extractor import (
                        update_card_memories_from_run,
                    )

                    card_mem_updated = update_card_memories_from_run(
                        self._memory.card_memory_store,
                        stm,
                        character,
                        final_deck,
                        victory,
                        final_act=final_act,
                        incomplete=is_incomplete,
                    )
                except Exception:
                    logger.warning("Card memory update failed", exc_info=True)
            elif not allow_run_learning:
                logger.info(
                    "Skipping run-level build/card learning for incomplete run "
                    "(%s, floor %d)",
                    completion_reason, final_floor,
                )

            # Event memories (run outcome anchored at extraction time so the
            # guide consolidator can reason about each decision against the
            # eventual victory/defeat without a separate postrun LLM call)
            from src.memory.event_extractor import extract_event_memories
            event_mems = extract_event_memories(
                stm, run_id, character,
                run_victory=victory,
                run_final_floor=final_floor,
            )
            if event_mems and self._memory.event_store:
                self._memory.event_store.add_batch(event_mems)

            logger.info(
                "HCM extraction: %d combat, %d route, %d event, deck=%s, card_mem=%d",
                len(combat_eps), len(route_mems), len(event_mems),
                "yes" if final_deck else "no",
                card_mem_updated,
            )
        except Exception:
            logger.warning("HCM post-run extraction failed", exc_info=True)

    async def _analyze_build_async(self) -> None:
        """Run LLM build analysis on the just-extracted CardBuildMemory.

        Uses the pre-extracted evidence dict (immutable) — does NOT hold a
        reference to the mutable ShortTermMemory object.  Replaces the stored
        memory with a new frozen instance enriched with LLM analysis fields.
        save_all() runs after this completes, persisting the enriched version.
        """
        if not self._pending_build_mem:
            return

        build_mem, evidence = self._pending_build_mem
        self._pending_build_mem = None

        # Consume the pre-rendered combat trace (may be None when gated off).
        combat_trace_text = self._pending_combat_trace
        candidates = self._pending_trace_candidates
        skipped_cards = self._pending_skipped_cards
        self._pending_combat_trace = None
        self._pending_trace_candidates = []
        self._pending_skipped_cards = []

        try:
            from src.memory.build_role_memory import (
                apply_build_roles_to_card_memory,
                role_observations_from_analysis,
            )
            from src.memory.card_build_extractor import analyze_build_with_llm
            from src.memory.models_v2 import CardBuildMemory

            # Turn 1 — LLM build analysis, optionally with combat trace as
            # cached prefix (ephemeral cache shared with Turn 2).
            analysis = await analyze_build_with_llm(
                evidence, combat_trace_text=combat_trace_text,
            )

            if analysis and analysis.get("build_tags"):
                build_tags = tuple(analysis.get("build_tags", ()))
                primary_plan = analysis.get("primary_plan", "")
                confidence = analysis.get("confidence", 0.0)
                _OUTCOME = frozenset({"victory", "defeat"})
                legacy_arch = primary_plan or next(
                    (t for t in build_tags if t not in _OUTCOME), "",
                )

                # Create enriched memory (frozen dataclass — new instance)
                updated = CardBuildMemory(
                    memory_id=build_mem.memory_id,
                    run_id=build_mem.run_id,
                    character=build_mem.character,
                    deck_events=build_mem.deck_events,
                    card_play_counts=build_mem.card_play_counts,
                    archetype=legacy_arch,
                    build_tags=build_tags,
                    build_summary=analysis.get("build_summary", ""),
                    primary_plan=primary_plan,
                    damage_engine=analysis.get("damage_engine", ""),
                    defense_engine=analysis.get("defense_engine", ""),
                    cycle_engine=analysis.get("cycle_engine", ""),
                    energy_engine=analysis.get("energy_engine", ""),
                    weak_points=analysis.get("weak_points", ""),
                    analysis_confidence=min(0.9, max(0.1, float(confidence))),
                    key_cards=tuple(
                        (kc["card"], kc.get("role", "utility"), kc.get("insight", ""))
                        for kc in analysis.get("key_cards", [])
                        if isinstance(kc, dict) and "card" in kc
                    ),
                    coherence_score=min(1.0, max(0.0, float(analysis.get("coherence_score", 0.0)))),
                    coherence_analysis=analysis.get("coherence_analysis", ""),
                    build_evidence=evidence,
                    starting_deck=build_mem.starting_deck,
                    final_deck=build_mem.final_deck,
                    victory=build_mem.victory,
                    final_floor=build_mem.final_floor,
                    fitness=build_mem.fitness,
                    timestamp=build_mem.timestamp,
                )
                # Replace in store
                if self._memory and self._memory.card_build_store:
                    self._memory.card_build_store.replace(build_mem.run_id, updated)
                    role_updates = 0
                    if self._memory.card_memory_store:
                        observations = role_observations_from_analysis(
                            analysis,
                            character=build_mem.character,
                            run_id=build_mem.run_id,
                        )
                        role_updates = apply_build_roles_to_card_memory(
                            observations,
                            self._memory.card_memory_store,
                            character=build_mem.character,
                        )
                    logger.info(
                        "Build analysis complete: plan=%s, tags=%s, card_roles=%d",
                        primary_plan or "?",
                        build_tags,
                        role_updates,
                    )

            # Turn 2 — card note updater (only when trace is non-empty and
            # card_memory_store is available). Also absorbs the deleted
            # core_engine postrun stage on Act 3 boss victories: the merged
            # call emits an additional `core_engine` block which is parsed
            # and applied to per-card observations in the same store write.
            if combat_trace_text and self._memory and getattr(
                self._memory, "card_memory_store", None,
            ):
                from src.memory.card_note_updater import update_card_notes_from_traces
                from src.memory.core_engine_extractor import find_final_boss_combat

                # candidates were extracted from the same combats that produced the trace.
                if candidates:
                    dry = not config.POSTRUN_NOTE_UPDATE_ENABLED
                    # Gate the core_engine output on confirmed Act 3 boss
                    # victory in this run. Reuses the existing helper.
                    episodes = (
                        self._memory.combat_store.get_all()
                        if self._memory.combat_store else []
                    )
                    act3_boss = find_final_boss_combat(
                        episodes, run_id=build_mem.run_id,
                    )
                    is_act3 = act3_boss is not None and bool(
                        getattr(self._run_state, "victory", False)
                    )
                    # final_deck / final_relics serve two consumers:
                    #   1. Act3 core_engine extractor (uses act3_boss snapshot).
                    #   2. Bucket B validation (uses end-of-run state for
                    #      combo_inferred token check and "card not in deck"
                    #      rule). Both consumers benefit from the broader
                    #      end-of-run snapshot, so source from evidence and
                    #      fall back to act3_boss when act3 is the gate.
                    final_deck: list[str] = list(evidence.get("final_deck") or [])
                    final_relics: list[str] = list(self._cached_relics)
                    if act3_boss is not None:
                        if act3_boss.context and act3_boss.context.deck_cards:
                            final_deck = list(act3_boss.context.deck_cards)
                        if act3_boss.relics:
                            final_relics = list(act3_boss.relics)
                    try:
                        result = await update_card_notes_from_traces(
                            store=self._memory.card_memory_store,
                            character=build_mem.character,
                            combat_trace_text=combat_trace_text,
                            candidate_cards=candidates,
                            run_id=build_mem.run_id,
                            is_act3_boss_victory=is_act3,
                            final_deck=final_deck,
                            final_relics=final_relics,
                            skipped_cards=skipped_cards,
                            dry_run=dry,
                            session_logger=self._session_logger,
                        )
                        logger.info(
                            "postrun_trace: turn2 result %s",
                            result,
                        )
                    except Exception:
                        logger.warning("postrun_trace: Turn 2 failed", exc_info=True)

        except Exception:
            logger.warning("LLM build analysis failed (non-fatal)", exc_info=True)

    # ── Post-run skill update ────────────────────────────────────

    async def _post_run_skill_update(self) -> None:
        """Save skills, score non-combat skills, and run retirement/lifecycle policy.

        Best-effort: errors are logged but do not affect the run result.
        """
        if not self._skill_library or not self._run_state:
            return

        try:
            # Coarse non-combat outcome recording (relocated from
            # _safe_post_run body, Spec #2 §2). These skills (map,
            # deck_building, event, rest) never get COMBAT_END feedback
            # — use floor reached as a proxy. Skip when the run is too
            # short to produce meaningful evaluation.
            run_floor = (
                (self._run_state.final_floor or self._run_state._highest_floor)
                if self._run_state else 0
            )
            run_steps = self._current_step
            is_meaningful_run = run_steps >= 20 and run_floor >= 5
            if self._noncombat_skill_ids:
                if is_meaningful_run:
                    run_ok = (
                        (self._run_state.victory if self._run_state else False)
                        or run_floor >= 30
                    )
                    self._skill_library.record_outcome(
                        list(self._noncombat_skill_ids), run_ok,
                    )
                    logger.info(
                        "Non-combat skill outcome: %s (floor %d) for %d skills",
                        "ok" if run_ok else "poor",
                        run_floor,
                        len(self._noncombat_skill_ids),
                    )
                else:
                    logger.info(
                        "Skipping skill scoring — run too short (floor %d, %d steps) "
                        "to produce meaningful evaluation",
                        run_floor, run_steps,
                    )

            # Score non-combat skills once at run end
            self._score_noncombat_skills_end_of_run()

            # Mistake-driven skill discovery (relocated from memory stage,
            # Spec #2 §3.1). Gated on the cadence snapshot taken at memory-
            # stage entry so consolidate_guides exceptions don't suppress
            # discovery (Spec #2 §3.4). Runs BEFORE save so any newly
            # written probation skills land in the persisted file below.
            if (
                getattr(self, "_postrun_consolidation_active", False)
                and self._memory
                and getattr(config, "MISTAKE_DISCOVERY_ENABLED", True)
            ):
                try:
                    import os as _os

                    from src.brain.prompts.system import SYSTEM_COMBAT as _COMBAT_SYS
                    from src.skills.mistake_discovery import run_mistake_discovery

                    run_id = self._run_state.run_id if self._run_state else ""
                    this_run_episodes = [
                        e for e in self._memory.combat_store.get_all()
                        if e.run_id == run_id
                    ]
                    sl = getattr(self, "_session_logger", None)
                    log_path = getattr(sl, "log_path", None) or getattr(sl, "path", None)
                    if log_path is None:
                        log_path = Path("nul") if _os.name == "nt" else Path("/dev/null")

                    stats = await run_mistake_discovery(
                        this_run_episodes=this_run_episodes,
                        combat_store=self._memory.combat_store,
                        skill_library=self._skill_library,
                        write_gate=self._write_gate,
                        log_path=log_path,
                        run_id=run_id,
                        combat_system_prompt=_COMBAT_SYS,
                        session_logger=self._session_logger,
                    )
                    if any(v > 0 for v in stats.values()):
                        logger.info("Mistake-driven discovery: %s", stats)
                    if self._session_logger is not None and hasattr(
                        self._session_logger, "log_postrun_artifact",
                    ) and any(v > 0 for v in stats.values()):
                        try:
                            self._session_logger.log_postrun_artifact(
                                stage="skills",
                                kind="skill_discovery",
                                action="mine",
                                summary=(
                                    f"persisted={stats.get('persisted', 0)}, "
                                    f"candidates={stats.get('candidates', 0)}, "
                                    f"ab_passed={stats.get('ab_passed', 0)}"
                                ),
                                after=dict(stats),
                                source="mistake_discovery",
                            )
                        except Exception:
                            pass
                except Exception:
                    logger.warning("Mistake-driven discovery failed", exc_info=True)

            # Save current skill state (with any usage/confidence updates)
            skill_path = paths.skills_file()
            self._skill_library.save(skill_path)

            # Retirement sweep + category caps
            removed = self._skill_library.sweep_retirements()
            if removed:
                logger.info("Retired %d skills: %s", len(removed), removed)
            self._skill_library.increment_deactivated_runs()
            capped = self._skill_library.enforce_category_caps(config.MAX_ACTIVE_PER_CATEGORY)
            if capped:
                logger.info("Category cap deactivated %d skills: %s", len(capped), capped)

            # Mistake-driven post-write lifecycle: attribute each injected skill's
            # effect using per-combat baseline outcomes (§6 of spec
            # 2026-04-19-mistake-driven-skill-discovery-design.md).
            if self._skill_library and self._memory and self._run_state:
                try:
                    from src.skills.lifecycle import update_skill_usage_from_run
                    run_id_lifecycle = self._run_state.run_id or ""
                    this_run_eps_lifecycle = [
                        e for e in self._memory.combat_store.get_all()
                        if e.run_id == run_id_lifecycle
                    ]
                    update_skill_usage_from_run(
                        this_run_episodes=this_run_eps_lifecycle,
                        skill_library=self._skill_library,
                        combat_store=self._memory.combat_store,
                        usage_log_path=paths.skill_usage_log(),
                    )
                    # §6.2 retirement policy: deactivate under-performing skills
                    from src.skills.lifecycle import apply_retirement_policy
                    deactivated = apply_retirement_policy(self._skill_library)
                    if deactivated:
                        logger.info(
                            "Retired %d skills by §6.2: %s",
                            len(deactivated), deactivated,
                        )
                except Exception:
                    logger.warning("Post-write lifecycle failed", exc_info=True)

            # Re-save after retirement/cap changes
            self._skill_library.save(skill_path)

            logger.info("Skills updated: %s", self._skill_library.stats())

        except Exception:
            logger.warning("Post-run skill update failed", exc_info=True)
            raise

    # ── Post-run evolution ──────────────────────────────────────

    # ── Mode B: seed stub self-evolution (postrun stage 5) ────────

    async def _post_run_fill_stubs(self) -> None:
        """Fill / update Mode B seed stubs from postrun evidence.

        No-op unless ``config.SEED_STUB_FILL_ENABLED`` is True. When active:
        loads run history, selects current + recent_win + recent_loss,
        builds combat replays (combat/boss stubs) and Attribution Summary
        (non-combat stubs), runs StubFiller, persists library, writes
        audit log. Best-effort: errors are logged but do not block other
        postrun stages.

        Spec: docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md
        """
        if not config.SEED_STUB_FILL_ENABLED:
            return
        if getattr(self, "_skill_library", None) is None:
            return
        if getattr(self, "_run_state", None) is None:
            return

        try:
            from src.brain.v2_backend import V2Backend
            from src.runs.history import RunHistoryStore
            from src.skills.stub_evidence import (
                build_attribution_summary,
                sample_combat_replays_for_stub,
                select_runs_for_fill,
            )
            from src.skills.stub_filler import StubFiller
            from src.storage import paths
            from src.postrun.context_builder import format_combat_replay
        except Exception:
            logger.warning("Mode B stub fill: import failure", exc_info=True)
            return

        character = getattr(self._run_state, "character", "") or ""
        if not character:
            logger.info("Mode B stub fill: no character on run_state, skipping")
            return

        try:
            history_store = RunHistoryStore.load(paths.runs_history_file())
        except Exception:
            logger.warning("Mode B stub fill: failed to load run history", exc_info=True)
            return

        # Scope to the current experiment slice (or untagged personal play
        # when ``_experiment_tag`` is empty). Without this filter, an ablation
        # condition's stub-fill prompt is fed evidence from every other
        # condition, prior experiments, and ad-hoc dev runs of the same
        # character — contaminating the "from-zero self-evolution" semantics
        # the Mode B design relies on.
        history = history_store.query(
            character=character,
            # ``getattr`` keeps unit tests that bypass __init__ via
            # ``AgentLoop.__new__(AgentLoop)`` working without forcing each
            # fixture to know about this private attribute.
            experiment_tag=getattr(self, "_experiment_tag", ""),
        )
        history.sort(key=lambda r: r.started_at, reverse=True)  # newest first

        # Synthesize an anchor record for the run that JUST finished.
        # Postrun stages execute before ``history_store.append`` in
        # ``scripts/run_agent.py``, so the just-played run is not in
        # ``runs/history.jsonl`` yet. Without this prepend, ``selected_runs[0]``
        # is the previous completed run — meaning every stub fill is fed
        # evidence one run stale, and the agent never learns from the run
        # whose decisions are freshest in combat_store / card_memory_store.
        # ``select_runs_for_fill`` only reads ``.run_id`` and ``.outcome``, so
        # a SimpleNamespace duck-types correctly. ``actual_ascension`` /
        # ``started_at`` are also referenced downstream for trajectory
        # rendering and ordering.
        from types import SimpleNamespace as _SN

        rs = self._run_state
        synth_outcome = "victory" if getattr(rs, "victory", False) else "defeat"
        synth_anchor = _SN(
            run_id=getattr(rs, "run_id", "") or "",
            outcome=synth_outcome,
            actual_ascension=(
                getattr(rs, "actual_ascension", None)
                or getattr(rs, "target_ascension", None)
                or 0
            ),
            started_at=getattr(rs, "start_time", 0) or 0,
        )
        # Drop any duplicate of the synth anchor that might already be in
        # history (defensive — shouldn't happen but be robust if the call
        # order ever changes).
        if synth_anchor.run_id:
            history = [r for r in history if r.run_id != synth_anchor.run_id]
        history = [synth_anchor, *history]
        selected_runs = select_runs_for_fill(history)
        if not selected_runs:
            logger.info("Mode B stub fill: no runs in history for %s", character)
            return

        selected_run_ids = [r.run_id for r in selected_runs]

        # Episodes by run (combat_store carries cumulative episodes; filter by run_id)
        episodes_by_run: dict[str, list] = {rid: [] for rid in selected_run_ids}
        if self._memory and getattr(self._memory, "combat_store", None) is not None:
            try:
                all_eps = self._memory.combat_store.get_all()
                for ep in all_eps:
                    rid = getattr(ep, "run_id", "")
                    if rid in episodes_by_run:
                        episodes_by_run[rid].append(ep)
            except Exception:
                logger.warning("Mode B stub fill: failed to gather episodes", exc_info=True)

        # Build evidence per stub
        stubs = [s for s in self._skill_library.all_skills if s.skill_id.startswith("stub_")]
        evidence_by_stub: dict[str, str] = {}

        for stub in stubs:
            sid = stub.skill_id
            if sid.endswith(("_combat", "_boss")):
                replays = sample_combat_replays_for_stub(
                    stub_id=sid,
                    run_ids=selected_run_ids,
                    episodes_by_run=episodes_by_run,
                )
                if replays:
                    try:
                        evidence_by_stub[sid] = "\n\n".join(
                            format_combat_replay(ep) for ep in replays
                        )
                    except Exception:
                        logger.warning(
                            "Mode B stub fill: format_combat_replay failed for %s",
                            sid, exc_info=True,
                        )
            else:
                # Non-combat stubs: full trajectory per selected run + Attribution
                # Summary on the current run. Trajectory provides the
                # cross-run "agent reasoning + outcome delta" view needed for
                # the agent to abstract principles. Attribution adds the
                # deterministic card-play / death cause aggregates.
                from src.skills.stub_evidence import render_trajectory_for_stub
                parts: list[str] = []
                for r in selected_runs:
                    decisions = self._load_decisions_for_run(r.run_id)
                    traj = render_trajectory_for_stub(
                        stub_id=sid,
                        run_id=r.run_id,
                        outcome=r.outcome or "",
                        character=character,
                        ascension=getattr(r, "actual_ascension", 0) or 0,
                        decisions=decisions,
                    )
                    if traj:
                        parts.append(traj)

                # Attribution Summary for the current run only (cumulative
                # card stats already span runs in card_memory_store).
                current = selected_runs[0]
                stats = self._collect_card_play_stats_for_stubs(character)
                thread = self._collect_strategic_thread_for_stubs()
                attribution = build_attribution_summary(
                    run_id=current.run_id,
                    final_deck=[],
                    final_relics=[],
                    death_cause=current.outcome or "",
                    strategic_thread_evolution=thread,
                    card_play_stats=stats,
                )
                if attribution:
                    parts.append(attribution)

                if parts:
                    evidence_by_stub[sid] = "\n\n".join(parts)

        if not evidence_by_stub:
            logger.info("Mode B stub fill: no evidence assembled, skipping")
            return

        try:
            backend = V2Backend()
            filler = StubFiller(library=self._skill_library, backend=backend)
            # Use async concurrent variant: 5 stubs fill in parallel
            # (~30s total instead of ~150s sequential).
            summary = await filler.afill_all_stubs(
                character=character,
                evidence_by_stub=evidence_by_stub,
            )
        except Exception as exc:
            logger.warning("Mode B stub fill: filler failure: %s", exc, exc_info=True)
            return

        run_id = getattr(self._run_state, "run_id", "") or ""
        self._write_stub_fill_log(run_id=run_id, character=character, summary=summary)

        # Persist library so the new stub content survives across runs
        try:
            from pathlib import Path as _Path
            from src.storage import paths as _paths
            self._skill_library.save(_paths.skills_file())
        except Exception:
            logger.warning("Mode B stub fill: library save failed", exc_info=True)

    def _load_decisions_for_run(
        self,
        run_id: str,
        log_dir: Path | None = None,
    ) -> list:
        """Load per-decision trajectory from a run's JSONL log file.

        Reuses ``src.postrun.context_builder.load_run_log`` (which produces
        ``LoggedDecision`` objects with ``before_state`` / ``after_state``).
        Adapts each LoggedDecision to a SimpleNamespace shape consumed by
        ``src.skills.stub_evidence.render_trajectory_for_stub``.

        Returns empty list if the log file is missing or unreadable.
        """
        from types import SimpleNamespace as _SN

        try:
            from src.postrun.context_builder import load_run_log
        except Exception:
            logger.warning("load_run_log import failed", exc_info=True)
            return []

        log_path = None
        if log_dir is not None:
            log_path = Path(log_dir) / f"run_{run_id}.jsonl"

        try:
            decisions, _states = load_run_log(run_id, log_path=log_path)
        except Exception:
            logger.warning("load_run_log failed for run_id=%s", run_id, exc_info=True)
            return []

        adapted: list = []
        for d in decisions:
            action_name = ""
            option_index = -1
            if isinstance(d.action, dict):
                action_name = str(d.action.get("action", "") or "")
                option_index = int(d.action.get("option_index", -1) or -1)
            before = d.before_state
            after = d.after_state
            hp_before = before.hp if before else 0
            hp_after = after.hp if after else hp_before
            gold_before = before.gold if before else 0
            gold_after = after.gold if after else gold_before
            deck_before = before.deck_size if before else 0
            deck_after = after.deck_size if after else deck_before
            deck_change = "no change"
            if before and after and before.deck and after.deck:
                added = set(after.deck) - set(before.deck)
                removed = set(before.deck) - set(after.deck)
                if added or removed:
                    parts = []
                    if added:
                        parts.append("+" + ", +".join(sorted(added)))
                    if removed:
                        parts.append("-" + ", -".join(sorted(removed)))
                    deck_change = " ".join(parts)
            elif deck_before != deck_after:
                deck_change = f"size {deck_before}->{deck_after}"

            adapted.append(_SN(
                floor=f"F{d.floor}",
                state_type=d.state_type,
                action=action_name,
                option_index=option_index,
                reasoning=d.reasoning or "",
                strategic_note=d.strategic_note or "",
                hp_before=hp_before, hp_after=hp_after,
                gold_before=gold_before, gold_after=gold_after,
                deck_before=deck_before, deck_after=deck_after,
                deck_change=deck_change,
            ))
        return adapted

    def _collect_card_play_stats_for_stubs(self, character: str) -> dict[str, dict]:
        """Pull per-card play counts + damage/block for the current character.

        Used by build_attribution_summary in Mode B postrun. Returns empty
        dict when card_memory_store is unavailable.
        """
        if not self._memory or not getattr(self._memory, "card_memory_store", None):
            return {}
        stats: dict[str, dict] = {}
        try:
            for mem in self._memory.card_memory_store.get_all_for_character(character):
                stats[mem.card_name] = {
                    "plays": getattr(mem, "play_count", 0),
                    "total_damage": getattr(mem, "total_damage", 0),
                    "total_block": getattr(mem, "total_block", 0),
                }
        except Exception:
            logger.warning("collect_card_play_stats failed", exc_info=True)
        return stats

    def _collect_strategic_thread_for_stubs(self) -> list[tuple[str, str]]:
        """Snapshot Strategic Thread evolution from current STM for Attribution.

        Returns list of (floor_label, note) tuples, max 8 entries. Empty when
        STM is disabled or absent.
        """
        if not self._memory:
            return []
        stm = getattr(self._memory, "short_term", None)
        if stm is None:
            return []
        thread = getattr(stm, "_strategic_thread", None) or []
        out: list[tuple[str, str]] = []
        for item in thread[:8]:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append((str(item[0]), str(item[1])))
            else:
                out.append(("?", str(item)))
        return out

    def _write_stub_fill_log(
        self,
        *,
        run_id: str,
        character: str,
        summary: dict,
    ) -> None:
        """Append an audit entry to ``evolution/stub_fill_log.jsonl``."""
        import json as _json
        import time as _time
        from pathlib import Path as _Path

        log_path = _Path(config.SEED_STUB_FILL_LOG)
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            logger.warning("stub_fill_log: cannot create parent dir", exc_info=True)
            return

        entry = {
            "run_id": run_id,
            "character": character,
            "filled_count": summary.get("filled_count", 0),
            "skipped_count": summary.get("skipped_count", 0),
            "warnings_by_stub": summary.get("warnings_by_stub", {}),
            "timestamp": _time.time(),
        }
        try:
            with log_path.open("a", encoding="utf-8") as f:
                f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            logger.warning("stub_fill_log: write failed", exc_info=True)

    async def _post_run_evolution(self) -> dict[str, object]:
        """Run self-evolution after a completed run.

        Uses EvolutionEngine (separate from V2Engine) to analyze the run
        and create tools/skills/guide updates. Best-effort: errors are
        logged but do not affect the run result.
        """
        if (
            not self._run_state
            or not config.EVOLUTION_ENABLED
            or not self._use_llm
            or not config.provider_supports_tool_loop(config.get_tier_provider("evolution"))
        ):
            return {"status": "skipped", "action_count": 0}

        context_chars = 0
        try:
            from src.brain.evolution_engine import EvolutionEngine
            from src.postrun.context_builder import build_evolution_context
            from src.brain.v2_backend import V2Backend
            from src.postrun.context_builder import (
                ReplayPackage,
                build_decision_digest,
                build_replay_package,
            )

            registry = getattr(self, "_dynamic_registry", None)
            run_id = getattr(self._run_state, "run_id", "") or "unknown"
            log_path = self._session_logger.log_path if self._session_logger else None
            combat_episodes = []
            if self._memory and self._memory.combat_store:
                combat_episodes = [
                    ep for ep in self._memory.combat_store.get_all()
                    if getattr(ep, "run_id", "") == run_id
                    and not getattr(ep, "is_aborted", False)
                ]
            decision_digest = build_decision_digest(
                self._run_state,
                combat_episodes=combat_episodes,
                log_path=log_path,
            )
            replay_package = (
                build_replay_package(
                    self._memory,
                    run_id,
                    anomaly_worse_limit=config.EVOLUTION_ANOMALY_WORSE_LIMIT,
                    anomaly_better_limit=config.EVOLUTION_ANOMALY_BETTER_LIMIT,
                    replay_token_budget=config.EVOLUTION_REPLAY_TOKEN_BUDGET,
                    log_path=log_path,
                )
                if self._memory is not None
                else ReplayPackage(entries=(), estimated_tokens=0)
            )
            context_bundle = build_evolution_context(
                self._run_state,
                decision_digest,
                replay_package,
                dynamic_registry=registry,
                memory_manager=self._memory,
                skill_triggers=self._skill_trigger_log or None,
                return_bundle=True,
            )
            context_chars = len(context_bundle.text)
            artifact_dir = paths.evolution_contexts_dir(run_id)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            summary_path = artifact_dir / "summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        **context_bundle.summary,
                        "context_chars": context_chars,
                        "context_estimated_tokens": context_bundle.estimated_tokens,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            # Create a fresh backend for evolution (separate from gameplay)
            backend = V2Backend()

            # Flush state snapshots to disk before evolution so they're available
            snapshot_store = getattr(self, "_snapshot_store", None)
            if snapshot_store:
                snapshot_store.flush_to_disk()

            engine = EvolutionEngine(
                backend=backend,
                tool_executor=self._v2_tool_executor,
                dynamic_registry=registry,
                skill_library=self._skill_library,
                memory_manager=self._memory,
                tool_preprocessor=self._tool_preprocessor,
                plan_verifier=getattr(self, "_plan_verifier", None),
                snapshot_store=snapshot_store,
                session_logger=self._session_logger,
            )

            run_char = getattr(self._run_state, "character", "") or ""
            actions = await asyncio.to_thread(
                engine.run_evolution,
                context_bundle.text,
                character=run_char,
                artifact_dir=artifact_dir,
                target_input_tokens=config.EVOLUTION_TARGET_INPUT_TOKENS,
                min_rounds=config.EVOLUTION_MIN_ROUNDS,
                max_rounds=config.EVOLUTION_MAX_ROUNDS,
                read_only_rounds=config.EVOLUTION_READ_ONLY_ROUNDS,
                seen_card_names=context_bundle.seen_card_names,
                combat_trace_text=self._pending_combat_trace,
            )
            session_summary = getattr(engine, "_last_session_summary", None) or {}
            summary_path.write_text(
                json.dumps(
                    {
                        **context_bundle.summary,
                        "context_chars": context_chars,
                        "context_estimated_tokens": context_bundle.estimated_tokens,
                        "session": session_summary,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            for action in actions:
                logger.info(
                    "Evolution: %s → %s",
                    action.tool,
                    action.result[:100],
                )

            # Write evolution log and persist tool stats
            if actions:
                self._write_evolution_log(actions)
            else:
                self._write_evolution_meta_log(
                    status="noop",
                    context_profile="heavy",
                    context_chars=context_chars,
                    action_count=0,
                )
            if registry:
                registry.save_stats()
            return {
                "status": "done",
                "context_profile": "heavy",
                "context_chars": context_chars,
                "context_estimated_tokens": context_bundle.estimated_tokens,
                "action_count": len(actions),
            }
        except Exception as exc:
            self._write_evolution_meta_log(
                status="error",
                context_profile="heavy",
                context_chars=context_chars,
                action_count=0,
                error=str(exc) or type(exc).__name__,
            )
            logger.warning("Post-run evolution failed", exc_info=True)
            raise

    @staticmethod
    def _evolution_entry_name(tool: str, tool_input: dict) -> str:
        """Best-effort human-readable name for evolution log consumers."""
        for key in ("tool_name", "skill_name", "metric", "key", "guide_type"):
            value = tool_input.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return tool

    @staticmethod
    def _evolution_entry_status(result: str) -> str:
        """Normalize free-form tool output into a compact status field."""
        text = result.strip().lower()
        if text.startswith("success:"):
            return "success"
        if text.startswith("rejected:"):
            return "rejected"
        if "error" in text or text.startswith("unknown"):
            return "error"
        return "ok"

    def _write_evolution_log(self, actions: list) -> None:
        """Append evolution actions to the evolution log file."""
        import json
        log_path = paths.evolution_log_file()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        run_id = self._run_state.run_id if self._run_state else "unknown"
        with open(log_path, "a", encoding="utf-8") as f:
            for action in actions:
                entry = {
                    "run_id": run_id,
                    "action": action.tool,
                    "name": self._evolution_entry_name(action.tool, action.tool_input),
                    "status": self._evolution_entry_status(action.result),
                    "tool": action.tool,
                    "input": action.tool_input,
                    "result": action.result,
                    "timestamp": action.timestamp,
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        logger.info("Evolution log: %d actions written to %s", len(actions), log_path)

    def _write_evolution_meta_log(
        self,
        *,
        status: str,
        context_profile: str,
        context_chars: int,
        action_count: int,
        error: str | None = None,
    ) -> None:
        """Append a meta entry for noop/error evolution outcomes."""
        import json

        log_path = paths.evolution_log_file()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        run_id = self._run_state.run_id if self._run_state else "unknown"
        entry = {
            "run_id": run_id,
            "entry_type": "meta",
            "status": status,
            "context_profile": context_profile,
            "context_chars": context_chars,
            "action_count": action_count,
            "timestamp": time.time(),
        }
        if error:
            entry["error"] = error

        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # ── Stuck recovery ──────────────────────────────────────────

    async def _force_unstick(self, gs: GameState) -> Decision | None:
        """Try common escape actions when stuck in a state."""
        floor = gs.run.floor if gs.run else 0

        # Overlay catch-all: dismiss unknown modals/overlays
        avail_early = set(gs.available_actions) if gs.available_actions else set()
        if "confirm_modal" in avail_early:
            logger.warning("Force-unstick: dismissing modal via confirm_modal")
            action = actions.confirm_modal()
            await self._execute(action)
            return Decision(
                floor=floor, state_type=gs.state_type, action=action,
                reasoning="Stuck recovery: dismiss modal via confirm_modal", source="random",
            )
        if "dismiss_modal" in avail_early:
            logger.warning("Force-unstick: dismissing modal via dismiss_modal")
            action = actions.dismiss_modal()
            await self._execute(action)
            return Decision(
                floor=floor, state_type=gs.state_type, action=action,
                reasoning="Stuck recovery: dismiss modal via dismiss_modal", source="random",
            )

        # In-combat card selection: select first available card or confirm
        if gs.state_type == "hand_select" and gs.selection:
            hs = gs.selection
            if hs.can_confirm:
                action = actions.confirm_selection()
                await self._execute(action, delta_source="confirm")
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="Stuck recovery: confirm hand selection", source="random",
                )
            selectable_cards = self._selection_selectable_cards(hs)
            if selectable_cards:
                card = selectable_cards[0]
                action = actions.select_deck_card(card.index)
                await self._execute(action, delta_source=card.name)
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning=f"Stuck recovery: select {card.name}", source="random",
                )

        # Combat: force end_turn when stuck (LLM keeps failing)
        if gs.is_combat and gs.combat and gs.is_play_phase:
            action = actions.end_turn()
            await self._execute(action, delta_source="turn_end")
            if gs.combat:
                self._end_turn_sent_round = gs.combat_round
            try:
                await self._wait_for_play_phase_timed(reason="stuck_recovery:end_turn")
            except McpTimeout:
                pass
            return Decision(
                floor=floor,
                state_type=gs.state_type,
                action=action,
                reasoning="Stuck recovery: force end_turn",
                source="random",
            )

        avail = gs.available_actions

        # Rewards: use collect_rewards_and_proceed (not proceed) on reward screens
        if "collect_rewards_and_proceed" in avail:
            self._opened_card_rewards.clear()
            self._card_reward_count_before_open = None
            self._last_opened_card_index = None
            action = actions.collect_rewards_and_proceed()
            result = await self._execute(action)
            if result is not None:
                return Decision(
                    floor=floor,
                    state_type=gs.state_type,
                    action=action,
                    reasoning="Stuck recovery: collect rewards and proceed",
                    source="random",
                )

        # Try proceed only when the button is actually enabled
        # (available_actions may list "proceed" as a possible type even when disabled)
        if gs.can_proceed:
            action = actions.proceed()
            result = await self._execute(action)
            if result is not None:
                return Decision(
                    floor=floor,
                    state_type=gs.state_type,
                    action=action,
                    reasoning="Stuck recovery: proceed",
                    source="random",
                )

        # For events: try advance_dialogue, then pick option, then force proceed.
        # Some events (e.g. Wellspring) have options=[] + advance_dialogue broken,
        # but proceed works — so always try proceed as last resort for events.
        if gs.state_type == "event":
            if "choose_event_option" in avail:
                # Try first unlocked option using raw state index
                first_unlocked = None
                if gs.event:
                    for o in gs.event.options:
                        if not o.is_locked:
                            first_unlocked = o.index
                            break
                action = actions.choose_event_option(first_unlocked if first_unlocked is not None else 0)
                result = await self._execute(action)
                if result is not None and result.get("status") != "error":
                    return Decision(
                        floor=floor, state_type=gs.state_type, action=action,
                        reasoning="Stuck recovery: advance dialogue", source="random",
                    )
            if gs.event:
                available = [o for o in gs.event.options if not o.is_locked]
                if available:
                    action = actions.choose_event_option(available[0].index)  # raw state index
                    await self._execute(action)
                    return Decision(
                        floor=floor, state_type=gs.state_type, action=action,
                        reasoning="Stuck recovery: pick first event option", source="random",
                    )
            # Last resort: force proceed even if not advertised (MCP mod quirk)
            action = actions.proceed()
            result = await self._execute(action)
            if result is not None and result.get("status") != "error":
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="Stuck recovery: force proceed from event", source="random",
                )

        # Rest site: pick first enabled option
        if "choose_rest_option" in avail and gs.rest:
            enabled = [o for o in gs.rest.options if o.is_enabled]
            if enabled:
                # C# indexes into full options list — use raw state index
                action = actions.choose_rest_option(enabled[0].index)
                await self._execute(action)
                # Track rest healing for non-combat scoring
                self._track_rest_heal(gs, enabled[0].title)
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning=f"Stuck recovery: rest option {enabled[0].name}", source="random",
                )

        # Shop: leave
        if "close_shop_inventory" in avail:
            action = actions.proceed()
            await self._execute(action)
            return Decision(
                floor=floor, state_type=gs.state_type, action=action,
                reasoning="Stuck recovery: leave shop", source="random",
            )

        # Card reward: only auto-click an explicitly labeled Skip button
        skip_alt = self._find_reward_alternative(gs, "skip")
        if skip_alt is not None:
            if "choose_reward_alternative" in avail:
                action = actions.choose_reward_alternative(skip_alt[0])
            elif "skip_reward_cards" in avail:
                action = actions.skip_reward_cards()
            else:
                action = None
            if action is not None:
                await self._execute(action)
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="Stuck recovery: skip card reward", source="random",
                )

        # Bundle selection fallback
        if gs.selection and "bundle" in (gs.selection.kind or "").lower():
            logger.info("Bundle selection detected, selecting first option")
            action = actions.select_deck_card(0)
            await self._execute(action)
            return Decision(
                floor=floor, state_type=gs.state_type, action=action,
                reasoning="Stuck recovery: bundle selection fallback", source="heuristic",
            )

        # card_select stuck: try confirm_selection first (e.g. "discard 3" but only 1 card left)
        if gs.state_type == "card_select" and "confirm_selection" in avail:
            action = actions.confirm_selection()
            result = await self._execute(action, delta_source="confirm")
            if result is not None and result.get("status") != "error":
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="Stuck recovery: confirm card selection (fewer cards than required)",
                    source="random",
                )

        # Generic: try first unhandled available action as last resort
        _handled = {"proceed", "choose_rest_option", "close_shop_inventory", "skip_reward_cards",
                     "choose_reward_alternative",
                     "play_card", "end_turn", "select_deck_card", "confirm_selection",
                     "choose_event_option", "choose_reward_card", "discard_potion",
                     "buy_card", "buy_relic", "buy_potion", "remove_card_at_shop",
                     "choose_treasure_relic", "open_chest", "collect_rewards_and_proceed",
                     # Overlay-escape actions are handled by the grace-period path in
                     # _maybe_handle_overlay_grace; force_unstick must NOT shortcut that.
                     "close_capstone_overlay", "close_pause_menu"}
        remaining = [a for a in avail if a not in _handled]
        if remaining:
            action_name = remaining[0]
            logger.info("Stuck recovery: attempting first unhandled action '%s'", action_name)
            action = {"action": action_name, "params": {}}
            result = await self._execute(action)
            if result is not None:
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning=f"Stuck recovery: generic action {action_name}", source="random",
                )

        logger.warning(
            "Stuck recovery exhausted: state=%s avail=%s", gs.state_type, avail,
        )
        return None

    # ── Decision dispatch ──────────────────────────────────────

    def _query_skills(self, gs: GameState) -> tuple[str, list[str]]:
        """Query skill library for the current game state.

        Returns (skill_text, skill_ids) for prompt injection and outcome tracking.
        """
        if not self._skill_library:
            return "", []

        try:
            from src.skills.composer import compose_skill_context

            # Extract context for skill matching
            enemy_name = ""
            hand_cards: frozenset[str] = frozenset()
            context_tags: set[str] = {gs.state_type}

            # Distinguish retain from discard/exhaust for skill matching
            skill_state_type = gs.state_type
            if gs.state_type == "hand_select" and gs.selection:
                sel_prompt = (gs.selection.prompt or "").lower()
                if "retain" in sel_prompt:
                    skill_state_type = "hand_select_retain"
                    context_tags.add("retain")

            if gs.is_combat and gs.enemies:
                enemy_name = gs.enemies[0].name if gs.enemies else ""
                if len(gs.enemies) > 1:
                    context_tags.add("multi_enemy")
                # Add enemy power names as context tags for skill matching
                for enemy in gs.enemies:
                    for power in (enemy.powers or []):
                        if power.name:
                            context_tags.add(f"enemy_power:{power.name.lower()}")

            hand_cards = _skill_matching_card_names(gs)

            if gs.character:
                context_tags.add(gs.character.lower())
                context_tags.add(gs.character.lower().removeprefix("the ").strip())
            if gs.character_id:
                context_tags.add(gs.character_id.lower())

            if gs.run:
                context_tags.add(f"act{gs.act}")

            # Add relic names for any_of_relics matching (Phase 2)
            if self._cached_relics:
                for r in self._cached_relics:
                    relic_name = r.split(" (")[0]  # "Name (description)" → "Name"
                    context_tags.add(relic_name)

            # Map state_type to skill category
            category_map = {
                "monster": "combat", "elite": "combat", "boss": "boss",
                "map": "map", "event": "event", "rest_site": "rest",
                "card_reward": "deck_building", "card_select": "deck_building",
                "hand_select": "deck_building", "treasure": "deck_building",
                "relic_select": "deck_building", "shop": "deck_building",
            }
            category = category_map.get(gs.state_type, "")

            # Compute situation for skill matching (Phase 2)
            sit = None
            if gs.is_combat:
                stm = self._hcm_short_term()
                if stm:
                    sit = stm.get_current_situation_tag()

            # Deck-building decisions (card_reward, shop, hand_select, etc.)
            # use a tighter skill cap to avoid archetype hopping. See
            # config.SKILLS_MAX_PER_PROMPT_DECKBUILDING for rationale.
            _DECKBUILD_STATES = {
                "card_reward", "card_select", "shop",
                "hand_select", "hand_select_retain", "treasure",
            }
            skill_limit = (
                config.SKILLS_MAX_PER_PROMPT_DECKBUILDING
                if gs.state_type in _DECKBUILD_STATES
                else config.SKILLS_MAX_PER_PROMPT
            )
            matches = self._skill_library.query(
                state_type=skill_state_type,
                enemy_name=enemy_name,
                act=gs.act if gs.run else 1,
                hp_ratio=gs.hp_ratio,
                deck_size=len(gs.deck) if gs.deck else 0,
                hand_cards=hand_cards,
                context_tags=frozenset(context_tags),
                category=category,
                limit=skill_limit,
                situation=sit,
            )

            if matches:
                threat_lvl = ""
                if sit and hasattr(sit, "threat_level"):
                    threat_lvl = sit.threat_level
                text, ids = compose_skill_context(
                    matches,
                    threat_level=threat_lvl,
                )
                if ids:
                    logger.debug(
                        "Skills retrieved: %s",
                        ", ".join(m[0].name for m in matches[:len(ids)]),
                    )
                return text, ids

        except Exception:
            logger.warning("Skill query failed", exc_info=True)

        return "", []

    def _record_skill_triggers(self, skill_ids: list[str], gs: "GameState") -> None:
        """A4: Record skill triggers for post-run evolution context."""
        if not self._skill_library or not skill_ids:
            return
        floor = gs.floor if hasattr(gs, "floor") else 0
        enemy = ""
        if gs.is_combat and gs.enemies:
            enemy = gs.enemies[0].name
        state_type = gs.state_type if hasattr(gs, "state_type") else ""
        for sid in skill_ids:
            skill = self._skill_library.get(sid)
            name = skill.name if skill else sid[:8]
            self._skill_trigger_log.append({
                "skill_name": name,
                "skill_id": sid,
                "floor": floor,
                "enemy": enemy,
                "state_type": state_type,
                "result": "",  # filled at combat end
            })

    def _update_skill_trigger_results(self, combat_won: bool, enemy_key: str) -> None:
        """A4: Backfill combat results into skill trigger log entries.

        Only fills entries whose ``enemy`` substring-matches ``enemy_key``
        so that multi-combat runs don't cross-contaminate results.
        Uses immutable replacement (new list of new dicts).
        """
        from src.memory.enemy_keys import enemy_key_lookup

        result = "WIN" if combat_won else "LOSS"
        ek_norm = enemy_key_lookup(enemy_key)
        self._skill_trigger_log = [
            {**entry, "result": result}
            if (
                not entry["result"]
                and entry["enemy"]
                and entry["state_type"] in ("monster", "elite", "boss")
                and (
                    (entry_norm := enemy_key_lookup(entry["enemy"]))
                    and (entry_norm in ek_norm or ek_norm in entry_norm)
                )
            )
            else entry
            for entry in self._skill_trigger_log
        ]

    def _build_combat_context_for_selection(self, gs: "GameState") -> str:
        """Build combat plan context for mid-combat card selection (discard/exhaust).

        Only produces context when we are actually in combat.  Non-combat
        card selections (shop remove, event transform, rest upgrade) must
        not see stale combat variables from a previous fight.
        """
        if self._v2_combat_conversation is None:
            return ""

        parts: list[str] = []

        if self._last_played_card_name:
            parts.append(f"Triggered by: {self._last_played_card_name}")

        if self._v2_round_actions:
            parts.append(f"Already played this turn: {', '.join(self._v2_round_actions)}")

        if self._combat_plan and self._combat_plan.reasoning:
            parts.append(
                "Turn plan (computed at round start — verify against LIVE enemy "
                f"powers below; powers may have shifted): {self._combat_plan.reasoning}"
            )

        if self._combat_plan and self._combat_plan_index < len(self._combat_plan.actions):
            remaining = [
                a.card_name
                for a in self._combat_plan.actions[self._combat_plan_index:]
                if not a.is_potion
            ]
            if remaining:
                parts.append(f"Cards still needed: {', '.join(remaining)}")

        # Sly detection from runtime rules_text (no hardcoded card list)
        if gs.selection and gs.selection.cards:
            sly = [
                c.name for c in gs.selection.cards
                if c.rules_text and _re.search(r'(?<!\w)Sly\.', c.rules_text)
            ]
            if sly:
                parts.append(
                    f"!! SLY CARDS: {', '.join(sly)} — discard these to play them FREE!"
                )

        # Fallback enemy powers only when the hand_select state itself lacks
        # combat data. When gs.enemies is populated, the hand_select prompt
        # already renders full power descriptions inline in its Enemies
        # section — don't duplicate here with raw name=amount.
        if not gs.enemies and self._last_known_enemies:
            enemy_lines = []
            for e in self._last_known_enemies:
                powers = getattr(e, "powers", None) or []
                if powers:
                    power_strs = [
                        f"{p.name}={p.amount}"
                        for p in powers
                        if hasattr(p, "name") and hasattr(p, "amount")
                    ]
                    if power_strs:
                        enemy_lines.append(f"{e.name}: {', '.join(power_strs)}")
            if enemy_lines:
                parts.append(
                    f"Enemy powers (last known, state lacks combat data): "
                    f"{' | '.join(enemy_lines)}"
                )

        # Latest strategic note from combat conversation
        if (self._v2_combat_conversation
                and self._v2_combat_conversation._strategic_notes):
            latest = self._v2_combat_conversation._strategic_notes[-1]
            parts.append(f"Strategic intent (R{latest[0]}): {latest[1]}")

        return "\n".join(parts)

    @staticmethod
    def _core_available_actions(avail: list[str] | None) -> list[str]:
        """Drop meta-actions that should not drive state classification."""
        if not avail:
            return []
        return [action for action in avail if action != "save_and_quit"]

    def _is_mechanical_noncombat_state(
        self,
        gs: GameState,
        avail: list[str] | None = None,
    ) -> bool:
        """Return True when the non-combat LLM should be skipped entirely."""
        actions_now = gs.available_actions if avail is None else avail
        core_actions = self._core_available_actions(actions_now)
        mechanical_states = {
            "combat_rewards",
            "cards_view",
            "timeline",
            "game_over",
            "unknown",
        }
        mechanical_actions = {
            "proceed",
            "collect_rewards_and_proceed",
            "discard_potion",
            "start_new_run",
            "confirm_selection",
            "close_cards_view",
        }
        return (
            gs.state_type in mechanical_states
            or not actions_now
            or (core_actions and all(action in mechanical_actions for action in core_actions))
            or gs.can_proceed
        )

    def _is_forced_potion_discard_state(self, avail: list[str] | None) -> bool:
        """Return True when discarding a potion is the only meaningful action."""
        core_actions = self._core_available_actions(avail)
        return bool(core_actions) and all(action == "discard_potion" for action in core_actions)

    def _build_state_prompt_v2(self, gs: GameState) -> str:
        """Build a simplified state-only prompt for V2 non-combat decisions.

        V2 prompts strip decision frameworks and output format — the LLM
        has query tools for strategy and decision tools for output schema.
        """
        if self._is_mechanical_noncombat_state(gs):
            return ""

        relics = self._cached_relics
        deck = gs.deck or []
        if gs.is_map:
            if self._route_plan is not None:
                current_step = self._find_current_step_index(gs)
                return build_map_step_prompt(
                    gs,
                    route=self._route_plan,
                    current_step_index=current_step,
                    options=gs.next_map_options,
                    relics=relics,
                )
            # No plan — basic options list (fallback)
            fallback_lines = ["## Map Navigation",
                     f"HP: {gs.player_hp}/{gs.player_max_hp} | Gold: {gs.gold} | Act: {gs.act}",
                     "\nAvailable nodes:"]
            for opt in gs.next_map_options:
                fallback_lines.append(f"- [index={opt.index}] {opt.node_type} at c{opt.col},r{opt.row}")
            return "\n".join(fallback_lines)
        if gs.state_type == "event":
            remaining = self._build_remaining_route(gs)
            return build_event_prompt(
                gs, deck=deck, relics=relics, kb=self._knowledge,
                remaining_route=remaining,
            )
        if gs.state_type == "crystal_sphere":
            return build_crystal_sphere_prompt(gs, deck=deck, relics=relics)
        if gs.state_type == "bundle_select":
            return build_bundle_selection_prompt(gs, deck=deck, relics=relics)
        if gs.state_type == "card_reward":
            character = self._run_state.character if self._run_state else ""
            guide_store = self._memory.guide_store if self._memory else None
            return build_card_reward_prompt(
                gs, deck=deck, relics=relics,
                character=character, guide_store=guide_store,
            )
        if gs.state_type == "rest_site":
            remaining = self._build_remaining_route(gs)
            return build_rest_prompt(
                gs,
                deck=deck,
                relics=relics,
                upcoming_nodes=self._upcoming_node_types,
                remaining_route=remaining,
                smith_cards=self._smith_preview_cards,
            )
        if gs.state_type == "shop":
            character = self._run_state.character if self._run_state else ""
            guide_store = self._memory.guide_store if self._memory else None
            return build_shop_plan_prompt(
                gs, deck=deck, relics=relics,
                character=character, guide_store=guide_store,
            )
        if gs.state_type == "relic_select":
            return build_relic_select_prompt(gs, deck=deck, relics=relics)
        if gs.state_type == "card_select":
            if self._is_pack_selection(gs):
                self._sync_pack_selection_session(gs)
                self._record_pack_preview_from_selection(gs)
                if self._all_pack_previews_collected(gs):
                    return build_pack_selection_prompt(
                        gs,
                        pack_previews=self._pack_previews,
                        current_pack_index=self._pack_last_clicked_option,
                        deck=deck,
                        relics=relics,
                    )
                return ""
            ctx = self._build_combat_context_for_selection(gs)
            return build_card_select_prompt(
                gs,
                deck=deck,
                relics=relics,
                knowledge=self._knowledge,
                combat_context=ctx,
            )
        if gs.state_type == "hand_select":
            ctx = self._build_combat_context_for_selection(gs)
            return build_hand_select_prompt(gs, combat_context=ctx)
        # Treasure is handled as auto-shortcut (always mechanical), no LLM prompt needed.
        return ""

    def _build_decision_context(
        self, gs: GameState, *,
        include_knowledge: bool = True,
        include_skills: bool = True,
        include_memory: bool = True,
    ) -> dict:
        """Build a reusable context dict with knowledge, skills, and memory.

        Used by all LLM decision paths (main, combat plan, potion, route)
        to ensure consistent context injection.
        """
        ctx: dict = {}

        if gs.available_actions:
            avail = gs.available_actions
            # Filter out actions that belong to other state types to avoid
            # misleading the LLM (e.g. combat_select_card in normal combat)
            if gs.state_type not in ("hand_select", "card_select"):
                avail = [a for a in avail
                         if a not in ("select_deck_card", "confirm_selection")]
            ctx["available_actions"] = avail

        extra_context = self._build_tool_preprocessor_context(gs)
        if extra_context:
            ctx["extra_context"] = extra_context

        if include_knowledge:
            knowledge_text = self._query_knowledge(gs)
            if knowledge_text:
                ctx["knowledge_context"] = knowledge_text

        if include_memory and self._memory:
            v2_ctx = self._memory.query_for_decision(
                gs, archetype="",
                current_round=gs.combat_round if gs.is_combat else 0,
            )
            if v2_ctx is not None and not v2_ctx.is_empty:
                ctx["working_context"] = v2_ctx

        if include_skills:
            skill_text, skill_ids = self._query_skills(gs)
            if skill_text:
                ctx["skill_context"] = skill_text
                self._active_skill_ids = skill_ids
                if gs.is_combat:
                    self._combat_skill_ids.update(skill_ids)
                    # B6: accumulate injected skill IDs on the active CombatTracker
                    # for post-combat lifecycle attribution (spec §6.1). Non-combat
                    # retrievals are intentionally not tracked here.
                    _record_injected_skills(self._hcm_short_term(), skill_ids)
                else:
                    self._noncombat_skill_ids.update(skill_ids)
                    for sid in skill_ids:
                        self._noncombat_skill_counts[sid] = self._noncombat_skill_counts.get(sid, 0) + 1
                # A4: record skill trigger for evolution context
                self._record_skill_triggers(skill_ids, gs)
            else:
                self._active_skill_ids = []

        # Inject boss strategy (from background web search)
        if self._boss_strategy and gs.is_combat:
            ctx["boss_strategy"] = self._boss_strategy

        # Inject knowledge facade for prompts that need direct DB lookups
        # (e.g. card_select upgrade mode needs on_upgrade info)
        if self._knowledge:
            ctx["knowledge"] = self._knowledge

        # Token budget control: hard char caps on context fields
        for field_name, cap in _CONTEXT_CHAR_CAPS.items():
            val = ctx.get(field_name)
            if isinstance(val, str) and len(val) > cap:
                ctx[field_name] = val[:cap] + "\n...(truncated)"

        # Emit context_assembly event for monitor dashboard
        self._emit_monitor("context_assembly", {
            "state_type": gs.state_type,
            "skills": ctx.get("skill_context", "")[:1000] if ctx.get("skill_context") else "",
            "memory_type": type(ctx.get("working_context")).__name__ if ctx.get("working_context") else "none",
            "knowledge_chars": len(ctx.get("knowledge_context", "")),
            "computed_insights": ctx.get("extra_context", "")[:500] if ctx.get("extra_context") else "",
            "boss_strategy": bool(ctx.get("boss_strategy")),
        })

        return ctx

    def _build_tool_preprocessor_context(self, gs: GameState) -> str:
        """Return computed tool hints for prompt injection.

        Runs state-derived dynamic tools before gameplay decisions and formats
        successful outputs as a compact ``## Computed Insights`` block. Also
        appends a built-in Regent resource hint when applicable so the LLM
        sees current Stars + per-card star_cost summary alongside the dynamic
        tool output.
        """
        regent_hint = self._build_regent_resource_hint(gs)

        if not self._tool_preprocessor:
            return regent_hint

        try:
            hints = self._tool_preprocessor.run_applicable(gs.state_type, gs)
            text = self._tool_preprocessor.format_hints(hints)
        except Exception:
            logger.debug(
                "Tool preprocessing failed for state_type=%s",
                gs.state_type,
                exc_info=True,
            )
            return regent_hint

        self._emit_monitor("tool_preprocessing", {
            "state_type": gs.state_type,
            "floor": gs.floor,
            "combat_round": gs.combat_round,
            "tools": [hint.tool_name for hint in hints],
            "hint_count": len(hints),
            "chars": len(text),
        })

        if regent_hint and text:
            return f"{regent_hint}\n\n{text}"
        return regent_hint or text

    @staticmethod
    def _build_regent_resource_hint(gs: GameState) -> str:
        """Return a short Regent-only resource block, empty for other characters.

        Renders current Stars plus a one-line summary of Star-cost cards and
        Star providers in the current hand. Triggered only in combat; quiet
        elsewhere so non-combat prompts stay unchanged.
        """
        if not getattr(gs, "is_combat", False):
            return ""
        character = (gs.character or "").strip().lower()
        if character != "the regent":
            return ""

        raw = getattr(gs, "raw", None)
        combat = getattr(raw, "combat", None) if raw is not None else None
        player = getattr(combat, "player", None) if combat is not None else None
        if player is None:
            return ""

        stars = int(getattr(player, "stars", 0) or 0)

        consumers: list[str] = []
        providers: list[str] = []
        try:
            from src.brain.prompts._regent_economy_fmt import classify_card
        except Exception:
            classify_card = None  # type: ignore[assignment]

        for card in getattr(gs, "hand", []):
            cost = int(getattr(card, "star_cost", 0) or 0)
            x_cost = bool(getattr(card, "star_costs_x", False))
            label = card.name
            if x_cost:
                consumers.append(f"{label} (★X)")
            elif cost > 0:
                consumers.append(f"{label} (★{cost})")
            elif classify_card is not None:
                star_role, _ = classify_card(card.name)
                if star_role == "provider":
                    providers.append(label)

        if not consumers and not providers and stars == 0:
            return ""

        lines = ["## Resources (Regent)", f"Stars before turn: {stars}"]
        if consumers:
            lines.append(f"Star-cost cards in hand: {', '.join(consumers)}")
        if providers:
            lines.append(f"Star providers in hand: {', '.join(providers)}")
        return "\n".join(lines)

    async def _maybe_handle_overlay_grace(
        self, gs: GameState, avail: list[str] | None,
    ) -> Decision | None:
        """Drive grace-window state machine for a stray UI overlay.

        Caller (`_decide_and_act`) has already verified the avail set is
        "overlay-only" (no real play actions), so this method is allowed
        to short-circuit normal dispatch unconditionally.

        Returns:
            * `Decision` — grace elapsed, we fired a close action.  Caller
              must early-return so the main loop records it normally.
            * `None` — still inside the grace window.  Caller must also
              early-return, NOT continue dispatching, otherwise other
              handlers (combat plan, map planner, LLM fallback) will be
              invoked on a degenerate state and the validator will reject
              their output, aborting the run.

        Nested-overlay handling: after firing once, the timer is left in an
        already-expired state so any subsequent observation of an overlay
        (whether the same token or a fresh one revealed after the close)
        fires immediately without re-imposing the 30s grace.  The outer
        "not overlay-only" path in `_decide_and_act` clears the tracker
        once the overlay is genuinely gone, which restores the user-peek
        grace for the *next* fresh overlay.
        """
        core_actions = [a for a in (avail or []) if a != "save_and_quit"]

        # Pick the most-specific escape (pause menu wins if both present).
        overlay_action = next(
            (a for a in _OVERLAY_ESCAPE_ACTIONS if a in core_actions),
            None,
        )
        if overlay_action is None:
            # Defensive: caller's check should prevent this.
            return None

        now = time.monotonic()
        is_new_token = overlay_action != self._overlay_grace_token
        if is_new_token:
            # First observation OR the user toggled to a different overlay
            # type while still inside an existing grace.  Either way, treat
            # as a fresh user inspection and (re)start the grace timer.
            self._overlay_grace_started_at = now
            self._overlay_grace_token = overlay_action
            logger.info(
                "Stray UI overlay detected (avail=%s); will auto-close via "
                "%s after %.0fs grace (set STS2_OVERLAY_GRACE_SECONDS to tune)",
                core_actions, overlay_action, OVERLAY_AUTO_CLOSE_GRACE_SECONDS,
            )

        elapsed = now - (self._overlay_grace_started_at or now)

        if elapsed >= OVERLAY_AUTO_CLOSE_GRACE_SECONDS:
            # Grace elapsed — fire mechanical close.  Do NOT clear the
            # tracker afterwards: nested overlays (e.g. card-zoom layered
            # on deck view) require multiple close calls; leaving the
            # timer "already expired" lets subsequent observations fire
            # the next close immediately without re-imposing the 30s
            # grace.  The outer "not overlay-only" detection in
            # _decide_and_act clears the tracker when the overlay finally
            # goes away.
            action = {"action": overlay_action, "params": {}}
            result = await self._execute(action)
            if result is None:
                logger.warning(
                    "Overlay auto-close (%s) returned None; will retry next tick",
                    overlay_action,
                )
                return None
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=(
                    f"Auto-recover from stray UI overlay via {overlay_action} "
                    f"(grace={OVERLAY_AUTO_CLOSE_GRACE_SECONDS:.0f}s elapsed)"
                ),
                source="auto",
            )

        # Still inside grace — wait one poll, prevent stuck escalation by
        # resetting both the key and counter (so the main loop's else
        # branch sees a "fresh" state each tick and never reaches
        # STUCK_THRESHOLD).
        await asyncio.sleep(config.MCP_POLL_INTERVAL)
        self._stuck_key = ""
        self._stuck_count = 0
        return None

    async def _decide_and_act(self, gs: GameState, step: int) -> Decision | None:
        """Route decisions through LLM strategy or random fallback.

        Dispatch uses available_actions from the mod (with state_type fallback
        for backward compatibility when available_actions is empty).
        """
        avail = gs.available_actions

        # ── Stray UI overlay auto-recovery ────────────────────────────────
        # If the player accidentally (or deliberately) opened a UI overlay
        # while the agent was running — TopBar deck button, TopBar map button
        # mid-combat, card/relic inspect zoom, or pause menu — the mod
        # exposes only `close_capstone_overlay` / `close_pause_menu` plus
        # `save_and_quit`.  None of those are part of normal play, so the
        # agent has no productive decision to make: it can only escape.
        #
        # CRITICAL: this branch must early-return regardless of whether the
        # helper fires a close (returns Decision) or is still inside the
        # grace window (returns None).  The state_type / screen reported
        # while an overlay is up is unreliable (often "unknown" or echoes
        # the underlying screen), and falling through to LLM dispatch would
        # produce nonsense decisions like `choose_map_node` when avail
        # contains only `close_capstone_overlay` — which then fails the
        # post-LLM validator and aborts the run.
        _overlay_core = [a for a in (avail or []) if a != "save_and_quit"]
        _overlay_only = (
            bool(_overlay_core)
            and all(a in _OVERLAY_ESCAPE_ACTIONS for a in _overlay_core)
        )
        if _overlay_only:
            return await self._maybe_handle_overlay_grace(gs, avail)
        # Not in overlay-only state — clear any stale tracker so the next
        # stray overlay starts a fresh grace window.
        if self._overlay_grace_token is not None:
            self._overlay_grace_started_at = None
            self._overlay_grace_token = None

        # Enemy turn / animation: no player actions possible — wait and re-poll.
        # The mod exposes save_and_quit during enemy turns, but we should never
        # attempt a decision in this state.
        if gs.is_combat and not gs.is_play_phase:
            return None

        # Action-aware category detection (fallback to state_type)
        in_map = "choose_map_node" in avail if avail else gs.is_map
        in_combat = (
            ("play_card" in avail or "end_turn" in avail)
            if avail else gs.is_combat
        )
        in_event = (
            ("choose_event_option" in avail)
            if avail else gs.state_type == "event"
        ) and gs.state_type not in ("card_select", "hand_select")
        in_rest = (
            ("choose_rest_option" in avail or gs.state_type == "rest_site")
            if avail else gs.state_type == "rest_site"
        )
        in_cards_view = gs.state_type == "cards_view"

        # Cache upcoming node types for threat assessment in rest/shop prompts
        if in_map and gs.next_map_options:
            self._upcoming_node_types = [n.node_type for n in gs.next_map_options]

        # Single-choice map node: skip LLM and route planning, just select it
        if in_map and gs.next_map_options and len(gs.next_map_options) == 1:
            node = gs.next_map_options[0]
            self._cached_map_node_type = self._classify_map_node(node)
            # Refresh live remaining route even for single-choice nodes so that
            # rest/shop prompts downstream still see accurate path data.
            if gs.map and gs.map.nodes:
                self._refresh_live_remaining_route(
                    gs, chosen_coord=(node.col, node.row)
                )
            action = actions.choose_map_node(node.index)
            logger.info("Map auto-select (only 1 option): %s", node.node_type)
            await self._execute(action)
            try:
                await self._wait_for_state_change_timed(
                    "map",
                    reason="auto:choose_map_node",
                )
            except McpTimeout:
                pass
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Only path: {node.node_type}",
                source="auto",
            )

        # Route planning + re-plan check (multi-option map nodes only)
        if in_map and gs.next_map_options and len(gs.next_map_options) > 1:
            await self._handle_map_route_decision(gs)

        if in_cards_view:
            return await self._handle_cards_view(gs)


        # Combat turn planning: plan-then-execute (potions are included in the plan)
        if in_combat and gs.combat and gs.is_play_phase and self._use_llm and self._v2_engine:
            plan_result = await self._execute_combat_plan(gs)
            if plan_result is not None:
                return plan_result
            # V2 combat plan failed — retry once, then try fallback model
            if self._v2_engine:
                logger.warning("V2 combat plan failed, retrying once...")
                # Re-poll state in case it changed
                try:
                    raw = await self._client.get_state()
                    gs = parse_state(raw)
                except Exception:
                    pass
                # Only retry if still in a combat play phase (not card_select/hand_select)
                if gs.is_combat and gs.combat and gs.is_play_phase:
                    plan_result2 = await self._execute_combat_plan(gs)
                    if plan_result2 is not None:
                        return plan_result2
                    # Retry also failed — try fallback (analysis-tier) model
                    logger.warning(
                        "V2 combat plan failed twice for %s at floor %d, "
                        "trying fallback model...",
                        gs.state_type,
                        gs.run.floor if gs.run else 0,
                    )
                    try:
                        raw = await self._client.get_state()
                        gs = parse_state(raw)
                    except Exception:
                        pass
                    if gs.is_combat and gs.combat and gs.is_play_phase:
                        plan_result3 = await self._execute_combat_plan(
                            gs, use_fallback_model=True,
                        )
                        if plan_result3 is not None:
                            return plan_result3
                        logger.error(
                            "V2 combat plan failed with fallback model for %s "
                            "at floor %d",
                            gs.state_type,
                            gs.run.floor if gs.run else 0,
                        )
                else:
                    # State changed to card_select/hand_select/etc — let main
                    # loop handle it on next iteration (don't abort the run)
                    logger.info(
                        "State changed to %s during combat plan retry, "
                        "falling through to non-combat handler",
                        gs.state_type,
                    )
                    return None

        # Finished event: auto-proceed without LLM (e.g. Crystal Sphere after divinations)
        if in_event and gs.event and gs.event.is_finished and "proceed" in avail:
            action = actions.proceed()
            logger.info("Event finished (is_finished=True), auto-proceed")
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Event finished, proceed",
                source="auto",
            )

        # Single-choice event: skip LLM, just select it (e.g. "Proceed" button)
        if in_event and gs.event:
            available = [o for o in gs.event.options if not o.is_locked]
            if len(available) == 1:
                option = available[0]
                action = actions.choose_event_option(option.index)  # raw state index
                logger.info("Event auto-select (only 1 option): %s", option.title or "Proceed")
                result = await self._execute(action)
                if result is None:
                    # Action was rejected (e.g. option locked server-side)
                    self._locked_event_fails += 1
                    if self._locked_event_fails >= 3:
                        self._locked_event_fails = 0
                        raise RuntimeError(
                            f"Event option '{option.title}' rejected as locked after 3 "
                            f"attempts — aborting run (MCP state desync)"
                        )
                    logger.warning(
                        "Event auto-select failed for '%s' (locked?), falling through "
                        "(attempt %d/3)",
                        option.title, self._locked_event_fails,
                    )
                else:
                    self._locked_event_fails = 0
                    return Decision(
                        floor=gs.run.floor if gs.run else 0,
                        state_type=gs.state_type,
                        action=action,
                        reasoning=f"Only option: {option.title or 'Proceed'}",
                        source="auto",
                    )

        # Rest site: auto-proceed if option already used (prevents double-rest)
        # Use available_actions ("proceed" in avail) or data model fallback
        if in_rest and gs.rest and gs.can_proceed:
            action = actions.proceed()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Auto-proceed from rest (option already used)",
                source="auto",
            )

        if gs.state_type == "shop" and gs.shop:
            if self._shop_pending_leave and not gs.shop.is_open and "proceed" in avail:
                action = actions.proceed()
                await self._execute(action)
                self._shop_pending_leave = False
                self._shop_auto_opened_this_visit = False
                self._shop_plan = None
                return Decision(
                    floor=gs.run.floor if gs.run else 0,
                    state_type=gs.state_type,
                    action=action,
                    reasoning="Leave shop after closing inventory",
                    source="auto",
                )

            foul_potion_result = await self._handle_shop_foul_potion(gs)
            if foul_potion_result is not None:
                return foul_potion_result

            # Shop: silently open inventory once so the LLM sees items on this visit.
            if (
                self._use_llm
                and self._v2_engine
                and not self._shop_pending_leave
                and not self._shop_auto_opened_this_visit
                and not gs.shop.is_open
                and "open_shop_inventory" in avail
            ):
                await self._execute({"action": "open_shop_inventory"})
                self._shop_auto_opened_this_visit = True
                await asyncio.sleep(0.3)
                # Re-poll state so LLM sees the open shop with items
                try:
                    raw = await self._client.get_state()
                    gs = parse_state(raw)
                    avail = gs.available_actions
                except Exception:
                    pass  # If re-poll fails, continue with old state

        # ── Shop Plan: mechanical execution of active plan ──
        if gs.state_type == "shop" and gs.shop and gs.shop.is_open:
            if self._shop_plan and not self._shop_plan.is_complete:
                result = await self._execute_shop_plan_step(gs)
                if result:
                    return result
                # result is None → plan discarded, fall through to LLM replan

            # Plan complete → leave shop
            if self._shop_plan and self._shop_plan.is_complete:
                if self._shop_plan.strategic_note:
                    fake_dec = LLMDecision(
                        action_name="proceed",
                        params={"strategic_note": self._shop_plan.strategic_note},
                        reasoning=self._shop_plan.reasoning,
                    )
                    self._record_strategic_note(fake_dec, "shop")
                self._shop_plan = None
                if "close_shop_inventory" in avail:
                    await self._execute({"action": "close_shop_inventory"})
                    self._shop_pending_leave = True
                    return Decision(
                        floor=gs.run.floor if gs.run else 0,
                        state_type=gs.state_type,
                        action={"action": "close_shop_inventory"},
                        reasoning="Shop plan complete — leaving",
                        source="plan",
                    )
                elif "proceed" in avail:
                    action = actions.proceed()
                    await self._execute(action)
                    self._shop_pending_leave = False
                    self._shop_auto_opened_this_visit = False
                    return Decision(
                        floor=gs.run.floor if gs.run else 0,
                        state_type=gs.state_type,
                        action=action,
                        reasoning="Shop plan complete — leaving",
                        source="plan",
                    )

        # ── Treasure: always mechanical (only ever 1 relic, no reason to skip) ──
        if gs.state_type == "treasure":
            return await self._handle_treasure(gs)

        # ── Crystal Sphere auto-proceed: if the minigame is finished and only
        # `crystal_sphere_proceed` is actionable, skip LLM and proceed.
        if (
            gs.state_type == "crystal_sphere"
            and gs.crystal_sphere is not None
            and gs.crystal_sphere.is_finished
            and gs.crystal_sphere.can_proceed
            and not gs.crystal_sphere.clickable_cells
            and not gs.crystal_sphere.can_use_big_tool
            and not gs.crystal_sphere.can_use_small_tool
        ):
            action = actions.crystal_sphere_proceed()
            logger.info("Crystal Sphere finished — auto-proceed")
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Crystal Sphere minigame finished, proceeding",
                source="auto",
            )

        # ── Combat plan discard: if last played action has a discard field, use it ──
        # Uses _last_played_plan_action which survives plan invalidation (draw-card re-plan)
        # SKIP for draw-then-discard cards (Acrobatics, Prepared, etc.): the plan wrote
        # the discard target before drawing — newly drawn cards (Sly, curses, status)
        # may be better targets.  Fall through to LLM hand_select instead.
        _plan_discard_is_draw_card = (
            self._last_played_card_rules
            and is_draw_card(self._last_played_card_rules)
        )
        if (gs.state_type in ("card_select", "hand_select")
                and gs.selection
                and self._last_played_plan_action is not None
                and self._last_played_plan_action.discard
                and not _plan_discard_is_draw_card):
            discard_specs = self._normalize_discard_specs(self._last_played_plan_action.discard)
            sel_cards = self._selection_selectable_cards(gs.selection)
            if discard_specs:
                if self._card_select_target == 0:
                    target = 0
                    if gs.selection.prompt:
                        target = self._parse_select_count_from_prompt(gs.selection.prompt)
                    if target == 0:
                        target = (
                            gs.selection.max_select
                            if gs.selection.max_select and gs.selection.max_select > 0
                            else 0
                        )
                    self._card_select_target = max(target, len(discard_specs), 1)
                    self._card_select_progress = self._selection_selected_count(gs.selection)

                already_made = self._selection_session_progress(gs.selection)
                remaining_needed = max(self._card_select_target - already_made, 0)

                if remaining_needed > 0:
                    executed_names: list[str] = []
                    pending_specs = list(discard_specs)
                    unresolved_specs: list[str] = []
                    action = None
                    current_gs = gs
                    made = already_made

                    while remaining_needed > 0 and current_gs.selection and pending_specs:
                        current_cards = self._selection_selectable_cards(current_gs.selection)
                        matched_at = -1
                        match = None
                        for spec_idx, discard_spec in enumerate(pending_specs):
                            candidate = self._resolve_discard_name(discard_spec, current_cards)
                            if candidate is None:
                                continue
                            matched_at = spec_idx
                            match = candidate
                            break

                        if match is None:
                            unresolved_specs = pending_specs.copy()
                            break

                        select_action = actions.select_deck_card(match.index)
                        if action is None:
                            action = select_action
                        await self._execute(select_action, delta_source=match.name)
                        # Detect Sly trigger: discard by card effect → auto-play
                        if self._is_sly_discard(match, current_gs):
                            self._hcm_record_card_play(match.name, energy_cost=0)
                            self._hcm_record_sly_play(match.name)
                            logger.info("Sly trigger (plan-discard): %s", match.name)
                        self._record_selection_choice(current_gs, match.index)
                        executed_names.append(match.name)
                        pending_specs.pop(matched_at)
                        made = self._selection_session_progress(current_gs.selection)
                        remaining_needed = max(self._card_select_target - made, 0)
                        if remaining_needed <= 0:
                            break

                        await asyncio.sleep(0.3)
                        fresh = await self._refresh_selection_state()
                        if not fresh or not fresh.selection:
                            break
                        current_gs = fresh
                        made = self._selection_session_progress(current_gs.selection)
                        remaining_needed = max(self._card_select_target - made, 0)

                    if action is not None:
                        logger.info(
                            "Plan-directed discard: selected=%s made=%d/%d (from '%s')",
                            executed_names,
                            made,
                            self._card_select_target,
                            self._last_played_card_name,
                        )

                        if made >= self._card_select_target:
                            confirm_state = current_gs
                            if self._card_select_target > 1 or gs.selection.can_confirm:
                                await asyncio.sleep(0.3)
                                fresh = await self._refresh_selection_state()
                                if fresh and fresh.selection:
                                    confirm_state = fresh
                                if (
                                    confirm_state
                                    and confirm_state.selection
                                    and "confirm_selection" in confirm_state.available_actions
                                ):
                                    confirm = actions.confirm_selection()
                                    try:
                                        await self._execute(confirm, delta_source="confirm")
                                    except (McpActionError, McpError) as exc:
                                        logger.warning(
                                            "Plan-directed discard confirm failed "
                                            "(may auto-process): %s",
                                            exc,
                                        )
                                else:
                                    logger.info(
                                        "Plan-directed discard already auto-processed "
                                        "after %d picks; skipping confirm",
                                        made,
                                    )
                            self._reset_card_select_tracking()
                            self._last_played_plan_action = None
                            return Decision(
                                floor=gs.run.floor if gs.run else 0,
                                state_type=gs.state_type,
                                action=action,
                                reasoning=(
                                    "Plan discard: "
                                    f"{', '.join(executed_names)} "
                                    f"(planned with {self._last_played_card_name})"
                                ),
                                source="plan",
                            )

                        if unresolved_specs:
                            logger.warning(
                                "Plan discard partially matched: unresolved=%s options=%s",
                                unresolved_specs,
                                [c.name for c in self._selection_selectable_cards(current_gs.selection)],
                            )
                        return Decision(
                            floor=gs.run.floor if gs.run else 0,
                            state_type=gs.state_type,
                            action=action,
                            reasoning=(
                                "Plan discard progress: "
                                f"{', '.join(executed_names)} "
                                f"({made}/{self._card_select_target})"
                            ),
                            source="plan",
                        )

                    logger.warning(
                        "Plan discard %s not found in options %s, falling through to LLM",
                        discard_specs,
                        [c.name for c in sel_cards],
                    )
                    self._last_played_plan_action = None

        if _plan_discard_is_draw_card and self._last_played_plan_action is not None:
            logger.info(
                "Draw-then-discard card '%s': ignoring plan discard '%s', "
                "deferring to LLM for post-draw hand evaluation",
                self._last_played_card_name,
                self._last_played_plan_action.discard,
            )
            self._last_played_plan_action = None

        # Auto-confirm card_select/hand_select when selection is already made
        # Check API can_confirm OR our own selection count tracking
        _cs_done = (
            self._card_select_target > 0
            and self._selection_session_progress(getattr(gs, "selection", None)) >= self._card_select_target
        )
        # Also auto-confirm when no more cards can be selected (e.g. "discard 3" but only 1 card left)
        _no_more_selectable = (
            gs.state_type in ("card_select", "hand_select")
            and "confirm_selection" in avail
            and "select_deck_card" not in avail
        )
        _selection_ready = (
            _cs_done
            or _no_more_selectable
            or (
                gs.selection is not None
                and gs.selection.can_confirm
                and self._selection_has_choice_made(gs.selection)
            )
        )
        if (
            gs.state_type in ("card_select", "hand_select")
            and _selection_ready
            and not self._is_pack_selection(gs)
            and (
                gs.selection is not None
                or (gs.state_type == "card_select" and _no_more_selectable)
            )
        ):
            logger.info(
                "Auto-confirm path: can_confirm=%s, made=%d/%d",
                getattr(gs.selection, "can_confirm", False),
                self._selection_session_progress(getattr(gs, "selection", None)),
                self._card_select_target,
            )
            if gs.state_type == "hand_select":
                return await self._handle_hand_select(gs)
            return await self._handle_card_select(gs)

        if gs.state_type == "card_select" and self._is_pack_selection(gs):
            preview_result = await self._handle_pack_selection_preview(gs)
            if preview_result is not None:
                return preview_result

        if (
            gs.state_type == "hand_select"
            and gs.selection
            and gs.selection.min_select == 0
            and "confirm_selection" in avail
            and not self._v2_combat_conversation
        ):
            logger.info(
                "Optional hand_select without combat conversation; using mechanical fallback"
            )
            return await self._handle_hand_select(gs)

        # ── V2 path: tool-use agent for non-combat decisions ──
        if self._v2_engine and not in_combat and self._use_llm:
            try:
                if self._v2_tool_executor:
                    self._v2_tool_executor.set_game_state(gs)
                # Pre-fetch Smith card data from MCP for rest_site decisions
                if gs.state_type == "rest_site" and gs.rest:
                    smith_cards = await self._gather_smith_preview(gs)
                    if smith_cards is not None:
                        self._smith_preview_cards = smith_cards
                    else:
                        self._smith_preview_cards = None
                else:
                    self._smith_preview_cards = None

                # Build state prompt (V1 framework code removed)
                state_prompt = self._build_state_prompt_v2(gs)
                if state_prompt:
                    ctx = self._build_decision_context(gs)
                    # Format WorkingContext → string
                    memory_str = ""
                    wc = ctx.get("working_context")
                    if wc is not None:
                        from src.memory.prompt_injector import format_working_context
                        memory_str = format_working_context(wc)
                    v2_decision = await self._v2_engine.decide_noncombat(
                        gs,
                        state_prompt,
                        extra_context=ctx.get("extra_context", ""),
                        skill_context=ctx.get("skill_context", ""),
                        memory_context=memory_str,
                        knowledge_context=ctx.get("knowledge_context", ""),
                    )
                    if v2_decision:
                        # Shop plan: parse multi-purchase plan
                        if gs.state_type == "shop":
                            plan = self._parse_shop_plan(v2_decision.params)
                            if plan is not None:
                                if plan.items:
                                    self._shop_plan = plan
                                    logger.info(
                                        "Shop plan created: %d purchases — %s",
                                        len(plan.items), plan.reasoning[:100],
                                    )
                                    result = await self._execute_shop_plan_step(gs)
                                    if result:
                                        return result
                                    # Plan discarded during first step (e.g. LLM picked
                                    # remove_card_at_shop when card_removal was already
                                    # used, or chose a sold-out item). Retry once with
                                    # explicit feedback; if retry also fails, close the
                                    # shop instead of fatally aborting the run.
                                    invalid_first_item = plan.items[0] if plan.items else None
                                    feedback = self._summarize_shop_plan_invalid_state(
                                        gs, invalid_first_item,
                                    )
                                    logger.info("Shop plan retry with feedback: %s", feedback)
                                    retry_prompt = (
                                        f"{state_prompt}\n\n"
                                        f"## IMPORTANT — Previous Shop Plan Rejected\n"
                                        f"{feedback}\n"
                                        "Re-plan with the constraints above. If nothing in "
                                        "the shop is worth buying given the current state, "
                                        "return an empty `purchases` list to leave the shop."
                                    )
                                    v2_retry = await self._v2_engine.decide_noncombat(
                                        gs,
                                        retry_prompt,
                                        extra_context=ctx.get("extra_context", ""),
                                        skill_context=ctx.get("skill_context", ""),
                                        memory_context=memory_str,
                                        knowledge_context=ctx.get("knowledge_context", ""),
                                    )
                                    if v2_retry:
                                        retry_plan = self._parse_shop_plan(v2_retry.params)
                                        if retry_plan is not None and retry_plan.items:
                                            self._shop_plan = retry_plan
                                            logger.info(
                                                "Shop plan (retry) created: %d purchases — %s",
                                                len(retry_plan.items),
                                                retry_plan.reasoning[:100],
                                            )
                                            retry_result = await self._execute_shop_plan_step(gs)
                                            if retry_result:
                                                return retry_result
                                        # retry returned empty plan or also failed → fall through
                                    # Graceful fallback: close shop rather than abort.
                                    if "close_shop_inventory" in avail:
                                        logger.warning(
                                            "Shop plan unrecoverable; closing shop to avoid abort"
                                        )
                                        self._shop_plan = None
                                        await self._execute({"action": "close_shop_inventory"})
                                        self._shop_pending_leave = True
                                        return Decision(
                                            floor=gs.run.floor if gs.run else 0,
                                            state_type=gs.state_type,
                                            action={"action": "close_shop_inventory"},
                                            reasoning="Shop plan unrecoverable after retry — leaving shop",
                                            source="plan",
                                        )
                                    # close not available — fall through to legacy paths
                                else:
                                    # Buy nothing
                                    logger.info("Shop plan: buy nothing — %s", plan.reasoning[:100])
                                    if plan.strategic_note:
                                        fake_dec = LLMDecision(
                                            action_name="proceed",
                                            params={"strategic_note": plan.strategic_note},
                                            reasoning=plan.reasoning,
                                        )
                                        self._record_strategic_note(fake_dec, "shop")
                                    if "close_shop_inventory" in avail:
                                        await self._execute({"action": "close_shop_inventory"})
                                        self._shop_pending_leave = True
                                        return Decision(
                                            floor=gs.run.floor if gs.run else 0,
                                            state_type=gs.state_type,
                                            action={"action": "close_shop_inventory"},
                                            reasoning=f"Shop plan: nothing to buy — {plan.reasoning[:80]}",
                                            source="llm",
                                        )
                                    elif "proceed" in avail:
                                        action = actions.proceed()
                                        await self._execute(action)
                                        self._shop_pending_leave = False
                                        self._shop_auto_opened_this_visit = False
                                        self._shop_plan = None
                                        return Decision(
                                            floor=gs.run.floor if gs.run else 0,
                                            state_type=gs.state_type,
                                            action=action,
                                            reasoning=f"Shop plan: nothing to buy — {plan.reasoning[:80]}",
                                            source="llm",
                                        )
                            # Plan parsing failed — fall through to retry/fallback
                        else:
                            result, val_error = await self._execute_llm_decision(
                                gs, v2_decision, DecisionSource.LLM,
                            )
                            if result:
                                self._record_strategic_note(v2_decision, gs.state_type)
                                return result
                            logger.warning("V2 decision failed validation: %s", val_error)

                            # ── V2 retry: inject error feedback and try again ──
                            if val_error:
                                logger.info("V2 retry with error feedback: %s", val_error)
                                retry_prompt = (
                                    f"{state_prompt}\n\n"
                                    f"## IMPORTANT — Previous Attempt Failed\n"
                                    "Your previous action "
                                    f"`{v2_decision.action_name}` was rejected: {val_error}\n"
                                    f"Available actions: {avail}\n"
                                    f"Choose a DIFFERENT action from the available list."
                                )
                                v2_retry = await self._v2_engine.decide_noncombat(
                                    gs,
                                    retry_prompt,
                                    extra_context=ctx.get("extra_context", ""),
                                    skill_context=ctx.get("skill_context", ""),
                                    memory_context=memory_str,
                                    knowledge_context=ctx.get("knowledge_context", ""),
                                )
                                if v2_retry:
                                    result2, val_error2 = await self._execute_llm_decision(
                                        gs, v2_retry, DecisionSource.LLM,
                                    )
                                    if result2:
                                        self._record_strategic_note(v2_retry, gs.state_type)
                                        return result2
                                    logger.warning("V2 retry also failed: %s", val_error2)
                    else:
                        logger.warning("V2 engine returned None for %s", gs.state_type)
            except Exception as exc:
                err_msg = f"V2 non-combat decision failed: {type(exc).__name__}({exc})"
                logger.error(err_msg)
                if self._session_logger:
                    self._session_logger.log_error(err_msg, step)

        if (
            gs.state_type == "hand_select"
            and gs.selection
            and gs.selection.min_select == 0
            and "confirm_selection" in avail
        ):
            logger.warning(
                "Optional hand_select unresolved by LLM path; confirming empty selection"
            )
            return await self._handle_hand_select(gs)

        # Mandatory hand_select fallback: LLM failed but we must pick cards
        if (
            gs.state_type == "hand_select"
            and gs.selection
            and "select_deck_card" in avail
        ):
            logger.warning(
                "Mandatory hand_select unresolved by LLM path; falling back to mechanical"
            )
            return await self._handle_hand_select(gs)

        # Mandatory card_select fallback: LLM failed but we must pick cards
        # (e.g. Demon Glass deck_card_select, event-triggered selections)
        if (
            gs.state_type == "card_select"
            and ("select_deck_card" in avail or "confirm_selection" in avail)
        ):
            logger.warning(
                "card_select unresolved by LLM path; falling back to mechanical"
            )
            return await self._handle_card_select(gs)

        # ── Mechanical-only states: proceed, collect_rewards, etc. ──
        # Empty avail usually means a transitional state (enemy turn, animation),
        # which is always safe to handle mechanically.
        if self._is_mechanical_noncombat_state(gs, avail):
            return await self._handle_mechanical(gs)

        # ── LLM failed for a high-risk decision state — abort rather than guess ──
        if self._v2_engine:
            # Only show conversation status for combat states where it's meaningful.
            # For non-combat states (event, shop, rest, etc.) _v2_combat_conversation
            # is always None by design, so reporting it as "MISSING" is misleading.
            _combat_states = {"monster", "elite", "boss"}
            if gs.state_type in _combat_states:
                conv_status = "present" if self._v2_combat_conversation else "MISSING"
                extra = f" [conversation={conv_status}]"
            else:
                extra = ""
            msg = (
                f"LLM decision failed for {gs.state_type} "
                f"(avail={avail}), aborting to prevent random play"
                f"{extra}"
            )
            logger.error(msg)
            raise RuntimeError(msg)

        # No-LLM mode: fall back to mechanical
        return await self._handle_mechanical(gs)

    # ── Combat plan execution ─────────────────────────────────

    def _remap_plan_target(
        self, planned_target: int, current_enemies: list,
    ) -> int | None:
        """Remap a plan-time target_index to the enemy's current positional index.

        Upstream excludes dead enemies and re-enumerates survivors 0..N-1, so a
        plan-time index can refer to an enemy that now sits at a different slot
        (or has died). We walk the plan-time ``enemy_id`` snapshot and the
        current enemy list in lockstep, pairing them by id in order so duplicate
        enemy types map to the correct surviving instance.

        Returns the current ``index`` if the intended enemy is still alive, or
        ``None`` if it died (caller should fall back / skip).
        """
        snapshot = self._combat_plan_enemy_ids
        if (
            snapshot is None
            or planned_target < 0
            or planned_target >= len(snapshot)
        ):
            return None
        j = 0
        for i, snap_eid in enumerate(snapshot):
            if j < len(current_enemies) and current_enemies[j].enemy_id == snap_eid:
                # Snapshot position i pairs with current_enemies[j]
                if i == planned_target:
                    return current_enemies[j].index
                j += 1
            else:
                # No pairing — snapshot enemy at position i died.
                if i == planned_target:
                    return None
        return None

    async def _execute_combat_plan(
        self, gs: GameState, *, use_fallback_model: bool = False,
    ) -> Decision | None:
        """Execute the next action from the combat turn plan.

        Plan-then-execute flow:
        1. If no plan or plan is for a different round → generate new plan
        2. Execute the next planned action (resolve card name to index)
        3. If the card is a draw-card, discard remaining plan (re-plan next step)
        4. If plan is exhausted → send end_turn

        Returns a Decision on success, or None to fall through to single-card LLM.
        """
        combat = gs.combat
        if not combat or not gs.is_play_phase:
            return None

        current_round = gs.combat_round
        floor = gs.run.floor if gs.run else 0

        # Skill eval: track round counter
        if self._skill_eval_state in ("active", "final"):
            if current_round > self._eval_round_count:
                self._eval_round_count = current_round

        # HCM: track round-level memory (once per round)
        if current_round != self._last_combat_round:
            # V2: record execution results from previous round into conversation
            if (
                self._v2_combat_conversation
                and self._v2_round_actions
                and self._last_combat_round >= 0
            ):
                try:
                    self._v2_combat_conversation.add_execution_result(
                        self._v2_round_actions, gs,
                    )
                except Exception:
                    pass
            self._v2_round_actions = []
            self._last_combat_round = current_round
            self._hcm_start_round(gs)

        # Honor end_turn already sent this round even when playable cards remain
        # (e.g. retained 0-cost Shivs from Phantom Blades). The previous plan
        # explicitly chose end_turn; replanning here would discard that intent
        # and the leftover cards are typically deliberate retains. The game
        # will transition to enemy turn shortly; just wait for it.
        if current_round == self._end_turn_sent_round:
            return None

        # If no playable cards, just end turn (don't waste LLM call)
        playable = gs.playable_cards
        if not playable:
            # ── Skill eval: kill/death detection before end_turn (no playable cards) ──
            if self._skill_eval_state == "active":
                if self._poison_kills_all_enemies(gs):
                    logger.info("Skill eval: POISON KILL DETECTED (no-playable shortcut)")
                    self._eval_round_count = current_round
                    await self._handle_eval_terminal(gs, won=True)
                    return Decision(
                        floor=floor, state_type=gs.state_type,
                        action=actions.end_turn(),
                        reasoning="Skill eval: poison kill detected, save and swap",
                        source="eval",
                    )
                incoming = compute_total_incoming(gs.enemies)
                player_block = gs.raw.combat.player.block if gs.raw.combat else 0
                effective_hp = gs.player_hp + player_block
                if incoming >= effective_hp:
                    logger.info(
                        "Skill eval: DEATH DETECTED (no-playable shortcut) "
                        "— incoming %d >= effective HP %d",
                        incoming, effective_hp,
                    )
                    self._eval_round_count = current_round
                    await self._handle_eval_terminal(gs, won=False)
                    return Decision(
                        floor=floor, state_type=gs.state_type,
                        action=actions.end_turn(),
                        reasoning="Skill eval: death detected, save and swap",
                        source="eval",
                    )
            self._end_turn_sent_round = current_round
            self._combat_plan = None
            action = actions.end_turn()
            await self._execute(action, delta_source="turn_end")
            try:
                await self._wait_for_play_phase_timed(reason="combat_plan:no_playable")
            except McpTimeout:
                pass
            return Decision(
                floor=floor, state_type=gs.state_type, action=action,
                reasoning="No playable cards, end turn", source="plan",
            )

        # No-target mode: all enemies dead/invulnerable (e.g. Subject phase
        # transition). Playable cards exist (energy-wise) but target-requiring
        # cards cannot execute. Either replan with explicit no-target context,
        # or end_turn if we already tried this round.
        if not gs.enemies:
            if self._no_target_replan_round == current_round:
                if current_round == self._end_turn_sent_round:
                    return None
                logger.info(
                    "Combat: no alive enemies at round %d, already replanned this round — ending turn",
                    current_round,
                )
                self._end_turn_sent_round = current_round
                self._combat_plan = None
                action = actions.end_turn()
                await self._execute(action, delta_source="turn_end")
                try:
                    await self._wait_for_play_phase_timed(
                        reason="combat_plan:no_target_fallback",
                    )
                except McpTimeout:
                    pass
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="No alive enemies, no-target replan exhausted — end turn",
                    source="plan",
                )
            logger.info(
                "Combat: no alive enemies at round %d — entering no-target replan mode",
                current_round,
            )
            self._no_target_replan_round = current_round
            plan = await self._generate_combat_plan(
                gs, is_replan=True,
                use_fallback_model=use_fallback_model,
                no_target_mode=True,
            )
            if plan is None:
                return None
            self._combat_plan = plan
            self._combat_plan_index = 0
            self._combat_plan_round = current_round
            self._combat_plan_alive = set()
            self._combat_plan_enemy_ids = tuple(e.enemy_id for e in gs.enemies)
            self._emit_monitor(
                "combat_plan",
                self._build_combat_plan_event(
                    plan, no_target_mode=True, trigger_kind="no_target",
                ),
            )
            # Fall through to normal plan-execution path below; if plan is
            # empty with end_turn=True the existing empty-plan branch handles it.

        # Generate new plan if needed (new round, or no plan after a trigger
        # cleared it). NOTE: plan exhaustion is handled below at the
        # `idx >= len(plan.actions)` branch, which honors `plan.end_turn`. Do
        # NOT re-enter the planner here just because the plan is used up — the
        # LLM already decided what to do at the end (end_turn=True or fall
        # through to single-card path), and re-asking burns an extra LLM call
        # that mislabels itself as a re-plan.
        if (
            self._combat_plan is None
            or self._combat_plan_round != current_round
        ):
            # Re-plan within the same round (draw-card split, validation failure)
            # uses fast tier; fresh round plan uses strategic tier
            is_replan = (
                self._combat_plan is None
                and self._combat_plan_round == current_round
            )
            plan = await self._generate_combat_plan(
                gs, is_replan=is_replan,
                use_fallback_model=use_fallback_model,
            )
            if plan is None:
                # LLM plan failed — return None to let single-card LLM try.
                # Keep _replan_trigger_desc/_kind populated so the next retry
                # within the same round can still build an accurate replan_ctx.
                return None
            new_round = current_round != self._combat_plan_round
            # Capture for the monitor emit before the new-round cleanup wipes
            # _replan_trigger_kind (so the dashboard sees what just triggered).
            if new_round:
                emit_trigger_kind = "fresh_round"
            elif is_replan:
                emit_trigger_kind = self._replan_trigger_kind or "validation_retry"
            else:
                emit_trigger_kind = "fresh_round"
            self._combat_plan = plan
            self._combat_plan_index = 0
            self._combat_plan_round = current_round
            if new_round:
                # Round actually advanced — drop trigger state from the
                # previous round so it cannot leak into a fresh-round replan
                # if the next iteration somehow re-enters the elif branch.
                self._prev_combat_plan = None
                self._replan_trigger_desc = ""
                self._replan_trigger_kind = ""
            # Snapshot alive enemies so we can detect deaths mid-plan
            self._combat_plan_alive = {e.index for e in gs.enemies}
            # Positional snapshot of enemy_ids — remap plan-time target_index
            # to current index when enemies die and upstream renumbers survivors.
            self._combat_plan_enemy_ids = tuple(e.enemy_id for e in gs.enemies)

            # Emit combat_plan to monitor
            self._emit_monitor(
                "combat_plan",
                self._build_combat_plan_event(
                    plan, trigger_kind=emit_trigger_kind,
                ),
            )

            # Record strategic note for future rounds
            if plan.note_to_future_self and self._v2_combat_conversation:
                self._v2_combat_conversation.record_strategic_note(
                    self._v2_combat_conversation._round_count,
                    plan.note_to_future_self,
                )
                # Also mirror into STM combat tracker so postrun can attach
                # the full decision chain to combat summaries / replay entries.
                stm = self._hcm_short_term()
                if stm is not None and stm.current_combat is not None:
                    stm.current_combat.record_strategic_note(plan.note_to_future_self)

            # Re-poll game state after plan generation (LLM call takes 2+ seconds,
            # hand may have changed due to animations or lingering card plays)
            try:
                raw = await self._client.get_state()
                fresh_gs = parse_state(raw)
                if fresh_gs.is_combat and fresh_gs.combat and fresh_gs.is_play_phase:
                    gs = fresh_gs
                    combat = gs.combat
                    floor = gs.run.floor if gs.run else 0
                else:
                    # Combat ended during plan generation — discard plan
                    self._combat_plan = None
                    return None
            except Exception:
                pass  # Use original gs if re-poll fails

            # If plan is empty, only trust it when the model explicitly chose end_turn.
            if plan.is_empty:
                playable_after_plan = gs.playable_cards
                if plan.end_turn:
                    logger.info(
                        "Combat plan: LLM chose empty plan (end turn) with %d playable cards — "
                        "trusting strategic decision. Reasoning: %s",
                        len(playable_after_plan),
                        (plan.reasoning or "")[:100],
                    )
                elif playable_after_plan:
                    logger.warning(
                        "Combat plan: LLM returned empty plan but %d playable cards remain "
                        "(end_turn=False) — falling through to single-card path",
                        len(playable_after_plan),
                    )
                    self._combat_plan = None
                    return None
                else:
                    logger.info(
                        "Combat plan: empty plan with no playable cards after re-poll — ending turn"
                    )

                if current_round == self._end_turn_sent_round:
                    return None
                # ── Skill eval: kill/death detection before end_turn (empty plan) ──
                if self._skill_eval_state == "active":
                    # Poison kill: if poison will kill all enemies on their turn
                    if self._poison_kills_all_enemies(gs):
                        logger.info("Skill eval: POISON KILL DETECTED — all enemies die from poison")
                        self._eval_round_count = current_round
                        await self._handle_eval_terminal(gs, won=True)
                        return Decision(
                            floor=floor, state_type=gs.state_type,
                            action=actions.end_turn(),
                            reasoning="Skill eval: poison kill detected, save and swap",
                            source="eval",
                        )
                    # Death: incoming damage will kill us
                    incoming = compute_total_incoming(gs.enemies)
                    player_block = gs.raw.combat.player.block if gs.raw.combat else 0
                    effective_hp = gs.player_hp + player_block
                    if incoming >= effective_hp:
                        logger.info(
                            "Skill eval: DEATH DETECTED — incoming %d >= effective HP %d",
                            incoming, effective_hp,
                        )
                        self._eval_round_count = current_round
                        await self._handle_eval_terminal(gs, won=False)
                        return Decision(
                            floor=floor, state_type=gs.state_type,
                            action=actions.end_turn(),
                            reasoning="Skill eval: death detected, save and swap",
                            source="eval",
                        )
                self._end_turn_sent_round = current_round
                action = actions.end_turn()
                await self._execute(action, delta_source="turn_end")
                try:
                    await self._wait_for_play_phase_timed(reason="combat_plan:empty_plan")
                except McpTimeout:
                    pass
                _r, _r_zh = _plan_decision_reasoning("Plan: end turn", plan)
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning=_r, reasoning_zh=_r_zh, source="plan",
                )

        plan = self._combat_plan
        idx = self._combat_plan_index

        # Safety: plan is exhausted → end turn
        if idx >= len(plan.actions):
            if plan.end_turn:
                if current_round == self._end_turn_sent_round:
                    return None
                # ── Skill eval: kill/death detection before end_turn (plan exhausted) ──
                if self._skill_eval_state == "active":
                    # Poison kill: if poison will kill all enemies on their turn
                    if self._poison_kills_all_enemies(gs):
                        logger.info("Skill eval: POISON KILL DETECTED — all enemies die from poison")
                        self._eval_round_count = current_round
                        await self._handle_eval_terminal(gs, won=True)
                        return Decision(
                            floor=floor, state_type=gs.state_type,
                            action=actions.end_turn(),
                            reasoning="Skill eval: poison kill detected, save and swap",
                            source="eval",
                        )
                    # Death: incoming damage will kill us
                    incoming = compute_total_incoming(gs.enemies)
                    player_block = gs.raw.combat.player.block if gs.raw.combat else 0
                    effective_hp = gs.player_hp + player_block
                    if incoming >= effective_hp:
                        logger.info(
                            "Skill eval: DEATH DETECTED — incoming %d >= effective HP %d",
                            incoming, effective_hp,
                        )
                        self._eval_round_count = current_round
                        await self._handle_eval_terminal(gs, won=False)
                        return Decision(
                            floor=floor, state_type=gs.state_type,
                            action=actions.end_turn(),
                            reasoning="Skill eval: death detected, save and swap",
                            source="eval",
                        )
                self._end_turn_sent_round = current_round
                self._combat_plan = None
                action = actions.end_turn()
                await self._execute(action, delta_source="turn_end")
                try:
                    await self._wait_for_play_phase_timed(reason="combat_plan:plan_complete")
                except McpTimeout:
                    pass
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="Plan complete, end turn", source="plan",
                )
            self._combat_plan = None
            return None

        # Execute the next planned action
        planned = plan.actions[idx]

        # ── Potion action ──
        if planned.is_potion:
            pot_idx = self._resolve_usable_potion_index(gs, planned)
            # Validate potion is usable
            usable = {p.index for p in gs.potions if p.can_use}
            if pot_idx not in usable:
                logger.warning(
                    "Combat plan: potion %s/%s not usable, skipping",
                    pot_idx,
                    planned.potion_name or "?",
                )
                self._combat_plan_index = idx + 1
                return await self._execute_combat_plan(gs)
            # Resolve target
            target_index = planned.target_index
            pot = next((p for p in gs.potions if p.index == pot_idx), None)
            if pot and pot.requires_target and target_index is None and gs.enemies:
                target_index = gs.enemies[0].index
            action = actions.use_potion(pot_idx, target_index)
            await self._execute(
                action,
                delta_source=pot.name if pot else f"potion_{pot_idx}",
                delta_target=self._resolve_delta_target(gs, target_index),
            )
            self._hcm_record_potion_use(pot.name if pot else f"potion_{pot_idx}")
            self._v2_round_actions.append(f"Used potion {pot.name if pot else pot_idx}")
            # Skill eval: track potion usage
            if self._skill_eval_state in ("active", "final"):
                self._eval_potions_used += 1
            self._combat_plan_index = idx + 1
            logger.info(
                "Plan [%d/%d]: potion %s",
                idx + 1,
                len(plan.actions),
                pot.name if pot else pot_idx,
            )
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Plan: use potion {pot.name if pot else pot_idx}",
                source="plan",
            )

        # ── Card action ──
        card_index = resolve_card_name(planned.card_name, gs)

        if card_index is None:
            # Card not found or not playable — advance past it and try the next one.
            logger.warning(
                "Combat plan: card '%s' not found/playable, skipping",
                planned.card_name,
            )
            self._combat_plan_index = idx + 1
            # Find the next resolvable action in the plan (iterative)
            while self._combat_plan_index < len(plan.actions):
                next_planned = plan.actions[self._combat_plan_index]
                if next_planned.is_potion:
                    break  # Potion — handled in next iteration
                next_idx = resolve_card_name(next_planned.card_name, gs)
                if next_idx is not None:
                    break
                logger.warning(
                    "Combat plan: card '%s' also not found, skipping",
                    next_planned.card_name,
                )
                self._combat_plan_index += 1
            else:
                # All remaining planned actions are unresolvable
                # Check: are the cards in hand but unplayable (energy)? → normal end turn
                # Or are they truly missing (bad plan)? → plan failure
                remaining_names = {
                    a.card_name.lower().rstrip("+")
                    for a in plan.actions[idx:]
                    if not a.is_potion
                }
                hand_names = {c.name.lower().rstrip("+") for c in (gs.hand or [])}
                cards_in_hand_but_unplayable = remaining_names & hand_names
                if cards_in_hand_but_unplayable:
                    # Cards exist but can't be played (likely energy exhausted)
                    # This is normal — plan was partially executed successfully
                    logger.info(
                        (
                            "Combat plan: remaining cards in hand but unplayable "
                            "(energy?): %s — ending turn"
                        ),
                        cards_in_hand_but_unplayable,
                    )
                    self._combat_plan = None
                    # Normal end turn
                    if current_round != self._end_turn_sent_round:
                        self._end_turn_sent_round = current_round
                        end_action = actions.end_turn()
                        await self._execute(end_action, delta_source="turn_end")
                        return Decision(
                            floor=floor, state_type=gs.state_type, action=end_action,
                            reasoning="Plan partially complete, remaining cards unplayable",
                            source="plan",
                        )
                    return None
                else:
                    # Cards not found at all — genuine plan failure
                    missing = remaining_names - hand_names
                    logger.warning(
                        "Combat plan: remaining cards not in hand: %s — plan failed",
                        missing,
                    )
                    # Flush partial execution into conversation so replan
                    # sees what was already played this turn
                    if self._v2_combat_conversation and self._v2_round_actions:
                        try:
                            self._v2_combat_conversation.add_execution_result(
                                self._v2_round_actions, gs,
                            )
                        except Exception:
                            pass
                        self._v2_round_actions = []
                    self._combat_plan = None
                    return None
            # Re-enter execution with the updated index
            return await self._execute_combat_plan(gs)

        # Safety: verify card_index is within current hand bounds
        hand = gs.hand
        if card_index >= len(hand):
            logger.warning(
                "Combat plan: resolved index %d out of range (hand has %d cards), discarding plan",
                card_index, len(hand),
            )
            self._combat_plan = None
            return None

        # Determine target → resolve to integer index for new API
        card = hand[card_index]
        if hasattr(card, "requires_target"):
            needs_target = card.requires_target
        else:
            needs_target = card.target_type in ("AnyEnemy", "single_enemy", "Enemy")
        target_index = planned.target_index if hasattr(planned, "target_index") else planned.target

        if needs_target:
            alive_indices = {e.index for e in gs.enemies}
            planned_target = target_index
            # When enemies die mid-plan the mod renumbers survivors, so the
            # plan-time ``target_index`` no longer refers to the same creature.
            # Remap via the enemy_id snapshot taken at plan creation.
            if planned_target is not None and self._combat_plan_enemy_ids is not None:
                remapped = self._remap_plan_target(planned_target, gs.enemies)
                if remapped is not None and remapped != planned_target:
                    logger.info(
                        "Plan target remap: %d → %d (survivors renumbered)",
                        planned_target, remapped,
                    )
                    target_index = remapped
                elif remapped is None and planned_target not in alive_indices:
                    target_index = None  # force fallback branch below

            if target_index is not None and target_index in alive_indices:
                pass  # Valid target
            elif gs.enemies:
                # Intended target died (or no plan snapshot) — auto-fill first alive
                old = planned_target
                target_index = gs.enemies[0].index
                logger.info(
                    "Plan auto-fill target: %s → %d (intended target died)",
                    old, target_index,
                )
            else:
                logger.warning(
                    "Combat plan: card '%s' needs target but none available",
                    planned.card_name,
                )
                self._combat_plan_index = idx + 1
                return None
        else:
            target_index = None

        # Execute the card play
        action = actions.play_card(card_index, target_index)
        execute_result = await self._execute(
            action,
            delta_source=card.name,
            delta_target=self._resolve_delta_target(gs, target_index),
        )
        gs_after_action = self._state_from_action_result(execute_result)

        # V2: record card play in short-term memory
        self._hcm_record_card_play(card.name, self._card_energy_cost(card))
        # V2 conversation: track action for round feedback
        target_suffix = f" → target[{target_index}]" if target_index is not None else ""
        self._v2_round_actions.append(f"Played {card.name}{target_suffix}")
        self._last_played_card_name = card.name
        self._last_played_card_rules = getattr(card, 'rules_text', '') or ""
        self._last_played_plan_action = planned  # survives plan invalidation

        # Advance plan index
        self._combat_plan_index = idx + 1

        # ── Skill eval: precise kill detection ──
        if self._skill_eval_state == "active" and self._combat_plan:
            try:
                raw_eval = await self._client.get_state()
                gs_eval = parse_state(raw_eval)
            except Exception:
                gs_eval = None

            if gs_eval:
                from src.skills.replay_evaluator import remaining_plan_kills_boss

                remaining_actions = self._combat_plan.actions[self._combat_plan_index:]
                # Direct damage kill
                if remaining_plan_kills_boss(
                    gs_eval.hand, gs_eval.enemies, remaining_actions,
                ):
                    logger.info("Skill eval: KILL DETECTED — remaining plan kills boss")
                    self._eval_round_count = current_round
                    await self._handle_eval_terminal(gs_eval, won=True)
                    return Decision(
                        floor=floor, state_type=gs.state_type, action=action,
                        reasoning="Skill eval: kill detected, save and swap",
                        source="eval",
                    )
                # Poison kill: plan is about to end → end_turn → poison kills
                if (not remaining_actions or self._combat_plan_index >= len(self._combat_plan.actions) - 1):
                    if self._poison_kills_all_enemies(gs_eval):
                        logger.info("Skill eval: POISON KILL DETECTED after last planned card")
                        self._eval_round_count = current_round
                        await self._handle_eval_terminal(gs_eval, won=True)
                        return Decision(
                            floor=floor, state_type=gs.state_type, action=action,
                            reasoning="Skill eval: poison kill detected, save and swap",
                            source="eval",
                        )

        # Resolve a usable post-play state for both downstream checks. The
        # MCP `state` field returned with the action call is sometimes a
        # transitional snapshot whose `raw.combat` is None (e.g. relic-draw
        # animation hasn't settled — see Joss Paper on the last Shiv of a
        # turn). Fall back to a fresh get_state() so death/hand-change
        # detection actually sees what changed.
        if gs_after_action is not None and gs_after_action.raw.combat is not None:
            gs_after = gs_after_action
        else:
            try:
                raw_after = await self._client.get_state()
                gs_after = parse_state(raw_after)
            except Exception:
                gs_after = gs  # fallback to pre-play state — better than crashing
            if gs_after.raw.combat is None:
                # Fallback fetch also has no combat — combat may have ended,
                # or mod is still mid-transition. Downstream checks will
                # gracefully no-op (gs_after == pre-play gs), preserving the
                # prior "skip detection" behaviour for this rare edge case.
                logger.warning(
                    "Post-play state has no combat data after fallback fetch "
                    "(card='%s'); skipping mid-plan death/hand-change detection",
                    card.name,
                )

        # Check for enemy deaths mid-plan → trigger re-plan if worthwhile
        if self._combat_plan_alive and gs_after.raw.combat is not None:
            post_alive = {e.index for e in gs_after.enemies}
            died = self._combat_plan_alive - post_alive
            remaining = len(self._combat_plan.actions) - self._combat_plan_index if self._combat_plan else 0
            player_energy = gs_after.energy

            if died:
                logger.info(
                    "Enemy death re-plan: %d enemies died, %d actions remain, %d energy",
                    len(died), remaining, player_energy,
                )
                pre_enemies_by_idx = {e.index: e.name for e in gs.enemies}
                dead_names = [
                    pre_enemies_by_idx.get(i, f"enemy[{i}]") for i in sorted(died)
                ]
                desc = (
                    f"{', '.join(dead_names)} died after playing {card.name}"
                    if dead_names
                    else f"Enemy died after playing {card.name}"
                )
                self._trigger_replan("enemy_death", desc, gs_after=gs_after)
                _r, _r_zh = _plan_decision_reasoning(
                    f"Plan [{idx + 1}/{len(plan.actions)}]: {planned.card_name}",
                    plan,
                    card_name=planned.card_name,
                )
                return Decision(
                    floor=floor,
                    state_type=gs.state_type,
                    action=action,
                    reasoning=_r,
                    reasoning_zh=_r_zh,
                    source="plan",
                )

        # Check the MCP post-state: if this play changed the current hand
        # beyond removing the played card, discard remaining plan and re-plan.
        # Uses the fallback-resolved ``gs_after`` from above so relic-draws
        # that arrived after the action call (transient `raw.combat is None`)
        # still get caught.
        if self._played_card_changed_current_hand(gs, gs_after, card):
            remaining_actions = plan.actions[idx + 1:]
            # Exception: if the newly-generated cards are already queued in
            # the remaining plan (e.g. Blade Dance generates 3 Shivs and the
            # plan has 3 Shiv plays lined up), the hand change was
            # anticipated — skip the re-plan so we don't thrash every turn.
            if self._plan_consumes_generated_cards(
                gs, gs_after, card, remaining_actions,
            ):
                logger.info(
                    "Plan-anticipated hand change from '%s': remaining plan "
                    "consumes generated cards, skipping re-plan",
                    card.name,
                )
            else:
                remaining_count = len(remaining_actions)
                if remaining_count > 0:
                    logger.info(
                        "Plan split: '%s' changed hand via MCP state, discarding %d remaining planned actions",
                        card.name, remaining_count,
                    )
                self._trigger_replan(
                    "hand_change",
                    f"{card.name} changed the current hand (drew/added cards)",
                    gs_after=gs_after,
                )

        reasoning, reasoning_zh = _plan_decision_reasoning(
            f"Plan [{idx + 1}/{len(plan.actions)}]: {planned.card_name}",
            plan,
            card_name=planned.card_name,
        )
        return Decision(
            floor=floor,
            state_type=gs.state_type,
            action=action,
            reasoning=reasoning,
            reasoning_zh=reasoning_zh,
            source="plan",
        )

    async def _generate_combat_plan(
        self, gs: GameState, *, is_replan: bool = False,
        use_fallback_model: bool = False,
        no_target_mode: bool = False,
    ) -> CombatPlan | None:
        """Generate a new combat plan via LLM.

        V2: multi-turn conversation with tool-use agent.
        V1: one-shot context assembly + plan_combat.

        Args:
            gs: Current game state.
            is_replan: If ``True``, use fast tier (draw-card re-plan,
                validation retry within same round).
            use_fallback_model: If ``True``, use analysis tier as fallback
                when the default tier fails repeatedly.
            no_target_mode: If ``True``, inject a replan_context telling the
                LLM no alive enemies exist (boss phase transition); allowed
                actions are non-target cards or end_turn.
        """
        # ── V2 path: multi-turn combat conversation ──
        _conversation = self._v2_combat_conversation
        if _conversation is None and self._v2_engine and not config.COMBAT_CONVERSATION_ENABLED:
            # Single-turn fallback: build a fresh per-turn conversation so
            # combat still plays when COMBAT_CONVERSATION_ENABLED=false.
            # Discarded after this call — self._v2_combat_conversation stays None.
            from src.brain.conversation import CombatConversation
            from src.brain.prompts.system import get_system_prompt
            _conversation = CombatConversation(
                get_system_prompt(self._resolve_combat_type(gs))
            )
        if _conversation is None:
            logger.error(
                "_generate_combat_plan: _v2_combat_conversation is None! "
                "v2_engine=%s", bool(self._v2_engine),
            )
        if self._v2_engine and _conversation:
            try:
                # Update tool executor with current game state
                if self._v2_tool_executor:
                    self._v2_tool_executor.set_game_state(gs)
                extra_context = self._build_tool_preprocessor_context(gs)
                # Canonical trigger label shared by replan_ctx, logger, and
                # monitor — keeps observability in lock-step with the prompt.
                if no_target_mode:
                    trigger_kind = "no_target"
                elif is_replan and self._prev_combat_plan:
                    trigger_kind = self._replan_trigger_kind or "unknown_replan"
                elif is_replan:
                    trigger_kind = "validation_retry"
                else:
                    trigger_kind = "fresh_round"
                # Build re-plan context: no-target mode takes precedence
                replan_ctx = ""
                if no_target_mode:
                    replan_ctx = (
                        "## No Valid Targets\n"
                        "All enemies are non-hittable (likely a multi-phase boss like "
                        "Subject transitioning between phases).\n\n"
                        "- DO NOT plan enemy-target-requiring cards.\n"
                        "- You MAY play non-target cards — especially Powers, or any "
                        "non-target attack/skill that benefits future turns.\n"
                        "- Choose `end_turn` if no useful non-target card is in hand."
                    )
                elif is_replan and self._prev_combat_plan:
                    prev = self._prev_combat_plan
                    completed = getattr(self, "_combat_plan_index", 0)
                    total = len(prev.actions)
                    # Fall back to a generic phrasing that does NOT lie about
                    # the cause if the structured desc is missing for any
                    # reason (e.g. an LLM-side regeneration retry where the
                    # first attempt failed before consuming the desc).
                    trigger = self._replan_trigger_desc or (
                        f"Plan invalidated after playing {self._last_played_card_name}"
                        if self._last_played_card_name
                        else "Plan invalidated mid-execution"
                    )
                    replan_ctx = (
                        f"Original plan ({completed}/{total} completed): "
                        f"{prev.reasoning}\n"
                        f"Trigger: {trigger}."
                    )
                    # NOTE: do NOT clear _replan_trigger_desc here. If the
                    # downstream LLM call fails and the loop retries, we want
                    # the same trigger phrase. Clearing happens on round
                    # transition or COMBAT_START.
                logger.info(
                    "Combat plan generation: trigger_kind=%s is_replan=%s",
                    trigger_kind, is_replan,
                )
                # Add round state to conversation
                deck_card_names = {c.name.rstrip("+") for c in gs.deck} if gs.deck else set()
                _conversation.add_round_state(
                    gs,
                    extra_context=extra_context,
                    replan_context=replan_ctx,
                    enemy_episodes=self._get_enemy_episodes(gs),
                    card_memory_store=getattr(self._memory, "card_memory_store", None) if self._memory else None,
                    deck_card_names=deck_card_names,
                )
                # Trivial-hand fast-path: when the player has ≤2 playable
                # cards, strategic-tier reasoning is wasted. Route to fast.
                # Takes priority over is_replan — a draw-card replan that
                # lands on a trivial hand should still go fast.
                simple = len(gs.playable_cards) <= 2
                # Generate plan via conversation (model-routed)
                plan = await self._v2_engine.generate_combat_plan(
                    _conversation,
                    is_replan=is_replan,
                    simple=simple,
                    use_fallback_model=use_fallback_model,
                )
                if plan is not None:
                    # Pre-execution validation: catch hallucinated cards
                    validation_error, valid_count = self._validate_combat_plan(plan, gs)
                    if validation_error:
                        # Try truncating to valid prefix before discarding
                        if valid_count > 0:
                            truncated = CombatPlan(
                                actions=plan.actions[:valid_count],
                                end_turn=True,
                                reasoning=plan.reasoning,
                                analysis=plan.analysis,
                                note_to_future_self=plan.note_to_future_self,
                            )
                            logger.warning(
                                "Combat plan truncated to %d/%d valid actions "
                                "(dropped from step %d: %s)",
                                valid_count, len(plan.actions),
                                valid_count + 1, validation_error,
                            )
                            plan = truncated
                        else:
                            logger.warning(
                                "Combat plan validation failed at step 1: %s",
                                validation_error,
                            )
                            _conversation.add_validation_error(
                                validation_error,
                            )
                            # Replan once with error feedback
                            plan = await self._v2_engine.generate_combat_plan(
                                _conversation,
                                is_replan=True,
                                use_fallback_model=use_fallback_model,
                            )
                            if plan is not None:
                                validation_error2, valid_count2 = self._validate_combat_plan(plan, gs)
                                if validation_error2:
                                    if valid_count2 > 0:
                                        plan = CombatPlan(
                                            actions=plan.actions[:valid_count2],
                                            end_turn=True,
                                            reasoning=plan.reasoning,
                                            analysis=plan.analysis,
                                            note_to_future_self=plan.note_to_future_self,
                                        )
                                        logger.warning(
                                            "Combat re-plan truncated to %d valid actions",
                                            valid_count2,
                                        )
                                    else:
                                        logger.warning(
                                            "Combat plan re-validation failed: %s",
                                            validation_error2,
                                        )
                                        plan = None
                    if plan is not None:
                        logger.info(
                            "V2 combat plan: %d actions, end_turn=%s",
                            len(plan.actions), plan.end_turn,
                        )
                        # Task B5: capture pre-plan round context onto the
                        # active CombatTracker for mistake-driven skill
                        # discovery (spec §2.2). Runs AFTER the strategic
                        # tier's llm_call event was written so the seq
                        # pins the round to the correct log entry.
                        self._capture_round_context_for_plan(gs, plan)
                        return plan
                logger.warning("V2 combat plan returned None")
            except Exception as exc:
                logger.error("V2 combat plan failed: %s", exc)

        # V2 is the only combat plan path. No V1 fallback.
        return None

    def _capture_round_context_for_plan(
        self, gs: "GameState", plan: "CombatPlan",
    ) -> None:
        """Snapshot pre-plan round context onto the active CombatTracker.

        Called immediately after a strategic-tier combat plan is produced
        and its ``llm_call`` event has been written. Enables postrun
        mistake-driven skill discovery to reconstruct each round's live
        context for the critic LLM (spec §2.2) and for prewrite A/B to
        fetch the original prompt via ``llm_call_seq`` (spec §4.4).

        Fully defensive: missing data sources default to 0/[]/-1, and
        any exception is swallowed — combat MUST continue on capture
        failure.
        """
        try:
            from src.brain.prompts._intent_fmt import compute_total_incoming
            from src.brain.v2_engine import capture_round_context

            stm = self._hcm_short_term()
            if stm is None:
                return
            tracker = stm.active_combat_tracker()
            if tracker is None:
                return

            # Pile sizes live on agent_view.combat (upstream RawCombatPayload
            # does not expose them).
            draw_n = 0
            discard_n = 0
            exhaust_n = 0
            try:
                av = gs.agent_view
                if av is not None and av.combat is not None:
                    draw_n = len(av.combat.draw)
                    discard_n = len(av.combat.discard)
                    exhaust_n = len(av.combat.exhaust)
            except AttributeError:
                pass

            # Usable potions: name list filtered by can_use.
            usable_potions: list[str] = []
            try:
                for p in (gs.potions or []):
                    if getattr(p, "can_use", False):
                        name = getattr(p, "name", None) or ""
                        if name:
                            usable_potions.append(name)
            except AttributeError:
                pass

            # Incoming damage (single source of truth for intent damage).
            try:
                incoming = compute_total_incoming(gs.enemies) if gs.enemies else 0
            except Exception:  # noqa: BLE001
                incoming = 0

            # Plan as human-readable "card->target" strings.
            agent_plan: list[str] = []
            try:
                for a in plan.actions:
                    label = a.card_name if a.action_type == "card" else f"potion:{a.potion_name or a.potion_index}"
                    tgt = "self" if a.target_index is None else f"enemy_{a.target_index}"
                    agent_plan.append(f"{label}->{tgt}")
            except AttributeError:
                pass

            # llm_call_seq from session logger — -1 if unavailable.
            seq = -1
            try:
                if self._session_logger is not None:
                    seq = self._session_logger.current_llm_call_seq()
            except AttributeError:
                pass

            capture_round_context(
                tracker=tracker,
                block_before=getattr(gs, "block", 0) or 0,
                draw_pile_size=draw_n,
                discard_pile_size=discard_n,
                exhaust_pile_size=exhaust_n,
                usable_potions=usable_potions,
                incoming_damage=incoming,
                agent_plan=agent_plan,
                llm_call_seq=seq,
            )
        except Exception:  # noqa: BLE001
            logger.debug("_capture_round_context_for_plan failed", exc_info=True)

    @staticmethod
    def _validate_combat_plan(
        plan: "CombatPlan", gs: GameState,
    ) -> tuple[str | None, int]:
        """Validate the deterministic prefix of a combat plan.

        The executor naturally re-plans once the hand or energy becomes
        uncertain, so this validator only hard-checks the sequential prefix
        before the first draw/generate/energy-changing action. That keeps
        validation aligned with execution semantics and avoids false negatives
        for plans like "play generator, then use the created Shiv".

        Returns:
            ``(error_message, valid_action_count)`` — ``error_message`` is
            ``None`` when the entire plan is valid. ``valid_action_count``
            is the number of leading actions that passed validation (may be
            >0 even when an error is returned for a later step).
        """

        from src.brain.card_effects import detect_draws_cards

        remaining_cards = [c for c in (gs.hand or []) if c.playable]
        current_energy = gs.energy

        def _hand_summary() -> str:
            counts: dict[str, int] = {}
            for card in remaining_cards:
                name = card.name.lower().rstrip("+")
                counts[name] = counts.get(name, 0) + 1
            return ", ".join(f"{cnt}x {name}" for name, cnt in sorted(counts.items())) or "no playable cards"

        def _match_remaining_card(
            planned_name: str,
        ):
            normalized = planned_name.lower().rstrip("+")
            for idx, card in enumerate(remaining_cards):
                if card.name.lower().rstrip("+") == normalized:
                    return idx, card
            for idx, card in enumerate(remaining_cards):
                if normalized in card.name.lower():
                    return idx, card
            return None, None

        def _find_planned_potion(planned: "PlannedAction"):
            for potion in gs.potions:
                if planned.potion_index is not None and potion.index == planned.potion_index:
                    return potion
            wanted = planned.potion_name.lower().strip()
            if wanted:
                for potion in gs.potions:
                    if (potion.name or "").lower().strip() == wanted:
                        return potion
            return None

        x_cost_played = False  # Track whether an X-cost card drained energy
        valid_count = 0  # Track how many actions passed validation

        for action_idx, action in enumerate(plan.actions, start=1):
            if action.is_potion:
                potion = _find_planned_potion(action)
                if potion is None:
                    # Count validation already passed as far as it can; skip
                    # unknown potion metadata rather than over-rejecting.
                    valid_count += 1
                    continue
                description = strip_bbcode(potion.description or "")
                name = (potion.name or "").lower()
                if "energy potion" in name:
                    current_energy += 2
                    valid_count += 1
                    continue
                if detect_draws_cards(description) or _card_generates(description):
                    valid_count += 1
                    break
                if _card_changes_energy(description):
                    valid_count += 1
                    break
                valid_count += 1
                continue

            card_pos, card = _match_remaining_card(action.card_name)
            if card is None:
                return (
                    "Invalid plan: "
                    f"step {action_idx} tries to play {action.card_name}, "
                    "but that card is not in your playable hand yet. "
                    f"Your playable hand RIGHT NOW: [{_hand_summary()}]. "
                    "Only plan cards that are currently in hand until after a draw/create action resolves.",
                    valid_count,
                )

            # Target availability: target-requiring card cannot execute with no alive enemies
            # (e.g. multi-phase boss mid-transition). Existing truncate logic handles
            # the valid-prefix case; valid_count=0 triggers the replan-with-context path.
            card_needs_target = (
                getattr(card, "requires_target", False)
                or card.target_type in ("AnyEnemy", "single_enemy", "Enemy")
            )
            if card_needs_target and not gs.enemies:
                return (
                    "Invalid plan: "
                    f"step {action_idx} tries to play {getattr(card, 'name', action.card_name)} "
                    "which needs an enemy target, but no alive enemies "
                    "(multi-phase boss transitioning between phases). "
                    "Plan only non-target cards (Defend / Powers / self-buffs) or end_turn.",
                    valid_count,
                )

            rules = getattr(card, "rules_text", "") or ""
            display_name = getattr(card, "name", action.card_name)
            if _card_is_x_cost(card):
                current_energy = 0
                x_cost_played = True
            else:
                fixed_cost = max(0, getattr(card, "energy_cost", 0))
                if fixed_cost > current_energy:
                    if x_cost_played:
                        # X-cost card consumed all energy — LLM must order
                        # X-cost cards LAST.  Hard rejection.
                        return (
                            "Invalid plan order: "
                            f"step {action_idx} tries to play {display_name} "
                            f"for {fixed_cost} energy with only {current_energy} "
                            "remaining (X-cost card consumed all energy earlier). "
                            "Move X-cost cards to the END of your plan.",
                            valid_count,
                        )
                    # No X-cost card played — energy deficit may be caused by
                    # a cost-changing card (e.g. Bullet Time makes hand free).
                    # Trust the LLM; if wrong, game executor rejects naturally.
                    valid_count += 1
                    break
                current_energy -= fixed_cost

            remaining_cards.pop(card_pos)
            valid_count += 1

            # After cards that draw, generate, or change energy, subsequent hand
            # state becomes uncertain and the executor will naturally re-plan.
            if detect_draws_cards(rules) or _card_generates(rules) or _card_changes_energy(rules):
                break
        return (None, valid_count)

    def _act_start_floor(self, gs: GameState) -> int:
        """Per-act offset such that ``floor = act_start_floor + row + 1``.

        Derived from the live map: ``act_start_floor = gs.floor - is_current.row - 1``.
        Cached per-act so rest/shop screens (which may lack ``is_current``) keep
        working from the value set at the previous map screen. Falls back to a
        hardcoded best-guess only if no map reading has ever been seen this act
        — but the empirical anchor in the cache always wins once available.
        """
        act = gs.act if hasattr(gs, "act") else 1
        gs_map = getattr(gs, "map", None)
        cur = getattr(gs_map, "current_node", None) if gs_map else None
        floor = getattr(gs, "floor", 0) or 0
        if cur is not None and floor > 0:
            offset = floor - cur.row - 1
            self._act_start_floor_cache[act] = offset
            return offset
        if act in self._act_start_floor_cache:
            return self._act_start_floor_cache[act]
        # First-call fallback before any map data has been observed for this act.
        # These match the runtime-derived offsets seen in production logs.
        return {1: 0, 2: 17, 3: 33}.get(act, 0)

    def _find_current_step_index(self, gs: GameState) -> int:
        """Find where the player currently is in the planned route."""
        if self._route_plan is None:
            return 0
        # Match current map position to route coordinates
        if gs.map and gs.map.current_node:
            current = (gs.map.current_node.col, gs.map.current_node.row)
            try:
                return self._route_plan.coords.index(current) + 1
            except ValueError:
                pass
        # Fallback: estimate from floor number (e.g. rest_site where map data is absent)
        if gs.floor > 0:
            act_start_floor = self._act_start_floor(gs)
            for i, coord in enumerate(self._route_plan.coords):
                _, row = coord
                floor_num = act_start_floor + row + 1
                if floor_num == gs.floor:
                    return i + 1  # remaining route starts after current node
                if floor_num > gs.floor:
                    return i  # no exact match; start from next future node
        return 0

    async def _handle_map_route_decision(self, gs: GameState) -> None:
        """Handle map route selection or re-plan if triggered.

        Called when multiple map options are available. Checks whether a
        new route selection is needed (act start or re-plan trigger) and
        runs Scenario A if so. Otherwise, Scenario B runs via normal
        V2Engine decision flow.
        """
        current_act = gs.act

        # Determine current coordinate for re-plan check
        current_coord = None
        if gs.map and gs.map.current_node:
            current_coord = (gs.map.current_node.col, gs.map.current_node.row)

        need_plan = False
        replan_reason_str = ""
        replan_trigger: ReplanReason | None = None

        if self._route_plan is None or current_act != self._planned_act:
            # No plan yet (act start)
            need_plan = True
        elif current_coord is not None:
            # Check re-plan conditions
            reason = check_replan_needed(
                hp=gs.player_hp,
                gold=gs.gold,
                current_coord=current_coord,
                route=self._route_plan,
            )
            if reason is not None:
                need_plan = True
                replan_trigger = reason
                replan_reason_str = {
                    ReplanReason.HP_DANGER: f"HP is {gs.player_hp} with danger ahead",
                    ReplanReason.GOLD_NO_SHOP: f"Gold is {gs.gold} but no shop on current route",
                    ReplanReason.PATH_DEVIATION: "Deviated from planned route",
                }[reason]
                logger.info("Route re-plan triggered: %s", reason.value)
                self._emit_monitor("route_replan", {
                    "reason": reason.value,
                    "hp": gs.player_hp,
                    "gold": gs.gold,
                    "detail": replan_reason_str,
                })

        if need_plan:
            await self._select_route(gs, replan_reason=replan_reason_str, replan_trigger=replan_trigger)

        # Always refresh live remaining route cache from current map data.
        # This ensures rest/shop prompts (where map data is absent) use the
        # most recent path, not a stale route from the start of the act.
        if gs.map and gs.map.nodes:
            self._refresh_live_remaining_route(gs)

    async def _select_route(
        self, gs: GameState,
        replan_reason: str = "",
        replan_trigger: ReplanReason | None = None,
    ) -> None:
        """Generate candidate routes and let LLM select one.

        Called at act start and when re-plan is triggered.
        """
        if not gs.is_map or not gs.map or not gs.map.nodes:
            return
        if not gs.run:
            return

        current_act = gs.act
        logger.info("Selecting route for Act %d (%d map nodes)%s",
                     current_act, len(gs.map.nodes),
                     f" [re-plan: {replan_reason}]" if replan_reason else "")

        routes = enumerate_routes(gs.map.nodes, max_paths=100)

        if not routes:
            logger.warning("No routes enumerated — no plan available")
            self._route_plan = None
            return

        # Sort by player preference (gold-aware: boosts shop priority when rich)
        routes = sort_routes(routes, gold=gs.gold)

        # Apply re-plan filters
        if replan_trigger == ReplanReason.HP_DANGER:
            # HP danger: filter out routes with Elite between current and nearest Rest
            def _safe_to_rest(r: RoutePath) -> bool:
                for t in r.nodes:
                    if is_rest_node(t):
                        return True  # reached rest without hitting elite
                    if t == "Elite":
                        return False  # elite before rest
                return True  # no elite at all
            safe = [r for r in routes if _safe_to_rest(r)]
            if safe:
                routes = safe  # only show safe routes; keep all if none are safe

        if replan_trigger == ReplanReason.GOLD_NO_SHOP:
            # Gold surplus: prioritize routes with shops (sort them first)
            with_shop = [r for r in routes if r.shop_count > 0]
            without_shop = [r for r in routes if r.shop_count == 0]
            routes = with_shop + without_shop

        # Format top 10 for LLM
        formatted = format_routes_for_prompt(routes, top_n=10)
        logger.info("Enumerated %d routes, formatted %d chars", len(routes), len(formatted))

        if not self._use_llm:
            self._route_plan = routes[0]
            self._planned_act = current_act
            logger.info("Route stored (no-LLM mode): %s", routes[0].nodes)
            return

        # Build full-context prompt for Scenario A
        strategic_thread = ""
        stm = self._get_short_term_ref()
        if stm is not None and hasattr(stm, "get_strategic_thread"):
            strategic_thread = stm.get_strategic_thread(
                max_entries=5, current_context="map",
            )

        prompt = build_route_selection_prompt(
            gs,
            routes_text=formatted,
            relics=self._cached_relics,
            strategic_thread=strategic_thread,
            replan_reason=replan_reason,
        )

        # Inject skills + memory context
        ctx = self._build_decision_context(gs, include_knowledge=False)
        extra_context = ctx.get("extra_context", "")
        skill_context = ctx.get("skill_context", "")
        memory_str = ""
        wc = ctx.get("working_context")
        if wc is not None:
            from src.memory.prompt_injector import format_working_context
            memory_str = format_working_context(wc)

        prompt_parts: list[str] = []
        if skill_context:
            prompt_parts.append(skill_context)
        if memory_str:
            prompt_parts.append(memory_str)
        if extra_context:
            prompt_parts.append(extra_context)
        prompt_parts.append(prompt)
        full_prompt = "\n\n".join(prompt_parts)

        try:
            from src.brain.llm_caller import call_raw as llm_call_raw
            raw_text, latency, tokens = await llm_call_raw(
                "You are a Slay the Spire 2 strategy expert. "
                "Pick the best route from the candidates.",
                full_prompt,
                think=True,
                model=config.LLM_STRATEGIC_MODEL,
                provider=config.get_tier_provider("strategic"),
                openai_relay_profile="default",
            )
            logger.info("Route selection LLM: %.0fms, %d tokens", latency, tokens)

            # Parse JSON response
            cleaned = _re.sub(r"<thinking>.*?</thinking>", "", raw_text, flags=_re.DOTALL).strip()

            try:
                _start = cleaned.find("{")
                _end = cleaned.rfind("}")
                if _start != -1 and _end > _start:
                    import json as _json
                    parsed = _json.loads(cleaned[_start:_end + 1])
                    route_num = parsed.get("route")
                    if isinstance(route_num, (int, float)) and 1 <= int(route_num) <= min(10, len(routes)):
                        route_num = int(route_num)
                        self._route_plan = routes[route_num - 1]
                        self._planned_act = current_act
                        logger.info("Route selected: #%d — %s", route_num, self._route_plan.nodes)
                        return
            except (ValueError, KeyError, TypeError):
                pass

            # Parse failed — use first sorted route
            logger.warning("Route selection parse failed — using sorted #1")
            self._route_plan = routes[0]
            self._planned_act = current_act

        except Exception as e:
            logger.warning("Route selection LLM failed: %s — using sorted #1", e)
            self._route_plan = routes[0]
            self._planned_act = current_act

    def _refresh_live_remaining_route(
        self,
        gs: GameState,
        chosen_coord: tuple[int, int] | None = None,
    ) -> None:
        """Cache the actual remaining path to boss from live map data.

        Called every time the player is at a map selection screen (where
        gs.map is populated). This prevents rest/shop prompts from showing
        stale route data when the player deviated from the original plan.

        When ``chosen_coord`` is provided, only routes whose first coord
        matches it are considered. This keeps the cache aligned with the
        node the agent actually picked, rather than the enumerator's
        preferred branch. Without this filter, if routes[0] starts with a
        different child than the one chosen, rest/shop prompts at the next
        floor would show a path from the wrong branch.
        """
        act_start_floor = self._act_start_floor(gs)
        routes = enumerate_routes(gs.map.nodes, max_paths=20)
        if chosen_coord is not None:
            routes = [r for r in routes if r.coords and r.coords[0] == chosen_coord]
        if not routes:
            self._live_remaining_route = None
            return
        routes = sort_routes(routes, gold=gs.gold)
        route = routes[0]
        result: list[tuple[int, str]] = []
        for coord, node_type in zip(route.coords, route.nodes):
            _, row = coord
            floor_num = act_start_floor + row + 1
            result.append((floor_num, node_type))
        self._live_remaining_route = result if result else None

    def _build_remaining_route(self, gs: GameState) -> list[tuple[int, str]] | None:
        """Extract remaining route nodes from current position to boss.

        Prefers the live remaining route cache (updated at each map step)
        over the static route plan, so rest/shop prompts reflect the actual
        path the player is on rather than the plan from act start.
        """
        current_floor = gs.floor

        # Use live cache if available — skip nodes at or before current floor
        if self._live_remaining_route is not None:
            remaining = [(f, t) for f, t in self._live_remaining_route if f > current_floor]
            if remaining:
                return remaining

        # Fall back to route plan (live cache absent or yielded nothing)
        if self._route_plan is None:
            return None
        route = self._route_plan
        step_idx = self._find_current_step_index(gs)
        if step_idx >= len(route.nodes):
            return None
        act_start_floor = self._act_start_floor(gs)
        result: list[tuple[int, str]] = []
        for i in range(step_idx, len(route.nodes)):
            _, row = route.coords[i]
            floor_num = act_start_floor + row + 1
            result.append((floor_num, route.nodes[i]))
        return result if result else None

    def _maybe_atomize_card_reward(
        self, gs: GameState, llm_dec: LLMDecision,
    ) -> dict | None:
        """Translate a card_reward LLM decision into atomic ``resolve_rewards``.

        Returns the action dict to use, or ``None`` to leave the existing
        action untouched.

        Triggers when:
          - config.RESOLVE_REWARDS_ATOMIC is enabled
          - state_type == "card_reward"
          - mod exposes "resolve_rewards" in available_actions

        Translation table:
          - choose_reward_card(option_index=N)         → resolve_rewards(option_index=N)
          - skip_reward_cards                          → resolve_rewards(option_index=-1)
          - choose_reward_alternative (skip variant)   → resolve_rewards(option_index=-1)
          - sacrifice_reward_cards                     → leave alone (no atomic equivalent)
        """
        if not config.RESOLVE_REWARDS_ATOMIC:
            return None
        if gs.state_type != "card_reward":
            return None
        avail = gs.available_actions or []
        if "resolve_rewards" not in avail:
            return None  # old mod, no atomic action exposed

        # Multi-pile guard: when the parent combat_rewards bundle held >=2
        # Card piles (Orrery, Question-Card-style relics, some boss/elite
        # rewards), resolve_rewards' drain logic silently discards every
        # CardReward button after the first pick — see GameActionService.cs
        # TryGetNextClaimableRewardButton (filter excludes CardReward once
        # _pendingCardRewardChoice resets to -1 post-pick). Fall back to the
        # non-atomic flow (claim_reward + choose_reward_card per pile) so
        # _handle_rewards can drain the remaining piles one-by-one. Single-
        # pile rewards (the common post-combat case) still atomize.
        if (self._card_reward_count_before_open or 0) >= 2:
            return None

        if llm_dec.action_name == "choose_reward_card":
            idx = self._safe_int(llm_dec.params.get("option_index"))
            if idx is None or idx < 0:
                return None
            return actions.resolve_rewards(option_index=idx)

        if llm_dec.action_name == "skip_reward_cards":
            return actions.resolve_rewards(option_index=-1)

        if llm_dec.action_name == "choose_reward_alternative":
            # Only atomize when the chosen alternative is a skip; sacrifice
            # has no equivalent in resolve_rewards and must stay multi-step.
            if self._is_reward_skip_alternative(gs, llm_dec):
                return actions.resolve_rewards(option_index=-1)
            return None

        return None

    @staticmethod
    def _is_reward_skip_alternative(gs: GameState, llm_dec: LLMDecision) -> bool:
        """True when choose_reward_alternative targets the Skip alternative."""
        cr = gs.reward
        if cr is None:
            return False
        idx = AgentLoop._safe_int(llm_dec.params.get("option_index"))
        if idx is None:
            return False
        for alt in cr.alternatives:
            if alt.index == idx:
                label = (alt.label or "").lower()
                return "skip" in label
        return False

    async def _execute_llm_decision(
        self, gs: GameState, llm_dec: LLMDecision, source: DecisionSource
    ) -> tuple[Decision | None, str | None]:
        """Execute an LLM-generated decision.

        Returns:
            (decision, None) on success.
            (None, error_message) if validation fails.
        """
        # Normalize params (e.g. target "null" → None, card name recovery) then validate
        llm_dec = self._normalize_llm_params(llm_dec, gs)
        validation_error = self._validate_llm_decision(gs, llm_dec)
        if validation_error:
            logger.warning(
                "LLM decision rejected: %s %s — %s",
                llm_dec.action_name, llm_dec.params, validation_error,
            )
            return None, validation_error

        selection_specs = self._selection_specs_from_indices(
            gs.selection,
            llm_dec.params.get("selected_indices"),
        )
        executed_selection_specs: list[SelectionCardSpec] = []
        if llm_dec.action_name == "select_deck_card":
            option_idx = self._safe_int(llm_dec.params.get("option_index"))
            if gs.selection:
                executed_selection_specs = (
                    selection_specs[:1]
                    if selection_specs
                    else self._selection_specs_from_indices(gs.selection, [option_idx])
                )
            action = actions.select_deck_card(option_idx) if option_idx is not None else llm_dec.to_action()
        else:
            action = llm_dec.to_action()

        # Reward atomization: translate card_reward decisions into a single
        # resolve_rewards call that drains gold/relic/potion + handles the
        # card pick + proceed in one round-trip. Saves ~3-5 MCP calls per
        # reward instance. Gated on (a) config flag and (b) mod exposing
        # resolve_rewards (old mod falls back to multi-step flow).
        atomized = self._maybe_atomize_card_reward(gs, llm_dec)
        if atomized is not None:
            action = atomized

        logger.info(
            "LLM decision: %s %s → %s — %s",
            llm_dec.action_name,
            llm_dec.params,
            action,
            llm_dec.reasoning,
        )

        # Resolve delta metadata for combat delta recording
        _delta_source: str | None = None
        _delta_target: str | None = None
        try:
            if llm_dec.action_name == "play_card":
                card_idx = llm_dec.params.get("card_index")
                if card_idx is not None and gs.hand:
                    for c in gs.hand:
                        if c.index == card_idx:
                            _delta_source = c.name
                            break
                tgt = llm_dec.params.get("target_index")
                _delta_target = self._resolve_delta_target(gs, tgt)
            elif llm_dec.action_name == "use_potion":
                pot_idx = llm_dec.params.get("potion_index")
                if pot_idx is not None and gs.potions:
                    for p in gs.potions:
                        if p.index == pot_idx:
                            _delta_source = p.name
                            break
                tgt = llm_dec.params.get("target_index")
                _delta_target = self._resolve_delta_target(gs, tgt)
            elif llm_dec.action_name == "end_turn":
                _delta_source = "turn_end"
            elif llm_dec.action_name == "select_deck_card":
                if executed_selection_specs and executed_selection_specs[0].name:
                    _delta_source = executed_selection_specs[0].name
                else:
                    idx = llm_dec.params.get("option_index")
                    if idx is not None and gs.selection:
                        for c in self._selection_selectable_cards(gs.selection):
                            if c.index == idx:
                                _delta_source = c.name
                                break
        except Exception:
            pass  # Delta metadata is best-effort

        await self._execute(action, delta_source=_delta_source, delta_target=_delta_target)

        # Detect Sly trigger for LLM-directed discard (select_deck_card)
        if llm_dec.action_name == "select_deck_card" and gs.selection:
            idx = llm_dec.params.get("option_index")
            if idx is not None:
                for c in self._selection_selectable_cards(gs.selection):
                    if c.index == idx and self._is_sly_discard(c, gs):
                        self._hcm_record_card_play(c.name, energy_cost=0)
                        self._hcm_record_sly_play(c.name)
                        logger.info("Sly trigger (LLM-discard): %s", c.name)
                        break

        # Track rest healing for non-combat scoring
        if llm_dec.action_name == "choose_rest_option" and gs.rest:
            idx = llm_dec.params.get("option_index")
            if idx is not None:
                enabled = [o for o in gs.rest.options if o.is_enabled]
                if 0 <= idx < len(enabled):
                    self._track_rest_heal(gs, enabled[idx].title)

            # Smith auto-execute: if LLM included smith_card_index, auto-select that card
            smith_card_idx = llm_dec.params.get("smith_card_index")
            if smith_card_idx is not None:
                smith_card_idx = self._safe_int(smith_card_idx)
                if smith_card_idx is not None:
                    logger.info("Smith auto-select: card index %d", smith_card_idx)
                    try:
                        await asyncio.sleep(config.ACTION_DELAY)
                        # Wait for card_select state
                        for _poll in range(6):
                            raw = await self._client.get_state()
                            fresh = parse_state(raw)
                            if fresh.state_type == "card_select" and fresh.selection:
                                break
                            await asyncio.sleep(0.5)
                        # Select the card
                        await self._execute(actions.select_deck_card(smith_card_idx))
                        await asyncio.sleep(config.ACTION_DELAY)
                        # Confirm
                        await self._execute(actions.confirm_selection())
                    except Exception:
                        logger.exception("Smith auto-select failed for card %d", smith_card_idx)

        # Post-action waits (best-effort: timeout just means animation is slow)
        if llm_dec.action_name == "end_turn":
            # Mark this round's end_turn as sent to prevent fallback spam
            if gs.combat:
                self._end_turn_sent_round = gs.combat_round
            try:
                await self._wait_for_play_phase_timed(reason="llm:end_turn")
            except McpTimeout:
                pass  # animation still playing, next poll will catch up
        elif llm_dec.action_name == "choose_map_node":
            # Cache chosen node's combat type before entering combat
            idx = llm_dec.params.get("option_index")
            if idx is not None and gs.next_map_options:
                for n in gs.next_map_options:
                    if n.index == idx:
                        self._cached_map_node_type = self._classify_map_node(n)
                        # Re-cache the remaining route through the ACTUAL chosen
                        # node. The earlier refresh in _handle_map_route_decision
                        # picked routes[0], which may start with a different
                        # child than the one the agent just selected.
                        if gs.map and gs.map.nodes:
                            self._refresh_live_remaining_route(
                                gs, chosen_coord=(n.col, n.row)
                            )
                        break
            try:
                await self._wait_for_state_change_timed(
                    "map",
                    reason="llm:choose_map_node",
                )
            except McpTimeout:
                pass  # animation still playing, next poll will catch up
        elif llm_dec.action_name == "buy_relic" and gs.state_type == "shop":
            # Some shop relics (e.g. Orrery, Kifuda) open a follow-up reward or
            # selection screen after purchase. Wait for that transition so the
            # next non-combat decision does not accidentally query the shop again.
            await self._wait_for_post_shop_relic_transition(
                gs,
                self._safe_int(llm_dec.params.get("option_index")),
            )
        elif llm_dec.action_name in ("buy_card", "buy_potion") and gs.state_type == "shop":
            await asyncio.sleep(0.3)
        elif (
            llm_dec.action_name == "close_shop_inventory"
            and gs.state_type == "shop"
            and gs.shop
            and gs.shop.is_open
        ):
            self._shop_pending_leave = True

        # Track multi-card selection: select_deck_card in card_select/hand_select
        if (
            llm_dec.action_name == "select_deck_card"
            and gs.state_type in ("card_select", "hand_select")
        ):
            # Initialize target if not yet set
            if self._card_select_target == 0 and gs.selection:
                cs = gs.selection
                # Prompt text is authoritative — C# mod's max_select is unreliable
                # for non-combat selections (BuildSelectionPayload returns defaults).
                target = 0
                if cs.prompt:
                    target = self._parse_select_count_from_prompt(cs.prompt)
                if target == 0:
                    target = cs.max_select if cs.max_select and cs.max_select > 0 else 0
                # If the LLM explicitly picked N cards via selected_indices,
                # target must be at least N (prevents clamping batch short).
                batch_indices = llm_dec.params.get("selected_indices")
                batch_len = len(batch_indices) if isinstance(batch_indices, list) else 0
                self._card_select_target = max(target, batch_len, 1)
                self._card_select_progress = self._selection_selected_count(cs)

            # Batch mode: selected_indices array (new path)
            sel_indices = llm_dec.params.get("selected_indices")
            if isinstance(sel_indices, list) and sel_indices:
                # Clamp to available: don't try to select more cards than exist
                max_available = (
                    len(self._selection_selectable_cards(gs.selection))
                    if gs.selection
                    else len(sel_indices)
                )
                clamped = selection_specs[:min(len(selection_specs), max_available, self._card_select_target)]
                executed_batch_specs: list[SelectionCardSpec] = []

                # Execute the first one already happened above via _execute(action).
                # Now execute the remaining indices back-to-back.
                first_idx = clamped[0].requested_index if clamped else None
                if first_idx is not None:
                    self._record_selection_choice(gs, first_idx)
                    executed_batch_specs.append(clamped[0])

                for requested in clamped[1:]:
                    extra_idx = requested.requested_index
                    if extra_idx is None:
                        continue
                    await asyncio.sleep(0.3)
                    try:
                        # Wait for selection screen to stabilise after prior pick
                        # (Sly triggers can cause animations that take several seconds)
                        fresh: GameState | None = None
                        for _wait in range(6):  # up to ~3s
                            fresh = await self._refresh_selection_state()
                            if fresh and fresh.selection:
                                break
                            await asyncio.sleep(0.5)

                        if fresh and fresh.selection:
                            gs = fresh
                            selectable_now = self._selection_selectable_cards(gs.selection)
                            all_cards_now = self._selection_cards(gs.selection)
                            selected_now = self._selection_selected_cards(gs.selection)
                            logger.info(
                                "Batch card select refresh: selectable=%s selected=%s all=%s "
                                "can_confirm=%s selected_count=%s state_type=%s",
                                [getattr(c, "name", "?") for c in selectable_now],
                                [getattr(c, "name", "?") for c in selected_now],
                                [getattr(c, "name", "?") for c in all_cards_now],
                                getattr(gs.selection, "can_confirm", None),
                                getattr(gs.selection, "selected_count", None),
                                gs.state_type,
                            )
                            if self._selection_session_progress(gs.selection) >= self._card_select_target:
                                break
                            selected_cards = selected_now
                            if selected_cards:
                                remaining_specs = [
                                    spec
                                    for spec in clamped
                                    if not any(
                                        self._selection_card_matches_spec(spec, selected_card)
                                        for selected_card in selected_cards
                                    )
                                ]
                                if not remaining_specs:
                                    break
                                requested = remaining_specs[0]
                            extra_idx, requested_name = self._resolve_selection_choice(gs, requested)
                            if extra_idx is None:
                                logger.warning(
                                    "Batch card select: card '%s' not found in selection, skipping",
                                    requested_name or requested.requested_index,
                                )
                                continue
                        else:
                            logger.warning(
                                "Batch card select: selection screen lost after prior pick, "
                                "skipping remaining (%s)",
                                requested.name or extra_idx,
                            )
                            break

                        extra_action = actions.select_deck_card(extra_idx)
                        result = await self._execute(extra_action, delta_source=requested_name or None)
                        if result is None:
                            logger.warning(
                                "Batch card select: execute returned None for idx=%d name=%s",
                                extra_idx, requested_name or "?",
                            )
                            break
                        made = self._record_selection_choice(gs, extra_idx)
                        executed_batch_specs.append(requested)
                        logger.info(
                            "Batch card select: idx=%d name=%s made=%d/%d",
                            extra_idx,
                            requested_name or "?",
                            made,
                            self._card_select_target,
                        )
                    except (McpActionError, McpError) as exc:
                        logger.warning(
                            "Batch card select idx=%d failed: %s — checking if can proceed",
                            extra_idx, exc,
                        )
                        # Fallback: if we can already proceed, stop selecting
                        break

                made = self._selection_session_progress(getattr(gs, "selection", None))
                logger.info(
                    "LLM batch card select: made=%d/%d selected=%s",
                    made, self._card_select_target, sorted(self._card_select_selected),
                )
            else:
                # Legacy single-index path
                idx = llm_dec.params.get("option_index")
                if idx is not None:
                    self._record_selection_choice(gs, idx)
                made = self._selection_session_progress(getattr(gs, "selection", None))
                logger.info(
                    "LLM card select: idx=%s made=%d/%d selected=%s",
                    idx, made, self._card_select_target, sorted(self._card_select_selected),
                )

            # Auto-confirm after reaching required count (or partial batch)
            made = self._selection_session_progress(getattr(gs, "selection", None))
            if made >= self._card_select_target:
                await asyncio.sleep(0.3)
                fresh = await self._refresh_selection_state()
                if (
                    fresh
                    and fresh.selection
                    and "confirm_selection" in fresh.available_actions
                ):
                    confirm = actions.confirm_selection()
                    try:
                        await self._execute(confirm, delta_source="confirm")
                        logger.info("Auto-confirm after LLM selected %d cards", made)
                    except (McpActionError, McpError) as exc:
                        logger.warning("Auto-confirm failed (may auto-process): %s", exc)
                else:
                    logger.info(
                        "Selection auto-processed after %d picks; skipping confirm",
                        made,
                    )
                self._reset_card_select_tracking()
            # Memory tracking for all selected cards (batch or single)
            if gs.selection and executed_selection_specs:
                floor_cs = gs.run.floor if gs.run else 0
                prompt_hint = (gs.selection.prompt or "").lower()
                all_selected = (
                    executed_batch_specs
                    if isinstance(sel_indices, list) and sel_indices
                    else executed_selection_specs
                )
                for c in all_selected:
                    if "remove" in prompt_hint:
                        self._hcm_record_deck_change(floor_cs, "remove", c.name, "card_select")
                        stm = self._hcm_short_term()
                        if stm is not None:
                            stm.record_card_removed(c.name)
                    elif "upgrade" in prompt_hint:
                        self._hcm_record_deck_change(floor_cs, "upgrade", c.name, "card_select")

        # Track card rewards: memory (deck_events + route node)
        floor = gs.run.floor if gs.run else 0
        if llm_dec.action_name == "choose_reward_card":
            idx = llm_dec.params.get("option_index") or llm_dec.params.get("card_index")
            if idx is not None and gs.reward:
                for c in gs.reward.card_options:
                    if c.index == idx:
                        # Memory: deck change + route node card gained
                        self._hcm_record_deck_change(floor, "add", c.name, "card_reward")
                        stm = self._hcm_short_term()
                        if stm is not None:
                            stm.record_card_gained(c.name)
                        logger.debug("Card taken: %s (floor %d)", c.name, floor)
                        break
        elif llm_dec.action_name in {"choose_reward_alternative", "skip_reward_cards"}:
            pass  # No additional tracking needed for skipped rewards
        elif llm_dec.action_name == "sacrifice_reward_cards":
            action = actions.sacrifice_reward_cards()
            logger.info("Sacrificing card reward (Pael's Wing)")
            # Compatibility path for older mods that do not expose choose_reward_alternative.

        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=llm_dec.reasoning,
            reasoning_zh=llm_dec.reasoning_zh,
            source=source.value,
            strategic_note=llm_dec.strategic_note,
        ), None

    @staticmethod
    def _safe_int(value: object) -> int | None:
        """Coerce a value to int, handling string ints from LLM responses."""
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _reward_alternative_label(option: object) -> str:
        return str(getattr(option, "label", "") or "").strip()

    def _find_reward_alternative(self, gs: GameState | None, label_hint: str) -> tuple[int, str] | None:
        if not gs or not gs.reward:
            return None
        needle = label_hint.strip().lower()
        for option in getattr(gs.reward, "alternatives", []) or []:
            label = self._reward_alternative_label(option)
            if not label or needle not in label.lower():
                continue
            idx = self._safe_int(getattr(option, "index", None))
            if idx is not None:
                return idx, label
        return None

    def _get_enemy_power_amount(self, power_name: str) -> int | None:
        """Return the amount of a named power on any alive enemy, or None if absent.

        Uses current gs.enemies when available, falling back to _last_known_enemies.
        """
        enemies = self._last_known_enemies  # Already a list; updated each observe step
        for e in enemies:
            for p in getattr(e, "powers", None) or []:
                if hasattr(p, "name") and p.name == power_name:
                    return getattr(p, "amount", None)
        return None

    def _normalize_llm_params(
        self,
        llm_dec: LLMDecision,
        gs: GameState | None = None,
    ) -> LLMDecision:
        """Return a new LLMDecision with normalized params (target, indices).

        Separated from validation so validation is pure (no side effects).
        Includes card-name recovery: if card_index is out of range but the
        reasoning mentions a card name that exists in hand, fix the index.
        """
        params = dict(llm_dec.params)  # shallow copy to avoid mutation
        action_name = llm_dec.action_name

        # In an open shop, `proceed` means "leave the room", but upstream
        # requires closing the inventory first.
        if (
            action_name == "proceed"
            and gs
            and gs.state_type == "shop"
            and gs.shop
            and gs.shop.is_open
            and "close_shop_inventory" in gs.available_actions
        ):
            action_name = "close_shop_inventory"

        # Normalize tool-use param names to upstream action params
        if llm_dec.action_name == "select_deck_card":
            if "card_index" in params and "option_index" not in params:
                params["option_index"] = params.pop("card_index")
            # Batch mode: extract first index as option_index for the initial execute
            sel_indices = params.get("selected_indices")
            if isinstance(sel_indices, list) and sel_indices:
                # Ensure all elements are ints
                params["selected_indices"] = [
                    int(x) if isinstance(x, (int, float)) else x for x in sel_indices
                ]
                if "option_index" not in params:
                    params["option_index"] = params["selected_indices"][0]
        elif llm_dec.action_name == "choose_reward_alternative":
            if "index" in params and "option_index" not in params:
                params["option_index"] = params.pop("index")

        if (
            action_name in {"skip_reward_cards", "sacrifice_reward_cards"}
            and gs
            and "choose_reward_alternative" in (gs.available_actions or [])
        ):
            label_hint = "skip" if action_name == "skip_reward_cards" else "sacrifice"
            resolved = self._find_reward_alternative(gs, label_hint)
            if resolved is not None:
                params["option_index"] = resolved[0]
                action_name = "choose_reward_alternative"
                logger.info(
                    "Mapped reward alias %s -> choose_reward_alternative(%d) [%s]",
                    llm_dec.action_name,
                    resolved[0],
                    resolved[1],
                )

        # Normalize target_index: -1 or None → None
        if "target_index" in params:
            raw_ti = params["target_index"]
            if raw_ti is None or raw_ti == -1:
                params["target_index"] = None
            elif isinstance(raw_ti, str):
                try:
                    if raw_ti.strip() in ("", "null", "none", "-1"):
                        params["target_index"] = None
                    else:
                        params["target_index"] = int(raw_ti)
                except ValueError:
                    params["target_index"] = None

        # Card-name recovery for play_card with out-of-range index
        if llm_dec.action_name == "play_card" and gs and gs.hand:
            idx = self._safe_int(params.get("card_index"))
            hand = gs.hand
            if idx is not None and (idx < 0 or idx >= len(hand)):
                # Try to find the card by name from reasoning text
                reasoning = llm_dec.reasoning or ""
                recovered = False
                for card in hand:
                    if card.playable and card.name.lower() in reasoning.lower():
                        logger.info(
                            "Card index recovery: %d → %d (matched '%s' in reasoning)",
                            idx, card.index, card.name,
                        )
                        params["card_index"] = card.index
                        recovered = True
                        break
                # If no name match, do NOT silently substitute — let validation
                # reject it so the retry path can give LLM feedback about the error
                if not recovered:
                    logger.warning(
                        "Card index %d out of range (hand size %d) and no name match in reasoning",
                        idx, len(hand),
                    )

            # Auto-fill missing target_index for targeted cards
            final_idx = self._safe_int(params.get("card_index"))
            if final_idx is not None and 0 <= final_idx < len(hand):
                card = hand[final_idx]
                needs_target = card.requires_target if hasattr(card, "requires_target") else False
                has_target = params.get("target_index") is not None
                if needs_target and not has_target and gs.enemies:
                    auto_idx = gs.enemies[0].index
                    logger.info("Auto-fill target_index for %s → %d", card.name, auto_idx)
                    params["target_index"] = auto_idx

        return LLMDecision(
            action_name=action_name,
            params=params,
            reasoning=llm_dec.reasoning,
            reasoning_zh=llm_dec.reasoning_zh,
            raw_text=llm_dec.raw_text,
            prompt_text=llm_dec.prompt_text,
            latency_ms=llm_dec.latency_ms,
            tokens_used=llm_dec.tokens_used,
            strategic_note=llm_dec.strategic_note,
        )

    def _validate_llm_decision(self, gs: GameState, llm_dec: LLMDecision) -> str | None:
        """Sanity-check LLM decision against current game state.

        Assumes params have been normalized via _normalize_llm_params().
        Returns None if valid, or an error message string describing why it failed.
        This method is pure — it does NOT mutate llm_dec.
        """
        # Pre-validate action against available_actions from mod
        avail = gs.available_actions
        if avail and llm_dec.action_name not in avail:
            return (
                f"action '{llm_dec.action_name}' not in available_actions: {avail}"
            )

        if llm_dec.action_name == "play_card":
            idx = self._safe_int(llm_dec.params.get("card_index"))
            hand = gs.hand
            if idx is None:
                return "card_index is missing or not an integer"
            if idx < 0 or idx >= len(hand):
                return (
                    f"card_index {idx} out of range "
                    f"(hand has {len(hand)} cards, valid: 0-{len(hand)-1})"
                )
            if not hand[idx].playable:
                playable = [i for i, c in enumerate(hand) if c.playable]
                return (
                    f"card at index {idx} ({hand[idx].name}) is not playable; "
                    f"playable indices: {playable}"
                )
            target_idx = self._safe_int(llm_dec.params.get("target_index"))
            card = hand[idx]
            if target_idx is not None and gs.enemies:
                alive_indices = {e.index for e in gs.enemies}
                if target_idx not in alive_indices:
                    return (
                        f"target_index {target_idx} not valid; "
                        f"alive indices: {sorted(alive_indices)}"
                    )
            # Ensure targeted cards have a target
            if card.requires_target and target_idx is None:
                alive = [e.index for e in gs.enemies]
                return f"card '{card.name}' requires target_index; alive indices: {sorted(alive)}"
        elif llm_dec.action_name == "use_potion":
            opt_idx = self._safe_int(llm_dec.params.get("option_index"))
            if opt_idx is None:
                return "option_index is missing or not an integer"
            valid_indices = {p.index for p in gs.potions if p.can_use}
            if opt_idx not in valid_indices:
                return f"potion option_index {opt_idx} not usable; valid: {sorted(valid_indices)}"
            target_idx = self._safe_int(llm_dec.params.get("target_index"))
            if target_idx is not None and gs.enemies:
                alive_indices = {e.index for e in gs.enemies}
                if target_idx not in alive_indices:
                    return (
                        f"potion target_index {target_idx} not valid; "
                        f"alive: {sorted(alive_indices)}"
                    )
        elif llm_dec.action_name == "select_deck_card":
            hs = gs.selection
            selectable_cards = self._selection_selectable_cards(hs)
            if not hs or not selectable_cards:
                return "no cards available for selection"
            valid_indices = {c.index for c in selectable_cards}

            # Support batch selection via selected_indices array
            sel_indices = llm_dec.params.get("selected_indices")
            if isinstance(sel_indices, list) and sel_indices:
                # Validate batch: no duplicates, all in range
                seen: set[int] = set()
                for i, raw_idx in enumerate(sel_indices):
                    idx = self._safe_int(raw_idx)
                    if idx is None:
                        return f"selected_indices[{i}] is not an integer: {raw_idx}"
                    if idx in seen:
                        return f"selected_indices has duplicate index {idx}"
                    if idx not in valid_indices:
                        return (
                            f"selected_indices[{i}]={idx} not in selectable cards; "
                            f"valid: {sorted(valid_indices)}"
                        )
                    seen.add(idx)
                # Clamp check: don't select more than available
                max_available = len(valid_indices)
                if len(sel_indices) > max_available:
                    return (
                        f"selected_indices has {len(sel_indices)} cards but only "
                        f"{max_available} are available"
                    )
            else:
                # Legacy single-index fallback
                idx = self._safe_int(
                    llm_dec.params.get("option_index", llm_dec.params.get("card_index"))
                )
                if idx is None:
                    return "selected_indices or option_index is required"
                if idx not in valid_indices:
                    return f"card_index {idx} not in selectable cards; valid: {sorted(valid_indices)}"
                # Reject re-selecting already-selected index (would toggle it off)
                if self._selection_indices_are_stable(gs) and idx in self._card_select_selected:
                    remaining = sorted(valid_indices - self._card_select_selected)
                    return (
                        f"card index {idx} already selected in this session "
                        f"(selecting it again would DESELECT it); "
                        f"pick a DIFFERENT card from: {remaining}"
                    )
        elif llm_dec.action_name == "choose_reward_alternative":
            reward = gs.reward
            if not reward or not reward.alternatives:
                return "no reward alternatives available"
            idx = self._safe_int(llm_dec.params.get("option_index"))
            if idx is None:
                return "option_index is missing or not an integer"
            valid_indices = {alt.index for alt in reward.alternatives}
            if idx not in valid_indices:
                return f"reward alternative index {idx} not valid; valid: {sorted(valid_indices)}"
        elif llm_dec.action_name == "discard_potion":
            # Reward-path discard: option_index is the held-potion slot index.
            # The forced-discard path in _handle_forced_potion_discard bypasses
            # this validator by constructing its own Decision directly, so this
            # branch is reward-context only in practice.
            idx = self._safe_int(llm_dec.params.get("option_index"))
            if idx is None:
                return "option_index is missing or not an integer"
            discardable = [
                p.index for p in (gs.potions or [])
                if getattr(p, "occupied", False) and getattr(p, "can_discard", False)
            ]
            if not discardable:
                return "no discardable held potions (all slots empty or potion not discardable)"
            if idx not in discardable:
                return (
                    f"discard_potion option_index {idx} not a discardable held slot; "
                    f"discardable: {sorted(discardable)}"
                )
        elif llm_dec.action_name == "choose_event_option":
            if not gs.event:
                return "not in an event"
            unlocked = [o for o in gs.event.options if not o.is_locked]
            if not unlocked:
                return "no unlocked event options"
            idx = self._safe_int(
                llm_dec.params.get("option_index", llm_dec.params.get("index"))
            )
            if idx is None:
                return "option_index is missing or not an integer"
            # C# indexes into full options list (including locked) — use raw state index
            valid = {o.index for o in unlocked}
            if idx not in valid:
                return f"event option index {idx} not valid (unlocked: {sorted(valid)})"
            llm_dec.params["option_index"] = idx
        elif llm_dec.action_name == "choose_rest_option":
            rest = gs.rest
            if not rest:
                return "not at a rest site"
            if gs.can_proceed:
                return "rest option already used, should proceed instead"
            enabled = [o for o in rest.options if o.is_enabled]
            if not enabled:
                return "no enabled rest options available"
            idx = self._safe_int(
                llm_dec.params.get("option_index", llm_dec.params.get("index"))
            )
            if idx is None:
                option_name = llm_dec.params.get("option", "")
                if option_name:
                    name_lower = option_name.lower()
                    for o in enabled:
                        if (o.option_id and o.option_id.lower() == name_lower) or \
                           (o.title and o.title.lower() == name_lower):
                            idx = o.index
                            break
            if idx is None:
                return "option_index is missing or not an integer"
            valid_indices = {o.index for o in enabled}
            if idx not in valid_indices:
                return f"option_index {idx} not valid; enabled: {sorted(valid_indices)}"
            # C# indexes into full options list — use raw state index
            llm_dec.params["option_index"] = idx
        elif llm_dec.action_name in ("shop_plan",):
            # Shop plan validated during parse + execution, not here
            return None
        elif llm_dec.action_name in (
            "buy_card",
            "buy_relic",
            "buy_potion",
            "remove_card_at_shop",
        ):
            if llm_dec.action_name == "remove_card_at_shop":
                if not gs.shop or not gs.shop.card_removal or not gs.shop.card_removal.available:
                    return "card removal not available"
                if not gs.shop.card_removal.enough_gold:
                    return f"cannot afford card removal ({gs.shop.card_removal.price}g)"
            else:
                idx = self._safe_int(llm_dec.params.get("option_index"))
                if idx is None:
                    return "option_index is missing or not an integer"
                shop = gs.shop
                if not shop:
                    return "not in shop"
                items = {
                    "buy_card": shop.cards,
                    "buy_relic": shop.relics,
                    "buy_potion": shop.potions,
                }.get(llm_dec.action_name, [])
                item = next((i for i in items if i.index == idx), None)
                if item is None:
                    valid = [i.index for i in items if i.is_stocked]
                    return f"option_index {idx} not found; stocked: {sorted(valid)}"
                if not item.is_stocked:
                    return f"'{item.name}' (index {idx}) sold out"
                if not item.enough_gold:
                    return f"cannot afford '{item.name}' ({item.price}g)"
        elif llm_dec.action_name == "choose_treasure_relic":
            idx = self._safe_int(llm_dec.params.get("option_index"))
            if idx is None:
                return "option_index is missing or not an integer"
            tr = gs.chest
            if not tr or not tr.relic_options:
                return "no relics available"
            valid_indices = {r.index for r in tr.relic_options}
            if idx not in valid_indices:
                return f"relic index {idx} not valid; valid: {sorted(valid_indices)}"
        return None

    # ── Mechanical handlers (no LLM needed) ────────────────────

    async def _handle_mechanical(self, gs: GameState) -> Decision | None:
        """Handle states that don't need LLM reasoning.

        Dispatch uses available_actions with state_type fallback for
        backward compatibility with older mod versions.
        """
        avail = gs.available_actions

        # In-combat card selection states must be checked BEFORE combat,
        # because hand_select/card_select occur during combat but need
        # their own handlers (not the combat fallback).
        if gs.state_type == "cards_view":
            return await self._handle_cards_view(gs)
        if gs.state_type == "hand_select" and ("select_deck_card" in avail or not avail):
            return await self._handle_hand_select(gs)
        if gs.state_type == "card_select" and ("select_deck_card" in avail or not avail):
            return await self._handle_card_select(gs)
        if "play_card" in avail or "end_turn" in avail or (not avail and gs.is_combat):
            return await self._handle_combat_fallback(gs)
        if (
            "claim_reward" in avail
            or "collect_rewards_and_proceed" in avail
            or gs.state_type == "combat_rewards"
        ):
            return await self._handle_rewards(gs)
        if "choose_reward_card" in avail or (not avail and gs.state_type == "card_reward"):
            return await self._handle_card_reward_fallback(gs)
        if "choose_map_node" in avail or (not avail and gs.is_map):
            return await self._handle_map_fallback(gs)
        if "choose_event_option" in avail or gs.state_type == "event":
            return await self._handle_event_fallback(gs)
        if "choose_rest_option" in avail or gs.state_type == "rest_site":
            return await self._handle_rest_fallback(gs)
        if (
            any(
                a in avail
                for a in ("buy_card", "buy_relic", "buy_potion", "remove_card_at_shop")
            )
            or gs.state_type == "shop"
        ):
            return await self._handle_shop_fallback(gs)
        if "choose_treasure_relic" in avail or "open_chest" in avail or gs.state_type == "treasure":
            return await self._handle_treasure(gs)

        if self._is_forced_potion_discard_state(avail):
            return await self._handle_forced_potion_discard(gs)

        logger.warning("Unhandled state: type=%s actions=%s", gs.state_type, avail)
        await asyncio.sleep(1.0)
        return None

    async def _handle_combat_fallback(self, gs: GameState) -> Decision | None:
        """Random combat fallback when LLM is unavailable."""
        combat = gs.combat
        if not combat or not gs.is_play_phase:
            await asyncio.sleep(0.3)
            return None

        # If there are playable cards, ALWAYS play one (regardless of end_turn_sent_round).
        # The end_turn guard only applies when there's truly nothing to play.
        playable = gs.playable_cards
        if playable:
            card = random.choice(playable)
            target_index = None
            if card.target_type in ("AnyEnemy", "single_enemy") and gs.enemies:
                target_index = random.choice(gs.enemies).index

            action = actions.play_card(card.index, target_index)
            await self._execute(
                action,
                delta_source=card.name,
                delta_target=self._resolve_delta_target(gs, target_index),
            )
            # V2: record card play in short-term memory
            self._hcm_record_card_play(card.name, self._card_energy_cost(card))
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Random: play {card.name}",
                source="random",
            )

        # No playable cards — end turn (with round guard to prevent spam)
        current_round = gs.combat_round
        if current_round == self._end_turn_sent_round:
            await asyncio.sleep(1.0)  # Wait for round transition animation
            return None
        self._end_turn_sent_round = current_round
        action = actions.end_turn()
        await self._execute(action, delta_source="turn_end")
        try:
            await self._wait_for_play_phase_timed(reason="fallback:end_turn")
        except McpTimeout:
            pass
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning="No playable cards, end turn",
            source="random",
        )

    async def _handle_rewards(self, gs: GameState) -> Decision | None:
        """Claim rewards mechanically."""
        rewards = gs.reward
        if not rewards:
            return None

        # --- Detect pick vs skip from previous card reward open ---
        # After returning from card_reward → combat_rewards, the Card count
        # tells us whether the agent picked (count decreased) or skipped
        # (count unchanged).  On pick, the claimed index is gone and higher
        # indices shifted down by 1 — adjust _opened_card_rewards accordingly.
        if self._card_reward_count_before_open is not None:
            current_card_count = sum(
                1 for r in rewards.rewards if r.reward_type.lower() == "card"
            )
            if current_card_count < self._card_reward_count_before_open:
                # Card was picked → remove claimed index, shift higher indices
                idx = self._last_opened_card_index
                if idx is not None:
                    self._opened_card_rewards.discard(idx)
                    self._opened_card_rewards = {
                        (i - 1 if i > idx else i)
                        for i in self._opened_card_rewards
                    }
            # else: card was skipped, indices unchanged — no adjustment needed
            self._card_reward_count_before_open = None
            self._last_opened_card_index = None

        # Quick exit: only use shortcut when no actionable rewards remain.
        # Card rewards stay claimable=True after being opened, so exclude
        # already-opened cards from the check.
        has_unclaimed = any(
            item.claimable
            and not (item.reward_type.lower() == "card" and item.index in self._opened_card_rewards)
            for item in rewards.rewards
        )
        if (
            "collect_rewards_and_proceed" in gs.available_actions
            and not rewards.pending_card_choice
            and not has_unclaimed
        ):
            self._opened_card_rewards.clear()
            action = actions.collect_rewards_and_proceed()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Collect all rewards and proceed",
                source="random",
            )

        open_potion_slots = gs.open_potion_slots
        for item in rewards.rewards:
            if not item.claimable:
                continue
            rtype = item.reward_type.lower()
            if rtype == "potion" and open_potion_slots <= 0:
                logger.info("Skipping potion reward (no open slots): %s", item.description)
                continue
            if rtype in ("gold", "potion", "relic", "specialcard"):
                gold_before = gs.gold if rtype == "gold" else 0
                action = actions.claim_reward(item.index)
                await self._execute(action)
                if rtype == "potion":
                    open_potion_slots -= 1
                # `description` may carry unsubstituted localization templates
                # (e.g. `{gold} Gold` for combat gold rewards) since the C# mod
                # passes localization values through verbatim. Strip any `{...}`
                # placeholder; for gold rewards specifically, observe the
                # post-claim state and substitute the actual gold delta.
                desc = _re.sub(r"\{[a-z_]+\}\s*", "", item.description or "").strip()
                if rtype == "gold":
                    try:
                        post_gs = parse_state(await self._client.get_state())
                        delta = post_gs.gold - gold_before
                    except Exception:
                        delta = 0
                    if delta > 0:
                        desc = f"{delta} Gold"
                claim_reasoning = f"Claim {rtype}: {desc}" if desc else f"Claim {rtype}"
                return Decision(
                    floor=gs.run.floor if gs.run else 0,
                    state_type=gs.state_type,
                    action=action,
                    reasoning=claim_reasoning,
                    source="random",
                )

        card_items = [
            r for r in rewards.rewards
            if r.reward_type.lower() == "card" and r.index not in self._opened_card_rewards
        ]
        if card_items:
            item = card_items[0]
            self._opened_card_rewards.add(item.index)
            self._card_reward_count_before_open = sum(
                1 for r in rewards.rewards if r.reward_type.lower() == "card"
            )
            self._last_opened_card_index = item.index
            action = actions.claim_reward(item.index)
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Open card reward",
                source="random",
            )

        # All rewards handled (gold/potion/relic claimed, cards opened or skipped)
        if rewards.can_proceed:
            self._opened_card_rewards.clear()
            self._card_reward_count_before_open = None
            self._last_opened_card_index = None
            # Use collect_rewards_and_proceed if available (REWARD screen),
            # fall back to proceed for other contexts
            if "collect_rewards_and_proceed" in gs.available_actions:
                action = actions.collect_rewards_and_proceed()
            else:
                action = actions.proceed()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="All rewards claimed, proceed",
                source="random",
            )
        return None

    async def _handle_card_reward_fallback(self, gs: GameState) -> Decision | None:
        cr = gs.reward
        if not cr:
            return None
        skip_alt = self._find_reward_alternative(gs, "skip")
        if skip_alt is not None:
            if "choose_reward_alternative" in gs.available_actions:
                action = actions.choose_reward_alternative(skip_alt[0])
            elif "skip_reward_cards" in gs.available_actions:
                action = actions.skip_reward_cards()
            else:
                action = None
        else:
            action = None
        if action is not None:
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Safe fallback: skip card reward",
                source="random",
            )
        if cr.card_options:
            card = random.choice(cr.card_options)
            action = actions.choose_reward_card(card.index)
            await self._execute(action)
            # Memory: record card taken (same hooks as LLM path)
            floor = gs.run.floor if gs.run else 0
            self._hcm_record_deck_change(floor, "add", card.name, "card_reward")
            stm = self._hcm_short_term()
            if stm is not None:
                stm.record_card_gained(card.name)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Fallback pick: {card.name}",
                source="random",
            )
        return None

    async def _handle_map_fallback(self, gs: GameState) -> Decision | None:
        options = gs.next_map_options
        if not options:
            await asyncio.sleep(0.5)
            return None
        node = random.choice(options)
        self._cached_map_node_type = self._classify_map_node(node)
        if gs.map and gs.map.nodes:
            self._refresh_live_remaining_route(
                gs, chosen_coord=(node.col, node.row)
            )
        action = actions.choose_map_node(node.index)
        await self._execute(action)
        try:
            await self._wait_for_state_change_timed(
                "map",
                reason="fallback:choose_map_node",
            )
        except McpTimeout:
            pass
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=f"Random path: {node.node_type}",
            source="random",
        )

    async def _handle_event_fallback(self, gs: GameState) -> Decision | None:
        ev = gs.event
        if not ev:
            return None
        if ev.is_finished:
            # Event resolved — proceed
            action = actions.proceed()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Event finished, proceed",
                source="random",
            )
        available = [o for o in ev.options if not o.is_locked]
        if not available:
            # No options available — two possibilities:
            # (a) Event options haven't loaded yet (state mid-transition): wait and retry
            # (b) Event finished showing result text: need to proceed
            # Strategy: wait one poll, then check can_proceed before trying proceed.
            # This avoids the "proceed" spam during event loading.
            await asyncio.sleep(0.3)
            if gs.can_proceed:
                action = actions.proceed()
                result = await self._execute(action)
                if result is not None:
                    return Decision(
                        floor=gs.run.floor if gs.run else 0,
                        state_type=gs.state_type,
                        action=action,
                        reasoning="Event: no options, proceed",
                        source="random",
                    )
            return None  # Will retry next poll (options may load, or stuck detection kicks in)
        proceed_opts = [o for o in available if o.is_proceed]
        option = random.choice(proceed_opts) if proceed_opts else random.choice(available)
        # C# indexes into full options list — use raw state index
        action = actions.choose_event_option(option.index)
        await self._execute(action)
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=f"Event: {option.title}",
            source="random",
        )

    async def _gather_smith_preview(
        self, gs: GameState,
    ) -> list | None:
        """Enter Smith via MCP, read selectable cards, then cancel back to rest.

        Returns the list of ``RawSelectionCardPayload`` from the game's
        card_select screen, or *None* on failure.  The agent uses this data
        to show real upgrade previews in the rest prompt.
        """
        rest = gs.rest
        if not rest:
            return None

        # Find the Smith option
        smith_idx: int | None = None
        for opt in rest.options:
            if opt.is_enabled and "smith" in opt.title.lower():
                smith_idx = opt.index
                break
        if smith_idx is None:
            logger.debug("No enabled Smith option found at rest site")
            return None

        try:
            # 1. Enter Smith
            logger.info("Smith preview: entering Smith (index=%d) to read card data", smith_idx)
            await self._client.post_action(actions.choose_rest_option(smith_idx))
            await asyncio.sleep(config.ACTION_DELAY)

            # 2. Poll for card_select state (up to 3s)
            smith_cards = None
            for _ in range(6):
                raw = await self._client.get_state()
                fresh = parse_state(raw)
                if fresh.selection and fresh.state_type == "card_select":
                    sel = fresh.selection
                    cards = list(sel.selectable_cards or sel.cards or [])
                    if cards:
                        smith_cards = cards
                        logger.info(
                            "Smith preview: got %d upgradeable cards from game",
                            len(cards),
                        )
                    break
                await asyncio.sleep(0.5)

            # 3. Cancel Smith — use cancel_selection to return to rest
            await self._client.post_action(actions.cancel_selection())
            await asyncio.sleep(config.ACTION_DELAY)

            # 4. Wait for rest_site state to return (up to 3s)
            for _ in range(6):
                raw = await self._client.get_state()
                fresh = parse_state(raw)
                if fresh.state_type == "rest_site":
                    logger.info("Smith preview: returned to rest site successfully")
                    break
                await asyncio.sleep(0.5)
            else:
                logger.warning(
                    "Smith preview: did not return to rest_site (now at %s)",
                    fresh.state_type,
                )

            return smith_cards

        except Exception:
            logger.exception("Smith preview failed — proceeding without upgrade data")
            return None

    async def _handle_rest_fallback(self, gs: GameState) -> Decision | None:
        rest = gs.rest
        if not rest:
            return None
        # Check can_proceed FIRST — after using an option, just leave
        if gs.can_proceed:
            action = actions.proceed()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Proceed from rest",
                source="random",
            )
        enabled = [o for o in rest.options if o.is_enabled]
        if not enabled:
            return None
        option = random.choice(enabled)
        # C# indexes into full options list — use raw state index
        action = actions.choose_rest_option(option.index)
        await self._execute(action)
        # Track rest healing for non-combat scoring
        self._track_rest_heal(gs, option.title)
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=f"Rest: {option.title}",
            source="random",
        )

    async def _handle_shop_fallback(self, gs: GameState) -> Decision | None:
        self._shop_plan = None
        foul_potion_result = await self._handle_shop_foul_potion(gs)
        if foul_potion_result is not None:
            return foul_potion_result
        if gs.shop and gs.shop.is_open and "close_shop_inventory" in gs.available_actions:
            action = {"action": "close_shop_inventory"}
            await self._execute(action)
            self._shop_pending_leave = True
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Close shop inventory to leave",
                source="random",
            )

        action = actions.proceed()
        await self._execute(action)
        self._shop_pending_leave = False
        self._shop_auto_opened_this_visit = False
        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning="Skip shop",
            source="random",
        )

    # ── Shop Plan helpers ──────────────────────────────────────────────

    def _parse_shop_plan(self, decision_input: dict) -> ShopPlan | None:
        """Parse a shop_plan decision dict into a ShopPlan object."""
        purchases = decision_input.get("purchases")
        if not isinstance(purchases, list):
            logger.warning("shop_plan: 'purchases' is not a list")
            return None

        items: list[ShopPlanItem] = []
        for p in purchases:
            if not isinstance(p, dict):
                continue
            action = p.get("action", "")
            item_name = p.get("item_name", "")
            price = p.get("price", 0)
            gold_after = p.get("gold_after", 0)
            reason = p.get("reason", "")
            if not action or not item_name:
                continue
            # Normalize action name
            if action == "remove_card":
                action = "remove_card_at_shop"
            items.append(ShopPlanItem(
                action=action,
                item_name=item_name,
                price=int(price) if price else 0,
                gold_after=int(gold_after) if gold_after else 0,
                reason=reason,
            ))

        return ShopPlan(
            items=items,
            reasoning=decision_input.get("reasoning", ""),
            strategic_note=decision_input.get("strategic_note", ""),
        )

    def _resolve_shop_item_index(
        self, gs: GameState, plan_item: ShopPlanItem,
    ) -> int | None:
        """Find the option_index for a planned purchase in the current shop state."""
        shop = gs.shop
        if not shop:
            return None

        if plan_item.action == "remove_card_at_shop":
            return -1  # Sentinel: no option_index needed

        name_lower = plan_item.item_name.lower().strip()
        item_lists = {
            "buy_card": shop.cards,
            "buy_relic": shop.relics,
            "buy_potion": shop.potions,
        }
        items = item_lists.get(plan_item.action, [])
        for item in items:
            if not item.is_stocked:
                continue
            item_name = (item.name or "").lower().strip()
            if item_name == name_lower:
                return item.index
        return None

    def _summarize_shop_plan_invalid_state(
        self, gs: GameState, plan_item: "ShopPlanItem | None",
    ) -> str:
        """Build a feedback string for the LLM after a shop plan is rejected.

        Lists the actually-available shop options and current gold so the LLM
        can produce a valid retry plan instead of repeating the rejected pick.
        """
        lines: list[str] = []
        if plan_item is not None:
            lines.append(
                f"Previous plan's first item `{plan_item.action} '{plan_item.item_name}'` was rejected."
            )
        shop = gs.shop if gs else None
        if shop is None:
            lines.append("Shop is no longer open.")
            return "\n".join(lines)
        if shop.card_removal is None or not shop.card_removal.available:
            lines.append("- card removal is NOT available (already used or unavailable).")
        else:
            cr = shop.card_removal
            lines.append(
                f"- card removal available at {cr.price}g (enough_gold={cr.enough_gold})."
            )
        for label, items in (
            ("relics", shop.relics or []),
            ("cards", shop.cards or []),
            ("potions", shop.potions or []),
        ):
            stocked = [i for i in items if getattr(i, "is_stocked", True)]
            if not stocked:
                lines.append(f"- no {label} stocked.")
            else:
                names = ", ".join(
                    f"'{i.name}'({i.price}g{'' if i.enough_gold else ',unaffordable'})"
                    for i in stocked
                )
                lines.append(f"- {label} stocked: {names}")
        lines.append(f"Current gold: {gs.gold}g.")
        return "\n".join(lines)

    def _validate_shop_plan_item_buyable(
        self, gs: GameState, plan_item: ShopPlanItem, option_index: int,
    ) -> str | None:
        """Return a reason when the planned shop item is no longer buyable."""
        shop = gs.shop
        if not shop:
            return "not in shop"

        item_lists = {
            "buy_card": shop.cards,
            "buy_relic": shop.relics,
            "buy_potion": shop.potions,
        }
        items = item_lists.get(plan_item.action)
        if items is None:
            return None

        item = next((i for i in items if i.index == option_index), None)
        if item is None:
            return f"option_index {option_index} no longer exists"
        if not item.is_stocked:
            return f"'{item.name}' is sold out"
        if not item.enough_gold:
            # Upstream marks potions as enough_gold=False when held-potion slots
            # are full (not just when the player can't afford it). Distinguish
            # these so the executor can auto-inject a discard_potion step rather
            # than aborting the plan.
            if plan_item.action == "buy_potion" and gs.gold >= item.price:
                return "_potion_slots_full"
            return f"'{item.name}' is not currently buyable ({item.price}g)"
        return None

    async def _execute_shop_plan_step(self, gs: GameState) -> Decision | None:
        """Execute the next item in the active shop plan.

        Returns a Decision on success, or None if the plan should be
        discarded (gold mismatch, item not found, etc.).
        """
        plan = self._shop_plan
        if plan is None or plan.is_complete:
            return None

        # Skip any leading items that should be silently dropped (e.g. a
        # buy_potion when slots are full and the plan has no discard step).
        while not plan.is_complete:
            item = plan.current_item
            if item is None:
                return None
            if item.action == "buy_potion":
                idx_for_skip = self._resolve_shop_item_index(gs, item)
                if idx_for_skip is not None:
                    reason = self._validate_shop_plan_item_buyable(gs, item, idx_for_skip)
                    if reason == "_potion_slots_full":
                        logger.warning(
                            "Shop plan: skipping buy_potion '%s' — potion slots full and plan has no discard_potion step (saving %dg)",
                            item.item_name, item.price,
                        )
                        plan.advance()
                        continue
            break

        if plan.is_complete:
            return None
        item = plan.current_item
        if item is None:
            return None

        # discard_potion: free a held-potion slot before a buy_potion.
        # No gold cost, no shop-item lookup — item_name refers to a HELD potion.
        if item.action == "discard_potion":
            held = [
                p for p in (gs.potions or [])
                if getattr(p, "occupied", False) and getattr(p, "can_discard", False)
            ]
            target_name = (item.item_name or "").strip().lower()
            match = next(
                (p for p in held if (getattr(p, "name", "") or "").strip().lower() == target_name),
                None,
            )
            if match is None:
                logger.warning(
                    "Shop plan: held potion '%s' not found (have: %s) — replanning",
                    item.item_name,
                    [getattr(p, "name", None) for p in held],
                )
                self._shop_plan = None
                return None
            action = actions.discard_potion(match.index)
            logger.info(
                "Shop plan [%d/%d]: discard_potion '%s' (slot %d) — %s",
                plan.current_index + 1, len(plan.items),
                item.item_name, match.index, item.reason,
            )
            await self._execute(action)
            plan.advance()
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Shop plan: discard {item.item_name}",
                source="plan",
            )

        # Gold check: if actual gold < item price, discard plan for replan
        if item.action != "remove_card_at_shop":
            if gs.gold < item.price:
                logger.warning(
                    "Shop plan gold mismatch: need %dg for '%s' but have %dg — replanning",
                    item.price, item.item_name, gs.gold,
                )
                self._shop_plan = None
                return None

        # Validate card removal availability
        if item.action == "remove_card_at_shop":
            if not gs.shop or not gs.shop.card_removal or not gs.shop.card_removal.available:
                logger.warning("Shop plan: card removal not available — replanning")
                self._shop_plan = None
                return None
            if not gs.shop.card_removal.enough_gold:
                logger.warning("Shop plan: can't afford card removal — replanning")
                self._shop_plan = None
                return None

        # Resolve option_index by name
        idx = self._resolve_shop_item_index(gs, item)
        if idx is None:
            logger.warning(
                "Shop plan: item '%s' not found in shop — replanning",
                item.item_name,
            )
            self._shop_plan = None
            return None
        unavailable = self._validate_shop_plan_item_buyable(gs, item, idx)
        if unavailable:
            logger.warning(
                "Shop plan: item '%s' no longer buyable: %s — replanning",
                item.item_name,
                unavailable,
            )
            self._shop_plan = None
            return None

        # Build and execute the action
        if item.action == "remove_card_at_shop":
            action = {"action": "remove_card_at_shop"}
        else:
            action = {"action": item.action, "option_index": idx}

        logger.info(
            "Shop plan [%d/%d]: %s '%s' (%dg) — %s",
            plan.current_index + 1, len(plan.items),
            item.action, item.item_name, item.price, item.reason,
        )

        await self._execute(action)

        # Post-purchase handling
        if item.action == "buy_relic":
            await self._wait_for_post_shop_relic_transition(gs, idx if idx != -1 else None)
        elif item.action in ("buy_card", "buy_potion"):
            await asyncio.sleep(0.3)

        plan.advance()

        # Gold verification: re-poll and check if next item is affordable
        try:
            raw = await self._client.get_state()
            fresh_gs = parse_state(raw)
            if not plan.is_complete and fresh_gs.state_type != "shop":
                # Follow-up scene triggered — plan stays, will resume when back to shop
                logger.info(
                    "Shop plan: follow-up scene triggered (%s), will resume after",
                    fresh_gs.state_type,
                )
            elif not plan.is_complete:
                next_item = plan.current_item
                if next_item and next_item.action != "remove_card_at_shop" and fresh_gs.gold < next_item.price:
                    logger.warning(
                        "Shop plan: can't afford next item '%s' (%dg, have %dg) — replanning",
                        next_item.item_name, next_item.price, fresh_gs.gold,
                    )
                    self._shop_plan = None
        except Exception:
            pass  # Best-effort verification

        return Decision(
            floor=gs.run.floor if gs.run else 0,
            state_type=gs.state_type,
            action=action,
            reasoning=f"Shop plan [{plan.current_index}/{len(plan.items)}]: {item.reason}",
            source="plan",
        )

    async def _handle_hand_select(self, gs: GameState) -> Decision | None:
        hs = gs.selection
        if not hs:
            return None
        selectable_cards = self._selection_selectable_cards(hs)
        can_confirm_now = hs.can_confirm or "confirm_selection" in gs.available_actions

        # Determine required selection count (once per session, same logic as card_select)
        if self._card_select_target == 0:
            target = hs.max_select if hs.max_select and hs.max_select > 0 else 0
            if target == 0 and hs.prompt:
                target = self._parse_select_count_from_prompt(hs.prompt)
            self._card_select_target = max(target, 1)
            self._card_select_progress = self._selection_selected_count(hs)
            self._card_select_selected.clear()
            logger.info(
                "Hand select session: target=%d (prompt=%s, max_select=%s)",
                self._card_select_target,
                (hs.prompt or "")[:60],
                hs.max_select,
            )

        selected_count = self._selection_selected_count(hs)
        made = self._selection_session_progress(hs)

        # Optional hand selections (e.g. Retain up to 1) can be safely skipped.
        # This is especially important when a run starts directly on this screen
        # before a combat conversation has been initialized.
        if hs.min_select == 0 and made == 0 and selected_count == 0 and can_confirm_now:
            action = actions.confirm_selection()
            try:
                await self._execute(action, delta_source="confirm")
            except (McpActionError, McpError) as exc:
                logger.warning("confirm_selection failed on optional hand select: %s", exc)
            self._reset_card_select_tracking()
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Confirm optional hand selection without choosing a card",
                source="random",
            )

        # Confirm if API says ready OR we've selected the required number
        if (can_confirm_now and (selected_count > 0 or made > 0)) or made >= self._card_select_target:
            # Single-card selections auto-process without confirm
            if self._card_select_target > 1 or can_confirm_now:
                action = actions.confirm_selection()
                try:
                    await self._execute(action, delta_source="confirm")
                except (McpActionError, McpError) as exc:
                    logger.warning("confirm_selection failed (may auto-process): %s", exc)
            else:
                action = {"action": "auto_process_single_select"}
                logger.info("Single-card select done, skipping confirm")
            logger.info(
                "Confirm hand selection (made=%d, target=%d, can_confirm=%s)",
                made, self._card_select_target, can_confirm_now,
            )
            self._reset_card_select_tracking()
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Confirm hand selection ({made}/{self._card_select_target})",
                source="random",
            )

        if selectable_cards:
            # Exclude already-selected indices to avoid toggling them off
            available = [c for c in selectable_cards if c.index not in self._card_select_selected]
            if not available:
                available = list(selectable_cards)  # Fallback: all exhausted, retry any
            card = random.choice(available)
            action = actions.select_deck_card(card.index)
            await self._execute(action, delta_source=card.name)
            # Detect Sly trigger: discard by card effect → auto-play
            if self._is_sly_discard(card, gs):
                self._hcm_record_card_play(card.name, energy_cost=0)
                self._hcm_record_sly_play(card.name)
                logger.info("Sly trigger (mechanical-discard): %s", card.name)
            made = self._record_selection_choice(gs, card.index)
            logger.info(
                "Hand select: picked %s idx=%d (made=%d/%d)",
                card.name,
                card.index,
                made,
                self._card_select_target,
            )

            # Auto-confirm if we just hit the target
            if made >= self._card_select_target:
                if self._card_select_target > 1:
                    await asyncio.sleep(0.3)
                    confirm = actions.confirm_selection()
                    try:
                        await self._execute(confirm, delta_source="confirm")
                        logger.info("Auto-confirm hand selection after %d cards", made)
                    except (McpActionError, McpError) as exc:
                        logger.warning(
                            "Auto-confirm hand select failed (may auto-process): %s",
                            exc,
                        )
                else:
                    logger.info("Single-card hand select done, skipping confirm")
                self._reset_card_select_tracking()
                return Decision(
                    floor=gs.run.floor if gs.run else 0,
                    state_type=gs.state_type,
                    action=action,
                    reasoning=f"Select {card.name} + confirm ({made} cards done)",
                    source="random",
                )

            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Select {card.name} ({made}/{self._card_select_target})",
                source="random",
            )
        return None

    async def _handle_card_select(self, gs: GameState) -> Decision | None:
        cs = gs.selection
        if not cs:
            if (
                "confirm_selection" in gs.available_actions
                and "select_deck_card" not in gs.available_actions
            ):
                # Upstream can briefly drop the selection payload after a card
                # click while still exposing the confirm button.
                action = actions.confirm_selection()
                try:
                    await self._execute(action, delta_source="confirm")
                except (McpActionError, McpError) as exc:
                    logger.warning("confirm_selection failed without selection payload: %s", exc)
                logger.info(
                    "Confirm selection without payload (made=%d, target=%d)",
                    self._selection_session_progress(),
                    self._card_select_target,
                )
                self._reset_card_select_tracking()
                return Decision(
                    floor=gs.run.floor if gs.run else 0,
                    state_type=gs.state_type,
                    action=action,
                    reasoning="Confirm selection after payload-less card_select refresh",
                    source="heuristic",
                )
            return None
        selectable_cards = self._selection_selectable_cards(cs)

        if self._is_pack_selection(gs):
            self._sync_pack_selection_session(gs)
            self._record_pack_preview_from_selection(gs)
            preview_result = await self._handle_pack_selection_preview(gs)
            if preview_result is not None:
                return preview_result
            if cs.can_confirm:
                action = actions.confirm_selection()
                try:
                    await self._execute(action, delta_source="confirm")
                except (McpActionError, McpError) as exc:
                    logger.warning("confirm_selection failed on pack select: %s", exc)
                self._reset_card_select_tracking()
                return Decision(
                    floor=gs.run.floor if gs.run else 0,
                    state_type=gs.state_type,
                    action=action,
                    reasoning="Confirm current pack selection",
                    source="heuristic",
                )

        # Determine required selection count (once per selection session)
        if self._card_select_target == 0:
            # Prefer API fields, fall back to prompt text parsing
            target = cs.max_select if cs.max_select and cs.max_select > 0 else 0
            if target == 0 and cs.prompt:
                target = self._parse_select_count_from_prompt(cs.prompt)
            self._card_select_target = max(target, 1)
            self._card_select_progress = self._selection_selected_count(cs)
            self._card_select_selected.clear()
            logger.info(
                "Card select session: target=%d (prompt=%s, max_select=%s)",
                self._card_select_target,
                (cs.prompt or "")[:60],
                cs.max_select,
            )

        selected_count = self._selection_selected_count(cs)
        made = self._selection_session_progress(cs)

        # Confirm if API says ready OR we've selected the required number
        if (cs.can_confirm and (selected_count > 0 or made > 0)) or made >= self._card_select_target:
            action = actions.confirm_selection()
            try:
                await self._execute(action, delta_source="confirm")
            except (McpActionError, McpError) as exc:
                # confirm_selection may not work for deck selections (no NPlayerHand confirm button)
                # The game may auto-process after selecting the correct number of cards
                logger.warning("confirm_selection failed (may auto-process): %s", exc)
            logger.info(
                "Confirm selection (made=%d, target=%d, can_confirm=%s)",
                made, self._card_select_target, cs.can_confirm,
            )
            self._reset_card_select_tracking()
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Confirm selection ({made}/{self._card_select_target})",
                source="random",
            )

        if selectable_cards:
            # Only hand-select style screens keep prior picks clickable by index.
            available = (
                [c for c in selectable_cards if c.index not in self._card_select_selected]
                if self._selection_indices_are_stable(gs)
                else list(selectable_cards)
            )
            if not available:
                available = list(selectable_cards)  # Fallback: all exhausted, retry any
            card = random.choice(available)
            action = actions.select_deck_card(card.index)
            await self._execute(action, delta_source=card.name)
            made = self._record_selection_choice(gs, card.index)
            # Memory: record card select as upgrade or remove
            floor = gs.run.floor if gs.run else 0
            prompt_hint = (cs.prompt or "").lower()
            if "remove" in prompt_hint:
                self._hcm_record_deck_change(floor, "remove", card.name, "card_select")
                stm = self._hcm_short_term()
                if stm is not None:
                    stm.record_card_removed(card.name)
            elif "upgrade" in prompt_hint:
                self._hcm_record_deck_change(floor, "upgrade", card.name, "card_select")
            else:
                self._hcm_record_deck_change(floor, "add", card.name, "card_select")
                stm = self._hcm_short_term()
                if stm is not None:
                    stm.record_card_gained(card.name)
            logger.info(
                "Card select: picked %s idx=%d (made=%d/%d)",
                card.name,
                card.index,
                made,
                self._card_select_target,
            )

            # If we just hit the target, confirm immediately in the same step
            if made >= self._card_select_target:
                await asyncio.sleep(0.3)  # Brief delay for game to register
                confirm = actions.confirm_selection()
                try:
                    await self._execute(confirm, delta_source="confirm")
                    logger.info("Auto-confirm after selecting %d cards", made)
                except (McpActionError, McpError) as exc:
                    logger.warning("Auto-confirm failed (may auto-process): %s", exc)
                self._reset_card_select_tracking()
                return Decision(
                    floor=gs.run.floor if gs.run else 0,
                    state_type=gs.state_type,
                    action=action,
                    reasoning=f"Select {card.name} + confirm ({made} cards done)",
                    source="random",
                )

            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Select {card.name} ({made}/{self._card_select_target})",
                source="random",
            )
        if "close_cards_view" in gs.available_actions:
            action = actions.close_cards_view()
            await self._execute(action)
            self._reset_card_select_tracking()
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Cancel selection",
                source="random",
            )
        return None

    async def _handle_relic_select_fallback(self, gs: GameState) -> Decision | None:
        rs = gs.chest
        if not rs:
            return None
        if rs.relic_options:
            relic = random.choice(rs.relic_options)
            action = actions.choose_treasure_relic(relic.index)
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Select relic: {relic.name}",
                source="random",
            )
        if gs.can_proceed:
            action = actions.proceed()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Skip relic",
                source="random",
            )
        return None

    async def _handle_treasure(self, gs: GameState) -> Decision | None:
        tr = gs.chest
        if not tr:
            return None
        # Chest not opened yet — open it first
        if not tr.is_opened and "open_chest" in gs.available_actions:
            action = actions.open_chest()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Open chest",
                source="random",
            )
        if tr.relic_options:
            relic = tr.relic_options[0]
            action = actions.choose_treasure_relic(relic.index)
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning=f"Claim: {relic.name}",
                source="random",
            )
        if gs.can_proceed:
            action = actions.proceed()
            await self._execute(action)
            return Decision(
                floor=gs.run.floor if gs.run else 0,
                state_type=gs.state_type,
                action=action,
                reasoning="Proceed from treasure",
            source="random",
        )
        return None

    # ── Execution ──────────────────────────────────────────────

    async def _recover_timed_out_action(
        self,
        action_name: str,
        action_params: dict,
        pre_version: int,
        pre_screen: str,
        pre_state: GameState | None,
        execute_started: float,
        attempt: int,
        delta_source: str | None,
        delta_target: str | None,
        error: Exception,
    ) -> dict | None:
        """Treat a response timeout as success if the game state already advanced."""
        try:
            await asyncio.sleep(config.ACTION_DELAY)
            fetch_started = time.monotonic()
            raw = await self._client.get_state()
            self._log_perf_duration(
                "execute.timeout_recovery_state_fetch",
                fetch_started,
                action=action_name,
                attempt=attempt + 1,
            )
            new_version, new_screen = self._extract_state_markers(raw)
            changed = (
                (new_version != pre_version and new_version > 0)
                or (new_screen and new_screen != pre_screen)
            )
            if not changed:
                return None

            post_state = None
            try:
                post_state = parse_state(raw)
            except Exception:
                pass
            self._record_combat_action_metrics(pre_state, post_state)
            self._record_combat_delta(
                pre_state, post_state, action_name, delta_source, delta_target,
            )
            logger.warning(
                "Action '%s' response timed out but state advanced "
                "(version %s→%s, screen %s→%s); treating as success",
                action_name, pre_version, new_version, pre_screen, new_screen,
            )
            result = {
                "action": action_name,
                "status": "timeout_recovered",
                "stable": True,
                "state": raw,
            }
            if self._session_logger:
                self._session_logger.log_action_result(
                    action=action_name,
                    params=action_params,
                    status="ok",
                    step=self._current_step,
                    mcp_result=result,
                )
                self._log_perf_duration(
                    "execute.total",
                    execute_started,
                    action=action_name,
                    attempt=attempt + 1,
                    status="timeout_recovered",
                )
            return result
        except Exception as recovery_error:
            logger.debug(
                "Timeout recovery failed after action '%s': %s (original: %s)",
                action_name,
                recovery_error,
                error,
            )
            return None

    async def _execute(
        self,
        action: dict,
        *,
        delta_source: str | None = None,
        delta_target: str | None = None,
    ) -> dict | None:
        """Execute an action with retry logic.

        Logs action results with status: ok / soft_fail / hard_fail.
        """
        action_name = action.get("action", "")
        action_params = {k: v for k, v in action.items() if k != "action"}
        for attempt in range(config.ACTION_RETRY_MAX):
            pre_state: GameState | None = None
            post_raw: dict | None = None
            execute_started = time.monotonic()
            try:
                # Capture pre-action state for change detection
                try:
                    pre_fetch_started = time.monotonic()
                    pre_raw = await self._client.get_state()
                    self._log_perf_duration(
                        "execute.pre_state_fetch",
                        pre_fetch_started,
                        action=action_name,
                        attempt=attempt + 1,
                    )
                    pre_version, pre_screen = self._extract_state_markers(pre_raw)
                    pre_state = parse_state(pre_raw)
                except Exception:
                    pre_version = 0
                    pre_screen = ""

                post_action_started = time.monotonic()
                result = await self._client.post_action(action)
                self._log_perf_duration(
                    "execute.post_action",
                    post_action_started,
                    action=action_name,
                    attempt=attempt + 1,
                    stable=result.get("stable") if isinstance(result, dict) else None,
                )
                settled_raw = None
                # If game is still transitioning, wait for state to stabilize
                if isinstance(result, dict) and not result.get("stable", True):
                    logger.info(
                        "Action '%s' not yet stable, waiting for state to settle...",
                        action_name,
                    )
                    wait_started = time.monotonic()
                    try:
                        await asyncio.sleep(config.ACTION_DELAY)
                        # Poll until state version OR screen/state_type changes (up to 4s)
                        for _poll in range(8):
                            raw = await self._client.get_state()
                            settled_raw = raw
                            new_version, new_screen = self._extract_state_markers(raw)
                            # Settled if version changed or screen changed
                            # (e.g. combat -> card_select).
                            if (
                                (new_version != pre_version and new_version > 0)
                                or (new_screen and new_screen != pre_screen)
                            ):
                                logger.debug(
                                    "State settled: version %s→%s, screen %s→%s",
                                    pre_version, new_version, pre_screen, new_screen,
                                )
                                break
                            await asyncio.sleep(0.5)
                        else:
                            logger.warning(
                                "Action '%s' not stable after 4s, proceeding (may be transitional)",
                                action_name,
                            )
                    except Exception as wait_err:
                        logger.debug("Wait-for-stable failed (non-fatal): %s", wait_err)
                    finally:
                        self._log_perf_duration(
                            "execute.wait_for_stable",
                            wait_started,
                            action=action_name,
                            attempt=attempt + 1,
                            settled=settled_raw is not None,
                        )

                post_state = None
                try:
                    if settled_raw is not None:
                        post_raw = settled_raw
                        if self._session_logger is not None:
                            self._session_logger.log_perf(
                                "execute.post_state_fetch",
                                0.0,
                                step=self._current_step,
                                action=action_name,
                                attempt=attempt + 1,
                                source="settled_poll",
                            )
                    elif (
                        isinstance(result, dict)
                        and result.get("stable", True)
                        and isinstance(result.get("state"), dict)
                    ):
                        post_raw = result["state"]
                        if self._session_logger is not None:
                            self._session_logger.log_perf(
                                "execute.post_state_fetch",
                                0.0,
                                step=self._current_step,
                                action=action_name,
                                attempt=attempt + 1,
                                source="action_result",
                            )
                    else:
                        post_fetch_started = time.monotonic()
                        post_raw = await self._client.get_state()
                        self._log_perf_duration(
                            "execute.post_state_fetch",
                            post_fetch_started,
                            action=action_name,
                            attempt=attempt + 1,
                            source="get_state",
                        )
                    post_state = parse_state(post_raw)
                except Exception:
                    post_state = None

                self._record_combat_action_metrics(pre_state, post_state)
                self._record_combat_delta(
                    pre_state, post_state, action_name, delta_source, delta_target,
                )
                # SUCCESS
                if self._session_logger:
                    self._session_logger.log_action_result(
                        action=action_name, params=action_params,
                        status="ok", step=self._current_step,
                        mcp_result=result if isinstance(result, dict) else None,
                    )
                    self._log_perf_duration(
                        "execute.total",
                        execute_started,
                        action=action_name,
                        attempt=attempt + 1,
                        status="ok",
                    )
                if isinstance(result, dict) and post_raw is not None and "state" not in result:
                    result = {**result, "state": post_raw}
                return result
            except McpActionError as e:
                err_msg = str(e).lower()
                if e.code == "read_timeout":
                    recovered = await self._recover_timed_out_action(
                        action_name,
                        action_params,
                        pre_version,
                        pre_screen,
                        pre_state,
                        execute_started,
                        attempt,
                        delta_source,
                        delta_target,
                        e,
                    )
                    if recovered is not None:
                        return recovered
                # Treat phase-transition errors as soft-success for end_turn/play_card
                if any(phrase in err_msg for phrase in (
                    "not in play phase", "actions are currently disabled",
                    "not in combat",
                )):
                    logger.debug("Action '%s' soft-failed (state transitioned): %s", action_name, e)
                    if self._session_logger:
                        self._session_logger.log_action_result(
                            action=action_name, params=action_params,
                            status="soft_fail", step=self._current_step,
                            error=str(e),
                        )
                    return None
                # Target died between state poll and action execution (race condition)
                # Re-poll and retry with first alive enemy
                if (
                    ("not found" in err_msg or "invalid_target" in err_msg)
                    and "target_index" in action
                ):
                    try:
                        raw = await self._client.get_state()
                        fresh = parse_state(raw)
                        if fresh.enemies:
                            new_target_idx = fresh.enemies[0].index
                            logger.info(
                                "Target race fix: %s → %s", action["target_index"], new_target_idx,
                            )
                            action = {**action, "target_index": new_target_idx}
                            action_params = {k: v for k, v in action.items() if k != "action"}
                            continue  # Retry with new target
                        else:
                            logger.info("All enemies dead, skipping action")
                            if self._session_logger:
                                self._session_logger.log_action_result(
                                    action=action_name, params=action_params,
                                    status="soft_fail", step=self._current_step,
                                    error="all enemies dead",
                                )
                            return None
                    except Exception:
                        pass
                logger.warning(
                    "Action error (attempt %d/%d): %s — action=%s",
                    attempt + 1, config.ACTION_RETRY_MAX, e, action,
                )
                if attempt < config.ACTION_RETRY_MAX - 1:
                    await asyncio.sleep(0.5)
            except McpError as e:
                logger.warning(
                    "MCP error (attempt %d/%d): %s — action=%s",
                    attempt + 1, config.ACTION_RETRY_MAX, e, action,
                )
                if self._session_logger:
                    self._session_logger.log_action_result(
                        action=action_name, params=action_params,
                        status="hard_fail", step=self._current_step,
                        error=str(e),
                    )
                if attempt < config.ACTION_RETRY_MAX - 1:
                    await asyncio.sleep(0.5)
                else:
                    raise
        logger.error("Action failed after %d retries: %s", config.ACTION_RETRY_MAX, action)
        if self._session_logger:
            self._session_logger.log_action_result(
                action=action_name, params=action_params,
                status="hard_fail", step=self._current_step,
                error=f"max retries ({config.ACTION_RETRY_MAX})",
            )
        return None
