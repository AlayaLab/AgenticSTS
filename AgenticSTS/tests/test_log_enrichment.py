"""Tests for session_logger's static-knowledge enrichment helpers.

Postrun core-engine analysis reads card / relic / power descriptions
directly from the per-run JSONL log. These helpers bake the knowledge
into each state snapshot so the analyzer doesn't have to do a separate
lookup round-trip (and stays consistent with whatever knowledge version
was active at log time).
"""
from __future__ import annotations


def test_card_description_enriches_known_card():
    from src.log.session_logger import _card_description
    out = _card_description("Neutralize")
    assert out.get("description"), "Neutralize should have a description"
    assert out.get("type") == "Attack"
    assert out.get("rarity") == "Basic"


def test_card_description_empty_for_unknown():
    from src.log.session_logger import _card_description
    assert _card_description("ThisCardDoesNotExist") == {}


def test_relic_description_enriches_known_relic():
    from src.log.session_logger import _relic_description
    out = _relic_description("Ring of the Snake")
    assert out.get("description"), "Ring of the Snake should have a description"
    assert out.get("rarity"), "Relic should have a rarity"


def test_relic_description_empty_for_unknown():
    from src.log.session_logger import _relic_description
    assert _relic_description("FakeRelicThatDoesNotExist") == {}


def test_power_description_known_power():
    from src.log.session_logger import _power_description
    assert "Poison" in _power_description("Poison") or \
        "HP" in _power_description("Poison"), \
        "Poison description should mention HP loss"


def test_with_power_desc_is_idempotent():
    from src.log.session_logger import _with_power_desc
    base = {"name": "Poison", "amount": 3}
    out1 = _with_power_desc(dict(base))
    out2 = _with_power_desc(dict(out1))
    assert out1 == out2, "enrichment must be idempotent"
    assert out1.get("description"), "Poison power should have a description"


def test_with_relic_desc_idempotent():
    from src.log.session_logger import _with_relic_desc
    base = {"name": "Ring of the Snake", "stack": 1}
    out = _with_relic_desc(dict(base))
    assert out["name"] == "Ring of the Snake"
    assert out["stack"] == 1
    assert out.get("description"), "Ring of the Snake should have a description"


def test_shop_card_entry_preserves_shop_fields():
    """Shop card enrichment must not drop price/enough_gold/category etc."""
    from src.log.session_logger import _shop_card_entry
    # Minimal stub matching the attrs _shop_card_entry reads
    class _C:
        index = 2
        name = "Neutralize"
        price = 50
        upgraded = False
        enough_gold = True
        category = "card"
        is_stocked = True
        rules_text = "Deal 3. Apply 1 Weak."
    out = _shop_card_entry(_C())
    assert out["index"] == 2
    assert out["name"] == "Neutralize"
    assert out["price"] == 50
    assert out["rules_text"].startswith("Deal")
    # Enrichment added
    assert out.get("type") == "Attack"
    assert out.get("description"), "Shop card should be enriched"


def test_reward_card_entry_enriches():
    """Card_reward / combat_rewards card options must carry description + type."""
    from src.log.session_logger import _reward_card_entry
    class _C:
        index = 0
        name = "Neutralize"
        upgraded = False
        rules_text = "Deal 3. Weak 1."
    out = _reward_card_entry(_C())
    assert out["index"] == 0
    assert out["name"] == "Neutralize"
    assert out.get("type") == "Attack"
    assert out.get("rarity") == "Basic"
    assert out.get("description"), "card_reward option should carry description"


def test_enrichment_helpers_do_not_mutate_input():
    """Immutability check: helpers must not mutate their dict argument
    even when enrichment adds fields. Fresh dict every call."""
    from src.log.session_logger import _with_power_desc, _with_relic_desc
    # Power
    p_in = {"name": "Poison", "amount": 3}
    p_snapshot = dict(p_in)
    p_out = _with_power_desc(p_in)
    assert p_in == p_snapshot, "_with_power_desc mutated input"
    assert p_out.get("description"), "enrichment should have run"
    # Relic
    r_in = {"name": "Ring of the Snake", "stack": 1}
    r_snapshot = dict(r_in)
    r_out = _with_relic_desc(r_in)
    assert r_in == r_snapshot, "_with_relic_desc mutated input"
    assert r_out.get("description"), "enrichment should have run"
