"""DynamicToolRegistry: load, validate, and execute agent-authored Python tools.

Agent-written tools live as `.py` files in `data/evolution/tools/`. Each file
exports ``SCHEMA`` (Anthropic tool_use dict), ``execute(**kwargs) -> str``, and
optionally ``TEST_CASES`` for sandbox validation.

Security model (Phase 1 — conservative):
- AST whitelist: only ``math``, ``collections``, ``itertools``, ``functools``
- Forbidden: ``import`` (except whitelist), ``open``, ``os``, ``sys``,
  ``subprocess``, ``__``-prefixed attribute access
- 1-second execution timeout per call
- ``compile()`` → AST scan → restricted-namespace ``exec()`` → TEST_CASES
"""

from __future__ import annotations

import ast
import logging
import re
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ── Sandbox configuration ───────────────────────────────────────

ALLOWED_MODULES: frozenset[str] = frozenset({
    "math", "collections", "itertools", "functools",
})

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "open", "exec", "eval", "compile", "globals", "locals",
    "getattr", "setattr", "delattr", "__import__",
    "breakpoint", "exit", "quit",
})

# NOTE: No explicit deny-list for modules needed — ALLOWED_MODULES is an
# allowlist, so anything not in it (os, sys, subprocess, etc.) is already
# blocked by the AST validator in visit_Import / visit_ImportFrom.

EXEC_TIMEOUT_SECONDS: float = 1.0


# ── Effectiveness scoring ──────────────────────────────────────


def compute_effectiveness(usage: int, success: int, runs_since: int) -> float:
    """Compute tool effectiveness score.

    Returns usage_rate * success_rate where:
    - usage_rate = average uses per run
    - success_rate = fraction of successful executions
    - New tools (runs_since=0) get benefit of doubt (score=1.0)
    """
    if runs_since == 0:
        return 1.0
    usage_rate = usage / max(1, runs_since)
    success_rate = success / max(1, usage)
    return usage_rate * success_rate


# ── Test case validation ───────────────────────────────────────


def _validate_test_case(
    execute_fn: Any,
    tc: dict,
    tool_name: str,
    idx: int,
) -> str | None:
    """Validate a single test case against execute_fn.

    Returns None on success, or a failure description string.

    Assertion dispatch (checked in order, all that match must pass):
    1. "expected_contains" (str) → assert str in str(result)
    2. "expected" (dict)        → per-key exact match on result dict
                                   float tolerance ±0.01, missing key → fail
    3. "expected" (str)         → same as expected_contains
    4. "expected_keys" (list)   → assert all keys present in result dict
    5. "expected_<field>_contains" → field-level substring match
    """
    tc_input = tc.get("input", {})
    try:
        result = execute_fn(**tc_input)
    except Exception as exc:
        return f"test case {idx} raised: {exc}"

    result_str = str(result)

    # 1. expected_contains (str)
    expected_contains = tc.get("expected_contains")
    if isinstance(expected_contains, str) and expected_contains:
        if expected_contains not in result_str:
            return (
                f"test case {idx}: expected_contains {expected_contains!r} "
                f"not in {result_str[:200]!r}"
            )

    # 2/3. expected (dict or str)
    expected = tc.get("expected")
    if isinstance(expected, dict) and expected:
        if not isinstance(result, dict):
            return (
                f"test case {idx}: expected dict result but got "
                f"{type(result).__name__}: {result_str[:200]}"
            )
        for key, exp_val in expected.items():
            if key not in result:
                return f"test case {idx}: missing key {key!r} in result"
            actual_val = result[key]
            # Bool exact match (before numeric check, since bool is subclass of int)
            if isinstance(exp_val, bool) or isinstance(actual_val, bool):
                if exp_val != actual_val:
                    return (
                        f"test case {idx}: key {key!r} expected {exp_val!r} "
                        f"but got {actual_val!r}"
                    )
                continue
            # Float tolerance
            if isinstance(exp_val, (int, float)) and isinstance(actual_val, (int, float)):
                if abs(float(exp_val) - float(actual_val)) > 0.01:
                    return (
                        f"test case {idx}: key {key!r} expected {exp_val} "
                        f"but got {actual_val}"
                    )
            elif exp_val != actual_val:
                return (
                    f"test case {idx}: key {key!r} expected {exp_val!r} "
                    f"but got {actual_val!r}"
                )
    elif isinstance(expected, str) and expected:
        if expected not in result_str:
            return (
                f"test case {idx}: expected {expected!r} not in {result_str[:200]!r}"
            )

    # 4. expected_keys (list)
    expected_keys = tc.get("expected_keys")
    if isinstance(expected_keys, list) and expected_keys:
        if not isinstance(result, dict):
            return (
                f"test case {idx}: expected_keys requires dict result but got "
                f"{type(result).__name__}"
            )
        for key in expected_keys:
            if key not in result:
                return f"test case {idx}: expected key {key!r} not in result"

    # 5. expected_<field>_contains (dynamic field-level substring match)
    for tc_key, tc_val in tc.items():
        if (
            tc_key.startswith("expected_")
            and tc_key.endswith("_contains")
            and tc_key not in ("expected_contains",)
            and isinstance(tc_val, str)
            and tc_val
        ):
            # Extract field name: "expected_warning_contains" → "warning"
            field_name = tc_key[len("expected_"):-len("_contains")]
            if isinstance(result, dict) and field_name in result:
                if tc_val not in str(result[field_name]):
                    return (
                        f"test case {idx}: {tc_key} {tc_val!r} not in "
                        f"result[{field_name!r}]={str(result[field_name])[:200]!r}"
                    )
            else:
                # Fall back to full result string match
                if tc_val not in result_str:
                    return (
                        f"test case {idx}: {tc_key} {tc_val!r} not in "
                        f"result {result_str[:200]!r}"
                    )

    # If no recognised assertion keys found, the test case is a smoke test
    # (checking that execute_fn doesn't raise). This is intentional.
    return None


