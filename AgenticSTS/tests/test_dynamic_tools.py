"""Tests for Step 2: DynamicToolRegistry + AST sandbox + integration points.

Covers:
- AST validation: allows safe code, blocks forbidden patterns
- Sandbox execution: restricted namespace, test case validation
- Tool loading from disk: SCHEMA + execute() + TEST_CASES
- Tool registration: validates, writes, loads
- Integration: is_query_tool(), tool_executor fallback, schema merging
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from src.brain.dynamic_tools import (
    DynamicToolRegistry,
    validate_ast,
)

# ── AST Validation ──────────────────────────────────────────────


class TestASTValidation:
    """Verify AST validator catches forbidden patterns."""

    def test_safe_code_passes(self):
        code = """
import math

SCHEMA = {
    "name": "test",
    "description": "test",
    "input_schema": {"type": "object", "properties": {}},
}

def execute(**kwargs):
    return str(math.sqrt(16))
"""
        violations = validate_ast(code)
        assert violations == []

    def test_forbidden_import_os(self):
        violations = validate_ast("import os")
        assert len(violations) == 1
        assert "os" in violations[0]

    def test_forbidden_import_subprocess(self):
        violations = validate_ast("import subprocess")
        assert len(violations) == 1
        assert "subprocess" in violations[0]

    def test_forbidden_import_from(self):
        violations = validate_ast("from pathlib import Path")
        assert len(violations) == 1
        assert "pathlib" in violations[0]

    def test_allowed_import_math(self):
        violations = validate_ast("import math")
        assert violations == []

    def test_allowed_import_collections(self):
        violations = validate_ast("from collections import defaultdict")
        assert violations == []

    def test_forbidden_open(self):
        violations = validate_ast("open('foo.txt')")
        assert any("open" in v for v in violations)

    def test_forbidden_eval(self):
        violations = validate_ast("eval('1+1')")
        assert any("eval" in v for v in violations)

    def test_forbidden_dunder(self):
        violations = validate_ast("x.__class__")
        assert any("__" in v for v in violations)

    def test_syntax_error(self):
        violations = validate_ast("def (broken")
        assert len(violations) == 1
        assert "Syntax error" in violations[0]


# ── Tool Loading & Execution ────────────────────────────────────

VALID_TOOL_CODE = '''
SCHEMA = {
    "name": "test_adder",
    "description": "Add two numbers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "a": {"type": "integer"},
            "b": {"type": "integer"}
        },
        "required": ["a", "b"],
        "additionalProperties": False
    }
}
APPLICABLE_STATES = ["monster", "elite", "boss"]

def execute(a: int, b: int, **kwargs) -> str:
    return f"Result: {a + b}"

TEST_CASES = [
    {"input": {"a": 2, "b": 3}, "expected_contains": "5"},
    {"input": {"a": -1, "b": 1}, "expected_contains": "0"},
]
'''

TOOL_WITH_FORBIDDEN_IMPORT = '''
import os

SCHEMA = {
    "name": "bad_tool",
    "description": "Bad",
    "input_schema": {"type": "object", "properties": {}},
}

def execute(**kwargs):
    return os.getcwd()
'''

TOOL_WITH_FAILING_TEST = '''
SCHEMA = {
    "name": "fail_test",
    "description": "Will fail test.",
    "input_schema": {"type": "object", "properties": {}}
}

def execute(**kwargs) -> str:
    return "actual_value"

TEST_CASES = [
    {"input": {}, "expected_contains": "impossible_value"},
]
'''


class TestDynamicToolRegistry:
    """Test tool loading, validation, and execution."""

    def test_load_valid_tool(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "test_adder.py").write_text(VALID_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            loaded = registry.load_all()
            assert loaded == 1
            assert registry.has("test_adder")
            assert registry.count == 1

    def test_execute_valid_tool(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "test_adder.py").write_text(VALID_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()
            result = registry.execute("test_adder", {"a": 10, "b": 20})
            assert "30" in result

    def test_reject_forbidden_import(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "bad.py").write_text(TOOL_WITH_FORBIDDEN_IMPORT, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            loaded = registry.load_all()
            assert loaded == 0
            assert registry.count == 0

    def test_reject_failing_test(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "fail.py").write_text(TOOL_WITH_FAILING_TEST, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            loaded = registry.load_all()
            assert loaded == 0

    def test_get_schemas(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "test_adder.py").write_text(VALID_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()
            schemas = registry.get_schemas()
            assert len(schemas) == 1
            assert schemas[0]["name"] == "test_adder"

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as td:
            registry = DynamicToolRegistry(Path(td))
            loaded = registry.load_all()
            assert loaded == 0
            assert registry.count == 0

    def test_nonexistent_directory(self):
        registry = DynamicToolRegistry(Path("/nonexistent/path"))
        loaded = registry.load_all()
        assert loaded == 0

    def test_unknown_tool_execute(self):
        registry = DynamicToolRegistry(Path("/nonexistent"))
        result = registry.execute("nonexistent_tool", {})
        assert "Unknown" in result

    def test_register_tool(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            registry = DynamicToolRegistry(tools_dir)
            result = registry.register_tool("adder", VALID_TOOL_CODE, "test motivation")
            assert "SUCCESS" in result
            assert registry.has("test_adder")
            # File uses SCHEMA name (actual_name), not the tool_name param
            assert (tools_dir / "test_adder.py").exists()

    def test_register_rejected_tool(self):
        with tempfile.TemporaryDirectory() as td:
            registry = DynamicToolRegistry(Path(td))
            result = registry.register_tool("bad", TOOL_WITH_FORBIDDEN_IMPORT)
            assert "REJECTED" in result
            assert registry.count == 0

    def test_stats(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "test_adder.py").write_text(VALID_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            # Execute once
            registry.execute("test_adder", {"a": 1, "b": 2})

            stats = registry.stats()
            assert "test_adder" in stats
            assert stats["test_adder"]["usage_count"] == 1
            assert stats["test_adder"]["success_count"] == 1


# ── Schema normalization (P0-2) ─────────────────────────────────

DICT_VALUES_TOOL_CODE = '''
SCHEMA = {
    "name": "test_dict_values",
    "description": "A tool with dict-style params.",
    "parameters": {
        "enemy_hp": {"type": "int", "description": "Enemy HP"},
        "poison_stacks": {"type": "integer", "description": "Poison count"},
        "is_weak": {"type": "bool", "description": "Weakness applied"},
    },
    "required": ["enemy_hp", "poison_stacks"],
}

def execute(enemy_hp: int = 0, poison_stacks: int = 0, is_weak: bool = False, **kwargs) -> str:
    return f"{enemy_hp},{poison_stacks},{is_weak}"
'''

STRING_DESC_TOOL_CODE = '''
SCHEMA = {
    "name": "test_string_desc",
    "description": "A tool with string description params.",
    "parameters": {
        "current_hp": "int \\u2014 current player HP",
        "damage": "int \\u2014 incoming damage",
        "enemies": "list \\u2014 list of enemy dicts",
    },
}

def execute(current_hp: int = 0, damage: int = 0, enemies: list = None, **kwargs) -> str:
    return f"{current_hp},{damage},{len(enemies or [])}"
'''

LEGACY_INPUT_TOOL_CODE = '''
SCHEMA = {
    "name": "test_legacy_input",
    "description": "A tool with legacy input key.",
    "input": {
        "deck": "list of card dicts",
        "card_to_remove": "dict with name and type",
    },
}

def execute(deck: list = None, card_to_remove: dict = None, **kwargs) -> str:
    return f"deck={len(deck or [])}"
'''

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


class TestGetParamInfo:
    """Verify get_param_info() extracts raw parameters."""

    def test_dict_values_format(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(DICT_VALUES_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            info = registry.get_param_info("test_dict_values")
            assert info is not None
            assert "enemy_hp" in info
            assert "poison_stacks" in info
            assert "is_weak" in info

    def test_string_description_format(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(STRING_DESC_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            info = registry.get_param_info("test_string_desc")
            assert info is not None
            assert "current_hp" in info
            assert isinstance(info["current_hp"], str)  # raw string preserved

    def test_unknown_tool_returns_none(self):
        registry = DynamicToolRegistry(Path("/nonexistent"))
        assert registry.get_param_info("nonexistent") is None


class TestGetNormalizedSchema:
    """Verify get_normalized_schema() produces Anthropic-compatible format."""

    def test_dict_values_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(DICT_VALUES_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            schema = registry.get_normalized_schema("test_dict_values")
            assert schema is not None
            assert schema["name"] == "test_dict_values"
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"

            props = schema["input_schema"]["properties"]
            assert props["enemy_hp"]["type"] == "integer"  # "int" → "integer"
            assert props["poison_stacks"]["type"] == "integer"
            assert props["is_weak"]["type"] == "boolean"  # "bool" → "boolean"

            # Required preserved
            assert "enemy_hp" in schema["input_schema"].get("required", [])
            assert "poison_stacks" in schema["input_schema"].get("required", [])

    def test_string_desc_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(STRING_DESC_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            schema = registry.get_normalized_schema("test_string_desc")
            assert schema is not None
            props = schema["input_schema"]["properties"]
            assert props["current_hp"]["type"] == "integer"
            assert props["damage"]["type"] == "integer"
            assert props["enemies"]["type"] == "array"  # "list" → "array"

    def test_legacy_input_normalized(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(LEGACY_INPUT_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            schema = registry.get_normalized_schema("test_legacy_input")
            assert schema is not None
            props = schema["input_schema"]["properties"]
            assert "deck" in props
            assert "card_to_remove" in props

    def test_unknown_tool_returns_none(self):
        registry = DynamicToolRegistry(Path("/nonexistent"))
        assert registry.get_normalized_schema("nonexistent") is None

    def test_get_normalized_schemas_list(self):
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(VALID_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            schemas = registry.get_normalized_schemas()
            assert len(schemas) == 1
            assert schemas[0]["name"] == "test_adder"
            assert "input_schema" in schemas[0]

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
            assert props["data"]["type"] == "string"


# ── Runtime bindability classification (P0-3) ───────────────────

STATE_DERIVED_TOOL_CODE = '''
SCHEMA = {
    "name": "test_state_derived",
    "description": "All params are auto-bindable.",
    "parameters": {
        "current_hp": {"type": "int", "description": "Player HP"},
        "incoming_damage": {"type": "int", "description": "Damage from intents"},
        "current_block": {"type": "int", "description": "Block"},
    },
}

def execute(current_hp: int = 0, incoming_damage: int = 0, current_block: int = 0, **kwargs) -> str:
    return "ok"
'''

PLAN_EVALUATOR_TOOL_CODE = '''
SCHEMA = {
    "name": "test_plan_evaluator",
    "description": "Has plan-dependent param.",
    "parameters": {
        "current_hp": {"type": "int", "description": "Player HP"},
        "planned_block": {"type": "int", "description": "Block from planned cards"},
    },
}

def execute(current_hp: int = 0, planned_block: int = 0, **kwargs) -> str:
    return "ok"
'''

EXPLICIT_TYPE_TOOL_CODE = '''
TOOL_TYPE = "state_derived"

SCHEMA = {
    "name": "test_explicit_type",
    "description": "Has explicit TOOL_TYPE override.",
    "parameters": {
        "planned_block": {"type": "int", "description": "Would be plan_evaluator without override"},
    },
}

def execute(planned_block: int = 0, **kwargs) -> str:
    return "ok"
'''


class TestClassifyToolRuntimeMode:
    """Verify classify_tool_runtime_mode() classifies correctly."""

    def test_state_derived(self):
        from src.brain.dynamic_tools import classify_tool_runtime_mode

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(STATE_DERIVED_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            assert classify_tool_runtime_mode("test_state_derived", registry) == "state_derived"

    def test_plan_evaluator(self):
        from src.brain.dynamic_tools import classify_tool_runtime_mode

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(PLAN_EVALUATOR_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            assert classify_tool_runtime_mode("test_plan_evaluator", registry) == "plan_evaluator"

    def test_explicit_type_overrides(self):
        from src.brain.dynamic_tools import classify_tool_runtime_mode

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "t.py").write_text(EXPLICIT_TYPE_TOOL_CODE, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            # Would be plan_evaluator from params, but TOOL_TYPE overrides
            assert classify_tool_runtime_mode("test_explicit_type", registry) == "state_derived"

    def test_unknown_tool(self):
        from src.brain.dynamic_tools import classify_tool_runtime_mode

        registry = DynamicToolRegistry(Path("/nonexistent"))
        assert classify_tool_runtime_mode("nonexistent", registry) == "unknown"

    def test_classify_all_real_tools(self):
        """Verify all 27 real tools are classified without errors."""
        from src.brain.dynamic_tools import classify_all_tools
        from src.storage import paths

        real_dir = paths.evolution_tools_dir()
        if not real_dir.exists():
            return  # Skip if no real tools dir

        registry = DynamicToolRegistry(real_dir)
        registry.load_all()

        if registry.count == 0:
            return  # Skip if no tools loaded

        classification = classify_all_tools(registry)
        assert len(classification) == registry.count

        # Every tool must be classified as state_derived or plan_evaluator
        for name, mode in classification.items():
            assert mode in ("state_derived", "plan_evaluator"), (
                f"Tool {name} classified as unexpected mode: {mode}"
            )


# ── Integration: ToolExecutor only handles static tools ─────────


class TestToolExecutorStaticOnly:
    """Verify ToolExecutor only dispatches static query tools (no dynamic fallback)."""

    def test_dynamic_tool_returns_unknown(self):
        """ToolExecutor does NOT fall back to dynamic registry."""
        from src.brain.tool_executor import ToolExecutor

        executor = ToolExecutor()
        result = executor.execute("test_adder", {"a": 5, "b": 7})
        assert "Unknown tool" in result

    def test_unknown_tool(self):
        from src.brain.tool_executor import ToolExecutor

        executor = ToolExecutor()
        result = executor.execute("nonexistent_tool", {})
        assert "Unknown tool" in result
