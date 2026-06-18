# Ablation Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add seven `STS2_*` env-flag gates so the ablation `baseline-strict` condition strips all strategy heuristics, hint injections, non-visible knowledge, and cross-decision state from LLM prompts — while leaving `full` runs bit-for-bit unchanged.

**Architecture:** Add config flags with defaults that preserve current behavior. Wrap strategy / leak / state-injection sites in `if config.<FLAG>:` branches. Extend the ablation runner to set the new flags for the baseline condition. Each gate is independent and individually testable.

**Tech Stack:** Python 3.11+, pytest, existing `tests/conftest.py` builders (`make_combat_gs`, `make_card_select_gs`, `make_event_gs`, `make_potion_discard_gs`, `make_shop_gs`).

**Spec:** `docs/superpowers/specs/2026-04-26-ablation-baseline-design.md`

---

## File Map

**Created:**
- `tests/prompts/__init__.py` — empty package marker
- `tests/prompts/test_baseline_variants.py` — prompt-strip tests across all 9 prompt files
- `tests/config/__init__.py` — empty package marker
- `tests/config/test_flag_defaults.py` — flag default + override tests

**Modified:**
- `config.py` — add 7 flag constants + `_PRESERVE_IF_SET` entries + `build_model_profile()` snapshot
- `src/brain/prompts/system.py` — 4 baseline variants + dispatcher reads `PROMPT_VARIANT`
- `src/brain/prompts/reward.py` — gate `## Evaluation` + `## Build Trajectory Check` blocks
- `src/brain/prompts/shop.py` — gate `## Guide` block; gate `format_relic_hints` + `format_card_notes` + boss guide calls
- `src/brain/prompts/rest.py` — gate advisory text after numeric heal calculations; gate `format_relic_hints`
- `src/brain/prompts/event.py` — gate trailing 2 advisory lines
- `src/brain/prompts/potion.py` — gate `## Threat Assessment` advisory labels + `## Potion Decision Framework` block
- `src/brain/prompts/hand_select.py` — extract flat-list helper; gate priority groupings + `## Tactical Flags` + mode-aware advice
- `src/brain/prompts/card_select.py` — gate trailing hint in `build_card_select_prompt` + `build_pack_selection_prompt`
- `src/brain/prompts/treasure.py` — gate trailing 2 advisory lines
- `src/brain/prompts/_boss_guide_fmt.py` — early return on `KNOWLEDGE_STRICT`
- `src/knowledge/injector.py` — early returns in `inject_event_knowledge`, `_build_monster_info`, `inject_encounter_knowledge` on `KNOWLEDGE_STRICT`
- `src/agent/loop.py` — gate `_get_short_term_ref` / `_hcm_short_term` on `STM_ENABLED`; gate CombatConversation creation on `COMBAT_CONVERSATION_ENABLED`; gate boss HP retention on `INCLUDE_BOSS_HP`
- `src/brain/v2_engine.py` — single-turn fallback when `COMBAT_CONVERSATION_ENABLED=false`
- `src/brain/run_context.py` — early return in `format_run_summary` on `RUN_CONTEXT_ENABLED`
- `scripts/run_ablation.py` — extend `Condition` dataclass + `to_env_overrides` + `build_condition_matrix`; rename condition_id to `*-baseline-strict`

---

## Task 1: Config flags scaffolding

**Files:**
- Modify: `config.py`
- Test: `tests/config/test_flag_defaults.py`

Spec ref: §5 (all sub-sections), §6, §7 task 1.

- [ ] **Step 1.1: Create test package marker**

```bash
mkdir -p tests/config
touch tests/config/__init__.py
```

- [ ] **Step 1.2: Write failing test for default values**

Create `tests/config/test_flag_defaults.py`:

```python
"""Tests for ablation-baseline flag defaults and overrides.

Defaults must preserve current ("full") behavior. Each flag toggles
independently. .env cannot override values the ablation runner sets.
"""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager


@contextmanager
def _envvar(**overrides: str):
    """Set env vars, reload config, restore on exit."""
    original = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            os.environ[k] = v
        import config
        importlib.reload(config)
        yield config
    finally:
        for k, v in original.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        import config
        importlib.reload(config)


def test_prompt_variant_defaults_to_full():
    with _envvar() as config:
        assert config.PROMPT_VARIANT == "full"


def test_prompt_hint_filter_defaults_to_false():
    with _envvar() as config:
        assert config.PROMPT_HINT_FILTER is False


def test_knowledge_strict_defaults_to_false():
    with _envvar() as config:
        assert config.KNOWLEDGE_STRICT is False


def test_stm_enabled_defaults_to_true():
    with _envvar() as config:
        assert config.STM_ENABLED is True


def test_combat_conversation_enabled_defaults_to_true():
    with _envvar() as config:
        assert config.COMBAT_CONVERSATION_ENABLED is True


def test_run_context_enabled_defaults_to_true():
    with _envvar() as config:
        assert config.RUN_CONTEXT_ENABLED is True


def test_include_boss_hp_defaults_to_true():
    with _envvar() as config:
        assert config.INCLUDE_BOSS_HP is True


def test_prompt_variant_baseline_override():
    with _envvar(STS2_PROMPT_VARIANT="baseline") as config:
        assert config.PROMPT_VARIANT == "baseline"


def test_knowledge_strict_true_override():
    with _envvar(STS2_KNOWLEDGE_STRICT="true") as config:
        assert config.KNOWLEDGE_STRICT is True


def test_stm_enabled_false_override():
    with _envvar(STS2_STM_ENABLED="false") as config:
        assert config.STM_ENABLED is False


def test_all_new_flags_in_preserve_if_set():
    with _envvar() as config:
        for flag in (
            "STS2_PROMPT_VARIANT",
            "STS2_PROMPT_HINT_FILTER",
            "STS2_KNOWLEDGE_STRICT",
            "STS2_STM_ENABLED",
            "STS2_COMBAT_CONVERSATION_ENABLED",
            "STS2_RUN_CONTEXT_ENABLED",
            "STS2_INCLUDE_BOSS_HP",
        ):
            assert flag in config._PRESERVE_IF_SET, f"{flag} missing from _PRESERVE_IF_SET"


def test_model_profile_includes_new_flags():
    with _envvar() as config:
        profile = config.build_model_profile()
        for key in (
            "prompt_variant",
            "prompt_hint_filter",
            "knowledge_strict",
            "stm_enabled",
            "combat_conversation_enabled",
            "run_context_enabled",
            "include_boss_hp",
        ):
            assert key in profile, f"{key} missing from model_profile"
```

- [ ] **Step 1.3: Run tests, verify all 12 fail with AttributeError**

Run: `pytest tests/config/test_flag_defaults.py -v`
Expected: 12 failures, each one citing the missing constant.

- [ ] **Step 1.4: Add the 7 flag constants to `config.py`**

Locate the existing block of `*_ENABLED` constants (around line 404-476 — `MEMORY_ENABLED`, `SKILLS_ENABLED`, `EVOLUTION_ENABLED`). Append:

```python
# ── Ablation baseline gates (added 2026-04-26) ───────────────────
# Defaults preserve current ("full") behavior. The ablation runner
# (scripts/run_ablation.py) sets these to baseline values for the
# baseline-strict condition. See:
#   docs/superpowers/specs/2026-04-26-ablation-baseline-design.md

PROMPT_VARIANT = os.getenv("STS2_PROMPT_VARIANT", "full").lower()
"""'full' (default, current behavior) or 'baseline' (strip strategy heuristics)."""

PROMPT_HINT_FILTER = os.getenv("STS2_PROMPT_HINT_FILTER", "false").lower() in ("true", "1", "yes")
"""When True, skip _relic_fmt.format_relic_hints and _card_clarifications calls."""

KNOWLEDGE_STRICT = os.getenv("STS2_KNOWLEDGE_STRICT", "false").lower() in ("true", "1", "yes")
"""When True, knowledge injectors that leak non-visible info return empty."""

STM_ENABLED = os.getenv("STS2_STM_ENABLED", "true").lower() in ("true", "1", "yes")
"""When False, AgentLoop._get_short_term_ref / _hcm_short_term return None."""

COMBAT_CONVERSATION_ENABLED = os.getenv("STS2_COMBAT_CONVERSATION_ENABLED", "true").lower() in ("true", "1", "yes")
"""When False, V2Engine treats each combat turn as a fresh single-message conversation."""

RUN_CONTEXT_ENABLED = os.getenv("STS2_RUN_CONTEXT_ENABLED", "true").lower() in ("true", "1", "yes")
"""When False, RunContextView.format_run_summary returns empty."""

INCLUDE_BOSS_HP = os.getenv("STS2_INCLUDE_BOSS_HP", "true").lower() in ("true", "1", "yes")
"""When False, prompts skip Boss HP target rendering (200/400/600 numbers)."""
```

- [ ] **Step 1.5: Add to `_PRESERVE_IF_SET`**

Locate the `_PRESERVE_IF_SET` set (around line 44-47). Append the 7 new env names:

```python
_PRESERVE_IF_SET = {
    "STS2_POSTRUN_ENABLED",
    "STS2_EVOLUTION_ENABLED",
    "STS2_SKILLS_ENABLED",
    "STS2_MEMORY_ENABLED",
    # Ablation baseline gates (added 2026-04-26)
    "STS2_PROMPT_VARIANT",
    "STS2_PROMPT_HINT_FILTER",
    "STS2_KNOWLEDGE_STRICT",
    "STS2_STM_ENABLED",
    "STS2_COMBAT_CONVERSATION_ENABLED",
    "STS2_RUN_CONTEXT_ENABLED",
    "STS2_INCLUDE_BOSS_HP",
}
```

