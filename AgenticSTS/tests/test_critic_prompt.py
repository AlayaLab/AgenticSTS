from src.memory.models_v2 import CombatEpisode, CombatRound
from src.skills.critic_prompt import format_round_snapshot, format_combat_header


def _round(**kw):
    defaults = dict(
        round_num=1, energy_available=3, energy_used=2, hp_start=50, hp_end=48,
        block_before=0, draw_pile_size=8, discard_pile_size=0, exhaust_pile_size=0,
        hand_at_start=("Strike", "Defend", "Neutralize"),
        usable_potions=(),
        enemy_intents=("Sewer Clam -> Attack 10",),
        incoming_damage=10,
        agent_plan=("Defend -> self",),
        damage_taken=2,
    )
    defaults.update(kw)
    return CombatRound(**defaults)


def _ep():
    return CombatEpisode(
        enemy_key="Sewer Clam",
        combat_type="monster",
        character="the silent",
        act=1,
        floor=3,
        hp_before=60,
        hp_after=55,
        total_damage_taken=5,
        rounds=(_round(),),
    )


def test_format_combat_header_contains_key_fields():
    s = format_combat_header(_ep())
    assert "monster" in s
    assert "act" in s.lower()
    assert "1" in s
    assert "silent" in s
    assert "60" in s


def test_format_round_snapshot_shape():
    s = format_round_snapshot(_round())
    assert "### Round 1" in s
    assert "Hand:" in s
    assert "Strike" in s
    assert "Piles:" in s
    assert "Draw 8" in s
    assert "Enemy intents:" in s
    assert "Incoming:" in s
    assert "10" in s
    assert "Agent plan:" in s
    assert "Defend -> self" in s
    assert "Outcome:" in s
    assert "damage_taken=2" in s


def test_format_round_snapshot_usable_potions():
    r = _round(usable_potions=("Fire Potion", "Block Potion"))
    s = format_round_snapshot(r)
    assert "Usable Potions:" in s
    assert "Fire Potion" in s


from src.skills.critic_prompt import build_critic_prompt


def test_build_critic_prompt_includes_baselines_and_hard_boundary():
    ep = _ep()
    prompt = build_critic_prompt(
        ep,
        baseline_a=0.10,
        baseline_b=0.12,
        n_a=5, n_b=7,
    )
    assert "Mistake Signal" in prompt
    assert f"{ep.total_damage_taken}" in prompt
    assert "baseline_a" in prompt.lower() or "Baseline A" in prompt
    assert "HARD BOUNDARY" in prompt
    assert "descriptive_rhythm" in prompt
    assert "Counterfactual Test" in prompt
    assert "JSON" in prompt.upper()


def test_build_critic_prompt_handles_missing_baseline():
    ep = _ep()
    # Only baseline A present, B inactive
    prompt = build_critic_prompt(ep, baseline_a=0.10, baseline_b=None, n_a=5, n_b=0)
    assert "0.10" in prompt
    assert "n/a" in prompt  # B baseline rendered as n/a


def test_build_critic_prompt_includes_per_round_trace():
    ep = _ep()
    prompt = build_critic_prompt(ep, baseline_a=0.10, baseline_b=0.12, n_a=5, n_b=7)
    assert "### Round 1" in prompt
    assert "## Per-Round Trace" in prompt
    assert "## Combat Start" in prompt


from src.skills.critic_prompt import parse_and_validate_critic_output, CriticResult


def _valid_skill_output():
    return {
        "analysis": "Agent wasted energy blocking on a buff turn.",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Save Shivs for attack turns",
            "content": "Do not apply Poison via Shiv on Sewer Clam buff turns; save Shivs for attack turns so Weak reduces the incoming hit.",
            "category": "combat",
            "trigger": {
                "state_types": ["monster"],
                "enemy_names": ["Sewer Clam"],
                "character": "silent",
                "requires_cards": ["Shiv"],
                "requires_hand_capabilities": [],
                "any_of_relics": [],
                "requires_enemy_powers": []
            },
            "counterfactual_note": "Holding Shivs for attack turns reduces damage taken by ~6.",
            "mistake_round_indices": [2],
            "expected_correction": "Hold Shivs until attack turn."
        }
    }


def test_validator_accepts_well_formed():
    result = parse_and_validate_critic_output(
        _valid_skill_output(),
        enemy_name="Sewer Clam", character="silent",
        round_count=3, round_llm_call_seqs=[1, 2, 3],
    )
    assert result.decision == "skill_needed"
    assert result.skill is not None
    assert result.skill["name"] == "Save Shivs for attack turns"


def test_validator_rejects_empty_name():
    out = _valid_skill_output()
    out["skill"]["name"] = ""
    result = parse_and_validate_critic_output(
        out, enemy_name="Sewer Clam", character="silent",
        round_count=3, round_llm_call_seqs=[1, 2, 3],
    )
    assert result.decision == "no_skill_needed"
    assert "name" in result.rejection_reason


def test_validator_rejects_bad_round_indices():
    out = _valid_skill_output()
    out["skill"]["mistake_round_indices"] = [99]  # beyond rounds
    result = parse_and_validate_critic_output(
        out, enemy_name="Sewer Clam", character="silent",
        round_count=3, round_llm_call_seqs=[1, 2, 3],
    )
    assert result.decision == "no_skill_needed"


def test_validator_rejects_missing_llm_call_seq():
    out = _valid_skill_output()
    # round 2 has llm_call_seq = -1 (not recorded) -> cannot fetch prompt for A/B
    result = parse_and_validate_critic_output(
        out, enemy_name="Sewer Clam", character="silent",
        round_count=3, round_llm_call_seqs=[1, -1, 3],
    )
    assert result.decision == "no_skill_needed"


def test_validator_descriptive_rhythm_regex():
    """Purely descriptive content + no imperative cue -> auto-relabel."""
    out = _valid_skill_output()
    out["skill"]["content"] = "Sewer Clam attacks on odd turns and buffs on even. The safe window is turn 2."
    result = parse_and_validate_critic_output(
        out, enemy_name="Sewer Clam", character="silent",
        round_count=3, round_llm_call_seqs=[1, 2, 3],
    )
    assert result.decision == "no_skill_needed"
    assert result.reason == "descriptive_rhythm"


def test_validator_imperative_cue_passes():
    out = _valid_skill_output()
    # 'save' is an imperative cue even though content mentions "attacks on"
    out["skill"]["content"] = "Sewer Clam attacks on odd turns: SAVE your Shivs for those turns and do not waste Poison on buff turns."
    result = parse_and_validate_critic_output(
        out, enemy_name="Sewer Clam", character="silent",
        round_count=3, round_llm_call_seqs=[1, 2, 3],
    )
    assert result.decision == "skill_needed"


def test_validator_enemy_mismatch_rejected():
    out = _valid_skill_output()
    out["skill"]["trigger"]["enemy_names"] = ["Rat"]
    result = parse_and_validate_critic_output(
        out, enemy_name="Sewer Clam", character="silent",
        round_count=3, round_llm_call_seqs=[1, 2, 3],
    )
    assert result.decision == "no_skill_needed"
