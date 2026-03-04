#!/usr/bin/env python3
from __future__ import annotations

import fnmatch
import json
import logging
import logging.config
import multiprocessing
import os
import signal
import sys
import traceback
from dataclasses import dataclass, field
from functools import partial
from multiprocessing.pool import ThreadPool
from pathlib import Path
from typing import TextIO

import click
import yaml
from click.core import ParameterSource
from packaging import specifiers, version

from lib.amazon_properties import get_properties_compilers_and_libraries
from lib.compiler_id_lookup import get_compiler_id_lookup
from lib.config import Config
from lib.config_safe_loader import ConfigSafeLoader
from lib.installable.installable import Installable
from lib.installation import installers_for
from lib.installation_context import FetchFailure, InstallationContext
from lib.library_platform import LibraryPlatform
from lib.library_yaml import LibraryYaml
from lib.squashfs import verify_squashfs_contents

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CliContext:
    installation_context: InstallationContext
    enabled: list[str]
    filter_match_all: bool
    parallel: int
    config: Config
    _name_to_installable_cache: dict[str, Installable] = field(default_factory=dict, init=False, repr=False)

    def pool(self):  # no type hint as mypy freaks out, really a multiprocessing.Pool
        # https://stackoverflow.com/questions/11312525/catch-ctrlc-sigint-and-exit-multiprocesses-gracefully-in-python
        _LOGGER.info("Creating thread pool with %s workers", self.parallel)
        original_sigint_handler = signal.signal(signal.SIGINT, signal.SIG_IGN)
        pool = ThreadPool(processes=self.parallel)
        signal.signal(signal.SIGINT, original_sigint_handler)
        return pool

    def get_installables(self, args_filter: list[str], bypass_enable_check: bool = False) -> list[Installable]:
        """Get installables matching the filter.

        Args:
            args_filter: Filter strings to match installables
            bypass_enable_check: If True, bypass all 'if:' conditions (nightly, non-free, etc.)
        """
        installables = []
        for yaml_path in Path(self.installation_context.yaml_dir).glob("*.yaml"):
            with yaml_path.open(encoding="utf-8") as yaml_file:
                yaml_doc = yaml.load(yaml_file, Loader=ConfigSafeLoader)
            for installer in installers_for(self.installation_context, yaml_doc, bypass_enable_check or self.enabled):
                installables.append(installer)
        Installable.resolve(installables)
        installables = sorted(
            filter(lambda installable: filter_aggregate(args_filter, installable, self.filter_match_all), installables),
            key=lambda x: x.sort_key,
        )
        return installables

    def find_installable_by_exact_name(self, name: str) -> Installable:
        """Find an installable by its exact name.

        Args:
            name: The exact name to search for (e.g., "compilers/c++/x86/gcc 14.1.0")

        Returns:
            The matching Installable object

        Raises:
            ValueError: If exactly one installable is not found (0 or 2+ matches)
        """
        if not self._name_to_installable_cache:
            # bypass_enable_check=True includes ALL installables regardless of 'if:' conditions
            # (nightly, non-free, etc). Critical for finding installables that might be
            # conditionally disabled but still exist on disk (e.g., during consolidation checks)
            for inst in self.get_installables([], bypass_enable_check=True):
                if inst.name in self._name_to_installable_cache:
                    raise ValueError(f"Duplicate installable name found: {inst.name}")
                self._name_to_installable_cache[inst.name] = inst

        if name not in self._name_to_installable_cache:
            raise ValueError(f"No installable found with exact name: {name}")

        return self._name_to_installable_cache[name]


def _context_match(context_query: str, installable: Installable) -> bool:
    """Match context query against installable's context path.

    Context matching rules:
    - If query starts with "/", requires exact prefix match from root
    - Otherwise, searches for substring match anywhere in the path
    - Supports wildcards (*) for glob-style pattern matching

    Args:
        context_query: Path pattern like "gcc", "cross/gcc", "/compilers", or "*/gcc"
        installable: The installable to check

    Returns:
        True if context matches the query pattern

    Examples:
        - "gcc" matches paths containing "gcc" anywhere
        - "cross/gcc" matches paths containing that sequence
        - "/compilers" only matches paths starting with "compilers/"
        - "*/gcc" matches any path ending with "gcc"
    """
    if "*" in context_query:  # Handle wildcards
        full_path = "/".join(installable.context)
        return fnmatch.fnmatch(full_path, context_query.lstrip("/"))

    context = context_query.split("/")
    root_only = not context[0]
    if root_only:
        context = context[1:]
        return installable.context[: len(context)] == context

    for sub in range(0, len(installable.context) - len(context) + 1):
        if installable.context[sub : sub + len(context)] == context:
            return True
    return False


