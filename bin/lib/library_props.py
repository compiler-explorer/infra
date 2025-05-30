"""
Library property generation utilities for Compiler Explorer.

This module contains functions for generating properties files for C++ libraries
from libraries.yaml configurations. These functions are designed to be reusable
across different parts of the system.
"""

from urllib.parse import urlparse


def generate_library_path(library_name, version):
    """Generate the standard library path for Compiler Explorer."""
    return f"/opt/compiler-explorer/libs/{library_name}/{version}/include"


def generate_version_property_key(library_name, version_id, property_name):
    """Generate a property key for a library version."""
    suffix = generate_version_property_suffix(version_id, property_name)
    return f"libs.{library_name}.{suffix}"


def generate_library_property_key(library_name, property_name):
    """Generate a property key for a library."""
    return f"libs.{library_name}.{property_name}"


def version_to_id(version):
    """Convert a version string to a version ID by removing dots."""
    return version.replace(".", "")


def generate_version_property_suffix(version_id, property_name):
    """Generate the suffix for a version property key (versions.{version_id}.{property_name})."""
    return f"versions.{version_id}.{property_name}"


def extract_library_id_from_github_url(github_url):
    """Extract library ID from GitHub URL."""
    parsed = urlparse(github_url)
    if parsed.netloc != "github.com":
        raise ValueError(f"URL must be a GitHub URL, got: {github_url}")

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        raise ValueError(f"Invalid GitHub URL format: {github_url}")

    repo_name = path_parts[1]
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


def update_library_in_properties(existing_content, library_name, library_properties, update_version_id=None):
    """Update a single library in the properties content.

    Args:
        existing_content: The existing properties file content
        library_name: Name of the library to update
        library_properties: Dict of properties for this library (without the libs.{library_name} prefix)
        update_version_id: If provided, indicates this is a single version update

    Returns:
        Updated content with the library properties merged
    """

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


    lines = existing_content.splitlines()
    result_lines = []

    seen_props = set()
    inside_library_block = False
    last_library_line_idx = -1
    existing_versions = []

    for _i, line in enumerate(lines):
        stripped = line.strip()

        if "=" in stripped and not stripped.startswith("#"):
            key = stripped.split("=", 1)[0]
            library_prefix = generate_library_property_key(library_name, "")
            if key.startswith(library_prefix):
                inside_library_block = True
                last_library_line_idx = len(result_lines)

                prop_name = key[len(library_prefix) :]
                seen_props.add(prop_name)

                if prop_name == "versions" and update_version_id:
                    if "=" in stripped:
                        _, versions_value = stripped.split("=", 1)
                        existing_versions = versions_value.split(":")

                    if update_version_id not in existing_versions:
                        existing_versions.append(update_version_id)

                        def version_sort_key(v):
                            try:
                                return int("".join(filter(str.isdigit, v)) or "0")
                            except ValueError:
                                return v

                        existing_versions.sort(key=version_sort_key)
                        result_lines.append(f"{key}={':'.join(existing_versions)}")
                    else:
                        result_lines.append(line)
                    continue

                if prop_name in library_properties:
                    result_lines.append(f"{key}={library_properties[prop_name]}")
                else:
                    result_lines.append(line)
                continue
            elif inside_library_block and key.startswith("libs.") and not key.startswith(library_prefix):
                inside_library_block = False

        result_lines.append(line)

    props_to_add = []
    for prop_name, value in library_properties.items():
        if prop_name not in seen_props and not prop_name.startswith("_"):
            props_to_add.append((prop_name, value))

    if props_to_add:
        if last_library_line_idx >= 0:
            insert_idx = last_library_line_idx + 1

            props_to_add.sort(key=sort_key)

            for prop_name, value in reversed(props_to_add):
                full_key = generate_library_property_key(library_name, prop_name)
                result_lines.insert(insert_idx, f"{full_key}={value}")
        else:
            if result_lines and result_lines[-1].strip() != "":
                result_lines.append("")

            props_to_add.sort(key=sort_key)

            for prop_name, value in props_to_add:
                full_key = generate_library_property_key(library_name, prop_name)
                result_lines.append(f"{full_key}={value}")

    return "\n".join(result_lines)


