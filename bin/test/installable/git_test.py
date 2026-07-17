import logging
import os
import subprocess
from pathlib import Path
from unittest import mock

import pytest
from lib.installable.git import GitHubInstallable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


@pytest.fixture(autouse=True, scope="session")
def _ensure_comprehensive_git_isolation():
    """
    Comprehensive git isolation to prevent test git operations from affecting main repository.
    This is critical when tests run via pre-commit hooks in git worktree environments.
    """
    # Store original values to restore later if needed
    original_git_env = {}

    # Comprehensive list of git environment variables that could cause pollution
    git_env_vars = [
        "GIT_DIR",  # Most critical - tells git where .git directory is
        "GIT_WORK_TREE",  # Working tree location
        "GIT_INDEX_FILE",  # Index file location (already handled but more comprehensive)
        "GIT_OBJECT_DIRECTORY",  # Object storage location
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",  # Alternate object directories
        "GIT_PREFIX",  # Path prefix for operations
        "GIT_COMMON_DIR",  # Critical for git worktrees!
        "GIT_CEILING_DIRECTORIES",  # Repository discovery ceiling
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",  # Cross-filesystem discovery
        "GIT_CONFIG_GLOBAL",  # Global config file
        "GIT_CONFIG_SYSTEM",  # System config file
        "GIT_CONFIG_COUNT",  # Config override count
        "GIT_AUTHOR_NAME",  # Author info
        "GIT_AUTHOR_EMAIL",
        "GIT_AUTHOR_DATE",
        "GIT_COMMITTER_NAME",  # Committer info
        "GIT_COMMITTER_EMAIL",
        "GIT_COMMITTER_DATE",
        "GIT_MERGE_AUTOEDIT",  # Merge behavior
        "GIT_SEQUENCE_EDITOR",  # Sequence editor
        "GIT_EDITOR",  # Editor
        "GIT_PAGER",  # Pager
        "GIT_REFLOG_ACTION",  # Reflog action
        "GIT_TERMINAL_PROMPT",  # Terminal prompting
        "GIT_SSH",  # SSH command
        "GIT_SSH_COMMAND",  # SSH command with args
        "GIT_CURL_VERBOSE",  # Curl verbosity
        "GIT_TRACE",  # Various tracing vars
        "GIT_TRACE_PACK_ACCESS",
        "GIT_TRACE_PACKET",
        "GIT_TRACE_PERFORMANCE",
        "GIT_TRACE_SETUP",
        "GIT_LITERAL_PATHSPECS",  # Pathspec handling
        "GIT_GLOB_PATHSPECS",
        "GIT_NOGLOB_PATHSPECS",
        "GIT_ICASE_PATHSPECS",
    ]

    # Remove or neutralize all git environment variables
    for var in git_env_vars:
        if var in os.environ:
            original_git_env[var] = os.environ[var]
            del os.environ[var]

    # Set critical isolation variables
    # Note: We don't set these to specific values here because each test
    # will set them appropriately in their clean environment

    yield

    # Restore original environment (though tests should be isolated anyway)
    for var, value in original_git_env.items():
        os.environ[var] = value


def _create_completely_isolated_git_env(tmp_path):
    """
    Create a completely isolated git environment for test operations.
    This environment prevents any git operations from affecting the main repository.

    CRITICAL: This explicitly unsets GIT_DIR and GIT_WORK_TREE which are set by git hooks
    and would otherwise cause git commands to operate on the main repository.
    """
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ.get("HOME", "/tmp"),
        "USER": os.environ.get("USER", "test"),
        "TERM": os.environ.get("TERM", "dumb"),
        "LANG": os.environ.get("LANG", "C"),
        # Pre-commit isolation
        "PRE_COMMIT_ALLOW_NO_CONFIG": "1",
        # Git isolation - prevent git from finding parent repositories
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_CEILING_DIRECTORIES": str(tmp_path),
        "GIT_DISCOVERY_ACROSS_FILESYSTEM": "0",
        # Ensure no git hooks interfere
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_EDITOR": ":",
    }

    # CRITICAL: Explicitly do NOT set GIT_DIR or GIT_WORK_TREE
    # These are set by git hooks and would cause operations to affect main repository
    # By not setting them, git will discover the repository from the cwd parameter

    return env


def _assert_git_repo_isolation(repo_path, expected_repo_path):
    """
    Assert that git operations are happening in the expected repository.
    This prevents tests from accidentally operating on the main repository.
    """
    # Create isolated environment for this check
    env = _create_completely_isolated_git_env(Path(expected_repo_path).parent.parent)

    # Check that the git directory is what we expect
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"], cwd=repo_path, capture_output=True, text=True, env=env
        )
        if result.returncode == 0:
            actual_git_dir = Path(repo_path) / result.stdout.strip()
            expected_git_dir = Path(expected_repo_path) / ".git"
            assert actual_git_dir.resolve() == expected_git_dir.resolve(), (
                f"Git isolation failed! Operating on {actual_git_dir} instead of {expected_git_dir}"
            )
    except (subprocess.SubprocessError, OSError) as e:
        # If we can't check, that's also a problem
        pytest.fail(f"Failed to verify git repository isolation: {e}")


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    ctx = mock.Mock(spec=InstallationContext)
    ctx.only_nightly = False
    return ctx


@pytest.fixture(name="fake_context_nightly")
def fake_context_nightly_fixture():
    ctx = mock.Mock(spec=InstallationContext)
    ctx.only_nightly = True
    return ctx


@pytest.fixture(name="staging_path")
def staging_path_fixture(tmp_path) -> Path:
    staging = tmp_path / "staging"
    staging.mkdir()
    return staging


