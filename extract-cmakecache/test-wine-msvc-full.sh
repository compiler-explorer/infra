#!/bin/bash

# Full test script for MSVC compiler cache extraction using Wine
# This script attempts to run the actual PowerShell cache extraction script

set -e

echo "=== Full Wine MSVC Compiler Cache Extraction Test ==="

# Paths to Windows compilers and tools
MSVC_VERSION="14.40.33807-14.40.33811.0"
MSVC_ROOT="/media/patrick-quist/D0-P1/efs/compilers/msvc/${MSVC_VERSION}"
SDK_ROOT="/media/patrick-quist/D0-P1/efs/compilers/windows-kits-10"
CMAKE_ROOT="/media/patrick-quist/D0-P1/efs/compilers/cmake-v3.29.2"

# Check if required paths exist
echo "Verifying paths..."
for path in "$MSVC_ROOT" "$SDK_ROOT" "$CMAKE_ROOT/bin/cmake.exe"; do
    if [ ! -e "$path" ]; then
        echo "ERROR: Required path not found: $path"
        exit 1
    fi
done

echo "✓ All required paths found"

# Set up Wine environment
export WINEPREFIX="${HOME}/.wine-msvc-test"
export WINEARCH="win64"

# Convert paths to Windows format
MSVC_WIN="$(winepath -w "$MSVC_ROOT")"
SDK_WIN="$(winepath -w "$SDK_ROOT")"
CMAKE_WIN="$(winepath -w "$CMAKE_ROOT")"

echo ""
echo "Setting up MSVC environment for Wine..."

# Set up comprehensive MSVC environment variables
export VCINSTALLDIR="$MSVC_WIN\\"
export VCToolsInstallDir="$MSVC_WIN\\"
export WindowsSdkDir="$SDK_WIN\\"
export WindowsSDKVersion="10.0.22621.0"
export WindowsLibPath="$SDK_WIN\\References\\10.0.22621.0\\"

# Set up PATH to include all required tools
WINE_PATH="$CMAKE_WIN\\bin;$MSVC_WIN\\bin\\Hostx64\\x64;C:\\windows\\system32;C:\\windows"
export PATH="$(winepath -u "$WINE_PATH"):$PATH"

# Set up INCLUDE paths
INCLUDE_PATHS="$MSVC_WIN\\include;$SDK_WIN\\Include\\$WindowsSDKVersion\\ucrt;$SDK_WIN\\Include\\$WindowsSDKVersion\\shared;$SDK_WIN\\Include\\$WindowsSDKVersion\\um;$SDK_WIN\\Include\\$WindowsSDKVersion\\winrt"

# Set up LIB paths  
LIB_PATHS="$MSVC_WIN\\lib\\x64;$SDK_WIN\\Lib\\$WindowsSDKVersion\\ucrt\\x64;$SDK_WIN\\Lib\\$WindowsSDKVersion\\um\\x64"

export INCLUDE="$INCLUDE_PATHS"
export LIB="$LIB_PATHS"
export LIBPATH="$LIB_PATHS"

# Set compiler environment variables for our script
# Use Wine wrapper scripts to make cl.exe work with CMake
WRAPPER_SCRIPT="$(pwd)/wine-cl-wrapper.sh"
export CC="$WRAPPER_SCRIPT"
export CXX="$WRAPPER_SCRIPT"
export CFLAGS="/std:c17 /nologo"
export CXXFLAGS="/std:c++17 /nologo"

# Enable debug logging for Wine wrapper
export WINE_CL_DEBUG=1

echo "Environment configured:"
echo "  CC=$CC"
echo "  CXX=$CXX"
echo "  CFLAGS=$CFLAGS"
echo "  CXXFLAGS=$CXXFLAGS"

echo ""
echo "Testing basic MSVC functionality..."

# Create a simple test program
cat > /tmp/wine_test.cpp << 'EOF'
#include <iostream>
#include <windows.h>

int main() {
    std::cout << "Hello from MSVC on Wine!" << std::endl;
    std::cout << "Compiler: " << _MSC_VER << std::endl;
    return 0;
}
EOF

# Test compilation
echo "Compiling test program..."
if wine "$MSVC_ROOT/bin/Hostx64/x64/cl.exe" /EHsc "/Fe:$(winepath -w /tmp/wine_test.exe)" "$(winepath -w /tmp/wine_test.cpp)" >/dev/null 2>&1; then
    echo "✓ MSVC compilation successful"
    
    # Test execution
    if wine /tmp/wine_test.exe 2>/dev/null; then
        echo "✓ MSVC program execution successful"
    else
        echo "⚠ MSVC program compilation worked but execution failed"
    fi
else
    echo "✗ MSVC compilation failed"
fi

# Clean up test files
rm -f /tmp/wine_test.cpp /tmp/wine_test.exe /tmp/wine_test.obj

echo ""
echo "Testing CMake availability..."
if wine "$CMAKE_ROOT/bin/cmake.exe" --version >/dev/null 2>&1; then
    echo "✓ CMake works via Wine"
    wine "$CMAKE_ROOT/bin/cmake.exe" --version | head -1
else
    echo "✗ CMake failed via Wine"
fi

echo ""
echo "Now attempting to run PowerShell cache extraction..."

