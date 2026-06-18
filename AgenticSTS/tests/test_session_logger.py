"""Unit tests for SessionLogger.

Verifies JSONL output format, field correctness, event type safety,
deduplication, and all new log methods (action_result, combat_summary).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
from src.log.session_logger import SessionLogger

TEST_LOG_DIR = Path("tests") / "_tmp_session_logger"
TEST_LOG_DIR.mkdir(parents=True, exist_ok=True)


def _make_logger(run_id: str) -> SessionLogger:
    log_path = TEST_LOG_DIR / f"run_{run_id}.jsonl"
    if log_path.exists():
        log_path.unlink()
    with patch.object(config, "LOG_DIR", str(TEST_LOG_DIR)):
        return SessionLogger(run_id)


def _read_events(logger: SessionLogger) -> list[dict]:
    """Flush and read all JSONL events from the log file.

    Skips the _meta header line if present (first line of fresh logs).
    """
    logger._file.flush()
    events = []
    with open(logger.log_path, "r", encoding="utf-8") as f:
        for line in f:
            event = json.loads(line)
            # Skip _meta header on fresh logs
            if "_meta" in event and "event" not in event:
                continue
            events.append(event)
    return events


# ── Basic infrastructure ───────────────────────────────────────


def test_write_event_produces_valid_jsonl():
    sl = _make_logger("test_basic")
    events = _read_events(sl)
    assert len(events) == 1  # run_start
    ev = events[0]
    assert ev["event"] == "run_start"
    assert isinstance(ev["event"], str)
    assert ev["run_id"] == "test_basic"
    assert "ts" in ev
    assert "dt" in ev
    # dt should be ISO 8601 with UTC offset
    assert "+" in ev["dt"] or "Z" in ev["dt"]
    sl.close()


def test_log_warning_writes_structured_warning_event():
    sl = _make_logger("test_warning")

    sl.log_warning(
        "V2Engine",
        "decision validation failed",
        warning_type="decision_validation_failed",
        errors=["Missing required field: selected_indices"],
        decision_tool="hand_select_action",
    )

    events = _read_events(sl)
    warning = events[-1]
    assert warning["event"] == "warning"
    assert warning["source"] == "V2Engine"
    assert warning["message"] == "decision validation failed"
    assert warning["warning_type"] == "decision_validation_failed"
    assert warning["errors"] == ["Missing required field: selected_indices"]
    assert warning["decision_tool"] == "hand_select_action"
    sl.close()


def test_dt_timestamp_is_utc_iso():
    sl = _make_logger("test_dt")
    events = _read_events(sl)
    dt = events[0]["dt"]
    # Should be parseable ISO 8601
    from datetime import datetime

    parsed = datetime.fromisoformat(dt)
    assert parsed.tzinfo is not None  # Must have timezone
    sl.close()


# ── State logging: event field collision (B1) ──────────────────


def _make_event_gs():
    """Create a mock GameState for state_type='event'."""
    gs = MagicMock()
    gs.state_type = "event"
    gs.summary.return_value = "[event] | F3"
    gs.is_combat = False
    gs.is_map = False
    gs.ascension = 0
    gs.run = MagicMock()
    gs.run.floor = 3
    gs.player_hp = 70
    gs.player_max_hp = 70
    gs.gold = 99
    gs.potion_slots = 3
    gs.deck = []

    # Event payload
    ev = MagicMock()
    ev.event_id = "NEOW"
    ev.title = "涅奥"
    ev.description = "A mysterious being."
    ev.is_finished = False
    option = MagicMock()
    option.index = 0
    option.title = "金色珍珠"
    option.description = "获得150金币"
    option.is_locked = False
    option.is_proceed = False
    ev.options = [option]
    gs.event = ev

    # Not these
    gs.rest = None
    gs.shop = None
    gs.reward = None
    gs.chest = None
    gs.selection = None
    gs.combat = None
    return gs


def test_event_state_no_field_collision():
    """B1: 'event' key in state data must not collide with top-level 'event' type."""
    sl = _make_logger("test_b1")
    gs = _make_event_gs()
    sl.log_state(gs, step=5)
    events = _read_events(sl)
    state_events = [e for e in events if e.get("state_type") == "event"]
    assert len(state_events) == 1
    ev = state_events[0]
    # Top-level "event" must be the string "state", NOT a dict
    assert ev["event"] == "state"
    # Event details should be under "event_details"
    assert "event_details" in ev
    assert ev["event_details"]["event_name"] == "涅奥"
    assert ev["event_details"]["event_id"] == "NEOW"
    sl.close()


# ── State logging: combat with card values (M2/M3) ────────────


def _make_combat_gs():
    """Create a mock GameState for combat with card values and intent damage."""
    gs = MagicMock()
    gs.state_type = "monster"
    gs.summary.return_value = "[monster] | F2 | HP:70/70"
    gs.is_combat = True
    gs.is_map = False
    gs.ascension = 0
    gs.combat_round = 1
    gs.is_play_phase = True
    gs.gold = 99
    gs.player_hp = 70
    gs.player_max_hp = 70
    gs.run = MagicMock()
    gs.run.floor = 2
    gs.run.max_energy = 3

    # Player
    player = MagicMock()
    player.current_hp = 70
    player.max_hp = 70
    player.block = 0
    player.energy = 3
    player.stars = 0
    player.powers = []
    gs.combat.player = player

    # Hand card with values
    card = MagicMock()
    card.index = 0
    card.name = "打击"
    card.energy_cost = 1
    card.playable = True
    card.target_type = "AnyEnemy"
    card.rules_text = "造成6点伤害。"
    card.damage = 6
    card.block = None
    card.hits = 1
    card.total_damage = 6
    card.target_previews = None
    card.upgraded = False
    card.star_cost = None
    card.card_type = "Attack"
    card.enchantment_name = None
    gs.hand = [card]

    # Potions
    potion = MagicMock()
    potion.index = 0
    potion.name = "力量药水"
    potion.occupied = True
    potion.can_use = True
    potion.target_type = "Self"
    potion.description = "获得2力量"
    gs.potions = [potion]

    # Relics
    relic = MagicMock()
    relic.name = "蛇之戒指"
    relic.stack = None
    gs.relics = [relic]

    # Enemy with intent damage
    enemy = MagicMock()
    enemy.enemy_id = "SLUDGE_SPINNER"
    enemy.name = "淤泥旋螺"
    enemy.current_hp = 37
    enemy.max_hp = 37
    enemy.block = 0
    intent = MagicMock()
    intent.intent_type = "Attack"
    intent.label = "8"
    intent.damage = 8
    intent.hits = 1
    intent.total_damage = 8
    enemy.intents = [intent]
    enemy.powers = []
    gs.enemies = [enemy]

    # Deck
    deck_card = MagicMock()
    deck_card.name = "打击"
    deck_card.upgraded = False
    deck_card.energy_cost = 1
    gs.deck = [deck_card]

    # Agent view (for pile sizes)
    gs.agent_view = None

    gs.rest = None
    gs.event = None
    gs.shop = None
    gs.reward = None
    gs.chest = None
    gs.selection = None
    return gs


def test_combat_state_has_card_values():
    """M2: Hand cards should include damage/block/rules_text."""
    sl = _make_logger("test_m2")
    gs = _make_combat_gs()
    sl.log_state(gs, step=1)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    hand = state["combat"]["player"]["hand"]
    assert len(hand) == 1
    c = hand[0]
    assert c["rules_text"] == "造成6点伤害。"
    assert c["damage"] == 6
    assert c["hits"] == 1
    assert c["total_damage"] == 6
    sl.close()


def test_combat_state_has_intent_damage():
    """M3: Intents should include structured damage fields."""
    sl = _make_logger("test_m3")
    gs = _make_combat_gs()
    sl.log_state(gs, step=1)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    intent = state["combat"]["enemies"][0]["intents"][0]
    assert intent["damage"] == 8
    assert intent["hits"] == 1
    assert intent["total_damage"] == 8
    sl.close()


def test_evolution_summary_logs_target_and_round_tokens():
    sl = _make_logger("test_evolution_summary")
    sl.log_evolution_summary(
        total_rounds=4,
        total_input_tokens=210000,
        total_output_tokens=5000,
        round_input_tokens=[42000, 50000, 56000, 62000],
        round_output_tokens=[1200, 1100, 1300, 1400],
        actions_taken=2,
        action_types=["write_skill", "author_tool"],
        model="gpt-5.4",
        fallbacks_used=1,
        duration_ms=12345,
        target_input_tokens=200000,
        target_reached=True,
        min_rounds=4,
        max_rounds=6,
        read_only_rounds=2,
    )
    events = _read_events(sl)
    summary = [event for event in events if event.get("event") == "evolution_summary"][0]
    assert summary["target_input_tokens"] == 200000
    assert summary["target_reached"] is True
    assert summary["round_input_tokens"] == [42000, 50000, 56000, 62000]
    assert summary["round_output_tokens"] == [1200, 1100, 1300, 1400]
    assert summary["read_only_rounds"] == 2
    sl.close()


def test_combat_state_logs_boss_stage_metadata_from_override():
    sl = _make_logger("test_boss_stage")
    gs = _make_combat_gs()
    gs.run.floor = 51
    sl.log_state(gs, step=1, combat_type_override="boss")
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    assert state["combat_type"] == "boss"
    assert state["encounter_label"] == "final_boss"
    assert state["boss_stage"] == "final_boss"
    assert state["is_final_boss"] is True
    sl.close()


def test_combat_state_has_potion_details():
    """M8: Potions should include occupied and description."""
    sl = _make_logger("test_m8")
    gs = _make_combat_gs()
    sl.log_state(gs, step=1)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    pot = state["combat"]["player"]["potions"][0]
    assert pot["occupied"] is True
    assert pot["description"] == "获得2力量"
    sl.close()


def test_state_has_deck_list():
    """M4: Deck should be a list of card dicts, not just deck_size."""
    sl = _make_logger("test_m4")
    gs = _make_combat_gs()
    sl.log_state(gs, step=1)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    assert "deck" in state
    assert isinstance(state["deck"], list)
    assert state["deck"][0]["name"] == "打击"
    assert state["deck_size"] == 1
    sl.close()


# ── State logging: shop (M5) ──────────────────────────────────


def _make_shop_gs():
    gs = MagicMock()
    gs.state_type = "shop"
    gs.summary.return_value = "[shop] | F5"
    gs.is_combat = False
    gs.is_map = False
    gs.ascension = 0
    gs.run = MagicMock()
    gs.run.floor = 5
    gs.player_hp = 60
    gs.player_max_hp = 70
    gs.gold = 200
    gs.potion_slots = 3
    gs.deck = []

    shop = MagicMock()
    shop.is_open = True
    card = MagicMock()
    card.index = 0
    card.name = "毒刺"
    card.price = 50
    card.enough_gold = True
    card.category = "Attack"
    card.is_stocked = True
    card.upgraded = False
    card.rules_text = "造成5点伤害。连击2次。"
    shop.cards = [card]
    shop.relics = []
    shop.potions = []
    removal = MagicMock()
    removal.price = 75
    removal.available = True
    removal.used = False
    removal.enough_gold = True
    shop.card_removal = removal
    gs.shop = shop

    gs.rest = None
    gs.event = None
    gs.reward = None
    gs.chest = None
    gs.selection = None
    gs.combat = None
    return gs


def _make_cards_view_gs():
    gs = MagicMock()
    gs.state_type = "cards_view"
    gs.summary.return_value = "[cards_view] | F18"
    gs.is_combat = False
    gs.is_map = False
    gs.ascension = 0
    gs.run = MagicMock()
    gs.run.floor = 18
    gs.player_hp = 70
    gs.player_max_hp = 70
    gs.gold = 128
    gs.potion_slots = 3
    gs.available_actions = ["proceed"]

    deck_card = MagicMock()
    deck_card.name = "中和"
    deck_card.upgraded = True
    deck_card.energy_cost = 0
    gs.deck = [deck_card]

    cards_view = MagicMock()
    cards_view.title = "Pandora's Box"
    card = MagicMock()
    card.index = 0
    card.name = "肾上腺素"
    card.rules_text = "获得2点能量。抽2张牌。消耗。"
    cards_view.cards = [card]
    gs.cards_view = cards_view

    gs.rest = None
    gs.event = None
    gs.shop = None
    gs.reward = None
    gs.chest = None
    gs.selection = None
    gs.combat = None
    return gs


def test_shop_state_logged():
    """M5: Shop inventory should be logged."""
    sl = _make_logger("test_shop")
    gs = _make_shop_gs()
    sl.log_state(gs, step=10)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    assert "shop_details" in state
    shop = state["shop_details"]
    assert shop["is_open"] is True
    assert len(shop["cards"]) == 1
    assert shop["cards"][0]["name"] == "毒刺"
    assert shop["cards"][0]["enough_gold"] is True
    assert shop["card_removal"]["price"] == 75
    assert shop["card_removal"]["available"] is True
    sl.close()


def test_cards_view_state_logged():
    sl = _make_logger("test_cards_view")
    gs = _make_cards_view_gs()
    sl.log_state(gs, step=18)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    assert "cards_view_details" in state
    details = state["cards_view_details"]
    assert details["title"] == "Pandora's Box"
    assert details["available_actions"] == ["proceed"]
    assert details["cards"][0]["name"] == "肾上腺素"
    sl.close()


# ── State logging: treasure (M5) ──────────────────────────────


def _make_treasure_gs():
    gs = MagicMock()
    gs.state_type = "treasure"
    gs.summary.return_value = "[treasure] | F8"
    gs.is_combat = False
    gs.is_map = False
    gs.ascension = 0
    gs.run = MagicMock()
    gs.run.floor = 8
    gs.player_hp = 55
    gs.player_max_hp = 70
    gs.gold = 150
    gs.potion_slots = 3
    gs.deck = []

    chest = MagicMock()
    chest.is_opened = True
    chest.has_relic_been_claimed = False
    relic_opt = MagicMock()
    relic_opt.index = 0
    relic_opt.name = "能量核心"
    relic_opt.rarity = "Rare"
    chest.relic_options = [relic_opt]
    gs.chest = chest

    gs.rest = None
    gs.event = None
    gs.shop = None
    gs.reward = None
    gs.selection = None
    gs.combat = None
    return gs


def test_treasure_state_logged():
    sl = _make_logger("test_treasure")
    gs = _make_treasure_gs()
    sl.log_state(gs, step=20)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    assert "treasure_details" in state
    t = state["treasure_details"]
    assert t["is_opened"] is True
    assert t["relic_options"][0]["name"] == "能量核心"
    sl.close()


# ── State logging: card_select (M5) ───────────────────────────


def _make_card_select_gs():
    gs = MagicMock()
    gs.state_type = "card_select"
    gs.summary.return_value = "[card_select] | F2"
    gs.is_combat = False
    gs.is_map = False
    gs.ascension = 0
    gs.run = MagicMock()
    gs.run.floor = 2
    gs.player_hp = 70
    gs.player_max_hp = 70
    gs.gold = 99
    gs.potion_slots = 3
    gs.deck = []

    sel = MagicMock()
    sel.kind = "discard"
    sel.prompt = "选择1张牌丢弃"
    sel.min_select = 1
    sel.max_select = 1
    card = MagicMock()
    card.index = 0
    card.name = "打击"
    card.rules_text = "造成6点伤害。"
    sel.cards = [card]
    gs.selection = sel

    gs.rest = None
    gs.event = None
    gs.shop = None
    gs.reward = None
    gs.chest = None
    gs.combat = None
    return gs


def test_card_select_state_logged():
    sl = _make_logger("test_card_select")
    gs = _make_card_select_gs()
    sl.log_state(gs, step=5)
    events = _read_events(sl)
    state = [e for e in events if e.get("event") == "state"][0]
    assert "selection_details" in state
    sel = state["selection_details"]
    assert sel["kind"] == "discard"
    assert sel["cards"][0]["name"] == "打击"
    sl.close()


# ── Transition (B2) ───────────────────────────────────────────


def test_transition_has_step():
    """B2: Transitions should include step number."""
    sl = _make_logger("test_b2")
    gs = MagicMock()
    gs.state_type = "monster"
    gs.summary.return_value = "[monster]"
    gs.run = None
    gs.player_hp = 70
    gs.player_max_hp = 70
    sl.log_transition("combat_start", gs, step=42)
    events = _read_events(sl)
    trans = [e for e in events if e["event"] == "transition"][0]
    assert trans["step"] == 42
    assert trans["type"] == "combat_start"
    sl.close()


# ── Action result (M1) ────────────────────────────────────────


def test_action_result_ok():
    sl = _make_logger("test_action_ok")
    sl.log_action_result(
        action="play_card",
        params={"card_index": 3, "target_index": 0},
        status="ok",
        step=10,
    )
    events = _read_events(sl)
    ar = [e for e in events if e["event"] == "action_result"][0]
    assert ar["action"] == "play_card"
    assert ar["status"] == "ok"
    assert ar["step"] == 10
    assert ar["params"]["card_index"] == 3
    assert "error" not in ar
    sl.close()


def test_action_result_soft_fail():
    sl = _make_logger("test_action_sf")
    sl.log_action_result(
        action="end_turn",
        params={},
        status="soft_fail",
        step=11,
        error="not in play phase",
    )
    events = _read_events(sl)
    ar = [e for e in events if e["event"] == "action_result"][0]
    assert ar["status"] == "soft_fail"
    assert ar["error"] == "not in play phase"
    sl.close()


def test_action_result_ok_with_mcp_result():
    sl = _make_logger("test_action_mcp")
    sl.log_action_result(
        action="play_card",
        params={"card_index": 0, "target_index": 0},
        status="ok",
        step=10,
        mcp_result={"status": "ok", "stable": True, "message": ""},
    )
    events = _read_events(sl)
    ar = [e for e in events if e["event"] == "action_result"][0]
    assert ar["mcp_status"] == "ok"
    assert ar["mcp_stable"] is True
    assert "mcp_message" not in ar  # Empty message omitted
    sl.close()


def test_action_result_hard_fail():
    sl = _make_logger("test_action_hf")
    sl.log_action_result(
        action="buy_card",
        params={"card_index": 0},
        status="hard_fail",
        step=12,
        error="max retries (3)",
    )
    events = _read_events(sl)
    ar = [e for e in events if e["event"] == "action_result"][0]
    assert ar["status"] == "hard_fail"
    assert "max retries" in ar["error"]
    sl.close()


def test_perf_event_logging():
    sl = _make_logger("test_perf")
    sl.log_perf(
        "execute.post_action",
        123.45,
        step=42,
        action="play_card",
        source="action_result",
    )
    events = _read_events(sl)
    perf = [e for e in events if e["event"] == "perf"][0]
    assert perf["stage"] == "execute.post_action"
    assert perf["duration_ms"] == 123.5
    assert perf["step"] == 42
    assert perf["action"] == "play_card"
    assert perf["source"] == "action_result"
    sl.close()


# ── Combat summary (M6) ──────────────────────────────────────


def _make_mock_tracker():
    """Create a mock CombatTracker similar to ShortTermMemory's."""
    tracker = MagicMock()
    tracker.enemy_key = "淤泥旋螺"
    tracker.combat_type = "monster"
    tracker._won = True
    tracker._hp_after = 52
    tracker.hp_before = 70
    tracker.floor = 2

    round1 = MagicMock()
    round1.round_num = 1
    round1.cards_played = ["打击", "防御"]
    round1.potions_used = []
    round1.hp_start = 70
    round1.hp_end = 62
    round1.block_gained = 5
    round1.damage_dealt = 12
    round1.damage_taken = 8
    round1.energy_used = 2
    round1.energy_available = 3

    round2 = MagicMock()
    round2.round_num = 2
    round2.cards_played = ["打击", "打击", "防御"]
    round2.potions_used = []
    round2.hp_start = 62
    round2.hp_end = 52
    round2.block_gained = 5
    round2.damage_dealt = 18
    round2.damage_taken = 10
    round2.energy_used = 3
    round2.energy_available = 3

    tracker.rounds = [round1, round2]
    return tracker


