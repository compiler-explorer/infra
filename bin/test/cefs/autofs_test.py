"""Tests for the CEFS autofs program map script."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from lib.cefs.autofs import LOOKUP_SCRIPT_TEMPLATE, make_first_level_map, make_lookup_script
from lib.cefs_manifest import generate_cefs_filename

REPO_ROOT = Path(__file__).resolve().parents[3]
VALID_NAME = "9da642f654bc890a12345678_opt_compiler-explorer_gcc-15.1.0"
MISSING_NAME = "0123456789abcdef01234567_consolidated"


def _setup_common_script() -> str:
    text = (REPO_ROOT / "setup-common.sh").read_text(encoding="utf-8")
    match = re.search(r"cat > /etc/auto\.cefs\.sub << 'EOF'\n(.*?\n)EOF\n", text, re.DOTALL)
    assert match, "could not find the /etc/auto.cefs.sub heredoc in setup-common.sh"
    return match.group(1)


def _run(script: Path, key: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["bash", str(script), key.encode()], capture_output=True, check=False)


def _create_image_if_possible(image_dir: Path, name: str) -> None:
    """Make the name's image exist where the filesystem allows, so that only the name check can reject it."""
    if name == MISSING_NAME or len(name) < 2 or "/" in name or len(name) + len(".sqfs") > 255:
        return
    subdir = image_dir / name[:2]
    subdir.mkdir(parents=True, exist_ok=True)
    (subdir / f"{name}.sqfs").write_bytes(b"")


@pytest.fixture(name="script")
def fixture_script(tmp_path: Path) -> Path:
    image_dir = tmp_path / "cefs-images"
    for name in (VALID_NAME, "abcdef0123456789abcdef01_consolidated"):
        subdir = image_dir / name[:2]
        subdir.mkdir(parents=True, exist_ok=True)
        (subdir / f"{name}.sqfs").write_bytes(b"")
    script = tmp_path / "auto.cefs.sub"
    script.write_text(make_lookup_script(image_dir), encoding="utf-8")
    return script


def test_setup_common_script_matches_ce_install_script():
    assert _setup_common_script() == make_lookup_script(Path("/efs/cefs-images"))


@pytest.mark.parametrize("name", [VALID_NAME, "abcdef0123456789abcdef01_consolidated"])
def test_lookup_script_valid_existing_name(script: Path, name: str):
    result = _run(script, name)
    image_dir = script.parent / "cefs-images"
    expected = f"-fstype=squashfs,loop,nosuid,nodev,ro :{image_dir}/{name[:2]}/{name}.sqfs\n"
    assert result.returncode == 0
    assert result.stdout.decode() == expected


INVALID_NAMES = [
    pytest.param(MISSING_NAME, id="well-formed-but-missing"),
    pytest.param("", id="empty"),
    pytest.param("9da642f654bc890a12345678", id="no-suffix"),
    pytest.param("9da642f654bc890a1234567_x", id="short-hash"),
    pytest.param("9DA642F654BC890A12345678_x", id="uppercase-hash"),
    pytest.param("-" + VALID_NAME, id="leading-dash"),
    pytest.param(VALID_NAME + "\n", id="trailing-newline"),
    pytest.param("9da642f654bc890a12345678_a b", id="embedded-space"),
    pytest.param("9da642f654bc890a12345678_" + "a" * 230, id="255-bytes"),
    *[
        pytest.param(f"9da642f654bc890a12345678_a{char}b", id=f"char-{ord(char):02x}")
        for char in ["\t", "\b", "\x01", "\x7f", ":", "/", "#", "$", "\\", "'", '"', "{", "}", ",", "*", "&"]
    ],
]


@pytest.mark.parametrize("name", INVALID_NAMES)
def test_lookup_script_rejects(script: Path, name: str):
    _create_image_if_possible(script.parent / "cefs-images", name)
    result = _run(script, name)
    assert result.returncode != 0
    assert result.stdout == b""


@pytest.mark.parametrize(
    "operation,path",
    [
        ("install", Path("/opt/compiler-explorer/gcc-15.1.0")),
        ("install", Path("/opt/compiler-explorer/odd name@v1~2,3=4:5?#$")),
        ("convert", Path("/opt/compiler-explorer/arm/gcc-10.2.0.img")),
        ("consolidate", None),
    ],
)
def test_generated_names_pass_lookup_check(operation: str, path: Path | None):
    match = re.search(r"valid_key='([^']*)'", LOOKUP_SCRIPT_TEMPLATE)
    assert match
    name = generate_cefs_filename("0123456789abcdef01234567", operation, path).removesuffix(".sqfs")
    assert re.fullmatch(match.group(1), name)


def _setup_common_first_level_map() -> str:
    text = (REPO_ROOT / "setup-common.sh").read_text(encoding="utf-8")
    match = re.search(r"^\s*(printf .*) > /etc/auto\.cefs$", text, re.MULTILINE)
    assert match, "could not find the /etc/auto.cefs printf in setup-common.sh"
    return subprocess.run(["bash", "-c", match.group(1)], capture_output=True, check=True, text=True).stdout


def test_setup_common_first_level_map_matches_ce_install_map():
    assert _setup_common_first_level_map() == make_first_level_map(Path("/etc/auto.cefs.sub"))


def test_first_level_map_lists_every_two_hex_digit_prefix_once():
    lines = make_first_level_map(Path("/etc/auto.cefs.sub")).splitlines()
    assert lines == [f"{n:02x} -fstype=autofs program:/etc/auto.cefs.sub" for n in range(256)]


def test_first_level_map_has_no_wildcard():
    assert "*" not in make_first_level_map(Path("/etc/auto.cefs.sub"))
