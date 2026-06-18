using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using Godot;
using MegaCrit.Sts2.Core.Localization;
using MegaCrit.Sts2.Core.Logging;
using MegaCrit.Sts2.Core.Models;

namespace STS2AIAgent.Game;

/// <summary>
/// Loads English localization tables directly from `res://localization/eng/*.json` and
/// resolves any LocString to its English text, regardless of the player's active locale.
///
/// This lets the mod emit English over the HTTP API while the player's UI continues to
/// run in whichever of the 14 supported locales they chose. The active locale state in
/// LocManager is never touched.
///
/// For LocStrings carrying dynamic variables (e.g. card descriptions with
/// `{Damage:diff()}`), we reuse LocManager's SmartFormatter via reflection with the
/// English CultureInfo. If reflection fails, we return the raw template as fallback.
///
/// For missing entries (e.g. modded content without an English translation), we return
/// the LocString's raw entry key — locale-blind by design, so the active locale never
/// leaks into the HTTP payload.
/// </summary>
internal static class EnglishLocResolver
{
    private const string LogPrefix = "[STS2AIAgent.EnglishLocResolver]";

    private static readonly string[] _tableFiles =
    {
        "achievements", "acts", "afflictions", "ancients", "ascension", "badges",
        "bestiary", "card_keywords", "card_library", "card_reward_ui",
        "card_selection", "cards", "characters", "combat_messages", "credits",
        "enchantments", "encounters", "epochs", "eras", "events", "extensions",
        "ftues", "game_modes", "game_over_screen", "gameplay_ui",
        "inspect_relic_screen", "intents", "main_menu_ui", "map", "merchant_room",
        "modifiers", "monsters", "orbs", "potion_lab", "potions", "powers",
        "relic_collection", "relics", "rest_site_ui", "rich_presence",
        "run_history", "settings_ui", "static_hover_tips", "stats_screen",
        "timeline", "vfx",
    };

    private static readonly CultureInfo _enCulture = CultureInfo.GetCultureInfo("en");

    private static Dictionary<string, Dictionary<string, string>>? _tables;
    private static Dictionary<string, LocTable>? _engLocTables;
    private static FieldInfo? _locManagerTablesField;
    private static MethodInfo? _locManagerSetCultureInfo;
    private static MethodInfo? _locManagerSetStringComparer;
    private static StringComparer? _enStringComparer;
    private static bool _initialized;

    // Active-locale -> English entity name map. Built once at Initialize() by
    // joining English entry values with the live LocManager tables for the
    // player's chosen locale. Used by ScrubLocaleNames to strip residual
    // active-locale strings out of dynamic-var-substituted descriptions
    // (e.g. relic transform descriptions where {Card.Title} was already
    // pre-formatted into Chinese before WithEnglishTables could intercept).
    private static Dictionary<string, string>? _activeToEnglish;
    private static Regex? _activeNameRe;

    // Categories to include in the active->English reverse map. Each entry
    // is (table_name, key_suffix) — the key in the table that holds the
    // canonical user-visible name for that entity type.
    private static readonly (string table, string suffix)[] _scrubCategories =
    {
        ("cards", ".title"),
        ("relics", ".title"),
        ("potions", ".title"),
        ("monsters", ".name"),
        ("powers", ".title"),
        ("enchantments", ".title"),
        ("afflictions", ".title"),
        ("orbs", ".title"),
        ("characters", ".title"),
    };

    public static bool IsReady => _initialized && _tables != null;

    public static void Initialize()
    {
        if (_initialized) return;
        _initialized = true;

        try
        {
            _tables = LoadTables();
            Log.Info($"{LogPrefix} Loaded {_tables.Count} English localization tables.");
        }
        catch (Exception ex)
        {
            Log.Error($"{LogPrefix} Failed to load English tables: {ex}");
            _tables = new Dictionary<string, Dictionary<string, string>>();
        }

        try
        {
            BindLocManagerInternals();
        }
        catch (Exception ex)
        {
            Log.Warn($"{LogPrefix} Failed to bind LocManager internals via reflection: {ex.Message}. WithEnglishTables() will be a no-op.");
        }

        try
        {
            BuildActiveLocaleScrubMap();
        }
        catch (Exception ex)
        {
            Log.Warn($"{LogPrefix} Failed to build active-locale scrub map: {ex.Message}. ScrubLocaleNames() will be a no-op.");
        }
    }

