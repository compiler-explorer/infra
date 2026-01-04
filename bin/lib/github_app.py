"""GitHub App authentication for Compiler Explorer Bot."""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

import jwt

from lib.amazon import get_ssm_param, ssm_client

LOGGER = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"
USER_AGENT = "CE GitHub App Auth"

# SSM parameter names
SSM_APP_ID = "/compiler-explorer/github-app-id"
SSM_PRIVATE_KEY = "/compiler-explorer/github-app-private-key"


def generate_jwt(app_id: str, private_key: str) -> str:
    """Generate a JWT for GitHub App authentication.

    Args:
        app_id: The GitHub App ID
        private_key: The private key in PEM format

    Returns:
        A JWT token valid for 10 minutes
    """
    now = int(time.time())
    payload = {
        "iat": now - 60,  # Issued 60 seconds ago to account for clock drift
        "exp": now + (10 * 60),  # Expires in 10 minutes
        "iss": app_id,
    }
    return jwt.encode(payload, private_key, algorithm="RS256")


def get_installation_id(app_jwt: str, org: str = "compiler-explorer") -> int:
    """Get the installation ID for a GitHub App on an organization.

    Args:
        app_jwt: JWT token for the GitHub App
        org: The organization name to find the installation for

    Returns:
        The installation ID

    Raises:
        RuntimeError: If the installation is not found or API request fails
    """
    try:
        req = urllib.request.Request(
            f"{GITHUB_API_URL}/app/installations",
            headers={
                "User-Agent": USER_AGENT,
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        result = urllib.request.urlopen(req)
        installations = json.loads(result.read())

        for installation in installations:
            if installation.get("account", {}).get("login") == org:
                return installation["id"]

        raise RuntimeError(f"GitHub App is not installed on organization '{org}'")
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to get GitHub App installations: {e}") from e


def get_installation_token(app_jwt: str, installation_id: int) -> str:
    """Get an installation access token for a GitHub App.

    Args:
        app_jwt: JWT token for the GitHub App
        installation_id: The installation ID

    Returns:
        An installation access token valid for 1 hour

    Raises:
        RuntimeError: If the token request fails
    """
    try:
        req = urllib.request.Request(
            f"{GITHUB_API_URL}/app/installations/{installation_id}/access_tokens",
            data=b"",
            method="POST",
            headers={
                "User-Agent": USER_AGENT,
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        result = urllib.request.urlopen(req)
        response = json.loads(result.read())
        return response["token"]
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as e:
        raise RuntimeError(f"Failed to get installation access token: {e}") from e


def get_github_app_token() -> str:
    """Get a GitHub installation access token using credentials from SSM.

    This function:
    1. Retrieves the App ID and private key from AWS SSM
    2. Generates a JWT signed with the private key
    3. Finds the installation ID for the compiler-explorer org
    4. Exchanges the JWT for an installation access token

    Returns:
        An installation access token for the GitHub App

    Raises:
        RuntimeError: If credentials are missing or authentication fails
    """
    LOGGER.debug("Retrieving GitHub App credentials from SSM")

    try:
        app_id = get_ssm_param(SSM_APP_ID)
    except Exception as e:
        raise RuntimeError(f"Failed to get GitHub App ID from SSM ({SSM_APP_ID}): {e}") from e

    try:
        # Private key is stored as SecureString, needs WithDecryption
        private_key = ssm_client.get_parameter(Name=SSM_PRIVATE_KEY, WithDecryption=True)["Parameter"]["Value"]
    except Exception as e:
        raise RuntimeError(f"Failed to get GitHub App private key from SSM ({SSM_PRIVATE_KEY}): {e}") from e

    LOGGER.debug("Generating JWT for GitHub App")
    app_jwt = generate_jwt(app_id, private_key)

    LOGGER.debug("Getting installation ID for compiler-explorer org")
    installation_id = get_installation_id(app_jwt)

    LOGGER.debug("Getting installation access token")
    return get_installation_token(app_jwt, installation_id)
