"""Test kill detection logic (isolated from AgentLoop)."""
from src.skills.replay_evaluator import remaining_plan_kills_boss


class FakeCard:
    def __init__(self, name, damage=None, total_damage=None, target_previews=None):
        self.name = name
        self.damage = damage
        self.total_damage = total_damage
        self.target_previews = target_previews or []


class FakeEnemy:
    def __init__(self, index, hp, block=0, is_alive=True):
        self.index = index
        self.current_hp = hp  # matches RawCombatEnemyPayload field name
        self.hp = hp  # fallback for getattr chain
        self.block = block
        self.is_alive = is_alive


class FakePlan:
    def __init__(self, card_name, is_potion=False, target_index=None):
        self.card_name = card_name
        self.is_potion = is_potion
        self.target_index = target_index


def test_exact_kill():
    hand = [FakeCard("Strike", damage=10, total_damage=10)]
    enemies = [FakeEnemy(0, hp=10, block=0)]
    remaining = [FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True


def test_not_enough_damage():
    hand = [FakeCard("Strike", damage=5, total_damage=5)]
    enemies = [FakeEnemy(0, hp=20, block=0)]
    remaining = [FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is False


def test_accounts_for_block():
    hand = [FakeCard("Strike", damage=15, total_damage=15)]
    enemies = [FakeEnemy(0, hp=10, block=5)]
    remaining = [FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True


def test_potion_ignored():
    hand = [FakeCard("Strike", damage=10, total_damage=10)]
    enemies = [FakeEnemy(0, hp=5, block=0)]
    remaining = [FakePlan("Potion", is_potion=True), FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True


def test_non_attack_ignored():
    hand = [FakeCard("Defend", damage=None, total_damage=None)]
    enemies = [FakeEnemy(0, hp=5, block=0)]
    remaining = [FakePlan("Defend")]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is False