def _parse_version(version_str: str) -> version.Version | None:
    """Parse a version string, trying to extract a valid version.

    First tries the version as-is, then tries removing prefix up to and
    including the last hyphen. Returns None if no valid version found.
    """
    try:
        return version.parse(version_str)
    except version.InvalidVersion:
        pass

    if "-" in version_str:
        last_hyphen = version_str.rfind("-")
        candidate = version_str[last_hyphen + 1 :]
        try:
            return version.parse(candidate)
        except version.InvalidVersion:
            pass

    return None


def try_parse_specifiers(query: str) -> specifiers.SpecifierSet | None:
    """Try to parse a string into a SpecifierSet.

    Args:
        query: The string to parse.

    Returns:
        A SpecifierSet if parsing was successful, None otherwise.
    """
    try:
        return specifiers.SpecifierSet(query)
    except (version.InvalidVersion, specifiers.InvalidSpecifier):
        return None


def _version_matches_range(version_str: str, specifiers: specifiers.SpecifierSet) -> bool:
    """Check if a version matches a range pattern using packaging.specifiers.

    Supports PEP 440 patterns like: ">=14.0", "<15.0", "~=1.70.0"
    Uses Python's standard packaging library for robust version comparison.
    """
    v = _parse_version(version_str)
    if v is None:
        return False

    return v in specifiers


def _target_match(target: str, installable: Installable) -> bool:
    """Match target query against installable's target name.

    Args:
        target: Target pattern like "14.1.0", "14.*", ">=14.0", "~=1.70.0", "!assertions-*"
        installable: The installable to check

    Returns:
        True if target matches the installable's target name

    Examples:
        - "14.1.0" matches only items with target_name exactly "14.1.0"
        - "14.*" matches "14.1.0", "14.2.1", etc.
        - ">=14.0" matches "14.1.0", "15.0.0", etc.
        - "~=1.70.0" matches "1.70.x" versions (compatible release)
        - "!assertions-*" matches anything NOT matching "assertions-*"
    """
    if target == installable.target_name:  # Exact match is always ok
        return True

    if specifiers := try_parse_specifiers(target):  # PEP 440 version specifiers
        return _version_matches_range(installable.target_name, specifiers)

    if target.startswith("!"):  # negative patterns
        return not _target_match(target[1:], installable)

    return fnmatch.fnmatch(installable.target_name, target)


def filter_match(filter_query: str, installable: Installable) -> bool:
    """Match a filter query against an installable.

    Filter syntax:
    - Single word: matches context (substring) OR target (pattern)
    - Two words: first matches context (pattern) AND second matches target (pattern)
    - Supports wildcards (*), negatives (!), and version ranges (>=, <, ~)

    Args:
        filter_query: Filter string like "gcc", "gcc 14.*", "!cross", ">=14.0", etc.
        installable: The installable to check

    Returns:
        True if the installable matches the filter query

    Examples:
        - "gcc" matches installables with "gcc" in path OR target named "gcc"
        - "gcc 14.*" matches installables with "gcc" in path AND target matching "14.*"
        - "!cross" matches installables without "cross" in path AND target not "cross"
        - "*/gcc >=14.0" matches any gcc with version >= 14.0
    """
    split = filter_query.split(" ", 1)
    if len(split) == 1:
        query = split[0]
        # Handle negative patterns specially for single word, unless it's a version match
        if query.startswith("!") and not try_parse_specifiers(query):
            # For negative single word, both context and target must NOT match
            positive_query = query[1:]
            return not (_context_match(positive_query, installable) or _target_match(positive_query, installable))
        # Otherwise, either context OR target can match
        return _context_match(query, installable) or _target_match(query, installable)
    return _context_match(split[0], installable) and _target_match(split[1], installable)


