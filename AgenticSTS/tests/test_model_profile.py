"""Tests for config.build_model_profile / model_profile_hash."""
import config


def test_build_model_profile_returns_dict_with_required_keys():
    profile = config.build_model_profile()
    assert isinstance(profile, dict)
    for key in (
        "fast_model", "strategic_model", "analysis_model",
        "fast_provider", "strategic_provider",
        "memory_enabled", "skills_enabled", "evolution_enabled",
    ):
        assert key in profile, f"missing key: {key}"


def test_model_profile_hash_is_stable():
    p1 = config.build_model_profile()
    p2 = config.build_model_profile()
    h1 = config.model_profile_hash(p1)
    h2 = config.model_profile_hash(p2)
    assert h1 == h2
    assert len(h1) == 8
    assert all(c in "0123456789abcdef" for c in h1)


def test_model_profile_hash_changes_with_different_config():
    p1 = config.build_model_profile()
    p2 = {**p1, "strategic_model": "totally-different-model"}
    assert config.model_profile_hash(p1) != config.model_profile_hash(p2)


def test_model_profile_label_contains_models():
    profile = config.build_model_profile()
    label = config.model_profile_label(profile)
    assert profile["strategic_model"] in label
    assert profile["fast_model"] in label
