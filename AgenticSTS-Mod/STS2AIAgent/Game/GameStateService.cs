using System.Collections;
using System.Globalization;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Reflection;
using System.Text.RegularExpressions;
using Godot;
using MegaCrit.Sts2.Core.CardSelection;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.CardRewardAlternatives;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Merchant;
using MegaCrit.Sts2.Core.Entities.Multiplayer;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Potions;
using MegaCrit.Sts2.Core.Entities.RestSite;
using MegaCrit.Sts2.Core.Events;
using MegaCrit.Sts2.Core.Events.Custom.CrystalSphereEvent;
using MegaCrit.Sts2.Core.HoverTips;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.Helpers;
using MegaCrit.Sts2.Core.Map;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Characters;
using MegaCrit.Sts2.Core.Models.Powers;
using MegaCrit.Sts2.Core.Models.Relics;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Multiplayer.Game;
using MegaCrit.Sts2.Core.Multiplayer.Game.Lobby;
using MegaCrit.Sts2.Core.MonsterMoves.Intents;
using MegaCrit.Sts2.Core.Nodes;
using MegaCrit.Sts2.Core.Nodes.Cards;
using MegaCrit.Sts2.Core.Nodes.Cards.Holders;
using MegaCrit.Sts2.Core.Nodes.Combat;
using MegaCrit.Sts2.Core.Nodes.CommonUi;
using MegaCrit.Sts2.Core.Nodes.Events;
using MegaCrit.Sts2.Core.Nodes.Events.Custom.CrystalSphere;
using MegaCrit.Sts2.Core.Nodes.Debug.Multiplayer;
using MegaCrit.Sts2.Core.Nodes.GodotExtensions;
using MegaCrit.Sts2.Core.Nodes.Rewards;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Nodes.Screens;
using MegaCrit.Sts2.Core.Nodes.Screens.Capstones;
using MegaCrit.Sts2.Core.Nodes.Screens.CardSelection;
using MegaCrit.Sts2.Core.Nodes.Screens.CharacterSelect;
using MegaCrit.Sts2.Core.Nodes.Screens.GameOverScreen;
using MegaCrit.Sts2.Core.Nodes.Screens.InspectScreens;
using MegaCrit.Sts2.Core.Nodes.Screens.MainMenu;
using MegaCrit.Sts2.Core.Nodes.Screens.Map;
using MegaCrit.Sts2.Core.Nodes.Screens.PauseMenu;
using MegaCrit.Sts2.Core.Nodes.Screens.ScreenContext;
using MegaCrit.Sts2.Core.Nodes.Screens.Shops;
using MegaCrit.Sts2.Core.Nodes.Screens.Timeline;
using MegaCrit.Sts2.Core.Nodes.Screens.Timeline.UnlockScreens;
using MegaCrit.Sts2.Core.Nodes.Screens.TreasureRoomRelic;
using MegaCrit.Sts2.Core.Nodes.TopBar;
using MegaCrit.Sts2.Core.Rooms;
using MegaCrit.Sts2.Core.Rewards;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Timeline;
using MegaCrit.Sts2.addons.mega_text;

namespace STS2AIAgent.Game;

