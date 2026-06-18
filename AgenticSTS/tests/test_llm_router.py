"""Tests for the health-aware LLM router (src/brain/llm_router.py).

Covers:
  - Circuit breaker state transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
  - Hard fail triggers immediate model switch within same call
  - Subsequent calls bypass unhealthy model during cooldown
  - Half-open probe after cooldown expiry
  - Soft fail limited retries, no circuit breaker trip
  - Call class fallback chain ordering
  - Hedge gating on unhealthy models
  - All-unhealthy fallback to primary
  - classify_failure() for various exception types
  - relay_profile isolation (gameplay vs postrun)
  - preferred_model / preferred_provider respected by select_model
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import patch

import httpx
import pytest

import config
from src.brain.llm_router import (
    CircuitState,
    FailureType,
    LLMRouter,
    ModelHealth,
    ModelSelection,
    classify_failure,
    get_router,
    relay_profile_for_call_class,
    reset_router,
)


# ── Fixture ────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_router(monkeypatch):
    """Reset global router singleton before each test.

    Also forces ``LLM_DISABLE_FALLBACK=False`` so the router builds full
    cross-family fallback chains during testing — the production default
    (``True``) truncates every chain to its primary entry, which is what
    the user wants at runtime but breaks every fallback / circuit /
    failover test in this file.  Tests that exercise the disable behavior
    directly should re-set the attr inside the test body.
    """
    monkeypatch.setattr(config, "LLM_DISABLE_FALLBACK", False)
    reset_router()
    yield
    reset_router()


@pytest.fixture
def router() -> LLMRouter:
    """Create a fresh router with short cooldown for fast tests."""
    return LLMRouter(cooldown_sec=2.0, hard_fail_threshold=2)


# ── classify_failure ───────────────────────────────────────────

class TestClassifyFailure:
    def test_timeout_error_is_hard(self):
        assert classify_failure(asyncio.TimeoutError()) == FailureType.HARD

    def test_builtin_timeout_is_hard(self):
        assert classify_failure(TimeoutError()) == FailureType.HARD

    def test_httpx_timeout_is_hard(self):
        assert classify_failure(httpx.ReadTimeout("read timed out")) == FailureType.HARD

    def test_httpx_connect_error_is_hard(self):
        assert classify_failure(httpx.ConnectError("connection refused")) == FailureType.HARD

    def test_429_status_is_hard(self):
        req = httpx.Request("POST", "https://example.com")
        resp = httpx.Response(429, request=req)
        exc = httpx.HTTPStatusError("rate limited", request=req, response=resp)
        assert classify_failure(exc) == FailureType.HARD

    def test_502_status_is_hard(self):
        req = httpx.Request("POST", "https://example.com")
        resp = httpx.Response(502, request=req)
        exc = httpx.HTTPStatusError("bad gateway", request=req, response=resp)
        assert classify_failure(exc) == FailureType.HARD

    def test_quota_string_is_hard(self):
        assert classify_failure(RuntimeError("insufficient_quota for model")) == FailureType.HARD

    def test_upstream_string_is_hard(self):
        assert classify_failure(RuntimeError("upstream_error: relay down")) == FailureType.HARD

    def test_parse_error_is_soft(self):
        assert classify_failure(ValueError("No <decision> block found")) == FailureType.SOFT

    def test_generic_error_is_soft(self):
        assert classify_failure(RuntimeError("schema mismatch")) == FailureType.SOFT

    def test_unparseable_llm_response_is_hard(self):
        """V2Backend's UnparseableLLMResponse must classify as HARD so the
        router switches model on first occurrence rather than burning
        2-3 same-model retries.  Empirically (run 20260428_024454: 37
        unparseable failures, total LLM time ~2x a comparable F48 victory
        without the detector) same-model retry rarely recovers in <2
        attempts on proxy.example.com's Gemini stream."""
        from src.brain.v2_backend import UnparseableLLMResponse

        # Both empirical message shapes must classify HARD via the
        # "unparseable response" marker in _HARD_FAIL_MARKERS.
        truncated = UnparseableLLMResponse(
            "unparseable response (truncated_decision): "
            "model=gemini-3.1-pro-preview finish=none text_len=28 "
            "reasoning_len=4 completion_tok=0",
        )
        empty_visible = UnparseableLLMResponse(
            "unparseable response (empty_visible_with_tokens): "
            "model=gemini-3.1-pro-preview finish=stop text_len=0 "
            "reasoning_len=4311 completion_tok=4311",
        )
        assert classify_failure(truncated) == FailureType.HARD
        assert classify_failure(empty_visible) == FailureType.HARD


