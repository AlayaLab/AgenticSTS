import pytest

from src.memory.models_v2 import CombatEpisode
from src.skills.mistake_discovery import loss_ratio, baseline_a, baseline_b


def _ep(hp_before=100, dmg=10, enemy_key="Rat", act=1, combat_type="monster",
        character="silent", run_id="r"):
    return CombatEpisode(
        run_id=run_id, enemy_key=enemy_key, act=act, combat_type=combat_type,
        character=character, hp_before=hp_before, total_damage_taken=dmg,
    )


def test_loss_ratio_basic():
    ep = _ep(hp_before=100, dmg=30)
    assert loss_ratio(ep) == 0.30


def test_loss_ratio_zero_hp_safe():
    ep = _ep(hp_before=0, dmg=5)
    # max(hp, 1) guard
    assert loss_ratio(ep) == 5.0


def test_baseline_a_median_over_history():
    # 5 episodes for Sewer Clam, loss_ratios 0.1/0.2/0.3/0.4/0.5
    history = [_ep(hp_before=100, dmg=r, enemy_key="Sewer Clam") for r in (10,20,30,40,50)]
    val = baseline_a(history)
    assert val == 0.30


def test_baseline_a_inactive_below_three():
    assert baseline_a([_ep(), _ep()]) is None


def test_baseline_b_mean_recent_pool():
    pool = [_ep(hp_before=100, dmg=r) for r in (20, 20, 30)]  # 0.20, 0.20, 0.30
    val = baseline_b(pool)
    assert val == pytest.approx(0.2333, abs=1e-3)


def test_baseline_b_inactive_below_three():
    assert baseline_b([_ep(), _ep()]) is None


from src.skills.mistake_discovery import is_mistake_episode, DELTA_BY_TYPE


def test_delta_table():
    assert DELTA_BY_TYPE == {"monster": 0.10, "elite": 0.15, "boss": 0.20}


def test_mistake_episode_a_only_triggers():
    ep = _ep(hp_before=100, dmg=30, combat_type="monster")  # loss = 0.30
    # baseline 0.15, delta 0.10 -> threshold 0.25 -> 0.30 > 0.25 -> mistake
    assert is_mistake_episode(ep, baseline_a_val=0.15, baseline_b_val=None)


def test_mistake_episode_b_only_triggers():
    ep = _ep(hp_before=100, dmg=30, combat_type="monster")
    assert is_mistake_episode(ep, baseline_a_val=None, baseline_b_val=0.15)


def test_mistake_episode_both_inactive_returns_false():
    ep = _ep(hp_before=100, dmg=50, combat_type="monster")
    assert not is_mistake_episode(ep, baseline_a_val=None, baseline_b_val=None)


def test_mistake_episode_within_delta_not_flagged():
    ep = _ep(hp_before=100, dmg=20, combat_type="monster")  # loss = 0.20
    # Baseline 0.15 + delta 0.10 = 0.25 threshold -> 0.20 NOT > 0.25 -> not mistake
    assert not is_mistake_episode(ep, baseline_a_val=0.15, baseline_b_val=None)


def test_mistake_episode_uses_elite_delta():
    ep = _ep(hp_before=100, dmg=30, combat_type="elite")  # loss = 0.30
    # 0.15 + 0.15 (elite delta) = 0.30 threshold -> 0.30 NOT > 0.30 (strict >) -> not mistake
    assert not is_mistake_episode(ep, baseline_a_val=0.15, baseline_b_val=None)
    ep2 = _ep(hp_before=100, dmg=31, combat_type="elite")  # loss = 0.31
    assert is_mistake_episode(ep2, baseline_a_val=0.15, baseline_b_val=None)


import asyncio
import json


