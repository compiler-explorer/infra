import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

import click

from lib.library_yaml import LibraryYaml

from .cli import cli


def generate_library_path(library_name, version):
    """Generate the standard library path for Compiler Explorer."""
    return f"/opt/compiler-explorer/libs/{library_name}/{version}/include"


def generate_version_property_key(library_name, version_id, property_name):
    """Generate a property key for a library version."""
    return f"libs.{library_name}.versions.{version_id}.{property_name}"


def generate_library_property_key(library_name, property_name):
    """Generate a property key for a library."""
    return f"libs.{library_name}.{property_name}"


def version_to_id(version):
    """Convert a version string to a version ID by removing dots."""
    return version.replace(".", "")


def extract_library_id_from_github_url(github_url):
    """Extract library ID from GitHub URL."""
    parsed = urlparse(github_url)
    if parsed.netloc != "github.com":
        raise ValueError(f"URL must be a GitHub URL, got: {github_url}")

    # Extract repo name from path (format: /owner/repo)
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError(f"Invalid GitHub URL format: {github_url}")

    repo_name = path_parts[1]
    # Convert to lowercase and replace hyphens with underscores
    return repo_name.lower().replace("-", "_")


def parse_properties_file(content):
    """Parse a properties file into a dictionary."""
    properties = {}

    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if "=" in line:
            key, value = line.split("=", 1)
            properties[key] = value

    return properties


def update_library_in_properties(existing_content, library_name, library_properties):
    """Update a single library in the properties content.

    Args:
        existing_content: The existing properties file content
        library_name: Name of the library to update
        library_properties: Dict of properties for this library (without the libs.{library_name} prefix)

    Returns:
        Updated content with the library properties merged
    """

    # Sort properties by type (base props, then versions, then version details)
    def sort_key(item):
        prop_name = item[0]
        if prop_name == "name":
            return (0, prop_name)
        elif prop_name == "url":
            return (1, prop_name)
        elif prop_name == "versions":
            return (2, prop_name)
        elif prop_name.startswith("versions."):
            return (3, prop_name)
        else:
            return (4, prop_name)

    # Check if this is a single version update
    update_version_id = library_properties.pop("_update_version_id", None)

    lines = existing_content.splitlines()
    result_lines = []

    # Track which properties we've already seen for this library
    seen_props = set()
    inside_library_block = False
    last_library_line_idx = -1
    existing_versions = []

    # First pass: update existing properties and track what we've seen
    for _i, line in enumerate(lines):
        stripped = line.strip()

        # Check if this line is a property for our library
        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0]
            if key.startswith(f"libs.{library_name}."):
                inside_library_block = True
                last_library_line_idx = len(result_lines)

                # Extract the property name without the library prefix
                prop_name = key[len(f"libs.{library_name}.") :]
                seen_props.add(prop_name)

                # Special handling for versions line when updating a single version
                if prop_name == "versions" and update_version_id:
                    # Parse existing versions
                    if "=" in stripped:
                        _, versions_value = stripped.split("=", 1)
                        existing_versions = versions_value.split(":")

                    # Check if version needs to be added
                    if update_version_id not in existing_versions:
                        existing_versions.append(update_version_id)

                        # Sort version IDs numerically where possible
                        def version_sort_key(v):
                            try:
                                # Try to extract numeric part for sorting
                                return int("".join(filter(str.isdigit, v)) or "0")
                            except ValueError:
                                return v

                        existing_versions.sort(key=version_sort_key)
                        result_lines.append(f"{key}={':'.join(existing_versions)}")
                    else:
                        # Version already exists, keep the line as is
                        result_lines.append(line)
                    continue

                # If we have a new value for this property, use it
                if prop_name in library_properties:
                    result_lines.append(f"{key}={library_properties[prop_name]}")
                else:
                    result_lines.append(line)
                continue
            elif inside_library_block and key.startswith("libs.") and not key.startswith(f"libs.{library_name}."):
                # We've moved to a different library
                inside_library_block = False

        result_lines.append(line)

    # Find properties that need to be added
    props_to_add = []
    for prop_name, value in library_properties.items():
        if prop_name not in seen_props and not prop_name.startswith("_"):
            props_to_add.append((prop_name, value))

    # If we have properties to add
    if props_to_add:
        if last_library_line_idx >= 0:
            # Insert after the last property of this library
            insert_idx = last_library_line_idx + 1

            props_to_add.sort(key=sort_key)

            # Insert the new properties
            for prop_name, value in reversed(props_to_add):
                full_key = f"libs.{library_name}.{prop_name}"
                result_lines.insert(insert_idx, f"{full_key}={value}")
        else:
            # Library doesn't exist yet, add it at the end
            if result_lines and result_lines[-1].strip() != "":
                result_lines.append("")

            # Sort properties for new library
            props_to_add.sort(key=sort_key)

            for prop_name, value in props_to_add:
                full_key = f"libs.{library_name}.{prop_name}"
                result_lines.append(f"{full_key}={value}")

    return "\n".join(result_lines)


