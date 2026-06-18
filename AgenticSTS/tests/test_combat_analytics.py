"""Tests for combat analytics module."""
from __future__ import annotations

from src.memory.combat_analytics import (
    compute_card_stats,
    compute_enemy_power_timeline,
    compute_poison_tick_per_round,
    compute_poison_tracking,
    compute_token_attribution,
    detect_death_cause,
    format_analytics,
)
from src.memory.models_v2 import (
    CombatDelta,
    CombatEpisode,
    CombatRound,
    EnemyDelta,
)

# ── Helpers ──────────────────────────────────────────────────


def _make_episode(
    won: bool = True,
    hp_before: int = 70,
    hp_after: int = 50,
    rounds: list[CombatRound] | None = None,
    terminal_reason: str | None = None,
) -> CombatEpisode:
    return CombatEpisode(
        enemy_key="The Insatiable",
        character="the silent",
        combat_type="boss",
        won=won,
        terminal_reason=terminal_reason or ("win" if won else "loss"),
        hp_before=hp_before,
        hp_after=hp_after,
        hp_delta=hp_after - hp_before,
        rounds=tuple(rounds or []),
    )


def _make_round(
    round_num: int = 1,
    hp_start: int = 70,
    hp_end: int = 70,
    damage_dealt: int = 0,
    damage_taken: int = 0,
    events: list[CombatDelta] | None = None,
    enemy_powers_snapshot: tuple[tuple[str, ...], ...] = (),
) -> CombatRound:
    return CombatRound(
        round_num=round_num,
        hp_start=hp_start,
        hp_end=hp_end,
        damage_dealt=damage_dealt,
        damage_taken=damage_taken,
        events=tuple(events or []),
        enemy_powers_snapshot=enemy_powers_snapshot,
    )


def _card_event(
    source: str,
    enemy_hp: int | None = None,
    poison_change: str = "",
    source_description: str = "",
    block: int | None = None,
) -> CombatDelta:
    enemy_deltas = ()
    if enemy_hp is not None or poison_change:
        powers_changed = (poison_change,) if poison_change else ()
        enemy_deltas = (EnemyDelta(
            enemy_id="E0", name="Boss", index=0,
            hp=enemy_hp, powers_changed=powers_changed,
        ),)
    return CombatDelta(
        event_type="card_play",
        source=source,
        source_description=source_description,
        enemy_deltas=enemy_deltas,
        block=block,
    )


# ── Death Cause ──────────────────────────────────────────────


class TestDeathCause:
    def test_win_returns_empty(self):
        ep = _make_episode(won=True)
        cause, detail = detect_death_cause(ep)
        assert cause == ""

    def test_hp_damage_death(self):
        r = _make_round(hp_start=10, hp_end=0, damage_taken=10)
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        cause, detail = detect_death_cause(ep)
        assert cause == "hp_damage"

    def test_sandpit_death(self):
        r = _make_round(
            hp_start=31, hp_end=0, damage_taken=0,
            enemy_powers_snapshot=(("Sandpit(1)", "Strength(2)"),),
        )
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        cause, detail = detect_death_cause(ep)
        assert cause == "sandpit"
        assert "31" in detail

    def test_mechanic_death_no_sandpit(self):
        r = _make_round(hp_start=25, hp_end=0, damage_taken=3)
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        cause, detail = detect_death_cause(ep)
        assert cause == "mechanic"

    def test_no_rounds(self):
        ep = _make_episode(won=False, hp_after=0, rounds=[])
        cause, detail = detect_death_cause(ep)
        assert cause == "hp_damage"

    def test_hp_after_positive_returns_empty(self):
        """hp_after > 0 means combat ended but not dead."""
        r = _make_round(hp_start=30, hp_end=30)
        ep = _make_episode(won=False, hp_after=30, rounds=[r])
        cause, _ = detect_death_cause(ep)
        assert cause == ""

    def test_aborted_combat_returns_empty(self):
        ep = _make_episode(won=False, hp_after=0, terminal_reason="abort")
        cause, detail = detect_death_cause(ep)
        assert cause == ""
        assert detail == ""


