"""Global configuration for AgenticSTS.

Model routing uses a single family registry:
    _MODEL_FAMILIES[family][tier] = {"model": <str>, "effort": <str>}

A family is a capability-paired set of models (fast + strategic, optionally
analysis) from one provider. Pick a family with ``STS2_MODEL_FAMILY`` and the
rest (models, thinking effort, provider, fallback chain) is derived. Per-tier
family overrides (``STS2_MODEL_FAMILY_FAST``), per-family effort overrides
(``STS2_QWEN_EFFORT_STRATEGIC``), and direct model overrides
(``STS2_FAST_MODEL``) are escape hatches.

Postrun (memory extraction, distillation, skill discovery, evolution) is
gated by (1) the ``STS2_POSTRUN_ENABLED`` flag and (2) whether the active
family declares an ``analysis`` tier. A family without ``analysis`` is
declaring "I don't do postrun" — useful for weak models where postrun would
poison the knowledge store. Weak gameplay families (qwen, deepseek) route
their analysis tier to gemini-3.1-pro-preview so postrun still runs with a
stronger model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# Load .env file if present (secrets stay out of git)
# Default policy: override — parent process env vars (e.g. Claude Code's
# ANTHROPIC_BASE_URL) should not shadow project-level .env values.
# Exception: a small allowlist of keys where explicit parent-process values
# (typically set by scripts/run_agent.py's _apply_pre_config_flags from CLI
# flags) MUST win over .env. These are keys whose .env entries are commonly
# stale "defaults" that the user wants the CLI to override.
_PRESERVE_IF_SET = {
    "STS2_MODEL_FAMILY",
    "STS2_FAST_MODEL",
    "STS2_STRATEGIC_MODEL",
    "STS2_ANALYSIS_MODEL",
    "STS2_EVOLUTION_MODEL",
    "STS2_THINK_EFFORT_FAST",
    "STS2_THINK_EFFORT_STRATEGIC",
    "STS2_THINK_EFFORT_ANALYSIS",
    "STS2_POSTRUN_ENABLED",
    "STS2_EVOLUTION_ENABLED",
    "STS2_SKILLS_ENABLED",
    "STS2_MEMORY_ENABLED",
    "STS2_MONITOR_ENABLED",
    # Ablation baseline gates (added 2026-04-26)
    "STS2_PROMPT_VARIANT",
    "STS2_PROMPT_HINT_FILTER",
    "STS2_KNOWLEDGE_STRICT",
    "STS2_STM_ENABLED",
    "STS2_COMBAT_CONVERSATION_ENABLED",
    "STS2_INCLUDE_BOSS_HP",
    "STS2_DISPLAY_LANGUAGE",
    # Storage roots (CRITICAL): subprocess-set values must NOT be clobbered
    # by .env. The ablation orchestrator passes per-experiment STS2_DATA_REPO
    # to isolate L4/L5 stores; if .env wins, every condition writes back to
    # the shared root and contaminates accumulated data.
    "STS2_DATA_REPO",
    "STS2_DATA_DIR",
    "STS2_RUNS_HISTORY_REPO",
    "STS2_MACHINE_ID",
}
_env_path = Path(__file__).parent / ".env"
if _env_path.is_file():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            if _k in _PRESERVE_IF_SET and _k in os.environ:
                continue  # CLI/shell-set value wins
            os.environ[_k] = _v.strip()

# ── Game MCP API ──────────────────────────────────────────────
MCP_BASE_URL = os.getenv("STS2_MCP_URL", "http://127.0.0.1:8128")
MCP_TIMEOUT = float(os.getenv("STS2_MCP_TIMEOUT", "30.0"))
MCP_POLL_INTERVAL = 0.15  # seconds between fallback state polls
SSE_ENABLED = os.getenv("STS2_SSE_ENABLED", "true").lower() in ("true", "1", "yes")

# ── Reward atomization ───────────────────────────────────────
# When true and the mod exposes `resolve_rewards`, the agent translates
# its `card_reward` decisions into a single atomic call that drains the
# entire reward chain in one round-trip (saving ~3-5 MCP calls per reward
# instance). Falls back to the legacy multi-step claim/open/pick flow
# when the mod doesn't expose the action (old mod compatibility).
RESOLVE_REWARDS_ATOMIC = os.getenv(
    "STS2_RESOLVE_REWARDS_ATOMIC", "true"
).lower() in ("true", "1", "yes")
# Upstream `/events/stream` emits lightweight event envelopes
# (`screen_changed`, `available_actions_changed`, etc.), not full state
# payloads. The client treats SSE as a wake-up signal and fetches `/state`
# when those events arrive. If SSE is unavailable, waits fall back to
# MCP_POLL_INTERVAL polling.

# ── LLM base config ───────────────────────────────────────────
# Legacy direct-dispatch knobs (still honoured by a handful of scripts/
# tests that predate the family registry).
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5.4")

# Fallback base URL for OpenAI-compatible backends. Empty by default so that
# a missing config does NOT silently register a localhost relay — that used
# to cause cross-family failover (e.g. gpt_family @ proxy.example.com timeout) to
# land on a non-existent local Ollama instance and 502.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
# For anthropic: SDK reads ANTHROPIC_API_KEY env var, or use LLM_API_KEY
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))
# OpenAI-compatible relays can use dedicated credentials, while still
# falling back to the older generic variables for local/dev setups.
OPENAI_COMPAT_BASE_URL = os.getenv(
    "OPENAI_COMPAT_BASE_URL",
    os.getenv("STS2_OPENAI_COMPAT_BASE_URL", LLM_BASE_URL),
)
OPENAI_COMPAT_API_KEY = os.getenv(
    "OPENAI_COMPAT_API_KEY",
    os.getenv("STS2_OPENAI_COMPAT_API_KEY", LLM_API_KEY),
)
OPENAI_COMPAT_FAILOVER_COOLDOWN_SEC = float(
    os.getenv("STS2_OPENAI_COMPAT_FAILOVER_COOLDOWN_SEC", "0"),
)
OPENAI_COMPAT_TIMEOUT_SEC = float(
    os.getenv("STS2_OPENAI_COMPAT_TIMEOUT_SEC", "600"),
)
# Read timeout — max gap between bytes from upstream.
# Strategic calls are now non-streaming (see V2Backend._should_stream_openai_compatible),
# so this is effectively the total wait for the upstream's first byte of the
# response body.  Sized to cover Gemini 3.1 Pro thinking + token generation.
# History: 90→60 on 2026-04-28 (kill silent-hang tails); 60→180 same day after
# strategic non-stream switch made chunk-level idle protection irrelevant;
# 180→120 on 2026-04-29 — 24h log analysis showed strategic max=118.6s, p99=70s,
# so 120s gives ~1.7× p99 headroom while cutting dead-stuck wait by 60s.
OPENAI_COMPAT_READ_TIMEOUT_SEC = float(
    os.getenv("STS2_OPENAI_COMPAT_READ_TIMEOUT_SEC", "120"),
)
# Fast tier read timeout — tighter than strategic since fast calls (hand_select,
# map step, single-card combat, potions, treasure) finish under 5s for 71% and
# under 20s for 97% of traffic. 24h log: p99=44s, max=95s, plus a tail of
# 180s ReadTimeouts on stuck connections. 45s sits just above p99, kills only
# ~1.2% of legitimate slow OK calls (45-95s tail) while cutting stuck-connection
# wait by 4× (180→45s). Set to 25s for more aggressive cut at the cost of ~3%.
OPENAI_COMPAT_FAST_READ_TIMEOUT_SEC = float(
    os.getenv("STS2_OPENAI_COMPAT_FAST_READ_TIMEOUT_SEC", "45"),
)
OPENAI_COMPAT_FIRST_CHUNK_DEADLINE_SEC = float(
    os.getenv("STS2_OPENAI_COMPAT_FIRST_CHUNK_DEADLINE_SEC", "10"),
)
OPENAI_COMPAT_HEDGE_ENABLED = (
    os.getenv("STS2_OPENAI_COMPAT_HEDGE_ENABLED", "true").lower()
    in ("1", "true", "yes")
)
POSTRUN_OPENAI_COMPAT_BASE_URL = os.getenv(
    "STS2_POSTRUN_OPENAI_COMPAT_BASE_URL",
    "",
)
POSTRUN_OPENAI_COMPAT_API_KEY = os.getenv(
    "STS2_POSTRUN_OPENAI_COMPAT_API_KEY",
    "",
)
# ── Per-Model-Family Credentials ─────────────────────────────
# When set, calls to a given model family use these credentials instead of
# the generic OPENAI_COMPAT / POSTRUN ones.  This allows different API keys
# per provider on the same a relay relay.  Only api_key is required; base_url
# defaults to OPENAI_COMPAT_BASE_URL if empty.
GPT_BASE_URL = os.getenv("STS2_GPT_BASE_URL", "")
GPT_API_KEY = os.getenv("STS2_GPT_API_KEY", "")
GEMINI_BASE_URL = os.getenv("STS2_GEMINI_BASE_URL", "")
GEMINI_API_KEY = os.getenv("STS2_GEMINI_API_KEY", "")
QWEN_BASE_URL = os.getenv("STS2_QWEN_BASE_URL", "")
QWEN_API_KEY = os.getenv("STS2_QWEN_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("STS2_DEEPSEEK_BASE_URL", "")
DEEPSEEK_API_KEY = os.getenv("STS2_DEEPSEEK_API_KEY", "")

LLM_RETRY_FOREVER = os.getenv("STS2_LLM_RETRY_FOREVER", "true").lower() in (
    "true",
    "1",
    "yes",
)
LLM_RETRY_BASE_DELAY_SEC = float(os.getenv("STS2_LLM_RETRY_BASE_DELAY_SEC", "3"))
LLM_RETRY_MAX_DELAY_SEC = float(os.getenv("STS2_LLM_RETRY_MAX_DELAY_SEC", "10"))
# Custom base URL for Anthropic API proxy (e.g. https://proxy.example.com)
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL", "")
ANTHROPIC_DISABLE_CACHE = os.getenv("STS2_ANTHROPIC_DISABLE_CACHE", "true").lower() in (
    "true",
    "1",
    "yes",
)

# Separate credentials for Opus models (e.g. direct Anthropic API when proxy lacks Opus access)
# When set, calls to claude-opus-* models use these credentials instead of the default ones.
OPUS_API_KEY = os.getenv("STS2_OPUS_API_KEY", "")
OPUS_BASE_URL = os.getenv("STS2_OPUS_BASE_URL", "")
OPUS_DISABLE_CACHE = os.getenv("STS2_OPUS_DISABLE_CACHE", "false").lower() in (
    "true",
    "1",
    "yes",
)

LLM_MAX_TOKENS = 4096
LLM_TEMPERATURE = 0

# ── Model Family Registry ─────────────────────────────────────
# Each family declares its capability-paired models + per-tier thinking
# effort. Postrun skips automatically for a family without an ``analysis``
# entry (double-safety alongside STS2_POSTRUN_ENABLED=false).
#
# Add a new family: drop an entry here + (optional) set its provider in
# ``_FAMILY_PROVIDER`` + define credentials via STS2_<FAMILY>_API_KEY /
# STS2_<FAMILY>_BASE_URL. ``llm_router`` derives peer chains from this
# registry automatically.
_MODEL_FAMILIES: dict[str, dict[str, dict[str, str]]] = {
    "gemini": {
        # 2026-04-28: fast tier swapped from gemini-3.1-flash-lite-preview
        # (no longer reachable on the proxy) to gemini-3-flash-preview.
        # 2026-04-29: strategic effort lowered medium → low. Empirically
        # gemini-3.1-pro at low is fast enough (5-10s/call vs 25-30s at
        # medium) without measurable decision-quality regression on STS2
        # combat plans / map / event / shop / reward — the determining
        # factor at this tier is access to retrieved memory + skills, not
        # extra Gemini chain-of-thought. Bump to medium per-tier via
        # STS2_GEMINI_EFFORT_STRATEGIC=medium if a specific experiment
        # needs deeper deliberation.
        "fast":      {"model": "gemini-3-flash-preview", "effort": "low"},
        "strategic": {"model": "gemini-3.1-pro-preview", "effort": "low"},
        "analysis":  {"model": "gemini-3.1-pro-preview", "effort": "high"},
    },
    "gpt": {
        "fast":      {"model": "gpt-5.4-mini",     "effort": "low"},
        "strategic": {"model": "gpt-5.4",          "effort": "medium"},
        "analysis":  {"model": "gpt-5.4-thinking", "effort": "high"},
    },
    "qwen": {
        # Weak-model test on DashScope (Alibaba Cloud official). Switched from
        # qwen3.5-35b-a3b → qwen3.5-27b on 2026-04-24 (35b-a3b MoE underperformed
        # on gameplay decisions). Bumped to qwen3.6-27b on 2026-05-07 for the
        # cross-model EMNLP probe (256K native context). `effort` maps to
        # enable_thinking: low → off (fast), medium/high → on.
        # Analysis tier borrows gemini-3.1-pro-preview — Qwen is too weak for
        # distillation / skill discovery, so we route postrun to a stronger
        # family. The relay auto-picks STS2_GEMINI_API_KEY via model-name lookup.
        "fast":      {"model": "qwen3.6-27b",            "effort": "low"},
        "strategic": {"model": "qwen3.6-27b",            "effort": "medium"},
        "analysis":  {"model": "gemini-3.1-pro-preview", "effort": "high"},
    },
    "claude": {
        "fast":      {"model": "claude-haiku-4-5",  "effort": "low"},
        "strategic": {"model": "claude-sonnet-4-6", "effort": "medium"},
        "analysis":  {"model": "claude-sonnet-4-6", "effort": "high"},
    },
    "deepseek": {
        # DeepSeek V4 family (2026-04-24 launch). Both Flash and Pro are
        # OpenAI-compatible at api.deepseek.com with 1M context + dual modes
        # (thinking / non-thinking). For the EMNLP cross-model probe we run
        # full Pro on both tiers (1.6T total / 49B active MoE, more capable
        # than Flash's 284B/13B — closes the gap toward Gemini Pro).
        # effort=low  → thinking disabled (fast tier).
        # effort=high → reasoning_effort="high" (strategic tier).
        # Smoke-test (2026-04-24, 5k-tok prompt, on Flash):
        #   high = 33.9s / 2.6k reasoning tok
        #   max  = 143.8s / 11.8k reasoning tok (4.24× slower, too slow for per-turn use)
        # Analysis tier borrows gemini-3.1-pro-preview for distillation / skill
        # discovery — relay auto-routes via STS2_GEMINI_API_KEY.
        "fast":      {"model": "deepseek-v4-pro",       "effort": "low"},
        "strategic": {"model": "deepseek-v4-pro",       "effort": "high"},
        "analysis":  {"model": "gemini-3.1-pro-preview", "effort": "high"},
    },
}

_FAMILY_PROVIDER: dict[str, str] = {
    "gemini":   "openai_compatible",
    "gpt":      "openai_compatible",
    "qwen":     "openai_compatible",
    "claude":   "anthropic",
    "deepseek": "openai_compatible",
}

# Active family (single switch; default Gemini). Per-tier overrides let you
# mix families (e.g. gemini-strategic + gpt-fast).
MODEL_FAMILY = os.getenv("STS2_MODEL_FAMILY", "gemini").strip().lower()
_FAST_FAMILY = os.getenv("STS2_MODEL_FAMILY_FAST", "").strip().lower() or MODEL_FAMILY
_STRATEGIC_FAMILY = os.getenv("STS2_MODEL_FAMILY_STRATEGIC", "").strip().lower() or MODEL_FAMILY
# Analysis + evolution default to following strategic's family. Postrun tiers
# share one family — mixing them across families is rarely useful.
_ANALYSIS_FAMILY = os.getenv("STS2_MODEL_FAMILY_ANALYSIS", "").strip().lower() or _STRATEGIC_FAMILY

# Fallback family order: when the primary family's model fails, try the same
# tier in these families in order.
MODEL_FAMILY_FALLBACK: tuple[str, ...] = tuple(
    f.strip().lower() for f in os.getenv(
        "STS2_MODEL_FAMILY_FALLBACK", "gemini,gpt,qwen,claude",
    ).split(",") if f.strip()
)


def _assert_family(name: str) -> None:
    if name not in _MODEL_FAMILIES:
        raise ValueError(
            f"Unknown model family: {name!r}. Known: {sorted(_MODEL_FAMILIES)}. "
            f"Register new families in config.py::_MODEL_FAMILIES + _FAMILY_PROVIDER."
        )


def _family_tier_entry(family: str, tier: str) -> dict[str, str] | None:
    """Return ``{"model": ..., "effort": ...}`` for a family×tier, or None if absent."""
    tiers = _MODEL_FAMILIES.get(family)
    if tiers is None:
        return None
    return tiers.get(tier)


def _resolve_effort(tier: str, family: str) -> str:
    """Resolve effort with precedence: per-family env > global env > registry default.

    Registry default falls back to an empty string when the family lacks
    the tier (caller should treat "" as "no thinking / not configured").
    """
    per_family_env = os.getenv(f"STS2_{family.upper()}_EFFORT_{tier.upper()}", "").strip()
    if per_family_env:
        return per_family_env
    global_env = os.getenv(f"STS2_THINK_EFFORT_{tier.upper()}", "").strip()
    if global_env:
        return global_env
    entry = _family_tier_entry(family, tier)
    default = entry["effort"] if entry else ""
    # STS2_QWEN_JSON_MODE: force qwen strategic effort to "low" (no thinking) so
    # response_format=json_object can be used (thinking mode is incompatible).
    # Resolved inline to avoid module-level ordering issues.
    if family == "qwen" and tier == "strategic" and \
            os.getenv("STS2_QWEN_JSON_MODE", "false").lower() in ("true", "1", "yes"):
        return "low"
    return default


def _resolve_tier_model(tier: str, family: str, explicit_env: str) -> str:
    """Resolve a tier's model with precedence: direct env override > registry.

    Returns an empty string when the family lacks the tier and no env
    override is set — callers must treat "" as "not configured".
    """
    if explicit_env:
        return explicit_env.strip()
    entry = _family_tier_entry(family, tier)
    return entry["model"] if entry else ""


# Sanity: the active fast + strategic families must declare those tiers.
_assert_family(_FAST_FAMILY)
_assert_family(_STRATEGIC_FAMILY)
if _family_tier_entry(_FAST_FAMILY, "fast") is None and not os.getenv("STS2_FAST_MODEL"):
    raise ValueError(
        f"Family {_FAST_FAMILY!r} has no 'fast' tier. Either register one in "
        f"_MODEL_FAMILIES or set STS2_FAST_MODEL explicitly."
    )
if _family_tier_entry(_STRATEGIC_FAMILY, "strategic") is None and not os.getenv("STS2_STRATEGIC_MODEL"):
    raise ValueError(
        f"Family {_STRATEGIC_FAMILY!r} has no 'strategic' tier. Either register one in "
        f"_MODEL_FAMILIES or set STS2_STRATEGIC_MODEL explicitly."
    )

# ── Resolved per-tier model + effort (back-compat exports) ─────
LLM_FAST_MODEL = _resolve_tier_model("fast", _FAST_FAMILY, os.getenv("STS2_FAST_MODEL", ""))
LLM_STRATEGIC_MODEL = _resolve_tier_model("strategic", _STRATEGIC_FAMILY, os.getenv("STS2_STRATEGIC_MODEL", ""))
LLM_ANALYSIS_MODEL = _resolve_tier_model("analysis", _ANALYSIS_FAMILY, os.getenv("STS2_ANALYSIS_MODEL", ""))
# Evolution falls back to analysis (same postrun tier) unless overridden.
EVOLUTION_MODEL = (
    os.getenv("STS2_EVOLUTION_MODEL", "").strip()
    or LLM_ANALYSIS_MODEL
)

# ── Providers (derived from family) ────────────────────────────
def _family_provider(family: str) -> str:
    _assert_family(family)
    return _FAMILY_PROVIDER.get(family, "openai_compatible")

LLM_FAST_PROVIDER = _family_provider(_FAST_FAMILY)
LLM_STRATEGIC_PROVIDER = _family_provider(_STRATEGIC_FAMILY)
LLM_ANALYSIS_PROVIDER = _family_provider(_ANALYSIS_FAMILY) if LLM_ANALYSIS_MODEL else ""
EVOLUTION_PROVIDER = LLM_ANALYSIS_PROVIDER or _family_provider(_ANALYSIS_FAMILY)
# Legacy default provider (used by a few callers that haven't migrated to
# tier-specific routing).
LLM_PROVIDER = LLM_STRATEGIC_PROVIDER

# ── Fallback chains (auto-derived from family fallback order) ──
# Master switch: when STS2_LLM_DISABLE_FALLBACK=true (the default as of
# 2026-04-28), every tier's fallback chain is forced empty regardless of
# MODEL_FAMILY_FALLBACK.  Combined with the existing LLM_RETRY_FOREVER=true
# default in llm_caller.py, this means a failing primary model retries on
# itself with backoff forever instead of switching to a peer family.  The
# user opted into this after observing that the cross-family fallbacks (gpt
# / qwen / claude relays) added latency without clear benefit when the
# primary (gemini) was the only family the deck-level prompts were tuned
# for.  Set STS2_LLM_DISABLE_FALLBACK=false to restore peer-family fallover.
LLM_DISABLE_FALLBACK = os.getenv(
    "STS2_LLM_DISABLE_FALLBACK", "true",
).lower() in ("true", "1", "yes")


def _build_fallback_chain(
    tier: str, primary_family: str, primary_model: str,
) -> tuple[tuple[str, str], ...]:
    """Return ``((provider, model), ...)`` fallback chain, excluding the primary.

    Returns an empty tuple when ``LLM_DISABLE_FALLBACK`` is set — the
    caller's retry-forever loop will keep hitting the primary instead of
    switching families.
    """
    if LLM_DISABLE_FALLBACK:
        return ()
    out: list[tuple[str, str]] = []
    seen: set[str] = {primary_model.lower()}
    for fam in MODEL_FAMILY_FALLBACK:
        if fam not in _MODEL_FAMILIES:
            continue
        entry = _family_tier_entry(fam, tier)
        if not entry:
            continue
        model = entry["model"]
        key = model.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((_family_provider(fam), model))
    return tuple(out)


_FAST_CHAIN = _build_fallback_chain("fast", _FAST_FAMILY, LLM_FAST_MODEL)
_STRATEGIC_CHAIN = _build_fallback_chain("strategic", _STRATEGIC_FAMILY, LLM_STRATEGIC_MODEL)
_ANALYSIS_CHAIN = (
    _build_fallback_chain("analysis", _ANALYSIS_FAMILY, LLM_ANALYSIS_MODEL)
    if LLM_ANALYSIS_MODEL else ()
)

def _env_fallback_override(env_name: str) -> tuple[str, ...] | None:
    """Parse a comma-separated env override into a fallback tuple, or None."""
    raw = os.getenv(env_name, "").strip()
    if not raw:
        return None
    return tuple(m.strip() for m in raw.split(",") if m.strip())


# Final fallback resolution.  ``LLM_DISABLE_FALLBACK`` (default true) wins
# over both env overrides (``STS2_*_FALLBACK_MODELS`` set in .env / shell)
# and registry-derived chains, so the user can flip the master switch
# without having to also unset every per-tier override.
LLM_FAST_FALLBACK_MODELS: tuple[str, ...] = () if LLM_DISABLE_FALLBACK else (
    _env_fallback_override("STS2_FAST_FALLBACK_MODELS")
    or tuple(m for _, m in _FAST_CHAIN)
)
LLM_STRATEGIC_FALLBACK_MODELS: tuple[str, ...] = () if LLM_DISABLE_FALLBACK else (
    _env_fallback_override("STS2_STRATEGIC_FALLBACK_MODELS")
    or tuple(m for _, m in _STRATEGIC_CHAIN)
)
LLM_ANALYSIS_FALLBACK_MODELS: tuple[str, ...] = () if LLM_DISABLE_FALLBACK else (
    _env_fallback_override("STS2_ANALYSIS_FALLBACK_MODELS")
    or tuple(m for _, m in _ANALYSIS_CHAIN)
)
EVOLUTION_FALLBACK_MODELS: tuple[str, ...] = () if LLM_DISABLE_FALLBACK else (
    _env_fallback_override("STS2_EVOLUTION_FALLBACK_MODELS")
    or LLM_ANALYSIS_FALLBACK_MODELS
)

# ── Thinking Mode ─────────────────────────────────────────────
# Effort is resolved via _resolve_effort: per-family env >
# global env (STS2_THINK_EFFORT_*) > registry default.
LLM_THINK_TYPE = os.getenv("STS2_THINK_TYPE", "adaptive")
LLM_THINK_EFFORT_FAST = _resolve_effort("fast", _FAST_FAMILY) or "low"
LLM_THINK_EFFORT_STRATEGIC = _resolve_effort("strategic", _STRATEGIC_FAMILY) or "medium"
LLM_THINK_EFFORT_ANALYSIS = _resolve_effort("analysis", _ANALYSIS_FAMILY) or "high"
# Budget for Batch API (legacy type=enabled mode, not adaptive)
LLM_THINK_BUDGET_ANALYSIS = int(os.getenv("STS2_THINK_BUDGET_ANALYSIS", "10000"))

# ── Paths ─────────────────────────────────────────────────────
# DATA_DIR names the *static* data root (knowledge/, patches/,
# version_compatibility.json). Dynamic subtrees (memory, skills, evolution,
# runs) resolve through src.storage.paths and honor STS2_DATA_REPO.
DATA_DIR = os.getenv("STS2_DATA_DIR", "data")
LOG_DIR = "logs"

# Lazy import of src.storage.paths to avoid ordering issues during bootstrap.
from src.storage import paths as _paths  # noqa: E402

# ── Memory (V2 HCM) ──────────────────────────────────────────
MEMORY_ENABLED = os.getenv("STS2_MEMORY_ENABLED", "true").lower() in ("true", "1", "yes")
MEMORY_DIR = str(_paths.memory_dir())
# Per-decision-type token budgets
COMBAT_MEMORY_TOKENS = 300          # budget for combat decisions
ROUTE_MEMORY_TOKENS = 250           # budget for map/route decisions
DECK_MEMORY_TOKENS = 300            # budget for card reward/shop decisions
REST_EVENT_MEMORY_TOKENS = 150      # budget for rest decisions
EVENT_MEMORY_TOKENS = 450            # budget for event decisions (separate from rest) — covers consolidated EventGuide (~280 tok) + 3 past event hints
MEMORY_TOTAL_TOKEN_CEILING = 600    # absolute max across all types

# ── Situation Classification ─────────────────────────────────
THREAT_LETHAL_HP_RATIO = float(os.getenv("STS2_THREAT_LETHAL_HP_RATIO", "0.5"))
THREAT_HIGH_DAMAGE = int(os.getenv("STS2_THREAT_HIGH_DAMAGE", "15"))
THREAT_MEDIUM_DAMAGE = int(os.getenv("STS2_THREAT_MEDIUM_DAMAGE", "8"))
UPCOMING_PATTERN_MIN_CONSISTENCY = float(os.getenv("STS2_UPCOMING_MIN_CONSISTENCY", "0.6"))

# ── Evidence-Gated Skill Discovery ───────────────────────────
CONFIRMED_THRESHOLD = float(os.getenv("STS2_CONFIRMED_THRESHOLD", "4.0"))
HYPOTHESIS_THRESHOLD = float(os.getenv("STS2_HYPOTHESIS_THRESHOLD", "2.0"))
MIN_EVIDENCE_SIMILARITY = float(os.getenv("STS2_MIN_EVIDENCE_SIMILARITY", "3.0"))
HYPOTHESES_DIR = str(_paths.evolution_dir())

# Consolidation
CONSOLIDATION_EVERY_N_RUNS = 1      # consolidate guides every run
CONSOLIDATION_MIN_EPISODES = 2      # min episodes before guide creation (lowered: sparse data)

# ── Skills ───────────────────────────────────────────────────
SKILLS_ENABLED = os.getenv("STS2_SKILLS_ENABLED", "true").lower() in ("true", "1", "yes")
SKILLS_DIR = str(_paths.skills_dir())
SKILLS_SEED_DIR = "src/skills/seeds"           # Built-in seed skills (shipped with code)
SKILLS_MAX_PER_PROMPT = int(os.getenv("STS2_SKILLS_MAX_PER_PROMPT", "7"))
# Deck-building decisions (card_reward, card_select, shop, hand_select, treasure)
# need a TIGHTER cap. Post-mortem of 2026-04-22 gemini-full ablation showed that
# injecting 5-7 archetype-specific skills per card_reward caused "archetype
# hopping" — every 3-4 picks the agent pivoted builds (Frontload→Poison→Shiv→
# Panache), ending up with an incoherent deck that died at the Act 2 boss.
# 3 skills keeps the most-relevant archetypal advice without overwhelming
# each pick with competing suggestions.
SKILLS_MAX_PER_PROMPT_DECKBUILDING = int(os.getenv("STS2_SKILLS_MAX_PER_PROMPT_DECKBUILDING", "3"))
SKILLS_MAX_INJECTION_TOKENS = int(os.getenv("STS2_SKILLS_MAX_INJECTION_TOKENS", "900"))
SKILLS_MIN_CONFIDENCE = 0.2                     # Below this, skill is auto-deactivated
MAX_ACTIVE_PER_CATEGORY = int(os.getenv("STS2_MAX_SKILLS_PER_CATEGORY", "15"))
SKILL_EXPLORATION_BONUS = float(os.getenv("STS2_SKILL_EXPLORATION_BONUS", "5.0"))
REPLAY_ENABLED = os.getenv("STS2_REPLAY_ENABLED", "true").lower() == "true"
REPLAY_MAX_ALTERNATIVES = int(os.getenv("STS2_REPLAY_MAX_ALTERNATIVES", "2"))
SKILL_EVAL_ENABLED = os.getenv("STS2_SKILL_EVAL", "false").lower() == "true"
SKILL_EVAL_MAX_REPLAYS = int(os.getenv("STS2_SKILL_EVAL_MAX_REPLAYS", "2"))
COHORT_SKILL_DISCOVERY_ENABLED = os.getenv("STS2_COHORT_SKILL_DISCOVERY", "true").lower() in (
    "true", "1", "yes"
)
MISTAKE_DISCOVERY_ENABLED = os.getenv("STS2_MISTAKE_DISCOVERY_ENABLED", "true").lower() in (
    "true", "1", "yes"
)
COHORT_MIN_WINS = int(os.getenv("STS2_COHORT_MIN_WINS", "5"))
COHORT_LOW_LOSS_PERCENTILE = float(os.getenv("STS2_COHORT_LOW_LOSS_PERCENTILE", "0.33"))
COHORT_LOW_LOSS_MIN = int(os.getenv("STS2_COHORT_LOW_LOSS_MIN", "3"))
COHORT_LOW_LOSS_MAX = int(os.getenv("STS2_COHORT_LOW_LOSS_MAX", "6"))
COHORT_MIN_RUNS = int(os.getenv("STS2_COHORT_MIN_RUNS", "2"))
COHORT_CLUSTER_JACCARD = float(os.getenv("STS2_COHORT_CLUSTER_JACCARD", "0.48"))
COHORT_CLUSTER_MIN_EPISODES = int(os.getenv("STS2_COHORT_CLUSTER_MIN_EPISODES", "3"))
COHORT_SHARED_CARD_SUPPORT = float(os.getenv("STS2_COHORT_SHARED_CARD_SUPPORT", "0.7"))
COHORT_DISCOVERY_MAX_COHORTS_PER_RUN = int(
    os.getenv("STS2_COHORT_MAX_COHORTS_PER_RUN", "3")
)
COHORT_DISCOVERY_MAX_LLM_CALLS_PER_RUN = int(
    os.getenv("STS2_COHORT_MAX_LLM_CALLS_PER_RUN", "6")
)

# ── Project root ───────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent

# ── Evolution (self-authoring) ──────────────────────────────
EVOLUTION_ENABLED = os.getenv("STS2_EVOLUTION_ENABLED", "true").lower() in ("true", "1", "yes")
EVOLUTION_DIR = str(_paths.evolution_dir())
EVOLUTION_TOOLS_DIR = str(_paths.evolution_tools_dir())
EVOLUTION_MIN_ROUNDS = int(os.getenv("STS2_EVOLUTION_MIN_ROUNDS", "4"))
# Bug A1 (2026-04-30): the 2026-04-25 spec lowered MAX_ROUNDS 6 → 3 to save tokens,
# but with READ_ONLY_ROUNDS=2 that left only 1 net write round. Empirically: 5/5
# postrun sessions produced action_count=0 (LLM exhausted budget on diagnostic
# queries before reaching write phase). Restored to 5 (net 3 write rounds), plus
# a final-round force-write safety net in evolution_engine.py.
EVOLUTION_MAX_ROUNDS = int(os.getenv("STS2_EVOLUTION_MAX_ROUNDS", "5"))
EVOLUTION_READ_ONLY_ROUNDS = int(os.getenv("STS2_EVOLUTION_READ_ONLY_ROUNDS", "2"))
# Soft target: disabled by default. Set >0 to enforce a cumulative input-token floor.
EVOLUTION_TARGET_INPUT_TOKENS = int(os.getenv("STS2_EVOLUTION_TARGET_INPUT_TOKENS", "0"))
EVOLUTION_REPLAY_TOKEN_BUDGET = int(os.getenv("STS2_EVOLUTION_REPLAY_TOKEN_BUDGET", "40000"))
EVOLUTION_ANOMALY_WORSE_LIMIT = int(os.getenv("STS2_EVOLUTION_ANOMALY_WORSE_LIMIT", "2"))
EVOLUTION_ANOMALY_BETTER_LIMIT = int(os.getenv("STS2_EVOLUTION_ANOMALY_BETTER_LIMIT", "2"))
# EVOLUTION_MODEL / EVOLUTION_FALLBACK_MODELS are resolved from the family
# registry earlier in this file (they follow the analysis tier). An explicit
# STS2_EVOLUTION_MODEL / STS2_EVOLUTION_FALLBACK_MODELS override is honoured
# there. Do not redefine them here.

# ── Ablation baseline gates (added 2026-04-26) ───────────────────────────
# Defaults preserve current ("full") behavior. The ablation runner
# (scripts/run_ablation.py) sets these to baseline values for the
# baseline-strict condition. See:
#   docs/superpowers/specs/2026-04-26-ablation-baseline-design.md

PROMPT_VARIANT = os.getenv("STS2_PROMPT_VARIANT", "full").lower()
"""'full' (default, current behavior) or 'baseline' (strip strategy heuristics)."""

PROMPT_HINT_FILTER = os.getenv("STS2_PROMPT_HINT_FILTER", "false").lower() in ("true", "1", "yes")
"""When True, skip _relic_fmt.format_relic_hints and _card_clarifications calls."""

KNOWLEDGE_STRICT = os.getenv("STS2_KNOWLEDGE_STRICT", "false").lower() in ("true", "1", "yes")
"""When True, knowledge injectors that leak non-visible info return empty."""

STM_ENABLED = os.getenv("STS2_STM_ENABLED", "true").lower() in ("true", "1", "yes")
"""When False, AgentLoop._get_short_term_ref / _hcm_short_term return None."""

# ── Mode B: seed stub self-evolution ──────────────────────────────
# (added 2026-05-03; see
#  docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md)

SEED_STUB_FILL_ENABLED = os.getenv("STS2_SEED_STUB_FILL_ENABLED", "false").lower() in ("true", "1", "yes")
"""Mode B: enable postrun stage 5 (StubFiller) to fill / update seed stubs."""

USE_SEED_STUBS = os.getenv("STS2_USE_SEED_STUBS", "false").lower() in ("true", "1", "yes")
"""Mode B: load character-parametric stub templates from src/skills/seeds_stubs/."""

DISABLE_SKILL_SEEDS = os.getenv("STS2_DISABLE_SKILL_SEEDS", "false").lower() in ("true", "1", "yes")
"""When True, skip loading expert seeds from src/skills/seeds/. Mode B uses this
to ensure agent-written stubs aren't blended with expert content."""

