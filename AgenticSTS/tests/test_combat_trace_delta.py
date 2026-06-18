"""Unit tests for combat trace delta computation."""
from __future__ import annotations


def _player(hp=80, block=0, energy=3, hand=None, draw_pile=None,
            discard_pile=None, exhaust_pile=None, powers=None):
    return {
        "hp": hp, "max_hp": 80, "block": block, "energy": energy,
        "hand": hand or [], "draw_pile": draw_pile or [],
        "discard_pile": discard_pile or [], "exhaust_pile": exhaust_pile or [],
        "powers": powers or [],
    }


def _enemy(eid="e1", name="Goon", hp=50, max_hp=50, intent="Attack 8", powers=None):
    return {
        "enemy_id": eid, "name": name, "hp": hp, "max_hp": max_hp,
        "intent": intent, "powers": powers or [],
    }


def _snapshot(player, enemies):
    return {"combat": {"player": player, "enemies": enemies}}


def _card(name, **extra):
    return {"name": name, "energy_cost": 1, "card_type": "Attack",
            "rules_text": "Deal X damage.", "upgraded": False,
            **extra}


def test_compute_delta_player_energy_block_change():
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(_player(energy=3, block=0), [_enemy()])
    post = _snapshot(_player(energy=0, block=8), [_enemy()])
    delta = compute_block_delta(pre, post, played_cards=["Defend"])
    assert delta.player_energy == (3, 0)
    assert delta.player_block == (0, 8)


def test_compute_delta_player_power_added():
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(_player(powers=[]), [_enemy()])
    post = _snapshot(
        _player(powers=[{"name": "Phantom Blades", "amount": 1, "description": "Shivs gain Retain."}]),
        [_enemy()],
    )
    delta = compute_block_delta(pre, post, played_cards=["Phantom Blades"])
    assert len(delta.player_powers_added) == 1
    p = delta.player_powers_added[0]
    assert p.name == "Phantom Blades"
    assert p.amount == 1
    assert p.description == "Shivs gain Retain."


def test_compute_delta_player_power_stack_changed():
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(
        _player(powers=[{"name": "Strength", "amount": 2, "description": "+dmg"}]),
        [_enemy()],
    )
    post = _snapshot(
        _player(powers=[{"name": "Strength", "amount": 5, "description": "+dmg"}]),
        [_enemy()],
    )
    delta = compute_block_delta(pre, post, played_cards=["Inflame"])
    assert delta.player_powers_added == ()
    assert delta.player_powers_stack_changed == (("Strength", 2, 5),)


def test_compute_delta_hand_added_cards():
    """Cards present in post.hand but not pre.hand AND not in played_cards
    are net additions (from card-generation effects or draws)."""
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(_player(hand=[_card("Hidden Daggers"), _card("Strike")]), [_enemy()])
    post = _snapshot(
        _player(hand=[_card("Strike"), _card("Shiv+"), _card("Shiv+")]),
        [_enemy()],
    )
    delta = compute_block_delta(pre, post, played_cards=["Hidden Daggers"])
    # Net additions: 2x Shiv+
    added_names = [c.name for c in delta.hand_added]
    assert added_names.count("Shiv+") == 2


def test_compute_delta_enemy_hp_damage():
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(_player(), [_enemy(hp=150)])
    post = _snapshot(_player(), [_enemy(hp=126)])
    delta = compute_block_delta(pre, post, played_cards=["Strike"])
    assert len(delta.enemies) == 1
    e = delta.enemies[0]
    assert e.name == "Goon"
    assert e.hp_pre == 150
    assert e.hp_post == 126
    assert e.killed is False


def test_compute_delta_enemy_killed_when_hp_zero_or_absent():
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(_player(), [_enemy(eid="e1", hp=10), _enemy(eid="e2", hp=20)])
    post = _snapshot(_player(), [_enemy(eid="e2", hp=15)])  # e1 absent
    delta = compute_block_delta(pre, post, played_cards=["Strike"])
    assert len(delta.enemies) == 2
    by_id = {e.id: e for e in delta.enemies}
    assert by_id["e1"].killed is True
    assert by_id["e2"].killed is False


