"""Mistake-driven skill discovery.

Core pipeline entrypoint for spec
2026-04-19-mistake-driven-skill-discovery-design.md:

1. §2.1  — baseline_a, baseline_b, is_mistake_episode (Task C2)
2. §3.1  — run_critic_parallel (Task C6)
3. §5.2  — run_mistake_discovery orchestrator (Task G1)

This file grows through Phase C/G; Task C1 seeds it with loss_ratio
and the two baseline functions only.
"""
from __future__ import annotations

import dataclasses
import statistics

from src.memory.models_v2 import CombatEpisode

# Minimum sample sizes (§2.1). Below this, the baseline is declared
# "inactive" and is_mistake_episode skips the side that has insufficient data.
BASELINE_MIN_SAMPLES: int = 3


def loss_ratio(ep: CombatEpisode) -> float:
    """Fraction of pre-combat HP lost during this combat.

    Guard against hp_before=0 via max(hp, 1). Returning a large number
    (dmg / 1) when hp_before is pathological is intentional: it flags
    the episode as a strong mistake candidate.
    """
    return ep.total_damage_taken / max(ep.hp_before, 1)


def baseline_a(history: list[CombatEpisode]) -> float | None:
    """Per-enemy historical median loss_ratio.

    Returns None when fewer than BASELINE_MIN_SAMPLES episodes exist
    (§2.1: 'Baseline A requires ≥3 historical episodes; otherwise A is
    inactive'). Caller passes an already-filtered list (same enemy_key,
    current run excluded).
    """
    if len(history) < BASELINE_MIN_SAMPLES:
        return None
    return statistics.median(loss_ratio(e) for e in history)


def baseline_b(pool: list[CombatEpisode]) -> float | None:
    """Act × combat_type × character mean loss_ratio over recent pool.

    Returns None when fewer than BASELINE_MIN_SAMPLES pool entries
    (§2.1: symmetric to baseline_a). Caller passes an already-filtered
    pool via combat_store.recent_by_act_type(...).
    """
    if len(pool) < BASELINE_MIN_SAMPLES:
        return None
    return statistics.fmean(loss_ratio(e) for e in pool)


# Per-combat-type delta thresholds (§2.1). Monster fights must exceed
# baseline by 10%; elites 15%; bosses 20%. Larger deltas for harder
# fights reflect naturally higher loss_ratio variance there.
DELTA_BY_TYPE: dict[str, float] = {
    "monster": 0.10,
    "elite": 0.15,
    "boss": 0.20,
}


def is_mistake_episode(
    ep: CombatEpisode,
    *,
    baseline_a_val: float | None,
    baseline_b_val: float | None,
) -> bool:
    """Return True iff ep.loss_ratio exceeds EITHER baseline by its type's delta.

    If both baselines are None (insufficient prior data) -> False, per §2.1
    ('If both inactive -> episode is not a mistake candidate').

    Uses strict `>` so an episode exactly AT the threshold is NOT flagged
    — matches the spec intent that only clear over-baseline episodes
    earn a critic call.
    """
    if baseline_a_val is None and baseline_b_val is None:
        return False
    delta = DELTA_BY_TYPE.get(ep.combat_type, 0.10)
    actual = loss_ratio(ep)
    if baseline_a_val is not None and actual > baseline_a_val + delta:
        return True
    if baseline_b_val is not None and actual > baseline_b_val + delta:
        return True
    return False


# ---------------------------------------------------------------------------
# §3.1 — parallel critic invocation
# ---------------------------------------------------------------------------

import asyncio
import json
import logging

from src.brain.llm_caller import call_raw
from src.skills.critic_prompt import (
    build_critic_prompt,
    parse_and_validate_critic_output,
    CriticResult,
)

logger = logging.getLogger(__name__)

_CRITIC_SYSTEM = (
    "You are a Slay the Spire 2 tactical critic. Produce strict JSON only."
)


