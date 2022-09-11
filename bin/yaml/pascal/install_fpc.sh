#!/usr/bin/env bash
#
# Generic FPC install script
#
# Modified version of:
#   Free Pascal installation script for Unixy platforms.
#   Copyright 1996-2004 Michael Van Canneyt, Marco van de Voort and Peter Vreman
#

VERSION=$1
FULLVERSION=$VERSION
PARAMINSTALLPATH=$2

#
#
#
CMDTAR="tar"
TAR="$CMDTAR --no-same-owner"
# Untar files ($3,optional) from  file ($1) to the given directory ($2)
unztar() {
    $TAR -xzf "$HERE/$1" -C "$2" "$3"
}

# Untar tar.gz file ($2) from file ($1) and untar result to the given directory ($3)
unztarfromtar() {
    $CMDTAR -xOf "$HERE/$1" "$2" | $TAR -C "$3" -xzf -
}

# Get file list from tar archive ($1) in variable ($2)
# optionally filter result through sed ($3)
listtarfiles() {
    askvar="$2"
    # shellcheck disable=SC2034
    if [ -n "$3" ]; then
        list=$($CMDTAR tvf "$1" | awk '{ print $(NF) }' | sed -n /"$3"/p)
    else
        list=$($CMDTAR tvf "$1" | awk '{ print $(NF) }')
    fi
    # shellcheck disable=SC2086
    eval $askvar='$list'
}

# Make all the necessary directories to get $1
makedirhierarch() {
    mkdir -p "$1"
}

# check to see if something is in the path
checkpath() {
    ARG="$1"
    OLDIFS="$IFS"
    IFS=":"
    eval set "$PATH"
    IFS="$OLDIFS"
    for i; do
        if [ "$i" = "$ARG" ]; then
            return 0
        fi
    done
    return 1
}

# Install files from binary-*.tar
#  $1 = cpu-target
#  $2 = cross prefix
installbinary() {
    if [ "$2" = "" ]; then
        FPCTARGET="$1"
        CROSSPREFIX=
    else
        FPCTARGET="${2%-}"
        CROSSPREFIX="$2"
    fi

    BINARYTAR="${CROSSPREFIX}binary.$1.tar"

    # conversion from long to short archname for ppc<x>
    case $FPCTARGET in
    m68k*)
        PPCSUFFIX=68k
        ;;
    sparc*)
        PPCSUFFIX=sparc
        ;;
    i386*)
        PPCSUFFIX=386
        ;;
    powerpc64*)
        PPCSUFFIX=ppc64
        ;;
    powerpc*)
        PPCSUFFIX=ppc
        ;;
    arm*)
        PPCSUFFIX=arm
        ;;
    x86_64*)
        PPCSUFFIX=x64
        ;;
    mips*)
        PPCSUFFIX=mips
        ;;
    ia64*)
        PPCSUFFIX=ia64
        ;;
    alpha*)
        PPCSUFFIX=axp
        ;;
    esac

    # Install compiler/RTL. Mandatory.
    echo "Installing compiler and RTL for $FPCTARGET..."
    unztarfromtar "$BINARYTAR" "${CROSSPREFIX}base.$1.tar.gz" "$PREFIX"

    if [ -f "binutils-${CROSSPREFIX}$1.tar.gz" ]; then
        if yesno "Install Cross binutils"; then
            unztar "binutils-${CROSSPREFIX}$1.tar.gz" "$PREFIX"
        fi
    fi

    # Install symlink
    rm -f "$EXECDIR/ppc${PPCSUFFIX}"
    ln -sfr "$LIBDIR/ppc${PPCSUFFIX}" "$EXECDIR/ppc${PPCSUFFIX}"

    echo "Installing rtl packages..."
    local packages
    listtarfiles "$BINARYTAR" packages units-rtl
    for f in $packages; do
        # shellcheck disable=SC2001
        p=$(echo "$f" | sed -e 's+^.*units-\([^\.]*\)\..*+\1+')
        echo "Installing $p"
        unztarfromtar "$BINARYTAR" "$f" "$PREFIX"
    done

    echo "Installing fcl..."
    listtarfiles "$BINARYTAR" packages units-fcl
    for f in $packages; do
        # shellcheck disable=SC2001
        p=$(echo "$f" | sed -e 's+^.*units-\([^\.]*\)\..*+\1+')
        echo "Installing $p"
        unztarfromtar "$BINARYTAR" "$f" "$PREFIX"
    done

    echo "Installing packages..."
    listtarfiles "$BINARYTAR" packages units
    for f in $packages; do
        if ! echo "$f" | grep -q fcl >/dev/null; then
            if ! echo "$f" | grep -q rtl >/dev/null; then
                # shellcheck disable=SC2001
                p=$(echo "$f" | sed -e 's+^.*units-\([^\.]*\)\..*+\1+')
                echo "Installing $p"
                unztarfromtar "$BINARYTAR" "$f" "$PREFIX"
            fi
        fi
    done

    echo "Installing utilities..."
    listtarfiles "$BINARYTAR" packages "${CROSSPREFIX}utils"
    for f in $packages; do
        # shellcheck disable=SC2001
        p=$(echo "$f" | sed -e 's+^.*utils-\([^\.]*\)\..*+\1+' -e 's+^.*\(utils\)[^\.]*\..*+\1+')
        echo "Installing $p"
        unztarfromtar "$BINARYTAR" "$f" "$PREFIX"
    done

    rm -f -- *."$1".tar.gz
}

# --------------------------------------------------------------------------
# welcome message.
#

echo "This shell script will attempt to install the Free Pascal Compiler"
echo "version $FULLVERSION with the items you select"
echo

# Here we start the thing.
HERE=$(pwd)

# Support ~ expansion
PREFIX=$(eval echo "$PARAMINSTALLPATH")
export PREFIX
makedirhierarch "$PREFIX"

# Set some defaults.
LIBDIR="$PREFIX/lib/fpc/$VERSION"
EXECDIR="$PREFIX/bin"

# Install all binary releases
for f in *binary*.tar; do
    # shellcheck disable=SC2001
    target=$(echo "$f" | sed 's+^.*binary\.\(.*\)\.tar$+\1+')
    # shellcheck disable=SC2001
    cross=$(echo "$f" | sed 's+binary\..*\.tar$++')

    # cross install?
    if [ "$cross" != "" ]; then
        if [ "$(command -v fpc 2>/dev/null)" = '' ]; then
            echo "No native FPC found."
            echo "For a proper installation of a cross FPC the installation of a native FPC is required."
            exit 1
        else
            if [ "$(fpc -iV)" != "$VERSION" ]; then
                echo "Warning: Native and cross FPC doesn't match; this could cause problems"
            fi
        fi
    fi
    installbinary "$target" "$cross"
done

echo Done.
echo

# The End
echo
echo End of installation.
echo
echo Refer to the documentation for more information.
echo