def test_compute_delta_enemy_intent_change():
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(_player(), [_enemy(intent="Attack 8")])
    post = _snapshot(_player(), [_enemy(intent="Defend 5")])
    delta = compute_block_delta(pre, post, played_cards=[])
    assert delta.enemies[0].intent_pre == "Attack 8"
    assert delta.enemies[0].intent_post == "Defend 5"


def test_compute_delta_returns_none_when_pre_missing():
    from src.memory.combat_trace_delta import compute_block_delta

    delta = compute_block_delta(None, _snapshot(_player(), [_enemy()]), played_cards=[])
    assert delta is None


def test_compute_delta_returns_none_when_post_missing():
    from src.memory.combat_trace_delta import compute_block_delta

    delta = compute_block_delta(_snapshot(_player(), [_enemy()]), None, played_cards=[])
    assert delta is None


def test_compute_delta_drew_count_inferred_from_draw_pile_shrink():
    """draw_pile shrunk by N AND post.hand contains N more cards -> drew N."""
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(
        _player(hand=[], draw_pile=[_card("A"), _card("B"), _card("C")]),
        [_enemy()],
    )
    post = _snapshot(
        _player(hand=[_card("A"), _card("B")], draw_pile=[_card("C")]),
        [_enemy()],
    )
    delta = compute_block_delta(pre, post, played_cards=[])
    assert delta.drew_count == 2


def test_first_appearance_tracker_seeded_from_hand():
    from src.memory.combat_trace_delta import FirstAppearanceTracker

    starting_hand = [_card("Strike"), _card("Defend"), _card("Backstab", upgraded=True)]
    starting_powers = [{"name": "Thorns", "amount": 3, "description": "Reflect"}]
    t = FirstAppearanceTracker.from_starting_state(starting_hand, starting_powers)
    assert t.has_seen_card("Strike") is True
    assert t.has_seen_card("Defend") is True
    assert t.has_seen_card("Backstab+") is True  # upgraded marker
    assert t.has_seen_card("Shiv") is False
    assert t.has_seen_power("Thorns") is True
    assert t.has_seen_power("Phantom Blades") is False


def test_first_appearance_tracker_marks_on_record():
    from src.memory.combat_trace_delta import FirstAppearanceTracker

    t = FirstAppearanceTracker.from_starting_state([], [])
    assert t.has_seen_card("Shiv") is False
    t.mark_card_seen("Shiv")
    assert t.has_seen_card("Shiv") is True
    t.mark_power_seen("Phantom Blades")
    assert t.has_seen_power("Phantom Blades") is True


def test_first_appearance_tracker_card_upgrade_distinct():
    """Shiv and Shiv+ are different identities."""
    from src.memory.combat_trace_delta import FirstAppearanceTracker

    t = FirstAppearanceTracker.from_starting_state([_card("Shiv")], [])
    assert t.has_seen_card("Shiv") is True
    assert t.has_seen_card("Shiv+") is False


def test_first_appearance_tracker_power_stack_shares_identity():
    """Phantom Blades(1) and Phantom Blades(2) share an identity — marking
    the same power name twice keeps the seen_powers set at size 1."""
    from src.memory.combat_trace_delta import FirstAppearanceTracker

    t = FirstAppearanceTracker.from_starting_state([], [])
    t.mark_power_seen("Phantom Blades")
    t.mark_power_seen("Phantom Blades")  # simulating a stack change
    assert t.has_seen_power("Phantom Blades") is True
    assert len(t.seen_powers) == 1


def test_format_delta_player_only_changed_fields():
    from src.memory.combat_trace_delta import (
        BlockDelta, FirstAppearanceTracker, format_block_delta,
    )
    delta = BlockDelta(
        player_energy=(3, 0), player_block=(0, 8), player_hp=None,
    )
    tracker = FirstAppearanceTracker()
    out = format_block_delta(delta, tracker)
    assert "Player: energy 3→0, block 0→8" in out
    # No power line, no hand line, no enemy line
    assert "+power" not in out
    assert "Hand:" not in out


