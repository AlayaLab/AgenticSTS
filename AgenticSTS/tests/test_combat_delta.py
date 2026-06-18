"""Tests for combat delta recording system.

Covers:
- CombatDelta / EnemyDelta serialization roundtrip
- CombatDelta sparse serialization (compact output)
- CombatContext serialization roundtrip
- CombatRound backward compat (no "events" key)
- CombatEpisode backward compat (no "context" key)
- compute_combat_delta: HP/block/energy, power diff, enemy death, relic stack, edge cases
- format_combat_replay: output structure
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.brain.evolution_engine import (
    _select_smart_episodes,
    build_evolution_context,
    format_combat_replay,
)
from src.memory.combat_delta import build_combat_context, compute_combat_delta
from src.memory.models_v2 import (
    CombatContext,
    CombatDelta,
    CombatEpisode,
    CombatRound,
    EnemyDelta,
    EnemySnapshot,
    RelicSnapshot,
)

# ── Mock helpers ──────────────────────────────────────────────────


def _mock_power(power_id: str, name: str, amount: int, is_debuff: bool = False):
    p = MagicMock()
    p.power_id = power_id
    p.name = name
    p.amount = amount
    p.is_debuff = is_debuff
    return p


def _mock_enemy(
    name: str,
    index: int,
    hp: int,
    max_hp: int = 100,
    block: int = 0,
    powers=None,
    is_alive: bool = True,
    enemy_id: str = "",
):
    e = MagicMock()
    e.name = name
    e.index = index
    e.enemy_id = enemy_id or f"{name}:{index}"
    e.current_hp = hp
    e.max_hp = max_hp
    e.block = block
    e.powers = powers or []
    e.is_alive = is_alive
    return e


def _mock_relic(name: str, stack=None, description: str = ""):
    r = MagicMock()
    r.name = name
    r.stack = stack
    r.description = description
    return r


def _mock_gs(
    *,
    hp: int = 50,
    max_hp: int = 80,
    block: int = 0,
    energy: int = 3,
    powers=None,
    enemies=None,
    relics=None,
    has_combat: bool = True,
    run_hp=None,
    exhaust_lines=None,
    state_type: str = "monster",
):
    """Build a minimal mock GameState for delta tests."""
    gs = MagicMock()

    if has_combat:
        gs.raw.combat.player.current_hp = hp
        gs.raw.combat.player.max_hp = max_hp
        gs.raw.combat.player.block = block
        gs.raw.combat.player.energy = energy
        gs.raw.combat.player.powers = powers or []
        gs.raw.combat.enemies = enemies or []
        gs.raw.run.current_hp = hp
        gs.raw.run.relics = relics or []
        gs.raw.run.deck = []
    else:
        gs.raw.combat = None
        gs.raw.run.current_hp = run_hp if run_hp is not None else hp
        gs.raw.run.relics = relics or []
        gs.raw.run.deck = []

    gs.relics = relics or []
    gs.state_type = state_type

    # agent_view for exhaust pile
    if has_combat and exhaust_lines is not None:
        items = [MagicMock(line=line) for line in exhaust_lines]
        gs.raw.agent_view.combat.exhaust = items
    elif has_combat:
        gs.raw.agent_view.combat.exhaust = []
    else:
        gs.raw.agent_view = None

    return gs


# ── 1. CombatDelta serialization roundtrip ────────────────────────


def test_combat_delta_roundtrip():
    """to_dict -> from_dict produces an identical CombatDelta."""
    delta = CombatDelta(
        event_type="card_play",
        source="Strike",
        target="Toadpole[0]",
        hp=-5,
        block=3,
        energy=-1,
        powers_changed=("+Strength(2)", "-Weak"),
        enemy_deltas=(
            EnemyDelta(
                enemy_id="Toadpole:0",
                name="Toadpole",
                index=0,
                hp=-6,
                block=-2,
                powers_changed=("+Vulnerable(2)",),
                died=False,
            ),
        ),
        cards_exhausted=("Defend",),
        relic_changes=("Incense Burner: 4->5",),
    )

    d = delta.to_dict()
    restored = CombatDelta.from_dict(d)

    assert restored.event_type == delta.event_type
    assert restored.source == delta.source
    assert restored.target == delta.target
    assert restored.hp == delta.hp
    assert restored.block == delta.block
    assert restored.energy == delta.energy
    assert restored.powers_changed == delta.powers_changed
    assert len(restored.enemy_deltas) == 1
    ed = restored.enemy_deltas[0]
    assert ed.enemy_id == "Toadpole:0"
    assert ed.hp == -6
    assert ed.block == -2
    assert ed.powers_changed == ("+Vulnerable(2)",)
    assert ed.died is False
    assert restored.cards_exhausted == delta.cards_exhausted
    assert restored.relic_changes == delta.relic_changes


# ── 2. CombatDelta sparse serialization ──────────────────────────


def test_combat_delta_sparse_serialization():
    """to_dict omits None/empty fields for compact output."""
    delta = CombatDelta(
        event_type="end_turn",
        source="turn_end",
    )

    d = delta.to_dict()

    # Required fields always present
    assert "event_type" in d
    assert "source" in d

    # Optional fields should be absent
    assert "target" not in d
    assert "hp" not in d
    assert "block" not in d
    assert "energy" not in d
    assert "powers_changed" not in d
    assert "enemy_deltas" not in d
    assert "cards_exhausted" not in d
    assert "relic_changes" not in d


def test_enemy_delta_sparse_serialization():
    """EnemyDelta.to_dict omits None/empty/False fields."""
    ed = EnemyDelta(
        enemy_id="Slime:0",
        name="Slime",
        index=0,
    )

    d = ed.to_dict()

    assert "enemy_id" in d
    assert "name" in d
    assert "index" in d
    # Optional fields absent
    assert "hp" not in d
    assert "block" not in d
    assert "powers_changed" not in d
    assert "died" not in d


# ── 3. CombatContext serialization roundtrip ─────────────────────


def test_combat_context_roundtrip():
    """CombatContext with relics (including stack) and enemy powers roundtrips."""
    ctx = CombatContext(
        enemy_key="multi:Slime+Fungus",
        character="Ironclad",
        combat_type="monster",
        relics=(
            RelicSnapshot(name="Incense Burner", description="Every 6 turns gain Intangible", stack=4),
            RelicSnapshot(name="Burning Blood", description="Heal 6 HP after combat"),
        ),
        starting_hp=65,
        starting_max_hp=80,
        deck_cards=("Strike", "Strike", "Defend", "Bash"),
        enemy_lineup=(
            EnemySnapshot(
                name="Slime",
                index=0,
                enemy_id="Slime:0",
                hp=30,
                max_hp=30,
                powers=("Thorns(2)",),
            ),
            EnemySnapshot(
                name="Fungus",
                index=1,
                enemy_id="Fungus:1",
                hp=40,
                max_hp=40,
                powers=(),
            ),
        ),
    )

    d = ctx.to_dict()
    restored = CombatContext.from_dict(d)

    assert restored.enemy_key == "multi:Slime+Fungus"
    assert restored.character == "Ironclad"
    assert restored.combat_type == "monster"
    assert restored.starting_hp == 65
    assert restored.starting_max_hp == 80
    assert restored.deck_cards == ("Strike", "Strike", "Defend", "Bash")

    # Relics
    assert len(restored.relics) == 2
    assert restored.relics[0].name == "Incense Burner"
    assert restored.relics[0].stack == 4
    assert restored.relics[0].description == "Every 6 turns gain Intangible"
    assert restored.relics[1].name == "Burning Blood"
    assert restored.relics[1].stack is None

    # Enemy lineup
    assert len(restored.enemy_lineup) == 2
    assert restored.enemy_lineup[0].name == "Slime"
    assert restored.enemy_lineup[0].powers == ("Thorns(2)",)
    assert restored.enemy_lineup[1].name == "Fungus"
    assert restored.enemy_lineup[1].powers == ()


def test_relic_snapshot_sparse():
    """RelicSnapshot.to_dict omits empty description and None stack."""
    r = RelicSnapshot(name="Akabeko")
    d = r.to_dict()

    assert d == {"name": "Akabeko"}
    assert "description" not in d
    assert "stack" not in d


# ── 4. CombatRound backward compat (no "events" key) ────────────


def test_combat_round_from_dict_no_events():
    """Old CombatRound dicts without 'events' key load with events=()."""
    old_data = {
        "round_num": 1,
        "energy_available": 3,
        "energy_used": 2,
        "hp_start": 50,
        "hp_end": 42,
        "block_gained": 5,
        "enemy_intents": ["Attack 12"],
        "cards_played": ["Strike", "Defend"],
        "potions_used": [],
        "damage_dealt": 6,
        "damage_taken": 8,
        # No "events" key at all
    }

    rnd = CombatRound.from_dict(old_data)

    assert rnd.round_num == 1
    assert rnd.energy_available == 3
    assert rnd.energy_used == 2
    assert rnd.hp_start == 50
    assert rnd.hp_end == 42
    assert rnd.block_gained == 5
    assert rnd.enemy_intents == ("Attack 12",)
    assert rnd.cards_played == ("Strike", "Defend")
    assert rnd.potions_used == ()
    assert rnd.damage_dealt == 6
    assert rnd.damage_taken == 8
    assert rnd.events == ()  # backward compat


# ── 5. CombatEpisode backward compat (no "context" key) ─────────


def test_combat_episode_from_dict_no_context():
    """Old CombatEpisode dicts without 'context' key load with context=None."""
    old_data = {
        "episode_id": "abc123",
        "run_id": "run_001",
        "floor": 5,
        "act": 1,
        "enemy_key": "Kin Priest",
        "character": "Regent",
        "combat_type": "boss",
        "rounds": [],
        "hp_before": 60,
        "hp_after": 35,
        "won": True,
        "hp_delta": -25,
        "total_damage_dealt": 100,
        "total_damage_taken": 25,
        "total_cards_played": 12,
        "deck_size": 20,
        "relics": ["Burning Blood"],
        "timestamp": 1700000000.0,
        # No "context" key at all
    }

    ep = CombatEpisode.from_dict(old_data)

    assert ep.episode_id == "abc123"
    assert ep.run_id == "run_001"
    assert ep.floor == 5
    assert ep.enemy_key == "Kin Priest"
    assert ep.character == "Regent"
    assert ep.combat_type == "boss"
    assert ep.rounds == ()
    assert ep.hp_before == 60
    assert ep.hp_after == 35
    assert ep.won is True
    assert ep.hp_delta == -25
    assert ep.relics == ("Burning Blood",)
    assert ep.context is None  # backward compat


def test_combat_episode_with_context_roundtrip():
    """CombatEpisode including context field roundtrips."""
    ctx = CombatContext(
        enemy_key="Toadpole",
        character="Silent",
        combat_type="monster",
        relics=(RelicSnapshot(name="Ring of the Snake"),),
        starting_hp=70,
        starting_max_hp=70,
        deck_cards=("Neutralize", "Survivor", "Strike", "Defend"),
        enemy_lineup=(
            EnemySnapshot(name="Toadpole", index=0, enemy_id="Toadpole:0", hp=50, max_hp=50),
        ),
    )
    ep = CombatEpisode(
        episode_id="ep_001",
        run_id="run_001",
        floor=2,
        act=1,
        enemy_key="Toadpole",
        character="Silent",
        combat_type="monster",
        rounds=(),
        hp_before=70,
        hp_after=60,
        won=True,
        hp_delta=-10,
        context=ctx,
    )

    d = ep.to_dict()
    assert "context" in d

    restored = CombatEpisode.from_dict(d)
    assert restored.context is not None
    assert restored.context.enemy_key == "Toadpole"
    assert restored.context.character == "Silent"
    assert len(restored.context.relics) == 1


# ── 6. compute_combat_delta: basic HP/block/energy change ────────


def test_compute_delta_hp_block_energy():
    """Delta captures HP, block, energy changes between pre and post states."""
    pre = _mock_gs(hp=50, block=0, energy=3)
    post = _mock_gs(hp=45, block=5, energy=1)

    delta = compute_combat_delta(pre, post, "card_play", "Iron Wave")

    assert delta is not None
    assert delta.event_type == "card_play"
    assert delta.source == "Iron Wave"
    assert delta.hp == -5       # 45 - 50
    assert delta.block == 5     # 5 - 0
    assert delta.energy == -2   # 1 - 3


def test_compute_delta_no_change():
    """When HP/block/energy unchanged, those fields are None."""
    pre = _mock_gs(hp=50, block=5, energy=2)
    post = _mock_gs(hp=50, block=5, energy=2)

    delta = compute_combat_delta(pre, post, "card_play", "Shrug It Off")

    assert delta is not None
    assert delta.hp is None
    assert delta.block is None
    assert delta.energy is None


# ── 7. compute_combat_delta: power diff ──────────────────────────


def test_compute_delta_power_diff():
    """Power changes: amount change and new power detected."""
    pre_powers = [_mock_power("str", "Strength", 3)]
    post_powers = [
        _mock_power("str", "Strength", 5),
        _mock_power("weak", "Weak", 1),
    ]

    pre = _mock_gs(powers=pre_powers)
    post = _mock_gs(powers=post_powers)

    delta = compute_combat_delta(pre, post, "card_play", "Flex")

    assert delta is not None
    # Strength changed from 3 to 5
    assert any("Strength" in p and "3" in p and "5" in p for p in delta.powers_changed)
    # New Weak(1) added
    assert any("+Weak(1)" == p for p in delta.powers_changed)


def test_compute_delta_power_removed():
    """Power disappearing shows as -PowerName."""
    pre_powers = [_mock_power("vuln", "Vulnerable", 2)]
    post_powers = []

    pre = _mock_gs(powers=pre_powers)
    post = _mock_gs(powers=post_powers)

    delta = compute_combat_delta(pre, post, "end_turn", "turn_end")

    assert delta is not None
    assert "-Vulnerable" in delta.powers_changed


# ── 8. compute_combat_delta: enemy death ─────────────────────────


def test_compute_delta_enemy_death():
    """Enemy disappearing from post-state while combat continues means died=True."""
    enemy_pre = _mock_enemy("Toadpole", 0, hp=5)
    # Post state: combat still active but enemy gone
    pre = _mock_gs(enemies=[enemy_pre])
    post = _mock_gs(enemies=[])  # empty list = enemy disappeared

    delta = compute_combat_delta(pre, post, "card_play", "Strike")

    assert delta is not None
    assert len(delta.enemy_deltas) == 1
    assert delta.enemy_deltas[0].died is True
    assert delta.enemy_deltas[0].name == "Toadpole"


def test_compute_delta_enemy_hp_change():
    """Enemy taking damage shows negative hp delta."""
    enemy_pre = _mock_enemy("Slime", 0, hp=30)
    enemy_post = _mock_enemy("Slime", 0, hp=24)

    pre = _mock_gs(enemies=[enemy_pre])
    post = _mock_gs(enemies=[enemy_post])

    delta = compute_combat_delta(pre, post, "card_play", "Strike")

    assert delta is not None
    assert len(delta.enemy_deltas) == 1
    assert delta.enemy_deltas[0].hp == -6  # 24 - 30


def test_compute_delta_enemy_alive_to_dead_flag():
    """Enemy still in list but is_alive changed from True to False."""
    enemy_pre = _mock_enemy("Cultist", 0, hp=10, is_alive=True)
    enemy_post = _mock_enemy("Cultist", 0, hp=0, is_alive=False)

    pre = _mock_gs(enemies=[enemy_pre])
    post = _mock_gs(enemies=[enemy_post])

    delta = compute_combat_delta(pre, post, "card_play", "Bash")

    assert delta is not None
    assert len(delta.enemy_deltas) == 1
    ed = delta.enemy_deltas[0]
    assert ed.died is True
    assert ed.hp == -10  # 0 - 10


# ── 9. compute_combat_delta: relic stack change ──────────────────


def test_compute_delta_relic_stack_change():
    """Relic counter changing between pre and post shows in relic_changes."""
    relic_pre = _mock_relic("Incense Burner", stack=4)
    relic_post = _mock_relic("Incense Burner", stack=5)

    pre = _mock_gs(relics=[relic_pre])
    post = _mock_gs(relics=[relic_post])

    delta = compute_combat_delta(pre, post, "end_turn", "turn_end")

    assert delta is not None
    assert len(delta.relic_changes) == 1
    assert "Incense Burner" in delta.relic_changes[0]
    assert "4" in delta.relic_changes[0]
    assert "5" in delta.relic_changes[0]


def test_compute_delta_relic_no_change():
    """Relic with unchanged stack produces no relic_changes."""
    relic_pre = _mock_relic("Burning Blood", stack=None)
    relic_post = _mock_relic("Burning Blood", stack=None)

    pre = _mock_gs(relics=[relic_pre])
    post = _mock_gs(relics=[relic_post])

    delta = compute_combat_delta(pre, post, "card_play", "Strike")

    assert delta is not None
    assert len(delta.relic_changes) == 0


# ── 10. compute_combat_delta: no combat in either state ──────────


def test_compute_delta_no_combat_returns_none():
    """Both states with raw.combat = None should return None."""
    pre = _mock_gs(has_combat=False)
    post = _mock_gs(has_combat=False)

    delta = compute_combat_delta(pre, post, "card_play", "Strike")

    assert delta is None


# ── 11. compute_combat_delta: cross-phase (combat -> reward) ─────


def test_compute_delta_cross_phase_combat_to_reward():
    """Pre has combat, post has raw.combat=None but run HP set. Still computes HP delta."""
    pre = _mock_gs(hp=50, block=5, energy=1)
    post = _mock_gs(has_combat=False, run_hp=42)

    delta = compute_combat_delta(pre, post, "end_turn", "turn_end")

    assert delta is not None
    # HP delta: post run HP (42) - pre combat HP (50) = -8
    assert delta.hp == -8
    # block goes to 0 (post has no combat, defaults to 0)
    assert delta.block == -5
    # energy goes to 0
    assert delta.energy == -1


def test_compute_delta_cross_phase_no_pre_combat():
    """Pre has no combat, post has combat. Should still compute from run HP."""
    pre = _mock_gs(has_combat=False, run_hp=60)
    post = _mock_gs(hp=60, block=0, energy=3)

    delta = compute_combat_delta(pre, post, "card_play", "Strike")

    assert delta is not None
    # HP unchanged (both 60)
    assert delta.hp is None
    # Energy went from 0 (no combat) to 3
    assert delta.energy == 3


# ── 11b. compute_combat_delta with REAL Pydantic models (Bug A2) ─


def test_compute_delta_card_play_with_real_pydantic_state():
    """Bug A2 (2026-04-30): compute_combat_delta crashed on the real
    upstream payload for any event_type='card_play'. The MagicMock-based
    tests above missed this because MagicMock auto-generates the missing
    `pre_combat.player.hand` attribute. With real Pydantic models,
    `RawCombatPlayerPayload` has no `hand` field — it lives on
    `RawCombatPayload` (parent). The exception was swallowed by
    `_record_combat_delta`'s try/except, silently dropping every card_play
    event from STM. Persisted episodes therefore had 0 card_play events
    and per-card stats (total_damage, total_block) stayed at 0 across runs.

    This test uses real parse_state to ensure compute_combat_delta works
    against the actual payload shape, not a MagicMock fixture.
    """
    from src.state.state_parser import parse_state

    pre_raw = {
        "combat": {
            "player": {
                "current_hp": 80, "max_hp": 80, "energy": 3, "block": 0,
                "powers": [],
            },
            "hand": [
                {"index": 0, "name": "Strike", "rules_text": "Deal 6 damage."},
            ],
            "enemies": [
                {"index": 0, "name": "TestEnemy", "current_hp": 50, "max_hp": 50,
                 "block": 0, "powers": [], "is_alive": True, "intents": []},
            ],
        },
        "agent_view": {"combat": {"exhaust": []}},
        "run": {"floor": 1, "current_hp": 80, "max_hp": 80, "relics": []},
    }
    post_raw = {
        "combat": {
            "player": {
                "current_hp": 80, "max_hp": 80, "energy": 2, "block": 0,
                "powers": [],
            },
            "hand": [],
            "enemies": [
                {"index": 0, "name": "TestEnemy", "current_hp": 44, "max_hp": 50,
                 "block": 0, "powers": [], "is_alive": True, "intents": []},
            ],
        },
        "agent_view": {"combat": {"exhaust": []}},
        "run": {"floor": 1, "current_hp": 80, "max_hp": 80, "relics": []},
    }

    pre = parse_state(pre_raw)
    post = parse_state(post_raw)

    # Must not raise AttributeError despite event_type='card_play'.
    delta = compute_combat_delta(pre, post, "card_play", "Strike", target=None)

    assert delta is not None
    assert delta.event_type == "card_play"
    assert delta.source == "Strike"
    # Energy went 3 → 2 (Strike costs 1)
    assert delta.energy == -1
    # Enemy took 6 damage (50 → 44)
    assert len(delta.enemy_deltas) == 1
    assert delta.enemy_deltas[0].hp == -6
    assert delta.enemy_deltas[0].name == "TestEnemy"
    # source_description should be populated from the played card's rules_text
    assert "Deal 6 damage" in delta.source_description


# ── 12. format_combat_replay: basic output ───────────────────────


def test_format_combat_replay_basic():
    """format_combat_replay includes header, context, and round details."""
    ctx = CombatContext(
        enemy_key="Toadpole",
        character="Ironclad",
        combat_type="monster",
        relics=(RelicSnapshot(name="Burning Blood", stack=None),),
        starting_hp=70,
        starting_max_hp=80,
        deck_cards=("Strike", "Strike", "Defend", "Bash"),
        enemy_lineup=(
            EnemySnapshot(
                name="Toadpole",
                index=0,
                enemy_id="Toadpole:0",
                hp=48,
                max_hp=48,
                powers=(),
            ),
        ),
    )

    delta1 = CombatDelta(
        event_type="card_play",
        source="Strike",
        target="Toadpole[0]",
        energy=-1,
        enemy_deltas=(
            EnemyDelta(enemy_id="Toadpole:0", name="Toadpole", index=0, hp=-6),
        ),
    )

    rnd = CombatRound(
        round_num=1,
        energy_available=3,
        energy_used=1,
        hp_start=70,
        hp_end=62,
        block_gained=0,
        enemy_intents=("Attack 8",),
        cards_played=("Strike",),
        damage_dealt=6,
        damage_taken=8,
        events=(delta1,),
    )

    ep = CombatEpisode(
        episode_id="ep_test",
        run_id="run_test",
        floor=3,
        act=1,
        enemy_key="Toadpole",
        character="Ironclad",
        combat_type="monster",
        rounds=(rnd,),
        hp_before=70,
        hp_after=62,
        won=True,
        hp_delta=-8,
        context=ctx,
    )

    output = format_combat_replay(ep)

    # Header
    assert "Toadpole" in output
    assert "Floor 3" in output
    assert "monster" in output

    # Context: relics
    assert "Burning Blood" in output

    # Context: deck
    assert "Deck (4)" in output

    # Context: enemies
    assert "HP=48/48" in output

    # Round header
    assert "Round 1" in output

    # Intent
    assert "Attack 8" in output

    # Delta line (source name appears)
    assert "Strike" in output


def test_format_combat_replay_no_context():
    """Replay works with context=None (old episodes)."""
    rnd = CombatRound(
        round_num=1,
        energy_available=3,
        energy_used=2,
        hp_start=50,
        hp_end=42,
        block_gained=5,
        enemy_intents=("Attack 12",),
        cards_played=("Strike", "Defend"),
        damage_dealt=6,
        damage_taken=8,
    )

    ep = CombatEpisode(
        episode_id="ep_old",
        run_id="run_old",
        floor=5,
        act=1,
        enemy_key="Slime",
        character="Silent",
        combat_type="monster",
        rounds=(rnd,),
        hp_before=50,
        hp_after=42,
        won=True,
        hp_delta=-8,
        context=None,
    )

    output = format_combat_replay(ep)

    assert "Slime" in output
    assert "Round 1" in output
    # Fallback aggregate summary (no events)
    assert "cards:" in output
    assert "Strike, Defend" in output


def test_format_combat_replay_max_rounds():
    """Only last max_rounds rounds are shown when episode has many rounds."""
    rounds = tuple(
        CombatRound(
            round_num=i,
            energy_available=3,
            energy_used=2,
            hp_start=50 - i,
            hp_end=50 - i - 2,
            block_gained=0,
            enemy_intents=("Attack 5",),
            cards_played=("Strike",),
            damage_dealt=6,
            damage_taken=2,
        )
        for i in range(1, 11)  # 10 rounds
    )

    ep = CombatEpisode(
        episode_id="ep_long",
        run_id="run_long",
        floor=10,
        act=2,
        enemy_key="Boss",
        character="Defect",
        combat_type="boss",
        rounds=rounds,
        hp_before=50,
        hp_after=30,
        won=True,
        hp_delta=-20,
        context=None,
    )

    output = format_combat_replay(ep, max_rounds=3)

    # Only rounds 8, 9, 10 should appear (last 3)
    assert "Round 8" in output
    assert "Round 9" in output
    assert "Round 10" in output
    # Early rounds should be trimmed (use word boundary via "Round N\n")
    assert "### Round 1\n" not in output
    assert "### Round 7\n" not in output


# ── Exhaust pile detection ───────────────────────────────────────


def test_compute_delta_exhaust_pile():
    """Cards exhausted between pre and post states are captured."""
    pre = _mock_gs(exhaust_lines=["Strike", "Defend"])
    post = _mock_gs(exhaust_lines=["Strike", "Defend", "Bash"])

    delta = compute_combat_delta(pre, post, "card_play", "Bash")

    assert delta is not None
    assert delta.cards_exhausted == ("Bash",)


def test_compute_delta_exhaust_pile_empty():
    """No exhaust change produces empty cards_exhausted."""
    pre = _mock_gs(exhaust_lines=["Strike"])
    post = _mock_gs(exhaust_lines=["Strike"])

    delta = compute_combat_delta(pre, post, "card_play", "Defend")

    assert delta is not None
    assert delta.cards_exhausted == ()


# ── build_combat_context ─────────────────────────────────────────


def test_build_combat_context_basic():
    """build_combat_context captures relics, enemies, deck from GameState."""
    enemy = _mock_enemy("Toadpole", 0, hp=48, max_hp=48, powers=[], is_alive=True)
    relic = MagicMock()
    relic.name = "Burning Blood"
    relic.description = "Heal 6 HP"
    relic.stack = None

    deck_card = MagicMock()
    deck_card.name = "Strike"

    gs = MagicMock()
    gs.raw.combat.player.current_hp = 70
    gs.raw.combat.player.max_hp = 80
    gs.raw.combat.enemies = [enemy]
    gs.raw.run.relics = [relic]
    gs.raw.run.deck = [deck_card]
    gs.state_type = "monster"

    ctx = build_combat_context(gs, "Ironclad")

    assert ctx is not None
    assert ctx.character == "Ironclad"
    assert ctx.enemy_key == "Toadpole"
    assert ctx.combat_type == "monster"
    assert ctx.starting_hp == 70
    assert ctx.starting_max_hp == 80
    assert len(ctx.relics) == 1
    assert ctx.relics[0].name == "Burning Blood"
    assert ctx.relics[0].description == "Heal 6 HP"
    assert ctx.deck_cards == ("Strike",)
    assert len(ctx.enemy_lineup) == 1
    assert ctx.enemy_lineup[0].name == "Toadpole"


def test_build_combat_context_no_combat():
    """build_combat_context returns None when not in combat."""
    gs = MagicMock()
    gs.raw.combat = None

    ctx = build_combat_context(gs, "Silent")

    assert ctx is None


def test_build_combat_context_multi_enemy():
    """Multi-enemy produces 'multi:' prefixed enemy_key."""
    e1 = _mock_enemy("Slime", 0, hp=20, is_alive=True)
    e2 = _mock_enemy("Fungus", 1, hp=30, is_alive=True)

    gs = MagicMock()
    gs.raw.combat.player.current_hp = 60
    gs.raw.combat.player.max_hp = 80
    gs.raw.combat.enemies = [e1, e2]
    gs.raw.run.relics = []
    gs.raw.run.deck = []
    gs.state_type = "monster"

    ctx = build_combat_context(gs, "Defect")

    assert ctx is not None
    assert ctx.enemy_key == "multi:Fungus+Slime"  # sorted alphabetically
    assert len(ctx.enemy_lineup) == 2


# ── _select_smart_episodes tests ──────────────────────────────


def _make_episode(
    episode_id: str,
    run_id: str = "test_run",
    floor: int = 5,
    hp_delta: int = -10,
    won: bool = True,
    combat_type: str = "monster",
    has_events: bool = True,
) -> CombatEpisode:
    """Build a CombatEpisode with optional events for replay selection tests."""
    delta = CombatDelta(event_type="card_play", source="Strike")
    events = (delta,) if has_events else ()
    rnd = CombatRound(
        round_num=1,
        energy_available=3,
        energy_used=1,
        hp_start=50,
        hp_end=50 + hp_delta,
        block_gained=0,
        enemy_intents=("Attack 8",),
        cards_played=("Strike",),
        damage_dealt=6,
        damage_taken=abs(hp_delta),
        events=events,
    )
    return CombatEpisode(
        episode_id=episode_id,
        run_id=run_id,
        floor=floor,
        act=1,
        enemy_key="TestEnemy",
        character="Silent",
        combat_type=combat_type,
        rounds=(rnd,),
        hp_before=50,
        hp_after=50 + hp_delta,
        won=won,
        hp_delta=hp_delta,
    )


def test_select_smart_episodes_prioritization():
    """Selects death combat, boss, and elite — skips regular monsters without anomaly."""
    ep_a = _make_episode("A", floor=10, hp_delta=-30, won=False, combat_type="monster")
    ep_b = _make_episode("B", floor=5, hp_delta=-40, won=True, combat_type="elite")
    ep_c = _make_episode("C", floor=8, hp_delta=-10, won=True, combat_type="boss")
    ep_d = _make_episode("D", floor=3, hp_delta=-5, won=True, combat_type="monster")

    mm = MagicMock()
    mm.combat_store.get_all.return_value = [ep_a, ep_b, ep_c, ep_d]

    result = _select_smart_episodes(mm, "test_run")

    result_ids = {ep.episode_id for ep in result}
    assert "A" in result_ids  # death combat
    assert "B" in result_ids  # elite
    assert "C" in result_ids  # boss
    assert "D" not in result_ids  # boring monster, not selected


def test_select_smart_episodes_skips_empty_events():
    """Episodes with no events in any round are excluded."""
    ep_a = _make_episode("A", floor=10, hp_delta=-30, won=False, has_events=False)
    ep_b = _make_episode("B", floor=5, hp_delta=-40, won=True, has_events=True, combat_type="elite")
    ep_c = _make_episode("C", floor=8, hp_delta=-10, won=True, combat_type="boss", has_events=True)

    mm = MagicMock()
    mm.combat_store.get_all.return_value = [ep_a, ep_b, ep_c]

    result = _select_smart_episodes(mm, "test_run")

    result_ids = {ep.episode_id for ep in result}
    # A has no events so it should be excluded even though it's a death combat
    assert "A" not in result_ids
    assert "B" in result_ids  # elite (with events)
    assert "C" in result_ids  # boss (with events)


def test_build_evolution_context_includes_replays():
    """build_evolution_context includes Combat Replays section when memory_manager has episodes."""
    ep = _make_episode(
        "ep_replay",
        run_id="test_run",
        floor=5,
        hp_delta=-15,
        won=True,
        combat_type="boss",  # boss is always selected
    )

    run_state = MagicMock()
    run_state.character = "Silent"
    run_state.victory = False
    run_state.final_floor = 10
    run_state.run_id = "test_run"
    run_state.fitness.return_value = 5.0
    run_state.decisions = []
    run_state.duration_seconds = 0.0

    mm = MagicMock()
    mm.combat_store.get_all.return_value = [ep]
    # Prevent guide_store from producing MagicMock cascade errors
    mm.guide_store = None
    mm.card_memory_store = None

    context = build_evolution_context(run_state, None, mm)

    assert "## Selected Replay Package" in context


# ── New field serialization tests ────────────────────────────────


class TestNewFieldSerialization:
    """Tests for source_description, player_powers, enemy_powers_snapshot."""

    def test_combat_delta_source_description_roundtrip(self):
        delta = CombatDelta(
            event_type="card_play",
            source="Blade Dance",
            source_description="Add 3 Shivs into your Hand. Exhaust.",
        )
        d = delta.to_dict()
        assert d["source_description"] == "Add 3 Shivs into your Hand. Exhaust."
        restored = CombatDelta.from_dict(d)
        assert restored.source_description == delta.source_description

    def test_combat_delta_source_description_backward_compat(self):
        d = {"event_type": "card_play", "source": "Strike"}
        restored = CombatDelta.from_dict(d)
        assert restored.source_description == ""

    def test_combat_delta_source_description_sparse(self):
        """Empty source_description is not serialized (sparse output)."""
        delta = CombatDelta(event_type="card_play", source="Strike")
        d = delta.to_dict()
        assert "source_description" not in d

    def test_combat_context_player_powers_roundtrip(self):
        ctx = CombatContext(
            enemy_key="Nibbit",
            character="the silent",
            player_powers=("Noxious Fumes(2)", "Envenom(1)"),
        )
        d = ctx.to_dict()
        assert d["player_powers"] == ["Noxious Fumes(2)", "Envenom(1)"]
        restored = CombatContext.from_dict(d)
        assert restored.player_powers == ctx.player_powers

    def test_combat_context_player_powers_backward_compat(self):
        d = {"enemy_key": "Nibbit", "character": "the silent"}
        restored = CombatContext.from_dict(d)
        assert restored.player_powers == ()

    def test_combat_round_enemy_powers_snapshot_roundtrip(self):
        rnd = CombatRound(
            round_num=1,
            enemy_powers_snapshot=(("Sandpit(4)", "Strength(2)"),),
        )
        d = rnd.to_dict()
        assert d["enemy_powers_snapshot"] == [["Sandpit(4)", "Strength(2)"]]
        restored = CombatRound.from_dict(d)
        assert restored.enemy_powers_snapshot == rnd.enemy_powers_snapshot

    def test_combat_round_enemy_powers_snapshot_backward_compat(self):
        d = {"round_num": 1, "damage_dealt": 10}
        restored = CombatRound.from_dict(d)
        assert restored.enemy_powers_snapshot == ()

    def test_combat_round_enemy_powers_snapshot_sparse(self):
        """Empty snapshot is not serialized."""
        rnd = CombatRound(round_num=1)
        d = rnd.to_dict()
        assert "enemy_powers_snapshot" not in d
