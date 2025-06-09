#!/bin/bash
# Wine wrapper for cl.exe to be used by CMake
# This script makes cl.exe work transparently with CMake on Linux

MSVC_ROOT="/media/patrick-quist/D0-P1/efs/compilers/msvc/14.40.33807-14.40.33811.0"
SDK_ROOT="/media/patrick-quist/D0-P1/efs/compilers/windows-kits-10"

# Set up Wine environment
export WINEPREFIX="${HOME}/.wine-msvc-test"
export WINEARCH="win64"

# Set up MSVC environment variables in Wine format
MSVC_WIN="$(winepath -w "$MSVC_ROOT")"
SDK_WIN="$(winepath -w "$SDK_ROOT")"

export VCINSTALLDIR="$MSVC_WIN\\"
export WindowsSdkDir="$SDK_WIN\\"
export WindowsSDKVersion="10.0.22621.0"

# Set up include and library paths
INCLUDE_PATHS="$MSVC_WIN\\include;$SDK_WIN\\Include\\10.0.22621.0\\ucrt;$SDK_WIN\\Include\\10.0.22621.0\\shared;$SDK_WIN\\Include\\10.0.22621.0\\um"
LIB_PATHS="$MSVC_WIN\\lib\\x64;$SDK_WIN\\Lib\\10.0.22621.0\\ucrt\\x64;$SDK_WIN\\Lib\\10.0.22621.0\\um\\x64"

export INCLUDE="$INCLUDE_PATHS"
export LIB="$LIB_PATHS"
export LIBPATH="$LIB_PATHS"

# Convert arguments to Windows paths and handle MSVC-specific issues
WINE_ARGS=()
OUTPUT_FILE=""
COMPILE_ONLY=false
SKIP_NEXT=false

# First pass: identify compilation mode and output file
i=0
args=("$@")
while [[ $i -lt ${#args[@]} ]]; do
    arg="${args[$i]}"
    if [[ "$arg" == "-c" ]]; then
        COMPILE_ONLY=true
    elif [[ "$arg" == "-o" ]] && [[ $((i+1)) -lt ${#args[@]} ]]; then
        OUTPUT_FILE="${args[$((i+1))]}"
        ((i++))  # Skip next argument as we've processed it
    fi
    ((i++))
done

# Second pass: convert arguments and handle MSVC quirks
i=0
while [[ $i -lt ${#args[@]} ]]; do
    arg="${args[$i]}"

    if [[ "$SKIP_NEXT" == "true" ]]; then
        SKIP_NEXT=false
        ((i++))
        continue
    fi

    if [[ "$arg" == "-o" ]]; then
        # Skip -o flag and its argument for MSVC (we'll use /Fo instead)
        SKIP_NEXT=true
        ((i++))
        continue
    elif [[ "$arg" =~ ^/.* ]] && [[ -f "$arg" || -d "$arg" ]]; then
        # Convert absolute file/directory paths to Windows paths
        WINE_ARGS+=("$(winepath -w "$arg")")
    elif [[ "$arg" =~ \.(c|cpp|cxx|cc|C|o|obj)$ ]]; then
        # Convert source/object files to Windows paths
        if [[ "$arg" =~ ^/.* ]]; then
            # Absolute path
            WINE_ARGS+=("$(winepath -w "$arg")")
        else
            # Relative path - make absolute first
            WINE_ARGS+=("$(winepath -w "$(pwd)/$arg")")
        fi
    elif [[ "$arg" =~ CMakeFiles/.* ]]; then
        # Convert CMake-generated relative paths to Windows paths
        WINE_ARGS+=("$(winepath -w "$(pwd)/$arg")")
    else
        # Keep all other arguments (flags, options) as-is
        WINE_ARGS+=("$arg")
    fi
    ((i++))
done

# Handle output file for compilation
if [[ -n "$OUTPUT_FILE" ]] && [[ "$COMPILE_ONLY" == "true" ]]; then
    # For compilation, use MSVC's /Fo flag
    if [[ "$OUTPUT_FILE" =~ ^/.* ]]; then
        WINE_ARGS+=("/Fo$(winepath -w "$OUTPUT_FILE")")
    else
        WINE_ARGS+=("/Fo$(winepath -w "$(pwd)/$OUTPUT_FILE")")
    fi
fi

# Debug logging
if [[ "${WINE_CL_DEBUG:-}" == "1" ]]; then
    echo "=== Wine CL Wrapper Debug ===" >&2
    echo "Original args: $*" >&2
    echo "Converted args: ${WINE_ARGS[*]}" >&2
    echo "Working directory: $(pwd)" >&2
    echo "INCLUDE: $INCLUDE" >&2
    echo "LIB: $LIB" >&2
    echo "=============================" >&2
fi

# Execute cl.exe through Wine
wine "$MSVC_ROOT/bin/Hostx64/x64/cl.exe" "${WINE_ARGS[@]}"
WINE_EXIT_CODE=$?

# Post-compilation: Handle .o vs .obj extension issue
if [[ $WINE_EXIT_CODE -eq 0 ]] && [[ "$COMPILE_ONLY" == "true" ]] && [[ -n "$OUTPUT_FILE" ]]; then
    if [[ "$OUTPUT_FILE" =~ \.o$ ]]; then
        # CMake expects .o but MSVC creates .obj
        OBJ_FILE="${OUTPUT_FILE%.o}.obj"

        # Make paths absolute
        if [[ "$OUTPUT_FILE" =~ ^/.* ]]; then
            ABS_O_FILE="$OUTPUT_FILE"
            ABS_OBJ_FILE="$OBJ_FILE"
        else
            ABS_O_FILE="$(pwd)/$OUTPUT_FILE"
            ABS_OBJ_FILE="$(pwd)/$OBJ_FILE"
        fi

        # If MSVC created .obj file, create a symlink as .o
        if [[ -f "$ABS_OBJ_FILE" ]] && [[ ! -f "$ABS_O_FILE" ]]; then
            ln -s "$(basename "$ABS_OBJ_FILE")" "$ABS_O_FILE" 2>/dev/null || cp "$ABS_OBJ_FILE" "$ABS_O_FILE"
        fi
    fi
fi

exit $WINE_EXIT_CODE