# ── Card Stats ───────────────────────────────────────────────


class TestCardStats:
    def test_basic_damage_attribution(self):
        events = [
            _card_event("Strike", enemy_hp=-6, source_description="Deal 6 damage."),
            _card_event("Strike", enemy_hp=-6, source_description="Deal 6 damage."),
            _card_event("Defend", block=8, source_description="Gain 8 Block."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        strike = next(s for s in stats if s.name == "Strike")
        assert strike.plays == 2
        assert strike.total_damage == 12

    def test_block_tracked(self):
        events = [
            _card_event("Defend", block=8, source_description="Gain 8 Block."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        defend = next(s for s in stats if s.name == "Defend")
        assert defend.total_block == 8

    def test_exhaust_detected_from_description(self):
        events = [
            _card_event("Blade Dance", enemy_hp=-2,
                        source_description="Add 3 Shivs into your Hand. Exhaust."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        bd = next(s for s in stats if s.name == "Blade Dance")
        assert bd.exhausts is True
        assert bd.tokens_generated == 3

    def test_poison_stacks_tracked(self):
        events = [
            _card_event("Poisoned Stab", enemy_hp=-6, poison_change="+Poison(3)",
                        source_description="Deal 6 damage. Apply 3 Poison."),
            _card_event("Deadly Poison", poison_change="Poison(3→5)",
                        source_description="Apply 5 Poison."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        ps = next(s for s in stats if s.name == "Poisoned Stab")
        assert ps.poison_stacks_applied == 3
        dp = next(s for s in stats if s.name == "Deadly Poison")
        assert dp.poison_stacks_applied == 2  # 5 - 3

    def test_sorted_by_damage_desc(self):
        events = [
            _card_event("Strike", enemy_hp=-6),
            _card_event("Predator", enemy_hp=-20),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        assert stats[0].name == "Predator"
        assert stats[1].name == "Strike"

    def test_no_events_returns_empty(self):
        r = _make_round()
        ep = _make_episode(rounds=[r])
        stats = compute_card_stats(ep)
        assert stats == ()


# ── Poison Tracking ──────────────────────────────────────────


class TestPoisonTracking:
    def test_poison_by_card(self):
        events = [
            _card_event("Poisoned Stab", poison_change="+Poison(3)"),
            _card_event("Deadly Poison", poison_change="Poison(3→8)"),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        tracking = compute_poison_tracking(ep)
        assert len(tracking) == 2
        # Sorted by stacks desc
        assert tracking[0] == ("Deadly Poison", 5)
        assert tracking[1] == ("Poisoned Stab", 3)

    def test_no_poison_returns_empty(self):
        events = [_card_event("Strike", enemy_hp=-6)]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        assert compute_poison_tracking(ep) == ()


# ── Poison Tick ──────────────────────────────────────────────


class TestPoisonTick:
    def test_tick_is_unattributed_damage(self):
        events = [_card_event("Defend", block=8)]
        r = _make_round(damage_dealt=15, events=events)
        ep = _make_episode(rounds=[r])
        ticks = compute_poison_tick_per_round(ep)
        assert ticks == (15,)

    def test_no_tick_when_events_match(self):
        events = [_card_event("Strike", enemy_hp=-10)]
        r = _make_round(damage_dealt=10, events=events)
        ep = _make_episode(rounds=[r])
        ticks = compute_poison_tick_per_round(ep)
        assert ticks == (0,)

    def test_multi_round_ticks(self):
        r1 = _make_round(
            round_num=1, damage_dealt=10,
            events=[_card_event("Strike", enemy_hp=-10)],
        )
        r2 = _make_round(
            round_num=2, damage_dealt=20,
            events=[_card_event("Defend", block=5)],
        )
        ep = _make_episode(rounds=[r1, r2])
        ticks = compute_poison_tick_per_round(ep)
        assert ticks == (0, 20)


# ── Enemy Power Timeline ────────────────────────────────────


class TestEnemyPowerTimeline:
    def test_sandpit_timeline(self):
        rounds = [
            _make_round(round_num=1, enemy_powers_snapshot=(("Sandpit(4)",),)),
            _make_round(round_num=2, enemy_powers_snapshot=(("Sandpit(3)",),)),
            _make_round(round_num=3, enemy_powers_snapshot=(("Sandpit(2)",),)),
        ]
        ep = _make_episode(rounds=rounds)
        timeline = compute_enemy_power_timeline(ep)
        assert len(timeline) == 3
        assert timeline[0]["Sandpit"] == "4"
        assert timeline[2]["Sandpit"] == "2"

    def test_empty_snapshot(self):
        rounds = [_make_round(round_num=1)]
        ep = _make_episode(rounds=rounds)
        timeline = compute_enemy_power_timeline(ep)
        assert timeline == ({},)

    def test_multi_power_tracking(self):
        rounds = [
            _make_round(
                round_num=1,
                enemy_powers_snapshot=(("Sandpit(4)", "Strength(0)"),),
            ),
            _make_round(
                round_num=2,
                enemy_powers_snapshot=(("Sandpit(3)", "Strength(2)"),),
            ),
        ]
        ep = _make_episode(rounds=rounds)
        timeline = compute_enemy_power_timeline(ep)
        assert timeline[0]["Strength"] == "0"
        assert timeline[1]["Strength"] == "2"


# ── Token Attribution ────────────────────────────────────────


class TestTokenAttribution:
    def test_blade_dance_shivs(self):
        events = [
            _card_event("Blade Dance", enemy_hp=-2,
                        source_description="Add 3 Shivs into your Hand. Exhaust."),
            _card_event("Shiv", enemy_hp=-10),
            _card_event("Shiv", enemy_hp=-10),
            _card_event("Shiv", enemy_hp=-10),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        attr = compute_token_attribution(ep)
        assert "Blade Dance" in attr
        assert attr["Blade Dance"]["generated"] == 3
        assert attr["Blade Dance"]["attributed_damage"] == 30

    def test_infinite_blades_power(self):
        events = [_card_event("Shiv", enemy_hp=-12)]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        attr = compute_token_attribution(ep, active_powers=("Infinite Blades",))
        assert "Infinite Blades" in attr
        assert attr["Infinite Blades"]["generated"] == 1

    def test_mixed_sources(self):
        # R1: BD(3) + IB(1) = 4 generators, 4 Shivs played
        events = [
            _card_event("Blade Dance", source_description="Add 3 Shivs into your Hand. Exhaust."),
            _card_event("Shiv", enemy_hp=-10),
            _card_event("Shiv", enemy_hp=-10),
            _card_event("Shiv", enemy_hp=-10),
            _card_event("Shiv", enemy_hp=-10),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        attr = compute_token_attribution(ep, active_powers=("Infinite Blades",))
        assert attr["Infinite Blades"]["generated"] == 1
        assert attr["Blade Dance"]["generated"] == 3


# ── Format ───────────────────────────────────────────────────


class TestFormat:
    def test_format_includes_death_cause(self):
        r = _make_round(
            hp_start=31, hp_end=0, damage_taken=0,
            enemy_powers_snapshot=(("Sandpit(1)",),),
        )
        ep = _make_episode(won=False, hp_after=0, rounds=[r])
        text = format_analytics(ep)
        assert "Sandpit" in text

    def test_format_includes_card_descriptions(self):
        events = [
            _card_event("Blade Dance", enemy_hp=-2,
                        source_description="Add 3 Shivs into your Hand. Exhaust."),
        ]
        r = _make_round(events=events)
        ep = _make_episode(rounds=[r])
        text = format_analytics(ep)
        assert "Blade Dance" in text
        assert "Add 3 Shivs" in text

    def test_format_empty_for_no_events(self):
        r = _make_round()
        ep = _make_episode(rounds=[r])
        text = format_analytics(ep)
        assert isinstance(text, str)

    def test_format_includes_enemy_timeline(self):
        rounds = [
            _make_round(round_num=1, enemy_powers_snapshot=(("Sandpit(4)",),)),
            _make_round(round_num=2, enemy_powers_snapshot=(("Sandpit(3)",),)),
        ]
        ep = _make_episode(rounds=rounds)
        text = format_analytics(ep)
        assert "Sandpit" in text
        assert "R1:" in text
        assert "R2:" in text

    def test_format_includes_poison(self):
        events = [
            _card_event("Deadly Poison", poison_change="+Poison(5)",
                        source_description="Apply 5 Poison."),
        ]
        r = _make_round(damage_dealt=10, events=events)
        ep = _make_episode(rounds=[r])
        text = format_analytics(ep)
        assert "Deadly Poison" in text
        assert "5 stacks" in text


class TestHistoricalComparison:
    def test_returns_none_insufficient_history(self):
        from src.memory.combat_analytics import historical_comparison

        ep = _make_episode(hp_before=70, hp_after=50)
        ep = CombatEpisode(
            episode_id="target",
            enemy_key="Goblin",
            hp_before=70,
            hp_after=50,
            won=True,
            rounds=(),
        )
        # Only 2 historical — below threshold of 3
        hist = [
            CombatEpisode(episode_id=f"h{i}", enemy_key="Goblin", hp_before=70, hp_after=60, won=True, rounds=())
            for i in range(2)
        ]
        result = historical_comparison(ep, hist)
        assert result is None

    def test_worse_than_usual(self):
        from src.memory.combat_analytics import historical_comparison

        ep = CombatEpisode(
            run_id="current_run", episode_id="target", enemy_key="Goblin",
            hp_before=70, hp_after=20, won=True, rounds=(),
        )
        # Historical: 5 episodes with ~5 HP loss each (with some variance)
        hist = [
            CombatEpisode(
                run_id=f"old_run_{i}", episode_id=f"h{i}", enemy_key="Goblin",
                hp_before=70, hp_after=65 - i, won=True, rounds=(),
            )
            for i in range(5)
        ]
        result = historical_comparison(ep, hist)
        assert result is not None
        assert "WORSE_THAN_USUAL" in result

    def test_better_than_usual(self):
        from src.memory.combat_analytics import historical_comparison

        ep = CombatEpisode(
            run_id="current_run", episode_id="target", enemy_key="Boss",
            hp_before=70, hp_after=68, won=True, rounds=(),
        )
        # Historical: 5 episodes with ~30 HP loss each (mean > 5, with variance)
        hist = [
            CombatEpisode(
                run_id=f"old_run_{i}", episode_id=f"h{i}", enemy_key="Boss",
                hp_before=70, hp_after=40 - i * 2, won=True, rounds=(),
            )
            for i in range(5)
        ]
        result = historical_comparison(ep, hist)
        assert result is not None
        assert "BETTER_THAN_USUAL" in result

    def test_typical(self):
        from src.memory.combat_analytics import historical_comparison

        ep = CombatEpisode(
            run_id="current_run", episode_id="target", enemy_key="Goblin",
            hp_before=70, hp_after=60, won=True, rounds=(),
        )
        # Historical: spread around ~10 HP loss — target is within normal range
        losses_after = [59, 61, 58, 62, 60]  # losses: 11, 9, 12, 8, 10 → mean ~10
        hist = [
            CombatEpisode(
                run_id=f"old_run_{i}", episode_id=f"h{i}", enemy_key="Goblin",
                hp_before=70, hp_after=losses_after[i], won=True, rounds=(),
            )
            for i in range(5)
        ]
        result = historical_comparison(ep, hist)
        assert result is not None
        assert "TYPICAL" in result
