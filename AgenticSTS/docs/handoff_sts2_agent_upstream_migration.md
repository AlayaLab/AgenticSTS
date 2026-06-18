# Handoff Plan: Singleplayer MCP Upstream Migration to STS2-Agent

## Purpose

This document is the corrected migration plan for moving the current `AgenticSTS`
Python agent and MCP integration onto the newer `STS2-Agent` codebase as the
singleplayer upstream.

This replaces the earlier idea of keeping or expanding a translation layer between:

- the current Python agent in this repository
- the current local mixed MCP/mod stack
- the newer `Github\STS2-Agent` project

The core conclusion is:

1. Do not build a new long-term translator layer.
2. Use `STS2-Agent` as the new C# singleplayer upstream.
3. Migrate the Python side to the real upstream schema and action contract.
4. Preserve any local capabilities that are still better than upstream by porting
   them into our fork when needed.

This plan is intended for review and execution by Claude.

---

## Scope

### In Scope

- Singleplayer only
- C# mod upstream choice and migration path
- Python parser/model/action/prompt/agent-loop migration
- Build, validation, and regression strategy
- Preservation of local features that matter to current behavior quality

### Out of Scope

- Multiplayer support
- Maintaining compatibility with the old `/api/v1/singleplayer` schema
- Keeping old LLM tool schemas or old action names as the internal source of truth

---

## Final Decision

### Upstream Decision

Use `Github\STS2-Agent` as the new C# upstream baseline for singleplayer.

### License Decision

The project may move to AGPL, so direct upstream reuse is acceptable from a licensing
perspective. This removes the strongest non-technical blocker.

### Migration Strategy

Do not keep the current translator-centered architecture as the long-term design.

The current Python stack already depends on the new API transport at `localhost:8080`,
but it still reconstructs old semantics through `src/mcp_client/state_translator.py`.
That translator is now technical debt, not a stable abstraction.

The target architecture should be:

- C# fork of `STS2-Agent` as the source of truth
- Python raw-state models aligned with the real `/state` payload
- Python `agent_view` models aligned with the upstream compact prompt-facing payload
- A thin `GameState` convenience wrapper for Python callers
- No fake old-state reconstruction as an internal dependency

---

## Why the Previous Plan Needs Correction

The previous plan was directionally right about removing information loss, but it
missed several important points.

### 1. It treats raw payload as the only useful schema

Upstream already exposes both:

- the raw `/state` payload
- the derived `agent_view` payload

`agent_view` contains useful prompt-facing information such as:

- glossary extraction
- normalized hand/deck/shop card lines
- target hints
- compact card pile formatting

If the migration only models raw payload 1:1 and ignores `agent_view`, it throws away
useful upstream work and forces the Python side to rebuild it.

### 2. It underestimates the migration surface

The Python side is not only using old models. It also uses old semantics in:

- `src/agent/loop.py`
- `src/brain/tool_schemas.py`
- `src/brain/prompts/*.py`
- `src/log/session_logger.py`
- `src/knowledge/injector.py`
- `src/memory/retriever.py`

The migration is not "models + parser + a few field renames". It is a contract change
across state parsing, LLM output schema, validation logic, and execution flow.

### 3. It misses upstream fields we should not silently drop

Examples of upstream fields that must be accounted for:

- `combat.players`
- `run.players`
- `character_name`
- `base_orb_slots`
- `star_costs_x`
- `multiplayer`
- `multiplayer_lobby`

Even if multiplayer is out of scope, the parser should tolerate these fields.

### 4. It does not explicitly preserve local strong points

The current local code still has useful ideas that may be better than upstream in some
places, especially:

- hover-tip / keyword extraction behavior
- glossary density and richness
- local logging and memory integration expectations

These need explicit preservation gates, not an implicit assumption that upstream is
always better.

### 5. It deletes the translator too early

The translator should not be removed until:

- raw models exist
- `agent_view` models exist
- `GameState` has been rewritten
- loop/prompt/tool/action code has been migrated
- validation and regression checks pass

---

## Non-Negotiable Migration Principles

1. No new long-term translator layer.
2. Raw upstream payload becomes the execution truth.
3. `agent_view` is preserved and used where it adds value.
4. Python convenience wrappers may stay, but they must not invent fake old semantics.
5. LLM output must be changed to the real upstream action contract.
6. Target validation must use `target_index_space` and `valid_target_indices`.
7. Any local feature that is better than upstream must be ported intentionally or
   explicitly abandoned with a decision record.
8. Old compatibility code is removed only after passing a defined cutover gate.

---

## Preservation Requirements

