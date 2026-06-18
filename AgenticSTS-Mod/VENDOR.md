# Provenance — Fork of CharTyr/STS2-Agent

This directory is a **fork** of
[CharTyr/STS2-Agent](https://github.com/CharTyr/STS2-Agent), originally
authored by [CharTyr](https://github.com/CharTyr). All credit for the
original mod goes to CharTyr. The fork is licensed under AGPL-3.0, inherited
from upstream (see [`LICENSE`](./LICENSE)).

**Upstream merge-base:** commit `30e39ea` (CharTyr/STS2-Agent,
"Delete .claude directory", 2026-03-29), verified by blob-hash analysis.

This fork includes **only the C# game mod** (`STS2AIAgent/`). The upstream
project also ships an MCP server and assorted tooling; those are not vendored
here because the surrounding agent talks to the mod's HTTP API with its own
client.

## Modifications relative to upstream

The custom changes on top of the merge-base, by area:

| Area | Summary |
|---|---|
| Selection / decks | Crystal Sphere support, `save_and_quit`, deck-selection enhancements, live selection-card state, `cancel_selection`, upgrade-preview data for the Smith screen, idempotent `confirm_selection` |
| Combat state | Preserve runtime power descriptions; structured pile cards (`draw_cards` / `discard_cards` / `exhaust_cards`) on the combat payload |
| Map / bosses | Expose `boss_encounter_id` / `second_boss_encounter_id` on the top-level game-state payload |
| Rewards | Unblock `discard_potion` on reward / card-reward screens; atomic `resolve_rewards` action; structured `card_type` / `rarity` / `energy_cost` on reward options |
| Bundles | Dedicated `bundles[]` payload for `NChooseABundleSelectionScreen` |

Primary custom files: `Game/GameActionService.cs`, `Game/GameStateService.cs`,
`Game/EnglishLocResolver.cs`.

## Syncing with upstream

To pull upstream updates, add CharTyr/STS2-Agent as a remote and **merge**
(don't rebase — merging preserves upstream commit SHAs so
`git log <merge-base>..HEAD` still shows the delta):

```bash
git remote add upstream https://github.com/CharTyr/STS2-Agent.git
git fetch upstream
git merge upstream/main          # resolve conflicts, commit
cd STS2AIAgent && dotnet build -c Release
```

Capstone screen support and the v0.6.1 GameDataExportService were
investigated upstream and deliberately **not** pulled (capstone is a
compendium/settings shell, not a victory screen; GameDataExport had low
short-term ROI).
