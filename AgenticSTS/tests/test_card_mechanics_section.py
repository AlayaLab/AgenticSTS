import json
import tempfile
from pathlib import Path

from src.postrun.context_builder import build_card_mechanics_section


def test_extracts_cards_from_log():
    log_lines = [
        json.dumps({"event": "state", "state_type": "combat", "combat": {
            "player": {"hand": [
                {"name": "Strike", "rules_text": "Deal 6 damage."},
                {"name": "Defend", "rules_text": "Gain 5 Block."},
                {"name": "Strike", "rules_text": "Deal 6 damage."},
            ], "hp": 50, "max_hp": 70, "block": 0, "energy": 3, "max_energy": 3,
               "stars": 0, "gold": 50, "powers": [], "potions": [], "relics": []},
            "enemies": [], "round": 1, "is_play_phase": True,
            "draw_pile_size": 5, "discard_pile_size": 0, "exhaust_pile_size": 0,
        }}),
        json.dumps({"event": "state", "state_type": "card_reward",
            "card_reward_details": {"card_options": [
                {"index": 0, "name": "Haze", "rules_text": "Sly. Apply 4 Poison to ALL enemies."},
            ]},
        }),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for line in log_lines:
            f.write(line + "\n")
        path = Path(f.name)
    try:
        section, seen_cards = build_card_mechanics_section(path, "test_run")
        assert "Strike" in section
        assert "Defend" in section
        assert "Haze" in section
        assert "Sly" in section  # keyword glossary triggered
        assert len(seen_cards) == 3
    finally:
        path.unlink()


def test_empty_log():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"event": "run_start"}) + "\n")
        path = Path(f.name)
    try:
        section, seen_cards = build_card_mechanics_section(path, "test_run")
        assert len(seen_cards) == 0
        assert section == ""
    finally:
        path.unlink()


def test_build_relic_context():
    log_lines = [
        json.dumps({"event": "state", "state_type": "combat", "combat": {
            "player": {"hand": [], "hp": 50, "max_hp": 70, "block": 0,
                       "energy": 3, "max_energy": 3, "stars": 0, "gold": 50,
                       "powers": [], "potions": [],
                       "relics": [
                           {"name": "Runic Pyramid", "description": "No longer discard hand."},
                           {"name": "Shuriken", "description": "Play 3 Attacks: gain 1 Str."},
                       ]},
            "enemies": [], "round": 1, "is_play_phase": True,
            "draw_pile_size": 5, "discard_pile_size": 0, "exhaust_pile_size": 0,
        }}),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for line in log_lines:
            f.write(line + "\n")
        path = Path(f.name)
    try:
        from src.postrun.context_builder import build_relic_context
        section = build_relic_context(path, "test_run")
        assert "Runic Pyramid" in section
        assert "Shuriken" in section
        assert "## Run Relics" in section
    finally:
        path.unlink()


def test_build_relic_context_empty_log():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps({"event": "run_start"}) + "\n")
        path = Path(f.name)
    try:
        from src.postrun.context_builder import build_relic_context
        section = build_relic_context(path, "test_run")
        assert section == ""
    finally:
        path.unlink()


def test_base_and_upgraded_both_shown_but_seen_names_deduped():
    """Both Strike and Strike+ appear in mechanics section, but seen_card_names dedupes to base."""
    log_lines = [
        json.dumps({"event": "state", "combat": {
            "player": {"hand": [
                {"name": "Strike+", "rules_text": "Deal 9 damage."},
                {"name": "Strike", "rules_text": "Deal 6 damage."},
            ], "hp": 50, "max_hp": 70, "block": 0, "energy": 3, "max_energy": 3,
               "stars": 0, "gold": 50, "powers": [], "potions": [], "relics": []},
            "enemies": [], "round": 1, "is_play_phase": True,
            "draw_pile_size": 5, "discard_pile_size": 0, "exhaust_pile_size": 0,
        }}),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for line in log_lines:
            f.write(line + "\n")
        path = Path(f.name)
    try:
        section, seen_cards = build_card_mechanics_section(path, "test_run")
        assert len(seen_cards) == 1  # seen_card_names dedupes to base name
        assert "Strike" in seen_cards
        # But the mechanics section shows BOTH versions
        assert "Strike: Deal 6 damage." in section
        assert "Strike+: Deal 9 damage." in section
    finally:
        path.unlink()


def test_prepared_base_and_upgraded_both_shown():
    """Both Prepared and Prepared+ appear with their own rules_text."""
    log_lines = [
        json.dumps({"event": "state", "combat": {
            "player": {"hand": [
                {"name": "Prepared", "rules_text": "Draw 1 card. Discard 1 card."},
                {"name": "Prepared+", "rules_text": "Draw 2 cards. Discard 2 cards."},
            ], "hp": 50, "max_hp": 70, "block": 0, "energy": 3, "max_energy": 3,
               "stars": 0, "gold": 50, "powers": [], "potions": [], "relics": []},
            "enemies": [], "round": 1, "is_play_phase": True,
            "draw_pile_size": 5, "discard_pile_size": 0, "exhaust_pile_size": 0,
        }}),
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for line in log_lines:
            f.write(line + "\n")
        path = Path(f.name)
    try:
        section, seen_cards = build_card_mechanics_section(path, "test_run")
        assert len(seen_cards) == 1  # seen_card_names dedupes to "Prepared"
        # Both versions shown in mechanics reference
        assert "Prepared: Draw 1 card. Discard 1 card." in section
        assert "Prepared+: Draw 2 cards. Discard 2 cards." in section
    finally:
        path.unlink()


def test_format_combat_round_digest_includes_deltas():
    from src.postrun.context_builder import format_combat_round_digest
    from unittest.mock import MagicMock

    ep = MagicMock()
    ep.won = True
    ep.hp_before = 50
    ep.hp_after = 50
    ep.floor = 5
    ep.combat_type = "monster"
    ep.enemy_key = "Slime"

    delta1 = MagicMock()
    delta1.event_type = "card_play"
    delta1.source = "Neutralize"
    delta1.block = None
    delta1.energy = None
    delta1.powers_changed = []
    delta1.cards_exhausted = []
    enemy_d1 = MagicMock()
    enemy_d1.hp = -3
    enemy_d1.powers_changed = ["Weak"]
    delta1.enemy_deltas = [enemy_d1]

    delta2 = MagicMock()
    delta2.event_type = "card_play"
    delta2.source = "Defend"
    delta2.block = 5
    delta2.energy = None
    delta2.powers_changed = []
    delta2.cards_exhausted = []
    delta2.enemy_deltas = []

    non_play = MagicMock()
    non_play.event_type = "end_turn"
    non_play.source = ""

    round1 = MagicMock()
    round1.round_num = 1
    round1.enemy_intents = ("Slime: Attack(6)",)
    round1.cards_played = ("Neutralize", "Defend")
    round1.damage_dealt = 3
    round1.damage_taken = 0
    round1.events = (delta1, non_play, delta2)

    ep.rounds = (round1,)

    text = format_combat_round_digest(ep)
    assert "Neutralize(3dmg,1Weak)" in text
    assert "Defend(+5blk)" in text