The migration is not acceptable if it loses any of the following without an explicit
decision.

### Must Preserve

- Defect/Regent combat fidelity:
  - `focus`
  - orb ordering / front-slot information
  - `star_costs_x`
- Target legality:
  - `requires_target`
  - `target_index_space`
  - `valid_target_indices`
- Selection constraints:
  - `min_select`
  - `max_select`
  - `requires_confirmation`
- Event safety:
  - `will_kill_player`
- Shop semantics:
  - inventory open/close state
  - separate purchase actions
  - card removal semantics
- Existing Python systems:
  - memory hooks
  - session logging
  - skills injection
  - knowledge injection
- Glossary / keyword assistance at prompt time

### Acceptable to Drop

- Legacy old action names as an internal contract
- Old old-style `state_type` as the true parser root
- Old shop flattening if typed shop sections are adopted everywhere
- Multiplayer payload consumption in Python business logic

---

## Target Architecture

### C# Layer

Base the mod on a fork of `STS2-Agent`.

That fork becomes the upstream we actually maintain and build.

Expected C# responsibilities:

- expose stable singleplayer raw `/state`
- expose stable `agent_view`
- preserve or improve glossary/keywords quality
- keep upstream singleplayer action semantics
- keep upstream test and validation scripts where practical

### Python Layer

The Python side should be split into four layers:

1. `raw` models
   - exact schema for `/state.data`
   - used for validation, execution, index checks, and logic

2. `agent_view` models
   - exact schema for `/state.data.agent_view`
   - used for prompt rendering and compact context

3. `GameState`
   - convenience wrapper
   - exposes stable Pythonic helpers like `hand`, `energy`, `deck`, `potions`
   - may derive `state_type` for internal routing convenience

4. business logic
   - loop
   - prompts
   - reasoner
   - memory
   - logger

### Action Contract

All Python execution paths must use the real upstream action names and parameter names.

That means the long-term internal contract should use examples like:

- `play_card(card_index, target_index)`
- `use_potion(option_index, target_index)`
- `choose_reward_card(option_index)`
- `select_deck_card(option_index)`
- `buy_card(option_index)`
- `buy_relic(option_index)`
- `buy_potion(option_index)`
- `remove_card_at_shop()`
- `choose_treasure_relic(option_index)`
- `collect_rewards_and_proceed()`

Not old compatibility names like:

- `shop_purchase`
- `select_card_reward`
- `combat_select_card`
- `claim_treasure_relic`
- string `target` using synthetic `entity_id`

---

## Phase Plan

### Phase 0: Freeze Baseline and Inventory

### Goal

Create a clear pre-migration baseline so regression is measurable.

### Tasks

- Record current singleplayer capabilities in this repository.
- Record current upstream singleplayer capabilities from `STS2-Agent`.
- Record all Python files that still depend on old semantics.
- Record all local features that must be preserved.

### Deliverables

- capability matrix
- field/action dependency inventory
- explicit preservation list

### Exit Criteria

- We can answer "what will break if the translator disappears?" with a file-level list.

---

### Phase 1: Fork and Build Baseline

### Goal

Adopt `STS2-Agent` as the maintained C# upstream fork and make local builds repeatable.

### Tasks

- Create or designate the maintained upstream fork.
- Standardize local build configuration around `Sts2DataDir`.
- Confirm local DLL build works with the actual game install path.
- Decide whether to keep upstream scripts unchanged or mirror them into this repo.

### Deliverables

- documented build command
- documented game path configuration
- successful local build of the new mod

### Exit Criteria

- `dotnet build` for the new upstream fork succeeds on the local machine with a
  documented path override.

---

### Phase 2: Define Python Raw and Agent-View Models

### Goal

Add first-class models for the real upstream payloads.

### Tasks

- Create raw payload models for `/state.data`.
- Create `agent_view` payload models for `/state.data.agent_view`.
- Keep them as exact schema models, not compatibility shapes.
- Include upstream fields that are currently unused but structurally important.

### Required Fields to Include

- raw root:
  - `state_version`
  - `run_id`
  - `screen`
  - `session`
  - `in_combat`
  - `turn`
  - `available_actions`
  - `combat`
  - `run`
  - `map`
  - `selection`
  - `character_select`
  - `timeline`
  - `chest`
  - `event`
  - `shop`
  - `rest`
  - `reward`
  - `modal`
  - `game_over`
  - `agent_view`

