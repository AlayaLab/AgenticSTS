"""Manually trigger post-run processing from a run log.

Extracts combat episodes from log, saves to memory, then runs self-evolution.

Usage:
    python -m scripts.run_evolution                    # latest log, extract + evolve
    python -m scripts.run_evolution --log <path>       # specific log
    python -m scripts.run_evolution --extract-only     # only extract memory, skip evolution
    python -m scripts.run_evolution --evolve-only      # only evolve, skip extraction
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from src.storage import paths  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
)
logger = logging.getLogger(__name__)


def _evolution_entry_name(tool: str, tool_input: dict) -> str:
    for key in ("tool_name", "skill_name", "metric", "key", "guide_type"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return tool


def _evolution_entry_status(result: str) -> str:
    text = result.strip().lower()
    if text.startswith("success:"):
        return "success"
    if text.startswith("rejected:"):
        return "rejected"
    if "error" in text or text.startswith("unknown"):
        return "error"
    return "ok"


# ── Log-based combat episode extraction ─────────────────────


def _extract_episodes_from_log(log_path: Path) -> tuple[list, str, str]:
    """Extract CombatEpisodes from a run log JSONL file.

    Uses combat_summary events (complete per-round data) and enriches
    with enemy_intents from state events where available.

    Returns: (episodes, run_id, character)
    """
    from src.memory.models_v2 import CombatEpisode, CombatRound

    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    run_id = "unknown"
    character = "Unknown"

    # Collect enemy intents per floor+round from state events
    # key: (floor, round_num) -> list of intent strings
    intent_map: dict[tuple[int, int], list[str]] = {}

    for e in events:
        if e["event"] == "run_start":
            run_id = e.get("run_id", "unknown")
        if e["event"] == "state":
            combat = e.get("combat")
            if combat and combat.get("enemies"):
                floor = e.get("floor", 0)
                rnd = combat.get("round", 0)
                intents = []
                for enemy in combat["enemies"]:
                    name = enemy.get("name", "?")
                    # Try structured intents first
                    intent_list = enemy.get("intents", [])
                    if intent_list:
                        parts = []
                        for it in intent_list:
                            if it.get("damage") is not None:
                                hits = it.get("hits", 1)
                                if hits and hits > 1:
                                    parts.append(f"Attack({it['damage']}x{hits}={it.get('total_damage', it['damage']*hits)})")
                                else:
                                    parts.append(f"Attack({it['damage']})")
                            elif it.get("type") and it["type"] != "Unknown":
                                parts.append(it["type"])
                            elif it.get("label"):
                                parts.append(it["label"])
                        intent_str = ", ".join(parts) if parts else (enemy.get("intent") or "?")
                    else:
                        intent_str = enemy.get("intent") or "?"
                    intents.append(f"{name}: {intent_str}")
                intent_map[(floor, rnd)] = intents
        # Detect character from llm_call prompts
        if e["event"] == "llm_call":
            prompt = e.get("prompt", "")
            for ch in ("The Ironclad", "The Silent", "The Defect", "The Regent", "The Necrobinder"):
                if ch in prompt:
                    character = ch
                    break

    # Build episodes from combat_summary events
    episodes = []
    for e in events:
        if e["event"] != "combat_summary":
            continue

        floor = e.get("floor", 0)
        rounds = []
        for r in e.get("rounds", []):
            rnd_num = r.get("round", 0)
            # Enrich with intents from state events
            intents = intent_map.get((floor, rnd_num), ())
            rounds.append(CombatRound(
                round_num=rnd_num,
                energy_available=r.get("energy_available", 0),
                energy_used=r.get("energy_used", 0),
                hp_start=r.get("hp_start", 0),
                hp_end=r.get("hp_end", 0),
                block_gained=r.get("block_gained", 0),
                enemy_intents=tuple(intents),
                cards_played=tuple(r.get("cards_played", [])),
                potions_used=tuple(r.get("potions_used", [])),
                damage_dealt=r.get("damage_dealt", 0),
                damage_taken=r.get("damage_taken", 0),
            ))

        episode = CombatEpisode(
            run_id=run_id,
            floor=floor,
            act=max(1, (floor - 1) // 17 + 1),  # approximate act from floor
            enemy_key=e.get("enemy_key", "unknown"),
            character=character,
            combat_type=e.get("combat_type", "monster"),
            rounds=tuple(rounds),
            hp_before=e.get("hp_before", 0),
            hp_after=e.get("hp_after", 0),
            won=e.get("won", True),
            hp_delta=e.get("hp_after", 0) - e.get("hp_before", 0),
            total_damage_dealt=e.get(
                "total_damage_dealt", sum(r.damage_dealt for r in rounds)
            ),
            total_damage_taken=sum(r.damage_taken for r in rounds),
            total_cards_played=e.get("total_cards_played", 0),
        )
        episodes.append(episode)

    return episodes, run_id, character


# ── Evolution context ───────────────────────────────────────


def _rebuild_context_from_log(log_path: Path) -> str:
    """Rebuild evolution context from a run log JSONL file."""
    events = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))

    character = "Unknown"
    victory = False
    final_floor = 0
    run_id = "unknown"
    decisions: list[str] = []

    for e in events:
        if e["event"] == "run_start":
            run_id = e.get("run_id", "unknown")
        if e["event"] == "state":
            floor = e.get("floor", 0)
            if floor:
                final_floor = max(final_floor, floor)
        if e["event"] == "decision":
            floor = e.get("floor", 0)
            st = e.get("state_type", "?")
            source = e.get("source", "?")
            reasoning = e.get("reasoning", "")
            if reasoning:
                snippet = (reasoning[:80] + "...") if len(reasoning) > 80 else reasoning
                decisions.append(f"  Floor {floor} ({st}) [{source}]: {snippet}")
        if e["event"] == "run_end":
            victory = e.get("victory", False)
            final_floor = e.get("floor", final_floor)
        if e["event"] == "llm_call":
            prompt = e.get("prompt", "")
            for ch in ("The Ironclad", "The Silent", "The Defect", "The Regent", "The Necrobinder"):
                if ch in prompt:
                    character = ch
                    break

    result_str = "VICTORY" if victory else f"DEFEAT at Floor {final_floor}"
    decision_text = "\n".join(decisions[-15:]) if decisions else "  (no decisions recorded)"

    sections = [
        f"You just completed a Slay the Spire 2 run as {character}.",
        f"Result: {result_str}",
        f"Run ID: {run_id} | Total events: {len(events)}",
        "",
        f"## Run Replay (last {min(15, len(decisions))} decisions)",
        decision_text,
        "",
        "## Focus",
        "Look at your MISTAKES. What tool or skill would have prevented the worst outcome?",
        "Max 3 improvements per run. Be specific and actionable.",
    ]
    return "\n".join(sections)


# ── Main ────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Run post-run processing manually")
    parser.add_argument("--log", type=str, help="Path to run log JSONL file")
    parser.add_argument("--extract-only", action="store_true", help="Only extract memory, skip evolution")
    parser.add_argument("--evolve-only", action="store_true", help="Only evolve, skip extraction")
    args = parser.parse_args()

    # Find log
    if args.log:
        log_path = Path(args.log)
    else:
        log_dir = Path("logs")
        logs = sorted(log_dir.glob("run_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not logs:
            logger.error("No run logs found in logs/")
            return
        log_path = logs[0]

    logger.info("Using log: %s", log_path)

    # ── Extract combat episodes ─────────────────────────────
    if not args.evolve_only:
        episodes, run_id, character = _extract_episodes_from_log(log_path)
        logger.info("Extracted %d combat episodes (run=%s, char=%s)", len(episodes), run_id, character)

        if episodes:
            from src.memory.combat_store import CombatMemoryStore

            store = CombatMemoryStore.load(paths.combat_episodes_file())
            existing = store.count

            # Check for duplicates (same run_id + floor)
            existing_keys = {(ep.run_id, ep.floor) for ep in store.get_all()}
            new_eps = [ep for ep in episodes if (ep.run_id, ep.floor) not in existing_keys]

            if new_eps:
                store.add_batch(new_eps)
                store.save(paths.combat_episodes_file())
                logger.info("Saved %d new episodes (skipped %d duplicates). Total: %d -> %d",
                            len(new_eps), len(episodes) - len(new_eps), existing, store.count)
            else:
                logger.info("All %d episodes already exist, nothing new to save", len(episodes))
        else:
            logger.info("No combat_summary events found in log — nothing to extract")

    if args.extract_only:
        return

    # ── Run evolution ───────────────────────────────────────
    context = _rebuild_context_from_log(log_path)
    logger.info("Evolution context (%d chars):\n%s\n...", len(context), context[:500])

    from src.brain.evolution_engine import EvolutionEngine
    from src.brain.v2_backend import V2Backend

    backend = V2Backend()

    # Load optional components
    tool_executor = None
    dynamic_registry = None
    skill_library = None
    memory_manager = None

    try:
        from src.brain.tool_executor import ToolExecutor
        from src.knowledge.knowledge import GameKnowledge

        knowledge = GameKnowledge()
        tool_executor = ToolExecutor(knowledge=knowledge)
    except Exception as exc:
        logger.warning("Could not init tool executor: %s", exc)

    try:
        from src.brain.dynamic_tools import DynamicToolRegistry

        dynamic_registry = DynamicToolRegistry()
    except Exception as exc:
        logger.warning("Could not init dynamic registry: %s", exc)

    try:
        from src.skills.library import SkillLibrary

        skill_library = SkillLibrary()
    except Exception as exc:
        logger.warning("Could not init skill library: %s", exc)

    try:
        from src.memory.memory_manager import MemoryManager

        memory_manager = MemoryManager()
    except Exception as exc:
        logger.warning("Could not init memory manager: %s", exc)

    engine = EvolutionEngine(
        backend=backend,
        tool_executor=tool_executor,
        dynamic_registry=dynamic_registry,
        skill_library=skill_library,
        memory_manager=memory_manager,
    )

    logger.info("Running evolution (Opus, max %d rounds)...", config.EVOLUTION_MAX_ROUNDS)
    actions = engine.run_evolution(context)

    if actions:
        logger.info("Evolution completed: %d actions", len(actions))
        for a in actions:
            inp_str = json.dumps(a.tool_input, ensure_ascii=False)[:80]
            logger.info("  [%s] %s -> %s", a.tool, inp_str, a.result[:200])

        # Write to evolution log
        log_file = paths.evolution_log_file()
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a", encoding="utf-8") as f:
            for a in actions:
                record = {
                    "run_id": "manual",
                    "action": a.tool,
                    "name": _evolution_entry_name(a.tool, a.tool_input),
                    "status": _evolution_entry_status(a.result),
                    "tool": a.tool,
                    "input": json.dumps(a.tool_input, ensure_ascii=False)[:300],
                    "result": a.result[:500],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.info("Evolution log updated: %s", log_file)
    else:
        logger.info("Evolution completed: no actions taken")


if __name__ == "__main__":
    main()
