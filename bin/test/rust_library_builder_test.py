from __future__ import annotations

import json
from logging import Logger
from pathlib import Path
from subprocess import TimeoutExpired
from unittest import mock
from unittest.mock import patch

import pytest
from lib.installation_context import InstallationContext
from lib.library_build_config import LibraryBuildConfig
from lib.rust_library_builder import (
    CARGO_MESSAGES_FILE,
    BuildStatus,
    CargoArtifactCollision,
    RustLibraryBuilder,
    cargo_supports_json_messages,
    move_crate_artifacts_to_deps,
)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    result = builder.makebuildhash(
        "rustc-1.70", "-O", "/opt/rust", "Linux", "Debug", "x86_64", "", "", ["flag1", "flag2"]
    )

    assert result.startswith("rustc-1.70_")
    assert len(result) > len("rustc-1.70_")


def test_get_conan_hash_success(requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    builder.current_buildparameters_obj["os"] = "Linux"
    builder.current_buildparameters_obj["buildtype"] = "Debug"
    builder.current_buildparameters_obj["compiler"] = "rustc"
    builder.current_buildparameters_obj["compiler_version"] = "rustc-1.70"
    builder.current_buildparameters_obj["libcxx"] = ""
    builder.current_buildparameters_obj["arch"] = "x86_64"
    builder.current_buildparameters_obj["stdver"] = ""
    builder.current_buildparameters_obj["flagcollection"] = ""

    requests_mock.get(
        "https://conan.compiler-explorer.com/v1/conans/rustlib/1.0.0/rustlib/1.0.0/search",
        json={
            "rust123456": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "rustc",
                    "compiler.version": "rustc-1.70",
                    "compiler.libcxx": "",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )

    result = builder.get_conan_hash("/tmp/buildfolder")

    assert result == "rust123456"


_RUST_FAILED_URL = "https://conan.compiler-explorer.com/failedbuilds/rustlib/1.0.0"


def _make_rust_builder(requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)
    builder.current_buildparameters_obj["compiler"] = "rustc"
    builder.current_buildparameters_obj["compiler_version"] = "rustc-1.70"
    builder.current_buildparameters_obj["arch"] = "x86_64"
    builder.current_buildparameters_obj["libcxx"] = ""
    return builder


def _rust_failed_record(**overrides):
    base = {
        "compiler": "rustc",
        "compiler_version": "rustc-1.70",
        "arch": "x86_64",
        "libcxx": "",
        "compiler_flags": "release",
        "commithash": "any",
    }
    base.update(overrides)
    return base


def test_rust_has_failed_before_overrides_flagcollection_from_build_method(requests_mock):
    builder = _make_rust_builder(requests_mock)
    requests_mock.get(_RUST_FAILED_URL, json=[_rust_failed_record(compiler_flags="release")])
    assert builder.has_failed_before({"build_method": "release"}) is True
    assert builder.has_failed_before({"build_method": "debug"}) is False


def test_rust_has_failed_before_caches_response(requests_mock):
    builder = _make_rust_builder(requests_mock)
    matcher = requests_mock.get(_RUST_FAILED_URL, json=[_rust_failed_record(compiler_flags="release")])
    builder.has_failed_before({"build_method": "release"})
    builder.has_failed_before({"build_method": "release"})
    assert matcher.call_count == 1


def test_rust_has_failed_before_matches_regardless_of_commithash(requests_mock):
    builder = _make_rust_builder(requests_mock)
    requests_mock.get(_RUST_FAILED_URL, json=[_rust_failed_record(compiler_flags="release", commithash="ancient")])
    assert builder.has_failed_before({"build_method": "release"}) is True


_RUST_SEARCH_URL = "https://conan.compiler-explorer.com/v1/conans/rustlib/1.0.0/rustlib/1.0.0/search"
_RUST_ANNOTATIONS_URL = "https://conan.compiler-explorer.com/annotations/rustlib/1.0.0"


def test_rust_is_already_uploaded_uses_bulk_annotations(requests_mock):
    builder = _make_rust_builder(requests_mock)
    builder.current_buildparameters_obj["os"] = "Linux"
    builder.current_buildparameters_obj["buildtype"] = "Debug"
    builder.current_buildparameters_obj["stdver"] = ""
    requests_mock.get(
        _RUST_SEARCH_URL,
        json={
            "rhash": {
                "settings": {
                    "os": "Linux",
                    "build_type": "Debug",
                    "compiler": "rustc",
                    "compiler.version": "rustc-1.70",
                    "compiler.libcxx": "",
                    "arch": "x86_64",
                    "stdver": "",
                    "flagcollection": "",
                }
            }
        },
    )
    matcher = requests_mock.get(
        _RUST_ANNOTATIONS_URL,
        json=[{"buildhash": "rhash", "annotation": {"commithash": "1.0.0"}, "buildinfo": {}}],
    )
    # Rust uses target_name as commit_hash, so 1.0.0 matches
    assert builder.is_already_uploaded("/tmp/buildfolder1", "/tmp/source") is True
    assert builder.is_already_uploaded("/tmp/buildfolder2", "/tmp/source") is True
    assert matcher.call_count == 1


@patch("subprocess.call")
def test_execute_build_script_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    mock_subprocess.side_effect = TimeoutExpired("cmd", 600)

    result = builder.executebuildscript("/tmp/buildfolder")

    assert result == BuildStatus.TimedOut


@patch("lib.rust_library_builder.get_ssm_param")
def test_conanproxy_login_success(mock_get_ssm, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    result = builder.get_commit_hash()
    assert result == "1.0.0"  # target_name


@patch("subprocess.call")
def test_execute_conan_script_success(mock_subprocess, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    mock_subprocess.return_value = 1

    result = builder.executeconanscript("/tmp/buildfolder", "x86_64", "")

    assert result == BuildStatus.Failed


def test_count_valid_library_binaries(requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    result = builder.countValidLibraryBinaries("/tmp/buildfolder", "x86_64", "")
    assert result == 1


@patch("os.path.exists")
@patch("os.mkdir")
def test_get_source_folder(mock_mkdir, mock_exists, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock(spec_set=InstallationContext)
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    builder.build_cleanup("/tmp/buildfolder")

    mock_rmtree.assert_called_once_with("/tmp/buildfolder", ignore_errors=True)


@patch("shutil.rmtree")
def test_build_cleanup_dry_run(mock_rmtree, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = True
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

    builder.build_cleanup("/tmp/buildfolder")

    mock_rmtree.assert_not_called()


@patch("shutil.rmtree")
def test_cache_cleanup_normal(mock_rmtree, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    logger = mock.Mock(spec_set=Logger)
    install_context = mock.Mock()
    install_context.dry_run = False
    build_config = create_rust_test_build_config()
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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
    builder = RustLibraryBuilder(logger, "rust", "rustlib", "1.0.0", install_context, build_config)

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


def _write_artifacts(target: Path, artifacts: list[tuple[list[str], list[str]]]) -> Path:
    """Create each artifact file and a cargo JSON message stream reporting them; returns the messages file."""
    lines = [json.dumps({"reason": "build-script-executed", "package_id": "x", "out_dir": str(target)})]
    for kinds, filenames in artifacts:
        for filename in filenames:
            path = target / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(filename)
        lines.append(
            json.dumps({
                "reason": "compiler-artifact",
                "target": {"kind": kinds},
                "filenames": [str(target / f) for f in filenames],
            })
        )
    lines.append(json.dumps({"reason": "build-finished", "success": True}))
    messages = target.parent / CARGO_MESSAGES_FILE
    messages.write_text("\n".join(lines) + "\n")
    return messages


def _files_under(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_move_crate_artifacts_old_layout_is_noop(tmp_path):
    target = tmp_path / "build"
    messages = _write_artifacts(
        target,
        [
            (["lib"], ["debug/deps/liblog-1111.rlib", "debug/deps/liblog-1111.rmeta"]),
            (["proc-macro"], ["debug/deps/libthing_derive-2222.so"]),
            (["custom-build"], ["debug/build/regex-3333/build-script-build"]),
            (["lib"], ["debug/libregex.rlib", "debug/deps/libregex-4444.rmeta"]),
        ],
    )
    before = _files_under(target)

    assert move_crate_artifacts_to_deps(messages, target) == []
    assert _files_under(target) == before


def test_move_crate_artifacts_new_layout_moves_into_deps(tmp_path):
    target = tmp_path / "build"
    messages = _write_artifacts(
        target,
        [
            (["lib"], ["debug/build/log/aaaa/out/liblog-1111.rlib", "debug/build/log/aaaa/out/liblog-1111.rmeta"]),
            (["proc-macro"], ["debug/build/thing_derive/bbbb/out/libthing_derive-2222.so"]),
            (["cdylib"], ["debug/build/plugin/cccc/out/libplugin.so"]),
            (["custom-build"], ["debug/build/ring/dddd/out/build-script-build"]),
            (["lib"], ["debug/libregex.rlib", "debug/build/regex/eeee/out/libregex-4444.rmeta"]),
        ],
    )
    (target / "debug/build/log/aaaa/out/liblog-1111.d").write_text("dep-info")

    moved = move_crate_artifacts_to_deps(messages, target)

    deps = (target / "debug" / "deps").resolve()
    assert sorted(p.name for p in moved) == [
        "liblog-1111.rlib",
        "liblog-1111.rmeta",
        "libregex-4444.rmeta",
        "libthing_derive-2222.so",
    ]
    assert all(p.parent == deps for p in moved)
    assert _files_under(target) == {
        "debug/libregex.rlib",
        "debug/deps/liblog-1111.rlib",
        "debug/deps/liblog-1111.rmeta",
        "debug/deps/libregex-4444.rmeta",
        "debug/deps/libthing_derive-2222.so",
        "debug/build/log/aaaa/out/liblog-1111.d",
        "debug/build/plugin/cccc/out/libplugin.so",
        "debug/build/ring/dddd/out/build-script-build",
    }


def test_move_crate_artifacts_refuses_to_overwrite(tmp_path):
    target = tmp_path / "build"
    messages = _write_artifacts(target, [(["lib"], ["debug/build/log/aaaa/out/liblog-1111.rlib"])])
    existing = target / "debug/deps/liblog-1111.rlib"
    existing.parent.mkdir(parents=True)
    existing.write_text("already here")

    with pytest.raises(CargoArtifactCollision):
        move_crate_artifacts_to_deps(messages, target)

    assert existing.read_text() == "already here"
    assert (target / "debug/build/log/aaaa/out/liblog-1111.rlib").exists()


def test_move_artifacts_to_deps_without_messages_is_ok(tmp_path, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    builder = RustLibraryBuilder(
        mock.Mock(spec_set=Logger),
        "rust",
        "rustlib",
        "1.0.0",
        mock.Mock(spec_set=InstallationContext),
        create_rust_test_build_config(),
    )

    assert builder.move_artifacts_to_deps(str(tmp_path / "build"), str(tmp_path)) == BuildStatus.Ok


def test_move_artifacts_to_deps_collision_fails_build_and_logs(tmp_path, requests_mock):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    builder = RustLibraryBuilder(
        mock.Mock(spec_set=Logger),
        "rust",
        "rustlib",
        "1.0.0",
        mock.Mock(spec_set=InstallationContext),
        create_rust_test_build_config(),
    )
    target = tmp_path / "build"
    _write_artifacts(target, [(["lib"], ["debug/build/log/aaaa/out/liblog-1111.rlib"])])
    (target / "debug/deps").mkdir(parents=True)
    (target / "debug/deps/liblog-1111.rlib").write_text("already here")
    (tmp_path / "buildlog.txt").write_text("cargo output\n")

    assert builder.move_artifacts_to_deps(str(target), str(tmp_path)) == BuildStatus.Failed
    assert "already exists" in (tmp_path / "buildlog.txt").read_text()


@pytest.mark.parametrize(
    "version_output, expected",
    [
        ("cargo 1.100.0 (1234567 2026-11-01)\n", True),
        ("cargo 1.38.0 (23ef9a4ef 2019-08-20)\n", True),
        ("cargo 1.37.0 (9edd08916 2019-08-02)\n", False),
        ("cargo 1.27.0 (1e95190e5 2018-05-27)\n", False),
        ("not cargo\n", False),
    ],
)
def test_cargo_supports_json_messages(version_output, expected):
    with patch("subprocess.check_output", return_value=version_output):
        assert cargo_supports_json_messages("/opt/rust/bin/cargo") is expected


def test_cargo_supports_json_messages_missing_cargo():
    with patch("subprocess.check_output", side_effect=FileNotFoundError):
        assert cargo_supports_json_messages("/opt/rust/bin/cargo") is False


@pytest.mark.parametrize("json_messages", [True, False])
def test_writebuildscript_cargo_line(tmp_path, requests_mock, json_messages):
    requests_mock.get(f"{BASE}rust.amazon.properties", text="")
    build_config = create_rust_test_build_config()
    build_config.prebuild_script = []
    builder = RustLibraryBuilder(
        mock.Mock(spec_set=Logger), "rust", "rustlib", "1.0.0", mock.Mock(spec_set=InstallationContext), build_config
    )
    with patch("lib.rust_library_builder.cargo_supports_json_messages", return_value=json_messages) as supports:
        builder.writebuildscript(
            "/b/build",
            str(tmp_path),
            "r11000",
            "",
            "/opt/rust/bin/rustc",
            "rust",
            "",
            "Linux",
            "Debug",
            "x86_64",
            "",
            "",
            [""],
            "",
            {"build_method": "--all-features", "linker": "/opt/gcc"},
            "/b/log",
        )
    supports.assert_called_once_with("/opt/rust/bin/cargo")

    script = (tmp_path / "build.sh").read_text().splitlines()
    assert 'export RUSTFLAGS="-C linker=/opt/gcc/bin/gcc --cap-lints=warn"' in script
    cargo_line = script[-1]
    if json_messages:
        assert cargo_line == (
            "$CARGO build --all-features --message-format=json-render-diagnostics --target-dir /b/build"
            " > /b/log/cargo-messages.json 2> /b/log/buildlog.txt"
        )
    else:
        assert cargo_line == "$CARGO build --all-features --target-dir /b/build > /b/log/buildlog.txt 2>&1"
