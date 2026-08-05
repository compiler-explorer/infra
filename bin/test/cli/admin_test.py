from __future__ import annotations

import pytest
from botocore.exceptions import ClientError
from lib.cli.admin import delete_ignoring_failures


def _raiser(code: str):
    def delete(**_kwargs):
        raise ClientError({"Error": {"Code": code, "Message": "boom"}}, "DeleteSnapshot")

    return delete


def test_success_counts_no_failures():
    assert delete_ignoring_failures("snap-1", lambda **_kwargs: None) == 0


def test_already_gone_errors_are_tolerated():
    assert delete_ignoring_failures("ami-1", _raiser("InvalidAMIID.Unavailable")) == 0
    assert delete_ignoring_failures("ami-1", _raiser("InvalidAMIID.NotFound")) == 0
    assert delete_ignoring_failures("snap-1", _raiser("InvalidSnapshot.NotFound")) == 0


def test_other_errors_are_counted_and_reported(capsys):
    assert delete_ignoring_failures("snap-1", _raiser("UnauthorizedOperation")) == 1
    assert "Failed to remove snap-1" in capsys.readouterr().err


def test_in_use_is_a_failure_by_default(capsys):
    assert delete_ignoring_failures("snap-1", _raiser("InvalidSnapshot.InUse")) == 1
    assert "Failed to remove snap-1" in capsys.readouterr().err


def test_in_use_is_benign_when_tolerated(capsys):
    assert delete_ignoring_failures("snap-1", _raiser("InvalidSnapshot.InUse"), in_use_ok=True) == 0
    output = capsys.readouterr()
    assert "orphan sweep will retry" in output.out
    assert not output.err


def test_non_client_errors_propagate():
    def delete(**_kwargs):
        raise ValueError("not an AWS error")

    with pytest.raises(ValueError):
        delete_ignoring_failures("snap-1", delete)
