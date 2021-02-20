from lib.releases import Version, VersionSource


def test_version_should_parse():
    assert Version.from_string('1234') == Version(VersionSource.GITHUB, 1234)
    assert Version.from_string('tr-123') == Version(VersionSource.TRAVIS, 123)
    assert Version.from_string('gh-123') == Version(VersionSource.GITHUB, 123)


def test_version_should_order_correctly_within_same_source():
    assert Version(VersionSource.TRAVIS, 123) < Version(VersionSource.TRAVIS, 125)
    assert Version(VersionSource.TRAVIS, 125) > Version(VersionSource.TRAVIS, 123)
    assert Version(VersionSource.GITHUB, 123) < Version(VersionSource.GITHUB, 125)
    assert Version(VersionSource.GITHUB, 125) > Version(VersionSource.GITHUB, 123)


def test_version_should_order_between_sources():
    assert Version(VersionSource.TRAVIS, 123) < Version(VersionSource.GITHUB, 125)
    assert Version(VersionSource.TRAVIS, 200) < Version(VersionSource.GITHUB, 100)


def test_version_should_str_nicely():
    assert f'{Version(VersionSource.GITHUB, 12)}' == 'gh-12'
