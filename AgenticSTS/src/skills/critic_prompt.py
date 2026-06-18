"""Critic prompt builder for mistake-driven skill discovery.

Spec references:
- §2.2 (round snapshot layout)
- §3.2 (full critic prompt template, added in Task C4)
- §3.4 (validator rules, added in Task C5)
"""
from __future__ import annotations

from src.memory.models_v2 import CombatEpisode, CombatRound


def format_combat_header(ep: CombatEpisode) -> str:
    """Format per-combat context (encounter type / act / floor / deck / relics /
    enemy lineup) as the top block of the critic snapshot.

    Falls back gracefully when CombatEpisode.context is absent — older
    episodes may lack full deck/enemy snapshots.
    """
    ctx = ep.context
    lines: list[str] = []
    lines.append("## Combat Start")
    lines.append(f"encounter_type: {ep.combat_type}")
    lines.append(f"act: {ep.act} | floor: {ep.floor}")
    lines.append(f"character: {ep.character} | hp_before: {ep.hp_before}")

    # Relics: use episode.relics (tuple[str] of "Name (desc)") if present
    if ep.relics:
        lines.append("")
        lines.append("## Relics")
        for r in ep.relics:
            lines.append(f"- {r}")

    # Deck (from context.deck_cards if available)
    if ctx is not None and getattr(ctx, "deck_cards", None):
        lines.append("")
        lines.append(f"## Current Deck ({len(ctx.deck_cards)} cards)")
        lines.append("  " + ", ".join(sorted(ctx.deck_cards)))

    # Enemies
    if ctx is not None and getattr(ctx, "enemy_lineup", None):
        lines.append("")
        lines.append("## Enemies (at combat start)")
        for i, en in enumerate(ctx.enemy_lineup):
            name = getattr(en, "name", str(en))
            hp = getattr(en, "hp", "?")
            maxhp = getattr(en, "max_hp", "?")
            lines.append(f"- {name} [index={i}]: HP {hp}/{maxhp}")

    return "\n".join(lines)


def format_round_snapshot(r: CombatRound) -> str:
    """Format one CombatRound as a ### Round N block for critic consumption.

    Mirrors the layout the live agent sees in the combat prompt, so the
    critic can reason counterfactually about what the agent COULD have
    done with the SAME hand/energy/intents/potions (§3.2 of spec).
    """
    lines: list[str] = []
    lines.append(f"### Round {r.round_num}")

    # Energy total = available + used (so the critic knows max energy this turn)
    lines.append(
        f"State: Energy {r.energy_available}/{r.energy_available + r.energy_used}, "
        f"HP {r.hp_start}, Block {r.block_before}"
    )

    if r.hand_at_start:
        lines.append(f"Hand: {', '.join(r.hand_at_start)} ({len(r.hand_at_start)} playable)")
    else:
        lines.append("Hand: (empty)")

    lines.append(
        f"Piles: Draw {r.draw_pile_size} | Discard {r.discard_pile_size} | "
        f"Exhaust {r.exhaust_pile_size}"
    )

    if r.usable_potions:
        lines.append(f"Usable Potions: {', '.join(r.usable_potions)}")

    if r.enemy_intents:
        lines.append(f"Enemy intents: {' | '.join(r.enemy_intents)}")

    lines.append(f"Incoming: {r.incoming_damage}")

    if r.agent_plan:
        lines.append(f"Agent plan: [{', '.join(r.agent_plan)}]")

    # Outcome classification matches short_term.CombatTracker._classify_outcome
    if r.damage_taken == 0:
        quality = "clean"
    elif r.damage_taken < 8:
        quality = "acceptable"
    else:
        quality = "ugly"
    lines.append(
        f"Outcome: damage_taken={r.damage_taken}, hp_after={r.hp_end}, quality={quality}"
    )

    return "\n".join(lines)


