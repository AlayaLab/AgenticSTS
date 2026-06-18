import json
from pathlib import Path

from src.patch.purge import purge_card_memories


def test_purge_card_memories_removes_changed_keys(tmp_path: Path):
    f = tmp_path / "card_memories.json"
    f.write_text(json.dumps({
        "the silent::strike": {"card_name": "Strike", "play_count": 300},
        "the silent::blade of ink": {"card_name": "Blade of Ink", "play_count": 45},
        "the ironclad::grapple": {"card_name": "Grapple", "play_count": 20},
        "the ironclad::bash": {"card_name": "Bash", "play_count": 150},
    }))
    changed = {"blade of ink", "grapple"}

    report = purge_card_memories(f, changed, dry_run=False)

    data = json.loads(f.read_text())
    assert "the silent::strike" in data
    assert "the ironclad::bash" in data
    assert "the silent::blade of ink" not in data
    assert "the ironclad::grapple" not in data
    assert report.deleted == 2
    assert report.kept == 2


def test_purge_card_memories_dry_run_does_not_write(tmp_path: Path):
    f = tmp_path / "card_memories.json"
    initial = {
        "the silent::blade of ink": {"card_name": "Blade of Ink", "play_count": 45},
    }
    f.write_text(json.dumps(initial))
    changed = {"blade of ink"}

    report = purge_card_memories(f, changed, dry_run=True)

    # file unchanged
    assert json.loads(f.read_text()) == initial
    assert report.deleted == 1


def test_purge_combat_episodes_by_enemy_major(tmp_path: Path):
    from src.patch.purge import purge_jsonl_episodes

    f = tmp_path / "combat_episodes.jsonl"
    f.write_text("\n".join([
        '{"_meta": {"game_version": "v0.5.3"}}',
        json.dumps({"enemy_key": "Doormaker", "cards_played": ["Strike", "Defend"]}),
        json.dumps({"enemy_key": "Cultist", "cards_played": ["Strike"]}),
    ]) + "\n")
    changed_major_enemies = {"doormaker"}
    changed_cards = set()

    report = purge_jsonl_episodes(f, changed_major_enemies=changed_major_enemies,
                                   changed_cards=changed_cards, dry_run=False)

    kept_lines = [ln for ln in f.read_text().splitlines() if ln and not ln.startswith('{"_meta"')]
    assert len(kept_lines) == 1
    assert json.loads(kept_lines[0])["enemy_key"] == "Cultist"
    assert report.deleted == 1
    assert report.kept == 1


def test_purge_combat_episodes_by_card_reference(tmp_path: Path):
    from src.patch.purge import purge_jsonl_episodes

    f = tmp_path / "combat_episodes.jsonl"
    f.write_text("\n".join([
        json.dumps({"enemy_key": "Cultist", "cards_played": ["Strike", "Blade of Ink", "Defend"]}),
        json.dumps({"enemy_key": "Cultist", "cards_played": ["Strike", "Defend"]}),
    ]) + "\n")

    report = purge_jsonl_episodes(f, changed_major_enemies=set(),
                                   changed_cards={"blade of ink"}, dry_run=False)

    kept = [json.loads(ln) for ln in f.read_text().splitlines() if ln]
    assert len(kept) == 1
    assert "Blade of Ink" not in kept[0]["cards_played"]
    assert report.deleted == 1


def test_purge_preserves_meta_header(tmp_path: Path):
    from src.patch.purge import purge_jsonl_episodes

    f = tmp_path / "combat_episodes.jsonl"
    f.write_text("\n".join([
        '{"_meta": {"game_version": "v0.5.3"}}',
        json.dumps({"enemy_key": "Doormaker", "cards_played": []}),
    ]) + "\n")
    purge_jsonl_episodes(f, changed_major_enemies={"doormaker"},
                          changed_cards=set(), dry_run=False)
    lines = f.read_text().splitlines()
    assert lines[0].startswith('{"_meta"')


