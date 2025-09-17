from __future__ import annotations

from logging import Logger
from subprocess import TimeoutExpired
from unittest import mock
from unittest.mock import patch

from lib.fortran_library_builder import BuildStatus, FortranLibraryBuilder
from lib.installation_context import InstallationContext
from lib.library_build_config import LibraryBuildConfig

BASE = "https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/"


def create_fortran_test_build_config():
    """Create a properly configured LibraryBuildConfig mock for Fortran testing."""
    config = mock.Mock(spec=LibraryBuildConfig)
    config.lib_type = "static"
    config.staticliblink = ["fortranlib"]
    config.sharedliblink = []
    config.description = "Fortran test library"
    config.url = "https://fortran.test.url"
    config.build_type = "fpm"
    config.build_fixed_arch = ""
    config.build_fixed_stdlib = ""
    config.package_install = False
    config.copy_files = []
    config.prebuild_script = ["echo 'fortran prebuild'"]
    config.postbuild_script = ["echo 'fortran postbuild'"]
    config.configure_flags = []
    config.extra_cmake_arg = []
    config.extra_make_arg = []
    config.make_targets = []
    config.make_utility = "make"
    config.skip_compilers = []
    config.use_compiler = ""
    return config


def test_get_toolchain_path_from_options_gcc_toolchain(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    options = "--gcc-toolchain=/opt/gfortran-11 -O2"
    result = builder.getToolchainPathFromOptions(options)
    assert result == "/opt/gfortran-11"


def test_get_toolchain_path_from_options_gxx_name(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    options = "--gxx-name=/opt/gcc/bin/g++ -std=f2008"
    result = builder.getToolchainPathFromOptions(options)
    assert result == "/opt/gcc"


def test_get_toolchain_path_from_options_none(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    options = "-O2 -std=f2008"
    result = builder.getToolchainPathFromOptions(options)
    assert result is False


def test_get_std_ver_from_options(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    options = "-std=f2018 -O2"
    result = builder.getStdVerFromOptions(options)
    assert result == "f2018"


def test_get_std_lib_from_options(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    options = "-stdlib=libgfortran -O2"
    result = builder.getStdLibFromOptions(options)
    assert result == "libgfortran"


def test_get_target_from_options(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    options = "-target aarch64-linux-gnu -O2"
    result = builder.getTargetFromOptions(options)
    assert result == "aarch64-linux-gnu"


def test_replace_optional_arg_with_value(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    arg = "fpm build --arch=%arch% --build=%buildtype%"
    result = builder.replace_optional_arg(arg, "arch", "x86_64")
    assert result == "fpm build --arch=x86_64 --build=%buildtype%"


def test_replace_optional_arg_no_value(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    arg = "fpm build %arch?% --build=%buildtype%"
    result = builder.replace_optional_arg(arg, "arch", "")
    assert not result


def test_expand_make_arg(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    arg = "--arch=%arch% --build=%buildtype% --std=%stdver%"
    result = builder.expand_make_arg(arg, "fortran", "Debug", "x86_64", "f2018", "libgfortran")
    assert result == "--arch=x86_64 --build=Debug --std=f2018"


@patch("subprocess.check_output")
def test_get_conan_hash_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    mock_subprocess.return_value = b"conanfile.py: ID: fortran123456\nOther output"
    builder.current_buildparameters = ["-s", "os=Linux"]

    result = builder.get_conan_hash("/tmp/buildfolder")

    assert result == "fortran123456"
    mock_subprocess.assert_called_once_with(
        ["conan", "info", "-r", "ceserver", "."] + builder.current_buildparameters, cwd="/tmp/buildfolder"
    )


@patch("subprocess.call")
def test_execute_build_script_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    mock_subprocess.return_value = 0

    result = builder.executebuildscript("/tmp/buildfolder")

    assert result == BuildStatus.Ok
    mock_subprocess.assert_called_once_with(
        ["bash", "/tmp/buildfolder/cebuild.sh"], cwd="/tmp/buildfolder", timeout=600
    )


@patch("subprocess.call")
def test_execute_build_script_timeout(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    mock_subprocess.side_effect = TimeoutExpired("cmd", 600)

    result = builder.executebuildscript("/tmp/buildfolder")

    assert result == BuildStatus.TimedOut


@patch("lib.base_library_builder.get_ssm_param")
def test_conanproxy_login_success(mock_get_ssm, requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    mock_get_ssm.return_value = "fortran_password"

    mock_response = mock.Mock()
    mock_response.ok = True
    mock_response.content = b'{"token": "fortran_token"}'

    with patch.object(builder.http_session, "post", return_value=mock_response):
        builder.conanproxy_login()

    assert builder.conanserverproxy_token == "fortran_token"
    mock_get_ssm.assert_called_once_with("/compiler-explorer/conanpwd")


def test_makebuildhash(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    result = builder.makebuildhash(
        "gfortran13", "-O2", "/opt/gcc", "Linux", "Debug", "x86_64", "f2018", "libgfortran", ["flag1", "flag2"]
    )

    assert result.startswith("gfortran13_")
    assert len(result) > len("gfortran13_")


def test_does_compiler_support_fixed_target_match(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    result = builder.does_compiler_support(
        "/usr/bin/gfortran", "fortran", "x86_64-linux-gnu", "-target x86_64-linux-gnu", ""
    )
    assert result is True


def test_does_compiler_support_fixed_target_mismatch(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    result = builder.does_compiler_support("/usr/bin/gfortran", "fortran", "x86", "-target x86_64-linux-gnu", "")
    assert result is False


def test_get_commit_hash_with_git(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    with patch("os.path.exists", return_value=True):
        with patch("subprocess.check_output") as mock_subprocess:
            mock_subprocess.return_value = b"abc1234 Latest fortran commit\n"

            result = builder.get_commit_hash()

            assert result == "abc1234"


def test_get_commit_hash_without_git(requests_mock):
    requests_mock.get(f"{BASE}fortran.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_fortran_test_build_config()
    builder = FortranLibraryBuilder(
        logger, "fortran", "fortranlib", "2.0.0", "/tmp/source", install_context, build_config, False
    )

    with patch("os.path.exists", return_value=False):
        result = builder.get_commit_hash()
        assert result == "2.0.0"  # target_name
