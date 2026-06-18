# Situation-Level Retrieval Design

**Date**: 2026-03-31
**Status**: Draft
**Goal**: Reduce prompt noise by matching memory/skills to specific combat situations, not just enemy-level categories.

---

## 1. Problem Statement

The current retrieval system matches at coarse granularity:

| Module | Current Match Key | What Gets Injected |
|--------|------------------|--------------------|
| Memory (retriever.py) | `enemy_key x character x combat_type` | Whole-fight guide + full R1-R8 intent dump |
| Skills (library.py) | `state_type + enemy_name + hp_ratio` | All combat-category skills that trigger-match |
| Tools (tool_preprocessor.py) | `APPLICABLE_STATES = ["monster"]` | All tools matching state type |
| Conversation (conversation.py) | Round number (keep_recent=1) | No situation awareness in what's injected |

### Concrete Symptoms

1. **Guide over-generalization**: `guide_consolidator.py` produces one guide per `(enemy_key, character)`. "Lead with Bash to apply Vulnerable early" is useless at R5 when Bash is in discard pile and incoming damage is 18.

2. **Pattern noise**: `format_enemy_patterns()` dumps full R1-R8 sequences from 3 past episodes at every round. At R5, R1-R3 data is noise. At R1, R6-R8 future data is speculative.

3. **No hand-situation awareness**: A hand with `[Weak, Defend, Defend+, Strike, Neutralize]` vs `[Strike, Strike, Strike, Dagger Spray, Backstab]` demands completely different tactical advice, but the system can't distinguish them.

4. **No threat calibration**: R3 with 18 incoming damage and R3 with 6 incoming damage get identical memory/skill injection.

5. **Premature consolidation trap**: The current whole-fight guides (`retriever.py:157`, `prompt_injector.py:27`) bake aggregated card-frequency data into fixed advice. This is the root cause of many bad guides — sparse, biased data gets crystallized into authoritative-looking text.

### Example: Fuzzy Wurm Crawler at R3

**Current system injects:**
- Whole-fight guide: "Lead with Bash, Pommel Strike is MVP, block is unnecessary"
- Full R1-R8 intent pattern from 3 episodes
- 2 generic combat rules
- 3 combat skills (energy management, sequencing, generic defense)

**What it should inject:**
- "R3: Attack 9x2=18 incoming. SURVIVAL PRIORITY. Apply Weak if available, then maximize block."
- "Past similar rounds: In 2/3 episodes, R3 was high-damage; hands with Weak+Block survived with <5 HP loss. Hands without Weak lost 12+ HP."
- "After R3: R4 was Buff in 2/3 episodes (67% confidence) — potential recovery window."
- Skills: only those matching `threat_level=high + intent_class=attack + can_apply_weak`

---

## 2. Design Goals

1. **Situation-level retrieval** — match memory/skills to `(enemy x threat_level x intent_class x hand_capabilities)`, not just `(enemy x character)`
2. **Capability-based hand abstraction** — encode "what can this hand DO" (can_block_full, can_apply_weak, can_kill), not just static counts
3. **Confidence-gated upcoming windows** — only inject "next round is low-pressure" when pattern consistency exceeds threshold
4. **Progressive injection** — R1 gets strategic overview; R2+ gets tactical situation hints; high-threat rounds get survival-only content
5. **Observation-first, consolidation-later** — validate round-level retrieval improves decisions BEFORE baking into guides
6. **Backward compatible** — extend existing models with optional fields; old data degrades gracefully (missing tags = "unknown", skipped in ranking)
7. **Zero additional API calls** — all new computation is local

---

## 3. New Feature Dimensions

### 3.1 Dimension Table

| Dimension | Type | Filter Level | Computed From |
|-----------|------|-------------|---------------|
| `enemy_key` | `str` | **Hard filter** (must match) | Existing field |
| `character` | `str` | **Hard filter** (must match) | Existing field |
| `threat_level` | `"lethal"\|"high"\|"medium"\|"low"` | **Strong ranking** (+2.0) | `compute_total_incoming()` vs HP/block |
| `intent_class` | `"attack"\|"buff"\|"debuff"\|"mixed"\|"unknown"` | **Strong ranking** (+1.5) | Parsed from intent strings |
| `hand_capabilities` | `HandCapabilityTag` | **Strong ranking** (per-capability +1.0) | Real-time from hand cards |
| `threat_window` | `"setup"\|"burst"\|"recovery"\|"lethal"` | **Weak ranking** (+0.5) | Derived from enemy behavior pattern |
| `deck_stage` | `"starter"\|"building"\|"scaling"\|"mature"` | **Weak ranking** (+0.5) | Floor band + deck size + card quality signals |
| `key_relics` | `frozenset[str]` | **Weak ranking** (+0.3 per match) | From relic list (any-of semantics) |

### 3.2 Two-Tier Retrieval Pipeline

```
Step 1: Hard Filter
  → enemy_key == current_enemy
  → character == current_character
  → yields candidate round pool

Step 2: Strong Ranking (situation match)
  → threat_level match:  +2.0 if same, +0.5 if adjacent (high↔lethal, medium↔high)
  → intent_class match:  +1.5 if same
  → hand capability overlap: +1.0 per matching boolean capability
  → can_full_block match: +1.5 (critical for survival decisions)
  → can_kill match: +2.0 (critical for lethal detection)

Step 3: Weak Ranking (context match)
  → threat_window match: +0.5
  → deck_stage match: +0.5
  → relic overlap: +0.3 per matching relic (any-of)

Step 4: Select top 3 rounds, deduplicate by (intent_class, threat_level, top-3-cards)
```

---

## 4. HandCapabilityTag

Encodes "what can this hand DO" — tactical capabilities, not static counts.

```python
@dataclass(frozen=True)
class HandCapabilityTag:
    # Defensive capabilities
    can_apply_weak: bool = False          # any card applies Weak to enemy
    can_apply_vulnerable: bool = False    # any card applies Vulnerable
    can_block_8_plus: bool = False        # total block in hand >= 8
    can_block_full_incoming: bool = False # total block >= total incoming damage

    # Offensive capabilities
    can_deal_12_plus: bool = False        # total attack damage >= 12
    can_kill_this_turn: bool = False      # total damage >= lowest enemy HP
    has_aoe: bool = False                 # any card hits all enemies

    # Utility capabilities
    has_draw_or_retain: bool = False      # any card draws or retains cards
    has_setup_only: bool = False          # hand is all powers/setup with no immediate impact

    # Energy profile
    zero_cost_count: int = 0             # how many 0-cost cards
    total_playable: int = 0             # cards playable within current energy

    # Raw counts (for similarity scoring, not primary matching)
    attack_count: int = 0
    block_count: int = 0
    total_damage: int = 0
    total_block: int = 0
```

### Computation

All fields computed from `RawCombatHandCardPayload` fields + current game state:

```python
def compute_hand_capabilities(
    hand: list[RawCombatHandCardPayload],
    total_incoming: int,
    enemy_hp_lowest: int,
    energy: int,
) -> HandCapabilityTag:
    total_damage = sum(c.damage * _effective_hits(c) for c in hand if c.damage)
    total_block = sum(c.block for c in hand if c.block)

    # Weak/Vulnerable detection from rules_text keywords
    weak_keywords = {"weak", "虚弱", "apply weak"}
    vuln_keywords = {"vulnerable", "易伤", "apply vulnerable"}
    draw_keywords = {"draw", "抽", "retain", "保留"}
    aoe_keywords = {"all enemies", "所有敌人"}

    can_weak = any(any(kw in (c.rules_text or "").lower() for kw in weak_keywords) for c in hand)
    can_vuln = any(any(kw in (c.rules_text or "").lower() for kw in vuln_keywords) for c in hand)
    has_draw = any(any(kw in (c.rules_text or "").lower() for kw in draw_keywords) for c in hand)
    has_aoe = any(any(kw in (c.rules_text or "").lower() for kw in aoe_keywords) for c in hand)

    # Setup-only: no attacks AND no block cards
    attack_cards = [c for c in hand if c.damage is not None]
    block_cards = [c for c in hand if c.block is not None]
    setup_only = len(attack_cards) == 0 and len(block_cards) == 0

    playable = sum(1 for c in hand if c.energy_cost <= energy and c.playable)

    return HandCapabilityTag(
        can_apply_weak=can_weak,
        can_apply_vulnerable=can_vuln,
        can_block_8_plus=total_block >= 8,
        can_block_full_incoming=total_block >= total_incoming,
        can_deal_12_plus=total_damage >= 12,
        can_kill_this_turn=total_damage >= enemy_hp_lowest and enemy_hp_lowest > 0,
        has_aoe=has_aoe,
        has_draw_or_retain=has_draw,
        has_setup_only=setup_only,
        zero_cost_count=sum(1 for c in hand if c.energy_cost == 0),
        total_playable=playable,
        attack_count=len(attack_cards),
        block_count=len(block_cards),
        total_damage=total_damage,
        total_block=total_block,
    )
```

### Capability Similarity

```python
_CAPABILITY_WEIGHTS = {
    "can_apply_weak": 1.5,
    "can_apply_vulnerable": 1.0,
    "can_block_full_incoming": 2.0,  # critical for survival decisions
    "can_block_8_plus": 1.0,
    "can_deal_12_plus": 1.0,
    "can_kill_this_turn": 2.5,       # highest weight: changes entire decision
    "has_aoe": 1.0,
    "has_draw_or_retain": 0.5,
    "has_setup_only": 1.5,           # important: signals "can't do anything this turn"
}

def hand_capability_similarity(a: HandCapabilityTag, b: HandCapabilityTag) -> float:
    """Weighted overlap of boolean capabilities. Range: 0.0 - ~12.0."""
    score = 0.0
    for field, weight in _CAPABILITY_WEIGHTS.items():
        if getattr(a, field) == getattr(b, field):
            score += weight
    return score
```

---

## 5. Threat Classification

### 5.1 Threat Level (per-round)

```python
def classify_threat(
    total_incoming: int,
    current_hp: int,
    current_block: int,
) -> str:
    effective_damage = max(0, total_incoming - current_block)
    hp_ratio = effective_damage / max(current_hp, 1)

    if hp_ratio >= 0.5:       # would lose 50%+ HP
        return "lethal"
    if effective_damage >= 15:
        return "high"
    if effective_damage >= 8:
        return "medium"
    return "low"
```

Thresholds configurable via `config.py`:
- `THREAT_LETHAL_HP_RATIO = 0.5`
- `THREAT_HIGH_DAMAGE = 15`
- `THREAT_MEDIUM_DAMAGE = 8`

