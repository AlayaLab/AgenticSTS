"""Parse decision events and group them into plan blocks for trace rendering.

Pure module: no I/O, no LLM, no global state. All public functions are
side-effect free.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal


ParsedKind = Literal["plan_step", "sub_action", "end_turn", "heuristic"]


@dataclass(frozen=True)
class ParsedReasoning:
    """Classified decision reasoning."""
    kind: ParsedKind
    raw: str
    step_idx: int = 0          # plan_step only
    plan_size: int = 0         # plan_step only
    card_name: str = ""        # plan_step only
    plan_reasoning_body: str = ""  # plan_step only


# "Plan [N/M]: <card> — <body>" — body may contain additional ' — ' separators,
# so we only split on the FIRST occurrence.
_PLAN_STEP_RE = re.compile(r"^Plan \[(\d+)/(\d+)\]:\s+(.+?)\s+—\s+(.+)$", re.DOTALL)

# Sub-action reasoning patterns produced by loop.py for hand-select / exhaust modals.
_SUB_ACTION_PREFIXES = (
    "Plan discard:",
    "Plan exhaust:",
    "Confirm hand selection",
    "Confirm selection",
    "Exhausting ",
)

_SUB_ACTION_ACTIONS = {"select_deck_card", "confirm_selection"}


def parse_reasoning(
    reasoning: str | None, action: dict | None, source: str | None,
) -> ParsedReasoning:
    """Classify a decision event's reasoning into one of four kinds."""
    text = (reasoning or "").strip()
    action_name = (action or {}).get("action", "")

    # End-turn: action authoritative
    if action_name == "end_turn":
        return ParsedReasoning(kind="end_turn", raw=text)

    # Heuristic / stuck recovery: source authoritative
    if source in {"random", "heuristic"}:
        return ParsedReasoning(kind="heuristic", raw=text)

    # Plan step: regex match on the structured prefix
    m = _PLAN_STEP_RE.match(text)
    if m:
        step_idx = int(m.group(1))
        plan_size = int(m.group(2))
        card_name = m.group(3).strip()
        body = m.group(4).strip()
        return ParsedReasoning(
            kind="plan_step", raw=text,
            step_idx=step_idx, plan_size=plan_size,
            card_name=card_name, plan_reasoning_body=body,
        )

    # Sub-action: prefix match OR action-name match
    if action_name in _SUB_ACTION_ACTIONS:
        return ParsedReasoning(kind="sub_action", raw=text)
    for prefix in _SUB_ACTION_PREFIXES:
        if text.startswith(prefix):
            return ParsedReasoning(kind="sub_action", raw=text)

    # Fallback: heuristic
    return ParsedReasoning(kind="heuristic", raw=text)


@dataclass
class ExecutedStep:
    """One executed step within a plan block: a card play with optional
    folded sub-actions (select_deck_card, confirm_selection).

    Mutable builder field — `group_decisions_into_blocks` appends to
    `sub_actions` after construction. Treat as read-only once the parent
    PlanBlock is returned.
    """
    card_name: str
    decision_step: int
    action: dict
    sub_actions: list[ParsedReasoning] = field(default_factory=list)


@dataclass
class PlanBlock:
    """A contiguous run of plan_step decisions sharing the same plan body.

    Mutable builder pattern — `group_decisions_into_blocks` assembles instances
    in place. Treat as read-only once returned from that function.

    `intended` lists the card names observed in `Plan [N/M]:` prefixes (one per
    decision in the block). `intended_size` is the original M from the prefix —
    when a plan is cut short by a replan, `len(intended) < intended_size`.
    """
    letter: str
    intended: list[str]
    plan_reasoning_body: str
    executed: list[ExecutedStep] = field(default_factory=list)
    first_step: int = -1
    last_step: int = -1
    intended_size: int = 0


@dataclass
class EndTurnBlock:
    """A standalone end_turn decision."""
    reasoning: str
    decision_step: int


@dataclass
class HeuristicBlock:
    """A standalone heuristic / stuck-recovery / unmatched decision."""
    reasoning: str
    decision_step: int
    action: dict
    source: str


Block = PlanBlock | EndTurnBlock | HeuristicBlock


