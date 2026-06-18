"""Ablation-study orchestrator.

Runs 4 conditions per model x N runs (default 10) and stamps every completed
run with an experiment tag so scripts/ablation_report.py can aggregate them.

Conditions per model:
    - {model}-baseline-strict: stripped prompts, no L4/L5, no postrun.
    - {model}-prompt-only:     full prompts, zero accumulated state, no postrun.
    - {model}-self-evolve:     blank L4/L5 start, postrun on (analysis=strategic),
                               isolated data dir at experiments/<tag>/<cond>/.
    - {model}-full:            full prompts + inherited L4/L5, no postrun.

Usage:
    python -m scripts.run_ablation --tag abl-2026-04-21 --runs-per-condition 10

Resume:
    Re-run with the same --tag. The orchestrator counts existing
    (experiment_tag, condition_id) records in runs/history.jsonl and only
    launches the remaining runs per condition. For self-evolve, the
    per-experiment data dir at <STS2_DATA_REPO>/experiments/<tag>/<cond>/
    already contains accumulated skills/memory, so the next run picks up
    where the prior one left off.
"""
from __future__ import annotations

import argparse
import datetime
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from scripts.ablation_report import condition_id_from_record
from src.runs.history import RunHistoryStore
from src.storage import paths


logger = logging.getLogger(__name__)


# Reserved for future subprocess-wide env overrides. run_agent.py now calls
# os._exit at end of __main__ to bypass Windows uvicorn-thread shutdown hang,
# so monitor can stay enabled per-subprocess (visible at http://localhost:5173).
_ABLATION_FIXED_ENV: dict[str, str] = {}


# Outcomes that should NOT count toward runs-per-condition: the agent
# either crashed (agent_abort, mcp_error) or its environment broke
# (interrupt). We auto-retry agent_abort / mcp_error per-slot up to
# RETRY_CAP_PER_SLOT times; interrupt is preserved as-is because it
# usually means the user wants to stop. ``max_steps`` is treated as a
# legitimate (non-victory) run, not retried — re-running the same
# stuck state would just hit the same wall.
_NON_COUNTING_OUTCOMES = frozenset({"agent_abort", "mcp_error", "interrupt"})
_RETRYABLE_OUTCOMES = frozenset({"agent_abort", "mcp_error"})
RETRY_CAP_PER_SLOT = 3


def count_existing_runs(
    history_path: Path, *, tag: str, condition_id: str,
) -> int:
    """Count VALID records in history.jsonl that match (tag, condition_id).

    Used by main() to skip already-completed runs when resuming with the
    same tag. Aborted runs (``agent_abort`` / ``mcp_error`` / ``interrupt``)
    are NOT counted toward the per-condition target, so a resumed session
    will refill those slots automatically.

    Returns 0 if the history file doesn't exist yet.
    """
    if not history_path.exists():
        return 0
    store = RunHistoryStore.load(history_path)
    return sum(
        1 for r in store.query(experiment_tag=tag)
        if condition_id_from_record(r) == condition_id
        and r.outcome not in _NON_COUNTING_OUTCOMES
    )


def latest_outcome_for(
    history_path: Path, *, tag: str, condition_id: str,
) -> str | None:
    """Return the outcome of the most-recent (by ts) matching record, or None.

    Used to detect whether the just-finished subprocess aborted so we can
    retry without consuming a slot. Reads the same history file the
    subprocess writes to; safe under append_dedup merge driver.
    """
    if not history_path.exists():
        return None
    store = RunHistoryStore.load(history_path)
    matching = [
        r for r in store.query(experiment_tag=tag)
        if condition_id_from_record(r) == condition_id
    ]
    if not matching:
        return None
    matching.sort(key=lambda r: getattr(r, "ended_at", 0) or 0)
    return matching[-1].outcome