def filter_aggregate(filters: list, installable: Installable, filter_match_all: bool = True) -> bool:
    """Apply multiple filters to an installable with AND/OR logic.

    Args:
        filters: List of filter query strings
        installable: The installable to check against all filters
        filter_match_all: If True, all filters must match (AND logic).
                         If False, any filter can match (OR logic).

    Returns:
        True if the installable passes the filter criteria

    Examples:
        With filter_match_all=True (default):
        - ["gcc", "14.1.0"] requires BOTH "gcc" match AND "14.1.0" match

        With filter_match_all=False:
        - ["gcc", "clang"] requires EITHER "gcc" match OR "clang" match

    Notes:
        - Empty filter list matches everything
        - Use --filter-match-all/--filter-match-any CLI flags to control behavior
    """
    # if there are no filters, accept it
    if not filters:
        return True

    # accept installable if it passes all filters (if filter_match_all is set) or any filters (otherwise)
    filter_generator = (filter_match(filt, installable) for filt in filters)
    return all(filter_generator) if filter_match_all else any(filter_generator)


def squash_mount_check(rootfolder: Path, subdir: str, context: CliContext) -> int:
    error_count = 0
    for filename in os.listdir(rootfolder / subdir):
        if filename.endswith(".img"):
            checkdir = Path("/opt/compiler-explorer/") / subdir / filename[:-4]
            if not checkdir.exists():
                _LOGGER.error("Missing mount point %s", checkdir)
                error_count += 1
        else:
            if not subdir:
                error_count += squash_mount_check(rootfolder, filename, context)
            else:
                error_count += squash_mount_check(rootfolder, f"{subdir}/{filename}", context)
    return error_count


@click.group()
@click.option(
    "--dest",
    default=Path("/opt/compiler-explorer"),
    metavar="DEST",
    type=click.Path(file_okay=False, path_type=Path),
    help="Install with DEST as the installation root",
    show_default=True,
)
@click.option(
    "--staging-dir",
    default=Path("{dest}/staging"),
    metavar="STAGEDIR",
    type=click.Path(file_okay=False, path_type=Path),
    help="Install to a unique subdirectory of STAGEDIR then rename in-place. Must be on the same drive as "
    "DEST for atomic rename/replace. Directory will be removed during install",
    show_default=True,
)
@click.option(
    "--check-user",
    default="",
    metavar="CHECKUSER",
    type=str,
    help="Executes --version checks under a different user",
)
@click.option("--debug/--no-debug", help="Turn on debugging")
@click.option("--dry-run/--for-real", help="Dry run only")
@click.option("--log-to-console", is_flag=True, help="Log output to console, even if logging to a file is requested")
@click.option("--log", metavar="LOGFILE", help="Log to LOGFILE", type=click.Path(dir_okay=False, writable=True))
@click.option(
    "--s3-bucket",
    default="compiler-explorer",
    metavar="BUCKET",
    help="Look for S3 resources in BUCKET",
    show_default=True,
)
@click.option(
    "--s3-dir",
    default="opt",
    metavar="DIR",
    help="Look for S3 resources in the bucket's subdirectory DIR",
    show_default=True,
)
@click.option("--enable", metavar="TYPE", multiple=True, help='Enable targets of type TYPE (e.g. "nightly")')
@click.option("--only-nightly", is_flag=True, help="Only install the nightly targets")
@click.option(
    "--cache",
    metavar="DIR",
    help="Cache requests at DIR",
    type=click.Path(file_okay=False, writable=True, path_type=Path),
)
@click.option(
    "--yaml-dir",
    default=Path(__file__).resolve().parent.parent / "yaml",
    help="Look for installation yaml files in DIRs",
    metavar="DIR",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--resource-dir",
    default=Path(__file__).resolve().parent.parent / "resources",
    help="Look for installation yaml files in DIRs",
    metavar="DIR",
    show_default=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--allow-unsafe-ssl/-safe-ssl-only", help="Skip ssl certificate checks on https connections")
@click.option("--keep-staging", is_flag=True, help="Keep the unique staging directory")
@click.option(
    "--filter-match-all/--filter-match-any", help="Filter expressions must all match / any match", default=True
)
@click.option(
    "--parallel",
    type=int,
    default=min(8, multiprocessing.cpu_count()),
    help="Limit the number of concurrent processes to N",
    metavar="N",
    show_default=True,
)
@click.option("--force-cefs", is_flag=True, help="Force CEFS installation mode even if disabled in config")
@click.option(
    "--force-traditional", is_flag=True, help="Force traditional NFS installation even if CEFS enabled in config"
)
@click.option(
    "--cefs-temp-dir",
    metavar="DIR",
    help="Override local temp directory for CEFS staging",
    type=click.Path(file_okay=False, path_type=Path),
)
@click.pass_context
def cli(
    ctx: click.Context,
    dest: Path,
    staging_dir: Path,
    debug: bool,
    log_to_console: bool,
    log: str | None,
    s3_bucket: str,
    s3_dir: str,
    dry_run: bool,
    enable: list[str],
    only_nightly: bool,
    cache: Path | None,
    yaml_dir: Path,
    allow_unsafe_ssl: bool,
    resource_dir: Path,
    keep_staging: bool,
    filter_match_all: bool,
    parallel: int,
    check_user: str,
    force_cefs: bool,
    force_traditional: bool,
    cefs_temp_dir: Path | None,
):
    """Install binaries, libraries and compilers for Compiler Explorer."""
    formatter = logging.Formatter(fmt="%(asctime)s %(name)-15s %(levelname)-8s %(message)s")
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug else logging.INFO)
    if log:
        file_handler = logging.FileHandler(log)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    if not log or log_to_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    platform = LibraryPlatform.Linux
    if "windows" in enable:
        platform = LibraryPlatform.Windows

    """ keep staging relative to dest if not set by the user """
    staging_source = click.get_current_context().get_parameter_source("staging_dir")
    if staging_source == ParameterSource.DEFAULT:
        staging_dir = Path(f"{dest}/staging")

    config = Config.load(dest / "config.yaml").with_cli_overrides(
        force_cefs=force_cefs,
        force_traditional=force_traditional,
        cefs_temp_dir=cefs_temp_dir,
    )
    context = InstallationContext(
        destination=dest,
        staging_root=staging_dir,
        s3_url=f"https://s3.amazonaws.com/{s3_bucket}/{s3_dir}",
        dry_run=dry_run,
        is_nightly_enabled="nightly" in enable,
        only_nightly=only_nightly,
        cache=cache,
        yaml_dir=yaml_dir,
        allow_unsafe_ssl=allow_unsafe_ssl,
        resource_dir=resource_dir,
        keep_staging=keep_staging,
        check_user=check_user,
        platform=platform,
        config=config,
    )
    ctx.obj = CliContext(
        installation_context=context,
        enabled=enable,
        filter_match_all=filter_match_all,
        parallel=parallel,
        config=config,
    )


