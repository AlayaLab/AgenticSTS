from src.memory.models_v2 import (
    CombatEpisode,
    CombatRound,
    EnemyIntentSnapshot,
    EnemyRoundState,
    PowerSnapshot,
)
from src.memory.short_term import CombatRoundTracker


def test_combat_round_new_fields_default():
    r = CombatRound()
    assert r.enemy_states == ()
    assert r.player_powers_snapshot == ()
    assert r.block_before == 0
    assert r.draw_pile_size == 0
    assert r.discard_pile_size == 0
    assert r.exhaust_pile_size == 0
    assert r.usable_potions == ()
    assert r.incoming_damage == 0
    assert r.agent_plan == ()
    assert r.llm_call_seq == -1


def test_combat_round_new_fields_roundtrip():
    r = CombatRound(
        round_num=2,
        hp_start=50,
        enemy_states=(
            EnemyRoundState(
                enemy_id="boss-1",
                name="The Insatiable",
                hp=120,
                max_hp=200,
                block=0,
                powers=(
                    PowerSnapshot(
                        power_id="SANDPIT",
                        name="Sandpit",
                        amount=4,
                        description="Decreases by 1 each turn.",
                    ),
                ),
                intents=(
                    EnemyIntentSnapshot(
                        intent_type="Attack",
                        damage=10,
                        hits=2,
                        total_damage=20,
                    ),
                ),
            ),
        ),
        player_powers_snapshot=(
            PowerSnapshot(
                power_id="WEAK",
                name="Weak",
                amount=2,
                description="Deal 25% less Attack damage.",
                is_debuff=True,
            ),
        ),
        block_before=8,
        draw_pile_size=5,
        discard_pile_size=3,
        exhaust_pile_size=1,
        usable_potions=("Fire Potion",),
        incoming_damage=12,
        agent_plan=("Defend -> self", "Strike -> enemy_0"),
        llm_call_seq=7,
    )
    d = r.to_dict()
    r2 = CombatRound.from_dict(d)
    assert r2 == r


def test_combat_round_legacy_dict_loads_with_defaults():
    """Old JSONL without new fields must still load."""
    legacy = {"round_num": 1, "hp_start": 60, "damage_taken": 5}
    r = CombatRound.from_dict(legacy)
    assert r.round_num == 1
    assert r.enemy_states == ()
    assert r.player_powers_snapshot == ()
    assert r.block_before == 0
    assert r.llm_call_seq == -1
    assert r.usable_potions == ()


def test_combat_episode_retrieved_skill_ids_default():
    ep = CombatEpisode()
    assert ep.retrieved_skill_ids == ()


def test_combat_episode_retrieved_skill_ids_roundtrip():
    ep = CombatEpisode(
        episode_id="ep1",
        run_id="r1",
        enemy_key="Sewer Clam",
        retrieved_skill_ids=("skill_a", "skill_b", "skill_a"),  # dedupe is caller responsibility
    )
    d = ep.to_dict()
    ep2 = CombatEpisode.from_dict(d)
    assert ep2.retrieved_skill_ids == ("skill_a", "skill_b", "skill_a")


def test_combat_episode_legacy_loads():
    legacy = {"episode_id": "x", "run_id": "r", "enemy_key": "Rat"}
    ep = CombatEpisode.from_dict(legacy)
    assert ep.retrieved_skill_ids == ()

def test_combat_round_tracker_new_fields():
    t = CombatRoundTracker()
    assert t.enemy_states == []
    assert t.player_powers_snapshot == []
    assert t.block_before == 0
    assert t.draw_pile_size == 0
    assert t.discard_pile_size == 0
    assert t.exhaust_pile_size == 0
    assert t.usable_potions == []
    assert t.incoming_damage == 0
    assert t.agent_plan == []
    assert t.llm_call_seq == -1
