from src.memory.short_term import CombatTracker, ShortTermMemory
from src.memory.combat_extractor import extract_combat_episodes


def test_extractor_preserves_round_context():
    stm = ShortTermMemory()
    tracker = CombatTracker(
        enemy_key="Sewer Clam",
        combat_type="monster",
        enemy_names=["Sewer Clam"],
        hp_before=60,
        floor=3,
        act=1,
    )
    tracker.start_round(round_num=1, energy=3, hp=60, enemy_intents=["Attack 10"], hand_cards=["Defend"])
    tracker.record_round_context(
        block_before=0,
        draw_pile_size=9,
        discard_pile_size=0,
        exhaust_pile_size=0,
        usable_potions=[],
        incoming_damage=10,
        agent_plan=["Defend -> self"],
        llm_call_seq=3,
    )
    tracker.record_card_play("Defend", energy_cost=1)
    tracker.update_hp(55)
    # Simulate end: push to completed
    tracker.rounds.append(tracker._current_round)
    tracker._current_round = None
    tracker.hp_after = 55
    stm.completed_combats.append(tracker)

    episodes = extract_combat_episodes(stm, run_id="rX", character="silent")
    assert len(episodes) == 1
    ep = episodes[0]
    r = ep.rounds[0]
    assert r.block_before == 0
    assert r.draw_pile_size == 9
    assert r.incoming_damage == 10
    assert r.agent_plan == ("Defend -> self",)
    assert r.llm_call_seq == 3


def test_extractor_preserves_retrieved_skill_ids():
    stm = ShortTermMemory()
    tracker = CombatTracker(
        enemy_key="Rat",
        combat_type="monster",
        enemy_names=["Rat"],
        hp_before=60,
        floor=1,
        act=1,
    )
    tracker.retrieved_skill_ids.extend(["skill_a", "skill_b", "skill_a"])
    tracker.start_round(round_num=1, energy=3, hp=60, enemy_intents=["Attack 5"])
    tracker.rounds.append(tracker._current_round)
    tracker._current_round = None
    tracker.hp_after = 55
    stm.completed_combats.append(tracker)

    episodes = extract_combat_episodes(stm, run_id="rX", character="silent")
    assert len(episodes) == 1
    ep = episodes[0]
    assert ep.retrieved_skill_ids == ("skill_a", "skill_b", "skill_a")
