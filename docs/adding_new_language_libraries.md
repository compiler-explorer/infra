# Adding new language library support

This documents the steps required to add library build and distribution
support for a new language in CE. Go support (PR #1942) is used as a
concrete reference throughout.

## Overview

CE distributes pre-built library artifacts via a Conan server. The build
pipeline works as follows:

1. Libraries are defined in YAML configuration
2. `ce_install build` invokes a language-specific builder class
3. The builder compiles each library against each compiler version
4. Compiled artifacts are packaged and uploaded to Conan
5. At runtime, CE downloads Conan packages and makes them available to
   compilations

Each language has its own builder because compilation models differ
significantly (C++ produces `.a`/`.so`, Rust produces `.rlib`, Go
populates a build cache, etc.).

## Checklist

### 1. Define libraries in YAML

Add a section to `bin/yaml/libraries.yaml` under the language name:

```yaml
go:
  uuid:
    build_type: gomod
    module: github.com/google/uuid
    targets:
    - v1.6.0
    type: gomod
```

The `type` field maps to an installer class (step 2). The `build_type`
field maps to a builder class (step 3). The `targets` list defines
versions to build. Any additional fields (e.g., `module`, `import_path`)
are language-specific and read by the builder via `LibraryBuildConfig`.

Existing language sections to reference: `c++` (cmake/make), `rust`
(cargo/cratesio), `fortran` (fpm), `go` (gomod).

### 2. Create an installable class

Create `bin/lib/installable/<type>.py` with a class extending
`Installable`. For Conan-distributed libraries this is typically a
minimal marker class -- the builder does the real work:

```python
class GoModuleInstallable(Installable):
    def is_installed(self) -> bool:
        return True  # Conan handles installation

    @property
    def is_squashable(self) -> bool:
        return False  # not distributed via squashfs
```

See `bin/lib/installable/go_module.py` (Go) or
`bin/lib/installable/crates_io.py` (Rust) as examples.

Register the class in `bin/lib/installation.py` by adding it to
`_INSTALLER_TYPES`:

```python
_INSTALLER_TYPES = {
    ...
    "gomod": GoModuleInstallable,
}
```

The key must match the `type` field in your YAML entries.

### 3. Create a builder class

Create `bin/lib/<language>_library_builder.py`. This is where the bulk
of the work lives. The builder must:

- Accept compiler properties, library config, and build parameters
- For each compiler version, compile the library and package the output
- Upload packages to Conan via `conan export-pkg` and `conan upload`
- Track success/failure via the Conan proxy server's API

The builder must expose a `makebuild(buildfor)` method that returns
`[succeeded, skipped, failed]` counts.

The `makebuildfor()` method (called per compiler) must call
`conanproxy_login()` before any build step that could fail and trigger
`save_build_logging()`. The logging endpoint requires a valid auth
token, so deferring the login until after the build will send
`Bearer None` if an early step fails.

Existing builders to reference:
- `bin/lib/go_library_builder.py` -- Go (GOCACHE delta capture)
- `bin/lib/rust_library_builder.py` -- Rust (Cargo)
- `bin/lib/fortran_library_builder.py` -- Fortran (FPM)
- `bin/lib/library_builder.py` -- C++ (cmake/make)

### 4. Wire the builder into the build dispatch

In `bin/lib/installable/installable.py`, add an `elif` branch to the
`build()` method (around line 270) that routes your `build_type` to your
builder:

```python
elif self.build_config.build_type == "gomod":
    gbuilder = GoLibraryBuilder(
        _LOGGER, self.language, self.context[-1],
        self.target_name, self.install_context, self.build_config
    )
    return gbuilder.makebuild(buildfor)
```

### 5. Register Conan compiler type

If the language uses a compiler type name that doesn't already exist in
Conan's settings, add it to `init/settings.yml` under the `compiler`
section:

```yaml
compiler:
    golang:
        version: ANY
        libcxx: ANY
```

The `version: ANY` and `libcxx: ANY` settings avoid constraining the
version strings. The `libcxx` field is required by Conan's settings
schema even if unused.

### 6. Add compiler property parsing (if needed)

If the builder needs language-specific compiler properties (e.g., Go
needs `goos` and `goarch`), update `bin/lib/amazon_properties.py` to
parse them from the properties file and propagate them from groups to
individual compilers. The builder reads these via `self.compilerprops`.

### 7. Update CI workflows

Three places need changes:

**Language detection** in `.github/workflows/lin-lib-build.yaml` -- add
a case to the shell `if/elif` chain that extracts the language from the
library path:

```bash
elif [[ "$LIBRARY" == libraries/go/* ]]; then
  LANGUAGE="go"
  LIBRARY_NAME="${LIBRARY#libraries/go/}"
```

The extracted language and library name are passed to
`init/start-builder.sh`, which reconstructs the path as
`libraries/$LANGUAGE/$LIBRARY_NAME` and calls `ce_install build`.

**Default filters** in the scheduled build workflows -- add
`libraries/<language>` to the default filter string in both:
- `.github/workflows/scheduled-lin-lib-builds.yaml` (daily)
- `.github/workflows/scheduled-lin-lib-builds-full.yaml` (weekly)

If the language has nightly builds, also update
`.github/workflows/scheduled-nightly-lin-lib-builds.yaml`.

### 8. Write tests

Tests go in `bin/test/` mirroring the source structure:
- `bin/test/<language>_library_builder_test.py` for the builder
- `bin/test/installable/<type>_test.py` for the installable
- `bin/test/cache_delta_test.py` if you add shared utilities

Mock external dependencies (AWS, Conan server, subprocess calls) and
test both success and failure paths.

### 9. Verify locally

```bash
# List discovered libraries
bin/ce_install list 'libraries/<language>'

# List scheduled build commands
bin/ce_install list-gh-build-commands-linux --per-lib 'libraries/<language>'

# Dry-run a build for a specific compiler
bin/ce_install --dry-run build 'libraries/<language>/<name>' --buildfor <compiler_id>

# Run tests and static checks
make static-checks
```

### 10. Runtime support in compiler-explorer

The main `compiler-explorer` repo needs changes to consume the Conan
packages at runtime. This is language-specific -- for Go it meant
merging `cache_delta/` into GOCACHE before compilation; for Rust it
means making `.rlib` files available to rustc; for C++ it means setting
include/library paths.

These changes live in the compiler-explorer repo (not infra) and should
be coordinated with the infra PR.

## Reference: files touched for Go library support

```
bin/yaml/libraries.yaml               -- library definitions (go section)
bin/lib/installable/go_module.py       -- installable marker class
bin/lib/go_library_builder.py          -- builder (build logic, Conan packaging)
bin/lib/cache_delta.py                 -- shared utility (GOCACHE delta capture)
bin/lib/installation.py                -- register "gomod" installer type
bin/lib/installable/installable.py     -- route "gomod" build_type to builder
bin/lib/amazon_properties.py           -- parse goos/goarch from compiler properties
init/settings.yml                      -- register "golang" Conan compiler type
.github/workflows/lin-lib-build.yaml   -- language detection for CI builds
.github/workflows/scheduled-*          -- default filters for scheduled builds
bin/test/                              -- unit tests for all new code
```
