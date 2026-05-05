from __future__ import annotations

import ast
import io
import os
from logging import Logger
from pathlib import Path
from subprocess import TimeoutExpired
from unittest import mock
from unittest.mock import patch

import pytest
from lib.installation_context import FetchFailure, InstallationContext
from lib.library_build_config import LibraryBuildConfig
from lib.library_builder import BuildStatus, LibraryBuilder, build_timeout, match_conan_settings
from lib.library_platform import LibraryPlatform

BASE = "https://raw.githubusercontent.com/compiler-explorer/compiler-explorer/main/etc/config/"


# Direct unit tests for match_conan_settings -- the matcher logic ported from ceconan.ts.
# These exercise the function in isolation, without the LibraryBuilder/HTTP scaffolding used
# by the get_conan_hash tests further down.

_TARGET_GCC = {
    "os": "Linux",
    "build_type": "Debug",
    "compiler": "gcc",
    "compiler.version": "g141",
    "compiler.libcxx": "libstdc++",
    "arch": "x86_64",
    "stdver": "",
    "flagcollection": "",
}


def _candidate(**overrides):
    base = {**_TARGET_GCC}
    base.update(overrides)
    return base


def test_match_conan_settings_exact():
    assert match_conan_settings(_TARGET_GCC, _candidate()) is True


def test_match_conan_settings_compiler_mismatch():
    assert match_conan_settings(_TARGET_GCC, _candidate(compiler="clang", **{"compiler.version": "clang19"})) is False


def test_match_conan_settings_libcxx_mismatch_real_compiler():
    assert match_conan_settings(_TARGET_GCC, _candidate(**{"compiler.libcxx": "libc++"})) is False


def test_match_conan_settings_arch_mismatch():
    assert match_conan_settings(_TARGET_GCC, _candidate(arch="x86")) is False


def test_match_conan_settings_os_mismatch():
    assert match_conan_settings(_TARGET_GCC, _candidate(os="Windows")) is False


def test_match_conan_settings_stdver_is_wildcard():
    target = {**_TARGET_GCC, "stdver": "c++23"}
    assert match_conan_settings(target, _candidate(stdver="")) is True
    assert match_conan_settings(target, _candidate(stdver="c++17")) is True


def test_match_conan_settings_headeronly_compiler_wildcard():
    headeronly = _candidate(compiler="headeronly", **{"compiler.version": "headeronly"})
    assert match_conan_settings(_TARGET_GCC, headeronly) is True


def test_match_conan_settings_headeronly_bypasses_libcxx_and_arch():
    headeronly = _candidate(
        compiler="headeronly",
        **{"compiler.version": "headeronly", "compiler.libcxx": "", "arch": ""},
    )
    target = {**_TARGET_GCC, "compiler.libcxx": "libc++", "arch": "x86"}
    assert match_conan_settings(target, headeronly) is True


def test_match_conan_settings_cshared_compiler_wildcard():
    cshared = _candidate(compiler="cshared", **{"compiler.version": "cshared"})
    assert match_conan_settings(_TARGET_GCC, cshared) is True


def test_match_conan_settings_cshared_bypasses_libcxx_but_not_arch():
    """Per the TS source: cshared wildcards libcxx; only headeronly wildcards arch."""
    cshared = _candidate(
        compiler="cshared",
        **{"compiler.version": "cshared", "compiler.libcxx": "", "arch": "x86_64"},
    )
    # libcxx mismatch is allowed for cshared
    target_diff_libcxx = {**_TARGET_GCC, "compiler.libcxx": "libc++"}
    assert match_conan_settings(target_diff_libcxx, cshared) is True
    # arch mismatch is NOT allowed for cshared
    target_diff_arch = {**_TARGET_GCC, "arch": "x86"}
    assert match_conan_settings(target_diff_arch, cshared) is False


def test_match_conan_settings_missing_candidate_key_compares_to_empty():
    """A missing key on the candidate side compares as empty string."""
    target = {**_TARGET_GCC, "compiler.libcxx": "libstdc++"}
    candidate = {k: v for k, v in _candidate().items() if k != "compiler.libcxx"}
    assert match_conan_settings(target, candidate) is False
    target_empty = {**_TARGET_GCC, "compiler.libcxx": ""}
    assert match_conan_settings(target_empty, candidate) is True


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
    except SyntaxError as e:
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
        logger, "lang", "somelib", "target", "src-folder", install_context, build_config, False, LibraryPlatform.Linux
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


SEARCH_URL = "https://conan.compiler-explorer.com/v1/conans/testlib/1.0.0/testlib/1.0.0/search"


def _make_builder_with_params(requests_mock, params_overrides=None):
    """Build a LibraryBuilder with current_buildparameters_obj populated for hash matching."""
    requests_mock.get(f"{BASE}cpp.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_test_build_config()
    builder = LibraryBuilder(
        logger, "cpp", "testlib", "1.0.0", "/tmp/source", install_context, build_config, False, LibraryPlatform.Linux
    )
    params = {
        "os": "Linux",
        "buildtype": "Debug",
        "compiler": "gcc",
        "compiler_version": "g141",
        "libcxx": "libstdc++",
        "arch": "x86_64",
        "stdver": "",
        "flagcollection": "",
    }
    if params_overrides:
        params.update(params_overrides)
    for k, v in params.items():
        builder.current_buildparameters_obj[k] = v
    return builder


def test_get_conan_hash_success(requests_mock):
    builder = _make_builder_with_params(requests_mock)
    requests_mock.get(
        SEARCH_URL,
        json={
            "abc123def456": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "gcc",
                    "compiler.version": "g141",
                    "compiler.libcxx": "libstdc++",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            },
            "other_hash": {"settings": {"compiler": "clang", "compiler.version": "clang1400"}},
        },
    )

    result = builder.get_conan_hash("/tmp/buildfolder")

    assert result == "abc123def456"


