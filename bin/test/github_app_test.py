"""Tests for the github_app module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from lib.github_app import (
    generate_jwt,
    get_github_app_token,
    get_installation_id,
    get_installation_token,
)


def generate_test_key_pair():
    """Generate a test RSA key pair."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend(),
    )

    pem_private = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    pem_public = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )

    return pem_private, pem_public


def test_generate_jwt_returns_string():
    """Test that generate_jwt returns a JWT string."""
    test_private_key, _ = generate_test_key_pair()

    jwt_token = generate_jwt("12345", test_private_key)

    assert isinstance(jwt_token, str)
    assert len(jwt_token.split(".")) == 3  # JWT has 3 parts separated by dots


def test_generate_jwt_contains_correct_claims():
    """Test that the generated JWT contains the correct claims."""
    test_private_key, test_public_key = generate_test_key_pair()

    jwt_token = generate_jwt("12345", test_private_key)

    decoded = jwt.decode(jwt_token, test_public_key, algorithms=["RS256"])

    assert decoded["iss"] == "12345"
    assert "iat" in decoded
    assert "exp" in decoded
    # exp should be about 10 minutes after iat (with 60s clock drift adjustment)
    assert abs((decoded["exp"] - decoded["iat"]) - 11 * 60) < 5


def test_get_installation_id_success():
    """Test successful installation ID retrieval."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps([
        {"id": 111, "account": {"login": "other-org"}},
        {"id": 222, "account": {"login": "compiler-explorer"}},
    ]).encode()

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = get_installation_id("fake_jwt", org="compiler-explorer")

    assert result == 222


def test_get_installation_id_not_found():
    """Test error when installation is not found."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps([
        {"id": 111, "account": {"login": "other-org"}},
    ]).encode()

    with patch("urllib.request.urlopen", return_value=mock_response):
        with pytest.raises(RuntimeError, match="not installed"):
            get_installation_id("fake_jwt", org="compiler-explorer")


def test_get_installation_token_success():
    """Test successful installation token retrieval."""
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({
        "token": "ghs_xxxxxxxxxxxxxxxxxxxx",
        "expires_at": "2024-01-01T00:00:00Z",
    }).encode()

    with patch("urllib.request.urlopen", return_value=mock_response):
        result = get_installation_token("fake_jwt", 12345)

    assert result == "ghs_xxxxxxxxxxxxxxxxxxxx"


def test_get_github_app_token_success():
    """Test successful end-to-end token retrieval."""
    test_private_key, _ = generate_test_key_pair()

    mock_ssm_client = MagicMock()
    mock_ssm_client.get_parameter.return_value = {"Parameter": {"Value": test_private_key}}

    mock_installations_response = MagicMock()
    mock_installations_response.read.return_value = json.dumps([
        {"id": 67890, "account": {"login": "compiler-explorer"}},
    ]).encode()

    mock_token_response = MagicMock()
    mock_token_response.read.return_value = json.dumps({
        "token": "ghs_test_token_12345",
    }).encode()

    with (
        patch("lib.github_app.get_ssm_param", return_value="12345"),
        patch("lib.github_app.ssm_client", mock_ssm_client),
        patch("urllib.request.urlopen", side_effect=[mock_installations_response, mock_token_response]),
    ):
        result = get_github_app_token()

    assert result == "ghs_test_token_12345"


def test_get_github_app_token_missing_app_id():
    """Test error when App ID is missing from SSM."""

    def mock_get_ssm_param(param):
        if "app-id" in param:
            raise Exception("Parameter not found")
        return "some_value"

    with patch("lib.github_app.get_ssm_param", side_effect=mock_get_ssm_param):
        with pytest.raises(RuntimeError, match="App ID"):
            get_github_app_token()


def test_get_github_app_token_missing_private_key():
    """Test error when private key is missing from SSM."""
    mock_ssm_client = MagicMock()
    mock_ssm_client.get_parameter.side_effect = Exception("Parameter not found")

    with (
        patch("lib.github_app.get_ssm_param", return_value="12345"),
        patch("lib.github_app.ssm_client", mock_ssm_client),
    ):
        with pytest.raises(RuntimeError, match="private key"):
            get_github_app_token()
