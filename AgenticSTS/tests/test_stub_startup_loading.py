"""Tests for Mode B stub loading at agent startup.

DISABLE_SKILL_SEEDS=true → expert seeds are skipped during init.
USE_SEED_STUBS=true → stub templates load when character becomes known.
"""

import importlib
import os
from pathlib import Path

from src.agent.loop import AgentLoop


def _clear_env():
    for k in (
        "STS2_DISABLE_SKILL_SEEDS",
        "STS2_USE_SEED_STUBS",
        "STS2_SKILLS_ENABLED",
    ):
        os.environ.pop(k, None)


def _empty_agent() -> AgentLoop:
    return AgentLoop.__new__(AgentLoop)


def test_init_skill_library_skips_expert_seeds_when_disable_set(monkeypatch):
    """DISABLE_SKILL_SEEDS=true: expert seed dir is NOT loaded."""
    _clear_env()
    os.environ["STS2_DISABLE_SKILL_SEEDS"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)

        # Track whether load_seeds was called
        from src.skills import library as lib_mod
        called = []
        original_load_seeds = lib_mod.SkillLibrary.load_seeds
        def _spy_load_seeds(seed_dir):
            called.append(seed_dir)
            return original_load_seeds(seed_dir)
        monkeypatch.setattr(lib_mod.SkillLibrary, "load_seeds", classmethod(lambda cls, sd: _spy_load_seeds(sd)))

        agent = _empty_agent()
        agent._init_skill_library()
        # Expert seeds NOT loaded because DISABLE_SKILL_SEEDS=true
        assert called == [], (
            f"Expected no seed-load calls when DISABLE_SKILL_SEEDS=true; got {called}"
        )
    finally:
        _clear_env()
        import config as _cfg
        importlib.reload(_cfg)


def test_lazy_load_seed_stubs_method_exists():
    """Lazy stub loader hook must exist on AgentLoop."""
    assert hasattr(AgentLoop, "_lazy_load_seed_stubs")


def test_lazy_load_seed_stubs_is_no_op_without_use_seed_stubs(monkeypatch):
    """USE_SEED_STUBS=false (default) → lazy load is a no-op."""
    _clear_env()
    import config as _cfg
    importlib.reload(_cfg)
    assert _cfg.USE_SEED_STUBS is False

    from src.skills.library import SkillLibrary
    agent = _empty_agent()
    agent._skill_library = SkillLibrary()

    agent._lazy_load_seed_stubs("the silent")
    assert agent._skill_library.count == 0  # no stubs loaded


def test_lazy_load_seed_stubs_loads_when_enabled(monkeypatch):
    """USE_SEED_STUBS=true + valid character → 5 Silent stubs load."""
    _clear_env()
    os.environ["STS2_USE_SEED_STUBS"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)

        from src.skills.library import SkillLibrary
        agent = _empty_agent()
        agent._skill_library = SkillLibrary()

        agent._lazy_load_seed_stubs("the silent")
        # All 5 silent stubs are now in the library, in pending_fill state
        stub_ids = {s.skill_id for s in agent._skill_library.all_skills if s.skill_id.startswith("stub_")}
        assert len(stub_ids) == 5
        for s in agent._skill_library.all_skills:
            if s.skill_id.startswith("stub_"):
                assert s.status == "pending_fill"
    finally:
        _clear_env()
        import config as _cfg
        importlib.reload(_cfg)


def test_lazy_load_seed_stubs_idempotent(monkeypatch):
    """Calling lazy load twice with same character does not duplicate."""
    _clear_env()
    os.environ["STS2_USE_SEED_STUBS"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)

        from src.skills.library import SkillLibrary
        agent = _empty_agent()
        agent._skill_library = SkillLibrary()

        agent._lazy_load_seed_stubs("the silent")
        agent._lazy_load_seed_stubs("the silent")
        assert agent._skill_library.count == 5
    finally:
        _clear_env()
        import config as _cfg
        importlib.reload(_cfg)


def test_lazy_load_seed_stubs_handles_no_library():
    """If skill library wasn't initialized, lazy load is a graceful no-op."""
    _clear_env()
    os.environ["STS2_USE_SEED_STUBS"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)

        agent = _empty_agent()
        agent._skill_library = None  # simulating SKILLS_ENABLED=false
        # Must not raise
        agent._lazy_load_seed_stubs("the silent")
    finally:
        _clear_env()
        import config as _cfg
        importlib.reload(_cfg)
