from src.memory.guide_consolidator import (
    build_combat_guide_prompt,
    parse_combat_guide_response,
)
from src.memory.models_v2 import (
    CombatEpisode,
    CombatGuide,
    CombatRound,
    EnemyIntentSnapshot,
    EnemyRoundState,
    PowerSnapshot,
)


def _round(
    round_num: int,
    *,
    enemy_hp: int,
    max_hp: int = 200,
    sandpit: int = 4,
    player_debuff: str = "Weak",
    player_debuff_amount: int = 1,
) -> CombatRound:
    return CombatRound(
        round_num=round_num,
        hp_start=70,
        hp_end=60,
        enemy_states=(
            EnemyRoundState(
                enemy_id="boss-1",
                name="The Insatiable",
                hp=enemy_hp,
                max_hp=max_hp,
                block=0,
                powers=(
                    PowerSnapshot(
                        power_id="SANDPIT",
                        name="Sandpit",
                        amount=sandpit,
                        description="Decreases by 1 each turn. When it reaches 0, you die.",
                    ),
                ),
                intents=(
                    EnemyIntentSnapshot(
                        intent_type="Attack",
                        damage=10,
                        hits=2,
                        total_damage=20,
                    ),
                    EnemyIntentSnapshot(
                        intent_type="Status",
                        label="Dazed",
                        status_card_count=2,
                    ),
                ),
            ),
        ),
        player_powers_snapshot=(
            PowerSnapshot(
                power_id=player_debuff.upper(),
                name=player_debuff,
                amount=player_debuff_amount,
                description=f"{player_debuff} description.",
                is_debuff=True,
            ),
        ),
    )


def _episode(*, won: bool, hp_after: int, rounds: tuple[CombatRound, ...]) -> CombatEpisode:
    return CombatEpisode(
        enemy_key="The Insatiable",
        character="the silent",
        combat_type="boss",
        won=won,
        terminal_reason="win" if won else "loss",
        hp_before=70,
        hp_after=hp_after,
        hp_delta=hp_after - 70,
        rounds=rounds,
    )


def test_build_combat_guide_prompt_focuses_on_enemy_mechanics():
    episodes = [
        _episode(
            won=False,
            hp_after=0,
            rounds=(
                _round(1, enemy_hp=200, sandpit=4),
                _round(2, enemy_hp=180, sandpit=3),
            ),
        ),
        _episode(
            won=True,
            hp_after=32,
            rounds=(
                _round(1, enemy_hp=200, sandpit=4),
                _round(2, enemy_hp=150, sandpit=3),
            ),
        ),
    ]

    prompt = build_combat_guide_prompt("The Insatiable", "the silent", episodes)

    assert "## Power-defined rules" in prompt
    assert "## HP / death / revive linked observations" in prompt
    assert "## Status / debuff pressure on player" in prompt
    assert "Top cards in wins" not in prompt
    assert "Cleanest wins" not in prompt
    assert "Do not rank cards" in prompt


def test_parse_combat_guide_response_reads_new_fields():
    raw = """
    {
      "trigger_model": "mixed",
      "mechanic_summary": ["Round timer plus low-HP shift."],
      "round_triggers": ["Sandpit decreases by 1 each round."],
      "threshold_triggers": ["At low HP, the boss gains a new phase power."],
      "danger_windows": ["R4-R6 when Sandpit is low and heavy attacks overlap."],
      "failure_modes": ["Losing track of Sandpit while eating status-card turns."],
      "guide_text": "- Respect the timer.\\n- Prepare for the low-HP phase.",
      "confidence": 0.82
    }
    """
    existing = CombatGuide(enemy_key="The Insatiable", character="the silent", version=2)
    guide = parse_combat_guide_response(
        raw,
        "The Insatiable",
        "the silent",
        episode_count=7,
        win_rate=0.4,
        existing_guide=existing,
    )

    assert guide is not None
    assert guide.trigger_model == "mixed"
    assert guide.mechanic_summary == ("Round timer plus low-HP shift.",)
    assert guide.round_triggers == ("Sandpit decreases by 1 each round.",)
    assert guide.threshold_triggers == ("At low HP, the boss gains a new phase power.",)
    assert guide.danger_windows == ("R4-R6 when Sandpit is low and heavy attacks overlap.",)
    assert guide.failure_modes == ("Losing track of Sandpit while eating status-card turns.",)
    assert guide.version == 3