# ── Circuit breaker basics ─────────────────────────────────────

class TestCircuitBreaker:
    def test_new_model_starts_closed(self, router: LLMRouter):
        sel = router.select_model("gameplay_fast")
        assert sel.model  # should return something
        assert sel.is_probe is False

    def test_single_hard_fail_stays_closed(self, router: LLMRouter):
        """One hard fail below threshold keeps CLOSED."""
        sel = router.select_model("gameplay_fast")
        opened = router.report_failure(
            "gameplay_fast", sel.provider, sel.model, FailureType.HARD,
        )
        assert opened is False  # threshold is 2
        # Model still available
        sel2 = router.select_model("gameplay_fast")
        assert sel2.model == sel.model

    def test_two_hard_fails_opens_circuit(self, router: LLMRouter):
        """Two consecutive hard fails trip the circuit breaker."""
        sel = router.select_model("gameplay_fast")
        router.report_failure(
            "gameplay_fast", sel.provider, sel.model, FailureType.HARD,
        )
        opened = router.report_failure(
            "gameplay_fast", sel.provider, sel.model, FailureType.HARD,
        )
        assert opened is True
        # Next select should skip the primary and return fallback
        sel2 = router.select_model("gameplay_fast")
        assert sel2.model != sel.model

    def test_success_resets_circuit(self, router: LLMRouter):
        """A success after partial failures resets the counter."""
        sel = router.select_model("gameplay_fast")
        router.report_failure(
            "gameplay_fast", sel.provider, sel.model, FailureType.HARD,
        )
        router.report_success("gameplay_fast", sel.provider, sel.model)
        # Counter should be reset — another single fail shouldn't open
        opened = router.report_failure(
            "gameplay_fast", sel.provider, sel.model, FailureType.HARD,
        )
        assert opened is False

    def test_soft_fail_does_not_open_circuit(self, router: LLMRouter):
        """Soft fails never trip the circuit breaker."""
        sel = router.select_model("gameplay_fast")
        for _ in range(10):
            opened = router.report_failure(
                "gameplay_fast", sel.provider, sel.model, FailureType.SOFT,
            )
            assert opened is False
        # Model still available
        sel2 = router.select_model("gameplay_fast")
        assert sel2.model == sel.model


# ── Cooldown and half-open probe ───────────────────────────────

class TestCooldownAndProbe:
    def test_cooldown_skips_unhealthy(self, router: LLMRouter):
        """During cooldown, select_model bypasses the unhealthy model."""
        sel = router.select_model("gameplay_strategic")
        primary = sel.model
        # Open the circuit
        router.report_failure(
            "gameplay_strategic", sel.provider, primary, FailureType.HARD,
        )
        router.report_failure(
            "gameplay_strategic", sel.provider, primary, FailureType.HARD,
        )
        # Immediately after — should get fallback
        sel2 = router.select_model("gameplay_strategic")
        assert sel2.model != primary

    def test_half_open_probe_after_cooldown(self, router: LLMRouter):
        """After cooldown expires, a probe is allowed."""
        sel = router.select_model("gameplay_strategic")
        primary = sel.model
        provider = sel.provider
        # Open the circuit
        router.report_failure("gameplay_strategic", provider, primary, FailureType.HARD)
        router.report_failure("gameplay_strategic", provider, primary, FailureType.HARD)

        # Fast-forward past cooldown (manipulate health directly)
        key = router._health_key("default", provider, primary)
        with router._lock:
            router._health[key].last_failure_time = time.monotonic() - 10  # 10s ago > 2s cooldown

        # Now select should return a probe
        sel3 = router.select_model("gameplay_strategic")
        assert sel3.model == primary
        assert sel3.is_probe is True

    def test_probe_success_closes_circuit(self, router: LLMRouter):
        """Successful probe transitions HALF_OPEN → CLOSED."""
        sel = router.select_model("gameplay_strategic")
        primary = sel.model
        provider = sel.provider
        # Open circuit
        router.report_failure("gameplay_strategic", provider, primary, FailureType.HARD)
        router.report_failure("gameplay_strategic", provider, primary, FailureType.HARD)
        # Fast-forward past cooldown
        key = router._health_key("default", provider, primary)
        with router._lock:
            router._health[key].last_failure_time = time.monotonic() - 10

        # Probe
        probe = router.select_model("gameplay_strategic")
        assert probe.is_probe is True
        # Report success
        router.report_success("gameplay_strategic", provider, primary)
        # Should be back to CLOSED — select without probe flag
        sel4 = router.select_model("gameplay_strategic")
        assert sel4.model == primary
        assert sel4.is_probe is False

    def test_probe_failure_reopens_circuit(self, router: LLMRouter):
        """Failed probe transitions HALF_OPEN → OPEN."""
        sel = router.select_model("gameplay_strategic")
        primary = sel.model
        provider = sel.provider
        # Open circuit
        router.report_failure("gameplay_strategic", provider, primary, FailureType.HARD)
        router.report_failure("gameplay_strategic", provider, primary, FailureType.HARD)
        # Fast-forward
        key = router._health_key("default", provider, primary)
        with router._lock:
            router._health[key].last_failure_time = time.monotonic() - 10

        # Probe
        probe = router.select_model("gameplay_strategic")
        assert probe.is_probe is True
        # Report failure
        opened = router.report_failure(
            "gameplay_strategic", provider, primary, FailureType.HARD,
        )
        assert opened is True
        # Should skip primary again
        sel5 = router.select_model("gameplay_strategic")
        assert sel5.model != primary


