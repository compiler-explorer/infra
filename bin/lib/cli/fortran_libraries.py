import logging
import sys

import click

from lib.library_props import (
    add_version_to_library,
    extract_library_id_from_github_url,
    extract_repo_from_github_url,
    find_existing_library_by_github_url,
    generate_library_property_key,
    generate_version_property_key,
    generate_version_property_suffix,
    load_library_yaml_section,
    output_properties,
    process_all_libraries_properties,
    process_library_specific_properties,
    should_skip_library,
    validate_library_version_args,
    version_to_id,
)

from ..ce_install import cli

_LOGGER = logging.getLogger(__name__)


@cli.group()
def fortran_library():
    """Fortran library management commands."""


@fortran_library.command(name="add")
@click.argument("github_url")
@click.argument("version")
@click.option(
    "--target-prefix",
    default="",
    help="Prefix for version tags (e.g., 'v' for tags like v3.11.3)",
)
def add_fortran_library(github_url, version, target_prefix):
    """Add a new Fortran library from GitHub URL with version.

    All Fortran libraries use FPM (Fortran Package Manager) for building.
    """
    # Load libraries.yaml and get Fortran section
    library_yaml, fortran_libraries = load_library_yaml_section("fortran")

    # Search for existing library by GitHub URL
    existing_lib_id = find_existing_library_by_github_url(fortran_libraries, github_url)

    if existing_lib_id:
        lib_id = existing_lib_id
        # Extract repo field from existing library
        repo_field = fortran_libraries[lib_id].get("repo", "")
    else:
        # Extract library ID from GitHub URL for new library
        try:
            lib_id = extract_library_id_from_github_url(github_url)
            repo_field = extract_repo_from_github_url(github_url)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

    # Check if library already exists
    if lib_id in fortran_libraries:
        # Add version to existing library
        if existing_lib_id:
            click.echo(f"Found existing library '{lib_id}' for {github_url}")

        message = add_version_to_library(fortran_libraries, lib_id, version, target_prefix)
        click.echo(message)
    else:
        # Create new library entry with FPM defaults
        library_entry = {
            "type": "github",
            "repo": repo_field,
            "build_type": "fpm",
            "check_file": "fpm.toml",
            "requires_tree_copy": True,  # Common for FPM libraries
            "targets": [version],
        }

        # Add target_prefix if specified
        if target_prefix:
            library_entry["target_prefix"] = target_prefix

        fortran_libraries[lib_id] = library_entry
        click.echo(f"Added new Fortran library {lib_id} with version {version}")

    # Save the updated YAML
    library_yaml.save()
    click.echo(f"Successfully updated {library_yaml.yaml_path}")
    click.echo(f"\nLibrary '{lib_id}' is now available for property generation.")
    click.echo("To update the properties file, run:")
    click.echo(f"  ce_install fortran-library generate-props --library {lib_id} --version {version} \\")
    click.echo("    --input-file <ce-repo>/etc/config/fortran.properties \\")
    click.echo("    --output-file <ce-repo>/etc/config/fortran.properties")


@fortran_library.command(name="generate-props")
@click.option("--input-file", type=click.Path(exists=True), help="Existing properties file to update")
@click.option("--output-file", type=click.Path(), help="Output file (defaults to stdout)")
@click.option("--library", help="Only update this specific library")
@click.option("--version", help="Only update this specific version (requires --library)")
def generate_fortran_props(input_file, output_file, library, version):
    """Generate Fortran properties file from libraries.yaml."""
    # Validate arguments
    error = validate_library_version_args(library, version)
    if error:
        click.echo(error, err=True)
        sys.exit(1)

    # Load libraries.yaml and get Fortran section
    library_yaml, fortran_libraries = load_library_yaml_section("fortran")

    # Check if there are any Fortran libraries
    if not fortran_libraries:
        click.echo("No Fortran libraries found in libraries.yaml")
        return

    if library:
        # Check if the specified library exists
        if library not in fortran_libraries:
            click.echo(f"Error: Library '{library}' not found in libraries.yaml", err=True)
            sys.exit(1)

        # Generate properties for specific library only
        lib_info = fortran_libraries[library]
        lib_props = generate_single_fortran_library_properties(library, lib_info, specific_version=version)

        result = process_library_specific_properties(
            input_file, library, lib_props, version, generate_standalone_fortran_library_properties
        )
    else:
        # Generate properties for all libraries
        new_properties_text = generate_all_fortran_libraries_properties(fortran_libraries)
        result = process_all_libraries_properties(input_file, new_properties_text)

    # Output
    message = output_properties(result, output_file)
    if message:
        click.echo(message)