def _next_letter(idx: int) -> str:
    """Map 0→A, 1→B, ..., 25→Z, 26→AA (paranoid; should not happen)."""
    if idx < 26:
        return chr(ord("A") + idx)
    first = chr(ord("A") + (idx // 26) - 1)
    second = chr(ord("A") + (idx % 26))
    return first + second


def group_decisions_into_blocks(decisions: list[dict]) -> list[Block]:
    """Walk decisions in chronological order and group into blocks.

    Boundary rules (any of these starts a new plan block):
    - plan_reasoning_body differs from current block's body
    - step_idx == 1 (counter reset = explicit replan)
    - previous block was end_turn or heuristic
    """
    blocks: list[Block] = []
    plan_block_count = 0  # for letter assignment
    current: PlanBlock | None = None

    for dec in decisions:
        parsed = parse_reasoning(
            dec.get("reasoning", ""), dec.get("action", {}) or {},
            dec.get("source", ""),
        )
        step = dec.get("step", -1)

        if parsed.kind == "plan_step":
            is_new_block = (
                current is None
                or current.plan_reasoning_body != parsed.plan_reasoning_body
                or parsed.step_idx == 1
            )
            if is_new_block:
                if current is not None:
                    blocks.append(current)
                letter = _next_letter(plan_block_count)
                plan_block_count += 1
                current = PlanBlock(
                    letter=letter,
                    intended=[parsed.card_name],
                    plan_reasoning_body=parsed.plan_reasoning_body,
                    first_step=step,
                    last_step=step,
                    intended_size=parsed.plan_size,
                )
                current.executed.append(ExecutedStep(
                    card_name=parsed.card_name,
                    decision_step=step,
                    action=dec.get("action", {}) or {},
                ))
            else:
                # Continuation of current plan block
                current.intended.append(parsed.card_name)
                current.last_step = step
                current.executed.append(ExecutedStep(
                    card_name=parsed.card_name,
                    decision_step=step,
                    action=dec.get("action", {}) or {},
                ))

        elif parsed.kind == "sub_action":
            if current is not None and current.executed:
                current.executed[-1].sub_actions.append(parsed)
                current.last_step = step
            else:
                # Orphan sub-action: emit as heuristic
                blocks.append(HeuristicBlock(
                    reasoning=parsed.raw, decision_step=step,
                    action=dec.get("action", {}) or {},
                    source=dec.get("source", "") or "",
                ))

        elif parsed.kind == "end_turn":
            if current is not None:
                blocks.append(current)
                current = None
            blocks.append(EndTurnBlock(reasoning=parsed.raw, decision_step=step))

        else:  # heuristic
            if current is not None:
                blocks.append(current)
                current = None
            blocks.append(HeuristicBlock(
                reasoning=parsed.raw, decision_step=step,
                action=dec.get("action", {}) or {},
                source=dec.get("source", "") or "",
            ))

    if current is not None:
        blocks.append(current)

    return blocks


# ---------------------------------------------------------------------------
# Text formatters (no Δ section — that is appended separately by the renderer)
# ---------------------------------------------------------------------------

def _collapse_repeated(names: list[str]) -> str:
    """Collapse runs of identical adjacent names: ['Shiv','Shiv','Shiv'] → 'Shiv×3'."""
    if not names:
        return ""
    out: list[str] = []
    i = 0
    while i < len(names):
        j = i + 1
        while j < len(names) and names[j] == names[i]:
            j += 1
        run = j - i
        out.append(f"{names[i]}×{run}" if run > 1 else names[i])
        i = j
    return ", ".join(out)


# Subset of _SUB_ACTION_PREFIXES — must stay in sync if new discard-like
# prefixes are added there.
_DISCARD_PREFIXES = ("Plan discard:", "Plan exhaust:")
_EXHAUSTING_PREFIX = "Exhausting "


def _summarize_sub_actions(sub_actions: list[ParsedReasoning]) -> str:
    """Produce a parenthetical summary like '(discarded Strike+, Defend+)' or
    '(exhausted Strike)'. Returns empty string if nothing meaningful."""
    discarded: list[str] = []
    exhausted: list[str] = []

    for sa in sub_actions:
        text = sa.raw
        if any(text.startswith(p) for p in _DISCARD_PREFIXES):
            # "Plan discard: Strike+, Defend+ (..." → "Strike+, Defend+"
            after = text.split(":", 1)[1].strip() if ":" in text else ""
            paren = after.find("(")
            if paren >= 0:
                after = after[:paren].strip().rstrip(",")
            if after:
                discarded.extend([n.strip() for n in after.split(",") if n.strip()])
        elif text.startswith(_EXHAUSTING_PREFIX):
            # "Exhausting the Strike to thin the deck." → "Strike"
            tail = text[len(_EXHAUSTING_PREFIX):].strip()
            cutoff = tail.find(" to ")
            phrase = tail[:cutoff] if cutoff != -1 else tail.rstrip(".")
            phrase = phrase.removeprefix("the ").strip()
            if phrase:
                exhausted.append(phrase)
        # confirm_selection / unrecognized → drop silently

    parts: list[str] = []
    if discarded:
        parts.append("discarded " + ", ".join(discarded))
    if exhausted:
        parts.append("exhausted " + ", ".join(exhausted))
    if not parts:
        return ""
    return "(" + "; ".join(parts) + ")"


def format_plan_block_text(block: PlanBlock) -> str:
    """Render a plan block to text WITHOUT the Δ section.

    Δ is appended separately by the renderer after computing snapshot diffs.
    Uses ``block.intended_size`` (not ``len(block.intended)``) for the K/N counts
    so cut-short plans are rendered correctly.
    """
    intended_str = _collapse_repeated(block.intended)

    # Sub-action annotations: walk executed and append paren summary inline.
    annotated: list[str] = []
    for step in block.executed:
        summary = _summarize_sub_actions(step.sub_actions) if step.sub_actions else ""
        annotated.append(f"{step.card_name} {summary}".strip())
    executed_annotated = _collapse_repeated(annotated)

    n_intended = block.intended_size
    n_executed = len(block.executed)

    lines = [
        f"  [{block.letter}] intended {n_intended} → {intended_str}",
        f"      Reason: {block.plan_reasoning_body}",
        f"      Executed {n_executed}/{n_intended}: {executed_annotated}",
    ]
    return "\n".join(lines)


_END_TURN_PREFIX = "Plan: end turn —"


def format_end_turn_block_text(block: EndTurnBlock) -> str:
    """Render an end-turn block. Strips the standard 'Plan: end turn —' prefix."""
    text = block.reasoning.strip()
    if text.startswith(_END_TURN_PREFIX):
        text = text[len(_END_TURN_PREFIX):].strip()
    return f"  [end_turn] Reason: {text}"


def format_heuristic_block_text(block: HeuristicBlock) -> str:
    """Render a heuristic / stuck-recovery block."""
    action_name = (block.action or {}).get("action", "?")
    return (
        f"  [heuristic: {block.source}] {action_name} — {block.reasoning}"
    )
