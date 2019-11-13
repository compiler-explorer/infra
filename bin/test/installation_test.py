import yaml
from nose.tools import assert_equals

from lib.installation import targets_from
from lib.config_safe_loader import ConfigSafeLoader


def parse_targets(string_config, enabled=None):
    enabled = enabled if enabled else set()
    return list(targets_from(yaml.load(string_config, Loader=ConfigSafeLoader), enabled))


def test_targets_from_simple_cases():
    assert list(targets_from({}, set())) == []
    assert parse_targets("") == []

    assert_equals(
        parse_targets("""
weasel:
    type: foo
    targets:
    - moo
    """), [
            {'type': 'foo', 'name': 'moo', 'context': ['weasel']}
        ])


def test_targets_from_carries_hierarchy_config():
    assert_equals(
        parse_targets("""
weasel:
    base_config: "weasel"
    weasel_config: "weasel"
    baboon:
        type: foo
        base_config: "baboon" # overrides weasel
        targets:
        - ook
    """), [
            {'type': 'foo', 'base_config': 'baboon', 'weasel_config': 'weasel',
             'context': ['weasel', 'baboon'], 'name': 'ook'}
        ])


def test_codependent_configs():
    [target] = parse_targets("""
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
    """)
    assert_equals(target['check_exe'], "mips-arch/blah")


def test_codependent_throws():
    try:
        parse_targets("""
compilers:
  mips:
    x: "{y}"
    y: "{x}"
    targets:
      - name: 5.4.0
        subdir: mips
    """)
        assert False
    except RuntimeError as re:
        assert_equals(str(re), "Too many mutual references (in compilers/mips)")
