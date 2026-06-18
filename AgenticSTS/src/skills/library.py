"""SkillLibrary: retrieval-augmented skill store for game decisions.

Loads seed skills from JSON, supports runtime skill discovery,
and provides context-aware retrieval for prompt injection.
"""

from __future__ import annotations

import json
import logging
import random
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from config import SKILL_EXPLORATION_BONUS
from src.patch.version import get_runtime_version
from src.skills.models import Skill

if TYPE_CHECKING:
    from src.memory.situation import SituationTag

logger = logging.getLogger(__name__)


class SkillLibrary:
    """Manages the skill collection with context-aware retrieval.

    NOT thread-safe. All access (queries, mutations, persistence) should
    happen from the agent loop's single async task. LLM calls that run
    in thread executors must not touch the library directly.
    """

    def __init__(self, skills: tuple[Skill, ...] = ()) -> None:
        self._skills: dict[str, Skill] = {s.skill_id: s for s in skills}
        self._active_override: set[str] | None = None

    @property
    def count(self) -> int:
        return len(self._skills)

    @property
    def active_count(self) -> int:
        return sum(1 for s in self._skills.values() if s.active)

    @property
    def all_skills(self) -> tuple[Skill, ...]:
        return tuple(self._skills.values())

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)

    def add(self, skill: Skill) -> None:
        """Add or replace a skill."""
        self._skills[skill.skill_id] = skill

    def add_batch(self, skills: list[Skill]) -> int:
        """Add multiple skills. Returns count of new skills added."""
        added = 0
        for s in skills:
            if s.skill_id not in self._skills:
                added += 1
            self._skills[s.skill_id] = s
        return added

    def update(self, skill: Skill) -> None:
        """Replace an existing skill (must exist)."""
        if skill.skill_id in self._skills:
            self._skills[skill.skill_id] = skill

    def deactivate(self, skill_id: str, superseded_by: str = "") -> None:
        """Deactivate a skill."""
        skill = self._skills.get(skill_id)
        if skill:
            self._skills[skill_id] = skill.with_deactivation(superseded_by)

    def replace(self, old_id: str, new_skill: Skill) -> None:
        """Atomic swap: deactivate ``old_id`` and install ``new_skill``.

        Semantics match a MERGE: the old skill is deactivated with
        ``superseded_by=new_skill.skill_id``, and the new skill is added
        (or overwrites the same slot if ``new_skill.skill_id == old_id``).

        Validation is performed before any mutation so callers never see
        a half-applied state.

        Raises:
            KeyError: ``old_id`` is not in the library.
            ValueError: ``new_skill.skill_id`` differs from ``old_id`` and
                is already present (would collide).

        Persistence: caller must explicitly invoke :meth:`save` — this
        library does not auto-persist (matches existing ``add``/``update``
        behavior).
        """
        if old_id not in self._skills:
            raise KeyError(f"skill {old_id!r} not in library")
        if new_skill.skill_id != old_id and new_skill.skill_id in self._skills:
            raise ValueError(
                f"skill id collision: {new_skill.skill_id!r} already present"
            )
        old = self._skills[old_id]
        self._skills[old_id] = old.with_deactivation(
            superseded_by=new_skill.skill_id,
        )
        self._skills[new_skill.skill_id] = new_skill

    def query(
        self,
        state_type: str = "",
        enemy_name: str = "",
        act: int = 1,
        hp_ratio: float = 1.0,
        deck_size: int = 0,
        hand_cards: frozenset[str] = frozenset(),
        context_tags: frozenset[str] = frozenset(),
        category: str = "",
        limit: int = 5,
        *,
        situation: SituationTag | None = None,
    ) -> list[tuple[Skill, float]]:
        """Retrieve skills matching the given game context.

        Returns list of (skill, relevance_score) sorted by effective priority.
        Only returns active skills.
        """
        # During replay: only return overridden skills
        if self._active_override is not None:
            return [
                (self._skills[sid], 1.0)
                for sid in self._active_override
                if sid in self._skills
            ][:limit]

        matches: list[tuple[Skill, float]] = []

        for skill in self._skills.values():
            if not skill.active:
                continue
            if skill.status == "deactivated":
                continue
            if skill.status == "pending_fill":
                # Mode B stub awaiting first fill — content is 'TBD', skip retrieval.
                continue

            # Category filter (if specified)
            if category and skill.category != category and skill.category != "general":
                # Combat and boss categories are interchangeable:
                # - combat skills are relevant in boss fights
                # - boss skills are relevant in combat (boss may be misclassified as elite/monster)
                combat_boss = {category, skill.category} <= {"combat", "boss"}
                if not combat_boss:
                    continue

            triggered, relevance = skill.trigger.matches(
                state_type=state_type,
                enemy_name=enemy_name,
                act=act,
                hp_ratio=hp_ratio,
                deck_size=deck_size,
                hand_cards=hand_cards,
                context_tags=context_tags,
                situation=situation,
            )

            if triggered:
                # Combine relevance with effective priority
                score = relevance * skill.effective_priority
                # Exploration bonus: untried skills get a boost to ensure they're tested
                if skill.usage_count == 0:
                    score += SKILL_EXPLORATION_BONUS
                matches.append((skill, score))

        # Sort by score descending; jitter breaks ties so skills with
        # identical scores rotate across queries instead of always winning
        matches.sort(key=lambda x: (x[1] + random.uniform(0, 0.001)), reverse=True)

        # Slot quota: guarantee min(2, available) non-seed, guarantee min(3, available) seed,
        # then fill remaining slots from EITHER pool by best score.
        all_seed = [(s, sc) for s, sc in matches if s.source == "seed"]
        all_nonseed = [(s, sc) for s, sc in matches if s.source != "seed"]

        # Phase 1: guarantee minimum non-seed slots
        nonseed_guaranteed = all_nonseed[:min(2, len(all_nonseed))]
        # Phase 2: guarantee minimum seed slots
        seed_guaranteed = all_seed[:min(3, len(all_seed))]
        # Phase 3: fill remaining from ALL leftover candidates by score
        used_ids = {s.skill_id for s, _ in nonseed_guaranteed + seed_guaranteed}
        remaining_pool = [(s, sc) for s, sc in matches if s.skill_id not in used_ids]
        remaining_pool.sort(key=lambda x: x[1] + random.uniform(0, 0.001), reverse=True)
        remaining_slots = max(0, limit - len(nonseed_guaranteed) - len(seed_guaranteed))
        fill = remaining_pool[:remaining_slots]

        combined = nonseed_guaranteed + seed_guaranteed + fill
        combined.sort(key=lambda x: x[1] + random.uniform(0, 0.001), reverse=True)
        top = combined[:limit]

        return top

    def record_outcome(
        self,
        skill_ids: list[str],
        success: bool,
        quality_score: float = 1.0,
    ) -> None:
        """Record outcome for skills that were active during a decision.

        Called after a combat/decision where these skills were injected
        into the prompt. Updates usage count and confidence.

        Args:
            skill_ids: Skill IDs that were injected into the prompt.
            success: Whether the decision led to a positive outcome.
            quality_score: 0.0-1.0 quality metric (default 1.0 for
                backward compatibility). Higher values give the
                observation more weight in the confidence update.
        """
        for sid in skill_ids:
            skill = self._skills.get(sid)
            if skill and skill.status != "deactivated":
                self._skills[sid] = skill.with_usage(
                    success, quality_score=quality_score,
                )

    def record_noncombat_outcome(self, skill_ids: list[str], score: float) -> None:
        """Record non-combat score for skills active during this act.

        Called at boss fight start. Updates both noncombat_scores (rolling
        window) AND main confidence (affects retrieval priority).
        Score mapping: >30 = success, quality = score/111 (linear 0.1-1.0).
        """
        for sid in skill_ids:
            if sid not in self._skills:
                continue
            skill = self._skills[sid]
            if skill.status == "deactivated":
                continue
            # 1. Append noncombat score (keep last 3)
            updated = skill.with_noncombat_score(score)
            # 2. Feed back into main confidence for retrieval priority
            success = score > 30  # at least beat Act 1 boss
            quality = max(0.1, min(1.0, score / 111))
            updated = updated.with_usage(success, quality_score=quality)
            # 3. Probation check: 3+ scores averaging below 15
            scores = updated.recent_noncombat_scores
            if len(scores) >= 3:
                avg = sum(scores) / len(scores)
                if avg < 15 and updated.status == "active":
                    updated = updated.with_update(status="probation")
            self._skills[sid] = updated

    @contextmanager
    def temporary_override(self, skill_ids: list[str]):
        """Temporarily override which skills are returned by query() for replay."""
        original = self._active_override
        self._active_override = set(skill_ids)
        try:
            yield
        finally:
            self._active_override = original

    def set_active_override(self, skill_ids: list[str]) -> None:
        """Set persistent skill override for eval mode (survives across rounds)."""
        self._active_override = set(skill_ids)

    def clear_active_override(self) -> None:
        """Clear persistent skill override, restoring normal query behavior."""
        self._active_override = None

    def record_replay_outcome(self, skill_id: str, *, success: bool, quality: float):
        """Record outcome from replay evaluation (stronger signal).

        Replay outcomes count as 2 normal uses because the controlled
        A/B comparison provides a stronger causal signal than regular
        gameplay observation.
        """
        skill = self._skills.get(skill_id)
        if not skill:
            return
        # Replay outcomes count as 2 normal uses (stronger signal)
        updated = skill.with_usage(success=success)
        if not success:
            updated = updated.with_usage(success=False)  # double-count failures
        self._skills[skill_id] = updated

    def sweep_retirements(self) -> list[str]:
        """Deactivate low-confidence skills, delete long-deactivated ones.

        Lifecycle: active → probation (20-50% success) → deactivated (<20%)
        → deleted (after 3 consecutive deactivated runs).
        Seeds are NOT exempt from retirement.
        """
        removed: list[str] = []
        updates: dict[str, Skill] = {}
        deletes: list[str] = []

        for skill in self._skills.values():
            # FIRST: Delete long-deactivated skills (regardless of usage)
            if skill.status == "deactivated" and skill.deactivated_runs >= 3:
                deletes.append(skill.skill_id)
                removed.append(skill.skill_id)
                logger.info("Retiring skill %s (deactivated for %d runs)", skill.name, skill.deactivated_runs)
                continue

            # Exploration period: don't judge skills with <5 uses
            if skill.usage_count < 5:
                continue

            rate = skill.success_count / max(skill.usage_count, 1)

            if rate < 0.2 and skill.status == "active":
                updates[skill.skill_id] = skill.with_update(
                    status="deactivated", deactivated_runs=0,
                )
            elif 0.2 <= rate < 0.5 and skill.status == "active":
                updates[skill.skill_id] = skill.with_update(status="probation")

        # Apply updates (immutable: replace dict entries)
        self._skills.update(updates)

        for sid in deletes:
            del self._skills[sid]

        if updates:
            logger.info(
                "Retirement sweep: %d status changes, %d deleted",
                len(updates), len(deletes),
            )
        return removed

    def enforce_category_caps(self, max_per_category: int = 15) -> list[str]:
        """Deactivate lowest-confidence skills exceeding category cap.

        Only non-deactivated skills count toward the cap. When a category
        exceeds the cap, the lowest-confidence skills are deactivated first.
        """
        from collections import defaultdict

        by_cat: dict[str, list[Skill]] = defaultdict(list)
        for s in self._skills.values():
            if s.status != "deactivated":
                by_cat[s.category].append(s)

        deactivated: list[str] = []
        updates: dict[str, Skill] = {}

        for cat, skills in by_cat.items():
            if len(skills) <= max_per_category:
                continue
            # Sort by confidence ascending: lowest confidence gets deactivated first
            skills.sort(key=lambda s: s.confidence)
            excess = len(skills) - max_per_category
            for victim in skills[:excess]:
                updates[victim.skill_id] = victim.with_update(
                    status="deactivated", deactivated_runs=0,
                )
                deactivated.append(victim.skill_id)

        self._skills.update(updates)

        if deactivated:
            logger.info(
                "Category cap enforcement: %d skills deactivated",
                len(deactivated),
            )
        return deactivated

    def increment_deactivated_runs(self) -> None:
        """Increment deactivated_runs counter for all deactivated skills.

        Call this once per run so that sweep_retirements can track how
        long skills have been deactivated.
        """
        updates: dict[str, Skill] = {}
        for skill in self._skills.values():
            if skill.status == "deactivated":
                updates[skill.skill_id] = skill.with_update(
                    deactivated_runs=skill.deactivated_runs + 1,
                )
        self._skills.update(updates)

    def stats(self) -> dict[str, Any]:
        """Return library statistics."""
        categories: dict[str, int] = {}
        sources: dict[str, int] = {}
        for s in self._skills.values():
            if s.active:
                categories[s.category] = categories.get(s.category, 0) + 1
                sources[s.source] = sources.get(s.source, 0) + 1
        return {
            "total": self.count,
            "active": self.active_count,
            "categories": categories,
            "sources": sources,
        }

    # ── Persistence ──────────────────────────────────────────────

    def save(self, path: Path) -> None:
        """Save all skills to a JSON file, stamping provenance fields."""
        from dataclasses import replace
        try:
            rv = get_runtime_version()
            stamped = [
                replace(
                    s,
                    game_version=s.game_version or rv.game_version,
                    mod_version=s.mod_version or rv.mod_version,
                    data_schema_version=rv.data_schema_version,
                )
                for s in self._skills.values()
            ]
        except Exception:
            stamped = list(self._skills.values())
        data = [s.to_dict() for s in stamped]
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.debug("Saved %d skills to %s", len(data), path)

    @classmethod
    def load(cls, path: Path) -> SkillLibrary:
        """Load skills from a JSON file."""
        if not path.exists():
            logger.info("No skill file at %s, starting empty", path)
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            skills = tuple(Skill.from_dict(d) for d in data)
            lib = cls(skills)
            logger.info(
                "Loaded %d skills (%d active) from %s",
                lib.count, lib.active_count, path,
            )
            return lib
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to load skills from %s: %s", path, e)
            return cls()

    @classmethod
    def load_seeds(cls, seed_dir: Path) -> SkillLibrary:
        """Load seed skills from all JSON files in a directory."""
        lib = cls()
        if not seed_dir.exists():
            logger.info("No seed directory at %s", seed_dir)
            return lib

        for json_file in sorted(seed_dir.glob("*.json")):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Support both single skill and list of skills
                items = data if isinstance(data, list) else [data]
                loaded = 0
                for item in items:
                    # Skip non-skill entries (e.g. card_notes with
                    # card_name/seed_note format) that lack both name and content.
                    if not item.get("name") and not item.get("content"):
                        continue
                    skill = Skill.from_dict(item)
                    lib.add(skill)
                    loaded += 1
                logger.debug("Loaded %d seeds from %s", loaded, json_file.name)
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to load seed %s: %s", json_file, e)

        logger.info("Loaded %d seed skills from %s", lib.count, seed_dir)
        return lib

    def load_seed_stubs(self, stub_dir: Path, character: str) -> int:
        """Mode B: load character-parametric stub templates.

        Reads ``*.template.json`` from ``stub_dir``, substitutes the given
        character into each, and adds the resulting Skill to the library
        with ``status="pending_fill"``. Stubs already present (same skill_id)
        are skipped — this method is idempotent on repeat calls for the
        same character.

        Returns the count of newly-added stubs.

        Spec: docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md
        """
        from src.skills.stub_template import load_stub_templates, substitute_character

        templates = load_stub_templates(stub_dir)
        added = 0
        for tpl in templates:
            instance = substitute_character(tpl, character=character)
            if not instance.get("name") and not instance.get("content"):
                # Same defensive skip as load_seeds (non-skill JSON entries)
                continue
            skill = Skill.from_dict(instance)
            if skill.skill_id in self._skills:
                logger.debug("Stub %s already in library, skipping", skill.skill_id)
                continue
            self._skills[skill.skill_id] = skill
            added += 1
        if added:
            logger.info("Loaded %d seed stubs for character=%s", added, character)
        return added

    def merge_seeds(self, seed_lib: SkillLibrary) -> int:
        """Merge seed skills: add new ones, update content of changed ones.

        For NEW seeds (skill_id not in runtime): add directly.
        For EXISTING seeds: if content, lessons, examples, or name changed
        in the seed source, update those fields while preserving runtime
        stats (confidence, usage_count, success_count, verified, etc.).
        Returns count of newly added seeds (not counting updates).
        """
        added = 0
        # Seed-authoritative fields: updated from source when changed
        _SEED_FIELDS = ("content", "lessons", "examples", "name", "trigger", "priority")

        for skill in seed_lib.all_skills:
            if skill.skill_id not in self._skills:
                self._skills[skill.skill_id] = skill
                added += 1
            else:
                # Detect seed content changes → update runtime copy
                existing = self._skills[skill.skill_id]
                if existing.source != "seed":
                    continue  # Don't touch evolved skills
                changes: dict = {}
                for field in _SEED_FIELDS:
                    seed_val = getattr(skill, field, None)
                    runtime_val = getattr(existing, field, None)
                    if seed_val != runtime_val:
                        changes[field] = seed_val
                if changes:
                    updated = existing.with_update(**changes)
                    self._skills[skill.skill_id] = updated
                    logger.info(
                        "Seed '%s' updated: %s",
                        skill.name,
                        ", ".join(changes.keys()),
                    )
        return added
