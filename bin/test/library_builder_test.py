import ast
import io
import os
from logging import Logger
from pathlib import Path
from subprocess import TimeoutExpired
from unittest import mock
from unittest.mock import patch

from lib.installation_context import InstallationContext
from lib.library_build_config import LibraryBuildConfig
from lib.library_builder import BuildStatus, LibraryBuilder
from lib.library_platform import LibraryPlatform

BASE = "https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/"


def create_test_build_config():
    """Create a properly configured LibraryBuildConfig mock for testing."""
    config = mock.Mock(spec=LibraryBuildConfig)
    config.lib_type = "static"
    config.staticliblink = ["testlib"]
    config.sharedliblink = []
    config.description = "Test library"
    config.url = "https://test.url"
    config.build_type = "cmake"
    config.build_fixed_arch = ""
    config.build_fixed_stdlib = ""
    config.package_install = False
    config.copy_files = []
    config.prebuild_script = []
    config.postbuild_script = []
    config.configure_flags = []
    config.extra_cmake_arg = []
    config.extra_make_arg = []
    config.make_targets = []
    config.make_utility = "make"
    config.skip_compilers = []
    config.use_compiler = ""
    return config


def assert_valid_python(python_source: str) -> None:
    try:
        ast.parse(python_source)
    except Exception as e:
        raise AssertionError("Not valid python") from e


