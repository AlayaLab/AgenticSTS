"""Convenience wrapper over the real upstream STS2-Agent state payload."""

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
    RawSelectionPayload,
    RawShopPayload,
    UpstreamGameState,
)

COMBAT_PHASES = frozenset({"monster", "elite", "boss"})
# card_select/hand_select can occur MID-COMBAT (e.g. Survivor discard, exhaust effects).
# capstone_overlay is a stray UI overlay (TopBar deck/map button, inspect zoom,
# pause menu) that the human supervisor can open mid-combat — the underlying
# combat is still active.  All must be treated as combat-adjacent to prevent
# false COMBAT_END detection (which would record a phantom Victory based on
# player_hp > 0, corrupt skill confidence, and discard mid-combat conversation).
COMBAT_ADJACENT_PHASES = frozenset(
    {"card_select", "hand_select", "combat_hand_select", "capstone_overlay"}
)

# Action names emitted by the mod when only an overlay-escape is possible.
# Mirrors `_OVERLAY_ESCAPE_ACTIONS` in src/agent/loop.py — kept in sync there.
_OVERLAY_ESCAPE_ACTIONS = frozenset({"close_capstone_overlay", "close_pause_menu"})
REWARD_PHASES = frozenset({"combat_rewards", "card_reward", "treasure"})
CHOICE_PHASES = frozenset(
    {
        "event",
        "crystal_sphere",
        "bundle_select",
        "rest_site",
        "shop",
        "card_select",
        "hand_select",
        "combat_hand_select",
        "cards_view",
    }
)
NAVIGATION_PHASES = frozenset({"map"})
MENU_PHASES = frozenset({"menu", "game_over", "victory", "timeline", "character_select", "overlay"})
IN_RUN_PHASES = COMBAT_PHASES | REWARD_PHASES | CHOICE_PHASES | NAVIGATION_PHASES
_HAND_SELECTION_KINDS = frozenset({"hand", "combat_hand_select"})
_BOSS_FLOORS = frozenset({17, 34, 51})
_BOSS_STAGE_BY_FLOOR = {
    17: "act1_boss",
    34: "act2_boss",
    51: "final_boss",
}


def _infer_act_from_floor(floor: int) -> int:
    if floor <= 17:
        return 1
    if floor <= 34:
        return 2
    return 3


def _infer_combat_type(raw: UpstreamGameState) -> str:
    if raw.combat_type:
        normalized = raw.combat_type.strip().lower()
        if normalized in COMBAT_PHASES:
            return normalized

    # Primary: use map node metadata (most reliable)
    if raw.map:
        for node in raw.map.nodes:
            if not node.is_current:
                continue
            node_type = node.node_type.lower()
            if node_type == "elite":
                return "elite"
            if "boss" in node_type or node.is_boss or node.is_second_boss:
                return "boss"
            return "monster"

    # During combat the upstream payload usually omits map data. Boss floors are
    # still authoritative and let us recover boss-vs-nonboss even without cache.
    if raw.run and raw.run.floor in _BOSS_FLOORS:
        return "boss"

    # No map data during combat — default to monster.
    # The authoritative source is _cached_map_node_type in the agent loop,
    # which is set at map node selection time (before combat starts).
    # HP heuristic removed: Act 3 normal enemies (e.g. Slimed Berserker 263 HP)
    # exceed any reasonable boss threshold.
    return "monster"


def _infer_reward_state_type(raw: UpstreamGameState, screen: str) -> str | None:
    """Infer reward/card-reward states from actions when the screen lags behind."""
    actions = set(raw.available_actions or [])

    if (
        screen in {"REWARD", "CARD_SELECTION"}
        and raw.reward
        and raw.reward.pending_card_choice
    ):
        return "card_reward"
    if (
        "choose_reward_card" in actions
        or "choose_reward_alternative" in actions
        or "skip_reward_cards" in actions
        or "sacrifice_reward_cards" in actions
    ):
        return "card_reward"
    if (
        screen == "REWARD"
        or "claim_reward" in actions
        or "collect_rewards_and_proceed" in actions
    ):
        return "combat_rewards"
    return None


def _infer_selection_state_type(raw: UpstreamGameState) -> str | None:
    """Infer card-selection states when the upstream screen lags behind.

    Some relic follow-ups can render a deck-selection grid inside another
    screen context (for example a shop purchase opening a duplicate-card
    picker).  In that case the action set and selection payload are more
    authoritative than the stale room screen.
    """
    if raw.selection is None:
        return None
    actions = set(raw.available_actions or [])
    if "select_deck_card" not in actions and "confirm_selection" not in actions:
        return None
    if raw.selection.kind in _HAND_SELECTION_KINDS:
        return "hand_select"
    return "card_select"


