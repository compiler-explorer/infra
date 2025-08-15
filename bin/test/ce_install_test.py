from unittest.mock import Mock

from lib.ce_install import filter_aggregate, filter_match


def fake(context, target_name):
    return Mock(context=context.split("/"), target_name=target_name)


def test_should_filter_exact_matches():
    assert filter_match("/compilers/c++ target", fake("compilers/c++", "target"))


def test_should_not_filter_mismatches():
    assert not filter_match("/compilers/c++ target", fake("libraries/ghidra", "classic"))


def test_should_filter_partial_path_matches():
    assert filter_match("/compilers", fake("compilers/c++", "target"))
    assert filter_match("compilers", fake("compilers/c++", "target"))
    assert filter_match("c++", fake("compilers/c++", "target"))
    assert filter_match("target", fake("compilers/c++", "target"))
    assert filter_match("compilers/c++", fake("compilers/c++", "target"))
    assert filter_match("compilers/c++ target", fake("compilers/c++", "target"))
    assert filter_match("c++ target", fake("compilers/c++", "target"))


def test_should_not_accept_partial_substrings_of_path_parts():
    assert not filter_match("targe", fake("compilers/c++", "target"))
    assert not filter_match("compilers/c", fake("compilers/c++", "target"))
    assert not filter_match("/compilers/c", fake("compilers/c++", "target"))


def test_should_match_target_and_context_when_given_both():
    assert filter_match("foo bar", fake("foo", "bar"))
    assert not filter_match("foo foo", fake("foo", "bar"))
    assert not filter_match("bar bar", fake("foo", "bar"))


def test_should_match_target_or_context_when_given_one():
    assert filter_match("badger", fake("badger", "monkey"))
    assert filter_match("monkey", fake("badger", "monkey"))
    assert not filter_match("badger/monkey", fake("badger", "monkey"))


def test_should_match_whole_name():
    assert filter_match("a/b/c", fake("a/b/c", "target"))


def test_should_match_end_of_context():
    assert filter_match("b/c", fake("a/b/c", "target"))


def test_should_honour_root_matches():
    assert filter_match("/a/b/c", fake("a/b/c", "target"))
    assert not filter_match("/b/c", fake("a/b/c", "target"))


def test_should_match_all_filters():
    assert not filter_aggregate(["a", "b"], fake("a", "target"), filter_match_all=True)
    assert not filter_aggregate(["a", "b"], fake("b", "target"), filter_match_all=True)
    assert filter_aggregate(["a", "target"], fake("a", "target"), filter_match_all=True)


def test_should_match_any_filter():
    assert filter_aggregate(["a", "b"], fake("a", "target"), filter_match_all=False)
    assert filter_aggregate(["a", "b"], fake("b", "target"), filter_match_all=False)
    assert not filter_aggregate(["a", "b"], fake("c", "target"), filter_match_all=False)


def test_all_should_match_all_filters():
    test = [
        fake("a/x", "target"),
        fake("a/y", "target"),
        fake("a/z", "target"),
        fake("a/z", "other"),
        fake("b/x", "target"),
        fake("b/y", "target"),
        fake("b/z", "target"),
        fake("b/z", "other"),
        fake("c/x", "target"),
        fake("c/y", "target"),
        fake("c/z", "target"),
        fake("c/z", "other"),
    ]

    filter1 = ["a", "b"]
    test1 = list(filter(lambda installable: filter_aggregate(filter1, installable, filter_match_all=True), test))
    test1_answer = []
    assert test1 == test1_answer

    filter2 = ["a", "target"]
    test2 = list(filter(lambda installable: filter_aggregate(filter2, installable, filter_match_all=True), test))
    test2_answer = [test[0], test[1], test[2]]
    assert test2 == test2_answer

    filter3 = ["target", "other"]
    test3 = list(filter(lambda installable: filter_aggregate(filter3, installable, filter_match_all=True), test))
    test3_answer = []
    assert test3 == test3_answer

    filter4 = ["c", "z", "other"]
    test4 = list(filter(lambda installable: filter_aggregate(filter4, installable, filter_match_all=True), test))
    test4_answer = [test[11]]
    assert test4 == test4_answer


def test_all_should_match_any_filter():
    test = [
        fake("a/x", "target"),
        fake("a/y", "target"),
        fake("a/z", "target"),
        fake("a/z", "other"),
        fake("b/x", "target"),
        fake("b/y", "target"),
        fake("b/z", "target"),
        fake("b/z", "other"),
        fake("c/x", "target"),
        fake("c/y", "target"),
        fake("c/z", "target"),
        fake("c/z", "other"),
    ]

    filter1 = ["a", "b"]
    test1 = list(filter(lambda installable: filter_aggregate(filter1, installable, filter_match_all=False), test))
    test1_answer = [test[0], test[1], test[2], test[3], test[4], test[5], test[6], test[7]]
    assert test1 == test1_answer

    filter2 = ["a", "b", "c/z"]
    test2 = list(filter(lambda installable: filter_aggregate(filter2, installable, filter_match_all=False), test))
    test2_answer = [test[0], test[1], test[2], test[3], test[4], test[5], test[6], test[7], test[10], test[11]]
    assert test2 == test2_answer

    filter3 = ["a/x target", "b/z other", "c/z other"]
    test3 = list(filter(lambda installable: filter_aggregate(filter3, installable, filter_match_all=False), test))
    test3_answer = [test[0], test[7], test[11]]
    assert test3 == test3_answer

    filter4 = ["y", "z"]
    test4 = list(filter(lambda installable: filter_aggregate(filter4, installable, filter_match_all=False), test))
    test4_answer = [test[1], test[2], test[3], test[5], test[6], test[7], test[9], test[10], test[11]]
    assert test4 == test4_answer


