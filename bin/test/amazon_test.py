from unittest.mock import patch

import pytest
from lib.amazon import delete_s3_objects, list_s3_artifacts, list_s3_objects


def test_list_s3_objects_yields_keys_and_sizes():
    pages = [
        {"KeyCount": 2, "Contents": [{"Key": "opt/a.tar.xz", "Size": 1}, {"Key": "opt/b.tar.xz", "Size": 2}]},
        {"KeyCount": 0},
    ]
    with patch("lib.amazon.anon_s3_client") as client:
        client.get_paginator.return_value.paginate.return_value = pages

        assert list(list_s3_objects("bucket", "opt/")) == [("opt/a.tar.xz", 1), ("opt/b.tar.xz", 2)]


def test_list_s3_artifacts_still_yields_just_keys():
    pages = [{"KeyCount": 1, "Contents": [{"Key": "opt/a.tar.xz", "Size": 1}]}]
    with patch("lib.amazon.anon_s3_client") as client:
        client.get_paginator.return_value.paginate.return_value = pages

        assert list(list_s3_artifacts("bucket", "opt/")) == ["opt/a.tar.xz"]


def test_delete_s3_objects_batches_at_the_api_limit():
    keys = [f"opt/thing-{index}.tar.xz" for index in range(1001)]
    with patch("lib.amazon.s3_client") as client:
        client.delete_objects.return_value = {}
        delete_s3_objects("bucket", keys)

    batches = [call.kwargs["Delete"]["Objects"] for call in client.delete_objects.call_args_list]
    assert [len(batch) for batch in batches] == [1000, 1]
    assert [entry["Key"] for batch in batches for entry in batch] == keys


def test_delete_s3_objects_does_nothing_when_given_nothing():
    with patch("lib.amazon.s3_client") as client:
        delete_s3_objects("bucket", [])

    client.delete_objects.assert_not_called()


def test_delete_s3_objects_raises_on_partial_failure():
    with patch("lib.amazon.s3_client") as client:
        client.delete_objects.return_value = {"Errors": [{"Key": "opt/a.tar.xz", "Message": "AccessDenied"}]}

        with pytest.raises(RuntimeError, match="Failed to delete 1 object"):
            delete_s3_objects("bucket", ["opt/a.tar.xz"])