# Import CLI modules to register commands
from lib.cli import cefs, cpp_libraries, fortran_libraries  # noqa: F401, E402


def get_exe_path_for_installable(installable, destination) -> str | None:
    """Get the full executable path for an installable.

    Returns the path that would be used to look up compiler IDs in properties files.
    """
    if installable.check_call:
        # check_call[0] is the path to the executable (already includes install_path after resolution)
        return str(destination / installable.check_call[0])
    return None


@cli.command(name="list")
@click.pass_obj
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
@click.option("--installed-only", is_flag=True, help="Only output installed targets")
@click.option("--show-compiler-ids", is_flag=True, help="Show compiler IDs from CE properties files")
@click.argument("filter_", metavar="FILTER", nargs=-1)
def list_cmd(context: CliContext, filter_: list[str], as_json: bool, installed_only: bool, show_compiler_ids: bool):
    """List installation targets matching FILTER."""
    lookup = get_compiler_id_lookup() if show_compiler_ids else None
    json_output: list[dict] = []

    for installable in context.get_installables(filter_):
        if installed_only and not installable.is_installed():
            continue

        if as_json:
            output = installable.to_json_dict()
            if lookup is not None:
                exe_path = get_exe_path_for_installable(installable, context.installation_context.destination)
                if exe_path:
                    compiler_ids = lookup.get_compiler_ids(exe_path)
                    output["compiler_ids"] = sorted(compiler_ids) if compiler_ids else []
                else:
                    output["compiler_ids"] = []
            json_output.append(output)
        else:
            if lookup is not None:
                exe_path = get_exe_path_for_installable(installable, context.installation_context.destination)
                if exe_path:
                    compiler_ids = lookup.get_compiler_ids(exe_path)
                    if compiler_ids:
                        print(f"{installable.name}: {', '.join(sorted(compiler_ids))}")
                    else:
                        print(f"{installable.name}: (no compiler ID found)")
                else:
                    print(f"{installable.name}: (no exe path)")
            else:
                print(installable.name)
        _LOGGER.debug(installable)

    if as_json:
        print(json.dumps(json_output))


