# CMake Compiler Cache Extraction Guide

This guide explains how to use the `Extract-CMakeCache.ps1` script to generate reusable CMake compiler cache files that can significantly speed up CMake configuration across multiple projects by skipping expensive compiler detection phases.

## What This Script Does

The script leverages CMake's own comprehensive compiler detection to create portable cache files that can be reused across different projects. Instead of maintaining version-specific compiler detection logic, it lets CMake do all the work and extracts only the reusable components.

## Prerequisites

- **PowerShell Core** (pwsh) - Works on Windows, Linux, and macOS
- **CMake** 3.10 or later
- **C and/or C++ Compiler** (MSVC, GCC, Clang, etc.)

## Quick Start

### Step 1: Set Environment Variables

```bash
# Linux/macOS with GCC (both C and C++)
export CC=gcc
export CFLAGS="-std=c17"
export CXX=g++
export CXXFLAGS="-std=c++17"

# Linux/macOS with Clang (both C and C++)
export CC=clang
export CFLAGS="-std=c17"
export CXX=clang++
export CXXFLAGS="-std=c++20"

# C++ only
export CXX=g++
export CXXFLAGS="-std=c++17"
```

```powershell
# Windows with MSVC (both C and C++)
$env:CC = "cl.exe"
$env:CFLAGS = "/std:c17"
$env:CXX = "cl.exe"
$env:CXXFLAGS = "/std:c++17"

# Windows with MinGW (both C and C++)
$env:CC = "gcc"
$env:CFLAGS = "-std=c17"
$env:CXX = "g++"
$env:CXXFLAGS = "-std=c++17"
```

### Step 2: Run the Extraction Script

```bash
# Using environment variables
pwsh /path/to/Extract-CMakeCache.ps1

# Using parameters for C++ only
pwsh /path/to/Extract-CMakeCache.ps1 -CXXCompilerPath "clang++" -CXXCompilerFlags "-std=c++20"

# Using parameters for both C and C++
pwsh /path/to/Extract-CMakeCache.ps1 -CCompilerPath "clang" -CCompilerFlags "-std=c17" -CXXCompilerPath "clang++" -CXXCompilerFlags "-std=c++20"
```

### Step 3: Use the Generated Cache

```bash
# Extract cache files to your build directory BEFORE running cmake
cd your-project
mkdir build
cd build
unzip /path/to/cmake-compiler-cache-extracted.zip

# Run cmake - should skip compiler detection
cmake ..
```

## Script Parameters

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `CCompilerPath` | Path to C compiler | `$env:CC` | `"gcc"`, `"cl.exe"`, `"clang"` |
| `CCompilerFlags` | Additional C compiler flags | `$env:CFLAGS` | `"-std=c17"`, `"/std:c17"` |
| `CXXCompilerPath` | Path to C++ compiler | `$env:CXX` | `"g++"`, `"cl.exe"`, `"clang++"` |
| `CXXCompilerFlags` | Additional C++ compiler flags | `$env:CXXFLAGS` | `"-std=c++20"`, `"/std:c++17"` |
| `OutputDir` | Output directory for cache files | `"./cmake-cache-extracted"` | `"./my-cache"` |
| `ZipOutput` | Create zip file | `$true` | `$false` |
| `KeepTempDir` | Keep temporary build directory | `$false` | `$true` |

## Usage Examples

### Basic Usage

```bash
# Set compilers and run with defaults (both C and C++)
export CC=gcc
export CFLAGS="-std=c17 -O2"
export CXX=g++
export CXXFLAGS="-std=c++17 -O2"
pwsh Extract-CMakeCache.ps1

# C++ only
export CXX=g++
export CXXFLAGS="-std=c++17 -O2"
pwsh Extract-CMakeCache.ps1
```

### Advanced Usage

