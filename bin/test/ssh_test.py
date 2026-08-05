"""Tests for ssh helpers."""

from unittest.mock import patch

from lib.ssh import DEFAULT_SSH_USER, ssh_target_for, ssh_user_for


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
