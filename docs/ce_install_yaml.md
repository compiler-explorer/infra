# Compiler Explorer YAML Installation Configuration

This document explains how to configure the installation of compilers and libraries in Compiler Explorer using YAML configuration files.

## Overview

The Compiler Explorer installation system uses YAML configuration files to define what compilers and libraries should be installed. These files are located in the `bin/yaml` directory and are processed by the `ce_install` tool (typeically invoked as `./bin/ce_install`).

The installation system offers a flexible way to define installation targets with properties that are inherited from parent nodes. This allows for concise configurations with a lot of shared settings.

## Basic Concepts

### Configuration Structure

The YAML files have a hierarchical structure that typically follows this pattern:

```yaml
compilers:  # or libraries:
  language:
    category:
      compiler_type:
        # Properties here are inherited by all targets
        type: some_installer_type
        check_exe: bin/compiler --version
        targets:
          - 1.0.0
          - 1.1.0
          - name: 2.0.0
            # Override properties for this specific target
```

### Property Inheritance and Hierarchy

The hierarchical structure of CE installation YAML allows for efficient configuration management through inheritance. Properties defined at higher levels in the hierarchy are inherited by all children, allowing common settings to be defined once and applied to multiple targets.

**Benefits of this approach**:
- Reduces duplication across similar compilers
- Centralizes common settings
- Simplifies maintenance when versions share properties
- Makes it easier to manage large numbers of compiler versions while keeping the YAML readable

**Simple Example**:
```yaml
compilers:
  c++:
    x86:
      gcc:
        type: s3tarballs
        check_exe: bin/g++ --version
        targets:
          - 4.9.0
          - 5.1.0
```

Both the `4.9.0` and `5.1.0` targets inherit the `type: s3tarballs` and `check_exe: bin/g++ --version` properties.

**More Complex Example**:
```yaml
compilers:
  mylang:  # Language level
    # Properties common to ALL mylang compilers
    x86:  # Architecture level
      # Properties common to all x86 mylang compilers
      mylang_official:  # Compiler family level
        # Properties common to all official mylang compiler versions
        type: github
        check_exe: bin/mylangc --version
        targets:  # Individual versions
          - 1.0.0  # Inherits all properties from above
          - name: 1.1.0-beta
            # Can override specific properties just for this version
            check_exe: bin/mylangc-beta --version
```

**When to Use Nesting vs. Flattening**:
- Most simple setups won't need any more nesting than `compilers/language`
- Use nesting when multiple compilers/versions share many properties
- Create separate sections (like `older` and `newer` in rust.yaml) when versions have significant differences in configuration

### String Interpolation

Property values can contain interpolated values using the `{{property}}` syntax. This allows constructing paths, URLs, or other values based on properties of the target.

For example:
```yaml
dir: "clang+llvm-{{name}}-{{suffix}}"
url: "https://llvm.org/releases/{{name}}/clang+llvm-{{name}}-{{suffix}}.tar.gz"
```

### Targets

Each target in the `targets:` list defines something to install. If a target is a simple string, it's treated as if it were `{name: "TARGET"}`. If it's an object, it can override properties inherited from parent nodes.

Targets can be referenced by their context and name, for example, `compilers/c++/x86/gcc 4.9.0`.

## Target Properties

The following properties are commonly used by installation targets:

| Property | Description |
|----------|-------------|
| `name` | The name of the target (required) |
| `type` | The installer type to use (e.g., `s3tarballs`, `github`, `script`) (required) |
| `dir` | The installation directory relative to the destination |
| `check_exe` | Command to check if the target is installed, relative to the installed directory. This is run and it completing successfully is used to determine if the install was successful. Either this or `check_file` should be defined |
| `check_file` | File to check if the target is installed, relative to the installed directory |
| `check_env` | Dictionary of environment variables to set when checking if the target is installed |
| `check_stderr_on_stdout` | Whether to redirect stderr to stdout when checking installation |
| `if` | Conditional flag to control if the target is included |
| `s3_path_prefix` | Custom path in S3 storage for S3 installer types |
| `install_always` | Whether to always install (used for nightlies). Without this, installation tries to be idempotent: the `check_file` or `check_exe` is used to determine if this target is already installed, and if so it is skipped |
| `compression` | Compression format for archive types (e.g., `gz`, `bz2`, `xz`) |
| `untar_dir` | Directory name when extracting archives |
| `create_untar_dir` | Whether to create the untar directory if it doesn't exist |
| `strip_components` | Number of leading path components to strip when extracting |
| `strip` | Whether to apply stripping to executables |
| `depends` | List of target dependencies |
| `symlink` | Symlink to create for the installed target (only needed in rare cases) |

