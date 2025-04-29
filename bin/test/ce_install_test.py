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