### 5.2 Intent Classification (per-round)

```python
_ATTACK_PATTERNS = {"attack", "strike", "bite", "slash", "thrash", "smash"}
_BUFF_PATTERNS = {"buff", "strength", "ritual", "rage", "grow", "enrage"}
_DEBUFF_PATTERNS = {"debuff", "weak", "vulnerable", "frail", "poison", "curse"}

def classify_intent(intents: list[str]) -> str:
    lowered = " ".join(i.lower() for i in intents)
    has_attack = any(kw in lowered for kw in _ATTACK_PATTERNS) or "Attack" in " ".join(intents)
    has_buff = any(kw in lowered for kw in _BUFF_PATTERNS)
    has_debuff = any(kw in lowered for kw in _DEBUFF_PATTERNS)

    if has_attack and not (has_buff or has_debuff):
        return "attack"
    if has_buff and not has_attack:
        return "buff"
    if has_debuff and not has_attack:
        return "debuff"
    if has_attack:
        return "mixed"
    return "unknown"
```

### 5.3 Threat Window (enemy behavior phase)

Derived from enemy intent sequence across past episodes, NOT from round number:

| Window | Meaning | Trigger |
|--------|---------|---------|
| `setup_window` | Enemy is buffing/preparing, low immediate threat | Intent is buff/debuff, incoming < 8 |
| `burst_window` | Enemy is dealing heavy damage | Intent is attack, incoming >= 15 |
| `recovery_window` | Enemy just finished burst, next move likely non-attack | Follows a burst round in 60%+ episodes |
| `lethal_window` | Enemy damage can kill player this turn | effective_damage >= current_hp |

**Important**: `threat_window` is NOT computed from round number (R1-2 = opening). It's computed from the enemy's actual behavior pattern. A Fuzzy Wurm Crawler might be in `setup_window` at R1, `burst_window` at R3, `recovery_window` at R4 — this is enemy-specific, not round-number-specific.

---

## 6. Deck Stage Classification

Deck stage captures "how developed is this deck", not just "how big". MVP uses a composite signal:

```python
def classify_deck_stage(
    floor: int,
    deck_size: int,
    has_scaling: bool,      # any card that scales (Strength, Demon Form, etc.)
    has_core_card: bool,    # at least 1 non-starter attack dealing 10+ base damage
    has_premium_block: bool, # at least 1 non-starter block card
) -> str:
    if floor <= 5 and deck_size <= 12:
        return "starter"
    if not has_core_card and not has_scaling:
        return "building"    # still assembling core pieces
    if has_scaling or (has_core_card and has_premium_block):
        return "scaling"     # has engine, growing power
    return "mature"          # deck is functional, refinement phase
```

Inputs:
- `floor`: from `GameState.floor`
- `deck_size`: from `len(gs.deck)` or `CombatTracker.deck_size`
- `has_scaling` / `has_core_card` / `has_premium_block`: derived from deck card list + knowledge DB card metadata (damage/block values from `card_lookup.py`)

---

## 7. SituationTag Model

Attached to each `CombatRound` in memory:

```python
@dataclass(frozen=True)
class SituationTag:
    threat_level: str = "medium"           # lethal|high|medium|low
    intent_class: str = "unknown"          # attack|buff|debuff|mixed|unknown
    threat_window: str = ""                # setup|burst|recovery|lethal (empty if unknown)
    hand_capabilities: HandCapabilityTag | None = None
    deck_stage: str = ""                   # starter|building|scaling|mature

    # Outcome data: what happened after this situation
    damage_taken: int = 0
    outcome_quality: str = ""              # "clean" (0 dmg) | "acceptable" (<8) | "bad" (8-15) | "disaster" (15+)
    cards_that_helped: tuple[str, ...] = () # cards played that contributed to good outcome
    next_round_window: str = ""            # threat_window of the NEXT round (for "defer output" learning)
```

### Backward Compatibility

- `SituationTag` is an OPTIONAL field on `CombatRound` (default `None`)
- Old episodes with `None` tags are skipped in situation-level ranking but still work for whole-fight retrieval
- Backfill script computes tags from existing round data

---

## 8. Upcoming Pattern Confidence

### The Problem

Current `format_upcoming_patterns()` in `enemy_pattern_injector.py` shows what happened in past episodes after the current round. But it presents all patterns as equally reliable, even when the enemy's behavior varies significantly across episodes.

### Confidence Threshold

```python
def format_upcoming_patterns_with_confidence(
    episodes: list[CombatEpisode],
    current_round: int,
    min_consistency: float = 0.6,  # 60% of episodes must agree
) -> str:
    """Only inject upcoming patterns when they're stable across episodes."""
    if not episodes or len(episodes) < 2:
        return ""

    # Collect next-round intent classes from all episodes
    next_intents: list[str] = []
    for ep in episodes:
        next_rounds = [r for r in ep.rounds if r.round_num == current_round + 1]
        if next_rounds:
            tag = next_rounds[0].situation_tag
            if tag:
                next_intents.append(tag.intent_class)
            else:
                next_intents.append(classify_intent(list(next_rounds[0].enemy_intents)))

    if not next_intents:
        return ""

    # Check consistency: does the majority agree?
    from collections import Counter
    counts = Counter(next_intents)
    most_common_class, most_common_count = counts.most_common(1)[0]
    consistency = most_common_count / len(next_intents)

    if consistency < min_consistency:
        return ""  # Not stable enough — don't inject

    # Format with confidence
    confidence_pct = int(consistency * 100)
    return (
        f"Likely R{current_round + 1}: {most_common_class} "
        f"({confidence_pct}% consistent across {len(next_intents)} past fights)"
    )
```

Config: `UPCOMING_PATTERN_MIN_CONSISTENCY = 0.6` (requires 60%+ agreement to inject).

---

## 9. Round-Level Retrieval (combat_store.py)

### New Method: `query_rounds()`

```python
def query_rounds(
    self,
    enemy_key: str,
    character: str,
    situation: SituationTag,
    limit: int = 3,
) -> list[tuple[CombatRound, SituationTag, float]]:
    """Retrieve past rounds matching the current situation.

    Returns: list of (round, tag, similarity_score) sorted by score descending.
    """
    candidates = []

    with self._lock:
        for ep in self._episodes:
            # Hard filter
            if ep.enemy_key != enemy_key:
                continue
            if ep.character != character:
                continue

            for rnd in ep.rounds:
                tag = rnd.situation_tag  # may be None for old data
                if tag is None:
                    continue

                score = 0.0

                # Strong ranking: threat + intent + hand capabilities
                if tag.threat_level == situation.threat_level:
                    score += 2.0
                elif _adjacent_threat(tag.threat_level, situation.threat_level):
                    score += 0.5

                if tag.intent_class == situation.intent_class:
                    score += 1.5

                if tag.hand_capabilities and situation.hand_capabilities:
                    score += hand_capability_similarity(
                        tag.hand_capabilities, situation.hand_capabilities
                    ) * 0.15  # normalize: max ~1.8

                # Weak ranking
                if tag.deck_stage and tag.deck_stage == situation.deck_stage:
                    score += 0.5

                # Prefer rounds with clean outcomes for learning
                if tag.outcome_quality == "clean":
                    score += 0.5
                elif tag.outcome_quality == "acceptable":
                    score += 0.2

                candidates.append((rnd, tag, score))

    # Sort by score, deduplicate
    candidates.sort(key=lambda x: x[2], reverse=True)
    return _deduplicate_rounds(candidates, limit)


def _deduplicate_rounds(
    candidates: list[tuple],
    limit: int,
) -> list[tuple]:
    """Deduplicate by (intent_class, threat_level, top-3-cards)."""
    seen = set()
    result = []
    for rnd, tag, score in candidates:
        dedup_key = (
            tag.intent_class,
            tag.threat_level,
            tuple(sorted(rnd.cards_played[:3])),
        )
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        result.append((rnd, tag, score))
        if len(result) >= limit:
            break
    return result
```

---

## 10. Past Round Exemplar Format

Each retrieved past round is formatted as a structured exemplar for the LLM:

```
### Similar Past Situation (score: 7.2)
- Intent: Attack 9x2=18 (attack, high threat)
- Hand capabilities: can_apply_weak, can_block_8_plus, NOT can_block_full
- Played: [Neutralize, Defend+, Defend, Backflip] (4 cards, 3 energy)
- Result: -5 HP (acceptable)
- Next round: buff (67% consistent) — recovery window available
```

Template:
```python
def format_round_exemplar(
    rnd: CombatRound,
    tag: SituationTag,
    score: float,
) -> str:
    lines = []
    lines.append(f"### Similar Past Situation (relevance: {score:.1f})")

    # Intent + threat
    intent_str = ", ".join(rnd.enemy_intents) if rnd.enemy_intents else "unknown"
    lines.append(f"- Intent: {intent_str} ({tag.intent_class}, {tag.threat_level} threat)")

    # Hand capabilities (only notable ones)
    if tag.hand_capabilities:
        caps = []
        hc = tag.hand_capabilities
        if hc.can_apply_weak: caps.append("can_apply_weak")
        if hc.can_apply_vulnerable: caps.append("can_apply_vulnerable")
        if hc.can_block_full_incoming: caps.append("can_block_full")
        elif hc.can_block_8_plus: caps.append("can_block_8+")
        if hc.can_kill_this_turn: caps.append("CAN_KILL")
        if hc.has_setup_only: caps.append("setup_only_hand")
        if hc.has_draw_or_retain: caps.append("has_draw")
        if caps:
            lines.append(f"- Hand capabilities: {', '.join(caps)}")

    # What was played
    cards = ", ".join(rnd.cards_played) if rnd.cards_played else "none"
    lines.append(f"- Played: [{cards}]")

    # Outcome
    lines.append(f"- Result: {rnd.damage_taken} HP lost ({tag.outcome_quality})")

    # Next-round window (if available)
    if tag.next_round_window:
        lines.append(f"- Next round: {tag.next_round_window}")

    return "\n".join(lines)
```

---

## 11. Progressive Prompt Injection

### Priority by Round

| Round | Content | Token Budget |
|-------|---------|-------------|
| R1 | Whole-fight guide (120t) + best 1 situation exemplar (80t) + upcoming window if confident (40t) | 240t |
| R2+ | Situation exemplars x2 (160t) + upcoming window (40t) + whole-fight guide demoted to 1-line summary (30t) | 230t |
| HIGH/LETHAL threat | Filter: only survival-relevant exemplars (can_block, can_apply_weak). Drop setup/greed content. | 200t |
| LOW threat | Allow setup/greed exemplars. Include "defer damage to this window" hints. | 250t |

