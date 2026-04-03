"""CLI commands for managing conan proxy build status."""

from __future__ import annotations

import click

from lib.conan_api import clear_build_status_for_compiler, clear_build_status_for_library, list_failed_builds

from ..ce_install import cli


@cli.group(name="build-status")
def build_status():
    """Manage library build failure status on the conan proxy."""


@build_status.command(name="clear-for-compiler")
@click.argument("compiler_version")
def clear_for_compiler(compiler_version: str):
    """Clear all build failures for a compiler so libraries will re-attempt building.

    COMPILER_VERSION is the compiler ID as used by the build system (e.g. g101, g141, clang1400).
    The compiler family is inferred automatically (gcc for g*, clang for clang*).
    """
    compiler = _compiler_family_from_id(compiler_version)
    click.echo(f"Clearing build failures for {compiler} {compiler_version}...")
    try:
        clear_build_status_for_compiler(compiler, compiler_version)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    click.echo("Done.")


@build_status.command(name="clear-for-library")
@click.argument("library")
@click.option("--version", "library_version", default=None, help="Only clear failures for this version")
def clear_for_library(library: str, library_version: str | None):
    """Clear all build failures for a library so it will re-attempt building.

    LIBRARY is the library ID as used by the build system (e.g. fmt, catch2, boost).
    """
    version_msg = f" version {library_version}" if library_version else ""
    click.echo(f"Clearing build failures for {library}{version_msg}...")
    try:
        clear_build_status_for_library(library, library_version)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e
    click.echo("Done.")


@build_status.command(name="list-failed")
@click.option("--library", default=None, help="Filter to a specific library name")
@click.option("--version", "library_version", default=None, help="Filter to a specific library version")
@click.option("--compiler-version", default=None, help="Filter to a specific compiler version (e.g. g141)")
@click.option("--timeout", default=300, show_default=True, help="Request timeout in seconds")
def list_failed(library: str | None, library_version: str | None, compiler_version: str | None, timeout: int):
    """List failed builds. At least one of --library or --compiler-version is required."""
    if not library and not compiler_version:
        raise click.ClickException(
            "Specify at least one of --library or --compiler-version (unfiltered queries will timeout)."
        )

    try:
        builds = list_failed_builds(timeout=timeout)
    except RuntimeError as e:
        raise click.ClickException(str(e)) from e

    failed = [b for b in builds if not b.get("success", True)]

    if library:
        failed = [b for b in failed if b.get("library") == library]
    if library_version:
        failed = [b for b in failed if b.get("library_version") == library_version]
    if compiler_version:
        failed = [b for b in failed if b.get("compiler_version") == compiler_version]

    if not failed:
        click.echo("No failed builds found.")
        return

    click.echo(f"{'Library':<25} {'Version':<15} {'Compiler':<20} {'Arch':<10} {'Stdlib':<15} {'Date'}")
    click.echo("-" * 105)
    for b in failed:
        lib = b.get("library", "")
        ver = b.get("library_version", "")
        comp = b.get("compiler_version", "")
        arch = b.get("arch", "")
        libcxx = b.get("libcxx", "")
        dt = b.get("build_dt", "")
        click.echo(f"{lib:<25} {ver:<15} {comp:<20} {arch:<10} {libcxx:<15} {dt}")

    click.echo(f"\nTotal: {len(failed)} failed build(s)")


def _compiler_family_from_id(compiler_version: str) -> str:
    """Infer the compiler family name from a compiler version ID."""
    if compiler_version.startswith("g"):
        return "gcc"
    if compiler_version.startswith("clang"):
        return "clang"
    if compiler_version.startswith("icc"):
        return "icc"
    raise click.ClickException(
        f"Cannot infer compiler family from '{compiler_version}'. "
        "Expected an ID starting with 'g' (gcc), 'clang', or 'icc'."
    )
