"""Write gate for L4 memory and L5 skill candidates.

Implements the 4-level cascade from
``docs/superpowers/specs/2026-04-18-write-gate-and-retriever-filter-design.md``,
levels 1–3 only. Level 4 (batch LLM judge) short-circuits to
``DEFER_TO_JUDGE`` in this commit and will be implemented in a follow-up.

Commit 1 operates in **observation mode**: callers run ``check_and_log``, which
records the decision to ``data/evolution/write_gate_log.jsonl`` but does not
block persistence. Observation produces the labeled dataset needed to
recalibrate the §4.3 starting thresholds (see spec §13.2).

Public surface:
    Candidate — what callers submit to the gate.
    GateDecision — what they get back.
    WriteGate — the orchestrator; instantiate once per process.

Embedding model defaults to ``text-embedding-3-large`` via the OpenAI-compatible
relay at ``STS2_GPT_BASE_URL``. Override via the ``STS2_EMBEDDING_MODEL`` env var.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Literal, Sequence

import config

logger = logging.getLogger(__name__)


# ── Thresholds (see spec §13.2) ─────────────────────────────────────

# Against L1/L2/L3 pre-indexed static spans
L1_L2_L3_REJECT_COSINE = 0.70
L1_L2_L3_JUDGE_LOWER = 0.55

# Against existing L4/L5 entries
L4_L5_AUTO_REJECT_COSINE = 0.85
L4_L5_MERGE_OR_COEXIST_LOWER = 0.70  # [0.70, 0.85) split on trigger Jaccard
L4_L5_JUDGE_LOWER = 0.55

# Trigger-tag Jaccard
TRIGGER_JACCARD_SAME_CONTEXT = 0.60


# ── Data types ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Candidate:
    """A proposed skill / guide / rule / card-note to persist.

    ``kind`` is a small enum used for log/diagnostic grouping; the gate does
    not branch on it. Callers pass the same shape for all candidate types.
    """

    kind: Literal["skill", "guide", "rule", "card_note"]
    name: str  # caller-stable identifier (skill_id, guide key, rule_id, ...)
    content: str  # the natural-language body that goes into the prompt
    trigger_tags: frozenset[str] = field(default_factory=frozenset)
    target_layer: Literal["L4", "L5"] = "L5"
    source_run_id: str = ""


@dataclass(frozen=True)
class ExistingEntry:
    """An already-persisted L4/L5 entry that the gate compares against."""

    id: str
    content: str
    trigger_tags: frozenset[str] = field(default_factory=frozenset)
    layer: Literal["L4", "L5"] = "L5"


@dataclass(frozen=True)
class StaticSpan:
    """A pre-indexed span of L1/L2/L3 static prompt text."""

    span_id: str
    text: str
    layer: Literal["L1", "L2", "L3"]
    source_file: str


Action = Literal["accept", "update", "merge", "reject", "defer_to_judge"]


@dataclass(frozen=True)
class GateDecision:
    action: Action
    target_id: str | None = None
    reason: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


# ── Per-model relay routing ─────────────────────────────────────────


def _relay_for_model(model: str) -> tuple[str, str, str]:
    """Pick the (base_url, api_key, provider_label) for a given model.

    Gemini models (``gemini-*``) must route through the Gemini relay at
    ``STS2_GEMINI_BASE_URL`` with ``STS2_GEMINI_API_KEY`` — calling them
    through the GPT key the previous implementation did produces the
    ``No available channel for model gemini-... under group gpt-az``
    503 error we actually observed in production.

    Qwen models route through the Qwen relay. Everything else (GPT-family
    chat models, OpenAI-native embedding models like ``text-embedding-3-large``)
    defaults to the GPT relay — that endpoint is OpenAI-compatible for
    both ``/v1/chat/completions`` and ``/v1/embeddings``.
    """
    model_low = (model or "").lower()
    if model_low.startswith("gemini"):
        base = os.getenv("STS2_GEMINI_BASE_URL", "https://proxy.example.com")
        key = os.getenv("STS2_GEMINI_API_KEY", "")
        return base, key, "gemini"
    if model_low.startswith("qwen"):
        base = os.getenv("STS2_QWEN_BASE_URL", "https://proxy.example.com")
        key = os.getenv("STS2_QWEN_API_KEY", "")
        return base, key, "qwen"
    # Default → GPT relay (also the right answer for OpenAI embedding models).
    base = os.getenv("STS2_GPT_BASE_URL", "https://proxy.example.com")
    key = os.getenv("STS2_GPT_API_KEY", "")
    return base, key, "gpt"


def _normalize_openai_base_url(raw: str) -> str:
    """Strip trailing slash and ensure ``/v1`` suffix for OpenAI-compat SDKs."""
    b = raw.rstrip("/")
    if not b.endswith("/v1"):
        b = b + "/v1"
    return b


# ── Tokenization (lightweight; reused from src.skills.dedup via duck-import) ─


_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "when", "if", "then", "and", "or",
    "to", "in", "on", "at", "for", "with", "this", "that", "it", "of",
    "be", "do", "not", "no", "but", "by", "from", "as", "so",
})


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, remove stopwords."""
    tokens: set[str] = set()
    for word in text.lower().split():
        word = word.strip(".,!?;:\"'()-[]{}*/\\`")
        if word and word not in _STOPWORDS:
            tokens.add(word)
    return tokens


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