def derive_state_type(raw: UpstreamGameState) -> str:
    """Derive a legacy-like phase label from the real upstream payload."""
    if raw.game_over:
        return "victory" if raw.game_over.is_victory else "game_over"

    # Stray UI overlay short-circuit — when the only non-trivial action is
    # an overlay-escape (close_capstone_overlay / close_pause_menu), the
    # underlying `screen` field is unreliable: a TopBar map button opened
    # mid-combat reads as MAP, deck-view CapstoneContainer reads as
    # whatever was underneath, etc.  Classify as a dedicated phase so the
    # state_machine treats it as combat-adjacent and does not fire a false
    # COMBAT_END (which would record a phantom Victory).  See
    # tests/test_overlay_state_classification.py for the regression set.
    avail = raw.available_actions or []
    overlay_core = [a for a in avail if a != "save_and_quit"]
    if overlay_core and all(a in _OVERLAY_ESCAPE_ACTIONS for a in overlay_core):
        return "capstone_overlay"

    # Crystal Sphere is exposed by the mod via a dedicated `crystal_sphere`
    # payload (see GameStateService.BuildCrystalSpherePayload). The screen
    # string is still "EVENT" for backward compat, but we treat it as a
    # distinct decision phase.
    if raw.crystal_sphere is not None:
        return "crystal_sphere"

    # Bundle (ScrollBoxes) selection is exposed via dedicated `bundles[]`
    # payload (see GameStateService.BuildBundlesPayload). Falls under
    # CARD_SELECTION screen string but gets its own state_type so we can
    # use a bundle-specific prompt instead of the per-pack flow.
    if raw.bundles:
        return "bundle_select"

    screen = raw.screen.upper()
    if screen in {"SHOP", "REWARD", "CARD_SELECTION"}:
        reward_state = _infer_reward_state_type(raw, screen)
        if reward_state is not None:
            return reward_state
    selection_state = _infer_selection_state_type(raw)
    if selection_state is not None:
        return selection_state
    if screen == "COMBAT":
        return _infer_combat_type(raw)
    if screen == "COMBAT_END":
        return "combat_rewards"
    if screen == "MAP":
        return "map"
    if screen == "EVENT":
        return "event"
    if screen == "REST":
        return "rest_site"
    if screen == "SHOP":
        return "shop"
    if screen == "REWARD":
        return "combat_rewards"
    if screen == "CARD_SELECTION":
        if raw.selection and raw.selection.kind in _HAND_SELECTION_KINDS:
            return "hand_select"
        return "card_select"
    if screen == "CARDS_VIEW":
        return "cards_view"
    if screen == "CHEST":
        return "treasure"
    if screen == "MAIN_MENU":
        return "menu"
    if screen == "CHARACTER_SELECT":
        return "character_select"
    if screen == "TIMELINE":
        return "timeline"
    if screen == "MODAL":
        return "overlay"
    return screen.lower()


