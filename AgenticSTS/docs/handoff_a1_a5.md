# Handoff Prompt: Complete A1-A5 C# Architecture Refactoring

Copy everything below the line into a new Claude Code session.

---

## Task

Refactor the STS2MCP C# mod (a Slay the Spire 2 Godot mod that exposes a REST API on localhost:15526) from a monolithic `static partial class McpMod` across 9 files into a clean service-oriented architecture inspired by the CharTyr/STS2-Agent reference project.

**The Python agent must continue working without ANY changes.** The REST API contract (endpoints, JSON shape, action names) must be 100% preserved.

## Current State

The mod works correctly. All features (singleplayer, multiplayer, SSE events, menu automation) are functional. The code is in `AgenticSTS\STS2MCP\` and builds with `dotnet build` (0 errors, 0 warnings).

### Current Files (all `static partial class McpMod`)

| File | Lines | Purpose |
|------|-------|---------|
| McpMod.cs | 327 | HttpListener, request router, main thread queue, CORS |
| McpMod.StateBuilder.cs | 1418 | Game state → JSON dict (singleplayer) |
| McpMod.Formatting.cs | 835 | State → markdown text |
| McpMod.Helpers.cs | 218 | SendJson, tree traversal, text cleanup, snake_case |
| McpMod.Actions.cs | 828 | Singleplayer action execution (play_card, end_turn, etc.) |
| McpMod.MultiplayerActions.cs | 120 | Multiplayer action execution |
| McpMod.MultiplayerState.cs | 476 | Multiplayer state building |
| McpMod.Events.cs | 229 | SSE streaming (PollStateChanges, ComputeStateDigest) |
| McpMod.MenuActions.cs | 477 | Multi-stage menu automation (start_new_run) |

### Current API Endpoints (MUST PRESERVE EXACTLY)

```
GET  /                        → health check JSON
GET  /api/v1/singleplayer     → game state (json or markdown via ?format=)
POST /api/v1/singleplayer     → execute action {"action": "...", ...params}
GET  /api/v1/multiplayer      → multiplayer game state
POST /api/v1/multiplayer      → execute multiplayer action
GET  /api/v1/events           → SSE stream (event: state, data: json)
```

### Current Threading Model

```csharp
// Main thread queue: ConcurrentQueue<Action> dequeued in ProcessFrame signal
internal static Task<T> RunOnMainThread<T>(Func<T> func) {
    var tcs = new TaskCompletionSource<T>();
    _mainThreadQueue.Enqueue(() => { ... });
    return tcs.Task;
}
// HTTP handlers call: RunOnMainThread(() => BuildGameState()).GetAwaiter().GetResult();
```

### Current JSON Config

```csharp
internal static readonly JsonSerializerOptions _jsonOptions = new() {
    WriteIndented = true,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
};
```

### Project File

```xml
<Project Sdk="Godot.NET.Sdk/4.4.0">
  <PropertyGroup>
    <TargetFramework>net9.0</TargetFramework>
    <LangVersion>12.0</LangVersion>
    <EnableDynamicLoading>true</EnableDynamicLoading>
  </PropertyGroup>
  <ItemGroup>
    <Reference Include="STS2"><HintPath>..\..\..\..\.steam\steam\steamapps\common\Slay the Spire 2\Slay the Spire 2.dll</HintPath></Reference>
    <Reference Include="0Harmony"><HintPath>..\..\..\..\.steam\steam\steamapps\common\Slay the Spire 2\GodotSharp\tools\0Harmony.dll</HintPath></Reference>
  </ItemGroup>
</Project>
```

## CharTyr Reference Architecture

The reference project at `<local-path>` demonstrates the target architecture. Read these files for patterns:

### GameThread.cs (102 lines) — Thread Safety
```csharp
// Captures SynchronizationContext at mod init, marshals work to game thread
public static class GameThread {
    static SynchronizationContext _context;
    static int _threadId;

    public static void Initialize() {
        _context = SynchronizationContext.Current;
        _threadId = Thread.CurrentThread.ManagedThreadId;
    }