@pytest.fixture(name="fake_remote_repo")
def fake_remote_repo_fixture(tmp_path) -> str:
    repo = tmp_path / "some-remote-repo"
    repo.mkdir()
    env = _create_completely_isolated_git_env(tmp_path)

    subprocess.check_call(["git", "init"], cwd=repo, env=env)
    subprocess.check_call(["git", "config", "--local", "user.email", "nobody@nowhere.not.real"], cwd=repo, env=env)
    subprocess.check_call(["git", "config", "--local", "user.name", "Not a Real Person"], cwd=repo, env=env)
    (repo / "some_file.txt").touch()
    subprocess.check_call(["git", "add", "some_file.txt"], cwd=repo, env=env)
    subprocess.check_call(["git", "commit", "-minitial"], cwd=repo, env=env)

    # CRITICAL: Assert that we created the repository we expect
    _assert_git_repo_isolation(str(repo), str(repo))

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
        dict(
            context=["outer", "inner"],
            name="fake",
            domainrepo="",
            repo=fake_remote_repo,
            check_file="fake-none",
            method="nightlyclone",
        ),
    )
    dest = ghi.clone(staging_dir, remote_url=fake_remote_repo, branch=None)
    assert dest.is_relative_to(staging_dir.path)
    assert (dest / "some_file.txt").exists()


def _make_ro(path: Path) -> None:
    for item in path.rglob("*"):
        item.chmod(item.stat().st_mode & 0o555)


@pytest.fixture(name="previously_installed_ghi")
def previously_installed_ghi_ficture(fake_context, tmp_path, fake_remote_repo, staging_dir):
    prior_root = tmp_path / "prior_version"
    fake_context.prior_installation = fake_context.destination = prior_root
    ghi = GitHubInstallable(
        fake_context,
        dict(
            context=["outer", "inner"],
            name="fake",
            domainrepo="",
            repo=fake_remote_repo,
            check_file="fake-none",
            method="nightlyclone",
        ),
    )
    # Fake out an installation at prior_version
    original = ghi.clone(staging_dir, remote_url=fake_remote_repo, branch=None)
    prior_version = prior_root / "libs" / "inner" / "fake"
    prior_version.parent.mkdir(parents=True)
    original.replace(prior_version)
    # Make the prior version read only
    _make_ro(prior_version)
    return ghi


def test_git_install_from_prior_version(previously_installed_ghi, caplog, fake_remote_repo, staging_dir, tmp_path):
    # CRITICAL: Assert git isolation before making any git operations
    _assert_git_repo_isolation(fake_remote_repo, fake_remote_repo)

    # Update the remote repo
    (Path(fake_remote_repo) / "some_new_file.txt").touch()
    env = _create_completely_isolated_git_env(tmp_path)
    subprocess.check_call(["git", "add", "some_new_file.txt"], cwd=fake_remote_repo, env=env)
    subprocess.check_call(["git", "commit", "-mupdated"], cwd=fake_remote_repo, env=env)

    # Assert isolation is still intact after git operations
    _assert_git_repo_isolation(fake_remote_repo, fake_remote_repo)

    # check we updated
    with caplog.at_level(logging.DEBUG):
        new_dest = previously_installed_ghi.clone(staging_dir, remote_url=fake_remote_repo, branch=None)
    assert new_dest.is_relative_to(staging_dir.path)
    assert (new_dest / "some_file.txt").exists()
    assert (new_dest / "some_new_file.txt").exists()

    # Naff way of ensuring we did actually bootstrap
    assert "Bootstrapping from existing branch at" in caplog.text


def test_should_install_when_not_present(fake_context, tmp_path, fake_remote_repo):
    fake_context.prior_installation = fake_context.destination = tmp_path / "nonexistent"
    ghi = GitHubInstallable(
        fake_context,
        dict(context=["outer", "inner"], name="fake", domainrepo="", repo=fake_remote_repo, check_file="fake-none"),
    )
    assert ghi.should_install()


def test_should_not_install_when_not_nightly(fake_context_nightly, tmp_path, fake_remote_repo):
    fake_context_nightly.prior_installation = fake_context_nightly.destination = tmp_path / "nonexistent"
    ghi = GitHubInstallable(
        fake_context_nightly,
        dict(context=["outer", "inner"], name="fake", domainrepo="", repo=fake_remote_repo, check_file="fake-none"),
    )
    assert not ghi.should_install()


def test_should_install_when_nightly(fake_context_nightly, tmp_path, fake_remote_repo):
    fake_context_nightly.prior_installation = fake_context_nightly.destination = tmp_path / "nonexistent"
    ghi = GitHubInstallable(
        fake_context_nightly,
        dict(
            context=["outer", "inner"],
            name="fake",
            domainrepo="",
            method="nightlyclone",
            repo=fake_remote_repo,
            check_file="fake-none",
        ),
    )
    assert ghi.should_install()


def test_should_not_install_when_present_and_up_to_date(previously_installed_ghi):
    assert not previously_installed_ghi.should_install()


def test_should_install_when_present_but_remote_has_updated(previously_installed_ghi, fake_remote_repo, tmp_path):
    # CRITICAL: Assert git isolation before making any git operations
    _assert_git_repo_isolation(fake_remote_repo, fake_remote_repo)

    # Update the remote repo
    (Path(fake_remote_repo) / "some_new_file.txt").touch()
    env = _create_completely_isolated_git_env(tmp_path)
    subprocess.check_call(["git", "add", "some_new_file.txt"], cwd=fake_remote_repo, env=env)
    subprocess.check_call(["git", "commit", "-mupdated"], cwd=fake_remote_repo, env=env)

    # Assert isolation is still intact after git operations
    _assert_git_repo_isolation(fake_remote_repo, fake_remote_repo)

    assert previously_installed_ghi.should_install()


# test comprehensive git isolation