# ── Embedding client ────────────────────────────────────────────────


class EmbeddingClient:
    """Thin wrapper around the OpenAI-compatible embedding endpoint.

    Persists a file-backed cache keyed by sha256 of the input text, so repeated
    checks (e.g. re-indexing L1 on every process start, re-embedding existing
    skills on every gate check) cost nothing after the first run.

    If the environment does not provide ``STS2_GPT_API_KEY`` and no override,
    ``embed()`` raises ``EmbeddingUnavailableError``. Callers are expected to
    catch this and degrade gracefully — the gate falls back to lexical-only
    comparisons when embeddings are unavailable.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self.model = model or os.getenv("STS2_EMBEDDING_MODEL", "text-embedding-3-large")
        # Route by model via _relay_for_model so we pick the right API key +
        # base URL for the model family. Embedding models are OpenAI-native,
        # so they go to the GPT relay; this is still the correct default.
        if base_url is None:
            default_base, default_key, _ = _relay_for_model(self.model)
        else:
            default_base, default_key = base_url, ""
        self.base_url = _normalize_openai_base_url(default_base)
        # Distinguish "not passed" (None) from "explicitly disabled" ("").
        # `api_key=""` is the test hook to force the "no credentials" path;
        # falling back to env would defeat that.
        if api_key is None:
            self.api_key = default_key
        else:
            self.api_key = api_key
        self.cache_path = cache_path or Path(config.EVOLUTION_DIR) / "embedding_cache.json"
        self._cache: dict[str, list[float]] = {}
        self._cache_loaded = False
        self._lock = threading.Lock()

    # ── cache ─────────────────────────────────────────────────

    def _load_cache(self) -> None:
        if self._cache_loaded:
            return
        try:
            if self.cache_path.is_file():
                with self.cache_path.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list):
                            self._cache[k] = v
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("embedding cache load failed (%s) — starting empty", exc)
        self._cache_loaded = True

    def _flush_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(self.cache_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(self._cache, fh)
            tmp.replace(self.cache_path)
        except OSError as exc:
            logger.warning("embedding cache flush failed: %s", exc)

    @staticmethod
    def _key(text: str, model: str) -> str:
        h = hashlib.sha256()
        h.update(model.encode("utf-8"))
        h.update(b"\0")
        h.update(text.encode("utf-8"))
        return h.hexdigest()

    # ── public ────────────────────────────────────────────────

    def available(self) -> bool:
        return bool(self.api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one embedding per input text.

        Deduplicates identical inputs internally and serves cache hits first,
        only calling the remote API for cache misses.
        """
        if not self.api_key:
            raise EmbeddingUnavailableError("STS2_GPT_API_KEY not configured")
        if not texts:
            return []

        with self._lock:
            self._load_cache()
            keys = [self._key(t, self.model) for t in texts]
            missing_idx: list[int] = []
            missing_texts: list[str] = []
            # Only embed each unique missing text once, even if duplicated in input.
            seen: dict[str, int] = {}
            for i, (key, text) in enumerate(zip(keys, texts, strict=True)):
                if key in self._cache:
                    continue
                if key in seen:
                    continue
                seen[key] = i
                missing_idx.append(i)
                missing_texts.append(text)

            if missing_texts:
                from openai import OpenAI  # local import so tests can mock

                client = OpenAI(api_key=self.api_key, base_url=self.base_url)
                resp = client.embeddings.create(model=self.model, input=missing_texts)
                for i, data in zip(missing_idx, resp.data, strict=True):
                    self._cache[keys[i]] = list(data.embedding)
                self._flush_cache()

            return [self._cache[k] for k in keys]

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]


class EmbeddingUnavailableError(RuntimeError):
    pass


# ── Cosine helper ───────────────────────────────────────────────────


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    return dot / ((na ** 0.5) * (nb ** 0.5))


# ── Static L1/L2/L3 span index ──────────────────────────────────────


