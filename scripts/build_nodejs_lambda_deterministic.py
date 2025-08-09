#!/usr/bin/env python3
"""
Deterministic Node.js Lambda package builder for Compiler Explorer.
Uses npm for dependency management and creates a reproducible ZIP file.

Usage:
    python build_nodejs_lambda_deterministic.py <source_dir> <output_zip_path>

Arguments:
    source_dir: Directory containing Lambda source code with package.json
    output_zip_path: Path to the output ZIP file (will also create <output_zip_path>.sha256)
"""

import argparse
import hashlib
import re
import shlex
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

# Exclusion patterns for files we don't want in the package
EXCLUDE_PATTERN = re.compile(
    r"(node_modules/\.cache|\.git/|\.DS_Store|__pycache__|\.pyc$|/tests/|test\.js$|\.test\.js$)"
)


def run_command(cmd, cwd=None, capture_output=True):
    """Run shell command and return output"""
    cmd = [str(x) for x in cmd] if isinstance(cmd, list) else str(cmd)
    print(f"Running: {shlex.join(cmd) if isinstance(cmd, list) else cmd}")

    kwargs = {"cwd": cwd, "shell": isinstance(cmd, str)}
    if capture_output:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["text"] = True

    result = subprocess.run(cmd, check=True, **kwargs)

    if capture_output:
        return result.stdout.strip()
    return None


def install_dependencies(source_path, temp_dir):
    """Install Node.js dependencies in the temporary directory"""
    package_json = source_path / "package.json"
    package_lock = source_path / "package-lock.json"

    if not package_json.exists():
        raise FileNotFoundError(f"package.json not found in {source_path}")

    # Copy package.json and package-lock.json to temp directory
    shutil.copy2(package_json, temp_dir / "package.json")
    if package_lock.exists():
        shutil.copy2(package_lock, temp_dir / "package-lock.json")

    # Install production dependencies only
    run_command(["npm", "install", "--production", "--no-optional"], cwd=temp_dir)

    # Clean up any cache or unnecessary files
    run_command(["npm", "cache", "clean", "--force"], cwd=temp_dir)

    # Remove any dev dependencies that might have been installed
    node_modules = temp_dir / "node_modules"
    if node_modules.exists():
        # Remove test files and other unnecessary files
        for path in node_modules.rglob("*"):
            if path.is_file() and EXCLUDE_PATTERN.search(str(path)):
                path.unlink(missing_ok=True)


def create_deterministic_zip(source_path, output_path):
    """Create a deterministic ZIP file from the lambda source"""
    source_path = Path(source_path).resolve()
    output_path = Path(output_path).resolve()

    print(f"Building Node.js Lambda package from {source_path}")

    # Create temp directory for building
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Copy source files (excluding tests and other unnecessary files)
        for item in source_path.iterdir():
            # Skip directories that shouldn't be in Lambda
            if item.name in [
                "node_modules",
                ".git",
                "coverage",
                ".nyc_output",
                ".venv",
                ".pytest_cache",
                ".ruff_cache",
                "__pycache__",
                ".mypy_cache",
                "dist",
                "build",
                ".dist",
            ]:
                continue

            # Skip test files and other development files
            if item.name.endswith((".test.js", ".spec.js", ".md", ".pyc")):
                continue

            # Skip hidden files except for specific ones we might need
            if item.name.startswith(".") and item.name not in [".env"]:
                continue

            if item.is_file():
                shutil.copy2(item, temp_path / item.name)
            elif item.is_dir():
                shutil.copytree(
                    item,
                    temp_path / item.name,
                    ignore=shutil.ignore_patterns(
                        "*.test.js",
                        "*.spec.js",
                        "test",
                        "tests",
                        "__tests__",
                        "coverage",
                        "*.md",
                        "__pycache__",
                        "*.pyc",
                        ".git",
                        ".venv",
                    ),
                )

        # Install dependencies
        install_dependencies(source_path, temp_path)

        # Create the ZIP file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zip_file:
            # Add all files in a deterministic order
            all_files = []
            for root, dirs, files in temp_path.walk():
                # Sort directories and files for deterministic order
                dirs.sort()
                files.sort()

                for file in files:
                    file_path = root / file
                    if not EXCLUDE_PATTERN.search(str(file_path)):
                        relative_path = file_path.relative_to(temp_path)
                        all_files.append((file_path, relative_path))

            # Sort all files by their relative path for deterministic order
            all_files.sort(key=lambda x: str(x[1]))

            # Add files to ZIP with fixed timestamps for reproducibility
            for file_path, relative_path in all_files:
                # Set a fixed timestamp (epoch) for deterministic builds
                info = zipfile.ZipInfo(str(relative_path))
                info.date_time = (1980, 1, 1, 0, 0, 0)
                info.external_attr = 0o644 << 16  # File permissions

                with open(file_path, "rb") as f:
                    zip_file.writestr(info, f.read())

    # Generate SHA256 hash
    with open(output_path, "rb") as f:
        sha256_hash = hashlib.sha256(f.read()).hexdigest()

    sha256_path = output_path.with_suffix(output_path.suffix + ".sha256")
    with open(sha256_path, "w") as f:
        f.write(sha256_hash)

    file_size = output_path.stat().st_size
    print(f"✅ Created deterministic Lambda package: {output_path}")
    print(f"   Size: {file_size:,} bytes")
    print(f"   SHA256: {sha256_hash}")
    print(f"   Hash file: {sha256_path}")


def main():
    parser = argparse.ArgumentParser(description="Build deterministic Node.js Lambda package")
    parser.add_argument("source_dir", help="Directory containing Lambda source code")
    parser.add_argument("output_zip", help="Path to output ZIP file")

    args = parser.parse_args()

    create_deterministic_zip(args.source_dir, args.output_zip)


if __name__ == "__main__":
    main()
