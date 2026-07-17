# Go Library Building

This document describes how Go module libraries are built, packaged, and
distributed for use in Compiler Explorer.

## Background

Go's compilation model differs fundamentally from C/C++/Rust. There are no
static libraries or header files. Instead, Go uses a build cache (`GOCACHE`)
containing compiled package objects keyed by "action IDs" -- hashes derived from
the source, compiler version, build flags, and environment. When a user's
program imports a library, the Go toolchain checks the cache for a matching
action ID and skips recompilation if found.

The library build system exploits this by pre-populating the GOCACHE with
compiled artifacts for each module, so that user compilations on CE get cache
hits instead of compiling dependencies from scratch every time.

## Architecture Overview

```
libraries.yaml          GoModuleInstallable         GoLibraryBuilder
  (config)        -->     (marker class)       -->    (build logic)
                                                          |
                                                    CacheDeltaCapture
                                                          |
                                                     Conan package
                                                   (cache_delta/ +
                                                    module_sources/ +
                                                    metadata.json)
```

Key source files:

- `bin/yaml/libraries.yaml` -- library definitions under `go:` section
- `bin/lib/installable/go_module.py` -- `GoModuleInstallable`, a thin marker
  class (Conan handles actual installation)
- `bin/lib/go_library_builder.py` -- `GoLibraryBuilder`, the build engine
- `bin/lib/cache_delta.py` -- `CacheDeltaCapture`, reusable delta-snapshot
  utility
- `bin/lib/golang_stdlib.py` -- stdlib pre-build (prerequisite for library
  builds)

## The Cache Delta Problem

A naive approach would build a module and ship the entire GOCACHE. But the
GOCACHE already contains the standard library (~3000 files), which is installed
separately per compiler version. Shipping the whole cache would mean massive
duplication across every library package.

The solution: snapshot the cache before building the library, build, then
extract only the new files (the "delta"). For `github.com/google/uuid`, this
reduces the package from ~3375 files to ~469 files (~85% reduction).

`CacheDeltaCapture` implements this pattern:

1. Copy the compiler's stdlib cache into a temporary GOCACHE directory
2. `capture_baseline()` -- record all files present
3. Run the build (which adds library-specific entries)
4. `get_delta()` / `copy_delta_to()` -- extract only the new files

This utility is language-agnostic and designed for reuse with Python/JS library
caches in the future.

## Build Process (step by step)

For each (library, version, compiler) triple:

1. **Locate stdlib cache** -- The builder looks for a pre-built cache at
   `<goroot>/../cache` or `<goroot>/cache`. If none exists, the build is
   skipped because without the stdlib cache, the library cache alone provides
   no speedup.

2. **Download module** -- `go mod download <module>@<version>` fetches the
   module and its transitive dependencies into a temporary GOPATH.

3. **Snapshot baseline** -- Copy the stdlib cache into a temporary GOCACHE,
   then call `CacheDeltaCapture.capture_baseline()`.

4. **Build the module** -- Two build passes:
   - First: compile a stub `main.go` that `import _ "<import_path>"` the
     module, using `go build -trimpath -v -o /dev/null .`
   - Second: build all subpackages via
     `go build -trimpath -v <module>/...` to populate cache entries for
     the full module tree (non-fatal if some subpackages fail due to build
     constraints)

5. **Extract delta** -- `CacheDeltaCapture.copy_delta_to()` copies only the
   new cache entries.

6. **Package for Conan** -- The build folder gets:
   - `cache_delta/` -- the compiled cache entries
   - `module_sources/` -- module source from `GOPATH/pkg/mod`
   - `metadata.json` -- module path, version, cache stats, go.sum content
   - `conanfile.py` + `conanexport.sh` -- Conan packaging glue

7. **Upload** -- `conan export-pkg` followed by `conan upload` to the CE Conan
   server.

## Action ID Compatibility

This is the single hardest part of the system. Go's build cache keys (action
IDs) are sensitive to many environment variables. A cache entry built with
different settings than the CE runtime will never get a hit. The following must
match exactly between build-time and runtime:

### `-trimpath`

CE compiles user code with `go build -trimpath`. Without `-trimpath`, the
action ID includes absolute paths from the build machine, which differ from
the CE runtime paths. Both the stdlib build and the library build must use
`-trimpath`.

This was discovered after initial builds produced cache misses despite
identical source and compiler versions.

### `CGO_ENABLED`