- [ ] **Step 1.6: Surface in `build_model_profile()`**

Locate `build_model_profile()` (line 533). Add the 7 new fields to the returned dict so `RunRecord.model_profile` records them:

```python
def build_model_profile() -> dict:
    return {
        # ... existing fields ...
        "memory_enabled": MEMORY_ENABLED,
        "skills_enabled": SKILLS_ENABLED,
        "evolution_enabled": EVOLUTION_ENABLED,
        # Ablation baseline gates
        "prompt_variant": PROMPT_VARIANT,
        "prompt_hint_filter": PROMPT_HINT_FILTER,
        "knowledge_strict": KNOWLEDGE_STRICT,
        "stm_enabled": STM_ENABLED,
        "combat_conversation_enabled": COMBAT_CONVERSATION_ENABLED,
        "run_context_enabled": RUN_CONTEXT_ENABLED,
        "include_boss_hp": INCLUDE_BOSS_HP,
    }
```

(Open the file to find the exact return-dict structure; the keys above are additive.)

- [ ] **Step 1.7: Run tests, verify all 12 pass**

Run: `pytest tests/config/test_flag_defaults.py -v`
Expected: 12 passing.

- [ ] **Step 1.8: Run full config-related test suite for regression**

Run: `pytest tests/ -k "config" -v`
Expected: all pass (no pre-existing tests should break).

- [ ] **Step 1.9: Commit**

```bash
git add config.py tests/config/__init__.py tests/config/test_flag_defaults.py
git commit -m "feat(config): add 7 ablation baseline gates with current-behavior defaults"
```

---

## Task 2: system.py baseline variants + dispatcher

**Files:**
- Modify: `src/brain/prompts/system.py`
- Test: `tests/prompts/test_baseline_variants.py` (new)

Spec ref: §5.1 first 5 rows.

- [ ] **Step 2.1: Create test package**

```bash
mkdir -p tests/prompts
touch tests/prompts/__init__.py
```

- [ ] **Step 2.2: Write failing test for system prompt variants**

Create `tests/prompts/test_baseline_variants.py`:

```python
"""Snapshot tests verifying baseline variants strip strategy content
and full variants are unchanged. Spec:
  docs/superpowers/specs/2026-04-26-ablation-baseline-design.md
"""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager


@contextmanager
def _set_variant(variant: str):
    original = os.environ.get("STS2_PROMPT_VARIANT")
    os.environ["STS2_PROMPT_VARIANT"] = variant
    try:
        import config
        importlib.reload(config)
        from src.brain.prompts import system
        importlib.reload(system)
        yield system
    finally:
        if original is None:
            os.environ.pop("STS2_PROMPT_VARIANT", None)
        else:
            os.environ["STS2_PROMPT_VARIANT"] = original
        import config
        importlib.reload(config)
        from src.brain.prompts import system
        importlib.reload(system)


# ── Baseline variant content checks ──────────────────────────────

def test_baseline_combat_strips_hp_conservation():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("monster")
        assert "HP Conservation" not in prompt
        assert "HP is a run-wide resource" not in prompt
        assert "Save sustained-buff potions" not in prompt


def test_baseline_combat_keeps_core_rules():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("monster")
        assert "Core Combat Rules" in prompt
        assert "Hand resets every turn" in prompt
        assert "Energy resets to 3" in prompt
        assert "Queue plays for generated cards" in prompt


def test_baseline_boss_strips_boss_strategy():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("boss")
        assert "Boss Fight Strategy" not in prompt
        assert "HP fully restores after" not in prompt
        assert "trade HP freely" not in prompt


def test_baseline_deckbuild_strips_two_phase_framework():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("card_reward")
        assert "Two-Phase" not in prompt
        assert "Foundation" not in prompt
        assert "Commitment" not in prompt
        assert "core engine" not in prompt.lower()
        assert "4 dimensions" not in prompt
        assert "strategic_note" not in prompt


def test_baseline_deckbuild_has_minimal_task_header():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("card_reward")
        assert "Deckbuilding Decision" in prompt


def test_baseline_strategic_strips_run_wide_strategy():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("rest_site")
        assert "Run-Wide Strategy" not in prompt
        assert "Upgrade (Smith) by default" not in prompt
        assert "HP is a run-wide resource" not in prompt
        assert "strategic_note" not in prompt


def test_baseline_strategic_has_minimal_task_header():
    with _set_variant("baseline") as system:
        prompt = system.get_system_prompt("event")
        assert "Strategic Decision" in prompt


# ── Full variant unchanged checks ────────────────────────────────

def test_full_combat_keeps_hp_conservation():
    with _set_variant("full") as system:
        prompt = system.get_system_prompt("monster")
        assert "HP Conservation" in prompt
        assert "HP is a run-wide resource" in prompt


def test_full_deckbuild_keeps_two_phase_framework():
    with _set_variant("full") as system:
        prompt = system.get_system_prompt("card_reward")
        assert "Two-Phase Framework" in prompt
        assert "Foundation" in prompt
        assert "Commitment" in prompt


def test_full_strategic_keeps_run_wide():
    with _set_variant("full") as system:
        prompt = system.get_system_prompt("rest_site")
        assert "Run-Wide Strategy" in prompt
```

- [ ] **Step 2.3: Run tests, verify they fail**

Run: `pytest tests/prompts/test_baseline_variants.py -v`
Expected: 7 baseline tests fail (assertions about absent content trip on full output); 3 full tests pass.

- [ ] **Step 2.4: Add baseline variants and dispatcher**

Edit `src/brain/prompts/system.py`. After the existing `SYSTEM_STRATEGIC` constant and before `_STATE_SYSTEM_MAP`, add:

```python
# ─── Baseline variants (ablation) ───────────────────────────────
# Strip strategy heuristics, keep mechanics + I/O. See:
#   docs/superpowers/specs/2026-04-26-ablation-baseline-design.md

_CORE_COMBAT_RULES = """
## Core Combat Rules
- Turn structure: Each turn you draw 5 cards, gain 3 energy, and your Block resets to 0. Play cards (costs energy), use potions (free). At end of turn, all remaining hand cards are discarded.
- Hand resets every turn: You get 5 NEW cards each turn from your draw pile. Cards with Retain stay. Cards drawn or created during THIS turn are part of THIS turn's hand immediately; unless they Retain or explicitly return, they will not stay for next turn.
- Hand size limit: Your hand can hold at most 10 cards. If a draw/add-to-hand effect would exceed 10 cards, excess drawn or generated cards are discarded or fail to enter your hand.
- Block resets every turn: Block only protects you during the upcoming enemy turn unless a visible card/power explicitly says Block is retained.
- Energy resets to 3: Unspent energy is wasted.
- Enemy intents are visible: Attack (damage value shown), Defend, Buff, Debuff, Status (adds junk cards to your deck).
- Draw effects resolve immediately: cards drawn or added to hand this turn are usable now.
- Draw pile is a forecast, not a reservation: any draw/add-to-hand effect this turn changes the forecast.
- Queue plays for generated cards: if your `plan` includes a card that ADDS new cards to your hand (Blade Dance / Storm of Steel / Cloak and Dagger → Shivs, Infernal Blade → random Attack, Nightmare → extra copies, etc.), you MUST also queue the plays for those generated cards in the same `plan`, placed AFTER the generator. The generated cards exist in hand the instant the generator resolves — treat them as part of this turn's available plays. Failing to queue them wastes them and forces a mid-round re-plan.
"""

SYSTEM_COMBAT_BASELINE = _SYSTEM_BASE + _CORE_COMBAT_RULES

SYSTEM_COMBAT_BOSS_BASELINE = _SYSTEM_BASE + _CORE_COMBAT_RULES

SYSTEM_DECKBUILD_BASELINE = _SYSTEM_BASE + """

## Deckbuilding Decision
You are evaluating cards to add to, modify, or remove from your deck.
Choose based on the information available below.
Do not include `strategic_note` in your output.
"""

SYSTEM_STRATEGIC_BASELINE = _SYSTEM_BASE + """

## Strategic Decision
You are making a run-level decision (rest / map / event).
Choose based on the information available below.
Do not include `strategic_note` in your output.
"""

_STATE_SYSTEM_MAP_BASELINE: dict[str, str] = {
    "monster": SYSTEM_COMBAT_BASELINE,
    "elite": SYSTEM_COMBAT_BASELINE,
    "boss": SYSTEM_COMBAT_BOSS_BASELINE,
    "hand_select": SYSTEM_COMBAT_BASELINE,
    "combat_hand_select": SYSTEM_COMBAT_BASELINE,
    "card_reward": SYSTEM_DECKBUILD_BASELINE,
    "card_select": SYSTEM_DECKBUILD_BASELINE,
    "shop": SYSTEM_DECKBUILD_BASELINE,
    "rest_site": SYSTEM_STRATEGIC_BASELINE,
    "map": SYSTEM_STRATEGIC_BASELINE,
    "event": SYSTEM_STRATEGIC_BASELINE,
}
```

- [ ] **Step 2.5: Update dispatcher to read PROMPT_VARIANT**

Replace `get_system_prompt`:

