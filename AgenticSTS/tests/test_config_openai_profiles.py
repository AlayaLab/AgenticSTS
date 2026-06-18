from __future__ import annotations

import config


def test_postrun_profile_reads_dedicated_base_url_and_api_key(monkeypatch):
    monkeypatch.setattr(config, "POSTRUN_OPENAI_COMPAT_BASE_URL", "https://postrun.example/v1")
    monkeypatch.setattr(config, "POSTRUN_OPENAI_COMPAT_API_KEY", "sk-postrun")
    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://game.example/v1")
    monkeypatch.setattr(config, "OPENAI_COMPAT_API_KEY", "sk-game")

    assert config.get_openai_compat_base_url("postrun") == "https://postrun.example/v1"
    assert config.get_openai_compat_api_key("postrun") == "sk-postrun"


def test_postrun_profile_falls_back_to_default_openai_compat_settings(monkeypatch):
    monkeypatch.delenv("STS2_POSTRUN_OPENAI_COMPAT_RELAYS", raising=False)
    monkeypatch.setattr(config, "POSTRUN_OPENAI_COMPAT_BASE_URL", "")
    monkeypatch.setattr(config, "POSTRUN_OPENAI_COMPAT_API_KEY", "")
    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://game.example/v1")
    monkeypatch.setattr(config, "OPENAI_COMPAT_API_KEY", "sk-game")

    relays = config.get_openai_compat_relays("postrun")

    assert config.get_openai_compat_base_url("postrun") == "https://game.example/v1"
    assert config.get_openai_compat_api_key("postrun") == "sk-game"
    assert relays == (
        {
            "name": "postrun_primary",
            "base_url": "https://game.example/v1",
            "api_key": "sk-game",
        },
    )
