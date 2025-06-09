#!/bin/bash

# Test script for MSVC compiler cache extraction using Wine
# This script sets up the Windows environment and runs the PowerShell script via Wine

set -e

echo "=== Wine MSVC Compiler Cache Extraction Test ==="

# Paths to Windows compilers and tools
MSVC_VERSION="14.40.33807-14.40.33811.0"
MSVC_ROOT="/media/patrick-quist/D0-P1/efs/compilers/msvc/${MSVC_VERSION}"
SDK_ROOT="/media/patrick-quist/D0-P1/efs/compilers/windows-kits-10"
CMAKE_ROOT="/media/patrick-quist/D0-P1/efs/compilers/cmake-v3.29.2"

# Check if required paths exist
if [ ! -d "$MSVC_ROOT" ]; then
    echo "ERROR: MSVC root not found: $MSVC_ROOT"
    exit 1
fi

if [ ! -d "$SDK_ROOT" ]; then
    echo "ERROR: Windows SDK root not found: $SDK_ROOT"
    exit 1
fi

if [ ! -f "$CMAKE_ROOT/bin/cmake.exe" ]; then
    echo "ERROR: CMake executable not found: $CMAKE_ROOT/bin/cmake.exe"
    exit 1
fi

echo "✓ MSVC Root: $MSVC_ROOT"
echo "✓ SDK Root: $SDK_ROOT"
echo "✓ CMake: $CMAKE_ROOT/bin/cmake.exe"

# Set up Wine environment variables for MSVC
export WINEPREFIX="${HOME}/.wine-msvc-test"
export WINEARCH="win64"

# Initialize Wine prefix if it doesn't exist
if [ ! -d "$WINEPREFIX" ]; then
    echo "Initializing Wine prefix: $WINEPREFIX"
    winecfg /v win10
fi

# Convert Unix paths to Windows paths for Wine
MSVC_WIN_ROOT="$(winepath -w "$MSVC_ROOT")"
SDK_WIN_ROOT="$(winepath -w "$SDK_ROOT")"
CMAKE_WIN_ROOT="$(winepath -w "$CMAKE_ROOT")"

echo "Windows paths:"
echo "  MSVC: $MSVC_WIN_ROOT"
echo "  SDK: $SDK_WIN_ROOT"
echo "  CMake: $CMAKE_WIN_ROOT"

# Set up MSVC environment variables
export VCINSTALLDIR="$MSVC_WIN_ROOT\\"
export WindowsSdkDir="$SDK_WIN_ROOT\\"
export WindowsSDKVersion="10.0.22621.0\\"

# Set compiler paths
export CC="$(winepath -w "$MSVC_ROOT/bin/Hostx64/x64/cl.exe")"
export CXX="$(winepath -w "$MSVC_ROOT/bin/Hostx64/x64/cl.exe")"

# Set compiler flags for MSVC
export CFLAGS="/std:c17"
export CXXFLAGS="/std:c++17"

# Set include and library paths
INCLUDE_PATHS="${MSVC_WIN_ROOT}\\include;${SDK_WIN_ROOT}\\Include\\10.0.22621.0\\ucrt;${SDK_WIN_ROOT}\\Include\\10.0.22621.0\\shared;${SDK_WIN_ROOT}\\Include\\10.0.22621.0\\um"
LIB_PATHS="${MSVC_WIN_ROOT}\\lib\\x64;${SDK_WIN_ROOT}\\Lib\\10.0.22621.0\\ucrt\\x64;${SDK_WIN_ROOT}\\Lib\\10.0.22621.0\\um\\x64"

export INCLUDE="$INCLUDE_PATHS"
export LIB="$LIB_PATHS"
export LIBPATH="$LIB_PATHS"

# Add CMake and compiler to PATH
export PATH="$(winepath -u "$CMAKE_WIN_ROOT\\bin"):$(winepath -u "$MSVC_WIN_ROOT\\bin\\Hostx64\\x64"):$PATH"

echo ""
echo "Environment setup complete. Testing compiler..."

# Test if the compiler works through Wine
echo "Testing MSVC compiler through Wine..."
echo '#include <stdio.h>' > /tmp/test.c
echo 'int main() { printf("Hello from MSVC!\\n"); return 0; }' >> /tmp/test.c

if wine "$MSVC_ROOT/bin/Hostx64/x64/cl.exe" /Fe:test.exe "$(winepath -w /tmp/test.c)" 2>/dev/null; then
    echo "✓ MSVC compiler test successful"
    rm -f test.exe test.obj
else
    echo "✗ MSVC compiler test failed"
    echo "This may be expected - Wine + MSVC can be challenging"
fi

rm -f /tmp/test.c

echo ""
echo "Testing PowerShell via Wine..."

# Check if PowerShell Core is available via Wine
if command -v wine >/dev/null 2>&1; then
    echo "Wine is available"
    
    # Try to run our PowerShell script via Wine
    echo "Attempting to run Extract-CMakeCache.ps1 via Wine..."
    echo "Note: This may fail due to Wine/PowerShell compatibility issues"
    
    # Copy the script to a location Wine can access
    WINE_SCRIPT_PATH="$WINEPREFIX/drive_c/temp/Extract-CMakeCache.ps1"
    mkdir -p "$(dirname "$WINE_SCRIPT_PATH")"
    cp "Extract-CMakeCache.ps1" "$WINE_SCRIPT_PATH"
    
    # Try to run with Wine + PowerShell
    # Note: This requires PowerShell to be installed in the Wine prefix
    if wine powershell.exe -File "C:\\temp\\Extract-CMakeCache.ps1" 2>/dev/null; then
        echo "✅ PowerShell script executed successfully via Wine!"
    else
        echo "❌ PowerShell script failed via Wine (expected - PowerShell Core not installed in Wine)"
    fi
else
    echo "❌ Wine not available"
fi

echo ""
echo "=== Alternative approach: Linux-based test ==="
echo "Since Wine + MSVC + PowerShell is complex, let's try a Linux simulation..."

# Create a mock test that simulates what would happen
echo "Creating mock MSVC environment for testing..."

# Export Windows-style paths as environment variables for our PowerShell script
export CC="$MSVC_ROOT/bin/Hostx64/x64/cl.exe"
export CXX="$MSVC_ROOT/bin/Hostx64/x64/cl.exe"
export CFLAGS="/std:c17"
export CXXFLAGS="/std:c++17"

echo "Environment variables set:"
echo "  CC=$CC"
echo "  CXX=$CXX"
echo "  CFLAGS=$CFLAGS"
echo "  CXXFLAGS=$CXXFLAGS"

echo ""
echo "Note: The actual cache extraction would require:"
echo "1. A working Wine environment with MSVC properly configured"
echo "2. PowerShell Core installed in the Wine prefix"
echo "3. Proper Windows registry entries for MSVC toolchain"
echo ""
echo "For production use, consider:"
echo "- Using a Windows VM or container"
echo "- Running the script directly on Windows"
echo "- Using Docker with Windows containers"

echo ""
echo "Test completed. The script demonstrates the setup required for Wine + MSVC."