def merge_properties(existing_content, new_content):
    """Merge new properties into existing properties file, preserving structure and comments."""
    # Parse both property sets
    new_props = parse_properties_file(new_content)

    # Extract library list from new properties
    new_libs_list = []
    if "libs" in new_props:
        new_libs_list = new_props["libs"].split(":")

    # Start with the existing content
    result_content = existing_content

    # Update the libs= line first
    lines = result_content.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("libs="):
            existing_libs = []
            if "=" in line.strip():
                _, value = line.strip().split("=", 1)
                existing_libs = [lib for lib in value.split(":") if lib]

            # Merge library lists
            merged_libs = existing_libs.copy()
            for lib in new_libs_list:
                if lib not in merged_libs:
                    merged_libs.append(lib)

            lines[i] = f"libs={':'.join(merged_libs)}"
            result_content = "\n".join(lines)
            break

    # Group new properties by library
    libraries_to_update = {}

    for key, value in new_props.items():
        if key.startswith("libs.") and "." in key[5:]:
            # This is a library property
            parts = key.split(".")
            lib_name = parts[1]
            prop_name = ".".join(parts[2:])  # Handle nested properties like versions.120.version

            if lib_name not in libraries_to_update:
                libraries_to_update[lib_name] = {}

            libraries_to_update[lib_name][prop_name] = value

    # Update each library
    for lib_name, lib_props in libraries_to_update.items():
        result_content = update_library_in_properties(result_content, lib_name, lib_props)

    # Clean up any double empty lines
    lines = result_content.splitlines()
    cleaned_lines = []
    prev_empty = False
    for line in lines:
        if line.strip() == "":
            if not prev_empty:
                cleaned_lines.append(line)
            prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False

    return "\n".join(cleaned_lines)


def generate_single_library_properties(library_name, lib_info, specific_version=None, for_update=False):
    """Generate properties for a single library.

    Args:
        library_name: Name of the library
        lib_info: Library information from libraries.yaml
        specific_version: If provided, only generate properties for this version
        for_update: If True, add special markers for property updates

    Returns:
        Dict of properties (without libs.{library_name} prefix)
    """
    lib_props = {}

    # Handle versions
    if "targets" in lib_info and lib_info["targets"]:
        if specific_version:
            # Filter to specific version
            found_version = None
            for target_version in lib_info["targets"]:
                if isinstance(target_version, dict):
                    ver_name = target_version.get("name", target_version)
                else:
                    ver_name = target_version

                if ver_name == specific_version:
                    found_version = target_version
                    break

            if not found_version:
                raise ValueError(f"Version '{specific_version}' not found for library '{library_name}'")

            # Generate properties for single version
            ver_id = version_to_id(specific_version)
            lib_props[f"versions.{ver_id}.version"] = specific_version

            # Add library type specific paths
            # Only set path if package_install is not true
            if not lib_info.get("package_install"):
                path = generate_library_path(library_name, specific_version)
                lib_props[f"versions.{ver_id}.path"] = path

            # When updating a specific version, check if we need to update the versions list
            if for_update:
                lib_props["_update_version_id"] = ver_id  # Special marker for version update
        else:
            # When updating all versions, we update library-level properties too
            # Add basic properties
            lib_props["name"] = library_name

            # Add URL if it's a GitHub library
            if lib_info.get("type") == "github" and "repo" in lib_info:
                lib_props["url"] = f"https://github.com/{lib_info['repo']}"

            # Generate properties for all versions
            version_ids = []
            for target_version in lib_info["targets"]:
                if isinstance(target_version, dict):
                    ver_name = target_version.get("name", target_version)
                    ver_id = version_to_id(ver_name)
                else:
                    ver_name = target_version
                    ver_id = version_to_id(target_version)
                version_ids.append(ver_id)

                lib_props[f"versions.{ver_id}.version"] = ver_name

                # Add library type specific paths
                # Only set path if package_install is not true
                if not lib_info.get("package_install"):
                    path = generate_library_path(library_name, ver_name)
                    lib_props[f"versions.{ver_id}.path"] = path

            lib_props["versions"] = ":".join(version_ids)
    else:
        # No targets specified, but we still need basic properties when not updating
        if not specific_version:
            lib_props["name"] = library_name
            if lib_info.get("type") == "github" and "repo" in lib_info:
                lib_props["url"] = f"https://github.com/{lib_info['repo']}"

    return lib_props


