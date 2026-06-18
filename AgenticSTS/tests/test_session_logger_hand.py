"""Verify _serialize_hand_card captures fields needed by trace renderer."""
from __future__ import annotations

from dataclasses import dataclass

from src.log.session_logger import SessionLogger


@dataclass
class _FakeCard:
    index: int = 0
    name: str = ""
    energy_cost: int = 1
    playable: bool = True
    target_type: str = "single"
    rules_text: str = ""
    damage: int | None = None
    block: int | None = None
    hits: int = 1
    total_damage: int | None = None
    target_previews: list = None
    upgraded: bool = False
    star_cost: int | None = None
    card_type: str = "Attack"
    enchantment_name: str | None = None

    def __post_init__(self) -> None:
        if self.target_previews is None:
            self.target_previews = []


def test_serialize_hand_card_has_enrichment_fields() -> None:
    card = _FakeCard(
        index=0, name="backstab", energy_cost=1,
        rules_text="Deal 11 damage. Only playable as first card each turn.",
        damage=11, total_damage=11,
        upgraded=True, card_type="Attack", star_cost=None,
        enchantment_name="swift",
    )
    data = SessionLogger._serialize_hand_card(card)
    assert data["upgraded"] is True
    assert data["card_type"] == "Attack"
    assert data["enchantment_name"] == "swift"
    assert "star_cost" in data
    assert data["star_cost"] is None


def test_serialize_hand_card_star_cost() -> None:
    card = _FakeCard(name="ice_lance", star_cost=1, card_type="Attack", damage=3)
    data = SessionLogger._serialize_hand_card(card)
    assert data["star_cost"] == 1


def test_serialize_hand_card_missing_fields_defaults() -> None:
    """Cards without new attributes must not crash serialization."""
    # Use a minimal object without the enrichment fields
    class OldCard:
        def __init__(self):
            self.index = 0
            self.name = "strike"
            self.energy_cost = 1
            self.playable = True
            self.target_type = "single"
            self.rules_text = "Deal 6 damage."
            self.damage = 6
            self.block = None
            self.hits = 1
            self.total_damage = 6
            self.target_previews = []

    card = OldCard()
    data = SessionLogger._serialize_hand_card(card)
    assert data["upgraded"] is False
    assert data["star_cost"] is None
    assert data["card_type"] == ""
    assert data["enchantment_name"] is None
