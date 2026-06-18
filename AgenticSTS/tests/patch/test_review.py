from pathlib import Path

from src.patch.review import generate_unified_diff, apply_rewrites
from src.patch.rewrite import FileChangeRequest, RewriteResult


def test_unified_diff_shows_changes():
    original = "line one\nline two\nline three\n"
    new = "line one\nline TWO\nline three\n"
    diff = generate_unified_diff(path="shop.py", old=original, new=new)
    assert "---" in diff
    assert "+++" in diff
    assert "-line two" in diff
    assert "+line TWO" in diff


def test_apply_rewrites_writes_new_content(tmp_path: Path):
    p = tmp_path / "shop.py"
    p.write_text("original\n")
    req = FileChangeRequest(path=p, matched_targets={"x"}, original_content="original\n")
    res = RewriteResult(request=req, new_content="rewritten\n", changed=True)

    applied = apply_rewrites([res], dry_run=False)
    assert applied == 1
    assert p.read_text() == "rewritten\n"


def test_apply_rewrites_dry_run_skips(tmp_path: Path):
    p = tmp_path / "shop.py"
    p.write_text("original\n")
    req = FileChangeRequest(path=p, matched_targets={"x"}, original_content="original\n")
    res = RewriteResult(request=req, new_content="rewritten\n", changed=True)
    applied = apply_rewrites([res], dry_run=True)
    assert applied == 0
    assert p.read_text() == "original\n"


def test_apply_rewrites_skips_unchanged(tmp_path: Path):
    p = tmp_path / "shop.py"
    p.write_text("same\n")
    req = FileChangeRequest(path=p, matched_targets={"x"}, original_content="same\n")
    res = RewriteResult(request=req, new_content="same\n", changed=False)
    applied = apply_rewrites([res], dry_run=False)
    assert applied == 0
