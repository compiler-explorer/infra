from __future__ import annotations

from logging import Logger
from subprocess import TimeoutExpired
from unittest import mock
from unittest.mock import patch

from lib.installation_context import InstallationContext
from lib.library_build_config import LibraryBuildConfig
from lib.rust_library_builder import BuildStatus, RustLibraryBuilder

BASE = "https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/"


def create_rust_test_build_config():
    """Create a properly configured LibraryBuildConfig mock for Rust testing."""
    config = mock.Mock(spec=LibraryBuildConfig)
    config.lib_type = "static"
    config.staticliblink = ["rustlib"]
    config.sharedliblink = []
    config.description = "Rust test library"
    config.url = "https://rust.test.url"
    config.build_type = "cargo"
    config.build_fixed_arch = ""
    config.build_fixed_stdlib = ""
    config.package_install = False
    config.copy_files = []
    config.prebuild_script = ["echo 'rust prebuild'"]
    config.postbuild_script = ["echo 'rust postbuild'"]
    config.configure_flags = []
    config.extra_cmake_arg = []
    config.extra_make_arg = []
    config.make_targets = []
    config.make_utility = "make"
    config.skip_compilers = []
    config.use_compiler = ""
    config.domainurl = "https://github.com"
    config.repo = "test/rust-lib"
    return config


def test_makebuildhash(requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    result = builder.makebuildhash(
        "rustc-1.70", "-O", "/opt/rust", "Linux", "Debug", "x86_64", "", "", ["flag1", "flag2"]
    )

    assert result.startswith("rustc-1.70_")
    assert len(result) > len("rustc-1.70_")


@patch("subprocess.check_output")
def test_get_conan_hash_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_subprocess.return_value = b"conanfile.py: ID: rust123456\nOther output"
    builder.current_buildparameters = ["-s", "os=Linux"]

    result = builder.get_conan_hash("/tmp/buildfolder")

    assert result == "rust123456"
    mock_subprocess.assert_called_once_with(
        ["conan", "info", "-r", "ceserver", "."] + builder.current_buildparameters, cwd="/tmp/buildfolder"
    )


@patch("subprocess.call")
def test_execute_build_script_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_subprocess.return_value = 0

    result = builder.executebuildscript("/tmp/buildfolder")

    assert result == BuildStatus.Ok
    mock_subprocess.assert_called_once_with(["./build.sh"], cwd="/tmp/buildfolder", timeout=600)


@patch("subprocess.call")
def test_execute_build_script_timeout(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_subprocess.side_effect = TimeoutExpired("cmd", 600)

    result = builder.executebuildscript("/tmp/buildfolder")

    assert result == BuildStatus.TimedOut


@patch("lib.rust_library_builder.get_ssm_param")
def test_conanproxy_login_success(mock_get_ssm, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_get_ssm.return_value = "rust_password"

    mock_response = mock.Mock()
    mock_response.ok = True
    mock_response.content = b'{"token": "rust_token"}'

    with patch.object(builder.http_session, "post", return_value=mock_response):
        builder.conanproxy_login()

    assert builder.conanserverproxy_token == "rust_token"
    mock_get_ssm.assert_called_once_with("/compiler-explorer/conanpwd")


def test_get_commit_hash(requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    result = builder.get_commit_hash()
    assert result == "1.0.0"  # target_name


@patch("subprocess.call")
def test_execute_conan_script_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_subprocess.return_value = 0

    result = builder.executeconanscript("/tmp/buildfolder", "x86_64", "")

    assert result == BuildStatus.Ok
    mock_subprocess.assert_called_once_with(["./conanexport.sh"], cwd="/tmp/buildfolder")


@patch("subprocess.call")
def test_execute_conan_script_failure(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_subprocess.return_value = 1

    result = builder.executeconanscript("/tmp/buildfolder", "x86_64", "")

    assert result == BuildStatus.Failed


def test_count_valid_library_binaries(requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    result = builder.countValidLibraryBinaries("/tmp/buildfolder", "x86_64", "")
    assert result == 1


@patch("os.path.exists")
@patch("os.mkdir")
def test_get_source_folder(mock_mkdir, mock_exists, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_staging = mock.Mock()
    mock_staging.path = "/tmp/staging"
    mock_exists.return_value = False

    result = builder.get_source_folder(mock_staging)

    expected_path = "/tmp/staging/crate_rustlib_1.0.0"
    assert result == expected_path
    mock_mkdir.assert_called_once_with(expected_path)
    assert expected_path in builder.cached_source_folders


@patch("shutil.rmtree")
def test_build_cleanup_normal(mock_rmtree, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    builder.build_cleanup("/tmp/buildfolder")

    mock_rmtree.assert_called_once_with("/tmp/buildfolder", ignore_errors=True)


@patch("shutil.rmtree")
def test_build_cleanup_dry_run(mock_rmtree, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = True
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    builder.build_cleanup("/tmp/buildfolder")

    mock_rmtree.assert_not_called()


@patch("shutil.rmtree")
def test_cache_cleanup_normal(mock_rmtree, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    builder.cached_source_folders = ["/tmp/folder1", "/tmp/folder2"]
    builder.cache_cleanup()

    assert mock_rmtree.call_count == 2
    mock_rmtree.assert_any_call("/tmp/folder1", ignore_errors=True)
    mock_rmtree.assert_any_call("/tmp/folder2", ignore_errors=True)


@patch("shutil.rmtree")
def test_cache_cleanup_dry_run(mock_rmtree, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = True
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    builder.cached_source_folders = ["/tmp/folder1", "/tmp/folder2"]
    builder.cache_cleanup()

    mock_rmtree.assert_not_called()


@patch("subprocess.check_call")
def test_upload_builds_with_uploads(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    builder.needs_uploading = 2
    builder.upload_builds()

    assert builder.needs_uploading == 0
    assert mock_subprocess.call_count == 2


@patch("subprocess.check_call")
def test_upload_builds_dry_run(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = True
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    builder.needs_uploading = 2
    builder.upload_builds()

    assert builder.needs_uploading == 0
    mock_subprocess.assert_not_called()


@patch("subprocess.check_call")
def test_clone_branch(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config, 1)

    mock_staging = mock.Mock()
    mock_staging.path = "/tmp/staging"

    builder.clone_branch("/tmp/dest", mock_staging)

    assert mock_subprocess.call_count == 2
    mock_subprocess.assert_any_call(
        ["git", "clone", "-q", "https://github.com/test/rust-lib.git", "/tmp/dest"],
        cwd="/tmp/staging",
    )
    mock_subprocess.assert_any_call(
        ["git", "-C", "/tmp/dest", "checkout", "-q", "1.0.0"],
        cwd="/tmp/staging",
    )
