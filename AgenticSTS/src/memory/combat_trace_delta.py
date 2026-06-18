"""Snapshot-diff primitives for combat trace delta rendering.

Pure module. No I/O, no LLM, no global state.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass(frozen=True)
class PowerDelta:
    """A power that newly appeared in post-snapshot."""
    name: str
    amount: int
    description: str


@dataclass(frozen=True)
class CardDelta:
    """A card that appeared in post.hand and was not played from pre."""
    name: str
    rules_text: str
    energy_cost: object  # int or None or "?"
    card_type: str


@dataclass(frozen=True)
class EnemyDelta:
    """Per-enemy diff between pre and post."""
    id: str
    name: str
    hp_pre: int
    hp_post: int
    killed: bool
    intent_pre: str
    intent_post: str
    powers_added: tuple[PowerDelta, ...]
    powers_stack_changed: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class BlockDelta:
    """Structured diff for a plan block."""
    player_energy: tuple[int, int] | None  # (pre, post)
    player_block: tuple[int, int] | None
    player_hp: tuple[int, int] | None
    player_powers_added: tuple[PowerDelta, ...] = ()
    player_powers_stack_changed: tuple[tuple[str, int, int], ...] = ()
    player_powers_removed: tuple[str, ...] = ()
    hand_added: tuple[CardDelta, ...] = ()
    drew_count: int = 0
    enemies: tuple[EnemyDelta, ...] = ()


def _player(snapshot: dict) -> dict:
    return ((snapshot or {}).get("combat") or {}).get("player") or {}


def _enemies(snapshot: dict) -> list[dict]:
    return ((snapshot or {}).get("combat") or {}).get("enemies") or []


# Indentation constants for the Δ section. The trace renderer embeds Δ
# inside plan-block output, so these align with the plan-block format
# in combat_trace_plan_grouper.format_plan_block_text.
_DELTA_HEADER_INDENT = " " * 6   # "      Δ:"
_DELTA_SECTION_INDENT = " " * 8  # "        Player:" / "Hand:" / "<Enemy>:"
_DELTA_ITEM_INDENT = " " * 10    # "          +power ..." / "          +1 Card ..."


def _card_render_name(card: dict) -> str:
    """Match the renderer's existing rule (_format_hand_card_line)."""
    name = card.get("name") or "?"
    if card.get("upgraded"):
        name = name + "+"
    enchant = card.get("enchantment_name") or ""
    if enchant:
        name = f"{name} [{enchant}]"
    return name


def _power_diff(
    pre_powers: list[dict], post_powers: list[dict],
) -> tuple[list[PowerDelta], list[tuple[str, int, int]], list[str]]:
    pre_by_name = {p.get("name"): p for p in pre_powers if p.get("name")}
    post_by_name = {p.get("name"): p for p in post_powers if p.get("name")}
    added: list[PowerDelta] = []
    stack_changed: list[tuple[str, int, int]] = []
    removed: list[str] = []
    for name, post_p in post_by_name.items():
        if name not in pre_by_name:
            added.append(PowerDelta(
                name=name,
                amount=int(post_p.get("amount", 0) or 0),
                description=post_p.get("description") or "",
            ))
        else:
            pre_amt = int(pre_by_name[name].get("amount", 0) or 0)
            post_amt = int(post_p.get("amount", 0) or 0)
            if pre_amt != post_amt:
                stack_changed.append((name, pre_amt, post_amt))
    for name in pre_by_name:
        if name not in post_by_name:
            removed.append(name)
    return added, stack_changed, removed