```bash
# Custom output directory, keep temp files for inspection (both C and C++)
pwsh Extract-CMakeCache.ps1 \
  -CCompilerPath "/usr/bin/gcc-11" \
  -CCompilerFlags "-std=c17 -march=native" \
  -CXXCompilerPath "/usr/bin/g++-11" \
  -CXXCompilerFlags "-std=c++20 -march=native" \
  -OutputDir "./gcc11-cache" \
  -KeepTempDir $true
```

### Cross-Platform Examples

```bash
# Linux with GCC 13 (both C and C++)
export CC=/usr/bin/gcc-13
export CFLAGS="-std=c17 -O3"
export CXX=/usr/bin/g++-13
export CXXFLAGS="-std=c++23 -O3"
pwsh Extract-CMakeCache.ps1

# macOS with Apple Clang (both C and C++)
export CC=clang
export CFLAGS="-std=c17 -stdlib=libc++"
export CXX=clang++
export CXXFLAGS="-std=c++20 -stdlib=libc++"
pwsh Extract-CMakeCache.ps1
```

```powershell
# Windows with MSVC 2022 (both C and C++)
$env:CC = "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64\cl.exe"
$env:CFLAGS = "/std:c17 /O2"
$env:CXX = "C:\Program Files\Microsoft Visual Studio\2022\Professional\VC\Tools\MSVC\14.38.33130\bin\Hostx64\x64\cl.exe"
$env:CXXFLAGS = "/std:c++20 /O2"
.\Extract-CMakeCache.ps1

# Windows with MinGW-w64 (both C and C++)
$env:CC = "C:\msys64\mingw64\bin\gcc.exe"
$env:CFLAGS = "-std=c17 -O2"
$env:CXX = "C:\msys64\mingw64\bin\g++.exe"
$env:CXXFLAGS = "-std=c++17 -O2"
.\Extract-CMakeCache.ps1
```

## Generated Files

The script creates:

```
cmake-cache-extracted/
├── CMakeCache.txt                           # Sanitized cache variables
├── CMakeFiles/
│   └── {VERSION}/
│       ├── CMakeCCompiler.cmake            # Complete C compiler info (if C used)
│       ├── CMakeCXXCompiler.cmake          # Complete C++ compiler info (if C++ used)
│       └── CMakeSystem.cmake               # System information
├── README.md                               # Usage instructions
└── cmake-compiler-cache-extracted.zip     # Packaged files
```

## Integration Workflows

### CI/CD Pipeline

```yaml
# GitHub Actions example
- name: Generate CMake Cache
  run: |
    export CC=gcc-11
    export CFLAGS="-std=c17"
    export CXX=g++-11
    export CXXFLAGS="-std=c++20"
    pwsh scripts/Extract-CMakeCache.ps1

- name: Cache CMake Compiler Detection
  uses: actions/cache@v3
  with:
    path: cmake-compiler-cache-extracted.zip
    key: cmake-cache-${{ runner.os }}-gcc11-${{ hashFiles('**/CMakeLists.txt') }}

- name: Configure Project
  run: |
    mkdir build && cd build
    unzip ../cmake-compiler-cache-extracted.zip
    cmake ..
```

### Docker Multi-Stage Build

```dockerfile
# Stage 1: Generate cache
FROM ubuntu:22.04 AS cache-generator
RUN apt-get update && apt-get install -y cmake gcc g++ powershell
COPY Extract-CMakeCache.ps1 /scripts/
RUN export CC=gcc CFLAGS="-std=c17" CXX=g++ CXXFLAGS="-std=c++17" && \
    pwsh /scripts/Extract-CMakeCache.ps1

# Stage 2: Use cache for builds
FROM ubuntu:22.04 AS builder
RUN apt-get update && apt-get install -y cmake gcc g++
COPY --from=cache-generator /cmake-compiler-cache-extracted.zip /cache/
COPY . /src
RUN cd /src && mkdir build && cd build && \
    unzip /cache/cmake-compiler-cache-extracted.zip && \
    cmake .. && make
```

### Makefile Integration

