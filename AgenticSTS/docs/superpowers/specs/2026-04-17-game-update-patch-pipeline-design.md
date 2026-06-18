# Game Update Patch Pipeline Design

**Date:** 2026-04-17
**Owner:** AgenticSTS Contributors
**Status:** Design approved, pending implementation plan
**Trigger:** STS2 main branch merging beta changes v0.100.0 → v0.103.1

---

## 1. Problem

STS2 is Early Access with frequent game updates. Each update can invalidate persistent memory, skill seeds, prompt hardcoded facts, and evolved self-modification artifacts. The project currently has **zero version-boundary design**:

- No `game_version` field anywhere in persistent data (13MB+ memory, 60+ evolution artifacts).
- `data/memory/v2/` stores index by literal card/enemy/relic names with no alias/version handling.
- `data/skills/skills.json` has hardcoded `requires_cards` triggers that silently stop firing when referenced cards are reworked or removed.
- Prompt files hardcode game constants (Act boundaries, 3-energy/5-card turn, Boss HP targets, A6 "Gloom" rule).
- `data/knowledge/*.md` was last synced 2026-03-10; `sync_upstream_data.py` SHA pin is 2026-03-30.
- No regression harness to verify agent still functions after an update.

Without version-boundary design, a game update silently pollutes memory and skills, degrading decision quality without detectable failure. For the EMNLP paper and long-term benchmark/website goals, this is unacceptable.

## 2. Goals & Non-Goals

### Goals
- Establish a **repeatable Patch Response Pipeline** that handles every future game update uniformly.
- Precisely invalidate persistent data that references changed entities (cards/relics/enemies/mechanics).
- Leave unchanged entities' data completely untouched across version bumps.
- Make every persisted record traceable to a `(game_version, mod_version)` tuple for research reproducibility.
- Provide dry-run + smoke-test safety nets before destructive operations.

### Non-Goals
- Automated mod compatibility repair. C# mod fixes (reflection field renames, etc.) remain manual.
- Cross-version name alias mapping. Unchanged-name entities keep unified records across versions; changed entities' records are deleted, not migrated.
- Soft `deprecated` flags on live data. Records are either active or snapshotted — no half-dead state.

## 3. Architecture Overview

Four orthogonal components driven by one authoritative source (the Patch Manifest):

```
                ┌─────────────────────────────────────┐
                │  Patch Manifest                     │
                │  data/patches/<game_version>.yaml   │
                │  — single source of truth per patch │
                └──────────────────┬──────────────────┘
                                   │
         ┌─────────────────┬───────┴───────┬────────────────────┐
         ▼                 ▼               ▼                    ▼
  ┌────────────┐   ┌───────────────┐  ┌─────────────┐  ┌──────────────────┐
  │ Versioning │   │ Purge Tool    │  │ LLM Rewrite │  │ Regression       │
  │ Layer      │   │ (entity-ref   │  │ Tool        │  │ Harness          │
  │            │   │  based)       │  │             │  │                  │
  │ provenance │   │ data/memory,  │  │ src/brain/  │  │ golden log       │
  │ only; no   │   │ skills,       │  │ prompts,    │  │ fingerprint      │
  │ retrieval  │   │ seeds, evol   │  │ seeds text  │  │ replay; mod API  │
  │ gating     │   │               │  │             │  │ coverage check   │
  └────────────┘   └───────────────┘  └─────────────┘  └──────────────────┘
                                   │
                                   ▼
                         ┌───────────────────┐
                         │ apply_patch.py    │
                         │ (orchestrator CLI)│
                         └───────────────────┘
```

Execution order when a new STS2 version ships:

1. Paste patch notes, generate `data/patches/v<new>.yaml`, commit.
2. `apply_patch --dry-run` → review impact.
3. Snapshot `data/` → `data.snapshots/v<old>-pre-v<new>/`.
4. `apply_patch` (non-dry) → deterministic purge + LLM-driven prompt rewrite + diff review.
5. Update game client.
6. Fix mod reflection fields manually, rebuild, deploy.
7. `sync_upstream_data.py --game-version v<new>`.
8. `apply_patch --smoke-test` → replay golden logs + 50-step live run.

## 4. Patch Manifest Format

File: `data/patches/<game_version>.yaml`. One per game version. Human-readable, machine-parseable. Acts as DB migration equivalent.

