"""Health-aware LLM router with circuit breaker and call-class fallback.

Provides a unified model selection layer shared by gameplay (v2_engine),
post-run (llm_caller), evolution (evolution_engine), and monitor
(summarizer).  Tracks per-model health via a circuit breaker so that a
model proven unhealthy is quickly bypassed rather than retried on every
subsequent call.

Key concepts:
  - **CallClass**: logical grouping of LLM calls with its own fallback
    chain.  ``gameplay_fast``, ``gameplay_strategic``, ``postrun_analysis``,
    etc.
  - **FailureType**: ``HARD`` (timeout / 5xx / empty / 429 — switch model
    immediately) vs ``SOFT`` (parse error / format anomaly — small retry
    budget).
  - **CircuitBreaker**: per ``(relay_profile, provider, model)`` health
    state.  CLOSED → healthy, OPEN → bypass, HALF_OPEN → allow one probe.
    The ``relay_profile`` dimension isolates gameplay (``default``) from
    post-run (``postrun``) — they use different endpoints / credentials,
    so a failure on one should not pollute the other.
  - **Fallback matrix**: peer-model first (``gpt-5.4 ↔ gemini-3.1-pro``,
    ``gpt-5.4-mini ↔ gemini-3.1-flash-lite``), cross-tier only as last
    resort.
"""

from __future__ import annotations

import enum
import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── Failure classification ─────────────────────────────────────

class FailureType(enum.Enum):
    """Severity of an LLM call failure."""

    HARD = "hard"
    SOFT = "soft"


# Hard fail markers in exception text (lowercase).
_HARD_FAIL_MARKERS = (
    "timeout",
    "timed out",
    "read operation timed out",
    "429",
    "500",
    "502",
    "503",
    "504",
    "524",
    "connection reset",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "upstream",
    "upstream_error",
    "gateway timeout",
    "deadline exceeded",
    "insufficient_quota",
    "quota exceeded",
    "quota",
    "billing",
    "resource has been exhausted",
    "permission denied",
    "suspended",
    "consumer suspended",
    "consumer has no access",
    "consumer not entitled",
    "api key not valid",
    "invalid api key",
    "empty response",
    "0tok",
    # V2Backend's UnparseableLLMResponse — proxy-truncation detection.
    # Empirically (28_024454: 37 unparseable / 685 steps; 28_052109: 20 / 481)
    # same-model retry rarely succeeds in 1 attempt — it takes 2-3 retries,
    # roughly doubling per-run LLM time vs the older V2Engine repair-turn
    # path.  Reclassifying as HARD makes the router switch model on first
    # occurrence (gemini-pro → gemini-flash → gpt-5.4), which costs 1 extra
    # call per failure instead of 2-3.
    "unparseable response",
)


def classify_failure(exc: BaseException | str) -> FailureType:
    """Classify an LLM error as HARD or SOFT.

    HARD failures trigger immediate model switch and circuit breaker
    state change.  SOFT failures allow a small retry budget on the
    same model.
    """
    import asyncio
    import httpx

    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return FailureType.HARD
    if isinstance(exc, httpx.TimeoutException):
        return FailureType.HARD
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in {429, 500, 502, 503, 504}:
            return FailureType.HARD
        # some relays wrap upstream provider errors (quota, API key, suspended)
        # as 400 with an informative body.  Check the body for hard markers.
        if status == 400:
            try:
                body = (exc.response.text or "").lower()
            except Exception:
                body = ""
            for marker in _HARD_FAIL_MARKERS:
                if marker in body:
                    return FailureType.HARD
    if isinstance(exc, httpx.RequestError) and not isinstance(
        exc, httpx.HTTPStatusError
    ):
        return FailureType.HARD

    text = str(exc).lower()
    for marker in _HARD_FAIL_MARKERS:
        if marker in text:
            return FailureType.HARD

    return FailureType.SOFT


# ── Circuit breaker ────────────────────────────────────────────

class CircuitState(enum.Enum):
    CLOSED = "closed"        # healthy — route normally
    OPEN = "open"            # unhealthy — skip this model
    HALF_OPEN = "half_open"  # probing — allow one request


