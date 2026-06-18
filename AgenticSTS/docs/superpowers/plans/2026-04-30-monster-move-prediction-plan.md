# Monster Move Prediction (turn+2 Markov) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a probabilistic "likely turn+2 move" line per enemy in the combat prompt, mined empirically from past `CombatEpisode` data, so the LLM can plan Sovereign Blade timing and damage spikes 2 turns ahead instead of only 1.

**Why now:** The mod only exposes the immediate next move via `enemy.Monster.NextMove.Intents`. There is no native turn+2 forecast and adding one mod-side requires reflecting on `MonsterModel.PickNextMove` (~1 day of C# work). Empirical mining from our existing `CombatEpisode` history is far cheaper (~1 hour of Python) and self-improving — every run we observe more transitions and the predictions sharpen.

**Tradeoffs / known limits:**
- Cold start: first encounters with a new enemy have zero data → output empty / "no prediction yet."
- Sparse enemies (rare elites the agent has only fought 1-2 times) have noisy distributions.
- Some monsters use weighted random independent of prior move; for those, the Markov estimate is just the marginal distribution and that's still useful.
- Some monsters have global cycle position (e.g., turn-N-modulo behaviour) the bigram model can't capture — accept the loss; cycle-aware prediction is option 2 in the original brief.
- Output is probabilistic; prompt phrasing must signal uncertainty so the LLM doesn't treat it as guaranteed.

**Tech Stack:** Python 3.14, pytest. New module `src/memory/monster_move_predictor.py`. Touches `src/memory/combat_extractor.py` (ensure round-level move list is captured), `src/brain/prompts/combat_plan.py` or wherever combat enemy intents are formatted, `src/memory/memory_manager.py` (expose predictor via the manager).

**Spec:** This document doubles as spec — the feature is small enough to skip a separate design.

---

## File Structure

| File | Change | Responsibility |
|------|--------|---------------|
| `src/memory/monster_move_predictor.py` | New | Bigram/marginal predictor over `CombatEpisode` round traces; one public class with `predict(enemy_key, current_move) -> list[(move_id, prob)]`. |
| `src/memory/combat_store.py` | Verify | Confirm `round_actions` / equivalent enemy-move trace is persisted per episode. If missing, add. |
| `src/memory/combat_extractor.py` | Verify/Modify | Confirm extractor populates the per-round enemy-move trace into `CombatEpisode`. |
| `src/memory/memory_manager.py` | Modify | Expose `monster_move_predictor` accessor (lazy-built from `combat_store`). |
| `src/brain/prompts/_intent_fmt.py` | Modify | New helper `format_predicted_next_move(enemy, predictor)` returning a single line; gated to only emit when prediction confidence ≥ threshold. |
| Combat plan prompt site (`reward.py` / `combat` prompt builder) | Modify | Append the predicted-next-move line under each enemy's existing intent line. |
| `tests/test_monster_move_predictor.py` | New | Unit tests for predictor: empty store, single transition, mixed bigram + marginal fallback, threshold gating. |

---

## Data prerequisites

Before predictor is useful, we need the enemy-move trace per round in `CombatEpisode`. Verify:

- [ ] **Step 0a: Confirm `CombatEpisode` schema includes per-round enemy-move IDs.**
  Inspect `src/memory/models_v2.py::CombatEpisode` and `src/memory/combat_extractor.py`. The per-round trace should look like `[{round: 1, enemy_moves: [{enemy_index: 0, move_id: "GLOMP_MOVE"}, ...]}, ...]`. If absent, add it: capture `enemy.move_id` per round during `CombatTracker.record_round_context` (see existing `agent_plan` capture pattern in `v2_engine.capture_round_context`).

- [ ] **Step 0b: If schema change is needed, write a one-shot migration that backfills `enemy_moves: []` for old episodes (so the predictor gracefully ignores pre-schema episodes).**

If the schema already has it, skip both substeps and proceed.

---

## Task 1: Predictor module (TDD)

**Files:**
- New: `src/memory/monster_move_predictor.py`
- New: `tests/test_monster_move_predictor.py`

- [ ] **Step 1: Write failing tests.**

```python
# tests/test_monster_move_predictor.py
def test_empty_store_returns_no_prediction():
    predictor = MonsterMovePredictor(combat_episodes=[])
    assert predictor.predict("CorpseSlug", current_move="GLOMP_MOVE") == []

def test_single_transition_yields_certain_prediction():
    eps = [_episode("CorpseSlug", moves=["GLOMP_MOVE", "WHIP_SLAP_MOVE"])]
    predictor = MonsterMovePredictor(combat_episodes=eps)
    result = predictor.predict("CorpseSlug", current_move="GLOMP_MOVE")
    assert result == [("WHIP_SLAP_MOVE", 1.0)]

def test_bigram_distribution():
    # GLOMP_MOVE → WHIP_SLAP_MOVE (3 times), GLOMP_MOVE → GOOP_MOVE (1 time)
    eps = [
        _episode("CorpseSlug", moves=["GLOMP_MOVE", "WHIP_SLAP_MOVE", "GLOMP_MOVE", "WHIP_SLAP_MOVE"]),
        _episode("CorpseSlug", moves=["GLOMP_MOVE", "WHIP_SLAP_MOVE", "GLOMP_MOVE", "GOOP_MOVE"]),
    ]
    predictor = MonsterMovePredictor(combat_episodes=eps)
    result = predictor.predict("CorpseSlug", current_move="GLOMP_MOVE")
    assert result == [("WHIP_SLAP_MOVE", 0.75), ("GOOP_MOVE", 0.25)]

def test_marginal_fallback_when_current_move_unseen():
    # current_move="UNSEEN" → fall back to marginal distribution of next moves
    eps = [_episode("CorpseSlug", moves=["GLOMP_MOVE", "WHIP_SLAP_MOVE", "GOOP_MOVE"])]
    predictor = MonsterMovePredictor(combat_episodes=eps)
    result = predictor.predict("CorpseSlug", current_move="UNSEEN")
    # Marginal: 1×GLOMP, 1×WHIP_SLAP, 1×GOOP (each appeared once after some move)
    assert sorted(result) == [("GLOMP_MOVE", 1/3), ("GOOP_MOVE", 1/3), ("WHIP_SLAP_MOVE", 1/3)]

def test_unknown_enemy_returns_empty():
    predictor = MonsterMovePredictor(combat_episodes=[])
    assert predictor.predict("Decimillipede", current_move="WRITHE_MOVE") == []
```

- [ ] **Step 2: Implement predictor.**

```python
# src/memory/monster_move_predictor.py
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable

from src.memory.models_v2 import CombatEpisode


@dataclass(frozen=True)
class MonsterMovePredictor:
    """Bigram next-move predictor mined from past CombatEpisode round traces.

    Builds two tables per enemy_key:
      - bigram[prev_move][next_move] = count
      - marginal[next_move] = count

    `predict(enemy_key, current_move)` returns sorted list of
    ``(move_id, probability)`` from bigram[current_move]; falls back to
    marginal when current_move is unseen for this enemy. Returns ``[]``
    when no data exists for the enemy at all.
    """

    _bigram: dict[str, dict[str, Counter[str]]]
    _marginal: dict[str, Counter[str]]
    _episode_count: dict[str, int]

    @classmethod
    def from_episodes(cls, episodes: Iterable[CombatEpisode]) -> "MonsterMovePredictor":
        bigram: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
        marginal: dict[str, Counter[str]] = defaultdict(Counter)
        episode_count: dict[str, int] = defaultdict(int)
        for ep in episodes:
            for enemy_key, move_seq in cls._extract_traces(ep):
                episode_count[enemy_key] += 1
                for prev, nxt in zip(move_seq, move_seq[1:]):
                    bigram[enemy_key][prev][nxt] += 1
                    marginal[enemy_key][nxt] += 1
        return cls(_bigram=bigram, _marginal=marginal, _episode_count=episode_count)

    def predict(self, enemy_key: str, current_move: str) -> list[tuple[str, float]]:
        if enemy_key not in self._marginal:
            return []
        candidates = self._bigram.get(enemy_key, {}).get(current_move)
        if not candidates:
            candidates = self._marginal[enemy_key]
        if not candidates:
            return []
        total = sum(candidates.values())
        return sorted(
            ((m, c / total) for m, c in candidates.items()),
            key=lambda x: -x[1],
        )

    def episode_count(self, enemy_key: str) -> int:
        return self._episode_count.get(enemy_key, 0)

    @staticmethod
    def _extract_traces(ep: CombatEpisode) -> Iterable[tuple[str, list[str]]]:
        """Yield (enemy_key, [move_id, ...]) per enemy seen across rounds."""
        # Implementation depends on CombatEpisode round-trace shape — adapt.
        # Expected shape: ep.rounds = [RoundContext(enemy_moves=[...])]
        per_enemy: dict[str, list[str]] = defaultdict(list)
        for rnd in getattr(ep, "rounds", []) or []:
            for em in getattr(rnd, "enemy_moves", []) or []:
                key = em.get("enemy_key") or em.get("enemy_name") or ""
                move = em.get("move_id") or ""
                if key and move:
                    per_enemy[key].append(move)
        yield from per_enemy.items()
```

- [ ] **Step 3: Run tests, expect green.**

```bash
.venv/bin/python -m pytest tests/test_monster_move_predictor.py -v
```

---

## Task 2: Wire predictor into MemoryManager

- [ ] **Step 1: Lazy-build predictor in `MemoryManager`.** Predictor is rebuilt at run start and on demand; building is O(total_rounds) which is fast.

```python
# src/memory/memory_manager.py
from src.memory.monster_move_predictor import MonsterMovePredictor

class MemoryManager:
    @property
    def monster_move_predictor(self) -> MonsterMovePredictor:
        if self._move_predictor is None:
            self._move_predictor = MonsterMovePredictor.from_episodes(
                self.combat_store.all_episodes()
            )
        return self._move_predictor

    def invalidate_move_predictor(self) -> None:
        """Call after combat extraction so the next access rebuilds with new data."""
        self._move_predictor = None
```

- [ ] **Step 2: Hook invalidation.** In the postrun combat-extraction stage where `CombatEpisode`s get persisted, call `memory.invalidate_move_predictor()` so the next agent run sees fresh data without restart.

---

## Task 3: Surface in combat prompt

**Goal:** Add ONE line per alive enemy under the existing intent line, only when prediction confidence is high enough.

**Threshold rule:**
- Need ≥ 5 episodes for this enemy AND top prediction probability ≥ 0.4 to show. Otherwise emit nothing (avoid LLM treating noisy predictions as truth).

- [ ] **Step 1: Helper in `_intent_fmt.py`.**

```python
def format_predicted_next_move(
    enemy: RawCombatEnemyPayload,
    predictor: MonsterMovePredictor | None,
    *,
    min_episodes: int = 5,
    min_top_prob: float = 0.4,
    top_k: int = 3,
) -> str:
    """Return e.g. "(turn+2 likely: WhipSlap 60% | Goop 30%, n=12)" or "".

    Empty string when (a) predictor is None, (b) episode_count below
    threshold, (c) top probability below threshold, (d) current move
    unknown.
    """
    if predictor is None:
        return ""
    enemy_key = enemy.name or enemy.enemy_id
    n = predictor.episode_count(enemy_key)
    if n < min_episodes:
        return ""
    current_move = enemy.move_id or ""
    if not current_move:
        return ""
    preds = predictor.predict(enemy_key, current_move)
    if not preds or preds[0][1] < min_top_prob:
        return ""
    head = preds[:top_k]
    parts = [f"{move} {int(prob*100)}%" for move, prob in head]
    return f"  ⤷ turn+2 likely: {' | '.join(parts)} (n={n})"
```

- [ ] **Step 2: Inject into combat plan prompt.** Find the per-enemy formatting site (likely in `combat_plan.py` or wherever the enemy block is built, alongside `format_enemy_intents`). Append the predicted-next line under the existing intent line, gated on `is_regent or always` (decide: probably always — this is character-agnostic).

- [ ] **Step 3: Pipe predictor through call chain.** `AgentLoop._generate_combat_plan` already has access to `self._memory`; pass `memory.monster_move_predictor` into the prompt builder. Default to `None` so non-combat callers aren't affected.

---

## Task 4: Sanity test on real data

- [ ] **Step 1:** Build predictor from current sibling-repo episodes:
  ```bash
  .venv/bin/python -c "
  from src.memory.combat_store import CombatStore
  from src.memory.monster_move_predictor import MonsterMovePredictor
  from src.storage import paths
  store = CombatStore.load(paths.combat_episodes_file())
  p = MonsterMovePredictor.from_episodes(store.all_episodes())
  for enemy in ['CorpseSlug', 'Vantom', 'Phantasmal Gardener', 'Entomancer']:
      n = p.episode_count(enemy)
      print(f'{enemy}: {n} episodes')
      if n > 0:
          # Top transitions from each move
          for prev, nxt in p._bigram.get(enemy, {}).items():
              total = sum(nxt.values())
              top = sorted(nxt.items(), key=lambda x: -x[1])[:3]
              print(f'  from {prev}: ' + ', '.join(f'{m}={c/total:.0%}' for m, c in top))
  "
  ```
- [ ] **Step 2:** Eyeball at least 3 enemies with ≥10 episodes — verify the bigram distributions match in-game expectation (e.g., Corpse Slug should have a clear bigram: GLOMP after WHIP_SLAP almost always).

---

## Task 5: A/B if signal is uncertain

- [ ] **Step 1 (optional):** Run an A/B with `STS2_PROMPT_VARIANT=monster_predict_off` vs default for 10 runs each on a stable Regent baseline, compare floor progression. If the signal is helpful for SB-timing decisions, average floor should rise.

---

## Future extensions (NOT in this plan)

- **Cycle-aware prediction (option 2 in original brief).** Reflect on `MonsterModel.PickNextMove` to extract deterministic move strategies. Larger work, mod-side. Worth doing for Decimillipede / Entomancer / The Insatiable specifically once the empirical predictor proves the value.
- **Hardcoded state-machine seeds for top dangerous enemies (option 3).** ~30 min per enemy. If Markov produces visibly bad predictions for specific enemies (e.g., due to RNG-heavy move logic), encode that enemy's true cycle as a seed.
- **Multi-step prediction (turn+3, +4).** Trivial extension once bigram is in place — chain predictions. Quality decays exponentially; probably not worth the prompt budget.

---

## Acceptance criteria

- New unit tests pass.
- Sanity-test step shows at least 3 enemies with sensible bigram distributions.
- Combat prompts for enemies with ≥5 past episodes contain a `⤷ turn+2 likely:` line.
- No regression in non-Regent character runs (the predictor is character-agnostic, so this is a sanity check, not an explicit gate).