    public static Task<T> InvokeAsync<T>(Func<T> action) {
        if (Thread.CurrentThread.ManagedThreadId == _threadId)
            return Task.FromResult(action()); // already on game thread
        var tcs = new TaskCompletionSource<T>();
        _context.Post(_ => { try { tcs.SetResult(action()); } catch(Exception e) { tcs.SetException(e); } }, null);
        return tcs.Task;
    }
}
```

### GameActionService.cs — Frame-Level Stability Detection
```csharp
// After executing an action, waits for game state to stabilize
// Uses NGame.Instance.ToSignal(tree, ProcessFrame) to yield per-frame
// Checks: round changed, side changed, action queue empty, not in play phase transition
// Returns { status: "completed"|"pending", stable: true|false }
```

### HttpServer.cs — Retry Logic
```csharp
// Retries listener start on error code 183 (prefix conflict) up to 20 times
// Reads STS2_API_PORT env var (we keep port 15526)
```

### ApiException.cs — Structured Errors
```csharp
public sealed class ApiException : Exception {
    public int StatusCode { get; }
    public string Code { get; }      // "invalid_action", "invalid_target", etc.
    public object? Details { get; }   // structured context
    public bool Retryable { get; }    // client should retry?
}
```

### GameEventService.cs — Event Polling (417 lines)
```csharp
// Singleton event publisher
// Polls every 120ms via GameThread.InvokeAsync(BuildStatePayload)
// Computes StateDigest, diffs against previous, publishes typed events
// Subscribers get bounded Channel<GameEventEnvelope>(256, DropOldest)
```

## Refactoring Plan: A1-A5

### A1: Infrastructure Layer

Create shared infrastructure that all services will use.

**New files:**
- `Game/GameThread.cs` — SynchronizationContext capture + InvokeAsync<T> (replace ConcurrentQueue pattern)
- `Server/JsonSettings.cs` — Shared JsonSerializerOptions (extracted from McpMod)
- `Server/ApiException.cs` — Structured error class with StatusCode, Code, Details, Retryable

**Key changes:**
- GameThread.Initialize() called at mod startup, captures SynchronizationContext.Current
- All RunOnMainThread calls replaced with GameThread.InvokeAsync()
- JsonSettings.Default replaces McpMod._jsonOptions
- ApiException thrown instead of returning `{"status": "error"}` dicts

**Constraint:** GameThread must use `SynchronizationContext.Post()` (CharTyr pattern), not our current `ConcurrentQueue + ProcessFrame`. This is cleaner because it uses Godot's built-in marshaling. However, we still need PollStateChanges() on ProcessFrame for SSE — keep the ProcessFrame signal connection for that purpose only.

### A2: GameStateService

Extract all state-building logic into a static service class.

**New file:** `Game/GameStateService.cs`

**Move from:**
- McpMod.StateBuilder.cs → GameStateService (all Build* methods)
- McpMod.MultiplayerState.cs → GameStateService (multiplayer Build* methods)
- McpMod.Formatting.cs → GameStateService or separate FormattingService

**Key methods:**
```csharp
public static class GameStateService {
    public static Dictionary<string, object?> BuildGameState() { ... }
    public static Dictionary<string, object?> BuildMultiplayerGameState() { ... }
    public static string FormatAsMarkdown(Dictionary<string, object?> state) { ... }
    // All helper methods (BuildPlayerState, BuildEnemyState, BuildCombatState, etc.)
}
```

**Constraint:** Return types stay as `Dictionary<string, object?>` — the Python agent parses raw JSON, not typed DTOs. Do not change the JSON shape.

### A3: GameActionService

Extract all action execution into a static service class.

**New file:** `Game/GameActionService.cs`

**Move from:**
- McpMod.Actions.cs → GameActionService (all Execute* methods)
- McpMod.MultiplayerActions.cs → GameActionService (multiplayer Execute* methods)
- McpMod.MenuActions.cs → GameActionService (ExecuteStartNewRun, menu automation)

**Key methods:**
```csharp
public static class GameActionService {
    public static Dictionary<string, object?> ExecuteAction(string action, Dictionary<string, JsonElement> params) { ... }
    public static Dictionary<string, object?> ExecuteMultiplayerAction(string action, Dictionary<string, JsonElement> params) { ... }
    // All Execute* handlers, target resolution, menu automation
}
```

**Enhancement:** Add frame-level stability detection for key actions (end_turn, play_card) following CharTyr's WaitForEndTurnTransitionAsync() pattern. But since our Python agent expects synchronous responses, return immediately and let the agent poll for state changes (via SSE or polling). The stability detection is a FUTURE enhancement — for now, preserve the current behavior.

**Constraint:** Action names and parameter shapes must not change. The Python agent sends `{"action": "play_card", "card_index": 0, "target_index": 0}` etc.

### A4: HTTP Server Layer

Extract HTTP server, router, and SSE handling.

**New files:**
- `Server/HttpServer.cs` — HttpListener setup with retry logic
- `Server/Router.cs` — Request routing (replaces HandleRequest in McpMod.cs)
- `Server/GameEventService.cs` — SSE event polling + subscriber management (replaces McpMod.Events.cs)

**Move from:**
- McpMod.cs ServerLoop, HandleRequest → HttpServer + Router
- McpMod.Events.cs → GameEventService

**Key patterns from CharTyr:**
- HttpServer singleton with Start()/Stop() lifecycle
- Router dispatches to GameThread.InvokeAsync(() => GameStateService.BuildGameState())
- GameEventService singleton with Start()/Stop(), polls via GameThread.InvokeAsync, publishes via channels
- Retry on port conflict (error code 183)

**Constraint:** Keep port 15526 (not CharTyr's 8080). Keep all existing routes.

### A5: ModEntry + Cleanup

Create clean entry point and remove old files.

**New file:** `ModEntry.cs`

```csharp
[ModInitializer("Initialize")]
public static class ModEntry {
    public const string Version = "0.3.0";