@dataclass(frozen=True)
class Condition:
    condition_id: str
    model_family: str
    skills: bool
    memory: bool
    evolution: bool
    # Ablation baseline gates (added 2026-04-26; run_ctx dropped 2026-04-28)
    prompt_variant: str = "full"
    hint_filter: bool = False
    knowledge_strict: bool = False
    stm: bool = True
    combat_conv: bool = True
    boss_hp: bool = True
    # Conditions A & B fields (added 2026-04-28)
    postrun: bool = False
    data_repo_subpath: str | None = None
    analysis_eq_strategic: bool = False
    # Mode B fields (added 2026-05-03; spec
    # docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md)
    disable_skill_seeds: bool = False
    use_seed_stubs: bool = False
    seed_stub_fill_enabled: bool = False

    def to_cli_args(
        self, *, tag: str, character: str, ascension: int | str, steps: int,
        passthrough: list[str] | tuple[str, ...] = (),
        keep_existing_run: bool = False,
    ) -> list[str]:
        # Flag names must match scripts/run_agent.py's argparse definitions.
        # If that file renames a flag, update this method accordingly.
        args: list[str] = [
            "--model-family", self.model_family,
            "--character", character,
            "--ascension", str(ascension),
            "--runs", "1",
            "--steps", str(steps),
            "--experiment-tag", tag,
        ]
        if not keep_existing_run:
            # Default: every subprocess starts from a clean game state.
            # Without this a timed-out / killed prior subprocess leaves an
            # active run that the next condition's subprocess would inherit.
            args.append("--abandon-existing")
        if not self.postrun:
            args.append("--no-postrun")
        if not self.skills:
            args.append("--no-skills")
        if not self.memory:
            args.append("--no-memory")
        if not self.evolution:
            args.append("--no-evolution")
        # Orchestrator-level passthrough flags (e.g. --launch-game /
        # --api-port=auto / --monitor-port=auto). These are forwarded
        # verbatim so each subprocess starts its own game instance.
        args.extend(passthrough)
        return args

    def to_env_overrides(self, *, tag: str = "") -> dict[str, str]:
        """Env-var overrides that pin STS2_*_ENABLED to the condition values.

        These are passed to subprocess.run's env kwarg. Paired with
        _PRESERVE_IF_SET in config.py so .env cannot override them.

        When ``data_repo_subpath`` is set, emits STS2_DATA_REPO (per-condition
        isolated subdir) and STS2_RUNS_HISTORY_REPO (shared parent for cross-
        condition aggregation). When ``analysis_eq_strategic`` is True, emits
        STS2_ANALYSIS_MODEL + STS2_THINK_EFFORT_ANALYSIS pinning the postrun
        model to the gameplay strategic-tier model.
        """
        import config

        out = {
            "STS2_SKILLS_ENABLED": "true" if self.skills else "false",
            "STS2_MEMORY_ENABLED": "true" if self.memory else "false",
            "STS2_EVOLUTION_ENABLED": "true" if self.evolution else "false",
            "STS2_PROMPT_VARIANT": self.prompt_variant,
            "STS2_PROMPT_HINT_FILTER": "true" if self.hint_filter else "false",
            "STS2_KNOWLEDGE_STRICT": "true" if self.knowledge_strict else "false",
            "STS2_STM_ENABLED": "true" if self.stm else "false",
            "STS2_COMBAT_CONVERSATION_ENABLED": "true" if self.combat_conv else "false",
            "STS2_INCLUDE_BOSS_HP": "true" if self.boss_hp else "false",
            # Mode B flags (always emit explicit value to prevent .env / shell
            # leakage into the experiment subprocess).
            "STS2_DISABLE_SKILL_SEEDS": "true" if self.disable_skill_seeds else "false",
            "STS2_USE_SEED_STUBS": "true" if self.use_seed_stubs else "false",
            "STS2_SEED_STUB_FILL_ENABLED": "true" if self.seed_stub_fill_enabled else "false",
        }

        if self.data_repo_subpath:
            shared_root = Path(os.environ.get("STS2_DATA_REPO") or paths.data_root())
            shared_root = shared_root.expanduser().resolve()
            subpath = self.data_repo_subpath.format(
                tag=tag, condition_id=self.condition_id,
            )
            isolated = (shared_root / subpath).resolve()
            out["STS2_DATA_REPO"] = str(isolated)
            out["STS2_RUNS_HISTORY_REPO"] = str(shared_root)
            # Defense-in-depth: even with isolated DATA_REPO, the static
            # seed file at src/skills/seeds/silent_card_notes.json (when
            # present) would auto-inject 87 encyclopedic notes into the
            # otherwise-empty card_memory_store on every fresh start —
            # contradicting the "from-zero" intent of self-evolve. Pin
            # the disable flag so this condition is safe even if the seed
            # file is restored or someone re-enables it. See
            # MemoryManager._load_card_seeds.
            out["STS2_DISABLE_CARD_SEEDS"] = "true"

        if self.analysis_eq_strategic:
            tier = config._MODEL_FAMILIES.get(self.model_family, {}).get("strategic")
            if tier is None:
                raise ValueError(
                    f"analysis_eq_strategic=True but family {self.model_family!r} "
                    f"has no 'strategic' tier in config._MODEL_FAMILIES"
                )
            # Sync MODEL only, not effort. Postrun effort is left to the
            # user's STS2_THINK_EFFORT_ANALYSIS env var (or family default)
            # so gameplay and postrun thinking budgets can be tuned
            # independently — important for "cheap gameplay + thoughtful
            # postrun" experiments.
            out["STS2_ANALYSIS_MODEL"] = tier["model"]

        return out