- important nested fields:
  - `combat.players`
  - `combat.player.focus`
  - `combat.player.orbs[].slot_index`
  - `combat.player.orbs[].is_front`
  - `combat.hand[].target_index_space`
  - `combat.hand[].valid_target_indices`
  - `combat.hand[].star_costs_x`
  - `combat.enemies[].is_alive`
  - `combat.enemies[].is_hittable`
  - `run.character_name`
  - `run.base_orb_slots`
  - `run.players`
  - `run.potions[].target_index_space`
  - `run.potions[].valid_target_indices`
  - `selection.min_select`
  - `selection.max_select`
  - `selection.requires_confirmation`
  - `event.options[].will_kill_player`
  - `shop.is_open`
  - `shop.can_open`
  - `shop.can_close`
  - `shop.card_removal`

### Deliverables

- new Python models for raw state
- new Python models for `agent_view`

### Exit Criteria

- real upstream state payload validates successfully without translation.

---

### Phase 3: Rewrite Parser and GameState Wrapper

### Goal

Make the Python state entrypoint consume real upstream state and expose stable helpers.

### Tasks

- Rewrite `src/state/state_parser.py` to parse real upstream payload directly.
- Rewrite `src/state/game_state.py` around raw + `agent_view`.
- Keep convenience properties that the rest of the codebase needs.
- Derive internal `state_type` only as a convenience label, not as the parser root.

### Required GameState Convenience Surface

- phase helpers:
  - `is_combat`
  - `is_reward`
  - `is_choice`
  - `is_map`
  - `is_in_run`

- combat helpers:
  - `hand`
  - `playable_cards`
  - `enemies`
  - `energy`
  - `player_hp`
  - `player_max_hp`
  - `gold`

- run helpers:
  - `deck`
  - `relics`
  - `potions`
  - `character`

- typed access:
  - `combat`
  - `selection`
  - `reward`
  - `shop`
  - `event`
  - `rest`
  - `chest`
  - `modal`
  - `game_over_info`
  - `agent_view`

### Exit Criteria

- Existing Python callers can read stable convenience properties from the new wrapper.

---

### Phase 4: Migrate Client, SSE, and Action Builders

### Goal

Remove old compatibility assumptions from transport and action code.

### Tasks

- Update `src/mcp_client/client.py` to stop calling the translator.
- Update `src/mcp_client/sse_client.py` to stop calling the translator.
- Rewrite `src/mcp_client/actions.py` around real upstream action names and params.
- Ensure menu and lifecycle actions use upstream singleplayer actions directly.

### Important Action Migration Rules

- use `target_index`, not synthetic `entity_id`
- use `option_index` where upstream expects it
- use typed shop actions
- preserve `collect_rewards_and_proceed`
- preserve modal actions

### Exit Criteria

- The client can read state and dispatch actions without compatibility translation.

---

### Phase 5: Rewrite Loop Execution Contract

### Goal

Move the agent loop away from old action names and old target semantics.

### Tasks

- Remove old internal action translation logic in `src/agent/loop.py`.
- Change decision validation to use real action names.
- Replace synthetic target string resolution with direct target-index logic.
- Validate targets against:
  - `requires_target`
  - `target_index_space`
  - `valid_target_indices`

### Required Behavioral Changes

- No new use of fake `entity_id` as an internal control contract.
- No shop flattening dependency in core execution.
- No "pick first alive enemy" fallback when the state already exposes legal targets.
- Potion targeting must use the same legality checks as card targeting.

### Exit Criteria

- `loop.py` can execute the full singleplayer flow with real upstream actions.

---

### Phase 6: Rewrite Tool Schemas and Prompts

### Goal

Make LLM outputs match the real API and use richer upstream context.

### Tasks

- Rewrite `src/brain/tool_schemas.py` to the real action vocabulary.
- Rewrite combat prompt outputs from `target` string to `target_index` integer.
- Rewrite shop prompt outputs from `shop_purchase` to typed purchase actions.
- Rewrite reward/select prompts to use upstream names.
- Inject new target legality and selection-count information into prompts.
- Evaluate whether prompts should read primarily from raw models, `agent_view`, or both.

### Prompt-Specific Must-Haves

- Combat:
  - show legal targets
  - use target indices
  - preserve intent visibility
  - preserve focus/orb visibility

- Potion:
  - use option index
  - expose legal targets

- Event:
  - mark lethal options using `will_kill_player`

- Selection:
  - expose `min_select`, `max_select`, and confirmation rules

- Shop:
  - render typed shop sections
  - respect inventory open/close semantics

### Exit Criteria

- LLM-produced actions are already in upstream format and do not need post-hoc name translation.

---

### Phase 7: Migrate Logging, Memory, Knowledge, and Auxiliary Systems

### Goal

