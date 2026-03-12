#!/usr/bin/env python3
"""Tests for CEFS .bak and .DELETE_ME_* cleanup."""

from __future__ import annotations

import os

from lib.cefs.gc import cleanup_bak_items, delete_bak_item
from lib.cefs.paths import FileWithAge


def test_delete_bak_item_removes_file(tmp_path):
    f = tmp_path / "compiler.bak"
    f.write_text("content")
    assert f.exists()

    error = delete_bak_item(f)

    assert error is None
    assert not f.exists()


def test_delete_bak_item_removes_symlink(tmp_path):
    target = tmp_path / "target_dir"
    target.mkdir()
    link = tmp_path / "compiler.bak"
    link.symlink_to(target)

    error = delete_bak_item(link)

    assert error is None
    assert not link.exists()
    assert target.exists()


def test_delete_bak_item_removes_directory(tmp_path):
    d = tmp_path / "gcc-14.1.0.bak"
    d.mkdir()
    (d / "bin").mkdir()
    (d / "bin" / "gcc").write_text("binary")

    error = delete_bak_item(d)

    assert error is None
    assert not d.exists()


def test_delete_bak_item_returns_error_for_missing_path(tmp_path):
    missing = tmp_path / "nonexistent.bak"

    error = delete_bak_item(missing)

    assert error is not None
    assert "Unknown file type" in error


def test_cleanup_bak_items_filters_by_age(tmp_path):
    old_file = tmp_path / "old.bak"
    old_file.write_text("old")
    recent_file = tmp_path / "recent.bak"
    recent_file.write_text("recent")

    min_age = 3600  # 1 hour

    items = [
        FileWithAge(old_file, 7200),
        FileWithAge(recent_file, 600),
    ]

    result = cleanup_bak_items(items, min_age, dry_run=False)

    assert result.deleted_count == 1
    assert result.skipped_too_recent == 1
    assert not result.errors
    assert not old_file.exists()
    assert recent_file.exists()


def test_cleanup_bak_items_dry_run(tmp_path):
    f = tmp_path / "compiler.bak"
    f.write_text("content")

    items = [FileWithAge(f, 7200)]

    result = cleanup_bak_items(items, min_age_seconds=3600, dry_run=True)

    assert result.deleted_count == 1
    assert result.skipped_too_recent == 0
    assert not result.errors
    assert f.exists()


def test_cleanup_bak_items_handles_mixed_types(tmp_path):
    bak_dir = tmp_path / "gcc-14.bak"
    bak_dir.mkdir()
    (bak_dir / "file").write_text("data")

    delete_me = tmp_path / "clang-17.DELETE_ME_20240101"
    delete_me.mkdir()
    (delete_me / "bin").mkdir()

    bak_symlink = tmp_path / "rust.bak"
    target = tmp_path / "rust_target"
    target.mkdir()
    bak_symlink.symlink_to(target)

    items = [
        FileWithAge(bak_dir, 7200),
        FileWithAge(delete_me, 7200),
        FileWithAge(bak_symlink, 7200),
    ]

    result = cleanup_bak_items(items, min_age_seconds=3600, dry_run=False)

    assert result.deleted_count == 3
    assert result.skipped_too_recent == 0
    assert not result.errors
    assert not bak_dir.exists()
    assert not delete_me.exists()
    assert not bak_symlink.exists()
    assert target.exists()


def test_cleanup_bak_items_records_errors(tmp_path):
    readonly_dir = tmp_path / "protected.bak"
    readonly_dir.mkdir()
    (readonly_dir / "file").write_text("data")
    os.chmod(readonly_dir, 0o000)

    items = [FileWithAge(readonly_dir, 7200)]

    result = cleanup_bak_items(items, min_age_seconds=3600, dry_run=False)

    # Restore permissions for cleanup
    os.chmod(readonly_dir, 0o755)

    assert result.deleted_count == 0
    assert len(result.errors) == 1
    assert "Failed to delete" in result.errors[0]


def test_cleanup_bak_items_empty_list():
    result = cleanup_bak_items([], min_age_seconds=3600, dry_run=False)

    assert result.deleted_count == 0
    assert result.skipped_too_recent == 0
    assert not result.errors


def test_cleanup_bak_items_all_too_recent(tmp_path):
    f1 = tmp_path / "a.bak"
    f1.write_text("a")
    f2 = tmp_path / "b.DELETE_ME_123"
    f2.write_text("b")

    items = [
        FileWithAge(f1, 300),
        FileWithAge(f2, 600),
    ]

    result = cleanup_bak_items(items, min_age_seconds=3600, dry_run=False)

    assert result.deleted_count == 0
    assert result.skipped_too_recent == 2
    assert f1.exists()
    assert f2.exists()
