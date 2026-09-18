from unittest.mock import MagicMock, patch

import pytest
from lib.installable.archives import (
    NightlyInstallable,
    RestQueryTarballInstallable,
    TarballInstallable,
    ZipArchiveInstallable,
)
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    return MagicMock(spec=InstallationContext)


def make_installable(fake_context, query: str) -> RestQueryTarballInstallable:
    return RestQueryTarballInstallable(
        fake_context,
        dict(
            context=["compilers", "example"],
            name="nightly",
            url="https://example.com/api/packages",
            query=query,
            dir="example-nightly",
            compression="gz",
        ),
    )


def test_rest_query_resolves_url(fake_context):
    fake_context.fetch_rest_query.return_value = [{"cdn_url": "https://example.com/thing.tar.gz"}]
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert installable.url == "https://example.com/thing.tar.gz"


def test_rest_query_empty_result_gives_no_url(fake_context):
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "[item for item in document if item['ok']]")

    assert not installable.url


def test_rest_query_failure_gives_no_url_instead_of_raising(fake_context):
    """An upstream that stops publishing what we query for must not abort the whole install run."""
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert not installable.url


def test_rest_query_fetch_failure_gives_no_url(fake_context):
    fake_context.fetch_rest_query.side_effect = OSError("connection reset")
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert not installable.url


def test_should_install_false_when_query_fails(fake_context):
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert installable.should_install() is False


def test_stage_raises_when_query_fails(fake_context):
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    with pytest.raises(RuntimeError, match="No installation candidate found"):
        installable.stage(MagicMock(spec=StagingDir))

    fake_context.fetch_url_and_pipe_to.assert_not_called()


def make_nightly(fake_context, config_extras: dict) -> NightlyInstallable:
    config = dict(context=["compilers", "c++"], name="trunk", check_exe="bin/thing --version")
    config.update(config_extras)
    return NightlyInstallable(fake_context, config)


@pytest.fixture(name="available_nightlies")
def available_nightlies_fixture():
    available = {"gcc-trunk": ["20260101"], "6502-c++-trunk": ["20260101"], "ncc-ng-trunk": ["20260101"]}
    with patch("lib.installable.archives.s3_available_compilers", return_value=available):
        yield available


def test_nightly_dated_s3_prefix_defaults_to_the_compiler_name(fake_context, available_nightlies):
    installable = make_nightly(fake_context, dict(context=["compilers", "c++", "gcc"]))

    assert installable.dated_s3_prefix == "gcc-trunk"


def test_nightly_dated_s3_prefix_follows_compiler_name(fake_context, available_nightlies):
    installable = make_nightly(fake_context, dict(compiler_name="ncc-ng-trunk"))

    assert installable.dated_s3_prefix == "ncc-ng-trunk"


def test_nightly_dated_s3_prefix_is_the_key_not_the_url_form(fake_context, available_nightlies):
    """s3_name is a URL path component and may be percent-encoded; the prefix is the literal key."""
    installable = make_nightly(fake_context, dict(compiler_name="6502-c++-trunk", s3_name="6502-c%2B%2B-trunk"))

    assert installable.dated_s3_prefix == "6502-c++-trunk"
    assert installable.s3_path == "6502-c%2B%2B-trunk-20260101"


def test_other_installables_have_no_dated_s3_prefix(fake_context):
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert installable.dated_s3_prefix is None


DIGEST = "ab" * 32


def tarball_config(**extras) -> dict:
    config = dict(
        context=["compilers", "example"],
        name="1.0",
        url="https://example.com/example-1.0.tar.gz",
        dir="example-1.0",
        compression="gz",
    )
    config.update(extras)
    return config


def test_tarball_passes_its_sha256_to_the_fetch(fake_context, tmp_path):
    (tmp_path / "example-1.0").mkdir()
    installable = TarballInstallable(fake_context, tarball_config(sha256=DIGEST.upper()))

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    fake_context.fetch_url_and_pipe_to.assert_called_once()
    assert fake_context.fetch_url_and_pipe_to.call_args.kwargs["sha256"] == DIGEST


def test_tarball_without_sha256_fetches_unverified(fake_context, tmp_path):
    (tmp_path / "example-1.0").mkdir()
    installable = TarballInstallable(fake_context, tarball_config())

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    assert fake_context.fetch_url_and_pipe_to.call_args.kwargs["sha256"] is None


def test_tarball_rejects_a_malformed_sha256_at_load(fake_context):
    with pytest.raises(ValueError, match="expected 64 hex digits"):
        TarballInstallable(fake_context, tarball_config(sha256="not-a-digest"))


def test_zip_passes_its_sha256_to_the_fetch(fake_context, tmp_path):
    (tmp_path / "example-1.0").mkdir()
    installable = ZipArchiveInstallable(
        fake_context,
        dict(
            context=["compilers", "example"],
            name="1.0",
            url="https://example.com/example-1.0.zip",
            dir="example-1.0",
            folder="example-1.0",
            sha256=DIGEST,
        ),
    )

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    assert fake_context.fetch_to.call_args.kwargs["sha256"] == DIGEST
