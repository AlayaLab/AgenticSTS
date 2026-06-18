import sys
from pathlib import Path
from unittest.mock import patch

from scripts.run_ablation import build_condition_matrix, Condition, count_existing_runs, main
from src.runs.history import RunHistoryStore, RunRecord


def test_matrix_has_five_conditions_per_model():
    """Matrix grew from 4 → 5 per model on 2026-05-03 with Mode B addition.
    The 5 conditions: baseline-strict, prompt-only, mode-a (NEW), self-evolve
    (now Mode B with stub flags), full. See spec
    docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md."""
    matrix = build_condition_matrix(models=("qwen", "gemini"))
    assert len(matrix) == 10  # 2 models * 5 conditions each
    ids = {c.condition_id for c in matrix}
    assert ids == {
        "qwen-baseline-strict", "qwen-prompt-only", "qwen-mode-a",
        "qwen-self-evolve", "qwen-full",
        "gemini-baseline-strict", "gemini-prompt-only", "gemini-mode-a",
        "gemini-self-evolve", "gemini-full",
    }


def test_baseline_disables_all_three():
    matrix = build_condition_matrix(models=("qwen",))
    baseline = next(c for c in matrix if c.condition_id == "qwen-baseline-strict")
    assert baseline.skills is False
    assert baseline.memory is False
    assert baseline.evolution is False


def test_full_enables_all_three():
    matrix = build_condition_matrix(models=("gemini",))
    full = next(c for c in matrix if c.condition_id == "gemini-full")
    assert full.skills is True
    assert full.memory is True
    assert full.evolution is True


def test_condition_to_cli_args_baseline():
    c = Condition(
        condition_id="qwen-baseline-strict", model_family="qwen",
        skills=False, memory=False, evolution=False,
        prompt_variant="baseline", hint_filter=True, knowledge_strict=True,
        stm=False, combat_conv=False, boss_hp=False,
    )
    args = c.to_cli_args(tag="abl-test", character="Silent", ascension=10, steps=500)
    assert "--model-family" in args and "qwen" in args
    assert "--no-skills" in args
    assert "--no-memory" in args
    assert "--no-evolution" in args
    assert "--no-postrun" in args  # frozen snapshot always
    assert "--abandon-existing" in args  # always start from clean game state
    assert "--experiment-tag" in args and "abl-test" in args
    assert "--character" in args and "Silent" in args
    assert "--ascension" in args and "10" in args
    assert "--runs" in args and "1" in args  # one run at a time
    assert "--steps" in args and "500" in args


def test_condition_to_cli_args_full():
    c = Condition(
        condition_id="gemini-full", model_family="gemini",
        skills=True, memory=True, evolution=True,
    )
    args = c.to_cli_args(tag="abl-test", character="Silent", ascension=10, steps=500)
    assert "--no-skills" not in args
    assert "--no-memory" not in args
    assert "--no-evolution" not in args
    assert "--no-postrun" in args  # still frozen
    assert "--abandon-existing" in args  # full condition also starts clean


def test_to_env_overrides_baseline():
    c = Condition(
        condition_id="qwen-baseline-strict", model_family="qwen",
        skills=False, memory=False, evolution=False,
        prompt_variant="baseline", hint_filter=True, knowledge_strict=True,
        stm=False, combat_conv=False, boss_hp=False,
    )
    env = c.to_env_overrides()
    assert env == {
        "STS2_SKILLS_ENABLED": "false",
        "STS2_MEMORY_ENABLED": "false",
        "STS2_EVOLUTION_ENABLED": "false",
        "STS2_PROMPT_VARIANT": "baseline",
        "STS2_PROMPT_HINT_FILTER": "true",
        "STS2_KNOWLEDGE_STRICT": "true",
        "STS2_STM_ENABLED": "false",
        "STS2_COMBAT_CONVERSATION_ENABLED": "false",
        "STS2_INCLUDE_BOSS_HP": "false",
        # Mode B flags (added 2026-05-03; explicitly false for non-Mode-B conditions)
        "STS2_DISABLE_SKILL_SEEDS": "false",
        "STS2_USE_SEED_STUBS": "false",
        "STS2_SEED_STUB_FILL_ENABLED": "false",
    }


def test_to_env_overrides_full():
    c = Condition(
        condition_id="gemini-full", model_family="gemini",
        skills=True, memory=True, evolution=True,
    )
    env = c.to_env_overrides()
    assert env == {
        "STS2_SKILLS_ENABLED": "true",
        "STS2_MEMORY_ENABLED": "true",
        "STS2_EVOLUTION_ENABLED": "true",
        "STS2_PROMPT_VARIANT": "full",
        "STS2_PROMPT_HINT_FILTER": "false",
        "STS2_KNOWLEDGE_STRICT": "false",
        "STS2_STM_ENABLED": "true",
        "STS2_COMBAT_CONVERSATION_ENABLED": "true",
        "STS2_INCLUDE_BOSS_HP": "true",
        # Mode B flags (full uses expert seeds, not stubs)
        "STS2_DISABLE_SKILL_SEEDS": "false",
        "STS2_USE_SEED_STUBS": "false",
        "STS2_SEED_STUB_FILL_ENABLED": "false",
    }