    public static void Initialize() {
        GameThread.Initialize();
        GameEventService.Instance.Start();
        HttpServer.Instance.Start();
        GD.Print($"[STS2 MCP] v{Version} started on http://localhost:15526/");
    }
}
```

**Delete old files:**
- McpMod.cs
- McpMod.StateBuilder.cs
- McpMod.Formatting.cs
- McpMod.Helpers.cs
- McpMod.Actions.cs
- McpMod.MultiplayerActions.cs
- McpMod.MultiplayerState.cs
- McpMod.Events.cs
- McpMod.MenuActions.cs

**Move shared helpers to appropriate locations:**
- SendJson/SendText/SendError → Router or HttpHelpers
- FindAll/FindFirst/FindAllSortedByPosition → Helpers/NodeExtensions.cs
- SafeGetText/StripRichTextTags/ToSnakeCase → Helpers/TextHelpers.cs
- SafeReadNullableInt → wherever it's used

**Bump version to 0.3.0 in mod_manifest.json**

## Execution Order

1. **A1 first** — GameThread, JsonSettings, ApiException (no functional changes, just infrastructure)
2. **A2** — GameStateService (move state building, verify JSON output identical)
3. **A3** — GameActionService (move actions, verify all actions work)
4. **A4** — HttpServer + Router + GameEventService (move HTTP layer, verify endpoints)
5. **A5 last** — ModEntry + cleanup (delete old files, verify build)

After each phase: `dotnet build` must produce 0 errors, 0 warnings.

## Testing Strategy

After each phase, verify:
1. `dotnet build` succeeds (0 errors, 0 warnings)
2. JSON output shape unchanged (if you can run the game, hit GET /api/v1/singleplayer)
3. All action names still work (play_card, end_turn, choose_map_node, etc.)
4. SSE endpoint still streams events

If you can't run the game, at minimum verify the build compiles and the code is logically equivalent.

## Critical Warnings

1. **DO NOT change any JSON field names or structure** — the Python agent parses these
2. **DO NOT change action names** — "play_card", "end_turn", "choose_map_node", etc.
3. **DO NOT change the port** — must stay localhost:15526
4. **DO NOT change endpoint paths** — /api/v1/singleplayer, /api/v1/multiplayer, /api/v1/events
5. **DO NOT add new dependencies** — only use what's already in the .csproj
6. **Preserve ALL game API calls** — every MegaCrit.* reference must be preserved as-is
7. **Keep `namespace STS2_MCP;`** — the mod framework needs this
8. **The `[ModInitializer("Initialize")]` attribute** must be on the class with the Initialize method

## File Locations

- **Our mod source:** `AgenticSTS\STS2MCP\`
- **CharTyr reference:** `<local-path>`
- **Python agent (read-only reference):** `AgenticSTS\src\`
- **Build command:** `cd AgenticSTS\STS2MCP && dotnet build`

## After Completion

When A1-A5 is complete, inform the user to return to the original session for:
- Code review (using code-reviewer agent)
- Phase E: Guided MCP tool profile (reducing ~30 MCP tools to 6 unified tools)
