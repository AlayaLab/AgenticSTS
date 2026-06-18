"""Tests for EventMemory frozen dataclass."""


def test_event_memory_roundtrip():
    """EventMemory serializes and deserializes correctly."""
    from src.memory.event_models import EventMemory

    mem = EventMemory(
        run_id="run_abc",
        floor=18,
        act=2,
        event_id="OROBAS",
        event_title="Orobas",
        character="the silent",
        chosen_option_index=1,
        chosen_option_text="Alchemical Coffer",
        all_options=("Gear Glass", "Alchemical Coffer", "Archaic Tooth"),
        hp_before=57,
        hp_after=57,
        gold_before=110,
        gold_after=110,
        cards_gained=(),
        cards_lost=(),
        relics_gained=(),
        potions_gained=("Fire Potion", "Block Potion", "Weak Potion", "Regen Potion"),
        run_victory=False,
        run_final_floor=34,
    )
    d = mem.to_dict()
    restored = EventMemory.from_dict(d)
    assert restored.event_id == "OROBAS"
    assert restored.chosen_option_index == 1
    assert restored.potions_gained == ("Fire Potion", "Block Potion", "Weak Potion", "Regen Potion")
    assert restored.run_id == "run_abc"
    assert restored.run_victory is False
    assert restored.run_final_floor == 34


def test_event_memory_defaults():
    """EventMemory has sane defaults for all fields."""
    from src.memory.event_models import EventMemory

    mem = EventMemory()
    assert mem.event_id == ""
    assert mem.run_victory is False
    assert mem.run_final_floor == 0
    assert mem.cards_gained == ()
    assert mem.memory_id  # auto-generated


def test_event_memory_drops_unknown_keys():
    """Legacy JSONL with the removed boss_impact_* keys still loads cleanly."""
    from src.memory.event_models import EventMemory

    d = {
        "event_id": "OROBAS",
        # Legacy fields that the model no longer defines
        "boss_impact_score": 0.6,
        "boss_impact_analysis": "legacy analysis text",
        "outcome_quality": "good",
    }
    mem = EventMemory.from_dict(d)
    assert mem.event_id == "OROBAS"
    assert not hasattr(mem, "boss_impact_score")
    assert mem.run_final_floor == 0


def test_event_guide_roundtrip():
    """EventGuide serializes and deserializes correctly."""
    from src.memory.event_models import EventGuide

    guide = EventGuide(
        event_id="OROBAS",
        character="the silent",
        guide_text="Prefer Alchemical Coffer when potion slots available.",
        episode_count=5,
        confidence=0.7,
    )
    d = guide.to_dict()
    restored = EventGuide.from_dict(d)
    assert restored.event_id == "OROBAS"
    assert restored.confidence == 0.7
    assert restored.guide_text.startswith("Prefer")


def test_event_option_snapshot_roundtrip():
    """EventOptionSnapshot serializes and deserializes correctly."""
    from src.memory.event_models import (
    EventOptionSnapshot,
    RelicReward,
)

    snap = EventOptionSnapshot(
        index=0,
        title="Grab the Sword",
        description="Obtain the Sword of Stone.",
        relics_offered=(RelicReward(name="Sword of Stone"),),
    )
    d = snap.to_dict()
    restored = EventOptionSnapshot.from_dict(d)
    assert restored.title == "Grab the Sword"
    assert restored.relics_offered[0].name == "Sword of Stone"
    assert restored.hp_cost is None