def test_preserve_if_set_includes_skill_memory_evolution():
    """Guard: subprocess env overrides for full condition rely on these keys
    being in config._PRESERVE_IF_SET so .env cannot clobber them.
    """
    import config
    for key in (
        "STS2_SKILLS_ENABLED",
        "STS2_MEMORY_ENABLED",
        "STS2_EVOLUTION_ENABLED",
        "STS2_MONITOR_ENABLED",
    ):
        assert key in config._PRESERVE_IF_SET, (
            f"{key} must be in config._PRESERVE_IF_SET — otherwise .env "
            f"will clobber subprocess env overrides for the full condition."
        )


def test_ablation_fixed_env_is_initially_empty():
    """_ABLATION_FIXED_ENV is reserved for subprocess-wide overrides.
    Currently empty — the Windows shutdown hang is solved by os._exit
    at end of run_agent.py __main__, so monitor can stay enabled.
    """
    from scripts.run_ablation import _ABLATION_FIXED_ENV
    assert _ABLATION_FIXED_ENV == {}


def _seed_record(*, tag, skills, memory, evolution, family, floor=10,
                  prompt_variant="full", hint_filter=False, knowledge_strict=False,
                  stm=True, combat_conv=True, boss_hp=True):
    return RunRecord(
        run_id=f"r-{family}-{skills}-{memory}-{evolution}-{floor}",
        experiment_tag=tag,
        final_floor=floor,
        skills_enabled=skills,
        memory_enabled=memory,
        model_profile={
            "strategic_family": family,
            "fast_family": family,
            "skills_enabled": skills,
            "memory_enabled": memory,
            "evolution_enabled": evolution,
            "prompt_variant": prompt_variant,
            "prompt_hint_filter": hint_filter,
            "knowledge_strict": knowledge_strict,
            "stm_enabled": stm,
            "combat_conversation_enabled": combat_conv,
            "include_boss_hp": boss_hp,
        },
    )


def test_count_existing_runs_zero_when_file_missing(tmp_path: Path):
    missing = tmp_path / "nonexistent.jsonl"
    assert count_existing_runs(missing, tag="any", condition_id="qwen-full") == 0


