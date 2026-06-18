# Mod: English HTTP output regardless of active game locale

## Context

The user wants the agent's HTTP API (`/state`, `/events/stream`, hover-tip text, etc.) to always receive English strings — so memory + skills + parsing pipelines stay English-only — **regardless of which of the 14 supported game locales the player chose** (`eng`, `zhs`, `deu`, `esp`, `fra`, `ita`, `jpn`, `kor`, `pol`, `ptb`, `rus`, `spa`, `tha`, `tur`). Today the mod reads `card.Title`, `enemy.Name`, `eventModel.Description.GetFormattedText()`, etc. — all locale-resolved strings — so when the player runs in any non-English locale, the agent receives that locale's text.

The approach below is **locale-agnostic by construction**: the mod loads English tables directly from disk at startup and never consults the active-locale state, so a Japanese / Korean / Russian / Chinese player gets identical English HTTP output.

## Key findings from the decompiled game source (local clone; path varies by contributor)

1. **Every model exposes a stable `(table, key)` pair alongside the locale-resolved string.** `CardModel.cs:90` defines `public LocString TitleLocString => new LocString("cards", base.Id.Entry + ".title")` and `:109` `Description => new LocString("cards", base.Id.Entry + ".description")`. `LocString.cs:14-18` exposes `LocTable` and `LocEntryKey` as public properties. The mod can read those instead of `card.Title`.

2. **Localization JSONs are plain files at `res://localization/<lang>/*.json`.** The same files we already have at `data/knowledge/localization/{eng,zhs}/`. The mod can load them via Godot `FileAccess` at startup, completely independent of the player's active locale.

3. **`SmartFormat` is locale-independent at the API level.** `LocManager.cs:197-220` shows `SmartFormat(LocString, vars)` calls `_smartFormatter.Format(culture, rawText, variables)` — culture is passed in, raw text comes from whichever table you choose. So we can format English templates with English culture against the same dynamic vars that the model would have used in Chinese.

4. **The engine has `LocManager.StartOverridingLanguageAsEnglish()` at `:293`, but it switches the player's UI too — unusable for our case.** It does confirm `_engTables` can coexist with the active locale's tables.

## Approach

**Mod-side change only.** Add an English-resolution layer in the C# mod that:
1. Loads `res://localization/eng/*.json` once at mod startup into a private `Dictionary<string, Dictionary<string, string>>` (`tableName → entryKey → English text`).
2. Exposes a helper that given any `LocString`, returns the English equivalent.
3. Replaces ~50 `.Title` / `.GetFormattedText()` call sites in `Game/GameStateService.cs` with the helper.

This keeps the player's game in Chinese (the active locale is untouched) while every API string the mod emits is resolved through the English tables.

## Implementation steps

### Step 1 — `Game/EnglishLocResolver.cs` (new file, ~80 LOC)

```csharp
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using Godot;
using MegaCrit.Sts2.Core.Localization;
using SmartFormat;

namespace STS2AIAgent.Game;

internal static class EnglishLocResolver
{
    private static Dictionary<string, Dictionary<string, string>>? _tables;
    private static SmartFormatter? _smartFormatter;
    private static readonly System.Globalization.CultureInfo _enCulture =
        System.Globalization.CultureInfo.GetCultureInfo("en");

    private static readonly string[] _tableFiles = {
        "cards", "relics", "potions", "monsters", "powers", "events",
        "intents", "afflictions", "enchantments", "card_keywords"
    };

    public static void Initialize()
    {
        _tables = new Dictionary<string, Dictionary<string, string>>();
        foreach (var name in _tableFiles)
        {
            var path = $"res://localization/eng/{name}.json";
            using var f = Godot.FileAccess.Open(path, Godot.FileAccess.ModeFlags.Read);
            if (f == null) continue;
            var json = f.GetAsText();
            var dict = JsonSerializer.Deserialize<Dictionary<string, string>>(json)
                       ?? new Dictionary<string, string>();
            _tables[name] = dict;
        }
        _smartFormatter = (SmartFormatter?)typeof(LocManager)
            .GetField("_smartFormatter", BindingFlags.NonPublic | BindingFlags.Static)?
            .GetValue(null);
    }

    /// Returns the raw English text for (table, key), or null if missing.
    public static string? GetRaw(string table, string key)
        => (_tables != null && _tables.TryGetValue(table, out var t) && t.TryGetValue(key, out var v))
           ? v : null;

    /// Returns the English equivalent of locString. If the English entry is missing
    /// (e.g. modded content with no English translation), returns the raw entry key
    /// (e.g. "some_mod_card.title") rather than falling back to the active-locale
    /// string — keeps output locale-agnostic so a Russian / Korean / etc. player
    /// never sees their locale leak through into the HTTP payload.
    public static string Resolve(LocString locString)
    {
        if (locString == null || locString.IsEmpty) return string.Empty;
        var raw = GetRaw(locString.LocTable, locString.LocEntryKey);
        if (raw == null) return locString.LocEntryKey;  // locale-blind fallback
        if (_smartFormatter == null || locString.Variables.Count == 0) return raw;
        try
        {
            var vars = new Dictionary<string, object>(locString.Variables);
            return _smartFormatter.Format(_enCulture, raw, vars);
        }
        catch { return raw; }
    }
}
```

Call `EnglishLocResolver.Initialize()` once from `ModEntry.cs` after the game has booted (after `LocManager.Instance` is non-null). Cost: ~5–10 ms cold load + ~500 KB RAM.

### Step 2 — Refactor call sites in `Game/GameStateService.cs`