SEED_STUB_DIR = str(PROJECT_ROOT / "src/skills/seeds_stubs")
"""Path to the stub template directory."""

SEED_STUB_FILL_LOG = str(_paths.evolution_dir() / "stub_fill_log.jsonl")
"""Audit log for Mode B fills/updates (separate from evolution_log.jsonl)."""

COMBAT_CONVERSATION_ENABLED = os.getenv("STS2_COMBAT_CONVERSATION_ENABLED", "true").lower() in ("true", "1", "yes")
"""When False, V2Engine treats each combat turn as a fresh single-message conversation."""

INCLUDE_BOSS_HP = os.getenv("STS2_INCLUDE_BOSS_HP", "true").lower() in ("true", "1", "yes")
"""When False, prompts skip Boss HP target rendering (200/400/600 numbers)."""

# ── Health-Aware Router ──────────────────────────────────────────
ROUTER_COOLDOWN_SEC = float(os.getenv("STS2_ROUTER_COOLDOWN_SEC", "60"))
ROUTER_HARD_FAIL_THRESHOLD = int(os.getenv("STS2_ROUTER_HARD_FAIL_THRESHOLD", "2"))
# Max same-model retries before the router switches to fallback.
# Hard fails get 1 retry; soft fails get this many.
ROUTER_MAX_HARD_RETRIES = int(os.getenv("STS2_ROUTER_MAX_HARD_RETRIES", "1"))
ROUTER_MAX_SOFT_RETRIES = int(os.getenv("STS2_ROUTER_MAX_SOFT_RETRIES", "2"))
# Latency SLA: if a "successful" call exceeds this threshold (ms), it
# counts as a slow_success for the router's health tracking.  Consecutive
# slow successes degrade the model's priority.
ROUTER_SLOW_THRESHOLD_MS = float(os.getenv("STS2_ROUTER_SLOW_THRESHOLD_MS", "45000"))
ROUTER_SLOW_CONSECUTIVE_LIMIT = int(os.getenv("STS2_ROUTER_SLOW_CONSECUTIVE_LIMIT", "3"))

