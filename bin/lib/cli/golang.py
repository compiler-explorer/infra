"""CLI commands for Go compiler management."""

from __future__ import annotations

import logging
from pathlib import Path

import click

from lib.ce_install import CliContext, cli
from lib.golang_stdlib import build_go_stdlib, is_go_installation, is_stdlib_already_built

LOGGER = logging.getLogger(__name__)


@cli.group(name="golang")
def golang():
    """Go compiler management commands."""


@golang.command(name="build-stdlib")
@click.option(
    "--arch",
    "architectures",
    multiple=True,
    help="Architecture to build for (format: OS/ARCH, e.g., linux/amd64). Can be specified multiple times. Default: linux/amd64, linux/arm64",
)
@click.option(
    "--cache-dir",
    "cache_dir",
    type=click.Path(path_type=Path),
    help="Custom cache directory path. Default: <install-dir>/cache",
)
@click.option(
    "--force",
    is_flag=True,
    help="Force rebuild even if stdlib is already built",
)
@click.option(
    "--skip-squash",
    is_flag=True,
    help="Skip squashing after building stdlib (useful for testing)",
)
@click.argument("filter_", metavar="FILTER", nargs=-1, required=False)
@click.pass_obj
def build_stdlib(
    context: CliContext,
    architectures: tuple[str, ...],
    cache_dir: Path | None,
    force: bool,
    skip_squash: bool,
    filter_: tuple[str, ...],
):
    """Build Go standard library cache for Go installations matching FILTER.

    This pre-builds the Go standard library for specified architectures,
    which significantly improves compilation performance. The stdlib cache
    is stored in the Go installation directory and will be included when
    the installation is squashed/consolidated with CEFS.

    By default, builds for linux/amd64 and linux/arm64. Use --arch to specify
    different architectures.

    Examples:
        ce golang build-stdlib golang           # Build for all Go installations
        ce golang build-stdlib "golang 1.24"    # Build for Go 1.24
        ce golang build-stdlib --arch linux/amd64 golang  # Build only for amd64
        ce golang build-stdlib --force golang   # Rebuild even if already built
        ce golang build-stdlib --cache-dir /tmp/gocache golang  # Custom cache location
    """
    # Convert tuple to list, or use defaults
    arch_list = list(architectures) if architectures else None

    # Get all Go installations
    all_installables = context.get_installables(list(filter_) if filter_ else [])

    # Filter to only Go compiler installables
    go_installables = []
    for installable in all_installables:
        install_path = context.installation_context.destination / installable.install_path
        if is_go_installation(install_path):
            go_installables.append((installable, install_path))

    if not go_installables:
        if filter_:
            LOGGER.warning("No Go installations found matching filter: %s", " ".join(filter_))
        else:
            LOGGER.warning("No Go installations found")
        return

    LOGGER.info("Found %d Go installation(s)", len(go_installables))

    successful = 0
    skipped = 0
    failed = 0

    for installable, install_path in go_installables:
        LOGGER.info("Processing %s...", installable.name)

        # Check if already built
        if not force and is_stdlib_already_built(install_path):
            LOGGER.info("  Stdlib already built, skipping (use --force to rebuild)")
            skipped += 1
            continue

        # Build stdlib
        try:
            if build_go_stdlib(install_path, arch_list, cache_dir, context.installation_context.dry_run):
                successful += 1

                # Squash the installation to include the new stdlib cache
                if not skip_squash and not context.installation_context.dry_run:
                    LOGGER.info("  Re-squashing to include stdlib cache...")
                    # TODO: Integrate with squashing system
                    # For now, just log that squashing should happen
                    LOGGER.info(
                        "  (Squashing integration TODO - manually run 'ce install %s' to squash)", installable.name
                    )
            else:
                failed += 1
        except RuntimeError as e:
            LOGGER.error("Failed to build stdlib for %s: %s", installable.name, e)
            failed += 1

    LOGGER.info("\nStdlib build complete:")
    LOGGER.info("  Successful: %d", successful)
    LOGGER.info("  Skipped: %d", skipped)
    LOGGER.info("  Failed: %d", failed)

    if failed > 0:
        raise click.ClickException(f"Failed to build stdlib for {failed} installation(s)")

    if successful > 0 and not skip_squash:
        LOGGER.info("\nTo include stdlib cache in squashed images, reinstall with:")
        LOGGER.info("  ce install %s", " ".join(filter_) if filter_ else "golang")