_CRITIC_BODY = """You are a Slay the Spire 2 critic. One past combat underperformed.
Decide if a reusable SKILL would have helped, OR if it was unavoidable.

## Counterfactual Test (MANDATORY)
For each round where HP was lost or a better play existed:
1. What did agent actually do? (see "Agent plan")
2. What COULD agent have done with the SAME hand/energy/intents/potions?
3. Would an average STS2 player naturally make the better choice from
   game mechanics alone, or would they need explicit guidance?

Decision rules:
- Agent's plan was already optimal for this hand/energy/intent     -> no_skill_needed, reason="bad_luck"
- Better play existed but required mechanic never surfaced by game -> no_skill_needed, reason="unavoidable_mechanic"
- The "fix" would just describe enemy rhythm without a concrete    -> no_skill_needed, reason="descriptive_rhythm"
  corrective card/target pick agent should have made
- Better play existed AND a reusable rule would catch it next time -> skill_needed

## Skill Scope (if you propose one)
The skill must GENERALIZE across future combats AND be PRESCRIPTIVE.
- GOOD: "vs {enemy}, do X" / "vs {enemy}, do NOT do Y"
- GOOD: "holding {card}, use it as X"
- BAD:  "vs {enemy} turn 1 play Strike then Defend" (hand/intent RNG)
- BAD:  anything already obvious from card text or enemy intent display

## HARD BOUNDARY - Skill vs Memory (descriptive rhythm is NOT a skill)
If your proposed "skill" is a turn-by-turn description of how the enemy behaves
with no concrete correction, REJECT and return reason="descriptive_rhythm".
Litmus: would agent have picked a DIFFERENT card/target on the failing round
if this skill were in its prompt? If no -> descriptive_rhythm.

Content budget: <=80 words, prescriptive tone, cite trigger conditions inline.
If skill_needed, you MUST list the round indices where the mistake happened
in mistake_round_indices and write what the agent SHOULD have done in
expected_correction (<=30 words).

## Output (strict JSON, no prose before or after)
{
  "analysis": "2-3 sentences on what went wrong",
  "decision": "skill_needed" | "no_skill_needed",
  "reason": "bad_luck" | "unavoidable_mechanic" | "descriptive_rhythm" | "skill_would_help",
  "skill": null | {
    "name": "<=8 words",
    "content": "<=80 words prescriptive rule",
    "category": "combat" | "boss" | "map" | "event" | "rest" | "deck_building" | "shop",
    "trigger": {
      "state_types": [...], "enemy_names": [...], "character": "silent" | null,
      "min_act": 1|2|3 | null, "max_act": 1|2|3 | null,
      "requires_cards": [...], "requires_hand_capabilities": [...],
      "hp_below": 0.0-1.0 | null, "hp_above": 0.0-1.0 | null,
      "any_of_relics": [...], "requires_enemy_powers": [...]
    },
    "counterfactual_note": "1 sentence",
    "mistake_round_indices": [int, ...],
    "expected_correction": "<=30 words"
  }
}
"""


def build_critic_prompt(
    ep: CombatEpisode,
    *,
    baseline_a: float | None,
    baseline_b: float | None,
    n_a: int,
    n_b: int,
) -> str:
    """Build the full critic prompt for one mistake episode (spec §3.2).

    Includes mistake signal (baselines + actual loss), full combat
    context from §2.2, and the HARD BOUNDARY rule forcing descriptive
    rhythm rejections.
    """
    from src.skills.mistake_discovery import loss_ratio  # local import avoids cycle

    actual = loss_ratio(ep)
    ba_str = f"{baseline_a:.2f}" if baseline_a is not None else "n/a"
    bb_str = f"{baseline_b:.2f}" if baseline_b is not None else "n/a"
    da = f"{actual - baseline_a:+.2f}" if baseline_a is not None else "n/a"
    db = f"{actual - baseline_b:+.2f}" if baseline_b is not None else "n/a"

    header = (
        "## Mistake Signal\n"
        f"- Enemy: {ep.enemy_key} ({ep.combat_type}, act {ep.act}, character {ep.character})\n"
        f"- This run: loss_ratio = {actual:.2f}  ({ep.total_damage_taken} damage on {ep.hp_before} HP)\n"
        f"- Baseline A (this enemy, historical median over N={n_a} fights): {ba_str}\n"
        f"- Baseline B (act {ep.act} x {ep.combat_type} x {ep.character}, last {n_b}): {bb_str}\n"
        f"- Exceeded: A by {da} | B by {db}\n"
    )
    round_traces = "\n\n".join(format_round_snapshot(r) for r in ep.rounds)
    combat_section = (
        format_combat_header(ep) + "\n\n## Per-Round Trace\n" + round_traces
    )
    return f"{_CRITIC_BODY}\n\n{header}\n{combat_section}\n"


# ---------------------------------------------------------------------------
# §3.4 validator
# ---------------------------------------------------------------------------

import re
from dataclasses import dataclass