def _hand_diff(
    pre_hand: list[dict], post_hand: list[dict], played_cards: list[str],
) -> list[CardDelta]:
    """Return cards present in post.hand that were not in pre.hand and were
    not played from pre (so they are net additions from card-gen / draws)."""
    pre_count = Counter(_card_render_name(c) for c in pre_hand)
    played_count = Counter(played_cards)
    # Cards "available before the block": pre.hand minus played
    pre_available = pre_count.copy()
    pre_available.subtract(played_count)
    # Anything in post.hand that exceeds pre_available is a net addition
    post_count = Counter(_card_render_name(c) for c in post_hand)
    post_card_objs: dict[str, dict] = {}
    for c in post_hand:
        post_card_objs.setdefault(_card_render_name(c), c)
    added: list[CardDelta] = []
    for name, post_n in post_count.items():
        delta = post_n - max(0, pre_available.get(name, 0))
        if delta > 0:
            obj = post_card_objs.get(name, {})
            for _ in range(delta):
                added.append(CardDelta(
                    name=name,
                    rules_text=obj.get("rules_text") or obj.get("description") or "",
                    energy_cost=obj.get("energy_cost"),
                    card_type=obj.get("card_type") or obj.get("type") or "?",
                ))
    return added


def _format_enemy_intent(enemy: dict) -> str:
    """Render an enemy's intent as a single string.

    Handles both production schema (`intents: [{type, label, damage, hits,
    total_damage}, ...]`) and legacy/test schema (`intent: "Attack 8"`).
    Returns "" if neither is present.
    """
    if not enemy:
        return ""
    legacy = enemy.get("intent")
    if isinstance(legacy, str) and legacy:
        return legacy
    intents = enemy.get("intents") or []
    if not intents:
        return ""
    parts: list[str] = []
    for i in intents:
        if not isinstance(i, dict):
            continue
        label = i.get("label") or i.get("type") or ""
        total = i.get("total_damage")
        hits = i.get("hits")
        if total is not None and hits and hits > 1:
            label = f"{label} {total} ({hits} hits)" if label else f"{total} ({hits} hits)"
        elif total is not None:
            label = f"{label} {total}" if label else str(total)
        if label:
            parts.append(label.strip())
    return ", ".join(parts)


def _enemy_diff(pre_enemies: list[dict], post_enemies: list[dict]) -> list[EnemyDelta]:
    post_by_id = {e.get("enemy_id"): e for e in post_enemies if e.get("enemy_id") is not None}
    out: list[EnemyDelta] = []
    for pre_e in pre_enemies:
        eid = pre_e.get("enemy_id")
        post_e = post_by_id.get(eid)
        if post_e is None:
            out.append(EnemyDelta(
                id=str(eid), name=pre_e.get("name") or "?",
                hp_pre=int(pre_e.get("hp", 0) or 0), hp_post=0, killed=True,
                intent_pre=_format_enemy_intent(pre_e),
                intent_post="", powers_added=(), powers_stack_changed=(),
            ))
            continue
        hp_pre = int(pre_e.get("hp", 0) or 0)
        hp_post = int(post_e.get("hp", 0) or 0)
        killed = hp_post <= 0
        added, stack_changed, _removed = _power_diff(
            pre_e.get("powers") or [], post_e.get("powers") or [],
        )
        out.append(EnemyDelta(
            id=str(eid), name=post_e.get("name") or pre_e.get("name") or "?",
            hp_pre=hp_pre, hp_post=hp_post, killed=killed,
            intent_pre=_format_enemy_intent(pre_e),
            intent_post=_format_enemy_intent(post_e),
            powers_added=tuple(added),
            powers_stack_changed=tuple(stack_changed),
        ))
    # Enemies that exist in post but not pre (summoned mid-block)
    pre_ids = {e.get("enemy_id") for e in pre_enemies}
    for post_e in post_enemies:
        if post_e.get("enemy_id") not in pre_ids:
            out.append(EnemyDelta(
                id=str(post_e.get("enemy_id")), name=post_e.get("name") or "?",
                hp_pre=int(post_e.get("hp", 0) or 0),
                hp_post=int(post_e.get("hp", 0) or 0),
                killed=False, intent_pre="", intent_post=_format_enemy_intent(post_e),
                powers_added=(), powers_stack_changed=(),
            ))
    return out


