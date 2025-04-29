#!/usr/bin/env python3
"""
Deterministic Lambda package builder for Compiler Explorer.
Uses Poetry for dependency management and creates a reproducible ZIP file.
"""

import base64
import hashlib
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

# Exclusion patterns for files we don't want in the package
EXCLUDE_PATTERN = re.compile(r"(__pycache__|\.pyc$|/tests/|\.dist-info$)")
EXCLUDE_COPY = shutil.ignore_patterns(
    "__pycache__", "*.dist-info*", "*.egg-info*", "pip", "setuptools", "wheel", "pkg_resources", "easy_install.py"
)


def run_command(cmd, cwd=None, capture_output=True):
    """Run shell command and return output"""
    cmd = [str(x) for x in cmd] if isinstance(cmd, list) else str(cmd)
    print(f"Running: {shlex.join(cmd) if isinstance(cmd, list) else cmd}")

    kwargs = {"cwd": cwd, "shell": isinstance(cmd, str)}
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        # Let stderr go to the console for better error visibility
        kwargs["text"] = True

    result = subprocess.run(cmd, check=True, **kwargs)

    if capture_output:
        return result.stdout.strip()
    return None


def create_deterministic_zip(source_dir, output_path):
    """Create a deterministic ZIP file with sorted entries and fixed timestamps"""
    # Use a fixed timestamp for reproducibility
    fixed_time = (1980, 1, 1, 0, 0, 0)

    source_path = Path(source_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get all files, sorted for deterministic ordering
    all_files = []

    # Find all files recursively, filtering out unwanted ones
    for path in sorted(source_path.rglob("*")):
        rel_path = path.relative_to(source_path)
        if EXCLUDE_PATTERN.search(str(rel_path)):
            continue
        if not path.is_dir():
            all_files.append((path, rel_path))

    # Sort files by path for deterministic ordering
    all_files.sort(key=lambda x: str(x[1]))

    # Log file stats
    print(f"Adding {len(all_files)} files to ZIP:")
    for _, rel_path in all_files[:5]:
        print(f"  {rel_path}")
    if len(all_files) > 5:
        print(f"  ... and {len(all_files) - 5} more files")

    # Create the deterministic ZIP file
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file_path, rel_path in all_files:
            # Get file info with fixed timestamp
            zip_info = zipfile.ZipInfo(str(rel_path))
            zip_info.date_time = fixed_time
            zip_info.external_attr = (file_path.stat().st_mode & 0o7777) << 16
            zipf.writestr(zip_info, file_path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)

    # Generate and save SHA256 hash
    sha256 = hashlib.sha256()
    sha256.update(output_path.read_bytes())
    sha256_base64 = base64.b64encode(sha256.digest()).decode("utf-8")

    # Write SHA directly to the .sha256 file
    Path(f"{output_path}.sha256").write_text(sha256_base64, encoding="utf-8")

    return sha256_base64


@contextmanager
def new_virtualenv(venv):
    old_env = os.environ.get("VIRTUAL_ENV")
    os.environ["VIRTUAL_ENV"] = str(venv)
    yield
    if old_env:
        os.environ["VIRTUAL_ENV"] = old_env


def get_poetry_venv_site_packages(lambda_dir, repo_root):
    """Get the site-packages directory from Poetry's virtual environment"""
    # Create or ensure the virtual environment exists with only main dependencies
    poetry_bin = repo_root / ".poetry/bin/poetry"
    with new_virtualenv(lambda_dir / ".venv"):
        run_command(
            [poetry_bin, "sync", "--no-root", "--no-interaction", "--only", "main"],
            cwd=lambda_dir,
            capture_output=False,
        )
        # Get the path to the virtual environment
        venv_path = run_command([poetry_bin, "env", "info", "--path"], cwd=lambda_dir)
        if not venv_path:
            raise RuntimeError("Could not determine Poetry virtual environment path")
        print(lambda_dir, venv_path)

        # Find site-packages directory
        venv_path = Path(venv_path)
        site_packages_dirs = list(venv_path.glob("lib/python*/site-packages"))

        if not site_packages_dirs:
            raise RuntimeError("Could not find site-packages directory in Poetry virtual environment")

        site_packages = site_packages_dirs[0]
        print(f"Found site-packages directory: {site_packages}")
    return site_packages


def build_lambda_package():
    """Build the Lambda package in a deterministic way"""
    # Set up paths
    repo_root = Path(__file__).parent.parent
    lambda_dir = repo_root / "lambda"
    dist_dir = repo_root / ".dist"
    lambda_zip_path = dist_dir / "lambda-package.zip"

    # Ensure dist directory exists
    dist_dir.mkdir(parents=True, exist_ok=True)

    # Get the site-packages directory from Poetry's virtual environment
    site_packages = get_poetry_venv_site_packages(lambda_dir, repo_root)

    # Create a temporary directory for staging the package content
    with tempfile.TemporaryDirectory() as temp_dir:
        staging_dir = Path(temp_dir) / "lambda-package"
        staging_dir.mkdir(parents=True, exist_ok=True)

        # Copy lambda Python files (excluding tests)
        print("Copying lambda Python files")
        for item in lambda_dir.glob("*.py"):
            if not item.name.endswith("_test.py"):
                shutil.copy2(item, staging_dir / item.name)
                print(f"Copied: {item.name}")

        # Copy dependencies from site-packages
        print("Copying dependencies from Poetry virtual environment")
        shutil.copytree(site_packages, staging_dir, symlinks=True, dirs_exist_ok=True, ignore=EXCLUDE_COPY)

        # Create the deterministic ZIP file
        print(f"Creating deterministic ZIP at: {lambda_zip_path}")
        sha256 = create_deterministic_zip(staging_dir, lambda_zip_path)
        print(f"SHA256: {sha256}")

        return lambda_zip_path, Path(f"{lambda_zip_path}.sha256")


if __name__ == "__main__":
    result_zip_path, result_sha_path = build_lambda_package()
    print(f"Lambda package created at: {result_zip_path}")
    print(f"Lambda package SHA256 hash created at: {result_sha_path}")