_CANONICAL_CATEGORIES = frozenset({
    "combat", "boss", "map", "event", "rest", "deck_building", "shop",
})
_CANONICAL_STATES = frozenset({
    "monster", "elite", "boss", "shop", "event", "rest_site",
    "map", "card_reward", "treasure",
})
# Imperative cue words: if none of these appear in content, the content
# is probably descriptive rhythm. Multi-word entries are checked as substrings;
# single-word entries are matched against tokenized words.
_IMPERATIVE_CUES = frozenset({
    "do", "don", "do not", "avoid", "prefer", "use", "save", "skip",
    "play", "block", "target", "hold", "never", "always",
})
_DESCRIPTIVE_RE = re.compile(
    r"(attacks on|buffs on|follows .* pattern|consistently (opens|alternates)|safe window)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CriticResult:
    """Outcome of parse_and_validate_critic_output.

    decision is 'skill_needed' only when every §3.4 check passes. Anything
    else collapses to 'no_skill_needed' with reason explaining why.
    """
    decision: str               # "skill_needed" | "no_skill_needed"
    reason: str                 # canonical reason string
    skill: dict | None          # validated skill sub-dict, or None when rejected
    rejection_reason: str = ""  # human-readable detail (empty when accepted)


def _has_imperative_cue(content: str) -> bool:
    """True if content contains at least one imperative cue word."""
    content_lower = content.lower()
    tokens = set(re.findall(r"[A-Za-z']+", content_lower))
    for cue in _IMPERATIVE_CUES:
        if " " in cue:
            if cue in content_lower:
                return True
        elif cue in tokens:
            return True
    return False


def _reject(reason: str, rejection_reason: str = "") -> CriticResult:
    return CriticResult(
        decision="no_skill_needed",
        reason=reason,
        skill=None,
        rejection_reason=rejection_reason or reason,
    )


def parse_and_validate_critic_output(
    output: dict,
    *,
    enemy_name: str,
    character: str,
    round_count: int,
    round_llm_call_seqs: list[int],
) -> CriticResult:
    """Apply spec §3.4 validator to a parsed critic JSON payload.

    Arguments:
        output: parsed JSON from the critic (already `json.loads`'d).
        enemy_name: ep.enemy_key — used for enemy-overlap check.
        character: ep.character — used for character equality check.
        round_count: total rounds in the source episode (index range).
        round_llm_call_seqs: per-round-index llm_call_seq; -1 means unrecorded
                             (can't fetch original prompt for A/B).

    Returns a CriticResult. If any validation rule fails, decision is
    'no_skill_needed' with reason explaining why (including a possible
    descriptive_rhythm relabel for content that matches the regex soft-check).
    """
    decision = output.get("decision", "")
    reason = output.get("reason", "")

    if decision == "no_skill_needed":
        return CriticResult(
            decision="no_skill_needed",
            reason=reason or "bad_luck",
            skill=None,
        )

    if decision != "skill_needed":
        return _reject("invalid_decision", f"decision={decision!r}")

    skill = output.get("skill") or {}

    # name
    name = skill.get("name", "")
    if not name or len(name) > 60:
        return _reject("invalid_name", f"name_len={len(name)}")

    # content length (word count <= 80)
    content = skill.get("content", "")
    if not content or len(content.split()) > 80:
        return _reject("invalid_content_len", f"words={len(content.split())}")

    # category
    category = skill.get("category", "")
    if category not in _CANONICAL_CATEGORIES:
        return _reject("invalid_category", category)

    trigger = skill.get("trigger") or {}

    # state_types canonical values
    state_types = trigger.get("state_types") or []
    for s in state_types:
        if s not in _CANONICAL_STATES:
            return _reject("invalid_state_type", s)

    # enemy overlap (case-insensitive substring either direction)
    enemy_names = trigger.get("enemy_names") or []
    if enemy_names:
        en_lower = enemy_name.lower()
        overlap = any(
            n.lower() in en_lower or en_lower in n.lower()
            for n in enemy_names
        )
        if not overlap:
            return _reject("enemy_mismatch", f"{enemy_names} vs {enemy_name}")

    # character equality (case-insensitive)
    tc = trigger.get("character")
    if tc is not None and tc and tc.lower() != character.lower():
        return _reject("character_mismatch", f"{tc} vs {character}")

    # at least one non-null dimension (avoid universal triggers)
    has_dim = any(
        trigger.get(k)
        for k in (
            "state_types", "enemy_names", "requires_cards",
            "requires_hand_capabilities", "any_of_relics",
            "requires_enemy_powers",
        )
    )
    if not has_dim and not (trigger.get("hp_below") or trigger.get("hp_above")):
        return _reject("universal_trigger")

    # counterfactual_note / expected_correction
    if not skill.get("counterfactual_note"):
        return _reject("missing_counterfactual_note")
    ec = skill.get("expected_correction", "")
    if not ec or len(ec.split()) > 30:
        return _reject("invalid_expected_correction")

    # mistake_round_indices — non-empty, in range, llm_call_seq present.
    # Convention: 1-based indices matching CombatRound.round_num.
    indices = skill.get("mistake_round_indices") or []
    if not indices:
        return _reject("empty_mistake_round_indices")
    for idx in indices:
        if not isinstance(idx, int) or idx < 1 or idx > round_count:
            return _reject("mistake_round_index_out_of_range", str(idx))
        seq_pos = idx - 1
        if seq_pos >= len(round_llm_call_seqs) or round_llm_call_seqs[seq_pos] < 0:
            return _reject("missing_llm_call_seq", f"round={idx}")

    # Descriptive-rhythm regex soft-check (defense-in-depth beyond the critic's own judgement)
    if _DESCRIPTIVE_RE.search(content) and not _has_imperative_cue(content):
        return CriticResult(
            decision="no_skill_needed",
            reason="descriptive_rhythm",
            skill=None,
            rejection_reason="content matched descriptive regex and lacks imperative cue",
        )

    return CriticResult(
        decision="skill_needed",
        reason=reason or "skill_would_help",
        skill=skill,
    )
