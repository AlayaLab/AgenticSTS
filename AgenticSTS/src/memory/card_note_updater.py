"""Turn 2 of the combat-trace postrun pipeline.

Consumes the same combat trace string that Turn 1 (build_analysis) used,
calls the analysis-tier LLM to selectively propose per-card note updates,
validates each proposal, and writes kept updates to the CardMemoryStore
via ``CardMemory.with_new_note`` (bounded 3-version history).

The trace is prepended directly to the Turn 2 user message body. The
previous ``call_raw(user_cached_prefix=...)`` cross-turn cache scheme
was a no-op (cache_control dropped on openai_compatible relays; system
prompt mismatch defeated reuse on Anthropic) and was removed in the
2026-05-01 cache cleanup spec.

Gated by ``config.POSTRUN_NOTE_UPDATE_ENABLED`` — when False, the LLM
call still runs but proposals are logged and dropped (no writes).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dataclasses import dataclass

from src.brain.llm_caller import call_raw  # noqa: E402 — kept at module level for patch-ability
from src.memory.card_memory_store import CardMemoryStore, _canonical_card_name
from src.memory.models_v2 import CardMemory, normalize_character

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Turn2Result:
    """Outcome of one card_note_updater (Turn 2) invocation.

    Captures three channels:
      - bucket A (``notes_*``): per-deck-card note updates.
      - core_engine: act3-victory engine extraction (merged in 2026-04-25).
      - bucket B (``non_deck_*``): non-deck card notes with evidence_type
        (skipped / combo_inferred), capped at 3 per run.

    ``core_engine_emitted`` distinguishes "LLM produced an engine block"
    (True) from "LLM produced an empty / no-engine result" (False) —
    useful for telemetry on gate-on / no-engine-found runs.
    """
    notes_written: int = 0
    notes_kept_unchanged: int = 0
    notes_invalid: int = 0
    core_engine_applied: int = 0
    core_engine_emitted: bool = False
    non_deck_written: int = 0
    non_deck_dropped: int = 0


_MAX_NOTE_CHARS = 200

# COUPLING: the literal phrase "Act 3 final boss" below is the trigger
# keyword the LLM looks for to decide whether to emit `core_engine`.
# `_render_act3_victory_section` (callers in update_card_notes_from_traces)
# emits the same phrase verbatim. Do not paraphrase either side; they
# must match for the gate to fire.
_NOTE_UPDATER_SYSTEM = (
    "You review postrun combat traces and selectively propose updates to "
    "per-card notes. A note is a <=200-character deck-building hint that "
    "surfaces when the card appears in a reward / shop / card_select "
    "decision. It should capture non-obvious role or risk information that "
    "aggregated counters cannot express.\n\n"
    "Output STRICTLY a JSON object with this shape:\n"
    "{\n"
    '  "updates": [\n'
    "    {\n"
    '      "card_name": "<one of the provided candidates, lowercase>",\n'
    '      "new_note": "<= 200 chars, concrete and forward-looking",\n'
    '      "reason": "<1 line — why this note, what trace moment justifies it>",\n'
    '      "trace_citation": "<short quote from trace, e.g. \'Combat 2 R3: '
    "played Backstab for 11 dmg after Sly'>\"\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Empty list if nothing in the traces warrants an update. Never invent "
    "cards. Only use card names that appear in the provided candidate list.\n\n"
    "Additionally, when the calling instructions explicitly state "
    "\"this run won the Act 3 final boss\", you MUST also output a "
    "`core_engine` field alongside `updates`:\n"
    "{\n"
    '  "core_engine": {\n'
    '    "engine_mechanic": "<abstract description of how the deck scaled, '
    "e.g. \\\"stacking continuous passive debuff damage while stalling\\\">\",\n"
    '    "core_cards": ["<1-3 card or relic names that provided '
    "multiplicative scaling>\"],\n"
    '    "support_cards": ["<cards that generated, applied, or cycled the '
    "mechanic; may be empty>\"],\n"
    '    "notes": "<1-2 sentences describing the synergy concretely>"\n'
    "  }\n"
    "}\n\n"
    "Rules: (1) core_cards must reference cards in the provided final "
    "deck or relics. (2) engine_mechanic is abstract — do NOT use "
    "archetype labels (shiv/poison/panache/etc.); describe the action or "
    "trigger. (3) If the win came from raw tempo with no clear scaling "
    "engine, engine_mechanic should say so and core_cards may be empty. "
    "(4) Omit the `core_engine` field entirely when the calling "
    "instructions do not mention \"Act 3 final boss\".\n\n"
    "Additionally, you MAY emit up to 3 entries in `non_deck_updates` for "
    "cards that are NOT in the run's deck but where the trace or "
    "class-pool context justifies a forward-looking note:\n"
    "- evidence_type \"skipped\": the run was offered this card at "
    "card_reward or shop and rejected it. trace_citation MUST quote the "
    "rejection moment.\n"
    "- evidence_type \"combo_inferred\": this card is in the class pool "
    "and has a concrete combo with a card or relic the run actually used. "
    "`reason` MUST name that deck card or relic.\n"
    "Cap: 3 entries total. Be stingy. Prefer \"skipped\" when both apply. "
    "card_name MUST be a card listed in the Class Pool Reference section "
    "of this system prompt; it MUST NOT be in the run's deck. Each entry "
    "has the same shape as `updates` plus a required `evidence_type` field."
)


_UPDATER_PROMPT_TEMPLATE = """\
## Candidate cards (name | current_note | play_count | sly_play | total_damage | total_block)