def test_combat_summary():
    sl = _make_logger("test_combat_summary")
    tracker = _make_mock_tracker()
    sl.log_combat_summary(tracker, step=20)
    events = _read_events(sl)
    cs = [e for e in events if e["event"] == "combat_summary"][0]
    assert cs["enemy_key"] == "淤泥旋螺"
    assert cs["won"] is True
    assert cs["total_rounds"] == 2
    assert cs["total_cards_played"] == 5
    assert cs["hp_before"] == 70
    assert cs["hp_after"] == 52
    assert cs["terminal_reason"] == "win"
    assert len(cs["rounds"]) == 2
    assert cs["rounds"][0]["cards_played"] == ["打击", "防御"]
    assert cs["rounds"][1]["damage_taken"] == 10
    sl.close()


def test_post_run_stage_events():
    sl = _make_logger("test_post_run_stage")
    sl.log_post_run_start(completion_reason="aborted", end_reason="max_steps")
    sl.log_post_run_stage("memory", "start")
    sl.log_post_run_stage("memory", "done")
    sl.log_post_run_stage(
        "evolution",
        "done",
        context_profile="compact",
        context_chars=128,
        action_count=0,
    )
    sl.log_post_run_end()

    events = _read_events(sl)
    assert [event["event"] for event in events[-4:]] == [
        "post_run_stage",
        "post_run_stage",
        "post_run_stage",
        "post_run_end",
    ]
    post_run_start = [event for event in events if event["event"] == "post_run_start"][0]
    assert post_run_start["completion_reason"] == "aborted"
    evo_done = [
        event for event in events
        if event["event"] == "post_run_stage"
        and event["stage"] == "evolution"
    ][0]
    assert evo_done["context_profile"] == "compact"
    assert evo_done["action_count"] == 0
    sl.close()