@dataclass(frozen=True, slots=True)
class UpstreamStateView:
    """Thin Pythonic wrapper over the upstream raw payload."""

    raw: UpstreamGameState
    state_type: str = ""

    @classmethod
    def from_payload(cls, payload: UpstreamGameState) -> UpstreamStateView:
        return cls(raw=payload, state_type=derive_state_type(payload))

    @property
    def screen(self) -> str:
        return self.raw.screen

    @property
    def session(self):
        return self.raw.session

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
    def is_menu(self) -> bool:
        return self.state_type in MENU_PHASES

    @property
    def is_in_run(self) -> bool:
        return self.state_type in IN_RUN_PHASES or self.raw.run is not None

    @property
    def available_actions(self) -> list[str]:
        return self.raw.available_actions

    def has_action(self, action_name: str) -> bool:
        return action_name in self.raw.available_actions

    @property
    def combat(self) -> RawCombatPayload | None:
        return self.raw.combat

    @property
    def run(self) -> RawRunPayload | None:
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
    def reward(self) -> RawRewardPayload | None:
        return self.raw.reward

    @property
    def shop(self) -> RawShopPayload | None:
        return self.raw.shop

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
    def chest(self) -> RawChestPayload | None:
        return self.raw.chest

    @property
    def modal(self) -> RawModalPayload | None:
        return self.raw.modal

    @property
    def game_over(self) -> RawGameOverPayload | None:
        return self.raw.game_over

    @property
    def agent_view(self) -> AgentViewPayload | None:
        return self.raw.agent_view

    @property
    def hand(self) -> list[RawCombatHandCardPayload]:
        if self.raw.combat is None:
            return []
        return list(self.raw.combat.hand)

    @property
    def playable_cards(self) -> list[RawCombatHandCardPayload]:
        return [card for card in self.hand if card.playable]

    @property
    def enemies(self) -> list[RawCombatEnemyPayload]:
        if self.raw.combat is None:
            return []
        return [enemy for enemy in self.raw.combat.enemies if enemy.is_alive]

    @property
    def energy(self) -> int:
        if self.raw.combat is None:
            return 0
        return self.raw.combat.player.energy

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
    def gold(self) -> int:
        if self.raw.run is None:
            return 0
        return self.raw.run.gold

    @property
    def floor(self) -> int:
        if self.raw.run is None:
            return 0
        return self.raw.run.floor

    @property
    def act(self) -> int:
        if self.raw.act is not None:
            return self.raw.act
        if self.raw.run is None:
            return 1
        return _infer_act_from_floor(self.raw.run.floor)

    @property
    def combat_type(self) -> str:
        if self.raw.combat_type:
            normalized = self.raw.combat_type.strip().lower()
            if normalized in COMBAT_PHASES:
                return normalized
        return ""

    @property
    def boss_stage(self) -> str | None:
        if self.raw.boss_stage:
            return self.raw.boss_stage
        if self.combat_type != "boss":
            return None
        if self.floor in _BOSS_STAGE_BY_FLOOR:
            return _BOSS_STAGE_BY_FLOOR[self.floor]
        if self.act <= 1:
            return "act1_boss"
        if self.act == 2:
            return "act2_boss"
        return "final_boss"

    @property
    def is_final_boss(self) -> bool:
        return bool(self.raw.is_final_boss or self.boss_stage == "final_boss")

    @property
    def upcoming_boss_enemy_keys(self) -> list[str]:
        """Enemy_keys for current act's boss node(s), resolved via encounter_lookup.
        Returns 0, 1, or 2 keys. Empty list if mod data missing / encounter unknown.
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
    def deck(self) -> list[RawDeckCardPayload]:
        if self.raw.run is None:
            return []
        return list(self.raw.run.deck)

    @property
    def relics(self) -> list:
        if self.raw.run is None:
            return []
        return list(self.raw.run.relics)

    @property
    def potions(self) -> list:
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
        """Programmatic character ID (used for guide loading, archetype detection)."""
        if self.raw.run is not None and self.raw.run.character_id:
            return self.raw.run.character_id
        if self.raw.character_select and self.raw.character_select.selected_character_id:
            return self.raw.character_select.selected_character_id
        return None

    @property
    def next_map_options(self) -> list[RawMapNodePayload]:
        if self.raw.map is None:
            return []
        return list(self.raw.map.available_nodes)

    @property
    def is_hand_select(self) -> bool:
        return self.state_type == "hand_select"

    @property
    def is_game_over(self) -> bool:
        return self.state_type in ("game_over", "victory")

    @property
    def hp_ratio(self) -> float:
        max_hp = self.player_max_hp
        return self.player_hp / max_hp if max_hp > 0 else 1.0

    @property
    def deck_size(self) -> int:
        return len(self.deck)

    @property
    def is_play_phase(self) -> bool:
        """True when it is the player's turn to act in combat.

        Uses end_turn (not play_card) because upstream only publishes play_card
        when at least one card is playable.  A hand with zero playable cards
        still needs to end_turn, so play_card alone would miss that case.
        """
        return self.is_combat and self.can_end_turn

    @property
    def can_play_card(self) -> bool:
        return "play_card" in self.raw.available_actions

    @property
    def can_end_turn(self) -> bool:
        return "end_turn" in self.raw.available_actions

    @property
    def can_proceed(self) -> bool:
        """True when proceed is semantically available (not just listed in actions)."""
        if self.raw.rest is not None:
            return not any(o.is_enabled for o in self.raw.rest.options)
        if self.raw.reward is not None:
            return self.raw.reward.can_proceed
        if self.raw.chest is not None:
            # Don't use `not relic_options` — upstream returns empty options
            # before the chest is opened, which is not the same as "done".
            return self.raw.chest.has_relic_been_claimed or "proceed" in self.raw.available_actions
        return "proceed" in self.raw.available_actions

    @property
    def combat_round(self) -> int:
        """Current combat round number (from top-level turn field)."""
        return self.raw.turn or 0

    def summary(self) -> str:
        parts = [f"[{self.state_type}]"]
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
                enemies_str = ", ".join(f"{e.name}({e.current_hp})" for e in alive)
                parts.append(f"vs [{enemies_str}]")
        elif self.raw.run is not None:
            parts.append(f"HP:{self.raw.run.current_hp}/{self.raw.run.max_hp}")
            parts.append(f"G:{self.raw.run.gold}")
        return " | ".join(parts)
