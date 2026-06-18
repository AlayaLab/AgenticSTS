"""Tests for tool validation pipeline: array binding, snapshot store, two-stage validation.

Covers:
- Module 1: bind_params array-aware binding (scalar vs array per schema type)
- Module 2: StateSnapshotStore capture, retrieval, disk flush, FIFO eviction
- Module 3: Stage 1 (binding dry-run) + Stage 2 (LLM quality judge)
- Module 4: DynamicToolRegistry.unregister()
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from src.brain.state_snapshot_store import StateSnapshotStore

# ── Helpers: build mock GameState ──────────────────────────────────


def _make_power(name: str, amount: int = 0) -> SimpleNamespace:
    return SimpleNamespace(name=name, amount=amount)


def _make_intent(damage=None, hits=None, total_damage=None, intent_type=None) -> SimpleNamespace:
    return SimpleNamespace(
        damage=damage, hits=hits, total_damage=total_damage, intent_type=intent_type,
    )


def _make_enemy(
    name: str = "Slime",
    current_hp: int = 50,
    max_hp: int = 60,
    block: int = 0,
    powers: list | None = None,
    intents: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        current_hp=current_hp,
        max_hp=max_hp,
        block=block,
        powers=powers or [],
        intents=intents or [],
    )


def _make_card(name: str = "Strike", energy_cost: int = 1, block=None, damage=None) -> SimpleNamespace:
    return SimpleNamespace(
        name=name, energy_cost=energy_cost, block=block, damage=damage,
        rarity="Common", card_type="Attack", rules_text="",
    )


def _make_gs(
    enemies: list | None = None,
    player_hp: int = 50,
    player_max_hp: int = 75,
    energy: int = 3,
    hand: list | None = None,
    deck: list | None = None,
    state_type: str = "monster",
    is_combat: bool = True,
    floor: int = 5,
    act: int = 1,
    gold: int = 100,
) -> SimpleNamespace:
    """Build a mock GameState for testing."""
    if enemies is None:
        enemies = [_make_enemy()]

    player = SimpleNamespace(
        block=5,
        powers=[_make_power("Dexterity", 2), _make_power("Strength", 1)],
    )
    combat = SimpleNamespace(player=player)
    raw = SimpleNamespace(
        combat=combat,
        run=SimpleNamespace(max_energy=3),
    )

    return SimpleNamespace(
        enemies=enemies,
        player_hp=player_hp,
        player_max_hp=player_max_hp,
        energy=energy,
        hand=hand or [],
        deck=deck or [],
        deck_size=len(deck or []),
        state_type=state_type,
        is_combat=is_combat,
        floor=floor,
        act=act,
        gold=gold,
        raw=raw,
        block=player.block,
        combat_round=1,
    )


# ── Module 1: Array-Aware Binding ──────────────────────────────────


class TestArrayBinding:
    """Verify bind_params returns arrays when schema declares type: array."""

    def test_enemy_hp_scalar_without_schema(self):
        """Without schema, enemy_hp returns scalar (backward compat)."""
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs(enemies=[
            _make_enemy(current_hp=100),
            _make_enemy(current_hp=60),
        ])
        result = bind_params({"enemy_hp": {}}, gs, schema=None)
        assert result is not None
        assert result["enemy_hp"] == 100  # scalar from enemies[0]

    def test_enemy_hp_array_with_schema(self):
        """With schema type=array, enemy_hp returns list of all enemies."""
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs(enemies=[
            _make_enemy(current_hp=100),
            _make_enemy(current_hp=60),
        ])
        schema = {"parameters": {"enemy_hp": {"type": "array"}}}
        result = bind_params({"enemy_hp": {}}, gs, schema=schema)
        assert result is not None
        assert result["enemy_hp"] == [100, 60]

    def test_poison_stacks_scalar_without_schema(self):
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs(enemies=[
            _make_enemy(powers=[_make_power("Poison", 10)]),
            _make_enemy(powers=[_make_power("Poison", 5)]),
        ])
        result = bind_params({"poison_stacks": {}}, gs, schema=None)
        assert result is not None
        assert result["poison_stacks"] == 10  # scalar from enemies[0]

    def test_poison_stacks_array_with_schema(self):
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs(enemies=[
            _make_enemy(powers=[_make_power("Poison", 10)]),
            _make_enemy(powers=[_make_power("Poison", 5)]),
        ])
        schema = {"parameters": {"poison_stacks": {"type": "array"}}}
        result = bind_params({"poison_stacks": {}}, gs, schema=schema)
        assert result is not None
        assert result["poison_stacks"] == [10, 5]

    def test_enemy_block_array_with_schema(self):
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs(enemies=[
            _make_enemy(block=8),
            _make_enemy(block=0),
        ])
        schema = {"parameters": {"enemy_block": {"type": "array"}}}
        result = bind_params({"enemy_block": {}}, gs, schema=schema)
        assert result is not None
        assert result["enemy_block"] == [8, 0]

    def test_enemy_vulnerable_array(self):
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs(enemies=[
            _make_enemy(powers=[_make_power("Vulnerable", 2)]),
            _make_enemy(powers=[]),
        ])
        schema = {"parameters": {"enemy_vulnerable": {"type": "array"}}}
        result = bind_params({"enemy_vulnerable": {}}, gs, schema=schema)
        assert result is not None
        assert result["enemy_vulnerable"] == [True, False]

    def test_nested_schema_properties(self):
        """Schema with properties nested under 'properties' key."""
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs(enemies=[
            _make_enemy(current_hp=100),
            _make_enemy(current_hp=60),
        ])
        schema = {
            "parameters": {
                "type": "object",
                "properties": {
                    "enemy_hp": {"type": "array", "items": {"type": "integer"}},
                },
            },
        }
        result = bind_params({"enemy_hp": {}}, gs, schema=schema)
        assert result is not None
        assert result["enemy_hp"] == [100, 60]

    def test_non_enemy_params_unaffected(self):
        """Non-enemy params like current_hp are unchanged regardless of schema."""
        from src.brain.tool_preprocessor import bind_params
        gs = _make_gs()
        schema = {"parameters": {"current_hp": {"type": "integer"}}}
        result = bind_params({"current_hp": {}}, gs, schema=schema)
        assert result is not None
        assert result["current_hp"] == 50  # always scalar


# ── Module 2: StateSnapshotStore ───────────────────────────────────


class TestStateSnapshotStore:
    """Verify snapshot capture, retrieval, and disk persistence."""

    def test_capture_combat_state(self):
        store = StateSnapshotStore(persist_path="/dev/null")
        store.capture("monster", {"screen": "combat"})
        snaps = store.get_snapshots(["monster"])
        assert len(snaps) == 1
        assert snaps[0].state_type == "monster"

    def test_ignore_non_combat_state(self):
        store = StateSnapshotStore(persist_path="/dev/null")
        store.capture("shop", {"screen": "shop"})
        assert store.get_snapshots(["shop"]) == []

    def test_ring_buffer_limit(self):
        store = StateSnapshotStore(persist_path="/dev/null")
        for i in range(25):
            store.capture("monster", {"floor": i})
        snaps = store.get_snapshots(["monster"], n=30)
        assert len(snaps) == 20  # ring buffer limit

    def test_most_recent_first(self):
        store = StateSnapshotStore(persist_path="/dev/null")
        store.capture("monster", {"floor": 1})
        store.capture("monster", {"floor": 2})
        snaps = store.get_snapshots(["monster"])
        assert snaps[0].raw_state["floor"] == 2  # most recent first

    def test_filter_by_state_type(self):
        store = StateSnapshotStore(persist_path="/dev/null")
        store.capture("monster", {"type": "monster"})
        store.capture("boss", {"type": "boss"})
        store.capture("elite", {"type": "elite"})
        assert len(store.get_snapshots(["boss"])) == 1
        assert len(store.get_snapshots(["monster", "elite"])) == 2

    def test_flush_to_disk_and_load(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshots.jsonl"
            store = StateSnapshotStore(persist_path=path)
            store.capture("monster", {"floor": 1})
            store.capture("boss", {"floor": 17})
            store.flush_to_disk()

            # Verify file written
            assert path.exists()
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 2

            # New store should load from disk
            store2 = StateSnapshotStore(persist_path=path)
            snaps = store2.get_snapshots(["monster", "boss"], n=5)
            assert len(snaps) == 2

    def test_disk_fifo_eviction(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "snapshots.jsonl"

            # Accumulate >100 entries on disk via multiple flush cycles
            # Ring buffer is 20, so each flush adds up to 20
            for batch in range(7):
                store = StateSnapshotStore(persist_path=path)
                for i in range(20):
                    store.capture("monster", {"floor": batch * 20 + i})
                store.flush_to_disk()

            # 7 batches × 20 = 140 attempted, but FIFO caps at 100
            lines = path.read_text().strip().split("\n")
            assert len(lines) == 100
            # Most recent entries should be preserved
            last_entry = json.loads(lines[-1])
            assert last_entry["raw_state"]["floor"] == 139

    def test_clear_memory(self):
        store = StateSnapshotStore(persist_path="/dev/null")
        store.capture("monster", {"floor": 1})
        store.clear_memory()
        assert store.get_snapshots(["monster"]) == []


# ── Module 3: Two-Stage Validation ─────────────────────────────────


# Minimal tool code for testing
GOOD_TOOL_CODE = '''
SCHEMA = {
    "name": "test_poison_calc",
    "description": "Calculate poison turns to kill enemy.",
    "parameters": {
        "enemy_hp": {"type": "array", "description": "List of enemy HP"},
        "poison_stacks": {"type": "array", "description": "List of poison stacks"},
    }
}

APPLICABLE_STATES = ["monster", "elite", "boss"]

def execute(enemy_hp, poison_stacks):
    results = []
    for i in range(len(enemy_hp)):
        hp = enemy_hp[i]
        poison = poison_stacks[i] if i < len(poison_stacks) else 0
        total = poison * (poison + 1) // 2
        results.append({"lethal": total >= hp, "turns": poison if total >= hp else -1})
    recommendation = "Focus defense" if all(r["lethal"] for r in results) else "Need more poison"
    return {"enemies": results, "recommendation": recommendation}

TEST_CASES = [
    {"description": "Lethal", "input": {"enemy_hp": [15], "poison_stacks": [5]},
     "expected": {"recommendation": "Focus defense"}},
    {"description": "Not lethal", "input": {"enemy_hp": [100], "poison_stacks": [5]},
     "expected": {"recommendation": "Need more poison"}},
]
'''


class TestValidationStage1:
    """Test binding dry-run validation."""

    def test_binding_succeeds_with_real_snapshots(self):
        """Tool with array params binds correctly to multi-enemy GameState."""
        from src.brain.evolution_engine import EvolutionEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            from src.brain.dynamic_tools import DynamicToolRegistry
            registry = DynamicToolRegistry(tmpdir)
            result = registry.register_tool("test_poison_calc", GOOD_TOOL_CODE, "test")
            assert result.startswith("SUCCESS"), f"Registration failed: {result}"

            # Build snapshot store with a real-ish snapshot
            snap_path = Path(tmpdir) / "snaps.jsonl"
            snap_store = StateSnapshotStore(persist_path=snap_path)

            # Create a raw state dict that parse_state can consume
            raw_state = _build_raw_mcp_state(
                enemies=[
                    {"name": "Slime", "hp": 50, "max_hp": 60, "block": 0, "poison": 10},
                    {"name": "Cultist", "hp": 30, "max_hp": 40, "block": 5, "poison": 3},
                ],
            )
            snap_store.capture("monster", raw_state)

            engine = EvolutionEngine(
                backend=MagicMock(),
                tool_executor=MagicMock(),
                dynamic_registry=registry,
                skill_library=None,
                snapshot_store=snap_store,
                tool_preprocessor=MagicMock(format_hints=lambda hints: "- test: recommendation=Focus defense"),
            )

            tool = registry.get("test_poison_calc")
            result = engine._validate_tool_binding(tool)
            assert result is None, f"Expected success, got: {result}"

    def test_binding_fails_no_snapshots_accepts(self):
        """No snapshots available → cold start grace → accept."""
        from src.brain.evolution_engine import EvolutionEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            from src.brain.dynamic_tools import DynamicToolRegistry
            registry = DynamicToolRegistry(tmpdir)
            registry.register_tool("test_poison_calc", GOOD_TOOL_CODE, "test")

            engine = EvolutionEngine(
                backend=MagicMock(),
                tool_executor=MagicMock(),
                dynamic_registry=registry,
                skill_library=None,
                snapshot_store=StateSnapshotStore(persist_path="/dev/null"),
            )

            tool = registry.get("test_poison_calc")
            result = engine._validate_tool_binding(tool)
            assert result is None  # Cold start grace


class TestValidationStage2:
    """Test LLM quality judge."""

    def test_helpful_verdict_accepts(self):
        from src.brain.evolution_engine import EvolutionEngine

        mock_response = SimpleNamespace(
            content=[SimpleNamespace(text="HELPFUL: This provides clear survival timeline.")]
        )
        mock_backend = MagicMock()
        mock_backend.call.return_value = mock_response

        engine = EvolutionEngine(
            backend=mock_backend,
            tool_executor=MagicMock(),
            dynamic_registry=MagicMock(),
            skill_library=None,
            tool_preprocessor=MagicMock(format_hints=lambda hints: "- test: Focus defense"),
        )
        engine._last_validation_success = (
            _make_gs(enemies=[
                _make_enemy(current_hp=50, powers=[_make_power("Poison", 10)]),
            ]),
            {"recommendation": "Focus defense"},
        )

        tool = SimpleNamespace(name="test_tool")
        result = engine._validate_tool_quality(tool)
        assert result is None  # accepted

    def test_redundant_verdict_rejects(self):
        from src.brain.evolution_engine import EvolutionEngine

        mock_response = SimpleNamespace(
            content=[SimpleNamespace(text="REDUNDANT: LLM can already compute poison math.")]
        )
        mock_backend = MagicMock()
        mock_backend.call.return_value = mock_response

        engine = EvolutionEngine(
            backend=mock_backend,
            tool_executor=MagicMock(),
            dynamic_registry=MagicMock(),
            skill_library=None,
            tool_preprocessor=MagicMock(format_hints=lambda hints: "- test: some hint"),
        )
        engine._last_validation_success = (_make_gs(), {"recommendation": "test"})

        tool = SimpleNamespace(name="test_tool")
        result = engine._validate_tool_quality(tool)
        assert result is not None
        assert "REJECTED" in result
        assert "redundant" in result.lower()

    def test_misleading_verdict_rejects(self):
        from src.brain.evolution_engine import EvolutionEngine

        mock_response = SimpleNamespace(
            content=[SimpleNamespace(text="MISLEADING: Wrong damage calculation.")]
        )
        mock_backend = MagicMock()
        mock_backend.call.return_value = mock_response

        engine = EvolutionEngine(
            backend=mock_backend,
            tool_executor=MagicMock(),
            dynamic_registry=MagicMock(),
            skill_library=None,
            tool_preprocessor=MagicMock(format_hints=lambda hints: "- test: wrong hint"),
        )
        engine._last_validation_success = (_make_gs(), {"recommendation": "test"})

        tool = SimpleNamespace(name="test_tool")
        result = engine._validate_tool_quality(tool)
        assert result is not None
        assert "REJECTED" in result
        assert "misleading" in result.lower()

    def test_judge_error_accepts(self):
        """If judge call fails (API error), accept the tool anyway."""
        from src.brain.evolution_engine import EvolutionEngine

        mock_backend = MagicMock()
        mock_backend.call.side_effect = RuntimeError("API timeout")

        engine = EvolutionEngine(
            backend=mock_backend,
            tool_executor=MagicMock(),
            dynamic_registry=MagicMock(),
            skill_library=None,
            tool_preprocessor=MagicMock(format_hints=lambda hints: "- test: hint"),
        )
        engine._last_validation_success = (_make_gs(), {"recommendation": "test"})

        tool = SimpleNamespace(name="test_tool")
        result = engine._validate_tool_quality(tool)
        assert result is None  # accept on judge error


# ── Module 4: Unregister ───────────────────────────────────────────


class TestUnregister:
    """Test DynamicToolRegistry.unregister() cleanup."""

    def test_unregister_removes_tool(self):
        from src.brain.dynamic_tools import DynamicToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = DynamicToolRegistry(tmpdir)
            result = registry.register_tool("test_poison_calc", GOOD_TOOL_CODE, "test")
            assert result.startswith("SUCCESS")
            assert registry.has("test_poison_calc")

            # Unregister
            removed = registry.unregister("test_poison_calc")
            assert removed is True
            assert not registry.has("test_poison_calc")

            # .py file deleted
            py_file = Path(tmpdir) / "test_poison_calc.py"
            assert not py_file.exists()

    def test_unregister_nonexistent_returns_false(self):
        from src.brain.dynamic_tools import DynamicToolRegistry

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = DynamicToolRegistry(tmpdir)
            assert registry.unregister("does_not_exist") is False


# ── Helper: Build raw MCP state payload ────────────────────────────


def _build_raw_mcp_state(
    enemies: list[dict] | None = None,
    player_hp: int = 50,
    player_max_hp: int = 75,
) -> dict:
    """Build a minimal raw MCP /state payload suitable for parse_state().

    This is a simplified version — only includes fields needed for
    tool binding tests. Real payloads have many more fields.
    """
    if enemies is None:
        enemies = [{"name": "Slime", "hp": 50, "max_hp": 60, "block": 0, "poison": 0}]

    enemy_list = []
    for e in enemies:
        powers = []
        if e.get("poison", 0) > 0:
            powers.append({"name": "Poison", "power_id": "Poison", "amount": e["poison"]})
        enemy_list.append({
            "name": e["name"],
            "current_hp": e["hp"],
            "max_hp": e["max_hp"],
            "block": e.get("block", 0),
            "powers": powers,
            "intents": [{"damage": 10, "hits": 1, "total_damage": 10, "intent_type": "ATTACK"}],
        })

    return {
        "screen": "combat",
        "state_type": "monster",
        "combat": {
            "player": {
                "current_hp": player_hp,
                "max_hp": player_max_hp,
                "block": 5,
                "powers": [],
                "energy": 3,
            },
            "enemies": enemy_list,
            "hand": [],
            "draw_pile": [],
            "discard_pile": [],
            "exhaust_pile": [],
            "round": 1,
        },
        "run": {
            "character": "Silent",
            "floor": 5,
            "act": 1,
            "max_energy": 3,
            "gold": 100,
            "deck": [],
            "relics": [],
            "potions": [],
        },
    }