def test_purge_card_builds_by_deck_reference(tmp_path: Path):
    from src.patch.purge import purge_jsonl_card_builds

    f = tmp_path / "card_builds.jsonl"
    f.write_text("\n".join([
        json.dumps({"starting_deck": ["Strike", "Defend"], "final_deck": ["Strike", "Blade of Ink"], "card_play_counts": [["Strike", 10]]}),
        json.dumps({"starting_deck": ["Strike"], "final_deck": ["Strike", "Bash"], "card_play_counts": [["Strike", 5]]}),
    ]) + "\n")
    report = purge_jsonl_card_builds(f, changed={"blade of ink"}, dry_run=False)
    kept = [json.loads(ln) for ln in f.read_text().splitlines() if ln]
    assert len(kept) == 1
    assert "Blade of Ink" not in kept[0]["final_deck"]
    assert report.deleted == 1


def test_purge_card_builds_by_play_counts(tmp_path: Path):
    from src.patch.purge import purge_jsonl_card_builds

    f = tmp_path / "card_builds.jsonl"
    f.write_text(json.dumps({
        "starting_deck": ["Strike"], "final_deck": ["Strike"],
        "card_play_counts": [["Grapple", 10], ["Strike", 5]]
    }) + "\n")
    report = purge_jsonl_card_builds(f, changed={"grapple"}, dry_run=False)
    assert report.deleted == 1


def test_purge_event_memories_by_cards_gained(tmp_path: Path):
    from src.patch.purge import purge_jsonl_event_memories

    f = tmp_path / "event_memories.jsonl"
    f.write_text("\n".join([
        json.dumps({"event_id": "E1", "cards_gained": ["Hidden Gem"]}),
        json.dumps({"event_id": "E2", "cards_gained": ["Spoils Map"]}),
    ]) + "\n")
    report = purge_jsonl_event_memories(f, changed={"hidden gem"}, dry_run=False)
    kept = [json.loads(ln) for ln in f.read_text().splitlines() if ln]
    assert len(kept) == 1
    assert kept[0]["event_id"] == "E2"


def test_purge_skills_by_requires_cards(tmp_path: Path):
    from src.patch.purge import purge_skills

    f = tmp_path / "skills.json"
    f.write_text(json.dumps({
        "version": 1,
        "skills": [
            {"id": "s1", "trigger": {"requires_cards": ["Apparition"]}},
            {"id": "s2", "trigger": {"requires_cards": ["Strike"]}},
            {"id": "s3", "trigger": {}},
        ]
    }))
    report = purge_skills(f, changed={"apparition"}, dry_run=False)
    data = json.loads(f.read_text())
    kept_ids = [s["id"] for s in data["skills"]]
    assert "s1" not in kept_ids
    assert "s2" in kept_ids
    assert "s3" in kept_ids
    assert report.deleted == 1


def test_purge_silent_card_notes(tmp_path: Path):
    from src.patch.purge import purge_silent_card_notes

    f = tmp_path / "silent_card_notes.json"
    f.write_text(json.dumps([
        {"character": "the silent", "card_name": "Abrasive", "note": "..."},
        {"character": "the silent", "card_name": "Blade of Ink", "note": "..."},
    ]))
    report = purge_silent_card_notes(f, changed={"blade of ink"}, dry_run=False)
    data = json.loads(f.read_text())
    names = [e["card_name"] for e in data]
    assert "Abrasive" in names
    assert "Blade of Ink" not in names
    assert report.deleted == 1


def test_purge_evolution_tools_by_text_reference(tmp_path: Path):
    from src.patch.purge import purge_evolution_dir

    evo = tmp_path / "evolution"
    tools = evo / "tools"
    tools.mkdir(parents=True)
    (tools / "score_tool_a.py").write_text("def score(card): return 1 if card == 'Blade of Ink' else 0")
    (tools / "score_tool_b.py").write_text("def score(card): return 1 if card == 'Strike' else 0")

    proposals = evo / "proposals"
    proposals.mkdir()
    (proposals / "p1.json").write_text(json.dumps({"code_edits": [], "prompt_effect": "adjust Doormaker behavior"}))
    (proposals / "p2.json").write_text(json.dumps({"code_edits": [], "prompt_effect": "generic prompt"}))

    report = purge_evolution_dir(evo, changed={"blade of ink", "doormaker"}, dry_run=False)

    assert not (tools / "score_tool_a.py").exists()
    assert (tools / "score_tool_b.py").exists()
    assert not (proposals / "p1.json").exists()
    assert (proposals / "p2.json").exists()
    assert report.deleted == 2


