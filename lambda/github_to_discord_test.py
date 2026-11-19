import base64
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest

import github_to_discord
from github_to_discord import get_body, is_public_repository_event, lambda_handler, signature_is_valid

SECRET = "s3cret"
WEBHOOK = "https://discord.com/api/webhooks/123/token"


def sign(body: bytes, secret: str = SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def make_event(payload: object, github_event: str = "push", signature: str | None = None, **extra_headers) -> dict:
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Event": github_event,
        "X-Hub-Signature-256": signature if signature is not None else sign(body),
        "Content-Type": "application/json",
    }
    headers.update(extra_headers)
    return {"headers": headers, "body": body.decode()}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK)


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"repository": {"private": False}}, True),
        ({"repository": {"private": False, "visibility": "public"}}, True),
        ({"repository": {"private": True}}, False),
        ({"repository": {"private": True, "visibility": "private"}}, False),
        ({"repository": {"private": False, "visibility": "internal"}}, False),
        ({"repository": {}}, False),
        ({"repository": {"private": None}}, False),
        ({"repository": {"private": "false"}}, False),
        ({"repository": {"private": 0}}, False),
        ({"repository": None}, False),
        ({"repository": "compiler-explorer/foo"}, False),
        ({"organization": {"login": "compiler-explorer"}}, False),
        ({}, False),
        ([], False),
        (None, False),
    ],
)
def test_is_public_repository_event(payload, expected):
    assert is_public_repository_event(payload) is expected


def test_signature_valid():
    body = b'{"a": 1}'
    assert signature_is_valid(SECRET, body, sign(body))


@pytest.mark.parametrize("header", [None, "", "sha256=deadbeef", "sha1=abc"])
def test_signature_invalid_header(header):
    assert not signature_is_valid(SECRET, b"{}", header)


def test_signature_wrong_secret():
    body = b"{}"
    assert not signature_is_valid(SECRET, body, sign(body, "other"))


def test_signature_rejects_everything_when_secret_unset():
    body = b"{}"
    assert not signature_is_valid("", body, sign(body, ""))


def test_get_body_handles_base64():
    raw = b'{"x": "y"}'
    assert get_body({"body": base64.b64encode(raw).decode(), "isBase64Encoded": True}) == raw
    assert get_body({"body": raw.decode()}) == raw
    assert get_body({}) == b""


def test_bad_signature_is_rejected_without_forwarding():
    event = make_event({"repository": {"private": False}}, signature="sha256=bad")
    with patch.object(github_to_discord.requests, "post") as post:
        assert lambda_handler(event, None)["statusCode"] == 401
    post.assert_not_called()


