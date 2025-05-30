import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

import click

from lib.library_yaml import LibraryYaml

from .cli import cli


def extract_library_id_from_github_url(github_url):
    """Extract library ID from GitHub URL."""
    parsed = urlparse(github_url)
    if parsed.netloc != 'github.com':
        raise ValueError(f"URL must be a GitHub URL, got: {github_url}")
    
    # Extract repo name from path (format: /owner/repo)
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) < 2:
        raise ValueError(f"Invalid GitHub URL format: {github_url}")
    
    repo_name = path_parts[1]
    # Convert to lowercase and replace hyphens with underscores
    return repo_name.lower().replace('-', '_')


def find_existing_library_by_github_url(cpp_libraries, github_url):
    """Find if a library already exists by checking the GitHub URL."""
    # Parse the URL to get the repo in owner/repo format
    parsed = urlparse(github_url)
    if parsed.netloc != 'github.com':
        return None
    
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) < 2:
        return None
    
    github_repo = f"{path_parts[0]}/{path_parts[1]}"
    
    # Search through all C++ libraries
    for lib_id, lib_info in cpp_libraries.items():
        if isinstance(lib_info, dict) and lib_info.get('repo') == github_repo:
            return lib_id
    
    # Also check in nightly section if it exists
    if 'nightly' in cpp_libraries and isinstance(cpp_libraries['nightly'], dict):
        for lib_id, lib_info in cpp_libraries['nightly'].items():
            if isinstance(lib_info, dict) and lib_info.get('repo') == github_repo:
                return lib_id
    
    return None


@cli.group()
def cpp_library():
    """C++ library management commands."""


@cpp_library.command(name="add")
@click.argument('github_url')
@click.argument('version')
@click.option(
    '--type',
    type=click.Choice(['header-only', 'packaged-headers', 'static', 'shared']),
    default='header-only',
    help='Library type (default: header-only)'
)
def add_cpp_library(github_url: str, version: str, type: str):
    """Add or update a C++ library entry in libraries.yaml."""
    # Load libraries.yaml first to search for existing library
    yaml_dir = Path(__file__).parent.parent.parent / 'yaml'
    library_yaml = LibraryYaml(str(yaml_dir))
    
    # Ensure c++ section exists
    if 'c++' not in library_yaml.yaml_doc['libraries']:
        library_yaml.yaml_doc['libraries']['c++'] = {}
    
    cpp_libraries = library_yaml.yaml_doc['libraries']['c++']
    
    # Search for existing library by GitHub URL
    existing_lib_id = find_existing_library_by_github_url(cpp_libraries, github_url)
    
    if existing_lib_id:
        lib_id = existing_lib_id
        # Extract repo field from existing library
        repo_field = cpp_libraries[lib_id].get('repo', '')
    else:
        # Extract library ID from GitHub URL for new library
        try:
            lib_id = extract_library_id_from_github_url(github_url)
        except ValueError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
        
        # Extract owner and repo from URL for the repo field
        parsed = urlparse(github_url)
        path_parts = parsed.path.strip('/').split('/')
        repo_field = f"{path_parts[0]}/{path_parts[1]}"
    
    # Check if library already exists
    if lib_id in cpp_libraries:
        # Add version to existing library
        if 'targets' not in cpp_libraries[lib_id]:
            cpp_libraries[lib_id]['targets'] = []
        
        if version not in cpp_libraries[lib_id]['targets']:
            cpp_libraries[lib_id]['targets'].append(version)
            if existing_lib_id:
                click.echo(f"Found existing library '{lib_id}' for {github_url}")
            click.echo(f"Added version {version} to library {lib_id}")
        else:
            click.echo(f"Version {version} already exists for library {lib_id}")
    else:
        # Create new library entry
        library_entry = {
            'type': 'github',
            'repo': repo_field,
            'check_file': 'README.md',  # Default check file
            'targets': [version]
        }
        
        # Set properties based on library type
        if type == 'packaged-headers':
            library_entry['build_type'] = 'cmake'
            library_entry['lib_type'] = 'headeronly'
            library_entry['package_install'] = True
        elif type == 'header-only':
            # Header-only libraries typically don't need build_type
            pass
        elif type == 'static':
            library_entry['build_type'] = 'cmake'
            library_entry['lib_type'] = 'static'
        elif type == 'shared':
            library_entry['build_type'] = 'cmake'
            library_entry['lib_type'] = 'shared'
        
        cpp_libraries[lib_id] = library_entry
        click.echo(f"Added new library {lib_id} with version {version}")
    
    # Save the updated YAML
    library_yaml.save()
    click.echo(f"Successfully updated {library_yaml.yaml_path}")


