from unittest.mock import MagicMock

import pytest
from lib.installable.archives import RestQueryTarballInstallable
from lib.installation_context import InstallationContext
from lib.staging import StagingDir


@pytest.fixture(name="fake_context")
def fake_context_fixture():
    return MagicMock(spec=InstallationContext)


def make_installable(fake_context, query: str) -> RestQueryTarballInstallable:
    return RestQueryTarballInstallable(
        fake_context,
        dict(
            context=["compilers", "example"],
            name="nightly",
            url="https://example.com/api/packages",
            query=query,
            dir="example-nightly",
            compression="gz",
        ),
    )


def test_rest_query_resolves_url(fake_context):
    fake_context.fetch_rest_query.return_value = [{"cdn_url": "https://example.com/thing.tar.gz"}]
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert installable.url == "https://example.com/thing.tar.gz"


def test_rest_query_empty_result_gives_no_url(fake_context):
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "[item for item in document if item['ok']]")

    assert not installable.url


def test_rest_query_failure_gives_no_url_instead_of_raising(fake_context):
    """An upstream that stops publishing what we query for must not abort the whole install run."""
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert not installable.url


def test_rest_query_fetch_failure_gives_no_url(fake_context):
    fake_context.fetch_rest_query.side_effect = OSError("connection reset")
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert not installable.url


def test_should_install_false_when_query_fails(fake_context):
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    assert installable.should_install() is False


def test_stage_raises_when_query_fails(fake_context):
    fake_context.fetch_rest_query.return_value = []
    installable = make_installable(fake_context, "document[0]['cdn_url']")

    with pytest.raises(RuntimeError, match="No installation candidate found"):
        installable.stage(MagicMock(spec=StagingDir))

    fake_context.fetch_url_and_pipe_to.assert_not_called()