# Prompt-evolution (postrun prompt patches) removed 2026-04-18 —
# see docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md.
PROMPT_PATCH_BACKUP_DIR = f"{EVOLUTION_DIR}/patch_backups"

# ── Tool Retirement ──────────────────────────────────────────
TOOL_RETIREMENT_SWEEP_INTERVAL = int(os.getenv("STS2_TOOL_RETIREMENT_INTERVAL", "10"))
TOOL_RETIREMENT_MIN_AGE_RUNS = int(os.getenv("STS2_TOOL_RETIREMENT_MIN_AGE", "5"))
TOOL_RETIREMENT_SCORE_THRESHOLD = float(os.getenv("STS2_TOOL_RETIREMENT_THRESHOLD", "0.1"))
TOOL_RETIREMENT_DELETE_AFTER_SWEEPS = int(os.getenv("STS2_TOOL_RETIREMENT_DELETE_AFTER", "2"))

# ── Web Search ──────────────────────────────────────────────
WEB_SEARCH_ENABLED = os.getenv("STS2_WEB_SEARCH", "true").lower() in ("true", "1", "yes")
WEB_SEARCH_MODEL = os.getenv("STS2_WEB_SEARCH_MODEL", "claude-opus-4-6")

# ── Monitor Dashboard ─────────────────────────────────────────
MONITOR_ENABLED = os.getenv("STS2_MONITOR_ENABLED", "true").lower() in ("true", "1", "yes")
MONITOR_PORT = int(os.getenv("STS2_MONITOR_PORT", "8081"))
MONITOR_SUMMARY_ENABLED = os.getenv("STS2_MONITOR_SUMMARY", "false").lower() in ("true", "1", "yes")
MONITOR_SUMMARY_MODEL = os.getenv("STS2_MONITOR_SUMMARY_MODEL", "gpt-5.4-mini")