Ensure the non-control systems continue to work after the state contract change.

### Tasks

- update `src/log/session_logger.py`
- update `src/knowledge/injector.py`
- update memory extractors and retrievers where they read old fields
- preserve card/relic/potion/deck context for memory and prompt injection

### Special Preservation Check

Compare old glossary/keyword quality against upstream `agent_view.glossary`.

If upstream is weaker in practice, port the stronger local behavior into the new fork
instead of accepting a regression.

### Exit Criteria

- Logging and memory continue to record meaningful singleplayer data under the new schema.

---

### Phase 8: Import Validation Scripts and Run Regression

### Goal

Use upstream's stronger validation discipline before removing old compatibility code.

### Tasks

- Import or mirror the upstream singleplayer validation scripts that matter:
  - state invariants
  - target-index contract
  - action lifecycle tests
  - mod load checks
- Adapt paths/config only as needed.
- Run the new mod plus Python agent against these checks.

### Required Minimum Validation

- state payload validates
- target-index legality behaves correctly
- reward flow works
- selection flow works
- potion flow works
- new-run / continue-run lifecycle works

### Exit Criteria

- Singleplayer regression suite passes at the mod-contract level.

---

### Phase 9: Cutover and Remove Compatibility Code

### Goal

Delete the old translator architecture after the new path is proven.

### Tasks

- remove `src/mcp_client/state_translator.py`
- remove old action-name compatibility branches
- remove old prompt/output compatibility assumptions
- update architecture docs to reflect the new design

### Hard Cutover Gate

Do not perform this phase until all of the following are true:

1. new C# fork builds locally
2. raw and `agent_view` models parse real state successfully
3. loop execution no longer relies on old action names
4. prompt and schema outputs match upstream actions
5. singleplayer regression checks pass
6. no unacceptable glossary/keyword regression exists

---

## File-Level Execution Checklist

### C# Upstream Fork

- [ ] Create/confirm maintained AGPL fork of `STS2-Agent`
- [ ] Standardize local build configuration for `Sts2DataDir`
- [ ] Confirm `dotnet build` succeeds with local game path
- [ ] Decide whether to modify upstream now or only after Python migration reveals gaps
- [ ] If needed, port stronger local glossary/keyword extraction into the fork

### Python State Layer

- [ ] Rewrite `src/mcp_client/models.py`
- [ ] Add raw `/state` payload models
- [ ] Add `agent_view` models
- [ ] Cover `star_costs_x`
- [ ] Cover `combat.players` and `run.players`
- [ ] Rewrite `src/state/state_parser.py`
- [ ] Rewrite `src/state/game_state.py`

### Python Transport Layer

- [ ] Update `src/mcp_client/client.py`
- [ ] Update `src/mcp_client/sse_client.py`
- [ ] Rewrite `src/mcp_client/actions.py`
- [ ] Stop importing or using `state_translator`

### Agent Execution

- [ ] Rewrite `src/agent/loop.py` around real action names
- [ ] Remove old `entity_id`-based targeting contract
- [ ] Validate against `valid_target_indices`
- [ ] Switch shop execution to typed purchase actions
- [ ] Keep menu/start-run handling aligned with upstream lifecycle actions

### LLM Layer

- [ ] Rewrite `src/brain/tool_schemas.py`
- [ ] Rewrite `src/brain/planner.py` target contract
- [ ] Rewrite `src/brain/reasoner.py` integer parameter handling
- [ ] Rewrite `src/brain/strategy_selector.py` state access if needed

### Prompt Layer

- [ ] Rewrite `src/brain/prompts/combat.py`
- [ ] Rewrite `src/brain/prompts/combat_plan.py`
- [ ] Rewrite `src/brain/prompts/potion.py`
- [ ] Rewrite `src/brain/prompts/shop.py`
- [ ] Rewrite `src/brain/prompts/event.py`
- [ ] Rewrite `src/brain/prompts/rest.py`
- [ ] Rewrite `src/brain/prompts/reward.py`
- [ ] Rewrite `src/brain/prompts/map.py`
- [ ] Rewrite `src/brain/prompts/card_select.py`
- [ ] Rewrite `src/brain/prompts/hand_select.py`
- [ ] Rewrite `src/brain/prompts/treasure.py`

### Logging / Memory / Knowledge

- [ ] Update `src/log/session_logger.py`
- [ ] Update `src/knowledge/injector.py`
- [ ] Update `src/memory/short_term.py` if field names changed
- [ ] Update `src/memory/extractor.py` if field names changed
- [ ] Update `src/memory/combat_extractor.py` if field names changed
- [ ] Update `src/memory/route_extractor.py` only if route contract changes
- [ ] Update `src/memory/card_build_extractor.py` only if deck/reward contract changes
- [ ] Update `src/memory/retriever.py` character source and combat accessors