def generate_all_libraries_properties(cpp_libraries):
    """Generate properties for all C++ libraries.

    Args:
        cpp_libraries: Dict of C++ libraries from libraries.yaml

    Returns:
        String containing all properties in CE format
    """
    all_ids = []
    properties_txt = ""

    for lib_id, lib_info in cpp_libraries.items():
        if lib_id in ["nightly", "if", "install_always"]:
            continue

        # Skip libraries that are manual or have no build type
        if "build_type" in lib_info and lib_info["build_type"] in ["manual", "none", "never"]:
            continue

        all_ids.append(lib_id)

        # Generate basic properties
        libverprops = f"libs.{lib_id}.name={lib_id}\n"

        # Add URL if it's a GitHub library
        if lib_info.get("type") == "github" and "repo" in lib_info:
            libverprops += f"libs.{lib_id}.url=https://github.com/{lib_info['repo']}\n"

        # Add versions
        if "targets" in lib_info and lib_info["targets"]:
            version_ids = []
            for target_version in lib_info["targets"]:
                if isinstance(target_version, dict):
                    ver_name = target_version.get("name", target_version)
                    ver_id = version_to_id(ver_name)
                else:
                    ver_name = target_version
                    ver_id = version_to_id(target_version)
                version_ids.append(ver_id)

            libverprops += f"libs.{lib_id}.versions={':'.join(version_ids)}\n"

            # Add version details
            for target_version in lib_info["targets"]:
                if isinstance(target_version, dict):
                    ver_name = target_version.get("name", target_version)
                    ver_id = version_to_id(ver_name)
                else:
                    ver_name = target_version
                    ver_id = version_to_id(target_version)

                libverprops += f"libs.{lib_id}.versions.{ver_id}.version={ver_name}\n"

                # Add library type specific paths
                # Only set path if package_install is not true
                if not lib_info.get("package_install"):
                    path = generate_library_path(lib_id, ver_name)
                    libverprops += f"libs.{lib_id}.versions.{ver_id}.path={path}\n"

        properties_txt += libverprops + "\n"

    # Generate header
    header_properties_txt = "libs=" + ":".join(all_ids) + "\n\n"
    return header_properties_txt + properties_txt


def generate_standalone_library_properties(library_name, lib_props, specific_version=None):
    """Generate standalone properties for a single library.

    Args:
        library_name: Name of the library
        lib_props: Library properties dict
        specific_version: If provided, add library-level properties for standalone generation

    Returns:
        String containing properties in CE format
    """
    # Make a copy to avoid modifying the original
    props_copy = lib_props.copy()

    # When generating standalone (no input file), include all properties
    if specific_version and "name" not in props_copy:
        # Add library-level properties for standalone generation
        props_copy["name"] = library_name
        # Note: URL would need to be passed in or retrieved separately

    properties_lines = []
    properties_lines.append(f"libs={library_name}")
    properties_lines.append("")

    # Remove the special marker before output
    props_copy.pop("_update_version_id", None)

    for prop_name, value in sorted(props_copy.items()):
        properties_lines.append(f"libs.{library_name}.{prop_name}={value}")

    return "\n".join(properties_lines)


def find_existing_library_by_github_url(cpp_libraries, github_url):
    """Find if a library already exists by checking the GitHub URL."""
    # Parse the URL to get the repo in owner/repo format
    parsed = urlparse(github_url)
    if parsed.netloc != "github.com":
        return None

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        return None

    github_repo = f"{path_parts[0]}/{path_parts[1]}"

    # Search through all C++ libraries
    for lib_id, lib_info in cpp_libraries.items():
        if isinstance(lib_info, dict) and lib_info.get("repo") == github_repo:
            return lib_id

    # Also check in nightly section if it exists
    if "nightly" in cpp_libraries and isinstance(cpp_libraries["nightly"], dict):
        for lib_id, lib_info in cpp_libraries["nightly"].items():
            if isinstance(lib_info, dict) and lib_info.get("repo") == github_repo:
                return lib_id

    return None


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
            lib_props = generate_single_library_properties(
                library, lib_info, specific_version=version, for_update=bool(input_file)
            )
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)

        if input_file:
            # Load existing properties file
            with open(input_file, "r", encoding="utf-8") as f:
                existing_content = f.read()

            # Update only the specific library
            result = update_library_in_properties(existing_content, library, lib_props)

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