# ── Display Language ──────────────────────────────────────────
# When "zh", the LLM is asked to additionally produce a `reasoning_zh` field
# (Simplified Chinese translation of `reasoning`) for stream display. The
# canonical `reasoning` field stays English so memory + skills + parsing are
# unaffected. Default "en" emits no extra field.
DISPLAY_LANGUAGE = os.getenv("STS2_DISPLAY_LANGUAGE", "en").strip().lower()

# ── Agent ─────────────────────────────────────────────────────
ACTION_RETRY_MAX = 3
ANIMATION_WAIT_MAX = 5.0  # max seconds to wait for animation
STATE_CHANGE_TIMEOUT = 15.0  # max seconds to wait for state change after action
ACTION_DELAY = float(os.getenv("STS2_ACTION_DELAY", "0.6"))  # seconds after each action


# ── Model profile (run attribution) ───────────────────────────────
def build_model_profile() -> dict:
    """Snapshot of current model routing config for run attribution.

    Families + effort are captured alongside model names so two runs with
    identical models but different effort still hash to different profiles.
    """
    return {
        "fast_model": LLM_FAST_MODEL,
        "strategic_model": LLM_STRATEGIC_MODEL,
        "analysis_model": LLM_ANALYSIS_MODEL or None,
        "fast_effort": LLM_THINK_EFFORT_FAST,
        "strategic_effort": LLM_THINK_EFFORT_STRATEGIC,
        "analysis_effort": LLM_THINK_EFFORT_ANALYSIS if LLM_ANALYSIS_MODEL else None,
        "fast_family": _FAST_FAMILY,
        "strategic_family": _STRATEGIC_FAMILY,
        "analysis_family": _ANALYSIS_FAMILY if LLM_ANALYSIS_MODEL else None,
        "fast_provider": LLM_FAST_PROVIDER,
        "strategic_provider": LLM_STRATEGIC_PROVIDER,
        "memory_enabled": MEMORY_ENABLED,
        "skills_enabled": SKILLS_ENABLED,
        "evolution_enabled": EVOLUTION_ENABLED,
        "postrun_enabled": postrun_effectively_enabled(),
        # Ablation baseline gates
        "prompt_variant": PROMPT_VARIANT,
        "prompt_hint_filter": PROMPT_HINT_FILTER,
        "knowledge_strict": KNOWLEDGE_STRICT,
        "stm_enabled": STM_ENABLED,
        "combat_conversation_enabled": COMBAT_CONVERSATION_ENABLED,
        "include_boss_hp": INCLUDE_BOSS_HP,
    }