@cpp_library.command(name="generate-windows-props")
def generate_cpp_windows_props():
    """Generate C++ Windows properties file from libraries.yaml."""
    # Load libraries.yaml
    yaml_dir = Path(__file__).parent.parent.parent / 'yaml'
    library_yaml = LibraryYaml(str(yaml_dir))
    
    # Check if there are any C++ libraries
    if 'c++' not in library_yaml.yaml_doc['libraries']:
        click.echo("No C++ libraries found in libraries.yaml")
        return
    
    # Generate properties using the existing method
    logger = logging.getLogger()
    properties_text = library_yaml.get_ce_properties_for_cpp_windows_libraries(logger)
    
    # Output to stdout (can be redirected to a file)
    click.echo(properties_text)


@cpp_library.command(name="generate-linux-props")
def generate_cpp_linux_props():
    """Generate C++ Linux properties file from libraries.yaml."""
    # Load libraries.yaml
    yaml_dir = Path(__file__).parent.parent.parent / 'yaml'
    library_yaml = LibraryYaml(str(yaml_dir))
    
    # Check if there are any C++ libraries
    if 'c++' not in library_yaml.yaml_doc['libraries']:
        click.echo("No C++ libraries found in libraries.yaml")
        return
    
    # For now, we'll generate a simple properties format for Linux
    # This follows a similar pattern to the Rust properties generation
    cpp_libraries = library_yaml.yaml_doc['libraries']['c++']
    all_ids = []
    properties_txt = ""
    
    for lib_id, lib_info in cpp_libraries.items():
        if lib_id in ['nightly', 'if', 'install_always']:
            continue
            
        # Skip libraries that are manual or have no build type
        if 'build_type' in lib_info and lib_info['build_type'] in ['manual', 'none', 'never']:
            continue
            
        all_ids.append(lib_id)
        
        # Generate basic properties
        libverprops = f"libs.{lib_id}.name={lib_id}\n"
        
        # Add URL if it's a GitHub library
        if lib_info.get('type') == 'github' and 'repo' in lib_info:
            libverprops += f"libs.{lib_id}.url=https://github.com/{lib_info['repo']}\n"
        
        # Add versions
        if 'targets' in lib_info and lib_info['targets']:
            version_ids = []
            for version in lib_info['targets']:
                if isinstance(version, dict):
                    ver_name = version.get('name', version)
                    ver_id = ver_name.replace('.', '')
                else:
                    ver_name = version
                    ver_id = version.replace('.', '')
                version_ids.append(ver_id)
            
            libverprops += f"libs.{lib_id}.versions={':'.join(version_ids)}\n"
            
            # Add version details
            for version in lib_info['targets']:
                if isinstance(version, dict):
                    ver_name = version.get('name', version)
                    ver_id = ver_name.replace('.', '')
                else:
                    ver_name = version
                    ver_id = version.replace('.', '')
                    
                libverprops += f"libs.{lib_id}.versions.{ver_id}.version={ver_name}\n"
                
                # Add library type specific paths
                if lib_info.get('lib_type') == 'headeronly' or lib_info.get('package_install'):
                    libverprops += f"libs.{lib_id}.versions.{ver_id}.path=./\n"
        
        properties_txt += libverprops + "\n"
    
    # Generate header
    header_properties_txt = "libs=" + ":".join(all_ids) + "\n\n"
    
    # Output to stdout
    click.echo(header_properties_txt + properties_txt)