@dataclass
class ModelHealth:
    """Mutable health record for a single ``(provider, model)`` pair."""

    state: CircuitState = CircuitState.CLOSED
    consecutive_hard_fails: int = 0
    consecutive_slow: int = 0   # consecutive calls exceeding latency SLA
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    total_hard_fails: int = 0
    total_soft_fails: int = 0
    total_successes: int = 0
    # When state == HALF_OPEN, we allow one probe. If it fails, go back to
    # OPEN with a longer cooldown.
    probe_in_flight: bool = False

    def is_available(self, now: float, cooldown_sec: float) -> bool:
        """Whether this model can accept a request right now."""
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.HALF_OPEN:
            return not self.probe_in_flight
        # OPEN → check if cooldown has elapsed
        if now - self.last_failure_time >= cooldown_sec:
            return True  # caller should transition to HALF_OPEN
        return False


# ── Model selection result ─────────────────────────────────────

@dataclass(frozen=True)
class ModelSelection:
    """Result of ``select_model`` / ``get_fallback``."""

    provider: str
    model: str
    is_probe: bool = False  # True if this is a half-open probe


# ── Call classes ───────────────────────────────────────────────

# Each call class has a primary model and an ordered fallback chain.
# The chain encodes "capability parity" ordering:
#   1. Peer model (same capability tier, different provider)
#   2. Cross-tier model (different capability tier, last resort)
#
# Chains are populated at module init from config values.

@dataclass(frozen=True)
class _ChainEntry:
    provider: str
    model: str
    relay_profile: str = "default"  # "default" for gameplay, "postrun" for post-run


# Maps call_class prefix → relay_profile.
# Gameplay uses "default" relay, postrun/evolution/monitor use "postrun".
_CALL_CLASS_RELAY_PROFILE: dict[str, str] = {
    "gameplay_fast": "default",
    "gameplay_strategic": "default",
    "gameplay_repair": "default",
    "postrun_analysis": "postrun",
    "postrun_summary": "postrun",
    "evolution": "postrun",
    "monitor_summary": "postrun",
}


def relay_profile_for_call_class(call_class: str) -> str:
    """Return the relay_profile for a given call_class."""
    return _CALL_CLASS_RELAY_PROFILE.get(call_class, "default")


