"""Situation classification for combat rounds.

Computes hand capability tags from game state. All local computation —
zero API calls.

Threat-level / intent-class / deck-stage classification was removed
(2026-04-20, Task A5 of mistake-driven-skill-discovery plan) — cohort
discovery no longer needs per-round clustering and HandCapabilities alone
suffices for SkillTrigger.requires_hand_capabilities live matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ── HandCapabilityTag ────────────────────────────────────────

_WEAK_KW = re.compile(r"weak|虚弱", re.IGNORECASE)
_VULN_KW = re.compile(r"vulnerable|易伤", re.IGNORECASE)
_DRAW_KW = re.compile(r"\bdraw\b|抽|retain|保留", re.IGNORECASE)
_AOE_KW = re.compile(r"all enemies|所有敌人", re.IGNORECASE)


@dataclass(frozen=True)
class HandCapabilityTag:
    """Tactical capabilities of a hand — what can this hand DO.

    Spec: Section 4. Focused on capabilities (can_apply_weak, can_kill)
    rather than static counts. Counts kept for similarity scoring.
    """

    # Defensive capabilities
    can_apply_weak: bool = False
    can_apply_vulnerable: bool = False
    can_block_8_plus: bool = False
    can_block_full_incoming: bool = False

    # Offensive capabilities
    can_deal_12_plus: bool = False
    can_kill_this_turn: bool = False
    has_aoe: bool = False

    # Utility capabilities
    has_draw_or_retain: bool = False
    has_setup_only: bool = False

    # Energy profile
    zero_cost_count: int = 0
    total_playable: int = 0

    # Raw counts (for similarity scoring)
    attack_count: int = 0
    block_count: int = 0
    total_damage: int = 0
    total_block: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "can_apply_weak": self.can_apply_weak,
            "can_apply_vulnerable": self.can_apply_vulnerable,
            "can_block_8_plus": self.can_block_8_plus,
            "can_block_full_incoming": self.can_block_full_incoming,
            "can_deal_12_plus": self.can_deal_12_plus,
            "can_kill_this_turn": self.can_kill_this_turn,
            "has_aoe": self.has_aoe,
            "has_draw_or_retain": self.has_draw_or_retain,
            "has_setup_only": self.has_setup_only,
            "zero_cost_count": self.zero_cost_count,
            "total_playable": self.total_playable,
            "attack_count": self.attack_count,
            "block_count": self.block_count,
            "total_damage": self.total_damage,
            "total_block": self.total_block,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HandCapabilityTag:
        if not d:
            return cls()
        return cls(
            can_apply_weak=d.get("can_apply_weak", False),
            can_apply_vulnerable=d.get("can_apply_vulnerable", False),
            can_block_8_plus=d.get("can_block_8_plus", False),
            can_block_full_incoming=d.get("can_block_full_incoming", False),
            can_deal_12_plus=d.get("can_deal_12_plus", False),
            can_kill_this_turn=d.get("can_kill_this_turn", False),
            has_aoe=d.get("has_aoe", False),
            has_draw_or_retain=d.get("has_draw_or_retain", False),
            has_setup_only=d.get("has_setup_only", False),
            zero_cost_count=d.get("zero_cost_count", 0),
            total_playable=d.get("total_playable", 0),
            attack_count=d.get("attack_count", 0),
            block_count=d.get("block_count", 0),
            total_damage=d.get("total_damage", 0),
            total_block=d.get("total_block", 0),
        )


def _knapsack_max(items: list[tuple[int, int]], budget: int) -> int:
    """Exact 0/1 knapsack — maximum value within energy budget.

    Takes (cost, value) pairs. Uses DP when budget is small (typical STS
    energy 3-5) and item count is small (hand size 5-12).

    Complexity: O(n * budget) time and O(budget) space — negligible for
    STS parameters (n<=12, budget<=10).
    """
    if not items or budget < 0:
        return 0
    # Separate 0-cost items (always free to play) from costed items
    free_total = sum(v for c, v in items if c == 0)
    costed = [(c, v) for c, v in items if c > 0]
    if not costed:
        return free_total
    # dp[j] = max value achievable spending exactly j energy on costed cards
    dp = [0] * (budget + 1)
    for cost, value in costed:
        if cost > budget:
            continue
        # Traverse budget in reverse to avoid reusing the same item
        for j in range(budget, cost - 1, -1):
            dp[j] = max(dp[j], dp[j - cost] + value)
    return max(dp) + free_total


def compute_hand_capabilities(
    hand: list,
    total_incoming: int,
    enemy_hp_lowest: int,
    energy: int,
) -> HandCapabilityTag:
    """Compute tactical capability tag from hand cards.

    Accepts either RawCombatHandCardPayload objects or dicts with the
    same field names (for testing). Zero API calls.
    """
    def _get(card, attr, default=None):
        if isinstance(card, dict):
            return card.get(attr, default)
        return getattr(card, attr, default)

    total_damage = 0
    total_block = 0
    attack_count = 0
    block_count = 0
    can_weak = False
    can_vuln = False
    has_draw = False
    has_aoe = False
    zero_cost = 0
    playable_count = 0

    for c in hand:
        dmg = _get(c, "damage")
        blk = _get(c, "block")
        rules = _get(c, "rules_text", "") or ""
        cost = _get(c, "energy_cost", 1) or 0
        is_playable = _get(c, "playable", True)
        hits = _get(c, "hits")

        if dmg is not None:
            h = hits if (hits is not None and hits > 1) else 1
            total_damage += dmg * h
            attack_count += 1
        if blk is not None:
            total_block += blk
            block_count += 1

        if _WEAK_KW.search(rules):
            can_weak = True
        if _VULN_KW.search(rules):
            can_vuln = True
        if _DRAW_KW.search(rules):
            has_draw = True
        if _AOE_KW.search(rules):
            has_aoe = True

        if cost == 0:
            zero_cost += 1
        if is_playable and cost <= energy:
            playable_count += 1

    setup_only = attack_count == 0 and block_count == 0 and len(hand) > 0

    # Energy-feasible capability estimation.
    # can_kill and can_block ask "does any energy-feasible subset achieve the
    # target?" — these are independent 0/1 knapsack problems (damage vs block),
    # so we run separate exact DP passes via _knapsack_max().
    damage_items: list[tuple[int, int]] = []
    block_items: list[tuple[int, int]] = []
    for c in hand:
        c_cost = _get(c, "energy_cost", 1) or 0
        if c_cost > energy or not _get(c, "playable", True):
            continue
        c_dmg = _get(c, "damage")
        if c_dmg is not None:
            c_hits = _get(c, "hits")
            h = c_hits if (c_hits is not None and c_hits > 1) else 1
            damage_items.append((c_cost, c_dmg * h))
        c_blk = _get(c, "block")
        if c_blk is not None and c_blk > 0:
            block_items.append((c_cost, c_blk))

    feasible_damage = _knapsack_max(damage_items, energy)
    feasible_block = _knapsack_max(block_items, energy)

    return HandCapabilityTag(
        can_apply_weak=can_weak,
        can_apply_vulnerable=can_vuln,
        can_block_8_plus=feasible_block >= 8,
        can_block_full_incoming=feasible_block >= total_incoming,
        can_deal_12_plus=feasible_damage >= 12,
        can_kill_this_turn=(feasible_damage >= enemy_hp_lowest > 0),
        has_aoe=has_aoe,
        has_draw_or_retain=has_draw,
        has_setup_only=setup_only,
        zero_cost_count=zero_cost,
        total_playable=playable_count,
        attack_count=attack_count,
        block_count=block_count,
        total_damage=total_damage,     # raw total (for reference)
        total_block=total_block,       # raw total (for reference)
    )


# ── SituationTag ─────────────────────────────────────────────


@dataclass(frozen=True)
class SituationTag:
    """Per-round situation tag for memory retrieval.

    Trimmed (2026-04-20) to ``hand_capabilities`` + outcome fields.
    Legacy threat_level/intent_class/threat_window/deck_stage/next_round_window/
    cards_that_helped fields were removed along with cohort discovery.
    ``tag_source`` is retained as provenance signal for evidence scoring in
    skills/evidence.py (slated for removal in Phase H).
    """

    hand_capabilities: HandCapabilityTag | None = None
    damage_taken: int = 0
    outcome_quality: str = ""
    # Provenance: "runtime" (predictive, computed at round start) vs
    # "backfill" (retrospective, computed from actual damage_taken after the
    # fact). Consumed by skills/evidence.py provenance weighting.
    tag_source: str = ""  # "runtime" | "backfill" | "" (unknown/legacy)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.hand_capabilities is not None:
            d["hand_capabilities"] = self.hand_capabilities.to_dict()
        if self.damage_taken:
            d["damage_taken"] = self.damage_taken
        if self.outcome_quality:
            d["outcome_quality"] = self.outcome_quality
        if self.tag_source:
            d["tag_source"] = self.tag_source
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SituationTag:
        """Rehydrate from dict. Tolerates legacy dicts with removed keys."""
        if not d:
            return cls()
        hc_raw = d.get("hand_capabilities")
        return cls(
            hand_capabilities=HandCapabilityTag.from_dict(hc_raw) if hc_raw else None,
            damage_taken=d.get("damage_taken", 0),
            outcome_quality=d.get("outcome_quality", ""),
            tag_source=d.get("tag_source", ""),
        )


# ── Enemy Behavior Summary ───────────────────────────────────


def format_enemy_behavior_summary(
    mechanic_summary: tuple[str, ...] | list[str],
    *,
    max_points: int = 2,
) -> str:
    """Format concise fight-mechanic takeaways for prompt injection."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for pattern in mechanic_summary:
        text = " ".join((pattern or "").strip().split())
        if not text:
            continue
        if text.startswith("- "):
            text = text[2:].strip()
        normalized = text.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(text)

    if not cleaned:
        return ""

    lines = ["### Past Experience"]
    for pattern in cleaned[:max_points]:
        lines.append(f"- {pattern}")
    return "\n".join(lines)