```makefile
CMAKE_CACHE = cmake-compiler-cache-extracted.zip

# Generate cache once
$(CMAKE_CACHE):
	@echo "Generating CMake compiler cache..."
	export CC=gcc CFLAGS="-std=c17" CXX=g++ CXXFLAGS="-std=c++17" && pwsh Extract-CMakeCache.ps1

# Use cache for configuration
build/Makefile: $(CMAKE_CACHE) CMakeLists.txt
	@mkdir -p build
	cd build && unzip -o ../$(CMAKE_CACHE) && cmake ..

build: build/Makefile
	$(MAKE) -C build

.PHONY: clean-cache
clean-cache:
	rm -f $(CMAKE_CACHE)
	rm -rf cmake-cache-extracted/
```

## What Gets Skipped

When using the cache successfully, you'll see these phases skipped:

```
-- The C compiler identification is GNU 13.3.0       ← Skipped detection
-- The CXX compiler identification is GNU 13.3.0     ← Skipped detection
-- Detecting C compiler ABI info                     ← Uses cached ABI
-- Detecting C compiler ABI info - done
-- Detecting CXX compiler ABI info                   ← Uses cached ABI
-- Detecting CXX compiler ABI info - done
-- Check for working C compiler: /usr/bin/gcc - skipped    ← Key indicator!
-- Check for working CXX compiler: /usr/bin/g++ - skipped  ← Key indicator!
-- Detecting C compile features                      ← Uses cached features
-- Detecting C compile features - done
-- Detecting CXX compile features                    ← Uses cached features
-- Detecting CXX compile features - done
```

The key indicators are: **`Check for working C compiler: [compiler] - skipped`** and **`Check for working CXX compiler: [compiler] - skipped`**

## Troubleshooting

### Cache Not Working

If compiler detection still runs:

1. **Check file placement**: Cache files must be in build directory BEFORE cmake runs
2. **Verify compiler path**: Cached compiler path must match current compiler
3. **Check permissions**: Ensure cache files are readable

```bash
# Debug: Check if cache files exist
ls -la CMakeCache.txt CMakeFiles/*/CMake*Compiler.cmake

# Debug: Verify compiler path matches
grep CMAKE_CXX_COMPILER CMakeCache.txt
which $CXX
```

### Compiler Path Issues

```bash
# If compiler moved, regenerate cache
export CXX=/new/path/to/g++
pwsh Extract-CMakeCache.ps1

# For relative paths, use absolute paths
export CXX=$(which g++)
pwsh Extract-CMakeCache.ps1
```

### Permission Errors

```bash
# Ensure script is executable
chmod +x Extract-CMakeCache.ps1

# Check PowerShell execution policy (Windows)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Performance Impact

Typical savings per project configuration:

- **Small projects**: 0.2-0.5 seconds saved
- **Large projects**: 1-3 seconds saved
- **CI/CD pipelines**: Cumulative savings across multiple builds
- **Docker builds**: Faster layer rebuilds when only source changes

## Best Practices

1. **One cache per compiler/version combination**
2. **Regenerate when compiler updates**
3. **Include compiler flags in cache generation**
4. **Store cache in version control for team consistency**
5. **Use in CI/CD for consistent build environments**

## Compatibility

- ✅ **CMake**: 3.10+ (tested with 3.28+)
- ✅ **Compilers**: MSVC, GCC, Clang, Apple Clang
- ✅ **Platforms**: Windows, Linux, macOS
- ✅ **PowerShell**: 6.0+ (PowerShell Core)
- ✅ **Project Types**: All C++ project configurations tested

## Security Notes

- Cache files contain only compiler and system information
- No source code, project paths, or sensitive data included
- Safe to share across team members with same compiler setup
- Consider using separate caches for different security contexts

---

*This cache extraction approach leverages CMake's own comprehensive compiler detection rather than maintaining custom version-specific logic, ensuring compatibility with all CMake versions and compiler updates.*