Each replacement is a 1-line swap. The pattern is:
- `card.Title` → `EnglishLocResolver.Resolve(card.TitleLocString)`
- `card.Title.GetFormattedText()` → same
- `relic.Title.GetFormattedText()` → `EnglishLocResolver.Resolve(relic.TitleLocString)`
- `eventModel.Description?.GetFormattedText()` → `EnglishLocResolver.Resolve(eventModel.Description)` (already a `LocString`)
- `enemy.Name` → needs check; if `enemy.Monster` exposes a `LocString`, use it; otherwise look up via `enemy.ModelId.Entry` against `monsters.json`
- `card.GetDescriptionForPile(...)` → see Step 3

**Concrete sites (from earlier audit of `STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs`)**:

Direct title/name (~25 sites): `2857`, `2093-2094`, `3553`, `4042`, `4322`, `4340`, `4385-4386`, `4444-4445`, `4504`, `4518`, `4598-4599`, `4671`, `4731`, `4854`, `4982`, `5151`, `5281`, `5296`, `5319`, `5342`, `5595`, `5613`, `5867`, `5906`, `5956`, `6181`, `6206`, `6222`, `6267`, `6278`, `6352`, `7054`, `7059`, `7064`.

For each, find the parallel `*LocString` accessor on the model (`TitleLocString`, `Description`, etc.). If one doesn't exist on a particular model, construct the LocString manually from `(table_name, base.Id.Entry + ".title")` — the convention is consistent across models per the decompiled `*Model.cs` files.

### Step 3 — Card descriptions and intent labels (the dynamic-vars cases)

`card.GetDescriptionForPile(PileType.Hand)` (lines `1994`, `2032`) returns a fully-formatted Chinese string with `{Damage:diff()}` etc. already substituted. To get the English equivalent, build the `LocString` manually:

```csharp
var descLoc = card.Description;            // LocString("cards", $"{id}.description")
DynamicVars.AddTo(descLoc);                // attach the same dynamic vars the game uses
descLoc.Add("Damage", card.GetDamage(...)); // any context-specific vars
return EnglishLocResolver.Resolve(descLoc);
```

The exact `DynamicVars.AddTo` call mirrors what `CardModel.cs` does internally — find the source-of-truth in the decompiled `CardModel.GetDescriptionForPile` method and replicate the var attachments. Same pattern for `intent.GetIntentLabel(...)` at line `5119`.

If replicating dynamic-var attachment is too fragile, **fallback v1**: leave card descriptions in Chinese for now (they're rendered live, agent can mostly skip them since `rules_text` from card metadata is also emitted). Ship Step 1+2 first, evaluate impact, decide whether Step 3 is needed.

### Step 4 — Build & deploy

```bash
cd STS2-Agent-Fork/STS2AIAgent && dotnet build -c Release
cp bin/Release/net9.0/STS2AIAgent.dll "C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2/mods/"
```

PCK and `mod_id.json` are unchanged — no need to regenerate.

## Critical files

- `STS2-Agent-Fork/STS2AIAgent/Game/EnglishLocResolver.cs` — new, ~80 LOC.
- `STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs` — ~35 1-line edits.
- `STS2-Agent-Fork/STS2AIAgent/ModEntry.cs` — 1 line: `EnglishLocResolver.Initialize();` after `LocManager.Instance` exists.

## Verification

1. **Compile**: `dotnet build -c Release` succeeds with 0 errors.
2. **Smoke test, primary locale (Chinese)**: launch game with locale set to `zhs`. Confirm UI is in Chinese. `curl http://localhost:8080/state` and inspect: `name` / `title` / `description` fields should be English (e.g. `"Strike"`, not `"打击"`); `card_id` should remain `"strike"`.
3. **Locale-agnostic check**: repeat the smoke test with at least two non-English, non-Chinese locales (e.g. `jpn`, `rus`). HTTP output for cards/relics/potions/monsters must be byte-identical to the `zhs` and `eng` runs.
4. **End-to-end agent run**: `python -m scripts.run_agent --steps 50 --runs 1 --no-postrun`. Watch monitor dashboard for any non-ASCII characters leaking into prompts. Compare a `decision` log entry between locale=`eng` and locale=`zhs` runs — payload text should be byte-identical for cards/relics/potions/monsters; only `reasoning_zh` (display-only, controlled by `STS2_DISPLAY_LANGUAGE`) should differ.
5. **Modded-content fallback**: install any community mod that adds new cards. Verify mod-added cards still serialize. With the locale-blind fallback, the `name` for a mod-added card with no English translation will be its raw entry key (e.g. `"some_mod_card.title"`) rather than the active-locale string — confirm the agent tolerates this gracefully.

## Out of scope

- Translating runtime UI labels from `gameplay_ui.json`, `combat_messages.json`, etc. — the mod doesn't emit those.
- Two-way translation (English-input from agent → Chinese display in game) — agent emits action params keyed by `card_id`, not by name, so no translation needed in that direction.
- Replacing `mcp_server/data/eng/*.json` as the agent-side fallback — it stays as backup for opaque random rewards per CLAUDE.md.

## Estimated effort

- Step 1 (resolver): 1 hour
- Step 2 (call-site sweep): 2–3 hours
- Step 3 (dynamic vars, if pursued): 2–4 hours
- Build + smoke test: 1 hour

**Total: ~half to one full day** for steps 1+2+4 (covers 90% of agent-visible text). Step 3 deferrable to v2 if descriptions in Chinese turn out to be tolerable.
