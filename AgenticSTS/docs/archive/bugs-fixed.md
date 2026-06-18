# Bugs Fixed (Archive)

Archived from CLAUDE.md on 2026-04-05. All bugs below are resolved.

## 2026-03-29
- **Thinking wastes 95% of tokens** (CRITICAL): proxy.example.com proxy drops tool_use blocks when response contains text + tool_use (multi-block). With thinking enabled, model produces thinking text before tool_use → proxy strips tool_use → V2Engine retries without thinking → tokens wasted. 321K tokens wasted per run (39/80 calls broken). Fix: thinking disabled for all tool_use paths (V2Engine gameplay + EvolutionEngine), kept for text-only post-run calls (call_raw). Circuit breaker removed (never triggered — proxy silently drops blocks instead of erroring).
- **Thinking restored via streaming** (IMPROVEMENT): Codex discovered `messages.stream().get_final_message()` bypasses proxy block stripping. Thinking re-enabled for strategic tier (effort=medium) and evolution engine (effort=high). Fast tier remains think=off. Token efficiency: no more wasted retries, thinking tokens are actual reasoning.

## 2026-03-28
- **Character name fragmentation** (HIGH): "The Silent" vs "the silent" vs "铁甲战士" across all memory stores. `normalize_character()` was added to extractors after data was already written, and `loop.py` stored raw `gs.character` in RunState. Fix: normalize at RunState assignment (loop.py:1230), normalize in guide_consolidator grouping, data migration script (`scripts/normalize_character_names.py`) fixed 885 records across 3 JSONL stores + guides.json.

## 2026-03-27
- **System prompt bloat** (PERF): Trimmed 6461→3869 chars. Status effects and combat rules moved to dynamic context in conversation.py.
- **Conditional pile injection** (PERF): Draw/discard/exhaust piles only shown when hand cards have draw/discard/exhaust effects.
- **Poison kill detection** (HIGH): Skill eval kill detection only checked card damage, missed poison tick kills at end of turn.
- **Eval post-reload crash** (CRITICAL): After save_and_quit + continue_run, _v2_combat_conversation was None. Re-initialization added.
- **Sweep deletion blocked** (HIGH): usage_count < 5 guard prevented deletion of deactivated skills. Deletion check moved before guard.
- **68% skills zero usage** (HIGH): Added exploration bonus (+5.0) for zero-usage skills to ensure they get tested.
- **save_and_quit during enemy turn** (MEDIUM): Agent crashed when only available action was save_and_quit during non-play phase. Added is_play_phase guard.
- **Hardcoded force-rest bypass** (HIGH): HP<25% code bypass removed. LLM now decides all rest/map choices.

## 2026-03-26
- **Combat type misclassification** (CRITICAL): `_infer_combat_type()` hardcoded `floor in (8, 16, 24)` as boss floors. STS2 actual boss floors: 17 (Act 1), 33 (Act 2), 43+ (Act 3). MCP API doesn't return map data during combat, so floor heuristic always fired. Floor 8 monsters classified as "boss" (9 episodes), floor 17 real bosses classified as "elite" (43 episodes). Fix: removed floor heuristic, added `_cached_map_node_type` in agent loop — caches map node metadata at selection time (before combat starts). Memory data repaired via `scripts/fix_combat_type.py`.

## 2026-03-24
- **Re-plan thinking disabled** (HIGH): Draw-card splitting (e.g. Backflip++) invalidates the current plan and triggers a re-plan. Re-plans were routed to fast tier (`budget=0, max_tokens=4096`) with no thinking. Models wrote extensive reasoning in the response text ("fake thinking"), consuming all 4096 tokens and truncating the tool call. Fix: re-plans now use strategic model with `budget=2000, effort="low"` (`max_tokens=8192` with proper thinking block).
- **Tier logging always "strategic"** (MEDIUM): When `LLM_FAST_MODEL == LLM_STRATEGIC_MODEL` (both sonnet-4-6), the tier name comparison always resolved to "strategic" even for fast-tier calls. Fix: `tier_name = "fast" if not use_think else "strategic"`.
- **Relic descriptions not in prompts** (MEDIUM): MCP API returns `RawRunRelicPayload.description` with full relic effect text, but `_cached_relics` only stored names. Fix: `_cached_relics` now stores `"Name (description)"` format with BBCode stripped.