def build_condition_matrix(models: tuple[str, ...] = ("qwen", "gemini")) -> list[Condition]:
    matrix: list[Condition] = []
    for m in models:
        # baseline-strict: every gate set to baseline value, no postrun, shared data dir
        matrix.append(Condition(
            condition_id=f"{m}-baseline-strict", model_family=m,
            skills=False, memory=False, evolution=False,
            prompt_variant="baseline",
            hint_filter=True,
            knowledge_strict=True,
            stm=False,
            combat_conv=False,
            boss_hp=False,
            postrun=False,
        ))
        # prompt-only: full prompts, zero accumulated state, no postrun
        matrix.append(Condition(
            condition_id=f"{m}-prompt-only", model_family=m,
            skills=False, memory=False, evolution=False,
            prompt_variant="full",
            hint_filter=False,
            knowledge_strict=False,
            stm=False,
            combat_conv=True,
            boss_hp=True,
            postrun=False,
        ))
        # mode-a: full prompts + expert seeds (skills=True so seeds load),
        # but no STM, no memory, no postrun. Tests "expert priors only".
        # Matches spec's "Mode A" condition.
        matrix.append(Condition(
            condition_id=f"{m}-mode-a", model_family=m,
            skills=True,           # expert seeds load
            memory=False,          # no L4 cross-run
            evolution=False,       # no postrun evolution
            prompt_variant="full",
            hint_filter=False,
            knowledge_strict=False,
            stm=False,             # no Strategic Thread
            combat_conv=True,
            boss_hp=True,
            postrun=False,         # no postrun stage
        ))
        # self-evolve: now Mode B — agent-written stubs replace expert seeds,
        # postrun stub fill enabled, isolated data dir, postrun model =
        # gameplay strategic model.
        matrix.append(Condition(
            condition_id=f"{m}-self-evolve", model_family=m,
            skills=True, memory=True, evolution=True,
            prompt_variant="full",
            hint_filter=False,
            knowledge_strict=False,
            stm=True,
            combat_conv=True,
            boss_hp=True,
            postrun=True,
            analysis_eq_strategic=True,
            data_repo_subpath="experiments/{tag}/{condition_id}",
            # Mode B: don't load expert seeds, load stubs instead, fill them postrun
            disable_skill_seeds=True,
            use_seed_stubs=True,
            seed_stub_fill_enabled=True,
        ))
        # full: defaults preserve current behavior; data dir shared (contaminated)
        matrix.append(Condition(
            condition_id=f"{m}-full", model_family=m,
            skills=True, memory=True, evolution=True,
        ))
    return matrix


def filter_matrix_by_conditions(
    matrix: list[Condition], conditions: str,
) -> list[Condition]:
    """Filter the condition matrix by condition kind.

    ``conditions`` is a comma-separated string of kinds (e.g.,
    ``"self-evolve"`` or ``"baseline-strict,full"``). The kind is the
    suffix of ``condition_id`` after the model prefix — i.e.,
    ``"gemini-self-evolve"`` has kind ``"self-evolve"``.

    Empty string returns the full matrix unchanged.
    """
    if not conditions:
        return matrix
    wanted = {k.strip() for k in conditions.split(",") if k.strip()}
    return [c for c in matrix if c.condition_id.split("-", 1)[1] in wanted]