### Validation

- [ ] Import/adapt upstream singleplayer test scripts
- [ ] Add parser validation test(s)
- [ ] Add GameState wrapper validation test(s)
- [ ] Add prompt smoke tests for changed schemas
- [ ] Run local mod build
- [ ] Run state contract checks
- [ ] Run target-index checks
- [ ] Run at least one short agent integration run

### Cleanup

- [ ] Delete `src/mcp_client/state_translator.py`
- [ ] Remove translator imports
- [ ] Remove old action-name compatibility maps
- [ ] Update architecture docs and `CLAUDE.md`

---

## Acceptance Gates

### Gate A: Build Gate

- new upstream fork builds locally
- build path configuration is documented

### Gate B: Parse Gate

- raw `/state` validates
- `agent_view` validates
- no translator required

### Gate C: Execution Gate

- play card works
- targeted play works
- potion use works
- reward flow works
- selection flow works
- shop flow works
- menu lifecycle works

### Gate D: Quality Gate

- no loss of target legality information
- no loss of selection-constraint information
- no loss of Defect/Regent combat fidelity
- no unacceptable glossary/keyword regression
- memory and logger still produce useful data

### Gate E: Cleanup Gate

- translator removed
- old compatibility action names removed from internal logic
- docs updated

---

## Explicit Risks

### Risk 1: Prompt regression despite better raw data

Even if raw schema is better, prompt quality may drop if `agent_view` or glossary usage is
not preserved.

Mitigation:

- evaluate prompts with both raw and `agent_view`
- keep glossary quality as an explicit acceptance item

### Risk 2: Hidden old-contract assumptions in loop and prompts

The largest migration risk is not parsing. It is old assumptions surviving in the
decision pipeline.

Mitigation:

- migrate tool schemas and prompts early
- remove old action-name translation before final cutover

### Risk 3: Local stronger behavior gets silently lost

Mitigation:

- compare old local feature quality against upstream
- port stronger local behavior into the upstream fork where needed

### Risk 4: Cleanup happens before validation is strong enough

Mitigation:

- import/adapt upstream validation scripts before deleting the translator

---

## Claude Execution Notes

When executing this migration, Claude should follow these rules:

1. Treat this as a phased migration, not a one-shot rewrite.
2. Do not delete the translator until the cutover gate is explicitly met.
3. Prefer keeping old Python convenience APIs only when they are thin wrappers over
   real upstream state.
4. Use upstream action names and integer target indices as the internal contract.
5. Preserve or port any local feature that is demonstrably better than upstream for
   singleplayer quality.
6. Ignore multiplayer business logic unless its presence affects parser correctness.
7. Keep validation visible and phase-gated.

---

## Recommended First Execution Slice

The first implementation slice should be intentionally narrow:

1. Fork/build baseline for `STS2-Agent`
2. Add raw + `agent_view` Python models
3. Rewrite parser and `GameState`
4. Keep translator temporarily as fallback only
5. Add parser validation tests

Do not start by rewriting every prompt.
Do not start by deleting old compatibility code.
Do not start by porting multiplayer logic.

This first slice should establish that the new source of truth is structurally sound
before touching the full decision pipeline.

---

## Post-Migration TODO

### ~~rules_text contains unresolved templates~~ DONE (2026-03-19)

Fixed in C# fork: `GetDescriptionForPile(PileType.Hand)` resolves all templates.
Also added `target_previews` with per-target Vulnerable-aware damage.

### ~~STS2MCP submodule removal~~ DONE (2026-03-19)

Submodule deinited, .gitmodules removed, all references cleaned.

### agent_view integration for prompt quality

Evaluate whether prompt rendering should read from `agent_view` fields:
- `agent_view.combat.draw/discard/exhaust` — pile contents (not in raw API)
- `agent_view.run.piles` — draw/discard/exhaust outside combat
- `agent_view.glossary` — keyword definitions vs local knowledge system
- `agent_view.combat.hand[].keywords/mods` — keyword + modifier tags

### Shop flow polish

- LLM doesn't know `remove_card_at_shop` has been used this visit
- open/close inventory state machine still has edge cases
- Prompt should show which actions are currently available

### Batch API not supported by proxy

`/v1/messages/batches` returns 404 on the proxy.example.com proxy. Post-run batch
analysis (reflection/distillation/discovery) falls back to heuristic mode.
Not a blocker but reduces post-run learning quality.
