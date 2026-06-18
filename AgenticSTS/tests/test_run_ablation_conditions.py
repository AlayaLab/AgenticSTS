"""Tests for run_ablation Condition extensions and matrix generation."""
from __future__ import annotations

from scripts.run_ablation import Condition, build_condition_matrix


def test_baseline_condition_overrides_all_new_flags():
    cond = Condition(
        condition_id="qwen-baseline-strict",
        model_family="qwen",
        skills=False,
        memory=False,
        evolution=False,
        prompt_variant="baseline",
        hint_filter=True,
        knowledge_strict=True,
        stm=False,
        combat_conv=False,
        boss_hp=False,
    )
    env = cond.to_env_overrides()
    assert env["STS2_PROMPT_VARIANT"] == "baseline"
    assert env["STS2_PROMPT_HINT_FILTER"] == "true"
    assert env["STS2_KNOWLEDGE_STRICT"] == "true"
    assert env["STS2_STM_ENABLED"] == "false"
    assert env["STS2_COMBAT_CONVERSATION_ENABLED"] == "false"
    assert env["STS2_INCLUDE_BOSS_HP"] == "false"
    assert env["STS2_SKILLS_ENABLED"] == "false"
    assert env["STS2_MEMORY_ENABLED"] == "false"
    assert env["STS2_EVOLUTION_ENABLED"] == "false"


def test_full_condition_uses_default_values():
    cond = Condition(
        condition_id="qwen-full",
        model_family="qwen",
        skills=True,
        memory=True,
        evolution=True,
    )
    env = cond.to_env_overrides()
    assert env["STS2_PROMPT_VARIANT"] == "full"
    assert env["STS2_PROMPT_HINT_FILTER"] == "false"
    assert env["STS2_KNOWLEDGE_STRICT"] == "false"
    assert env["STS2_STM_ENABLED"] == "true"
    assert env["STS2_COMBAT_CONVERSATION_ENABLED"] == "true"
    assert env["STS2_INCLUDE_BOSS_HP"] == "true"
    assert env["STS2_SKILLS_ENABLED"] == "true"


def test_matrix_baseline_strict_id_format():
    matrix = build_condition_matrix(("qwen", "gemini"))
    ids = {c.condition_id for c in matrix}
    assert "qwen-baseline-strict" in ids
    assert "qwen-full" in ids
    assert "gemini-baseline-strict" in ids
    assert "gemini-full" in ids
    # Old "qwen-baseline" must NOT appear (renamed to disambiguate from
    # historical loose-baseline records).
    assert "qwen-baseline" not in ids
    assert "gemini-baseline" not in ids


def test_matrix_baseline_strict_full_strip():
    matrix = build_condition_matrix(("qwen",))
    baseline = next(c for c in matrix if c.condition_id == "qwen-baseline-strict")
    assert baseline.skills is False
    assert baseline.memory is False
    assert baseline.evolution is False
    assert baseline.prompt_variant == "baseline"
    assert baseline.hint_filter is True
    assert baseline.knowledge_strict is True
    assert baseline.stm is False
    assert baseline.combat_conv is False
    assert baseline.boss_hp is False


def test_cli_args_pass_through_existing_flags():
    cond = Condition(
        condition_id="qwen-baseline-strict",
        model_family="qwen",
        skills=False, memory=False, evolution=False,
    )
    args = cond.to_cli_args(tag="t1", character="Silent", ascension=5, steps=500)
    assert "--no-skills" in args
    assert "--no-memory" in args
    assert "--no-evolution" in args
    assert "--no-postrun" in args


def test_matrix_has_five_conditions_per_model():
    """Each model produces 5 conditions on 2026-05-03+:
    baseline-strict, prompt-only, mode-a (NEW), self-evolve (now Mode B), full.
    See spec docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md."""
    matrix = build_condition_matrix(("gemini",))
    ids = [c.condition_id for c in matrix]
    assert ids == [
        "gemini-baseline-strict",
        "gemini-prompt-only",
        "gemini-mode-a",
        "gemini-self-evolve",
        "gemini-full",
    ]


def test_prompt_only_keeps_full_prompts_zero_state():
    matrix = build_condition_matrix(("gemini",))
    cond = next(c for c in matrix if c.condition_id == "gemini-prompt-only")
    # Full prompt structure
    assert cond.prompt_variant == "full"
    assert cond.hint_filter is False
    assert cond.knowledge_strict is False
    assert cond.boss_hp is True
    assert cond.combat_conv is True   # intra-fight working memory stays on
    # Zero accumulated state
    assert cond.skills is False
    assert cond.memory is False
    assert cond.evolution is False
    assert cond.stm is False
    # No postrun, no isolated data dir
    assert cond.postrun is False
    assert cond.data_repo_subpath is None


def test_self_evolve_blank_start_with_postrun():
    matrix = build_condition_matrix(("gemini",))
    cond = next(c for c in matrix if c.condition_id == "gemini-self-evolve")
    assert cond.skills is True
    assert cond.memory is True
    assert cond.evolution is True
    assert cond.stm is True
    assert cond.combat_conv is True
    assert cond.postrun is True
    assert cond.analysis_eq_strategic is True
    assert cond.data_repo_subpath == "experiments/{tag}/{condition_id}"
