# Library Configuration Reference

Technical reference for all library settings in `bin/yaml/libraries.yaml` and the
build system that processes them.

For step-by-step guides on adding libraries, see:
- [Adding new language libraries](adding_new_language_libraries.md)
- [Adding Rust crates](adding_rust_crates.md)
- [C++ library commands](cpp_library_commands.md)
- [Fortran library commands](fortran_library_commands.md)
- [Go library building](go_library_building.md)

For general YAML installation configuration (property inheritance, string
interpolation, installer types), see [ce_install_yaml.md](ce_install_yaml.md).

## YAML Structure

```yaml
libraries:
  <language>:          # c++, c, rust, fortran, go, android-java
    <library-id>:
      type: <installer-type>
      build_type: <build-system>
      lib_type: <output-type>
      targets:
        - <version-string>
        - name: <version-string>
          <per-version-overrides>
```

Every property set at a parent level is inherited by all children. Individual
targets can override any property by using `name: <version>` dict syntax instead
of a bare string. See [ce_install_yaml.md](ce_install_yaml.md) for details on
inheritance and string interpolation.

## Core Properties

These apply to all library entries regardless of language or build system.

| Property | Type | Default | Description |
|---|---|---|---|
| `type` | string | (required) | Installer type. Determines how source is fetched. See [Installer Types](#installer-types). |
| `build_type` | string | `none` | Build system. Determines how the library is compiled. See [Build Types](#build-types). |
| `lib_type` | string | `headeronly` | Output type. See [Library Types](#library-types). |
| `targets` | list | (required) | Versions to install. Plain strings or dicts with `name` plus overrides. |
| `check_file` | string | | File path (relative to install root) to verify installation succeeded. |
| `check_exe` | string/list | | Command to run to verify installation. Either this or `check_file` is needed. |
| `depends` | list | | Other installables this library requires, e.g. `libraries/c++/openssl 1_1_1g`. Resolved paths available as `%DEP0%`, `%DEP1%`, etc. |
| `if` | string | | Conditional flag. Library is only installed when `--enable <flag>` is passed. Common values: `nightly`, `non-free`. |
| `install_always` | bool | `false` | Force reinstall every time (bypasses check_file/check_exe). |

## Library Types

Set via `lib_type`. Determines what the build produces and how CE links the library.

| Value | Description |
|---|---|
| `headeronly` | No compiled output. Source/headers only. Cannot have `staticliblink` or `sharedliblink`. |
| `static` | Produces static archives (`.a` / `.lib`). |
| `shared` | Produces shared objects (`.so` / `.dll`) linked against C++ stdlib. |
| `cshared` | C shared library with no C++ stdlib dependency. Requires `use_compiler`. See [cshared in depth](#cshared-in-depth). |

Parsed and validated in `bin/lib/library_build_config.py:LibraryBuildConfig`.

### `cshared` in depth

`cshared` is for pure-C shared libraries that have no C++ standard library
dependency. The resulting `.so` must not link against `libstdc++.so` or
`libc++.so` -- the builder verifies this via `ldd` after the build and rejects
any binary that does. (This is the inverse of `shared`, which *requires* one of
those to be present.)

The purpose is to produce a single compiler-independent artifact. A `shared`
library is built once per compiler/stdlib combination because different compilers
produce ABI-incompatible C++ objects. A `cshared` library, being pure C, works
with any compiler, so it only needs to be built once.

Use `cshared` when:

- The library is written in C (not C++).
- The library's `.so` should be usable from any compiler without ABI concerns.
- Other libraries (including non-C++ languages like Fortran) need to link against
  it at build time.

Do not use `cshared` for C++ libraries, even if they expose a C API -- if any
C++ stdlib symbols leak into the `.so`, the build validation will reject it.

#### How `cshared` differs from `shared` in the build pipeline

| Aspect | `shared` | `cshared` |
|---|---|---|
| Compilers used | All compatible compilers | Exactly one, set by `use_compiler` |
| stdlib iteration | Clang builds twice (libstdc++ and libc++) | Always one build, no stdlib variation |
| Binary validation | Requires `libstdc++.so` or `libc++.so` in `ldd` output | Requires *absence* of both |
| Conan identity | Per-compiler (e.g. `compiler=gcc / version=13.1`) | Always `compiler=cshared / version=cshared` |
| Download endpoint | `/downloadpkg/<lib>/<ver>/<compiler>/<arch>/<libcxx>` | `/downloadcshared/<lib>/<ver>` |

The synthetic Conan identity (`compiler=cshared / version=cshared`) is registered
in `init/settings.yml`. Because there is only one artifact per library version,
the Conan server exposes a simpler download URL with no compiler parameters.

#### `cshared` as a build dependency

The `downloadcshared` endpoint makes `cshared` libraries easy to consume in
`prebuild_script` for other languages. For example, the Fortran `http_client`
library downloads the `cshared` curl artifact:

```yaml
prebuild_script:
  - curl -sL -o curl.tgz https://conan.compiler-explorer.com/downloadcshared/curl/7.83.1
  - tar -xzf curl.tgz
```

The tarball contains the Conan package layout (`lib/`, `include/`, etc.). This
works because `curl` uses both `lib_type: cshared` and `package_install: true`,
so its Conan package includes headers alongside the `.so`.

#### `cshared` configuration requirements

- `use_compiler` is mandatory. The builder raises an error at config load time if
  it is missing.
- Pick a stable GCC or Clang version as the compiler (e.g. `g102`, `g105`,
  `clang1400`). It does not matter which, since the output is C-only.
- If downstream consumers need headers, also set `package_install: true` so the
  install tree (including `include/`) is packaged.

Current `cshared` libraries:

| Library | Compiler | Also uses `package_install` |
|---|---|---|
| `curl` | `clang1400` | yes |
| `icu` | `g102` | yes |
| `pcre2` | `g105` | yes |
| `sqlite` | `g102` | no |

## Build Types

Set via `build_type`. Routes to a language-specific builder class in
`bin/lib/installable/installable.py`.

| Value | Builder | Description |
|---|---|---|
| `cmake` | `LibraryBuilder` | CMake-based C/C++ library. Most common for C++ libs. |
| `make` | `LibraryBuilder` | Autotools / Makefile-based C/C++ library. |
| `none` | `LibraryBuilder` (Windows only) | Cloned but not compiled. Used for header-only libs that need staging on Windows. |
| `never` | (skipped) | Never compiled. Typically header-only libs fetched as tarballs. |
| `manual` | (skipped) | Manually built outside the automated system. |
| `cargo` | `RustLibraryBuilder` | Rust crate compiled with Cargo. |
| `fpm` | `FortranLibraryBuilder` | Fortran library built with Fortran Package Manager. |
| `gomod` | `GoLibraryBuilder` | Go module. Builds populate GOCACHE. |

## Installer Types

Set via `type`. Determines how source code is fetched. The most commonly used
types for libraries are listed here. For the full list, see
[ce_install_yaml.md](ce_install_yaml.md).

| Type | Class | Typical use |
|---|---|---|
| `github` | `GitHubInstallable` | C++ libraries from GitHub repos |
| `gitlab` | `GitLabInstallable` | Libraries from GitLab |
| `bitbucket` | `BitbucketInstallable` | Libraries from Bitbucket |
| `tarballs` | `TarballInstallable` | Libraries downloaded as archives from URLs |
| `singleFile` | `SingleFileInstallable` | Single JAR/file downloads (Android libraries) |
| `script` | `ScriptInstallable` | Custom install script |
| `cratesio` | `CratesIOInstallable` | Rust crates from crates.io |
| `gomod` | `GoModuleInstallable` | Go modules (marker class; Conan handles distribution) |
| `s3tarballs` | `S3TarballInstallable` | Archives from the CE S3 bucket |

## Build Configuration Properties

These properties control how a library is compiled. Read by `LibraryBuildConfig`
from the library's YAML dict.

### CMake / Make Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `extra_cmake_arg` | list | `[]` | Additional arguments passed to `cmake`. Supports build-time variable expansion. |
| `extra_make_arg` | list | `[]` | Additional arguments passed to `make` or `ninja`. |
| `make_targets` | list | `[]` | Specific build targets (e.g. `all`, `bal`, `bsl`). If empty, builds the default target. |
| `make_utility` | string | `make` | Build tool: `make` or `ninja`. |
| `configure_flags` | list | `[]` | Flags passed to `./configure` when `build_type: make`. |
| `source_folder` | string | `""` | Subdirectory within the source tree that contains `configure` / build files. When set, the build script `cd`s into this directory before running configure and make. Useful when the tarball root is not the build root (e.g. ICU extracts to `icu/` with source in `icu/source/`). |
| `package_install` | bool | `false` | Run `cmake --install` / `make install` to copy artifacts to an install prefix. See [package_install in depth](#package_install-in-depth). |

### Linking Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `staticliblink` | list | `[]` | Names of static `.a` libraries to link (without `lib` prefix and extension). |
| `sharedliblink` | list | `[]` | Names of shared `.so`/`.dll` libraries to link. |

These are used to generate CE `.properties` files that tell the frontend which
libraries to pass to the linker. Header-only libraries must not set either.

Per-version linking can be specified by making a target a dict:

```yaml
targets:
  - name: '20250127.0'
    staticliblink:
      - absl_base
      - absl_strings
```

### Compiler Selection Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `use_compiler` | string | `""` | Build with a specific compiler only. Required when `lib_type: cshared`. |
| `skip_compilers` | list | `[]` | Compiler IDs to skip when building. |
| `build_fixed_arch` | string | `""` | Build only for a specific architecture (e.g. `x86_64`, `x86`). |
| `build_fixed_stdlib` | string | `""` | Build only with a specific C++ stdlib (e.g. `libc++`). |

### Script Properties

Scripts run at various stages of the install and build pipeline. Each has a
PowerShell variant for Windows builds.

| Property | Windows variant | When it runs |
|---|---|---|
| `after_stage_script` | `after_stage_script_pwsh` | After source is fetched/staged, before build. Runs in the source directory. |
| `prebuild_script` | `prebuild_script_pwsh` | Before the build script executes. Runs in the build directory. |
| `postbuild_script` | `postbuild_script_pwsh` | After the build script completes. |

Scripts are lists of shell commands (or PowerShell commands for `_pwsh` variants).

Build-time variable expansion is available in `prebuild_script` and
`postbuild_script`:

| Variable | Description |
|---|---|
| `%compiler%` | Compiler executable path |
| `%arch%` | Target architecture |
| `%libcxx%` | C++ standard library |
| `%stdver%` | C++ standard version |
| `%buildtype%` | Build configuration (Release/Debug) |
| `%DEP0%`, `%DEP1%`, ... | Install paths of entries in `depends` list |

### Miscellaneous Build Properties

| Property | Type | Default | Description |
|---|---|---|---|
| `copy_files` | list | `[]` | Conan `self.copy(...)` lines for custom file packaging. |
| `requires_tree_copy` | bool | `false` | Copy full source tree into build folder. Required for FPM builds that modify files in place. |

### `package_install` in depth

Controls whether a formal install step runs after the build, and changes how
artifacts are collected into the Conan package. Default is `false`; always forced
to `true` on Windows regardless of what the YAML says.

#### Effect on the build script

For `build_type: cmake` (and `none`), when `package_install` is true the
generated build script appends:

```sh
cmake --install . > ceinstall_0.txt 2>&1
```

CMake is already configured with `--install-prefix <staging>/install`, so this
copies headers, libraries, and any other install components into that prefix
using the project's own `install()` rules.

For `build_type: make`, when `package_install` is true:
- `./configure` is called with `--prefix=<staging>/install`
- After the make targets, `make install` is appended

When `package_install` is **false**, no install step runs. Instead, the builder
uses `find` to move built `.a` and `.so*` files into the build folder root:

```sh
find . -iname 'lib<name>*.a' -type f -exec mv {} . \;
find . -iname 'lib<name>*.so*' -type f,l -exec mv {} . \;
```

#### Effect on Conan packaging

The generated `conanfile.py` differs significantly:

With `package_install: true`:
```python
def package(self):
    self.copy("*", src="../install", dst=".", keep_path=True)
```
Copies the entire install tree verbatim -- headers in `include/`, libraries in
`lib/`, and anything else the build system installs. Directory structure is
preserved.

Without `package_install`:
```python
def package(self):
    self.copy("lib<name>*.a", dst="lib", keep_path=False)
    self.copy("lib<name>*.so*", dst="lib", keep_path=False)
```
Only the specific library binaries matching `staticliblink` / `sharedliblink`
are collected into a flat `lib/` directory. No headers are included.

#### Effect on binary validation

After building, the system checks that valid library binaries exist. With
`package_install: true`, it looks in the install prefix subdirectories
(`<install>/lib` and `<install>/bin`). Without it, it looks in the raw build
directory.

#### When to use `package_install: true`

Headers that exist in the original source (from the GitHub clone or tarball
extraction) are already available without `package_install` -- the source tree is
staged as-is. `package_install` is only needed when the build system produces
headers that are not in the original source:

1. **Generated headers.** Some libraries generate headers during the build that
   encode compiler or architecture details. A common pattern in autotools
   projects is a `config.h.in` template that produces a `config.h` only when the
   build script runs. Without `package_install`, these generated headers are not
   collected into the Conan package.

2. **Restructured headers.** Some libraries reorganize their header layout during
   `cmake --install` or `make install` -- for example, merging headers from
   multiple subdirectories into a single `include/` tree, or renaming/moving
   files. The original source layout does not match what consumers expect to
   `#include`.

3. **`cshared` libraries consumed by other builds.** Libraries downloaded via
   `downloadcshared` (e.g. curl used by Fortran http_client) need generated or
   restructured headers alongside the `.so` in the tarball. That only happens
   with `package_install: true`.

Do not use it when:

- The library's source headers are already in the layout consumers expect (the
  common case for most GitHub-hosted libraries).
- The library produces only a `.a` or `.so` with no generated headers (the
  `find` fallback is sufficient and produces a smaller Conan package).

Libraries using `package_install: true`: abseil, bde, boost_bin, cpptrace, curl,
hpx, icu, kokkos, liblzma, mfem, pcre2, qt, re2, zlib, and some nightly entries.

## Source Fetch Properties

These control how source code is downloaded. Applicable properties depend on the
`type`.

### GitHub / GitLab / Bitbucket

| Property | Type | Default | Description |
|---|---|---|---|
| `repo` | string | (required) | Repository path, e.g. `catchorg/Catch2`. |
| `method` | string | `archive` | Clone method: `archive`, `clone_branch`, `nightlyclone`, `nightlybranch`. |
| `target_prefix` | string | `""` | Prefix for git tags, e.g. `v` makes target `1.0.0` look for tag `v1.0.0`. |
| `recursive` | bool | `true` | Clone submodules recursively. |
| `subdir` | string | | Override subdirectory within install path. |
| `path_name` | string | | Override for the full install path. |

### Tarballs

| Property | Type | Default | Description |
|---|---|---|---|
| `url` | string | (required) | Download URL. Supports `{{name}}` interpolation. |
| `compression` | string | `gz` | Archive compression: `gz`, `xz`, `bz2`. |
| `untar_dir` | string | | Directory name after extraction. |
| `dir` | string | | Installation directory. |
| `extract_only` | string | | Only extract this subdirectory from the archive. |
| `strip_components` | int | `0` | Strip leading path components from tar. |

### Single File

| Property | Type | Default | Description |
|---|---|---|---|
| `url` | string | (required) | Download URL. |
| `dir` | string | | Install directory. |
| `filename` | string | | Filename to save as. |

## Language-Specific Configuration

### C++ Libraries

The largest section. Uses `github`, `tarballs`, `bitbucket`, or `gitlab` as
installer types. Build types are `cmake`, `make`, `none`, `never`, or `manual`.

Typical header-only library:
```yaml
catch2:
  check_file: single_include/catch2/catch.hpp
  repo: catchorg/Catch2
  target_prefix: v
  targets:
    - 2.13.10
  type: github
```

Typical static library with cmake:
```yaml
fmt:
  build_type: cmake
  check_file: README.md
  lib_type: static
  make_utility: ninja
  package_install: true
  repo: fmtlib/fmt
  staticliblink:
    - fmt
  targets:
    - 11.0.0
  type: github
```

C shared library (built with a fixed compiler, no C++ stdlib dependency):
```yaml
sqlite:
  build_type: make
  check_file: configure
  dir: libs/sqlite/{{name}}
  lib_type: cshared
  sharedliblink:
    - sqlite3
  targets:
    - name: 3.40.0
      untar_dir: sqlite-autoconf-3400000
      url: https://sqlite.org/2022/sqlite-autoconf-3400000.tar.gz
  type: tarballs
  use_compiler: g102
```

Library with prebuild dependencies:
```yaml
boost_bin:
  build_type: cmake
  prebuild_script:
    - curl -sL -o zlib.tgz https://conan.compiler-explorer.com/downloadpkg/zlib/1.3.1/%compiler%/%arch%/%libcxx%
    - mkdir -p /tmp/zlib
    - tar xzf zlib.tgz -C /tmp/zlib
  prebuild_script_pwsh:
    - echo "not building with zlib"
  postbuild_script:
    - rm -Rf /tmp/zlib
  extra_cmake_arg:
    - -DBOOST_INSTALL_LAYOUT=system
    - -DBUILD_SHARED_LIBS=ON
  lib_type: shared
  sharedliblink:
    - boost_iostreams
  package_install: true
```

### Rust Libraries

All Rust libraries use `type: cratesio` and `build_type: cargo`. Targets are
crate version numbers. No linking properties are needed; Cargo handles
dependency resolution.

```yaml
serde:
  build_type: cargo
  targets:
    - 1.0.136
    - 1.0.219
  type: cratesio
```

### Fortran Libraries

All Fortran libraries use `type: github` and `build_type: fpm`. All require
`requires_tree_copy: true` because FPM modifies files in place during builds.

```yaml
json_fortran:
  build_type: fpm
  check_file: fpm.toml
  repo: jacobwilliams/json-fortran
  requires_tree_copy: true
  targets:
    - 8.3.0
  type: github
```

Libraries with C dependencies use `prebuild_script` to download pre-built shared
libraries from the Conan server:

```yaml
http_client:
  build_type: fpm
  check_file: fpm.toml
  prebuild_script:
    - curl -sL -o curl.tgz https://conan.compiler-explorer.com/downloadcshared/curl/7.83.1
    - tar -xzf curl.tgz
    - cp lib/libcurl-d.so lib/libcurl.so
    - export FPM_CFLAGS="-I/opt/compiler-explorer/libs/curl/7.83.1/include"
  repo: fortran-lang/http-client
  requires_tree_copy: true
  target_prefix: v
  targets:
    - 0.1.0
  type: github
```

### Go Libraries

All Go libraries use `type: gomod` and `build_type: gomod`. The builder
pre-populates GOCACHE with compiled artifacts. See
[go_library_building.md](go_library_building.md) for architectural details.

| Property | Required | Description |
|---|---|---|
| `module` | yes | Go module path (the argument to `go get`). |
| `import_path` | no | Package import path if different from `module`. Needed when the module root contains `package main`. |

```yaml
protobuf:
  build_type: gomod
  import_path: google.golang.org/protobuf/proto
  module: google.golang.org/protobuf
  targets:
    - v1.34.1
    - v1.36.0
  type: gomod
```

### Android / Java Libraries

Uses `singleFile` or `script` installer types. No build step; JAR files are
downloaded directly.

Supports `nightly` / `release` sub-sections for libraries with both stable and
nightly channels:

```yaml
r8-keep-annotations:
  check_file: keepanno-annotations.jar
  dir: r8-{{name}}-keepanno
  filename: keepanno-annotations.jar
  nightly:
    if: nightly
    targets:
      - latest
    url: https://storage.googleapis.com/r8-releases/raw/latest-dev/keepanno-annotations.jar
  release:
    targets:
      - 8.7.18
    url: https://storage.googleapis.com/r8-releases/raw/{{name}}/keepanno-annotations.jar
  type: singleFile
```

## Nightly / Conditional Libraries

Libraries or groups of libraries can be conditionally installed using `if`:

```yaml
nightly:
  if: nightly
  stdlib_fortran:
    build_type: fpm
    method: nightlybranch
    repo: fortran-lang/stdlib
    targets:
      - stdlib-fpm
    type: github
```

The `nightly` key acts as a grouping namespace. The `if: nightly` on the group
means none of those entries are installed unless `--enable nightly` is passed to
`ce_install`.

For git-based nightly sources, use `method: nightlyclone` (fetches default branch
HEAD) or `method: nightlybranch` (fetches a named branch). Combine with
`install_always: true` to force re-fetching on every run.

## Build Pipeline

All library builds go through the Conan server
(`https://conan.compiler-explorer.com`). Each build is uniquely identified by
(OS, compiler type, compiler version, C++ stdlib, architecture, library name,
library version, commit hash).

The pipeline, triggered by `ce_install build`:

1. Source is fetched and staged according to `type` and its properties
2. `after_stage_script` runs (if defined)
3. For each compatible compiler:
   a. `prebuild_script` runs
   b. The language-specific builder generates and executes a build script
   c. `postbuild_script` runs
   d. Artifacts are packaged via `conan export-pkg`
   e. Package is uploaded via `conan upload`
4. Build results (success/failure) are reported to the Conan proxy server

The builder checks the Conan proxy to skip already-uploaded builds. Use `--force`
to rebuild everything.

## String Interpolation

Properties support Jinja2-style `{{variable}}` expansion. Common variables:

| Variable | Source |
|---|---|
| `{{name}}` | Target version string |
| `{{underscore_name}}` | Version with dots replaced by underscores |
| `{{yaml_dir}}` | Path to `bin/yaml` directory |
| `{{resource_dir}}` | Path to resources directory |
| `{{destination}}` | Installation destination root |

## Key Source Files

| File | Role |
|---|---|
| `bin/yaml/libraries.yaml` | All library definitions |
| `bin/lib/library_build_config.py` | `LibraryBuildConfig` -- parses and validates build properties |
| `bin/lib/library_builder.py` | C++ builder (cmake/make) |
| `bin/lib/rust_library_builder.py` | Rust builder (cargo) |
| `bin/lib/fortran_library_builder.py` | Fortran builder (fpm) |
| `bin/lib/go_library_builder.py` | Go builder (GOCACHE delta capture) |
| `bin/lib/library_yaml.py` | YAML loading, properties file generation |
| `bin/lib/library_props.py` | CE `.properties` file generation utilities |
| `bin/lib/installable/installable.py` | Base class; routes `build_type` to builder |
| `bin/lib/installable/git.py` | GitHub/GitLab/Bitbucket installers |
| `bin/lib/installable/archives.py` | Tarball, S3, zip installers |
| `bin/lib/installable/go_module.py` | Go module installer (marker class) |
| `bin/lib/installation.py` | Maps `type` strings to installer classes |