@dataclass
class FirstAppearanceTracker:
    """Per-combat set of card/power names already shown with description.

    Names already in the set render as bare names; new names render with
    description and are added to the set.
    """
    seen_cards: set[str] = field(default_factory=set)
    seen_powers: set[str] = field(default_factory=set)

    @classmethod
    def from_starting_state(
        cls, starting_hand: list[dict], starting_powers: list[dict],
    ) -> "FirstAppearanceTracker":
        t = cls()
        for c in starting_hand or []:
            if not isinstance(c, dict):
                continue
            t.seen_cards.add(_card_render_name(c))
        for p in starting_powers or []:
            if not isinstance(p, dict):
                continue
            name = p.get("name")
            if name:
                t.seen_powers.add(name)
        return t

    def has_seen_card(self, name: str) -> bool:
        return name in self.seen_cards

    def has_seen_power(self, name: str) -> bool:
        return name in self.seen_powers

    def mark_card_seen(self, name: str) -> None:
        self.seen_cards.add(name)

    def mark_power_seen(self, name: str) -> None:
        self.seen_powers.add(name)


def _format_card_description(card: CardDelta) -> str:
    """Render '<name> (<type>, cost=<c>): <rules>' (omits ': <rules>' when empty)."""
    cost_str = "?" if card.energy_cost is None else str(card.energy_cost)
    rules = card.rules_text or ""
    suffix = f": {rules}" if rules else ""
    return f"{card.name} ({card.card_type}, cost={cost_str}){suffix}"


def _collapse_hand_added(
    hand_added: tuple[CardDelta, ...], tracker: FirstAppearanceTracker,
) -> list[str]:
    """Group identical CardDelta entries and emit '+K <name>' (with optional
    description on first appearance) per group."""
    # Group by name (preserve insertion order)
    by_name: dict[str, list[CardDelta]] = {}
    for c in hand_added:
        by_name.setdefault(c.name, []).append(c)

    lines: list[str] = []
    for name, group in by_name.items():
        count = len(group)
        prefix = f"+{count} {name}" if count > 1 else f"+{name}"
        if not tracker.has_seen_card(name):
            desc = _format_card_description(group[0])
            tracker.mark_card_seen(name)
            lines.append(f"{prefix} — {desc}")
        else:
            lines.append(prefix)
    return lines


def format_block_delta(
    delta: BlockDelta | None, tracker: FirstAppearanceTracker,
) -> str:
    """Render BlockDelta to text. Returns empty string if no fields changed.

    Mutates ``tracker``: every card and power name encountered is marked as
    seen (whether or not its description was emitted). Subsequent blocks in
    the same combat will use the updated tracker state to suppress repeat
    descriptions.
    """
    if delta is None:
        return ""

    player_bits: list[str] = []
    if delta.player_energy is not None:
        player_bits.append(f"energy {delta.player_energy[0]}→{delta.player_energy[1]}")
    if delta.player_block is not None:
        player_bits.append(f"block {delta.player_block[0]}→{delta.player_block[1]}")
    if delta.player_hp is not None:
        player_bits.append(f"hp {delta.player_hp[0]}→{delta.player_hp[1]}")
    if delta.drew_count > 0:
        player_bits.append(f"drew {delta.drew_count}")

    power_lines: list[str] = []
    for p in delta.player_powers_added:
        head = f"+power {p.name}({p.amount})"
        if p.description and not tracker.has_seen_power(p.name):
            tracker.mark_power_seen(p.name)
            power_lines.append(f"{head} — {p.description}")
        else:
            tracker.mark_power_seen(p.name)
            power_lines.append(head)
    for name, pre_amt, post_amt in delta.player_powers_stack_changed:
        power_lines.append(f"{name}({pre_amt})→({post_amt})")
    for name in delta.player_powers_removed:
        power_lines.append(f"-power {name}")

    hand_lines = _collapse_hand_added(delta.hand_added, tracker)

    enemy_lines: list[str] = []
    for e in delta.enemies:
        head = f"{e.name}: {e.hp_pre}→{e.hp_post} HP"
        if e.hp_pre != e.hp_post:
            diff = e.hp_post - e.hp_pre
            head += f" ({diff:+d})"
        if e.killed:
            head += " (killed)"
        if e.intent_pre and e.intent_post:
            if e.intent_pre == e.intent_post:
                head += f", intent unchanged ({e.intent_pre})"
            else:
                head += f", intent {e.intent_pre}→{e.intent_post}"
        enemy_lines.append(head)
        for p in e.powers_added:
            head2 = f"  +power {p.name}({p.amount})"
            if p.description and not tracker.has_seen_power(p.name):
                tracker.mark_power_seen(p.name)
                head2 += f" — {p.description}"
            else:
                tracker.mark_power_seen(p.name)
            enemy_lines.append(head2)
        for name, pre_amt, post_amt in e.powers_stack_changed:
            enemy_lines.append(f"  {name}({pre_amt})→({post_amt})")

    out_lines: list[str] = []
    if player_bits or power_lines:
        if player_bits:
            out_lines.append(f"{_DELTA_SECTION_INDENT}Player: " + ", ".join(player_bits))
        else:
            out_lines.append(f"{_DELTA_SECTION_INDENT}Player:")
        for pl in power_lines:
            out_lines.append(_DELTA_ITEM_INDENT + pl)
    if hand_lines:
        out_lines.append(f"{_DELTA_SECTION_INDENT}Hand:")
        for hl in hand_lines:
            out_lines.append(_DELTA_ITEM_INDENT + hl)
    if enemy_lines:
        for el in enemy_lines:
            out_lines.append(_DELTA_SECTION_INDENT + el)

    if not out_lines:
        return ""
    return f"{_DELTA_HEADER_INDENT}Δ:\n" + "\n".join(out_lines)