# ── LLM call (B3) ─────────────────────────────────────────────


def test_llm_call_has_think_budget():
    """B3: LLM calls should include think_budget (0 for gameplay, thinking disabled for tool_use)."""
    test_log_path = TEST_LOG_DIR / "run_test_b3.jsonl"
    if test_log_path.exists():
        test_log_path.unlink()
    with patch.object(config, "LOG_DIR", str(TEST_LOG_DIR)):
        sl = SessionLogger("test_b3")
        sl.log_llm_call(
            prompt="test",
            response="test",
            latency_ms=100,
            tokens=50,
            model="claude-sonnet-4-6",
            tier="strategic",
            cache_read_tokens=123,
            cache_creation_input_tokens=456,
            prepared_prefix_hash="abc123deadbeef00",
            think_budget=0,
        )
        events = _read_events(sl)
        llm = [e for e in events if e["event"] == "llm_call"][0]
        assert llm["think_budget"] == 0
        assert llm["model"] == "claude-sonnet-4-6"
        assert llm["tier"] == "strategic"
        assert llm["cache_read_tokens"] == 123
        assert llm["cache_creation_input_tokens"] == 456
        assert llm["prepared_prefix_hash"] == "abc123deadbeef00"
        sl.close()


# ── Deduplication ──────────────────────────────────────────────