async def _critic_one(
    ep: CombatEpisode,
    baseline_a_val: float | None,
    baseline_b_val: float | None,
    n_a: int,
    n_b: int,
) -> CriticResult:
    """Run the critic for a single mistake episode and validate the output."""
    prompt = build_critic_prompt(
        ep,
        baseline_a=baseline_a_val,
        baseline_b=baseline_b_val,
        n_a=n_a, n_b=n_b,
    )
    try:
        text, _latency, _tokens = await call_raw(
            system=_CRITIC_SYSTEM,
            prompt=prompt,
            effort="high",
            call_type="mistake_critic",
            max_tokens=16000,
        )
    except Exception as e:
        logger.warning("critic call failed for episode %s: %s", ep.episode_id, e)
        return CriticResult(
            decision="no_skill_needed",
            reason="critic_error",
            skill=None,
            rejection_reason=str(e),
        )

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(
            "critic returned non-JSON for episode %s: %s", ep.episode_id, e,
        )
        return CriticResult(
            decision="no_skill_needed",
            reason="invalid_json",
            skill=None,
            rejection_reason=str(e),
        )

    round_seqs = [r.llm_call_seq for r in ep.rounds]
    return parse_and_validate_critic_output(
        obj,
        enemy_name=ep.enemy_key,
        character=ep.character,
        round_count=len(ep.rounds),
        round_llm_call_seqs=round_seqs,
    )


async def run_critic_parallel(
    episodes: list[CombatEpisode],
    *,
    baselines_a: list[float | None],
    baselines_b: list[float | None],
    ns_a: list[int],
    ns_b: list[int],
) -> list[CriticResult]:
    """Fan critic calls out in parallel across all mistake episodes (§3.1).

    Every episode gets ONE analysis-tier critic call. Failures (network,
    JSON parse, validator) collapse to no_skill_needed with a reason tag;
    the pipeline tolerates per-episode failures without aborting the run.
    """
    tasks = [
        _critic_one(ep, ba, bb, na, nb)
        for ep, ba, bb, na, nb in zip(episodes, baselines_a, baselines_b, ns_a, ns_b)
    ]
    return list(await asyncio.gather(*tasks))


# ---------------------------------------------------------------------------
# §5.2 — main orchestrator
# ---------------------------------------------------------------------------

from pathlib import Path
from typing import TYPE_CHECKING

from src.memory.combat_store import CombatMemoryStore

if TYPE_CHECKING:
    from src.memory.write_gate import WriteGate
    from src.skills.library import SkillLibrary