def merge_properties(existing_content, new_content):
    """Merge new properties into existing properties file, preserving structure and comments."""
    new_props = parse_properties_file(new_content)

    new_libs_list = []
    if "libs" in new_props:
        new_libs_list = new_props["libs"].split(":")

    result_content = existing_content

    lines = result_content.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("libs="):
            existing_libs = []
            if "=" in line.strip():
                _, value = line.strip().split("=", 1)
                existing_libs = [lib for lib in value.split(":") if lib]

            merged_libs = existing_libs.copy()
            for lib in new_libs_list:
                if lib not in merged_libs:
                    merged_libs.append(lib)

            lines[i] = f"libs={':'.join(merged_libs)}"
            result_content = "\n".join(lines)
            break

    libraries_to_update = {}

    for key, value in new_props.items():
        if key.startswith("libs.") and "." in key[5:]:
            parts = key.split(".")
            lib_name = parts[1]
            prop_name = ".".join(parts[2:])  # Handle nested properties like versions.120.version

            if lib_name not in libraries_to_update:
                libraries_to_update[lib_name] = {}

            libraries_to_update[lib_name][prop_name] = value

    for lib_name, lib_props in libraries_to_update.items():
        result_content = update_library_in_properties(result_content, lib_name, lib_props)

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


def generate_single_library_properties(library_name, lib_info, specific_version=None):
    """Generate properties for a single library.

    Args:
        library_name: Name of the library
        lib_info: Library information from libraries.yaml
        specific_version: If provided, only generate properties for this version

    Returns:
        Dict of properties (without libs.{library_name} prefix)
    """
    lib_props = {}

    if "targets" in lib_info and lib_info["targets"]:
        if specific_version:
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

            ver_id = version_to_id(specific_version)
            version_suffix = generate_version_property_suffix(ver_id, "version")
            lib_props[version_suffix] = specific_version

            if not lib_info.get("package_install"):
                path = generate_library_path(library_name, specific_version)
                path_suffix = generate_version_property_suffix(ver_id, "path")
                lib_props[path_suffix] = path

        else:
            # When updating all versions, we update library-level properties too
            lib_props["name"] = library_name

            if lib_info.get("type") == "github" and "repo" in lib_info:
                lib_props["url"] = f"https://github.com/{lib_info['repo']}"

            # Add link properties if present
            if "sharedliblink" in lib_info and lib_info["sharedliblink"]:
                lib_props["liblink"] = ":".join(lib_info["sharedliblink"])
            if "staticliblink" in lib_info and lib_info["staticliblink"]:
                lib_props["staticliblink"] = ":".join(lib_info["staticliblink"])

            version_ids = []
            for target_version in lib_info["targets"]:
                if isinstance(target_version, dict):
                    ver_name = target_version.get("name", target_version)
                    ver_id = version_to_id(ver_name)
                else:
                    ver_name = target_version
                    ver_id = version_to_id(target_version)
                version_ids.append(ver_id)

                version_suffix = generate_version_property_suffix(ver_id, "version")
                lib_props[version_suffix] = ver_name

                if not lib_info.get("package_install"):
                    path = generate_library_path(library_name, ver_name)
                    path_suffix = generate_version_property_suffix(ver_id, "path")
                    lib_props[path_suffix] = path

            lib_props["versions"] = ":".join(version_ids)
    else:
        # No targets specified, but we still need basic properties when not updating
        if not specific_version:
            lib_props["name"] = library_name
            if lib_info.get("type") == "github" and "repo" in lib_info:
                lib_props["url"] = f"https://github.com/{lib_info['repo']}"

            # Add link properties if present
            if "sharedliblink" in lib_info and lib_info["sharedliblink"]:
                lib_props["liblink"] = ":".join(lib_info["sharedliblink"])
            if "staticliblink" in lib_info and lib_info["staticliblink"]:
                lib_props["staticliblink"] = ":".join(lib_info["staticliblink"])

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
        if should_skip_library(lib_id, lib_info):
            continue

        all_ids.append(lib_id)

        name_key = generate_library_property_key(lib_id, "name")
        libverprops = f"{name_key}={lib_id}\n"

        if lib_info.get("type") == "github" and "repo" in lib_info:
            url_key = generate_library_property_key(lib_id, "url")
            libverprops += f"{url_key}=https://github.com/{lib_info['repo']}\n"

        # Add link properties if present
        if "sharedliblink" in lib_info and lib_info["sharedliblink"]:
            liblink_key = generate_library_property_key(lib_id, "liblink")
            libverprops += f"{liblink_key}={':'.join(lib_info['sharedliblink'])}\n"
        if "staticliblink" in lib_info and lib_info["staticliblink"]:
            staticliblink_key = generate_library_property_key(lib_id, "staticliblink")
            libverprops += f"{staticliblink_key}={':'.join(lib_info['staticliblink'])}\n"

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

            versions_key = generate_library_property_key(lib_id, "versions")
            libverprops += f"{versions_key}={':'.join(version_ids)}\n"

            for target_version in lib_info["targets"]:
                if isinstance(target_version, dict):
                    ver_name = target_version.get("name", target_version)
                    ver_id = version_to_id(ver_name)
                else:
                    ver_name = target_version
                    ver_id = version_to_id(target_version)

                version_key = generate_version_property_key(lib_id, ver_id, "version")
                libverprops += f"{version_key}={ver_name}\n"

                if not lib_info.get("package_install"):
                    path = generate_library_path(lib_id, ver_name)
                    path_key = generate_version_property_key(lib_id, ver_id, "path")
                    libverprops += f"{path_key}={path}\n"

        properties_txt += libverprops + "\n"

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
    props_copy = lib_props.copy()

    # When generating standalone (no input file), include all properties
    if specific_version and "name" not in props_copy:
        props_copy["name"] = library_name
        # Note: URL would need to be passed in or retrieved separately

    properties_lines = []
    properties_lines.append(f"libs={library_name}")
    properties_lines.append("")


    for prop_name, value in sorted(props_copy.items()):
        property_key = generate_library_property_key(library_name, prop_name)
        properties_lines.append(f"{property_key}={value}")

    return "\n".join(properties_lines)