```python
def get_system_prompt(state_type: str) -> str:
    """Get the appropriate system prompt for a game state type.

    Reads ``config.PROMPT_VARIANT`` ('full' or 'baseline') to pick between
    the strategy-rich full prompts and the baseline (mechanics + I/O only)
    prompts used for ablation. Default 'full' preserves current behavior.
    """
    import config
    if config.PROMPT_VARIANT == "baseline":
        return _STATE_SYSTEM_MAP_BASELINE.get(state_type, SYSTEM_STRATEGIC_BASELINE)
    return _STATE_SYSTEM_MAP.get(state_type, SYSTEM_STRATEGIC)
```

- [ ] **Step 2.6: Run tests, verify all pass**

Run: `pytest tests/prompts/test_baseline_variants.py -v`
Expected: 10 passing.

- [ ] **Step 2.7: Run system-prompt regression**

Run: `pytest tests/ -k "system_prompt or system" -v`
Expected: all pass.

- [ ] **Step 2.8: Commit**

```bash
git add src/brain/prompts/system.py tests/prompts/__init__.py tests/prompts/test_baseline_variants.py
git commit -m "feat(prompts): add baseline system prompt variants gated on PROMPT_VARIANT"
```

---

## Task 3: reward.py + shop.py strategy block gates

**Files:**
- Modify: `src/brain/prompts/reward.py`
- Modify: `src/brain/prompts/shop.py`
- Test: `tests/prompts/test_baseline_variants.py` (extend)

Spec ref: §5.1 reward.py / shop.py rows; §5.2 `format_card_notes` / `get_inline_warning`; §5.3 `format_upcoming_boss_guide`.

- [ ] **Step 3.1: Append failing tests for reward and shop**

Append to `tests/prompts/test_baseline_variants.py`:

```python
# ── reward.py / shop.py ──────────────────────────────────────────

def _build_reward_gs():
    """Minimal GameState with reward state for prompt builder tests."""
    from unittest.mock import MagicMock

    gs = MagicMock()
    gs.act = 1
    gs.floor = 7
    gs.player_hp = 56
    gs.player_max_hp = 70
    gs.hp_ratio = 0.8
    gs.gold = 95
    gs.open_potion_slots = 1

    rw = MagicMock()
    rw.pending_card_choice = True
    rw.alternatives = []
    card = MagicMock()
    card.index = 0
    card.name = "Backflip"
    card.upgraded = False
    card.rules_text = "Gain 5 Block. Draw 2 cards."
    card.resolved_rules_text = card.rules_text
    card.dynamic_values = []
    rw.card_options = [card]
    rw.rewards = []
    gs.reward = rw
    return gs


def test_baseline_reward_strips_boss_damage_check():
    with _set_variant("baseline") as _:
        from src.brain.prompts.reward import build_card_reward_prompt
        prompt = build_card_reward_prompt(_build_reward_gs(), deck=[], relics=[])
        assert "Boss Damage Check" not in prompt
        assert "Build Trajectory" not in prompt
        assert "Boss HP target" not in prompt
        assert "200" not in prompt
        assert "400" not in prompt
        assert "600" not in prompt


def test_full_reward_keeps_boss_damage_check():
    with _set_variant("full") as _:
        from src.brain.prompts.reward import build_card_reward_prompt
        prompt = build_card_reward_prompt(_build_reward_gs(), deck=[], relics=[])
        assert "Boss Damage Check" in prompt
        assert "Build Trajectory Check" in prompt


def _build_shop_gs():
    """Minimal GameState with shop cards for prompt builder tests."""
    from tests.conftest import make_shop_gs
    gs = make_shop_gs()
    return gs


def test_baseline_shop_strips_guide_block():
    with _set_variant("baseline") as _:
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(_build_shop_gs(), deck=[], relics=[])
        assert "## Guide" not in prompt
        assert "Boss HP" not in prompt
        assert "Build Plan in the Strategic Thread" not in prompt


def test_full_shop_keeps_guide_block():
    with _set_variant("full") as _:
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(_build_shop_gs(), deck=[], relics=[])
        assert "## Guide" in prompt
```

- [ ] **Step 3.2: Run tests, verify the 4 new tests fail**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "reward or shop"`
Expected: 4 baseline tests fail; full tests pass.

- [ ] **Step 3.3: Gate `## Evaluation — Boss Damage Check` block in reward.py**

Open `src/brain/prompts/reward.py`. The block to gate starts at line 161 (`## Evaluation — Boss Damage Check`) and ends at line 180 (the SKIP guidance line about "lean deck beats a bloated one"). Wrap the block:

```python
        if config.PROMPT_VARIANT != "baseline":
            # Boss damage check
            boss_hp = BOSS_HP_TARGETS.get(act, BOSS_HP_TARGETS[2])
            target_dps = boss_hp // 10

            lines.append("")
            lines.append("## Evaluation — Boss Damage Check")
            # ... existing 10 lines through the SKIP guidance ...
            lines.append("SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one.")
```

Add `import config` at the top of the file if not already present.

- [ ] **Step 3.4: Gate `## Build Trajectory Check` block in reward.py**

The block starts at line 184 and ends at line 190 (5 numbered points). Wrap identically:

```python
        if config.PROMPT_VARIANT != "baseline":
            # Build trajectory check
            lines.append("")
            lines.append("## Build Trajectory Check")
            # ... existing 5 numbered points ...
```

- [ ] **Step 3.5: Gate `## Guide` block in shop.py**

Open `src/brain/prompts/shop.py`. The block starts at line 218 (`## Guide`) and ends at line 229. Wrap:

```python
        if config.PROMPT_VARIANT != "baseline":
            # DPS-aware guide
            boss_hp = BOSS_HP_TARGETS.get(gs.act, BOSS_HP_TARGETS[2])
            target_dps = boss_hp // 10

            lines.append("")
            lines.append("## Guide")
            # ... existing 7 advisory lines ...
```

Add `import config` if not already present.

- [ ] **Step 3.6: Run tests, verify pass**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "reward or shop"`
Expected: all 4 passing.

- [ ] **Step 3.7: Run reward / shop regression**

Run: `pytest tests/ -k "reward or shop or dps_aware" -v`
Expected: pass (existing reward / shop / dps tests still green).

- [ ] **Step 3.8: Commit**

```bash
git add src/brain/prompts/reward.py src/brain/prompts/shop.py tests/prompts/test_baseline_variants.py
git commit -m "feat(prompts): gate reward/shop strategy blocks on PROMPT_VARIANT"
```

---

## Task 4: rest.py + event.py + treasure.py + card_select.py advisory text gates

**Files:**
- Modify: `src/brain/prompts/rest.py`
- Modify: `src/brain/prompts/event.py`
- Modify: `src/brain/prompts/treasure.py`
- Modify: `src/brain/prompts/card_select.py`
- Test: `tests/prompts/test_baseline_variants.py` (extend)

Spec ref: §5.1 rest.py / event.py / treasure.py / card_select.py rows.

- [ ] **Step 4.1: Append failing tests**

```python
# ── rest.py / event.py / treasure.py / card_select.py ────────────

def test_baseline_rest_strips_advisory_text():
    from tests.conftest import make_combat_gs  # placeholder; rest needs its own minimal gs
    from unittest.mock import MagicMock
    gs = MagicMock()
    gs.act = 2
    gs.floor = 22
    gs.player_hp = 25
    gs.player_max_hp = 70
    gs.hp_ratio = 0.36
    gs.gold = 50
    gs.can_proceed = False
    rest = MagicMock()
    rest.options = []
    gs.rest = rest

    with _set_variant("baseline") as _:
        from src.brain.prompts.rest import build_rest_prompt
        prompt = build_rest_prompt(gs, deck=[], relics=[])
        # Numeric heal calc retained
        assert "Healing restores" in prompt
        # Advisory phrases stripped
        assert "Strongly consider healing" not in prompt
        assert "HP is relatively healthy" not in prompt
        assert "Boss is next" not in prompt
        assert "Prioritize healing over upgrading" not in prompt
        assert "Review the Smith upgradeable cards above to assess" not in prompt


def test_baseline_event_strips_trailing_guidance():
    from tests.conftest import make_event_gs
    from src.mcp_client.upstream_models import RawEventOptionPayload
    opts = [
        RawEventOptionPayload(
            index=0, id="OPT_A", title="Option A",
            description="Take 5 HP damage.", is_locked=False,
            is_proceed=False, will_kill_player=False,
        ),
    ]
    gs = make_event_gs(opts)

    with _set_variant("baseline") as _:
        from src.brain.prompts.event import build_event_prompt
        prompt = build_event_prompt(gs, deck=[], relics=[])
        assert "Evaluate each option's risk vs reward" not in prompt
        assert "consider whether your deck needs more damage" not in prompt
        assert "200" not in prompt
        assert "400" not in prompt
        assert "600" not in prompt
        # Live MCP option still rendered
        assert "Option A" in prompt


def test_baseline_treasure_strips_relic_advice():
    from unittest.mock import MagicMock
    gs = MagicMock()
    gs.act = 1
    gs.floor = 9
    gs.player_hp = 60
    gs.player_max_hp = 70
    gs.hp_ratio = 0.86
    gs.gold = 100
    chest = MagicMock()
    relic = MagicMock()
    relic.index = 0
    relic.name = "Anchor"
    relic.rarity = "Common"
    chest.relic_options = [relic]
    gs.chest = chest

    with _set_variant("baseline") as _:
        from src.brain.prompts.treasure import build_treasure_prompt
        prompt = build_treasure_prompt(gs, deck=[], relics=[])
        assert "Almost always take a relic" not in prompt
        assert "Energy/draw relics are S-tier" not in prompt
        assert "Anchor" in prompt  # listing kept


