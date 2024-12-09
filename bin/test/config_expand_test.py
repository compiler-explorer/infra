from lib.config_expand import expand_one


def test_expand_one():
    assert expand_one("moo", {}) == "moo"
    assert expand_one("a{badger}b", {"badger": "moose"}) == "amooseb"
