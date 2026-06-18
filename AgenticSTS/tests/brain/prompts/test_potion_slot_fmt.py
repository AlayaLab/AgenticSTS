from types import SimpleNamespace

from src.brain.prompts._potion_slot_fmt import format_potion_slot_decision


def _potion(index: int, name: str, desc: str, occupied: bool = True):
    return SimpleNamespace(index=index, name=name, description=desc, occupied=occupied)


def _gs(potions, open_slots, total_slots=3):
    return SimpleNamespace(
        potions=potions, open_potion_slots=open_slots, potion_slots=total_slots,
    )


def test_empty_when_not_full():
    gs = _gs([_potion(0, "Fire Potion", "Deal 10 damage.")], open_slots=2)
    lines = format_potion_slot_decision(gs, candidate_potions=[("Ghost Potion", "Intangible.")])
    assert lines == []


def test_empty_when_no_candidates():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _gs(held, open_slots=0)
    lines = format_potion_slot_decision(gs, candidate_potions=[])
    assert lines == []


def test_subsection_renders_held_and_candidate():
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage."),
        _potion(1, "Block Potion", "Gain 12 block."),
        _potion(2, "Ancient Potion", "Start each turn with +1 energy."),
    ]
    gs = _gs(held, open_slots=0)
    lines = format_potion_slot_decision(
        gs,
        candidate_potions=[("Ghost Potion", "Intangible for 1 turn.")],
    )
    text = "\n".join(lines)
    assert "## Potion Slot Decision (slots FULL)" in text
    assert "[0] Fire Potion" in text
    assert "Deal 10 damage." in text
    assert "[1] Block Potion" in text
    assert "[2] Ancient Potion" in text
    # Sustained keyword detection → timing tag
    assert "[SUSTAINED]" in text or "[INSTANT]" in text
    assert "Ghost Potion" in text
    assert "Intangible for 1 turn." in text
    assert "discard one of [0/1/2]" in text


def test_subsection_skips_empty_held_slots():
    # Only occupied slots should be listed even if gs.potions includes empty placeholders.
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage.", occupied=True),
        _potion(1, "", "", occupied=False),
        _potion(2, "Block Potion", "Gain 12 block.", occupied=True),
    ]
    gs = _gs(held, open_slots=0)
    lines = format_potion_slot_decision(gs, candidate_potions=[("Ghost Potion", "Intangible.")])
    text = "\n".join(lines)
    assert "[0] Fire Potion" in text
    assert "[1] " not in text or "[1] Block" not in text  # index 1 placeholder skipped
    assert "[2] Block Potion" in text
    assert "discard one of [0/2]" in text


def test_subsection_handles_multiple_candidates():
    held = [_potion(0, "Fire Potion", "Deal 10 damage.")]
    gs = _gs(held, open_slots=0, total_slots=1)
    lines = format_potion_slot_decision(
        gs,
        candidate_potions=[
            ("Ghost Potion", "Intangible for 1 turn."),
            ("Regen Potion", "Regen 5 for 5 turns."),
        ],
    )
    text = "\n".join(lines)
    assert "Ghost Potion" in text
    assert "Regen Potion" in text
    assert "Candidate" in text
