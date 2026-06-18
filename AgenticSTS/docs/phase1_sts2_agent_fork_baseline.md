# Phase 1: STS2-Agent Fork Baseline

Date: 2026-03-19

## Scope

This document records the completed Phase 1 setup for the `STS2-Agent` upstream fork baseline.
Phase 1 is intentionally limited to fork/worktree setup, build verification, and minimal
environment normalization. It does not include Python-side migration, translator removal, or
API semantics changes.

## Result

- Working copy created at `STS2-Agent-Fork`
- Upstream remote normalized to `https://github.com/CharTyr/STS2-Agent.git`
- Working tree confirmed clean after setup
- Release build verified on this machine

## Verified Environment

- STS2 root: `D:\SteamLibrary\steamapps\common\Slay the Spire 2`
- `Sts2DataDir`: `D:\SteamLibrary\steamapps\common\Slay the Spire 2\data_sts2_windows_x86_64`
- .NET SDK: `9.0.312`

## Verified Build Command

```powershell
dotnet build STS2-Agent-Fork\STS2AIAgent\STS2AIAgent.csproj -c Release -p:Sts2DataDir='D:/SteamLibrary/steamapps/common/Slay the Spire 2/data_sts2_windows_x86_64'
```

## Build Output

- DLL: `STS2-Agent-Fork\STS2AIAgent\bin\Release\net9.0\STS2AIAgent.dll`

## Current Warning

- `GameStateService.cs(1859,21): warning CS8602`

This warning does not block Phase 2, but it should remain visible during later refactors so it
is not accidentally hidden by larger changes.

## Remote Strategy

- `Github\STS2-Agent` remains the local upstream reference clone
- `STS2-Agent-Fork` is the active working copy for migration work
- `upstream` in the working copy points to the official GitHub repository
- No personal/team `origin` remote is configured yet

## Phase Boundary

Phase 1 is complete only for repository/bootstrap concerns. The following work has not started:

- raw `/state` Python model migration
- `agent_view` model integration
- `GameState` wrapper rewrite
- action contract migration in the Python agent
- translator retirement

## Ready For Phase 2

Phase 2 can start from `STS2-Agent-Fork` with the following assumptions:

- C# baseline is buildable locally
- upstream sync path is stable
- no migration code has been mixed into the fork bootstrap step
