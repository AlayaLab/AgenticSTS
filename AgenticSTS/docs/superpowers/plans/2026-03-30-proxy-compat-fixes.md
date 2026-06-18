# Proxy Compatibility Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 proxy compatibility issues that waste Opus API calls and generate log noise on every run.

**Architecture:** Three independent surgical fixes in the normalization layer (`dynamic_tools.py`), evolution retry logic (`evolution_engine.py`), and batch API caching (`batch.py`). No architectural changes — just bug fixes and hardening.

**Tech Stack:** Python, JSON Schema, Anthropic SDK

**Spec:** `docs/superpowers/specs/2026-03-30-proxy-compat-fixes-design.md`

---

### Task 1: Fix Dynamic Tool Schema Normalization — Tests

**Files:**
- Modify: `tests/test_dynamic_tools.py:327-398` (add tests to `TestGetNormalizedSchema`)

- [ ] **Step 1: Add test fixtures for new schema edge cases**

Add these tool code constants after the existing `LEGACY_INPUT_TOOL_CODE` (around line 115):

```python
COMPOUND_TYPE_TOOL_CODE = '''
SCHEMA = {
    "name": "test_compound_type",
    "description": "Tool with compound Python types.",
    "parameters": {
        "enemies": {"type": "list[dict]", "description": "list of enemy dicts"},
        "names": {"type": "list[str]", "description": "list of name strings"},
    },
}

def execute(enemies=None, names=None, **kwargs) -> str:
    return "ok"
'''

DEFAULT_KEY_TOOL_CODE = '''
SCHEMA = {
    "name": "test_default_key",
    "description": "Tool with default keys in params.",
    "parameters": {
        "hp": {"type": "int", "description": "HP", "default": 70},
        "block": {"type": "int", "description": "Block", "default": 0},
    },
}

def execute(hp=70, block=0, **kwargs) -> str:
    return "ok"
'''

EMPTY_DESC_TOOL_CODE = '''
SCHEMA = {
    "name": "test_empty_desc",
    "description": "",
    "parameters": {
        "x": {"type": "int", "description": "input"},
    },
}

def execute(x=0, **kwargs) -> str:
    return "ok"
'''

UNKNOWN_TYPE_TOOL_CODE = '''
SCHEMA = {
    "name": "test_unknown_type",
    "description": "Tool with a non-standard type.",
    "parameters": {
        "data": {"type": "custom_thing", "description": "something"},
    },
}

def execute(data=None, **kwargs) -> str:
    return "ok"
'''
```

- [ ] **Step 2: Add test methods to `TestGetNormalizedSchema`**

Add after `test_get_normalized_schemas_list` (after line 397):

```python
    def test_compound_type_list_dict(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(COMPOUND_TYPE_TOOL_CODE, encoding="utf-8")
            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()
            schema = registry.get_normalized_schema("test_compound_type")
            assert schema is not None
            props = schema["input_schema"]["properties"]
            assert props["enemies"]["type"] == "array"
            assert props["enemies"]["items"] == {"type": "object"}
            assert props["names"]["type"] == "array"
            assert props["names"]["items"] == {"type": "string"}

    def test_default_key_removed(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(DEFAULT_KEY_TOOL_CODE, encoding="utf-8")
            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()
            schema = registry.get_normalized_schema("test_default_key")
            assert schema is not None
            props = schema["input_schema"]["properties"]
            assert "default" not in props["hp"]
            assert "default" not in props["block"]

    def test_empty_description_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(EMPTY_DESC_TOOL_CODE, encoding="utf-8")
            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()
            schema = registry.get_normalized_schema("test_empty_desc")
            assert schema is not None
            assert schema["description"] != ""
            assert schema["description"] == "(no description)"

    def test_unknown_type_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(UNKNOWN_TYPE_TOOL_CODE, encoding="utf-8")
            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()
            schema = registry.get_normalized_schema("test_unknown_type")
            assert schema is not None
            props = schema["input_schema"]["properties"]
            assert props["data"]["type"] == "string"  # fallback from "custom_thing"
```

- [ ] **Step 3: Run tests — verify they FAIL**

Run: `python -m pytest tests/test_dynamic_tools.py::TestGetNormalizedSchema -v --timeout=10`
Expected: 4 new tests FAIL (compound type gets `"list[dict]"`, default key present, empty desc, unknown type passes through)

- [ ] **Step 4: Commit failing tests**

```bash
git add tests/test_dynamic_tools.py
git commit -m "test: add schema normalization edge case tests (compound types, default key, empty desc, unknown type)"
```

---

### Task 2: Fix Dynamic Tool Schema Normalization — Implementation

**Files:**
- Modify: `src/brain/dynamic_tools.py:316-468`