# ── Fallback chain ordering ────────────────────────────────────

class TestFallbackChain:
    def test_get_fallback_returns_next_in_chain(self, router: LLMRouter):
        """get_fallback returns the next model after current."""
        chain = router.get_chain("gameplay_fast")
        assert len(chain) >= 2
        first_model = chain[0][1]
        fb = router.get_fallback("gameplay_fast", first_model)
        assert fb is not None
        assert fb.model == chain[1][1]

    def test_get_fallback_returns_none_at_end(self, router: LLMRouter):
        """get_fallback returns None when at end of chain."""
        chain = router.get_chain("gameplay_fast")
        last_model = chain[-1][1]
        fb = router.get_fallback("gameplay_fast", last_model)
        assert fb is None

    def test_disable_fallback_truncates_chain_to_primary(self, monkeypatch):
        """STS2_LLM_DISABLE_FALLBACK=true (the production default since
        2026-04-28) collapses every chain to its primary entry, so
        ``get_fallback`` always returns None.  Combined with
        ``LLM_RETRY_FOREVER=true`` this gives the user the desired
        "retry primary forever, never switch family" behavior."""
        # Override the autouse fixture's relax-for-tests setting.
        monkeypatch.setattr(config, "LLM_DISABLE_FALLBACK", True)
        reset_router()
        r = LLMRouter(cooldown_sec=2.0, hard_fail_threshold=2)
        for call_class in (
            "gameplay_fast", "gameplay_strategic", "gameplay_repair",
            "monitor_summary", "postrun_analysis", "postrun_summary",
            "evolution",
        ):
            chain = r.get_chain(call_class)
            assert len(chain) <= 1, (
                f"chain {call_class!r} should collapse to <=1 entry "
                f"when LLM_DISABLE_FALLBACK is set, got {chain}"
            )
            if chain:
                primary_model = chain[0][1]
                assert r.get_fallback(call_class, primary_model) is None

    def test_get_fallback_skips_unhealthy(self, router: LLMRouter):
        """get_fallback skips models with open circuit breakers."""
        chain = router.get_chain("gameplay_strategic")
        if len(chain) < 3:
            pytest.skip("Need at least 3 models in chain")
        first_model = chain[0][1]
        second_model = chain[1][1]
        second_provider = chain[1][0]
        # Open circuit on second model
        router.report_failure(
            "gameplay_strategic", second_provider, second_model, FailureType.HARD,
        )
        router.report_failure(
            "gameplay_strategic", second_provider, second_model, FailureType.HARD,
        )
        # Fallback from first should skip second
        fb = router.get_fallback("gameplay_strategic", first_model)
        assert fb is not None
        assert fb.model != second_model


# ── Hedge gating ───────────────────────────────────────────────

class TestHedgeGating:
    def test_hedge_ok_when_healthy(self, router: LLMRouter):
        sel = router.select_model("gameplay_fast")
        assert router.should_hedge("gameplay_fast", sel.provider, sel.model) is True

    def test_hedge_blocked_when_open(self, router: LLMRouter):
        sel = router.select_model("gameplay_fast")
        router.report_failure("gameplay_fast", sel.provider, sel.model, FailureType.HARD)
        router.report_failure("gameplay_fast", sel.provider, sel.model, FailureType.HARD)
        assert router.should_hedge("gameplay_fast", sel.provider, sel.model) is False