```yaml
game_version: v0.103.1
previous_version: v0.100.0
patch_date: 2026-04-17
source: "STS2 main branch merge of beta v0.100.0 through v0.103.1"
summary: |
  Mid-size patch: Ironclad/Silent/Regent/Necrobinder rebalance,
  Doormaker rework, 5 new Neow relics, badges/leaderboard systems added.

# Cards removed entirely (game auto-replaces with placeholder status card)
removed_cards:
  - name: "Grapple"
    character: "ironclad"
    replacement_note: "Game auto-replaces with placeholder status card"

# Cards with changed mechanics (name may or may not be same)
reworked_cards:
  - name: "Blade of Ink"
    character: "the silent"
    severity: major       # major → memories invalid; minor → memories retained
    change: "Completely reworked — generates Inky-enchanted Shivs"
  - name: "Arsenal"
    character: "regent"
    severity: major
    change: "Strength from any cards created, not just Colorless"
  - name: "Borrowed Time"
    character: "necrobinder"
    severity: major
    change: "Cost 0 Doom apply → Cost 1 energy spike + cost surcharge"
  - name: "Hidden Gem"
    category: "colorless"
    severity: major
  - name: "Dominate"
    character: "ironclad"
    severity: minor
  - name: "Expect a Fight"
    character: "ironclad"
    severity: minor
  - name: "Spite"
    character: "ironclad"
    severity: minor
  - name: "Stoke"
    character: "ironclad"
    severity: minor

# Only rarity changed; mechanics identical → pool weight shifts only
rarity_changed_cards:
  - name: "Acrobatics"
    character: "the silent"
    from: common
    to: uncommon

# Brand-new cards added
new_cards:
  - name: "Not Yet"
    character: "ironclad"
    text: "Cost 2 Skill | Heal 10(13) HP. Exhaust."

# Relics (same severity semantics)
reworked_relics:
  - name: "Regalite"
    character: "regent"
    severity: major
    change: "Block from any card created, not just Colorless"
  - name: "Pendulum"
    severity: major

new_relics:
  - name: "Hefty Tablet"
    source: neow
  - name: "Neow's Talisman"
    source: neow
  - name: "Neow's Bones"
    source: neow
  - name: "Phial Holster"
    source: neow
  - name: "Winged Boots"
    source: neow

# Enemies
reworked_enemies:
  - name: "Doormaker"
    severity: major
  - name: "Skulking Colony"
    severity: minor

# Global mechanic changes (special keys beyond entity names)
ascension_changes:
  - ascension: 6
    from: "Gloom — Less rest sites"
    to: "Inflation — Removing cards at Merchant is more expensive"

shop_changes:
  - "All shop relics cost 25 gold less"
  - "Gold-generating relics no longer appear in shop"

# Prompt wording clarifications (not mechanical; still trigger LLM rewrite)
writing_clarifications:
  - entity: "Fairy in a Bottle"
    clarification: "Only triggers at HP=0, not by any death cause"

# New systems (schema additions, frontend implications)
new_systems:
  - name: "Badges"
    scope: "run_end_summary"
  - name: "Leaderboards (friends-only, win+badges+speed ranked)"
    scope: "meta"

# Invalidation rules — derived by apply_patch from above sections,
# but expressible here for override if needed:
invalidation_rules:
  card_memories:
    - condition: "card_name in (reworked_cards.major ∪ removed_cards)"
      action: purge
  card_builds:
    - condition: "starting_deck ∪ final_deck ∪ card_play_counts.keys intersects (reworked_cards.major ∪ removed_cards)"
      action: purge
  combat_episodes:
    - condition: "enemy_key references reworked_enemies.major OR cards_played intersects (reworked_cards.major ∪ removed_cards)"
      action: purge
  skills:
    - condition: "trigger.requires_cards intersects (reworked_cards.major ∪ removed_cards)"
      action: purge
  guides:
    - condition: "enemy_key OR key_cards OR text references a changed entity"
      action: purge
```

**Manifest authoring workflow:** user pastes patch notes → Claude generates draft → user reviews/corrects → commits. Schema validation via `data/patches/_schema.yaml` (optional, future).

**Name normalization:** all entity name matching uses slug form (lowercase, whitespace collapsed, punctuation stripped) to avoid fragmentation.

## 5. Versioning Layer

### 5.1 Persistent Record Fields

Extend `models_v2.py` base types with three optional provenance fields:

```python
class VersionedRecord(BaseModel):
    game_version: str | None = None      # e.g. "v0.103.1"
    mod_version: str | None = None       # e.g. "v0.5.4-xc"
    data_schema_version: int = 2         # our persistence format version
```