    private static void BuildActiveLocaleScrubMap()
    {
        if (_tables == null) return;
        var locManager = LocManager.Instance;
        if (locManager == null) return;

        // Skip the scrub when active locale already is English -- the map
        // would be identity and the regex pass would just waste cycles.
        if (string.Equals(locManager.Language, "eng", StringComparison.OrdinalIgnoreCase))
        {
            _activeToEnglish = null;
            _activeNameRe = null;
            return;
        }

        var map = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var (tableName, suffix) in _scrubCategories)
        {
            if (!_tables.TryGetValue(tableName, out var engTable)) continue;

            LocTable activeTable;
            try { activeTable = locManager.GetTable(tableName); }
            catch { continue; }

            foreach (var pair in engTable)
            {
                var key = pair.Key;
                var engValue = pair.Value;
                if (string.IsNullOrEmpty(key) || string.IsNullOrEmpty(engValue)) continue;
                if (!key.EndsWith(suffix, StringComparison.Ordinal)) continue;
                if (!activeTable.HasEntry(key)) continue;

                string activeValue;
                try { activeValue = activeTable.GetRawText(key); }
                catch { continue; }
                if (string.IsNullOrEmpty(activeValue)) continue;
                if (string.Equals(activeValue, engValue, StringComparison.Ordinal)) continue;

                // First-write wins so longer same-value collisions don't override
                // a prior shorter mapping.
                if (!map.ContainsKey(activeValue))
                    map[activeValue] = engValue;
            }
        }

        if (map.Count == 0)
        {
            _activeToEnglish = null;
            _activeNameRe = null;
            return;
        }

        // Build a longest-first alternation regex so multi-character matches
        // (e.g. "战斗好伙伴V1.0") win over substrings ("战斗").
        var sortedKeys = map.Keys
            .OrderByDescending(k => k.Length)
            .ThenBy(k => k, StringComparer.Ordinal)
            .ToArray();
        var pattern = string.Join("|", sortedKeys.Select(Regex.Escape));
        _activeNameRe = new Regex(pattern, RegexOptions.Compiled);
        _activeToEnglish = map;