## 2026-03-23
- **Dynamic registry stale wiring** (HIGH): `loop.py` still tried to route dynamic tools through removed `query_tools.set_dynamic_registry()` / `ToolExecutor.set_dynamic_registry()` hooks. Fix: `AgentLoop._init_v2()` now loads `DynamicToolRegistry` directly.
- **Combat prompt import residue** (HIGH): one combat init path still referenced `SYSTEM_PROMPT_V2` after the rename to `SYSTEM_PROMPT`.

## 2026-03-21
- **Multi-card selection infinite loop** (CRITICAL): "Choose 2 cards to Remove" caused 161+ LLM calls looping. Root cause: C# mod's `BuildSelectionPayload` only extracts metadata from `NPlayerHand` (combat hand). Fix: parse required count from prompt text, track selected indices per session, auto-confirm after target count reached.
- **V1 combat fallback code residue** (CRITICAL): `_generate_combat_plan()` had V1 `plan_combat()` code after the "V1 path removed" comment.
- **V2 empty response breaks loop** (HIGH): Proxy/API returning `stop_reason=end_turn` with empty content caused `_agent_loop` to `break` immediately.
- **Single-card select confirm timeout** (HIGH): Combat card selections (Survivor discard, Nightmare choose) attempted `confirm_selection`.
- **energy_used always 0** (MEDIUM): `card.energy` attribute doesn't exist (`energy_cost` is the correct field).

## 2026-03-20
- **Card reward case sensitivity** (CRITICAL): `reward_type == "card"` didn't match API's `"Card"` → `.lower()` added.
- **c.can_play AttributeError**: `RawCombatHandCardPayload` has `.playable` not `.can_play`.
- **Rest threat assessment blind**: Rest prompt had no info about next map node.
- **V2Backend no timeout**: Added 120s HTTP timeout to prevent 10-minute proxy hangs.
- **Prompt cache miss 100%**: `run_summary` was concatenated into system prompt.
- **search_strategy frozenset errors**: `frozenset & list` type mismatch.
- **Structured card previews**: Added card-level `damage`, `block`, `hits`, `total_damage` fields from DynamicVars.

## 2026-03-19
- **rules_text unresolved templates**: `GetCardRulesText()` used reflection → switched to `GetDescriptionForPile(PileType.Hand)`.
- **No target-specific damage info**: Added `target_previews` with `UpdateDynamicVarPreview` + `CalculatedDamageVar.Calculate(target)`.

## 2026-03-18
- **deck_events always empty**: `_hcm_record_deck_change()` defined but never called.
- **damage_taken always 0**: combat rounds never computed damage.
- **Shop model blind**: C# sends `category`/`can_afford`/`card_name`, Python expected `type`/`is_affordable`/`name`.
- **Event body invisible**: C# sends `"body"`, Python expected `"body_text"`.
- **Event index mismatch**: state indexes all options (incl. locked), C# action uses compressed (unlocked-only) index.

## 2026-03-15 to 2026-03-17
- **Empty combat plan ends turn with energy**: LLM returns 0-action plan but playable cards exist.
- **Combat fallback deadlock**: `_end_turn_sent_round` guard blocked ALL paths.
- **Stuck recovery infinite loop**: `_force_unstick()` blindly tried `proceed`.
- **LLM failure terminated run**: `self._running = False`.
- **Skill feedback loop disconnected**: `record_outcome()` was never called.
- **Rest 97.8% rate**: "HP<80%→rest" in prompt + system.py + 2 seeds → all rewritten to "Smith default".
