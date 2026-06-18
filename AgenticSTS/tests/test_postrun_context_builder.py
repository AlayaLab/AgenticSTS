from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import config
from src.memory.models_v2 import CombatDelta, CombatEpisode, CombatRound
from src.postrun.context_builder import build_decision_digest, build_replay_package
from src.state.run_state import RunState


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _state_event(
    *,
    step: int,
    floor: int,
    state_type: str,
    hp: int,
    gold: int,
    deck: list[str],
) -> dict:
    return {
        "event": "state",
        "step": step,
        "floor": floor,
        "state_type": state_type,
        "hp": hp,
        "player": {"gold": gold},
        "deck_size": len(deck),
        "deck": [{"name": card, "upgraded": card.endswith("+")} for card in deck],
    }


def _decision_event(
    *,
    step: int,
    floor: int,
    state_type: str,
    action: str,
    reasoning: str,
    source: str = "llm",
    **extra: object,
) -> dict:
    payload = {"action": action, **extra}
    return {
        "event": "decision",
        "step": step,
        "floor": floor,
        "state_type": state_type,
        "action": payload,
        "reasoning": reasoning,
        "source": source,
    }


def test_build_decision_digest_uses_all_noncombat_decisions_and_state_deltas(tmp_path: Path):
    run_id = "digest_test"
    log_path = tmp_path / f"run_{run_id}.jsonl"
    _write_log(
        log_path,
        [
            {"event": "run_start", "run_id": run_id},
            _state_event(step=1, floor=1, state_type="event", hp=70, gold=99, deck=["Strike", "Defend"]),
            _decision_event(
                step=1,
                floor=1,
                state_type="event",
                action="choose_event_option",
                option_index=2,
                reasoning="Take the gold and curse.",
            ),
            _state_event(
                step=2,
                floor=1,
                state_type="event",
                hp=70,
                gold=432,
                deck=["Strike", "Defend", "Greed"],
            ),
            _decision_event(
                step=2,
                floor=1,
                state_type="event",
                action="choose_event_option",
                option_index=0,
                reasoning="Only option: proceed.",
                source="auto",
            ),
            _state_event(
                step=3,
                floor=1,
                state_type="map",
                hp=70,
                gold=432,
                deck=["Strike", "Defend", "Greed"],
            ),
            _state_event(
                step=4,
                floor=2,
                state_type="card_reward",
                hp=66,
                gold=432,
                deck=["Strike", "Defend", "Greed"],
            ),
            _decision_event(
                step=4,
                floor=2,
                state_type="card_reward",
                action="choose_reward_card",
                option_index=1,
                reasoning="Need stronger frontload.",
            ),
            _state_event(
                step=5,
                floor=2,
                state_type="map",
                hp=66,
                gold=432,
                deck=["Strike", "Defend", "Greed", "Dagger Spray"],
            ),
        ],
    )
    combat_episode = CombatEpisode(
        run_id=run_id,
        enemy_key="Jaw Worm",
        floor=2,
        combat_type="monster",
        hp_before=70,
        hp_after=66,
        rounds=(CombatRound(round_num=1, cards_played=("Strike",), damage_dealt=6, damage_taken=4),),
    )
    run_state = RunState(run_id=run_id, character="silent", final_floor=2)

    with patch.object(config, "LOG_DIR", str(tmp_path)):
        digest = build_decision_digest(run_state, combat_episodes=[combat_episode])

    assert len(digest.non_combat_decisions) == 3
    assert digest.text.count("F1 [event]") == 2
    assert "Gold 99->432" in digest.text
    assert "Deck 2->3" in digest.text
    assert "Greed" in digest.text
    assert "Dagger Spray" in digest.text
    assert "Jaw Worm" in digest.text


def test_build_replay_package_selects_mandatory_and_anomaly_entries():
    history = [
        CombatEpisode(run_id="hist1", enemy_key="Cultist", floor=3, combat_type="monster", hp_before=70, hp_after=68),
        CombatEpisode(run_id="hist2", enemy_key="Cultist", floor=7, combat_type="monster", hp_before=70, hp_after=67),
        CombatEpisode(run_id="hist3", enemy_key="Cultist", floor=11, combat_type="monster", hp_before=70, hp_after=66),
    ]
    current = [
        CombatEpisode(
            run_id="run_now",
            enemy_key="Act Boss",
            floor=40,
            combat_type="boss",
            hp_before=52,
            hp_after=31,
            rounds=(CombatRound(round_num=1, events=(CombatDelta(event_type="card_play", source="Strike"),)),),
        ),
        CombatEpisode(
            run_id="run_now",
            enemy_key="Elite Slaver",
            floor=20,
            combat_type="elite",
            hp_before=65,
            hp_after=54,
            rounds=(CombatRound(round_num=1, events=(CombatDelta(event_type="card_play", source="Defend"),)),),
        ),
        CombatEpisode(
            run_id="run_now",
            enemy_key="Cultist",
            floor=5,
            combat_type="monster",
            hp_before=70,
            hp_after=40,
            rounds=(CombatRound(round_num=1, events=(CombatDelta(event_type="card_play", source="Strike"),)),),
        ),
        CombatEpisode(
            run_id="run_now",
            enemy_key="Final Boss",
            floor=51,
            combat_type="boss",
            hp_before=31,
            hp_after=0,
            won=False,
            terminal_reason="loss",
            rounds=(CombatRound(round_num=1, events=(CombatDelta(event_type="card_play", source="Defend"),)),),
        ),
    ]
    combat_store = MagicMock()
    combat_store.get_all.return_value = [*history, *current]
    memory_manager = SimpleNamespace(combat_store=combat_store)

    replay_package = build_replay_package(memory_manager, "run_now", replay_token_budget=50000)

    enemy_keys = [entry.episode.enemy_key for entry in replay_package.entries]
    assert "Act Boss" in enemy_keys
    assert "Elite Slaver" in enemy_keys
    assert "Final Boss" in enemy_keys
    cultist_entry = next(entry for entry in replay_package.entries if entry.episode.enemy_key == "Cultist")
    assert cultist_entry.anomaly_label == "WORSE_THAN_USUAL"
    assert cultist_entry.comparator_episode is not None
    assert cultist_entry.comparator_reason