def run_single(
    cond: Condition,
    *,
    tag: str,
    character: str,
    ascension: int | str,
    steps: int,
    timeout: int = 0,
    passthrough: list[str] | tuple[str, ...] = (),
    keep_existing_run: bool = False,
) -> int:
    cmd = [sys.executable, "-m", "scripts.run_agent"] + cond.to_cli_args(
        tag=tag, character=character, ascension=ascension, steps=steps,
        passthrough=passthrough, keep_existing_run=keep_existing_run,
    )
    env = {**os.environ, **_ABLATION_FIXED_ENV, **cond.to_env_overrides(tag=tag)}
    logger.info("Launching [%s]: %s", cond.condition_id, " ".join(cmd[3:]))
    # timeout <= 0 means no timeout — let the run play to victory/defeat/max_steps
    _timeout = timeout if timeout and timeout > 0 else None
    try:
        proc = subprocess.run(cmd, timeout=_timeout, env=env)
    except subprocess.TimeoutExpired:
        logger.error(
            "[%s] run exceeded timeout of %d seconds; marking as failed",
            cond.condition_id, timeout,
        )
        return -1
    return proc.returncode


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", type=str, default="")
    parser.add_argument("--runs-per-condition", type=int, default=10)
    parser.add_argument("--character", type=str, default="Silent")
    parser.add_argument(
        "--ascension", type=str, default="auto",
        help=(
            "Ascension: integer (0-20), 'auto' (starts from the highest "
            "cleared + 1, default, starts at A0 if no prior clears), or "
            "'auto-N' (auto-progress with floor A<N>)."
        ),
    )
    parser.add_argument(
        "--steps", type=int, default=5000,
        help="Max steps per run (default 5000 — effectively 'run to victory or defeat').",
    )
    parser.add_argument("--models", nargs="+", default=["qwen", "gemini"])
    parser.add_argument(
        "--conditions", type=str, default="",
        help=(
            "Comma-separated condition kinds to run (e.g., 'self-evolve' or "
            "'baseline-strict,full'). Default empty = all 4 kinds per model."
        ),
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--launch-game", action="store_true",
        help="Forward --launch-game to each run_agent subprocess so each run "
             "starts its own game instance (kills it on run end).",
    )
    parser.add_argument(
        "--api-port", type=str, default="",
        help="Forward --api-port=<value> to each run_agent subprocess. "
             "Use 'auto' for free-port autodetection per run.",
    )
    parser.add_argument(
        "--monitor-port", type=str, default="",
        help="Forward --monitor-port=<value> to each run_agent subprocess.",
    )
    parser.add_argument(
        "--timeout-sec", type=int, default=0,
        help=(
            "Per-run subprocess timeout in seconds. 0 (default) = no timeout — "
            "let the run play to victory, defeat, or max_steps."
        ),
    )
    parser.add_argument(
        "--keep-existing-run", action="store_true",
        help=(
            "Skip --abandon-existing on every subprocess so a saved/in-progress "
            "game is re-entered instead of wiped. Use when resuming a partially-"
            "played run mid-experiment (e.g. orchestrator was Ctrl-C'd and the "
            "game still has the run open). WARNING: if a prior subprocess "
            "crashed mid-combat, the next subprocess will inherit that exact "
            "state — make sure that's actually what you want for the experiment."
        ),
    )
    parser.add_argument("--history", type=Path, default=paths.runs_history_file(),
                        help="Path to run history JSONL (used for resume).")
    args = parser.parse_args()

    # Build orchestrator-level passthrough flags forwarded to each subprocess.
    passthrough: list[str] = []
    if args.launch_game:
        passthrough.append("--launch-game")
    if args.api_port:
        passthrough.append(f"--api-port={args.api_port}")
    if args.monitor_port:
        passthrough.append(f"--monitor-port={args.monitor_port}")

    tag = args.tag or f"ablation-{datetime.datetime.now().strftime('%Y-%m-%dT%H%M')}"
    matrix = build_condition_matrix(tuple(args.models))

    if args.conditions:
        matrix = filter_matrix_by_conditions(matrix, args.conditions)
        if not matrix:
            logger.error(
                "No conditions matched filter %r. Available kinds: "
                "baseline-strict, prompt-only, self-evolve, full",
                args.conditions,
            )
            return 1
        logger.info("Filtered matrix to %d conditions: %s", len(matrix),
                    [c.condition_id for c in matrix])

    total_target = len(matrix) * args.runs_per_condition
    logger.info("Starting ablation: tag=%s, %d conditions x %d runs = %d target",
                tag, len(matrix), args.runs_per_condition, total_target)

    if args.dry_run:
        for cond in matrix:
            logger.info("DRY-RUN %s -> %s", cond.condition_id,
                        cond.to_cli_args(tag=tag, character=args.character,
                                         ascension=args.ascension, steps=args.steps,
                                         passthrough=passthrough,
                                         keep_existing_run=args.keep_existing_run))
        return 0

    # Resume: count per-condition records already in history under this tag.
    resume_plan: list[tuple[Condition, int]] = []
    already_done = 0
    for cond in matrix:
        existing = count_existing_runs(
            args.history, tag=tag, condition_id=cond.condition_id,
        )
        remaining = max(0, args.runs_per_condition - existing)
        if existing:
            logger.info("[%s] resume: %d already done, %d more to run",
                        cond.condition_id, existing, remaining)
        resume_plan.append((cond, remaining))
        already_done += existing

    total_new = sum(rem for _, rem in resume_plan)
    logger.info("Resume plan: %d already done, %d new runs to launch",
                already_done, total_new)

    completed = 0
    aborted_retries = 0
    try:
        for cond, remaining in resume_plan:
            slot = 0
            while slot < remaining:
                slot += 1
                # Per-slot retry: a single slot may launch multiple subprocesses
                # if early ones crash with retryable outcomes. We only count
                # the slot as "filled" when a non-aborted record lands in
                # history.jsonl OR we hit RETRY_CAP_PER_SLOT and bail.
                for attempt in range(1, RETRY_CAP_PER_SLOT + 1):
                    suffix = f" (retry {attempt - 1})" if attempt > 1 else ""
                    logger.info(
                        "--- [%s] slot %d/%d%s ---",
                        cond.condition_id, slot, remaining, suffix,
                    )
                    rc = run_single(
                        cond, tag=tag, character=args.character,
                        ascension=args.ascension, steps=args.steps,
                        timeout=args.timeout_sec, passthrough=passthrough,
                        keep_existing_run=args.keep_existing_run,
                    )
                    if rc != 0:
                        logger.warning(
                            "[%s] slot %d attempt %d exited %d",
                            cond.condition_id, slot, attempt, rc,
                        )
                    outcome = latest_outcome_for(
                        args.history, tag=tag, condition_id=cond.condition_id,
                    )
                    if outcome in _RETRYABLE_OUTCOMES and attempt < RETRY_CAP_PER_SLOT:
                        aborted_retries += 1
                        logger.warning(
                            "[%s] slot %d attempt %d outcome=%s — "
                            "not counting, retrying (%d/%d)",
                            cond.condition_id, slot, attempt, outcome,
                            attempt, RETRY_CAP_PER_SLOT,
                        )
                        continue
                    # Either non-abort outcome, or hit retry cap — fill the slot.
                    if outcome in _RETRYABLE_OUTCOMES:
                        logger.error(
                            "[%s] slot %d aborted %d times in a row — "
                            "filling slot anyway and moving on",
                            cond.condition_id, slot, RETRY_CAP_PER_SLOT,
                        )
                    break
                completed += 1
                logger.info(
                    "Progress: %d/%d new (aborted retries this session: %d)",
                    completed, total_new, aborted_retries,
                )
    except KeyboardInterrupt:
        logger.warning(
            "Interrupted by user (Ctrl-C). Completed %d/%d new runs this session "
            "(plus %d from prior sessions). Results recorded under tag=%s. "
            "Resume by re-running with --tag %s (same args). "
            "Retrieve with: python -m scripts.ablation_report --tag %s",
            completed, total_new, already_done, tag, tag, tag,
        )
        return 130

    logger.info(
        "Done. Launched %d new runs (%d from prior sessions). Tag=%s. "
        "Run: python -m scripts.ablation_report --tag %s",
        completed, already_done, tag, tag,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