@cli.command()
@click.pass_obj
@click.argument("filter_", metavar="FILTER", nargs=-1)
def verify(context: CliContext, filter_: list[str]):
    """Verify the installations of targets matching FILTER."""
    num_ok = 0
    num_not_ok = 0
    for installable in context.get_installables(filter_):
        print(f"Checking {installable.name}")
        if not installable.is_installed():
            _LOGGER.info("%s is not installed", installable.name)
            num_not_ok += 1
        elif not installable.verify():
            _LOGGER.info("%s is not OK", installable.name)
            num_not_ok += 1
        else:
            num_ok += 1
    print(f"{num_ok} packages OK, {num_not_ok} not OK or not installed")
    if num_not_ok:
        sys.exit(1)


@cli.command(name="list-paths")
@click.pass_obj
@click.option("--json", "as_json", is_flag=True, help="Output in JSON format")
@click.option("--absolute", is_flag=True, help="Show absolute paths")
@click.argument("filter_", metavar="FILTER", nargs=-1)
def list_paths(context: CliContext, filter_: list[str], as_json: bool, absolute: bool):
    """List installation paths for targets matching FILTER without installing."""
    paths = {}
    for installable in context.get_installables(filter_):
        if absolute:
            # Combine with destination to get absolute path
            path = str(context.installation_context.destination / installable.install_path)
        else:
            # Relative path within the installation directory
            path = installable.install_path

        if as_json:
            paths[installable.name] = path
        else:
            print(f"{installable.name}: {path}")

    if as_json:
        print(json.dumps(paths, indent=2))


@cli.command()
@click.pass_obj
@click.argument("filter_", metavar="FILTER", nargs=-1)
def check_installed(context: CliContext, filter_: list[str]):
    """Check whether targets matching FILTER are installed."""
    for installable in context.get_installables(filter_):
        if installable.is_installed():
            print(f"{installable.name}: installed")
        else:
            print(f"{installable.name}: not installed")


@cli.command()
@click.pass_obj
@click.argument("filter_", metavar="FILTER", nargs=-1)
def check_should_install(context: CliContext, filter_: list[str]):
    """Check whether targets matching FILTER Should be installed."""
    for installable in context.get_installables(filter_):
        if installable.should_install():
            print(f"{installable.name}: yes")
        else:
            print(f"{installable.name}: no")


@cli.command()
def amazon_check():
    _LOGGER.debug("Starting Amazon Check")
    languages = ["c", "c++", "d", "cuda"]

    for language in languages:
        _LOGGER.info("Checking %s libraries", language)
        [_, libraries] = get_properties_compilers_and_libraries(language, _LOGGER, LibraryPlatform.Linux, True)

        for libraryid in libraries:
            _LOGGER.debug("Checking %s", libraryid)
            for lib_version in libraries[libraryid]["versionprops"]:
                includepaths = libraries[libraryid]["versionprops"][lib_version]["path"]
                for includepath in includepaths:
                    _LOGGER.debug("Checking for library %s %s: %s", libraryid, lib_version, includepath)
                    if not os.path.exists(includepath):
                        _LOGGER.error("Path missing for library %s %s: %s", libraryid, lib_version, includepath)
                    else:
                        _LOGGER.debug("Found path for library %s %s: %s", libraryid, lib_version, includepath)

                libpaths = libraries[libraryid]["versionprops"][lib_version]["libpath"]
                for libpath in libpaths:
                    _LOGGER.debug("Checking for library %s %s: %s", libraryid, lib_version, libpath)
                    if not os.path.exists(libpath):
                        _LOGGER.error("Path missing for library %s %s: %s", libraryid, lib_version, libpath)
                    else:
                        _LOGGER.debug("Found path for library %s %s: %s", libraryid, lib_version, libpath)


def _to_squash(image_dir: Path, force: bool, installable: Installable) -> tuple[Installable, Path] | None:
    if not installable.is_squashable:
        _LOGGER.info("%s isn't squashable; skipping", installable.name)
        return None
    if not installable.is_installed():
        _LOGGER.warning("%s wasn't installed; skipping squash", installable.name)
        return None

    # Check if source path is a symlink (indicates CEFS conversion)
    source_path = installable.install_context.destination / installable.install_path
    if source_path.is_symlink():
        _LOGGER.info("%s source path is a symlink (CEFS converted); skipping squash", installable.name)
        return None

    destination = image_dir / f"{installable.install_path}.img"
    if destination.exists() and not force:
        _LOGGER.info("Skipping %s as it already exists at %s", installable.name, destination)
        return None
    if installable.nightly_like:
        _LOGGER.info("Skipping %s as it looks like a nightly", installable.name)
        return None
    return installable, destination