def test_format_delta_new_power_carries_description_first_time():
    from src.memory.combat_trace_delta import (
        BlockDelta, PowerDelta, FirstAppearanceTracker, format_block_delta,
    )
    delta = BlockDelta(
        player_energy=None, player_block=None, player_hp=None,
        player_powers_added=(
            PowerDelta(name="Phantom Blades", amount=1, description="Shivs gain Retain."),
        ),
    )
    tracker = FirstAppearanceTracker()
    out = format_block_delta(delta, tracker)
    assert "+power Phantom Blades(1) — Shivs gain Retain." in out
    assert tracker.has_seen_power("Phantom Blades")


def test_format_delta_new_power_no_description_on_second_appearance():
    from src.memory.combat_trace_delta import (
        BlockDelta, PowerDelta, FirstAppearanceTracker, format_block_delta,
    )
    tracker = FirstAppearanceTracker()
    tracker.mark_power_seen("Phantom Blades")
    delta = BlockDelta(
        player_energy=None, player_block=None, player_hp=None,
        player_powers_added=(
            PowerDelta(name="Phantom Blades", amount=1, description="Shivs gain Retain."),
        ),
    )
    out = format_block_delta(delta, tracker)
    assert "+power Phantom Blades(1)" in out
    assert "Shivs gain Retain." not in out


def test_format_delta_power_stack_change():
    from src.memory.combat_trace_delta import (
        BlockDelta, FirstAppearanceTracker, format_block_delta,
    )
    delta = BlockDelta(
        player_energy=None, player_block=None, player_hp=None,
        player_powers_stack_changed=(("Strength", 2, 5),),
    )
    out = format_block_delta(delta, FirstAppearanceTracker())
    assert "Strength(2)→(5)" in out


def test_format_delta_hand_added_collapses_runs_with_first_description():
    from src.memory.combat_trace_delta import (
        BlockDelta, CardDelta, FirstAppearanceTracker, format_block_delta,
    )
    delta = BlockDelta(
        player_energy=None, player_block=None, player_hp=None,
        hand_added=(
            CardDelta(name="Shiv+", rules_text="Deal 6 damage.",
                      energy_cost=0, card_type="Attack"),
            CardDelta(name="Shiv+", rules_text="Deal 6 damage.",
                      energy_cost=0, card_type="Attack"),
        ),
    )
    tracker = FirstAppearanceTracker()
    out = format_block_delta(delta, tracker)
    assert "+2 Shiv+" in out
    assert "Shiv+ (Attack, cost=0): Deal 6 damage." in out
    assert tracker.has_seen_card("Shiv+")


def test_format_delta_drew_count_with_card_descriptions():
    from src.memory.combat_trace_delta import (
        BlockDelta, CardDelta, FirstAppearanceTracker, format_block_delta,
    )
    delta = BlockDelta(
        player_energy=None, player_block=None, player_hp=None,
        drew_count=2,
        hand_added=(
            CardDelta(name="Footwork+", rules_text="Gain 3 Dexterity.",
                      energy_cost=1, card_type="Power"),
        ),
    )
    out = format_block_delta(delta, FirstAppearanceTracker())
    assert "drew 2" in out


def test_format_delta_enemy_damage_and_unchanged_intent():
    from src.memory.combat_trace_delta import (
        BlockDelta, EnemyDelta, FirstAppearanceTracker, format_block_delta,
    )
    delta = BlockDelta(
        player_energy=None, player_block=None, player_hp=None,
        enemies=(
            EnemyDelta(id="e1", name="Fabricator", hp_pre=150, hp_post=126,
                       killed=False, intent_pre="Summon", intent_post="Summon",
                       powers_added=(), powers_stack_changed=()),
        ),
    )
    out = format_block_delta(delta, FirstAppearanceTracker())
    assert "Fabricator: 150→126 HP (-24)" in out
    assert "intent unchanged (Summon)" in out


