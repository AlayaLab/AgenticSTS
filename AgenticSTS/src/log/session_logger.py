"""Structured session logger for agent runs.

Logs decisions, state transitions, and run outcomes
to JSON-lines files for later analysis.

Also pushes events to an optional EventBus for real-time monitoring.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import config
from src.patch.version import get_runtime_version
from src.state.game_state import GameState, resolve_boss_stage, resolve_encounter_label
from src.state.run_state import Decision

logger = logging.getLogger(__name__)


# ── Knowledge enrichment ──────────────────────────────────────
# Postrun analysis (core-engine identification from winning Act 3 boss rounds)
# needs full card/relic/power descriptions baked into each state snapshot —
# not just names. Names are meaningless without effect text when the LLM is
# reasoning about which mechanic scaled a deck. We bake enrichment in at log
# time instead of at postrun time so every downstream consumer (evolution,
# skill discovery, core-engine extractor) sees the same rich context.
def _get_knowledge():
    """Return GameKnowledge singleton or None if unavailable."""
    try:
        from src.knowledge.knowledge import GameKnowledge
        return GameKnowledge.get_instance()
    except Exception:
        return None


def _card_description(name: str, upgraded: bool = False) -> dict:
    """Look up static card metadata + description. Safe on missing data."""
    kb = _get_knowledge()
    if kb is None:
        return {}
    try:
        cd = kb.cards.get(name)
        if cd is None:
            return {}
        out: dict = {}
        if cd.description:
            out["description"] = cd.description
        if cd.type:
            out["type"] = cd.type
        if cd.rarity:
            out["rarity"] = cd.rarity
        if cd.target:
            out["target"] = cd.target
        if upgraded and kb.cards.get_upgrade_preview(name):
            upg = kb.cards.get_upgrade_preview(name)
            if upg:
                out["upgrade_effect"] = upg
        return out
    except Exception:
        return {}


def _relic_description(name: str) -> dict:
    """Look up relic description + metadata. Safe on missing data."""
    kb = _get_knowledge()
    if kb is None:
        return {}
    try:
        r = kb.relics.get(name)
        if r is None:
            return {}
        out: dict = {}
        if getattr(r, "description", None):
            out["description"] = r.description
        if getattr(r, "rarity", None):
            out["rarity"] = r.rarity
        if getattr(r, "pool", None):
            out["pool"] = r.pool
        return out
    except Exception:
        return {}


def _power_description(name: str) -> str:
    """Look up power description. Safe on missing data."""
    try:
        from src.knowledge.power_lookup import get_power_description
        return get_power_description(name) or ""
    except Exception:
        return ""


def _with_power_desc(power_entry: dict) -> dict:
    """Enrich a power log entry with its description.

    Returns a new dict (immutability convention). Idempotent.
    """
    desc = _power_description(power_entry.get("name", ""))
    if not desc:
        return power_entry
    return {**power_entry, "description": desc}


def _with_relic_desc(relic_entry: dict) -> dict:
    """Enrich a relic log entry with its description + metadata.

    Returns a new dict (immutability convention). Idempotent.
    """
    extra = _relic_description(relic_entry.get("name", ""))
    if not extra:
        return relic_entry
    return {**relic_entry, **extra}


def _shop_card_entry(c) -> dict:
    """Serialize a shop card with description, type, rarity enrichment.

    Returns a new dict (immutability convention).
    """
    base: dict = {
        "index": c.index, "name": c.name, "price": c.price,
        "upgraded": c.upgraded,
        "enough_gold": c.enough_gold, "category": c.category,
        "is_stocked": c.is_stocked, "rules_text": c.rules_text,
    }
    extra = _card_description(c.name, upgraded=c.upgraded)
    return {**base, **extra} if extra else base


def _reward_card_entry(c) -> dict:
    """Serialize a card_reward / combat_rewards card option with enrichment.

    Returns a new dict (immutability convention).
    """
    base: dict = {
        "index": c.index, "name": c.name,
        "upgraded": c.upgraded,
        "rules_text": c.rules_text,
    }
    extra = _card_description(c.name, upgraded=c.upgraded)
    return {**base, **extra} if extra else base


class SessionLogger:
    """Writes structured logs to a JSONL file per run.

    Optionally pushes events to an EventBus for real-time WebSocket streaming.
    Thread-safe: LLM worker threads can call log_llm_call() safely.
    """

    def __init__(self, run_id: str, event_bus: object | None = None) -> None:
        self._run_id = run_id
        self._start_time = time.time()
        self._event_bus = event_bus
        self._lock = threading.Lock()
        self._last_state_hash: str | None = None
        self._meta_written = False
        self._llm_call_seq: int = -1

        log_dir = Path(config.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        self._log_path = log_dir / f"run_{run_id}.jsonl"
        self._file = open(self._log_path, "a", encoding="utf-8")

        self._write_event("run_start", {"run_id": run_id})

    # ── State snapshot ─────────────────────────────────────────

    def log_state(
        self,
        gs: GameState,
        step: int,
        combat_type_override: str | None = None,
    ) -> None:
        """Log a full game state snapshot for post-run replay.

        Deduplicates: only emits when payload hash differs from last snapshot.
        """
        floor = gs.run.floor if gs.run else 0
        act = None
        if floor > 0:
            if floor <= 17:
                act = 1
            elif floor <= 34:
                act = 2
            else:
                act = 3

        summary = (
            gs.summary(combat_type_override=combat_type_override)
            if combat_type_override is not None
            else gs.summary()
        )

        data: dict = {
            "step": step,
            "state_type": gs.state_type,
            "summary": summary,
        }
        if gs.run:
            data["floor"] = gs.run.floor
        data["ascension"] = gs.ascension
        data["hp"] = gs.player_hp
        data["hp_max"] = gs.player_max_hp

        native_combat_type = getattr(gs, "combat_type", "")
        if not isinstance(native_combat_type, str):
            native_combat_type = ""
        effective_combat_type = combat_type_override or native_combat_type
        if not effective_combat_type and gs.state_type in ("monster", "elite", "boss"):
            effective_combat_type = gs.state_type
        if effective_combat_type:
            data["combat_type"] = effective_combat_type
            boss_stage = getattr(gs, "boss_stage", None)
            if not isinstance(boss_stage, str):
                boss_stage = resolve_boss_stage(
                    state_type=gs.state_type,
                    floor=floor,
                    act=act,
                    in_combat=gs.is_combat,
                    combat_type_override=effective_combat_type,
                )
            data["encounter_label"] = boss_stage or resolve_encounter_label(
                state_type=gs.state_type,
                floor=floor,
                act=act,
                in_combat=gs.is_combat,
                combat_type_override=effective_combat_type,
            )
            if boss_stage:
                data["boss_stage"] = boss_stage
                data["is_final_boss"] = boss_stage == "final_boss"

        if gs.is_combat and gs.combat:
            self._build_combat_state(gs, data)
        elif gs.run:
            data["player"] = {
                "hp": gs.player_hp,
                "max_hp": gs.player_max_hp,
                "gold": gs.gold,
                "potion_slots": gs.potion_slots,
            }

        # Deck (available in all game states when run is active)
        # Enriched with static card knowledge so postrun analysis doesn't
        # need a separate lookup round-trip.
        if gs.deck:
            data["deck_size"] = len(gs.deck)
            deck_entries: list[dict] = []
            for c in gs.deck:
                entry: dict = {
                    "name": c.name,
                    "upgraded": c.upgraded,
                    "energy_cost": c.energy_cost,
                }
                entry.update(_card_description(c.name, upgraded=c.upgraded))
                deck_entries.append(entry)
            data["deck"] = deck_entries

        # Non-combat state details
        self._build_state_details(gs, data)

        # Dedup: skip if game state unchanged from last snapshot.
        # Exclude "step" from hash — it changes every poll but doesn't
        # reflect actual game state changes.
        hash_payload = {k: v for k, v in data.items() if k != "step"}
        state_hash = hashlib.md5(
            json.dumps(hash_payload, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        if state_hash == self._last_state_hash:
            return
        self._last_state_hash = state_hash

        self._write_event("state", data)

    def _build_combat_state(self, gs: GameState, data: dict) -> None:
        """Build combat state payload with full card values and intent damage."""
        p = gs.combat.player
        data["combat"] = {
            "round": gs.combat_round,
            "is_play_phase": gs.is_play_phase,
            "player": {
                "hp": p.current_hp,
                "max_hp": p.max_hp,
                "block": p.block,
                "energy": p.energy,
                "max_energy": gs.run.max_energy if gs.run else 0,
                "stars": p.stars,
                "gold": gs.gold,
                "hand": [self._serialize_hand_card(c) for c in gs.hand],
                "powers": [
                    _with_power_desc({"name": pw.name, "amount": pw.amount})
                    for pw in p.powers
                ],
                "potions": [self._serialize_potion(pot) for pot in gs.potions],
                "relics": [
                    _with_relic_desc({"name": r.name, "stack": r.stack})
                    for r in gs.relics
                ],
            },
            "enemies": [
                {
                    "enemy_id": e.enemy_id, "name": e.name,
                    "hp": e.current_hp, "max_hp": e.max_hp, "block": e.block,
                    "intents": [
                        {
                            "type": i.intent_type, "label": i.label,
                            "damage": i.damage, "hits": i.hits,
                            "total_damage": i.total_damage,
                        }
                        for i in e.intents
                    ],
                    "powers": [
                        _with_power_desc({"name": pw.name, "amount": pw.amount})
                        for pw in e.powers
                    ],
                }
                for e in gs.enemies
            ],
        }
        # Pile sizes from agent_view (draw/discard/exhaust are lists)
        av = gs.agent_view
        if av and av.combat:
            avc = av.combat
            data["combat"]["draw_pile_size"] = len(avc.draw)
            data["combat"]["discard_pile_size"] = len(avc.discard)
            data["combat"]["exhaust_pile_size"] = len(avc.exhaust)

    @staticmethod
    def _serialize_hand_card(c) -> dict:
        """Serialize a hand card with full value fields for replay.

        Fields beyond the base set are needed by the postrun combat trace
        renderer so Turn 1 / Turn 2 LLM calls see upgrade / star-cost /
        enchantment state that plain counters cannot express.
        """
        card: dict = {
            "index": c.index, "name": c.name,
            "energy_cost": c.energy_cost, "playable": c.playable,
            "target_type": c.target_type,
            "rules_text": c.rules_text,
            "damage": c.damage, "block": c.block,
            "hits": c.hits, "total_damage": c.total_damage,
            "upgraded": bool(getattr(c, "upgraded", False)),
            "star_cost": getattr(c, "star_cost", None),
            "card_type": getattr(c, "card_type", "") or "",
            # NOTE: the upstream C# mod's RawCombatHandCardPayload does not
            # currently expose enchantment_name, so this field is always None
            # for live hand cards. Extend the C# payload to populate it.
            "enchantment_name": getattr(c, "enchantment_name", None),
        }
        if c.target_previews:
            card["target_previews"] = [
                {
                    "target_index": tp.target_index,
                    "damage": tp.damage, "hits": tp.hits,
                    "total_damage": tp.total_damage,
                }
                for tp in c.target_previews
            ]
        return card

    @staticmethod
    def _serialize_potion(pot) -> dict:
        """Serialize a potion with description for replay."""
        return {
            "index": pot.index, "name": pot.name,
            "occupied": pot.occupied,
            "can_use": pot.can_use, "target_type": pot.target_type,
            "description": pot.description,
        }

    def _build_state_details(self, gs: GameState, data: dict) -> None:
        """Build non-combat state-specific details."""
        st = gs.state_type

        if st == "rest_site" and gs.rest:
            data["rest_site"] = {
                "options": [
                    {
                        "index": o.index, "title": o.title,
                        "option_id": o.option_id, "is_enabled": o.is_enabled,
                    }
                    for o in gs.rest.options
                ],
            }

        elif st == "event" and gs.event:
            ev = gs.event
            # B1 fix: use "event_details" to avoid collision with top-level "event" key
            data["event_details"] = {
                "event_id": ev.event_id,
                "event_name": ev.title,
                "description": ev.description,
                "is_finished": ev.is_finished,
                "options": [
                    {
                        "index": o.index, "title": o.title,
                        "description": o.description,
                        "is_locked": o.is_locked, "is_proceed": o.is_proceed,
                    }
                    for o in ev.options
                ],
            }

        elif gs.is_map and gs.map:
            data["map_details"] = {
                "next_options": [
                    {"index": o.index, "node_type": o.node_type}
                    for o in gs.next_map_options
                ],
            }

        elif st == "combat_rewards" and gs.reward:
            data["rewards"] = {
                "can_proceed": gs.reward.can_proceed,
                "rewards": [
                    {
                        "index": i.index, "reward_type": i.reward_type,
                        "description": i.description,
                    }
                    for i in gs.reward.rewards
                ],
            }
            # Card choice within rewards
            if gs.reward.pending_card_choice and gs.reward.card_options:
                data["card_options"] = [
                    _reward_card_entry(c)
                    for c in gs.reward.card_options
                ]
                if gs.reward.alternatives:
                    data["alternatives"] = [
                        {"index": a.index, "label": a.label}
                        for a in gs.reward.alternatives
                    ]

        elif st == "card_reward" and gs.reward:
            data["card_reward_details"] = {
                "card_options": [
                    _reward_card_entry(c)
                    for c in gs.reward.card_options
                ],
                "alternatives": [
                    {"index": a.index, "label": a.label}
                    for a in gs.reward.alternatives
                ],
            }

        elif st == "shop" and gs.shop:
            shop = gs.shop
            data["shop_details"] = {
                "is_open": shop.is_open,
                "cards": [
                    _shop_card_entry(c)
                    for c in shop.cards
                ],
                "relics": [
                    _with_relic_desc({
                        "index": r.index, "name": r.name, "price": r.price,
                        "enough_gold": r.enough_gold, "is_stocked": r.is_stocked,
                    })
                    for r in shop.relics
                ],
                "potions": [
                    {
                        "index": p.index, "name": p.name, "price": p.price,
                        "enough_gold": p.enough_gold, "is_stocked": p.is_stocked,
                    }
                    for p in shop.potions
                ],
                "card_removal": {
                    "price": shop.card_removal.price,
                    "available": shop.card_removal.available,
                    "used": shop.card_removal.used,
                    "enough_gold": shop.card_removal.enough_gold,
                } if shop.card_removal else None,
            }

        elif st in ("treasure", "chest") and gs.chest:
            data["treasure_details"] = {
                "is_opened": gs.chest.is_opened,
                "has_relic_been_claimed": gs.chest.has_relic_been_claimed,
                "relic_options": [
                    _with_relic_desc({
                        "index": r.index, "name": r.name,
                        "rarity": r.rarity,
                    })
                    for r in gs.chest.relic_options
                ],
            }

        elif st in ("card_select", "hand_select") and gs.selection:
            sel = gs.selection
            data["selection_details"] = {
                "kind": sel.kind,
                "prompt": sel.prompt,
                "min_select": sel.min_select,
                "max_select": sel.max_select,
                "cards": [
                    {
                        "index": c.index, "name": c.name,
                        "rules_text": c.rules_text,
                    }
                    for c in sel.cards
                ],
            }

        elif st == "cards_view" and gs.cards_view:
            cards_view = gs.cards_view
            data["cards_view_details"] = {
                "title": cards_view.title,
                "available_actions": list(gs.available_actions),
                "cards": [
                    {
                        "index": c.index, "name": c.name,
                        "rules_text": c.rules_text,
                    }
                    for c in cards_view.cards
                ],
            }

    def force_state_emit(self) -> None:
        """Reset dedup hash so next log_state() always emits."""
        self._last_state_hash = None

    # ── Decision ───────────────────────────────────────────────

    def log_decision(self, decision: Decision, step: int) -> None:
        """Log an agent decision."""
        event: dict = {
            "step": step,
            "floor": decision.floor,
            "state_type": decision.state_type,
            "action": decision.action,
            "reasoning": decision.reasoning,
            "source": decision.source,
        }
        if decision.reasoning_zh:
            event["reasoning_zh"] = decision.reasoning_zh
        if decision.strategic_note:
            event["strategic_note"] = decision.strategic_note
        # Inline-markup pass: wrap enemy names and keywords with [e]…[/e] / [k]…[/k]
        # tags so the stream-ui can color them at render time. Applied to a new
        # `text_marked` field — the canonical `reasoning` / `reasoning_zh` stay
        # clean for memory + skills + multi-turn LLM context.
        # When DISPLAY_LANGUAGE=zh, also synthesize a Chinese version for
        # heuristic decisions that don't carry reasoning_zh from the model.
        try:
            from src.knowledge.locale_translator import get_translator
            translator = get_translator()
        except Exception:
            translator = None

        if config.DISPLAY_LANGUAGE == "zh":
            zh = decision.reasoning_zh
            if not zh and decision.reasoning and translator is not None:
                try:
                    translated = translator.translate_reasoning(decision.reasoning)
                    if translated and translated != decision.reasoning:
                        zh = translated
                        event["reasoning_zh"] = translated
                except Exception:
                    pass
            if zh:
                event["text"] = zh

        if translator is not None:
            try:
                src_text = (
                    event.get("text")
                    or event.get("reasoning_zh")
                    or decision.reasoning
                )
                if src_text:
                    marked = translator.apply_inline_markup(src_text)
                    if marked and marked != src_text:
                        event["text_marked"] = marked
            except Exception:
                pass

        self._write_event("decision", event)

    # ── Action result ──────────────────────────────────────────

    def log_action_result(
        self,
        action: str,
        params: dict,
        status: str,
        step: int,
        error: str = "",
        mcp_result: dict | None = None,
    ) -> None:
        """Log the result of an MCP action execution.

        Args:
            action: Action name (e.g. "play_card", "end_turn").
            params: Action parameters (excluding "action" key).
            status: One of "ok", "soft_fail", "hard_fail".
            step: Current agent step number.
            error: Error message for failed actions.
            mcp_result: Raw response data from post_action() on success.
        """
        data: dict = {
            "step": step,
            "action": action,
            "params": params,
            "status": status,
        }
        if error:
            data["error"] = error
        if mcp_result is not None:
            # Capture key MCP response fields for replay
            data["mcp_status"] = mcp_result.get("status", "")
            data["mcp_stable"] = mcp_result.get("stable", True)
            if mcp_result.get("message"):
                data["mcp_message"] = mcp_result["message"]
        self._write_event("action_result", data)

    # ── LLM call ───────────────────────────────────────────────

    def log_llm_request_start(
        self,
        *,
        call_type: str,
        provider: str,
        model: str,
        tier: str,
        state_type: str,
        round_idx: int,
        think_enabled: bool,
        tool_count: int,
        message_count: int,
    ) -> None:
        """Log the start of an LLM request for real-time monitoring."""
        self._write_event("llm_request_start", {
            "call_type": call_type,
            "provider": provider,
            "model": model,
            "tier": tier,
            "state_type": state_type,
            "round_idx": round_idx,
            "think_enabled": think_enabled,
            "tool_count": tool_count,
            "message_count": message_count,
        })

    def log_llm_first_chunk(
        self,
        *,
        call_type: str,
        provider: str,
        model: str,
        tier: str,
        state_type: str,
        round_idx: int,
        latency_ms: float,
        chunk_meta: dict | None = None,
    ) -> None:
        """Log when the first streamed chunk or response bytes are observed."""
        self._write_event("llm_first_chunk", {
            "call_type": call_type,
            "provider": provider,
            "model": model,
            "tier": tier,
            "state_type": state_type,
            "round_idx": round_idx,
            "latency_ms": round(latency_ms, 1),
            "chunk_meta": chunk_meta or {},
        })

    def log_llm_request_end(
        self,
        *,
        call_type: str,
        provider: str,
        model: str,
        tier: str,
        state_type: str,
        round_idx: int,
        latency_ms: float,
        status: str,
        stop_reason: str = "",
        tokens: int = 0,
        error: str = "",
    ) -> None:
        """Log the end of an LLM request for real-time monitoring."""
        data = {
            "call_type": call_type,
            "provider": provider,
            "model": model,
            "tier": tier,
            "state_type": state_type,
            "round_idx": round_idx,
            "latency_ms": round(latency_ms, 1),
            "status": status,
            "stop_reason": stop_reason,
            "tokens": tokens,
        }
        if error:
            data["error"] = error
        self._write_event("llm_request_end", data)

    def log_llm_call(
        self,
        prompt: str,
        response: str,
        latency_ms: float,
        tokens: int,
        call_type: str = "decision",
        model: str = "",
        tier: str = "",
        thinking_text: str = "",
        cache_read_tokens: int = 0,
        cache_creation_input_tokens: int = 0,
        prepared_prefix_hash: str = "",
        stop_reason: str = "",
        attempt: int = 1,
        system_prompt: str = "",
        think_budget: int = 0,
        tools: list[dict] | None = None,
        messages: list[dict] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Log a full LLM API call with prompt and response.

        Thread-safe: can be called from LLM worker threads.

        Args:
            tools: Tool definitions sent to the API (list of name/description/input_schema dicts).
            messages: Full message history sent to the API (multi-turn conversation).
        """
        # Build tool summary: name + description + full input schema
        tools_summary: list[dict] | None = None
        if tools:
            tools_summary = [
                {
                    "name": t.get("name", ""),
                    "description": t.get("description", ""),
                    "input_schema": t.get("input_schema"),
                }
                for t in tools
            ]

        # Serialize messages for logging — extract text from structured content
        messages_log: list[dict] | None = None
        if messages:
            messages_log = []
            for msg in messages:
                role = msg.get("role", "")
                content = msg.get("content", "")
                if isinstance(content, str):
                    messages_log.append({"role": role, "content": content})
                elif isinstance(content, list):
                    # Structured content blocks (tool_result, text blocks, SDK objects)
                    parts = []
                    for block in content:
                        if isinstance(block, dict):
                            # tool_result blocks
                            if block.get("type") == "tool_result":
                                tool_id = block.get("tool_use_id", "")
                                c = block.get("content", "")
                                parts.append(f"[tool_result:{tool_id[:8]}] {c}")
                            elif block.get("type") == "text":
                                parts.append(block.get("text", ""))
                            else:
                                parts.append(str(block))
                        else:
                            # SDK objects (assistant content blocks)
                            btype = getattr(block, "type", "")
                            if btype == "text":
                                parts.append(getattr(block, "text", ""))
                            elif btype == "tool_use":
                                name = getattr(block, "name", "")
                                inp = getattr(block, "input", {})
                                tool_json = json.dumps(inp, ensure_ascii=False)[:500]
                                parts.append(f"[tool_use:{name}] {tool_json}")
                            elif btype == "thinking":
                                parts.append("[thinking block]")
                            else:
                                parts.append(str(block)[:200])
                    messages_log.append({"role": role, "content": "\n".join(parts)})
                else:
                    messages_log.append({"role": role, "content": str(content)[:500]})

        self._write_event("llm_call", {
            "call_type": call_type,
            "model": model,
            "tier": tier,
            "think_budget": think_budget,
            "system_prompt": system_prompt,
            "prompt": prompt,
            "response": response,
            "thinking_text": thinking_text,
            "latency_ms": round(latency_ms, 1),
            "tokens": tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "prepared_prefix_hash": prepared_prefix_hash,
            "stop_reason": stop_reason,
            "attempt": attempt,
            "tools": tools_summary,
            "messages": messages_log,
        })

    # ── Transition ─────────────────────────────────────────────

    def log_transition(
        self,
        transition: str,
        gs: GameState,
        step: int = 0,
        combat_type_override: str | None = None,
    ) -> None:
        """Log a phase transition."""
        floor = gs.run.floor if gs.run else 0
        act = None
        if floor > 0:
            if floor <= 17:
                act = 1
            elif floor <= 34:
                act = 2
            else:
                act = 3

        summary = (
            gs.summary(combat_type_override=combat_type_override)
            if combat_type_override is not None
            else gs.summary()
        )

        data: dict = {
            "step": step,
            "type": transition,
            "state_type": gs.state_type,
            "summary": summary,
        }
        # When DISPLAY_LANGUAGE=zh, build Chinese-translated fields for stream-ui
        # display. Entity names get replaced via the static eng->zhs lookup;
        # structural labels (HP, E, Hand, vs, F<n>, Act <n> Boss) stay English.
        # type_zh / state_type_zh come from static maps so the UI can render
        # without knowing any agent-side vocabulary.
        if config.DISPLAY_LANGUAGE == "zh":
            try:
                from src.knowledge.locale_translator import get_translator
                tr = get_translator()
                t_zh = tr.translate_transition_type(transition)
                if t_zh:
                    data["type_zh"] = t_zh
                st_zh = tr.translate_state_type(gs.state_type)
                if st_zh:
                    data["state_type_zh"] = st_zh
                if summary:
                    summary_zh = tr.translate_summary(summary)
                    if summary_zh and summary_zh != summary:
                        data["summary_zh"] = summary_zh
                        data["text"] = summary_zh
            except Exception:
                pass
        if gs.run:
            data["floor"] = gs.run.floor
        data["hp"] = gs.player_hp
        data["hp_max"] = gs.player_max_hp

        native_combat_type = getattr(gs, "combat_type", "")
        if not isinstance(native_combat_type, str):
            native_combat_type = ""
        effective_combat_type = combat_type_override or native_combat_type
        if not effective_combat_type and gs.state_type in ("monster", "elite", "boss"):
            effective_combat_type = gs.state_type
        if effective_combat_type:
            data["combat_type"] = effective_combat_type
            boss_stage = getattr(gs, "boss_stage", None)
            if not isinstance(boss_stage, str):
                boss_stage = resolve_boss_stage(
                    state_type=gs.state_type,
                    floor=floor,
                    act=act,
                    in_combat=gs.is_combat,
                    combat_type_override=effective_combat_type,
                )
            data["encounter_label"] = boss_stage or resolve_encounter_label(
                state_type=gs.state_type,
                floor=floor,
                act=act,
                in_combat=gs.is_combat,
                combat_type_override=effective_combat_type,
            )
            if boss_stage:
                data["boss_stage"] = boss_stage
                data["is_final_boss"] = boss_stage == "final_boss"

        self._write_event("transition", data)

    # ── Combat summary ─────────────────────────────────────────

    def log_combat_summary(self, tracker, step: int) -> None:
        """Log combat summary from a completed CombatTracker.

        Args:
            tracker: A CombatTracker from ShortTermMemory.completed_combats.
                     Must have _won and _hp_after attrs set by end_combat().
            step: Current agent step number.
        """
        rounds_data = []
        for r in tracker.rounds:
            rounds_data.append({
                "round": r.round_num,
                "cards_played": r.cards_played,
                "potions_used": r.potions_used,
                "hp_start": r.hp_start, "hp_end": r.hp_end,
                "block_gained": r.block_gained,
                "damage_dealt": r.damage_dealt,
                "damage_taken": r.damage_taken,
                "energy_used": r.energy_used,
                "energy_available": r.energy_available,
            })
        terminal_reason = getattr(tracker, "_terminal_reason", None)
        if not isinstance(terminal_reason, str) or not terminal_reason:
            terminal_reason = getattr(tracker, "terminal_reason", None)
        if not isinstance(terminal_reason, str) or not terminal_reason:
            terminal_reason = "win" if getattr(tracker, "_won", False) else "loss"
        payload: dict = {
            "step": step,
            "enemy_key": tracker.enemy_key,
            "combat_type": tracker.combat_type,
            "won": getattr(tracker, "_won", False),
            "terminal_reason": terminal_reason,
            "floor": tracker.floor,
            "total_rounds": len(tracker.rounds),
            "total_cards_played": sum(len(r.cards_played) for r in tracker.rounds),
            "total_damage_dealt": sum(r.damage_dealt for r in tracker.rounds),
            "total_damage_taken": sum(r.damage_taken for r in tracker.rounds),
            "hp_before": tracker.hp_before,
            "hp_after": getattr(tracker, "_hp_after", 0),
            "rounds": rounds_data,
        }
        strat_notes = getattr(tracker, "strategic_notes", None)
        if strat_notes:
            payload["strategic_notes"] = [
                {"round": int(rn), "note": str(note)} for rn, note in strat_notes if note
            ]
        self._write_event("combat_summary", payload)

    # ── Error / run end ────────────────────────────────────────

    def log_warning(
        self,
        source: str,
        message: str,
        *,
        step: int | None = None,
        **details: object,
    ) -> None:
        """Log a non-fatal runtime warning."""
        payload: dict[str, object] = {
            "source": source,
            "message": message,
        }
        if step is not None:
            payload["step"] = step
        for key, value in details.items():
            if value is not None:
                payload[key] = value
        self._write_event("warning", payload)

    def log_error(self, error: str, step: int) -> None:
        """Log an error."""
        self._write_event("error", {"step": step, "error": error})

    def log_run_end(
        self,
        victory: bool,
        floor: int,
        fitness: float,
        *,
        ascension: int | None = None,
        completion_reason: str | None = None,
        end_reason: str | None = None,
    ) -> None:
        """Log run completion."""
        payload = {
            "victory": victory,
            "floor": floor,
            "fitness": round(fitness, 1),
            "duration_s": round(time.time() - self._start_time, 1),
        }
        if ascension is not None:
            payload["ascension"] = ascension
        if completion_reason:
            payload["completion_reason"] = completion_reason
        if end_reason:
            payload["end_reason"] = end_reason
        self._write_event("run_end", payload)

    def log_post_run_start(
        self,
        *,
        completion_reason: str | None = None,
        end_reason: str | None = None,
    ) -> None:
        """Log the start of post-run processing."""
        payload: dict[str, object] = {}
        if completion_reason:
            payload["completion_reason"] = completion_reason
        if end_reason:
            payload["end_reason"] = end_reason
        self._write_event("post_run_start", payload)

    def log_post_run_stage(self, stage: str, status: str, **details: object) -> None:
        """Log a post-run stage transition with minimal structured details."""
        payload: dict[str, object] = {
            "stage": stage,
            "status": status,
        }
        for key, value in details.items():
            if value is not None:
                payload[key] = value
        self._write_event("post_run_stage", payload)

    def log_post_run_end(self) -> None:
        """Log the end of post-run processing."""
        self._write_event("post_run_end", {})

    def log_postrun_artifact(
        self,
        *,
        stage: str,
        kind: str,
        action: str = "write",
        target: str = "",
        summary: str = "",
        before: object = None,
        after: object = None,
        source: str = "",
        details: dict | None = None,
    ) -> None:
        """Log a persisted postrun artifact (skill / guide / memory / rule / tool).

        ``stage`` is the postrun stage that produced it (``memory``, ``skills``,
        ``evolution``, ``distill``, ``guides``).  ``kind`` describes the artifact
        type (``skill``, ``combat_guide``, ``route_guide``, ``card_memory``,
        ``rule``, ``dynamic_tool`` …).  ``before`` / ``after`` can be full dicts,
        strings, or None — the monitor renders whatever is present.
        """
        payload: dict[str, object] = {
            "stage": stage,
            "kind": kind,
            "action": action,
            "target": target,
            "summary": summary,
            "source": source,
        }
        if before is not None:
            payload["before"] = before
        if after is not None:
            payload["after"] = after
        if details:
            payload["details"] = details
        self._write_event("postrun_artifact", payload)

    def log_evolution_round(
        self,
        round_idx: int,
        model: str,
        provider: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        thinking_tokens: int = 0,
        tool_calls: int = 0,
        tool_names: list[str] | None = None,
        stop_reason: str = "",
        latency_ms: int = 0,
        error: str | None = None,
        phase: str = "",
        system_prompt: str = "",
        messages: list[dict] | None = None,
        response_text: str = "",
        thinking_text: str = "",
        tool_uses: list[dict] | None = None,
        tool_results: list[dict] | None = None,
    ) -> None:
        """Log a single evolution LLM round with full telemetry.

        ``messages`` / ``response_text`` / ``tool_uses`` / ``tool_results`` are
        included so the frontend monitor can show the full evolution trace.
        """
        payload: dict[str, object] = {
            "round": round_idx,
            "model": model,
            "provider": provider,
            "phase": phase,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "thinking_tokens": thinking_tokens,
            "tool_calls": tool_calls,
            "stop_reason": stop_reason,
            "latency_ms": latency_ms,
            "system_prompt": system_prompt,
            "response_text": response_text,
            "thinking_text": thinking_text,
        }
        if messages is not None:
            payload["messages"] = messages
        if tool_uses is not None:
            payload["tool_uses"] = tool_uses
        if tool_results is not None:
            payload["tool_results"] = tool_results
        if tool_names:
            payload["tool_names"] = tool_names
        if error:
            payload["error"] = error
        self._write_event("evolution_round", payload)

    def log_evolution_summary(
        self,
        total_rounds: int,
        total_input_tokens: int = 0,
        total_output_tokens: int = 0,
        round_input_tokens: list[int] | None = None,
        round_output_tokens: list[int] | None = None,
        actions_taken: int = 0,
        action_types: list[str] | None = None,
        model: str = "",
        fallbacks_used: int = 0,
        duration_ms: int = 0,
        target_input_tokens: int = 0,
        target_enforced: bool = False,
        target_reached: bool = False,
        min_rounds: int = 0,
        max_rounds: int = 0,
        read_only_rounds: int = 0,
    ) -> None:
        """Log evolution session summary."""
        payload: dict[str, object] = {
            "total_rounds": total_rounds,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "actions_taken": actions_taken,
            "model": model,
            "fallbacks_used": fallbacks_used,
            "duration_ms": duration_ms,
            "target_input_tokens": target_input_tokens,
            "target_enforced": target_enforced,
            "target_reached": target_reached,
            "min_rounds": min_rounds,
            "max_rounds": max_rounds,
            "read_only_rounds": read_only_rounds,
        }
        if round_input_tokens:
            payload["round_input_tokens"] = round_input_tokens
        if round_output_tokens:
            payload["round_output_tokens"] = round_output_tokens
        if action_types:
            payload["action_types"] = action_types
        self._write_event("evolution_summary", payload)

    def log_postrun_llm_call(
        self,
        call_type: str,
        model: str = "",
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
        error: str | None = None,
        system_prompt: str = "",
        prompt: str = "",
        response: str = "",
        thinking_text: str = "",
        provider: str = "",
        effort: str = "",
    ) -> None:
        """Log a post-run LLM call (consolidation, discovery, distillation, etc.).

        Full prompt/response/thinking are included so the frontend monitor can
        replay the postrun reasoning just like gameplay ``llm_call`` events.
        """
        payload: dict[str, object] = {
            "call_type": call_type,
            "model": model,
            "provider": provider,
            "effort": effort,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "system_prompt": system_prompt,
            "prompt": prompt,
            "response": response,
            "thinking_text": thinking_text,
        }
        if error:
            payload["error"] = error
        self._write_event("postrun_llm_call", payload)

    def log_router_event(
        self,
        event: str,
        *,
        call_class: str = "",
        provider: str = "",
        model: str = "",
        reason: str = "",
        error: str = "",
        **extra: object,
    ) -> None:
        """Log a health-aware router event (model switch, circuit open, probe, etc.)."""
        payload: dict[str, object] = {
            "router_event": event,
        }
        if call_class:
            payload["call_class"] = call_class
        if provider:
            payload["provider"] = provider
        if model:
            payload["model"] = model
        if reason:
            payload["reason"] = reason
        if error:
            payload["error"] = error
        for key, value in extra.items():
            if value is not None:
                payload[key] = value
        self._write_event("router", payload)

    def log_perf(
        self,
        stage: str,
        duration_ms: float,
        *,
        step: int | None = None,
        **details: object,
    ) -> None:
        """Log a measured runtime stage duration."""
        payload: dict[str, object] = {
            "stage": stage,
            "duration_ms": round(duration_ms, 1),
        }
        if step is not None:
            payload["step"] = step
        for key, value in details.items():
            if value is not None:
                payload[key] = value
        self._write_event("perf", payload)

    # ── Lifecycle ──────────────────────────────────────────────

    def close(self) -> None:
        """Flush and close the log file."""
        if self._file and not self._file.closed:
            self._file.flush()
            self._file.close()

    def __enter__(self) -> SessionLogger:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Internal ───────────────────────────────────────────────

    def _ensure_meta(self) -> None:
        """Write _meta header on first write if file is fresh (empty).

        Append-mode files: only inject _meta if the file is empty (fresh).
        Subsequent appends (multiple run_id loggers to same file) skip meta injection.
        """
        if self._meta_written:
            return
        self._meta_written = True

        # Only write meta if file is a fresh (empty) file
        if self._log_path.exists() and self._log_path.stat().st_size > 0:
            return  # existing log, don't inject

        rv = get_runtime_version()
        meta = {
            "_meta": {
                "game_version": rv.game_version,
                "mod_version": rv.mod_version,
                "data_schema_version": rv.data_schema_version,
            }
        }
        try:
            line = json.dumps(meta, ensure_ascii=False)
            self._file.write(line + "\n")
            self._file.flush()
        except (OSError, ValueError) as e:
            logger.warning("Failed to write _meta header: %s", e)

    def _write_event(self, event_type: str, data: dict) -> None:
        with self._lock:
            try:
                # Ensure _meta header is written first on fresh logs
                self._ensure_meta()

                record = {
                    "ts": round(time.time(), 3),
                    "dt": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                    "event": event_type,
                    "run_id": self._run_id,
                    **data,
                }
                line = json.dumps(record, ensure_ascii=False)
                self._file.write(line + "\n")
                self._file.flush()

                # Increment llm_call_seq counter for llm_call events
                if event_type == "llm_call":
                    self._llm_call_seq += 1
            except (OSError, ValueError) as e:
                logger.warning("Failed to write log event '%s': %s", event_type, e)

        # Push to EventBus for real-time monitoring (outside lock)
        # Skip perf events — high volume, only useful in JSONL for offline analysis
        if self._event_bus is not None and event_type != "perf":
            try:
                step = data.get("step")
                self._event_bus.emit(
                    event_type, data, step=step, run_id=self._run_id,
                )
            except Exception:
                pass  # Monitor never crashes agent

    @property
    def log_path(self) -> Path:
        return self._log_path

    def current_llm_call_seq(self) -> int:
        """Zero-based index of the most recent llm_call event written.

        Returns -1 if no llm_call event has been written yet.

        Used by CombatTracker.record_round_context to pin the round to a
        specific log entry so prewrite A/B can later fetch the raw prompt
        (see docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md §2.2).
        """
        return self._llm_call_seq
