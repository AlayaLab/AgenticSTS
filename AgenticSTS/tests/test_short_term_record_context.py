from src.memory.short_term import CombatTracker


def test_record_round_context_sets_all_fields():
    t = CombatTracker()
    t.start_round(round_num=1, energy=3, hp=50, enemy_intents=["Attack 12"], hand_cards=["Strike"])
    t.record_round_context(
        block_before=5,
        draw_pile_size=12,
        discard_pile_size=3,
        exhaust_pile_size=0,
        usable_potions=["Fire Potion"],
        incoming_damage=12,
        agent_plan=["Defend -> self", "Strike -> enemy_0"],
        llm_call_seq=42,
    )
    cur = t._current_round
    assert cur.block_before == 5
    assert cur.draw_pile_size == 12
    assert cur.usable_potions == ["Fire Potion"]
    assert cur.incoming_damage == 12
    assert cur.agent_plan == ["Defend -> self", "Strike -> enemy_0"]
    assert cur.llm_call_seq == 42


def test_record_round_context_noop_when_no_active_round():
    t = CombatTracker()
    # Do NOT call start_round — _current_round is None
    t.record_round_context(block_before=5)  # must not raise
    assert t._current_round is None