def generate_single_fortran_library_properties(library_name, lib_info, specific_version=None):
    """Generate properties for a single Fortran library."""
    lib_props = {}

    if "targets" in lib_info and lib_info["targets"]:
        if specific_version:
            # Only generate properties for the specific version
            if specific_version not in lib_info["targets"]:
                raise ValueError(f"Version '{specific_version}' not found for library '{library_name}'")

            ver_id = version_to_id(specific_version)
            version_suffix = generate_version_property_suffix(ver_id, "version")
            lib_props[version_suffix] = specific_version

            # No path for Fortran libraries - they use packagedheaders=true
        else:
            # Generate properties for all versions
            lib_props["name"] = library_name

            if lib_info.get("type") == "github" and "repo" in lib_info:
                lib_props["url"] = f"https://github.com/{lib_info['repo']}"

            # Add Fortran-specific properties
            lib_props["packagedheaders"] = "true"
            lib_props["staticliblink"] = library_name  # Use library name as default

            version_ids = []
            for version in lib_info["targets"]:
                ver_id = version_to_id(version)
                version_ids.append(ver_id)

                version_suffix = generate_version_property_suffix(ver_id, "version")
                lib_props[version_suffix] = version

                # No path for Fortran libraries

            lib_props["versions"] = ":".join(version_ids)
    else:
        # No targets specified, but we still need basic properties when not updating
        if not specific_version:
            lib_props["name"] = library_name
            if lib_info.get("type") == "github" and "repo" in lib_info:
                lib_props["url"] = f"https://github.com/{lib_info['repo']}"

            # Add Fortran-specific properties even without targets
            lib_props["packagedheaders"] = "true"
            lib_props["staticliblink"] = library_name

    return lib_props


def generate_all_fortran_libraries_properties(fortran_libraries):
    """Generate properties for all Fortran libraries."""
    all_ids = []
    properties_txt = ""

    for lib_id, lib_info in fortran_libraries.items():
        if should_skip_library(lib_id, lib_info):
            continue

        all_ids.append(lib_id)

        name_key = generate_library_property_key(lib_id, "name")
        libverprops = f"{name_key}={lib_id}\n"

        if lib_info.get("type") == "github" and "repo" in lib_info:
            url_key = generate_library_property_key(lib_id, "url")
            libverprops += f"{url_key}=https://github.com/{lib_info['repo']}\n"

        # Add Fortran-specific properties
        packagedheaders_key = generate_library_property_key(lib_id, "packagedheaders")
        libverprops += f"{packagedheaders_key}=true\n"
        staticliblink_key = generate_library_property_key(lib_id, "staticliblink")
        libverprops += f"{staticliblink_key}={lib_id}\n"

        if "targets" in lib_info and lib_info["targets"]:
            version_ids = []
            for version in lib_info["targets"]:
                ver_id = version_to_id(version)
                version_ids.append(ver_id)

            versions_key = generate_library_property_key(lib_id, "versions")
            libverprops += f"{versions_key}={':'.join(version_ids)}\n"

            for version in lib_info["targets"]:
                ver_id = version_to_id(version)
                version_key = generate_version_property_key(lib_id, ver_id, "version")
                libverprops += f"{version_key}={version}\n"

                # No path for Fortran libraries

        properties_txt += libverprops + "\n"

    header_properties_txt = "libs=" + ":".join(all_ids) + "\n\n"
    return header_properties_txt + properties_txt


def generate_standalone_fortran_library_properties(library_name, lib_props, specific_version=None):
    """Generate standalone properties for a single Fortran library."""
    properties_lines = []
    properties_lines.append(f"libs={library_name}")
    properties_lines.append("")

    for prop_name, value in sorted(lib_props.items()):
        property_key = generate_library_property_key(library_name, prop_name)
        properties_lines.append(f"{property_key}={value}")

    return "\n".join(properties_lines)