def test_event_memory_option_details_roundtrip():
    """EventMemory with all_option_details survives serialization."""
    from src.memory.event_models import (
    EventMemory,
    EventOptionSnapshot,
    RelicReward,
)

    opts = (
        EventOptionSnapshot(index=0, title="Grab the Sword",
                            description="Obtain the Sword of Stone.",
                            relics_offered=(RelicReward(name="Sword of Stone"),)),
        EventOptionSnapshot(index=1, title="Dive into the Water",
                            description="Gain 111 Gold. Lose 7 HP.",
                            hp_cost=7),
    )
    mem = EventMemory(
        event_id="SUNKEN_STATUE",
        all_option_details=opts,
    )
    d = mem.to_dict()
    restored = EventMemory.from_dict(d)
    assert len(restored.all_option_details) == 2
    assert restored.all_option_details[0].relics_offered[0].name == "Sword of Stone"
    assert restored.all_option_details[1].hp_cost == 7


def test_event_memory_backwards_compat_no_option_details():
    """Old EventMemory dicts without all_option_details load with empty tuple."""
    from src.memory.event_models import EventMemory

    d = {"event_id": "SUNKEN_STATUE", "all_options": ["A", "B"]}
    mem = EventMemory.from_dict(d)
    assert mem.all_option_details == ()
    assert mem.all_options == ("A", "B")


def test_relic_reward_roundtrip():
    """RelicReward serializes with name/description/rarity."""
    from src.memory.event_models import RelicReward

    r = RelicReward(name="Archaic Tooth", description="Transform a card.", rarity="uncommon")
    d = r.to_dict()
    restored = RelicReward.from_dict(d)
    assert restored.name == "Archaic Tooth"
    assert restored.description == "Transform a card."
    assert restored.rarity == "uncommon"


def test_relic_reward_defaults():
    from src.memory.event_models import RelicReward

    r = RelicReward(name="X")
    assert r.description == ""
    assert r.rarity == ""


def test_card_reward_maps_mod_keys():
    """CardReward.from_dict accepts mod-side keys `type` and `is_upgraded`."""
    from src.memory.event_models import CardReward

    mod_payload = {
        "name": "Suppress+",
        "cost": 1,
        "type": "skill",
        "rules_text": "Apply 2 Weak.",
        "is_upgraded": True,
    }
    c = CardReward.from_dict(mod_payload)
    assert c.name == "Suppress+"
    assert c.cost == 1
    assert c.card_type == "skill"
    assert c.rules_text == "Apply 2 Weak."
    assert c.upgraded is True

    # to_dict emits the Python-side names, not the mod keys
    persisted = c.to_dict()
    assert persisted == {
        "name": "Suppress+",
        "cost": 1,
        "card_type": "skill",
        "rules_text": "Apply 2 Weak.",
        "upgraded": True,
    }

    # Round-trip from persisted form
    restored = CardReward.from_dict(persisted)
    assert restored.card_type == "skill"
    assert restored.upgraded is True


def test_potion_reward_maps_mod_key():
    """PotionReward.from_dict reads mod-side `type` into potion_type."""
    from src.memory.event_models import PotionReward

    mod_payload = {
        "name": "Fire Potion",
        "description": "Deal 20 damage.",
        "type": "damage",
    }
    p = PotionReward.from_dict(mod_payload)
    assert p.name == "Fire Potion"
    assert p.description == "Deal 20 damage."
    assert p.potion_type == "damage"

    persisted = p.to_dict()
    assert persisted["potion_type"] == "damage"
    assert "type" not in persisted


def test_reward_from_dict_tolerates_unknown_keys():
    """All three reward types silently drop unknown keys."""
    from src.memory.event_models import (
    RelicReward,
    CardReward,
    PotionReward,
)

    assert RelicReward.from_dict({"name": "X", "future_field": 1}).name == "X"
    assert CardReward.from_dict({"name": "X", "future_field": 1}).name == "X"
    assert PotionReward.from_dict({"name": "X", "future_field": 1}).name == "X"


