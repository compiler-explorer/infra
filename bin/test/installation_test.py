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
