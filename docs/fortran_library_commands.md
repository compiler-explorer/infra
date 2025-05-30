# Fortran Library Management Commands

This document describes the Fortran library management commands for adding and managing Fortran libraries in Compiler Explorer.

## Overview

The Fortran library commands allow you to:
- Add new Fortran libraries from GitHub URLs
- Generate properties files for Fortran libraries
- Update existing properties files with new or modified libraries

All Fortran libraries in Compiler Explorer use FPM (Fortran Package Manager) for building.

## Commands

### `fortran-library add`

Add a new Fortran library or update an existing library version.

```bash
ce_install fortran-library add <github_url> <version> [--target-prefix <prefix>]
```

**Parameters:**
- `github_url`: GitHub URL of the library (e.g., `https://github.com/jacobwilliams/json-fortran`)
- `version`: Version to add (e.g., `8.3.0`)
- `--target-prefix`: Prefix for version tags (optional, e.g., 'v' for tags like v0.1.0)

**Examples:**
```bash
# Add a Fortran library
ce_install fortran-library add https://github.com/jacobwilliams/json-fortran 8.3.0

# Add a library with 'v' prefixed version tags
ce_install fortran-library add https://github.com/fortran-lang/http-client 0.1.0 --target-prefix v
```

### `fortran-library generate-props`

Generate properties file for Fortran libraries.

```bash
ce_install fortran-library generate-props [options]
```

**Options:**
- `--input-file <file>`: Existing properties file to update
- `--output-file <file>`: Output file (defaults to stdout)
- `--library <name>`: Only process this specific library
- `--version <version>`: Only process this specific version (requires --library)

**Examples:**
```bash
# Generate all Fortran library properties to stdout
ce_install fortran-library generate-props

# Generate properties to a file
ce_install fortran-library generate-props --output-file fortran_libraries.properties

# Update existing properties file
ce_install fortran-library generate-props --input-file existing.properties --output-file updated.properties

# Generate properties for a specific library
ce_install fortran-library generate-props --library json_fortran

# Generate properties for a specific library version
ce_install fortran-library generate-props --library json_fortran --version 8.3.0 --input-file existing.properties
```

## Usage Workflow

### Adding a New Library

1. **Add the library:**
   ```bash
   ce_install fortran-library add https://github.com/jacobwilliams/json-fortran 8.3.0
   ```

2. **Generate updated properties:**
   ```bash
   ce_install fortran-library generate-props \
     --input-file /opt/compiler-explorer/etc/config/fortran.properties \
     --output-file /opt/compiler-explorer/etc/config/fortran.properties
   ```

### Adding a Version to Existing Library

```bash
# Add new version
ce_install fortran-library add https://github.com/jacobwilliams/json-fortran 8.4.0

# Update properties for just this library
ce_install fortran-library generate-props --library json_fortran \
  --input-file existing.properties --output-file updated.properties
```

### Generating Properties from Scratch

```bash
# Generate complete properties file
ce_install fortran-library generate-props --output-file fortran_libraries.properties
```

## Properties Format

Fortran libraries use a specific properties format that differs from C++ libraries:

- No path properties (uses `packagedheaders=true` instead)
- Includes `staticliblink` property with the library name
- Direct library format: `libs.{library_name}.{property}`

Example properties output:
```properties
libs=json_fortran:http_client

libs.json_fortran.name=json_fortran
libs.json_fortran.url=https://github.com/jacobwilliams/json-fortran
libs.json_fortran.packagedheaders=true
libs.json_fortran.staticliblink=json_fortran
libs.json_fortran.versions=830
libs.json_fortran.versions.830.version=8.3.0
```

## Notes

- All Fortran libraries use FPM (Fortran Package Manager) as their build system
- The `add` command automatically sets `build_type: fpm` and `check_file: fpm.toml`
- Libraries are typically configured with `requires_tree_copy: true` for FPM compatibility
- Properties generation can be done for all libraries or filtered to specific libraries/versions
- Library paths follow a consistent structure under `/opt/compiler-explorer/libs/fortran/`