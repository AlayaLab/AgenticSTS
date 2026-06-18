"""Skill data models: frozen dataclasses for the procedural knowledge system.

A Skill is a structured unit of game knowledge that can be:
- Triggered by specific game contexts (state type, enemy, HP, act)
- Retrieved and composed into LLM prompts
- Tracked for effectiveness and evolved over time
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.memory.situation import SituationTag


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ── State type normalization ─────────────────────────────────────
# LLM-authored skills use semantic labels like "combat" or "rest",
# but gameplay queries use the actual state_type values from the MCP API.
# This mapping ensures evolved/discovered skills match at retrieval time.

_STATE_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "combat": ("monster", "elite", "boss"),
    "combat_plan": ("monster", "elite", "boss"),
    "rest": ("rest_site",),
    "combat_reward": ("card_reward",),
    "combat_rewards": ("card_reward",),
    "deck_building": ("card_reward", "card_select", "shop"),
}

# Canonical gameplay state_types (pass through unchanged)
_CANONICAL_STATES: frozenset[str] = frozenset({
    "monster", "elite", "boss", "map", "rest_site", "event",
    "shop", "card_reward", "card_select", "hand_select", "treasure",
    "relic_select",
})


def normalize_state_types(raw: frozenset[str] | list | tuple) -> frozenset[str]:
    """Map semantic state labels to canonical gameplay state_types.

    "combat" → {"monster", "elite", "boss"}
    "rest" → {"rest_site"}
    "monster" → {"monster"} (pass through)
    """
    result: set[str] = set()
    for s in raw:
        s_lower = s.lower().strip()
        if s_lower in _STATE_TYPE_ALIASES:
            result.update(_STATE_TYPE_ALIASES[s_lower])
        elif s_lower in _CANONICAL_STATES:
            result.add(s_lower)
        # else: drop unknown state types silently
    return frozenset(result)


def _now() -> float:
    return time.time()


@dataclass(frozen=True)
class AnchorExemplar:
    """Anchor back to the original gameplay prompt that proved this skill valuable.

    ``llm_call_seq`` indexes ``logs/run_<run_id>.jsonl`` llm_call events (zero-based
    across all llm_call events), matching the neighbor-landed ``CombatRound.llm_call_seq``
    convention. Used by merge AB validation to replay the original decision with the
    merged skill injected.
    """

    run_id: str
    llm_call_seq: int
    expected_correction: str
    counterfactual_note: str = ""
    episode_id: str = ""
    round_num: int = 0


@dataclass(frozen=True)
class SkillTrigger:
    """Defines when a skill should be activated.

    All conditions are AND-joined. Empty/default values mean "match all".
    """

    # Which state types activate this skill (empty = all)
    state_types: frozenset[str] = frozenset()

    # Specific enemy names (empty = all enemies)
    enemy_names: frozenset[str] = frozenset()

    # Act range: only activate in these acts (inclusive)
    min_act: int = 0
    max_act: int = 99

    # HP ratio threshold: activate when HP ratio is below this (1.0 = always)
    hp_below: float = 1.0

    # HP ratio threshold: activate when HP ratio is above this (0.0 = always)
    hp_above: float = 0.0

    # Minimum deck size to activate (0 = no minimum)
    min_deck_size: int = 0

    # Maximum deck size to activate (999 = no maximum)
    max_deck_size: int = 999

    # Card names that must be present in hand/deck for skill to activate
    requires_cards: frozenset[str] = frozenset()

    # Hard character filter: skill only fires for these characters (empty = all characters).
    # Use normalized short names: "ironclad", "silent", "regent", "necrobinder", "defect".
    character: frozenset[str] = frozenset()

    any_of_relics: frozenset[str] = frozenset()     # hard filter: at least ONE must be present
    requires_hand_capabilities: frozenset[str] = frozenset()  # hard filter: at least ONE must be true
    requires_enemy_powers: frozenset[str] = frozenset()  # hard filter: at least ONE enemy must have this power (lowercase, matched via context_tags "enemy_power:<name>")

    def matches(
        self,
        state_type: str = "",
        enemy_name: str = "",
        act: int = 1,
        hp_ratio: float = 1.0,
        deck_size: int = 0,
        hand_cards: frozenset[str] = frozenset(),
        context_tags: frozenset[str] = frozenset(),
        *,
        situation: SituationTag | None = None,
    ) -> tuple[bool, float]:
        """Check if this trigger matches the given context.

        Returns (matches: bool, relevance_score: float).
        Higher relevance = more specific match.
        """
        score = 0.0

        # State type check
        if self.state_types:
            if state_type not in self.state_types:
                return False, 0.0
            score += 1.0

        # Character check (hard filter): context_tags already contains normalized character name
        if self.character:
            if not (self.character & context_tags):
                return False, 0.0
            score += 0.5

        # Enemy check — supports prefix match so "Test Subject" matches "Test Subject #C22"
        if self.enemy_names:
            actual = enemy_name.upper() if enemy_name else ""
            matched = any(
                actual == n.upper() or actual.startswith(n.upper() + " ") or actual.startswith(n.upper() + "#")
                for n in self.enemy_names
            )
            if matched:
                score += 2.0  # Enemy-specific skills are highly relevant
            else:
                return False, 0.0

        # Act range check
        if not (self.min_act <= act <= self.max_act):
            return False, 0.0
        if self.min_act > 0 or self.max_act < 99:
            score += 0.5

        # HP ratio check
        if hp_ratio > self.hp_below:
            return False, 0.0
        if hp_ratio < self.hp_above:
            return False, 0.0
        if self.hp_below < 1.0 or self.hp_above > 0.0:
            score += 0.5

        # Deck size check
        if not (self.min_deck_size <= deck_size <= self.max_deck_size):
            return False, 0.0

        # Card requirement check (overlap-weighted, diminishing returns)
        if self.requires_cards:
            overlap = self.requires_cards.intersection(hand_cards)
            if not overlap:
                return False, 0.0
            score += 1.5 + 0.5 * (len(overlap) - 1)

        # Situation-level matching: hand-capability hard filter
        if situation is not None:
            if self.requires_hand_capabilities and situation.hand_capabilities:
                hc = situation.hand_capabilities
                has_any = any(getattr(hc, cap, False) for cap in self.requires_hand_capabilities)
                if not has_any:
                    return False, 0.0
                score += 1.0

        # Relic matching: any_of_relics uses context_tags (relics passed via tags)
        if self.any_of_relics:
            relic_overlap = self.any_of_relics & context_tags
            if not relic_overlap:
                return False, 0.0
            score += 0.3 * len(relic_overlap)

        # Enemy power matching: requires at least one enemy to have this power
        # Powers are passed via context_tags as "enemy_power:<name>" (lowercase)
        if self.requires_enemy_powers:
            power_tags = {t for t in context_tags if t.startswith("enemy_power:")}
            active_powers = {t.removeprefix("enemy_power:") for t in power_tags}
            if not (self.requires_enemy_powers & active_powers):
                return False, 0.0
            score += 2.0

        return True, max(score, 0.1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "state_types": sorted(self.state_types),
            "enemy_names": sorted(self.enemy_names),
            "min_act": self.min_act,
            "max_act": self.max_act,
            "hp_below": self.hp_below,
            "hp_above": self.hp_above,
            "min_deck_size": self.min_deck_size,
            "max_deck_size": self.max_deck_size,
            "requires_cards": sorted(self.requires_cards),
            "character": sorted(self.character),
            "any_of_relics": sorted(self.any_of_relics),
            "requires_hand_capabilities": sorted(self.requires_hand_capabilities),
            "requires_enemy_powers": sorted(self.requires_enemy_powers),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkillTrigger:
        return cls(
            state_types=normalize_state_types(d.get("state_types", ())),
            enemy_names=frozenset(d.get("enemy_names", ())),
            min_act=d.get("min_act", 0),
            max_act=d.get("max_act", 99),
            hp_below=d.get("hp_below", 1.0),
            hp_above=d.get("hp_above", 0.0),
            min_deck_size=d.get("min_deck_size", 0),
            max_deck_size=d.get("max_deck_size", 999),
            requires_cards=frozenset(d.get("requires_cards", ())),
            character=frozenset(d.get("character", ())),
            any_of_relics=frozenset(d.get("any_of_relics", ())),
            requires_hand_capabilities=frozenset(d.get("requires_hand_capabilities", ())),
            requires_enemy_powers=frozenset(d.get("requires_enemy_powers", ())),
        )


@dataclass(frozen=True)
class Skill:
    """A procedural knowledge module for game decisions.

    Content is natural language text that gets injected into LLM prompts
    when the trigger conditions match the current game state.

    Design informed by:
    - SkillRL (hierarchical SkillBank: general vs specific tiers)
    - SoK Agentic Skills (7-stage lifecycle, quality control gates)
    - Voyager (self-verification before promoting skills)
    - BUSE (bottom-up skill evolution tested on STS)
    """

    skill_id: str = field(default_factory=_new_id)
    name: str = ""
    category: str = "general"  # combat | deck_building | map | event | rest | boss | general
    trigger: SkillTrigger = field(default_factory=SkillTrigger)

    # Anchor back-references to original gameplay prompts that proved this skill valuable.
    # Used by merge AB validation to replay the original decision with merged content injected.
    anchor_exemplars: tuple[AnchorExemplar, ...] = ()

    # Hierarchy tier (SkillRL pattern)
    # "general": universal guidance, always considered (e.g. energy management)
    # "specific": situation-targeted, only when trigger matches (e.g. Kin Priest strategy)
    tier: str = "specific"  # general | specific

    # The core procedural knowledge (injected into prompts)
    content: str = ""

    # Failure lessons: what goes wrong when this skill is NOT followed
    # (SkillRL pattern: experience-based distillation captures both success and failure)
    lessons: str = ""

    # Concrete examples of applying this skill
    examples: tuple[str, ...] = ()

    # Priority: higher = injected first (same category)
    priority: int = 50

    # Provenance
    source: str = "seed"  # seed | discovered | refined | merged
    source_run_ids: tuple[str, ...] = ()
    created_at: float = field(default_factory=_now)
    version: int = 1  # Incremented on refinement

    # Effectiveness tracking
    confidence: float = 0.7  # 0-1, seed skills start at 0.7
    usage_count: int = 0
    success_count: int = 0  # Positive outcome after skill was active
    failure_count: int = 0  # Negative outcome after skill was active

    # Verification gate (SoK/Voyager pattern)
    # Discovered skills start unverified (probation).
    # After MIN_VERIFICATION_USES, if success_rate > 0.5, skill graduates to verified.
    # Unverified skills get lower injection priority.
    verified: bool = True  # Seed skills are pre-verified

    # Lifecycle
    status: str = "active"  # "active" | "probation" | "deactivated"
    supplements_seed_id: str = ""  # seed skill this supplements (if any)
    deactivated_runs: int = 0  # consecutive runs while deactivated
    # Per-run tracking: how many consecutive runs this skill has been injected
    # in WITHOUT producing an 'improved' outcome in any of the combats that run.
    # Resets to 0 when any injected combat that run hits 'improved'.
    # Reaches 3 -> retirement per spec §6.2 (seed skills exempt).
    consecutive_unimproved_runs: int = 0
    active: bool = True
    superseded_by: str = ""  # skill_id that replaced this one

    # Non-combat scoring: recent composite scores at boss fight entry (last 3)
    recent_noncombat_scores: tuple[float, ...] = ()

    # Provenance: version metadata stamped at persist time
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 3

    # Mode B (seed stub self-evolution): metadata for stub templates.
    # Empty for non-stub skills. Fields: topic, scope, dimensions_to_consider,
    # out_of_scope, format_constraints, leakage_guard.
    # When status == "pending_fill", content is "TBD" and the skill is excluded
    # from retrieval. After fill, source becomes "stub_filled" and status "active".
    # See docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md.
    scaffold: dict = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        """Success rate among tracked outcomes."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5  # Unknown
        return self.success_count / total

    @property
    def effective_priority(self) -> float:
        """Priority weighted by confidence and usage evidence.

        Scoring philosophy: fully automatic lifecycle — no human verification
        gate. Skills earn authority through gameplay data alone.

        Components:
        - base = priority × confidence
        - usage bonus: up to +20 for skills with positive outcomes
        """
        base = self.priority * self.confidence

        # Usage-based bonus: reward skills that have been tried and succeeded.
        if self.usage_count > 0:
            base += min(self.usage_count, 10) * 2.0 * self.confidence

        return base

    def with_update(
        self,
        anchor_exemplars: tuple[AnchorExemplar, ...] | None = None,
        **kwargs: Any,
    ) -> Skill:
        """Return a new Skill with specified fields replaced (immutable update).

        ``anchor_exemplars`` uses a None-sentinel: pass None (or omit) to preserve
        existing anchors; pass an explicit tuple (including empty tuple ``()``) to
        replace them. This differs from other kwargs, which always overwrite when
        provided.
        """
        from dataclasses import fields as dc_fields

        current = {f.name: getattr(self, f.name) for f in dc_fields(self)}
        current["anchor_exemplars"] = (
            self.anchor_exemplars if anchor_exemplars is None else anchor_exemplars
        )
        current.update(kwargs)
        return Skill(**current)

    def with_noncombat_score(self, score: float) -> Skill:
        """Return a new Skill with a noncombat score appended (keep last 3)."""
        scores = self.recent_noncombat_scores + (score,)
        # Keep only the last 3 scores
        if len(scores) > 3:
            scores = scores[-3:]
        return self.with_update(recent_noncombat_scores=scores)

    def with_usage(self, success: bool, quality_score: float = 1.0) -> Skill:
        """Return a new skill with updated usage tracking and verification.

        Handles:
        - Usage counting
        - Confidence updating (Laplace-smoothed, quality-weighted)
        - Verification graduation (probation → verified after enough successes)
        - Auto-deactivation (too many failures)

        Args:
            success: Whether the decision led to a positive outcome.
            quality_score: 0.0-1.0 quality metric. Higher values give
                the observation more weight in the confidence blend.
                Default 1.0 preserves backward compatibility.
        """
        new_usage = self.usage_count + 1
        new_success = self.success_count + (1 if success else 0)
        new_failure = self.failure_count + (0 if success else 1)

        # Update confidence using Laplace-smoothed success rate
        total_tracked = new_success + new_failure
        if total_tracked >= 3:
            # Blend seed confidence with observed success rate
            observed = (new_success + 1) / (total_tracked + 2)
            # Weighted blend: more data → more weight on observed
            # quality_score scales the weight: high quality = full weight,
            # low quality = barely registers (min 0.1 to avoid zero-weight)
            weight = min(total_tracked / 10.0, 1.0) * max(0.1, quality_score)
            new_confidence = (1 - weight) * self.confidence + weight * observed
        else:
            new_confidence = self.confidence

        # verified field retained for backward compat but no longer gates scoring
        new_verified = self.verified

        # Auto-deactivate if consistently failing (SoK recommendation)
        new_active = self.active
        if total_tracked >= 5 and new_confidence < 0.15:
            new_active = False

        return Skill(
            skill_id=self.skill_id,
            name=self.name,
            category=self.category,
            trigger=self.trigger,
            anchor_exemplars=self.anchor_exemplars,
            tier=self.tier,
            content=self.content,
            lessons=self.lessons,
            examples=self.examples,
            priority=self.priority,
            source=self.source,
            source_run_ids=self.source_run_ids,
            created_at=self.created_at,
            version=self.version,
            confidence=new_confidence,
            usage_count=new_usage,
            success_count=new_success,
            failure_count=new_failure,
            verified=new_verified,
            status=self.status,
            supplements_seed_id=self.supplements_seed_id,
            deactivated_runs=self.deactivated_runs,
            consecutive_unimproved_runs=self.consecutive_unimproved_runs,
            active=new_active,
            superseded_by=self.superseded_by,
            recent_noncombat_scores=self.recent_noncombat_scores,
            game_version=self.game_version,
            mod_version=self.mod_version,
            data_schema_version=self.data_schema_version,
            scaffold=self.scaffold,
        )

    def with_deactivation(self, superseded_by: str = "") -> Skill:
        """Return a deactivated copy of this skill."""
        return Skill(
            skill_id=self.skill_id,
            name=self.name,
            category=self.category,
            trigger=self.trigger,
            anchor_exemplars=self.anchor_exemplars,
            tier=self.tier,
            content=self.content,
            lessons=self.lessons,
            examples=self.examples,
            priority=self.priority,
            source=self.source,
            source_run_ids=self.source_run_ids,
            created_at=self.created_at,
            version=self.version,
            confidence=self.confidence,
            usage_count=self.usage_count,
            success_count=self.success_count,
            failure_count=self.failure_count,
            verified=self.verified,
            status="deactivated",
            supplements_seed_id=self.supplements_seed_id,
            deactivated_runs=self.deactivated_runs,
            consecutive_unimproved_runs=self.consecutive_unimproved_runs,
            active=False,
            superseded_by=superseded_by,
            recent_noncombat_scores=self.recent_noncombat_scores,
            game_version=self.game_version,
            mod_version=self.mod_version,
            data_schema_version=self.data_schema_version,
            scaffold=self.scaffold,
        )

    def to_dict(self) -> dict[str, Any]:
        blob: dict[str, Any] = {
            "skill_id": self.skill_id,
            "name": self.name,
            "category": self.category,
            "trigger": self.trigger.to_dict(),
            "tier": self.tier,
            "content": self.content,
            "lessons": self.lessons,
            "examples": list(self.examples),
            "priority": self.priority,
            "source": self.source,
            "source_run_ids": list(self.source_run_ids),
            "created_at": self.created_at,
            "version": self.version,
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "verified": self.verified,
            "status": self.status,
            "supplements_seed_id": self.supplements_seed_id,
            "deactivated_runs": self.deactivated_runs,
            "active": self.active,
            "superseded_by": self.superseded_by,
            "recent_noncombat_scores": list(self.recent_noncombat_scores),
            **({"consecutive_unimproved_runs": self.consecutive_unimproved_runs}
               if self.consecutive_unimproved_runs else {}),
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
            **({"scaffold": self.scaffold} if self.scaffold else {}),
        }
        blob["anchor_exemplars"] = [
            {
                "run_id": a.run_id,
                "llm_call_seq": a.llm_call_seq,
                "expected_correction": a.expected_correction,
                "counterfactual_note": a.counterfactual_note,
                "episode_id": a.episode_id,
                "round_num": a.round_num,
            }
            for a in self.anchor_exemplars
        ]
        return blob

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Skill:
        trigger_data = d.get("trigger", {})
        trigger = SkillTrigger.from_dict(trigger_data) if trigger_data else SkillTrigger()
        raw_anchors = d.get("anchor_exemplars") or ()
        anchors = tuple(
            AnchorExemplar(
                run_id=a.get("run_id", ""),
                llm_call_seq=int(a.get("llm_call_seq", 0)),
                expected_correction=a.get("expected_correction", ""),
                counterfactual_note=a.get("counterfactual_note", ""),
                episode_id=a.get("episode_id", ""),
                round_num=int(a.get("round_num", 0)),
            )
            for a in raw_anchors
        )
        return cls(
            skill_id=d.get("skill_id", _new_id()),
            name=d.get("name", ""),
            category=d.get("category", "general"),
            trigger=trigger,
            anchor_exemplars=anchors,
            tier=d.get("tier", "specific"),
            content=d.get("content", ""),
            lessons=d.get("lessons", ""),
            examples=tuple(d.get("examples", ())),
            priority=d.get("priority", 50),
            source=d.get("source", "seed"),
            source_run_ids=tuple(d.get("source_run_ids", ())),
            created_at=d.get("created_at", _now()),
            version=d.get("version", 1),
            confidence=d.get("confidence", 0.7),
            usage_count=d.get("usage_count", 0),
            success_count=d.get("success_count", 0),
            failure_count=d.get("failure_count", 0),
            verified=d.get("verified", True),
            status=d.get("status", "active"),
            supplements_seed_id=d.get("supplements_seed_id", ""),
            deactivated_runs=d.get("deactivated_runs", 0),
            consecutive_unimproved_runs=d.get("consecutive_unimproved_runs", 0),
            active=d.get("active", True),
            superseded_by=d.get("superseded_by", ""),
            recent_noncombat_scores=tuple(
                float(x) for x in d.get("recent_noncombat_scores", ())
            ),
            game_version=d.get("game_version", None),
            mod_version=d.get("mod_version", None),
            data_schema_version=d.get("data_schema_version", 2),
            scaffold=dict(d.get("scaffold", {})),
        )
