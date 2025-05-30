import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

import click

from lib.library_props import (
    extract_library_id_from_github_url,
    find_existing_library_by_github_url,
    generate_library_property_key,
    generate_version_property_key,
    parse_properties_file,
    should_skip_library,
    update_library_in_properties,
    version_to_id,
)
from lib.library_yaml import LibraryYaml

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
    # Extract library ID from GitHub URL
    try:
        lib_id = extract_library_id_from_github_url(github_url)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

    # Parse GitHub URL to get repo field
    parsed = urlparse(github_url)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        click.echo(f"Error: Invalid GitHub URL format: {github_url}", err=True)
        sys.exit(1)
    repo_field = f"{path_parts[0]}/{path_parts[1]}"

    # Load libraries.yaml
    yaml_dir = Path(__file__).parent.parent.parent / "yaml"
    library_yaml = LibraryYaml(str(yaml_dir))

    # Ensure fortran section exists
    if "fortran" not in library_yaml.yaml_doc["libraries"]:
        library_yaml.yaml_doc["libraries"]["fortran"] = {}

    fortran_libraries = library_yaml.yaml_doc["libraries"]["fortran"]

    # Check if library already exists by GitHub URL
    existing_lib_id = find_existing_library_by_github_url(fortran_libraries, github_url)

    if existing_lib_id:
        # Library exists, check if it's in main section or nightly
        if existing_lib_id in fortran_libraries:
            # Library is in main section
            lib_id = existing_lib_id
            if version not in fortran_libraries[lib_id]["targets"]:
                fortran_libraries[lib_id]["targets"].append(version)
                click.echo(f"Added version {version} to existing library {lib_id}")

                # Update target_prefix if specified and not already set
                if target_prefix and "target_prefix" not in fortran_libraries[lib_id]:
                    fortran_libraries[lib_id]["target_prefix"] = target_prefix
                    click.echo(f"Added target_prefix '{target_prefix}' to library {lib_id}")
            else:
                click.echo(f"Version {version} already exists for library {lib_id}")
        else:
            # Library exists in nightly section - this is a conflict
            click.echo(
                f"Error: A library with the same GitHub repository already exists in the nightly section as '{existing_lib_id}'. "
                f"Please use a different library name or update the nightly version instead.",
                err=True,
            )
            sys.exit(1)
    elif lib_id in fortran_libraries:
        # Library ID exists but with different GitHub URL
        click.echo(
            f"Error: Library ID '{lib_id}' already exists with different repository: "
            f"{fortran_libraries[lib_id].get('repo', 'unknown')}",
            err=True,
        )
        sys.exit(1)
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
    if version and not library:
        click.echo("Error: --version requires --library to be specified", err=True)
        sys.exit(1)

    # Load libraries.yaml
    yaml_dir = Path(__file__).parent.parent.parent / "yaml"
    library_yaml = LibraryYaml(str(yaml_dir))

    # Check if there are any Fortran libraries
    if "fortran" not in library_yaml.yaml_doc["libraries"]:
        click.echo("No Fortran libraries found in libraries.yaml")
        return

    fortran_libraries = library_yaml.yaml_doc["libraries"]["fortran"]

    if library:
        # Check if the specified library exists
        if library not in fortran_libraries:
            click.echo(f"Error: Library '{library}' not found in libraries.yaml", err=True)
            sys.exit(1)

        # Generate properties for specific library only
        lib_info = fortran_libraries[library]
        lib_props = generate_single_fortran_library_properties(library, lib_info, specific_version=version)

        if input_file:
            # Load existing properties file
            with open(input_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # Update only the specific library
            update_version_id = None
            if version:
                update_version_id = version_to_id(version)
            result = update_library_in_properties(
                existing_content, library, lib_props, update_version_id
            )

            # If the library wasn't in the libs= list, we need to add it
            if f"libs.{library}." not in existing_content:
                # Preserve whether original content had final newline
                original_ends_with_newline = existing_content.endswith("\n")

                lines = result.splitlines()
                for i, line in enumerate(lines):
                    if line.strip().startswith("libs="):
                        # Parse existing libs
                        if "=" in line:
                            prefix, libs_value = line.split("=", 1)
                            existing_libs = [lib for lib in libs_value.split(":") if lib]
                            if library not in existing_libs:
                                existing_libs.append(library)
                                lines[i] = f"{prefix}={':'.join(existing_libs)}"
                        break
                result = "\n".join(lines)
                # Preserve original final newline behavior
                if original_ends_with_newline and not result.endswith("\n"):
                    result += "\n"
        else:
            # Generate standalone properties for just this library
            result = generate_standalone_fortran_library_properties(library, lib_props, specific_version=version)
    else:
        # Generate properties for all libraries
        new_properties_text = generate_all_fortran_libraries_properties(fortran_libraries)

        if input_file:
            # Load existing properties file
            with open(input_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # Merge properties
            from lib.library_props import merge_properties
            merged_content = merge_properties(existing_content, new_properties_text)
            result = merged_content
        else:
            result = new_properties_text

    # Output
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(result)
        click.echo(f"Properties written to {output_file}")
    else:
        click.echo(result)


def generate_single_fortran_library_properties(library_name, lib_info, specific_version=None):
    """Generate properties for a single Fortran library."""
    lib_props = {}

    if "targets" in lib_info and lib_info["targets"]:
        if specific_version:
            # Only generate properties for the specific version
            if specific_version not in lib_info["targets"]:
                raise ValueError(f"Version '{specific_version}' not found for library '{library_name}'")

            ver_id = version_to_id(specific_version)
            lib_props[f"versions.{ver_id}.version"] = specific_version

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

                lib_props[f"versions.{ver_id}.version"] = version

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

        libverprops = f"libs.{lib_id}.name={lib_id}\n"

        if lib_info.get("type") == "github" and "repo" in lib_info:
            libverprops += f"libs.{lib_id}.url=https://github.com/{lib_info['repo']}\n"

        # Add Fortran-specific properties
        libverprops += f"libs.{lib_id}.packagedheaders=true\n"
        libverprops += f"libs.{lib_id}.staticliblink={lib_id}\n"

        if "targets" in lib_info and lib_info["targets"]:
            version_ids = []
            for version in lib_info["targets"]:
                ver_id = version_to_id(version)
                version_ids.append(ver_id)

            libverprops += f"libs.{lib_id}.versions={':'.join(version_ids)}\n"

            for version in lib_info["targets"]:
                ver_id = version_to_id(version)
                libverprops += f"libs.{lib_id}.versions.{ver_id}.version={version}\n"

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
        properties_lines.append(f"libs.{library_name}.{prop_name}={value}")

    return "\n".join(properties_lines)