def test_dedup_skips_identical_state():
    sl = _make_logger("test_dedup")
    gs = _make_event_gs()
    sl.log_state(gs, step=1)
    sl.log_state(gs, step=2)  # Same state, different step — should dedup
    events = _read_events(sl)
    state_events = [e for e in events if e.get("event") == "state"]
    assert len(state_events) == 1
    sl.close()


def test_dedup_emits_after_force():
    sl = _make_logger("test_dedup_force")
    gs = _make_event_gs()
    sl.log_state(gs, step=1)
    sl.force_state_emit()
    sl.log_state(gs, step=2)
    events = _read_events(sl)
    state_events = [e for e in events if e.get("event") == "state"]
    assert len(state_events) == 2
    sl.close()


# ── All event types are strings ────────────────────────────────


def test_all_event_types_are_strings():
    """Verify no event type is accidentally a dict (B1 regression)."""
    sl = _make_logger("test_all_strings")
    transition_gs = MagicMock(state_type="monster", summary=lambda: "x")
    transition_gs.run = None
    transition_gs.player_hp = 70
    transition_gs.player_max_hp = 70
    # Log various events
    sl.log_state(_make_event_gs(), step=1)
    sl.log_state(_make_combat_gs(), step=2)
    sl.log_state(_make_shop_gs(), step=3)
    sl.log_state(_make_treasure_gs(), step=4)
    sl.log_state(_make_card_select_gs(), step=5)
    sl.log_transition("combat_start", transition_gs, step=6)
    sl.log_decision(
        MagicMock(floor=1, state_type="event", action={}, reasoning="",
                  source="llm", strategic_note=None, reasoning_zh=""), step=7
    )
    sl.log_action_result("play_card", {}, "ok", step=8)
    sl.log_combat_summary(_make_mock_tracker(), step=9)
    sl.log_error("test error", step=10)
    sl.log_warning("V2Engine", "test warning", step=11)
    sl.log_run_end(victory=False, floor=7, fitness=53.9)

    events = _read_events(sl)
    for ev in events:
        assert isinstance(ev["event"], str), f"Event type is not string: {ev['event']}"
    sl.close()
