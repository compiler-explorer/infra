from datetime import date

import pytest
from lib.nightly_prune import DatedArtifact, parse_dated_artifact, parse_dated_artifacts, plan_prune

PREFIX = "opt/"


def artifact(family: str, date: str, size: int = 1) -> DatedArtifact:
    return DatedArtifact(date=date, key=f"{PREFIX}{family}-{date}.tar.xz", family=family, size=size)


def test_parses_a_dated_tarball():
    parsed = parse_dated_artifact("opt/gcc-trunk-20260101.tar.xz", 123, PREFIX)

    assert parsed == DatedArtifact(date="20260101", key="opt/gcc-trunk-20260101.tar.xz", family="gcc-trunk", size=123)


@pytest.mark.parametrize("compression", [".tar.xz", ".tar.gz", ".tar.bz2", ".tar.zstd", ".tar"])
def test_parses_every_compression_we_use(compression):
    parsed = parse_dated_artifact(f"opt/thing-trunk-20260101{compression}", 1, PREFIX)

    assert parsed is not None
    assert parsed.family == "thing-trunk"


def test_parses_names_the_old_regex_could_not_match():
    """The shell version's [-a-zA-Z0-9_] character class could not match across a "+"."""
    parsed = parse_dated_artifact("opt/6502-c++-trunk-20260101.tar.xz", 1, PREFIX)

    assert parsed is not None
    assert parsed.family == "6502-c++-trunk"


def test_parses_names_with_dots_and_underscores():
    for family in ("clang-thephd.dev", "gcc-ilazaric-enclosing_cast"):
        parsed = parse_dated_artifact(f"opt/{family}-20260101.tar.xz", 1, PREFIX)

        assert parsed is not None
        assert parsed.family == family


@pytest.mark.parametrize(
    "key",
    [
        "opt/gcc-14.1.0.tar.xz",  # a version, not a date
        "opt/gcc-trunk-20260101.zip",  # not a tarball
        "opt/ccomp-master-20230307-x86_64.tar.xz",  # date is not the last component
        "opt/gcc-trunk-20261301.tar.xz",  # month 13
        "opt/gcc-trunk-20260132.tar.xz",  # day 32
        "opt/gcc-trunk-19990101.tar.xz",  # before we existed
        "opt/nested/gcc-trunk-20260101.tar.xz",  # not directly under the prefix
        "opt-nonfree/edg-20260101.tar.xz",  # a different prefix entirely
        "opt/20260101.tar.xz",  # no family at all
    ],
)
def test_rejects_keys_that_are_not_dated_builds(key):
    assert parse_dated_artifact(key, 1, PREFIX) is None


def test_parse_dated_artifacts_drops_the_rest():
    objects = [("opt/gcc-trunk-20260101.tar.xz", 1), ("opt/gcc-14.1.0.tar.xz", 2), ("opt/", 0)]

    assert [parsed.family for parsed in parse_dated_artifacts(objects, PREFIX)] == ["gcc-trunk"]


def test_keeps_the_newest_dates_and_removes_the_rest():
    artifacts = [artifact("gcc-trunk", date) for date in ("20260101", "20260102", "20260103", "20260104")]

    plan = plan_prune(artifacts, {"gcc-trunk": ["compilers/c++/gcc trunk"]}, keep_last=2)

    (family,) = plan.claimed
    assert [a.date for a in family.keep] == ["20260103", "20260104"]
    assert [a.date for a in family.remove] == ["20260101", "20260102"]


def test_ranks_by_date_in_the_key_not_by_input_order():
    artifacts = [artifact("gcc-trunk", date) for date in ("20260104", "20260101", "20260103", "20260102")]

    plan = plan_prune(artifacts, {"gcc-trunk": ["x"]}, keep_last=1)

    (family,) = plan.claimed
    assert [a.date for a in family.keep] == ["20260104"]