def model_profile_hash(profile: dict) -> str:
    """Stable 8-char hex hash for grouping runs by config."""
    import hashlib
    blob = json.dumps(profile, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:8]


def model_profile_label(profile: dict) -> str:
    """Human-readable label: 'strategic / fast'."""
    return f"{profile.get('strategic_model', '?')} / {profile.get('fast_model', '?')}"


def normalize_provider(provider: str | None) -> str:
    """Normalize provider aliases to the routing values used by the app."""
    value = (provider or LLM_PROVIDER or "anthropic").strip().lower()
    if value == "ollama":
        return "openai_compatible"
    return value


def get_tier_provider(tier: str) -> str:
    """Return the configured provider for a decision tier.

    Returns an empty string for the analysis/evolution tiers when the active
    family does not declare an analysis model — caller code should treat
    ``""`` as "tier unavailable, skip".
    """
    key = tier.strip().lower()
    if key == "fast":
        return normalize_provider(LLM_FAST_PROVIDER)
    if key == "strategic":
        return normalize_provider(LLM_STRATEGIC_PROVIDER)
    if key == "analysis":
        if not LLM_ANALYSIS_PROVIDER:
            return ""
        return normalize_provider(LLM_ANALYSIS_PROVIDER)
    if key == "evolution":
        if not EVOLUTION_PROVIDER:
            return ""
        return normalize_provider(EVOLUTION_PROVIDER)
    return normalize_provider(LLM_PROVIDER)


