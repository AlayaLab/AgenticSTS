"""Verifies --no-evolution flag promotes to STS2_EVOLUTION_ENABLED=false before config imports."""
import importlib
import os
import sys


def test_no_evolution_flag_sets_env(monkeypatch):
    monkeypatch.delenv("STS2_EVOLUTION_ENABLED", raising=False)
    test_argv = ["run_agent.py", "--no-evolution", "--steps", "1"]
    monkeypatch.setattr(sys, "argv", test_argv)

    from scripts import run_agent
    run_agent._apply_pre_config_flags()

    assert os.environ.get("STS2_EVOLUTION_ENABLED") == "false"


def test_no_evolution_absent_leaves_env_untouched(monkeypatch):
    monkeypatch.delenv("STS2_EVOLUTION_ENABLED", raising=False)
    test_argv = ["run_agent.py", "--steps", "1"]
    monkeypatch.setattr(sys, "argv", test_argv)

    from scripts import run_agent
    run_agent._apply_pre_config_flags()

    assert "STS2_EVOLUTION_ENABLED" not in os.environ


def test_no_evolution_flag_disables_in_config(monkeypatch):
    monkeypatch.setenv("STS2_EVOLUTION_ENABLED", "false")
    import config as cfg
    importlib.reload(cfg)
    try:
        assert cfg.EVOLUTION_ENABLED is False
        profile = cfg.build_model_profile()
        assert profile["evolution_enabled"] is False
    finally:
        # Restore the module to its default state so we don't leak into other tests
        monkeypatch.delenv("STS2_EVOLUTION_ENABLED", raising=False)
        importlib.reload(cfg)
