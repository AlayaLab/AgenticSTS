# Phase 0: Migration Baseline Inventory

## Current Singleplayer Capabilities (this repo)

### State Parsing
- Parses via `state_translator.py` (translation layer)
- 13 Pydantic frozen models in old format
- `state_type` is the primary router (50+ consumers)
- Available actions translated from new→old names

### Combat
- Full combat loop: plan-then-execute (Sonnet) + single-card fallback (Haiku)
- Card targeting by `entity_id` string (fabricated `"EnemyId_Index"`)
- Potion check per round
- Draw-card detection → re-plan

### Navigation
- Route planning per act (LLM)
- Map node selection (LLM)
- HP-gated rest forcing (<25%)

### Decision Pipeline
- 11 multi-factor scoring prompts
- 12 Claude tool definitions for structured output
- 3-stage retry: LLM → error feedback → non-thinking → mechanical
- Context assembly: knowledge + skills + memory + relics + archetype

### Memory
- V1: 3-layer (episodes, reflections, rules)
- V2 HCM: domain stores (combat, route, card_build) + guide consolidation
- Short-term: mutable trackers within run

### Skills
- 49 seed skills across 9 categories
- Confidence tracking + post-run discovery

### Knowledge
- 577 cards, 121 monsters, 64 potions, 68 events
- Web search + archetype system (339 card ratings)
- Boss strategy fetch at combat start

---

## Current Upstream Capabilities (STS2-Agent v0.5.2)

### API Endpoints
- `GET /health` — health check with mod/protocol version
- `GET /state` — full state with raw + agent_view
- `POST /action` — unified action endpoint with stability tracking
- `GET /events/stream` — SSE with 15s heartbeat
- `GET /actions/available` — action descriptors

### State Payload
- `state_version: 6`
- `screen` enum (COMBAT, MAP, EVENT, REST, SHOP, REWARD, CARD_SELECTION, CHEST, GAME_OVER, MAIN_MENU, CHARACTER_SELECT, TIMELINE, MODAL)
- 41 supported actions
- Raw payload: full game state with all fields
- `agent_view`: prompt-facing compact payload with glossary, card stacks, pile contents

### Fields NOT in our current models (information loss)
- `focus` (Defect orb scaling)
- `is_alive`, `is_hittable` (enemy state)
- `valid_target_indices`, `target_index_space`, `requires_target` (card/potion targeting)
- `will_kill_player` (event safety)
- `min_select`, `max_select`, `requires_confirmation` (selection constraints)
- `is_front`, `slot_index` (orb ordering)
- `is_melted` (relic destruction)
- `option_id` (rest option identity)
- Draw/discard/exhaust pile contents (only via agent_view)
- Card modifier tags (only via agent_view)
- Glossary/keyword extraction (only via agent_view)
- `run_id`, `state_version` (session tracking)
- `stable`, `status` in action responses (stability tracking)

### Action Contract Differences
| Our internal name | Upstream name |
|-------------------|---------------|
| `play_card(card_index, target=entity_id_str)` | `play_card(card_index, target_index=int)` |
| `shop_purchase(index)` | `buy_card(option_index)` / `buy_relic(option_index)` / `buy_potion(option_index)` / `remove_card_at_shop()` |
| `select_card_reward(card_index)` | `choose_reward_card(option_index)` |
| `skip_card_reward()` | `skip_reward_cards()` |
| `combat_select_card(card_index)` | `select_deck_card(option_index)` |
| `combat_confirm_selection()` | `confirm_selection()` |
| `select_card(index)` | `select_deck_card(option_index)` |
| `claim_treasure_relic(index)` | `choose_treasure_relic(option_index)` |
| `advance_dialogue()` | `choose_event_option(option_index=0)` |

---

## File-Level Dependency on Old Semantics

### Critical (100+ field accesses)
- `src/agent/loop.py` — state_type routing, entity_id targeting, battle.player.hand, shop.items flat list

### Heavy (30-85 accesses)
- `src/brain/prompts/combat.py` — PlayerCombat (hand, energy, hp, powers), EnemyInfo (entity_id, hp, intents)
- `src/brain/prompts/combat_plan.py` — same as combat.py
- `src/brain/prompts/potion.py` — PlayerCombat.potions (slot, can_use_in_combat)
- `src/log/session_logger.py` — nearly all model fields
- `src/state/game_state.py` — GameStateResponse wrapping

### Medium (10-30 accesses)
- `src/knowledge/injector.py` — CardInfo, EnemyInfo, PotionInfo type imports
- `src/brain/tool_schemas.py` — old action names in enums
- `src/brain/planner.py` — PlannedAction.target as string, card.can_play
- `src/brain/strategy_selector.py` — battle.is_play_phase, hand_select.selectable_cards
- `src/brain/reasoner.py` — LLMDecision.to_action() param handling
- `src/brain/prompts/shop.py` — shop.items flat iteration
- `src/brain/prompts/event.py` — event_name, body_text
- `src/brain/prompts/reward.py` — CardRewardChoice fields
- `src/brain/prompts/rest.py` — RestOption.id
- `src/brain/prompts/map.py` — MapNextOption.type
- `src/brain/prompts/card_select.py` — CardSelectCard fields
- `src/brain/prompts/hand_select.py` — HandSelectCard fields
- `src/brain/prompts/treasure.py` — TreasureRelic fields

### Light (1-10 accesses)
- `src/memory/short_term.py` — called from loop.py with extracted primitives
- `src/memory/extractor.py` — reads Decision objects
- `src/memory/combat_extractor.py` — reads ShortTermMemory
- `src/memory/route_extractor.py` — reads ShortTermMemory
- `src/memory/card_build_extractor.py` — reads ShortTermMemory
- `src/memory/retriever.py` — character source
- `src/mcp_client/sse_client.py` — state_type, battle.is_play_phase

---

## Local Features to Preserve

### Must Preserve
1. Combat plan-then-execute architecture (single LLM call per round)
2. 3-tier model routing (Haiku/Sonnet/Opus per state type)
3. Memory V1+V2 with post-run extraction and guide consolidation
4. 49 seed skills + confidence tracking
5. Knowledge database (577 cards, 121 monsters, 64 potions, 68 events)
6. Web search + archetype system
7. Session logging (JSONL)
8. Relic synergy system (35 relics with context-filtered hints)

### Evaluate vs Upstream
1. Glossary/keyword quality: compare our knowledge injector vs agent_view.glossary
2. Card formatting: compare our prompt formatting vs agent_view.line
3. Intent formatting: compare our _intent_fmt.py vs agent_view enemy intent display

---

## Answer: "What breaks if translator disappears?"

Every file in the "Critical" and "Heavy" sections above. Specifically:
- loop.py: 100+ old field accesses will fail
- All 11 prompt files: old model types and field names
- game_state.py: wraps old GameStateResponse
- state_parser.py: calls translate_state()
- tool_schemas.py: old action names in enums
- session_logger.py: old field names in logging
- knowledge/injector.py: old model type references

Total: ~28 files, ~500+ individual field accesses to migrate.