def provider_supports_tool_loop(provider: str | None) -> bool:
    """Whether the provider can participate in the V2 tool loop."""
    return normalize_provider(provider) in {"anthropic", "openai_compatible"}


def gameplay_supports_v2() -> bool:
    """Whether the configured gameplay tiers can use the V2 architecture."""
    return (
        provider_supports_tool_loop(LLM_FAST_PROVIDER)
        or provider_supports_tool_loop(LLM_STRATEGIC_PROVIDER)
    )


def _strip_env_quotes(value: str) -> str:
    """Strip surrounding quotes commonly used in ``.env`` files."""
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1].strip()
    return text


def normalize_openai_compat_profile(profile: str | None) -> str:
    """Normalize OpenAI-compatible relay profiles."""
    value = (profile or "default").strip().lower()
    if value == "postrun":
        return "postrun"
    return "default"


def get_openai_compat_base_url(profile: str | None = None) -> str:
    """Return the configured base URL for an OpenAI-compatible relay profile."""
    use_profile = normalize_openai_compat_profile(profile)
    if use_profile == "postrun":
        return _strip_env_quotes(
            POSTRUN_OPENAI_COMPAT_BASE_URL or OPENAI_COMPAT_BASE_URL or LLM_BASE_URL
        )
    return _strip_env_quotes(OPENAI_COMPAT_BASE_URL or LLM_BASE_URL)


