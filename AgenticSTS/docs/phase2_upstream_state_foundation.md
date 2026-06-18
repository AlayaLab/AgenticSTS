# Phase 2: Upstream State Foundation

Date: 2026-03-19

## Scope

This phase establishes the Python-side foundation for the real upstream
`STS2-Agent` `/state` payload without cutting over the runtime yet.

Completed here:

- first-class raw `/state.data` models
- first-class `agent_view` models
- direct upstream payload parser
- new convenience wrapper over upstream state
- minimal parser/wrapper validation tests

Not completed here:

- replacing the current `parse_state()` translator path
- rewriting `src/state/game_state.py`
- migrating `client.py`, `sse_client.py`, `actions.py`, `loop.py`, or prompts

## Code Added

- `src/mcp_client/upstream_models.py`
- `src/state/upstream_game_state.py`
- `tests/test_upstream_state_parser.py`

## Code Updated

- `src/state/state_parser.py`

## New Entry Points

- `parse_upstream_state_payload(raw_json)`
- `safe_parse_upstream_state_payload(raw_json)`
- `parse_upstream_game_state(raw_json)`
- `safe_parse_upstream_game_state(raw_json)`
- `unwrap_state_payload(raw_json)`

## Preserved Upstream Fields

The new models explicitly preserve the fields that were called out as
non-negotiable in the migration plan, including:

- `combat.players`
- `run.players`
- `character_name`
- `base_orb_slots`
- `focus`
- orb `slot_index`
- orb `is_front`
- `target_index_space`
- `valid_target_indices`
- `star_costs_x`
- `selection.min_select`
- `selection.max_select`
- `selection.requires_confirmation`
- `event.options[].will_kill_player`
- `shop.is_open`
- `shop.can_open`
- `shop.can_close`
- `shop.card_removal`
- `agent_view.glossary` as `dict[str, str]`

## Validation Performed

`pytest` and `ruff` were not installed in the current Python environment, so the
validation in this phase used:

- `python -m compileall src tests`
- direct import-and-run of the parser/wrapper test functions

Those checks passed locally.

## Current Boundary

The active runtime still uses:

- legacy `parse_state()`
- `src/mcp_client/state_translator.py`
- existing `src/state/game_state.py`

This is intentional. Phase 2 added a parallel new path without breaking the old one.

## Recommended Next Step

Start Phase 3 by rewriting `src/state/game_state.py` around the new upstream models
or by gradually switching call sites to `parse_upstream_game_state()` and the new
wrapper before touching transport and loop logic.