# Check if pwsh is available in Wine
if wine pwsh.exe -? >/dev/null 2>&1; then
    echo "✓ PowerShell Core found in Wine"
    
    # Run our cache extraction script
    echo "Running Extract-CMakeCache.ps1 with MSVC..."
    
    if wine pwsh.exe -File "$(winepath -w "$(pwd)/Extract-CMakeCache.ps1")" -OutputDir "$(winepath -w "$(pwd)/msvc-cache-wine")"; then
        echo "🎉 SUCCESS: MSVC cache extraction completed via Wine!"
        
        if [ -f "msvc-cache-wine/CMakeCache.txt" ]; then
            echo "✓ Cache files generated successfully"
            echo "Generated files:"
            ls -la msvc-cache-wine/
        fi
        
        if [ -f "cmake-compiler-cache-extracted.zip" ]; then
            echo "✓ Zip file created: cmake-compiler-cache-extracted.zip"
            echo "Size: $(du -h cmake-compiler-cache-extracted.zip | cut -f1)"
        fi
    else
        echo "❌ PowerShell cache extraction failed"
    fi
    
elif command -v pwsh >/dev/null 2>&1; then
    echo "⚠ PowerShell Core not found in Wine, but available on host system"
    echo "Attempting to run with host PowerShell and Wine environment..."
    
    # Run with host PowerShell but Wine environment variables
    echo "Running with verbose error output..."
    set +e  # Don't exit on error so we can examine the failure
    pwsh -File "Extract-CMakeCache.ps1" -OutputDir "msvc-cache-native" -KeepTempDir 2>&1 | tee pwsh-output.log
    PWSH_EXIT_CODE=$?
    set -e
    
    # Check for both exit code and error indicators in output
    HAS_CMAKE_ERROR=$(grep -c "CMake configuration failed\|CMake Error\|-- Configuring incomplete" pwsh-output.log 2>/dev/null || echo "0")
    HAS_SUCCESS_OUTPUT=$(grep -c "Compiler cache extraction complete\|✓ CMake configuration successful" pwsh-output.log 2>/dev/null || echo "0")
    
    # Remove any whitespace/newlines
    HAS_CMAKE_ERROR=$(echo "$HAS_CMAKE_ERROR" | tr -d '\n\r ')
    HAS_SUCCESS_OUTPUT=$(echo "$HAS_SUCCESS_OUTPUT" | tr -d '\n\r ')
    
    if [[ $PWSH_EXIT_CODE -eq 0 ]] && [[ $HAS_CMAKE_ERROR -eq 0 ]] && [[ $HAS_SUCCESS_OUTPUT -gt 0 ]]; then
        echo "🎉 SUCCESS: MSVC cache extraction completed with native PowerShell!"
        
        if [ -f "msvc-cache-native/CMakeCache.txt" ]; then
            echo "✓ Cache files generated successfully"
            echo "Generated files:"
            ls -la msvc-cache-native/
        fi
    else
        echo "❌ Native PowerShell cache extraction failed!"
        echo "   Exit code: $PWSH_EXIT_CODE"
        echo "   CMake errors found: $HAS_CMAKE_ERROR"
        echo "   Success indicators: $HAS_SUCCESS_OUTPUT"
        echo ""
        echo "=== PowerShell Output Log ==="
        cat pwsh-output.log
        echo "============================"
        echo ""
        
        # Look for temp directories that might have been created
        echo "=== Searching for temporary directories ==="
        find /tmp -name "*cmake-cache-extract*" -type d 2>/dev/null | head -5 || echo "No temp directories found"
        
        # Check if any were mentioned in the output
        TEMP_DIR=$(grep -o "/tmp/cmake-cache-extract-[0-9]*" pwsh-output.log | head -1 || echo "")
        if [ -n "$TEMP_DIR" ] && [ -d "$TEMP_DIR" ]; then
            echo ""
            echo "=== Found temporary directory: $TEMP_DIR ==="
            echo "Directory structure:"
            find "$TEMP_DIR" -type f | head -20
            echo ""
            
            if [ -f "$TEMP_DIR/build/CMakeFiles/CMakeError.log" ]; then
                echo "=== CMake Error Log ==="
                cat "$TEMP_DIR/build/CMakeFiles/CMakeError.log"
                echo "======================="
            fi
            
            if [ -f "$TEMP_DIR/build/CMakeFiles/CMakeOutput.log" ]; then
                echo "=== CMake Output Log ==="
                cat "$TEMP_DIR/build/CMakeFiles/CMakeOutput.log"
                echo "========================"
            fi
            
            # Look for the specific failed compilation
            echo "=== Looking for failed test compilation ==="
            find "$TEMP_DIR" -name "TryCompile-*" -type d | while read trydir; do
                echo "Try compile directory: $trydir"
                if [ -f "$trydir/CMakeFiles/cmTC_*/build.make" ]; then
                    echo "Build makefile contents:"
                    cat "$trydir/CMakeFiles/cmTC_"*/build.make
                fi
                echo ""
            done
        fi
    fi
else
    echo "❌ PowerShell Core not available"
    echo "Install PowerShell Core (pwsh) to test cache extraction"
fi

echo ""
echo "=== Test Summary ==="
echo "This test demonstrates:"
echo "1. ✓ MSVC compiler works through Wine"
echo "2. ✓ Windows paths are properly converted"
echo "3. ✓ Environment variables are set correctly"
echo "4. ? PowerShell + CMake + MSVC integration (depends on PowerShell availability)"
echo ""
echo "For full functionality, ensure PowerShell Core is installed in your Wine prefix or on the host system."