async def run_mistake_discovery(
    *,
    this_run_episodes: list[CombatEpisode],
    combat_store: CombatMemoryStore,
    skill_library: "SkillLibrary",
    write_gate: "WriteGate",
    log_path: Path,
    run_id: str,
    combat_system_prompt: str,
    session_logger=None,
) -> dict[str, int]:
    """Main entrypoint (spec §5.2).

    Stages:
      1. Compute per-episode Baseline A + B; filter to mistake candidates
      2. Parallel critic call per mistake episode
      3. Convert critic candidates -> Skill objects
      4. Cascade dedup via WriteGate.filter_skill_batch
      5. Pre-write A/B validation per kept candidate (§4)
      6. Persist survivors with confidence 0.40 + 0.05 * helps_rounds

    Returns a stats dict for logging:
      - mistakes             : episodes that triggered the filter
      - critic_skill_needed  : critic said skill_needed
      - cascade_rejected     : dropped by WriteGate
      - ab_passed/ab_failed  : A/B outcome
      - persisted            : landed in library

    When ``session_logger`` is provided, emits one
    ``mistake_discovery_verdict`` event per mistake episode (spec §5.4),
    regardless of outcome (critic rejected / cascade dropped / A/B failed /
    persisted). ``session_logger=None`` (the default) disables event
    emission — useful for tests and ad-hoc invocations.
    """
    from src.skills.prewrite_ab import validate_candidate
    from dataclasses import replace

    stats = {
        "mistakes": 0,
        "critic_skill_needed": 0,
        "cascade_rejected": 0,
        "ab_passed": 0,
        "ab_failed": 0,
        "persisted": 0,
    }

    # Stage 1: filter mistakes + compute baselines
    mistakes: list[CombatEpisode] = []
    ba_list: list[float | None] = []
    bb_list: list[float | None] = []
    na_list: list[int] = []
    nb_list: list[int] = []

    for ep in this_run_episodes:
        history = [
            e for e in combat_store.get_by_enemy(ep.enemy_key)
            if e.run_id != run_id
        ]
        pool = combat_store.recent_by_act_type(
            act=ep.act, combat_type=ep.combat_type, character=ep.character,
            limit=10, exclude_run_id=run_id,
        )
        ba = baseline_a(history)
        bb = baseline_b(pool)
        if is_mistake_episode(ep, baseline_a_val=ba, baseline_b_val=bb):
            mistakes.append(ep)
            ba_list.append(ba)
            bb_list.append(bb)
            na_list.append(len(history))
            nb_list.append(len(pool))

    stats["mistakes"] = len(mistakes)

    # Seed per-episode verdict payloads (§5.4). Filled progressively as
    # each episode moves through the later stages; emitted at the end.
    verdicts: dict[str, dict] = {}
    for ep, ba, bb in zip(mistakes, ba_list, bb_list):
        verdicts[ep.episode_id] = {
            "event": "mistake_discovery_verdict",
            "run_id": run_id,
            "episode_id": ep.episode_id,
            "enemy": ep.enemy_key,
            "loss_ratio": round(loss_ratio(ep), 4),
            "baseline_A": round(ba, 4) if ba is not None else None,
            "baseline_B": round(bb, 4) if bb is not None else None,
            "critic_decision": None,
            "cascade_verdict": None,
            "ab_verdict": None,
            "skill_id": None,
        }

    if not mistakes:
        _emit_verdict_events(session_logger, verdicts)
        return stats

    # Stage 2: parallel critic (C6)
    critic_results = await run_critic_parallel(
        mistakes,
        baselines_a=ba_list, baselines_b=bb_list,
        ns_a=na_list, ns_b=nb_list,
    )
    candidates: list[tuple[CombatEpisode, dict]] = []
    for ep, res in zip(mistakes, critic_results):
        verdicts[ep.episode_id]["critic_decision"] = res.decision
        if res.decision == "skill_needed" and res.skill is not None:
            candidates.append((ep, res.skill))
            stats["critic_skill_needed"] += 1

    if not candidates:
        _emit_verdict_events(session_logger, verdicts)
        return stats

    # Stage 3: convert candidates -> Skill objects for cascade dedup
    from src.skills.models import AnchorExemplar, Skill, SkillTrigger

    skill_objs: list[Skill] = []
    for ep, cand in candidates:
        trig_raw = cand.get("trigger") or {}

        # character may be a single string from critic — normalize to frozenset
        char_val = trig_raw.get("character")
        if char_val is None or char_val == "":
            char_frozenset = frozenset()
        elif isinstance(char_val, str):
            char_frozenset = frozenset([char_val])
        else:
            char_frozenset = frozenset(char_val)

        trigger = SkillTrigger(
            state_types=frozenset(trig_raw.get("state_types") or ()),
            enemy_names=frozenset(trig_raw.get("enemy_names") or ()),
            character=char_frozenset,
            min_act=trig_raw.get("min_act") if trig_raw.get("min_act") is not None else 0,
            max_act=trig_raw.get("max_act") if trig_raw.get("max_act") is not None else 99,
            requires_cards=frozenset(trig_raw.get("requires_cards") or ()),
            requires_hand_capabilities=frozenset(trig_raw.get("requires_hand_capabilities") or ()),
            any_of_relics=frozenset(trig_raw.get("any_of_relics") or ()),
            requires_enemy_powers=frozenset(trig_raw.get("requires_enemy_powers") or ()),
            hp_below=trig_raw.get("hp_below") if trig_raw.get("hp_below") is not None else 1.0,
            hp_above=trig_raw.get("hp_above") if trig_raw.get("hp_above") is not None else 0.0,
        )
        sk = Skill(
            name=cand["name"],
            category=cand["category"],
            trigger=trigger,
            content=cand["content"],
            source="mistake_driven",
            source_run_ids=(run_id,),
            confidence=0.40,  # will bump after A/B
            verified=False,
            status="probation",
        )
        skill_objs.append(sk)

    # Stage 4: cascade dedup
    existing = list(skill_library.all_skills)
    kept, dropped, held = write_gate.filter_skill_batch(
        skill_objs, existing_skills=existing, run_id=run_id,
    )
    stats["cascade_rejected"] = len(dropped)
    stats["cascade_held"] = len(held)

    # Tie cascade decisions back to episodes via skill.name.
    # Build name_to_ep / name_to_cand once here — used both for anchor stamping
    # (held branch) and for Stage 6 episode lookup.
    name_to_ep: dict[str, CombatEpisode] = {
        s.name: ep for (ep, _c), s in zip(candidates, skill_objs)
    }
    name_to_cand: dict[str, dict] = {
        s.name: c for (_ep, c), s in zip(candidates, skill_objs)
    }

    kept_names = {k.name for k in kept}
    dropped_by_name: dict[str, object] = {
        getattr(obj, "name", ""): dec for obj, dec in dropped
    }
    held_by_name: dict[str, object] = {
        getattr(obj, "name", ""): dec for obj, dec in held
    }

    _stamp_anchors_on_held(
        held,
        write_gate=write_gate,
        name_to_ep=name_to_ep,
        name_to_cand=name_to_cand,
        run_id=run_id,
    )

    keep_pairs: list[tuple[CombatEpisode, dict, Skill]] = []
    for (ep, cand), sk in zip(candidates, skill_objs):
        if sk.name in kept_names:
            verdicts[ep.episode_id]["cascade_verdict"] = "ACCEPT"
            keep_pairs.append((ep, cand, sk))
        elif sk.name in held_by_name:
            verdicts[ep.episode_id]["cascade_verdict"] = "HELD"
        elif sk.name in dropped_by_name:
            dec = dropped_by_name[sk.name]
            action = getattr(dec, "action", "UNKNOWN")
            verdicts[ep.episode_id]["cascade_verdict"] = str(action).upper()

    if not keep_pairs:
        _emit_verdict_events(session_logger, verdicts)
        return stats

    # Stage 5: A/B validate in parallel across candidates
    async def _validate(ep, cand, sk):
        passed, per_round, hits = await validate_candidate(
            candidate=cand, episode=ep, log_path=log_path,
            combat_system_prompt=combat_system_prompt,
        )
        return sk, cand, passed, per_round, hits

    ab_outcomes = await asyncio.gather(
        *(_validate(ep, cand, sk) for ep, cand, sk in keep_pairs)
    )

    # Stage 6: persist survivors
    for sk, cand, passed, per_round, hits in ab_outcomes:
        ep_match = name_to_ep.get(sk.name)
        if not passed:
            stats["ab_failed"] += 1
            # Was it actively harmful, or just unclear?
            if any(getattr(r, "verdict", "") == "skill_harmful" for r in per_round):
                ab_verdict = "skill_harmful"
            else:
                ab_verdict = "skill_unclear"
            if ep_match is not None:
                verdicts[ep_match.episode_id]["ab_verdict"] = ab_verdict
            logger.info(
                "mistake_discovery: A/B failed for %s (hits=%d across %d rounds)",
                sk.name, hits, len(per_round),
            )
            continue
        stats["ab_passed"] += 1
        rounds_in_cand = max(1, len(cand.get("mistake_round_indices", [])))
        new_conf = 0.40 + 0.05 * rounds_in_cand  # 0.45..0.55 typical

        # Stamp AnchorExemplars: each mistake round becomes a log anchor the
        # merge pipeline can later replay via fetch_prompt_a(log, seq=...).
        anchors: list[AnchorExemplar] = []
        if ep_match is not None:
            expected = cand.get("expected_correction", "")
            cf_note = cand.get("counterfactual_note", "")
            for idx in cand.get("mistake_round_indices") or []:
                zero_idx = int(idx) - 1
                if 0 <= zero_idx < len(ep_match.rounds):
                    rnd = ep_match.rounds[zero_idx]
                    anchors.append(AnchorExemplar(
                        run_id=run_id,
                        llm_call_seq=int(rnd.llm_call_seq),
                        expected_correction=expected,
                        counterfactual_note=cf_note,
                        episode_id=ep_match.episode_id,
                        round_num=int(idx),
                    ))

        sk_final = replace(
            sk,
            confidence=new_conf,
            anchor_exemplars=tuple(anchors),
        )
        skill_library.add(sk_final)
        stats["persisted"] += 1
        if ep_match is not None:
            verdicts[ep_match.episode_id]["ab_verdict"] = "skill_helps"
            verdicts[ep_match.episode_id]["skill_id"] = sk_final.skill_id
        logger.info(
            "mistake_discovery: persisted skill %r (confidence=%.2f)",
            sk_final.name, new_conf,
        )

    _emit_verdict_events(session_logger, verdicts)
    return stats


