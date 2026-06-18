"""Tests for the Mode B 4-condition matrix in run_ablation.py.

The condition matrix maps to the spec's 4 conditions:
- baseline = baseline-strict (existing, slim prompts + no learning + no STM)
- Mode A   = mode-a (NEW: full prompts + expert seeds + no STM + no postrun)
- Mode B   = self-evolve (extended: full prompts + agent stubs + STM + postrun)
- full     = full (existing, full prompts + expert seeds + STM + postrun)
"""

from scripts.run_ablation import Condition, build_condition_matrix


def _condition_by_id(matrix: list[Condition], cid: str) -> Condition:
    for c in matrix:
        if c.condition_id == cid:
            return c
    raise AssertionError(f"condition {cid!r} not found in matrix")


def test_condition_has_mode_b_fields():
    """Condition dataclass must carry the 3 Mode B env-var fields."""
    c = Condition(
        condition_id="x", model_family="gemini",
        skills=True, memory=True, evolution=True,
        disable_skill_seeds=True,
        use_seed_stubs=True,
        seed_stub_fill_enabled=True,
    )
    assert c.disable_skill_seeds is True
    assert c.use_seed_stubs is True
    assert c.seed_stub_fill_enabled is True


def test_condition_default_mode_b_fields_off():
    """All 3 Mode B fields default to False (off)."""
    c = Condition(
        condition_id="x", model_family="gemini",
        skills=True, memory=True, evolution=True,
    )
    assert c.disable_skill_seeds is False
    assert c.use_seed_stubs is False
    assert c.seed_stub_fill_enabled is False


def test_env_overrides_emit_mode_b_flags_when_enabled():
    """to_env_overrides must emit STS2_DISABLE_SKILL_SEEDS / USE_SEED_STUBS /
    SEED_STUB_FILL_ENABLED based on the Condition fields."""
    c = Condition(
        condition_id="x", model_family="gemini",
        skills=True, memory=True, evolution=True,
        disable_skill_seeds=True,
        use_seed_stubs=True,
        seed_stub_fill_enabled=True,
    )
    env = c.to_env_overrides(tag="t")
    assert env.get("STS2_DISABLE_SKILL_SEEDS") == "true"
    assert env.get("STS2_USE_SEED_STUBS") == "true"
    assert env.get("STS2_SEED_STUB_FILL_ENABLED") == "true"


def test_env_overrides_emit_mode_b_flags_false_when_disabled():
    """When Mode B fields default off, env must explicitly emit 'false'.
    (Defense-in-depth: prevents .env or shell vars from leaking through.)"""
    c = Condition(
        condition_id="x", model_family="gemini",
        skills=True, memory=True, evolution=True,
    )
    env = c.to_env_overrides(tag="t")
    assert env.get("STS2_DISABLE_SKILL_SEEDS") == "false"
    assert env.get("STS2_USE_SEED_STUBS") == "false"
    assert env.get("STS2_SEED_STUB_FILL_ENABLED") == "false"


def test_matrix_contains_mode_a_condition_for_each_model():
    """build_condition_matrix must include {model}-mode-a per model."""
    matrix = build_condition_matrix(("gemini",))
    ids = {c.condition_id for c in matrix}
    assert "gemini-mode-a" in ids, f"mode-a missing; got: {ids}"


def test_mode_a_has_expert_seeds_no_postrun_no_stm():
    """Mode A: full prompts + expert seeds (skills=True) + STM off + no postrun
    + no memory + no evolution."""
    matrix = build_condition_matrix(("gemini",))
    c = _condition_by_id(matrix, "gemini-mode-a")
    assert c.skills is True               # expert seeds load
    assert c.memory is False              # no L4 cross-run
    assert c.evolution is False           # no postrun evolution
    assert c.postrun is False             # no postrun stage at all
    assert c.stm is False                 # no Strategic Thread
    assert c.prompt_variant == "full"
    assert c.disable_skill_seeds is False  # expert seeds DO load
    assert c.use_seed_stubs is False       # not Mode B
    assert c.seed_stub_fill_enabled is False


def test_self_evolve_now_carries_mode_b_flags():
    """self-evolve becomes Mode B: stubs replace expert seeds, fill enabled."""
    matrix = build_condition_matrix(("gemini",))
    c = _condition_by_id(matrix, "gemini-self-evolve")
    assert c.skills is True               # retrieval enabled
    assert c.memory is True
    assert c.evolution is True
    assert c.postrun is True
    assert c.stm is True
    assert c.prompt_variant == "full"
    # Mode B specifics
    assert c.disable_skill_seeds is True   # don't load expert seeds
    assert c.use_seed_stubs is True        # load stubs instead
    assert c.seed_stub_fill_enabled is True


def test_baseline_strict_unchanged():
    """baseline-strict should still be the slim no-everything condition."""
    matrix = build_condition_matrix(("gemini",))
    c = _condition_by_id(matrix, "gemini-baseline-strict")
    assert c.skills is False
    assert c.memory is False
    assert c.evolution is False
    assert c.stm is False
    assert c.prompt_variant == "baseline"
    assert c.postrun is False


def test_full_unchanged():
    """full should preserve current production behavior."""
    matrix = build_condition_matrix(("gemini",))
    c = _condition_by_id(matrix, "gemini-full")
    assert c.skills is True
    assert c.memory is True
    assert c.evolution is True
    assert c.disable_skill_seeds is False  # full uses expert seeds
    assert c.use_seed_stubs is False