def test_purge_guides_by_enemy_key(tmp_path: Path):
    """Combat guides keyed by enemy — purge only when enemy_key is changed."""
    from src.patch.purge import purge_guides

    f = tmp_path / "guides.json"
    f.write_text(json.dumps({
        "version": 1,
        "combat_guides": {
            "doormaker:ironclad": {"enemy_key": "Doormaker", "guide_text": "fight X"},
            "nibbit:ironclad": {"enemy_key": "Nibbit", "guide_text": "fight Y"},
        }
    }))
    report = purge_guides(f, changed={"doormaker"}, dry_run=False)
    data = json.loads(f.read_text())
    assert "doormaker:ironclad" not in data["combat_guides"]
    assert "nibbit:ironclad" in data["combat_guides"]
    assert report.deleted == 1
    assert report.kept == 1


def test_purge_guides_by_text_reference(tmp_path: Path):
    """Guide text that mentions a changed entity → purge."""
    from src.patch.purge import purge_guides

    f = tmp_path / "guides.json"
    f.write_text(json.dumps({
        "deck_guides": {
            "silent:shiv": {
                "character": "the silent", "archetype": "shiv",
                "guide_text": "Lean on Blade of Ink for buffs",
                "key_cards": ["Blade of Ink", "Dagger Throw"],
            },
            "silent:poison": {
                "character": "the silent", "archetype": "poison",
                "guide_text": "Stack Deadly Poison early",
                "key_cards": ["Deadly Poison"],
            },
        }
    }))
    report = purge_guides(f, changed={"blade of ink"}, dry_run=False)
    data = json.loads(f.read_text())
    assert "silent:shiv" not in data["deck_guides"]
    assert "silent:poison" in data["deck_guides"]
    assert report.deleted == 1


def test_purge_guides_keeps_everything_when_no_overlap(tmp_path: Path):
    """No changed entities touched → file unchanged, report.deleted == 0."""
    from src.patch.purge import purge_guides

    f = tmp_path / "guides.json"
    original = json.dumps({
        "combat_guides": {"nibbit:ironclad": {"enemy_key": "Nibbit", "guide_text": "fight"}}
    })
    f.write_text(original)
    report = purge_guides(f, changed={"doormaker"}, dry_run=False)
    assert f.read_text() == original
    assert report.deleted == 0
    assert report.kept == 1


def test_purge_guides_dry_run(tmp_path: Path):
    from src.patch.purge import purge_guides

    f = tmp_path / "guides.json"
    original = json.dumps({
        "combat_guides": {"doormaker:ironclad": {"enemy_key": "Doormaker"}}
    })
    f.write_text(original)
    report = purge_guides(f, changed={"doormaker"}, dry_run=True)
    assert f.read_text() == original  # file unchanged
    assert report.deleted == 1  # report still counts


def test_purge_guides_handles_list_format(tmp_path: Path):
    """Legacy list-format guide sections should also work."""
    from src.patch.purge import purge_guides

    f = tmp_path / "guides.json"
    f.write_text(json.dumps({
        "combat_guides": [
            {"enemy_key": "Doormaker", "guide_text": "x"},
            {"enemy_key": "Nibbit", "guide_text": "y"},
        ]
    }))
    report = purge_guides(f, changed={"doormaker"}, dry_run=False)
    data = json.loads(f.read_text())
    kept = [g for g in data["combat_guides"]]
    assert len(kept) == 1
    assert kept[0]["enemy_key"] == "Nibbit"
    assert report.deleted == 1