class StaticSpanIndex:
    """Pre-indexed L1 spans with cached embeddings.

    Commit 1 scope: only L1 (the 4 system prompts in src/brain/prompts/system.py).
    L2 and L3 extraction is deferred to a follow-up commit — they need AST
    parsing of state-template source files to separate static literals from
    f-string interpolations. Until then the index is L1-only and the §4.3
    L1/L2/L3 reject rule functionally reduces to "L1 reject".

    Index is persisted to ``data/evolution/l1_l2_l3_index.json`` keyed by
    source-file hash, so we only re-embed when system.py changes.
    """

    INDEX_PATH = "l1_l2_l3_index.json"

    def __init__(
        self,
        embedder: EmbeddingClient,
        *,
        evolution_dir: Path | None = None,
    ) -> None:
        self._embedder = embedder
        self._index_path = (evolution_dir or Path(config.EVOLUTION_DIR)) / self.INDEX_PATH
        self._spans: list[StaticSpan] = []
        self._vecs: list[list[float]] = []
        self._source_hash = ""
        self._lock = threading.Lock()

    # ── span extraction ──────────────────────────────────────

    def _collect_l1_spans(self) -> list[StaticSpan]:
        """Pull the 4 system prompts and split into span-sized chunks."""
        from src.brain.prompts.system import (
            SYSTEM_COMBAT,
            SYSTEM_COMBAT_BOSS,
            SYSTEM_DECKBUILD,
            SYSTEM_STRATEGIC,
        )

        source = "src/brain/prompts/system.py"
        sources: list[tuple[str, str]] = [
            ("SYSTEM_COMBAT", SYSTEM_COMBAT),
            ("SYSTEM_COMBAT_BOSS", SYSTEM_COMBAT_BOSS),
            ("SYSTEM_DECKBUILD", SYSTEM_DECKBUILD),
            ("SYSTEM_STRATEGIC", SYSTEM_STRATEGIC),
        ]
        out: list[StaticSpan] = []
        for name, text in sources:
            for i, chunk in enumerate(_split_at_markdown_sections(text)):
                chunk = chunk.strip()
                if len(chunk) < 40:
                    continue
                span_id = f"L1:{name}#{i}"
                out.append(
                    StaticSpan(
                        span_id=span_id,
                        text=chunk,
                        layer="L1",
                        source_file=f"{source}:{name}",
                    )
                )
        return out

    def _source_fingerprint(self) -> str:
        """Hash the span bodies — if any L1 text changes, the cache invalidates."""
        h = hashlib.sha256()
        for span in self._spans:
            h.update(span.text.encode("utf-8"))
            h.update(b"\0")
        return h.hexdigest()

    # ── load / build / persist ───────────────────────────────

    def rebuild_if_stale(self) -> None:
        with self._lock:
            candidate_spans = self._collect_l1_spans()
            h = hashlib.sha256()
            for span in candidate_spans:
                h.update(span.text.encode("utf-8"))
                h.update(b"\0")
            fingerprint = h.hexdigest()

            if self._spans and fingerprint == self._source_hash:
                return  # already in memory with matching hash

            # Try cache
            cached = self._try_load_cache(fingerprint)
            if cached is not None:
                spans, vecs = cached
                self._spans = spans
                self._vecs = vecs
                self._source_hash = fingerprint
                return

            # Cache miss → embed
            if not self._embedder.available():
                # Graceful degradation: store spans without vectors.
                logger.warning(
                    "StaticSpanIndex: no embedding API available; index will "
                    "have spans but no vectors (max_similarity will return 0)."
                )
                self._spans = candidate_spans
                self._vecs = []
                self._source_hash = fingerprint
                return

            texts = [s.text for s in candidate_spans]
            try:
                vecs = self._embedder.embed(texts)
            except Exception as exc:
                logger.warning("StaticSpanIndex: embed failed (%s); degrading", exc)
                self._spans = candidate_spans
                self._vecs = []
                self._source_hash = fingerprint
                return

            self._spans = candidate_spans
            self._vecs = vecs
            self._source_hash = fingerprint
            self._persist_cache()

    def _try_load_cache(
        self, fingerprint: str,
    ) -> tuple[list[StaticSpan], list[list[float]]] | None:
        try:
            if not self._index_path.is_file():
                return None
            with self._index_path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            if not isinstance(data, dict):
                return None
            if data.get("source_hash") != fingerprint:
                return None
            if data.get("embedding_model") != self._embedder.model:
                return None
            raw_spans = data.get("spans", [])
            raw_vecs = data.get("embeddings", [])
            if len(raw_spans) != len(raw_vecs):
                return None
            spans = [
                StaticSpan(
                    span_id=s["span_id"],
                    text=s["text"],
                    layer=s["layer"],
                    source_file=s["source_file"],
                )
                for s in raw_spans
            ]
            return spans, [list(v) for v in raw_vecs]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("StaticSpanIndex cache read failed: %s", exc)
            return None

    def _persist_cache(self) -> None:
        try:
            self._index_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "source_hash": self._source_hash,
                "embedding_model": self._embedder.model,
                "spans": [asdict(s) for s in self._spans],
                "embeddings": self._vecs,
                "persisted_at": time.time(),
            }
            tmp = self._index_path.with_suffix(self._index_path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(payload, fh)
            tmp.replace(self._index_path)
        except OSError as exc:
            logger.warning("StaticSpanIndex persist failed: %s", exc)

    # ── query ────────────────────────────────────────────────

    def max_similarity(
        self, embedding: Sequence[float],
    ) -> tuple[float, StaticSpan | None]:
        """Return (max cosine, offending span) across the index.

        Returns (0.0, None) if the index has no vectors (e.g. no API key).
        On dimension mismatch (usually from a cache file built by a
        different embedding model leaking into the live path — e.g. a test
        writing to the real cache dir), bust the in-memory cache and
        return 0 so the next call triggers a clean rebuild.
        """
        if not self._vecs:
            return 0.0, None
        if len(self._vecs[0]) != len(embedding):
            logger.warning(
                "StaticSpanIndex dim mismatch (cached %d vs probe %d) — "
                "invalidating cache and returning 0 for this call",
                len(self._vecs[0]), len(embedding),
            )
            self._vecs = []
            self._source_hash = ""
            # Best-effort wipe of the on-disk cache so the next rebuild is clean.
            try:
                if self._index_path.is_file():
                    self._index_path.unlink()
            except OSError:
                pass
            return 0.0, None
        best = -1.0
        best_span: StaticSpan | None = None
        for span, vec in zip(self._spans, self._vecs, strict=True):
            c = _cosine(embedding, vec)
            if c > best:
                best = c
                best_span = span
        return max(best, 0.0), best_span

    def spans_above(
        self, embedding: Sequence[float], threshold: float,
        *, max_results: int = 5,
    ) -> list[tuple[float, StaticSpan]]:
        """Return all (cosine, span) pairs whose cosine ≥ threshold.

        Sorted descending by cosine. Capped at ``max_results`` so the judge
        prompt stays small. Returns empty list if no vectors are loaded or
        if the cached dim does not match the probe (mirrors ``max_similarity``).
        """
        if not self._vecs or len(self._vecs[0]) != len(embedding):
            return []
        scored: list[tuple[float, StaticSpan]] = []
        for span, vec in zip(self._spans, self._vecs, strict=True):
            c = _cosine(embedding, vec)
            if c >= threshold:
                scored.append((c, span))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:max_results]

    @property
    def span_count(self) -> int:
        return len(self._spans)


