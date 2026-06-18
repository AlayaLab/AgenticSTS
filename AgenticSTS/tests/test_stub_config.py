"""Verify Mode B / STM env vars exist with correct defaults + toggle semantics."""
import importlib
import os


_MODE_B_VARS = (
    "STS2_SEED_STUB_FILL_ENABLED",
    "STS2_USE_SEED_STUBS",
    "STS2_DISABLE_SKILL_SEEDS",
    "STS2_STM_ENABLED",
)


def _clear_env():
    for k in _MODE_B_VARS:
        os.environ.pop(k, None)


def test_seed_stub_defaults():
    """All Mode B flags default off; STM defaults on (existing behavior preserved)."""
    _clear_env()
    import config as _cfg
    importlib.reload(_cfg)
    assert _cfg.SEED_STUB_FILL_ENABLED is False
    assert _cfg.USE_SEED_STUBS is False
    assert _cfg.DISABLE_SKILL_SEEDS is False
    assert _cfg.STM_ENABLED is True


def test_seed_stub_dir_resolves_to_real_path():
    """SEED_STUB_DIR must point to the actual templates directory."""
    _clear_env()
    import config as _cfg
    importlib.reload(_cfg)
    from pathlib import Path
    p = Path(_cfg.SEED_STUB_DIR)
    assert p.exists(), f"SEED_STUB_DIR {p} does not exist"
    assert p.name == "seeds_stubs"


def test_seed_stub_fill_enabled_can_be_toggled():
    """Setting STS2_SEED_STUB_FILL_ENABLED=true flips the flag at config reload."""
    os.environ["STS2_SEED_STUB_FILL_ENABLED"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)
        assert _cfg.SEED_STUB_FILL_ENABLED is True
    finally:
        _clear_env()


def test_use_seed_stubs_can_be_toggled():
    os.environ["STS2_USE_SEED_STUBS"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)
        assert _cfg.USE_SEED_STUBS is True
    finally:
        _clear_env()


def test_disable_skill_seeds_can_be_toggled():
    """Mode B disables expert seeds; baseline also uses this."""
    os.environ["STS2_DISABLE_SKILL_SEEDS"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)
        assert _cfg.DISABLE_SKILL_SEEDS is True
    finally:
        _clear_env()


def test_stm_enabled_can_be_disabled():
    """baseline / Mode A turn STM off."""
    os.environ["STS2_STM_ENABLED"] = "false"
    try:
        import config as _cfg
        importlib.reload(_cfg)
        assert _cfg.STM_ENABLED is False
    finally:
        _clear_env()


def test_seed_stub_fill_log_path_resolves():
    """Audit log path must be available + parent dir creatable."""
    _clear_env()
    import config as _cfg
    importlib.reload(_cfg)
    from pathlib import Path
    p = Path(_cfg.SEED_STUB_FILL_LOG)
    # Path itself doesn't need to exist, but parent must be creatable
    assert p.name == "stub_fill_log.jsonl"
    assert "evolution" in p.parts or str(p.parent).endswith("evolution")
