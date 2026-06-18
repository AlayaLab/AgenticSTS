"""Config + integration test for the deck-building skill cap.

Post-mortem finding from the 2026-04-22 gemini-full ablation:
archetype-specific skills were retrieved at every card_reward, causing
the agent to pivot builds every 3-4 picks ("Frontload" -> "Poison" ->
"Shiv" -> "Panache") and end up with an incoherent deck. A tighter
cap on deck-building decisions keeps the guidance focused.
"""
from __future__ import annotations


def test_deckbuilding_cap_is_lower_than_combat_cap():
    """Deck-building decisions must have a tighter skill cap than combat.

    If this test fails because the defaults became equal, the archetype-
    hopping regression may re-emerge. Keep them distinct unless the
    ablation study says otherwise.
    """
    import config
    assert hasattr(config, "SKILLS_MAX_PER_PROMPT_DECKBUILDING"), (
        "SKILLS_MAX_PER_PROMPT_DECKBUILDING must exist in config"
    )
    assert config.SKILLS_MAX_PER_PROMPT_DECKBUILDING < config.SKILLS_MAX_PER_PROMPT, (
        f"Deck-building cap ({config.SKILLS_MAX_PER_PROMPT_DECKBUILDING}) "
        f"must be < combat cap ({config.SKILLS_MAX_PER_PROMPT})"
    )
    assert config.SKILLS_MAX_PER_PROMPT_DECKBUILDING >= 1, (
        "Deck-building cap must be >= 1 (or skills should be disabled entirely)"
    )


def test_env_override_respected(monkeypatch):
    """Operators can tune the deck-building cap via env var."""
    monkeypatch.setenv("STS2_SKILLS_MAX_PER_PROMPT_DECKBUILDING", "2")
    import importlib
    import sys
    if "config" in sys.modules:
        importlib.reload(sys.modules["config"])
    import config
    assert config.SKILLS_MAX_PER_PROMPT_DECKBUILDING == 2
    # Restore
    monkeypatch.delenv("STS2_SKILLS_MAX_PER_PROMPT_DECKBUILDING", raising=False)
    importlib.reload(config)


def test_loop_uses_deckbuilding_cap_for_card_reward_states():
    """The agent loop's _query_skills must pick the tighter cap for
    card_reward / shop / hand_select / card_select / treasure states."""
    import inspect
    from src.agent.loop import AgentLoop
    src = inspect.getsource(AgentLoop._query_skills)
    # The source must reference both the deck-building state set and the
    # dedicated config constant. Light structural check — avoids the
    # complex mock harness a full behaviour test would need.
    assert "SKILLS_MAX_PER_PROMPT_DECKBUILDING" in src, (
        "_query_skills must branch on SKILLS_MAX_PER_PROMPT_DECKBUILDING "
        "for deck-building decisions"
    )
    for state in ("card_reward", "card_select", "shop", "hand_select", "treasure"):
        assert state in src, f"deck-building state {state!r} must be in the filter set"