def should_skip_library(lib_id, lib_info):
    """Check if a library should be skipped based on its configuration.

    Args:
        lib_id: Library identifier
        lib_info: Library configuration dictionary

    Returns:
        True if the library should be skipped, False otherwise
    """
    if lib_id in ["nightly", "if", "install_always"]:
        return True

    if "build_type" in lib_info and lib_info["build_type"] in ["manual", "none", "never"]:
        return True

    return False


def should_skip_library_for_windows(lib_id, lib_info):
    """Check if a library should be skipped for Windows properties based on its configuration.

    Args:
        lib_id: Library identifier
        lib_info: Library configuration dictionary

    Returns:
        True if the library should be skipped, False otherwise
    """
    if lib_id in ["nightly", "if", "install_always"]:
        return True

    if "build_type" in lib_info and lib_info["build_type"] in ["manual", "none", "never", "make"]:
        return True

    return False


def find_existing_library_by_github_url(cpp_libraries, github_url):
    """Find if a library already exists by checking the GitHub URL."""
    parsed = urlparse(github_url)
    if parsed.netloc != "github.com":
        return None

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        return None

    github_repo = f"{path_parts[0]}/{path_parts[1]}"

    for lib_id, lib_info in cpp_libraries.items():
        if isinstance(lib_info, dict) and lib_info.get("repo") == github_repo:
            return lib_id

    if "nightly" in cpp_libraries and isinstance(cpp_libraries["nightly"], dict):
        for lib_id, lib_info in cpp_libraries["nightly"].items():
            if isinstance(lib_info, dict) and lib_info.get("repo") == github_repo:
                return lib_id

    return None