def _build_call_class_chains() -> dict[str, list[_ChainEntry]]:
    """Build fallback chains for each call class from config.

    Peers are derived from ``config._MODEL_FAMILIES`` and
    ``config.MODEL_FAMILY_FALLBACK``: for any model we can locate in the
    registry, its peers are the same-tier models of the fallback families
    (in declared order). Off-registry models use a coarse family heuristic.

    Called once at module load (and again after config changes in tests).
    """
    import config

    oai = "openai_compatible"
    fast_provider = config.get_tier_provider("fast") or oai
    strategic_provider = config.get_tier_provider("strategic") or oai
    analysis_provider = config.get_tier_provider("analysis")  # may be ""
    evolution_provider = config.get_tier_provider("evolution")  # may be ""

    fast_model = config.LLM_FAST_MODEL
    strategic_model = config.LLM_STRATEGIC_MODEL
    analysis_model = config.LLM_ANALYSIS_MODEL
    evolution_model = config.EVOLUTION_MODEL
    summary_model = config.MONITOR_SUMMARY_MODEL

    def _peer_entries(model: str, tier: str) -> list[tuple[str, str]]:
        """Return same-tier peer (provider, model) pairs from other families.

        Order: ``config.MODEL_FAMILY_FALLBACK``. Excludes the primary's
        family (detected via ``config._detect_model_family``) and any
        duplicates of ``model`` itself.

        Returns ``[]`` when ``config.LLM_DISABLE_FALLBACK`` is set so the
        cross-family fallover is fully suppressed at chain build time —
        without this gate, ``_peer_entries`` would still inject GPT / Qwen
        / Claude peers into every chain even though
        ``LLM_*_FALLBACK_MODELS`` was forced empty.
        """
        if config.LLM_DISABLE_FALLBACK:
            return []
        primary_family = config._detect_model_family(model)
        primary_lower = (model or "").strip().lower()
        peers: list[tuple[str, str]] = []
        seen: set[str] = {primary_lower} if primary_lower else set()
        for fam in config.MODEL_FAMILY_FALLBACK:
            if fam == primary_family:
                continue
            entry = config._family_tier_entry(fam, tier)
            if not entry:
                continue
            peer_model = entry["model"]
            key = peer_model.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            peers.append((config._family_provider(fam), peer_model))
        return peers

    def _chain(
        relay_profile: str,
        *entries: tuple[str, str] | None,
    ) -> list[_ChainEntry]:
        seen: set[str] = set()
        result: list[_ChainEntry] = []
        for item in entries:
            if item is None:
                continue
            provider, model = item
            if not model:
                continue
            key = model.strip().lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(_ChainEntry(
                provider=provider or oai,
                model=model,
                relay_profile=relay_profile,
            ))
        return result

    # Env-override fallback lists (e.g. STS2_STRATEGIC_FALLBACK_MODELS).
    # These are already registry-aware — they're tuple(m for _, m in chain)
    # unless explicitly overridden — so we feed them in as "extra" entries.
    strategic_extra = list(config.LLM_STRATEGIC_FALLBACK_MODELS)
    analysis_extra = list(config.LLM_ANALYSIS_FALLBACK_MODELS)

    chains: dict[str, list[_ChainEntry]] = {
        # ── Gameplay (relay_profile="default") ──
        # primary → same-tier peers → cross-tier (strategic) + its peers
        "gameplay_fast": _chain(
            "default",
            (fast_provider, fast_model),
            *_peer_entries(fast_model, "fast"),
            (strategic_provider, strategic_model),
            *_peer_entries(strategic_model, "strategic"),
        ),
        "gameplay_strategic": _chain(
            "default",
            (strategic_provider, strategic_model),
            *_peer_entries(strategic_model, "strategic"),
            *((oai, m) for m in strategic_extra),
            (fast_provider, fast_model),
            *_peer_entries(fast_model, "fast"),
        ),
        "gameplay_repair": _chain(
            "default",
            (strategic_provider, strategic_model),
            *_peer_entries(strategic_model, "strategic"),
            *((oai, m) for m in strategic_extra),
            (fast_provider, fast_model),
        ),
        # ── Monitor summary (relay_profile="postrun", always populated) ──
        "monitor_summary": _chain(
            "postrun",
            (oai, summary_model),
            *_peer_entries(summary_model, "fast"),
        ),
    }

    # ── Post-run (only when analysis tier is configured) ─────────
    # Families without an analysis tier (e.g. qwen) produce empty chains
    # here. Callers guard via config.postrun_effectively_enabled(); the
    # router returns early if these keys are ever resolved (caller should
    # not invoke postrun at all when disabled).
    if analysis_model:
        chains["postrun_analysis"] = _chain(
            "postrun",
            (analysis_provider or oai, analysis_model),
            *((oai, m) for m in analysis_extra),
            *_peer_entries(analysis_model, "analysis"),
            *_peer_entries(analysis_model, "strategic"),
        )
        chains["postrun_summary"] = _chain(
            "postrun",
            (oai, summary_model),
            *_peer_entries(summary_model, "fast"),
        )
    else:
        chains["postrun_analysis"] = []
        chains["postrun_summary"] = []

    if evolution_model:
        chains["evolution"] = _chain(
            "postrun",
            (evolution_provider or oai, evolution_model),
            *((oai, m) for m in analysis_extra),
            *_peer_entries(evolution_model, "analysis"),
            *_peer_entries(evolution_model, "strategic"),
        )
    else:
        chains["evolution"] = []

    # Master switch: when LLM_DISABLE_FALLBACK is set, truncate every chain
    # to its primary entry so ``get_fallback`` always returns None and the
    # caller's retry-forever loop keeps hitting the same model.  This
    # covers the cross-tier shortcuts (e.g. gameplay_strategic still
    # listing the fast model after strategic) that ``_peer_entries`` and
    # the env-override gating don't reach on their own.
    if config.LLM_DISABLE_FALLBACK:
        for key, chain in chains.items():
            if len(chain) > 1:
                chains[key] = chain[:1]

    return chains


# ── Router ─────────────────────────────────────────────────────

