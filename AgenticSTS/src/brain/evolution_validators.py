"""Validators for the evolution stage.

Spec #4 module split: these functions used to live as methods of
EvolutionEngine. They moved here because their dependencies on the
engine instance are narrow (skill_library, memory_manager,
_run_context for some) and they are conceptually a single layer.

Each engine method now retains a 2-line delegator into the matching
function below. Tests calling engine._validate_*,
engine._find_similar_skill, engine._auto_classify_triggers, etc. flow
through the delegators unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

import config

logger = logging.getLogger(__name__)

# Common short card names that appear in English prose — skip auto-detect
_CARD_NAME_STOPLIST = frozenset({
    "strike", "defend", "block", "bash", "zap", "dualcast",
})


def extract_relevant_replay(engine: Any, trigger: object) -> str:
    """(Extracted from EvolutionEngine._extract_relevant_replay.)

    Extract a combat replay section only when trigger anchors make it relevant.
    """
    run_ctx = getattr(engine, "_run_context", "") or ""
    if not run_ctx:
        return ""

    # Split into replay sections
    sections = run_ctx.split("## Combat Replay:")
    if len(sections) < 2:
        return ""

    # Try to match by enemy name or card name from trigger
    enemy_names = getattr(trigger, "enemy_names", frozenset())
    requires_cards = getattr(trigger, "requires_cards", frozenset())
    search_terms = {n.lower() for n in enemy_names} | {c.lower() for c in requires_cards}
    if not search_terms:
        return ""

    for section in sections[1:]:
        section_lower = section.lower()
        for term in search_terms:
            if term in section_lower:
                # Return full replay section (capped at 2000 chars)
                return ("## Combat Replay:" + section)[:2000]

    return ""


def compress_skill_content(engine: Any, content: str, skill_name: str) -> str | None:
    """(Extracted from EvolutionEngine._compress_skill_content.)

    Auto-compress skill content to ≤400 chars using a fast LLM call.

    Returns compressed text, or None if compression fails.
    """
    prompt = (
        f"Compress the following strategy skill to ≤380 characters. "
        f"Keep ALL key rules and specifics. Remove examples, bullet "
        f"numbering, negative cases, and filler words. Output ONLY "
        f"the compressed text, nothing else.\n\n"
        f"Skill name: {skill_name}\n"
        f"Original ({len(content)} chars):\n{content}"
    )
    try:
        response = engine._backend.call(
            system="You are a text compressor. Output only the compressed text.",
            messages=[{"role": "user", "content": prompt}],
            provider=config.EVOLUTION_PROVIDER,
            model=config.EVOLUTION_MODEL,
            tools=[],
            think=False,
            max_tokens=600,
            openai_relay_profile="postrun",
        )
        compressed = ""
        for block in response.content:
            if hasattr(block, "text"):
                compressed += block.text
        compressed = compressed.strip()
        # Require minimum 20 chars to avoid LLM refusals being stored
        if compressed and 20 <= len(compressed) <= 400:
            logger.info(
                "Auto-compressed skill '%s': %d → %d chars",
                skill_name, len(content), len(compressed),
            )
            return compressed
        logger.warning(
            "Auto-compression still too long for '%s': %d chars",
            skill_name, len(compressed),
        )
        return None
    except Exception as exc:
        logger.warning("Auto-compression failed for '%s': %s", skill_name, exc)
        return None


def find_similar_skill(
    engine: Any, content: str, category: str, skill_name: str = ""
) -> Any | None:
    """(Extracted from EvolutionEngine._find_similar_skill.)

    Find existing skill with 40%+ keyword overlap in the same category.

    Also matches on exact name (case-insensitive) regardless of content
    overlap — prevents duplicate skills with the same name but different
    phrasing from being written in separate postrun sessions.
    """
    if engine._skill_library is None:
        return None

    new_words = set(content.lower().split())
    name_lower = skill_name.strip().lower()

    for skill in engine._skill_library.all_skills:
        if skill.category != category:
            continue
        # Name-match: same skill name → always treat as the same skill
        if name_lower and skill.name.strip().lower() == name_lower:
            return skill
        # Content-overlap fallback
        if len(new_words) < 3:
            continue
        existing_words = set(skill.content.lower().split())
        if not existing_words:
            continue
        union_size = len(new_words | existing_words)
        if union_size == 0:
            continue
        overlap = len(new_words & existing_words) / union_size
        if overlap > 0.4:
            return skill
    return None


def auto_classify_triggers(
    engine: Any,
    content: str,
    motivation: str,
    explicit_cards: list[str],
    explicit_enemies: list[str],
    *,
    skill_name: str = "",
) -> tuple[list[str], list[str]]:
    """(Extracted from EvolutionEngine._auto_classify_triggers.)

    Scan skill name + content for card/enemy mentions, auto-fill if LLM omitted.

    Only auto-fills requires_cards when the skill is ABOUT a specific card
    (card name appears in skill_name or is the clear subject of content).
    Enemy names are auto-filled more aggressively since enemy-specific skills
    are common and well-scoped.

    Returns (requires_cards, enemy_names) — possibly augmented.
    """
    from src.knowledge.knowledge import GameKnowledge

    result_cards: list[str] = list(explicit_cards)
    result_enemies: list[str] = list(explicit_enemies)

    try:
        kb = GameKnowledge.get_instance()
    except Exception:
        return result_cards, result_enemies

    name_lower = skill_name.lower()
    content_lower = content.lower()
    motivation_lower = motivation.lower()

    import re as _re

    # Auto-detect card names — ONLY if card name appears in skill_name
    # (skill_name is the strongest signal that skill is ABOUT this card)
    # Uses word boundary matching to avoid "Patter" matching "pattern"
    if not explicit_cards and kb.cards:
        for card in kb.cards._cards.values():
            cname = card.name
            if len(cname) < 5 or cname.lower() in _CARD_NAME_STOPLIST:
                continue
            pattern = r"\b" + _re.escape(cname.lower()) + r"\b"
            if _re.search(pattern, name_lower):
                result_cards.append(cname)
                logger.info(
                    "Auto-classified card trigger: '%s' (found in skill name)",
                    cname,
                )

    # Auto-detect enemy names — check both skill_name AND content
    # Monster names in knowledge are PascalCase ("PhrogParasite") but
    # skill text uses spaces ("Phrog Parasite"). Match both forms.
    if not explicit_enemies and kb.monsters:
        text = f"{name_lower} {content_lower} {motivation_lower}"
        for monster in kb.monsters._monsters.values():
            mname = monster.name
            if len(mname) < 4:
                continue
            # Match PascalCase directly and with spaces inserted
            if mname.lower() in text:
                result_enemies.append(mname)
                logger.info(
                    "Auto-classified enemy trigger: '%s' (detected in content)",
                    mname,
                )
            else:
                # Insert spaces before uppercase letters for matching
                import re
                spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", mname).lower()
                if len(spaced) > 4 and spaced in text:
                    result_enemies.append(mname)
                    logger.info(
                        "Auto-classified enemy trigger: '%s' (via '%s')",
                        mname, spaced,
                    )

    return result_cards, result_enemies


def validate_tool_binding(engine: Any, tool: Any) -> str | None:
    """(Extracted from EvolutionEngine._validate_tool_binding.)

    Stage 1: Test tool binding + execution against real GameState snapshots.

    Returns a REJECTED message on failure, or None on success.
    """
    # deferred: avoids circular import (evolution_engine ↔ evolution_validators)
    from src.brain.evolution_engine import _can_bind_param

    if engine._snapshot_store is None:
        return None  # No store available — skip (cold start grace)

    applicable = tool.schema.get("APPLICABLE_STATES", [])
    snapshots = engine._snapshot_store.get_snapshots(
        state_types=list(applicable) if applicable else None,
        n=5,
    )
    if not snapshots:
        logger.debug("No snapshots for validation of %s — accepting", tool.name)
        return None  # Cold start grace

    from src.brain.tool_preprocessor import bind_params
    from src.state.state_parser import parse_state

    failures: list[str] = []
    engine._last_validation_success = None  # Store for Stage 2

    for snap in snapshots:
        try:
            gs = parse_state(snap.raw_state)
        except Exception as exc:
            logger.debug("Snapshot parse failed: %s", exc)
            continue

        param_info = engine._dynamic_registry.get_param_info(tool.name)
        if param_info is None:
            failures.append("no param info")
            continue

        bound = bind_params(param_info, gs, schema=tool.schema)
        if bound is None:
            unbound = [
                p for p in param_info
                if not _can_bind_param(p, gs)
            ]
            failures.append(f"bind failed: params {unbound} unresolvable from GameState")
            continue

        try:
            result = tool.execute_raw(**bound)
            result_str = str(result)
            if "execution error:" in result_str:
                failures.append(f"execute error: {result_str[:200]}")
            elif not result:
                failures.append("execute returned empty result")
            else:
                # Success — store for Stage 2
                engine._last_validation_success = (gs, result)
                return None  # At least one snapshot succeeded
        except Exception as exc:
            failures.append(f"execute raised: {exc}")

    # All snapshots failed
    return (
        f"REJECTED: Tool failed on all {len(snapshots)} real game states. "
        f"Errors: {'; '.join(failures[:3])}"
    )


def validate_tool_quality(engine: Any, tool: Any) -> str | None:
    """(Extracted from EvolutionEngine._validate_tool_quality.)

    Stage 2: Ask Sonnet whether the tool output helps combat decisions.

    Returns a REJECTED message if tool is redundant/misleading, None if helpful.
    """
    # deferred: avoids circular import (evolution_engine ↔ evolution_validators)
    from src.brain.evolution_engine import _build_state_summary

    if not hasattr(engine, "_last_validation_success") or engine._last_validation_success is None:
        return None  # No successful execution to judge — accept

    gs, tool_result = engine._last_validation_success
    engine._last_validation_success = None

    from src.brain.tool_preprocessor import ToolHint

    # Format the tool hint
    hint = ToolHint(tool_name=tool.name, result=tool_result, latency_ms=0)
    if engine._tool_preprocessor:
        hint_text = engine._tool_preprocessor.format_hints([hint])
    else:
        hint_text = f"- {tool.name}: {str(tool_result)[:300]}"

    # Build compact state summary
    state_summary = _build_state_summary(gs)

    judge_prompt = (
        "You are evaluating whether a computed combat insight helps an AI agent "
        "make better decisions in Slay the Spire 2.\n\n"
        f"## Game State\n{state_summary}\n\n"
        f"## Computed Insight\n{hint_text}\n\n"
        "## Evaluation Criteria\n"
        "1. Does this insight provide information NOT easily derivable from the raw numbers?\n"
        "2. Is the recommendation actionable (tells the agent what to DO)?\n"
        "3. Could this insight change a decision (e.g., 'focus defense' vs 'stack more poison')?\n\n"
        "Rate: HELPFUL / REDUNDANT / MISLEADING\n"
        "One sentence reasoning."
    )

    try:
        response = engine._backend.call(
            system="",
            messages=[{"role": "user", "content": judge_prompt}],
            provider=config.EVOLUTION_PROVIDER,
            model=config.EVOLUTION_MODEL,
            tools=[],
            think=False,
            max_tokens=200,
            openai_relay_profile="postrun",
        )

        # Extract text from response
        verdict_text = ""
        if hasattr(response, "content"):
            for block in response.content:
                if hasattr(block, "text"):
                    verdict_text += block.text
        elif isinstance(response, str):
            verdict_text = response

        verdict_upper = verdict_text.upper()

        if "MISLEADING" in verdict_upper:
            return (
                f"REJECTED: Quality judge found insight misleading. "
                f"Reasoning: {verdict_text[:200]}. "
                f"Fix the calculation or recommendation logic."
            )
        if "REDUNDANT" in verdict_upper:
            return (
                f"REJECTED: Quality judge found insight redundant. "
                f"Reasoning: {verdict_text[:200]}. "
                f"Consider: does this tool add information beyond what "
                f"the LLM can derive from raw HP/poison/block numbers?"
            )

        # HELPFUL or unparseable → accept
        logger.info(
            "Tool %s passed quality judge: %s",
            tool.name,
            verdict_text[:100],
        )
        return None

    except Exception as exc:
        # Don't block on judge errors — accept with warning
        logger.warning("Quality judge failed for %s: %s", tool.name, exc)
        return None


def check_skill_overmatch(engine: Any, trigger: object) -> None:
    """(Extracted from EvolutionEngine._check_skill_overmatch.)

    Stage 3: Over-match check (warn only). No LLM calls.
    """
    if engine._snapshot_store is None:
        return

    from src.state.state_parser import parse_state

    trigger_states = getattr(trigger, "state_types", frozenset())
    if not trigger_states:
        return  # Generic trigger — skip check

    # Get snapshots of DIFFERENT state types
    all_types = {"monster", "elite", "boss"}
    non_matching = all_types - trigger_states
    if not non_matching:
        return

    snapshots = engine._snapshot_store.get_snapshots(
        state_types=list(non_matching), n=2,
    )

    for snap in snapshots:
        try:
            gs = parse_state(snap.raw_state)
            hand_cards = frozenset(c.name for c in gs.hand) if gs.hand else frozenset()
            # Check context_tags for character
            context_tags = frozenset()

            matched, score = trigger.matches(
                state_type=snap.state_type,
                enemy_name="",
                act=gs.act or 1,
                hp_ratio=gs.player_hp / max(gs.player_max_hp, 1),
                deck_size=len(gs.deck) if gs.deck else 0,
                hand_cards=hand_cards,
                context_tags=context_tags,
            )
            if matched:
                logger.warning(
                    "Skill trigger over-match: matched %s snapshot (score=%.1f) "
                    "— consider narrowing trigger",
                    snap.state_type, score,
                )
        except Exception as exc:
            logger.debug("Stage 3 snapshot check failed: %s", exc)


def validate_skill_facts(
    engine: Any,
    skill_name: str,
    content: str,
    motivation: str,
    trigger: object,
    category: str,
) -> str | None:
    """(Extracted from EvolutionEngine._validate_skill_facts.)

    Stage 1: Factual consistency check. Returns reject reason or None.
    """
    if category not in {"combat", "boss"}:
        return None

    replay = extract_relevant_replay(engine, trigger)
    if not replay:
        return None  # No replay data — skip

    prompt = (
        f"Given this combat replay data:\n{replay}\n\n"
        f"The agent wants to create this skill:\n"
        f"Name: {skill_name}\n"
        f"Content: {content}\n"
        f"Motivation: {motivation}\n\n"
        "Check FACTUAL CLAIMS in the content and motivation against the replay:\n"
        "1. Does the replay support the claimed card behavior?\n"
        "2. Are damage/HP numbers consistent with what happened?\n"
        "3. Is the causal chain correct (did X actually cause Y)?\n\n"
        "Verdict: CONSISTENT / INCONSISTENT / UNVERIFIABLE\n"
        "If INCONSISTENT, quote the specific wrong claim on the next line."
    )

    try:
        model = config.EVOLUTION_MODEL or config.LLM_ANALYSIS_MODEL
        response = engine._backend.call(
            system="You are a factual accuracy checker for game strategy skills.",
            messages=[{"role": "user", "content": prompt}],
            provider=config.EVOLUTION_PROVIDER,
            model=model,
            tools=[],
            think=False,
            max_tokens=500,
            openai_relay_profile="postrun",
        )
        text = engine._backend.extract_text(response).upper()
        if "INCONSISTENT" in text:
            # Extract the detail line
            full = engine._backend.extract_text(response)
            lines = full.strip().split("\n")
            detail = lines[-1] if len(lines) > 1 else "factual claim contradicts replay"
            logger.warning(
                "Skill '%s' REJECTED (Stage 1 factual): %s",
                skill_name, detail,
            )
            return f"Factual inconsistency: {detail[:200]}"
    except Exception as exc:
        logger.warning("Skill validation Stage 1 failed (non-blocking): %s", exc)

    return None


def validate_skill_injection(
    engine: Any,
    skill_name: str,
    content: str,
    trigger: object,
) -> str | None:
    """(Extracted from EvolutionEngine._validate_skill_injection.)

    Stage 2: Injection simulation. Returns reject reason or None.
    """
    if engine._snapshot_store is None:
        return None

    from src.state.state_parser import parse_state

    # Get snapshots matching trigger's state types
    state_types = list(getattr(trigger, "state_types", frozenset()))
    snapshots = engine._snapshot_store.get_snapshots(
        state_types=state_types or None, n=3,
    )
    if not snapshots:
        return None  # Cold start grace

    model = config.EVOLUTION_MODEL or config.LLM_ANALYSIS_MODEL
    has_helpful = False
    has_harmful = False
    harmful_detail = ""

    for snap in snapshots:
        try:
            gs = parse_state(snap.raw_state)
            # Format compact game state summary
            hand_str = ", ".join(c.name for c in gs.hand) if gs.hand else "empty"
            enemy_parts = []
            for e in (gs.enemies or []):
                hp_str = f"{e.current_hp}/{e.max_hp}" if e.max_hp else str(e.current_hp)
                intent = ""
                primary = e.intents[0] if e.intents else None
                if primary and primary.damage is not None:
                    hits = primary.hits or 1
                    intent = f" intent={primary.damage}×{hits}" if hits > 1 else f" intent={primary.damage}dmg"
                enemy_parts.append(f"{e.name} HP={hp_str}{intent}")
            enemies_str = ", ".join(enemy_parts) if enemy_parts else "none"

            state_summary = (
                f"HP: {gs.player_hp}/{gs.player_max_hp}, "
                f"Energy: {gs.energy}/{gs.max_energy}, "
                f"Block: {gs.block}, "
                f"Hand: [{hand_str}], "
                f"Enemies: [{enemies_str}]"
            )

            prompt = (
                "You are evaluating a strategy skill for a Slay the Spire 2 agent.\n\n"
                f"Game state:\n{state_summary}\n\n"
                f"Proposed skill to inject:\n\"{content}\"\n\n"
                "Questions:\n"
                "1. Is this skill RELEVANT to this game state? (yes/no)\n"
                "2. If the agent followed it, would the DECISION change? (yes/no/maybe)\n"
                "3. If changed, is the NEW decision BETTER? (yes/no/unclear)\n\n"
                "Verdict: HELPFUL / IRRELEVANT / HARMFUL"
            )

            response = engine._backend.call(
                system="You are a game strategy evaluator.",
                messages=[{"role": "user", "content": prompt}],
                provider=config.EVOLUTION_PROVIDER,
                model=model,
                tools=[],
                think=False,
                max_tokens=500,
                openai_relay_profile="postrun",
            )
            verdict = engine._backend.extract_text(response).upper()
            if "HARMFUL" in verdict:
                has_harmful = True
                harmful_detail = engine._backend.extract_text(response)[:200]
            elif "HELPFUL" in verdict:
                has_helpful = True
        except Exception as exc:
            logger.warning("Skill validation Stage 2 snapshot failed: %s", exc)
            continue

    if has_harmful:
        logger.warning(
            "Skill '%s' REJECTED (Stage 2 harmful injection): %s",
            skill_name, harmful_detail,
        )
        return f"Injection simulation: skill could lead to worse decisions. {harmful_detail}"

    if not has_helpful and snapshots:
        logger.info(
            "Skill '%s' Stage 2 warning: no snapshots found skill HELPFUL",
            skill_name,
        )

    return None


def validate_skill_quality(
    engine: Any,
    skill_name: str,
    content: str,
    category: str,
    trigger: object,
) -> str | None:
    """(Extracted from EvolutionEngine._validate_skill_quality.)

    Stage 4: LLM quality judge. Returns reject reason or None.
    """
    state_types = sorted(getattr(trigger, "state_types", frozenset()))
    enemy_names = sorted(getattr(trigger, "enemy_names", frozenset()))
    requires_cards = sorted(getattr(trigger, "requires_cards", frozenset()))

    prompt = (
        "Evaluate this strategy skill for a Slay the Spire 2 agent:\n\n"
        f"Skill: \"{skill_name}\"\n"
        f"Content: \"{content}\"\n"
        f"Category: {category}\n"
        f"Trigger: state_types={state_types}, "
        f"enemy_names={enemy_names}, "
        f"requires_cards={requires_cards}\n\n"
        "Questions:\n"
        "1. Does this provide knowledge NOT already obvious from card descriptions?\n"
        "2. Is it specific enough to change a decision in a concrete situation?\n"
        "3. Could following this advice EVER lead to a worse outcome?\n\n"
        "Verdict: HELPFUL / REDUNDANT / MISLEADING"
    )

    try:
        model = config.EVOLUTION_MODEL or config.LLM_ANALYSIS_MODEL
        response = engine._backend.call(
            system="You are a quality reviewer for game strategy skills.",
            messages=[{"role": "user", "content": prompt}],
            provider=config.EVOLUTION_PROVIDER,
            model=model,
            tools=[],
            think=False,
            max_tokens=300,
            openai_relay_profile="postrun",
        )
        verdict = engine._backend.extract_text(response).upper()
        if "MISLEADING" in verdict:
            detail = engine._backend.extract_text(response)[:200]
            logger.warning(
                "Skill '%s' REJECTED (Stage 4 misleading): %s",
                skill_name, detail,
            )
            return f"Quality judge: MISLEADING — {detail}"
        if "REDUNDANT" in verdict:
            detail = engine._backend.extract_text(response)[:200]
            logger.warning(
                "Skill '%s' REJECTED (Stage 4 redundant): %s",
                skill_name, detail,
            )
            return f"Quality judge: REDUNDANT — {detail}"
    except Exception as exc:
        logger.warning("Skill validation Stage 4 failed (non-blocking): %s", exc)

    return None


def validate_skill(
    engine: Any,
    skill_name: str,
    content: str,
    motivation: str,
    trigger: object,  # SkillTrigger
    category: str,
) -> tuple[bool, str]:
    """(Extracted from EvolutionEngine._validate_skill.)

    Run 4-stage validation. Returns (passed, reject_reason_or_empty).
    """
    # Stage 1: Factual Consistency
    reject = validate_skill_facts(
        engine,
        skill_name,
        content,
        motivation,
        trigger,
        category,
    )
    if reject:
        return False, reject

    # Stage 2: Injection Simulation
    reject = validate_skill_injection(engine, skill_name, content, trigger)
    if reject:
        return False, reject

    # Stage 3: Over-Match Check (warn only, never rejects)
    check_skill_overmatch(engine, trigger)

    # Stage 4: Quality Judge
    reject = validate_skill_quality(engine, skill_name, content, category, trigger)
    if reject:
        return False, reject

    return True, ""