_MD_HEADER_RE = re.compile(r"(?m)^(?=##\s|\*\*)")


def _split_at_markdown_sections(text: str) -> list[str]:
    """Split system-prompt text at `##` and `**` boundaries.

    Not perfect — just `lines.append`-style splits are fine for a 1000-token
    system prompt. Empty trailing fragments are filtered by caller.
    """
    parts = _MD_HEADER_RE.split(text)
    return [p for p in parts if p.strip()]


# ── Write gate ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class _NeighborScore:
    entry: ExistingEntry
    cosine: float
    trigger_jaccard: float


@dataclass(frozen=True)
class PendingSkillCandidate:
    """A ``defer_to_judge`` skill held in limbo until the batch judge verdict lands.

    ``request_id`` is the batch judge request id (see ``JudgeQueue.to_requests``).
    It is the join key between this buffer and ``BatchJudgeResult.candidate_judgements``.
    """

    skill: object  # duck-typed Skill — keeps write_gate.py decoupled from src.skills.models
    decision_action: str  # always "defer_to_judge" for now; retained for future kinds
    request_id: str


class WriteGate:
    """Levels 1–3 of the write-gate cascade.

    Level 4 (batch LLM judge) is stubbed — any Level-3 "defer" returns
    ``GateDecision(action='defer_to_judge', ...)`` and callers observe the
    decision but persist the candidate anyway during commit 1's observation
    mode.
    """

    def __init__(
        self,
        *,
        embedder: EmbeddingClient | None = None,
        static_index: StaticSpanIndex | None = None,
        log_path: Path | None = None,
        judge_queue: object | None = None,
    ) -> None:
        self._embedder = embedder or EmbeddingClient()
        self._static = static_index or StaticSpanIndex(self._embedder)
        self._log_path = log_path or Path(config.EVOLUTION_DIR) / "write_gate_log.jsonl"
        self._log_lock = threading.Lock()
        # Judge queue is duck-typed so write_gate.py doesn't import the
        # judge module (avoids a circular import; keeps Level 4 optional).
        self._judge_queue = judge_queue
        # Hold per-check state for the judge queue so check() can hand off
        # the candidate's neighbors and L1 spans without recomputing.
        self._last_neighbors: list[Any] = []
        self._last_l1_overlap: tuple[float, StaticSpan | None] = (0.0, None)
        self._last_judge_request_id: str = ""
        self._pending_skills: list[PendingSkillCandidate] = []
        self._pending_lock = threading.Lock()

    # ── core check ───────────────────────────────────────────

    def check(
        self,
        candidate: Candidate,
        existing: Sequence[ExistingEntry] = (),
    ) -> GateDecision:
        """Decide what to do with ``candidate``.

        Does not persist and does not log — see ``check_and_log``.
        """
        self._last_judge_request_id = ""

        # Mode B isolation guard: candidates in the stub_* namespace are reserved
        # for the seed stub fill pipeline (src/skills/stub_filler.py). Mistake
        # discovery and self-evolution must NOT create or modify stubs through
        # this gate. See docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md.
        if candidate.name.startswith("stub_"):
            return GateDecision(
                action="reject",
                reason="stub_namespace_reserved",
                meta={"note": "skill_id with 'stub_' prefix is managed by Mode B fill pipeline"},
            )
        # Filter stub entries out of the existing set so the gate is blind to
        # them when evaluating a non-stub candidate. This prevents update/merge
        # decisions from ever targeting a stub id.
        existing = tuple(e for e in existing if not e.id.startswith("stub_"))

        # Level 1 — exact name / id match.
        for e in existing:
            if e.id == candidate.name and e.layer == candidate.target_layer:
                return GateDecision(
                    action="update",
                    target_id=e.id,
                    reason="exact_name_match",
                    meta={"level": 1},
                )

        # Need L1/L2/L3 index before any embedding work.
        try:
            self._static.rebuild_if_stale()
        except Exception as exc:
            logger.warning("static index rebuild failed: %s — proceeding without", exc)

        # Level 3 requires embeddings. If the embedder is unavailable, fall
        # back to lexical-only: we keep Level-2 (Jaccard) as a signal but
        # otherwise auto-accept. This matches commit 1's observation posture.
        if not self._embedder.available():
            return GateDecision(
                action="accept",
                reason="embedder_unavailable_fallback",
                meta={"level": 0, "note": "lexical-only path"},
            )

        # Guard: the OpenAI embeddings endpoint rejects empty strings with
        # ``'$.input' is invalid``. Skip the round-trip entirely when the
        # candidate body is empty — no meaningful similarity can be computed.
        if not (candidate.content or "").strip():
            return GateDecision(
                action="reject",
                reason="empty_content",
                meta={"level": 0, "note": "candidate.content is empty/whitespace"},
            )

        # Filter out existing entries with empty bodies for the same reason;
        # we keep the list shape aligned with ``texts`` below so the post-embed
        # zip still pairs each vector with the right ``ExistingEntry``.
        existing_non_empty: list[ExistingEntry] = [
            e for e in existing if (e.content or "").strip()
        ]

        # Embed candidate and all existing entries in one batch call so that
        # cache hits dominate future postruns.
        try:
            texts = [candidate.content] + [e.content for e in existing_non_empty]
            vecs = self._embedder.embed(texts)
        except Exception as exc:
            logger.warning("candidate embed failed: %s — using lexical+LLM fallback", exc)
            return self._embed_failed_fallback(
                candidate, existing_non_empty, embed_error=str(exc)
            )

        cand_vec = vecs[0]
        existing_vecs = vecs[1:]

        # Level 3a — L1/L2/L3 overlap check.
        l1_cos, l1_span = self._static.max_similarity(cand_vec)
        if l1_cos >= L1_L2_L3_REJECT_COSINE:
            return GateDecision(
                action="reject",
                reason=f"l1_overlap:{l1_span.span_id if l1_span else '?'}",
                meta={
                    "level": 3,
                    "l1_cosine": l1_cos,
                    "l1_span_id": l1_span.span_id if l1_span else None,
                },
            )

        # Level 3b — L4/L5 comparison.
        neighbors: list[_NeighborScore] = []
        for e, vec in zip(existing_non_empty, existing_vecs, strict=True):
            c = _cosine(cand_vec, vec)
            j = _jaccard(candidate.trigger_tags, e.trigger_tags)
            neighbors.append(_NeighborScore(e, c, j))
        neighbors.sort(key=lambda n: n.cosine, reverse=True)
        top = neighbors[0] if neighbors else None
        top_cos = top.cosine if top else 0.0
        top_jaccard = top.trigger_jaccard if top else 0.0

        if top is not None and top.cosine >= L4_L5_AUTO_REJECT_COSINE:
            return GateDecision(
                action="reject",
                target_id=top.entry.id,
                reason="l4l5_auto_duplicate",
                meta={"level": 3, "cosine": top.cosine, "trigger_jaccard": top.trigger_jaccard},
            )

        if top is not None and L4_L5_MERGE_OR_COEXIST_LOWER <= top.cosine < L4_L5_AUTO_REJECT_COSINE:
            if top.trigger_jaccard >= TRIGGER_JACCARD_SAME_CONTEXT:
                return GateDecision(
                    action="merge",
                    target_id=top.entry.id,
                    reason="same_trigger_similar_content",
                    meta={"level": 3, "cosine": top.cosine, "trigger_jaccard": top.trigger_jaccard},
                )
            return GateDecision(
                action="accept",
                reason="distinct_trigger_context_variant",
                meta={"level": 3, "cosine": top.cosine, "trigger_jaccard": top.trigger_jaccard},
            )

        # Judge zone (against L1/L2/L3 OR against L4/L5 neighbours).
        if (L1_L2_L3_JUDGE_LOWER <= l1_cos < L1_L2_L3_REJECT_COSINE
                or (top is not None and L4_L5_JUDGE_LOWER <= top.cosine < L4_L5_MERGE_OR_COEXIST_LOWER)):
            self._last_judge_request_id = self._maybe_enqueue_for_judge(
                candidate, neighbors, cand_vec,
            )
            return GateDecision(
                action="defer_to_judge",
                target_id=top.entry.id if top else None,
                reason="below_reject_above_accept",
                meta={
                    "level": 3,
                    "l1_cosine": l1_cos,
                    "l1_span_id": l1_span.span_id if l1_span else None,
                    "top_cosine": top_cos,
                    "top_trigger_jaccard": top_jaccard,
                },
            )

        # Below all thresholds.
        return GateDecision(
            action="accept",
            reason="below_all_thresholds",
            meta={
                "level": 3,
                "l1_cosine": l1_cos,
                "top_cosine": top_cos,
                "top_trigger_jaccard": top_jaccard,
            },
        )

    # ── embed-failure fallback ───────────────────────────────

    def _embed_failed_fallback(
        self,
        candidate: Candidate,
        existing: list[ExistingEntry],
        *,
        embed_error: str = "",
    ) -> GateDecision:
        """Fallback when the embedding API call fails for a non-empty candidate.

        Asks the fast Gemini model for a DUPLICATE / UNIQUE verdict against the
        top-5 existing entries (picked by lexical Jaccard for ranking only, not
        as a gate).  If the LLM call also fails, defer_to_judge — never
        blind-accept on failure.
        """
        if not existing:
            return GateDecision(
                action="accept",
                reason="embed_failed_no_existing",
                meta={"level": 0, "embed_error": embed_error},
            )

        cand_tokens = _tokenize(candidate.content)
        top_similar: list[tuple[float, ExistingEntry]] = sorted(
            ((_jaccard(cand_tokens, _tokenize(e.content)), e) for e in existing),
            key=lambda x: x[0],
            reverse=True,
        )[:5]

        try:
            return self._fast_llm_dup_check(candidate, top_similar, embed_error=embed_error)
        except Exception as llm_exc:
            logger.warning("LLM dup-check fallback also failed: %s — deferring", llm_exc)
            return GateDecision(
                action="defer_to_judge",
                reason="embed_failed_llm_also_failed",
                meta={
                    "level": 0,
                    "embed_error": embed_error,
                    "llm_error": str(llm_exc),
                },
            )

    def _fast_llm_dup_check(
        self,
        candidate: Candidate,
        similar: list[tuple[float, ExistingEntry]],
        *,
        embed_error: str = "",
    ) -> GateDecision:
        """Call the fast Gemini model for a DUPLICATE / UNIQUE verdict.

        Used when embedding fails but lexical similarity is high enough to
        warrant a semantic check before accepting.
        """
        fast_model = (
            os.getenv("STS2_FAST_MODEL", "").strip()
            or config.LLM_FAST_MODEL
        )
        if not fast_model:
            raise RuntimeError("No fast model resolved for dedup judge")
        base_url, api_key, _ = _relay_for_model(fast_model)
        if not api_key:
            raise RuntimeError(f"No API key configured for fast model {fast_model!r}")

        similar_text = "\n\n".join(
            f"[Existing #{i + 1}] (jaccard={j:.2f})\n{e.content[:400]}"
            for i, (j, e) in enumerate(similar)
        )
        prompt = (
            "You are a skill library deduplication judge.\n"
            "Decide if the CANDIDATE skill is a semantic DUPLICATE of any of the EXISTING skills.\n\n"
            f"CANDIDATE:\n{candidate.content[:500]}\n\n"
            f"EXISTING:\n{similar_text}\n\n"
            "Reply with exactly one word:\n"
            "  DUPLICATE  — if the candidate largely repeats existing knowledge\n"
            "  UNIQUE     — if the candidate adds distinct value not covered above"
        )

        from openai import OpenAI
        client = OpenAI(
            api_key=api_key,
            base_url=_normalize_openai_base_url(base_url),
        )
        resp = client.chat.completions.create(
            model=fast_model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.0,
        )
        verdict = (resp.choices[0].message.content or "").strip().upper()
        top_j, top_e = similar[0]

        if "DUPLICATE" in verdict:
            return GateDecision(
                action="reject",
                target_id=top_e.id,
                reason="embed_failed_llm_duplicate",
                meta={"level": 0, "llm_verdict": verdict, "top_jaccard": round(top_j, 3)},
            )
        return GateDecision(
            action="accept",
            reason="embed_failed_llm_unique",
            meta={"level": 0, "llm_verdict": verdict, "top_jaccard": round(top_j, 3)},
        )

    # ── judge enqueue ────────────────────────────────────────

    def _maybe_enqueue_for_judge(
        self,
        candidate: Candidate,
        neighbors: Sequence["_NeighborScore"],
        candidate_vec: Sequence[float],
    ) -> str:
        """If a judge queue is wired, enqueue with top-3 neighbors and the
        L1/L2/L3 spans whose cosine ≥ ``L1_L2_L3_JUDGE_LOWER``.

        Imports the judge data types lazily to avoid the
        ``write_gate`` ↔ ``write_gate_judge`` circular dependency at module
        import time. No-op when the queue is None.

        Returns the ``request_id`` allocated by ``JudgeQueue.enqueue``, or
        an empty string when no queue is wired or enqueue failed.
        """
        if self._judge_queue is None:
            return ""
        try:
            from src.memory.write_gate_judge import CandidateNeighbor

            top_neighbors = [
                CandidateNeighbor(
                    entry_id=n.entry.id,
                    layer=n.entry.layer,
                    content=n.entry.content,
                    cosine=n.cosine,
                    trigger_jaccard=n.trigger_jaccard,
                )
                for n in neighbors[:3]
            ]
            spans = [
                span for _, span in self._static.spans_above(
                    candidate_vec, threshold=L1_L2_L3_JUDGE_LOWER, max_results=5,
                )
            ]
            return str(self._judge_queue.enqueue(candidate, top_neighbors, spans))
        except Exception as exc:
            logger.warning("judge enqueue failed: %s", exc)
            return ""

    # ── observation-mode wrapper ─────────────────────────────

    def check_and_log(
        self,
        candidate: Candidate,
        existing: Sequence[ExistingEntry] = (),
    ) -> GateDecision:
        """Decide + append one JSONL row to the observation log.

        Callers use this during commit 1 to collect labeled decision data
        without changing persistence behavior.
        """
        decision = self.check(candidate, existing)
        self._log_decision(candidate, decision, existing_count=len(existing))
        return decision

    # ── log ──────────────────────────────────────────────────

    def _log_decision(
        self,
        candidate: Candidate,
        decision: GateDecision,
        *,
        existing_count: int,
    ) -> None:
        record = {
            "ts": round(time.time(), 3),
            "kind": candidate.kind,
            "name": candidate.name,
            "target_layer": candidate.target_layer,
            "source_run_id": candidate.source_run_id,
            "trigger_tag_count": len(candidate.trigger_tags),
            "content_len": len(candidate.content),
            "existing_count": existing_count,
            "action": decision.action,
            "target_id": decision.target_id,
            "reason": decision.reason,
            "meta": decision.meta,
        }
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._log_lock, self._log_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("write_gate observation log failed: %s", exc)

    @property
    def static_index(self) -> StaticSpanIndex:
        return self._static

    @property
    def judge_queue(self) -> object | None:
        return self._judge_queue

    # ── pending skill buffer (hold-and-flush) ─────────────────

    def enqueue_pending_skill(
        self,
        skill: object,
        *,
        request_id: str,
        decision_action: str = "defer_to_judge",
    ) -> None:
        """Buffer a ``defer_to_judge`` candidate until the batch judge returns.

        ``filter_skill_batch`` calls this for every ``held`` candidate that
        carries a real ``request_id``. Held candidates are drained during the
        reap step that consumes the batch judge verdict.
        """
        with self._pending_lock:
            self._pending_skills.append(
                PendingSkillCandidate(
                    skill=skill,
                    decision_action=decision_action,
                    request_id=request_id,
                )
            )

    def pending_skills(self) -> list[PendingSkillCandidate]:
        """Snapshot of pending candidates (safe to iterate outside the lock)."""
        with self._pending_lock:
            return list(self._pending_skills)

    def clear_pending_skills(self) -> None:
        """Drop all pending candidates (called after reap completes)."""
        with self._pending_lock:
            self._pending_skills.clear()

    def flush_judge_round(
        self,
        judge_client: object,
        *,
        round_id: str = "",
        conflict_pairs: Sequence[Any] = (),
    ) -> object | None:
        """Submit all queued candidates + structural-conflict pairs as a
        single batch judge call.

        ``conflict_pairs`` should be a sequence of
        :class:`~src.memory.write_gate_judge.ConflictPair` produced by
        ``find_structural_conflicts``. Both inputs may be empty — if there is
        nothing to judge, returns ``None`` without making a call.

        Commit 2 ships this in observation mode: the judge result is
        appended to ``data/evolution/judge_log.jsonl`` for diagnostics, but
        the gate does NOT mutate any L4/L5 store based on the verdicts. That
        enforcement step lands with commit 3 / 4.
        """
        if self._judge_queue is None:
            return None
        candidate_requests = list(self._judge_queue.to_requests())  # type: ignore[attr-defined]
        if not candidate_requests and not conflict_pairs:
            return None

        # Build conflict requests inline so write_gate has no static dep on
        # the judge module's request types beyond what's needed.
        from src.memory.write_gate_judge import (
            JudgeRequest,
            append_judge_log,
            batch_judge,
        )

        conflict_requests: list[JudgeRequest] = []
        for i, pair in enumerate(conflict_pairs, start=1):
            conflict_requests.append(
                JudgeRequest(
                    kind="conflict",
                    request_id=f"conf_{i:04d}",
                    pair=(pair.a, pair.b),
                )
            )
        all_requests = candidate_requests + conflict_requests
        result = batch_judge(judge_client, all_requests)
        try:
            append_judge_log(
                self._log_path.parent / "judge_log.jsonl",
                round_id=round_id,
                requests=all_requests,
                result=result,
            )
        except Exception as exc:
            logger.warning("judge log append failed: %s", exc)
        self._judge_queue.clear()  # type: ignore[attr-defined]
        return result

    # ── observation helpers for each postrun write site ──────

    def observe_skill_batch(
        self,
        new_skills: Sequence[object],
        existing_skills: Sequence[object],
        *,
        run_id: str = "",
    ) -> list[GateDecision]:
        """Observation-mode hook for skill discovery output.

        Runs the gate on each new skill against the existing library, logs
        the decision, and returns the list of decisions. Does NOT block
        persistence — callers that want enforcement should use
        :meth:`filter_skill_batch` instead.

        Accepts duck-typed ``Skill`` objects (``.name``, ``.content``,
        ``.trigger``) to avoid coupling this module to the skill models.
        """
        existing_entries = [_skill_to_entry(s) for s in existing_skills]
        decisions: list[GateDecision] = []
        for new in new_skills:
            cand = _skill_to_candidate(new, run_id=run_id)
            decisions.append(self.check_and_log(cand, existing_entries))
        return decisions

    # Gate actions whose skills are allowed into the library. ``accept`` is
    # the normal new-entry path; ``update`` lets a refreshed version of the
    # same skill_id replace the previous row. ``defer_to_judge`` is separated
    # into the hold bucket — those candidates wait for the batch judge
    # verdict before being persisted (reaped in a later task). ``reject``
    # and ``merge`` are actively blocked: reject = auto-duplicate or L1
    # overlap, merge = new candidate is subsumed by an existing skill.
    _PERSIST_ACTIONS: frozenset[str] = frozenset({"accept", "update"})
    _HOLD_ACTIONS: frozenset[str] = frozenset({"defer_to_judge"})

    def filter_skill_batch(
        self,
        new_skills: Sequence[object],
        existing_skills: Sequence[object],
        *,
        run_id: str = "",
    ) -> tuple[
        list[object],
        list[tuple[object, GateDecision]],
        list[tuple[object, GateDecision]],
    ]:
        """Enforcement-mode variant of :meth:`observe_skill_batch`.

        Runs the gate on every candidate, logs the decision, and returns
        ``(kept, dropped, held)``:

        - ``kept`` contains the original duck-typed skill objects whose
          action is in :attr:`_PERSIST_ACTIONS` (``accept`` / ``update``).
          Callers should feed these into ``SkillLibrary.add_batch`` instead
          of the raw input list.
        - ``dropped`` is a list of ``(skill, decision)`` tuples for the
          candidates the gate rejected/merged, so callers can log a
          summary or expose the drop count to the operator.
        - ``held`` is a list of ``(skill, decision)`` tuples for candidates
          whose action is ``defer_to_judge``.  Callers **MUST NOT** persist
          these inline; they await the batch judge verdict. Each held
          candidate with a non-empty request_id is also enqueued onto the
          pending buffer (see :meth:`enqueue_pending_skill`); candidates
          without a request_id are logged and skipped (not buffered).

        Emits one INFO log line per dropped or held candidate for visibility.
        """
        existing_entries = [_skill_to_entry(s) for s in existing_skills]
        kept: list[object] = []
        dropped: list[tuple[object, GateDecision]] = []
        held: list[tuple[object, GateDecision]] = []
        for new in new_skills:
            cand = _skill_to_candidate(new, run_id=run_id)
            decision = self.check_and_log(cand, existing_entries)
            if decision.action in self._PERSIST_ACTIONS:
                kept.append(new)
            elif decision.action in self._HOLD_ACTIONS:
                request_id = self._last_judge_request_id
                if request_id:
                    self.enqueue_pending_skill(
                        new,
                        request_id=request_id,
                        decision_action=decision.action,
                    )
                else:
                    logger.warning(
                        "write_gate held skill with no request_id — not buffered (reap will not be able to resolve) name=%r",
                        getattr(new, "name", "") or getattr(new, "skill_id", ""),
                    )
                held.append((new, decision))
                logger.info(
                    "write_gate held skill name=%r action=%s target=%s reason=%s",
                    getattr(new, "name", "") or getattr(new, "skill_id", ""),
                    decision.action,
                    decision.target_id or "-",
                    decision.reason,
                )
            else:
                dropped.append((new, decision))
                logger.info(
                    "write_gate dropped skill name=%r action=%s target=%s reason=%s",
                    getattr(new, "name", "") or getattr(new, "skill_id", ""),
                    decision.action,
                    decision.target_id or "-",
                    decision.reason,
                )
        return kept, dropped, held