The default is `1` on Linux. The stdlib build uses `CGO_ENABLED=0` (to avoid
C toolchain dependencies during cross-compilation), but library builds use
`CGO_ENABLED=1` to match the CE runtime default.

The commit history shows this was initially set to `0`, then reverted, then
set to `1` explicitly -- each change caused action ID mismatches.

### `GOOS` / `GOARCH`

Read from compiler properties (`group.<id>.goos`, `group.<id>.goarch`) rather
than inferred, falling back to `linux`/`amd64`. These values are part of the
action ID and must match what CE passes at runtime.

### Import path notation

Subpackages must be built using the full import path (`module/...`) rather than
`./...` from inside the module directory. The build working directory affects
how Go computes action IDs; using import path notation makes the IDs
independent of the build directory.

## YAML Configuration

Libraries are defined in `bin/yaml/libraries.yaml` under the `go:` section:

```yaml
go:
  uuid:
    build_type: gomod
    module: github.com/google/uuid
    targets:
    - v1.6.0
    type: gomod
  protobuf:
    build_type: gomod
    import_path: google.golang.org/protobuf/proto
    module: google.golang.org/protobuf
    targets:
    - v1.34.1
    - v1.36.0
    type: gomod
```

Fields:

- `module` (required) -- Go module path (the argument to `go get`)
- `import_path` (optional) -- package path to import in the stub program.
  Defaults to `module`. Needed for modules like `protobuf` whose root package
  contains `package main` and cannot be imported directly.
- `build_type` -- must be `gomod`
- `type` -- must be `gomod`
- `targets` -- list of version tags

## Conan Namespace

Library packages are prefixed with `go_` (e.g., `go_uuid`, `go_protobuf`) to
avoid namespace collisions with C/C++ libraries that might share the same
short name.

The Conan compiler type is `golang` for standard Go compilers, `gccgo` for
gccgo (though gccgo module support is not yet functional).

## Conan Settings

The `golang` compiler type is registered in `init/settings.yml` with
`version: ANY` and `libcxx: ANY` (libcxx is unused but required by Conan's
settings schema).

## Stdlib Pre-build

Library builds depend on a pre-built stdlib cache. This is handled by
`bin/lib/golang_stdlib.py` during compiler installation (the `go` installer
type in `bin/yaml/go.yaml`).

Key details:
- Default architectures: `linux/amd64`, `linux/arm`, `linux/arm64`
- Stored in `<go-installation>/cache/`
- Marker files: `.built_linux_amd64` etc.
- Uses `CGO_ENABLED=0` and `-trimpath`
- Download URL: `https://dl.google.com/go/go<version>.linux-amd64.tar.gz`

## CLI Usage

```bash
# Dry-run build for a specific compiler
ce_install --dry-run build 'libraries/go/uuid' --buildfor gl1238

# Build all Go libraries for all compilers
ce_install build 'libraries/go'

# Force rebuild everything
ce_install build 'libraries/go/uuid' --force
```

The `--force` flag passes `"forceall"` as the buildfor parameter, which
bypasses both the "has failed before" and "already uploaded" checks.

## Skipped Compilers

The builder skips:
- `gotip`, `go-tip` -- nightly/unstable versions
- `gccgo` -- does not support Go modules
- Compilers without an `exe` property
- Compilers listed in the library's `skip_compilers` config
- Compilers without a stdlib cache

## Compiler Properties Integration

The builder reads compiler properties via `get_properties_compilers_and_libraries()`
from `bin/lib/amazon_properties.py`. The PR added `goos` and `goarch` property
parsing, which are inherited from compiler groups to individual compilers
(e.g., `group.386gl.goarch=386`).

## Failure Handling

- Build failures are reported to the Conan proxy server
  (`/buildfailed` endpoint)
- Failed builds are tracked so they are not re-attempted unless `--force` is
  used
- Subpackage build failures (`module/...`) are logged as warnings but do not
  fail the overall build (some subpackages may have unsatisfied build
  constraints)
- Build timeouts (600s) are treated as failures

## Package Contents

A Conan package for a Go library contains:

```
cache_delta/
  00/
    00abcdef12345678-d    # compiled object
  01/
    01abcdef12345678-d
  ...
module_sources/
  cache/
    download/
      sumdb/
      ...
    vcs/
      ...
metadata.json
```

The `cache_delta/` entries are keyed by action ID hash prefixes, matching Go's
GOCACHE layout. At runtime, CE merges these into the GOCACHE before
compilation so that `go build` gets cache hits on library packages.