def test_can_write_conan_file(requests_mock):
    requests_mock.get(f"{BASE}lang.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    build_config.staticliblink = ["static1", "static2"]
    build_config.sharedliblink = ["shared1", "shared2"]
    build_config.copy_files = [
        'self.copy("*", src="include", dst="include", keep_path=True)',
        'self.copy("*.png", src="resources", dst="resources", keep_path=True)',
    ]
    build_config.description = "description"
    build_config.url = "https://some.url"
    build_config.package_install = False
    lb = LibraryBuilder(
        logger,
        "lang",
        "somelib",
        "target",
        "src-folder",
        install_context,
        build_config,
        False,
        LibraryPlatform.Linux,
        1,
    )
    tio = io.StringIO()
    lb.write_conan_file_to(tio)
    conan_file = tio.getvalue()
    assert_valid_python(conan_file)
    lines = [line.strip() for line in conan_file.split("\n")]
    assert 'name = "somelib"' in lines
    assert 'version = "target"' in lines
    assert 'description = "description"' in lines
    assert 'url = "https://some.url"' in lines
    assert 'self.copy("*", src="include", dst="include", keep_path=True)' in lines
    assert 'self.copy("*.png", src="resources", dst="resources", keep_path=True)' in lines
    assert 'self.copy("libstatic1*.a", dst="lib", keep_path=False)' in lines
    assert 'self.copy("libstatic2*.a", dst="lib", keep_path=False)' in lines
    assert 'self.copy("libshared1*.so*", dst="lib", keep_path=False)' in lines
    assert 'self.copy("libshared2*.so*", dst="lib", keep_path=False)' in lines
    assert (
        'self.cpp_info.libs = ["static1","static2","static1d","static2d","shared1","shared2","shared1d","shared2d"]'
        in lines
    )


def test_get_toolchain_path_from_options_gcc_toolchain(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    options = "--gcc-toolchain=/opt/gcc-11 -O2"
    result = builder.getToolchainPathFromOptions(options)
    assert result == "/opt/gcc-11"


def test_get_toolchain_path_from_options_gxx_name(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    options = "--gxx-name=/opt/gcc/bin/g++ -std=c++17"
    result = builder.getToolchainPathFromOptions(options)
    assert result == "/opt/gcc"


def test_get_toolchain_path_from_options_none(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    options = "-O2 -std=c++17"
    result = builder.getToolchainPathFromOptions(options)
    assert result is False


def test_get_sysroot_path_from_options(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    options = "--sysroot=/opt/sysroot -O2"
    result = builder.getSysrootPathFromOptions(options)
    assert result == "/opt/sysroot"


def test_get_std_ver_from_options(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    options = "-std=c++17 -O2"
    result = builder.getStdVerFromOptions(options)
    assert result == "c++17"


def test_get_std_lib_from_options(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    options = "-stdlib=libc++ -O2"
    result = builder.getStdLibFromOptions(options)
    assert result == "libc++"


def test_get_target_from_options(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    options = "-target x86_64-linux-gnu -O2"
    result = builder.getTargetFromOptions(options)
    assert result == "x86_64-linux-gnu"


def test_replace_optional_arg_with_value(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    arg = "cmake -DARCH=%arch% -DBUILD=%buildtype%"
    result = builder.replace_optional_arg(arg, "arch", "x86_64")
    assert result == "cmake -DARCH=x86_64 -DBUILD=%buildtype%"


def test_replace_optional_arg_no_value(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    arg = "cmake %arch?% -DBUILD=%buildtype%"
    result = builder.replace_optional_arg(arg, "arch", "")
    assert not result


def test_expand_make_arg(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    arg = "-DARCH=%arch% -DBUILD=%buildtype% -DSTD=%stdver%"
    result = builder.expand_make_arg(arg, "gcc", "Debug", "x86_64", "c++17", "libstdc++")
    assert result == "-DARCH=x86_64 -DBUILD=Debug -DSTD=c++17"


@patch("subprocess.check_output")
def test_get_conan_hash_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    mock_subprocess.return_value = b"conanfile.py: ID: abc123def456\nOther output"
    builder.current_buildparameters = ["-s", "os=Linux"]

    result = builder.get_conan_hash("/tmp/buildfolder")

    assert result == "abc123def456"
    mock_subprocess.assert_called_once_with(
        ["conan", "info", "-r", "ceserver", "."] + builder.current_buildparameters, cwd="/tmp/buildfolder"
    )


@patch("subprocess.call")
def test_execute_build_script_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    mock_subprocess.return_value = 0

    result = builder.executebuildscript("/tmp/buildfolder")

    assert result == BuildStatus.Ok
    mock_subprocess.assert_called_once_with(["./cebuild.sh"], cwd="/tmp/buildfolder", timeout=600)


@patch("subprocess.call")
def test_execute_build_script_timeout(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    mock_subprocess.side_effect = TimeoutExpired("cmd", 600)

    result = builder.executebuildscript("/tmp/buildfolder")

    assert result == BuildStatus.TimedOut


@patch("lib.library_builder.get_ssm_param")
def test_conanproxy_login_success(mock_get_ssm, requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    mock_get_ssm.return_value = "test_password"

    mock_response = mock.Mock()
    mock_response.ok = True
    mock_response.content = b'{"token": "test_token"}'

    with patch.object(builder.http_session, "post", return_value=mock_response):
        builder.conanproxy_login()

    assert builder.conanserverproxy_token == "test_token"
    mock_get_ssm.assert_called_once_with("/compiler-explorer/conanpwd")


@patch("lib.library_builder.get_ssm_param")
def test_conanproxy_login_with_env_var(mock_get_ssm, requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    mock_response = mock.Mock()
    mock_response.ok = True
    mock_response.content = b'{"token": "test_token"}'

    with patch.dict(os.environ, {"CONAN_PASSWORD": "env_password"}):
        with patch.object(builder.http_session, "post", return_value=mock_response):
            builder.conanproxy_login()

    # Should use env var, not SSM
    mock_get_ssm.assert_not_called()


def test_does_compiler_support_fixed_target_match(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    result = builder.does_compiler_support("/usr/bin/gcc", "gcc", "x86_64-linux-gnu", "-target x86_64-linux-gnu", "")
    assert result is True


def test_does_compiler_support_fixed_target_mismatch(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    result = builder.does_compiler_support("/usr/bin/gcc", "gcc", "x86", "-target x86_64-linux-gnu", "")
    assert result is False


def test_script_env_linux(requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    result = builder.script_env("CC", "/usr/bin/gcc")
    assert result == 'export CC="/usr/bin/gcc"\n'


@patch("glob.glob")
def test_count_headers(mock_glob, requests_mock):
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )

    mock_glob.side_effect = [
        ["/tmp/build/header1.h", "/tmp/build/header2.h"],  # *.h files
        ["/tmp/build/header3.hpp"],  # *.hpp files
    ]

    result = builder.countHeaders(Path("/tmp/build"))

    assert result == 3
    assert mock_glob.call_count == 2
