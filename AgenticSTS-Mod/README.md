# AgenticSTS-Mod

A *Slay the Spire 2* game mod that exposes the live game state and player
actions over a local HTTP API, so an external agent can observe and play the
game. It is the bridge used by the [AgenticSTS](../AgenticSTS) research agent.

## Credit & provenance

This mod is a **fork of [CharTyr/STS2-Agent](https://github.com/CharTyr/STS2-Agent)**,
created and originally authored by **[CharTyr](https://github.com/CharTyr)**.
All credit for the original mod design and implementation goes to CharTyr.

This directory contains **only the C# game mod** (`STS2AIAgent/`). The
upstream project also ships an MCP server and assorted tooling; those are not
included here because the AgenticSTS agent talks to the mod's HTTP API
directly with its own client. See `VENDOR.md` for the full fork history and
the exact upstream merge-base.

## License

**GNU Affero General Public License v3.0 (AGPL-3.0).** See [`LICENSE`](./LICENSE).
This license is inherited from the upstream project and governs this entire
directory. If you distribute or run a modified version of this mod, the
AGPL-3.0 terms apply. (Note: the AGPL applies to this mod only — the rest of
the surrounding repository is licensed separately.)

## Technical overview

- **Stack:** .NET 9 / Godot 4.5 / Harmony.
- **API:** HTTP REST on `localhost:8128` (configurable):
  - `GET /state` — current game state
  - `POST /action` — submit a player action
  - `GET /events/stream` — server-sent event notifications
- **Custom files** (relative to upstream): `Game/GameActionService.cs`,
  `Game/GameStateService.cs`.

## Build

```bash
cd STS2AIAgent
dotnet build -c Release
```

Building requires the STS2 game DLLs. They are read from the default Steam
install path:

```
C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2/data_sts2_windows_x86_64/
```

Override the location by setting the `STS2_DATA_DIR` environment variable
before building. See `STS2AIAgent/local.props.example` for the project's
local build properties.

## Deploy

Copy the built mod into the game's `mods/` directory and launch the game:

```
STS2AIAgent.dll
STS2AIAgent.pck
mod_id.json
```

The built `.dll`/`.pck` land in `STS2AIAgent/bin/Release/net9.0/`. A
pre-built copy is also tracked at `build/mods/STS2AIAgent/` for
clone-and-deploy without setting up the .NET SDK.

## Disclaimer

Not affiliated with, endorsed by, or sponsored by Mega Crit (developer of
*Slay the Spire 2*).