def test_run_critic_parallel_fans_out_gather(monkeypatch):
    """Verify parallel fan-out: 3 episodes yield 3 critic calls, all `no_skill_needed`."""
    from src.skills.mistake_discovery import run_critic_parallel

    episodes = [
        _ep(enemy_key="A", hp_before=100, dmg=40),
        _ep(enemy_key="B", hp_before=100, dmg=50),
        _ep(enemy_key="C", hp_before=100, dmg=60),
    ]

    call_count = {"n": 0}

    async def fake_call_raw(*args, **kwargs):
        call_count["n"] += 1
        resp = {
            "analysis": "mistake",
            "decision": "no_skill_needed",
            "reason": "bad_luck",
            "skill": None,
        }
        return json.dumps(resp), 1.0, 10

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)

    async def run():
        return await run_critic_parallel(
            episodes,
            baselines_a=[0.1, 0.1, 0.1],
            baselines_b=[0.2, 0.2, 0.2],
            ns_a=[5, 5, 5], ns_b=[5, 5, 5],
        )

    results = asyncio.run(run())
    assert len(results) == 3
    assert call_count["n"] == 3
    assert all(r.decision == "no_skill_needed" for r in results)


def test_run_critic_parallel_handles_llm_exception(monkeypatch):
    """A crashing LLM call produces a no_skill_needed fallback, does not propagate."""
    from src.skills.mistake_discovery import run_critic_parallel

    async def fake_call_raw(*args, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)

    episodes = [_ep(enemy_key="A")]
    results = asyncio.run(run_critic_parallel(
        episodes, baselines_a=[0.1], baselines_b=[0.2], ns_a=[5], ns_b=[5],
    ))
    assert len(results) == 1
    assert results[0].decision == "no_skill_needed"
    assert results[0].reason == "critic_error"


def test_run_mistake_discovery_zero_episodes_returns_zero_stats(tmp_path):
    """Orchestrator must handle empty episode list without crashing."""
    import asyncio
    from src.skills.mistake_discovery import run_mistake_discovery
    from src.memory.combat_store import CombatMemoryStore
    from src.skills.library import SkillLibrary
    from src.memory.write_gate import WriteGate

    log = tmp_path / "empty.jsonl"
    log.write_text("")

    stats = asyncio.run(run_mistake_discovery(
        this_run_episodes=[],
        combat_store=CombatMemoryStore(),
        skill_library=SkillLibrary(),
        write_gate=WriteGate(),
        log_path=log,
        run_id="r_empty",
        combat_system_prompt="system",
    ))
    assert stats["mistakes"] == 0
    assert stats["persisted"] == 0


def test_run_mistake_discovery_no_mistakes_short_circuits(tmp_path, monkeypatch):
    """Episodes exist but none exceed baseline — pipeline stops after filter."""
    import asyncio
    from src.skills.mistake_discovery import run_mistake_discovery
    from src.memory.combat_store import CombatMemoryStore
    from src.skills.library import SkillLibrary
    from src.memory.write_gate import WriteGate

    store = CombatMemoryStore()
    # History: 5 episodes at loss=0.10 (enough to activate baseline_a=0.10)
    for i in range(5):
        store.add_batch([_ep(run_id=f"old{i}", hp_before=100, dmg=10, enemy_key="Rat")])
    # This run: 1 episode at loss=0.12 (baseline 0.10 + delta 0.10 = 0.20; 0.12 < 0.20)
    ep_this = _ep(run_id="r_now", hp_before=100, dmg=12, enemy_key="Rat")
    store.add_batch([ep_this])

    log = tmp_path / "run.jsonl"
    log.write_text("")

    # call_raw must never be invoked (filter eliminates the episode first)
    async def fake_call_raw(*a, **kw):
        raise AssertionError("critic called for non-mistake episode")
    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)

    stats = asyncio.run(run_mistake_discovery(
        this_run_episodes=[ep_this],
        combat_store=store,
        skill_library=SkillLibrary(),
        write_gate=WriteGate(),
        log_path=log, run_id="r_now",
        combat_system_prompt="system",
    ))
    assert stats["mistakes"] == 0
    assert stats["critic_skill_needed"] == 0