# ── All-unhealthy fallback ─────────────────────────────────────

class TestAllUnhealthy:
    def test_returns_primary_when_all_unhealthy(self, router: LLMRouter):
        """When all models are unhealthy, return primary anyway."""
        chain = router.get_chain("gameplay_fast")
        for provider, model in chain:
            router.report_failure("gameplay_fast", provider, model, FailureType.HARD)
            router.report_failure("gameplay_fast", provider, model, FailureType.HARD)
        sel = router.select_model("gameplay_fast")
        assert sel.model == chain[0][1]


# ── Introspection ──────────────────────────────────────────────

class TestIntrospection:
    def test_get_health_snapshot(self, router: LLMRouter):
        sel = router.select_model("gameplay_fast")
        router.report_success("gameplay_fast", sel.provider, sel.model)
        router.report_failure("gameplay_fast", sel.provider, sel.model, FailureType.SOFT)
        snapshot = router.get_health_snapshot()
        key = router._health_key("default", sel.provider, sel.model)
        assert key in snapshot
        assert snapshot[key]["total_successes"] == 1
        assert snapshot[key]["total_soft_fails"] == 1

    def test_get_stats(self, router: LLMRouter):
        stats = router.get_stats()
        assert "model_switches" in stats
        assert "probes_launched" in stats

    def test_reset_clears_state(self, router: LLMRouter):
        sel = router.select_model("gameplay_fast")
        router.report_failure("gameplay_fast", sel.provider, sel.model, FailureType.HARD)
        router.reset()
        assert router.get_health_snapshot() == {}


# ── Singleton ──────────────────────────────────────────────────

class TestSingleton:
    def test_get_router_returns_same_instance(self):
        r1 = get_router()
        r2 = get_router()
        assert r1 is r2

    def test_reset_router_creates_new_instance(self):
        r1 = get_router()
        reset_router()
        r2 = get_router()
        assert r1 is not r2


# ── relay_profile isolation ────────────────────────────────────

class TestRelayProfileIsolation:
    """Gameplay and postrun use the same model name but different relay
    profiles.  A failure on gameplay's relay_profile="default" must NOT
    pollute the health of postrun's relay_profile="postrun" or vice versa.
    """

    def test_gameplay_failure_does_not_affect_postrun(self, router: LLMRouter):
        """Opening circuit on gameplay_strategic leaves postrun_analysis healthy.

        Even when both chains contain the same model (e.g. gemini-3.1-pro),
        the health state is scoped by relay_profile.
        """
        gp_sel = router.select_model("gameplay_strategic")
        model = gp_sel.model
        provider = gp_sel.provider

        # Open circuit on gameplay (relay_profile="default")
        router.report_failure("gameplay_strategic", provider, model, FailureType.HARD)
        router.report_failure("gameplay_strategic", provider, model, FailureType.HARD)

        # gameplay_strategic should skip this model
        gp2 = router.select_model("gameplay_strategic")
        assert gp2.model != model

        # postrun health for the same model should still be CLOSED
        # (different relay_profile key). We can verify by checking the
        # health snapshot directly.
        snapshot = router.get_health_snapshot()
        gameplay_key = router._health_key("default", provider, model)
        postrun_key = router._health_key("postrun", provider, model)
        assert snapshot[gameplay_key]["state"] == "open"
        # postrun key either doesn't exist (CLOSED by default) or is still closed
        if postrun_key in snapshot:
            assert snapshot[postrun_key]["state"] == "closed"

    def test_postrun_failure_does_not_affect_gameplay(self, router: LLMRouter):
        """Opening circuit on postrun_analysis leaves gameplay_strategic healthy."""
        pr_sel = router.select_model("postrun_analysis")
        model = pr_sel.model
        provider = pr_sel.provider

        # Open circuit on postrun (relay_profile="postrun")
        router.report_failure("postrun_analysis", provider, model, FailureType.HARD)
        router.report_failure("postrun_analysis", provider, model, FailureType.HARD)

        # gameplay health for the same model should still be CLOSED
        snapshot = router.get_health_snapshot()
        postrun_key = router._health_key("postrun", provider, model)
        gameplay_key = router._health_key("default", provider, model)
        assert snapshot[postrun_key]["state"] == "open"
        if gameplay_key in snapshot:
            assert snapshot[gameplay_key]["state"] == "closed"

    def test_health_keys_include_relay_profile(self, router: LLMRouter):
        """Health keys are namespaced by relay_profile."""
        sel = router.select_model("gameplay_fast")
        router.report_success("gameplay_fast", sel.provider, sel.model)
        router.report_success("postrun_summary", sel.provider, sel.model)

        snapshot = router.get_health_snapshot()
        gameplay_key = router._health_key("default", sel.provider, sel.model)
        postrun_key = router._health_key("postrun", sel.provider, sel.model)
        assert gameplay_key in snapshot
        assert postrun_key in snapshot
        assert gameplay_key != postrun_key

    def test_relay_profile_for_call_class_mapping(self):
        """relay_profile_for_call_class returns correct profile per class."""
        assert relay_profile_for_call_class("gameplay_fast") == "default"
        assert relay_profile_for_call_class("gameplay_strategic") == "default"
        assert relay_profile_for_call_class("postrun_analysis") == "postrun"
        assert relay_profile_for_call_class("evolution") == "postrun"
        assert relay_profile_for_call_class("monitor_summary") == "postrun"


