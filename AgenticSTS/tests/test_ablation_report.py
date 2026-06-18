from pathlib import Path
from src.runs.history import RunRecord, RunHistoryStore
from scripts.ablation_report import (
    bootstrap_ci,
    aggregate_by_condition,
    format_markdown,
    condition_id_from_record,
)


def _rec(*, tag, victory, floor, fitness, skills, memory, evolution, family="gemini"):
    return RunRecord(
        run_id=f"r-{tag}-{victory}-{floor}",
        experiment_tag=tag,
        victory=victory,
        outcome="victory" if victory else "defeat",
        final_floor=floor,
        fitness=fitness,
        memory_enabled=memory,
        skills_enabled=skills,
        combats_won=floor // 2,
        combats_total=floor // 2 + 1,
        model_profile={
            "fast_family": family,
            "strategic_family": family,
            "skills_enabled": skills,
            "memory_enabled": memory,
            "evolution_enabled": evolution,
        },
    )


def test_condition_id_from_record():
    full = _rec(tag="t", victory=True, floor=50, fitness=1.0,
                skills=True, memory=True, evolution=True, family="qwen")
    assert condition_id_from_record(full) == "qwen-full"

    baseline = _rec(tag="t", victory=False, floor=10, fitness=0.1,
                    skills=False, memory=False, evolution=False, family="gemini")
    assert condition_id_from_record(baseline) == "gemini-baseline"

    mixed = _rec(tag="t", victory=False, floor=20, fitness=0.3,
                 skills=True, memory=False, evolution=False, family="gemini")
    assert condition_id_from_record(mixed) == "gemini-mixed"


def _record_with_profile(profile: dict) -> RunRecord:
    """Build a minimal RunRecord with the given model_profile."""
    return RunRecord(
        run_id="r-x",
        experiment_tag="t",
        victory=False,
        outcome="defeat",
        final_floor=5,
        skills_enabled=bool(profile.get("skills_enabled")),
        memory_enabled=bool(profile.get("memory_enabled")),
        model_profile=profile,
    )


def _gemini_profile(**kw) -> dict:
    base = dict(
        strategic_family="gemini",
        skills_enabled=False, memory_enabled=False, evolution_enabled=False,
        prompt_variant="full", prompt_hint_filter=False, knowledge_strict=False,
        stm_enabled=False, combat_conversation_enabled=True, include_boss_hp=True,
    )
    base.update(kw)
    return base


def test_baseline_strict_detected():
    p = _gemini_profile(
        prompt_variant="baseline", prompt_hint_filter=True, knowledge_strict=True,
        stm_enabled=False, combat_conversation_enabled=False, include_boss_hp=False,
    )
    assert condition_id_from_record(_record_with_profile(p)) == "gemini-baseline-strict"


def test_prompt_only_detected():
    p = _gemini_profile()
    assert condition_id_from_record(_record_with_profile(p)) == "gemini-prompt-only"


def test_self_evolve_detected():
    p = _gemini_profile(
        skills_enabled=True, memory_enabled=True, evolution_enabled=True,
        stm_enabled=True, postrun_enabled=True,
    )
    assert condition_id_from_record(_record_with_profile(p)) == "gemini-self-evolve"


def test_full_detected_via_postrun_disabled():
    p = _gemini_profile(
        skills_enabled=True, memory_enabled=True, evolution_enabled=True,
        stm_enabled=True, postrun_enabled=False,
    )
    assert condition_id_from_record(_record_with_profile(p)) == "gemini-full"


def test_bootstrap_ci_stable_for_trivial_data():
    lo, hi = bootstrap_ci([1.0] * 10, n_boot=200, seed=42)
    assert lo == 1.0 and hi == 1.0

    lo, hi = bootstrap_ci([1.0, 1.0, 0.0, 0.0, 1.0], n_boot=500, seed=42)
    # n=5, mean=0.6, deterministic with seed=42 → observed (0.2, 1.0)
    assert 0.1 <= lo <= 0.5
    assert 0.7 <= hi <= 1.0


def test_aggregate_by_condition(tmp_path: Path):
    path = tmp_path / "h.jsonl"
    store = RunHistoryStore(path)
    for v, f in [(True, 50), (False, 10), (False, 15)]:
        store.append(_rec(tag="abl", victory=v, floor=f, fitness=f/100.0,
                          skills=False, memory=False, evolution=False, family="gemini"))
    for v, f in [(True, 55), (True, 50), (False, 20)]:
        store.append(_rec(tag="abl", victory=v, floor=f, fitness=f/100.0,
                          skills=True, memory=True, evolution=True, family="gemini"))

    loaded = RunHistoryStore.load(path)
    records = loaded.query(experiment_tag="abl")
    agg = aggregate_by_condition(records)

    assert "gemini-baseline" in agg
    assert "gemini-full" in agg
    assert agg["gemini-baseline"]["n"] == 3
    assert agg["gemini-baseline"]["win_rate"] == 1 / 3
    assert agg["gemini-full"]["win_rate"] == 2 / 3
    assert agg["gemini-full"]["avg_floor"] > agg["gemini-baseline"]["avg_floor"]


def test_format_markdown_has_expected_columns():
    agg = {
        "qwen-baseline": {
            "n": 10, "win_rate": 0.1, "win_rate_ci": (0.0, 0.3),
            "avg_floor": 15.2, "avg_fitness": 0.2, "combat_win_rate": 0.55,
        },
        "qwen-full": {
            "n": 10, "win_rate": 0.3, "win_rate_ci": (0.1, 0.5),
            "avg_floor": 28.5, "avg_fitness": 0.45, "combat_win_rate": 0.70,
        },
    }
    md = format_markdown(agg, tag="abl-2026-04-21")
    assert "abl-2026-04-21" in md
    assert "qwen-baseline" in md
    assert "qwen-full" in md
    for col in ("n", "Win rate", "95% CI", "Avg floor", "Avg fitness", "Combat win%"):
        assert col in md
    assert "Δ (full - baseline)" in md or "delta" in md.lower()