Applied to: `CombatEpisode`, `RouteMemory`, `CardBuildMemory`, `CardMemory`, `EventMemory`, `Guide*`, `Skill`, `SkillCandidate`, `RunRecord`.

Each JSONL log file also writes a `{"_meta": {"game_version": ..., "mod_version": ...}}` header line at start.

### 5.2 Runtime Source of Truth

`data/version_compatibility.json`:

```json
{
  "current": {
    "game_version": "v0.103.1",
    "mod_version": "v0.5.4-xc",
    "verified_date": "2026-04-18"
  },
  "history": [
    {
      "game_version": "v0.5.3",
      "mod_version": "v0.5.3-chartyr",
      "snapshot_path": "data.snapshots/v0.5.3-pre-v0.103.1/",
      "retired_date": "2026-04-18"
    }
  ]
}
```

Loaded at agent startup. Env vars `STS2_GAME_VERSION` / `STS2_MOD_VERSION` act as overrides for debugging. Monitor UI and log headers display the active pair.

### 5.3 Retrieval Semantics

**Version fields are provenance only — not a retrieval gate.** A record's `game_version` is informational (useful for research, benchmark splits) but `retriever` scoring does not filter on it. Entity-reference-based purge is the only mechanism that removes stale data.

Rationale: records that reference only unchanged entities stay accurate across versions. Per-version gating would discard valid data unnecessarily and slow learning recovery.

### 5.4 Keyed Store Merge

`card_memory_store.upsert()` logic unchanged (additive merge for same `character::card_name`). If the card was unchanged between versions, new plays accumulate on top of old stats — which is desired. If the card was reworked, purge removed the old entry before any new writes occur.

## 6. Purge Tool (Entity-Reference Based)

Core script: `scripts/apply_patch.py`.

Two distinct sets derived from manifest:

- **`changed_entities`** (for data purge): slugged union of `reworked_cards.major ∪ removed_cards ∪ reworked_relics.major ∪ reworked_enemies.major`.
  `minor` severity entries are excluded — data retained, LLM may still update prompt wording around them.
- **`prompt_review_targets`** (for LLM rewrite): superset of `changed_entities` plus `ascension_changes`, `writing_clarifications`, `shop_changes`, `new_relics`, `new_cards`. Triggers prompt edits even when no data purge is needed.

```python
# Simplified flow
def apply_patch(manifest_path, dry_run=False, smoke_test=False):
    manifest = load_manifest(manifest_path)
    changed_entities = compute_changed_set(manifest)          # for data purge
    prompt_targets = compute_prompt_review_set(manifest)      # superset for LLM rewrite

    if not dry_run:
        snapshot_data()  # cp -r data/ data.snapshots/v<old>-pre-v<new>/

    # Phase 1: deterministic data purge
    purge_card_memories(changed_entities, dry_run)
    purge_card_builds(changed_entities, dry_run)
    purge_combat_episodes(changed_entities, dry_run)
    purge_event_memories(changed_entities, dry_run)
    purge_skills(changed_entities, dry_run)
    purge_skill_seeds(changed_entities, dry_run)
    purge_evolution_artifacts(changed_entities, dry_run)
    purge_guides(changed_entities, dry_run)  # entity-reference based, not wipe-all

    # Phase 2: LLM-driven prompt rewrite (broader scope than purge)
    diff = llm_rewrite_prompts(manifest, prompt_targets, dry_run)
    if not dry_run:
        review_and_apply_diff(diff)  # user reviews all-at-once

    # Phase 3: update version_compatibility.json
    bump_current_version(manifest.game_version, dry_run)

    # Phase 4: optional smoke test
    if smoke_test:
        run_regression_harness()
```

### 6.1 Data Purge Rules