def test_event_option_snapshot_accepts_dict_rewards():
    """New payload shape: reward dicts with full detail."""
    from src.memory.event_models import (
    EventOptionSnapshot,
    RelicReward,
    CardReward,
    PotionReward,
)

    opt = EventOptionSnapshot(
        index=0,
        title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        relics_offered=(
            RelicReward(name="Archaic Tooth",
                        description="Transform a starter card.",
                        rarity="uncommon"),
        ),
        cards_offered=(
            CardReward(name="Suppress+", cost=1, card_type="skill",
                       rules_text="Apply 2 Weak.", upgraded=True),
        ),
        potions_offered=(
            PotionReward(name="Fire Potion", description="Deal 20.",
                         potion_type="damage"),
        ),
    )
    d = opt.to_dict()
    restored = EventOptionSnapshot.from_dict(d)
    assert restored.relics_offered[0].rarity == "uncommon"
    assert restored.cards_offered[0].rules_text == "Apply 2 Weak."
    assert restored.cards_offered[0].upgraded is True
    assert restored.potions_offered[0].potion_type == "damage"


def test_event_option_snapshot_legacy_strings_upgrade():
    """Legacy JSONL with string-only reward lists loads cleanly."""
    from src.memory.event_models import EventOptionSnapshot

    legacy = {
        "index": 0,
        "title": "Archaic Tooth",
        "description": "Transform a card.",
        "relics_offered": ["Archaic Tooth"],
        "cards_offered": ["Suppress+"],
        "potions_offered": ["Fire Potion"],
    }
    opt = EventOptionSnapshot.from_dict(legacy)
    assert opt.relics_offered[0].name == "Archaic Tooth"
    assert opt.relics_offered[0].description == ""
    assert opt.cards_offered[0].name == "Suppress+"
    assert opt.cards_offered[0].rules_text == ""
    assert opt.potions_offered[0].name == "Fire Potion"
    assert opt.potions_offered[0].potion_type == ""


def test_event_option_snapshot_mod_payload_keys():
    """Mod-side keys (type, is_upgraded) flow through via reward from_dict."""
    from src.memory.event_models import EventOptionSnapshot

    mod_style = {
        "index": 1,
        "title": "Demon Glass",
        "description": "See 15 cards from Ironclad.",
        "cards_offered": [
            {"name": "Bash", "cost": 2, "type": "attack",
             "rules_text": "Deal 8. Vuln 2.", "is_upgraded": False},
        ],
    }
    opt = EventOptionSnapshot.from_dict(mod_style)
    assert opt.cards_offered[0].card_type == "attack"
    assert opt.cards_offered[0].upgraded is False


def test_event_guide_option_roundtrip():
    from src.memory.event_models import EventGuideOption

    opt = EventGuideOption(
        canonical_name="Archaic Tooth",
        stage_index=0,
        variant_type="fixed",
        score=0.7,
        analysis="Free upgrade to starter card.",
        observed_rewards=("Suppress+",),
        sample_size=14,
    )
    d = opt.to_dict()
    restored = EventGuideOption.from_dict(d)
    assert restored.canonical_name == "Archaic Tooth"
    assert restored.variant_type == "fixed"
    assert restored.score == 0.7
    assert restored.sample_size == 14


def test_event_guide_option_defaults():
    from src.memory.event_models import EventGuideOption

    opt = EventGuideOption(canonical_name="X")
    assert opt.stage_index == 0
    assert opt.variant_type == "fixed"
    assert opt.score == 0.0
    assert opt.sample_size == 0
    assert opt.observed_rewards == ()


def test_event_guide_with_options_roundtrip():
    from src.memory.event_models import (
    EventGuide,
    EventGuideOption,
)

    guide = EventGuide(
        event_id="OROBAS",
        character="the silent",
        guide_text="Free power spike.",
        options=(
            EventGuideOption(canonical_name="Archaic Tooth", stage_index=0,
                             score=0.7, analysis="Free upgrade.", sample_size=14),
            EventGuideOption(canonical_name="Demon Glass", stage_index=0,
                             variant_type="random_from_pool", score=0.3,
                             analysis="Deck injection.",
                             observed_rewards=("Bash", "Iron Wave"),
                             sample_size=3),
        ),
        episode_count=20,
        confidence=0.8,
    )
    d = guide.to_dict()
    restored = EventGuide.from_dict(d)
    assert len(restored.options) == 2
    assert restored.options[0].canonical_name == "Archaic Tooth"
    assert restored.options[1].observed_rewards == ("Bash", "Iron Wave")


