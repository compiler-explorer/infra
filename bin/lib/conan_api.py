"""Client for the Conan proxy server build status API."""

from __future__ import annotations

import json
import os
from typing import Any

import requests

from lib.amazon import get_ssm_param

CONAN_SERVER_URL = "https://conan.compiler-explorer.com"


def get_conan_auth_token() -> str:
    """Authenticate with the conan proxy and return a bearer token."""
    password = os.environ.get("CONAN_PASSWORD")
    if not password:
        password = get_ssm_param("/compiler-explorer/conanpwd")

    response = requests.post(f"{CONAN_SERVER_URL}/login", json={"password": password}, timeout=30)
    if not response.ok:
        raise RuntimeError(f"Conan proxy login failed: {response.status_code} {response.text}")

    return json.loads(response.content)["token"]


def clear_build_status_for_compiler(compiler: str, compiler_version: str) -> None:
    """Clear all build failure records for a compiler, allowing libraries to rebuild."""
    token = get_conan_auth_token()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload = {"compiler": compiler, "compiler_version": compiler_version}

    response = requests.post(
        f"{CONAN_SERVER_URL}/clearbuildstatusforcompiler", json=payload, headers=headers, timeout=30
    )
    if not response.ok:
        raise RuntimeError(f"Failed to clear build status: {response.status_code} {response.text}")


def clear_build_status_for_library(library: str, library_version: str | None = None) -> None:
    """Clear all build failure records for a library, optionally filtered by version."""
    token = get_conan_auth_token()
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    payload: dict[str, str] = {"library": library}
    if library_version:
        payload["library_version"] = library_version

    response = requests.post(
        f"{CONAN_SERVER_URL}/clearbuildstatusforlibrary", json=payload, headers=headers, timeout=30
    )
    if not response.ok:
        raise RuntimeError(f"Failed to clear build status: {response.status_code} {response.text}")


def list_failed_builds(timeout: int = 300) -> list[dict[str, Any]]:
    """List all recently failed builds from the conan proxy."""
    response = requests.get(f"{CONAN_SERVER_URL}/allfailedbuilds", timeout=timeout)
    if not response.ok:
        raise RuntimeError(f"Failed to fetch failed builds: {response.status_code} {response.text}")

    return json.loads(response.content)