{candidate_table}

## Cards offered but not picked this run (eligible for evidence_type="skipped")

{skipped_section}

## Instructions

For each candidate card, decide whether the traces at the top of this user
message justify a new or updated note.

**MANDATORY first-note rule:** For any candidate card whose `current_note`
column shows `(empty)` or `(no memory yet)` AND that appears at least once
in the trace (drawn, played, discarded, exhausted, or retained), you MUST
propose a `new_note`. Skip only if the card is in the candidate list but
the trace contains no evidence of it being interacted with.

For cards that already have a `current_note`, propose updates only when the
trace reveals something the current note misses. Keep new_note terse
(<=200 chars), concrete, and oriented toward future deck-building decisions.
Never invent cards not in the candidate list.

You MAY also emit up to 3 entries in `non_deck_updates` per the rules in
the system prompt. Use the "Cards offered but not picked" list above for
`evidence_type="skipped"` entries.

Respond with ONLY the JSON object.
"""


def _render_candidate_table(
    store: CardMemoryStore, character: str, candidate_cards: list[str],
) -> str:
    """Render the candidate card table as a pipe-delimited list."""
    lines: list[str] = []
    for name in candidate_cards:
        mem = store.get(character, name)
        if mem is None:
            lines.append(f"- {name} | (no memory yet) | 0 | 0 | 0 | 0")
            continue
        lines.append(
            f"- {name} | {(mem.note or '(empty)')[:120]} | "
            f"{mem.play_count} | {mem.sly_play_count} | "
            f"{mem.total_damage} | {mem.total_block}"
        )
    return "\n".join(lines) if lines else "(no candidates)"


def _render_act3_victory_section(
    final_deck: list[str], final_relics: list[str],
) -> str:
    """Conditional user-message tail rendered only when this run won
    the Act 3 final boss.

    The literal phrase ``Act 3 final boss`` is the trigger keyword the
    system prompt looks for to require ``core_engine`` output; do not
    paraphrase.
    """
    lines = [
        "## This run won the Act 3 final boss",
        "",
        "Final deck (at end of run):",
    ]
    if final_deck:
        lines.extend(f"- {c}" for c in final_deck)
    else:
        lines.append("(deck not captured)")
    lines.append("")
    lines.append("Final relics:")
    if final_relics:
        lines.extend(f"- {r}" for r in final_relics)
    else:
        lines.append("(no relics captured)")
    lines.append("")
    lines.append(
        "Identify the core engine of this winning deck per the rules "
        "in the system prompt. Output the `core_engine` field "
        "alongside `updates`."
    )
    return "\n".join(lines)


def parse_note_updates(
    raw_text: str, candidate_cards: set[str],
) -> tuple[list[dict], int]:
    """Parse LLM response into validated proposals.

    Returns ``(proposals, invalid_count)``. Whole-response JSON failure
    returns ``([], 0)`` — not counted as invalid proposals because no
    proposals existed in the first place.
    """
    raw = (raw_text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        logger.warning("card_note_updater: failed to parse LLM JSON")
        return [], 0

    updates = parsed.get("updates") if isinstance(parsed, dict) else None
    if not isinstance(updates, list):
        return [], 0

    # Canonicalize candidate set so upgrade-variant differences (Strike vs
    # Strike+ vs Strike++) collapse to the same base name. The LLM's
    # ``card_name`` is canonicalized the same way before the membership
    # check, so a proposal naming any upgrade variant matches the candidate
    # list as long as the base card was offered.
    candidate_canonical = {_canonical_card_name(c) for c in candidate_cards}
    valid: list[dict] = []
    invalid = 0
    for u in updates:
        if not isinstance(u, dict):
            invalid += 1
            continue
        card = _canonical_card_name(str(u.get("card_name", "")))
        new_note = str(u.get("new_note", "")).strip()
        reason = str(u.get("reason", "")).strip()
        citation = str(u.get("trace_citation", "")).strip()
        if not card or card not in candidate_canonical:
            if u.get("card_name"):
                logger.warning(
                    "card_note_updater: dropped proposal with unknown card_name=%r",
                    u.get("card_name"),
                )
            invalid += 1
            continue
        if not new_note or len(new_note) > _MAX_NOTE_CHARS:
            invalid += 1
            continue
        if not reason or len(reason) > _MAX_NOTE_CHARS:
            invalid += 1
            continue
        if not citation:
            invalid += 1
            continue
        valid.append({
            "card_name": card,
            "new_note": new_note,
            "reason": reason,
            "trace_citation": citation,
        })
    return valid, invalid


_BUCKET_B_CAP = 3


def parse_non_deck_updates(
    raw_text: str,
    *,
    class_pool: frozenset[str],
    final_deck: frozenset[str],
    final_relics: frozenset[str],
    skipped_cards: frozenset[str],
) -> tuple[list[dict], int]:
    """Parse the bucket B (``non_deck_updates``) channel of Turn 2.

    Returns ``(proposals, dropped_count)``. Each surviving proposal has
    ``reason`` already prefixed with ``[skipped]`` or ``[combo_inferred]``
    so the apply path is identical to bucket A. Proposals beyond
    ``_BUCKET_B_CAP`` are truncated and counted as dropped.

    Validation rules (all must pass):
      1. card_name (canonicalized via ``_canonical_card_name``) must be
         in ``class_pool``.
      2. card_name must NOT be in ``final_deck``.
      3. ``evidence_type == "skipped"``: card_name (canonicalized) must
         appear in ``skipped_cards``; ``trace_citation`` must be non-empty.
      4. ``evidence_type == "combo_inferred"``: ``reason`` must contain at
         least one lowercased token from ``final_deck`` ∪ ``final_relics``.
      5. ``new_note`` and ``reason`` must each be non-empty and
         <= ``_MAX_NOTE_CHARS``.

    Returns ``([], 0)`` on whole-response JSON failure (sentinel — bucket
    A parser handles the same payload and logs its own warning).
    """
    raw = (raw_text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        return [], 0
    if not isinstance(parsed, dict):
        return [], 0

    entries = parsed.get("non_deck_updates")
    if not isinstance(entries, list):
        return [], 0

    skipped_canonical = {
        _canonical_card_name(s) for s in skipped_cards if s
    }
    deck_relic_tokens = {t.lower() for t in (final_deck | final_relics) if t}

    valid: list[dict] = []
    dropped = 0
    for entry in entries:
        if not isinstance(entry, dict):
            dropped += 1
            continue
        card = _canonical_card_name(str(entry.get("card_name", "")))
        new_note = str(entry.get("new_note", "")).strip()
        evidence_type = str(entry.get("evidence_type", "")).strip().lower()
        reason = str(entry.get("reason", "")).strip()
        citation = str(entry.get("trace_citation", "")).strip()

        # Rule 5: length bounds
        if not new_note or len(new_note) > _MAX_NOTE_CHARS:
            dropped += 1
            continue
        if not reason or len(reason) > _MAX_NOTE_CHARS:
            dropped += 1
            continue

        # Rule 1: in class pool
        if not card or card not in class_pool:
            dropped += 1
            continue

        # Rule 2: NOT in deck
        if card in final_deck:
            dropped += 1
            continue

        # Rule 3 / 4: per-evidence-type checks
        if evidence_type == "skipped":
            if card not in skipped_canonical:
                dropped += 1
                continue
            if not citation:
                dropped += 1
                continue
        elif evidence_type == "combo_inferred":
            reason_lower = reason.lower()
            if not any(tok in reason_lower for tok in deck_relic_tokens):
                dropped += 1
                continue
        else:
            dropped += 1
            continue

        valid.append({
            "card_name": card,
            "new_note": new_note,
            "reason": f"[{evidence_type}] {reason}",
            "trace_citation": citation,
        })

    if len(valid) > _BUCKET_B_CAP:
        dropped += len(valid) - _BUCKET_B_CAP
        valid = valid[:_BUCKET_B_CAP]

    return valid, dropped


def parse_core_engine_block(raw_text: str) -> tuple[bool, dict | None]:
    """Extract and validate the optional ``core_engine`` field from the
    Turn 2 response.

    Returns ``(emitted, engine_or_none)``:
      - ``(True, dict)``: LLM emitted a valid non-empty engine block.
        Caller MUST invoke ``apply_to_card_memory(engine, ...)``.
      - ``(True, None)``: LLM emitted the field but with empty mechanic
        AND empty core_cards (the "no clear engine" sentinel). Caller
        must NOT apply, but must log this as a legitimate outcome
        (telemetry distinguishes it from absence).
      - ``(False, None)``: field absent OR outer JSON malformed OR
        engine is not a dict. Caller does nothing.

    Independent of ``parse_note_updates``: each function parses the
    outer envelope itself. The overhead is negligible for Turn 2's
    single-response volume; the simplicity is worth it.
    """
    raw = (raw_text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        return False, None
    if not isinstance(parsed, dict):
        return False, None

    if "core_engine" not in parsed:
        return False, None
    engine = parsed.get("core_engine")
    if not isinstance(engine, dict):
        # Field present but unusable. Treat as not-emitted (we can't
        # extract anything from it); caller can warn separately if needed.
        return False, None

    mechanic = str(engine.get("engine_mechanic", "") or "").strip()
    core_cards = [str(c) for c in (engine.get("core_cards") or []) if c]
    support_cards = [str(c) for c in (engine.get("support_cards") or []) if c]
    notes = str(engine.get("notes", "") or "").strip()

    # Sentinel: empty mechanic AND empty core_cards → "no engine found".
    # The LLM emitted the field deliberately, so emitted=True; but the
    # contents are not applyable, so engine=None.
    if not mechanic and not core_cards:
        return True, None

    return True, {
        "engine_mechanic": mechanic,
        "core_cards": core_cards,
        "support_cards": support_cards,
        "notes": notes,
    }


def apply_note_updates(
    store: CardMemoryStore,
    *,
    character: str,
    proposals: list[dict],
    run_id: str,
    dry_run: bool = False,
) -> int:
    """Persist validated proposals to the store. Returns written count.

    When ``dry_run`` is True, logs each proposal but performs no writes.

    ``character`` is passed through to ``CardMemory`` as-is (lowercased) so
    that the store key produced by ``put`` matches what callers expect when
    they call ``store.get(character, ...)``.  Canonical alias resolution
    (e.g. "silent" -> "the silent") is the responsibility of the caller when
    it matters; here we preserve the key that was used at call time.
    """
    # NOTE: callers are responsible for passing already-normalized
    # character names. update_card_notes_from_traces (below) calls
    # normalize_character() before dispatching here. Direct callers
    # that skip that step may produce mismatched store keys for
    # character aliases.
    char_key = character.lower().strip()
    written = 0
    for p in proposals:
        card_name = p["card_name"]
        if dry_run:
            logger.info(
                "card_note_updater[DRY_RUN]: would update %s/%s -> %s (reason=%s)",
                char_key, card_name, p["new_note"][:60], p["reason"][:60],
            )
            continue
        existing = store.get(char_key, card_name) or CardMemory(
            character=char_key, card_name=card_name,
        )
        updated = existing.with_new_note(
            new_note=p["new_note"],
            run_id=run_id,
            reason=p["reason"],
            trace_citation=p["trace_citation"],
        )
        store.put(updated)
        written += 1
    return written


async def update_card_notes_from_traces(
    *,
    store: CardMemoryStore,
    character: str,
    combat_trace_text: str,
    candidate_cards: list[str],
    run_id: str,
    is_act3_boss_victory: bool = False,
    final_deck: list[str] | None = None,
    final_relics: list[str] | None = None,
    skipped_cards: list[str] | None = None,
    dry_run: bool = False,
    session_logger: object | None = None,
) -> Turn2Result:
    """Turn 2 entry point. Calls LLM, parses both channels, applies.

    Channels:
      - `updates`: per-card note updates (always solicited).
      - `core_engine`: block emitted by the LLM only when the user
        message contains the literal phrase "Act 3 final boss". The
        caller passes ``is_act3_boss_victory=True`` plus the final
        deck/relics to render that section. Off-gate emissions are
        dropped defensively (warning logged).

    ``session_logger`` is optional. When provided and the engine is
    successfully applied (``engine_applied > 0`` and not dry_run),
    emits a ``log_postrun_artifact`` call with
    ``kind="core_engine_observation"``.

    Returns a ``Turn2Result`` summarizing both channels' outcomes.
    """
    if not combat_trace_text or not candidate_cards:
        return Turn2Result()

    from src.knowledge.class_pool_injector import render_class_pool_section

    char_norm = normalize_character(character)
    pool_section = render_class_pool_section(char_norm)
    system_prompt = (
        _NOTE_UPDATER_SYSTEM + "\n\n" + pool_section
        if pool_section else _NOTE_UPDATER_SYSTEM
    )
    candidate_table = _render_candidate_table(store, char_norm, candidate_cards)
    skipped_list = list(skipped_cards or [])
    if skipped_list:
        skipped_section = "\n".join(f"- {c}" for c in skipped_list)
    else:
        skipped_section = "(none)"
    prompt = _UPDATER_PROMPT_TEMPLATE.format(
        candidate_table=candidate_table,
        skipped_section=skipped_section,
    )

    if is_act3_boss_victory:
        prompt = (
            prompt
            + "\n\n"
            + _render_act3_victory_section(
                list(final_deck or []), list(final_relics or []),
            )
        )

    # Inline the trace at the top — single-block user content. The previous
    # user_cached_prefix split was a no-op on openai_compatible relays and
    # was defeated by the system-prompt mismatch with Turn 1 on Anthropic.
    prompt = combat_trace_text + "\n\n" + prompt

    # 2026-04-29: switched ``think=False`` → ``think=True`` + analysis effort.
    # The previous setup let Gemini default to thinking_level=medium (chosen
    # by ``_build_gemini_extra_body`` when effort=""), which consumed ~4K
    # output tokens on hidden thinking and produced only ~150 visible tokens
    # — enough to start the JSON but not close it. Empirically every run on
    # 2026-04-28 truncated card_note_update output at ~575 chars and
    # ``parse_note_updates`` returned 0 proposals. With think=True +
    # effort="high" the gemini extra_body builder (v2_backend.py:566) and
    # max_tokens floor (v2_backend.py:1311) raise the visible budget to
    # ~7616 tokens, leaving room for the full ``updates`` array. Also pass
    # an explicit max_tokens so the analysis tier doesn't silently fall
    # back to the 4096 default if the effort floor logic changes.
    import config as _config
    try:
        raw_text, latency_ms, tokens = await call_raw(
            system_prompt,
            prompt,
            think=True,
            effort=_config.LLM_THINK_EFFORT_ANALYSIS or "high",
            call_type="card_note_update",
            max_tokens=24000,
        )
    except Exception:
        logger.warning("card_note_updater: LLM call failed", exc_info=True)
        return Turn2Result()

    logger.info(
        "card_note_updater: LLM call %.0fms, %d tokens", latency_ms, tokens,
    )
    if raw_text and not raw_text.rstrip().endswith(("}", "]", "```")):
        logger.warning(
            "card_note_updater: response looks truncated "
            "(len=%d, tail=%r) — JSON parse will likely yield 0 updates",
            len(raw_text), raw_text[-80:].replace("\n", " "),
        )

    candidate_set = {c.lower() for c in candidate_cards}
    proposals, invalid = parse_note_updates(raw_text, candidate_set)
    written = apply_note_updates(
        store, character=char_norm,
        proposals=proposals, run_id=run_id, dry_run=dry_run,
    )
    kept_unchanged = max(0, len(candidate_cards) - len(proposals) - invalid)

    # ── bucket B (non-deck card notes) ──────────────────────────
    from src.knowledge.class_pool_injector import class_pool_card_names
    class_pool = class_pool_card_names(char_norm)
    final_deck_canonical = frozenset(
        _canonical_card_name(c) for c in (final_deck or []) if c
    )
    final_relics_lower = frozenset(
        str(r).strip().lower() for r in (final_relics or []) if r
    )
    skipped_canonical = frozenset(
        _canonical_card_name(c) for c in skipped_list if c
    )
    non_deck_proposals, non_deck_dropped = parse_non_deck_updates(
        raw_text,
        class_pool=class_pool,
        final_deck=final_deck_canonical,
        final_relics=final_relics_lower,
        skipped_cards=skipped_canonical,
    )
    non_deck_written = apply_note_updates(
        store, character=char_norm,
        proposals=non_deck_proposals, run_id=run_id, dry_run=dry_run,
    )

    # ── core_engine channel ─────────────────────────────────────
    engine_applied = 0
    engine_emitted = False
    if is_act3_boss_victory:
        engine_emitted, engine = parse_core_engine_block(raw_text)
        if engine is not None:
            if dry_run:
                logger.info(
                    "card_note_updater[DRY_RUN]: would apply core_engine "
                    "mechanic=%s core=%d support=%d",
                    engine["engine_mechanic"][:60],
                    len(engine["core_cards"]),
                    len(engine["support_cards"]),
                )
            else:
                from src.memory.core_engine_extractor import apply_to_card_memory
                engine_applied = apply_to_card_memory(
                    engine, store, character=char_norm, run_id=run_id,
                )
                if (
                    engine_applied > 0
                    and session_logger is not None
                    and hasattr(session_logger, "log_postrun_artifact")
                ):
                    try:
                        session_logger.log_postrun_artifact(
                            stage="memory",
                            kind="core_engine_observation",
                            action="apply",
                            summary=(
                                f"engine={engine['engine_mechanic'][:60]} "
                                f"core={','.join(engine['core_cards'])} "
                                f"support={','.join(engine['support_cards'])} "
                                f"applied={engine_applied}"
                            ),
                            after={
                                "engine_mechanic": engine["engine_mechanic"],
                                "core_cards": engine["core_cards"],
                                "support_cards": engine["support_cards"],
                                "applied": engine_applied,
                            },
                            source="card_note_updater_engine",
                        )
                    except Exception:
                        pass
        elif engine_emitted:
            # Sentinel — LLM tried, said no engine. Spec §6 legitimate.
            logger.info(
                "card_note_updater: core_engine emitted as no-engine "
                "sentinel (no apply)"
            )
    else:
        # Gate off: detect off-gate leak and warn (purely observational).
        leaked, _leak = parse_core_engine_block(raw_text)
        if leaked:
            logger.warning(
                "card_note_updater: dropped off-gate core_engine emission "
                "(is_act3_boss_victory=False)"
            )

    logger.info(
        "postrun_trace: turn2 notes_written=%d kept=%d invalid=%d  "
        "engine_applied=%d engine_emitted=%s  "
        "non_deck_written=%d non_deck_dropped=%d  (dry_run=%s)",
        written, kept_unchanged, invalid,
        engine_applied, engine_emitted,
        non_deck_written, non_deck_dropped, dry_run,
    )
    return Turn2Result(
        notes_written=written,
        notes_kept_unchanged=kept_unchanged,
        notes_invalid=invalid,
        core_engine_applied=engine_applied,
        core_engine_emitted=engine_emitted,
        non_deck_written=non_deck_written,
        non_deck_dropped=non_deck_dropped,
    )