def get_openai_compat_api_key(profile: str | None = None) -> str:
    """Return the configured API key for an OpenAI-compatible relay profile."""
    use_profile = normalize_openai_compat_profile(profile)
    if use_profile == "postrun":
        return _strip_env_quotes(
            POSTRUN_OPENAI_COMPAT_API_KEY or OPENAI_COMPAT_API_KEY or LLM_API_KEY
        )
    return _strip_env_quotes(OPENAI_COMPAT_API_KEY or LLM_API_KEY)


def _parse_named_relays(raw: str, *, default_prefix: str) -> tuple[dict[str, str], ...]:
    """Parse relay config from JSON or ``name|base_url|api_key`` entries.

    Supported formats:
      1. JSON array:
         ``[{"name":"primary","base_url":"https://a","api_key":"sk-..."}, ...]``
      2. Semicolon-separated entries:
         ``primary|https://a|sk-...;backup|https://b|sk-...``
         ``https://a|sk-...;https://b|sk-...`` also works (auto-named).
    """
    text = _strip_env_quotes(raw or "")
    if not text:
        return ()

    relays: list[dict[str, str]] = []

    if text.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            for idx, item in enumerate(payload, start=1):
                if not isinstance(item, dict):
                    continue
                base_url = _strip_env_quotes(str(item.get("base_url", "")))
                if not base_url:
                    continue
                api_key = _strip_env_quotes(str(item.get("api_key", "")))
                name = _strip_env_quotes(str(item.get("name") or f"{default_prefix}_{idx}"))
                relays.append({
                    "name": name or f"{default_prefix}_{idx}",
                    "base_url": base_url,
                    "api_key": api_key,
                })
            if relays:
                return tuple(relays)

    for idx, chunk in enumerate(text.split(";"), start=1):
        entry = _strip_env_quotes(chunk)
        if not entry:
            continue
        parts = [_strip_env_quotes(part) for part in entry.split("|")]
        if len(parts) == 2:
            name = f"{default_prefix}_{idx}"
            base_url, api_key = parts
        elif len(parts) >= 3:
            name, base_url, api_key = parts[:3]
            name = name or f"{default_prefix}_{idx}"
        else:
            continue
        if not base_url:
            continue
        relays.append({
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
        })

    return tuple(relays)


