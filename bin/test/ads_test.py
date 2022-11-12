from lib.cli.ads import parse_valid_ranges


def test_from_date_should_parse():
    (from_date, until_date) = parse_valid_ranges("2022-01-01", None)
    assert from_date == "2022-01-01T00:00:00"
    assert until_date is None


def test_until_date_should_parse():
    (from_date, until_date) = parse_valid_ranges(None, "2022-01-01")
    assert from_date is None
    assert until_date == "2022-01-01T00:00:00"


def test_both_dates_should_parse():
    (from_date, until_date) = parse_valid_ranges("2022-01-01", "2022-01-01")
    assert from_date == "2022-01-01T00:00:00"
    assert until_date == "2022-01-01T00:00:00"


def test_no_dates_should_parse():
    (from_date, until_date) = parse_valid_ranges(None, None)
    assert from_date is None
    assert until_date is None
