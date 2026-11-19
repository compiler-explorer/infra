"""Relay GitHub organisation webhooks to Discord, dropping anything from non-public repositories.

GitHub org webhooks fire for every repository in the org (private ones included) and cannot be filtered by
visibility, while Discord's /github endpoint happily renders whatever it is given. This sits in between: GitHub
posts here, and we only forward events that are provably from a public repository.

Fails closed: if we can't prove the event is public, it is dropped.
"""

import base64
import hashlib
import hmac
import json
import logging
import os

import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# GitHub gives up on a delivery after 10s, so there's no point waiting longer on Discord: (connect, read).
DISCORD_TIMEOUT_SECONDS = (3, 6)

# A public `repository` doesn't make the whole payload safe to publish (security advisories and alerts, secret
# teams, ...), so only events that describe ordinary public activity are forwarded; everything else is dropped.
FORWARDED_EVENTS = frozenset({
    "check_run",
    "check_suite",
    "commit_comment",
    "create",
    "delete",
    "discussion",
    "discussion_comment",
    "fork",
    "gollum",
    "issue_comment",
    "issues",
    "public",
    "pull_request",
    "pull_request_review",
    "pull_request_review_comment",
    "push",
    "release",
    "status",
    "watch",
})


def _response(status: int, body: str) -> dict:
    return {"statusCode": status, "body": body}


def get_body(event: dict) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            return base64.b64decode(body, validate=True)
        except ValueError:  # binascii.Error is a ValueError
            return b""
    return body.encode("utf-8")


def signature_is_valid(secret: str, body: bytes, signature_header: str | None) -> bool:
    if not secret or not signature_header:
        return False
    expected = "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    # Compare bytes: compare_digest raises TypeError on non-ASCII str, which an unauthenticated caller could trigger.
    return hmac.compare_digest(expected.encode("utf-8"), signature_header.encode("utf-8", "replace"))


def _is_public_repo(repository: object) -> bool:
    if not isinstance(repository, dict):
        return False
    # `is False` (not falsiness) so a missing/null/unexpected value is treated as "not provably public".
    # Also require visibility, when present, to be "public" so that "internal" repos can't slip through.
    return repository.get("private") is False and repository.get("visibility", "public") == "public"


def is_public_repository_event(payload: object) -> bool:
    """True only if the payload names a repository that is explicitly not private, and nothing else it names isn't.

    Events without a repository (org/team/membership events...) are dropped: we can't tell what they relate to.
    """
    if not isinstance(payload, dict):
        return False
    if not _is_public_repo(payload.get("repository")):
        return False
    changes = payload.get("changes")
    # e.g. an issue transferred out of a public repo into a private one names the destination repo.
    if isinstance(changes, dict) and "new_repository" in changes and not _is_public_repo(changes["new_repository"]):
        return False
    # Requesting review from a (possibly secret) team puts the team's details in the payload.
    return "requested_team" not in payload


def lambda_handler(event, _context):
    # Function URLs lower-case header names.
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    body = get_body(event)

    if not signature_is_valid(os.environ.get("GITHUB_WEBHOOK_SECRET", ""), body, headers.get("x-hub-signature-256")):
        logger.warning("Rejecting request with missing or invalid signature")
        return _response(401, "invalid signature")

    github_event = headers.get("x-github-event", "")
    if github_event == "ping":
        return _response(200, "pong")
    if github_event not in FORWARDED_EVENTS:
        logger.info("Dropping %s event: not on the forwarded list", github_event)
        return _response(200, "dropped")

    try:
        payload = json.loads(body)
    except ValueError:
        return _response(400, "invalid json")

    if not is_public_repository_event(payload):
        # Deliberately don't log repo names: this is the case where they might be private.
        logger.info("Dropping %s event: not from a provably public repository", github_event)
        return _response(200, "dropped")

    forward_headers = {
        "content-type": headers.get("content-type", "application/json"),
        "x-github-event": github_event,
    }
    if "x-github-delivery" in headers:
        forward_headers["x-github-delivery"] = headers["x-github-delivery"]
    try:
        response = requests.post(
            os.environ["DISCORD_WEBHOOK_URL"].rstrip("/") + "/github",
            data=body,
            headers=forward_headers,
            timeout=DISCORD_TIMEOUT_SECONDS,
        )
    except requests.RequestException as e:
        # Log the type only: the message includes the request URL, which contains the Discord webhook token.
        logger.error("Failed to forward %s event to Discord: %s", github_event, type(e).__name__)
        return _response(502, "discord error")
    logger.info("Forwarded %s event to Discord: %s", github_event, response.status_code)
    # Surface Discord failures to GitHub so they show up in the hook's "Recent Deliveries" and can be redelivered.
    return _response(200 if response.ok else 502, "forwarded" if response.ok else "discord error")
