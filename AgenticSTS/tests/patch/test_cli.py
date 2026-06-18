import subprocess
import sys
from pathlib import Path


def test_cli_help_runs():
    """Verify --help flag works and produces output."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.apply_patch", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "apply_patch" in result.stdout.lower() or "usage" in result.stdout.lower()


def test_cli_dry_run_flag_parses(tmp_path, minimal_manifest_path):
    """Verify --dry-run flag parses with minimal test data."""
    # Create a test data directory structure with minimal required files
    test_data = tmp_path / "data"
    test_data.mkdir()
    (test_data / "memory" / "v2").mkdir(parents=True)
    (test_data / "memory" / "v2" / "card_memories.json").write_text("{}")
    (test_data / "memory" / "v2" / "card_builds.jsonl").touch()
    (test_data / "memory" / "v2" / "combat_episodes.jsonl").touch()
    (test_data / "memory" / "v2" / "event_memories.jsonl").touch()
    (test_data / "memory" / "v2" / "guides.json").write_text('{"combat_guides": [], "route_guides": [], "deck_guides": []}')
    (test_data / "skills").mkdir(parents=True)
    (test_data / "skills" / "skills.json").write_text('{"skills": []}')
    (test_data / "evolution").mkdir(parents=True)
    (test_data / "version_compatibility.json").write_text('{"current": {"game_version": "v0.103.1"}}')
    (test_data / "run_state.json").write_text("{}")

    result = subprocess.run(
        [sys.executable, "-m", "scripts.apply_patch",
         "--manifest", str(minimal_manifest_path),
         "--data-root", str(test_data),
         "--dry-run", "--skip-llm"],
        capture_output=True, text=True,
        cwd=Path(__file__).parent.parent.parent,  # repo root
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
    assert "apply_patch" in result.stdout.lower() or "dry" in result.stdout.lower()


def test_cli_missing_manifest_fails():
    """Verify missing manifest causes error exit."""
    result = subprocess.run(
        [sys.executable, "-m", "scripts.apply_patch",
         "--manifest", "/nonexistent/path.yaml", "--dry-run"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "not found" in (result.stderr + result.stdout).lower()
