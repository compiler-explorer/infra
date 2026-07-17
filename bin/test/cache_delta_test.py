"""Tests for cache_delta module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from lib.cache_delta import CacheDeltaCapture, copy_and_capture_delta


class TestCacheDeltaCapture:
    """Tests for CacheDeltaCapture class."""

    def test_init(self, tmp_path: Path):
        """Test initialization."""
        capture = CacheDeltaCapture(tmp_path)
        assert capture.cache_dir == tmp_path
        assert not capture.has_baseline
        assert capture.baseline_count == 0

    def test_capture_baseline_empty_dir(self, tmp_path: Path):
        """Test baseline capture on empty directory."""
        capture = CacheDeltaCapture(tmp_path)
        count = capture.capture_baseline()

        assert count == 0
        assert capture.has_baseline
        assert capture.baseline_count == 0

    def test_capture_baseline_with_files(self, tmp_path: Path):
        """Test baseline capture with existing files."""
        # Create some files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file2.txt").write_text("content2")

        capture = CacheDeltaCapture(tmp_path)
        count = capture.capture_baseline()

        assert count == 2
        assert capture.has_baseline
        assert capture.baseline_count == 2

    def test_capture_baseline_nonexistent_dir(self, tmp_path: Path):
        """Test baseline capture on nonexistent directory."""
        nonexistent = tmp_path / "does_not_exist"
        capture = CacheDeltaCapture(nonexistent)
        count = capture.capture_baseline()

        assert count == 0
        assert capture.has_baseline

    def test_get_delta_without_baseline_raises(self, tmp_path: Path):
        """Test that get_delta raises if no baseline captured."""
        capture = CacheDeltaCapture(tmp_path)

        with pytest.raises(RuntimeError, match="No baseline captured"):
            capture.get_delta()

    def test_get_delta_no_changes(self, tmp_path: Path):
        """Test delta when no files added."""
        (tmp_path / "existing.txt").write_text("existing")

        capture = CacheDeltaCapture(tmp_path)
        capture.capture_baseline()

        delta = capture.get_delta()
        assert delta == set()
        assert capture.get_delta_count() == 0

    def test_get_delta_with_new_files(self, tmp_path: Path):
        """Test delta captures new files."""
        (tmp_path / "existing.txt").write_text("existing")

        capture = CacheDeltaCapture(tmp_path)
        capture.capture_baseline()

        # Add new files
        (tmp_path / "new1.txt").write_text("new1")
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "new2.txt").write_text("new2")

        delta = capture.get_delta()
        assert delta == {"new1.txt", "subdir/new2.txt"}
        assert capture.get_delta_count() == 2

    def test_get_delta_ignores_modified_baseline_files(self, tmp_path: Path):
        """Test that modifying baseline files doesn't add them to delta."""
        existing = tmp_path / "existing.txt"
        existing.write_text("original")

        capture = CacheDeltaCapture(tmp_path)
        capture.capture_baseline()

        # Modify existing file
        existing.write_text("modified content")

        delta = capture.get_delta()
        assert delta == set()

    def test_get_delta_size_bytes(self, tmp_path: Path):
        """Test delta size calculation."""
        capture = CacheDeltaCapture(tmp_path)
        capture.capture_baseline()

        # Add files with known sizes
        (tmp_path / "file1.txt").write_text("12345")  # 5 bytes
        (tmp_path / "file2.txt").write_text("1234567890")  # 10 bytes

        size = capture.get_delta_size_bytes()
        assert size == 15

    def test_get_delta_size_bytes_empty_delta(self, tmp_path: Path):
        """Test delta size when no new files."""
        (tmp_path / "existing.txt").write_text("content")

        capture = CacheDeltaCapture(tmp_path)
        capture.capture_baseline()

        size = capture.get_delta_size_bytes()
        assert size == 0

    def test_copy_delta_to(self, tmp_path: Path):
        """Test copying delta files to destination."""
        cache_dir = tmp_path / "cache"
        dest_dir = tmp_path / "dest"
        cache_dir.mkdir()

        (cache_dir / "existing.txt").write_text("existing")

        capture = CacheDeltaCapture(cache_dir)
        capture.capture_baseline()

        # Add new files
        (cache_dir / "new1.txt").write_text("new1content")
        (cache_dir / "sub").mkdir()
        (cache_dir / "sub" / "new2.txt").write_text("new2content")

        copied = capture.copy_delta_to(dest_dir)

        assert copied == 2
        assert (dest_dir / "new1.txt").exists()
        assert (dest_dir / "new1.txt").read_text() == "new1content"
        assert (dest_dir / "sub" / "new2.txt").exists()
        assert (dest_dir / "sub" / "new2.txt").read_text() == "new2content"
        # Existing file should NOT be copied
        assert not (dest_dir / "existing.txt").exists()

    def test_copy_delta_to_dry_run(self, tmp_path: Path):
        """Test dry run doesn't copy files."""
        cache_dir = tmp_path / "cache"
        dest_dir = tmp_path / "dest"
        cache_dir.mkdir()

        capture = CacheDeltaCapture(cache_dir)
        capture.capture_baseline()

        (cache_dir / "new.txt").write_text("new")

        copied = capture.copy_delta_to(dest_dir, dry_run=True)

        assert copied == 1
        assert not dest_dir.exists()

    def test_copy_delta_to_without_baseline_raises(self, tmp_path: Path):
        """Test copy_delta_to raises without baseline."""
        capture = CacheDeltaCapture(tmp_path)

        with pytest.raises(RuntimeError, match="No baseline captured"):
            capture.copy_delta_to(tmp_path / "dest")

    def test_copy_delta_handles_deleted_files(self, tmp_path: Path):
        """Test handling of files deleted between delta calculation and copy."""
        cache_dir = tmp_path / "cache"
        dest_dir = tmp_path / "dest"
        cache_dir.mkdir()

        capture = CacheDeltaCapture(cache_dir)
        capture.capture_baseline()

        # Add and then delete a file
        new_file = cache_dir / "new.txt"
        new_file.write_text("content")

        # Get delta while file exists
        delta = capture.get_delta()
        assert "new.txt" in delta

        # Delete file before copy
        new_file.unlink()

        # Copy should handle gracefully
        copied = capture.copy_delta_to(dest_dir)
        assert copied == 0

    def test_capture_baseline_from_different_dir(self, tmp_path: Path):
        """Test capturing baseline from a different directory."""
        source_dir = tmp_path / "source"
        cache_dir = tmp_path / "cache"
        source_dir.mkdir()
        cache_dir.mkdir()

        # Create files in source
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "sub" / "file2.txt").parent.mkdir()
        (source_dir / "sub" / "file2.txt").write_text("content2")

        capture = CacheDeltaCapture(cache_dir)
        count = capture.capture_baseline_from(source_dir)

        assert count == 2
        assert capture.has_baseline

        # Now add a file to cache_dir that matches source
        (cache_dir / "file1.txt").write_text("content1")
        # And a truly new file
        (cache_dir / "new.txt").write_text("new")

        delta = capture.get_delta()
        # file1.txt should not be in delta (it's in baseline)
        # new.txt should be in delta
        assert delta == {"new.txt"}

    def test_handles_deep_directory_structure(self, tmp_path: Path):
        """Test with deeply nested directories."""
        capture = CacheDeltaCapture(tmp_path)

        # Create baseline with deep structure
        deep = tmp_path / "a" / "b" / "c" / "d"
        deep.mkdir(parents=True)
        (deep / "baseline.txt").write_text("baseline")

        capture.capture_baseline()

        # Add new deep file
        new_deep = tmp_path / "x" / "y" / "z"
        new_deep.mkdir(parents=True)
        (new_deep / "new.txt").write_text("new")

        delta = capture.get_delta()
        assert "x/y/z/new.txt" in delta
        assert capture.get_delta_count() == 1