### Injection Structure in prompt_injector.py

```
## Situation Intel
*Adapt to your CURRENT hand and threat level.*

[If HIGH/LETHAL threat]:
  **SURVIVAL PRIORITY**: {incoming} damage incoming. {threat_level} threat.

[Situation exemplars — 1-3 past rounds with similar situation]

[If confident upcoming window]:
  Likely R{n+1}: {window_type} ({confidence}% consistent)

## Enemy Intel (background — existing guide, demoted at R2+)
[R1: full guide]
[R2+: 1-line summary only]
```

---

## 12. Skill Trigger Extensions

### New Optional Fields on SkillTrigger

```python
@dataclass(frozen=True)
class SkillTrigger:
    # ... existing fields unchanged ...

    # NEW: Situation-level triggers (all empty = match all, backward compat)
    threat_levels: frozenset[str] = frozenset()     # {"high", "lethal"}
    intent_classes: frozenset[str] = frozenset()     # {"attack", "mixed"}
    round_phases: frozenset[str] = frozenset()       # DEPRECATED: use threat_window
    deck_stages: frozenset[str] = frozenset()        # {"building", "scaling"}
    any_of_relics: frozenset[str] = frozenset()      # at least ONE must be present

    # Hand capability requirements (any listed = at least one must be true)
    requires_hand_capabilities: frozenset[str] = frozenset()
    # e.g. {"can_apply_weak", "can_block_full_incoming"}
    # Semantics: at least ONE of these must be true (OR, not AND)
```

### Updated Scoring in SkillTrigger.matches()

```python
def matches(self, ..., *, situation: SituationTag | None = None) -> tuple[bool, float]:
    # ... existing checks unchanged ...

    if situation is not None:
        # Threat level: ranking signal
        if self.threat_levels:
            if situation.threat_level in self.threat_levels:
                score += 2.0
            # Not a hard filter — skill still matches, just lower score

        # Intent class: ranking signal
        if self.intent_classes:
            if situation.intent_class in self.intent_classes:
                score += 1.5

        # Deck stage: weak ranking
        if self.deck_stages:
            if situation.deck_stage in self.deck_stages:
                score += 0.5

        # Relics: hard filter if specified (any-of semantics)
        # Note: caller must pass current relics via context_tags or a separate param
        if self.any_of_relics:
            relic_overlap = self.any_of_relics.intersection(context_tags)
            if not relic_overlap:
                return False, 0.0
            score += 0.3 * len(relic_overlap)

        # Hand capabilities: hard filter if specified (any-of)
        if self.requires_hand_capabilities and situation.hand_capabilities:
            hc = situation.hand_capabilities
            has_any = any(
                getattr(hc, cap, False)
                for cap in self.requires_hand_capabilities
            )
            if not has_any:
                return False, 0.0
            score += 1.0

    return True, max(score, 0.1)
```

---

## 13. Implementation Plan

### Phase 1: Situation Tagging + Round-Level Retrieval (MVP)

**Scope**: Add SituationTag/HandCapabilityTag, compute at round start, retrieve similar past rounds, inject into prompt.

**Files to modify**:

| File | Changes |
|------|---------|
| `src/memory/models_v2.py` | Add `HandCapabilityTag`, `SituationTag`, optional `situation_tag` field on `CombatRound` |
| `src/memory/short_term.py` | Compute `SituationTag` at `start_combat_round()`, store in `CombatRoundTracker` |
| `src/memory/combat_store.py` | Add `query_rounds()` method with two-tier retrieval |
| `src/memory/retriever.py` | Accept `current_round` + `hand_cards` + `gs` for situation computation; call `query_rounds()`; add `situation_hints` to `WorkingContext` |
| `src/memory/models_v2.py` | Add `situation_hints: tuple[str, ...]` to `WorkingContext` |
| `src/memory/prompt_injector.py` | Add `## Situation Intel` section, format round exemplars |
| `src/brain/enemy_pattern_injector.py` | Add `format_upcoming_patterns_with_confidence()`, replace existing call at R2+ |
| `src/brain/conversation.py` | Pass `current_round` + hand cards to retriever at each round; wire upcoming patterns |
| `config.py` | Add `THREAT_*` thresholds, `UPCOMING_PATTERN_MIN_CONSISTENCY` |

**New files**:
| File | Purpose |
|------|---------|
| `src/memory/situation.py` | `classify_threat()`, `classify_intent()`, `classify_deck_stage()`, `compute_hand_capabilities()`, `compute_situation_tag()` |
| `scripts/backfill_situation_tags.py` | Migration script: compute SituationTag for existing combat_episodes.jsonl |

**Expected benefit**:
- ~60% reduction in irrelevant pattern data at R2+
- Round-level "situation → action → outcome" exemplars in prompt
- Confidence-gated upcoming windows prevent learning from random patterns

