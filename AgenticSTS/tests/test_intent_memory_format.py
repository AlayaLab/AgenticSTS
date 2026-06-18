from src.brain.prompts._intent_fmt import format_enemy_intents_for_memory
from src.mcp_client.upstream_models import RawCombatEnemyIntentPayload, RawCombatEnemyPayload


def test_memory_format_prefers_structured_attack_label():
    enemy = RawCombatEnemyPayload(
        name="Sludge Spinner",
        intent="SLUDGE_BURST_MOVE",
        intents=[
            RawCombatEnemyIntentPayload(intent_type="Attack", label="14"),
        ],
    )

    assert format_enemy_intents_for_memory(enemy) == "Attack(14)"


def test_memory_format_uses_agent_view_fallback_instead_of_move_id():
    enemy = RawCombatEnemyPayload(
        name="Seapunk",
        intent="POSE_MOVE",
        intents=[],
    )

    assert format_enemy_intents_for_memory(enemy, fallback_intent="Buff, Defend") == "Buff, Defend"


def test_memory_format_drops_opaque_move_ids_without_better_fallback():
    enemy = RawCombatEnemyPayload(
        name="Mecha Knight",
        intent="FLAMETHROWER_MOVE",
        intents=[],
    )

    assert format_enemy_intents_for_memory(enemy) == "Unknown"
