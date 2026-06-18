# Character Build Guide Registry

## Problem

Runtime deckbuilding uses the two-phase framework: stay flexible in Phase 1, then commit once a real engine appears. The deck-guide memory layer currently works against that model because it groups postrun build memories by free-form LLM tags and falls back to `general`. That caused stale guides such as `the silent:general`, `thin_deck`, and duplicate key-order variants to be injected into reward/shop decisions.

Two concrete bugs fall out of this:

- Retrieval defaults to `general`, so stale general advice can appear even when the current deck has no matching build commitment.
- Guide consolidation treats `existing.memory_count >= len(builds)` as up-to-date. After pruning or tag reclassification, an existing guide can have a larger stored count than the current group and will never be recalculated.

## Decision

Deck guides are character-specific build guides, not cross-character mechanics. For The Silent, keep only the two active builds that are currently useful:

- `the silent:shiv`
- `the silent:poison`

Remove all other deck guides from `data/memory/v2/guides.json`. Combat, route, and event guides are not part of this cleanup.

`general`, `thin_deck`, and `small_deck` are not active builds:

- `general` should not be injected at runtime.
- `thin_deck` / `small_deck` are deck-size policy or anti-patterns, not build identities.
- Other stale Silent build buckets are deleted rather than migrated.

## Runtime Retrieval

Reward/shop/card-select retrieval should:

1. Derive build-guide candidates from explicit archetype, the strategic thread, current deck cards, and offered cards.
2. Canonicalize candidates through a small character build registry.
3. Retrieve active build guides in priority order.
4. Never fall back to `general`.

For The Silent v1, the registry allows only `shiv` and `poison`. A deck or offer containing poison signals can retrieve the poison guide; Shiv signals can retrieve the Shiv guide. If no active build signal exists, no deck guide is injected and the agent stays in Phase 1 under the two-phase framework.

## Consolidation

Postrun consolidation should canonicalize LLM build tags before grouping. For The Silent, only `shiv` and `poison` groups are eligible for guide consolidation. Deprecated or unsupported Silent tags are skipped.

The guide refresh check should treat count mismatch in either direction as stale:

- `existing.memory_count == len(builds)` means up-to-date.
- `existing.memory_count < len(builds)` means new evidence.
- `existing.memory_count > len(builds)` means pruning/reclassification happened and the guide should be recomputed.

## Postrun Build Classification

Postrun build analysis should no longer let Silent create arbitrary build tags.
For characters with an active registry, the LLM receives the active build list
and must classify the run as one of:

- `update_existing`
- `merge_into_existing`
- `create_candidate`
- `reject_no_clear_build`
- `reject_too_early`

For The Silent v1, only `shiv` and `poison` can become the stored build tag.
Rejected runs keep only the outcome tag and do not create or update a deck
guide bucket.

The same postrun analysis may emit per-card build roles. These are appended to
CardMemory as `build_role_observations`:

```json
{
  "run_id": "20260423_x",
  "build_id": "poison",
  "role": "core",
  "phase": "commitment",
  "evidence": "Noxious Fumes provided recurring poison scaling.",
  "confidence": 0.8
}
```

Runtime card-memory injection can surface those roles for offered cards and can
use them as build-guide retrieval signals.

## Future Work

The registry should eventually become persisted per character with at most three active builds. For characters without an active registry, postrun can still bootstrap candidates from meaningful runs, but runtime must not invent a `general` build guide.