def get_openai_compat_relays(profile: str | None = None) -> tuple[dict[str, str], ...]:
    """Return configured OpenAI-compatible relay candidates in priority order."""
    use_profile = normalize_openai_compat_profile(profile)
    if use_profile == "postrun":
        explicit = _parse_named_relays(
            os.getenv("STS2_POSTRUN_OPENAI_COMPAT_RELAYS", ""),
            default_prefix="postrun_relay",
        )
        if explicit:
            return explicit

        base_url = get_openai_compat_base_url("postrun")
        if not base_url:
            return ()

        return ({
            "name": "postrun_primary",
            "base_url": base_url,
            "api_key": get_openai_compat_api_key("postrun"),
        },)

    explicit = _parse_named_relays(
        os.getenv("STS2_OPENAI_COMPAT_RELAYS", ""),
        default_prefix="openai_relay",
    )
    if explicit:
        return explicit

    base_url = get_openai_compat_base_url("default")
    if not base_url:
        return ()

    return ({
        "name": "openai_primary",
        "base_url": base_url,
        "api_key": get_openai_compat_api_key("default"),
    },)


def _detect_model_family(model: str) -> str:
    """Detect the model family from a model name string.

    First does a reverse lookup against the ``_MODEL_FAMILIES`` registry
    (exact match on any declared model in any tier). Falls back to string
    heuristics for off-registry variants (e.g. ``gpt-5.4-codex``,
    ``gemini-3-flash-preview``) that the fallback-chain may emit.
    """
    lower = (model or "").strip().lower()
    if not lower:
        return ""
    for fam, tiers in _MODEL_FAMILIES.items():
        for entry in tiers.values():
            if entry["model"].lower() == lower:
                return fam
    if lower.startswith("gpt-") or lower.startswith("gpt5") or "gpt-5" in lower or "gpt5" in lower:
        return "gpt"
    if "gemini" in lower:
        return "gemini"
    if "qwen" in lower or "qwq" in lower:
        return "qwen"
    if "claude" in lower:
        return "claude"
    if "deepseek" in lower:
        return "deepseek"
    return ""


def get_model_family_relay(model: str) -> dict[str, str] | None:
    """Return per-model-family relay credentials, or None if not configured.

    When ``STS2_<FAMILY>_API_KEY`` is set, calls to that model family use
    these credentials instead of the generic profile-level relay.
    ``base_url`` defaults to ``OPENAI_COMPAT_BASE_URL``. Supports all
    families registered in ``_MODEL_FAMILIES``.
    """
    family = _detect_model_family(model)
    if not family:
        return None
    api_key_env = f"STS2_{family.upper()}_API_KEY"
    base_url_env = f"STS2_{family.upper()}_BASE_URL"
    api_key = _strip_env_quotes(os.getenv(api_key_env, ""))
    if not api_key:
        return None
    base_url = _strip_env_quotes(os.getenv(base_url_env, ""))
    if not base_url:
        base_url = _strip_env_quotes(OPENAI_COMPAT_BASE_URL or LLM_BASE_URL)
    return {
        "name": f"{family}_family",
        "base_url": base_url,
        "api_key": api_key,
    }


def model_family_registry_snapshot() -> dict[str, dict[str, dict[str, str]]]:
    """Read-only view of the registry (copy), for logging / debugging."""
    return {
        fam: {tier: dict(entry) for tier, entry in tiers.items()}
        for fam, tiers in _MODEL_FAMILIES.items()
    }


WRITE_GATE_REAP_ENABLED: bool = (
    os.getenv("STS2_WRITE_GATE_REAP_ENABLED", "false").lower() == "true"
)

# ── Postrun Switch ────────────────────────────────────────────
# Double-safety model:
#   1) STS2_POSTRUN_ENABLED=false → explicit off (highest priority)
#   2) Active family has no `analysis` tier AND no STS2_ANALYSIS_MODEL env
#      override → implicit off (the family declared itself postrun-incapable)
POSTRUN_ENABLED: bool = os.getenv("STS2_POSTRUN_ENABLED", "true").lower() in (
    "true", "1", "yes",
)

# ── Combat trace postrun analysis ─────────────────────────────
# Master switch for rendering + passing combat traces into postrun
# build_analysis (Turn 1) and card_note_updater (Turn 2). When off,
# Turn 1 runs without trace context (original behavior) and Turn 2
# is skipped entirely.
POSTRUN_COMBAT_TRACE_ENABLED: bool = os.getenv(
    "STS2_POSTRUN_COMBAT_TRACE_ENABLED", "true",
).lower() in ("true", "1", "yes")

# Turn 2 write gate. When off, the card_note_updater LLM call still
# runs to produce log-only dry-run output but does NOT persist any
# note changes. Default flipped to true on 2026-04-25 after smoke
# test confirmed proposal quality; set env var to "false" to revert
# to dry-run observation mode.
POSTRUN_NOTE_UPDATE_ENABLED: bool = os.getenv(
    "STS2_POSTRUN_NOTE_UPDATE_ENABLED", "true",
).lower() in ("true", "1", "yes")

# Interrupted-run filter. Trace renderer is skipped when the floor
# sum of the last two completed combats is below this threshold —
# avoids spending tokens on short aborted runs whose decks are not
# meaningful enough to inform note updates.
POSTRUN_TRACE_MIN_FLOOR_SUM: int = int(
    os.getenv("STS2_POSTRUN_TRACE_MIN_FLOOR_SUM", "15"),
)

# Per-combat round cap. Combats exceeding this round count are
# dropped from the trace entirely (not truncated mid-combat) to
# avoid rendering an incomplete fight.
POSTRUN_TRACE_MAX_ROUNDS: int = int(
    os.getenv("STS2_POSTRUN_TRACE_MAX_ROUNDS", "30"),
)


def postrun_effectively_enabled() -> bool:
    """Whether postrun processing should run for the current config.

    Returns False when either (1) the user set STS2_POSTRUN_ENABLED=false,
    or (2) the active analysis family has no analysis tier model AND the
    user did not supply an STS2_ANALYSIS_MODEL override. Callers should
    short-circuit memory/skill/evolution stages when this is False.
    """
    if not POSTRUN_ENABLED:
        return False
    if not LLM_ANALYSIS_MODEL:
        return False
    return True


def postrun_disabled_reason() -> str:
    """Return a human-readable explanation of why postrun is disabled.

    Returns an empty string when postrun is effectively enabled.
    """
    if not POSTRUN_ENABLED:
        return "STS2_POSTRUN_ENABLED=false"
    if not LLM_ANALYSIS_MODEL:
        return (
            f"family {_ANALYSIS_FAMILY!r} declares no 'analysis' tier "
            f"and no STS2_ANALYSIS_MODEL override"
        )
    return ""