class TestCopyAndCaptureDelta:
    """Tests for copy_and_capture_delta convenience function."""

    def test_basic_workflow(self, tmp_path: Path):
        """Test the complete copy-build-capture workflow."""
        source_cache = tmp_path / "source"
        build_cache = tmp_path / "build"
        delta_dest = tmp_path / "delta"

        source_cache.mkdir()
        (source_cache / "stdlib.txt").write_text("stdlib content")

        def build_operation():
            # Simulate build adding files
            (build_cache / "library.txt").write_text("library content")

        baseline, delta = copy_and_capture_delta(
            source_cache=source_cache,
            build_cache=build_cache,
            build_operation=build_operation,
            delta_dest=delta_dest,
        )

        assert baseline == 1  # stdlib.txt
        assert delta == 1  # library.txt
        assert (delta_dest / "library.txt").exists()
        assert not (delta_dest / "stdlib.txt").exists()

    def test_dry_run(self, tmp_path: Path):
        """Test dry run mode."""
        source_cache = tmp_path / "source"
        build_cache = tmp_path / "build"
        delta_dest = tmp_path / "delta"

        source_cache.mkdir()
        (source_cache / "stdlib.txt").write_text("stdlib")

        def build_operation():
            (build_cache / "library.txt").write_text("library")

        baseline, delta = copy_and_capture_delta(
            source_cache=source_cache,
            build_cache=build_cache,
            build_operation=build_operation,
            delta_dest=delta_dest,
            dry_run=True,
        )

        # In dry run, source isn't copied to build, but build_operation still runs
        # The delta is calculated but not copied to destination
        assert baseline == 0  # No files copied from source in dry run
        assert delta == 1  # library.txt is in the delta (would be copied)
        assert not delta_dest.exists()  # But delta_dest wasn't created

    def test_empty_source_cache(self, tmp_path: Path):
        """Test with no source cache (fresh build)."""
        source_cache = tmp_path / "source"  # Doesn't exist
        build_cache = tmp_path / "build"
        delta_dest = tmp_path / "delta"

        build_cache.mkdir()

        def build_operation():
            (build_cache / "library.txt").write_text("library")

        baseline, delta = copy_and_capture_delta(
            source_cache=source_cache,
            build_cache=build_cache,
            build_operation=build_operation,
            delta_dest=delta_dest,
        )

        assert baseline == 0
        assert delta == 1
        assert (delta_dest / "library.txt").exists()

    def test_build_operation_called(self, tmp_path: Path):
        """Test that build operation is called."""
        source_cache = tmp_path / "source"
        build_cache = tmp_path / "build"
        delta_dest = tmp_path / "delta"

        source_cache.mkdir()

        mock_build = MagicMock()

        copy_and_capture_delta(
            source_cache=source_cache,
            build_cache=build_cache,
            build_operation=mock_build,
            delta_dest=delta_dest,
        )

        mock_build.assert_called_once()