def test_count_existing_runs_counts_matching_records(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    # 3 qwen-full runs + 1 qwen-baseline-strict under tag "abl"
    for i in range(3):
        store.append(_seed_record(
            tag="abl", skills=True, memory=True, evolution=True,
            family="qwen", floor=10 + i,
        ))
    store.append(_seed_record(
        tag="abl", skills=False, memory=False, evolution=False,
        family="qwen", floor=5,
        prompt_variant="baseline", hint_filter=True, knowledge_strict=True,
        stm=False, combat_conv=False, boss_hp=False,
    ))
    # 2 qwen-full runs under a different tag — should NOT count
    for i in range(2):
        store.append(_seed_record(
            tag="other", skills=True, memory=True, evolution=True,
            family="qwen", floor=20 + i,
        ))

    assert count_existing_runs(path, tag="abl", condition_id="qwen-full") == 3
    assert count_existing_runs(path, tag="abl", condition_id="qwen-baseline-strict") == 1
    assert count_existing_runs(path, tag="abl", condition_id="gemini-full") == 0
    assert count_existing_runs(path, tag="other", condition_id="qwen-full") == 2


def test_timeout_sec_flag_accepted_in_dry_run():
    # --timeout-sec must be a recognized argparse flag; dry-run exits 0.
    argv = [
        "run_ablation",
        "--tag", "smoke-timeout",
        "--dry-run",
        "--runs-per-condition", "1",
        "--timeout-sec", "600",
    ]
    with patch.object(sys, "argv", argv):
        rc = main()
    assert rc == 0


def test_to_cli_args_omits_no_postrun_when_postrun_true():
    """Condition.postrun=True must not pass --no-postrun on the CLI."""
    cond = Condition(
        condition_id="test-self-evolve", model_family="gemini",
        skills=True, memory=True, evolution=True,
        postrun=True,
    )
    args = cond.to_cli_args(tag="t", character="Silent", ascension="auto", steps=100)
    assert "--no-postrun" not in args


def test_to_cli_args_includes_no_postrun_when_postrun_false():
    """Condition.postrun=False (default) must pass --no-postrun."""
    cond = Condition(
        condition_id="test-baseline", model_family="gemini",
        skills=False, memory=False, evolution=False,
    )
    args = cond.to_cli_args(tag="t", character="Silent", ascension="auto", steps=100)
    assert "--no-postrun" in args


def test_to_env_overrides_emits_data_repo_when_subpath_set(tmp_path, monkeypatch):
    """When data_repo_subpath is set, STS2_DATA_REPO and STS2_RUNS_HISTORY_REPO
    must be emitted with the subpath substituted."""
    monkeypatch.setenv("STS2_DATA_REPO", str(tmp_path))
    cond = Condition(
        condition_id="gemini-self-evolve", model_family="gemini",
        skills=True, memory=True, evolution=True,
        postrun=True,
        data_repo_subpath="experiments/{tag}/{condition_id}",
    )
    overrides = cond.to_env_overrides(tag="pilot-x")

    expected_data_repo = str((tmp_path / "experiments" / "pilot-x" / "gemini-self-evolve").resolve())
    assert overrides["STS2_DATA_REPO"] == expected_data_repo
    assert overrides["STS2_RUNS_HISTORY_REPO"] == str(tmp_path.resolve())


def test_to_env_overrides_omits_data_repo_when_subpath_unset():
    """Conditions without data_repo_subpath inherit shared STS2_DATA_REPO."""
    cond = Condition(
        condition_id="gemini-baseline-strict", model_family="gemini",
        skills=False, memory=False, evolution=False,
    )
    overrides = cond.to_env_overrides(tag="pilot-x")
    assert "STS2_DATA_REPO" not in overrides
    assert "STS2_RUNS_HISTORY_REPO" not in overrides


def test_to_env_overrides_emits_analysis_model_when_eq_strategic():
    """analysis_eq_strategic=True syncs ONLY the model (not effort).

    Effort is left to the user's STS2_THINK_EFFORT_ANALYSIS env var (or
    family default) so postrun effort can be tuned independently of
    gameplay strategic effort.
    """
    cond = Condition(
        condition_id="gpt-self-evolve", model_family="gpt",
        skills=True, memory=True, evolution=True,
        postrun=True,
        analysis_eq_strategic=True,
    )
    overrides = cond.to_env_overrides(tag="pilot-x")
    # gpt strategic = gpt-5.4 per _MODEL_FAMILIES in config.py
    assert overrides["STS2_ANALYSIS_MODEL"] == "gpt-5.4"
    # Effort intentionally NOT emitted — defers to env / family default.
    assert "STS2_THINK_EFFORT_ANALYSIS" not in overrides


def test_filter_matrix_by_conditions_self_evolve_only():
    """--conditions=self-evolve filters matrix to only self-evolve conditions
    across all selected models."""
    from scripts.run_ablation import build_condition_matrix, filter_matrix_by_conditions

    matrix = build_condition_matrix(("gemini", "qwen"))
    filtered = filter_matrix_by_conditions(matrix, "self-evolve")
    assert {c.condition_id for c in filtered} == {
        "gemini-self-evolve", "qwen-self-evolve",
    }


def test_filter_matrix_by_conditions_multi():
    """Comma-separated kinds keep matching across models."""
    from scripts.run_ablation import build_condition_matrix, filter_matrix_by_conditions

    matrix = build_condition_matrix(("gemini",))
    filtered = filter_matrix_by_conditions(matrix, "baseline-strict,self-evolve")
    assert {c.condition_id for c in filtered} == {
        "gemini-baseline-strict", "gemini-self-evolve",
    }


def test_filter_matrix_by_conditions_empty_means_all():
    """Empty filter returns the full matrix."""
    from scripts.run_ablation import build_condition_matrix, filter_matrix_by_conditions

    matrix = build_condition_matrix(("gemini",))
    filtered = filter_matrix_by_conditions(matrix, "")
    assert len(filtered) == len(matrix)


def test_filter_matrix_by_conditions_no_match_returns_empty():
    """Filter with no matching kind yields empty list (caller handles error)."""
    from scripts.run_ablation import build_condition_matrix, filter_matrix_by_conditions

    matrix = build_condition_matrix(("gemini",))
    filtered = filter_matrix_by_conditions(matrix, "nonexistent")
    assert filtered == []


def test_to_cli_args_appends_passthrough_flags():
    """passthrough kwarg appends arbitrary flags to the run_agent CLI.

    Used to forward --launch-game / --api-port=auto / --monitor-port=auto
    from the orchestrator to each subprocess.
    """
    cond = Condition(
        condition_id="gemini-self-evolve", model_family="gemini",
        skills=True, memory=True, evolution=True,
        postrun=True,
    )
    args = cond.to_cli_args(
        tag="t", character="Silent", ascension="auto", steps=100,
        passthrough=["--launch-game", "--api-port=auto", "--monitor-port=auto"],
    )
    assert "--launch-game" in args
    assert "--api-port=auto" in args
    assert "--monitor-port=auto" in args


def test_to_cli_args_passthrough_defaults_to_empty():
    """No passthrough kwarg means no extra args (back-compat)."""
    cond = Condition(
        condition_id="gemini-baseline-strict", model_family="gemini",
        skills=False, memory=False, evolution=False,
    )
    args = cond.to_cli_args(
        tag="t", character="Silent", ascension="auto", steps=100,
    )
    assert "--launch-game" not in args
    assert "--api-port=auto" not in args