## Script-Related Properties

Several properties control pre, post, and installation scripts:

| Property | Description |
|----------|-------------|
| `after_stage_script` | Commands to run after staging but before installation |
| `after_stage_script_pwsh` | PowerShell commands for Windows installation |
| `prebuild_script` | Commands to run before building libraries |
| `postbuild_script` | Commands to run after building libraries |
| `script` | The script content for targets of type `script` |

## Installer Types and Required Properties

The following installer types are available, each with specific required and optional properties:

| Type | Description | Required Properties | Common Optional Properties |
|------|-------------|---------------------|----------------------------|
| `s3tarballs` | Downloads and extracts a tarball from Compiler Explorer's Amazon S3 bucket (compatible with the way we build all our major compilers) | `check_exe` or `check_file` | `dir`, `s3_path_prefix`, `untar_dir` |
| `tarballs` | Downloads and extracts a tarball from a URL | `check_exe` or `check_file`, `url` | `dir`, `compression`, `untar_dir` |
| `nightlytarballs` | Downloads and extracts a tarball for nightly builds | `check_exe` or `check_file` | `dir`, `compression` |
| `nightly` | Installs a nightly build from a custom location | `check_exe` | `dir`, `nightly_install_days` |
| `script` | Runs a script to install the target | `check_exe` or `check_file`, `script` | `dir` |
| `solidity` | Installs a Solidity compiler | `check_exe` or `check_file` | `dir` |
| `singleFile` | Installs a single file from a URL | `check_exe` or `check_file`, `url` | `dir` |
| `github` | Clones and installs from a GitHub repository | `check_exe` or `check_file`, `repo` | `dir`, `method`, `recursive` |
| `gitlab` | Clones and installs from a GitLab repository | `check_exe` or `check_file`, `repo` | `dir`, `method`, `recursive` |
| `bitbucket` | Clones and installs from a Bitbucket repository | `check_exe` or `check_file`, `repo` | `dir`, `method`, `recursive` |
| `rust` | Installs a Rust compiler | `check_exe`, `base_package` | `dir` |
| `pip` | Installs a Python package with pip | `check_exe` or `check_file` | `dir` |
| `ziparchive` | Downloads and extracts a ZIP archive | `check_exe` or `check_file`, `url` | `dir` |
| `cratesio` | Installs a Rust crate from crates.io | `check_exe` or `check_file` | `dir` |
| `non-free-s3tarballs` | Downloads and extracts a non-free tarball from S3 | `check_exe` or `check_file` | `dir`, `s3_path_prefix` |
| `edg` | Installs an EDG compiler (very special-case) | `check_exe` or `check_file` | `dir` |
| `restQueryTarballs` | Downloads tarball using REST API information | `check_exe` or `check_file`, `url` | `dir` |
| `go` | Installs a Go compiler and automatically builds the standard library | `check_exe` or `check_file` | `dir`, `build_stdlib`, `build_stdlib_archs` |

## GitHub/GitLab/Bitbucket Repository Properties

When using the `github`, `gitlab`, or `bitbucket` installer types, the following properties are useful:

| Property | Description |
|----------|-------------|
| `repo` | Repository path (e.g., `username/repo`) |
| `target_prefix` | Prefix to add to target name for tag/branch (e.g., `v` for `v1.0.0`) |
| `method` | Clone method (`archive`, `clone_branch`, `nightlyclone`, `nightlybranch`) |
| `recursive` | Whether to clone submodules recursively (default: `true`) |

## Conditional Installation

Targets can be made conditional using the `if:` property. This is often used to mark targets as "nightly" builds or as third-party compilers:

```yaml
nightly:
  if: nightly
  type: nightly
  targets:
    - trunk
```

When running `ce_install`, you can enable these conditional targets with the `--enable` option, e.g.:
```bash
ce_install --enable nightly install
```

Common condition flags include:
- `nightly` - For nightly/trunk builds
- `non-free` - For proprietary compilers

## Dependencies

Targets can depend on other targets using the `depends:` property, which takes a list of target references:

```yaml
depends:
  - compilers/c++/x86/gcc 13.2.0
```

The paths of dependencies are interpolated in the target's properties as `%DEP0%`, `%DEP1%`, etc., corresponding to the order of dependencies.

## Cross-Compiler Configuration

Cross compilers often use additional properties to define architecture-specific settings:

```yaml
arch_prefix: arm-unknown-linux-gnueabi
check_exe: "{{arch_prefix}}/bin/{{arch_prefix}}-g++ --version"
s3_path_prefix: "{{subdir}}-gcc-{{name}}"
path_name: "{{subdir}}/gcc-{{name}}"
untar_dir: "gcc-{{name}}"
```

These are mostly conventions, used in the interpolation and not something that the underlying installation system requires.

## Library-Specific Properties

Libraries have additional properties that control how they are built:

| Property | Description |
|----------|-------------|
| `build_type` | The build system to use (e.g., `cmake`, `make`, `cargo`, `none`, `manual`, `never`) |
| `lib_type` | Type of library (e.g., `static`, `shared`, `headeronly`, `cshared`) |
| `make_targets` | Targets to build with make |
| `make_utility` | Build utility to use (e.g., `ninja`) |
| `extra_cmake_arg` | Additional arguments to pass to cmake |
| `package_install` | Whether to use `cmake --install` during build |
| `staticliblink` | Static libraries to link against |
| `sharedliblink` | Shared libraries to link against |
| `use_compiler` | Specific compiler to use during build |

Example of library configuration:

```yaml
boost_bin:
  build_type: cmake
  lib_type: shared
  make_targets:
    - all
  extra_cmake_arg:
    - -DBOOST_INSTALL_LAYOUT=system
    - -DBUILD_SHARED_LIBS=ON
  sharedliblink:
    - boost_iostreams
  package_install: true
```

## Go Compiler-Specific Properties

The `go` installer type is used for installing Go compilers with automatic standard library building. It extends the `tarballs` installer type and automatically builds the Go standard library for specified architectures during installation.

| Property | Description | Default |
|----------|-------------|---------|
| `build_stdlib` | Whether to automatically build the standard library during installation | `true` |
| `build_stdlib_archs` | List of architectures to build the standard library for | `["linux/amd64", "linux/arm64"]` |

Example of Go compiler configuration:

```yaml
compilers:
  go:
    type: go
    check_exe: go/bin/go version
    compression: gz
    dir: golang-{{name}}
    untar_path: go
    url: https://go.dev/dl/go{{name}}.linux-amd64.tar.gz
    build_stdlib: true
    build_stdlib_archs:
      - linux/amd64
      - linux/arm64
    targets:
      - 1.23.8
      - 1.24.2
```

The standard library cache is stored in the `cache` subdirectory of the Go installation. Architecture-specific marker files (e.g., `.built_linux_amd64`) are created to track which architectures have been built.

## Pre/Post Build Scripts

Libraries can define scripts to run before and after building:

```yaml
prebuild_script:
  - curl -sL -o zlib.tgz https://conan.compiler-explorer.com/downloadpkg/zlib/1.3.1/%compiler%/%arch%/%libcxx%
  - mkdir -p /tmp/zlib
  - tar xzf zlib.tgz -C /tmp/zlib

postbuild_script:
  - rm -Rf /tmp/zlib
  - readelf -sW ../install/lib/libboost_iostreams.so | c++filt | grep zlib_base
```

For Windows, separate PowerShell scripts can be provided:

```yaml
prebuild_script_pwsh:
  - echo "not building with zlib"
```

## Using YAML Anchors

Standard YAML anchors can be used to reuse script blocks across multiple targets:

```yaml
script: &intel-one-install-script |
  rm -Rf ~/.intel
  rm -Rf ~/intel
  rm -Rf /var/intel/installercache
  bash {{script_filename}} -s -a -s --action install --eula accept --install-dir $CE_STAGING_DIR/{{dir}}
  rm -Rf ~/.intel
  rm -Rf ~/intel
  rm -Rf /var/intel/installercache
```

This can then be used elsewhere in the same file:

```yaml
script: *intel-one-install-script
```

## Version Differentiation

For cases where URL patterns or package structures change between versions, you can use nested sections:

```yaml
rust:
  type: rust
  dir: rust-{{name}}
  # other shared config here
  older:
    base_package: rustc-{{name}}-x86_64-unknown-linux-gnu
    targets:
      - 1.0.0
      - 1.1.0
  newer:
    base_package: rust-{{name}}-x86_64-unknown-linux-gnu
    targets:
      - 1.5.0
      - 1.6.0
```

## Special Compiler Features

Some compilers have unique features:

1. **EDG Compilers**:
```yaml
macro_output_dir: base/lib
macro_gen: edg-compiler/make_predef_macro_table
```

2. **Nightly compilers with symlinks**:
```yaml
targets:
  - name: trunk
    symlink: gcc-snapshot
```

3. **Complex templating for embedded platforms**:
```yaml
url: https://github.com/espressif/crosstool-NG/releases/download/esp-{{name}}/{{arch_prefix}}-{{release_name}}-{{host_type}}.tar.{{compression}}
```