- [ ] **Step 1: Add `re` import and `_VALID_JSON_SCHEMA_TYPES` constant**

At the top of the file (around line 15, with existing imports), add `import re`.

After `_TYPE_MAP` (after line 329), add:

```python
_VALID_JSON_SCHEMA_TYPES = frozenset({
    "string", "integer", "number", "boolean", "array", "object", "null",
})
```

- [ ] **Step 2: Fix `_normalize_param` string branch — compound types (line 370-383)**

Replace lines 370-383:

```python
        if len(parts) == 2:
            type_hint = parts[0].strip().lower()
            desc = parts[1].strip()
        else:
            type_hint = raw.strip().lower()
            desc = ""

        json_type = _TYPE_MAP.get(type_hint, "string")
        result: dict = {"type": json_type}
        if desc:
            result["description"] = desc
        # JSON Schema 2020-12 requires "items" for array types
        if json_type == "array":
            result["items"] = {"type": "object"}
        return result
```

With:

```python
        if len(parts) == 2:
            type_hint = parts[0].strip().lower()
            desc = parts[1].strip()
        else:
            type_hint = raw.strip().lower()
            desc = ""

        # Handle compound Python types: "list[dict]", "list[str]", etc.
        inner_type: str | None = None
        compound = re.match(r"^(list|array)\[(\w+)]$", type_hint)
        if compound:
            json_type = "array"
            inner_type = _TYPE_MAP.get(compound.group(2), "object")
        else:
            json_type = _TYPE_MAP.get(type_hint, "string")

        result: dict = {"type": json_type}
        if desc:
            result["description"] = desc
        # JSON Schema 2020-12 requires "items" for array types
        if json_type == "array":
            result["items"] = {"type": inner_type or "object"}
        return result
```

- [ ] **Step 3: Fix `_normalize_param` dict branch — compound types (line 389-391)**

Replace lines 389-391:

```python
        if "type" in result:
            raw_type = str(result["type"]).lower()
            result["type"] = _TYPE_MAP.get(raw_type, raw_type)
```

With:

```python
        if "type" in result:
            raw_type = str(result["type"]).lower()
            compound = re.match(r"^(list|array)\[(\w+)]$", raw_type)
            if compound:
                result["type"] = "array"
                inner = _TYPE_MAP.get(compound.group(2), "object")
                result["items"] = {"type": inner}
            else:
                result["type"] = _TYPE_MAP.get(raw_type, raw_type)
```

- [ ] **Step 4: Fix `_normalize_param` — add `default` deletion branch (line 413-414)**

After line 414 (`del result["required"]`), add:

```python
                elif bad_key == "default":
                    del result["default"]
```

- [ ] **Step 5: Add final type guard before return (line 416)**

Before the `return result` on line 416, add:

```python
        # Final guard: reject any type not in JSON Schema spec
        if result.get("type") not in _VALID_JSON_SCHEMA_TYPES:
            result["type"] = "string"

```

- [ ] **Step 6: Fix `_normalize_schema` — empty description fallback (line 433)**

Change line 433:

```python
    description = schema.get("description", "")
```

To:

```python
    description = schema.get("description", "") or "(no description)"
```

- [ ] **Step 7: Run tests — verify they PASS**

Run: `python -m pytest tests/test_dynamic_tools.py::TestGetNormalizedSchema -v --timeout=10`
Expected: All tests PASS including the 4 new ones.

- [ ] **Step 8: Run full schema validation on real tools**

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

Expected: `All 42 tool schemas valid`

- [ ] **Step 9: Commit**

```bash
git add src/brain/dynamic_tools.py
git commit -m "fix: normalize dynamic tool schemas for Bedrock JSON Schema 2020-12 compliance

- Handle compound Python types (list[dict] → array + items)
- Actually delete 'default' keys (missing elif branch)
- Fallback unknown types to 'string'
- Default empty descriptions to '(no description)'"
```

---

### Task 3: Evolution Retry — Tests

**Files:**
- Modify: `tests/test_proxy_compat.py` (add `_is_transient` tests)

- [ ] **Step 1: Add `_is_transient` tests**

Append to `tests/test_proxy_compat.py`:

```python
from src.brain.evolution_engine import _is_transient


class TestIsTransient:
    def test_502_is_transient(self):
        assert _is_transient("Error code: 502 - upstream failed") is True

    def test_503_is_transient(self):
        assert _is_transient("Error code: 503 - service unavailable") is True

    def test_timeout_is_transient(self):
        assert _is_transient("Request timed out or interrupted") is True

    def test_upstream_is_transient(self):
        assert _is_transient("Upstream request failed after retries") is True

    def test_connection_is_transient(self):
        assert _is_transient("Connection reset by peer") is True

    def test_400_not_transient(self):
        assert _is_transient("Error code: 400 - ValidationException") is False

    def test_schema_not_transient(self):
        assert _is_transient("JSON schema is invalid") is False
```

