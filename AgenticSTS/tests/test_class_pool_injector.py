"""Tests for class_pool_injector — uses real upstream cards.json."""
from __future__ import annotations

from src.knowledge.class_pool_injector import (
    class_pool_card_names,
    render_class_pool_section,
)


def test_render_class_pool_section_silent_has_88_lines():
    section = render_class_pool_section("Silent")
    body_lines = [l for l in section.splitlines() if l.startswith("- ")]
    # Format: "- Name | Cost | Type | Rarity | Target | Description"
    assert len(body_lines) == 88
    assert "## Class Pool Reference (Silent — 88 cards)" in section


def test_render_class_pool_section_has_hedge_line():
    section = render_class_pool_section("Silent")
    assert "FULL static class pool" in section
    assert "combo-space awareness only" in section


def test_render_class_pool_section_strips_bbcode():
    section = render_class_pool_section("Silent")
    # No raw BBCode brackets in the rendered text
    assert "[gold]" not in section
    assert "[/gold]" not in section
    assert "[img]" not in section


def test_render_class_pool_section_unknown_character_returns_empty():
    assert render_class_pool_section("banana") == ""
    assert render_class_pool_section("") == ""


def test_render_class_pool_section_excludes_colorless():
    section = render_class_pool_section("Silent")
    # Bandage Up is a colorless card; it must not leak into the silent pool
    assert "Bandage Up" not in section


def test_render_class_pool_section_normalizes_character_alias():
    # "the silent" canonicalizes to silent
    a = render_class_pool_section("Silent")
    b = render_class_pool_section("the silent")
    assert a == b


def test_class_pool_card_names_returns_lowercase_set():
    names = class_pool_card_names("Silent")
    assert isinstance(names, frozenset)
    assert len(names) == 88
    # All lowercase
    assert all(n == n.lower() for n in names)
    assert "backstab" in names
    assert "abrasive" in names


def test_class_pool_card_names_unknown_returns_empty():
    assert class_pool_card_names("banana") == frozenset()


def test_class_pool_section_caches_per_character(monkeypatch):
    """Second call must not re-read the JSON file."""
    import src.knowledge.class_pool_injector as cpi
    cpi._SECTION_CACHE.clear()
    cpi._POOL_CACHE.clear()
    cpi._CARDS_JSON_CACHE = None

    read_count = {"n": 0}
    real_loader = cpi._load_cards_json

    def counting_loader():
        read_count["n"] += 1
        return real_loader()

    monkeypatch.setattr(cpi, "_load_cards_json", counting_loader)
    cpi.render_class_pool_section("Silent")
    cpi.render_class_pool_section("Silent")
    cpi.class_pool_card_names("Silent")
    assert read_count["n"] == 1