@cli.command()
@click.pass_obj
@click.option("--force", is_flag=True, help="Force even if would otherwise skip")
@click.option(
    "--image-dir",
    default=None,
    metavar="IMAGES",
    type=click.Path(file_okay=False, path_type=Path),
    help="Build images to IMAGES",
)
@click.argument("filter_", metavar="FILTER", nargs=-1)
def squash(context: CliContext, filter_: list[str], force: bool, image_dir: Path | None):
    """Create squashfs images for all targets matching FILTER."""
    if not context.config.squashfs.traditional_enabled:
        _LOGGER.error("Squashfs is disabled in configuration")
        return

    if image_dir is None:
        image_dir = context.config.squashfs.image_dir

    with context.pool() as pool:
        should_install_func = partial(_to_squash, image_dir, force)
        to_do = filter(lambda x: x is not None, pool.map(should_install_func, context.get_installables(filter_)))

    for installable, destination in to_do:
        if context.installation_context.dry_run:
            _LOGGER.info("Would squash %s to %s", installable.name, destination)
        else:
            _LOGGER.info("Squashing %s to %s", installable.name, destination)
            installable.squash_to(destination, context.config.squashfs)


@cli.command()
@click.pass_obj
@click.option("--verify", is_flag=True, help="Verify squashfs contents match NFS directories")
@click.option("--no-check-mount-targets", is_flag=True, help="Skip checking mount targets exist")
@click.option(
    "--image-dir",
    default=None,
    metavar="IMAGES",
    type=click.Path(file_okay=False, path_type=Path),
    help="Look for images in IMAGES",
)
@click.argument("filter_", metavar="FILTER", nargs=-1)
def squash_check(
    context: CliContext, filter_: list[str], image_dir: Path | None, verify: bool, no_check_mount_targets: bool
):
    """Check squash images matching FILTER, optionally verify contents."""
    if image_dir is None:
        image_dir = context.config.squashfs.image_dir

    total_errors = 0

    if not image_dir.exists():
        _LOGGER.error("Missing squash directory %s", image_dir)
        sys.exit(1)

    # Check for missing/unexpected squash images
    installables = context.get_installables(filter_)
    for installable in installables:
        destination = image_dir / f"{installable.install_path}.img"
        if not installable.is_squashable:
            continue
        if installable.nightly_like:
            if destination.exists():
                _LOGGER.error("Found squash: %s for nightly", installable.name)
                total_errors += 1
        elif not destination.exists():
            _LOGGER.error("Missing squash: %s (for %s)", installable.name, destination)
            total_errors += 1
        elif verify:
            # Verify contents if requested
            nfs_path = context.installation_context.destination / installable.install_path
            _LOGGER.info("Verifying %s...", installable.name)
            total_errors += verify_squashfs_contents(destination, nfs_path)

    # Check mount points (unless disabled)
    if not no_check_mount_targets:
        total_errors += squash_mount_check(image_dir, "", context)

    # Summary and exit
    if total_errors > 0:
        _LOGGER.error("Found %d total errors", total_errors)
        sys.exit(1)
    else:
        _LOGGER.info("All checks passed")
        sys.exit(0)


def _should_install(force: bool, installable: Installable) -> tuple[Installable, bool]:
    try:
        return installable, force or installable.should_install()
    except (OSError, RuntimeError) as ex:
        raise RuntimeError(f"Unable to install {installable}") from ex