def test_a_family_that_stopped_building_keeps_its_newest_builds():
    """Rank, not age: unlike a lifecycle rule, an abandoned nightly does not lose everything."""
    artifacts = [artifact("clang-old", date) for date in ("20170422", "20170424", "20170425")]

    plan = plan_prune(artifacts, {"clang-old": ["x"]}, keep_last=2)

    (family,) = plan.claimed
    assert [a.date for a in family.keep] == ["20170424", "20170425"]
    assert [a.date for a in family.remove] == ["20170422"]


def test_keeps_everything_when_there_are_fewer_builds_than_the_limit():
    artifacts = [artifact("gcc-trunk", "20260101"), artifact("gcc-trunk", "20260102")]

    plan = plan_prune(artifacts, {"gcc-trunk": ["x"]}, keep_last=5)

    (family,) = plan.claimed
    assert family.remove == ()
    assert len(family.keep) == 2


def test_counts_dates_not_objects():
    """Two artifacts sharing a date are one build; keeping N dates keeps both of them."""
    artifacts = [
        DatedArtifact(date="20260101", key="opt/x-20260101.tar.xz", family="x", size=1),
        DatedArtifact(date="20260102", key="opt/x-20260102.tar.xz", family="x", size=1),
        DatedArtifact(date="20260102", key="opt/x-20260102.tar.gz", family="x", size=1),
    ]

    plan = plan_prune(artifacts, {"x": ["x"]}, keep_last=1)

    (family,) = plan.claimed
    assert [a.key for a in family.keep] == ["opt/x-20260102.tar.gz", "opt/x-20260102.tar.xz"]
    assert [a.key for a in family.remove] == ["opt/x-20260101.tar.xz"]


def test_unclaimed_families_are_reported_and_never_removed():
    artifacts = [artifact("gcc-trunk", "20260101"), *[artifact("mystery", d) for d in ("20170101", "20170102")]]

    plan = plan_prune(artifacts, {"gcc-trunk": ["x"]}, keep_last=1)

    assert [family.family for family in plan.unclaimed] == ["mystery"]
    (unclaimed,) = plan.unclaimed
    assert unclaimed.remove == ()
    assert len(unclaimed.keep) == 2
    assert plan.to_remove == ()


def test_reports_claims_with_nothing_in_s3():
    plan = plan_prune([artifact("gcc-trunk", "20260101")], {"gcc-trunk": ["x"], "never-built": ["y"]}, keep_last=1)

    assert plan.claimed_without_artifacts == ("never-built",)


def test_totals_cover_only_what_would_be_removed():
    artifacts = [
        artifact("gcc-trunk", "20260101", size=100),
        artifact("gcc-trunk", "20260102", size=200),
        artifact("unclaimed", "20260101", size=4000),
    ]

    plan = plan_prune(artifacts, {"gcc-trunk": ["x"]}, keep_last=1)

    assert plan.bytes_to_remove == 100
    assert len(plan.to_remove) == 1


def test_refuses_to_keep_nothing():
    with pytest.raises(ValueError, match="at least 1"):
        plan_prune([artifact("gcc-trunk", "20260101")], {"gcc-trunk": ["x"]}, keep_last=0)


def test_refuses_to_plan_without_claims():
    """If the YAML yielded no nightlies, everything would look unclaimed: that is a bug, not a cull."""
    with pytest.raises(ValueError, match="refusing"):
        plan_prune([artifact("gcc-trunk", "20260101")], {}, keep_last=5)


def test_newest_date_spans_kept_and_removed():
    artifacts = [artifact("gcc-trunk", date) for date in ("20260101", "20260102", "20260103")]

    plan = plan_prune(artifacts, {"gcc-trunk": ["x"]}, keep_last=1)

    (family,) = plan.claimed
    assert family.newest_date == "20260103"


def test_built_since_separates_live_families_from_relics():
    plan = plan_prune(
        [artifact("live", "20260601"), artifact("relic", "20170101")], {"live": ["x"], "relic": ["y"]}, keep_last=5
    )

    live, relic = plan.claimed
    cutoff = date(2026, 5, 15)
    assert live.built_since(cutoff)
    assert not relic.built_since(cutoff)
