"""Combat state diff engine: computes per-action deltas between GameState snapshots.

Given pre-action and post-action GameState, produces a CombatDelta recording
exactly what changed (HP, block, energy, powers, enemy state, relic counters,
exhaust pile).  Only non-None / non-empty fields represent actual changes.

Also provides ``build_combat_context`` to capture fixed per-combat context
(relics with counters, enemy lineup with powers, deck) at combat start.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.memory.enemy_keys import normalize_enemy_key
from src.memory.models_v2 import (
    CombatContext,
    CombatDelta,
    EnemyDelta,
    EnemySnapshot,
    RelicSnapshot,
)

if TYPE_CHECKING:
    from src.mcp_client.upstream_models import RawCombatPowerPayload
    from src.state.game_state import GameState

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────


def _enemy_key(enemy) -> str:
    """Stable enemy identifier — matches loop.py ``_enemy_snapshot``."""
    return getattr(enemy, "enemy_id", "") or f"{enemy.name}:{enemy.index}"


def _format_power(p: RawCombatPowerPayload) -> str:
    """Human-readable power string, e.g. 'Thorns(2)' or 'Weak(1)'."""
    amt = p.amount
    if amt is not None and amt != 0:
        return f"{p.name}({amt})"
    return p.name


def _diff_powers(
    pre_powers: list[RawCombatPowerPayload],
    post_powers: list[RawCombatPowerPayload],
) -> tuple[str, ...]:
    """Compute power changes between two power lists.

    Returns e.g. ("+Strength(2)", "-Weak", "Vulnerable(1→2)").
    """
    pre_map: dict[str, RawCombatPowerPayload] = {p.power_id or p.name: p for p in pre_powers}
    post_map: dict[str, RawCombatPowerPayload] = {p.power_id or p.name: p for p in post_powers}

    changes: list[str] = []

    # New or changed powers
    for key, post_p in post_map.items():
        pre_p = pre_map.get(key)
        if pre_p is None:
            # New power
            changes.append(f"+{_format_power(post_p)}")
        else:
            pre_amt = pre_p.amount or 0
            post_amt = post_p.amount or 0
            if pre_amt != post_amt:
                changes.append(f"{post_p.name}({pre_amt}→{post_amt})")

    # Removed powers
    for key, pre_p in pre_map.items():
        if key not in post_map:
            changes.append(f"-{pre_p.name}")

    return tuple(changes)


def _diff_or_none(a: int, b: int) -> int | None:
    """Return delta if different, else None."""
    d = b - a
    return d if d != 0 else None


# ── Main diff function ───────────────────────────────────────────


def compute_combat_delta(
    pre: GameState,
    post: GameState,
    event_type: str,
    source: str,
    target: str | None = None,
) -> CombatDelta | None:
    """Compute state delta between pre-action and post-action states.

    Uses ``raw.combat`` presence (not ``state_type``) as the combat guard,
    so mid-combat phases like ``hand_select`` / ``card_select`` are covered.
    Also handles cross-phase transitions (combat → reward / game_over).

    Returns None if neither state has combat data.
    """
    pre_combat = pre.raw.combat if pre.raw else None
    post_combat = post.raw.combat if post.raw else None

    if pre_combat is None and post_combat is None:
        return None

    # ── Player deltas ────────────────────────────────────────────
    pre_hp = pre_combat.player.current_hp if pre_combat else (pre.raw.run.current_hp if pre.raw.run else 0)
    post_hp = post_combat.player.current_hp if post_combat else (post.raw.run.current_hp if post.raw.run else 0)

    pre_block = pre_combat.player.block if pre_combat else 0
    post_block = post_combat.player.block if post_combat else 0

    pre_energy = pre_combat.player.energy if pre_combat else 0
    post_energy = post_combat.player.energy if post_combat else 0

    hp_delta = _diff_or_none(pre_hp, post_hp)
    block_delta = _diff_or_none(pre_block, post_block)
    energy_delta = _diff_or_none(pre_energy, post_energy)

    # ── Player power diff ────────────────────────────────────────
    pre_player_powers = list(pre_combat.player.powers) if pre_combat else []
    post_player_powers = list(post_combat.player.powers) if post_combat else []

    powers_changed: tuple[str, ...] = ()
    if pre_player_powers or post_player_powers:
        powers_changed = _diff_powers(pre_player_powers, post_player_powers)

    # ── Per-enemy diff ───────────────────────────────────────────
    pre_enemies_map: dict[str, object] = {}
    if pre_combat:
        for e in pre_combat.enemies:
            pre_enemies_map[_enemy_key(e)] = e

    post_enemies_map: dict[str, object] = {}
    if post_combat:
        for e in post_combat.enemies:
            post_enemies_map[_enemy_key(e)] = e

    enemy_deltas_list: list[EnemyDelta] = []
    for key, pre_e in pre_enemies_map.items():
        post_e = post_enemies_map.get(key)
        if post_e is None:
            # Enemy disappeared (died or combat ended)
            if post_combat is not None:
                # Combat still going — enemy truly died
                enemy_deltas_list.append(EnemyDelta(
                    enemy_id=key,
                    name=pre_e.name,
                    index=pre_e.index,
                    died=True,
                ))
            continue

        e_hp = _diff_or_none(pre_e.current_hp, post_e.current_hp)
        e_block = _diff_or_none(pre_e.block, post_e.block)
        e_powers = _diff_powers(list(pre_e.powers), list(post_e.powers))
        e_died = pre_e.is_alive and not post_e.is_alive

        if e_hp is not None or e_block is not None or e_powers or e_died:
            enemy_deltas_list.append(EnemyDelta(
                enemy_id=key,
                name=pre_e.name,
                index=pre_e.index,
                hp=e_hp,
                block=e_block,
                powers_changed=e_powers,
                died=e_died,
            ))

    # ── Relic stack diff ─────────────────────────────────────────
    relic_changes: list[str] = []
    pre_relics = {r.name: r for r in (pre.relics or [])}
    post_relics = {r.name: r for r in (post.relics or [])}
    for name, pre_r in pre_relics.items():
        post_r = post_relics.get(name)
        if post_r is None:
            continue
        pre_stack = pre_r.stack
        post_stack = post_r.stack
        if pre_stack is not None and post_stack is not None and pre_stack != post_stack:
            relic_changes.append(f"{name}: {pre_stack}→{post_stack}")
        elif pre_stack is None and post_stack is not None:
            relic_changes.append(f"{name}: →{post_stack}")

    # ── Exhaust pile diff ────────────────────────────────────────
    cards_exhausted: list[str] = []
    pre_av = pre.raw.agent_view if pre.raw else None
    post_av = post.raw.agent_view if post.raw else None
    if (
        pre_av and pre_av.combat
        and post_av and post_av.combat
    ):
        pre_exhaust = [c.line for c in pre_av.combat.exhaust]
        post_exhaust = [c.line for c in post_av.combat.exhaust]
        # Assumes exhaust pile is append-only (cards are added to the end, never
        # reordered or removed). This holds for STS2 in practice — exhaust pile
        # manipulation effects are extremely rare. If this assumption breaks,
        # switch to a multiset diff (Counter subtraction).
        if len(post_exhaust) > len(pre_exhaust):
            cards_exhausted = post_exhaust[len(pre_exhaust):]

    # ── Source description (rules_text for played card) ─────────
    # Bug A2 (2026-04-30): hand lives on RawCombatPayload, not RawCombatPlayerPayload.
    # The previous `pre_combat.player.hand` raised AttributeError on real Pydantic
    # payloads (silently swallowed by _record_combat_delta's try/except), dropping
    # every card_play delta and zeroing per-card stats across runs.
    source_description = ""
    if event_type == "card_play" and pre_combat:
        for card in pre_combat.hand:
            if card.name == source:
                source_description = card.rules_text or ""
                break

    # ── Assemble ─────────────────────────────────────────────────
    return CombatDelta(
        event_type=event_type,
        source=source,
        source_description=source_description,
        target=target,
        hp=hp_delta,
        block=block_delta,
        energy=energy_delta,
        powers_changed=powers_changed,
        enemy_deltas=tuple(enemy_deltas_list),
        cards_exhausted=tuple(cards_exhausted),
        relic_changes=tuple(relic_changes),
    )


# ── Combat context builder ───────────────────────────────────────


def build_combat_context(gs: GameState, character: str) -> CombatContext | None:
    """Capture fixed combat context from GameState at combat start.

    Returns None if the state is not in combat.
    """
    combat = gs.raw.combat if gs.raw else None
    run = gs.raw.run if gs.raw else None
    if combat is None:
        return None

    # Relics with stack counters
    relics: tuple[RelicSnapshot, ...] = ()
    if run and run.relics:
        relics = tuple(
            RelicSnapshot(
                name=r.name,
                description=r.description or "",
                stack=r.stack,
            )
            for r in run.relics
        )

    # Enemy lineup — use full list (not gs.enemies which filters alive-only)
    enemy_lineup: list[EnemySnapshot] = []
    for e in combat.enemies:
        powers = tuple(_format_power(p) for p in e.powers) if e.powers else ()
        enemy_lineup.append(EnemySnapshot(
            name=e.name,
            index=e.index,
            enemy_id=e.enemy_id or f"{e.name}:{e.index}",
            hp=e.current_hp,
            max_hp=e.max_hp,
            powers=powers,
        ))

    # Deck
    deck_cards: tuple[str, ...] = ()
    if run and run.deck:
        deck_cards = tuple(c.name for c in run.deck)

    # Enemy key (same logic as short_term.start_combat)
    enemy_names = [e.name for e in combat.enemies if e.is_alive]
    if len(enemy_names) == 1:
        enemy_key = normalize_enemy_key(enemy_names[0])
    elif len(enemy_names) > 1:
        enemy_key = normalize_enemy_key("multi:" + "+".join(sorted(enemy_names)))
    else:
        enemy_key = "unknown"

    # Player powers at combat start
    player_powers: tuple[str, ...] = ()
    if combat.player.powers:
        player_powers = tuple(_format_power(p) for p in combat.player.powers)

    return CombatContext(
        enemy_key=enemy_key,
        character=character,
        combat_type=gs.state_type if gs.state_type in ("monster", "elite", "boss") else "monster",
        relics=relics,
        starting_hp=combat.player.current_hp,
        starting_max_hp=combat.player.max_hp,
        deck_cards=deck_cards,
        enemy_lineup=tuple(enemy_lineup),
        player_powers=player_powers,
    )
