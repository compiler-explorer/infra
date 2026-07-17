import re
from pathlib import Path
from unittest import mock

import pytest
import yaml
from lib.config_safe_loader import ConfigSafeLoader
from lib.installable.installable import Installable
from lib.installation import targets_from
from lib.installation_context import InstallationContext


def parse_targets(string_config, enabled=None):
    enabled = enabled if enabled else set()
    return list(targets_from(yaml.load(string_config, Loader=ConfigSafeLoader), enabled))


def test_targets_from_simple_cases():
    assert list(targets_from({}, set())) == []
    assert parse_targets("") == []

    assert parse_targets(
        """
weasel:
    type: foo
    targets:
    - moo
    """
    ) == [{"type": "foo", "name": "moo", "underscore_name": "moo", "context": ["weasel"]}]


def test_targets_from_carries_hierarchy_config():
    assert parse_targets(
        """
weasel:
    base_config: "weasel"
    weasel_config: "weasel"
    baboon:
        type: foo
        base_config: "baboon" # overrides weasel
        targets:
        - ook
    """
    ) == [
        {
            "type": "foo",
            "base_config": "baboon",
            "weasel_config": "weasel",
            "context": ["weasel", "baboon"],
            "name": "ook",
            "underscore_name": "ook",
        }
    ]


def test_codependent_configs():
    [target] = parse_targets(
        """
compilers:
  gcc:
    check_exe: "bin/{{arch_prefix}}/blah"
    subdir: arm
    mips:
      arch_prefix: "{{subdir}}-arch"
      check_exe: "{{arch_prefix}}/blah"
      targets:
        - name: 5.4.0
          subdir: mips
    """
    )
    assert target["check_exe"] == "mips-arch/blah"


def test_codependent_throws():
    with pytest.raises(RuntimeError, match=re.escape("Too many mutual references (in compilers/mips)")):
        parse_targets(
            """
compilers:
  mips:
    x: "{{y}}"
    y: "{{x}}"
    targets:
      - name: 5.4.0
        subdir: mips
    """
        )


def test_numbers_at_root():
    [target] = parse_targets(
        """
compilers:
  num_to_keep: 2
  targets:
    - name: 5.4.0
    """
    )
    assert target["num_to_keep"] == 2


def test_numbers_at_leaf():
    [target] = parse_targets(
        """
compilers:
  targets:
    - name: 5.4.0
      num_to_keep: 2
    """
    )
    assert target["num_to_keep"] == 2


def test_nested_expansion():
    [first, second] = parse_targets(
        """
compilers:
  v5to7:
    architectures: &up-to-7
      - AAA
    targets:
      - first
  v10to12:
    architectures:
      - *up-to-7
      - DDD
    targets:
      - second
"""
    )
    assert first["architectures"] == ["AAA"]
    assert second["architectures"] == [["AAA"], "DDD"]


def test_jinja_expansion():
    [target] = parse_targets(
        """
compilers:
  targets:
    - name: 5.4.0
      spleen: '{{ name }}'
      """
    )
    assert target["spleen"] == "5.4.0"


def test_jinja_expansion_with_filters():
    [target] = parse_targets(
        """
compilers:
  targets:
    - name: 5.4.0
      spleen: "{{ name | replace('.', '_') }}"
      """
    )
    assert target["spleen"] == "5_4_0"


def test_jinja_expansion_with_filters_refering_forward():
    [target] = parse_targets(
        """
boost:
  underscore_name: "{{ name | replace('.', '_') }}"
  url: https://dl.bintray.com/boostorg/release/{{name}}/source/boost_{{underscore_name}}.tar.bz2
  targets:
    - 1.64.0
      """
    )
    assert target["url"] == "https://dl.bintray.com/boostorg/release/1.64.0/source/boost_1_64_0.tar.bz2"


def test_after_stage_script_dep():
    ic = mock.Mock(spec_set=InstallationContext)
    ic.destination = Path("/some/install/dir")
    installation_a = Installable(
        ic,
        {
            "context": ["compilers"],
            "name": "a",
            "after_stage_script": ["echo hello", "echo %DEP0%", "moo"],
            "depends": ["compilers b"],
        },
    )
    installation_b = Installable(ic, {"context": ["compilers"], "name": "b"})
    installation_b.install_path = "pathy"
    Installable.resolve([installation_a, installation_b])
    assert installation_a.after_stage_script == ["echo hello", "echo /some/install/dir/pathy", "moo"]


def test_check_exe_dep():
    ic = mock.Mock(spec_set=InstallationContext)
    ic.destination = Path("/some/install/dir")
    installation_a = Installable(
        ic,
        {
            "context": ["compilers"],
            "name": "a",
            "check_exe": "%DEP0%/bin/java --jar path/to/jar",
            "depends": ["compilers b"],
        },
    )
    installation_b = Installable(ic, {"context": ["compilers"], "name": "b"})
    installation_b.install_path = "pathy"
    Installable.resolve([installation_a, installation_b])
    assert installation_a.check_call == ["/some/install/dir/pathy/bin/java", "--jar", "path/to/jar"]


def make_mock_ic(destination: Path, dry_run: bool = False) -> mock.Mock:
    ic = mock.create_autospec(InstallationContext, instance=True)
    ic.destination = destination
    ic.dry_run = dry_run
    # Use the real remove_dir implementation
    ic.remove_dir = lambda directory: InstallationContext.remove_dir(ic, directory)
    return ic


def test_remove_dir_removes_real_directory(tmp_path):
    """remove_dir should delete real directories."""
    ic = make_mock_ic(tmp_path)

    real_dir = tmp_path / "some-compiler-20250101"
    real_dir.mkdir()
    (real_dir / "bin").mkdir()

    ic.remove_dir("some-compiler-20250101")

    assert not real_dir.exists()


def test_remove_dir_removes_symlink(tmp_path):
    """remove_dir should remove symlinks (CEFS case) rather than silently doing nothing.

    On CEFS, nightly compiler paths are symlinks to /cefs/... squashfs mounts.
    shutil.rmtree silently fails on symlinks in Python 3.12+ (NotADirectoryError is
    swallowed by ignore_errors=True), leaving stale symlinks accumulating indefinitely.
    """
    ic = make_mock_ic(tmp_path)

    # Simulate a CEFS setup: real dir elsewhere, symlink in the destination
    cefs_target = tmp_path / "cefs_storage" / "abc123_some-compiler-20250101"
    cefs_target.mkdir(parents=True)
    symlink_path = tmp_path / "some-compiler-20250101"
    symlink_path.symlink_to(cefs_target)

    assert symlink_path.is_symlink()

    ic.remove_dir("some-compiler-20250101")

    assert not symlink_path.exists(follow_symlinks=False), "Symlink should have been removed"
    assert cefs_target.exists(), "CEFS target should not have been deleted"


def test_remove_dir_dry_run_does_nothing(tmp_path):
    """remove_dir in dry-run mode should not delete anything."""
    ic = make_mock_ic(tmp_path, dry_run=True)

    real_dir = tmp_path / "some-compiler-20250101"
    real_dir.mkdir()

    ic.remove_dir("some-compiler-20250101")

    assert real_dir.exists(), "Directory should not be removed in dry-run mode"
