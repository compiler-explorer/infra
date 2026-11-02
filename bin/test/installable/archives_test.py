import subprocess
import zipfile
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


def write_zip_to(fd, members: dict[str, str]) -> None:
    with zipfile.ZipFile(fd, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)


def run_for_real(staging: StagingDir, command, cwd=None) -> None:
    subprocess.check_call(command, cwd=str(cwd or staging.path))


def zip_context(members: dict[str, str]) -> MagicMock:
    context = MagicMock(spec=InstallationContext)
    context.fetch_to.side_effect = lambda url, fd, sha256=None: write_zip_to(fd, members)
    context.stage_subdir.side_effect = lambda staging, subdir: (staging.path / subdir).mkdir(
        parents=True, exist_ok=True
    )
    context.stage_command.side_effect = run_for_real
    return context


def test_tarball_with_zip_compression_unzips_into_the_untar_dir(tmp_path):
    context = zip_context({"bin/thing": "binary", "README.txt": "hi"})
    installable = TarballInstallable(
        context, tarball_config(url="https://example.com/example-1.0.zip", compression="zip", create_untar_dir=True)
    )

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    assert (tmp_path / "example-1.0" / "bin" / "thing").read_text() == "binary"
    assert not (tmp_path / "distribution.zip").exists()
    context.fetch_url_and_pipe_to.assert_not_called()


def test_tarball_with_zip_compression_passes_its_sha256_to_the_fetch(tmp_path):
    context = zip_context({"example-1.0/bin/thing": "binary"})
    installable = TarballInstallable(
        context, tarball_config(url="https://example.com/example-1.0.zip", compression="zip", sha256=DIGEST)
    )

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    assert context.fetch_to.call_args.kwargs["sha256"] == DIGEST


@pytest.mark.parametrize("option", [dict(strip_components=1), dict(extract_only="bin")])
def test_tarball_with_zip_compression_rejects_tar_only_options(fake_context, option):
    with pytest.raises(RuntimeError, match="not supported for zip"):
        TarballInstallable(fake_context, tarball_config(compression="zip", **option))


def test_rest_query_with_zip_compression_unzips_the_resolved_url(tmp_path):
    context = zip_context({"bin/thing": "binary"})
    context.fetch_rest_query.return_value = [
        {"tag_name": "nightly-20261102", "assets": [{"name": "thing.zip", "browser_download_url": "https://x/t.zip"}]}
    ]
    installable = RestQueryTarballInstallable(
        context,
        dict(
            context=["compilers", "example"],
            name="trunk",
            url="https://example.com/api/releases",
            query="[a['browser_download_url'] for r in document for a in r['assets']][0]",
            dir="example-trunk",
            compression="zip",
            create_untar_dir=True,
        ),
    )

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    assert context.fetch_to.call_args.args[0] == "https://x/t.zip"
    assert (tmp_path / "example-trunk" / "bin" / "thing").read_text() == "binary"


def test_tarball_with_zip_compression_is_rejected_on_windows(fake_context):
    with patch("lib.installable.archives.is_windows", return_value=True):
        with pytest.raises(RuntimeError, match="use type: ziparchive"):
            TarballInstallable(fake_context, tarball_config(compression="zip"))
