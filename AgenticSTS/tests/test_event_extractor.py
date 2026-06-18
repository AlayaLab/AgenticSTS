"""Tests for event memory extraction."""
from src.memory.short_term import ShortTermMemory


def test_extract_event_memories():
    """Extracts EventMemory from completed events in ShortTermMemory."""
    from src.memory.event_extractor import extract_event_memories

    stm = ShortTermMemory()
    stm.start_event("OROBAS", "Orobas", 18, 2, 57, 110, ["Strike", "Defend"])
    stm.end_event(1, "Alchemical Coffer", 57, 110,
                  ["Gear Glass", "Alchemical Coffer", "Archaic Tooth"],
                  [], [], [], ["Fire Potion"])

    stm.start_event("SHRINE", "Shrine", 10, 1, 60, 50, ["Strike"])
    stm.end_event(0, "Pray", 55, 50, ["Pray", "Leave"], [], [], [], [])

    memories = extract_event_memories(stm, "run_123", "the silent")
    assert len(memories) == 2
    assert memories[0].event_id == "OROBAS"
    assert memories[0].character == "the silent"
    assert memories[0].run_id == "run_123"
    assert memories[0].potions_gained == ("Fire Potion",)
    assert memories[1].event_id == "SHRINE"
    assert memories[1].hp_before == 60
    assert memories[1].hp_after == 55


def test_extract_empty():
    """No events returns empty list."""
    from src.memory.event_extractor import extract_event_memories

    stm = ShortTermMemory()
    memories = extract_event_memories(stm, "run_x", "the silent")
    assert memories == []


def test_extract_preserves_option_details():
    """Option details flow from EventTracker through to EventMemory."""
    from src.memory.event_extractor import extract_event_memories

    stm = ShortTermMemory()
    stm.start_event(
        event_id="SUNKEN_STATUE",
        event_title="The Sunken Statue",
        floor=8, act=1, hp=50, gold=100, deck=["Strike"],
    )
    details = [
        {"index": 0, "title": "Grab the Sword",
         "description": "Obtain the Sword of Stone.",
         "relics_offered": ["Sword of Stone"]},
        {"index": 1, "title": "Dive into the Water",
         "description": "Gain 111 Gold. Lose 7 HP.",
         "hp_cost": 7},
    ]
    stm.end_event(
        chosen_index=0,
        option_text="Grab the Sword",
        hp_after=50,
        gold_after=100,
        all_options=["Grab the Sword", "Dive into the Water"],
        cards_gained=[],
        cards_lost=[],
        relics_gained=["Sword of Stone"],
        potions_gained=[],
        all_option_details=details,
    )
    mems = extract_event_memories(stm, "run_1", "the silent")
    assert len(mems) == 1
    assert len(mems[0].all_option_details) == 2
    assert mems[0].all_option_details[0].title == "Grab the Sword"
    assert mems[0].all_option_details[0].relics_offered[0].name == "Sword of Stone"
    assert mems[0].all_option_details[1].hp_cost == 7
