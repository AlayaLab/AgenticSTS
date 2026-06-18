# Proxy Compatibility Fixes — Design Spec

**Date**: 2026-03-30
**Status**: Reviewed
**Scope**: 3 targeted fixes for proxy.example.com (Bedrock) proxy compatibility

## Problem Statement

Over the last 12 hours (~143 runs), three proxy-related issues caused significant waste:

1. **Evolution fails every run (400 Bedrock ValidationException)**: Agent-authored dynamic tools have JSON schemas that violate JSON Schema draft 2020-12. The proxy.example.com proxy routes to AWS Bedrock which enforces strict validation. Each failed evolution call wastes one Opus API call (~$0.10-0.30).

2. **Batch API 404 every run**: The proxy doesn't support `/v1/messages/batches`. The existing sync fallback works, but the 404 is retried every run, generating log noise and a wasted HTTP round-trip.

3. **Evolution zero retry**: Any exception (502, timeout, 400) breaks the evolution loop immediately. Transient errors (502, timeout) could succeed on retry.

## Root Cause Analysis

### Fix 1: Dynamic Tool Schema Validation

**File**: `src/brain/dynamic_tools.py`

`_normalize_param()` (lines 357-418) has 3 bugs:

| Bug | Location | Example | Bedrock Behavior |
|-----|----------|---------|-----------------|
| Compound Python types pass through `_TYPE_MAP` | Line 391 | `"type": "list[dict]"` | Rejects: not valid JSON Schema type |
| `default` key never deleted | Lines 402-414 | `{"type":"integer","default":0}` | Rejects: non-standard property key |
| Empty tool descriptions | `_normalize_schema` L433 | `"description": ""` | May reject empty string |

**Evidence**: 26 schema issues across 42 tools (1 invalid type, 13 `default` keys, 7 empty descriptions, plus 5 tools with both issues).

**Specific compound type bug**: `_TYPE_MAP` maps `"list"→"array"` but the dict branch (line 389-391) does:
```python
raw_type = str(result["type"]).lower()
result["type"] = _TYPE_MAP.get(raw_type, raw_type)  # "list[dict]" not in map → passes through
```

**Specific `default` bug**: The sanitization loop iterates `("required", "desc", "default")` but only has branches for `"desc"` and `"required"`. There is no `elif bad_key == "default"` — the key is checked but never removed.

### Fix 2: Evolution Retry

**File**: `src/brain/evolution_engine.py`

Lines 343-356: catch-all `except Exception` immediately `break`s the evolution loop. No distinction between transient (502, timeout) and permanent (400 schema) errors. No retry.

### Fix 3: Batch API Caching

**File**: `src/brain/batch.py`

`submit_batch()` (lines 50-78): catch-all `except Exception` logs warning and returns None. No memory of failure — next run tries again, gets 404 again.

## Design

### Fix 1: Schema Normalization (`src/brain/dynamic_tools.py`)

**A. Compound type handling in `_normalize_param` (dict branch, ~line 389)**

Before the `_TYPE_MAP` lookup, detect compound Python type syntax via regex:

```python
import re  # at module top

# In _normalize_param, dict branch, before TYPE_MAP lookup:
raw_type = str(result["type"]).lower()
compound = re.match(r"^(list|array)\[(\w+)]$", raw_type)
if compound:
    result["type"] = "array"
    inner = _TYPE_MAP.get(compound.group(2), "object")
    result["items"] = {"type": inner}
else:
    result["type"] = _TYPE_MAP.get(raw_type, raw_type)
```

Same pattern for the string branch (~line 370), also using inner type for items:
```python
type_hint = parts[0].strip().lower()
compound = re.match(r"^(list|array)\[(\w+)]$", type_hint)
if compound:
    json_type = "array"
    inner_type = _TYPE_MAP.get(compound.group(2), "object")
    # Override the default items in the array→items block below
else:
    json_type = _TYPE_MAP.get(type_hint, "string")
# When setting items for array types, use inner_type if available from compound match
```

**B. Delete `default` key (line 413, add new branch)**

```python
elif bad_key == "required":
    del result["required"]
elif bad_key == "default":      # NEW
    del result["default"]       # NEW
```

**C. Final type guard (after all type resolution, before return)**

Add a module-level constant and a final check:

```python
_VALID_JSON_SCHEMA_TYPES = frozenset({"string", "integer", "number", "boolean", "array", "object", "null"})

# At end of _normalize_param, before return:
if result.get("type") not in _VALID_JSON_SCHEMA_TYPES:
    result["type"] = "string"
```

**D. Empty description fallback in `_normalize_schema` (~line 433)**

```python
description = schema.get("description", "") or "(no description)"
```

### Fix 2: Evolution Transient Retry (`src/brain/evolution_engine.py`)

Replace the catch-all at lines 354-356 with error-type-aware handling. Use **inline retry** (nested try/except) to actually re-run the same round:

