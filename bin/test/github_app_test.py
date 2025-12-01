"""Tests for the github_app module."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

import jwt
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


class TestGenerateJwt(unittest.TestCase):
    """Tests for JWT generation."""

    def test_generate_jwt_returns_string(self):
        """Test that generate_jwt returns a JWT string."""
        test_private_key, _ = generate_test_key_pair()

        jwt_token = generate_jwt("12345", test_private_key)

        self.assertIsInstance(jwt_token, str)
        # JWT has 3 parts separated by dots
        self.assertEqual(len(jwt_token.split(".")), 3)

    def test_generate_jwt_contains_correct_claims(self):
        """Test that the generated JWT contains the correct claims."""
        test_private_key, test_public_key = generate_test_key_pair()

        jwt_token = generate_jwt("12345", test_private_key)

        # Decode and verify claims
        decoded = jwt.decode(jwt_token, test_public_key, algorithms=["RS256"])

        self.assertEqual(decoded["iss"], "12345")
        self.assertIn("iat", decoded)
        self.assertIn("exp", decoded)
        # exp should be about 10 minutes after iat (with 60s clock drift adjustment)
        self.assertAlmostEqual(decoded["exp"] - decoded["iat"], 11 * 60, delta=5)


class TestGetInstallationId(unittest.TestCase):
    """Tests for getting installation ID."""

    def test_get_installation_id_success(self):
        """Test successful installation ID retrieval."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {"id": 111, "account": {"login": "other-org"}},
            {"id": 222, "account": {"login": "compiler-explorer"}},
        ]).encode()

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_installation_id("fake_jwt", org="compiler-explorer")

        self.assertEqual(result, 222)

    def test_get_installation_id_not_found(self):
        """Test error when installation is not found."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps([
            {"id": 111, "account": {"login": "other-org"}},
        ]).encode()

        with patch("urllib.request.urlopen", return_value=mock_response):
            with self.assertRaises(RuntimeError) as context:
                get_installation_id("fake_jwt", org="compiler-explorer")

        self.assertIn("not installed", str(context.exception))


class TestGetInstallationToken(unittest.TestCase):
    """Tests for getting installation access token."""

    def test_get_installation_token_success(self):
        """Test successful installation token retrieval."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "token": "ghs_xxxxxxxxxxxxxxxxxxxx",
            "expires_at": "2024-01-01T00:00:00Z",
        }).encode()

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = get_installation_token("fake_jwt", 12345)

        self.assertEqual(result, "ghs_xxxxxxxxxxxxxxxxxxxx")


class TestGetGithubAppToken(unittest.TestCase):
    """Tests for the main get_github_app_token function."""

    def test_get_github_app_token_success(self):
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

        self.assertEqual(result, "ghs_test_token_12345")

    def test_get_github_app_token_missing_app_id(self):
        """Test error when App ID is missing from SSM."""

        def mock_get_ssm_param(param):
            if "app-id" in param:
                raise Exception("Parameter not found")
            return "some_value"

        with patch("lib.github_app.get_ssm_param", side_effect=mock_get_ssm_param):
            with self.assertRaises(RuntimeError) as context:
                get_github_app_token()

        self.assertIn("App ID", str(context.exception))

    def test_get_github_app_token_missing_private_key(self):
        """Test error when private key is missing from SSM."""
        mock_ssm_client = MagicMock()
        mock_ssm_client.get_parameter.side_effect = Exception("Parameter not found")

        with (
            patch("lib.github_app.get_ssm_param", return_value="12345"),
            patch("lib.github_app.ssm_client", mock_ssm_client),
        ):
            with self.assertRaises(RuntimeError) as context:
                get_github_app_token()

        self.assertIn("private key", str(context.exception))


if __name__ == "__main__":
    unittest.main()