def test_wildcard_target_matching():
    """Test wildcard patterns in target names."""
    # Test single * wildcard
    assert filter_match("assertions-*", fake("compilers/c++/clang", "assertions-3.5.0"))
    assert filter_match("assertions-*", fake("compilers/c++/clang", "assertions-10.0.0"))
    assert not filter_match("assertions-*", fake("compilers/c++/clang", "10.0.0"))

    # Test version wildcards
    assert filter_match("14.*", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("14.*", fake("compilers/c++/gcc", "14.2.1"))
    assert not filter_match("14.*", fake("compilers/c++/gcc", "13.1.0"))

    # Test context + wildcard target
    assert filter_match("gcc 14.*", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("clang assertions-*", fake("compilers/c++/clang", "assertions-3.5.0"))
    assert not filter_match("gcc 14.*", fake("compilers/c++/clang", "14.1.0"))


def test_wildcard_context_matching():
    """Test wildcard patterns in context paths."""
    # Test wildcards in context
    assert filter_match("*/gcc", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("*/gcc", fake("cross/gcc", "14.1.0"))
    assert not filter_match("*/gcc", fake("compilers/c++/clang", "14.1.0"))

    # Test multiple wildcards
    assert filter_match("*/c++/*", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("*/c++/*", fake("libraries/c++/boost", "1.70.0"))
    assert not filter_match("*/c++/*", fake("compilers/c/gcc", "14.1.0"))


def test_negative_filter_matching():
    """Test negative filter patterns."""
    # Test negative context matching
    assert filter_match("!cross", fake("compilers/c++/gcc", "14.1.0"))
    assert not filter_match("!cross", fake("compilers/c++/cross/gcc", "14.1.0"))

    # Test negative target matching
    assert filter_match("!assertions-3.5.0", fake("compilers/c++/clang", "10.0.0"))
    assert not filter_match("!assertions-3.5.0", fake("compilers/c++/clang", "assertions-3.5.0"))

    # Test negative with wildcards
    assert filter_match("!assertions-*", fake("compilers/c++/clang", "10.0.0"))
    assert not filter_match("!assertions-*", fake("compilers/c++/clang", "assertions-3.5.0"))

    # Test context + negative target
    assert filter_match("gcc !assertions-*", fake("compilers/c++/gcc", "14.1.0"))
    assert not filter_match("gcc !assertions-*", fake("compilers/c++/gcc", "assertions-14.1.0"))


def test_version_range_matching():
    """Test semantic version range patterns."""
    # Test >= version matching
    assert filter_match(">=14.0.0", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match(">=14.0.0", fake("compilers/c++/gcc", "15.0.0"))
    assert not filter_match(">=14.0.0", fake("compilers/c++/gcc", "13.1.0"))

    # Test < version matching
    assert filter_match("<15.0.0", fake("compilers/c++/gcc", "14.1.0"))
    assert not filter_match("<15.0.0", fake("compilers/c++/gcc", "15.0.0"))

    # Test tilde range matching (~1.70 matches 1.70.x)
    assert filter_match("~1.70", fake("libraries/c++/boost", "1.70.0"))
    assert filter_match("~1.70", fake("libraries/c++/boost", "1.70.5"))
    assert not filter_match("~1.70", fake("libraries/c++/boost", "1.71.0"))

    # Test context + version range
    assert filter_match("gcc >=14.0", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("boost ~1.70", fake("libraries/c++/boost", "1.70.0"))


def test_complex_filter_combinations():
    """Test combinations of multiple filter features."""
    # Wildcards with negative
    assert filter_match("gcc !14.*", fake("compilers/c++/gcc", "13.1.0"))
    assert not filter_match("gcc !14.*", fake("compilers/c++/gcc", "14.1.0"))

    # Multiple negatives
    test_items = [
        fake("compilers/c++/gcc", "14.1.0"),
        fake("compilers/c++/clang", "14.1.0"),
        fake("compilers/c++/icc", "14.1.0"),
        fake("cross/gcc", "14.1.0"),
    ]

    # Should match only ICC (not gcc, not clang, not cross)
    filtered = list(
        filter(lambda x: filter_aggregate(["!gcc", "!clang", "!cross"], x, filter_match_all=True), test_items)
    )
    assert len(filtered) == 1
    assert filtered[0].context == ["compilers", "c++", "icc"]


def test_backwards_compatibility():
    """Ensure existing filter behavior is preserved."""
    # All existing exact matching should still work
    assert filter_match("gcc", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("14.1.0", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("gcc 14.1.0", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("/compilers", fake("compilers/c++/gcc", "14.1.0"))
    assert filter_match("c++/gcc", fake("compilers/c++/gcc", "14.1.0"))

    # Ensure non-pattern strings don't get treated as patterns
    assert not filter_match("14.1.0", fake("compilers/c++/gcc", "14.1.1"))
    assert not filter_match("gcc", fake("compilers/c++/clang", "14.1.0"))