# ── preferred_model override ───────────────────────────────────

class TestPreferredModelOverride:
    """select_model should honour caller's preferred model if healthy,
    but fall back to the chain when it's unhealthy.
    """

    def test_preferred_model_used_when_healthy(self, router: LLMRouter):
        """When preferred_model is healthy, it's returned."""
        sel = router.select_model(
            "gameplay_fast",
            preferred_provider="openai_compatible",
            preferred_model="kimi-k2.5",
        )
        assert sel.model == "kimi-k2.5"

    def test_preferred_model_skipped_when_unhealthy(self, router: LLMRouter):
        """When preferred_model is OPEN, the chain takes over."""
        # Make kimi-k2.5 unhealthy on the gameplay relay
        router.report_failure(
            "gameplay_fast", "openai_compatible", "kimi-k2.5", FailureType.HARD,
        )
        router.report_failure(
            "gameplay_fast", "openai_compatible", "kimi-k2.5", FailureType.HARD,
        )
        sel = router.select_model(
            "gameplay_fast",
            preferred_provider="openai_compatible",
            preferred_model="kimi-k2.5",
        )
        # Should fall through to the chain head
        chain = router.get_chain("gameplay_fast")
        assert sel.model == chain[0][1]

    def test_preferred_model_not_in_chain_still_works(self, router: LLMRouter):
        """A preferred model not in the chain is tried first if healthy."""
        sel = router.select_model(
            "gameplay_strategic",
            preferred_provider="openai_compatible",
            preferred_model="custom-model-v3",
        )
        assert sel.model == "custom-model-v3"


# ── Integration scenario: gameplay hard fail → switch model ─────

class TestGameplayScenario:
    """Simulate the v2_engine call pattern with router."""

    def test_hard_fail_triggers_switch_within_call(self, router: LLMRouter):
        """Simulates: model A hard-fails → get_fallback → model B succeeds."""
        sel = router.select_model("gameplay_strategic")
        model_a = sel.model

        # Simulate hard fail
        router.report_failure(
            "gameplay_strategic", sel.provider, model_a,
            FailureType.HARD, error="502 bad gateway",
        )
        router.report_failure(
            "gameplay_strategic", sel.provider, model_a,
            FailureType.HARD, error="502 bad gateway",
        )

        # Get fallback within same call
        fb = router.get_fallback("gameplay_strategic", model_a)
        assert fb is not None
        model_b = fb.model
        assert model_b != model_a

        # Model B succeeds
        router.report_success("gameplay_strategic", fb.provider, model_b)

        # Subsequent call: model A still in cooldown, starts with B
        sel2 = router.select_model("gameplay_strategic")
        assert sel2.model != model_a  # skips A (OPEN)

    def test_postrun_fallback_on_timeout(self, router: LLMRouter):
        """Post-run now falls back on timeout, not just content_filter."""
        sel = router.select_model("postrun_analysis")
        model_a = sel.model

        # Simulate timeout (hard fail)
        router.report_failure(
            "postrun_analysis", sel.provider, model_a,
            FailureType.HARD, error="timeout",
        )
        router.report_failure(
            "postrun_analysis", sel.provider, model_a,
            FailureType.HARD, error="timeout",
        )

        # Should get fallback
        fb = router.get_fallback("postrun_analysis", model_a)
        if fb is not None:
            assert fb.model != model_a
