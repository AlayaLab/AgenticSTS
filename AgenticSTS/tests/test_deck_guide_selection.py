"""Tests for _select_deck_keys_for_refresh helper in guide_consolidator."""

from src.memory.guide_consolidator import _select_deck_keys_for_refresh
from src.memory.models_v2 import CardBuildMemory


def _make_build(
    *,
    run_id: str = "run-a",
    character: str = "The Silent",
    primary_plan: str = "shiv",
    build_tags: tuple[str, ...] = ("shiv",),
    archetype: str = "",
) -> CardBuildMemory:
    return CardBuildMemory(
        run_id=run_id,
        character=character,
        primary_plan=primary_plan,
        build_tags=build_tags,
        archetype=archetype,
    )


def test_selects_only_current_run_keys():
    builds = [
        _make_build(run_id="run-a", character="The Silent", primary_plan="shiv", build_tags=("shiv",)),
        _make_build(run_id="run-b", character="The Silent", primary_plan="poison", build_tags=("poison",)),
        _make_build(run_id="run-b", character="The Ironclad", primary_plan="strength", build_tags=("strength",)),
    ]

    keys = _select_deck_keys_for_refresh(builds, "run-a")

    assert keys == {("the silent", "shiv")}


def test_ignores_unregistered_or_deprecated_tags():
    builds = [
        _make_build(run_id="run-a", character="The Silent", primary_plan="thin deck", build_tags=("thin_deck",)),
        _make_build(run_id="run-a", character="The Silent", primary_plan="general", build_tags=("defeat",)),
        _make_build(run_id="run-a", character="The Ironclad", primary_plan="strength", build_tags=("strength",)),
    ]

    keys = _select_deck_keys_for_refresh(builds, "run-a")

    assert keys == {("the ironclad", "strength")}


def test_uses_legacy_archetype_when_build_tags_missing():
    builds = [
        _make_build(
            run_id="run-a",
            character="The Silent",
            primary_plan="",
            build_tags=(),
            archetype="poison",
        ),
    ]

    keys = _select_deck_keys_for_refresh(builds, "run-a")

    assert keys == {("the silent", "poison")}


def test_multiple_builds_same_bucket_dedupe_to_single_key():
    builds = [
        _make_build(run_id="run-a", character="The Silent", primary_plan="shiv", build_tags=("shiv", "defeat")),
        _make_build(run_id="run-a", character="The Silent", primary_plan="shiv burst", build_tags=("shiv", "victory")),
    ]

    keys = _select_deck_keys_for_refresh(builds, "run-a")

    assert keys == {("the silent", "shiv")}
