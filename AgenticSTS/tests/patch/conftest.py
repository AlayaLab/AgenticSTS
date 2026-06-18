from pathlib import Path
import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def minimal_manifest_path() -> Path:
    return FIXTURE_DIR / "minimal_manifest.yaml"
