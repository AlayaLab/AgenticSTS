# Game Knowledge Database (L3)

This directory holds the typed game-knowledge layer (cards, relics, monsters,
events, intents, localization strings) consumed by the agent's L3 retrieval.

**What is NOT redistributed here.** Several generated subsets are intentionally
absent from the public repository and must be regenerated locally. They are
verbatim or derived game content (AGPL-3.0 upstream, or extracted from Mega
Crit's proprietary package), so they fall outside this directory's Apache-2.0
grant:

| Excluded | Why | Regenerate with |
|---|---|---|
| `upstream/*.json` (CharTyr-derived records) | upstream is AGPL-3.0; incompatible with this directory's Apache-2.0 license | `python -m scripts.sync_upstream_data` |
| `upstream/*_dll.json` (game-binary extracts) | derived from Mega Crit's proprietary `sts2.dll`; you must own the game | `python -m scripts.extract_mechanics_from_dll` |
| `afflictions.json`, `powers.json` (upstream string tables) | verbatim CharTyr-derived AGPL-3.0 records | `python -m scripts.sync_upstream_data` |
| `localization/{eng,zhs}/*.json` (game localization strings) | verbatim strings extracted from the proprietary `SlayTheSpire2.pck`; you must own the game | `python -m scripts.extract_pck_localization` |
| `cards.md`, `card-behaviors.md`, `characters.md`, `events.md`, `monsters.md`, `monster-behaviors.md`, `potions.md`, `potion-behaviors.md` (decompiled game-mechanic index tables — internal command names + values) | auto-generated from the decompiled `sts2.dll`; you must own the game | decompile your own `sts2.dll` into `extraction/decompiled/`, run `scripts/generate-sts2-knowledge.ps1` (writes `docs/game-knowledge/*.md`), then copy those files into `data/knowledge/` where the runtime parser reads them |

> The hand-authored `character_strategies.md` (compiled from public web research) and
> this `README.md` are **not** decompiled and **do** ship with the repository.

Each script writes its outputs into `data/knowledge/` on your machine; those
outputs remain governed by the upstream licenses (AGPL-3.0 / your game license)
and are **not** covered by this repository's Apache-2.0 grant. The regenerated
paths are listed in the top-level `.gitattributes` (`export-ignore`) and the
project `.gitignore` so they are never accidentally committed back.

Only patch metadata, version compatibility, and hand-curated strategy notes ship
with the repository. **No game binaries, executable code, art, audio, or verbatim
game-string tables are included.** All rights to the underlying game belong to
Mega Crit; this project is not affiliated with or endorsed by Mega Crit.
Rights-holders can open an issue for takedown requests.