```python
for round_idx in range(max_rounds):
    try:
        response = self._backend.call(...)
    except Exception as exc:
        exc_str = str(exc)
        # 400 = schema/validation error — won't self-heal
        if "400" in exc_str or "ValidationException" in exc_str:
            logger.warning("Evolution schema rejected at round %d: %s", round_idx, exc)
            break
        # Transient errors (502, 503, timeout) — inline retry once
        if _is_transient(exc_str):
            logger.warning("Evolution transient error at round %d, retrying in 3s: %s", round_idx, exc)
            time.sleep(3)
            try:
                response = self._backend.call(...)  # same params, same round
            except Exception as retry_exc:
                logger.warning("Evolution retry also failed at round %d: %s", round_idx, retry_exc)
                break
        else:
            logger.warning("Evolution LLM call failed at round %d: %s", round_idx, exc)
            break
```

Helper function (module-level):
```python
def _is_transient(exc_str: str) -> bool:
    """Check if an error message indicates a transient/retriable failure."""
    return any(kw in exc_str.lower() for kw in (
        "502", "503", "timed out", "timeout", "upstream", "connection",
    ))
```

Note: `time` is already imported at module level in `evolution_engine.py`.

### Fix 3: Batch API Session Cache (`src/brain/batch.py`)

Add module-level availability flag:

```python
_batch_available: bool | None = None  # None=untested, True=works, False=unavailable

def submit_batch(requests, tasks_meta) -> str | None:
    global _batch_available
    if _batch_available is False:
        return None  # Already known unavailable this session

    # ... existing try block ...
    try:
        ...
        _batch_available = True
        return batch.id
    except Exception as e:
        err = str(e)
        if "404" in err or "Invalid URL" in err:
            _batch_available = False
            logger.info("Batch API not supported by proxy, disabled for session")
        else:
            logger.warning("Batch submission failed: %s", e)
        return None
```

## Files Modified

| File | Lines | Change |
|------|-------|--------|
| `src/brain/dynamic_tools.py` | ~357-468 | Compound type parsing, `default` deletion, type guard, empty desc |
| `src/brain/evolution_engine.py` | ~343-356 | Transient error retry, 400 early-exit |
| `src/brain/batch.py` | ~50-78 | Session-level availability cache |

## Verification

### Unit Tests (add to existing test files)

**`tests/test_dynamic_tools.py`** — add to `TestGetNormalizedSchema`:
- `test_compound_type_list_dict`: tool with `"type": "list[dict]"` → `"type": "array", "items": {"type": "object"}`
- `test_compound_type_list_str`: tool with `"type": "list[str]"` → `"type": "array", "items": {"type": "string"}`
- `test_default_key_removed`: param with `"default": 0` → key absent in output
- `test_empty_description_fallback`: tool with `"description": ""` → `"(no description)"`
- `test_unknown_type_fallback`: param with `"type": "custom_thing"` → `"type": "string"`

**`tests/test_proxy_compat.py`** (or inline):
- `test_is_transient_502`: `_is_transient("502 Bad Gateway")` → True
- `test_is_transient_400`: `_is_transient("400 ValidationException")` → False
- `test_batch_cache_after_404`: after simulated 404, `submit_batch` returns None immediately

### Integration Checks

1. **Schema validation** (automated):
   ```bash
   python -c "
   import sys; sys.path.insert(0, '.')
   from src.brain.dynamic_tools import DynamicToolRegistry
   reg = DynamicToolRegistry(); reg.load_all()
   schemas = reg.get_normalized_schemas()
   bad = []
   for s in schemas:
       if not s.get('description') or s['description'] == '':
           bad.append(('empty_desc', s['name']))
       for pname, pdef in s['input_schema'].get('properties', {}).items():
           t = pdef.get('type', '')
           if t not in ('string','integer','number','boolean','array','object','null'):
               bad.append(('bad_type', s['name'], pname, t))
           if 'default' in pdef:
               bad.append(('has_default', s['name'], pname))
   assert len(bad) == 0, f'{len(bad)} issues: {bad}'
   print(f'All {len(schemas)} tool schemas valid')
   "
   ```

2. **Import check**:
   ```bash
   python -c "import src.brain.dynamic_tools; import src.brain.evolution_engine; import src.brain.batch; print('OK')"
   ```

3. **Existing tests**:
   ```bash
   python -m pytest tests/ -k "dynamic or evolution or batch or proxy" --timeout=30 -q
   ```

4. **Live validation**: Start agent, run 1 complete game. Check logs:
   - No `ValidationException` in evolution output
   - `Batch API not supported by proxy` appears once (not every run)
   - Evolution either completes or fails with non-schema error

## Non-Goals

- Not fixing the 42 tool `.py` files directly (normalization layer handles it)
- Not adding evolution auto-disable (user preference: fix schema is sufficient)
- Not addressing 502/503 gameplay errors (already handled by V2Engine retry)
- Not addressing 224s slow calls (streaming handles it correctly)
- Not addressing the Floor 5 event lock bug (can't reproduce currently)
