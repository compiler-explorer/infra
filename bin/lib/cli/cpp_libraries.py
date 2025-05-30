import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

import click

from lib.library_props import (
    extract_library_id_from_github_url,
    find_existing_library_by_github_url,
    generate_all_libraries_properties,
    generate_single_library_properties,
    generate_standalone_library_properties,
    merge_properties,
    update_library_in_properties,
    version_to_id,
)
from lib.library_yaml import LibraryYaml

from .cli import cli


@cli.group()
def cpp_library():
    """C++ library management commands."""


@cpp_library.command(name="add")
@click.argument("github_url")
@click.argument("version")
@click.option(
    "--type",
    type=click.Choice(["header-only", "packaged-headers", "static", "shared"]),
    default="header-only",
    help="Library type (default: header-only)",
)
def add_cpp_library(github_url: str, version: str, type: str):
    """Add or update a C++ library entry in libraries.yaml."""
    # Load libraries.yaml first to search for existing library
    yaml_dir = Path(__file__).parent.parent.parent / "yaml"
    library_yaml = LibraryYaml(str(yaml_dir))

    # Ensure c++ section exists
    if "c++" not in library_yaml.yaml_doc["libraries"]:
        library_yaml.yaml_doc["libraries"]["c++"] = {}

    cpp_libraries = library_yaml.yaml_doc["libraries"]["c++"]

    # Search for existing library by GitHub URL
    existing_lib_id = find_existing_library_by_github_url(cpp_libraries, github_url)

    if existing_lib_id:
        lib_id = existing_lib_id
        # Extract repo field from existing library
        repo_field = cpp_libraries[lib_id].get("repo", "")
    else:
        # Extract library ID from GitHub URL for new library
        try:
            lib_id = extract_library_id_from_github_url(github_url)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        # Extract owner and repo from URL for the repo field
        parsed = urlparse(github_url)
        path_parts = parsed.path.strip("/").split("/")
        repo_field = f"{path_parts[0]}/{path_parts[1]}"

    # Check if library already exists
    if lib_id in cpp_libraries:
        # Add version to existing library
        if "targets" not in cpp_libraries[lib_id]:
            cpp_libraries[lib_id]["targets"] = []

        if version not in cpp_libraries[lib_id]["targets"]:
            cpp_libraries[lib_id]["targets"].append(version)
            if existing_lib_id:
                click.echo(f"Found existing library '{lib_id}' for {github_url}")
            click.echo(f"Added version {version} to library {lib_id}")
        else:
            click.echo(f"Version {version} already exists for library {lib_id}")
    else:
        # Create new library entry
        library_entry = {
            "type": "github",
            "repo": repo_field,
            "check_file": "README.md",  # Default check file
            "targets": [version],
        }

        # Set properties based on library type
        if type == "packaged-headers":
            library_entry["build_type"] = "cmake"
            library_entry["lib_type"] = "headeronly"
            library_entry["package_install"] = True
        elif type == "header-only":
            # Header-only libraries typically don't need build_type
            pass
        elif type == "static":
            library_entry["build_type"] = "cmake"
            library_entry["lib_type"] = "static"
        elif type == "shared":
            library_entry["build_type"] = "cmake"
            library_entry["lib_type"] = "shared"

        cpp_libraries[lib_id] = library_entry
        click.echo(f"Added new library {lib_id} with version {version}")

    # Save the updated YAML
    library_yaml.save()
    click.echo(f"Successfully updated {library_yaml.yaml_path}")


@cpp_library.command(name="generate-windows-props")
@click.option("--input-file", type=click.Path(exists=True), help="Existing properties file to update")
@click.option("--output-file", type=click.Path(), help="Output file (defaults to stdout)")
@click.option("--library", help="Only update this specific library")
@click.option("--version", help="Only update this specific version (requires --library)")
def generate_cpp_windows_props(input_file, output_file, library, version):
    """Generate C++ Windows properties file from libraries.yaml."""
    if version and not library:
        click.echo("Error: --version requires --library to be specified", err=True)
        sys.exit(1)

    # Load libraries.yaml
    yaml_dir = Path(__file__).parent.parent.parent / "yaml"
    library_yaml = LibraryYaml(str(yaml_dir))

    # Check if there are any C++ libraries
    if "c++" not in library_yaml.yaml_doc["libraries"]:
        click.echo("No C++ libraries found in libraries.yaml")
        return

    if library:
        # Generate properties for specific library only
        # For now, we'll need to use the Linux generator and adapt it
        # since get_ce_properties_for_cpp_windows_libraries doesn't support filtering
        click.echo("Filtering by library for Windows properties is not yet implemented", err=True)
        sys.exit(1)
    else:
        # Generate properties using the existing method
        logger = logging.getLogger()
        new_properties_text = library_yaml.get_ce_properties_for_cpp_windows_libraries(logger)

    if input_file:
        # Load existing properties file
        with open(input_file, "r", encoding="utf-8") as f:
            existing_content = f.read()

        # Merge properties
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


@cpp_library.command(name="generate-linux-props")
@click.option("--input-file", type=click.Path(exists=True), help="Existing properties file to update")
@click.option("--output-file", type=click.Path(), help="Output file (defaults to stdout)")
@click.option("--library", help="Only update this specific library")
@click.option("--version", help="Only update this specific version (requires --library)")
def generate_cpp_linux_props(input_file, output_file, library, version):
    """Generate C++ Linux properties file from libraries.yaml."""
    if version and not library:
        click.echo("Error: --version requires --library to be specified", err=True)
        sys.exit(1)

    # Load libraries.yaml
    yaml_dir = Path(__file__).parent.parent.parent / "yaml"
    library_yaml = LibraryYaml(str(yaml_dir))

    # Check if there are any C++ libraries
    if "c++" not in library_yaml.yaml_doc["libraries"]:
        click.echo("No C++ libraries found in libraries.yaml")
        return

    cpp_libraries = library_yaml.yaml_doc["libraries"]["c++"]

    if library:
        # Check if the specified library exists
        if library not in cpp_libraries:
            click.echo(f"Error: Library '{library}' not found in libraries.yaml", err=True)
            sys.exit(1)

        # Generate properties for specific library only
        lib_info = cpp_libraries[library]

        # Check if library should be skipped
        if lib_info.get("build_type") in ["manual", "none", "never"]:
            click.echo(
                f"Warning: Library '{library}' has build_type '{lib_info.get('build_type')}' and would normally be skipped",
                err=True,
            )

        # Generate properties for this library using the refactored function
        try:
            lib_props = generate_single_library_properties(library, lib_info, specific_version=version)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        if input_file:
            # Load existing properties file
            with open(input_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # Update only the specific library
            # If we're updating a specific version, pass the version ID
            update_version_id = None
            if version:
                update_version_id = version_to_id(version)
            result = update_library_in_properties(existing_content, library, lib_props, update_version_id)

            # If the library wasn't in the libs= list, we need to add it
            if f"libs.{library}." not in existing_content:
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
        else:
            # Generate standalone properties for just this library
            # When generating standalone (no input file), include all properties
            if version and "name" not in lib_props:
                # Add library-level properties for standalone generation
                lib_props["name"] = library
                if lib_info.get("type") == "github" and "repo" in lib_info:
                    lib_props["url"] = f"https://github.com/{lib_info['repo']}"

            result = generate_standalone_library_properties(library, lib_props, specific_version=version)
    else:
        # Generate properties for all libraries using the refactored function
        new_properties_text = generate_all_libraries_properties(cpp_libraries)

        if input_file:
            # Load existing properties file
            with open(input_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # Merge properties
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