- [ ] **Step 2: Run tests — verify they FAIL**

Run: `python -m pytest tests/test_proxy_compat.py::TestIsTransient -v --timeout=10`
Expected: FAIL with `ImportError: cannot import name '_is_transient'`

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_proxy_compat.py
git commit -m "test: add _is_transient helper tests for evolution retry"
```

---

### Task 4: Evolution Retry — Implementation

**Files:**
- Modify: `src/brain/evolution_engine.py:343-356`

- [ ] **Step 1: Add `_is_transient` helper (module-level)**

Add before the `EvolutionEngine` class (around line 30, after the imports):

```python
def _is_transient(exc_str: str) -> bool:
    """Check if an error message indicates a transient/retriable failure."""
    return any(kw in exc_str.lower() for kw in (
        "502", "503", "timed out", "timeout", "upstream", "connection",
    ))
```

- [ ] **Step 2: Replace the catch-all exception handler (lines 343-356)**

Replace:

```python
        for round_idx in range(max_rounds):
            try:
                response = self._backend.call(
                    system=EVOLUTION_SYSTEM_PROMPT,
                    messages=messages,
                    model=model,
                    tools=all_tools,
                    think=True,
                    effort="high",
                    max_tokens=4096,
                )
            except Exception as exc:
                logger.warning("Evolution LLM call failed at round %d: %s", round_idx, exc)
                break
```

With:

```python
        for round_idx in range(max_rounds):
            try:
                response = self._backend.call(
                    system=EVOLUTION_SYSTEM_PROMPT,
                    messages=messages,
                    model=model,
                    tools=all_tools,
                    think=True,
                    effort="high",
                    max_tokens=4096,
                )
            except Exception as exc:
                exc_str = str(exc)
                # 400 = schema/validation error — won't self-heal
                if "400" in exc_str or "ValidationException" in exc_str:
                    logger.warning(
                        "Evolution schema rejected at round %d: %s",
                        round_idx, exc,
                    )
                    break
                # Transient errors (502, 503, timeout) — inline retry once
                if _is_transient(exc_str):
                    logger.warning(
                        "Evolution transient error at round %d, retrying in 3s: %s",
                        round_idx, exc,
                    )
                    time.sleep(3)
                    try:
                        response = self._backend.call(
                            system=EVOLUTION_SYSTEM_PROMPT,
                            messages=messages,
                            model=model,
                            tools=all_tools,
                            think=True,
                            effort="high",
                            max_tokens=4096,
                        )
                    except Exception as retry_exc:
                        logger.warning(
                            "Evolution retry also failed at round %d: %s",
                            round_idx, retry_exc,
                        )
                        break
                else:
                    logger.warning(
                        "Evolution LLM call failed at round %d: %s",
                        round_idx, exc,
                    )
                    break
```

- [ ] **Step 3: Run tests — verify they PASS**

Run: `python -m pytest tests/test_proxy_compat.py::TestIsTransient -v --timeout=10`
Expected: All 7 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add src/brain/evolution_engine.py
git commit -m "fix: add transient error retry to evolution engine (502/timeout → 1 retry, 400 → no retry)"
```

---

### Task 5: Batch API Session Cache — Tests

**Files:**
- Modify: `tests/test_proxy_compat.py` (add batch cache test)

- [ ] **Step 1: Add batch cache test**

Append to `tests/test_proxy_compat.py`:

```python
from unittest.mock import patch, MagicMock
import src.brain.batch as batch_module


class TestBatchCache:
    def setup_method(self):
        # Reset module-level cache between tests
        batch_module._batch_available = None

    def test_batch_cache_after_404(self):
        """After a 404 error, subsequent calls return None without HTTP call."""
        with patch.dict("os.environ", {}, clear=False):
            # First call: simulate 404
            with patch("anthropic.Anthropic") as mock_cls:
                mock_client = MagicMock()
                mock_client.messages.batches.create.side_effect = Exception(
                    "Error code: 404 - Invalid URL (POST /v1/messages/batches)"
                )
                mock_cls.return_value = mock_client

                result = batch_module.submit_batch(
                    [{"custom_id": "test", "params": {}}],
                    [{"type": "test"}],
                )
                assert result is None
                assert batch_module._batch_available is False

            # Second call: should return None immediately (no HTTP call)
            with patch("anthropic.Anthropic") as mock_cls2:
                result2 = batch_module.submit_batch(
                    [{"custom_id": "test2", "params": {}}],
                    [{"type": "test2"}],
                )
                assert result2 is None
                mock_cls2.assert_not_called()  # No client created

    def test_batch_non_404_does_not_cache(self):
        """Non-404 errors should NOT disable batch for the session."""
        with patch("anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_client.messages.batches.create.side_effect = Exception(
                "Error code: 500 - internal server error"
            )
            mock_cls.return_value = mock_client

            result = batch_module.submit_batch(
                [{"custom_id": "test", "params": {}}],
                [{"type": "test"}],
            )
            assert result is None
            assert batch_module._batch_available is None  # NOT cached as unavailable
```