def test_get_conan_hash_dry_run_returns_none(requests_mock):
    builder = _make_builder_with_params(requests_mock)
    builder.install_context.dry_run = True
    assert builder.get_conan_hash("/tmp/buildfolder") is None


def test_get_conan_hash_empty_search_returns_none(requests_mock):
    builder = _make_builder_with_params(requests_mock)
    requests_mock.get(SEARCH_URL, json={})
    assert builder.get_conan_hash("/tmp/buildfolder") is None


def test_get_conan_hash_404_returns_none(requests_mock):
    builder = _make_builder_with_params(requests_mock)
    requests_mock.get(SEARCH_URL, status_code=404)
    assert builder.get_conan_hash("/tmp/buildfolder") is None


def test_get_conan_hash_500_raises(requests_mock):
    """Non-404 server errors should propagate, not silently degrade."""
    builder = _make_builder_with_params(requests_mock)
    requests_mock.get(SEARCH_URL, status_code=500)
    with pytest.raises(FetchFailure):
        builder.get_conan_hash("/tmp/buildfolder")


def test_get_conan_hash_non_dict_json_raises(requests_mock):
    """Search responses that aren't a JSON object should propagate, not silently degrade."""
    builder = _make_builder_with_params(requests_mock)
    requests_mock.get(SEARCH_URL, json=["not", "an", "object"])
    with pytest.raises(FetchFailure):
        builder.get_conan_hash("/tmp/buildfolder")


def test_get_conan_hash_headeronly_matches_any_compiler(requests_mock):
    builder = _make_builder_with_params(requests_mock)
    requests_mock.get(
        SEARCH_URL,
        json={
            "headeronly_hash": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "headeronly",
                    "compiler.version": "headeronly",
                    "compiler.libcxx": "",
                    "arch": "",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )
    assert builder.get_conan_hash("/tmp/buildfolder") == "headeronly_hash"


def test_get_conan_hash_cshared_matches_any_compiler(requests_mock):
    builder = _make_builder_with_params(requests_mock)
    requests_mock.get(
        SEARCH_URL,
        json={
            "cshared_hash": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "cshared",
                    "compiler.version": "cshared",
                    "compiler.libcxx": "",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )
    assert builder.get_conan_hash("/tmp/buildfolder") == "cshared_hash"


def test_get_conan_hash_stdver_is_wildcard(requests_mock):
    builder = _make_builder_with_params(requests_mock, {"stdver": "c++23"})
    requests_mock.get(
        SEARCH_URL,
        json={
            "h": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "gcc",
                    "compiler.version": "g141",
                    "compiler.libcxx": "libstdc++",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )
    assert builder.get_conan_hash("/tmp/buildfolder") == "h"


def test_get_conan_hash_libcxx_mismatch_returns_none(requests_mock):
    builder = _make_builder_with_params(requests_mock, {"libcxx": "libstdc++"})
    requests_mock.get(
        SEARCH_URL,
        json={
            "h": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "gcc",
                    "compiler.version": "g141",
                    "compiler.libcxx": "libc++",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )
    assert builder.get_conan_hash("/tmp/buildfolder") is None


def test_get_conan_hash_caches_search_response(requests_mock):
    builder = _make_builder_with_params(requests_mock)
    matcher = requests_mock.get(
        SEARCH_URL,
        json={
            "h": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "gcc",
                    "compiler.version": "g141",
                    "compiler.libcxx": "libstdc++",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )

    builder.get_conan_hash("/tmp/build1")
    builder.get_conan_hash("/tmp/build2")

    assert matcher.call_count == 1


@patch("subprocess.check_call")
def test_upload_builds_invalidates_search_cache(mock_subprocess, requests_mock):
    builder = _make_builder_with_params(requests_mock)
    matcher = requests_mock.get(
        SEARCH_URL,
        json={
            "h": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "gcc",
                    "compiler.version": "g141",
                    "compiler.libcxx": "libstdc++",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )
    builder.needs_uploading = 1

    builder.get_conan_hash("/tmp/build1")
    builder.upload_builds()
    builder.get_conan_hash("/tmp/build2")

    assert matcher.call_count == 2


@patch("subprocess.check_call")
def test_set_as_uploaded_first_time_does_not_raise(mock_subprocess, requests_mock):
    """Regression test: set_as_uploaded must not raise on a never-before-uploaded build.

    Reproduces the bug where get_conan_hash was called BEFORE upload_builds, so the
    search response (which only includes already-uploaded packages) returned None.
    """
    builder = _make_builder_with_params(requests_mock)
    builder.conanserverproxy_token = "test-token"

    matched_settings = {
        "os": "Linux",
        "build_type": "Debug",
        "compiler": "gcc",
        "compiler.version": "g141",
        "compiler.libcxx": "libstdc++",
        "arch": "x86_64",
        "stdver": "",
        "flagcollection": "",
    }
    # First search call (from get_build_annotations) returns empty: package not yet uploaded.
    # After upload_builds invalidates the cache, the second search call returns our package.
    requests_mock.get(SEARCH_URL, [{"json": {}}, {"json": {"freshly_uploaded_hash": {"settings": matched_settings}}}])
    requests_mock.post(
        "https://conan.compiler-explorer.com/annotations/testlib/1.0.0/freshly_uploaded_hash",
        json={"ok": True},
    )

    builder.needs_uploading = 1
    builder.current_commit_hash = "abc123"

    builder.set_as_uploaded("/tmp/buildfolder")

    mock_subprocess.assert_called()


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
    mock_subprocess.assert_called_once_with(["./cebuild.sh"], cwd="/tmp/buildfolder", timeout=build_timeout)


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
