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


def test_multiple_targets_with_overrides():
    assert_equals(
        parse_targets("""
compilers:
    clang:
    - type: type_a
      value: type_a_base
      targets:
      - one
      - two
      - name: three
        value: type_three_override
    - type: type_b
      targets:
      - four
      - five
    - type: type_c
      targets:
      - six
    """), [
            {'type': 'type_a', 'value': 'type_a_base', 'name': 'one', 'context': ['compilers', 'clang']},
            {'type': 'type_a', 'value': 'type_a_base', 'name': 'two', 'context': ['compilers', 'clang']},
            {'type': 'type_a', 'value': 'type_three_override', 'name': 'three', 'context': ['compilers', 'clang']},
            {'type': 'type_b', 'name': 'four', 'context': ['compilers', 'clang']},
            {'type': 'type_b', 'name': 'five', 'context': ['compilers', 'clang']},
            {'type': 'type_c', 'name': 'six', 'context': ['compilers', 'clang']}
        ])


def test_targets_with_string_interpolation():
    assert_equals(
        parse_targets("""
root:
    var: The first var
    child:
        type: tip
        var2: the second var
        targets:
        - name: bob
          value: "{var}-{var2}"
    """), [
            {'type': 'tip', 'name': 'bob', 'context': ['root', 'child'], 'var': 'The first var',
             'var2': 'the second var',
             'value': 'The first var-the second var'}
        ])


def test_targets_enabled():
    assert_equals(
        parse_targets("""
weasel:
    if: weasels_allowed
    type: foo
    targets:
    - moo
    """), [])
    assert_equals(
        parse_targets("""
weasel:
    if: weasels_allowed
    type: foo
    targets:
    - moo
    """, ['weasels_allowed']), [
            {'if': 'weasels_allowed', 'type': 'foo', 'context': ['weasel'], 'name': 'moo'}
        ])


def test_targets_with_type_in_outer():
    assert_equals(
        parse_targets("""
outer:
    type: outer
    inner:
        targets:
        - target
    """), [{'name': 'target', 'type': 'outer', 'context': ['outer', 'inner']}])


def test_targets_with_context_and_targets():
    assert_equals(
        parse_targets("""
outer:
    type: outer
    targets:
    - outer_target
    inner:
        targets:
        - inner_target
    """), [
            {'name': 'inner_target', 'type': 'outer', 'context': ['outer', 'inner']},
            {'name': 'outer_target', 'type': 'outer', 'context': ['outer']},
        ])


def test_targets_dependent_expansion():
    assert_equals(
        parse_targets("""
root:
    arch_prefix: abc
    check_exe: def
    arch_prefix: "{subdir}-unknown-linux-gnu"
    check_exe: "{arch_prefix}/bin/{arch_prefix}-g++ --version"
    targets:
      - name: 5.4.0
        subdir: mips
    """)[0]['check_exe'], 'mips-unknown-linux-gnu/bin/mips-unknown-linux-gnu-g++ --version')


def test_targets_array_expansion():
    assert_equals(
        parse_targets("""
nasm:
  configure_command:
    - bash
    - -c
    - cd nasm-{name} && sh configure --prefix=/tmp/foo && make -j$(nproc)
  targets:
    - 2.12.02
""")[0]['configure_command'], ['bash', '-c', 'cd nasm-2.12.02 && sh configure --prefix=/tmp/foo && make -j$(nproc)']
    )


def test_bools_stay_bool():
    yaml_test = yaml.load("true1: true", Loader=ConfigSafeLoader)
    assert_equals(yaml_test['true1'], True)
    target = parse_targets("""
moose:
  true1: true
  targets:
    - name: a
      false1: false
""")[0]
    assert_equals(target['true1'], True)
    assert_equals(target['false1'], False)


def test_strings_that_look_datey_stay_stringy():
    yaml_test = yaml.load("date: 2017-01-01", Loader=ConfigSafeLoader)
    assert_equals(yaml_test['date'], "2017-01-01")


def test_dont_load_floats():
    target = parse_targets("""
moose:
  value1: 0.1
  targets:
    - name: a
      value2: 1.77
""")[0]
    assert_equals(target['value1'], "0.1")
    assert_equals(target['value2'], "1.77")
