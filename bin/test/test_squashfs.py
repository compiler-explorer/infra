#!/usr/bin/env python3
"""Tests for squashfs utilities."""

from lib.squashfs import SquashfsEntry, parse_unsquashfs_line


class TestUnsquashfsParser:
    def test_parse_regular_file(self):
        """Test parsing a regular file without spaces."""
        line = "-rw-r--r-- root/root      1234 2021-03-12 09:29 /usr/bin/gcc"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="-", size=1234, path="usr/bin/gcc")

    def test_parse_regular_file_with_spaces(self):
        """Test parsing a regular file with spaces in the name."""
        line = "-rw-r--r-- root/root       628 2021-03-12 09:29 /debugger/10.1.1/dep/lib/python3.9/site-packages/setuptools/command/launcher manifest.xml"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(
            file_type="-",
            size=628,
            path="debugger/10.1.1/dep/lib/python3.9/site-packages/setuptools/command/launcher manifest.xml",
        )

    def test_intel_compiler_case(self):
        """Test the exact Intel compiler case that was failing."""
        line = "-rw-r--r-- root/root               628 2021-03-12 09:29 /debugger/10.1.1/dep/lib/python3.9/site-packages/setuptools/command/launcher manifest.xml"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(
            file_type="-",
            size=628,
            path="debugger/10.1.1/dep/lib/python3.9/site-packages/setuptools/command/launcher manifest.xml",
        )

    def test_parse_directory(self):
        """Test parsing a directory."""
        line = "drwxr-xr-x root/root         0 2021-03-12 09:29 /usr/include"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="d", size=0, path="usr/include")

    def test_parse_directory_with_spaces(self):
        """Test parsing a directory with spaces."""
        line = "drwxr-xr-x root/root         0 2021-03-12 09:29 /my special directory/with spaces"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="d", size=0, path="my special directory/with spaces")

    def test_parse_symlink(self):
        """Test parsing a symlink without spaces."""
        line = "lrwxrwxrwx root/root         0 2021-03-12 09:29 /usr/bin/g++ -> /usr/bin/gcc"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="l", size=0, path="usr/bin/g++", target="/usr/bin/gcc")

    def test_parse_symlink_with_spaces_in_source(self):
        """Test parsing a symlink with spaces in the source path."""
        line = "lrwxrwxrwx root/root         0 2021-03-12 09:29 /my link with spaces -> /target"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="l", size=0, path="my link with spaces", target="/target")

    def test_parse_symlink_with_spaces_in_target(self):
        """Test parsing a symlink with spaces in the target path."""
        line = "lrwxrwxrwx root/root         0 2021-03-12 09:29 /mylink -> /target with spaces"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="l", size=0, path="mylink", target="/target with spaces")

    def test_parse_symlink_with_spaces_in_both(self):
        """Test parsing a symlink with spaces in both source and target."""
        line = "lrwxrwxrwx root/root         0 2021-03-12 09:29 /my link file -> /my target file"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="l", size=0, path="my link file", target="/my target file")

    def test_parse_root_directory(self):
        """Test parsing the root directory line (no path)."""
        line = "drwxr-xr-x root/root         0 2021-03-12 09:29"
        result = parse_unsquashfs_line(line)
        assert result is None  # Root directory should be skipped

    def test_parse_executable_file(self):
        """Test parsing an executable file."""
        line = "-rwxr-xr-x root/root     12345 2021-03-12 09:29 /bin/bash"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="-", size=12345, path="bin/bash")

    def test_parse_setuid_file(self):
        """Test parsing a file with setuid bit."""
        line = "-rwsr-xr-x root/root      5678 2021-03-12 09:29 /usr/bin/sudo"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="-", size=5678, path="usr/bin/sudo")

    def test_parse_sticky_bit_directory(self):
        """Test parsing a directory with sticky bit."""
        line = "drwxrwxrwt root/root         0 2021-03-12 09:29 /tmp"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="d", size=0, path="tmp")

    def test_parse_block_device(self):
        """Test parsing a block device (if present in squashfs)."""
        line = "brw-r--r-- root/root       123 2021-03-12 09:29 /dev/sda"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(
            file_type="b",
            size=0,  # Block devices get size 0
            path="dev/sda",
        )

    def test_parse_character_device(self):
        """Test parsing a character device (if present in squashfs)."""
        line = "crw-r--r-- root/root       456 2021-03-12 09:29 /dev/null"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(
            file_type="c",
            size=0,  # Character devices get size 0
            path="dev/null",
        )

    def test_invalid_line(self):
        """Test that invalid lines return None."""
        assert parse_unsquashfs_line("invalid line") is None
        assert parse_unsquashfs_line("") is None
        assert parse_unsquashfs_line("   ") is None

    def test_large_file_size(self):
        """Test parsing files with large sizes."""
        line = "-rw-r--r-- root/root 1234567890 2021-03-12 09:29 /huge/file.dat"
        result = parse_unsquashfs_line(line)
        assert result == SquashfsEntry(file_type="-", size=1234567890, path="huge/file.dat")

    def test_arrow_in_filename(self):
        """Test parsing a regular file with ' -> ' in its name (edge case)."""
        # This is tricky - a file actually named "file -> something.txt"
        # In unsquashfs output, this would NOT be a symlink (note the file type is '-' not 'l')
        line = "-rw-r--r-- root/root       100 2021-03-12 09:29 /weird/file -> not_a_link.txt"
        result = parse_unsquashfs_line(line)
        # Since file type is '-' not 'l', this should be treated as a filename with arrow
        assert result == SquashfsEntry(file_type="-", size=100, path="weird/file -> not_a_link.txt")