def test_event_guide_legacy_without_options():
    """Legacy EventGuide JSONL (no `options` key) still loads; options=()."""
    from src.memory.event_models import EventGuide

    legacy = {
        "event_id": "OROBAS",
        "character": "the silent",
        "guide_text": "Legacy freeform text.",
        "episode_count": 5,
        "confidence": 0.7,
        "version": 2,
    }
    guide = EventGuide.from_dict(legacy)
    assert guide.event_id == "OROBAS"
    assert guide.options == ()
    assert guide.version == 2


def test_finalize_event_stage_preserves_mod_reward_detail():
    """Verify the extractor captures full mod payload (name + description +
    rarity / rules_text / type). This test simulates the mod's EventOption
    payload shape directly."""
    from dataclasses import dataclass

    @dataclass
    class _FakeOption:
        index: int
        title: str
        description: str
        effect_description: str
        hp_cost: int | None
        gold_cost: int | None
        is_proceed: bool
        relics_offered: list
        cards_offered: list
        potions_offered: list

    opt = _FakeOption(
        index=2,
        title="Archaic Tooth",
        description="Transform [gold]Neutralize+[/gold] into [gold]Suppress+[/gold].",
        effect_description="Transform Neutralize+ into Suppress+.",
        hp_cost=None, gold_cost=None, is_proceed=False,
        relics_offered=[{
            "name": "Archaic Tooth",
            "description": "Transform a [gold]starter[/gold] card.",
            "rarity": "uncommon",
        }],
        cards_offered=[{
            "name": "Suppress+", "cost": 1, "type": "skill",
            "rules_text": "Apply [red]2 Weak[/red].", "is_upgraded": True,
        }],
        potions_offered=[],
    )

    from src.agent.loop import _build_event_option_detail

    detail = _build_event_option_detail(opt)
    # BBCode stripped
    assert "[gold]" not in detail["description"]
    assert "[gold]" not in detail["relics_offered"][0]["description"]
    assert "[red]" not in detail["cards_offered"][0]["rules_text"]
    # Mod keys preserved (EventOptionSnapshot.from_dict handles the rename)
    assert detail["relics_offered"][0]["rarity"] == "uncommon"
    assert detail["cards_offered"][0]["rules_text"] == "Apply 2 Weak."
    assert detail["cards_offered"][0]["is_upgraded"] is True

    # Round-trip through EventOptionSnapshot
    from src.memory.event_models import EventOptionSnapshot
    snap = EventOptionSnapshot.from_dict(detail)
    assert snap.relics_offered[0].description == "Transform a starter card."
    assert snap.relics_offered[0].rarity == "uncommon"
    assert snap.cards_offered[0].upgraded is True
    assert snap.cards_offered[0].card_type == "skill"
    assert snap.cards_offered[0].rules_text == "Apply 2 Weak."


def test_build_event_option_detail_prefers_effect_description():
    """When effect_description is present, it overrides the raw description."""
    from dataclasses import dataclass
    from src.agent.loop import _build_event_option_detail

    @dataclass
    class _O:
        index: int = 0
        title: str = "X"
        description: str = "raw desc"
        effect_description: str = "effect desc"
        hp_cost: int | None = None
        gold_cost: int | None = None
        is_proceed: bool = False
        relics_offered: list = None
        cards_offered: list = None
        potions_offered: list = None

    o = _O(relics_offered=[], cards_offered=[], potions_offered=[])
    detail = _build_event_option_detail(o)
    assert detail["description"] == "effect desc"
