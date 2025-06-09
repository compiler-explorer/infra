#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Extracts and packages CMake compiler cache files for reuse across projects.

.DESCRIPTION
    This script runs a minimal CMake configuration to generate compiler detection files,
    then extracts the reusable components that can skip compiler detection in other projects.
    This approach leverages CMake's own comprehensive compiler detection instead of 
    maintaining our own version-specific logic.
    
    Supports both C and C++ compilers in a single pass.

.PARAMETER CCompilerPath
    Path to the C compiler (uses $env:CC if not specified)

.PARAMETER CCompilerFlags
    Additional C compiler flags (uses $env:CFLAGS if not specified)

.PARAMETER CXXCompilerPath
    Path to the C++ compiler (uses $env:CXX if not specified)

.PARAMETER CXXCompilerFlags
    Additional C++ compiler flags (uses $env:CXXFLAGS if not specified)

.PARAMETER OutputDir
    Directory where the cache files will be generated (default: ./cmake-cache-extracted)

.PARAMETER ZipOutput
    Create a zip file with the cache files (default: $true)

.PARAMETER KeepTempDir
    Keep the temporary build directory for inspection (default: $false)

.EXAMPLE
    # Linux with GCC (both C and C++)
    $env:CC = "gcc"
    $env:CFLAGS = "-std=c17"
    $env:CXX = "g++"
    $env:CXXFLAGS = "-std=c++17"
    ./Extract-CMakeCache.ps1

.EXAMPLE
    # Windows with MSVC
    $env:CC = "cl.exe"
    $env:CFLAGS = "/std:c17"
    $env:CXX = "cl.exe"
    $env:CXXFLAGS = "/std:c++17"
    .\Extract-CMakeCache.ps1

.EXAMPLE
    # With parameters (C++ only)
    .\Extract-CMakeCache.ps1 -CXXCompilerPath "clang++" -CXXCompilerFlags "-std=c++20"

.EXAMPLE
    # With parameters (both C and C++)
    .\Extract-CMakeCache.ps1 -CCompilerPath "clang" -CCompilerFlags "-std=c17" -CXXCompilerPath "clang++" -CXXCompilerFlags "-std=c++20"
#>

param(
    [string]$CCompilerPath = $env:CC,
    [string]$CCompilerFlags = $env:CFLAGS,
    [string]$CXXCompilerPath = $env:CXX,
    [string]$CXXCompilerFlags = $env:CXXFLAGS,
    [string]$OutputDir = "./cmake-cache-extracted",
    [bool]$ZipOutput = $true,
    [switch]$KeepTempDir
)

# Show parameter values when keeping temp directory
if ($KeepTempDir) {
    Write-Host "KeepTempDir enabled - temporary directory will be preserved" -ForegroundColor Cyan
}

# Validation - at least one compiler must be specified
if (-not $CCompilerPath -and -not $CXXCompilerPath) {
    Write-Error "No compiler specified. Set `$env:CC and/or `$env:CXX or use -CCompilerPath/-CXXCompilerPath parameters."
    exit 1
}

# Function to resolve compiler path
function Resolve-CompilerPath {
    param([string]$CompilerPath)
    
    if (-not $CompilerPath) {
        return $null
    }
    
    try {
        if ($IsWindows -or $PSVersionTable.PSVersion.Major -lt 6) {
            return (Get-Command $CompilerPath -ErrorAction Stop).Source
        } else {
            $WhichResult = which $CompilerPath 2>/dev/null
            if ($WhichResult) {
                return $WhichResult
            } else {
                return (Get-Command $CompilerPath -ErrorAction Stop).Source
            }
        }
    } catch {
        Write-Error "Compiler not found: $CompilerPath"
        exit 1
    }
}

# Resolve compiler paths
$CCompilerFullPath = $null
$CXXCompilerFullPath = $null

if ($CCompilerPath) {
    $CCompilerFullPath = Resolve-CompilerPath $CCompilerPath
    Write-Host "Using C compiler: $CCompilerFullPath" -ForegroundColor Green
}

