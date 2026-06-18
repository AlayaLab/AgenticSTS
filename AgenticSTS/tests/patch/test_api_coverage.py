from src.patch.api_coverage import flatten_keys, compare


def test_flatten_nested_dict():
    raw = {"run": {"floor": 1, "player": {"hp": 70}}, "combat": None}
    keys = flatten_keys(raw)
    assert "run.floor" in keys
    assert "run.player.hp" in keys
    assert "combat" in keys


def test_flatten_handles_list_of_dicts():
    raw = {"enemies": [{"name": "X", "hp": 10}, {"name": "Y"}]}
    keys = flatten_keys(raw)
    assert "enemies[].name" in keys
    assert "enemies[].hp" in keys


def test_compare_reports_missing_and_unused():
    raw_keys = {"a.b", "a.c", "new_field"}
    modeled = {"a.b", "a.c", "old_field"}
    report = compare(raw_keys, modeled)
    assert "new_field" in report.missing_from_model
    assert "old_field" in report.unused_in_response
