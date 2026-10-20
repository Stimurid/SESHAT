"""Portable F09A durable artifact-write regression checks."""
from __future__ import annotations

from seshat.batch import _atomic_write_artifacts, _atomic_write_file


def test_single_file_atomic_write_fsync_supports_windows(tmp_path):
    root = tmp_path / "private-output"
    root.mkdir()
    dest = root / "manifest.json"
    data = b'{"kind":"synthetic"}'
    _atomic_write_file(dest, data)
    assert dest.read_bytes() == data
    assert not (root / ".staging-manifest.json").exists()


def test_multi_artifact_write_fsync_supports_windows(tmp_path):
    root = tmp_path / "private-output"
    root.mkdir()
    item = root / "item-1"
    files = {
        "report.json": b'{"status":"unreviewed"}',
        "report.html": b"<html>fixture</html>",
        "receipt.json": b'{"digest":"test"}',
        "report.md": b"# Fixture",
    }
    _atomic_write_artifacts(item, files, trusted_root=root)
    for name, content in files.items():
        assert (item / name).read_bytes() == content
    assert not (root / ".staging-item-1").exists()