def _skill_to_entry(skill: object) -> ExistingEntry:
    return ExistingEntry(
        id=getattr(skill, "name", "") or getattr(skill, "skill_id", ""),
        content=getattr(skill, "content", ""),
        trigger_tags=_trigger_tags_from_skill(skill),
        layer="L5",
    )


def _skill_to_candidate(skill: object, *, run_id: str = "") -> Candidate:
    return Candidate(
        kind="skill",
        name=getattr(skill, "name", "") or getattr(skill, "skill_id", ""),
        content=getattr(skill, "content", ""),
        trigger_tags=_trigger_tags_from_skill(skill),
        target_layer="L5",
        source_run_id=run_id,
    )


def _trigger_tags_from_skill(skill: object) -> frozenset[str]:
    """Flatten a SkillTrigger-like object into a tag set for Jaccard.

    Reads the active frozensets on :class:`SkillTrigger`:
    state_types / enemy_names / requires_hand_capabilities /
    requires_enemy_powers.

    The legacy fields tags / threat_levels / intent_classes / deck_stages
    were removed on 2026-04-20 with the mistake-driven redesign.
    Missing attributes are skipped silently so the gate still works on
    legacy skills that were loaded from disk before migration.
    """
    trigger = getattr(skill, "trigger", None)
    if trigger is None:
        return frozenset()
    tags: set[str] = set()
    for attr in (
        "state_types",
        "enemy_names",
        "requires_hand_capabilities",
        "requires_enemy_powers",
    ):
        vals = getattr(trigger, attr, None)
        if vals:
            try:
                for v in vals:
                    if isinstance(v, str) and v:
                        tags.add(f"{attr}:{v}")
            except TypeError:
                pass
    return frozenset(tags)
