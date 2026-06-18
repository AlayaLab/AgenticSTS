from __future__ import annotations

import json
from pathlib import Path

from scripts.cleanup_aborted_memories import (
    cleanup_memory_records,
    find_legacy_incomplete_runs,
    main,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


def test_cleanup_script_finds_and_removes_legacy_incomplete_runs(tmp_path) -> None:
    logs_dir = tmp_path / "logs"
    memory_dir = tmp_path / "memory"
    logs_dir.mkdir()
    memory_dir.mkdir()

    _write_jsonl(
        logs_dir / "run_aborted.jsonl",
        [
            {"event": "run_start", "run_id": "run-abort"},
            {"event": "state", "run_id": "run-abort", "state_type": "monster"},
            {"event": "error", "run_id": "run-abort", "error": "Fatal error: aborting to prevent random play"},
            {"event": "run_end", "run_id": "run-abort", "victory": False},
        ],
    )
    _write_jsonl(
        logs_dir / "run_natural.jsonl",
        [
            {"event": "run_start", "run_id": "run-natural"},
            {"event": "state", "run_id": "run-natural", "state_type": "game_over"},
            {"event": "run_end", "run_id": "run-natural", "victory": False},
        ],
    )
    _write_jsonl(
        memory_dir / "combat_episodes.jsonl",
        [
            {"run_id": "run-abort", "kind": "combat"},
            {"run_id": "run-natural", "kind": "combat"},
        ],
    )
    _write_jsonl(
        memory_dir / "route_memories.jsonl",
        [
            {"run_id": "run-abort", "kind": "route"},
            {"run_id": "run-natural", "kind": "route"},
        ],
    )
    _write_jsonl(
        memory_dir / "card_builds.jsonl",
        [
            {"run_id": "run-abort", "kind": "build"},
            {"run_id": "run-natural", "kind": "build"},
        ],
    )

    candidates = find_legacy_incomplete_runs(logs_dir)

    assert [candidate.run_id for candidate in candidates] == ["run-abort"]

    total_counts, per_run_counts = cleanup_memory_records(
        {"run-abort"},
        memory_dir,
        apply=False,
    )
    assert total_counts == {
        "combat_episodes.jsonl": 1,
        "route_memories.jsonl": 1,
        "card_builds.jsonl": 1,
    }
    assert per_run_counts["run-abort"]["combat_episodes.jsonl"] == 1

    cleanup_memory_records({"run-abort"}, memory_dir, apply=True)

    remaining_combat = [
        json.loads(line)
        for line in (memory_dir / "combat_episodes.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert remaining_combat == [{"run_id": "run-natural", "kind": "combat"}]


def test_cleanup_script_hides_already_clean_candidates_by_default(tmp_path, capsys) -> None:
    logs_dir = tmp_path / "logs"
    memory_dir = tmp_path / "memory"
    logs_dir.mkdir()
    memory_dir.mkdir()

    _write_jsonl(
        logs_dir / "run_aborted.jsonl",
        [
            {"event": "run_start", "run_id": "run-abort"},
            {"event": "error", "run_id": "run-abort", "error": "fatal aborting to prevent random play"},
            {"event": "run_end", "run_id": "run-abort", "victory": False},
        ],
    )
    _write_jsonl(memory_dir / "combat_episodes.jsonl", [{"run_id": "run-natural"}])
    _write_jsonl(memory_dir / "route_memories.jsonl", [{"run_id": "run-natural"}])
    _write_jsonl(memory_dir / "card_builds.jsonl", [{"run_id": "run-natural"}])

    exit_code = main(
        [
            "--logs-dir",
            str(logs_dir),
            "--memory-dir",
            str(memory_dir),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "no deletable legacy incomplete records found" in output
    assert "already clean" in output