def test_missing_secret_rejects_everything(monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET")
    with patch.object(github_to_discord.requests, "post") as post:
        assert lambda_handler(make_event({"repository": {"private": False}}), None)["statusCode"] == 401
    post.assert_not_called()


def test_ping_answers_without_forwarding():
    with patch.object(github_to_discord.requests, "post") as post:
        result = lambda_handler(make_event({"zen": "hi"}, github_event="ping"), None)
    assert result["statusCode"] == 200
    post.assert_not_called()


def test_invalid_json_is_a_bad_request():
    body = b"not json"
    event = {"headers": {"x-hub-signature-256": sign(body), "x-github-event": "push"}, "body": body.decode()}
    with patch.object(github_to_discord.requests, "post") as post:
        assert lambda_handler(event, None)["statusCode"] == 400
    post.assert_not_called()


@pytest.mark.parametrize(
    "payload",
    [
        {"repository": {"private": True, "full_name": "compiler-explorer/ce-security"}},
        {"repository": {"private": False, "visibility": "internal"}},
        {"organization": {"login": "compiler-explorer"}},
        {},
    ],
)
def test_non_public_events_are_dropped(payload):
    with patch.object(github_to_discord.requests, "post") as post:
        result = lambda_handler(make_event(payload), None)
    assert result == {"statusCode": 200, "body": "dropped"}
    post.assert_not_called()


def test_public_event_is_forwarded_verbatim_to_discord_github_endpoint():
    payload = {"repository": {"private": False, "full_name": "compiler-explorer/compiler-explorer"}}
    event = make_event(payload, github_event="issues", **{"X-GitHub-Delivery": "abc-123"})
    with patch.object(github_to_discord.requests, "post", return_value=MagicMock(ok=True, status_code=204)) as post:
        result = lambda_handler(event, None)
    assert result["statusCode"] == 200
    post.assert_called_once()
    args, kwargs = post.call_args
    assert args[0] == WEBHOOK + "/github"
    assert kwargs["data"] == event["body"].encode()
    assert kwargs["headers"]["x-github-event"] == "issues"
    assert kwargs["headers"]["x-github-delivery"] == "abc-123"


@pytest.mark.parametrize(
    "github_event",
    [
        "repository_advisory",
        "secret_scanning_alert",
        "code_scanning_alert",
        "dependabot_alert",
        "team_add",
        "team",
        "member",
        "package",
        "deployment",
        "",
    ],
)
def test_events_not_on_the_allowlist_are_dropped_even_for_public_repos(github_event):
    with patch.object(github_to_discord.requests, "post") as post:
        result = lambda_handler(make_event({"repository": {"private": False}}, github_event=github_event), None)
    assert result == {"statusCode": 200, "body": "dropped"}
    post.assert_not_called()


def test_issue_transferred_to_private_repo_is_dropped():
    payload = {
        "action": "transferred",
        "repository": {"private": False},
        "changes": {"new_repository": {"private": True, "full_name": "compiler-explorer/ce-security"}},
    }
    with patch.object(github_to_discord.requests, "post") as post:
        result = lambda_handler(make_event(payload, github_event="issues"), None)
    assert result["body"] == "dropped"
    post.assert_not_called()


def test_issue_transferred_to_public_repo_is_forwarded():
    payload = {
        "action": "transferred",
        "repository": {"private": False},
        "changes": {"new_repository": {"private": False}},
    }
    with patch.object(github_to_discord.requests, "post", return_value=MagicMock(ok=True)) as post:
        lambda_handler(make_event(payload, github_event="issues"), None)
    post.assert_called_once()


def test_review_request_naming_a_team_is_dropped():
    payload = {"action": "review_requested", "repository": {"private": False}, "requested_team": {"name": "secret"}}
    with patch.object(github_to_discord.requests, "post") as post:
        result = lambda_handler(make_event(payload, github_event="pull_request"), None)
    assert result["body"] == "dropped"
    post.assert_not_called()


def test_network_error_returns_502_and_does_not_log_the_webhook_url(caplog):
    # requests' exception text embeds the URL, which contains the Discord token.
    error = github_to_discord.requests.ConnectionError(f"Max retries exceeded with url: {WEBHOOK}/github")
    with patch.object(github_to_discord.requests, "post", side_effect=error):
        result = lambda_handler(make_event({"repository": {"private": False}}), None)
    assert result["statusCode"] == 502
    assert "token" not in caplog.text
    assert "ConnectionError" in caplog.text


@pytest.mark.parametrize("header", ["sha256=\u00e9\u00e9", "\U0001f4a5"])
def test_non_ascii_signature_header_is_rejected_cleanly(header):
    assert not signature_is_valid(SECRET, b"{}", header)
    event = make_event({"repository": {"private": False}}, signature=header)
    assert lambda_handler(event, None)["statusCode"] == 401


def test_base64_body_end_to_end_with_lowercase_headers():
    body = json.dumps({"repository": {"private": False}}).encode()
    event = {
        "headers": {
            "x-github-event": "push",
            "x-hub-signature-256": sign(body),
            "content-type": "application/json",
        },
        "body": base64.b64encode(body).decode(),
        "isBase64Encoded": True,
    }
    with patch.object(github_to_discord.requests, "post", return_value=MagicMock(ok=True)) as post:
        assert lambda_handler(event, None)["statusCode"] == 200
    assert post.call_args.kwargs["data"] == body
    assert post.call_args.kwargs["headers"]["content-type"] == "application/json"
    assert "x-github-delivery" not in post.call_args.kwargs["headers"]


def test_malformed_base64_body_is_never_forwarded():
    # Decodes to an empty body; even with a matching signature there is nothing publishable in it.
    event = {
        "headers": {"x-hub-signature-256": sign(b""), "x-github-event": "push"},
        "body": "!!!not base64!!!",
        "isBase64Encoded": True,
    }
    with patch.object(github_to_discord.requests, "post") as post:
        assert lambda_handler(event, None)["statusCode"] == 400
    post.assert_not_called()


def test_trailing_slash_on_webhook_url_is_tolerated(monkeypatch):
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", WEBHOOK + "/")
    with patch.object(github_to_discord.requests, "post", return_value=MagicMock(ok=True)) as post:
        lambda_handler(make_event({"repository": {"private": False}}), None)
    assert post.call_args[0][0] == WEBHOOK + "/github"


def test_discord_failure_is_reported_to_github():
    with patch.object(github_to_discord.requests, "post", return_value=MagicMock(ok=False, status_code=500)):
        result = lambda_handler(make_event({"repository": {"private": False}}), None)
    assert result["statusCode"] == 502