- [ ] **Step 2: Run tests — verify they FAIL**

Run: `python -m pytest tests/test_proxy_compat.py::TestBatchCache -v --timeout=10`
Expected: FAIL (no `_batch_available` attribute on batch module yet)

- [ ] **Step 3: Commit failing tests**

```bash
git add tests/test_proxy_compat.py
git commit -m "test: add batch API session cache tests (404 caching, non-404 passthrough)"
```

---

### Task 6: Batch API Session Cache — Implementation

> **Note**: After implementing, re-run `python -m pytest tests/test_proxy_compat.py::TestBatchCache -v` to verify the Task 5 tests now PASS.

**Files:**
- Modify: `src/brain/batch.py:50-78`

- [ ] **Step 1: Add module-level availability flag**

After line 22 (`_PENDING_FILE = ...`), add:

```python
_batch_available: bool | None = None  # None=untested, True=works, False=unavailable
```

- [ ] **Step 2: Update `submit_batch` with cache logic**

Replace lines 50-78:

```python
def submit_batch(
    requests: list[dict],
    tasks_meta: list[dict],
) -> str | None:
    """Submit a batch of LLM requests to Anthropic Batch API.

    Args:
        requests: List of batch request dicts (custom_id + params).
        tasks_meta: Metadata for each request (type, run_id, etc.) for
                    result processing. Must parallel requests list.

    Returns:
        Batch ID on success, None on failure.
    """
    if not requests:
        return None

    try:
        import anthropic
        kwargs: dict = {}
        if config.LLM_API_KEY:
            kwargs["api_key"] = config.LLM_API_KEY
        if config.ANTHROPIC_BASE_URL:
            kwargs["base_url"] = config.ANTHROPIC_BASE_URL
        client = anthropic.Anthropic(**kwargs)
        batch = client.messages.batches.create(requests=requests)
    except Exception as e:
        logger.warning("Batch submission failed: %s", e)
        return None
```

With:

```python
def submit_batch(
    requests: list[dict],
    tasks_meta: list[dict],
) -> str | None:
    """Submit a batch of LLM requests to Anthropic Batch API.

    Args:
        requests: List of batch request dicts (custom_id + params).
        tasks_meta: Metadata for each request (type, run_id, etc.) for
                    result processing. Must parallel requests list.

    Returns:
        Batch ID on success, None on failure.
    """
    global _batch_available
    if not requests:
        return None
    if _batch_available is False:
        return None  # Already known unavailable this session

    try:
        import anthropic
        kwargs: dict = {}
        if config.LLM_API_KEY:
            kwargs["api_key"] = config.LLM_API_KEY
        if config.ANTHROPIC_BASE_URL:
            kwargs["base_url"] = config.ANTHROPIC_BASE_URL
        client = anthropic.Anthropic(**kwargs)
        batch = client.messages.batches.create(requests=requests)
        _batch_available = True
    except Exception as e:
        err = str(e)
        if "404" in err or "Invalid URL" in err:
            _batch_available = False
            logger.info("Batch API not supported by proxy, disabled for session")
        else:
            logger.warning("Batch submission failed: %s", e)
        return None
```

- [ ] **Step 3: Import check**

Run: `python -c "import src.brain.batch; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/brain/batch.py
git commit -m "fix: cache batch API unavailability per session (avoid 404 retry every run)"
```

---

### Task 7: Final Verification

- [ ] **Step 1: Run all related tests**

```bash
python -m pytest tests/test_dynamic_tools.py tests/test_proxy_compat.py -v --timeout=30
```

Expected: All tests PASS.

- [ ] **Step 2: Import check all 3 modules**

```bash
python -c "import src.brain.dynamic_tools; import src.brain.evolution_engine; import src.brain.batch; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full schema validation on 42 real tools**

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

Expected: `All 42 tool schemas valid`

- [ ] **Step 4: Commit spec + plan**

```bash
git add docs/superpowers/specs/2026-03-30-proxy-compat-fixes-design.md docs/superpowers/plans/2026-03-30-proxy-compat-fixes.md
git commit -m "docs: add proxy compatibility fixes spec and implementation plan"
```
