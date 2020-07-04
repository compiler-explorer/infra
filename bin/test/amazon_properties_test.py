import logging

from lib.amazon_properties import get_properties_compilers_and_libraries

logger = logging.getLogger(__name__)
logger.level = 9

def test_should_contain_some_compilers_and_libraries():
    [_compilers, _libraries] = get_properties_compilers_and_libraries('c++', logger)
    assert len(_compilers) > 0
    assert len(_libraries) > 0

def test_should_not_contain_g412():
    [_compilers, _libraries] = get_properties_compilers_and_libraries('c++', logger)
    assert not 'g412' in _compilers

def test_should_not_contain_msvc():
    [_compilers, _libraries] = get_properties_compilers_and_libraries('c++', logger)
    assert not 'cl19_2015_u3_64' in _compilers

def test_should_contain_gcc101():
    [_compilers, _libraries] = get_properties_compilers_and_libraries('c++', logger)
    assert 'g101' in _compilers

def test_should_contain_clang800():
    [_compilers, _libraries] = get_properties_compilers_and_libraries('c++', logger)
    assert 'clang800' in _compilers

def test_should_contain_optionsforclang800():
    [_compilers, _libraries] = get_properties_compilers_and_libraries('c++', logger)
    assert '--gcc-toolchain=/opt/compiler-explorer/gcc-8.3.0' in _compilers['clang800']['options']
