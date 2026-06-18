# Act-Boss-Aware Reward/Shop Card Selection — Design

**Status:** Draft
**Date:** 2026-04-18
**Owner:** AgenticSTS Contributors

## 1. Goal

Inject the CombatGuide for the current act's scheduled boss into `card_reward` and shop (cards-for-sale only) prompts, so the agent can consider boss matchup when picking cards. Only the current act's boss is exposed (not future acts), matching what is visible on the in-game map.

Injection MUST NOT over-constrain deckbuild: a single-line qualifier tells the agent to consider matchup without over-optimizing for one fight.

## 2. Scope

- In scope: `card_reward` (post-combat), shop card purchase section
- Not in scope: relic rewards / relic shop, potion shop, events, treasure, rest (Smith), card_select (upgrade/remove), combat prompts

## 3. Non-Goals

- Exposing future acts' bosses (agent cannot see them in-game)
- Injecting raw monster mechanics (HP / intents) — only the consolidated CombatGuide. If no guide exists for this `enemy_key × character`, inject nothing.
- Injecting past CombatEpisode snapshots (guide has already distilled them)

## 4. Architecture

```
[C# Mod]                                  [Python]                                   [Prompt]
runState.Act.BossEncounter           MapPayload                              UpstreamStateView
  .SecondBossEncounter (optional)  ──►  boss_encounter_id: str?      ──►    .upcoming_boss_enemy_keys
                                        second_boss_encounter_id: str?
                                                                               │
                                                                               ▼
                                                                       encounter_lookup
                                                                     (encounter_id → enemy_key via monsters[*].name)
                                                                               │
                                                                               ▼
                                                                       guide_store.get_combat_guide
                                                                      (enemy_key × character)
                                                                               │
                                                                               ▼
                                                               reward.py / shop.py prompt
                                                                "## Upcoming Act Boss" subsection
```

**Key invariant:** The subsection is injected only when a CombatGuide exists for the resolved `enemy_key × character`. Missing mod field / unknown encounter id / missing guide → section omitted (not downgraded to mechanics).

## 5. Double-Boss Case

Ascension 10 final act fights two bosses sequentially (not a path fork). When `second_boss_encounter_id` is present and both have guides, render both guides as separate labeled subsections. Since we're unlikely to reach A10 this milestone, this is a correctness guarantee rather than a performance concern.

## 6. Components

### 6.1 C# Mod (`STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs`)

Extend `BuildMapPayload` and `MapPayload` record:

```csharp
boss_encounter_id        = runState.Act.BossEncounter?.Id.ToString(),
second_boss_encounter_id = runState.Act.SecondBossEncounter?.Id.ToString(),
```

New nullable string fields on the `MapPayload` record. Uses already-public properties on `ActModel`; no reflection needed.

### 6.2 Python — Upstream Models (`src/mcp_client/upstream_models.py`)

Add to `RawMapPayload`:

```python
boss_encounter_id: str | None = None
second_boss_encounter_id: str | None = None
```

Default `None` keeps compatibility with older mod versions.

### 6.3 Python — Encounter Lookup (`src/knowledge/encounter_lookup.py`)

Add method that reproduces the exact `enemy_key` convention used by `combat_extractor._build_enemy_key`:

```python
def resolve_encounter_enemy_key(self, encounter_id: str) -> str | None:
    """Build the enemy_key that would be used by combat_extractor for a boss
    encounter, so CombatGuide lookups match the key under which guides are stored.

    Rules (identical to memory.combat_extractor._build_enemy_key):
      1. If the encounter has exactly one monster → return normalize_enemy_key(monster_name)
      2. If it has multiple monsters → return normalize_enemy_key("multi:" + "+".join(sorted(monster_names)))
      3. If encounter unknown or has no monsters → return None.
    """
```

Why this works: `encounters.json` already ships a complete `monsters: [{id, name}, ...]` list per boss encounter. E.g.:

| encounter_id | monsters (names) | resolved enemy_key |
|---|---|---|
| `CEREMONIAL_BEAST_BOSS` | `["Ceremonial Beast"]` | `"Ceremonial Beast"` |
| `DOORMAKER_BOSS` | `["Door", "Doormaker"]` | `"multi:Door+Doormaker"` |
| `KAISER_CRAB_BOSS` | `["Crusher", "Rocket"]` | `"multi:Crusher+Rocket"` |

Import `normalize_enemy_key` from `src.memory.enemy_keys` to keep a single source of truth for the normalization rules (e.g. the `Test Subject #C10` collapse). No HP / ordering heuristics needed.

Note that encounter `name` (e.g., `"Kaiser Crab"`) is NOT the enemy_key — at combat time `gs.enemies` contains the individual monsters, not the encounter wrapper, so keys must come from the `monsters[*].name` list.

### 6.4 Python — State View (`src/state/upstream_game_state.py`)

Add lazy property:

```python
@property
def upcoming_boss_enemy_keys(self) -> list[str]:
    """Resolved enemy_keys (matching combat_extractor convention) for current
    act's boss node(s). Empty list if no mod data, unknown encounter, or no
    boss node in current act. Returns 0, 1, or 2 keys.

    Uses encounter_lookup.resolve_encounter_enemy_key on raw.map.boss_encounter_id
    and raw.map.second_boss_encounter_id in order; filters out None.
    """
```

### 6.5 Prompt Helper (`src/brain/prompts/_boss_guide_fmt.py` — new)

Single shared helper to avoid duplication between reward.py and shop.py:

```python
def format_upcoming_boss_guide(
    gs: GameState,
    character: str,
    guide_store: GuideStore,
) -> list[str]:
    """Return prompt lines for upcoming boss guide(s), or [] if nothing to inject."""
```

Output format (when one guide exists):

```
## Upcoming Act Boss: Queen
<CombatGuide.summary content — reused from guide_store's existing format>

Consider matchup when picking, but don't over-optimize deckbuild for one fight.
```

When two guides exist (A10 double boss):

```
## Upcoming Act Bosses (sequential):

### Queen
<guide 1>

### Doormaker
<guide 2>

Consider matchup when picking, but don't over-optimize deckbuild for one fight.
```

### 6.6 Injection Sites

- `src/brain/prompts/reward.py` — `build_card_reward_prompt`: call `format_upcoming_boss_guide` and append lines before the `## Available Cards` section.
- `src/brain/prompts/shop.py` — `build_shop_prompt`: call helper; append only when the shop has cards for sale (skip on relic-only / potion-only shop visits).

## 7. Data Flow

1. Every `/state` response includes `map.boss_encounter_id` (and optional second). Updates automatically on act transition.
2. `UpstreamStateView.upcoming_boss_enemy_keys` resolves lazily per state snapshot (cheap: one dict lookup each).
3. `build_card_reward_prompt` / `build_shop_prompt` invoke the helper; helper calls `guide_store.get_combat_guide(enemy_key, character)`.
4. Guide hit → subsection rendered; miss → nothing injected.
5. Prompt cache: injection lives in the user message (not system prompt), so cache-hit rate is unaffected.

## 8. Error Handling

| Condition | Behavior |
|---|---|
| Mod lacks new fields (old mod version) | `boss_encounter_id=None` → empty `upcoming_boss_enemy_keys` → no injection |
| Encounter id not found in encounter_lookup | Return `None` from resolver → no injection; `logger.debug` entry |
| Encounter has empty `monsters` list | Return `None` → no injection |
| Guide store miss for `enemy_key × character` | No injection |
| State is not reward/shop | Helper never called (zero overhead) |
| Shop has no cards for sale | Helper skipped |

## 9. Testing

### Unit

- `test_encounter_lookup.py::test_resolve_enemy_key_single_monster` — `resolve_encounter_enemy_key("CEREMONIAL_BEAST_BOSS")` returns `"Ceremonial Beast"`.
- `test_encounter_lookup.py::test_resolve_enemy_key_multi_monster` — `resolve_encounter_enemy_key("DOORMAKER_BOSS")` returns `"multi:Door+Doormaker"` (sorted).
- `test_encounter_lookup.py::test_resolve_enemy_key_unknown_returns_none` — unknown id returns `None`.
- `test_boss_guide_fmt.py::test_no_guide_returns_empty` — helper returns `[]` when guide_store has no match.
- `test_boss_guide_fmt.py::test_single_boss_format` — helper returns a section with `## Upcoming Act Boss: <name>` header.
- `test_boss_guide_fmt.py::test_double_boss_format` — two guides rendered with `### <name>` subheaders.
- `test_reward_prompt.py::test_boss_guide_injected_when_present` — `build_card_reward_prompt` contains the subsection when `upcoming_boss_enemy_keys` and guide both exist.
- `test_shop_prompt.py::test_boss_guide_skipped_when_no_cards_for_sale` — shop prompt omits subsection on relic-only shop state.

### Integration (live)

- Start a new run, enter act 1 (first card reward at floor 2-3). Inspect logged prompt: if no prior guide, `## Upcoming Act Boss` should be absent.
- Complete one boss fight, run enough to trigger guide consolidation (`post_run` phase, every 5 runs). Start another run with the same character. At first card reward, the subsection should appear with last run's guide content.
- Transition from act 1 → act 2: at first card_reward in act 2, the upcoming boss should differ from act 1's.

## 10. Rollout

1. Ship C# mod change (requires `dotnet build -c Release` + redeploy DLL + user relaunches STS2)
2. Ship Python changes — behavior is gracefully degraded until mod is updated (old mod → no injection, no errors)
3. Monitor prompt logs over 5–10 runs to verify no duplicate/malformed injection
4. No flag / gating — feature is zero-impact when data absent
