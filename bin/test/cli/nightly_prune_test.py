from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from lib.cli.nightly_prune import claims_from_installables, prune_nightlies


def fake_installable(name: str, prefix: str | None):
    installable = MagicMock()
    installable.name = name
    installable.dated_s3_prefix = prefix
    return installable


def fake_cli_context(installables, dry_run: bool = False):
    context = MagicMock()
    context.get_installables.return_value = installables
    context.installation_context.s3_bucket = "compiler-explorer"
    context.installation_context.s3_dir = "opt"
    context.installation_context.dry_run = dry_run
    return context


def objects_for(*keys: str) -> list[tuple[str, int]]:
    return [(key, 1) for key in keys]


def test_claims_ignore_installables_without_dated_artifacts():
    claims = claims_from_installables([
        fake_installable("compilers/c++/gcc trunk", "gcc-trunk"),
        fake_installable("x", None),
    ])

    assert claims == {"gcc-trunk": ["compilers/c++/gcc trunk"]}


def test_claims_record_every_installable_sharing_a_prefix():
    claims = claims_from_installables([fake_installable("a", "shared"), fake_installable("b", "shared")])

    assert claims == {"shared": ["a", "b"]}


@pytest.fixture(name="s3")
def s3_fixture():
    with (
        patch("lib.cli.nightly_prune.list_s3_objects") as list_objects,
        patch("lib.cli.nightly_prune.delete_s3_objects") as delete_objects,
    ):
        yield list_objects, delete_objects


def test_dry_run_by_default(s3):
    list_objects, delete_objects = s3
    list_objects.return_value = objects_for(
        "opt/gcc-trunk-20260101.tar.xz", "opt/gcc-trunk-20260102.tar.xz", "opt/gcc-trunk-20260103.tar.xz"
    )
    context = fake_cli_context([fake_installable("compilers/c++/gcc trunk", "gcc-trunk")])

    result = CliRunner().invoke(prune_nightlies, ["--keep", "1"], obj=context)

    assert result.exit_code == 0, result.output
    delete_objects.assert_not_called()
    assert "DRY RUN: would remove 2 object(s)" in result.output
    assert "REMOVE opt/gcc-trunk-20260101.tar.xz" in result.output
    assert "KEEP   opt/gcc-trunk-20260103.tar.xz" in result.output


def test_delete_removes_exactly_the_planned_keys(s3):
    list_objects, delete_objects = s3
    list_objects.return_value = objects_for(
        "opt/gcc-trunk-20260101.tar.xz", "opt/gcc-trunk-20260102.tar.xz", "opt/orphan-20260101.tar.xz"
    )
    context = fake_cli_context([fake_installable("compilers/c++/gcc trunk", "gcc-trunk")])

    result = CliRunner().invoke(prune_nightlies, ["--keep", "1", "--delete"], obj=context)

    assert result.exit_code == 0, result.output
    delete_objects.assert_called_once_with("compiler-explorer", ["opt/gcc-trunk-20260101.tar.xz"])


def test_global_dry_run_beats_delete(s3):
    list_objects, delete_objects = s3
    list_objects.return_value = objects_for("opt/gcc-trunk-20260101.tar.xz", "opt/gcc-trunk-20260102.tar.xz")
    context = fake_cli_context([fake_installable("compilers/c++/gcc trunk", "gcc-trunk")], dry_run=True)

    result = CliRunner().invoke(prune_nightlies, ["--keep", "1", "--delete"], obj=context)

    assert result.exit_code == 0, result.output
    delete_objects.assert_not_called()


def test_unclaimed_families_are_shouted_about_but_left_alone(s3):
    list_objects, delete_objects = s3
    list_objects.return_value = objects_for(
        "opt/gcc-trunk-20260101.tar.xz",
        "opt/rust-miri-nightly-20170101.tar.xz",
        "opt/rust-miri-nightly-20170102.tar.xz",
    )
    context = fake_cli_context([fake_installable("compilers/c++/gcc trunk", "gcc-trunk")])

    result = CliRunner().invoke(prune_nightlies, ["--keep", "1", "--delete"], obj=context)

    assert result.exit_code == 0, result.output
    delete_objects.assert_not_called()
    assert "UNCLAIMED: 1 dated families" in result.output
    assert "dormant:" in result.output
    assert "rust-miri-nightly: 2 object(s)" in result.output


def test_an_unclaimed_family_still_being_built_is_called_out(s3):
    """A live build nothing installs is the blind spot that made this command necessary."""
    list_objects, _ = s3
    today = date.today().strftime("%Y%m%d")
    list_objects.return_value = objects_for(
        "opt/gcc-trunk-20260101.tar.xz", f"opt/clad-trunk-clang-20.1.0-{today}.tar.xz"
    )
    context = fake_cli_context([fake_installable("compilers/c++/gcc trunk", "gcc-trunk")])

    result = CliRunner().invoke(prune_nightlies, [], obj=context)

    assert result.exit_code == 0, result.output
    assert "still being built" in result.output
    assert f"clad-trunk-clang-20.1.0: 1 object(s), 1 byte, newest {today}" in result.output


def test_refuses_to_run_without_any_claims(s3):
    list_objects, delete_objects = s3
    list_objects.return_value = objects_for("opt/gcc-trunk-20260101.tar.xz")
    context = fake_cli_context([fake_installable("something", None)])

    result = CliRunner().invoke(prune_nightlies, ["--delete"], obj=context)

    assert result.exit_code != 0
    assert "No nightly installables found" in result.output
    delete_objects.assert_not_called()


def test_keep_must_be_at_least_one(s3):
    _, delete_objects = s3
    context = fake_cli_context([fake_installable("compilers/c++/gcc trunk", "gcc-trunk")])

    result = CliRunner().invoke(prune_nightlies, ["--keep", "0", "--delete"], obj=context)

    assert result.exit_code != 0
    delete_objects.assert_not_called()