        Log.Info($"{LogPrefix} Active-locale scrub map built: {map.Count} {locManager.Language}->English entity names.");
    }

    /// <summary>
    /// Replaces any active-locale entity names embedded in <paramref name="text"/>
    /// with their English equivalents. Used to clean up dynamic-var-substituted
    /// descriptions where {Card1.Title} got pre-formatted into the player's locale
    /// before we could intercept (LocString.cs:122 Add(string, LocString) eagerly
    /// formats). Returns the input unchanged when the active locale is English or
    /// the scrub map could not be built.
    /// </summary>
    public static string ScrubLocaleNames(string? text)
    {
        if (string.IsNullOrEmpty(text)) return text ?? string.Empty;
        if (_activeNameRe == null || _activeToEnglish == null) return text!;
        return _activeNameRe.Replace(text!, m =>
            _activeToEnglish.TryGetValue(m.Value, out var en) ? en : m.Value);
    }

    private static Dictionary<string, Dictionary<string, string>> LoadTables()
    {
        var tables = new Dictionary<string, Dictionary<string, string>>(_tableFiles.Length);
        foreach (var name in _tableFiles)
        {
            var path = $"res://localization/eng/{name}.json";
            using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
            if (f == null) continue;
            var json = f.GetAsText();
            if (string.IsNullOrWhiteSpace(json)) continue;
            try
            {
                var dict = JsonSerializer.Deserialize<Dictionary<string, string>>(json);
                if (dict != null) tables[name] = dict;
            }
            catch (JsonException ex)
            {
                Log.Warn($"{LogPrefix} Failed to parse {path}: {ex.Message}");
            }
        }
        return tables;
    }

    private static void BindLocManagerInternals()
    {
        if (_tables == null) return;

        // Field: LocManager._tables — swapped to English during WithEnglishTables.
        _locManagerTablesField = typeof(LocManager).GetField(
            "_tables",
            BindingFlags.NonPublic | BindingFlags.Instance);
        if (_locManagerTablesField == null) return;

        // Property setters: LocManager.CultureInfo and StringComparer (private
        // setter on auto-property). We swap these so SmartFormat's plural rules
        // and number formatting use English while we resolve.
        _locManagerSetCultureInfo = typeof(LocManager)
            .GetProperty("CultureInfo")?.GetSetMethod(nonPublic: true);
        _locManagerSetStringComparer = typeof(LocManager)
            .GetProperty("StringComparer")?.GetSetMethod(nonPublic: true);
        _enStringComparer = StringComparer.Create(_enCulture, ignoreCase: false);

        // Build LocTable instances from the raw English JSON dicts. Reuses the
        // public LocTable(name, data, fallback) constructor so the format matches
        // exactly what the game's own LoadTablesFromPath would produce.
        var engLocTables = new Dictionary<string, LocTable>(_tables.Count);
        foreach (var (name, data) in _tables)
        {
            engLocTables[name] = new LocTable(name, new Dictionary<string, string>(data));
        }
        _engLocTables = engLocTables;
    }

    /// <summary>
    /// Runs <paramref name="action"/> with LocManager._tables temporarily swapped to
    /// the English tables, so any call to LocString.GetFormattedText() or
    /// CardModel.GetDescriptionForPile(...) inside the action resolves against
    /// English templates regardless of the player's active locale.
    ///
    /// MUST be called from the game thread (via GameThread.InvokeAsync) so that no
    /// concurrent UI render observes the swapped tables.
    /// </summary>
    public static T WithEnglishTables<T>(Func<T> action)
    {
        if (action == null) throw new ArgumentNullException(nameof(action));
        if (_locManagerTablesField == null || _engLocTables == null
            || LocManager.Instance == null)
        {
            return action();
        }

        var instance = LocManager.Instance;
        var savedTables = _locManagerTablesField.GetValue(instance);
        var savedCulture = instance.CultureInfo;
        var savedComparer = instance.StringComparer;
        try
        {
            _locManagerTablesField.SetValue(instance, _engLocTables);
            // Also swap CultureInfo + StringComparer so SmartFormat's plural
            // rules and number formatting follow English. Without this, e.g.
            // {Amount:plural:a card|N cards} renders the singular form for
            // any locale that has only one plural form (incl. Chinese).
            _locManagerSetCultureInfo?.Invoke(instance, new object[] { _enCulture });
            if (_enStringComparer != null)
                _locManagerSetStringComparer?.Invoke(instance, new object[] { _enStringComparer });
            return action();
        }
        finally
        {
            _locManagerTablesField.SetValue(instance, savedTables);
            _locManagerSetCultureInfo?.Invoke(instance, new object[] { savedCulture });
            if (savedComparer != null)
                _locManagerSetStringComparer?.Invoke(instance, new object[] { savedComparer });
        }
    }

    /// <summary>
    /// Returns the raw English text for (table, key), or null if missing.
    /// </summary>
    public static string? GetRaw(string? table, string? key)
    {
        if (_tables == null || string.IsNullOrEmpty(table) || string.IsNullOrEmpty(key))
            return null;
        if (!_tables.TryGetValue(table!, out var t)) return null;
        return t.TryGetValue(key!, out var v) ? v : null;
    }

    /// <summary>
    /// Returns the English title of a card, including the upgrade suffix that
    /// CardModel.Title appends in the active locale ("+", "+1", "+2", ...). Mirrors
    /// the formatting in MegaCrit.Sts2.Core.Models.CardModel.Title.
    /// </summary>
    public static string ResolveCardTitle(CardModel? card)
    {
        if (card == null) return string.Empty;
        var name = Resolve(card.TitleLocString);
        if (!card.IsUpgraded) return name;
        if (card.MaxUpgradeLevel > 1) return $"{name}+{card.CurrentUpgradeLevel}";
        return name + "+";
    }

    /// <summary>
    /// Returns the English equivalent of locString, applying any dynamic variables it
    /// carries. Falls back to the raw entry key if the English entry is missing — never
    /// leaks the active locale's text. Returns "" for null/empty LocStrings.
    /// </summary>
    public static string Resolve(LocString? locString)
    {
        if (locString == null || locString.IsEmpty) return string.Empty;

        var raw = GetRaw(locString.LocTable, locString.LocEntryKey);
        if (raw == null)
        {
            // Locale-blind fallback: return the entry key, never the active-locale text.
            return locString.LocEntryKey ?? string.Empty;
        }

        // No vars: return the raw English template directly.
        if (locString.Variables == null || locString.Variables.Count == 0) return raw;

        // With vars: delegate to the game's own LocManager.SmartFormat under the
        // English-tables swap. SmartFormat is already initialized with all the
        // game's extensions (PluralLocalizationFormatter, EnergyIconsFormatter,
        // ...) so this matches in-game rendering exactly. Swap CultureInfo too
        // so plural rules follow English ("a card" / "2 cards"), not the
        // active locale's rules.
        try
        {
            var vars = new Dictionary<string, object>(locString.Variables);
            return WithEnglishTables(() => LocManager.Instance.SmartFormat(locString, vars));
        }
        catch
        {
            return raw;
        }
    }
}