**Risk**:
- Backfill quality limited by missing `hand_at_start` data in old episodes (CombatRoundTracker has it, but CombatRound model doesn't persist it yet → need to add)
- Threat classification thresholds may need tuning per enemy type

**Estimated effort**: 3-4 days

### Phase 2: Skill Trigger Extensions + Prompt Priority Tuning

**Scope**: Extend SkillTrigger with situation dimensions. Implement progressive injection (R1 vs R2+, high vs low threat).

**Files to modify**:

| File | Changes |
|------|---------|
| `src/skills/models.py` | Add `threat_levels`, `intent_classes`, `deck_stages`, `any_of_relics`, `requires_hand_capabilities` to `SkillTrigger` |
| `src/skills/library.py` | Pass `situation` to `trigger.matches()`, update scoring |
| `src/skills/composer.py` | Threat-aware skill filtering (HIGH → survival skills only) |
| `src/memory/prompt_injector.py` | Progressive injection: R1 guide-heavy, R2+ situation-heavy, threat-aware content filtering |
| `src/agent/loop.py` | Pass situation context to skill queries |
| `src/brain/conversation.py` | Demote whole-fight guide to 1-line at R2+ |

**Expected benefit**:
- Skills fire only in matching situations (no more "energy management" advice at lethal-threat rounds)
- Token budget better allocated: survival content at high threat, setup content at low threat

**Risk**:
- LLM-authored skills (from discovery/evolution) won't have situation triggers initially — need to update `discovery.py` prompt
- Existing seed skills have empty situation triggers → they still match everywhere (correct: they're universal)

**Estimated effort**: 3-4 days

### Phase 3: Observation + Decision Point

**Scope**: Run 10-20 games with Phase 1+2. Measure impact. Decide whether to proceed with SituationGuide consolidation.

**Metrics to track**:
- Combat HP efficiency (HP lost per combat) — before vs after
- Prompt token relevance (manual audit: % of injected content actually relevant)
- Skill trigger precision (% of injected skills that match current situation)
- Upcoming window accuracy (% of confident predictions that were correct)

**Decision gate**: Only proceed to SituationGuide consolidation if:
1. Round-level retrieval demonstrably improves decisions (lower HP loss or better card sequencing)
2. Enough tagged round data accumulates (100+ tagged rounds per common enemy)
3. Pattern consistency is high enough to warrant consolidation

### Phase 4 (Conditional): Situation Guide Consolidation

**Only if Phase 3 validation passes.**

**Scope**: Sub-group combat episodes by `(enemy_key, character, threat_level, intent_class)`. Generate per-situation guides via LLM.

**Files**:
- `src/memory/models_v2.py` — add `SituationGuide` model
- `src/memory/guide_store.py` — add `get_situation_guide()` / `set_situation_guide()`
- `src/memory/guide_consolidator.py` — sub-group by situation tags, minimum 4 tagged rounds per group

### Phase 5 (Later): Tool Gating + Advanced Matching

**Scope**: `APPLICABLE_SITUATIONS` for dynamic tools. HandCapabilityTag similarity in memory ranking. Deck stage in tool preprocessing.

**Lower ROI than Phase 1-2. Defer unless specific tool noise identified.**

---

## 14. Data Model Changes Summary

### New Types

```python
# src/memory/models_v2.py

@dataclass(frozen=True)
class HandCapabilityTag:
    can_apply_weak: bool = False
    can_apply_vulnerable: bool = False
    can_block_8_plus: bool = False
    can_block_full_incoming: bool = False
    can_deal_12_plus: bool = False
    can_kill_this_turn: bool = False
    has_aoe: bool = False
    has_draw_or_retain: bool = False
    has_setup_only: bool = False
    zero_cost_count: int = 0
    total_playable: int = 0
    attack_count: int = 0
    block_count: int = 0
    total_damage: int = 0
    total_block: int = 0

@dataclass(frozen=True)
class SituationTag:
    threat_level: str = "medium"
    intent_class: str = "unknown"
    threat_window: str = ""
    hand_capabilities: HandCapabilityTag | None = None
    deck_stage: str = ""
    damage_taken: int = 0
    outcome_quality: str = ""
    cards_that_helped: tuple[str, ...] = ()
    next_round_window: str = ""
```

### Modified Types

```python
# CombatRound: add optional situation_tag
@dataclass(frozen=True)
class CombatRound:
    # ... existing fields ...
    situation_tag: SituationTag | None = None  # NEW (backward compat: None)
    hand_at_start: tuple[str, ...] = ()        # NEW: persist hand for backfill

# CombatRoundTracker: already has hand_at_start, just needs situation_tag
@dataclass
class CombatRoundTracker:
    # ... existing fields ...
    situation_tag: SituationTag | None = None  # NEW

# WorkingContext: add situation hints
@dataclass(frozen=True)
class WorkingContext:
    # ... existing fields ...
    situation_hints: tuple[str, ...] = ()  # NEW: formatted round exemplars

# SkillTrigger: add situation dimensions
@dataclass(frozen=True)
class SkillTrigger:
    # ... existing fields ...
    threat_levels: frozenset[str] = frozenset()
    intent_classes: frozenset[str] = frozenset()
    deck_stages: frozenset[str] = frozenset()
    any_of_relics: frozenset[str] = frozenset()
    requires_hand_capabilities: frozenset[str] = frozenset()
```

---

## 15. Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Backfill: old episodes missing `hand_at_start` data | Medium | Backfill script sets `hand_capabilities=None` for old rounds; they still participate in threat/intent matching, just not hand-capability matching |
| Sparse data: rare enemies have <3 episodes | Low | Fall back to whole-fight guide (existing behavior). Situation retrieval gracefully returns empty. |
| Threat thresholds wrong for specific enemies | Medium | Make configurable. Log threat classifications for tuning. Can add per-enemy overrides later. |
| Intent parsing keywords incomplete | Medium | Start conservative (only "Attack" + damage numbers). Expand keywords as we see more enemy types. |
| Upcoming window over-confidence | High | Hard threshold: 60% consistency minimum, 2+ episodes minimum. Better to inject nothing than wrong info. |
| Token budget overflow with new sections | Medium | Strict budget per section. Situation hints replace (not add to) R2+ pattern dump. Net neutral or positive. |
| SituationTag serialization bloats JSONL | Low | HandCapabilityTag is ~15 fields of bools/ints. ~200 bytes per round. Acceptable. |

---

## 16. Success Criteria

Phase 1+2 is successful if:

1. **Combat HP efficiency improves by 10%+** — measured as average HP lost per combat across 20+ runs
2. **Prompt relevance increases** — manual audit of 10 combats shows 80%+ of injected memory/skill content is situation-relevant (vs current ~40%)
3. **No regression in win rate** — win rate stays same or improves
4. **Upcoming window accuracy > 70%** — when we predict "next round is X", it actually is X at least 70% of the time
5. **Zero additional API calls** — all situation computation is local

---

## Appendix A: Reusable Existing Structures

| Structure | Location | Reuse |
|-----------|----------|-------|
| `compute_total_incoming()` | `src/brain/prompts/_intent_fmt.py` | Direct input to `classify_threat()` |
| `CombatRoundTracker.hand_at_start` | `src/memory/short_term.py:41` | Input for `compute_hand_capabilities()` |
| `format_upcoming_patterns()` | `src/brain/enemy_pattern_injector.py:59` | Wrap with confidence threshold |
| `SkillTrigger.matches()` scoring | `src/skills/models.py:100` | Extend with situation dimensions |
| `_format_round_bucket()` | `src/memory/guide_consolidator.py:93` | Precursor to situation grouping |
| `CombatRound.enemy_intents` | `src/memory/models_v2.py:276` | Input for `classify_intent()` |
| `CombatContext.deck_cards` | `src/memory/models_v2.py:233` | Input for `classify_deck_stage()` |
| `_effective_hits()` | `src/brain/conversation.py:57` | Reuse for `total_damage` in HandCapabilityTag |

---

## 17. Evidence-Gated Skill / Tool Generation Quality Control

### 17.1 Problem: Current Generation Pipeline is Quantity-First

The existing skill/tool generation has two independent paths, both biased toward producing output:

**Path 1: `discovery.py` (skill discovery)**
- Runs every N runs via `_post_run_skill_update()` in `loop.py`
- Sends a run summary + key decisions to LLM with prompt "extract 0-3 new skills"
- Only dedup check: existing skill names listed in prompt (text-level, not semantic)
- Only quality gate: 400-char content limit
- Result: LLM generates 1-3 skills almost every time, many of which are:
  - Restatements of system prompt knowledge ("block when incoming is high")
  - Overgeneralized ("Silent should be more aggressive in Act 1")
  - Only supported by the current run with no cross-run validation
  - Semantically duplicate of existing skills but worded differently

**Path 2: `evolution_engine.py` (self-evolution)**
- Runs post-run via `_post_run_evolution()` with Opus 4.6
- Uses `write_skill` + `author_tool` tools in a multi-turn loop
- Dedup check: `_find_similar_skill()` — 40% keyword overlap in same category
- Quality gate: content length, trigger validation, test cases for tools
- Result: more thoughtful than discovery, but still:
  - No requirement for negative evidence
  - No cross-run validation against memory
  - No check against system prompt common knowledge
  - Tools generated for single-occurrence edge cases

**Observed symptoms** (from `data/evolution/archive_manual_review/`):
- 42 dynamic tools + 22 evolved skills archived for manual review
- Many tools solve problems that occur once in 20+ runs
- Many skills are mild variants of seed skill content
- Skill library inflation: more noise → worse retrieval → worse decisions → worse evolved skills (negative spiral)

### 17.2 Core Principle: Evidence-First, Not Summary-First

A skill should not be generated because the LLM can "summarize a lesson from this run." It should be generated only when there is **contrastive evidence** that following the advice produces better outcomes than not following it.

The default posture is **conservative**: do not generate. Only generate when evidence clears a quality gate.

### 17.3 Three-Tier Output Classification

Every candidate produced by the generation pipeline is classified into one of three tiers:

| Tier | Name | Persistence | Injected into prompts? |
|------|------|-------------|----------------------|
| 1 | `confirmed_skill` | Saved to `skills.json`, active | Yes, via normal retrieval |
| 2 | `candidate_hypothesis` | Saved to `data/evolution/hypotheses.jsonl` | No — held for future validation |
| 3 | `rejected_noise` | Logged to `data/evolution/evolution_log.jsonl` with rejection reason | No |

**Key change**: The current pipeline has only two states (generated → active, or not generated). The new pipeline adds `candidate_hypothesis` as a holding zone. Most candidates start here and only graduate to `confirmed_skill` after cross-run validation.

### 17.4 Evidence Model: Skill Evidence Card

Every candidate (whether confirmed, hypothesis, or rejected) carries an evidence card:

```python
@dataclass(frozen=True)
class SkillEvidenceCard:
    """Structured evidence supporting or refuting a candidate skill."""

    # Identity
    candidate_name: str = ""
    candidate_content: str = ""
    candidate_trigger: dict = field(default_factory=dict)

    # Positive evidence: situations where this advice was followed → good outcome
    positive_examples: tuple[RoundExemplar, ...] = ()

    # Negative evidence: situations where this advice was NOT followed → bad outcome
    negative_examples: tuple[RoundExemplar, ...] = ()

    # Cross-run support: similar situations from memory that corroborate
    supporting_memory_refs: tuple[str, ...] = ()  # episode_id references

    # Contradictions: situations where following this advice led to bad outcomes
    contradicting_examples: tuple[RoundExemplar, ...] = ()

    # Overlap analysis
    overlapping_skill_ids: tuple[str, ...] = ()    # existing skills with similar content
    overlapping_rule_ids: tuple[str, ...] = ()     # existing rules with similar content
    overlap_type: str = ""  # "semantic_duplicate" | "strict_subset" | "partial_overlap" | "novel"

    # Common knowledge check
    is_system_prompt_knowledge: bool = False        # covered by system prompt
    system_prompt_evidence: str = ""                # which part of system prompt covers this

    # Scores
    evidence_support_score: float = 0.0             # 0-1: strength of positive evidence
    negative_case_score: float = 0.0                # 0-1: strength of "not doing it = worse"
    cross_run_support_score: float = 0.0            # 0-1: consistency across runs
    novelty_score: float = 0.0                      # 0-1: how much new info this adds
    execution_clarity_score: float = 0.0            # 0-1: how actionable the advice is
    overlap_penalty: float = 0.0                    # 0-1: deduction for redundancy
    common_knowledge_penalty: float = 0.0           # 0-1: EFFECTIVE penalty after trigger-specificity
                                                    # adjustment (see 17.8). Capped at 0.3 when
                                                    # trigger is narrow even if keyword overlap is high.

    # Composite
    @property
    def candidacy_score(self) -> float:
        """Composite score determining tier classification."""
        raw = (
            self.evidence_support_score * 2.0       # most important
            + self.negative_case_score * 1.5        # second most important
            + self.cross_run_support_score * 1.0
            + self.novelty_score * 1.0
            + self.execution_clarity_score * 0.5
            - self.overlap_penalty * 2.0            # heavy penalty
            - self.common_knowledge_penalty * 2.0   # heavy penalty
        )
        return max(0.0, raw)

    # Decision
    decision: str = ""  # "confirmed" | "candidate" | "rejected"
    rejection_reason: str = ""
    source_run_id: str = ""
    timestamp: float = 0.0


@dataclass(frozen=True)
class RoundExemplar:
    """A specific round used as evidence for/against a skill candidate."""

    episode_id: str = ""
    run_id: str = ""
    enemy_key: str = ""
    round_num: int = 0
    threat_level: str = ""
    intent_class: str = ""
    hand_capabilities_summary: str = ""    # e.g. "can_apply_weak, can_block_8+"
    cards_played: tuple[str, ...] = ()
    damage_taken: int = 0
    outcome_quality: str = ""              # clean|acceptable|bad|disaster
    relevance_note: str = ""               # why this exemplar supports/refutes the candidate
    tag_source: str = ""                   # "runtime" | "backfill" | "" — provenance from SituationTag
```

### 17.5 Evidence Collection Pipeline

The generation pipeline changes from:

```
Current:  run_data → LLM("extract skills") → skills → add to library
```

To:

```
Proposed: run_data → LLM("propose candidates") → candidates
              → evidence_collector(candidate, current_run, memory)
              → score_candidate(evidence_card)
              → classify: confirmed | hypothesis | rejected
              → confirmed → library; hypothesis → hypotheses.jsonl; rejected → log
```

#### Step 1: Candidate Proposal (LLM)

The discovery/evolution LLM still proposes candidates, but the prompt changes:

```
OLD: "Extract 0-3 new strategic skills from this run."
NEW: "Propose 0-2 candidate hypotheses from this run.
     For each candidate, you MUST provide:
     1. The specific rounds/situations that motivated this hypothesis
     2. At least one round where NOT following this advice led to worse outcomes
     3. Why this is NOT already covered by existing skills or the system prompt
     If you cannot provide items 2 AND 3, do not propose the candidate."
```

The LLM output format changes to include evidence references:

```json
{
  "name": "Weak_before_block_on_Fuzzy_Wurm_burst",
  "content": "When facing Fuzzy Wurm at high-threat attack round with can_apply_weak + can_block_8+: apply Weak first, then block. Reduces incoming by ~25% before block absorbs remainder.",
  "category": "combat",
  "trigger": {
    "enemy_names": ["Fuzzy Wurm Crawler"],
    "state_types": ["monster"],
    "threat_levels": ["high", "lethal"],
    "requires_hand_capabilities": ["can_apply_weak"]
  },
  "positive_rounds": [
    {"round": 3, "floor": 8, "description": "Applied Weak+Defend, took 5 dmg instead of 18"}
  ],
  "negative_rounds": [
    {"round": 3, "floor": 8, "description": "Previous run: no Weak, pure block, took 12 dmg"}
  ],
  "not_covered_by": "System prompt says 'block when high incoming' but doesn't specify Weak-first sequencing for damage reduction."
}
```

#### Step 2: Evidence Collection (Local, No API Calls)

For each candidate proposed by the LLM, the system automatically collects additional evidence.

**Critical constraint**: only rounds that are *situationally similar* to the candidate's trigger can serve as positive or negative evidence. Without this, the system will compare fundamentally different hands, threat levels, or enemy phases and draw false conclusions.

##### 2a. Situation Similarity Gate for Evidence Rounds

A past round qualifies as evidence for a candidate only if it passes a minimum similarity threshold:

```python
MIN_EVIDENCE_SIMILARITY = 3.0  # out of ~8.0 max

def is_valid_evidence_round(
    candidate_trigger: dict,
    round_tag: SituationTag,
    episode: CombatEpisode,
) -> tuple[bool, float]:
    """Check whether a round is situationally similar enough to serve as
    evidence for/against a candidate.  Returns (qualifies, similarity_score).

    Similarity dimensions and weights:
      enemy_key match (hard filter):   REQUIRED — mismatch → reject
      combat_type match:               +1.0 if same
      threat_level match:              +2.0 if same, +0.5 if adjacent
      intent_class match:              +1.5 if same
      hand_capability overlap:         +0.2 per matching boolean capability (max ~2.0)
      deck_stage match:                +0.5 if same

    A round must score >= MIN_EVIDENCE_SIMILARITY to be used as evidence.

    Provenance adjustment (tag_source):
      - "runtime" rounds use the standard threshold (MIN_EVIDENCE_SIMILARITY).
      - "backfill" or "" rounds use a raised threshold (+1.0) because their
        threat_level is retrospective and hand_capabilities is always None,
        making the similarity score inherently less trustworthy.
    """
    # Hard filter: enemy must match
    candidate_enemies = set(candidate_trigger.get("enemy_names", []))
    if candidate_enemies and episode.enemy_key not in candidate_enemies:
        return False, 0.0
    if not candidate_enemies and round_tag is None:
        return False, 0.0

    score = 0.0

    # combat_type
    candidate_types = set(candidate_trigger.get("state_types", []))
    if candidate_types and episode.combat_type in candidate_types:
        score += 1.0

    if round_tag is None:
        return score >= MIN_EVIDENCE_SIMILARITY, score

    # threat_level
    candidate_threats = set(candidate_trigger.get("threat_levels", []))
    if candidate_threats:
        if round_tag.threat_level in candidate_threats:
            score += 2.0
        elif _adjacent_threat(round_tag.threat_level, next(iter(candidate_threats))):
            score += 0.5
        # If threat_level is specified in trigger but round doesn't match at all,
        # this round is poor evidence — don't add score but don't hard-reject either.

    # intent_class
    candidate_intents = set(candidate_trigger.get("intent_classes", []))
    if candidate_intents:
        if round_tag.intent_class in candidate_intents:
            score += 1.5

    # hand_capability overlap
    candidate_caps = set(candidate_trigger.get("requires_hand_capabilities", []))
    if candidate_caps and round_tag.hand_capabilities:
        hc = round_tag.hand_capabilities
        matches = sum(1 for cap in candidate_caps if getattr(hc, cap, False))
        score += matches * 0.2

    # deck_stage
    candidate_stages = set(candidate_trigger.get("deck_stages", []))
    if candidate_stages and round_tag.deck_stage in candidate_stages:
        score += 0.5

    # Provenance-adjusted threshold
    threshold = MIN_EVIDENCE_SIMILARITY
    if round_tag.tag_source != "runtime":
        threshold += 1.0  # backfill/legacy rounds need stronger match

    return score >= threshold, score
```

##### 2a-bis. Evidence Provenance Weighting

Each evidence round carries a provenance multiplier that scales its contribution
to the candidate's scores:

| `tag_source` | Multiplier | Rationale |
|---|---|---|
| `"runtime"` | 1.0 | Predictive tag — what was knowable at decision time |
| `"backfill"` | 0.5 | Retrospective tag — threat_level from actual damage, no hand data |
| `""` (legacy) | 0.5 | Same as backfill — predates provenance tracking |

Applied in `_build_evidence_card()` when accumulating scores:
- Each positive/negative example's contribution is multiplied by its provenance weight
- Example: 2 runtime positives (2 × 1.0 = 2.0 effective) vs 4 backfill positives (4 × 0.5 = 2.0 effective)

**Confirmation rule**: backfilled rounds may support a hypothesis, but cannot alone
confirm it. Specifically, `classify_candidate()` requires at least one runtime-tagged
round among the positive evidence to return `"confirmed"`. A candidate with only
backfill evidence maxes out at `"candidate"` regardless of score.

The distinction between positive and negative evidence then becomes:
- **Positive exemplar**: round passes similarity gate AND the advice was followed AND outcome was good (`clean` or `acceptable`)
- **Negative exemplar**: round passes similarity gate AND the advice was NOT followed AND outcome was bad (`bad` or `disaster`)
- Rounds that don't pass the similarity gate are **ignored** — they cannot serve as evidence in either direction.

##### 2b. Evidence Collection Function

```python
async def collect_evidence(
    candidate: dict,
    current_run_episodes: list[CombatEpisode],
    combat_store: CombatMemoryStore,
    skill_library: SkillLibrary,
    rule_store: RuleStore,
    system_prompt_keywords: set[str],
) -> SkillEvidenceCard:
    """Collect and score evidence for a candidate skill. Zero API calls."""

    trigger = candidate.get("trigger", {})

    # 1. Extract positive examples from current run (similarity-gated)
    positive = _find_positive_examples(candidate, current_run_episodes, trigger)

    # 2. Extract negative examples from current run (similarity-gated)
    negative = _find_negative_examples(candidate, current_run_episodes, trigger)

    # 3. Cross-run validation from memory (similarity-gated)
    memory_support = _find_cross_run_support(candidate, combat_store, trigger)
    memory_contradictions = _find_cross_run_contradictions(candidate, combat_store, trigger)

    # 4. Overlap check against existing skills
    overlap_skills = _find_overlapping_skills(candidate, skill_library)
    overlap_rules = _find_overlapping_rules(candidate, rule_store)

    # 5. Common knowledge check (trigger-aware — see 17.8)
    is_common = _is_system_prompt_knowledge(candidate, system_prompt_keywords)

    # 6. Score all dimensions
    return _build_evidence_card(
        candidate, positive, negative,
        memory_support, memory_contradictions,
        overlap_skills, overlap_rules, is_common,
    )
```

#### Step 3: Scoring

Each dimension is scored 0.0-1.0:

**`evidence_support_score`**:
- 0.0: no positive examples
- 0.3: 1 positive example from current run only
- 0.5: 2+ positive examples from current run
- 0.7: positive examples + cross-run support
- 1.0: 3+ positive examples across 2+ runs

**`negative_case_score`**:
- 0.0: no negative examples at all
- 0.3: 1 weak negative example (bad outcome but confounded)
- 0.5: 1 strong negative example (same situation, didn't follow advice, clearly worse)
- 0.7: 2+ negative examples
- 1.0: negative examples across multiple runs

**`cross_run_support_score`**:
- 0.0: current run only, no memory support
- 0.3: 1 supporting episode from memory
- 0.6: 2+ supporting episodes from different runs
- 1.0: 3+ supporting episodes + no contradictions

**`novelty_score`**:
- 0.0: semantic duplicate of existing skill
- 0.2: strict subset of existing skill (less specific)
- 0.5: partial overlap but adds new trigger conditions or tactical detail
- 0.8: adds a new dimension (e.g. first skill to mention threat_window for this enemy)
- 1.0: entirely new insight with no overlap

**`execution_clarity_score`**:
- 0.0: abstract evaluation ("be more careful")
- 0.3: directional advice ("prioritize defense")
- 0.6: specific advice with conditions ("when X, do Y")
- 0.8: specific advice with conditions AND sequencing ("when X, first do Y, then Z")
- 1.0: fully executable with measurable outcome ("when incoming >= 15 and can_apply_weak, play Weak before Block; expected to reduce damage by 25%")

**`overlap_penalty`**:
- 0.0: no overlap with any existing skill/rule
- 0.3: shares category + some keywords with an existing skill
- 0.6: covers substantially similar ground as an existing skill
- 0.8: is a weaker/vaguer restatement of an existing skill
- 1.0: is semantically identical to an existing skill

**`common_knowledge_penalty`**:
- 0.0: not covered by system prompt or seed skills
- 0.3: tangentially related to system prompt content
- 0.6: clearly covered by system prompt in general terms
- 0.8: directly stated in system prompt
- 1.0: is a basic game mechanic that any player knows (e.g. "block reduces damage")

#### Step 4: Classification Gate

The gate resolves the tension between two legitimate evidence paths:

- **Path A (contrastive)**: positive + negative evidence → can confirm with moderate score
- **Path B (cross-run pattern)**: strong positive + cross-run consistency, no negatives → can also confirm, but needs higher bar

The rule is: **without negative evidence, a candidate can never be directly `confirmed` — it maxes out at `candidate_hypothesis`**. This is deliberate. Negative evidence is what distinguishes "this happened to correlate with good outcomes" from "not doing this makes outcomes worse." A hypothesis can still be promoted to confirmed later via the lifecycle re-evaluation (Section 17.10) when negative evidence accumulates naturally.

The one exception: cross-run pattern candidates with very strong consistency (`cross_run_support_score >= 0.8` AND `evidence_support_score >= 0.7`) can be confirmed without explicit negative evidence, because the cross-run replication itself is evidence against the null hypothesis.

```python
CONFIRMED_THRESHOLD = 4.0   # candidacy_score >= 4.0 → confirmed_skill
HYPOTHESIS_THRESHOLD = 2.0  # 2.0 <= score < 4.0 → candidate_hypothesis
# score < 2.0 → rejected_noise

def classify_candidate(card: SkillEvidenceCard) -> str:
    score = card.candidacy_score

    # Hard rejections (regardless of score)
    if card.common_knowledge_penalty >= 0.8:
        return "rejected"  # it's just system prompt knowledge
    if card.overlap_penalty >= 0.8 and card.novelty_score < 0.3:
        return "rejected"  # it's a duplicate with no new info
    if card.evidence_support_score == 0.0:
        return "rejected"  # no positive evidence at all
    if card.execution_clarity_score < 0.3:
        return "rejected"  # too vague to be actionable

    has_positive = card.evidence_support_score >= 0.3
    has_negative = card.negative_case_score >= 0.3
    has_strong_cross_run = (
        card.cross_run_support_score >= 0.8
        and card.evidence_support_score >= 0.7
    )
    # Provenance gate: at least one runtime-tagged round in positive evidence.
    # Backfill-only evidence can support a hypothesis but never confirm.
    has_runtime_evidence = any(
        ex.tag_source == "runtime"
        for ex in card.positive_examples
    )

    if not has_positive:
        return "rejected"

    if score >= CONFIRMED_THRESHOLD:
        if not has_runtime_evidence:
            # Backfill-only — cap at hypothesis regardless of score
            return "candidate"
        if has_negative:
            # Path A: contrastive evidence with runtime backing → confirmed
            return "confirmed"
        if has_strong_cross_run:
            # Path B: very strong cross-run replication → confirmed
            return "confirmed"
        # Has score + runtime but no negative AND no strong cross-run → hypothesis
        return "candidate"

    if score >= HYPOTHESIS_THRESHOLD:
        return "candidate"
    return "rejected"
```

**Summary of allowed paths to each tier:**

| Tier | Path A (contrastive) | Path B (cross-run only) |
|------|---------------------|------------------------|
| `confirmed` | score >= 4.0 AND has_negative AND has_runtime_evidence | score >= 4.0 AND cross_run >= 0.8 AND evidence >= 0.7 AND has_runtime_evidence |
| `candidate` | score >= 2.0, any evidence shape (backfill-only OK) | score >= 2.0, any evidence shape (backfill-only OK) |
| `rejected` | score < 2.0 OR hard rejection | score < 2.0 OR hard rejection |

### 17.6 Evidence Minimum Requirements

A candidate MUST meet at least one of these evidence patterns to avoid immediate rejection.

**All evidence rounds must pass the situation similarity gate** (Section 17.5 Step 2a, `MIN_EVIDENCE_SIMILARITY >= 3.0`). Rounds that don't pass are not counted. **Adherence is evaluated mechanically** (Section 17.10 Adherence Evaluator): "advice followed" means `adherence.level in ("full", "partial")` with `evidence_weight > 0`.

| Pattern | Positive Evidence | Negative Evidence | Cross-Run |
|---------|------------------|-------------------|-----------|
| **Strong contrastive** | 1+ similarity-gated rounds where advice followed (full/partial) → good outcome | 1+ similarity-gated rounds where advice NOT followed → bad outcome | Optional |
| **Cross-run pattern** | 2+ similarity-gated positive rounds across 2+ runs | Optional (but boosts score; required for `confirmed` without negatives per Step 4) | Required |
| **Current-run strong** | 2+ similarity-gated positive rounds in current run | 2+ similarity-gated negative rounds in current run | Not required |

If none of these patterns are met, the candidate is classified as `rejected_noise`.

### 17.7 Semantic Dedup: Beyond Keyword Overlap

The current `_find_similar_skill()` uses 40% keyword overlap, which misses semantic duplicates. The new system uses a layered dedup approach:

**Layer 1: Trigger overlap** (fast, local)
```python
def trigger_overlap(a: SkillTrigger, b: SkillTrigger) -> float:
    """Score 0-1 how similar two triggers are."""
    score = 0.0
    dimensions = 0

    if a.state_types and b.state_types:
        dimensions += 1
        score += len(a.state_types & b.state_types) / max(len(a.state_types | b.state_types), 1)

    if a.enemy_names and b.enemy_names:
        dimensions += 1
        score += len(a.enemy_names & b.enemy_names) / max(len(a.enemy_names | b.enemy_names), 1)

    if a.threat_levels and b.threat_levels:
        dimensions += 1
        score += len(a.threat_levels & b.threat_levels) / max(len(a.threat_levels | b.threat_levels), 1)

    if a.intent_classes and b.intent_classes:
        dimensions += 1
        score += len(a.intent_classes & b.intent_classes) / max(len(a.intent_classes | b.intent_classes), 1)

    return score / max(dimensions, 1)
```

**Layer 2: Content keyword overlap** (existing, improved)
```python
def content_overlap(a_content: str, b_content: str) -> float:
    """Improved keyword overlap with stopword removal and stemming."""
    STOPWORDS = {"the", "a", "an", "is", "are", "when", "if", "then", "and", "or",
                 "to", "in", "on", "at", "for", "with", "this", "that", "it"}
    a_words = set(a_content.lower().split()) - STOPWORDS
    b_words = set(b_content.lower().split()) - STOPWORDS
    if not a_words or not b_words:
        return 0.0
    return len(a_words & b_words) / len(a_words | b_words)
```

**Layer 3: Semantic equivalence check** (combined)
```python
def is_semantic_duplicate(candidate: dict, existing: Skill) -> bool:
    """A candidate is a semantic duplicate if triggers overlap highly
    AND content conveys the same actionable advice."""
    t_overlap = trigger_overlap(candidate_trigger, existing.trigger)
    c_overlap = content_overlap(candidate["content"], existing.content)

    # Same trigger + same content = duplicate
    if t_overlap >= 0.7 and c_overlap >= 0.4:
        return True
    # Very similar content even with different trigger = likely duplicate
    if c_overlap >= 0.6:
        return True
    return False
```

### 17.8 Common Knowledge Detection

Skills that restate system prompt knowledge provide zero information gain. Detect and reject them.

**Critical constraint**: keyword overlap alone is not enough to flag a candidate as common knowledge. A candidate like "Fuzzy Wurm high-threat attack round: Weak before Block" contains the words `weak`, `block`, `damage` — the same words in the system prompt concept `block_when_high_incoming`. But the candidate is clearly NOT common knowledge: it specifies an enemy, a threat level, a sequencing order, and a quantitative claim. The penalty must account for trigger specificity.

**Rule: Common knowledge penalty is heavy only when ALL of the following are true:**
1. Content keyword overlap with a system prompt concept is high (>= 0.6)
2. Trigger is broad (no enemy_names, no threat_levels, no intent_classes, no requires_hand_capabilities)
3. Novelty is low (novelty_score < 0.5)

If ANY of these conditions is false, the penalty is capped at 0.3 regardless of keyword overlap.

```python
# Pre-computed from system prompts (COMBAT, COMBAT_BOSS, DECKBUILD, STRATEGIC)
SYSTEM_PROMPT_CONCEPTS = {
    "block_when_high_incoming": {"block", "incoming", "damage", "high", "defend"},
    "energy_management": {"energy", "cost", "0-cost", "free", "spend"},
    "kill_if_possible": {"kill", "lethal", "finish", "one-shot"},
    "vulnerable_before_damage": {"vulnerable", "before", "damage", "apply"},
    "weak_reduces_damage": {"weak", "reduce", "incoming", "less"},
    "dont_waste_energy": {"waste", "energy", "unspent", "leftover"},
    "play_0_cost_first": {"0-cost", "free", "first", "before"},
    "aoe_for_multi_enemy": {"aoe", "all", "enemies", "multi", "area"},
    "draw_before_play": {"draw", "before", "play", "cards", "cycle"},
    "potion_timing": {"potion", "timing", "save", "boss", "emergency"},
}


def _trigger_specificity(trigger: dict) -> float:
    """Score 0-1 how specific a candidate's trigger is.

    A fully generic trigger (empty enemy, empty threat, empty intent,
    empty hand capability) scores 0.0.
    Each specific dimension adds to the score.
    """
    score = 0.0
    if trigger.get("enemy_names"):
        score += 0.3
    if trigger.get("threat_levels"):
        score += 0.2
    if trigger.get("intent_classes"):
        score += 0.2
    if trigger.get("requires_hand_capabilities"):
        score += 0.2
    if trigger.get("deck_stages"):
        score += 0.1
    return min(score, 1.0)


def common_knowledge_score(content: str, trigger: dict, novelty: float) -> float:
    """Score 0-1 how much this content is just system prompt common knowledge.

    Returns the EFFECTIVE penalty after accounting for trigger specificity.
    High keyword overlap + broad trigger + low novelty = high penalty.
    High keyword overlap + narrow trigger = capped at 0.3 (specific advice
    that happens to use common words is NOT common knowledge).
    """
    words = set(content.lower().split())
    max_overlap = 0.0
    for concept, keywords in SYSTEM_PROMPT_CONCEPTS.items():
        overlap = len(words & keywords) / len(keywords)
        max_overlap = max(max_overlap, overlap)

    if max_overlap < 0.4:
        return 0.0  # not enough keyword overlap to trigger concern

    specificity = _trigger_specificity(trigger)

    # All three conditions must hold for heavy penalty
    is_broad_trigger = specificity < 0.2
    is_low_novelty = novelty < 0.5
    is_high_overlap = max_overlap >= 0.6

    if is_high_overlap and is_broad_trigger and is_low_novelty:
        return max_overlap  # full penalty (0.6 - 1.0)

    # If trigger is specific or novelty is decent, cap the penalty
    # Rationale: "Weak before Block on Fuzzy Wurm at high threat" uses
    # the same words as "weak reduces damage" but is clearly different advice.
    return min(max_overlap * (1.0 - specificity), 0.3)
```

**Examples of the corrected behavior:**

| Candidate | Keyword Overlap | Trigger Specificity | Novelty | Effective Penalty |
|-----------|----------------|--------------------|---------|--------------------|
| "block when incoming is high" | 0.8 (`block_when_high_incoming`) | 0.0 (no trigger conditions) | 0.1 | **0.8** (all conditions met → full penalty) |
| "Fuzzy Wurm high-threat: Weak before Block" | 0.6 (`weak_reduces_damage`) | 0.7 (enemy + threat + hand_cap) | 0.8 | **0.18** (specific trigger → capped) |
| "apply Vulnerable before damage" | 0.8 (`vulnerable_before_damage`) | 0.0 (generic) | 0.2 | **0.8** (generic restatement → full) |
| "vs The Insatiable SALIVATE: go full offense" | 0.3 | 0.5 (enemy + intent) | 0.9 | **0.0** (overlap < 0.4 → no concern) |

Also check against seed skills:
```python
def is_seed_restatement(content: str, seed_skills: list[Skill]) -> bool:
    """Check if candidate is just restating a seed skill."""
    for seed in seed_skills:
        if seed.source != "seed":
            continue
        if content_overlap(content, seed.content) >= 0.5:
            return True
    return False
```

### 17.9 Specific Rejection Cases

These candidates should be automatically rejected:

| Candidate | Rejection Reason |
|-----------|-----------------|
| "Block when incoming damage is high" | `common_knowledge_penalty >= 0.8`: system prompt says this |
| "Silent should play more defensively in Act 1" | `execution_clarity_score < 0.3`: not actionable, no specific conditions |
| "Use Weak on attack rounds" | `overlap_penalty >= 0.6`: seed skill already covers Weak application |
| "Fogmog is easy, just attack" | `evidence_support_score = 0`: no contrastive evidence, just observation |
| "Prioritize energy management" | `common_knowledge_penalty >= 0.8` + `execution_clarity_score < 0.3` |
| "When HP is low, use potions" | `common_knowledge_penalty = 1.0`: basic game mechanic |

These candidates should be accepted:

| Candidate | Evidence | Why Accepted |
|-----------|----------|-------------|
| "Fuzzy Wurm R3 burst: Weak before Block when both available. Reduces effective incoming by 25% before block absorbs. Without Weak-first, R3 costs 12+ HP; with Weak-first, costs 3-5 HP." | 2 positive (R3 low damage), 1 negative (R3 high damage without Weak), 1 memory support | Novel sequencing insight. Starts as `candidate_hypothesis` (score ~3.5), promotes after cross-run corroboration. |
| "The Insatiable SALIVATE_MOVE rounds: go full offensive. 0 incoming damage. These rounds follow LUNGING_BITE in 80% of episodes." | 3 positive (offensive on buff rounds = 0 HP lost), 2 negative (defensive on buff rounds = wasted cards), cross-run pattern 80% | Specific enemy phase identification. Strong evidence + cross-run consistency → `confirmed_skill` (score ~4.5). |

### 17.10 Candidate Hypothesis Lifecycle

Hypotheses that don't meet the `confirmed` threshold are stored and re-evaluated:

```
candidate_hypothesis created at run N
  → at run N+K (next run encountering same enemy/situation):
    → find similarity-gated rounds from new episodes
    → evaluate adherence: did the agent follow the advice?
    → evaluate outcome: was the result good or bad?
    → classify: corroboration | contradiction | inconclusive
    → if corroborated: bump evidence scores, re-classify
    → if contradicted: add contradicting_examples, re-classify
    → if 3+ corroborations across 2+ runs: auto-promote to confirmed_skill
    → if 3+ contradictions: auto-reject
    → if 10 runs with no relevant encounters: expire and archive
```

**Storage**: `data/evolution/hypotheses.jsonl` — one JSON line per hypothesis with full evidence card.

**Re-evaluation trigger**: at post-run, after memory extraction, check all active hypotheses against the new episodes.

#### Adherence Evaluator

The lifecycle above depends on determining whether the agent "followed" or "didn't follow" a hypothesis's advice in a given round. This needs an operational definition — without it, promotion/rejection is not auditable or reproducible.

```python
@dataclass(frozen=True)
class AdherenceResult:
    """Whether a candidate's advice was followed in a specific round."""
    level: str = "unknown"        # "full" | "partial" | "none" | "unknown"
    evidence_weight: float = 0.0  # how much this round counts as corroboration/contradiction
    matched_actions: tuple[str, ...] = ()   # which parts of the advice were followed
    missed_actions: tuple[str, ...] = ()    # which parts were not followed
    note: str = ""


def evaluate_adherence(
    candidate: dict,
    round_tag: SituationTag,
    round_data: CombatRound,
) -> AdherenceResult:
    """Determine whether a round's actual play followed the candidate's advice.

    Works by extracting ACTION PREDICATES from the candidate content and
    checking them against the round's cards_played + potions_used.

    Three adherence levels:
      full:    ALL action predicates satisfied → evidence_weight = 1.0
      partial: SOME action predicates satisfied → evidence_weight = 0.5
      none:    NO action predicates satisfied → evidence_weight = 1.0 (strong non-adherence)
      unknown: cannot determine (no extractable predicates) → evidence_weight = 0.0
    """
    content = candidate.get("content", "").lower()
    cards_played = set(c.lower() for c in round_data.cards_played)
    potions_used = set(p.lower() for p in round_data.potions_used)
    hc = round_tag.hand_capabilities if round_tag else None

    predicates = _extract_action_predicates(content, hc)
    if not predicates:
        return AdherenceResult(level="unknown", evidence_weight=0.0,
                               note="No extractable action predicates from candidate content")

    matched = []
    missed = []
    for pred in predicates:
        if pred.check(cards_played, potions_used, round_data):
            matched.append(pred.description)
        else:
            missed.append(pred.description)

    if not missed:
        return AdherenceResult(level="full", evidence_weight=1.0,
                               matched_actions=tuple(matched), note="All predicates satisfied")
    if not matched:
        return AdherenceResult(level="none", evidence_weight=1.0,
                               missed_actions=tuple(missed), note="No predicates satisfied")
    ratio = len(matched) / (len(matched) + len(missed))
    return AdherenceResult(level="partial", evidence_weight=0.5,
                           matched_actions=tuple(matched), missed_actions=tuple(missed),
                           note=f"{len(matched)}/{len(matched)+len(missed)} predicates satisfied")
```

##### Action Predicate Extraction

Action predicates are mechanical checks extracted from the candidate's natural language content:

| Pattern in content | Predicate | Check against |
|---|---|---|
| "apply Weak" / "play Weak" / "use Neutralize" | `CardPlayedPredicate("neutralize")` | card name in `cards_played` |
| "block" / "play Defend" | `CardTypePredicate("block")` | any card with block in `cards_played` |
| "Weak before Block" / "first X then Y" | `SequencePredicate("neutralize", "defend")` | card order in `cards_played` list |
| "go offensive" / "full damage" | `CapabilityUsedPredicate("attack_count >= 2")` | attack cards in `cards_played` >= 2 |
| "don't attack" / "skip offense" | `NegativePredicate("attack_count == 0")` | no attack cards in `cards_played` |

```python
@dataclass(frozen=True)
class ActionPredicate:
    """A single testable assertion about what the agent should have done."""
    predicate_type: str = ""     # "card_played" | "card_type" | "sequence" | "capability" | "negative"
    description: str = ""        # human-readable: "played Neutralize"
    args: tuple[str, ...] = ()   # predicate-specific arguments

    def check(self, cards_played: set[str], potions_used: set[str],
              round_data: CombatRound) -> bool:
        if self.predicate_type == "card_played":
            return any(self.args[0] in c for c in cards_played)
        if self.predicate_type == "card_type":
            # "block" → check if any block card was played
            if self.args[0] == "block":
                return bool(cards_played)  # simplified; real impl checks card metadata
            return False
        if self.predicate_type == "sequence":
            # "a before b" → check order in cards_played list
            played_list = [c.lower() for c in round_data.cards_played]
            try:
                idx_a = next(i for i, c in enumerate(played_list) if self.args[0] in c)
                idx_b = next(i for i, c in enumerate(played_list) if self.args[1] in c)
                return idx_a < idx_b
            except StopIteration:
                return False
        if self.predicate_type == "negative":
            return not any(self.args[0] in c for c in cards_played)
        return False


def _extract_action_predicates(
    content: str,
    hand_capabilities: HandCapabilityTag | None,
) -> list[ActionPredicate]:
    """Extract testable predicates from natural language skill content.

    Uses keyword patterns — not LLM. Fast, deterministic, auditable.
    Returns empty list if content is too abstract to extract predicates.
    """
    predicates: list[ActionPredicate] = []

    # Pattern: "play/apply/use <CardName>"
    import re
    for m in re.finditer(r"(?:play|apply|use)\s+(\w[\w\s]*?)(?:\s+(?:first|before|then)|[,.]|$)", content, re.IGNORECASE):
        card = m.group(1).strip().lower()
        if card and len(card) > 2:
            predicates.append(ActionPredicate("card_played", f"played {card}", (card,)))

    # Pattern: "X before Y" / "first X then Y"
    seq_patterns = [
        re.compile(r"(\w+)\s+before\s+(\w+)", re.IGNORECASE),
        re.compile(r"first\s+(\w+).*?then\s+(\w+)", re.IGNORECASE),
    ]
    for pat in seq_patterns:
        for m in pat.finditer(content):
            a, b = m.group(1).lower(), m.group(2).lower()
            predicates.append(ActionPredicate("sequence", f"{a} before {b}", (a, b)))

    # Pattern: "go offensive" / "full damage" / "all-out attack"
    if re.search(r"(?:go\s+)?(?:offensive|full\s+damage|all-out|aggressive)", content, re.IGNORECASE):
        predicates.append(ActionPredicate("capability", "offensive focus", ("attack_majority",)))

    # Pattern: "don't attack" / "skip offense" / "no attacks"
    if re.search(r"(?:don'?t|skip|no)\s+(?:attack|offense|damage)", content, re.IGNORECASE):
        predicates.append(ActionPredicate("negative", "no attacks", ("attack",)))

    return predicates
```

##### Adherence → Evidence Mapping

| Adherence | Outcome | Classification | Weight |
|-----------|---------|---------------|--------|
| `full` | `clean` or `acceptable` | **Corroboration** (positive evidence) | 1.0 |
| `full` | `bad` or `disaster` | **Contradiction** (advice followed but failed) | 1.0 |
| `partial` | `clean` or `acceptable` | **Weak corroboration** | 0.5 |
| `partial` | `bad` or `disaster` | **Inconclusive** (can't tell if partial was the cause) | 0.0 |
| `none` | `clean` or `acceptable` | **Inconclusive** (good outcome but not because of this advice) | 0.0 |
| `none` | `bad` or `disaster` | **Corroboration via negative** (didn't follow → bad) | 1.0 |
| `unknown` | any | **Skip** — don't count this round | 0.0 |

Only rounds with `evidence_weight > 0` are counted in hypothesis re-evaluation. This prevents noisy rounds from diluting the evidence base.

### 17.11 Tool Generation Quality Control

Tools are higher-risk than skills (they execute code, affect reasoning pipeline). Apply stricter gates:

#### Tool-Specific Minimum Requirements

| Requirement | Skills | Tools |
|-------------|--------|-------|
| Positive evidence minimum | 1 round | 3 rounds across 2+ runs |
| Negative evidence minimum | 0 (but boosts score) | 1 round required |
| Cross-run validation | Optional | Required |
| Overlap check | Semantic dedup | Semantic dedup + parameter overlap |
| Test cases | N/A | 2+ with assertions (existing) |
| Applicability | Trigger conditions | `APPLICABLE_STATES` + `APPLICABLE_SITUATIONS` |

#### Tool vs Skill Decision Logic

```
Should this be a TOOL or a SKILL?

Is it a numeric CALCULATION (damage math, lethal check, energy optimization)?
  → YES: Tool (if evidence meets tool threshold)
  → NO: Continue

Is it a repeatable CLASSIFICATION (threat level, hand signature, window detection)?
  AND does it appear in 5+ situations across 3+ runs?
  → YES: Tool (stable enough to codify)
  → NO: Skill (or hypothesis)

Is it STRATEGIC ADVICE (when to do X, how to sequence)?
  → Always a Skill, never a Tool

Is it a single-enemy SPECIAL CASE?
  → Always a Skill (tools should be enemy-agnostic where possible)
```

#### Tool Rejection Rules

Do NOT generate a tool when:
- The calculation it performs is trivial (e.g., `total_damage = sum(card.damage for card in hand)` — already available via HandCapabilityTag)
- It solves a problem that occurred in only 1 run (insufficient evidence for a code artifact)
- It overlaps with an existing ToolPreprocessor state-derived tool (check parameter overlap >= 60%)
- It can be expressed as a 1-line condition in a skill trigger (e.g., `has_scaling = any(...)` — put this in SkillTrigger, not a tool)

### 17.12 Integration with Existing Architecture

#### Changes to `discovery.py`

```python
# Current flow:
#   run_data → LLM → parse_discovered_skills → add_batch to library

# New flow:
#   run_data → LLM (revised prompt requiring evidence) → parse_candidates
#   → collect_evidence(candidate, run_episodes, stores) → score
#   → classify → confirmed: add to library | hypothesis: save to hypotheses.jsonl | rejected: log

async def discover_skills(
    run_state: RunState,
    existing_skills: list[Skill] | None = None,
    *,
    # NEW parameters
    combat_store: CombatMemoryStore | None = None,
    rule_store: RuleStore | None = None,
    current_run_episodes: list[CombatEpisode] | None = None,
) -> tuple[list[Skill], list[SkillEvidenceCard]]:
    """Returns (confirmed_skills, all_evidence_cards) for audit trail."""
```

#### Changes to `evolution_engine.py`

The `_handle_write_skill` method gains a pre-check:

```python
def _handle_write_skill(self, tool_input: dict) -> str:
    # ... existing validation ...

    # NEW: Evidence collection before accepting
    evidence = collect_evidence_for_evolution_candidate(
        tool_input,
        self._memory_manager,
        self._skill_library,
    )

    if evidence.candidacy_score < HYPOTHESIS_THRESHOLD:
        reason = evidence.rejection_reason or "insufficient evidence"
        _log_rejected(tool_input, evidence)
        return f"REJECTED: {reason}. Candidacy score: {evidence.candidacy_score:.1f} (need >= {HYPOTHESIS_THRESHOLD})"

    if evidence.candidacy_score < CONFIRMED_THRESHOLD:
        _save_hypothesis(tool_input, evidence)
        return (
            f"SAVED AS HYPOTHESIS (score {evidence.candidacy_score:.1f}, "
            f"need {CONFIRMED_THRESHOLD} for confirmation). "
            "Will be re-evaluated in future runs with more evidence."
        )

    # Score is high enough — proceed with existing skill creation flow
    # ... existing skill creation code ...
```

#### Changes to `loop.py` post-run

```python
async def _post_run_skill_update(self) -> None:
    # ... existing code ...

    # NEW: Re-evaluate pending hypotheses against this run's data
    if self._memory:
        promoted = await self._reevaluate_hypotheses(current_run_episodes)
        if promoted:
            logger.info("Promoted %d hypotheses to confirmed skills", len(promoted))
```

#### New Files

| File | Purpose |
|------|---------|
| `src/skills/evidence.py` | `SkillEvidenceCard`, `RoundExemplar`, `collect_evidence()`, `score_candidate()`, `classify_candidate()` |
| `src/skills/dedup.py` | `trigger_overlap()`, `content_overlap()`, `is_semantic_duplicate()`, `common_knowledge_score()`, `is_seed_restatement()` |
| `src/skills/hypothesis_store.py` | JSONL store for candidate hypotheses, re-evaluation logic |

### 17.13 Implementation Phasing

This quality control work should be interleaved with the situation-level retrieval phases:

#### Phase 1.5 (alongside Phase 2): Evidence Gate MVP

**Scope**: Add evidence collection + scoring to discovery.py. Reject low-evidence candidates. Log all decisions.

**Files**:
- `src/skills/evidence.py` (new) — evidence card, scoring, classification
- `src/skills/dedup.py` (new) — semantic dedup, common knowledge detection
- `src/skills/discovery.py` — revised prompt, evidence pipeline integration
- `config.py` — `CONFIRMED_THRESHOLD`, `HYPOTHESIS_THRESHOLD`

**Expected benefit**:
- 60-70% reduction in low-quality skill generation
- Audit trail for every generation decision

**Risk**: LLM may struggle to provide evidence references in the required format. Mitigation: fall back to local-only evidence collection if LLM output lacks references.

#### Phase 2.5 (alongside Phase 3): Hypothesis Store + Re-evaluation

**Scope**: Implement hypothesis lifecycle. Store unconfirmed candidates. Re-evaluate across runs.

**Files**:
- `src/skills/hypothesis_store.py` (new) — JSONL persistence, re-evaluation
- `src/agent/loop.py` — wire hypothesis re-evaluation into post-run
- `src/brain/evolution_engine.py` — evidence gate in `_handle_write_skill`

**Expected benefit**:
- Skills that survive multiple runs are genuinely useful
- False positives caught before polluting the prompt

#### Phase 3.5: Tool Generation Gates

**Scope**: Apply evidence requirements to `author_tool`. Require cross-run validation for tools.

**Files**:
- `src/brain/evolution_engine.py` — evidence gate in `_handle_author_tool`
- `src/skills/evidence.py` — tool-specific scoring (higher thresholds)

### 17.14 Metrics

Track generation quality over time:

| Metric | How | Target |
|--------|-----|--------|
| Generation rate | skills_generated / runs | Decrease by 50%+ |
| Confirmation rate | confirmed / (confirmed + hypothesis + rejected) | 20-30% (most should be hypothesis or rejected) |
| Hypothesis promotion rate | promoted / total_hypotheses | 30-50% (if lower, thresholds too loose) |
| Hypothesis expiry rate | expired / total_hypotheses | 40-60% (most hypotheses should NOT become skills) |
| Skill churn | deactivated_in_30_days / active_skills | Decrease (fewer bad skills = less churn) |
| Prompt noise reduction | irrelevant_skills_injected / total_injected | Decrease by 40%+ |

---

## Appendix B: Skill vs Tool vs Hypothesis Decision Tree

```
                    Candidate Proposed
                          |
                    Collect Evidence
                          |
              +-----------+-----------+
              |                       |
         Is it a                 Is it
         numeric                strategic
         calculation?           advice?
              |                       |
         [YES: Tool path]       [Skill path]
              |                       |
         3+ rounds,             Evidence gate:
         2+ runs,               positive + negative
         cross-run              examples?
         validated?                   |
              |                  +----+----+
         [YES]  [NO]            |         |
           |      |          [YES]     [NO]
         Tool   Reject        |          |
                or Skill    Score >= 4?  Score >= 2?
                              |            |
                         [YES] [NO]   [YES]  [NO]
                           |     |      |      |
                      confirmed hypothesis  rejected
                         skill
```

---

## Appendix C: Example Evidence Card

```yaml
candidate_name: "Weak_before_block_on_Fuzzy_Wurm_burst"
candidate_content: "When facing Fuzzy Wurm at high-threat attack round with can_apply_weak + can_block_8+: apply Weak first, then block. Reduces effective incoming by ~25%."
candidate_trigger:
  enemy_names: ["Fuzzy Wurm Crawler"]
  threat_levels: ["high", "lethal"]
  requires_hand_capabilities: ["can_apply_weak"]

positive_examples:
  - episode_id: "abc123"
    round_num: 3
    threat_level: "high"
    intent_class: "attack"
    hand_capabilities_summary: "can_apply_weak, can_block_8+"
    cards_played: ["Neutralize", "Defend+", "Defend"]
    damage_taken: 5
    outcome_quality: "acceptable"
    relevance_note: "Applied Weak first, then blocked. Incoming reduced from 18 to 13, block absorbed 8. Net damage 5."

  - episode_id: "def456"
    round_num: 3
    threat_level: "high"
    cards_played: ["Neutralize", "Backflip", "Defend"]
    damage_taken: 3
    outcome_quality: "clean"
    relevance_note: "Weak + high block hand. Only took 3 damage despite 18 base incoming."

negative_examples:
  - episode_id: "ghi789"
    round_num: 3
    threat_level: "high"
    hand_capabilities_summary: "can_apply_weak, can_deal_12+"
    cards_played: ["Strike", "Strike", "Dagger Spray"]
    damage_taken: 18
    outcome_quality: "disaster"
    relevance_note: "Had Weak in hand but chose offense. Took full 18 damage. Died 2 rounds later."

supporting_memory_refs: ["abc123", "def456", "jkl012"]
contradicting_examples: []
overlapping_skill_ids: []
overlap_type: "novel"
is_system_prompt_knowledge: false

evidence_support_score: 0.7    # 2 positive in current run (0.7 * 2.0 = 1.4)
negative_case_score: 0.5       # 1 strong negative (0.5 * 1.5 = 0.75)
cross_run_support_score: 0.3   # 1 supporting episode from memory (0.3 * 1.0 = 0.3)
novelty_score: 0.8             # new: Weak-first sequencing for specific enemy (0.8 * 1.0 = 0.8)
execution_clarity_score: 0.8   # specific: enemy + threat + hand + sequence (0.8 * 0.5 = 0.4)
overlap_penalty: 0.0           # no overlap (0.0 * 2.0 = 0.0)
common_knowledge_penalty: 0.18 # keyword overlap 0.6 with "weak_reduces_damage" BUT trigger
                               # specificity 0.7 (enemy+threat+hand_cap) → capped:
                               # min(0.6 * (1.0 - 0.7), 0.3) = 0.18 (0.18 * 2.0 = -0.36)

# candidacy_score = 1.4 + 0.75 + 0.3 + 0.8 + 0.4 - 0.0 - 0.36 = 3.29
# 3.29 < CONFIRMED_THRESHOLD (4.0) → saved as candidate_hypothesis
# Also: has_negative=true but score < 4.0 → candidate regardless
# After 2 more runs corroborate (cross_run_support_score → 0.8, evidence → 0.8):
# revised score ≈ 4.2 + has_negative → promoted to confirmed_skill
candidacy_score: 3.29
decision: "candidate"  # will be promoted after cross-run corroboration
```