internal static class GameStateService
{
    private const int StateVersion = 10;
    private const int AgentViewVersion = 3;
    private const string EnergyIconToken = "__STS2_ENERGY_ICON__";
    private const string StarIconToken = "__STS2_STAR_ICON__";
    private const string HpIconToken = "__STS2_HP_ICON__";
    private static readonly string[] EventHpCostCandidates = { "HpCost", "HealthCost", "HPCost", "LifeCost" };
    private static readonly string[] EventGoldCostCandidates = { "GoldCost", "Cost", "Price" };
    private static readonly string[] EventCardMemberCandidates =
    {
        "Card", "Cards", "CardReward", "CardRewards", "RewardCard", "RewardCards",
        "CardsOffered", "OfferedCards", "PreviewCard", "PreviewCards"
    };
    private static readonly string[] EventRelicMemberCandidates =
    {
        "Relic", "Relics", "RelicReward", "RelicRewards", "RewardRelic", "RewardRelics",
        "RelicPreview", "PreviewRelic", "PreviewRelics"
    };
    private static readonly string[] EventPotionMemberCandidates =
    {
        "Potion", "Potions", "PotionReward", "PotionRewards", "RewardPotion", "RewardPotions",
        "PotionPreview", "PreviewPotion", "PreviewPotions"
    };
    private static readonly string[] EventCurseMemberCandidates =
    {
        "Curse", "Curses", "CurseCard", "CurseCards", "CurseReward", "CurseRewards"
    };
    private static readonly string[] KnownEventCurseNames =
    {
        "Ascender's Bane", "Clumsy", "Curse of the Bell", "Decay", "Doubt", "Injury",
        "Necronomicurse", "Normality", "Pain", "Parasite", "Pride", "Regret",
        "Shame", "Writhe"
    };
    private static readonly IReadOnlyDictionary<string, EventCardInfo> EventCardTextFallbacks =
        new Dictionary<string, EventCardInfo>(StringComparer.OrdinalIgnoreCase)
        {
            ["Clumsy"] = new()
            {
                name = "Clumsy",
                cost = -1,
                type = "Curse",
                rules_text = "Unplayable. Ethereal.",
                is_upgraded = false
            },
            ["Spoils Map"] = new()
            {
                name = "Spoils Map",
                cost = -1,
                type = "Quest",
                rules_text = "Marks a site of 600 extra Gold in the next Act.",
                is_upgraded = false
            }
        };
    private static readonly string[] DebugInterestingNodeKeywords =
    {
        "Card", "Potion", "Tooltip", "ToolTip", "Preview", "Hover", "Relic", "Reward"
    };
    private static readonly string[] EventReflectionCandidateMembers =
        EventHpCostCandidates
            .Concat(EventGoldCostCandidates)
            .Concat(EventCardMemberCandidates)
            .Concat(EventRelicMemberCandidates)
            .Concat(EventPotionMemberCandidates)
            .Concat(EventCurseMemberCandidates)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    private static readonly string[] EventDebugMemberCandidates =
        EventReflectionCandidateMembers
            .Concat(new[]
            {
                "Card", "Cards", "CardModel", "CardModels", "Preview", "PreviewCard", "PreviewCards",
                "Tooltip", "ToolTip", "TooltipData", "HoverPreview", "Reward", "Rewards",
                "Potion", "Potions", "PotionModel", "PotionModels", "Relic", "Relics",
                "Description", "DynamicDescription", "Title", "Name", "Label", "Text"
            })
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    private static readonly Regex EventHpCostRegex =
        new(@"(?:Lose|Pay)\s+\[?[^\d\]]*\]?(\d+)\s+(?:Max\s+)?HP", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex EventGoldCostRegex =
        new(@"(?:Lose|Pay)\s+\[?[^\d\]]*\]?(\d+)\s+Gold", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex EventRandomRelicRegex =
        new(@"\brandom\s+(?:(?<rarity>common|uncommon|rare|boss|shop|ancient)\s+)?relic\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex EventRandomPotionRegex =
        new(@"\brandom\s+(?:(?<rarity>common|uncommon|rare)\s+)?potion\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex EventGenericCurseRegex =
        new(@"\b(?:add|shuffle|put|obtain|receive|gain)\s+(?:a|an|\d+)\s+curse\b|\bcursed\s+with\b", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly object EventReflectionProbeLock = new();
    private static readonly HashSet<string> EventReflectionProbeSeen = new(StringComparer.Ordinal);
    private static readonly IReadOnlyDictionary<int, string> BossStageByFloor = new Dictionary<int, string>
    {
        [17] = "act1_boss",
        [34] = "act2_boss",
        [51] = "final_boss"
    };

    private readonly record struct EncounterMetadata(
        string? CombatType,
        string? BossStage,
        bool IsFinalBoss,
        int? Act);

    public static GameStatePayload BuildStatePayload()
    {
        var currentScreen = ActiveScreenContext.Instance.GetCurrentScreen();
        var combatState = CombatManager.Instance.DebugOnlyGetState();
        var runState = RunManager.Instance.DebugOnlyGetState();
        var screen = ResolveScreen(currentScreen);
        var session = BuildSessionPayload(currentScreen, runState);
        var availableActions = BuildAvailableActionNames(currentScreen, combatState, runState);
        var combat = BuildCombatPayload(combatState);
        var run = BuildRunPayload(currentScreen, combatState, runState);
        var multiplayer = BuildMultiplayerPayload(currentScreen, runState);
        var multiplayerLobby = BuildMultiplayerLobbyPayload(currentScreen);
        var map = BuildMapPayload(currentScreen, runState);
        var selection = BuildSelectionPayload(currentScreen);
        var cardsView = BuildCardsViewPayload(currentScreen);
        var characterSelect = BuildCharacterSelectPayload(currentScreen);
        var timeline = BuildTimelinePayload(currentScreen);
        var chest = BuildChestPayload(currentScreen);
        var eventPayload = BuildEventPayload(currentScreen);
        var crystalSphere = BuildCrystalSpherePayload(currentScreen);
        var shop = BuildShopPayload(currentScreen);
        var rest = BuildRestPayload(currentScreen);
        var reward = BuildRewardPayload(currentScreen);
        var bundles = BuildBundlesPayload(currentScreen);
        var modal = BuildModalPayload(currentScreen);
        var gameOver = BuildGameOverPayload(currentScreen, runState);
        var encounterMetadata = ResolveEncounterMetadata(currentScreen, combatState, runState);

        return new GameStatePayload
        {
            state_version = StateVersion,
            run_id = runState?.Rng.StringSeed ?? "run_unknown",
            screen = screen,
            session = session,
            in_combat = CombatManager.Instance.IsInProgress,
            turn = combatState?.RoundNumber,
            combat_type = encounterMetadata.CombatType,
            boss_stage = encounterMetadata.BossStage,
            is_final_boss = encounterMetadata.IsFinalBoss,
            act = encounterMetadata.Act,
            boss_encounter_id = runState?.Act?.BossEncounter?.Id.Entry,
            second_boss_encounter_id = runState?.Act?.SecondBossEncounter?.Id.Entry,
            available_actions = availableActions,
            combat = combat,
            run = run,
            multiplayer = multiplayer,
            multiplayer_lobby = multiplayerLobby,
            map = map,
            selection = selection,
            cards_view = cardsView,
            character_select = characterSelect,
            timeline = timeline,
            chest = chest,
            @event = eventPayload,
            crystal_sphere = crystalSphere,
            shop = shop,
            rest = rest,
            reward = reward,
            bundles = bundles,
            modal = modal,
            game_over = gameOver,
            agent_view = BuildAgentViewPayload(
                screen,
                session,
                runState?.Rng.StringSeed ?? "run_unknown",
                combatState?.RoundNumber,
                availableActions,
                combatState,
                runState,
                combat,
                run,
                map,
                selection,
                cardsView,
                characterSelect,
                timeline,
                chest,
                eventPayload,
                shop,
                rest,
                reward,
                modal,
                gameOver,
                encounterMetadata)
        };
    }

    private static SessionPayload BuildSessionPayload(IScreenContext? currentScreen, RunState? runState)
    {
        if (GetMultiplayerTestScene() != null)
        {
            return new SessionPayload
            {
                mode = "multiplayer",
                phase = "multiplayer_lobby",
                control_scope = "local_player"
            };
        }

        var characterSelectScreen = GetCharacterSelectScreen(currentScreen);
        if (characterSelectScreen != null)
        {
            return new SessionPayload
            {
                mode = characterSelectScreen.Lobby.NetService.Type.IsMultiplayer() ? "multiplayer" : "singleplayer",
                phase = "character_select",
                control_scope = "local_player"
            };
        }

        if (runState != null)
        {
            return new SessionPayload
            {
                mode = RunManager.Instance.NetService.Type.IsMultiplayer() ? "multiplayer" : "singleplayer",
                phase = "run",
                control_scope = "local_player"
            };
        }

        return new SessionPayload
        {
            mode = "singleplayer",
            phase = "menu",
            control_scope = "local_player"
        };
    }

    public static AvailableActionsPayload BuildAvailableActionsPayload()
    {
        var currentScreen = ActiveScreenContext.Instance.GetCurrentScreen();
        var combatState = CombatManager.Instance.DebugOnlyGetState();
        var runState = RunManager.Instance.DebugOnlyGetState();
        var descriptors = new List<ActionDescriptor>();

        if (GetOpenModal() != null)
        {
            if (CanConfirmModal(currentScreen))
            {
                descriptors.Add(new ActionDescriptor
                {
                    name = "confirm_modal",
                    requires_target = false,
                    requires_index = false
                });
            }

            if (CanDismissModal(currentScreen))
            {
                descriptors.Add(new ActionDescriptor
                {
                    name = "dismiss_modal",
                    requires_target = false,
                    requires_index = false
                });
            }

            return new AvailableActionsPayload
            {
                screen = ResolveScreen(currentScreen),
                actions = descriptors.ToArray()
            };
        }

        if (CanEndTurn(currentScreen, combatState))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "end_turn",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanPlayAnyCard(currentScreen, combatState))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "play_card",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanContinueRun(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "continue_run",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanAbandonRun(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "abandon_run",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanOpenCharacterSelect(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "open_character_select",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanOpenTimeline(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "open_timeline",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanCloseMainMenuSubmenu(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "close_main_menu_submenu",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanChooseTimelineEpoch(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "choose_timeline_epoch",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanConfirmTimelineOverlay(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "confirm_timeline_overlay",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanChooseMapNode(currentScreen, runState))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "choose_map_node",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanCollectRewardsAndProceed(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "collect_rewards_and_proceed",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanResolveRewards(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "resolve_rewards",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanClaimReward(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "claim_reward",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanChooseRewardCard(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "choose_reward_card",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanChooseRewardAlternative(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "choose_reward_alternative",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanSkipRewardCards(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "skip_reward_cards",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanSacrificeRewardCards(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "sacrifice_reward_cards",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanSelectDeckCard(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "select_deck_card",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanCloseCardsView(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "close_cards_view",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanCloseCapstoneOverlay(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "close_capstone_overlay",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanClosePauseMenu(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "close_pause_menu",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanCancelSelection(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "cancel_selection",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanConfirmSelection(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "confirm_selection",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanProceed(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "proceed",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanOpenChest(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "open_chest",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanChooseTreasureRelic(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "choose_treasure_relic",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanChooseEventOption(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "choose_event_option",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanChooseRestOption(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "choose_rest_option",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanOpenShopInventory(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "open_shop_inventory",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanCloseShopInventory(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "close_shop_inventory",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanBuyShopCard(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "buy_card",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanBuyShopRelic(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "buy_relic",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanBuyShopPotion(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "buy_potion",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanRemoveCardAtShop(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "remove_card_at_shop",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanSelectCharacter(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "select_character",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanEmbark(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "embark",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanUnready(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "unready",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanHostMultiplayerLobby(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "host_multiplayer_lobby",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanJoinMultiplayerLobby(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "join_multiplayer_lobby",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanReadyMultiplayerLobby(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "ready_multiplayer_lobby",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanDisconnectMultiplayerLobby(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "disconnect_multiplayer_lobby",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanIncreaseAscension(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "increase_ascension",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanDecreaseAscension(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "decrease_ascension",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanUsePotion(currentScreen, combatState, runState))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "use_potion",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanDiscardPotion(currentScreen, runState))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "discard_potion",
                requires_target = false,
                requires_index = true
            });
        }

        if (CanSaveAndQuit(currentScreen, runState))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "save_and_quit",
                requires_target = false,
                requires_index = false
            });
        }

        if (CanReturnToMainMenu(currentScreen))
        {
            descriptors.Add(new ActionDescriptor
            {
                name = "return_to_main_menu",
                requires_target = false,
                requires_index = false
            });
        }

        return new AvailableActionsPayload
        {
            screen = ResolveScreen(currentScreen),
            actions = descriptors.ToArray()
        };
    }

    public static string ResolveScreen(IScreenContext? currentScreen)
    {
        if (GetOpenModal() != null)
        {
            return "MODAL";
        }

        var screen = ResolveNonModalScreen(currentScreen);
        if (screen == "UNKNOWN" && currentScreen != null)
        {
            Log.Warn($"[STS2AIAgent] Unhandled screen type: {currentScreen.GetType().FullName}");
        }

        return screen;
    }

    public static bool CanEndTurn(IScreenContext? currentScreen, CombatState? combatState)
    {
        if (!CanUseCombatActions(currentScreen, combatState, out _, out _))
        {
            return false;
        }

        return !CombatManager.Instance.IsPlayerReadyToEndTurn(LocalContext.GetMe(combatState)!);
    }

    public static bool CanPlayAnyCard(IScreenContext? currentScreen, CombatState? combatState)
    {
        if (!CanUseCombatActions(currentScreen, combatState, out var me, out _))
        {
            return false;
        }

        return me!.PlayerCombatState!.Hand.Cards.Any(IsCardPlayable);
    }

    public static Player? GetLocalPlayer(CombatState? combatState)
    {
        return LocalContext.GetMe(combatState);
    }

    public static Player? GetLocalPlayer(RunState? runState)
    {
        return LocalContext.GetMe(runState);
    }

    /// <summary>
    /// True when the local player is in the card-play phase of their turn.
    /// Replaces <c>CombatManager.IsPlayPhase</c>, which game v0.107.1 removed in
    /// favor of the per-player <see cref="PlayerCombatState.Phase"/> enum
    /// (<c>Start -&gt; AutoPrePlay -&gt; Play -&gt; AutoPostPlay -&gt; End</c>).
    /// </summary>
    public static bool IsLocalPlayerInPlayPhase()
    {
        var combatState = CombatManager.Instance.DebugOnlyGetState();
        return GetLocalPlayer(combatState)?.PlayerCombatState?.Phase == PlayerTurnPhase.Play;
    }

    public static bool CanChooseMapNode(IScreenContext? currentScreen, RunState? runState)
    {
        return GetAvailableMapNodes(currentScreen, runState).Count > 0;
    }

    public static bool CanCollectRewardsAndProceed(IScreenContext? currentScreen)
    {
        return currentScreen is NRewardsScreen || currentScreen is NCardRewardSelectionScreen;
    }

    public static bool CanResolveRewards(IScreenContext? currentScreen)
    {
        // Atomic resolve_rewards is available everywhere collect_rewards_and_proceed is.
        // The agent can call it from either NRewardsScreen (combat_rewards) or
        // NCardRewardSelectionScreen (card_reward) to drain the entire reward chain
        // in one mod-side call (see ExecuteResolveRewardsAsync).
        return CanCollectRewardsAndProceed(currentScreen);
    }

    public static bool CanClaimReward(IScreenContext? currentScreen)
    {
        return GetRewardButtons(currentScreen).Any(button => button.IsEnabled);
    }

    public static bool CanChooseRewardCard(IScreenContext? currentScreen)
    {
        return GetCardRewardOptions(currentScreen).Count > 0;
    }

    public static bool CanChooseRewardAlternative(IScreenContext? currentScreen)
    {
        return GetCardRewardAlternativeButtons(currentScreen).Count > 0;
    }

    public static bool CanSkipRewardCards(IScreenContext? currentScreen)
    {
        return FindSkipRewardButton(GetCardRewardAlternativeButtons(currentScreen)) != null;
    }

    public static bool CanSacrificeRewardCards(IScreenContext? currentScreen)
    {
        return FindSacrificeButton(GetCardRewardAlternativeButtons(currentScreen)) != null;
    }

    public static string GetRewardAlternativeLabel(NCardRewardAlternativeButton button)
    {
        // Resolve through CardRewardAlternative.Title (LocString) when reachable
        // so the label is locale-blind English. Fallback to the rendered Godot
        // label only if reflection misses.
        var fromAlt = TryGetRewardAlternativeTitleFromScreen(button);
        if (!string.IsNullOrEmpty(fromAlt))
            return fromAlt;
        return button.GetNodeOrNull<MegaLabel>("Label")?.Text ?? button.Name;
    }

    /// <summary>
    /// Walks up from the button to its NCardRewardSelectionScreen parent, finds
    /// the matching CardRewardAlternative in the screen's private _extraOptions
    /// list, and resolves its Title (a LocString) through EnglishLocResolver.
    /// Returns null if the parent screen / field / matching alternative is not
    /// reachable.
    /// </summary>
    private static string? TryGetRewardAlternativeTitleFromScreen(NCardRewardAlternativeButton button)
    {
        if (button == null) return null;
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;

        // Walk up to find the screen carrying _extraOptions: IReadOnlyList<CardRewardAlternative>.
        Node? cursor = button;
        for (int hop = 0; hop < 8 && cursor != null; hop++)
        {
            var t = cursor.GetType();
            FieldInfo? listField = null;
            while (t != null && t != typeof(object))
            {
                listField = t.GetField("_extraOptions", flags);
                if (listField != null) break;
                t = t.BaseType;
            }
            if (listField != null)
            {
                if (listField.GetValue(cursor) is IEnumerable<CardRewardAlternative> alternatives)
                {
                    var altList = alternatives as IReadOnlyList<CardRewardAlternative>
                        ?? alternatives.ToList();
                    // Index by sibling order under _rewardAlternativesContainer.
                    var siblings = button.GetParent()?.GetChildren()
                        .OfType<NCardRewardAlternativeButton>()
                        .ToList();
                    var idx = siblings?.IndexOf(button) ?? -1;
                    if (idx >= 0 && idx < altList.Count && altList[idx].Title != null)
                    {
                        return EnglishLocResolver.Resolve(altList[idx].Title);
                    }
                }
                return null;
            }
            cursor = cursor.GetParent();
        }
        return null;
    }

    public static NCardRewardAlternativeButton? FindRewardAlternativeButton(
        IReadOnlyList<NCardRewardAlternativeButton> alternatives,
        string label)
    {
        return alternatives.FirstOrDefault(button =>
            GetRewardAlternativeLabel(button).Contains(label, StringComparison.OrdinalIgnoreCase));
    }

    public static NCardRewardAlternativeButton? FindSkipRewardButton(IReadOnlyList<NCardRewardAlternativeButton> alternatives)
    {
        return FindRewardAlternativeButton(alternatives, "Skip");
    }

    public static NCardRewardAlternativeButton? FindSacrificeButton(IReadOnlyList<NCardRewardAlternativeButton> alternatives)
    {
        return FindRewardAlternativeButton(alternatives, "Sacrifice");
    }

    public static bool CanSelectDeckCard(IScreenContext? currentScreen)
    {
        return currentScreen is NChooseABundleSelectionScreen
            ? GetBundleSelectionOptions(currentScreen).Count > 0
            : GetDeckSelectionOptions(currentScreen).Count > 0;
    }

    public static bool CanCloseCardsView(IScreenContext? currentScreen)
    {
        return GetCardsViewBackButton(currentScreen) != null;
    }

    /// <summary>
    /// Closeable overlay state — the player accidentally opened an overlay
    /// (TopBar deck button, TopBar map button mid-combat, a pile-view from
    /// combat, or a card/relic inspect zoom) and needs to be sent back to
    /// the underlying screen.
    ///
    /// Coverage:
    ///   1. NCapstoneContainer (deck view, map-from-topbar, pile views, any
    ///      other ICapstoneScreen) — closed via NCapstoneContainer.Close().
    ///   2. NInspectCardScreen / NInspectRelicScreen — independent zoom
    ///      overlays that ESC normally dismisses.  Both have public Close()
    ///      and live as floating Control nodes in the scene tree, so we
    ///      detect them by walking the tree (same pattern as the pause menu).
    ///   3. Standalone NMapScreen.IsOpen (no capstone wrapper) — only when
    ///      a combat is active, so closing makes sense (we'd be returning
    ///      to combat, not breaking normal map navigation).
    /// </summary>
    public static bool CanCloseCapstoneOverlay(IScreenContext? currentScreen)
    {
        var capstone = NCapstoneContainer.Instance;
        if (capstone != null && capstone.InUse)
        {
            return true;
        }

        if (FindVisibleInspectCardScreen() != null || FindVisibleInspectRelicScreen() != null)
        {
            return true;
        }

        if (currentScreen is NMapScreen mapScreen && mapScreen.IsOpen)
        {
            return CombatManager.Instance.IsInProgress;
        }

        return false;
    }

    /// <summary>
    /// Walk the scene tree for a visible NInspectCardScreen.  These are
    /// instantiated on demand by NDeckViewScreen / NCardsViewScreen and do
    /// not register themselves as the ActiveScreenContext, so a tree walk
    /// is the only reliable detection.
    /// </summary>
    public static NInspectCardScreen? FindVisibleInspectCardScreen()
    {
        var root = NGame.Instance?.GetTree()?.Root;
        if (root == null) return null;
        return FindDescendants<NInspectCardScreen>(root)
            .FirstOrDefault(n => GodotObject.IsInstanceValid(n) && n.IsVisibleInTree());
    }

    public static NInspectRelicScreen? FindVisibleInspectRelicScreen()
    {
        var root = NGame.Instance?.GetTree()?.Root;
        if (root == null) return null;
        return FindDescendants<NInspectRelicScreen>(root)
            .FirstOrDefault(n => GodotObject.IsInstanceValid(n) && n.IsVisibleInTree());
    }

    /// <summary>
    /// Pause menu is a UI overlay, not a capstone — it has its own toggle
    /// path via the TopBar pause button.  Same OnRelease() the in-game ESC
    /// hotkey triggers will hide it.
    /// </summary>
    public static bool CanClosePauseMenu(IScreenContext? currentScreen)
    {
        if (currentScreen is NPauseMenu)
        {
            return true;
        }

        // The pause menu is a UI overlay so GetCurrentScreen() may report
        // the underlying screen.  Search the scene tree.
        var root = NGame.Instance?.GetTree()?.Root;
        if (root == null)
        {
            return false;
        }

        return FindDescendants<NPauseMenu>(root)
            .Any(pm => GodotObject.IsInstanceValid(pm) && pm.IsVisibleInTree());
    }

    public static bool CanCancelSelection(IScreenContext? currentScreen)
    {
        return GetSelectionCancelButton(currentScreen) != null;
    }

    public static NButton? GetSelectionCancelButton(IScreenContext? currentScreen)
    {
        // NDeckUpgradeSelectScreen (Smith) has a close button at "%Close"
        if (currentScreen is NDeckUpgradeSelectScreen upgradeScreen)
        {
            var closeButton = upgradeScreen.GetNodeOrNull<NBackButton>("%Close");
            if (closeButton is { IsEnabled: true })
                return closeButton;
        }
        // NChooseACardSelectionScreen has a skip button at "SkipButton"
        if (currentScreen is NChooseACardSelectionScreen chooseScreen)
        {
            var skipButton = chooseScreen.GetNodeOrNull<NButton>("SkipButton");
            if (skipButton is { Visible: true, IsEnabled: true })
                return skipButton;
        }
        return null;
    }

    public static bool CanConfirmSelection(IScreenContext? currentScreen)
    {
        return TryGetSelectionConfirmButton(currentScreen, out _);
    }

    public static bool CanProceed(IScreenContext? currentScreen)
    {
        if (currentScreen is NRewardsScreen or NCardRewardSelectionScreen)
        {
            return false;
        }

        return GetProceedButton(currentScreen) != null;
    }

    public static bool CanOpenChest(IScreenContext? currentScreen)
    {
        if (currentScreen is not NTreasureRoom treasureRoom)
        {
            return false;
        }

        var chestButton = treasureRoom.GetNodeOrNull<NButton>("%Chest");
        return chestButton != null && GodotObject.IsInstanceValid(chestButton) && chestButton.IsEnabled;
    }

    public static bool CanChooseTreasureRelic(IScreenContext? currentScreen)
    {
        if (GetTreasureRelicCollection(currentScreen) == null)
        {
            return false;
        }

        var relics = RunManager.Instance.TreasureRoomRelicSynchronizer.CurrentRelics;
        return relics != null && relics.Count > 0;
    }

    public static NTreasureRoomRelicCollection? GetTreasureRelicCollection(IScreenContext? currentScreen)
    {
        if (currentScreen is NTreasureRoomRelicCollection relicCollection)
        {
            return relicCollection;
        }

        if (currentScreen is NTreasureRoom treasureRoom)
        {
            var nestedCollection = treasureRoom.GetNodeOrNull<NTreasureRoomRelicCollection>("%RelicCollection");
            if (nestedCollection != null &&
                GodotObject.IsInstanceValid(nestedCollection) &&
                nestedCollection.Visible)
            {
                return nestedCollection;
            }
        }

        return null;
    }

    public static bool CanChooseEventOption(IScreenContext? currentScreen)
    {
        // Crystal Sphere is exposed via the dedicated `crystal_sphere_*` actions
        // (see BuildCrystalSpherePayload). The generic event-option path no
        // longer applies to it.
        if (currentScreen is NCrystalSphereScreen)
        {
            return false;
        }

        if (!TryGetActiveEventModel(currentScreen, out var eventModel) || eventModel == null)
        {
            return false;
        }

        try
        {
            // Finished events have a synthetic proceed option
            if (eventModel.IsFinished)
            {
                return true;
            }

            // Non-finished events need at least one non-locked option
            return eventModel.CurrentOptions.Any(o => !o.IsLocked);
        }
        catch
        {
            return false;
        }
    }

    internal static bool TryGetActiveEventModel(IScreenContext? currentScreen, out EventModel? eventModel)
    {
        eventModel = null;

        if (currentScreen is NCrystalSphereScreen)
        {
            try
            {
                eventModel = RunManager.Instance.EventSynchronizer.GetLocalEvent();
                return eventModel != null;
            }
            catch
            {
                eventModel = null;
                return false;
            }
        }

        if (IsExplicitNonEventScreen(currentScreen))
        {
            return false;
        }

        try
        {
            eventModel = RunManager.Instance.EventSynchronizer.GetLocalEvent();
            if (eventModel == null)
            {
                return false;
            }

            return currentScreen is NEventRoom ||
                   eventModel.IsFinished ||
                   eventModel.CurrentOptions.Count > 0;
        }
        catch
        {
            eventModel = null;
            return false;
        }
    }

    internal static bool IsEventScreenActive(IScreenContext? currentScreen)
    {
        return currentScreen is NCrystalSphereScreen || TryGetActiveEventModel(currentScreen, out _);
    }

    private static bool IsExplicitNonEventScreen(IScreenContext? currentScreen)
    {
        return currentScreen switch
        {
            null => true,
            NPauseMenu => true,
            NGameOverScreen => true,
            NCardRewardSelectionScreen => true,
            NChooseACardSelectionScreen => true,
            NChooseABundleSelectionScreen => true,
            NDeckCardSelectScreen or NDeckUpgradeSelectScreen or NDeckTransformSelectScreen or NDeckEnchantSelectScreen => true,
            NCardGridSelectionScreen => true,
            NCardsViewScreen => true,
            NRewardsScreen => true,
            NTreasureRoom or NTreasureRoomRelicCollection => true,
            NRestSiteRoom => true,
            NMerchantRoom or NMerchantInventory => true,
            NCombatRoom => true,
            NMapScreen or NMapRoom => true,
            NCharacterSelectScreen => true,
            NTimelineScreen => true,
            NPatchNotesScreen => true,
            NSubmenu => true,
            NLogoAnimation => true,
            NMainMenu => true,
            _ => false
        };
    }

    public static bool CanChooseRestOption(IScreenContext? currentScreen)
    {
        if (currentScreen is not NRestSiteRoom)
        {
            return false;
        }

        try
        {
            var options = RunManager.Instance.RestSiteSynchronizer.GetLocalOptions();
            return options != null && options.Any(o => o.IsEnabled);
        }
        catch
        {
            return false;
        }
    }

    public static bool CanOpenShopInventory(IScreenContext? currentScreen)
    {
        if (TryGetActiveEventModel(currentScreen, out _))
        {
            return false;
        }

        var room = GetMerchantRoom(currentScreen);
        return room != null && room.Inventory != null && !room.Inventory.IsOpen && currentScreen is NMerchantRoom;
    }

    public static bool CanCloseShopInventory(IScreenContext? currentScreen)
    {
        if (TryGetActiveEventModel(currentScreen, out _))
        {
            return false;
        }

        return currentScreen is NMerchantInventory inventory && inventory.IsOpen;
    }

    public static bool CanBuyShopCard(IScreenContext? currentScreen)
    {
        if (TryGetActiveEventModel(currentScreen, out _))
        {
            return false;
        }

        var inventoryScreen = GetMerchantInventoryScreen(currentScreen);
        return inventoryScreen != null && inventoryScreen.IsOpen &&
            GetMerchantCardEntries(currentScreen).Any(entry => entry.IsStocked && entry.EnoughGold);
    }

    public static bool CanBuyShopRelic(IScreenContext? currentScreen)
    {
        if (TryGetActiveEventModel(currentScreen, out _))
        {
            return false;
        }

        var inventoryScreen = GetMerchantInventoryScreen(currentScreen);
        return inventoryScreen != null && inventoryScreen.IsOpen &&
            GetMerchantRelicEntries(currentScreen).Any(entry => entry.IsStocked && entry.EnoughGold);
    }

    public static bool CanBuyShopPotion(IScreenContext? currentScreen)
    {
        if (TryGetActiveEventModel(currentScreen, out _))
        {
            return false;
        }

        var inventoryScreen = GetMerchantInventoryScreen(currentScreen);
        var inventory = GetMerchantInventory(currentScreen);
        return inventoryScreen != null && inventoryScreen.IsOpen &&
            GetMerchantPotionEntries(currentScreen).Any(entry => CanPurchaseShopPotion(inventory?.Player, entry));
    }

    public static bool CanRemoveCardAtShop(IScreenContext? currentScreen)
    {
        if (TryGetActiveEventModel(currentScreen, out _))
        {
            return false;
        }

        var inventoryScreen = GetMerchantInventoryScreen(currentScreen);
        var entry = GetMerchantCardRemovalEntry(currentScreen);
        return inventoryScreen != null && inventoryScreen.IsOpen &&
            entry?.IsStocked == true && entry.EnoughGold;
    }

    public static bool CanSelectCharacter(IScreenContext? currentScreen)
    {
        var multiplayerTestScene = GetMultiplayerTestScene();
        if (multiplayerTestScene != null)
        {
            return GetMultiplayerTestLobby(multiplayerTestScene) != null && GetMultiplayerLobbyCharacters().Length > 0;
        }

        return GetCharacterSelectButtons(currentScreen)
            .Any(button => !button.IsLocked && button.IsEnabled && button.IsVisibleInTree());
    }

    public static bool CanContinueRun(IScreenContext? currentScreen)
    {
        if (currentScreen is not NMainMenu mainMenu || !mainMenu.IsVisibleInTree())
        {
            return false;
        }

        if (mainMenu.SubmenuStack?.SubmenusOpen == true)
        {
            return false;
        }

        var continueButton = GetMainMenuContinueButton(mainMenu);
        return continueButton != null && continueButton.IsVisibleInTree() && continueButton.IsEnabled;
    }

    public static bool CanAbandonRun(IScreenContext? currentScreen)
    {
        if (currentScreen is not NMainMenu mainMenu || !mainMenu.IsVisibleInTree())
        {
            return false;
        }

        if (mainMenu.SubmenuStack?.SubmenusOpen == true)
        {
            return false;
        }

        var abandonButton = GetMainMenuAbandonRunButton(mainMenu);
        return abandonButton != null && abandonButton.IsVisibleInTree() && abandonButton.IsEnabled;
    }

    public static bool CanOpenCharacterSelect(IScreenContext? currentScreen)
    {
        if (currentScreen is not NMainMenu mainMenu || !mainMenu.IsVisibleInTree())
        {
            return false;
        }

        if (mainMenu.SubmenuStack?.SubmenusOpen == true)
        {
            return false;
        }

        var singleplayerButton = GetMainMenuSingleplayerButton(mainMenu);
        if (singleplayerButton != null && singleplayerButton.IsVisibleInTree() && singleplayerButton.IsEnabled)
        {
            return true;
        }

        // Some main-menu states still allow the singleplayer submenu to open even when the
        // button has not become visible in the scene tree. If there is no active run flow to
        // continue or abandon, prefer exposing character select instead of hard-blocking.
        return !CanContinueRun(currentScreen) && !CanAbandonRun(currentScreen);
    }

    public static bool CanOpenTimeline(IScreenContext? currentScreen)
    {
        if (currentScreen is not NMainMenu mainMenu || !mainMenu.IsVisibleInTree())
        {
            return false;
        }

        if (mainMenu.SubmenuStack?.SubmenusOpen == true)
        {
            return false;
        }

        var timelineButton = GetMainMenuTimelineButton(mainMenu);
        return timelineButton != null && timelineButton.IsVisibleInTree() && timelineButton.IsEnabled;
    }

    public static bool CanCloseMainMenuSubmenu(IScreenContext? currentScreen)
    {
        if (currentScreen is not NSubmenu submenu || !submenu.IsVisibleInTree())
        {
            return false;
        }

        var submenuStack = GetMainMenuSubmenuStack(submenu);
        return submenuStack != null && submenuStack.SubmenusOpen;
    }

    public static bool CanEmbark(IScreenContext? currentScreen)
    {
        var embarkButton = GetCharacterEmbarkButton(currentScreen);
        return embarkButton != null && embarkButton.IsEnabled && embarkButton.IsVisibleInTree();
    }

    public static bool CanUnready(IScreenContext? currentScreen)
    {
        var multiplayerTestScene = GetMultiplayerTestScene();
        var multiplayerLobby = multiplayerTestScene != null ? GetMultiplayerTestLobby(multiplayerTestScene) : null;
        if (multiplayerLobby != null)
        {
            return multiplayerLobby.LocalPlayer.isReady;
        }

        var unreadyButton = GetCharacterUnreadyButton(currentScreen);
        return unreadyButton != null && unreadyButton.IsEnabled && unreadyButton.IsVisibleInTree();
    }

    public static bool CanHostMultiplayerLobby(IScreenContext? currentScreen)
    {
        var scene = GetMultiplayerTestScene();
        return scene != null && GetMultiplayerTestLobby(scene) == null;
    }

    public static bool CanJoinMultiplayerLobby(IScreenContext? currentScreen)
    {
        var scene = GetMultiplayerTestScene();
        return scene != null && GetMultiplayerTestLobby(scene) == null;
    }

    public static bool CanReadyMultiplayerLobby(IScreenContext? currentScreen)
    {
        var scene = GetMultiplayerTestScene();
        var lobby = scene != null ? GetMultiplayerTestLobby(scene) : null;
        return lobby != null && !lobby.LocalPlayer.isReady;
    }

    public static bool CanDisconnectMultiplayerLobby(IScreenContext? currentScreen)
    {
        var scene = GetMultiplayerTestScene();
        return scene != null && GetMultiplayerTestLobby(scene) != null;
    }

    public static bool CanIncreaseAscension(IScreenContext? currentScreen)
    {
        return CanAdjustAscension(currentScreen, delta: 1);
    }

    public static bool CanDecreaseAscension(IScreenContext? currentScreen)
    {
        return CanAdjustAscension(currentScreen, delta: -1);
    }

    public static bool CanChooseTimelineEpoch(IScreenContext? currentScreen)
    {
        return GetTimelineSlots(currentScreen).Any(slot => slot.State is EpochSlotState.Obtained or EpochSlotState.Complete);
    }

    public static bool CanConfirmTimelineOverlay(IScreenContext? currentScreen)
    {
        var unlockConfirmButton = GetTimelineUnlockConfirmButton(currentScreen);
        if (unlockConfirmButton != null && unlockConfirmButton.IsVisibleInTree() && unlockConfirmButton.IsEnabled)
        {
            return true;
        }

        var inspectCloseButton = GetTimelineInspectCloseButton(currentScreen);
        return inspectCloseButton != null && inspectCloseButton.IsVisibleInTree() && inspectCloseButton.IsEnabled;
    }

    public static bool CanUsePotion(IScreenContext? currentScreen, CombatState? combatState, RunState? runState)
    {
        var player = GetLocalPlayer(runState);
        if (player == null)
        {
            return false;
        }

        return player.PotionSlots.Any(potion => IsPotionUsable(currentScreen, combatState, player, potion));
    }

    public static bool CanUsePotionAtIndex(IScreenContext? currentScreen, CombatState? combatState, RunState? runState, int optionIndex)
    {
        var player = GetLocalPlayer(runState);
        if (player == null || optionIndex < 0 || optionIndex >= player.PotionSlots.Count)
        {
            return false;
        }

        return IsPotionUsable(currentScreen, combatState, player, player.PotionSlots[optionIndex]);
    }

    public static bool CanDiscardPotion(IScreenContext? currentScreen, RunState? runState)
    {
        var player = GetLocalPlayer(runState);
        if (player == null || !CanDiscardPotionsInCurrentScreen(currentScreen))
        {
            return false;
        }

        return player.PotionSlots.Any(potion => IsPotionDiscardable(player, potion));
    }

    public static bool CanDiscardPotionAtIndex(IScreenContext? currentScreen, RunState? runState, int optionIndex)
    {
        var player = GetLocalPlayer(runState);
        if (player == null || !CanDiscardPotionsInCurrentScreen(currentScreen) || optionIndex < 0 || optionIndex >= player.PotionSlots.Count)
        {
            return false;
        }

        return IsPotionDiscardable(player, player.PotionSlots[optionIndex]);
    }

    public static bool CanConfirmModal(IScreenContext? currentScreen)
    {
        return GetModalConfirmButton(currentScreen) != null;
    }

    public static bool CanDismissModal(IScreenContext? currentScreen)
    {
        return GetModalCancelButton(currentScreen) != null;
    }

    public static bool CanReturnToMainMenu(IScreenContext? currentScreen)
    {
        return currentScreen is NGameOverScreen;
    }

    public static bool CanSaveAndQuit(IScreenContext? currentScreen, RunState? runState)
    {
        if (runState == null || runState.IsGameOver || RunManager.Instance.NetService.Type == NetGameType.Client)
        {
            return false;
        }

        var saveAndQuitButton = GetPauseMenuSaveAndQuitButton(currentScreen);
        if (saveAndQuitButton != null)
        {
            return true;
        }

        var pauseButton = GetTopBarPauseButton();
        return pauseButton != null && pauseButton.IsVisibleInTree() && pauseButton.IsEnabled;
    }

    public static IReadOnlyList<NMapPoint> GetAvailableMapNodes(IScreenContext? currentScreen, RunState? runState)
    {
        if (!TryGetMapScreen(currentScreen, runState, out var mapScreen))
        {
            return Array.Empty<NMapPoint>();
        }

        return FindDescendants<NMapPoint>(mapScreen!)
            .Where(node => GodotObject.IsInstanceValid(node) && node.IsEnabled)
            .OrderBy(node => node.Point.coord.row)
            .ThenBy(node => node.Point.coord.col)
            .ToArray();
    }

    public static IReadOnlyList<NRewardButton> GetRewardButtons(IScreenContext? currentScreen)
    {
        if (currentScreen is not NRewardsScreen rewardScreen)
        {
            return Array.Empty<NRewardButton>();
        }

        return FindDescendants<NRewardButton>(rewardScreen)
            .Where(node => GodotObject.IsInstanceValid(node))
            .OrderBy(node => node.GlobalPosition.Y)
            .ThenBy(node => node.GlobalPosition.X)
            .ToArray();
    }

    public static NProceedButton? GetRewardProceedButton(IScreenContext? currentScreen)
    {
        if (currentScreen is not NRewardsScreen rewardScreen)
        {
            return null;
        }

        return FindDescendants<NProceedButton>(rewardScreen)
            .FirstOrDefault(node => GodotObject.IsInstanceValid(node));
    }

    public static IReadOnlyList<NCardHolder> GetCardRewardOptions(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCardRewardSelectionScreen cardRewardScreen)
        {
            return Array.Empty<NCardHolder>();
        }

        return FindDescendants<NCardHolder>(cardRewardScreen)
            .Where(node => GodotObject.IsInstanceValid(node) && node.CardModel != null)
            .OrderBy(node => node.GlobalPosition.Y)
            .ThenBy(node => node.GlobalPosition.X)
            .ToArray();
    }

    public static IReadOnlyList<NCardRewardAlternativeButton> GetCardRewardAlternativeButtons(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCardRewardSelectionScreen cardRewardScreen)
        {
            return Array.Empty<NCardRewardAlternativeButton>();
        }

        return FindDescendants<NCardRewardAlternativeButton>(cardRewardScreen)
            .Where(node => GodotObject.IsInstanceValid(node) && node.IsVisibleInTree())
            .OrderBy(node => node.GlobalPosition.Y)
            .ThenBy(node => node.GlobalPosition.X)
            .ToArray();
    }

    public static IReadOnlyList<NCardHolder> GetDeckSelectionOptions(IScreenContext? currentScreen)
    {
        if (currentScreen is NCardsViewScreen)
        {
            return Array.Empty<NCardHolder>();
        }

        if (currentScreen is NCardGridSelectionScreen cardSelectScreen)
        {
            return GetVisibleGridCardHolders(cardSelectScreen)
                .Cast<NCardHolder>()
                .ToArray();
        }

        if (currentScreen is NChooseACardSelectionScreen chooseCardScreen)
        {
            return GetChooseCardSelectionOptions(chooseCardScreen);
        }

        if (TryGetCombatHandSelection(currentScreen, out var hand))
        {
            return hand!.ActiveHolders
                .Where(node => GodotObject.IsInstanceValid(node) && node.Visible && node.CardModel != null)
                .OrderBy(node => node.GetIndex())
                .Cast<NCardHolder>()
                .ToArray();
        }

        if (currentScreen is Node rootNode)
        {
            return GetVisibleGridCardHolders(rootNode)
                .Cast<NCardHolder>()
                .ToArray();
        }

        return Array.Empty<NCardHolder>();
    }

    /// <summary>
    /// Returns the clickable NCardBundle options for a NChooseABundleSelectionScreen.
    /// Each bundle represents one pack the player can choose.
    /// </summary>
    public static IReadOnlyList<NCardBundle> GetBundleSelectionOptions(IScreenContext? currentScreen)
    {
        if (currentScreen is not NChooseABundleSelectionScreen bundleScreen)
        {
            return Array.Empty<NCardBundle>();
        }

        return FindDescendants<NCardBundle>(bundleScreen)
            .OrderBy(bundle => bundle.GlobalPosition.X)
            .ToArray();
    }

    private static IReadOnlyList<NCardHolder> GetChooseCardSelectionOptions(NChooseACardSelectionScreen chooseCardScreen)
    {
        var holders = GetVisibleGridCardHolders(chooseCardScreen)
            .Cast<NCardHolder>()
            .ToArray();
        if (holders.Length <= 1)
        {
            return holders;
        }

        var topRowY = holders.Min(holder => holder.GlobalPosition.Y);
        const float rowTolerance = 100f;
        var topRow = holders
            .Where(holder => Mathf.Abs(holder.GlobalPosition.Y - topRowY) <= rowTolerance)
            .OrderBy(holder => holder.GlobalPosition.X)
            .ToArray();

        return topRow.Length > 0 && topRow.Length < holders.Length
            ? topRow
            : holders;
    }

    private static SelectionCardPayload[] GetChooseCardPreviewCards(NChooseACardSelectionScreen chooseCardScreen)
    {
        var allHolders = GetVisibleGridCardHolders(chooseCardScreen).ToArray();
        if (allHolders.Length == 0)
        {
            return Array.Empty<SelectionCardPayload>();
        }

        var optionSet = GetChooseCardSelectionOptions(chooseCardScreen)
            .OfType<NGridCardHolder>()
            .ToHashSet();

        return allHolders
            .Where(holder => !optionSet.Contains(holder) && holder.CardModel != null)
            .Select((holder, index) => BuildSelectionCardPayload(holder.CardModel!, index))
            .ToArray();
    }

    /// <summary>
    /// Returns preview cards for an event-embedded card selection (e.g. Neow "Scroll Boxes").
    /// The top row of NGridCardHolder nodes are the pack options (already in <paramref name="options"/>);
    /// the remaining holders below are the cards inside the currently-previewed pack.
    /// </summary>
    private static SelectionCardPayload[] GetEventEmbeddedPreviewCards(
        IScreenContext? currentScreen, IReadOnlyList<NCardHolder> options)
    {
        if (currentScreen is not Node rootNode)
        {
            return Array.Empty<SelectionCardPayload>();
        }

        var allHolders = GetVisibleGridCardHolders(rootNode).ToArray();
        if (allHolders.Length <= 1)
        {
            return Array.Empty<SelectionCardPayload>();
        }

        // The top row of holders are the pack options; holders below are preview cards
        // for the currently-hovered pack. Use the same Y-coordinate threshold logic as
        // GetChooseCardSelectionOptions to separate the two rows.
        var minY = allHolders.Min(holder => holder.GlobalPosition.Y);
        const float rowTolerance = 100f;

        return allHolders
            .Where(holder => holder.GlobalPosition.Y > minY + rowTolerance && holder.CardModel != null)
            .Select((holder, index) => BuildSelectionCardPayload(holder.CardModel!, index))
            .ToArray();
    }

    public static string? GetDeckSelectionPrompt(IScreenContext? currentScreen)
    {
        if (currentScreen is NCardsViewScreen)
        {
            return null;
        }

        if (currentScreen is NCardGridSelectionScreen cardSelectScreen)
        {
            // Resolve the source LocString via reflection on the screen's
            // private _prefs / CardSelectorPrefs.Prompt so we get English
            // regardless of the player's active in-game locale. Fall back to
            // the rendered Godot label only if reflection misses.
            var fromPrefs = TryGetPromptFromCardSelectorPrefs(cardSelectScreen);
            if (!string.IsNullOrEmpty(fromPrefs))
                return fromPrefs;
            return cardSelectScreen.GetNodeOrNull<MegaRichTextLabel>("%BottomLabel")?.Text;
        }

        if (currentScreen is NChooseACardSelectionScreen chooseCardScreen)
        {
            var fromPrefs = TryGetPromptFromCardSelectorPrefs(chooseCardScreen);
            if (!string.IsNullOrEmpty(fromPrefs))
                return fromPrefs;
            return SafeReadString(() => chooseCardScreen.GetNodeOrNull<NCommonBanner>("Banner")?.label.Text);
        }

        if (currentScreen is NChooseABundleSelectionScreen bundleSelectionScreen)
        {
            var fromPrefs = TryGetPromptFromCardSelectorPrefs(bundleSelectionScreen);
            if (!string.IsNullOrEmpty(fromPrefs))
                return fromPrefs;
            return SafeReadString(() => bundleSelectionScreen.GetNodeOrNull<NCommonBanner>("Banner")?.label.Text);
        }


        if (TryGetCombatHandSelection(currentScreen, out var hand))
        {
            // Resolve the source LocString via the hand's _prefs.Prompt so the
            // agent gets English regardless of the player's active locale.
            // Fall back to the rendered Godot label only if reflection misses.
            var prefs = TryGetCombatHandSelectionPrefs(hand!);
            if (prefs is { } p && p.Prompt != null)
            {
                var resolved = EnglishLocResolver.Resolve(p.Prompt);
                if (!string.IsNullOrEmpty(resolved))
                    return resolved;
            }
            return SafeReadString(() => hand!.GetNodeOrNull<MegaRichTextLabel>("%SelectionHeader")?.Text);
        }

        if (currentScreen is NEventRoom &&
            TryGetActiveEventModel(currentScreen, out var eventModel) &&
            eventModel != null)
        {
            return EnglishLocResolver.Resolve(eventModel.Description);
        }

        if (currentScreen is Node rootNode)
        {
            // Generic fallback: read the rendered Godot label. We can't resolve
            // through a LocString here since the source isn't reachable, but we
            // can still scrub embedded active-locale entity names (Block,
            // Strike, etc.) so the agent at least sees English keywords.
            var raw = SafeReadString(() =>
                rootNode.GetNodeOrNull<MegaRichTextLabel>("%BottomLabel")?.Text ??
                FindDescendants<MegaRichTextLabel>(rootNode)
                    .FirstOrDefault(label => label.IsVisibleInTree() && !string.IsNullOrWhiteSpace(label.Text))?.Text);
            return EnglishLocResolver.ScrubLocaleNames(raw);
        }

        return null;
    }

    public static bool TryGetCombatHandSelection(IScreenContext? currentScreen, out NPlayerHand? hand)
    {
        hand = null;

        if (currentScreen is not NCombatRoom combatRoom)
        {
            return false;
        }

        hand = combatRoom.Ui?.Hand;
        return hand != null &&
            GodotObject.IsInstanceValid(hand) &&
            hand.IsInCardSelection &&
            hand.CurrentMode is NPlayerHand.Mode.SimpleSelect or NPlayerHand.Mode.UpgradeSelect;
    }

    private static CardSelectorPrefs? TryGetCombatHandSelectionPrefs(NPlayerHand hand)
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
        var field = typeof(NPlayerHand).GetField("_prefs", flags);
        if (field?.GetValue(hand) is CardSelectorPrefs prefs)
        {
            return prefs;
        }

        return null;
    }

    /// <summary>
    /// Walks the screen's class hierarchy (private fields) for a CardSelectorPrefs
    /// instance and resolves its Prompt LocString through EnglishLocResolver so
    /// the agent gets the English prompt even when the player's UI is non-English.
    /// Returns null when no prefs/prompt is reachable.
    /// </summary>
    private static string? TryGetPromptFromCardSelectorPrefs(object screen)
    {
        if (screen == null) return null;
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
        var type = screen.GetType();
        while (type != null && type != typeof(object))
        {
            foreach (var field in type.GetFields(flags))
            {
                if (field.FieldType != typeof(CardSelectorPrefs)) continue;
                if (field.GetValue(screen) is CardSelectorPrefs prefs && prefs.Prompt != null)
                {
                    return EnglishLocResolver.Resolve(prefs.Prompt);
                }
            }
            type = type.BaseType;
        }
        return null;
    }

    public static bool TryGetCombatHandSelectionMetadata(
        IScreenContext? currentScreen,
        out NPlayerHand? hand,
        out CombatHandSelectionMetadata metadata)
    {
        metadata = default;
        if (!TryGetCombatHandSelection(currentScreen, out hand) || hand == null)
        {
            return false;
        }

        var prefs = TryGetCombatHandSelectionPrefs(hand);
        var requiresConfirmation = prefs?.RequireManualConfirmation ?? false;
        var canConfirm = requiresConfirmation &&
            TryGetCombatHandConfirmButton(hand, out var confirmButton) &&
            confirmButton!.Visible &&
            confirmButton.IsEnabled;

        metadata = new CombatHandSelectionMetadata(
            prefs?.MinSelect ?? 1,
            prefs?.MaxSelect ?? 1,
            GetCombatHandSelectedCount(hand),
            requiresConfirmation,
            canConfirm);
        return true;
    }

    private static int GetCombatHandSelectedCount(NPlayerHand hand)
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
        var field = typeof(NPlayerHand).GetField("_selectedCards", flags);
        return field?.GetValue(hand) is System.Collections.ICollection collection ? collection.Count : 0;
    }

    private static bool TryGetCombatHandConfirmButton(NPlayerHand hand, out NConfirmButton? confirmButton)
    {
        confirmButton = hand.GetNodeOrNull<NConfirmButton>("%SelectModeConfirmButton")
            ?? hand.GetNodeOrNull<NConfirmButton>("SelectModeConfirmButton");
        return confirmButton != null && GodotObject.IsInstanceValid(confirmButton);
    }

    private static IReadOnlyList<CardModel> GetCombatHandSelectedCards(NPlayerHand hand)
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
        var field = typeof(NPlayerHand).GetField("_selectedCards", flags);
        if (field?.GetValue(hand) is not IEnumerable selectedEntries)
        {
            return Array.Empty<CardModel>();
        }

        var selected = new List<CardModel>();
        foreach (var entry in selectedEntries)
        {
            switch (entry)
            {
                case NCardHolder holder when holder.CardModel != null:
                    selected.Add(holder.CardModel);
                    break;
                case CardModel card:
                    selected.Add(card);
                    break;
            }
        }

        return selected;
    }

    /// <summary>
    /// Extract selection metadata for non-combat deck selection screens
    /// (NDeckUpgradeSelectScreen, NDeckTransformSelectScreen, NDeckEnchantSelectScreen, etc.).
    /// Parses required count from prompt text and checks confirm button visibility.
    /// </summary>
    private static CombatHandSelectionMetadata GetDeckSelectionMetadata(IScreenContext? currentScreen, string? prompt)
    {
        // Parse required count from prompt: "Choose [blue]2[/blue] cards to Remove"
        var requiredCount = 1;
        var isAnyNumber = false;
        if (!string.IsNullOrEmpty(prompt))
        {
            // Strip BBCode tags like [blue], [/blue], [gold], [/gold]
            var cleanPrompt = Regex.Replace(prompt, @"\[/?[a-zA-Z_]+\]", "");

            // Detect "any number" prompts (e.g. Demon Glass: "Select any number of cards to add to your Deck.")
            if (Regex.IsMatch(cleanPrompt, @"any\s+number\s+of\s+card", RegexOptions.IgnoreCase))
            {
                isAnyNumber = true;
                requiredCount = 0;
            }
            else
            {
                var match = Regex.Match(cleanPrompt, @"[Cc]hoose\s+(\d+)\s+card");
                if (match.Success && int.TryParse(match.Groups[1].Value, out var parsed) && parsed > 0)
                {
                    requiredCount = parsed;
                }
            }
        }

        var canConfirm = TryGetSelectionConfirmButton(currentScreen, out _);
        var requiresConfirmation = requiredCount > 1 ||
            currentScreen is NChooseACardSelectionScreen ||
            canConfirm;

        var selectedCount = currentScreen switch
        {
            NChooseACardSelectionScreen => canConfirm ? 1 : 0,
            _ => GetGridSelectionSelectedCount(currentScreen)
        };

        // "any number" → min=0, max=total cards available
        var minSelect = isAnyNumber ? 0 : requiredCount;
        var maxSelect = isAnyNumber
            ? GetDeckSelectionOptions(currentScreen).Count
            : requiredCount;

        return new CombatHandSelectionMetadata(
            minSelect,          // MinSelect
            maxSelect,          // MaxSelect
            selectedCount,      // SelectedCount — counted from preview containers
            requiresConfirmation,
            canConfirm);
    }

    public static bool TryGetSelectionConfirmButton(IScreenContext? currentScreen, out NConfirmButton? confirmButton)
    {
        confirmButton = null;

        if (TryGetCombatHandSelection(currentScreen, out var hand) &&
            hand != null &&
            TryGetCombatHandConfirmButton(hand, out var handConfirm) &&
            IsClickableControlUsable(handConfirm))
        {
            confirmButton = handConfirm;
            return true;
        }

        if (currentScreen is not Node rootNode)
        {
            return false;
        }

        confirmButton = FindDescendants<NConfirmButton>(rootNode)
            .FirstOrDefault(IsClickableControlUsable);
        return confirmButton != null;
    }

    /// <summary>
    /// Count currently selected cards in deck grid selection screens by inspecting preview containers.
    /// When a card is selected in the grid, it appears in a preview container. We count those.
    /// </summary>
    private static int GetGridSelectionSelectedCount(IScreenContext? currentScreen)
    {
        if (currentScreen is not Node)
            return 0;

        try
        {
            return GetGridSelectionSelectedCardHolders(currentScreen).Count;
        }
        catch
        {
            return 0;
        }
    }

    /// <summary>
    /// Count visible card holders inside a named container node.
    /// </summary>
    private static int CountPreviewCardsInContainer(Node screen, string containerName)
    {
        var container = screen.GetNodeOrNull<Control>(containerName);
        if (container?.Visible != true) return 0;

        // Try NGridCardHolder first (grid-style card holders)
        var gridCards = FindDescendants<NGridCardHolder>(container)
            .Count(h => GodotObject.IsInstanceValid(h) && h.IsVisibleInTree() && h.CardModel != null);
        if (gridCards > 0) return gridCards;

        // Fall back to NCardHolder (broader base class)
        return FindDescendants<NCardHolder>(container)
            .Count(h => GodotObject.IsInstanceValid(h) && h.IsVisibleInTree() && h.CardModel != null);
    }

    private static IReadOnlyList<NCardHolder> GetPreviewCardHoldersInContainer(Node screen, string containerName)
    {
        var container = screen.GetNodeOrNull<Control>(containerName);
        if (container?.Visible != true)
        {
            return Array.Empty<NCardHolder>();
        }

        return FindDescendants<NCardHolder>(container)
            .Where(h => GodotObject.IsInstanceValid(h) && h.IsVisibleInTree() && h.CardModel != null)
            .OrderBy(h => h.GlobalPosition.Y)
            .ThenBy(h => h.GlobalPosition.X)
            .ToArray();
    }

    private static IReadOnlyList<NCardHolder> GetGridSelectionSelectedCardHolders(IScreenContext? currentScreen)
    {
        if (currentScreen is not Node gridScreen)
        {
            return Array.Empty<NCardHolder>();
        }

        var holders = new List<NCardHolder>();
        holders.AddRange(GetPreviewCardHoldersInContainer(gridScreen, "%PreviewContainer"));

        if (currentScreen is NDeckUpgradeSelectScreen)
        {
            holders.AddRange(GetPreviewCardHoldersInContainer(gridScreen, "%UpgradeSinglePreviewContainer"));
            holders.AddRange(GetPreviewCardHoldersInContainer(gridScreen, "%UpgradeMultiPreviewContainer"));
        }

        if (currentScreen is NDeckEnchantSelectScreen)
        {
            holders.AddRange(GetPreviewCardHoldersInContainer(gridScreen, "%EnchantSinglePreviewContainer"));
            holders.AddRange(GetPreviewCardHoldersInContainer(gridScreen, "%EnchantMultiPreviewContainer"));
        }

        var seen = new HashSet<ulong>();
        var deduped = new List<NCardHolder>();
        foreach (var holder in holders)
        {
            if (seen.Add(holder.GetInstanceId()))
            {
                deduped.Add(holder);
            }
        }

        return deduped;
    }

    /// <summary>
    /// Check if a confirm button is visible and enabled in one of the preview containers.
    /// </summary>
    private static bool TryGetDeckConfirmButton(Node screen, string primaryContainer, string? secondaryContainer)
    {
        var container = screen.GetNodeOrNull<Control>(primaryContainer);
        if (container?.Visible == true)
        {
            var btn = container.GetNodeOrNull<NConfirmButton>("Confirm");
            if (btn?.IsEnabled == true) return true;
        }

        if (secondaryContainer != null)
        {
            var container2 = screen.GetNodeOrNull<Control>(secondaryContainer);
            if (container2?.Visible == true)
            {
                var btn2 = container2.GetNodeOrNull<NConfirmButton>("Confirm");
                if (btn2?.IsEnabled == true) return true;
            }
        }

        return false;
    }

    private static CardsViewPayload? BuildCardsViewPayload(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCardsViewScreen cardsViewScreen)
        {
            return null;
        }

        var cards = GetVisibleGridCardHolders(cardsViewScreen)
            .Where(holder => holder.CardModel != null)
            .Select((holder, index) => BuildSelectionCardPayload(holder.CardModel!, index))
            .ToArray();
        if (cards.Length == 0)
        {
            return null;
        }

        return new CardsViewPayload
        {
            title = SafeReadString(() =>
                cardsViewScreen.GetNodeOrNull<NCommonBanner>("Banner")?.label.Text ??
                cardsViewScreen.GetNodeOrNull<MegaRichTextLabel>("%Header")?.Text,
                "Cards View"),
            cards = cards
        };
    }

    private static string SafeReadString(Func<string?> getter, string fallback = "")
    {
        try
        {
            var value = getter();
            return value == null ? fallback : value;
        }
        catch
        {
            return fallback;
        }
    }

    private static bool SafeReadBool(Func<bool> getter, bool fallback = false)
    {
        try
        {
            return getter();
        }
        catch
        {
            return fallback;
        }
    }

    private static string GetCardRulesText(CardModel? card)
    {
        if (card == null)
        {
            return string.Empty;
        }

        // Primary: rendered description with resolved values, resolved against
        // English LocManager tables so the agent gets English regardless of the
        // player's active locale. GetDescriptionForPile resolves {Damage:diff()},
        // {Block:diff()}, etc. Works best for hand cards in combat (full runtime
        // context). May return base values or throw for non-hand contexts —
        // fallback handles that.
        try
        {
            var rendered = EnglishLocResolver.WithEnglishTables(
                () => card.GetDescriptionForPile(PileType.Hand));
            rendered = EnglishLocResolver.ScrubLocaleNames(rendered);
            if (!string.IsNullOrWhiteSpace(rendered))
                return NormalizeCardRulesText(rendered);
        }
        catch { /* fall through to reflection paths */ }

        // Fallback: reflection-based text extraction (may return unresolved templates)
        foreach (var memberName in new[]
        {
            "Description",
            "RulesText",
            "Body",
            "Text",
            "RawText",
            "DescriptionText"
        })
        {
            var text = TryReadCardTextMember(card, memberName);
            if (!string.IsNullOrWhiteSpace(text))
            {
                return NormalizeCardRulesText(text);
            }
        }

        return string.Empty;
    }

    private static string GetResolvedCardRulesText(CardModel? card)
    {
        if (card == null)
        {
            return string.Empty;
        }

        try
        {
            card.UpdateDynamicVarPreview(CardPreviewMode.Normal, card.CurrentTarget, card.DynamicVars);
            var pileType = card.Pile?.Type ?? PileType.None;
            var resolved = EnglishLocResolver.WithEnglishTables(
                () => card.GetDescriptionForPile(pileType, card.CurrentTarget));
            resolved = EnglishLocResolver.ScrubLocaleNames(resolved);
            if (!string.IsNullOrWhiteSpace(resolved))
            {
                return NormalizeCardRulesText(resolved);
            }
        }
        catch
        {
        }

        return GetCardRulesText(card);
    }

    private static CardDynamicValuePayload[] BuildCardDynamicValuePayloads(CardModel? card)
    {
        if (card == null)
        {
            return Array.Empty<CardDynamicValuePayload>();
        }

        try
        {
            var previewSet = card.DynamicVars.Clone(card);
            card.UpdateDynamicVarPreview(CardPreviewMode.Normal, card.CurrentTarget, previewSet);

            return previewSet.Values
                .Select(dynamicVar => new CardDynamicValuePayload
                {
                    name = dynamicVar.Name,
                    base_value = (int)dynamicVar.BaseValue,
                    current_value = (int)dynamicVar.PreviewValue,
                    enchanted_value = (int)dynamicVar.EnchantedValue,
                    is_modified = (int)dynamicVar.PreviewValue != (int)dynamicVar.BaseValue
                        || (int)dynamicVar.EnchantedValue != (int)dynamicVar.BaseValue,
                    was_just_upgraded = dynamicVar.WasJustUpgraded
                })
                .OrderBy(payload => payload.name, StringComparer.Ordinal)
                .ToArray();
        }
        catch
        {
            return Array.Empty<CardDynamicValuePayload>();
        }
    }

    private static string GetPreferredCardRulesText(string rulesText, string? resolvedRulesText)
    {
        return string.IsNullOrWhiteSpace(resolvedRulesText) ? rulesText : resolvedRulesText;
    }

    private static AscensionEffectPayload[] BuildAscensionEffectPayloads(int ascensionLevel)
    {
        if (ascensionLevel <= 0)
        {
            return Array.Empty<AscensionEffectPayload>();
        }

        return Enumerable.Range(1, ascensionLevel)
            .Select(level => new AscensionEffectPayload
            {
                id = $"LEVEL_{level:D2}",
                name = EnglishLocResolver.Resolve(AscensionHelper.GetTitle(level)),
                description = EnglishLocResolver.Resolve(AscensionHelper.GetDescription(level))
            })
            .ToArray();
    }

    private static string TryReadCardTextMember(object instance, string memberName)
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        try
        {
            var property = instance.GetType().GetProperty(memberName, flags);
            if (property != null)
            {
                return TryCoerceText(property.GetValue(instance));
            }

            var field = instance.GetType().GetField(memberName, flags);
            if (field != null)
            {
                return TryCoerceText(field.GetValue(instance));
            }
        }
        catch
        {
        }

        return string.Empty;
    }

    private static string TryCoerceText(object? value)
    {
        if (value == null)
        {
            return string.Empty;
        }

        if (value is string text)
        {
            return text;
        }

        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var valueType = value.GetType();

        try
        {
            var getFormattedText = valueType.GetMethod("GetFormattedText", flags, null, Type.EmptyTypes, null);
            if (getFormattedText != null && getFormattedText.ReturnType == typeof(string))
            {
                // Resolve through the English LocManager tables (locale-blind),
                // then scrub embedded active-locale entity names.
                var rendered = EnglishLocResolver.WithEnglishTables(
                    () => getFormattedText.Invoke(value, null) as string);
                return EnglishLocResolver.ScrubLocaleNames(rendered);
            }
        }
        catch
        {
        }

        try
        {
            var textProperty = valueType.GetProperty("Text", flags);
            if (textProperty != null && textProperty.PropertyType == typeof(string))
            {
                return textProperty.GetValue(value) as string ?? string.Empty;
            }
        }
        catch
        {
        }

        return value.ToString() ?? string.Empty;
    }

    private static string NormalizeCardRulesText(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        var normalized = ReplaceInlineIconTags(value);
        normalized = ReplaceInlineResourceIcons(normalized);
        normalized = Regex.Replace(normalized, @"\[(?:/?[^\]]+)\]", string.Empty);
        normalized = Regex.Replace(normalized, @"res://[^\s]+", string.Empty);
        normalized = ReplaceIconTokensWithCounts(normalized);
        normalized = Regex.Replace(normalized, @"\s+", " ");
        // [energy:1]/[star:1]/[hp:1] render as unit-suffix icons after a cost digit, not as "1 energy".
        // e.g. "0 1 energy cards" → "0 energy cards" (0-cost cards)
        normalized = Regex.Replace(normalized, @"(\d)\s+1 energy\b", "$1 energy", RegexOptions.IgnoreCase);
        normalized = Regex.Replace(normalized, @"(\d)\s+1 star\b", "$1 star", RegexOptions.IgnoreCase);
        normalized = Regex.Replace(normalized, @"(\d)\s+1 HP\b", "$1 HP");
        return normalized.Trim();
    }

    private static string ReplaceInlineIconTags(string value)
    {
        var normalized = value;
        normalized = Regex.Replace(
            normalized,
            @"\[energy:(?<amount>[^\]]+)\]",
            match => FormatInlineResourceText(match.Groups["amount"].Value, "energy", "energy"));
        normalized = Regex.Replace(
            normalized,
            @"\[star:(?<amount>[^\]]+)\]",
            match => FormatInlineResourceText(match.Groups["amount"].Value, "star", "stars"));
        normalized = Regex.Replace(
            normalized,
            @"\[hp:(?<amount>[^\]]+)\]",
            match => FormatInlineResourceText(match.Groups["amount"].Value, "HP", "HP"));
        return normalized;
    }

    private static string ReplaceInlineResourceIcons(string value)
    {
        var normalized = value;
        normalized = Regex.Replace(
            normalized,
            @"res://[^\s\]]*energy_icon\.png",
            $" {EnergyIconToken} ",
            RegexOptions.IgnoreCase);
        normalized = Regex.Replace(
            normalized,
            @"res://[^\s\]]*star_icon\.png",
            $" {StarIconToken} ",
            RegexOptions.IgnoreCase);
        normalized = Regex.Replace(
            normalized,
            @"res://[^\s\]]*(?:hp|health)_icon\.png",
            $" {HpIconToken} ",
            RegexOptions.IgnoreCase);
        return normalized;
    }

    private static string ReplaceIconTokensWithCounts(string value)
    {
        var normalized = value;
        normalized = ReplaceIconTokenRuns(normalized, EnergyIconToken, "energy", "energy");
        normalized = ReplaceIconTokenRuns(normalized, StarIconToken, "star", "stars");
        normalized = ReplaceIconTokenRuns(normalized, HpIconToken, "HP", "HP");
        return normalized;
    }

    private static string ReplaceIconTokenRuns(string value, string token, string singular, string plural)
    {
        var pattern = $@"(?:{Regex.Escape(token)}\s*)+";
        return Regex.Replace(value, pattern, match =>
        {
            var count = Regex.Matches(match.Value, Regex.Escape(token)).Count;
            var label = count == 1 ? singular : plural;
            return $" {count} {label} ";
        });
    }

    private static string FormatInlineResourceText(string rawAmount, string singular, string plural)
    {
        var token = rawAmount.Trim();
        if (string.IsNullOrEmpty(token))
        {
            return singular;
        }

        if (token.Equals("X", StringComparison.OrdinalIgnoreCase))
        {
            return $"1 {singular}";
        }

        if (int.TryParse(token, out var amount))
        {
            var label = amount == 1 ? singular : plural;
            return $"{amount} {label}";
        }

        return singular;
    }

    public static NProceedButton? GetProceedButton(IScreenContext? currentScreen)
    {
        if (currentScreen is null || currentScreen is NCardRewardSelectionScreen)
        {
            return null;
        }

        if (currentScreen is NRewardsScreen rewardsScreen)
        {
            var rewardProceedButton = GetRewardProceedButton(rewardsScreen);
            return IsProceedButtonUsable(rewardProceedButton)
                ? rewardProceedButton
                : null;
        }

        if (currentScreen is IRoomWithProceedButton roomWithProceedButton)
        {
            return IsProceedButtonUsable(roomWithProceedButton.ProceedButton)
                ? roomWithProceedButton.ProceedButton
                : null;
        }

        if (currentScreen is not Node rootNode)
        {
            return null;
        }

        return FindDescendants<NProceedButton>(rootNode)
            .FirstOrDefault(IsProceedButtonUsable);
    }

    private static CrystalSpherePayload? BuildCrystalSpherePayload(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCrystalSphereScreen crystalSphereScreen ||
            !GodotObject.IsInstanceValid(crystalSphereScreen))
        {
            return null;
        }

        try
        {
            var minigame = GetCrystalSphereMinigame(currentScreen);
            if (minigame == null)
            {
                return null;
            }

            var allCells = FindDescendants<NCrystalSphereCell>(crystalSphereScreen)
                .Where(c => c.Entity != null)
                .OrderBy(c => c.Entity!.Y)
                .ThenBy(c => c.Entity!.X)
                .ToList();

            int gridWidth = allCells.Count > 0 ? allCells.Max(c => c.Entity!.X) + 1 : 0;
            int gridHeight = allCells.Count > 0 ? allCells.Max(c => c.Entity!.Y) + 1 : 0;

            var cells = new List<CrystalSphereCellPayload>(allCells.Count);
            var clickable = new List<CrystalSphereCellRefPayload>();
            var revealed = new List<CrystalSphereRevealedItemPayload>();

            foreach (var cell in allCells)
            {
                var entity = cell.Entity!;
                bool clickableCell = entity.IsHidden && IsClickableControlUsable(cell);
                string? itemType = null;
                bool? isGood = null;

                if (!entity.IsHidden)
                {
                    var itemRef = GetReflectedProperty(entity, "Item");
                    if (itemRef != null)
                    {
                        itemType = itemRef.GetType().Name;
                        try
                        {
                            var goodObj = GetReflectedProperty(itemRef, "IsGood");
                            if (goodObj is bool g)
                            {
                                isGood = g;
                            }
                        }
                        catch { /* ignore */ }
                    }
                }

                cells.Add(new CrystalSphereCellPayload
                {
                    x = entity.X,
                    y = entity.Y,
                    is_hidden = entity.IsHidden,
                    is_clickable = clickableCell,
                    item_type = itemType,
                    is_good = isGood
                });

                if (clickableCell)
                {
                    clickable.Add(new CrystalSphereCellRefPayload
                    {
                        x = entity.X,
                        y = entity.Y
                    });
                }

                if (!entity.IsHidden && itemType != null)
                {
                    revealed.Add(new CrystalSphereRevealedItemPayload
                    {
                        x = entity.X,
                        y = entity.Y,
                        item_type = itemType,
                        is_good = isGood ?? false
                    });
                }
            }

            var bigButton = TryGetMemberValue(crystalSphereScreen, "_bigDivinationButton") as NDivinationButton;
            var smallButton = TryGetMemberValue(crystalSphereScreen, "_smallDivinationButton") as NDivinationButton;
            var activeTool = minigame.CrystalSphereTool;

            string toolLabel = activeTool switch
            {
                CrystalSphereMinigame.CrystalSphereToolType.Big => "big",
                CrystalSphereMinigame.CrystalSphereToolType.Small => "small",
                _ => "none"
            };

            string? instructionsTitle = NormalizeCardRulesText(SafeReadString(() =>
                (TryGetMemberValue(crystalSphereScreen, "_instructionsTitleLabel") as MegaRichTextLabel)?.Text));
            string? instructionsDescription = NormalizeCardRulesText(SafeReadString(() =>
                (TryGetMemberValue(crystalSphereScreen, "_instructionsDescriptionLabel") as MegaRichTextLabel)?.Text));
            string? divinationsLabel = NormalizeCardRulesText(SafeReadString(() =>
                (TryGetMemberValue(crystalSphereScreen, "_divinationsLeftLabel") as MegaRichTextLabel)?.Text));

            var proceedButton = GetProceedButton(currentScreen);

            return new CrystalSpherePayload
            {
                grid_width = gridWidth,
                grid_height = gridHeight,
                tool = toolLabel,
                can_use_big_tool = activeTool != CrystalSphereMinigame.CrystalSphereToolType.Big &&
                    IsClickableControlUsable(bigButton),
                can_use_small_tool = activeTool != CrystalSphereMinigame.CrystalSphereToolType.Small &&
                    IsClickableControlUsable(smallButton),
                divinations_left = Math.Max(0, minigame.DivinationCount),
                divinations_left_text = string.IsNullOrWhiteSpace(divinationsLabel) ? null : divinationsLabel,
                instructions_title = string.IsNullOrWhiteSpace(instructionsTitle) ? null : instructionsTitle,
                instructions_description = string.IsNullOrWhiteSpace(instructionsDescription) ? null : instructionsDescription,
                can_proceed = IsProceedButtonUsable(proceedButton),
                is_finished = minigame.IsFinished,
                cells = cells.ToArray(),
                clickable_cells = clickable.ToArray(),
                revealed_items = revealed.ToArray()
            };
        }
        catch (Exception ex)
        {
            var screenType = currentScreen?.GetType().FullName ?? "<null>";
            Log.Warn($"[STS2AIAgent] Failed to build Crystal Sphere payload on screen {screenType}: {ex}");
            return null;
        }
    }

    public static bool CanCrystalSphereSetTool(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCrystalSphereScreen crystalSphereScreen ||
            !GodotObject.IsInstanceValid(crystalSphereScreen))
        {
            return false;
        }

        var minigame = GetCrystalSphereMinigame(currentScreen);
        if (minigame == null)
        {
            return false;
        }

        var bigButton = TryGetMemberValue(crystalSphereScreen, "_bigDivinationButton") as NDivinationButton;
        var smallButton = TryGetMemberValue(crystalSphereScreen, "_smallDivinationButton") as NDivinationButton;
        var activeTool = minigame.CrystalSphereTool;

        bool bigUsable = activeTool != CrystalSphereMinigame.CrystalSphereToolType.Big &&
            IsClickableControlUsable(bigButton);
        bool smallUsable = activeTool != CrystalSphereMinigame.CrystalSphereToolType.Small &&
            IsClickableControlUsable(smallButton);

        return bigUsable || smallUsable;
    }

    public static bool CanCrystalSphereClickCell(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCrystalSphereScreen crystalSphereScreen ||
            !GodotObject.IsInstanceValid(crystalSphereScreen))
        {
            return false;
        }

        var minigame = GetCrystalSphereMinigame(currentScreen);
        if (minigame == null ||
            minigame.CrystalSphereTool == CrystalSphereMinigame.CrystalSphereToolType.None)
        {
            return false;
        }

        return FindDescendants<NCrystalSphereCell>(crystalSphereScreen)
            .Any(cell => cell.Entity != null && cell.Entity.IsHidden && IsClickableControlUsable(cell));
    }

    public static bool CanCrystalSphereProceed(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCrystalSphereScreen)
        {
            return false;
        }

        return IsProceedButtonUsable(GetProceedButton(currentScreen));
    }

    public static NDivinationButton? GetCrystalSphereToolButton(IScreenContext? currentScreen, string tool)
    {
        if (currentScreen is not NCrystalSphereScreen crystalSphereScreen)
        {
            return null;
        }

        return tool switch
        {
            "big" => TryGetMemberValue(crystalSphereScreen, "_bigDivinationButton") as NDivinationButton,
            "small" => TryGetMemberValue(crystalSphereScreen, "_smallDivinationButton") as NDivinationButton,
            _ => null
        };
    }

    public static NCrystalSphereCell? GetCrystalSphereCellAt(IScreenContext? currentScreen, int x, int y)
    {
        if (currentScreen is not NCrystalSphereScreen crystalSphereScreen)
        {
            return null;
        }

        return FindDescendants<NCrystalSphereCell>(crystalSphereScreen)
            .FirstOrDefault(c => c.Entity != null && c.Entity.X == x && c.Entity.Y == y);
    }

    internal static IReadOnlyList<CrystalSphereActionOption> GetCrystalSphereOptions(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCrystalSphereScreen crystalSphereScreen ||
            !GodotObject.IsInstanceValid(crystalSphereScreen))
        {
            return Array.Empty<CrystalSphereActionOption>();
        }

        var minigame = GetCrystalSphereMinigame(currentScreen);
        if (minigame == null)
        {
            return Array.Empty<CrystalSphereActionOption>();
        }

        var options = new List<CrystalSphereActionOption>();
        var activeTool = minigame.CrystalSphereTool;
        var divinationsLeft = Math.Max(0, minigame.DivinationCount);

        var smallButton = TryGetMemberValue(crystalSphereScreen, "_smallDivinationButton") as NDivinationButton;
        if (activeTool != CrystalSphereMinigame.CrystalSphereToolType.Small &&
            IsClickableControlUsable(smallButton))
        {
            options.Add(new CrystalSphereActionOption
            {
                text_key = "TOOL_SMALL",
                title = "Select small divination",
                description = $"Divinations left: {divinationsLeft}.",
                action_type = CrystalSphereActionType.SelectSmallTool,
                control = smallButton!
            });
        }

        var bigButton = TryGetMemberValue(crystalSphereScreen, "_bigDivinationButton") as NDivinationButton;
        if (activeTool != CrystalSphereMinigame.CrystalSphereToolType.Big &&
            IsClickableControlUsable(bigButton))
        {
            options.Add(new CrystalSphereActionOption
            {
                text_key = "TOOL_BIG",
                title = "Select big divination",
                description = $"Divinations left: {divinationsLeft}.",
                action_type = CrystalSphereActionType.SelectBigTool,
                control = bigButton!
            });
        }

        if (activeTool != CrystalSphereMinigame.CrystalSphereToolType.None)
        {
            foreach (var cell in FindDescendants<NCrystalSphereCell>(crystalSphereScreen)
                         .Where(IsClickableControlUsable)
                         .Where(cell => cell.Entity != null && cell.Entity.IsHidden)
                         .OrderBy(cell => cell.Entity!.Y)
                         .ThenBy(cell => cell.Entity!.X))
            {
                options.Add(new CrystalSphereActionOption
                {
                    text_key = $"CELL_{cell.Entity!.X}_{cell.Entity.Y}",
                    title = $"Reveal cell ({cell.Entity.X},{cell.Entity.Y})",
                    description = $"Use {DescribeCrystalSphereTool(activeTool)} divination.",
                    action_type = CrystalSphereActionType.ClickCell,
                    control = cell,
                    cell_x = cell.Entity.X,
                    cell_y = cell.Entity.Y
                });
            }
        }

        var proceedButton = GetProceedButton(currentScreen);
        if (IsProceedButtonUsable(proceedButton))
        {
            options.Add(new CrystalSphereActionOption
            {
                text_key = "PROCEED",
                title = "Proceed",
                description = "Leave the Crystal Sphere minigame.",
                is_proceed = true,
                action_type = CrystalSphereActionType.Proceed,
                control = proceedButton!
            });
        }

        for (int i = 0; i < options.Count; i++)
        {
            options[i].index = i;
        }

        return options;
    }

    internal static CrystalSphereMinigame? GetCrystalSphereMinigame(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCrystalSphereScreen crystalSphereScreen ||
            !GodotObject.IsInstanceValid(crystalSphereScreen))
        {
            return null;
        }

        return TryGetMemberValue(crystalSphereScreen, "_entity") as CrystalSphereMinigame;
    }

    internal static string GetCrystalSphereOptionSignature(IScreenContext? currentScreen)
    {
        var minigame = GetCrystalSphereMinigame(currentScreen);
        var options = GetCrystalSphereOptions(currentScreen);
        var proceedAvailable = GetProceedButton(currentScreen) != null;

        return string.Join(
            "|",
            new[]
            {
                $"divinations:{minigame?.DivinationCount ?? -1}",
                $"tool:{minigame?.CrystalSphereTool.ToString() ?? "None"}",
                $"finished:{minigame?.IsFinished ?? false}",
                $"proceed:{proceedAvailable}",
                string.Join(";", options.Select(option =>
                    $"{option.action_type}:{option.cell_x}:{option.cell_y}:{option.text_key}"))
            });
    }

    public static NButton? GetCardsViewBackButton(IScreenContext? currentScreen)
    {
        if (currentScreen is not NCardsViewScreen cardsViewScreen)
        {
            return null;
        }

        var backButton = cardsViewScreen.GetNodeOrNull<NButton>("BackButton");
        return backButton != null &&
            GodotObject.IsInstanceValid(backButton) &&
            backButton.IsVisibleInTree() &&
            backButton.IsEnabled
            ? backButton
            : null;
    }

    public static Creature? ResolveEnemyTarget(CombatState combatState, int targetIndex)
    {
        var enemies = combatState.Enemies.ToList();
        if (targetIndex < 0 || targetIndex >= enemies.Count)
        {
            return null;
        }

        var enemy = enemies[targetIndex];
        return enemy.IsAlive && enemy.IsHittable ? enemy : null;
    }

    public static Creature? ResolvePlayerTarget(CombatState combatState, int targetIndex)
    {
        var players = GetOrderedCombatPlayers(combatState);
        if (targetIndex < 0 || targetIndex >= players.Count)
        {
            return null;
        }

        var player = players[targetIndex];
        return player.Creature.IsAlive ? player.Creature : null;
    }

    public static bool CardRequiresTarget(CardModel card)
    {
        return RequiresIndexedCardTarget(card.TargetType);
    }

    public static bool IsCardPlayable(CardModel card)
    {
        return card.CanPlay(out _, out _) && IsCardTargetSupported(card);
    }

    public static bool IsCardTargetSupported(CardModel card)
    {
        return card.TargetType switch
        {
            TargetType.None => true,
            TargetType.Self => true,
            TargetType.AnyEnemy => true,
            TargetType.AllEnemies => true,
            TargetType.RandomEnemy => true,
            TargetType.AnyAlly => true,
            TargetType.AllAllies => true,
            _ => false
        };
    }

    public static string? GetUnplayableReasonCode(CardModel card)
    {
        card.CanPlay(out var reason, out _);
        return GetUnplayableReasonCode(reason);
    }

    public static string? GetUnplayableReasonCode(UnplayableReason reason)
    {
        if (reason == UnplayableReason.None)
        {
            return null;
        }

        if (reason.HasFlag(UnplayableReason.EnergyCostTooHigh))
        {
            return "not_enough_energy";
        }

        if (reason.HasFlag(UnplayableReason.StarCostTooHigh))
        {
            return "not_enough_stars";
        }

        if (reason.HasFlag(UnplayableReason.NoLivingAllies))
        {
            return "no_living_allies";
        }

        if (reason.HasFlag(UnplayableReason.BlockedByHook))
        {
            return "blocked_by_hook";
        }

        if (reason.HasFlag(UnplayableReason.HasUnplayableKeyword) || reason.HasFlag(UnplayableReason.BlockedByCardLogic))
        {
            return "unplayable";
        }

        return reason.ToString();
    }

    private static bool CanUseCombatActions(IScreenContext? currentScreen, CombatState? combatState, out Player? me, out NCombatRoom? combatRoom)
    {
        me = null;
        combatRoom = null;

        if (combatState == null || currentScreen is not NCombatRoom room)
        {
            return false;
        }

        combatRoom = room;

        if (!CombatManager.Instance.IsInProgress ||
            CombatManager.Instance.IsOverOrEnding ||
            !IsLocalPlayerInPlayPhase() ||
            CombatManager.Instance.PlayerActionsDisabled)
        {
            return false;
        }

        if (combatRoom.Mode != CombatRoomMode.ActiveCombat)
        {
            return false;
        }

        var hand = combatRoom.Ui?.Hand;
        if (hand == null || hand.InCardPlay || hand.IsInCardSelection || hand.CurrentMode != MegaCrit.Sts2.Core.Nodes.Combat.NPlayerHand.Mode.Play)
        {
            return false;
        }

        me = LocalContext.GetMe(combatState);
        if (me == null || !me.Creature.IsAlive)
        {
            return false;
        }

        return true;
    }

    private static string[] BuildAvailableActionNames(IScreenContext? currentScreen, CombatState? combatState, RunState? runState)
    {
        var names = new List<string>();

        if (GetOpenModal() != null)
        {
            if (CanConfirmModal(currentScreen))
            {
                names.Add("confirm_modal");
            }

            if (CanDismissModal(currentScreen))
            {
                names.Add("dismiss_modal");
            }

            return names.ToArray();
        }

        if (CanEndTurn(currentScreen, combatState))
        {
            names.Add("end_turn");
        }

        if (CanPlayAnyCard(currentScreen, combatState))
        {
            names.Add("play_card");
        }

        if (CanContinueRun(currentScreen))
        {
            names.Add("continue_run");
        }

        if (CanAbandonRun(currentScreen))
        {
            names.Add("abandon_run");
        }

        if (CanOpenCharacterSelect(currentScreen))
        {
            names.Add("open_character_select");
        }

        if (CanOpenTimeline(currentScreen))
        {
            names.Add("open_timeline");
        }

        if (CanCloseMainMenuSubmenu(currentScreen))
        {
            names.Add("close_main_menu_submenu");
        }

        if (CanChooseTimelineEpoch(currentScreen))
        {
            names.Add("choose_timeline_epoch");
        }

        if (CanConfirmTimelineOverlay(currentScreen))
        {
            names.Add("confirm_timeline_overlay");
        }

        if (CanChooseMapNode(currentScreen, runState))
        {
            names.Add("choose_map_node");
        }

        if (CanCollectRewardsAndProceed(currentScreen))
        {
            names.Add("collect_rewards_and_proceed");
        }

        if (CanResolveRewards(currentScreen))
        {
            names.Add("resolve_rewards");
        }

        if (CanClaimReward(currentScreen))
        {
            names.Add("claim_reward");
        }

        if (CanChooseRewardCard(currentScreen))
        {
            names.Add("choose_reward_card");
        }

        if (CanChooseRewardAlternative(currentScreen))
        {
            names.Add("choose_reward_alternative");
        }

        if (CanSkipRewardCards(currentScreen))
        {
            names.Add("skip_reward_cards");
        }

        if (CanSacrificeRewardCards(currentScreen))
        {
            names.Add("sacrifice_reward_cards");
        }

        if (CanSelectDeckCard(currentScreen))
        {
            names.Add("select_deck_card");
        }

        if (CanCloseCardsView(currentScreen))
        {
            names.Add("close_cards_view");
        }

        if (CanCloseCapstoneOverlay(currentScreen))
        {
            names.Add("close_capstone_overlay");
        }

        if (CanClosePauseMenu(currentScreen))
        {
            names.Add("close_pause_menu");
        }

        if (CanCancelSelection(currentScreen))
        {
            names.Add("cancel_selection");
        }

        if (CanConfirmSelection(currentScreen))
        {
            names.Add("confirm_selection");
        }

        if (CanProceed(currentScreen))
        {
            names.Add("proceed");
        }

        if (CanOpenChest(currentScreen))
        {
            names.Add("open_chest");
        }

        if (CanChooseTreasureRelic(currentScreen))
        {
            names.Add("choose_treasure_relic");
        }

        if (CanChooseEventOption(currentScreen))
        {
            names.Add("choose_event_option");
        }

        if (currentScreen is NCrystalSphereScreen)
        {
            if (CanCrystalSphereSetTool(currentScreen))
            {
                names.Add("crystal_sphere_set_tool");
            }

            if (CanCrystalSphereClickCell(currentScreen))
            {
                names.Add("crystal_sphere_click_cell");
            }

            if (CanCrystalSphereProceed(currentScreen))
            {
                names.Add("crystal_sphere_proceed");
            }
        }

        if (CanChooseRestOption(currentScreen))
        {
            names.Add("choose_rest_option");
        }

        if (CanOpenShopInventory(currentScreen))
        {
            names.Add("open_shop_inventory");
        }

        if (CanCloseShopInventory(currentScreen))
        {
            names.Add("close_shop_inventory");
        }

        if (CanBuyShopCard(currentScreen))
        {
            names.Add("buy_card");
        }

        if (CanBuyShopRelic(currentScreen))
        {
            names.Add("buy_relic");
        }

        if (CanBuyShopPotion(currentScreen))
        {
            names.Add("buy_potion");
        }

        if (CanRemoveCardAtShop(currentScreen))
        {
            names.Add("remove_card_at_shop");
        }

        if (CanSelectCharacter(currentScreen))
        {
            names.Add("select_character");
        }

        if (CanEmbark(currentScreen))
        {
            names.Add("embark");
        }

        if (CanUnready(currentScreen))
        {
            names.Add("unready");
        }

        if (CanHostMultiplayerLobby(currentScreen))
        {
            names.Add("host_multiplayer_lobby");
        }

        if (CanJoinMultiplayerLobby(currentScreen))
        {
            names.Add("join_multiplayer_lobby");
        }

        if (CanReadyMultiplayerLobby(currentScreen))
        {
            names.Add("ready_multiplayer_lobby");
        }

        if (CanDisconnectMultiplayerLobby(currentScreen))
        {
            names.Add("disconnect_multiplayer_lobby");
        }

        if (CanIncreaseAscension(currentScreen))
        {
            names.Add("increase_ascension");
        }

        if (CanDecreaseAscension(currentScreen))
        {
            names.Add("decrease_ascension");
        }

        if (CanUsePotion(currentScreen, combatState, runState))
        {
            names.Add("use_potion");
        }

        if (CanDiscardPotion(currentScreen, runState))
        {
            names.Add("discard_potion");
        }

        if (CanSaveAndQuit(currentScreen, runState))
        {
            names.Add("save_and_quit");
        }

        if (CanReturnToMainMenu(currentScreen))
        {
            names.Add("return_to_main_menu");
        }

        return names.ToArray();
    }

    private static CombatPayload? BuildCombatPayload(CombatState? combatState)
    {
        var me = LocalContext.GetMe(combatState);
        if (combatState == null || me?.PlayerCombatState == null)
        {
            return null;
        }

        var hand = me.PlayerCombatState.Hand.Cards.ToList();
        var enemies = combatState.Enemies.ToList();
        var orbQueue = me.PlayerCombatState.OrbQueue;
        var orbs = orbQueue.Orbs.ToList();
        var connectedPlayerIds = GetConnectedPlayerIds(combatState.RunState as RunState);

        return new CombatPayload
        {
            player = new CombatPlayerPayload
            {
                current_hp = me.Creature.CurrentHp,
                max_hp = me.Creature.MaxHp,
                block = me.Creature.Block,
                energy = me.PlayerCombatState.Energy,
                stars = me.PlayerCombatState.Stars,
                focus = me.Creature.GetPowerAmount<FocusPower>(),
                powers = BuildCreaturePowerPayloads(me.Creature),
                base_orb_slots = me.BaseOrbSlotCount,
                orb_capacity = orbQueue.Capacity,
                empty_orb_slots = Math.Max(0, orbQueue.Capacity - orbs.Count),
                orbs = orbs.Select((orb, index) => BuildCombatOrbPayload(orb, index)).ToArray(),
                draw_cards = BuildStructuredPileCards(ReadCombatPileCards(me.PlayerCombatState, "DrawPile", "DrawDeck")),
                discard_cards = BuildStructuredPileCards(ReadCombatPileCards(me.PlayerCombatState, "DiscardPile")),
                exhaust_cards = BuildStructuredPileCards(ReadCombatPileCards(me.PlayerCombatState, "ExhaustPile"))
            },
            players = GetOrderedCombatPlayers(combatState)
                .Select(player => BuildCombatPlayerSummaryPayload(player, combatState, connectedPlayerIds, me.NetId))
                .ToArray(),
            hand = hand.Select((card, index) => BuildHandCardPayload(combatState, card, index)).ToArray(),
            enemies = enemies.Select((enemy, index) => BuildEnemyPayload(enemy, index)).ToArray()
        };
    }

    private static PileCardPayload[] BuildStructuredPileCards(CardModel[] cards)
    {
        if (cards == null || cards.Length == 0)
        {
            return Array.Empty<PileCardPayload>();
        }

        return cards
            .Select(card => new PileCardPayload
            {
                card_id = card?.Id.Entry ?? string.Empty,
                upgraded = card?.IsUpgraded ?? false,
                card_type = card?.Type.ToString() ?? string.Empty
            })
            .ToArray();
    }

    private static RunPayload? BuildRunPayload(IScreenContext? currentScreen, CombatState? combatState, RunState? runState)
    {
        var player = LocalContext.GetMe(runState);
        if (player == null || runState == null)
        {
            return null;
        }

        var connectedPlayerIds = GetConnectedPlayerIds(runState);

        return new RunPayload
        {
            character_id = player.Character.Id.Entry,
            character_name = EnglishLocResolver.Resolve(player.Character.Title),
            ascension = runState.AscensionLevel,
            ascension_effects = BuildAscensionEffectPayloads(runState.AscensionLevel),
            floor = runState.TotalFloor,
            current_hp = player.Creature.CurrentHp,
            max_hp = player.Creature.MaxHp,
            gold = player.Gold,
            max_energy = player.MaxEnergy,
            base_orb_slots = player.BaseOrbSlotCount,
            deck = player.Deck.Cards.Select((card, index) => BuildDeckCardPayload(card, index)).ToArray(),
            relics = player.Relics.Select((relic, index) => BuildRunRelicPayload(relic, index)).ToArray(),
            players = runState.Players
                .OrderBy(runState.GetPlayerSlotIndex)
                .Select(otherPlayer => BuildRunPlayerSummaryPayload(runState, otherPlayer, connectedPlayerIds, player.NetId))
                .ToArray(),
            potions = player.PotionSlots.Select((potion, index) =>
                BuildRunPotionPayload(currentScreen, combatState, player, potion, index)).ToArray()
        };
    }

    private static EncounterMetadata ResolveEncounterMetadata(
        IScreenContext? currentScreen,
        CombatState? combatState,
        RunState? runState)
    {
        int? act = runState != null ? ResolveActFromFloor(runState.TotalFloor) : null;
        var isCombatEncounter = CombatManager.Instance.IsInProgress ||
            combatState != null ||
            currentScreen is NCombatRoom;

        if (!isCombatEncounter || runState == null)
        {
            return new EncounterMetadata(null, null, false, act);
        }

        var combatType = ResolveCombatType(runState);
        var bossStage = ResolveBossStage(combatType, runState.TotalFloor, act);

        return new EncounterMetadata(
            combatType,
            bossStage,
            string.Equals(bossStage, "final_boss", StringComparison.Ordinal),
            act);
    }

    private static string ResolveCombatType(RunState runState)
    {
        var currentPoint = FindCurrentMapPoint(runState);
        if (currentPoint != null)
        {
            var currentCoord = currentPoint.coord;
            var secondBossCoord = runState.Map.SecondBossMapPoint?.coord;
            var isBossNode = currentCoord == runState.Map.BossMapPoint.coord;
            var isSecondBossNode = secondBossCoord.HasValue && currentCoord == secondBossCoord.Value;
            return NormalizeCombatType(currentPoint.PointType.ToString(), isBossNode, isSecondBossNode);
        }

        if (BossStageByFloor.ContainsKey(runState.TotalFloor))
        {
            return "boss";
        }

        return "monster";
    }

    private static MapPoint? FindCurrentMapPoint(RunState runState)
    {
        if (!runState.CurrentMapCoord.HasValue)
        {
            return null;
        }

        var currentCoord = runState.CurrentMapCoord.Value;
        return GetAllMapPoints(runState.Map).FirstOrDefault(point => point.coord == currentCoord);
    }

    private static string NormalizeCombatType(
        string? nodeType,
        bool isBossNode = false,
        bool isSecondBossNode = false)
    {
        if (isBossNode || isSecondBossNode)
        {
            return "boss";
        }

        var normalized = (nodeType ?? string.Empty).Trim().ToLowerInvariant();
        if (normalized.Contains("elite", StringComparison.Ordinal))
        {
            return "elite";
        }

        if (normalized.Contains("boss", StringComparison.Ordinal))
        {
            return "boss";
        }

        return "monster";
    }

    private static string? ResolveBossStage(string? combatType, int floor, int? act)
    {
        if (!string.Equals(combatType, "boss", StringComparison.Ordinal))
        {
            return null;
        }

        var resolvedAct = act ?? ResolveActFromFloor(floor);
        if (resolvedAct <= 1)
        {
            return "act1_boss";
        }

        if (resolvedAct == 2)
        {
            return "act2_boss";
        }

        if (BossStageByFloor.TryGetValue(floor, out var bossStage))
        {
            return bossStage;
        }

        return "final_boss";
    }

    private static int ResolveActFromFloor(int floor)
    {
        if (floor <= 17)
        {
            return 1;
        }

        if (floor <= 34)
        {
            return 2;
        }

        return 3;
    }

    private static object BuildAgentViewPayload(
        string screen,
        SessionPayload session,
        string runId,
        int? turn,
        string[] availableActions,
        CombatState? combatState,
        RunState? runState,
        CombatPayload? combat,
        RunPayload? run,
        MapPayload? map,
        SelectionPayload? selection,
        CardsViewPayload? cardsView,
        CharacterSelectPayload? characterSelect,
        TimelinePayload? timeline,
        ChestPayload? chest,
        EventPayload? eventPayload,
        ShopPayload? shop,
        RestPayload? rest,
        RewardPayload? reward,
        ModalPayload? modal,
        GameOverPayload? gameOver,
        EncounterMetadata encounterMetadata)
    {
        var glossaryTerms = new HashSet<string>(StringComparer.Ordinal);

        return new
        {
            version = AgentViewVersion,
            screen,
            run_id = runId,
            session,
            turn,
            actions = availableActions,
            available_actions = availableActions,
            combat_type = encounterMetadata.CombatType,
            boss_stage = encounterMetadata.BossStage,
            is_final_boss = encounterMetadata.IsFinalBoss,
            act = encounterMetadata.Act,
            combat = BuildAgentCombatPayload(combatState, combat, glossaryTerms),
            run = BuildAgentRunPayload(combatState, runState, run, glossaryTerms),
            map = BuildAgentMapPayload(map),
            selection = BuildAgentSelectionPayload(selection, glossaryTerms),
            cards_view = BuildAgentCardsViewPayload(cardsView, glossaryTerms),
            character_select = BuildAgentCharacterSelectPayload(characterSelect),
            timeline = BuildAgentTimelinePayload(timeline),
            chest = BuildAgentChestPayload(chest),
            @event = BuildAgentEventPayload(eventPayload),
            shop = BuildAgentShopPayload(shop, glossaryTerms),
            rest = BuildAgentRestPayload(rest),
            reward = BuildAgentRewardPayload(reward, glossaryTerms),
            modal = BuildAgentModalPayload(modal),
            game_over = BuildAgentGameOverPayload(gameOver),
            glossary = BuildAgentGlossary(glossaryTerms)
        };
    }

    private static object? BuildAgentCombatPayload(
        CombatState? combatState,
        CombatPayload? combat,
        HashSet<string> glossaryTerms)
    {
        if (combat == null)
        {
            return null;
        }

        var liveHand = LocalContext.GetMe(combatState)?.PlayerCombatState?.Hand.Cards.ToList()
            ?? new List<CardModel>();
        var playerCombatState = LocalContext.GetMe(combatState)?.PlayerCombatState;

        return new
        {
            player = new
            {
                hp = $"{combat.player.current_hp}/{combat.player.max_hp}",
                block = combat.player.block,
                energy = combat.player.energy,
                stars = combat.player.stars,
                focus = combat.player.focus,
                orbs = combat.player.orbs.Select(orb => FormatOrbLine(orb)).ToArray()
            },
            hand = combat.hand.Select(card =>
                BuildAgentHandCardPayload(
                    card,
                    card.index >= 0 && card.index < liveHand.Count ? liveHand[card.index] : null,
                    glossaryTerms)).ToArray(),
            draw = BuildAgentCardStacks(ReadCombatPileCards(playerCombatState, "DrawPile", "DrawDeck"), glossaryTerms),
            discard = BuildAgentCardStacks(ReadCombatPileCards(playerCombatState, "DiscardPile"), glossaryTerms),
            exhaust = BuildAgentCardStacks(ReadCombatPileCards(playerCombatState, "ExhaustPile"), glossaryTerms),
            enemies = combat.enemies.Select(enemy => new
            {
                i = enemy.index,
                name = enemy.name,
                hp = $"{enemy.current_hp}/{enemy.max_hp}",
                block = enemy.block,
                intent = enemy.intent,
                alive = enemy.is_alive,
                hittable = enemy.is_hittable
            }).ToArray()
        };
    }

    private static object? BuildAgentRunPayload(
        CombatState? combatState,
        RunState? runState,
        RunPayload? run,
        HashSet<string> glossaryTerms)
    {
        if (run == null)
        {
            return null;
        }

        var player = LocalContext.GetMe(runState);
        var deckCards = player?.Deck.Cards.ToArray() ?? Array.Empty<CardModel>();
        var combatPlayer = LocalContext.GetMe(combatState)?.PlayerCombatState;

        foreach (var effect in run.ascension_effects)
        {
            CollectGlossaryTerms(glossaryTerms, effect.name);
            CollectGlossaryTerms(glossaryTerms, effect.description);
        }

        return new
        {
            character = run.character_name,
            ascension = run.ascension,
            ascension_effects = run.ascension_effects,
            floor = run.floor,
            hp = $"{run.current_hp}/{run.max_hp}",
            gold = run.gold,
            max_energy = run.max_energy,
            base_orb_slots = run.base_orb_slots,
            deck = deckCards.Length > 0
                ? BuildAgentCardStacks(deckCards, glossaryTerms)
                : BuildAgentCardStacks(run.deck, glossaryTerms),
            relics = run.relics
                .Select(relic => relic.is_melted ? $"{relic.name} (melted)" : relic.name)
                .ToArray(),
            potions = run.potions.Select(potion => new
            {
                i = potion.index,
                line = FormatPotionLine(potion),
                usable = potion.can_use,
                discard = potion.can_discard,
                target = NormalizeTargetHint(potion.target_type),
                targets = potion.valid_target_indices
            }).ToArray(),
            piles = new
            {
                draw = BuildAgentCardStacks(ReadCombatPileCards(combatPlayer, "DrawPile", "DrawDeck"), glossaryTerms),
                discard = BuildAgentCardStacks(ReadCombatPileCards(combatPlayer, "DiscardPile"), glossaryTerms),
                exhaust = BuildAgentCardStacks(ReadCombatPileCards(combatPlayer, "ExhaustPile"), glossaryTerms)
            }
        };
    }

    private static object? BuildAgentSelectionPayload(SelectionPayload? selection, HashSet<string> glossaryTerms)
    {
        if (selection == null)
        {
            return null;
        }

        CollectGlossaryTerms(glossaryTerms, selection.prompt);

        return new
        {
            kind = selection.kind,
            prompt = selection.prompt,
            min = selection.min_select,
            max = selection.max_select,
            selected = selection.selected_count,
            confirm = selection.can_confirm,
            cards = selection.cards.Select(card => BuildAgentChoiceCardPayload(card.index, card.name, card.upgraded, card.energy_cost, card.star_cost, card.costs_x, card.star_costs_x, GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text), glossaryTerms)).ToArray(),
            selected_cards = selection.selected_cards.Select(card => BuildAgentChoiceCardPayload(card.index, card.name, card.upgraded, card.energy_cost, card.star_cost, card.costs_x, card.star_costs_x, GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text), glossaryTerms)).ToArray(),
            selectable_cards = selection.selectable_cards.Select(card => BuildAgentChoiceCardPayload(card.index, card.name, card.upgraded, card.energy_cost, card.star_cost, card.costs_x, card.star_costs_x, GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text), glossaryTerms)).ToArray(),
            preview_cards = selection.preview_cards.Select(card => BuildAgentChoiceCardPayload(card.index, card.name, card.upgraded, card.energy_cost, card.star_cost, card.costs_x, card.star_costs_x, GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text), glossaryTerms)).ToArray()
        };
    }

    private static object? BuildAgentCardsViewPayload(CardsViewPayload? cardsView, HashSet<string> glossaryTerms)
    {
        if (cardsView == null)
        {
            return null;
        }

        CollectGlossaryTerms(glossaryTerms, cardsView.title);

        return new
        {
            title = cardsView.title,
            cards = cardsView.cards.Select(card => BuildAgentChoiceCardPayload(card.index, card.name, card.upgraded, card.energy_cost, card.star_cost, card.costs_x, card.star_costs_x, GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text), glossaryTerms)).ToArray()
        };
    }

    private static object? BuildAgentRewardPayload(RewardPayload? reward, HashSet<string> glossaryTerms)
    {
        if (reward == null)
        {
            return null;
        }

        foreach (var option in reward.rewards)
        {
            CollectGlossaryTerms(glossaryTerms, option.description);
        }

        return new
        {
            pending_card_choice = reward.pending_card_choice,
            can_proceed = reward.can_proceed,
            rewards = reward.rewards.Select(option => new
            {
                i = option.index,
                line = $"{option.reward_type}: {option.description}",
                claimable = option.claimable
            }).ToArray(),
            cards = reward.card_options.Select(card => BuildAgentChoiceCardPayload(card.index, card.name, card.upgraded, null, null, false, false, GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text), glossaryTerms)).ToArray(),
            alternatives = reward.alternatives.Select(option => new
            {
                i = option.index,
                line = option.label
            }).ToArray()
        };
    }

    private static object? BuildAgentEventPayload(EventPayload? eventPayload)
    {
        if (eventPayload == null)
        {
            return null;
        }

        return new
        {
            id = eventPayload.event_id,
            title = eventPayload.title,
            finished = eventPayload.is_finished,
            options = eventPayload.options.Select(option => new
            {
                i = option.index,
                line = FormatEventOptionLine(option),
                locked = option.is_locked,
                proceed = option.is_proceed
            }).ToArray()
        };
    }

    private static object? BuildAgentShopPayload(ShopPayload? shop, HashSet<string> glossaryTerms)
    {
        if (shop == null)
        {
            return null;
        }

        return new
        {
            open = shop.is_open,
            can_open = shop.can_open,
            can_close = shop.can_close,
            cards = shop.cards.Select(card =>
                BuildAgentPricedCardPayload(
                    card.index,
                    card.name,
                    card.upgraded,
                    card.energy_cost,
                    card.star_cost,
                    card.costs_x,
                    card.star_costs_x,
                    GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text),
                    card.price,
                    card.enough_gold,
                    glossaryTerms)).ToArray(),
            relics = shop.relics.Select(relic => new
            {
                i = relic.index,
                line = $"{relic.name} [{relic.rarity}] | {relic.price}g",
                affordable = relic.enough_gold,
                stocked = relic.is_stocked
            }).ToArray(),
            potions = shop.potions.Select(potion => new
            {
                i = potion.index,
                line = $"{potion.name ?? "empty"}{(string.IsNullOrWhiteSpace(potion.usage) ? string.Empty : $": {potion.usage}")} | {potion.price}g",
                affordable = potion.enough_gold,
                stocked = potion.is_stocked
            }).ToArray(),
            remove = shop.card_removal == null
                ? null
                : new
                {
                    price = shop.card_removal.price,
                    affordable = shop.card_removal.enough_gold,
                    available = shop.card_removal.available,
                    used = shop.card_removal.used
                }
        };
    }

    private static object? BuildAgentRestPayload(RestPayload? rest)
    {
        if (rest == null)
        {
            return null;
        }

        return new
        {
            options = rest.options.Select(option => new
            {
                i = option.index,
                line = string.IsNullOrWhiteSpace(option.description)
                    ? option.title
                    : $"{option.title}: {option.description}",
                enabled = option.is_enabled
            }).ToArray()
        };
    }

    private static object? BuildAgentMapPayload(MapPayload? map)
    {
        if (map == null)
        {
            return null;
        }

        return new
        {
            current = map.current_node == null ? null : $"{map.current_node.row},{map.current_node.col}",
            options = map.available_nodes.Select(node => new
            {
                i = node.index,
                line = $"{node.node_type} ({node.row},{node.col})"
            }).ToArray()
        };
    }

    private static object? BuildAgentCharacterSelectPayload(CharacterSelectPayload? characterSelect)
    {
        if (characterSelect == null)
        {
            return null;
        }

        return new
        {
            selected = characterSelect.selected_character_id,
            embark = characterSelect.can_embark,
            ascension = characterSelect.ascension,
            characters = characterSelect.characters.Select(character => new
            {
                i = character.index,
                line = character.is_random ? $"{character.name} (random)" : character.name,
                locked = character.is_locked,
                selected = character.is_selected
            }).ToArray()
        };
    }

    private static object? BuildAgentTimelinePayload(TimelinePayload? timeline)
    {
        if (timeline == null)
        {
            return null;
        }

        return new
        {
            back = timeline.back_enabled,
            confirm = timeline.can_confirm_overlay,
            slots = timeline.slots.Select(slot => new
            {
                i = slot.index,
                line = $"{slot.title} [{slot.state}]",
                actionable = slot.is_actionable
            }).ToArray()
        };
    }

    private static object? BuildAgentChestPayload(ChestPayload? chest)
    {
        if (chest == null)
        {
            return null;
        }

        return new
        {
            opened = chest.is_opened,
            claimed = chest.has_relic_been_claimed,
            relics = chest.relic_options.Select(relic => new
            {
                i = relic.index,
                line = $"{relic.name} [{relic.rarity}]"
            }).ToArray()
        };
    }

    private static object? BuildAgentModalPayload(ModalPayload? modal)
    {
        if (modal == null)
        {
            return null;
        }

        return new
        {
            type = modal.type_name,
            confirm = modal.can_confirm,
            dismiss = modal.can_dismiss,
            confirm_label = modal.confirm_label,
            dismiss_label = modal.dismiss_label
        };
    }

    private static object? BuildAgentGameOverPayload(GameOverPayload? gameOver)
    {
        if (gameOver == null)
        {
            return null;
        }

        return new
        {
            victory = gameOver.is_victory,
            floor = gameOver.floor,
            character = gameOver.character_id,
            can_continue = gameOver.can_continue,
            can_return = gameOver.can_return_to_main_menu
        };
    }

    private static object BuildAgentHandCardPayload(
        CombatHandCardPayload card,
        CardModel? liveCard,
        HashSet<string> glossaryTerms)
    {
        var displayRulesText = GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text);
        var mods = GetCardModifierTags(liveCard);
        var keywords = GetGlossaryMatches(displayRulesText, mods);
        CollectGlossaryTerms(glossaryTerms, displayRulesText, mods);

        return new
        {
            i = card.index,
            line = FormatCardLine(card.name, card.upgraded, 1, card.energy_cost, card.star_cost, card.costs_x, card.star_costs_x, displayRulesText),
            type = card.card_type,
            playable = card.playable,
            target = card.requires_target ? NormalizeTargetHint(card.target_index_space ?? card.target_type) : null,
            targets = card.requires_target ? card.valid_target_indices : Array.Empty<int>(),
            why = card.playable ? null : card.unplayable_reason,
            keywords,
            mods
        };
    }

    private static object BuildAgentChoiceCardPayload(
        int index,
        string name,
        bool upgraded,
        int? energyCost,
        int? starCost,
        bool costsX,
        bool starCostsX,
        string rulesText,
        HashSet<string> glossaryTerms)
    {
        var keywords = GetGlossaryMatches(rulesText);
        CollectGlossaryTerms(glossaryTerms, rulesText);

        return new
        {
            i = index,
            line = FormatCardLine(name, upgraded, 1, energyCost, starCost, costsX, starCostsX, rulesText),
            keywords,
            mods = Array.Empty<string>()
        };
    }

    private static object BuildAgentPricedCardPayload(
        int index,
        string name,
        bool upgraded,
        int energyCost,
        int starCost,
        bool costsX,
        bool starCostsX,
        string rulesText,
        int price,
        bool enoughGold,
        HashSet<string> glossaryTerms)
    {
        var keywords = GetGlossaryMatches(rulesText);
        CollectGlossaryTerms(glossaryTerms, rulesText);

        return new
        {
            i = index,
            line = $"{FormatCardLine(name, upgraded, 1, energyCost, starCost, costsX, starCostsX, rulesText)} | {price}g",
            affordable = enoughGold,
            keywords,
            mods = Array.Empty<string>()
        };
    }

    private static object[] BuildAgentCardStacks(IEnumerable<CardModel> cards, HashSet<string> glossaryTerms)
    {
        var descriptors = cards
            .Select(card => BuildAgentCardDescriptor(card, glossaryTerms))
            .ToArray();

        return BuildAgentCardStacks(descriptors);
    }

    private static object[] BuildAgentCardStacks(IEnumerable<DeckCardPayload> cards, HashSet<string> glossaryTerms)
    {
        var descriptors = cards
            .Select(card => BuildAgentCardDescriptor(card, glossaryTerms))
            .ToArray();

        return BuildAgentCardStacks(descriptors);
    }

    private static object[] BuildAgentCardStacks(IEnumerable<AgentCardDescriptor> descriptors)
    {
        return descriptors
            .GroupBy(descriptor => descriptor.GroupKey, StringComparer.Ordinal)
            .Select(group =>
            {
                var first = group.First();
                var line = FormatCardLine(first.name, first.upgraded, group.Count(), first.energy_cost, first.star_cost, first.costs_x, first.star_costs_x, first.rules_text);

                return new
                {
                    line,
                    keywords = first.keywords,
                    mods = first.mods
                };
            })
            .OrderBy(item => item.line, StringComparer.Ordinal)
            .Cast<object>()
            .ToArray();
    }

    private static AgentCardDescriptor BuildAgentCardDescriptor(CardModel card, HashSet<string> glossaryTerms)
    {
        var rulesText = GetResolvedCardRulesText(card);
        var mods = GetCardModifierTags(card);
        var keywords = GetGlossaryMatches(rulesText, mods);
        CollectGlossaryTerms(glossaryTerms, rulesText, mods);

        return new AgentCardDescriptor(
            EnglishLocResolver.ResolveCardTitle(card),
            card.IsUpgraded,
            card.EnergyCost.GetWithModifiers(CostModifiers.All),
            Math.Max(0, card.GetStarCostWithModifiers()),
            card.EnergyCost.CostsX,
            card.HasStarCostX,
            rulesText,
            keywords,
            mods);
    }

    private static AgentCardDescriptor BuildAgentCardDescriptor(DeckCardPayload card, HashSet<string> glossaryTerms)
    {
        var rulesText = GetPreferredCardRulesText(card.rules_text, card.resolved_rules_text);
        var keywords = GetGlossaryMatches(rulesText);
        CollectGlossaryTerms(glossaryTerms, rulesText);

        return new AgentCardDescriptor(
            card.name,
            card.upgraded,
            card.energy_cost,
            card.star_cost,
            card.costs_x,
            card.star_costs_x,
            rulesText,
            keywords,
            Array.Empty<string>());
    }

    private static string FormatCardLine(
        string name,
        bool upgraded,
        int count,
        int? energyCost,
        int? starCost,
        bool costsX,
        bool starCostsX,
        string rulesText)
    {
        var title = upgraded && !name.EndsWith("+", StringComparison.Ordinal) ? $"{name}+" : name;
        if (count > 1)
        {
            title = $"{title}*{count}";
        }

        var cost = FormatCardCost(energyCost, starCost, costsX, starCostsX);
        var prefix = string.IsNullOrWhiteSpace(cost) ? title : $"{title} [{cost}]";
        return string.IsNullOrWhiteSpace(rulesText)
            ? prefix
            : $"{prefix}: {rulesText}";
    }

    private static string FormatCardCost(int? energyCost, int? starCost, bool costsX, bool starCostsX)
    {
        // STS-conventional notation: bare number for energy cost (1, 2, X), prefixed
        // ★ for star cost (★1, ★X). Locale-blind so the agent gets a stable format
        // regardless of the player's UI language.
        var parts = new List<string>();
        if (costsX)
        {
            parts.Add("X");
        }
        else if (energyCost.HasValue)
        {
            parts.Add($"{Math.Max(0, energyCost.Value)}");
        }

        if (starCostsX)
        {
            parts.Add("★X");
        }
        else if (starCost.HasValue && starCost.Value > 0)
        {
            parts.Add($"★{starCost.Value}");
        }

        return string.Join("/", parts);
    }

    private static string FormatOrbLine(CombatOrbPayload orb)
    {
        return $"{orb.name} passive {orb.passive_value} / evoke {orb.evoke_value}";
    }

    private static string FormatPotionLine(RunPotionPayload potion)
    {
        if (!potion.occupied)
        {
            return $"{potion.index}: empty";
        }

        var usage = string.IsNullOrWhiteSpace(potion.usage) ? string.Empty : $": {potion.usage}";
        return $"{potion.index}: {potion.name}{usage}";
    }

    private static string FormatEventOptionLine(EventOptionPayload option)
    {
        var segments = new List<string>();
        if (!string.IsNullOrWhiteSpace(option.title))
        {
            segments.Add(option.title);
        }

        if (!string.IsNullOrWhiteSpace(option.description))
        {
            segments.Add(option.description);
        }

        if (segments.Count == 0 && !string.IsNullOrWhiteSpace(option.text_key))
        {
            segments.Add(option.text_key);
        }

        return string.Join(" | ", segments);
    }

    private static CardModel[] ReadCombatPileCards(object? playerCombatState, params string[] memberNames)
    {
        if (playerCombatState == null)
        {
            return Array.Empty<CardModel>();
        }

        foreach (var memberName in memberNames)
        {
            var memberValue = TryGetMemberValue(playerCombatState, memberName);
            var cards = ExtractCards(memberValue);
            if (cards.Length > 0 || memberValue != null)
            {
                return cards;
            }
        }

        return Array.Empty<CardModel>();
    }

    private static CardModel[] ExtractCards(object? value)
    {
        return ExtractCards(value, new HashSet<object>(ReferenceEqualityComparer.Instance));
    }

    private static CardModel[] ExtractCards(object? value, HashSet<object> visited)
    {
        if (value == null)
        {
            return Array.Empty<CardModel>();
        }

        if (!visited.Add(value))
        {
            return Array.Empty<CardModel>();
        }

        if (value is IEnumerable enumerable and not string)
        {
            var cards = new List<CardModel>();
            foreach (var item in enumerable)
            {
                if (item is CardModel card)
                {
                    cards.Add(card);
                }
            }

            if (cards.Count > 0)
            {
                return cards.ToArray();
            }
        }

        foreach (var memberName in new[] { "Cards", "CardModels", "Entries", "List" })
        {
            var nested = TryGetMemberValue(value, memberName);
            if (nested == null)
            {
                continue;
            }

            var cards = ExtractCards(nested, visited);
            if (cards.Length > 0)
            {
                return cards;
            }
        }

        return Array.Empty<CardModel>();
    }

    private static object? TryGetMemberValue(object instance, string memberName)
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;

        try
        {
            var property = instance.GetType().GetProperty(memberName, flags);
            if (property != null)
            {
                return property.GetValue(instance);
            }

            var field = instance.GetType().GetField(memberName, flags);
            if (field != null)
            {
                return field.GetValue(instance);
            }
        }
        catch
        {
        }

        return null;
    }

    private static string[] GetCardModifierTags(CardModel? card)
    {
        if (card == null)
        {
            return Array.Empty<string>();
        }

        var values = new HashSet<string>(StringComparer.Ordinal);
        foreach (var memberName in new[]
        {
            "Enchantments",
            "Enchants",
            "Modifiers",
            "ModifierIds",
            "Affixes",
            "Augments",
            "Keywords"
        })
        {
            var memberValue = TryGetMemberValue(card, memberName);
            foreach (var token in ExtractModifierTokens(memberValue))
            {
                if (string.IsNullOrWhiteSpace(token))
                {
                    continue;
                }

                values.Add(NormalizeCardRulesText(token));
            }
        }

        return values.OrderBy(value => value, StringComparer.Ordinal).ToArray();
    }

    private static IEnumerable<string> ExtractModifierTokens(object? value)
    {
        if (value == null)
        {
            yield break;
        }

        if (value is string text)
        {
            if (!string.IsNullOrWhiteSpace(text))
            {
                yield return text;
            }

            yield break;
        }

        if (value is IEnumerable enumerable)
        {
            foreach (var item in enumerable)
            {
                foreach (var token in ExtractModifierTokens(item))
                {
                    yield return token;
                }
            }

            yield break;
        }

        foreach (var memberName in new[] { "Title", "Name", "Keyword", "Text", "Description", "Label" })
        {
            var memberValue = TryGetMemberValue(value, memberName);
            if (TryCoerceText(memberValue) is { Length: > 0 } memberText)
            {
                yield return memberText;
            }
        }

        var idValue = TryGetMemberValue(value, "Id");
        if (idValue != null)
        {
            var entryValue = TryGetMemberValue(idValue, "Entry");
            if (entryValue is string entryText && !string.IsNullOrWhiteSpace(entryText))
            {
                yield return entryText;
            }
        }
    }

    private static string[] GetGlossaryMatches(string text, params string[][] modifierGroups)
    {
        var values = new HashSet<string>(StringComparer.Ordinal);

        foreach (var (keyword, _) in AgentKeywordDefinitions)
        {
            if (!string.IsNullOrWhiteSpace(text) && text.Contains(keyword, StringComparison.Ordinal))
            {
                values.Add(keyword);
            }

            foreach (var modifierGroup in modifierGroups)
            {
                if (modifierGroup.Any(modifier => modifier.Contains(keyword, StringComparison.Ordinal)))
                {
                    values.Add(keyword);
                }
            }
        }

        return values.OrderBy(value => value, StringComparer.Ordinal).ToArray();
    }

    private static void CollectGlossaryTerms(HashSet<string> glossaryTerms, string? text, params string[][] modifierGroups)
    {
        if (glossaryTerms.Count >= AgentKeywordDefinitions.Length)
        {
            return;
        }

        foreach (var keyword in GetGlossaryMatches(text ?? string.Empty, modifierGroups))
        {
            glossaryTerms.Add(keyword);
        }
    }

    private static Dictionary<string, string> BuildAgentGlossary(HashSet<string> glossaryTerms)
    {
        var glossary = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var (keyword, definition) in AgentKeywordDefinitions)
        {
            if (glossaryTerms.Contains(keyword))
            {
                glossary[keyword] = definition;
            }
        }

        return glossary;
    }

    private static string? NormalizeTargetHint(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        var normalized = value.Trim().ToLowerInvariant();
        if (normalized.Contains("enemy", StringComparison.Ordinal))
        {
            return "enemy";
        }

        if (normalized.Contains("player", StringComparison.Ordinal) || normalized.Contains("self", StringComparison.Ordinal))
        {
            return "player";
        }

        return normalized;
    }

    private static readonly (string keyword, string definition)[] AgentKeywordDefinitions =
    {
        ("Strength", "Each stack of Strength typically adds 1 damage per attack hit."),
        ("Dexterity", "Each stack of Dexterity typically adds 1 to Block gained."),
        ("Vulnerable", "Vulnerable targets take more attack damage."),
        ("Weak", "Weak targets deal less attack damage."),
        ("Frail", "Frail targets gain less Block."),
        ("Block", "Block absorbs incoming damage before HP is lost."),
        ("Exhaust", "Exhausted cards are removed from this combat after being played."),
        ("Retain", "Retain cards are not discarded at the end of your turn."),
        ("Poison", "Poison deals equal HP loss at end of turn, then decreases by 1."),
        ("Stun", "Stun cards typically cannot be played voluntarily."),
        ("Burn", "Burn cards typically deal extra damage from hand or on resolution."),
        ("Void", "Void cards typically consume energy when drawn or block plays."),
        ("Lose Strength", "Lose Strength temporarily reduces Strength."),
        ("Focus", "Focus typically boosts orb passive and evoke effects."),
        ("Orb Slot", "Orb Slot determines how many orbs you can hold at once."),
        ("Enchantment", "Enchantments are extra effects or modifiers attached to cards."),
        ("Infused", "Infused indicates a card carries an extra attached effect."),
        ("Temporary", "Temporary cards typically leave the deck rotation at end of turn or after being played.")
    };

    private static MultiplayerPayload? BuildMultiplayerPayload(IScreenContext? currentScreen, RunState? runState)
    {
        var multiplayerTestScene = GetMultiplayerTestScene();
        var multiplayerTestLobby = multiplayerTestScene != null ? GetMultiplayerTestLobby(multiplayerTestScene) : null;
        if (multiplayerTestLobby != null)
        {
            return new MultiplayerPayload
            {
                is_multiplayer = true,
                net_game_type = multiplayerTestLobby.NetService.Type.ToString(),
                local_player_id = NetIdToString(multiplayerTestLobby.LocalPlayer.id),
                player_count = multiplayerTestLobby.Players.Count,
                connected_player_ids = multiplayerTestLobby.Players
                    .OrderBy(player => player.slotId)
                    .Select(player => NetIdToString(player.id))
                    .ToArray()
            };
        }

        var characterSelectScreen = GetCharacterSelectScreen(currentScreen);
        if (characterSelectScreen != null)
        {
            var lobby = characterSelectScreen.Lobby;
            if (!lobby.NetService.Type.IsMultiplayer())
            {
                return null;
            }

            return new MultiplayerPayload
            {
                is_multiplayer = true,
                net_game_type = lobby.NetService.Type.ToString(),
                local_player_id = NetIdToString(lobby.LocalPlayer.id),
                player_count = lobby.Players.Count,
                connected_player_ids = lobby.Players
                    .OrderBy(player => player.slotId)
                    .Select(player => NetIdToString(player.id))
                    .ToArray()
            };
        }

        if (runState == null || !RunManager.Instance.NetService.Type.IsMultiplayer())
        {
            return null;
        }

        var localPlayer = GetLocalPlayer(runState);
        return new MultiplayerPayload
        {
            is_multiplayer = true,
            net_game_type = RunManager.Instance.NetService.Type.ToString(),
            local_player_id = localPlayer != null ? NetIdToString(localPlayer.NetId) : null,
            player_count = runState.Players.Count,
            connected_player_ids = GetConnectedPlayerIds(runState)
                .OrderBy(id => runState.GetPlayerSlotIndex(id))
                .Select(NetIdToString)
                .ToArray()
        };
    }

    private static MultiplayerLobbyPayload? BuildMultiplayerLobbyPayload(IScreenContext? currentScreen)
    {
        var scene = GetMultiplayerTestScene();
        if (scene == null)
        {
            return null;
        }

        var lobby = GetMultiplayerTestLobby(scene);
        var selectedCharacterId = lobby?.LocalPlayer.character?.Id.Entry
            ?? GetMultiplayerTestCharacterPaginator(scene)?.Character?.Id.Entry;
        var localPlayerId = lobby != null ? NetIdToString(lobby.LocalPlayer.id) : null;

        return new MultiplayerLobbyPayload
        {
            net_game_type = lobby?.NetService.Type.ToString() ?? NetGameType.Singleplayer.ToString(),
            join_host = GetMultiplayerLobbyJoinHost(),
            join_port = GetMultiplayerLobbyJoinPort(),
            local_net_id_hint = NetIdToString(GetMultiplayerLobbyJoinNetIdHint()),
            has_lobby = lobby != null,
            is_host = lobby?.NetService.Type == NetGameType.Host,
            is_client = lobby?.NetService.Type == NetGameType.Client,
            local_ready = lobby?.LocalPlayer.isReady ?? false,
            can_host = CanHostMultiplayerLobby(currentScreen),
            can_join = CanJoinMultiplayerLobby(currentScreen),
            can_ready = CanReadyMultiplayerLobby(currentScreen),
            can_disconnect = CanDisconnectMultiplayerLobby(currentScreen),
            can_unready = CanUnready(currentScreen),
            selected_character_id = selectedCharacterId,
            player_count = lobby?.Players.Count ?? 0,
            max_players = lobby != null
                ? lobby.MaxPlayers > 0 ? lobby.MaxPlayers : lobby.Players.Count
                : 4,
            players = lobby?.Players
                .OrderBy(player => player.slotId)
                .Select(player => BuildCharacterSelectPlayerPayload(player, lobby.LocalPlayer.id))
                .ToArray() ?? Array.Empty<CharacterSelectPlayerPayload>(),
            characters = GetMultiplayerLobbyCharacters()
                .Select((character, index) => new CharacterSelectOptionPayload
                {
                    index = index,
                    character_id = character.Id.Entry,
                    name = EnglishLocResolver.Resolve(character.Title),
                    is_locked = false,
                    is_selected = selectedCharacterId == character.Id.Entry,
                    is_random = false
                })
                .ToArray()
        };
    }

    private static MapPayload? BuildMapPayload(IScreenContext? currentScreen, RunState? runState)
    {
        if (!TryGetMapScreen(currentScreen, runState, out var mapScreen))
        {
            return null;
        }

        var visibleNodes = FindDescendants<NMapPoint>(mapScreen!)
            .Where(node => GodotObject.IsInstanceValid(node))
            .GroupBy(node => node.Point.coord)
            .ToDictionary(
                group => group.Key,
                group => group
                    .OrderBy(node => node.GlobalPosition.Y)
                    .ThenBy(node => node.GlobalPosition.X)
                    .First());

        var availableNodes = visibleNodes.Values
            .Where(node => node.IsEnabled)
            .OrderBy(node => node.Point.coord.row)
            .ThenBy(node => node.Point.coord.col)
            .ToArray();
        var availableCoords = new HashSet<MapCoord>(availableNodes.Select(node => node.Point.coord));
        var visitedCoords = new HashSet<MapCoord>(runState!.VisitedMapCoords);
        var allMapPoints = GetAllMapPoints(runState.Map);

        return new MapPayload
        {
            current_node = BuildMapCoordPayload(runState!.CurrentMapCoord),
            is_travel_enabled = mapScreen!.IsTravelEnabled,
            is_traveling = mapScreen.IsTraveling,
            map_generation_count = RunManager.Instance.MapSelectionSynchronizer.MapGenerationCount,
            rows = runState.Map.GetRowCount(),
            cols = runState.Map.GetColumnCount(),
            starting_node = BuildMapCoordPayload(runState.Map.StartingMapPoint.coord),
            boss_node = BuildMapCoordPayload(runState.Map.BossMapPoint.coord),
            second_boss_node = BuildMapCoordPayload(runState.Map.SecondBossMapPoint?.coord),
            nodes = allMapPoints
                .Select(point => BuildMapGraphNodePayload(
                    point,
                    visibleNodes.TryGetValue(point.coord, out var mapNode) ? mapNode : null,
                    visitedCoords,
                    availableCoords,
                    runState.CurrentMapCoord,
                    runState.Map.StartingMapPoint.coord,
                    runState.Map.BossMapPoint.coord,
                    runState.Map.SecondBossMapPoint?.coord))
                .ToArray(),
            available_nodes = availableNodes.Select((node, index) => BuildMapNodePayload(node, index)).ToArray()
        };
    }

    /// <summary>
    /// Top-level structured bundle payload for NChooseABundleSelectionScreen
    /// (e.g. ScrollBoxes Ancient relic).  Each entry is one bundle the agent
    /// can pick; cards inside are explicit so the agent doesn't have to
    /// decode flattened preview indices.
    ///
    /// Returns null when not on a bundle-selection screen.
    /// </summary>
    private static BundlePayload[]? BuildBundlesPayload(IScreenContext? currentScreen)
    {
        if (currentScreen is not NChooseABundleSelectionScreen bundleScreen)
        {
            return null;
        }

        var bundles = GetBundleSelectionOptions(bundleScreen);
        if (bundles.Count == 0)
        {
            return null;
        }

        return bundles
            .Select((bundle, bundleIdx) =>
            {
                var cards = bundle.Bundle ?? Array.Empty<CardModel>() as IReadOnlyList<CardModel>;
                return new BundlePayload
                {
                    index = bundleIdx,
                    cards = cards
                        .Select((card, cardIdx) => new BundleCardPayload
                        {
                            index = cardIdx,
                            card_id = card.Id.Entry,
                            name = card.Title,
                            upgraded = card.IsUpgraded,
                            card_type = card.Type.ToString(),
                            rarity = card.Rarity.ToString(),
                            energy_cost = card.EnergyCost.GetWithModifiers(CostModifiers.All),
                            costs_x = card.EnergyCost.CostsX,
                            rules_text = GetCardRulesText(card),
                            resolved_rules_text = GetResolvedCardRulesText(card),
                            dynamic_values = BuildCardDynamicValuePayloads(card)
                        })
                        .ToArray()
                };
            })
            .ToArray();
    }

    /// <summary>
    /// Builds a bundle-select SelectionPayload for NChooseABundleSelectionScreen.
    /// Each NCardBundle becomes one selectable option; its Bundle property supplies the CardModel list.
    /// preview_cards contains ALL cards across all bundles, ordered by bundle index then card position.
    /// </summary>
    private static SelectionPayload? BuildBundleSelectionPayload(NChooseABundleSelectionScreen bundleScreen)
    {
        var bundles = GetBundleSelectionOptions(bundleScreen);
        if (bundles.Count == 0)
        {
            return null;
        }

        var prompt = GetDeckSelectionPrompt(bundleScreen) ?? string.Empty;
        var canConfirm = TryGetSelectionConfirmButton(bundleScreen, out _);

        // Each bundle option: use the first CardModel from Bundle as representative
        var cards = bundles
            .Select((bundle, index) =>
            {
                var cardModels = bundle.Bundle;
                if (cardModels == null || cardModels.Count == 0)
                {
                    return null;
                }
                return BuildSelectionCardPayload(cardModels[0], index);
            })
            .OfType<SelectionCardPayload>()
            .ToArray();

        // Preview cards: all CardModels from all bundles, in order
        var previewCards = bundles
            .SelectMany((bundle, bundleIndex) =>
                (bundle.Bundle ?? Array.Empty<CardModel>() as IReadOnlyList<CardModel>)
                    .Select((card, cardIndex) => BuildSelectionCardPayload(card, bundleIndex * 100 + cardIndex)))
            .ToArray();

        return new SelectionPayload
        {
            kind = "bundle_select",
            prompt = prompt,
            min_select = 1,
            max_select = 1,
            selected_count = 0,
            requires_confirmation = canConfirm,
            can_confirm = canConfirm,
            cards = cards,
            selectable_cards = cards,
            preview_cards = previewCards
        };
    }

    private static SelectionPayload? BuildSelectionPayload(IScreenContext? currentScreen)
    {
        // Bundle selection screen has a dedicated path — NCardBundle is not an NCardHolder.
        if (currentScreen is NChooseABundleSelectionScreen bundleSelectionScreen)
        {
            return BuildBundleSelectionPayload(bundleSelectionScreen);
        }

        var isCombatHandSelection = TryGetCombatHandSelectionMetadata(currentScreen, out var combatHand, out var metadata);
        var isGridSelection = currentScreen is NCardGridSelectionScreen;
        var isChooseCardSelection = currentScreen is NChooseACardSelectionScreen;
        var isEmbeddedGridSelection =
            !isGridSelection &&
            !isChooseCardSelection &&
            currentScreen is not NChooseABundleSelectionScreen &&
            currentScreen is not NCardsViewScreen &&
            currentScreen is Node embeddedNode &&
            GetVisibleGridCardHolders(embeddedNode).Count > 0;
        var isEventEmbeddedSelection = currentScreen is NEventRoom && isEmbeddedGridSelection;

        if (!isCombatHandSelection &&
            !isGridSelection &&
            !isChooseCardSelection &&
            !isEmbeddedGridSelection)
        {
            return null;
        }

        var cards = GetDeckSelectionOptions(currentScreen);
        var prompt = GetDeckSelectionPrompt(currentScreen) ?? string.Empty;

        // Try combat hand first, then fall back to deck selection metadata
        var selectionMetadata = isCombatHandSelection
            ? metadata
            : GetDeckSelectionMetadata(currentScreen, prompt);

        var isUpgradeScreen = currentScreen is NDeckUpgradeSelectScreen;
        var selectionCards = cards.Where(holder => holder.CardModel != null)
            .Select((holder, index) => BuildSelectionCardPayload(
                holder.CardModel!, index, includeUpgradePreview: isUpgradeScreen))
            .ToArray();
        SelectionCardPayload[] selectableCards = selectionCards;
        var selectedCards = Array.Empty<SelectionCardPayload>();

        if (isCombatHandSelection && combatHand != null)
        {
            var selectedStableIds = GetCombatHandSelectedCards(combatHand)
                .Select(BuildSelectionCardStableId)
                .Where(stableId => !string.IsNullOrWhiteSpace(stableId))
                .ToHashSet();

            selectionCards = cards.Where(holder => holder.CardModel != null)
                .Select((holder, index) =>
                {
                    var stableId = BuildSelectionCardStableId(holder.CardModel);
                    var isSelected = selectedStableIds.Contains(stableId);
                    return BuildSelectionCardPayload(
                        holder.CardModel!,
                        index,
                        stableId,
                        isSelected,
                        !isSelected);
                })
                .ToArray();
            selectableCards = selectionCards.Where(card => card.is_selectable).ToArray();
            selectedCards = selectionCards.Where(card => card.is_selected).ToArray();
        }
        else if (isGridSelection || isEmbeddedGridSelection)
        {
            selectedCards = GetGridSelectionSelectedCardHolders(currentScreen)
                .Where(holder => holder.CardModel != null)
                .Select((holder, index) => BuildSelectionCardPayload(
                    holder.CardModel!,
                    index,
                    stableId: null,
                    isSelected: true,
                    isSelectable: false))
                .ToArray();
            selectableCards = selectionCards;
        }
        else if (isChooseCardSelection || isEventEmbeddedSelection)
        {
            selectableCards = selectionCards;
        }

        if (selectionCards.Length == 0 &&
            selectableCards.Length == 0 &&
            selectedCards.Length == 0 &&
            !selectionMetadata.CanConfirm &&
            selectionMetadata.SelectedCount <= 0)
        {
            return null;
        }

        return new SelectionPayload
        {
            kind = currentScreen switch
            {
                NDeckUpgradeSelectScreen => "deck_upgrade_select",
                NDeckTransformSelectScreen => "deck_transform_select",
                NDeckEnchantSelectScreen => "deck_enchant_select",
                NChooseACardSelectionScreen => "choose_card_select",
                _ when isEventEmbeddedSelection => "choose_card_select",
                _ when isEmbeddedGridSelection => "deck_card_select",
                _ when TryGetCombatHandSelection(currentScreen, out var hand) => hand!.CurrentMode == NPlayerHand.Mode.UpgradeSelect
                    ? "combat_hand_upgrade_select"
                    : "combat_hand_select",
                _ => "deck_card_select"
            },
            prompt = prompt,
            min_select = selectionMetadata.MinSelect,
            max_select = selectionMetadata.MaxSelect,
            selected_count = selectionMetadata.SelectedCount,
            requires_confirmation = selectionMetadata.RequiresConfirmation,
            can_confirm = selectionMetadata.CanConfirm,
            cards = selectionCards,
            selected_cards = selectedCards,
            selectable_cards = selectableCards,
            preview_cards = currentScreen is NChooseACardSelectionScreen chooseCardScreen
                ? GetChooseCardPreviewCards(chooseCardScreen)
                : isEventEmbeddedSelection
                    ? GetEventEmbeddedPreviewCards(currentScreen, cards)
                    : Array.Empty<SelectionCardPayload>()
        };
    }

    private static CharacterSelectPayload? BuildCharacterSelectPayload(IScreenContext? currentScreen)
    {
        var screen = GetCharacterSelectScreen(currentScreen);
        if (screen == null)
        {
            return null;
        }

        var buttons = GetCharacterSelectButtons(currentScreen);
        try
        {
            var lobby = screen.Lobby;
            var localPlayer = lobby.LocalPlayer;
            var waitingPanel = screen.GetNodeOrNull<Control>("ReadyAndWaitingPanel");
            var selectedCharacterId = localPlayer.character?.Id.Entry;

            return new CharacterSelectPayload
            {
                selected_character_id = selectedCharacterId,
                is_multiplayer = lobby.NetService.Type.IsMultiplayer(),
                net_game_type = lobby.NetService.Type.ToString(),
                can_embark = CanEmbark(currentScreen),
                can_unready = CanUnready(currentScreen),
                can_increase_ascension = CanIncreaseAscension(currentScreen),
                can_decrease_ascension = CanDecreaseAscension(currentScreen),
                local_ready = localPlayer.isReady,
                is_waiting_for_players = waitingPanel?.Visible ?? false,
                player_count = lobby.Players.Count,
                max_players = lobby.MaxPlayers > 0 ? lobby.MaxPlayers : lobby.Players.Count,
                ascension = lobby.Ascension,
                max_ascension = lobby.MaxAscension,
                seed = lobby.Seed,
                modifier_ids = lobby.Modifiers.Select(modifier => modifier.Id.Entry).ToArray(),
                players = lobby.Players
                    .OrderBy(player => player.slotId)
                    .Select(player => BuildCharacterSelectPlayerPayload(player, localPlayer.id))
                    .ToArray(),
                characters = buttons.Select((button, index) => new CharacterSelectOptionPayload
                {
                    index = index,
                    character_id = button.Character.Id.Entry,
                    name = EnglishLocResolver.Resolve(button.Character.Title),
                    is_locked = button.IsLocked,
                    is_selected = button.IsRandom
                        ? selectedCharacterId == button.Character.Id.Entry
                        : selectedCharacterId == button.Character.Id.Entry,
                    is_random = button.IsRandom
                }).ToArray()
            };
        }
        catch
        {
            return new CharacterSelectPayload
            {
                players = Array.Empty<CharacterSelectPlayerPayload>(),
                characters = buttons.Select((button, index) => new CharacterSelectOptionPayload
                {
                    index = index,
                    character_id = button.Character.Id.Entry,
                    name = EnglishLocResolver.Resolve(button.Character.Title),
                    is_locked = button.IsLocked,
                    is_selected = false,
                    is_random = button.IsRandom
                }).ToArray()
            };
        }
    }

    private static EventPayload? BuildEventPayload(IScreenContext? currentScreen)
    {
        // Crystal Sphere is its own minigame: it gets a structured `crystal_sphere`
        // payload (BuildCrystalSpherePayload) and the event payload stays null so
        // Python derives state_type=crystal_sphere instead of the generic event flow.
        if (currentScreen is NCrystalSphereScreen)
        {
            return null;
        }

        if (!TryGetActiveEventModel(currentScreen, out var eventModel) || eventModel == null)
        {
            return null;
        }

        try
        {
            var eventId = SafeReadString(() => eventModel.Id?.Entry, "unknown");
            var options = new List<EventOptionPayload>();

            if (eventModel.IsFinished)
            {
                // Mirror NEventRoom.SetOptions(): synthesize a Proceed option
                options.Add(new EventOptionPayload
                {
                    index = 0,
                    text_key = "PROCEED",
                    title = "Proceed",
                    description = "",
                    is_locked = false,
                    is_proceed = true
                });
            }
            else
            {
                var currentOptions = eventModel.CurrentOptions;
                for (int i = 0; i < currentOptions.Count; i++)
                {
                    var opt = currentOptions[i];
                    // Bind the event's DynamicVars (e.g. {Curse}/{Relic}/{Enchantment}
                    // for Grave of the Forgotten) onto the option's LocStrings before
                    // resolving — this is what NEventOptionButton does when rendering
                    // option text in-game. Without this step the resolved description
                    // still ships the raw `{Token}` placeholders.
                    BindEventDynamicVars(eventModel, opt);
                    var optionTitle = EnglishLocResolver.Resolve(opt.Title);
                    var optionDescription = EnglishLocResolver.Resolve(opt.Description);
                    // Wrap dangerous reflection calls individually
                    bool willKill = false;
                    bool hasRelic = false;
                    string effectDescription = optionDescription;
                    int? hpCost = null;
                    int? goldCost = null;
                    EventCardInfo[] cardsOffered = Array.Empty<EventCardInfo>();
                    EventRelicInfo[] relicsOffered = Array.Empty<EventRelicInfo>();
                    EventPotionInfo[] potionsOffered = Array.Empty<EventPotionInfo>();
                    string[] cursesRisk = Array.Empty<string>();

                    TryLogEventOptionReflection(opt, eventId, i, optionTitle);
                    try { willKill = GetEventOptionWillKillPlayer(eventModel, opt); } catch { /* ignore */ }
                    try { hasRelic = GetReflectedProperty(opt, "Relic") != null; } catch { /* ignore */ }
                    try
                    {
                        effectDescription = SafeReadString(
                            () => GetDynamicFormattedTextProperty(opt, "DynamicDescription", "Description", "EffectDescription"),
                            optionDescription);
                    }
                    catch { /* ignore */ }
                    effectDescription = NormalizeEventStructuredText(effectDescription);
                    try { hpCost = GetFirstNullableIntProperty(opt, EventHpCostCandidates); } catch { /* ignore */ }
                    try { goldCost = GetFirstNullableIntProperty(opt, EventGoldCostCandidates); } catch { /* ignore */ }
                    try { cardsOffered = ExtractEventCardInfos(opt, effectDescription); } catch { /* ignore */ }
                    try { relicsOffered = ExtractEventRelicInfos(opt, effectDescription); } catch { /* ignore */ }
                    try { potionsOffered = ExtractEventPotionInfos(opt, effectDescription); } catch { /* ignore */ }
                    try { cursesRisk = ExtractEventCurseRisks(opt, effectDescription); } catch { /* ignore */ }

                    hpCost ??= TryParseEventCost(effectDescription, EventHpCostRegex);
                    goldCost ??= TryParseEventCost(effectDescription, EventGoldCostRegex);
                    hasRelic = hasRelic || relicsOffered.Length > 0;

                    options.Add(new EventOptionPayload
                    {
                        index = i,
                        text_key = SafeReadString(() => opt.TextKey),
                        title = optionTitle,
                        description = optionDescription,
                        is_locked = SafeReadBool(() => opt.IsLocked),
                        is_proceed = SafeReadBool(() => opt.IsProceed),
                        will_kill_player = willKill,
                        has_relic_preview = hasRelic,
                        effect_description = effectDescription,
                        hp_cost = hpCost,
                        gold_cost = goldCost,
                        cards_offered = cardsOffered,
                        relics_offered = relicsOffered,
                        potions_offered = potionsOffered,
                        curses_risk = cursesRisk
                    });
                }
            }

            return new EventPayload
            {
                event_id = eventId,
                title = EnglishLocResolver.Resolve(eventModel.Title),
                description = EnglishLocResolver.Resolve(eventModel.Description),
                is_finished = SafeReadBool(() => eventModel.IsFinished),
                options = options.ToArray()
            };
        }
        catch (Exception ex)
        {
            var screenType = currentScreen?.GetType().FullName ?? "<null>";
            Log.Warn($"[STS2AIAgent] Failed to build event payload on screen {screenType}: {ex}");
            // Return minimal payload so agent knows it's an event (not null)
            try
            {
                var fallbackEventModel = RunManager.Instance.EventSynchronizer.GetLocalEvent();
                return new EventPayload
                {
                    event_id = fallbackEventModel != null ? SafeReadString(() => fallbackEventModel.Id?.Entry, "unknown") : "unknown",
                    title = fallbackEventModel != null ? EnglishLocResolver.Resolve(fallbackEventModel.Title) : "Unknown Event",
                    description = $"Event payload build failed: {ex.Message}",
                    is_finished = false,
                    options = Array.Empty<EventOptionPayload>()
                };
            }
            catch
            {
                return new EventPayload
                {
                    event_id = "unknown",
                    title = "Unknown Event",
                    description = $"Event payload build failed: {ex.Message}",
                    is_finished = false,
                    options = Array.Empty<EventOptionPayload>()
                };
            }
        }
    }

    private static EventPayload? BuildCrystalSphereEventPayload(NCrystalSphereScreen crystalSphereScreen)
    {
        try
        {
            var minigame = GetCrystalSphereMinigame(crystalSphereScreen);
            if (minigame == null)
            {
                return null;
            }

            var eventModel = RunManager.Instance.EventSynchronizer.GetLocalEvent();
            var options = GetCrystalSphereOptions(crystalSphereScreen)
                .Select(option => new EventOptionPayload
                {
                    index = option.index,
                    text_key = option.text_key,
                    title = option.title,
                    description = option.description,
                    is_locked = false,
                    is_proceed = option.is_proceed
                })
                .ToArray();

            var title = NormalizeCardRulesText(EnglishLocResolver.Resolve(eventModel?.Title));
            if (string.IsNullOrWhiteSpace(title))
            {
                title = NormalizeCardRulesText(SafeReadString(() =>
                    (TryGetMemberValue(crystalSphereScreen, "_instructionsTitleLabel") as MegaRichTextLabel)?.Text));
            }

            if (string.IsNullOrWhiteSpace(title))
            {
                title = "Crystal Sphere";
            }

            var descriptionSegments = new List<string>();

            var eventDescription = NormalizeCardRulesText(EnglishLocResolver.Resolve(eventModel?.Description));
            if (!string.IsNullOrWhiteSpace(eventDescription))
            {
                descriptionSegments.Add(eventDescription);
            }

            var instructionText = NormalizeCardRulesText(SafeReadString(() =>
                (TryGetMemberValue(crystalSphereScreen, "_instructionsDescriptionLabel") as MegaRichTextLabel)?.Text));
            if (!string.IsNullOrWhiteSpace(instructionText) &&
                !string.Equals(instructionText, eventDescription, StringComparison.Ordinal))
            {
                descriptionSegments.Add(instructionText);
            }

            descriptionSegments.Add(
                $"Divinations left: {Math.Max(0, minigame.DivinationCount)}. Active tool: {DescribeCrystalSphereTool(minigame.CrystalSphereTool)}.");

            if (minigame.CrystalSphereTool == CrystalSphereMinigame.CrystalSphereToolType.None)
            {
                descriptionSegments.Add("Select a divination tool before revealing a cell.");
            }
            else
            {
                var hiddenCellCount = FindDescendants<NCrystalSphereCell>(crystalSphereScreen)
                    .Count(cell => IsClickableControlUsable(cell) && cell.Entity != null && cell.Entity.IsHidden);
                descriptionSegments.Add($"Clickable hidden cells: {hiddenCellCount}.");
            }

            if (GetProceedButton(crystalSphereScreen) != null)
            {
                descriptionSegments.Add("Proceed is available.");
            }

            return new EventPayload
            {
                event_id = SafeReadString(() => eventModel?.Id?.Entry, "CRYSTAL_SPHERE"),
                title = title,
                description = string.Join(" ", descriptionSegments.Where(segment => !string.IsNullOrWhiteSpace(segment))),
                is_finished = minigame.IsFinished || GetProceedButton(crystalSphereScreen) != null,
                options = options
            };
        }
        catch (Exception ex)
        {
            Log.Warn($"[STS2AIAgent] Failed to build Crystal Sphere payload: {ex}");
            return new EventPayload
            {
                event_id = "CRYSTAL_SPHERE",
                title = "Crystal Sphere",
                description = $"Crystal Sphere payload build failed: {ex.Message}",
                is_finished = false,
                options = Array.Empty<EventOptionPayload>()
            };
        }
    }

    private static RestPayload? BuildRestPayload(IScreenContext? currentScreen)
    {
        if (currentScreen is not NRestSiteRoom)
        {
            return null;
        }

        try
        {
            var options = RunManager.Instance.RestSiteSynchronizer.GetLocalOptions();
            if (options == null)
            {
                return new RestPayload
                {
                    options = Array.Empty<RestOptionPayload>()
                };
            }

            return new RestPayload
            {
                options = options.Select((opt, i) => new RestOptionPayload
                {
                    index = i,
                    option_id = opt.OptionId ?? "unknown",
                    title = EnglishLocResolver.Resolve(opt.Title),
                    description = EnglishLocResolver.Resolve(opt.Description),
                    is_enabled = opt.IsEnabled
                }).ToArray()
            };
        }
        catch
        {
            return null;
        }
    }

    private static ShopPayload? BuildShopPayload(IScreenContext? currentScreen)
    {
        if (TryGetActiveEventModel(currentScreen, out _))
        {
            return null;
        }

        var merchantRoom = GetMerchantRoom(currentScreen);
        var inventoryScreen = GetMerchantInventoryScreen(currentScreen);
        var inventory = inventoryScreen?.Inventory ?? merchantRoom?.Inventory?.Inventory;

        if (merchantRoom == null && inventoryScreen == null)
        {
            return null;
        }

        if (inventory == null)
        {
            return new ShopPayload
            {
                is_open = inventoryScreen?.IsOpen ?? false,
                can_open = CanOpenShopInventory(currentScreen),
                can_close = CanCloseShopInventory(currentScreen),
                cards = Array.Empty<ShopCardPayload>(),
                relics = Array.Empty<ShopRelicPayload>(),
                potions = Array.Empty<ShopPotionPayload>(),
                card_removal = null
            };
        }

        var cards = inventory.CharacterCardEntries
            .Select((entry, index) => BuildShopCardPayload(entry, index, "character"))
            .Concat(inventory.ColorlessCardEntries.Select((entry, index) =>
                BuildShopCardPayload(entry, inventory.CharacterCardEntries.Count + index, "colorless")))
            .ToArray();

        return new ShopPayload
        {
            is_open = inventoryScreen?.IsOpen ?? false,
            can_open = CanOpenShopInventory(currentScreen),
            can_close = CanCloseShopInventory(currentScreen),
            cards = cards,
            relics = inventory.RelicEntries.Select((entry, index) => BuildShopRelicPayload(entry, index)).ToArray(),
            potions = inventory.PotionEntries.Select((entry, index) => BuildShopPotionPayload(entry, index, inventory.Player)).ToArray(),
            card_removal = BuildShopCardRemovalPayload(inventory.CardRemovalEntry)
        };
    }

    private static TimelinePayload? BuildTimelinePayload(IScreenContext? currentScreen)
    {
        var timelineScreen = GetTimelineScreen(currentScreen);
        if (timelineScreen == null)
        {
            return null;
        }

        var slots = GetTimelineSlots(currentScreen)
            .Select((slot, index) => new TimelineSlotPayload
            {
                index = index,
                epoch_id = slot.model.Id,
                title = EnglishLocResolver.Resolve(slot.model.Title) is { Length: > 0 } resolvedTitle
                    ? resolvedTitle
                    : slot.model.Id,
                state = slot.State.ToString().ToLowerInvariant(),
                is_actionable = slot.State is EpochSlotState.Obtained or EpochSlotState.Complete
            })
            .ToArray();

        return new TimelinePayload
        {
            back_enabled = GetTimelineBackButton(currentScreen)?.IsEnabled == true,
            inspect_open = GetTimelineInspectScreen(currentScreen)?.Visible == true,
            unlock_screen_open = GetTimelineUnlockScreen(currentScreen) != null,
            can_choose_epoch = CanChooseTimelineEpoch(currentScreen),
            can_confirm_overlay = CanConfirmTimelineOverlay(currentScreen),
            slots = slots
        };
    }

    private static ChestPayload? BuildChestPayload(IScreenContext? currentScreen)
    {
        var relicCollection = GetTreasureRelicCollection(currentScreen);
        if (relicCollection != null)
        {
            var relics = RunManager.Instance.TreasureRoomRelicSynchronizer.CurrentRelics;
            var hasRelicBeenClaimed = GetProceedButton(currentScreen) != null;
            return new ChestPayload
            {
                is_opened = true,
                has_relic_been_claimed = hasRelicBeenClaimed,
                relic_options = BuildTreasureRelicOptions(relics)
            };
        }

        if (currentScreen is NTreasureRoom treasureRoom)
        {
            var chestButton = treasureRoom.GetNodeOrNull<NButton>("%Chest");
            var isOpened = chestButton == null || !GodotObject.IsInstanceValid(chestButton) || !chestButton.IsEnabled;
            var hasRelicBeenClaimed = GetProceedButton(currentScreen) != null;

            return new ChestPayload
            {
                is_opened = isOpened,
                has_relic_been_claimed = hasRelicBeenClaimed,
                relic_options = Array.Empty<ChestRelicOptionPayload>()
            };
        }

        return null;
    }

    private static ChestRelicOptionPayload[] BuildTreasureRelicOptions(IReadOnlyList<RelicModel>? relics)
    {
        if (relics == null || relics.Count == 0)
        {
            return Array.Empty<ChestRelicOptionPayload>();
        }

        return relics.Select((relic, index) => new ChestRelicOptionPayload
        {
            index = index,
            relic_id = relic.Id.Entry,
            name = EnglishLocResolver.Resolve(relic.Title),
            rarity = relic.Rarity.ToString()
        }).ToArray();
    }

    private static RewardPayload? BuildRewardPayload(IScreenContext? currentScreen)
    {
        if (currentScreen is NRewardsScreen)
        {
            var rewardButtons = GetRewardButtons(currentScreen);
            var proceedButton = GetRewardProceedButton(currentScreen);

            return new RewardPayload
            {
                pending_card_choice = false,
                can_proceed = proceedButton?.IsEnabled ?? false,
                rewards = rewardButtons.Select((button, index) => BuildRewardOptionPayload(button, index)).ToArray(),
                card_options = Array.Empty<RewardCardOptionPayload>()
            };
        }

        if (currentScreen is NCardRewardSelectionScreen cardRewardSelection)
        {
            var cardOptions = GetCardRewardOptions(currentScreen);
            var alternatives = GetCardRewardAlternativeButtons(currentScreen);

            // Include unclaimed reward items from the parent NRewardsScreen so the agent
            // can detect full-slot potion rewards and decide whether to discard a held potion.
            var parentRewards = FindAncestorRewardsScreen(cardRewardSelection);
            var rewardButtons = parentRewards != null
                ? GetRewardButtons(parentRewards)
                : Array.Empty<NRewardButton>();

            return new RewardPayload
            {
                pending_card_choice = true,
                can_proceed = false,
                rewards = rewardButtons.Select((button, index) => BuildRewardOptionPayload(button, index)).ToArray(),
                card_options = cardOptions.Select((holder, index) => BuildRewardCardOptionPayload(holder, index)).ToArray(),
                alternatives = alternatives.Select((button, index) => BuildRewardAlternativePayload(button, index)).ToArray()
            };
        }

        return null;
    }

    private static ModalPayload? BuildModalPayload(IScreenContext? currentScreen)
    {
        var modal = GetOpenModal();
        if (modal is not Node modalNode)
        {
            return null;
        }

        var confirmButton = GetModalConfirmButton(currentScreen);
        var cancelButton = GetModalCancelButton(currentScreen);

        return new ModalPayload
        {
            type_name = modal.GetType().Name,
            underlying_screen = currentScreen is Node node && ReferenceEquals(node, modalNode)
                ? ResolveUnderlyingScreen(modalNode)
                : null,
            can_confirm = confirmButton != null,
            can_dismiss = cancelButton != null,
            confirm_label = GetButtonLabel(confirmButton),
            dismiss_label = GetButtonLabel(cancelButton)
        };
    }

    private static GameOverPayload? BuildGameOverPayload(IScreenContext? currentScreen, RunState? runState)
    {
        if (currentScreen is not NGameOverScreen screen)
        {
            return null;
        }

        var player = LocalContext.GetMe(runState);
        var continueButton = screen.GetNodeOrNull<NButton>("%ContinueButton");
        var mainMenuButton = screen.GetNodeOrNull<NButton>("%MainMenuButton");
        var history = RunManager.Instance.History;

        return new GameOverPayload
        {
            is_victory = history?.Win ?? (runState?.CurrentRoom?.IsVictoryRoom ?? false),
            floor = runState?.TotalFloor,
            character_id = player?.Character.Id.Entry,
            can_continue = continueButton?.IsEnabled ?? false,
            can_return_to_main_menu = true,
            showing_summary = mainMenuButton?.Visible == true || mainMenuButton?.IsEnabled == true
        };
    }

    // Walk a card's hover tips and extract the CardModel instances that
    // represent cards this card generates (e.g. BladeOfInk -> Shiv,
    // HiddenDaggers -> Shiv, GraveWarden -> Soul). Mirrors the game UI's own
    // hover-preview source: CardModel.ExtraHoverTips includes
    // HoverTipFactory.FromCard<T>() entries that get wrapped in CardHoverTip.
    private static GeneratedCardPayload[] ExtractGeneratedCards(CardModel? card)
    {
        if (card == null)
        {
            return Array.Empty<GeneratedCardPayload>();
        }

        IEnumerable<IHoverTip> tips;
        try
        {
            tips = card.HoverTips;
        }
        catch
        {
            return Array.Empty<GeneratedCardPayload>();
        }

        var result = new List<GeneratedCardPayload>();
        var seenIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var tip in tips)
        {
            if (tip is not CardHoverTip cardTip || cardTip.Card == null)
            {
                continue;
            }
            var generated = cardTip.Card;
            if (ReferenceEquals(generated, card))
            {
                continue;
            }
            var idEntry = generated.Id.Entry ?? string.Empty;
            // De-dup by (id, upgraded) so cards that preview the same generated
            // type twice don't bloat the payload. Use a composite key.
            var key = idEntry + "|" + (generated.IsUpgraded ? "1" : "0");
            if (!seenIds.Add(key))
            {
                continue;
            }

            string[] keywords;
            try
            {
                keywords = generated.Keywords?.Select(k => k.ToString()).ToArray()
                    ?? Array.Empty<string>();
            }
            catch
            {
                keywords = Array.Empty<string>();
            }

            int energyCost;
            try { energyCost = generated.EnergyCost.GetWithModifiers(CostModifiers.All); }
            catch { energyCost = 0; }

            result.Add(new GeneratedCardPayload
            {
                card_id = idEntry,
                name = EnglishLocResolver.ResolveCardTitle(generated),
                upgraded = generated.IsUpgraded,
                card_type = generated.Type.ToString(),
                energy_cost = energyCost,
                rules_text = GetCardRulesText(generated),
                keywords = keywords
            });
        }
        return result.ToArray();
    }

    private static CombatHandCardPayload BuildHandCardPayload(CombatState combatState, CardModel card, int index)
    {
        card.CanPlay(out var reason, out _);
        var targetSupported = IsCardTargetSupported(card);
        var targetIndexSpace = GetCardTargetIndexSpace(card);
        var validTargetIndices = GetCardTargetIndices(combatState, card);
        var resolvedRulesText = GetResolvedCardRulesText(card);
        var dynamicValues = BuildCardDynamicValuePayloads(card);

        var rulesText = GetCardRulesText(card);

        // Card-level structured preview values (untargeted, player-side modifiers only)
        // Hit count priority: Hits/CalculatedHits (authoritative) > Repeat (for attack cards
        // with DamageVar — safe because all non-attack RepeatVar cards lack DamageVar) > 1
        int? cardDamage = TryGetDynamicInt(card, "Damage", "CalculatedDamage");
        int? cardBlock = TryGetDynamicInt(card, "Block", "CalculatedBlock");
        int? cardHits = TryGetDynamicInt(card, "Hits", "CalculatedHits")
                        ?? (cardDamage != null
                            ? (TryGetDynamicInt(card, "Repeat") ?? 1)
                            : (int?)null);
        int? cardTotalDamage = (cardDamage != null && cardHits != null)
            ? cardDamage * cardHits : (int?)null;

        // Replay: number of additional times the card auto-plays (e.g. Glam enchantment)
        int? cardReplay = TryGetDynamicInt(card, "Replay");

        return new CombatHandCardPayload
        {
            index = index,
            card_id = card.Id.Entry,
            name = EnglishLocResolver.ResolveCardTitle(card),
            upgraded = card.IsUpgraded,
            card_type = card.Type.ToString(),
            target_type = card.TargetType.ToString(),
            requires_target = CardRequiresTarget(card),
            target_index_space = targetIndexSpace,
            valid_target_indices = validTargetIndices,
            costs_x = card.EnergyCost.CostsX,
            star_costs_x = card.HasStarCostX,
            energy_cost = card.EnergyCost.GetWithModifiers(CostModifiers.All),
            star_cost = Math.Max(0, card.GetStarCostWithModifiers()),
            rules_text = rulesText,
            resolved_rules_text = resolvedRulesText,
            dynamic_values = dynamicValues,
            playable = targetSupported && reason == UnplayableReason.None,
            unplayable_reason = targetSupported
                ? GetUnplayableReasonCode(reason)
                : "unsupported_target_type",
            damage = cardDamage,
            block = cardBlock,
            hits = cardHits,
            total_damage = cardTotalDamage,
            replay = cardReplay,
            target_previews = GetTargetPreviews(combatState, card),
            generated_cards = ExtractGeneratedCards(card)
        };
    }

    private static int? TryGetDynamicInt(CardModel card, params string[] keys)
    {
        foreach (var key in keys)
        {
            if (card.DynamicVars.ContainsKey(key))
            {
                try { return card.DynamicVars[key].IntValue; }
                catch { /* skip unreadable var */ }
            }
        }
        return null;
    }

    private static TargetPreviewPayload[]? GetTargetPreviews(
        CombatState combatState, CardModel card)
    {
        if (!CardRequiresTarget(card))
            return null;

        var targetIndexSpace = GetCardTargetIndexSpace(card);
        var indices = GetCardTargetIndices(combatState, card);
        if (indices.Length == 0)
            return null;

        // Resolve damage key: Strike uses Damage, Body Slam / Ashen Strike use CalculatedDamage
        string? damageKey = card.DynamicVars.ContainsKey("Damage") ? "Damage"
            : card.DynamicVars.ContainsKey("CalculatedDamage") ? "CalculatedDamage"
            : null;
        if (damageKey == null)
            return null;

        var baseDamage = card.DynamicVars[damageKey].IntValue;
        var baseHits = TryGetDynamicInt(card, "Hits", "CalculatedHits")
                       ?? TryGetDynamicInt(card, "Repeat")
                       ?? 1;
        var baseTotalDamage = baseDamage * baseHits;
        var previews = new List<TargetPreviewPayload>();

        foreach (var idx in indices)
        {
            try
            {
                Creature? creature = targetIndexSpace switch
                {
                    "enemies" => ResolveEnemyTarget(combatState, idx),
                    "players" => ResolvePlayerTarget(combatState, idx),
                    _ => null
                };
                if (creature == null) continue;
                if (!card.CanPlayTargeting(creature)) continue;

                var dvs = card.DynamicVars.Clone(card);
                dvs.ClearPreview();
                card.UpdateDynamicVarPreview(CardPreviewMode.Normal, creature, dvs);

                var previewDamage = (int)dvs[damageKey].PreviewValue;

                // Extract preview hits from cloned DynamicVars
                // Priority: Hits/CalculatedHits (authoritative) > Repeat (attack cards)
                int previewHits = baseHits;
                foreach (var hitsKey in new[] { "Hits", "CalculatedHits", "Repeat" })
                {
                    if (dvs.ContainsKey(hitsKey))
                    {
                        try { previewHits = (int)dvs[hitsKey].PreviewValue; break; }
                        catch { /* fall through to next key */ }
                    }
                }
                var previewTotalDamage = previewDamage * previewHits;

                // Emit when ANY of damage/hits/total differs from base
                if (previewDamage != baseDamage || previewHits != baseHits || previewTotalDamage != baseTotalDamage)
                {
                    previews.Add(new TargetPreviewPayload
                    {
                        target_index = idx,
                        damage = previewDamage,
                        hits = previewHits,
                        total_damage = previewTotalDamage
                    });
                }
            }
            catch
            {
                // One target's failure doesn't break the rest
            }
        }

        return previews.Count > 0 ? previews.ToArray() : null;
    }


    private static CombatEnemyPayload BuildEnemyPayload(Creature enemy, int index)
    {
        var moveId = enemy.Monster?.NextMove?.Id;
        var intents = BuildEnemyIntentPayloads(enemy);

        return new CombatEnemyPayload
        {
            index = index,
            enemy_id = enemy.ModelId.Entry,
            name = EnglishLocResolver.Resolve(enemy.Monster?.Title) is { Length: > 0 } resolved
                ? resolved
                : enemy.Name,
            current_hp = enemy.CurrentHp,
            max_hp = enemy.MaxHp,
            block = enemy.Block,
            is_alive = enemy.IsAlive,
            is_hittable = enemy.IsHittable,
            powers = BuildCreaturePowerPayloads(enemy),
            intent = moveId,
            move_id = moveId,
            intents = intents
        };
    }

    private static CombatPowerPayload[] BuildCreaturePowerPayloads(Creature creature)
    {
        var powersValue = creature.GetType().GetProperty("Powers")?.GetValue(creature);
        if (powersValue is not System.Collections.IEnumerable powersEnumerable)
        {
            return Array.Empty<CombatPowerPayload>();
        }

        var result = new List<CombatPowerPayload>();
        var index = 0;

        foreach (var power in powersEnumerable)
        {
            if (power == null)
            {
                continue;
            }

            var powerType = power.GetType();
            var idEntry = SafeReadString(() =>
            {
                var idValue = powerType.GetProperty("Id")?.GetValue(power);
                if (idValue == null)
                {
                    return string.Empty;
                }

                return idValue.GetType().GetProperty("Entry")?.GetValue(idValue)?.ToString();
            });

            var title = SafeReadString(() =>
            {
                var titleValue = powerType.GetProperty("Title")?.GetValue(power);
                if (titleValue == null)
                {
                    return string.Empty;
                }

                // Resolve power title through English LocManager tables so the
                // agent gets English regardless of the player's active locale.
                return EnglishLocResolver.WithEnglishTables(() =>
                    titleValue.GetType().GetMethod("GetFormattedText")?.Invoke(titleValue, null)?.ToString());
            });

            var amount = GetReflectedNullableIntProperty(power, "Amount");
            var description = GetResolvedPowerDescription(power);

            var isDebuff = string.Equals(
                GetReflectedProperty(power, "TypeForCurrentAmount")?.ToString()
                    ?? GetReflectedProperty(power, "Type")?.ToString(),
                "Debuff",
                StringComparison.Ordinal);

            result.Add(new CombatPowerPayload
            {
                index = index,
                power_id = string.IsNullOrWhiteSpace(idEntry) ? "unknown_power" : idEntry,
                name = string.IsNullOrWhiteSpace(title) ? idEntry : title,
                amount = amount,
                description = description,
                is_debuff = isDebuff
            });
            index += 1;
        }

        return result.ToArray();
    }

    private static string GetResolvedPowerDescription(object power)
    {
        if (power == null)
        {
            return string.Empty;
        }

        var description = GetDynamicFormattedTextProperty(
            power,
            "DynamicDescription",
            "Description",
            "RulesText",
            "Body",
            "Text");
        return string.IsNullOrWhiteSpace(description)
            ? string.Empty
            : NormalizeCardRulesText(description);
    }

    private static CombatEnemyIntentPayload[] BuildEnemyIntentPayloads(Creature enemy)
    {
        var nextMove = enemy.Monster?.NextMove;
        if (nextMove == null)
        {
            return Array.Empty<CombatEnemyIntentPayload>();
        }

        var targets = enemy.CombatState?.Players
            .Select(player => player.Creature)
            .ToArray() ?? Array.Empty<Creature>();

        return nextMove.Intents
            .Select((intent, index) => BuildEnemyIntentPayload(intent, enemy, targets, index))
            .ToArray();
    }

    private static CombatEnemyIntentPayload BuildEnemyIntentPayload(
        AbstractIntent intent,
        Creature owner,
        Creature[] targets,
        int index)
    {
        int? damage = null;
        int? hits = null;
        int? totalDamage = null;
        int? statusCardCount = null;

        if (intent is AttackIntent attackIntent)
        {
            damage = SafeReadNullableInt(() => attackIntent.GetSingleDamage(targets, owner));
            hits = SafeReadNullableInt(() => Math.Max(1, attackIntent.Repeats));
            totalDamage = SafeReadNullableInt(() => attackIntent.GetTotalDamage(targets, owner));
        }

        if (intent is StatusIntent statusIntent)
        {
            statusCardCount = SafeReadNullableInt(() => statusIntent.CardCount);
        }

        var label = EnglishLocResolver.Resolve(intent.GetIntentLabel(targets, owner));

        return new CombatEnemyIntentPayload
        {
            index = index,
            intent_type = intent.IntentType.ToString(),
            label = string.IsNullOrWhiteSpace(label) ? null : label,
            damage = damage,
            hits = hits,
            total_damage = totalDamage,
            status_card_count = statusCardCount
        };
    }

    private static int? SafeReadNullableInt(Func<int> getter)
    {
        try
        {
            return getter();
        }
        catch
        {
            return null;
        }
    }

    private static CombatOrbPayload BuildCombatOrbPayload(OrbModel orb, int slotIndex)
    {
        return new CombatOrbPayload
        {
            slot_index = slotIndex,
            orb_id = orb.Id.Entry,
            name = EnglishLocResolver.Resolve(orb.Title),
            passive_value = orb.PassiveVal,
            evoke_value = orb.EvokeVal,
            is_front = slotIndex == 0
        };
    }

    private static MapNodePayload BuildMapNodePayload(NMapPoint node, int index)
    {
        return new MapNodePayload
        {
            index = index,
            row = node.Point.coord.row,
            col = node.Point.coord.col,
            node_type = node.Point.PointType.ToString(),
            state = node.State.ToString()
        };
    }

    private static MapGraphNodePayload BuildMapGraphNodePayload(
        MapPoint point,
        NMapPoint? mapNode,
        HashSet<MapCoord> visitedCoords,
        HashSet<MapCoord> availableCoords,
        MapCoord? currentCoord,
        MapCoord startCoord,
        MapCoord bossCoord,
        MapCoord? secondBossCoord)
    {
        return new MapGraphNodePayload
        {
            row = point.coord.row,
            col = point.coord.col,
            node_type = point.PointType.ToString(),
            state = ResolveMapPointState(point.coord, mapNode, visitedCoords, availableCoords, currentCoord),
            visited = visitedCoords.Contains(point.coord),
            is_current = currentCoord.HasValue && currentCoord.Value == point.coord,
            is_available = availableCoords.Contains(point.coord),
            is_start = point.coord == startCoord,
            is_boss = point.coord == bossCoord,
            is_second_boss = secondBossCoord.HasValue && point.coord == secondBossCoord.Value,
            parents = point.parents
                .OrderBy(parent => parent.coord.row)
                .ThenBy(parent => parent.coord.col)
                .Select(parent => BuildMapCoordPayload(parent.coord)!)
                .ToArray(),
            children = point.Children
                .OrderBy(child => child.coord.row)
                .ThenBy(child => child.coord.col)
                .Select(child => BuildMapCoordPayload(child.coord)!)
                .ToArray()
        };
    }

    private static MapCoordPayload? BuildMapCoordPayload(MapCoord? coord)
    {
        if (!coord.HasValue)
        {
            return null;
        }

        return new MapCoordPayload
        {
            row = coord.Value.row,
            col = coord.Value.col
        };
    }

    private static IReadOnlyList<MapPoint> GetAllMapPoints(ActMap map)
    {
        var points = new Dictionary<MapCoord, MapPoint>();

        void AddPoint(MapPoint? point)
        {
            if (point == null)
            {
                return;
            }

            points[point.coord] = point;
        }

        foreach (var point in map.GetAllMapPoints())
        {
            AddPoint(point);
        }

        AddPoint(map.StartingMapPoint);
        AddPoint(map.BossMapPoint);
        AddPoint(map.SecondBossMapPoint);

        return points.Values
            .OrderBy(point => point.coord.row)
            .ThenBy(point => point.coord.col)
            .ToArray();
    }

    private static string ResolveMapPointState(
        MapCoord coord,
        NMapPoint? mapNode,
        HashSet<MapCoord> visitedCoords,
        HashSet<MapCoord> availableCoords,
        MapCoord? currentCoord)
    {
        if (mapNode != null)
        {
            return mapNode.State.ToString();
        }

        if (availableCoords.Contains(coord))
        {
            return MapPointState.Travelable.ToString();
        }

        if (visitedCoords.Contains(coord) || (currentCoord.HasValue && currentCoord.Value == coord))
        {
            return MapPointState.Traveled.ToString();
        }

        return MapPointState.Untravelable.ToString();
    }

    private static RewardOptionPayload BuildRewardOptionPayload(NRewardButton button, int index)
    {
        var reward = button.Reward;

        return new RewardOptionPayload
        {
            index = index,
            reward_type = GetRewardTypeName(reward),
            description = EnglishLocResolver.Resolve(reward?.Description),
            claimable = button.IsEnabled
        };
    }

    private static RewardCardOptionPayload BuildRewardCardOptionPayload(NCardHolder holder, int index)
    {
        var card = holder.CardModel;
        var resolvedRulesText = GetResolvedCardRulesText(card);
        var dynamicValues = BuildCardDynamicValuePayloads(card);

        return new RewardCardOptionPayload
        {
            index = index,
            card_id = card?.Id.Entry ?? string.Empty,
            name = EnglishLocResolver.ResolveCardTitle(card),
            upgraded = card?.IsUpgraded ?? false,
            card_type = card?.Type.ToString() ?? string.Empty,
            rarity = card?.Rarity.ToString() ?? string.Empty,
            energy_cost = card?.EnergyCost.GetWithModifiers(CostModifiers.All) ?? 0,
            costs_x = card?.EnergyCost.CostsX ?? false,
            rules_text = GetCardRulesText(card),
            resolved_rules_text = resolvedRulesText,
            dynamic_values = dynamicValues,
            generated_cards = ExtractGeneratedCards(card)
        };
    }

    private static RewardAlternativePayload BuildRewardAlternativePayload(NCardRewardAlternativeButton button, int index)
    {
        return new RewardAlternativePayload
        {
            index = index,
            label = GetRewardAlternativeLabel(button)
        };
    }

    private static RunRelicPayload BuildRunRelicPayload(RelicModel relic, int index)
    {
        return new RunRelicPayload
        {
            index = index,
            relic_id = relic.Id.Entry,
            name = EnglishLocResolver.Resolve(relic.Title),
            description = GetDynamicFormattedTextProperty(relic, "DynamicDescription", "Description"),
            stack = GetReflectedNullableIntProperty(relic, "Amount"),
            is_melted = relic.IsMelted,
            counter = relic.ShowCounter ? (int?)relic.DisplayAmount : null
        };
    }

    private static RunPotionPayload BuildRunPotionPayload(
        IScreenContext? currentScreen,
        CombatState? combatState,
        Player player,
        PotionModel? potion,
        int index)
    {
        var requiresTarget = potion != null && PotionRequiresTarget(combatState, potion);
        var targetIndexSpace = potion != null ? GetPotionTargetIndexSpace(combatState, potion) : null;
        var validTargetIndices = potion != null ? GetPotionTargetIndices(combatState, potion) : Array.Empty<int>();

        return new RunPotionPayload
        {
            index = index,
            potion_id = potion?.Id.Entry,
            name = EnglishLocResolver.Resolve(potion?.Title),
            description = potion != null ? NormalizeCardRulesText(GetDynamicFormattedTextProperty(potion, "DynamicDescription", "Description") ?? string.Empty) : null,
            rarity = potion != null ? GetReflectedStringProperty(potion, "Rarity") : null,
            occupied = potion != null,
            usage = potion?.Usage.ToString(),
            target_type = potion?.TargetType.ToString(),
            is_queued = potion?.IsQueued ?? false,
            requires_target = requiresTarget,
            target_index_space = targetIndexSpace,
            valid_target_indices = validTargetIndices,
            can_use = IsPotionUsable(currentScreen, combatState, player, potion),
            can_discard = CanDiscardPotionsInCurrentScreen(currentScreen) && IsPotionDiscardable(player, potion)
        };
    }

    private static bool IsEventReflectionDebugEnabled()
    {
        var raw = System.Environment.GetEnvironmentVariable("STS2_EVENT_REFLECTION_DEBUG");
        return !string.IsNullOrWhiteSpace(raw)
            && (raw == "1" || raw.Equals("true", StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>
    /// Binds the event's DynamicVars onto the option's Title/Description LocStrings
    /// so subsequent GetFormattedText() calls resolve `{Curse}`/`{Relic}`/`{Enchantment}`
    /// placeholders. Mirrors what NEventOptionButton does on focus.
    /// All access goes through reflection so we silently no-op if the game's
    /// EventModel/LocString shape changes in a future patch.
    /// </summary>
    private static void BindEventDynamicVars(object eventModel, object option)
    {
        try
        {
            var dynamicVars = GetReflectedProperty(eventModel, "DynamicVars");
            if (dynamicVars == null)
            {
                return;
            }

            var addToMethod = dynamicVars.GetType().GetMethod(
                "AddTo",
                BindingFlags.Instance | BindingFlags.Public);
            if (addToMethod == null)
            {
                return;
            }

            foreach (var memberName in new[] { "Title", "Description" })
            {
                var locString = GetReflectedProperty(option, memberName);
                if (locString == null)
                {
                    continue;
                }

                try
                {
                    addToMethod.Invoke(dynamicVars, new[] { locString });
                }
                catch
                {
                    // Non-fatal: a duplicate-key add or unsupported var type just
                    // leaves the placeholder unresolved.
                }
            }
        }
        catch
        {
            // Reflection shape mismatch — let downstream Resolve() fall through
            // to the raw template; better than crashing the whole event payload.
        }
    }

    private static void TryLogEventOptionReflection(object option, string eventId, int optionIndex, string optionTitle)
    {
        if (!IsEventReflectionDebugEnabled())
        {
            return;
        }

        var type = option.GetType();
        var probeKey = $"{eventId}|{optionIndex}|{optionTitle}|{type.FullName}";
        lock (EventReflectionProbeLock)
        {
            if (!EventReflectionProbeSeen.Add(probeKey))
            {
                return;
            }
        }

        const BindingFlags flags = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var props = string.Join(", ", type.GetProperties(flags).Select(p => p.Name).OrderBy(name => name));
        var fields = string.Join(", ", type.GetFields(flags).Select(f => f.Name).OrderBy(name => name));
        var hits = new List<string>();
        foreach (var memberName in EventReflectionCandidateMembers)
        {
            var value = TryGetMemberValue(option, memberName);
            if (value != null)
            {
                hits.Add($"{memberName}:{value.GetType().FullName}");
            }
        }

        Log.Warn(
            $"[STS2AIAgent][event-reflect] event={eventId} option={optionIndex} title='{optionTitle}' "
            + $"type={type.FullName} hits=[{string.Join(", ", hits)}] props=[{props}] fields=[{fields}]");
    }

    private static int? GetFirstNullableIntProperty(object target, params string[] propertyNames)
    {
        foreach (var propertyName in propertyNames)
        {
            var value = GetReflectedNullableIntProperty(target, propertyName);
            if (value.HasValue)
            {
                return value.Value;
            }
        }

        return null;
    }

    private static int? TryParseEventCost(string text, Regex regex)
    {
        var normalized = NormalizeEventStructuredText(text);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return null;
        }

        var match = regex.Match(normalized);
        if (!match.Success || match.Groups.Count < 2)
        {
            return null;
        }

        return int.TryParse(match.Groups[1].Value, out var value) ? value : null;
    }

    private static EventCardInfo[] ExtractEventCardInfos(object option, string optionDescription)
    {
        var cards = new List<EventCardInfo>();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        foreach (var card in ExtractEventHoverTipCards(option))
        {
            var info = BuildEventCardInfo(card);
            if (!string.IsNullOrWhiteSpace(info.name) && seen.Add($"{info.name}|{info.is_upgraded}"))
            {
                cards.Add(info);
            }
        }

        if (cards.Count == 0)
        {
            foreach (var memberName in EventCardMemberCandidates)
            {
                var value = TryGetMemberValue(option, memberName);
                if (value == null)
                {
                    continue;
                }

                foreach (var card in ExtractCards(value))
                {
                    var info = BuildEventCardInfo(card);
                    if (!string.IsNullOrWhiteSpace(info.name) && seen.Add($"{info.name}|{info.is_upgraded}"))
                    {
                        cards.Add(info);
                    }
                }

                foreach (var candidate in EnumerateCandidateObjects(value))
                {
                    if (candidate is CardModel)
                    {
                        continue;
                    }

                    var info = BuildEventCardInfo(candidate);
                    if (!string.IsNullOrWhiteSpace(info.name) && seen.Add($"{info.name}|{info.is_upgraded}"))
                    {
                        cards.Add(info);
                    }
                }
            }
        }

        if (cards.Count == 0)
        {
            foreach (var info in ExtractTextCardInfos(optionDescription))
            {
                if (!string.IsNullOrWhiteSpace(info.name) && seen.Add($"{info.name}|{info.is_upgraded}"))
                {
                    cards.Add(info);
                }
            }
        }

        return cards.ToArray();
    }

    private static EventRelicInfo[] ExtractEventRelicInfos(object option, string optionDescription)
    {
        var relics = new List<EventRelicInfo>();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        foreach (var relic in ExtractEventHoverTipRelics(option))
        {
            var info = BuildEventRelicInfo(relic);
            if (!string.IsNullOrWhiteSpace(info.name) && seen.Add(info.name))
            {
                relics.Add(info);
            }
        }

        if (relics.Count == 0)
        {
            foreach (var memberName in EventRelicMemberCandidates)
            {
                var value = TryGetMemberValue(option, memberName);
                if (value == null)
                {
                    continue;
                }

                foreach (var candidate in EnumerateCandidateObjects(value))
                {
                    var info = BuildEventRelicInfo(candidate);
                    if (!string.IsNullOrWhiteSpace(info.name) && seen.Add(info.name))
                    {
                        relics.Add(info);
                    }
                }
            }
        }

        if (relics.Count == 0)
        {
            var placeholder = TryBuildRandomRelicPlaceholder(optionDescription);
            if (placeholder != null && !string.IsNullOrWhiteSpace(placeholder.name))
            {
                relics.Add(placeholder);
            }
        }

        return relics.ToArray();
    }

    private static EventPotionInfo[] ExtractEventPotionInfos(object option, string optionDescription)
    {
        var potions = new List<EventPotionInfo>();
        var seen = new HashSet<string>(StringComparer.Ordinal);

        foreach (var potion in ExtractEventHoverTipPotions(option))
        {
            var info = BuildEventPotionInfo(potion);
            if (!string.IsNullOrWhiteSpace(info.name) && seen.Add(info.name))
            {
                potions.Add(info);
            }
        }

        if (potions.Count == 0)
        {
            foreach (var memberName in EventPotionMemberCandidates)
            {
                var value = TryGetMemberValue(option, memberName);
                if (value == null)
                {
                    continue;
                }

                foreach (var candidate in EnumerateCandidateObjects(value))
                {
                    var info = BuildEventPotionInfo(candidate);
                    if (!string.IsNullOrWhiteSpace(info.name) && seen.Add(info.name))
                    {
                        potions.Add(info);
                    }
                }
            }
        }

        if (potions.Count == 0)
        {
            var placeholder = TryBuildRandomPotionPlaceholder(optionDescription);
            if (placeholder != null && !string.IsNullOrWhiteSpace(placeholder.name))
            {
                potions.Add(placeholder);
            }
        }

        return potions.ToArray();
    }

    private static string[] ExtractEventCurseRisks(object option, string optionDescription)
    {
        var curses = new HashSet<string>(StringComparer.Ordinal);

        foreach (var card in ExtractEventHoverTipCards(option))
        {
            if (card.Type == CardType.Curse)
            {
                var curseName = EnglishLocResolver.ResolveCardTitle(card);
                if (!string.IsNullOrWhiteSpace(curseName))
                {
                    curses.Add(curseName);
                }
            }
        }

        if (curses.Count == 0)
        {
            foreach (var memberName in EventCurseMemberCandidates)
            {
                var value = TryGetMemberValue(option, memberName);
                if (value == null)
                {
                    continue;
                }

                foreach (var card in ExtractCards(value))
                {
                    var curseName = EnglishLocResolver.ResolveCardTitle(card);
                    if (!string.IsNullOrWhiteSpace(curseName))
                    {
                        curses.Add(curseName);
                    }
                }

                foreach (var candidate in EnumerateCandidateObjects(value))
                {
                    var name = SafeReadString(() =>
                        GetDynamicFormattedTextProperty(candidate, "Title", "Name", "CardName")
                        ?? GetReflectedStringProperty(candidate, "Title")
                        ?? GetReflectedStringProperty(candidate, "Name")
                        ?? GetReflectedStringProperty(candidate, "CardName"));
                    if (!string.IsNullOrWhiteSpace(name))
                    {
                        curses.Add(name);
                    }
                }
            }
        }

        foreach (var curseName in ExtractTextCurseRisks(optionDescription))
        {
            curses.Add(curseName);
        }

        return curses.ToArray();
    }

    private static IEnumerable<IHoverTip> GetEventHoverTips(object option)
    {
        if (option is EventOption eventOption)
        {
            return eventOption.HoverTips ?? Array.Empty<IHoverTip>();
        }

        var value = TryGetMemberValue(option, "HoverTips");
        if (value is IEnumerable<IHoverTip> hoverTips)
        {
            return hoverTips;
        }

        if (value is IEnumerable enumerable)
        {
            return enumerable.OfType<IHoverTip>().ToArray();
        }

        return Array.Empty<IHoverTip>();
    }

    private static IEnumerable<CardModel> ExtractEventHoverTipCards(object option)
    {
        foreach (var hoverTip in GetEventHoverTips(option))
        {
            if (hoverTip is CardHoverTip cardHoverTip)
            {
                yield return cardHoverTip.Card;
                continue;
            }

            if (hoverTip.CanonicalModel is CardModel cardModel)
            {
                yield return cardModel;
            }
        }
    }

    private static IEnumerable<RelicModel> ExtractEventHoverTipRelics(object option)
    {
        foreach (var hoverTip in GetEventHoverTips(option))
        {
            if (hoverTip.CanonicalModel is RelicModel relicModel)
            {
                yield return relicModel;
            }
        }
    }

    private static IEnumerable<PotionModel> ExtractEventHoverTipPotions(object option)
    {
        foreach (var hoverTip in GetEventHoverTips(option))
        {
            if (hoverTip.CanonicalModel is PotionModel potionModel)
            {
                yield return potionModel;
            }
        }
    }

    private static IEnumerable<string> ExtractTextCurseRisks(string optionDescription)
    {
        var normalizedDescription = NormalizeEventStructuredText(optionDescription);
        if (string.IsNullOrWhiteSpace(normalizedDescription))
        {
            yield break;
        }

        var matchedKnownCurse = false;
        foreach (var curseName in KnownEventCurseNames)
        {
            if (!Regex.IsMatch(
                    normalizedDescription,
                    $@"\b{Regex.Escape(curseName)}\b",
                    RegexOptions.IgnoreCase | RegexOptions.CultureInvariant))
            {
                continue;
            }

            matchedKnownCurse = true;
            yield return curseName;
        }

        if (!matchedKnownCurse && EventGenericCurseRegex.IsMatch(normalizedDescription))
        {
            yield return "Unknown curse";
        }
    }

    private static IEnumerable<EventCardInfo> ExtractTextCardInfos(string optionDescription)
    {
        var normalizedDescription = NormalizeEventStructuredText(optionDescription);
        if (string.IsNullOrWhiteSpace(normalizedDescription))
        {
            yield break;
        }

        foreach (var entry in EventCardTextFallbacks)
        {
            if (!Regex.IsMatch(
                    normalizedDescription,
                    $@"\b{Regex.Escape(entry.Key)}\b",
                    RegexOptions.IgnoreCase | RegexOptions.CultureInvariant))
            {
                continue;
            }

            yield return CloneEventCardInfo(entry.Value);
        }
    }

    private static EventCardInfo CloneEventCardInfo(EventCardInfo info)
    {
        return new EventCardInfo
        {
            name = info.name,
            cost = info.cost,
            type = info.type,
            rules_text = info.rules_text,
            is_upgraded = info.is_upgraded
        };
    }

    private static string NormalizeEventStructuredText(string value)
    {
        return string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : NormalizeCardRulesText(value);
    }

    private static string NormalizeEventRewardRarity(string rarity)
    {
        if (string.IsNullOrWhiteSpace(rarity))
        {
            return string.Empty;
        }

        var trimmed = NormalizeEventStructuredText(rarity);
        if (string.IsNullOrWhiteSpace(trimmed))
        {
            return string.Empty;
        }

        return CultureInfo.InvariantCulture.TextInfo.ToTitleCase(trimmed.ToLowerInvariant());
    }

    private static EventRelicInfo? TryBuildRandomRelicPlaceholder(string optionDescription)
    {
        var normalizedDescription = NormalizeEventStructuredText(optionDescription);
        if (string.IsNullOrWhiteSpace(normalizedDescription))
        {
            return default;
        }

        var match = EventRandomRelicRegex.Match(normalizedDescription);
        if (!match.Success)
        {
            return default;
        }

        var rarity = NormalizeEventRewardRarity(match.Groups["rarity"].Value);
        var displayName = string.IsNullOrWhiteSpace(rarity)
            ? "Random relic"
            : $"Random {rarity} relic";

        return new EventRelicInfo
        {
            name = displayName,
            description = normalizedDescription,
            rarity = rarity
        };
    }

    private static EventPotionInfo? TryBuildRandomPotionPlaceholder(string optionDescription)
    {
        var normalizedDescription = NormalizeEventStructuredText(optionDescription);
        if (string.IsNullOrWhiteSpace(normalizedDescription))
        {
            return null;
        }

        var match = EventRandomPotionRegex.Match(normalizedDescription);
        if (!match.Success)
        {
            return null;
        }

        var rarity = NormalizeEventRewardRarity(match.Groups["rarity"].Value);
        var displayName = string.IsNullOrWhiteSpace(rarity)
            ? "Random potion"
            : $"Random {rarity} potion";

        return new EventPotionInfo
        {
            name = displayName,
            description = normalizedDescription,
            type = string.IsNullOrWhiteSpace(rarity) ? "Random" : $"{rarity} Random"
        };
    }

    private static IEnumerable<object> EnumerateCandidateObjects(object value)
    {
        if (value is string)
        {
            yield break;
        }

        if (value is IEnumerable enumerable)
        {
            foreach (var item in enumerable)
            {
                if (item != null)
                {
                    yield return item;
                }
            }

            yield break;
        }

        yield return value;
    }

    private static EventCardInfo BuildEventCardInfo(CardModel card)
    {
        return new EventCardInfo
        {
            name = EnglishLocResolver.ResolveCardTitle(card),
            cost = card.EnergyCost.GetWithModifiers(CostModifiers.All),
            type = card.Type.ToString(),
            rules_text = NormalizeEventStructuredText(GetCardRulesText(card)),
            is_upgraded = card.IsUpgraded
        };
    }

    private static EventCardInfo BuildEventCardInfo(object card)
    {
        if (card is CardModel cardModel)
        {
            return BuildEventCardInfo(cardModel);
        }

        return new EventCardInfo
        {
            name = SafeReadString(() =>
                GetDynamicFormattedTextProperty(card, "Title", "Name", "CardName")
                ?? GetReflectedStringProperty(card, "Title")
                ?? GetReflectedStringProperty(card, "Name")
                ?? GetReflectedStringProperty(card, "CardName")),
            cost = GetFirstNullableIntProperty(card, "EnergyCost", "Cost", "CurrentCost") ?? 0,
            type = SafeReadString(() =>
                GetReflectedStringProperty(card, "Type")
                ?? GetReflectedStringProperty(card, "CardType")),
            rules_text = NormalizeEventStructuredText(SafeReadString(() =>
                GetDynamicFormattedTextProperty(card, "RulesText", "Description", "Text", "Body"))),
            is_upgraded = GetReflectedBoolProperty(card, "IsUpgraded")
                || GetReflectedBoolProperty(card, "Upgraded")
        };
    }

    private static EventRelicInfo BuildEventRelicInfo(object relic)
    {
        if (relic is RelicModel relicModel)
        {
            return new EventRelicInfo
            {
                name = EnglishLocResolver.Resolve(relicModel.Title),
                description = NormalizeEventStructuredText(SafeReadString(() => GetDynamicFormattedTextProperty(relicModel, "DynamicDescription", "Description"))),
                rarity = relicModel.Rarity.ToString()
            };
        }

        var name = SafeReadString(() =>
            GetDynamicFormattedTextProperty(relic, "Title", "Name")
            ?? GetReflectedStringProperty(relic, "Title")
            ?? GetReflectedStringProperty(relic, "Name"));
        var description = NormalizeEventStructuredText(SafeReadString(() =>
            GetDynamicFormattedTextProperty(relic, "DynamicDescription", "Description", "Text")));
        var rarity = NormalizeEventRewardRarity(SafeReadString(() =>
            GetReflectedStringProperty(relic, "Rarity")
            ?? GetReflectedStringProperty(relic, "Tier")));

        if (string.IsNullOrWhiteSpace(name))
        {
            var isRandom = GetReflectedBoolProperty(relic, "IsRandom")
                || GetReflectedBoolProperty(relic, "Random")
                || GetReflectedBoolProperty(relic, "IsRandomReward");
            if (isRandom || !string.IsNullOrWhiteSpace(rarity))
            {
                name = string.IsNullOrWhiteSpace(rarity)
                    ? "Random relic"
                    : $"Random {rarity} relic";
            }
        }

        if (string.IsNullOrWhiteSpace(description) && name.StartsWith("Random ", StringComparison.OrdinalIgnoreCase))
        {
            description = string.IsNullOrWhiteSpace(rarity)
                ? "Receive a random relic."
                : $"Receive a random {rarity.ToLowerInvariant()} relic.";
        }

        return new EventRelicInfo
        {
            name = name,
            description = description,
            rarity = rarity
        };
    }

    private static EventPotionInfo BuildEventPotionInfo(object potion)
    {
        if (potion is PotionModel potionModel)
        {
            return new EventPotionInfo
            {
                name = EnglishLocResolver.Resolve(potionModel.Title),
                description = NormalizeEventStructuredText(SafeReadString(() => GetDynamicFormattedTextProperty(potionModel, "DynamicDescription", "Description"))),
                type = potionModel.Usage.ToString()
            };
        }

        return new EventPotionInfo
        {
            name = SafeReadString(() =>
                GetDynamicFormattedTextProperty(potion, "Title", "Name")
                ?? GetReflectedStringProperty(potion, "Title")
                ?? GetReflectedStringProperty(potion, "Name")),
            description = NormalizeEventStructuredText(SafeReadString(() =>
                GetDynamicFormattedTextProperty(potion, "DynamicDescription", "Description", "Text"))),
            type = SafeReadString(() =>
                GetReflectedStringProperty(potion, "Usage")
                ?? GetReflectedStringProperty(potion, "Type")
                ?? GetReflectedStringProperty(potion, "PotionType"))
        };
    }

    private static object? GetReflectedProperty(object target, string propertyName)
    {
        return TryGetMemberValue(target, propertyName);
    }

    private static string? GetReflectedStringProperty(object target, string propertyName)
    {
        var value = GetReflectedProperty(target, propertyName);
        return value?.ToString();
    }

    private static string? GetReflectedFormattedTextProperty(object target, string propertyName)
    {
        var value = GetReflectedProperty(target, propertyName);
        if (value == null)
        {
            return null;
        }

        // Resolve through the English LocManager tables so descriptions emitted to
        // the agent stay English regardless of the player's active locale, then
        // ScrubLocaleNames to strip residual active-locale entity names that got
        // pre-formatted into LocString variables before WithEnglishTables could
        // intercept (e.g. relic transform descriptions where {Card1.Title} was
        // already-Chinese by the time we entered the swap).
        try
        {
            var resolved = EnglishLocResolver.WithEnglishTables(() =>
                value.GetType().GetMethod("GetFormattedText")?.Invoke(value, null)?.ToString());
            return EnglishLocResolver.ScrubLocaleNames(resolved);
        }
        catch
        {
            return value.ToString();
        }
    }

    private static string? GetDynamicFormattedTextProperty(object target, params string[] propertyNames)
    {
        foreach (var propertyName in propertyNames)
        {
            var value = GetReflectedFormattedTextProperty(target, propertyName);
            if (!string.IsNullOrWhiteSpace(value))
            {
                return value;
            }
        }

        return null;
    }

    private static int? GetReflectedNullableIntProperty(object target, string propertyName)
    {
        try
        {
            var value = GetReflectedProperty(target, propertyName);
            return value == null ? null : Convert.ToInt32(value);
        }
        catch
        {
            return null;
        }
    }

    private static bool GetReflectedBoolProperty(object target, string propertyName)
    {
        try
        {
            var value = GetReflectedProperty(target, propertyName);
            return value != null && Convert.ToBoolean(value);
        }
        catch
        {
            return false;
        }
    }

    private static bool GetEventOptionWillKillPlayer(object eventModel, object option)
    {
        try
        {
            var owner = GetReflectedProperty(eventModel, "Owner");
            var willKillPlayer = GetReflectedProperty(option, "WillKillPlayer") as Delegate;
            if (owner == null || willKillPlayer == null)
            {
                return false;
            }

            return willKillPlayer.DynamicInvoke(owner) as bool? ?? false;
        }
        catch
        {
            return false;
        }
    }

    private static CharacterSelectPlayerPayload BuildCharacterSelectPlayerPayload(LobbyPlayer player, ulong localPlayerId)
    {
        return new CharacterSelectPlayerPayload
        {
            player_id = NetIdToString(player.id),
            slot_index = player.slotId,
            is_local = player.id == localPlayerId,
            character_id = player.character?.Id.Entry,
            character_name = EnglishLocResolver.Resolve(player.character?.Title),
            is_ready = player.isReady,
            max_multiplayer_ascension_unlocked = player.maxMultiplayerAscensionUnlocked
        };
    }

    private static RunPlayerSummaryPayload BuildRunPlayerSummaryPayload(
        RunState runState,
        Player player,
        IReadOnlyCollection<ulong> connectedPlayerIds,
        ulong localPlayerId)
    {
        return new RunPlayerSummaryPayload
        {
            player_id = NetIdToString(player.NetId),
            slot_index = runState.GetPlayerSlotIndex(player),
            is_local = player.NetId == localPlayerId,
            is_connected = connectedPlayerIds.Contains(player.NetId),
            character_id = player.Character.Id.Entry,
            character_name = EnglishLocResolver.Resolve(player.Character.Title),
            current_hp = player.Creature.CurrentHp,
            max_hp = player.Creature.MaxHp,
            gold = player.Gold,
            is_alive = player.Creature.IsAlive
        };
    }

    private static CombatPlayerSummaryPayload BuildCombatPlayerSummaryPayload(
        Player player,
        CombatState combatState,
        IReadOnlyCollection<ulong> connectedPlayerIds,
        ulong localPlayerId)
    {
        return new CombatPlayerSummaryPayload
        {
            player_id = NetIdToString(player.NetId),
            slot_index = combatState.RunState is RunState runState ? runState.GetPlayerSlotIndex(player) : 0,
            is_local = player.NetId == localPlayerId,
            is_connected = connectedPlayerIds.Contains(player.NetId),
            character_id = player.Character.Id.Entry,
            character_name = EnglishLocResolver.Resolve(player.Character.Title),
            current_hp = player.Creature.CurrentHp,
            max_hp = player.Creature.MaxHp,
            block = player.Creature.Block,
            energy = player.PlayerCombatState?.Energy ?? 0,
            stars = player.PlayerCombatState?.Stars ?? 0,
            focus = player.Creature.GetPowerAmount<FocusPower>(),
            is_alive = player.Creature.IsAlive
        };
    }

    private static string? GetCardTargetIndexSpace(CardModel card)
    {
        return card.TargetType switch
        {
            TargetType.AnyEnemy => "enemies",
            TargetType.AnyAlly => "players",
            _ => null
        };
    }

    private static string? GetPotionTargetIndexSpace(CombatState? combatState, PotionModel potion)
    {
        return potion.TargetType switch
        {
            TargetType.AnyEnemy => "enemies",
            TargetType.AnyPlayer when PotionRequiresExplicitPlayerSelection(combatState, potion) => "players",
            TargetType.AnyAlly => "players",
            _ => null
        };
    }

    private static int[] GetCardTargetIndices(CombatState combatState, CardModel card)
    {
        return card.TargetType switch
        {
            TargetType.AnyEnemy => GetTargetableEnemyIndices(combatState),
            TargetType.AnyAlly => GetTargetablePlayerIndices(combatState, card.Owner, allowSelf: false),
            _ => Array.Empty<int>()
        };
    }

    private static int[] GetPotionTargetIndices(CombatState? combatState, PotionModel potion)
    {
        if (combatState == null)
        {
            return Array.Empty<int>();
        }

        return potion.TargetType switch
        {
            TargetType.AnyEnemy => GetTargetableEnemyIndices(combatState),
            TargetType.AnyPlayer when PotionRequiresExplicitPlayerSelection(combatState, potion) => GetTargetablePlayerIndices(combatState, potion.Owner, allowSelf: true),
            TargetType.AnyAlly => GetTargetablePlayerIndices(combatState, potion.Owner, allowSelf: false),
            _ => Array.Empty<int>()
        };
    }

    private static ShopCardPayload BuildShopCardPayload(MerchantCardEntry entry, int index, string category)
    {
        var card = entry.CreationResult?.Card;
        var resolvedRulesText = GetResolvedCardRulesText(card);
        var dynamicValues = BuildCardDynamicValuePayloads(card);
        return new ShopCardPayload
        {
            index = index,
            category = category,
            card_id = card?.Id.Entry ?? string.Empty,
            name = EnglishLocResolver.ResolveCardTitle(card),
            upgraded = card?.IsUpgraded ?? false,
            card_type = card?.Type.ToString() ?? string.Empty,
            rarity = card?.Rarity.ToString() ?? string.Empty,
            costs_x = card?.EnergyCost.CostsX ?? false,
            star_costs_x = card?.HasStarCostX ?? false,
            energy_cost = card?.EnergyCost.GetWithModifiers(CostModifiers.All) ?? 0,
            star_cost = card != null ? Math.Max(0, card.GetStarCostWithModifiers()) : 0,
            rules_text = GetCardRulesText(card),
            resolved_rules_text = resolvedRulesText,
            dynamic_values = dynamicValues,
            price = entry.IsStocked ? entry.Cost : 0,
            on_sale = entry.IsOnSale,
            is_stocked = entry.IsStocked,
            enough_gold = entry.IsStocked && entry.EnoughGold,
            generated_cards = ExtractGeneratedCards(card)
        };
    }

    private static ShopRelicPayload BuildShopRelicPayload(MerchantRelicEntry entry, int index)
    {
        var relic = entry.Model;
        return new ShopRelicPayload
        {
            index = index,
            relic_id = relic?.Id.Entry ?? string.Empty,
            name = EnglishLocResolver.Resolve(relic?.Title),
            description = relic != null ? GetDynamicFormattedTextProperty(relic, "DynamicDescription", "Description") : null,
            rarity = relic?.Rarity.ToString() ?? string.Empty,
            price = entry.IsStocked ? entry.Cost : 0,
            is_stocked = entry.IsStocked,
            enough_gold = entry.IsStocked && entry.EnoughGold
        };
    }

    private static ShopPotionPayload BuildShopPotionPayload(MerchantPotionEntry entry, int index, Player? player)
    {
        var potion = entry.Model;
        return new ShopPotionPayload
        {
            index = index,
            potion_id = potion?.Id.Entry,
            name = EnglishLocResolver.Resolve(potion?.Title),
            description = potion != null ? NormalizeCardRulesText(GetDynamicFormattedTextProperty(potion, "DynamicDescription", "Description") ?? string.Empty) : null,
            rarity = potion?.Rarity.ToString(),
            usage = potion?.Usage.ToString(),
            price = entry.IsStocked ? entry.Cost : 0,
            is_stocked = entry.IsStocked,
            enough_gold = CanPurchaseShopPotion(player, entry)
        };
    }

    private static bool CanPurchaseShopPotion(Player? player, MerchantPotionEntry entry)
    {
        return entry.IsStocked &&
            entry.EnoughGold &&
            player?.PotionSlots.Any(slot => slot == null) == true;
    }

    private static ShopCardRemovalPayload? BuildShopCardRemovalPayload(MerchantCardRemovalEntry? entry)
    {
        if (entry == null)
        {
            return null;
        }

        return new ShopCardRemovalPayload
        {
            price = entry.IsStocked ? entry.Cost : 0,
            available = entry.IsStocked,
            used = entry.Used,
            enough_gold = entry.IsStocked && entry.EnoughGold
        };
    }

    private static DeckCardPayload BuildDeckCardPayload(CardModel card, int index)
    {
        var resolvedRulesText = GetResolvedCardRulesText(card);
        var dynamicValues = BuildCardDynamicValuePayloads(card);
        string? enchantmentId = null;
        string? enchantmentName = null;
        try
        {
            var enchantment = card.Enchantment;
            if (enchantment != null)
            {
                enchantmentId = enchantment.Id?.Entry;
                enchantmentName = EnglishLocResolver.Resolve(enchantment.Title);
            }
        }
        catch
        {
            // Non-fatal: enchantment data may not be available on all card states.
        }
        return new DeckCardPayload
        {
            index = index,
            card_id = card.Id.Entry,
            name = EnglishLocResolver.ResolveCardTitle(card),
            upgraded = card.IsUpgraded,
            card_type = card.Type.ToString(),
            rarity = card.Rarity.ToString(),
            costs_x = card.EnergyCost.CostsX,
            star_costs_x = card.HasStarCostX,
            energy_cost = card.EnergyCost.GetWithModifiers(CostModifiers.All),
            star_cost = Math.Max(0, card.GetStarCostWithModifiers()),
            rules_text = GetCardRulesText(card),
            resolved_rules_text = resolvedRulesText,
            dynamic_values = dynamicValues,
            enchantment_id = enchantmentId,
            enchantment_name = enchantmentName
        };
    }

    private static SelectionCardPayload BuildSelectionCardPayload(CardModel card, int index, bool includeUpgradePreview = false)
    {
        return BuildSelectionCardPayload(card, index, stableId: null, isSelected: false, isSelectable: true, includeUpgradePreview: includeUpgradePreview);
    }

    private static string BuildSelectionCardStableId(CardModel? card)
    {
        if (card == null)
        {
            return string.Empty;
        }

        return $"{card.Id.Entry}:{(card.IsUpgraded ? 1 : 0)}:{RuntimeHelpers.GetHashCode(card):x}";
    }

    private static SelectionCardPayload BuildSelectionCardPayload(
        CardModel card,
        int index,
        string? stableId,
        bool isSelected,
        bool isSelectable,
        bool includeUpgradePreview = false)
    {
        var resolvedRulesText = GetResolvedCardRulesText(card);
        var dynamicValues = BuildCardDynamicValuePayloads(card);

        // Upgrade preview: temporarily upgrade the card, read stats, then downgrade
        string? upgradePreviewDesc = null;
        int? upgradePreviewCost = null;
        if (includeUpgradePreview && !card.IsUpgraded && card.CurrentUpgradeLevel < card.MaxUpgradeLevel)
        {
            var costBefore = card.EnergyCost.GetWithModifiers(CostModifiers.All);
            try
            {
                card.UpgradeInternal();
                try
                {
                    upgradePreviewDesc = GetResolvedCardRulesText(card);
                    var costAfter = card.EnergyCost.GetWithModifiers(CostModifiers.All);
                    if (costAfter != costBefore)
                        upgradePreviewCost = costAfter;
                }
                finally
                {
                    card.DowngradeInternal();
                }
            }
            catch
            {
                // Non-fatal: skip upgrade preview if UpgradeInternal itself fails
            }
        }

        return new SelectionCardPayload
        {
            index = index,
            stable_id = stableId ?? BuildSelectionCardStableId(card),
            card_id = card.Id.Entry,
            name = EnglishLocResolver.ResolveCardTitle(card),
            upgraded = card.IsUpgraded,
            card_type = card.Type.ToString(),
            rarity = card.Rarity.ToString(),
            costs_x = card.EnergyCost.CostsX,
            star_costs_x = card.HasStarCostX,
            energy_cost = card.EnergyCost.GetWithModifiers(CostModifiers.All),
            star_cost = Math.Max(0, card.GetStarCostWithModifiers()),
            rules_text = GetCardRulesText(card),
            resolved_rules_text = resolvedRulesText,
            dynamic_values = dynamicValues,
            is_selected = isSelected,
            is_selectable = isSelectable,
            upgrade_preview_description = upgradePreviewDesc,
            upgrade_preview_cost = upgradePreviewCost
        };
    }

    private static bool IsClickableControlUsable(NClickableControl? control)
    {
        return control != null &&
            GodotObject.IsInstanceValid(control) &&
            control.IsEnabled &&
            control.IsVisibleInTree();
    }

    public static bool IsControlClickable(NClickableControl? control)
    {
        return IsClickableControlUsable(control);
    }

    private static bool IsProceedButtonUsable(NProceedButton? button)
    {
        return IsClickableControlUsable(button);
    }

    private static string GetRewardTypeName(Reward? reward)
    {
        return reward switch
        {
            CardReward => "Card",
            GoldReward => "Gold",
            PotionReward => "Potion",
            RelicReward => "Relic",
            CardRemovalReward => "RemoveCard",
            SpecialCardReward => "SpecialCard",
            LinkedRewardSet => "LinkedRewardSet",
            null => "Unknown",
            _ => reward.GetType().Name
        };
    }

    private static bool IsPotionUsable(IScreenContext? currentScreen, CombatState? combatState, Player player, PotionModel? potion)
    {
        if (potion == null || !IsPotionDiscardable(player, potion))
        {
            return false;
        }

        if (!potion.PassesCustomUsabilityCheck || !IsPotionTargetSupported(combatState, potion))
        {
            return false;
        }

        return potion.Usage switch
        {
            PotionUsage.AnyTime => true,
            PotionUsage.CombatOnly => CanUseCombatActions(currentScreen, combatState, out _, out _),
            _ => false
        };
    }

    private static bool CanDiscardPotionsInCurrentScreen(IScreenContext? currentScreen)
    {
        // Restrict potion discard to screens where the in-game UI actually
        // surfaces it: reward / card-reward (must free a slot before claiming
        // a new potion), merchant inventory (buying potions), and the pause
        // menu (vanilla allows discarding from there).  Returning `true`
        // unconditionally caused stuck loops when overlay screens (deck view,
        // map-from-topbar, etc.) trapped the agent: those overlays don't
        // expose any other action, so `discard_potion` was the only one the
        // agent could fire, draining the potion inventory until the run was
        // abandoned via max_steps.
        return currentScreen is
            NRewardsScreen or
            NCardRewardSelectionScreen or
            NMerchantRoom or
            NMerchantInventory or
            NPauseMenu;
    }

    private static bool IsPotionDiscardable(Player player, PotionModel? potion)
    {
        return potion != null &&
            !potion.IsQueued &&
            !potion.Owner.Creature.IsDead &&
            player.CanRemovePotions;
    }

    public static bool PotionRequiresTarget(CombatState? combatState, PotionModel potion)
    {
        return potion.TargetType switch
        {
            TargetType.AnyEnemy => true,
            TargetType.AnyPlayer => PotionRequiresExplicitPlayerSelection(combatState, potion),
            TargetType.AnyAlly => combatState != null && GetTargetablePlayerIndices(combatState, potion.Owner, allowSelf: false).Length > 0,
            _ => false
        };
    }

    private static bool IsPotionTargetSupported(CombatState? combatState, PotionModel potion)
    {
        return potion.TargetType switch
        {
            TargetType.AnyEnemy => GetTargetableEnemyIndices(combatState).Length > 0,
            TargetType.AnyPlayer => PotionRequiresExplicitPlayerSelection(combatState, potion)
                ? GetTargetablePlayerIndices(combatState, potion.Owner, allowSelf: true).Length > 0
                : true,
            TargetType.AnyAlly => GetTargetablePlayerIndices(combatState, potion.Owner, allowSelf: false).Length > 0,
            TargetType.TargetedNoCreature => true,
            _ => true
        };
    }

    private static bool PotionRequiresExplicitPlayerSelection(CombatState? combatState, PotionModel potion)
    {
        return combatState != null &&
            CombatManager.Instance.IsInProgress &&
            potion.Owner.RunState.Players.Count > 1 &&
            combatState.PlayerCreatures.Count(creature => creature.IsAlive) > 1;
    }

    private static bool RequiresIndexedCardTarget(TargetType targetType)
    {
        return targetType == TargetType.AnyEnemy || targetType == TargetType.AnyAlly;
    }

    public static int[] GetTargetableEnemyIndices(CombatState? combatState)
    {
        if (combatState == null)
        {
            return Array.Empty<int>();
        }

        return combatState.Enemies
            .Select((enemy, index) => new { enemy, index })
            .Where(entry => entry.enemy.IsAlive && entry.enemy.IsHittable)
            .Select(entry => entry.index)
            .ToArray();
    }

    public static int[] GetTargetablePlayerIndices(CombatState? combatState, Player owner, bool allowSelf)
    {
        if (combatState == null)
        {
            return Array.Empty<int>();
        }

        return GetOrderedCombatPlayers(combatState)
            .Select((player, index) => new { player, index })
            .Where(entry => entry.player.Creature.IsAlive)
            .Where(entry => allowSelf || entry.player.NetId != owner.NetId)
            .Select(entry => entry.index)
            .ToArray();
    }

    private static IReadOnlyList<Player> GetOrderedCombatPlayers(CombatState combatState)
    {
        return combatState.Players
            .OrderBy(player => combatState.RunState is RunState runState ? runState.GetPlayerSlotIndex(player) : 0)
            .ToArray();
    }

    private static NMerchantRoom? GetMerchantRoom(IScreenContext? currentScreen)
    {
        return currentScreen switch
        {
            NMerchantRoom room => room,
            NMerchantInventory => NMerchantRoom.Instance,
            _ => null
        };
    }

    private static NMerchantInventory? GetMerchantInventoryScreen(IScreenContext? currentScreen)
    {
        return currentScreen switch
        {
            NMerchantInventory inventory => inventory,
            NMerchantRoom room when room.Inventory != null => room.Inventory,
            _ => null
        };
    }

    public static MerchantInventory? GetMerchantInventory(IScreenContext? currentScreen)
    {
        return GetMerchantInventoryScreen(currentScreen)?.Inventory ?? GetMerchantRoom(currentScreen)?.Inventory?.Inventory;
    }

    public static IReadOnlyList<MerchantCardEntry> GetMerchantCardEntries(IScreenContext? currentScreen)
    {
        var inventory = GetMerchantInventory(currentScreen);
        if (inventory == null)
        {
            return Array.Empty<MerchantCardEntry>();
        }

        return inventory.CharacterCardEntries.Concat(inventory.ColorlessCardEntries).ToArray();
    }

    public static IReadOnlyList<MerchantRelicEntry> GetMerchantRelicEntries(IScreenContext? currentScreen)
    {
        return GetMerchantInventory(currentScreen)?.RelicEntries?.ToArray() ?? Array.Empty<MerchantRelicEntry>();
    }

    public static IReadOnlyList<MerchantPotionEntry> GetMerchantPotionEntries(IScreenContext? currentScreen)
    {
        return GetMerchantInventory(currentScreen)?.PotionEntries?.ToArray() ?? Array.Empty<MerchantPotionEntry>();
    }

    public static MerchantCardRemovalEntry? GetMerchantCardRemovalEntry(IScreenContext? currentScreen)
    {
        return GetMerchantInventory(currentScreen)?.CardRemovalEntry;
    }

    public static NCharacterSelectScreen? GetCharacterSelectScreen(IScreenContext? currentScreen)
    {
        return currentScreen as NCharacterSelectScreen;
    }

    public static NMultiplayerTest? GetMultiplayerTestScene()
    {
        var currentScene = NGame.Instance?.RootSceneContainer?.CurrentScene;
        return currentScene is NMultiplayerTest multiplayerTest && multiplayerTest.IsVisibleInTree()
            ? multiplayerTest
            : null;
    }

    public static StartRunLobby? GetMultiplayerTestLobby(NMultiplayerTest scene)
    {
        const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
        var field = typeof(NMultiplayerTest).GetField("_lobby", flags);
        return field?.GetValue(scene) as StartRunLobby;
    }

    public static NMultiplayerTestCharacterPaginator? GetMultiplayerTestCharacterPaginator(NMultiplayerTest scene)
    {
        return scene.GetNodeOrNull<NMultiplayerTestCharacterPaginator>("CharacterChooser");
    }

    public static string GetMultiplayerLobbyJoinHost()
    {
        var raw = System.Environment.GetEnvironmentVariable("STS2_MULTIPLAYER_HOST_IP");
        return string.IsNullOrWhiteSpace(raw) ? "127.0.0.1" : raw.Trim();
    }

    public static int GetMultiplayerLobbyJoinPort()
    {
        return 33771;
    }

    public static ulong GetMultiplayerLobbyJoinNetIdHint()
    {
        var raw = System.Environment.GetEnvironmentVariable("STS2_MULTIPLAYER_NET_ID");
        if (!string.IsNullOrWhiteSpace(raw) && ulong.TryParse(raw.Trim(), out var parsed))
        {
            return parsed;
        }

        return (ulong)System.Environment.ProcessId;
    }

    public static CharacterModel[] GetMultiplayerLobbyCharacters()
    {
        return
        [
            ModelDb.Character<Ironclad>(),
            ModelDb.Character<Silent>(),
            ModelDb.Character<Regent>(),
            ModelDb.Character<Necrobinder>(),
            ModelDb.Character<Defect>()
        ];
    }

    public static IReadOnlyList<NCharacterSelectButton> GetCharacterSelectButtons(IScreenContext? currentScreen)
    {
        var screen = GetCharacterSelectScreen(currentScreen);
        if (screen == null)
        {
            return Array.Empty<NCharacterSelectButton>();
        }

        return FindDescendants<NCharacterSelectButton>(screen)
            .Where(node => GodotObject.IsInstanceValid(node))
            .OrderBy(node => node.GlobalPosition.Y)
            .ThenBy(node => node.GlobalPosition.X)
            .ToArray();
    }

    public static NConfirmButton? GetCharacterEmbarkButton(IScreenContext? currentScreen)
    {
        return GetCharacterSelectScreen(currentScreen)?.GetNodeOrNull<NConfirmButton>("ConfirmButton");
    }

    public static NBackButton? GetCharacterUnreadyButton(IScreenContext? currentScreen)
    {
        return GetCharacterSelectScreen(currentScreen)?.GetNodeOrNull<NBackButton>("UnreadyButton");
    }

    public static NMainMenuTextButton? GetMainMenuContinueButton(NMainMenu mainMenu)
    {
        return mainMenu.GetNodeOrNull<NMainMenuTextButton>("MainMenuTextButtons/ContinueButton");
    }

    public static NMainMenuTextButton? GetMainMenuAbandonRunButton(NMainMenu mainMenu)
    {
        return mainMenu.GetNodeOrNull<NMainMenuTextButton>("MainMenuTextButtons/AbandonRunButton");
    }

    public static NMainMenuTextButton? GetMainMenuSingleplayerButton(NMainMenu mainMenu)
    {
        return mainMenu.GetNodeOrNull<NMainMenuTextButton>("MainMenuTextButtons/SingleplayerButton");
    }

    public static NMainMenuTextButton? GetMainMenuTimelineButton(NMainMenu mainMenu)
    {
        return mainMenu.GetNodeOrNull<NMainMenuTextButton>("MainMenuTextButtons/TimelineButton");
    }

    public static NTopBarPauseButton? GetTopBarPauseButton()
    {
        return NRun.Instance?.GlobalUi?.TopBar?.Pause;
    }

    public static NPauseMenuButton? GetPauseMenuSaveAndQuitButton(IScreenContext? currentScreen)
    {
        if (currentScreen is not NPauseMenu pauseMenu || !pauseMenu.IsVisibleInTree())
        {
            return null;
        }

        var buttonContainer = pauseMenu.GetNodeOrNull<Control>("%ButtonContainer");
        var saveAndQuitButton = buttonContainer?.GetNodeOrNull<NPauseMenuButton>("SaveAndQuit");
        if (saveAndQuitButton == null ||
            !GodotObject.IsInstanceValid(saveAndQuitButton) ||
            !saveAndQuitButton.IsVisibleInTree() ||
            !saveAndQuitButton.IsEnabled)
        {
            return null;
        }

        return saveAndQuitButton;
    }

    public static NTimelineScreen? GetTimelineScreen(IScreenContext? currentScreen)
    {
        if (currentScreen is NTimelineScreen timelineScreen && timelineScreen.IsVisibleInTree())
        {
            return timelineScreen;
        }

        return null;
    }

    public static IReadOnlyList<NEpochSlot> GetTimelineSlots(IScreenContext? currentScreen)
    {
        var timelineScreen = GetTimelineScreen(currentScreen);
        if (timelineScreen == null)
        {
            return Array.Empty<NEpochSlot>();
        }

        return FindDescendants<NEpochSlot>(timelineScreen)
            .Where(slot => slot.IsVisibleInTree() && slot.model != null && slot.State != EpochSlotState.NotObtained)
            .OrderBy(slot => slot.GlobalPosition.X)
            .ThenBy(slot => slot.GlobalPosition.Y)
            .ToArray();
    }

    public static NEpochInspectScreen? GetTimelineInspectScreen(IScreenContext? currentScreen)
    {
        var timelineScreen = GetTimelineScreen(currentScreen);
        var inspectScreen = timelineScreen?.GetNodeOrNull<NEpochInspectScreen>("%EpochInspectScreen");
        return inspectScreen?.Visible == true ? inspectScreen : null;
    }

    public static NUnlockScreen? GetTimelineUnlockScreen(IScreenContext? currentScreen)
    {
        var timelineScreen = GetTimelineScreen(currentScreen);
        if (timelineScreen == null)
        {
            return null;
        }

        return FindDescendants<NUnlockScreen>(timelineScreen)
            .FirstOrDefault(screen => screen.IsVisibleInTree());
    }

    public static NButton? GetTimelineBackButton(IScreenContext? currentScreen)
    {
        return GetTimelineScreen(currentScreen)?.GetNodeOrNull<NButton>("BackButton");
    }

    public static NButton? GetTimelineInspectCloseButton(IScreenContext? currentScreen)
    {
        return GetTimelineInspectScreen(currentScreen)?.GetNodeOrNull<NButton>("%CloseButton");
    }

    public static NButton? GetTimelineUnlockConfirmButton(IScreenContext? currentScreen)
    {
        return GetTimelineUnlockScreen(currentScreen)?.GetNodeOrNull<NButton>("ConfirmButton");
    }

    public static NMainMenuSubmenuStack? GetMainMenuSubmenuStack(Node? node)
    {
        var current = node;
        while (current != null)
        {
            if (current is NMainMenuSubmenuStack submenuStack)
            {
                return submenuStack;
            }

            current = current.GetParent();
        }

        return null;
    }

    private static NRewardsScreen? FindAncestorRewardsScreen(Node startNode)
    {
        var current = startNode.GetParent();
        while (current != null)
        {
            if (current is NRewardsScreen rewardsScreen)
                return rewardsScreen;
            current = current.GetParent();
        }

        return null;
    }

    public static IScreenContext? GetOpenModal()
    {
        return NModalContainer.Instance?.OpenModal;
    }

    public static NButton? GetModalConfirmButton(IScreenContext? currentScreen)
    {
        // "%FtueConfirmButton": the NFtue first-time-tutorial popups (added game
        // v0.107.1, e.g. NAscensionSingleplayerFtue / NAscensionMultiplayerFtue)
        // wire this button's Released signal to CloseFtue. Treating it as a modal
        // confirm lets the agent dismiss the one-time Ascension tutorial overlay
        // instead of stalling on a modal with no actions.
        return FindModalButton("VerticalPopup/YesButton", "ConfirmButton", "%ConfirmButton", "%Confirm", "%AcknowledgeButton", "%FtueConfirmButton");
    }

    public static NButton? GetModalCancelButton(IScreenContext? currentScreen)
    {
        return FindModalButton("VerticalPopup/NoButton", "CancelButton", "%CancelButton", "%BackButton");
    }

    private static NButton? FindModalButton(params string[] paths)
    {
        var modal = GetOpenModal();
        if (modal is not Node modalNode)
        {
            return null;
        }

        foreach (var path in paths)
        {
            var button = modalNode.GetNodeOrNull<NButton>(path);
            if (button != null && GodotObject.IsInstanceValid(button) && button.IsEnabled && button.IsVisibleInTree())
            {
                return button;
            }
        }

        return null;
    }

    private static string? ResolveUnderlyingScreen(Node modalNode)
    {
        var parent = modalNode.GetParent();
        while (parent != null)
        {
            if (parent is IScreenContext screenContext && !ReferenceEquals(parent, modalNode))
            {
                return ResolveNonModalScreen(screenContext);
            }

            parent = parent.GetParent();
        }

        return null;
    }

    private static string ResolveNonModalScreen(IScreenContext? currentScreen)
    {
        if (currentScreen != null &&
            TryGetCombatHandSelection(currentScreen, out _))
        {
            return "CARD_SELECTION";
        }

        if (currentScreen is NCardsViewScreen)
        {
            return "CARDS_VIEW";
        }

        // NChooseABundleSelectionScreen is a dedicated screen type for the "Choose a Pack"
        // event option (e.g. Neow "Scroll Boxes"). Detect it before the event check because
        // TryGetActiveEventModel may still return true while this screen is the top context.
        if (currentScreen is NChooseABundleSelectionScreen)
        {
            return "CARD_SELECTION";
        }

        // Check for embedded card selection UI before the event check.
        // The Neow "Scroll Boxes" option (and similar event-triggered card packs)
        // renders NGridCardHolder nodes inside NEventRoom. TryGetActiveEventModel
        // returns true for NEventRoom unconditionally, so the event check must come
        // AFTER the card-grid check to avoid misclassifying pack selection as EVENT.
        if (currentScreen is Node rootNode &&
            GetVisibleGridCardHolders(rootNode).Count > 0)
        {
            return "CARD_SELECTION";
        }

        if (currentScreen is NCrystalSphereScreen || TryGetActiveEventModel(currentScreen, out _))
        {
            return "EVENT";
        }

        if (GetMultiplayerTestScene() != null)
        {
            return "MULTIPLAYER_LOBBY";
        }

        return currentScreen switch
        {
            NGameOverScreen => "GAME_OVER",
            NPauseMenu => "PAUSE_MENU",
            NCardRewardSelectionScreen => "REWARD",
            NChooseACardSelectionScreen => "CARD_SELECTION",
            NChooseABundleSelectionScreen => "CARD_SELECTION",
            NDeckCardSelectScreen or NDeckUpgradeSelectScreen or NDeckTransformSelectScreen or NDeckEnchantSelectScreen => "CARD_SELECTION",
            NCardGridSelectionScreen => "CARD_SELECTION",
            NRewardsScreen => "REWARD",
            NTreasureRoom or NTreasureRoomRelicCollection => "CHEST",
            NRestSiteRoom => "REST",
            NMerchantRoom or NMerchantInventory => "SHOP",
            NEventRoom => "EVENT",
            NCombatRoom => "COMBAT",
            NMapScreen or NMapRoom => "MAP",
            NCharacterSelectScreen => "CHARACTER_SELECT",
            NTimelineScreen => "TIMELINE",
            NPatchNotesScreen => "MAIN_MENU",
            NSubmenu => "MAIN_MENU",
            NLogoAnimation => "MAIN_MENU",
            NMainMenu => "MAIN_MENU",
            _ => "UNKNOWN"
        };
    }

    private static string? GetButtonLabel(NButton? button)
    {
        if (button == null)
        {
            return null;
        }

        return button.GetNodeOrNull<MegaLabel>("Label")?.Text ?? button.Name.ToString();
    }

    private static bool TryGetMapScreen(IScreenContext? currentScreen, RunState? runState, out NMapScreen? mapScreen)
    {
        mapScreen = currentScreen as NMapScreen ?? NMapScreen.Instance;
        if (runState == null || currentScreen is not (NMapScreen or NMapRoom))
        {
            return false;
        }

        if (mapScreen == null || !GodotObject.IsInstanceValid(mapScreen))
        {
            return false;
        }

        return mapScreen.IsVisibleInTree() && mapScreen.IsOpen;
    }

    public static DebugNodesPayload BuildDebugNodesPayload()
    {
        var currentScreen = ActiveScreenContext.Instance.GetCurrentScreen();
        var screenTypeName = currentScreen?.GetType().Name ?? "null";

        if (currentScreen is not Node screenNode)
        {
            return new DebugNodesPayload
            {
                current_screen_type = screenTypeName,
                descendant_types = Array.Empty<DebugNodeTypeCount>(),
                card_holders = Array.Empty<DebugCardHolderInfo>(),
                visible_children_types = Array.Empty<string>(),
                event_option_buttons = Array.Empty<DebugEventOptionInfo>(),
                interesting_nodes = Array.Empty<DebugInterestingNodeInfo>()
            };
        }

        // Group all descendants by type name
        var allDescendants = FindDescendants<Node>(screenNode);
        var descendantTypes = allDescendants
            .GroupBy(n => n.GetType().Name)
            .Select(g => new DebugNodeTypeCount { type = g.Key, count = g.Count() })
            .OrderByDescending(x => x.count)
            .ToArray();

        // Collect NCardHolder info (base class covers NGridCardHolder too)
        var cardHolders = FindDescendants<NCardHolder>(screenNode)
            .Select(h => new DebugCardHolderInfo
            {
                type = h.GetType().Name,
                name = h.Name,
                visible = GodotObject.IsInstanceValid(h) && h.IsVisibleInTree(),
                card_model_null = h.CardModel == null,
                global_position_x = (int)h.GlobalPosition.X,
                global_position_y = (int)h.GlobalPosition.Y
            })
            .ToArray();

        // Visible direct children types (CanvasItem has IsVisibleInTree; include non-CanvasItem nodes too)
        var visibleChildrenTypes = screenNode.GetChildren()
            .OfType<Node>()
            .Where(c => GodotObject.IsInstanceValid(c) && (c is not CanvasItem ci || ci.IsVisibleInTree()))
            .Select(c => c.GetType().Name)
            .ToArray();

        return new DebugNodesPayload
        {
            current_screen_type = screenTypeName,
            descendant_types = descendantTypes,
            card_holders = cardHolders,
            visible_children_types = visibleChildrenTypes,
            event_option_buttons = BuildDebugEventOptionInfos(screenNode),
            interesting_nodes = BuildDebugInterestingNodeInfos(screenNode)
        };
    }

    private static DebugEventOptionInfo[] BuildDebugEventOptionInfos(Node screenNode)
    {
        return FindDescendants<NEventOptionButton>(screenNode)
            .Select((button, index) => new DebugEventOptionInfo
            {
                index = index,
                type = button.GetType().Name,
                name = button.Name,
                path = SafeReadString(() => button.GetPath().ToString()),
                visible = GodotObject.IsInstanceValid(button) && button.IsVisibleInTree(),
                global_position_x = (int)button.GlobalPosition.X,
                global_position_y = (int)button.GlobalPosition.Y,
                text = GetDebugNodeText(button),
                member_hits = BuildDebugMemberHits(button, EventDebugMemberCandidates)
            })
            .ToArray();
    }

    private static DebugInterestingNodeInfo[] BuildDebugInterestingNodeInfos(Node screenNode)
    {
        return FindDescendants<Node>(screenNode)
            .Where(node => IsInterestingDebugNode(node))
            .Select(node => new DebugInterestingNodeInfo
            {
                type = node.GetType().Name,
                name = node.Name,
                path = SafeReadString(() => node.GetPath().ToString()),
                visible = GodotObject.IsInstanceValid(node) && (node is not CanvasItem item || item.IsVisibleInTree()),
                text = GetDebugNodeText(node),
                member_hits = BuildDebugMemberHits(node, EventDebugMemberCandidates)
            })
            .Take(80)
            .ToArray();
    }

    private static bool IsInterestingDebugNode(Node node)
    {
        if (!GodotObject.IsInstanceValid(node))
        {
            return false;
        }

        var typeName = node.GetType().Name;
        var nodeName = node.Name.ToString();
        if (DebugInterestingNodeKeywords.Any(keyword =>
                typeName.Contains(keyword, StringComparison.OrdinalIgnoreCase)
                || nodeName.Contains(keyword, StringComparison.OrdinalIgnoreCase)))
        {
            return true;
        }

        return BuildDebugMemberHits(node, EventDebugMemberCandidates).Length > 0;
    }

    private static string[] BuildDebugMemberHits(object target, IEnumerable<string> memberNames)
    {
        var hits = new List<string>();
        foreach (var memberName in memberNames)
        {
            var value = TryGetMemberValue(target, memberName);
            if (value == null)
            {
                continue;
            }

            hits.Add($"{memberName}:{DescribeDebugValue(value)}");
        }

        return hits.Distinct(StringComparer.Ordinal).Take(24).ToArray();
    }

    private static string DescribeDebugValue(object value)
    {
        if (value is CardModel card)
        {
            return $"CardModel({card.Id.Entry}|{EnglishLocResolver.ResolveCardTitle(card)})";
        }

        if (value is PotionModel potion)
        {
            return $"PotionModel({potion.Id.Entry}|{EnglishLocResolver.Resolve(potion.Title)})";
        }

        if (value is RelicModel relic)
        {
            return $"RelicModel({relic.Id.Entry}|{EnglishLocResolver.Resolve(relic.Title)})";
        }

        if (value is Node node)
        {
            return $"Node({node.GetType().Name}|{node.Name})";
        }

        if (value is IEnumerable enumerable and not string)
        {
            var samples = new List<string>();
            foreach (var item in enumerable)
            {
                if (item == null)
                {
                    continue;
                }

                samples.Add(DescribeDebugValue(item));
                if (samples.Count >= 3)
                {
                    break;
                }
            }

            return samples.Count == 0
                ? $"Enumerable({value.GetType().Name})"
                : $"Enumerable({string.Join(", ", samples)})";
        }

        var text = NormalizeEventStructuredText(TryCoerceText(value));
        if (!string.IsNullOrWhiteSpace(text))
        {
            return text.Length > 80 ? text[..80] + "..." : text;
        }

        return value.GetType().Name;
    }

    private static string GetDebugNodeText(Node node)
    {
        var texts = new List<string>();

        foreach (var candidate in new[] { "Text", "Label", "Title", "Description" })
        {
            var value = TryReadCardTextMember(node, candidate);
            var normalized = NormalizeEventStructuredText(value);
            if (!string.IsNullOrWhiteSpace(normalized))
            {
                texts.Add(normalized);
            }
        }

        texts.AddRange(
            FindDescendants<MegaLabel>(node)
                .Select(label => NormalizeEventStructuredText(label.Text))
                .Where(text => !string.IsNullOrWhiteSpace(text)));

        texts.AddRange(
            FindDescendants<MegaRichTextLabel>(node)
                .Select(label => NormalizeEventStructuredText(label.Text))
                .Where(text => !string.IsNullOrWhiteSpace(text)));

        return string.Join(" | ", texts
            .Distinct(StringComparer.Ordinal)
            .Take(4));
    }

    internal static List<T> FindDescendants<T>(Node root) where T : Node
    {
        var found = new List<T>();
        FindDescendantsRecursive(root, found);
        return found;
    }

    private static IReadOnlyList<NGridCardHolder> GetVisibleGridCardHolders(Node root)
    {
        return FindDescendants<NGridCardHolder>(root)
            .Where(node => GodotObject.IsInstanceValid(node) && node.IsVisibleInTree() && node.CardModel != null)
            .OrderBy(node => node.GlobalPosition.Y)
            .ThenBy(node => node.GlobalPosition.X)
            .ToArray();
    }

    private static void FindDescendantsRecursive<T>(Node node, List<T> found) where T : Node
    {
        if (!GodotObject.IsInstanceValid(node))
        {
            return;
        }

        if (node is T typedNode)
        {
            found.Add(typedNode);
        }

        foreach (Node child in node.GetChildren())
        {
            FindDescendantsRecursive(child, found);
        }
    }

    private static string DescribeCrystalSphereTool(CrystalSphereMinigame.CrystalSphereToolType tool)
    {
        return tool switch
        {
            CrystalSphereMinigame.CrystalSphereToolType.Small => "small",
            CrystalSphereMinigame.CrystalSphereToolType.Big => "big",
            _ => "none"
        };
    }

    private static bool CanAdjustAscension(IScreenContext? currentScreen, int delta)
    {
        var screen = GetCharacterSelectScreen(currentScreen);
        if (screen == null)
        {
            return false;
        }

        var lobby = screen.Lobby;
        if (lobby.NetService.Type == NetGameType.Client || lobby.LocalPlayer.isReady)
        {
            return false;
        }

        var nextAscension = lobby.Ascension + delta;
        return nextAscension >= 0 && nextAscension <= lobby.MaxAscension;
    }

    private static IReadOnlyCollection<ulong> GetConnectedPlayerIds(RunState? runState)
    {
        if (runState == null)
        {
            return Array.Empty<ulong>();
        }

        var connectedPlayerIds = RunManager.Instance.RunLobby?.ConnectedPlayerIds;
        if (connectedPlayerIds != null && connectedPlayerIds.Count > 0)
        {
            return connectedPlayerIds;
        }

        return runState.Players.Select(player => player.NetId).ToArray();
    }

    private static string NetIdToString(ulong netId)
    {
        return netId.ToString();
    }
}

internal sealed class GameStatePayload
{
    public int state_version { get; init; }

    public string run_id { get; init; } = "run_unknown";

    public string screen { get; init; } = "UNKNOWN";

    public SessionPayload session { get; init; } = new();

    public bool in_combat { get; init; }

    public int? turn { get; init; }

    public string? combat_type { get; init; }

    public string? boss_stage { get; init; }

    public bool is_final_boss { get; init; }

    public int? act { get; init; }

    public string? boss_encounter_id { get; init; }

    public string? second_boss_encounter_id { get; init; }

    public string[] available_actions { get; init; } = Array.Empty<string>();

    public CombatPayload? combat { get; init; }

    public RunPayload? run { get; init; }

    public MultiplayerPayload? multiplayer { get; init; }

    public MultiplayerLobbyPayload? multiplayer_lobby { get; init; }

    public MapPayload? map { get; init; }

    public SelectionPayload? selection { get; init; }

    public CardsViewPayload? cards_view { get; init; }

    public CharacterSelectPayload? character_select { get; init; }

    public TimelinePayload? timeline { get; init; }

    public ChestPayload? chest { get; init; }

    public EventPayload? @event { get; init; }

    public CrystalSpherePayload? crystal_sphere { get; init; }

    public ShopPayload? shop { get; init; }

    public RestPayload? rest { get; init; }

    public RewardPayload? reward { get; init; }

    public BundlePayload[]? bundles { get; init; }

    public ModalPayload? modal { get; init; }

    public GameOverPayload? game_over { get; init; }

    public object? agent_view { get; init; }
}

internal sealed class SessionPayload
{
    public string mode { get; init; } = "singleplayer";

    public string phase { get; init; } = "menu";

    public string control_scope { get; init; } = "local_player";
}

internal sealed class AvailableActionsPayload
{
    public string screen { get; init; } = "UNKNOWN";

    public ActionDescriptor[] actions { get; init; } = Array.Empty<ActionDescriptor>();
}

internal sealed class CombatPayload
{
    public CombatPlayerPayload player { get; init; } = new();

    public CombatPlayerSummaryPayload[] players { get; init; } = Array.Empty<CombatPlayerSummaryPayload>();

    public CombatHandCardPayload[] hand { get; init; } = Array.Empty<CombatHandCardPayload>();

    public CombatEnemyPayload[] enemies { get; init; } = Array.Empty<CombatEnemyPayload>();
}

internal sealed class RunPayload
{
    public string character_id { get; init; } = string.Empty;

    public string character_name { get; init; } = string.Empty;

    public int ascension { get; init; }

    public AscensionEffectPayload[] ascension_effects { get; init; } = Array.Empty<AscensionEffectPayload>();

    public int floor { get; init; }

    public int current_hp { get; init; }

    public int max_hp { get; init; }

    public int gold { get; init; }

    public int max_energy { get; init; }

    public int base_orb_slots { get; init; }

    public DeckCardPayload[] deck { get; init; } = Array.Empty<DeckCardPayload>();

    public RunRelicPayload[] relics { get; init; } = Array.Empty<RunRelicPayload>();

    public RunPlayerSummaryPayload[] players { get; init; } = Array.Empty<RunPlayerSummaryPayload>();

    public RunPotionPayload[] potions { get; init; } = Array.Empty<RunPotionPayload>();
}

internal sealed class AscensionEffectPayload
{
    public string id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;
}

internal sealed class MultiplayerPayload
{
    public bool is_multiplayer { get; init; }

    public string net_game_type { get; init; } = string.Empty;

    public string? local_player_id { get; init; }

    public int player_count { get; init; }

    public string[] connected_player_ids { get; init; } = Array.Empty<string>();
}

internal sealed class MultiplayerLobbyPayload
{
    public string net_game_type { get; init; } = string.Empty;

    public string join_host { get; init; } = "127.0.0.1";

    public int join_port { get; init; }

    public string? local_net_id_hint { get; init; }

    public bool has_lobby { get; init; }

    public bool is_host { get; init; }

    public bool is_client { get; init; }

    public bool local_ready { get; init; }

    public bool can_host { get; init; }

    public bool can_join { get; init; }

    public bool can_ready { get; init; }

    public bool can_disconnect { get; init; }

    public bool can_unready { get; init; }

    public string? selected_character_id { get; init; }

    public int player_count { get; init; }

    public int max_players { get; init; }

    public CharacterSelectPlayerPayload[] players { get; init; } = Array.Empty<CharacterSelectPlayerPayload>();

    public CharacterSelectOptionPayload[] characters { get; init; } = Array.Empty<CharacterSelectOptionPayload>();
}

internal sealed class MapPayload
{
    public MapCoordPayload? current_node { get; init; }

    public bool is_travel_enabled { get; init; }

    public bool is_traveling { get; init; }

    public int map_generation_count { get; init; }

    public int rows { get; init; }

    public int cols { get; init; }

    public MapCoordPayload? starting_node { get; init; }

    public MapCoordPayload? boss_node { get; init; }

    public MapCoordPayload? second_boss_node { get; init; }

    public MapGraphNodePayload[] nodes { get; init; } = Array.Empty<MapGraphNodePayload>();

    public MapNodePayload[] available_nodes { get; init; } = Array.Empty<MapNodePayload>();
}

internal sealed class SelectionPayload
{
    public string kind { get; init; } = string.Empty;

    public string prompt { get; init; } = string.Empty;

    public int min_select { get; init; } = 1;

    public int max_select { get; init; } = 1;

    public int selected_count { get; init; }

    public bool requires_confirmation { get; init; }

    public bool can_confirm { get; init; }

    public SelectionCardPayload[] cards { get; init; } = Array.Empty<SelectionCardPayload>();

    public SelectionCardPayload[] selected_cards { get; init; } = Array.Empty<SelectionCardPayload>();

    public SelectionCardPayload[] selectable_cards { get; init; } = Array.Empty<SelectionCardPayload>();

    public SelectionCardPayload[] preview_cards { get; init; } = Array.Empty<SelectionCardPayload>();
}

internal sealed class CardsViewPayload
{
    public string title { get; init; } = string.Empty;

    public SelectionCardPayload[] cards { get; init; } = Array.Empty<SelectionCardPayload>();
}

internal readonly record struct CombatHandSelectionMetadata(
    int MinSelect,
    int MaxSelect,
    int SelectedCount,
    bool RequiresConfirmation,
    bool CanConfirm);

internal sealed class CharacterSelectPayload
{
    public string? selected_character_id { get; init; }

    public bool is_multiplayer { get; init; }

    public string net_game_type { get; init; } = string.Empty;

    public bool can_embark { get; init; }

    public bool can_unready { get; init; }

    public bool can_increase_ascension { get; init; }

    public bool can_decrease_ascension { get; init; }

    public bool local_ready { get; init; }

    public bool is_waiting_for_players { get; init; }

    public int player_count { get; init; }

    public int max_players { get; init; }

    public int ascension { get; init; }

    public int max_ascension { get; init; }

    public string? seed { get; init; }

    public string[] modifier_ids { get; init; } = Array.Empty<string>();

    public CharacterSelectPlayerPayload[] players { get; init; } = Array.Empty<CharacterSelectPlayerPayload>();

    public CharacterSelectOptionPayload[] characters { get; init; } = Array.Empty<CharacterSelectOptionPayload>();
}

internal sealed class CharacterSelectPlayerPayload
{
    public string player_id { get; init; } = string.Empty;

    public int slot_index { get; init; }

    public bool is_local { get; init; }

    public string? character_id { get; init; }

    public string? character_name { get; init; }

    public bool is_ready { get; init; }

    public int max_multiplayer_ascension_unlocked { get; init; }
}

internal sealed class CharacterSelectOptionPayload
{
    public int index { get; init; }

    public string character_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool is_locked { get; init; }

    public bool is_selected { get; init; }

    public bool is_random { get; init; }
}

internal sealed class TimelinePayload
{
    public bool back_enabled { get; init; }

    public bool inspect_open { get; init; }

    public bool unlock_screen_open { get; init; }

    public bool can_choose_epoch { get; init; }

    public bool can_confirm_overlay { get; init; }

    public TimelineSlotPayload[] slots { get; init; } = Array.Empty<TimelineSlotPayload>();
}

internal sealed class TimelineSlotPayload
{
    public int index { get; init; }

    public string epoch_id { get; init; } = string.Empty;

    public string title { get; init; } = string.Empty;

    public string state { get; init; } = string.Empty;

    public bool is_actionable { get; init; }
}

internal sealed class ChestPayload
{
    public bool is_opened { get; init; }

    public bool has_relic_been_claimed { get; init; }

    public ChestRelicOptionPayload[] relic_options { get; init; } = Array.Empty<ChestRelicOptionPayload>();
}

internal sealed class ChestRelicOptionPayload
{
    public int index { get; init; }

    public string relic_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public string rarity { get; init; } = string.Empty;
}

internal sealed class EventCardInfo
{
    public string name { get; init; } = string.Empty;

    public int cost { get; init; }

    public string type { get; init; } = string.Empty;

    public string rules_text { get; init; } = string.Empty;

    public bool is_upgraded { get; init; }
}

internal sealed class EventRelicInfo
{
    public string name { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;

    public string rarity { get; init; } = string.Empty;
}

internal sealed class EventPotionInfo
{
    public string name { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;

    public string type { get; init; } = string.Empty;
}

internal sealed class EventPayload
{
    public string event_id { get; init; } = string.Empty;

    public string title { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;

    public bool is_finished { get; init; }

    public EventOptionPayload[] options { get; init; } = Array.Empty<EventOptionPayload>();
}

internal sealed class EventOptionPayload
{
    public int index { get; init; }

    public string text_key { get; init; } = string.Empty;

    public string title { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;

    public bool is_locked { get; init; }

    public bool is_proceed { get; init; }

    public bool will_kill_player { get; init; }

    public bool has_relic_preview { get; init; }

    public string effect_description { get; init; } = string.Empty;

    public int? hp_cost { get; init; }

    public int? gold_cost { get; init; }

    public EventCardInfo[] cards_offered { get; init; } = Array.Empty<EventCardInfo>();

    public EventRelicInfo[] relics_offered { get; init; } = Array.Empty<EventRelicInfo>();

    public EventPotionInfo[] potions_offered { get; init; } = Array.Empty<EventPotionInfo>();

    public string[] curses_risk { get; init; } = Array.Empty<string>();
}

internal enum CrystalSphereActionType
{
    SelectSmallTool,
    SelectBigTool,
    ClickCell,
    Proceed
}

internal sealed class CrystalSphereActionOption
{
    public int index { get; set; }

    public string text_key { get; init; } = string.Empty;

    public string title { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;

    public bool is_proceed { get; init; }

    public CrystalSphereActionType action_type { get; init; }

    public NClickableControl control { get; init; } = null!;

    public int? cell_x { get; init; }

    public int? cell_y { get; init; }
}

internal sealed class CrystalSpherePayload
{
    public int grid_width { get; init; }

    public int grid_height { get; init; }

    public string tool { get; init; } = "none";

    public bool can_use_big_tool { get; init; }

    public bool can_use_small_tool { get; init; }

    public int divinations_left { get; init; }

    public string? divinations_left_text { get; init; }

    public string? instructions_title { get; init; }

    public string? instructions_description { get; init; }

    public bool can_proceed { get; init; }

    public bool is_finished { get; init; }

    public CrystalSphereCellPayload[] cells { get; init; } = Array.Empty<CrystalSphereCellPayload>();

    public CrystalSphereCellRefPayload[] clickable_cells { get; init; } = Array.Empty<CrystalSphereCellRefPayload>();

    public CrystalSphereRevealedItemPayload[] revealed_items { get; init; } = Array.Empty<CrystalSphereRevealedItemPayload>();
}

internal sealed class CrystalSphereCellPayload
{
    public int x { get; init; }

    public int y { get; init; }

    public bool is_hidden { get; init; }

    public bool is_clickable { get; init; }

    public string? item_type { get; init; }

    public bool? is_good { get; init; }
}

internal sealed class CrystalSphereCellRefPayload
{
    public int x { get; init; }

    public int y { get; init; }
}

internal sealed class CrystalSphereRevealedItemPayload
{
    public int x { get; init; }

    public int y { get; init; }

    public string item_type { get; init; } = "unknown";

    public bool is_good { get; init; }
}

internal sealed class RestPayload
{
    public RestOptionPayload[] options { get; init; } = Array.Empty<RestOptionPayload>();
}

internal sealed class RestOptionPayload
{
    public int index { get; init; }

    public string option_id { get; init; } = string.Empty;

    public string title { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;

    public bool is_enabled { get; init; }
}

internal sealed class ShopPayload
{
    public bool is_open { get; init; }

    public bool can_open { get; init; }

    public bool can_close { get; init; }

    public ShopCardPayload[] cards { get; init; } = Array.Empty<ShopCardPayload>();

    public ShopRelicPayload[] relics { get; init; } = Array.Empty<ShopRelicPayload>();

    public ShopPotionPayload[] potions { get; init; } = Array.Empty<ShopPotionPayload>();

    public ShopCardRemovalPayload? card_removal { get; init; }
}

internal sealed class ShopCardPayload
{
    public int index { get; init; }

    public string category { get; init; } = string.Empty;

    public string card_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;

    public string rarity { get; init; } = string.Empty;

    public bool costs_x { get; init; }

    public bool star_costs_x { get; init; }

    public int energy_cost { get; init; }

    public int star_cost { get; init; }

    public string rules_text { get; init; } = string.Empty;

    public string resolved_rules_text { get; init; } = string.Empty;

    public CardDynamicValuePayload[] dynamic_values { get; init; } = Array.Empty<CardDynamicValuePayload>();

    public int price { get; init; }

    public bool on_sale { get; init; }

    public bool is_stocked { get; init; }

    public bool enough_gold { get; init; }

    public GeneratedCardPayload[] generated_cards { get; init; } = Array.Empty<GeneratedCardPayload>();
}

internal sealed class ShopRelicPayload
{
    public int index { get; init; }

    public string relic_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public string? description { get; init; }

    public string rarity { get; init; } = string.Empty;

    public int price { get; init; }

    public bool is_stocked { get; init; }

    public bool enough_gold { get; init; }
}

internal sealed class ShopPotionPayload
{
    public int index { get; init; }

    public string? potion_id { get; init; }

    public string? name { get; init; }

    public string? description { get; init; }

    public string? rarity { get; init; }

    public string? usage { get; init; }

    public int price { get; init; }

    public bool is_stocked { get; init; }

    public bool enough_gold { get; init; }
}

internal sealed class ShopCardRemovalPayload
{
    public int price { get; init; }

    public bool available { get; init; }

    public bool used { get; init; }

    public bool enough_gold { get; init; }
}

internal sealed class MapCoordPayload
{
    public int row { get; init; }

    public int col { get; init; }
}

internal sealed class MapNodePayload
{
    public int index { get; init; }

    public int row { get; init; }

    public int col { get; init; }

    public string node_type { get; init; } = string.Empty;

    public string state { get; init; } = string.Empty;
}

internal sealed class MapGraphNodePayload
{
    public int row { get; init; }

    public int col { get; init; }

    public string node_type { get; init; } = string.Empty;

    public string state { get; init; } = string.Empty;

    public bool visited { get; init; }

    public bool is_current { get; init; }

    public bool is_available { get; init; }

    public bool is_start { get; init; }

    public bool is_boss { get; init; }

    public bool is_second_boss { get; init; }

    public MapCoordPayload[] parents { get; init; } = Array.Empty<MapCoordPayload>();

    public MapCoordPayload[] children { get; init; } = Array.Empty<MapCoordPayload>();
}

internal sealed class CombatPlayerPayload
{
    public int current_hp { get; init; }

    public int max_hp { get; init; }

    public int block { get; init; }

    public int energy { get; init; }

    public int stars { get; init; }

    public int focus { get; init; }

    public CombatPowerPayload[] powers { get; init; } = Array.Empty<CombatPowerPayload>();

    public int base_orb_slots { get; init; }

    public int orb_capacity { get; init; }

    public int empty_orb_slots { get; init; }

    public CombatOrbPayload[] orbs { get; init; } = Array.Empty<CombatOrbPayload>();

    public PileCardPayload[] draw_cards { get; init; } = Array.Empty<PileCardPayload>();

    public PileCardPayload[] discard_cards { get; init; } = Array.Empty<PileCardPayload>();

    public PileCardPayload[] exhaust_cards { get; init; } = Array.Empty<PileCardPayload>();
}

internal sealed class PileCardPayload
{
    public string card_id { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;
}

internal sealed class CombatPlayerSummaryPayload
{
    public string player_id { get; init; } = string.Empty;

    public int slot_index { get; init; }

    public bool is_local { get; init; }

    public bool is_connected { get; init; }

    public string character_id { get; init; } = string.Empty;

    public string character_name { get; init; } = string.Empty;

    public int current_hp { get; init; }

    public int max_hp { get; init; }

    public int block { get; init; }

    public int energy { get; init; }

    public int stars { get; init; }

    public int focus { get; init; }

    public bool is_alive { get; init; }
}

internal sealed class RunPlayerSummaryPayload
{
    public string player_id { get; init; } = string.Empty;

    public int slot_index { get; init; }

    public bool is_local { get; init; }

    public bool is_connected { get; init; }

    public string character_id { get; init; } = string.Empty;

    public string character_name { get; init; } = string.Empty;

    public int current_hp { get; init; }

    public int max_hp { get; init; }

    public int gold { get; init; }

    public bool is_alive { get; init; }
}

internal sealed class CombatOrbPayload
{
    public int slot_index { get; init; }

    public string orb_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public decimal passive_value { get; init; }

    public decimal evoke_value { get; init; }

    public bool is_front { get; init; }
}

internal sealed class CombatHandCardPayload
{
    public int index { get; init; }

    public string card_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;

    public string target_type { get; init; } = string.Empty;

    public bool requires_target { get; init; }

    public string? target_index_space { get; init; }

    public int[] valid_target_indices { get; init; } = Array.Empty<int>();

    public bool costs_x { get; init; }

    public bool star_costs_x { get; init; }

    public int energy_cost { get; init; }

    public int star_cost { get; init; }

    public string rules_text { get; init; } = string.Empty;

    public string resolved_rules_text { get; init; } = string.Empty;

    public CardDynamicValuePayload[] dynamic_values { get; init; } = Array.Empty<CardDynamicValuePayload>();

    public bool playable { get; init; }

    public string? unplayable_reason { get; init; }

    // Structured card-level preview values (untargeted, player-side modifiers only)
    public int? damage { get; init; }

    public int? block { get; init; }

    public int? hits { get; init; }

    public int? total_damage { get; init; }

    // Replay: additional auto-plays (e.g. Glam enchantment gives Replay 1)
    public int? replay { get; init; }

    public TargetPreviewPayload[]? target_previews { get; init; }

    // Cards this card generates mid-play (e.g. Blade of Ink -> Inky Shiv,
    // Hidden Daggers -> Shiv, Grave Warden -> Soul). Sourced from the same
    // CardModel.HoverTips path the game UI uses for long-press previews,
    // so upgrade-aware variants (Shiv vs Shiv+) are already correct.
    public GeneratedCardPayload[] generated_cards { get; init; } = Array.Empty<GeneratedCardPayload>();
}

internal sealed class GeneratedCardPayload
{
    public string card_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;

    public int energy_cost { get; init; }

    public string rules_text { get; init; } = string.Empty;

    public string[] keywords { get; init; } = Array.Empty<string>();
}

internal sealed class TargetPreviewPayload
{
    public int target_index { get; init; }

    public int damage { get; init; }

    public int hits { get; init; } = 1;

    public int total_damage { get; init; }
}

internal sealed class CombatEnemyPayload
{
    public int index { get; init; }

    public string enemy_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public int current_hp { get; init; }

    public int max_hp { get; init; }

    public int block { get; init; }

    public bool is_alive { get; init; }

    public bool is_hittable { get; init; }

    public CombatPowerPayload[] powers { get; init; } = Array.Empty<CombatPowerPayload>();

    public string? intent { get; init; }

    public string? move_id { get; init; }

    public CombatEnemyIntentPayload[] intents { get; init; } = Array.Empty<CombatEnemyIntentPayload>();
}

internal sealed class CombatEnemyIntentPayload
{
    public int index { get; init; }

    public string intent_type { get; init; } = string.Empty;

    public string? label { get; init; }

    public int? damage { get; init; }

    public int? hits { get; init; }

    public int? total_damage { get; init; }

    public int? status_card_count { get; init; }
}

internal sealed class CombatPowerPayload
{
    public int index { get; init; }

    public string power_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public int? amount { get; init; }

    public string description { get; init; } = string.Empty;

    public bool is_debuff { get; init; }
}

internal sealed class RewardPayload
{
    public bool pending_card_choice { get; init; }

    public bool can_proceed { get; init; }

    public RewardOptionPayload[] rewards { get; init; } = Array.Empty<RewardOptionPayload>();

    public RewardCardOptionPayload[] card_options { get; init; } = Array.Empty<RewardCardOptionPayload>();

    public RewardAlternativePayload[] alternatives { get; init; } = Array.Empty<RewardAlternativePayload>();
}

internal sealed class ModalPayload
{
    public string type_name { get; init; } = string.Empty;

    public string? underlying_screen { get; init; }

    public bool can_confirm { get; init; }

    public bool can_dismiss { get; init; }

    public string? confirm_label { get; init; }

    public string? dismiss_label { get; init; }
}

internal sealed class GameOverPayload
{
    public bool is_victory { get; init; }

    public int? floor { get; init; }

    public string? character_id { get; init; }

    public bool can_continue { get; init; }

    public bool can_return_to_main_menu { get; init; }

    public bool showing_summary { get; init; }
}

internal sealed class RewardOptionPayload
{
    public int index { get; init; }

    public string reward_type { get; init; } = string.Empty;

    public string description { get; init; } = string.Empty;

    public bool claimable { get; init; }
}

internal sealed class RewardCardOptionPayload
{
    public int index { get; init; }

    public string card_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;

    public string rarity { get; init; } = string.Empty;

    public int energy_cost { get; init; }

    public bool costs_x { get; init; }

    public string rules_text { get; init; } = string.Empty;

    public string resolved_rules_text { get; init; } = string.Empty;

    public CardDynamicValuePayload[] dynamic_values { get; init; } = Array.Empty<CardDynamicValuePayload>();

    public GeneratedCardPayload[] generated_cards { get; init; } = Array.Empty<GeneratedCardPayload>();
}

internal sealed class RewardAlternativePayload
{
    public int index { get; init; }

    public string label { get; init; } = string.Empty;
}

internal sealed class BundlePayload
{
    public int index { get; init; }

    public BundleCardPayload[] cards { get; init; } = Array.Empty<BundleCardPayload>();
}

internal sealed class BundleCardPayload
{
    public int index { get; init; }

    public string card_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;

    public string rarity { get; init; } = string.Empty;

    public int energy_cost { get; init; }

    public bool costs_x { get; init; }

    public string rules_text { get; init; } = string.Empty;

    public string resolved_rules_text { get; init; } = string.Empty;

    public CardDynamicValuePayload[] dynamic_values { get; init; } = Array.Empty<CardDynamicValuePayload>();
}

internal sealed class DeckCardPayload
{
    public int index { get; init; }

    public string card_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;

    public string rarity { get; init; } = string.Empty;

    public bool costs_x { get; init; }

    public bool star_costs_x { get; init; }

    public int energy_cost { get; init; }

    public int star_cost { get; init; }

    public string rules_text { get; init; } = string.Empty;

    public string resolved_rules_text { get; init; } = string.Empty;

    public CardDynamicValuePayload[] dynamic_values { get; init; } = Array.Empty<CardDynamicValuePayload>();

    public string? enchantment_id { get; init; }

    public string? enchantment_name { get; init; }
}

internal sealed class SelectionCardPayload
{
    public int index { get; init; }

    public string stable_id { get; init; } = string.Empty;

    public string card_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool upgraded { get; init; }

    public string card_type { get; init; } = string.Empty;

    public string rarity { get; init; } = string.Empty;

    public bool costs_x { get; init; }

    public bool star_costs_x { get; init; }

    public int energy_cost { get; init; }

    public int star_cost { get; init; }

    public string rules_text { get; init; } = string.Empty;

    public string resolved_rules_text { get; init; } = string.Empty;

    public CardDynamicValuePayload[] dynamic_values { get; init; } = Array.Empty<CardDynamicValuePayload>();

    public bool is_selected { get; init; }

    public bool is_selectable { get; init; } = true;

    /// <summary>
    /// Upgrade preview: the card's description text after upgrading (BBCode).
    /// Only populated for non-upgraded cards on the Smith (deck_upgrade_select) screen.
    /// </summary>
    [System.Text.Json.Serialization.JsonIgnore(Condition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull)]
    public string? upgrade_preview_description { get; init; }

    /// <summary>
    /// Upgrade preview: the card's energy cost after upgrading.
    /// Only populated when the upgrade changes the cost.
    /// </summary>
    [System.Text.Json.Serialization.JsonIgnore(Condition = System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull)]
    public int? upgrade_preview_cost { get; init; }
}

internal sealed class CardDynamicValuePayload
{
    public string name { get; init; } = string.Empty;

    public int base_value { get; init; }

    public int current_value { get; init; }

    public int enchanted_value { get; init; }

    public bool is_modified { get; init; }

    public bool was_just_upgraded { get; init; }
}

internal sealed class RunRelicPayload
{
    public int index { get; init; }

    public string relic_id { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public string? description { get; init; }

    public int? stack { get; init; }

    public bool is_melted { get; init; }

    /// <summary>
    /// Current progress value for counter relics (ShowCounter == true), e.g. Nunchaku
    /// tracks attacks played toward the next Energy trigger. Null for non-counter relics.
    /// </summary>
    public int? counter { get; init; }
}

internal sealed class RunPotionPayload
{
    public int index { get; init; }

    public string? potion_id { get; init; }

    public string? name { get; init; }

    public string? description { get; init; }

    public string? rarity { get; init; }

    public bool occupied { get; init; }

    public string? usage { get; init; }

    public string? target_type { get; init; }

    public bool is_queued { get; init; }

    public bool requires_target { get; init; }

    public string? target_index_space { get; init; }

    public int[] valid_target_indices { get; init; } = Array.Empty<int>();

    public bool can_use { get; init; }

    public bool can_discard { get; init; }
}

internal readonly record struct AgentCardDescriptor(
    string name,
    bool upgraded,
    int energy_cost,
    int star_cost,
    bool costs_x,
    bool star_costs_x,
    string rules_text,
    string[] keywords,
    string[] mods)
{
    public string GroupKey =>
        string.Join(
            "\u001f",
            name,
            upgraded ? "1" : "0",
            energy_cost.ToString(),
            star_cost.ToString(),
            costs_x ? "1" : "0",
            star_costs_x ? "1" : "0",
            rules_text,
            string.Join("\u001e", mods));
}

internal sealed class ActionDescriptor
{
    public string name { get; init; } = string.Empty;

    public bool requires_target { get; init; }

    public bool requires_index { get; init; }
}

internal sealed class DebugNodesPayload
{
    public string current_screen_type { get; init; } = string.Empty;

    public DebugNodeTypeCount[] descendant_types { get; init; } = Array.Empty<DebugNodeTypeCount>();

    public DebugCardHolderInfo[] card_holders { get; init; } = Array.Empty<DebugCardHolderInfo>();

    public string[] visible_children_types { get; init; } = Array.Empty<string>();

    public DebugEventOptionInfo[] event_option_buttons { get; init; } = Array.Empty<DebugEventOptionInfo>();

    public DebugInterestingNodeInfo[] interesting_nodes { get; init; } = Array.Empty<DebugInterestingNodeInfo>();
}

internal sealed class DebugNodeTypeCount
{
    public string type { get; init; } = string.Empty;

    public int count { get; init; }
}

internal sealed class DebugCardHolderInfo
{
    public string type { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public bool visible { get; init; }

    public bool card_model_null { get; init; }

    public int global_position_x { get; init; }

    public int global_position_y { get; init; }
}

internal sealed class DebugEventOptionInfo
{
    public int index { get; init; }

    public string type { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public string path { get; init; } = string.Empty;

    public bool visible { get; init; }

    public int global_position_x { get; init; }

    public int global_position_y { get; init; }

    public string text { get; init; } = string.Empty;

    public string[] member_hits { get; init; } = Array.Empty<string>();
}

internal sealed class DebugInterestingNodeInfo
{
    public string type { get; init; } = string.Empty;

    public string name { get; init; } = string.Empty;

    public string path { get; init; } = string.Empty;

    public bool visible { get; init; }

    public string text { get; init; } = string.Empty;

    public string[] member_hits { get; init; } = Array.Empty<string>();
}