def test_baseline_card_select_strips_mode_hint():
    from tests.conftest import make_card_select_gs
    gs = make_card_select_gs(prompt="Choose a card to upgrade.")

    with _set_variant("baseline") as _:
        from src.brain.prompts.card_select import build_card_select_prompt
        prompt = build_card_select_prompt(gs, deck=[], relics=[])
        assert "biggest dimension boost" not in prompt
        assert "cost reduction > doubled" not in prompt
        assert "Curses/Statuses first" not in prompt
        assert "card most central to your win condition" not in prompt
```

- [ ] **Step 4.2: Run tests, verify they fail**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "rest or event or treasure or card_select"`
Expected: 4 baseline tests fail.

- [ ] **Step 4.3: Gate advisory text in `rest.py`**

Open `src/brain/prompts/rest.py`. Add `import config` at top.

For each advisory line (lines 147, 149, 151, 156, 232, 235, 238 per spec §5.1), wrap the individual append. Example for line 147 area:

```python
            if missing >= heal_amt:
                if config.PROMPT_VARIANT != "baseline":
                    lines.append("Healing uses the full amount with no overflow. You should heal before the boss fight.")
            elif missing >= heal_amt * 0.5:
                if config.PROMPT_VARIANT != "baseline":
                    lines.append("Your deck is mostly finalized. Healing gives you more margin to survive the boss. Strongly consider healing unless HP is already near full.")
            else:
                if config.PROMPT_VARIANT != "baseline":
                    lines.append("HP is relatively healthy. Smith if there is a high-impact upgrade target; otherwise heal to top off.")
```

For the elite_imminent line 156:
```python
        elif elite_imminent:
            heal_amt = int(gs.player_max_hp * 0.3)
            healed = min(gs.player_hp + heal_amt, gs.player_max_hp)
            lines.append("")
            if config.PROMPT_VARIANT != "baseline":
                lines.append(f"⚠ **ELITE FIGHT NEXT** — Healing restores {heal_amt} HP (to {healed}). Weigh that against upgrading a card for every remaining combat.")
            else:
                lines.append(f"Healing restores {heal_amt} HP (to {healed}).")
```

For the lower-section lines (around 230-238), gate similarly. Keep the numeric `Healing restores X HP (Y missing)` line unconditionally; gate the advisory follow-ups.

- [ ] **Step 4.4: Gate trailing 2 lines in `event.py`**

Open `src/brain/prompts/event.py`. Add `import config` at top. Wrap lines 167-168:

```python
    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        lines.append("Evaluate each option's risk vs reward. Consider HP cost, gold cost, and what you gain.")
        lines.append("If an option offers a card: consider whether your deck needs more damage to handle upcoming bosses (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600 in ~10 turns). Prefer damage/poison options when your deck's attack output is low.")
```

- [ ] **Step 4.5: Gate trailing 2 lines in `treasure.py`**

Open `src/brain/prompts/treasure.py`. Add `import config`. Wrap lines 49-50:

```python
    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        lines.append("Almost always take a relic — relics compound across every remaining combat.")
        lines.append("Energy/draw relics are S-tier. Skip only if the downside directly destroys your strategy.")
```

- [ ] **Step 4.6: Gate end hints in `card_select.py`**

Open `src/brain/prompts/card_select.py`. Add `import config`. In `build_card_select_prompt`, wrap lines 304-310:

```python
    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        if is_upgrade:
            lines.append("Upgrade: pick biggest dimension boost (cost reduction > doubled dmg/block > added draw). Never upgrade basic Strike/Defend.")
        elif is_remove:
            lines.append("Remove: Curses/Statuses first, then weakest card. Check deck still functions after removal (enough damage + defense). Don't over-thin.")
        else:
            lines.append("Pick the card most central to your win condition.")
```

In `build_pack_selection_prompt`, wrap line 167:

```python
    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        lines.append(
            "Prefer the pack that best fits the deck's current win condition, curve, and act survival."
        )
```

- [ ] **Step 4.7: Run tests, verify pass**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "rest or event or treasure or card_select"`
Expected: 4 passing.

- [ ] **Step 4.8: Run regression on these prompt files**

Run: `pytest tests/ -k "rest or event or treasure or card_select or upgrade_prompt" -v`
Expected: pass.

- [ ] **Step 4.9: Commit**

```bash
git add src/brain/prompts/rest.py src/brain/prompts/event.py src/brain/prompts/treasure.py src/brain/prompts/card_select.py tests/prompts/test_baseline_variants.py
git commit -m "feat(prompts): gate rest/event/treasure/card_select advisory text on PROMPT_VARIANT"
```

---

## Task 5: potion.py — Threat Assessment + Decision Framework strip

**Files:**
- Modify: `src/brain/prompts/potion.py`
- Test: `tests/prompts/test_baseline_variants.py` (extend)

Spec ref: §5.1 potion.py rows.

- [ ] **Step 5.1: Append failing tests**

```python
# ── potion.py ────────────────────────────────────────────────────

def _build_potion_gs():
    from tests.conftest import make_combat_gs, make_hand_card
    from src.mcp_client.upstream_models import RawRunPotionPayload
    potions = [
        RawRunPotionPayload(
            index=0, potion_id="block_potion", name="Block Potion",
            description="Gain 12 Block.", can_use=True, requires_target=False,
        ),
    ]
    return make_combat_gs(
        hand=[make_hand_card("Strike", 0, playable=True, rules_text="Deal 6 damage.")],
        potions=potions,
    )


def test_baseline_potion_strips_decision_framework():
    with _set_variant("baseline") as _:
        from src.brain.prompts.potion import build_potion_prompt
        prompt = build_potion_prompt(_build_potion_gs())
        assert "Potion Decision Framework" not in prompt
        assert "USE potion when" not in prompt
        assert "SAVE potion when" not in prompt
        assert "Golden rule" not in prompt
        assert "dying with unused potions is the worst outcome" not in prompt


def test_baseline_potion_strips_threat_labels_keeps_numbers():
    with _set_variant("baseline") as _:
        from src.brain.prompts.potion import build_potion_prompt
        prompt = build_potion_prompt(_build_potion_gs())
        # Numeric line retained
        assert "Incoming damage:" in prompt
        # Advisory labels stripped
        assert "LETHAL" not in prompt
        assert "CRITICAL HP" not in prompt
        assert "defensive potions are valuable" not in prompt


def test_full_potion_keeps_decision_framework():
    with _set_variant("full") as _:
        from src.brain.prompts.potion import build_potion_prompt
        prompt = build_potion_prompt(_build_potion_gs())
        assert "Potion Decision Framework" in prompt
        assert "Golden rule" in prompt
```

- [ ] **Step 5.2: Run, verify fail**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "potion"`
Expected: 2 baseline tests fail.

- [ ] **Step 5.3: Gate Threat Assessment advisory lines**

Open `src/brain/prompts/potion.py`. Add `import config`. Modify the `## Threat Assessment` section (lines 110-120):

```python
    lines.append("")
    lines.append("## Threat Assessment")
    lines.append(f"HP: {p.current_hp}/{p.max_hp} ({hp_ratio:.0%}) | Incoming damage: {total_incoming} (after block: {effective_incoming})")
    if config.PROMPT_VARIANT != "baseline":
        if effective_incoming >= p.current_hp:
            lines.append("LETHAL -- you will DIE this turn without Block Potion or killing attackers!")
        elif hp_ratio < 0.25:
            lines.append(f"CRITICAL HP ({p.current_hp}/{p.max_hp} = {hp_ratio:.0%}) -- defensive/healing potions are high priority.")
        elif effective_incoming > 0:
            pct = effective_incoming / p.current_hp if p.current_hp > 0 else 1.0
            if pct >= 0.5:
                lines.append(f"Incoming {effective_incoming} = {pct:.0%} of HP -- defensive potions are valuable.")
```

- [ ] **Step 5.4: Gate `## Potion Decision Framework` block**

Wrap lines 122-148:

```python
    if config.PROMPT_VARIANT != "baseline":
        # Decision framework
        lines.append("")
        lines.append("## Potion Decision Framework")
        # ... existing block through "Golden rule" ...
        lines.append("Golden rule: dying with unused potions is the worst outcome. When in doubt, USE.")
```

- [ ] **Step 5.5: Run tests**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "potion"`
Expected: 3 passing.

- [ ] **Step 5.6: Commit**

```bash
git add src/brain/prompts/potion.py tests/prompts/test_baseline_variants.py
git commit -m "feat(prompts): gate potion Decision Framework + Threat labels on PROMPT_VARIANT"
```

---

## Task 6: hand_select.py — flat list + Tactical Flags strip

**Files:**
- Modify: `src/brain/prompts/hand_select.py`
- Test: `tests/prompts/test_baseline_variants.py` (extend)

Spec ref: §5.1 hand_select.py rows.

- [ ] **Step 6.1: Append failing tests**

```python
# ── hand_select.py ───────────────────────────────────────────────

