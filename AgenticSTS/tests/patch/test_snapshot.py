from pathlib import Path

from src.patch.snapshot import snapshot_data


def test_snapshot_sanitizes_malicious_label(tmp_path: Path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "a.txt").write_text("x")
    snap_root = tmp_path / "snapshots"

    # Attempt path traversal: label with ../ and / should not escape snap_root
    dst = snapshot_data(src, snap_root, label="../../../evil")
    # Resolved path must still be inside snap_root
    assert str(dst.resolve()).startswith(str(snap_root.resolve()))
    assert dst.exists()
    # Label got sanitized (no ".." remain in segment name)
    assert ".." not in dst.name


def test_snapshot_copies_tree(tmp_path: Path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "a.txt").write_text("hello")
    (src / "sub").mkdir()
    (src / "sub" / "b.txt").write_text("world")

    snap_root = tmp_path / "snapshots"
    dst = snapshot_data(src, snap_root, label="pre-v0.103.1")

    assert dst.exists()
    assert "pre-v0.103.1" in dst.name
    assert (dst / "a.txt").read_text() == "hello"
    assert (dst / "sub" / "b.txt").read_text() == "world"


def test_snapshot_refuses_overwrite(tmp_path: Path):
    src = tmp_path / "data"
    src.mkdir()
    (src / "x.txt").write_text("x")
    snap_root = tmp_path / "snapshots"

    first = snapshot_data(src, snap_root, label="tag1")
    # second call with same label gets suffixed path, no error
    second = snapshot_data(src, snap_root, label="tag1")
    assert first != second
    assert second.exists()
