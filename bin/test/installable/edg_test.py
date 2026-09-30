from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from lib.installable.edg import EdgNightlyInstallable, EdgS3TarballInstallable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    context = MagicMock(spec=InstallationContext)
    context.destination = Path("/opt/compiler-explorer")
    return context


def with_backend(installable):
    installable.depends = [MagicMock(install_path="gcc-16.1.0")]
    return installable


def make_release(fake_context, compiler_type: str) -> EdgS3TarballInstallable:
    return with_backend(
        EdgS3TarballInstallable(
            fake_context,
            dict(
                context=["compilers", "c++", "edgcpp"],
                name=f"7.0-{compiler_type}-16",
                compiler_type=compiler_type,
                macro_output_dir="base/lib",
                s3_path_prefix="edg-7.0",
                untar_dir=f"edg-7.0/{compiler_type}",
                path_name=f"edg-7.0-{compiler_type}-16",
            ),
        )
    )


@pytest.fixture(name="available_nightlies")
def available_nightlies_fixture():
    with patch("lib.installable.archives.s3_available_compilers", return_value={"edg-trunk": ["20260930"]}):
        yield


def make_nightly(fake_context, compiler_type: str) -> EdgNightlyInstallable:
    return with_backend(
        EdgNightlyInstallable(
            fake_context,
            dict(
                context=["compilers", "c++", "nightly", "edgcpp"],
                name=f"trunk-{compiler_type}",
                compiler_type=compiler_type,
                macro_output_dir="base/lib",
                compiler_name="edg-trunk",
                path_name_prefix=f"edg-trunk-{compiler_type}",
            ),
        )
    )


def test_release_fetches_the_shared_tarball_from_opt(fake_context):
    installable = make_release(fake_context, "gcc")

    assert installable.s3_path == "edg-7.0.tar.xz"
    assert installable.install_path == "edg-7.0-gcc-16"


@patch("lib.installable.edg.subprocess")
def test_release_gcc_mode_uses_the_bundled_tools(mock_subprocess, fake_context, tmp_path):
    mock_subprocess.check_output.return_value = b"160100\n"
    (tmp_path / "edg-7.0" / "gcc").mkdir(parents=True)
    installable = make_release(fake_context, "gcc")

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    tools = tmp_path / "edg-7.0" / "tools"
    scrapes = [call.args[0] for call in mock_subprocess.check_output.call_args_list]
    assert [scrape[0] for scrape in scrapes] == [str(tools / "edg-scrape-compiler")] * 3
    assert scrapes[0][1] == "--compiler-path=/opt/compiler-explorer/gcc-16.1.0/bin/gcc"
    macro_gen = mock_subprocess.check_call.call_args
    assert macro_gen.args[0][:2] == ["bash", str(tools / "make_predef_macro_table")]
    assert macro_gen.kwargs["cwd"] == tmp_path / "edg-7.0" / "gcc" / "base" / "lib"

    shim = (tmp_path / "edg-7.0" / "gcc" / "eccp-scripts" / "eccp-gcc").read_text()
    assert 'EDG_INSTALL_DIR="/opt/compiler-explorer/edg-7.0-gcc-16"' in shim
    assert 'EDG_CPFE_DEFAULT_OPTIONS="--gnu 160100"' in shim


@patch("lib.installable.edg.subprocess")
def test_release_default_mode_needs_no_tools(mock_subprocess, fake_context, tmp_path):
    (tmp_path / "edg-7.0" / "default").mkdir(parents=True)
    installable = make_release(fake_context, "default")

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    mock_subprocess.check_output.assert_not_called()
    mock_subprocess.check_call.assert_not_called()
    assert (tmp_path / "edg-7.0" / "default" / "eccp-scripts" / "eccp-default").exists()


def test_nightly_modes_share_one_tarball_but_install_apart(fake_context, available_nightlies):
    gcc = make_nightly(fake_context, "gcc")
    default = make_nightly(fake_context, "default")

    assert gcc.s3_path == default.s3_path == "edg-trunk-20260930"
    assert gcc.dated_s3_prefix == default.dated_s3_prefix == "edg-trunk"
    assert gcc.local_path == "edg-trunk-20260930/gcc"
    assert gcc.install_path == "edg-trunk-gcc-20260930"
    assert default.install_path == "edg-trunk-default-20260930"
    assert gcc.path_name_symlink == "edg-trunk-gcc"


@patch("lib.installable.edg.subprocess")
def test_nightly_shim_points_at_the_dated_install(mock_subprocess, fake_context, available_nightlies, tmp_path):
    (tmp_path / "edg-trunk-20260930" / "default").mkdir(parents=True)
    installable = make_nightly(fake_context, "default")

    installable.stage(MagicMock(spec=StagingDir, path=tmp_path))

    shim = (tmp_path / "edg-trunk-20260930" / "default" / "eccp-scripts" / "eccp-default").read_text()
    assert 'EDG_INSTALL_DIR="/opt/compiler-explorer/edg-trunk-default-20260930"' in shim


@pytest.mark.parametrize(
    "current, expected",
    [("edg-trunk-gcc-20260929", True), ("edg-trunk-gcc-20260930", False)],
)
def test_nightly_should_install_compares_the_install_not_the_tarball_dir(
    fake_context, available_nightlies, current, expected
):
    fake_context.get_current_link_target.return_value = Path(current)
    installable = make_nightly(fake_context, "gcc")

    assert installable.should_install() is expected
