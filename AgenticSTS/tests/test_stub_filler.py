"""Integration tests for StubFiller orchestration with a mock backend."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.skills.library import SkillLibrary


def _stub_lib(character: str = "the silent") -> SkillLibrary:
    lib = SkillLibrary()
    stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
    lib.load_seed_stubs(stub_dir, character=character)
    return lib


def _backend_returning(payload: dict) -> MagicMock:
    """Build a mock backend.call() that returns a single text-block response
    containing the given JSON payload."""
    backend = MagicMock()
    backend.call.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=5000, output_tokens=600),
    )
    return backend


def _good_payload(prefix: str = "P") -> dict:
    return {
        "principles": [
            {"text": f"{prefix} use ALL energy each turn.",
             "example": "If 1 energy left, play a 1-cost."},
            {"text": f"{prefix} read intents BEFORE deciding offense vs defense.",
             "example": "When the enemy buffs, set up your engine."},
            {"text": f"{prefix} prefer the 0-damage line over a faster line.",
             "example": "Take a defensive turn even if slower."},
            {"text": f"{prefix} sequence free plays first.",
             "example": "Free Strike before a costed skill."},
            {"text": f"{prefix} save buff potions for boss fights.",
             "example": "Don't burn Strength Potion on a hallway."},
        ],
        "confidence": 0.7,
        "dimensions_covered": ["energy_allocation", "intent_reading"],
        "evidence_basis": "Cross-run pattern analysis.",
    }


def test_filler_promotes_pending_stub_to_active_after_first_fill():
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    backend = _backend_returning(_good_payload("Z"))

    filler = StubFiller(library=lib, backend=backend)
    stub_ids = [s.skill_id for s in lib.all_skills if s.skill_id.startswith("stub_")]
    summary = filler.fill_all_stubs(
        character="the silent",
        evidence_by_stub={sid: f"## Evidence for {sid}\n..." for sid in stub_ids},
    )

    assert summary["filled_count"] == 5
    for s in lib.all_skills:
        if s.skill_id.startswith("stub_"):
            assert s.status == "active"
            assert s.source == "stub_filled"
            assert s.version == 1
            assert "use ALL energy" in s.content


def test_filler_skips_stub_when_evidence_is_empty():
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    backend = _backend_returning(_good_payload())
    filler = StubFiller(library=lib, backend=backend)

    # Provide evidence for only ONE stub
    summary = filler.fill_all_stubs(
        character="the silent",
        evidence_by_stub={"stub_the_silent_combat": "## Evidence ..."},
    )
    assert summary["filled_count"] == 1
    assert summary["skipped_count"] == 4
    # Backend was called exactly once (only the one stub with evidence)
    assert backend.call.call_count == 1


def test_filler_update_passes_existing_content_to_prompt():
    """Second fill on an active stub uses build_update_prompt + existing content."""
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    # Promote one stub to active manually
    s = lib.get("stub_the_silent_combat")
    lib.add(s.with_update(
        status="active",
        source="stub_filled",
        content="1. Old principle.",
        version=1,
    ))

    captured_prompts: list[str] = []
    def _capture(**kwargs):
        captured_prompts.append(kwargs["messages"][0]["content"])
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(_good_payload("Q")))],
            stop_reason="end_turn",
        )
    backend = MagicMock()
    backend.call.side_effect = _capture

    filler = StubFiller(library=lib, backend=backend)
    filler.fill_all_stubs(
        character="the silent",
        evidence_by_stub={"stub_the_silent_combat": "## Evidence"},
    )

    assert any("Old principle" in p for p in captured_prompts), (
        "update prompt didn't include existing content"
    )
    assert any("Existing Content (v1)" in p for p in captured_prompts)
    # Version bumped
    updated = lib.get("stub_the_silent_combat")
    assert updated.version == 2
    assert "use ALL energy" in updated.content  # new content overwrites


def test_filler_handles_malformed_response_gracefully():
    """If backend returns non-JSON text, filler logs and skips, doesn't crash."""
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    backend = MagicMock()
    backend.call.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="<not json>")],
        stop_reason="end_turn",
    )

    # Provide evidence for ALL 5 stubs so the test isolates parse-failure behavior
    # (otherwise stubs without evidence also count as "skipped" but for a different reason).
    stub_ids = [s.skill_id for s in lib.all_skills if s.skill_id.startswith("stub_")]
    filler = StubFiller(library=lib, backend=backend)
    summary = filler.fill_all_stubs(
        character="the silent",
        evidence_by_stub={sid: "## Evidence" for sid in stub_ids},
    )
    assert summary["filled_count"] == 0
    assert summary["skipped_count"] == 5  # all 5 attempted, all failed parse
    # Stubs stay pending_fill — none got promoted because all parses failed
    for s in lib.all_skills:
        if s.skill_id.startswith("stub_"):
            assert s.status == "pending_fill"


