"""Memory Manager: unified facade for the V2 HCM memory system.

Orchestrates domain-specific stores (combat, route, card_build),
guides, and short-term memory.

Provides query_for_decision() for prompt injection.
"""

from __future__ import annotations

import logging
from pathlib import Path

import config
from src.state.game_state import GameState

logger = logging.getLogger(__name__)


class MemoryManager:
    """Unified facade for the V2 HCM memory system."""

    def __init__(self, data_dir: Path | None = None) -> None:
        base = data_dir or Path(config.MEMORY_DIR)
        base.mkdir(parents=True, exist_ok=True)

        self._base_dir = base
        self._v2_dir = base / "v2"
        self._guide_path = self._v2_dir / "guides.json"

        self._consolidation_count = self._load_consolidation_counter(base)

        # V2 (HCM) stores
        self._init_v2_stores(base)

        logger.info("MemoryManager loaded [HCM V2]")

    def _init_v2_stores(self, base: Path) -> None:
        """Initialize V2 HCM domain-specific stores."""
        from src.memory.card_build_store import CardBuildStore
        from src.memory.card_memory_store import CardMemoryStore
        from src.memory.combat_store import CombatMemoryStore
        from src.memory.guide_store import GuideStore
        from src.memory.route_store import RouteMemoryStore
        from src.memory.short_term import ShortTermMemory

        self._v2_dir.mkdir(parents=True, exist_ok=True)

        self._short_term = ShortTermMemory()
        self._combat_store = CombatMemoryStore.load(
            self._v2_dir / "combat_episodes.jsonl",
        )
        self._route_store = RouteMemoryStore.load(
            self._v2_dir / "route_memories.jsonl",
        )
        self._card_build_store = CardBuildStore.load(
            self._v2_dir / "card_builds.jsonl",
        )
        self._card_memory_store = CardMemoryStore.load(
            self._v2_dir / "card_memories.json",
        )
        self._guide_store = GuideStore.load(self._guide_path)

        from src.memory.event_store import EventMemoryStore
        self._event_store = EventMemoryStore.load(
            self._v2_dir / "event_memories.jsonl",
        )

        # Load card seed notes
        self._load_card_seeds()

        logger.info(
            "HCM V2 stores loaded: %d combat, %d route, %d card_build, %d card_mem, %d event, guides=%s",
            self._combat_store.count,
            self._route_store.count,
            self._card_build_store.count,
            self._card_memory_store.count,
            self._event_store.count,
            self._guide_store.stats(),
        )

    def reload_prompt_context(self) -> dict[str, int]:
        """Reload persistent prompt-time stores for the next run.

        Long-lived agent processes can outlive post-run consolidation updates
        written by a prior run. Reload the prompt-facing stores so new runs use
        the latest guides without discarding short-term state mid-run.
        """
        from src.memory.event_store import EventMemoryStore
        from src.memory.guide_store import GuideStore

        self._guide_store = GuideStore.load(self._guide_path)
        self._event_store = EventMemoryStore.load(
            self._v2_dir / "event_memories.jsonl",
        )

        stats = {
            "guide_combat": self._guide_store.combat_guide_count,
            "guide_route": self._guide_store.route_guide_count,
            "guide_deck": self._guide_store.deck_guide_count,
            "event_memories": self._event_store.count,
        }
        logger.info("Reloaded prompt context from disk: %s", stats)
        return stats

    def _load_card_seeds(self) -> None:
        """Load card seed notes from any `*_card_notes.json` in the seed directory.

        Each character has its own `<character>_card_notes.json` (e.g.
        `silent_card_notes.json`, `regent_card_notes.json`). Each entry has
        `character`, `card_name`, `note`, plus optional metadata fields like
        `star_role` / `forge_role` (read by Phase-3 economy formatters, ignored
        here).

        Set ``STS2_DISABLE_CARD_SEEDS=true`` to skip — used by fresh-start /
        self-evolve experiments where the agent must build card_memory
        from real traces only, with no pre-seeded encyclopedic notes.
        """
        import json as _json
        import os as _os

        if _os.getenv("STS2_DISABLE_CARD_SEEDS", "").strip().lower() in ("1", "true", "yes"):
            logger.info("STS2_DISABLE_CARD_SEEDS set — skipping card seed load.")
            return

        seed_dir = Path(config.SKILLS_SEED_DIR)
        if not seed_dir.exists():
            return

        from src.memory.models_v2 import CardMemory

        total_loaded = 0
        for seed_file in sorted(seed_dir.glob("*_card_notes.json")):
            try:
                data = _json.loads(seed_file.read_text(encoding="utf-8"))
                seeds: list[CardMemory] = []
                for entry in data:
                    seeds.append(CardMemory(
                        character=entry.get("character", ""),
                        card_name=entry.get("card_name", "").lower(),
                        note=entry.get("note") or entry.get("seed_note", ""),
                    ))
                loaded = self._card_memory_store.load_seeds(seeds)
                total_loaded += loaded
                if loaded > 0:
                    logger.info("Loaded %d card seed notes from %s", loaded, seed_file.name)
            except Exception as exc:
                logger.warning("Failed to load card seeds from %s: %s", seed_file, exc)

        if total_loaded > 0:
            logger.info("Total card seed notes loaded across all characters: %d", total_loaded)

    # ── V2 (HCM) query ─────────────────────────────────────────

    def query_for_decision(self, gs: GameState, *, archetype: str = "", current_round: int = 0):
        """Query HCM stores for the current decision.

        Args:
            gs: Current game state.
            archetype: Detected deck archetype (e.g. "poison", "shiv").
                Used for DeckGuide retrieval. Empty = "general".
            current_round: Combat round number (>0 enables situation-level retrieval).

        Returns a WorkingContext.
        """
        from src.memory.retriever import query_for_decision

        return query_for_decision(
            gs=gs,
            short_term=self._short_term,
            combat_store=self._combat_store,
            route_store=self._route_store,
            card_build_store=self._card_build_store,
            guide_store=self._guide_store,
            card_memory_store=self._card_memory_store,
            event_store=self._event_store,
            archetype=archetype,
            current_round=current_round,
        )

    @property
    def v2_enabled(self) -> bool:
        return True

    @property
    def short_term(self):
        """Access short-term memory (V2)."""
        return self._short_term

    @property
    def combat_store(self):
        return self._combat_store

    @property
    def route_store(self):
        return self._route_store

    @property
    def card_build_store(self):
        return self._card_build_store

    @property
    def guide_store(self):
        return self._guide_store

    @property
    def card_memory_store(self):
        return self._card_memory_store

    @property
    def event_store(self):
        return self._event_store

    # ── Guide consolidation counter ─────────────────────────

    @staticmethod
    def _load_consolidation_counter(base_dir: Path) -> int:
        import json
        path = base_dir / "consolidation_counter.json"
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8")).get("count", 0)
            except Exception:
                return 0
        return 0

    def increment_consolidation_count(self) -> None:
        self._consolidation_count += 1
        import json
        path = self._base_dir / "consolidation_counter.json"
        path.write_text(json.dumps({"count": self._consolidation_count}), encoding="utf-8")

    @property
    def should_consolidate(self) -> bool:
        return self._consolidation_count >= config.CONSOLIDATION_EVERY_N_RUNS

    def reset_consolidation_count(self) -> None:
        self._consolidation_count = 0
        import json
        path = self._base_dir / "consolidation_counter.json"
        path.write_text(json.dumps({"count": 0}), encoding="utf-8")

    def maintenance(self) -> dict[str, int]:
        """Run periodic maintenance (currently no-op after rules removal)."""
        return {}

    def save_all(self) -> None:
        """Flush all stores to disk."""
        v2_dir = self._base_dir / "v2"
        v2_dir.mkdir(parents=True, exist_ok=True)
        self._combat_store.save(v2_dir / "combat_episodes.jsonl")
        self._route_store.save(v2_dir / "route_memories.jsonl")
        self._card_build_store.save(v2_dir / "card_builds.jsonl")
        self._card_memory_store.save(v2_dir / "card_memories.json")
        self._guide_store.save(v2_dir / "guides.json")
        self._event_store.save(v2_dir / "event_memories.jsonl")

        logger.debug("Saved all memory stores to %s", self._base_dir)

    def reset_short_term(self) -> None:
        """Reset short-term memory for a new run."""
        self._short_term.reset_run()

    def stats(self) -> dict[str, int]:
        """Return memory system statistics."""
        s = {
            "v2_combat_episodes": self._combat_store.count,
            "v2_route_memories": self._route_store.count,
            "v2_card_builds": self._card_build_store.count,
            "v2_card_memories": self._card_memory_store.count,
            "v2_event_memories": self._event_store.count,
        }
        if self._guide_store:
            s.update({f"v2_{k}": v for k, v in self._guide_store.stats().items()})
        return s