| File | Purge criterion |
|---|---|
| `card_memories.json` | `card_name_slug ∈ changed_entities` → delete key |
| `card_builds.jsonl` | `(starting_deck ∪ final_deck ∪ card_play_counts.keys).slug ∩ changed_entities ≠ ∅` → delete row |
| `combat_episodes.jsonl` | `enemy_key.slug references reworked_enemies.major` OR `cards_played.slug ∩ changed_entities ≠ ∅` → delete row |
| `event_memories.jsonl` | `cards_gained.slug ∩ changed_entities ≠ ∅` → delete row |
| `skills.json` | `trigger.requires_cards.slug ∩ changed_entities ≠ ∅` → delete skill |
| `src/skills/seeds/silent_card_notes.json` | `card_name_slug ∈ changed_entities` → drop entry |
| `src/skills/seeds/core_*.json` | Text scan for entity references → if found, LLM rewrites that entry (phase 2) |
| `data/evolution/tools/*.py` | File text scan for entity names → if referenced, delete file |
| `data/evolution/proposals/*.json` | Scan `code_edits` / `prompt_effect` → if referenced, delete |
| `data/evolution/ab_test_results/*.json` | Scan `scenario` / `picks` → if referenced, delete |
| `data/evolution/evolution_log.jsonl` | Per-line scan; keep non-referencing lines |
| `data/memory/v2/guides.json` | Per-guide scan: purge if `enemy_key`, `key_cards`, or narrative text references a changed entity; others kept as-is |
| `data/runs/history.jsonl` | Not purged; historical only, does not feed decisions |

### 6.2 LLM Rewrite Rules (Phase 2)

For each file in `src/brain/prompts/**/*.py`:

1. Slug-scan content for any `changed_entities` member.
2. If no match, skip.
3. If match, dispatch subagent with:
   - Manifest entries for matched entities (full from→to change description).
   - File content.
   - Instruction: produce minimal diff rewriting affected lines only; preserve unrelated content.
4. Collect all diffs.
5. Present all diffs as one review batch to user.
6. User approves → apply atomically. Reject → skip file (leave stale, user fixes manually later).

Same logic applied to free-text seed files (`src/skills/seeds/core_*.json`) where entries reference entities in narrative text rather than structured `card_name` field.

### 6.3 CLI Flags

| Flag | Behavior |
|---|---|
| `--dry-run` | Report impact count, no writes |
| (default) | Snapshot + purge + LLM rewrite + version bump |
| `--smoke-test` | After apply, run golden log replay + optional 50-step live run |
| `--skip-llm` | Deterministic purge only; skip prompt rewrite (debug) |
| `--manifest <path>` | Override manifest path (default: latest in `data/patches/`) |

## 7. Regression Harness

### 7.1 Golden Log Replay

`tests/test_log_replay.py` + `tests/fixtures/golden_logs/<game_version>/*.jsonl`.

`LogReplayClient(MCPClient)` replays state sequence from a log file instead of calling real mod. Agent runs end-to-end, decisions captured, fingerprint computed:

```python
{
  "num_decisions": 127,
  "decision_types": {"play_card": 80, "end_turn": 20, ...},
  "state_types_seen": ["combat", "map", "reward", ...],
  "error_count": 0,
  "source_distribution": {"v2_engine_fast": 95, "v2_engine_strategic": 32}
}
```

Fingerprint tolerates LLM output drift but catches catastrophic regressions (infinite loops, exception spikes, state-type misrouting).

Seed set: 3–5 runs spanning ascension 0/4 victories, act2-boss loss, event-heavy run, shop/rest-heavy run. Frozen per game version under `tests/fixtures/golden_logs/v<version>/`.

### 7.2 Mod API Coverage Check

`scripts/check_mod_api_coverage.py` compares `/state` raw JSON keys (flattened, recursive) against Pydantic model fields:

- `missing`: keys mod returns but client does not model → warn, consider adding.
- `unused`: fields client expects but mod no longer returns → error, likely schema break.

Runs automatically after each game update, first smoke test only. Also wired into CI as optional gate.

### 7.3 Smoke Test Composition

Invoked by `apply_patch --smoke-test`:

1. `pytest tests/test_log_replay.py --golden-only` — replay all golden logs under current version slot.
2. Import sanity: `python -c "from src.memory.models_v2 import *; from src.brain.v2_engine import *"`.
3. Persistent data reload: sample 100 records per store type, `.model_validate()`.
4. Skill library load: `SkillLibrary.load()` must return non-empty.
5. (If `--live-smoke`) 50-step real run, monitor connectivity check, anomaly scan in log.

## 8. Mod Compatibility Workflow

Not Python-automatable. Manual C#/IL work, Claude-assisted.

```
1. cd STS2-Agent-Fork/STS2AIAgent && dotnet build -c Release
   - Compile errors → sts2.dll signatures changed → identify types affected.
2. Run mod, start a game run in STS2.
   - Reflection crashes (_prefs, _selectedCards, _devConsole, etc.) →
     ilspycmd the new sts2.dll, locate new field names,
     update GameActionService.cs / GameStateService.cs.
   - EventReflectionCandidateMembers misses → enable STS2_EVENT_REFLECTION_DEBUG=1,
     observe actual member names, update candidate list.
3. Verify /state returns for combat/map/event/rest/shop/reward/card_select screens.
4. Run scripts/check_mod_api_coverage.py → triage missing/unused fields.
5. Bump mod_version, commit, update data/version_compatibility.json.
```