def test_filler_attaches_warnings_to_summary():
    """Validators run after fill — warnings appear in summary, content is still written."""
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    # Payload with too few principles (3 < 4) → triggers principle_count_off warning
    bad_payload = {
        "principles": [
            {"text": "Use energy.", "example": "ex"},
            {"text": "Read intents.", "example": "ex"},
            {"text": "Block first.", "example": "ex"},
        ],
        "confidence": 0.7,
    }
    backend = _backend_returning(bad_payload)

    filler = StubFiller(library=lib, backend=backend)
    summary = filler.fill_all_stubs(
        character="the silent",
        evidence_by_stub={"stub_the_silent_combat": "## Evidence"},
    )
    assert summary["filled_count"] == 1
    warnings = summary["warnings_by_stub"]["stub_the_silent_combat"]
    assert any("principle_count_off" in w for w in warnings)
    # Stub still got written despite warning (warn-only)
    s = lib.get("stub_the_silent_combat")
    assert s.status == "active"


# ── Concurrent fill (afill_all_stubs) ──────────────────────────


import asyncio
import time as _time

import pytest


@pytest.mark.asyncio
async def test_afill_all_stubs_runs_backend_calls_concurrently():
    """async afill_all_stubs must dispatch backend.call across stubs concurrently,
    so total wall-time ≈ max(per-stub) not sum(per-stub).

    Each backend call sleeps 100ms in this test. With 5 stubs, sequential
    would take ≥500ms; concurrent should be ≤300ms (with overhead margin).
    """
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    stub_ids = [s.skill_id for s in lib.all_skills if s.skill_id.startswith("stub_")]

    call_times: list[float] = []

    def _slow_call(**kwargs):
        call_times.append(_time.monotonic())
        _time.sleep(0.1)  # simulate per-call latency
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(_good_payload()))],
            stop_reason="end_turn",
        )
    backend = MagicMock()
    backend.call.side_effect = _slow_call

    filler = StubFiller(library=lib, backend=backend)

    started = _time.monotonic()
    summary = await filler.afill_all_stubs(
        character="the silent",
        evidence_by_stub={sid: f"## Evidence {sid}" for sid in stub_ids},
    )
    elapsed = _time.monotonic() - started

    assert summary["filled_count"] == 5
    # Concurrent: all 5 calls should start within ~50ms of each other.
    # Sequential would have call_times[4] - call_times[0] >= 0.4s.
    assert call_times[-1] - call_times[0] < 0.05, (
        f"Backend calls were not concurrent — first to last gap "
        f"{call_times[-1] - call_times[0]:.3f}s suggests sequential dispatch"
    )
    # Total elapsed should be ~0.1s (one call's worth) + overhead
    assert elapsed < 0.4, (
        f"afill_all_stubs took {elapsed:.3f}s — sequential would be ~0.5s, "
        f"concurrent should be ~0.1-0.2s"
    )


@pytest.mark.asyncio
async def test_afill_all_stubs_handles_per_stub_errors_independently():
    """If backend.call raises for one stub, the other 4 must still complete."""
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    stub_ids = [s.skill_id for s in lib.all_skills if s.skill_id.startswith("stub_")]

    call_count = [0]
    def _flaky_call(**kwargs):
        call_count[0] += 1
        if call_count[0] == 3:
            raise RuntimeError("simulated backend failure")
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=json.dumps(_good_payload()))],
            stop_reason="end_turn",
        )
    backend = MagicMock()
    backend.call.side_effect = _flaky_call

    filler = StubFiller(library=lib, backend=backend)
    summary = await filler.afill_all_stubs(
        character="the silent",
        evidence_by_stub={sid: f"## Evidence {sid}" for sid in stub_ids},
    )
    assert summary["filled_count"] == 4  # one failed
    assert summary["skipped_count"] == 1


@pytest.mark.asyncio
async def test_afill_all_stubs_returns_same_shape_as_sync_version():
    """Async version returns the same summary dict shape as sync."""
    from src.skills.stub_filler import StubFiller

    lib = _stub_lib()
    backend = _backend_returning(_good_payload())
    filler = StubFiller(library=lib, backend=backend)
    summary = await filler.afill_all_stubs(
        character="the silent",
        evidence_by_stub={"stub_the_silent_combat": "## Evidence"},
    )
    assert "filled_count" in summary
    assert "skipped_count" in summary
    assert "warnings_by_stub" in summary
