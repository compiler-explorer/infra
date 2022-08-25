from unittest.mock import MagicMock

import pytest
import yaml

from lib.config_safe_loader import ConfigSafeLoader
from lib.installation import targets_from, Installable, InstallationContext


def parse_targets(string_config, enabled=None):
    enabled = enabled if enabled else set()
    return list(targets_from(yaml.load(string_config, Loader=ConfigSafeLoader), enabled))


def test_targets_from_simple_cases():
    assert list(targets_from({}, set())) == []
    assert parse_targets("") == []

    assert (
        parse_targets(
            """
weasel:
    type: foo
    targets:
    - moo
    """
        )
        == [{"type": "foo", "name": "moo", "underscore_name": "moo", "context": ["weasel"]}]
    )


def test_targets_from_carries_hierarchy_config():
    assert (
        parse_targets(
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
        )
        == [
            {
                "type": "foo",
                "base_config": "baboon",
                "weasel_config": "weasel",
                "context": ["weasel", "baboon"],
                "name": "ook",
                "underscore_name": "ook",
            }
        ]
    )


def test_codependent_configs():
    [target] = parse_targets(
        """
compilers:
  gcc:
    check_exe: "bin/{arch_prefix}/blah"
    subdir: arm
    mips:
      arch_prefix: "{subdir}-arch"
      check_exe: "{arch_prefix}/blah"
      targets:
        - name: 5.4.0
          subdir: mips
    """
    )
    assert target["check_exe"] == "mips-arch/blah"


def test_codependent_throws():
    with pytest.raises(RuntimeError, match=r"Too many mutual references \(in compilers/mips\)"):
        parse_targets(
            """
compilers:
  mips:
    x: "{y}"
    y: "{x}"
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
  url: https://dl.bintray.com/boostorg/release/{name}/source/boost_{underscore_name}.tar.bz2
  targets:
    - 1.64.0
      """
    )
    assert target["url"] == "https://dl.bintray.com/boostorg/release/1.64.0/source/boost_1_64_0.tar.bz2"


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    return MagicMock(spec=InstallationContext)


def test_installable_sort(fake_context):
    ab_c = Installable(fake_context, dict(context=["a", "b"], name="c"))
    v1_2_3 = Installable(fake_context, dict(context=[], name="1.2.3"))
    v10_1 = Installable(fake_context, dict(context=[], name="10.1"))
    v10_1_alpha = Installable(fake_context, dict(context=[], name="10.1-alpha"))
    v10_2 = Installable(fake_context, dict(context=[], name="10.2"))
    assert sorted([v10_1, v10_1_alpha, ab_c, v1_2_3, v10_2], key=lambda x: x.sort_key) == [
        v1_2_3,
        v10_1,
        v10_1_alpha,
        v10_2,
        ab_c,
    ]