def test_format_delta_enemy_killed_marker():
    from src.memory.combat_trace_delta import (
        BlockDelta, EnemyDelta, FirstAppearanceTracker, format_block_delta,
    )
    delta = BlockDelta(
        player_energy=None, player_block=None, player_hp=None,
        enemies=(
            EnemyDelta(id="e1", name="Goon", hp_pre=10, hp_post=0,
                       killed=True, intent_pre="Attack 8", intent_post="",
                       powers_added=(), powers_stack_changed=()),
        ),
    )
    out = format_block_delta(delta, FirstAppearanceTracker())
    assert "Goon: 10→0 HP (-10) (killed)" in out


def test_format_delta_returns_empty_when_no_changes():
    from src.memory.combat_trace_delta import (
        BlockDelta, FirstAppearanceTracker, format_block_delta,
    )
    out = format_block_delta(
        BlockDelta(player_energy=None, player_block=None, player_hp=None),
        FirstAppearanceTracker(),
    )
    assert out == ""


# ---------------------------------------------------------------------------
# Fix 1: _format_enemy_intent — production schema + legacy fallback
# ---------------------------------------------------------------------------

def test_format_enemy_intent_uses_intents_list_in_production_schema():
    """Production schema: enemies emit `intents: [{...}]`, not `intent` string."""
    from src.memory.combat_trace_delta import _format_enemy_intent

    # Production-shape enemy with structured intents
    enemy = {
        "enemy_id": "e1", "name": "Goon",
        "intents": [{"type": "attack", "label": "Attack",
                     "damage": 8, "hits": 1, "total_damage": 8}],
    }
    assert _format_enemy_intent(enemy) == "Attack 8"


def test_format_enemy_intent_handles_multi_hit_attack():
    from src.memory.combat_trace_delta import _format_enemy_intent

    enemy = {
        "intents": [{"type": "attack", "label": "Slash",
                     "damage": 4, "hits": 3, "total_damage": 12}],
    }
    assert _format_enemy_intent(enemy) == "Slash 12 (3 hits)"


def test_format_enemy_intent_falls_back_to_legacy_string():
    """Legacy/test schema: enemies emit `intent: 'Attack 8'`."""
    from src.memory.combat_trace_delta import _format_enemy_intent

    enemy = {"intent": "Attack 8"}
    assert _format_enemy_intent(enemy) == "Attack 8"


def test_format_enemy_intent_returns_empty_when_no_intent():
    from src.memory.combat_trace_delta import _format_enemy_intent

    assert _format_enemy_intent({}) == ""
    assert _format_enemy_intent({"intents": []}) == ""


def test_compute_delta_enemy_intent_via_intents_list():
    """Production schema: intent change should be detected via `intents` list."""
    from src.memory.combat_trace_delta import compute_block_delta

    pre = _snapshot(_player(), [{
        "enemy_id": "e1", "name": "Goon", "hp": 50, "max_hp": 50,
        "intents": [{"type": "attack", "label": "Attack",
                     "damage": 8, "hits": 1, "total_damage": 8}],
        "powers": [],
    }])
    post = _snapshot(_player(), [{
        "enemy_id": "e1", "name": "Goon", "hp": 50, "max_hp": 50,
        "intents": [{"type": "defend", "label": "Defend",
                     "damage": 0, "hits": 0, "total_damage": 0}],
        "powers": [],
    }])
    delta = compute_block_delta(pre, post, played_cards=[])
    assert delta.enemies[0].intent_pre == "Attack 8"
    assert delta.enemies[0].intent_post.startswith("Defend")


# ---------------------------------------------------------------------------
# Fix 2: drew_count from combat.draw_pile_size scalar
# ---------------------------------------------------------------------------

def test_compute_delta_drew_count_via_combat_draw_pile_size():
    """Production schema: draw_pile_size is a scalar at combat root."""
    from src.memory.combat_trace_delta import compute_block_delta

    pre = {
        "combat": {
            "player": _player(hand=[]),
            "enemies": [_enemy()],
            "draw_pile_size": 10,
        }
    }
    post = {
        "combat": {
            "player": _player(hand=[_card("A"), _card("B")]),
            "enemies": [_enemy()],
            "draw_pile_size": 8,
        }
    }
    delta = compute_block_delta(pre, post, played_cards=[])
    assert delta.drew_count == 2
