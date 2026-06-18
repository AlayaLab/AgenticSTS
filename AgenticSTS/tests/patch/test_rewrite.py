from pathlib import Path

from src.patch.rewrite import scan_prompt_files, FileChangeRequest, rewrite_file


class FakeBackend:
    def __init__(self, response: str):
        self.response = response
        self.last_prompt = None

    def complete(self, *, system: str, user: str) -> str:
        self.last_prompt = (system, user)
        return self.response


def test_scan_prompt_files_finds_references(tmp_path: Path):
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "shop.py").write_text('GUIDE = "Fairy in a Bottle saves you from death"')
    (root / "rest.py").write_text('GUIDE = "Sleep restores HP"')
    (root / "system.py").write_text('GUIDE = "Gloom ascension reduces rest sites"')

    requests = scan_prompt_files(root, targets={"fairy in a bottle", "ascension_6"})
    files = {r.path.name for r in requests}
    assert "shop.py" in files


def test_scan_prompt_files_ignores_unaffected(tmp_path: Path):
    root = tmp_path / "prompts"
    root.mkdir()
    (root / "event.py").write_text('GUIDE = "Event choices should favor scaling"')
    requests = scan_prompt_files(root, targets={"doormaker", "blade of ink"})
    assert requests == []


def test_rewrite_file_calls_backend_and_returns_new_content(tmp_path: Path):
    src_file = tmp_path / "shop.py"
    src_file.write_text('TEXT = "Fairy in a Bottle saves you from death"')

    new_content = 'TEXT = "Fairy in a Bottle saves you only at HP=0"'
    backend = FakeBackend(response=new_content)

    request = FileChangeRequest(
        path=src_file,
        matched_targets={"fairy in a bottle"},
        original_content=src_file.read_text(),
    )

    manifest_context = "Fairy in a Bottle: Only triggers at HP=0, not any death cause"

    result = rewrite_file(request, manifest_context=manifest_context, backend=backend)

    assert result.new_content == new_content
    assert result.changed
    assert "fairy in a bottle" in result.request.matched_targets
    assert "Fairy in a Bottle" in backend.last_prompt[1]


def test_rewrite_file_no_change_when_response_identical(tmp_path: Path):
    src_file = tmp_path / "noop.py"
    content = 'TEXT = "No change needed"'
    src_file.write_text(content)
    backend = FakeBackend(response=content)
    request = FileChangeRequest(path=src_file, matched_targets={"x"}, original_content=content)
    result = rewrite_file(request, manifest_context="irrelevant", backend=backend)
    assert not result.changed
