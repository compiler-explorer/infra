import re

import pytest
from lib.config_expand import expand_one, expand_target


def test_expand_one():
    assert expand_one("moo", {}) == "moo"
    assert expand_one("a{{badger}}b", {"badger": "moose"}) == "amooseb"


def test_expand_one_ignores_single_braces():
    assert expand_one("a{badger}b", {"badger": "moose"}) == "a{badger}b"


def test_expand_one_allows_escapes():
    assert expand_one("a{% raw %}{badger}{% endraw %}b", {"badger": "moose"}) == "a{badger}b"


def test_expand_target_handles_self_references():
    assert expand_target({"sponge": "bob_{{bob}}", "bob": "robert"}, []) == {"sponge": "bob_robert", "bob": "robert"}


def test_expand_target_handles_multiple_self_references():
    assert expand_target({"sponge": "bob_{{bob}}", "bob": "{{ian}}", "ian": "will{{iam}}", "iam": "y"}, []) == {
        "sponge": "bob_willy",
        "bob": "willy",
        "ian": "willy",
        "iam": "y",
    }


def test_expand_target_handles_infinite_recursion():
    with pytest.raises(RuntimeError, match=re.escape("Too many mutual references (in moo/shmoo)")):
        assert expand_target({"bob": "{{ian}}", "ian": "ooh{{bob}}"}, ["moo", "shmoo"])
