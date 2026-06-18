"""Typed models for the upstream STS2-Agent `/state` payload.

These models represent the real payload shape returned by the upstream C# mod.
They intentionally do not translate fields into the legacy compatibility schema.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class UpstreamModel(BaseModel):
    """Base model for upstream state payloads."""

    model_config = ConfigDict(extra="ignore", frozen=True)


class RawSessionPayload(UpstreamModel):
    mode: str = "singleplayer"
    phase: str = "menu"
    control_scope: str = "local_player"


class RawCombatPowerPayload(UpstreamModel):
    index: int = 0
    power_id: str = ""
    name: str = ""
    amount: int | None = None
    description: str = ""
    is_debuff: bool = False


class RawCombatOrbPayload(UpstreamModel):
    slot_index: int = 0
    orb_id: str = ""
    name: str = ""
    passive_value: float = 0.0
    evoke_value: float = 0.0
    is_front: bool = False


class TargetPreview(UpstreamModel):
    target_index: int = 0
    damage: int = 0
    hits: int = 1
    total_damage: int = 0


class DynamicValue(UpstreamModel):
    """v0.5.3 per-card dynamic value."""

    name: str = ""
    base_value: float = 0
    current_value: float = 0
    enchanted_value: float | None = None
    is_modified: bool = False
    was_just_upgraded: bool = False


class RawGeneratedCardPayload(UpstreamModel):
    """A card that the source card generates mid-play (e.g. Blade of Ink → Shiv).

    Sourced from CardModel.HoverTips in the C# mod, mirroring the same
    long-press preview the game UI shows. Upgrade-aware: when the source
    card is upgraded, the generated card here is the upgraded variant
    (e.g. Hidden Daggers+ → Shiv+).
    """

    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    card_type: str = ""
    energy_cost: int = 0
    rules_text: str = ""
    keywords: list[str] = Field(default_factory=list)


class RawCombatHandCardPayload(UpstreamModel):
    index: int = 0
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    card_type: str = ""
    target_type: str = ""
    requires_target: bool = False
    target_index_space: str | None = None
    valid_target_indices: list[int] = Field(default_factory=list)
    costs_x: bool = False
    star_costs_x: bool = False
    energy_cost: int = 0
    star_cost: int = 0
    rules_text: str = ""
    playable: bool = False
    unplayable_reason: str | None = None
    # Structured card-level preview values (untargeted, player-side modifiers only)
    damage: int | None = None
    block: int | None = None
    hits: int | None = None
    total_damage: int | None = None
    # Replay: additional auto-plays (e.g. Glam enchantment gives replay=1)
    replay: int | None = None
    target_previews: list[TargetPreview] | None = None
    # Cards this card generates mid-play (e.g. Blade of Ink → Inky Shiv).
    generated_cards: list[RawGeneratedCardPayload] = Field(default_factory=list)


class RawCombatEnemyIntentPayload(UpstreamModel):
    index: int = 0
    intent_type: str = ""
    label: str | None = None
    damage: int | None = None
    hits: int | None = None
    total_damage: int | None = None
    status_card_count: int | None = None


class RawCombatEnemyPayload(UpstreamModel):
    index: int = 0
    enemy_id: str = ""
    name: str = ""
    current_hp: int = 0
    max_hp: int = 0
    block: int = 0
    is_alive: bool = False
    is_hittable: bool = False
    powers: list[RawCombatPowerPayload] = Field(default_factory=list)
    # Deprecated: legacy string field from older mod versions, always None in current upstream.
    # Use `intents` (structured list) instead.
    intent: str | None = None
    move_id: str | None = None
    intents: list[RawCombatEnemyIntentPayload] = Field(default_factory=list)


class RawPileCardPayload(UpstreamModel):
    """Structured pile card (draw/discard/exhaust). Additive companion to
    the textual `draw`/`discard`/`exhaust` strings on agent_view."""

    card_id: str = ""
    upgraded: bool = False
    card_type: str = ""


class RawCombatPlayerPayload(UpstreamModel):
    current_hp: int = 0
    max_hp: int = 0
    block: int = 0
    energy: int = 0
    stars: int = 0
    focus: int = 0
    powers: list[RawCombatPowerPayload] = Field(default_factory=list)
    base_orb_slots: int = 0
    orb_capacity: int = 0
    empty_orb_slots: int = 0
    orbs: list[RawCombatOrbPayload] = Field(default_factory=list)
    draw_cards: list[RawPileCardPayload] = Field(default_factory=list)
    discard_cards: list[RawPileCardPayload] = Field(default_factory=list)
    exhaust_cards: list[RawPileCardPayload] = Field(default_factory=list)


class RawCombatPlayerSummaryPayload(UpstreamModel):
    player_id: str = ""
    slot_index: int = 0
    is_local: bool = False
    is_connected: bool = False
    character_id: str = ""
    character_name: str = ""
    current_hp: int = 0
    max_hp: int = 0
    block: int = 0
    energy: int = 0
    stars: int = 0
    focus: int = 0
    is_alive: bool = False


class RawCombatPayload(UpstreamModel):
    player: RawCombatPlayerPayload = Field(default_factory=RawCombatPlayerPayload)
    players: list[RawCombatPlayerSummaryPayload] = Field(default_factory=list)
    hand: list[RawCombatHandCardPayload] = Field(default_factory=list)
    enemies: list[RawCombatEnemyPayload] = Field(default_factory=list)


class RawDeckCardPayload(UpstreamModel):
    index: int = 0
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    card_type: str = ""
    rarity: str = ""
    costs_x: bool = False
    star_costs_x: bool = False
    energy_cost: int = 0
    star_cost: int = 0
    rules_text: str = ""
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
    enchantment_id: str | None = None
    enchantment_name: str | None = None


class RawRunRelicPayload(UpstreamModel):
    index: int = 0
    relic_id: str = ""
    name: str = ""
    description: str | None = None
    stack: int | None = None
    is_melted: bool = False
    counter: int | None = None  # progress toward next trigger for counter relics (e.g. Nunchaku attack count)


class RawRunPotionPayload(UpstreamModel):
    index: int = 0
    potion_id: str | None = None
    name: str | None = None
    description: str | None = None
    rarity: str | None = None
    occupied: bool = False
    usage: str | None = None
    target_type: str | None = None
    is_queued: bool = False
    requires_target: bool = False
    target_index_space: str | None = None
    valid_target_indices: list[int] = Field(default_factory=list)
    can_use: bool = False
    can_discard: bool = False


class RawRunPlayerSummaryPayload(UpstreamModel):
    player_id: str = ""
    slot_index: int = 0
    is_local: bool = False
    is_connected: bool = False
    character_id: str = ""
    character_name: str = ""
    current_hp: int = 0
    max_hp: int = 0
    gold: int = 0
    is_alive: bool = False


class RawRunPayload(UpstreamModel):
    character_id: str = ""
    character_name: str = ""
    floor: int = 0
    ascension: int = 0
    current_hp: int = 0
    max_hp: int = 0
    gold: int = 0
    max_energy: int = 0
    base_orb_slots: int = 0
    deck: list[RawDeckCardPayload] = Field(default_factory=list)
    relics: list[RawRunRelicPayload] = Field(default_factory=list)
    players: list[RawRunPlayerSummaryPayload] = Field(default_factory=list)
    potions: list[RawRunPotionPayload] = Field(default_factory=list)


class RawMultiplayerPayload(UpstreamModel):
    is_multiplayer: bool = False
    net_game_type: str = ""
    local_player_id: str | None = None
    player_count: int = 0
    connected_player_ids: list[str] = Field(default_factory=list)


class RawCharacterSelectPlayerPayload(UpstreamModel):
    player_id: str = ""
    slot_index: int = 0
    is_local: bool = False
    character_id: str | None = None
    character_name: str | None = None
    is_ready: bool = False
    max_multiplayer_ascension_unlocked: int = 0


class RawCharacterSelectOptionPayload(UpstreamModel):
    index: int = 0
    character_id: str = ""
    name: str = ""
    is_locked: bool = False
    is_selected: bool = False
    is_random: bool = False


class RawMultiplayerLobbyPayload(UpstreamModel):
    net_game_type: str = ""
    join_host: str = "127.0.0.1"
    join_port: int = 0
    local_net_id_hint: str | None = None
    has_lobby: bool = False
    is_host: bool = False
    is_client: bool = False
    local_ready: bool = False
    can_host: bool = False
    can_join: bool = False
    can_ready: bool = False
    can_disconnect: bool = False
    can_unready: bool = False
    selected_character_id: str | None = None
    player_count: int = 0
    max_players: int = 0
    players: list[RawCharacterSelectPlayerPayload] = Field(default_factory=list)
    characters: list[RawCharacterSelectOptionPayload] = Field(default_factory=list)


class RawMapCoordPayload(UpstreamModel):
    row: int = 0
    col: int = 0


class RawMapNodePayload(UpstreamModel):
    index: int = 0
    row: int = 0
    col: int = 0
    node_type: str = ""
    state: str = ""  # "UNREACHED", "REACHED", "COMPLETED"


class RawMapGraphNodePayload(UpstreamModel):
    row: int = 0
    col: int = 0
    node_type: str = ""
    state: str = ""  # "UNREACHED", "REACHED", "COMPLETED"
    visited: bool = False
    is_current: bool = False
    is_available: bool = False
    is_start: bool = False
    is_boss: bool = False
    is_second_boss: bool = False
    parents: list[RawMapCoordPayload] = Field(default_factory=list)
    children: list[RawMapCoordPayload] = Field(default_factory=list)


class RawMapPayload(UpstreamModel):
    current_node: RawMapCoordPayload | None = None
    is_travel_enabled: bool = False
    is_traveling: bool = False
    map_generation_count: int = 0
    rows: int = 0
    cols: int = 0
    starting_node: RawMapCoordPayload | None = None
    boss_node: RawMapCoordPayload | None = None
    second_boss_node: RawMapCoordPayload | None = None
    nodes: list[RawMapGraphNodePayload] = Field(default_factory=list)
    available_nodes: list[RawMapNodePayload] = Field(default_factory=list)


class RawSelectionCardPayload(UpstreamModel):
    index: int = 0
    stable_id: str = ""
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    card_type: str = ""
    rarity: str = ""
    costs_x: bool = False
    star_costs_x: bool = False
    energy_cost: int = 0
    star_cost: int = 0
    rules_text: str = ""
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
    is_selected: bool = False
    is_selectable: bool = True
    # Upgrade preview (Smith screen only): resolved description after upgrading
    upgrade_preview_description: str | None = None
    # Upgrade preview: new energy cost after upgrading (only set when cost changes)
    upgrade_preview_cost: int | None = None


class RawSelectionPayload(UpstreamModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    kind: str = ""
    prompt: str = ""
    min_select: int = Field(default=1, alias="min")
    max_select: int = Field(default=1, alias="max")
    selected_count: int = Field(default=0, alias="selected")
    requires_confirmation: bool = False
    can_confirm: bool = Field(default=False, alias="confirm")
    cards: list[RawSelectionCardPayload] = Field(default_factory=list)
    selected_cards: list[RawSelectionCardPayload] = Field(default_factory=list)
    selectable_cards: list[RawSelectionCardPayload] = Field(default_factory=list)
    preview_cards: list[RawSelectionCardPayload] = Field(default_factory=list)


class RawCardsViewPayload(UpstreamModel):
    title: str = ""
    cards: list[RawSelectionCardPayload] = Field(default_factory=list)


class RawCharacterSelectPayload(UpstreamModel):
    selected_character_id: str | None = None
    is_multiplayer: bool = False
    net_game_type: str = ""
    can_embark: bool = False
    can_unready: bool = False
    can_increase_ascension: bool = False
    can_decrease_ascension: bool = False
    local_ready: bool = False
    is_waiting_for_players: bool = False
    player_count: int = 0
    max_players: int = 0
    ascension: int = 0
    max_ascension: int = 0
    seed: str | None = None
    modifier_ids: list[str] = Field(default_factory=list)
    players: list[RawCharacterSelectPlayerPayload] = Field(default_factory=list)
    characters: list[RawCharacterSelectOptionPayload] = Field(default_factory=list)


class RawTimelineSlotPayload(UpstreamModel):
    index: int = 0
    epoch_id: str = ""
    title: str = ""
    state: str = ""
    is_actionable: bool = False


class RawTimelinePayload(UpstreamModel):
    back_enabled: bool = False
    inspect_open: bool = False
    unlock_screen_open: bool = False
    can_choose_epoch: bool = False
    can_confirm_overlay: bool = False
    slots: list[RawTimelineSlotPayload] = Field(default_factory=list)


class RawChestRelicOptionPayload(UpstreamModel):
    index: int = 0
    relic_id: str = ""
    name: str = ""
    rarity: str = ""


class RawChestPayload(UpstreamModel):
    is_opened: bool = False
    has_relic_been_claimed: bool = False
    relic_options: list[RawChestRelicOptionPayload] = Field(default_factory=list)


class RawEventOptionPayload(UpstreamModel):
    index: int = 0
    text_key: str = ""
    title: str = ""
    description: str = ""
    is_locked: bool = False
    is_proceed: bool = False
    will_kill_player: bool = False
    has_relic_preview: bool = False
    # Extended fields (from enhanced C# mod)
    effect_description: str = ""
    hp_cost: int | None = None
    gold_cost: int | None = None
    cards_offered: list[dict] = Field(default_factory=list)
    relics_offered: list[dict] = Field(default_factory=list)
    potions_offered: list[dict] = Field(default_factory=list)
    curses_risk: list[str] = Field(default_factory=list)


class RawEventPayload(UpstreamModel):
    event_id: str = ""
    title: str = ""
    description: str = ""
    is_finished: bool = False
    options: list[RawEventOptionPayload] = Field(default_factory=list)


class RawCrystalSphereCellPayload(UpstreamModel):
    x: int = 0
    y: int = 0
    is_hidden: bool = True
    is_clickable: bool = False
    item_type: str | None = None
    is_good: bool | None = None


class RawCrystalSphereCellRefPayload(UpstreamModel):
    x: int = 0
    y: int = 0


class RawCrystalSphereRevealedItemPayload(UpstreamModel):
    x: int = 0
    y: int = 0
    item_type: str = "unknown"
    is_good: bool = False


class RawCrystalSpherePayload(UpstreamModel):
    grid_width: int = 0
    grid_height: int = 0
    tool: str = "none"
    can_use_big_tool: bool = False
    can_use_small_tool: bool = False
    divinations_left: int = 0
    divinations_left_text: str | None = None
    instructions_title: str | None = None
    instructions_description: str | None = None
    can_proceed: bool = False
    is_finished: bool = False
    cells: list[RawCrystalSphereCellPayload] = Field(default_factory=list)
    clickable_cells: list[RawCrystalSphereCellRefPayload] = Field(default_factory=list)
    revealed_items: list[RawCrystalSphereRevealedItemPayload] = Field(default_factory=list)


class RawRestOptionPayload(UpstreamModel):
    index: int = 0
    option_id: str = ""
    title: str = ""
    description: str = ""
    is_enabled: bool = False


class RawRestPayload(UpstreamModel):
    options: list[RawRestOptionPayload] = Field(default_factory=list)


class RawShopCardPayload(UpstreamModel):
    index: int = 0
    category: str = ""
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    card_type: str = ""
    rarity: str = ""
    costs_x: bool = False
    star_costs_x: bool = False
    energy_cost: int = 0
    star_cost: int = 0
    rules_text: str = ""
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
    price: int = 0
    on_sale: bool = False
    is_stocked: bool = False
    enough_gold: bool = False
    generated_cards: list[RawGeneratedCardPayload] = Field(default_factory=list)


class RawShopRelicPayload(UpstreamModel):
    index: int = 0
    relic_id: str = ""
    name: str = ""
    description: str | None = None
    rarity: str = ""
    price: int = 0
    is_stocked: bool = False
    enough_gold: bool = False


class RawShopPotionPayload(UpstreamModel):
    index: int = 0
    potion_id: str | None = None
    name: str | None = None
    description: str | None = None
    rarity: str | None = None
    usage: str | None = None
    price: int = 0
    is_stocked: bool = False
    enough_gold: bool = False


class RawShopCardRemovalPayload(UpstreamModel):
    price: int = 0
    available: bool = False
    used: bool = False
    enough_gold: bool = False


class RawShopPayload(UpstreamModel):
    is_open: bool = False
    can_open: bool = False
    can_close: bool = False
    cards: list[RawShopCardPayload] = Field(default_factory=list)
    relics: list[RawShopRelicPayload] = Field(default_factory=list)
    potions: list[RawShopPotionPayload] = Field(default_factory=list)
    card_removal: RawShopCardRemovalPayload | None = None


class RawRewardOptionPayload(UpstreamModel):
    index: int = 0
    reward_type: str = ""
    description: str = ""
    claimable: bool = False


class RawRewardCardOptionPayload(UpstreamModel):
    index: int = 0
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    card_type: str = ""
    rarity: str = ""
    energy_cost: int = 0
    costs_x: bool = False
    rules_text: str = ""
    dynamic_values: list[DynamicValue] = Field(default_factory=list)
    resolved_rules_text: str = ""
    generated_cards: list[RawGeneratedCardPayload] = Field(default_factory=list)


class RawRewardAlternativePayload(UpstreamModel):
    index: int = 0
    label: str = ""


class RawRewardPayload(UpstreamModel):
    pending_card_choice: bool = False
    can_proceed: bool = False
    rewards: list[RawRewardOptionPayload] = Field(default_factory=list)
    card_options: list[RawRewardCardOptionPayload] = Field(default_factory=list)
    alternatives: list[RawRewardAlternativePayload] = Field(default_factory=list)


class RawBundleCardPayload(UpstreamModel):
    """One card inside a Bundle (NCardBundle from NChooseABundleSelectionScreen)."""

    index: int = 0
    card_id: str = ""
    name: str = ""
    upgraded: bool = False
    card_type: str = ""
    rarity: str = ""
    energy_cost: int = 0
    costs_x: bool = False
    rules_text: str = ""
    resolved_rules_text: str = ""
    dynamic_values: list[DynamicValue] = Field(default_factory=list)


class RawBundlePayload(UpstreamModel):
    """One bundle option on a NChooseABundleSelectionScreen.

    Triggered by the ScrollBoxes Ancient relic: the agent picks one bundle
    and ALL its cards enter the deck.
    """

    index: int = 0
    cards: list[RawBundleCardPayload] = Field(default_factory=list)


class RawModalPayload(UpstreamModel):
    type_name: str = ""
    underlying_screen: str | None = None
    can_confirm: bool = False
    can_dismiss: bool = False
    confirm_label: str | None = None
    dismiss_label: str | None = None


class RawGameOverPayload(UpstreamModel):
    is_victory: bool = False
    floor: int | None = None
    character_id: str | None = None
    can_continue: bool = False
    can_return_to_main_menu: bool = False
    showing_summary: bool = False


class AgentViewCardStackItem(UpstreamModel):
    line: str = ""
    keywords: list[str] = Field(default_factory=list)
    mods: list[str] = Field(default_factory=list)


class AgentViewCombatPlayerPayload(UpstreamModel):
    hp: str = ""
    block: int = 0
    energy: int = 0
    stars: int = 0
    focus: int = 0
    orbs: list[str] = Field(default_factory=list)


class AgentViewCombatHandCardPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    type: str = ""
    playable: bool = False
    target: str | None = None
    targets: list[int] = Field(default_factory=list)
    why: str | None = None
    keywords: list[str] = Field(default_factory=list)
    mods: list[str] = Field(default_factory=list)


class AgentViewCombatEnemyPayload(UpstreamModel):
    i: int = 0
    name: str = ""
    hp: str = ""
    block: int = 0
    intent: str | None = None
    alive: bool = False
    hittable: bool = False


class AgentViewCombatPayload(UpstreamModel):
    player: AgentViewCombatPlayerPayload = Field(default_factory=AgentViewCombatPlayerPayload)
    hand: list[AgentViewCombatHandCardPayload] = Field(default_factory=list)
    draw: list[AgentViewCardStackItem] = Field(default_factory=list)
    discard: list[AgentViewCardStackItem] = Field(default_factory=list)
    exhaust: list[AgentViewCardStackItem] = Field(default_factory=list)
    enemies: list[AgentViewCombatEnemyPayload] = Field(default_factory=list)


class AgentViewRunPotionPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    usable: bool = False
    discard: bool = False
    target: str | None = None
    targets: list[int] = Field(default_factory=list)


class AgentViewRunPilesPayload(UpstreamModel):
    draw: list[AgentViewCardStackItem] = Field(default_factory=list)
    discard: list[AgentViewCardStackItem] = Field(default_factory=list)
    exhaust: list[AgentViewCardStackItem] = Field(default_factory=list)


class AgentViewRunPayload(UpstreamModel):
    character: str = ""
    floor: int = 0
    hp: str = ""
    gold: int = 0
    max_energy: int = 0
    base_orb_slots: int = 0
    deck: list[AgentViewCardStackItem] = Field(default_factory=list)
    relics: list[str] = Field(default_factory=list)
    potions: list[AgentViewRunPotionPayload] = Field(default_factory=list)
    piles: AgentViewRunPilesPayload = Field(default_factory=AgentViewRunPilesPayload)


class AgentViewChoiceCardPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    keywords: list[str] = Field(default_factory=list)
    mods: list[str] = Field(default_factory=list)


class AgentViewSelectionPayload(UpstreamModel):
    kind: str = ""
    prompt: str = ""
    min: int = 0
    max: int = 0
    selected: int = 0
    confirm: bool = False
    cards: list[AgentViewChoiceCardPayload] = Field(default_factory=list)
    selected_cards: list[AgentViewChoiceCardPayload] = Field(default_factory=list)
    selectable_cards: list[AgentViewChoiceCardPayload] = Field(default_factory=list)
    preview_cards: list[AgentViewChoiceCardPayload] = Field(default_factory=list)


class AgentViewCardsViewPayload(UpstreamModel):
    title: str = ""
    cards: list[AgentViewChoiceCardPayload] = Field(default_factory=list)


class AgentViewRewardOptionPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    claimable: bool = False


class AgentViewRewardAlternativePayload(UpstreamModel):
    i: int = 0
    line: str = ""


class AgentViewRewardPayload(UpstreamModel):
    pending_card_choice: bool = False
    can_proceed: bool = False
    rewards: list[AgentViewRewardOptionPayload] = Field(default_factory=list)
    cards: list[AgentViewChoiceCardPayload] = Field(default_factory=list)
    alternatives: list[AgentViewRewardAlternativePayload] = Field(default_factory=list)


class AgentViewEventOptionPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    locked: bool = False
    proceed: bool = False


class AgentViewEventPayload(UpstreamModel):
    id: str = ""
    title: str = ""
    finished: bool = False
    options: list[AgentViewEventOptionPayload] = Field(default_factory=list)


class AgentViewShopCardPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    affordable: bool = False
    keywords: list[str] = Field(default_factory=list)
    mods: list[str] = Field(default_factory=list)


class AgentViewShopItemPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    affordable: bool = False
    stocked: bool = False


class AgentViewShopRemovalPayload(UpstreamModel):
    price: int = 0
    affordable: bool = False
    available: bool = False
    used: bool = False


class AgentViewShopPayload(UpstreamModel):
    open: bool = False
    can_open: bool = False
    can_close: bool = False
    cards: list[AgentViewShopCardPayload] = Field(default_factory=list)
    relics: list[AgentViewShopItemPayload] = Field(default_factory=list)
    potions: list[AgentViewShopItemPayload] = Field(default_factory=list)
    remove: AgentViewShopRemovalPayload | None = None


class AgentViewRestOptionPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    enabled: bool = False


class AgentViewRestPayload(UpstreamModel):
    options: list[AgentViewRestOptionPayload] = Field(default_factory=list)


class AgentViewMapOptionPayload(UpstreamModel):
    i: int = 0
    line: str = ""


class AgentViewMapPayload(UpstreamModel):
    current: str | None = None
    options: list[AgentViewMapOptionPayload] = Field(default_factory=list)


class AgentViewCharacterSelectOptionPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    locked: bool = False
    selected: bool = False


class AgentViewCharacterSelectPayload(UpstreamModel):
    selected: str | None = None
    embark: bool = False
    ascension: int = 0
    characters: list[AgentViewCharacterSelectOptionPayload] = Field(default_factory=list)


class AgentViewTimelineSlotPayload(UpstreamModel):
    i: int = 0
    line: str = ""
    actionable: bool = False


class AgentViewTimelinePayload(UpstreamModel):
    back: bool = False
    confirm: bool = False
    slots: list[AgentViewTimelineSlotPayload] = Field(default_factory=list)


class AgentViewChestRelicPayload(UpstreamModel):
    i: int = 0
    line: str = ""


class AgentViewChestPayload(UpstreamModel):
    opened: bool = False
    claimed: bool = False
    relics: list[AgentViewChestRelicPayload] = Field(default_factory=list)


class AgentViewModalPayload(UpstreamModel):
    type: str = ""
    confirm: bool = False
    dismiss: bool = False
    confirm_label: str | None = None
    dismiss_label: str | None = None


class AgentViewGameOverPayload(UpstreamModel):
    victory: bool = False
    floor: int | None = None
    character: str | None = None
    can_continue: bool = False
    can_return: bool = False


class AgentViewPayload(UpstreamModel):
    version: int = 0
    screen: str = "UNKNOWN"
    run_id: str = "run_unknown"
    session: RawSessionPayload = Field(default_factory=RawSessionPayload)
    turn: int | None = None
    combat_type: str | None = None
    boss_stage: str | None = None
    is_final_boss: bool = False
    act: int | None = None
    actions: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    combat: AgentViewCombatPayload | None = None
    run: AgentViewRunPayload | None = None
    map: AgentViewMapPayload | None = None
    selection: AgentViewSelectionPayload | None = None
    cards_view: AgentViewCardsViewPayload | None = None
    character_select: AgentViewCharacterSelectPayload | None = None
    timeline: AgentViewTimelinePayload | None = None
    chest: AgentViewChestPayload | None = None
    event: AgentViewEventPayload | None = None
    shop: AgentViewShopPayload | None = None
    rest: AgentViewRestPayload | None = None
    reward: AgentViewRewardPayload | None = None
    modal: AgentViewModalPayload | None = None
    game_over: AgentViewGameOverPayload | None = None
    glossary: dict[str, str] = Field(default_factory=dict)


class UpstreamGameState(UpstreamModel):
    """Top-level upstream `/state.data` payload."""

    state_version: int = 0
    run_id: str = "run_unknown"
    screen: str = "UNKNOWN"
    session: RawSessionPayload = Field(default_factory=RawSessionPayload)
    in_combat: bool = False
    turn: int | None = None
    combat_type: str | None = None
    boss_stage: str | None = None
    is_final_boss: bool = False
    act: int | None = None
    boss_encounter_id: str | None = None
    second_boss_encounter_id: str | None = None
    available_actions: list[str] = Field(default_factory=list)
    combat: RawCombatPayload | None = None
    run: RawRunPayload | None = None
    multiplayer: RawMultiplayerPayload | None = None
    multiplayer_lobby: RawMultiplayerLobbyPayload | None = None
    map: RawMapPayload | None = None
    selection: RawSelectionPayload | None = None
    cards_view: RawCardsViewPayload | None = None
    character_select: RawCharacterSelectPayload | None = None
    timeline: RawTimelinePayload | None = None
    chest: RawChestPayload | None = None
    event: RawEventPayload | None = None
    crystal_sphere: RawCrystalSpherePayload | None = None
    shop: RawShopPayload | None = None
    rest: RawRestPayload | None = None
    reward: RawRewardPayload | None = None
    bundles: list[RawBundlePayload] | None = None
    modal: RawModalPayload | None = None
    game_over: RawGameOverPayload | None = None
    agent_view: AgentViewPayload | None = None


def get_damage_block_from_dynamic_values(
    dvs: list[DynamicValue],
) -> tuple[int | None, int | None, int | None]:
    """Extract (damage, block, hits) from DynamicValue list.

    Returns (None, None, None) if empty (v0.5.2 compat).
    """
    if not dvs:
        return None, None, None
    damage = block = hits = None
    for dv in dvs:
        nl = dv.name.lower()
        if nl in ("damage", "calculateddamage"):
            damage = int(dv.current_value)
        elif nl in ("block", "calculatedblock"):
            block = int(dv.current_value)
        elif nl in ("hits", "calculatedhits"):
            hits = int(dv.current_value)
    return damage, block, hits
