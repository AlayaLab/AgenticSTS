"""Tests for ablation-baseline flag defaults and overrides.

Defaults must preserve current ("full") behavior. Each flag toggles
independently. .env cannot override values the ablation runner sets.
"""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager


@contextmanager
def _envvar(**overrides: str):
    """Set env vars, reload config, restore on exit."""
    original = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            os.environ[k] = v
        import config
        importlib.reload(config)
        yield config
    finally:
        for k, v in original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import config
        importlib.reload(config)


def test_prompt_variant_defaults_to_full():
    with _envvar() as config:
        assert config.PROMPT_VARIANT == "full"


def test_prompt_hint_filter_defaults_to_false():
    with _envvar() as config:
        assert config.PROMPT_HINT_FILTER is False


def test_knowledge_strict_defaults_to_false():
    with _envvar() as config:
        assert config.KNOWLEDGE_STRICT is False


def test_stm_enabled_defaults_to_true():
    with _envvar() as config:
        assert config.STM_ENABLED is True


def test_combat_conversation_enabled_defaults_to_true():
    with _envvar() as config:
        assert config.COMBAT_CONVERSATION_ENABLED is True


def test_include_boss_hp_defaults_to_true():
    with _envvar() as config:
        assert config.INCLUDE_BOSS_HP is True


def test_prompt_variant_baseline_override():
    with _envvar(STS2_PROMPT_VARIANT="baseline") as config:
        assert config.PROMPT_VARIANT == "baseline"


def test_knowledge_strict_true_override():
    with _envvar(STS2_KNOWLEDGE_STRICT="true") as config:
        assert config.KNOWLEDGE_STRICT is True


def test_stm_enabled_false_override():
    with _envvar(STS2_STM_ENABLED="false") as config:
        assert config.STM_ENABLED is False


def test_all_new_flags_in_preserve_if_set():
    with _envvar() as config:
        for flag in (
            "STS2_PROMPT_VARIANT",
            "STS2_PROMPT_HINT_FILTER",
            "STS2_KNOWLEDGE_STRICT",
            "STS2_STM_ENABLED",
            "STS2_COMBAT_CONVERSATION_ENABLED",
            "STS2_INCLUDE_BOSS_HP",
        ):
            assert flag in config._PRESERVE_IF_SET, f"{flag} missing from _PRESERVE_IF_SET"


def test_storage_roots_preserved_against_dotenv():
    """STS2_DATA_REPO and friends MUST be in _PRESERVE_IF_SET.

    Critical for ablation experiments: orchestrator passes per-experiment
    STS2_DATA_REPO to subprocess; if not preserved, .env overwrites it and
    every condition writes back to the shared root, contaminating data.
    """
    with _envvar() as config:
        for flag in (
            "STS2_DATA_REPO",
            "STS2_DATA_DIR",
            "STS2_RUNS_HISTORY_REPO",
            "STS2_MACHINE_ID",
        ):
            assert flag in config._PRESERVE_IF_SET, (
                f"{flag} missing from _PRESERVE_IF_SET — subprocess-set value "
                f"will be clobbered by .env, breaking ablation isolation."
            )


def test_model_profile_includes_new_flags():
    with _envvar() as config:
        profile = config.build_model_profile()
        for key in (
            "prompt_variant",
            "prompt_hint_filter",
            "knowledge_strict",
            "stm_enabled",
            "combat_conversation_enabled",
            "include_boss_hp",
        ):
            assert key in profile, f"{key} missing from model_profile"
