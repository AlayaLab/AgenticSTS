"""Mode B stub fill orchestrator: prompt -> LLM -> parse -> validate -> persist.

Top-level entry points:
- ``fill_all_stubs(character, evidence_by_stub)``: synchronous, sequential.
  Used by tests and any caller that doesn't have an async event loop.
- ``afill_all_stubs(character, evidence_by_stub)``: asynchronous, concurrent.
  Dispatches per-stub backend.call() in parallel via asyncio.to_thread +
  gather. Used by AgentLoop._post_run_fill_stubs in production.

Both share ``_fill_one`` for the per-stub work: pick fill or update prompt,
call backend, parse, validate, render principles, replace stub via
``library.add()``. Bypasses WriteGate (Layer 4 of isolation per spec §10).

Spec: ``docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md``
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from src.skills.library import SkillLibrary
from src.skills.models import Skill
from src.skills.stub_prompts import build_fill_prompt, build_update_prompt
from src.skills.stub_validators import run_stub_validators

logger = logging.getLogger(__name__)


class StubFiller:
    """Fill / update Mode B seed stubs via LLM postrun call.

    Stateless aside from the (library, backend) pair — orchestration is
    purely sequential. Backend must implement ``.call(messages, system, ...)``
    returning an object with ``content`` (list of blocks with ``.type`` and
    ``.text``) and ``stop_reason``.
    """

    def __init__(self, library: SkillLibrary, backend: Any):
        self._library = library
        self._backend = backend

    # ── Public API ────────────────────────────────────────────

    def fill_all_stubs(
        self,
        *,
        character: str,
        evidence_by_stub: dict[str, str],
    ) -> dict[str, Any]:
        """Fill / update every stub matching ``character``.

        Args:
            character: lowercase character key (e.g. "the silent").
            evidence_by_stub: skill_id -> assembled evidence string. Stubs
                with empty / missing evidence are skipped.

        Returns:
            Summary dict for audit logging:
                ``{"filled_count": int, "skipped_count": int, "warnings_by_stub": {id: [str]}}``.
        """
        stubs = [
            s for s in self._library.all_skills
            if s.skill_id.startswith("stub_")
            and s.trigger.character
            and character in s.trigger.character
        ]

        filled = 0
        skipped = 0
        warnings_by_stub: dict[str, list[str]] = {}

        for stub in stubs:
            evidence = evidence_by_stub.get(stub.skill_id, "")
            if not evidence.strip():
                logger.info("No evidence for %s, skipping fill", stub.skill_id)
                skipped += 1
                continue

            try:
                new_skill, warnings = self._fill_one(stub, evidence)
            except Exception as exc:
                logger.warning(
                    "Fill failed for %s: %s", stub.skill_id, exc, exc_info=True,
                )
                skipped += 1
                continue

            self._library.add(new_skill)
            warnings_by_stub[stub.skill_id] = warnings
            filled += 1

        return {
            "filled_count": filled,
            "skipped_count": skipped,
            "warnings_by_stub": warnings_by_stub,
        }

    async def afill_all_stubs(
        self,
        *,
        character: str,
        evidence_by_stub: dict[str, str],
    ) -> dict[str, Any]:
        """Async concurrent variant: dispatch per-stub fill in parallel.

        Each stub's backend.call() is wrapped in asyncio.to_thread so the
        event loop isn't blocked while the LLM call runs. asyncio.gather
        runs all stubs concurrently — with 5 stubs each ~30s, total wall
        time drops from ~150s (sequential) to ~30s (concurrent).

        Per-stub failures are isolated: a backend exception on one stub
        does not abort the others. Returns the same summary dict shape
        as fill_all_stubs.
        """
        stubs = [
            s for s in self._library.all_skills
            if s.skill_id.startswith("stub_")
            and s.trigger.character
            and character in s.trigger.character
        ]

        async def _run_one(stub) -> tuple[str, str, list[str], Any]:
            """Returns (status, skill_id, warnings, new_skill_or_none)."""
            evidence = evidence_by_stub.get(stub.skill_id, "")
            if not evidence.strip():
                logger.info("No evidence for %s, skipping fill", stub.skill_id)
                return ("skip", stub.skill_id, [], None)
            try:
                # _fill_one is synchronous; wrap in to_thread so backend.call
                # doesn't block the event loop. Concurrent across stubs.
                new_skill, warnings = await asyncio.to_thread(
                    self._fill_one, stub, evidence,
                )
                return ("filled", stub.skill_id, warnings, new_skill)
            except Exception as exc:
                logger.warning(
                    "Fill failed for %s: %s", stub.skill_id, exc, exc_info=True,
                )
                return ("failed", stub.skill_id, [], None)

        results = await asyncio.gather(*(_run_one(s) for s in stubs))

        filled = 0
        skipped = 0
        warnings_by_stub: dict[str, list[str]] = {}
        for status, sid, warnings, new_skill in results:
            if status == "filled" and new_skill is not None:
                self._library.add(new_skill)
                warnings_by_stub[sid] = warnings
                filled += 1
            else:
                skipped += 1

        return {
            "filled_count": filled,
            "skipped_count": skipped,
            "warnings_by_stub": warnings_by_stub,
        }

    # ── Internal ──────────────────────────────────────────────

    def _fill_one(self, stub: Skill, evidence: str) -> tuple[Skill, list[str]]:
        """Fill a single stub; returns (updated_skill, warnings_list)."""
        scaffold = stub.scaffold or {}
        cluster = self._cluster_label(stub.skill_id)
        is_update = (stub.status == "active")

        if is_update:
            prompt = build_update_prompt(
                scaffold=scaffold,
                state_type_cluster=cluster,
                evidence=evidence,
                existing_content=stub.content or "",
                existing_version=stub.version,
            )
        else:
            prompt = build_fill_prompt(
                scaffold=scaffold,
                state_type_cluster=cluster,
                evidence=evidence,
            )

        # Route through the analysis tier explicitly. Without these kwargs
        # V2Backend falls back to ``self._default_model = config.LLM_MODEL``,
        # which defaults to ``"gpt-5.4"`` whenever ``LLM_MODEL`` is unset in
        # ``.env`` — silently shipping every stub fill to GPT regardless of
        # the configured model family. ``openai_relay_profile="postrun"`` also
        # pins the relay credentials to the postrun key set, so a Gemini
        # gameplay run does not accidentally consume the GPT quota.
        import config
        analysis_model = config.LLM_ANALYSIS_MODEL or config.LLM_STRATEGIC_MODEL
        analysis_provider = (
            config.LLM_ANALYSIS_PROVIDER
            or config.LLM_STRATEGIC_PROVIDER
            or config.LLM_PROVIDER
        )
        response = self._backend.call(
            system="You write strategy skills for an autonomous game-playing agent.",
            messages=[{"role": "user", "content": prompt}],
            model=analysis_model,
            provider=analysis_provider,
            think=True,
            effort=config.LLM_THINK_EFFORT_ANALYSIS or "high",
            openai_relay_profile="postrun",
            tier="analysis",
        )
        text = self._extract_text(response)
        parsed = self._parse_json(text)
        if parsed is None:
            raise ValueError(
                f"Could not parse JSON from response: {text[:200]!r}"
            )

        warnings = run_stub_validators(parsed, scaffold)
        new_content = self._render_principles_to_content(parsed.get("principles", []))

        new_skill = stub.with_update(
            content=new_content,
            source="stub_filled",
            status="active",
            confidence=float(parsed.get("confidence", 0.5)),
            version=stub.version + 1,
        )
        return new_skill, warnings

    @staticmethod
    def _cluster_label(stub_id: str) -> str:
        """Friendly state-type cluster label for the prompt."""
        if stub_id.endswith("_combat"):
            return "non-boss combat (hallway and elite encounters)"
        if stub_id.endswith("_boss"):
            return "boss combat (act-ending fights with HP fully restoring after)"
        if stub_id.endswith("_deckbuilding"):
            return (
                "deck-building decisions "
                "(card_reward, card_select, shop, treasure, relic_select)"
            )
        if stub_id.endswith("_map"):
            return "map / path-selection decisions"
        if stub_id.endswith("_intermission"):
            return (
                "rest_site and event decisions "
                "(resource trade-offs at non-combat nodes)"
            )
        return "<unknown cluster>"

    @staticmethod
    def _extract_text(response: Any) -> str:
        """Pull the first text block from the response.content list."""
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "text":
                return block.text or ""
        return ""

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        """Find the first balanced JSON object in ``text`` and parse it.

        LLMs often wrap JSON in markdown fences or trailing commentary;
        scanning for the outermost {...} block is the most robust approach.
        Returns None on failure.
        """
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start: i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        return None
        return None

    @staticmethod
    def _render_principles_to_content(principles: list[dict]) -> str:
        """Render parsed principles list as numbered markdown content."""
        lines: list[str] = []
        for i, p in enumerate(principles, start=1):
            lines.append(f"{i}. {p.get('text', '')}")
            example = p.get("example")
            if example:
                lines.append(f"   Example: {example}")
        return "\n".join(lines)