# ── AST Validator ───────────────────────────────────────────────

class SandboxViolation(Exception):
    """Raised when agent-authored code violates sandbox rules."""


class _ASTValidator(ast.NodeVisitor):
    """Walk AST and reject forbidden patterns."""

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod = alias.name.split(".")[0]
            if mod not in ALLOWED_MODULES:
                allowed = ", ".join(sorted(ALLOWED_MODULES))
                self.violations.append(
                    f"Forbidden import: {alias.name} (allowed: {allowed})"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            mod = node.module.split(".")[0]
            if mod not in ALLOWED_MODULES:
                self.violations.append(f"Forbidden import from: {node.module}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self.violations.append(f"Forbidden dunder access: __{node.attr}")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self.violations.append(f"Forbidden name: {node.id}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check for forbidden function calls by name
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_NAMES:
            self.violations.append(f"Forbidden call: {node.func.id}()")
        self.generic_visit(node)


def _fix_json_literals(code: str) -> str:
    """Replace bare JSON boolean/null literals with Python equivalents.

    LLMs sometimes emit ``true``, ``false``, ``null`` (JSON) instead of the
    Python ``True``, ``False``, ``None``.  These cause ``NameError`` at exec
    time.

    Only substitutes outside string literals (single/double/triple quoted).
    Odd-indexed segments from splitting on the string-literal pattern are the
    quoted parts — left untouched.
    """
    # Pattern captures all Python string literals (triple before single)
    _STR_RE = re.compile(
        r'(""".*?"""|\'\'\'.*?\'\'\'|"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\')',
        re.DOTALL,
    )
    _LITERAL_MAP = [
        (re.compile(r"\btrue\b"), "True"),
        (re.compile(r"\bfalse\b"), "False"),
        (re.compile(r"\bnull\b"), "None"),
    ]
    parts = _STR_RE.split(code)
    for i, part in enumerate(parts):
        if i % 2 == 0:  # Non-string segment: apply substitutions
            for pattern, replacement in _LITERAL_MAP:
                part = pattern.sub(replacement, part)
            parts[i] = part
        # Odd index = string literal — leave unchanged
    return "".join(parts)


def _rescue_schema_from_code(code: str) -> dict | None:
    """Extract and parse a SCHEMA dict from raw Python source when exec missed it.

    Handles the common case where the LLM wrote ``schema = {`` (lowercase) or
    placed the assignment inside a guard block.  Tries two strategies:

    1. ``ast.literal_eval`` — correct for any valid Python dict literal.
    2. ``json.loads`` with light cleanup — fallback for near-JSON dicts.

    Returns the parsed dict if it has a ``"name"`` key, else ``None``.
    """
    # Match SCHEMA / schema / Schema assignment
    match = re.search(r"\b[Ss][Cc][Hh][Ee][Mm][Aa]\s*=\s*(\{)", code)
    if not match:
        return None

    # Walk the source forward to find the matching closing brace
    start = match.start(1)
    depth = 0
    end = start
    for i, ch in enumerate(code[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    else:
        return None  # Unbalanced braces

    schema_text = code[start:end]

    # Strategy 1: ast.literal_eval (handles Python dict syntax natively)
    try:
        parsed = ast.literal_eval(schema_text)
        if isinstance(parsed, dict) and "name" in parsed:
            return parsed
    except Exception:
        pass

    # Strategy 2: minimal JSON cleanup + json.loads
    try:
        import json
        cleaned = re.sub(r"\bTrue\b", "true", schema_text)
        cleaned = re.sub(r"\bFalse\b", "false", cleaned)
        cleaned = re.sub(r"\bNone\b", "null", cleaned)
        # Replace single-quoted keys/values with double quotes (naive but common)
        cleaned = re.sub(r"'([^'\\]*)'", r'"\1"', cleaned)
        # Remove trailing commas before closing braces/brackets
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict) and "name" in parsed:
            return parsed
    except Exception:
        pass

    return None


def validate_ast(source: str) -> list[str]:
    """Parse and validate source code against sandbox rules.

    Returns list of violation descriptions (empty = safe).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [f"Syntax error: {e}"]

    validator = _ASTValidator()
    validator.visit(tree)
    return validator.violations


# ── Restricted execution ────────────────────────────────────────

def _build_restricted_namespace() -> dict[str, Any]:
    """Build a restricted namespace for tool execution."""
    import collections
    import functools
    import itertools
    import math

    _allowed_modules = {
        "math": math,
        "collections": collections,
        "itertools": itertools,
        "functools": functools,
    }

    def _restricted_import(name: str, *args: Any, **kwargs: Any) -> Any:
        """Only allow importing whitelisted modules."""
        top = name.split(".")[0]
        if top not in _allowed_modules:
            raise ImportError(f"Import of '{name}' is not allowed in sandboxed tools")
        return _allowed_modules[top]

    return {
        "__builtins__": {
            # Restricted import for whitelisted modules
            "__import__": _restricted_import,
            # Safe builtins only
            "abs": abs, "all": all, "any": any, "bin": bin,
            "bool": bool, "chr": chr, "dict": dict, "divmod": divmod,
            "enumerate": enumerate, "filter": filter, "float": float,
            "format": format, "frozenset": frozenset, "hex": hex,
            "int": int, "isinstance": isinstance, "issubclass": issubclass,
            "iter": iter, "len": len, "list": list, "map": map,
            "max": max, "min": min, "next": next, "oct": oct,
            "ord": ord, "pow": pow, "print": print, "range": range,
            "repr": repr, "reversed": reversed, "round": round,
            "set": set, "slice": slice, "sorted": sorted, "str": str,
            "sum": sum, "tuple": tuple, "zip": zip,
            # NOTE: type() intentionally excluded — 3-arg form can create
            # classes with arbitrary dunder methods. Pure computation tools
            # should not need type().
            "True": True, "False": False, "None": None,
            "ValueError": ValueError, "TypeError": TypeError,
            "KeyError": KeyError, "IndexError": IndexError,
            "ZeroDivisionError": ZeroDivisionError,
            "RuntimeError": RuntimeError,
        },
        # Pre-imported for convenience (also available via import statement)
        **_allowed_modules,
    }


def _exec_with_elapsed_check(
    code: str,
    namespace: dict,
    timeout: float = EXEC_TIMEOUT_SECONDS,
) -> None:
    """Execute code in namespace with a post-hoc elapsed-time check.

    NOT a preemptive timeout — infinite loops will block the caller.
    For Phase 1, we trust that AST-validated pure-computation tools
    complete quickly. The elapsed check catches unexpectedly slow
    (but terminating) code. True preemption would require threading.
    """
    start = time.monotonic()
    exec(code, namespace)  # noqa: S102 — sandboxed namespace
    elapsed = time.monotonic() - start
    if elapsed > timeout:
        raise SandboxViolation(f"Execution took {elapsed:.2f}s (limit: {timeout}s)")


# ── Schema normalization helpers ────────────────────────────────

# Map simplified type names to JSON Schema types
_TYPE_MAP: dict[str, str] = {
    "int": "integer",
    "integer": "integer",
    "float": "number",
    "number": "number",
    "str": "string",
    "string": "string",
    "bool": "boolean",
    "boolean": "boolean",
    "array": "array",
    "list": "array",
    "object": "object",
    "dict": "object",
}

_VALID_JSON_SCHEMA_TYPES = frozenset({
    "string", "integer", "number", "boolean", "array", "object", "null",
})


def _extract_raw_params(schema: dict) -> dict[str, dict]:
    """Extract parameter definitions from a SCHEMA dict.

    Handles three container keys: "parameters", "input_schema", "input".
    If the container is already a JSON Schema object (has "type"+"properties"),
    unwraps to the properties dict.

    Returns a dict mapping param_name -> raw definition (dict or str).
    """
    container = schema.get(
        "parameters",
        schema.get("input_schema", schema.get("input", schema.get("properties", {}))),
    )
    if not isinstance(container, dict):
        return {}

    # JSON Schema wrapper: {"type": "object", "properties": {...}}
    if "type" in container and "properties" in container:
        return container.get("properties", {})

    # Filter out JSON Schema meta-keys that aren't param names
    meta_keys = {"type", "required", "additionalProperties", "returns"}
    return {k: v for k, v in container.items() if k not in meta_keys}


def _normalize_param(raw: str | dict) -> dict:
    """Normalize a single parameter definition to JSON Schema format.

    Handles:
    - str: "int — description" → {"type": "integer", "description": "description"}
    - dict with "type": "int" → {"type": "integer", ...}
    - dict already in JSON Schema format → pass through
    """
    if isinstance(raw, str):
        # Format: "int — description" or "list of dicts — desc"
        # Split on em dash (with or without surrounding spaces)
        parts = raw.split("—", 1)
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

    if isinstance(raw, dict):
        result = dict(raw)  # shallow copy to avoid mutation

        # Normalize type name if present
        if "type" in result:
            raw_type = str(result["type"]).lower()
            compound = re.match(r"^(list|array)\[(\w+)]$", raw_type)
            if compound:
                result["type"] = "array"
                inner = _TYPE_MAP.get(compound.group(2), "object")
                result["items"] = {"type": inner}
            else:
                result["type"] = _TYPE_MAP.get(raw_type, raw_type)

        # If no type at all, infer "string" as safe default
        if "type" not in result:
            result["type"] = "string"

        # JSON Schema 2020-12 requires "items" for array types
        if result["type"] == "array" and "items" not in result:
            result["items"] = {"type": "object"}

        # Remove non-standard keys that break strict JSON Schema validation
        for bad_key in ("required", "desc", "default"):
            if bad_key in result and bad_key != "description":
                # "required" at property level is invalid (belongs in parent)
                # "desc" is non-standard (should be "description")
                # "default" at property level may confuse some validators
                if bad_key == "desc":
                    # Promote "desc" to "description"
                    if "description" not in result:
                        result["description"] = result.pop("desc")
                    else:
                        del result["desc"]
                elif bad_key == "required":
                    del result["required"]
                elif bad_key == "default":
                    del result["default"]

        # Final guard: reject any type not in JSON Schema spec
        if result.get("type") not in _VALID_JSON_SCHEMA_TYPES:
            result["type"] = "string"

        return result

    return {"type": "string"}


def _normalize_schema(schema: dict) -> dict:
    """Normalize a tool SCHEMA to Anthropic tool_use format.

    Input formats handled:
    - "parameters": {"key": {"type": "int", ...}}  (dict_values)
    - "parameters": {"key": "type — description"}  (string_description)
    - "input": {"key": "description"}              (legacy key)
    - Already Anthropic format with "input_schema"  (pass through)

    Output: {"name": ..., "description": ..., "input_schema": {"type": "object", ...}}
    """
    name = schema.get("name", "unknown")
    description = schema.get("description", "") or "(no description)"

    # Extract raw params and normalize each one
    raw_params = _extract_raw_params(schema)
    properties: dict[str, dict] = {}
    for pname, pdef in raw_params.items():
        properties[pname] = _normalize_param(pdef)

    # Extract required list if present (from multiple possible locations)
    required: list[str] = []
    container = schema.get(
        "parameters",
        schema.get("input_schema", schema.get("input", schema.get("properties", {}))),
    )
    if isinstance(container, dict):
        req = container.get("required", [])
        if isinstance(req, list):
            required = [r for r in req if r in properties]
    # Also check schema root level
    if not required:
        req = schema.get("required", [])
        if isinstance(req, list):
            required = [r for r in req if r in properties]

    input_schema: dict = {
        "type": "object",
        "properties": properties,
    }
    if required:
        input_schema["required"] = required

    return {
        "name": name,
        "description": description,
        "input_schema": input_schema,
    }


# ── Runtime bindability classification (P0-3) ──────────────────

# Parameters that can be automatically bound from GameState at decision time.
# Combat state: HP, block, energy, debuffs/buffs, enemies, intents.
# Run state: deck, floor, act, gold.
AUTO_BINDABLE: frozenset[str] = frozenset({
    # Player vitals
    "current_hp", "player_hp", "max_hp",
    "current_block",
    "energy", "energy_available", "current_energy", "energy_per_turn",
    # Player buffs/debuffs
    "dexterity", "strength", "current_strength",
    "frailed", "buffer_active",
    "accuracy_stacks",
    # Enemy info
    "enemies", "enemy_hp", "enemy_block", "num_enemies",
    "enemy_vulnerable", "poison_stacks",
    # Enemy intents (computed)
    "incoming_damage", "incoming_damage_per_turn",
    "enemy_damage", "hits_per_turn",
    "enemy_attacks",
    # Deck / hand
    "deck", "cards", "deck_cards", "card_names",
    "deck_size", "basic_card_count",
    "hand", "block_cards_in_hand",
    # Run progress
    "floor", "current_floor", "act",
    "current_gold", "gold",
})

# Parameters that require plan output, candidate selection, or subjective judgment.
NOT_BINDABLE: frozenset[str] = frozenset({
    # Plan-dependent
    "planned_block", "planned_damage",
    "block_cards",  # which cards to play (not just what's in hand)
    "attack_cards",
    "candidate_card", "play_sequence",
    "target_enemy_index",
    "num_shivs",
    "extra_stacks_per_turn", "extra_stacks_this_turn",
    "damage_multiplier",
    "alternative_block",
    "block_per_turn",
    # Candidate / removal
    "card_to_remove", "proposed_removal", "strikes_to_remove",
    "removed_this_session", "original_deck",
    # Config / thresholds
    "has_key_upgrade",
    "minimum_bonus_threshold", "min_attacks", "min_survival_hp",
    "damage_per_turn_available",
    "max_turns", "turns_remaining",
    "phantom_blades_bonus",
    # Event-specific (not generic GameState)
    "hp_cost", "gold_cost",
    "hp_cost_is_percentage", "gold_cost_is_percentage",
})


def classify_tool_runtime_mode(
    name: str,
    registry: "DynamicToolRegistry",
) -> str:
    """Classify a dynamic tool as state_derived or plan_evaluator.

    state_derived: ALL parameters can be auto-bound from GameState.
      → Can be run before LLM call as preprocessing hints.

    plan_evaluator: Some parameters depend on candidate plans/hypothetical values.
      → Requires LLM output first; future P2 integration.

    Returns "unknown" if the tool is not registered.

    Priority: explicit TOOL_TYPE declaration in .py file > auto-inference.
    """
    tool = registry.get(name)
    if tool is None:
        return "unknown"

    # Check for explicit TOOL_TYPE in the tool's schema (loaded from .py namespace)
    schema = tool.schema
    tool_type = schema.get("TOOL_TYPE")
    if tool_type in ("state_derived", "plan_evaluator"):
        return tool_type

    # Auto-infer from parameter names
    params = _extract_raw_params(schema)
    if not params:
        # No parameters = pure state query, treat as state_derived
        return "state_derived"

    for pname in params:
        if pname in NOT_BINDABLE:
            return "plan_evaluator"
        if pname not in AUTO_BINDABLE:
            # Unknown param — conservative classification
            return "plan_evaluator"

    return "state_derived"


def classify_all_tools(
    registry: "DynamicToolRegistry",
) -> dict[str, str]:
    """Classify all registered tools. Returns {name: mode}."""
    return {name: classify_tool_runtime_mode(name, registry) for name in registry.names()}


# ── Tool wrapper ────────────────────────────────────────────────

class DynamicTool:
    """A single agent-authored tool loaded from a .py file."""

    __slots__ = ("name", "schema", "execute_fn", "test_cases", "source_path",
                 "usage_count", "success_count", "created_at", "motivation",
                 "deactivated", "format_compact_fn", "creation_run")

    def __init__(
        self,
        name: str,
        schema: dict,
        execute_fn: Any,
        test_cases: list[dict],
        source_path: Path,
        motivation: str = "",
    ) -> None:
        self.name = name
        self.schema = schema
        self.execute_fn = execute_fn
        self.test_cases = test_cases
        self.source_path = source_path
        self.usage_count = 0
        self.success_count = 0
        self.created_at = time.time()
        self.motivation = motivation
        self.deactivated = False
        self.format_compact_fn = None
        self.creation_run = 0

    def execute_raw(self, **kwargs: Any) -> Any:
        """Run the tool and return the raw result without str conversion."""
        self.usage_count += 1
        try:
            result = self.execute_fn(**kwargs)
            self.success_count += 1
            return result
        except Exception as exc:
            return f"Tool {self.name} execution error: {exc}"

    def execute(self, **kwargs: Any) -> str:
        """Run the tool's execute function in a restricted namespace."""
        return str(self.execute_raw(**kwargs))


# ── Registry ────────────────────────────────────────────────────

class DynamicToolRegistry:
    """Manages agent-authored dynamic tools.

    Loads tools from disk, validates via AST sandbox, runs test cases,
    and provides schema/execution interface for V2 engine integration.
    """

    def __init__(self, tools_dir: str | Path | None = None) -> None:
        if tools_dir is None:
            from src.storage import paths
            tools_dir = paths.evolution_tools_dir()
        self._tools_dir = Path(tools_dir)
        self._tools: dict[str, DynamicTool] = {}
        self._total_runs: int = 0
        self._retirement_state: dict[str, dict] = {}  # name -> {deactivated_at_sweep, consecutive_sweeps}

    @property
    def count(self) -> int:
        return len(self._tools)

    def has(self, name: str) -> bool:
        """Check if a dynamic tool with this name is registered."""
        return name in self._tools

    def get(self, name: str) -> DynamicTool | None:
        return self._tools.get(name)

    def names(self) -> frozenset[str]:
        return frozenset(self._tools.keys())

    def get_schemas(self) -> list[dict]:
        """Return raw schemas for all registered tools (original format)."""
        return [t.schema for t in self._tools.values()]

    # ── Schema normalization (P0-2) ────────────────────────────

    def get_param_info(self, name: str) -> dict[str, dict] | None:
        """Return raw parameters dict for runtime bindability analysis.

        Extracts parameter definitions from the tool's SCHEMA without
        any format conversion. Returns None if tool not found.

        The returned dict maps parameter names to their raw definitions,
        which may be:
        - dict: {"type": "int", "description": "..."}
        - str: "int — description"
        """
        tool = self._tools.get(name)
        if tool is None:
            return None
        return _extract_raw_params(tool.schema)

    def get_normalized_schema(self, name: str) -> dict | None:
        """Return Anthropic-compatible tool_use schema for a single tool.

        Only does format conversion — no semantic inference (e.g., does
        not guess which parameters are required).

        Returns None if tool not found.
        """
        tool = self._tools.get(name)
        if tool is None:
            return None
        return _normalize_schema(tool.schema)

    def get_normalized_schemas(self) -> list[dict]:
        """Return all schemas in Anthropic format. For evolution agent use."""
        return [_normalize_schema(t.schema) for t in self._tools.values()]

    def execute(self, name: str, params: dict) -> str:
        """Execute a registered tool by name. Returns result string."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Unknown dynamic tool: {name}"
        return tool.execute(**params)

    # ── Loading ─────────────────────────────────────────────────

    def load_all(self) -> int:
        """Load all valid tools from the tools directory.

        Returns count of successfully loaded tools.
        """
        if not self._tools_dir.exists():
            logger.debug("No tools directory at %s", self._tools_dir)
            return 0

        loaded = 0
        for py_file in sorted(self._tools_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            try:
                tool = self._load_tool_file(py_file)
                if tool is not None:
                    self._tools[tool.name] = tool
                    loaded += 1
                    logger.info("Loaded dynamic tool: %s from %s", tool.name, py_file.name)
            except Exception as exc:
                logger.warning("Failed to load tool %s: %s", py_file.name, exc)

        if loaded:
            logger.info("DynamicToolRegistry: %d tools loaded", loaded)
        return loaded

    def _load_tool_file(self, path: Path) -> DynamicTool | None:
        """Load and validate a single tool file.

        Returns None if validation fails.
        """
        source = path.read_text(encoding="utf-8")

        # Step 1: AST validation
        violations = validate_ast(source)
        if violations:
            logger.warning("Tool %s failed AST validation: %s", path.name, violations)
            return None

        # Step 2: Execute in restricted namespace
        namespace = _build_restricted_namespace()
        try:
            _exec_with_elapsed_check(source, namespace)
        except SandboxViolation as exc:
            logger.warning("Tool %s sandbox violation: %s", path.name, exc)
            return None
        except Exception as exc:
            logger.warning("Tool %s execution failed: %s", path.name, exc)
            return None

        # Step 3: Extract SCHEMA, execute, TEST_CASES
        schema = namespace.get("SCHEMA")
        execute_fn = namespace.get("execute")
        test_cases = namespace.get("TEST_CASES", [])

        if not isinstance(schema, dict) or "name" not in schema:
            logger.warning("Tool %s: missing or invalid SCHEMA dict", path.name)
            return None
        if not callable(execute_fn):
            logger.warning("Tool %s: missing execute() function", path.name)
            return None

        tool_name = schema["name"]

        # Step 4: Run test cases (structured validation)
        if test_cases:
            for i, tc in enumerate(test_cases):
                failure = _validate_test_case(execute_fn, tc, tool_name, i)
                if failure is not None:
                    logger.warning("Tool %s: %s", tool_name, failure)
                    return None

        # Capture optional TOOL_TYPE for runtime classification (P0-3)
        tool_type = namespace.get("TOOL_TYPE")
        if tool_type in ("state_derived", "plan_evaluator"):
            schema["TOOL_TYPE"] = tool_type

        # Capture optional APPLICABLE_STATES for preprocessing (P1)
        applicable_states = namespace.get("APPLICABLE_STATES")
        if isinstance(applicable_states, (list, tuple, set, frozenset)):
            schema["APPLICABLE_STATES"] = list(applicable_states)

        # Capture optional FORMAT_COMPACT for compact hint formatting
        format_compact_fn = namespace.get("FORMAT_COMPACT")

        motivation = namespace.get("MOTIVATION", "")
        tool = DynamicTool(
            name=tool_name,
            schema=schema,
            execute_fn=execute_fn,
            test_cases=test_cases,
            source_path=path,
            motivation=motivation,
        )
        if callable(format_compact_fn):
            tool.format_compact_fn = format_compact_fn
        return tool

    # ── Quality gate helpers ─────────────────────────────────────

    def _check_dedup(self, name: str, schema: dict) -> str | None:
        """Check for duplicate tools. Returns rejection message or None."""
        new_words = set(name.split("_"))
        new_params = set(_extract_raw_params(schema).keys())

        for existing in self._tools.values():
            # Name word overlap
            ex_words = set(existing.name.split("_"))
            if new_words and ex_words:
                overlap = len(new_words & ex_words) / max(len(new_words), len(ex_words))
                if overlap > 0.8:
                    return (
                        f"Similar tool already exists: {existing.name} "
                        f"(name overlap {overlap:.0%}). "
                        f"Author a tool with different functionality."
                    )

            # Param overlap (Jaccard)
            ex_params = set(_extract_raw_params(existing.schema).keys())
            if new_params and ex_params:
                union = new_params | ex_params
                jaccard = len(new_params & ex_params) / len(union) if union else 0
                if jaccard > 0.8:
                    return (
                        f"Similar tool already exists: {existing.name} "
                        f"(param overlap {jaccard:.0%}). "
                        f"Author a tool with different parameters."
                    )

        return None

    # ── Registration (from EvolutionEngine) ─────────────────────

    def register_tool(self, tool_name: str, code: str, motivation: str = "") -> str:
        """Validate and register a new tool from code string.

        Writes the .py file to disk, then loads it.
        Returns a status message (success or failure reason).
        """
        import re

        # Sanitize tool_name to prevent path traversal
        tool_name = re.sub(r"[^a-zA-Z0-9_]", "_", tool_name)
        if not tool_name:
            return "REJECTED: tool_name must contain at least one alphanumeric character."

        # Pre-pass: normalize JSON boolean/null literals that LLMs sometimes emit.
        # Word-boundary substitution is safe because `true/false/null` are not
        # valid Python names — the exec step would fail with NameError otherwise.
        code = _fix_json_literals(code)

        # Step 1: AST validation
        violations = validate_ast(code)
        if violations:
            return f"REJECTED: AST violations: {'; '.join(violations)}"

        # Step 2: Execute in sandbox to validate
        namespace = _build_restricted_namespace()
        try:
            _exec_with_elapsed_check(code, namespace)
        except SandboxViolation as exc:
            return f"REJECTED: Sandbox violation: {exc}"
        except Exception as exc:
            return f"REJECTED: Execution error: {exc}"

        # Step 3: Validate exports
        schema = namespace.get("SCHEMA")
        execute_fn = namespace.get("execute")
        test_cases = namespace.get("TEST_CASES", [])

        # SCHEMA rescue: if exec succeeded but SCHEMA is missing/invalid, try to
        # extract it directly from the code text (handles lowercase `schema = {}`
        # or SCHEMA defined inside a conditional block).
        if not isinstance(schema, dict) or "name" not in schema:
            rescued = _rescue_schema_from_code(code)
            if rescued:
                logger.info("SCHEMA rescue succeeded for tool '%s'", tool_name)
                schema = rescued
                namespace["SCHEMA"] = schema
            else:
                return "REJECTED: Missing or invalid SCHEMA dict (must have 'name' key)"
        if not callable(execute_fn):
            return "REJECTED: Missing execute() function"

        actual_name = schema["name"]
        # Sanitize actual_name too (used for filename)
        safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", actual_name)
        if not safe_name:
            return "REJECTED: SCHEMA name must contain at least one alphanumeric character."

        # Step 4: Run test cases (structured validation)
        if test_cases:
            for i, tc in enumerate(test_cases):
                failure = _validate_test_case(execute_fn, tc, actual_name, i)
                if failure is not None:
                    return f"REJECTED: {failure}"

        # ── Quality Gate: APPLICABLE_STATES required ──
        applicable = namespace.get("APPLICABLE_STATES")
        if not isinstance(applicable, (list, tuple, set, frozenset)) or not applicable:
            return (
                "REJECTED: APPLICABLE_STATES is required. "
                "Declare which state types this tool applies to. "
                "Valid: monster, elite, boss, map, rest_site, shop, card_reward, "
                "card_select, event, hand_select, treasure, relic_select"
            )

        # ── Quality Gate: Minimum 2 test cases with assertions ──
        if len(test_cases) < 2:
            return f"REJECTED: Need at least 2 TEST_CASES (got {len(test_cases)})."

        _ASSERTION_KEYS = {"expected", "expected_contains", "expected_keys"}
        assertion_count = 0
        for tc in test_cases:
            if any(k in tc for k in _ASSERTION_KEYS):
                assertion_count += 1
            elif any(
                k.startswith("expected_") and k.endswith("_contains")
                for k in tc
            ):
                assertion_count += 1
        if assertion_count < 1:
            return (
                "REJECTED: At least 1 test case must have an assertion "
                "(expected, expected_contains, expected_keys, or "
                "expected_<field>_contains)."
            )

        # ── Quality Gate: Dedup check ──
        dedup_msg = self._check_dedup(actual_name, schema)
        if dedup_msg:
            return f"REJECTED: {dedup_msg}"

        # Step 5: Write to disk (use schema name for filename consistency)
        self._tools_dir.mkdir(parents=True, exist_ok=True)
        file_path = self._tools_dir / f"{safe_name}.py"
        file_path.write_text(code, encoding="utf-8")

        # Step 6: Load and register
        tool = DynamicTool(
            name=actual_name,
            schema=schema,
            execute_fn=execute_fn,
            test_cases=test_cases,
            source_path=file_path,
            motivation=motivation,
        )
        tool.creation_run = self._total_runs
        self._tools[actual_name] = tool
        logger.info("Registered new dynamic tool: %s (%s)", actual_name, file_path.name)
        return f"SUCCESS: Tool '{actual_name}' registered and available for future runs."

    # ── Stats ───────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Return usage stats for all registered tools."""
        tool_stats: dict[str, Any] = {
            t.name: {
                "usage_count": t.usage_count,
                "success_count": t.success_count,
                "motivation": t.motivation,
            }
            for t in self._tools.values()
        }
        # Identify promotion candidates: high-effectiveness, mature, reliable tools
        candidates: list[str] = []
        for t in self._tools.values():
            if t.deactivated:
                continue
            runs_since = max(1, self._total_runs - getattr(t, "creation_run", 0))
            score = compute_effectiveness(t.usage_count, t.success_count, runs_since)
            success_rate = t.success_count / max(1, t.usage_count)
            if score > 2.0 and runs_since > 20 and success_rate > 0.95:
                candidates.append(t.name)
        tool_stats["promote_candidates"] = candidates
        return tool_stats

    def save_stats(self, path: Path | None = None) -> None:
        """Persist usage stats to JSON (survives process restarts)."""
        if path is None:
            path = self._tools_dir / "tool_stats.json"
        import json
        data: dict[str, Any] = {
            "__meta__": {"total_runs": self._total_runs},
        }
        for t in self._tools.values():
            data[t.name] = {
                "usage_count": t.usage_count,
                "success_count": t.success_count,
                "creation_run": getattr(t, "creation_run", 0),
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        # Save retirement state separately
        ret_path = self._tools_dir / "retirement_state.json"
        ret_path.write_text(json.dumps(self._retirement_state, indent=2), encoding="utf-8")

    def load_stats(self, path: Path | None = None) -> None:
        """Restore usage stats from JSON after process restart."""
        if path is None:
            path = self._tools_dir / "tool_stats.json"
        if not path.exists():
            return
        import json
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            meta = data.pop("__meta__", {})
            self._total_runs = meta.get("total_runs", 0)
            for name, counts in data.items():
                tool = self._tools.get(name)
                if tool is not None:
                    tool.usage_count = counts.get("usage_count", 0)
                    tool.success_count = counts.get("success_count", 0)
                    tool.creation_run = counts.get("creation_run", 0)
            logger.debug("Loaded tool stats for %d tools from %s", len(data), path)
        except Exception as exc:
            logger.warning("Failed to load tool stats from %s: %s", path, exc)

        # Load retirement state
        ret_path = self._tools_dir / "retirement_state.json"
        if ret_path.exists():
            try:
                self._retirement_state = json.loads(ret_path.read_text(encoding="utf-8"))
                # Mark tools as deactivated
                for name, state in self._retirement_state.items():
                    tool = self._tools.get(name)
                    if tool and state.get("consecutive_sweeps", 0) >= 1:
                        tool.deactivated = True
            except Exception as exc:
                logger.warning("Failed to load retirement state: %s", exc)

    def unregister(self, name: str) -> bool:
        """Remove a tool from registry, delete its .py file and stats entry.

        Returns True if the tool was found and removed, False otherwise.
        Called by the validation pipeline when a newly authored tool fails
        real-state validation.
        """
        tool = self._tools.pop(name, None)
        if tool is None:
            return False

        # Delete .py file from disk
        if tool.source_path and tool.source_path.exists():
            try:
                tool.source_path.unlink()
                logger.info("Deleted tool file: %s", tool.source_path)
            except OSError as exc:
                logger.warning("Failed to delete tool file %s: %s", tool.source_path, exc)

        # Clean up retirement state
        self._retirement_state.pop(name, None)

        logger.info("Unregistered dynamic tool: %s", name)
        return True

    def increment_run_counter(self) -> None:
        """Increment total run counter. Called from agent loop at run start."""
        self._total_runs += 1

    def retirement_sweep(self) -> list[str]:
        """Run retirement sweep. Returns list of action descriptions.

        Tools with low effectiveness get deactivated on first offense,
        deleted on second consecutive sweep.
        """
        import config as _config

        threshold = getattr(_config, "TOOL_RETIREMENT_SCORE_THRESHOLD", 0.1)
        min_age = getattr(_config, "TOOL_RETIREMENT_MIN_AGE_RUNS", 5)
        delete_after = getattr(_config, "TOOL_RETIREMENT_DELETE_AFTER_SWEEPS", 2)

        actions: list[str] = []

        for name in list(self._tools.keys()):
            tool = self._tools[name]
            runs_since = max(0, self._total_runs - getattr(tool, "creation_run", 0))

            if runs_since < min_age:
                continue  # Too new

            score = compute_effectiveness(tool.usage_count, tool.success_count, runs_since)

            if score >= threshold:
                # Tool is healthy — remove from retirement state if present
                if name in self._retirement_state:
                    del self._retirement_state[name]
                    tool.deactivated = False
                    actions.append(f"REINSTATED: {name} (score={score:.2f})")
                continue

            # Low score — check retirement state
            state = self._retirement_state.get(name, {})
            consecutive = state.get("consecutive_sweeps", 0) + 1

            if consecutive >= delete_after:
                # Delete the tool
                if tool.source_path.exists():
                    tool.source_path.unlink()
                del self._tools[name]
                if name in self._retirement_state:
                    del self._retirement_state[name]
                actions.append(f"DELETED: {name} (score={score:.2f}, {consecutive} consecutive sweeps)")
            else:
                # Deactivate
                tool.deactivated = True
                self._retirement_state[name] = {
                    "deactivated_at_sweep": self._total_runs,
                    "consecutive_sweeps": consecutive,
                }
                actions.append(f"DEACTIVATED: {name} (score={score:.2f}, sweep {consecutive})")

        return actions