if ($CXXCompilerPath) {
    $CXXCompilerFullPath = Resolve-CompilerPath $CXXCompilerPath
    Write-Host "Using C++ compiler: $CXXCompilerFullPath" -ForegroundColor Green
}

# Create temporary directory for CMake test
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "cmake-cache-extract-$(Get-Random)"
Write-Host "Creating temporary project in: $TempDir" -ForegroundColor Cyan

try {
    New-Item -Path $TempDir -ItemType Directory -Force | Out-Null
    
    # Determine which languages to enable
    $Languages = @()
    if ($CCompilerFullPath) { $Languages += "C" }
    if ($CXXCompilerFullPath) { $Languages += "CXX" }
    $LanguagesList = $Languages -join " "

    # Create minimal CMakeLists.txt for compiler detection
    $MinimalCMakeList = @"
cmake_minimum_required(VERSION 3.10)
project(CompilerDetection $LanguagesList)

# Force CMake to detect compiler features and ABI
"@

    # Add language enablement
    foreach ($lang in $Languages) {
        $MinimalCMakeList += "`nenable_language($lang)"
    }

    # Add test executables
    if ($CCompilerFullPath) {
        $MinimalCMakeList += @"

# Create a minimal C executable to ensure full compiler testing
add_executable(test_detection_c test.c)
"@
    }

    if ($CXXCompilerFullPath) {
        $MinimalCMakeList += @"

# Create a minimal C++ executable to ensure full compiler testing
add_executable(test_detection_cxx test.cpp)
"@
    }

    # Add information printing
    $MinimalCMakeList += "

# Print detected information
message(STATUS ""Platform: `${CMAKE_SYSTEM_NAME}"")"

    if ($CCompilerFullPath) {
        $MinimalCMakeList += "
message(STATUS ""C Compiler: `${CMAKE_C_COMPILER}"")
message(STATUS ""C Compiler ID: `${CMAKE_C_COMPILER_ID}"")
message(STATUS ""C Compiler Version: `${CMAKE_C_COMPILER_VERSION}"")"
    }

    if ($CXXCompilerFullPath) {
        $MinimalCMakeList += "
message(STATUS ""C++ Compiler: `${CMAKE_CXX_COMPILER}"")
message(STATUS ""C++ Compiler ID: `${CMAKE_CXX_COMPILER_ID}"")
message(STATUS ""C++ Compiler Version: `${CMAKE_CXX_COMPILER_VERSION}"")"
    }

    $MinimalCMakeList += "
message(STATUS ""Cache extraction successful!"")"

    # Create test source files
    if ($CCompilerFullPath) {
        $TestCContent = @"
/* Minimal C test program to verify compiler works */
int main() {
    return 0;
}
"@
        Set-Content -Path (Join-Path $TempDir "test.c") -Value $TestCContent
    }

    if ($CXXCompilerFullPath) {
        $TestCppContent = @"
// Minimal C++ test program to verify compiler works
int main() {
    return 0;
}
"@
        Set-Content -Path (Join-Path $TempDir "test.cpp") -Value $TestCppContent
    }

    Set-Content -Path (Join-Path $TempDir "CMakeLists.txt") -Value $MinimalCMakeList

    # Create build directory
    $BuildDir = Join-Path $TempDir "build"
    New-Item -Path $BuildDir -ItemType Directory -Force | Out-Null

    # Set up environment - store originals and set new values
    $OriginalCC = $env:CC
    $OriginalCFLAGS = $env:CFLAGS
    $OriginalCXX = $env:CXX
    $OriginalCXXFLAGS = $env:CXXFLAGS
    
    if ($CCompilerFullPath) {
        $env:CC = $CCompilerFullPath
        if ($CCompilerFlags) {
            $env:CFLAGS = $CCompilerFlags
        }
    }
    
    if ($CXXCompilerFullPath) {
        $env:CXX = $CXXCompilerFullPath
        if ($CXXCompilerFlags) {
            $env:CXXFLAGS = $CXXCompilerFlags
        }
    }

    try {
        Write-Host "Running CMake to detect compiler..." -ForegroundColor Yellow
        
        # Run CMake configuration
        Push-Location $BuildDir
        $CMakeOutput = cmake .. 2>&1
        $CMakeExitCode = $LASTEXITCODE
        Pop-Location

        if ($CMakeExitCode -ne 0) {
            Write-Host "CMake configuration failed:" -ForegroundColor Red
            Write-Host $CMakeOutput -ForegroundColor Red
            Write-Host "Exiting with error code 1" -ForegroundColor Red
            $global:LASTEXITCODE = 1
            exit 1
        }

        Write-Host "✓ CMake configuration successful" -ForegroundColor Green
        
        # Find the CMake version directory
        $CMakeFilesDir = Join-Path $BuildDir "CMakeFiles"
        $VersionDirs = Get-ChildItem -Path $CMakeFilesDir -Directory | Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' }
        
        if ($VersionDirs.Count -eq 0) {
            Write-Error "Could not find CMake version directory in $CMakeFilesDir"
            exit 1
        }
        
        $CMakeVersion = $VersionDirs[0].Name
        $CMakeVersionDir = Join-Path $CMakeFilesDir $CMakeVersion
        Write-Host "Found CMake version: $CMakeVersion" -ForegroundColor Cyan

        # Create output directory
        if (Test-Path $OutputDir) {
            $OutputDir = Resolve-Path $OutputDir
        } else {
            $OutputDir = New-Item -Path $OutputDir -ItemType Directory -Force | Select-Object -ExpandProperty FullName
        }

        $OutputCMakeFilesDir = Join-Path $OutputDir "CMakeFiles"
        $OutputVersionDir = Join-Path $OutputCMakeFilesDir $CMakeVersion
        New-Item -Path $OutputVersionDir -ItemType Directory -Force | Out-Null

        # Copy essential compiler detection files
        $FilesToCopy = @(
            @{
                Source = Join-Path $BuildDir "CMakeCache.txt"
                Dest = Join-Path $OutputDir "CMakeCache.txt"
                Description = "Main cache file"
            },
            @{
                Source = Join-Path $CMakeVersionDir "CMakeSystem.cmake"
                Dest = Join-Path $OutputVersionDir "CMakeSystem.cmake"
                Description = "System information"
            }
        )
        
        # Add C compiler files if C compiler was used
        if ($CCompilerFullPath) {
            $FilesToCopy += @{
                Source = Join-Path $CMakeVersionDir "CMakeCCompiler.cmake"
                Dest = Join-Path $OutputVersionDir "CMakeCCompiler.cmake"
                Description = "C compiler detection"
            }
        }
        
        # Add C++ compiler files if C++ compiler was used
        if ($CXXCompilerFullPath) {
            $FilesToCopy += @{
                Source = Join-Path $CMakeVersionDir "CMakeCXXCompiler.cmake"
                Dest = Join-Path $OutputVersionDir "CMakeCXXCompiler.cmake"
                Description = "C++ compiler detection"
            }
        }

        Write-Host "Extracting reusable cache files..." -ForegroundColor Yellow
        
        foreach ($file in $FilesToCopy) {
            if (Test-Path $file.Source) {
                Copy-Item -Path $file.Source -Destination $file.Dest -Force
                Write-Host "✓ Copied: $($file.Description)" -ForegroundColor Gray
            } else {
                Write-Warning "Missing file: $($file.Source)"
            }
        }

        # Create a sanitized version of CMakeCache.txt with portable paths
        $CacheContent = Get-Content -Path (Join-Path $OutputDir "CMakeCache.txt")
        $SanitizedCache = @()
        
        foreach ($line in $CacheContent) {
            # Skip project-specific directory paths
            if ($line -match '^(CMAKE_CACHEFILE_DIR|CMAKE_HOME_DIRECTORY|.*_BINARY_DIR|.*_SOURCE_DIR):') {
                continue
            }
            
            # Replace absolute paths in compiler-related variables with correct paths
            if ($line -match '^CMAKE_C_COMPILER:FILEPATH=(.+)$' -and $CCompilerFullPath) {
                $SanitizedCache += "CMAKE_C_COMPILER:FILEPATH=$CCompilerFullPath"
            }
            elseif ($line -match '^CMAKE_CXX_COMPILER:FILEPATH=(.+)$' -and $CXXCompilerFullPath) {
                $SanitizedCache += "CMAKE_CXX_COMPILER:FILEPATH=$CXXCompilerFullPath"
            }
            elseif ($line -match '^CMAKE_.*_FLAGS.*=.*') {
                $SanitizedCache += $line
            }
            elseif ($line -match '^CMAKE_.*(LOADED|INITIALIZED|WORKS|COMPILED):INTERNAL=') {
                $SanitizedCache += $line
            }
            elseif ($line -match '^CMAKE_BUILD_TYPE:') {
                $SanitizedCache += $line
            }
            elseif ($line -match '^CMAKE_EXECUTABLE_SUFFIX:') {
                $SanitizedCache += $line
            }
            elseif ($line -match '^#' -or $line.Trim() -eq '') {
                $SanitizedCache += $line
            }
        }

        # Add essential cache variables if they're missing
        $EssentialVars = @(
            "CMAKE_PLATFORM_INFO_INITIALIZED:INTERNAL=1"
        )
        
        if ($CCompilerFullPath) {
            $EssentialVars += "CMAKE_C_COMPILER_LOADED:INTERNAL=1"
        }
        
        if ($CXXCompilerFullPath) {
            $EssentialVars += "CMAKE_CXX_COMPILER_LOADED:INTERNAL=1"
        }

        foreach ($var in $EssentialVars) {
            $varName = $var.Split(':')[0]
            if (-not ($SanitizedCache | Where-Object { $_ -match "^$([Regex]::Escape($varName)):" })) {
                $SanitizedCache += $var
            }
        }

        Set-Content -Path (Join-Path $OutputDir "CMakeCache.txt") -Value $SanitizedCache

        # Create usage instructions
        $CompilerInfo = @()
        if ($CCompilerFullPath) {
            $CompilerInfo += "- C Compiler: $CCompilerFullPath"
            if ($CCompilerFlags) { $CompilerInfo += "- C Compiler Flags: $CCompilerFlags" }
        }
        if ($CXXCompilerFullPath) {
            $CompilerInfo += "- C++ Compiler: $CXXCompilerFullPath"
            if ($CXXCompilerFlags) { $CompilerInfo += "- C++ Compiler Flags: $CXXCompilerFlags" }
        }
        
        $GeneratedFilesList = @("- CMakeCache.txt: Sanitized cache variables (project paths removed)")
        if ($CCompilerFullPath) { $GeneratedFilesList += "- CMakeFiles/$CMakeVersion/CMakeCCompiler.cmake: Complete C compiler detection results" }
        if ($CXXCompilerFullPath) { $GeneratedFilesList += "- CMakeFiles/$CMakeVersion/CMakeCXXCompiler.cmake: Complete C++ compiler detection results" }
        $GeneratedFilesList += "- CMakeFiles/$CMakeVersion/CMakeSystem.cmake: System information"
        
        $UsageInstructions = @"
# CMake Compiler Cache - Extracted from Real CMake

## Generated Files:
$($GeneratedFilesList -join "`n")

## Source Information:
$($CompilerInfo -join "`n")
- CMake Version: $CMakeVersion
- Platform: $($env:OS ?? 'Unix')
- Generated: $(Get-Date)

## How to Use:
1. Copy these files to your CMake build directory BEFORE running cmake
2. Ensure the compiler path is still accessible in the target environment
3. Run cmake as usual - it should skip compiler detection phases

## Example Usage:
``````bash
# Extract cache files to new build directory
unzip cmake-compiler-cache.zip -d ./new-build/

# Run cmake (should skip "Check for working CXX compiler", "Detecting CXX compiler ABI info", etc.)
cd new-build
cmake ../your-project
``````

## What Gets Skipped:
"@

        if ($CCompilerFullPath) {
            $UsageInstructions += @"
- ✅ "The C compiler identification is [compiler]"
- ✅ "Detecting C compiler ABI info"
- ✅ "Check for working C compiler"
- ✅ "Detecting C compile features"
"@
        }

        if ($CXXCompilerFullPath) {
            $UsageInstructions += @"
- ✅ "The CXX compiler identification is [compiler]"
- ✅ "Detecting CXX compiler ABI info"
- ✅ "Check for working CXX compiler"
- ✅ "Detecting CXX compile features"
"@
        }

        $UsageInstructions += @"

## Notes:
- These files are specific to the exact compiler path and version
- If the compiler moves or version changes, regenerate the cache
- The cache includes comprehensive feature detection that our manual script couldn't replicate
- This is the same mechanism CMake uses internally for caching
"@

        $ReadmeFile = Join-Path $OutputDir "README.md"
        Set-Content -Path $ReadmeFile -Value $UsageInstructions

        Write-Host "✓ Generated cache files:" -ForegroundColor Green
        Write-Host "  - CMakeCache.txt (sanitized)" -ForegroundColor Gray
        if ($CCompilerFullPath) {
            Write-Host "  - CMakeFiles/$CMakeVersion/CMakeCCompiler.cmake" -ForegroundColor Gray
        }
        if ($CXXCompilerFullPath) {
            Write-Host "  - CMakeFiles/$CMakeVersion/CMakeCXXCompiler.cmake" -ForegroundColor Gray
        }
        Write-Host "  - CMakeFiles/$CMakeVersion/CMakeSystem.cmake" -ForegroundColor Gray
        Write-Host "  - README.md" -ForegroundColor Gray

        # Create zip file if requested
        if ($ZipOutput) {
            $ZipFile = Join-Path (Split-Path $OutputDir) "cmake-compiler-cache-extracted.zip"
            if (Test-Path $ZipFile) {
                Remove-Item $ZipFile -Force
            }
            
            Write-Host "Creating zip archive..." -ForegroundColor Yellow
            Compress-Archive -Path "$OutputDir/*" -DestinationPath $ZipFile -Force
            Write-Host "✓ Created: $ZipFile" -ForegroundColor Green
            
            $ZipSizeMB = [math]::Round((Get-Item $ZipFile).Length / 1MB, 2)
            Write-Host "  Size: $ZipSizeMB MB" -ForegroundColor Gray
        }

        Write-Host "`n✅ Compiler cache extraction complete!" -ForegroundColor Green
        Write-Host "This cache was generated by CMake itself and includes:" -ForegroundColor Cyan
        Write-Host "  ➤ Complete compiler feature detection" -ForegroundColor Gray
        Write-Host "  ➤ ABI information and toolchain tools" -ForegroundColor Gray
        Write-Host "  ➤ System-specific configuration" -ForegroundColor Gray
        Write-Host "  ➤ All version-specific optimizations" -ForegroundColor Gray

    } finally {
        # Restore environment
        if ($OriginalCC) {
            $env:CC = $OriginalCC
        } else {
            Remove-Item Env:CC -ErrorAction SilentlyContinue
        }
        
        if ($OriginalCFLAGS) {
            $env:CFLAGS = $OriginalCFLAGS
        } else {
            Remove-Item Env:CFLAGS -ErrorAction SilentlyContinue
        }
        
        if ($OriginalCXX) {
            $env:CXX = $OriginalCXX
        } else {
            Remove-Item Env:CXX -ErrorAction SilentlyContinue
        }
        
        if ($OriginalCXXFLAGS) {
            $env:CXXFLAGS = $OriginalCXXFLAGS
        } else {
            Remove-Item Env:CXXFLAGS -ErrorAction SilentlyContinue
        }
    }

} finally {
    # Clean up temporary directory
    if (Test-Path $TempDir) {
        if ($KeepTempDir) {
            Write-Host "Temporary directory preserved: $TempDir" -ForegroundColor Yellow
        } else {
            Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}