## Example Configurations

### Compiler Example

```yaml
compilers:
  c++:
    x86:
      gcc:
        type: s3tarballs
        check_exe: bin/g++ --version
        targets:
          - 8.1.0
          - 8.2.0
          - 8.3.0
```

### Library Example

```yaml
libraries:
  c++:
    boost:
      build_type: cmake
      check_file: README.md
      lib_type: static
      repo: boostorg/boost
      targets:
        - 1.78.0
        - 1.79.0
      type: github
```

### Cross-Compiler Example

```yaml
cross:
  type: s3tarballs
  arch_prefix:
  gcc:
    s3_path_prefix: "{{subdir}}-gcc-{{name}}"
    path_name: "{{subdir}}/gcc-{{name}}"
    untar_dir: "gcc-{{name}}"
    check_exe: "bin/{{arch_prefix}}-g++ --version"
    subdir: arm
    arm-wince:
      path_name: "{{subdir}}/gcc-ce-{{name}}"
      arch_prefix: arm-mingw32ce
      subdir: arm-wince
      untar_dir: "gcc-ce-{{name}}"
      s3_path_prefix: "gcc-ce-{{name}}"
      targets:
        - 8.2.0
```

## Adding New Languages, Compilers, or Libraries

### Adding a New Programming Language

To add a new programming language to Compiler Explorer:

1. **Create a Language YAML File**:
   Create a file named `bin/yaml/your_language.yaml` following this pattern:
   ```yaml
   compilers:
     your_language:
       compiler_name:  # Optional level - can be omitted if only one compiler for the language
         type: <installer_type>
         check_exe: "bin/your_compiler --version"
         targets:
           - 1.0.0
           - 1.1.0
           # More versions...
   ```

2. **Choose an Appropriate Installer Type**:
   - For Compiler Explorer-managed builds; use S3-hosted tarballs: `s3tarballs`. Managed builds are ones we run on CE's own infrastructure, building the compiler specifically for our environment. See, for example https://github.com/compiler-explorer/misc-builder/.
   - For compiler that can be installed by extracting a pre-built URL: `tarballs`
   - For GitHub-hosted compilers: `github`

3. **Common Properties for New Configurations**:
   - `check_exe`: Command to verify installation (required)
   - `dir`: Installation directory pattern (usually language-name-{{version}})
   - For GitHub projects:
     - `repo`: GitHub repository (e.g., "your-org/compiler")
     - `method`: Clone method (typically "archive" or "clone_branch")

### Adding a New Compiler or Library to an Existing Language

1. Identify the appropriate YAML file based on the language
2. Add a new target under the appropriate category
3. Set required properties based on the installation type

### Testing Your Configuration

```bash
# List available targets
./bin/ce_install list compilers/your_language

# Install a specific target
./bin/ce_install install compilers/your_language/x86/compiler_name 1.0.0

# Check installation location
ls /opt/compiler-explorer/
```

## Command Line Tool

The `ce_install` tool provides several commands for working with the YAML configuration:

- `list`: List installation targets matching a filter
- `verify`: Verify the installation of targets matching a filter
- `install`: Install targets matching a filter
- `build`: Build library targets matching a filter

By default it will try and install to `/opt/compiler-explorer` but this can be changed with `--dest`.

## Testing, Verification and Troubleshooting

The following workflow is recommended for adding and testing new compiler configurations:

1. **Develop Configuration**:
   Start by copying an existing similar language configuration as a template.

2. **Validate YAML Syntax**:
   Ensure your YAML is well-formed using a YAML linter. The pre-commit hooks (if enabled) will do this for you (`pre-commit run --all` to do it on demand)

3. **Listing Test**:
   Run `./bin/ce_install list <your-target>` to verify the configuration loads.

4. **Dry-Run Installation**:
   Run `./bin/ce_install --dry-run install <your-target>` to simulate installation.

5. **Full Installation Test**:
   Run `./bin/ce_install install <your-target>` to perform the actual installation.

### Troubleshooting Tips

When installation fails, check the following:

1. Verify the URL or source location is correct
2. Ensure the `check_exe` or `check_file` path is correct
3. Check for missing dependencies
4. Look for interpolation errors in property values
5. For GitHub installer issues, check repository access and tag/release names
6. For S3 installers, verify bucket access and path structure
7. Use `--debug` flag for verbose output: `./bin/ce_install --debug install <your-target>`

If a target uses a custom build system or requires special handling, consider using the `script` installer type with a custom installation script.
