"""Tests for ssh helpers."""

import subprocess
from unittest.mock import patch

import pytest
from lib.ssh import DEFAULT_SSH_USER, exec_remote, ssh_target_for, ssh_user_for


class FakeInstance:
    def __init__(self, ssh_user: str | None = None):
        if ssh_user is not None:
            self.ssh_user = ssh_user


def test_ssh_user_for_defaults_to_ubuntu():
    assert ssh_user_for(FakeInstance()) == DEFAULT_SSH_USER


def test_ssh_user_for_uses_instance_override():
    assert ssh_user_for(FakeInstance(ssh_user="Administrator")) == "Administrator"


@patch("lib.ssh.ssh_address_for")
def test_ssh_target_for_combines_user_and_address(mock_address):
    mock_address.return_value = "10.0.0.1"
    assert ssh_target_for(FakeInstance()) == "ubuntu@10.0.0.1"


@patch("lib.ssh.ssh_address_for")
def test_ssh_target_for_uses_override(mock_address):
    mock_address.return_value = "10.0.0.2"
    assert ssh_target_for(FakeInstance(ssh_user="Administrator")) == "Administrator@10.0.0.2"


class FakeProcess:
    """Stands in for subprocess.Popen: the first communicate() either times out or returns."""

    def __init__(self, hang: bool, returncode: int = 0, stdout: str = "hello\n"):
        self.hang = hang
        self.returncode = returncode
        self.stdout = stdout
        self.killed = False
        self.timeouts: list[float | None] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def communicate(self, timeout=None):
        self.timeouts.append(timeout)
        if self.hang and not self.killed:
            raise subprocess.TimeoutExpired(cmd="ssh", timeout=timeout)
        return self.stdout, ""

    def kill(self):
        self.killed = True


@patch("lib.ssh.ssh_target_for", return_value="ubuntu@10.0.0.1")
@patch("lib.ssh.subprocess.Popen")
def test_exec_remote_passes_timeout_and_returns_output(mock_popen, _target):
    process = FakeProcess(hang=False)
    mock_popen.return_value = process
    assert exec_remote(FakeInstance(), ["echo", "hello"], timeout=30) == "hello\n"
    assert process.timeouts == [30]
    ssh_args = mock_popen.call_args.kwargs["args"]
    assert "-oServerAliveInterval=15" in ssh_args
    assert "-oServerAliveCountMax=4" in ssh_args


@patch("lib.ssh.ssh_target_for", return_value="ubuntu@10.0.0.1")
@patch("lib.ssh.subprocess.Popen")
def test_exec_remote_timeout_kills_ssh_and_raises(mock_popen, _target):
    process = FakeProcess(hang=True)
    mock_popen.return_value = process
    with pytest.raises(RuntimeError, match="timed out after 30s"):
        exec_remote(FakeInstance(), ["echo", "hello"], timeout=30)
    assert process.killed


@patch("lib.ssh.ssh_target_for", return_value="ubuntu@10.0.0.1")
@patch("lib.ssh.subprocess.Popen")
def test_exec_remote_timeout_with_ignore_errors_returns_empty(mock_popen, _target):
    process = FakeProcess(hang=True)
    mock_popen.return_value = process
    assert not exec_remote(FakeInstance(), ["Test-Path", "x"], ignore_errors=True, timeout=30)
    assert process.killed