def _build_hand_select_gs(prompt_text="Discard 1 card.", kind="hand"):
    """Minimal GameState with combat + selection for hand_select prompt."""
    from unittest.mock import MagicMock
    from src.mcp_client.upstream_models import RawSelectionCardPayload
    sel_cards = [
        RawSelectionCardPayload(
            index=0, stable_id="strike::0", card_id="strike", name="Strike",
            card_type="Attack", energy_cost=1, rules_text="Deal 6 damage.",
        ),
        RawSelectionCardPayload(
            index=1, stable_id="sly_card::1", card_id="sly_card", name="Sly Test",
            card_type="Skill", energy_cost=1, rules_text="Sly. Test sly card.",
        ),
        RawSelectionCardPayload(
            index=2, stable_id="curse::2", card_id="curse", name="Bad Curse",
            card_type="Curse", energy_cost=0, rules_text="Take 5 HP damage.",
        ),
    ]
    gs = MagicMock()
    sel = MagicMock()
    sel.kind = kind
    sel.prompt = prompt_text
    sel.min_select = 1
    sel.max_select = 1
    sel.selected_count = 0
    sel.can_confirm = False
    sel.cards = sel_cards
    sel.selectable_cards = sel_cards
    sel.selected_cards = []
    gs.selection = sel
    gs.combat = MagicMock()
    gs.combat.player = MagicMock(
        current_hp=40, max_hp=70, energy=3, block=0, powers=[],
    )
    gs.run_info = MagicMock(max_energy=3)
    gs.enemies = []
    return gs


def test_baseline_hand_select_strips_priority_grouping():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        assert "### Discard FIRST" not in prompt
        assert "### Discard SECOND" not in prompt
        assert "plays for free" not in prompt


def test_baseline_hand_select_strips_tactical_flags():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        assert "## Tactical Flags" not in prompt
        assert "Sandpit" not in prompt
        assert "DEATH COUNTDOWN" not in prompt
        assert "PRIORITY: Discard a Sly card" not in prompt


def test_baseline_hand_select_keeps_mechanic_only_mode_hint():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        # Mechanic statement kept
        assert "Discard = temporary" in prompt
        # Strategy advice stripped — there's no strategy advice for plain discard mode,
        # but verify retain mode strips "Retain every non-harmful card"
        retain_prompt = build_hand_select_prompt(_build_hand_select_gs(prompt_text="Retain up to 2 cards."))
        assert "Retain every non-harmful card" not in retain_prompt


def test_baseline_hand_select_lists_all_cards_flat():
    with _set_variant("baseline") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        # All 3 cards still appear, just without priority groupings
        assert "Strike" in prompt
        assert "Sly Test" in prompt
        assert "Bad Curse" in prompt


def test_full_hand_select_keeps_priority_grouping():
    with _set_variant("full") as _:
        from src.brain.prompts.hand_select import build_hand_select_prompt
        prompt = build_hand_select_prompt(_build_hand_select_gs())
        assert "### Discard FIRST" in prompt or "plays for free" in prompt
```

- [ ] **Step 6.2: Run, verify fail**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "hand_select"`
Expected: 4 baseline tests fail.

- [ ] **Step 6.3: Add flat-list helper**

Open `src/brain/prompts/hand_select.py`. After `_format_card_line` (around line 60), add:

```python
def _render_selectable_cards_flat(selectable_cards) -> list[str]:
    """Render cards as a flat list without priority grouping.

    Used in the baseline ablation variant where strategy hints (Sly first /
    harmful first / non-harmful retain default) are stripped.
    """
    return [_format_card_line(c) for c in selectable_cards]
```

- [ ] **Step 6.4: Gate priority grouping in `## Cards You Can Select`**

Add `import config` at top. Modify the discard branch (around line 184), retain branch (line 207), and exhaust branch (line 224):

```python
    lines.append("")
    lines.append("## Cards You Can Select")

    if config.PROMPT_VARIANT == "baseline":
        lines.extend(_render_selectable_cards_flat(selectable_cards))
    elif is_discard:
        # ... existing priority grouping (Sly first / harmful second / other) ...
    elif is_retain:
        # ... existing skip / keep grouping ...
    else:
        # Flat listing for exhaust/other modes
        for c in selectable_cards:
            lines.append(_format_card_line(c))
```

- [ ] **Step 6.5: Gate `## Tactical Flags` section**

Wrap the entire tactical_flags block (around lines 230-262):

```python
    if config.PROMPT_VARIANT != "baseline":
        # ── Tactical Flags ────────────────────────────────────────
        tactical_flags: list[str] = []

        sly_cards = [c.name for c in selectable_cards if _is_sly(c)]
        if sly_cards and is_discard:
            tactical_flags.append(...)
        # ... existing block including Sandpit warning ...

        if tactical_flags:
            lines.append("")
            lines.append("## Tactical Flags")
            for flag in tactical_flags:
                lines.append(flag)
```

- [ ] **Step 6.6: Gate strategy parts of mode-aware end hint**

Modify the trailing block (around lines 277-290). Keep the mechanic statement; strip strategy advice:

```python
    # Compact mode-aware hint
    lines.append("")
    if is_exhaust:
        if config.PROMPT_VARIANT == "baseline":
            lines.append("Exhaust = GONE forever this combat.")
        else:
            lines.append("Exhaust = GONE forever this combat. Exhaust Curses/Status first, then Strikes, then worst cards. Never exhaust your key scaling cards.")
    elif is_discard:
        lines.append("Discard = temporary (you'll draw them again).")
    elif is_retain:
        if config.PROMPT_VARIANT == "baseline":
            lines.append(
                "Retain = keep for next turn (free extras — you still draw 5 normally; hand cap 10)."
            )
        else:
            lines.append(
                "Retain = keep for next turn. Retained cards are FREE EXTRAS — "
                "you still draw your full 5 cards normally (hand limit 10). "
                "Retain every non-harmful card unless there is a specific reason not to. "
                "Do NOT retain: Status cards, Curses, cards that deal self-damage."
            )
    else:
        lines.append(f'This is a "{kind}" selection. Pick what you need least.')
```

- [ ] **Step 6.7: Run tests**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "hand_select"`
Expected: 5 passing.

- [ ] **Step 6.8: Commit**

```bash
git add src/brain/prompts/hand_select.py tests/prompts/test_baseline_variants.py
git commit -m "feat(prompts): gate hand_select grouping/tactical_flags/advice on PROMPT_VARIANT"
```

---

## Task 7: PROMPT_HINT_FILTER gate (relic_fmt + card_clarifications)

**Files:**
- Modify: `src/brain/prompts/reward.py`
- Modify: `src/brain/prompts/shop.py`
- Modify: `src/brain/prompts/rest.py`
- Modify: `src/brain/prompts/map.py`
- Test: `tests/prompts/test_baseline_variants.py` (extend)

Spec ref: §5.2.

- [ ] **Step 7.1: Append failing tests**

```python
# ── PROMPT_HINT_FILTER ───────────────────────────────────────────