@cli.command()
@click.pass_obj
@click.option("--force", is_flag=True, help="Force even if would otherwise skip")
@click.argument("filter_", metavar="FILTER", nargs=-1)
def install(context: CliContext, filter_: list[str], force: bool):
    """Install targets matching FILTER."""
    num_installed = 0
    num_skipped = 0
    failed = []

    with context.pool() as pool:
        to_do = pool.map(partial(_should_install, force), context.get_installables(filter_))

    for installable, should_install in to_do:
        print(f"Installing {installable.name}")
        if should_install:
            try:
                installable.install()
                if context.installation_context.dry_run:
                    _LOGGER.info("Assuming %s installed OK (dry run)", installable.name)
                    num_installed += 1
                else:
                    if not installable.is_installed():
                        _LOGGER.error("%s installed OK, but doesn't appear as installed after", installable.name)
                        failed.append(installable.name)
                    else:
                        _LOGGER.info("%s installed OK", installable.name)
                        num_installed += 1
            except Exception as e:  # noqa: BLE001
                _LOGGER.info("%s failed to install: %s\n%s", installable.name, e, traceback.format_exc(5))
                failed.append(installable.name)
        else:
            _LOGGER.info("%s is already installed, skipping", installable.name)
            num_skipped += 1
    print(
        f"{num_installed} packages installed "
        f"{'(apparently; this was a dry-run) ' if context.installation_context.dry_run else ''}OK, "
        f"{num_skipped} skipped, and {len(failed)} failed installation"
    )
    if failed:
        print("Failed:")
        for f in sorted(failed):
            print(f"  {f}")
        sys.exit(1)


@cli.command()
@click.pass_obj
@click.option("--force", is_flag=True, help="Force even if would otherwise skip")
@click.option(
    "--buildfor",
    default="",
    metavar="BUILDFOR",
    help="Filter to only build for given compiler (should be a CE compiler identifier), leave empty to build for all",
)
@click.option("--popular-compilers-only", is_flag=True, help="Only build with popular (enough) compilers")
@click.option("--temp-install", is_flag=True, help="Temporary install target if it's not installed yet")
@click.argument("filter_", metavar="FILTER", nargs=-1)
def build(
    context: CliContext,
    filter_: list[str],
    force: bool,
    buildfor: str,
    popular_compilers_only: bool,
    temp_install: bool,
):
    """Build library targets matching FILTER."""
    num_installed = 0
    num_skipped = 0
    num_failed = 0

    platform = LibraryPlatform.Linux

    if "windows" in context.enabled:
        platform = LibraryPlatform.Windows

    for installable in context.get_installables(filter_):
        if buildfor:
            print(f"Building {installable.name} ({platform.value}) just for {buildfor}")
        else:
            print(f"Building {installable.name} ({platform.value}) for all")

        if force or installable.should_build(platform):
            was_temp_installed = False

            if not installable.is_installed() and temp_install:
                _LOGGER.info("Temporarily installing %s", installable.name)
                saved_dry_run = context.installation_context.dry_run
                context.installation_context.dry_run = False
                try:
                    installable.install()
                    was_temp_installed = True
                except FetchFailure:
                    num_failed += 1
                    continue
                finally:
                    context.installation_context.dry_run = saved_dry_run

            if not installable.is_installed() and not was_temp_installed:
                _LOGGER.info("%s is not installed, unable to build", installable.name)
                num_skipped += 1
            else:
                try:
                    # Pass "forceall" to force rebuild when --force is specified without --buildfor
                    effective_buildfor = buildfor if buildfor else ("forceall" if force else "")
                    [num_installed, num_skipped, num_failed] = installable.build(
                        effective_buildfor, popular_compilers_only, platform
                    )
                    if num_installed > 0:
                        _LOGGER.info("%s built OK", installable.name)
                    elif num_failed:
                        _LOGGER.info("%s failed to build", installable.name)
                    elif num_skipped == 0:
                        _LOGGER.info("%s hit a BUG", installable.name)
                except RuntimeError as e:
                    if buildfor:
                        raise e
                    else:
                        _LOGGER.info("%s failed to build: %s", installable.name, e)
                        num_failed += 1

            if was_temp_installed:
                _LOGGER.info("Uninstalling temporary %s", installable.name)
                installable.uninstall()
        else:
            _LOGGER.info("%s does not have to build, skipping", installable.name)
            num_skipped += 1
    print(f"{num_installed} packages built OK, {num_skipped} skipped, and {num_failed} failed build")
    if num_failed:
        sys.exit(1)


@cli.command()
@click.pass_obj
def reformat(context: CliContext):
    """Reformat the YAML."""
    lib_yaml = LibraryYaml(context.installation_context.yaml_dir)
    lib_yaml.reformat()


@cli.command()
@click.pass_obj
def add_top_rust_crates(context: CliContext):
    """Add configuration for the top 100 rust crates."""
    libyaml = LibraryYaml(context.installation_context.yaml_dir)
    libyaml.add_top_rust_crates()
    libyaml.save()


