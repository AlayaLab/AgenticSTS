"""Write-gate post-flush reap: apply batch judge verdicts to held candidates."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.memory.write_gate import WriteGate
from src.memory.write_gate_judge import BatchJudgeResult, CandidateJudgement
from src.skills.library import SkillLibrary
from src.skills.merge_pipeline import run_merge_pair
from src.storage import paths

logger = logging.getLogger(__name__)


def _append_reap_log(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def reap_judge_verdicts(
    *,
    gate: WriteGate,
    library: SkillLibrary,
    batch_result: BatchJudgeResult,
    log_dir: Path,
    combat_system_prompt: str,
    reap_log_path: Path | None = None,
) -> dict[str, int]:
    """Apply verdicts to held pending skills and clear the buffer.

    Branches on ``CandidateJudgement.decision``:
      - ADD    → ``library.add(skill)``
      - UPDATE → ``library.replace(target_id, skill)``, falling back to ``add``
                 if ``target_id`` is absent or unknown.
      - REJECT → drop (log only).
      - MERGE  → ``run_merge_pair(pending.skill, library.get(target_id))``;
                 on ``promote`` → ``library.replace(target_id, merged_skill)``;
                 on ``abandoned`` / ``ab_failed`` → drop.

    Any pending row whose ``request_id`` has no matching judgement is dropped
    (strict 宁缺毋滥 stance). The pending buffer is cleared at the end —
    guaranteed via try/finally so unexpected exceptions in the loop body do not
    leave the buffer populated (which would cause double-processing next run).
    """
    log_path = reap_log_path or paths.reap_log_file()
    stats = {
        "added": 0, "updated": 0, "rejected": 0, "merged": 0,
        "merge_ab_failed": 0, "merge_abandoned": 0, "unjudged": 0,
    }
    pending = gate.pending_skills()
    judgements = batch_result.candidate_judgements or {}

    try:
        for pc in pending:
            judgement = judgements.get(pc.request_id)
            entry: dict[str, Any] = {
                "skill_id": pc.skill.skill_id,
                "request_id": pc.request_id,
            }
            if judgement is None:
                stats["unjudged"] += 1
                entry["decision"] = "UNJUDGED"
                entry["reason"] = "no_matching_request_id"
                _append_reap_log(log_path, entry)
                continue

            entry["decision"] = judgement.decision
            entry["target_id"] = judgement.target_id
            entry["reason"] = judgement.reason

            if judgement.decision == "ADD":
                library.add(pc.skill)
                stats["added"] += 1

            elif judgement.decision == "UPDATE":
                tgt = judgement.target_id
                if not tgt:
                    library.add(pc.skill)
                    stats["added"] += 1
                    entry["reason"] = f"{judgement.reason}; missing_target_fallback_add"
                else:
                    try:
                        library.replace(tgt, pc.skill)
                        stats["updated"] += 1
                    except KeyError as e:
                        logger.warning(
                            "reap UPDATE target %r missing — adding instead: %s",
                            tgt, e,
                        )
                        library.add(pc.skill)
                        stats["added"] += 1
                        entry["reason"] = (
                            f"{judgement.reason}; missing_target_fallback_add"
                        )
                    except ValueError as e:
                        logger.warning(
                            "reap UPDATE replace failed: %s — adding instead", e,
                        )
                        library.add(pc.skill)
                        stats["added"] += 1
                        entry["reason"] = f"{judgement.reason}; fallback_add:{e}"

            elif judgement.decision == "REJECT":
                stats["rejected"] += 1

            elif judgement.decision == "MERGE":
                tgt_id = judgement.target_id
                target_skill = library.get(tgt_id) if tgt_id else None
                if target_skill is None:
                    stats["rejected"] += 1
                    entry["reason"] = f"{judgement.reason}; missing_merge_target"
                else:
                    try:
                        merge_result = await run_merge_pair(
                            skill_a=pc.skill, skill_b=target_skill,
                            log_dir=log_dir,
                            combat_system_prompt=combat_system_prompt,
                        )
                    except Exception as e:  # noqa: BLE001 — must not abort reap loop
                        logger.warning(
                            "reap MERGE run_merge_pair raised for %s vs %s: %s",
                            pc.skill.skill_id, tgt_id, e,
                        )
                        stats["merge_ab_failed"] += 1
                        entry["reason"] = (
                            f"{entry.get('reason', '')}; merge_exception:{e}"
                        )
                    else:
                        entry["merge_outcome"] = merge_result.outcome
                        entry["merge_reason"] = merge_result.reason
                        if (
                            merge_result.outcome == "promote"
                            and merge_result.merged_skill
                        ):
                            try:
                                library.replace(
                                    tgt_id, merge_result.merged_skill,
                                )
                                stats["merged"] += 1
                            except (KeyError, ValueError) as e:
                                logger.warning(
                                    "reap MERGE replace failed: %s", e,
                                )
                                stats["merge_ab_failed"] += 1
                                entry["reason"] = (
                                    f"{entry.get('reason', '')}; replace_err:{e}"
                                )
                        elif merge_result.outcome == "abandoned":
                            stats["merge_abandoned"] += 1
                        else:
                            stats["merge_ab_failed"] += 1
            else:
                logger.warning("reap: unknown decision %r", judgement.decision)
                stats["rejected"] += 1

            _append_reap_log(log_path, entry)
    finally:
        gate.clear_pending_skills()

    return stats