@contextmanager
def _set_hint_filter(value: bool):
    original = os.environ.get("STS2_PROMPT_HINT_FILTER")
    os.environ["STS2_PROMPT_HINT_FILTER"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        # Reload prompt modules that read PROMPT_HINT_FILTER
        from src.brain.prompts import reward, shop, rest, map as map_prompts
        for m in (reward, shop, rest, map_prompts):
            importlib.reload(m)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_PROMPT_HINT_FILTER", None)
        else:
            os.environ["STS2_PROMPT_HINT_FILTER"] = original
        import config
        importlib.reload(config)


def test_hint_filter_strips_relic_synergies_in_shop():
    from tests.conftest import make_shop_gs
    gs = make_shop_gs(relic_name="Anchor")  # Anchor has a curated relic hint

    with _set_hint_filter(True):
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(gs, deck=[], relics=["Anchor"])
        assert "## Relic Synergies" not in prompt
        assert "safe turn 1" not in prompt  # Anchor's strategy hint


def test_hint_filter_strips_card_notes_in_reward():
    from unittest.mock import MagicMock
    gs = _build_reward_gs()
    speedster = MagicMock()
    speedster.index = 1
    speedster.name = "Speedster"
    speedster.upgraded = False
    speedster.rules_text = "Whenever you draw a card, deal 2 damage."
    speedster.resolved_rules_text = speedster.rules_text
    speedster.dynamic_values = []
    gs.reward.card_options.append(speedster)

    with _set_hint_filter(True):
        from src.brain.prompts.reward import build_card_reward_prompt
        prompt = build_card_reward_prompt(gs, deck=[], relics=[])
        assert "## Card Notes" not in prompt
        assert "Turn-start draw does NOT trigger" not in prompt


def test_hint_filter_off_keeps_hints():
    from tests.conftest import make_shop_gs
    gs = make_shop_gs(relic_name="Anchor")

    with _set_hint_filter(False):
        from src.brain.prompts.shop import build_shop_plan_prompt
        prompt = build_shop_plan_prompt(gs, deck=[], relics=["Anchor"])
        assert "## Relic Synergies" in prompt
```

- [ ] **Step 7.2: Run, verify fail**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "hint_filter"`
Expected: 2 baseline tests fail.

- [ ] **Step 7.3: Gate `format_relic_hints` calls**

Open `src/brain/prompts/shop.py` (line 107-109), `rest.py` (line 179-181), `map.py` (lines 46-48 and 116-118). Each call site looks like:

```python
relic_section = format_relic_hints(relics or [], context="<context>")
if relic_section:
    lines.append(relic_section)
```

Wrap each:

```python
if not config.PROMPT_HINT_FILTER:
    relic_section = format_relic_hints(relics or [], context="<context>")
    if relic_section:
        lines.append(relic_section)
```

Add `import config` to `map.py` if not already present.

- [ ] **Step 7.4: Gate `format_card_notes` and `get_inline_warning` calls**

In `src/brain/prompts/reward.py`, the `format_card_notes` call is at the bottom of the card_reward block. Wrap:

```python
if not config.PROMPT_HINT_FILTER:
    offered_names = [c.name for c in rw.card_options]
    deck_names = [d.name for d in deck] if deck else []
    notes = format_card_notes(offered_names, deck_names)
    if notes:
        lines.append(notes)
```

Inside the per-card line builder (`for c in rw.card_options:` loop), wrap the inline warning:

```python
if not config.PROMPT_HINT_FILTER:
    inline_warn = get_inline_warning(c.name)
    if inline_warn:
        base_line += f" {inline_warn}"
```

In `src/brain/prompts/shop.py`, do the same for both `get_inline_warning` (inside the `for c in shop.cards` loop) and `format_card_notes` (after the items listing).

- [ ] **Step 7.5: Run tests**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "hint_filter"`
Expected: 3 passing.

- [ ] **Step 7.6: Run regression on shop / reward / rest / map prompt tests**

Run: `pytest tests/ -k "shop or reward or rest or map_prompt or dps_aware or card_clarifications" -v`
Expected: pass.

- [ ] **Step 7.7: Commit**

```bash
git add src/brain/prompts/reward.py src/brain/prompts/shop.py src/brain/prompts/rest.py src/brain/prompts/map.py tests/prompts/test_baseline_variants.py
git commit -m "feat(prompts): gate relic_fmt + card_clarifications calls on PROMPT_HINT_FILTER"
```

---

## Task 8: KNOWLEDGE_STRICT gate (injector + boss guide)

**Files:**
- Modify: `src/knowledge/injector.py`
- Modify: `src/brain/prompts/_boss_guide_fmt.py`
- Test: `tests/prompts/test_baseline_variants.py` (extend)

Spec ref: §5.3.

- [ ] **Step 8.1: Append failing tests**

```python
# ── KNOWLEDGE_STRICT ─────────────────────────────────────────────

@contextmanager
def _set_knowledge_strict(value: bool):
    original = os.environ.get("STS2_KNOWLEDGE_STRICT")
    os.environ["STS2_KNOWLEDGE_STRICT"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        from src.knowledge import injector
        from src.brain.prompts import _boss_guide_fmt
        importlib.reload(injector)
        importlib.reload(_boss_guide_fmt)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_KNOWLEDGE_STRICT", None)
        else:
            os.environ["STS2_KNOWLEDGE_STRICT"] = original
        import config
        importlib.reload(config)


def test_knowledge_strict_strips_event_outcomes():
    with _set_knowledge_strict(True):
        from src.knowledge.injector import inject_event_knowledge
        from unittest.mock import MagicMock
        kb = MagicMock()
        result = inject_event_knowledge("BUGSLAYER", kb)
        assert result == ""


def test_knowledge_strict_strips_monster_patterns():
    with _set_knowledge_strict(True):
        from src.knowledge.injector import _build_monster_info
        from unittest.mock import MagicMock
        kb = MagicMock()
        enemy = MagicMock()
        enemy.name = "Chomper"
        result = _build_monster_info([enemy], kb)
        assert result == []


def test_knowledge_strict_strips_encounter_classification():
    with _set_knowledge_strict(True):
        from src.knowledge.injector import inject_encounter_knowledge
        from unittest.mock import MagicMock
        kb = MagicMock()
        result = inject_encounter_knowledge({"chomper"}, {"Chomper"}, kb)
        assert result == ""


def test_knowledge_strict_strips_upcoming_boss_guide():
    with _set_knowledge_strict(True):
        from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
        from unittest.mock import MagicMock
        gs = MagicMock()
        gs.upcoming_boss_enemy_keys = ["FrogKnight"]
        store = MagicMock()
        result = format_upcoming_boss_guide(gs, "Silent", store)
        assert result == []


def test_knowledge_strict_off_runs_normally():
    with _set_knowledge_strict(False):
        from src.knowledge.injector import _build_monster_info
        from unittest.mock import MagicMock
        kb = MagicMock()
        kb.monsters.get_combat_summary.return_value = "Chomper: HP 30, attacks 12"
        enemy = MagicMock()
        enemy.name = "Chomper"
        result = _build_monster_info([enemy], kb)
        assert len(result) == 1
        assert "Chomper" in result[0]
```

- [ ] **Step 8.2: Run, verify fail**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "knowledge_strict"`
Expected: 4 strict tests fail.

- [ ] **Step 8.3: Gate `inject_event_knowledge`**

Open `src/knowledge/injector.py`. Add `import config` at top. Modify:

```python
def inject_event_knowledge(event_id: str, kb: GameKnowledge) -> str:
    """Inject event context including structured options when available."""
    if config.KNOWLEDGE_STRICT:
        return ""
    # ... existing body ...
```

- [ ] **Step 8.4: Gate `_build_monster_info`**

```python
def _build_monster_info(
    enemies: list[RawCombatEnemyPayload], kb: GameKnowledge
) -> list[str]:
    """Build monster info lines within token budget."""
    if config.KNOWLEDGE_STRICT:
        return []
    # ... existing body ...
```

- [ ] **Step 8.5: Gate `inject_encounter_knowledge`**

```python
def inject_encounter_knowledge(
    enemy_ids: set[str],
    enemy_names: set[str],
    kb: GameKnowledge,
) -> str:
    """Inject encounter composition at combat start."""
    if config.KNOWLEDGE_STRICT:
        return ""
    # ... existing body ...
```

- [ ] **Step 8.6: Gate `format_upcoming_boss_guide`**

Open `src/brain/prompts/_boss_guide_fmt.py`. Add `import config` at top. Modify:

```python
def format_upcoming_boss_guide(
    gs,
    character: str,
    guide_store: _GuideStoreLike,
) -> list[str]:
    """Return prompt lines injecting CombatGuide(s) for the upcoming act boss(es)."""
    if config.KNOWLEDGE_STRICT:
        return []
    if not character:
        return []
    # ... existing body ...
```

- [ ] **Step 8.7: Run tests**

Run: `pytest tests/prompts/test_baseline_variants.py -v -k "knowledge_strict"`
Expected: 5 passing.

- [ ] **Step 8.8: Run knowledge / injector regression**

Run: `pytest tests/ -k "knowledge or injector or combat_guide_prompt" -v`
Expected: pass.

- [ ] **Step 8.9: Commit**

```bash
git add src/knowledge/injector.py src/brain/prompts/_boss_guide_fmt.py tests/prompts/test_baseline_variants.py
git commit -m "feat(knowledge): gate event/monster/encounter/boss-guide injectors on KNOWLEDGE_STRICT"
```

---

## Task 9: STM_ENABLED gate

**Files:**
- Modify: `src/agent/loop.py`
- Test: `tests/test_agent_stm_gate.py` (new)

Spec ref: §5.4 STM_ENABLED row.

- [ ] **Step 9.1: Write failing test**

Create `tests/test_agent_stm_gate.py`:

```python
"""Tests for STS2_STM_ENABLED=false bypass of STM reads in AgentLoop."""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from unittest.mock import MagicMock

from tests.conftest import make_loop


@contextmanager
def _stm_enabled(value: bool):
    original = os.environ.get("STS2_STM_ENABLED")
    os.environ["STS2_STM_ENABLED"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_STM_ENABLED", None)
        else:
            os.environ["STS2_STM_ENABLED"] = original
        import config
        importlib.reload(config)


def test_stm_disabled_get_short_term_ref_returns_none():
    with _stm_enabled(False):
        loop = make_loop(MagicMock())
        # Even if STM is internally constructed, the gated accessor returns None
        assert loop._get_short_term_ref() is None
        assert loop._hcm_short_term() is None


def test_stm_enabled_get_short_term_ref_returns_object():
    with _stm_enabled(True):
        loop = make_loop(MagicMock())
        # When enabled, accessor returns whatever STM exists (may be None if
        # MemoryManager not initialized in --no-llm mode, but the gate itself
        # does not force-None).
        # We only assert the gate is not the short-circuit cause:
        # call it and accept any non-error result.
        loop._get_short_term_ref()  # must not raise
        loop._hcm_short_term()  # must not raise
```

- [ ] **Step 9.2: Run, verify fail**

Run: `pytest tests/test_agent_stm_gate.py -v`
Expected: `test_stm_disabled_get_short_term_ref_returns_none` fails (returns the actual STM object, not None).

- [ ] **Step 9.3: Gate `_get_short_term_ref`**

Open `src/agent/loop.py`. Locate `_get_short_term_ref` (line 593). Add early return:

```python
    def _get_short_term_ref(self) -> object | None:
        import config
        if not config.STM_ENABLED:
            return None
        # ... existing body ...
```

- [ ] **Step 9.4: Gate `_hcm_short_term`**

Locate `_hcm_short_term` (line 3044). Add identical early return:

```python
    def _hcm_short_term(self):
        import config
        if not config.STM_ENABLED:
            return None
        # ... existing body ...
```

- [ ] **Step 9.5: Verify downstream None-handling**

Each consumer of these accessors must already tolerate `None`. Quick grep verification:

Run: `grep -n "_get_short_term_ref\|_hcm_short_term" src/agent/loop.py`

For each call site, confirm one of:
- `if stm is not None and hasattr(stm, ...)` guard
- `if stm:` truthy check
- The result is passed to a function that accepts None

The audit on lines 2241, 2409, 2563, 3061, 3460, 3500, 3530, 3595, 3744, 3750 was performed during spec writing (§5.4); all consumers are guarded. If a new consumer was added between spec writing and implementation, add a guard.

- [ ] **Step 9.6: Run tests**

Run: `pytest tests/test_agent_stm_gate.py -v`
Expected: 2 passing.

- [ ] **Step 9.7: Run agent loop regression**

Run: `pytest tests/ -k "agent or loop" -v --timeout=60`
Expected: pass.

- [ ] **Step 9.8: Commit**

```bash
git add src/agent/loop.py tests/test_agent_stm_gate.py
git commit -m "feat(agent): gate STM accessors on STM_ENABLED"
```

---

## Task 10: COMBAT_CONVERSATION_ENABLED gate

**Files:**
- Modify: `src/agent/loop.py`
- Modify: `src/brain/v2_engine.py` (single-turn fallback)
- Test: `tests/test_combat_conversation_gate.py` (new)

Spec ref: §5.4 COMBAT_CONVERSATION_ENABLED row.

- [ ] **Step 10.1: Read v2_engine entry point first**

Run: `grep -n "_v2_combat_conversation\|CombatConversation\|add_combat_start\|generate_combat_summary" src/brain/v2_engine.py`

Identify the function that creates the conversation. The agent loop creates `_v2_combat_conversation` at line 2342-2345 (per audit) and calls into v2_engine to drive turn-by-turn plays. v2_engine reads `_v2_combat_conversation` from the agent loop or receives it as a parameter.

- [ ] **Step 10.2: Write failing test**

Create `tests/test_combat_conversation_gate.py`:

```python
"""Tests for STS2_COMBAT_CONVERSATION_ENABLED=false single-turn fallback."""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from unittest.mock import MagicMock

from tests.conftest import make_loop


@contextmanager
def _combat_conv_enabled(value: bool):
    original = os.environ.get("STS2_COMBAT_CONVERSATION_ENABLED")
    os.environ["STS2_COMBAT_CONVERSATION_ENABLED"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_COMBAT_CONVERSATION_ENABLED", None)
        else:
            os.environ["STS2_COMBAT_CONVERSATION_ENABLED"] = original
        import config
        importlib.reload(config)


def test_maybe_create_combat_conversation_returns_none_when_disabled():
    """When STS2_COMBAT_CONVERSATION_ENABLED=false, the factory returns None
    without attempting to construct CombatConversation. Pre-implementation
    this fails with AttributeError (no helper); post-implementation the gate
    short-circuits and returns None."""
    with _combat_conv_enabled(False):
        loop = make_loop(MagicMock())
        result = loop._maybe_create_combat_conversation(MagicMock())
        assert result is None


def test_maybe_create_combat_conversation_helper_exists_when_enabled():
    """Pre-implementation: AttributeError. Post-implementation: helper
    callable. Exact return value depends on whether real CombatConversation
    can be built from a MagicMock backend; we only require the helper exists
    and does not short-circuit to None on the enabled path."""
    with _combat_conv_enabled(True):
        loop = make_loop(MagicMock())
        assert hasattr(loop, "_maybe_create_combat_conversation")
        # Calling with MagicMock may raise inside CombatConversation
        # construction — that's acceptable; we don't assert a return value
        # here. Exception means the gate did not early-return None.
        try:
            loop._maybe_create_combat_conversation(MagicMock())
        except Exception:
            pass
```

- [ ] **Step 10.3: Run, verify fail**

Run: `pytest tests/test_combat_conversation_gate.py -v`
Expected: failures depending on current code state.

- [ ] **Step 10.4: Add gated factory in AgentLoop**

Open `src/agent/loop.py`. Around line 2342 (where `CombatConversation(...)` is constructed), refactor to a helper:

```python
    def _maybe_create_combat_conversation(self, gs):
        """Create a CombatConversation for the current fight, or None when
        STS2_COMBAT_CONVERSATION_ENABLED=false. Call sites already check
        ``self._v2_combat_conversation`` for truthy before use."""
        import config
        if not config.COMBAT_CONVERSATION_ENABLED:
            return None
        from src.brain.conversation import CombatConversation
        return CombatConversation(...)  # existing constructor args
```

Replace the inline construction at lines 2342-2345 with `self._v2_combat_conversation = self._maybe_create_combat_conversation(gs)`. The existing `if self._v2_combat_conversation:` guard at line 2486 already short-circuits when the value is None.

- [ ] **Step 10.5: Verify v2_engine handles None conversation**

Open `src/brain/v2_engine.py`. Search for any unconditional dereference of the conversation. The engine's combat plan loop (driven by `decide_combat`) uses `CombatConversation` to maintain message history across rounds. When the conversation is None:

- Each round must build a fresh single-message context from the current `GameState` (already handled by `_build_state_prompt_v2` which is round-state-driven).
- `add_execution_result` and `generate_combat_summary` calls on the conversation must be no-ops (already guarded by `if self._v2_combat_conversation:` at line 2486-2502).

If `decide_combat` directly accesses the conversation without a guard, add one:

```python
async def decide_combat(self, gs, conversation, ...):
    if conversation is None:
        # Build a fresh single-turn context
        return await self._decide_combat_single_turn(gs, ...)
    # ... existing multi-turn path ...
```

If a `_decide_combat_single_turn` doesn't exist, factor out the single-message build: it composes (system_prompt, state_prompt, knowledge, skill, memory) into one user message and calls the LLM once. No `add_combat_start` / no `add_execution_result`.

- [ ] **Step 10.6: Run tests**

Run: `pytest tests/test_combat_conversation_gate.py -v`
Expected: 2 passing.

- [ ] **Step 10.7: Run combat / v2 regression**

Run: `pytest tests/ -k "combat or v2 or conversation" -v --timeout=60`
Expected: pass.

- [ ] **Step 10.8: Commit**

```bash
git add src/agent/loop.py src/brain/v2_engine.py tests/test_combat_conversation_gate.py
git commit -m "feat(combat): gate CombatConversation creation on COMBAT_CONVERSATION_ENABLED"
```

---

## Task 11: RUN_CONTEXT_ENABLED gate

**Files:**
- Modify: `src/brain/run_context.py`
- Test: `tests/test_run_context_gate.py` (new)

Spec ref: §5.4 RUN_CONTEXT_ENABLED row.

- [ ] **Step 11.1: Write failing test**

Create `tests/test_run_context_gate.py`:

```python
"""Tests for STS2_RUN_CONTEXT_ENABLED=false bypass."""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from unittest.mock import MagicMock


@contextmanager
def _run_context_enabled(value: bool):
    original = os.environ.get("STS2_RUN_CONTEXT_ENABLED")
    os.environ["STS2_RUN_CONTEXT_ENABLED"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        from src.brain import run_context
        importlib.reload(run_context)
        yield run_context
    finally:
        if original is None:
            os.environ.pop("STS2_RUN_CONTEXT_ENABLED", None)
        else:
            os.environ["STS2_RUN_CONTEXT_ENABLED"] = original
        import config
        importlib.reload(config)


def test_run_context_disabled_returns_empty_summary():
    from unittest.mock import MagicMock
    rs = MagicMock()
    rs.character = "Silent"
    rs.combats_total = 5
    rs.combats_won = 3
    rs.floor_snapshots = []
    rs.final_floor = 12
    stm = MagicMock()
    stm.get_deck_summary.return_value = "Deck: 15 cards"

    with _run_context_enabled(False) as run_context:
        view = run_context.RunContextView(run_state=rs, short_term_memory=stm)
        assert view.format_run_summary() == ""


def test_run_context_enabled_returns_summary():
    from unittest.mock import MagicMock
    rs = MagicMock()
    rs.character = "Silent"
    rs.combats_total = 5
    rs.combats_won = 3
    rs.floor_snapshots = []
    rs.final_floor = 12
    stm = None  # avoid deeper mock plumbing

    with _run_context_enabled(True) as run_context:
        view = run_context.RunContextView(run_state=rs, short_term_memory=stm)
        result = view.format_run_summary()
        assert result != ""
        assert "Silent" in result
```

- [ ] **Step 11.2: Run, verify fail**

Run: `pytest tests/test_run_context_gate.py -v`
Expected: `test_run_context_disabled_returns_empty_summary` fails.

- [ ] **Step 11.3: Gate `format_run_summary`**

Open `src/brain/run_context.py`. Add `import config` at top. Modify `format_run_summary`:

```python
    def format_run_summary(self, max_tokens: int = 400) -> str:
        """Generate compact run summary for system prompt injection."""
        import config
        if not config.RUN_CONTEXT_ENABLED:
            return ""
        rs = self._run_state
        if rs is None:
            return ""
        # ... existing body ...
```

- [ ] **Step 11.4: Run tests**

Run: `pytest tests/test_run_context_gate.py -v`
Expected: 2 passing.

- [ ] **Step 11.5: Run run_context regression**

Run: `pytest tests/ -k "run_context" -v`
Expected: pass.

- [ ] **Step 11.6: Commit**

```bash
git add src/brain/run_context.py tests/test_run_context_gate.py
git commit -m "feat(run_context): gate format_run_summary on RUN_CONTEXT_ENABLED"
```

---

## Task 12: Ablation runner extensions

**Files:**
- Modify: `scripts/run_ablation.py`
- Test: `tests/test_run_ablation_conditions.py` (new)

Spec ref: §7 task 10.

- [ ] **Step 12.1: Write failing test**

Create `tests/test_run_ablation_conditions.py`:

```python
"""Tests for run_ablation Condition extensions and matrix generation."""
from __future__ import annotations

from scripts.run_ablation import Condition, build_condition_matrix


def test_baseline_condition_overrides_all_new_flags():
    cond = Condition(
        condition_id="qwen-baseline-strict",
        model_family="qwen",
        skills=False,
        memory=False,
        evolution=False,
        prompt_variant="baseline",
        hint_filter=True,
        knowledge_strict=True,
        stm=False,
        combat_conv=False,
        run_ctx=False,
        boss_hp=False,
    )
    env = cond.to_env_overrides()
    assert env["STS2_PROMPT_VARIANT"] == "baseline"
    assert env["STS2_PROMPT_HINT_FILTER"] == "true"
    assert env["STS2_KNOWLEDGE_STRICT"] == "true"
    assert env["STS2_STM_ENABLED"] == "false"
    assert env["STS2_COMBAT_CONVERSATION_ENABLED"] == "false"
    assert env["STS2_RUN_CONTEXT_ENABLED"] == "false"
    assert env["STS2_INCLUDE_BOSS_HP"] == "false"
    assert env["STS2_SKILLS_ENABLED"] == "false"
    assert env["STS2_MEMORY_ENABLED"] == "false"
    assert env["STS2_EVOLUTION_ENABLED"] == "false"


def test_full_condition_uses_default_values():
    cond = Condition(
        condition_id="qwen-full",
        model_family="qwen",
        skills=True,
        memory=True,
        evolution=True,
    )
    env = cond.to_env_overrides()
    assert env["STS2_PROMPT_VARIANT"] == "full"
    assert env["STS2_PROMPT_HINT_FILTER"] == "false"
    assert env["STS2_KNOWLEDGE_STRICT"] == "false"
    assert env["STS2_STM_ENABLED"] == "true"
    assert env["STS2_COMBAT_CONVERSATION_ENABLED"] == "true"
    assert env["STS2_RUN_CONTEXT_ENABLED"] == "true"
    assert env["STS2_INCLUDE_BOSS_HP"] == "true"
    assert env["STS2_SKILLS_ENABLED"] == "true"


def test_matrix_baseline_strict_id_format():
    matrix = build_condition_matrix(("qwen", "gemini"))
    ids = {c.condition_id for c in matrix}
    assert "qwen-baseline-strict" in ids
    assert "qwen-full" in ids
    assert "gemini-baseline-strict" in ids
    assert "gemini-full" in ids
    # Old "qwen-baseline" must NOT appear (renamed to disambiguate from
    # historical loose-baseline records).
    assert "qwen-baseline" not in ids
    assert "gemini-baseline" not in ids


def test_matrix_baseline_strict_full_strip():
    matrix = build_condition_matrix(("qwen",))
    baseline = next(c for c in matrix if c.condition_id == "qwen-baseline-strict")
    assert baseline.skills is False
    assert baseline.memory is False
    assert baseline.evolution is False
    assert baseline.prompt_variant == "baseline"
    assert baseline.hint_filter is True
    assert baseline.knowledge_strict is True
    assert baseline.stm is False
    assert baseline.combat_conv is False
    assert baseline.run_ctx is False
    assert baseline.boss_hp is False


def test_cli_args_pass_through_existing_flags():
    cond = Condition(
        condition_id="qwen-baseline-strict",
        model_family="qwen",
        skills=False, memory=False, evolution=False,
    )
    args = cond.to_cli_args(tag="t1", character="Silent", ascension=5, steps=500)
    assert "--no-skills" in args
    assert "--no-memory" in args
    assert "--no-evolution" in args
    assert "--no-postrun" in args
```

- [ ] **Step 12.2: Run, verify fail**

Run: `pytest tests/test_run_ablation_conditions.py -v`
Expected: failures (Condition has no new fields; matrix names don't include `-strict`).

- [ ] **Step 12.3: Extend `Condition` dataclass**

Open `scripts/run_ablation.py`. Replace the existing Condition with:

```python
@dataclass(frozen=True)
class Condition:
    condition_id: str
    model_family: str
    skills: bool
    memory: bool
    evolution: bool
    # Ablation baseline gates (added 2026-04-26)
    prompt_variant: str = "full"
    hint_filter: bool = False
    knowledge_strict: bool = False
    stm: bool = True
    combat_conv: bool = True
    run_ctx: bool = True
    boss_hp: bool = True

    def to_cli_args(
        self, *, tag: str, character: str, ascension: int | str, steps: int,
    ) -> list[str]:
        # ... existing CLI args (unchanged) ...

    def to_env_overrides(self) -> dict[str, str]:
        return {
            "STS2_SKILLS_ENABLED": "true" if self.skills else "false",
            "STS2_MEMORY_ENABLED": "true" if self.memory else "false",
            "STS2_EVOLUTION_ENABLED": "true" if self.evolution else "false",
            "STS2_PROMPT_VARIANT": self.prompt_variant,
            "STS2_PROMPT_HINT_FILTER": "true" if self.hint_filter else "false",
            "STS2_KNOWLEDGE_STRICT": "true" if self.knowledge_strict else "false",
            "STS2_STM_ENABLED": "true" if self.stm else "false",
            "STS2_COMBAT_CONVERSATION_ENABLED": "true" if self.combat_conv else "false",
            "STS2_RUN_CONTEXT_ENABLED": "true" if self.run_ctx else "false",
            "STS2_INCLUDE_BOSS_HP": "true" if self.boss_hp else "false",
        }
```

- [ ] **Step 12.4: Update `build_condition_matrix`**

Replace the existing function:

```python
def build_condition_matrix(models: tuple[str, ...] = ("qwen", "gemini")) -> list[Condition]:
    matrix: list[Condition] = []
    for m in models:
        # baseline-strict: every gate set to baseline value
        matrix.append(Condition(
            condition_id=f"{m}-baseline-strict", model_family=m,
            skills=False, memory=False, evolution=False,
            prompt_variant="baseline",
            hint_filter=True,
            knowledge_strict=True,
            stm=False,
            combat_conv=False,
            run_ctx=False,
            boss_hp=False,
        ))
        # full: defaults preserve current behavior
        matrix.append(Condition(
            condition_id=f"{m}-full", model_family=m,
            skills=True, memory=True, evolution=True,
        ))
    return matrix
```

- [ ] **Step 12.5: Run tests**

Run: `pytest tests/test_run_ablation_conditions.py -v`
Expected: 5 passing.

- [ ] **Step 12.6: Verify dry-run output**

Run: `python -m scripts.run_ablation --tag dry-test --runs-per-condition 1 --dry-run --models qwen`

Expected output includes lines like:
```
DRY-RUN qwen-baseline-strict -> ['--model-family', 'qwen', ...]
DRY-RUN qwen-full -> ['--model-family', 'qwen', ...]
```

- [ ] **Step 12.7: Commit**

```bash
git add scripts/run_ablation.py tests/test_run_ablation_conditions.py
git commit -m "feat(ablation): extend Condition with 7 new gates; rename baseline → baseline-strict"
```

---

## Task 13: End-to-end smoke test

**Files:**
- No new files; runs the existing agent in `--no-llm` random-fallback mode with all gates flipped.

Spec ref: §9 validation criteria.

- [ ] **Step 13.1: Run baseline-strict no-LLM smoke**

```bash
STS2_PROMPT_VARIANT=baseline \
STS2_PROMPT_HINT_FILTER=true \
STS2_KNOWLEDGE_STRICT=true \
STS2_STM_ENABLED=false \
STS2_COMBAT_CONVERSATION_ENABLED=false \
STS2_RUN_CONTEXT_ENABLED=false \
STS2_INCLUDE_BOSS_HP=false \
python -m scripts.run_agent --steps 30 --runs 1 --no-llm --no-postrun --no-skills --no-memory --no-evolution --character Silent --ascension 0
```

Expected: agent runs to completion (defeat, max_steps, or victory) without unhandled exceptions. Random-fallback mode means decisions are bad, but they are decisions — no crash on `None` returns or missing context.

- [ ] **Step 13.2: Run full smoke for regression check**

```bash
python -m scripts.run_agent --steps 30 --runs 1 --no-llm --no-postrun --character Silent --ascension 0
```

Expected: agent runs to completion. This verifies default flags still work.

- [ ] **Step 13.3: Verify run_history records new fields**

After Step 13.1, inspect the appended record in `data/runs/history.jsonl` (or sibling repo `runs/history.jsonl` if `STS2_DATA_REPO` is set):

```bash
tail -1 data/runs/history.jsonl | python -m json.tool | grep -A 1 model_profile
```

Expected: `model_profile` dict contains keys `prompt_variant`, `prompt_hint_filter`, `knowledge_strict`, `stm_enabled`, `combat_conversation_enabled`, `run_context_enabled`, `include_boss_hp` with the baseline-strict values.

- [ ] **Step 13.4: Run full test suite**

Run: `pytest tests/ -v --timeout=120 -x`
Expected: all pass. `-x` stops at first failure for fast feedback.

- [ ] **Step 13.5: Commit any incidental fixes**

If steps 13.1-13.3 surfaced minor issues (missing None guards, unhandled edge cases), fix them and commit:

```bash
git add <fixed_files>
git commit -m "fix: address baseline-strict smoke test edge cases"
```

If everything ran clean, no commit needed.

- [ ] **Step 13.6: Final integration commit**

If you split prior tasks into many small commits, you may now squash or leave as-is. The plan does not require squashing — frequent commits are good practice.

---

## Done criteria

- All 12 tasks complete (1-12) with passing tests.
- Smoke runs (Task 13) succeed in both modes.
- `pytest tests/ -v --timeout=120` reports green.
- `python -m scripts.run_ablation --tag smoke-1 --runs-per-condition 1 --models qwen --dry-run` shows 2 conditions per model: `qwen-baseline-strict` and `qwen-full`.

After this, the experiment in spec §8 can run: tag `abl-2026-04-26-baseline-strict`, 20 runs per condition, `python -m scripts.run_ablation --tag abl-2026-04-26-baseline-strict --runs-per-condition 20 --models qwen gemini`.