def _stamp_anchors_on_held(
    held_rows: list[tuple[object, object]],
    *,
    write_gate,
    name_to_ep: "dict[str, CombatEpisode]",
    name_to_cand: "dict[str, dict]",
    run_id: str,
) -> None:
    """Replace each held skill on ``write_gate._pending_skills`` with an
    anchor-stamped copy. Called right after ``filter_skill_batch`` so Task 9's
    merge pipeline can re-run AB against the original gameplay prompts.

    ``held_rows`` is the ``held`` bucket from ``filter_skill_batch`` (a list
    of ``(skill, GateDecision)`` tuples). The pending buffer already contains
    one row per held skill — we rebuild each with ``anchor_exemplars``
    filled in from ``cand["mistake_round_indices"]``.
    """
    if not held_rows:
        return

    held_names = {
        getattr(sk, "name", "") for sk, _dec in held_rows
    }
    if not held_names:
        return

    from src.skills.models import AnchorExemplar

    with write_gate._pending_lock:
        new_pending: list = []
        for pending in write_gate._pending_skills:
            skill_name = getattr(pending.skill, "name", "")
            if skill_name not in held_names:
                new_pending.append(pending)
                continue
            ep = name_to_ep.get(skill_name)
            cand = name_to_cand.get(skill_name)
            if ep is None or cand is None:
                new_pending.append(pending)
                continue
            anchors: list[AnchorExemplar] = []
            for idx in (cand.get("mistake_round_indices") or []):
                zero = int(idx) - 1
                if 0 <= zero < len(ep.rounds):
                    rnd = ep.rounds[zero]
                    anchors.append(AnchorExemplar(
                        run_id=run_id,
                        llm_call_seq=int(rnd.llm_call_seq),
                        expected_correction=cand.get("expected_correction", ""),
                        counterfactual_note=cand.get("counterfactual_note", ""),
                        episode_id=getattr(ep, "episode_id", ""),
                        round_num=int(idx),
                    ))
            stamped_skill = dataclasses.replace(
                pending.skill, anchor_exemplars=tuple(anchors)
            )
            new_pending.append(
                dataclasses.replace(pending, skill=stamped_skill)
            )
        write_gate._pending_skills = new_pending


def _emit_verdict_events(session_logger, verdicts: dict[str, dict]) -> None:
    """Emit one ``mistake_discovery_verdict`` event per mistake episode.

    Safe no-op when ``session_logger`` is ``None`` or ``verdicts`` is empty.
    Exceptions from individual writes are logged and swallowed so a logger
    fault never aborts the orchestrator.
    """
    if session_logger is None or not verdicts:
        return
    for payload in verdicts.values():
        try:
            session_logger._write_event("mistake_discovery_verdict", payload)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning("failed to emit mistake_discovery_verdict: %s", e)
