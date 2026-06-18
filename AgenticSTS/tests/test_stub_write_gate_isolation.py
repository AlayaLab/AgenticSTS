"""WriteGate isolation: Mode B stubs cannot be created or modified by
mistake_discovery / self-evolution write paths.

These tests exercise WriteGate.check() directly. The gate decides
accept / update / merge / reject; persistence is the caller's responsibility,
so the relevant guard is that no decision ever returns a write action
against a stub-namespace id.
"""

from src.memory.write_gate import (
    Candidate,
    ExistingEntry,
    GateDecision,
    WriteGate,
)


def _gate() -> WriteGate:
    """Build a gate with no embedder (lexical-only fast path)."""
    # Force embedder unavailable so tests don't make network calls.
    # When embedder is unavailable, the gate falls back to "accept" for
    # non-stub candidates after Level 1 — which is what we want to verify
    # that the stub guard fires BEFORE that fallback.
    from src.memory.write_gate import EmbeddingClient
    embedder = EmbeddingClient()  # default: not configured -> available()=False

    class _NoEmbed:
        def available(self):
            return False
        def embed(self, *args, **kwargs):
            return []

    return WriteGate(embedder=_NoEmbed())


def test_gate_rejects_candidate_with_stub_prefix():
    """A skill named stub_* must be rejected — that namespace is reserved."""
    gate = _gate()
    cand = Candidate(
        kind="skill",
        name="stub_evil_attempt",
        content="Some evolved skill content trying to claim a stub id.",
    )
    decision = gate.check(cand, existing=[])
    assert decision.action == "reject"
    assert "stub" in decision.reason.lower() or "reserved" in decision.reason.lower()


def test_gate_rejects_update_targeting_existing_stub():
    """A non-stub candidate whose name exactly matches an existing stub
    (Level 1 match would normally return action=update) must be rejected
    because the target is in the stub namespace.
    """
    gate = _gate()
    cand = Candidate(
        kind="skill",
        name="stub_the_silent_combat",  # tries to update by exact-name match
        content="Hijacked content.",
    )
    existing = [
        ExistingEntry(
            id="stub_the_silent_combat",
            content="Real stub content",
            layer="L5",
        ),
    ]
    decision = gate.check(cand, existing=existing)
    # Either the prefix check on candidate.name catches this first,
    # OR the existing-id check catches it. Either way: reject.
    assert decision.action == "reject"
    assert "stub" in decision.reason.lower() or "reserved" in decision.reason.lower()


def test_gate_accepts_normal_candidate_with_no_stub_collision():
    """Non-stub candidate with no stub conflict should pass the guard
    (downstream gate logic decides accept vs update vs reject by similarity)."""
    gate = _gate()
    cand = Candidate(
        kind="skill",
        name="evolved_legit_skill",
        content="HP conservation: prefer the no-damage line over a faster line.",
    )
    decision = gate.check(cand, existing=[])
    # With embedder unavailable, gate falls back to accept (or rejects empty
    # content). For non-empty non-stub content, expect accept.
    assert decision.action == "accept"


def test_gate_filters_stub_entries_from_existing_when_evaluating_non_stub():
    """If a non-stub candidate has similar content to a stub, the gate must
    NOT propose update/merge against the stub. The stub is invisible to
    similarity matching from outside the stub pipeline.
    """
    gate = _gate()
    cand = Candidate(
        kind="skill",
        name="evolved_combat_principles",
        content="Use ALL energy each turn. Read intents BEFORE deciding offense vs defense.",
    )
    existing = [
        ExistingEntry(
            id="stub_the_silent_combat",
            content="Use ALL energy each turn. Read intents.",  # similar wording
            layer="L5",
        ),
    ]
    decision = gate.check(cand, existing=existing)
    # The gate must not propose a write against the stub. Either accept
    # (treat as novel) or reject for some other reason — but never update/merge
    # into stub_the_silent_combat.
    assert decision.target_id != "stub_the_silent_combat"
    assert decision.action in ("accept", "reject")