## 9. Playbook in CLAUDE.md

Append to project CLAUDE.md:

```markdown
## Game Update Playbook

When STS2 releases a new version:

1. Paste patch notes → Claude generates data/patches/v<new>.yaml manifest
2. Commit manifest; review diff
3. python -m scripts.apply_patch data/patches/v<new>.yaml --dry-run
   → review purge impact
4. python -m scripts.apply_patch data/patches/v<new>.yaml
   → snapshots, purges, LLM-rewrites prompts, bumps version_compatibility.json
   → review and approve diff batch
5. Update game via Steam
6. Rebuild mod (see STS2-Agent-Fork/), fix reflection if needed
7. python -m scripts.sync_upstream_data --game-version v<new>
8. python -m scripts.apply_patch data/patches/v<new>.yaml --smoke-test
9. python -m scripts.run_agent --steps 50 --runs 1 (live verification)
```

## 10. Scope Boundaries

### Included in this design
- Patch Manifest schema and authoring workflow.
- `apply_patch.py` orchestrator with dry-run + smoke-test.
- Version fields on all persistent records + `version_compatibility.json`.
- Entity-reference-based purge logic across stores, skills, seeds, evolution artifacts.
- LLM-driven prompt rewrite with all-at-once diff review.
- Golden log replay regression harness.
- Mod API coverage check.
- CLAUDE.md playbook.

### Deferred (out of scope)
- Automated C# mod reflection repair. Remains manual/Claude-assisted.
- Cross-version alias mapping for renamed entities. If STS2 ever renames an entity without mechanical change, treat as two separate entities (old purged, new accumulates fresh).
- Per-version leaderboard splits in feat/leaderboard-mvp. Noted as follow-up for that branch.
- Knowledge file auto-sync from mod. Requires mod upstream to first ship new `eng/*.json`; existing `sync_upstream_data.py` handles once SHA pin updated.

## 11. Migration Plan for Current State (v0.5.3 → v0.103.1)

This design itself is authored before the v0.103.1 update is applied. First-time execution:

1. Implement the pipeline components per this spec while on v0.5.3.
2. Backfill `data/version_compatibility.json` with current state:
   `{current: {game_version: v0.5.3, mod_version: v0.5.3-chartyr}}`.
3. Do **not** backfill `game_version` into existing records — leave as `None`. Future retrievals treat `None` identically to any other provenance tag (non-gating).
4. Author `data/patches/v0.103.1.yaml` from the v0.100.0 → v0.103.1 release notes.
5. Run full playbook for v0.103.1 as the first real application.

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LLM-rewritten prompts introduce subtle bugs | All-at-once diff review; user approves atomically; prior snapshot allows rollback. |
| Manifest misses a reworked entity → stale data persists | `--dry-run` shows purge count; if suspiciously low, investigate before proceeding. `check_mod_api_coverage` after update surfaces downstream symptoms. |
| Snapshot directory accumulates disk space | Snapshot goes to `data.snapshots/` which is `.gitignore`d; manual cleanup user responsibility. Playbook notes this. |
| Evolution artifact gets deleted but its downstream prompt patch references it | Evolution purge scans cross-references among artifacts before deleting (implementation detail, flagged in plan). |
| Fingerprint-based regression tolerance masks real LLM routing regressions | Fingerprint includes `source_distribution` — if model tier routing silently changes, fingerprint detects. Complement with periodic manual spot-check of one golden log. |
| Mod `/state` schema change Pydantic silently ignores (extra="ignore") | `check_mod_api_coverage` explicitly surfaces `missing` keys as warnings. Mandatory first-smoke-test step. |
| User authors malformed manifest | Schema validation via Pydantic model for Manifest itself; `--dry-run` rejects invalid YAML before any write. |

## 13. Success Criteria

Pipeline is successful when:
- A future game update takes under 2 hours of human time (excluding mod C# fixes and LLM diff review).
- No silent data corruption: every purged record is logged with reason; every retained record justifies its retention by entity-reference check.
- Golden log regression passes with zero `error_count` delta before/after a pure code refactor (ensuring harness is load-bearing).
- Each run in `data/runs/history.jsonl` is traceable to exact `(game_version, mod_version, model_profile)` tuple — EMNLP reproducibility gate.