class LLMRouter:
    """Singleton health-aware model router.

    Thread-safe.  All callers share one instance so that a model
    marked unhealthy by gameplay is immediately bypassed by post-run,
    evolution, etc.
    """

    # Default circuit breaker parameters
    DEFAULT_COOLDOWN_SEC = 60.0
    DEFAULT_HARD_FAIL_THRESHOLD = 2  # consecutive hard fails → OPEN
    DEFAULT_HALF_OPEN_COOLDOWN_MULTIPLIER = 2.0  # double cooldown after failed probe

    def __init__(
        self,
        *,
        cooldown_sec: float = DEFAULT_COOLDOWN_SEC,
        hard_fail_threshold: int = DEFAULT_HARD_FAIL_THRESHOLD,
    ) -> None:
        self._lock = threading.Lock()
        self._health: dict[str, ModelHealth] = {}  # key = "relay_profile|provider|model"
        self._cooldown_sec = cooldown_sec
        self._hard_fail_threshold = hard_fail_threshold
        self._chains = _build_call_class_chains()
        # Telemetry counters
        self._switches: int = 0
        self._probes_launched: int = 0
        self._probes_succeeded: int = 0
        self._session_logger: object | None = None

    def set_session_logger(self, sl: object | None) -> None:
        """Attach a SessionLogger for telemetry."""
        self._session_logger = sl

    def rebuild_chains(self) -> None:
        """Re-read config and rebuild call-class chains.

        Call after config values change (primarily useful in tests).
        """
        with self._lock:
            self._chains = _build_call_class_chains()

    # ── Health key ─────────────────────────────────────────────

    @staticmethod
    def _health_key(relay_profile: str, provider: str, model: str) -> str:
        rp = (relay_profile or "default").strip().lower()
        return f"{rp}|{provider.strip().lower()}|{model.strip().lower()}"

    def _get_health(self, relay_profile: str, provider: str, model: str) -> ModelHealth:
        key = self._health_key(relay_profile, provider, model)
        health = self._health.get(key)
        if health is None:
            health = ModelHealth()
            self._health[key] = health
        return health

    # ── Model selection ────────────────────────────────────────

    def select_model(
        self,
        call_class: str,
        *,
        preferred_provider: str = "",
        preferred_model: str = "",
    ) -> ModelSelection:
        """Return the best available model for *call_class*.

        If *preferred_provider* and *preferred_model* are given, they are
        tried first (honouring the circuit breaker).  This allows the
        caller's tier routing to remain authoritative while the router
        still provides health-aware fallback.

        Skips models whose circuit breaker is OPEN (unless cooldown has
        elapsed, in which case a HALF_OPEN probe is allowed).  Falls
        through the chain in priority order.
        """
        chain = self._chains.get(call_class)
        if chain is None:
            logger.warning("LLMRouter: unknown call_class %r, using first configured chain", call_class)
            chain = next(
                (c for c in self._chains.values() if c),
                [],
            )
        if not chain:
            raise RuntimeError(
                f"LLMRouter: no models configured for call_class {call_class!r}. "
                f"This typically means the active model family declares no tier "
                f"for this call class (e.g. qwen has no 'analysis' tier and "
                f"postrun is disabled). Caller should check "
                f"config.postrun_effectively_enabled() before invoking postrun."
            )

        rp = chain[0].relay_profile if chain else "default"
        now = time.monotonic()

        def _try_entry(provider: str, model: str) -> ModelSelection | None:
            """Attempt to select *model* if its circuit breaker allows."""
            health = self._get_health(rp, provider, model)

            if health.state == CircuitState.CLOSED:
                return ModelSelection(provider=provider, model=model)

            if health.state == CircuitState.HALF_OPEN and not health.probe_in_flight:
                health.probe_in_flight = True
                self._probes_launched += 1
                self._log_router_event(
                    "half_open_probe",
                    call_class=call_class,
                    provider=provider,
                    model=model,
                )
                return ModelSelection(provider=provider, model=model, is_probe=True)

            if health.state == CircuitState.OPEN:
                if now - health.last_failure_time >= self._cooldown_sec:
                    health.state = CircuitState.HALF_OPEN
                    health.probe_in_flight = True
                    self._probes_launched += 1
                    self._log_router_event(
                        "cooldown_expired_probe",
                        call_class=call_class,
                        provider=provider,
                        model=model,
                    )
                    return ModelSelection(provider=provider, model=model, is_probe=True)

            return None  # unhealthy, skip

        with self._lock:
            # ── Try caller-preferred model first (if provided & healthy) ──
            if preferred_model:
                prov = preferred_provider or (chain[0].provider if chain else "openai_compatible")
                sel = _try_entry(prov, preferred_model)
                if sel is not None:
                    return sel

            # ── Walk the chain ──
            for entry in chain:
                sel = _try_entry(entry.provider, entry.model)
                if sel is not None:
                    return sel

            # All models unhealthy — use first in chain (best available)
            first = chain[0]
            logger.warning(
                "LLMRouter: all models unhealthy for %s, using primary %s anyway",
                call_class, first.model,
            )
            return ModelSelection(provider=first.provider, model=first.model)

    def get_fallback(
        self,
        call_class: str,
        current_model: str,
    ) -> ModelSelection | None:
        """Return the next healthy model after *current_model* in the chain.

        Returns None when no further fallbacks exist.
        """
        chain = self._chains.get(call_class, [])
        rp = chain[0].relay_profile if chain else "default"
        now = time.monotonic()

        # Find current model's position in chain
        current_lower = current_model.strip().lower()
        start_idx = 0
        for i, entry in enumerate(chain):
            if entry.model.strip().lower() == current_lower:
                start_idx = i + 1
                break

        with self._lock:
            for entry in chain[start_idx:]:
                health = self._get_health(rp, entry.provider, entry.model)
                if health.is_available(now, self._cooldown_sec):
                    self._switches += 1
                    self._log_router_event(
                        "model_switch",
                        call_class=call_class,
                        provider=entry.provider,
                        model=entry.model,
                        reason=f"fallback from {current_model}",
                    )
                    return ModelSelection(provider=entry.provider, model=entry.model)

        return None

    # ── Outcome reporting ──────────────────────────────────────

    def _rp_for_call_class(self, call_class: str) -> str:
        """Derive relay_profile from call_class, consulting chain metadata."""
        chain = self._chains.get(call_class)
        if chain:
            return chain[0].relay_profile
        return relay_profile_for_call_class(call_class)

    def report_success(
        self,
        call_class: str,
        provider: str,
        model: str,
        *,
        latency_ms: float = 0,
    ) -> None:
        """Record a successful LLM call.  Resets circuit breaker to CLOSED.

        If *latency_ms* exceeds ``ROUTER_SLOW_THRESHOLD_MS``, the call is
        counted as a "slow success".  After
        ``ROUTER_SLOW_CONSECUTIVE_LIMIT`` consecutive slow successes the
        model is soft-degraded (OPEN) so the router prefers faster peers.
        """
        import config as _cfg
        rp = self._rp_for_call_class(call_class)
        with self._lock:
            health = self._get_health(rp, provider, model)
            was_probe = health.state == CircuitState.HALF_OPEN
            health.state = CircuitState.CLOSED
            health.consecutive_hard_fails = 0
            health.last_success_time = time.monotonic()
            health.total_successes += 1
            health.probe_in_flight = False
            if was_probe:
                self._probes_succeeded += 1
                self._log_router_event(
                    "probe_success",
                    call_class=call_class,
                    provider=provider,
                    model=model,
                )

            # ── Latency-aware degradation ──
            slow_threshold = getattr(_cfg, "ROUTER_SLOW_THRESHOLD_MS", 45000)
            slow_limit = getattr(_cfg, "ROUTER_SLOW_CONSECUTIVE_LIMIT", 3)
            if latency_ms > 0 and slow_threshold > 0:
                if latency_ms > slow_threshold:
                    health.consecutive_slow += 1
                    if health.consecutive_slow >= slow_limit:
                        health.state = CircuitState.OPEN
                        health.last_failure_time = time.monotonic()
                        self._log_router_event(
                            "slow_degraded",
                            call_class=call_class,
                            provider=provider,
                            model=model,
                            consecutive_slow=health.consecutive_slow,
                            latency_ms=round(latency_ms),
                        )
                else:
                    health.consecutive_slow = 0

    def report_failure(
        self,
        call_class: str,
        provider: str,
        model: str,
        failure_type: FailureType,
        error: str = "",
    ) -> bool:
        """Record a failed LLM call.

        Returns True if the circuit breaker opened (caller should switch
        model immediately).
        """
        rp = self._rp_for_call_class(call_class)
        with self._lock:
            health = self._get_health(rp, provider, model)
            now = time.monotonic()

            if failure_type == FailureType.HARD:
                health.consecutive_hard_fails += 1
                health.total_hard_fails += 1
                health.last_failure_time = now

                if health.state == CircuitState.HALF_OPEN:
                    # Probe failed → back to OPEN with extended cooldown
                    health.state = CircuitState.OPEN
                    health.probe_in_flight = False
                    self._log_router_event(
                        "probe_failed",
                        call_class=call_class,
                        provider=provider,
                        model=model,
                        error=error,
                    )
                    return True

                if health.consecutive_hard_fails >= self._hard_fail_threshold:
                    health.state = CircuitState.OPEN
                    self._log_router_event(
                        "circuit_opened",
                        call_class=call_class,
                        provider=provider,
                        model=model,
                        consecutive_fails=health.consecutive_hard_fails,
                        error=error,
                    )
                    return True

            else:
                health.total_soft_fails += 1

            return False

    # ── Hedge gating ───────────────────────────────────────────

    def should_hedge(self, call_class: str, provider: str, model: str) -> bool:
        """Whether hedging is advisable for this model.

        Returns False if the model's circuit breaker is OPEN —
        hedging a known-bad model wastes traffic.
        """
        rp = self._rp_for_call_class(call_class)
        with self._lock:
            health = self._get_health(rp, provider, model)
            return health.state == CircuitState.CLOSED

    # ── Introspection ──────────────────────────────────────────

    def get_health_snapshot(self) -> dict[str, dict]:
        """Return a snapshot of all model health states (for diagnostics)."""
        with self._lock:
            return {
                key: {
                    "state": h.state.value,
                    "consecutive_hard_fails": h.consecutive_hard_fails,
                    "total_hard_fails": h.total_hard_fails,
                    "total_soft_fails": h.total_soft_fails,
                    "total_successes": h.total_successes,
                    "last_failure_age_sec": round(time.monotonic() - h.last_failure_time, 1)
                    if h.last_failure_time > 0 else None,
                }
                for key, h in self._health.items()
            }

    def get_stats(self) -> dict[str, int]:
        """Return aggregate telemetry counters."""
        return {
            "model_switches": self._switches,
            "probes_launched": self._probes_launched,
            "probes_succeeded": self._probes_succeeded,
        }

    def get_chain(self, call_class: str) -> list[tuple[str, str]]:
        """Return the fallback chain for a call class (for diagnostics)."""
        return [
            (e.provider, e.model)
            for e in self._chains.get(call_class, [])
        ]

    def reset(self) -> None:
        """Reset all health state (for tests)."""
        with self._lock:
            self._health.clear()
            self._switches = 0
            self._probes_launched = 0
            self._probes_succeeded = 0

    # ── Telemetry ──────────────────────────────────────────────

    def _log_router_event(self, event: str, **details: object) -> None:
        logger.info("LLMRouter: %s %s", event, details)
        sl = self._session_logger
        if sl is not None and hasattr(sl, "log_router_event"):
            try:
                sl.log_router_event(event=event, **details)
            except Exception:
                pass


# ── Singleton ──────────────────────────────────────────────────

_router: LLMRouter | None = None
_router_lock = threading.Lock()


def get_router() -> LLMRouter:
    """Return the global LLMRouter singleton."""
    global _router
    if _router is None:
        with _router_lock:
            if _router is None:
                import config
                cooldown = float(
                    getattr(config, "ROUTER_COOLDOWN_SEC", LLMRouter.DEFAULT_COOLDOWN_SEC)
                )
                threshold = int(
                    getattr(config, "ROUTER_HARD_FAIL_THRESHOLD", LLMRouter.DEFAULT_HARD_FAIL_THRESHOLD)
                )
                _router = LLMRouter(cooldown_sec=cooldown, hard_fail_threshold=threshold)
    return _router


def reset_router() -> None:
    """Reset the global singleton (for tests)."""
    global _router
    with _router_lock:
        _router = None
