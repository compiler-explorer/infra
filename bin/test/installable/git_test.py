import subprocess
from pathlib import Path
from unittest import mock

import pytest
import logging

from lib.installable.git import GitHubInstallable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    return mock.Mock(spec_set=InstallationContext)


@pytest.fixture(name="staging_path")
def staging_path_fixture(tmp_path) -> Path:
    staging = tmp_path / "staging"
    staging.mkdir()
    return staging


@pytest.fixture(name="fake_remote_repo")
def fake_remote_repo_fixture(tmp_path) -> str:
    repo = tmp_path / "some-remote-repo"
    repo.mkdir()
    subprocess.check_call(["git", "init", str(repo)])
    (repo / "some_file.txt").touch()
    subprocess.check_call(["git", "-C", str(repo), "add", "some_file.txt"])
    subprocess.check_call(["git", "-C", str(repo), "commit", "-minitial"])
    return str(repo)


@pytest.fixture(name="staging_dir")
def staging_dir_fixture(staging_path) -> StagingDir:
    staging = mock.Mock(spec_set=StagingDir)
    staging.path = staging_path
    return staging


def test_git_install_from_scratch(fake_context, staging_dir, tmp_path, fake_remote_repo):
    fake_context.prior_installation = tmp_path / "nonexistent"
    ghi = GitHubInstallable(
        fake_context,
        dict(context=["outer", "inner"], name="fake", domainrepo="", repo=fake_remote_repo, check_file="fake-none"),
    )
    dest = ghi.clone(staging_dir, remote_url=fake_remote_repo, branch=None)
    assert dest.is_relative_to(staging_dir.path)
    assert (dest / "some_file.txt").exists()


def _make_ro(path: Path) -> None:
    for item in path.rglob("*"):
        item.chmod(item.stat().st_mode & 0o555)


def test_git_install_from_prior_version(caplog, fake_context, staging_dir, tmp_path, fake_remote_repo):
    prior_root = tmp_path / "prior_version"
    fake_context.prior_installation = prior_root
    ghi = GitHubInstallable(
        fake_context,
        dict(context=["outer", "inner"], name="fake", domainrepo="", repo=fake_remote_repo, check_file="fake-none"),
    )
    # Fake out an install at prior_version
    original = ghi.clone(staging_dir, remote_url=fake_remote_repo, branch=None)
    prior_version = prior_root / "libs" / "inner" / "fake"
    prior_version.parent.mkdir(parents=True)
    original.replace(prior_version)

    # Make the prior version read only
    _make_ro(prior_version)

    # Update the remote repo
    (Path(fake_remote_repo) / "some_new_file.txt").touch()
    subprocess.check_call(["git", "-C", fake_remote_repo, "add", "some_new_file.txt"])
    subprocess.check_call(["git", "-C", fake_remote_repo, "commit", "-mupdated"])

    # check we updated
    with caplog.at_level(logging.DEBUG):
        new_dest = ghi.clone(staging_dir, remote_url=fake_remote_repo, branch=None)
    assert new_dest.is_relative_to(staging_dir.path)
    assert (new_dest / "some_file.txt").exists()
    assert (new_dest / "some_new_file.txt").exists()

    # Naff way of ensuring we did actually bootstrap
    assert "Bootstrapping from existing branch at" in caplog.text