def compute_block_delta(
    pre_snapshot: dict | None, post_snapshot: dict | None,
    played_cards: list[str],
) -> BlockDelta | None:
    """Compute structured diff for a plan block. Returns None if either
    snapshot is missing or malformed."""
    if pre_snapshot is None or post_snapshot is None:
        return None
    pre_p = _player(pre_snapshot)
    post_p = _player(post_snapshot)
    if not pre_p or not post_p:
        return None

    pre_e_amount = int(pre_p.get("energy", 0) or 0)
    post_e_amount = int(post_p.get("energy", 0) or 0)
    pre_block = int(pre_p.get("block", 0) or 0)
    post_block = int(post_p.get("block", 0) or 0)
    pre_hp = int(pre_p.get("hp", 0) or 0)
    post_hp = int(post_p.get("hp", 0) or 0)

    powers_added, powers_stack, powers_removed = _power_diff(
        pre_p.get("powers") or [], post_p.get("powers") or [],
    )
    hand_added = _hand_diff(
        pre_p.get("hand") or [], post_p.get("hand") or [], played_cards,
    )
    # Production schema: combat.draw_pile_size is a scalar at combat root.
    # Fall back to len(player.draw_pile) for legacy/test fixtures that pass a list.
    pre_combat = (pre_snapshot or {}).get("combat") or {}
    post_combat = (post_snapshot or {}).get("combat") or {}
    pre_draw_n = pre_combat.get("draw_pile_size")
    if pre_draw_n is None:
        pre_draw_n = len(pre_p.get("draw_pile") or [])
    post_draw_n = post_combat.get("draw_pile_size")
    if post_draw_n is None:
        post_draw_n = len(post_p.get("draw_pile") or [])
    # Approximation: counts how many cards left the draw pile this block.
    # Under-counts when a discard→draw reshuffle occurs mid-block (the new
    # cards refill draw_pile, masking the actual draw count). Reshuffle
    # detection would require tracking discard pile size; deferred.
    drew_count = max(0, int(pre_draw_n or 0) - int(post_draw_n or 0))

    return BlockDelta(
        player_energy=(pre_e_amount, post_e_amount) if pre_e_amount != post_e_amount else None,
        player_block=(pre_block, post_block) if pre_block != post_block else None,
        player_hp=(pre_hp, post_hp) if pre_hp != post_hp else None,
        player_powers_added=tuple(powers_added),
        player_powers_stack_changed=tuple(powers_stack),
        player_powers_removed=tuple(powers_removed),
        hand_added=tuple(hand_added),
        drew_count=drew_count,
        enemies=tuple(_enemy_diff(_enemies(pre_snapshot), _enemies(post_snapshot))),
    )
