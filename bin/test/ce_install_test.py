from unittest.mock import Mock

from lib.ce_install import filter_match


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
