"""Immutable game state snapshot wrapping the upstream STS2-Agent payload.

Phase 3 rewrite: GameState now wraps UpstreamGameState directly.
Convenience properties delegate to real upstream fields — no fake
old-model reconstruction.

Old accessor aliases (.battle, .rest_site, .treasure, etc.) return
the upstream raw types to ease incremental migration.  Callers that
reach into the old nested structure (e.g. gs.battle.player.hand)
will hit AttributeError and must be migrated in Phase 4-6.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.mcp_client.upstream_models import (
    AgentViewPayload,
    RawBundlePayload,
    RawCardsViewPayload,
    RawChestPayload,
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCrystalSpherePayload,
    RawDeckCardPayload,
    RawEventPayload,
    RawGameOverPayload,
    RawMapNodePayload,
    RawMapPayload,
    RawModalPayload,
    RawRestPayload,
    RawRewardPayload,
    RawRunPayload,
    RawRunPotionPayload,
    RawRunRelicPayload,
    RawSelectionPayload,
    RawShopPayload,
    UpstreamGameState,
)
from src.state.upstream_game_state import (
    CHOICE_PHASES,
    COMBAT_PHASES,
    IN_RUN_PHASES,
    MENU_PHASES,
    NAVIGATION_PHASES,
    REWARD_PHASES,
    derive_state_type,
)

# Re-export phase sets so existing `from src.state.game_state import COMBAT_PHASES` still works.
__all__ = [
    "GameState",
    "COMBAT_PHASES",
    "REWARD_PHASES",
    "CHOICE_PHASES",
    "NAVIGATION_PHASES",
    "MENU_PHASES",
    "IN_RUN_PHASES",
    "infer_act_from_floor",
    "resolve_boss_stage",
    "resolve_encounter_label",
]

_BOSS_STAGE_BY_FLOOR: dict[int, str] = {
    17: "act1_boss",
    34: "act2_boss",
    51: "final_boss",
}


def infer_act_from_floor(floor: int) -> int:
    """Infer act number from floor when upstream omits explicit act."""
    if floor <= 17:
        return 1
    if floor <= 34:
        return 2
    return 3


def resolve_boss_stage(
    *,
    state_type: str,
    floor: int,
    act: int | None = None,
    in_combat: bool = False,
    combat_type_override: str | None = None,
) -> str | None:
    """Resolve boss stage for a combat.

    Returns one of:
    - ``act1_boss``
    - ``act2_boss``
    - ``final_boss``
    """
    effective_type = combat_type_override or state_type
    if effective_type == "boss":
        resolved_act = act if act is not None else infer_act_from_floor(floor)
        if resolved_act <= 1:
            return "act1_boss"
        if resolved_act == 2:
            return "act2_boss"
        if floor in _BOSS_STAGE_BY_FLOOR:
            return _BOSS_STAGE_BY_FLOOR[floor]
        return "final_boss"

    if in_combat and floor in _BOSS_STAGE_BY_FLOOR:
        return _BOSS_STAGE_BY_FLOOR[floor]

    return None


def resolve_encounter_label(
    *,
    state_type: str,
    floor: int,
    act: int | None = None,
    in_combat: bool = False,
    combat_type_override: str | None = None,
) -> str:
    """Resolve the most specific combat label available."""
    effective_type = combat_type_override or state_type
    boss_stage = resolve_boss_stage(
        state_type=state_type,
        floor=floor,
        act=act,
        in_combat=in_combat,
        combat_type_override=combat_type_override,
    )
    return boss_stage or effective_type



@dataclass(frozen=True, slots=True)
class GameState:
    """Immutable snapshot of the game at one point in time.

    Wraps the real upstream UpstreamGameState payload.
    Convenience properties provide stable Pythonic access;
    ``raw`` gives direct access to the full upstream model.
    """

    raw: UpstreamGameState
    state_type: str = ""

    # ── Factory ────────────────────────────────────────────────

    @classmethod
    def from_upstream(cls, payload: UpstreamGameState) -> GameState:
        return cls(raw=payload, state_type=derive_state_type(payload))


    # ── Phase queries ──────────────────────────────────────────

    @property
    def is_combat(self) -> bool:
        return self.state_type in COMBAT_PHASES

    @property
    def is_reward(self) -> bool:
        return self.state_type in REWARD_PHASES

    @property
    def is_choice(self) -> bool:
        return self.state_type in CHOICE_PHASES

    @property
    def is_map(self) -> bool:
        return self.state_type in NAVIGATION_PHASES

    @property
    def is_hand_select(self) -> bool:
        return self.state_type == "hand_select"

    @property
    def is_menu(self) -> bool:
        return self.state_type in MENU_PHASES

    @property
    def is_game_over(self) -> bool:
        return self.state_type in ("game_over", "victory")

    @property
    def is_in_run(self) -> bool:
        return self.state_type in IN_RUN_PHASES or self.raw.run is not None

    # ── Upstream typed accessors ───────────────────────────────

    @property
    def combat(self) -> RawCombatPayload | None:
        return self.raw.combat

    @property
    def run_info(self) -> RawRunPayload | None:
        return self.raw.run

    @property
    def map(self) -> RawMapPayload | None:
        return self.raw.map

    @property
    def selection(self) -> RawSelectionPayload | None:
        return self.raw.selection

    @property
    def cards_view(self) -> RawCardsViewPayload | None:
        return self.raw.cards_view

    @property
    def event(self) -> RawEventPayload | None:
        return self.raw.event

    @property
    def crystal_sphere(self) -> RawCrystalSpherePayload | None:
        return self.raw.crystal_sphere

    @property
    def bundles(self) -> list[RawBundlePayload]:
        return list(self.raw.bundles or [])

    @property
    def rest(self) -> RawRestPayload | None:
        return self.raw.rest

    @property
    def shop(self) -> RawShopPayload | None:
        return self.raw.shop

    @property
    def reward(self) -> RawRewardPayload | None:
        return self.raw.reward

    @property
    def chest(self) -> RawChestPayload | None:
        return self.raw.chest

    @property
    def modal(self) -> RawModalPayload | None:
        return self.raw.modal

    @property
    def game_over_info(self) -> RawGameOverPayload | None:
        return self.raw.game_over

    @property
    def agent_view(self) -> AgentViewPayload | None:
        return self.raw.agent_view

    # ── Shape-compatible aliases ─────────────────────────────────
    # Only aliases where the upstream raw type is directly usable by
    # existing callers.  Shape-INCOMPATIBLE aliases (old PlayerSummary,
    # old CardRewardInfo, old ShopInfo.items, etc.) are intentionally
    # NOT provided — they would silently AttributeError at runtime,
    # which is worse than a clear break.  Phase 4-6 migrate those callers.

    @property
    def battle(self) -> RawCombatPayload | None:
        """Alias for .combat.

        CAUTION: gs.battle.player.hand will AttributeError — hand is at
        gs.combat.hand (or gs.hand) in the upstream model.  Phase 4 fixes
        all direct .battle.player.* paths.
        """
        return self.raw.combat

    @property
    def run(self) -> RawRunPayload | None:
        """Alias for .run_info."""
        return self.raw.run

    @property
    def treasure(self) -> RawChestPayload | None:
        """Alias for .chest."""
        return self.raw.chest

    # ── Potion slot convenience ──────────────────────────────────
    # Old PlayerSummary had .potion_slots / .open_potion_slots.
    # These derive from run.potions now.

    @property
    def potion_slots(self) -> int:
        if self.raw.run is None:
            return 0
        return len(self.raw.run.potions)

    @property
    def open_potion_slots(self) -> int:
        if self.raw.run is None:
            return 0
        return sum(1 for p in self.raw.run.potions if not p.occupied)

    # ── Available actions ─────────────────────────────────────

    @property
    def available_actions(self) -> list[str]:
        # Filter out save_and_quit — it's never a valid gameplay action.
        # Only the skill eval save/reload cycle uses it, and that calls
        # the MCP action directly (not through available_actions).
        return [a for a in self.raw.available_actions if a != "save_and_quit"]

    def has_action(self, action_name: str) -> bool:
        return action_name in self.raw.available_actions

    @property
    def can_play_card(self) -> bool:
        return "play_card" in self.raw.available_actions

    @property
    def can_end_turn(self) -> bool:
        return "end_turn" in self.raw.available_actions

    @property
    def is_play_phase(self) -> bool:
        """True when it is the player's turn to act in combat.

        Uses end_turn (not play_card) because upstream only publishes
        play_card when at least one card is playable.
        """
        return self.is_combat and self.can_end_turn

    @property
    def can_proceed(self) -> bool:
        """True when proceed is semantically valid."""
        if self.raw.rest is not None:
            return not any(o.is_enabled for o in self.raw.rest.options)
        if self.raw.reward is not None:
            return self.raw.reward.can_proceed
        if self.raw.chest is not None:
            return (
                self.raw.chest.has_relic_been_claimed
                or "proceed" in self.raw.available_actions
            )
        return "proceed" in self.raw.available_actions

    # ── Combat convenience ─────────────────────────────────────

    @property
    def hand(self) -> list[RawCombatHandCardPayload]:
        if self.raw.combat is None:
            return []
        return list(self.raw.combat.hand)

    @property
    def playable_cards(self) -> list[RawCombatHandCardPayload]:
        return [c for c in self.hand if c.playable]

    @property
    def enemies(self) -> list[RawCombatEnemyPayload]:
        if self.raw.combat is None:
            return []
        return [e for e in self.raw.combat.enemies if e.is_alive]

    @property
    def block(self) -> int:
        """Combat block shim for migrated callers that used ``gs.block`` directly."""
        if self.raw.combat is None:
            return 0
        return self.raw.combat.player.block

    @property
    def energy(self) -> int:
        if self.raw.combat is None:
            return 0
        return self.raw.combat.player.energy

    @property
    def max_energy(self) -> int:
        """Run max energy shim for migrated callers that used ``gs.max_energy`` directly."""
        if self.raw.run is None:
            return 0
        return self.raw.run.max_energy

    @property
    def player_hp(self) -> int:
        if self.raw.combat is not None:
            return self.raw.combat.player.current_hp
        if self.raw.run is not None:
            return self.raw.run.current_hp
        return 0

    @property
    def player_max_hp(self) -> int:
        if self.raw.combat is not None:
            return self.raw.combat.player.max_hp
        if self.raw.run is not None:
            return self.raw.run.max_hp
        return 0

    @property
    def hp_ratio(self) -> float:
        max_hp = self.player_max_hp
        return self.player_hp / max_hp if max_hp > 0 else 1.0

    @property
    def gold(self) -> int:
        if self.raw.run is None:
            return 0
        return self.raw.run.gold

    @property
    def combat_round(self) -> int:
        """Current combat round number (from top-level turn field)."""
        return self.raw.turn or 0

    # ── Run convenience ───────────────────────────────────────

    @property
    def deck(self) -> list[RawDeckCardPayload]:
        if self.raw.run is None:
            return []
        return list(self.raw.run.deck)

    @property
    def deck_size(self) -> int:
        return len(self.deck)

    @property
    def act(self) -> int:
        """Resolve act number, preferring upstream explicit metadata."""
        if self.raw.act is not None:
            return self.raw.act
        if self.raw.run is None:
            return 1
        return infer_act_from_floor(self.raw.run.floor)

    @property
    def combat_type(self) -> str:
        """Combat type provided explicitly by the upstream mod, if any."""
        if self.raw.combat_type:
            normalized = self.raw.combat_type.strip().lower()
            if normalized in COMBAT_PHASES:
                return normalized
        return ""

    @property
    def boss_stage(self) -> str | None:
        """Resolved boss stage, preferring upstream explicit metadata."""
        if self.raw.boss_stage:
            return self.raw.boss_stage
        if self.floor <= 0:
            return None
        return resolve_boss_stage(
            state_type=self.state_type,
            floor=self.floor,
            act=self.act,
            in_combat=self.raw.in_combat,
            combat_type_override=self.combat_type or None,
        )

    @property
    def is_final_boss(self) -> bool:
        return bool(self.raw.is_final_boss or self.boss_stage == "final_boss")

    @property
    def upcoming_boss_enemy_keys(self) -> list[str]:
        """Enemy_keys for current act's boss node(s), resolved via encounter_lookup.
        Returns 0, 1, or 2 keys. Empty if mod data missing or encounter unknown.
        Returned in fight order: primary boss first, second boss (if present) second."""
        ids = [self.raw.boss_encounter_id, self.raw.second_boss_encounter_id]
        ids = [i for i in ids if i]
        if not ids:
            return []
        from src.knowledge.knowledge import GameKnowledge
        try:
            kb = GameKnowledge.get_instance()
        except Exception:
            return []
        resolved = [kb.encounters.resolve_encounter_enemy_key(i) for i in ids]
        return [k for k in resolved if k]

    @property
    def floor(self) -> int:
        if self.raw.run is None:
            return 0
        return self.raw.run.floor

    @property
    def relics(self) -> list[RawRunRelicPayload]:
        if self.raw.run is None:
            return []
        return list(self.raw.run.relics)

    @property
    def potions(self) -> list[RawRunPotionPayload]:
        if self.raw.run is None:
            return []
        return list(self.raw.run.potions)

    @property
    def character(self) -> str | None:
        """Display name of the current character."""
        if self.raw.run is not None and self.raw.run.character_name:
            return self.raw.run.character_name
        if self.raw.character_select and self.raw.character_select.selected_character_id:
            return self.raw.character_select.selected_character_id
        return None

    @property
    def character_id(self) -> str | None:
        """Programmatic ID (for guide loading, archetype detection)."""
        if self.raw.run is not None and self.raw.run.character_id:
            return self.raw.run.character_id
        if self.raw.character_select and self.raw.character_select.selected_character_id:
            return self.raw.character_select.selected_character_id
        return None

    @property
    def ascension(self) -> int:
        """Current ascension level (from run payload, fallback to character select)."""
        if self.raw.run is not None:
            return self.raw.run.ascension
        if self.raw.character_select is not None:
            return self.raw.character_select.ascension
        return 0

    # ── Map convenience ────────────────────────────────────────

    @property
    def next_map_options(self) -> list[RawMapNodePayload]:
        if self.raw.map is None:
            return []
        return list(self.raw.map.available_nodes)

    # ── Summary ────────────────────────────────────────────────

    def summary(self, combat_type_override: str | None = None) -> str:
        """Short human-readable summary for logging."""
        effective_combat_type = combat_type_override or self.combat_type or None
        state_label = effective_combat_type or self.state_type
        if state_label in COMBAT_PHASES:
            encounter_label = resolve_encounter_label(
                state_type=self.state_type,
                floor=self.floor,
                act=self.act,
                in_combat=self.is_combat,
                combat_type_override=effective_combat_type,
            )
            if encounter_label != state_label:
                state_label = f"{state_label}/{encounter_label}"

        parts = [f"[{state_label}]"]
        if self.raw.run is not None:
            parts.append(f"F{self.raw.run.floor}")
            if self.raw.run.character_name:
                parts.append(self.raw.run.character_name)
        if self.raw.combat is not None:
            p = self.raw.combat.player
            parts.append(
                f"HP:{p.current_hp}/{p.max_hp} E:{p.energy} Hand:{len(self.raw.combat.hand)}"
            )
            alive = [e for e in self.raw.combat.enemies if e.is_alive]
            if alive:
                def _intent_short(e) -> str:
                    if not e.intents:
                        return ""
                    it = e.intents[0]
                    if it.total_damage:
                        hits = it.hits or 1
                        return f" {it.damage}×{hits}" if hits > 1 else f" {it.total_damage}dmg"
                    if it.intent_type:
                        return f" {it.intent_type}"
                    return ""
                enemies_str = ", ".join(f"{e.name}({e.current_hp}{_intent_short(e)})" for e in alive)
                parts.append(f"vs [{enemies_str}]")
        elif self.raw.run is not None:
            parts.append(
                f"HP:{self.raw.run.current_hp}/{self.raw.run.max_hp} G:{self.raw.run.gold}"
            )
        return " | ".join(parts)