@cli.command()
@click.pass_obj
def generate_rust_props(context: CliContext):
    """Generate Rust property files for crates."""
    propfile = Path(os.path.join(os.curdir, "props"))
    with propfile.open(mode="w", encoding="utf-8") as file:
        libyaml = LibraryYaml(context.installation_context.yaml_dir)
        props = libyaml.get_ce_properties_for_rust_libraries()
        file.write(props)


@cli.command()
@click.pass_obj
@click.argument("libid")
@click.argument("libversion")
def add_crate(context: CliContext, libid: str, libversion: str):
    """Add crate LIBID version LIBVERSION."""
    libyaml = LibraryYaml(context.installation_context.yaml_dir)
    libyaml.add_rust_crate(libid, libversion)
    libyaml.save()


@cli.command()
@click.pass_obj
def generate_cpp_windows_props(context: CliContext):
    """Generate Cpp for Windows property files for libraries."""
    propfile = Path(os.path.join(os.curdir, "props"))
    with propfile.open(mode="w", encoding="utf-8") as file:
        libyaml = LibraryYaml(context.installation_context.yaml_dir)
        props = libyaml.get_ce_properties_for_cpp_windows_libraries(logging.getLogger())
        file.write(props)


@cli.command(name="list-gh-build-commands")
@click.pass_obj
@click.option("--per-lib", is_flag=True, help="Group by library instead of version")
@click.argument("filter_", metavar="FILTER", nargs=-1)
def list_gh_build_commands(context: CliContext, per_lib: bool, filter_: list[str]):
    """List gh workflow commands matching FILTER."""
    grouped = set()

    if per_lib:
        for installable in context.get_installables(filter_):
            if not installable.should_build(LibraryPlatform.Windows):
                continue
            shorter_name = installable.name.replace("libraries/c++/", "").split(" ")[0]
            grouped.add(shorter_name)

        for group in grouped:
            print(f'gh workflow run win-lib-build.yaml --field "library={group}" -R github.com/compiler-explorer/infra')
    else:
        for installable in context.get_installables(filter_):
            if not installable.should_build(LibraryPlatform.Windows):
                continue
            shorter_name = installable.name.replace("libraries/c++/", "")
            print(
                f'gh workflow run win-lib-build.yaml --field "library={shorter_name}" -R github.com/compiler-explorer/infra'
            )


@cli.command(name="list-gh-build-commands-linux")
@click.pass_obj
@click.option("--per-lib", is_flag=True, help="Group by library instead of version")
@click.argument("filter_", metavar="FILTER", nargs=-1)
def list_gh_build_commands_linux(context: CliContext, per_lib: bool, filter_: list[str]):
    """List gh workflow commands for Linux builds matching FILTER."""
    grouped = set()

    if per_lib:
        for installable in context.get_installables(filter_):
            if not installable.should_build(LibraryPlatform.Linux):
                continue
            shorter_name = installable.name.replace("libraries/c++/", "").split(" ")[0]
            grouped.add(shorter_name)

        for group in grouped:
            print(f'gh workflow run lin-lib-build.yaml --field "library={group}" -R github.com/compiler-explorer/infra')
    else:
        for installable in context.get_installables(filter_):
            if not installable.should_build(LibraryPlatform.Linux):
                continue
            shorter_name = installable.name.replace("libraries/c++/", "")
            print(
                f'gh workflow run lin-lib-build.yaml --field "library={shorter_name}" -R github.com/compiler-explorer/infra'
            )


@cli.command()
@click.argument("output", type=click.File("w", encoding="utf-8"), default="-")
@click.pass_obj
def config_dump(context: CliContext, output: TextIO):
    """Dumps all config, expanded."""
    for yaml_path in sorted(Path(context.installation_context.yaml_dir).glob("*.yaml")):
        with yaml_path.open(encoding="utf-8") as yaml_file:
            yaml_doc = yaml.load(yaml_file, Loader=ConfigSafeLoader)
        for installer in sorted(installers_for(context.installation_context, yaml_doc, True), key=str):
            # Read all public strings fields from installer
            as_dict = {
                "name": installer.name,
                "type": str(installer),
                "config": {
                    field: getattr(installer, field)
                    for field in dir(installer)
                    if not field.startswith("_") and isinstance(getattr(installer, field), str)
                },
            }
            output.write(json.dumps(as_dict) + "\n")


def main():
    cli(prog_name="ce_install")


if __name__ == "__main__":
    main()
